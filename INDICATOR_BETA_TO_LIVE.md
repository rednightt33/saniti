# A new indicator: beta only (lab), then live

A checklist an agent follows literally, step by step, for a new technical indicator of the Terminal (the `I` series of
`apps/edge-bff/terminal/src/data/indRegistry.json`) that the Terminal draws, the Screener screens and the Backtest tests.
Part A puts it on the beta only (the `lab` stage); Part B releases it to the live site when the user says so; Part C,
when the user asks for it, puts it on the live site for the admin only first (the `preview` stage), and Part B then
releases it from there.

The user, 2026-11-23: "Ok untuk indicator beta to live MD, masukan ke agents md beserta 2 docs sebelumnya agar AI bisa
refer that" and "Cabut tes penjaga lab". The plan behind it (the user, 2026-11-22): 10 to 20 new indicators built and
tested on the beta only, in the Terminal, the Screener and the Backtest; each moves to the live site only when the user
says so.

Checked by a dry run on 2026-11-23 in a copy of the repository: a lab indicator I54 (Price Z-Score) planted by Part A
steps 1-6, every page built, the suites run (green once the test fixes it found were made: the loader, the look-ahead
gate, the derived counts, the Screener overlay test), then released by Part B step 2 and run again. The deploy and
on-site steps (Part A 11-13, Part B 5-8) were not run (no deploy); the formula test of Part A step 7 is there because the
run showed that the page tests never see a lab formula. The files and lines it changed are cited.

**Read with it:**
- `SCREENER_ONBOARDING.md` §2.11 (the worked example of a released indicator, end to end: formula, registry, parity,
  overlay, tests, deploy order, records) and §3.2 (the one-page checklist). They predate the lab stage; this file says
  where the lab differs.
- `LIVE_PROMOTION.md` §3 (the lab, preview and released switches, what keeps a lab item off the live site and a
  preview item from everyone but the admin) and §4 (the steps of every promotion).
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
- **Flow indicators** (`FL..`) have their own steps: section "A lab Flow indicator" below (built 2026-11-23).
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
   helpers a lab formula needs private (`function def`, `const srcOf`, `const SRC`, `interface Seg`: find them by symbol,
   the lines move). Export them (`export function def`, `export const srcOf`, `export const SRC`, `export interface Seg`); the
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
   `DEFAULTS.<key>` is required: `def` reads it for every parameter and throws without it (the look-ahead gate now fails
   naming the indicator, ERRORS M549). The keys of the defaults are
   the registry's parameter keys. The third argument of `def` is the data the formula needs: `SRC` for a `source`
   parameter, `() => 'V'` for volume, `() => 'HLC'` (or `p => 'HLC' + needSrc(p.source)`) for a range; read a neighbour.
