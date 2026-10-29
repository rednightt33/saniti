/* The Screener page's own words (report FRONTEND INTEGRATION 9.1: words inside the app stay in the app, as the
   Backtest's api/texts.ts; the shell's words live in static/edge-labels.js). Plain text: the page escapes every string
   it puts into markup (format.ts esc). The API sends codes, never messages for the page to show verbatim where the
   page has its own wording (report 9.2: remarks are worded here from the API's codes). */
import type { CellRemark, ErrorCode, LimitEntry, LimitName, NaReason, RowRemark } from './core/contract.ts';
import { nf } from './format.ts';
import { OPLABEL } from './entries.ts';
import { cardName, type Card } from './forms.ts';
import { ctx as page, entryOf, S } from './state.ts';

export const T = {
  signIn: 'Sign in to EDGE first, then open the Screener tab again.',
  forbidden: 'EDGE refused this request (the session or its token is no longer valid). Reload the page.',
  unreachable: 'The screener service cannot be reached; retry shortly.',
  // waiting states (report 6c.6); every ring is the shared one (terminal/src/ui/spin.ts)
  loadingIndicators: 'Loading indicators',
  loadingPresets: 'Loading presets',
  loadingResults: 'Loading results',
  loadingData: 'Loading data status',
  running: 'Running screen',
  updating: 'Updating…',
  outOfDate: 'Out of date',
  retry: 'Retry',
  // fixed reasons for what has no data (report 9.2 D rows; P11 a: shown disabled with the reason, not removed)
  noIndex: 'No data: index membership (LQ45, IDX30, IDX80, ISSI) is not in the market database.',
  noBoard: 'No data: the listing board (Main, Development) is not in the market database; market_board is the trading board.',
  noCap: 'No data: market cap waits for EXEC-MCAP (shares outstanding), which has no go yet.',
  noFreeFloat: 'No data: free float is not in the market database.',
  noNotation: 'No data: special notation / FCA flags are not in the market database, so this filter is off (P11).',
  noFundamentals: 'No data: fundamentals wait for a data source and its own decision (P11).',
  sendPhase: 'Send to Backtest comes with Phase 1b (its rules, P13, are confirmed first).',
  bandarPhase: 'Not editable here: the bandar thresholds become parameters of each bandar condition when the flow definitions arrive (P9, Phase 3).',
  // P17 consequence (catalog default_offered false: I43 VWAP, whose registry default anchor Session is not offered)
  noDefault: 'The screener does not offer this indicator\'s registry default, so the card opens at the starting parameters shown; change them here.',
  noWatchlistPage: 'Saved in your EDGE watchlist.',
} as const;

/** Why a cell is n/a (contract NaReason), as its tooltip says it. */
export const NA_TEXT: Record<NaReason, string> = {
  INSUFFICIENT_HISTORY: 'n/a: not enough history for this indicator up to the evaluation date',
  NULL_AT_EVALUATION: 'n/a: no value on the evaluation date (flat window, zero band width or zero volume)',
  FLOW_UNAVAILABLE: 'n/a: flow data is not available for this stock',
  FLOW_LAGGED: 'n/a: flow data is older than the price data',
  NOT_APPLICABLE: 'n/a: this metric does not apply to this stock',
  DATA_INTEGRITY: 'n/a: the data failed its integrity check in this publication',
  MIXED_ADJUSTMENT_BASIS: 'n/a: the window crosses an unadjusted corporate action',
};
export const naText = (r: string | null | undefined) => r ? (NA_TEXT as Record<string, string>)[r] || `n/a (${r})` : 'n/a';

const ACTION: Record<string, string> = { STOCK_SPLIT:'stock split', REVERSE_SPLIT:'reverse split', RIGHTS_ISSUE:'rights issue',
  BONUS_SHARES:'bonus shares', STOCK_DIVIDEND:'stock dividend', WARRANT:'warrant' };
export const actionText = (a: string) => ACTION[a] || a.toLowerCase().replace(/_/g, ' ');

