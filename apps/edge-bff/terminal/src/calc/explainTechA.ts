/* EXEC-IND-CARDS IC4: technical explainers (calc/explain.ts: the interface, the helpers and the rule that the card's
   number is the chart's number). One file per part so they can be written side by side; explainTechIndex.ts joins them. */
import type { Explanation, Step, Term, TechExplainer, Unit } from './explain';
import { againstLevels, dateOf, fmt, intOf, sourceAt, SOURCES } from './explain';
import type { Bars, Params, Series } from './indicators';
import { DEFAULTS, F, isN, ema as refEma, rma as refRma, sma as refSma, wma as refWma } from './indicators';
import IND from '../data/indRegistry.json';

/* ---- shared pieces of the I02-I26 explainers ----
   Each explainer first reads the chart's own value (F[key] on the same candles and parameters): the card's value is
   that number, and there is no explanation where the chart has none. The steps rebuild the last step of the formula
   from the candles of the run that holds t (calc/indicators.ts def: a candle with a missing input breaks the series and
   the calculation restarts after it); earlier values of a running average come from the same calculations, or from
   the same operations in the same order where the chart keeps them internal (Wilder sums, SAR, Supertrend bands). */
type V = Record<string, number>;
type Combine = (v: V) => number | null;
interface Ctx {
  key: string; P: Params; o: string; v: number;
  out: Record<string, Series>;        // the chart's outputs on S (index i = the value at t)
  i: number;                          // t inside the run (the run starts at candle t − i)
  S: Bars;                            // the run's candles up to t
  src: number[];                      // the source price of S (P.source; close when the indicator has none)
  date: (k: number) => string;        // the date of candle k of S
}
const NEED: Record<string, string> = { open:'O', high:'H', low:'L', close:'C', hl2:'HL', hlc3:'HLC', ohlc4:'OHLC' };
const needOf = (s: unknown) => NEED[String(s)] || 'C';
const srcNeed = (P: Params) => needOf(P.source);
const LENGTH_KEYS = /(^|_)(length|smoothing|smooth_k|smooth_d|periods)$/;   // calc/indicators.ts def
const truthy = (v: unknown) => v === true || v === 'true' || v === 1 || v === '1';
const isZero = (v: number) => -1e-14 < v && v < 1e-14;                     // TA-Lib TA_IS_ZERO (calc/indicators.ts)
const GUIDES: Record<string, number[]> = Object.fromEntries((IND as any[]).map(r => [r.key, (r.guides || []).filter((g: any) => Number.isFinite(g))]));

/** the chart's value of `key` at t (null when the chart has none), the parameters as the chart reads them, the run.
    The value is F[key] on the run's candles up to t: every indicator here reads only candles up to t and restarts at
    the run's first candle (calc/indicators.ts def), so it is the same double as F[key] on all candles at t. */
function ctxOf(key: string, B: Bars, p: Params, t: number, output: string | undefined, need: (P: Params) => string): Ctx | null {
  if (!(t >= 0 && t < B.C.length)) return null;
  const P: Params = { ...DEFAULTS[key], ...p };
  for (const [k, x] of Object.entries(P)) {
    if (LENGTH_KEYS.test(k)) P[k] = Math.floor(Number(x));
    else if (typeof DEFAULTS[key][k] === 'number') P[k] = Number(x);
  }
  const cols = (['O', 'H', 'L', 'C', 'V'] as const).filter(f => need(P).includes(f)), ok = (k: number) => cols.every(f => isN(B[f][k]));
  if (!ok(t)) return null;
  let s = t; while (s > 0 && ok(s - 1)) s--;
  const cut = (a: any) => (a ? a.slice(s, t + 1) : []) as number[];
  const S: Bars = { O:cut(B.O), H:cut(B.H), L:cut(B.L), C:cut(B.C), V:cut(B.V), T:B.T ? B.T.slice(s, t + 1) : undefined };
  const out = F[key](S, p), outs = Object.keys(out).filter(k => !k.startsWith('_')), o = output ?? outs[0], i = t - s;
  const v = outs.includes(o) ? out[o][i] : null;
  if (!isN(v)) return null;
  const sn = String(P.source || 'close');
  return { key, P, o, v, i, S, out, src:S.C.map((_, k) => sourceAt(S, sn, k)), date:k => dateOf(B, s + k) };
}

const short = (rows: string[][]) => rows.length > 12 ? [...rows.slice(0, 5), rows[0].map((_, j) => (j ? '' : '…')), ...rows.slice(-5)] : rows;
const SUBS = '₀₁₂₃₄₅₆₇₈₉';
/** k candles back as a subscript: D, D₋₁, D₋₂ … */
const ago = (k: number) => (k ? '₋' + String(k).replace(/\d/g, d => SUBS[+d]) : '');
const srcName = (P: Params) => { const s = String(P.source || 'close'); return SOURCES[s] || s };
const srcLabel = (P: Params) => `Harga ${srcName(P)}`;
const n2 = (v: number) => fmt.num(v);
const n4 = (v: number) => fmt.num(v, 4);
const pc2 = (v: number) => fmt.pct(v);
/** a number as an operand: a negative one in parentheses (5 − (−3), not 5 − −3) */
const pr = (v: number, f: (v: number) => string = n2) => (v < 0 ? `(${f(v)})` : f(v));
const term = (key: string, label: string, value: number, unit: Unit = 'price'): Term => ({ key, label, value, unit });
const safe = (f: Combine): Combine => v => { const x = f(v); return isN(x) ? x : null };

/** where the value sits against the indicator's reference lines (indRegistry guides) */
function readStep(c: Ctx, fv: (v: number) => string): Step[] {
  const lv = GUIDES[c.key] || [];
  if (!lv.length || c.o === 'direction') return [];
  const where = lv.length > 1 ? againstLevels(c.v, lv) : c.v === lv[0] ? `tepat di garis ${fmt.num(lv[0], 0)}` : `${c.v > lv[0] ? 'di atas' : 'di bawah'} garis ${fmt.num(lv[0], 0)}`;
  return [{ title:'Baca hasilnya', text:`${fv(c.v)} berada ${where}.` }];
}
/** the explanation: the chart's value, the last step (expr, terms, combine) and the steps; span = a fixed window */
function done(c: Ctx, expr: string, terms: Term[], combine: Combine, steps: Step[], span?: [number, number], fv: (v: number) => string = n2): Explanation {
  return { output:c.o, value:c.v, expr, terms, combine:safe(combine), steps:[...steps, ...readStep(c, fv)],
    ...(span ? { span:{ from:c.date(span[0]), to:c.date(span[1]), candles:span[1] - span[0] + 1 } } : {}) };
}

/** the mean of values (oldest first): one term per value up to five values, else SUM and n */
function meanOf(vals: number[], key: string, label: (j: number) => string, unit: Unit) {
  const m = vals.length;
  if (m > 5) {
    const SUM = vals.reduce((s, x) => s + x, 0);
    return { expr:'SUM ÷ n', terms:[term('SUM', `Jumlah ${m} nilai`, SUM, unit), term('n', 'Panjang (n)', m, 'count')], combine:((v: V) => (v.n ? v.SUM / v.n : null)) as Combine };
  }
  const terms = vals.map((x, j) => term(key + ago(m - 1 - j), label(j), x, unit));
  return { expr:m === 1 ? terms[0].key : `(${terms.map(x => x.key).join(' + ')}) ÷ ${m}`, terms, combine:((v: V) => terms.reduce((s, x) => s + v[x.key], 0) / m) as Combine };
}

/** TA-Lib EMA of any series (F.ema reads the series as the close; a gap restarts it, as calc/indicators.ts runs) */
const taEma = (x: Series, n: number) => F.ema({ O:x, H:x, L:x, C:x, V:x }, { length:n, source:'close' }).ema;

/** one update of an EMA (y of x, length n) at candle i of the run, as a sentence; xWord names x */
function emaLine(c: Ctx, name: string, y: Series, x: Series, n: number, fv = n2, xWord = 'harga') {
  const i = c.i;
  if (!isN(y[i - 1])) return `${name} = ${fv(y[i])}: nilai pertamanya, rata-rata sederhana ${n} nilai pertama.`;
  return `${name} = ${name} sebelumnya + α × (${xWord} − ${name} sebelumnya) = ${fv(y[i - 1])} + ${n4(2 / (n + 1))} × (${fv(x[i])} − ${pr(y[i - 1], fv)}) = ${fv(y[i])}, dengan α = 2 ÷ (${n} + 1). Seri ini diperbarui setiap candle sejak seed, rata-rata sederhana ${n} nilai pertama.`;
}

/* an exponential average at candle i: the seed (mean of the first n inputs) or the update from the previous value */
interface Avg {
  c: Ctx; x: Series; y: Series; n: number;
  form: 'talib' | 'ref';   // talib (kEma): Y₋₁ + α × (x − Y₋₁), a gap restarts it; ref (ema helper): α × x + (1 − α) × Y₋₁, a gap after the seed is skipped
  name: string; key: string; xName: string; xKey: string; u: Unit; fv: (v: number) => string; before?: Step[];
}
function avgExplain(a: Avg): Explanation {
  const { c, x, y, n, fv } = a, i = c.i, talib = a.form === 'talib';
  let j = -1;
  if (talib) { if (i > 0 && isN(y[i - 1])) j = i - 1 } else for (let k = i - 1; k >= 0; k--) if (isN(y[k])) { j = k; break }
  if (j < 0) {
    const xs = x.slice(i - n + 1, i + 1) as number[], SUM = xs.reduce((s, v) => s + v, 0);
    return done(c, 'SUM ÷ n', [term('SUM', `Jumlah ${a.xName} ${n} candle`, SUM, a.u), term('n', 'Panjang (n)', n, 'count')], v => (v.n ? v.SUM / v.n : null), [
      ...(a.before || []),
      { title:`${a.name} pertama (seed)`, text:`Seri ${a.name} dimulai di candle ini: nilai pertamanya adalah rata-rata sederhana ${n} nilai ${a.xName} pertama, ${c.date(i - n + 1)} sampai ${c.date(i)}. Sesudah ini nilainya diperbarui setiap candle.`,
        table:{ head:['Tanggal', a.xName], rows:short(xs.map((v, k) => [c.date(i - n + 1 + k), fv(v)])) } },
      { title:'Jumlahkan dan bagi dengan n', text:`SUM = ${fv(SUM)}; ${fv(SUM)} ÷ ${n} = ${fv(c.v)}.` },
    ], undefined, fv);
  }
  let seed = j;
  if (talib) while (seed > 0 && isN(y[seed - 1])) seed--; else seed = y.findIndex(isN);
  const prev = y[j] as number, X = x[i] as number, al = 2 / (n + 1), P = a.key + '₋₁';
  const rows: string[][] = [];
  for (let k = Math.max(seed, i - 4); k <= i; k++) rows.push([c.date(k), isN(x[k]) ? fv(x[k]) : '–', isN(y[k]) ? fv(y[k]) : '–']);
  const combine: Combine = talib ? v => (v[a.xKey] - v[P]) * v['α'] + v[P] : v => v['α'] * v[a.xKey] + (1 - v['α']) * v[P];
  return done(c, talib ? `${P} + α × (${a.xKey} − ${P})` : `α × ${a.xKey} + (1 − α) × ${P}`,
    [term(P, `${a.name} candle sebelumnya (${c.date(j)})`, prev, a.u), term('α', `Bobot α = 2 ÷ (${n} + 1)`, al, 'num'), term(a.xKey, `${a.xName} ${c.date(i)}`, X, a.u)], combine, [
      ...(a.before?.length ? a.before : [{ title:`${a.xName} candle ini`, text:`${c.date(i)}: ${a.xKey} = ${fv(X)}.` }]),
      { title:`${a.name} candle sebelumnya`, text:`${P} (${c.date(j)}) = ${fv(prev)}. Seri ini dimulai di ${c.date(seed)} dari seed (rata-rata sederhana ${n} nilai pertama), lalu diperbarui setiap candle sepanjang riwayat; karena itu nilai-nilai lama tetap ikut memengaruhi.`,
        table:{ head:['Tanggal', a.xName, a.name], rows } },
      { title:'Bobot α', text:`α = 2 ÷ (${n} + 1) = ${n4(al)}: candle terbaru mendapat bobot ${fmt.num(100 * al, 1)}%, ${P} sisanya.` },
      { title:`Hitung ${a.name}`, text:(talib ? `${fv(prev)} + ${n4(al)} × (${fv(X)} − ${pr(prev, fv)})` : `${n4(al)} × ${pr(X, fv)} + (1 − ${n4(al)}) × ${pr(prev, fv)}`) + ` = ${fv(c.v)}.` },
    ], undefined, fv);
}

