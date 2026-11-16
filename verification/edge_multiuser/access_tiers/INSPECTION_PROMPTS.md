# EDGE access tiers: inspection prompts for 10 read-only sub-agents (prepared 2026-11-16, not run yet)

Purpose: give the main agent a clear picture of how the current EDGE architecture works, so it can write the
implementation plan for accounts, roles and plans (admin, free, paid), gating per tab and per piece of content inside a
tab, an admin dashboard, and a payment gateway that plugs in later. Approved direction and user decisions: `PLAN.md`
EDGE-MULTIUSER. Earlier evidence: `verification/edge_multiuser/` (audit 2026-10-28) and the dependency audit of
2026-11-11 recorded in `PLAN.md`; both must be re-verified against the current code, not trusted.

Run settings: 10 agents, model Opus 5.5, reasoning effort medium (user 2026-11-16), all read-only, in parallel. The main
agent merges the ten reports into one implementation plan for the user's "go".

## Shared brief (prepended to every prompt)

```
Read-only audit of /home/user/saniti (branch claude/pensive-feynman-4ahfe3). Do not edit files, do not call Railway, do
not write to any database, do not deploy. Read AGENTS.md first.

Context: EDGE is a web app served by apps/edge-bff (FastAPI) with four tabs: Monitor (AI chat via market-ai-orc),
Terminal, Backtest and Screener (separate Vite front-ends under apps/edge-bff/{terminal,backtest,screener}, served by
edge-bff). Today it has ONE user: login, password verifier and owner ('edge-private') come from env vars
(apps/edge-bff/app/config.py); the session check only accepts settings.owner (app/main.py:274-279). Data tables in
schema edge_bff already carry owner_key.

Target (user decisions 2026-11-16): many users who self-register (email + password, code by email valid 5 minutes,
signed in directly after the code; Google sign-in later), password minimum 8 characters, MFA for admin, anyone may
register for now. Every tab is reachable by every signed-in user, but each role or plan (admin, free, paid, later more)
may see a different version of a tab AND different content inside it: for example some Terminal panels, indicators or
data sets only for paid users; the Backtest page open to all while its results are hidden for free users. After sign-in
a user without an active paid plan is sent to pay; the payment gateway is not chosen yet and must plug in later. An
admin menu gets a dashboard: registered users, last sign-in, plan/status, expiry date, and similar.

Design rule from the user: design for the class of problem, not the instance. Gating must be enforced on the server
(the API, terminal-api grants, workers), never only by hiding things in the browser. What a plan may use must be data
(a catalog of named capabilities and limits per plan, read at run time), not if-statements naming a plan or a feature.

Your report (at most about 1200 words, file:line evidence for every claim, VERIFIED = read in code or config now,
SUSPECTED = inferred):
1. How your area works today, end to end.
2. Gating points: every place where a role/plan check must sit so that content can be opened or closed per plan,
   at which layer (route, store query, terminal-api grant, worker, front-end display), and the smallest unit that can
   be gated today (whole tab, route, data set, file, field, result part).
3. What would leak or break with many users or with plans (cross-user data, paid content reachable by a free user,
   shared quotas, single-instance state, browser storage).
4. Proposed change, its layer, and what it does not cover. Say when the current structure should be changed rather
   than extended.
5. Tests that would prove the gate holds (including a case other than the obvious one).
6. Open questions for the user, each with its context in plain language.
```

## The ten prompts (each follows the shared brief)

1. **Shell, routing and page serving.** `apps/edge-bff/app/main.py` page routes (`/`, `/login`, `/monitor`, `/terminal`,
   `/backtest`, `/screener`, `/c/{id}`, the `*-app/` pages and assets), `static/index.html` router (`go()`, public
   routes, `AuthPage`, `AccountMenu`, the tab bar), how each Vite app is built, embedded and boots (its first calls,
   `/api/v1/auth/session`, the `capabilities` object at `main.py:485`). Where a plan-aware session answer (role, plan,
   capabilities, expiry, "must pay") would be read by each tab, and where registration, code entry, forgot password, a
   paywall page and an admin menu would live in the shell.
2. **edge-bff API authorization layer.** Every route (methods, `session`/`write`/none), the middleware (origin, CSRF,
   CSP, error handlers), the sign-in limiter, `security.py`, `store.py` session functions. How to introduce one
   principal (user id, owner key, role, plan, capabilities) and one capability check usable by every router
   (`backtest.py`, `screener.py`, `layouts.py`, `presets.py`, `drawings.py`), 401 vs 403 contracts and how each front-end
   reacts to them, and a route-table test that fails when a new route has no check. Include the registration, email
   code and reset routes that will be added (shape only).
