"""FinTrack sobre o Supabase: mesmas rotas /api/* da 0.6.x, com Auth, Data API (RLS) e Storage do Supabase.

Ative com FINTRACK_BACKEND=supabase (run.py). O app.py (SQLite) continua disponível como alternativa.
Sessão: dois cookies HttpOnly com o access token e o refresh token do Supabase Auth. O backend renova o
access token quando expira. Os dados pessoais são lidos e gravados com o token do usuário (RLS sempre ativo);
a chave secreta só é usada depois que uma chamada com o token do usuário confirmou quem ele é.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

import teacher_templates
import app as legacy  # reaproveita validações, IA, e-mail e conteúdo estático da 0.6.x (sem usar o SQLite)
import backend_services
from backend_services import local_today
from email_check import check_email
from supa import AuthSession, Supabase, SupabaseError, jwt_claims

logger = logging.getLogger("fintrack.supabase")
STATIC = legacy.STATIC
MEDIA = Path(__file__).resolve().parent / "media" / "education"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
sb = Supabase(SUPABASE_URL, os.getenv("SUPABASE_PUBLISHABLE_KEY", ""), os.getenv("SUPABASE_SECRET_KEY") or None)

AT_COOKIE, RT_COOKIE, PKCE_COOKIE = "ft_at", "ft_rt", "ft_pkce"
REFRESH_DAYS = 30
ONBOARDING_URL = "/login.html?google=completar&t=sessao"
LOGIN_FAILED = "E-mail ou senha incorretos. Se você criou a conta com o Google, use “Continuar com Google”."


def cookie_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "0") == "1"


def app_base() -> str:
    return os.getenv("APP_BASE_URL", "http://127.0.0.1:8010").rstrip("/")


def google_ready() -> bool:
    return os.getenv("FINTRACK_GOOGLE_ENABLED", "0") == "1" and bool(SUPABASE_URL)


# ===================== app, erros e cabeçalhos =====================
def _startup():
    if sb.secret_key:
        try:
            sb.rpc("service_set_email_ready", {"p_ready": legacy.smtp_ready()}, service=True)
        except SupabaseError:
            logger.warning("Não foi possível sincronizar email_delivery_ready")
    if os.getenv("FINTRACK_DISABLE_WORKER") != "1":
        threading.Thread(target=_worker, daemon=True).start()


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    _startup()
    try:
        yield
    finally:
        _stop.set()


app = FastAPI(title="FinTrack (Supabase)", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return await legacy.validation_error(request, exc)


@app.exception_handler(SupabaseError)
async def supabase_error(request: Request, exc: SupabaseError):
    status, detail = translate(exc)
    if status >= 500:
        logger.warning("Supabase %s %s: %s %s", request.method, request.url.path, exc.status, exc.code)
    return JSONResponse(status_code=status, content={"detail": detail})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Erro inesperado em %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erro interno. Tente novamente em instantes."})


def translate(e: SupabaseError) -> tuple[int, str]:
    """Converte erros do Supabase em respostas em português, sem vazar detalhes técnicos."""
    code, msg = e.code, e.message or ""
    if code.startswith("FT"):          # erros nossos (private.http_error): já estão em português
        return e.status, msg
    if code in ("PGRST301", "PGRST302", "bad_jwt", "session_not_found", "refresh_token_not_found", "refresh_token_already_used") or e.status == 401:
        return 401, "Sessão expirada."
    table = {
        "23505": (409, "Esse registro já existe."), "23503": (422, "Referência inválida."),
        "23514": (422, "Confira os valores informados."), "23502": (422, "Preencha todos os campos obrigatórios."),
        "22P02": (422, "Dado em formato inválido."), "22007": (422, "Data inválida."), "22008": (422, "Data inválida."),
        "42501": (403, "Sem permissão."), "PGRST116": (404, "Registro não encontrado."),
        "invalid_credentials": (401, LOGIN_FAILED), "email_not_confirmed": (403, "Confirme seu e-mail pelo link que enviamos antes de entrar."),
        "user_already_exists": (400, "Não foi possível criar a conta com esses dados."), "email_exists": (400, "Não foi possível criar a conta com esses dados."),
        "weak_password": (422, "Use pelo menos 8 caracteres, com pelo menos uma letra e um número."),
        "over_request_rate_limit": (429, "Muitas tentativas. Aguarde um pouco e tente novamente."),
        "over_email_send_rate_limit": (429, "Muitos e-mails enviados. Aguarde um pouco e tente novamente."),
        "otp_expired": (400, "Este link expirou ou já foi utilizado."), "flow_state_not_found": (400, "O login com Google expirou. Tente de novo."),
        "flow_state_expired": (400, "O login com Google expirou. Tente de novo."),
    }
    if code in table:
        return table[code]
    if e.status == 429:
        return 429, "Muitas tentativas. Aguarde um pouco e tente novamente."
    if e.status >= 500 or e.status == 503:
        return 503, "O banco de dados não respondeu. Tente novamente em instantes."
    return (e.status if 400 <= e.status < 500 else 400), "Não foi possível concluir a operação."


@app.middleware("http")
async def security_and_session(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Solicitação de outra origem bloqueada."}, status_code=403)
        origin, host = request.headers.get("origin"), request.headers.get("x-forwarded-host") or request.headers.get("host")
        if origin and host and origin.split("://", 1)[-1].lower() != host.lower():
            return JSONResponse({"detail": "Origem não autorizada."}, status_code=403)
    request.state.new_session = None
    request.state.clear_session = False
    response = await call_next(request)
    if request.state.new_session is not None:
        set_session_cookies(response, request.state.new_session)
    elif request.state.clear_session:
        clear_session_cookies(response)
    media = "'self'" + (f" {SUPABASE_URL}" if SUPABASE_URL else "")
    for k, v in {
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=()", "Cross-Origin-Opener-Policy": "same-origin",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/ https://cdn.jsdelivr.net/npm/; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/; "
                                   "font-src 'self' https://fonts.gstatic.com data: https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/; img-src 'self' data: blob: https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/; "
                                   f"media-src {media} https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/ https://vlibras.gov.br; connect-src 'self' https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/ https://cdn.jsdelivr.net/npm/ https://tessdata.projectnaptha.com; worker-src 'self' blob:; frame-src https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    }.items():
        response.headers.setdefault(k, v)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if (request.headers.get("x-forwarded-proto") or request.url.scheme).lower() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ===================== limite de tentativas (em memória, uma instância) =====================
_RL: dict[str, list[float]] = {}
_RL_LOCK = threading.Lock()


def rate_limit(key: str, limit: int, window: int):
    now = time.monotonic()
    with _RL_LOCK:
        hits = [t for t in _RL.get(key, []) if now - t < window]
        if len(hits) >= limit:
            raise HTTPException(429, "Muitas tentativas. Aguarde um pouco e tente novamente.",
                                headers={"Retry-After": str(max(1, int(window - (now - hits[0]))))})
        hits.append(now)
        _RL[key] = hits
        if len(_RL) > 5000:
            for k in [k for k, v in _RL.items() if not v or now - v[-1] > 86400][:2500]:
                _RL.pop(k, None)


def client_key(request: Request) -> str:
    return (request.client.host if request.client else "unknown")[:80]


# ===================== sessão =====================
def set_session_cookies(response: Response, s: AuthSession):
    max_age = max(60, s.expires_at - int(time.time()))
    response.set_cookie(AT_COOKIE, s.access_token, httponly=True, samesite="lax", secure=cookie_secure(), max_age=max_age, path="/")
    response.set_cookie(RT_COOKIE, s.refresh_token, httponly=True, samesite="lax", secure=cookie_secure(),
                        max_age=REFRESH_DAYS * 86400, path="/")


def clear_session_cookies(response: Response):
    response.delete_cookie(AT_COOKIE, path="/")
    response.delete_cookie(RT_COOKIE, path="/")


class Sess:
    def __init__(self, token: str):
        self.token = token
        c = jwt_claims(token)
        self.uid: str = c.get("sub", "")
        self.email: str = c.get("email", "")
        self._profile: Optional[dict] = None
        self.verified = False

    def profile(self) -> dict:
        """Lê o perfil com o token: além dos dados, prova que o token é válido (assinatura conferida no Supabase)."""
        if self._profile is None:
            rows = sb.select("profiles", self.token, id=f"eq.{self.uid}", select="*")
            if not rows:
                raise HTTPException(401, "Sessão expirada.")
            self._profile, self.verified = rows[0], True
        return self._profile

    def verify(self) -> str:
        """Confirma o usuário antes de qualquer operação com a chave secreta."""
        self.profile()
        return self.uid


def session(request: Request) -> Sess:
    cached = getattr(request.state, "sess", None)
    if cached:
        return cached
    at, rt = request.cookies.get(AT_COOKIE), request.cookies.get(RT_COOKIE)
    if at and jwt_claims(at).get("exp", 0) > time.time() + 30:
        s = Sess(at)
    elif rt:
        try:
            new = sb.refresh(rt)
        except SupabaseError:
            request.state.clear_session = True
            raise HTTPException(401, "Sessão expirada.")
        request.state.new_session = new
        s = Sess(new.access_token)
    else:
        raise HTTPException(401, "Sessão necessária.")
    if not s.uid:
        raise HTTPException(401, "Sessão expirada.")
    request.state.sess = s
    return s


def start_session(request: Request, auth: AuthSession) -> Sess:
    request.state.new_session = auth
    s = Sess(auth.access_token)
    request.state.sess = s
    return s


def next_page(s: Sess) -> str:
    p = s.profile()
    if not p.get("role"):
        return ONBOARDING_URL
    return "/avatar.html" if p.get("onboarding_status") != "concluido" else "/app.html"


def parse_date(v: Any) -> date:
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        raise HTTPException(422, "Data inválida.")


def clean(v: Optional[str]) -> Optional[str]:
    return " ".join(v.split()) if isinstance(v, str) and v.strip() else None


def one(rows: list, message="Registro não encontrado.") -> dict:
    if not rows:
        raise HTTPException(404, message)
    return rows[0]


# ===================== autenticação =====================
ADULT_ONLY = "O FinTrack é destinado a pessoas com 18 anos ou mais. Confirme sua idade para continuar."


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100); email: str = Field(min_length=3, max_length=320)  # validado por check_email
    password: str = Field(min_length=8, max_length=128); role: str; terms: bool; adult: bool = False


class LoginIn(BaseModel):
    email: EmailStr; password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    # token: token_hash (modelo de e-mail personalizado); access_token: link padrão do Supabase (vem no #fragmento)
    token: Optional[str] = Field(default=None, min_length=6, max_length=200)
    access_token: Optional[str] = Field(default=None, min_length=20, max_length=4000)
    password: str = Field(min_length=8, max_length=128)


class OnboardingIn(BaseModel):
    token: str = ""; name: str = Field(min_length=2, max_length=100); role: str; terms: bool; adult: bool = False


@app.post("/api/auth/register")
def register(b: RegisterIn, request: Request):
    rate_limit("register:" + client_key(request), 5, 3600)
    if b.role not in ("aluno", "professor"):
        raise HTTPException(422, "Perfil inválido.")
    if not b.terms:
        raise HTTPException(422, "Aceite os termos e a política de privacidade.")
    if not b.adult:
        raise HTTPException(422, ADULT_ONLY)
    legacy.validate_password(b.password)
    checked = check_email(b.email)
    if not checked.ok:
        raise HTTPException(422, checked.message)
    try:
        r = sb.sign_up(b.email.lower(), b.password, {"name": " ".join(b.name.split())}, redirect_to=app_base() + "/login.html?confirmado=1")
    except SupabaseError as e:
        if e.status != 429:
            raise
        r = {}
    if not r.get("access_token"):
        # Conta que já existe (ou cadastro repetido): se e-mail e senha conferem e o e-mail já está confirmado, entra direto.
        try:
            s = start_session(request, sb.sign_in(b.email.lower(), b.password))
        except SupabaseError:
            s = None
        if s:
            if not s.profile().get("role"):
                sb.rpc("complete_onboarding", {"p_name": b.name, "p_role": b.role, "p_accept_terms": True,
                                               "p_professor_code": request.headers.get("x-professor-signup-code") or None}, s.token)
                s._profile = None
            return {"status": "ok", "next": next_page(s)}
        # Confirmação de e-mail ligada no Supabase: o perfil é concluído no primeiro login ("Quase lá").
        return {"status": "confirmar", "next": None,
                "message": "Enviamos um link de confirmação para o seu e-mail. Depois de confirmar, entre com seu e-mail e senha."}
    s = start_session(request, AuthSession.from_payload(r))
    out = sb.rpc("complete_onboarding", {"p_name": b.name, "p_role": b.role, "p_accept_terms": True,
                                          "p_professor_code": request.headers.get("x-professor-signup-code") or None}, s.token)
    return {"status": "ok", "next": out["next"]}


class EmailIn(BaseModel):
    email: str = Field(min_length=1, max_length=320)


@app.post("/api/auth/check-email")
def check_email_route(b: EmailIn, request: Request):
    """Aviso imediato na tela de cadastro (formato, domínio, erro de digitação). Não revela se a conta existe."""
    rate_limit("check-email:" + client_key(request), 60, 600)
    r = check_email(b.email)
    return {"ok": r.ok, "message": r.message, "suggestion": r.suggestion}


@app.post("/api/auth/login")
def login(b: LoginIn, request: Request):
    email = b.email.lower()
    rate_limit("login-ip:" + client_key(request), 30, 900)
    rate_limit("login:" + client_key(request) + ":" + hashlib.sha256(email.encode()).hexdigest()[:12], 10, 900)
    s = start_session(request, sb.sign_in(email, b.password))
    return {"status": "ok", "next": next_page(s)}


@app.post("/api/auth/forgot")
def forgot(b: ForgotIn, request: Request):
    rate_limit("forgot:" + client_key(request) + ":" + hashlib.sha256(b.email.lower().encode()).hexdigest()[:12], 5, 3600)
    try:
        sb.recover(b.email.lower(), app_base() + "/reset.html")
    except SupabaseError as e:
        if e.status == 429:
            raise
        logger.warning("Falha ao pedir recuperação de senha (%s)", e.code)
    return {"email_configured": True,
            "message": "Se houver uma conta com este e-mail, enviaremos um link de redefinição. Confira também a caixa de spam."}


@app.post("/api/auth/reset")
def reset_password(b: ResetIn, request: Request):
    rate_limit("reset:" + client_key(request), 10, 3600)
    legacy.validate_password(b.password)
    if b.token:
        access = sb.verify_recovery(b.token).access_token
    elif b.access_token:
        access = b.access_token   # o Supabase Auth valida o token ao trocar a senha
    else:
        raise HTTPException(400, "Este link expirou ou já foi utilizado.")
    sb.update_user(access, {"password": b.password})
    sb.sign_out(access, scope="global")   # encerra as outras sessões
    request.state.clear_session = True
    return {"status": "ok"}


@app.post("/api/auth/logout")
def logout(request: Request):
    at = request.cookies.get(AT_COOKIE)
    if at:
        sb.sign_out(at)
    request.state.clear_session = True
    return {"status": "ok"}


@app.get("/api/auth/google/start")
def google_start(request: Request):
    if not google_ready():
        return RedirectResponse("/login.html?google_error=indisponivel", status_code=303)
    rate_limit("google-start:" + client_key(request), 30, 600)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = RedirectResponse(sb.authorize_url("google", app_base() + "/api/auth/google/callback", challenge), status_code=303)
    r.set_cookie(PKCE_COOKIE, verifier, httponly=True, samesite="lax", secure=cookie_secure(), max_age=600, path="/api/auth/google")
    return r


@app.get("/api/auth/google/callback")
def google_callback(request: Request, code: str = "", error: str = ""):
    def fail(reason):
        r = RedirectResponse("/login.html?google_error=" + reason, status_code=303)
        r.delete_cookie(PKCE_COOKIE, path="/api/auth/google")
        return r
    if error:
        return fail("cancelado" if error == "access_denied" else "falha")
    verifier = request.cookies.get(PKCE_COOKIE, "")
    if not code or not verifier:
        return fail("estado")
    try:
        auth = sb.exchange_code(code, verifier)
    except SupabaseError:
        return fail("falha")
    s = start_session(request, auth)
    r = RedirectResponse(next_page(s), status_code=303)
    r.delete_cookie(PKCE_COOKIE, path="/api/auth/google")
    return r


@app.get("/api/auth/google/pending")
def onboarding_info(request: Request, t: str = ""):
    s = session(request)
    p = s.profile()
    if p.get("role"):
        raise HTTPException(409, "O perfil desta conta já foi definido. Entre normalmente.")
    return {"email": s.email, "name": p.get("name") or ""}


@app.post("/api/auth/google/complete")
def onboarding_complete(b: OnboardingIn, request: Request):
    s = session(request)
    if b.role not in ("aluno", "professor"):
        raise HTTPException(422, "Perfil inválido.")
    if not b.terms:
        raise HTTPException(422, "Aceite os termos e a política de privacidade.")
    if not b.adult:
        raise HTTPException(422, ADULT_ONLY)
    out = sb.rpc("complete_onboarding", {"p_name": b.name, "p_role": b.role, "p_accept_terms": True,
                                          "p_professor_code": request.headers.get("x-professor-signup-code") or None}, s.token)
    return {"status": "ok", "next": out["next"]}


def avatar_view(row: Optional[dict]):
    return {"kind": row["kind"], "preset": row["preset"], "bg": row["bg"], "v": row["updated_at"]} if row else None


@app.get("/api/auth/me")
def me(request: Request):
    s = session(request)
    p = s.profile()
    settings = one(sb.select("user_settings", s.token, user_id=f"eq.{s.uid}", select="theme,tips,goal_alerts,weekly_email,chart_type"), "Sessão expirada.")
    av = sb.select("user_avatars", s.token, user_id=f"eq.{s.uid}", select="kind,preset,bg,updated_at")
    user = sb.get_user(s.token)
    providers = {i.get("provider") for i in user.get("identities") or []}
    return {"id": s.uid, "name": p["name"], "email": user.get("email") or s.email, "role": p.get("role"),
            "settings": settings, "avatar": avatar_view(av[0] if av else None),
            "email_verified": bool(user.get("email_confirmed_at")), "has_password": "email" in providers,
            "google_linked": "google" in providers}


# ===================== avatar =====================
class AvatarPresetIn(BaseModel):
    preset: str; bg: str


@app.get("/api/avatar/options")
def avatar_options(request: Request):
    session(request)
    return {"presets": [{"key": k, "label": v} for k, v in legacy.AVATAR_PRESETS.items()], "backgrounds": legacy.AVATAR_BGS}


def _drop_photo(path: Optional[str]):
    if path:
        try:
            sb.remove("avatars", [path])
        except SupabaseError:
            logger.warning("Não foi possível apagar a foto antiga do avatar")


@app.put("/api/avatar/preset")
def avatar_set_preset(b: AvatarPresetIn, request: Request):
    s = session(request)
    if b.preset not in legacy.AVATAR_PRESETS or b.bg not in legacy.AVATAR_BGS:
        raise HTTPException(422, "Avatar inválido.")
    old = sb.select("user_avatars", s.token, user_id=f"eq.{s.uid}", select="photo_path")
    values = {"kind": "preset", "preset": b.preset, "bg": b.bg}
    rows = sb.update("user_avatars", values, s.token, user_id=f"eq.{s.uid}") or sb.insert("user_avatars", {"user_id": s.uid, **values}, s.token)
    if old:
        _drop_photo(old[0].get("photo_path"))
    return {"avatar": avatar_view(rows[0])}


@app.post("/api/avatar/photo")
async def avatar_upload(request: Request, image: UploadFile = File(...)):
    s = session(request)
    uid = s.verify()
    data = await image.read(legacy.MAX_AVATAR_BYTES + 1)
    if len(data) > legacy.MAX_AVATAR_BYTES:
        raise HTTPException(422, "A foto deve ter no máximo 600 KB. Recorte novamente.")
    mime, ext = legacy.validate_image_bytes(data)   # tipo pelo conteúdo, nunca pelo cabeçalho
    path = f"{uid}/{uuid.uuid4().hex[:12]}{ext}"
    old = sb.select("user_avatars", s.token, user_id=f"eq.{uid}", select="photo_path,bg")
    sb.upload("avatars", path, data, mime)
    values = {"kind": "photo", "photo_path": path, "photo_mime": mime}
    rows = sb.update("user_avatars", values, service=True, user_id=f"eq.{uid}") or \
        sb.insert("user_avatars", {"user_id": uid, "preset": "coruja", "bg": legacy.AVATAR_BGS[0], **values}, service=True)
    if old:
        _drop_photo(old[0].get("photo_path"))
    return {"avatar": avatar_view(rows[0])}


@app.post("/api/avatar/skip")
def avatar_skip(request: Request):
    s = session(request)
    sb.rpc("skip_avatar", {}, s.token)
    av = sb.select("user_avatars", s.token, user_id=f"eq.{s.uid}", select="kind,preset,bg,updated_at")
    return {"avatar": avatar_view(av[0] if av else None)}


@app.get("/api/avatar/{uid}/photo")
def avatar_photo(uid: str, request: Request):
    s = session(request)
    rows = sb.select("user_avatars", s.token, user_id=f"eq.{uid}", select="kind,photo_path,photo_mime")  # RLS: dono ou mesma turma
    if not rows or rows[0]["kind"] != "photo":
        raise HTTPException(404, "Sem foto.")
    try:
        data = sb.download("avatars", rows[0]["photo_path"])
    except SupabaseError:
        raise HTTPException(404, "Sem foto.")
    return Response(data, media_type=rows[0]["photo_mime"], headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


# ===================== categorias e transações =====================
class CatIn(BaseModel):
    type: str; name: str = Field(min_length=2, max_length=50)


def categories_of(s: Sess) -> list:
    if not hasattr(s, "_cats"):
        s._cats = sb.select("categories", s.token, select="id,type,name,user_id,active", order="position.asc,name.asc")
    return s._cats


def category_id(s: Sess, type_: str, name: str) -> str:
    if type_ not in ("receita", "despesa"):
        raise HTTPException(422, "Tipo inválido.")
    for c in categories_of(s):
        if c["type"] == type_ and c["name"] == name and c["active"]:
            return c["id"]
    raise HTTPException(422, "Categoria incompatível com o tipo selecionado.")


@app.get("/api/categories")
def categories(request: Request):
    s = session(request)
    cats = categories_of(s)
    return {"receita": [c["name"] for c in cats if c["user_id"] is None and c["type"] == "receita"],
            "despesa": [c["name"] for c in cats if c["user_id"] is None and c["type"] == "despesa"],
            "personalizadas": [{"id": c["id"], "type": c["type"], "name": c["name"]} for c in cats if c["user_id"] and c["active"]]}


@app.post("/api/categories")
def add_category(b: CatIn, request: Request):
    s = session(request)
    if b.type not in ("receita", "despesa"):
        raise HTTPException(422, "Tipo inválido.")
    try:
        row = sb.insert("categories", {"user_id": s.uid, "type": b.type, "name": " ".join(b.name.split())}, s.token)[0]
    except SupabaseError as e:
        if e.code == "23505":
            raise HTTPException(409, "Essa categoria já existe.")
        raise
    return {"id": row["id"], "type": row["type"], "name": row["name"]}


class TxIn(BaseModel):
    type: str; category: str; description: str = Field(min_length=1, max_length=160)
    amount: Any; date: str; note: Optional[str] = Field(default=None, max_length=1000); recurrence: Optional[dict] = None


@app.post("/api/transactions")
def add_tx(b: TxIn, request: Request):
    s = session(request)
    cid, value, d = category_id(s, b.type, b.category), legacy.cents(b.amount), parse_date(b.date)
    if b.recurrence and b.recurrence.get("enabled"):
        start = parse_date(b.recurrence.get("start_date") or b.date)
        end = parse_date(b.recurrence["end_date"]) if b.recurrence.get("end_date") else None
        tid = sb.rpc("create_recurring_transaction", {
            "p_type": b.type, "p_category_id": cid, "p_description": b.description.strip(), "p_amount_cents": value,
            "p_start_date": start.isoformat(), "p_frequency": b.recurrence.get("frequency"),
            "p_end_date": end.isoformat() if end else None, "p_note": b.note}, s.token)
        return {"status": "ok", "id": tid}
    row = sb.insert("transactions", {"user_id": s.uid, "type": b.type, "category_id": cid, "description": b.description.strip(),
                                     "amount_cents": value, "occurred_on": d.isoformat(), "note": b.note}, s.token)[0]
    return {"status": "ok", "id": row["id"]}


@app.get("/api/transactions")
def list_tx(request: Request, type: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
            q: Optional[str] = None, sort: str = "date_desc", page: int = 1, page_size: int = 20):
    s = session(request)
    return sb.rpc("transaction_page", {"p_type": type, "p_start": parse_date(start).isoformat() if start else None,
                                        "p_end": parse_date(end).isoformat() if end else None, "p_q": q, "p_sort": sort,
                                        "p_page": page, "p_page_size": page_size}, s.token)


@app.put("/api/transactions/{tid}")
def edit_tx(tid: str, b: TxIn, request: Request, scope: str = "single"):
    s = session(request)
    if scope not in ("single", "future"):
        raise HTTPException(422, "Escopo inválido.")
    sb.rpc("update_transaction_scoped", {"p_transaction_id": tid, "p_scope": scope, "p_type": b.type,
                                         "p_category_id": category_id(s, b.type, b.category), "p_description": b.description.strip(),
                                         "p_amount_cents": legacy.cents(b.amount), "p_occurred_on": parse_date(b.date).isoformat(),
                                         "p_note": b.note}, s.token)
    return {"status": "ok", "scope": scope}


@app.delete("/api/transactions/{tid}")
def delete_tx(tid: str, request: Request, scope: str = "single"):
    s = session(request)
    if scope not in ("single", "future"):
        raise HTTPException(422, "Escopo inválido.")
    n = sb.rpc("delete_transaction_scoped", {"p_transaction_id": tid, "p_scope": scope}, s.token)
    return {"status": "ok", "deleted": n, "scope": scope}


@app.get("/api/dashboard")
def dashboard(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    s = session(request)
    d = sb.rpc("dashboard", {"p_start": parse_date(start).isoformat() if start else None,
                             "p_end": parse_date(end).isoformat() if end else None}, s.token)
    for r in d.get("recent", []):
        r["date"] = r.pop("occurred_on", None)
    return d


# ===================== metas =====================
class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=100); description: Optional[str] = Field(default=None, max_length=600)
    target: Any; deadline: str


class AmountIn(BaseModel):
    amount: Any


@app.get("/api/goals")
def get_goals(request: Request):
    s = session(request)
    items = sb.select("goal_overview", s.token, select="*", order="status.asc,deadline.asc,created_at.desc")
    bal = sb.rpc("balance_summary", {}, s.token)
    return {"items": items, **bal}


@app.post("/api/goals")
def new_goal(b: GoalIn, request: Request):
    s = session(request)
    row = sb.insert("goals", {"user_id": s.uid, "title": b.title.strip(), "description": b.description,
                              "target_cents": legacy.cents(b.target), "deadline": parse_date(b.deadline).isoformat()}, s.token)[0]
    return {"status": "ok", "id": row["id"]}


@app.put("/api/goals/{gid}")
def edit_goal(gid: str, b: GoalIn, request: Request):
    s = session(request)
    rows = sb.update("goals", {"title": b.title.strip(), "description": b.description, "target_cents": legacy.cents(b.target),
                               "deadline": parse_date(b.deadline).isoformat()}, s.token, id=f"eq.{gid}")
    if not rows:
        one(sb.select("goals", s.token, id=f"eq.{gid}", select="id"))
        raise HTTPException(422, "Somente metas em andamento podem ser editadas.")
    return {"status": "ok"}


@app.post("/api/goals/{gid}/reserve")
def goal_reserve(gid: str, b: AmountIn, request: Request):
    s = session(request)
    sb.rpc("reserve_goal", {"p_goal_id": gid, "p_amount_cents": legacy.cents(b.amount),
                            "p_idempotency_key": request.headers.get("idempotency-key")}, s.token)
    return {"status": "ok"}


@app.post("/api/goals/{gid}/withdraw")
def goal_withdraw(gid: str, b: AmountIn, request: Request):
    s = session(request)
    sb.rpc("withdraw_goal", {"p_goal_id": gid, "p_amount_cents": legacy.cents(b.amount),
                             "p_idempotency_key": request.headers.get("idempotency-key")}, s.token)
    return {"status": "ok"}


@app.post("/api/goals/{gid}/complete")
def goal_complete(gid: str, request: Request):
    return sb.rpc("complete_goal", {"p_goal_id": gid}, session(request).token)


@app.delete("/api/goals/{gid}")
def goal_delete(gid: str, request: Request):
    return sb.rpc("delete_goal", {"p_goal_id": gid}, session(request).token)


# ===================== educação e vídeos =====================
class ProgressIn(BaseModel):
    status: str; score: Optional[int] = None; answers: Optional[dict] = None


class CheckIn(BaseModel):
    i: int; answer: Any = None


class SubmitIn(BaseModel):
    answers: list


def lesson_catalog(s: Sess) -> dict:
    rows = sb.select("education_lessons", s.token, select="id,key,title,position,education_modules(key,title,level,position)")
    out = {}
    for r in sorted(rows, key=lambda r: (r["education_modules"]["position"], r["position"])):
        m = r["education_modules"]
        out[f'{m["key"]}:{r["key"]}'] = {"id": r["id"], "module": m["key"], "topic": r["key"], "title": r["title"],
                                         "module_title": m["title"], "level": m["level"]}
    return out


@app.get("/api/education")
def get_education(request: Request):
    s = session(request)
    outline = sb.rpc("education_outline", {}, s.token)
    catalog = lesson_catalog(s)
    by_id = {v["id"]: k for k, v in catalog.items()}
    contents = {c["lesson_id"]: c for c in sb.select("education_lesson_contents", s.token, select="*")}       # RLS: só liberadas
    acts: dict[str, list] = {}
    for a in sb.select("education_activities", s.token, select="lesson_id,position,kind,prompt,public_data", order="position.asc"):
        acts.setdefault(a["lesson_id"], []).append({"t": a["kind"], "q": a["prompt"], **a["public_data"]})
    modules = []
    for m in outline["modules"]:
        topics = []
        for t in m["topics"]:
            lid = catalog[f'{m["key"]}:{t["key"]}']["id"]
            c = contents.get(lid)
            if m["unlocked"] and c:
                topics.append({"key": t["key"], "title": t["title"], "goal": c["goal"], "explain": c["explanation"],
                               "example": c["example"], "summary": c["summary"], "sources": c["sources"],
                               "reviewed": str(c["reviewed_on"])[:7], "acts": acts.get(lid, [])})
            else:
                topics.append({"key": t["key"], "title": t["title"], "acts": [], "activity_count": t["activity_count"]})
        intro = m.get("intro")
        modules.append({"key": m["key"], "level": m["level"], "level_name": m["level_name"], "title": m["title"],
                        "description": m["description"], "topics": topics,
                        "intro": {"duration": float(intro["duration"]), "version": intro["version"], "watched": float(intro["watched"]),
                                  "completed": intro["completed"]} if intro else None})
    progress = []
    for p in sb.select("education_progress", s.token, select="*"):
        key = by_id.get(p["lesson_id"])
        if key:
            mk, tk = key.split(":", 1)
            progress.append({"module_key": mk, "topic_key": tk, "status": p["status"], "score": p["best_score"],
                             "answers_json": json.dumps({"attempts": p["attempts"], "last_score": p["last_score"]}),
                             "updated_at": p["updated_at"]})
    return {"modules": modules, "progress": progress, "pass": outline["pass"]}


@app.put("/api/education/{module}/{topic}")
def set_progress(module: str, topic: str, b: ProgressIn, request: Request):
    if b.status != "em_andamento":
        raise HTTPException(400, "Conclua as atividades da aula para registrar a conclusão.")
    sb.rpc("start_lesson", {"p_module_key": module, "p_lesson_key": topic}, session(request).token)
    return {"status": "ok"}


@app.post("/api/education/{module}/{topic}/check")
def check_item(module: str, topic: str, b: CheckIn, request: Request):
    return sb.rpc("check_activity", {"p_module_key": module, "p_lesson_key": topic, "p_index": b.i, "p_answer": b.answer},
                  session(request).token)


@app.post("/api/education/{module}/{topic}/submit")
def submit_lesson(module: str, topic: str, b: SubmitIn, request: Request):
    return sb.rpc("submit_lesson", {"p_module_key": module, "p_lesson_key": topic, "p_answers": b.answers}, session(request).token)


class Tick(BaseModel):
    token: str = Field(min_length=20, max_length=100); position: float = Field(ge=0, allow_inf_nan=False)


@app.post("/api/intro/{module}/start")
def intro_start(module: str, request: Request):
    r = sb.rpc("video_start", {"p_module_key": module}, session(request).token)
    return {"duration": float(r["duration"]), "version": r["version"], "watched": float(r["watched"]),
            "completed": r["completed"], "token": r["token"]}


@app.post("/api/intro/{module}/tick")
def intro_tick(module: str, b: Tick, request: Request):
    r = sb.rpc("video_tick", {"p_module_key": module, "p_token": b.token, "p_position": b.position}, session(request).token)
    return {"watched": float(r["watched"]), "completed": r["completed"], "accepted": r["accepted"]}


@app.get("/api/intro/{module}/media")
def intro_media(module: str, request: Request):
    s = session(request)
    rows = sb.select("education_video_assets", s.token, select="storage_bucket,storage_path,education_modules!inner(key)",
                     **{"education_modules.key": f"eq.{module}", "status": "eq.publicado"})
    asset = one(rows, "Vídeo não encontrado.")
    try:
        return RedirectResponse(sb.signed_url(asset["storage_bucket"], asset["storage_path"], 600), status_code=307)
    except SupabaseError:
        local = MEDIA / f"{module}.mp4"
        if local.is_file():   # vídeo ainda não enviado ao Storage: usa o arquivo do pacote
            s.verify()
            return FileResponse(local, media_type="video/mp4", headers={"Cache-Control": "private, no-store"})
        raise HTTPException(404, "Vídeo indisponível no momento.")


@app.get("/api/lessons")
def lessons(request: Request):
    return {"items": [{"key": k, **{x: v[x] for x in ("module", "topic", "title", "module_title", "level")}}
                      for k, v in lesson_catalog(session(request)).items()]}


# ===================== FinBot =====================
class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000); request_key: str = Field(min_length=8, max_length=100)


@app.get("/api/ai/conversations")
def conversations(request: Request):
    return {"items": sb.select("ai_conversations", session(request).token, select="*", order="updated_at.desc")}


@app.post("/api/ai/conversations")
def conversation_new(request: Request):
    s = session(request)
    row = sb.insert("ai_conversations", {"user_id": s.uid}, s.token)[0]
    return {"id": row["id"], "title": row["title"]}


@app.get("/api/ai/conversations/{cid}")
def conversation_get(cid: str, request: Request):
    s = session(request)
    one(sb.select("ai_conversations", s.token, id=f"eq.{cid}", select="id"))
    return {"messages": sb.select("ai_messages", s.token, conversation_id=f"eq.{cid}", select="*", order="created_at.asc")}


@app.patch("/api/ai/conversations/{cid}")
def conversation_rename(cid: str, b: RenameIn, request: Request):
    one(sb.update("ai_conversations", {"title": b.title.strip()}, session(request).token, id=f"eq.{cid}"))
    return {"status": "ok"}


@app.delete("/api/ai/conversations/{cid}")
def conversation_delete(cid: str, request: Request):
    one(sb.delete("ai_conversations", session(request).token, id=f"eq.{cid}"))
    return {"status": "ok"}


@app.get("/api/ai/status")
def ai_status(request: Request):
    session(request)
    return {"configured": legacy.ai_ready(), "provider": legacy.ai_provider_name(),
            "model": legacy.openai_model() if os.getenv("OPENAI_API_KEY") else (os.getenv("AI_MODEL") or None)}


SYSTEM_PROMPT = """Você é o FinBot, assistente de educação e organização financeira do FinTrack.
Responda em português brasileiro, de forma clara, prática e adequada a estudantes e professores.
Nunca peça senhas bancárias, códigos de autenticação ou credenciais. Nunca faça transferências nem afirme que movimentou dinheiro.
Não acesse nem invente dados de outros usuários. Não invente renda, hábitos, transações ou metas.
Quando houver dados observados, separe claramente o que veio dos registros do usuário do que é sugestão educativa.
Sobre investimentos, explique riscos, liquidez e incerteza; nunca prometa lucro ou retorno garantido.
Você pode orientar e explicar, mas alterações financeiras exigem ações explícitas do usuário na interface."""


@app.post("/api/ai/conversations/{cid}/messages")
def message_send(cid: str, b: MessageIn, request: Request):
    s = session(request)
    rate_limit("ai-message:" + s.uid, 30, 3600)
    conv = one(sb.select("ai_conversations", s.token, id=f"eq.{cid}", select="id,title"))  # prova de posse (RLS)
    text, assistant_key = b.content.strip(), "assistant:" + b.request_key
    old = sb.select("ai_messages", s.token, request_key=f"eq.{b.request_key}", select="*")
    if old and (old[0]["content"] != text or old[0]["conversation_id"] != cid):
        raise HTTPException(409, "Esta tentativa já foi usada para outra mensagem.")
    answered = sb.select("ai_messages", s.token, request_key=f"eq.{assistant_key}", conversation_id=f"eq.{cid}", select="*")
    if answered:
        return {"duplicate": True, "assistant_message": answered[0]}
    if not old:
        sb.insert("ai_messages", {"conversation_id": cid, "user_id": s.uid, "content": text, "request_key": b.request_key}, s.token)
    hist = sb.select("ai_messages", s.token, conversation_id=f"eq.{cid}", select="role,content", order="created_at.desc", limit="20")[::-1]
    if not legacy.ai_ready():
        raise HTTPException(503, "A IA ainda não está configurada no servidor. Sua mensagem foi salva.")
    try:
        answer = legacy.call_ai([{"role": "system", "content": SYSTEM_PROMPT}] + hist)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception:
        raise HTTPException(502, "A IA não respondeu. Tente novamente.")
    try:
        msg = sb.insert("ai_messages", {"conversation_id": cid, "user_id": s.uid, "role": "assistant", "content": answer,
                                        "request_key": assistant_key}, service=True)[0]   # posse já provada acima
    except SupabaseError as e:
        if e.code == "23505":
            return {"duplicate": True, "assistant_message": one(sb.select("ai_messages", s.token, request_key=f"eq.{assistant_key}", select="*"))}
        raise
    if conv["title"] == "Nova conversa":
        sb.update("ai_conversations", {"title": text[:60]}, s.token, id=f"eq.{cid}")
    return {"assistant_message": {k: msg[k] for k in ("id", "role", "content", "request_key", "created_at")}}


@app.post("/api/ai/analyze-spending")
def analyze_spending(request: Request):
    s = session(request)
    rate_limit("ai-analysis:" + s.uid, 12, 3600)
    end = local_today(); start = end - timedelta(days=90)
    r = sb.rpc("spending_aggregates", {"p_start": start.isoformat(), "p_end": end.isoformat()}, s.token)
    period = {"start": start.isoformat(), "end": end.isoformat()}
    if not r:
        return {"has_data": False, "message": "Ainda não há transações no período para analisar.", "period": period}
    if not legacy.ai_ready():
        raise HTTPException(503, "Há dados para análise, mas a IA ainda não está configurada no servidor.")
    try:
        answer = legacy.call_ai([
            {"role": "system", "content": "Você é um educador financeiro. Separe dados observados de sugestões e informe limitações. Não invente renda, hábitos ou registros."},
            {"role": "user", "content": f"Período: {period['start']} a {period['end']}. Analise apenas estes agregados, sem inventar hábitos ou renda: " + json.dumps(r, ensure_ascii=False)}])
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception:
        raise HTTPException(502, "Não foi possível concluir a análise com IA agora.")
    return {"has_data": True, "period": period, "observed": r, "analysis": answer}


# ===================== comprovantes =====================
@app.post("/api/receipts/upload")
async def receipt_upload(request: Request, image: UploadFile = File(...)):
    s = session(request)
    rate_limit("receipt-upload:" + s.uid, 20, 3600)
    uid = s.verify()
    content = await image.read(legacy.MAX_RECEIPT_BYTES + 1)
    if not content:
        raise HTTPException(422, "A imagem está vazia.")
    if len(content) > legacy.MAX_RECEIPT_BYTES:
        raise HTTPException(422, "A imagem deve ter no máximo 5 MB.")
    mime, ext = legacy.validate_image_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    dup = sb.select("receipts", s.token, sha256=f"eq.{digest}", select="id,mime,original_name")
    if dup:
        return {"id": dup[0]["id"], "name": dup[0]["original_name"], "mime": dup[0]["mime"], "duplicate": True,
                "warning": "Este comprovante já foi enviado anteriormente."}
    rid = str(uuid.uuid4()); path = f"{uid}/{rid}{ext}"
    sb.upload("receipts", path, content, mime)
    try:
        sb.insert("receipts", {"id": rid, "user_id": uid, "storage_path": path, "mime": mime,
                               "original_name": (image.filename or "comprovante")[:200], "size_bytes": len(content), "sha256": digest}, service=True)
    except SupabaseError:
        sb.remove("receipts", [path])
        raise
    return {"id": rid, "name": image.filename, "mime": mime, "duplicate": False}


@app.get("/api/receipts/{rid}/file")
def receipt_file(rid: str, request: Request):
    r = one(sb.select("receipts", session(request).token, id=f"eq.{rid}", select="storage_path,mime"))
    return Response(sb.download("receipts", r["storage_path"]), media_type=r["mime"],
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/receipts/{rid}/analyze")
def receipt_analyze(rid: str, request: Request):
    s = session(request)
    r = one(sb.select("receipts", s.token, id=f"eq.{rid}", select="storage_path,mime"))
    url = os.getenv("RECEIPT_ANALYZER_URL")
    if not url:
        raise HTTPException(503, "O reconhecimento de comprovantes não está configurado. Você pode preencher a transação manualmente.")
    import httpx
    headers = {"Authorization": "Bearer " + os.environ["RECEIPT_ANALYZER_KEY"]} if os.getenv("RECEIPT_ANALYZER_KEY") else {}
    try:
        resp = httpx.post(url, json={"image_base64": base64.b64encode(sb.download("receipts", r["storage_path"])).decode(), "mime": r["mime"]},
                          headers=headers, timeout=45)
        resp.raise_for_status()
        raw = resp.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Não foi possível analisar o comprovante agora.")
    return {"result": clean_receipt(raw, s), "saved": False}


def clean_receipt(raw: Any, s: Sess) -> dict:
    """Só repassa campos reconhecíveis; a pessoa revisa tudo antes de salvar."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    if raw.get("type") in ("receita", "despesa"):
        out["type"] = raw["type"]
    try:
        out["amount_cents"] = legacy.cents(raw.get("amount"))
    except HTTPException:
        pass
    try:
        d = date.fromisoformat(str(raw.get("date")))
        if d <= local_today():
            out["date"] = d.isoformat()
    except ValueError:
        pass
    if isinstance(raw.get("description"), str) and raw["description"].strip():
        out["description"] = " ".join(raw["description"].split())[:160]
    try:
        category_id(s, out.get("type", "despesa"), raw.get("category"))
        out["category"] = raw["category"]
    except HTTPException:
        pass
    return out


