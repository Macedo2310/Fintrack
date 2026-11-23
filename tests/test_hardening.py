"""Correções da 0.6.1: IP do cliente, páginas internas, limites persistidos, lifespan, vídeos e tipo de atividade."""
import struct
import time
import warnings

import pytest
from fastapi.testclient import TestClient

import app as fintrack
import video_lessons
from conftest import new_client


def test_forged_forwarded_for_does_not_bypass_login_limit(server_app):
    """Trocar X-Forwarded-For a cada tentativa não cria um novo balde de limite."""
    fintrack.reset_rate_limits()
    c = TestClient(server_app)
    codes = [c.post("/api/auth/login", headers={"X-Forwarded-For": f"10.0.0.{i}"},
                    json={"email": "alvo@example.com", "password": "errada123"}).status_code for i in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_rate_limit_survives_restart(server_app):
    """O contador fica no banco: um novo ciclo de vida do app (reinício) continua barrando."""
    fintrack.reset_rate_limits()
    for _ in range(10):
        TestClient(server_app).post("/api/auth/login", json={"email": "reinicio@example.com", "password": "errada123"})
    with TestClient(server_app) as restarted:  # executa shutdown/startup de novo
        r = restarted.post("/api/auth/login", json={"email": "reinicio@example.com", "password": "errada123"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_old_rate_limit_entries_are_purged(server_app):
    fintrack.reset_rate_limits()
    with fintrack.conn() as c:
        c.execute("INSERT INTO rate_limits VALUES(?,?)", ("antigo", time.time() - fintrack.RATE_LIMIT_RETENTION - 10))
        c.execute("INSERT INTO rate_limits VALUES(?,?)", ("recente", time.time()))
    fintrack.purge_rate_limits()
    with fintrack.conn() as c:
        keys = {r["key"] for r in c.execute("SELECT key FROM rate_limits")}
    assert keys == {"recente"}


@pytest.mark.parametrize("path", ["/static/app.html", "/static/APP.HTML", "/static/./avatar.html",
                                  "/static/x/../app.html", "/App.html", "/AVATAR.HTML"])
def test_internal_pages_need_session_even_via_static(server_app, path):
    anon = TestClient(server_app)
    r = anon.get(path)
    assert r.status_code == 401
    assert 'data-page="dashboard"' not in r.text


def test_internal_page_via_static_still_works_with_session(make_client):
    c = make_client()
    r = c.get("/static/app.html")
    assert r.status_code == 200 and 'data-page="dashboard"' in r.text
    assert c.get("/static/app.css").status_code == 200  # demais arquivos continuam públicos


def test_app_uses_lifespan_without_deprecation_warning():
    assert fintrack.app.router.lifespan_context is not None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with TestClient(fintrack.app):
            pass
    assert not [w for w in caught if "on_event" in str(w.message)]


def test_assignment_content_type_is_validated_and_stored(make_client):
    teacher = make_client("professor", "Prof. Tipo")
    cid = teacher.post("/api/classes", json={"name": "Turma tipo"}).json()["id"]
    key = teacher.get("/api/lessons").json()["items"][0]["key"]
    bad = teacher.post(f"/api/classes/{cid}/assignments", json={"content_key": key, "content_type": "video"})
    assert bad.status_code == 422
    ok = teacher.post(f"/api/classes/{cid}/assignments", json={"content_key": key, "content_type": "aula"})
    assert ok.status_code == 200
    with fintrack.conn() as c:
        assert c.execute("SELECT content_type FROM assignments WHERE id=?", (ok.json()["id"],)).fetchone()[0] == "aula"


def _old_duration(path):
    """Implementação anterior (lia o arquivo inteiro), mantida aqui só para comparar o resultado."""
    data = path.read_bytes()
    def boxes(start, end):
        while start + 8 <= end:
            size, kind = struct.unpack_from('>I4s', data, start)
            header = 8
            if size == 1:
                size = struct.unpack_from('>Q', data, start + 8)[0]; header = 16
            if size == 0: size = end - start
            payload = start + header
            if kind == b'moov':
                result = boxes(payload, start + size)
                if result: return result
            if kind == b'mvhd':
                offset = payload + (20 if data[payload] == 1 else 12)
                scale = struct.unpack_from('>I', data, offset)[0]
                ticks = struct.unpack_from('>Q' if data[payload] == 1 else '>I', data, offset + 4)[0]
                return ticks / scale
            start += size
    return boxes(0, len(data))


@pytest.mark.parametrize("key", ["poupanca", "controle", "planejamento"])
def test_video_duration_matches_previous_reader(key):
    path = video_lessons.MEDIA / (key + ".mp4")
    assert video_lessons.duration(path) == pytest.approx(_old_duration(path))


def test_video_duration_reads_only_headers(monkeypatch):
    calls = []
    original = video_lessons.Path.read_bytes
    monkeypatch.setattr(video_lessons.Path, "read_bytes", lambda self: calls.append(self) or original(self))
    video_lessons.duration(video_lessons.MEDIA / "controle.mp4")
    assert calls == []


def test_video_duration_rejects_file_without_moov(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(struct.pack(">I4s", 16, b"free") + b"\0" * 8)
    with pytest.raises(ValueError):
        video_lessons.duration(f)
