import csv, hmac, json, logging, os, re, secrets, sqlite3, sys
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from gen import add_bh, current_articles, DOM, TEAM, ESC, SLA_H, F
DB = os.environ.get('CAMPUS_DB', 'data/app.db')
GT = os.environ.get('CAMPUS_GT', 'data/ground_truth.csv')

def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def rows(sql, *a):
    c = con()
    r = [dict(x) for x in c.execute(sql, a)]
    c.close()
    return r

def words(s):
    return set(re.findall('[a-z]{4,}', s.lower()))

def create_ticket(d):
    c = con()
    try:
        for k in ('requester_id', 'category_id', 'subject'):
            if not str(d.get(k, '')).strip():
                raise ValueError(f'{k} is required')
        pr = d.get('priority', 'normal')
        if pr not in SLA_H:
            raise ValueError('priority must be urgent, high or normal')
        cat = c.execute('SELECT * FROM category WHERE category_id=?', (d['category_id'],)).fetchone()
        if not cat or not c.execute('SELECT 1 FROM requester WHERE requester_id=?', (d['requester_id'],)).fetchone():
            raise ValueError('unknown requester or category')
        now = datetime.strptime(d['now'], F) if d.get('now') else datetime.now().replace(microsecond=0)
        n = c.execute('SELECT max(CAST(substr(ticket_id,10) AS INT)) FROM ticket').fetchone()[0] + 1
        tid = f'TKT-2026-{n:06d}'
        text = d['subject'] + ' ' + d.get('body', '')
        arts = [dict(a) for a in c.execute('SELECT * FROM knowledge_article')]
        best = sorted(((len(words(text) & words(a['title'] + ' ' + a['body'])), a) for a in current_articles(arts, cat['domain'], now)), key=lambda x: -x[0])
        art = best[0][1] if best and best[0][0] >= 2 else None
        esc = int(art is None)
        term = c.execute('SELECT term_id FROM term WHERE start_date<=? ORDER BY start_date DESC LIMIT 1', (now.strftime('%Y-%m-%d'),)).fetchone()
        ts = now.strftime(F)
        due = add_bh(now, SLA_H[pr]).strftime(F)
        c.execute('INSERT INTO ticket VALUES(?,?,?,?,?,?,?,?,?,?,NULL)', (tid, d['requester_id'], d['category_id'], term[0] if term else 'TERM-2026FA', pr, d['subject'], esc, esc, 'escalated' if esc else 'in_progress', ts))
        c.execute('INSERT INTO message VALUES(?,?,?,?,?,?,?)', (f'MSG-{tid}-001', tid, 1, 'requester', text, 0, ts))
        if art:
            c.execute('INSERT INTO message VALUES(?,?,?,?,?,?,?)', (f'MSG-{tid}-002', tid, 2, 'bot', f'Per {art['title']}: {art['body']}', 1, ts))
            c.execute('INSERT INTO message_citation VALUES(?,?,?)', (f'MSG-{tid}-002', art['article_id'], art['version']))
        c.execute('INSERT INTO assignment VALUES(?,?,?,?,?)', (f'ASG-{tid}-1', tid, TEAM[cat['domain']], ts, 'category_routing_rule'))
        ev = [('CREATED',), ('ROUTED',)] + ([('ANSWERED',)] if art else []) + ([('ESCALATED',)] if esc else [])
        for i, (e,) in enumerate(ev, 1):
            c.execute('INSERT INTO ticket_event VALUES(?,?,?,?)', (f'EVT-{tid}-{i:03d}', tid, e, ts))
        if esc:
            c.execute('INSERT INTO assignment VALUES(?,?,?,?,?)', (f'ASG-{tid}-2', tid, ESC, ts, 'escalation_rule'))
        c.execute('INSERT INTO sla VALUES(?,?,?,?,?,?,0)', (f'SLA-{tid}', tid, pr, SLA_H[pr], ts, due))
        c.commit()
        return {'ticket_id': tid, 'escalated': bool(esc), 'cited_article': art and art['article_id'], 'due_at': due}
    finally:
        c.close()

def resolve_ticket(tid, d):
    c = con()
    try:
        t = c.execute('SELECT * FROM ticket WHERE ticket_id=?', (tid,)).fetchone()
        if not t:
            raise LookupError('ticket not found')
        if t['status'] in ('resolved', 'closed'):
            raise ValueError('ticket already resolved')
        rating = d.get('rating')
        if rating is not None and rating not in range(1, 6):
            raise ValueError('rating must be 1-5')
        ts = datetime.now().replace(microsecond=0).strftime(F)
        ts = max(ts, t['created_at'])
        s = c.execute('SELECT due_at FROM sla WHERE ticket_id=?', (tid,)).fetchone()
        c.execute("UPDATE ticket SET status='resolved',resolved_at=? WHERE ticket_id=?", (ts, tid))
        c.execute('UPDATE sla SET breached=? WHERE ticket_id=?', (int(ts > s['due_at']), tid))
        n = c.execute('SELECT COALESCE(MAX(CAST(substr(event_id, -3) AS INT)), 0) FROM ticket_event WHERE ticket_id=?', (tid,)).fetchone()[0] + 1
        c.execute('INSERT INTO ticket_event VALUES(?,?,?,?)', (f'EVT-{tid}-{n:03d}', tid, 'RESOLVED', ts))
        if rating:
            c.execute('INSERT INTO resolution_feedback VALUES(?,?,?,?,?)', (f'FB-{tid}', tid, rating, d.get('comment', ''), ts))
        c.commit()
        return {'ticket_id': tid, 'status': 'resolved'}
    finally:
        c.close()

