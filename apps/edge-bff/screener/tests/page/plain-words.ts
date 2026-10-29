/* What a user-visible string must never show (AGENTS.md "Gates and evidence" (d); the page, the catalog and the
   refusals speak plain English): the names of the code, not the words of the page. One pattern for every page test
   (tests/page/refusals.test.ts, tests/page/plain-words.test.ts), so a class of internal name is added here once. */
import { CELL_REMARKS, ERROR_CODES, NA_REASONS, ROW_REMARK_CODES } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';

/** every code the contract, the worker or edge-bff answers with or puts in a cell (one-word ones such as TIMEOUT, BUSY
    and STALE included) */
export const CODES: readonly string[] = [...ERROR_CODES, 'DATA_VERSION_PENDING', 'ORIGIN_REJECTED', 'SERVICE_UNAVAILABLE', 'INTERNAL_ERROR',
  ...NA_REASONS, ...ROW_REMARK_CODES, ...CELL_REMARKS];

/** the metric ids of screener-metrics.json that are one lower-case word but no word of the page ("use fpct to compare
    stocks", "read with bandar" was "Bandar balance"): every such id but the ones that are ordinary words the page's
    sentences use (a breakout, the last close, a broker, the bandar thresholds, the length cap, a payout); an id with an
    underscore, a digit or a capital is caught by the patterns below already */
const ID_WORDS = new Set(['breakout', 'breakdown', 'squeeze', 'silent', 'last', 'bars', 'broker', 'bandar', 'breadth', 'cap', 'peg', 'payout', 'car']);
export const METRIC_IDS: readonly string[] = METRICS_CATALOG.metrics.map(m => m.id).filter(id => /^[a-z]+$/.test(id) && !ID_WORDS.has(id));

/** An internal name: a limit, field or file name (snake_case: market_board, compare_lag), a code (UPPER_SNAKE, or any
    code of CODES), a contract path (definition.…, conditions[i]), a camelCase wire name (asOf, divYield), a wire name
    with a digit (value2, top5), a metric id (fpct, topacc: METRIC_IDS), a route (GET universe), a decision, rule or item
    id (P33, D7, M255, U12), a registry, Feature or flow id (I37, F03, FL09), a plan id (EXEC-MCAP) or the service's own
    parts (a replica). */
export const INTERNAL = new RegExp([
  String.raw`\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b`, String.raw`\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b`,
  String.raw`definitions?\.(?=\w)|definitions?\[|conditions\[|universe\.(?=\w)`, `\\b(?:${CODES.join('|')})\\b`,
  String.raw`\b[a-z]+[A-Z][A-Za-z]*\b`, String.raw`\b[a-z]+\d+\b`, `\\b(?:${METRIC_IDS.join('|')})\\b`, String.raw`\b(?:GET|POST|PUT|DELETE) [a-z/]`,
  String.raw`\b(?:P|D|M|U|I|F|FL)\d+\b`, String.raw`\bEXEC-[A-Z0-9]`, String.raw`\breplicas?\b`,
].join('|'));

/** the internal names a string shows (empty when it is plain words) */
export const internalNames = (s: string): string[] => [...s.matchAll(new RegExp(INTERNAL.source, 'g'))].map(m => m[0]);
