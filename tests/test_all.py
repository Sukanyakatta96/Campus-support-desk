import csv
import sqlite3, unittest, tempfile, os, sys, json, threading, urllib.request, urllib.error
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen
D = tempfile.mkdtemp()
gen.export(D, n_t=600, n_a=60, n_m=2400)
os.environ['CAMPUS_DEMO_PASSWORD'] = 'test-pw'
os.environ['CAMPUS_DB'] = f'{D}/app.db'
os.environ['CAMPUS_GT'] = f'{D}/ground_truth.csv'
import app

class Gen(unittest.TestCase):

    def test_business_hours(self):
        f = lambda s, h: gen.add_bh(datetime.strptime(s, gen.F), h).strftime(gen.F)
        self.assertEqual(f('2026-03-06 16:00:00', 4), '2026-03-09 12:00:00')
        self.assertEqual(f('2026-03-07 10:00:00', 1), '2026-03-09 10:00:00')
        self.assertEqual(f('2026-03-04 09:00:00', 8), '2026-03-04 17:00:00')

    def test_validation_passes(self):
        self.assertTrue(gen.validate(f'{D}/app.db')['passed'])

    def test_reproducible(self):
        a = gen.export(tempfile.mkdtemp(), n_t=100, n_a=30, n_m=400)
        b = gen.export(tempfile.mkdtemp(), n_t=100, n_a=30, n_m=400)
        self.assertEqual(a, b)
        self.assertNotEqual(a, gen.export(tempfile.mkdtemp(), n_t=100, n_a=30, n_m=400, seed=1))

    def test_counts(self):
        d = tempfile.mkdtemp()
        gen.export(d, n_t=600, n_a=60, n_m=2400)
        self.assertEqual(gen.validate(f'{d}/app.db')['counts'], {'ticket': 600, 'message': 2400, 'knowledge_article': 60})

class Audit(unittest.TestCase):

    def test_detectors_match_ground_truth(self):
        for k, v in app.audit().items():
            self.assertGreater(v['ground_truth'], 0, k)
            self.assertEqual((v['precision'], v['recall']), (1.0, 1.0), k)

def http(base, path, body=None, tok=None):
    h = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + tok} if tok else {})}
    r = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r) as x:
            return (x.status, json.loads(x.read()))
    except urllib.error.HTTPError as e:
        return (e.code, json.loads(e.read()))