def audit():
    """Rule-based detectors run on input tables only; ground_truth.csv is read solely to score them."""
    c = con()
    det = {}
    det['ANSWER_CITES_EXPIRED_POLICY'] = {r[0] for r in c.execute('SELECT DISTINCT t.ticket_id FROM message_citation x JOIN message m USING(message_id) JOIN ticket t ON t.ticket_id=m.ticket_id JOIN knowledge_article a USING(article_id) WHERE a.effective_from>substr(t.created_at,1,10) OR (a.effective_to IS NOT NULL AND a.effective_to<substr(t.created_at,1,10))')}
    det['TICKET_ROUTED_TO_UNAUTHORIZED_TEAM'] = {r[0] for r in c.execute("SELECT t.ticket_id FROM assignment s JOIN ticket t USING(ticket_id) JOIN category g USING(category_id) WHERE s.team_id NOT IN (g.owner_team_id,'TEAM-ESC')")}
    det['RESPONSE_CLAIMS_UNSUPPORTED_FACT'] = {r[0] for r in c.execute('SELECT ticket_id FROM message m WHERE sender_type!="requester" AND factual_claim=1 AND NOT EXISTS(SELECT 1 FROM message_citation WHERE message_id=m.message_id)')}
    det['SLA_CLOCK_IGNORES_BUSINESS_HOURS'] = {r['ticket_id'] for r in c.execute('SELECT ticket_id,started_at,target_hours,due_at FROM sla') if add_bh(datetime.strptime(r['started_at'], F), r['target_hours']).strftime(F) != r['due_at']}
    det['ESCALATION_NOT_TRIGGERED'] = {r[0] for r in c.execute("SELECT ticket_id FROM ticket t WHERE escalation_required=1 AND NOT EXISTS(SELECT 1 FROM ticket_event WHERE ticket_id=t.ticket_id AND event_type='ESCALATED')")}
    c.close()
    truth = {}
    if os.path.exists(GT):
        for r in csv.DictReader(open(GT)):
            truth.setdefault(r['issue_type'], set()).add(r['ticket_id'])
    out = {}
    for k, found in det.items():
        tr = truth.get(k, set())
        tp = len(found & tr)
        out[k] = dict(detected=len(found), ground_truth=len(tr), precision=round(tp / len(found), 3) if found else None, recall=round(tp / len(tr), 3) if tr else None)
    return out

def metrics():
    one = lambda s: rows(s)[0]
    return dict(by_status=rows('SELECT status,count(*) n FROM ticket GROUP BY status'), by_domain=rows('SELECT g.domain,count(*) n FROM ticket t JOIN category g USING(category_id) GROUP BY 1'), sla_breach_rate=one('SELECT round(avg(breached),3) v FROM sla')['v'], avg_rating=one('SELECT round(avg(rating),2) v FROM resolution_feedback')['v'], escalation_rate=one('SELECT round(avg(status="escalated" OR escalation_required),3) v FROM ticket')['v'], total=one('SELECT count(*) v FROM ticket')['v'])

def detail(tid):
    t = rows('SELECT t.*,g.domain,g.name category FROM ticket t JOIN category g USING(category_id) WHERE ticket_id=?', tid)
    if not t:
        return None
    return dict(ticket=t[0], messages=rows('SELECT m.*,group_concat(c.article_id||" v"||c.article_version) citations FROM message m LEFT JOIN message_citation c USING(message_id) WHERE ticket_id=? GROUP BY m.message_id ORDER BY seq', tid), events=rows('SELECT * FROM ticket_event WHERE ticket_id=? ORDER BY event_id', tid), assignments=rows('SELECT * FROM assignment WHERE ticket_id=?', tid), sla=rows('SELECT * FROM sla WHERE ticket_id=?', tid)[0], feedback=rows('SELECT * FROM resolution_feedback WHERE ticket_id=?', tid))
LOG = logging.getLogger('campus')
STAFF = {'support_staff', 'academic_administrator', 'platform_administrator'}
ADMIN = {'academic_administrator', 'platform_administrator'}
SESSIONS = {}

class AuthError(Exception):
    pass

class Forbidden(Exception):
    pass

