# EDGE access tiers: architecture findings and implementation plan (2026-11-16, read-only; not executed)

Source: ten read-only inspections run from `INSPECTION_PROMPTS.md` (Opus 5.5, medium) on branch
`claude/pensive-feynman-4ahfe3`, merged and spot-checked by the main agent. Every key claim below was re-read in the code
on 2026-11-16 (cited file:line); live facts come from the read-only jobs of 2026-11-11 (`PLAN.md` EDGE-MULTIUSER) and
`railway variables` names. User decisions: `PLAN.md` EDGE-MULTIUSER (2026-11-11 and 2026-11-16).

## 1. The one structural fact

EDGE has a multi-owner data model behind a single-owner application.
- Every `edge_bff` table already filters by `owner_key`, except `backtest_results`. That table is reached only after an
  owner-checked parent (`apps/edge-bff/app/backtest.py:607-623`, `:1343-1347`).
- The session check accepts only the environment owner and returns a token, not a user (`apps/edge-bff/app/main.py:274-279`).
- Every router binds `self.settings.owner` once at start-up: `backtest.py:1249`, `screener.py:916` (and `ask()`
  `:648`), `layouts.py:215`, `presets.py:189`, `drawings.py:161`, plus 41 uses in `main.py`.

Adding users is therefore a change of structure (a per-request principal), not an extra check.

## 2. Where each kind of content can be gated (smallest unit the server can refuse today)

| Tab | Content | Server unit today | Enforcement point |
|---|---|---|---|
| All | tab pages | none (page shells and the `*-app/` bundles are public and hold no user data, `main.py:310-407`) | display only; data routes are the gate |
| Terminal | price, broker/flow, events, intraday per timeframe, yield, references, logos | one object per dataset × ticker × year, or pack/ref name (`apps/terminal-publisher/publisher.py:62-112`); the selection `chosen` is built before `grant()` (`apps/terminal-api/app/main.py:536-551`) | terminal-api grant, once it knows the user (T2) |
| Terminal | single indicators, panels, sections | none: computed in the browser from granted rows; formulas ship in the public bundle | only through the data they read, or server-side compute (design change) |
| Terminal | corporate actions vs insider; Foreign/Domestic, board, frequency columns; broker classification | none: mixed in one file (`terminal/src/data/live.ts:401-419`, `worker.ts:94,125`) | needs a publisher file split |
| Terminal | history depth | coarse: price is one pack with every year (`publisher.py:83-84`) | packs per depth tier, or no packs for capped plans |
| Backtest | catalog, `/signals`, validate, submit, result `core`, `events:<T>`, trials | route; result part (`backtest.py:328-376`) | edge-bff route + worker `context` limits (`apps/backtest-worker/src/validate.ts:172`) + result sections served per viewer |
| Backtest | single-stock preview | none: computed in the browser from Terminal files | through the Terminal file gate only |
| Screener | metrics, indicators, flow params, options, row count, counts, preview | one id or parameter in the normalized definition (normalize runs before the caches) | worker check right after `normalize`, plus an answer-shape id in the result-cache key (`apps/screener-worker/src/run.ts:138-139`) |
| Monitor | models, reasoning, mode, lane, exports, runs and USD per day | model id + level (`apps/market-ai-orc/app/model_choices.py:57-59`); mode only after routing (`market-ai-orc/app/main.py:613-628`) | edge-bff before submit + Orc's allowed set; usage ledger |
| Saved items | layouts, presets, drawings, screens, watchlist | row, by owner | store query; caps become plan limits (`layouts.py:37`, `presets.py:36`, `drawings.py:32-33`, `screener.py:77-78`) |

## 3. Defects and risks found (recorded in `ERRORS_AND_SOLUTIONS.md` M423-M430 where new)

1. Cross-owner exposure of the manual agent (`market-ai-orc/app/manual_agent.py:112-116`; `edge-bff/app/main.py:598-610`). M429.
2. Orc identity:
   - any holder of the shared key may name any owner; a missing header becomes `default`
     (`conversations.py:97-99`);
   - progress of a run without an owner is readable by every caller. M430.
3. terminal-api has a public domain (`terminal-api-dev.up.railway.app`, `RAILWAY_PUBLIC_DOMAIN` set) and identifies the
   gateway key with no source check (`terminal-api/app/main.py:191-194`).
   - Once the owner header is trusted (T2), the key alone names any user.
   - The `AccountCache` key is `(kind, name/email/token)` (`accounts.py:33-35`), so per-owner identity must enter it. M425.
4. All EDGE users share one terminal-api account:
   - quotas are overridden to 1e9 (TEMPORARY, `verification/terminal_api/jobs/quota_unlimited_edge_owner.sql`);
   - one advisory lock and one audit trail for everyone.
