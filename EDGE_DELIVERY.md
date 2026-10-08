# EDGE implementation delivery — 2026-10-08

## 1. BEST RECOMMENDATION / CURRENT DECISION

The code and deterministic local validation are complete on isolated branch `codex/edge-bff`.
The user approved dev rollout from this branch: "Ok, do it." Live admin reconciliation succeeded and
the EDGE migration/login were applied and verified. BFF service/domain and secure variables are allocated;
deployment/public verification is in progress. Main remains unmerged; no paid AI calls were made.

## 2. VERIFIED FACTS

- Repository implementation baseline: `242e282f18a1b58d81d630044e9fc69bd5fdec23`. During execution, main advanced to
  `93efb9fac8ae419e4f11f23e7ad06e9579163d88` with EXEC/error documentation only; those changes were preserved by rebasing the review branch.
- Read-only Railway inspection: project lucid-patience `8aef1702-030b-49cb-9df7-5ac2e0a42691`, dev environment
  `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49`, Orc service `41dc17ee-3bac-41ef-90ec-8b9356815c71`, active SUCCESS
  deployment `6a0ebf8f-d4e6-4d7f-a397-31b6be3b713f`, runtime commit `92884b684d760e9b8d4c3399def268bd32f011f5`.
- Market Postgres `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86` is the verified live target. Web governor's Postgres-E8GM
  `4b193143-be17-456b-bc00-c1760ef5db82` is excluded. EDGE service is `c3656044-2817-44a7-9b55-54910bab416f`;
  allocated origin `https://edge-bff-dev.up.railway.app` (not yet verified as ready).
- Admin preflight 10:10:09 UTC and readback 10:13:24 UTC: PostgreSQL 18.6, database railway;
  three EDGE tables, 28 columns, 40 constraints, six indexes, restricted DML on those three only.
  Full targeted schema/grant evidence is in `verification/edge`. Existing public/audit document snapshots
  retain their original date; this is not a claim that every market table was refreshed.
- Runtime model slot 1, mode switch 4, analysis budget 1800 s, provider request timeout 600 s, enabled server
  conversation/run-memory storage. Code's mode-4 maximum is 3600 s when its override is unset; BFF uses 3900 s.
- Source `final 8 oct.html` SHA256 `3ad20976de979ca6c854571e9558cf6530c684365236e70295ffd7139421b4a8`.
- The current canonical saved response excludes POST's `conversation` decoration. This was verified using actual
  Orc HTTP/storage with a scripted model, rather than an assumed fixture (repository M68 rule).

## 3. IMPLEMENTED CHANGES

- One additive owner-checked Orc request-read endpoint; no existing runner/run/tool/model/provider/mode changes.
- One BFF application serving the same-origin HTML, with real single-user password authentication, hashed opaque
  revocable sessions, CSRF/origin controls, strict inputs, bounded authentication attempts and generic public errors.
- Managed Postgres queue worker with idempotent submissions, fenced leases/heartbeats, restart/timeout recovery,
  same-request bounded replay, and safe lifecycle logging. Missing/disabled read capability fails closed.
- Resource-oriented REST and authenticated factual SSE; current snapshots restore after reconnect/refresh.
  Blocking Orc waits run outside the async event loop. Browser disconnect does not cancel Orc.
- Supplied vanilla frontend/CSS adapted: send, new conversation, saved history, bookmark/pin, response history,
  factual lifecycle, actual source/evidence/annotation metadata, usage/cost where reported, clarification choices,
  research-plan approve/revise/cancel, real login/logout, existing artifact downloads.
- Demo data/timers/prices removed. Deep/model switch/active cancel/attachments/data scope/support/notifications/
  public sharing/billing/profile editing remain unavailable. No reasoning, token stream or invented tool progress.
- Safe generic text/structured response renderer replaces fixed fake research tables. No raw AI HTML insertion.

## 4. FILES CHANGED

Existing files: `.railway/railway.ts`, `EXEC.md`, `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md`,
`RAILWAY_CHANGELOG.md`, `ERRORS_AND_SOLUTIONS.md`, and Orc `app/conversations.py`, `app/main.py`,
`tests/test_conversations.py`, `README.md`.

New files: `EDGE_RECONCILIATION.md`, this report; `apps/edge-bff` configuration/security/client/store/worker/main
modules, package initializer, Dockerfile/.dockerignore, pinned runtime/dev requirements, password-hash helper,
README, `static/index.html`, `static/edge-client.js`, and four test files; proposed migration
`database/migrations/20261008_002_create_edge_bff.sql`; provisioning and read-only preflight scripts.

