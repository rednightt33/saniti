# Bringing beta work to the live site

This document is for any agent or person who brings work from the beta to the live site. It assumes you have not
read the conversation that set this up, so read it end to end before you move the `live` branch.

User decisions (EXEC.md, option A):

- 2026-11-19 and 2026-11-20: two sites from one code base.
  - The beta is `edge-bff` at edge-bff-dev.up.railway.app. It is for the admin only, gets every feature first and
    deploys from `main`.
  - The live site is `edge-bff-live` at app.edgefinance.id. It deploys only from the branch `live`, with Wait for CI.
- 2026-11-20: "Tidak bisa pengembangan di beta dibawa live on schedule basis. Semuanya harus on request basis."

## 1. The two sites

| | Beta | Live |
|---|---|---|
| Railway service | `edge-bff` (`c3656044-…`) | `edge-bff-live` (`3baa0d66-…`) |
| Address | https://edge-bff-dev.up.railway.app | https://app.edgefinance.id (edgefinance.id and www redirect to it, 301, Hostinger) |
| Branch | `main` | `live` (Railway waits for the commit's CI) |
| Who signs in | the admin (`EDGE_MULTIUSER` off) | the admin and accounts marked as test accounts (pre-launch mode); visitors open the Terminal on BBCA |
| What it shows | every tab, lab and released | released tabs and items only (section 3) |

What is shared and what is not:

- **Shared:** one code base (`apps/edge-bff`). One PostgreSQL database, so both sites see the same users, sessions,
  watchlists, layouts and jobs. One bucket. terminal-api, the workers, the publisher and market-ai-orc. A change to a
  shared service is live for both sites the moment it deploys.
- **Separate:** each site runs the commit of its own branch, with its own variables. Each site's `GET /version` shows
  its commit.

## 2. Principles

1. **Only on request.** The user names what goes live. Nothing moves on a schedule, and nothing moves "while we are at
   it".
2. **Whole commits.** `live` moves to one commit of `main`. Every commit before it goes along. The target must be:
   - a commit the beta already runs (its latest SUCCESS deployment);
   - a commit whose own CI run is green.

   So anything not ready must be switched off on the live site by the code itself (section 3). It is never kept out by
   picking commits.
3. **Expand-only migrations.** The database is shared and the live site runs older code. Every migration that reaches
   `main` must keep that older code working:
   - add tables, columns with defaults, or new rows;
   - never drop, rename or narrow anything the live site's commit still reads;
   - remove an old column or table only after `live` has moved past every reader.

   A known side effect (ERRORS M511): an expand migration fails each open connection's cached query plan once (0A000).
4. **Compatible shared services.** terminal-api, the workers and the AI serve both sites.
   - Add fields; never remove or rename one that the live site's commit reads.
   - A new route serves both sites. The live site reaches it only once its own code calls it.
5. **Switches live in the code, not in variables.** The release file decides what is lab and what is released (section
   3). So a given commit means the same thing on both sites, and a test can check it.
6. **Plans in the database.** What each plan gets is the plan's capabilities in `edge_bff` (CONTRACT.md 8a). It changes
   through an audited step, not a deploy. A plan can only grant what the live site holds: a lab tab or item stays off
   for everyone there, the admin's `*` included.

## 3. The switches: lab or released

`apps/edge-bff/catalog/releases.json` is kept by hand; no script writes it. The live site holds nothing at the lab
stage. The beta (switch off) shows everything to the admin.

| What | Where | Unlisted means | Effect of `lab` on the live site |
|---|---|---|---|
| A tab: the first part of a capability key, e.g. `screener` in `screener.view`, or a page of the shell | `tabs` | lab | `principal.beta_only` refuses its keys to everyone, the admin's `*` included; `auth/config` `hidden_tabs` hides it from the rail |
| A catalog item: an indicator, Flow indicator, candle pattern, Screener metric or preset | `items` | lab | its key `<family>:<id>` is refused (`releases.KIND_OF_FAMILY`) |
| A tab that never goes live | `principal.BETA_ONLY_TABS` (`admin`, `monitor`) | — | its keys are refused and its routes answer 404 before any session |

These tests enforce the switches:

- `apps/edge-bff/tests/test_live_switch.py` fails when a capability tab (the first part of a key in
  `edge_bff.capabilities`) or a page of the shell (`static/edge-app.js`, routes with `auth:true`) has no entry. Each
  must be listed as lab or released, or belong to `BETA_ONLY_TABS`. The same file shows that a lab tab is refused on
  the live site, the admin's `*` included, is hidden from the live rail, and stays on the beta.
- `apps/edge-bff/tests/test_releases.py` covers the items.

How a new piece of work enters:

- **A new tab or page.** Add it to `tabs` as `"lab"` in the same commit that adds it. A tab you leave out is lab
  anyway, but `test_live_switch.py` fails until it is listed.
- **A new catalog item.** Leave it out of `items` (lab) or add it as `"lab"`.
- **A change to a released tab.** This needs care: once `live` moves, the change is live. Either keep it off with its
  own new item or tab at the lab stage, or tell the user it will be live when `live` moves (section 4, step 3).

Releasing means a commit that changes the stage from `lab` to `released`. It takes the normal path (session branch →
CI → `main` → the beta runs it), and then `live` moves to it. The user's request names it.

## 4. Steps for each request

1. **The user names the scope**, for example "bawa Screener preset baru ke live". Record their words in EXEC.md.
2. **See what would move.**

   ```
   python3 scripts/live_diff.py --sites
   ```

   It is read-only and fetches `main` and `live`. It lists:
   - the commits the live site lacks;
   - the areas they change;
   - the new migrations (check each against principle 3);
   - the release file's changes and what stays lab;
   - the commits both sites run, and whether the beta runs `main`.

   Add `--json` for machine-readable output, or `--beta <ref>` for a target older than `main`.
3. **Tell the user, in plain Indonesian, everything that moves**, not only what they asked for:
   - the other commits that come along;
   - what stays off (lab);
   - the migrations;
   - any change to a released tab.

   Wait for their go. If the request is a lab item or tab, the release commit (section 3) comes first.
4. **Pick the target.** It is the commit the beta runs (`GET https://edge-bff-dev.up.railway.app/version`), and its
   own CI run must be green (the GitHub Actions runs for that commit). If the beta does not run it yet, put it on
   `main` first and wait for the beta's SUCCESS.
5. **No active user run (ERRORS M340).** Run `python3 scripts/restart_postgres.py` without `--apply`; this only
   checks. Its `user_runs` must show `edge_jobs` 0 and `orc_turns` 0. A memory refusal in the same output does not
   matter here. If a run is active, wait until it ends.
6. **Move `live`:**

   ```
   git push origin <commit>:refs/heads/live
   ```

   Only a fast-forward to the target. Railway waits for that commit's CI, then deploys `edge-bff-live`. Never
   `railway up` to that service: a CLI upload skips both the branch and CI, and the next push to `live` replaces it.
7. **Wait for SUCCESS.**
   - `railway deployment list -s 3baa0d66-41ce-4986-9b56-93b4d13a4e10 -e dev --json`: the new deployment must reach
     `SUCCESS`.
   - `GET https://app.edgefinance.id/version` must show the commit.
   - Never claim the deployment worked before both hold.
8. **Run the smoke from outside.** Neither script needs credentials.

   ```
   python3 verification/edge_multiuser/live_smoke/http_smoke.py https://app.edgefinance.id
   node verification/edge_multiuser/live_smoke/browser_smoke.cjs https://app.edgefinance.id <png> /terminal
   ```

   The HTTP smoke expects:
   - `/ready` 200, and CSP and HSTS on the page;
   - `hidden_tabs` holding `admin`, `monitor` and every lab tab;
   - a visitor's BBCA open and another ticker refused with the sign-in words;
   - `routes.unexpected` `{}`. Beta-only routes answer 404. Gated routes answer 401. The Terminal relay's made-up path
     answers 404;
   - registration 403 `REGISTRATION_CLOSED` while in pre-launch;
   - a foreign origin 403;
   - an unknown login 401.

   The browser smoke expects the Terminal to open, the rail to have no Monitor or lab tab, and no model list to be
   asked for.

   Then the owner signs in to check the admin's side themself. The admin's first password (`EDGE_ADMIN_*` on
   orc-test-runner) stops working once the owner resets or changes it (ERRORS M516). `--admin` tries it once, and a
   401 then is expected.
9. **Records:**
   - `RAILWAY_CHANGELOG.md`: the commit, the deployment ID, the smoke and the user's words;
   - EXEC.md: the request's status;
   - the feature notes below;
   - `ERRORS_AND_SOLUTIONS.md`: anything that went wrong.

## 5. Rollback

- **One version back.** With the user's go, move `live` back to the previous commit, the one in RAILWAY_CHANGELOG.md:

  ```
  git push --force-with-lease origin <previous commit>:refs/heads/live
  ```

  CI and the deploy follow. Or redeploy the previous deployment from the Railway dashboard. Then run the smoke again.
- **A migration that went out with the bad commit stays.** It was expand-only (principle 3), so the older code still
  works with it.
- **Take the site down:** EXEC.md option A, "Switch-on order and rollback" (`railway down`, housekeeping back to the
  beta, the open Backtest jobs).

## 6. Never

- Never `railway up` to `edge-bff-live`, or redeploy it from a commit that is not on `live`.
- Never move `live` to a commit the beta has not run, or to a commit whose CI is red or still running.
- Never move `live` on a schedule, or together with work the user did not name.
- Never use a migration that breaks the live site's commit (drop, rename, narrow, or a new NOT NULL without a
  default).
