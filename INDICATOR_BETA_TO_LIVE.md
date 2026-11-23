# A new indicator: beta only (lab), then live

A checklist an agent follows literally, step by step, for a new technical indicator of the Terminal (the `I` series of
`apps/edge-bff/terminal/src/data/indRegistry.json`) that the Terminal draws, the Screener screens and the Backtest tests.
Part A puts it on the beta only (the `lab` stage); Part B releases it to the live site when the user says so.

The user, 2026-11-23: "Ok untuk indicator beta to live MD, masukan ke agents md beserta 2 docs sebelumnya agar AI bisa
refer that" and "Cabut tes penjaga lab". The plan behind it (the user, 2026-11-22): 10 to 20 new indicators built and
tested on the beta only, in the Terminal, the Screener and the Backtest; each moves to the live site only when the user
says so.

Proven by a dry run on 2026-11-23: a lab indicator I54 (Price Z-Score) planted in a copy of the repository, every page
built, the suites run, then released the same way (Part B). Every step below was needed by that run; the files and
lines it changed are cited.

**Read with it:**
- `SCREENER_ONBOARDING.md` §2.11 (the worked example of a released indicator, end to end: formula, registry, parity,
  overlay, tests, deploy order, records) and §3.2 (the one-page checklist). They predate the lab stage; this file says
  where the lab differs.
- `LIVE_PROMOTION.md` §3 (the lab and released switches, what keeps a lab item off the live site) and §4 (the steps of
  every promotion).
- `BACKTEST_END_TO_END.md` and `apps/edge-bff/backtest/CONTRACT.md` before any change the Backtest reads; AGENTS.md
  "Backtest look-ahead gate".
