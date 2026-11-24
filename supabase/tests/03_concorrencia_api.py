"""Teste real de concorrência pela Data API (o mesmo caminho do app), sem precisar da senha do banco.

Cada thread usa um cliente HTTP próprio, então cada chamada vira uma requisição e uma transação independentes
no PostgREST. Cria UMA conta temporária "concorrencia-<uuid>@example.com" e a apaga no final (inclusive em caso
de erro); a exclusão em cascata remove perfil, transação, meta e eventos.

Cenários (saldo inicial R$ 100):
  A) 8 reservas simultâneas de R$ 10 com a MESMA chave de idempotência -> 1 evento só, R$ 10 reservados.
  B) 8 reservas simultâneas de R$ 80 com chaves diferentes (disponível R$ 90) -> exatamente 1 aprovada.

Uso (PowerShell, dentro de FinTrack-0.6.1; SUPABASE_URL e as chaves vêm do .env):
  .venv\\Scripts\\python.exe supabase\\tests\\03_concorrencia_api.py
"""
import os
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from supa import Supabase, SupabaseError  # noqa: E402

N = 8
cfg = {k: os.getenv(k) for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY")}
if not all(cfg.values()):
    sys.exit("Defina SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY e SUPABASE_SECRET_KEY no .env.")


def client():
    return Supabase(cfg["SUPABASE_URL"], cfg["SUPABASE_PUBLISHABLE_KEY"], cfg["SUPABASE_SECRET_KEY"])


def burst(token, goal, amount, keys):
    """Dispara len(keys) reservas ao mesmo tempo; devolve a lista de resultados."""
    barrier = threading.Barrier(len(keys))
    results, lock = [], threading.Lock()

    def worker(key):
        c = client()
        try:
            barrier.wait()
            try:
                c.rpc("reserve_goal", {"p_goal_id": goal, "p_amount_cents": amount, "p_idempotency_key": key}, token=token)
                outcome = "aprovada"
            except SupabaseError as e:
                outcome = f"recusada ({e.status}): {str(e)[:70]}"
        finally:
            c.http.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def main():
    admin = client()
    email = f"concorrencia-{uuid.uuid4().hex[:12]}@example.com"
    password = "Conc" + uuid.uuid4().hex[:12] + "9"
    uid = admin.admin_create_user({"email": email, "password": password, "email_confirm": True,
                                   "user_metadata": {"name": "Teste Concorrência"}})["id"]
    ok = False
    try:
        today = datetime.now(timezone(timedelta(hours=-3))).date()  # America/Sao_Paulo (sem horário de verão)
        token = admin.sign_in(email, password).access_token
        admin.rpc("complete_onboarding", {"p_name": "Teste Concorrência", "p_role": "aluno", "p_accept_terms": True}, token=token)
        cat = admin.select("categories", token=token, select="id", user_id="is.null", type="eq.receita", name="eq.Mesada")[0]["id"]
        admin.insert("transactions", {"user_id": uid, "type": "receita", "category_id": cat, "description": "Saldo inicial",
                                      "amount_cents": 10000, "occurred_on": today.isoformat()}, token=token)
        goal = admin.insert("goals", {"user_id": uid, "title": "Concorrência", "target_cents": 100000,
                                      "deadline": (today + timedelta(days=30)).isoformat()}, token=token)[0]["id"]

        a = burst(token, goal, 1000, ["mesma-chave"] * N)
        events_a = admin.select("goal_reservation_events", token=token, select="id", goal_id=f"eq.{goal}")
        sum_a = admin.rpc("balance_summary", token=token)
        print("Cenário A (mesma chave):", *sorted(a), sep="\n  ")
        print("  eventos gravados:", len(events_a), "| resumo:", sum_a)
        ok_a = len(events_a) == 1 and sum_a["reserved"] == 1000

        b = burst(token, goal, 8000, [f"chave-{i:04d}" for i in range(N)])
        sum_b = admin.rpc("balance_summary", token=token)
        approved = sum(r == "aprovada" for r in b)
        print("Cenário B (saldo disputado):", *sorted(b), sep="\n  ")
        print("  aprovadas:", approved, "| resumo:", sum_b)
        ok_b = approved == 1 and sum_b["reserved"] == 9000 and sum_b["available"] == 1000

        ok = ok_a and ok_b
        print("RESULTADO:", "OK" if ok else f"FALHOU (A={'ok' if ok_a else 'falhou'}, B={'ok' if ok_b else 'falhou'})")
    finally:
        admin.admin_delete_user(uid)
        left = admin.select("profiles", service=True, select="id", id=f"eq.{uid}")
        print("limpeza:", "ok" if not left else "FALHOU")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
