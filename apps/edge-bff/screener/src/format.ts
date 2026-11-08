/* Number, money and text formatting of the prototype (screener EDGE layout.html, "formatting"), kept 1:1, plus the
   page's display of a cell value from its unit. Display only: no formula. */

/** one en-US formatter per number of decimals (toLocaleString with options builds a new one on every call, the page's
    largest cost when it draws a table) */
const NF = new Map<number, Intl.NumberFormat>();
const fmtOf = (d: number) => NF.get(d) ?? (NF.set(d, new Intl.NumberFormat('en-US', { minimumFractionDigits:d, maximumFractionDigits:d })), NF.get(d)!);
/** a number with d decimals, en-US grouping, the minus as U+2212; '—' when missing */
export const nf = (v: number | null | undefined, d = 0): string => {
  if (v == null || !isFinite(v)) return '—';
  const s = fmtOf(d).format(v);
  return /^-0(\.0+)?$/.test(s) ? s.slice(1) : s.replace('-', '−');
};
/** a signed number with its unit ('+1.25%') */
export const sgn = (v: number | null | undefined, d = 2, u = '%'): string =>
  v == null || !isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + nf(Math.abs(v), d) + u;
/** rupiah, short (Rp 1.2B, Rp 3.40T) */
export const idr = (v: number | null | undefined): string => {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v), s = a >= 1e12 ? nf(a / 1e12, 2) + 'T' : a >= 1e9 ? nf(a / 1e9, a >= 1e11 ? 0 : 1) + 'B' : a >= 1e6 ? nf(a / 1e6, 1) + 'M' : nf(a);
  return (v < 0 ? '−' : '') + 'Rp ' + s;
};
export const tone = (v: number | null | undefined) => v == null || !isFinite(v) || v === 0 ? '' : v > 0 ? 'up' : 'down';
/** a timestamp in the exchange's zone, WIB (Asia/Jakarta, the zone of the exchange dates): '2026-10-29 19:59 WIB', or
    its date alone. Any ISO 8601 spelling is read (the publisher writes '+00:00' with microseconds, other sources 'Z' or
    no offset, which the contract means as UTC; ERRORS M302); the fraction is cut to milliseconds before parsing so every
    browser reads it the same. A text that is not a timestamp is returned unchanged, a missing one as '—'. */
const WIB = new Intl.DateTimeFormat('en-US', { timeZone:'Asia/Jakarta', year:'numeric', month:'2-digit', day:'2-digit',
  hour:'2-digit', minute:'2-digit', hourCycle:'h23' });
