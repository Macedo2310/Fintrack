"""Backup consistente, verificação e restauração em diretórios isolados (subprocessos com outro FINTRACK_DATA_DIR)."""
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def run(args, data_dir, check=True):
    env = {**os.environ, "FINTRACK_DATA_DIR": str(data_dir), "FINTRACK_DISABLE_WORKER": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, *args], cwd=BASE, env=env, capture_output=True, text=True, encoding="utf-8", check=check)


SEED = textwrap.dedent("""
    import io
    from fastapi.testclient import TestClient
    from PIL import Image
    import app
    with TestClient(app.app) as c:
        c.post('/api/auth/register', json={'name':'Backup','email':'backup@example.com','password':'Senha123segura','role':'aluno','terms':True})
        c.post('/api/transactions', json={'type':'receita','category':'Mesada','description':'Antes do backup','amount':'321,00','date':'2026-01-10'})
        buf = io.BytesIO(); Image.new('RGB', (20, 20), 'blue').save(buf, 'PNG')
        c.post('/api/receipts/upload', files={'image': ('r.png', buf.getvalue(), 'image/png')})
""")


def test_backup_verify_and_restore(tmp_path):
    original, restored = tmp_path / "original", tmp_path / "restaurado"
    run(["-c", SEED], original)
    assert "Integridade: ['ok']" in run(["manage_db.py", "check"], original).stdout

    backup = tmp_path / "backup-1"
    out = run(["manage_db.py", "backup", str(backup)], original).stdout
    assert "1 arquivo(s)" in out and (backup / "manifest.json").exists()
    assert run(["manage_db.py", "backup", str(backup)], original, check=False).returncode != 0  # não sobrescreve
    assert "Backup íntegro" in run(["manage_db.py", "verify", str(backup)], original).stdout

    # adulteração é detectada e impede a restauração
    tampered = tmp_path / "backup-adulterado"
    run(["manage_db.py", "backup", str(tampered)], original)
    with open(tampered / "fintrack.db", "ab") as f:
        f.write(b"x")
    assert run(["manage_db.py", "verify", str(tampered)], original, check=False).returncode == 1
    assert run(["manage_db.py", "restore", str(tampered)], restored, check=False).returncode != 0

    # restauração em outro diretório (servidor parado)
    run(["-c", "import app; app.init_db()"], restored)
    out = run(["manage_db.py", "restore", str(backup)], restored).stdout
    assert "Restaurado" in out
    db = sqlite3.connect(restored / "fintrack.db")
    assert db.execute("SELECT description, amount_cents FROM transactions").fetchall() == [("Antes do backup", 32100)]
    path = db.execute("SELECT private_path FROM receipts").fetchone()[0]
    db.close()
    assert Path(path).is_file() and str(restored) in path  # caminho do comprovante ajustado ao novo diretório
    assert "Integridade: ['ok']" in run(["manage_db.py", "check"], restored).stdout
    assert any(p.name.startswith("antes-da-restauracao-") for p in (restored / "backups").iterdir())
