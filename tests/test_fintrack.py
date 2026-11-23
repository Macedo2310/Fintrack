"""Fluxos principais da FinTrack contra o backend real (FastAPI + SQLite temporário)."""
import concurrent.futures
import socket
import sqlite3
import threading
import time
from datetime import date, timedelta

import httpx
import pytest
import uvicorn

import app as fintrack
import backend_services as svc
import video_lessons
from fastapi.testclient import TestClient

TODAY = svc.local_today()


def iso(d):
    return d.isoformat()


def tx(c, type_="receita", amount="100", category=None, day=None, **extra):
    body = {"type": type_, "category": category or ("Mesada" if type_ == "receita" else "Alimentação"),
            "description": extra.pop("description", "Lançamento"), "amount": amount, "date": iso(day or TODAY), **extra}
    return c.post("/api/transactions", json=body)


def complete_intro(c, module, monkeypatch):
    """Simula a reprodução contínua: o relógio do servidor avança junto com a posição."""
    clock = [1_000_000.0]
    monkeypatch.setattr(video_lessons.time, "time", lambda: clock[0])
    start = c.post(f"/api/intro/{module}/start").json()
    duration = start["duration"]
    pos = 0.0
    while pos < duration:
        pos = min(duration, pos + 5)
        clock[0] += 5
        r = c.post(f"/api/intro/{module}/tick", json={"token": start["token"], "position": pos}).json()
        assert r["accepted"]
    assert r["completed"]
    monkeypatch.undo()


# 1. Cadastro, login, logout e sessão expirada ---------------------------------
def test_signup_login_logout_and_expired_session(server_app, make_client):
    aluno = make_client("aluno")
    prof = make_client("professor")
    assert aluno.get("/api/auth/me").json()["role"] == "aluno"
    assert prof.get("/api/auth/me").json()["role"] == "professor"

    fintrack.reset_rate_limits()
    c = TestClient(server_app)
    weak = c.post("/api/auth/register", json={"name": "Fraca", "email": "fraca@example.com", "password": "somenteletras", "role": "aluno", "terms": True})
    assert weak.status_code == 422 and "letra e um número" in weak.json()["detail"]
    assert c.post("/api/auth/register", json={"name": "X", "email": "nao-email", "password": "Senha123", "role": "aluno", "terms": True}).status_code == 422
    assert c.post("/api/auth/register", json={"name": "Sem termos", "email": "t@example.com", "password": "Senha123", "role": "aluno", "terms": False}).status_code == 422
    assert c.post("/api/auth/register", json={"name": "Admin", "email": "adm@example.com", "password": "Senha123", "role": "admin", "terms": True}).status_code == 422
    # e-mail repetido não revela detalhes
    assert c.post("/api/auth/register", json={"name": "Dup", "email": aluno.email, "password": "Senha123", "role": "aluno", "terms": True}).status_code == 400

    login = TestClient(server_app)
    assert login.post("/api/auth/login", json={"email": aluno.email, "password": "errada123"}).status_code == 401
    r = login.post("/api/auth/login", json={"email": aluno.email.upper(), "password": "Senha123segura"})
    assert r.status_code == 200 and r.json()["next"] == "/app.html"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert login.get("/api/auth/me").status_code == 200
    assert login.post("/api/auth/logout").status_code == 200
    assert login.get("/api/auth/me").status_code == 401

    with sqlite3.connect(fintrack.DB_PATH) as db:
        db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00Z' WHERE user_id=?", (aluno.uid,))
    expired = aluno.get("/api/auth/me")
    assert expired.status_code == 401 and expired.json()["detail"] == "Sessão expirada."
    # página interna sem sessão não é entregue
    assert aluno.get("/app.html").status_code == 401


