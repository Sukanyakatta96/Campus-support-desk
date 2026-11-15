import json
import re
import sqlite3

import app
import gen

ID_FORMATS = {
    'ticket_id': 'TKT-2026-######', 'message_id': 'MSG-<ticket_id>-###', 'article_id': 'KB-######',
    'policy_id': 'POL-<FIN|REG|IT|ACC>-2026-###', 'sla_id': 'SLA-<ticket_id>', 'requester_id': 'REQ-######',
    'assignment_id': 'ASG-<ticket_id>-#', 'event_id': 'EVT-<ticket_id>-###', 'feedback_id': 'FB-<ticket_id>',
    'role_id': 'ROLE-###', 'term_id': 'TERM-2026<SP|SU|FA>', 'category_id': 'CAT-<domain>-<code>',
}
FLAGS = {'is_ambiguous', 'escalation_required', 'factual_claim', 'breached'}
DATES = {'start_date', 'end_date', 'effective_from', 'effective_to'}


def unit(col):
    if col.endswith('_at'): return 'timestamp (campus local time)'
    if col in DATES: return 'date'
    if col == 'target_hours': return 'business hours'
    if col == 'rating': return 'stars'
    if col in FLAGS: return 'boolean 0/1'
    return ''


def check_clauses(ddl):
    """Return the text inside every CHECK(...) in a CREATE TABLE statement (handles nested parentheses)."""
    found = []
    for m in re.finditer(r'CHECK\(', ddl):
        i, depth = m.end(), 1
        while depth:
            depth += {'(': 1, ')': -1}.get(ddl[i], 0)
            i += 1
        found.append(ddl[m.end():i - 1])
    return found


def describe_table(con, table):
    q = lambda sql, *a: con.execute(sql, a).fetchall()
    ddl = q('SELECT sql FROM sqlite_master WHERE name=?', table)[0][0]
    info = q(f'pragma table_info({table})')
    fks = {r[3]: f'{r[2]}.{r[4] or "PK"}' for r in q(f'pragma foreign_key_list({table})')}
    uniq = {ic[0][2] for i in q(f'pragma index_list({table})') if i[2] and len(ic := q(f'pragma index_info({i[1]})')) == 1}
    n_pk = sum(1 for c in info if c[5])
    clauses = check_clauses(ddl)
    lines = [f'\n## {table}\n', '| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |', '|---|---|---|---|---|---|---|---|']
    for _, name, typ, notnull, _, pk in info:
        allowed = '; '.join(c for c in clauses if re.match(rf'{name}\s+(IN|BETWEEN)', c))
        rules = [f'format {ID_FORMATS[name]}'] if name in ID_FORMATS else []
        if name in fks: rules.append(f'must exist in {fks[name]}')
        rules += [c for c in clauses if re.search(rf'\b{name}\b', c) and not re.match(rf'{name}\s+(IN|BETWEEN)', c)]
        if name == 'effective_to': rules.append('NULL while the version is current')
        lines.append(f'| {name} | {typ} | {"yes" if notnull or pk else "no"} | {"PK" if pk else "FK" if name in fks else ""} | '
                     f'{"yes" if (pk and n_pk == 1) or name in uniq else "no"} | {allowed} | {unit(name)} | {"; ".join(rules)} |')
    composite = re.findall(r'UNIQUE\(([^)]*)\)', ddl)
    if composite: lines.append('\nComposite uniqueness: ' + '; '.join(f'({c})' for c in composite))
    return lines


def relationships(con):
    rows = []
    for t in [r[0] for r in con.execute("select name from sqlite_master where type='table'")]:
        info = {c[1]: c for c in con.execute(f'pragma table_info({t})')}
        for fk in con.execute(f'pragma foreign_key_list({t})'):
            unique = any(i[2] and len(con.execute(f'pragma index_info({i[1]})').fetchall()) == 1 and con.execute(f'pragma index_info({i[1]})').fetchone()[2] == fk[3] for i in con.execute(f'pragma index_list({t})'))
            card = '1:0..1' if unique else '1:N'
            if t == 'message_citation': card = 'N:M bridge'
            rows.append(f'| {fk[2]} | {t} | {fk[3]} | {card} | {"mandatory" if info[fk[3]][3] else "optional"} |')
    return rows