No applied migration or generated AI model/tool/router document changed. No credentials from uploaded tokens,
Railway variables or database URLs were committed.

## 5. DATABASE CHANGES

Live: **none**. Proposed: dedicated `edge_bff` schema with `sessions`, `jobs`, `conversation_ui`, restricted
NOLOGIN runtime group and separately provisioned login. No full response or event table, no direct BFF access to
Orc tables. Identity/claim indexes concern only the small operational queue; no speculative market-data index.
One active job per owner is deliberate. Existing market data, catalogs and canonical retention are unchanged.

Migration and restricted login were verified on disposable local PostgreSQL 17. Applied migration hashes remain
unchanged. The proposal is not listed as applied. Live role/grant/schema/migration-state readback remains required.

## 6. API CONTRACTS

Orc: `GET /v1/agent/requests/{request_id}` under existing bearer + owner checks. Returns stored lifecycle/domain
status and public saved result; missing/foreign identity yields identical REQUEST_NOT_FOUND 404. It does not run AI.

BFF: `/api/v1/auth/sign-in|session|sign-out`; POST/GET `/runs`; GET `/runs/{id}` and `/events`; GET paginated
`/conversations` and `/{id}/messages`; PATCH conversation/run preferences; GET existing `/exports/{id}`. See the
complete table and payload contract in `apps/edge-bff/README.md`. Unknown model/provider/owner/path fields are refused.

BFF QUEUED/RUNNING/RECOVERING/FINISHED/FAILED/INTERRUPTED is independent of Orc
COMPLETED/NEEDS_CLARIFICATION/AWAITING_CONFIRMATION/LIMITED/FAILED. FINISHED means saved delivery, not necessarily a
successful answer. SSE carries persisted snapshots with a monotonic version, no durable event replay.

## 7. TESTS RUN AND RESULTS

The following final checks used only disposable local resources or deterministic transports:

| Command / working directory | Result |
| --- | --- |
| `ORC_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres /workspace/.venvs/saniti-orc/bin/python -m pytest -q` in `apps/market-ai-orc` | **1533 passed**, 1 dependency deprecation warning |
| `EDGE_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55432/postgres PYTHONPATH=/workspace/saniti-edge/apps/edge-bff /workspace/.venvs/saniti-orc/bin/python -m pytest -q apps/edge-bff/tests` at repo root | **23 passed**, 3 dependency deprecation warnings |
| `npm ci --ignore-scripts --cache /tmp/edge-npm-cache` | Passed with frozen lockfile; no integrity verification disabled |
| `node_modules/.bin/esbuild .railway/railway.ts --bundle --platform=node --outfile=/tmp/edge-railway-config.cjs` | Passed |
| `node_modules/.bin/tsx -e` importing/evaluating the IaC program and asserting exactly one edge-bff resource | Passed, 26 total resources; structural evaluation only |
| `node --check apps/edge-bff/static/edge-client.js` and extracted inline HTML script | Passed |
| `/workspace/.venvs/saniti-orc/bin/python -m pip check` | No broken requirements |
| Applied migration SHA256 verification; `git diff --check` | Passed |
| Docker build, then local non-root readiness/static/auth/CSRF/queue smoke (`/tmp/edge_container_smoke.py`) | Passed, uid 10001, zero AI calls |

BFF tests cover all five domain statuses; actual canonical Orc envelope; authentication/revocation/CSRF/input limits;
concurrent duplicate/conflicting submits; owner isolation; lease recovery/fencing and ambiguous timeout without a
second execution; saved-result/expiry/pin handling; restricted login access; disabled read capability; deployment
credential/timeout guards. Chromium tests exercise actual BFF/worker/local Postgres plus deterministic Orc, reload
and metadata persistence, clarification and all plan actions, logout, disabled controls and safe AI text. Real local
HTTP streaming verifies delivery and health/refresh recovery while the Orc thread is blocked.

Docker build used existing proxy variables by name, a build-only proxy DNS mapping and a `build_ca` secret mount
from the cloud's existing trusted certificate bundle. TLS verification remained enabled. Final image SHA256:
`a305852ebe758cb0a0ed220ffc95c6878fe65e4025ea5eef5411502027a3e69d`.
Initial setup/fixture failures were diagnosed and corrected; the final results above are passing runs. Container
file permissions were fixed before delivery. No remaining failed local application check is being hidden.

