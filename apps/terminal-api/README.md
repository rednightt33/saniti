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

## Tests

`pip install -r requirements-dev.txt`, then `python -m pytest tests` (99 passed on 2026-11-16, after the checkers' fix
round). The two modes and the
host rule: `tests/test_private_only.py`. `scripts/measure_grant_transactions.py` calls the app on the private host as
edge-bff does.