3. **The registry row.** Append to `terminal/src/data/indRegistry.json` (the fields of a neighbour of the same zone, e.g.
   I17 for a panel line: `id`, `cat`, `name`, `key`, `short`, `req`, `zone`, `unit`, `colorRule`, `outs`, `params`,
   `guides`, `fill`, `tip`, `info`, `display`, `position`). The file is written one value per line: keep it so with
   `json.dumps(rows, indent=0, ensure_ascii=False)`.
   To draw an indicator as its source draws it (EXEC-PINE-INDICATORS, 2026-11-23; `terminal/src/app/indicators.ts` reads
   them, nothing is coded per indicator): per output `colors` [main, second], `alpha` (0..1), `step` (a stepped line),
   `join` (the line drawn across days without a value, as Pine's `style_line` and `style_stepline` do; ERRORS M557),
   `palette` with `paletteFrom` (a line coloured per bar by another output's index: Alpha KAMA, Alpha Extract), `marker`
   {shape, position, text, size, on, style, textColor} (a mark on the price, or with `on` at another output's value;
   `style` "label" draws Pine's `label.style_label_up/down`, a filled box with a pointer and `textColor` text, as the
   TradingView screenshots of Alpha Extract and Alpha Divergence show); per row
   `guideStyle` {color, width, style}, `fills` [{a, b, color, color2?, opacity}] (areas between two outputs, two colours
   with `color2`) and `layers` [{k, label, on}] with a drawing in `calc/indicators.ts` `DRAWINGS` (registered by the lab
   module: labels on earlier candles, segments, a level ray, background ranges; never an output of F, so the Screener,
   the Backtest and the look-ahead gate never read a mark placed in hindsight). An output coded in categories carries
   `categories` [{value, key, label}]; the Screener's forms `state_category` and `event_category_change` then offer "is
   one of" and "changed from -> to within N" (SCREENER_ONBOARDING 2.11.1, the category forms).
   The Style tab's colour box (`app/colorPicker.ts`, UD32) offers opacity, thickness and line style per output only on
   an indicator with `zone` "overlay" (UD31, `lineOptions`); a panel indicator's box holds the colours only. A
   `DRAWINGS` mark with `style` "label" is drawn the same way as a label marker.
4. **The stage.** `apps/edge-bff/catalog/releases.json` `items`: `{"kind": "indicator", "id": "I54", "stage": "lab"}`
   (the completeness test, `test_every_registry_id_has_an_entry_and_every_entry_names_a_registry_id`, prints this line
   when it is missing).
5. **The Screener overlay.** `apps/edge-bff/screener/src/core/screener-overlay.json` `indicators.I54`: `shape`,
   `synonyms`, `description`, `default_test`, `outputs.<key>.tests` (SCREENER_ONBOARDING §2.11 Step 4; the generator
   refuses an entry that breaks a rule, `overlayProblems`). The file is written with `json.dumps(doc, indent=2,
   ensure_ascii=False)` and a final newline (the registry file above has `indent=0` and none).
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
10. **Commit and push the session branch; read its CI runs** (the whole suites; a red run is fixed before step 11).
11. **The beta deploy, with the user's confirmation (AGENTS.md "Deploys").** Tell the user, before asking:
    - the shared workers change for **both** sites at this deploy: they compute the new formula for anyone whose allow
      holds it, which on the live site is no one; their versions change, so saved screens are re-reviewed once;
    - nothing changes on the live site's pages.
    Then, in order (RAILWAY_CHANGELOG.md 2026-11-22 "The round's close" is a worked record):
    1. the M340 check: `python3 scripts/restart_postgres.py` (check mode): `user_runs` `edge_jobs` 0, `orc_turns` 0;
    2. the backtest-worker by CLI upload (it is not GitHub-connected), from a commit whose `Backtest look-ahead gate`
       run is green (`apps/backtest-worker/README.md`, Deploy; record the run ID): `git archive <commit>` of the COPY paths of
       `apps/backtest-worker/Dockerfile` (the lab folder included) into a scratch folder, the Dockerfile at its root,
       `railway up <folder> --path-as-root -p <project> --service backtest-worker --environment dev --detach`; wait for
       SUCCESS and read `engine_version` in its start log;
    3. fast-forward `main` to the commit: edge-bff (the beta) and the screener-worker deploy at once (Wait for CI is off
       since 2026-11-23, AGENTS.md "Deploys"): read that commit's runs to their end and tell the user at once when one is
       red, with a proposal (a fix or the rollback RAILWAY_CHANGELOG names); wait for both SUCCESS, the beta's `/version` naming the commit and `/ready` 200;
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

**The tripwire in Part A** (check of steps 2-3, F7): a lab formula moves both engine versions, so the Backtest tripwire
(`npm run tripwire` in `apps/edge-bff/screener`, not in CI) is recorded in the lab commit with the user's words
(`--record --exec <section> --decision "<words>" --note "<what>"`), as Part B step 2 records it at release.

## Part B: release to the live site, on the user's OK

Only when the user names the indicator ("I54 boleh ke live"); never on a schedule (AGENTS.md "The live site").

1. **Record the user's words** in `EXEC.md`.
2. **One commit that releases it:**
   - move `DEFAULTS.<key>` into the `DEFAULTS` object and `F.<key>` into the `F` map of `terminal/src/calc/indicators.ts`
     (the `DEFAULTS` object and the `F` map), and remove both from `terminal/src/lab/index.ts` (leave its comment and `export {};`);
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
   - the formula's unit test (Part A step 7) now imports `calc/indicators.ts` only;
   - the Feature 04 oracle: a new indicator Feature 04 does not store gets an `ORACLE_NOTES` line
     (`scripts/terminal_indicator_spec.py`) and `scripts/screener/parity_f04.py --write` (SCREENER_ONBOARDING §2.11 Step 4);
   - the Backtest tripwire (`npm run tripwire` in `apps/edge-bff/screener`; not in CI) flags any registry or worker
     change: record its baseline with the user's go in the same commit (`--record --exec EXEC-MU-ACCOUNTS --decision
     "<the user's words>" --note "<what changed>"`, `scripts/screener/check_backtest_untouched.mjs`). Part A records it
     too.
3. **The tests of Part A step 9 again**, the public builds now holding the indicator (`test_3f_public_bundles.py`).
4. **Commit and push; read its CI runs** (Part A step 10).
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

## A lab Flow indicator (FL..)

Built 2026-11-23, step 3 of the user's sequence ("Satu batasan yang masih ada: indikator Flow (FL) baru belum bisa
dijadikan lab ... Kalau Anda mau menambah FL khusus beta, bagian itu perlu dibangun dulu"; "Oke, mulai"). Proven by a dry
run in a copy of the repository: a lab FL53 entered through the spreadsheet and the generator, its formula registered
from the lab module with the shared building blocks, every page built (FL53 in no public file, in the Terminal's and
the Backtest's lab builds), the Terminal (1087), Screener core (412), screener-worker, backtest-worker look-ahead, pit
and grammar suites, the edge-bff release and proof-build tests and the generator checks run (ERRORS M551); not
checked: a browser drawing the lab FL53 on the lab Terminal (its lab bundle holds the registration). Part A's
steps 9-13 (tests, commit, CI, the deploys, the check on the beta) and Parts B and C apply as for a technical
indicator; these replace its steps 1-8:

1. **The registry entry, from the spreadsheet's builder.** Its id is the next free `FL` after the registry's last
   (`tests/test_releases.py` `test_the_flow_registry_is_numbered_without_gaps`); release in id order where the user
   allows. The spreadsheet `FLOW_INDICATORS_SPEC.xlsx` is generated: add the indicator to
   `verification/terminal_api/flow_indicators/build_spec_workbook.py` (its row of `Ringkasan`: id, name, place, unit,
   frequency; its parameter rows), rebuild with `python3 -I build_spec_workbook.py user_input_20261030.xlsx
   FLOW_INDICATORS_SPEC.xlsx` in that folder (`scripts/tests/test_registries_current.py`
   `test_flow_spec_workbook_is_current` refuses a hand edit of the workbook), then `python3 scripts/build_flow_registry.py`
   (it sorts by number). In `scripts/build_flow_registry.py`: its plain tip in `PLAIN`; its menu family is the name's
   head before ` · ` looked up in `FAMILY_OF` (`Share`, `Transaction Size`, `Transactions`, `Activity Spike`,
   `Concentration HHI`, `Concentration Top-N`, `Top Brokers`, `Buy VWAP`, `Sell VWAP`, `Implied Cost`, `Flow Ratio`, the
   `Net Flow` names; any other head is `Other`); each spreadsheet word must be in `LABELS`, `OPTIONS`, `UNIT` or `PLACE`
   (the script names the map and the fix when one is not); an output other than `value` is named in `outputs()`. An
   indicator the script builds itself goes in `extra_indicators`. None of these files is in a page build.
2. **Its stage:** `apps/edge-bff/catalog/releases.json` `{"kind": "flow_indicator", "id": "FL53", "stage": "lab"}`.
3. **Its formula, in the lab module only:** `apps/edge-bff/terminal/src/lab/index.ts`,
   `registerFlow('FL53', (c, p) => ...)` built from `flowKit` (`calc/flow.ts`: the call's broker grid, the window,
   the Top-N cohort and its sums, the ratio and null rules). A block it needs that the kit lacks is added to `flowKit`
   in the same commit; never copy one. `registerFlow` refuses an id that has a formula. What a block returns is shared
   with the released formulas: read it, never change it (the cohort is handed out as a copy).
   Its unit test: `terminal/tests/calc/<id>.test.ts` imports `../../src/lab/index.ts` and checks `computeFlow` against
   values computed by hand (as `flow_register.test.ts` does for FL97); the page tests never load the lab module. At
   release, the Flow oracle (`verification/terminal_api/flow_indicators/oracle/`) is extended or the release says why not.
4. **Its Screener output kinds:** `apps/edge-bff/screener/src/core/flow-kinds.json` `indicators.FL53` (each output's
   kind letter, `adv_floor`). The generator refuses an output without one.
5. **The generated registries:** `npm run registry` in `apps/edge-bff/screener` (it imports the lab module through the
   loader, so it computes the formula), then `registry:check`; `npm run registry:check` in `apps/backtest-worker`
   (technical indicators only: no change).
6. **No id in shipped code.** A table keyed by FL id in a public file (`SINGLE_SECURITY`, `MENU_HIDDEN`, the
   point-in-time list) would name the lab item: `test_an_item_the_shipped_code_names_is_never_lab` refuses it and the
   bundle scan finds it. A lab Flow indicator that needs such a row cannot be lab today: the tables would first be
   derived from the registry entry (EXEC-MU-ACCOUNTS, Carried open parts, "A lab Flow indicator that needs a per-id
   row"), which the user decides.
7. **The gates:** the look-ahead gate computes it with every option and its numbers at their minimum, three times the
   default and the maximum, and fails when a registry Flow indicator has no formula or only nulls at its defaults
   (`apps/backtest-worker/tests/lookahead.test.ts`); the screener-worker's catalog count is derived from the generated
   registry (`tests/flow.test.ts`). **The tripwire:** the engine versions hash the lab module and `flowRegistry.json`, so
   record its baseline in the lab commit with the user's words (`npm run tripwire` in `apps/edge-bff/screener`; `--record
   --exec <section> --decision "<words>" --note "<what>"`, `scripts/screener/check_backtest_untouched.mjs`). Part A step 9's
   expected changes for a Flow indicator: both engine versions and `screener_registry_version`; `registry_version` stays.
8. **Its release** (Part B) or preview (Part C) moves the formula into `calc/flow.ts` `FLOW` and out of the lab module;
   the page tests then compute it (`terminal/tests/calc/flow.test.ts` "registry"). No Flow count is pinned in the page
   tests (check of steps 2-3, P2: `terminal/tests/data/pane_filters.test.ts` holds the final proposal's counts for
   FL01-FL52 and a rule for every later one, `flow.test.ts` the order, `screener/tests/core/catalog.test.ts` follows the
   generated registry). Preview: the rule of Part C step 0.

## Part C: on the live site for the admin only (preview), on the user's OK

The user, 2026-11-23: "ada indikator baru di main --> promote ke live, tapi saya mau promote ke live hanya admin saja
yang bisa lihat, user paid tidak bisa lihat" (EXEC-MU-ACCOUNTS "A preview release stage"; LIVE_PROMOTION.md §3
"Preview"). Only when the user names the indicator for it ("I54 preview ke live"). What preview holds and what it does
not: the admin (`*`, or an account given its id) sees and runs it on both sites; paid, free and guest accounts never see
it, nor an account whose family value is `{"all": true}` (UD28) (the menus leave it out, the catalogs do not list it,
the workers refuse it); its definition and formula are in the public page files, so anyone reading those files can see
them. A formula that must stay private stays lab. The live site must run a commit at or after `fb4a5c3c` (the code of
the preview stage; LIVE_PROMOTION.md §7), so the first preview item's promotion moves that code too; LIVE_PROMOTION.md
§4's first table names this path.

0. **Can it be preview?** an indicator or a Flow indicator may be preview only when no shipped code but its own formula
   definition names or computes it (`tests/test_releases.py` `test_an_item_the_shipped_code_names_is_never_lab`, its
   `FORMULA_HOME` rule): 36 of today's 53 indicators and 20 of the 52 Flow indicators qualify today; a new one qualifies
   when only its formula names it (checked on disk 2026-11-23 with I53 and FL22 at preview: every
   suite named below green). An item that another formula, a built-in, a worker or a page list names or computes stays lab or
   released, or that code moves first.
1. **Record the user's words** in `EXEC.md`.
2. **One commit that moves it to preview:** every line of Part B step 2 (the formula into `calc/indicators.ts` or
   `calc/flow.ts` and out of `src/lab/index.ts`, the registries, the release pins, the golden, the pointers, the oracle,
   the tripwire record), with its `releases.json` stage `preview` instead of `released`. The public builds now hold it,
   marked `release: 'preview'`; `terminal/tests/calc/public_formulas.test.ts` fails if its formula is still lab-only.
   A stored example (`/api/v1/examples`) that names it is withheld from visitors until it is captured again.
3. **The tests of Part A step 9**, `tests/test_releases.py` (the shipped-code rule above), `tests/test_preview_stage.py`,
   `tests/test_3f_tab_catalogs.py` and `tests/test_3f_public_bundles.py`.
4. **Commit and push; read its CI runs** (Part A step 10).
5. **The beta deploy, with the user's confirmation** (Part A step 11).
6. **The promotion** (Part B step 7): `scripts/live_diff.py --sites` names it under "preview (on the live site for the
   admin only, ...)"; tell the user that, and everything else that moves. After the move, as the admin on the live
   site: the indicator is in the Terminal's menu and computes; as a paid test account (step 9's window accounts, or
   one the admin gives Paid on the beta's admin page): it is neither in the menu nor in the Screener's or Backtest's
   lists, and `/api/v1/catalog/indicator` does not list it.
7. **Records** (Part B step 8).

**From preview to released** (Part B, when the user says so): the formula is already public, so Part B step 2 is only
its `releases.json` stage `released` and the tripwire record; then Part B steps 3-8.

## Notes

- This guide's order (the backtest-worker first, then `main`) replaces SCREENER_ONBOARDING §2.11 Step 6.1-6.2.
- The lab build goes to the admin on the beta only: `app/principal.py` `Auth.lab_admin`.
- A fix of a lab formula only (no registry row changed) moves both engine versions but not `registry_version` or the
  Screener's `formula_version`: the registry hashes `indRegistry.json` and `calc/indicators.ts`, not the lab module.
- Other kinds (tests/test_releases.py `LAB_KIND_HELD`): a Screener metric and a preset may be lab (data the workers read
  whole); a Flow indicator may be lab since 2026-11-23 (section "A lab Flow indicator"); a candle pattern may not yet: a
  lab candle needs its pair and mirror (`candles.ts`), a `CASES` entry and the count pins of `lookahead.test.ts`,
  `candles.test.ts` and `operators.test.ts` made derived, and a dry run like the indicator's (EXEC-MU-ACCOUNTS, Carried
  open parts). Preview (Part C): an indicator or a Flow indicator may be preview only when no shipped code but its own
  formula definition names or computes it (`tests/test_releases.py` `test_an_item_the_shipped_code_names_is_never_lab`,
  its `FORMULA_HOME` rule): 36 of today's 53 indicators and 20 of the 52 Flow indicators qualify today; a new one
  qualifies when only its formula names it; candle patterns, most Screener metrics and presets qualify
  as data. Its formula is public at that stage.

## Many indicators at once

A batch follows the same steps once: one lab commit for all of them (Part A), one beta deploy; each release (Part B) may
take one or several, by the user's words. The ids stay in order (I54, I55, ...); the release pins of Part B step 2
change by the number released.
