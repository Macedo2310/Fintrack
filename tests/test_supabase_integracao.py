"""Integração do backend app_supabase.py com o Supabase REAL (Auth, Data API com RLS, Storage).

Só roda quando habilitado, porque cria 3 contas temporárias (ft-teste-…@example.com) e as apaga no final,
junto com os arquivos enviados ao Storage — inclusive se algum passo falhar:

  $env:FINTRACK_SUPABASE_TEST='1'
  # SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY e SUPABASE_SECRET_KEY vêm do .env
  .venv\\Scripts\\python.exe -m pytest tests\\test_supabase_integracao.py -v
"""
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
ENABLED = os.getenv("FINTRACK_SUPABASE_TEST") == "1" and all(
    os.getenv(k) for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY"))
pytestmark = pytest.mark.skipif(not ENABLED, reason="defina FINTRACK_SUPABASE_TEST=1 e as chaves do Supabase no .env")

PASSWORD = "Teste" + uuid.uuid4().hex[:10] + "9"


def png(size=64, color=(16, 185, 129)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def env():
    os.environ.setdefault("FINTRACK_DISABLE_WORKER", "1")
    os.environ["COOKIE_SECURE"] = "0"
    import app_supabase
    from fastapi.testclient import TestClient
    sb = app_supabase.sb
    run = uuid.uuid4().hex[:8]
    users = {}
    try:
        for who in ("aluno1", "aluno2", "prof"):
            u = sb.admin_create_user({"email": f"ft-teste-{who}-{run}@example.com", "password": PASSWORD, "email_confirm": True,
                                      "user_metadata": {"name": f"Teste {who}"}})
            users[who] = {"id": u["id"], "email": u["email"], "client": TestClient(app_supabase.app)}
        yield {"sb": sb, "users": users, "mod": app_supabase}
    finally:
        for u in users.values():
            uid = u["id"]
            for bucket, table, col in (("avatars", "user_avatars", "photo_path"), ("receipts", "receipts", "storage_path")):
                try:
                    paths = [r[col] for r in sb.select(table, service=True, user_id=f"eq.{uid}", select=col) if r.get(col)]
                    sb.remove(bucket, paths)
                except Exception:
                    pass
            try:
                sb.admin_delete_user(uid)
            except Exception:
                pass


def ok(r, status=200):
    assert r.status_code == status, (r.status_code, r.text)
    return r.json()


def test_fluxo_completo(env):
    sb, U, mod = env["sb"], env["users"], env["mod"]
    a1, a2, p = U["aluno1"]["client"], U["aluno2"]["client"], U["prof"]["client"]
    from backend_services import local_today
    today = local_today()

    # ---------- login e onboarding ----------
    for who, role in (("aluno1", "aluno"), ("aluno2", "aluno"), ("prof", "professor")):
        c = U[who]["client"]
        j = ok(c.post("/api/auth/login", json={"email": U[who]["email"], "password": PASSWORD}))
        assert j["next"] == mod.ONBOARDING_URL
        assert c.get("/app.html", follow_redirects=False).status_code == 303   # sem papel: vai para "Quase lá"
        assert ok(c.get("/api/auth/google/pending?t=sessao"))["email"] == U[who]["email"]
        assert ok(c.post("/api/auth/google/complete", json={"token": "sessao", "name": f"Teste {who}", "role": role, "terms": True}))["next"] == "/avatar.html"
    assert ok(a1.put("/api/avatar/preset", json={"preset": "gato", "bg": "#7C5CFF"}))["avatar"]["preset"] == "gato"
    ok(a2.post("/api/avatar/skip")); ok(p.post("/api/avatar/skip"))
    me = ok(a1.get("/api/auth/me"))
    assert me["role"] == "aluno" and me["avatar"]["kind"] == "preset" and me["email_verified"] and me["has_password"]
    assert a1.get("/app.html").status_code == 200
    assert a1.post("/api/auth/google/complete", json={"name": "Outro", "role": "professor", "terms": True}).status_code == 409

    # ---------- categorias e transações ----------
    cats = ok(a1.get("/api/categories"))
    assert "Mesada" in cats["receita"] and "Alimentação" in cats["despesa"]
    assert ok(a1.post("/api/categories", json={"type": "despesa", "name": "Cursos online"}))["name"] == "Cursos online"
    assert a1.post("/api/categories", json={"type": "despesa", "name": "cursos ONLINE"}).status_code == 409
    ok(a1.post("/api/transactions", json={"type": "receita", "category": "Mesada", "description": "Mesada", "amount": "1.000,00", "date": today.isoformat()}))
    ok(a1.post("/api/transactions", json={"type": "despesa", "category": "Cursos online", "description": "Curso", "amount": "50", "date": today.isoformat()}))
    assert a1.post("/api/transactions", json={"type": "receita", "category": "Alimentação", "description": "x", "amount": "1", "date": today.isoformat()}).status_code == 422
    assert a1.post("/api/transactions", json={"type": "despesa", "category": "Lazer", "description": "x", "amount": "0", "date": today.isoformat()}).status_code == 422
    start = (today - timedelta(days=14)).isoformat()
    ok(a1.post("/api/transactions", json={"type": "despesa", "category": "Alimentação", "description": "Lanche", "amount": "10,00", "date": start,
                                          "recurrence": {"enabled": True, "frequency": "semanal", "start_date": start}}))
    lst = ok(a1.get("/api/transactions?page_size=50"))
    assert lst["total"] == 5 and lst["summary"]["receitas"] == 100000 and lst["summary"]["despesas"] == 5000 + 3000
    assert ok(a1.get("/api/transactions?q=lanche"))["total"] == 3        # busca sem diferenciar maiúsculas
    assert ok(a1.get("/api/transactions?q=100%25"))["total"] == 0
    rec = [x for x in lst["items"] if x["description"] == "Lanche"]
    assert all(x["recurrence_active"] and x["recurrence_frequency"] == "semanal" for x in rec)
    mid = next(x for x in rec if x["date"] == (today - timedelta(days=7)).isoformat())
    ok(a1.put(f"/api/transactions/{mid['id']}?scope=future", json={"type": "despesa", "category": "Alimentação", "description": "Lanche novo",
                                                                  "amount": "12,00", "date": mid["date"]}))
    assert ok(a1.delete(f"/api/transactions/{mid['id']}?scope=future"))["deleted"] == 2
    d = ok(a1.get("/api/dashboard"))
    assert d["balance_total"] == 100000 - 5000 - 1000 and len(d["months"]) == 6 and all("date" in r for r in d["recent"])

    # ---------- metas ----------
    g = ok(a1.post("/api/goals", json={"title": "Fone", "target": "300,00", "deadline": (today + timedelta(days=30)).isoformat()}))["id"]
    ok(a1.post(f"/api/goals/{g}/reserve", json={"amount": "200"}))
    assert a1.post(f"/api/goals/{g}/reserve", json={"amount": "999999"}).status_code == 422
    goals = ok(a1.get("/api/goals"))
    assert goals["reserved"] == 20000 and goals["available"] == goals["balance_total"] - 20000 and goals["items"][0]["percent"] == 66
    assert "nenhuma despesa" in ok(a1.post(f"/api/goals/{g}/complete"))["message"]
    assert a1.put(f"/api/goals/{g}", json={"title": "x", "target": "1", "deadline": today.isoformat()}).status_code == 422
    ok(a1.delete(f"/api/goals/{g}"))
    assert ok(a1.get("/api/goals"))["reserved"] == 0

    # ---------- educação e vídeo ----------
    edu = ok(a1.get("/api/education"))
    assert edu["pass"] == 70 and len(edu["modules"]) == 4 and edu["modules"][0]["topics"][0]["acts"] == []
    assert a1.post("/api/education/poupanca/o-que-e/submit", json={"answers": [1, [0, 1, 1, 0, 1, 0], [0, 2, 4]]}).status_code == 403
    s = ok(a1.post("/api/intro/poupanca/start"))
    assert s["duration"] == 36.5 and len(s["token"]) >= 20
    assert ok(a1.post("/api/intro/poupanca/tick", json={"token": s["token"], "position": 30}))["accepted"] is False
    assert a1.get("/api/intro/poupanca/media", follow_redirects=False).status_code in (200, 307)
    video = sb.select("education_video_assets", service=True, storage_path="eq.intro/poupanca-v1.mp4", select="id")[0]["id"]
    sb.update("education_video_progress", {"completed": True, "completed_at": datetime.now(timezone.utc).isoformat(), "watched_seconds": 36.5}, service=True,
              user_id=f"eq.{U['aluno1']['id']}", video_id=f"eq.{video}")   # simula ter assistido (o tempo real é testado no SQL)
    edu = ok(a1.get("/api/education"))
    t0 = edu["modules"][0]["topics"][0]
    assert t0["acts"] and t0["reviewed"] == "2026-11" and t0["goal"]
    ok(a1.put("/api/education/poupanca/o-que-e", json={"status": "em_andamento"}))
    assert ok(a1.post("/api/education/poupanca/vantagens/check", json={"i": 1, "answer": "4.500"}))["ok"] is True
    r = ok(a1.post("/api/education/poupanca/o-que-e/submit", json={"answers": [1, [0, 1, 1, 0, 1, 0], [0, 2, 4]]}))
    assert r["score"] == 100 and r["completed"] and r["attempts"] == 1
    prog = {(x["module_key"], x["topic_key"]): x for x in ok(a1.get("/api/education"))["progress"]}
    assert prog[("poupanca", "o-que-e")]["status"] == "concluida" and prog[("poupanca", "o-que-e")]["score"] == 100

    # ---------- FinBot ----------
    cid = ok(a1.post("/api/ai/conversations"))["id"]
    r = a1.post(f"/api/ai/conversations/{cid}/messages", json={"content": "Oi", "request_key": "req-" + uuid.uuid4().hex})
    assert r.status_code in (200, 503, 502)
    assert len(ok(a1.get(f"/api/ai/conversations/{cid}"))["messages"]) >= 1
    assert a2.get(f"/api/ai/conversations/{cid}").status_code == 404
    ok(a1.patch(f"/api/ai/conversations/{cid}", json={"title": "Renomeada"}))

    # ---------- comprovantes ----------
    img = png()
    up = ok(a1.post("/api/receipts/upload", files={"image": ("nota.png", img, "image/png")}))
    assert up["duplicate"] is False
    assert a1.get(f"/api/receipts/{up['id']}/file").content == img
    assert ok(a1.post("/api/receipts/upload", files={"image": ("nota.png", img, "image/png")}))["duplicate"] is True
    assert a1.post("/api/receipts/upload", files={"image": ("falso.png", b"nao e imagem", "image/png")}).status_code == 422
    assert a2.get(f"/api/receipts/{up['id']}/file").status_code == 404

    # ---------- turmas ----------
    assert a1.post("/api/classes", json={"name": "Turma falsa"}).status_code == 403
    cls = ok(p.post("/api/classes", json={"name": "Turma Teste", "description": "Integração"}))
    assert ok(a1.post("/api/classes/preview", json={"code": cls["code"].lower()}))["class"]["name"] == "Turma Teste"
    ok(a1.post("/api/classes/join", json={"code": cls["code"]}))
    assert a1.post("/api/classes/join", json={"code": cls["code"]}).status_code == 409
    assert ok(a1.get("/api/classes"))["items"][0]["teacher_name"] == "Teste prof"
    lessons = ok(p.get("/api/lessons"))["items"]
    assert len(lessons) == 12 and lessons[0]["key"] == "poupanca:o-que-e"
    ok(p.post(f"/api/classes/{cls['id']}/assignments", json={"content_key": "poupanca:o-que-e", "due_date": (today + timedelta(days=2)).isoformat()}))
    assert p.post(f"/api/classes/{cls['id']}/assignments", json={"content_key": "nada:nada"}).status_code == 422
    assert ok(a1.get("/api/assignments"))["items"][0]["state"] == "concluida"
    ok(a2.post("/api/classes/join", json={"code": cls["code"]}))
    assert ok(a2.get("/api/assignments"))["items"][0]["state"] == "pendente"
    pa = ok(p.get("/api/assignments"))["items"][0]
    assert pa["total"] == 2 and pa["done"] == 1
    res = ok(p.get(f"/api/classes/{cls['id']}/assignment-results"))["items"]
    assert {x["student_name"] for x in res} == {"Teste aluno1", "Teste aluno2"}
    parts = ok(p.get(f"/api/classes/{cls['id']}/participants"))["items"]
    assert len(parts) == 2 and all(x["email"].endswith("@example.com") for x in parts)
    assert ok(p.get(f"/api/classes/{cls['id']}/financial-summary"))["items"] == []
    ok(a1.put(f"/api/classes/{cls['id']}/share", json={"enabled": True}))
    summ = ok(p.get(f"/api/classes/{cls['id']}/financial-summary"))["items"]
    assert len(summ) == 1 and summ[0]["receitas"] == 100000 and "description" not in summ[0]
    ok(a1.put(f"/api/classes/{cls['id']}/share", json={"enabled": False}))
    assert ok(p.get(f"/api/classes/{cls['id']}/financial-summary"))["items"] == []
    assert ok(p.get("/api/transactions"))["total"] == 0 and ok(a2.get("/api/transactions"))["total"] == 0
    assert a2.get(f"/api/classes/{cls['id']}/participants").status_code == 403

    # ---------- foto de avatar (Storage + RLS de turma) ----------
    ok(a1.post("/api/avatar/photo", files={"image": ("eu.png", png(80, (255, 92, 138)), "image/png")}))
    assert p.get(f"/api/avatar/{U['aluno1']['id']}/photo").status_code == 200      # professor da turma
    assert a2.get(f"/api/avatar/{U['aluno1']['id']}/photo").status_code == 404     # colega não
    ok(a1.put("/api/avatar/preset", json={"preset": "urso", "bg": "#1DB954"}))     # volta ao padrão e apaga a foto

    # ---------- lembretes, preferências e sessão ----------
    ok(a2.post("/api/transactions", json={"type": "despesa", "category": "Lazer", "description": "Cinema", "amount": "30", "date": today.isoformat()}))
    n = ok(a2.get("/api/notifications"))
    assert any(x["event_key"].startswith("spending:") for x in n["items"])
    ok(a2.post("/api/notifications/read-all"))
    assert ok(a2.get("/api/notifications"))["unread"] == 0
    ok(a2.put("/api/notifications/preferences", json={"lessons": True, "spending": False, "monthly_budget_cents": 50000}))
    assert ok(a2.get("/api/notifications/preferences"))["monthly_budget_cents"] == 50000
    assert ok(a2.put("/api/settings", json={"theme": "light"}))["settings"]["theme"] == "light"
    assert a2.put("/api/settings", json={"weekly_email": True}).status_code == 422 or os.getenv("SMTP_HOST")
    a2.cookies.delete(mod.AT_COOKIE)                                    # access token "expirado": renova pelo refresh token
    assert ok(a2.get("/api/auth/me"))["role"] == "aluno" and a2.cookies.get(mod.AT_COOKIE)
    ok(a2.post("/api/auth/logout"))
    assert a2.get("/api/auth/me").status_code == 401
