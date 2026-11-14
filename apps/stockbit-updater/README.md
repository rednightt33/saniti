# stockbit-updater

Railway service that updates every Stockbit-sourced table in one round (EXEC-STOCKBIT-UPDATER, user go 2026-10-25,
EXEC-GO-1025). How to run a round and read its result: `UPDATE_TABLE.md` section 0.

| File | Role |
|---|---|
| `updater.py` | One round per run (Run Now or the cron schedule): token expiry, broker load, Feature refresh, INDEX, event reload, stock lists, Radar, table status, monitoring row, Telegram |
| `broker_import.py` | The user's ticker-first Broker Summary importer: missing dates, symbols, six filters per symbol, `buy_freq`/`sell_freq`, per-date control in `stockbit_full_broker_import_status`; VERIFY compares 15 columns both ways. EXEC-UNIVERSE-BROKER L1: the codes that are not four letters are found per date broker-first (`discover_long`, 112 brokers × 6 filters), fetched ticker-first and cross-checked key by key (`cross_check`; a difference stops the date); `BROKER_LONG_CODES=false` loads four-letter symbols only |
| `refresh.py` | Feature 05 per changed date, 02 and 06 per ticker, 03 per date, checks, INDEX tables when needed; at the end of a round the Radar tables (`refresh_radar`, EXEC-RADAR: Feature 07 per stale ticker and date, a failure is a warning in `features.radar`) |
| `stock_lists.py` | EXEC-STOCK-CATALOG: reads the 66 enabled `Stock_List` lists (33 indices, 33 KONGLO groups) and their members from Stockbit and applies them with `apply_stock_list_snapshot` (all lists or none). A refusal or failure writes a FAILED `Stock_List_Load_Log` row and is a warning in `Monitoring_Stockbit_Update.stock_lists`; the round stays SUCCESS (decision D2). Lists Stockbit shows outside `Stock_List` are reported, never loaded |
| `test_stock_lists.py` | Its tests against a local PostgreSQL with migration 20261109_001 |
| `stockbit_ihsg_daily.py` | The user's IHSG daily helper, unchanged |
| `test_broker_import.py` | Tests against a local PostgreSQL (`UPDATER_TEST_POSTGRES_URL`) |
| `deploy.sh` | Stages this folder with `apps/stockbit-event-annotation/`, `scripts/` and `features/feature04` and runs `railway up` |

Variables (names only): `DATABASE_URL` (reference to Postgres), `STOCKBIT_TOKEN` (the user's JWT, never in Git or logs),
`STATE_DIR=/data`, `RAW_RETENTION_DAYS=0` (no raw response kept, since 2026-11-09), `UPDATER_WORKERS=6`, `UPDATER_MODE`
(`APPLY`, `VERIFY` or `CHECK`: volume, database and token expiry only, no Stockbit call),
`UPDATER_VERIFY_DATE` (read only in VERIFY), `TELEGRAM_NOTIFY_URL`, `TELEGRAM_NOTIFY_SECRET` (reference to
telegram-monitor).

Since 2026-11-09 (EXEC-STOCKBIT-CRON) the service is a Railway cron job (`0 15 1 1 *`, a once-a-year schedule that
only satisfies Railway): a deploy, a variable change or a platform restore runs nothing; a round runs when the user
presses Run Now, normally after replacing `STOCKBIT_TOKEN`. A run while another round's heartbeat is fresh refuses
(`round_refused`). There is no GitHub source. Restart policy `NEVER` is set on the service instance (`.railway/railway.ts`):
the one in `railway.json` does not override it (ERRORS M416).

Tests: `UPDATER_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres python -m pytest apps/stockbit-updater`.
