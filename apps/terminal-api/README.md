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
| backtest-worker, screener-worker | `X-Terminal-Proxy-Key` = their own `TERMINAL_SERVICE_KEY_<NAME>` (their service account) | private network |
| administrator | `X-Terminal-Admin-Key` = `TERMINAL_ADMIN_KEY` (`/admin/...`) | private network once the public domain is gone |
| a person signing in directly | cookie `terminal_session` from `POST /auth/sign-in` | only while a browser origin is configured |

Every service already calls `http://terminal-api.railway.internal:8080` (edge-bff `EDGE_TERMINAL_URL`, the workers'
`TERMINAL_URL`).

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

## Gateway host rule (M470; both modes)

The EDGE gateway key counts only on a request addressed to the private host `terminal-api.railway.internal` (Host
header, port ignored) that carries none of the headers Railway's public edge adds (`x-forwarded-for`,
`x-forwarded-host`, `x-real-ip`, `forwarded`, `x-railway-edge`). Otherwise the answer is 403
`gateway_host_not_allowed`, naming the host or the edge header found and the fix (`EDGE_TERMINAL_URL` on the private
network). The host list is fixed in code (`config.py` `PRIVATE_HOST`); a public `*.up.railway.app` name, an upper-case
name or a port in it stops the start. A wrong key on any host stays 401 `proxy_key_rejected`. The service keys are
not bound to a host.

Consequence: a local verification tool that calls the public domain with the gateway key (as the tools behind the
gateway's public-address access rows up to 2026-11-01 did) is refused; run such checks on the private network
(orc-test-runner or a job).

## Tests

`pip install -r requirements-dev.txt`, then `python -m pytest tests` (91 passed on 2026-11-16). The two modes and the
host rule: `tests/test_private_only.py`. `scripts/measure_grant_transactions.py` calls the app on the private host as
edge-bff does.