def require(user, roles):
    if user['role'] not in roles:
        raise Forbidden('your role is not permitted to do this')

def own_or_staff(user, d):
    if d and user['role'] not in STAFF and (d['ticket']['requester_id'] != user['requester_id']):
        raise Forbidden('not your ticket')

def scoped_body(user, body):
    """Non-staff users can only file requests as themselves and cannot override the clock."""
    if user['role'] in STAFF:
        return body
    return {**{k: v for k, v in body.items() if k != 'now'}, 'requester_id': user['requester_id']}

def login_users():
    return rows('SELECT q.requester_id, r.name role FROM requester q JOIN role r USING(role_id) WHERE (SELECT count(*) FROM requester q2 WHERE q2.role_id=q.role_id AND q2.requester_id<=q.requester_id)<=2 ORDER BY r.role_id, q.requester_id')

def login(d):
    pw = os.environ.get('CAMPUS_DEMO_PASSWORD')
    if not pw:
        raise ValueError('CAMPUS_DEMO_PASSWORD is not configured on the server')
    r = rows('SELECT q.requester_id, r.name role FROM requester q JOIN role r USING(role_id) WHERE q.requester_id=?', str(d.get('requester_id', '')))
    if not r or not hmac.compare_digest(str(d.get('password', '')), pw):
        raise AuthError('invalid credentials')
    tok = secrets.token_urlsafe(24)
    SESSIONS[tok] = r[0]
    return dict(token=tok, staff=r[0]['role'] in STAFF, **r[0])

class H(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        LOG.info('%s %s', self.address_string(), fmt % args)

    def send(self, code, obj, ctype='application/json'):
        b = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def route(self, method):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}') if method == 'POST' else {}
            if p == '/':
                return self.send(200, open('static/index.html').read(), 'text/html')
            if p == '/api/login-users':
                return self.send(200, login_users())
            if p == '/api/login' and method == 'POST':
                return self.send(200, login(body))
            user = self.user()
            if not user:
                return self.send(401, {'error': 'authentication required'})
            if p == '/api/metrics':
                require(user, STAFF)
                return self.send(200, metrics())
            if p == '/api/audit':
                require(user, ADMIN)
                return self.send(200, audit())
            if p == '/api/lookups':
                return self.send(200, dict(categories=rows('SELECT * FROM category'), requesters=rows('SELECT requester_id,full_name FROM requester WHERE ?=1 OR requester_id=? LIMIT 50', int(user['role'] in STAFF), user['requester_id'])))
            if p == '/api/tickets' and method == 'GET':
                w, a = (['1=1'], [])
                if user['role'] not in STAFF:
                    w.append('t.requester_id=?')
                    a.append(user['requester_id'])
                for k, col in (('status', 't.status'), ('domain', 'g.domain'), ('priority', 't.priority')):
                    if q.get(k):
                        w.append(f'{col}=?')
                        a.append(q[k])
                if q.get('q'):
                    w.append('(t.subject LIKE ? OR t.ticket_id LIKE ?)')
                    a += [f'%{q['q']}%'] * 2
                lim = min(int(q.get('limit', 25)), 100)
                off = int(q.get('offset', 0))
                where = ' AND '.join(w)
                tot = rows(f'SELECT count(*) n FROM ticket t JOIN category g USING(category_id) WHERE {where}', *a)[0]['n']
                return self.send(200, dict(total=tot, items=rows(f'SELECT t.ticket_id,t.requester_id,t.subject,t.priority,t.status,t.created_at,g.domain,s.due_at,s.breached FROM ticket t JOIN category g USING(category_id) JOIN sla s USING(ticket_id) WHERE {where} ORDER BY t.created_at DESC LIMIT ? OFFSET ?', *a, lim, off)))
            if p == '/api/tickets' and method == 'POST':
                return self.send(201, create_ticket(scoped_body(user, body)))
            m = re.fullmatch('/api/tickets/(TKT-2026-\\d{6})(/resolve)?', p)
            if m and method == 'GET':
                r = detail(m[1])
                own_or_staff(user, r)
                return self.send(200 if r else 404, r or {'error': 'ticket not found'})
            if m and m[2] and (method == 'POST'):
                require(user, STAFF)
                return self.send(200, resolve_ticket(m[1], body))
            self.send(404, {'error': 'not found'})
        except AuthError as e:
            LOG.warning('authentication failure on %s: %s', p, e)
            self.send(401, {'error': str(e)})
        except Forbidden as e:
            self.send(403, {'error': str(e)})
        except LookupError as e:
            self.send(404, {'error': str(e)})
        except (ValueError, json.JSONDecodeError) as e:
            self.send(400, {'error': str(e)})

    def user(self):
        h = self.headers.get('Authorization', '')
        return SESSIONS.get(h[7:]) if h.startswith('Bearer ') else None

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f'Serving on http://localhost:{port}')
    logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