# ===================== turmas =====================
class ClassIn(BaseModel):
    name: str = Field(min_length=2, max_length=100); description: Optional[str] = Field(default=None, max_length=500)


class CodeIn(BaseModel):
    code: str


class ActivityIn(BaseModel):
    type: str; title: str = Field(min_length=3, max_length=120); config: dict
    due_date: Optional[str] = None; instructions: Optional[str] = Field(default=None, max_length=1000)


class QuizAnswersIn(BaseModel):
    answers: list[int] = Field(max_length=15)


class AssignmentIn(BaseModel):
    content_key: str = Field(max_length=120); content_type: str = "aula"; due_date: Optional[str] = None
    instructions: Optional[str] = Field(default=None, max_length=1000)


class ShareIn(BaseModel):
    enabled: bool


def require_role(s: Sess, role: str, message: str):
    if s.profile().get("role") != role:
        raise HTTPException(403, message)


@app.get("/api/classes")
def classes(request: Request):
    s = session(request)
    role = s.profile()["role"]
    if role == "professor":
        rows = sb.select("classes", s.token, teacher_id=f"eq.{s.uid}", select="*,class_memberships(count)", order="created_at.desc")
        items = [{**{k: v for k, v in r.items() if k != "class_memberships"}, "code": r["join_code"],
                  "participants": (r.get("class_memberships") or [{"count": 0}])[0]["count"]} for r in rows]
    else:
        rows = sb.select("class_memberships", s.token, student_id=f"eq.{s.uid}",
                         select="share_financial,joined_at,classes(*,teacher:profiles!classes_teacher_id_fkey(name))", order="joined_at.desc")
        items = []
        for r in rows:
            c = r["classes"]
            items.append({**{k: v for k, v in c.items() if k != "teacher"}, "code": c["join_code"],
                          "teacher_name": (c.get("teacher") or {}).get("name", ""), "share_financial": r["share_financial"]})
    return {"role": role, "items": items}


