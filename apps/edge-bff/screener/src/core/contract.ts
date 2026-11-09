/* EDGE screener contract, schema_version 1 (EXEC-SCREENER, go 2026-10-28; report API CONTRACT section 8): the requests
   the page sends to edge-bff /api/v1/screener/*, the answers edge-bff relays from the private screener-worker, the
   saved items edge-bff stores itself, and the worker's private routes. One file for the page (Vite), the worker (Node,
   type stripping) and the tests; edge-bff (Python) stores definitions as JSON and does not interpret them beyond the
   fields named here. Types only, plus a few constants: no formula, so the page may import it (report I1, 9.1).

   Units (the Backtest's convention, apps/edge-bff/backtest/src/core/contract.ts; no "Rp miliar" on the wire):
   - money: IDR (rupiah); prices: IDR per share (index points for IHSG); ADV20: IDR (SMA20 of close x volume);
   - percent values are percent where the metric is a percent (pct_distance, chg_1d_pct, RSI 0-100); an indicator
     output keeps its own unit (registry `unit`, derived by the scaling probe, report 6.8);
   - dates: exchange dates 'YYYY-MM-DD' (Asia/Jakarta trading days); timestamps ISO 8601 UTC;
   - no NaN or Infinity on the wire: a missing number is null; a cell's tested value is null only on an NA cell, which
     carries its reason (report I5; the exact per-field rule is on Cell);
   - values are raw doubles rounded to 12 significant digits (report 8.5).

   Lists that look like enums but are data (the valid indicator ids, transform `fn`, pattern `type`, flow and
   cross-section `metric`, universe `attr`) are typed `string` here on purpose: they are read from the generated
   catalog (screener-registry.json, screener-metrics.json) by validate.ts and the page, never kept in code (report 6.9).

   P4 (user 2026-10-28, "P4 tidak, dihide tapi di remark saat di show di filter table"; P4.1 "P4 - pakai A"): stale
   tickers and tickers with an unadjusted price break are hidden by default; shown through the universe chips, their
   rows carry a remark with the reason, and price-derived values whose lookback crosses the ex-date are SHOWN with a
   cell remark, not blanked. A remark explains a value and never changes PASS, FAIL or NA (report 6.9 Remarks). Where a
   report section still says "blank" or "NA" for those cells, the user's P4.1 choice wins.

   Field lists follow report section 8 exactly; a field marked "additive" is not in section 8 but is named by another
   report section (cited on the field) and only adds information. */
import type { Grouping } from '../../../backtest/src/core/contract.ts';

export type { Grouping };

export const SCHEMA_VERSION = 1;

/* ------------------------------------------------------------------------------------------------------------ */
/* shared blocks (report 8.3)                                                                                    */
/* ------------------------------------------------------------------------------------------------------------ */

/** Every worker answer: the versions that decide its numbers (report 8.3, I6). */
export interface Versions {
  screener_engine: string;            // 16 hex: content hash of screener core, worker src, imported core and calc files, Node major
  registry: string;                   // 16 hex: registry_version of backtest-registry.json, passed through
  screener_registry: string;          // 16 hex: screener_registry_version of screener-registry.json, sha256 over base + overlay + derived fields (report 6.8 Versions; 8.3 abbreviates it as base + overlay)
  price_data: string;                 // 64 hex: datafile.dataVersion over (ticker, 'price', pack sha256) of every ticker
  flow_data: string | null;           // 64 hex: sha256 over the sorted name:sha256 of the loaded broker day files (EXEC-SCREENER-FLOW-CANDLES P4, verification/screener/P4_BROKER_DAYS.md section 3); null when none is loaded
  definition_hash?: string;           // 64 hex: sha256 of canonicalJson(definition, params resolved, labels removed); set on run. Report 8.3 also names counts, but a counts answer covers up to max_counts definitions, which one hash cannot name: its versions leave it out (each entry is keyed by item_id; the worker caches per definition_hash, report 8.6)
}

/** The publication's outcome as the catalog reports it (report 8.3): equal on every worker replica, so the catalog
    bytes and their ETag are too (report 6d.4 rule 4). The transient 'refreshing' and the snapshot age are on /health
    only (WorkerHealth). */
export type RefreshState = 'ready' | 'failed_keeping_previous';

/** Every worker answer: which publication it was computed from (report 8.3; as-of policy 6.5). */
export interface DataStatus {
  evaluation_date: string;            // E = price_through
  price_through: string;              // state.json
  flow_through: string | null;        // the newest loaded broker day (P4); null when none is loaded
  broker_behind_sessions: number | null;
  published_at: string;               // state.json finished_at
  broker_window?: BrokerWindow;       // P4 (additive): the broker days the worker holds; set on every worker answer
  refresh?: RefreshState;             // catalog only: the publication's outcome
  /** catalog only (EXEC-SCREENER-BROKER-PICK, additive): the brokers of the reference file `brokers` (IDX_Broker_Profile:
      code, name, domicile), for the flow indicators' broker list; absent when the publication has none */
  brokers?: BrokerRef[];
}
export interface BrokerRef { code: string; name: string; type?: string }
/** EXEC-SCREENER-FLOW-CANDLES P4 (user 2026-11-07, K1 window 60 sessions; verification/screener/P4_BROKER_DAYS.md
    section 3): the loaded broker days, oldest and newest, how many, and whether every day of the publication's window
    (its newest 60 indexed broker days) is loaded; complete is false while days still wait for a follow-up refresh. A
    publication that indexes no broker day: {first: null, last: null, sessions: 0, complete: true}. */
export interface BrokerWindow { first: string | null; last: string | null; sessions: number; complete: boolean }

/** Error body, the edge-bff convention ({"error": {...}}; apps/edge-bff/backtest/CONTRACT.md section 11). TEMPORARY
    exception (report 8.1, ERRORS M261): 401/403 of the auth dependencies are {"detail": ...}; the client maps them. */
export interface ApiError { error: { code: ErrorCode | string; field?: string; message?: string; details?: Record<string, unknown> } }

/** Refusal and failure codes, exactly the table of report 8.8. Each refusal names the field where there is one and
    the fix (AGENTS.md "Gates and evidence" (d)). The backtest core's own codes (resolveParams: PARAM_NOT_ACCEPTED,
    INVALID_PARAM, INVALID_PARAMS; conditions.ts: UNKNOWN_OUTPUT) never reach the wire: registry.ts maps them onto
    INVALID_CONDITION or PARAM_OUT_OF_RANGE (registry.ts mapCoreError). */
export type ErrorCode =
  | 'INVALID_INPUT' | 'INVALID_CONDITION' | 'UNKNOWN_INDICATOR' | 'PARAM_OUT_OF_RANGE' | 'METRIC_UNAVAILABLE'
  | 'LIMIT_EXCEEDED' | 'DATA_UNAVAILABLE' | 'DATA_INTEGRITY' | 'BUSY' | 'SCREEN_REPLACED' | 'PREVIEW_REPLACED'
  | 'DATA_VERSION_CHANGED' | 'REVISION_CONFLICT' | 'NAME_TAKEN' | 'NOT_FOUND' | 'REQUEST_TOO_LARGE'
  | 'SCREENER_DISABLED' | 'SCREENER_NOT_READY' | 'SCREENER_UNAVAILABLE' | 'TIMEOUT';