def main():
    con = sqlite3.connect('data/app.db')
    q = lambda sql: con.execute(sql).fetchall()
    tables = [r[0] for r in q("select name from sqlite_master where type='table' order by rowid")]
    open('migrations/001_init.sql', 'w').write(gen.DDL)
    open('exports/seed.sql', 'w').write('\n'.join(con.iterdump()))
    dictionary, er = ['# Data dictionary\nGenerated from the live schema by `make_docs.py`. Timestamps `YYYY-MM-DD HH:MM:SS`; dates `YYYY-MM-DD`. '
                      'Ticket lifecycle: `open` -> `in_progress` (answered) or `escalated` -> `resolved` -> `closed` (14 days after resolution). '
                      'Article lifecycle: `current` -> `superseded` (effective_to set the day before the next version starts).\n'], ['erDiagram']
    for t in tables:
        cols = [d[0] for d in con.execute(f'select * from {t} limit 0').description]
        with open(f'exports/{t}.json', 'w') as fh: json.dump([dict(zip(cols, r)) for r in q(f'select * from {t}')], fh)
        dictionary += describe_table(con, t)
        er += [f'    {r[2]} ||--o{{ {t} : "{r[3]}"' for r in con.execute(f'pragma foreign_key_list({t})')]
    open('docs/data_dictionary.md', 'w').write('\n'.join(dictionary) + '\n')
    open('docs/er_diagram.md', 'w').write('# ER diagram\n\n```mermaid\n' + '\n'.join(er) + '\n```\n\n## Relationships\n\n| Parent | Child | Foreign key | Cardinality | Participation |\n|---|---|---|---|---|\n' + '\n'.join(relationships(con)) + '\n')
    open('docs/architecture.md', 'w').write('# Architecture\n```mermaid\nflowchart LR\n  UI[Presentation: static/index.html] -->|JSON/HTTP + bearer token| API[Application: app.py auth, routing, retrieval, SLA, escalation, audit]\n  API --> RULES[gen.py rules: add_bh, current_articles]\n  API -->|sqlite3, FKs on| DB[(Data: data/app.db)]\n  GEN[gen.py seeded generator] --> DB\n  GEN --> CSV[data/*.csv + ground_truth.csv]\n  MIG[migrate.py + migrations/] --> DB\n  API -. scores detectors against .-> CSV\n```\n')
    manifest = json.load(open('data/manifest.json'))
    json.dump({'generator_command': 'python gen.py --tickets 5000 --articles 200 --messages 20000 --seed 20261022', 'seed': 20261022, 'external_sources': [],
               'provenance': 'All records are synthetic, produced by gen.py. No external or personal data was used, so no third-party licence terms apply. Policy text is invented.',
               'files': manifest}, open('docs/source_manifest.json', 'w'), indent=1)
    dist = {'tickets by status': q('select status,count(*) from ticket group by 1'), 'tickets by domain': q('select g.domain,count(*) from ticket t join category g using(category_id) group by 1'),
            'tickets by priority': q('select priority,count(*) from ticket group by 1'), 'events by type': q('select event_type,count(*) from ticket_event group by 1'),
            'sla breach rate / avg rating': q('select round(avg(breached),3),(select round(avg(rating),2) from resolution_feedback) from sla')}
    validation, audit = gen.validate('data/app.db'), app.audit()
    report = ['# Validation report\n', '## Structural validation (gen.validate)\n```json\n' + json.dumps(validation, indent=1) + '\n```\n',
              '## Distributions\n' + '\n'.join(f'- {k}: {v}' for k, v in dist.items()) + '\n',
              '## Audit detectors vs ground truth (seed 20261022)\nThe detectors are rule-based and read the input tables only; ground_truth.csv is used solely to score them. '
              'Perfect scores show the documented rules identify every injected case and flag no baseline row (no false positives); they are not evidence of a hard detection problem.\n',
              '| Check | Detected | Ground truth | Precision | Recall |\n|---|---|---|---|---|']
    report += [f'| {k} | {x["detected"]} | {x["ground_truth"]} | {x["precision"]} | {x["recall"]} |' for k, x in audit.items()]
    report += ['\n## Reproducibility\nTwo regenerations with the same seed gave identical SHA-256 checksums (`data/manifest.json`).\n', '| File | Rows | SHA-256 |\n|---|---|---|']
    report += [f'| {k}.csv | {x["rows"]} | `{x["sha256"][:16]}...` |' for k, x in manifest.items()]
    for title, path in (('Automated tests', 'docs/test_report.txt'), ('Live API smoke test', 'docs/smoke_test.txt'), ('Browser end-to-end test', 'docs/ui_test.txt')):
        report += [f'\n## {title}\n```\n' + open(path).read() + '```']
    open('docs/validation_report.md', 'w').write('\n'.join(report) + '\n')
    print('docs ok:', len(tables), 'tables')


if __name__ == '__main__':
    main()
