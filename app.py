from __future__ import annotations

import base64, calendar, hashlib, io, json, logging, os, secrets, smtplib, sqlite3, threading, time, urllib.request, urllib.error, urllib.parse, uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError

BASE = Path(__file__).resolve().parent
load_dotenv(BASE/".env")

# Vercel Functions have a read-only project filesystem. Only /tmp is writable.
# Local development keeps using ./data as before.
IS_VERCEL = bool(os.getenv("VERCEL"))
STATIC = BASE/"static"
DATA = Path(os.environ["FINTRACK_DATA_DIR"]) if os.getenv("FINTRACK_DATA_DIR") else (Path("/tmp/fintrack") if IS_VERCEL else BASE/"data")
UPLOADS = DATA/"uploads"
DB_PATH = DATA/"fintrack.db"
DATA.mkdir(parents=True,exist_ok=True)
UPLOADS.mkdir(parents=True,exist_ok=True)

app = FastAPI(title="FinTrack", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory=STATIC), name="static")

_RATE_BUCKETS={}
_RATE_LOCK=threading.Lock()

def client_key(request:Request)->str:
    forwarded=(request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:return forwarded[:80]
    return (request.client.host if request.client else "unknown")[:80]

def rate_limit(key:str,limit:int,window_seconds:int):
    now=time.monotonic()
    with _RATE_LOCK:
        if len(_RATE_BUCKETS)>5000:
            stale=[k for k,v in _RATE_BUCKETS.items() if not v or now-v[-1]>86400]
            for k in stale[:2500]:_RATE_BUCKETS.pop(k,None)
        bucket=[t for t in _RATE_BUCKETS.get(key,[]) if now-t<window_seconds]
        if len(bucket)>=limit:
            retry=max(1,int(window_seconds-(now-bucket[0])))
            raise HTTPException(429,"Muitas tentativas. Aguarde um pouco e tente novamente.",headers={"Retry-After":str(retry)})
        bucket.append(now)
        _RATE_BUCKETS[key]=bucket

@app.middleware("http")
async def security_headers(request:Request,call_next):
    # Bloqueia mutações disparadas explicitamente de outro site moderno.
    if request.method not in {"GET","HEAD","OPTIONS"}:
        if request.headers.get("sec-fetch-site")=="cross-site":
            return Response(content='{"detail":"Solicitação de outra origem bloqueada."}',status_code=403,media_type="application/json")
        origin=request.headers.get("origin")
        host=request.headers.get("x-forwarded-host") or request.headers.get("host")
        if origin and host:
            try:
                if urllib.parse.urlparse(origin).netloc.lower()!=host.lower():
                    return Response(content='{"detail":"Origem não autorizada."}',status_code=403,media_type="application/json")
            except Exception:
                return Response(content='{"detail":"Origem inválida."}',status_code=403,media_type="application/json")
    response=await call_next(request)
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("X-Frame-Options","DENY")
    response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy","camera=(self), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy","same-origin")
    response.headers.setdefault("Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control","no-store")
    proto=(request.headers.get("x-forwarded-proto") or request.url.scheme).lower()
    if proto=="https":
        response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    return response
AVATAR_PRESETS={"cacheada":"Cacheada","longos":"Cabelos longos","plumas":"Plumas","classico":"Clássico","aviador":"Aviador","coruja":"Coruja","cao":"Cão","gato":"Gato","raposa":"Raposa","urso":"Urso"}
AVATAR_BGS=["#1DB954","#7C5CFF","#3B82F6","#FF5C8A","#F5A524","#2A2A2A"]
MAX_AVATAR_BYTES=600*1024
SESSION_COOKIE, SESSION_DAYS, MAX_RECEIPT_BYTES = "fintrack_session", 14, 5*1024*1024
MAX_MONEY_CENTS=int(os.getenv("MAX_MONEY_CENTS","100000000000"))  # R$ 1 bi por lançamento
logger=logging.getLogger("fintrack")

INCOME_CATEGORIES = ["Mesada","Salário","Bolsa","Trabalho eventual","Vendas","Presentes","Outros"]
EXPENSE_CATEGORIES = ["Alimentação","Transporte","Lazer","Contas","Saúde","Educação","Compras","Assinaturas","Outros"]

from education_content import EDUCATION, PASS, public_module, grade_item
from backend_services import local_today

class ManagedConnection(sqlite3.Connection):
    """Commit/rollback and always release the file handle at context exit."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def conn():
    c=sqlite3.connect(DB_PATH,timeout=30,factory=ManagedConnection); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA synchronous=FULL")
    return c

def now_iso(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
def today_iso(): return local_today().isoformat()
def parse_date(s):
    try:return date.fromisoformat(s)
    except (TypeError,ValueError):raise HTTPException(422,"Data inválida.")
def cents(v):
    try:
        s=str(v).strip().replace("R$","").replace(" ","")
        if "," in s:
            s=s.replace(".","").replace(",",".")
        value=Decimal(s)
        if not value.is_finite():raise InvalidOperation
        quantized=value.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        n=int(quantized*100)
    except (InvalidOperation,ValueError,TypeError):
        raise HTTPException(422,"Valor inválido.")
    if n<=0:raise HTTPException(422,"O valor deve ser maior que zero.")
    if n>MAX_MONEY_CENTS:raise HTTPException(422,"O valor informado excede o limite permitido.")
    return n

def validate_password(password:str):
    if len(password)<8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(422,"Use pelo menos 8 caracteres, com pelo menos uma letra e um número.")

def validate_image_bytes(data:bytes):
    """Decodifica a imagem para evitar confiar apenas em extensão/MIME ou bytes iniciais."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt=(img.format or "").upper()
            width,height=img.size
            if width<=0 or height<=0 or width*height>20_000_000:
                raise HTTPException(422,"A imagem possui dimensões inválidas ou muito grandes.")
            img.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(422,"O arquivo não contém uma imagem válida.")
    mapping={"JPEG":("image/jpeg",".jpg"),"PNG":("image/png",".png"),"WEBP":("image/webp",".webp")}
    if fmt not in mapping:
        raise HTTPException(422,"Envie uma imagem JPG, PNG ou WebP.")
    return mapping[fmt]

def thash(t): return hashlib.sha256(t.encode()).hexdigest()
def pwd(password,salt_b64=None):
    salt=base64.b64decode(salt_b64) if salt_b64 else secrets.token_bytes(16)
    dk=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return base64.b64encode(dk).decode(),base64.b64encode(salt).decode()
def pwd_ok(password,expected,salt):
    actual,_=pwd(password,salt); return secrets.compare_digest(actual,expected)

def init_db():
    schema=r"""
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN('aluno','professor')),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reset_tokens(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at TEXT NOT NULL,used INTEGER DEFAULT 0,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS user_avatars(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL CHECK(kind IN('preset','photo')),preset TEXT NOT NULL,bg TEXT NOT NULL,photo_path TEXT,photo_mime TEXT,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS user_settings(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,theme TEXT DEFAULT 'dark',tips INTEGER DEFAULT 1,goal_alerts INTEGER DEFAULT 1,weekly_email INTEGER DEFAULT 0,chart_type TEXT DEFAULT 'line');
    CREATE TABLE IF NOT EXISTS custom_categories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,type TEXT NOT NULL,name TEXT NOT NULL,UNIQUE(user_id,type,name));
    CREATE TABLE IF NOT EXISTS recurrences(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,type TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,amount_cents INTEGER NOT NULL,frequency TEXT NOT NULL,start_date TEXT NOT NULL,next_date TEXT NOT NULL,end_date TEXT,anchor_day INTEGER NOT NULL,anchor_month INTEGER NOT NULL,note TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,type TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),date TEXT NOT NULL,note TEXT,recurrence_id TEXT REFERENCES recurrences(id) ON DELETE SET NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_rec_occ ON transactions(recurrence_id,date) WHERE recurrence_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id,date);
    CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,description TEXT,target_cents INTEGER NOT NULL,deadline TEXT NOT NULL,status TEXT DEFAULT 'ativa',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS goal_reservations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,kind TEXT NOT NULL,amount_cents INTEGER NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS education_progress(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,module_key TEXT NOT NULL,topic_key TEXT NOT NULL,status TEXT NOT NULL,score INTEGER,answers_json TEXT,updated_at TEXT NOT NULL,PRIMARY KEY(user_id,module_key,topic_key));
    CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,role TEXT NOT NULL,content TEXT NOT NULL,request_key TEXT,created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_msg_req ON messages(user_id,request_key) WHERE request_key IS NOT NULL;
    CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY,teacher_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,description TEXT,code TEXT UNIQUE NOT NULL,code_active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS memberships(id TEXT PRIMARY KEY,class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,student_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,share_financial INTEGER DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(class_id,student_id));
    CREATE TABLE IF NOT EXISTS assignments(id TEXT PRIMARY KEY,class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,teacher_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,content_key TEXT NOT NULL,content_type TEXT NOT NULL,due_date TEXT,instructions TEXT,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assignment_progress(assignment_id TEXT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,student_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,status TEXT DEFAULT 'pendente',score INTEGER,submitted_at TEXT,PRIMARY KEY(assignment_id,student_id));
    CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,private_path TEXT NOT NULL,mime TEXT NOT NULL,original_name TEXT NOT NULL,created_at TEXT NOT NULL,content_sha256 TEXT);
    CREATE INDEX IF NOT EXISTS idx_sessions_user_exp ON sessions(user_id,expires_at);
    CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id,created_at);
    CREATE INDEX IF NOT EXISTS idx_memberships_student ON memberships(student_id);
    CREATE INDEX IF NOT EXISTS idx_assignments_class ON assignments(class_id,created_at);
    """
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(schema)
        cols={r["name"] for r in c.execute("PRAGMA table_info(user_settings)").fetchall()}
        if "chart_type" not in cols:
            c.execute("ALTER TABLE user_settings ADD COLUMN chart_type TEXT DEFAULT 'line'")
        receipt_cols={r["name"] for r in c.execute("PRAGMA table_info(receipts)").fetchall()}
        if "content_sha256" not in receipt_cols:
            c.execute("ALTER TABLE receipts ADD COLUMN content_sha256 TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_receipts_user_hash ON receipts(user_id,content_sha256)")
    from backend_services import migrate
    migrate(conn, DB_PATH)

def auth(request):
    tok=request.cookies.get(SESSION_COOKIE)
    if not tok: raise HTTPException(401,"Sessão necessária.")
    with conn() as c:
        u=c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",(thash(tok),now_iso())).fetchone()
    if not u: raise HTTPException(401,"Sessão expirada.")
    return u

def owner(table,item,user):
    if table not in {"transactions","goals","conversations","receipts"}: raise HTTPException(500,"Tabela inválida.")
    with conn() as c:r=c.execute(f"SELECT * FROM {table} WHERE id=? AND user_id=?",(item,user)).fetchone()
    if not r: raise HTTPException(404,"Registro não encontrado.")
    return r

def next_occ(d,f,day,month):
    if f=="semanal": return d+timedelta(days=7)
    if f=="mensal":
        y,m=d.year,d.month+1
        if m==13:y,m=y+1,1
        return date(y,m,min(day,calendar.monthrange(y,m)[1]))
    y=d.year+1; return date(y,month,min(day,calendar.monthrange(y,month)[1]))

def generate_recurrences():
    t=local_today()
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        for r in c.execute("SELECT * FROM recurrences WHERE active=1 AND next_date<=?", (t.isoformat(),)).fetchall():
            d=date.fromisoformat(r["next_date"]); end=date.fromisoformat(r["end_date"]) if r["end_date"] else None
            while d<=t and (not end or d<=end):
                c.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()),r["user_id"],r["type"],r["category"],r["description"],r["amount_cents"],d.isoformat(),r["note"],r["id"],now_iso(),now_iso()))
                d=next_occ(d,r["frequency"],r["anchor_day"],r["anchor_month"])
            c.execute("UPDATE recurrences SET next_date=?,active=? WHERE id=?",(d.isoformat(),0 if end and d>end else 1,r["id"]))

