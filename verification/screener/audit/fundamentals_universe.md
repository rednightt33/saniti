# Fundamentals and universe filters: EDGE Screener audit (read-only, 2026-10-27)

Scope: the prototype's Fundamentals metrics and presets, and its universe filters, checked against the repository at `3db84ae` (origin/main) and the live market PostgreSQL (pgweb, read-only). No file in the repository was changed (`git status` clean). Raw query outputs are in `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/fundamentals_universe/`.

Labels: **FACT** (seen now, with a citation), **INFERENCE**, **PROPOSED**, **UNKNOWN**.

---

## 1. Headline

1. **FACT.** The system has no source of financial-statement fundamentals anywhere: no database, no loader, no endpoint. Of the prototype's 32 Fundamental metrics, **0 are available now**:
   - **2 can be derived** from existing data, with caveats: dividend yield and years of dividends, from `idx_event_annotation` DIVIDEND events plus price.
   - **1 is waiting for an approved plan** that has not had its go: market cap (EXEC-MCAP).
   - **The other 29 need new data:** financial statements, free float, ownership or bank ratios.
2. **FACT.** None of the 8 fundamental presets can run today. Partial runs are possible only for:
   - "High Dividend" (2 of 3 conditions derivable);
   - the Combined presets (only their technical and flow halves).
3. **FACT.** On the universe side, **sector, industry, price and average traded value (ADV) can be served now** from live data. The following have no source in the database or the repository: index membership (LQ45/IDX30/IDX80/ISSI), listing board (Main/Development/…), free float, special notation/FCA and listing date. Market cap waits for EXEC-MCAP.
4. **FACT.** `Universe_Equity_Description.Sector`/`Industry` are stored swapped: 841 of 844 rows differ from `IDX_Stock_Universe`, and the 3 equal rows are `Undefined`. The screener must read classifications from `IDX_Stock_Universe` only.

---

## 2. Where a fundamental source could be (search results)

