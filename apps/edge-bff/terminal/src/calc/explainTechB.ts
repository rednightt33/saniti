/* EXEC-IND-CARDS IC4: technical explainers (calc/explain.ts: the interface, the helpers and the rule that the card's
   number is the chart's number). One file per part so they can be written side by side; explainTechIndex.ts joins them. */
import type { Explanation, Step, TechExplainer, Term, Unit } from './explain';
import { dateOf, fmt, sourceAt, SOURCES } from './explain';
import type { Bars, Params, Series } from './indicators';
import { DEFAULTS, ema, F, isN } from './indicators';

/* ---- shared pieces of I27-I53 ----
   The card's number is the chart's number to the last digit, so where the chart keeps a running sum (TA-Lib SMA/WMA,
   the reference engine's sma(), TA-Lib MFI) the explainer repeats that running sum from the start of the bar run, and
   recursive state (EMA, Wilder ATR, OBV, A/D ...) is read from the chart's own series at t-1 (calc/indicators.ts F). */
type Vals = Record<string, number>;
interface Last { expr: string; terms: Term[]; combine: (v: Vals) => number | null }

const LENGTH_KEYS = /(^|_)(length|smoothing|smooth_k|smooth_d|periods)$/;
/** the parameters as calc/indicators.ts def() reads them (defaults merged, lengths floored); null = invalid, chart empty */
function prm(key: string, p0: Params): Params | null {
  const p: Params = { ...DEFAULTS[key], ...(p0 || {}) };
  for (const [k, v] of Object.entries(p)) {
    if (LENGTH_KEYS.test(k)) { const n = Math.floor(Number(v)); if (!(n >= 1)) return null; p[k] = n }
    else if (typeof DEFAULTS[key][k] === 'number') { const x = Number(v); if (!Number.isFinite(x)) return null; p[k] = x }
  }
  return p;
}
const NEED: Record<string, string> = { open:'O', high:'H', low:'L', close:'C', hl2:'HL', hlc3:'HLC', ohlc4:'OHLC' };
const srcNeed = (p: Params) => NEED[String(p.source)] || 'C';
/** first bar of the run of bars around t whose inputs are finite (def(): a bar without its inputs restarts the series) */
function segStart(B: Bars, t: number, need: string): number {
  const cols = (['O', 'H', 'L', 'C', 'V'] as const).filter(f => need.includes(f)), ok = (i: number) => cols.every(f => isN(B[f][i]));
  if (!ok(t)) return -1;
  let s = t; while (s > 0 && ok(s - 1)) s--;
  return s;
}
interface At { p: Params; out: Record<string, Series>; o: string; s0: number; s: string }
/** the indicator's parameters, the chart's series, the output asked and the start of the bar run; null when the chart has
    no value at t (warm-up, missing inputs, invalid parameters) */
function at(key: string, need: (p: Params) => string, B: Bars, p0: Params, t: number, output?: string): At | null {
  const p = prm(key, p0); if (!p || !(t >= 0 && t < B.C.length)) return null;
  const out = F[key](B, p) as Record<string, Series>, outs = Object.keys(out).filter(k => !k.startsWith('_'));
  const o = output ?? outs[0];
  if (!outs.includes(o) || !isN(out[o][t])) return null;
  const s0 = segStart(B, t, need(p));
  return s0 < 0 ? null : { p, out, o, s0, s:String(p.source || 'close') };
}
function done(o: string, last: Last, steps: Step[], span?: Explanation['span']): Explanation {
  const value = last.combine(Object.fromEntries(last.terms.map(x => [x.key, x.value])));
  return { output:o, value, expr:last.expr, terms:last.terms, combine:last.combine, steps, ...(span ? { span } : {}) };
}

/* numbers and tables */
const px = (v: number) => fmt.num(v);
const vol = (v: number) => fmt.num(v, 0);
/** about four significant digits (small ratios, weights, per-volume values) */
const fx = (v: number) => {
  if (!isN(v)) return '–';
  const a = Math.abs(v);
  return fmt.num(v, a === 0 || a >= 100 ? 2 : Math.max(2, Math.min(12, 3 - Math.floor(Math.log10(a)))));
};
const lbl = (s: string) => SOURCES[s] || s;
const range = (a: number, b: number) => Array.from({ length:Math.max(0, b - a + 1) }, (_, k) => a + k);
const sumOf = (xs: number[]) => xs.reduce((a, v) => a + v, 0);
const short = (rows: string[][]) => rows.length > 12 ? [...rows.slice(0, 5), rows[0].map((_, j) => j ? '' : '…'), ...rows.slice(-5)] : rows;
const table = (B: Bars, idx: number[], head: string[], cells: (i: number, k: number) => string[]) =>
  ({ head:['Tanggal', ...head], rows:short(idx.map((i, k) => [dateOf(B, i), ...cells(i, k)])) });
const windowSpan = (B: Bars, a: number, t: number) => ({ from:dateOf(B, a), to:dateOf(B, t), candles:t - a + 1 });
const prevOf = (S: Series, t: number, s0: number) => t - 1 >= s0 && isN(S[t - 1]) ? S[t - 1] as number : null;
const chain = (B: Bars, s0: number) => `Nilainya berantai sejak candle pertama data (${dateOf(B, s0)}): setiap candle memperbarui nilai sebelumnya, jadi seluruh riwayat ikut terbawa.`;
const nTerm = (n: number): Term => ({ key:'n', label:'Panjang (n)', value:n, unit:'count' });

/* running sums exactly as the chart keeps them */
/** reference engine sma() (calc/indicators.ts sma): the sum it divides at t; a null restarts it; null before n values */
function htmlSum(x: (i: number) => number | null, from: number, t: number, n: number): number | null {
  let s = 0, run = 0;
  for (let i = from; i <= t; i++) { const v = x(i); if (!isN(v)) { s = 0; run = 0; continue } s += v; run++; if (run > n) s -= x(i - n) as number }
  return run >= n ? s : null;
}
/** TA-Lib SMA (calc/indicators.ts kSma) on the run of finite values starting at r0: the sum it divides at t */
function taSum(x: (i: number) => number, r0: number, t: number, n: number): number {
  let s = 0; for (let i = r0; i < r0 + n - 1; i++) s += x(i);
  for (let i = r0 + n - 1; ; i++) { s += x(i); if (i >= t) return s; s -= x(i - n + 1) }
}
/** TA-Lib WMA (calc/indicators.ts kWma) on the run starting at r0: the weighted sum it divides at t */
function taWsum(x: (i: number) => number, r0: number, t: number, n: number): number {
  if (n === 1) return x(t);
  let pSub = 0, pSum = 0, tv = 0, tr = r0, i = r0;
  for (; i < r0 + n - 1; i++) { pSub += x(i); pSum += x(i) * (i - r0 + 1) }
  for (; ; i++) { pSub += x(i); pSub -= tv; pSum += x(i) * n; tv = x(tr++); if (i >= t) return pSum; pSum -= pSub }
}

/* last steps shared by several indicators */
const sumLast = (SUM: number, n: number, label: string, unit: Unit): Last =>
  ({ expr:'SUM ÷ n', terms:[{ key:'SUM', label, value:SUM, unit }, nTerm(n)], combine:v => v.n ? v.SUM / v.n : null });
const wmaLast = (WS: number, D: number, label: string, unit: Unit): Last =>
  ({ expr:'WS ÷ D', terms:[{ key:'WS', label, value:WS, unit }, { key:'D', label:'Jumlah bobot n(n + 1) ÷ 2', value:D, unit:'count' }], combine:v => v.D ? v.WS / v.D : null });