_worker_stop=threading.Event()

def worker():
    while not _worker_stop.is_set():
        try:generate_recurrences()
        except Exception:
            logger.exception("Falha ao gerar recorrências")
        _worker_stop.wait(60)

@app.on_event("startup")
def startup():
    init_db()
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at<=?",(now_iso(),))
        c.execute("DELETE FROM reset_tokens WHERE expires_at<=? OR used=1",(now_iso(),))
    generate_recurrences()
    # A thread infinita não é adequada para funções serverless.
    # Em produção, recorrências devem usar Vercel Cron/job externo.
    if not IS_VERCEL:
        _worker_stop.clear()
        threading.Thread(target=worker,daemon=True).start()

@app.on_event("shutdown")
def shutdown():
    _worker_stop.set()

class RegisterIn(BaseModel):
    name:str=Field(min_length=2,max_length=100); email:EmailStr
    password:str=Field(min_length=8,max_length=128); role:str; terms:bool
class LoginIn(BaseModel):
    email:EmailStr; password:str
class ForgotIn(BaseModel):
    email:EmailStr
class ResetIn(BaseModel):
    token:str; password:str=Field(min_length=8,max_length=128)

def session(user_id,response,payload):
    raw=secrets.token_urlsafe(32); exp=(datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat().replace("+00:00","Z")
    with conn() as c:c.execute("INSERT INTO sessions VALUES(?,?,?,?)",(thash(raw),user_id,exp,now_iso()))
    response.set_cookie(SESSION_COOKIE,raw,httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","0")=="1",max_age=SESSION_DAYS*86400,path="/")
    return payload

@app.post("/api/auth/register")
def register(b:RegisterIn,response:Response,request:Request):
    rate_limit("register:"+client_key(request),5,3600)
    if b.role not in ("aluno","professor"):raise HTTPException(422,"Perfil inválido.")
    if not b.terms:raise HTTPException(422,"Aceite os termos e a política de privacidade.")
    validate_password(b.password)
    professor_code=os.getenv("PROFESSOR_SIGNUP_CODE","").strip()
    if b.role=="professor" and professor_code:
        supplied=request.headers.get("x-professor-signup-code","")
        if not secrets.compare_digest(supplied,professor_code):
            raise HTTPException(403,"Cadastro de professor requer autorização.")
    uid=str(uuid.uuid4()); ph,salt=pwd(b.password)
    with conn() as c:
        try:
            c.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)",(uid,b.name.strip(),b.email.lower(),ph,salt,b.role,now_iso()))
            c.execute("INSERT INTO user_settings(user_id) VALUES(?)",(uid,))
        except sqlite3.IntegrityError: raise HTTPException(400,"Não foi possível criar a conta com esses dados.")
    return session(uid,response,{"status":"ok","next":"/avatar.html"})

@app.post("/api/auth/login")
def login(b:LoginIn,response:Response,request:Request):
    email=b.email.lower()
    rate_limit("login-ip:"+client_key(request),30,900)
    rate_limit("login:"+client_key(request)+":"+hashlib.sha256(email.encode()).hexdigest()[:12],10,900)
    with conn() as c:u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not u or not pwd_ok(b.password,u["password_hash"],u["salt"]):raise HTTPException(401,"E-mail ou senha incorretos.")
    return session(u["id"],response,{"status":"ok","next":"/app.html" if avatar_of(u["id"]) else "/avatar.html"})

@app.post("/api/auth/logout")
def logout(request:Request,response:Response):
    tok=request.cookies.get(SESSION_COOKIE)
    if tok:
        with conn() as c:c.execute("DELETE FROM sessions WHERE token_hash=?",(thash(tok),))
    response.delete_cookie(SESSION_COOKIE,path="/"); response.headers["Cache-Control"]="no-store"; return {"status":"ok"}

@app.get("/api/auth/me")
def me(request:Request):
    u=auth(request)
    with conn() as c:s=c.execute("SELECT * FROM user_settings WHERE user_id=?",(u["id"],)).fetchone()
    return {"id":u["id"],"name":u["name"],"email":u["email"],"role":u["role"],"settings":dict(s),"avatar":avatar_of(u["id"])}

def avatar_of(uid):
    with conn() as c:r=c.execute("SELECT kind,preset,bg,updated_at FROM user_avatars WHERE user_id=?",(uid,)).fetchone()
    return {"kind":r["kind"],"preset":r["preset"],"bg":r["bg"],"v":r["updated_at"]} if r else None

def drop_photo(c,uid):
    r=c.execute("SELECT photo_path FROM user_avatars WHERE user_id=?",(uid,)).fetchone()
    if r and r["photo_path"]:
        try:Path(r["photo_path"]).unlink()
        except OSError:pass

class AvatarPresetIn(BaseModel):
    preset:str;bg:str

@app.get("/api/avatar/options")
def avatar_options(request:Request):
    auth(request);return {"presets":[{"key":k,"label":v} for k,v in AVATAR_PRESETS.items()],"backgrounds":AVATAR_BGS}

@app.put("/api/avatar/preset")
def avatar_set_preset(b:AvatarPresetIn,request:Request):
    u=auth(request)
    if b.preset not in AVATAR_PRESETS or b.bg not in AVATAR_BGS:raise HTTPException(422,"Avatar inválido.")
    with conn() as c:
        drop_photo(c,u["id"])
        c.execute("""INSERT INTO user_avatars VALUES(?,?,?,?,NULL,NULL,?)
          ON CONFLICT(user_id) DO UPDATE SET kind='preset',preset=excluded.preset,bg=excluded.bg,photo_path=NULL,photo_mime=NULL,updated_at=excluded.updated_at""",(u["id"],"preset",b.preset,b.bg,now_iso()))
    return {"avatar":avatar_of(u["id"])}

@app.post("/api/avatar/photo")
async def avatar_upload(request:Request,image:UploadFile=File(...)):
    u=auth(request)
    data=await image.read(MAX_AVATAR_BYTES+1)
    if len(data)>MAX_AVATAR_BYTES:raise HTTPException(422,"A foto deve ter no máximo 600 KB. Recorte novamente.")
    # O tipo é definido pelo conteúdo do arquivo, nunca pelo cabeçalho enviado.
    detected=validate_image_bytes(data)
    if not detected:raise HTTPException(422,"Envie uma imagem JPG, PNG ou WebP.")
    mime,ext=detected
    folder=UPLOADS/"avatars";folder.mkdir(parents=True,exist_ok=True)
    path=folder/(u["id"]+"-"+uuid.uuid4().hex[:8]+ext)
    with conn() as c:
        old=c.execute("SELECT bg FROM user_avatars WHERE user_id=?",(u["id"],)).fetchone()
        drop_photo(c,u["id"]);path.write_bytes(data)
        c.execute("""INSERT INTO user_avatars VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET kind='photo',photo_path=excluded.photo_path,photo_mime=excluded.photo_mime,updated_at=excluded.updated_at""",
          (u["id"],"photo","coruja",old["bg"] if old else AVATAR_BGS[0],str(path),mime,now_iso()))
    return {"avatar":avatar_of(u["id"])}

@app.post("/api/avatar/skip")
def avatar_skip(request:Request):
    """Pular a criação: usa um avatar padrão do app, que pode ser trocado depois em Configurações."""
    u=auth(request)
    with conn() as c:c.execute("INSERT OR IGNORE INTO user_avatars VALUES(?,?,?,?,NULL,NULL,?)",(u["id"],"preset","coruja",AVATAR_BGS[0],now_iso()))
    return {"avatar":avatar_of(u["id"])}

@app.get("/api/avatar/{uid}/photo")
def avatar_photo(uid:str,request:Request):
    """Foto privada: só o próprio usuário e professor/aluno da mesma turma podem ver."""
    u=auth(request)
    with conn() as c:
        if uid!=u["id"] and not c.execute("""SELECT 1 FROM memberships m JOIN classes k ON k.id=m.class_id
            WHERE (k.teacher_id=? AND m.student_id=?) OR (k.teacher_id=? AND m.student_id=?)""",(u["id"],uid,uid,u["id"])).fetchone():
            raise HTTPException(403,"Sem permissão.")
        r=c.execute("SELECT photo_path,photo_mime FROM user_avatars WHERE user_id=? AND kind='photo'",(uid,)).fetchone()
    if not r or not r["photo_path"] or not Path(r["photo_path"]).exists():raise HTTPException(404,"Sem foto.")
    return FileResponse(r["photo_path"],media_type=r["photo_mime"],headers={"Cache-Control":"private, max-age=86400","X-Content-Type-Options":"nosniff"})

def smtp_ready(): return bool(os.getenv("SMTP_HOST") and os.getenv("APP_BASE_URL"))
def send_reset(email,token):
    msg=EmailMessage(); msg["Subject"]="Redefinição de senha — FinTrack"; msg["To"]=email
    msg["From"]=os.getenv("SMTP_FROM",os.getenv("SMTP_USER","noreply@localhost"))
    msg.set_content("Use este link temporário para definir uma nova senha:\n\n"+os.getenv("APP_BASE_URL").rstrip("/")+"/reset.html?token="+token)
    with smtplib.SMTP(os.getenv("SMTP_HOST"),int(os.getenv("SMTP_PORT","587")),timeout=12) as s:
        if os.getenv("SMTP_STARTTLS","1")=="1":s.starttls()
        if os.getenv("SMTP_USER"):s.login(os.getenv("SMTP_USER"),os.getenv("SMTP_PASSWORD",""))
        s.send_message(msg)

@app.post("/api/auth/forgot")
def forgot(b:ForgotIn,request:Request):
    email=b.email.lower()
    rate_limit("forgot:"+client_key(request)+":"+hashlib.sha256(email.encode()).hexdigest()[:12],5,3600)
    neutral={"message":"Se o endereço puder receber a recuperação, enviaremos as instruções."}
    if not smtp_ready():
        return neutral
    with conn() as c:
        u=c.execute("SELECT id,email FROM users WHERE email=?",(email,)).fetchone()
        if u:
            raw=secrets.token_urlsafe(32);exp=(datetime.now(timezone.utc)+timedelta(minutes=30)).replace(microsecond=0).isoformat().replace("+00:00","Z")
            c.execute("INSERT INTO reset_tokens VALUES(?,?,?,?,?)",(thash(raw),u["id"],exp,0,now_iso()))
            try:send_reset(u["email"],raw)
            except Exception:
                logger.exception("Falha ao enviar recuperação de senha")
    return neutral

@app.post("/api/auth/reset")
def reset_password(b:ResetIn):
    validate_password(b.password)
    with conn() as c:
        r=c.execute("SELECT * FROM reset_tokens WHERE token_hash=? AND used=0 AND expires_at>?",(thash(b.token),now_iso())).fetchone()
        if not r: raise HTTPException(400,"Este link expirou ou já foi utilizado.")
        ph,salt=pwd(b.password); c.execute("UPDATE users SET password_hash=?,salt=? WHERE id=?",(ph,salt,r["user_id"]))
        c.execute("UPDATE reset_tokens SET used=1 WHERE token_hash=?",(thash(b.token),)); c.execute("DELETE FROM sessions WHERE user_id=?",(r["user_id"],))
    return {"status":"ok"}

class CatIn(BaseModel):
    type:str; name:str=Field(min_length=2,max_length=50)
@app.get("/api/categories")
def categories(request:Request):
    u=auth(request)
    with conn() as c:custom=[dict(r) for r in c.execute("SELECT id,type,name FROM custom_categories WHERE user_id=? ORDER BY name",(u["id"],)).fetchall()]
    return {"receita":INCOME_CATEGORIES,"despesa":EXPENSE_CATEGORIES,"personalizadas":custom}
@app.post("/api/categories")
def add_category(b:CatIn,request:Request):
    u=auth(request)
    if b.type not in ("receita","despesa"):raise HTTPException(422,"Tipo inválido.")
    name=" ".join(b.name.split())
    base=INCOME_CATEGORIES if b.type=="receita" else EXPENSE_CATEGORIES
    if any(x.casefold()==name.casefold() for x in base):raise HTTPException(409,"Essa categoria já existe.")
    cid=str(uuid.uuid4())
    with conn() as c:
        if c.execute("SELECT 1 FROM custom_categories WHERE user_id=? AND type=? AND lower(name)=lower(?)",(u["id"],b.type,name)).fetchone():
            raise HTTPException(409,"Essa categoria já existe.")
        c.execute("INSERT INTO custom_categories VALUES(?,?,?,?)",(cid,u["id"],b.type,name))
    return {"id":cid,"type":b.type,"name":name}

def valid_category(user,type_,category):
    base=INCOME_CATEGORIES if type_=="receita" else EXPENSE_CATEGORIES if type_=="despesa" else []
    if not base:raise HTTPException(422,"Tipo inválido.")
    with conn() as c:custom=[r["name"] for r in c.execute("SELECT name FROM custom_categories WHERE user_id=? AND type=?",(user,type_)).fetchall()]
    if category not in base+custom:raise HTTPException(422,"Categoria incompatível com o tipo selecionado.")

class TxIn(BaseModel):
    type:str; category:str; description:str=Field(min_length=1,max_length=160)
    amount:Any; date:str; note:Optional[str]=Field(default=None,max_length=1000); recurrence:Optional[dict]=None

@app.post("/api/transactions")
def add_tx(b:TxIn,request:Request):
    u=auth(request); valid_category(u["id"],b.type,b.category); value=cents(b.amount); d=parse_date(b.date)
    rid=None
    with conn() as c:
        if b.recurrence and b.recurrence.get("enabled"):
            f=b.recurrence.get("frequency")
            if f not in ("semanal","mensal","anual"):raise HTTPException(422,"Frequência inválida.")
            start=parse_date(b.recurrence.get("start_date") or b.date); end=parse_date(b.recurrence["end_date"]) if b.recurrence.get("end_date") else None
            if end and end<start:raise HTTPException(422,"A data de encerramento não pode ser anterior ao início.")
            rid=str(uuid.uuid4()); nd=next_occ(start,f,start.day,start.month)
            c.execute("INSERT INTO recurrences VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,u["id"],b.type,b.category,b.description.strip(),value,f,start.isoformat(),nd.isoformat(),end.isoformat() if end else None,start.day,start.month,b.note,1,now_iso()))
            d=start
        tid=str(uuid.uuid4())
        c.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)",(tid,u["id"],b.type,b.category,b.description.strip(),value,d.isoformat(),b.note,rid,now_iso(),now_iso()))
    return {"status":"ok","id":tid}

@app.get("/api/transactions")
def list_tx(request:Request,type:Optional[str]=None,start:Optional[str]=None,end:Optional[str]=None,q:Optional[str]=None,sort:str="date_desc",page:int=1,page_size:int=20):
    u=auth(request); page=max(page,1); page_size=min(max(page_size,1),100); where=["user_id=?"]; args=[u["id"]]
    if type in ("receita","despesa"):where.append("type=?");args.append(type)
    if start:parse_date(start);where.append("date>=?");args.append(start)
    if end:parse_date(end);where.append("date<=?");args.append(end)
    if start and end and start>end:raise HTTPException(422,"A data inicial não pode ser posterior à final.")
    if q:where.append("(description LIKE ? OR category LIKE ?)");args += [f"%{q}%",f"%{q}%"]
    w=" AND ".join(where); order="date ASC,created_at ASC" if sort=="date_asc" else "date DESC,created_at DESC"
    with conn() as c:
        total=c.execute(f"SELECT COUNT(*) n FROM transactions WHERE {w}",args).fetchone()["n"]
        rows=c.execute(f"SELECT * FROM transactions WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?",args+[page_size,(page-1)*page_size]).fetchall()
        s=c.execute(f"SELECT COALESCE(SUM(CASE WHEN type='receita' THEN amount_cents ELSE 0 END),0) r,COALESCE(SUM(CASE WHEN type='despesa' THEN amount_cents ELSE 0 END),0) d FROM transactions WHERE {w}",args).fetchone()
    return {"items":[dict(r) for r in rows],"total":total,"page":page,"page_size":page_size,"summary":{"receitas":s["r"],"despesas":s["d"],"resultado":s["r"]-s["d"]}}

@app.put("/api/transactions/{tid}")
def edit_tx(tid:str,b:TxIn,request:Request,scope:str="single"):
    u=auth(request); row=owner("transactions",tid,u["id"]); valid_category(u["id"],b.type,b.category); value=cents(b.amount); d=parse_date(b.date)
    with conn() as c:
        c.execute("UPDATE transactions SET type=?,category=?,description=?,amount_cents=?,date=?,note=?,updated_at=? WHERE id=? AND user_id=?",(b.type,b.category,b.description.strip(),value,d.isoformat(),b.note,now_iso(),tid,u["id"]))
        if scope=="future" and row["recurrence_id"]:
            c.execute("UPDATE recurrences SET type=?,category=?,description=?,amount_cents=?,note=? WHERE id=? AND user_id=?",(b.type,b.category,b.description.strip(),value,b.note,row["recurrence_id"],u["id"]))
            c.execute("UPDATE transactions SET type=?,category=?,description=?,amount_cents=?,note=?,updated_at=? WHERE recurrence_id=? AND user_id=? AND date>=? AND id<>?",(b.type,b.category,b.description.strip(),value,b.note,now_iso(),row["recurrence_id"],u["id"],row["date"],tid))
    return {"status":"ok","scope":scope}
@app.delete("/api/transactions/{tid}")
def delete_tx(tid:str,request:Request):
    u=auth(request);owner("transactions",tid,u["id"])
    with conn() as c:c.execute("DELETE FROM transactions WHERE id=? AND user_id=?",(tid,u["id"]))
    return {"status":"ok"}

def balance(c,user):
    return int(c.execute("SELECT COALESCE(SUM(CASE WHEN type='receita' THEN amount_cents ELSE -amount_cents END),0) n FROM transactions WHERE user_id=? AND date<=?",(user,today_iso())).fetchone()["n"])
def reserved(c,user,goal=None):
    sql="SELECT COALESCE(SUM(CASE WHEN r.kind='reserva' THEN r.amount_cents ELSE -r.amount_cents END),0) n FROM goal_reservations r JOIN goals g ON g.id=r.goal_id WHERE r.user_id=? AND g.status!='excluida'"
    a=[user]
    if goal:sql+=" AND r.goal_id=?";a.append(goal)
    return int(c.execute(sql,a).fetchone()["n"])

@app.get("/api/dashboard")
def dashboard(request:Request,start:Optional[str]=None,end:Optional[str]=None):
    u=auth(request); t=local_today(); start=start or t.replace(day=1).isoformat(); end=end or t.isoformat(); parse_date(start);parse_date(end)
    if start>end:raise HTTPException(422,"A data inicial não pode ser posterior à final.")
    with conn() as c:
        bal=balance(c,u["id"]); res=reserved(c,u["id"])
        p=c.execute("SELECT COALESCE(SUM(CASE WHEN type='receita' THEN amount_cents ELSE 0 END),0) r,COALESCE(SUM(CASE WHEN type='despesa' THEN amount_cents ELSE 0 END),0) d FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",(u["id"],start,end)).fetchone()
        cats=[dict(r) for r in c.execute("SELECT category,SUM(amount_cents) amount_cents FROM transactions WHERE user_id=? AND type='despesa' AND date BETWEEN ? AND ? GROUP BY category ORDER BY amount_cents DESC",(u["id"],start,end)).fetchall()]
        # Keep the V5 graph's six-month history, independently of summary filters.
        end_day=parse_date(end)
        absolute_month=end_day.year*12+end_day.month-1
        month_keys=[f"{n//12:04d}-{n%12+1:02d}" for n in range(absolute_month-5,absolute_month+1)]
        chart_end=f"{end_day.year:04d}-{end_day.month:02d}-{calendar.monthrange(end_day.year,end_day.month)[1]:02d}"
        monthly={r["month"]:dict(r) for r in c.execute("SELECT substr(date,1,7) month,SUM(CASE WHEN type='receita' THEN amount_cents ELSE 0 END) receitas,SUM(CASE WHEN type='despesa' THEN amount_cents ELSE 0 END) despesas FROM transactions WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY substr(date,1,7)",(u["id"],month_keys[0]+"-01",chart_end)).fetchall()}
        months=[monthly.get(key,{"month":key,"receitas":0,"despesas":0}) for key in month_keys]
        recent=[dict(r) for r in c.execute("SELECT * FROM transactions WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC,created_at DESC LIMIT 5",(u["id"],start,end)).fetchall()]
        gs=[dict(r) for r in c.execute("SELECT g.*,COALESCE(SUM(CASE WHEN gr.kind='reserva' THEN gr.amount_cents ELSE -gr.amount_cents END),0) reserved_cents FROM goals g LEFT JOIN goal_reservations gr ON gr.goal_id=g.id WHERE g.user_id=? AND g.status!='excluida' GROUP BY g.id ORDER BY g.created_at DESC LIMIT 4",(u["id"],)).fetchall()]
    return {"period":{"start":start,"end":end},"balance_total":bal,"receitas":p["r"],"despesas":p["d"],"resultado":p["r"]-p["d"],"reserved":res,"available":bal-res,"categories":cats,"months":months,"recent":recent,"goals":gs}

class GoalIn(BaseModel):
    title:str=Field(min_length=1,max_length=100);description:Optional[str]=Field(default=None,max_length=600);target:Any;deadline:str
class AmountIn(BaseModel):
    amount:Any

@app.get("/api/goals")
def get_goals(request:Request):
    u=auth(request)
    with conn() as c:rows=c.execute("SELECT g.*,COALESCE(SUM(CASE WHEN r.kind='reserva' THEN r.amount_cents ELSE -r.amount_cents END),0) reserved_cents FROM goals g LEFT JOIN goal_reservations r ON r.goal_id=g.id WHERE g.user_id=? AND g.status!='excluida' GROUP BY g.id ORDER BY g.created_at DESC",(u["id"],)).fetchall()
    return {"items":[dict(r) for r in rows]}
@app.post("/api/goals")
def new_goal(b:GoalIn,request:Request):
    u=auth(request); value=cents(b.target); d=parse_date(b.deadline)
    if d<local_today():raise HTTPException(422,"O prazo precisa ser hoje ou uma data futura.")
    gid=str(uuid.uuid4())
    with conn() as c:c.execute("INSERT INTO goals VALUES(?,?,?,?,?,?,?,?,?)",(gid,u["id"],b.title.strip(),b.description,value,d.isoformat(),"ativa",now_iso(),now_iso()))
    return {"status":"ok","id":gid}
@app.put("/api/goals/{gid}")
def edit_goal(gid:str,b:GoalIn,request:Request):
    u=auth(request);owner("goals",gid,u["id"]);value=cents(b.target);d=parse_date(b.deadline)
    with conn() as c:c.execute("UPDATE goals SET title=?,description=?,target_cents=?,deadline=?,updated_at=? WHERE id=? AND user_id=?",(b.title.strip(),b.description,value,d.isoformat(),now_iso(),gid,u["id"]))
    return {"status":"ok"}
@app.post("/api/goals/{gid}/reserve")
def goal_reserve(gid:str,b:AmountIn,request:Request):
    u=auth(request);owner("goals",gid,u["id"]);value=cents(b.amount)
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        current=c.execute("SELECT status FROM goals WHERE id=? AND user_id=?",(gid,u["id"])).fetchone()
        if not current or current["status"]!="ativa":raise HTTPException(422,"A meta precisa estar ativa para receber reservas.")
        if value>balance(c,u["id"])-reserved(c,u["id"]):raise HTTPException(422,"O valor excede seu saldo disponível.")
        c.execute("INSERT INTO goal_reservations VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),u["id"],gid,"reserva",value,now_iso()))
    return {"status":"ok"}
@app.post("/api/goals/{gid}/withdraw")
def goal_withdraw(gid:str,b:AmountIn,request:Request):
    u=auth(request);owner("goals",gid,u["id"]);value=cents(b.amount)
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        current=c.execute("SELECT status FROM goals WHERE id=? AND user_id=?",(gid,u["id"])).fetchone()
        if not current or current["status"]=="excluida":raise HTTPException(422,"A meta não está disponível para retirada.")
        if value>reserved(c,u["id"],gid):raise HTTPException(422,"A retirada não pode ser maior que a reserva atual.")
        c.execute("INSERT INTO goal_reservations VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),u["id"],gid,"retirada",value,now_iso()))
    return {"status":"ok"}
@app.post("/api/goals/{gid}/complete")
def goal_complete(gid:str,request:Request):
    u=auth(request);owner("goals",gid,u["id"])
    with conn() as c:c.execute("UPDATE goals SET status='concluida',updated_at=? WHERE id=? AND user_id=?",(now_iso(),gid,u["id"]))
    return {"status":"ok"}
@app.delete("/api/goals/{gid}")
def goal_delete(gid:str,request:Request):
    u=auth(request);owner("goals",gid,u["id"])
    with conn() as c:c.execute("UPDATE goals SET status='excluida',updated_at=? WHERE id=? AND user_id=?",(now_iso(),gid,u["id"]))
    return {"status":"ok","message":"A reserva foi liberada para o saldo disponível; o saldo total não mudou."}

class ProgressIn(BaseModel):
    status:str;score:Optional[int]=None;answers:Optional[dict]=None
class CheckIn(BaseModel):
    i:int;answer:Any=None
class SubmitIn(BaseModel):
    answers:list

def find_lesson(module,topic):
    for m in EDUCATION:
        if m["key"]==module:
            for t in m["topics"]:
                if t["key"]==topic:return t
    raise HTTPException(404,"Conteúdo não encontrado.")

@app.get("/api/education")
def get_education(request:Request):
    u=auth(request)
    with conn() as c:p=[dict(r) for r in c.execute("SELECT * FROM education_progress WHERE user_id=?",(u["id"],)).fetchall()]
    return {"modules":[public_module(m) for m in EDUCATION],"progress":p,"pass":PASS}

@app.put("/api/education/{module}/{topic}")
def set_progress(module:str,topic:str,b:ProgressIn,request:Request):
    """Só registra que a aula foi aberta. A conclusão exige as atividades (rota /submit)."""
    u=auth(request);find_lesson(module,topic)
    if b.status!="em_andamento":raise HTTPException(400,"Conclua as atividades da aula para registrar a conclusão.")
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO education_progress VALUES(?,?,?,?,?,?,?)",(u["id"],module,topic,"em_andamento",None,"{}",now_iso()))
    return {"status":"ok"}

@app.post("/api/education/{module}/{topic}/check")
def check_item(module:str,topic:str,b:CheckIn,request:Request):
    auth(request);t=find_lesson(module,topic)
    if not 0<=b.i<len(t["acts"]):raise HTTPException(404,"Atividade não encontrada.")
    try:f,right=grade_item(t["acts"][b.i],b.answer)
    except Exception:raise HTTPException(422,"Resposta inválida.")
    a=t["acts"][b.i]
    return {"ok":f==1.0,"fraction":f,"right":right,"why":a["why"]}

@app.post("/api/education/{module}/{topic}/submit")
def submit_lesson(module:str,topic:str,b:SubmitIn,request:Request):
    u=auth(request);t=find_lesson(module,topic)
    if len(b.answers)!=len(t["acts"]):raise HTTPException(422,"Responda todas as atividades.")
    fr=[];res=[]
    for a,x in zip(t["acts"],b.answers):
        try:f,right=grade_item(a,x)
        except Exception:raise HTTPException(422,"Resposta inválida.")
        fr.append(f);res.append({"ok":f==1.0,"fraction":f,"right":right,"why":a["why"]})
    score=round(100*sum(fr)/len(fr))
    with conn() as c:
        prev=c.execute("SELECT status,score,answers_json FROM education_progress WHERE user_id=? AND module_key=? AND topic_key=?",(u["id"],module,topic)).fetchone()
        try:attempts=(json.loads(prev["answers_json"] or "{}").get("attempts") or 0)+1 if prev else 1
        except Exception:attempts=1
        best=max(score,prev["score"] or 0) if prev else score
        done=score>=PASS or (prev is not None and prev["status"]=="concluida")
        c.execute("""INSERT INTO education_progress VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(user_id,module_key,topic_key) DO UPDATE SET status=excluded.status,score=excluded.score,answers_json=excluded.answers_json,updated_at=excluded.updated_at""",
          (u["id"],module,topic,"concluida" if done else "em_andamento",best,json.dumps({"attempts":attempts,"last":b.answers,"last_score":score},ensure_ascii=False),now_iso()))
        if u["role"]=="aluno" and done:
            c.execute("""UPDATE assignment_progress SET status='concluida',score=?,submitted_at=?
              WHERE student_id=? AND assignment_id IN (SELECT id FROM assignments WHERE content_key IN (?,?))""",(best,now_iso(),u["id"],module+":"+topic,topic))
    return {"score":score,"best":best,"passed":score>=PASS,"completed":done,"attempts":attempts,"results":res}

@app.get("/api/ai/conversations")
def conversations(request:Request):
    u=auth(request)
    with conn() as c:r=c.execute("SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC",(u["id"],)).fetchall()
    return {"items":[dict(x) for x in r]}
@app.post("/api/ai/conversations")
def conversation_new(request:Request):
    u=auth(request);cid=str(uuid.uuid4())
    with conn() as c:c.execute("INSERT INTO conversations VALUES(?,?,?,?,?)",(cid,u["id"],"Nova conversa",now_iso(),now_iso()))
    return {"id":cid,"title":"Nova conversa"}
@app.get("/api/ai/conversations/{cid}")
def conversation_get(cid:str,request:Request):
    u=auth(request);owner("conversations",cid,u["id"])
    with conn() as c:r=c.execute("SELECT * FROM messages WHERE conversation_id=? AND user_id=? ORDER BY created_at",(cid,u["id"])).fetchall()
    return {"messages":[dict(x) for x in r]}
class RenameIn(BaseModel):
    title:str=Field(min_length=1,max_length=80)
@app.patch("/api/ai/conversations/{cid}")
def conversation_rename(cid:str,b:RenameIn,request:Request):
    u=auth(request);owner("conversations",cid,u["id"])
    with conn() as c:c.execute("UPDATE conversations SET title=?,updated_at=? WHERE id=? AND user_id=?",(b.title.strip(),now_iso(),cid,u["id"]))
    return {"status":"ok"}
@app.delete("/api/ai/conversations/{cid}")
def conversation_delete(cid:str,request:Request):
    u=auth(request);owner("conversations",cid,u["id"])
    with conn() as c:c.execute("DELETE FROM conversations WHERE id=? AND user_id=?",(cid,u["id"]))
    return {"status":"ok"}

def ai_ready():
    return bool(os.getenv("OPENAI_API_KEY") or (os.getenv("AI_PROVIDER_URL") and os.getenv("AI_API_KEY") and os.getenv("AI_MODEL")))

def ai_provider_name():
    return "openai" if os.getenv("OPENAI_API_KEY") else ("compatível" if ai_ready() else "não configurado")

def openai_model():
    return os.getenv("OPENAI_MODEL","gpt-5.6-luna").strip() or "gpt-5.6-luna"

def _extract_responses_text(obj:dict)->str:
    direct=obj.get("output_text")
    if isinstance(direct,str) and direct.strip():
        return direct.strip()
    parts=[]
    for item in obj.get("output",[]) or []:
        if not isinstance(item,dict) or item.get("type")!="message":
            continue
        for content in item.get("content",[]) or []:
            if not isinstance(content,dict):
                continue
            if content.get("type")=="output_text" and isinstance(content.get("text"),str):
                parts.append(content["text"])
    text="\n".join(x.strip() for x in parts if x and x.strip()).strip()
    if not text:
        raise RuntimeError("A resposta da IA não trouxe texto utilizável.")
    return text

def call_openai(messages):
    api_key=os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada.")
    instructions=[]
    input_items=[]
    for m in messages:
        role=(m.get("role") or "user").lower()
        content=str(m.get("content") or "").strip()
        if not content:
            continue
        if role in ("system","developer"):
            instructions.append(content)
        elif role in ("user","assistant"):
            input_items.append({"role":role,"content":content})
    payload={
        "model":openai_model(),
        "input":input_items,
        "max_output_tokens":int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS","1200"))
    }
    if instructions:
        payload["instructions"]="\n\n".join(instructions)
    req=urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type":"application/json",
            "Authorization":"Bearer "+api_key
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req,timeout=int(os.getenv("OPENAI_TIMEOUT_SECONDS","60"))) as r:
            obj=json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail=json.loads(e.read().decode("utf-8")).get("error",{}).get("message")
        except Exception:
            detail=None
        if e.code==401:
            raise RuntimeError("A chave da OpenAI foi recusada. Verifique OPENAI_API_KEY.")
        if e.code==403:
            raise RuntimeError(f"O projeto/chave da OpenAI não tem acesso ao modelo {openai_model()}. Verifique as permissões da chave e o Model Usage do projeto.")
        if e.code==429:
            raise RuntimeError("A OpenAI limitou as solicitações ou não há saldo/crédito disponível na API.")
        raise RuntimeError(detail or f"A OpenAI retornou erro HTTP {e.code}.")
    except urllib.error.URLError:
        raise RuntimeError("Não foi possível alcançar a OpenAI. Verifique a conexão com a internet.")
    return _extract_responses_text(obj)

def call_ai(messages):
    if os.getenv("OPENAI_API_KEY"):
        return call_openai(messages)
    if os.getenv("AI_PROVIDER_URL") and os.getenv("AI_API_KEY") and os.getenv("AI_MODEL"):
        payload=json.dumps({"model":os.getenv("AI_MODEL"),"messages":messages,"temperature":0.3}).encode()
        req=urllib.request.Request(os.getenv("AI_PROVIDER_URL"),data=payload,headers={"Content-Type":"application/json","Authorization":"Bearer "+os.getenv("AI_API_KEY")},method="POST")
        with urllib.request.urlopen(req,timeout=45) as r:o=json.loads(r.read().decode())
        try:return o["choices"][0]["message"]["content"]
        except:raise RuntimeError("Resposta de IA em formato inesperado.")
    raise RuntimeError("A IA ainda não está configurada.")

@app.get("/api/ai/status")
def ai_status(request:Request):
    auth(request)
    return {
        "configured":ai_ready(),
        "provider":ai_provider_name(),
        "model":openai_model() if os.getenv("OPENAI_API_KEY") else (os.getenv("AI_MODEL") or None)
    }

class MessageIn(BaseModel):
    content:str=Field(min_length=1,max_length=4000);request_key:str=Field(min_length=8,max_length=100)
@app.post("/api/ai/conversations/{cid}/messages")
def message_send(cid:str,b:MessageIn,request:Request):
    u=auth(request);rate_limit("ai-message:"+u["id"],30,3600);owner("conversations",cid,u["id"]);text=b.content.strip()
    assistant_key="assistant:"+b.request_key
    with conn() as c:
        answered=c.execute("SELECT * FROM messages WHERE user_id=? AND conversation_id=? AND request_key=?",(u["id"],cid,assistant_key)).fetchone()
        if answered:
            return {"duplicate":True,"assistant_message":dict(answered)}
        old=c.execute("SELECT * FROM messages WHERE user_id=? AND conversation_id=? AND request_key=?",(u["id"],cid,b.request_key)).fetchone()
        if old and old["content"]!=text:
            raise HTTPException(409,"Esta tentativa já foi usada para outra mensagem.")
        if not old:
            mid=str(uuid.uuid4());c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",(mid,cid,u["id"],"user",text,b.request_key,now_iso()))
            c.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now_iso(),cid))
        hist=[dict(x) for x in c.execute("SELECT role,content FROM messages WHERE conversation_id=? AND role IN ('user','assistant') ORDER BY created_at DESC LIMIT 20",(cid,)).fetchall()][::-1]
    if not ai_ready():raise HTTPException(503,"A IA ainda não está configurada no servidor. Sua mensagem foi salva.")
    try:
        answer=call_ai([{"role":"system","content":"""Você é o FinBot, assistente de educação e organização financeira do FinTrack.
Responda em português brasileiro, de forma clara, prática e adequada a estudantes e professores.
Nunca peça senhas bancárias, códigos de autenticação ou credenciais. Nunca faça transferências nem afirme que movimentou dinheiro.
Não acesse nem invente dados de outros usuários. Não invente renda, hábitos, transações ou metas.
Quando houver dados observados, separe claramente o que veio dos registros do usuário do que é sugestão educativa.
Sobre investimentos, explique riscos, liquidez e incerteza; nunca prometa lucro ou retorno garantido.
Você pode orientar e explicar, mas alterações financeiras exigem ações explícitas do usuário na interface."""}]+hist)
    except RuntimeError as e:
        raise HTTPException(502,str(e))
    except Exception:
        raise HTTPException(502,"A IA não respondeu. Tente novamente.")
    aid=str(uuid.uuid4());created=now_iso()
    with conn() as c:
        try:
            c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",(aid,cid,u["id"],"assistant",answer,assistant_key,created))
        except sqlite3.IntegrityError:
            existing=c.execute("SELECT * FROM messages WHERE user_id=? AND conversation_id=? AND request_key=?",(u["id"],cid,assistant_key)).fetchone()
            if existing:return {"duplicate":True,"assistant_message":dict(existing)}
            raise
        c.execute("UPDATE conversations SET updated_at=? WHERE id=?",(created,cid))
        if c.execute("SELECT COUNT(*) n FROM messages WHERE conversation_id=?",(cid,)).fetchone()["n"]<=2:c.execute("UPDATE conversations SET title=? WHERE id=?",(text[:60],cid))
    return {"assistant_message":{"id":aid,"role":"assistant","content":answer,"request_key":assistant_key,"created_at":created}}