/** A row remark (P4), as the Remark column and the preview say it (report 9.2 wording). */
export function remarkText(r: RowRemark): string {
  if (r.code === 'STALE') return `Stale: last trade ${r.last_bar_date}`;
  const ratio = r.ratio_old != null && r.ratio_new != null ? ` (${nf(r.ratio_old, 0)}:${nf(r.ratio_new, 0)})` : '';
  return `Price break: ${actionText(r.action)}${ratio} ex ${r.ex_date}, history not adjusted`;
}
/** The short badge of a remark and its full reason (title). */
export const remarkBadge = (r: RowRemark) => r.code === 'STALE' ? 'Stale' : 'Price break';
export function remarkTitle(r: RowRemark): string {
  if (r.code === 'STALE') return `${remarkText(r)}. The stock is evaluated at its own last bar; its values are shown.`;
  const cr = r.close_ratio != null ? ` Close on the ex-date ÷ the close before: ${nf(r.close_ratio, 3)}.` : '';
  return `${remarkText(r)}. Values whose look-back crosses the ex-date are shown and marked (P4.1 A).${cr} TEMPORARY until the data layer adjusts history (D22).`;
}
/** The CSV's remark cell (report 9.6): the code and its date. */
export const remarkCsv = (rs: RowRemark[]) => rs.map(r => r.code === 'STALE' ? `STALE ${r.last_bar_date}` : `PRICE_BREAK ${r.action} ${r.ex_date}`).join('; ');

/** A cell remark (P4.1 A): the mark's tooltip, naming the ex-date(s) of the row. */
export function cellRemarkText(c: CellRemark, rowRemarks: RowRemark[]): string {
  const ex = rowRemarks.filter(r => r.code === 'PRICE_BREAK').map(r => (r as Extract<RowRemark, { code: 'PRICE_BREAK' }>).ex_date);
  return c === 'PRICE_BREAK_IN_LOOKBACK'
    ? `Distorted: this value's look-back contains the unadjusted ex-date${ex.length ? ' ' + ex.join(', ') : ''}. Shown as computed (P4.1 A).`
    : c;
}

/** The universe chips (P4): label while on, and what the drawer's checkbox says. */
export const chipTraded = (e: string | null) => `Traded on ${e || 'the evaluation date'}`;
export const chipNoBreak = 'No unadjusted price break';

/* ---- refusals (report API CONTRACT 8.8, 8.9; AGENTS.md "Gates and evidence") ---------------------------------------
   A refusal's code, field, details and Retry-After travel; its words are put together here, so that every message names
   where the problem is (the field as a place on the page: the card by its number and name, a parameter by its catalog
   label) and how to fix it. A refusal that points at a limit (details.limit, or the limit its code stands for) is worded
   from that limit's catalog entry (limits[]: the rule, the unit, the fix its refused example names), the entry Method &
   sources lists before the user meets it, so no limit and no number is kept here. The server's message is used only
   where the page has no structured reason (INVALID_INPUT, INVALID_CONDITION, a limit the catalog does not list), with
   its field paths put into the same words. */

/** What a refusal is worded from. `limits`, `cards` and `filters` default to the page's catalog and cards (the
    definition the page sent); a caller wording another definition's refusal passes that one's. */
export interface ErrorContext {
  field?: string | null; details?: Record<string, unknown> | null; retryAfter?: number | null; server?: string;
  limits?: readonly LimitEntry[] | null; cards?: readonly Card[]; filters?: readonly Card[];
}

/** The limit a code stands for when its body names none (report 8.9: the worker deadline answers 504 TIMEOUT, its
    queue 409 BUSY, the request body 413 REQUEST_TOO_LARGE); a body's details.limit always wins. */
const LIMIT_OF_CODE: Partial<Record<ErrorCode, LimitName>> = { TIMEOUT:'deadline_ms', BUSY:'queue', REQUEST_TOO_LARGE:'request_bytes' };

const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s;
/** a clause as a sentence: capitalised, one closing full stop */
const sentence = (s: string) => { const t = s.trim(); return t ? cap(t) + (/[.!?]$/.test(t) ? '' : '.') : '' };
const num = (x: unknown): number | null => typeof x === 'number' && Number.isFinite(x) ? x : null;
const plain = (x: number) => Number.isInteger(x) ? nf(x) : String(x);

/* the place a field names */
/** structural names of the contract's paths that say nothing to the user (the test, its sides, a reference) */
const SILENT = new Set(['definition', 'test', 'metric', 'signal', 'lhs', 'rhs', 'of', 'pattern', 'args']);
/** field names whose name alone does not say it; every other name is worded by fieldWords' rule */
const FIELD_WORDS: Record<string, string> = {
  within:'within (sessions)', value2:'upper value', op:'operator', logic:'match logic', at_least:'match logic (at least)',
  enabled:'on/off switch', body:'request', view:'table view', revision:'saved version', item_id:'saved item',
  client_order:'page order', data_version:'data shown', traded_on_eval_date:chipTraded(null), exclude_price_breaks:chipNoBreak,
};
const AFFIX: Record<string, string> = { in:'included', out:'excluded', min:'minimum', max:'maximum' };
/** A field name in words: underscores to spaces, in/out/min/max first as adjectives, the unit suffix idr dropped, a
    name with digits in capitals (price_min: minimum price; sectors_in: included sectors; adv20_min_idr: minimum ADV20). */
