/* Refusals of a screen definition (EXEC-SCREENER; report TARGET ARCHITECTURE 6.1 I7, 6.9, 6.12; API CONTRACT 8.5,
   8.8, 8.9). Invalid input is refused with the field and the fix, never clamped, rounded or reordered (I7): the first
   problem is thrown as a ScreenerError (errors.ts) whose `field` is the path in the request body
   ('definition.conditions[2].test.metric.params.length', 'definition.universe.sectors_in[0]') and whose message says
   what to change; details carry the allowed values, the range or the limit (report 8.8):
   - INVALID_INPUT: an unknown field (every object is closed), a wrong JSON type, schema_version other than 1;
   - INVALID_CONDITION: a wrong test shape; between with value > value2 (field value2; value = value2 is accepted); an
     operator or test form the output does not allow (the catalog's tests[].ops); price vs an output that is not
     level_comparable; a within that is not a whole number of at least 1; a duplicate or malformed condition id; logic
     at_least without a whole at_least >= 1; an unknown sector, industry or ticker (refused by name, with the allowed
     list);
   - UNKNOWN_INDICATOR / PARAM_OUT_OF_RANGE: through registry.ts (resolveScreenerParams; the backtest core's
     resolveParams first, then the narrowing and the caps); an enum option the screener does not offer (P17 a: the I43
     anchors Session, Decade and Century, including Session taken as the registry default when anchor is left out) is
     INVALID_CONDITION with the offered options;
   - METRIC_UNAVAILABLE {metric, availability, reason}: a metric whose availability is not AVAILABLE (derived at run
     time from screener-metrics.json `requires` against the files indexed in state.json; report 6.12);
   - LIMIT_EXCEEDED {limit, allowed, needed}: more than max_conditions enabled conditions, more than
     max_metric_filters metric filters (VALUE tests only), a within above within_max (a published limit of 8.9, so its
     rule and examples are in catalog.limits[] before the user meets it).
   The valid ids (indicator ids, transform fn, pattern type, flow and cross-section metric, universe attr) are read from
   the generated registry and screener-metrics.json, never from a list in this file (report 6.9). The normalized
   definition has every parameter resolved (registry defaults filled in); definitionHash is taken over it with the
   labels removed (report 8.3).
   Pure module (no DOM, no Node API). Implemented here: withoutLabels, definitionHash. The rest are typed stubs. */
import { canonicalJson, sha256Hex } from '../../../backtest/src/core/hash.ts';
import type { Availability, CatalogParam, Definition, Grouping, MetricKind, Periods, Test, TestKind, UniverseDef } from './contract.ts';

/** One entry of src/core/screener-metrics.json (report 6.12): the non-indicator metrics (transforms, patterns,
    cross-section, flow, universe attributes, the 32 fundamental metrics) with the Feature_Catalog fields, so a later AI
    onboarding can reuse them. requires: the xsection file and columns the metric reads (null: computed from the price
    snapshot alone); decision: set while the metric waits for a user decision (REQUIRES_DECISION, e.g. P9 bandar);
    applies_to: a predicate on the reference file, e.g. "Industry = Banks" (NOT_APPLICABLE elsewhere). kind: the
    reference kind a condition on it uses, as contract.ts CatalogMetric (one type for both, so the worker serves an
    entry as it is); a fundamental metric is a per-ticker value at E, kind 'universe', group naming it fundamental. */
export interface MetricDefinition {
  id: string; group: string; kind: MetricKind;
  params: CatalogParam[]; tests: TestKind[]; unit: string | null;
  formula: string; interpretation: string; misuse: string; evidence: string;
  requires: { file: string; columns: string[] } | null;
  decision: string | null;
  applies_to: string | null;
}
export interface MetricsCatalog { schema_version: number; periods: Periods; metrics: MetricDefinition[] }

/** Availability of a metric at run time (report 6.12): REQUIRES_DECISION when `decision` is set; REQUIRES_DATA when its
    `requires.file` is not in the state.json xsection index or lacks a column; else AVAILABLE (NOT_APPLICABLE is per
    ticker, from applies_to). reason: a plain sentence naming the file or the decision. */
export function availabilityOf(m: MetricDefinition, index: Readonly<Record<string, { columns?: string[] }>>): { availability: Availability; reason: string | null } {
  throw new Error('not implemented: availabilityOf');
}

/** What validation needs besides the definition. limits: the worker's environment values (report 8.9); capBudgetMs:
    SCREENER_CAP_BUDGET_MS (registry.ts caps); tickers: the listed stocks of the snapshot; groupings: catalog.groupings
    (the allowed sector and industry values); metrics: screener-metrics.json with availability resolved. */
export interface ValidateContext {
  limits: { max_conditions: number; max_metric_filters: number; within_max: number };
  capBudgetMs: number;
  tickers: ReadonlySet<string>;
  groupings: readonly Grouping[];
  metrics: MetricsCatalog;
  availability: ReadonlyMap<string, { availability: Availability; reason: string | null }>;
}

/** The whole definition, normalized (rules above), or the first ScreenerError. `field` is the path of the definition
    in the request body ('definition'). */
export function validateDefinition(input: unknown, ctx: ValidateContext, field = 'definition'): Definition {
  throw new Error('not implemented: validateDefinition');
}
/** One test (a condition card's, a metric filter's or a My metric's), normalized. */
export function validateTest(input: unknown, field: string, ctx: ValidateContext): Test {
  throw new Error('not implemented: validateTest');
}
/** The universe block, normalized (contract.ts UniverseDef; P15 classification values from the groupings). The P4 chips
    traded_on_eval_date and exclude_price_breaks are true when absent (report 8.5 "Default true") and include_unclassified
    false; a present value that is not a boolean is INVALID_INPUT. The normalized block always holds all three, so the
    definition hash of a request that leaves a default out equals that of one that states it. */
export function validateUniverse(input: unknown, field: string, ctx: ValidateContext): UniverseDef {
  throw new Error('not implemented: validateUniverse');
}

/** The definition without condition labels (a label never changes a number, so it never changes the hash). */
export function withoutLabels(d: Definition): Definition {
  return { ...d, conditions: d.conditions.map(({ label: _label, ...c }) => c) };
}
/** definition_hash (report 8.3): sha256 hex of canonicalJson (backtest core hash.ts) of the normalized definition with
    labels removed. The result cache, counts and saved items key on it (report 8.6, 8.10). */
export const definitionHash = (normalized: Definition): Promise<string> => sha256Hex(canonicalJson(withoutLabels(normalized)));
