import csv, json, random, sqlite3, hashlib, argparse, os, math
from datetime import datetime, timedelta
DOM = {'FIN': 'financial_aid', 'REG': 'registration', 'IT': 'it', 'ACC': 'accessibility'}
TEAM = {d: f'TEAM-{d}' for d in DOM}
ESC = 'TEAM-ESC'
SLA_H = {'urgent': 4, 'high': 8, 'normal': 24}
NOW = datetime(2026, 11, 14, 12)
F = '%Y-%m-%d %H:%M:%S'
CATS = [(f'CAT-{d}-{n}', d, nm) for d, ns in {'FIN': ['AID', 'BILL'], 'REG': ['ENR', 'GRD'], 'IT': ['ACCT', 'LMS'], 'ACC': ['ACCOM', 'ASSIST']}.items() for n, nm in zip(ns, {'AID': 'Aid eligibility', 'BILL': 'Tuition billing', 'ENR': 'Enrollment and add/drop', 'GRD': 'Grades and transcripts', 'ACCT': 'Account access', 'LMS': 'Learning platform', 'ACCOM': 'Exam accommodations', 'ASSIST': 'Assistive technology'}.values()) for n, nm in [(n, nm)]]
TOPICS = {'FIN': ['scholarship refund', 'aid deadline', 'tuition payment plan', 'satisfactory academic progress'], 'REG': ['add drop deadline', 'transcript request', 'course withdrawal', 'enrollment hold'], 'IT': ['password reset', 'multi factor login', 'lms course access', 'campus wifi'], 'ACC': ['extended exam time', 'screen reader support', 'accommodation letter', 'captioning request']}

def add_bh(start, hours):
    """Add business hours (Mon-Fri 09:00-17:00) to a datetime."""
    t, rem = (start, hours * 60)
    while True:
        if t.weekday() >= 5 or t.hour >= 17:
            t = (t + timedelta(days=1)).replace(hour=9, minute=0, second=0)
            continue
        if t.hour < 9:
            t = t.replace(hour=9, minute=0, second=0)
        left = (t.replace(hour=17, minute=0, second=0) - t).total_seconds() / 60
        if rem <= left:
            return t + timedelta(minutes=rem)
        rem -= left
        t = (t + timedelta(days=1)).replace(hour=9, minute=0, second=0)

def current_articles(arts, domain, at):
    d = at.strftime('%Y-%m-%d')
    return [a for a in arts if a['domain'] == domain and a['effective_from'] <= d and (not a['effective_to'] or a['effective_to'] >= d)]

DOM_WEIGHTS = {'FIN': 30, 'REG': 30, 'IT': 25, 'ACC': 15}
TERM_WEIGHTS = [40, 15, 45]
REQUEST_TEXT = ['Hi, I have a question: {s}. Can you help?', 'Following up on this: {s}. This is time sensitive.', '{s} - what is the policy and what do I need to do?', 'I am not sure how to proceed with this: {s}.']
AGENT_TEXT = ['Thanks, we are reviewing this and may need more detail.', 'Could you confirm your student ID and the term this applies to?', 'We have passed this to the responsible team and will update you.', 'Please see the policy above and let us know if that resolves it.']


def draw_created(R, terms):
    """Pick a term, then a timestamp: half of requests cluster in the first weeks of term (deadline surge), most land on weekdays."""
    term = R.choices(terms, TERM_WEIGHTS)[0]
    start = datetime.strptime(term[2], '%Y-%m-%d')
    end = min(datetime.strptime(term[3], '%Y-%m-%d'), datetime(2026, 11, 13))
    span = (end - start).days
    day = min(R.expovariate(1 / 10), span) if R.random() < 0.5 else R.uniform(0, span)
    t = (start + timedelta(days=int(day), hours=R.triangular(7, 21, 12), minutes=R.randint(0, 59))).replace(second=0, microsecond=0)
    if t.weekday() >= 5 and R.random() < 0.7:
        t += timedelta(days=7 - t.weekday())
    return term[0], t


