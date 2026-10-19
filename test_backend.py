"""Run against an isolated server on 8019. Never uses the user's data directory."""
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE/'.runtime')]
os.environ['FINTRACK_DATA_DIR'] = str(BASE/'.work/qa-data')
import app
import backend_services as svc

URL = 'http://127.0.0.1:8019'
passed = []
def ok(name):
    passed.append(name)
    print('PASS', name)
def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(c, path, body=None, method=None, expected=200):
    request = urllib.request.Request(URL+path, data=None if body is None else json.dumps(body).encode(), method=method or ('POST' if body is not None else 'GET'), headers={'Content-Type':'application/json'})
    try:
        with c.open(request, timeout=30) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    assert status == expected, (path, status, raw[:400])
    return json.loads(raw)

student, other = client(), client()
uid_tag = uuid.uuid4().hex[:10]
for c, suffix in [(student,'one'),(other,'two')]:
    req(c, '/api/auth/register', {'name':'Backend QA','email':f'{uid_tag}.{suffix}@example.com','password':'TestingFinTrack2026','role':'aluno','terms':True})
    req(c, '/api/avatar/skip', {})
uid = req(student,'/api/auth/me')['id']
for path in ['/api/market','/api/notifications','/api/notifications/preferences']:
    req(client(), path, expected=401)
ok('New endpoints require authentication')
today = svc.local_today().isoformat()
req(student,'/api/transactions',{'type':'receita','category':'Mesada','description':'QA income','amount':'100','date':today})
gid = req(student,'/api/goals',{'title':'QA deadline','target':'90','deadline':today})['id']
first = req(student,'/api/notifications')
assert len(first['items']) == 1 and first['unread'] == 1
nid = first['items'][0]['id']
assert req(student,'/api/notifications')['total'] == 1
assert req(other,'/api/notifications')['total'] == 0
req(other,f'/api/notifications/{nid}/read',{},expected=404)
req(student,f'/api/notifications/{nid}/read',{})
assert req(student,'/api/notifications')['unread'] == 0
ok('Reminder deduplication, read persistence and cross-account isolation')

def reserve(_):
    try:
        req(student,f'/api/goals/{gid}/reserve',{'amount':'80'})
        return 200
    except AssertionError as e:
        assert e.args[0][1] == 422, e
        return 422
with concurrent.futures.ThreadPoolExecutor(2) as pool:
    assert sorted(pool.map(reserve,range(2))) == [200,422]
assert req(student,'/api/dashboard')['reserved'] == 8000
ok('Simultaneous reservations cannot spend the same balance twice')

req(student,'/api/notifications/preferences',{'lessons':True,'spending':True,'monthly_budget_cents':10000},'PUT')
req(student,'/api/notifications/preferences',{'monthly_budget_cents':-1},'PUT',422)
req(student,'/api/notifications/preferences',{'monthly_budget_cents':1.2},'PUT',422)
req(student,'/api/transactions',{'type':'despesa','category':'Lazer','description':'QA expense','amount':'85','date':today})
assert any('80%' in n['body'] or '85%' in n['body'] for n in req(student,'/api/notifications')['items'])
before = req(student,'/api/notifications')['total']
req(student,'/api/notifications/preferences',{'lessons':False,'spending':False,'monthly_budget_cents':10000},'PUT')
req(student,'/api/transactions',{'type':'despesa','category':'Lazer','description':'QA expense','amount':'20','date':today})
assert req(student,'/api/notifications')['total'] == before
ok('Spending thresholds, preferences and invalid budget validation')

lesson = app.EDUCATION[0]
topic = lesson['topics'][0]
req(student,f"/api/education/{lesson['key']}/{topic['key']}",{'status':'em_andamento'},'PUT')
assert not any(n['kind']=='lesson' for n in req(student,'/api/notifications')['items'])
req(student,'/api/notifications/preferences',{'lessons':True,'spending':False,'monthly_budget_cents':10000},'PUT')
assert sum(n['kind']=='lesson' for n in req(student,'/api/notifications')['items']) == 1
req(student,'/api/notifications/read-all',{})
assert req(student,'/api/notifications')['unread'] == 0
ok('Lesson reminders respect preferences and remain read')

with app.conn() as c:
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    before_users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
svc.migrate(app.conn, app.DB_PATH)
with app.conn() as c:
    assert c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==before_users
    plan=str([tuple(r) for r in c.execute('EXPLAIN QUERY PLAN SELECT * FROM transactions WHERE user_id=? AND type=? AND date BETWEEN ? AND ? ORDER BY date,created_at',(uid,'despesa',today,today))])
    assert 'idx_tx_user_type_date' in plan, plan
closed=app.conn()
with closed:
    closed.execute('SELECT 1')
try:
    closed.execute('SELECT 1')
    raise AssertionError('Connection leaked')
except sqlite3.ProgrammingError:
    pass
dest=svc.backup_database(app.DB_PATH, BASE/'.work/qa-data/verified-backup.db')
with sqlite3.connect(dest) as c:
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==before_users
ok('Migration preserves data, indexes selected, connections closed and backup verified')

# Test source failure and stale fallback without touching the public provider.
original = svc.fetch_indicator
with app.conn() as c:
    c.execute('DELETE FROM market_cache')
svc.fetch_indicator=lambda key: {'key':key,'value':1.5,'observed_at':today}
assert len(svc.market_data(app.conn)['items']) == 4
with app.conn() as c:
    c.execute('UPDATE market_cache SET fetched_at=0')
def fail(key):
    raise OSError('simulated outage')
svc.fetch_indicator=fail
data=svc.market_data(app.conn)
assert len(data['items']) == 4 and all(i['stale'] for i in data['items'])
with app.conn() as c:
    c.execute('DELETE FROM market_cache')
svc._retry_after.clear()
assert len(svc.market_data(app.conn)['unavailable']) == 4
svc.fetch_indicator=original
svc._retry_after.clear()
ok('Market cache persists and source outages have honest fallback')

(BASE/'.work/backend-test-results.json').write_text(json.dumps({'passed':passed},ensure_ascii=False,indent=2),encoding='utf-8')
print('COMPLETE',len(passed),'groups')