export function fieldWords(k: string): string {
  if (FIELD_WORDS[k]) return FIELD_WORDS[k];
  const w = k.split('_').filter(x => x && x !== 'idr');
  return [...w.filter(x => AFFIX[x]).map(x => AFFIX[x]), ...w.filter(x => !AFFIX[x]).map(x => /\d/.test(x) ? x.toUpperCase() : x)].join(' ');
}
/** A field path walked: its words, the card it names (conditions[i], universe.metric_filters[j]; definitionOf keeps
    card order, switched-off cards included) and the parameter key under that card's params. */
function spot(field: string, o: ErrorContext): { words: string[]; card: Card | null; param: string | null } {
  const cards = o.cards ?? S.cards, filters = o.filters ?? S.universe.filters;
  const words: string[] = [];
  let card: Card | null = null, param: string | null = null, inParams = false;
  for (const seg of field.split('.')) {
    const m = /^(.*?)(?:\[(\d+)\])?$/.exec(seg)!, name = m[1], i = m[2] != null ? Number(m[2]) : null;
    if (inParams) {
      inParams = false; param = name;
      const p = card ? entryOf(card)?.params.find(x => x.key === name) : undefined;
      words.push(p?.label || fieldWords(name)); continue;
    }
    if (name === 'params') { inParams = true; continue }
    if (name === 'conditions' || name === 'metric_filters') {
      const filter = name === 'metric_filters';
      if (filter && words[words.length - 1] === 'the universe') words.pop();
      if (i == null) { words.push(filter ? 'the universe filters' : 'the conditions'); continue }
      card = (filter ? filters : cards)[i] ?? null;
      // the card's name as its header shows it; none while the catalog's entries are not loaded (cardName's 'Condition')
      const named = card ? cardName(entryOf(card), card) : '';
      words.push(`${filter ? 'universe filter' : 'condition'} ${i + 1}${named && named !== 'Condition' ? ` (${named})` : ''}`); continue;
    }
    if (name === 'universe') { words.push('the universe'); continue }
    if (name === 'definitions' && i != null) { words.push(`saved screen ${i + 1}`); continue }
    if (SILENT.has(name)) continue;
    words.push(fieldWords(name) + (i != null ? ` ${i + 1}` : ''));
  }
  return { words, card, param };
}
/** A refusal's field (the contract's path: definition.conditions[1].test.metric.params.length) as the place the page
    shows it: "condition 2 (Relative Strength Index), Length"; '' without a field. */
export const placeText = (field: string | null | undefined, o: ErrorContext = {}): string =>
  field ? spot(field, o).words.join(', ') || 'the screen' : '';
/** the catalog parameter a field names (a card's params.<key>), for a range the refusal does not carry */
function paramOf(field: string | null | undefined, o: ErrorContext) {
  if (!field) return null;
  const s = spot(field, o);
  return s.card && s.param ? entryOf(s.card)?.params.find(p => p.key === s.param) ?? null : null;
}
/** the contract paths in a server message (definition.…, universe.…, conditions[i]…) in the page's words */
const PATH = /\b(?:(?:definition|universe)\.(?=[A-Za-z_])|conditions\[\d+\])[\w.[\]]*/g;
const worded = (s: string, o: ErrorContext) => s.replace(PATH, p => { const t = p.replace(/\.+$/, ''); return placeText(t, o) + p.slice(t.length) });
/** the server's reason in the page's words, led by the place when it does not name it */
function reasonOf(o: ErrorContext, place: string): string {
  const s = o.server ? worded(o.server, o).trim() : '';
  return s ? sentence(place && !s.toLowerCase().includes(place.toLowerCase()) ? `${place}: ${s}` : s) : '';
}

