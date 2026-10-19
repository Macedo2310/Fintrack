"""Versioned database upgrades, BCB market data and account-scoped reminders."""
import json
import logging
import math
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger("fintrack.services")


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_today():
    # Brasília has used UTC-3 without DST since 2019; no OS timezone dependency.
    return datetime.now(timezone(timedelta(hours=-3))).date()


def backup_database(path, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup reprovado na verificação de integridade")
    finally:
        target.close()
        source.close()
    return destination


def migrate(connect, path):
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            return
    backup_database(path, Path(path).parent / "backups" / ("before-v1-" + uuid.uuid4().hex + ".db"))
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_tx_user_type_date ON transactions(user_id,type,date,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_tx_user_order ON transactions(user_id,date,created_at)",
        "CREATE INDEX IF NOT EXISTS idx_goals_user_status ON goals(user_id,status,deadline)",
        "CREATE INDEX IF NOT EXISTS idx_reservations_goal ON goal_reservations(goal_id,user_id)",
        "CREATE INDEX IF NOT EXISTS idx_reservations_user ON goal_reservations(user_id,goal_id)",
        "CREATE INDEX IF NOT EXISTS idx_recurrences_due ON recurrences(active,next_date)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_reset_expiry ON reset_tokens(expires_at)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id,updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_assignment_student ON assignment_progress(student_id,status)",
        "CREATE INDEX IF NOT EXISTS idx_classes_teacher ON classes(teacher_id)",
        """CREATE TABLE IF NOT EXISTS reminder_preferences(
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            lessons INTEGER NOT NULL DEFAULT 1 CHECK(lessons IN (0,1)),
            spending INTEGER NOT NULL DEFAULT 1 CHECK(spending IN (0,1)),
            monthly_budget_cents INTEGER NOT NULL DEFAULT 0 CHECK(monthly_budget_cents>=0))""",
        """CREATE TABLE IF NOT EXISTS notifications(
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_key TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('goal','lesson','spending')),
            title TEXT NOT NULL, body TEXT NOT NULL, destination TEXT NOT NULL,
            created_at TEXT NOT NULL, read_at TEXT, UNIQUE(user_id,event_key))""",
        "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id) WHERE read_at IS NULL",
        """CREATE TABLE IF NOT EXISTS market_cache(
            key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL)""",
    ]
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            return
        for sql in statements:
            c.execute(sql)
        c.execute("INSERT INTO schema_migrations VALUES(1,?)", (stamp(),))
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Inconsistência de vínculos no banco; migração cancelada")


class ReminderPreferences(BaseModel):
    lessons: bool = True
    spending: bool = True
    monthly_budget_cents: int = Field(default=0, ge=0, le=100_000_000_000, strict=True)


def generate_reminders(connect, uid):
    today = local_today()
    month = today.strftime("%Y-%m")
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR IGNORE INTO reminder_preferences(user_id) VALUES(?)", (uid,))
        prefs = c.execute("SELECT * FROM reminder_preferences WHERE user_id=?", (uid,)).fetchone()
        settings = c.execute("SELECT goal_alerts FROM user_settings WHERE user_id=?", (uid,)).fetchone()
        events = []
        if settings and settings["goal_alerts"]:
            goals = c.execute("""SELECT g.*,COALESCE(SUM(CASE WHEN r.kind='reserva' THEN r.amount_cents ELSE -r.amount_cents END),0) saved
                FROM goals g LEFT JOIN goal_reservations r ON r.goal_id=g.id AND r.user_id=g.user_id
                WHERE g.user_id=? AND g.status='ativa' GROUP BY g.id""", (uid,)).fetchall()
            for g in goals:
                ready = g["saved"] >= g["target_cents"]
                if ready or g["deadline"] <= (today + timedelta(days=7)).isoformat():
                    stage = "ready" if ready else ("overdue" if g["deadline"] < today.isoformat() else "due")
                    title = "Meta pronta para concluir" if ready else "Confira o prazo da sua meta"
                    events.append((f"goal:{g['id']}:{g['deadline']}:{stage}", "goal", title,
                                   f"{g['title']} — " + ("você já reservou o valor planejado." if ready else f"prazo em {g['deadline']}."), "goals"))
        if prefs["lessons"]:
            pending = c.execute("SELECT COUNT(*) FROM education_progress WHERE user_id=? AND status='em_andamento'", (uid,)).fetchone()[0]
            if pending:
                year, week, _ = today.isocalendar()
                events.append((f"lesson:{year}-{week}", "lesson", "Continue seu aprendizado", f"Você tem {pending} aula(s) em andamento. Reserve um momento para continuar.", "education"))
            assignments = c.execute("""SELECT a.id,a.due_date,c.name FROM assignment_progress p
                JOIN assignments a ON a.id=p.assignment_id JOIN classes c ON c.id=a.class_id
                JOIN memberships m ON m.class_id=a.class_id AND m.student_id=p.student_id
                WHERE p.student_id=? AND p.status!='concluida' AND a.due_date IS NOT NULL AND a.due_date<=?""",
                (uid, (today+timedelta(days=3)).isoformat())).fetchall()
            for a in assignments:
                events.append((f"assignment:{a['id']}:{a['due_date']}", "lesson", "Atividade com prazo", f"{a['name']} — entrega em {a['due_date']}. Confira as atividades pendentes.", "classes"))
        if prefs["spending"]:
            totals = c.execute("""SELECT COALESCE(SUM(CASE WHEN type='despesa' THEN amount_cents ELSE 0 END),0) spent,
                COALESCE(SUM(CASE WHEN type='receita' THEN amount_cents ELSE 0 END),0) income
                FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?""", (uid, month+"-01", today.isoformat())).fetchone()
            budget, spent = prefs["monthly_budget_cents"], totals["spent"]
            if budget and spent*100 >= budget*80:
                stage = "100" if spent >= budget else "80"
                events.append((f"budget:{month}:{budget}:{stage}", "spending", "Atenção ao orçamento do mês", f"Suas despesas atingiram {spent*100//budget}% do limite mensal definido por você.", "transactions"))
            elif not budget and spent > totals["income"]:
                events.append((f"spending:{month}", "spending", "Gastos acima das entradas", "As despesas registradas neste mês superam as receitas registradas. Confira seus lançamentos.", "transactions"))
        for key, kind, title, body, destination in events:
            c.execute("""INSERT INTO notifications(id,user_id,event_key,kind,title,body,destination,created_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,event_key) DO NOTHING""",
                (str(uuid.uuid4()), uid, key, kind, title, body, destination, stamp()))


def fetch_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "FinTrack/1.0"})
    with urllib.request.urlopen(req, timeout=8) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Resposta excessiva da fonte")
    return json.loads(raw)


