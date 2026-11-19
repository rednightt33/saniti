# Beta and live: separation proposal (research workflow, 2026-11-19)

The user asked 2026-11-19: "Terkait dengan environment yang tadi sudah sempat kita discuss, apakah ini best practice, bisa research dulu dan propose ke saya kira-kira kita harus seperti apa untuk memisahkan admin environment dan live production nantinya given the current architecture." Below is the synthesis of a workflow (an architecture map, two web researches, three designs, two judges) as returned, not yet decided by the user. The full outputs are in `research.json`. EXEC.md, EXEC-MU-ACCOUNTS, "Production environment", holds the decisions.

FINAL PROPOSAL: separating the admin/beta site from the live site (EDGE, 2026-11-19)

I re-checked the load-bearing facts in the repository at HEAD f63641e1, and ran one read-only GitHub API call. I changed no files and made no Railway or database calls. The facts I re-checked:
- security.py:42-47, throttle.py:58-63, config.py:105-182, main.py:270-287, worker.py:40-56, mailer.py:1-15 and :70-95, backtest.py:640-662, auth_flows.py:400-410;
- terminal-api config.py:105-125 and main.py:340-352;
- railway.ts:1-20 and :286-300; restart_postgres.py:300-330; database-schema-docs.yml:20 and :99-106; the trigger lines of every workflow;
- ERRORS M424 and the Railway-credential entry; capacity_fairness_scale_cost.md:44-54 and :96-112; EXEC.md:15984-16035;
- a grep for terminal-api /history callers.

## 1. Direct answer

**It is not "best practice" in the full sense, but it is a recognised pattern and acceptable as a first stage, time-boxed and with guardrails.**

- **Recognised.** "One environment, two websites, a shared database and back-end" is a release channel, or "ring 0":
  - Fowler: blue-green that keeps one database and switches only the web layer (martinfowler.com/bliki/BlueGreenDeployment.html).
  - Heroku: "an admin app running the same version of code, but with different configurations" (devcenter.heroku.com/articles/pipelines).
  - Microsoft: ring 0 and progressive exposure (learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments).
- **Not full best practice.** For software that holds customer accounts, the standard is to separate customer data from development, and from the agents that change things, before separating websites. Replit's fix after an agent deleted a production database was "Development and production databases are now automatically kept separate" (fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/; docs.replit.com/features/data-and-storage/development-and-production). Railway's own guide puts the production boundary at a separate environment (railway.com/guides/isolate-staging-production).
- **What the choice protects.** It protects live users from bad website code, which is the largest single source of change: 90 edge-bff deploy sections in 30 days (RAILWAY_CHANGELOG.md, 2026-10-20 to 11-19).
- **What it does not protect.** The larger dangers to live accounts stay shared:
  - about 90 migrations in 30 days, about 15 of them on the edge_bff/terminal schemas;
  - 12 Postgres restarts;
  - out-of-memory kills at 512 MB and 1 GB (railway.ts:15-19);
  - 2 GB / 1 vCPU shared with backfills (railway.ts:20);
  - data crons and agent jobs using the owner login (RAILWAY_CHANGELOG.md:1766; scripts/onboarding/run_job.sh:6-8);
  - no backup (PITR disabled, capacity_fairness_scale_cost.md:303; MU21 open, verification/edge_multiuser/AUDIT.md:891).
  Google SRE: "a bad canary can affect the control" when they share data stores (sre.google/workbook/canarying-releases/).
- **As planned ("only the website is doubled"), it has concrete defects that must be fixed before EDGE_MULTIUSER goes on:**
  1. **The beta would swallow live users' sign-in codes.**
     - EDGE_EMAIL_ENABLED defaults to true and EDGE_EMAIL_MODE to log (config.py:124-125).
     - The sender claims any outbox row, with no site filter (mailer.py:84-86).
     - In log mode it marks the row sent and keeps the code readable (mailer.py:9-11).
  2. **Beta code would run live users' backtests.** The claim takes any owner's queued job (backtest.py:650-660). EDGE_WORKER_ENABLED switches the AI loop, the backtest loop and the email sender together (config.py:109; main.py:276-283). The hourly session clean-up lives inside the AI loop (worker.py:46-48).
  3. **Recent migrations would break an older live site.** Nothing guards "old code after a migration": store.ready guards only the reverse (edge-bff store.py:56-82). Examples:
     - 20261116_001: SET NOT NULL plus a new primary key on watchlist_items;
     - 20261117_002: DROP users_email_key;
     - 20261118_100: DROP subscriber_kind_check.
  4. **The workers change under the live page.** The page bundle carries its own copy of the screener and backtest cores (apps/edge-bff/Dockerfile:5-76). screener-worker deployed 23 times in 30 days, and backtest has no version check.