- Never switch a tab or an item for one site with a variable. The stage lives in the release file.
- Never change the live service's trigger or source from a session. Its token cannot (ERRORS M514), so ask the user,
  naming every field.

## 7. Feature notes

Update this table at every promotion: what is on each site, and since when.

| Feature or tab | Stage | On live since | Notes |
|---|---|---|---|
| Terminal | released | 2026-11-20 (`349947ec`) | Visitors: BBCA, prices from 730 days back, broker and events locked (F1, TEMPORARY until 3e). The visitor's Statistics asks for IHSG and gets 403 (3e, ERRORS M516) |
| Backtest, Screener, Watchlist, Radar, Overview | released | 2026-11-20 (`349947ec`) | Signed-in only. Pre-launch: the admin and test accounts |
| Catalog items: 53 indicators, 56 Flow indicators, 20 candle patterns, 55 Screener metrics, 26 presets | released | 2026-11-20 | Every item that existed on 2026-11-17 is released (user decision 2026-11-17) |
| Monitor, Admin | beta only | — | `BETA_ONLY_TABS` |
| Privacy and Terms links hidden until their texts exist (both sites); Terminal footer "Charts by TradingView" only | released | 2026-11-20 (`4785d1ef`) | The user's "OK" to both; the links return when `EDGE_PRIVACY_URL` / `EDGE_TERMS_URL` are set |
| Tab switch (`tabs` in the release file), this runbook, `scripts/live_diff.py` | released | 2026-11-20 (`4785d1ef`) | No visible change: every tab stays released |
| The A2 fix (the account's own browser, a reset bound to its browser, the client's part of an address's day; ERRORS M517) | beta first | not yet | Needs migrations `20261120_001` and `_002` on the database first (applied on dev before the beta); goes live on the user's request |
