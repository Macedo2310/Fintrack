"""Cadastro sem etapa de código e login com Google (troca de código simulada; nada sai para a internet)."""
import re
import sqlite3
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

import app as fintrack

PASSWORD = "Senha123segura"


@pytest.fixture
def mailbox(monkeypatch):
    """Liga a verificação (como se o SMTP estivesse configurado) e captura as mensagens."""
    box = []
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.invalid")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    monkeypatch.setattr(fintrack, "send_email", lambda to, subject, body: box.append((to, subject, body)))
    return box


def verify_by_reset(c, email, box):
    """Confirma o e-mail pelo único caminho existente com senha: redefinição pelo link enviado."""
    fintrack.reset_rate_limits()
    c.post("/api/auth/forgot", json={"email": email})
    token = re.search(r"token=([\w-]+)", box[-1][2]).group(1)
    assert c.post("/api/auth/reset", json={"token": token, "password": PASSWORD}).status_code == 200


def register(c, email, role="aluno"):
    fintrack.reset_rate_limits()
    return c.post("/api/auth/register", json={"name": "Verifica", "email": email, "password": PASSWORD, "role": role, "terms": True})












def test_signup_goes_straight_to_avatar_even_with_email_configured(server_app, mailbox):
    c = TestClient(server_app)
    r = register(c, "direto@example.com")
    assert r.status_code == 200 and r.json()["next"] == "/avatar.html"
    assert mailbox == []  # nenhum código é enviado
    assert c.post("/api/avatar/skip").status_code == 200 and c.get("/api/dashboard").status_code == 200
    assert c.post("/api/auth/verify-email", json={"code": "123456"}).status_code in (404, 405)  # rota removida
    assert c.get("/verificar.html", follow_redirects=False).status_code == 404
    fintrack.reset_rate_limits()
    login = TestClient(server_app).post("/api/auth/login", json={"email": "direto@example.com", "password": PASSWORD})
    assert login.json()["next"] == "/app.html"


def test_reset_password_marks_email_verified(server_app, mailbox):
    c = TestClient(server_app)
    register(c, "verifica5@example.com")
    fintrack.reset_rate_limits()
    assert c.post("/api/auth/forgot", json={"email": "verifica5@example.com"}).status_code == 200
    token = re.search(r"token=([\w-]+)", mailbox[-1][2]).group(1)
    assert c.post("/api/auth/reset", json={"token": token, "password": "NovaSenha123"}).status_code == 200
    n = TestClient(server_app)
    n.post("/api/auth/login", json={"email": "verifica5@example.com", "password": "NovaSenha123"})
    assert n.get("/api/auth/me").json()["email_verified"] is True


# ===== Google =====
@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cliente-teste.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "segredo-de-teste")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    claims = {}

    def fake_exchange(code, verifier):
        assert code == "codigo-do-google" and len(verifier) >= 43
        return dict(claims)
    monkeypatch.setattr(fintrack, "google_exchange", fake_exchange)
    return claims


def google_login(c, claims, override_state=None):
    start = c.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    url = urllib.parse.urlparse(start.headers["location"])
    q = urllib.parse.parse_qs(url.query)
    assert url.netloc == "accounts.google.com" and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://testserver/api/auth/google/callback"] and q["scope"] == ["openid email profile"]
    claims.setdefault("nonce", q["nonce"][0])
    state = override_state or q["state"][0]
    return c.get("/api/auth/google/callback", params={"code": "codigo-do-google", "state": state}, follow_redirects=False)


def base_claims(sub, email, **extra):
    return {"iss": "https://accounts.google.com", "aud": "cliente-teste.apps.googleusercontent.com", "exp": time.time() + 300,
            "sub": sub, "email": email, "email_verified": True, "name": "Ana Google", **extra}


def test_google_unconfigured_is_honest(server_app):
    c = TestClient(server_app)
    r = c.get("/api/auth/google/start", follow_redirects=False)
    assert r.headers["location"] == "/login.html?google_error=indisponivel"
    assert c.get("/api/health").json()["google_ready"] is False