type Range = { min?: number | null; max?: number | null; exclusive_min?: boolean; integer?: boolean; type?: string };
function rangeWords(r: Range): string {
  const lo = num(r.min), hi = num(r.max), what = r.integer || r.type === 'integer' ? 'a whole number' : 'a number';
  if (lo == null && hi == null) return '';
  if (lo != null && hi != null) return r.exclusive_min ? `${what} above ${plain(lo)} and at most ${plain(hi)}` : `${what} from ${plain(lo)} to ${plain(hi)}`;
  return lo != null ? `${what} ${r.exclusive_min ? 'above' : 'of at least'} ${plain(lo)}` : `${what} of at most ${plain(hi!)}`;
}

/* limits */
/** The fix a catalog limit names: the closing parenthesis of its refused example ("… (switch one off or remove it)");
    one that opens with the code it is answered with ("(BUSY: retry in a few seconds)") gives what follows the code,
    which the page words itself; an example without one gives the right example. */
function fixOf(l: LimitEntry): string {
  const m = /\(([^()]*)\)\W*$/.exec(l.example_refused || '');
  const fix = m ? m[1].replace(/^[A-Z][A-Z0-9_]+:\s*/, '').trim() : '';
  return sentence(fix || `allowed: ${l.example_ok}`);
}
/** A refusal that points at a limit, worded from the limit's catalog entry: the lead, the place in the screen (a
    field of the definition; an envelope field such as the ticker or the name is no place, the rule says where), the
    rule, what this request needed (in the entry's unit, its number written as the rule writes the value) and the fix;
    null when the catalog does not list the limit (the caller words it without). */
function limitText(lead: string, name: string | undefined, d: Record<string, unknown>, o: ErrorContext): string | null {
  const l = name ? (o.limits ?? page.catalog?.limits ?? []).find(x => x.name === name) : undefined;
  if (!l) return null;
  const needed = num(d.needed), grouped = l.rule.includes(nf(l.value));
  const need = needed == null ? '' : `; this one needs ${grouped ? nf(needed) : String(needed)} ${l.unit}`;
  return `${lead}${inScreen(o)}: ${l.rule.replace(/[.\s]+$/, '')}${need}. ${fixOf(l)}`;
}
/** " in <place>" for a field of the definition (a path the contract roots at definition, universe or conditions) */
const inScreen = (o: ErrorContext) => {
  const f = o.field || '', p = f.replace(PATH, '') === '' ? placeText(f, o) : '';
  return p ? ` in ${p}` : '';
};
/** what any refusal adds from its details: the costliest condition (as its place) and the wait it names (its
    details.retry_after_seconds, else a Retry-After) */
function extras(d: Record<string, unknown>, o: ErrorContext): string {
  let s = '';
  if (typeof d.costliest === 'string') {
    const i = (o.cards ?? S.cards).findIndex(c => c.id === d.costliest);
    if (i >= 0) s += ` The costliest is ${placeText(`conditions[${i}]`, o)}.`;
  }
  const w = num(d.retry_after_seconds) ?? num(o.retryAfter);
  if (w != null) s += ` Try again in ${plain(Math.max(1, Math.ceil(w)))} s.`;
  return s;
}

/** The page's wording of a refusal or failure from its code (report 8.8, last column; the codes of contract.ts
    ErrorCode, plus edge-bff's own ORIGIN_REJECTED): where the problem is and how to fix it, in plain words. */
