"""Start FinTrack using regular dependencies or the optional local .runtime folder."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if (BASE / '.runtime').is_dir():
    sys.path.insert(0, str(BASE / '.runtime'))
os.chdir(BASE)
if __name__ == '__main__':
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv(BASE / '.env')
    # FINTRACK_BACKEND=supabase usa app_supabase.py (Supabase); sem a variável, app.py (SQLite local).
    target = 'app_supabase:app' if os.getenv('FINTRACK_BACKEND', 'sqlite').lower() == 'supabase' else 'app:app'
    # Atrás de Nginx/Caddy, liste em FORWARDED_ALLOW_IPS o IP do proxy: só dele o X-Forwarded-For é aceito.
    uvicorn.run(target, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8010')),
                proxy_headers=True, forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS', '127.0.0.1'))