def test_login_rate_limit_and_honest_password_recovery(server_app, make_client):
    u = make_client()
    c = TestClient(server_app)
    codes = [c.post("/api/auth/login", json={"email": u.email, "password": "Errada0000"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = c.post("/api/auth/forgot", json={"email": u.email})
    assert r.status_code == 503 and "não está configurada" in r.json()["detail"]
    other = c.post("/api/auth/forgot", json={"email": "ninguem@example.com"})
    assert other.status_code == 503 and other.json() == r.json()  # não revela existência da conta
    assert c.post("/api/auth/reset", json={"token": "x" * 20, "password": "NovaSenha1"}).status_code == 400


def test_signup_rate_limit(server_app):
    c = TestClient(server_app)
    codes = [c.post("/api/auth/register", json={"name": "Lote", "email": f"lote{i}@example.com", "password": "Senha123segura", "role": "aluno", "terms": True}).status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_validation_errors_are_plain_portuguese(server_app, make_client):
    c = make_client()
    r = c.post("/api/goals", json={"title": "", "target": "10", "deadline": iso(TODAY)})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and "título" in r.json()["detail"]


# 2. Isolamento entre contas ---------------------------------------------------
def test_accounts_cannot_read_or_change_each_other(make_client):
    a, b = make_client(), make_client()
    tid = tx(a, amount="50").json()["id"]
    gid = a.post("/api/goals", json={"title": "Fone", "target": "200", "deadline": iso(TODAY + timedelta(days=30))}).json()["id"]
    cid = a.post("/api/ai/conversations").json()["id"]
    assert b.get("/api/transactions").json()["total"] == 0
    body = {"type": "receita", "category": "Mesada", "description": "invasão", "amount": "1", "date": iso(TODAY)}
    assert b.put(f"/api/transactions/{tid}", json=body).status_code == 404
    assert b.delete(f"/api/transactions/{tid}").status_code == 404
    assert b.post(f"/api/goals/{gid}/reserve", json={"amount": "1"}).status_code == 404
    assert b.delete(f"/api/goals/{gid}").status_code == 404
    assert b.get(f"/api/ai/conversations/{cid}").status_code == 404
    assert b.get("/api/goals").json()["items"] == []
    assert b.get("/api/dashboard").json()["balance_total"] == 0
    assert a.get("/api/dashboard").json()["balance_total"] == 5000


# 3. Transações -----------------------------------------------------------------
def test_transactions_crud_search_filters_and_validation(make_client):
    c = make_client()
    assert tx(c, amount="0").status_code == 422
    assert tx(c, amount="-5").status_code == 422
    assert tx(c, amount="abc").status_code == 422
    assert tx(c, amount="1000000000,01").status_code == 422  # acima do limite
    assert tx(c, category="Salário", type_="despesa").status_code == 422  # categoria de outro tipo
    assert tx(c, description="").status_code == 422

    tx(c, amount="1.234,56", description="Bolsa de estudos", category="Bolsa")
    tx(c, "despesa", "45,90", description="Lanche_cantina 100%", category="Alimentação", day=TODAY - timedelta(days=40))
    tid = tx(c, "despesa", "12,10", description="Ônibus", category="Transporte").json()["id"]

    r = c.get("/api/transactions").json()
    assert r["total"] == 3 and r["summary"] == {"receitas": 123456, "despesas": 5800, "resultado": 117656}
    assert c.get("/api/transactions", params={"q": "100%"}).json()["total"] == 1  # curinga escapado
    assert c.get("/api/transactions", params={"q": "_"}).json()["total"] == 1
    assert c.get("/api/transactions", params={"q": "transp"}).json()["total"] == 1  # busca por categoria
    f = c.get("/api/transactions", params={"type": "despesa", "start": iso(TODAY - timedelta(days=7))}).json()
    assert f["total"] == 1 and f["summary"]["despesas"] == 1210 and f["summary"]["receitas"] == 0
    amounts = [x["amount_cents"] for x in c.get("/api/transactions", params={"sort": "amount_desc"}).json()["items"]]
    assert amounts == sorted(amounts, reverse=True)
    page = c.get("/api/transactions", params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1

    c.put(f"/api/transactions/{tid}", json={"type": "despesa", "category": "Transporte", "description": "Metrô", "amount": "8", "date": iso(TODAY)})
    assert c.get("/api/transactions", params={"q": "Metrô"}).json()["items"][0]["amount_cents"] == 800
    assert c.delete(f"/api/transactions/{tid}").status_code == 200
    assert c.get("/api/transactions").json()["total"] == 2

    assert c.post("/api/categories", json={"type": "despesa", "name": "Material escolar"}).status_code == 200
    assert c.post("/api/categories", json={"type": "despesa", "name": "material ESCOLAR"}).status_code == 409
    assert tx(c, "despesa", "30", category="Material escolar").status_code == 200
    assert "Material escolar" not in str(make_client().get("/api/categories").json())  # categoria é por conta


def test_recurrence_generates_without_duplicates_and_scoped_changes(make_client):
    c = make_client()
    start = TODAY - timedelta(days=21)
    r = tx(c, "despesa", "20", category="Assinaturas", description="Streaming", day=start,
           recurrence={"enabled": True, "frequency": "semanal", "start_date": iso(start)})
    assert r.status_code == 200
    items = c.get("/api/transactions").json()["items"]
    dates = sorted(x["date"] for x in items)
    assert dates == [iso(start + timedelta(days=7 * i)) for i in range(4)]
    assert all(x["recurrence_active"] == 1 and x["recurrence_frequency"] == "semanal" for x in items)
    fintrack.generate_recurrences()
    fintrack.generate_recurrences()
    assert c.get("/api/transactions").json()["total"] == 4  # sem duplicidade

    second = sorted(items, key=lambda x: x["date"])[1]
    body = {"type": "despesa", "category": "Assinaturas", "description": "Streaming família", "amount": "35", "date": second["date"]}
    c.put(f"/api/transactions/{second['id']}?scope=future", json=body)
    after = sorted(c.get("/api/transactions").json()["items"], key=lambda x: x["date"])
    assert [x["amount_cents"] for x in after] == [2000, 3500, 3500, 3500]
    assert c.put(f"/api/transactions/{second['id']}?scope=tudo", json=body).status_code == 422

    third = after[2]
    d = c.delete(f"/api/transactions/{third['id']}?scope=future").json()
    assert d["deleted"] == 2
    rest = c.get("/api/transactions").json()["items"]
    assert len(rest) == 2 and all(x["recurrence_active"] == 0 for x in rest)
    fintrack.generate_recurrences()
    assert c.get("/api/transactions").json()["total"] == 2  # recorrência encerrada não volta


# 4 e 6. Cálculos e metas -------------------------------------------------------
def test_balance_rules_and_goal_lifecycle(make_client):
    c = make_client()
    tx(c, amount="500")
    tx(c, "despesa", "120")
    tx(c, amount="300", day=TODAY - timedelta(days=70))  # fora do período padrão (mês atual)
    tx(c, amount="999", day=TODAY + timedelta(days=10))  # futuro: não entra no saldo de hoje
    gid = c.post("/api/goals", json={"title": "Notebook", "target": "1000", "deadline": iso(TODAY + timedelta(days=5))}).json()["id"]
    assert c.post("/api/goals", json={"title": "Antiga", "target": "10", "deadline": iso(TODAY - timedelta(days=1))}).status_code == 422

    assert c.post(f"/api/goals/{gid}/reserve", json={"amount": "200"}).status_code == 200
    d = c.get("/api/dashboard", params={"start": iso(TODAY.replace(day=1)), "end": iso(TODAY)}).json()
    assert d["balance_total"] == 68000  # 500 - 120 + 300; reserva não reduz o saldo total
    assert d["reserved"] == 20000 and d["available"] == 48000
    assert d["despesas"] == (12000 if TODAY.day >= 1 else 0)  # reserva não vira despesa
    assert d["resultado"] == d["receitas"] - d["despesas"]
    assert len(d["months"]) == 6 and d["months"][-1]["month"] == TODAY.strftime("%Y-%m")
    assert any(m["receitas"] == 0 and m["despesas"] == 0 for m in d["months"])  # meses vazios aparecem

    assert c.post(f"/api/goals/{gid}/reserve", json={"amount": "481"}).json()["detail"] == "O valor excede seu saldo disponível."
    assert c.post(f"/api/goals/{gid}/withdraw", json={"amount": "250"}).status_code == 422
    c.post(f"/api/goals/{gid}/withdraw", json={"amount": "50"})
    g = c.get("/api/goals").json()
    goal = g["items"][0]
    assert goal["reserved_cents"] == 15000 and goal["remaining_cents"] == 85000 and goal["percent"] == 15 and goal["state"] == "ativa"
    assert g["available"] == 68000 - 15000

    c.put(f"/api/goals/{gid}", json={"title": "Notebook", "target": "150", "deadline": goal["deadline"]})
    assert c.get("/api/goals").json()["items"][0]["state"] == "pronta"
    assert c.post(f"/api/goals/{gid}/complete").status_code == 200
    assert c.post(f"/api/goals/{gid}/complete").status_code == 422
    assert c.put(f"/api/goals/{gid}", json={"title": "x", "target": "1", "deadline": goal["deadline"]}).status_code == 422
    assert c.get("/api/goals").json()["items"][0]["state"] == "concluida"
    assert c.get("/api/dashboard").json()["reserved"] == 15000  # reserva continua separada após concluir
    c.delete(f"/api/goals/{gid}")
    d2 = c.get("/api/dashboard").json()
    assert d2["reserved"] == 0 and d2["balance_total"] == 68000 and d2["available"] == 68000
    assert c.get("/api/goals").json()["items"] == []


# 5. Reservas simultâneas -------------------------------------------------------
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_simultaneous_reservations_cannot_spend_same_balance(server_app):
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(server_app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        c = httpx.Client(base_url=base)
        c.post("/api/auth/register", json={"name": "Concorrência", "email": f"conc{port}@example.com", "password": "Senha123segura", "role": "aluno", "terms": True})
        c.post("/api/transactions", json={"type": "receita", "category": "Mesada", "description": "Base", "amount": "100", "date": iso(TODAY)})
        g1 = c.post("/api/goals", json={"title": "A", "target": "100", "deadline": iso(TODAY + timedelta(days=9))}).json()["id"]
        g2 = c.post("/api/goals", json={"title": "B", "target": "100", "deadline": iso(TODAY + timedelta(days=9))}).json()["id"]
        cookies = dict(c.cookies)

        def reserve(gid):
            with httpx.Client(base_url=base, cookies=cookies) as cl:
                return cl.post(f"/api/goals/{gid}/reserve", json={"amount": "80"}).status_code

        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(reserve, [g1, g2] * 4))
        assert codes.count(200) == 1 and codes.count(422) == 7
        d = c.get("/api/dashboard").json()
        assert d["reserved"] == 8000 and d["available"] == 2000
    finally:
        server.should_exit = True
        thread.join(5)


# 7 e 8. Educação e vídeos ------------------------------------------------------
def test_video_gate_resume_and_skip_protection(make_client, monkeypatch):
    c = make_client()
    m = c.get("/api/education").json()["modules"]
    assert len(m) == 4 and sum(len(x["topics"]) for x in m) == 12
    assert m[0]["topics"][0]["acts"] == []  # sem conteúdo antes do vídeo
    assert c.post("/api/education/poupanca/o-que-e/check", json={"i": 0, "answer": 1}).status_code == 403

    clock = [5000.0]
    monkeypatch.setattr(video_lessons.time, "time", lambda: clock[0])
    s = c.post("/api/intro/poupanca/start").json()
    clock[0] += 5
    assert c.post("/api/intro/poupanca/tick", json={"token": s["token"], "position": 5}).json()["accepted"]
    clock[0] += 1
    jump = c.post("/api/intro/poupanca/tick", json={"token": s["token"], "position": s["duration"]}).json()
    assert not jump["accepted"] and not jump["completed"] and jump["watched"] == 5  # avançar a barra não libera
    # outra aba invalida o token anterior
    s2 = c.post("/api/intro/poupanca/start").json()
    assert s2["watched"] == 5  # retomada do ponto salvo
    assert c.post("/api/intro/poupanca/tick", json={"token": s["token"], "position": 6}).status_code == 409
    monkeypatch.undo()
    complete_intro(c, "poupanca", monkeypatch)
    again = c.post("/api/intro/poupanca/start").json()
    assert again["completed"] is True  # vídeo já concluído continua concluído
    assert len(c.get("/api/education").json()["modules"][0]["topics"][0]["acts"]) == 3
    assert make_client().post("/api/intro/poupanca/start").json()["completed"] is False  # progresso por conta
    assert c.get("/api/intro/poupanca/media", headers={"Range": "bytes=0-99"}).status_code == 206
    assert TestClient(fintrack.app).get("/api/intro/poupanca/media").status_code == 401
    assert TestClient(fintrack.app).get("/media/education/poupanca.mp4").status_code == 404


def test_lessons_grading_server_side_and_progress(make_client, monkeypatch):
    c = make_client()
    complete_intro(c, "poupanca", monkeypatch)
    pub = c.get("/api/education").json()
    assert pub["pass"] == 70
    assert all("ans" not in a and "why" not in a for a in pub["modules"][0]["topics"][1]["acts"])  # respostas não vão ao navegador

    ok = c.post("/api/education/poupanca/vantagens/check", json={"i": 1, "answer": "4.500"}).json()
    assert ok["ok"] and "700 + 450" in ok["why"]
    assert c.post("/api/education/poupanca/vantagens/check", json={"i": 1, "answer": "4500,00"}).json()["ok"]
    assert c.post("/api/education/poupanca/vantagens/check", json={"i": 0, "answer": [0, 9]}).status_code == 422

    bad = c.post("/api/education/poupanca/vantagens/submit", json={"answers": [[1], "100", "1", 0]}).json()
    assert bad["score"] == 0 and not bad["completed"] and bad["attempts"] == 1
    good = c.post("/api/education/poupanca/vantagens/submit", json={"answers": [[0, 2, 4], "4.500", "9", 1]}).json()
    assert good["score"] == 100 and good["completed"] and good["attempts"] == 2
    assert all(r["why"] for r in good["results"])
    worse = c.post("/api/education/poupanca/vantagens/submit", json={"answers": [[1], "1", "1", 0]}).json()
    assert worse["completed"] and worse["best"] == 100  # conclusão não é perdida
    prog = {(p["module_key"], p["topic_key"]): p for p in c.get("/api/education").json()["progress"]}
    assert prog[("poupanca", "vantagens")]["status"] == "concluida" and prog[("poupanca", "vantagens")]["score"] == 100

    complete_intro(c, "planejamento", monkeypatch)
    neg = c.post("/api/education/planejamento/plano/submit", json={"answers": [[-10, 50, 60], "240", 1]}).json()
    assert neg["results"][0]["ok"] is False  # orçamento com percentual negativo é recusado
    budget = c.post("/api/education/planejamento/plano/submit", json={"answers": [[50, 30, 20], "240", 1]}).json()
    assert budget["score"] == 100
    classify = c.post("/api/education/planejamento/metas/check", json={"i": 2, "answer": [0, 1, 2, 0, 0]}).json()
    assert classify["fraction"] == 0.8 and not classify["ok"]


def test_course_content_precision():
    from education_content import EDUCATION
    text = str(EDUCATION)
    assert "não é sinônimo de poupar" in text
    assert "É um exemplo adaptável" in text
    assert "Rendimentos não são garantidos" in text
    assert "Consulte a taxa vigente no Banco Central" in text
    titles = [t["title"] for m in EDUCATION for t in m["topics"]]
    assert titles == ["Poupar, investir e caderneta", "Reserva de emergência", "Começando com pouco", "Receitas e despesas",
                      "Necessidades, desejos e impulso", "Organização mensal", "Definindo metas", "Orçamento pessoal",
                      "Tesouro Direto", "Selic, juros e inflação", "Fundos imobiliários", "Liquidez, risco e diversificação"]
    kinds = {a["t"] for m in EDUCATION for t in m["topics"] for a in t["acts"]}
    assert kinds == {"quiz", "multi", "classify", "calc", "budget"}


# 9 e 10. Turmas, atribuições e privacidade -------------------------------------
def test_classes_assignments_and_financial_privacy(make_client, monkeypatch):
    prof, aluno, intruso, outro_prof = make_client("professor"), make_client("aluno"), make_client("aluno"), make_client("professor")
    assert aluno.post("/api/classes", json={"name": "Turma"}).status_code == 403
    k = prof.post("/api/classes", json={"name": "1º ano A", "description": "Educação financeira"}).json()
    cid, code = k["id"], k["code"]
    assert aluno.post("/api/classes/preview", json={"code": "ZZZZZZ"}).status_code == 404
    assert aluno.post("/api/classes/preview", json={"code": code.lower()}).json()["class"]["name"] == "1º ano A"

    # atribuição antes de o aluno entrar; aluno já tinha concluído outra aula
    complete_intro(aluno, "poupanca", monkeypatch)
    aluno.post("/api/education/poupanca/dicas/submit", json={"answers": ["1440", "180", 1, [0, 1, 0, 1, 0, 1]]})
    assert prof.post(f"/api/classes/{cid}/assignments", json={"content_key": "inexistente:x"}).status_code == 422
    assert prof.post(f"/api/classes/{cid}/assignments", json={"content_key": "poupanca:dicas", "due_date": iso(TODAY - timedelta(days=1))}).status_code == 422
    a1 = prof.post(f"/api/classes/{cid}/assignments", json={"content_key": "poupanca:o-que-e", "due_date": iso(TODAY + timedelta(days=2))}).json()["id"]
    prof.post(f"/api/classes/{cid}/assignments", json={"content_key": "poupanca:dicas"})
    assert outro_prof.post(f"/api/classes/{cid}/assignments", json={"content_key": "poupanca:dicas"}).status_code == 403

    assert aluno.post("/api/classes/join", json={"code": code}).status_code == 200
    assert aluno.post("/api/classes/join", json={"code": code}).status_code == 409
    mine = {x["content_key"]: x for x in aluno.get("/api/assignments").json()["items"]}
    assert mine["poupanca:o-que-e"]["state"] == "pendente" and mine["poupanca:o-que-e"]["title"] == "Poupar, investir e caderneta"
    assert mine["poupanca:dicas"]["state"] == "concluida"  # já concluída antes de entrar

    aluno.post("/api/education/poupanca/o-que-e/submit", json={"answers": [1, [0, 1, 1, 0, 1, 0], [0, 2, 4]]})
    results = prof.get(f"/api/classes/{cid}/assignment-results").json()["items"]
    assert {r["content_key"]: r["state"] for r in results} == {"poupanca:o-que-e": "concluida", "poupanca:dicas": "concluida"}
    assert next(r for r in results if r["assignment_id"] == a1)["score"] == 100
    assert outro_prof.get(f"/api/classes/{cid}/assignment-results").status_code == 403
    assert prof.get(f"/api/classes/{cid}/participants").json()["items"][0]["share_financial"] == 0

    # compartilhamento desativado por padrão e aplicado no backend
    tx(aluno, amount="250")
    tx(aluno, "despesa", "40")
    assert prof.get(f"/api/classes/{cid}/financial-summary").json()["items"] == []
    assert outro_prof.get(f"/api/classes/{cid}/financial-summary").status_code == 403
    assert intruso.put(f"/api/classes/{cid}/share", json={"enabled": True}).status_code == 404
    assert prof.put(f"/api/classes/{cid}/share", json={"enabled": True}).status_code == 403
    aluno.put(f"/api/classes/{cid}/share", json={"enabled": True})
    s = prof.get(f"/api/classes/{cid}/financial-summary").json()["items"][0]
    assert s == {"student_id": aluno.uid, "student_name": "Conta Teste", "receitas": 25000, "despesas": 4000, "resultado": 21000, "registros": 2}
    assert "description" not in str(s)
    # mesmo autorizado, professor não acessa lançamentos nem conversas
    cid_conv = aluno.post("/api/ai/conversations").json()["id"]
    assert prof.get(f"/api/ai/conversations/{cid_conv}").status_code == 404
    assert prof.get("/api/transactions").json()["total"] == 0
    aluno.put(f"/api/classes/{cid}/share", json={"enabled": False})
    assert prof.get(f"/api/classes/{cid}/financial-summary").json()["items"] == []

    # código: renovar e desativar
    new_code = prof.post(f"/api/classes/{cid}/code/renew").json()["code"]
    assert intruso.post("/api/classes/preview", json={"code": code}).status_code == 404
    assert outro_prof.post(f"/api/classes/{cid}/code/renew").status_code == 404
    prof.post(f"/api/classes/{cid}/code/disable")
    assert intruso.post("/api/classes/join", json={"code": new_code}).status_code == 404

    # saída da turma
    assert aluno.delete(f"/api/classes/{cid}/membership").status_code == 200
    assert aluno.get("/api/assignments").json()["items"] == []
    assert prof.get(f"/api/classes/{cid}/participants").json()["items"] == []


# 11. FinBot --------------------------------------------------------------------
def test_finbot_configured_unconfigured_and_provider_error(make_client, monkeypatch):
    c = make_client()
    assert c.get("/api/ai/status").json()["configured"] is False
    cid = c.post("/api/ai/conversations").json()["id"]
    r = c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "O que é Selic?", "request_key": "chave-0001"})
    assert r.status_code == 503 and "não está configurada" in r.json()["detail"]
    msgs = c.get(f"/api/ai/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user"]  # nenhuma resposta inventada
    tx(c, "despesa", "30")
    assert c.post("/api/ai/analyze-spending").status_code == 503

    monkeypatch.setenv("OPENAI_API_KEY", "teste-nao-real")
    def failing(_):
        raise RuntimeError("A OpenAI limitou as solicitações ou não há saldo/crédito disponível na API.")
    monkeypatch.setattr(fintrack, "call_ai", failing)
    e = c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "O que é Selic?", "request_key": "chave-0001"})
    assert e.status_code == 502 and "limitou" in e.json()["detail"]
    assert len(c.get(f"/api/ai/conversations/{cid}").json()["messages"]) == 1

    sent = []
    def fake(messages):
        sent.append(messages)
        return "A Selic é a taxa básica de juros."
    monkeypatch.setattr(fintrack, "call_ai", fake)
    ok = c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "O que é Selic?", "request_key": "chave-0001"}).json()
    assert ok["assistant_message"]["content"].startswith("A Selic")
    dup = c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "O que é Selic?", "request_key": "chave-0001"}).json()
    assert dup["duplicate"] is True and len(sent) == 1  # repetição não gera nova chamada
    assert c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "Outra", "request_key": "chave-0001"}).status_code == 409
    assert len(c.get(f"/api/ai/conversations/{cid}").json()["messages"]) == 2

    analysis = c.post("/api/ai/analyze-spending").json()
    assert analysis["has_data"] and "descri" not in str(sent[-1]).lower().split("separe")[0]
    assert "Lançamento" not in str(sent[-1])  # descrições não são enviadas, só agregados

    c.patch(f"/api/ai/conversations/{cid}", json={"title": "Juros"})
    assert c.get("/api/ai/conversations").json()["items"][0]["title"] == "Juros"
    assert c.delete(f"/api/ai/conversations/{cid}").status_code == 200
    assert c.get("/api/ai/conversations").json()["items"] == []


