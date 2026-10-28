# EDGE multi-user: identity, sessions and per-user state (read-only planning, 2026-10-28)

Scope: every place EDGE assumes one owner or one login, across the EDGE shell and its tabs (Monitor = the AI chat,
Terminal, Backtest, Screener as designed), the Orc path, the AI conversation store, terminal-api and Telegram. For each
one: what changes when EDGE serves many external users, the options, the migration path from the single owner, and the
security requirements. Basis: user decision P29 (external users on every tab) and P30/P31 of `EXEC.md:8503-8513`,
`PLAN.md:912-927` (EDGE-MULTIUSER), report section 6d (`.../scratchpad/report/06d_multi_user_scale_cost.md`, table E1-E6).

Labels: FACT (file:line, query or CLI read), INFERENCE, PROPOSED, UNKNOWN. Nothing in the repository, Railway or the
database was changed. One side effect to report: a `git fetch origin main` updated only the remote-tracking ref
`origin/main` (no branch, index or working-tree change).

**Evidence base.** Code lines are from the working tree of branch `claude/charming-hamilton-faq25e` (HEAD `0a20886` at
reading time). The deployed edge-bff is `origin/main` `f265ae4` (Railway deployment `32a25029`, SUCCESS,
2026-10-28T15:04Z). Its identity code is the same. Only the Screener lines are missing, so line numbers shift by about 18:
for example, on `origin/main` the owner check of `session()` is `main.py:250` and `sign_in` is `main.py:402`. Live DB reads
used `pgq2.py` (role pgweb, read-only), which cannot read rows in `edge_bff` or `terminal`. For those, pg_catalog
metadata and `reltuples` estimates were used. Railway was read for variable names, plus three yes/no comparisons that
printed no value (marked "boolean check").

---

## 1. Key facts in one screen

1. **One identity and one owner, fixed in configuration.**
   - **FACT:** `EDGE_OWNER`, `EDGE_LOGIN` and `EDGE_PASSWORD_VERIFIER` are required settings (`apps/edge-bff/app/config.py:12-14, 54-57`).
   - **FACT:** sign-in compares the body with the one login (`main.py:451`) and creates every session for `settings.owner` (`main.py:459`).
   - **FACT:** the session check refuses any session row whose `owner_key` is not `settings.owner` (`main.py:268`).
   - **FACT:** live, `EDGE_OWNER` = `edge-private`, as documented in `apps/edge-bff/README.md:399` (boolean check).
2. **The owner comes from configuration, never from the session.**
   - **FACT:** there are 41 `settings.owner` uses in `main.py`, one in `backtest.py` (`:1050`) and two in `screener.py` (`:642` worker owner tag, `:903` routes).
   - **FACT:** Orc receives `X-Saniti-Owner: settings.owner` (`client.py:34-37`, `main.py:690`).
3. **The data model is already multi-owner.**
   - **FACT:** every `edge_bff` table carries `owner_key`, and every store statement names it: `sessions`, `jobs`, `conversation_ui`, `backtest_jobs`, `backtest_trials` (live pg_catalog), plus `screener_items` and `watchlist_items` in migration `20261028_001`.
   - **FACT:** the Screener migration is not applied in dev yet: neither table is in pg_class.
   - **FACT:** Orc keys `AI_conversation.owner_key` (migration `20260927_002:33,43,49`). Every other `AI_conversation_*` table is reached through `conversation_id` behind an owner check (`result_store.py:309-316`, `conversations.py:302, 536, 552, 573`).
   - **FACT:** no table has row-level security (`relrowsecurity` false for all of `edge_bff`, `terminal` and `AI_conversation*`, live).
4. **Live owners.**
   - **FACT:** `AI_conversation` holds 534 conversations from 29 owner keys (live). Only these three are identified by md5 prefix:
     - `golden-multi-angle` (orc-test-runner): 415 conversations;
     - `edge-private` (EDGE): 92 conversations;
     - 27 one-conversation test owners from 2026-09-28/29.
   - **FACT:** `edge_bff` row estimates (`reltuples`): `jobs` about 340, `conversation_ui` about 88, `sessions` about 28, `backtest_jobs` about 43, `backtest_trials` about 250.
5. **The sign-in limiter is in-process and keyed by the TCP peer.**
   - **FACT:** the limiter allows 5 failures a minute per `request.client.host` (`main.py:440-449`) and clears all keys above 1024 (`main.py:442-443`).
   - **FACT:** uvicorn runs with `--no-proxy-headers` (`apps/edge-bff/Dockerfile:49`; `.railway/railway.ts:184`).
   - **INFERENCE:** the key is the Railway edge's address, not the user. So the limit is shared by everybody (5 wrong passwords by anyone can block sign-in for all for up to 60 s), and there is no per-account limit.
6. **Terminal: one account for all EDGE users.**
   - **FACT:** every proxied request counts against the one `TERMINAL_PROXY_SUBSCRIBER` (`apps/terminal-api/app/config.py:25-28, 44-45`; `main.py:174-180`). The backtest-worker uses the same key and account (`apps/backtest-worker/src/terminal.ts:5-6`).
   - **FACT:** quotas, the per-account advisory lock and the `access_log` audit therefore cannot tell users apart (`FUTURE_PLAN.md:902-905`).
   - **FACT:** terminal-api already has a working subscriber directory (email, scrypt hash, active, expiry, quotas and overrides, session cap 2, Postgres sign-in throttle per email and per IP, admin log) (`database/migrations/20261025_100_create_terminal_schema.sql:23-102`).
7. **The AI path trusts the header.**
   - **FACT:** anyone holding `MARKET_AI_ORC_API_KEY` can act as any owner by setting `X-Saniti-Owner` (`market-ai-orc/app/conversations.py:6-8, 97-103`; `main.py:590-592`).
   - **FACT:** the key holders are edge-bff and orc-test-runner (Railway variable names; `PROJECT_CONTEXT.md:58`).
   - **FACT:** without the header the owner becomes the shared `default` (`conversations.py:50, 98-99`).