@app.post("/api/classes")
def class_new(b: ClassIn, request: Request):
    s = session(request)
    require_role(s, "professor", "Apenas professores podem criar turmas.")
    row = sb.insert("classes", {"teacher_id": s.uid, "name": b.name.strip(), "description": b.description}, s.token)[0]
    return {"id": row["id"], "code": row["join_code"]}


@app.put("/api/classes/{cid}")
def class_edit(cid: str, b: ClassIn, request: Request):
    one(sb.update("classes", {"name": b.name.strip(), "description": b.description}, session(request).token, id=f"eq.{cid}"),
        "Turma não encontrada.")
    return {"status": "ok"}


@app.post("/api/classes/preview")
def class_preview(b: CodeIn, request: Request):
    return sb.rpc("preview_class", {"p_code": b.code}, session(request).token)


@app.post("/api/classes/join")
def class_join(b: CodeIn, request: Request):
    sb.rpc("join_class", {"p_code": b.code}, session(request).token)
    return {"status": "ok"}


@app.delete("/api/classes/{cid}/membership")
def class_leave(cid: str, request: Request):
    s = session(request)
    require_role(s, "aluno", "Fluxo disponível para alunos.")
    one(sb.delete("class_memberships", s.token, class_id=f"eq.{cid}", student_id=f"eq.{s.uid}"), "Vínculo não encontrado.")
    return {"status": "ok"}


