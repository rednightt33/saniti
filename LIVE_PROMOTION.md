# Bringing beta work to the live site

This document is for any agent or person who brings work from the beta to the live site. It assumes you have not
read the conversation that set this up, so read it end to end before you move the `live` branch.

User decisions (EXEC.md, option A):

- 2026-11-19 and 2026-11-20: two sites from one code base.
  - The beta is `edge-bff` at edge-bff-dev.up.railway.app. It is for the admin only, gets every feature first and
    deploys from `main`.
  - The live site is `edge-bff-live` at app.edgefinance.id. It deploys only from the branch `live` (Wait for CI off since 2026-11-23, the user; back on near the launch).
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

**3f (EXEC option A item 4, CONTRACT.md 8 "Lab code") built what keeps a lab item out of the public page builds and the
tab catalogs.** What held back the first lab item after its checker (2026-11-21) is closed on both sites by the deploys
of 2026-11-22 (RAILWAY_CHANGELOG.md "The round's close": the workers' refusals name nothing outside allow, both workers
load the lab formulas, the live site's Terminal parks a saved entry its build lacks and cuts the stored examples to its
release file), and the user lifted the item guard on 2026-11-23 ("Cabut tes penjaga lab"). The guards that stay:

- `tests/test_releases.py` `LAB_KIND_HELD`: a Flow indicator may not be lab (its formula has no lab registration point:
  `calc/flow.ts` keeps its map unexported and keys each formula by its id);
- the standing rules: an item no worker gates by id is never lab, nor an item the shipped code names or computes by its
  key (CRIT-3), and a released entry's text names no lab item;
- `tests/test_live_switch.py` `LAB_TAB_HELD_UNTIL`: a lab tab's rail entry, route, frame wrapper and words are in the
  public shell, so no tab may be lab until the server hands the rail entry to the principals holding it.

A lab indicator follows `INDICATOR_BETA_TO_LIVE.md` (Part A: the beta only; Part B: the release), proven end to end by
its dry run of 2026-11-23.

What is built:

- **Page builds.** Every page build applies the filter (`apps/edge-bff/shared/release-filter.mjs`, in `plugins` and
  in `worker.plugins`, so the Web Worker files too): the public build keeps only the released entries of every file
  that names items. An unlisted id is lab, a missing release file or a part of a registry that is missing stops the
  build.
  - `npm run build` of the Terminal and the Backtest page also makes a lab build (`static/terminal-app-lab`,
    `backtest/dist-lab`), which keeps every entry and the lab formulas. The other pages have no lab build.
  - edge-bff serves the lab build from the same address to the admin on the beta (`auth.lab_admin`: with the switch on,
    admin.access and the second factor passed; on today's beta, with the switch off, the owner's signed-in session) who
    holds every item of every kind (`catalog.holds_every_item`: the build carries them all). Its files answer under
    `/<app>/lab/assets/` and 404 to everyone else and on the live site.
- **Tab catalogs.** The Screener's and the Backtest's catalogs list a lab item only to a principal that holds it
  (`catalog.tab_list`, the rule of `/api/v1/catalog`), and a preset that reads an entry left out is left out too.
- **Lab tabs.** A tab with its own page app (`<tab>-app`) at the lab stage is served, page and assets, to the admin on the
  beta who holds the tab's own `<tab>.view`. A new tab must be its own `<tab>-app`: a tab that is a page of the shell
  ships its whole code in the shell.
- **Items no worker gates by id are never lab** (a standing rule, `test_releases.py`
  test_an_item_no_worker_gates_by_id_is_never_lab): a Screener metric with a `ref` (hi52, lo52, rs, vol_ratio: it reaches
  the wire as its composition of transforms) and a universe attribute every answer shows (`row`). Every principal
  reads or runs them whatever its plan, so the lab stage could only hide a catalog row. A new one is staged in the lab
  with an id the workers gate (an attribute without `row`, a pattern, cross-section metric or indicator).