/** HTTP status per code (report 8.8); the worker and edge-bff answer with these. */
export const ERROR_STATUS: Readonly<Record<ErrorCode, number>> = Object.freeze({
  INVALID_INPUT: 422, INVALID_CONDITION: 422, UNKNOWN_INDICATOR: 422, PARAM_OUT_OF_RANGE: 422, METRIC_UNAVAILABLE: 422,
  LIMIT_EXCEEDED: 422, DATA_UNAVAILABLE: 424, DATA_INTEGRITY: 424, BUSY: 409, SCREEN_REPLACED: 409, PREVIEW_REPLACED: 409,
  DATA_VERSION_CHANGED: 409, REVISION_CONFLICT: 409, NAME_TAKEN: 409, NOT_FOUND: 404, REQUEST_TOO_LARGE: 413,
  SCREENER_DISABLED: 503, SCREENER_NOT_READY: 503, SCREENER_UNAVAILABLE: 503, TIMEOUT: 504,
});
export const ERROR_CODES = Object.freeze(Object.keys(ERROR_STATUS) as ErrorCode[]);
/** LIMIT_EXCEEDED details (report 8.8, 8.9): which limit (a LimitName, so the page finds its rule and examples in
    catalog.limits[] by the same name), the allowed value and what the request needed; `costliest` (a condition id)
    for limit 'compute_budget'. */
export interface LimitExceededDetails { limit: LimitName; allowed: number; needed: number; costliest?: string }
/** PARAM_OUT_OF_RANGE details (report 8.8 `{field, min, max}`): max = the base max or the derived cap, whichever is
    lower; exclusive_min and integer say which narrowing rule refused the value (report 6.8 rules a and b). */
export interface ParamRangeDetails { field: string; min?: number; max?: number; exclusive_min?: boolean; integer?: boolean }
/** INVALID_CONDITION / UNKNOWN_INDICATOR details (report 8.8 "allowed values"): the values the field accepts. */
export interface AllowedDetails { allowed: (string | number)[] }
/** METRIC_UNAVAILABLE details (report 8.8, 6.12). */
export interface MetricUnavailableDetails { metric: string; availability: Exclude<Availability, 'AVAILABLE'>; reason: string; reason_code?: NaReason }

/** Latest wins per page (the Backtest preview's client_order; report 8.1): a newer seq of the same page replaces the
    older call, which answers 409 SCREEN_REPLACED / PREVIEW_REPLACED. */
export interface ClientOrder { page: string; seq: number }

/* ------------------------------------------------------------------------------------------------------------ */
/* metric references and tests (report 8.5, 6.9)                                                                */
/* ------------------------------------------------------------------------------------------------------------ */

export type ParamValue = number | string | boolean;
export type ParamMap = Record<string, ParamValue>;
/** The parameters a condition summary names (report 8.5 params_resolved): an indicator's or a transform's (ParamMap),
    or a flow indicator's, whose boards, investor types and brokers are lists (P5a). */
export type ResolvedParams = Record<string, ParamValue | string[]>;
export type PriceField = 'open' | 'high' | 'low' | 'close' | 'volume';
export const PRICE_FIELDS: readonly PriceField[] = ['open', 'high', 'low', 'close', 'volume'];
export type Board = 'regular' | 'all';

/** A registry indicator output (I01..I53 today). params: accepted parameters only, missing ones take the registry
    default; checked by the backtest core's resolveParams plus the screener narrowing (registry.ts), never adjusted:
    a registry default the screener does not offer (P17 a: I43 anchor Session) is refused naming params.anchor with
    the offered options, so the page sends the catalog's `default` values. */
export interface IndicatorRef { kind: 'indicator'; indicator: string; params?: ParamMap; output: string }
/** A bar field of the ticker's own bars. */
export interface PriceRef { kind: 'price'; field: PriceField }
/** Condition arithmetic over another reference (report 6.9; today pct_distance, band_position, lag, change,
    rolling_max, rolling_min, rising_run, ma, ratio, vs_index; the valid fn values and their args are in
    screener-metrics.json). args may hold numbers, strings, booleans or a second reference (ratio's denominator). */
export interface TransformRef { kind: 'transform'; fn: string; of: MetricRef; args?: Record<string, ParamValue | MetricRef> }
/** A pattern signal (today breakout, breakdown, volspike, macross, macd_divergence, squeeze, stoch_cross_in_zone,
    new_high, silent; core PRICE_ACTION and bullishDivergence where they exist; and the 20 candlestick patterns of the
    Backtest core's candle registry, EXEC-SCREENER-FLOW-CANDLES P6, computed by its candles.ts). */
export interface PatternRef { kind: 'pattern'; type: string; params?: ParamMap }
/** A flow parameter's value (EXEC-SCREENER-FLOW-CANDLES P5a): a number, text or switch, or a list of texts (the boards,
    investor types and brokers of the Terminal's flowRegistry.json `multi` and `brokers` parameters). */
export type FlowParamValue = ParamValue | string[];
/** One of the Terminal's 48 flow indicators as a series (EXEC-SCREENER-FLOW-CANDLES P5a; verification/screener/
    P5_FLOW.md section 1): metric 'FL01'..'FL48'; output one of the registry's `outputs` (default the first); params the
    registry's parameters (flowRegistry.json indicators[].params; the Terminal's setup), a parameter left out taking its
    registry default (flow.ts flowDefaults; the board default Regular, G1, user 2026-11-07), the kinds that only draw
    (levels, button, fixed) refused. Computed by the Terminal's own flow.ts computeFlow on the broker rows the worker
    holds, on the stock's own price bars inside the loaded broker window (G2), read at the stock's last candle with
    broker data (P10 a). P5b (P5_FLOW.md section 3): metric may also be a Screener version's id (FL18-FL20, FL23, FL44,
    FL45 with their screener parameters) or one of the Screener's own flow entries (fnet; ksei_net), same shape. */
export interface FlowRef { kind: 'flow'; metric: string; output?: string; params?: Record<string, FlowParamValue> }
/** A cross-sectional value on the fixed population (P7; today return_rank). */
export interface XsectionRef { kind: 'xsection'; metric: string; params?: { window?: number } & Record<string, ParamValue> }
/** A universe attribute (last, chg_1d_pct, adv20_idr, bars, ...; screener-metrics.json). */
export interface UniverseRef { kind: 'universe'; attr: string }
/** Operator 11, Ranking / Cross-Sectional (EXEC-SCREENER-FLOW-CANDLES P2; verification/screener/OPERATORS.md): the
    percent rank, 0-100, of a series' value at each ticker's evaluation bar against the population of decision C (user
    2026-11-07): the stocks of the user's own filtered universe (after the universe filters, before the conditions)
    whose value is not missing; xsection.ts percentRank. A VALUE test only; not a metric filter (the population is the
    filtered universe itself) and not inside a window test. The fixed-population return_rank (K3) is a separate
    metric. */