- **Verdict.** Accept it as Stage 1 for a closed launch with no paying users. Add the guardrails below, and commit now to a trigger for Stage 2, which moves account data off the market Postgres.
- **The judges.** Judge 1 preferred a separate production environment now (Design 2). Judge 2 preferred this guarded Stage 1 (Design 3). Summed scores: Design 3 108, Designs 1 and 2 101 each. Both judges call the user's choice acceptable only as a time-boxed first stage with guardrails.

## 2. Recommended architecture: "one environment, two release channels, guarded account data"
(Design 3, with grafts from Designs 1 and 2)

### 2.1 Topology
**Railway.** Project lucid-patience, environment `dev` only, not renamed, since the scripts use its ID (PROJECT_CONTEXT.md:9-12).

**edge-bff = the beta and admin console.**
- Keeps following `main` with Wait-for-CI (railway.ts:246-255).
- Address: edge-bff-dev.up.railway.app.
- New variables: `EDGE_SITE=beta` and `EDGE_EMAIL_ENABLED=false`.

**edge-bff-live (new).**
- Same Dockerfile, rootDirectory and start command as edge-bff.
- Source: `github("rednightt33/saniti", { branch: "live", checkSuites: true, rootDirectory: "/apps/edge-bff" })`, one replica, `--workers 1`.
  - Railway allows a trigger branch per service (docs.railway.com/guides/github-autodeploys).
  - One process is a code assumption (railway.ts:249; apps/edge-bff/README.md:576).
- Domain: the user's domain. Prefer a subdomain such as app.<domain>; an apex needs CNAME flattening or ALIAS from the DNS provider.
  - Railway needs a CNAME plus a TXT record. DNS can take up to 72 h. Behind Cloudflare, SSL must be "Full", not "Full (Strict)" (docs.railway.com/networking/domains/working-with-domains).
- Its own variables:
  - `EDGE_SITE=live`;
  - `EDGE_PUBLIC_ORIGIN=https://<domain>`. Only one origin is accepted (main.py:351), so www must redirect;
  - `EDGE_ENVIRONMENT` not dev/local;
  - `EDGE_EMAIL_MODE=resend`, `RESEND_API_KEY`, `EDGE_EMAIL_FROM`, `RESEND_WEBHOOK_SECRET`. config.py:135-138 refuses log mode only when EDGE_MULTIUSER is on outside dev/local.
- Values identical to edge-bff, as reference variables:
  - `EDGE_DATABASE_URL`: the code requires edge_bff_login (config.py:148-149). Two pools of 6 = 12 of the login's 20 connections (store.py:30; provision_edge_bff_login.py:71).
  - `EDGE_SESSION_SECRET`, `EDGE_MFA_KEY`, `EDGE_CODE_SECRET`, `TERMINAL_PROXY_KEY`, the worker keys, the Orc URL and key (see 2.5 for why the secrets stay identical).

**Shared, one copy each, as today:** Postgres, terminal-api, backtest-worker, screener-worker, the Orc stack, terminal-publisher, the terminal-display bucket, every cron, and the Telegram services.
- terminal-api accepts exactly one gateway key (terminal-api config.py:111,123; main.py:344-349). A per-site key would need a terminal-api code change, so it is not in this plan.

**Outside Railway:**
- The live origin goes into the terminal-display bucket CORS (scripts/terminal_bucket_cors.py; RAILWAY_CHANGELOG.md:6412). `set` replaces the whole list, so all three origins go in together.
- Resend's SPF/DKIM/DMARC records go on the domain, and its webhook points to the live domain at /api/v1/hooks/email/resend.
- Start DNS and Resend as soon as the domain is known.

### 2.2 Where each kind of data lives

