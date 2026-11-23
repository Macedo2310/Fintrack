"""Manutenção local do FinTrack.

  python manage_db.py check                     verifica integridade e vínculos do banco
  python manage_db.py backup PASTA_NOVA         copia o banco (API de backup do SQLite) e os uploads
  python manage_db.py verify PASTA_DO_BACKUP    confere um backup sem tocar no banco em uso
  python manage_db.py restore PASTA_DO_BACKUP   restaura (pare o servidor antes)

O destino do backup precisa ser uma pasta nova. A restauração guarda uma cópia
do estado atual em data/backups/antes-da-restauracao-* antes de substituir.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / '.runtime'))
import os
os.environ.setdefault('FINTRACK_DISABLE_WORKER', '1')
from app import DB_PATH, UPLOADS, conn
from backend_services import backup_database


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def check_db(path):
    c = sqlite3.connect(path)
    try:
        integrity = [r[0] for r in c.execute('PRAGMA integrity_check').fetchall()]
        foreign = c.execute('PRAGMA foreign_key_check').fetchall()
        versions = [r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version')] if c.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone() else []
    finally:
        c.close()
    return integrity == ['ok'] and not foreign, integrity, len(foreign), versions


def backup(dest):
    dest.mkdir(parents=True)
    db_copy = backup_database(DB_PATH, dest / 'fintrack.db')
    archive = dest / 'uploads.zip'
    files = 0
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        if UPLOADS.is_dir():
            for f in sorted(UPLOADS.rglob('*')):
                if f.is_file():
                    z.write(f, f.relative_to(UPLOADS).as_posix())
                    files += 1
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'database_sha256': sha256(db_copy), 'uploads_sha256': sha256(archive), 'uploads_files': files}
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def verify(src):
    manifest = json.loads((src / 'manifest.json').read_text(encoding='utf-8'))
    problems = []
    if sha256(src / 'fintrack.db') != manifest['database_sha256']:
        problems.append('O arquivo do banco foi alterado depois do backup.')
    if sha256(src / 'uploads.zip') != manifest['uploads_sha256']:
        problems.append('O arquivo de uploads foi alterado depois do backup.')
    ok, integrity, foreign, versions = check_db(src / 'fintrack.db')
    if not ok:
        problems.append(f'Banco do backup reprovado: {integrity}, vínculos com erro: {foreign}.')
    with zipfile.ZipFile(src / 'uploads.zip') as z:
        bad = z.testzip()
        if bad:
            problems.append(f'Arquivo corrompido no ZIP de uploads: {bad}')
        for name in z.namelist():
            if name.startswith('/') or '..' in Path(name).parts:
                problems.append(f'Caminho inseguro no ZIP: {name}')
    return problems, manifest, versions


def restore(src):
    problems, manifest, _ = verify(src)
    if problems:
        raise SystemExit('Backup não restaurado:\n- ' + '\n- '.join(problems))
    safety = DB_PATH.parent / 'backups' / ('antes-da-restauracao-' + uuid.uuid4().hex)
    if DB_PATH.exists():
        backup(safety)
    for suffix in ('-wal', '-shm'):
        Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
    shutil.copy2(src / 'fintrack.db', DB_PATH)
    if UPLOADS.exists():
        shutil.rmtree(UPLOADS)
    UPLOADS.mkdir(parents=True)
    with zipfile.ZipFile(src / 'uploads.zip') as z:
        z.extractall(UPLOADS)
    # Caminhos de arquivos privados ficam gravados no banco; ajusta para o diretório atual.
    with conn() as c:
        for table, column in (('receipts', 'private_path'), ('user_avatars', 'photo_path')):
            for row in c.execute(f'SELECT rowid, {column} p FROM {table} WHERE {column} IS NOT NULL').fetchall():
                parts = Path(row['p']).parts
                if 'uploads' in parts:
                    rel = Path(*parts[len(parts) - parts[::-1].index('uploads'):])
                    c.execute(f'UPDATE {table} SET {column}=? WHERE rowid=?', (str(UPLOADS / rel), row['rowid']))
    return safety


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['check', 'backup', 'verify', 'restore'])
    parser.add_argument('path', nargs='?')
    args = parser.parse_args()
    if args.action in ('backup', 'verify', 'restore') and not args.path:
        parser.error('Informe a pasta do backup.')
    if args.action == 'check':
        if not DB_PATH.is_file():
            parser.error('Banco não encontrado. Inicie o aplicativo primeiro.')
        ok, integrity, foreign, versions = check_db(DB_PATH)
        with conn() as c:
            c.execute('PRAGMA optimize')
        print('Banco:', DB_PATH)
        print('Integridade:', integrity)
        print('Violações de vínculos:', foreign)
        print('Migrações aplicadas:', versions)
        sys.exit(0 if ok else 1)
    target = Path(args.path).resolve()
    if args.action == 'backup':
        if not DB_PATH.is_file():
            parser.error('Banco não encontrado. Inicie o aplicativo primeiro.')
        if target.exists():
            parser.error('O destino já existe; escolha uma pasta nova.')
        m = backup(target)
        print(f'Backup criado em {target} ({m["uploads_files"]} arquivo(s) enviados).')
    elif args.action == 'verify':
        problems, m, versions = verify(target)
        print('Criado em:', m['created_at'], '| migrações:', versions, '| uploads:', m['uploads_files'])
        print('Backup íntegro.' if not problems else 'Problemas:\n- ' + '\n- '.join(problems))
        sys.exit(1 if problems else 0)
    else:
        safety = restore(target)
        print(f'Restaurado a partir de {target}. Estado anterior guardado em {safety}.')