class Api(unittest.TestCase):

    @classmethod
    def setUpClass(c):
        c.s = app.ThreadingHTTPServer(('127.0.0.1', 0), app.H)
        threading.Thread(target=c.s.serve_forever, daemon=True).start()
        c.u = f'http://127.0.0.1:{c.s.server_port}'
        db = sqlite3.connect(f'{D}/app.db')
        pick = lambda role: db.execute('SELECT requester_id FROM requester q JOIN role r USING(role_id) WHERE r.name=? ORDER BY 1', (role,)).fetchone()[0]
        c.learner_id = pick('learner')
        c.admin_id = pick('platform_administrator')
        login = lambda rid: http(c.u, '/api/login', {'requester_id': rid, 'password': 'test-pw'})[1]['token']
        c.staff, c.learner, c.admin = (login(pick('support_staff')), login(c.learner_id), login(c.admin_id))

    @classmethod
    def tearDownClass(c):
        c.s.shutdown()
        c.s.server_close()

    def call(self, path, body=None, tok='staff'):
        return http(self.u, path, body, getattr(self, tok) if tok else None)

    def test_authentication(self):
        self.assertEqual(self.call('/api/tickets', tok=None)[0], 401)
        self.assertEqual(http(self.u, '/api/login', {'requester_id': self.learner_id, 'password': 'wrong'})[0], 401)
        self.assertEqual(self.call('/api/tickets', tok=None)[0], 401)

    def test_role_based_access(self):
        self.assertEqual(self.call('/api/audit', tok='learner')[0], 403)
        self.assertEqual(self.call('/api/metrics', tok='learner')[0], 403)
        self.assertEqual(self.call('/api/audit', tok='staff')[0], 403)
        self.assertEqual(self.call('/api/audit', tok='admin')[0], 200)
        s, d = self.call('/api/tickets?limit=100', tok='learner')
        self.assertTrue(d['items'] and all((i['requester_id'] == self.learner_id for i in d['items'])))
        other = next((i for i in self.call('/api/tickets?limit=100')[1]['items'] if i['requester_id'] != self.learner_id))['ticket_id']
        self.assertEqual(self.call('/api/tickets/' + other, tok='learner')[0], 403)
        self.assertEqual(self.call(f'/api/tickets/{other}/resolve', {}, tok='learner')[0], 403)

    def test_learner_can_only_file_as_self(self):
        s, r = self.call('/api/tickets', {'requester_id': 'REQ-000999', 'category_id': 'CAT-IT-ACCT', 'subject': 'wifi', 'body': 'campus wifi'}, tok='learner')
        self.assertEqual(s, 201)
        self.assertEqual(self.call('/api/tickets/' + r['ticket_id'], tok='learner')[1]['ticket']['requester_id'], self.learner_id)

    def test_list_and_filter(self):
        s, d = self.call('/api/tickets?status=escalated&domain=IT')
        self.assertEqual(s, 200)
        self.assertTrue(all((i['status'] == 'escalated' and i['domain'] == 'IT' for i in d['items'])))

    def test_create_grounded_then_resolve(self):
        s, r = self.call('/api/tickets', {'requester_id': 'REQ-000001', 'category_id': 'CAT-IT-ACCT', 'subject': 'password reset', 'body': 'multi factor login password reset', 'now': '2026-10-01 10:00:00'})
        self.assertEqual(s, 201)
        self.assertFalse(r['escalated'])
        self.assertTrue(r['cited_article'])
        _, d = self.call('/api/tickets/' + r['ticket_id'])
        self.assertEqual([e['event_type'] for e in d['events']], ['CREATED', 'ROUTED', 'ANSWERED'])
        self.assertEqual(d['assignments'][0]['team_id'], 'TEAM-IT')
        self.assertEqual(self.call(f'/api/tickets/{r['ticket_id']}/resolve', {'rating': 5})[0], 200)
        self.assertEqual(self.call(f'/api/tickets/{r['ticket_id']}/resolve', {})[0], 400)

    def test_ambiguous_escalates(self):
        s, r = self.call('/api/tickets', {'requester_id': 'REQ-000001', 'category_id': 'CAT-FIN-AID', 'subject': 'help', 'body': 'zzz'})
        self.assertTrue(r['escalated'])

    def test_closed_ticket_cannot_be_resolved(self):
        closed = self.call('/api/tickets?status=closed&limit=1')[1]['items'][0]['ticket_id']
        self.assertEqual(self.call(f'/api/tickets/{closed}/resolve', {})[0], 400)

    def test_negative(self):
        self.assertEqual(self.call('/api/tickets', {'requester_id': 'REQ-000001', 'category_id': 'NOPE', 'subject': 'x'})[0], 400)
        self.assertEqual(self.call('/api/tickets', {'category_id': 'CAT-IT-ACCT', 'subject': 'x'})[0], 400)
        self.assertEqual(self.call('/api/tickets/TKT-2026-999999')[0], 404)
        self.assertEqual(self.call('/api/tickets/TKT-2026-999999/resolve', {})[0], 404)
        self.assertEqual(self.call('/api/tickets/TKT-2026-000001/resolve', {'rating': 9})[0], 400)