| # | Place checked | Result | Label |
|---|---|---|---|
| 1 | Market DB tables and columns | 87 public relations (`information_schema.tables`). A column search for board, listing, notation, suspension, LQ45, IDX30, IDX80, ISSI, shares, outstanding, market cap, float, EPS, earnings, revenue, equity, dividend, book, fiscal period or report finds only `market_board` (trading board) and `shares_*` in the insider and event tables. No statement, ratio, market cap, shares-outstanding, free-float or index-membership column exists (`column_search.txt`). | FACT |
| 2 | `AI_metric_catalog` | 6 metrics, all price or flow (`broker_net_value`, `last_close`, `net_foreign_value`, `period_high`, `period_low`, `volume`) | FACT |
| 3 | `AI_formula_reference` | 246 formulas. 4 need inputs the database lacks: `CALC_066` Turnover Ratio (`shares_outstanding`), `CALC_067` Free Float Turnover (`free_float_shares`), `CALC_082` Sector Cap Weighted Return (`lagged_market_cap`), and `CALC_059` (generic equity series). The gap is already visible in the catalog. | FACT |
| 4 | `Feature_Catalog`, `AI_table_catalog`, `Table_Catalog` | 0 rows mention fundamentals, market cap or shares outstanding. No table has `data_domain` FUNDAMENTAL. | FACT |
| 5 | `apps/stockbit-*` | Stockbit endpoints in code: `/findata-view/marketdetectors/brokers`, `/order-trade/broker/activity`, `/marketdetectors/{symbol}`, `/corpaction/{slug}`, `/insider/company/majorholder`. No keystats or financial-statement endpoint is used (`stockbit_ihsg_daily.py:162,194`, `broker_import.py:129`, `stockbit_events.py:5-6`). | FACT |
| 6 | `apps/market-sql-governor/app/external.py:1-12,56,106-108` | Defines an external-provider contract that includes `data_type` FUNDAMENTAL and point-in-time rules (availability or publication timestamp, vintages). The registry is empty ("No provider is connected"). | FACT |
| 7 | `apps/market-ai-orc/app/orchestrator.py:1279` | `OUTSIDE_DATA_RULE` tells the model that fundamentals are outside the catalog | FACT |
| 8 | EXEC.md EXEC-MCAP (8152-8270, "menunggu go") | **Part A:** daily market cap from the TradingView quote session (the same websocket as prices). Fields available without an account: `market_cap_calc`, `market_cap_basic`, `total_shares_outstanding_calculated`, `total_shares_outstanding`, `float_shares_outstanding`, `regular_close`, `regular_close_time`, `currency_code`, `fundamental_currency_code`. Coverage is 820 of 844 stocks; 24 have no data. There is no history: ingest starts on day 1. **Part B:** historical market cap from quarterly or yearly share counts (`total_shares_outstanding_fq_h`, `_fy_h`), 779 stocks. Licence risk noted at EXEC.md:8190-8193. Planned columns are `market_cap`, `shares_outstanding` and `market_cap_source`; free float is **not** in the column plan (EXEC.md:8207-8211). | FACT |
| 9 | TradingView scanner | `apps/terminal-publisher/publisher.py:102,132` already POSTs to `scanner.tradingview.com/indonesia/scan` with columns `['name','logoid']` only. Whether it exposes IDX fundamentals, and under what licence, has not been checked anywhere in the repository. | FACT (use) / UNKNOWN (fundamentals) |
| 10 | `Postgres-E8GM` | Web-governor store only: `web_event_item`, `web_ask`, `web_fact` (30 days), `web_orc_result`, `web_orc_budget` (PROJECT_CONTEXT.md:14). Not a structured fundamentals source. | FACT |
| 11 | `DB2` | Only mention: RAILWAY_CHANGELOG.md:3664 (2026-09-13: "captured the pre-existing `DB2` and `db-ops-runner` resources"). Today `.railway/railway.ts` declares only `Postgres-E8GM` and `Postgres` (lines 7-9) and no DB2. Its contents are not documented. `postgres-volume-thQL` (50 GB, railway.ts:14) is declared, but its attachment was not traced. | FACT (absence) / UNKNOWN (content) |
| 12 | PLAN.md:321 | User plan of 2026-10-09 ("bukan perintah jalan") to ingest "macro, fundamental, fx, cross market…" later. No source has been chosen. | FACT |
| 13 | NEW_TABLE_ONBOARDING_PLAN.md:89,129; ERRORS Part A A2.7 | Fundamental onboarding must settle: period type, fiscal period end versus filing date, restatements as versions, currency and scale, consolidated or parent, TTM and ratios as Features, and `release_date` with as-of joins | FACT |
| 14 | xlsx spec (11 sheets) | Never mentions fundamentals, universe, sector, board or liquidity (openpyxl scan, `scripts/xlsx_grep.py`) | FACT |
| 15 | Stockbit keystats/financial API, IDX XBRL statements, OJK bank reports, KSEI ownership | Nothing in the repository references them | UNKNOWN (not invented) |

---

## 3. The prototype's Fundamentals (HTML 712-735, 848-861, 1101-1113)

**FACT** (from the HTML):
- **Synthetic data.** `makeFundamentals` (713-733) builds a random snapshot per ticker. Line 566 says "financials are deterministic samples, not market data".
- **Banks** (`industry==='Banks'`) get `der`, `roic`, `evEbitda` and `intCov` set to null, plus five bank-only metrics.
- **Financials sector** gets `grossMargin`, `curr` and `altman` set to null.
- **Snapshot only.** Every metric is "Latest reported" (848) and is evaluated only on the last bar through `I.last` (1062). There is no fundamental history.
- **Send to Backtest** marks fundamental conditions "Screen only — it chose the tickers" (1684).
- **The stock preview** shows Market cap, P/E, P/B, ROE, Div. yield, EPS growth, D/E and Piotroski (1604).

