# stockbit-event-annotation

Pulls Stockbit corporate actions and insider movements and builds `idx_event_annotation`, the one source EDGE chart
annotations read (EXEC-EVENT-ANNOTATION, user decisions in `PLAN.md` and `EXEC.md`). How to run an update:
`UPDATE_TABLE.md` part B.

| File | Role |
|---|---|
| `stockbit_events.py` | Fetching (`/corpaction/{type}?year=`, `/insider/company/majorholder`), normalizing a Stockbit row to a table row, stable keys, percent quality flag. Standard library only. |
| `job.py` | Railway job: full pull, gate, reconcile both source tables, `refresh_idx_event_annotation()`, checks, one transaction (`APPLY` or `DRYRUN`). |
| `export_job.py` | Read-only Railway job: streams `idx_event_annotation` through the log (gzip+base64 chunks, sha256). |
| `build_excel.py` | Local: rebuilds the Excel from the export log, refusing an incomplete log. |
| `run_on_railway.sh` | Sets `STOCKBIT_TOKEN` (stdin) and `DATABASE_URL` on `orc-test-runner` for one run, removes both after. |
| `test_stockbit_events.py` | Unit tests (`python -m pytest apps/stockbit-event-annotation`). |

Schema: `database/migrations/20261025_013_create_stockbit_event_annotation.sql`. Source quirks found while building it
(percent overflow value, holder id instead of transaction id, exact duplicate rows, IDX and KSEI reporting the same
movement): `ERRORS_AND_SOLUTIONS.md` D21.

Designed to move unchanged into a future Stockbit pull service (`FUTURE_PLAN.md` STOCKBIT-PULLER): the job needs only
`DATABASE_URL`, `STOCKBIT_TOKEN` and `params.json`.
