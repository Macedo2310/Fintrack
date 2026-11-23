"""Cliente mínimo do Supabase (Auth, Data API/PostgREST, Storage) usado pelo app_supabase.py.

Duas identidades:
  - token do usuário (access token do Supabase Auth): toda leitura/escrita de dados pessoais passa por ele,
    então o RLS vale também no backend;
  - chave secreta (service_role): só para o que o sistema faz em nome do usuário depois de validá-lo
    (gravar resposta da IA, enviar arquivos validados, indicadores, resumo semanal). Nunca vai ao navegador.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


class SupabaseError(Exception):
    def __init__(self, status: int, message: str, code: str = "", details: Any = None):
        super().__init__(message)
        self.status, self.message, self.code, self.details = status, message, code or "", details


def jwt_claims(token: str) -> dict:
    """Lê as declarações do JWT SEM validar a assinatura. Use só para expiração e para montar filtros;
    a validação real acontece no Supabase (PostgREST/Auth) em toda chamada feita com o token."""
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


@dataclass
class AuthSession:
    access_token: str
    refresh_token: str
    expires_at: int
    user: dict = field(default_factory=dict)

    @classmethod
    def from_payload(cls, p: dict) -> "AuthSession":
        exp = p.get("expires_at") or int(time.time()) + int(p.get("expires_in") or 3600)
        return cls(p["access_token"], p["refresh_token"], int(exp), p.get("user") or {})


class Supabase:
    def __init__(self, url: str, publishable_key: str, secret_key: Optional[str] = None, timeout: float = 20.0):
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.secret_key = secret_key
        self.http = httpx.Client(timeout=timeout)

    # ---------- infraestrutura ----------
    def _headers(self, token: Optional[str] = None, service: bool = False) -> dict:
        if service:
            if not self.secret_key:
                raise SupabaseError(503, "A chave secreta do Supabase não está configurada no servidor.")
            h = {"apikey": self.secret_key}
            # Chaves antigas (JWT service_role) também vão no Authorization; as novas (sb_secret_…) não.
            if self.secret_key.startswith("eyJ"):
                h["Authorization"] = "Bearer " + self.secret_key
            return h
        h = {"apikey": self.publishable_key}
        if token:
            h["Authorization"] = "Bearer " + token
        return h

    def _send(self, method: str, url: str, headers: dict, **kw) -> httpx.Response:
        try:
            r = self.http.request(method, url, headers=headers, **kw)
        except httpx.HTTPError:
            raise SupabaseError(503, "Não foi possível acessar o banco de dados agora. Tente novamente em instantes.")
        if r.status_code >= 300:   # 300 = relacionamento ambíguo no PostgREST: também é erro
            raise self._error(r)
        return r

    @staticmethod
    def _error(r: httpx.Response) -> SupabaseError:
        try:
            body = r.json()
        except ValueError:
            body = {"message": r.text[:300]}
        if not isinstance(body, dict):
            body = {"message": str(body)[:300]}
        # Auth: {"code": 400, "error_code": "invalid_credentials", "msg": ...}; PostgREST: {"code": "23505", "message": ...}
        code = str(body.get("error_code") or body.get("code") or body.get("error") or "")
        msg = body.get("message") or body.get("msg") or body.get("error_description") or body.get("error") or "Erro no Supabase."
        return SupabaseError(r.status_code, str(msg), code, body.get("details"))

    # ---------- Auth ----------
    def sign_up(self, email: str, password: str, data: dict, redirect_to: Optional[str] = None) -> dict:
        params = {"redirect_to": redirect_to} if redirect_to else None
        return self._send("POST", f"{self.url}/auth/v1/signup", self._headers(), params=params,
                          json={"email": email, "password": password, "data": data}).json()

    def sign_in(self, email: str, password: str) -> AuthSession:
        r = self._send("POST", f"{self.url}/auth/v1/token", self._headers(), params={"grant_type": "password"},
                       json={"email": email, "password": password})
        return AuthSession.from_payload(r.json())

    def refresh(self, refresh_token: str) -> AuthSession:
        r = self._send("POST", f"{self.url}/auth/v1/token", self._headers(), params={"grant_type": "refresh_token"},
                       json={"refresh_token": refresh_token})
        return AuthSession.from_payload(r.json())

    def exchange_code(self, auth_code: str, verifier: str) -> AuthSession:
        r = self._send("POST", f"{self.url}/auth/v1/token", self._headers(), params={"grant_type": "pkce"},
                       json={"auth_code": auth_code, "code_verifier": verifier})
        return AuthSession.from_payload(r.json())

    def authorize_url(self, provider: str, redirect_to: str, code_challenge: str) -> str:
        q = urllib.parse.urlencode({"provider": provider, "redirect_to": redirect_to, "code_challenge": code_challenge,
                                    "code_challenge_method": "s256"})
        return f"{self.url}/auth/v1/authorize?{q}"

    def sign_out(self, access_token: str, scope: str = "local") -> None:
        try:
            self._send("POST", f"{self.url}/auth/v1/logout", self._headers(access_token), params={"scope": scope})
        except SupabaseError:
            pass  # sessão já inválida: o cookie é apagado de qualquer forma

    def recover(self, email: str, redirect_to: str) -> None:
        self._send("POST", f"{self.url}/auth/v1/recover", self._headers(), params={"redirect_to": redirect_to}, json={"email": email})

    def verify_recovery(self, token_hash: str) -> AuthSession:
        r = self._send("POST", f"{self.url}/auth/v1/verify", self._headers(), json={"type": "recovery", "token_hash": token_hash})
        return AuthSession.from_payload(r.json())

    def get_user(self, access_token: str) -> dict:
        return self._send("GET", f"{self.url}/auth/v1/user", self._headers(access_token)).json()

    def update_user(self, access_token: str, attrs: dict) -> dict:
        return self._send("PUT", f"{self.url}/auth/v1/user", self._headers(access_token), json=attrs).json()

    def admin_create_user(self, attrs: dict) -> dict:
        return self._send("POST", f"{self.url}/auth/v1/admin/users", self._headers(service=True), json=attrs).json()

    def admin_delete_user(self, user_id: str) -> None:
        self._send("DELETE", f"{self.url}/auth/v1/admin/users/{user_id}", self._headers(service=True))

    # ---------- Data API ----------
    def rest(self, method: str, table: str, *, token: Optional[str] = None, service: bool = False,
             params: Optional[dict] = None, json_body: Any = None, prefer: Optional[str] = None) -> Any:
        h = self._headers(token, service)
        if prefer:
            h["Prefer"] = prefer
        r = self._send(method, f"{self.url}/rest/v1/{table}", h, params=params, json=json_body)
        if not r.content:
            return None
        return r.json()

    def select(self, table: str, token: Optional[str] = None, service: bool = False, **params) -> list:
        return self.rest("GET", table, token=token, service=service, params=params) or []

    def insert(self, table: str, row: Any, token: Optional[str] = None, service: bool = False) -> list:
        return self.rest("POST", table, token=token, service=service, json_body=row, prefer="return=representation") or []

    def update(self, table: str, values: dict, token: Optional[str] = None, service: bool = False, **filters) -> list:
        return self.rest("PATCH", table, token=token, service=service, params=filters, json_body=values,
                         prefer="return=representation") or []

    def delete(self, table: str, token: Optional[str] = None, service: bool = False, **filters) -> list:
        return self.rest("DELETE", table, token=token, service=service, params=filters, prefer="return=representation") or []

    def rpc(self, fn: str, args: Optional[dict] = None, token: Optional[str] = None, service: bool = False) -> Any:
        return self.rest("POST", f"rpc/{fn}", token=token, service=service, json_body=args or {})

    # ---------- Storage (sempre com a chave secreta) ----------
    def upload(self, bucket: str, path: str, data: bytes, mime: str, upsert: bool = False) -> None:
        h = self._headers(service=True)
        h.update({"Content-Type": mime, "x-upsert": "true" if upsert else "false"})
        self._send("POST", f"{self.url}/storage/v1/object/{bucket}/{path}", h, content=data)

    def download(self, bucket: str, path: str) -> bytes:
        return self._send("GET", f"{self.url}/storage/v1/object/authenticated/{bucket}/{path}", self._headers(service=True)).content

    def remove(self, bucket: str, paths: list) -> None:
        if paths:
            self._send("DELETE", f"{self.url}/storage/v1/object/{bucket}", self._headers(service=True), json={"prefixes": paths})

    def signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        r = self._send("POST", f"{self.url}/storage/v1/object/sign/{bucket}/{path}", self._headers(service=True),
                       json={"expiresIn": expires_in}).json()
        signed = r.get("signedURL") or r.get("signedUrl") or ""
        return f"{self.url}/storage/v1{signed}" if signed.startswith("/") else signed