@app.post("/api/classes/{cid}/code/renew")
def class_renew(cid: str, request: Request):
    return {"code": sb.rpc("renew_class_code", {"p_class_id": cid}, session(request).token)}


@app.post("/api/classes/{cid}/code/disable")
def class_disable(cid: str, request: Request):
    one(sb.update("classes", {"code_active": False}, session(request).token, id=f"eq.{cid}"), "Turma não encontrada.")
    return {"status": "ok"}


@app.get("/api/classes/{cid}/participants")
def class_participants(cid: str, request: Request):
    items = sb.rpc("class_participants", {"p_class_id": cid}, session(request).token)
    return {"items": [{**x, "created_at": x["joined_at"]} for x in items]}


@app.get("/api/classes/{cid}/assignment-results")
def assignment_results(cid: str, request: Request):
    s = session(request)
    names = {p["id"]: p["name"] for p in sb.rpc("class_participants", {"p_class_id": cid}, s.token)}  # 403 se não for o dono
    by_lesson = {v["id"]: (k, v["title"]) for k, v in lesson_catalog(s).items()}
    rows = sb.select("assignment_overview", s.token, class_id=f"eq.{cid}", select="*", order="created_at.desc")
    items = [{"assignment_id": r["assignment_id"], "content_key": by_lesson.get(r["lesson_id"], ("", ""))[0], "due_date": r["due_date"],
              "student_name": names.get(r["student_id"], "—"), "status": r["status"], "score": r["score"],
              "submitted_at": r["submitted_at"], "title": activity_title(r, by_lesson), "state": r["state"],
              "content_type": r["content_type"], "progress": r["progress"], "target": (r["config"] or {}).get("target")} for r in rows]
    order = {}
    for r in rows:   # atividades mais recentes primeiro; dentro de cada uma, alunos por nome (igual à 0.6.x)
        order.setdefault(r["assignment_id"], len(order))
    items.sort(key=lambda x: (order[x["assignment_id"]], x["student_name"]))
    return {"items": items}