# 12. Indicadores ---------------------------------------------------------------
def test_market_fresh_stale_and_unavailable(make_client, monkeypatch):
    c = make_client()
    with sqlite3.connect(fintrack.DB_PATH) as db:
        db.execute("DELETE FROM market_cache")
    svc._retry_after.clear()

    def fake(key):
        if key in ("SELIC", "IPCA"):
            raise TimeoutError("simulado")
        return {"key": key, "label": key, "value": 5.1234, "unit": "BRL · PTAX venda", "observed_at": iso(TODAY), "reference": "Fechamento", "source": "Banco Central do Brasil", "source_url": "simulado"}
    monkeypatch.setattr(svc, "fetch_indicator", fake)
    m = c.get("/api/market").json()
    assert {i["key"]: i["status"] for i in m["items"]} == {"USD": "atualizado", "EUR": "atualizado"}
    assert set(m["unavailable"]) == {"SELIC", "IPCA"}  # sem valores inventados

    with sqlite3.connect(fintrack.DB_PATH) as db:
        db.execute("UPDATE market_cache SET fetched_at=fetched_at-7200")
    def down(key):
        raise TimeoutError("fonte fora do ar")
    monkeypatch.setattr(svc, "fetch_indicator", down)
    svc._retry_after.clear()
    stale = c.get("/api/market").json()
    assert all(i["stale"] and i["status"] == "antigo" for i in stale["items"]) and len(stale["items"]) == 2
    assert TestClient(fintrack.app).get("/api/market").status_code == 401


