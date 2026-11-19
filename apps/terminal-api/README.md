# terminal-api

Subscriber API of the financial terminal (EXEC-TERMINAL-API): a ticker's manifest, short-lived presigned URLs for the
pre-published files in the private bucket `terminal-display`, and bounded history from PostgreSQL, each logged and
counted against the caller's quotas (`terminal.quota`). Design: `verification/terminal_api/DESIGN.md`; endpoints and
limits: `verification/terminal_api/FRONTEND_HANDOFF.md`; service accounts and the pool: `app/main.py` docstring
(EXEC-MU-RUNTIME Phase 1b).

Railway service `terminal-api` (`ba235c68-d3f5-400c-9bb3-a774b9c47a32`), healthcheck `/ready`. It is not
GitHub-connected: a new build is uploaded with the CLI (`git archive <commit> apps/terminal-api`, as in
`RAILWAY_CHANGELOG.md`), and a deployment is claimed only at `SUCCESS`.

## Callers

| Caller | Credential | Where it is accepted |
|---|---|---|
| EDGE (edge-bff's Terminal gateway) | `X-Terminal-Proxy-Key` = `TERMINAL_PROXY_KEY`; acts as the one account `TERMINAL_PROXY_SUBSCRIBER` | only on the private host (below) |
| backtest-worker, screener-worker | `X-Terminal-Proxy-Key` = their own `TERMINAL_SERVICE_KEY_<NAME>` (their service account) | only on the private host |
| administrator | `X-Terminal-Admin-Key` = `TERMINAL_ADMIN_KEY` (`/admin/...`) | only on the private host, in both modes |
| a person signing in directly | cookie `terminal_session` from `POST /auth/sign-in` | only while a browser origin is configured |

Every service already calls `http://terminal-api.railway.internal:8080` (edge-bff `EDGE_TERMINAL_URL`, the workers'
`TERMINAL_URL`). Scripts that use the admin key (`scripts/terminal_subscriber.py`, `verification/terminal_api/validate.py`,
`verification/terminal_api/quota_live.py`) must run on the private network (orc-test-runner or a job): over the
public URL they are refused (C1 M3, ERRORS M477).

## Private-only mode (EXEC-MU-ACCOUNTS Phase 0, ERRORS M470)

User decision 2026-11-16: "Terminal API publik (hapus)" — the public domain is removed, after a read-only check that
no direct sign-in was used within 30 days (job `a97135cc`; ERRORS M470).

- **Private-only** is the state with `TERMINAL_ALLOWED_ORIGINS` and `RAILWAY_PUBLIC_DOMAIN` both unset
  (`app/config.py` `Settings.private_only`). The service then starts (an older build refused to start without an
  origin), adds no CORS middleware, and refuses before any database read:
  - the direct sign-in `POST /auth/sign-in`, with or without a key;
  - every API route called without `X-Terminal-Proxy-Key` (with a session cookie or nothing; `/health` and `/ready`
    are not API routes);
  - a browser write on a cookie route.

  The refusal is 403 `direct_access_closed`, and its message names the fix: open the Terminal in EDGE (`/terminal`),
  or, for a service, call `http://terminal-api.railway.internal:8080` with its key in `X-Terminal-Proxy-Key`. The
  gateway key, the service keys and the admin key keep working.
- With an origin configured (today: `TERMINAL_ALLOWED_ORIGINS=https://terminal-api-dev.up.railway.app`) the direct
  sign-in works as before.

## Private host rule for every key (M470, C1 M3 and L2 in M477; both modes)

Every key, the EDGE gateway key, a service key and the admin key, counts only on a request addressed to the private
host and that carries none of the headers Railway's public edge adds (`x-forwarded-for`, `x-forwarded-host`,
`x-real-ip`, `forwarded`, `x-railway-edge`). The check runs before any key is judged (`app/main.py`
`private_only_keys`, called from `identify` and from the admin dependency).

- The Host must be exactly `terminal-api.railway.internal` with an optional `:digits` port, in any letter case.
  Userinfo, a path, a query, a fragment, brackets, a trailing dot or a bad port are refused.
