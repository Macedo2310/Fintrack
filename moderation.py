"""Moderação simples de texto (pt-BR) para o que as pessoas escrevem no FinTrack.

- offensive(text): linguagem ofensiva, assédio ou ameaça -> o conteúdo é bloqueado.
- self_harm(text): sinais de sofrimento intenso -> NÃO bloqueia; o FinBot responde com acolhimento.
A comparação ignora maiúsculas, acentos, letras repetidas e trocas comuns (4->a, 3->e, 0->o, @->a ...),
e só casa palavras inteiras, para evitar falsos positivos (ex.: "computador", "Bettina").
"""
import re
import unicodedata

_LEET = str.maketrans({"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t"})


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).translate(_LEET)
    t = re.sub(r"[^a-z\s]", " ", t)
    t = re.sub(r"(.)\1{2,}", r"\1", t)          # "porrrra" -> "pora"... e também "poooorra" -> "porra"
    return re.sub(r"\s+", " ", t).strip()


# Palavras e expressões (já normalizadas). Insultos leves do dia a dia ("burro", "idiota") ficam de fora
# de propósito: alunos usam ao falar de si mesmos ("sou burro com dinheiro").
_WORDS = {
    "porra", "pora", "caralho", "caralh", "krl", "crl", "puta", "puto", "putaria", "merda", "foda", "fodase", "foder", "fudido", "fodido",
    "arrombado", "arrombada", "cuzao", "cusao", "buceta", "boceta", "piroca", "pqp", "fdp", "vsf", "tnc", "vtnc", "vtmnc",
    "viado", "viadinho", "traveco", "retardado", "retardada", "vagabundo", "vagabunda", "desgracado", "desgracada", "babaca", "otario", "otaria",
}
_PHRASES = [
    "filho da puta", "filha da puta", "vai se foder", "vai se fuder", "vai tomar no cu", "tomar no cu", "pau no cu", "toma no cu",
    "vou te matar", "te mato", "vou matar voce", "se mata", "morre logo", "seu lixo", "sua lixo", "macaco imundo", "preto imundo",
]
_SELF_HARM = [
    "quero me matar", "vou me matar", "me matar", "suicidio", "suicidar", "tirar minha vida", "tirar a minha vida", "nao quero mais viver",
    "quero morrer", "acabar com a minha vida", "acabar com minha vida", "me machucar", "nao aguento mais viver",
]
_PHRASE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PHRASES) + r")\b")
_SELF_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _SELF_HARM) + r")\b")


def offensive(text: str) -> bool:
    t = normalize(text)
    if not t:
        return False
    if _PHRASE_RE.search(t):
        return True
    return any(w in _WORDS for w in t.split())


def self_harm(text: str) -> bool:
    return bool(_SELF_RE.search(normalize(text)))


BLOCK_MESSAGE = "Sua mensagem tem linguagem ofensiva e não foi enviada. O FinTrack é um espaço de aprendizado e respeito para todos."

SUPPORT_REPLY = (
    "Sinto muito que você esteja passando por isso. Você não precisa enfrentar esse momento sozinho.\n\n"
    "Converse agora com o CVV (Centro de Valorização da Vida): ligue 188, a ligação é gratuita e o atendimento funciona 24 horas, "
    "ou acesse cvv.org.br para conversar por chat. Em caso de emergência, ligue 192 (SAMU).\n\n"
    "Se o dinheiro estiver pesando nisso, dívidas e apertos têm saída, e posso ajudar você a montar um plano passo a passo quando quiser. "
    "Falar com alguém de confiança também ajuda muito."
)