3. **Terminal content inventory and front-end gating.** `apps/edge-bff/terminal/src`: every panel, indicator, overlay,
   data set and file kind the page shows (price, broker/flow, events, intraday, fixed income, xsection, references,
   logos, layouts, presets, drawings), which call or file feeds each, and the smallest unit the server can refuse. What
   the page does when a request is refused, and how a locked item would be shown (teaser, lock icon) without its data
   reaching the browser.
4. **terminal-api, terminal-publisher and the data-file path.** `apps/terminal-api`, `apps/terminal-publisher`, edge-bff
   `forward_terminal` and `TERMINAL_ROUTES`, the `terminal` schema (subscriber, quota, quota_override, usage_hour,
   access_log, session). Whether grants can be decided per data set and per plan (e.g. an allowlist of data kinds or
   tickers per plan), how an EDGE user would map to a subscriber (T2, the `x-terminal-proxy-owner` header, the account
   cache key hazard), quotas per plan, and the presigned-URL lifetime as a leak window.
5. **Backtest.** `apps/edge-bff/app/backtest.py`, `apps/backtest-worker`, `apps/edge-bff/backtest/src`,
   `BACKTEST_END_TO_END.md`, `apps/edge-bff/backtest/CONTRACT.md`. Which parts can be opened while others stay closed
   (page, catalog, preview in the browser, portfolio preview, submit, result parts `core`/`events:<T>`, trials,
   export), where a plan limit (jobs per day, tickers, horizon) and a hidden-result rule would be enforced, and what the
   browser computes itself from Terminal files (so hiding it there needs the file gate).
6. **Screener.** `apps/edge-bff/app/screener.py`, `apps/screener-worker`, `apps/edge-bff/screener/src`,
   `SCREENER_LIBRARY.md`, `SCREENER_ONBOARDING.md`. Catalog, metrics, presets, runs, counts, previews, saved items and
   watchlist: which can be limited or closed per plan, how the HMAC owner tag and the CPU budget per owner would take
   a plan, and whether shared result caches could hand paid results to a free user.
7. **Monitor and market-ai-orc.** edge-bff `client.py`, `worker.py`, the run routes, and `apps/market-ai-orc`
   (`conversations.py`, `main.py`, `model_choices.py`, `manual_agent.py`, `progress.py`, `config.py`). Where a plan
   decides models, modes (`analysis_path`, mode 4), runs per day and a cost budget; the owner trust (shared key,
   `X-Saniti-Owner`, default owner `default`, the test runner's key); the manual agent (M259); the single dispatch slot;
   and what must change before a paying user shares the queue.
8. **Database model and conventions.** `database/migrations` (edge_bff, terminal, AI tables, `APPLIED.sha256`),
   `DATABASE_SCHEMA.md`, `DATABASE_CATALOG.md`, `DATABASE_CHANGELOG.md`, roles, grants and connection limits, the
   catalog exclusions. Propose the shape (not SQL yet) of: users, identities (password, Google later), email codes,
   sign-in attempts, sessions, MFA, plans, a capability catalog per plan, subscriptions with expiry, payments and
   gateway events, usage counters, admin audit. How existing `owner_key` rows map to users, and the indexes the admin
   dashboard and the per-request check need (with the measurement rule of AGENTS.md).
9. **Admin dashboard, email and payment readiness.** What admin-like surfaces exist now (manual routes, Telegram bot,
   pgweb, monitor tables), how an admin page would read users, sign-ins, plans, expiry and usage, and how an outbound
   email sender (Resend over HTTPS, an outbox table with retries) and an inbound payment webhook (public route, signature
   check, idempotency, replay, state machine for paid/expired/refunded) would fit edge-bff and Railway. Keep the gateway
   behind an adapter so Midtrans, Xendit, Stripe or another can be plugged in; name what each would need from us.
10. **Front-end shared code, browser state, build, tests and rollout.** `static/edge-client.js`, `edge-view.js`,
    `edge-labels.js`, `preview/`, the per-app storage (`ml.*`, `scr.*`, IndexedDB `terminal-files`), sign-out clean-up,
    the test suites (`apps/edge-bff/tests`, each app's `tests`, `verification/terminal_api/terminal_look/look_check11.mjs`),
    `.railway/railway.ts` watch paths, deploy rules (M340, SUCCESS only), and the records AGENTS.md requires per change.
    How capabilities reach each app's UI consistently, how a plan change takes effect without a stale page, and the
    rollout order that keeps the current single user working throughout.

## After the run

The main agent checks the reports' key claims in the code, resolves contradictions, and writes one implementation plan
(phases, schema, routes, gating catalog, admin dashboard, payment adapter, tests, rollout) into `PLAN.md`/`EXEC.md` for
the user's "go". Nothing is built before that "go".