def activity_title(r: dict, by_lesson: dict) -> str:
    if r.get("content_type", "aula") == "aula":
        v = by_lesson.get(r["lesson_id"])
        return (v[1] if isinstance(v, tuple) else (v or {}).get("title")) or "Aula"
    return r.get("title") or ("Desafio" if r.get("content_type") == "desafio" else "Quiz")


@app.get("/api/classes/{cid}/dashboard")
def class_dashboard(cid: str, request: Request):
    """Painel do professor: quanto da turma concluiu cada atividade e cada aluno (sem dados financeiros)."""
    s = session(request)
    students = sb.rpc("class_participants", {"p_class_id": cid}, s.token)   # 403 se não for o dono
    by_lesson = {v["id"]: (k, v["title"]) for k, v in lesson_catalog(s).items()}
    rows = sb.select("assignment_overview", s.token, class_id=f"eq.{cid}", select="*", order="created_at.asc")
    acts, people = {}, {p["id"]: {"name": p["name"], "concluida": 0, "pendente": 0, "atrasada": 0} for p in students}
    for r in rows:
        a = acts.setdefault(r["assignment_id"], {"id": r["assignment_id"], "title": activity_title(r, by_lesson),
                                                 "type": r["content_type"], "due_date": r["due_date"],
                                                 "concluida": 0, "pendente": 0, "atrasada": 0})
        a[r["state"]] += 1
        if r["student_id"] in people:
            people[r["student_id"]][r["state"]] += 1
    for x in list(acts.values()) + list(people.values()):
        x["total"] = x["concluida"] + x["pendente"] + x["atrasada"]
        x["pct"] = round(100 * x["concluida"] / x["total"]) if x["total"] else 0
    done = sum(a["concluida"] for a in acts.values()); total = sum(a["total"] for a in acts.values())
    return {"students": len(students), "activities": list(acts.values()),
            "people": sorted(people.values(), key=lambda x: (x["pct"], x["name"])),
            "overall": {"concluida": done, "total": total, "pct": round(100 * done / total) if total else 0,
                        "atrasada": sum(a["atrasada"] for a in acts.values())}}


