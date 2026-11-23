"""Account-scoped introductory video progress; media stays outside public assets."""
import secrets
import struct
import time
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

MEDIA = Path(__file__).parent / 'media' / 'education'

def duration(path):
    """Lê a duração no cabeçalho mvhd sem carregar o vídeo inteiro: percorre as caixas de topo
    com seek e lê apenas o conteúdo da caixa moov (alguns KB)."""
    with open(path, 'rb') as f:
        end = f.seek(0, 2)
        start = 0
        while start + 8 <= end:
            f.seek(start)
            head = f.read(16)
            size, kind = struct.unpack_from('>I4s', head, 0)
            header = 8
            if size == 1:
                if len(head) < 16: raise ValueError('Invalid MP4')
                size = struct.unpack_from('>Q', head, 8)[0]; header = 16
            if size == 0: size = end - start
            if size < header or start + size > end: raise ValueError('Invalid MP4')
            if kind == b'moov':
                f.seek(start + header)
                result = _mvhd_duration(f.read(size - header))
                if result: return result
            start += size
    raise ValueError('Missing video duration')

def _mvhd_duration(data):
    start, end = 0, len(data)
    while start + 8 <= end:
        size, kind = struct.unpack_from('>I4s', data, start)
        header = 8
        if size == 1:
            size = struct.unpack_from('>Q', data, start + 8)[0]; header = 16
        if size == 0: size = end - start
        if size < header or start + size > end: raise ValueError('Invalid MP4')
        payload = start + header
        if kind == b'mvhd':
            offset = payload + (20 if data[payload] == 1 else 12)
            scale = struct.unpack_from('>I', data, offset)[0]
            ticks = struct.unpack_from('>Q' if data[payload] == 1 else '>I', data, offset + 4)[0]
            return ticks / scale
        start += size
    return None

# This original fragmented MP4 has a zero mvhd duration. Its complete media
# duration was measured with the browser's HTMLMediaElement (no re-encoding).
DURATION_OVERRIDES = {'investimentos': 40.05449}
VIDEOS = {key: {'duration': DURATION_OVERRIDES[key] if key in DURATION_OVERRIDES else duration(MEDIA / (key + '.mp4')), 'version': '1'} for key in ('poupanca', 'controle', 'planejamento', 'investimentos')}

def migrate(conn):
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS education_videos (
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          module TEXT NOT NULL, version TEXT NOT NULL, watched REAL NOT NULL DEFAULT 0,
          completed INTEGER NOT NULL DEFAULT 0, token TEXT, position REAL, ping REAL,
          started REAL, origin REAL, PRIMARY KEY(user_id,module,version))''')

def status(conn, uid, module):
    if module not in VIDEOS: return None
    meta = VIDEOS[module]
    with conn() as c:
        row = c.execute('SELECT watched,completed FROM education_videos WHERE user_id=? AND module=? AND version=?', (uid,module,meta['version'])).fetchone()
    return dict(meta, watched=row['watched'] if row else 0, completed=bool(row and row['completed']))

def require_intro(conn, uid, module):
    s = status(conn, uid, module)
    if s and not s['completed']: raise HTTPException(403, 'Assista ao vídeo introdutório completo para liberar esta aula.')

def modules(conn, uid, items):
    for m in items:
        m['intro'] = status(conn, uid, m['key'])
        if m['intro'] and not m['intro']['completed']:
            for t in m['topics']:
                count = len(t['acts'])
                for k in list(t):
                    if k not in ('key','title'): del t[k]
                t.update(acts=[], activity_count=count)
    return items

class Tick(BaseModel):
    token: str = Field(min_length=20,max_length=100)
    position: float = Field(ge=0,allow_inf_nan=False)

def register(app, conn, auth):
    @app.get('/api/intro/{module}/media')
    def media(module: str, request: Request):
        auth(request)
        if module not in VIDEOS: raise HTTPException(404)
        return FileResponse(MEDIA / (module + '.mp4'), media_type='video/mp4', headers={'Cache-Control':'private, no-store'})

    @app.post('/api/intro/{module}/start')
    def start(module: str, request: Request):
        uid = auth(request)['id']; s = status(conn,uid,module)
        if s is None: raise HTTPException(404)
        token = secrets.token_urlsafe(32); now = time.time()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO education_videos(user_id,module,version) VALUES(?,?,?)', (uid,module,s['version']))
            c.execute('UPDATE education_videos SET token=?,position=watched,origin=watched,ping=?,started=? WHERE user_id=? AND module=? AND version=?', (token,now,now,uid,module,s['version']))
            row = c.execute('SELECT watched,completed FROM education_videos WHERE user_id=? AND module=? AND version=?',(uid,module,s['version'])).fetchone()
        return dict(s, watched=row['watched'], completed=bool(row['completed']), token=token)

    @app.post('/api/intro/{module}/tick')
    def tick(module: str, b: Tick, request: Request):
        uid = auth(request)['id']
        if module not in VIDEOS: raise HTTPException(404)
        meta = VIDEOS[module]; now = time.time()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            r = c.execute('SELECT * FROM education_videos WHERE user_id=? AND module=? AND version=?',(uid,module,meta['version'])).fetchone()
            if not r or not secrets.compare_digest(r['token'] or '', b.token): raise HTTPException(409,'O vídeo foi aberto em outra aba. Reabra esta aula para continuar.')
            delta = b.position-r['position']
            valid = (0 <= delta <= 8 and b.position <= meta['duration']+0.2
                     and b.position-r['origin'] <= now-r['started']+0.35 and b.position <= r['watched']+8)
            watched = max(r['watched'],min(b.position,meta['duration'])) if valid else r['watched']
            done = bool(r['completed'] or watched >= meta['duration']-0.15)
            c.execute('UPDATE education_videos SET watched=?,completed=?,position=?,ping=? WHERE user_id=? AND module=? AND version=?', (watched,int(done),b.position if valid else watched,now,uid,module,meta['version']))
        return {'watched':watched,'completed':done,'accepted':valid}
