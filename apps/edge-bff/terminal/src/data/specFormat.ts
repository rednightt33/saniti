/* EDGE Design Spec v1.2, section 6 "Format angka" (user 2026-11-01: "font size dll di standardize mengikuti design specs
   terlampir"): one set of number rules for every place an indicator appears (legend, pane axis, card).
     Pemisah ribuan koma, desimal titik (en-US); minus "−" (U+2212)
     Harga 0 desimal · Perubahan tanda + 2 desimal · Nilai transaksi Rp + B (miliar) / T (triliun), never "M"
     Rasio 1-2 desimal + × · Indikator 1 desimal, parameter in parentheses: RSI (14)
   A value below 0.1 keeps three significant digits (an indicator of 0.0042 does not read 0.0). */
const NF = new Map<number, Intl.NumberFormat>();
const nf = (d: number) => { let f = NF.get(d); if (!f) NF.set(d, f = new Intl.NumberFormat('en-US', { minimumFractionDigits:d, maximumFractionDigits:d })); return f };
const ok = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);
const minus = (s: string) => s.replace(/^-/, '−');

/** a number with d decimals, en-US, minus sign U+2212 */
export function num(v: number | null | undefined, d = 2): string {
  return ok(v) ? minus(nf(d).format(v)) : '–';
}
/** three significant digits for a small value, else d decimals */
export function smart(v: number | null | undefined, d = 1): string {
  if (!ok(v)) return '–';
  /* EXEC-QA5-FIX (QA 2026-11-07, agent 5 F6): a floating-point remainder (an axis tick of 5.55e-17 at the zero line) is 0,
     not "5.55e-17" */
  if (Math.abs(v) < 1e-9) v = 0;
  const a = Math.abs(v);
  if (a > 0 && a < 0.1) return minus(String(Number(v.toPrecision(3))));
  return num(v, d);
}
/** Harga: 0 decimals (IDX prices are whole rupiah) */
export const price = (v: number | null | undefined) => num(v, 0);
/** Perubahan: sign and 2 decimals, "+1.23%" / "−0.40%" */
export const change = (v: number | null | undefined, d = 2) => !ok(v) ? '–' : (v > 0 ? '+' : '') + num(v, d) + '%';
/** an indicator level in percent (1 decimal, no sign): "48.2%" */
export const pctLevel = (v: number | null | undefined) => !ok(v) ? '–' : smart(v, 1) + '%';
/** a difference of two percentages, in percentage points (EXEC-TERMINAL-IND-EDIT: FL11 and FL34 change lines) */
/* EXEC-QA5-FIX (QA F7, Q4): the sign follows the number as shown, so −0.003 reads "0.00 pt", never "−0.00 pt" or "+0.00 pt" */
export const points = (v: number | null | undefined) => { if (!ok(v)) return '–'; const r = +v.toFixed(2) || 0; return (r > 0 ? '+' : '') + num(r, 2) + ' pt' };
/** a change in percent with its sign, as the level's digits: "+7.9%" / "−7.9%" / "0.0%" (QA agent 5 F8: "Change %"
    indicators showed a rise without "+") */
export const pctChange = (v: number | null | undefined) => { if (!ok(v)) return '–'; const t = pctLevel(v); return t.startsWith('−') || /^0(\.0+)?%$/.test(t) ? t : '+' + t };
/** Rasio: 2 decimals and × */
export const ratio = (v: number | null | undefined) => !ok(v) ? '–' : smart(v, 2) + '×';
/** Nilai transaksi: Rp with B (miliar) or T (triliun), 1 decimal; below 1B the whole rupiah */
export function idr(v: number | null | undefined): string {
  if (!ok(v)) return '–';
  const a = Math.abs(v), s = v < 0 ? '−' : '';
  if (a >= 1e12) return `${s}Rp ${nf(a >= 1e13 ? 0 : 1).format(a / 1e12)}T`;
  if (a >= 1e9) return `${s}Rp ${nf(1).format(a / 1e9)}B`;
  return `${s}Rp ${nf(0).format(a)}`;
}
/** Indikator: 1 decimal (a whole count with none; a small value with three significant digits) */
export const indicator = (v: number | null | undefined) => !ok(v) ? '–' : Number.isInteger(v) && Math.abs(v) >= 1000 ? num(v, 0) : smart(v, 1);

/** the rule for an indicator's unit (indRegistry `unit`, flowRegistry `unit`) */
export function byUnit(unit: string): (v: number) => string {
  const u = unit || '';
  if (/^IDR$|IDR\/tx|price_times_volume/.test(u)) return idr;
  if (/^%$|percent/.test(u)) return pctLevel;
  if (/^(x|ratio)$|^ratio_signed$/.test(u)) return ratio;
  if (/^(flag|days|0-1|streak)$/.test(u)) return v => num(v, Number.isInteger(v) ? 0 : 1);
  if (/volume|^lot\|IDR$|^lot\/tx$/.test(u)) return v => Math.abs(v) >= 1e6 ? compact(v) : num(v, Math.abs(v) < 100 ? 1 : 0);
  return indicator;
}
const CF = new Intl.NumberFormat('en-US', { notation:'compact', maximumFractionDigits:1 });
/** a large count (volume): 12.3M shares; not used for rupiah (B/T there) */
export const compact = (v: number | null | undefined) => ok(v) ? minus(CF.format(v)) : '–';

/** an indicator's title with its parameters in parentheses: "RSI (14, close)" */
export const titled = (name: string, params: (string | number | null | undefined)[]) => {
  const p = params.filter(x => x !== '' && x !== null && x !== undefined).map(String);
  return p.length ? `${name} (${p.join(', ')})` : name;
};
