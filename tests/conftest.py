"""Ambiente isolado: banco e uploads temporários, sem worker em segundo plano e sem chaves externas."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = Path(tempfile.mkdtemp(prefix="fintrack-test-"))
os.environ["FINTRACK_DATA_DIR"] = str(DATA_DIR)
os.environ["FINTRACK_DISABLE_WORKER"] = "1"
for key in ("OPENAI_API_KEY", "AI_PROVIDER_URL", "AI_API_KEY", "AI_MODEL", "SMTP_HOST", "RECEIPT_ANALYZER_URL", "PROFESSOR_SIGNUP_CODE"):
    os.environ[key] = ""
sys.path.insert(0, str(BASE))

import app as fintrack  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    fintrack.reset_rate_limits()
    yield


@pytest.fixture(scope="session")
def server_app():
    with TestClient(fintrack.app) as c:  # executa o startup (migrações) uma vez
        yield fintrack.app


_counter = [0]


def new_client(server_app, role="aluno", name="Conta Teste"):
    _counter[0] += 1
    fintrack.reset_rate_limits()  # o limite de cadastro por IP é testado à parte
    c = TestClient(server_app)
    email = f"user{_counter[0]}-{os.getpid()}@example.com"
    r = c.post("/api/auth/register", json={"name": name, "email": email, "password": "Senha123segura", "role": role, "terms": True})
    assert r.status_code == 200, r.text
    c.post("/api/avatar/skip")
    c.email = email
    c.uid = c.get("/api/auth/me").json()["id"]
    return c


@pytest.fixture
def make_client(server_app):
    return lambda role="aluno", name="Conta Teste": new_client(server_app, role, name)