8. **The manual troubleshooting path crosses owners (cross-tenant leak once a second user exists).**
   - **FACT:** `AI_ENABLE_MANUAL_AGENT=true` on dev (`RAILWAY_CHANGELOG.md:18`). The "Claude (manual)" model is then offered to every session (`model_choices.py:52-57`).
   - **FACT:** `manual.pending()` returns every waiting step of every run with its full model payload, and `answer()` accepts any step id (`manual_agent.py:112-117`; Orc `main.py:678-692`, no owner).
   - **FACT:** edge-bff exposes both routes to any session (`main.py:581-593`). The POST has no CSRF check (ERRORS M259, open).
   - **INFERENCE:** with two users, one user could read the other's prompts and data and inject model replies into the other's run.
9. **Monitor (AI) runs are serial across all of EDGE.**
   - **FACT:** the worker claims one job, awaits it to the end, then claims the next (`worker.py:36-45`). The claim is global FIFO by `created_at` (`store.py:158-169`), and a run may take up to 3900 s (`config.py:19`).
   - **FACT:** "one active job per owner" is a database rule (`edge_bff_one_active_owner`, migration `20261008_002`), not a fairness mechanism.
   - **INFERENCE:** with many users, one user's long run delays every other user's question. This is a cross-area item for the scale and AI-budget work.
10. **No AI budget per user.**
    - **FACT:** limits are per run (`AI_MAX_ANALYSIS_SECONDS`, `AI_MAX_TOOL_CALLS`, `AI_MAX_OUTPUT_TOKENS`, ... on Railway). There is one `OPENROUTER_API_KEY`.
    - **FACT:** Orc returns the run's `cost` in its response (`market-ai-orc/app/schemas.py:700-703`). edge-bff already reads the stored response (`main.py:281-284`), so metering per owner needs no new Orc call.
11. **Leftover credential.**
    - **FACT:** `EDGE_INITIAL_PASSWORD` is still set and non-empty on edge-bff (boolean check), although `README.md:402` says to remove it after copying.
    - **FACT:** the dev E2E scripts read it (`verification/backtest/e2e_dev.py:912-919`, `page_timing_dev.py:14`).

---

## 2. Inventory of single-owner and single-login assumptions

### 2.1 edge-bff: configuration, sign-in, sessions, CSRF

| Item | Today | Multi-user impact | Change (PROPOSED) |
|---|---|---|---|
| Identity config | FACT `config.py:12-14, 54-57, 80-83`: one owner (regex `[A-Za-z0-9._:@-]{1,128}`), one login, one scrypt verifier, from env | One person only | A user directory (section 4); env values seed the first admin account (section 5) |
| Sign-in | FACT `main.py:438-463`: compares `body.login.casefold()` with `settings.login` (constant time), verifies the one verifier, revokes the old cookie's session, creates a 64-hex token, stores `sha256(token)` (`security.py:23-24`) with `settings.owner` | Must look up a user by login; must not reveal which logins exist | Lookup by normalised login (email); dummy scrypt verify for an unknown login (terminal-api `security.py:16-25` precedent); one error code for every failure; check user status |
| Sign-in limiter | FACT `main.py:179, 440-454`: in-process `defaultdict(deque)`, 5 failures per 60 s per `request.client.host`; cleared above 1024 keys; one process by design (`README.md:412-413`) | INFERENCE (see 1.5): a global lockout, no per-account limit, lost on restart, multiplied by N replicas (report 6d.5) | Postgres table per login and per client IP over a rolling window, as `terminal.sign_in_attempt` (`terminal-api/app/store.py:84-92`; limits 10 per email and 30 per IP in 15 min, migration `20261025_100:87-88`) |
| Client IP | FACT: `--no-proxy-headers`. terminal-api instead takes the first `X-Forwarded-For` entry (`terminal-api/app/security.py:40-47`) | The per-IP limit needs the real client | UNKNOWN: whether Railway's edge overwrites or prepends a client-supplied `X-Forwarded-For`. Test before trusting it; until then the per-login limit is the primary limit |
| Session table | FACT migration `20261008_002`: `sessions(token_hash PK, owner_key, created_at, expires_at, revoked_at)`; read by `store.py:63-65` | No user id, no status join, no list of a user's sessions | Add `user_id` (FK), `last_seen_at`, an IP hash or user-agent label; the session check joins `users` and refuses disabled users |
| Session lifetime | FACT `config.py:18`; live `EDGE_SESSION_SECONDS` = 86400 (boolean check): absolute 24 h, no idle timeout, no cap per owner | Many devices per user, shared devices | Idle timeout plus absolute cap; at most K sessions per user (terminal uses 2, `20261025_100:85`); revoke all on password change, reset, disable or role change |
| Revocation reach | FACT: every request reads the session (`main.py:265-270`), and the SSE loop re-reads it every poll (`main.py:562`) | Good: a revoke takes effect within `EDGE_POLL_SECONDS` | Keep |
| Session cleanup | FACT `worker.py:38-40` → `store.py:326-328`, hourly, only while the AI worker runs (`EDGE_WORKER_ENABLED`) | With replicas or a disabled worker, cleanup could stop | Move to an independent periodic task (or every replica, idempotent) |
| CSRF | FACT `security.py:27-28`, `main.py:272-275`: token = HMAC-SHA256(`EDGE_SESSION_SECRET`, session token), stateless; exact `Origin` on every POST/PATCH/PUT/DELETE including sign-in (`main.py:237-240`) | Works per user unchanged | Keep. Fix M259 (`main.py:587` uses `session`, not `write`) and add a route-table walk test (ERRORS M259 solution) |
| Cookie | FACT `main.py:461-462`: `edge_session`, HttpOnly, Secure, SameSite=Strict, Path=/, host-only. Live domain under `up.railway.app` (boolean check), a public-suffix domain, so siblings cannot share cookies | On a custom domain, sibling subdomains become same-site | Never set `Domain=`. Rename to `__Host-edge_session` when moving to a custom domain. Keep the exact-Origin check, which also stops same-site siblings |
| Session API | FACT `main.py:465-469`: returns `login: settings.login` and fixed capabilities | Per-user display and capabilities (role, tier, budget left) | Return the principal's login, display name, role and per-user capabilities |
| CSP of the shell | FACT `main.py:262`: `script-src 'self' 'unsafe-inline'` (README: the inline renderer needs it) | INFERENCE: with external users and model or web-derived text in answers, any HTML injection runs script, which can read the CSRF token (`/auth/session`) and act as the user | A nonce-based CSP (or moving inline scripts to files) before external users; the tab pages already use `script-src 'self'` (`main.py:40-58`) |

