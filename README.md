# Campus Support Desk

Routes student and faculty requests, retrieves policy-grounded answers, and tracks resolution and escalation across financial aid, registration, IT and accessibility.

## Architecture
Three tiers, Python standard library only (no installs):
- **Presentation:** `static/index.html`, a light-theme single-page UI (sign-in, dashboard, ticket list/filters/detail, new request, audit).
- **Application:** `app.py` (auth, role checks, JSON API, routing, policy retrieval, SLA, escalation, audit detectors, logging) and `gen.py` (shared business rules and the seeded generator).
- **Data:** SQLite (`data/app.db`) with PK/FK/CHECK constraints; `migrations/` + `migrate.py` for schema; CSV/JSON/SQL exports.

Diagrams: `docs/architecture.md`, `docs/er_diagram.md` (Mermaid, with cardinality and optionality).

## Folder structure
`gen.py` generator + validator | `app.py` server | `migrate.py` migration runner | `make_docs.py` docs/exports | `smoke_test.py` API check | `ui_test.py` browser test | `tests/` unit, integration, API, DB tests | `data/` CSVs, `ground_truth.csv`, `app.db`, `manifest.json` | `exports/` SQL seed + JSON per table | `migrations/` | `docs/` data dictionary, ER, validation report, test logs, screenshots | `.env.example` | `Dockerfile`

## Setup and run
Prerequisites: Python 3.10+ (browser test additionally needs `pip install playwright` and `playwright install chromium`).
```
cp .env.example .env && export CAMPUS_DEMO_PASSWORD=choose-a-password   # variables are read from the environment
python migrate.py data/new.db            # apply migrations to an empty database (optional)
python gen.py                            # 5,000 tickets / 200 articles / 20,000 messages, seed 20261022 -> data/
python gen.py --tickets 500 --articles 60 --messages 2000 --out data_small   # same generator, starter scale
python make_docs.py                      # regenerate docs, exports, validation report
python app.py                            # http://localhost:8000
```
Config: `PORT`, `CAMPUS_DB`, `CAMPUS_GT`, `CAMPUS_DEMO_PASSWORD`, `LOG_LEVEL`.

## Authentication and roles
Sign in as a listed synthetic user with the shared demo password. Learners/instructors see and file only their own tickets. Support staff, academic administrators and platform administrators see all tickets, resolve them and view metrics; only the two administrator roles see the audit.

## Business rules
- **Routing:** category -> owning team; escalations add a second assignment to `TEAM-ESC` (history is append-only).
- **SLA:** urgent 4h, high 8h, normal 24h, in business hours (Mon-Fri 09:00-17:00).
- **Answers:** cite only articles effective on the ticket date; the cited version is stored in `message_citation`. No matching current article -> treated as ambiguous and escalated.
- **Escalation:** ambiguous requests, and urgent requests left unresolved.
- **Lifecycle:** `open` -> `in_progress` | `escalated` -> `resolved` -> `closed`; every change is an event in `ticket_event`.
- **Anomalies** (about 1% each, labelled only in `ground_truth.csv`): expired policy cited, unauthorized team, unsupported claim, SLA ignoring business hours, escalation not triggered.

## API
`POST /api/login` | `GET /api/login-users` | `GET /api/tickets?status=&domain=&priority=&q=&limit=&offset=` | `GET /api/tickets/{id}` | `POST /api/tickets` | `POST /api/tickets/{id}/resolve` | `GET /api/metrics` | `GET /api/audit` | `GET /api/lookups`

## Testing and validation
```
python -m unittest discover -s tests                 # 21 tests
CAMPUS_DEMO_PASSWORD=... python smoke_test.py http://localhost:8000
CAMPUS_DEMO_PASSWORD=... python ui_test.py http://localhost:8000
```
Results are recorded in `docs/validation_report.md`. `gen.validate` checks PK/FK integrity, ID formats, enums, date ordering, lifecycle/event consistency, SLA and citation reconciliation, duplicates and overlapping article versions.

## Example workflow
A learner files "add drop deadline" -> routed to TEAM-REG, answered with a cited current article version, SLA due time computed in business hours -> staff resolves with a rating -> event history shows CREATED, ROUTED, ANSWERED, RESOLVED. A vague request has no policy match, so it escalates to TEAM-ESC.

## Deployment
`docker build -t campus-support . && docker run -p 8000:8000 -e CAMPUS_DEMO_PASSWORD=... campus-support`. For production, run behind a TLS-terminating reverse proxy and replace the SQLite file with a managed database.

## Requirement traceability
| Requirement | Where |
|---|---|
| Entities, PK/FK, bridge table, cardinality, lifecycle | `gen.DDL`, `docs/er_diagram.md`, `docs/data_dictionary.md` |
| ID conventions, deterministic seed, scale parameters | `gen.py`; tests `test_id_conventions`, `test_reproducible` |
| 5,000 / 200 / 20,000 volumes, edge-case coverage | `data/manifest.json`; `test_edge_cases_present` |
| Labelled anomalies, separate ground truth | `data/ground_truth.csv`; `test_ground_truth_never_in_application_database` |
| Derived values and reconciliation | `gen.validate` (SLA, breach, citation version, events vs status) |
| Answers cite current sources; routing consistent; escalation; version recorded | `/api/audit` detectors; `message_citation.article_version` |
| Metrics | dashboard, `/api/metrics`, audit precision/recall |
| Provenance | `docs/source_manifest.json` (all synthetic, no external data) |

## Known limitations
- Login is a shared demo password with in-memory tokens (no expiry or rate limiting); not production identity management.
- Policy retrieval is keyword overlap, not embeddings; "unsupported claim" detection relies on the `factual_claim` flag set at generation, not language analysis.
- Audit scores are perfect by construction (rule-based detectors against rule-based injection); they show no baseline false positives, not detection difficulty.
- The `open` state appears only in injected escalation-not-triggered cases; generated and live tickets are answered immediately.
- Data dictionary descriptions are schema-derived (type, allowed values, units, rules) with no free-text business definitions per field.
- Browser test covers the happy path on a desktop viewport in Chromium only; no mobile, load or security testing. The Dockerfile was not built here.
- Live tickets use the server clock; the app supports no editing or reassignment of tickets.