export interface RankRef { kind: 'rank'; of: MetricRef }
export type MetricRef = IndicatorRef | PriceRef | TransformRef | PatternRef | FlowRef | XsectionRef | UniverseRef | RankRef;
export type MetricKind = MetricRef['kind'];

/** A constant side of a STATE or EVENT comparison. */
export interface ValueSide { value: number }
export type Side = MetricRef | ValueSide;

/** VALUE (report 6.9): the metric at the evaluation bar. gt/lt strict; between inclusive (value <= x <= value2) and
    counted as one condition; value > value2 is refused with INVALID_CONDITION field value2, never reordered (I7);
    value = value2 is accepted (TEST PLAN 10b.3). */
export interface ValueTest { kind: 'value'; metric: MetricRef; op: ValueOp; value: number; value2?: number }
/** VALUE operators (OPERATORS.md operators 1 and 15): gt, lt strict; ge, le inclusive; eq, ne only on a whole-number
    series (K7: a count such as rising_run or a universe attribute in sessions); between inside, both bounds included;
    outside: x < value or x > value2. between and outside take value <= value2 (never reordered). */
export type ValueOp = 'gt' | 'lt' | 'ge' | 'le' | 'eq' | 'ne' | 'between' | 'outside';
export const VALUE_OPS: readonly ValueOp[] = ['gt', 'lt', 'ge', 'le', 'eq', 'ne', 'between', 'outside'];
/** STATE (report 6.9): compare(lhs, op, rhs)[at] with the core's rules (bar 0 never true, NaN false). price vs an
    output only where the output is level_comparable (its comparable_with field); a pattern state is true on `at`. */
export interface StateCompare { kind: 'state'; lhs: Side; op: 'gt' | 'lt'; rhs: Side }
export interface StatePattern { kind: 'state'; pattern: PatternRef }
export type StateTest = StateCompare | StatePattern;
/** EVENT (report 6.9): a cross through core compare (both sides finite on the bar and the bar before) or a pattern
    signal, on the ticker's own bars, within the last `within` bars ending at the evaluation bar: j = the largest index
    in [at-within+1, at] where the signal is 1. within is per condition, 1..within_max (130 technical; flow maximum
    derived from the published window). An event is never reduced to a state. */
export interface EventCross { lhs: Side; op: 'crosses_above' | 'crosses_below'; rhs: Side }
export interface EventPattern { pattern: PatternRef }
export interface EventTest { kind: 'event'; signal: EventCross | EventPattern; within: number }
/** Operators 5, 9 and 10 (OPERATORS.md: Ever / Lookback, Persistence / Frequency, Consecutive / Streak) over an inner
    test on the ticker's own bars (a VALUE test, a STATE comparison or pattern, or an EVENT cross or pattern with within
    1: the cross on that session, operator 8; a rank across stocks is not taken inside a window), on the `length` sessions ending at the evaluation bar:
    - ever: the inner test passes on at least one of them;
    - at_least: on at least `count` of them (1 <= count <= length);
    - streak: on each of the last `length` sessions (a session where the inner test is n/a breaks the run).
    A session where the inner test is n/a counts as not passing; the test is n/a only when the inner test is n/a on
    every one of the sessions. length 1..within_max (the evaluation tail). The cell's value is the number of passing
    sessions in the window (streak: the run ending at the evaluation bar, at most length); event_date and bars_ago name
    the latest passing session. */
export interface WindowTest { kind: 'window'; mode: WindowMode; length: number; count?: number; test: ValueTest | StateTest | EventTest }
export type WindowMode = 'ever' | 'at_least' | 'streak';
export const WINDOW_MODES: readonly WindowMode[] = ['ever', 'at_least', 'streak'];
export type Test = ValueTest | StateTest | EventTest | WindowTest;
export type TestKind = Test['kind'];

/** One condition card. id ^[0-9a-z]{1,6}$, unique in the definition; at most max_conditions enabled. */
export interface ConditionDef { id: string; enabled: boolean; label?: string; test: Test }
export const CONDITION_ID = /^[0-9a-z]{1,6}$/;

/** Universe hard filters, stage S0 (report 8.5, 6.10, 6.12). Conjunctive and outside `met`, so safe for every logic.
    - security_types: only 'stock' today (P15);
    - sectors_in / industries_in keep a ticker without that classification only when include_unclassified is true;
      the _out filters never drop it (P15); 'Undefined' is not a value; values come from catalog.groupings;
    - price_min (last close), adv20_min_idr (liquidity() at E): number >= 0 or null; min_history_bars: integer >= 1
      or null; boundaries inclusive;
    - traded_on_eval_date (default true, P4; report 8.5 "Default true", so a request may leave it out and absent means
      true, here, in universe.ts and in validate.ts's normalized definition): hides stale tickers (last bar before E);
      false lists them with the row remark STALE, evaluated at their own last bar;
    - exclude_price_breaks (default true, P4 user choice; chip "No unadjusted price break"; absent means true as
      above): hides tickers with an unadjusted price-affecting action (ADJUSTED_HISTORY_BOUNDARY <= ex-date <= last
      bar); false lists them with the row remark PRICE_BREAK and the cell remark PRICE_BREAK_IN_LOOKBACK on affected
      cells (P4.1 A: values shown);
    - tickers: an explicit list, each must be in the universe (unknown tickers refused by name);
    - metric_filters: VALUE tests only, at most max_metric_filters;
    - indices_in / indices_out, groups_in / groups_out (additive, EXEC-SCREENER-STOCK-LISTS, user 2026-11-09 options 1A,
      2, 3): the `code` of a list of catalog.stock_lists (kind INDEX for indices, KONGLO for groups; "LQ45", "SALIM"),
      on the current members only. _in keeps a stock in at least one chosen list of that kind ("any of them"), _out
      drops a stock in any chosen list; Index and Group combine with AND, and with sector and industry as before. A stock
      in no list is not "unclassified": include_unclassified does not touch these filters. Empty lists are left out of
      the normalized definition, so a definition without them hashes as before; one with them is refused while the
      stock-lists file is not available (validate.ts). */
export interface UniverseDef {
  security_types: ['stock'];
  sectors_in?: string[]; sectors_out?: string[]; industries_in?: string[]; industries_out?: string[];
  indices_in?: string[]; indices_out?: string[]; groups_in?: string[]; groups_out?: string[];
  include_unclassified?: boolean;
  price_min?: number | null; adv20_min_idr?: number | null; min_history_bars?: number | null;
  traded_on_eval_date?: boolean;      // absent: true (P4)
  exclude_price_breaks?: boolean;     // absent: true (P4)
  tickers?: string[] | null;
  metric_filters?: ValueTest[];
}
/** Defaults of the universe chips (P4 decided; prototype liquidity defaults kept: price >= Rp 50, ADV20 >= Rp 1 B;
    report 6.12, 9.2). "Clear all" returns to these (report 9.2). */