| Data | Location | Written by | Guard |
|---|---|---|---|
| Accounts, identities, MFA, email codes, outbox, sessions, throttle, subscriptions, admin_audit | `edge_bff.*`, main Postgres | both sites; sessions tagged by `site` | nightly logical dump plus a dump before every APPLY; no ad hoc writes; expand-contract |
| Watchlists, layouts, drawings, presets, screener items | `edge_bff.*` | both sites | same |
| Backtest jobs, results, trials | `edge_bff.backtest_*` | the site that created the job (`site` column) | claims filtered by site |
| AI jobs and conversations | `edge_bff.jobs`, `public."AI_conversation*"` | beta only at launch (AI is admin-only, D1; CONTRACT.md:397) | in the dump |
| Terminal tiers, quotas, usage, access logs, owner rows | `terminal.*` | terminal-api (shared) | in the dump; expand-contract |
| Plan catalog rows (plans, plan_capabilities, overrides) | `edge_bff.*` | admin | they are live configuration; change only with the user's go |
| Market data | `public.*` → terminal-publisher → terminal-display bucket → terminal-api presigned URLs → both sites | data jobs, as today | one truth: a bad publication reaches both sites at once; existing reader checks; manual republish (AGENTS.md, Postgres memory step 4) |

- No page or worker calls terminal-api `/history`. A grep of apps/** .ts/.js for `history/price|broker` finds nothing (2026-11-19). So migrations on Price_Stock_Indonesia_IDX and Feature_05 are not live-facing in practice.
- Live personal data never goes into chat, logs or dev files. Diagnosis of user data uses counts only (graft from Design 2).

### 2.3 Site roles and loop owners (code change: per-loop switches replace the all-or-nothing EDGE_WORKER_ENABLED)

| Loop / feature | live | beta |
|---|---|---|
| Backtest loop | claims `site='live'` | claims `site='beta'` |
| AI job loop | off (no AI on live) | on |
| Email sender | on, the only Resend sender | off (`EDGE_EMAIL_ENABLED=false`) |
| Housekeeping: session, throttle and registration clean-up (store.py:354-358), backtest prune (backtest.py:749-752) | on, in its own maintenance task | off |
| Seeds | on | on (idempotent under advisory locks, accounts.py:102-109, :168-170) |

- One expand migration adds `site text NOT NULL DEFAULT 'beta'` on sessions, jobs and backtest_jobs.
  - The default must be 'beta', because every existing row is the admin's. Design 1's 'live' default was wrong.
  - From then on the code writes `site` explicitly, and adds an index on `(site, state, created_at)` for the claim.
- Each backtest answer gets a version stamp, as screener answers already carry (screener.py:5-10, :665-677).

### 2.4 Change flow

| Change | Beta | Live | Rule |
|---|---|---|---|
| edge-bff code | push `main`, CI-gated | only on "push ke live", same sha | `live` is always an ancestor of `main`; no cherry-picks; at most two versions alive (martinfowler.com/bliki/CanaryRelease.html); promote at least weekly |
| edge_bff / terminal migrations | applied once (shared DB) | same moment | expand only. A contract step (DROP, RENAME, SET NOT NULL, new PK/UNIQUE, ALTER TYPE, DROP CONSTRAINT) needs the header `-- contract-after-live: <sha>` with that sha an ancestor of `origin/live`. A lint in run_job.sh/migration_job.py and CI enforces it; it would have flagged all three examples in section 1. A fresh dump is required before APPLY (martinfowler.com/bliki/ParallelChange.html; AWS blue-green whitepaper) |
| Data-table migrations and backfills | shared | shared | as today (large-update rules). Ad hoc heavy work outside IDX trading hours, because there is 1 vCPU (railway.ts:20) |
| terminal-api, backtest-worker, screener-worker | deploy as today | same instant | additive API only. Live smoke after every shared deploy; if it is red, roll that service back first. Escape hatch for an unavoidable break: a temporary `<name>-live` copy pinned to `live`. That needs the config.py hostname checks relaxed (config.py:166-182), about 0.25 day |
| Orc stack | as today | not used by live | becomes a shared service under the same rule when AI opens to users |
| Publisher output | SCHEMA_VERSION=1, additive only (publisher.py:158) | same | a breaking format publishes v2 beside v1 until `live` reads v2 |
| Plan catalog rows | shared rows | immediate | the user's go |

### 2.5 Promote, rollback and status (one script, `scripts/push_live.py`, in the owner's words)

**"push ke live" runs `--check`.**
1. Read the beta's `/version`, a new endpoint returning RAILWAY_GIT_COMMIT_SHA.
2. Require every check suite on that sha to be green, and a soak on the beta (default 24 h, adjustable).
3. Refuse, with the reason in plain Indonesian, when:
   - a check is red or pending;
   - beta's sha differs from the candidate;
   - a needed migration is not applied;
   - a user run is active (M340).
4. Show the commits since the current live tag, the pages that change, the migrations involved, and the beta smoke result.
5. Then ask for the go.

**`--apply`:**
1. Tag `live-YYYY-MM-DD-N` and fast-forward `live` (`git push origin <sha>:live`, fast-forward only).
2. Wait for edge-bff-live SUCCESS. SKIPPED is correct when apps/edge-bff did not change.
3. Read back `/ready` and `/version == sha`.
4. Run the live smoke with a synthetic free-plan account, whose password sits on a one-shot runner: sign in, BBCA in the Terminal, one Screener run, one small BBCA backtest, Overview/Radar/Watchlist reads.
5. Record the promote in RAILWAY_CHANGELOG.md and send a Telegram notice.

**Wait-for-CI on `live`.** It works without workflow changes: backend-tests, backtest-lookahead and generated-files run `on: push` with no branch filter (verified). edge-bff-image and backtest-page-smoke are path-filtered.

**"balikin live" runs `--rollback`.**
- Within 120 h: Railway's rollback of the previous edge-bff-live deployment, which takes seconds (Pro image retention: docs.railway.com/reference/pricing/plans; railway.com/guides/roll-back-bad-deploy).
- After 120 h: move `live` back to the previous tag (`--force-with-lease`) and redeploy, or CLI-upload a `git archive` of that tag.
- Then the smoke test.
- Never a database step, because migrations are expand-only.

**"status live" runs `--status`:** the live tag, its date, and what is on beta but not yet on live.

**A GitHub ruleset on `live`** blocks accidental pushes. Rulesets are available: the repository is public (`gh api repos/rednightt33/saniti`: visibility public). But the agents' GitHub credential has admin:true, so the ruleset guards only by convention.

**Secrets stay identical on both sites.**
- A separate EDGE_SESSION_SECRET isolates nothing. Sessions are looked up by plain sha256 (security.py:42-43). The secret only signs CSRF (security.py:46-47) and keys the sign-in throttle HMAC (throttle.py:61-63; main.py:235), so separate secrets would double the attempts an attacker gets on the admin account.
- EDGE_MFA_KEY derives the TOTP secret (auth_flows.py:538-577). EDGE_CODE_SECRET hashes email codes (auth_flows.py:127).
- Isolation comes from three things: host-only cookies with no Domain attribute (auth_flows.py:405-407), the `sessions.site` check, and the separate hosts.

### 2.6 How admin features stay off the public site
- **Beta (`EDGE_SITE=beta`):**
  - every request needs an admin principal (admin_owners, config.py:120) with MFA, or gets 403, enforced on the server;
  - registration, forgot and reset are refused, with wording that points to the live domain (edge-labels.js);
  - a "BETA · <sha>" banner;
  - AI Monitor, lab chunks (`/{app}-app/lab/{name}`, CONTRACT.md:270-271), the Phase 4 /admin page and `/api/v1/admin/*` live only here.
- **Live (`EDGE_SITE=live`):** a site mask strips `admin.access`, `monitor.*` and every lab-stage capability from every principal. The /admin, Monitor, lab and AI routes answer 404. The admin can sign in on live and sees it as a customer does.
- **Why this layout:** NIST SP 800-53 SC-2 separates management from user functions, including "isolating administrative interfaces on different domains" (csf.tools/reference/nist-sp-800-53/r5/sc/sc-2/). OWASP: "not to mix web applications of different security levels on the same domain" (cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- **Optional, about 0.1 day:** rename the session cookie to the `__Host-` prefix before switch-on, when only the admin would be signed out once (same OWASP page). Later, Cloudflare Access or an IP allowlist could go in front of the beta.

### 2.7 Cost per month (Railway Pro; memory USD 10/GB-month, volume 0.15, bucket 0.015; railway.com/pricing)
**Today:** USD 33.43 of usage, measured 2026-10-24..28 (capacity_fairness_scale_cost.md:50, table :96-110). The November pace is about USD 40 (USD 29.71 used by 11-13 in a period that began 10-21; ERRORS M424). Pro includes USD 20, so the bill is about the usage.

| Added | Basis | USD/month |
|---|---|---|
| edge-bff-live | edge-bff measured at 0.082 GB = 1.00 (capacity doc :105); more with users | 1-1.5 |
| Logical dump cron and private bucket | schema size not measured, expected under 1 GB | < 0.3 |
| Moving the restart times, option (a) in section 5 | at most about 1.7 GB of cache × extra hours × USD 0.0139/GB-h | 0-3 |
| Native volume backups or PITR (optional, decision 6) | not measured; copy-on-write keeps changed blocks, and backfills rewrite the 53 GB database often (docs.railway.com/reference/backups) | 1-5 or more; read back after a week |
| **Total** | | **about 1.5-2 core; about 3-10 with the options**, so about USD 36-50 of usage |

Not included: the domain and Resend (free-tier limits not checked).

### 2.8 Effort before launch (agent-days)

| # | Work | Days |
|---|---|---|
| a | Usage-limit headroom and soft warning (the user, in the dashboard); restart times moved with scripts/set_postgres_restart_times.py | 0.2 |
| b | `EDGE_SITE`: beta admin gate, registration refused on beta, live site mask and 404s, `sessions.site` binding, banner, `/version`, tests | 1.5-2 |
| c | Per-loop switches, `site` columns and claim filters, housekeeping and email only on live, the backtest version stamp | 1-1.25 |
| d | edge-bff-live in railway.ts, domain/TLS, Resend DNS and webhook, CORS; restart_postgres.py checks /ready of both sites (today only edge-bff, restart_postgres.py:314-327); M340 covers both | 1 |
| e | push_live.py (check/apply/rollback/status), live smoke runner, ruleset | 1.5 |
| f | Dump cron, pre-APPLY dump gate in migration_job.py, one restore drill; native backups if chosen | 1 |
| g | Contract-migration lint, plus a CI grep that blocks `edge_bff.`/`terminal.` outside apps/edge-bff, apps/terminal-api and database/migrations | 0.5-1 |
| h | Docs: AGENTS.md "Beta and live", README, PROJECT_CONTEXT, BACKTEST_END_TO_END, RAILWAY_CHANGELOG, EXEC | 0.5 |
| | **Total** | **about 7.5-8.5** |

- The user's own time is about 1 h: DNS records, Resend domain verification, the usage limit, and keys entered in the dashboard.
- Order: a, c, b and f must land before EDGE_MULTIUSER is switched on, even before the live domain exists. d and e come before the domain opens. g may slip to week 1, but its rule goes into AGENTS.md on day 1.
- Timeline: with a go by about 21 Nov, 3 Dec is realistic and 26 Nov is tight. The remaining EXEC-MU-ACCOUNTS work competes for the same days; 20261118_001/_002/_100 are still pending.
- **After launch:**
  - a compat-live CI job: replay the edge_bff/terminal migrations on a throwaway Postgres and run the live tag's DB tests against the candidate schema (Design 2), about 1 day;
  - a "status live" Telegram button;
  - an external uptime ping (telegram-monitor sleeps).

**New AGENTS.md section "Beta and live":**
1. `live` moves only through push_live.py, after the user's "push ke live" and go.
2. Never claim a live change before edge-bff-live is at SUCCESS and the sha has been read back.
3. Expand-contract for edge_bff, terminal, AI_conversation* and publisher formats, with the contract header.
4. Every shared deploy keeps working with the live sha and ends with the live smoke.
5. No ad hoc writes to the user schemas; a dump before any APPLY on them; aggregates only for user data.
6. Plan catalog rows change only with the user's go.
7. Email and housekeeping run only on live; the beta stays admin-only.
8. M340 and the Postgres restart cover both sites; ad hoc heavy work runs outside trading hours.

### 2.9 Risks this does not cover
1. **One Postgres, 2 GB / 1 vCPU.** A heavy job, an out-of-memory kill or a planned restart (about 12 s) stops sign-in and the Terminal on both sites.
2. **Owner-level reach.**
   - Data crons and runners use `${{Postgres.DATABASE_URL}}`.
   - The daily GitHub workflow builds an owner URL through the public TCP proxy (database-schema-docs.yml:99-106; proxy at railway.ts:10).
   - Grants cannot stop the owner, so only rules and backups protect user rows.
3. **Agents' credentials reach live.**
   - Railway: the agents use the proxy's account credential (ERRORS_AND_SOLUTIONS.md:7754-7756). Environment RBAC is Enterprise-only (docs.railway.com/reference/environments).
   - GitHub: the agents' credential is repo admin.
4. **Shared terminal-api, workers and publisher output change under live.** The smoke detects a break; nothing blocks it.
5. **Page/worker skew.** The Screener tolerates it partly (versions and needs_review, screener.py:454-455, :697). The backtest has only the new stamp.
6. **The beta's newest code manages live users through /admin.** Every action is audited in admin_audit, but it is still the untested version.
7. **Market-data errors reach both sites at the same publish.**
8. **Workspace-wide stops.** M424: hard limit 30 against 29.71 used, soft limit 0, every service down for about 20 h (ERRORS_AND_SOLUTIONS.md:7590-7608); also M346. No environment layout avoids this; only headroom and a warning help.
9. **The repository is public**, so code, migrations, railway.ts and runbooks are world-readable while the account database has a public proxy (password-protected).

## 3. Alternatives the user could prefer
- **A. Light production environment now (Design 2, Judge 1's pick).**
  - What it is: a new empty `production` environment with edge-bff, an edge-admin host, terminal-api, both workers, a small Postgres with PITR and no proxy, and its own bucket. It is fed only by a `market-release` copier of the published files. Promotion goes through GitHub-approved workflows. The agents get a dev-scoped project token ("can only be used to authenticate requests to that environment", docs.railway.com/integrations/api).
  - Trade-off: live accounts are fully off the dev Postgres and out of the agents' reach. It costs about +USD 10-18 a month (the screener's awake memory is about 1.15 GB, not 0.4-0.7) and about 7 agent-days plus about 2 h of the user's time; 3 Dec is at risk; it reverses the user's 2026-11-19 choice.
  - It is real only if the agents also get a non-admin GitHub identity. A project token also breaks serviceConnect (RAILWAY_CHANGELOG.md:1767) and today's runbooks that use the account credential.
- **B. Pin the workers from day one (Design 1).**
  - What it is: add screener-worker-live (following `live`) and backtest-worker-live (CLI upload of the live sha in each promote).
  - Trade-off: it removes page/worker skew, for about +USD 3-8 a month, +1 day (the config.py hostname change), and one more upload step per promote.
- **Not recommended: the choice as-is, without guardrails.** It is cheapest (+USD 1-1.5), but it carries the defects in section 1 (swallowed codes, beta code running live jobs, broken old site after a migration).

## 4. Growth path (the trigger for each next step)
1. **Pinned live worker copies.** When: a breaking core change is pending, or the first page/worker skew incident. Effort and cost: 1 day, +USD 3-8.
2. **Stage 2: account data on its own small Postgres.**
   - What: edge_bff and the terminal account tables, with PITR and no TCP proxy. Only the edge-bff, edge-bff-live and terminal-api logins write; agents read aggregates; migrations need the user's go. Data crons and runners move off the owner URL to a role with no rights on edge_bff/terminal.
   - When, whichever comes first: the first paying user or the payment adapter going live (CONTRACT.md section 11); about 50 registered users; the first incident where a data job, a restart or an agent touched user data or stopped sign-in.
   - Effort and cost: 3-4 days (terminal-api needs a second database connection, store.py:12-16), +USD 2-5.
3. **AI opened to a paid plan (D1 changes).** Orc becomes live-facing: either a live copy following `live`, or the two-version rule plus smoke. AI_conversation* then holds customer data and joins Stage 2's database.
4. **Stage 3: a separate Railway production environment (Alternative A).**
   - When: a second operator joins; UU PDP or payment compliance requires it; shared-service changes break live more than about twice a month; or Stage 2 is not enough.
   - Preconditions: agents on a dev-scoped project token, a GitHub identity without admin, and a check of read-only bucket keys.
   - Effort and cost: 1-2 weeks, +USD 10-18.
5. **A separate workspace for production.** When: a workspace-wide stop hits live users after launch.
6. **A full copy of dev.** Not justified at any foreseeable team size: it roughly doubles the bill and every data operation.

## 5. Decisions the user must take (each needs its context first, per AGENTS.md)
1. **Stage 1 shape:** (a) the user's choice plus the guardrails above [recommended]; (b) a light production environment now (Alternative A).
2. **Beta sign-in:** (a) admin only, as decided; (b) admin plus named test-* accounts, so registration and plan gates can be tested on the beta before a push.
3. **Workers:** (a) shared, with an escape hatch [recommended]; (b) pinned from day one, +USD 3-8, +1 day.
4. **Postgres restart times** (today 09:45 and 20:45 WIB, railway.ts:295; 09:45 is in trading hours):
   - (a) about 12:15 (lunch break) and 23:45 WIB, about +USD 0-3;
   - (b) drop the morning restart and keep 23:45, about +USD 5-10;
   - (c) keep the current times.
   The script refuses times near other crons or in B6.
5. **Usage limit:** a new hard limit (suggestion: about 2× the expected bill, about USD 80) and a soft warning (about USD 50).
6. **Backups:** (a) a logical dump of user data only, cents a month [minimum]; (b) the dump plus native volume backups or PITR, cost not measured.
7. **Public TCP proxy on the main Postgres:** (a) keep it, but move the daily schema-docs workflow to a read-only login; (b) close it and run that job inside Railway.
8. **Repository visibility:** keep it public, or make it private. Private hides the code and runbooks, but may cost Actions minutes and ruleset or environment features (to verify).
9. **Promote rules:** a 24 h soak on beta (yes or no), and whether the agent may roll live back by itself when the post-promote smoke fails, reporting at once.
10. **The Stage 2 trigger** to commit to now: the first paying user, about 50 users, or the first incident.
11. **Domain form:** a subdomain (app.<domain>) or the apex. This depends on whether the DNS provider supports CNAME flattening.

## 6. Claims dropped or corrected (do not repeat these)
- "A separate session secret isolates the sites." Wrong: see 2.5. It splits the throttle counters.
- "`site DEFAULT 'live'`." Wrong: the existing rows are the beta's, so the default is 'beta'.
- "Price/Feature_05 migrations reach live at once through /history." Wrong: nothing calls /history.
- "A volume backup copies the whole 100 GB." Wrong: backups are incremental; only a restore is whole-volume.
- "Each site gets its own terminal gateway key" with no code change. Wrong: terminal-api accepts one key.
- "EDGE_ENVIRONMENT=live forces Resend." Imprecise: see config.py:135-138 in 2.1.
- "Every CI workflow runs on any branch." Wrong: three do; two are path-filtered; one is scheduled.
- "A GitHub ruleset or environment approval stops agents." Wrong: the agents' credential is repo admin.
- "screener-worker uses 0.4-0.7 GB awake." Wrong: about 1.15 GB (M424); RSS 0.57 GB idle to 1.81 GB full (apps/screener-worker/README.md:311).
- "Design 1 takes 3.5-4.5 days." Not credible: about 7.5-8.5 days for this scope.
- "The database is about 23 GB" (EXEC.md:15996). Stale: 53 GB (RAILWAY_CHANGELOG.md ~:1722; DATABASE_CHANGELOG.md:826).

## 7. Not verified (check before or during the build)
- Native backup and PITR availability and real cost on this plan.
- Whether a Railway rollback behaves as expected after `live` has been moved back.
- edge-bff-live's real memory.
- The size of the user schemas.
- GitHub feature availability if the repository goes private.
- Resend free-tier limits.
- The current IDX session times (lunch break assumed Monday-Thursday 12:00-13:30, Friday 11:30-14:00).
- UU PDP 27/2022 duties for account data and dumps.
- Whether Railway buckets can issue read-only keys (matters for Stage 3).