def fetch_indicator(key):
    if key in ("USD", "EUR"):
        today = local_today()
        query = urllib.parse.urlencode({"@moeda": f"'{key}'", "@dataInicial": f"'{(today-timedelta(days=14)):%m-%d-%Y}'",
            "@dataFinalCotacao": f"'{today:%m-%d-%Y}'", "$format": "json", "$top": "1", "$orderby": "dataHoraCotacao desc",
            "$filter": "tipoBoletim eq 'Fechamento'"}, quote_via=urllib.parse.quote)
        url = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)?"+query
        row = fetch_json(url)["value"][0]
        value, observed = float(row["cotacaoVenda"]), row["dataHoraCotacao"][:10]
        label, unit = ("Dólar" if key == "USD" else "Euro"), "BRL · PTAX venda"
    else:
        series, label, unit = {"SELIC": (432, "Meta Selic", "% ao ano"), "IPCA": (433, "IPCA", "% no mês")}[key]
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/1?formato=json"
        rows = fetch_json(url)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Série temporária indisponível no Banco Central")
        row = rows[-1]
        value, observed = float(row["valor"]), datetime.strptime(row["data"], "%d/%m/%Y").date().isoformat()
    if not math.isfinite(value) or (key in ("USD", "EUR") and value <= 0):
        raise ValueError("Valor inválido da fonte")
    datetime.strptime(observed, "%Y-%m-%d")
    return {"key": key, "label": label, "value": value, "unit": unit, "observed_at": observed, "source": "Banco Central do Brasil", "source_url": url}