/** Wilder DMI at candle i of the run, as calc/indicators.ts kDmi (the same operations in the same order) */
function dmiAt(H: number[], L: number[], C: number[], d: number, a: number, i: number) {
  let pH = H[0], pL = L[0], pC = C[0], pDM = 0, mDM = 0, tr = 0, sumDX = 0, nDX = 0, prevADX = 0, r: any = null;
  const seedDX: (number | null)[] = [];
  for (let k = 1; k <= i; k++) {
    const dP = H[k] - pH, dM = pL - L[k]; pH = H[k]; pL = L[k];
    const t = Math.max(pH - pL, Math.abs(pC - pH), Math.abs(pC - pL)), cPrev = pC; pC = C[k];
    const minusWins = dM > 0 && dP < dM, plusWins = !minusWins && dP > 0 && dP > dM;
    const o: any = { dP, dM, p1:plusWins ? dP : 0, m1:minusWins ? dM : 0, t, cPrev, pDM0:pDM, mDM0:mDM, tr0:tr, adx0:prevADX, plus:null, minus:null, dx:null, how:'' };
    if (k < d) { if (minusWins) mDM += dM; else if (plusWins) pDM += dP; tr += t }
    else {
      pDM -= pDM / d; mDM -= mDM / d;
      if (minusWins) mDM += dM; else if (plusWins) pDM += dP;
      tr = tr - (tr / d) + t;
      let dx: number | null = null;
      if (!isZero(tr)) {
        const mi = 100.0 * (mDM / tr), pi = 100.0 * (pDM / tr), s = mi + pi;
        o.plus = pi; o.minus = mi;
        if (!isZero(s)) dx = 100.0 * (Math.abs(mi - pi) / s);
      } else { o.plus = 0; o.minus = 0 }
      o.dx = dx;
      if (nDX < a) { if (dx !== null) sumDX += dx; seedDX.push(dx); if (++nDX === a) { prevADX = sumDX / a; o.how = 'seed' } }
      else { o.how = dx !== null ? 'update' : 'keep'; if (dx !== null) prevADX = ((prevADX * (a - 1)) + dx) / a }
    }
    o.pDM = pDM; o.mDM = mDM; o.tr = tr; o.adx = prevADX; o.sumDX = sumDX; o.seedDX = seedDX.slice();
    if (k === i) r = o;
  }
  return r;
}

/** Supertrend at candle i of the run, as calc/indicators.ts F.supertrend (ATR as I30) */
function stAt(S: Bars, P: Params, i: number) {
  const H = S.H as number[], L = S.L as number[], C = S.C as number[], atr = F.atr(S, { length:P.atr_length, smoothing_type:'RMA' }).atr;
  let fu: number | null = null, fl: number | null = null, prevSt: number | null = null, d = 1, r: any = null;
  for (let k = 0; k <= i; k++) {
    const a = atr[k]; if (!isN(a)) continue;
    const mid = (H[k] + L[k]) / 2, bu = mid + P.factor * a, bl = mid - P.factor * a;
    const nfl = fl === null || bl > fl || C[k - 1] < fl ? bl : fl;
    const nfu = fu === null || bu < fu || C[k - 1] > fu ? bu : fu;
    let how: string;
    if (prevSt === null) { d = 1; how = 'first' }
    else if (prevSt === fu) { d = C[k] > nfu ? 1 : -1; how = 'down' }
    else { d = C[k] < nfl ? -1 : 1; how = 'up' }
    if (k === i) r = { a, atrPrev:atr[k - 1], tr:k ? Math.max(H[k] - L[k], Math.abs(C[k - 1] - H[k]), Math.abs(C[k - 1] - L[k])) : null, mid, bu, bl, fl, fu, nfl, nfu, how, d, cPrev:C[k - 1], c:C[k] };
    fl = nfl; fu = nfu; prevSt = d === 1 ? fl : fu;
  }
  return r;
}

/** Parabolic SAR bar by bar (1..i of the run), as calc/indicators.ts F.psar (TA-Lib SAREXT) */
function psarTrace(H: number[], L: number[], P: Params, i: number) {
  const max = P.maximum, inc = Math.min(P.increment, max), start = Math.min(P.start, max);
  const dP = H[1] - H[0], dM = L[0] - L[1];
  let long = !(dM > 0 && dP < dM), af = start;
  let ep = long ? H[1] : L[1], s = long ? L[0] : H[0], nL = L[1], nH = H[1];
  const R: any[] = [];
  for (let k = 1; k <= i; k++) {
    const pL = nL, pH = nH; nL = L[k]; nH = H[k];
    const r: any = { k, long0:long, tested:s, ep0:ep, af0:af, pL, pH, nL, nH, pIdx:k === 1 ? 1 : k - 1, rev:false };
    if (long) {
      if (nL <= s) {
        long = false; s = ep; if (s < pH) s = pH; if (s < nH) s = nH;
        r.rev = true; r.sar = s; r.dir = -1; af = start; ep = nL;
        s = r.raw = s + af * (ep - s); if (s < pH) s = pH; if (s < nH) s = nH;
      } else {
        r.sar = s; r.dir = 1;
        if (nH > ep) { ep = nH; af += inc; if (af > max) af = max; r.newEp = true }
        s = r.raw = s + af * (ep - s); if (s > pL) s = pL; if (s > nL) s = nL;
      }
    } else if (nH >= s) {
      long = true; s = ep; if (s > pL) s = pL; if (s > nL) s = nL;
      r.rev = true; r.sar = s; r.dir = 1; af = start; ep = nH;
      s = r.raw = s + af * (ep - s); if (s > pL) s = pL; if (s > nL) s = nL;
    } else {
      r.sar = s; r.dir = -1;
      if (nL < ep) { ep = nL; af += inc; if (af > max) af = max; r.newEp = true }
      s = r.raw = s + af * (ep - s); if (s < pH) s = pH; if (s < nH) s = nH;
    }
    r.af = af; r.ep = ep; r.next = s; R[k] = r;
  }
  return { R, start, inc, max };
}

/** TA-Lib RSI's Wilder averages of gains (g) and losses (l) at candle i of the run, as calc/indicators.ts kRsi */
function rsiAt(x: number[], n: number, i: number) {
  let prevV = x[0], g = 0, l = 0, t = 1, g0 = 0, l0 = 0;
  for (let k = n; k > 0; k--) { const v = x[t++], d = v - prevV; prevV = v; if (d < 0) l -= d; else g += d }
  l /= n; g /= n;
  for (; t <= i; t++) { const v = x[t], d = v - prevV; prevV = v; g0 = g; l0 = l; l *= n - 1; g *= n - 1; if (d < 0) l -= d; else g += d; l /= n; g /= n }
  return { g, l, g0, l0, seed:i === n };
}

/** TA-Lib WMA's weighted sum Σ (weight × x) at candle i of the run: its running sums, as calc/indicators.ts kWma, so
    that Σwx ÷ Σw gives the chart's double (a direct sum can differ in the last digits on decimal prices) */
function wmaSum(x: number[], n: number, i: number) {
  if (n === 1) return x[i];
  let pSub = 0, pSum = 0, tv = 0, tr = 0, k = 0;
  for (; k < n - 1; k++) { pSub += x[k]; pSum += x[k] * (k + 1) }
  for (; k < i; k++) { pSub += x[k]; pSub -= tv; pSum += x[k] * n; tv = x[tr++]; pSum -= pSub }
  return pSum + x[i] * n;
}

/** the fast %K of x[k] in the min/max of `lo`/`hi` over the last m values (TA-Lib STOCHF: 0 on a zero range) */
function fastK(x: number[], hi: number[], lo: number[], m: number, k: number) {
  let h = hi[k - m + 1], l = lo[k - m + 1];
  for (let j = k - m + 2; j <= k; j++) { if (hi[j] > h) h = hi[j]; if (lo[j] < l) l = lo[j] }
  const d = (h - l) / 100.0;
  return { h, l, v:d !== 0.0 ? (x[k] - l) / d : 0.0 };
}