- Off the private host the answer is one generic 403 `gateway_host_not_allowed`, the same for a valid, a wrong or an
  absent key. It names neither the private host nor a variable ("This address does not accept keyed requests. Fix:
  call terminal-api from inside its own network, ..."). The reason and the kind of credential go to the server log,
  never the key.
- On the private host a wrong key is 401 `proxy_key_rejected`, as before.
- The host list is fixed in code (`config.py` `PRIVATE_HOST`); a public `*.up.railway.app` name, an upper-case name
  or a port in it stops the start.

Consequence: a local verification tool that calls the public domain with any key (as the tools behind the gateway's
public-address access rows up to 2026-11-01 did) is refused; run such checks on the private network (orc-test-runner
or a job).

## EDGE owners and their plans (EXEC-MU-ACCOUNTS Phase 3c, T2)

CONTRACT.md section 8b "3c in detail"; code `app/entitlements.py` (the headers), `app/cut.py` (the cut), `app/main.py`
(`ROUTE_ACCESS`, `limits_of`, the gate functions); tests `tests/test_phase3c.py`; migration
`database/migrations/20261118_100_terminal_owner_subscriber.sql`, which must be applied before this build is deployed
(`/ready` reads its two columns).

**Headers.** Only beside the gateway key, edge-bff names the owner and its plan:

- `x-terminal-proxy-owner`: the principal's owner key, `^[A-Za-z0-9._:@-]{1,128}$` (Orc's owner rule).
- `x-terminal-capabilities`: compact ASCII JSON, at most 8 KiB, exactly these keys:
  `{"v":1,"version":"db-0123456789ab","admin":false,"tickers":["BBCA"],"datasets":["price"],"history_days":730,"quota":{"files_per_hour":300}}`.
  - `tickers` and `datasets` are `"*"` or lists without repeats. A dataset id is `price`, `broker`, `events` or `yield`
    (the `/bundle` datasets, `BUNDLE_DATASET`), `intraday` or `reference`. An id of the right form that this build does
    not know is left out and logged (`owner_datasets_ignored`), never a refusal of the call (re-check R2-5): an
    edge-bff one dataset ahead keeps working. Order rule: add a dataset on terminal-api first, remove it on edge-bff
    first.
  - `history_days` is `null` or 0-36600; 0 serves no row dated up to the data's last date (the value edge-bff sends for
    a plan whose limit reads as 0; re-check R1-22).
  - `quota` holds only `files_per_hour`, `tickers_per_hour`, `tickers_per_day`, `megabytes_per_day` and
    `history_per_hour`, each 1-10^9.
  - `"admin": true` (the principal holds `*`) goes only with `"tickers":"*","datasets":"*","history_days":null,"quota":{}`.
- Neither header: the gateway's one account, exactly as before (deploy step 2).
- One header without the other, a header that breaks a rule, or either header with a service key or a session: 400
  (`invalid_owner_headers` with `field`, or `owner_not_allowed`). The message names the rule, the fix and a right example.
- Every answer to an owner call, refusals included, carries `x-terminal-capabilities-applied: 1 <version>` (the header
  it applied; re-check R2-4). edge-bff refuses an answer for a capped principal without it, so a terminal-api from before
  this phase, which ignores the headers, never serves a capped plan in full.

**Owner rows.**
- Each owner has its own `terminal.subscriber` row (kind `owner`, `edge_owner_key`), made on first use
  (`store.owner_account`: INSERT ... ON CONFLICT DO NOTHING, then a read; eight concurrent first calls made one row on
  PostgreSQL 16).
- The caller's credential is `('gateway', owner)`: the account cache, the usage, the lock and the audit rows are the
  owner's. Each audit row carries the header's `version` (`terminal.access_log.version`).
- Both the gateway's account and the owner's row must be active; the administrator can turn one owner off on its row.
- So the gateway's own account (`TERMINAL_PROXY_SUBSCRIBER`; the record says "through 2027-10-25") is one point every
  EDGE call depends on. `/ready` reports it as `gateway_account` {`state`: ok, expiring (within 30 days), expired,
  inactive or missing, `days_left`} and logs `gateway_account_<state>` unless ok; it never makes the service unready
  (re-check R1-4). Owner rows are made with an end of 2100-01-01 (`store.OWNER_EXPIRES`) and never end on their own.

**Quotas (decision D6).**
- `admin: true`: the gateway subscriber's own limits. Its `terminal.quota_override` rows (today's 1e9) are read from
  the gateway's row, never copied; the usage is counted on the owner's own row.
- Any other owner: the `terminal.quota` defaults (no override of any row), overlaid by the header's `quota`. A key left
  out keeps its default, never "unlimited".
- A refusal is 429 `quota_exceeded` with `quota` (the name), `limit`, `window` and `retry_after_s`, and the same wait in
  `Retry-After` (re-check R1-1, R1-26): the seconds until the rolling window lets enough of the account's use go for the
  refused request to fit (`store.frees_in`, read only on a refusal), at most the window's length. edge-bff relays it as
  429 `LIMIT_REACHED` with `details.limit` `terminal.<quota>`. The service ceilings and the sign-in throttle send
  `Retry-After` too.

**Every data route** (main.py `ROUTE_ACCESS`; a test fails on a route without an entry). For an owner whose plan is not
`*` a refusal is 403 `capability_required` with `capability` (`terminal.tickers`, `terminal.dataset:<id>` or
`terminal.history_days`):

- `/bundle`: a ticker outside `tickers` is refused. A dataset outside `datasets` answers
  `{"locked": true, "capability": "terminal.dataset:<id>"}` (no url, sha or rows); the asked intraday timeframe likewise
  (`intraday`).
