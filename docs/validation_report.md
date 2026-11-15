# Validation report

## Structural validation (gen.validate)
```json
{
 "foreign_key_violations": 0,
 "ticket_id_format_bad": 0,
 "message_id_mismatch": 0,
 "message_before_ticket": 0,
 "resolved_without_timestamp": 0,
 "one_current_version_per_policy": 0,
 "sla_without_ticket": 0,
 "sla_target_mismatch": 0,
 "sla_start_mismatch": 0,
 "sla_breach_not_reconciled": 0,
 "citation_version_mismatch": 0,
 "message_seq_gaps": 0,
 "resolved_status_event_mismatch": 0,
 "closed_status_event_mismatch": 0,
 "events_out_of_order": 0,
 "events_after_closed": 0,
 "ambiguous_not_flagged_for_escalation": 0,
 "ticket_outside_term": 0,
 "duplicate_tickets": 0,
 "overlapping_article_versions": 0,
 "counts": {
  "ticket": 5000,
  "message": 20000,
  "knowledge_article": 200
 },
 "passed": true
}
```

## Distributions
- tickets by status: [('closed', 4476), ('escalated', 286), ('in_progress', 27), ('open', 50), ('resolved', 161)]
- tickets by domain: [('ACC', 776), ('FIN', 1460), ('IT', 1284), ('REG', 1480)]
- tickets by priority: [('high', 988), ('normal', 3634), ('urgent', 378)]
- events by type: [('ANSWERED', 4474), ('CLOSED', 4476), ('CREATED', 5000), ('ESCALATED', 524), ('RESOLVED', 4637), ('ROUTED', 5000)]
- sla breach rate / avg rating: [(0.161, 4.46)]

## Audit detectors vs ground truth (seed 20261022)
The detectors are rule-based and read the input tables only; ground_truth.csv is used solely to score them. Perfect scores show the documented rules identify every injected case and flag no baseline row (no false positives); they are not evidence of a hard detection problem.

| Check | Detected | Ground truth | Precision | Recall |
|---|---|---|---|---|
| ANSWER_CITES_EXPIRED_POLICY | 50 | 50 | 1.0 | 1.0 |
| TICKET_ROUTED_TO_UNAUTHORIZED_TEAM | 50 | 50 | 1.0 | 1.0 |
| RESPONSE_CLAIMS_UNSUPPORTED_FACT | 50 | 50 | 1.0 | 1.0 |
| SLA_CLOCK_IGNORES_BUSINESS_HOURS | 50 | 50 | 1.0 | 1.0 |
| ESCALATION_NOT_TRIGGERED | 50 | 50 | 1.0 | 1.0 |

## Reproducibility
Two regenerations with the same seed gave identical SHA-256 checksums (`data/manifest.json`).

| File | Rows | SHA-256 |
|---|---|---|
| role.csv | 5 | `81d3a3d6c5f769b1...` |
| term.csv | 3 | `c7afe34625e8afdb...` |
| requester.csv | 1000 | `d7e811b75a012b53...` |
| category.csv | 8 | `c306135a41f295be...` |
| policy_document.csv | 24 | `e81b268cb4077aeb...` |
| knowledge_article.csv | 200 | `93178cac51e50059...` |
| ticket.csv | 5000 | `6ff8b6d42b0da3e8...` |
| message.csv | 20000 | `595cd87b0f55d9a0...` |
| message_citation.csv | 4424 | `9b40096dc57ca166...` |
| assignment.csv | 5524 | `b5ce988ef7cd13a0...` |
| ticket_event.csv | 24111 | `767a4e0055aa5c77...` |
| sla.csv | 5000 | `fcac57e4841c313b...` |
| resolution_feedback.csv | 3243 | `f64c2412e844c0c0...` |
| ground_truth.csv | 250 | `2229118dd1d83a57...` |