5. Browser storage:
   - unsynced drawings move into the next signed-in account (`terminal/src/data/drawingsApi.ts:50-69,122`). M423;
   - account data survives sign-out (`static/edge-client.js:11,138`; `ml.*`, `scr.last`, `edge-model-choice`,
     `edge-side-attach:*`, IndexedDB `terminal-files`). M428.
6. Every front-end treats any 403 as a CSRF or session failure:
   - `layoutsApi.ts:50` retries;
   - `screener/src/api/live.ts:36,69` and `backtest/src/api/live.ts:51` drop the session;
   - FastAPI refusals come out as `{"detail"}` (`main.py:277-283`).

   A plan refusal would be misread. M426.
7. The public Terminal bundle embeds a real BBCA broker summary of 2023-12-18 (`terminal/src/data/fixtureConstants.ts:1-3`). M424.
8. No CI runs any test (`.github/workflows/` holds only `database-schema-docs.yml`).
   `verification/terminal_api/terminal_look/look_check11.mjs:8-10` hard-codes another session's scratchpad. M427.
9. Single-process state:
   - in edge-bff: the sign-in limiter `main.py:457-466`, the model cache `:612`, backtest previews, and the screener
     `flight`/`pages`;
   - in Orc: stop, progress, manual steps;
   - in the screener worker: the owner budget per replica.
10. Capacity:
    - one AI run at a time for everyone (`worker.py:32-50`, `store.py:158-169`, up to 3,900 s);
    - one backtest job slot, plain FIFO (`backtest.py:638-648`; correction to the 2026-10-28 audit, which said "rotation");
    - one shared preview FIFO in the worker.
11. A payment webhook would be refused by the Origin check (`main.py:246-249`).
12. The Monitor's model list is one global cache (`main.py:612-628`).

## 4. Target design

- **Principal.** `session()` and `write()` return
  `Principal(user_id, owner_key, role, plan, status, expires_at, mfa_ok, capabilities, limits, version)`.
  - It is read in one query from sessions, users, the active subscription and the plan's capabilities.
  - An expired plan reads as the fallback plan at request time, so no cron is needed.
  - `settings.owner`, `settings.login` and `settings.password_verifier` are retired after the seed.
- **Catalog as data** (schema `edge_bff`):
  - `plans`;
  - `capabilities` (name, kind flag/limit, unit, means, display name; same shape as `terminal.quota`);
  - `plan_capabilities` (versioned) and per-user overrides;
  - `subscriptions` (status, starts_at, expires_at, provider, provider_ref; one active per user);
  - `usage_counters`.

  Code names capabilities only; a test forbids plan names in code.
- **One check.** `need("<capability>", write=…)` as a route dependency, and `p.can()` / `p.limit()` inside handlers.
  - Refusals use `{"error":{"code","message","details":{"capability"}}}`, where code is `CAPABILITY_REQUIRED`,
    `PLAN_EXPIRED`, `LIMIT_REACHED`, `MFA_REQUIRED` or `UNAUTHENTICATED`.
  - Another user's item answers 404.
  - The gate rule of AGENTS.md "Gates and evidence" (rule, how to pass, examples, message) applies to every new code.
- **Downstream.**
  - edge-bff sends the owner and the resolved capability set to:
    - terminal-api (T2: `x-terminal-proxy-owner` mapped to `terminal.subscriber.edge_owner_key`, owner in the cache
      credential, capability filter on `chosen`, a locked entry returned without URL or sha);
    - backtest-worker and screener-worker (`context.capabilities`/`limits`, the worker takes `min(ceiling, context)`);
    - Orc (allowed models, modes and lane).
  - Orc refuses a missing owner. The test runner gets its own key, limited to test owners.
- **Accounts.**
  - Tables: `users` (opaque immutable `owner_key` `u_` + 24 hex; `edge-private` seeded as user #1, role admin; reserved
    `default`, `golden-*`, `test-*`, `someone-else`), `identities` (provider + subject; password now, Google later),
    `email_codes` (hash, purpose, 5-minute expiry, attempt cap, one live code), `auth_throttle` (per email hash, IP hash
    and both; Postgres, works with replicas), `sessions` (+ `user_id`, `last_seen_at`, `mfa_passed_at`, idle timeout),
    `mfa_totp` + recovery codes, and `admin_audit` (written in the same transaction as the change).
  - Routes:
    - `POST /auth/register` always answers 202, whether or not the email exists;
    - `/register/verify` signs in;
    - `/code/resend`;
    - `/password/forgot` always answers 202;
    - `/password/reset` revokes every session and sends the user to sign-in;
    - `/mfa/enroll` and `/mfa/verify`.
