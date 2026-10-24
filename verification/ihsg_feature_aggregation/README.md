# IHSG Features 2–6 — pre-implementation inspection

Recorded 2026-10-24 WIB. Source-code inspection and proposed implementation contract only:
no migration, data load, application implementation, release or deployment was executed.
The exact inspected feature-branch revision is in `inspection_manifest.json`; it does not
assert what is currently on remote main or deployed.

## User decisions

- Aggregate all source tickers per date for Features 2, 3, 5 and 6, preserving broker,
  investor type and market-board dimensions wherever the feature grain requires them.
- “leave as null untuk ini: feature 3: broker_concentration_hhi”: aggregate IHSG HHI is
  deliberately NULL. It is not a calculation failure or a reason to retry. Ordinary-stock HHI remains unchanged.
- “untuk feature 4 kolom asset type buat jadi 'index'”: resolve indices from universe
  Security Type, not a hardcoded IHSG exception. Stock -> equity; index -> index; fixed-income universe -> bonds.
- Latest request: “lakukan inspeksi terhadap script pembuatan setiap kolomnya. Ensure this is di note
  sebelum masuk implementation phase.” This authorizes the inspection/documentation, not implementation.

`COLUMN_INSPECTION.md` and `column_inspection.csv` cover every column, including identity/metadata:
**221 unique entries** = F02 38 + F03 24 + F04 57 + F05 15 + F06 87.
Each entry separates existing formula, NULL/history rules, source path and planned aggregate treatment.
“Bisa/bersyarat” is feasibility, not a claim the existing scripts already implement IHSG aggregation.

## Calculation sources inspected

| Feature | Actual writer / formula | Validation / definition sources inspected |
|---|---|---|
| 2 | `scripts/backfill_feature_02_v2.py`: STAGE_YEAR, INSERT_TICKER | Schema migration 20260914_034, canonical cutover 20260914_043; dedicated Feature 2 docs |
| 3 | `refresh_feature_03_stock_broker_daily` in `20260914_047_define_feature_03_investor_type_v2.sql` | Schema 20260913_009; dedicated Feature 3 v2 docs |
| 4 | `features/feature04/engine.py`, `swing.py`, `incremental.py` | `specs.py`, pipeline/backfill, worker source and checkpoint/bootstrap paths |
| 5 | `refresh_feature_05` in `20261022_002_create_feature_05_foreign_domestic_broker_detail.sql` | Catalog generator f05_columns; `apps/feature-05-06-job/job.py` |
| 6 | `refresh_feature_06` in `20261022_003_create_feature_06_foreign_domestic.sql` | Catalog generator f06_columns; independent `scripts/check_feature_06_sample.py`; job |

Additional dependencies inspected: Feature04 migrations 20261011_006, 20261011_008,
20261012_003 and 20261012_004; Feature05/06 onboarding 20261023_004; Telegram monitor and trigger.
Applied migrations are historical evidence; implementation must add forward migrations.
Old Feature 2 Markdown still describes Feature 3 foreign/domestic as broker-domicile based.
The newer Feature 3 v2 SQL and dedicated v2 documentation take precedence: source investor identity
sets Foreign/Domestic, while broker classifications use the current broker profile.

## Findings and implementation implications

### Feature 2

Current staging groups Date × Symbol × Broker × Investor Type × Market Board. A new aggregate path
must sum additive raw fields without the Symbol dimension, assign the aggregate identity separately,
and then run the existing rolling formulas on that series. Do not fabricate IHSG rows in raw
IDX_Broker_Summary and do not sum already-calculated ratios, ranks, percentiles or day counts.

Calendar = observed aggregate source sessions across all boards. Missing broker/type/board on a known
session contributes zero to rolling windows, without manufacturing output rows. An entirely missing
source date is not silently made into a zero-trading day. Twenty-/sixty-session windows and the preceding
252 complete rolling values remain required. Z-scores/percentiles compare own series history, excluding today.
Market-wide broker net can cancel across securities: buy/sell days must be recounted from that net,
not added from each stock's buy/sell-day counts. Current broker classifications are not point-in-time history.