@app.get("/api/teacher/templates")
def teacher_templates_list(request: Request):
    s = session(request)
    require_role(s, "professor", "Apenas professores.")
    return teacher_templates.catalog()


@app.post("/api/classes/{cid}/activities")
def activity_new(cid: str, b: ActivityIn, request: Request):
    s = session(request)
    require_role(s, "professor", "Apenas professores lançam atividades.")
    if b.type not in ("desafio", "quiz"):
        raise HTTPException(422, "Tipo de atividade inválido.")
    return sb.rpc("create_activity", {"p_class_id": cid, "p_type": b.type, "p_title": b.title, "p_config": b.config,
                                      "p_due": parse_date(b.due_date).isoformat() if b.due_date else None,
                                      "p_instructions": clean(b.instructions)}, s.token)


@app.post("/api/assignments/{aid}/quiz")
def quiz_submit(aid: str, b: QuizAnswersIn, request: Request):
    return sb.rpc("submit_quiz", {"p_assignment_id": aid, "p_answers": b.answers}, session(request).token)


@app.get("/api/classes/{cid}/financial-summary")
def class_financial_summary(cid: str, request: Request, start: Optional[str] = None, end: Optional[str] = None):
    return sb.rpc("class_financial_summary", {"p_class_id": cid, "p_start": parse_date(start).isoformat() if start else None,
                                               "p_end": parse_date(end).isoformat() if end else None}, session(request).token)