## Automated tests
```
test_ambiguous_escalates (test_all.Api.test_ambiguous_escalates) ... ok
test_authentication (test_all.Api.test_authentication) ... authentication failure on /api/login: invalid credentials
ok
test_closed_ticket_cannot_be_resolved (test_all.Api.test_closed_ticket_cannot_be_resolved) ... ok
test_create_grounded_then_resolve (test_all.Api.test_create_grounded_then_resolve) ... ok
test_learner_can_only_file_as_self (test_all.Api.test_learner_can_only_file_as_self) ... ok
test_list_and_filter (test_all.Api.test_list_and_filter) ... ok
test_negative (test_all.Api.test_negative) ... ok
test_role_based_access (test_all.Api.test_role_based_access) ... /home/claude/campus_support/app.py:102: ResourceWarning: unclosed file <_io.TextIOWrapper name='/tmp/tmpxswsf6kp/ground_truth.csv' mode='r' encoding='utf-8'>
  for r in csv.DictReader(open(GT)):
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok
test_detectors_match_ground_truth (test_all.Audit.test_detectors_match_ground_truth) ... ok
test_distributions_are_realistic (test_all.Compliance.test_distributions_are_realistic) ... ok
test_edge_cases_present (test_all.Compliance.test_edge_cases_present) ... /home/claude/campus_support/tests/test_all.py:161: ResourceWarning: unclosed file <_io.TextIOWrapper name='/tmp/tmpspgmb5f1/ground_truth.csv' mode='r' encoding='utf-8'>
  types = {r[0] for r in csv.DictReader(open(f'{self.d}/ground_truth.csv'))} if False else {r['issue_type'] for r in csv.DictReader(open(f'{self.d}/ground_truth.csv'))}
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok
test_every_answer_has_answered_event (test_all.Compliance.test_every_answer_has_answered_event) ... ok
test_ground_truth_never_in_application_database (test_all.Compliance.test_ground_truth_never_in_application_database) ... ok
test_id_conventions (test_all.Compliance.test_id_conventions) ... ok
test_lifecycle_states_and_events (test_all.Compliance.test_lifecycle_states_and_events) ... ok
test_validator_detects_corruption (test_all.Compliance.test_validator_detects_corruption) ... ok
test_business_hours (test_all.Gen.test_business_hours) ... ok
test_counts (test_all.Gen.test_counts) ... ok
test_reproducible (test_all.Gen.test_reproducible) ... ok
test_validation_passes (test_all.Gen.test_validation_passes) ... ok
test_migration_matches_generator_schema_and_is_idempotent (test_all.Migrations.test_migration_matches_generator_schema_and_is_idempotent) ... /home/claude/campus_support/tests/test_all.py:191: ResourceWarning: unclosed file <_io.TextIOWrapper name='/home/claude/campus_support/migrations/001_init.sql' mode='r' encoding='utf-8'>
  self.assertEqual(open(os.path.join(ROOT, 'migrations', '001_init.sql')).read(), gen.DDL)
ResourceWarning: Enable tracemalloc to get the object allocation traceback
/home/claude/campus_support/migrate.py:20: ResourceWarning: unclosed file <_io.TextIOWrapper name='/home/claude/campus_support/migrations/001_init.sql' mode='r' encoding='utf-8'>
  con.executescript(open(path).read())
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok

----------------------------------------------------------------------
Ran 21 tests in 1.765s

OK
```

## Live API smoke test
```
PASS  unauthenticated request rejected 
PASS  bad password rejected 
PASS  staff reads metrics 
PASS  learner blocked from metrics 
PASS  learner files grounded request -> TKT-2026-005001 cites KB-000177
PASS  ambiguous request escalates -> TKT-2026-005002
PASS  learner cannot resolve 
PASS  staff resolves with rating 
PASS  event history preserved ['CREATED', 'ROUTED', 'ANSWERED', 'RESOLVED']
```

## Browser end-to-end test
```
PASS  wrong password shows an error
PASS  learner sees only Tickets and New request
PASS  learner files a request and gets a cited answer
PASS  staff dashboard loads metrics
PASS  staff does not see the admin-only Audit tab
PASS  staff filters, opens and resolves a ticket with rating
PASS  administrator sees the 5-check audit
PASS  no JavaScript errors
```