### 3.1 The 32 metrics (`FUND`, 849-854; Magic rank 855-856)

Class key:
- **DERIV**: derivable from existing data, with caveats.
- **PLAN**: needs an approved plan that has not had its go (EXEC-MCAP).
- **NEW**: needs a new data source.
- **DEC**: needs a product decision.

| # | Key | Label | Inputs a real version needs | In DB now | Class | Banks |
|---|---|---|---|---|---|---|
| 1 | cap | Market cap (IDR T) | close × shares outstanding, same split basis | No | PLAN (EXEC-MCAP A/B) + DEC (buckets) | yes |
| 2 | pe | P/E | price, EPS (TTM or FY), shares | No | NEW + DEC (TTM/FY; loss gives n/m) | yes |
| 3 | pb | P/B | price, equity attributable to parent, shares | No | NEW | yes |
| 4 | peg | PEG (P/E ÷ 3Y EPS CAGR) | P/E plus 4 fiscal years of EPS | No | NEW + DEC | yes |
| 5 | evEbitda | EV/EBITDA | market cap, debt, cash, minorities, EBITDA | No | NEW + PLAN | not meaningful (prototype null) |
| 6 | divYield | Dividend yield | trailing 12-month cash dividends per share ÷ close | Inputs yes | **DERIV** + DEC | yes |
| 7 | payout | Payout ratio | dividends ÷ net income | No (net income) | NEW | yes |
| 8 | divYears | Years of dividends | years with a cash dividend | Inputs yes | **DERIV** + DEC (consecutive or total) | yes |
| 9 | roe | ROE | net income, average equity | No | NEW | yes |
| 10 | roa | ROA | net income, average assets | No | NEW | yes |
| 11 | roic | ROIC | NOPAT, invested capital | No | NEW | no (prototype null) |
| 12 | netMargin | Net margin | net income ÷ revenue | No | NEW + DEC (bank "revenue") | definition differs |
| 13 | grossMargin | Gross margin | gross profit ÷ revenue | No | NEW | no for Financials (prototype null) |
| 14 | revG | Revenue growth YoY | 2 periods of revenue | No | NEW | definition differs |
| 15 | epsG | EPS growth YoY | 2 periods of EPS | No | NEW | yes |
| 16 | epsGq | EPS growth, latest quarter YoY | quarterly EPS; IDX interim reports are cumulative (Q1/H1/9M), so quarters must be de-cumulated (INFERENCE) | No | NEW + DEC | yes |
| 17 | epsG3y | EPS CAGR 3Y | 4 fiscal years of EPS | No | NEW | yes |
| 18 | der | Debt / equity | interest-bearing debt or total liabilities, ÷ equity | No | NEW + DEC (definition) | no (prototype null) |
| 19 | curr | Current ratio | current assets ÷ current liabilities | No | NEW | no for Financials (prototype null) |
| 20 | intCov | Interest coverage | EBIT ÷ interest expense | No | NEW | no (prototype null) |
| 21 | fcfYield | FCF yield | (CFO − capex) ÷ market cap | No | NEW + PLAN | not meaningful (INFERENCE; the prototype computes it for banks) |
| 22 | piotroski | Piotroski F-score | 2 fiscal years: NI, CFO, assets, LT debt, current assets and liabilities, shares, gross margin, revenue | No | NEW + DEC | 2 tests undefined for banks; the prototype scores banks anyway |
| 23 | altman | Altman Z | working capital, retained earnings, EBIT, market value of equity, sales, assets, liabilities | No | NEW + PLAN | no for Financials (prototype null) |
| 24 | grahamRatio | Price ÷ Graham number | √(P/E × P/B ÷ 22.5) | No | NEW | yes |
| 25 | magicRank | Magic Formula rank | cross-sectional ranks of earnings yield and ROIC | No | NEW + PLAN + DEC (see note) | Financials excluded |
| 26 | freeFloat | Free float % | float shares ÷ shares | No | NEW + DEC (the TradingView field `float_shares_outstanding` exists per EXEC.md:8167-8169 but is not in the EXEC-MCAP plan) | yes |
| 27 | foreignOwn | Foreign ownership % | ownership by investor type (a registry such as KSEI: INFERENCE, not in the repository). Broker foreign *flow* is not ownership. | No | NEW | yes |
| 28 | nim | NIM (banks) | bank income statement and earning assets | No | NEW, BANK-ONLY | 48 banks |
| 29 | npl | Gross NPL (banks) | bank loan-quality disclosure | No | NEW, BANK-ONLY + DEC (gross or net) | 48 banks |
| 30 | car | CAR (banks) | capital-adequacy disclosure (not a standard statement line) | No | NEW, BANK-ONLY | 48 banks |
| 31 | casa | CASA (banks) | deposit breakdown | No | NEW, BANK-ONLY | 48 banks |
| 32 | ldr | LDR (banks) | loans ÷ deposits; the regulator's variant may differ (INFERENCE) | No | NEW, BANK-ONLY + DEC | 48 banks |