export const UNIVERSE_DEFAULTS: Readonly<UniverseDef> = Object.freeze<UniverseDef>({
  security_types: ['stock'], include_unclassified: false, price_min: 50, adv20_min_idr: 1e9, min_history_bars: null,
  traded_on_eval_date: true, exclude_price_breaks: true, tickers: null, metric_filters: [],
});

export type Logic = 'all' | 'any' | 'at_least';
/** The portable definition (screen/v1): one object for run, save, CSV metadata and Send to Backtest (report 6.15).
    at_least is required with logic at_least (integer >= 1); above the active count it means all (core entryNeed). */
export interface Definition { universe: UniverseDef; conditions: ConditionDef[]; logic: Logic; at_least?: number }

/* ------------------------------------------------------------------------------------------------------------ */
/* NA reasons and remarks (report 6.9, P4)                                                                       */
/* ------------------------------------------------------------------------------------------------------------ */

/** Why a cell is NA (report 6.9 NA reason codes; never fails the whole screen):
    - INSUFFICIENT_HISTORY: the series has no value on any of the ticker's bars up to the evaluation bar (the core's
      INDICATOR_OUTPUT_EMPTY, caught per ticker like signals.ts unlessLeftOut);
    - NULL_AT_EVALUATION: the series has values earlier but none at the evaluation bar (zero band width, flat window,
      zero volume, an option that needs volume on an instrument without volume such as IHSG);
    - FLOW_UNAVAILABLE / FLOW_LAGGED: flow missing, or older than the policy allows (P10; Phase 2);
    - NOT_APPLICABLE: the metric's applies_to excludes the ticker (bank metrics outside Banks);
    - DATA_INTEGRITY: the flow self-check failed on this publication (report 6.11; Phase 2);
    - MIXED_ADJUSTMENT_BASIS: a dividend TTM window crosses a price-affecting action (P11; Phase 2).
    A stale ticker is not NA: it is evaluated at its own last bar and carries the row remark STALE (P4). A price
    break is not NA either: the value is shown with the cell remark PRICE_BREAK_IN_LOOKBACK (P4.1 A). */
export type NaReason = 'INSUFFICIENT_HISTORY' | 'NULL_AT_EVALUATION' | 'FLOW_UNAVAILABLE' | 'FLOW_LAGGED' | 'NOT_APPLICABLE'
  | 'DATA_INTEGRITY' | 'MIXED_ADJUSTMENT_BASIS';
export const NA_REASONS: readonly NaReason[] = ['INSUFFICIENT_HISTORY', 'NULL_AT_EVALUATION', 'FLOW_UNAVAILABLE', 'FLOW_LAGGED',
  'NOT_APPLICABLE', 'DATA_INTEGRITY', 'MIXED_ADJUSTMENT_BASIS'];

/** Row remarks (P4; report 8.4 universe body, 8.5 rows[].remarks; codes in 6.9 Remarks). The page words them in
    src/texts.ts from these codes and fields (report 9.2), so no message travels.
    - STALE: the ticker's last bar is before E; last_bar_date is that bar;
    - PRICE_BREAK (TEMPORARY, until the D22 data-layer fix): one remark per unadjusted price-affecting action (type in
      PRICE_ACTION_TYPES of datafile.ts, ADJUSTED_HISTORY_BOUNDARY <= ex_date <= the ticker's last bar); action: its
      type (STOCK_SPLIT, ...); ratio_old / ratio_new as published (null when absent); close_ratio = close on the
      ex-date / close on the bar before (null when either is missing). */
export interface StaleRemark { code: 'STALE'; last_bar_date: string }
export interface PriceBreakRemark { code: 'PRICE_BREAK'; action: string; ex_date: string; ratio_old: number | null; ratio_new: number | null; close_ratio: number | null }
export type RowRemark = StaleRemark | PriceBreakRemark;
export type RowRemarkCode = RowRemark['code'];
export const ROW_REMARK_CODES: readonly RowRemarkCode[] = ['STALE', 'PRICE_BREAK'];
/** Cell remark (P4.1 A; report 8.5 cells[].remark): on a PRICE_BREAK row, a price-derived cell whose lookback contains
    an ex-date keeps its value and its pass or fail and is marked as distorted. The lookback: a window-class output only
    while its window contains the ex-date; recursive, cumulative and calendar outputs always after the ex-date (report
    6.12). Flow, ADV20 and universe attributes never carry it. */
export type CellRemark = 'PRICE_BREAK_IN_LOOKBACK';
export const CELL_REMARKS: readonly CellRemark[] = ['PRICE_BREAK_IN_LOOKBACK'];

/* ------------------------------------------------------------------------------------------------------------ */
/* POST run (report 8.5)                                                                                         */
/* ------------------------------------------------------------------------------------------------------------ */

export interface RunOptions { exhaustive?: boolean; explain?: boolean }
/** data_version (optional, report 8.5 and 6d.4 rule 1): the price_data of the page's catalog. A replica answers at
    that version while it holds it (its current one, or the previous one during SCREENER_PREVIOUS_GRACE_S); a newer
    one answers the worker-only 409 DATA_VERSION_PENDING (edge-bff retries once, then 503 SCREENER_NOT_READY), an
    older one 409 DATA_VERSION_CHANGED. Absent: the replica's current version. */
export interface RunRequest { schema_version: 1; client_order: ClientOrder; data_version?: string; definition: Definition; options?: RunOptions }

/** Where a condition's values came from: precomputed (a pre-warmed snapshot hit), dynamic (computed for this screen
    on full history), flow (a condition that reads a flow indicator, P5a: evaluated at the stock's last candle with
    broker data, eval_date_basis 'flow_date'), xsection. is_default says whether the parameters are the registry's
    (report 8.5). */
export type ConditionSource = 'precomputed' | 'dynamic' | 'flow' | 'xsection';
/** Per-condition summary. metric: '<id>.<output>' for an indicator, '<lhs> x <rhs>' for a cross between two
    references (report 8.5 example). passed counts the tickers in `evaluated`; it equals the count over every eligible
    ticker only when exhaustive is true, and the page never shows a non-exhaustive count against the universe size
    (report 6.10). */