- **Email.**
  - An `email_outbox` (idempotency key, purpose, status, attempts, lease, `next_at`) with its own loop beside the backtest
    loop, behind its own switch.
  - Resend over HTTPS with `Idempotency-Key`; a code email past its 5 minutes is never sent; the payload is cleared once
    sent.
  - Bounces and complaints arrive through a signed webhook into `email_suppression`.
  - Pattern: `Telegram_Notification_Log` / `claim_delivery`.
- **Admin.**
  - An `/admin` page and `/api/v1/admin/*`, behind `admin.*` capabilities plus fresh MFA.
  - The page lists users, last sign-in, plan, status, expiry and usage.
  - Actions: disable (revokes sessions and the terminal subscriber), change plan, extend with a written reason; each is
    audited.
- **Payments (plug-in later).**
  - Adapter interface: `create_checkout(order, user, return_urls)`, `verify_webhook(headers, raw)` and
    `fetch_status(order_id)`; the provider is chosen by a variable.
  - Webhook route `POST /api/v1/hooks/payments/{provider}`, exempt from the Origin check by exact prefix only. The
    signature is checked over the raw body, which is already buffered at `main.py:261`.
  - `payment_events` are UNIQUE (provider, event id); the order amount and currency must match.
  - Subscription state machine: pending, active, past_due, cancelled, expired, refunded. An event older than the last
    applied one is ignored.
  - A reconciliation loop fetches the status of pending orders.
  - `/auth/session` returns `next: verify|mfa|pay|null`. The pay, account and sign-out pages stay open without a plan.
- **Front-end.**
  - One shared session module for the shell and the three apps (they already share code by relative import; Dockerfile
    stages copy siblings).
  - Entitlement version header plus `BroadcastChannel` so a plan change reaches every open frame.
  - A storage registry (`browser` vs `user` keys) cleared on sign-out or a change of user; the drawings merge stamped per
    user or retired.
  - `access` wording in `edge-labels.js`, loaded by the apps.
  - Locked items show a lock or teaser, never data.

## 5. Phases (each needs the user's "go"; flag `EDGE_MULTIUSER` off until Phase 6, so the current user keeps working)

| Phase | Content | Visible change |
|---|---|---|
| 0. Hardening | manual agent admin-only and owner-scoped with CSRF (M259, M429); Orc refuses a missing owner and the test runner gets its own key (Railway variable, needs approval); terminal-api refuses the gateway key on its public domain or the domain is removed (M425); sign-in throttle in Postgres; drawings fix and sign-out clean-up (M423, M428); 403 contract in the four front-ends (M426); fixture data replaced (M424); a CI workflow for pytest and vitest and a portable look check (M427) | none |
| 1. Accounts | users, identities, email codes, throttle, sessions, MFA, outbox; principal on every route; registration, code, forgot and reset pages; Resend sender; admin MFA; user #1 seeded | sign-up (behind the flag) |
| 2. Catalog | plans, capabilities, subscriptions, usage; `need()`; entitlements in `/auth/session`; shared front-end module; locked wording; route-table test | none for the admin (all capabilities) |
| 3. Gates per tab | Terminal T2 and the grant filter, per-user quotas; Backtest worker context and result sections; Screener worker check and cache key; Monitor allowed set and usage ledger | locked items for non-admin users |
| 4. Admin dashboard | users, sign-ins, plans, expiry, usage, actions with audit | admin page |
| 5. Payments | paywall flow, adapter, webhook, payment tables, state machine, reconciliation, test provider | pay page |
| 6. Launch | custom domain and `EDGE_PUBLIC_ORIGIN`, Privacy and Terms pages, data terms per source (MU2), two-tester run, flag on; fairness slots after measurement | public sign-up |

## 6. Tests that must pass (added with the phase that needs them)

1. A route-table walk: every route is public by list or carries `need()`, and every write has CSRF (fails today on M259).
2. Two-user isolation over every owned kind; the other user's item gives 404.
3. A free principal calling paid routes directly, including the second path to the same content:
   - `/events` and `/signals` beside `/result`;
   - `history/broker` and `files` beside `/bundle`;
   - a screener definition naming a paid metric only in an extra column or a disabled condition.
4. Expiry one second ago refuses with no cron; a downgrade mid-session refuses the next call; a catalog row change
   changes access with no deploy.
5. terminal-api: owners A and B get separate subscribers, quotas and cache entries; the gateway key on the public domain
   is refused.
6. Auth:
   - identical answers for existing and new emails;
   - six failures across two app copies give 429;
   - a code is refused after 5 minutes and after 5 tries;
   - admin without MFA gets 403.
7. Email: a 500 then 200 from Resend sends one email with one idempotency key; the loop sends while a long AI run holds
   the job worker.
8. Payments: duplicate webhook gives one change; bad signature or wrong amount gives no change; a missed webhook is
   reconciled.
9. Browser: user B on A's browser inherits none of A's drawings, settings or cached screener result.
