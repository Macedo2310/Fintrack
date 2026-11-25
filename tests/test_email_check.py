"""Verificação de e-mail no cadastro (sem rede: o DNS é simulado)."""
import pytest
from fastapi.testclient import TestClient

import email_check as ec


@pytest.mark.parametrize("raw,ok,frag", [
    ("enzomacedo8gmail.com", False, "Falta o @"),
    ("enzo @gmail.com", False, "formato válido"),
    ("enzo@gmial.com", False, "enzo@gmail.com"),
    ("enzo@gmail.con", False, "enzo@gmail.com"),
    ("enzo@hotmial.com", False, "enzo@hotmail.com"),
    ("enzo@outlok.com", False, "enzo@outlook.com"),
    ("enzo@mailinator.com", False, "descartáveis"),
    ("enzomacedo8@gmail.com", True, ""),
    ("Enzo@Yahoo.com.br", True, ""),
    ("ana@ymail.com", True, ""),          # provedor real parecido com gmail: não é erro de digitação
    ("aluno@escola.sp.gov.br", True, ""),
])
def test_format_typos_and_disposable(raw, ok, frag):
    r = ec.check_email(raw, dns=False)
    assert r.ok is ok and frag in (r.message + (r.suggestion or ""))


def test_dns_rejects_domain_without_mail(monkeypatch):
    from email_validator import EmailUndeliverableError

    def fake(email, check_deliverability, timeout=None):
        raise EmailUndeliverableError("x")
    monkeypatch.setattr(ec, "validate_email", lambda e, check_deliverability=False, timeout=None:
                        fake(e, check_deliverability) if check_deliverability else type("V", (), {"normalized": e})())
    ec._CACHE.clear()
    r = ec.check_email("ana@empresa-inexistente-xyz.com.br")
    assert not r.ok and "não existe ou não recebe e-mails" in r.message


def test_dns_failure_does_not_block_signup(monkeypatch):
    def boom(email, check_deliverability=False, timeout=None):
        if check_deliverability:
            raise OSError("sem rede")
        return type("V", (), {"normalized": email})()
    monkeypatch.setattr(ec, "validate_email", boom)
    ec._CACHE.clear()
    assert ec.check_email("ana@dominio-qualquer.com.br").ok


def test_signup_endpoint_blocks_bad_email_before_supabase(monkeypatch):
    import app_supabase as mod
    called = []
    monkeypatch.setattr(mod.sb, "sign_up", lambda *a, **k: called.append(1))
    c = TestClient(mod.app)
    r = c.post("/api/auth/register", json={"name": "Enzo", "email": "enzo@gmial.com", "password": "Senha123ok", "role": "aluno", "terms": True, "adult": True})
    assert r.status_code == 422 and "enzo@gmail.com" in r.json()["detail"] and not called
    j = c.post("/api/auth/check-email", json={"email": "enzo@gmial.com"}).json()
    assert j["ok"] is False and j["suggestion"] == "enzo@gmail.com"


def test_signup_requires_adult(monkeypatch):
    import app_supabase as a
    from fastapi.testclient import TestClient
    r = TestClient(a.app).post("/api/auth/register", json={"name": "Enzo", "email": "enzo@gmail.com", "password": "Senha123ok", "role": "aluno", "terms": True})
    assert r.status_code == 422 and "18 anos" in r.json()["detail"]