export interface ConditionSummary {
  id: string; source: ConditionSource; metric: string; params_resolved: ResolvedParams; is_default: boolean; kind: TestKind;
  unit: string | null; evaluated: number; passed: number; na: number; exhaustive: boolean;
  eval_date_basis: 'ticker_last_bar' | 'flow_date';
}
export type CellStatus = 'pass' | 'fail' | 'na' | 'not_evaluated';
/** One condition on one ticker (report 8.5). value for VALUE; lhs and rhs for STATE and EVENT (the current values);
    event_date, bars_ago (the ticker's own bars), market_sessions_ago (the IHSG calendar, informational) and
    last_event_date (the last event within within_max bars) for EVENT. reason is set exactly when status is 'na' (I5);
    remark is null or PRICE_BREAK_IN_LOOKBACK (the value is shown and marked, P4.1 A).
    Nulls (I5, "no null value without a reason"): value (VALUE) and lhs / rhs (STATE) are null only on an NA cell; on
    EVENT, event_date, bars_ago and market_sessions_ago are null exactly when no event was found within `within` (FAIL
    or NA), last_event_date when none was found within within_max, and lhs / rhs are the current values, shown for
    information, so they may be null on a PASS (an earlier cross stands) or a FAIL (evaluate.ts evaluateEvent).
    Sort key: the value for VALUE and STATE, 1000 - bars_ago for EVENT; nulls last (report 6.9 Sort). */
export interface Cell {
  id: string; status: CellStatus;
  value?: number | null; lhs?: number | null; rhs?: number | null; unit?: string | null;
  eval_date: string | null; event_date?: string | null; bars_ago?: number | null; market_sessions_ago?: number | null;
  last_event_date?: string | null;
  reason: NaReason | null;
  remark: CellRemark | null;
}
export type RowStatus = 'match' | 'near';
/** A result row: matches and near rows only (report 8.5). board and market_cap are always null ("no data", FACT: no
    source exists). near = !match && need >= 2 && met == need - 1, the one rule for table, preview and CSV (6.9). */
export interface ResultRow {
  ticker: string; name: string | null; sector: string | null; industry: string | null; board: null; market_cap: null;
  last: number | null; chg_1d_pct: number | null; adv20_idr: number | null; last_bar_date: string; stale: boolean;
  remarks: RowRemark[];
  status: RowStatus; met: number; need: number; na_count: number; cells: Cell[];
}
/** The universe funnel of one run (report 8.5): listed = stocks in the reference file; eligible = after S0;
    stale_hidden and price_break_hidden = hidden by the P4 chips (0 when the chip is off); filtered_out = the rest. */
export interface UniverseCounts { listed: number; eligible: number; stale_hidden: number; price_break_hidden: number; filtered_out: number }
/** Warnings (report 8.5, "for example"): FLOW_LAGGED (Phase 2); PRICE_BREAKS_IN_RESULT with details {rows, cells}, the
    rows and cells that carry a price-break remark; NO_PRUNING_FOR_ANY (logic any: the planner cannot prune, 6.10). */
export type WarningCode = 'FLOW_LAGGED' | 'PRICE_BREAKS_IN_RESULT' | 'NO_PRUNING_FOR_ANY';
export interface Warning { code: WarningCode | string; message: string; count?: number; details?: Record<string, unknown> }
export interface Timings { queue: number; s0: number; s1: number; s2: number; s3: number; s4: number; total: number }
export type StageName = 'S0' | 'S1' | 'S2' | 'S3' | 'S4';
/** options.explain (report 6.16, 8.5 `plan`): the stages, the order of the S3 conditions, survivors per stage, cache hits. */
export interface PlanExplain {
  stages: { name: StageName; in: number; out: number; ms: number }[];
  order: string[];                    // condition ids in evaluation order
  pruned: number;                     // tickers pruned before S4
  cache_hits: number;
  exhaustive: boolean;
  note?: string;                      // e.g. 'ANY: no safe pruning'
}
export interface RunResponse {
  schema_version: 1; versions: Versions; data: DataStatus;
  mode: 'screen' | 'universe_only';   // universe_only: no active condition, the universe is listed
  universe: UniverseCounts;
  conditions: ConditionSummary[];
  need: number; match_count: number; near_count: number;
  rows: ResultRow[];
  warnings: Warning[];
  timings_ms: Timings;
  plan?: PlanExplain;
}

/* ------------------------------------------------------------------------------------------------------------ */
/* POST preview, validate, counts (report 8.6)                                                                   */
/* ------------------------------------------------------------------------------------------------------------ */

/** data_version: the price_data the page's table came from; older than the versions the replica holds answers 409
    DATA_VERSION_CHANGED and the page re-reads the catalog and re-runs the screen (chart and table never mix two
    publications); newer answers the worker-only DATA_VERSION_PENDING (report 8.6, 6d.4). */
export interface PreviewRequest { schema_version: 1; client_order: ClientOrder; definition: Definition; ticker: string; data_version: string }
export type PreviewStatus = 'match' | 'near' | 'fail' | 'outside_universe';
export type PerfPeriod = '1M' | '3M' | '6M' | '1Y';
export const PERF_PERIODS: readonly PerfPeriod[] = ['1M', '3M', '6M', '1Y'];
/** The previewed ticker: cells and status are returned even outside the universe; bars: the last PREVIEW_BARS
    (columns), ihsg_close aligned to the ticker's dates with asOf; overlays per active condition; event markers per
    condition; perf: rebased "Stock vs IHSG" (P14) over the session counts of catalog.periods. */
export interface PreviewResponse {
  versions: Versions; data: DataStatus;
  ticker: string; status: PreviewStatus; remarks: RowRemark[]; met: number; need: number; cells: Cell[];
  bars: { d: string[]; o: (number | null)[]; h: (number | null)[]; l: (number | null)[]; c: (number | null)[]; v: (number | null)[] };
  ihsg_close: (number | null)[];
  /** unit, additive (EXEC-SCREENER-ADD, ERRORS M368): the series' scaling class (registry Unit: 'price',
      'price_change', 'volume', 'price_x_volume', 'dimensionless', 'other'; null when the core gives none). The page
      draws only 'price' series on the candle axis; a percent, an oscillator or a rank there flattened the candles.
      Optional for the page: an answer of an older worker has none, and such a series is not drawn. */
  overlays: { condition_id: string; output: string; unit?: string | null; values: (number | null)[] }[];
  markers: { condition_id: string; bars: { date: string; kind: string }[] }[];
  perf: Record<PerfPeriod, { stock_pct: number | null; ihsg_pct: number | null }>;
}
/** Bars a preview answer carries (report 8.6: "last 260"); the chart draws the last 130 (report 9.3). */
export const PREVIEW_BARS = 260;
export interface ValidateRequest { schema_version: 1; definition: Definition }
/** valid: the definition with parameters resolved (normalized) and its hash; a refusal is the 422 of the first problem. */
export interface ValidateResponse {
  valid: true; definition_hash: string; normalized: Definition;
  /** additive (integration 2026-10-28): the worker's versions when it validated (edge-bff stores registry and
      screener_registry with a saved item from this same answer, not from a later /health read) */
  versions?: Versions;
}
/** data_version as in RunRequest (report 8.6). At most max_counts definitions. */
export interface CountsRequest { schema_version: 1; data_version?: string; definitions: { item_id: string; definition: Definition }[] }
export type CountsEntry = { item_id: string; match_count: number; near_count: number } | { item_id: string; error: ApiError['error'] };
export interface CountsResponse { versions: Versions; data: DataStatus; counts: CountsEntry[] }

