"""Local maintenance: python manage_db.py check|backup [destination]."""
import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / '.runtime'))
from app import DB_PATH, conn
from backend_services import backup_database

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'backup'])
    parser.add_argument('destination', nargs='?')
    args = parser.parse_args()
    if not DB_PATH.is_file():
        parser.error('Banco não encontrado. Inicie o aplicativo primeiro.')
    if args.action == 'backup':
        if not args.destination:
            parser.error('Informe um arquivo novo de destino para o backup.')
        target = Path(args.destination).resolve()
        if target.exists():
            parser.error('O destino já existe; escolha um novo arquivo.')
        print(backup_database(DB_PATH, target))
    else:
        with conn() as c:
            integrity = c.execute('PRAGMA integrity_check').fetchall()
            foreign = c.execute('PRAGMA foreign_key_check').fetchall()
            print('Integridade:', [r[0] for r in integrity])
            print('Violações de vínculos:', len(foreign))
            c.execute('PRAGMA optimize')
        sys.exit(0 if len(integrity) == 1 and integrity[0][0] == 'ok' and not foreign else 1)
