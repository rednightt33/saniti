# EDGE private frontend and BFF

One service serves the supplied vanilla HTML, authenticates one private user, queues delivery to the existing Orc,
and exposes persisted lifecycle snapshots over SSE. Standard follows Orc's configured model and mode. There is
no public model/provider/path override and no per-token, reasoning, or per-tool stream.

The HTML comes from `final 8 oct.html`; its original CSS and workspace renderer are retained. Demo conversations,
market values, result tables, prices, sources, upload simulation and timed execution are removed. The renderer
accepts canonical response types rather than a fixed research template. AI text uses text nodes, never raw HTML.
`static/edge-client.js` holds the session/API/SSE/adapters separately from view handlers.

## Persistence and ownership

Orc owns history, answers, methodology, evidence, usage and exports. BFF accesses them only through authenticated
Orc endpoints, not SQL. Its dedicated restricted schema holds three operational tables: sessions, jobs and UI
metadata. Jobs retain original inputs for deterministic replay, not answers. Pins/bookmarks do not extend Orc's
retention (code default 30 days, actual configuration must be checked before rollout). Expired history returns 410.
There is currently no automatic purge of terminal job inputs/UI metadata: define an operational retention policy
before long-term use. Sessions are cleaned hourly.

Deployment configuration rejects an administrative database username; it requires `edge_bff_login`.
The server sets `X-Saniti-Owner`; a browser cannot choose an owner. One active job per owner is intentional for this
single-user first delivery. Different tabs cannot start concurrent paid runs. A submission key identifies a logical
submission: same key + payload returns the same request; changed payload returns 409. Retry in the UI prepares a
new submission. An ambiguous transport retry reuses the identical key; it is not an automatic new AI execution.

## Worker and SSE

The managed worker claims jobs with `FOR UPDATE SKIP LOCKED`, a 90-second lease and 20-second heartbeats. Expired
leases can be reclaimed. All writes are fenced by the lease token and expiry. Every dispatch first reads Orc's
request identity. A saved result is delivered without POST; RUNNING is polled. Ambiguous dispatch is checked twice
before at most three total attempts using the same request ID and exact payload. Orc's idempotency, not the BFF
lease alone, prevents a second execution. The 3900-second HTTP timeout covers the verified mode-4 3600-second
budget plus margin. No timeout or browser disconnect claims to cancel Orc.

SSE is cookie-authenticated, same-origin, uncompressed, and unbuffered. Events are `snapshot` with the monotonic
job `state_version` as `id`. Reconnection restores the current snapshot, not a historical event sequence. Connections
rotate after 240 seconds; browser EventSource reconnects automatically with Last-Event-ID, falling back to REST
polling after repeated failures. Terminal snapshots close the stream. Refresh restores the active job from the
server. Logout revokes the session and disconnects browser followers.

## API contracts

All routes are under `/api/v1`; all writes require exact Origin and, except sign-in, `X-CSRF-Token` from the session
endpoint. Cookie `edge_session` is opaque, HttpOnly, Secure and SameSite=Strict in deployment; only its hash is stored.
No CORS is enabled. Responses are not cached. Inputs forbid unknown fields.

| Method/path | Input/result |
| --- | --- |
| POST `/auth/sign-in` | `{login,password}`; session cookie, login, CSRF token |
| GET `/auth/session` | Authenticated login, CSRF, supported capabilities |
| POST `/auth/sign-out` | Revoke session; clear cookie |
| POST `/runs` | `{submission_key,message,conversation_id?,chosen_option?,plan_reply?}`; 202 request identity |
| GET `/runs` | `{active: snapshot or null}`; refresh recovery |
| GET `/runs/{request_id}` | Owner-scoped snapshot, saved canonical response when terminal |
| GET `/runs/{request_id}/events` | Same snapshot as SSE, `Last-Event-ID` supported |
| GET `/conversations` | Search/title, bookmark filter, offset/limit pagination; BFF-owned conversations |
| GET `/conversations/{id}/messages` | Canonical history pagination `after/limit`, UI metadata; 410 if expired |
| PATCH `/conversations/{id}/preferences` | Desired `{bookmarked?,title?}` |
| PATCH `/runs/{id}/preferences` | Desired `{pinned}`; canonical response must exist |
| GET `/exports/{export_id}` | Owner-checked streaming proxy of an existing Orc artifact |

`plan_reply` is `{plan_id, action: APPROVE|REVISE|CANCEL, revision_instruction?}`. The client reads the issued plan
ID; Orc validates latest-plan state and ownership. Cancel applies to a pending plan, not an active request.
`chosen_option` uses an Orc-issued route. Free-text replies remain ordinary message submissions.

