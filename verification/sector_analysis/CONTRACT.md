# Sector Analysis: the build contract (EXEC-SECTOR-ANALYSIS, 2026-11-26)

The interface between the four build parts: the database (S1), the publisher (S2), the gateway and shell (S3) and the
page (S4). The user's decisions are in `EXEC.md` EXEC-SECTOR-ANALYSIS (UD66 A-J, UD67 1A 2A); the design is the user's
final prototype, audited in `final/click_inventory.md` and `final/formulas.md` (the formulas this contract keeps unless
a decision below changes them). A change to this contract is made here first and told to every part.

## 1. Decisions that shape the data

| Id | Decision | In the build |
|---|---|---|
| A1 | the final HTML is the page | 5 tabs (Overview, Relative Strength, Rotation, Pair Matrix, Breadth), the cards the prototype draws; benchmark IHSG (LQ45 also in Beta & Correlation) |
| A (UD67 2A) | neutral names | "Rotation map" (not "Relative Rotation Graph"/"RRG"), axes "Relative strength" and "Momentum" (not "RS-Ratio"/"RS-Momentum"); the formula stays the prototype's (D11), called our own |
| B | real data everywhere | no seeded, random or illustrative value is shown; a value the data cannot give is "—" with its reason |
| C1 | no EMA20 | breadth and stock status use EMA50 and EMA200 only; every EMA20 column, option and label is removed |
| D1 | weights = 20-day average traded value, pluggable | every weight (industry index, treemap area, top-N by size, dot size) comes from ONE weight basis, named in the files (`weight_basis`, `weight_label`); switching to market cap = a new basis, no page change |
| E | periods as the Overview | sessions: 1D 1, 3D 3, 1W 5, 2W 10, 1M 20, 3M 60, 6M 120, 1Y 252; YTD from the last session of the previous calendar year (`apps/edge-bff/overview/src/model.ts` `periodStart`); weekly steps = 5 sessions; "4W/8W/12W" = 20/40/60; a Custom range is capped and anchored as the Overview's Custom (F1) |
| F | tab released on `main` | `apps/edge-bff/catalog/releases.json` tab `sector`, stage `released`; the live site only when `live` moves (the user asks first) |
| G (UD67 1A) | "Open in Terminal" | opens the Terminal on the selected sector's index ticker (e.g. IDXFINANCE), IHSG when no sector is selected; a stock row or dot opens that stock |
| H | hidden cards removed | snCard, the legacy Sector Performance and Sector stocks cards, rsC, pmA, pmB, brM, brC, brB and their code; no CSV button |
| I | 20 dates | the date picker lists the 20 newest market dates, as the Overview |
| J | who sees what | paid: everything; free and guests (later, when the live site gets it): the example of one day as the Overview's, the 5 tabs switchable, any other click shows the same sign-in/upgrade prompt as the Overview's example |

## 2. Database (S1): `Feature_08_Group_Daily`

One row per market date and group. Groups: `MARKET` (one row, `group_name` = the market ticker from
`Feature_Index_Entity` entity_kind MARKET, today IHSG: every common stock, "Undefined" sector included), `SECTOR` (the 11
IDX sectors of `Feature_Index_Entity` entity_kind SECTOR, members by `IDX_Stock_Universe."Sector"`), `INDUSTRY` (every
`IDX_Stock_Universe."Industry"` except 'Undefined', with its sector). Membership is the current classification (as the
Overview and Feature 01); point-in-time membership is out of scope (said in the formulas document).

| Column | Meaning |
|---|---|
| `date`, `group_kind`, `group_name`, `sector` | the key (`date`, `group_kind`, `group_name`); `sector` = the industry's sector, the sector itself, NULL for MARKET |
| `members` | common stocks of the group with a final daily close on `date` |
| `n_ema50`, `above_ema50` | members with `ema_50` not NULL; of them, `close > ema_50` (Feature 04, timeframe Daily) |
| `n_ema200`, `above_ema200` | the same for `ema_200` |
| `adv_1d`, `unch_1d`, `dec_1d` | members whose close is above / equal to / below their previous final close |
| `weight_basis`, `weight_sum` | the basis name (`adv20_value` today) and the sum of the members' weights on `date` |
| `ret_1d_w` | weighted daily return in %: Σ w_i(t−1)·r_i(t) / Σ w_i(t−1) over members with both closes (weights of the previous date, so a date's return never uses that date's own weights) |
| `index_level` | chain-linked level: the group's first date = 100, then level(t) = level(t−1)·(1 + ret_1d_w/100); NULL when a date has no member with both closes (the level carries) |
| `calculation_version`, `calculated_at` | as the other Feature tables |