@app.post("/api/ai/analyze-spending")
def analyze_spending(request:Request):
    u=auth(request);rate_limit("ai-analysis:"+u["id"],12,3600);start=(local_today()-timedelta(days=90)).isoformat();end=today_iso()
    with conn() as c:r=[dict(x) for x in c.execute("SELECT category,type,SUM(amount_cents) amount_cents,COUNT(*) count FROM transactions WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY category,type",(u["id"],start,end)).fetchall()]
    if not r:return {"has_data":False,"message":"Ainda não há transações no período para analisar.","period":{"start":start,"end":end}}
    if not ai_ready():raise HTTPException(503,"Há dados para análise, mas a IA ainda não está configurada. Configure OPENAI_API_KEY no arquivo .env.")
    try:
        answer=call_ai([{"role":"system","content":"Você é um educador financeiro. Separe dados observados de sugestões e informe limitações. Não invente renda, hábitos ou registros."},{"role":"user","content":"Período: "+start+" a "+end+". Analise apenas estes agregados, sem inventar hábitos ou renda: "+json.dumps(r,ensure_ascii=False)}])
    except RuntimeError as e:
        raise HTTPException(502,str(e))
    except Exception:
        raise HTTPException(502,"Não foi possível concluir a análise com IA agora.")
    return {"has_data":True,"period":{"start":start,"end":end},"observed":r,"analysis":answer}