- AGENTS.md "Deploys" (every deploy waits for the user's confirmation) and "The live site".

## What the lab stage does (and what it does not)

| Place | A lab indicator | Where it is enforced |
|---|---|---|
| Terminal page, public build (every visitor, the live site, any account on the beta but the admin) | absent: no registry entry, no formula | `apps/edge-bff/shared/release-filter.mjs` (`releaseFilter`, `labAlias`: `@edge-lab` is `terminal/src/lab/none.ts`); `tests/test_3f_public_bundles.py` |
| Terminal and Backtest pages, lab build | present, entry and formula | the same filter with `lab: true` (`static/terminal-app-lab`, `backtest/dist-lab`) |
| Who gets a lab build | the admin on the beta who holds every item (`auth.lab_admin`, `catalog.holds_every_item`) | `apps/edge-bff/app/main.py` `page_app` (`lab_build`); never on the live site |
| Screener page | no lab build: its builder reads the catalog the worker answers (`screener/src/api/live.ts` `catalog`), and edge-bff lists a lab entry only to its holders (`catalog.tab_list`) | `tests/test_3f_tab_catalogs.py` |
| Workers (Screener, Backtest; shared by both sites) | hold every formula, a lab one included; compute it only for a principal whose `allow` holds it | `apps/edge-bff/app/allow.py` `allow_of` (never `*` from the live site); screener-worker `src/run.ts` `gateSent`, backtest-worker `src/access.ts` `requireItem` |
| Live site | refused for everyone, the admin's `*` included | `releases.json` stage `lab`; `principal.live_view`; `tests/test_beta_live_site.py` |
| The AI (market-ai-orc, shared) | not told about it while lab | do not add it to the AI formula reference until Part B |

Not covered by the lab stage:
- **Flow indicators** (`FL..`): held at `released` (`apps/edge-bff/tests/test_releases.py` `LAB_KIND_HELD`): a lab Flow
  formula has no registration point (`terminal/src/calc/flow.ts` keeps its `FLOW` map unexported and keys every formula
  by its id). A beta-only Flow indicator needs that point built first, reached from `terminal/src/main.ts`, the workers
  and the generators as `@edge-lab` is: a separate piece of work, asked of the user.
- An indicator another built-in computes by its key (a pattern, a transform, a preset that needs new code in the shared
  cores) is named in code and cannot be lab (`test_an_item_the_shipped_code_names_is_never_lab`).
- Candle patterns, Screener metrics and presets may be lab as data (`LAB_KIND_HELD` comment in `test_releases.py`);
  this checklist covers indicators.

## Part 0: before writing code

- [ ] The user's words that ask for the indicator, in `EXEC.md` with the date (AGENTS.md "Plans").
- [ ] Its definition settled with the user (SCREENER_ONBOARDING §2.11 Step 0): the outputs, the parameters with their
      defaults, minimums and steps, the reference it is checked against. **Causal only**: a value at bar t reads bars up
      to t, never later ones (the Backtest look-ahead gate refuses it otherwise).
- [ ] Its id: the next free `I..` after the last row of `indRegistry.json` (I54 after I53), and a `key` (snake case) no
      other entry has.
- [ ] Its Screener presentation (shape, test forms, synonyms, a 20-160 character description) from SCREENER_ONBOARDING
      §1.10 and §2.11 Step 4.

## Part A: the indicator on the beta only (lab)

All edits are on the session branch; one commit per indicator (or one per batch) is fine.

1. **The formula wrapper, first lab indicator only.** `terminal/src/calc/indicators.ts` keeps its wrapper `def` and the
   helpers a lab formula needs private (`def` at `indicators.ts:244`, `srcOf` at `:201`, `SRC` at `:274`, `Seg` at
   `:200`). Export them (`export function def`, `export const srcOf`, `export const SRC`, `export interface Seg`); the
   formulas do not change. This changes `registry_version` and both engine versions once (the file is hashed): the
   Screener re-reviews saved screens once after the deploy.
2. **The formula, in the lab module only.** `terminal/src/lab/index.ts` (never `calc/indicators.ts` while lab: that file
   is in every public build):
   ```ts
   import { DEFAULTS, F, def, SRC, srcOf, sma, stdev } from '../calc/indicators';

   // I54, Price Z-Score (lab): ...
   DEFAULTS.price_zscore = { length: 20, source: 'close' };
   F.price_zscore = def('price_zscore', ['zscore'], SRC, (B, p) => {
     const x = srcOf(B, p.source), m = sma(x, p.length), s = stdev(x, p.length);
     return { zscore: x.map((v, i) => { const mi = m[i], si = s[i]; return mi !== null && si !== null && si > 0 ? (v - mi) / si : null }) };
   });
   ```
   `DEFAULTS.<key>` is required: `def` reads it for every parameter (`indicators.ts:246`, `:250`, which throws without it). The keys of the defaults are
   the registry's parameter keys.
3. **The registry row.** Append to `terminal/src/data/indRegistry.json` (the fields of a neighbour of the same zone, e.g.
   I17 for a panel line: `id`, `cat`, `name`, `key`, `short`, `req`, `zone`, `unit`, `colorRule`, `outs`, `params`,
   `guides`, `fill`, `tip`, `info`, `display`, `position`). The file is written one value per line: keep it so with
   `json.dumps(rows, indent=0, ensure_ascii=False)`.
4. **The stage.** `apps/edge-bff/catalog/releases.json` `items`: `{"kind": "indicator", "id": "I54", "stage": "lab"}`
   (the completeness test, `test_every_registry_id_has_an_entry_and_every_entry_names_a_registry_id`, prints this line
   when it is missing).
5. **The Screener overlay.** `apps/edge-bff/screener/src/core/screener-overlay.json` `indicators.I54`: `shape`,
   `synonyms`, `description`, `default_test`, `outputs.<key>.tests` (SCREENER_ONBOARDING §2.11 Step 4; the generator
   refuses an entry that breaks a rule, `overlayProblems`).
6. **The generated registries.** Both generators import the lab module, so they see the formula:
   - `npm run registry` in `apps/backtest-worker` → `apps/edge-bff/backtest/src/core/backtest-registry.json`;
   - `npm run registry` in `apps/edge-bff/screener` → `screener/src/core/screener-registry.json` and
     `backtest/src/core/compare-lag.json` (it derives first valid bar, cost class, narrowing and caps by running the
     formula);
   - then `npm run registry:check` in both. Commit the generated files with their sources (AGENTS.md "Generated files").
7. **A unit test of the formula.** The Terminal's page tests run the public build (`@edge-lab` is `none.ts`), so they never
   see a lab formula. Add `terminal/tests/calc/<key>.test.ts` that imports `../../src/lab/index.ts` and checks the
   formula against the reference of Part 0 (known values, the first valid bar, nulls, flat and short series), as the
   parity tests of SCREENER_ONBOARDING §2.11 Step 3 do.
8. **Not yet:** the AI formula reference (`scripts/terminal_indicator_spec.py`) stays without the row while the
   indicator is lab (the AI is shared by both sites); see Part B step 6.
9. **The tests that cover what changed** (the whole suites run in CI on push):
   - edge-bff: `tests/test_releases.py`, `tests/test_3f_public_bundles.py` (the public builds hold neither the id nor the
     formula), `tests/test_3f_lab_pages.py` (the lab builds are served whole to the admin, 404 to everyone else),
     `tests/test_3f_tab_catalogs.py`, `tests/test_allow.py`, `tests/test_beta_live_site.py`, `tests/test_c3_phase2_check.py`;
     build every page first (`npm run build` in terminal, backtest, screener and the other page folders; CI does).
   - pages: `npx vitest run` in terminal (with the new formula test), screener and backtest; `npx tsc --noEmit`.
   - workers: `npm test` in `apps/backtest-worker` (the look-ahead gate `tests/lookahead.test.ts` computes every registry
     indicator, the lab one included, and fails if one has no formula in the process: `loader/register.mjs` registers the
     lab module in every process it starts) and in `apps/screener-worker`.
   - `node scripts/check_image_imports.mjs apps/backtest-worker/Dockerfile` and the Screener's.
   - Expected changes: `registry_version`, both engine versions and `screener_registry_version`. Pinned counts of 53
     indicators in the page tests do not change at the lab stage (the page tests see the public registry).
10. **Commit and push the session branch; CI green.**
11. **The beta deploy, with the user's confirmation (AGENTS.md "Deploys").** Tell the user, before asking:
    - the shared workers change for **both** sites at this deploy: they compute the new formula for anyone whose allow
      holds it, which on the live site is no one; their versions change, so saved screens are re-reviewed once;
    - nothing changes on the live site's pages.
    Then, in order (RAILWAY_CHANGELOG.md 2026-11-22 "The round's close" is a worked record):
    1. the M340 check: `python3 scripts/restart_postgres.py` (check mode): `user_runs` `edge_jobs` 0, `orc_turns` 0;
    2. the backtest-worker by CLI upload (it is not GitHub-connected): `git archive <commit>` of the COPY paths of
       `apps/backtest-worker/Dockerfile` (the lab folder included) into a scratch folder, the Dockerfile at its root,
       `railway up <folder> --path-as-root -p <project> --service backtest-worker --environment dev --detach`; wait for
       SUCCESS and read `engine_version` in its start log;
    3. fast-forward `main` to the commit: edge-bff (the beta) and the screener-worker wait for CI, then deploy; wait for
       both SUCCESS, the beta's `/version` naming the commit and `/ready` 200;
    4. records: RAILWAY_CHANGELOG.md, `verification/records/deployed_commits.json` (the beta's commit) and the ERRORS
       statuses (AGENTS.md "Findings and fixes" rule 9: `python3 scripts/record_status.py` shows 0 stale).
12. **Check it on the beta and the live site.**
    - The admin on the beta: the Terminal's indicator menu has it and draws it; the Screener's catalog lists it and a
      screen with it runs; a Backtest condition with it runs.
    - A visitor of the beta and the live site: absent from every page, catalog and answer;
      `python3 verification/edge_multiuser/live_smoke/http_smoke.py https://app.edgefinance.id`: `lab_probe_file` 404
      for both lab builds (the fixed-name file only a lab build holds, `shared/release-filter.mjs` `LAB_PROBE`).
    - **The saved layout round trip (CRIT-1), the first lab indicator only:** on the beta, as the admin, add it to the
      chart (the layout is saved for the account, on both sites); open the live site's Terminal signed in as the same
      admin (the public build, which lacks it) and change something on the chart (an indicator's eye); open the beta
      again: the lab indicator is still on the chart with its settings (`terminal/src/data/inputs.ts` `restoreList`
      parks it on the live site; `tests/test_crit1_restore_browser.py` holds the public half). Record the result in
      ERRORS M523 (CRIT-1).
13. **Tell the user** the indicator is on the beta only, how to see it, and what Part B will move.

## Part B: release to the live site, on the user's OK

Only when the user names the indicator ("I54 boleh ke live"); never on a schedule (AGENTS.md "The live site").

1. **Record the user's words** in `EXEC.md`.
2. **One commit that releases it:**
   - move `DEFAULTS.<key>` into the `DEFAULTS` object and `F.<key>` into the `F` map of `terminal/src/calc/indicators.ts`
     (`:215`, `:277`), and remove both from `terminal/src/lab/index.ts` (leave its comment and `export {};`);
   - `releases.json`: its stage `released`;
   - `npm run registry` in `apps/backtest-worker` and `apps/edge-bff/screener`, then `registry:check` in both;
   - the release pins (the page tests count the public registry, which now holds it): `terminal/tests/calc/edge.test.ts`
     (a row in its `REGISTRY` table and the count in "has the 53 registry keys"), `screener/tests/core/registry.test.ts`
     (the indicator and output counts, the shape counts of "keeps the shapes of report 6.9.1", the catalog counts),
     `screener/tests/core/metrics.test.ts` (the output count), `screener/tests/page/plain-words.test.ts` (the indicator
     count); the dry run changed exactly these (53 to 54, 76 to 77, `osc` 25 to 26);
   - the Screener golden (`screener/tests/core/golden-grammar.test.mjs`) keeps every recorded case and lets new ones in;
     record the new indicator's cases with `GOLDEN_UPDATE=1 npx vitest run tests/core/golden-grammar.test.mjs` in this
     commit;
   - `SCREENER_ONBOARDING.md` pointers into `calc/indicators.ts` move with its lines: the pointer test
     (`apps/screener-worker/tests/onboarding_pointers.test.ts`) names each line to change.
3. **The tests of Part A step 9 again**, the public builds now holding the indicator (`test_3f_public_bundles.py`).
4. **Commit and push; CI green.**
5. **The beta deploy, with the user's confirmation** (Part A step 11; the engine versions change again).
6. **Optional, asked of the user: the AI.** The AI formula reference (`scripts/terminal_indicator_spec.py`, its `I`
   table) is generated into the applied migration `20261025_102_terminal_indicator_formulas.sql`; a new row would edit
   an applied migration (forbidden). The first indicator released to the AI splits the generator: I01-I53 stay frozen in
   `20261025_102`, new rows go into a new forward migration (SCREENER_ONBOARDING §2.11 Step 2, the OPEN gotcha), applied
   on dev with the user's go and recorded in DATABASE_CHANGELOG.md.
7. **The promotion** (LIVE_PROMOTION.md §4): `python3 scripts/live_diff.py --sites`; tell the user everything that
   moves (whole commits: every commit on `main` before this one goes too); with the user's go, move `live` to the
   commit the beta runs; wait for SUCCESS and `/version`; run the three smokes (`http_smoke.py` with `lab_probe_file`
   404, `browser_smoke.cjs`, `example_smoke.py`).
8. **Records:** RAILWAY_CHANGELOG.md (both deploys), `deployed_commits.json` (both sites), ERRORS statuses (rule 9),
   LIVE_PROMOTION.md §7 (the feature notes), EXEC.md (the request done).

## Many indicators at once

A batch follows the same steps once: one lab commit for all of them (Part A), one beta deploy; each release (Part B) may
take one or several, by the user's words. The ids stay in order (I54, I55, ...); the release pins of Part B step 2
change by the number released.