### Feature 3

First sum Foreign/Domestic activity per broker for counts/rankings; keep source investor identity
for foreign/domestic net flow. Active zero-net brokers remain active when gross activity exists.
Top buyer/seller ties use ascending broker code. Profiles missing from the join remain in totals,
breadth and rankings but do not enter classified sums; do not claim those sums cover unknown profiles.

Existing HHI is mathematically computable among same-day brokers; no cross-ticker benchmark is needed.
The user nevertheless requires NULL for the new aggregate. Apply this policy on every future refresh,
not just initial load, and teach completeness checks/catalogs that this NULL is intentional.
Do not change ordinary-stock HHI or create retries because aggregate HHI is NULL.

### Features 5 and 6: frequency completeness

Feature 5 currently copies one source row; aggregation needs explicit daily SUM by broker/type/board.
Feature 6 calculates daily, cumulative, rolling, persistence, strength and historical statistics from it.
The formulas remain unchanged after changing the input grain, subject to missing-input rules below.

**Existing frequency code does not enforce completeness for a mixed aggregate.** It uses SQL SUM,
count(buy_freq), and COALESCE based on the presence of some frequency. SUM ignores NULL; a mixture
of known and unknown frequencies can therefore look like a total, or an absent subset can become zero.
Rolling SUM can also skip NULL sessions. The proposed aggregate path must track completeness separately
for buy/sell and investor type, and require complete input over every window used by an output.
Propagate unknown frequency from Feature 5 through Feature 6; never replace unknown by zero.
Value-per-frequency must have matching numerator/denominator coverage. Existing sample validators
mirror present partial-frequency handling and require additional independent aggregate checks.

Proposed gap semantics: compute each source ticker/date/board balance gap before aggregation, then
BOOL_OR those flags. Opposite source imbalances must not cancel and hide missing brokers. Feature 6
inherits that flag. This is an explicit proposed aggregate policy, not a behavior already implemented.
Arithmetic matching alone cannot prove source completeness.

Cumulative net requires initial history or a trusted cumulative anchor. One isolated day cannot represent
cumulative net since 2016. Existing F06 incremental refresh reads 312 prior sessions and continues an
older stored cumulative anchor. First aggregate initialization needs its history; routine updates should
read bounded context and propagate affected outputs, not rebuild unrelated ticker histories.

### Feature 4: index classification across dependencies

Its 57 columns contain 51 analytical/price/state outputs plus six identity/metadata fields. All numerical
formulas remain based on actual index OHLC from the universe TradingView mapping (IDX:COMPOSITE for
IHSG), never summed/averaged constituent OHLC. Index close/levels are index points, not IDR. Volume
missing from the provider remains NULL; none of the analytical output formulas needs volume.

Preserve SMA/EMA seeds, Wilder RSI/ATR/ADX, MACD and Bollinger parameters. All 25 TA-Lib patterns
retain pinned-library lookbacks/default parameters and native signed codes (zero = available non-detection).
Strict inside bar remains high[t]<high[t-1] and low[t]>low[t-1]. SMI retains 14/5/5, first-input EMA
seeding and threshold ±40. Swing block order and state are retained; break_swing_high is integer 1/0
on valid processed rows, never a retrospective label or a Boolean substituted for the stored code.

Changing target asset_type alone is insufficient. Inspected touchpoints:

1. SQL resolver feature04_asset_type, source-min-date selection, enqueue/retry source selection and
   target/queue/column-status/log/monitor/retry/checkpoint CHECK constraints accept only equity/bonds.
   Verify deployed definitions before writing the forward migration.
