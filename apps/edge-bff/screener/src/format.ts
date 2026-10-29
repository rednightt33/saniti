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