**Magic Formula note (FACT, prototype 855).** The prototype ranks by EV/EBITDA, where Greenblatt uses EBIT/EV, and it ranks across all non-financial listings before the preset's universe filter (`capMin 5`) is applied. "Top 20" can therefore return fewer than 20 rows. The ranking universe is a product decision.

**Bank count (FACT).** `IDX_Stock_Universe.Industry='Banks'` = 48; `Sector='Financials'` = 100.

### 3.2 Derivable dividend metrics: measured

**FACT** (`corp_action.txt`):
- **Events:** `idx_event_annotation` has 5,301 DIVIDEND events, ex-dates 2009-01-20 to 2026-11-03. `amount_per_share`, `currency` (all IDR) and the cum/ex/record/pay dates are 100% filled.
- **Coverage:** of the 844 universe stocks, 568 have at least one dividend, 374 had an ex-date in the trailing 365 days to 2026-10-27, and 314 paid in 5 or more distinct calendar years.
- **Sample trailing yield:** ADRO 10.71%, ASII 8.42%, BBCA 7.78%, BBRI 11.93%, ITMG 7.02%, PTBA 3.61%, TLKM 10.43%, UNVR 14.41%.

**Caveats:**
- **FACT:** the payload field `dividend_value_adjusted` and `dividend_fiscal_year` are 0 (BBCA 2020-2026). Amounts are as announced, with no split adjustment and no fiscal-year mapping.
- **FACT:** stored prices are adjusted inconsistently. PBSA is raw across its 2026-10-14 1:2 split (845 → 384). RAJA looks adjusted across its 2026-07-16 1:5 split (920 → 875). See `split_check.txt` and EXEC.md:8244-8246.
- **FACT:** the table was first loaded 2026-10-25 (`first_seen_at`), so load time cannot serve as historical availability.
- **INFERENCE:** the sample yields include special dividends and are not validated against an independent source. Some values look high (BBCA 2026-06-17 20 IDR, 2026-08-31 25 IDR).

### 3.3 Presets (1101-1113)