These tests enforce the switches:

- `apps/edge-bff/tests/test_live_switch.py` fails when a capability tab (the first part of a key in
  `edge_bff.capabilities`) or a page of the shell (`static/edge-app.js`, routes with `auth:true`) has no entry. Each
  must be listed as lab or released, or belong to `BETA_ONLY_TABS`. The same file shows that a lab tab is refused on
  the live site, the admin's `*` included, is hidden from the live rail, and stays on the beta. It refuses any lab tab
  for now (above).
- `apps/edge-bff/tests/test_releases.py`: every registry id has an entry; an item is at the lab stage only in a kind `LAB_KIND_HELD` does not hold (a candle pattern and a Flow indicator held).
- `apps/edge-bff/tests/test_3f_public_bundles.py` scans every file served without the admin check (each page's build,
  its Web Worker files and the shell) for every lab item's id and formula key. Its proof builds (round 2 of the
  checker) copy apps/edge-bff, write fixture items on disk into every registry the filter knows (one released, one lab,
  one unlisted, each with a marker; `terminal/tests/lab/plant.mjs`), import them from every page and Web Worker entry,
  and build every page there with its own configuration: each public bundle file carries the released ones only, each
  lab one all of them, the lab formula only the lab builds, and each build names only its own files. With
  `EDGE_TEST_REQUIRE_NODE=1` (CI) a page not built fails the test instead of skipping it.
- `apps/edge-bff/terminal/tests/lab/public-entries.test.mjs` walks every page and Web Worker entry, derived from each
  `index.html` and each `new Worker(new URL(...))`: none reaches a module under `terminal/src/lab/` but `none.ts`.
  `coverage.test.mjs` fails when a JSON file a public entry reaches is neither filtered nor written down as naming no
  item, or when a part of a registry the filter leaves names an item.
- `apps/edge-bff/tests/test_3f_lab_pages.py` (who is served a lab build and a lab tab; the repository's real lab builds
  too) and `tests/test_3f_tab_catalogs.py` (the catalogs, on the beta and the live site, and both routes over HTTP).

How a new piece of work enters:

- **A new tab or page.** Its own `<tab>-app`, listed in `tabs`. While the lab-tab guard holds, a new tab is added as
  `"released"` only when the user asks for it to be live, or kept off `main`. A tab you leave out is lab anyway, but
  `test_live_switch.py` fails until it is listed.
- **A new catalog item.** May enter as `"lab"` (since 2026-11-23; a Flow indicator not yet). A technical indicator follows
  `INDICATOR_BETA_TO_LIVE.md` literally; in short:
  - Its definition goes into its registry as usual. The public build leaves it out, and the lab build keeps it.
  - A lab technical indicator's formula goes into `apps/edge-bff/terminal/src/lab/index.ts`, registered into the
    formula map `F` (and its defaults into `DEFAULTS`) under its registry `key`, with the released formulas' wrapper
    `def`. Never put it in `calc/indicators.ts` while it is lab: that file is in every public build.
  - The registry generators and both workers load that module (built, 3f TR-2: `@edge-lab`, `terminal/src/lab` in both
    engine versions; every process the workers' loader starts registers it, the tests and the look-ahead gate
    included). The workers' engine and registry versions change when the item is added. The Screener also needs its
    overlay entry (`screener-overlay.json`). The page tests pin 53 indicators of the public registry: they change only
    at the release.
  - Releasing it moves the formula into `calc/indicators.ts` and the stage to `"released"`, in one commit, with the
    page tests' pinned counts.
  - A lab Flow indicator's formula has no registration point (the `FLOW` map of `calc/flow.ts` is not exported). Its
    formula runs on the page's main thread, so that point is reached from `main.ts`.
  - A lab candle pattern, Screener metric or preset is data the workers read whole. The public page builds and the
    catalogs leave it out.
  - Items written in code are not release items: the Terminal's netflow and netbuyline, the VOL row, the Backtest's
    legacy cards (fnet, broker, top5). The bundle scan fails if one of them is made lab, because the code names it.
  - Nor can an existing item be put back at the lab stage by the release file alone when code names or computes it
    (round 2, CRIT-3): every Flow indicator's formula is keyed by its id in `terminal/src/calc/flow.ts` (FL51's entry is
    read with `find(...)!`, so filtering it out would break the page), the page modules name about 30 more ids
    (`flowIndicators.ts` SINGLE_SECURITY, `indMenu.ts`, the Screener page's `builder.ts` and `extra-columns.ts`, the
    Backtest's `core/catalog.ts`), and built-ins compute some without their id (the Backtest's rank items for I07, I35
    and I13, the ATR stops for I30, the transform `ma`). Held: `test_an_item_the_shipped_code_names_is_never_lab`.
  - A released entry's text must not name a lab item.