@app.post("/api/receipts/upload")
async def receipt_upload(request:Request,image:UploadFile=File(...)):
    u=auth(request);rate_limit("receipt-upload:"+u["id"],20,3600)
    content=await image.read(MAX_RECEIPT_BYTES+1)
    if not content:raise HTTPException(422,"A imagem está vazia.")
    if len(content)>MAX_RECEIPT_BYTES:raise HTTPException(422,"A imagem deve ter no máximo 5 MB.")
    detected=validate_image_bytes(content)
    if not detected:raise HTTPException(422,"Envie uma imagem JPG, PNG ou WebP válida.")
    mime,ext=detected
    digest=hashlib.sha256(content).hexdigest()
    with conn() as c:
        duplicate=c.execute("SELECT id,mime,original_name FROM receipts WHERE user_id=? AND content_sha256=? ORDER BY created_at DESC LIMIT 1",(u["id"],digest)).fetchone()
        if duplicate:
            return {"id":duplicate["id"],"name":duplicate["original_name"],"mime":duplicate["mime"],"duplicate":True,"warning":"Este comprovante já foi enviado anteriormente."}
        rid=str(uuid.uuid4());folder=UPLOADS/u["id"];folder.mkdir(parents=True,exist_ok=True);path=folder/(rid+ext);path.write_bytes(content)
        c.execute("INSERT INTO receipts(id,user_id,private_path,mime,original_name,created_at,content_sha256) VALUES(?,?,?,?,?,?,?)",(rid,u["id"],str(path),mime,(image.filename or "comprovante")[:200],now_iso(),digest))
    return {"id":rid,"name":image.filename,"mime":mime,"duplicate":False}
