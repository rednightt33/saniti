/* EXEC-BACKTEST-REVAMP P4: the point-in-time Flow indicators a backtest reads ({"kind":"flow","metric":"FL18",...}),
   their parameters (the Terminal registry's names: flowRegistry.json; anchor for FL18-FL20, FL44, FL45, start for FL23
   and FL51), outputs and refusals, each with the rule, how to pass it and the fix in its message (AGENTS "Gates and
   evidence"):
   - ANCHOR_REQUIRED: the anchor (start) is a date the admin sets (user decision 1A); "view" or nothing is refused;
   - INVALID_ANCHOR: a real date YYYY-MM-DD; ANCHOR_BEFORE_DATA (per stock, at the run): not before its first broker day;
   - RANK_NOT_ALLOWED: FL19 and FL20 rank net buyers only (the implied cost of a position bought);
   - TOP_N_LIMIT: at most 10 brokers (FL19's walk is redone each time the cohort changes: top 20 costs 223 ms a stock);
   - CONDITION_UNAVAILABLE: FL52 (FL23 on the price chart: use FL23); FL51's end (always the candle itself);
   - INVALID_CONDITION: an unknown parameter, option or output, with the ones allowed.
   Defaults are the registry's (calc/flow.ts flowDefaults). */
import { flowDefaults } from '../../../edge-bff/terminal/src/calc/flow.ts';
import { ValidationError } from '../../../edge-bff/backtest/src/core/registry.ts';
import { isIsoDate } from '../../../edge-bff/backtest/src/core/signals.ts';

export const TOP_MAX = 10;
/** The right a request's context must carry to read a point-in-time indicator (user 2026-11-15: admins only; edge-bff
    sets the context from the session, P5; the worker refuses without it, CONDITION_RESTRICTED). */
export const D_RIGHT = 'flow_point_in_time';
const BOARDS = ['Regular', 'Nego', 'Cash'], INVESTORS = ['Foreign', 'Domestic'];
/** price: a price level comparable with the close; pct: a percentage; amount: lots or rupiah; flag: 0/1 */
export type Unit = 'price' | 'pct' | 'amount' | 'flag';
interface Spec { family: 'anchored' | 'inventory' | 'loaders'; date: 'anchor' | 'start'; outputs: Record<string, Unit>; main: string; keys: string[] }
const ANCHORED_KEYS = ['anchor', 'scope', 'brokers', 'top', 'rank', 'boards', 'investors'];
export const D_SPECS: Record<string, Spec> = {
  FL18: { family: 'anchored', date: 'anchor', outputs: { value: 'price', cohort_changed: 'flag' }, main: 'value', keys: ANCHORED_KEYS },
  FL19: { family: 'anchored', date: 'anchor', outputs: { value: 'price', cohort_changed: 'flag' }, main: 'value', keys: ANCHORED_KEYS },
  FL20: { family: 'anchored', date: 'anchor', outputs: { value: 'pct', cohort_changed: 'flag' }, main: 'value', keys: ANCHORED_KEYS },
  FL44: { family: 'anchored', date: 'anchor', outputs: { value: 'price', cohort_changed: 'flag' }, main: 'value', keys: ANCHORED_KEYS },
  FL45: { family: 'anchored', date: 'anchor', outputs: { value: 'pct', cohort_changed: 'flag' }, main: 'value', keys: ANCHORED_KEYS },
  FL23: { family: 'inventory', date: 'start', outputs: { total: 'amount', cohort_changed: 'flag' }, main: 'total', keys: ['start', 'brokers', 'unit', 'view', 'boards', 'investors'] },
  FL51: { family: 'loaders', date: 'start', outputs: { cost: 'price', distance: 'pct', share: 'pct', cohort_changed: 'flag' }, main: 'cost', keys: ['start', 'top', 'cost', 'loader', 'boards', 'investors'] },
};
/** The ids the look-ahead gate finds choosing their brokers with later data (tests/lookahead.test.ts TERMINAL_HINDSIGHT). */
export const D_IDS = [...Object.keys(D_SPECS), 'FL52'].sort();
export const isD = (id: unknown): boolean => typeof id === 'string' && D_IDS.includes(id);

const bad = (code: string, field: string, message: string): never => { throw new ValidationError(code, field, message) };
const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);