_market_lock = threading.Lock()
_retry_after = {}


def market_data(connect):
    # One refresh per process; persisted successes survive restarts. Failures back off.
    with _market_lock:
        with connect() as c:
            cached = {r["key"]: dict(r) for r in c.execute("SELECT * FROM market_cache")}
        now = time.time()
        keys = ("USD", "EUR", "SELIC", "IPCA")
        needed = [k for k in keys if (k not in cached or now-cached[k]["fetched_at"] > 3600) and now >= _retry_after.get(k, 0)]
        def refresh(key):
            try:
                return key, fetch_indicator(key)
            except Exception:
                log.warning("Fonte BCB indisponível para %s", key)
                return key, None
        if needed:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(refresh, needed))
            with connect() as c:
                for key, item in results:
                    if item:
                        payload = json.dumps(item, ensure_ascii=False)
                        c.execute("INSERT INTO market_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at", (key, payload, now))
                        cached[key] = {"payload": payload, "fetched_at": now}
                    else:
                        _retry_after[key] = now+300
        items = []
        for key in keys:
            row = cached.get(key)
            if row:
                items.append({**json.loads(row["payload"]), "stale": now-row["fetched_at"] > 3600,
                              "fetched_at": datetime.fromtimestamp(row["fetched_at"], timezone.utc).isoformat()})
        return {"items": items, "unavailable": [k for k in keys if k not in cached]}


def register_routes(app, connect, auth):
    @app.get("/api/market")
    def market(request: Request):
        auth(request)
        return market_data(connect)

    @app.get("/api/notifications/preferences")
    def preferences(request: Request):
        uid = auth(request)["id"]
        with connect() as c:
            c.execute("INSERT OR IGNORE INTO reminder_preferences(user_id) VALUES(?)", (uid,))
            row = dict(c.execute("SELECT lessons,spending,monthly_budget_cents FROM reminder_preferences WHERE user_id=?", (uid,)).fetchone())
        return row

    @app.put("/api/notifications/preferences")
    def save_preferences(body: ReminderPreferences, request: Request):
        uid = auth(request)["id"]
        with connect() as c:
            c.execute("""INSERT INTO reminder_preferences VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                lessons=excluded.lessons,spending=excluded.spending,monthly_budget_cents=excluded.monthly_budget_cents""",
                (uid, int(body.lessons), int(body.spending), body.monthly_budget_cents))
        return body.model_dump()

    @app.get("/api/notifications")
    def notifications(request: Request, page: int = 1):
        uid = auth(request)["id"]
        generate_reminders(connect, uid)
        with connect() as c:
            items = [dict(r) for r in c.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 30 OFFSET ?", (uid, (max(1, min(page, 10000))-1)*30))]
            unread = c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (uid,)).fetchone()[0]
            total = c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=?", (uid,)).fetchone()[0]
        return {"items": items, "unread": unread, "total": total}

    @app.post("/api/notifications/read-all")
    def read_all(request: Request):
        uid = auth(request)["id"]
        with connect() as c:
            c.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (stamp(), uid))
        return {"status": "ok"}

    @app.post("/api/notifications/{notification_id}/read")
    def read_one(notification_id: str, request: Request):
        uid = auth(request)["id"]
        with connect() as c:
            result = c.execute("UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?", (stamp(), notification_id, uid))
            if not result.rowcount:
                raise HTTPException(404, "Lembrete não encontrado.")
        return {"status": "ok"}