@app.get("/api/receipts/{rid}/file")
def receipt_file(rid:str,request:Request):
    u=auth(request);r=owner("receipts",rid,u["id"]);path=Path(r["private_path"])
    if not path.exists():raise HTTPException(404,"Arquivo do comprovante não está disponível neste servidor.")
    return FileResponse(path,media_type=r["mime"],headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
@app.post("/api/receipts/{rid}/analyze")
def receipt_analyze(rid:str,request:Request):
    u=auth(request);r=owner("receipts",rid,u["id"]);url=os.getenv("RECEIPT_ANALYZER_URL")
    if not url:raise HTTPException(503,"O reconhecimento de comprovantes não está configurado. Você pode preencher a transação manualmente.")
    payload=json.dumps({"image_base64":base64.b64encode(Path(r["private_path"]).read_bytes()).decode(),"mime":r["mime"]}).encode()
    headers={"Content-Type":"application/json"}
    if os.getenv("RECEIPT_ANALYZER_KEY"):headers["Authorization"]="Bearer "+os.getenv("RECEIPT_ANALYZER_KEY")
    try:
        req=urllib.request.Request(url,data=payload,headers=headers,method="POST")
        with urllib.request.urlopen(req,timeout=45) as rr:result=json.loads(rr.read().decode())
    except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,json.JSONDecodeError,OSError):
        raise HTTPException(502,"Não foi possível analisar o comprovante agora.")
    return {"result":result,"saved":False}