| Preset | Conditions (prototype) | Runnable today | Blocked by |
|---|---|---|---|
| Graham Defensive | pe<15, grahamRatio<1, der<1, divYears>4, epsG3y>0 | No (1 of 5 derivable) | statements. der is null for banks, so banks are silently excluded. |
| Piotroski ≥7 | piotroski>6, pb<3 | No | statements |
| Magic Formula | magicRank<21; universe capMin 5, sectorsEx Financials | No (only the sector exclusion) | statements, market cap |
| Quality Compounder | roe>15, der<0.8, netMargin>10, epsG3y>8 | No | statements (banks excluded via der) |
| High Dividend | divYield>5, payout<85, divYears>4 | Partial (2 of 3) | payout needs net income |
| GARP | peg<1, epsG>15, roe>12 | No | statements |
| Deep Value | pb<1, 0≤pe≤10 | No | statements |
| Bank Quality | roe>12, npl<3, car>18, casa>60; universe industries ['Banks'] | Universe yes (48 banks), metrics no | bank ratios |
| CANSLIM-lite (Combined) | epsGq, epsG3y, roe; hi52, rs_rank | Technical half only | statements |
| Quality + Foreign Inflow | roe, der; fnet 20d, price_ma 50 | Flow and technical half only | statements |
| Value + Accumulation | pb, pe; bandar acc | Flow half only | statements |
| Minervini (Technical) | universe advMin 5 plus technical conditions | Universe part yes | (technical area) |

### 3.4 What a correct fundamental screen needs in time (PROPOSED requirements, from A2.7, Part C, `external.py` and onboarding §2.2)

**For "today" screens, each value carries:**
- the report it comes from: `fiscal_period_end`, period type (Q1/H1/9M/FY, cumulative or de-cumulated), consolidated or parent, audited or not;
- its **publication or filing date** and the `available_at` time;
- the reporting currency and scale. **FACT:** `IDX_Stock_Universe."Fundamental Currency"` = IDR for all 844 stocks. That is a TradingView attribute; whether coal miners that report in USD are converted is UNKNOWN.

**Rules for "today" screens:**
- TTM construction rules.
- The share count used for per-share values (weighted versus period-end), adjusted for splits after the period end.
- The price of the last *final* session. Price and shares must be on the same split basis.
- The UI shows "period X, published Y" and flags stale reports.

**For historical or point-in-time screens** (the prototype has none, so this is the gate for any future "screen performance" or Backtest use):
- Join on the availability (filing) date, never the period end.
- Keep vintages: a restatement must not overwrite what was known at date D.
- Shares as of D. EXEC-MCAP B gives quarterly approximations that can lag up to one quarter.
- Universe as of D.

**Facts that limit historical screens today:**
- Sector history exists only from 2026-09-28 (`IDX_Stock_Universe_History`: 851 rows, first capture 2026-09-28; the only later changes are XCID/XCIS/XSPI `0`→`Undefined` and IHSG added 2026-10-23).
- There is no index, board or notation history.
- **Survivorship:** the price table holds exactly the 845 universe tickers. A loose index scan finds 0 tickers outside the universe, so delisted stocks are absent. `Feature_03` on 2026-10-27 shows 37 Regular-board tickers missing from the universe (ETFs XB…/XS…, plus AKKU, CRAB, GTBO, TRUE, UNSP).
- Dividends are usable as of their `ex_date`. True announcement availability would need the payload field `dividend_created` (INFERENCE).

---

## 4. Universe: tables and live values

**FACT** (`columns.txt`, `universe_counts.txt`, `universe_industries.txt`):

**`IDX_Stock_Universe`** (845 rows):
- Columns: Region, Country, Company Name, Ticker (PK), Exchange, TradingView Symbol/URL, Security Type, Type Specs, Is Common Stock, TradingView Country, Currency, Fundamental Currency, ISIN, Sector, Industry, `price_feed_daily` (NULL in all 845 rows).
- 844 rows are `stock/common` IDR; 1 is `index` (IHSG).
- **No** board, index membership, listing date, notation, shares or market cap.
- Sectors (12 values): Consumer Cyclicals 139, Consumer Non-Cyclicals 122, Financials 100, Basic Materials 93, Properties & Real Estate 79, Energy 78, Infrastructures 56, Industrials 56, Technology 41, Healthcare 39, Transportation & Logistic 38, Undefined 4 (IHSG, XCID, XCIS, XSPI).
- XCID, XCIS and XSPI are DIRE real-estate funds typed `stock/common`.
- Industry: 59 distinct values including `Undefined`. AI catalog: `NOT_APPLICABLE`, "Current-state reference data; not point-in-time".

