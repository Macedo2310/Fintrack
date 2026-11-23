"""Teste real de concorrência: 8 reservas simultâneas de R$ 80 com saldo de R$ 100 -> exatamente 1 aprovada.

Usa 8 conexões PostgreSQL independentes (o mesmo que 8 requisições ao mesmo tempo). Cria UMA conta temporária
"concorrencia-<uuid>@teste.invalid" e a apaga no final (inclusive em caso de erro); a exclusão em cascata
remove perfil, transação, meta e eventos.

Uso (PowerShell, dentro de FinTrack-0.6.1):
  .venv\\Scripts\\python.exe -m pip install -r supabase\\scripts\\requirements-migracao.txt
  $env:SUPABASE_DB_URL='postgresql://postgres:<senha>@db.<ref>.supabase.co:5432/postgres'
  .venv\\Scripts\\python.exe supabase\\tests\\02_concorrencia_reservas.py
"""
import os
import sys
import threading
import uuid

import psycopg

URL = os.environ.get("SUPABASE_DB_URL") or sys.exit("Defina SUPABASE_DB_URL no terminal.")
UID = str(uuid.uuid4())
CLAIMS = '{"sub":"%s","role":"authenticated"}' % UID
N, AMOUNT = 8, 8000


def as_user(conn):
    conn.execute("set local role authenticated")
    conn.execute("select set_config('request.jwt.claims', %s, true)", (CLAIMS,))


def main():
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute("""insert into auth.users (instance_id, id, aud, role, email, encrypted_password, raw_user_meta_data,
                         raw_app_meta_data, created_at, updated_at)
                         values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated', 'authenticated', %s, '',
                                 '{"name":"Teste Concorrência"}', '{}', now(), now())""", (UID, f"concorrencia-{UID}@teste.invalid"))
        try:
            with psycopg.connect(URL) as c:
                as_user(c)
                c.execute("select public.complete_onboarding('Teste Concorrência', 'aluno', true)")
                cat = c.execute("select id from public.categories where user_id is null and type = 'receita' and name = 'Mesada'").fetchone()[0]
                c.execute("""insert into public.transactions (user_id, type, category_id, description, amount_cents, occurred_on)
                             values (%s, 'receita', %s, 'Saldo inicial', 10000, private.today_br())""", (UID, cat))
                goal = c.execute("""insert into public.goals (user_id, title, target_cents, deadline)
                                    values (%s, 'Concorrência', 100000, private.today_br() + 30) returning id""", (UID,)).fetchone()[0]
                c.commit()

            barrier = threading.Barrier(N)
            results = []
            lock = threading.Lock()

            def worker(i):
                with psycopg.connect(URL) as c:
                    as_user(c)
                    barrier.wait()
                    try:
                        c.execute("select public.reserve_goal(%s, %s, %s)", (goal, AMOUNT, f"concorrencia-{i:04d}"))
                        c.commit()
                        outcome = "aprovada"
                    except psycopg.Error as e:
                        c.rollback()
                        outcome = "recusada: " + (e.diag.message_primary or str(e))[:80]
                with lock:
                    results.append(outcome)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            approved = sum(r == "aprovada" for r in results)
            with psycopg.connect(URL) as c:
                as_user(c)
                summary = c.execute("select public.balance_summary()").fetchone()[0]
            print("\n".join(sorted(results)))
            print("resumo:", summary)
            ok = approved == 1 and summary["reserved"] == AMOUNT and summary["available"] == 10000 - AMOUNT
            print("RESULTADO:", "OK - exatamente 1 reserva aprovada" if ok else f"FALHOU - {approved} aprovadas")
            sys.exit(0 if ok else 1)
        finally:
            admin.execute("delete from auth.users where id = %s", (UID,))
            left = admin.execute("select count(*) from public.profiles where id = %s", (UID,)).fetchone()[0]
            print("limpeza:", "ok" if left == 0 else "FALHOU")


if __name__ == "__main__":
    main()