- The weight basis is one SQL function, `public.feature_08_weight(date)` → (ticker, weight), which today returns
  `public.overview_stock_size(date)` (the Overview's 20-day average traded value). Market cap later = a new version of this
  function and `weight_basis`, then a recompute.
- Breadth must equal the Overview's market breadth on the MARKET row (`apps/terminal-publisher/overview.py` `BREADTH_SQL`):
  the same counts, the same NULL handling.
- `public.refresh_feature_08_day(date)` computes one date (idempotent upsert); it is called by `feature-04-worker` when it
  finalizes a daily run (`finalize_runs`), for the finalized session, after Feature 04 of that date is complete. A
  backfill job fills every market date from 2021-01-25 (the sector indexes' first date), one date per statement (a
  large write: AGENTS.md "Postgres memory after large updates").
- Catalog: Table_Catalog, Column_Catalog, Feature_Catalog (formula, interpretation, recommended use, misuse warning,
  validation evidence), `scripts/audit_feature_catalog_semantics.py`; EXPLAIN (ANALYZE, BUFFERS) of the publisher's and
  the refresh's queries; grants: SELECT to `terminal_market_reader` and `pgweb_reader`, EXECUTE of the refresh to the
  feature-04-worker's role.

## 3. Publisher (S2): family `sector/`

Gzip JSON files, content-keyed and indexed in state.json `sector` exactly as the Overview's (`overview.py` header). Every
list ordered here, so equal tables give equal bytes. A file is rewritten only when its content changes; history is
carried from the previous publication (as `overview-stocks` and the Overview breadth).

### 3.1 `sector-meta` (schema 1)
```
{ "schema": 1, "market": "IHSG", "benchmarks": ["IHSG", "LQ45"],
  "weight_basis": "adv20_value", "weight_label": "20-day average traded value",
  "periods": {"1D":1,"3D":3,"1W":5,"2W":10,"1M":20,"3M":60,"6M":120,"1Y":252},
  "sectors": [{"name": "Financials", "short": "Financials", "index": "IDXFINANCE"}, ...11, ordered by name],
  "industries": [{"name": "Banks", "sector": "Financials"}, ...],
  "stocks": {"ticker": [...], "name": [...], "sector": [... "Other" for Undefined], "industry": [... null for Undefined]},
  "dates": ["2026-10-30", ... 20 newest market dates, oldest first],
  "prices_through": "YYYY-MM-DD", "breadth_through": "YYYY-MM-DD" }
```
### 3.2 `sector-series` (schema 1)
The 300 newest market dates (oldest first), the same dates as the Overview series.
```
{ "schema": 1, "dates": [...300],
  "index": {"IHSG": [close...], "LQ45": [...]},
  "sector": {"Financials": [close of IDXFINANCE...], ...11},
  "breadth": {"IHSG": {"members":[...],"n50":[...],"a50":[...],"n200":[...],"a200":[...],"adv":[...],"unch":[...],"dec":[...]},
              "Financials": {...}, ...11},
  "industry": {"Banks": {"level": [...], "members": [...]}, ...} }
```
### 3.3 `sector-day-YYYY-MM-DD` (schema 1), one per date of `meta.dates`
Rows aligned by `i` (the index in `meta.stocks`); every common stock with a final close on the date.
```
{ "schema": 1, "date": "...", "prior_date": "...",
  "stocks": {"i": [...], "close": [...], "volume": [...], "r1d": [...], "r5d": [...], "r1m": [...], "r3m": [...],
             "weight": [...], "above_ema50": [1|0|null], "above_ema200": [...],
             "d_ema50": [% distance, close/ema_50 − 1, ×100], "d_ema200": [...],
             "days50": [sessions in the current status vs EMA50, ≥1], "days200": [...],
             "since50": ["YYYY-MM-DD" first session of that status], "since200": [...]} }
```
Returns use the Overview's sessions (1D 1, 1W 5, 1M 20, 3M 60) from final closes. Days in status are counted back over
Feature 04 rows (capped at 300 sessions, then shown as "300+").
### 3.4 `sector-stocks-<INDEX>` (schema 1), one per sector (e.g. `sector-stocks-IDXFINANCE`)
Read by the page only when that sector's stock lines or stock β/correlation are opened.
```
{ "schema": 1, "sector": "Financials", "dates": [...300, as sector-series], "ticker": [...], "close": [[300 closes], ...] }
```
### 3.5 Example (J)
The example files for visitors are made as the Overview's (`apps/terminal-publisher/examples.py`,
`apps/edge-bff/app/examples.py` TABS): one market date, the same file shapes.

## 4. Gateway and shell (S3)
- terminal-api: family `sector` presigned for the EDGE gateway key, as `overview`.
- edge-bff: `/api/v1/sector/index` and `/api/v1/sector/file/<name>?sha=` as the Overview's routes (immutable cache by
  sha); capability `sector` in the plan catalog (paid plans: on; free and guests: the example, J); tab `sector` in
  `catalog/releases.json` (released, F); the rail entry after Overview (icon, label "Sector Analysis"), route
  `/sector`, the page app `sector-app`; wording in `static/edge-labels.js`; every test that lists tabs or capabilities
  updated (`tests/test_live_switch.py`, `test_releases.py`, example docs).
- Browser storage keys of the page are registered in `apps/edge-bff/shared/edge-session.ts` STORAGE (AGENTS.md).

## 5. Page (S4): `apps/edge-bff/sector` (Vite, TypeScript) built into `static/sector-app`
- Port of the final prototype's cards and interactions with the files of section 3; the decisions of section 1; the
  defects of `final/click_inventory.md` (21 + 8) fixed, the phone width (390 px) included; the EDGE design system
  (`.claude/skills/edge-design-system/`); tests with vitest on fixtures in the contract's shapes.
- The page computes in the browser what depends on the user's choice (returns over a period, ranks, the rotation map,
  pair spreads, correlations, β from closes, A/U/D of a horizon, industry aggregates of the day); it never queries the
  database.
- Downloads: index, meta, series and the chosen day on open; `sector-stocks-<INDEX>` only when a sector's stock lines
  or stock β window is opened; every file cached by its sha.