/* ------------------------------------------------------------------------------------------------------------ */
/* GET catalog, GET universe (report 8.4)                                                                        */
/* ------------------------------------------------------------------------------------------------------------ */

/** The limits of report 8.9 by name (catalog limits[].name; LIMIT_EXCEEDED details.limit: one name for both, so a
    refusal points at the published rule). Worker limits are each an environment variable with no default
    (SCREENER_MAX_CONDITIONS -> max_conditions, SCREENER_MAX_CPU_MS -> compute_budget, the name report 6.10 and 8.8 give
    its refusal, ...); edge-bff's follow its own config (request_bytes, saved_definition_bytes, saved_items, watchlist,
    inflight_per_page). owner_cpu_budget (SCREENER_OWNER_CPU_MS, P33 built in Phase 1, user 2026-10-28): one owner tag's
    compute per sliding minute on a replica; its refusal is LIMIT_EXCEEDED with details.retry_after_seconds. The refresh caps (max_file_bytes, max_inflated_bytes, max_refresh_bytes) never refuse a request:
    they fail a refresh (REFRESH_FAILED in the log), so they are listed for transparency only. broker_depth (K1,
    EXEC-SCREENER-FLOW-CANDLES P5a): the sessions a flow condition reads (the flow indicator's own window plus its
    operators' N, length or within) are at most the loaded broker window's sessions (data.broker_window.sessions). */
export type LimitName = 'max_conditions' | 'max_metric_filters' | 'within_max' | 'cap_budget_ms' | 'compute_budget' | 'deadline_ms'
  | 'inflight_per_page' | 'owner_inflight' | 'owner_cpu_budget' | 'previous_grace_s' | 'queue' | 'request_bytes' | 'saved_definition_bytes'
  | 'saved_items' | 'watchlist' | 'max_counts' | 'max_response_bytes' | 'max_file_bytes' | 'max_inflated_bytes'
  | 'max_refresh_bytes' | 'broker_depth';
/** A limit as the page shows it before the user meets it (AGENTS.md "Gates and evidence": the rule, how to pass it,
    one right and one wrong example), generated from the value, never typed into the page. */
export interface LimitEntry { name: LimitName | string; value: number; unit: string; rule: string; example_ok: string; example_refused: string }

/** Availability, derived at run time (report 6.12): indicators from the generated registry; every other metric from
    screener-metrics.json `requires` against the files indexed in state.json. */
export type Availability = 'AVAILABLE' | 'REQUIRES_DATA' | 'REQUIRES_DECISION' | 'NOT_APPLICABLE';
/** history_class (report 6.8 cut probe): window (equal to full history once its window is full), recursive (decays
    toward the full-history value), cumulative (never converges: level depends on the start bar), calendar (anchored). */
export type HistoryClass = 'window' | 'recursive' | 'cumulative' | 'calendar';
/** cost_class (report 6.8): O(N) or O(N·n), from the work of F at two lengths of the parameter (its default L1 and
    L2 = max(1000, 50 x L1), at most a quarter of the fixture's bars), counted, never timed: V8 precise block coverage
    counts the executed source characters in a child process without the optimizing compiler (--max-opt=1). O(N·n) when
    the work grows at least five times, O(N) when at most twice; a growth in between stops the build
    (scripts/build-screener-registry.mjs costClass, costVerdict). */
export type CostClass = 'O(N)' | 'O(N·n)';
/** The prototype's shapes (report 6.9.1), kept in screener-overlay.json. */
export type Shape = 'line' | 'band' | 'dir' | 'osc' | 'pair' | 'adx' | 'vol' | 'cum';
/** The test forms an output allows (screener-overlay.json), each one wire form of report 6.9.1:
    value                 VALUE on the output
    value_pct_distance    VALUE on transform pct_distance(close, output)
    value_band_position   VALUE on transform band_position(the band of this instance)
    state_level           STATE price field (comparable_with) gt|lt output, at the output's price_compare_lag
    state_value           STATE output gt|lt a value (direction gt 0)
    state_output          STATE output gt|lt another output of the same instance (with_output)
    state_instance        STATE output gt|lt the same output of a second instance (SMA50 vs SMA200, ma_cross above)
    state_rising          STATE output gt transform lag(output, bars)
    state_vs_ma           STATE output gt|lt transform ma(output, ma, length)
    event_level           EVENT price field crosses output, at the output's price_compare_lag
    event_value           EVENT output crosses a value
    event_output          EVENT output crosses another output of the same instance (with_output)
    event_instance        EVENT output crosses the same output of a second instance (golden / death cross)
    event_vs_ma           EVENT output crosses transform ma(output, ma, length) */
export type TestForm = 'value' | 'value_pct_distance' | 'value_band_position' | 'state_level' | 'state_value' | 'state_output'
  | 'state_instance' | 'state_rising' | 'state_vs_ma' | 'event_level' | 'event_value' | 'event_output' | 'event_instance'
  | 'event_vs_ma';
export type TestOp = 'gt' | 'lt' | 'between' | 'crosses_above' | 'crosses_below';
/** One allowed test form of an output: ops restricts the operators to the prototype's (report 6.9.1, kept 1:1);
    labels: the prototype's card label per operator where it has one; defaults: the value or the transform arguments
    the card opens with (value; bars; ma and length). */
export interface TestFormSpec { form: TestForm; ops: TestOp[]; with_output?: string; labels?: Partial<Record<TestOp, string>>; defaults?: Record<string, ParamValue> }
/** A test form shown disabled with its reason (raw cumulative levels, report 6.7). */
export interface DisabledTestForm { form: TestForm; reason: string }
/** The card a new condition on this indicator opens with (the prototype's XK.def, kept as a product choice). */
export interface DefaultTest { form: TestForm; output: string; op: TestOp; value?: number; value2?: number; within?: number }