def code():return secrets.token_hex(3).upper()
class ClassIn(BaseModel):
    name:str=Field(min_length=2,max_length=100);description:Optional[str]=Field(default=None,max_length=500)
class CodeIn(BaseModel):
    code:str
@app.get("/api/classes")
def classes(request:Request):
    u=auth(request)
    with conn() as c:
        if u["role"]=="professor":r=c.execute("SELECT c.*,(SELECT COUNT(*) FROM memberships m WHERE m.class_id=c.id) participants FROM classes c WHERE teacher_id=? ORDER BY created_at DESC",(u["id"],)).fetchall()
        else:r=c.execute("SELECT c.*,u.name teacher_name,m.share_financial FROM memberships m JOIN classes c ON c.id=m.class_id JOIN users u ON u.id=c.teacher_id WHERE m.student_id=? ORDER BY m.created_at DESC",(u["id"],)).fetchall()
    return {"role":u["role"],"items":[dict(x) for x in r]}
@app.post("/api/classes")
def class_new(b:ClassIn,request:Request):
    u=auth(request)
    if u["role"]!="professor":raise HTTPException(403,"Apenas professores podem criar turmas.")
    cid=str(uuid.uuid4())
    with conn() as c:
        for _ in range(5):
            k=code()
            try:c.execute("INSERT INTO classes VALUES(?,?,?,?,?,?,?)",(cid,u["id"],b.name.strip(),b.description,k,1,now_iso()));break
            except sqlite3.IntegrityError:continue
        else:raise HTTPException(500,"Não foi possível gerar o código.")
    return {"id":cid,"code":k}