# 13. Lembretes -----------------------------------------------------------------
def test_reminders_per_account_without_duplicates(make_client, monkeypatch):
    c, other = make_client(), make_client()
    tx(c, amount="100")
    tx(c, "despesa", "150")  # despesas > receitas sem limite definido
    c.post("/api/goals", json={"title": "Viagem", "target": "900", "deadline": iso(TODAY + timedelta(days=3))})
    first = c.get("/api/notifications").json()
    kinds = sorted(n["kind"] for n in first["items"])
    assert kinds == ["goal", "spending"] and first["unread"] == 2
    again = c.get("/api/notifications").json()
    assert again["total"] == 2  # sem duplicação
    c.post("/api/notifications/read-all")
    assert c.get("/api/notifications").json() == {**c.get("/api/notifications").json(), "unread": 0, "total": 2}
    assert other.get("/api/notifications").json()["total"] == 0
    assert other.post(f"/api/notifications/{first['items'][0]['id']}/read").status_code == 404

    c.put("/api/notifications/preferences", json={"lessons": True, "spending": True, "monthly_budget_cents": 10000})
    budget = [n for n in c.get("/api/notifications").json()["items"] if n["title"] == "Atenção ao orçamento do mês"]
    assert len(budget) == 1 and "150%" in budget[0]["body"]
    assert c.put("/api/notifications/preferences", json={"lessons": True, "spending": True, "monthly_budget_cents": -1}).status_code == 422

    c.put("/api/settings", json={"goal_alerts": False})
    p = make_client()
    p.put("/api/settings", json={"goal_alerts": False})
    p.post("/api/goals", json={"title": "Sem aviso", "target": "10", "deadline": iso(TODAY)})
    assert p.get("/api/notifications").json()["total"] == 0  # preferência respeitada