export function errorText(code: string, o: ErrorContext = {}): string {
  const d = o.details || {}, place = placeText(o.field, o);
  const limit = (lead: string) => limitText(lead, typeof d.limit === 'string' ? d.limit : LIMIT_OF_CODE[code as ErrorCode], d, o);
  const why = reasonOf(o, place);
  let text: string;
  switch (code) {
    case 'INVALID_INPUT': text = `${why || sentence(`${place || 'the request'} is not in a form the screener accepts`)} Correct it and try again, or reload the page.`; break;
    case 'INVALID_CONDITION': {
      const allowed = Array.isArray(d.allowed) ? d.allowed.map(x => OPLABEL[String(x)] || String(x)) : [];
      text = `${why || sentence(`${place || 'a condition'} is not valid${allowed.length && allowed.length <= 12 ? `: use one of ${allowed.join(', ')}` : ''}`)} Change it and run again.`; break;
    }
    case 'UNKNOWN_INDICATOR':
      text = `${sentence(`${place ? `${place}: ` : ''}this indicator is not in the screener's catalog (it was renamed or removed)`)} Remove the condition, or add it again from the indicator list.`; break;
    case 'PARAM_OUT_OF_RANGE': {
      const r: Range | null = num(d.min) != null || num(d.max) != null ? d as Range : paramOf(o.field, o);
      const range = r ? rangeWords(r) : '';
      text = `${sentence(`${place || 'a parameter'} is out of range${range ? `: use ${range}` : ''}`)} Change it and run again.`; break;
    }
    case 'METRIC_UNAVAILABLE': {
      const id = typeof d.metric === 'string' ? d.metric : '', label = (id && page.byKey.get(id)?.label) || (id ? fieldWords(id) : '');
      const because = typeof d.reason === 'string' ? d.reason.trim().replace(/[.\s]+$/, '') : '';
      const subject = place && label && place.includes(label) ? place : [place, label].filter(Boolean).join(': ') || 'this metric';
      text = `${label || because ? sentence(`${subject} is not available yet${because ? `: ${because}` : ''}`) : why || sentence(`${subject} is not available yet`)} Switch it off or remove it to run the screen.`; break;
    }
    case 'LIMIT_EXCEEDED': {
      const allowed = num(d.allowed), needed = num(d.needed);
      text = limit('Limit reached') ?? (why ? `Limit reached: ${why}`
        : `Limit reached${inScreen(o)}${allowed != null ? `: at most ${plain(allowed)}` : ''}${needed != null ? `, this one needs ${plain(needed)}` : ''}. Reduce it and try again.`); break;
    }
    case 'DATA_UNAVAILABLE': text = 'No published data is loaded yet; it loads after the next publication or within minutes of a restart; try again later.'; break;
    case 'DATA_INTEGRITY': text = 'The latest publication failed its checks and no earlier one is loaded; it retries at the next publication. Try again later.'; break;
    case 'BUSY': text = limit('The screener is busy') ?? 'The screener is busy; retry in a few seconds.'; break;
    case 'SCREEN_REPLACED': case 'PREVIEW_REPLACED': text = 'A newer request of this page replaced this one; its answer follows, nothing to do.'; break;
    case 'DATA_VERSION_CHANGED': text = 'New data was published since the page loaded; the screen runs again on it.'; break;
    case 'REVISION_CONFLICT': text = 'This saved item was changed elsewhere (another tab or device) since it was loaded. Reload it, or save yours as a copy.'; break;
    case 'NAME_TAKEN': text = 'Another saved item of this kind already has this name. Pick another name, or open that item and save over it.'; break;
    case 'NOT_FOUND': text = 'This saved item no longer exists (it was deleted elsewhere); reload the list.'; break;
    case 'REQUEST_TOO_LARGE': text = limit('The request is too large') ?? 'The definition is too large: remove conditions or filters.'; break;
    case 'SCREENER_DISABLED': text = 'The screener is switched off on this EDGE environment; an administrator switches it on. The other EDGE tabs work meanwhile.'; break;
    case 'SCREENER_NOT_READY': return `The screener is starting or loading new data; retry in ${plain(o.retryAfter ?? num(d.retry_after_seconds) ?? 5)} s.`;
    case 'SCREENER_UNAVAILABLE': text = T.unreachable; break;
    case 'TIMEOUT': text = limit('The screen took too long') ?? 'The screen took longer than the limit: use fewer custom conditions or shorter lengths.'; break;
    case 'ORIGIN_REJECTED': text = 'EDGE refused this change because it did not come from the EDGE page itself. Open EDGE at its own address and try again.'; break;
    default: text = `${why || 'The screener could not answer this request.'} Retry; if it fails again, reload the page.`;
  }
  return text + extras(d, o);
}

/** The page head's data line (report 9.2): listings, evaluation date and publication. */
export const dataLine = (listed: number, evalDate: string, published: string) =>
  `IDX equities (${nf(listed)} listings) · close ${evalDate} · published ${published.replace('T', ' ').replace(/:\d\d(\.\d+)?Z$/, ' UTC').replace(/Z$/, ' UTC')}`;

/** "How conditions work", rewritten to the real semantics (report 9.2 Method & sources). */
export const methodText = (evalDate: string) =>
  `VALUE tests read each stock's value on the evaluation date (${evalDate}). STATE tests compare two values on that date. ` +
  `EVENT tests (crosses, breakouts, divergences, flips) pass when the event happened within the chosen number of sessions, ` +
  `counted on the stock's own bars. A stock without a trade on ${evalDate} is stale: it is hidden by default, and when shown ` +
  `it is evaluated at its own last bar with a remark. Near misses are one condition short of the match.`;