@app.put("/api/classes/{cid}")
def class_edit(cid:str,b:ClassIn,request:Request):
    u=auth(request)
    with conn() as c:
        cur=c.execute("UPDATE classes SET name=?,description=? WHERE id=? AND teacher_id=?",(b.name.strip(),b.description,cid,u["id"]))
        if cur.rowcount==0:raise HTTPException(404,"Turma não encontrada.")
    return {"status":"ok"}
@app.post("/api/classes/preview")
def class_preview(b:CodeIn,request:Request):
    u=auth(request);rate_limit("class-code:"+u["id"]+":"+client_key(request),20,600)
    if u["role"]!="aluno":raise HTTPException(403,"Fluxo disponível para alunos.")
    with conn() as c:
        r=c.execute("SELECT c.id,c.name,c.description,u.name teacher_name FROM classes c JOIN users u ON u.id=c.teacher_id WHERE c.code=? AND c.code_active=1",(b.code.strip().upper(),)).fetchone()
        if not r:raise HTTPException(404,"Código inválido ou desativado.")
        dup=c.execute("SELECT 1 FROM memberships WHERE class_id=? AND student_id=?",(r["id"],u["id"])).fetchone()
    return {"class":dict(r),"already_member":bool(dup)}
@app.post("/api/classes/join")
def class_join(b:CodeIn,request:Request):
    u=auth(request);rate_limit("class-join:"+u["id"]+":"+client_key(request),10,600)
    if u["role"]!="aluno":raise HTTPException(403,"Fluxo disponível para alunos.")
    with conn() as c:
        r=c.execute("SELECT id FROM classes WHERE code=? AND code_active=1",(b.code.strip().upper(),)).fetchone()
        if not r:raise HTTPException(404,"Código inválido ou desativado.")
        try:c.execute("INSERT INTO memberships VALUES(?,?,?,?,?)",(str(uuid.uuid4()),r["id"],u["id"],0,now_iso()))
        except sqlite3.IntegrityError:raise HTTPException(409,"Você já participa dessa turma.")
    return {"status":"ok"}
@app.post("/api/classes/{cid}/code/renew")
def class_renew(cid:str,request:Request):
    u=auth(request);k=code()
    with conn() as c:
        cur=c.execute("UPDATE classes SET code=?,code_active=1 WHERE id=? AND teacher_id=?",(k,cid,u["id"]))
        if cur.rowcount==0:raise HTTPException(404,"Turma não encontrada.")
    return {"code":k}
@app.post("/api/classes/{cid}/code/disable")
def class_disable(cid:str,request:Request):
    u=auth(request)
    with conn() as c:
        cur=c.execute("UPDATE classes SET code_active=0 WHERE id=? AND teacher_id=?",(cid,u["id"]))
        if cur.rowcount==0:raise HTTPException(404,"Turma não encontrada.")
    return {"status":"ok"}
