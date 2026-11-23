"""Testes do backend Supabase que não usam rede: tradução de erros, sessão por cookie e renovação do token."""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

import app_supabase as mod
from supa import AuthSession, SupabaseError, jwt_claims


def fake_jwt(sub="11111111-1111-4111-8111-111111111111", exp_in=3600, email="a@example.com"):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'HS256'})}.{enc({'sub': sub, 'exp': int(time.time()) + exp_in, 'email': email})}.assinatura"


def test_jwt_claims_tolerates_garbage():
    assert jwt_claims("nada") == {}
    assert jwt_claims(fake_jwt(sub="x"))["sub"] == "x"


@pytest.mark.parametrize("code,status,expected", [
    ("FT422", 422, "mensagem nossa"), ("23505", 409, "Esse registro já existe."), ("42501", 403, "Sem permissão."),
    ("invalid_credentials", 400, mod.LOGIN_FAILED), ("PGRST301", 401, "Sessão expirada."),
    ("over_request_rate_limit", 429, "Muitas tentativas. Aguarde um pouco e tente novamente."),
    ("qualquer", 500, "O banco de dados não respondeu. Tente novamente em instantes."),
])
def test_translate(code, status, expected):
    s, msg = mod.translate(SupabaseError(status, "mensagem nossa" if code.startswith("FT") else "detalhe técnico", code))
    assert msg == expected and "técnico" not in msg


def test_requests_without_session_get_401_and_pages_redirect(monkeypatch):
    c = TestClient(mod.app)
    assert c.get("/api/dashboard").status_code == 401
    assert c.get("/app.html").status_code == 401


def test_expired_access_token_is_refreshed_and_cookie_rotated(monkeypatch):
    new_at = fake_jwt()
    calls = {}
    monkeypatch.setattr(mod.sb, "refresh", lambda rt: calls.setdefault("rt", rt) and AuthSession(new_at, "novo-refresh", int(time.time()) + 3600))
    monkeypatch.setattr(mod.sb, "rpc", lambda fn, args=None, token=None, service=False: {"items": [], "unread": 0, "total": 0, "_token": token})
    c = TestClient(mod.app)
    c.cookies.set(mod.AT_COOKIE, fake_jwt(exp_in=-10))
    c.cookies.set(mod.RT_COOKIE, "refresh-antigo")
    r = c.get("/api/notifications")
    assert r.status_code == 200 and r.json()["_token"] == new_at and calls["rt"] == "refresh-antigo"
    set_cookie = r.headers.get_list("set-cookie")
    assert any(h.startswith(f"{mod.AT_COOKIE}={new_at};") for h in set_cookie)
    assert any(h.startswith(f"{mod.RT_COOKIE}=novo-refresh;") for h in set_cookie)
    assert all("httponly" in h.lower() and "samesite=lax" in h.lower() for h in set_cookie)


def test_failed_refresh_clears_cookies(monkeypatch):
    def boom(rt):
        raise SupabaseError(400, "x", "refresh_token_not_found")
    monkeypatch.setattr(mod.sb, "refresh", boom)
    c = TestClient(mod.app)
    c.cookies.set(mod.RT_COOKIE, "velho")
    r = c.get("/api/notifications")
    assert r.status_code == 401
    cleared = r.headers.get_list("set-cookie")
    assert any(h.startswith(f'{mod.RT_COOKIE}=""') and "max-age=0" in h.lower() for h in cleared)
    assert any(h.startswith(f'{mod.AT_COOKIE}=""') for h in cleared)


def test_supabase_errors_reach_client_in_portuguese(monkeypatch):
    def rpc(fn, args=None, token=None, service=False):
        raise SupabaseError(422, "O valor excede seu saldo disponível.", "FT422")
    monkeypatch.setattr(mod.sb, "rpc", rpc)
    c = TestClient(mod.app)
    c.cookies.set(mod.AT_COOKIE, fake_jwt())
    r = c.post("/api/goals/abc/reserve", json={"amount": "10"})
    assert r.status_code == 422 and r.json()["detail"] == "O valor excede seu saldo disponível."


def test_service_key_never_sent_as_bearer_when_new_format():
    from supa import Supabase
    s = Supabase("https://x.supabase.co", "sb_publishable_x", "sb_secret_y")
    assert s._headers(service=True) == {"apikey": "sb_secret_y"}
    assert s._headers("tok") == {"apikey": "sb_publishable_x", "Authorization": "Bearer tok"}
    with pytest.raises(SupabaseError):
        Supabase("https://x.supabase.co", "p")._headers(service=True)


def test_csp_allows_video_from_supabase_only():
    c = TestClient(mod.app)
    csp = c.get("/api/health").headers["content-security-policy"]
    assert "media-src 'self'" in csp and "connect-src 'self'" in csp