export function timeText(iso: string | null | undefined, dateOnly = false): string {
  if (!iso) return '—';
  const m = /^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d(?::\d\d)?)(\.\d+)?(Z|[+-]\d\d:?\d\d)?$/i.exec(iso.trim());
  const t = m ? Date.parse(`${m[1]}T${m[2]}${m[3] ? m[3].slice(0, 4) : ''}${!m[4] || m[4].toUpperCase() === 'Z' ? 'Z' : m[4].length === 5 ? m[4].slice(0, 3) + ':' + m[4].slice(3) : m[4]}`) : NaN;
  if (!isFinite(t)) return iso;
  const p = Object.fromEntries(WIB.formatToParts(t).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}` + (dateOnly ? '' : ` ${p.hour}:${p.minute} WIB`);
}
/** the prototype's escape for text put into markup (report 9.1: every untrusted string goes through it) */
export const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]!));
/** the prototype's format for values in price, volume or raw index units (xfmt) */
export const xfmt = (v: number) => {
  const a = Math.abs(v);
  return a > 0 && a < 0.01 ? v.toPrecision(3) : a >= 1e12 ? nf(v / 1e12, 2) + 'T' : a >= 1e9 ? nf(v / 1e9, 2) + 'B' : a >= 1e6 ? nf(v / 1e6, 2) + 'M'
    : a >= 1e4 ? nf(v / 1e3, 1) + 'K' : a >= 100 ? nf(v, 0) : a >= 1 ? nf(v, 2) : nf(v, 4);
};
/** IDR in Rp B, as the prototype's Avg value column and its liquidity input */
export const rpB = (idrValue: number | null | undefined, d = 1) => idrValue == null || !isFinite(idrValue) ? '—' : nf(idrValue / 1e9, d) + 'B';

/** A cell's value as text from its unit (contract units: 'percent', '%', 'index', 'price', 'IDR', 'volume', 'ratio',
    'x', 'days', 'pts', ...). Unknown units fall back to the prototype's xfmt. */
export function valueText(v: number | null | undefined, unit: string | null | undefined, signed = false): string {
  if (v == null || !isFinite(v)) return 'n/a';
  const u = (unit || '').toLowerCase();
  if (u === '%' || u === 'percent' || u === 'pct') return signed ? sgn(v, Math.abs(v) >= 100 ? 0 : 1) : nf(v, Math.abs(v) >= 100 ? 0 : 1) + '%';
  if (u === 'index' || u === 'oscillator') return nf(v, Math.abs(v) >= 100 ? 0 : 1);
  if (u === 'fraction') return nf(v, 2);
  if (u === 'x' || u === '×' || u === 'ratio' || u === 'multiple') return nf(v, 2) + '×';
  if (u === 'idr' || u === 'rp') return idr(v);
  if (u === 'pts' || u === 'points') return sgn(v, 1, ' pts');
  if (u === 'days' || u === 'sessions' || u === 'bars') return nf(v, 0);
  if (u === 'rank' || u === 'percentile') return nf(v, 0);
  return xfmt(v);
}
/** the hue of a name (sector tags, logos), as the prototype */
export const hue = (s: string) => { let h = 0; for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) % 360; return h };
export const sectorTag = (s: string | null | undefined) => s ? `<span class="sector" style="--h:${hue(s)}">${esc(s)}</span>` : '<span class="muted">—</span>';
export const slug = (s: string) => s.toLowerCase().replace(/\W+/g, '-').replace(/^-+|-+$/g, '') || 'screen';

/* ---- EXEC-SCREENER-V21 (data audit, report v21/reports/s2_data.md): a value written with the unit the catalog gives
   it. The wire's Cell.unit is the scaling probe's coarse class (registry.ts UNITS: price, price_change, volume,
   price_x_volume, dimensionless, other): a percent distance, ROC, ATR % and historical volatility all arrive as
   'dimensionless', so valueText (above) writes them without '%'. These helpers take the format from the catalog
   (an output's unit plus display_unit, a metric's unit, the test form) and never from Cell.unit alone. Display only. */

/** How a value is written. pct_signed: percent with its sign (+1.25%); pct: percent, no sign forced; index: a plain
    oscillator or 0-100 index; fraction: a ratio such as %B or CMF; multiple: a multiple (1.16×); price: IDR per share
    (index points for IHSG); price_change: a difference of prices, IDR per share; volume: shares; idr: rupiah; count:
    a whole number (sessions, years); rank: a percentile rank; pts: percentage points; raw: a number without a known
    unit (shown as computed). */
export type ValueFormat = 'pct_signed' | 'pct' | 'index' | 'fraction' | 'multiple' | 'price' | 'price_change' | 'volume' | 'idr'
  | 'count' | 'rank' | 'pts' | 'raw';

/** The format of an indicator output, from its catalog `unit` and `display_unit` (each mapping checked against the
    formula in terminal/src/calc/indicators.ts: roc, ppo, trix, pvo, volume_roc x 100; natr 100 x ATR / close;
    hist_vol stdev of returns x sqrt(annualization) x 100; bollinger_width 100 x width / basis; force_index
    EMA(change x volume) in rupiah). `form` is the test form when it is a transform of the output: value_pct_distance
    is a signed percent, value_band_position a percent of the band. */
export function formatOfOutput(unit: string | null | undefined, displayUnit: string | null | undefined, form?: string | null): ValueFormat {
  if (form === 'value_pct_distance') return 'pct_signed';
  if (form === 'value_band_position') return 'pct';
  const u = (unit || '').toLowerCase(), d = (displayUnit || '').toLowerCase();
  if (u === 'price') return 'price';
  if (u === 'price_change') return 'price_change';
  if (u === 'volume') return 'volume';
  if (u === 'price_x_volume') return 'idr';
  if (u !== 'dimensionless') return 'raw';
  if (d === 'percent_signed') return 'pct_signed';
  if (d === 'percent_nonnegative' || d === 'formula_defined_percent_or_fraction' || d === 'ratio_or_percent_defined_by_formula') return 'pct';
  if (d.startsWith('index_0') || d.startsWith('index_minus') || d === 'oscillator') return 'index';
  if (d === 'ratio' || d === 'ratio_signed') return 'fraction';
  return 'raw';
}
/** The format of a non-indicator metric from its catalog unit (screener-metrics.json: '%', 'x', 'IDR', 'IDR per share',
    'sessions', 'years', 'rank', 'pts'; a flow indicator's: 'IDR/tx', 'flag', 'brokers', '0-100', '0-1', '-1..1', 'sd'). */
export function formatOfMetric(unit: string | null | undefined): ValueFormat {
  const u = (unit || '').toLowerCase();
  return u === '%' || u === 'percent' || u === 'pct' ? 'pct_signed' : u === 'x' || u === '×' || u === 'ratio' || u === 'multiple' ? 'multiple'
    : u === 'idr' || u === 'idr/tx' ? 'idr' : u === 'idr per share' || u === 'price' ? 'price' : u === 'volume' || u === 'shares' ? 'volume'
    : u === 'sessions' || u === 'days' || u === 'bars' || u === 'years' || u === 'brokers' || u === 'flag' ? 'count' : u === 'rank' || u === 'percentile' ? 'rank'
    : u === 'pts' || u === 'points' ? 'pts'
    // the Terminal's flow units (flowRegistry.json `unit`, P5c): a 0-100 score, a 0-1 or -1..1 share, a z-score, a difference
    : u === '0-100' ? 'index' : u === '0-1' || u === '-1..1' || u === 'sd' || u === 'diff' ? 'fraction' : 'raw';
}

/** d decimals, widened (up to 4 more) when rounding would turn a value that is not zero into 0 or −0, so a small
    negative never reads as 0; below that it is float noise of a zero and is written as 0 */
function keepDecimals(v: number, d: number): number {
  const a = Math.abs(v);
  if (a === 0 || a >= 0.5 * 10 ** -d) return d;
  for (let k = d + 1; k <= d + 4; k++) if (a >= 0.5 * 10 ** -k) return k;
  return d;
}
const pctDecimals = (v: number) => Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
/** A number in compact notation with its sign (U+2212) and about three significant digits: 1.24M, −15.1M, 980,
    3.40B. No unit: the column header names it (unitWords). */
export function compact(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v), [div, suf] = a >= 1e12 ? [1e12, 'T'] : a >= 1e9 ? [1e9, 'B'] : a >= 1e6 ? [1e6, 'M'] : a >= 1e4 ? [1e3, 'K'] : [1, ''];
  const x = a / div, d = suf ? (x >= 100 ? 0 : x >= 10 ? 1 : 2) : (a >= 100 ? 0 : keepDecimals(a, 2));
  return (v < 0 ? '−' : '') + nf(x, d) + suf;
}
/** A value in its format; '—' when missing (the caller shows n/a with its reason for an NA cell, never this). */
export function fmtValue(v: number | null | undefined, f: ValueFormat): string {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  switch (f) {
    case 'pct_signed': { const d = keepDecimals(v, pctDecimals(v)); return (v > 0 ? '+' : v < 0 ? '−' : '') + nf(a, d) + '%' }
    case 'pct': { const d = keepDecimals(v, pctDecimals(v)); return (v < 0 ? '−' : '') + nf(a, d) + '%' }
    case 'index': { const d = keepDecimals(v, a >= 1000 ? 0 : 1); return (v < 0 ? '−' : '') + nf(a, d) }
    case 'fraction': { const d = keepDecimals(v, 2); return (v < 0 ? '−' : '') + nf(a, d) }
    case 'multiple': return nf(v, keepDecimals(v, 2)) + '×';
    case 'price': return nf(v, a >= 10 ? 0 : 2);
    case 'price_change': { const d = keepDecimals(v, a >= 100 ? 0 : 2); return (v < 0 ? '−' : '') + nf(a, d) }
    case 'volume': return compact(v);
    case 'idr': return idr(v);
    case 'count': case 'rank': return nf(v, 0);
    case 'pts': return sgn(v, 1, ' pts');
    case 'raw': return compact(v);
  }
}
/** The unit of a format in words, for a column header or tooltip ('' for a plain index or fraction, whose name says
    what it is). */
export function unitWords(f: ValueFormat): string {
  return ({ pct_signed:'%', pct:'%', index:'', fraction:'', multiple:'×', price:'IDR per share', price_change:'IDR per share',
    volume:'shares', idr:'IDR', count:'', rank:'percentile', pts:'percentage points', raw:'' } as Record<ValueFormat, string>)[f];
}
/** Whether values in this format compare across stocks (a percent, an index, a ratio) or depend on the stock's price
    level or share count (prices, price differences, volumes, rupiah amounts), so ranking them across stocks misleads. */
export const comparableAcrossStocks = (f: ValueFormat) => f !== 'price' && f !== 'price_change' && f !== 'volume' && f !== 'idr' && f !== 'raw';