@app.get("/api/classes/{cid}/participants")
def class_participants(cid:str,request:Request):
    u=auth(request)
    with conn() as c:
        if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",(cid,u["id"])).fetchone():raise HTTPException(403,"Sem permissão.")
        r=c.execute("SELECT users.id,users.name,users.email,m.share_financial,m.created_at,a.kind avatar_kind,a.preset avatar_preset,a.bg avatar_bg,a.updated_at avatar_v FROM memberships m JOIN users ON users.id=m.student_id LEFT JOIN user_avatars a ON a.user_id=users.id WHERE m.class_id=?",(cid,)).fetchall()
    return {"items":[dict(x) for x in r]}
@app.get("/api/classes/{cid}/assignment-results")
def assignment_results(cid:str,request:Request):
    u=auth(request)
    with conn() as c:
        if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",(cid,u["id"])).fetchone():raise HTTPException(403,"Sem permissão.")
        r=c.execute("""SELECT a.id assignment_id,a.content_key,a.due_date,u.name student_name,
          p.status,p.score,p.submitted_at FROM assignments a
          JOIN assignment_progress p ON p.assignment_id=a.id
          JOIN users u ON u.id=p.student_id
          WHERE a.class_id=? ORDER BY a.created_at DESC,u.name""",(cid,)).fetchall()
    return {"items":[dict(x) for x in r]}

@app.get("/api/classes/{cid}/financial-summary")
def class_financial_summary(cid:str,request:Request,start:Optional[str]=None,end:Optional[str]=None):
    u=auth(request)
    t=local_today();start=start or t.replace(day=1).isoformat();end=end or t.isoformat()
    parse_date(start);parse_date(end)
    if start>end:raise HTTPException(422,"A data inicial não pode ser posterior à final.")
    with conn() as c:
        if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",(cid,u["id"])).fetchone():
            raise HTTPException(403,"Sem permissão.")
        students=c.execute("""SELECT users.id,users.name FROM memberships m
          JOIN users ON users.id=m.student_id
          WHERE m.class_id=? AND m.share_financial=1 ORDER BY users.name""",(cid,)).fetchall()
        items=[]
        for s in students:
            a=c.execute("""SELECT
              COALESCE(SUM(CASE WHEN type='receita' THEN amount_cents ELSE 0 END),0) receitas,
              COALESCE(SUM(CASE WHEN type='despesa' THEN amount_cents ELSE 0 END),0) despesas,
              COUNT(*) registros
              FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?""",(s["id"],start,end)).fetchone()
            items.append({"student_id":s["id"],"student_name":s["name"],"receitas":a["receitas"],"despesas":a["despesas"],"resultado":a["receitas"]-a["despesas"],"registros":a["registros"]})
    return {"period":{"start":start,"end":end},"items":items,"privacy":"Somente alunos que autorizaram o compartilhamento desta turma."}

class AssignmentIn(BaseModel):
    content_key:str;content_type:str;due_date:Optional[str]=None;instructions:Optional[str]=Field(default=None,max_length=1000)
@app.post("/api/classes/{cid}/assignments")
def assignment_new(cid:str,b:AssignmentIn,request:Request):
    u=auth(request)
    if b.due_date:parse_date(b.due_date)
    with conn() as c:
        if not c.execute("SELECT 1 FROM classes WHERE id=? AND teacher_id=?",(cid,u["id"])).fetchone():raise HTTPException(403,"Sem permissão.")
        aid=str(uuid.uuid4());c.execute("INSERT INTO assignments VALUES(?,?,?,?,?,?,?,?)",(aid,cid,u["id"],b.content_key,b.content_type,b.due_date,b.instructions,now_iso()))
        for s in c.execute("SELECT student_id FROM memberships WHERE class_id=?",(cid,)).fetchall():c.execute("INSERT OR IGNORE INTO assignment_progress(assignment_id,student_id) VALUES(?,?)",(aid,s["student_id"]))
    return {"id":aid}
@app.get("/api/assignments")
def assignments(request:Request):
    u=auth(request)
    with conn() as c:
        if u["role"]=="aluno":r=c.execute("SELECT a.*,c.name class_name,p.status,p.score FROM assignment_progress p JOIN assignments a ON a.id=p.assignment_id JOIN classes c ON c.id=a.class_id WHERE p.student_id=? ORDER BY a.created_at DESC",(u["id"],)).fetchall()
        else:r=c.execute("SELECT a.*,c.name class_name FROM assignments a JOIN classes c ON c.id=a.class_id WHERE a.teacher_id=? ORDER BY a.created_at DESC",(u["id"],)).fetchall()
    return {"items":[dict(x) for x in r]}

class SettingsIn(BaseModel):
    theme:Optional[str]=None;tips:Optional[bool]=None;goal_alerts:Optional[bool]=None;weekly_email:Optional[bool]=None;chart_type:Optional[str]=None
@app.put("/api/settings")
def settings(b:SettingsIn,request:Request):
    u=auth(request)
    with conn() as c:
        cur=dict(c.execute("SELECT * FROM user_settings WHERE user_id=?",(u["id"],)).fetchone())
        v={"theme":b.theme if b.theme in ("dark","light") else cur["theme"],"tips":int(b.tips) if b.tips is not None else cur["tips"],"goal_alerts":int(b.goal_alerts) if b.goal_alerts is not None else cur["goal_alerts"],"weekly_email":int(b.weekly_email) if b.weekly_email is not None else cur["weekly_email"],"chart_type":b.chart_type if b.chart_type in ("line","bar","pie") else (cur.get("chart_type") or "line")}
        c.execute("UPDATE user_settings SET theme=?,tips=?,goal_alerts=?,weekly_email=?,chart_type=? WHERE user_id=?",(v["theme"],v["tips"],v["goal_alerts"],v["weekly_email"],v["chart_type"],u["id"]))
    return {"status":"ok","settings":v}
class ProfileIn(BaseModel):
    name:str=Field(min_length=2,max_length=100)
@app.put("/api/profile")
def profile(b:ProfileIn,request:Request):
    u=auth(request)
    with conn() as c:c.execute("UPDATE users SET name=? WHERE id=?",(b.name.strip(),u["id"]))
    return {"status":"ok","name":b.name.strip()}
class ShareIn(BaseModel):
    enabled:bool
@app.put("/api/classes/{cid}/share")
def class_share(cid:str,b:ShareIn,request:Request):
    u=auth(request)
    if u["role"]!="aluno":raise HTTPException(403,"Configuração disponível para alunos.")
    with conn() as c:
        cur=c.execute("UPDATE memberships SET share_financial=? WHERE class_id=? AND student_id=?",(int(b.enabled),cid,u["id"]))
        if cur.rowcount==0:raise HTTPException(404,"Vínculo não encontrado.")
    return {"status":"ok"}

@app.get("/api/health")
def health():
    return {
        "status":"ok",
        "platform":"vercel" if IS_VERCEL else "local",
        "storage":"temporary" if IS_VERCEL else "local",
        "persistent":not IS_VERCEL,
        "ai_ready":ai_ready(),
        "email_ready":smtp_ready(),
        "warning":"Na Vercel, SQLite e uploads em /tmp são temporários. Use banco/storage externo para produção." if IS_VERCEL else None
    }

@app.get("/")
def home():return FileResponse(STATIC/"index.html",headers={"Cache-Control":"no-store"})
@app.get("/login.html")
def login_page():return FileResponse(STATIC/"login.html",headers={"Cache-Control":"no-store"})
@app.get("/reset.html")
def reset_page():return FileResponse(STATIC/"reset.html",headers={"Cache-Control":"no-store"})
@app.get("/app.html")
def app_page(request:Request):
    try:auth(request)
    except HTTPException:return FileResponse(STATIC/"login.html",status_code=401,headers={"Cache-Control":"no-store"})
    return FileResponse(STATIC/"app.html",headers={"Cache-Control":"no-store,max-age=0"})
@app.get("/avatar.html")
def avatar_page(request:Request):
    try:auth(request)
    except HTTPException:return FileResponse(STATIC/"login.html",status_code=401,headers={"Cache-Control":"no-store"})
    return FileResponse(STATIC/"avatar.html",headers={"Cache-Control":"no-store,max-age=0"})
@app.get("/terms")
def terms():return FileResponse(STATIC/"terms.html")
@app.get("/privacy")
def privacy():return FileResponse(STATIC/"privacy.html")

from backend_services import register_routes
register_routes(app, conn, auth)

# Serve the original V5 relative asset URLs after all API/page routes.
app.mount("/", StaticFiles(directory=STATIC, html=True), name="original-assets")