@app.post("/api/classes/{cid}/assignments")
def assignment_new(cid: str, b: AssignmentIn, request: Request):
    s = session(request)
    require_role(s, "professor", "Apenas professores atribuem atividades.")
    if b.content_type != "aula":
        raise HTTPException(422, "Tipo de atividade inválido. Por enquanto, apenas aulas do curso podem ser atribuídas.")
    lesson = lesson_catalog(s).get(b.content_key)
    if not lesson:
        raise HTTPException(422, "Escolha uma aula do curso.")
    if not any(c for c in sb.select("classes", s.token, id=f"eq.{cid}", teacher_id=f"eq.{s.uid}", select="id")):
        raise HTTPException(403, "Sem permissão.")
    row = sb.insert("assignments", {"class_id": cid, "teacher_id": s.uid, "lesson_id": lesson["id"], "content_type": "aula",
                                    "due_date": parse_date(b.due_date).isoformat() if b.due_date else None,
                                    "instructions": clean(b.instructions)}, s.token)[0]
    return {"id": row["id"]}


@app.delete("/api/assignments/{aid}")
def assignment_delete(aid: str, request: Request):
    one(sb.delete("assignments", session(request).token, id=f"eq.{aid}"), "Atividade não encontrada.")
    return {"status": "ok"}


@app.get("/api/assignments")
def assignments(request: Request):
    s = session(request)
    by_lesson = {v["id"]: v for v in lesson_catalog(s).values()}
    out = []
    if s.profile()["role"] == "aluno":
        rows = sb.select("assignment_overview", s.token, student_id=f"eq.{s.uid}", select="*")
        names = {c["id"]: c["name"] for c in sb.select("classes", s.token, select="id,name")}
        for r in rows:
            l = by_lesson.get(r["lesson_id"], {})
            out.append({"id": r["assignment_id"], "class_id": r["class_id"], "class_name": names.get(r["class_id"], ""),
                        "due_date": r["due_date"], "instructions": r["instructions"], "status": r["status"], "score": r["score"],
                        "state": r["state"], "title": activity_title(r, by_lesson), "module": l.get("module"), "topic": l.get("topic"),
                        "content_key": f'{l.get("module")}:{l.get("topic")}' if l else None, "created_at": r["created_at"],
                        "content_type": r["content_type"], "config": r["config"], "progress": r["progress"], "attempts": r["attempts"]})
        out.sort(key=lambda x: (x["due_date"] is None, x["due_date"] or "", ""))
    else:
        rows = sb.select("assignments", s.token, teacher_id=f"eq.{s.uid}", select="*,classes(name)", order="created_at.desc")
        prog = sb.select("assignment_progress", s.token, select="assignment_id,status",
                         assignment_id=f"in.({','.join(r['id'] for r in rows)})") if rows else []
        for r in rows:
            l = by_lesson.get(r["lesson_id"], {})
            mine = [p for p in prog if p["assignment_id"] == r["id"]]
            out.append({**{k: v for k, v in r.items() if k != "classes"}, "class_name": r["classes"]["name"],
                        "title": activity_title(r, by_lesson), "module": l.get("module"), "topic": l.get("topic"),
                        "content_key": f'{l.get("module")}:{l.get("topic")}' if l else None, "total": len(mine),
                        "done": sum(p["status"] == "concluida" for p in mine)})
    return {"items": out}


@app.put("/api/classes/{cid}/share")
def class_share(cid: str, b: ShareIn, request: Request):
    s = session(request)
    require_role(s, "aluno", "Configuração disponível para alunos.")
    one(sb.update("class_memberships", {"share_financial": b.enabled}, s.token, class_id=f"eq.{cid}", student_id=f"eq.{s.uid}"),
        "Vínculo não encontrado.")
    return {"status": "ok"}