**`IDX_Stock_Universe_History`:** bitemporal (`valid_from/to`, `recorded_from/to`, `pit_valid_from/to`, `available_at`, `capture_id`, `source_provenance`), starting 2026-09-28.

**`Universe_Equity_Description`** (844 rows): Region, Market, Country, Exchange, Ticker, Company_Name, TV_Sector (20 TradingView sectors), TV_Industry, ISIN, Sector, Industry. **Sector and Industry are swapped:** BBCA `Sector=Banks`, `Industry=Financials`; 841 of 844 differ from `IDX_Stock_Universe`. The 2026-09-12 swap fix touched only `IDX_Stock_Universe` (DATABASE_CHANGELOG.md:1820-1828, ERRORS D01). The table is not in `AI_table_catalog`.

**`Feature_01_Stock_Daily`:** date, ticker, close, volume, sector, industry, returns, volatility, `volume_avg_20d` (unit Shares), highs, drawdowns. **No traded value, market cap or shares.** It has 828 tickers on 2026-10-27 and starts 2018-01-02.

**`Price_Stock_Indonesia_IDX`:**
- OHLCV, source metadata, `is_final`, 2018-01-02 to 2026-10-27, 829 rows on 2026-10-27.
- **No value, market cap or shares columns.** `AI_column_catalog.unit` is blank for close and volume (ERRORS D07 OPEN). `row_presence` = ACTIVITY_ONLY.
- 0 zero-volume rows on 2026-10-27: a session without trades has no row.

**`Feature_03_Stock_Broker_Daily`:** `total_buy_value`/`total_sell_value` per (date, ticker, market_board), 2016-01-04 to 2026-10-27. `market_board` CHECK = Regular/Nego/Tunai. These are **trading boards, not listing boards**.

**Prototype versus database names (FACT):**
- All 11 prototype sectors equal the database values exactly; the database adds `Undefined`.
- Only 14 of the 31 prototype industry labels exist in the database ("Banks" does). 17 are prototype-only: Telecommunication, Utilities, Heavy Constructions, Food & Beverage, Retailing, Real Estate, Software & IT Services, and others. The database has 58 real industries.
- Of the 94 prototype tickers, 93 are in the universe; **WIKA is not**. For the 93, sectors match for 92 (SIDO: prototype Consumer Non-Cyclicals, database Healthcare/Pharmaceuticals); industries match for 43.

### 4.1 Universe filters of the prototype (`freshUniverse` 1141, `inUniverse` 1160-1174, `QF` 1258-1263, `usec` 1265-1277, `CAPB` 1257)

