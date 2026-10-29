# EDGE-MULTIUSER: EDGE for external users on every tab (planner draft, 2026-10-28)

**Status: PROPOSED.** This is read-only planning: nothing has been executed. Approval of this plan is not a go. Each
phase starts only after the user's go for that phase (AGENTS.md, Plans). This draft makes no change to the repository
(no edit, no git state change), no Railway mutation and no database write.

**Basis (the user's words, 2026-10-28)**
- "Also, ini nanti akan multiuse,r jadi infrastruktur harus bisa di scale UP + efficient cost wise." (`PLAN.md:914-915`)
- P29, on who the "many users" are: "External / Ini termasuk tab2 lagi ya monitor, terminal, backtest juga" (`PLAN.md:915`;
  `EXEC.md:8503`).
- Asked whether "rekomendasi kamu sudah OK" also covers the flow decisions D1-D14 and P24-P34, the user answered "YEs".
  FACT: this is recorded in `EXEC.md:8503-8516` (branch commit `ce941a3`). For this plan it means:
  - P30 (a): the user directory is its own EDGE-wide item, and this plan is that item.
  - P31 (a): one terminal identity per user, plus service accounts for the workers.
  - P32: two `screener-worker` replicas from the first external user.
  - P33: a per-user CPU budget in the Screener.
  - P34: per-replica caches.
  - P25 and P26 (the shell waits for the model list, and the shell is sent uncompressed): measure first, then option (a).

**Inputs**
- Three area notes in this folder. Each holds file:line evidence for its claims:
  - identity (`identity_sessions_per_user_state.md`);
  - capacity and cost (`capacity_fairness_scale_cost.md`);
  - data terms and privacy (`data_terms_exposure.md`).
- The Screener report, section 6d (`.../scratchpad/report/06d_multi_user_scale_cost.md`).
- `verification/screener/AUDIT.md` (6d, 13.3).

**Evidence base**
- Repository branch `claude/charming-hamilton-faq25e` at HEAD `0a20886` (Screener work in progress).
- **Re-checked 2026-10-28 about 19:10 UTC** (the draft was first written at 15:50 UTC):
  - FACT: `main` on GitHub is at `15ec418` (GitHub API, `list_commits`). The local remote-tracking ref still reads
    `2e7f7fd`, because this re-check made no `git fetch`.
  - FACT: deployed edge-bff is `7b05b9fd`, SUCCESS, commit `baa0903` (created 16:52 UTC, `railway status --json`). The
    earlier deployment `32a25029` (`f265ae4`) is superseded.
  - FACT: the four commits on `main` after `f265ae4` touch only the Terminal front-end (`apps/edge-bff/terminal/src/...`),
    tests, `verification/terminal_api/...` and record files (GitHub commit file lists of `54b198a`, `c6602d5`, `baa0903`,
    `4f17e4d`, `15ec418`). No `app/*.py` file changed, so every identity, worker and store fact below still holds for the
    deployed code. The Terminal change matters for quotas (row 14, MP-11, Appendix A item 9).
- Railway has one environment, `dev`.
- Lines marked **[re-read]** were re-read by this note on 2026-10-28 (code, live pg_catalog through `pgq2.py`, Railway CLI
  status and variable names). Other facts are quoted from the sibling notes, which give their file:line. Code line numbers
  are from the branch working tree.
- Labels: FACT (evidence given), INFERENCE, PROPOSED, UNKNOWN.

---

## 1. Current verified state: one owner wherever it matters

| # | Area | State (FACT) | Evidence | Consequence with many users (INFERENCE) |
|---|---|---|---|---|
| 1 | Identity | One owner, one login and one password verifier, all from environment variables. Sign-in compares the one login. Every session is created for `settings.owner`. The session check refuses any other owner | `apps/edge-bff/app/config.py:12-14, 54-57`; `main.py:268` and sign-in `main.py:440-463` **[re-read]** | A second person cannot have an account |
| 2 | Owner source | `settings.owner` appears 41 times in `main.py`, plus `backtest.py:1050` and `screener.py:642, 903`. No route reads the owner from the session | grep count **[re-read]** | Every route serves the one owner |
| 3 | Data model | Every `edge_bff` table carries `owner_key`, and so does Orc's `AI_conversation`. Child tables are reached through owner-checked parents. No table has row-level security. Live: 6 `edge_bff` tables, none with row-level security, and the Screener tables are not applied yet. `AI_conversation` holds 519 conversations under 14 owners at 19:10 UTC: `golden-multi-angle` 415, `edge-private` 92, and 12 rows under 4 test owners. At 15:50 UTC it held 534 under 29; INFERENCE: the 30-day expiry (`expires_at`) removed late-September test conversations | live pg_catalog and counts **[re-read twice]**; identity §2.3 | The data layer is ready; the routes and identity are not |
| 4 | Sign-in limiter | In process: 5 failures a minute per `request.client.host`, with uvicorn `--no-proxy-headers` | `main.py:440-449` **[re-read]**; `apps/edge-bff/Dockerfile:49` | It probably keys on Railway's edge address: one person's typos lock everyone out, and there is no per-account limit |
| 5 | Sessions | 24 h absolute lifetime, no idle timeout, no cap per owner | `config.py:18`; identity §2.1 | Needs a per-user policy |
| 6 | Orc trust | Anyone holding `MARKET_AI_ORC_API_KEY` acts as any owner through `X-Saniti-Owner`. A missing header becomes the shared owner `default` | `apps/market-ai-orc/app/conversations.py:6-8, 50, 97-103` (identity §2.5) | The test runner and edge-bff can impersonate anyone |
| 7 | Manual agent | `pending()` returns every waiting step of every run with its full model payload. edge-bff exposes both routes to any session, and the POST takes `session`, not `write` (M259, OPEN) | `manual_agent.py:112-116`; edge-bff `main.py:581-592` **[re-read]**; `ERRORS_AND_SOLUTIONS.md:3030` | Once a second user exists, one user can read another's prompts and inject model replies |
| 8 | AI dispatch | One loop claims one job and awaits it to the end. The claim is FIFO by `created_at`. A partial unique index allows one active job per owner | `worker.py:32-45`, `store.py:158-169`, migration `20261008_002:46-48` **[re-read]** | The queue holds at most one job per owner, so FIFO is already fair across owners. The limit is the single slot: 2 users at once already queue |
| 9 | AI run time | Runs take 100-200 s on average, p90 250-450 s (495 runs, 2026-10-07..26) | capacity §3.2 | 10 users at once means about 25 min of wait at the back of the queue |
| 10 | Sandbox | Session cap 4 in code (default 2); dev sets 4 (`RAILWAY_CHANGELOG.md:791`, user: "Ya naikan ke 4"; `PROJECT_CONTEXT.md:53`). `PY_SANDBOX_MAX_SESSIONS_PER_REQUEST` is not set on dev, so one answer may hold all 4 sessions. A full sandbox waits up to `PY_SANDBOX_OPEN_WAIT_SECONDS` (set on dev; value not read). The volume pins it to 1 replica | `apps/market-python-sandbox/app/config.py:287-289, 296`, `sessions.py:704-716` **[re-read]**; Railway variable names **[re-read]**; `PROJECT_CONTEXT.md:53, 87` | About 7 users at once if each run uses one session; as few as 1 if heavy runs open four |
| 11 | Orc state | The stop registry and progress live in memory "because the service runs one replica" | `stop.py:5-8` **[re-read]**; `progress.py:24` | Orc cannot add replicas without moving this state |
| 12 | AI budget | Caps exist per run only. One OpenRouter key whose USD limit is raised by hand. Orc returns each run's `cost` | identity §2.5; `schemas.py:700-703` | One user can use up AI for everyone |
| 13 | Backtest | One job thread and one preview thread. The claim takes the oldest QUEUED job of an owner with nothing running, so it is FIFO across owners with no rotation. Each owner may have 1 running and 3 queued | `backtest-worker/src/server.ts:108`; `backtest.py:516-527` **[re-read]**; `config.py:37` | An owner who queues 3 jobs delays every other owner |
| 14 | Terminal | Every gateway request is the one `TERMINAL_PROXY_SUBSCRIBER`, under one advisory lock, with quotas overridden to 1e9 (TEMPORARY). A per-subscriber model already runs: directory, quotas, a 2-session cap, a Postgres sign-in throttle and an admin log. Since `54b198a` (deployed in `7b05b9fd`), a chart can add up to 2 assets, and each asset asks `/bundle` twice (price, then broker), on top of the chart's own bundle and the IHSG and compare series | `apps/terminal-api/app/main.py:174-180` **[re-read]**; migration `20261025_100`; `terminal/src/data/live.ts` `loadAsset`, `loadAssetFlow` at `15ec418` **[re-read]** | There is no per-person quota or audit. One chart view can now cost up to about 5 grants and 3 tickers (INFERENCE) |
| 15 | Screener | Phase 1 is being built on the branch. Its tables and the HMAC owner tag are per owner. `screener-worker` does not exist on Railway yet | identity §2.8; `railway status` **[re-read]** | Only `screener.py:642, 903` need the session owner |
| 16 | edge-bff process | One process and one replica. The AI and Backtest loops run inside it, both switched by `EDGE_WORKER_ENABLED`. The pool is 6 against the role limit of 20 | `main.py:191, 194`, `config.py:23, 65` **[re-read]**; live `rolconnlimit` **[re-read]** | A web/worker split needs no new switch |
| 17 | Shell page | 474,253 bytes, served `no-store` with no gzip. The CSP has `script-src 'unsafe-inline'` for two inline scripts (line 6, 610 characters; line 10292, 192,810 characters). Answers are built with `createElement`/`textContent` ("never innerHTML") | `static/index.html` measured; `index.html:11807` **[re-read]**; `main.py:262` | A hash-based CSP is possible, and the injection surface is smaller than the CSP suggests |
| 18 | Postgres | One instance with a 4 GB limit; no PgBouncer, HA or point-in-time recovery (PITR). `shared_buffers` 128 MB, `work_mem` 4 MB. Role limits: edge 20, terminal 20, conversation 10, audit 10, orc 5, governor 5, pgweb 5, publisher 4 | live `pg_settings`, `pg_roles` **[re-read]**; capacity §2.3 | The role limits bound scale-out |
| 19 | Railway | Pro plan. One environment, `dev`. Everything runs in `sfo`; the `terminal-display` bucket is in `sin`. A second database, `Postgres-E8GM`, holds the web-governor stores | `railway status` **[re-read]**; `BACKTEST_END_TO_END.md:656` | External users would share an environment with tests and work-in-progress deploys |
| 20 | Cost today | About USD 33.4 a month of usage, of which RAM 22.05 | capacity §2.2 | AI tokens will dominate (section 4) |
| 21 | Data terms | No licence is recorded for TradingView (anonymous token; "tidak memberi izin tertulis") or for Stockbit (one personal JWT). Nothing is recorded on IDX, KSEI, logos, web results or model output. No page shows attribution, terms of use or a privacy notice | data_terms §1, §3, §6; `EXEC.md:8190-8193` | This blocks the first external user |
| 22 | Privacy | Users' questions are kept with no purge (`edge_bff.jobs.input`) and forever with no owner link (`AI_research_run_audit`). Conversations expire after 30 days | data_terms §5.1 | Needs retention, deletion and a notice |
| 23 | Browser | `edge-side-attach:*` (quoted answer text) survives sign-out | `index.html:10959, 10666` (identity §2.9) | The next user on a shared browser sees it |
| 24 | Leftover credential | `EDGE_INITIAL_PASSWORD` is still set, and the dev E2E scripts use it | identity §1.11; edge-bff variable names **[re-read 19:10 UTC]** | Remove it once test accounts exist |
| 25 | Catalog precedent | `Table_Catalog` has no `edge_bff` or `terminal` rows | live query **[re-read]** | New operational tables follow that precedent (confirm against `DATABASE_CATALOG.md` when executing) |

**In one line (INFERENCE):** EDGE has a multi-owner data model behind a single-owner application. The work is mostly
identity, admission (fairness and budgets), one service split, and data terms. It is not a rewrite of the stores.

---

## 2. Target architecture for external users

### 2.0 Topology (PROPOSED)

```
Browser ──HTTPS (custom domain, __Host- cookie)──> edge-bff WEB  (N replicas, stateless; EDGE_WORKER_ENABLED=false)
   │                                                 │ principal {user_id, owner_key, role} from edge_bff.sessions ⋈ users
   │                                                 │ admission: per-owner limits + usage ledger (Postgres)
   │                                                 ├─> terminal-api   x-terminal-proxy-key + x-terminal-proxy-owner → that user's subscriber
   │                                                 ├─> screener-worker ×2   x-screener-owner = HMAC tag (P32)
   │                                                 └─> backtest-worker  previews (owner tag)
   └─ presigned bucket downloads (sin, free egress)
edge-bff WORKER (1 replica, private; EDGE_WORKER_ENABLED=true)
   ├─ AI dispatch: K slots, FIFO (one active job per owner) ─> market-ai-orc (1 replica, vertical) ─> sandbox shard(s), governors
   └─ Backtest loop: round-robin over owners ─> backtest-worker (K job threads; later a 2nd service with job affinity)
backtest-worker, screener-worker ─> terminal-api with their OWN service accounts and keys
Postgres: edge_bff (users, tokens, auth_events, sign_in_attempts, sessions, jobs, usage_ledger, user_limits, ...), terminal, AI_*
```

Proposals MP-01 to MP-28 follow, grouped by area. Each one states:
- the need;
- the general class of the problem;
- the fix and the layer that owns it;
- what it covers and what it does not;
- its risks and cost;
- how it is verified;
- whether it is permanent or TEMPORARY.

### 2.1 Accounts and identity

**MP-01 User directory with invitation-only accounts** (Phase 2)
- **Need:** each person has their own account (row 1).
- **Class:** identity and authentication.
- **Fix and owner:** edge-bff and a forward migration.
  - Tables:
    - `edge_bff.users`: `user_id`, `owner_key` (opaque and immutable, `u_` + 24 hex), `login` (lower-case email), `display_name`, `password_verifier` (the existing scrypt format, shared with terminal-api), `role` (`user`, `admin` or `tester`), `status` (`invited`, `active` or `disabled`), timestamps;
    - `edge_bff.user_tokens` (invitation and reset, hashed, single use, short expiry);
    - `edge_bff.auth_events`;
    - `sessions.user_id` and `last_seen_at`.
  - User #1 is seeded **at edge-bff start when `users` is empty**, from the `EDGE_OWNER`, `EDGE_LOGIN` and `EDGE_PASSWORD_VERIFIER` values the service already holds. No verifier passes through another job. User #1 keeps `owner_key = edge-private` and becomes `admin`, so the 92 conversations and about 43 backtests need no data rewrite.
  - Reserved, never-issued keys: `default`, `edge-private`, `golden-*`, `test-*`, `someone-else`.
- **Covers:** sign-in per person, invitations, disabling, admin-issued reset links.
- **Does not cover:** self sign-up, email delivery, social login, payments (MU7-MU9, MU4).
- **Risks and cost:** we own the security of the flows (mitigated by R3-R12 and the tests in section 5). About USD 0 marginal.
- **Verification:** unit tests; DRYRUN and APPLY of the migration on dev with read-back; IT1-IT6.
- **Permanence:** permanent. An external identity provider (OIDC) can be added later on the same table (`idp_issuer`, `idp_subject`).

**MP-02 The owner comes from the session principal on every route** (Phase 2, behind `EDGE_MULTIUSER`)
- **Need:** every route serves the signed-in person (row 2).
- **Class:** tenant isolation; the authorization source.
- **Fix and owner:** edge-bff.
  - `session()` returns `{user_id, owner_key, role, login}` and `write()` passes it on.
  - The 41 sites in `main.py`, `backtest.py:1050` and `screener.py:642, 903` take `principal.owner_key` for each request.
  - The store layer already takes the owner as an argument (identity §2.2), so no SQL changes.
  - With the flag off, the environment login maps to user #1, so behaviour is unchanged.
- **Covers:** Monitor, Backtest, Screener and the Terminal proxy.
- **Does not cover:** Orc's trust in the header (MP-05) or the terminal subscriber (MP-09).
- **Risks and cost:** a missed site would serve the wrong owner. The route-table walk test IT1 is derived from `app.routes`, so a new route cannot skip it.
- **Verification:** IT1, IT2; the existing E2E with the flag off.
- **Permanence:** permanent. The flag is TEMPORARY and is removed after the first external user plus a grace period.

**MP-03 Sign-in throttling in Postgres** (Phase 1: the per-login part; Phase 2: the per-IP part after the header test)
- **Need:** one person's failures must not lock out everyone, and an account needs its own limit (row 4).
- **Class:** abuse limiting across processes and replicas.
- **Fix and owner:** edge-bff and a migration.
  - `edge_bff.sign_in_attempts(login, ip_hash, ok, at)`, with rolling windows per login and per client IP (the precedent is `terminal.sign_in_attempt`: 10 per email and 30 per IP in 15 min).
  - A dummy scrypt verify for an unknown login.
  - One error code for every failure.
  - Per-IP limits are enabled only after a probe settles whether Railway's edge overwrites or appends a client-sent `X-Forwarded-For` (UNKNOWN).
- **Covers:** brute force and accidental lockout; it is correct with N replicas.
- **Does not cover:** distributed credential stuffing (MFA, MU10; monitoring trigger T12).
- **Risks and cost:** one INSERT per attempt. The probe needs a short-lived echo route or service (Railway change, recorded).
- **Verification:** five failures on an unknown login leave the real login usable (today's limiter would block it); IT5.
- **Permanence:** permanent.

**MP-04 Session policy** (Phase 2)
- **Need:** shared devices and many devices per person (row 5).
- **Class:** session lifecycle.
- **Fix and owner:** edge-bff.
  - An idle timeout plus the absolute lifetime.
  - At most K sessions per user (oldest revoked).
  - Revoke all sessions on a password change, reset, disable or role change.
  - The session check joins `users` and refuses `disabled`.
  - A "sign out everywhere" action, and the user's list of their own sessions.
  - Values: MU12.
- **Covers:** session reach after a disable (within one SSE poll, `EDGE_POLL_SECONDS`).
- **Does not cover:** device fingerprinting.
- **Risks and cost:** one join per request (the session SELECT already costs about 4 ms; 6d.5).
- **Verification:** IT4.
- **Permanence:** permanent.

### 2.2 Per-user isolation

**MP-05 Close the cross-tenant paths before a second user exists** (Phase 1)
- **Need:** rows 6 and 7.
- **Class:** confused deputy and trust boundary.
- **Fix and owner:**
  - edge-bff:
    - M259: the manual POST depends on `write`, with a route-table test that every POST, PATCH, PUT and DELETE except sign-in needs CSRF;
    - `/api/v1/dev/manual/*` is admin only, and `/api/v1/models` hides the manual choice from non-admins.
  - Orc:
    - each manual step stores its run's owner, and `pending(owner)` and `answer(owner, step_id)` see only that owner's steps;
    - with `EDGE_MULTIUSER` on, Orc refuses a missing `X-Saniti-Owner` instead of falling back to `default`.
  - Orc and Railway: the test runner gets its own key, which Orc accepts only for test owners (`golden-*`, `test-*`, `someone-else`). Variable names are recorded in `RAILWAY_CHANGELOG.md`.
  - The manual agent's policy toward external users is MU15.
- **Covers:** reading, answering or stopping another user's run through the manual path or through the header.
- **Does not cover:** a holder of the edge-bff key itself (that key's rotation, R8).
- **Risks and cost:** small code changes. `AI_TOOLS.md` and `AI_MODELS.md` are unaffected (no tool or model-call change; their drift tests confirm).
- **Verification:** IT3, IT6; Orc tests `test_manual_agent*` extended to two owners.
- **Permanence:** permanent.

**MP-06 Shell CSP without `'unsafe-inline'`, using script hashes** (Phase 1)
- **Need:** defence in depth for external users (row 17).
- **Class:** browser script injection.
- **Fix and owner:** edge-bff computes the sha256 of the two inline `<script>` blocks of `index.html` at start and sends `script-src 'self' 'sha256-…' 'sha256-…'`.
  - Hashes, not nonces: a nonce changes the shell's bytes on every response, which would defeat P26's `ETag`/`304`.
  - Hashes also keep the one-file layout that `preview/edge_preview.py import` round-trips (AGENTS.md, EDGE front-end).
  - `style-src 'unsafe-inline'` stays (lower risk; a later item).
- **Covers:** any injected inline or external script.
- **Does not cover:** injected styles.
- **Risks and cost:** a forgotten inline handler would break. FACT: no `on…=` attributes were found in `index.html` **[re-read]**.
- **Verification:** a Chromium smoke test with the strict CSP and no console CSP violations; a test that the header hashes match the served file.
- **Permanence:** permanent.

**MP-07 Clear per-user browser state** (Phase 1)
- **Need:** row 23.
- **Class:** shared-device leakage.
- **Fix and owner:** `static/index.html` and `edge-client.js`.
  - On sign-out, and when a different login signs in, clear `edge-side-attach:*`, `edge-research-context` and the model choice.
  - Keep the theme, panel widths and the shared market-file cache (IndexedDB `terminal-files`, keyed by sha256, with no user data).
- **Covers:** quoted answers and drafts left in the browser.
- **Does not cover:** the browser's own HTTP cache (data stays `no-store`).
- **Risks and cost:** none.
- **Verification:** IT9.
- **Permanence:** permanent.

**MP-08 Postgres row-level security as defence in depth** (can follow)
- **Need:** catch a forgotten `WHERE owner_key`.
- **Class:** defence in depth.
- **Fix and owner:** a migration plus `Store.connect(owner)`, which sets `edge.owner` per transaction. The worker's cross-owner claim uses a separate role.
- **Covers:** a store-level bug.
- **Does not cover:** a wrong principal.
- **Risks and cost:** a session variable on every statement, and a second role.
- **Verification:** IT1 with the policy on.
- **Permanence:** optional; decided after Phase 2 (identity R14).

### 2.3 Per-user terminal identity and quotas, plus worker service accounts (P31 (a), decided)

**MP-09 One terminal subscriber per EDGE user, through the gateway** (Phase 3)
- **Need:** row 14. Quotas, the advisory lock and `access_log` per person.
- **Class:** per-tenant identity on a downstream service.
- **Fix and owner:** terminal-api, a migration and edge-bff.
  - A nullable unique column `terminal.subscriber.edge_owner_key`. The row is created when the EDGE account is created (terminal-api admin API) and has no usable password.
  - edge-bff sends `x-terminal-proxy-owner: <owner_key>` with the gateway key.
  - `subscriber()` resolves it to an active, current row. A missing or unknown owner is 401, never a fallback to a shared account.
  - The header is honoured only with the gateway key.
- **Covers:** per-person quotas, audit, and the end of global serialisation.
- **Does not cover:** worker traffic (MP-10).
- **Risks and cost:** the Terminal, Backtest previews and Screener all pass through it.
  - Read `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` first (AGENTS.md).
  - terminal-api deploys by CLI under the M248 procedure, outside the publisher window (M250).
- **Verification:** IT7; Backtest E2E (`verification/backtest/e2e_dev.py`); Terminal smoke; `access_log` rows per subscriber, read back with a role that can read `terminal` (pgweb cannot).
- **Permanence:** permanent.

**MP-10 Worker service accounts; end the TEMPORARY 1e9 override** (Phase 3)
- **Need:** worker downloads serve many users from one cache, so charging them to a person would be wrong.
- **Class:** service identity.
- **Fix and owner:** terminal-api and Railway.
  - `backtest-worker` and `screener-worker` each get their own key variable and their own subscriber row, with quotas sized to measured use (a cold 12-stock portfolio is 28 MB; the Screener needs 15-30 MB per publication per replica, 6d.7).
  - The people's override is removed; the precedent job is `verification/terminal_api/jobs/quota_unlimited_edge_owner.sql`.
  - User fairness for worker work stays in edge-bff (MP-12).
- **Covers:** quota truth and worker audit.
- **Does not cover:** per-user fairness inside a worker.
- **Risks and cost:** a quota sized too low stops Backtest or Screener refreshes. Size from the measured use × 3 and alert at 50% (trigger T6).
- **Verification:** IT7; worker refresh logs; quota rows.
- **Permanence:** permanent. The 1e9 override is TEMPORARY by its own record.

**MP-11 Quota counters, "files I have", and ticker-based quotas** (Phase 3)
- **Need:** usage is summed from the log under a lock, and a cached re-open still consumes quota. `files_per_hour` 60 allows only about 12 ticker opens an hour (capacity §3.4). INFERENCE: with the new assets feature (row 14), a chart with 2 assets asks for about 13 files and 3 tickers, so the same quota allows about 4-5 such views an hour.
- **Class:** quota accounting.
- **Fix and owner:**
  - terminal-api: a counter row per subscriber per hour and per day, updated in the grant transaction (`FUTURE_PLAN.md:907-924` item b). The log stays as a 90-day audit.
  - Terminal page (`terminal/src/data/live.ts`) and terminal-api: `/bundle` accepts the sha256 values the browser already holds and grants and counts only the missing files.
  - Binding limits are tickers per hour and day plus bytes per day; the values are MU16.
- **Covers:** quota cost independent of log size; fair counting.
- **Does not cover:** copying of allowed data (`verification/terminal_api/DESIGN.md:133-134`; section 6).
- **Risks and cost:** a contract change on `/bundle`, tested with the existing 40-test suite pattern. `live.ts` changed on `main` on 2026-10-28 (EXEC-TERMINAL-ASSETS, `54b198a`), so this work builds on that version, and the "have" list must cover the asset calls (`loadAsset`, `loadAssetFlow`) too.
- **Verification:** unit tests; a timed grant (target under 50 ms, T6).
- **Permanence:** permanent.

### 2.4 Fairness and limits per user in Backtest, Screener and AI

| Layer | Monitor (AI) | Backtest | Screener | Terminal |
|---|---|---|---|---|
| In flight per owner | 1 active message (FACT, index) | 1 running + 3 queued; 1 preview (FACT) | 1 run + 1 preview per (owner, page) (6d.6) | browser-driven |
| Across owners | FIFO over at most one job per owner: already fair. K slots (MP-13) | round-robin (MP-15) | owner lanes, deficit round robin (6d.6) | per-user lock (MP-09) |
| Per-owner budget | USD per day (MU6) | jobs per day (MU16) | CPU per minute (P33, decided) | tickers and bytes per day (MU16) |
| Enforced at | edge-bff submit | edge-bff submit and claim | edge-bff (single entry); worker lanes as a backstop | terminal-api |
| Refusal (each with the four parts below) | `AI_BUDGET_EXCEEDED` | `BACKTEST_DAILY_LIMIT` | `SCREENER_CPU_BUDGET` (in `limits[]`) | existing quota refusals |

Every new user-facing refusal ships with four parts. AGENTS.md "Gates and evidence" requires them for gates that refuse a
model reply; this plan applies them to every user gate too, as the Screener's `limits[]` already does:
1. the rule, visible before acting (the remaining budget shown beside the composer or run button);
2. how to pass it (the reset time, or ask the admin);
3. one right and one wrong example;
4. a message in plain Indonesian (`edge-labels.js`, `user_texts.py`) that names the limit, what was used and when it resets.

These limits protect cost, so they are guarantees and stay in code. Their values are the user's words (AGENTS.md, Judgement
principle).

**MP-12 One usage ledger and per-owner limits** (Phase 4)
- **Need:** budgets per user across tabs (row 12; P33). With two Screener replicas, a per-replica bound becomes 2× (6d.6).
- **Class:** metering and admission.
- **Fix and owner:** edge-bff and a migration.
  - `edge_bff.usage_ledger(owner_key, feature, window_kind, window_start, units, cost_usd, events)`: counters, not a log, written with `INSERT … ON CONFLICT DO UPDATE` from data edge-bff already relays (Orc's `cost`, the backtest `duration_ms`, the Screener's `timings_ms`, export counts).
  - `edge_bff.user_limits(owner_key | tier, feature, limit)`, in the shape of `terminal.quota_override`.
  - Day windows use Asia/Jakarta time.
- **Covers:** AI USD per day, Backtest jobs per day, Screener CPU per minute and exports.
- **Does not cover:** in-run cost. A run's cost is known only at its end, so overshoot is at most one run, bounded by the per-run caps.
- **Risks and cost:** one UPSERT per answer and one SELECT per admission.
- **Verification:** IT12; ledger read-back against Orc's audit cost.
- **Permanence:** permanent.

**MP-13 AI throughput: K dispatch slots** (Phase 4)
- **Need:** row 8.
- **Class:** a head-of-line single slot.
- **Fix and owner:** the edge-bff worker.
  - `run()` claims up to K jobs, holding each under its own lease and heartbeat (`asyncio` semaphore). The claim SQL is unchanged: one active job per owner keeps FIFO fair.
  - K starts at 2. K stays ≤ the free sandbox sessions ÷ sessions per answer (row 10; `PY_SANDBOX_MAX_SESSIONS_PER_REQUEST` is an EXEC-V user decision, see MU6).
- **Covers:** queue wait for light users (T1).
- **Does not cover:** sandbox capacity (MP-20).
- **Risks and cost:** contention on the `market_ai_orc` 5 and `market_sql_governor` 5 role limits and on the governor's heavy-query concurrency (measure, T8). Orc's sync route holds one thread per run (pool about 40, INFERENCE).
- **Verification:** a mini load test of 3 test users at once (all dispatched); T1 and T2 read from logs.
- **Permanence:** permanent. K is a variable.

**MP-14 Split edge-bff into web and worker services** (Phase 4)
- **Need:** web replicas must not each run AI and Backtest loops (capacity §3.1).
- **Class:** separating stateful loops from the stateless request tier.
- **Fix and owner:** Railway and `.railway/railway.ts`.
  - A new private service `edge-bff-worker`: same repository and image, `EDGE_WORKER_ENABLED=true`, no public domain, 1 replica. It also carries the session cleanup (`worker.py:38-40`).
  - The public `edge-bff` gets `EDGE_WORKER_ENABLED=false`.
- **Covers:** safe web scale-out, and loop restarts independent of web deploys.
- **Does not cover:** the pool limit: web N × 6 + worker 6 ≤ 20 means N ≤ 2 until the role limit rises (MP-19).
- **Risks and cost:** about USD 1 a month. Two deploy targets from one image.
- **Verification:** deployment SUCCESS for both; AI and Backtest E2E; `/ready` on web without the loops.
- **Permanence:** permanent.

**MP-15 Backtest fairness and throughput** (Phase 4)
- **Need:** row 13.
- **Class:** FIFO starvation and a single slot.
- **Fix and owner:**
  - edge-bff `backtest.py` claim: choose the owner whose last `started_at` is oldest (NULLS FIRST), then that owner's oldest QUEUED job. Latest-wins becomes per (owner, page), like the Screener.
  - backtest-worker `src/server.ts`: the preview queue is round-robin by owner tag. K = 2 job threads, after a parity test and a memory test (per-thread cache `BACKTEST_CACHE_BYTES` 1.5 GB).
  - Later, a second worker service, with a `backtest_jobs.worker` column for job affinity, since Railway has no sticky sessions.
- **Covers:** light users' wait while a heavy user queues 3 (T4).
- **Does not cover:** a single 900 s job, which still holds one slot (`BACKTEST_TIMEOUT_SECONDS`).
- **Risks and cost:** RAM up to +1.5 GB per thread, about USD 5-15 a month. Read `BACKTEST_END_TO_END.md` and `CONTRACT.md` first.
- **Verification:** IT8; a Backtest parity test (same results); a fairness scenario in the load test.
- **Permanence:** permanent.

**MP-16 The Screener as decided (P32, P33, P34)** (built in EXEC-SCREENER; the external gate is in Phase 6)
- **Need:** the Screener ready for external users.
- **Class:** shared per-publication compute with per-owner admission.
- **Fix and owner:** `screener-worker`, as designed in 6d.
  - Stateless replicas; 2 replicas from the first external user (P32).
  - A per-user CPU budget (P33), charged in MP-12's ledger at edge-bff from `timings_ms`. Each worker's per-owner lane stays as the backstop. INFERENCE: this places the decided budget at the one point every request passes; it does not change the decision.
  - Per-replica caches (P34).
- **Covers:** Screener fairness and cost.
- **Does not cover:** what the data terms allow (section 6).
- **Risks and cost:** about USD 12 a month for 2 replicas (6d.9).
- **Verification:** 6d.11 S21-S24.
- **Permanence:** permanent.

**MP-17 AI spend guard at the key level** (Phase 1)
- **Need:** one shared OpenRouter key with a hand-raised limit (row 12).
- **Class:** cost circuit breaker.
- **Fix and owner:** the operator channel.
  - A scheduled check of the key's usage against its limit (OpenRouter key endpoint; re-read its docs at build time) in `telegram-monitor`, alerting at 50% and 80% (T3).
  - Test owners (`golden-*`) get their own budget rows in MP-12, so test suites cannot drain users' AI.
- **Covers:** an early warning.
- **Does not cover:** per-user fairness (MP-12).
- **Risks and cost:** one HTTP call per interval.
- **Verification:** the alert fires in a dry run with a lowered threshold.
- **Permanence:** permanent.

### 2.5 edge-bff statelessness for more than one replica

| State | Today (FACT) | Rule for N > 1 (PROPOSED) |
|---|---|---|
| Sign-in limiter | in memory, per TCP peer | Postgres (MP-03) |
| AI and Backtest loops | in every process | only in `edge-bff-worker` (MP-14) |
| Preview latest-wins (Backtest, Screener) | per process | keep. A cross-replica race costs compute, not correctness (6d.5) |
| Model list, terminal client, catalog caches | per process | keep. The Screener catalog cache is monotonic by `published_at` (6d.5) |
| `preview_pages` and Screener `pages` | grow per owner without bound | add a bounded LRU per owner (INFERENCE: small today, unbounded with many owners) |
| Pool | 6 per process; role limit 20 | raise `edge_bff_login` by migration (for example to 40) before N > 2 (MP-19) |
| Shell | 474 KB, `no-store`, no gzip | P26: gzip for HTML, JS and JSON, and `ETag` with revalidation for the shell only; data stays `no-store`. First settle whether Railway's edge already compresses (L-U1) |

Scale order: `--workers 2` in one container, then replicas, within the pool rule (T7).

### 2.6 AI capacity path

**MP-20 AI scale-out path** (can follow, on triggers T1 and T2)
- **Need:** more than about 7 users at once on Monitor.
- **Class:** a volume-pinned single replica.
- **Fix and owner:**
  1. Measure the sessions per answer from the sandbox logs, and decide `PY_SANDBOX_MAX_SESSIONS_PER_REQUEST` for multi-user (MU6 sub-question; it was an EXEC-V user decision).
  2. Sandbox shards `market-python-sandbox-2..n`, each with its own volume. Orc picks a shard by conversation id, since data reuse is per conversation (`PROJECT_CONTEXT.md:53`).
  3. Orc stays at 1 replica and scales vertically (0.002 vCPU average). Its stop and progress state moves to Postgres only if a trigger requires a second Orc replica.
- **Covers:** Monitor concurrency.
- **Does not cover:** token cost (MP-12).
- **Risks and cost:** about USD 7-8 a month per idle shard; each shard is another volume to back up.
- **Verification:** the load test (MP-28) at 10 and 50 synthetic owners.
- **Permanence:** permanent once triggered.

### 2.7 Data exposure control

**MP-22 Exposure switch per source and role** (Phase 5; the values come from MU2 and MU3)
- **Need:** until each source's terms are settled, external roles must not receive it raw (section 6).
- **Class:** data-licence guarantee (it protects data, so it lives in code).
- **Fix and owner:** one table in code, `SOURCE_EXPOSURE[source][role]` = `raw`, `derived` or `off`, read by:
  - edge-bff: the Terminal proxy, by dataset (terminal-api already separates datasets in grants); the Screener preview bars; every export route;
  - the AI path: a second SQL Governor login for external roles whose Postgres grants exclude `off` sources. Postgres then enforces it, and the list lives in `scripts/provision_market_sql_governor_login.py`. Orc selects the profile from a role header that edge-bff sets.
  - A refusal `SOURCE_NOT_AVAILABLE` carries the four parts.
- **Covers:** raw and derived exposure per role.
- **Does not cover:** copying of what is allowed (that is a terms question).
- **Risks and cost:** a second governor role (connection limit 5) and Orc routing (design detail UNKNOWN; reviewed at Phase 5).
- **Verification:** IT13.
- **Permanence:** permanent.

**MP-23 Retention, deletion and audit linkage** (Phase 5; the values come from MU18)
- **Need:** row 22.
- **Class:** the privacy lifecycle.
- **Fix and owner:**
  - edge-bff: a purge of `jobs.input`, `conversation_ui`, backtest jobs and trials, and Screener items, by owner and by age.
  - Orc: a new owner-delete endpoint covering conversations, outputs, exports and bucket objects.
  - A migration: an HMAC owner tag on `AI_research_run_audit` and on the web-governor stores (`Postgres-E8GM`), or no question text stored for external roles.
  - terminal-api: subscriber deactivation, and pruning of `sign_in_attempt`.
  - The account deletion flow: admin first, self-service later.
- **Covers:** "delete my account" and stated retention.
- **Does not cover:** Railway's log retention, or third-party retention (MU17).
- **Risks and cost:** destructive operations. DRYRUN first, and audit every purge.
- **Verification:** IT14.
- **Permanence:** permanent.

**MP-24 Notices and attribution** (Phase 5)
- **Need:** row 21: no terms, privacy notice or attribution.
- **Class:** user-facing disclosure.
- **Fix and owner:** edge-bff static pages and `edge-labels.js`:
  - a privacy notice and terms of use, drafted per MU19;
  - source lines per screen and export, once MU2 settles the attribution;
  - the Lightweight Charts attribution (today `attributionLogo:false` everywhere; how attribution is given is UNKNOWN, data_terms Q-TV6);
  - "Not investment advice" kept.
- **Covers:** disclosure.
- **Does not cover:** legal sufficiency. That is for the user and their counsel; no legal conclusion is drawn here.
- **Risks and cost:** none.
- **Verification:** a page smoke test; a grep test that every export carries the source line.
- **Permanence:** permanent.

**MP-25 Prompt data policy at the model provider** (Phase 5; only with the user's approval, MU17)
- **Need:** external users' prompts go to OpenRouter's default routing with no data-policy option set (data_terms §4).
- **Class:** third-party processing.
- **Fix and owner:** Orc provider settings (OpenRouter's data-policy option; re-read the API at decision time). This is a provider change, so it needs approval (AGENTS.md, Model and provider). Regenerate `AI_MODELS.md`.
- **Covers:** provider logging and training.
- **Does not cover:** OpenRouter's own retention.
- **Risks and cost:** fewer endpoints for DeepSeek, so latency or price may change. Measure with a small golden test first.
- **Verification:** provider logs show only compliant endpoints.
- **Permanence:** permanent once approved.

### 2.8 Operations, environment and scale

**MP-18 edge-bff replica rules:** see 2.5 (Phase 4, and on T7).

**MP-19 Postgres headroom** (Phase 6, and on T8 and T9)
- **Fix and owner:** a migration and Railway.
  - Raise `edge_bff_login`, which carries the web and worker pools.
  - PgBouncer in transaction mode before total connections pass about 60-80. First check psycopg's `prepare_threshold`; only transaction-level advisory locks are used (FACT, capacity §3.6).
  - Memory and tuning on T9.
  - PITR or verified backups per MU21.
- **Risks and cost:** RAM at USD 10 per GB-month; PITR price UNKNOWN (re-read Railway at decision time).
- **Verification:** `pg_stat_activity` per role; a restore drill if PITR is enabled.
- **Permanence:** permanent.

**MP-21 Observability per owner** (Phase 4 to 6)
- An admin view of the ledger per owner per day.
- Alerts T1-T14 to the operator channel only, with no user content in Telegram (identity §2.10).
- `auth_events`.
- Service logs carry an HMAC owner tag, never a login or email (R10).
- **Verification:** the log leak scan (`tools/leakcheck.py` precedent in this scratchpad; the house equivalent at execution).
- **Permanence:** permanent.

**MP-26 Environment and release discipline** (Phase 6; MU20)
- **Need:** row 19. External users must not share the environment that holds tests, golden runs and work-in-progress CLI deploys.
- **Options:** see MU20.
  - At a minimum (TEMPORARY, for a closed beta):
    - user-facing services deploy only from `main` after tests, outside market hours;
    - test suites run under test owners with their own budget rows;
    - no CLI upload of a tree not in Git (M217, D24 lesson).
- **Risks and cost:** a production tier costs about USD 30-35 a month more (section 4.6). How market data would be shared across environments is UNKNOWN.
- **Permanence:** the beta discipline is TEMPORARY; a production environment is permanent.

**MP-27 Custom domain** (Phase 6; MU22)
- Cookie `__Host-edge_session`, never `Domain=`.
- `allowed_origins`, the CSP and terminal-api origins updated together.
- **Verification:** IT3 and IT4 on the new origin.
- **Permanence:** permanent.

**MP-28 Cross-tab load test and cost calibration** (Phase 6; MU26)
- Synthetic owners: either `tester` accounts (after Phase 2), or a private-network harness sending distinct owner values (the precedents are orc-test-runner and `feature-05-06-job`).
- Scenarios:
  - 1, 10 and 50 owners per tab: AI queue wait and cost per turn by route;
  - Backtest wait for light owners while one owner queues 3 heavy jobs;
  - terminal grants per second with per-user subscribers;
  - edge-bff relay at 50-200 concurrent requests;
  - Postgres RAM, hit ratio and connections;
  - Railway usage before and after;
  - 6d.11 S21-S25.
- **Cost:** AI tokens of about USD 1-5 per run of the suite (INFERENCE: 50-150 turns × USD 0.02-0.03).
- **Output:** results with deployment ids and log locations; the trigger thresholds are then set from them.
- **Permanence:** a repeatable suite.

### 2.9 Scaling triggers (PROPOSED thresholds; MP-28 sets the final values)

| # | Signal (source) | Threshold | Action |
|---|---|---|---|
| T1 | Age of the oldest QUEUED `edge_bff.jobs` row, p95 over 15 min in market hours | > 30 s | raise K (MP-13) up to free sandbox sessions, then add a shard (MP-20) |
| T2 | Sandbox sessions busy, or slot waits (sandbox logs) | 4/4 for > 5% of market minutes | add a sandbox shard |
| T3 | AI spend per day against the OpenRouter key limit; owners at their budget | 50% / 80%; any owner capped | alert; review caps (MU6) |
| T4 | Oldest QUEUED `backtest_jobs`, p95 | > 30 s | K = 2 threads, then a second worker |
| T5 | backtest-worker RSS | > 70% of its limit | lower the per-thread cache or raise the limit |
| T6 | terminal-api `/bundle` p95 and grant time; a service account above 50% of its quota | > 1 s / > 50 ms / > 50% | counters (MP-11); resize the quota |
| T7 | edge-bff event-loop lag p95, pool waits, 5xx | > 50 ms or waits > 0 | `--workers 2`, then replicas |
| T8 | Connections per role against `rolconnlimit` | > 70% | raise the limit or add PgBouncer |
| T9 | Postgres RAM against 4 GB, buffer hit ratio, temp spills in market hours | > 70% / < 95% / growing | memory and tuning |
| T10 | Screener triggers | 6d.10 | 6d.10 |
| T11 | Weekly usage per service (GraphQL `usage`) | +30% week on week | review against section 4 |
| T12 | Sign-in failures per login and per IP, lockouts per hour | 10× baseline | alert; consider MFA for users |
| T13 | Share of submits refused by a budget, per day | > 10% | review the caps with the user (cost against usability) |
| T14 | A scheduled two-user isolation canary (IT1 subset) | any failure | page the operator; turn off `EDGE_MULTIUSER` for new sign-ins |

---

## 3. Phased delivery

Each phase follows the mandatory workflow. Each one:
- inspects the live state before changing anything;
- applies forward migrations only, with DRYRUN, APPLY and read-back;
- updates `DATABASE_SCHEMA.md`, `DATABASE_CHANGELOG.md`, `RAILWAY_CHANGELOG.md` (variable names only) and `ERRORS_AND_SOLUTIONS.md`;
- puts user wording in `edge-labels.js` and `user_texts.py`;
- claims a deployment only at `SUCCESS`;
- ends with `git diff --check`, a commit, and a push to `main`.

| Phase | Goal | Proposals | Can start | Exit criterion |
|---|---|---|---|---|
| 0 | Decisions | MU1-MU26 (section 7) | now | MU1 (go for Phase 1); MU2/MU3 in progress with providers |
| 1 | Hardening on today's single owner (no visible change) | MP-03 (per login), MP-05, MP-06, MP-07, MP-17; Railway config drift; header probe | on the go (MU1) | M259 FIXED; IT3, IT6 (manual), IT9 green |
| 2 | Accounts, with the owner from the session (`EDGE_MULTIUSER`) | MP-01, MP-02, MP-03 (per IP), MP-04; tester accounts; remove `EDGE_INITIAL_PASSWORD` | after Phase 1 and MU7-MU13 | IT1, IT2, IT4, IT5 green with 2+ tester accounts; flag off leaves behaviour unchanged |
| 3 | Terminal identity (P31) | MP-09, MP-10, MP-11 | after Phase 2 (parallel with 4) | IT7 green; override removed; Backtest E2E green |
| 4 | Fairness, budgets, throughput | MP-12, MP-13, MP-14, MP-15, MP-16 (budget part), P26, MP-21 | after Phase 2, plus MU6 and MU16 | IT8, IT10, IT12 green; T1 and T4 within target in the mini load test |
| 5 | Privacy and exposure | MP-22, MP-23, MP-24, MP-25 (if approved) | design any time; values after MU2, MU3, MU17-MU19 | IT13, IT14 green; notices live |
| 6 | Launch readiness | MP-19, MP-26, MP-27, MP-28; P32 second replica; gate G1-G14 | after Phases 2-5 | gate green; first invite |

### 3.1 Phase 1: hardening (single owner, no visible change)

- **edge-bff**
  - `app/main.py`:
    - manual POST on `write` (M259);
    - admin-only manual routes (with one owner, the owner is the admin);
    - limiter to Postgres per login;
    - the CSP with hashes;
    - a route-table CSRF walk test.
  - `app/store.py`: attempts queries.
  - `app/security.py`: hashes.
  - `static/index.html`, `static/edge-client.js`: clear state on sign-out.
  - Tests under `apps/edge-bff/tests/`.
- **market-ai-orc**
  - `app/manual_agent.py`: the step stores its owner; `pending(owner)` and `answer(owner, …)`.
  - `app/main.py`: the manual routes take the header owner.
  - Tests. No change to the prompt, tools or models (the drift tests of `AI_TOOLS.md`, `AI_MODELS.md` and the prompt history must stay green).
- **Migration:** `database/migrations/<date>_edge_bff_sign_in_attempts.sql`.
- **Railway**
  - `railway config pull --force` and `config plan` to settle the `.railway/railway.ts` drift (`TERMINAL_PROXY_*`, `EDGE_TERMINAL_URL`, `BACKTEST_CACHE_DIR*` are not declared; capacity §2.1).
  - A short-lived header-echo probe for `X-Forwarded-For`, removed afterwards.
  - The key-limit alert in `telegram-monitor` (MP-17).
- **Records**
  - ERRORS: M259 status update.
  - New entries (next free M numbers when executing):
    - the global sign-in lockout via the proxy address;
    - the manual agent crossing owners;
    - the AI single dispatch slot;
    - the Backtest FIFO, which is not a rotation (6d.8 E5 correction);
    - the `.railway/railway.ts` variable drift;
    - `EDGE_INITIAL_PASSWORD` left set.
  - READMEs of edge-bff and Orc.
- **Verification:** tests; deployment ids at SUCCESS; live: five failures on an unknown login, then the real login still signs in; the table read back.
- **Rollback:** revert. The table is additive.

### 3.2 Phase 2: accounts

- **edge-bff**
  - `app/config.py`: `EDGE_MULTIUSER` and policy values.
  - `app/main.py`:
    - the principal;
    - sign-in by lookup with a dummy verify;
    - the session API returns the principal and capabilities;
    - admin routes: invite, reset link, disable, role, session list, revoke-all;
    - accept-invite and set-password.
  - `app/store.py`.
  - `app/backtest.py:1050` and `app/screener.py:642, 903`: owner per request.
  - `static/index.html`, `edge-labels.js`, `edge-client.js`: invite and reset pages, a minimal admin view, "sign out everywhere".
  - README identity section.
- **market-ai-orc**
  - `app/conversations.py`: refuse a missing owner when on.
  - `app/main.py`: a second key for the test runner, restricted to test owners.
- **orc-test-runner:** its own key variable.
- **Migration:** `database/migrations/<date>_edge_bff_users.sql` (`users`, `user_tokens`, `auth_events`, `sessions.user_id`, `last_seen_at`). User #1 is seeded at edge-bff start.
- **Railway** (names only):
  - `EDGE_MULTIUSER` on edge-bff;
  - the new Orc key on market-ai-orc and orc-test-runner;
  - tester credentials on the E2E runner;
  - delete `EDGE_INITIAL_PASSWORD`.
- **Records:** `PROJECT_CONTEXT.md` (owner model), `DATABASE_SCHEMA.md` and the changelogs.
- **Coordination:** `screener.py` is being written on the EXEC-SCREENER branch. Phase 2 starts after Screener Phase 1 merges to `main`, or rebases onto it (risk RK11).
- **Verification:** IT1, IT2, IT4, IT5, IT6 with two tester accounts on dev. With the flag on, user #1 sees the same 92 conversations.
- **Rollback:** flag off.

### 3.3 Phase 3: terminal identity

- **Read first:** `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md`.
- **terminal-api**
  - `app/main.py`: `subscriber()` with the owner header and the service keys.
  - `app/store.py`: counters in the grant transaction.
  - `app/quota.py`, `app/config.py`, `app/security.py`.
  - `/bundle` "have" list.
  - Tests.
- **Migration:** `database/migrations/<date>_terminal_edge_owner_counters.sql` (`subscriber.edge_owner_key`, service subscriber rows, `usage_counter`, grants).
- **edge-bff:** `app/main.py` proxy header; creation of a subscriber with each account.
- **backtest-worker:** `src/terminal.ts`, `src/config.ts` (own key).
- **screener-worker:** the same, once built.
- **Terminal page:** `terminal/src/data/live.ts` (send the held sha256 values).
- **Railway:** key variables on terminal-api, backtest-worker and screener-worker. CLI deploys under M248, outside the M250 window.
- **Data:** remove the people's 1e9 override; set service quotas from measured use.
- **Records:** `BACKTEST_END_TO_END.md`, `CONTRACT.md`, terminal-api README, the ERRORS U1 status.
- **Verification:** IT7; Backtest E2E; Terminal smoke; quota and audit rows read back.
- **Rollback:** an explicit TEMPORARY switch maps people to a capped shared subscriber. It is never silent and never unlimited.

### 3.4 Phase 4: fairness, budgets, throughput

- **Migration:** `database/migrations/<date>_edge_bff_usage.sql` (`usage_ledger`, `user_limits`).
- **edge-bff**
  - `app/worker.py`: K slots; a ledger write at FINISHED.
  - `app/backtest.py`: the round-robin claim; latest-wins per (owner, page); the ledger.
  - `app/screener.py`: the ledger from `timings_ms`; the P33 check.
  - `app/main.py`: budget admission; remaining budget in the session API; gzip and `ETag` for the shell (P26).
  - `app/config.py`: `EDGE_AI_DISPATCH_SLOTS` and limit defaults.
  - `edge-labels.js`, `index.html`: budget display and refusals.
- **backtest-worker:** `src/server.ts`, `src/config.ts` (K threads after the parity and memory test; the owner-tagged preview queue).
- **Railway:** the new service `edge-bff-worker`; `EDGE_WORKER_ENABLED=false` on web; `.railway/railway.ts`.
- **Records:** `RAILWAY_CHANGELOG.md`, `BACKTEST_END_TO_END.md` (claim rule), `CONTRACT.md`, ERRORS.
- **Verification:** IT8, IT10, IT12; a mini load test with 3 tester accounts.
- **Rollback:** K=1; the budget switch off; the worker service scaled to 0 with `EDGE_WORKER_ENABLED=true` on web.

### 3.5 Phase 5: privacy and exposure

- **edge-bff:** the exposure table and its checks on the Terminal proxy, Screener preview and exports; purge jobs; account deletion.
- **market-ai-orc:** the owner-delete endpoint; selection of the governor profile.
- **Scripts:** `scripts/provision_market_sql_governor_login.py`, for a second, narrower login.
- **Migrations:**
  - an HMAC owner tag on `AI_research_run_audit`;
  - the web-governor store tags (`Postgres-E8GM`);
  - `terminal.sign_in_attempt` pruning.
- **Pages:** the privacy notice, terms and attribution in `edge-labels.js` and static files.
- **Orc provider setting:** only if MU17 approves it (regenerate `AI_MODELS.md`).
- **Verification:** IT13, IT14.
- **Rollback:** the exposure table defaults to `off` for external roles. Purges are audited and DRYRUN first.

### 3.6 Phase 6: launch readiness

The environment (MU20), backups and PITR (MU21), the domain (MU22), the role limits and PgBouncer (MP-19), the
observability alerts (MP-21), the load test and cost calibration (MP-28), the second `screener-worker` replica (P32), the gate
below, then the first invite. After a grace period, remove `EDGE_LOGIN` and `EDGE_PASSWORD_VERIFIER`.

### 3.7 Gate: what must exist before the first external user

| # | Must exist | Proposal | Why it cannot follow |
|---|---|---|---|
| G1 | A written answer per data source, with the exposure set to match | MU2, MU3, MP-22 | The data may not be shown otherwise (section 6) |
| G2 | Accounts: invitation-only, with disable and admin-issued reset | MP-01 | A second person cannot sign in otherwise |
| G3 | The owner from the session on every route; isolation suite green | MP-02, IT1-IT6 | Otherwise a cross-tenant leak |
| G4 | Manual-agent and CSRF paths closed; Orc refuses a missing owner | MP-05 | A leak and injection otherwise |
| G5 | Sign-in throttle per login in Postgres | MP-03 | A global lockout otherwise |
| G6 | Session policy with revoke-all | MP-04 | A disabled user keeps access otherwise |
| G7 | Per-user terminal subscriber; worker service accounts; no people at 1e9 | MP-09, MP-10 | No per-person bound or audit otherwise |
| G8 | If Monitor is open to externals: an AI budget per user and K ≥ 2 | MP-12, MP-13, MU6 | Runaway cost and a global queue otherwise |
| G9 | Backtest round-robin claim | MP-15 | Starvation otherwise |
| G10 | Screener: 2 replicas and a per-user CPU budget (P32, P33) | MP-16 | Decided by the user |
| G11 | Privacy notice, terms, retention and a deletion path | MP-23, MP-24, MU18, MU19 | Personal data of external users |
| G12 | Strict shell CSP; per-user browser state cleared | MP-06, MP-07 | Defence in depth on shared devices |
| G13 | The environment and backup decision executed (MU20, MU21) | MP-26, MP-19 | Loss of user data or unstable deploys otherwise |
| G14 | Key-limit alert, ledger view and isolation canary | MP-17, MP-21, T14 | Silent failure otherwise |

### 3.8 Can follow (after the first external user, or on a trigger)

- Row-level security (MP-08).
- Sandbox shards and Orc state in Postgres (MP-20).
- edge-bff replicas beyond 2 (role limit), and a terminal-api replica (`terminal_api_login` 20 against 2 × 8).
- A second backtest-worker service with job affinity.
- PgBouncer (if not needed earlier).
- An OIDC provider, self sign-up, email self-service reset, WebAuthn.
- Tiers and payments (MU4, MU11).
- Per-user Telegram alerts (MU25).
- A region nearer Indonesia (MU24).
- The `style-src 'unsafe-inline'` clean-up.

---

## 4. Cost model per user and per concurrent user

### 4.1 Measured inputs (FACT, from the sibling notes, which give the queries)

| Input | Value | Source |
|---|---|---|
| Platform usage today (dev, one user) | USD 33.4 a month: RAM 22.05, volumes 8.41, CPU 2.12, egress 0.85. Postgres 13.86; sandbox 7.24; each EDGE-path service 0.5-1.6 | Railway usage API 10-24..28 × 7.5 (capacity §2.2) |
| Prices | RAM USD 10 per GB-month; vCPU USD 20 per vCPU-month; egress USD 0.05/GB; volume USD 0.15 per GB-month; bucket egress free; private network free | Railway docs read 2026-10-28 (6d.1) |
| AI cost per turn | USD 0.0004 (router greeting) to 0.07; suite averages 0.019-0.071; central 0.03 | `RAILWAY_CHANGELOG.md` samples (capacity §3.2) |
| AI run time | 100-200 s average, p90 250-450 s | `AI_research_run_audit`, 495 runs |
| Backtest job | 5-12 s end to end, about 7 vCPU-s | `apps/backtest-worker/README.md:422-440` |
| Screener uncached run | 0.5 vCPU-s; replica about 0.6 GB | 6d.9 |
| terminal-api grant | about 25 ms under the lock; 20 concurrent: median 0.53 s | `ERRORS_AND_SOLUTIONS.md:2302-2305` |
| Storage per active user-month | about 0.1 GB | capacity §3.6 |

### 4.2 Formula (INFERENCE)

```
monthly_usd = F_platform + Σ capacity_steps + N × (m_ai + m_infra)
F_platform  ≈ 33.4 today + 12 (screener-worker ×2, P32) + 1 (edge-bff-worker)   [+ 30-35 if a production tier, MU20]
m_ai        = days × turns_per_day × c_turn      (c_turn 0.02-0.07, central 0.03); with a cap B: m_ai ≤ days × B
m_infra     ≈ USD 0.1 per active user-month (Backtest 0.02, Screener 0.01, Terminal < 0.01, egress 0.02, storage 0.02)
```

### 4.3 Per active user per month (INFERENCE; profile: 21 trading days, 10 AI turns, 20 backtests, 200 Screener runs, 50 ticker opens a day)

| Component | USD/user-month |
|---|---|
| AI tokens | **6.3** (range 2.1-29.4, for 5-20 turns a day at USD 0.02-0.07 a turn) |
| Everything else | **≈ 0.08** |
| Total | **≈ 6.4**, of which AI is about 98% |

Effect of a per-user AI cap (MU6). The cap makes AI cost bounded instead of open-ended:

| Daily cap | Turns a day at USD 0.03 | Worst case per user-month (21 trading days / 30 days) |
|---|---|---|
| USD 0.25 | about 8 | USD 5.25 / 7.50 |
| USD 0.50 | about 16 | USD 10.50 / 15.00 |
| USD 1.00 | about 33 | USD 21.00 / 30.00 |

### 4.4 Per concurrent user, and capacity per configuration (INFERENCE)

Per user-hour of active use:
- Monitor at 20 turns an hour: tokens USD 0.40-1.40, plus Orc and sandbox residency USD 0.04-0.08.
- Backtest at 10 jobs an hour: under USD 0.001.
- Screener: about USD 0.001.
- Terminal: negligible (bucket egress is free).

Total: about **USD 0.65 an hour with AI**, about **USD 0.002 without** (plus the fixed replicas).

| Users at once without queueing | Monitor | Backtest | Screener | Terminal |
|---|---|---|---|---|
| Today | about 2 (1 slot, utilisation 0.56) | about 6 (1 slot) | not deployed | about 280 (one lock), assuming 1 grant per view; about 55 if every view adds 2 assets (about 5 grants) |
| After Phase 4 | about 7 at K = 4 (if 1 session per answer; as few as 1-2 if answers hold 4) | about 12 (K = 2) | about 74 (2 replicas × K 2) | per-user locks (no global serialisation) |
| Each further step | +about 7 per sandbox shard (about USD 7-8 a month) | +about 6 per job slot (USD 5-15 a month) | +about 37 per replica (about USD 6 a month) | terminal-api replica needs a role change |

### 4.5 Scenarios (USD a month; INFERENCE; inputs replaced by MP-28 and real logs)

| Daily users (at once) | Fixed infra | Monitor closed to externals | AI central (0.03 × 10 a day) | AI at a cap of USD 0.50 a day (worst case) |
|---|---|---|---|---|
| 10 (3) | about 50 | about 51 | about 115 | about 156 |
| 50 (15) | about 95 (about 70-75 without the AI steps) | about 75-80 | about 415 | about 625 |
| 200 (60) | about 165 (about 100-135 without the AI steps) | about 120-155 | about 1,445 | about 2,285 |

Add about USD 30-35 a month to every column if MU20 chooses a production tier. The PITR, domain and email provider prices
are UNKNOWN (re-read them at decision time).

### 4.6 New fixed costs this plan adds (INFERENCE)

| Item | USD a month | When |
|---|---|---|
| `screener-worker` second replica (P32) | about 6 (12 for both) | first external user |
| `edge-bff-worker` | about 1 | Phase 4 |
| Backtest K = 2 | 5-15 | on T4 |
| Sandbox shard | 7-8 each | on T1 and T2 |
| Postgres +1 GB | 10 | on T9 |
| PgBouncer | about 1 | on T8 |
| Production tier (MU20 (b)) | about 30-35 (edge-bff 1.0, Orc 1.3, sandbox 7.2, governors 3.0, audit 0.8, terminal-api 1.5, backtest 0.5, screener 12, a small user-state database 3-5) | before an open or paid launch |
| PITR / HA, domain, email | UNKNOWN | MU21, MU22, MU9 |

### 4.7 Cost-efficiency levers (PROPOSED; ordered by effect)

1. A per-user AI cap and the key alert (MP-12, MP-17): the only open-ended cost.
2. Keep cheap turns on the router (a greeting costs USD 0.0004) and say so in the budget display.
3. "Files I have" on `/bundle` (MP-11): fewer grants and presigns.
4. Shell gzip and `ETag` (P26): 474 KB down to 103 KB per open, near zero on revalidation.
5. Threads before replicas; replicas only on triggers; no Redis and no volume for the Screener (6d).
6. Shared per-publication compute (Screener, Terminal): marginal cost near zero.
7. PgBouncer before buying RAM for connections.

---

## 5. Security and privacy requirements, and tests

### 5.1 Requirements (PROPOSED; R1-R14 as in identity §6, with R15-R20 added here)

| # | Requirement | Owner layer | Test |
|---|---|---|---|
| R1 | The owner comes only from the server-side session principal, never from the body, query, a browser header or a browser cookie | edge-bff | IT1 |
| R2 | "Not yours" answers exactly like "not found" (status, code, timing class) | edge-bff, Orc | IT1 |
| R3 | Sign-in throttle per login (and per IP once the source is trusted), a dummy verify, one error code | edge-bff | IT5 |
| R4 | 256-bit tokens stored hashed, rotated on sign-in; revoke-all on credential, role or status change; a cap per user; idle timeout; status checked on every request | edge-bff | IT4 |
| R5 | CSRF HMAC, exact `Origin` and SameSite=Strict on every write (route walk) | edge-bff | IT3 |
| R6 | Cookie host-only, Secure, HttpOnly, `__Host-` on a custom domain | edge-bff | IT4 |
| R7 | Shell CSP without `'unsafe-inline'` scripts (hashes) | edge-bff | smoke test |
| R8 | Orc: only edge-bff holds the user key; the test key is limited to test owners; a missing owner is refused; manual steps are owner-scoped or admin-only; keys rotated when holders change | Orc | IT6 |
| R9 | Per-user limits on expensive routes, in Postgres once N > 1 | edge-bff, terminal-api | IT10, IT12 |
| R10 | `auth_events` and an admin log; logs carry an HMAC owner tag only; never a token, verifier, login or email | edge-bff | IT11 |
| R11 | Owner-wide purge across `edge_bff`, Orc and the bucket; retention stated | edge-bff, Orc | IT14 |
| R12 | No shared login; hashed single-use invitation and reset tokens; TOTP secrets encrypted with a key held outside the database | edge-bff | IT4 |
| R13 | Unguessable public ids; `user_id` never in the browser | all | IT1 |
| R14 | Optional row-level security | Postgres | IT1 (policy on) |
| R15 | **Exposure guarantee:** an external role never receives a source marked `off`, raw or in an export | edge-bff, governor | IT13 |
| R16 | **Cost guarantee:** no AI dispatch for an owner over budget; overshoot at most one run | edge-bff | IT12 |
| R17 | **Admin hardening:** TOTP required for `admin` (MU10); every admin action audited | edge-bff | IT11 |
| R18 | **Third-party flows disclosed:** OpenRouter and model providers, Exa, Google News, the bucket host, Google Fonts (or self-host the fonts so users' IPs do not go to Google) | pages | review |
| R19 | **No user content in Telegram** | telegram-monitor | log review |
| R20 | **Isolation canary:** a scheduled two-user check, which stops new external sign-ins on failure | edge-bff-worker | T14 |

### 5.2 Tests (PROPOSED; IT1-IT10 from identity §7, IT11-IT14 added)

| # | Test |
|---|---|
| IT1 | Route-table walk derived from `app.routes`. B calls every route with A's ids (conversation, run, side chat, pin, bookmark, export, backtest job and result, saved screen, My metric, watchlist). B gets the answer a random id gets, and A's state is unchanged |
| IT2 | B's lists and searches (`q=` with A's question text) never show A's ids |
| IT3 | Every write route except sign-in returns 403 without `X-CSRF-Token` (with a valid `Origin`) |
| IT4 | Disable ends the session at the next request and on the open SSE stream within one poll; a reset revokes every session; A's CSRF token fails with B's session; the session cap holds |
| IT5 | Failures on login A do not block login B; per-IP limits only after the spoofing probe |
| IT6 | Orc: owner A cannot read, stop, branch, export or see progress of B (existing tests) plus the manual steps; a missing owner is refused; the test key is refused for a real owner |
| IT7 | Terminal: with owner A, quotas and `access_log` land on A's subscriber; an unknown owner gets 401; the header is ignored without the gateway key; workers count on their service rows |
| IT8 | Backtest and Screener: latest-wins never cancels another owner's or another page's call; a light owner is not starved behind 3 heavy jobs |
| IT9 | Browser: after sign-out and sign-in as B, nothing of A's remains in session or local storage |
| IT10 | Load fairness: with A looping heavy requests, B's p95 stays within the stated bound per tab |
| IT11 | Audit: every auth and admin event is recorded; a log scan finds no token, verifier, login, email or raw owner key |
| IT12 | Budgets: each refusal (`AI_BUDGET_EXCEEDED`, `BACKTEST_DAILY_LIMIT`, `SCREENER_CPU_BUDGET`) has the four parts; the remaining budget is shown before acting; the ledger matches Orc's cost within one run |
| IT13 | Exposure: an external tester cannot obtain an `off` source through Terminal files, Screener preview bars, AI tables or XLSX input sheets, or any export |
| IT14 | Deletion: the account purge removes the user's rows in `edge_bff`, Orc conversations, outputs and bucket objects, and the terminal subscriber; tagged audit rows follow MU18 |

---

## 6. Data terms: what must be settled before going external

FACT (data_terms §6): neither market source has a licence recorded anywhere in the repository. The documents say nothing on
IDX or KSEI, the sector classification, logos, web results or model output. No legal conclusion is drawn here. Every row is
UNKNOWN until the user and the provider answer it. The questions are listed in data_terms §4, and the default proposed below
lasts until each one is answered.

| Source | Where it reaches external users | Raw at source grain? | Repository evidence | Default for external roles until answered (PROPOSED) |
|---|---|---|---|---|
| IDX stock and IHSG end-of-day prices (TradingView websocket, anonymous token) | every tab | yes: Terminal files, Screener 260-bar preview, AI tables and input sheets up to 200,000 rows | "tidak memberi izin tertulis" (`EXEC.md:8190-8193`); IDX as data owner: none | `off` (in practice no external launch: every tab rests on prices) |
| Bond series (`TVC:`) | Monitor | through the AI | none | `off` |
| Market cap and free float (EXEC-MCAP, not built) | — | — | licence risk named | not built for externals |
| Broker summary (Stockbit, one personal JWT) | Terminal (per broker and day), Monitor, Backtest flow, Screener flow (Phase 2) | yes | none | `off` |
| Corporate actions | Terminal events, Monitor | yes | none | `off` |
| Insider and major-holder movements, with holder names (IDX and KSEI origin; 2,212 and 3,066 names) | Terminal events, Monitor | yes, including third parties' personal data | none | `off` |
| Sector and industry classification | Screener, Terminal, Monitor | yes | source unknown | `off`, or the user's own classification |
| Logos (Stockbit PNG, TradingView SVG) | every page | yes | "belum diperiksa" (`FUTURE_PLAN.md:868-870`) | `off` (ticker text instead) |
| Web results and news (Exa through OpenRouter, Google News RSS "unofficial", direct fetch without robots.txt) | Monitor | quotes | `apps/market-web-governor/README.md:160` | `off` for externals, or links only |
| Model output (OpenRouter and providers) | Monitor | — | none | per MU6 and MU17 |
| Lightweight Charts attribution (`attributionLogo:false` everywhere) | Terminal, Backtest, Screener | — | Apache-2.0 header in the bundle | add attribution as MU2 settles (how: UNKNOWN) |
| Derived values (Feature 01-06, indicators, backtests, flow FL01-FL18) | every tab | derived | follow their sources | follow the source row |

Also to settle with the user before going external: whether EDGE is paid (MU4); the privacy notice, the terms and the
applicable law (for Indonesian users the Personal Data Protection Law, UU No. 27/2022, is for the user and counsel to
confirm; MU19); retention and deletion (MU18); the model-provider data policy (MU17); the manual agent (MU15).

---

## 7. Decisions for the user (MU1-MU26)

"Needed by" names the phase the decision blocks.

| # | Decision | Options | Recommendation | Impact | Needed by |
|---|---|---|---|---|---|
| MU1 | Approve this plan as the EDGE-MULTIUSER plan, and give a go for Phase 1 only | (a) approve, go Phase 1; (b) approve, no go yet; (c) change the plan | (a): Phase 1 is single-owner hardening that is useful even if launch slips, and it closes M259 | Moves the PLAN.md item from "rencana belum disusun" to a plan; nothing else starts | now |
| MU2 | Data terms per source (section 6) | (a) no external user until each source has a written answer from the provider (and IDX/KSEI where they own the data); (b) a closed beta with only the sources the user has confirmed; (c) launch without answers | (a). The plan builds the exposure switch meanwhile, so each answer becomes configuration | Decides whether and when G1 passes; may require a licensed data vendor (cost UNKNOWN) | Phase 6 (start now) |
| MU3 | Exposure default for unanswered sources | (a) `off` for external roles; (b) derived-only; (c) raw | (a) | Sets MP-22's table | Phase 5 |
| MU4 | Is EDGE paid? | (a) free closed beta; (b) paid; (c) free, then paid | State the intent now. Payments are outside this plan (a separate item) | Changes every data-terms question, tiers and invoicing | Phase 2 design |
| MU5 | Expected numbers (P29 numbers) | daily users, users at once, AI turns per user per day, backtests per user per day, for 3 and 12 months | Give bands (for example 10 / 50 / 200) so triggers and cost (section 4.5) are set | Sizes Phases 4 and 6 | Phase 4 |
| MU6 | Monitor (AI chat) for external users | (a) closed to externals at first (hidden for role `user`); (b) open with a daily USD cap per user (amount), and a sandbox sessions-per-answer limit for multi-user (`PY_SANDBOX_MAX_SESSIONS_PER_REQUEST`, an EXEC-V decision); (c) open, unlimited | (b) with an initial cap of USD 0.50 a day (about 16 turns), if MU2 clears the sources the AI reads. Otherwise (a). Never (c) | 98% of marginal cost; worst case USD 10.5 per user-month at that cap | Phase 4 |
| MU7 | Sign-up model | (a) invitation by the admin only; (b) self sign-up with approval; (c) open | (a) | Scope of MP-01 | Phase 2 |
| MU8 | Identity provider | (a) own accounts; (b) external OIDC now; (c) own now, OIDC later on the same table | (c) | Vendor, cost (UNKNOWN), redirect URIs | Phase 2 |
| MU9 | Login identifier and email delivery | (a) email as login, links handed over by the admin at first; (b) an email provider now (which) | (a); (b) before self sign-up | Invite and reset UX | Phase 2 |
| MU10 | MFA | (a) TOTP required for admin, optional for users; (b) required for all; (c) none | (a) | Admin takeover risk | Phase 2 |
| MU11 | Roles and tiers | (a) `user`, `admin`, `tester` with one quota set plus per-owner overrides; (b) tiers now | (a); tiers with MU4 | Shape of `user_limits` | Phase 2 |
| MU12 | Session policy | lifetime, idle timeout, devices per user | Keep the 24 h absolute lifetime, add an 8 h idle timeout, at most 3 sessions per user | Shared-device risk against convenience | Phase 2 |
| MU13 | Existing history | (a) `edge-private` becomes user #1 (admin), unchanged; (b) start fresh | (a) | No data rewrite. The 30-day conversation expiry keeps running (Appendix A item 10) | Phase 2 |
| MU14 | Models offered per role | (a) the same four EDGE choices for all, manual hidden for non-admins; (b) a narrower list for externals | (a). Changing the offered list needs approval (AGENTS.md) | Cost per turn and UX | Phase 4 |
| MU15 | Manual agent with external users | (a) admin-only and owner-scoped, off by default outside troubleshooting; (b) off whenever external users exist; (c) as today | (a). It sends a user's conversation to the operator's session, so state this in the privacy notice | A leak path, and privacy | Phase 1 |
| MU16 | Initial per-user quotas per tab | Terminal tickers per hour and day, MB per day; Backtest jobs per day; Screener CPU per minute; exports per day | Start from today's terminal defaults (30 tickers/h, 150/day, 300 MB/day) after "files I have", and state whether an added asset counts as a ticker (a chart with 2 assets is 3 tickers); Backtest 1 running + 3 queued and 200 jobs/day; Screener per 6d with P33; review from the ledger after two weeks | UX against cost and data-terms bounds | Phase 3/4 |
| MU17 | Model-provider data policy for prompts | (a) keep default routing; (b) require OpenRouter's no-logging/no-training option for external users (a provider change) | Decide with MU19; if (b), measure on DeepSeek with a small golden test first | Privacy against latency and price | Phase 5 |
| MU18 | Retention and deletion | retention of `jobs.input`, conversation UI, backtests and trials, screens; conversations (30 days today); `AI_research_run_audit` and the web stores: (a) tag with the owner and purge on deletion, (b) keep and disclose, (c) store no question text for externals | 90 days for `jobs.input` and the UI lists of role `user`, 30 days for conversations, (a) for audit | Privacy and storage | Phase 5 |
| MU19 | Privacy notice, terms and applicable law | who drafts; legal review; the language(s) | The user and counsel draft; the plan supplies the factual inventory (data_terms §5) | Gate G11 | Phase 5 |
| MU20 | Environment for external users | (a) dev with release discipline for a closed beta, TEMPORARY with an end date; (b) a production environment for the user-facing tier (how market data is shared across environments is UNKNOWN); (c) a full duplicate, including the crons | (a) for a closed beta of at most about 10 invited users, then (b) before an open or paid launch. Not (c): it doubles the TradingView and Stockbit pulls | +USD 30-35 a month for (b) | Phase 6 |
| MU21 | Availability and backups | (a) the current single instance; (b) PITR or verified backups; (c) HA | (b) before the first external user's data is stored; (c) on a stated target | Data loss risk; cost UNKNOWN | Phase 6 |
| MU22 | Custom domain before external users | (a) yes; (b) stay on `up.railway.app` | (a): it sets the cookie prefix, CSP, origins and future identity-provider redirects once | Cost UNKNOWN (small) | Phase 6 |
| MU23 | terminal-api direct sign-in | (a) keep for administrator-managed subscribers; (b) close once everyone comes through EDGE | (b), after checking that no live subscriber besides the gateway uses it (pgweb cannot read `terminal`: UNKNOWN) | Attack surface | Phase 3 |
| MU24 | Region | (a) keep `sfo`; (b) move nearer Indonesia | (a) until timings are measured from Indonesia (6c L-U4) | Latency; a 51 GB move | can follow |
| MU25 | Telegram | (a) operator only; (b) per-user alerts later | (a) | No user content in Telegram | can follow |
| MU26 | Load test on dev with synthetic owners | approve the scenarios and an AI spend of about USD 5 per run | Approve as part of Phase 6, with a mini version in Phase 4 | Sets the triggers and the cost model | Phase 4/6 |

---

## 8. Risks

| # | Risk | Effect | Mitigation | Residual |
|---|---|---|---|---|
| RK1 | Data terms deny raw display, or require a paid licence | No external launch, or a vendor cost and a re-architecture of sources | MU2 now; the exposure switch (MP-22) turns answers into configuration | High until answered |
| RK2 | AI cost runaway on one shared key | The bill, or AI stopping for everyone | MP-12 cap, MP-17 alert, T3, test-owner budgets | Low with a cap |
| RK3 | A forgotten route leaks another user's data | Privacy breach | Route-walk tests (IT1) derived from `app.routes`, the canary (T14), optional row-level security | Low |
| RK4 | External users on dev hit work-in-progress deploys or test load | Outages and odd results | MU20 discipline, then production; deploys outside market hours | Medium in a beta |
| RK5 | Single Postgres without PITR or HA | Loss of user data | MU21 (b) before the first external user | Medium until enabled |
| RK6 | Orc and the sandbox are single replicas (in-memory state, volume) | A Monitor outage on crash or deploy | Vertical first; shards (MP-20); Orc state in Postgres on a trigger | Medium |
| RK7 | Railway's `X-Forwarded-For` handling is unknown | Spoofable or global per-IP limits | Per-login limits first; the probe before per-IP | Low |
| RK8 | Credential stuffing on user accounts | Account takeover | The throttle, T12, admin TOTP, optional user MFA (MU10) | Medium |
| RK9 | Quota values break Terminal UX | Users blocked while browsing | "Files I have", ticker-based quotas, MU16 review from the ledger | Low |
| RK10 | Sessions per answer are higher than assumed (one answer may hold 4 sandbox sessions) | Monitor concurrency far below 7 | Measure first; a per-answer limit for multi-user (MU6); shards | Medium |
| RK11 | Merge conflicts with the Screener branch (`screener.py`, `main.py`) | Delay or regressions | Phase 2 after Screener Phase 1 merges; the owner is already a parameter in the store layer | Low |
| RK12 | The cost model comes from dev testing (about 23 runs a day of one user) | Real use differs | MP-28 calibration, T11 weekly review | Medium |
| RK13 | Third-party processing of prompts (providers; the manual agent sends prompts to the operator's session) | Privacy complaint | MU15, MU17, notices (MP-24) | Medium until decided |
| RK14 | The Stockbit data path rests on one personal token | Data stops for all users if it is revoked; a terms risk | MU2; a licensed source if required | High (also RK1) |
| RK15 | Config drift (`.railway/railway.ts` misses live variables) | A `config pull` surprise or a wrong deploy | Settle the drift in Phase 1 | Low |
| RK16 | Destructive purge or deletion bugs | Data loss | DRYRUN, audited purges, IT14, backups first (MU21) | Low |
| RK17 | Parallel sessions write the same record files and code on `main` while this plan's phases run on long branches. FACT: `baa0903` (2026-10-28 16:52 UTC) emptied `EXEC.md` (8,509 lines deleted) and `verification/terminal_api/FRONTEND_ARCHITECTURE.md`, and `4f17e4d` restored them 3 minutes later (GitHub commit stats) | Lost records or merge regressions in `main.py`, `live.ts`, `EXEC.md` | Rebase onto `main` right before each phase's push. Before committing, check `git diff --stat`: no record file may lose lines it did not mean to remove. One phase at a time on the shared files | Low to medium |

---

## Appendix A. Corrections and additions to the sibling notes and to 6d

1. **The AI queue is already fair across owners.** The partial unique index allows one active job per owner
   (`20261008_002:46-48`), and submit refuses a second active job (`store.py:85-87`). So the FIFO claim holds at most one
   job per owner. The capacity note's "round-robin claim" is needed for the Backtest, not for the AI. For the AI, only the
   K slots are needed (MP-13).
2. **One answer may hold all 4 sandbox sessions.** `PY_SANDBOX_MAX_SESSIONS_PER_REQUEST` is not set on dev and defaults to
   `PY_SANDBOX_MAX_SESSIONS` (4) (`config.py:288-289`; Railway variable names **[re-read]**). The "about 7 users per sandbox"
   figure holds only if most answers use one session; measure it (RK10, MU6).
3. **CSP: hashes, not nonces.** Identity R7 proposed a nonce. A nonce changes the shell's bytes on every response and defeats
   P26's `ETag`/`304`. Two inline blocks make hashes simple (MP-06).
4. **The injection surface is smaller than implied.** The shell builds answers with `createElement`/`textContent`
   ("never innerHTML", `index.html:11807`). The strict CSP is defence in depth, not a fix for a known hole.
5. **The pool rule with a worker service is N ≤ 2 web replicas, not 3** (N × 6 + 6 ≤ 20) until the role limit rises.
6. **User #1 is seeded at edge-bff start** from the environment values the service already holds, instead of a one-off job
   that reads the verifier elsewhere.
7. **`Postgres-E8GM` is a second database** (web-governor stores; **[re-read]** in `railway status`). It is in scope for
   backups, retention, owner tagging and deletion, and was not named separately in the cost table.
8. **The sandbox's code default is 2 sessions** (cap 4). Dev sets 4. The K rule must read the live value.
9. **Terminal assets multiply grants per view** (new on `main` after the sibling notes were written). The capacity note's
   "1 grant per ticker open" and "about 12 ticker opens an hour" assume a single ticker. A chart with 2 assets asks
   `/bundle` up to 5 times, and with packs it asks for about 13 files. This makes MP-11 ("files I have", and quotas that
   count tickers and bytes) more pressing before external Terminal users (`live.ts` at `15ec418`).
10. **The owner counts dropped between two reads on the same day** (534/29 to 519/14). The 30-day conversation expiry
    is running. The "92 conversations of `edge-private`" that MU13 preserves is also subject to it. FACT (pgweb, 19:10
    UTC): their `expires_at` runs from 2026-11-07 to 2026-11-25, and 21 of them expire within 14 days. MU13 keeps the
    owner key and whatever history remains; it does not stop the expiry. Changing the expiry is MU18.

## Appendix B. What this note re-read (2026-10-28, read-only)

- **Code**
  - `apps/edge-bff/app/worker.py:28-80`, `store.py:70-98, 155-169`, `main.py:185-200, 262-272, 436-465, 580-593`, `backtest.py:510-530`, `config.py:23, 65`.
  - Migration `20261008_002:44-50`.
  - `apps/market-ai-orc/app/manual_agent.py:105-120`, `stop.py:5-10`, `main.py:694-695`.
  - `apps/market-python-sandbox/app/config.py:283-296`, `sessions.py:700-716`.
  - `apps/terminal-api/app/main.py:170-182`.
  - `apps/edge-bff/static/index.html`: inline script sizes and lines, no `on…=` handlers, the `innerHTML` comment at 11807.
- **Live database** (pgweb, read-only): `pg_roles.rolconnlimit`; `pg_settings` (`max_connections`, `shared_buffers`, `work_mem`); the `edge_bff` relations (6, no Screener tables); `AI_conversation` 534 rows, 29 owners (at 15:50 UTC); `Table_Catalog` has no `edge_bff` or `terminal` rows.
- **Railway** (`@railway/cli@5.71.0`): `status --json` (environment `dev` only; edge-bff `32a25029` SUCCESS at `f265ae4` (at 15:50 UTC, since superseded), plan `pro`; no `screener-worker`; `Postgres-E8GM` present); the `market-python-sandbox` variable names (`PY_SANDBOX_*` keys only; no values printed). The temporary status file was deleted after reading.
- **Git:** branch HEAD `0a20886`, `origin/main` `2e7f7fd` (local ref). No change was made.
- **Re-check at about 19:10 UTC** (read-only):
  - Railway `status --json`: edge-bff `7b05b9fd` SUCCESS at `baa0903`; still only `dev`; still no `screener-worker`.
  - Railway variable names (keys only) of edge-bff and market-python-sandbox. `EDGE_INITIAL_PASSWORD` is present;
    `PY_SANDBOX_MAX_SESSIONS_PER_REQUEST` is absent.
  - GitHub API: `main` commits since 2026-10-28 00:00 UTC with their file lists; `terminal/src/data/live.ts` at
    `15ec418`.
  - pgweb: `AI_conversation` counts per owner and its `expires_at` range; `edge_bff` relations and `relrowsecurity`;
    `rolconnlimit`; `pg_stat_activity` per role (pgweb 2, edge_bff_login 2, terminal_api_login 2, postgres 1). `edge_bff.jobs` itself
    is not readable by pgweb (permission denied), so queue depth was not read.
  - Spot-checked against the branch: `edge-bff main.py:579-593`, `worker.py:30-46`, `manual_agent.py:108-118`, migration
    `20261008_002:44-50`, `market-python-sandbox config.py:284-297`.

## Appendix C. Records to update when executing (by phase)

- **Every phase:** `ERRORS_AND_SOLUTIONS.md` (new entries and status updates), `RAILWAY_CHANGELOG.md` (names, actions, deployment ids), `DATABASE_SCHEMA.md` and `DATABASE_CHANGELOG.md` for each migration, `PLAN.md`/`EXEC.md` (approval with the user's words; move the item to `EXEC.md` on go; remove it when done).
- **Phase 1 and 2:** `apps/edge-bff/README.md` (identity, limiter, CSP), `apps/market-ai-orc/README.md` (owner trust, manual agent), `PROJECT_CONTEXT.md` (owner model).
- **Phase 3:** `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md`, the terminal-api README, `verification/terminal_api/` (quota job).
- **Phase 4:** `.railway/railway.ts` (the new service and variables), `BACKTEST_END_TO_END.md` (claim rule), the Screener API contract (budget in `limits[]`).
- **Phase 5:** `AI_MODELS.md` only if MU17 (b) is approved; `scripts/provision_market_sql_governor_login.py` and its record; the privacy and terms pages.
- **Not affected unless scope changes:** `AI_TOOLS.md`, `AI_ROUTER.md`, `prompts/SYSTEM_PROMPT_HISTORY.md` (no tool, router or prompt change is planned; their drift tests confirm).