# ===================== preferências, perfil, lembretes, indicadores =====================
class SettingsIn(BaseModel):
    theme: Optional[str] = None; tips: Optional[bool] = None; goal_alerts: Optional[bool] = None
    weekly_email: Optional[bool] = None; chart_type: Optional[str] = None


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class ReminderPrefsIn(BaseModel):
    lessons: bool = True; spending: bool = True
    monthly_budget_cents: int = Field(default=0, ge=0, le=100_000_000_000, strict=True)


@app.put("/api/settings")
def settings(b: SettingsIn, request: Request):
    s = session(request)
    patch = {k: v for k, v in b.model_dump().items() if v is not None}
    if patch.get("theme") not in (None, "dark", "light"):
        patch.pop("theme")
    if patch.get("chart_type") not in (None, "line", "bar", "pie"):
        patch.pop("chart_type")
    cols = "theme,tips,goal_alerts,weekly_email,chart_type"
    rows = sb.update("user_settings", patch, s.token, user_id=f"eq.{s.uid}") if patch else \
        sb.select("user_settings", s.token, user_id=f"eq.{s.uid}", select=cols)
    return {"status": "ok", "settings": {k: one(rows)[k] for k in cols.split(",")}}


@app.put("/api/profile")
def profile(b: ProfileIn, request: Request):
    s = session(request)
    name = " ".join(b.name.split())
    one(sb.update("profiles", {"name": name}, s.token, id=f"eq.{s.uid}"))
    return {"status": "ok", "name": name}


@app.get("/api/notifications/preferences")
def reminder_preferences(request: Request):
    s = session(request)
    rows = sb.select("reminder_preferences", s.token, user_id=f"eq.{s.uid}", select="lessons,spending,monthly_budget_cents")
    return rows[0] if rows else {"lessons": True, "spending": True, "monthly_budget_cents": 0}


@app.put("/api/notifications/preferences")
def save_reminder_preferences(b: ReminderPrefsIn, request: Request):
    s = session(request)
    values = b.model_dump()
    if not sb.update("reminder_preferences", values, s.token, user_id=f"eq.{s.uid}"):
        sb.insert("reminder_preferences", {"user_id": s.uid, **values}, s.token)
    return values


@app.get("/api/notifications")
def notifications(request: Request, page: int = 1):
    return sb.rpc("my_notifications", {"p_page": page}, session(request).token)


@app.post("/api/notifications/read-all")
def notifications_read_all(request: Request):
    sb.rpc("mark_all_notifications_read", {}, session(request).token)
    return {"status": "ok"}


@app.post("/api/notifications/{nid}/read")
def notification_read(nid: str, request: Request):
    from datetime import datetime, timezone
    one(sb.update("notifications", {"read_at": datetime.now(timezone.utc).isoformat()}, session(request).token, id=f"eq.{nid}"),
        "Lembrete não encontrado.")
    return {"status": "ok"}


_MARKET_LOCK = threading.Lock()
_MARKET_RETRY: dict[str, float] = {}
PERIOD_KIND = {"USD": "fechamento_diario", "EUR": "fechamento_diario", "SELIC": "meta_vigente", "IPCA": "variacao_mensal"}


@app.get("/api/market")
def market(request: Request):
    s = session(request)
    data = sb.rpc("market_indicators", {}, s.token)
    if not sb.secret_key:
        return data
    have = {i["key"]: i for i in data["items"]}
    now = time.time()
    due = [k for k in PERIOD_KIND if (k not in have or have[k]["stale"]) and now >= _MARKET_RETRY.get(k, 0)]
    if due and _MARKET_LOCK.acquire(blocking=False):
        try:
            for k in due:
                try:
                    it = backend_services.fetch_indicator(k)
                    sb.rpc("service_upsert_market_indicator", {
                        "p_key": k, "p_label": it["label"], "p_value": it["value"], "p_unit": it["unit"], "p_period_kind": PERIOD_KIND[k],
                        "p_observed_on": it["observed_at"], "p_reference": it["reference"], "p_source_url": it["source_url"]}, service=True)
                except Exception:
                    logger.warning("Fonte BCB indisponível para %s", k)
                    _MARKET_RETRY[k] = now + 300
                    try:
                        sb.rpc("service_mark_market_error", {"p_key": k}, service=True)
                    except SupabaseError:
                        pass
        finally:
            _MARKET_LOCK.release()
        data = sb.rpc("market_indicators", {}, s.token)
    return data


@app.get("/api/health")
def health():
    return {"status": "ok", "backend": "supabase", "supabase_ready": bool(SUPABASE_URL and sb.publishable_key),
            "service_key_ready": bool(sb.secret_key), "ai_ready": legacy.ai_ready(), "email_ready": legacy.smtp_ready(),
            "recovery_ready": bool(SUPABASE_URL),   # recuperação de senha: e-mail enviado pelo Supabase Auth
            "receipt_analysis_ready": bool(os.getenv("RECEIPT_ANALYZER_URL")), "google_ready": google_ready()}


# ===================== resumo semanal (worker) =====================
_stop = threading.Event()


def send_weekly_summaries() -> int:
    today = local_today()
    if today.weekday() != 0 or not legacy.smtp_ready() or not sb.secret_key:
        return 0
    year, week, _ = today.isocalendar()
    key = f"{year}-W{week:02d}"
    start, end = today - timedelta(days=7), today - timedelta(days=1)
    sent = 0
    for u in sb.rpc("service_weekly_summary_candidates", {"p_week": key, "p_start": start.isoformat(), "p_end": end.isoformat()}, service=True):
        body = (f"Olá, {u['name'].split()[0]}!\n\nResumo de {backend_services.br(start.isoformat())} a {backend_services.br(end.isoformat())} "
                "com base nos registros que você fez no FinTrack:\n\n"
                f"Receitas: {backend_services.brl(u['receitas'])}\nDespesas: {backend_services.brl(u['despesas'])}\n"
                f"Resultado do período: {backend_services.brl(u['receitas'] - u['despesas'])}\n"
                f"Lançamentos: {u['lancamentos']}\nMetas em andamento: {u['metas_ativas']}\n\n"
                "Este é um resumo educativo e não representa saldo bancário. Para parar de receber, desative a opção em Configurações.")
        try:
            legacy.send_email(u["email"], "Seu resumo semanal — FinTrack", body)
        except Exception:
            logger.warning("Falha ao enviar resumo semanal para uma conta")
            continue
        sb.rpc("service_mark_weekly_sent", {"p_user": u["user_id"], "p_week": key}, service=True)
        sent += 1
    return sent


def _worker():
    # Recorrências e manutenção rodam no pg_cron do Supabase; aqui só o e-mail semanal (precisa do SMTP do backend).
    while not _stop.is_set():
        try:
            send_weekly_summaries()
        except Exception:
            logger.exception("Falha ao enviar resumos semanais")
        _stop.wait(600)


# ===================== páginas =====================
@app.get("/")
def home():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/login.html")
def login_page():
    return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})


@app.get("/reset.html")
def reset_page():
    return FileResponse(STATIC / "reset.html", headers={"Cache-Control": "no-store"})


def protected_page(request: Request, name: str):
    try:
        s = session(request)
        if not s.profile().get("role"):
            return RedirectResponse(ONBOARDING_URL, status_code=303)
    except (HTTPException, SupabaseError):
        return FileResponse(STATIC / "login.html", status_code=401, headers={"Cache-Control": "no-store"})
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-store,max-age=0"})


@app.get("/app.html")
def app_page(request: Request):
    return protected_page(request, "app.html")


@app.get("/avatar.html")
def avatar_page(request: Request):
    return protected_page(request, "avatar.html")


@app.get("/terms")
def terms():
    return FileResponse(STATIC / "terms.html")


@app.get("/privacy")
def privacy():
    return FileResponse(STATIC / "privacy.html")


app.mount("/static", legacy.GuardedStatic(directory=STATIC), name="static")
app.mount("/", legacy.GuardedStatic(directory=STATIC, html=True), name="original-assets")