| Filter | Prototype field and default | Served by existing data? | How / measured (FACT unless marked) | Class |
|---|---|---|---|---|
| Index LQ45/IDX30/IDX80/ISSI | `indexes` [] | No | No table or column; no repository reference | NEW DATA (effective-dated constituents) |
| Listing board Main/Development | `boards` [] | No | `market_board` = Regular/Nego/Tunai (trading board) must not be used | NEW DATA |
| Sector include/exclude | `sectors`, `sectorsEx` | **Yes** | `IDX_Stock_Universe."Sector"`; counts above; `Undefined` set apart (backtest-worker `terminal.ts:156` `classification`) | AVAILABLE (current state) |
| Industry | `industries` | **Yes** | `IDX_Stock_Universe."Industry"` (58 plus Undefined); the value list must come from data, not the prototype labels | AVAILABLE |
| Market cap min/max, buckets Mega ≥200T, Big 50-200, Mid 10-50, Small 1-10, Micro <1 | `capMin`/`capMax` '' | No | after EXEC-MCAP go: `market_cap` on price rows, 820 of 844 stocks; history only via Part B | PLAN + DEC (bucket thresholds are prototype values) |
| ADV ≥ Rp B over 20 sessions | `advMin` **1** | **Yes** | Σ(close×volume) over the last 20 IHSG sessions ÷ 20 (window 2026-09-30 to 2026-10-27): 840 stocks have at least 1 bar, 395 ≥ 1 B, 211 ≥ 5 B, 145 ≥ 10 B. Against `Feature_03` Regular `total_buy_value`: median ratio 1.0001 (p5 0.966, p95 1.018); 396 ≥ 1 B on Regular, **431 ≥ 1 B with Nego and Tunai included**; 48 stocks have fewer than 20 bars | AVAILABLE + DEC (board; days without a bar) |
| Price ≥ Rp | `priceMin` **50** | **Yes** | last close: 83 stocks < 50; the default universe (price ≥ 50 and ADV ≥ 1 B) = **353** stocks | AVAILABLE + DEC (stale last bar) |
| Free float ≥ % | `ffMin` 0 | No | — | NEW DATA (or extend the EXEC-MCAP plan) |
| Exclude special notation/FCA | `exclNotation` **true** | No | no source; proxy "no bar on the last session": 16 stocks on 2026-10-27 (BIKE, BSWD, IGAR, MASB, MPRO, MSIN, TFCO, TGKA, TRUK in the last 2 weeks; ADHI, CSMI, INPS, IPAC, PPGL, PTPP, XSPI older). That is a suspension or no-trade proxy, not notation (INFERENCE) | NEW DATA + DEC: as shipped, the default-on filter would be a silent no-op |
| Metric filters | `fund` [] | per metric | the indicator engine; fundamental metrics are blocked as in §3 | per metric |
| Listing age (asked; not in the prototype) | — | No exact source | proxy first price bar, censored: 384 stocks start exactly on 2018-01-02; 208 in 2018-2020, 179 in 2021-2023, 66 in 2024-2025, 7 in 2026. Broker data starts 2016-01-04 | NEW DATA / DEC |
| Security type (implicit) | — | Yes | `"Security Type"='stock'` (844); DIRE funds XCID/XCIS/XSPI are in it with sector Undefined | AVAILABLE + DEC |

**Other measured facts:**
- **Volume unit (INFERENCE, strongly supported):** price-table `volume` is in shares, not lots. Close × volume matches Feature_03 IDR value at a ratio of about 1.0 (`value_check.txt`, `adv_dist.txt`).
- **Freshness (FACT):** price, Feature_01 and Feature_03 all end 2026-10-27.

### 4.2 Coupling with Backtest (FACT, relevant to "Backtest must not break")

- `apps/terminal-publisher/publisher.py:96,416-423` publishes `ref/tickers.json.gz` from `IDX_Stock_Universe` with columns `ticker, name, type, sector, industry`. Its comment reads: "every column after ticker, name and type is a classification the backtest offers as a portfolio filter … one can be added."
- `apps/backtest-worker/src/terminal.ts:156,607-612` and `catalog.ts groupingsOf` turn **every extra column** into a portfolio-picker grouping. Any non-string value is treated as unclassified.
- **INFERENCE:** adding board or index columns to that file changes the Backtest picker. A numeric column (market cap, ADV) would appear as a grouping with every stock unclassified. Numeric screener attributes therefore need a separate reference file or endpoint.
- **INFERENCE:** sector and industry can be reused from the existing file as they are.

---

## 5. Proposals (PROPOSED: not approved; implementation needs the user's go)

- **P1, universe phase 1.**
  - Serve sector and industry from `IDX_Stock_Universe` only, with values read from data and `Undefined` counted apart.
  - Serve price ≥ from the last final close.
  - Serve ADV20 as Σ(close×volume)/20 from the price table, equal to the Regular board within ±4% at p5/p95, or exactly from Feature_03 Regular, after the user decides.
  - Use stocks only.
  - Show Index, Board, Free float, Notation and Market cap as **disabled with a "data not available yet" reason**, never as active filters that do nothing. That means changing the prototype default `exclNotation:true`.