BFF lifecycle: QUEUED/RUNNING/RECOVERING/FINISHED/FAILED/INTERRUPTED. Orc domain status is independently one of
COMPLETED/NEEDS_CLARIFICATION/AWAITING_CONFIRMATION/LIMITED/FAILED. FINISHED means a canonical result was saved,
even if its domain status is FAILED. The read endpoint's saved envelope excludes POST's `conversation` decoration.
Sources are drawn only from actual evidence/annotations/data_record. Usage/cost appears only when the saved execution reports it.

## Railway dev configuration

| Variable | Value/source |
| --- | --- |
| EDGE_DATABASE_URL | New restricted `edge_bff_login` on existing market Postgres, private endpoint; secure value |
| EDGE_ORC_URL | `http://market-ai-orc.railway.internal:8080` |
| MARKET_AI_ORC_API_KEY | Railway reference to existing Orc variable |
| EDGE_OWNER | `edge-private`, stable server-owned identity; never browser supplied |
| EDGE_LOGIN | `edge`, selected under the user's 2026-10-08 delegation; set before deployment |
| EDGE_PASSWORD_VERIFIER | Scrypt verifier of the securely generated private password |
| EDGE_INITIAL_PASSWORD | Temporary credential handoff in Railway Variables; unused by the application. Owner retrieves securely, then removes this variable after copying the password |
| EDGE_SESSION_SECRET | Random 32+ character secret, entered securely |
| EDGE_PUBLIC_ORIGIN | Exact HTTPS origin of the new service; set after domain allocation |
| EDGE_ENVIRONMENT | `dev` (use `local` only for loopback tests) |
| EDGE_SECURE_COOKIE | `true`; local tests alone use false |
| EDGE_SESSION_SECONDS | 86400 |
| EDGE_ORC_TIMEOUT_SECONDS | 3900, must exceed active Orc maximum + margin (minimum 3900 seconds) |
| EDGE_LEASE_SECONDS / EDGE_HEARTBEAT_SECONDS | 90 / 20 |
| EDGE_POLL_SECONDS / EDGE_WORKER_ENABLED | 2 / true |

Use one uvicorn process/one replica initially. Disable request access logs and proxy headers; authentication attempt
limiting is process-local. HTTPS termination is Railway's responsibility. No plaintext password, database credential,
Orc key, session secret or Railway token is bundled or stored in Git. Public errors are generic; private diagnostic
keys/addresses are filtered. The original inline renderer requires CSP `unsafe-inline`; unsafe-eval is not enabled.

## Local validation

Use a **disposable** Postgres admin URL; tests create/drop databases and roles. Never point these at Railway.

```bash
python -m venv /tmp/edge-venv
/tmp/edge-venv/bin/pip install -r requirements-dev.txt
# Also install ../market-ai-orc/requirements-dev.txt for the real canonical contract test.
EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres /tmp/edge-venv/bin/python -m pytest -q
```

Browser tests use installed Chromium `/usr/bin/chromium` (set `EDGE_TEST_CHROMIUM` for another path); install
Chromium locally or use Playwright's verified browser installer. They launch a local BFF/worker with real local
Postgres and a deterministic Orc substitute. The separate contract test obtains JSON from actual Orc HTTP/storage
with a scripted model, satisfying the repository's M68 rule. No OpenRouter call is made by these tests.

## Rollout gate and rollback

See `EDGE_DELIVERY.md`. Migration is **APPLIED** and verified at 10:13:24 UTC on 2026-10-08 after admin preflight.
See `verification/edge` for live columns, constraints, indexes and grants. The only Orc code
change is additive GET `/v1/agent/requests/{request_id}`; no existing runner/tool/model/provider configuration changes.
The user approved dev deployment directly from `codex/edge-bff`; keep main unmerged. Further merge approval is separate.

After approved reconciliation: apply the forward migration; provision the restricted login with
`scripts/provision_edge_bff_login.py`; verify actual grants; deploy the additive Orc endpoint; create the one BFF
service and its secure variables/domain; deploy BFF; verify unpaid health/auth/read paths. A paid AI smoke test
requires separate approval. Do not apply the full IaC project until its live plan has been checked for unrelated drift.

Rollback stops BFF dispatch and disables its public ingress, then restores the previous Orc deployment if necessary.
A dispatched Orc run can continue and save its result. Preserve the new operational schema/rows for review; dropping
it or deleting jobs requires a separate destructive decision. No original market or canonical tables are changed.

Local container validation also confirmed uid 10001 can read root-owned code/static after COPY, and health/auth/CSRF/
queue persistence work in the image. Copied private file modes are normalized with read/traverse permission only.