def test_assignment_overdue_reminder(make_client):
    prof, aluno = make_client("professor"), make_client()
    k = prof.post("/api/classes", json={"name": "Turma B"}).json()
    aluno.post("/api/classes/join", json={"code": k["code"]})
    aid = prof.post(f"/api/classes/{k['id']}/assignments", json={"content_key": "controle:organizacao", "due_date": iso(TODAY)}).json()["id"]
    with sqlite3.connect(fintrack.DB_PATH) as db:
        db.execute("UPDATE assignments SET due_date=? WHERE id=?", (iso(TODAY - timedelta(days=2)), aid))
    items = aluno.get("/api/notifications").json()["items"]
    assert any(n["title"] == "Atividade atrasada" for n in items)
    assert aluno.get("/api/assignments").json()["items"][0]["state"] == "atrasada"


# 14. Preferências após sair e entrar -------------------------------------------
def test_preferences_persist_after_relogin(server_app, make_client):
    c = make_client()
    c.put("/api/settings", json={"theme": "light", "chart_type": "pie", "tips": False, "goal_alerts": False})
    c.put("/api/notifications/preferences", json={"lessons": False, "spending": True, "monthly_budget_cents": 50000})
    assert c.put("/api/settings", json={"weekly_email": True}).status_code == 422  # sem SMTP
    c.put("/api/profile", json={"name": "Nome Novo"})
    c.post("/api/auth/logout")
    n = TestClient(server_app)
    n.post("/api/auth/login", json={"email": c.email, "password": "Senha123segura"})
    me = n.get("/api/auth/me").json()
    assert me["name"] == "Nome Novo"
    assert me["settings"]["theme"] == "light" and me["settings"]["chart_type"] == "pie"
    assert me["settings"]["tips"] == 0 and me["settings"]["goal_alerts"] == 0 and me["settings"]["weekly_email"] == 0
    assert n.get("/api/notifications/preferences").json() == {"lessons": 0, "spending": 1, "monthly_budget_cents": 50000}
    assert n.put("/api/settings", json={"chart_type": "radar"}).json()["settings"]["chart_type"] == "pie"