- **P2, fundamentals phase 1.**
  - Offer only dividend yield (TTM by ex-date) and years of dividends, after validating them on a sample against an independent source and settling the split-adjustment rule.
  - Show every other Fundamental metric and preset as "requires fundamental data" (the AGENTS.md gate rules apply to any refusal text).
  - Ship "High Dividend" only as a labelled variant without payout, if the user agrees.
- **P3, market cap.** It depends on EXEC-MCAP Part A (and B for history) getting its go. The screener then reads `market_cap` from the latest final price row. Free float could be added to the same plan through `float_shares_outstanding` (user decision; same licence caveat).
- **P4, fundamental source.** The user picks the provider and accepts its licence. Onboard by NEW_TABLE_ONBOARDING_PLAN.md (§2.2 Fundamental, items 1-22, A2.7). The shape should be:
  - a statement-line table keyed `(ticker, fiscal_period_end, period_type, scope, line_item, vintage)`, with `filing_date`, `available_at`, currency, scale and source;
  - ratio Features computed as of the availability date;
  - a separate set of lines for banks (NIM, NPL, CAR, CASA, LDR).

  Not to be built before approval.
- **P5.** Keep numeric universe attributes out of `ref/tickers.json.gz`; use a new screener reference file or endpoint so the Backtest picker does not change.
- **P6.** Record the swapped columns in `Universe_Equity_Description` and the PBSA raw-split price in `ERRORS_AND_SOLUTIONS.md` when a recording task is approved. Neither is in ERRORS today: grep finds no PBSA entry, and no entry for the swapped UED columns beyond D01's fix of `IDX_Stock_Universe`.

## 6. Product decisions for the user

1. **Source and licence for fundamentals:** a TradingView field set, Stockbit, IDX statements or a vendor. Or no fundamentals in version 1.
2. **Fundamentals tab:** ship it partly (dividend only) or hide it until data exists.
3. **Market cap:** give EXEC-MCAP its go, and set the bucket thresholds (Mega ≥ 200T and so on are prototype values).
4. **ADV definition:**
   - Regular board, or all boards (431 versus 396 stocks ≥ 1 B)?
   - Days without a bar: sum ÷ 20, or the mean over traded days?
   - Window: 20 sessions?
5. **Stocks without a recent bar** (suspended or no trade): keep them or exclude them.
6. **Index, board, notation and free-float filters:** hide them, disable them with a reason, or approve new data for them.
7. **DIRE funds and `Undefined` sector rows:** include or exclude.
8. **Bank metrics:** whether to support them, and their definitions (NPL gross or net; LDR variant).
9. **Metric definitions:** TTM or FY, negative P/E, the D/E definition, Magic Formula (EBIT/EV versus EV/EBITDA, and the ranking universe), Piotroski for banks.
10. **Point-in-time scope:** "today only" fundamentals, or historical screens. Historical screens also need vintages, filing dates and delisted stocks.
11. **Dividend rule:** special dividends included or not, and split adjustment of amounts.

## 7. Scratch files

All under `/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/fundamentals_universe/`:

| File | Contents |
|---|---|
| `columns.txt`, `columns_flow.txt`, `column_search.txt` | schemas |
| `universe_counts.txt`, `universe_industries.txt`, `ued.txt`, `universe_history.txt` | universe values |
| `catalog_fund.txt`, `catalog_universe.txt` | catalogs |
| `corp_action.txt` | dividends and splits |
| `value_check.txt`, `adv_dist.txt` | traded value and ADV |
| `last_price.txt`, `first_bar.txt` | suspension and listing-age proxies |
| `split_check.txt` | PBSA and RAJA prices around their splits |
| `survivorship.txt` | price tickers versus universe |
| `board_values.txt` | trading boards and tickers outside the universe |
| `proto_*.txt`, `p_*.txt`, `d_*.txt` | prototype versus database names |
| `scripts/xlsx_grep.py` | xlsx scan |