export interface DRef { metric: string; output: string; unit: Unit; params: Record<string, unknown> }
/** A point-in-time reference checked and completed (every parameter stated, so the hash reads one form). */
export function checkDRef(ref: Record<string, unknown>, field: string): DRef {
  const id = ref.metric as string;
  if (id === 'FL52') bad('CONDITION_UNAVAILABLE', field, `${field}: FL52 is FL23 on the price chart; in a backtest use FL23 (the same formula) with params.start.`);
  const s = D_SPECS[id];
  for (const k of Object.keys(ref)) if (!['kind', 'metric', 'output', 'params'].includes(k)) bad('INVALID_CONDITION', `${field}.${k}`, `${field}.${k} is not a field of a Flow reference; use kind, metric, output and params.`);
  const output = ref.output === undefined ? s.main : ref.output;
  if (typeof output !== 'string' || !(output in s.outputs)) bad('INVALID_CONDITION', `${field}.output`, `${field}.output: ${JSON.stringify(output)} is not an output of ${id} in a backtest; use one of ${Object.keys(s.outputs).join(', ')}.`);
  if (ref.params !== undefined && !isObj(ref.params)) bad('INVALID_CONDITION', `${field}.params`, `${field}.params must be an object of ${id}'s parameters.`);
  const g = (ref.params ?? {}) as Record<string, unknown>, pf = `${field}.params`;
  if (id === 'FL51' && 'end' in g) bad('CONDITION_UNAVAILABLE', `${pf}.end`, `${pf}.end: in a backtest FL51 reads its loaders up to each day itself (no end date, which would read later days); remove end.`);
  for (const k of Object.keys(g)) if (!s.keys.includes(k)) bad('INVALID_CONDITION', `${pf}.${k}`, `${pf}.${k}: not a parameter of ${id} in a backtest; use only ${s.keys.join(', ')}.`);
  const date = g[s.date];
  if (date === undefined || date === null || date === '' || date === 'view')
    bad('ANCHOR_REQUIRED', `${pf}.${s.date}`, `${field}: ${id} needs params.${s.date}, a date YYYY-MM-DD from which brokers are ${s.family === 'anchored' ? 'ranked' : 'chosen'} (right: "2024-01-02"; wrong: "view" or none).`);
  if (!isIsoDate(date)) bad('INVALID_ANCHOR', `${pf}.${s.date}`, `${pf}.${s.date} must be a real date YYYY-MM-DD, e.g. 2024-01-02 (wrong: ${JSON.stringify(date)}).`);
  const def = flowDefaults(id) as Record<string, unknown>;
  const pick = (k: string) => k in g ? g[k] : def[k];
  const list = (k: string, allowed: string[]) => {
    const v = pick(k);
    if (!Array.isArray(v) || !v.length || v.some(x => !allowed.includes(x as string))) bad('INVALID_CONDITION', `${pf}.${k}`, `${pf}.${k} must be a non-empty list of ${allowed.join(', ')}.`);
    return [...new Set(v as string[])].sort((a, b) => allowed.indexOf(a) - allowed.indexOf(b));
  };
  const codes = (k: string, max: number) => {
    const v = g[k];
    if (!Array.isArray(v) || !v.length || v.length > max || v.some(x => typeof x !== 'string' || !/^[A-Z0-9]{2,4}$/.test(x)))
      bad('INVALID_CONDITION', `${pf}.${k}`, `${pf}.${k} must name 1 to ${max} broker codes (right: ["YP", "AK"]; wrong: []).`);
    return [...new Set(v as string[])].sort();
  };
  const one = <T extends string>(k: string, allowed: readonly T[]): T => {
    const v = pick(k);
    if (!allowed.includes(v as T)) bad('INVALID_CONDITION', `${pf}.${k}`, `${pf}.${k} must be one of ${allowed.join(', ')}.`);
    return v as T;
  };
  const top = (k: string, d: number) => {
    const v = k in g ? g[k] : d, n = typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : v;
    if (!Number.isInteger(n) || (n as number) < 1) bad('INVALID_CONDITION', `${pf}.${k}`, `${pf}.${k} must be a whole number of brokers of at least 1.`);
    if ((n as number) > TOP_MAX) bad('TOP_N_LIMIT', `${pf}.${k}`, `${field}: params.${k} may be at most ${TOP_MAX} for ${id} in a backtest (each change of the brokers walks the history again); use ${TOP_MAX} or fewer.`);
    return n as number;
  };
  const boards = list('boards', BOARDS), investors = list('investors', INVESTORS);
  let params: Record<string, unknown>;
  if (s.family === 'anchored') {
    const scope = one('scope', ['topn', 'selected'] as const);
    const rank = one('rank', ['net_buy', 'gross_buy', 'net_sell'] as const);
    if ((id === 'FL19' || id === 'FL20') && rank !== 'net_buy')
      bad('RANK_NOT_ALLOWED', `${pf}.rank`, `${field}: ${id} is computed for net buyers only (the cost of a position bought); set params.rank to net_buy.`);
    params = { anchor: date, scope, top: top('top', 3), rank, boards, investors, ...(scope === 'selected' ? { brokers: codes('brokers', TOP_MAX) } : {}) };
  } else if (s.family === 'inventory') {
    const b = g.brokers === undefined || g.brokers === 'auto_c' ? 'auto_c' : codes('brokers', 5);
    params = { start: date, brokers: b, unit: one('unit', ['lot', 'value'] as const), view: one('view', ['cum', 'daily'] as const), boards, investors };
  } else {
    const n = top('top', Number(def.top) || 3), loader = 'loader' in g ? g.loader : 0;
    if (!Number.isInteger(loader) || (loader as number) < 0 || (loader as number) > n)
      bad('INVALID_CONDITION', `${pf}.loader`, `${pf}.loader must be 0 (all the loaders, weighted by their lots) or a rank from 1 to ${n}.`);
    params = { start: date, top: n, cost: one('cost', ['avg', 'model'] as const), loader, boards, investors };
  }
  return { metric: id, output, unit: s.outputs[output], params };
}