- **A change to a released tab.** This needs care: once `live` moves, the change is live. Either keep it off with its
  own new item at the lab stage (a tab once its guard is lifted), or tell the user it will be live when `live` moves
  (section 4, step 3).

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

   Only a fast-forward to the target. Railway deploys `edge-bff-live` at once (Wait for CI off since 2026-11-23); read
   that commit's CI to its end and report a red run to the user with a proposal. Never
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
   - an unknown login 401;
   - `lab build terminal-app` and `lab build backtest-app`: the public build, and the lab build's Web Worker file and its
     fixed-name probe (`lab_probe_file`, `shared/release-filter.mjs` `LAB_PROBE`) 404.

   The browser smoke expects the Terminal to open, the rail to have no Monitor or lab tab, and no model list to be
   asked for.

   The example smoke (3e, ERRORS M527) opens each data page's example as a visitor, in a real browser:

   ```
   EDGE_TEST_CHROMIUM=/opt/pw-browsers/chromium python3 verification/edge_multiuser/live_smoke/example_smoke.py https://app.edgefinance.id --png <dir>
   ```

   It expects, for every tab of `app/examples.py` TABS: the example in its frame under its dated note, only
   `/api/v1/examples/<tab>/...` read, and a click opening "Sign in to open <tab>"; the Watchlist with its list and its
   two date pills; VERDICT OK. `EDGE_TEST_CHROMIUM` names a Chromium where Playwright's own is not installed.

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
| Monitor, Admin | beta only | — | `BETA_ONLY_TABS`. The admin page (Phase 4): its files and data answer 404 on the live site, `/admin` too; on the beta its code step needs `EDGE_MFA_KEY` equal to the live site's, and its Resend code `EDGE_CODE_SECRET` equal to the live site's (`config.shared_key_marks` logs both marks); its actions (disable, plan, sessions, codes) write the shared database, so they act on live accounts |
| A sign-in stays at the page it was shown at (Phase 4; every tab, when the account can open it; the user's "A", 2026-11-22) | released | 2026-11-22 (`ec739a06`) | Before: every sign-in led to the Monitor or the Terminal. With this commit a person signed out at, say, `/backtest` lands on `/backtest` after signing in; `/login` and the account pages lead to the landing page as before |
| Contact support (Phase 4; the user, 2026-11-22: the rail's mailbox on both sites; `support` in `tabs`, a capability domain with no page of its own) | released | 2026-11-22 (`ec739a06`) | Migration `20261122_001` first (expand-only). **At its promotion the live site needs** `TELEGRAM_NOTIFY_URL`, `TELEGRAM_SUPPORT_SECRET` (references to telegram-monitor's, as the beta's) and `EDGE_ADMIN_ORIGIN` (the beta's address) on `edge-bff-live`; without them a message is still kept and emailed, with no Telegram summary and no link. The live site's sender emails the admins; its housekeeping retries the Telegram summaries of both sites. **Until `live` runs this commit, the live site's older sender (`4b35b5ed`) sends the beta's support emails without their images and without Reply-To** (it posts only the sender, the address, the subject and the text, and claims every pending email of the shared outbox), and no site retries a Telegram summary that failed: promote before relying on the emails, and never call the email checked from a beta test. Promoted 2026-11-22 with `TELEGRAM_NOTIFY_URL`, `TELEGRAM_SUPPORT_SECRET` and `EDGE_ADMIN_ORIGIN` set on `edge-bff-live` (RAILWAY_CHANGELOG.md) |
| Privacy and Terms links hidden until their texts exist (both sites); Terminal footer "Charts by TradingView" only | released | 2026-11-20 (`4785d1ef`) | The user's "OK" to both; the links return when `EDGE_PRIVACY_URL` / `EDGE_TERMS_URL` are set |
| Tab switch (`tabs` in the release file), this runbook, `scripts/live_diff.py` | released | 2026-11-20 (`4785d1ef`) | No visible change: every tab stays released |
| The A2 fix (the account's own browser, a reset bound to its browser, the client's part of an address's day; ERRORS M517) | released | 2026-11-21 (`4b35b5ed`) | Migrations `20261120_001` and `_002` applied on dev. Goes live on the user's request. The user chose (2026-11-21) to bring it live together with 3e and 3f, in one promotion, not alone |
| The MFA lock names the way still open (ERRORS M519: with both ways locked, the `/mfa` page no longer offers the authenticator code) | released | 2026-11-21 (`4b35b5ed`) | Additive (`details.use` "code"); no migration. It goes live with A2, 3e and 3f |
| 3e without the example mode (CONTRACT 8b; every tab in the rail, `LockedTabPage`, the Terminal's locks in place) | released | 2026-11-21 (`4b35b5ed`) | **Visible on the live site when `live` moves past it:** a visitor's rail gains Overview, Watchlist and Radar, and every tab but the Terminal shows a sign-in card. The Terminal shows "Broker data · Locked" as the Flow Timeline's head, the Events button with a lock, and IHSG Locked in Statistics, where the F1 stopgap hid them. A test account sees "not in your plan" on the paid tabs. A saved asset the visitor does not hold says Locked; the Broker activity button carries the lock. Not built: the example mode and the Monitor's example (D4) |
| 3f, lab code out of the public bundles (CONTRACT 8 "Lab code", 8b "3f"), with both rounds of its checker | released | 2026-11-21 (`4b35b5ed`) | No visible change from 3f itself: no item or tab may be lab yet (section 3), and every page but the Backtest ships the same files (the image's asset names at `33c84c1f` and `9723caf7` are equal for the Terminal, its lab build, the Screener, the Radar, the Overview and the Watchlist). It also fixes two defects older than 3f that act on the live site once `live` moves: the Screener's catalog copies are kept per the presets held, so the admin and an account without presets never share one (ERRORS M522); a saved screen is checked again under any context but the widest (M526; no deployed site's answer changes) |
| The image builds the Backtest page as CI builds and tests it (ERRORS M525; with 3f, older than it) | released | 2026-11-21 (`4b35b5ed`) | The bundle's files change once: `index-BliQA-_i.js` becomes `index-BoIVVtuS.js` and `load.worker-BVk4JsHs.js` becomes `load.worker-BZlCroBw.js` (CI's image builds of `33c84c1f` and `9723caf7`), the lab build's likewise. The same source; its Terminal modules are now compiled as ES2022 (their class fields), as in the build every page test runs on. Watch the beta's Backtest page after the deploy |
| The example mode (3e, CONTRACT 8b "3e"; ERRORS M527): a visitor and the free plan see each data page as it opens, with one day's data, and a click asks to sign in or to upgrade | released | 2026-11-21 (`4b35b5ed`) | **Promoted 2026-11-21:** `live` at `4b35b5ed`, then `20261121_002` applied (APPLY `f866eeca`); the smoke as a visitor OK, `example_smoke.py` included (RAILWAY_CHANGELOG.md). **The Watchlist (the user, 2026-11-21: "Untuk table watchlist nggak apa-apa pakai data latest saja", "Benar opsi B"):** like the Overview, it needs no capture: edge-bff cuts the live publication to today's LQ45 (as overview-meta publishes it) with the four default indicators (ERRORS M527); the stored rows of 30 October (the wrong list) were deleted on dev (job `724dc7c4`). **Apply order:** (1) before the promotion, `20261121_001` (the table `edge_bff.example_files`; nothing reads it yet) is applied on dev and the capture job (`verification/edge_multiuser/example_mode/capture_job.py`) writes the stored examples' files (the Radar, the Backtest, the Screener); (2) `live` moves to the commit that serves them: an account on the free plan sees the examples at once (it holds the flags since 20261117_003; in the pre-launch mode only a test account on it signs in), a visitor still the locked pages; (3) once the live site runs that commit, `20261121_002` (the guest plan's five example flags) is applied: a visitor sees the examples on its next request; (4) the smoke as a visitor: `http_smoke.py`'s `examples` entry shows every tab's index 200 and every file 200 (the tabs of `app/examples.py`; before (3) they answer 403); `/overview` opens on the latest market date under its note, a filter works, 5D or another time control opens the sign-in box, the page reads only `/api/v1/examples/overview/...` (the one example read through terminal-api for the visitor); `/watchlist` opens on the LQ45 list of the latest price date under its note (the prices' and the broker data's dates in its pills), a click opens the sign-in box, the page reads only `/api/v1/examples/watchlist/...` (read through terminal-api for the visitor, as the Overview's); `/radar` opens the example under its note, the page reads only `/api/v1/examples/radar/...`, a click opens the sign-in box; `/backtest` opens on the stored run (its results view), reading only `/api/v1/examples/backtest/...`; `/screener` opens on the preset Golden Cross with its results, reading only `/api/v1/examples/screener/...` (the example-mode checker, ERRORS M527: the Overview and the Watchlist were missing here). The Backtest's example is the stored run of the page's default setup: a commit that changes that setup fails the page suite (`backtest/tests/example.test.ts`) until the example is captured again (`verification/edge_multiuser/example_mode`: backtest_catalog_job.py, backtest_request.ts, capture_job.py with capture_backtest.json), so `live` never moves to a commit whose page would refuse its own example. The Market Overview's and the Watchlist's examples need no capture: each is the live publication's opening view on its newest day, trimmed by edge-bff, and their terminal-api reads count against the visitor's own Terminal quota (the guest owner, per visitor) once per publication and process. The beta shows no example (the admin holds every tab). **Rollback:** a forward migration with `20261121_002`'s rollback block (the visitor's locked pages again); the table stays (expand-only) |
| The round of 2026-11-22: Phase 4 (beta only), group A, the lab gaps, fix round 1 of the test-out, ERRORS M539 and M547, the Terminal drag rounds of another session (M538) | released | 2026-11-22 (`ec739a06`) | The user's go for the beta deploy and the promotion (RAILWAY_CHANGELOG.md 2026-11-22). The shared workers changed for both sites at the beta deploy: a refusal to a restricted principal names no item outside its allow, a deep request answers 422, both engine versions changed (saved screens re-reviewed once). Fix round 1's fixes are tested out by another agent only in step 8 (EXEC UD23). |
| The Screener worker: its catalog carries the admin mark (ERRORS M520), the admin-only Flow versions are refused before their parameters are read (M521), and a deeply nested request is answered 422 again, not 500 (M524) | released | 2026-11-21 (`4b35b5ed` on `main`: screener-worker `4f68955c`, a shared service) | The live Screener then lists FL18, FL19, FL20, FL23, FL44, FL45 and the preset `follow` to nobody, the admin included (nobody holds the point-in-time right on live). That is the intended rule. The Screener engine version changes once per deploy that carries these. Tell the user before `main` moves |
