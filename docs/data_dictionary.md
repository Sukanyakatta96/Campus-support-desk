# Data dictionary
Generated from the live schema by `make_docs.py`. Timestamps `YYYY-MM-DD HH:MM:SS`; dates `YYYY-MM-DD`. Ticket lifecycle: `open` -> `in_progress` (answered) or `escalated` -> `resolved` -> `closed` (14 days after resolution). Article lifecycle: `current` -> `superseded` (effective_to set the day before the next version starts).


## role

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| role_id | TEXT | yes | PK | yes |  |  | format ROLE-### |
| name | TEXT | yes |  | yes |  |  |  |

## term

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| term_id | TEXT | yes | PK | yes |  |  | format TERM-2026<SP|SU|FA> |
| name | TEXT | yes |  | no |  |  |  |
| start_date | TEXT | yes |  | no |  | date | end_date>start_date |
| end_date | TEXT | yes |  | no |  | date | end_date>start_date |

## requester

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| requester_id | TEXT | yes | PK | yes |  |  | format REQ-###### |
| full_name | TEXT | yes |  | no |  |  |  |
| email | TEXT | yes |  | yes |  |  |  |
| role_id | TEXT | yes | FK | no |  |  | format ROLE-###; must exist in role.PK |

## category

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| category_id | TEXT | yes | PK | yes |  |  | format CAT-<domain>-<code> |
| domain | TEXT | yes |  | no | domain IN('FIN','REG','IT','ACC') |  |  |
| name | TEXT | yes |  | no |  |  |  |
| owner_team_id | TEXT | yes |  | no |  |  |  |

## policy_document

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| policy_id | TEXT | yes | PK | yes |  |  | format POL-<FIN|REG|IT|ACC>-2026-### |
| domain | TEXT | yes |  | no |  |  |  |
| title | TEXT | yes |  | no |  |  |  |
| owner_team | TEXT | yes |  | no |  |  |  |

## knowledge_article

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| article_id | TEXT | yes | PK | yes |  |  | format KB-###### |
| policy_id | TEXT | yes | FK | no |  |  | format POL-<FIN|REG|IT|ACC>-2026-###; must exist in policy_document.PK |
| domain | TEXT | yes |  | no |  |  |  |
| version | INT | yes |  | no |  |  |  |
| title | TEXT | yes |  | no |  |  |  |
| body | TEXT | yes |  | no |  |  |  |
| effective_from | TEXT | yes |  | no |  | date | effective_to IS NULL OR effective_to>=effective_from |
| effective_to | TEXT | no |  | no |  | date | effective_to IS NULL OR effective_to>=effective_from; NULL while the version is current |
| status | TEXT | yes |  | no | status IN('current','superseded') |  |  |

Composite uniqueness: (policy_id,version)

## ticket

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| ticket_id | TEXT | yes | PK | yes |  |  | format TKT-2026-###### |
| requester_id | TEXT | yes | FK | no |  |  | format REQ-######; must exist in requester.PK |
| category_id | TEXT | yes | FK | no |  |  | format CAT-<domain>-<code>; must exist in category.PK |
| term_id | TEXT | yes | FK | no |  |  | format TERM-2026<SP|SU|FA>; must exist in term.PK |
| priority | TEXT | yes |  | no | priority IN('urgent','high','normal') |  |  |
| subject | TEXT | yes |  | no |  |  |  |
| is_ambiguous | INT | yes |  | no |  | boolean 0/1 |  |
| escalation_required | INT | yes |  | no |  | boolean 0/1 |  |
| status | TEXT | yes |  | no | status IN('open','in_progress','escalated','resolved','closed') |  |  |
| created_at | TEXT | yes |  | no |  | timestamp (campus local time) | resolved_at IS NULL OR resolved_at>=created_at |
| resolved_at | TEXT | no |  | no |  | timestamp (campus local time) | resolved_at IS NULL OR resolved_at>=created_at |

## message

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| message_id | TEXT | yes | PK | yes |  |  | format MSG-<ticket_id>-### |
| ticket_id | TEXT | yes | FK | no |  |  | format TKT-2026-######; must exist in ticket.PK |
| seq | INT | yes |  | no |  |  |  |
| sender_type | TEXT | yes |  | no | sender_type IN('requester','agent','bot') |  |  |
| body | TEXT | yes |  | no |  |  |  |
| factual_claim | INT | yes |  | no |  | boolean 0/1 |  |
| sent_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |

Composite uniqueness: (ticket_id,seq)

## message_citation

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| message_id | TEXT | yes | PK | no |  |  | format MSG-<ticket_id>-###; must exist in message.PK |
| article_id | TEXT | yes | PK | no |  |  | format KB-######; must exist in knowledge_article.PK |
| article_version | INT | yes |  | no |  |  |  |

## assignment

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| assignment_id | TEXT | yes | PK | yes |  |  | format ASG-<ticket_id>-# |
| ticket_id | TEXT | yes | FK | no |  |  | format TKT-2026-######; must exist in ticket.PK |
| team_id | TEXT | yes |  | no |  |  |  |
| assigned_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |
| reason | TEXT | yes |  | no |  |  |  |

## ticket_event

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| event_id | TEXT | yes | PK | yes |  |  | format EVT-<ticket_id>-### |
| ticket_id | TEXT | yes | FK | no |  |  | format TKT-2026-######; must exist in ticket.PK |
| event_type | TEXT | yes |  | no | event_type IN('CREATED','ROUTED','ANSWERED','ESCALATED','RESOLVED','CLOSED') |  |  |
| event_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |

## sla

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| sla_id | TEXT | yes | PK | yes |  |  | format SLA-<ticket_id> |
| ticket_id | TEXT | yes | FK | yes |  |  | format TKT-2026-######; must exist in ticket.PK |
| priority | TEXT | yes |  | no |  |  |  |
| target_hours | INT | yes |  | no |  | business hours |  |
| started_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |
| due_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |
| breached | INT | yes |  | no |  | boolean 0/1 |  |

## resolution_feedback

| Field | Type | Required | Key | Unique | Allowed values / range | Unit | Validation rule |
|---|---|---|---|---|---|---|---|
| feedback_id | TEXT | yes | PK | yes |  |  | format FB-<ticket_id> |
| ticket_id | TEXT | yes | FK | yes |  |  | format TKT-2026-######; must exist in ticket.PK |
| rating | INT | yes |  | no | rating BETWEEN 1 AND 5 | stars |  |
| comment | TEXT | no |  | no |  |  |  |
| submitted_at | TEXT | yes |  | no |  | timestamp (campus local time) |  |