def test_google_new_account_requires_role_and_terms(server_app, google):
    c = TestClient(server_app)
    google.update(base_claims("g-100", "Ana.Google@example.com"))
    r = google_login(c, google)
    assert r.status_code == 303 and r.headers["location"].startswith("/login.html?google=completar&t=")
    token = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["location"]).query)["t"][0]
    assert c.get("/api/auth/me").status_code == 401  # ainda não há conta nem sessão
    info = c.get("/api/auth/google/pending", params={"t": token}).json()
    assert info == {"email": "ana.google@example.com", "name": "Ana Google"}
    fintrack.reset_rate_limits()
    assert c.post("/api/auth/google/complete", json={"token": token, "name": "Ana", "role": "aluno", "terms": False}).status_code == 422
    done = c.post("/api/auth/google/complete", json={"token": token, "name": "Ana Souza", "role": "professor", "terms": True})
    assert done.status_code == 200 and done.json()["next"] == "/avatar.html"
    me = c.get("/api/auth/me").json()
    assert me["role"] == "professor" and me["google_linked"] and me["email_verified"] and not me["has_password"]
    assert c.post("/api/auth/google/complete", json={"token": token, "name": "Ana", "role": "aluno", "terms": True}).status_code == 400  # uso único
    # conta só Google não entra por senha
    fintrack.reset_rate_limits()
    assert TestClient(server_app).post("/api/auth/login", json={"email": "ana.google@example.com", "password": "qualquer1"}).status_code == 401

    # próximo login com Google entra direto
    n = TestClient(server_app)
    google.clear(); google.update(base_claims("g-100", "ana.google@example.com"))
    again = google_login(n, google)
    assert again.headers["location"] == "/avatar.html" and n.get("/api/auth/me").json()["name"] == "Ana Souza"


def test_google_links_existing_account_and_protects_unverified(server_app, google, mailbox):
    # conta com e-mail confirmado (pela redefinição de senha): Google é vinculado e a senha continua valendo
    owner = TestClient(server_app)
    register(owner, "dono@example.com")
    verify_by_reset(owner, "dono@example.com", mailbox)
    fintrack.reset_rate_limits()
    owner.post("/api/auth/login", json={"email": "dono@example.com", "password": PASSWORD})
    owner.post("/api/avatar/skip")
    g = TestClient(server_app)
    google.update(base_claims("g-200", "dono@example.com"))
    assert google_login(g, google).headers["location"] == "/app.html"
    assert g.get("/api/auth/me").json()["has_password"] is True
    assert owner.get("/api/auth/me").status_code == 200

    # alguém cadastrou o e-mail de outra pessoa e nunca confirmou: o dono real assume pelo Google
    intruso = TestClient(server_app)
    register(intruso, "vitima@example.com")
    dono_real = TestClient(server_app)
    google.clear(); google.update(base_claims("g-300", "vitima@example.com"))
    google_login(dono_real, google)
    assert intruso.get("/api/auth/me").status_code == 401  # sessão do intruso encerrada
    fintrack.reset_rate_limits()
    assert TestClient(server_app).post("/api/auth/login", json={"email": "vitima@example.com", "password": PASSWORD}).status_code == 401
    me = dono_real.get("/api/auth/me").json()
    assert me["email_verified"] and me["google_linked"] and not me["has_password"]


def test_google_rejects_bad_state_claims_and_unverified_email(server_app, google):
    c = TestClient(server_app)
    google.update(base_claims("g-400", "x@example.com"))
    assert google_login(c, google, override_state="estado-forjado").headers["location"].endswith("google_error=estado")
    # callback sem o cookie do navegador que iniciou o login
    other = TestClient(server_app)
    start = c.get("/api/auth/google/start", follow_redirects=False)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start.headers["location"]).query)["state"][0]
    assert other.get("/api/auth/google/callback", params={"code": "codigo-do-google", "state": state}, follow_redirects=False).headers["location"].endswith("estado")

    for bad in ({"aud": "outro-app"}, {"iss": "https://falso.example"}, {"exp": time.time() - 10}, {"nonce": "nonce-errado"}):
        google.clear(); google.update(base_claims("g-401", "y@example.com", **bad))
        assert google_login(TestClient(server_app), google).headers["location"].endswith("google_error=falha"), bad
    google.clear(); google.update(base_claims("g-402", "z@example.com", email_verified=False))
    assert google_login(TestClient(server_app), google).headers["location"].endswith("nao_verificado")
    cancel = TestClient(server_app).get("/api/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert cancel.headers["location"].endswith("google_error=cancelado")
    # state é de uso único
    c2 = TestClient(server_app)
    google.clear(); google.update(base_claims("g-403", "w@example.com"))
    start = c2.get("/api/auth/google/start", follow_redirects=False)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(start.headers["location"]).query)
    google["nonce"] = q["nonce"][0]
    c2.get("/api/auth/google/callback", params={"code": "codigo-do-google", "state": q["state"][0]}, follow_redirects=False)
    c2.cookies.set(fintrack.OAUTH_COOKIE, q["state"][0], path="/api/auth/google")
    replay = c2.get("/api/auth/google/callback", params={"code": "codigo-do-google", "state": q["state"][0]}, follow_redirects=False)
    assert replay.headers["location"].endswith("estado")