import re
import shutil
import migrate
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Compliance(unittest.TestCase):
    """Checks the problem statement's coverage, lifecycle, distribution, provenance and ID rules on a 1,000-ticket dataset."""

    @classmethod
    def setUpClass(c):
        c.d = tempfile.mkdtemp()
        gen.export(c.d, n_t=1000, n_a=100, n_m=4000)
        c.db = sqlite3.connect(f'{c.d}/app.db')

    def q(self, sql):
        return self.db.execute(sql).fetchall()

    def test_every_answer_has_answered_event(self):
        self.assertEqual(self.q("SELECT count(DISTINCT m.ticket_id) FROM message m WHERE factual_claim=1")[0][0], self.q("SELECT count(DISTINCT ticket_id) FROM ticket_event WHERE event_type='ANSWERED'")[0][0])

    def test_lifecycle_states_and_events(self):
        states = {r[0] for r in self.q('SELECT DISTINCT status FROM ticket')}
        self.assertTrue({'in_progress', 'escalated', 'resolved', 'closed'} <= states, states)
        self.assertGreater(self.q("SELECT count(*) FROM ticket_event WHERE event_type='CLOSED'")[0][0], 0)

    def test_distributions_are_realistic(self):
        dom = [r[0] for r in self.q('SELECT count(*) FROM ticket t JOIN category g USING(category_id) GROUP BY g.domain')]
        self.assertGreater(max(dom) / min(dom), 1.3)
        self.assertTrue(0.03 < self.q('SELECT avg(breached) FROM sla')[0][0] < 0.25)
        self.assertTrue(0.04 < self.q("SELECT avg(priority='urgent') FROM ticket")[0][0] < 0.12)
        first_weeks = self.q("SELECT count(*) FROM ticket t JOIN term m USING(term_id) WHERE julianday(substr(t.created_at,1,10)) - julianday(m.start_date) < 21")[0][0]
        self.assertGreater(first_weeks / 1000, 0.3)

    def test_edge_cases_present(self):
        for sql in ("SELECT count(*) FROM ticket WHERE is_ambiguous=1", "SELECT count(*) FROM ticket WHERE priority='urgent' AND resolved_at IS NULL", "SELECT count(*) FROM sla WHERE breached=1", "SELECT count(*) FROM knowledge_article WHERE status='superseded'"):
            self.assertGreater(self.q(sql)[0][0], 0, sql)
        types = {r[0] for r in csv.DictReader(open(f'{self.d}/ground_truth.csv'))} if False else {r['issue_type'] for r in csv.DictReader(open(f'{self.d}/ground_truth.csv'))}
        self.assertEqual(len(types), 5)

    def test_ground_truth_never_in_application_database(self):
        tables = {r[0] for r in self.q("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('ground_truth', tables)
        self.assertFalse([1 for t in tables for c in self.q(f'pragma table_info({t})') if c[1] == 'issue_type'])

    def test_id_conventions(self):
        patterns = {'ticket': ('ticket_id', r'TKT-2026-\d{6}'), 'knowledge_article': ('article_id', r'KB-\d{6}'), 'policy_document': ('policy_id', r'POL-(FIN|REG|IT|ACC)-2026-\d{3}'), 'sla': ('sla_id', r'SLA-TKT-2026-\d{6}'), 'message': ('message_id', r'MSG-TKT-2026-\d{6}-\d{3}')}
        for table, (col, rx) in patterns.items():
            bad = [r[0] for r in self.q(f'SELECT {col} FROM {table}') if not re.fullmatch(rx, r[0])]
            self.assertEqual(bad, [], table)

    def test_validator_detects_corruption(self):
        bad = f'{self.d}/bad.db'
        shutil.copy(f'{self.d}/app.db', bad)
        con = sqlite3.connect(bad)
        con.execute("UPDATE ticket SET status='closed' WHERE ticket_id=(SELECT ticket_id FROM ticket WHERE status='resolved' LIMIT 1)")
        con.execute("INSERT INTO message VALUES('MSG-TKT-2026-999999-001','TKT-2026-999999',1,'bot','x',0,'2026-01-01 00:00:00')")
        con.commit()
        con.close()
        report = gen.validate(bad)
        self.assertFalse(report['passed'])
        self.assertGreater(report['closed_status_event_mismatch'], 0)
        self.assertGreater(report['foreign_key_violations'], 0)


class Migrations(unittest.TestCase):
    def test_migration_matches_generator_schema_and_is_idempotent(self):
        self.assertEqual(open(os.path.join(ROOT, 'migrations', '001_init.sql')).read(), gen.DDL)
        db = os.path.join(tempfile.mkdtemp(), 'm.db')
        self.assertEqual(migrate.apply(db, os.path.join(ROOT, 'migrations')), ['001_init.sql'])
        self.assertEqual(migrate.apply(db, os.path.join(ROOT, 'migrations')), [])
        self.assertEqual(sqlite3.connect(db).execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name!='schema_migrations'").fetchone()[0], 13)


if __name__ == '__main__':
    unittest.main()