export interface CatalogParam {
  key: string; type: 'integer' | 'number' | 'enum' | 'boolean';
  label: string | null;              // additive: the workbook's display label (indRegistry.json params[].label)
  /** The value a new card opens with: the registry default (P21 a), except where the screener does not offer the
      registry default (P17 a: I43 anchor Session), where it is the overlay's start value (CatalogIndicator
      default_offered false). */
  default: ParamValue;
  min?: number; max?: number;        // max: the base max or the derived cap, whichever is lower (report 6.8 caps)
  exclusive_min: boolean;            // derived degeneracy probe or an overlay override with evidence (report 6.8 rule a)
  integer: boolean;                  // the base type or the derived floor probe (report 6.8 rule b)
  options?: string[];                // the options the screener offers: the base's, narrowed by a decision (P17 a)
  step?: number;
}
export interface CatalogOutput {
  key: string; shape: Shape; tests: TestFormSpec[];
  unit: string;                      // derived by the scaling and shift probes (registry.ts UNITS)
  level_comparable: boolean;
  price_compare_lag: { gt: 0 | 1; lt: 0 | 1 };
  inputs_by_source: Record<string, Record<string, string[]>>;   // enum parameter -> option -> needed fields (O H L C V); [] = no value at that option
  label: string | null;              // additive (6.8 overlay "display labels"; indRegistry outs[].label)
  display_unit: string | null;       // additive: the workbook's unit (indRegistry.json), for display
  comparable_with: 'close' | 'volume' | null;   // additive: what level_comparable compares with (6.8 scaling probe)
  disabled_tests: DisabledTestForm[];           // additive: forms shown disabled with a reason (6.9.1 cum rows)
  history_class: HistoryClass;                  // additive: per output (6.8 cut probe "for all 76 outputs")
  first_valid_bar: number | null;               // additive: at the start configuration, the registry defaults except I43 at Week (6.8 "first_valid_bar per output")
}
export interface CatalogIndicator {
  id: string; key: string; name: string; category: string; synonyms: string[]; formula_version: string;
  params: CatalogParam[]; outputs: CatalogOutput[]; history_class: HistoryClass; cost_class: CostClass;
  overlay: { shape: Shape; default_test: DefaultTest | null };
  /** additive (report 13 P17 consequence, built as recommended): false when a registry default is not offered (I43:
      anchor Session, P17 a), so the card has no "Default" chip and opens as Custom at the params' `default` values
      (anchor Week); every condition on it has is_default false. True for the other 52. */
  default_offered: boolean;
  /** additive (page O5): the registry's short name (indRegistry.json `short`, e.g. 'SMA', 'Stoch'); null when it has none */
  short: string | null;
  /** additive (page O1): one plain-English sentence on what the indicator measures (screener-overlay.json, our own
      wording), the page's tooltip and search text */
  description: string;
}
/** A non-indicator metric (screener-metrics.json; report 6.12): the Feature_Catalog fields, so a later AI onboarding can
    reuse them. */
export interface CatalogMetric {
  id: string; group: string;
  /** additive: the reference kind a condition on it uses (transform, pattern, flow, xsection, universe). A fundamental
      (fundamentals[]) is a per-ticker value at E like a universe attribute, so its kind is 'universe' and its group
      says it is fundamental (validate.ts MetricDefinition has the same type). */
  kind: MetricKind;
  params: CatalogParam[]; tests: TestKind[]; unit: string | null;
  formula: string; interpretation: string; misuse: string;
  availability: Availability; reason: string | null; applies_to: string | null;
  /** additive (EXEC-SCREENER-FLOW-CANDLES P5a): a flow indicator's Terminal setup, generated from flowRegistry.json
      (params is empty on a flow entry: its parameters are these) */
  flow?: CatalogFlow;
  /** additive and optional (EXEC-SCREENER-FLOW-CANDLES P6, QA of unit C item 2): the side of a pattern, as the Backtest
      core's candle registry states it (candle-registry.json `side`): bullish, a sign the price may rise, or bearish;
      absent on every entry that has none */
  side?: PatternSide;
}
/** The side of a pattern (CatalogMetric.side). */
export type PatternSide = 'bullish' | 'bearish';
export const PATTERN_SIDES: readonly PatternSide[] = ['bullish', 'bearish'];
/** A flow entry's setup (P5_FLOW.md sections 2 and 3): the registry's family, place, tip and parameters as they are
    (condition false on the kinds that only draw; screener true on a parameter of the Screener's version, text its
    words), each output with its kind of OPERATORS.md section 4 (a letter, or by a parameter, which may again follow
    another parameter) and unit, the default output, the ADV floor flag, version 'screener' for the Screener's version
    of an indicator or its own entry (P5b), and, at this publication, the sessions the indicator reads at its defaults
    (depth; null when not known) and the loaded broker sessions they are measured against (K1). */
export interface CatalogFlow {
  family: string; place: string; tip: string | null; unit: string;
  outputs: { key: string; kind: unknown }[]; default_output: string;
  params: { key: string; label: string; kind: string; status?: string; options?: unknown[]; default?: unknown; min?: number | null; max?: number | null; text?: string; condition: boolean; screener?: boolean }[];
  adv_floor: boolean; needs_classification: boolean;
  version?: 'terminal' | 'screener';
  depth: number | null; sessions: number;
}
/** Session counts of 1M, 3M, 6M and 1Y (P23 a: 21/63/126/252), from screener-metrics.json. */
export type Periods = Record<PerfPeriod, number>;
export interface CatalogPreset {
  id: string; category: string; name: string; why: string; definition: Definition;
  availability: Availability; reason: string | null;
  match_count: number | null; near_count: number | null;   // at versions.price_data; null when unavailable
  unavailable_legs: string[];        // additive: condition ids of the unavailable legs (6.12, 9.2 "naming the unavailable legs")
  /** additive (page O2): the table's default sort when the preset opens (the prototype's per-preset sort; key 'c:<condition
      id>' or a column key); absent = the page's default (match first) */
  view?: SavedView;
}
export interface CatalogResponse {
  versions: Versions; data: DataStatus;
  limits: LimitEntry[];
  indicators: CatalogIndicator[];
  metrics: CatalogMetric[];
  fundamentals: CatalogMetric[];
  periods: Periods;
  groupings: Grouping[];             // the Backtest's groupingsOf over ref/tickers.json.gz; unclassified counted apart
  presets: CatalogPreset[];
  /** additive (EXEC-SCREENER-STOCK-LISTS): the indices and stock groups of the reference file `stock_lists`, the values
      of the universe's indices_* and groups_*; absent from an older worker, whose page offers no list filter */
  stock_lists?: StockListsBlock;
  /** additive (EXEC-SCREENER-FLOW-CANDLES P3): the universal operators the page offers (screener-metrics.json
      operators, each measure with its transform's arguments); absent from an older worker, whose page offers none */
  operators?: CatalogOperators;
}
/** The universal operators of verification/screener/OPERATORS.md as the page offers them: measures (a transform of the
    condition's series, with the transform's arguments and the unit of its result) and tests (how the measured series
    is tested), plus the output types a series made by a transform has (types). */
export interface CatalogOperators {
  types: Record<string, { fns: string[]; words: string }>;
  measures: { id: number; fn: string; label: string; help: string; unit: string | Record<string, string>; not_on: string[]; second?: boolean; short?: string; default: { cmp: string; value: number; range?: [number, number] }; args: CatalogParam[] }[];
  tests: { id: number; key: OperatorTestKey; label: string; help: string; ops: string[]; within?: boolean; length?: boolean; count?: boolean; not_on_units?: string[]; not_on_levels?: boolean; not_on?: string[];
    short?: string; default: { cmp?: string; value?: number; value2?: number; n?: number; k?: number; range?: [number, number] } }[];
  default_measure: string;
}
export type OperatorTestKey = 'value' | 'range' | 'cross' | 'ever' | 'at_least' | 'streak' | 'rank';
/** EXEC-SCREENER-STOCK-LISTS (user 2026-11-09): a list's kind as the publisher writes it (Stock_List.list_kind): INDEX
    a Stockbit Indeks list, KONGLO a Stockbit stock group (konglomerasi; set by Stockbit, not a proof of ownership). */
