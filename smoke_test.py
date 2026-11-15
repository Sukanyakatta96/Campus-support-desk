import json, os, sys, urllib.error, urllib.request
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'

def call(path, body=None, token=None):
    headers = {'Content-Type': 'application/json', **({'Authorization': f'Bearer {token}'} if token else {})}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return (r.status, json.loads(r.read() or b'{}'))
    except urllib.error.HTTPError as e:
        return (e.code, json.loads(e.read()))

def check(label, ok, detail=''):
    print(f'{('PASS' if ok else 'FAIL')}  {label} {detail}')
    if not ok:
        sys.exit(1)
users = call('/api/login-users')[1]
staff = next((u for u in users if u['role'] == 'support_staff'))
learner = next((u for u in users if u['role'] == 'learner'))
pw = os.environ['CAMPUS_DEMO_PASSWORD']
check('unauthenticated request rejected', call('/api/metrics')[0] == 401)
check('bad password rejected', call('/api/login', {'requester_id': staff['requester_id'], 'password': 'x'})[0] == 401)
st = call('/api/login', {'requester_id': staff['requester_id'], 'password': pw})[1]['token']
lt = call('/api/login', {'requester_id': learner['requester_id'], 'password': pw})[1]['token']
check('staff reads metrics', call('/api/metrics', token=st)[0] == 200)
check('learner blocked from metrics', call('/api/metrics', token=lt)[0] == 403)
s, t = call('/api/tickets', {'category_id': 'CAT-REG-ENR', 'subject': 'add drop deadline', 'body': 'enrollment add drop deadline question'}, lt)
check('learner files grounded request', s == 201 and t['cited_article'] and (not t['escalated']), f'-> {t['ticket_id']} cites {t['cited_article']}')
s, t2 = call('/api/tickets', {'category_id': 'CAT-REG-ENR', 'subject': 'help', 'body': 'zzz'}, lt)
check('ambiguous request escalates', s == 201 and t2['escalated'], f'-> {t2['ticket_id']}')
check('learner cannot resolve', call(f'/api/tickets/{t['ticket_id']}/resolve', {}, lt)[0] == 403)
check('staff resolves with rating', call(f'/api/tickets/{t['ticket_id']}/resolve', {'rating': 5}, st)[0] == 200)
d = call(f'/api/tickets/{t['ticket_id']}', token=st)[1]
check('event history preserved', [e['event_type'] for e in d['events']] == ['CREATED', 'ROUTED', 'ANSWERED', 'RESOLVED'], str([e['event_type'] for e in d['events']]))