/** TA-Lib EMA step (calc/indicators.ts kEma): (x − E₋₁) × α + E₋₁, α = 2 ÷ (n + 1) */
function kEmaLast(E: string, X: string, prev: number, x: number, n: number, labels: [string, string], unit: Unit): Last {
  const P = E + '₋₁';
  return { expr:`${P} + α × (${X} − ${P})`, combine:v => (v[X] - v[P]) * v['α'] + v[P],
    terms:[{ key:P, label:labels[0], value:prev, unit }, { key:X, label:labels[1], value:x, unit }, { key:'α', label:`Bobot α = 2 ÷ (${n} + 1)`, value:2 / (n + 1), unit:'num' }] };
}
/** reference engine EMA/RMA step (calc/indicators.ts ewm): α × x + (1 − α) × E₋₁ */
function ewmLast(E: string, X: string, prev: number, x: number, a: number, aLabel: string, labels: [string, string], unit: Unit): Last {
  const P = E + '₋₁';
  return { expr:`α × ${X} + (1 − α) × ${P}`, combine:v => v['α'] * v[X] + (1 - v['α']) * v[P],
    terms:[{ key:P, label:labels[0], value:prev, unit }, { key:X, label:labels[1], value:x, unit }, { key:'α', label:aLabel, value:a, unit:'num' }] };
}
/** one line on a TA-Lib EMA series S (seeded with the mean of its first n values) at t */
function kEmaText(B: Bars, S: Series, t: number, s0: number, n: number, name: string, xName: string, x: number, f: (v: number) => string) {
  const prev = prevOf(S, t, s0), a = 2 / (n + 1);
  return prev === null ? `${name} dimulai di candle ini: rata-rata ${n} nilai pertama = ${f(S[t] as number)}.`
    : `${name} = ${name}₋₁ + α × (${xName} − ${name}₋₁) = ${f(prev)} + ${fx(a)} × (${f(x)} − ${f(prev)}) = ${f(S[t] as number)} (α = 2 ÷ (${n} + 1), ${name}₋₁ dari ${dateOf(B, t - 1)}).`;
}
/** one line on a reference-engine EMA series S at index k of a run (prev at k-1) */
function ewmText(S: Series, k: number, n: number, name: string, xName: string, x: number, f: (v: number) => string) {
  const prev = k > 0 && isN(S[k - 1]) ? S[k - 1] as number : null, a = 2 / (n + 1);
  return prev === null ? `${name} dimulai di candle ini: rata-rata ${n} nilai pertama = ${f(S[k] as number)}.`
    : `${name} = α × ${xName} + (1 − α) × ${name}₋₁ = ${fx(a)} × ${f(x)} + ${fx(1 - a)} × ${f(prev)} = ${f(S[k] as number)} (α = 2 ÷ (${n} + 1)).`;
}
const trOf = (B: Bars, i: number) => Math.max(B.H[i] - B.L[i], Math.abs(B.C[i - 1] - B.H[i]), Math.abs(B.C[i - 1] - B.L[i]));
const trText = (B: Bars, t: number) => `H = ${px(B.H[t])}, L = ${px(B.L[t])}, close sebelumnya C₋₁ = ${px(B.C[t - 1])}. TR = max(H − L, |H − C₋₁|, |L − C₋₁|) = max(${px(B.H[t] - B.L[t])}, ${px(Math.abs(B.H[t] - B.C[t - 1]))}, ${px(Math.abs(B.L[t] - B.C[t - 1]))}) = ${px(trOf(B, t))}.`;
const mfmOf = (B: Bars, i: number) => B.H[i] === B.L[i] ? 0 : ((B.C[i] - B.L[i]) - (B.H[i] - B.C[i])) / (B.H[i] - B.L[i]);

/* ---- I27-I29: the bands (calc/indicators.ts bands). Basis = the MA type over n values of the source; SD = TA-Lib's
   population stdev around the window SMA, the chart's own value (F.stddev runs the same kStd); bands = basis ± k × SD ---- */