- `/files`, `/history/price|broker`, `/manifest/{t}`: the ticker and the dataset.
- `/reference/{name}` (re-check R2-32, `app/refcut.py`; decision D3 = B read as "no list of other tickers"): with the
  dataset `reference` the published file, as before. Without it the plan's own copy, built from the published file
  server-side: a file with a `ticker` column keeps the rows of the plan's tickers; the broker list keeps every row with
  the dataset `broker` and none without it; any other file (the stock lists) has no rows. It is answered in the shape of
  a cut, `{"url": "/api/terminal/v1/reference/<name>/cut?sha256=<hex>", "expires_in_seconds": 0, "sha256", "bytes",
  "rows"}`, and `GET /reference/{name}/cut` serves the bytes, counted as one file with one audit row
  (`object_key` `refcut/<name>/<sha256>`). A file that cannot be filtered is 503 `reference_unavailable`, never served
  whole. The free plan's ticker list holds BBCA alone, so the Terminal draws it.
- `/xsection`: the gateway key is refused with an owner header, whatever the plan; only the screener-worker's key reads it.
- `/state`: no data file, no refusal; `xsection` is null for such an owner, and `refs` is null without `reference`.
- `/logo/{t}`: an image, not data, so no filter (the search shows every ticker's logo; 3e marks the locked ones).
- The page routes (`/radar`, `/overview`, `/watchlist`): the headers are accepted for the per-owner audit and quota, with
  no new refusal (edge-bff gates those tabs itself). edge-bff keeps a page file it relayed in a process cache by sha256
  (`apps/edge-bff/app/pages.py`), so a file is granted, counted and audited here for the first owner that reads it in an
  edge-bff process, not for every reader (re-check R1-5, R1-31).

**History cap and the cut (decision D2 = A).** With `history_days` N and a dataset's manifest `data_through` D (its date
part), the window is the rows dated strictly after D − N days, with no upper bound. Example: N = 730, D = 2026-11-17:
D − 730 = 2024-11-17 is not served and 2024-11-18 is the first date served; 2024-11-18 .. 2026-11-17 are 730 calendar
days.

- `/bundle` answers each dated dataset (price, broker, events, yield) with one file entry, whatever `packs` says:
  `{"year": null, "pack": "cut", "url": "/api/terminal/v1/cut/<TICKER>/<dataset>?sha256=<hex>", "sha256", "bytes",
  "rows"}`, and `cut: {history_days, after}` on the dataset. The url is relative: edge-bff relays it. `/bundle` builds
  the cuts after checking the ticker quotas, but logs no audit row for them.
- `GET /cut/{ticker}/{dataset}?sha256=<hex>` serves the cut's gzip bytes as they are (`application/gzip`, no
  `Content-Encoding`, with `ETag` and `X-Terminal-Cut-Sha256`). N comes from the header only. It is counted as one file
  of its bytes with one audit row (`object_key` `cut/<T>/<dataset>/<N>/<sha256>`). A stale `sha256` gets the current
  cut; the page's check then asks a new `/bundle`.
- The cut (`app/cut.py`) reads the dataset's manifest files whose `last` is after the window start (a dataset that lists
  no file but a pack reads the pack) and checks each against its manifest sha256. It keeps the readers' shape:
  `columns` (their union; a column an older file lacks is null) with one array per column, the newest file's other
  fields, `dataset` `<name>-cut`, `year` null and `cut` {history_days, after, through}. Broker `gap` rows and the events
  `basis` block are cut by their own dates.
- Bytes: gzip level 9 with mtime 0, so the sha256 is fixed per (data, N). Built cuts are cached in memory per (ticker,
  dataset, N, data_through, source sha256s), at most 64 MB.
- A file that cannot be cut correctly (a list without a date rule, unequal columns, bytes unlike the manifest) is never
  served whole: `/bundle` answers it `{locked, capability terminal.history_days, reason}` and `/cut` 503
  `cut_unavailable`. Intraday bars are not cut: under a cap they are locked with `terminal.history_days`.
- `/files` grants only files that lie entirely after the window start (manifest `first`); a pack, an older yearly file
  or the events `all` file is refused. `/history` is refused for a range that starts on or before the window start. The
  manifest lists only the files `/files` would grant.

## Tests

`pip install -r requirements-dev.txt`, then `python -m pytest tests` (141 passed and 2 skipped on 2026-11-18, Phase 3c;
with `TERMINAL_TEST_POSTGRES_URL` set to a server holding the terminal migrations through 20261118_100, 143 passed).
The two modes and the host rule: `tests/test_private_only.py`. The owner headers, quotas, route gates and the cut:
`tests/test_phase3c.py`. `scripts/measure_grant_transactions.py` calls the app on the private host as edge-bff does.