def test_weekly_summary_only_when_configured(make_client, monkeypatch):
    c = make_client()
    tx(c, amount="80", day=TODAY - timedelta(days=2))
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.invalid")
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8010")
    assert c.put("/api/settings", json={"weekly_email": True}).status_code == 200
    monday = TODAY - timedelta(days=TODAY.weekday())
    monkeypatch.setattr(svc, "local_today", lambda: monday)
    outbox = []
    sent = svc.send_weekly_summaries(fintrack.conn, lambda to, subject, body: outbox.append((to, subject, body)))
    assert sent >= 1 and any(to == c.email for to, _, _ in outbox)
    assert svc.send_weekly_summaries(fintrack.conn, lambda *a: outbox.append(a)) == 0  # não reenvia na mesma semana
    monkeypatch.setattr(svc, "local_today", lambda: monday + timedelta(days=1))
    assert svc.send_weekly_summaries(fintrack.conn, lambda *a: outbox.append(a)) == 0  # só às segundas


# Uploads e segurança -------------------------------------------------------------
def test_uploads_are_validated_and_private(make_client):
    import io
    from PIL import Image
    a, b = make_client(), make_client()
    fake = a.post("/api/avatar/photo", files={"image": ("foto.png", b"GIF89a nao e png", "image/png")})
    assert fake.status_code == 422
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "green").save(buf, "PNG")
    assert a.post("/api/avatar/photo", files={"image": ("foto.png", buf.getvalue(), "image/png")}).status_code == 200
    assert a.get(f"/api/avatar/{a.uid}/photo").headers["content-type"] == "image/png"
    assert b.get(f"/api/avatar/{a.uid}/photo").status_code == 403
    rid = a.post("/api/receipts/upload", files={"image": ("r.png", buf.getvalue(), "image/png")}).json()["id"]
    assert b.get(f"/api/receipts/{rid}/file").status_code == 404
    assert a.post(f"/api/receipts/{rid}/analyze").status_code == 503  # sem serviço externo configurado
    big = a.post("/api/receipts/upload", files={"image": ("g.png", b"0" * (5 * 1024 * 1024 + 10), "image/png")})
    assert big.status_code == 422


def test_cross_site_mutation_blocked_and_headers(make_client):
    c = make_client()
    r = c.post("/api/transactions", json={}, headers={"Origin": "https://malicioso.example"})
    assert r.status_code == 403
    h = c.get("/api/dashboard").headers
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"] and h["cache-control"] == "no-store"
