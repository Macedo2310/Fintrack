"""Migra os dados de um banco SQLite da FinTrack 0.6.x para o Supabase.

Modos
  simular  (padrão) Só LÊ o SQLite e gera o relatório: inventário, contagens, órfãos, duplicados,
           valores inválidos e o plano de importação. Não acessa a rede.
  aplicar  Cria as contas no Supabase Auth (Admin API), importa os dados numa ÚNICA transação
           PostgreSQL, envia fotos e comprovantes ao Storage conferindo SHA-256 e compara totais.
  videos   Envia os 4 vídeos introdutórios ao bucket education-videos e confere o SHA-256.

Uso (PowerShell, dentro de FinTrack-0.6.1):
  .venv\\Scripts\\python.exe -m pip install -r supabase\\scripts\\requirements-migracao.txt
  .venv\\Scripts\\python.exe supabase\\scripts\\migrar_sqlite.py simular --sqlite data\\fintrack.db --saida relatorio-migracao
  # Para aplicar, defina no PRÓPRIO terminal (nunca no código nem no repositório):
  #   $env:SUPABASE_URL='https://<ref>.supabase.co'
  #   $env:SUPABASE_SERVICE_ROLE_KEY='<chave secreta>'
  #   $env:SUPABASE_DB_URL='postgresql://postgres:<senha>@db.<ref>.supabase.co:5432/postgres'
  .venv\\Scripts\\python.exe supabase\\scripts\\migrar_sqlite.py aplicar --sqlite data\\fintrack.db --uploads data\\uploads --saida relatorio-migracao

Regras
  - Senhas, salts, sessões e tokens antigos NÃO são copiados. As contas são criadas sem senha;
    cada pessoa define uma nova em "Esqueci minha senha" (ou entra com o Google, que o Supabase
    vincula pelo e-mail confirmado).
  - Nada é descartado em silêncio: todo registro ignorado ou ajustado aparece no relatório.
  - O SQLite é aberto somente para leitura.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

NS = uuid.UUID("6f1d3c2a-6a43-4f43-9a0e-0f1a7c5e2b10")  # mesmo namespace de gerar_seed_conteudo.py
BASE = Path(__file__).resolve().parents[2]
INCOME = ["Mesada", "Salário", "Bolsa", "Trabalho eventual", "Vendas", "Presentes", "Outros"]
EXPENSE = ["Alimentação", "Transporte", "Lazer", "Contas", "Saúde", "Educação", "Compras", "Assinaturas", "Outros"]
AUTH_ONLY_TABLES = {"sessions", "reset_tokens", "oauth_states", "google_pending", "email_verifications"}
MAX_CENTS = 100_000_000_000


def lesson_id(module_key, topic_key):
    return str(uuid.uuid5(NS, f"lesson:{module_key}:{topic_key}"))


def video_id(module_key, version):
    return str(uuid.uuid5(NS, f"video:{module_key}:{version}"))


def valid_uuid(v):
    try:
        return str(uuid.UUID(str(v))) == str(v).lower()
    except (ValueError, TypeError):
        return False


def ts(v):
    """Texto ISO do SQLite (sempre UTC, sufixo Z) -> datetime com fuso."""
    if v in (None, ""):
        return None
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def dt(v):
    return date.fromisoformat(str(v)) if v not in (None, "") else None


class Report:
    def __init__(self):
        self.issues = []          # problemas por registro
        self.counts = {}
        self.plan = Counter()

    def issue(self, table, rec_id, kind, detail, action):
        self.issues.append({"tabela": table, "id": str(rec_id), "tipo": kind, "detalhe": detail, "acao": action})


def load(con, table):
    try:
        return [dict(r) for r in con.execute(f'select * from "{table}"')]
    except sqlite3.OperationalError:
        return []


def analyze(sqlite_path: Path):
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rep = Report()
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by 1")]
    for t in tables:
        cols = [c[1] for c in con.execute(f'pragma table_info("{t}")')]
        fks = [{"de": f[3], "para": f"{f[2]}.{f[4]}"} for f in con.execute(f'pragma foreign_key_list("{t}")')]
        rep.counts[t] = {"linhas": con.execute(f'select count(*) from "{t}"').fetchone()[0], "colunas": cols, "fks": fks}
    rep.integrity = con.execute("pragma integrity_check").fetchone()[0]
    rep.fk_violations = [list(r) for r in con.execute("pragma foreign_key_check")]
    rep.migrations = [r[0] for r in con.execute("select version from schema_migrations")] if "schema_migrations" in tables else []

    d = {t: load(con, t) for t in tables}
    users = {u["id"]: u for u in d.get("users", [])}
    emails = Counter(u["email"].lower() for u in users.values())
    for u in users.values():
        if emails[u["email"].lower()] > 1:
            rep.issue("users", u["id"], "duplicado", "e-mail repetido (ignorando caixa)", "conta NÃO criada; revisar manualmente")
        if not valid_uuid(u["id"]):
            rep.issue("users", u["id"], "id", "id não é UUID", "novo UUID; id antigo fica em profiles.legacy_user_id")
        if u.get("role") not in ("aluno", "professor"):
            rep.issue("users", u["id"], "valor", f"papel {u.get('role')!r}", "conta criada sem papel (onboarding pendente)")
        if not u.get("password_hash"):
            rep.issue("users", u["id"], "auth", "conta só Google", "vincula no primeiro login com Google (mesmo e-mail)")

    custom = defaultdict(set)
    for c in d.get("custom_categories", []):
        custom[(c["user_id"], c["type"])].add(c["name"])

    def check_money(table, row, col):
        v = row.get(col)
        if not isinstance(v, int) or v <= 0 or v > MAX_CENTS:
            rep.issue(table, row.get("id"), "valor", f"{col}={v!r}", "registro NÃO importado")
            return False
        return True

    recs = {r["id"]: r for r in d.get("recurrences", [])}
    for r in recs.values():
        if r["user_id"] not in users:
            rep.issue("recurrences", r["id"], "órfão", "conta inexistente", "NÃO importado")
        check_money("recurrences", r, "amount_cents")
    for t in d.get("transactions", []):
        if t["user_id"] not in users:
            rep.issue("transactions", t["id"], "órfão", "conta inexistente", "NÃO importado"); continue
        check_money("transactions", t, "amount_cents")
        base = INCOME if t["type"] == "receita" else EXPENSE
        if t["category"] not in base and t["category"] not in custom[(t["user_id"], t["type"])]:
            rep.issue("transactions", t["id"], "categoria", f"{t['type']}/{t['category']!r} não existe",
                      "cria categoria pessoal com esse nome")
        if t.get("recurrence_id") and t["recurrence_id"] not in recs:
            rep.issue("transactions", t["id"], "órfão", "recorrência inexistente", "importado sem vínculo de recorrência")
        try:
            dt(t["date"])
        except ValueError:
            rep.issue("transactions", t["id"], "data", repr(t["date"]), "NÃO importado")
    occ = Counter((t["recurrence_id"], t["date"]) for t in d.get("transactions", []) if t.get("recurrence_id"))
    for (rid, day), n in occ.items():
        if n > 1:
            rep.issue("transactions", rid, "duplicado", f"{n} ocorrências em {day}", "mantém a mais antiga; demais sem vínculo")

    goals = {g["id"]: g for g in d.get("goals", [])}
    for g in goals.values():
        check_money("goals", g, "target_cents")
    reserved = Counter()
    for e in d.get("goal_reservations", []):
        g = goals.get(e["goal_id"])
        if not g or g["user_id"] != e["user_id"]:
            rep.issue("goal_reservations", e["id"], "órfão", "meta inexistente ou de outra conta", "NÃO importado"); continue
        reserved[e["goal_id"]] += e["amount_cents"] if e["kind"] == "reserva" else -e["amount_cents"]
    for gid, v in reserved.items():
        if v < 0:
            rep.issue("goals", gid, "valor", f"reserva líquida negativa ({v})", "importado como está; revisar")

    lessons = set()
    try:
        sys.path.insert(0, str(BASE))
        import education_content as ec
        lessons = {f"{m['key']}:{t['key']}" for m in ec.EDUCATION for t in m["topics"]}
    except Exception:
        pass
    for p in d.get("education_progress", []):
        if lessons and f"{p['module_key']}:{p['topic_key']}" not in lessons:
            rep.issue("education_progress", f"{p['user_id']}:{p['module_key']}:{p['topic_key']}", "órfão", "aula inexistente", "NÃO importado")
        try:
            json.loads(p.get("answers_json") or "{}")
        except ValueError:
            rep.issue("education_progress", p["user_id"], "json", "answers_json inválido", "importado sem respostas")
    for a in d.get("assignments", []):
        if lessons and a["content_key"] not in lessons:
            rep.issue("assignments", a["id"], "órfão", f"aula {a['content_key']!r}", "NÃO importado")
    for m in d.get("messages", []):
        if m["role"] not in ("user", "assistant"):
            rep.issue("messages", m["id"], "valor", f"papel {m['role']!r}", "NÃO importado")

    for t in sorted(AUTH_ONLY_TABLES & set(tables)):
        rep.plan[f"{t}: não migrado (responsabilidade do Supabase Auth)"] = rep.counts[t]["linhas"]
    con.close()
    return rep, d


def write_report(rep: Report, out: Path, extra=None):
    out.mkdir(parents=True, exist_ok=True)
    data = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "integridade_sqlite": rep.integrity,
            "violacoes_fk_sqlite": rep.fk_violations, "migracoes_sqlite": rep.migrations, "tabelas": rep.counts,
            "ocorrencias": rep.issues, "plano": dict(rep.plan), **(extra or {})}
    (out / "relatorio.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = ["# Relatório de migração SQLite → Supabase", "", f"Gerado em {data['gerado_em']}.",
             f"Integridade do SQLite: **{rep.integrity}**; violações de FK: {len(rep.fk_violations)}; migrações: {rep.migrations}.", "",
             "## Inventário", "", "| Tabela | Linhas | FKs |", "|---|---:|---|"]
    for t, c in rep.counts.items():
        lines.append(f"| `{t}` | {c['linhas']} | {', '.join(f['de'] + '→' + f['para'] for f in c['fks']) or '—'} |")
    lines += ["", f"## Ocorrências ({len(rep.issues)})", ""]
    if rep.issues:
        lines += ["| Tabela | Registro | Tipo | Detalhe | Ação |", "|---|---|---|---|---|"]
        lines += [f"| {i['tabela']} | `{i['id']}` | {i['tipo']} | {i['detalhe']} | {i['acao']} |" for i in rep.issues]
    else:
        lines.append("Nenhum registro inválido, órfão ou duplicado.")
    if rep.plan:
        lines += ["", "## Plano / resultado", ""] + [f"- {k}: {v}" for k, v in rep.plan.items()]
    for k, v in (extra or {}).items():
        lines += ["", f"## {k}", "", "```json", json.dumps(v, ensure_ascii=False, indent=2, default=str), "```"]
    (out / "relatorio.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------- aplicação -----------------------------
def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Defina a variável de ambiente {name} no terminal antes de aplicar.")
    return v


def http(method, url, key, body=None, content_type="application/json", raw=False):
    data = body if raw or body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = r.read()
            return payload if raw and method == "GET" else (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url.split('/v1/')[-1]} -> {e.code}: {e.read()[:300]!r}") from None


def upload(sb, key, bucket, path, data, mime):
    http("POST", f"{sb}/storage/v1/object/{bucket}/{path}", key, data, mime, raw=True)
    got = http("GET", f"{sb}/storage/v1/object/authenticated/{bucket}/{path}", key, raw=True)
    if hashlib.sha256(got).hexdigest() != hashlib.sha256(data).hexdigest():
        raise RuntimeError(f"SHA-256 diferente após envio: {bucket}/{path}")


def find_upload(stored_path, uploads: Path):
    parts = Path(str(stored_path)).parts
    if "uploads" in parts:
        rel = Path(*parts[len(parts) - parts[::-1].index("uploads"):])
        cand = uploads / rel
        if cand.is_file():
            return cand
    return None


def apply(rep: Report, d, uploads: Path, out: Path):
    import psycopg  # requirements-migracao.txt
    sb, key, dburl = env("SUPABASE_URL").rstrip("/"), env("SUPABASE_SERVICE_ROLE_KEY"), env("SUPABASE_DB_URL")
    skip_users = {i["id"] for i in rep.issues if i["tabela"] == "users" and i["tipo"] == "duplicado"}
    bad = {(i["tabela"], i["id"]) for i in rep.issues if i["acao"].startswith("NÃO importado") or i["acao"].startswith("registro NÃO")}
    created, idmap = [], {}
    with psycopg.connect(dburl) as pg:
        # Re-execução segura: contas já migradas são reaproveitadas pelo legacy_user_id.
        for legacy, new in pg.execute("select legacy_user_id, id from public.profiles where legacy_user_id is not null"):
            idmap[legacy] = str(new)
    try:
        for u in d.get("users", []):
            if u["id"] in skip_users or u["id"] in idmap:
                continue
            res = http("POST", f"{sb}/auth/v1/admin/users", key, {
                "email": u["email"].lower(), "email_confirm": bool(u.get("email_verified")),
                "user_metadata": {"name": u["name"], "migrado_de": "fintrack-0.6"}})
            idmap[u["id"]] = res["id"] if "id" in res else res["user"]["id"]
            created.append(idmap[u["id"]])
        rep.plan["contas criadas no Supabase Auth"] = len(created)

        U = lambda legacy: idmap.get(legacy)  # noqa: E731
        with psycopg.connect(dburl) as pg, pg.cursor() as cur:
            cur.execute("select id, type, name from public.categories where user_id is null")
            cat = {(t, n): str(i) for i, t, n in cur.fetchall()}

            def category(user, type_, name):
                k = (user, type_, name)
                if (type_, name) in cat:
                    return cat[(type_, name)]
                if k not in cat:
                    cur.execute("""insert into public.categories (user_id, type, name) values (%s, %s, %s)
                                   on conflict do nothing returning id""", (user, type_, name))
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("select id from public.categories where user_id = %s and type = %s and lower(name) = lower(%s)", (user, type_, name))
                        row = cur.fetchone()
                    cat[k] = str(row[0])
                return cat[k]

            for u in d.get("users", []):
                uid = U(u["id"])
                if not uid:
                    continue
                av = next((a for a in d.get("user_avatars", []) if a["user_id"] == u["id"]), None)
                role = u["role"] if u.get("role") in ("aluno", "professor") else None
                status = "pendente" if role is None else ("concluido" if av else "sem_avatar")
                # O cadastro da 0.6.x só era aceito com os termos marcados: o aceite é datado no cadastro.
                cur.execute("""update public.profiles set name = %s, role = %s, onboarding_status = %s, legacy_user_id = %s,
                               terms_accepted_at = %s, created_at = %s where id = %s""",
                            (u["name"][:100], role, status, u["id"], ts(u["created_at"]) if role else None, ts(u["created_at"]), uid))
                s = next((x for x in d.get("user_settings", []) if x["user_id"] == u["id"]), None)
                if s:
                    cur.execute("""update public.user_settings set theme = %s, chart_type = %s, tips = %s, goal_alerts = %s,
                                   weekly_email = false where user_id = %s""",
                                (s["theme"] if s["theme"] in ("dark", "light") else "dark",
                                 s.get("chart_type") if s.get("chart_type") in ("line", "bar", "pie") else "line",
                                 bool(s["tips"]), bool(s["goal_alerts"]), uid))
                    if s["weekly_email"]:
                        rep.issue("user_settings", u["id"], "valor", "resumo semanal estava ativo",
                                  "importado DESATIVADO; reativar depois de configurar o e-mail")
                p = next((x for x in d.get("reminder_preferences", []) if x["user_id"] == u["id"]), None)
                if p:
                    cur.execute("update public.reminder_preferences set lessons = %s, spending = %s, monthly_budget_cents = %s where user_id = %s",
                                (bool(p["lessons"]), bool(p["spending"]), int(p["monthly_budget_cents"]), uid))
                if av:
                    photo_path = photo_mime = None
                    if av["kind"] == "photo":
                        f = find_upload(av["photo_path"], uploads)
                        if f:
                            photo_path, photo_mime = f"{uid}/{f.name}", av["photo_mime"]
                            upload(sb, key, "avatars", photo_path, f.read_bytes(), photo_mime)
                        else:
                            rep.issue("user_avatars", u["id"], "arquivo", "foto não encontrada", "importado como avatar padrão")
                    cur.execute("""insert into public.user_avatars (user_id, kind, preset, bg, photo_path, photo_mime, updated_at)
                                   values (%s, %s, %s, %s, %s, %s, %s) on conflict (user_id) do nothing""",
                                (uid, "photo" if photo_path else "preset", av["preset"], av["bg"], photo_path, photo_mime, ts(av["updated_at"])))

            for c in d.get("custom_categories", []):
                if U(c["user_id"]):
                    category(U(c["user_id"]), c["type"], c["name"])

            rec_ok = set()
            for r in d.get("recurrences", []):
                if ("recurrences", r["id"]) in bad or not U(r["user_id"]):
                    continue
                cur.execute("""insert into public.recurrences (id, user_id, type, category_id, description, amount_cents, frequency,
                               start_date, next_date, end_date, anchor_day, anchor_month, note, active, created_at)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (r["id"], U(r["user_id"]), r["type"], category(U(r["user_id"]), r["type"], r["category"]), r["description"],
                             r["amount_cents"], r["frequency"], dt(r["start_date"]), dt(r["next_date"]), dt(r["end_date"]),
                             r["anchor_day"], r["anchor_month"], r["note"], bool(r["active"]), ts(r["created_at"])))
                rec_ok.add(r["id"])
            seen_occ = set()
            for t in sorted(d.get("transactions", []), key=lambda x: x["created_at"]):
                if ("transactions", t["id"]) in bad or not U(t["user_id"]):
                    continue
                rid = t.get("recurrence_id") if t.get("recurrence_id") in rec_ok else None
                if rid and (rid, t["date"]) in seen_occ:
                    rid = None
                if rid:
                    seen_occ.add((rid, t["date"]))
                cur.execute("""insert into public.transactions (id, user_id, type, category_id, description, amount_cents, occurred_on,
                               note, recurrence_id, created_at, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (t["id"], U(t["user_id"]), t["type"], category(U(t["user_id"]), t["type"], t["category"]), t["description"],
                             t["amount_cents"], dt(t["date"]), t["note"], rid, ts(t["created_at"]), ts(t["updated_at"])))

            # Metas: o gatilho recusa prazo passado em INSERT; na importação ele é desligado só nesta transação.
            cur.execute("alter table public.goals disable trigger goals_guard")
            for g in d.get("goals", []):
                if ("goals", g["id"]) in bad or not U(g["user_id"]):
                    continue
                cur.execute("""insert into public.goals (id, user_id, title, description, target_cents, deadline, status, completed_at,
                               deleted_at, created_at, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (g["id"], U(g["user_id"]), g["title"], g["description"], g["target_cents"], dt(g["deadline"]), g["status"],
                             ts(g["updated_at"]) if g["status"] == "concluida" else None,
                             ts(g["updated_at"]) if g["status"] == "excluida" else None, ts(g["created_at"]), ts(g["updated_at"])))
            cur.execute("alter table public.goals enable trigger goals_guard")
            for e in d.get("goal_reservations", []):
                if ("goal_reservations", e["id"]) in bad or not U(e["user_id"]):
                    continue
                cur.execute("""insert into public.goal_reservation_events (id, user_id, goal_id, kind, amount_cents, created_at)
                               values (%s,%s,%s,%s,%s,%s)""", (e["id"], U(e["user_id"]), e["goal_id"], e["kind"], e["amount_cents"], ts(e["created_at"])))

            for p in d.get("education_progress", []):
                key_ = f"{p['user_id']}:{p['module_key']}:{p['topic_key']}"
                if ("education_progress", key_) in bad or not U(p["user_id"]):
                    continue
                try:
                    a = json.loads(p.get("answers_json") or "{}")
                except ValueError:
                    a = {}
                cur.execute("""insert into public.education_progress (user_id, lesson_id, status, best_score, last_score, attempts,
                               last_answers, completed_at, updated_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (U(p["user_id"]), lesson_id(p["module_key"], p["topic_key"]), p["status"], p["score"], a.get("last_score"),
                             int(a.get("attempts") or 0), json.dumps(a.get("last")) if a.get("last") is not None else None,
                             ts(p["updated_at"]) if p["status"] == "concluida" else None, ts(p["updated_at"])))
            for v in d.get("education_videos", []):
                if not U(v["user_id"]):
                    continue
                cur.execute("""insert into public.education_video_progress (user_id, video_id, watched_seconds, completed, completed_at)
                               values (%s,%s,%s,%s,%s)""",
                            (U(v["user_id"]), video_id(v["module"], v["version"]), v["watched"], bool(v["completed"]),
                             datetime.now(timezone.utc) if v["completed"] else None))
                if v["completed"]:
                    rep.issue("education_videos", f"{v['user_id']}:{v['module']}", "data", "SQLite não guarda quando concluiu",
                              "completed_at = momento da migração")

            for c in d.get("conversations", []):
                if U(c["user_id"]):
                    cur.execute("insert into public.ai_conversations (id, user_id, title, created_at, updated_at) values (%s,%s,%s,%s,%s)",
                                (c["id"], U(c["user_id"]), c["title"][:80], ts(c["created_at"]), ts(c["updated_at"])))
            for m in d.get("messages", []):
                if ("messages", m["id"]) in bad or not U(m["user_id"]):
                    continue
                cur.execute("""insert into public.ai_messages (id, conversation_id, user_id, role, content, request_key, created_at)
                               values (%s,%s,%s,%s,%s,%s,%s)""", (m["id"], m["conversation_id"], U(m["user_id"]), m["role"], m["content"],
                                                               m["request_key"], ts(m["created_at"])))

            for c in d.get("classes", []):
                if U(c["teacher_id"]):
                    cur.execute("""insert into public.classes (id, teacher_id, name, description, join_code, code_active, created_at)
                                   values (%s,%s,%s,%s,%s,%s,%s)""", (c["id"], U(c["teacher_id"]), c["name"], c["description"], c["code"],
                                                                     bool(c["code_active"]), ts(c["created_at"])))
            for m in d.get("memberships", []):
                if U(m["student_id"]):
                    cur.execute("""insert into public.class_memberships (class_id, student_id, share_financial, joined_at)
                                   values (%s,%s,%s,%s)""", (m["class_id"], U(m["student_id"]), bool(m["share_financial"]), ts(m["created_at"])))
            cur.execute("alter table public.assignments disable trigger assignments_before")  # prazos antigos podem ter passado
            cur.execute("alter table public.assignments disable trigger assignments_after")   # progresso vem do SQLite
            for a in d.get("assignments", []):
                if ("assignments", a["id"]) in bad or not U(a["teacher_id"]):
                    continue
                cur.execute("""insert into public.assignments (id, class_id, teacher_id, lesson_id, content_type, due_date, instructions, created_at)
                               values (%s,%s,%s,%s,'aula',%s,%s,%s)""",
                            (a["id"], a["class_id"], U(a["teacher_id"]), lesson_id(*a["content_key"].split(":", 1)), dt(a["due_date"]),
                             a["instructions"], ts(a["created_at"])))
            cur.execute("alter table public.assignments enable trigger assignments_before")
            cur.execute("alter table public.assignments enable trigger assignments_after")
            classes_of = {a["id"]: a["class_id"] for a in d.get("assignments", []) if ("assignments", a["id"]) not in bad}
            members = {(m["class_id"], m["student_id"]) for m in d.get("memberships", [])}
            for p in d.get("assignment_progress", []):
                cid = classes_of.get(p["assignment_id"])
                if not cid or (cid, p["student_id"]) not in members or not U(p["student_id"]):
                    rep.issue("assignment_progress", f"{p['assignment_id']}:{p['student_id']}", "órfão", "atividade ou vínculo inexistente", "NÃO importado")
                    continue
                cur.execute("""insert into public.assignment_progress (assignment_id, class_id, student_id, status, score, submitted_at)
                               values (%s,%s,%s,%s,%s,%s)""", (p["assignment_id"], cid, U(p["student_id"]), p["status"], p["score"], ts(p["submitted_at"])))

            for r in d.get("receipts", []):
                if not U(r["user_id"]):
                    continue
                f = find_upload(r["private_path"], uploads)
                if not f:
                    rep.issue("receipts", r["id"], "arquivo", "arquivo não encontrado", "NÃO importado"); continue
                data = f.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if r.get("content_sha256") and r["content_sha256"] != digest:
                    rep.issue("receipts", r["id"], "hash", "SHA-256 diferente do registrado", "NÃO importado"); continue
                path = f"{U(r['user_id'])}/{r['id']}{f.suffix}"
                upload(sb, key, "receipts", path, data, r["mime"])
                cur.execute("""insert into public.receipts (id, user_id, storage_path, mime, original_name, size_bytes, sha256, created_at)
                               values (%s,%s,%s,%s,%s,%s,%s,%s) on conflict (user_id, sha256) do nothing""",
                            (r["id"], U(r["user_id"]), path, r["mime"], r["original_name"][:200] or "comprovante", len(data), digest, ts(r["created_at"])))

            for n in d.get("notifications", []):
                if U(n["user_id"]):
                    cur.execute("""insert into public.notifications (id, user_id, event_key, kind, title, body, destination, created_at, read_at)
                                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing""",
                                (n["id"], U(n["user_id"]), n["event_key"], n["kind"], n["title"], n["body"], n["destination"],
                                 ts(n["created_at"]), ts(n["read_at"])))
            for w in d.get("weekly_email_log", []):
                if U(w["user_id"]):
                    cur.execute("insert into private.weekly_email_log (user_id, iso_week, sent_at) values (%s,%s,%s) on conflict do nothing",
                                (U(w["user_id"]), w["week"], ts(w["sent_at"])))

            # Conferência: totais por conta e tipo precisam bater centavo a centavo.
            expected = Counter()
            for t in d.get("transactions", []):
                if ("transactions", t["id"]) not in bad and U(t["user_id"]):
                    expected[(U(t["user_id"]), t["type"])] += t["amount_cents"]
            cur.execute("select user_id::text, type, sum(amount_cents)::bigint from public.transactions where user_id = any(%s::uuid[]) group by 1, 2",
                        (list(idmap.values()),))
            got = Counter({(u, ty): int(s) for u, ty, s in cur.fetchall()})
            diffs = {f"{k[0]}:{k[1]}": {"sqlite": expected[k], "supabase": got.get(k, 0)} for k in expected if expected[k] != got.get(k, 0)}
            if diffs:
                raise RuntimeError(f"Totais divergentes; nada foi gravado: {diffs}")
            rep.plan["totais conferidos (conta x tipo)"] = len(expected)
            pg.commit()
    except Exception:
        rep.plan["ERRO: transação do banco desfeita"] = 1
        if created:
            rep.plan["contas recém-criadas removidas do Auth"] = 0
            for uid in created:
                try:
                    http("DELETE", f"{sb}/auth/v1/admin/users/{uid}", key)
                    rep.plan["contas recém-criadas removidas do Auth"] += 1
                except RuntimeError:
                    pass
        write_report(rep, out, {"mapa_de_ids": idmap})
        raise
    write_report(rep, out, {"mapa_de_ids": idmap})


def send_videos():
    """Envia os 4 MP4 ao bucket education-videos e confere o SHA-256 baixando de volta."""
    sys.path.insert(0, str(BASE))
    from dotenv import load_dotenv
    from supa import Supabase
    load_dotenv(BASE / ".env")
    sb = Supabase(env("SUPABASE_URL"), os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
                  os.environ.get("SUPABASE_SECRET_KEY") or env("SUPABASE_SERVICE_ROLE_KEY"), timeout=180)
    for module in ("poupanca", "controle", "planejamento", "investimentos"):
        data = (BASE / "media" / "education" / f"{module}.mp4").read_bytes()
        path = f"intro/{module}-v1.mp4"
        sb.upload("education-videos", path, data, "video/mp4", upsert=True)
        ok = hashlib.sha256(sb.download("education-videos", path)).hexdigest() == hashlib.sha256(data).hexdigest()
        print(f"{path}: {len(data)} bytes, SHA-256 {'conferido' if ok else 'DIFERENTE'}")
        if not ok:
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["simular", "aplicar", "videos"])
    ap.add_argument("--sqlite", type=Path)
    ap.add_argument("--uploads", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("relatorio-migracao"))
    a = ap.parse_args()
    if a.modo == "videos":
        return send_videos()
    if not a.sqlite or not a.sqlite.is_file():
        ap.error("Informe --sqlite com o caminho do fintrack.db.")
    rep, d = analyze(a.sqlite)
    if a.modo == "simular":
        write_report(rep, a.saida)
        print(f"Simulação concluída: {len(rep.issues)} ocorrência(s). Relatório em {a.saida / 'relatorio.md'}")
        return
    apply(rep, d, a.uploads or a.sqlite.parent / "uploads", a.saida)
    print(f"Migração aplicada. Relatório em {a.saida / 'relatorio.md'}")


if __name__ == "__main__":
    main()