function bandsAt(B: Bars, a: At, t: number) {
  const { p, s0, s } = a, n: number = p.length, k: number = p.std_dev, type = String(p.basis_ma_type);
  const kind = ['EMA', 'WMA', 'RMA', 'VWMA'].includes(type) ? type : 'SMA';
  const bb = F.bollinger(B, p), SD = F.stddev(B, { length:n, source:s, stdev_method:'population' }).stddev[t] as number;
  const i0 = t - n + 1, idx = range(i0, t), X = (i: number) => sourceAt(B, s, i) as number, xs = idx.map(X), x = X(t);
  const mean = sumOf(xs) / n, SS = sumOf(xs.map(v => (v - mean) ** 2));
  let basis: Last, text: string;
  if (kind === 'SMA') {
    const SUM = taSum(X, s0, t, n);
    basis = sumLast(SUM, n, `Jumlah ${lbl(s)} ${n} candle`, 'price');
    text = `Rata-rata sederhana ${n} candle: ${px(SUM)} ÷ ${n} = ${px(SUM / n)}.`;
  } else if (kind === 'WMA') {
    const WS = taWsum(X, s0, t, n), D = (n * (n + 1)) >> 1;
    basis = wmaLast(WS, D, `Jumlah ${lbl(s)} × bobot (terbaru ${n}, terlama 1)`, 'price');
    text = `Rata-rata berbobot linear: bobot ${n} untuk candle terbaru sampai 1 untuk yang terlama; ${px(WS)} ÷ ${D} = ${px(WS / D)}.`;
  } else if (kind === 'VWMA') {
    const V = (i: number) => B.V[i], SPV = htmlSum(i => isN(X(i)) && isN(V(i)) ? X(i) * V(i) : null, s0, t, n) as number, SV = htmlSum(V, s0, t, n) as number;
    basis = { expr:'ΣPV ÷ ΣV', terms:[{ key:'ΣPV', label:`Jumlah ${lbl(s)} × volume ${n} candle`, value:SPV, unit:'num' }, { key:'ΣV', label:`Jumlah volume ${n} candle`, value:SV, unit:'count' }],
      combine:v => v['ΣV'] ? (v['ΣPV'] / n) / (v['ΣV'] / n) : null };
    text = `Rata-rata berbobot volume: Σ(${lbl(s)} × V) ÷ ΣV = ${fx(SPV)} ÷ ${vol(SV)} = ${px(SPV / SV)}.`;
  } else {
    const prev = prevOf(bb.basis, t, s0);
    if (prev === null) {
      basis = sumLast(sumOf(xs), n, `Jumlah ${n} ${lbl(s)} pertama`, 'price');
      text = `${kind} dimulai di candle ini dengan rata-rata ${n} nilai pertama: ${px(sumOf(xs))} ÷ ${n} = ${px(sumOf(xs) / n)}.`;
    } else if (kind === 'EMA') {
      basis = kEmaLast('EMA', 'src', prev, x, n, [`EMA candle sebelumnya (${dateOf(B, t - 1)})`, `${lbl(s)} candle ini`], 'price');
      text = `EMA₋₁ = ${px(prev)}; ${px(prev)} + ${fx(2 / (n + 1))} × (${px(x)} − ${px(prev)}) = ${px(bb.basis[t] as number)}. ${chain(B, s0)}`;
    } else {
      basis = ewmLast('RMA', 'src', prev, x, 1 / n, `Bobot α = 1 ÷ ${n}`, [`RMA candle sebelumnya (${dateOf(B, t - 1)})`, `${lbl(s)} candle ini`], 'price');
      text = `RMA₋₁ = ${px(prev)}; ${fx(1 / n)} × ${px(x)} + ${fx(1 - 1 / n)} × ${px(prev)} = ${px(bb.basis[t] as number)}. ${chain(B, s0)}`;
    }
  }
  const steps: Step[] = [
    { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}, nilai ${lbl(s)} setiap candle (x).`,
      table:table(B, idx, [lbl(s), '(x − x̄)²'], (_, j) => [px(xs[j]), px((xs[j] - mean) ** 2)]) },
    { title:`Basis (${kind} ${n})`, text },
  ];
  const sdStep: Step = { title:'Simpangan baku (SD)', text:`Rata-rata jendela x̄ = ${px(mean)}; jumlah (x − x̄)² = ${px(SS)}. SD = √(${px(SS)} ÷ ${n}) = ${px(SD)} (simpangan baku populasi, dibagi n${kind === 'SMA' ? '' : '; tetap terhadap rata-rata sederhana x̄, seperti TA-Lib'}).` };
  const span = kind === 'EMA' || kind === 'RMA' ? undefined : windowSpan(B, i0, t);
  return { n, k, s, kind, x, SD, basis, steps, sdStep, span, bb };
}
function bandLast(r: ReturnType<typeof bandsAt>, t: number, up: boolean): Last {
  return { expr:up ? 'basis + k × SD' : 'basis − k × SD', combine:up ? v => v.basis + v.SD * v.k : v => v.basis - v.SD * v.k,
    terms:[{ key:'basis', label:`Basis (${r.kind} ${r.n})`, value:r.bb.basis[t] as number, unit:'price' },
           { key:'k', label:'Pengali simpangan baku (k)', value:r.k, unit:'num' },
           { key:'SD', label:`Simpangan baku ${r.n} candle`, value:r.SD, unit:'price' }] };
}
const bandStep = (r: ReturnType<typeof bandsAt>, t: number, up: boolean): Step => {
  const b = r.bb.basis[t] as number, v = (up ? r.bb.upper : r.bb.lower)[t] as number;
  return { title:up ? 'Pita atas' : 'Pita bawah', text:`basis ${up ? '+' : '−'} k × SD = ${px(b)} ${up ? '+' : '−'} ${fmt.num(r.k)} × ${px(r.SD)} = ${px(v)}.` };
};

/* ---- I30 ATR (and I31 NATR): TR from the second bar of the run (TA-Lib), smoothed by the chosen average ---- */
function atrAt(B: Bars, n: number, type: string, t: number, s0: number): { last: Last; steps: Step[]; span?: Explanation['span'] } {
  const kind = type === 'SMA' || type === 'EMA' || type === 'WMA' ? type : 'RMA', S = F.atr(B, { length:n, smoothing_type:type }).atr;
  const TR = trOf(B, t), trStep: Step = { title:'True range (TR) candle ini', text:trText(B, t) };
  const trs = (a: number) => ({ idx:range(a, t), tbl:table(B, range(a, t), ['H', 'L', 'C₋₁', 'TR'], i => [px(B.H[i]), px(B.L[i]), px(B.C[i - 1]), px(trOf(B, i))]) });
  const T = (i: number) => trOf(B, i);
  if (kind === 'RMA' && n <= 1) {
    const last: Last = { expr:'max(H − L, |H − C₋₁|, |L − C₋₁|)', combine:v => Math.max(v.H - v.L, Math.abs(v['C₋₁'] - v.H), Math.abs(v['C₋₁'] - v.L)),
      terms:[{ key:'H', label:'High candle ini', value:B.H[t], unit:'price' }, { key:'L', label:'Low candle ini', value:B.L[t], unit:'price' }, { key:'C₋₁', label:'Close candle sebelumnya', value:B.C[t - 1], unit:'price' }] };
    return { last, steps:[trStep, { title:'Dengan n = 1', text:`ATR = TR candle ini = ${px(TR)}.` }] };
  }
  const prev = prevOf(S, t, s0);
  if (kind === 'SMA' || kind === 'WMA' || prev === null) {                 // a window of n TR (SMA, WMA, or the seed of RMA/EMA)
    const w = trs(t - n + 1), seed = kind === 'RMA' || kind === 'EMA';
    const last = kind === 'WMA' ? wmaLast(taWsum(T, s0 + 1, t, n), (n * (n + 1)) >> 1, `Jumlah TR × bobot (terbaru ${n}, terlama 1)`, 'price')
      : sumLast(kind === 'SMA' ? taSum(T, s0 + 1, t, n) : sumOf(w.idx.map(T)), n, seed ? `Jumlah ${n} TR pertama` : `Jumlah TR ${n} candle`, 'price');
    const S1 = last.terms[0].value, D = last.terms[1].value;
    return { last, span:seed ? undefined : windowSpan(B, t - n, t), steps:[trStep,
      { title:seed ? `${n} TR pertama` : `TR ${n} candle terakhir`, text:seed ? `ATR dimulai di candle ini (${kind}): rata-rata ${n} TR pertama sejak ${dateOf(B, s0 + 1)}; candle pertama data tidak punya TR.` : `${dateOf(B, t - n + 1)} sampai ${dateOf(B, t)}.`, table:w.tbl },
      { title:kind === 'WMA' ? 'Rata-rata berbobot' : 'Bagi dengan n', text:kind === 'WMA' ? `Bobot ${n} untuk TR terbaru sampai 1 untuk yang terlama: ${px(S1)} ÷ ${D} = ${px(S1 / D)}.` : `${px(S1)} ÷ ${n} = ${px(S1 / n)}.` }] };
  }
  if (kind === 'EMA') {
    const last = kEmaLast('ATR', 'TR', prev, TR, n, [`ATR candle sebelumnya (${dateOf(B, t - 1)})`, 'True range candle ini'], 'price');
    return { last, steps:[trStep, { title:'ATR sebelumnya', text:`ATR₋₁ = ${px(prev)}. ${chain(B, s0)}` },
      { title:'Haluskan (EMA)', text:`${px(prev)} + ${fx(2 / (n + 1))} × (${px(TR)} − ${px(prev)}) = ${px(S[t] as number)}.` }] };
  }
  const last: Last = { expr:'(ATR₋₁ × (n − 1) + TR) ÷ n', combine:v => v.n ? (v['ATR₋₁'] * (v.n - 1) + v.TR) / v.n : null,
    terms:[{ key:'ATR₋₁', label:`ATR candle sebelumnya (${dateOf(B, t - 1)})`, value:prev, unit:'price' }, { key:'TR', label:'True range candle ini', value:TR, unit:'price' }, nTerm(n)] };
  return { last, steps:[trStep, { title:'ATR sebelumnya', text:`ATR₋₁ = ${px(prev)}. ATR dimulai di ${dateOf(B, s0 + n)} dengan rata-rata ${n} TR pertama. ${chain(B, s0)}` },
    { title:'Haluskan (Wilder)', text:`(${px(prev)} × (${n} − 1) + ${px(TR)}) ÷ ${n} = ${px(S[t] as number)}.` }] };
}

/* ---- I43 VWAP: sums from the start of the anchor period (calc/indicators.ts vwap, the same order of operations) ---- */
const ANCHOR: Record<string, string> = { Session:'sesi', Week:'minggu', Month:'bulan', Quarter:'kuartal', Year:'tahun', Decade:'dekade', Century:'abad' };

/* ---- I52 KVO: the volume force of each bar of the run (calc/indicators.ts kvo, the same order of operations) ---- */
function kvoForce(B: Bars, s0: number, t: number) {
  const vf: (number | null)[] = [null]; let trend = 0, cm = 0, dmPrev = 0, last = { tr:0, trendPrev:0, dm:0, cm:0 };
  for (let i = s0 + 1; i <= t; i++) {
    const s = B.H[i] + B.L[i] + B.C[i], sp = B.H[i - 1] + B.L[i - 1] + B.C[i - 1], tr = s > sp ? 1 : s < sp ? -1 : trend, dm = B.H[i] - B.L[i];
    cm = i === s0 + 1 ? dm : (tr === trend ? cm + dm : dmPrev + dm);
    vf.push(cm ? B.V[i] * Math.abs(2 * (dm / cm - 1)) * tr * 100 : 0);
    last = { tr, trendPrev:trend, dm, cm };
    trend = tr; dmPrev = dm;
  }
  return { vf, ...last };
}

/* I27-I53 (see explainTechA.ts for the reference) */
export const TECH_EXPLAIN_B: Record<string, TechExplainer> = {
  /* I27 Bollinger Bands: upper/lower = basis ± k × SD, basis = SMA (or the chosen MA) of n values (calc/indicators.ts bands) */
  bollinger: (B, p0, t, output) => {
    const a = at('bollinger', srcNeed, B, p0, t, output); if (!a) return null;
    const r = bandsAt(B, a, t);
    if (a.o === 'basis') return done('basis', r.basis, [...r.steps, { title:'Hasil', text:`Basis = ${px(r.bb.basis[t] as number)}.` }], r.span);
    const up = a.o === 'upper';
    return done(a.o, bandLast(r, t, up), [...r.steps, r.sdStep, bandStep(r, t, up)], r.span);
  },
  /* I28 Bollinger %B = (src − lower) ÷ (upper − lower), bands as I27 */
  bollinger_pctb: (B, p0, t, output) => {
    const a = at('bollinger_pctb', srcNeed, B, p0, t, output); if (!a) return null;
    const r = bandsAt(B, a, t), U = r.bb.upper[t] as number, L = r.bb.lower[t] as number;
    const last: Last = { expr:'(src − lower) ÷ (upper − lower)', combine:v => v.upper - v.lower !== 0 ? (v.src - v.lower) / (v.upper - v.lower) : null,
      terms:[{ key:'src', label:`${lbl(r.s)} candle ini`, value:r.x, unit:'price' }, { key:'lower', label:'Pita bawah', value:L, unit:'price' }, { key:'upper', label:'Pita atas', value:U, unit:'price' }] };
    const v = last.combine({ src:r.x, lower:L, upper:U });
    return done(a.o, last, [...r.steps, r.sdStep, bandStep(r, t, true), bandStep(r, t, false),
      { title:'Posisi harga di antara pita', text:`(${px(r.x)} − ${px(L)}) ÷ (${px(U)} − ${px(L)}) = ${fx(v)}. Nilai 0 berarti di pita bawah, 1 di pita atas, 0,5 di basis.` }], r.span);
  },
  /* I29 Bollinger Bandwidth = 100 × (upper − lower) ÷ basis, bands as I27 */
  bollinger_width: (B, p0, t, output) => {
    const a = at('bollinger_width', srcNeed, B, p0, t, output); if (!a) return null;
    const r = bandsAt(B, a, t), U = r.bb.upper[t] as number, L = r.bb.lower[t] as number, M = r.bb.basis[t] as number;
    const last: Last = { expr:'100 × (upper − lower) ÷ basis', combine:v => v.basis ? 100 * ((v.upper - v.lower) / v.basis) : null,
      terms:[{ key:'upper', label:'Pita atas', value:U, unit:'price' }, { key:'lower', label:'Pita bawah', value:L, unit:'price' }, { key:'basis', label:`Basis (${r.kind} ${r.n})`, value:M, unit:'price' }] };
    return done(a.o, last, [...r.steps, r.sdStep, bandStep(r, t, true), bandStep(r, t, false),
      { title:'Lebar pita terhadap basis', text:`100 × (${px(U)} − ${px(L)}) ÷ ${px(M)} = ${fmt.num(100 * ((U - L) / M))}%.` }], r.span);
  },
  /* I30 ATR: Wilder average of TR seeded with the mean of the first n TR (TA-Lib); other smoothing types on request */
  atr: (B, p0, t, output) => {
    const a = at('atr', () => 'HLC', B, p0, t, output); if (!a) return null;
    const r = atrAt(B, a.p.length, a.p.smoothing_type, t, a.s0);
    return done(a.o, r.last, r.steps, r.span);
  },
  /* I31 NATR = ATR ÷ C × 100 (0 when C is 0), ATR as I30 */
  natr: (B, p0, t, output) => {
    const a = at('natr', () => 'HLC', B, p0, t, output); if (!a) return null;
    const r = atrAt(B, a.p.length, a.p.smoothing_type, t, a.s0), ATR = r.last.combine(Object.fromEntries(r.last.terms.map(x => [x.key, x.value]))) as number, C = B.C[t];
    const last: Last = { expr:'ATR ÷ C × 100', combine:v => Math.abs(v.C) < 1e-14 ? 0 : (v.ATR / v.C) * 100,
      terms:[{ key:'ATR', label:`ATR ${a.p.length}`, value:ATR, unit:'price' }, { key:'C', label:'Close candle ini', value:C, unit:'price' }] };
    return done(a.o, last, [...r.steps, { title:'Nyatakan dalam persen close', text:`${px(ATR)} ÷ ${px(C)} × 100 = ${fmt.num(Math.abs(C) < 1e-14 ? 0 : (ATR / C) * 100)}%.` }], r.span);
  },
  /* I32 Standard deviation: population (TA-Lib STDDEV, the chart's own value) or sample (n − 1) of n values */
  stddev: (B, p0, t, output) => {
    const a = at('stddev', srcNeed, B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, s = a.s, sample = a.p.stdev_method === 'sample', i0 = t - n + 1, idx = range(i0, t), xs = idx.map(i => sourceAt(B, s, i) as number);
    let m = 0; for (let j = 0; j < n; j++) m += xs[n - 1 - j]; m /= n;                  // newest first, as calc/indicators.ts stdev
    let ss = 0; for (let j = 0; j < n; j++) ss += (xs[n - 1 - j] - m) ** 2;
    const SD = a.out.stddev[t] as number, SS = sample ? ss : n * SD * SD;               // population: TA-Lib's variance × n
    const last: Last = sample
      ? { expr:'√(SS ÷ (n − 1))', terms:[{ key:'SS', label:'Jumlah kuadrat selisih dari rata-rata', value:SS, unit:'price' }, nTerm(n)], combine:v => v.n > 1 && v.SS >= 0 ? Math.sqrt(v.SS / (v.n - 1)) : null }
      : { expr:'√(SS ÷ n)', terms:[{ key:'SS', label:'Jumlah kuadrat selisih dari rata-rata', value:SS, unit:'price' }, nTerm(n)], combine:v => v.n >= 1 && v.SS >= 0 ? Math.sqrt(v.SS / v.n) : null };
    return done(a.o, last, [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}, nilai ${lbl(s)} setiap candle (x).`, table:table(B, idx, [lbl(s), '(x − x̄)²'], (_, j) => [px(xs[j]), px((xs[j] - m) ** 2)]) },
      { title:'Rata-rata', text:`x̄ = ${px(sumOf(xs))} ÷ ${n} = ${px(m)}.` },
      { title:'Jumlah kuadrat selisih', text:`SS = Σ(x − x̄)² = ${px(SS)}.` },
      { title:sample ? 'Bagi dengan n − 1, lalu akar' : 'Bagi dengan n, lalu akar', text:sample ? `√(${px(SS)} ÷ ${n - 1}) = ${px(SD)} (simpangan baku sampel).` : `√(${px(SS)} ÷ ${n}) = ${px(SD)} (simpangan baku populasi, seperti TA-Lib).` },
    ], windowSpan(B, i0, t));
  },
  /* I33 Historical volatility: population stdev of n returns × √A × 100 (calc/indicators.ts hist_vol) */
  hist_vol: (B, p0, t, output) => {
    const a = at('hist_vol', srcNeed, B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, s = a.s, A: number = a.p.annualization_periods, simple = a.p.return_type === 'simple', X = (i: number) => sourceAt(B, s, i) as number;
    const ret = (i: number) => simple ? X(i) / X(i - 1) - 1 : Math.log(X(i) / X(i - 1)), idx = range(t - n + 1, t), rs = idx.map(ret);
    let m = 0; for (let j = 0; j < n; j++) m += rs[n - 1 - j]; m /= n;                  // newest first, as calc/indicators.ts stdev
    let ss = 0; for (let j = 0; j < n; j++) ss += (rs[n - 1 - j] - m) ** 2;
    const SD = Math.sqrt(ss / n);
    const last: Last = { expr:'SD × √A × 100', combine:v => v.A >= 0 ? v.SD * Math.sqrt(v.A) * 100 : null,
      terms:[{ key:'SD', label:`Simpangan baku ${n} return`, value:SD, unit:'num' }, { key:'A', label:'Periode setahun (A)', value:A, unit:'count' }] };
    return done(a.o, last, [
      { title:`Return ${n} candle terakhir`, text:`r = ${simple ? `${lbl(s)} ÷ ${lbl(s)}₋₁ − 1` : `ln(${lbl(s)} ÷ ${lbl(s)}₋₁)`} setiap candle, ${dateOf(B, t - n + 1)} sampai ${dateOf(B, t)} (${n} return dari ${n + 1} candle).`,
        table:table(B, idx, [lbl(s), 'r'], (i, j) => [px(X(i)), fmt.pct(100 * rs[j], 3)]) },
      { title:'Simpangan baku return', text:`Rata-rata r̄ = ${fmt.pct(100 * m, 4)}. SD = √(Σ(r − r̄)² ÷ ${n}) = ${fx(SD)} (populasi, dibagi n).` },
      { title:'Setahunkan dan jadikan persen', text:`${fx(SD)} × √${A} × 100 = ${fmt.num(SD * Math.sqrt(A) * 100)}%.` },
    ], windowSpan(B, t - n, t));
  },
  /* I34 Average daily range = SMA(H − L, n) (calc/indicators.ts adr, reference sma) */
  adr: (B, p0, t, output) => {
    const a = at('adr', () => 'HL', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, i0 = t - n + 1, SUM = htmlSum(i => B.H[i] - B.L[i], a.s0, t, n) as number;
    return done(a.o, sumLast(SUM, n, `Jumlah H − L ${n} candle`, 'price'), [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}, rentang H − L setiap candle.`, table:table(B, range(i0, t), ['H', 'L', 'H − L'], i => [px(B.H[i]), px(B.L[i]), px(B.H[i] - B.L[i])]) },
      { title:'Jumlahkan', text:`SUM = ${px(SUM)}.` },
      { title:'Bagi dengan n', text:`${px(SUM)} ÷ ${n} = ${px(SUM / n)}.` },
    ], windowSpan(B, i0, t));
  },
  /* I35 Volume SMA = SUM(V, n) ÷ n (TA-Lib SMA) */
  volume_sma: (B, p0, t, output) => {
    const a = at('volume_sma', () => 'V', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, i0 = t - n + 1, SUM = taSum(i => B.V[i], a.s0, t, n);
    return done(a.o, sumLast(SUM, n, `Jumlah volume ${n} candle`, 'count'), [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}, volume setiap candle.`, table:table(B, range(i0, t), ['Volume'], i => [vol(B.V[i])]) },
      { title:'Jumlahkan', text:`SUM = ${vol(SUM)}.` },
      { title:'Bagi dengan n', text:`${vol(SUM)} ÷ ${n} = ${fmt.num(SUM / n)}.` },
    ], windowSpan(B, i0, t));
  },
  /* I36 Volume EMA: TA-Lib EMA of V seeded with the mean of the first n volumes */
  volume_ema: (B, p0, t, output) => {
    const a = at('volume_ema', () => 'V', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, S = a.out.volume_ema, prev = prevOf(S, t, a.s0), V = B.V[t];
    if (prev === null) {
      const idx = range(t - n + 1, t), SUM = sumOf(idx.map(i => B.V[i]));
      return done(a.o, sumLast(SUM, n, `Jumlah ${n} volume pertama`, 'count'), [
        { title:'Nilai awal', text:`EMA dimulai di candle ini dengan rata-rata ${n} volume pertama sejak ${dateOf(B, a.s0)}.`, table:table(B, idx, ['Volume'], i => [vol(B.V[i])]) },
        { title:'Bagi dengan n', text:`${vol(SUM)} ÷ ${n} = ${fmt.num(SUM / n)}.` }]);
    }
    return done(a.o, kEmaLast('EMA', 'V', prev, V, n, [`EMA volume candle sebelumnya (${dateOf(B, t - 1)})`, 'Volume candle ini'], 'count'), [
      { title:'Volume candle ini', text:`V = ${vol(V)}.` },
      { title:'EMA sebelumnya', text:`EMA₋₁ = ${fmt.num(prev)}. ${chain(B, a.s0)}` },
      { title:'Perbarui', text:`EMA₋₁ + α × (V − EMA₋₁) = ${fmt.num(prev)} + ${fx(2 / (n + 1))} × (${vol(V)} − ${fmt.num(prev)}) = ${fmt.num(S[t] as number)} (α = 2 ÷ (${n} + 1)).` }]);
  },
  /* I37 Relative volume = V ÷ SMA(V, n), the window including this candle */
  rvol: (B, p0, t, output) => {
    const a = at('rvol', () => 'V', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, i0 = t - n + 1, SUM = htmlSum(i => B.V[i], a.s0, t, n) as number, VMA = SUM / n, V = B.V[t];
    const last: Last = { expr:'V ÷ VMA', combine:v => v.VMA ? v.V / v.VMA : null,
      terms:[{ key:'V', label:'Volume candle ini', value:V, unit:'count' }, { key:'VMA', label:`Rata-rata volume ${n} candle`, value:VMA, unit:'count' }] };
    return done(a.o, last, [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}, termasuk candle ini.`, table:table(B, range(i0, t), ['Volume'], i => [vol(B.V[i])]) },
      { title:'Rata-rata volume', text:`VMA = ${vol(SUM)} ÷ ${n} = ${fmt.num(VMA)}.` },
      { title:'Bandingkan', text:`${vol(V)} ÷ ${fmt.num(VMA)} = ${fx(V / VMA)}× rata-ratanya.` },
    ], windowSpan(B, i0, t));
  },
  /* I38 PVO = 100 × (EMA fast − EMA slow) ÷ EMA slow of volume; signal = TA-Lib EMA of PVO; histogram = PVO − signal */
  pvo: (B, p0, t, output) => {
    const a = at('pvo', () => 'V', B, p0, t, output); if (!a) return null;
    const { p, out, s0 } = a, f: number = p.fast_length, sl: number = p.slow_length, m: number = p.signal_length, V = B.V[t];
    const EFs = F.volume_ema(B, { length:f }).volume_ema, ESs = F.volume_ema(B, { length:sl }).volume_ema, EF = EFs[t] as number, ES = ESs[t] as number;
    const PVO = out.pvo[t] as number, pvoStep: Step = { title:'Dua EMA volume', text:`${kEmaText(B, EFs, t, s0, f, `EMA${f}`, 'V', V, fmt.num)} ${kEmaText(B, ESs, t, s0, sl, `EMA${sl}`, 'V', V, fmt.num)} ${chain(B, s0)}` };
    const pvoText = `(${fmt.num(EF)} − ${fmt.num(ES)}) ÷ ${fmt.num(ES)} × 100 = ${fmt.pct(PVO)}.`;
    if (a.o === 'pvo') {
      const last: Last = { expr:'(EF − ES) ÷ ES × 100', combine:v => Math.abs(v.ES) < 1e-14 ? 0 : ((v.EF - v.ES) / v.ES) * 100,
        terms:[{ key:'EF', label:`EMA volume ${f} (cepat)`, value:EF, unit:'count' }, { key:'ES', label:`EMA volume ${sl} (lambat)`, value:ES, unit:'count' }] };
      return done('pvo', last, [{ title:'Volume candle ini', text:`V = ${vol(V)}.` }, pvoStep, { title:'Selisih dalam persen EMA lambat', text:pvoText }]);
    }
    const SIG = out.signal[t] as number, prev = prevOf(out.signal, t, s0);
    const sigStep: Step = prev === null
      ? { title:'Garis sinyal', text:`Sinyal dimulai di candle ini: rata-rata ${m} PVO pertama = ${fmt.pct(SIG, 4)}.`, table:table(B, range(t - m + 1, t), ['PVO'], i => [fmt.pct(out.pvo[i] as number, 4)]) }
      : { title:'Garis sinyal', text:`Sinyal = SIG₋₁ + α × (PVO − SIG₋₁) = ${fmt.pct(prev, 4)} + ${fx(2 / (m + 1))} × (${fmt.pct(PVO, 4)} − ${fmt.pct(prev, 4)}) = ${fmt.pct(SIG, 4)} (EMA ${m}). ${chain(B, s0)}` };
    const steps = [pvoStep, { title:'PVO candle ini', text:pvoText }, sigStep];
    if (a.o === 'signal') {
      const last = prev === null ? sumLast(sumOf(range(t - m + 1, t).map(i => out.pvo[i] as number)), m, `Jumlah ${m} PVO pertama`, 'pct')
        : kEmaLast('SIG', 'PVO', prev, PVO, m, [`Sinyal candle sebelumnya (${dateOf(B, t - 1)})`, 'PVO candle ini'], 'pct');
      return done('signal', last, steps);
    }
    const last: Last = { expr:'PVO − SIG', combine:v => v.PVO - v.SIG, terms:[{ key:'PVO', label:'PVO candle ini', value:PVO, unit:'pct' }, { key:'SIG', label:'Garis sinyal', value:SIG, unit:'pct' }] };
    return done(a.o, last, [...steps, { title:'Histogram', text:`${fmt.pct(PVO, 4)} − ${fmt.pct(SIG, 4)} = ${fmt.pct(PVO - SIG, 4)}.` }]);
  },
  /* I39 Volume ROC = (V ÷ V n candle lalu − 1) × 100 (null when that volume is 0) */
  volume_roc: (B, p0, t, output) => {
    const a = at('volume_roc', () => 'V', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, V = B.V[t], Vn = B.V[t - n];
    const last: Last = { expr:'(V ÷ V₋ₙ − 1) × 100', combine:v => v['V₋ₙ'] !== 0 ? ((v.V / v['V₋ₙ']) - 1.0) * 100.0 : null,
      terms:[{ key:'V', label:'Volume candle ini', value:V, unit:'count' }, { key:'V₋ₙ', label:`Volume ${n} candle sebelumnya (${dateOf(B, t - n)})`, value:Vn, unit:'count' }] };
    return done(a.o, last, [
      { title:'Dua volume yang dibandingkan', text:`Candle ini dan ${n} candle sebelumnya.`, table:{ head:['Tanggal', 'Volume'], rows:[[dateOf(B, t - n), vol(Vn)], [dateOf(B, t), vol(V)]] } },
      { title:'Perubahan dalam persen', text:`(${vol(V)} ÷ ${vol(Vn)} − 1) × 100 = ${fmt.pct(((V / Vn) - 1) * 100)}.` },
    ], windowSpan(B, t - n, t));
  },
  /* I40 OBV: starts at the first candle's volume; adds V when close rises, subtracts it when close falls (TA-Lib OBV) */
  obv: (B, p0, t, output) => {
    const a = at('obv', () => 'CV', B, p0, t, output); if (!a) return null;
    const V = B.V[t];
    if (t === a.s0) return done(a.o, { expr:'V', terms:[{ key:'V', label:'Volume candle pertama', value:V, unit:'count' }], combine:v => v.V },
      [{ title:'Nilai awal', text:`OBV dimulai di candle pertama data (${dateOf(B, t)}) dengan volume candle itu: ${vol(V)}.` }]);
    const prev = a.out.obv[t - 1] as number, C = B.C[t], Cp = B.C[t - 1], up = C > Cp, down = C < Cp;
    const P: Term = { key:'OBV₋₁', label:`OBV candle sebelumnya (${dateOf(B, t - 1)})`, value:prev, unit:'count' }, VT: Term = { key:'V', label:'Volume candle ini', value:V, unit:'count' };
    const last: Last = up ? { expr:'OBV₋₁ + V', terms:[P, VT], combine:v => v['OBV₋₁'] + v.V } : down ? { expr:'OBV₋₁ − V', terms:[P, VT], combine:v => v['OBV₋₁'] - v.V }
      : { expr:'OBV₋₁', terms:[P], combine:v => v['OBV₋₁'] };
    return done(a.o, last, [
      { title:'Arah close', text:`Close ${px(C)} dibanding close sebelumnya ${px(Cp)}: ${up ? 'naik, volume ditambahkan' : down ? 'turun, volume dikurangkan' : 'sama, OBV tidak berubah'}. Volume candle ini ${vol(V)}.` },
      { title:'OBV sebelumnya', text:`OBV₋₁ = ${vol(prev)}. OBV dimulai di ${dateOf(B, a.s0)} dengan volume candle itu. ${chain(B, a.s0)}` },
      { title:'Perbarui', text:up ? `${vol(prev)} + ${vol(V)} = ${vol(prev + V)}.` : down ? `${vol(prev)} − ${vol(V)} = ${vol(prev - V)}.` : `OBV tetap ${vol(prev)}.` },
    ]);
  },
  /* I41 PVT: starts at 0; adds V × (C − C₋₁) ÷ C₋₁ each candle */
  pvt: (B, p0, t, output) => {
    const a = at('pvt', () => 'CV', B, p0, t, output); if (!a) return null;
    if (t === a.s0) return done(a.o, { expr:'PVT₀', terms:[{ key:'PVT₀', label:'Nilai awal', value:0, unit:'num' }], combine:v => v['PVT₀'] },
      [{ title:'Nilai awal', text:`PVT dimulai dari 0 di candle pertama data (${dateOf(B, t)}).` }]);
    const prev = a.out.pvt[t - 1] as number, V = B.V[t], C = B.C[t], Cp = B.C[t - 1], d = Cp ? V * (C - Cp) / Cp : 0;
    const last: Last = { expr:'PVT₋₁ + V × (C − C₋₁) ÷ C₋₁', combine:v => v['C₋₁'] ? v['PVT₋₁'] + v.V * (v.C - v['C₋₁']) / v['C₋₁'] : v['PVT₋₁'] + 0,
      terms:[{ key:'PVT₋₁', label:`PVT candle sebelumnya (${dateOf(B, t - 1)})`, value:prev, unit:'num' }, { key:'V', label:'Volume candle ini', value:V, unit:'count' },
             { key:'C', label:'Close candle ini', value:C, unit:'price' }, { key:'C₋₁', label:'Close candle sebelumnya', value:Cp, unit:'price' }] };
    return done(a.o, last, [
      { title:'Kontribusi candle ini', text:`V × (C − C₋₁) ÷ C₋₁ = ${vol(V)} × (${px(C)} − ${px(Cp)}) ÷ ${px(Cp)} = ${fmt.num(d)} (volume dikali return close ${fmt.pct(Cp ? 100 * (C - Cp) / Cp : 0)}).` },
      { title:'PVT sebelumnya', text:`PVT₋₁ = ${fmt.num(prev)}. PVT dimulai dari 0 di ${dateOf(B, a.s0)}. ${chain(B, a.s0)}` },
      { title:'Perbarui', text:`${fmt.num(prev)} + ${fmt.num(d)} = ${fmt.num(prev + d)}.` },
    ]);
  },
  /* I42 VWMA = SUM(src × V, n) ÷ SUM(V, n) (calc/indicators.ts vwmaOf: two reference sma() sums) */
  vwma: (B, p0, t, output) => {
    const a = at('vwma', p => 'V' + srcNeed(p), B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, s = a.s, i0 = t - n + 1, X = (i: number) => sourceAt(B, s, i);
    const SPV = htmlSum(i => isN(X(i)) && isN(B.V[i]) ? X(i) * B.V[i] : null, a.s0, t, n) as number, SV = htmlSum(i => B.V[i], a.s0, t, n) as number;
    const last: Last = { expr:'ΣPV ÷ ΣV', combine:v => v['ΣV'] ? (v['ΣPV'] / n) / (v['ΣV'] / n) : null,
      terms:[{ key:'ΣPV', label:`Jumlah ${lbl(s)} × volume ${n} candle`, value:SPV, unit:'num' }, { key:'ΣV', label:`Jumlah volume ${n} candle`, value:SV, unit:'count' }] };
    return done(a.o, last, [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}: harga ${lbl(s)} (P) dan volume (V) setiap candle.`,
        table:table(B, range(i0, t), [lbl(s), 'Volume', 'P × V'], i => [px(X(i)), vol(B.V[i]), fmt.num(X(i) * B.V[i], 0)]) },
      { title:'Jumlahkan', text:`ΣPV = ${fmt.num(SPV, 0)}; ΣV = ${vol(SV)}.` },
      { title:'Bagi', text:`${fmt.num(SPV, 0)} ÷ ${vol(SV)} = ${px(SPV / SV)}. Candle dengan volume besar menarik rata-rata lebih kuat.` },
    ], windowSpan(B, i0, t));
  },
  /* I43 Anchored VWAP: SUM(src × V) ÷ SUM(V) from the start of the anchor period; bands ± k × volume-weighted SD or ± k% */
  vwap: (B, p0, t, output) => {
    const a = at('vwap', p => 'V' + srcNeed(p), B, p0, t, output); if (!a) return null;
    const { p, out, s0, s } = a, X = (i: number) => sourceAt(B, s, i) as number;
    const ps = Math.max(s0, ...((out as any)._breaks as number[] || []).filter(b => b <= t));
    let sv = 0, spv = 0, sp2v = 0;
    for (let i = ps; i <= t; i++) { const x = X(i); sv += B.V[i]; spv += x * B.V[i]; sp2v += x * x * B.V[i] }
    const VW = spv / sv, SD = Math.sqrt(Math.max(0, sp2v / sv - VW * VW)), k: number = p.band_1_multiplier, anchor = String(p.anchor);
    const idx = range(ps, t), one = ps === t;
    const steps: Step[] = [
      { title:`Periode ${ANCHOR[anchor] || anchor}`, text:one ? `Anchor ${anchor}: periode ini hanya candle ${dateOf(B, t)} (pada grafik harian satu sesi = satu candle), jadi VWAP sama dengan harga ${lbl(s)} candle ini.`
        : `Anchor ${anchor}: jumlah dimulai ulang di awal setiap ${ANCHOR[anchor] || 'periode'}. Periode ini berjalan ${dateOf(B, ps)} sampai ${dateOf(B, t)} (${idx.length} candle).`,
        table:table(B, idx, [lbl(s), 'Volume', 'P × V'], i => [px(X(i)), vol(B.V[i]), fmt.num(X(i) * B.V[i], 0)]) },
      { title:'VWAP', text:`ΣPV ÷ ΣV = ${fmt.num(spv, 0)} ÷ ${vol(sv)} = ${px(VW)}.` },
    ];
    const span = windowSpan(B, ps, t);
    if (a.o === 'vwap') return done('vwap', { expr:'ΣPV ÷ ΣV', combine:v => v['ΣV'] ? v['ΣPV'] / v['ΣV'] : null,
      terms:[{ key:'ΣPV', label:`Jumlah ${lbl(s)} × volume sejak awal periode`, value:spv, unit:'num' }, { key:'ΣV', label:'Jumlah volume sejak awal periode', value:sv, unit:'count' }] }, steps, span);
    const up = a.o === 'upper1', VT: Term = { key:'VWAP', label:'VWAP candle ini', value:VW, unit:'price' };
    if (p.bands_mode === 'Percentage') {
      const last: Last = { expr:up ? 'VWAP × (1 + k ÷ 100)' : 'VWAP × (1 − k ÷ 100)', combine:up ? v => v.VWAP * (1 + v.k / 100) : v => v.VWAP * (1 - v.k / 100),
        terms:[VT, { key:'k', label:'Lebar pita (persen)', value:k, unit:'num' }] };
      return done(a.o, last, [...steps, { title:up ? 'Pita atas' : 'Pita bawah', text:`${px(VW)} × (1 ${up ? '+' : '−'} ${fmt.num(k)} ÷ 100) = ${px(up ? VW * (1 + k / 100) : VW * (1 - k / 100))}.` }], span);
    }
    const last: Last = { expr:up ? 'VWAP + k × SD' : 'VWAP − k × SD', combine:up ? v => v.VWAP + v.k * v.SD : v => v.VWAP - v.k * v.SD,
      terms:[VT, { key:'k', label:'Pengali simpangan baku (k)', value:k, unit:'num' }, { key:'SD', label:'Simpangan baku berbobot volume', value:SD, unit:'price' }] };
    return done(a.o, last, [...steps,
      { title:'Simpangan baku berbobot volume', text:`SD = √(max(0, Σ(P² × V) ÷ ΣV − VWAP²)) = ${px(SD)}${one ? ' (satu candle: praktis 0)' : ''}.` },
      { title:up ? 'Pita atas' : 'Pita bawah', text:`${px(VW)} ${up ? '+' : '−'} ${fmt.num(k)} × ${px(SD)} = ${px(up ? VW + k * SD : VW - k * SD)}.` }], span);
  },
  /* I44 A/D line: ADL₋₁ + MFM × V, MFM = ((C − L) − (H − C)) ÷ (H − L), 0 when H = L (TA-Lib AD, starts at 0) */
  adl: (B, p0, t, output) => {
    const a = at('adl', () => 'HLCV', B, p0, t, output); if (!a) return null;
    const first = t === a.s0, prev = first ? 0 : a.out.adl[t - 1] as number, H = B.H[t], L = B.L[t], C = B.C[t], V = B.V[t];
    const MFM = H - L > 0 ? ((C - L) - (H - C)) / (H - L) : 0;
    const last: Last = { expr:'ADL₋₁ + MFM × V', combine:v => v['ADL₋₁'] + v.MFM * v.V,
      terms:[{ key:'ADL₋₁', label:first ? 'Nilai awal' : `A/D candle sebelumnya (${dateOf(B, t - 1)})`, value:prev, unit:'num' },
             { key:'MFM', label:'Pengali money flow candle ini', value:MFM, unit:'num' }, { key:'V', label:'Volume candle ini', value:V, unit:'count' }] };
    return done(a.o, last, [
      { title:'Posisi close dalam candle', text:`MFM = ((C − L) − (H − C)) ÷ (H − L) = ((${px(C)} − ${px(L)}) − (${px(H)} − ${px(C)})) ÷ (${px(H)} − ${px(L)}) = ${fx(MFM)}. +1 = close di high, −1 = close di low${H - L > 0 ? '' : '; H = L, jadi 0'}.` },
      { title:'Money flow volume', text:`MFM × V = ${fx(MFM)} × ${vol(V)} = ${fmt.num(MFM * V)}.` },
      { title:first ? 'Nilai awal' : 'A/D sebelumnya', text:first ? `A/D dimulai dari 0 di candle pertama data (${dateOf(B, t)}).` : `ADL₋₁ = ${fmt.num(prev)}. A/D dimulai dari 0 di ${dateOf(B, a.s0)}. ${chain(B, a.s0)}` },
      { title:'Perbarui', text:`${fmt.num(prev)} + ${fmt.num(MFM * V)} = ${fmt.num(prev + MFM * V)}.` },
    ]);
  },
  /* I45 Chaikin Money Flow = SUM(MFM × V, n) ÷ SUM(V, n) (calc/indicators.ts cmf: two reference sma() sums) */
  cmf: (B, p0, t, output) => {
    const a = at('cmf', () => 'HLCV', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, i0 = t - n + 1, SMV = htmlSum(i => mfmOf(B, i) * B.V[i], a.s0, t, n) as number, SV = htmlSum(i => B.V[i], a.s0, t, n) as number;
    const last: Last = { expr:'ΣMFV ÷ ΣV', combine:v => v['ΣV'] ? ((v['ΣMFV'] / n) * n) / ((v['ΣV'] / n) * n) : null,
      terms:[{ key:'ΣMFV', label:`Jumlah MFM × volume ${n} candle`, value:SMV, unit:'num' }, { key:'ΣV', label:`Jumlah volume ${n} candle`, value:SV, unit:'count' }] };
    return done(a.o, last, [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}. MFM = ((C − L) − (H − C)) ÷ (H − L): +1 close di high, −1 close di low, 0 bila H = L.`,
        table:table(B, range(i0, t), ['MFM', 'Volume', 'MFM × V'], i => [fx(mfmOf(B, i)), vol(B.V[i]), fmt.num(mfmOf(B, i) * B.V[i], 0)]) },
      { title:'Jumlahkan', text:`ΣMFV = ${fmt.num(SMV, 0)}; ΣV = ${vol(SV)}.` },
      { title:'Bagi', text:`${fmt.num(SMV, 0)} ÷ ${vol(SV)} = ${fx(SMV / SV)}.` },
    ], windowSpan(B, i0, t));
  },
  /* I46 Chaikin oscillator = EMA fast(A/D) − EMA slow(A/D), both seeded with the first A/D value (TA-Lib ADOSC) */
  chaikin_osc: (B, p0, t, output) => {
    const a = at('chaikin_osc', () => 'HLCV', B, p0, t, output); if (!a) return null;
    const f: number = a.p.fast_length, sl: number = a.p.slow_length, s0 = a.s0, AD = F.adl(B, {}).adl;
    const fk = 2 / (f + 1), sk = 2 / (sl + 1), f1 = 1.0 - fk, s1 = 1.0 - sk;
    let fe = AD[s0] as number, se = fe, fp = fe, sp = fe;
    for (let i = s0 + 1; i <= t; i++) { fp = fe; sp = se; const ad = AD[i] as number; fe = (fk * ad) + (f1 * fe); se = (sk * ad) + (s1 * se) }
    const ad = AD[t] as number, last: Last = { expr:'EF − ES', combine:v => v.EF - v.ES,
      terms:[{ key:'EF', label:`EMA ${f} garis A/D (cepat)`, value:fe, unit:'num' }, { key:'ES', label:`EMA ${sl} garis A/D (lambat)`, value:se, unit:'num' }] };
    return done(a.o, last, [
      { title:'Garis A/D candle ini', text:`A/D = ${fmt.num(ad)} (A/D₋₁ + MFM × V, seperti indikator A/D Line).` },
      t === s0 ? { title:'Nilai awal', text:`Kedua EMA dimulai dari A/D candle pertama data (${dateOf(B, s0)}), seperti TA-Lib ADOSC.` }
        : { title:'Perbarui kedua EMA', text:`EF = ${fx(fk)} × ${fmt.num(ad)} + ${fx(f1)} × ${fmt.num(fp)} = ${fmt.num(fe)} (α = 2 ÷ (${f} + 1)). ES = ${fx(sk)} × ${fmt.num(ad)} + ${fx(s1)} × ${fmt.num(sp)} = ${fmt.num(se)} (α = 2 ÷ (${sl} + 1)). Keduanya dimulai dari A/D candle pertama data (${dateOf(B, s0)}), seperti TA-Lib ADOSC; seluruh riwayat ikut terbawa.` },
      { title:'Selisih', text:`${fmt.num(fe)} − ${fmt.num(se)} = ${fmt.num(fe - se)}.` },
    ]);
  },
  /* I47 MFI = 100 × PF ÷ (PF + NF) over n candles, flows TP × V split by the sign of ΔTP (TA-Lib MFI; 0 when PF + NF < 1) */
  mfi: (B, p0, t, output) => {
    const a = at('mfi', () => 'HLCV', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, s0 = a.s0, TP = (i: number) => (B.H[i] + B.L[i] + B.C[i]) / 3.0;
    const pos: number[] = [0], neg: number[] = [0]; let prev = TP(s0), PF = 0, NF = 0;           // TA-Lib's running sums
    for (let i = s0 + 1; i <= t; i++) {
      const k = i - s0; if (k > n) { PF -= pos[k - n]; NF -= neg[k - n] }
      let tp = TP(i); const d = tp - prev; prev = tp; tp *= B.V[i]; pos[k] = 0; neg[k] = 0;
      if (d < 0) { neg[k] = tp; NF += tp } else if (d > 0) { pos[k] = tp; PF += tp }
    }
    const i0 = t - n + 1, last: Last = { expr:'100 × PF ÷ (PF + NF)', combine:v => v.PF + v.NF < 1.0 ? 0.0 : 100.0 * (v.PF / (v.PF + v.NF)),
      terms:[{ key:'PF', label:`Money flow positif ${n} candle`, value:PF, unit:'num' }, { key:'NF', label:`Money flow negatif ${n} candle`, value:NF, unit:'num' }] };
    return done(a.o, last, [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}. TP = (H + L + C) ÷ 3; money flow = TP × V, positif bila TP naik dari candle sebelumnya, negatif bila turun, diabaikan bila sama.`,
        table:table(B, range(i0, t), ['TP', 'Arah', 'TP × V'], i => [px(TP(i)), TP(i) > TP(i - 1) ? 'naik' : TP(i) < TP(i - 1) ? 'turun' : 'sama', fmt.num(TP(i) * B.V[i], 0)]) },
      { title:'Jumlahkan per arah', text:`PF = ${fmt.num(PF, 0)}; NF = ${fmt.num(NF, 0)}.` },
      { title:'Hitung nilainya', text:PF + NF < 1 ? 'PF + NF di bawah 1, jadi MFI = 0 (aturan TA-Lib).' : `100 × ${fmt.num(PF, 0)} ÷ (${fmt.num(PF, 0)} + ${fmt.num(NF, 0)}) = ${fmt.num(100 * (PF / (PF + NF)))}.` },
    ], windowSpan(B, t - n, t));
  },
  /* I48 Elder's Force Index = EMA((C − C₋₁) × V, n) (reference ema, seeded with the mean of the first n values) */
  force_index: (B, p0, t, output) => {
    const a = at('force_index', () => 'CV', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, s0 = a.s0, S = a.out.force_index, FI = (i: number) => (B.C[i] - B.C[i - 1]) * B.V[i], prev = prevOf(S, t, s0);
    const fiStep: Step = { title:'Force candle ini', text:`FI = (C − C₋₁) × V = (${px(B.C[t])} − ${px(B.C[t - 1])}) × ${vol(B.V[t])} = ${fmt.num(FI(t), 0)}.` };
    if (prev === null) {
      const idx = range(t - n + 1, t), SUM = sumOf(idx.map(FI));
      return done(a.o, sumLast(SUM, n, `Jumlah ${n} force pertama`, 'num'), [fiStep,
        { title:'Nilai awal', text:`EMA dimulai di candle ini dengan rata-rata ${n} force pertama sejak ${dateOf(B, s0 + 1)}.`, table:table(B, idx, ['ΔC', 'Volume', 'FI'], i => [px(B.C[i] - B.C[i - 1]), vol(B.V[i]), fmt.num(FI(i), 0)]) },
        { title:'Bagi dengan n', text:`${fmt.num(SUM, 0)} ÷ ${n} = ${fmt.num(SUM / n)}.` }]);
    }
    const al = 2 / (n + 1);
    return done(a.o, ewmLast('EFI', 'FI', prev, FI(t), al, `Bobot α = 2 ÷ (${n} + 1)`, [`EFI candle sebelumnya (${dateOf(B, t - 1)})`, 'Force candle ini'], 'num'), [fiStep,
      { title:'EFI sebelumnya', text:`EFI₋₁ = ${fmt.num(prev)}. ${chain(B, s0)}` },
      { title:'Haluskan (EMA)', text:`${fx(al)} × ${fmt.num(FI(t), 0)} + ${fx(1 - al)} × ${fmt.num(prev)} = ${fmt.num(S[t] as number)}.` }]);
  },
  /* I49 Ease of Movement = SMA(ΔHL2 × (H − L) ÷ V × scale, n); a zero-volume candle has no value and restarts the window */
  eom: (B, p0, t, output) => {
    const a = at('eom', () => 'HLV', B, p0, t, output); if (!a) return null;
    const n: number = a.p.length, k: number = a.p.volume_scale, s0 = a.s0, M = (i: number) => (B.H[i] + B.L[i]) / 2;
    const raw = (i: number) => i > s0 && B.V[i] ? (M(i) - M(i - 1)) * (B.H[i] - B.L[i]) / B.V[i] * k : null;
    const i0 = t - n + 1, SUM = htmlSum(raw, s0, t, n) as number;
    return done(a.o, sumLast(SUM, n, `Jumlah EMV ${n} candle`, 'num'), [
      { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, i0)} sampai ${dateOf(B, t)}. EMV = (HL2 − HL2₋₁) × (H − L) ÷ V × ${fmt.num(k, 0)}, HL2 = (H + L) ÷ 2.`,
        table:table(B, range(i0, t), ['ΔHL2', 'H − L', 'Volume', 'EMV'], i => [px(M(i) - M(i - 1)), px(B.H[i] - B.L[i]), vol(B.V[i]), fx(raw(i) as number)]) },
      { title:'Jumlahkan', text:`SUM = ${fx(SUM)}.` },
      { title:'Bagi dengan n', text:`${fx(SUM)} ÷ ${n} = ${fx(SUM / n)}.` },
    ], windowSpan(B, t - n, t));
  },
  /* I50 Negative Volume Index: changes with the close return only when volume falls */
  nvi: (B, p0, t, output) => volumeIndex('nvi', B, p0, t, output),
  /* I51 Positive Volume Index: changes with the close return only when volume rises */
  pvi: (B, p0, t, output) => volumeIndex('pvi', B, p0, t, output),
  /* I52 Klinger Volume Oscillator: EMA fast − EMA slow of the volume force; signal = EMA of KVO (reference ema) */
  kvo: (B, p0, t, output) => {
    const a = at('kvo', () => 'HLCV', B, p0, t, output); if (!a) return null;
    const { p, out, s0 } = a, f: number = p.fast_length, sl: number = p.slow_length, m: number = p.signal_length, k = t - s0;
    const K = kvoForce(B, s0, t), EFs = ema(K.vf, f), ESs = ema(K.vf, sl), EF = EFs[k] as number, ES = ESs[k] as number, VF = K.vf[k] as number;
    const vfStep: Step = { title:'Volume force candle ini', text:`Tren = ${K.tr > 0 ? '+1 (H + L + C naik)' : K.tr < 0 ? '−1 (H + L + C turun)' : '0'}${K.tr === K.trendPrev ? ', sama dengan candle sebelumnya' : ', berganti'}. dm = H − L = ${px(K.dm)}; cm = ${px(K.cm)} (${K.tr === K.trendPrev ? 'cm₋₁ + dm' : 'dm₋₁ + dm, tren berganti'}). VF = V × |2 × (dm ÷ cm − 1)| × tren × 100 = ${fmt.num(VF, 0)}.` };
    const emaStep: Step = { title:'Dua EMA volume force', text:`${ewmText(EFs, k, f, 'EF', 'VF', VF, fmt.num)} ${ewmText(ESs, k, sl, 'ES', 'VF', VF, fmt.num)} ${chain(B, s0)}` };
    if (a.o === 'kvo') return done('kvo', { expr:'EF − ES', combine:v => v.EF - v.ES,
      terms:[{ key:'EF', label:`EMA ${f} volume force (cepat)`, value:EF, unit:'num' }, { key:'ES', label:`EMA ${sl} volume force (lambat)`, value:ES, unit:'num' }] },
      [vfStep, emaStep, { title:'Selisih', text:`${fmt.num(EF)} − ${fmt.num(ES)} = ${fmt.num(EF - ES)}.` }]);
    const KVO = out.kvo[t] as number, SIG = out.signal[t] as number, prev = prevOf(out.signal, t, s0), al = 2 / (m + 1);
    if (prev === null) {
      const idx = range(t - m + 1, t), SUM = sumOf(idx.map(i => out.kvo[i] as number));
      return done(a.o, sumLast(SUM, m, `Jumlah ${m} KVO pertama`, 'num'), [vfStep, emaStep,
        { title:'Garis sinyal', text:`Sinyal dimulai di candle ini dengan rata-rata ${m} KVO pertama.`, table:table(B, idx, ['KVO'], i => [fmt.num(out.kvo[i] as number)]) },
        { title:'Bagi dengan n', text:`${fmt.num(SUM)} ÷ ${m} = ${fmt.num(SIG)}.` }]);
    }
    return done(a.o, ewmLast('SIG', 'KVO', prev, KVO, al, `Bobot α = 2 ÷ (${m} + 1)`, [`Sinyal candle sebelumnya (${dateOf(B, t - 1)})`, 'KVO candle ini'], 'num'), [vfStep, emaStep,
      { title:'KVO candle ini', text:`KVO = EF − ES = ${fmt.num(KVO)}.` },
      { title:'Garis sinyal (EMA)', text:`${fx(al)} × ${fmt.num(KVO)} + ${fx(1 - al)} × ${fmt.num(prev)} = ${fmt.num(SIG)} (sinyal₋₁ dari ${dateOf(B, t - 1)}).` }]);
  },
  /* I53 Market Facilitation Index = (H − L) ÷ V × scale (null when V = 0) */
  market_fi: (B, p0, t, output) => {
    const a = at('market_fi', () => 'HLV', B, p0, t, output); if (!a) return null;
    const H = B.H[t], L = B.L[t], V = B.V[t], k: number = a.p.volume_scale, v = (H - L) / V * k;
    const last: Last = { expr:'(H − L) ÷ V × k', combine:x => x.V ? (x.H - x.L) / x.V * x.k : null,
      terms:[{ key:'H', label:'High candle ini', value:H, unit:'price' }, { key:'L', label:'Low candle ini', value:L, unit:'price' }, { key:'V', label:'Volume candle ini', value:V, unit:'count' }, { key:'k', label:'Skala volume', value:k, unit:'num' }] };
    return done(a.o, last, [
      { title:'Rentang dan volume candle ini', text:`H − L = ${px(H)} − ${px(L)} = ${px(H - L)}; V = ${vol(V)}.` },
      { title:'Rentang per volume', text:`${px(H - L)} ÷ ${vol(V)} × ${fmt.num(k, 0)} = ${fx(v)}: pergerakan harga untuk setiap unit volume (Bill Williams; bukan Money Flow Index).` },
    ]);
  },
};

/* I50 / I51: index starts at initial_value; on a candle whose volume falls (NVI) or rises (PVI) it moves with C ÷ C₋₁ */
function volumeIndex(key: 'nvi' | 'pvi', B: Bars, p0: Params, t: number, output?: string): Explanation | null {
  const a = at(key, () => 'CV', B, p0, t, output); if (!a) return null;
  const N = key.toUpperCase(), P0 = `${N}₀`, P = `${N}₋₁`, word = key === 'nvi' ? 'turun' : 'naik';
  if (t === a.s0) return done(a.o, { expr:P0, terms:[{ key:P0, label:'Nilai awal', value:a.p.initial_value, unit:'num' }], combine:v => v[P0] },
    [{ title:'Nilai awal', text:`${N} dimulai dari ${fmt.num(a.p.initial_value)} di candle pertama data (${dateOf(B, t)}).` }]);
  const prev = a.out[key][t - 1] as number, V = B.V[t], Vp = B.V[t - 1], C = B.C[t], Cp = B.C[t - 1];
  const moves = (key === 'nvi' ? V < Vp : V > Vp) && !!Cp, PT: Term = { key:P, label:`${N} candle sebelumnya (${dateOf(B, t - 1)})`, value:prev, unit:'num' };
  const last: Last = moves ? { expr:`${P} × C ÷ C₋₁`, combine:v => v['C₋₁'] ? v[P] * (v.C / v['C₋₁']) : v[P],
    terms:[PT, { key:'C', label:'Close candle ini', value:C, unit:'price' }, { key:'C₋₁', label:'Close candle sebelumnya', value:Cp, unit:'price' }] }
    : { expr:P, terms:[PT], combine:v => v[P] };
  return done(a.o, last, [
    { title:'Volume dibanding candle sebelumnya', text:`V = ${vol(V)}, V₋₁ = ${vol(Vp)}: volume ${V < Vp ? 'turun' : V > Vp ? 'naik' : 'sama'}. ${N} hanya bergerak bila volume ${word}${moves ? ', jadi candle ini dihitung' : ', jadi nilainya tetap'}.` },
    { title:`${N} sebelumnya`, text:`${P} = ${fmt.num(prev)}. ${N} dimulai dari ${fmt.num(a.p.initial_value)} di ${dateOf(B, a.s0)}. ${chain(B, a.s0)}` },
    { title:'Perbarui', text:moves ? `${fmt.num(prev)} × ${px(C)} ÷ ${px(Cp)} = ${fmt.num(prev * (C / Cp))} (return close ${fmt.pct(100 * (C / Cp - 1))}).` : `${N} tetap ${fmt.num(prev)}.` },
  ]);
}