2. Engine ASSET_TYPES, symbol validation, incremental classification/fingerprints, source/target loaders,
   pipeline, backfill, worker correction/finality policies and bootstrap must accept index deliberately.
   Indices use the existing IDX price source and session/finality policy; no new hardcoded schedule.
3. Telegram retry currently rejects types outside equity/bonds. Monitor classifies equity-only executions
   as IDX_EQUITY; index grouping must be deliberate rather than accidentally falling into ADHOC.
4. Feature joins/catalog filters currently assume equity/bonds. Update only intended joins, definitions,
   units, access and retry choices while preserving stock/bond behavior.

Resolver: Security Type=index -> index; Security Type=stock -> equity; fixed-income universe -> bonds.
Handle unknown/unsupported types and ambiguous memberships explicitly. Never classify every non-index
instrument as equity merely because it appears in an IDX universe.

Prior verified IHSG rows were written under equity (see verification/ihsg_price_history/apply).
Before rekeying index identities, check collisions and active worker leases and scope all affected operational
rows via universe classification. Checkpoint fingerprints contain asset_type: do not merely rename their keys
and assume they are trusted. Rebuild or explicitly revalidate affected index state. Numerical outputs need
not change solely for metadata reclassification, but target keys, state, queues and subsequent suffix
calculations must agree. Never set queue/column statuses SUCCESS manually.

### Access, source scope and refresh order

All raw symbols include warrants/rights and other instruments. This is a market-wide flow proxy labelled
IHSG, not an official historical IHSG-constituent series. Lots combine different securities; they are not
index units. Keep identical source scope across Features 2/3/5/6 and exclude synthetic aggregates from
any raw-source selection to prevent self-inclusion/double counting.

Existing AI views for Features 5/6 filter universe Security Type=stock, excluding index. Merely storing
IHSG aggregate rows in base tables will not expose them to AI. An explicit index-inclusive view/access
contract and associated catalog, joins, preview and governor checks are required; do not label index stock.

Feature 2/3 do not have automatic refresh workers in the inspected code. Feature 05/06 staged job is not
a sufficient automatic aggregate refresher: its Feature 06 phase skips ticker identities already present.
Implement explicit changed-source refresh in order 2 -> 3 and 5 -> 6, including historical corrections;
do not rely on discovering a new ticker to refresh an existing aggregate.

Price ingestion and broker ingestion are independent. Prior live evidence (2026-10-23) had broker source
through 2026-08-31 and IHSG prices through 2026-10-23. These are historical audit observations, not a
fresh 2026-10-24 live check. Do not forward-fill broker features to the latest price date.

## Acceptance required before release (not executed)

- Recheck actual deployed Git/schema/routines, membership/source coverage, affected row counts,
  credentials/permissions, active leases and key collisions before mutation.
- Independently reconcile additive fields to raw source; recalculate all nonadditive outputs for sampled
  dates, brokers, investor types and every board. Validate exact 221-column coverage.
- Cover warmup, absent pairs, active zero-net brokers, ties, zero denominators/stddev and cancelling source gaps.
- Verify daily/window NULL-frequency propagation and matching value/frequency coverage.
- Assert aggregate HHI remains NULL on initial and subsequent refreshes and is not failed/retried;
  stock HHI, ordinary-stock features and bonds remain unchanged.
- Verify index classification across target/queue/log/status/state/monitor/retry and AI access. Compare stored
  numerical values and full reference versus latest-five-session incremental calculation from trusted state.
  Run the normal worker validation rather than manufacturing success; verify idempotent reruns.
- Prepare forward migrations and semantic/null-policy catalog entries, update schema/catalog/changelogs,
  dictionaries and operational docs, and run relevant semantic/index acceptance checks.
- Existing branch runtime compatibility work is not assumed released; resolve deployment baseline before execution.

No new application tests ran: this task changed documentation only. Matrix checks covered exact column
counts and unique names. The old temporary read-only DB helper was absent in this environment; the attempt
to use it stopped before any database connection. No fresh live verification or database mutation occurred.