### 2.2 edge-bff routes: where the owner comes from

FACT: every data route takes the owner from `settings.owner`, never from the session. Monitor/AI: `main.py:278, 282, 482-488,
499-520, 526, 538-547, 552, 583, 592, 604, 616, 623-629, 636-644, 649-651, 655-668, 676-677, 690`. Backtest:
`backtest.py:1050` binds `owner = self.settings.owner` once, when the routes are registered. Screener: `screener.py:903`, and the worker
owner tag is computed from `self.settings.owner` (`screener.py:642`), not from the route's owner.

PROPOSED: `session()` returns a principal `{user_id, owner_key, role, login}`. `write()` passes it on. Every route,
`Backtests.routes` and `Screeners.routes` take `owner = principal.owner_key` per request, and `Screeners.ask()` takes the
owner as a parameter. INFERENCE: this is mechanical. The store layer already takes the owner as an argument everywhere
(`store.py`, `backtest.py:432-599`, `screener.py:428-514`), so no SQL changes.

### 2.3 edge-bff tables and what keys them

| Table | Key / uniqueness (FACT, migrations) | Per-user rule today | Multi-user note |
|---|---|---|---|
| `sessions` | PK `token_hash`; `owner_key` not null | none | Add `user_id`; index `(user_id)` for "revoke all" |
| `jobs` | PK `request_id` (`edge_` + 32 hex); UNIQUE `(owner_key, submission_key)`; partial UNIQUE `(owner_key)` while QUEUED/RUNNING/RECOVERING; claim index `(created_at)` | One active AI job per owner; per-owner advisory lock on submit (`store.py:77`) | Keep. INFERENCE: `list_conversations` and `side_chats` scan `jobs` by `(owner_key, conversation_id)` with no index on it (live index list), and the search does `ILIKE` on `input->>'message'`. Measure with `EXPLAIN (ANALYZE, BUFFERS)` at multi-user volume before adding `(owner_key, conversation_id, created_at DESC)` (AGENTS.md performance rule) |
| `conversation_ui` | PK `(owner_key, conversation_id)`; UNIQUE `(owner_key, parent_request_id)` WHERE kind='SIDE' (`20261024_002`) | Per owner | OK |
| `backtest_jobs` | PK `request_id` (`bt_` + 32 hex); UNIQUE `(owner_key, submission_key)`; UNIQUE `(owner_key)` WHERE RUNNING; index `(owner_key, created_at DESC)` (`20261026_005:24-56`) | One running, 3 queued per owner (`config.py:37`); claim rotates across owners (`backtest.py:516-526`) | OK; throughput is one job EDGE-wide (report E5) |
| `backtest_results` | PK `(request_id, part)`, no owner | Reached only after `store.job(owner, request_id)` (`backtest.py:1125-1160`) | OK. INFERENCE: keep that order; a test should assert a result route never reads a part before the owner check |
| `backtest_trials` | UNIQUE `(owner_key, lineage_key, variant_hash)`, global `recorded_seq` (`20261026_005:77-89`) | The K3 trial count per owner | Correct per user (each user's own multiple-testing count) |
| `screener_items`, `watchlist_items` (not yet live) | PK `item_id` (`scr_` + 32 hex) and UNIQUE `(owner_key, kind, name)`; PK `(owner_key, ticker)` (`20261028_001:26-50`) | 50 per kind, watchlist limit; advisory lock per owner (`screener.py:445, 502`); another owner's id answers like a missing one (`screener.py:463`) | Ready |

Roles (FACT, live): `edge_bff_login` connection limit 20, `market_ai_conversation` 10, `terminal_api_login` 20.

### 2.4 edge-bff in-process state

| State | Key | FACT | Multi-user / multi-replica note |
|---|---|---|---|
| `failures` sign-in limiter | client host | `main.py:179, 440-454` | Section 2.1 |
| `models_cache` | global | `main.py:595-611`, 600 s | No user data; fine while every user sees the same models. If tiers offer different models, key by tier |
| `terminal_http` client | global | `main.py:182, 407-408` | Fine |
| Backtest `previews` / `preview_pages` | owner | `backtest.py:935-936, 1016-1037` | Latest-wins is per owner, so two tabs of one user cancel each other (report 6d.6). `preview_pages` keeps an entry per owner forever: memory grows with the number of owners (INFERENCE: small, but unbounded) |
| Screener `flight` / `pages` / `docs` / `reviews` | (owner, lane, page) / documents | `screener.py:606-610` | Already per (owner, page); same unbounded-per-owner note for `pages` |
| Backtest catalog cache | global | report 6d.1 | No user data |

### 2.5 Monitor (AI chat) and the Orc path

- **Ownership contract.** FACT: Orc's owner is the trusted caller's header (`conversations.py:6-8`). It is validated by
  `OWNER_RE` (`:51, 97-103`) and checked on every conversation, request, export, branch and progress read, and on every
  stop (`conversations.py:262-302, 536-573`; `stop.py:40-44`; `progress.py:105-109`; `result_store.py:309-316`). The
  sandbox reuse key is derived from the owner and the conversation (`conversations.py:106-109`). The Orc tests cover
  isolation at the store level (`tests/test_conversations.py:163`, `test_stop.py:15`, `test_progress.py:17`,
  `test_export.py:116`, `test_table_export.py:124`, `test_conversation_branch.py:112`).
- **Trust boundary.** FACT: Orc trusts any holder of `MARKET_AI_ORC_API_KEY` for any owner (`main.py:590-592`).
  orc-test-runner uses owners `golden-multi-angle` and `someone-else` (`apps/orc-test-runner/run.py:29, 86, 123`).
  - PROPOSED: owner keys of real users are opaque (section 4.3), so they cannot collide with test names.
  - PROPOSED: give the test runner its own key, which Orc accepts only for `golden-*` or `test-*` owners.
  - PROPOSED: when multi-user is on, Orc refuses a missing header instead of using `default`.
- **Per-owner state held by Orc:**
  - FACT: `AI_conversation` holds the owner key, a 30-day retention and the single-active-run lease (`20260927_002`).
  - FACT: the child tables (`_turn`, `_output`, `_execution`, `_export`, `_evidence`, `_run_memory`) have no owner column and are reached by `conversation_id`.
  - FACT: the result bucket keys are `outputs/<conversation_id>/<output_id>` (`PROJECT_CONTEXT.md:57`).
  - FACT: no audit table records the owner. `ai_audit.*` and `AI_research_run_audit` have no owner column (pg_catalog scan). The only owner-to-request link is `edge_bff.jobs` (never purged, `README.md:329-330`) and `AI_conversation` (expires).
- **Run budgets.** FACT: there are per-run caps only (variable names `AI_MAX_ANALYSIS_SECONDS`, `AI_MAX_TOOL_CALLS`,
  `AI_MAX_TOOL_ITERATIONS`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_CONTEXT_TOKENS`, `AI_MAX_HISTORY_TOKENS` on Railway), plus EDGE's one
  active job per owner. There is no per-owner daily or monthly cost budget and no per-owner request rate. PROPOSED:
  1. When a job reaches FINISHED, edge-bff's worker writes `{owner_key, request_id, cost, tokens, model}` to a new `edge_bff.ai_usage` table, from the response it already reads (`worker.py:78-81`; Orc `schemas.py:700-703`).
  2. `submit` refuses with `AI_BUDGET_EXCEEDED` when the owner's rolling sum is over the user's budget.
  3. The refusal follows the AGENTS.md gate rule: a rule the model sees before it writes, how to pass it, one right and one wrong example, and a message naming the fix.
  4. INFERENCE: a run's cost is known only at its end, so a budget can overshoot by at most one run. Per-run caps bound that overshoot.
- **Concurrency.** FACT: the EDGE AI worker is serial (1.9). PROPOSED, cross-area: K dispatch slots, picking the
  oldest QUEUED job, with the one-active-per-owner index kept and round-robin by owner. Orc is one uvicorn process
  (`apps/market-ai-orc/Dockerfile:9`) whose stop and progress registries are in memory (`stop.py`, `progress.py`), so
  scaling Orc horizontally needs its own design.
- **Manual agent (EXEC-MANUAL).** FACT (1.8). PROPOSED, before the first external user: (a) a role check in edge-bff: only
  `admin` reaches `/api/v1/dev/manual/*`, and `/api/v1/models` hides the manual option from non-admins (edge-bff filters
  Orc's list, or Orc reads an `X-Saniti-Role`); (b) Orc scopes `pending()` and `answer()` to the step's run owner (the
  step stores the owner from `progress`/`stop` context); (c) or `AI_ENABLE_MANUAL_AGENT` stays off outside troubleshooting.
  Fix M259 in the same change.
- **Models list.** FACT: Orc's `/v1/models` takes no owner (`main.py:662-676`). With tiers, edge-bff filters by the user's tier.

### 2.6 Terminal tab

- FACT: the shell's Terminal page reaches terminal-api only through edge-bff with the gateway key
  (`main.py:398-431`, routes whitelisted in `main.py:35-37`). Every request becomes the one `TERMINAL_PROXY_SUBSCRIBER`
  (`terminal-api/app/main.py:157-180`; `store.py:117-119`). The screener-worker reaches `/xsection` the same way
  (`terminal-api/app/main.py:190-198, 418-419`).
- FACT: the quotas are per subscriber over rolling windows, read from `access_log` under a per-subscriber lock
  (`terminal-api/app/quota.py:1-41`; migration `20261025_100:78-88`). The 1e9 override on the gateway subscriber is
  TEMPORARY (report 6d.7; ERRORS around `:1540`, `:1944`).
- PROPOSED (P31 (a), approved as the direction on 2026-10-28):
  1. Add a nullable, unique column `terminal.subscriber.edge_owner_key` (migration). edge-bff creates the user's subscriber row when it creates the EDGE account, through terminal-api's admin API (`main.py:501-510`) or a shared migration-defined function. This subscriber has no usable password, so direct sign-in is impossible, and terminal-api cannot know the EDGE owner except through the gateway.
  2. edge-bff sends `x-terminal-proxy-owner: <owner_key>` with the gateway key. terminal-api's `subscriber()` resolves it by `edge_owner_key` (active and current) instead of `TERMINAL_PROXY_SUBSCRIBER`. A missing or unknown owner is 401, never a fallback to the shared account.
  3. The backtest-worker and screener-worker keep a service subscriber (the current `TERMINAL_PROXY_SUBSCRIBER`, renamed as a service account) with its own quota row.
  4. Quotas and audit then become per person (`access_log.subscriber_id`), and the per-account lock stops serialising all users (`FUTURE_PLAN.md:902-905`).
  5. INFERENCE: terminal-api also checks a `x-terminal-proxy-owner` value against the owner regex; it never accepts one without the gateway key.
- FACT: terminal-api also has a public domain with its own cookie `terminal_session`, SameSite `lax` by default
  (`terminal-api/app/config.py:23, 43`). INFERENCE: EDGE users never need it. The direct sign-in stays for administrator-managed
  subscribers (option A of 2026-10-25) or is closed when every user comes through EDGE (open question Q10).

### 2.7 Backtest tab

- FACT: the owner comes from `settings.owner` (`backtest.py:1050`). The tables are owner-keyed (2.3). There is at most one
  running job and 3 queued per owner (`config.py:29-37`; `backtest.py:437-457`). The claim skips owners with a running job
  (`backtest.py:516-526`). The worker has no notion of owner (`apps/backtest-worker/src/config.ts:24, 40`). The preview is
  latest-wins per owner (2.4).
- PROPOSED: the owner comes from the principal. Latest-wins becomes per (owner, page), as the Screener does
  (`client_order`; report 6d.6). A per-user compute budget follows P33 if the user chooses it. Throughput (one job
  EDGE-wide, report E5) is another area.

### 2.8 Screener (as designed, P30 (c) for Phase 1)

- FACT: every per-user row is keyed by `owner_key` (migration `20261028_001`). Every worker call carries the opaque tag
  HMAC-SHA256(`SCREENER_WORKER_KEY`, owner)[:16] (`screener.py:157-161`, test `tests/test_screener.py:449`). Ownership
  of items and the watchlist is tested (`tests/test_screener.py:923`). The only single-owner points are `screener.py:642, 903`.
- PROPOSED: pass the principal's owner to `ask()` and the routes. Nothing else changes (report 6d.3).

### 2.9 Browser state (all tabs)

- FACT: the shell keeps no credentials in storage (`edge-client.js:1`). It keeps these per browser, not per user:
  - `localStorage`: `edge-model-choice` (`index.html:11261, 11275, 11310`), panel widths and the theme (`index.html:10850-10858, 11077-11078, 12444, 12464`);
  - `sessionStorage`: `edge-side-attach:<conversation_id>`, which holds quoted answer text (`index.html:10959`).
- FACT: sign-out calls the API and resets in-memory state only (`index.html:10666`; `edge-client.js:11`).
- FACT: the Terminal and Screener pages cache market files in IndexedDB `terminal-files` keyed by sha256
  (`terminal/src/data/rack.ts:5, 15`; `screener/src/api/boot-cache.ts:3`). This is shared market data, not user data. The Screener drops
  another login's pointer (report 6d.3 table).
- PROPOSED: on sign-out, and when a different login signs in, clear `edge-side-attach:*`, `edge-research-context`
  and the model choice. Keep display preferences and the shared market-file cache.

### 2.10 Telegram

- FACT: telegram-trigger accepts one chat, `TELEGRAM_ALLOWED_CHAT_ID`, with a webhook secret
  (`apps/telegram-trigger/README.md:17-20`). telegram-monitor sends to one `TELEGRAM_CHAT_ID` (`apps/telegram-monitor/README.md`,
  variables). Logs: `Telegram_Command_Log.chat_id`, `Feature04_Retry_Request.chat_id` (live columns). Neither touches
  EDGE identities or user content.
- PROPOSED: Telegram stays an operator channel. Requirement: no user content (questions, owner keys, logins) in any Telegram
  message. Per-user alerts (for example Screener watchlist alerts) would be a new feature that links a chat to a user
  with a one-time code. Open question Q11.

### 2.11 Operations and credentials

- FACT: `EDGE_INITIAL_PASSWORD` is still on edge-bff (1.11). The dev E2E signs in as the owner with it.
- PROPOSED: dedicated test accounts (role `tester`, their own owner keys) whose credentials live only in the E2E
  runner's variables. Remove `EDGE_INITIAL_PASSWORD`. Record both in `RAILWAY_CHANGELOG.md` by name only.

---

## 3. What changes for many external users

| Need | Today (FACT) | Required (PROPOSED) |
|---|---|---|
| Accounts | One env login | User directory: login (email), display name, password verifier, role, status (invited, active, disabled), owner key, created and changed timestamps |
| Roles | None | `user`, `admin` (users, quotas, dev and manual routes, data-retention actions), optionally `tester`. Roles are checked server-side per route. The role is never sent by the browser |
| Isolation | Store-level owner filters; the owner comes from config | Owner from the session principal on every route; HTTP-level two-user tests (section 7); opaque owner keys; optional Postgres RLS as defence in depth (section 6, R14) |
| Sign-up / invitation | None | Invitation-only first (admin creates an invite; single-use token stored hashed, short expiry; the user sets a password). Self sign-up only with an explicit decision (Q1) |
| Password reset | None | Admin-issued single-use reset link (hashed token, 30-60 min, revokes all sessions). Self-service by email once an email provider is chosen. FACT: no email-sending integration exists in `apps/` (search for smtp, sendgrid, mailgun, postmark, resend: none) |
| Password policy | One verifier, scrypt n=16384 (`security.py:6-9`) | Same scrypt verifier format (shared with terminal-api, `terminal-api/app/security.py:6`). Minimum length about 12 or more; check against a breached-password list (k-anonymity API or a local list; Q4); rehash when parameters change |
| MFA | None (FACT: no TOTP or WebAuthn code) | TOTP required for `admin`, optional for users at first (Q3); recovery codes stored hashed. WebAuthn later |
| Audit | No sign-in or admin log in `edge_bff`; job logs carry no owner (`store.py:150, 199, 232`) | `edge_bff.auth_event` (user, event, ok, IP hash, user agent, at) for sign-in, sign-out, failure, reset, MFA, invite, role or status change. Admin actions log as `terminal.admin_log`. Service logs carry an owner tag (the Screener's HMAC style), never the login |
| Quotas and budgets | AI: none per owner. Terminal: one shared account. Backtest: 3 queued and 1 running per owner. Screener: lanes and limits | Per-user AI budget (2.5); per-user terminal subscriber (2.6); Backtest and Screener as designed (P33) |
| Data lifecycle | `jobs.input` and `conversation_ui` never purged (`README.md:327-333`); Orc conversations 30 days | Account deletion purges by `owner_key` in `edge_bff` and through a new Orc owner-delete endpoint (conversations, outputs, exports, bucket objects). A retention period for `jobs.input` is stated to users (Q8) |
| Sessions per user | Unlimited, 24 h absolute | Cap, idle timeout, a list of the user's sessions and "sign out everywhere" |

---

## 4. Options

### 4.1 Option A: user directory in `edge_bff` (PROPOSED as the first step; report P30 (a))

Sketch (PROPOSED DDL; names are illustrative):

```sql
CREATE TABLE edge_bff.users (
  user_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  owner_key    text NOT NULL UNIQUE CHECK (owner_key ~ '^[A-Za-z0-9._:@-]{1,128}$'),  -- immutable, opaque
  login        text NOT NULL UNIQUE CHECK (login = lower(login)),                       -- email
  display_name text NOT NULL,
  password_verifier text CHECK (password_verifier ~ '^scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}$'), -- NULL until invite accepted
  role         text NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin','tester')),
  status       text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active','disabled')),
  mfa_totp_secret_enc bytea, password_changed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE edge_bff.user_tokens (          -- invitations, password resets (one table, kind column)
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'), user_id bigint NOT NULL REFERENCES edge_bff.users,
  kind text NOT NULL CHECK (kind IN ('INVITE','RESET')), expires_at timestamptz NOT NULL, used_at timestamptz);
CREATE TABLE edge_bff.sign_in_attempts (login text, ip_hash text, ok boolean NOT NULL, at timestamptz NOT NULL DEFAULT now());
CREATE TABLE edge_bff.auth_events (...);
ALTER TABLE edge_bff.sessions ADD COLUMN user_id bigint REFERENCES edge_bff.users, ADD COLUMN last_seen_at timestamptz;
```

- Pros:
  - no vendor and about zero marginal cost;
  - reuses the existing session, CSRF, scrypt and cookie code;
  - the same shape as `terminal.subscriber`, which already runs live;
  - the grant model stays (`edge_bff_runtime`).
- Cons:
  - we build and own invitations, reset, MFA and breached-password checks;
  - email delivery needs a provider decision; invitation links can be handed over out of band by the admin at first.

### 4.2 Option B: external identity provider (OIDC)

- edge-bff becomes an OIDC client (authorization code with PKCE, state and nonce). After the callback it creates the same
  `edge_bff.sessions` row. `users` gains `idp_issuer` and `idp_subject` (unique) and keeps `owner_key`, role, status and quotas.
- Pros:
  - MFA, reset, email verification, social login and anomaly detection come with the provider.
- Cons:
  - vendor and data-processing terms for external users;
  - cost per monthly active user: UNKNOWN, prices not read for this note; re-read at decision time;
  - redirect URIs and a custom domain;
  - a hard dependency on the provider's availability for sign-in.
- INFERENCE: even with B, the `edge_bff.users` table and per-user `owner_key` stay. So A's schema is a prerequisite either way, and B can be added later as another sign-in method on the same users.

### 4.3 Per-user `owner_key` (common to A and B)

- PROPOSED: `owner_key` is opaque and immutable (for example `u_` + 24 random hex). It is never the email: logins change, and the
  owner key appears in Orc rows, sandbox reuse keys and worker tags. The format fits Orc's `OWNER_RE`
  (`conversations.py:51`), the `AI_conversation` check (`20260927_002:43`) and edge-bff's regex (`config.py:82`).
- Reserved and never issued: `default`, `edge-private` (kept for the current owner's account), `golden-*`, `test-*`,
  `someone-else`.

### 4.4 Recommendation (PROPOSED)

1. A now, invitation-only, with admin-issued reset links and TOTP for admins.
2. B considered only when self sign-up or social login is wanted (Q1, Q2).
3. Per-user terminal subscribers (P31 (a)) and the AI budget in the same EDGE-MULTIUSER execution.
4. The manual-agent and CSRF fixes go first, because they are leaks the moment a second user exists.

---

## 5. Migration path from the single owner (PROPOSED)

| Step | What | Rollback |
|---|---|---|
| M0 Hardening (no visible change) | Fix M259 (`write` on the manual POST plus a route-walk test); owner-scope or admin-gate Orc manual steps; move the sign-in limiter to Postgres; clear per-user browser state on sign-out; remove `EDGE_INITIAL_PASSWORD` once test accounts exist | Revert commits |
| M1 Schema | Forward migration: `users`, `user_tokens`, `sign_in_attempts`, `auth_events`; `sessions.user_id`. A one-off job seeds user #1: `owner_key = EDGE_OWNER` (live `edge-private`), `login = EDGE_LOGIN`, `password_verifier = EDGE_PASSWORD_VERIFIER` read from env inside the job and never printed, role `admin`, status `active`. Existing rows need no rewrite: their `owner_key` already equals user #1's | Tables are additive; drop through a new migration |
| M2 Code behind `EDGE_MULTIUSER` | `session()` returns the principal; all routes, Backtest and Screener take the owner from it; sign-in looks up `users` with a dummy verify; per-user session API. With the flag off, the env login maps to user #1 (the same owner), so behaviour is unchanged | Flag off |
| M3 Terminal identity | `terminal.subscriber.edge_owner_key`; a subscriber row per EDGE user; `x-terminal-proxy-owner`; the service account for the workers; end the TEMPORARY 1e9 override | Gateway falls back to the service account (temporary) |
| M4 Budgets and fairness | `edge_bff.ai_usage` and the per-user budget refusal; K AI dispatch slots round-robin by owner (cross-area); Backtest latest-wins per (owner, page) | Budget switch off |
| M5 Admin and accounts UI | Invite, disable, role and reset in an admin view; the user's own sessions list, password change, MFA enrolment | — |
| M6 First external user | Data-terms check (E6) answered; isolation suite green on dev; invite. After a grace period remove `EDGE_LOGIN` and `EDGE_PASSWORD_VERIFIER` (keep `EDGE_OWNER` only if user #1 still needs it) | Disable the user |

Each step follows the mandatory workflow:
- schema changes get a forward migration, `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md` and `Table_Catalog`/`Column_Catalog` for new `edge_bff` tables;
- Railway changes are recorded by name in `RAILWAY_CHANGELOG.md`;
- errors go in `ERRORS_AND_SOLUTIONS.md`;
- user texts go in `edge-labels.js`.

Every new refusal (`SIGN_IN_RATE_LIMIT` per login, `AI_BUDGET_EXCEEDED`, `ACCOUNT_DISABLED`, `INVITE_EXPIRED`) ships with the four parts of AGENTS.md "Gates and evidence".

---

## 6. Security requirements (PROPOSED)

- **R1 Owner source.** The owner comes only from the server-side session principal. It never comes from a body, query,
  header or cookie the browser sets (today's rule, `README.md:336`, kept).
- **R2 Same answer for "not yours" and "not found".** A resource of another owner answers exactly like an unknown id
  (status, code, timing class). Today's code does this: `store.py:136, 297, 305`; `screener.py:463`; Orc `stop.py:41`.
- **R3 Sign-in throttling in Postgres.** Throttle per login and per client IP. The real client IP must be established
  first (UNKNOWN 2.1). Use a dummy verify for an unknown login. Give one error code for wrong login, wrong password and
  locked. Unlock by time window, never by a user-visible count.
- **R4 Sessions.**
  - Use a 256-bit random token, store its hash (today) and rotate it on sign-in (today).
  - Revoke all of a user's sessions on password change, reset, disable or role change.
  - Cap sessions per user and add an idle timeout.
  - Check the user's status on every request (a join).
- **R5 CSRF.** Keep the HMAC token, the exact Origin check and SameSite=Strict. Every write route depends on `write`,
  enforced by a route-table walk test (M259).
- **R6 Cookies.** Host-only, Secure, HttpOnly and SameSite=Strict. Use the `__Host-` prefix on a custom domain and never
  set `Domain=`. terminal-api's `terminal_session` stays on its own host.
- **R7 CSP.** Drop `'unsafe-inline'` from the shell's `script-src` (use a nonce) before external users. Keep
  `frame-ancestors 'self'`.
- **R8 Orc trust boundary.**
  - Only edge-bff and the test runner hold `MARKET_AI_ORC_API_KEY`; the test runner gets its own key, restricted to test owners.
  - Refuse a missing `X-Saniti-Owner` when multi-user is on.
  - Owner-scope or role-gate the manual steps.
  - Rotate the key when holders change.
- **R9 Per-user rate limits** on expensive routes: AI submit (budget and requests per minute), exports, Backtest submit
  (exists), Screener (lanes exist), Terminal (per-user subscriber quotas). With more than one edge-bff replica, any limit
  that must hold globally lives in Postgres (report 6d.5).
- **R10 Audit.** `auth_events` and an admin log. Log lines carry an HMAC owner tag, never a login or email. Never log
  tokens or verifiers (today's rule: no access log, generic errors, `main.py:230-233`).
- **R11 Privacy and deletion.** An owner-wide purge in `edge_bff` and Orc (a new endpoint), including bucket outputs.
  Retention of `jobs.input` is stated to users.
- **R12 Credentials.**
  - No shared login; per-user test accounts.
  - `EDGE_INITIAL_PASSWORD` removed.
  - Invite and reset tokens stored hashed, single use, short-lived.
  - TOTP secrets encrypted with a key that is not in the database.
- **R13 Identifiers.** Unguessable public ids (today, FACT): `conv_` + 32 hex, `edge_` + 32 hex, `bt_` + 32 hex,
  `scr_` + 32 hex, `exp_` + 24 hex. The integer `user_id` never appears in the browser; the browser sees only the login
  and display name.
- **R14 Defence in depth (optional).** Postgres RLS on `edge_bff` tables with
  `owner_key = current_setting('edge.owner')`, set per transaction by `Store.connect(owner)`. It catches a forgotten
  `WHERE owner_key` at the cost of a session variable on every statement. The worker's cross-owner claim needs a separate
  role or a `BYPASSRLS` path.

---

## 7. Tenant isolation tests (PROPOSED test plan)

1. **Route-table walk.** For every route under `/api/` except health and sign-in: create users A and B. A creates one
   resource of each kind (conversation and run, side chat, pin, bookmark, export, backtest job, result and events, saved
   screen, My metric, watchlist entry). B calls every route with A's ids. Expect B to get the same status and code as for
   a random id, and A's state to be unchanged. The test is derived from `app.routes`, not from a list, so a new route
   cannot skip it.
2. **List routes.** B's lists (`/conversations`, `/backtests`, `/screener/items`, `/screener/watchlist`, the active
   run) never contain A's ids, including through search (`q=` with A's question text).
3. **Every write needs CSRF.** Every POST, PATCH, PUT and DELETE except sign-in returns 403 without `X-CSRF-Token`, with
   a valid Origin sent (M259 lesson).
4. **Session lifecycle.** A disabled user's session ends at its next request and on the open SSE stream within one poll.
   A password reset revokes all sessions. One user's CSRF token fails with another user's session.
5. **Sign-in limiter.** Failures against login A do not block login B. With per-IP limits, establish the IP source first
   (spoofed `X-Forwarded-For` test against Railway).
6. **Orc.** Header owner A cannot read, stop, branch, export or see the progress of owner B's request (exists:
   `tests/test_conversations.py:163`, `test_stop.py:15`, `test_progress.py:17`, `test_export.py:116`). Add: manual steps
   are visible and answerable only for the owner's own run, or only for admin.
7. **Terminal.** With `x-terminal-proxy-owner` A, quotas and `access_log` rows land on A's subscriber. An unknown owner
   is 401. No gateway key means no owner header is honoured.
8. **Screener and Backtest.** Latest-wins never cancels another owner's or another page's call. Owner tags differ per owner
   (exists for the Screener: `tests/test_screener.py:449`).
9. **Browser.** After sign-out and a sign-in as B on the same browser, no `edge-side-attach:*` or `edge-research-context`
   of A remains (Chromium test, as the existing UI tests).
10. **Load-time fairness** (with M4). With A looping heavy requests, B's p95 stays within the stated bound (report S23
    pattern).

---

## 8. Open questions for the user

- **Q1 Sign-up.** Invitation by the admin only, self sign-up with admin approval, or open sign-up?
- **Q2 Identity provider.** Our own accounts (A) first, or an external login provider (B; which one; Google login wanted)?
- **Q3 MFA.** Required for everyone, optional for users and required for admins, or not at first?
- **Q4 Reset and email.** Is an admin-issued reset link acceptable at first? Which email provider later (invites,
  resets, alerts)? Is a breached-password check wanted?
- **Q5 Roles and tiers.** Only `user` and `admin`, or plans with different quotas (AI budget, models, Terminal quotas,
  Backtest queue)?
- **Q6 AI for external users.**
  - Is the Monitor chat open to them?
  - What budget per user (USD per day or month), and which models per tier?
  - Does the manual agent stay admin-only or switched off?
- **Q7 Session policy.** Keep 24 h? Add an idle timeout? How many devices at once (terminal uses 2)?
- **Q8 Retention and deletion.** How long are users' questions (`jobs.input`) kept? What does "delete my account" erase?
- **Q9 Login identifier.** Email, required for invites and resets, instead of today's username `edge`?
- **Q10 terminal-api direct sign-in.** Keep it for administrator-managed subscribers, or close it once every user comes
  through EDGE?
- **Q11 Telegram.** Operator-only, or per-user alerts later?
- **Q12 Domain.** A custom domain for EDGE before external users? This affects the cookie prefix, CSP and identity-provider
  redirect URIs.
- **Q13 Existing history.** Confirm that today's owner `edge-private` (92 AI conversations, about 88 list rows, about 43
  backtests) becomes the user's own admin account, unchanged.
- **Q14 Data terms (E6, owned elsewhere).** Blocks M6 whatever the identity choice.

---

## 9. Evidence index

- **edge-bff**
  - `apps/edge-bff/app/config.py:12-19, 29-37, 54-57, 80-83`
  - `apps/edge-bff/app/main.py:179, 237-240, 262, 265-275, 278-284, 438-476, 478-493, 581-593, 595-611, 683-706`
  - `apps/edge-bff/app/security.py:6-28`
  - `apps/edge-bff/app/store.py:59-69, 71-98, 128-137, 158-169, 326-328`
  - `apps/edge-bff/app/worker.py:32-45, 70-81`
  - `apps/edge-bff/app/client.py:34-37, 60-67`
  - `apps/edge-bff/app/backtest.py:432-457, 516-526, 935-936, 1002-1037, 1050, 1125-1160`
  - `apps/edge-bff/app/screener.py:157-161, 428-514, 606-610, 642, 903`
  - `apps/edge-bff/Dockerfile:49`
  - `apps/edge-bff/README.md:323-337, 395-413`
  - `apps/edge-bff/static/edge-client.js:1, 11, 139`
  - `apps/edge-bff/static/index.html:10666, 10959, 11261-11310`
- **market-ai-orc**
  - `apps/market-ai-orc/app/conversations.py:6-8, 49-51, 97-109`
  - `apps/market-ai-orc/app/main.py:590-592, 641-692, 694-791`
  - `apps/market-ai-orc/app/manual_agent.py:112-117`
  - `apps/market-ai-orc/app/model_choices.py:52-57`
  - `apps/market-ai-orc/app/stop.py:40-44`, `apps/market-ai-orc/app/progress.py:105-109`, `apps/market-ai-orc/app/result_store.py:309-316`, `apps/market-ai-orc/app/schemas.py:700-703`
- **terminal-api**
  - `apps/terminal-api/app/main.py:157-198, 230-260, 494-525`
  - `apps/terminal-api/app/config.py:21-28, 43-45`
  - `apps/terminal-api/app/store.py:84-119`
  - `apps/terminal-api/app/security.py:16-25, 40-47`
  - `apps/terminal-api/app/quota.py:1-41`
- **Other services**
  - `apps/backtest-worker/src/terminal.ts:5-6`
  - `apps/orc-test-runner/run.py:29, 86, 123`
  - `apps/telegram-trigger/README.md:17-20`
- **Migrations:** `database/migrations/` `20261008_002`, `20261024_002`, `20261026_005`, `20261028_001`, `20260927_002`, `20261025_100`
- **Records**
  - `ERRORS_AND_SOLUTIONS.md:3030-3047` (M259)
  - `RAILWAY_CHANGELOG.md:18`
  - `FUTURE_PLAN.md:882-924`
  - `EXEC.md:8503-8513`
  - `PLAN.md:912-927`
  - `.railway/railway.ts:158-190`
- **Live, read-only, 2026-10-28**
  - pg_catalog: owner columns of every schema; no RLS; role limits 20, 10, 20; `edge_bff` indexes; no Screener tables.
  - `AI_conversation`: 534 rows, 29 owners, distribution by md5 prefix.
  - Railway variable names: edge-bff, terminal-api, market-ai-orc, backtest-worker.
  - Boolean checks: `EDGE_OWNER` = `edge-private`; session 86400 s; `EDGE_INITIAL_PASSWORD` present; both public domains under `up.railway.app`.
  - Deployments: edge-bff `32a25029` SUCCESS (`f265ae4`); terminal-api `689dc465` SUCCESS.