/* I01-I26 (I01 sma is the reference explainer) */
export const TECH_EXPLAIN_A: Record<string, TechExplainer> = {
  /* I01 SMA: SUM(src, n) / n over the last n valid, consecutive values (calc/indicators.ts sma, roll) */
  sma: (B, p, t) => {
    const n = intOf(p.length, 20), s = String(p.source || 'close');
    if (t - n + 1 < 0) return null;
    const xs: number[] = [];
    for (let i = t - n + 1; i <= t; i++) { const v = sourceAt(B, s, i); if (v === null) return null; xs.push(v) }
    const SUM = xs.reduce((x, v) => x + v, 0), combine = (v: Record<string, number>) => v.n ? v.SUM / v.n : null;
    const rows = xs.map((v, k) => [dateOf(B, t - n + 1 + k), fmt.num(v)]);
    const shown = rows.length > 12 ? [...rows.slice(0, 5), ['…', ''], ...rows.slice(-5)] : rows;
    return {
      output:'sma', value:combine({ SUM, n }), expr:'SUM ÷ n', span:{ from:dateOf(B, t - n + 1), to:dateOf(B, t), candles:n },
      terms:[{ key:'SUM', label:`Jumlah ${SOURCES[s] || s} ${n} candle`, value:SUM, unit:'price' }, { key:'n', label:'Panjang (n)', value:n, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${n} candle terakhir`, text:`${dateOf(B, t - n + 1)} sampai ${dateOf(B, t)}, nilai ${SOURCES[s] || s} setiap candle.`,
          table:{ head:['Tanggal', SOURCES[s] || s], rows:shown } },
        { title:'Jumlahkan', text:`SUM = ${fmt.num(SUM)}.` },
        { title:'Bagi dengan n', text:`${fmt.num(SUM)} ÷ ${n} = ${fmt.num(SUM / n)}.` },
      ],
    };
  },

  /* I02 EMA: TA-Lib EMA, SMA seed; EMA = EMA₋₁ + α (src − EMA₋₁), α = 2 / (n + 1) (F.ema) */
  ema: (B, p, t, output) => {
    const c = ctxOf('ema', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length;
    return avgExplain({ c, x:c.src, y:c.out.ema, n, form:'talib', name:`EMA ${n}`, key:'EMA', xName:srcLabel(c.P), xKey:'src', u:'price', fv:n2 });
  },

  /* I03 WMA: Σ (weight × src) / Σ weight, weights 1..n with the newest n (TA-Lib WMA) */
  wma: (B, p, t, output) => {
    const c = ctxOf('wma', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, a = i - n + 1, den = (n * (n + 1)) / 2, x = c.src, SW = wmaSum(x, n, i);
    const rows: string[][] = [];
    for (let k = a; k <= i; k++) { const w = k - a + 1; rows.push([c.date(k), n2(x[k]), String(w), n2(x[k] * w)]) }
    return done(c, 'Σwx ÷ Σw', [term('Σwx', `Jumlah bobot × ${srcName(c.P)} ${n} candle`, SW), term('Σw', `Jumlah bobot 1 sampai ${n}`, den, 'count')],
      v => (v['Σw'] ? v['Σwx'] / v['Σw'] : null), [
        { title:`Ambil ${n} candle terakhir`, text:`${c.date(a)} sampai ${c.date(i)}. Candle terbaru berbobot ${n}, sebelumnya ${n - 1}, dan seterusnya sampai 1 untuk candle terlama.`,
          table:{ head:['Tanggal', srcLabel(c.P), 'Bobot', 'Bobot × harga'], rows:short(rows) } },
        { title:'Jumlahkan', text:`Σwx = ${n2(SW)}; Σw = ${n} × (${n} + 1) ÷ 2 = ${den}.` },
        { title:'Bagi', text:`${n2(SW)} ÷ ${den} = ${n2(c.v)}.` },
      ], [a, i]);
  },

  /* I04 Hull MA: WMA over floor(√n) values of D = 2 × WMA(src, floor(n/2)) − WMA(src, n) (F.hma, wma helper) */
  hma: (B, p, t, output) => {
    const c = ctxOf('hma', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, h = Math.max(1, Math.floor(n / 2)), r = Math.max(1, Math.floor(Math.sqrt(n))), i = c.i, x = c.src;
    const wh = refWma(x, h), wn = refWma(x, n), D = wh.map((v, k) => (isN(v) && isN(wn[k]) ? 2 * v - wn[k] : null)), den = r * (r + 1) / 2;
    const terms = Array.from({ length:r }, (_, j) => term('D' + ago(j), `D ${c.date(i - j)}`, D[i - j] as number));
    const rows = Array.from({ length:r }, (_, j) => { const k = i - r + 1 + j; return [c.date(k), n2(wh[k]), n2(wn[k]), n2(D[k]), String(j + 1)] });
    return done(c, r === 1 ? 'D' : `(${terms.map((y, j) => `${r - j} × ${y.key}`).join(' + ')}) ÷ ${den}`, terms,
      v => { let s = 0; for (let j = 0; j < r; j++) s += v[terms[j].key] * (r - j); return s / den }, [
        { title:'Tiga panjang', text:`n = ${n}; setengah n = ${h} dan akar n = ${r} (keduanya dibulatkan ke bawah).` },
        { title:`WMA ${h} dan WMA ${n}`, text:`Rata-rata berbobot ${srcName(c.P)} (candle terbaru berbobot terbesar) di ${c.date(i)}: WMA ${h} = ${n2(wh[i])}, WMA ${n} = ${n2(wn[i])}.` },
        { title:'Selisih yang dipercepat (D)', text:`D = 2 × WMA ${h} − WMA ${n}; di ${c.date(i)}: 2 × ${n2(wh[i])} − ${n2(wn[i])} = ${n2(D[i])}.`,
          table:{ head:['Tanggal', `WMA ${h}`, `WMA ${n}`, 'D', 'Bobot'], rows } },
        { title:`WMA ${r} dari D`, text:`HMA = rata-rata berbobot ${r} nilai D terakhir (bobot ${r} untuk yang terbaru, jumlah bobot ${den}) = ${n2(c.v)}.` },
      ], [i - n - r + 2, i]);
  },

  /* I05 KAMA: KAMA₋₁ + SC (src − KAMA₋₁), SC = (ER (fast − slow) + slow)², ER = |change n| / path n (F.kama) */
  kama: (B, p, t, output) => {
    const c = ctxOf('kama', B, p, t, output, srcNeed); if (!c) return null;
    const { length:n, fast_length:fl, slow_length:sl } = c.P, i = c.i, x = c.src;
    const roc = x[i] - x[i - n]; let path = 0; const rows: string[][] = [];
    for (let k = i - n; k <= i; k++) { const d = k > i - n ? Math.abs(x[k] - x[k - 1]) : null; if (d !== null) path += d; rows.push([c.date(k), n2(x[k]), d === null ? '' : n2(d)]) }
    const er = path <= roc || isZero(path) ? 1.0 : Math.abs(roc / path);
    const cMax = 2.0 / (sl + 1.0), cDiff = 2.0 / (fl + 1.0) - cMax, sc0 = (er * cDiff) + cMax, SC = sc0 * sc0;
    const y = c.out.kama, first = !isN(y[i - 1]), prev = first ? x[i - 1] : (y[i - 1] as number), n6 = (v: number) => fmt.num(v, 6);
    return done(c, 'KAMA₋₁ + SC × (src − KAMA₋₁)',
      [term('KAMA₋₁', first ? `Nilai awal: ${srcName(c.P)} ${c.date(i - 1)}` : `KAMA ${c.date(i - 1)}`, prev), term('SC', 'Konstanta penghalus (SC)', SC, 'num'), term('src', `${srcLabel(c.P)} ${c.date(i)}`, x[i])],
      v => (v.src - v['KAMA₋₁']) * v.SC + v['KAMA₋₁'], [
        { title:`Arah ${n} candle`, text:`Perubahan bersih ${c.date(i - n)} ke ${c.date(i)}: ${n2(x[i])} − ${n2(x[i - n])} = ${n2(roc)}.` },
        { title:`Jalur ${n} candle`, text:`Jumlah perubahan absolut setiap candle (seberapa berliku jalannya) = ${n2(path)}.`, table:{ head:['Tanggal', srcLabel(c.P), '|Perubahan|'], rows:short(rows) } },
        { title:'Efficiency ratio (ER)', text:isZero(path) ? 'Jalurnya 0 (harga tidak bergerak): ER = 1.' : `ER = |arah| ÷ jalur = ${n2(Math.abs(roc))} ÷ ${n2(path)} = ${n4(er)} (1 = bergerak lurus, mendekati 0 = berputar-putar).` },
        { title:'Konstanta penghalus (SC)', text:`cepat = 2 ÷ (${fl} + 1) = ${n4(2 / (fl + 1))}, lambat = 2 ÷ (${sl} + 1) = ${n4(cMax)}; SC = (ER × (cepat − lambat) + lambat)² = (${n4(er)} × ${n4(cDiff)} + ${n4(cMax)})² = ${n6(SC)}.` },
        { title:'KAMA sebelumnya', text:first ? `KAMA dimulai di candle ini; nilai awalnya (KAMA₋₁) adalah ${srcName(c.P)} candle sebelumnya, ${n2(prev)}.`
          : `KAMA₋₁ (${c.date(i - 1)}) = ${n2(prev)}. KAMA dimulai dari ${srcName(c.P)} candle ke-${n} lalu diperbarui setiap candle sepanjang riwayat, jadi nilai lama tetap ikut memengaruhi.` },
        { title:'Hitung KAMA', text:`${n2(prev)} + ${n6(SC)} × (${n2(x[i])} − ${n2(prev)}) = ${n2(c.v)}.` },
      ]);
  },

  /* I06 MACD: EMA(fast) − EMA(slow); signal = TA-Lib EMA of MACD (seed = mean of its first values); histogram (F.macd) */
  macd: (B, p, t, output) => {
    const c = ctxOf('macd', B, p, t, output, srcNeed); if (!c) return null;
    const { fast_length:f, slow_length:s, signal_length:m } = c.P, i = c.i, r = c.out;
    const ef = F.ema(c.S, { length:f, source:c.P.source }).ema, es = F.ema(c.S, { length:s, source:c.P.source }).ema;
    const macdStep: Step = { title:'MACD candle ini', text:`MACD = EMA ${f} − EMA ${s} dari ${srcName(c.P)} = ${n2(ef[i])} − ${pr(es[i])} = ${n2(r.macd[i])}.` };
    if (c.o === 'signal') return avgExplain({ c, x:r.macd, y:r.signal, n:m, form:'talib', name:`Signal ${m}`, key:'SIG', xName:'MACD', xKey:'MACD', u:'price', fv:n2, before:[macdStep] });
    if (c.o === 'histogram') return done(c, 'MACD − SIG', [term('MACD', `MACD ${c.date(i)}`, r.macd[i]), term('SIG', `Signal ${m} ${c.date(i)}`, r.signal[i])], v => v.MACD - v.SIG, [
      macdStep,
      { title:`Signal ${m}`, text:emaLine(c, `Signal ${m}`, r.signal, r.macd, m, n2, 'MACD') },
      { title:'Histogram', text:`MACD − Signal = ${n2(r.macd[i])} − ${pr(r.signal[i])} = ${n2(c.v)}.` },
    ]);
    return done(c, 'EMAfast − EMAslow', [term('EMAfast', `EMA ${f} ${srcName(c.P)} (cepat)`, ef[i]), term('EMAslow', `EMA ${s} ${srcName(c.P)} (lambat)`, es[i])], v => v.EMAfast - v.EMAslow, [
      { title:`${srcLabel(c.P)} candle ini`, text:`${c.date(i)}: ${n2(c.src[i])}.` },
      { title:`EMA ${f} (cepat)`, text:emaLine(c, `EMA ${f}`, ef, c.src, f) },
      { title:`EMA ${s} (lambat)`, text:emaLine(c, `EMA ${s}`, es, c.src, s) },
      { title:'Hitung MACD', text:`${n2(ef[i])} − ${pr(es[i])} = ${n2(c.v)}.` },
    ]);
  },

  /* I07 ADX / +DI / −DI: Wilder sums of +DM, −DM and TR; DI = 100 DM / TR; ADX = Wilder average of DX (kDmi) */
  adx: (B, p, t, output) => {
    const c = ctxOf('adx', B, p, t, output, () => 'HLC'); if (!c) return null;
    const d = c.P.di_length, a = c.P.adx_smoothing, i = c.i, H = c.S.H as number[], L = c.S.L as number[], C = c.S.C as number[];
    const r = dmiAt(H, L, C, d, a, i);
    const diStep: Step = { title:'+DI dan −DI', text:`+DI = 100 × +DMₛ ÷ TRₛ = ${n2(r.plus)}; −DI = 100 × −DMₛ ÷ TRₛ = ${n2(r.minus)}.` };
    if (c.o === 'adx') {
      const dxStep: Step = { title:'DX candle ini', text:r.dx === null ? '+DI dan −DI sama-sama 0, jadi DX tidak ada di candle ini.'
        : `DX = 100 × |+DI − −DI| ÷ (+DI + −DI) = 100 × |${n2(r.plus)} − ${n2(r.minus)}| ÷ (${n2(r.plus)} + ${n2(r.minus)}) = ${n2(r.dx)}.` };
      if (r.how === 'seed') {
        const k0 = i - a + 1, rows = (r.seedDX as (number | null)[]).map((x, j) => [c.date(k0 + j), x === null ? '– (0)' : n2(x)]);
        return done(c, 'ΣDX ÷ n', [term('ΣDX', `Jumlah ${a} DX pertama`, r.sumDX, 'num'), term('n', 'Penghalusan ADX (n)', a, 'count')], v => (v.n ? v['ΣDX'] / v.n : null), [
          diStep, dxStep,
          { title:'ADX pertama', text:`Seri ADX dimulai di candle ini: rata-rata sederhana ${a} DX pertama (DX yang tidak ada dihitung 0).`, table:{ head:['Tanggal', 'DX'], rows:short(rows) } },
          { title:'Bagi dengan n', text:`${n2(r.sumDX)} ÷ ${a} = ${n2(c.v)}.` },
        ]);
      }
      if (r.how === 'keep') return done(c, 'ADX₋₁', [term('ADX₋₁', `ADX ${c.date(i - 1)}`, r.adx0, 'num')], v => v['ADX₋₁'], [
        diStep, dxStep, { title:'ADX tetap', text:`Tanpa DX, ADX sama dengan nilai sebelumnya: ${n2(c.v)}.` }]);
      return done(c, '(ADX₋₁ × (n − 1) + DX) ÷ n', [term('ADX₋₁', `ADX ${c.date(i - 1)}`, r.adx0, 'num'), term('DX', `DX ${c.date(i)}`, r.dx, 'num'), term('n', 'Penghalusan ADX (n)', a, 'count')],
        v => ((v['ADX₋₁'] * (v.n - 1)) + v.DX) / v.n, [
          diStep, dxStep,
          { title:'ADX sebelumnya', text:`ADX₋₁ (${c.date(i - 1)}) = ${n2(r.adx0)}. ADX dimulai dari rata-rata ${a} DX pertama, lalu dihaluskan setiap candle sepanjang riwayat (rata-rata Wilder).` },
          { title:'Hitung ADX', text:`(${n2(r.adx0)} × ${a - 1} + ${n2(r.dx)}) ÷ ${a} = ${n2(c.v)}.` },
        ]);
    }
    const plus = c.o === 'plus_di', K = plus ? '+DMₛ' : '−DMₛ', dm = plus ? r.pDM : r.mDM, dm0 = plus ? r.pDM0 : r.mDM0, dm1 = plus ? r.p1 : r.m1;
    return done(c, `100 × ${K} ÷ TRₛ`, [term(K, `Jumlah Wilder ${plus ? '+DM' : '−DM'} (${d})`, dm), term('TRₛ', `Jumlah Wilder TR (${d})`, r.tr)],
      v => (isZero(v['TRₛ']) ? 0 : 100.0 * (v[K] / v['TRₛ'])), [
        { title:'Gerak candle ini', text:`Naik = High − High₋₁ = ${n2(H[i])} − ${n2(H[i - 1])} = ${n2(r.dP)}; turun = Low₋₁ − Low = ${n2(L[i - 1])} − ${n2(L[i])} = ${n2(r.dM)}. Yang lebih besar dan positif dihitung, yang lain 0: +DM = ${n2(r.p1)}, −DM = ${n2(r.m1)}.`,
          table:{ head:['Tanggal', 'High', 'Low', 'Close'], rows:[i - 1, i].map(k => [c.date(k), n2(H[k]), n2(L[k]), n2(C[k])]) } },
        { title:'True range (TR)', text:`TR = max(H − L, |C₋₁ − H|, |C₋₁ − L|) = max(${n2(H[i] - L[i])}, ${n2(Math.abs(r.cPrev - H[i]))}, ${n2(Math.abs(r.cPrev - L[i]))}) = ${n2(r.t)}.` },
        { title:`Jumlah Wilder (${d})`, text:`Jumlah baru = jumlah lama − jumlah lama ÷ ${d} + nilai candle ini. ${K} = ${n2(dm0)} − ${n2(dm0 / d)} + ${n2(dm1)} = ${n2(dm)}; TRₛ = ${n2(r.tr0)} − ${n2(r.tr0 / d)} + ${n2(r.t)} = ${n2(r.tr)}. Jumlah ini dimulai dari jumlah biasa ${d - 1} candle pertama, lalu diperbarui setiap candle sepanjang riwayat.` },
        { title:`Hitung ${plus ? '+DI' : '−DI'}`, text:isZero(r.tr) ? 'TRₛ = 0: DI = 0.' : `100 × ${n2(dm)} ÷ ${n2(r.tr)} = ${n2(c.v)}.` },
      ]);
  },

  /* I08 Aroon: 100 (n − bars since the extreme of the last n + 1 bars) / n; ties take the most recent (TA-Lib AROON) */
  aroon: (B, p, t, output) => {
    const c = ctxOf('aroon', B, p, t, output, () => 'HL'); if (!c) return null;
    const n = c.P.length, i = c.i, up = c.o === 'aroon_up', X = (up ? c.S.H : c.S.L) as number[], word = up ? 'High tertinggi' : 'Low terendah';
    let e = i - n; for (let j = i - n + 1; j <= i; j++) if (up ? X[j] >= X[e] : X[j] <= X[e]) e = j;
    const k = i - e, rows = Array.from({ length:n + 1 }, (_, j) => [c.date(i - n + j), n2(X[i - n + j]), i - n + j === e ? '◀' : '']);
    return done(c, '100 × (n − k) ÷ n', [term('n', 'Panjang (n)', n, 'count'), term('k', `Candle sejak ${word}`, k, 'count')], v => (100.0 / v.n) * (v.n - v.k), [
      { title:`Ambil ${n + 1} candle`, text:`${c.date(i - n)} sampai ${c.date(i)} (n + 1 candle), nilai ${up ? 'High' : 'Low'}.`, table:{ head:['Tanggal', up ? 'High' : 'Low', ''], rows:short(rows) } },
      { title:`Cari ${word}`, text:`${word} = ${n2(X[e])} pada ${c.date(e)} (bila ada yang sama, yang terbaru dipakai): k = ${k} candle yang lalu.` },
      { title:'Hitung', text:`100 × (${n} − ${k}) ÷ ${n} = ${n2(c.v)}.` },
    ], [i - n, i]);
  },

  /* I09 Supertrend: HL2 ± factor × ATR, final bands carried while price stays inside, direction flips on a close
     through the active band (F.supertrend) */
  supertrend: (B, p, t, output) => {
    const c = ctxOf('supertrend', B, p, t, output, () => 'HLC'); if (!c) return null;
    const P = c.P, i = c.i, r = stAt(c.S, P, i), m = P.factor, mm = fmt.num(m);
    const lowerText = r.fl === null ? `Pita bawah akhir = pita bawah dasar (candle pertama Supertrend) = ${n2(r.nfl)}`
      : r.cPrev < r.fl ? `Pita bawah akhir = pita bawah dasar = ${n2(r.nfl)}, karena close sebelumnya ${n2(r.cPrev)} di bawah pita bawah sebelumnya ${n2(r.fl)}`
      : `Pita bawah akhir = max(pita bawah dasar, pita bawah sebelumnya) = max(${n2(r.bl)}, ${n2(r.fl)}) = ${n2(r.nfl)}`;
    const upperText = r.fu === null ? `Pita atas akhir = pita atas dasar (candle pertama Supertrend) = ${n2(r.nfu)}`
      : r.cPrev > r.fu ? `Pita atas akhir = pita atas dasar = ${n2(r.nfu)}, karena close sebelumnya ${n2(r.cPrev)} di atas pita atas sebelumnya ${n2(r.fu)}`
      : `Pita atas akhir = min(pita atas dasar, pita atas sebelumnya) = min(${n2(r.bu)}, ${n2(r.fu)}) = ${n2(r.nfu)}`;
    const dirText = r.how === 'first' ? 'Candle pertama Supertrend: arah awal naik (1).'
      : r.how === 'down' ? `Sebelumnya tren turun (garis di pita atas). Close ${n2(r.c)} ${r.c > r.nfu ? '>' : '≤'} pita atas ${n2(r.nfu)}: ${r.d === 1 ? 'berbalik naik (1)' : 'tetap turun (−1)'}.`
      : `Sebelumnya tren naik (garis di pita bawah). Close ${n2(r.c)} ${r.c < r.nfl ? '<' : '≥'} pita bawah ${n2(r.nfl)}: ${r.d === -1 ? 'berbalik turun (−1)' : 'tetap naik (1)'}.`;
    const steps: Step[] = [
      { title:`ATR ${P.atr_length}`, text:isN(r.atrPrev) ? `ATR = (ATR₋₁ × (${P.atr_length} − 1) + TR) ÷ ${P.atr_length} = (${n2(r.atrPrev)} × ${P.atr_length - 1} + ${n2(r.tr)}) ÷ ${P.atr_length} = ${n2(r.a)}; TR = max(H − L, |C₋₁ − H|, |C₋₁ − L|). Rata-rata Wilder seperti indikator ATR, berjalan sepanjang riwayat.` : `ATR pertama = rata-rata ${P.atr_length} true range pertama = ${n2(r.a)}.` },
      { title:'Pita dasar', text:`HL2 = (High + Low) ÷ 2 = ${n2(r.mid)}. Pita atas dasar = HL2 + ${mm} × ATR = ${n2(r.bu)}; pita bawah dasar = HL2 − ${mm} × ATR = ${n2(r.bl)}.` },
      { title:'Pita akhir', text:`${lowerText}. ${upperText}.` },
      { title:'Arah', text:dirText },
    ];
    if (c.o === 'direction') {
      if (r.how === 'first') return done(c, '1', [], () => 1, steps);
      return r.how === 'down'
        ? done(c, 'C > FU ? 1 : −1', [term('C', `Close ${c.date(i)}`, r.c), term('FU', 'Pita atas akhir', r.nfu)], v => (v.C > v.FU ? 1 : -1), steps)
        : done(c, 'C < FL ? −1 : 1', [term('C', `Close ${c.date(i)}`, r.c), term('FL', 'Pita bawah akhir', r.nfl)], v => (v.C < v.FL ? -1 : 1), steps);
    }
    const up = r.d === 1, prev = up ? r.fl : r.fu, reset = prev === null || (up ? r.cPrev < prev : r.cPrev > prev);
    const base = [term('HL2', `(High + Low) ÷ 2 ${c.date(i)}`, r.mid), term('m', 'Faktor (m)', m, 'num'), term('ATR', `ATR ${P.atr_length}`, r.a)];
    const band = (v: V) => (up ? v.HL2 - v.m * v.ATR : v.HL2 + v.m * v.ATR);
    const last: Step = { title:'Garis Supertrend', text:`Tren ${up ? 'naik: garis = pita bawah akhir' : 'turun: garis = pita atas akhir'} = ${n2(c.v)}.` };
    if (reset) return done(c, up ? 'HL2 − m × ATR' : 'HL2 + m × ATR', base, band, [...steps, last]);
    const K = up ? 'FL₋₁' : 'FU₋₁';
    return done(c, up ? 'max(HL2 − m × ATR, FL₋₁)' : 'min(HL2 + m × ATR, FU₋₁)', [...base, term(K, `Pita ${up ? 'bawah' : 'atas'} akhir ${c.date(i - 1)}`, prev)],
      v => (up ? Math.max(band(v), v[K]) : Math.min(band(v), v[K])), [...steps, last]);
  },

  /* I10 Donchian: upper = MAX(H, n), lower = MIN(L, n), basis = their mean (TA-Lib MAX / MIN) */
  donchian: (B, p, t, output) => {
    const c = ctxOf('donchian', B, p, t, output, () => 'HL'); if (!c) return null;
    const n = c.P.length, i = c.i, a = i - n + 1, H = c.S.H as number[], L = c.S.L as number[];
    let hh = H[a], ll = L[a], hk = a, lk = a;
    for (let k = a + 1; k <= i; k++) { if (H[k] > hh) { hh = H[k]; hk = k } if (L[k] < ll) { ll = L[k]; lk = k } }
    const steps: Step[] = [
      { title:`Ambil ${n} candle terakhir`, text:`${c.date(a)} sampai ${c.date(i)}.`, table:{ head:['Tanggal', 'High', 'Low'], rows:short(Array.from({ length:n }, (_, j) => [c.date(a + j), n2(H[a + j]), n2(L[a + j])])) } },
      { title:'Tertinggi dan terendah', text:`High tertinggi (HH) = ${n2(hh)} pada ${c.date(hk)}; Low terendah (LL) = ${n2(ll)} pada ${c.date(lk)}.` },
    ];
    const HH = term('HH', `High tertinggi ${n} candle`, hh), LL = term('LL', `Low terendah ${n} candle`, ll);
    if (c.o === 'upper') return done(c, 'HH', [HH], v => v.HH, [...steps, { title:'Pita atas', text:`Pita atas = HH = ${n2(c.v)}.` }], [a, i]);
    if (c.o === 'lower') return done(c, 'LL', [LL], v => v.LL, [...steps, { title:'Pita bawah', text:`Pita bawah = LL = ${n2(c.v)}.` }], [a, i]);
    return done(c, '(HH + LL) ÷ 2', [HH, LL], v => (v.HH + v.LL) / 2, [...steps, { title:'Garis tengah', text:`(${n2(hh)} + ${n2(ll)}) ÷ 2 = ${n2(c.v)}.` }], [a, i]);
  },

  /* I11 Keltner: basis = EMA (or SMA) of src; upper / lower = basis ± multiplier × range (ATR, TR or RMA(H − L)) */
  keltner: (B, p, t, output) => {
    const c = ctxOf('keltner', B, p, t, output, P => 'HLC' + needOf(P.source)); if (!c) return null;
    const P = c.P, n = P.length, i = c.i, x = c.src, H = c.S.H as number[], L = c.S.L as number[], C = c.S.C as number[], expo = truthy(P.use_exponential_ma);
    const basis = expo ? refEma(x, n) : refSma(x, n);
    if (c.o === 'basis') {
      if (expo) return avgExplain({ c, x, y:basis, n, form:'ref', name:`EMA ${n}`, key:'EMA', xName:srcLabel(P), xKey:'src', u:'price', fv:n2 });
      const xs = x.slice(i - n + 1, i + 1), SUM = xs.reduce((s, v) => s + v, 0);
      return done(c, 'SUM ÷ n', [term('SUM', `Jumlah ${srcName(P)} ${n} candle`, SUM), term('n', 'Panjang (n)', n, 'count')], v => (v.n ? v.SUM / v.n : null), [
        { title:`Ambil ${n} candle terakhir`, text:`${c.date(i - n + 1)} sampai ${c.date(i)}.`, table:{ head:['Tanggal', srcLabel(P)], rows:short(xs.map((v, k) => [c.date(i - n + 1 + k), n2(v)])) } },
        { title:'Garis tengah (SMA)', text:`${n2(SUM)} ÷ ${n} = ${n2(c.v)}.` },
      ], [i - n + 1, i]);
    }
    const style = P.bands_style === 'TR' ? 'TR' : P.bands_style === 'HL_RANGE' ? 'HL_RANGE' : 'ATR';
    const trOf = (k: number) => Math.max(H[k] - L[k], Math.abs(C[k - 1] - H[k]), Math.abs(C[k - 1] - L[k]));
    let R: number, RK: string, rLabel: string, rText: string;
    if (style === 'TR') { R = trOf(i); RK = 'TR'; rLabel = `True range ${c.date(i)}`; rText = `TR = max(H − L, |C₋₁ − H|, |C₋₁ − L|) = ${n2(R)}.` }
    else if (style === 'HL_RANGE') {
      const rr = refRma(H.map((h, k) => h - L[k]), n); R = rr[i] as number; RK = 'R'; rLabel = `Rata-rata Wilder (High − Low) ${n} candle`;
      rText = isN(rr[i - 1]) ? `R = (R₋₁ × (${n} − 1) + (High − Low)) ÷ ${n}, rata-rata Wilder yang berjalan sepanjang riwayat: ${n2(rr[i - 1])} → ${n2(R)}.` : `R pertama = rata-rata ${n} rentang High − Low pertama = ${n2(R)}.`;
    } else {
      const at = F.atr(c.S, { length:P.atr_length, smoothing_type:'RMA' }).atr; R = at[i] as number; RK = 'ATR'; rLabel = `ATR ${P.atr_length}`;
      rText = isN(at[i - 1]) ? `ATR = (ATR₋₁ × (${P.atr_length} − 1) + TR) ÷ ${P.atr_length} = (${n2(at[i - 1])} × ${P.atr_length - 1} + ${n2(trOf(i))}) ÷ ${P.atr_length} = ${n2(R)}; rata-rata Wilder yang berjalan sepanjang riwayat.` : `ATR pertama = rata-rata ${P.atr_length} true range pertama = ${n2(R)}.`;
    }
    const up = c.o === 'upper', sign = up ? '+' : '−', bv = basis[i] as number;
    return done(c, `Basis ${sign} m × ${RK}`, [term('Basis', `${expo ? 'EMA' : 'SMA'} ${n} ${srcName(P)}`, bv), term('m', 'Pengali (m)', P.multiplier, 'num'), term(RK, rLabel, R)],
      v => (up ? v.Basis + v.m * v[RK] : v.Basis - v.m * v[RK]), [
        { title:'Garis tengah', text:expo ? emaLine(c, `EMA ${n}`, basis, x, n) : `SMA ${n} ${srcName(P)} = ${n2(bv)}.` },
        { title:style === 'TR' ? 'True range' : style === 'HL_RANGE' ? 'Rentang rata-rata' : `ATR ${P.atr_length}`, text:rText },
        { title:up ? 'Pita atas' : 'Pita bawah', text:`${n2(bv)} ${sign} ${fmt.num(P.multiplier)} × ${n2(R)} = ${n2(c.v)}.` },
      ]);
  },

  /* I12 Parabolic SAR: SAR₋₁ + AF (EP − SAR₋₁), kept outside the last two candles' range; a touch flips the trend and the
     SAR jumps to the old extreme (TA-Lib SAREXT, F.psar) */
  psar: (B, p, t, output) => {
    const c = ctxOf('psar', B, p, t, output, () => 'HL'); if (!c) return null;
    const i = c.i, H = c.S.H as number[], L = c.S.L as number[], { R, start, inc, max } = psarTrace(H, L, c.P, i), r = R[i];
    const up = r.long0;
    const before: Step = { title:'Tren sebelum candle ini', text:(i === 1 ? `Arah awal dari dua candle pertama: ${up ? 'naik' : 'turun'} (turun hanya bila penurunan Low lebih besar dari kenaikan High). ` : `Tren ${up ? 'naik (SAR di bawah harga)' : 'turun (SAR di atas harga)'}. `)
      + `SAR yang berlaku untuk ${c.date(i)} = ${n2(r.tested)}.` };
    const check: Step = { title:'Cek pembalikan', text:up ? `Low ${n2(r.nL)} ${r.nL <= r.tested ? '≤' : '>'} SAR ${n2(r.tested)}: ${r.rev ? 'harga menyentuh SAR, tren berbalik turun (−1)' : 'tren naik berlanjut (1)'}.`
      : `High ${n2(r.nH)} ${r.nH >= r.tested ? '≥' : '<'} SAR ${n2(r.tested)}: ${r.rev ? 'harga menyentuh SAR, tren berbalik naik (1)' : 'tren turun berlanjut (−1)'}.` };
    if (c.o === 'direction') return up
      ? done(c, 'L ≤ SAR ? −1 : 1', [term('L', `Low ${c.date(i)}`, r.nL), term('SAR', `SAR yang berlaku ${c.date(i)}`, r.tested)], v => (v.L <= v.SAR ? -1 : 1), [before, check])
      : done(c, 'H ≥ SAR ? 1 : −1', [term('H', `High ${c.date(i)}`, r.nH), term('SAR', `SAR yang berlaku ${c.date(i)}`, r.tested)], v => (v.H >= v.SAR ? 1 : -1), [before, check]);
    if (r.rev) {
      const k1 = up ? 'H₋₁' : 'L₋₁', k0 = up ? 'H' : 'L', w = up ? 'High' : 'Low';
      return done(c, up ? 'max(EP, H₋₁, H)' : 'min(EP, L₋₁, L)',
        [term('EP', `Titik ekstrem tren ${up ? 'naik' : 'turun'} yang berakhir`, r.ep0), term(k1, `${w} ${c.date(r.pIdx)}`, up ? r.pH : r.pL), term(k0, `${w} ${c.date(i)}`, up ? r.nH : r.nL)],
        v => (up ? Math.max(v.EP, v[k1], v[k0]) : Math.min(v.EP, v[k1], v[k0])), [
          before, check,
          { title:'SAR baru', text:`Saat berbalik, SAR pindah ke titik ekstrem tren lama (EP = ${n2(r.ep0)}), ${up ? 'paling rendah setinggi High' : 'paling tinggi serendah Low'} candle sebelumnya dan candle ini: ${up ? 'max' : 'min'}(${n2(r.ep0)}, ${n2(up ? r.pH : r.pL)}, ${n2(up ? r.nH : r.nL)}) = ${n2(c.v)}. AF kembali ke ${n4(start)}.` },
        ]);
    }
    if (i === 1) {
      const K = up ? 'L₋₁' : 'H₋₁';
      return done(c, K, [term(K, `${up ? 'Low' : 'High'} ${c.date(0)}`, up ? L[0] : H[0])], v => v[K], [before,
        { title:'SAR pertama', text:`SAR pertama = ${up ? 'Low' : 'High'} candle pertama = ${n2(c.v)}.` }, check]);
    }
    const q = R[i - 1], w = up ? 'Low' : 'High', cl = up ? 'L' : 'H';
    const lim = q.pIdx === q.k ? [term(cl + '₋₁', `${w} ${c.date(q.k)}`, up ? q.nL : q.nH)] : [term(cl + '₋₂', `${w} ${c.date(q.pIdx)}`, up ? q.pL : q.pH), term(cl + '₋₁', `${w} ${c.date(q.k)}`, up ? q.nL : q.nH)];
    const keys = lim.map(x => x.key), raw = (v: V) => v['SAR₋₁'] + v.AF * (v.EP - v['SAR₋₁']);
    return done(c, `${up ? 'min' : 'max'}(SAR₋₁ + AF × (EP − SAR₋₁), ${keys.join(', ')})`,
      [term('SAR₋₁', `SAR ${c.date(i - 1)}`, q.sar), term('AF', 'Faktor percepatan (AF)', q.af, 'num'), term('EP', `Titik ekstrem (EP) sampai ${c.date(i - 1)}`, q.ep), ...lim],
      v => (up ? Math.min(raw(v), ...keys.map(k => v[k])) : Math.max(raw(v), ...keys.map(k => v[k]))), [
        before,
        { title:'Bahan dari candle sebelumnya', text:`SAR₋₁ = ${n2(q.sar)}; EP = ${up ? 'High tertinggi' : 'Low terendah'} sejak tren dimulai = ${n2(q.ep)}; AF = ${n4(q.af)} (mulai ${n4(start)}, naik ${n4(inc)} setiap EP baru, paling besar ${n4(max)}). SAR berjalan dari candle pertama sepanjang riwayat.` },
        { title:'Geser SAR', text:`SAR₋₁ + AF × (EP − SAR₋₁) = ${n2(q.sar)} + ${n4(q.af)} × (${n2(q.ep)} − ${n2(q.sar)}) = ${n2(q.raw)}.` },
        { title:'Batas', text:`SAR tidak boleh ${up ? 'di atas Low' : 'di bawah High'} ${keys.length > 1 ? 'dua candle' : 'candle'} sebelumnya: ${up ? 'min' : 'max'}(${[q.raw, ...lim.map(x => x.value)].map(n2).join(', ')}) = ${n2(c.v)}.` },
        check,
      ]);
  },

  /* I13 RSI: 100 − 100 / (1 + AG / AL), AG / AL Wilder averages of gains / losses (TA-Lib RSI; 0 when both are 0) */
  rsi: (B, p, t, output) => {
    const c = ctxOf('rsi', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, x = c.src, r = rsiAt(x, n, i), nm = srcName(c.P);
    const terms = [term('AG', `Rata-rata kenaikan (${n})`, r.g), term('AL', `Rata-rata penurunan (${n})`, r.l)];
    const combine: Combine = v => (isZero(v.AG + v.AL) ? 0 : v.AL === 0 ? 100 : 100 - 100 / (1 + v.AG / v.AL));
    const last: Step = { title:'Hitung RSI', text:isZero(r.g + r.l) ? 'AG dan AL sama-sama 0 (harga tidak bergerak): RSI = 0.' : r.l === 0 ? 'AL = 0 (tidak ada penurunan): RSI = 100.'
      : `RS = AG ÷ AL = ${n2(r.g)} ÷ ${n2(r.l)} = ${n4(r.g / r.l)}; RSI = 100 − 100 ÷ (1 + ${n4(r.g / r.l)}) = ${n2(c.v)}.` };
    const change = (k: number) => [c.date(k), n2(x[k]), n2(x[k] - x[k - 1])];
    if (r.seed) return done(c, '100 − 100 ÷ (1 + AG ÷ AL)', terms, combine, [
      { title:'RSI pertama', text:`Seri RSI dimulai di candle ini. Ambil ${n} perubahan ${nm} pertama, ${c.date(1)} sampai ${c.date(i)}.`, table:{ head:['Tanggal', srcLabel(c.P), 'Perubahan'], rows:short(Array.from({ length:n }, (_, j) => change(j + 1))) } },
      { title:'Rata-rata awal', text:`AG = jumlah kenaikan ÷ ${n} = ${n2(r.g)}; AL = jumlah penurunan ÷ ${n} = ${n2(r.l)}.` },
      last,
    ]);
    const d = x[i] - x[i - 1], g1 = d > 0 ? d : 0, l1 = d < 0 ? -d : 0;
    return done(c, '100 − 100 ÷ (1 + AG ÷ AL)', terms, combine, [
      { title:'Perubahan candle ini', text:`${nm} ${c.date(i)} − ${c.date(i - 1)} = ${n2(x[i])} − ${n2(x[i - 1])} = ${n2(d)}: kenaikan ${n2(g1)}, penurunan ${n2(l1)}.`,
        table:{ head:['Tanggal', srcLabel(c.P), 'Perubahan'], rows:Array.from({ length:Math.min(5, i) }, (_, j) => change(i - Math.min(5, i) + 1 + j)) } },
      { title:'Rata-rata kenaikan (AG)', text:`AG = (AG₋₁ × (${n} − 1) + kenaikan) ÷ ${n} = (${n2(r.g0)} × ${n - 1} + ${n2(g1)}) ÷ ${n} = ${n2(r.g)}.` },
      { title:'Rata-rata penurunan (AL)', text:`AL = (AL₋₁ × (${n} − 1) + penurunan) ÷ ${n} = (${n2(r.l0)} × ${n - 1} + ${n2(l1)}) ÷ ${n} = ${n2(r.l)}.` },
      { title:'Rata-rata Wilder', text:`AG dan AL dimulai dari rata-rata sederhana ${n} perubahan pertama (sampai ${c.date(n)}), lalu diperbarui setiap candle sepanjang riwayat; nilai lama tetap ikut memengaruhi.` },
      last,
    ]);
  },

  /* I14 Stochastic RSI: fast %K of RSI in its own min / max (0 on a zero range); K = SMA(fast %K), D = SMA(K) */
  stoch_rsi: (B, p, t, output) => {
    const c = ctxOf('stoch_rsi', B, p, t, output, srcNeed); if (!c) return null;
    const P = c.P, m = P.stoch_length, sk = P.smooth_k, sd = P.smooth_d, i = c.i;
    const rs = F.rsi(c.S, { length:P.rsi_length, source:P.source }).rsi as number[];
    const raw = (k: number) => fastK(rs, rs, rs, m, k), K = (k: number) => { let s = 0; for (let j = k - sk + 1; j <= k; j++) s += raw(j).v; return s / sk };
    const rsiStep: Step = { title:`RSI ${P.rsi_length}`, text:`RSI ${P.rsi_length} dari ${srcName(P)} (seperti indikator RSI, rata-rata Wilder sepanjang riwayat) di ${c.date(i)} = ${n2(rs[i])}.` };
    if (c.o === 'd') {
      const ks = Array.from({ length:sd }, (_, j) => K(i - sd + 1 + j)), mo = meanOf(ks, 'K', j => `K ${c.date(i - sd + 1 + j)}`, 'num');
      return done(c, mo.expr, mo.terms, mo.combine, [
        rsiStep,
        { title:`K (${sk} candle)`, text:`Setiap K = rata-rata ${sk} %K mentah, %K mentah = 100 × (RSI − min RSI ${m}) ÷ (max RSI ${m} − min RSI ${m}).`, table:{ head:['Tanggal', 'K'], rows:short(ks.map((v, j) => [c.date(i - sd + 1 + j), n2(v)])) } },
        { title:`D = rata-rata ${sd} K`, text:`(${ks.map(n2).join(' + ')}) ÷ ${sd} = ${n2(c.v)}.` },
      ]);
    }
    const rws = Array.from({ length:sk }, (_, j) => raw(i - sk + 1 + j)), mo = meanOf(rws.map(w => w.v), 'R', j => `%K mentah ${c.date(i - sk + 1 + j)}`, 'num');
    return done(c, mo.expr, mo.terms, mo.combine, [
      rsiStep,
      { title:'%K mentah', text:`%K mentah = 100 × (RSI − min) ÷ (max − min), min dan max dari ${m} RSI terakhir (0 bila max = min).`,
        table:{ head:['Tanggal', 'RSI', 'Min', 'Max', '%K mentah'], rows:short(rws.map((w, j) => [c.date(i - sk + 1 + j), n2(rs[i - sk + 1 + j]), n2(w.l), n2(w.h), n2(w.v)])) } },
      { title:`K = rata-rata ${sk} %K mentah`, text:`(${rws.map(w => n2(w.v)).join(' + ')}) ÷ ${sk} = ${n2(c.v)}.` },
    ]);
  },

  /* I15 Stochastic (slow): raw %K = 100 (C − LL) / (HH − LL) over k_length; K = SMA(raw, smooth_k); D = SMA(K, d_length) */
  stochastic: (B, p, t, output) => {
    const c = ctxOf('stochastic', B, p, t, output, () => 'HLC'); if (!c) return null;
    const P = c.P, kn = P.k_length, sk = P.smooth_k, dn = P.d_length, i = c.i, H = c.S.H as number[], L = c.S.L as number[], C = c.S.C as number[];
    const raw = (k: number) => fastK(C, H, L, kn, k), K = (k: number) => { let s = 0; for (let j = k - sk + 1; j <= k; j++) s += raw(j).v; return s / sk };
    const w = raw(i);
    const winStep: Step = { title:`Rentang ${kn} candle`, text:`${c.date(i - kn + 1)} sampai ${c.date(i)}: High tertinggi (HH) = ${n2(w.h)}, Low terendah (LL) = ${n2(w.l)}.`,
      table:{ head:['Tanggal', 'High', 'Low', 'Close'], rows:short(Array.from({ length:kn }, (_, j) => { const k = i - kn + 1 + j; return [c.date(k), n2(H[k]), n2(L[k]), n2(C[k])] })) } };
    if (c.o === 'd') {
      const ks = Array.from({ length:dn }, (_, j) => K(i - dn + 1 + j)), mo = meanOf(ks, 'K', j => `K ${c.date(i - dn + 1 + j)}`, 'num');
      return done(c, mo.expr, mo.terms, mo.combine, [
        winStep,
        { title:`K (${sk} candle)`, text:`Setiap K = rata-rata ${sk} %K mentah, %K mentah = 100 × (Close − LL) ÷ (HH − LL) dari ${kn} candle.`, table:{ head:['Tanggal', 'K'], rows:short(ks.map((v, j) => [c.date(i - dn + 1 + j), n2(v)])) } },
        { title:`D = rata-rata ${dn} K`, text:`(${ks.map(n2).join(' + ')}) ÷ ${dn} = ${n2(c.v)}.` },
      ], [i - kn - sk - dn + 3, i]);
    }
    const rws = Array.from({ length:sk }, (_, j) => raw(i - sk + 1 + j)), mo = meanOf(rws.map(x => x.v), 'R', j => `%K mentah ${c.date(i - sk + 1 + j)}`, 'num');
    return done(c, mo.expr, mo.terms, mo.combine, [
      winStep,
      { title:'%K mentah', text:`%K mentah = 100 × (Close − LL) ÷ (HH − LL), HH dan LL dari ${kn} candle yang berakhir di tanggal itu (0 bila HH = LL).`,
        table:{ head:['Tanggal', 'Close', 'LL', 'HH', '%K mentah'], rows:short(rws.map((x, j) => [c.date(i - sk + 1 + j), n2(C[i - sk + 1 + j]), n2(x.l), n2(x.h), n2(x.v)])) } },
      { title:`K = rata-rata ${sk} %K mentah`, text:`(${rws.map(x => n2(x.v)).join(' + ')}) ÷ ${sk} = ${n2(c.v)}.` },
    ], [i - kn - sk + 2, i]);
  },

  /* I16 Williams %R: −100 (HH − src) / (HH − LL) over n (TA-Lib WILLR; 0 on a zero range) */
  williams_r: (B, p, t, output) => {
    const c = ctxOf('williams_r', B, p, t, output, P => 'HL' + needOf(P.source)); if (!c) return null;
    const n = c.P.length, i = c.i, a = i - n + 1, H = c.S.H as number[], L = c.S.L as number[], X = c.src[i];
    let hh = H[a], ll = L[a]; for (let k = a + 1; k <= i; k++) { if (H[k] > hh) hh = H[k]; if (L[k] < ll) ll = L[k] }
    return done(c, '−100 × (HH − src) ÷ (HH − LL)', [term('HH', `High tertinggi ${n} candle`, hh), term('LL', `Low terendah ${n} candle`, ll), term('src', `${srcLabel(c.P)} ${c.date(i)}`, X)],
      v => { const d = (v.HH - v.LL) * (-0.01); return d !== 0.0 ? (v.HH - v.src) / d : 0.0 }, [
        { title:`Ambil ${n} candle terakhir`, text:`${c.date(a)} sampai ${c.date(i)}: HH = ${n2(hh)}, LL = ${n2(ll)}.`, table:{ head:['Tanggal', 'High', 'Low'], rows:short(Array.from({ length:n }, (_, j) => [c.date(a + j), n2(H[a + j]), n2(L[a + j])])) } },
        { title:`${srcLabel(c.P)} candle ini`, text:`${c.date(i)}: ${n2(X)}.` },
        { title:'Hitung', text:hh === ll ? 'HH = LL (rentang nol): %R = 0.' : `−100 × (${n2(hh)} − ${n2(X)}) ÷ (${n2(hh)} − ${n2(ll)}) = ${n2(c.v)}.` },
      ], [a, i]);
  },

  /* I17 ROC: 100 (src / src₋ₙ − 1) (TA-Lib ROC; 0 when src₋ₙ is 0) */
  roc: (B, p, t, output) => {
    const c = ctxOf('roc', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, x = c.src;
    return done(c, '(src ÷ src₋ₙ − 1) × 100', [term('src', `${srcLabel(c.P)} ${c.date(i)}`, x[i]), term('src₋ₙ', `${srcLabel(c.P)} ${c.date(i - n)} (${n} candle sebelumnya)`, x[i - n])],
      v => (v['src₋ₙ'] !== 0.0 ? ((v.src / v['src₋ₙ']) - 1.0) * 100.0 : 0.0), [
        { title:'Dua harga', text:`${c.date(i)}: ${n2(x[i])}; ${n} candle sebelumnya (${c.date(i - n)}): ${n2(x[i - n])}.` },
        { title:'Hitung', text:x[i - n] === 0 ? 'Harga dasar 0: ROC = 0.' : `(${n2(x[i])} ÷ ${n2(x[i - n])} − 1) × 100 = ${pc2(c.v)}.` },
      ], [i - n, i], pc2);
  },

  /* I18 Momentum: src − src₋ₙ (TA-Lib MOM) */
  momentum: (B, p, t, output) => {
    const c = ctxOf('momentum', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, x = c.src;
    return done(c, 'src − src₋ₙ', [term('src', `${srcLabel(c.P)} ${c.date(i)}`, x[i]), term('src₋ₙ', `${srcLabel(c.P)} ${c.date(i - n)} (${n} candle sebelumnya)`, x[i - n])],
      v => v.src - v['src₋ₙ'], [
        { title:'Dua harga', text:`${c.date(i)}: ${n2(x[i])}; ${n} candle sebelumnya (${c.date(i - n)}): ${n2(x[i - n])}.` },
        { title:'Hitung', text:`${n2(x[i])} − ${n2(x[i - n])} = ${n2(c.v)}.` },
      ], [i - n, i]);
  },

  /* I19 CCI: (TP − MA) / (c × MD), TP = (H + L + C) / 3, MA and MD (mean absolute deviation) over n (TA-Lib CCI) */
  cci: (B, p, t, output) => {
    const c = ctxOf('cci', B, p, t, output, () => 'HLC'); if (!c) return null;
    const n = c.P.length, k = c.P.constant, i = c.i, H = c.S.H as number[], L = c.S.L as number[], C = c.S.C as number[];
    const tp = H.map((_, j) => sourceAt(c.S, 'hlc3', j) as number), at = (j: number) => tp[i - (((i - j) % n) + n) % n];   // TA-Lib's circular order
    let ma = 0; for (let j = 0; j < n; j++) ma += at(j);
    ma /= n;
    let md = 0; for (let j = 0; j < n; j++) md += Math.abs(at(j) - ma);
    const MD = md / n, a = i - n + 1;
    return done(c, '(TP − MA) ÷ (c × MD)', [term('TP', `Harga tipikal ${c.date(i)}`, tp[i]), term('MA', `Rata-rata TP ${n} candle`, ma), term('MD', `Deviasi rata-rata TP ${n} candle`, MD), term('c', 'Konstanta (c)', k, 'num')],
      v => { const d = v.TP - v.MA; return d !== 0.0 && v.MD !== 0.0 ? d / (v.c * v.MD) : 0.0 }, [
        { title:`Harga tipikal ${n} candle`, text:`TP = (High + Low + Close) ÷ 3 untuk ${c.date(a)} sampai ${c.date(i)}.`,
          table:{ head:['Tanggal', 'High', 'Low', 'Close', 'TP'], rows:short(Array.from({ length:n }, (_, j) => [c.date(a + j), n2(H[a + j]), n2(L[a + j]), n2(C[a + j]), n2(tp[a + j])])) } },
        { title:'Rata-rata dan deviasi', text:`MA = rata-rata ${n} TP = ${n2(ma)}; MD = rata-rata |TP − MA| = ${n2(MD)}.` },
        { title:'Hitung', text:tp[i] - ma === 0 || MD === 0 ? 'TP sama dengan MA atau deviasinya 0: CCI = 0.' : `(${n2(tp[i])} − ${n2(ma)}) ÷ (${fmt.num(k, 3)} × ${n2(MD)}) = ${n2(c.v)}.` },
      ], [a, i]);
  },

  /* I20 CMO: 100 (SU − SD) / (SU + SD), plain n-candle sums of up and down changes (F.cmo, sma helper) */
  cmo: (B, p, t, output) => {
    const c = ctxOf('cmo', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, x = c.src, d = x.map((v, k) => (k ? v - x[k - 1] : null));
    const SU = (refSma(d.map(v => (isN(v) ? Math.max(v, 0) : null)), n)[i] as number) * n, SD = (refSma(d.map(v => (isN(v) ? Math.max(-v, 0) : null)), n)[i] as number) * n;
    const rows = Array.from({ length:n }, (_, j) => { const k = i - n + 1 + j; return [c.date(k), n2(x[k]), n2(d[k]), n2(Math.max(d[k], 0)), n2(Math.max(-d[k], 0))] });
    return done(c, '100 × (SU − SD) ÷ (SU + SD)', [term('SU', `Jumlah kenaikan ${n} candle`, SU), term('SD', `Jumlah penurunan ${n} candle`, SD)],
      v => { const s = v.SU + v.SD; return s ? 100 * (v.SU - v.SD) / s : null }, [
        { title:`Perubahan ${n} candle`, text:`Perubahan ${srcName(c.P)} setiap candle, ${c.date(i - n + 1)} sampai ${c.date(i)}.`, table:{ head:['Tanggal', srcLabel(c.P), 'Perubahan', 'Naik', 'Turun'], rows:short(rows) } },
        { title:'Jumlahkan', text:`SU = jumlah kenaikan = ${n2(SU)}; SD = jumlah penurunan = ${n2(SD)} (jumlah biasa ${n} candle, bukan rata-rata Wilder).` },
        { title:'Hitung', text:`100 × (${n2(SU)} − ${n2(SD)}) ÷ (${n2(SU)} + ${n2(SD)}) = ${n2(c.v)}.` },
      ], [i - n, i]);
  },

  /* I21 TSI: 100 DS / DA, DS / DA = EMA(EMA(change, long), short) of the change / of its size; signal = EMA(TSI) */
  tsi: (B, p, t, output) => {
    const c = ctxOf('tsi', B, p, t, output, srcNeed); if (!c) return null;
    const P = c.P, i = c.i, x = c.src, lo = P.long_length, sh = P.short_length, m = P.signal_length;
    const pc = x.map((v, k) => (k ? v - x[k - 1] : null)), apc = pc.map(v => (isN(v) ? Math.abs(v) : null));
    const e1 = refEma(pc, lo), ds = refEma(e1, sh), a1 = refEma(apc, lo), da = refEma(a1, sh);
    const tsi = ds.map((v, k) => (isN(v) && isN(da[k]) && da[k] !== 0 ? 100 * (v / (da[k] as number)) : null));
    const smooth: Step = { title:'Penghalusan ganda', text:`Perubahan ${srcName(P)} dihaluskan dua kali: EMA ${lo}, lalu EMA ${sh} dari hasilnya (DS); ukurannya |perubahan| dihaluskan sama (DA). Setiap EMA dimulai dari rata-rata sederhana nilai pertamanya dan berjalan sepanjang riwayat.`,
      table:{ head:['', 'Perubahan', '|Perubahan|'], rows:[[`Candle ${c.date(i)}`, n2(pc[i]), n2(apc[i])], [`EMA ${lo}`, n2(e1[i]), n2(a1[i])], [`EMA ${sh} (DS, DA)`, n2(ds[i]), n2(da[i])]] } };
    if (c.o === 'signal') return avgExplain({ c, x:tsi, y:refEma(tsi, m), n:m, form:'ref', name:`Signal ${m}`, key:'SIG', xName:'TSI', xKey:'TSI', u:'num', fv:n2,
      before:[smooth, { title:'TSI candle ini', text:`TSI = 100 × DS ÷ DA = 100 × ${pr(ds[i])} ÷ ${n2(da[i])} = ${n2(tsi[i])}.` }] });
    return done(c, '100 × DS ÷ DA', [term('DS', 'Perubahan yang dihaluskan dua kali', ds[i]), term('DA', '|Perubahan| yang dihaluskan dua kali', da[i])],
      v => (v.DA !== 0 ? 100 * (v.DS / v.DA) : null), [
        smooth,
        { title:'Hitung TSI', text:`100 × ${pr(ds[i])} ÷ ${n2(da[i])} = ${n2(c.v)}.` },
      ]);
  },

  /* I22 TRIX: 100 (E3 / E3₋₁ − 1), E3 = EMA(EMA(EMA(src, n), n), n) (TA-Lib TRIX) */
  trix: (B, p, t, output) => {
    const c = ctxOf('trix', B, p, t, output, srcNeed); if (!c) return null;
    const n = c.P.length, i = c.i, e1 = F.ema(c.S, { length:n, source:c.P.source }).ema, e2 = taEma(e1, n), e3 = taEma(e2, n), p4 = (v: number) => fmt.pct(v, 4);
    return done(c, '(E3 ÷ E3₋₁ − 1) × 100', [term('E3', `EMA tiga kali ${c.date(i)}`, e3[i]), term('E3₋₁', `EMA tiga kali ${c.date(i - 1)}`, e3[i - 1])],
      v => (v['E3₋₁'] !== 0.0 ? ((v.E3 / v['E3₋₁']) - 1.0) * 100.0 : 0.0), [
        { title:`EMA ${n} tiga kali`, text:`${srcName(c.P)} dihaluskan dengan EMA ${n}, hasilnya dihaluskan lagi dengan EMA ${n}, lalu sekali lagi (E3). Setiap EMA dimulai dari rata-rata sederhana ${n} nilai pertamanya dan berjalan sepanjang riwayat.`,
          table:{ head:['Tanggal', srcLabel(c.P), 'EMA 1', 'EMA 2', 'E3'], rows:[i - 1, i].map(k => [c.date(k), n2(c.src[k]), n2(e1[k]), n2(e2[k]), n2(e3[k])]) } },
        { title:'Hitung', text:`(${n2(e3[i])} ÷ ${n2(e3[i - 1])} − 1) × 100 = ${p4(c.v)}.` },
      ], undefined, p4);
  },

  /* I23 Ultimate Oscillator: 100 (w₁ A₁ + w₂ A₂ + w₃ A₃) / (w₁ + w₂ + w₃), A = ΣBP / ΣTR over each period (TA-Lib ULTOSC) */
  ultimate_osc: (B, p, t, output) => {
    const c = ctxOf('ultimate_osc', B, p, t, output, () => 'HLC'); if (!c) return null;
    const P = c.P, i = c.i, H = c.S.H as number[], L = c.S.L as number[], C = c.S.C as number[];
    const per = [P.fast_length, P.middle_length, P.slow_length], W = [P.weight_fast, P.weight_middle, P.weight_slow];
    const bpTr = (d: number): [number, number] => { const cy = C[d - 1], tl = Math.min(L[d], cy); let tr = H[d] - L[d], x = Math.abs(cy - H[d]); if (x > tr) tr = x; x = Math.abs(cy - L[d]); if (x > tr) tr = x; return [C[d] - tl, tr] };
    const sums = per.map(n => { let a = 0, b = 0; for (let d = i - n + 1; d <= i; d++) { const [x, y] = bpTr(d); a += x; b += y } return { a, b, A:isZero(b) ? 0 : a / b } });
    const [bp, tr] = bpTr(i), K = ['₁', '₂', '₃'];
    const terms = [...sums.map((s, k) => term('A' + K[k], `ΣBP ÷ ΣTR ${per[k]} candle`, s.A, 'num')), ...W.map((w, k) => term('w' + K[k], `Bobot ${per[k]} candle`, w, 'num'))];
    return done(c, '100 × (w₁ × A₁ + w₂ × A₂ + w₃ × A₃) ÷ (w₁ + w₂ + w₃)', terms,
      v => { const ws = v['w₁'] + v['w₂'] + v['w₃']; return ws ? 100.0 * ((v['w₁'] * v['A₁'] + v['w₂'] * v['A₂'] + v['w₃'] * v['A₃']) / ws) : null }, [
        { title:'Tekanan beli dan true range', text:`Setiap candle: BP = Close − min(Low, Close₋₁), TR = max(High, Close₋₁) − min(Low, Close₋₁). Di ${c.date(i)}: BP = ${n2(bp)}, TR = ${n2(tr)}.` },
        { title:'Tiga periode', text:'A = jumlah BP ÷ jumlah TR untuk setiap periode (periode tanpa rentang dihitung 0).',
          table:{ head:['Periode', 'ΣBP', 'ΣTR', 'A', 'Bobot'], rows:sums.map((s, k) => [`${per[k]} candle`, n2(s.a), n2(s.b), n4(s.A), fmt.num(W[k], 0)]) } },
        { title:'Rata-rata berbobot', text:`100 × (${sums.map((s, k) => `${fmt.num(W[k], 0)} × ${n4(s.A)}`).join(' + ')}) ÷ ${fmt.num(W[0] + W[1] + W[2], 0)} = ${n2(c.v)}.` },
      ], [i - Math.max(...per), i]);
  },

  /* I24 Awesome Oscillator: SMA(HL2, fast) − SMA(HL2, slow) (F.awesome_osc, sma helper) */
  awesome_osc: (B, p, t, output) => {
    const c = ctxOf('awesome_osc', B, p, t, output, () => 'HL'); if (!c) return null;
    const f = c.P.fast_length, s = c.P.slow_length, i = c.i, x = c.S.H.map((_, k) => sourceAt(c.S, 'hl2', k));
    const sf = refSma(x, f)[i] as number, ss = refSma(x, s)[i] as number, w = Math.max(f, s);
    return done(c, 'SMAfast − SMAslow', [term('SMAfast', `Rata-rata HL2 ${f} candle`, sf), term('SMAslow', `Rata-rata HL2 ${s} candle`, ss)], v => v.SMAfast - v.SMAslow, [
      { title:'Harga tengah (HL2)', text:`HL2 = (High + Low) ÷ 2 setiap candle; ${c.date(i)}: ${n2(x[i])}.`, table:{ head:['Tanggal', 'HL2'], rows:short(Array.from({ length:w }, (_, j) => [c.date(i - w + 1 + j), n2(x[i - w + 1 + j])])) } },
      { title:'Dua rata-rata', text:`SMA ${f} = ${n2(sf)} (${c.date(i - f + 1)} sampai ${c.date(i)}); SMA ${s} = ${n2(ss)} (${c.date(i - s + 1)} sampai ${c.date(i)}).` },
      { title:'Hitung', text:`${n2(sf)} − ${n2(ss)} = ${n2(c.v)}.` },
    ], [i - w + 1, i]);
  },

  /* I25 PPO: 100 (EMA fast − EMA slow) / EMA slow (0 when EMA slow is 0); signal = TA-Lib EMA of PPO; histogram */
  ppo: (B, p, t, output) => {
    const c = ctxOf('ppo', B, p, t, output, srcNeed); if (!c) return null;
    const { fast_length:f, slow_length:s, signal_length:m } = c.P, i = c.i, r = c.out;
    const ef = F.ema(c.S, { length:f, source:c.P.source }).ema, es = F.ema(c.S, { length:s, source:c.P.source }).ema;
    const ppoStep: Step = { title:'PPO candle ini', text:`PPO = (EMA ${f} − EMA ${s}) ÷ EMA ${s} × 100 = (${n2(ef[i])} − ${n2(es[i])}) ÷ ${n2(es[i])} × 100 = ${pc2(r.ppo[i])}.` };
    if (c.o === 'signal') return avgExplain({ c, x:r.ppo, y:r.signal, n:m, form:'talib', name:`Signal ${m}`, key:'SIG', xName:'PPO', xKey:'PPO', u:'pct', fv:pc2, before:[ppoStep] });
    if (c.o === 'histogram') return done(c, 'PPO − SIG', [term('PPO', `PPO ${c.date(i)}`, r.ppo[i], 'pct'), term('SIG', `Signal ${m} ${c.date(i)}`, r.signal[i], 'pct')], v => v.PPO - v.SIG, [
      ppoStep,
      { title:`Signal ${m}`, text:emaLine(c, `Signal ${m}`, r.signal, r.ppo, m, pc2, 'PPO') },
      { title:'Histogram', text:`PPO − Signal = ${pc2(r.ppo[i])} − ${pr(r.signal[i], pc2)} = ${pc2(c.v)}.` },
    ], undefined, pc2);
    return done(c, '(EMAfast − EMAslow) ÷ EMAslow × 100', [term('EMAfast', `EMA ${f} ${srcName(c.P)} (cepat)`, ef[i]), term('EMAslow', `EMA ${s} ${srcName(c.P)} (lambat)`, es[i])],
      v => (isZero(v.EMAslow) ? 0.0 : ((v.EMAfast - v.EMAslow) / v.EMAslow) * 100.0), [
        { title:`${srcLabel(c.P)} candle ini`, text:`${c.date(i)}: ${n2(c.src[i])}.` },
        { title:`EMA ${f} (cepat)`, text:emaLine(c, `EMA ${f}`, ef, c.src, f) },
        { title:`EMA ${s} (lambat)`, text:emaLine(c, `EMA ${s}`, es, c.src, s) },
        { title:'Hitung PPO', text:`(${n2(ef[i])} − ${n2(es[i])}) ÷ ${n2(es[i])} × 100 = ${pc2(c.v)}.` },
      ], undefined, pc2);
  },

  /* I26 Balance of Power: (C − O) / (H − L), 0 when H = L (TA-Lib BOP) */
  bop: (B, p, t, output) => {
    const c = ctxOf('bop', B, p, t, output, () => 'OHLC'); if (!c) return null;
    const i = c.i, [O, H, L, C] = [c.S.O[i], c.S.H[i], c.S.L[i], c.S.C[i]] as number[];
    return done(c, '(C − O) ÷ (H − L)', [term('C', `Close ${c.date(i)}`, C), term('O', `Open ${c.date(i)}`, O), term('H', `High ${c.date(i)}`, H), term('L', `Low ${c.date(i)}`, L)],
      v => { const r = v.H - v.L; return r < 1e-14 ? 0.0 : (v.C - v.O) / r }, [
        { title:'Candle ini', text:`${c.date(i)}: Open ${n2(O)}, High ${n2(H)}, Low ${n2(L)}, Close ${n2(C)}.` },
        { title:'Hitung', text:H - L < 1e-14 ? 'High = Low (rentang nol): BOP = 0.' : `(${n2(C)} − ${n2(O)}) ÷ (${n2(H)} − ${n2(L)}) = ${fmt.num(c.v, 4)}: ${c.v > 0 ? 'pembeli menguasai candle ini' : c.v < 0 ? 'penjual menguasai candle ini' : 'seimbang'}.` },
      ], [i, i], n4);
  },
};