export type StockListKind = 'INDEX' | 'KONGLO';
export const STOCK_LIST_KINDS: readonly StockListKind[] = ['INDEX', 'KONGLO'];
/** One list of catalog.stock_lists: key the publisher's list_key ('INDEX:550'), code the value a filter names ('LQ45'),
    name and definition as Stock_List holds them (the definition is the source's words, in Indonesian), tickers the
    listed stocks of this publication in it (its members outside the Screener's universe, and non-stocks, are not
    counted), as_of the last complete stockbit-updater round that loaded its members (null before the first). */
export interface StockListEntry { key: string; kind: StockListKind; code: string; name: string; definition: string; tickers: number; as_of: string | null }
/** catalog.stock_lists: AVAILABLE with the lists in the file's order (indices, then groups, each in Stockbit's order),
    or REQUIRES_DATA with no list and the plain reason (the publication has no stock-lists file, or it could not be
    read): an index or group filter is then refused, and the rest of the Screener works as before. as_of: the newest
    as_of of the lists (null when none has one). */
export interface StockListsBlock { availability: 'AVAILABLE' | 'REQUIRES_DATA'; reason: string | null; as_of: string | null; lists: StockListEntry[] }
/** One ticker of the universe, for the page's popover counts (it runs universe.ts on these rows, the worker runs the
    same function in S0; report 8.4). Every listed stock is in it, hidden ones included, so the chips can count what
    they hide (P4). indices / groups (additive, EXEC-SCREENER-STOCK-LISTS): the codes of the INDEX and KONGLO lists the
    stock is a current member of, in catalog.stock_lists order; absent while the stock-lists file is not available
    (an older worker sends none either). */
export interface UniverseRow {
  ticker: string; name: string | null; sector: string | null; industry: string | null;
  last: number | null; chg_1d_pct: number | null; adv20_idr: number | null;
  first_bar: string; last_bar: string; bars: number; stale: boolean; remarks: RowRemark[];
  indices?: string[]; groups?: string[];
}
export interface UniverseResponse { versions: Versions; data: DataStatus; rows: UniverseRow[] }

/* ------------------------------------------------------------------------------------------------------------ */
/* saved items and watchlist (edge-bff store; report 8.7, P12 a)                                                 */
/* ------------------------------------------------------------------------------------------------------------ */

export type ItemKind = 'screen' | 'metric';
/** A saved screen's page state beside its definition (sort and near toggle; report 9.5). */
export interface SavedView { sort?: { key: string; dir: 'asc' | 'desc' }; show_near?: boolean }
/** kind 'screen': the portable definition plus the view; kind 'metric' (My metric): one condition card's test. */
export interface ScreenItemDefinition { definition: Definition; view?: SavedView }
export interface MetricItemDefinition { test: Test }
export const ITEM_ID = /^scr_[0-9a-f]{32}$/;
export interface SavedItem {
  item_id: string; kind: ItemKind; name: string; definition: ScreenItemDefinition | MetricItemDefinition;
  schema_version: number; registry_version: string; screener_registry_version: string; definition_hash: string;
  revision: number; created_at: string; updated_at: string;
  needs_review: { field: string; reason: string }[];      // re-validation on load; nothing is adjusted silently
}
export interface ItemsResponse { items: SavedItem[] }
/** No revision = create; a stale revision answers 409 REVISION_CONFLICT. name: 1-120 characters, trimmed (migration 1). */
export interface PutItemRequest { kind: ItemKind; name: string; definition: ScreenItemDefinition | MetricItemDefinition; revision?: number }
export interface WatchlistResponse { tickers: { ticker: string; added_at: string }[] }
export const TICKER = /^[A-Z0-9]{1,12}$/;              // terminal-api's ticker rule

/* ------------------------------------------------------------------------------------------------------------ */
/* worker private API (report 8.11): header x-screener-worker-key (>= 32 characters) on every route except /health; */
/* private host only; errors in the ApiError shape; no secret in any log.                                         */
/* ------------------------------------------------------------------------------------------------------------ */

export const WORKER_KEY_HEADER = 'x-screener-worker-key';
export const WORKER_KEY_MIN_LENGTH = 32;
/** The opaque owner tag edge-bff sends on every call except /health and /ready (report 8.11, 6d.6): the first 16 hex
    of HMAC-SHA256(SCREENER_WORKER_KEY, owner_key), so the worker can share its threads fairly per owner (at most
    SCREENER_OWNER_INFLIGHT running per tag per replica, round-robin across tags) without learning the owner's key. */
export const WORKER_OWNER_HEADER = 'x-screener-owner';
export const WORKER_OWNER_TAG = /^[0-9a-f]{16}$/;
/** Worker-only refusal (report 8.8 note, 6d.4 rule 3): a request pinned to a data_version newer than the replica holds.
    It never reaches the page: edge-bff retries once on a new connection, then answers 503 SCREENER_NOT_READY with
    Retry-After: 2. */
export type WorkerErrorCode = ErrorCode | 'DATA_VERSION_PENDING';
export const WORKER_ERROR_STATUS: Readonly<Record<WorkerErrorCode, number>> = Object.freeze({ ...ERROR_STATUS, DATA_VERSION_PENDING: 409 });
/** The worker answers these routes gzip-encoded (Content-Encoding: gzip, with an ETag of the JSON bytes); edge-bff
    checks status and content type, reads at most SCREENER_MAX_RESPONSE_BYTES and relays the bytes without parsing a
    2xx body (report 8.11, 6d.5). Error bodies are small JSON and are parsed to map codes. */
export const WORKER_GZIP_ROUTES: readonly string[] = Object.freeze(['POST /v1/run', 'POST /v1/preview', 'POST /v1/counts']);
/** The worker routes edge-bff relays; bodies are the public request and response types above. */
export const WORKER_ROUTES = Object.freeze({
  health: 'GET /health', ready: 'GET /ready',
  catalog: 'GET /v1/catalog', universe: 'GET /v1/universe',
  run: 'POST /v1/run', preview: 'POST /v1/preview', validate: 'POST /v1/validate', counts: 'POST /v1/counts',
} as const);
/** GET /health (no key): liveness, versions, snapshot age and refresh state ('loading' before the first snapshot,
    'refreshing' while a new publication is built; report 8.11, 6d.4). edge-bff polls it at most every 60 s and refetches
    catalog and universe only when price_data or screener_registry changed, replacing them only by a later published_at
    (report 8.4 Caching, 6d.5). */
export interface WorkerHealth {
  ok: boolean; versions: Omit<Versions, 'definition_hash'> | null; published_at: string | null;
  snapshot_age_seconds: number | null; refresh: RefreshState | 'refreshing' | 'loading';
}
/** GET /ready: 200 only with a loaded snapshot; otherwise 503 SCREENER_NOT_READY with retry_after_seconds. */
export interface WorkerReady { ready: boolean; retry_after_seconds?: number }