def build(n_t=5000, n_a=200, n_m=20000, seed=20261022):
    R = random.Random(seed)
    T0 = datetime(2026, 1, 5, 9)
    roles = [f'ROLE-{i + 1:03d}' for i in range(5)]
    role_names = ['learner', 'instructor', 'academic_administrator', 'support_staff', 'platform_administrator']
    terms = [('TERM-2026SP', 'Spring 2026', '2026-01-12', '2026-05-08'), ('TERM-2026SU', 'Summer 2026', '2026-05-18', '2026-08-07'), ('TERM-2026FA', 'Fall 2026', '2026-08-24', '2026-12-11')]
    reqs = [dict(requester_id=f'REQ-{i + 1:06d}', full_name=f'Requester {i + 1}', email=f'user{i + 1}@example.edu', role_id=R.choices(roles, [80, 10, 3, 5, 2])[0]) for i in range(max(50, n_t // 5))]
    pols = [dict(policy_id=f'POL-{d}-2026-{k:03d}', domain=DOM[d], domain_code=d, title=f'{DOM[d].replace('_', ' ').title()} Policy {k}', owner_team=TEAM[d]) for d in DOM for k in range(1, 7)]
    nver = math.ceil(n_a / len(pols))
    step = 400 // nver
    arts = []
    for i in range(n_a):
        p = pols[i % len(pols)]
        v = i // len(pols) + 1
        tp = TOPICS[p['domain_code']][i % 4]
        arts.append(dict(article_id=f'KB-{i + 1:06d}', policy_id=p['policy_id'], domain=p['domain_code'], version=v, title=f'{tp.title()} (v{v})', body=f'Under {p['title']} version {v}, requests about {tp} are handled by {p['owner_team']}. Submit documentation and expect review within the published service level.', effective_from=(datetime(2025, 1, 1) + timedelta(days=(v - 1) * step)).strftime('%Y-%m-%d'), effective_to=None, status='current'))
    last = {}
    for a in arts:
        k = a['policy_id']
        if k in last:
            prev = last[k]
            prev['effective_to'] = (datetime.strptime(a['effective_from'], '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            prev['status'] = 'superseded'
        last[k] = a
    T, M, A, EV, S, FB, C, ES = ([], [], [], [], [], [], [], [])
    extra = n_m % n_t
    base = n_m // n_t
    for k in range(1, n_t + 1):
        tid = f'TKT-2026-{k:06d}'
        cat = R.choices(CATS, [DOM_WEIGHTS[c[1]] for c in CATS])[0]
        d = cat[1]
        term, created = draw_created(R, terms)
        pr = R.choices(['urgent', 'high', 'normal'], [8, 20, 72])[0]
        amb = int(R.random() < 0.1)
        tp = R.choice(TOPICS[d])
        unresolved = pr == 'urgent' and R.random() < 0.15
        esc_req = int(amb or unresolved)
        h = SLA_H[pr]
        due = add_bh(created, h)
        esc_at = add_bh(created, 2) if esc_req else None
        res = None if unresolved or (amb and R.random() < 0.5) else add_bh(created, h * R.triangular(0.1, 1.3, 0.45) + (2 if esc_req else 0))
        if res and (res > NOW or (created > NOW - timedelta(days=14) and R.random() < 0.15)):
            res = None
        closed_at = res + timedelta(days=14) if res else None
        status = 'closed' if closed_at and closed_at <= NOW else 'resolved' if res else 'escalated' if esc_req else 'in_progress'
        subj = f'Question about {tp}' if not amb else R.choice(['Need help with my account', 'Something is wrong, please advise', 'Quick question', 'Not sure who to ask'])
        T.append(dict(ticket_id=tid, requester_id=R.choice(reqs)['requester_id'], category_id=cat[0], term_id=term, priority=pr, subject=subj, is_ambiguous=amb, escalation_required=esc_req, status=status, created_at=created.strftime(F), resolved_at=res.strftime(F) if res else None))
        end = res or esc_at or created + timedelta(days=2)
        n = base + (1 if k <= extra else 0)
        n = max(n, 2)
        cur = current_articles(arts, d, created)
        art = None if amb else R.choice(cur)
        ans_at = None
        for i in range(1, n + 1):
            sender = 'requester' if i % 2 == 1 else 'bot' if i == 2 else 'agent'
            ts = created + (end - created) * (i - 1) / n + timedelta(minutes=i)
            claim = int(sender in ('bot', 'agent') and i == 2 and (art is not None))
            mid = f'MSG-{tid}-{i:03d}'
            M.append(dict(message_id=mid, ticket_id=tid, seq=i, sender_type=sender, body=R.choice(REQUEST_TEXT).format(s=subj.lower()) if sender == 'requester' else f'Per {art['title']}: {art['body']}' if claim else R.choice(AGENT_TEXT), factual_claim=claim, sent_at=ts.strftime(F)))
            if claim:
                C.append(dict(message_id=mid, article_id=art['article_id'], article_version=art['version']))
                ans_at = ts
        team = TEAM[d]
        A.append(dict(assignment_id=f'ASG-{tid}-1', ticket_id=tid, team_id=team, assigned_at=(created + timedelta(minutes=1)).strftime(F), reason='category_routing_rule'))
        evs = [('CREATED', created), ('ROUTED', created + timedelta(minutes=1))] + ([('ANSWERED', ans_at)] if art else [])
        if esc_req:
            A.append(dict(assignment_id=f'ASG-{tid}-2', ticket_id=tid, team_id=ESC, assigned_at=esc_at.strftime(F), reason='escalation_rule'))
            evs.append(('ESCALATED', esc_at))
        if res:
            evs.append(('RESOLVED', res))
        if status == 'closed':
            evs.append(('CLOSED', closed_at))
        for i, (etype, at) in enumerate(sorted(evs, key=lambda e: e[1]), 1):
            EV.append(dict(event_id=f'EVT-{tid}-{i:03d}', ticket_id=tid, event_type=etype, event_at=at.strftime(F)))
        breached = int((res or NOW) > due)
        S.append(dict(sla_id=f'SLA-{tid}', ticket_id=tid, priority=pr, target_hours=h, started_at=created.strftime(F), due_at=due.strftime(F), breached=breached))
        if res and R.random() < 0.7:
            FB.append(dict(feedback_id=f'FB-{tid}', ticket_id=tid, rating=2 + R.randint(0, 1) if breached else R.choice([4, 5, 5]), comment='auto-generated synthetic feedback', submitted_at=(res + timedelta(hours=3)).strftime(F)))
    tix = {t['ticket_id']: t for t in T}
    used = set()
    GT = []
    q = max(1, n_t // 100)

    def pick(pred):
        c = [t for t in T if t['ticket_id'] not in used and pred(t)]
        R.shuffle(c)
        c = c[:q]
        used.update((t['ticket_id'] for t in c))
        return c
    cited = {m['ticket_id']: m for m in M if m['factual_claim']}
    cit = {c['message_id']: c for c in C}
    expired = [a for a in arts if a['effective_to']]
    for t in pick(lambda t: t['ticket_id'] in cited and t['is_ambiguous'] == 0):
        d = [c for c in CATS if c[0] == t['category_id']][0][1]
        ex = [a for a in expired if a['domain'] == d and a['effective_to'] < t['created_at'][:10]]
        if ex:
            a = R.choice(ex)
            cit[cited[t['ticket_id']]['message_id']].update(article_id=a['article_id'], article_version=a['version'])
            GT.append((t['ticket_id'], cited[t['ticket_id']]['message_id'], 'ANSWER_CITES_EXPIRED_POLICY'))
    for t in pick(lambda t: t['is_ambiguous'] == 0):
        d = [c for c in CATS if c[0] == t['category_id']][0][1]
        a1 = [a for a in A if a['ticket_id'] == t['ticket_id']][0]
        a1['team_id'] = TEAM[R.choice([x for x in DOM if x != d])]
        GT.append((t['ticket_id'], a1['assignment_id'], 'TICKET_ROUTED_TO_UNAUTHORIZED_TEAM'))
    for t in pick(lambda t: t['ticket_id'] in cited and t['is_ambiguous'] == 0):
        m = cited[t['ticket_id']]
        C[:] = [c for c in C if c['message_id'] != m['message_id']]
        m['body'] = 'Per policy, this is always approved automatically within one hour.'
        GT.append((t['ticket_id'], m['message_id'], 'RESPONSE_CLAIMS_UNSUPPORTED_FACT'))
    sla = {s['ticket_id']: s for s in S}
    for t in pick(lambda t: add_bh(datetime.strptime(t['created_at'], F), SLA_H[t['priority']]) != datetime.strptime(t['created_at'], F) + timedelta(hours=SLA_H[t['priority']])):
        s = sla[t['ticket_id']]
        s['due_at'] = (datetime.strptime(t['created_at'], F) + timedelta(hours=s['target_hours'])).strftime(F)
        s['breached'] = int((datetime.strptime(t['resolved_at'], F) if t['resolved_at'] else NOW) > datetime.strptime(s['due_at'], F))
        GT.append((t['ticket_id'], s['sla_id'], 'SLA_CLOCK_IGNORES_BUSINESS_HOURS'))
    for t in pick(lambda t: t['escalation_required'] == 1 and t['status'] == 'escalated'):
        A[:] = [a for a in A if a['assignment_id'] != f'ASG-{t['ticket_id']}-2']
        EV[:] = [e for e in EV if not (e['ticket_id'] == t['ticket_id'] and e['event_type'] == 'ESCALATED')]
        t['status'] = 'open'
        GT.append((t['ticket_id'], t['ticket_id'], 'ESCALATION_NOT_TRIGGERED'))
    cats = [dict(category_id=c[0], domain=c[1], name=c[2], owner_team_id=TEAM[c[1]]) for c in CATS]
    tabs = dict(role=[dict(role_id=r, name=n) for r, n in zip(roles, role_names)], term=[dict(term_id=a, name=b, start_date=c, end_date=d) for a, b, c, d in terms], requester=reqs, category=cats, policy_document=[{k: v for k, v in p.items() if k != 'domain_code'} for p in pols], knowledge_article=arts, ticket=T, message=M, message_citation=C, assignment=A, ticket_event=EV, sla=S, resolution_feedback=FB)
    return (tabs, [dict(ticket_id=a, entity_id=b, issue_type=c) for a, b, c in GT])
DDL = "PRAGMA foreign_keys=ON;\nCREATE TABLE role(role_id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE);\nCREATE TABLE term(term_id TEXT PRIMARY KEY,name TEXT NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL CHECK(end_date>start_date));\nCREATE TABLE requester(requester_id TEXT PRIMARY KEY,full_name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,role_id TEXT NOT NULL REFERENCES role);\nCREATE TABLE category(category_id TEXT PRIMARY KEY,domain TEXT NOT NULL CHECK(domain IN('FIN','REG','IT','ACC')),name TEXT NOT NULL,owner_team_id TEXT NOT NULL);\nCREATE TABLE policy_document(policy_id TEXT PRIMARY KEY,domain TEXT NOT NULL,title TEXT NOT NULL,owner_team TEXT NOT NULL);\nCREATE TABLE knowledge_article(article_id TEXT PRIMARY KEY,policy_id TEXT NOT NULL REFERENCES policy_document,domain TEXT NOT NULL,version INT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,effective_from TEXT NOT NULL,effective_to TEXT,status TEXT NOT NULL CHECK(status IN('current','superseded')),UNIQUE(policy_id,version),CHECK(effective_to IS NULL OR effective_to>=effective_from));\nCREATE TABLE ticket(ticket_id TEXT PRIMARY KEY,requester_id TEXT NOT NULL REFERENCES requester,category_id TEXT NOT NULL REFERENCES category,term_id TEXT NOT NULL REFERENCES term,priority TEXT NOT NULL CHECK(priority IN('urgent','high','normal')),subject TEXT NOT NULL,is_ambiguous INT NOT NULL,escalation_required INT NOT NULL,status TEXT NOT NULL CHECK(status IN('open','in_progress','escalated','resolved','closed')),created_at TEXT NOT NULL,resolved_at TEXT,CHECK(resolved_at IS NULL OR resolved_at>=created_at));\nCREATE TABLE message(message_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES ticket,seq INT NOT NULL,sender_type TEXT NOT NULL CHECK(sender_type IN('requester','agent','bot')),body TEXT NOT NULL,factual_claim INT NOT NULL,sent_at TEXT NOT NULL,UNIQUE(ticket_id,seq));\nCREATE TABLE message_citation(message_id TEXT NOT NULL REFERENCES message,article_id TEXT NOT NULL REFERENCES knowledge_article,article_version INT NOT NULL,PRIMARY KEY(message_id,article_id));\nCREATE TABLE assignment(assignment_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES ticket,team_id TEXT NOT NULL,assigned_at TEXT NOT NULL,reason TEXT NOT NULL);\nCREATE TABLE ticket_event(event_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES ticket,event_type TEXT NOT NULL CHECK(event_type IN('CREATED','ROUTED','ANSWERED','ESCALATED','RESOLVED','CLOSED')),event_at TEXT NOT NULL);\nCREATE TABLE sla(sla_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL UNIQUE REFERENCES ticket,priority TEXT NOT NULL,target_hours INT NOT NULL,started_at TEXT NOT NULL,due_at TEXT NOT NULL,breached INT NOT NULL);\nCREATE TABLE resolution_feedback(feedback_id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL UNIQUE REFERENCES ticket,rating INT NOT NULL CHECK(rating BETWEEN 1 AND 5),comment TEXT,submitted_at TEXT NOT NULL);\n"

def export(out, **kw):
    os.makedirs(out, exist_ok=True)
    tabs, gt = build(**kw)
    sums = {}
    for n, rows in list(tabs.items()) + [('ground_truth', gt)]:
        p = os.path.join(out, f'{n}.csv')
        with open(p, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
        with open(p, 'rb') as fh:
            sums[n] = dict(rows=len(rows), sha256=hashlib.sha256(fh.read()).hexdigest())
    db = os.path.join(out, 'app.db')
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.executescript(DDL)
    for n, rows in tabs.items():
        con.executemany(f'INSERT INTO {n}({','.join(rows[0])}) VALUES({','.join('?' * len(rows[0]))})', [tuple(r.values()) for r in rows])
    con.commit()
    con.close()
    with open(os.path.join(out, 'manifest.json'), 'w') as fh:
        json.dump(sums, fh, indent=1)
    return sums

def validate(db):
    con = sqlite3.connect(db)
    q = lambda s: con.execute(s).fetchall()
    r = {}
    r['foreign_key_violations'] = len(q('PRAGMA foreign_key_check'))
    r['ticket_id_format_bad'] = q("SELECT count(*) FROM ticket WHERE ticket_id NOT GLOB 'TKT-2026-[0-9][0-9][0-9][0-9][0-9][0-9]'")[0][0]
    r['message_id_mismatch'] = q("SELECT count(*) FROM message WHERE message_id != 'MSG-'||ticket_id||'-'||printf('%03d',seq)")[0][0]
    r['message_before_ticket'] = q('SELECT count(*) FROM message m JOIN ticket t USING(ticket_id) WHERE m.sent_at<t.created_at')[0][0]
    r['resolved_without_timestamp'] = q("SELECT count(*) FROM ticket WHERE (status IN ('resolved','closed'))!=(resolved_at IS NOT NULL)")[0][0]
    r['one_current_version_per_policy'] = q('SELECT count(*) FROM (SELECT policy_id FROM knowledge_article WHERE effective_to IS NULL GROUP BY policy_id HAVING count(*)!=1)')[0][0]
    r['sla_without_ticket'] = q('SELECT count(*) FROM ticket t LEFT JOIN sla s USING(ticket_id) WHERE s.sla_id IS NULL')[0][0]
    one = lambda sql: q(sql)[0][0]
    r['sla_target_mismatch'] = one("SELECT count(*) FROM sla WHERE target_hours != CASE priority WHEN 'urgent' THEN 4 WHEN 'high' THEN 8 ELSE 24 END")
    r['sla_start_mismatch'] = one('SELECT count(*) FROM sla s JOIN ticket t USING(ticket_id) WHERE s.started_at != t.created_at')
    r['sla_breach_not_reconciled'] = one("SELECT count(*) FROM sla s JOIN ticket t USING(ticket_id) WHERE s.breached != (COALESCE(t.resolved_at,'2026-11-14 12:00:00') > s.due_at)")
    r['citation_version_mismatch'] = one('SELECT count(*) FROM message_citation c JOIN knowledge_article a USING(article_id) WHERE c.article_version != a.version')
    r['message_seq_gaps'] = one('SELECT count(*) FROM (SELECT 1 FROM message GROUP BY ticket_id HAVING max(seq) != count(*))')
    r['resolved_status_event_mismatch'] = one("SELECT count(*) FROM ticket t WHERE (t.status IN ('resolved','closed')) != EXISTS(SELECT 1 FROM ticket_event e WHERE e.ticket_id=t.ticket_id AND e.event_type='RESOLVED' AND e.event_at=t.resolved_at)")
    r['closed_status_event_mismatch'] = one("SELECT count(*) FROM ticket t WHERE (t.status='closed') != EXISTS(SELECT 1 FROM ticket_event e WHERE e.ticket_id=t.ticket_id AND e.event_type='CLOSED')")
    r['events_out_of_order'] = one('SELECT count(*) FROM ticket_event a JOIN ticket_event b ON a.ticket_id=b.ticket_id AND a.event_id<b.event_id AND a.event_at>b.event_at')
    r['events_after_closed'] = one("SELECT count(*) FROM ticket_event c JOIN ticket_event e ON c.ticket_id=e.ticket_id AND c.event_type='CLOSED' AND e.event_id>c.event_id")
    r['ambiguous_not_flagged_for_escalation'] = one('SELECT count(*) FROM ticket WHERE is_ambiguous=1 AND escalation_required=0')
    r['ticket_outside_term'] = one('SELECT count(*) FROM ticket t JOIN term m USING(term_id) WHERE substr(t.created_at,1,10) NOT BETWEEN m.start_date AND m.end_date')
    r['duplicate_tickets'] = one('SELECT count(*) FROM (SELECT 1 FROM ticket GROUP BY requester_id, subject, created_at HAVING count(*)>1)')
    r['overlapping_article_versions'] = one('SELECT count(*) FROM knowledge_article a JOIN knowledge_article b ON a.policy_id=b.policy_id AND a.version<b.version AND (a.effective_to IS NULL OR a.effective_to>=b.effective_from)')
    r['counts'] = {t: q(f'SELECT count(*) FROM {t}')[0][0] for t in ('ticket', 'message', 'knowledge_article')}
    r['passed'] = all((v == 0 for k, v in r.items() if k not in ('counts', 'passed')))
    return r
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--tickets', type=int, default=5000)
    ap.add_argument('--articles', type=int, default=200)
    ap.add_argument('--messages', type=int, default=20000)
    ap.add_argument('--seed', type=int, default=20261022)
    ap.add_argument('--out', default='data')
    a = ap.parse_args()
    s = export(a.out, n_t=a.tickets, n_a=a.articles, n_m=a.messages, seed=a.seed)
    print(json.dumps(validate(os.path.join(a.out, 'app.db')), indent=1))