Not run: live schema/role/grant readback (network-blocked); live migration/deployment/domain/real export/proxy
checks (approval-gated); paid end-to-end AI test (not authorized). Live IaC plan also needs a linked CLI context;
local TypeScript evaluation/bundling is not a live drift review.

## 8. RAILWAY CHANGES

Live: migration/login verified; one edge-bff service, public domain and secure variables allocated. Deployment
is pending. Its Orc key is an existing-variable reference; no administrative DB credential is in the BFF.
The original runner and unrelated services are unchanged. Main remains unmerged.

Cloud development configuration is separate: updated install/start instructions and added only the pgweb hostname
to the existing custom egress list, preserving the prior four destinations. The draft tool confirmed **saved** and
`requires_publish=true`. The user must review/save/publish in Environment Settings for that configuration to activate.
No cloud publication/fresh-task restore was performed, and saved settings do not prove live DB connectivity.

## 9. RISKS / TRADE-OFFS

- Snapshot SSE provides factual delivery states, not tool activity or historical events. Direct Orc POST remains
  blocking internally; no active cancellation or token/hidden-reasoning stream exists in this scope.
- One active request per owner is stricter than one per conversation; an uncertain run may temporarily block new
  submissions. Recovery relies on the deployed additive read endpoint and existing Orc idempotency/storage.
- The first response renderer shows Markdown as safe text and structured findings/plans generically; rich chart/
  table formatting and public sharing need further work. Existing artifact downloads are supported.
- One process/replica and process-local sign-in limiting fit a private user. Multiuser auth, shared rate limiting,
  external notifications/support/billing are future scope. Original inline renderer requires CSP unsafe-inline.
- Terminal job inputs/UI metadata currently have no automatic purge. Decide operational retention before long-term
  use. Pins/bookmarks do not keep a canonical answer alive beyond Orc retention.
- The full current IaC project must be inspected for unrelated drift before any apply. Do not apply it wholesale
  based on local bundling. Main application changes can auto-deploy, so approval precedes merge.

## 10. UNKNOWN / BLOCKED

Earlier transport blockers were resolved for reconciliation: pgweb is reachable and its target matched market PG;
supported private-network Railway sandbox execution provided administrative access. No global pgweb
connection or unrelated service was changed. Direct TCP/SSH DNS remains unavailable from this cloud machine.

The user selected branch-only delivery on 2026-10-08 and delegated the private login choice: `EDGE_LOGIN=edge`.
That branch-only follow-up was superseded by explicit go for dev deployment from the branch; main stays unmerged.
Non-secret owner is `edge-private`; credentials and HTTPS origin have been set securely. The generated password
handoff is `EDGE_INITIAL_PASSWORD` in Railway Variables, unused by app code; copy it securely then remove that
variable after saving the password. No secret value is requested or printed in chat.
Git push permission was verified separately from GitHub API authentication. The feature branch is published;
GitHub CLI API authentication is unavailable, so no draft PR was created.

## 11. APPROVED DEV ROLLOUT SCOPE

The attached executor required separate deployment go, supplied by the user on 2026-10-08: **"Ok, do it."**
This approves deployment from `codex/edge-bff`; it does not approve a main merge or paid AI calls.

After successful read-only preflight, the approved **dev-only** scope is:

1. Apply `20261008_002_create_edge_bff.sql` to market Postgres ID `bb21a9f4-a9d3-4a51-945f-fa86b63f4b86`;
   provision `edge_bff_login` with the helper; read back schema and exact grants.
2. Deploy the additive Orc endpoint from the branch on service `41dc17ee-3bac-41ef-90ec-8b9356815c71`, leaving its execution,
   feature flags, tools, models/providers/mode and runner configuration intact. Confirm its exact deployment SUCCESS.
3. Create the one edge-bff service on project/environment above, set the listed variables securely and existing-key
   reference, allocate one Railway HTTPS domain, set its exact origin, deploy and verify unpaid health/auth/read paths.

Evidence is the code/migration diff and passing local checks. Stop if preflight/plan shows drift; do not change
unrelated grants/services to make this proposal pass. Rollback stops BFF dispatch/public ingress, restores the prior
Orc deployment if required, and preserves operational rows/schema for review. A previously dispatched Orc run may
continue; deleting data requires a separate decision. **Paid AI smoke tests require separate approval.**

## 12. NEXT ACTION

Complete Orc/BFF deployments from the branch, verify exact SUCCESS deployments, public health/auth/static
and unpaid private backend reads, clean up the privileged sandbox, and publish rollout evidence on the branch.
Keep EXEC-EDGE open until live delivery is verified. Paid end-to-end model calls remain a separate decision.
