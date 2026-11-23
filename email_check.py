"""Verificação de e-mail no cadastro, SEM enviar mensagem.

O que dá para garantir sem e-mail de confirmação:
  1. formato válido (RFC, via email-validator);
  2. o domínio existe e recebe e-mail (consulta DNS: registros MX/A);
  3. não é erro de digitação de um provedor conhecido (gmial.com → gmail.com), mesmo que o domínio errado exista;
  4. não é provedor de e-mail descartável.

O que NÃO dá para garantir: que a caixa existe (ex.: axxcfi@gmail.com). Gmail, Outlook e outros não informam
isso a terceiros. A prova definitiva é o código/link de confirmação por e-mail (etapa futura).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from email_validator import EmailNotValidError, EmailUndeliverableError, validate_email

POPULAR = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "icloud.com", "live.com",
           "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "msn.com", "protonmail.com", "hotmail.com.br",
           "outlook.com.br", "gmail.com.br", "me.com", "proton.me"]
# Provedores reais parecidos com os populares: nunca tratados como erro de digitação.
KNOWN_OK = {"ymail.com", "rocketmail.com", "aol.com", "gmx.com", "gmx.net", "zoho.com", "mail.com", "hey.com", "pm.me",
            "live.com.br", "r7.com", "globo.com", "globomail.com", "oi.com.br", "zipmail.com.br", "usp.br", "unicamp.br",
            "outlook.pt", "hotmail.pt", "yahoo.co.uk", "yahoo.es", "msn.com.br"}
DISPOSABLE = {"mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com", "temp-mail.org", "yopmail.com",
              "trashmail.com", "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
              "fakeinbox.com", "mintemail.com", "mohmal.com", "emailondeck.com", "tempmailo.com", "tempail.com"}

_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 3600


@dataclass
class EmailCheck:
    ok: bool
    email: str = ""
    message: str = ""
    suggestion: Optional[str] = None


def _distance(a: str, b: str) -> int:
    """Distância de Damerau-Levenshtein (troca de letras vizinhas conta 1)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def suggest_domain(domain: str) -> Optional[str]:
    """Sugere o provedor conhecido mais parecido (ex.: gmial.com → gmail.com, hotmail.con → hotmail.com)."""
    domain = domain.lower()
    if domain in POPULAR or domain in KNOWN_OK:
        return None
    best = min(POPULAR, key=lambda p: _distance(domain, p))
    limit = 1 if len(domain) <= 7 else 2
    return best if _distance(domain, best) <= limit else None


def _deliverability(domain: str, email: str) -> Optional[str]:
    """None se o domínio recebe e-mail; senão a mensagem de erro. Falha de rede não bloqueia o cadastro."""
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(domain)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        validate_email(email, check_deliverability=True, timeout=4)
        result = None
    except EmailUndeliverableError:
        result = f"O domínio “{domain}” não existe ou não recebe e-mails. Confira o que vem depois do @."
    except EmailNotValidError:
        result = None   # erro de formato é tratado antes; aqui só interessa o DNS
    except Exception:
        return None     # DNS indisponível: não impede o cadastro e não guarda no cache
    with _LOCK:
        _CACHE[domain] = (now, result)
    return result


def check_email(raw: str, dns: bool = True) -> EmailCheck:
    raw = (raw or "").strip()
    if "@" not in raw:
        return EmailCheck(False, message="Falta o @ no e-mail. Exemplo: nome@gmail.com.")
    try:
        email = validate_email(raw, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return EmailCheck(False, message="Este e-mail não está num formato válido. Confira se não há espaços ou caracteres especiais.")
    local, domain = email.rsplit("@", 1)
    if domain in DISPOSABLE:
        return EmailCheck(False, message="Use um e-mail pessoal. Endereços temporários ou descartáveis não são aceitos.")
    fix = suggest_domain(domain)
    if fix:
        return EmailCheck(False, message=f"Você quis dizer {local}@{fix}? Confira o que vem depois do @.", suggestion=f"{local}@{fix}")
    if dns:
        problem = _deliverability(domain, email)
        if problem:
            return EmailCheck(False, message=problem)
    return EmailCheck(True, email=email)
