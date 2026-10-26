# stockbit-updater

Railway service that updates every Stockbit-sourced table in one round (EXEC-STOCKBIT-UPDATER, user go 2026-10-25,
EXEC-GO-1025). How to run a round and read its result: `UPDATE_TABLE.md` section 0.

| File | Role |
|---|---|
| `updater.py` | One round per deployment: token expiry, broker load, Feature refresh, INDEX, event reload, table status, monitoring row, Telegram |
| `broker_import.py` | The user's ticker-first Broker Summary importer: missing dates, symbols, six filters per symbol, `buy_freq`/`sell_freq`, per-date control in `stockbit_full_broker_import_status`; VERIFY compares 15 columns both ways |
| `refresh.py` | Feature 05 per changed date, 02 and 06 per ticker, 03 per date, checks, INDEX tables when needed |
| `stockbit_ihsg_daily.py` | The user's IHSG daily helper, unchanged |
| `test_broker_import.py` | Tests against a local PostgreSQL (`UPDATER_TEST_POSTGRES_URL`) |
| `deploy.sh` | Stages this folder with `apps/stockbit-event-annotation/`, `scripts/` and `features/feature04` and runs `railway up` |

Variables (names only): `DATABASE_URL` (reference to Postgres), `STOCKBIT_TOKEN` (the user's JWT, never in Git or logs),
`STATE_DIR=/data`, `RAW_RETENTION_DAYS=3`, `UPDATER_WORKERS=6`, `UPDATER_MODE` (`APPLY` or `VERIFY`),
`UPDATER_VERIFY_DATE` (read only in VERIFY), `TELEGRAM_NOTIFY_URL`, `TELEGRAM_NOTIFY_SECRET` (reference to
telegram-monitor).

Every deployment runs a round, including the one Railway starts after a variable change, so changing `STOCKBIT_TOKEN`
is how a round is started (decision K2 A). There is no GitHub source: a push to `main` never starts a round. Restart
policy `NEVER`: a failed round is not retried with the same token.

Tests: `UPDATER_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres python -m pytest apps/stockbit-updater`.
