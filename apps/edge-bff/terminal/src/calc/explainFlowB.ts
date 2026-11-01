/* EXEC-IND-CARDS IC3: Flow explainers (calc/explain.ts: the interface, the helpers and the rule that the card's number
   is the chart's number). One file per part so they can be written side by side; explainFlowIndex.ts joins them. */
import type { FlowContext, FlowParams, FlowRows, Num } from './flow';
import { BOARDS, INVESTORS, above, atLeast, atMost, boardIndex, classBrokers, flowDefaults, investorIndex } from './flow';
import type { BrokerSums, Explanation, FlowExplainer, Step, Term } from './explain';
import { brokerRow, filterText, flowWindow, fmt, intOf, levelsOf, spanOf, topBy } from './explain';

/* ---- sums as the chart adds them (calc/flow.ts grid, bw, aw) ----
   The chart adds a broker's rows of one candle in row order (a cell), adds the cells of a window exactly and rounds once,
   and for "every broker" first adds the brokers' cells of each candle in broker order. Rupiah sums are about 1e10 with
   fractions, so a plain running sum (explain.ts windowSums) differs from the chart in the last digits (FL25 on the test
   data: up to 6e-5 rupiah). FL25 shows such a sum, FL23 adds them up, and Top-N rankings, signs and percentiles compare
   them: these sums follow the chart's order, so the card's number is the chart's to the last digit. */
type Col = 'bv' | 'sv' | 'bl' | 'sl' | 'bf' | 'sf' | 'miss';     // miss: rows without bf/sf
interface BS extends BrokerSums { i: number }                     // a broker's sums and its index in rows.brokers
interface Cells {
  /** broker b's sum of m over candles a..t */
  b(m: Col, b: number, a: number, t: number): number;
  /** every broker's sum of m over candles a..t */
  all(m: Col, a: number, t: number): number;
  /** every broker's sums over a..t (the measures ms, the others 0), in broker order */
  list(a: number, t: number, ms?: Col[]): BS[];
}
/** the exact sum of get(k), k = a..t, rounded once (compensated, as calc/flow.ts runSum and diff) */
function exactSum(get: (k: number) => number, a: number, t: number): number {
  let hi = 0, lo = 0;
  for (let k = a; k <= t; k++) { const x = get(k), s = hi + x, bb = s - hi; lo += (hi - (s - bb)) + (x - bb); hi = s }
  return hi + lo;
}
/** the cells of candles from..to with a board and investor filter (null = all, as calc/flow.ts grid) */
function cellsOf(R: FlowRows, from: number, to: number, boards: readonly string[] | null, investors: readonly string[] | null): Cells {
  const okB = new Set((boards ?? BOARDS).map(boardIndex)), okI = new Set((investors ?? INVESTORS).map(investorIndex));
  const B = R.brokers.length, S = Math.max(0, to - from + 1), keep: number[] = [];
  for (let k = 0; k < R.n; k++) if (R.t[k] >= from && R.t[k] <= to && okB.has(R.brd[k]) && okI.has(R.inv[k])) keep.push(k);
  const cell: Partial<Record<Col, Float64Array>> = {}, tot: Partial<Record<Col, Float64Array>> = {};
  const build = (m: Col) => {
    const arr = new Float64Array(B * S), sum = new Float64Array(S), col = m === 'miss' ? null : R[m], counts = m === 'bf' || m === 'sf';
    for (const k of keep) {
      const at = R.b[k] * S + R.t[k] - from, gap = Number.isNaN(R.bf[k]) || Number.isNaN(R.sf[k]);
      if (!col) { if (gap) arr[at] += 1 } else if (!counts || !gap) arr[at] += col[k];
    }
    for (let b = 0; b < B; b++) for (let i = 0; i < S; i++) sum[i] += arr[b * S + i];
    cell[m] = arr; tot[m] = sum;
  };
  const self: Cells = {
    b:(m, b, a, t) => { if (!cell[m]) build(m); const arr = cell[m]!, o = b * S - from; return exactSum(k => arr[o + k], a, t) },
    all:(m, a, t) => { if (!tot[m]) build(m); const s = tot[m]!; return exactSum(k => s[k - from], a, t) },
    list:(a, t, ms = ['bv', 'sv']) => R.brokers.map((code, i) => {
      const s: BS = { code, i, bv:0, sv:0, bl:0, sl:0, bf:0, sf:0 };
      for (const m of ms) if (m !== 'miss') s[m] = self.b(m, i, a, t);
      return s;
    }),
  };
  return self;
}
/** each candle's sum of bv over every broker with a board filter, plain (only whether it is 0 is read) */
function bvByCandle(R: FlowRows, boards: readonly string[] | null): Float64Array {
  const okB = new Set((boards ?? BOARDS).map(boardIndex)), out = new Float64Array(R.N);
  for (let k = 0; k < R.n; k++) if (okB.has(R.brd[k])) out[R.t[k]] += R.bv[k];
  return out;
}

/* ---- cohorts (calc/flow.ts cohort, topBrokers: score > 0, ties by broker code) ---- */
const net = (s: BrokerSums) => s.bv - s.sv;
const SCORE: Record<string, (s: BrokerSums) => number> = { net_buy:net, gross_buy:s => s.bv, net_sell:s => s.sv - s.bv, gross_buy_lots:s => s.bl };
const RANK: Record<string, string> = { net_buy:'net beli', gross_buy:'nilai beli (gross)', net_sell:'net jual', gross_buy_lots:'lot beli' };
const scoreOf = (p: FlowParams) => SCORE[p.rank || 'net_buy'] || SCORE.net_buy;
/** the cohort over a..t: null = every broker; the selected codes in broker order; else the Top-N by the rank */
function cohortOf(X: Cells, p: FlowParams, a: number, t: number, ms: Col[] = ['bv', 'sv']): BS[] | null {
  const scope = p.scope ?? 'topn';
  if (scope === 'all') return null;
  const L = X.list(a, t, p.rank === 'gross_buy_lots' && !ms.includes('bl') ? [...ms, 'bl'] : ms);
  if (scope === 'selected') { const want = new Set<string>(p.brokers || []); return L.filter(s => want.has(s.code)) }
  return topBy(L, intOf(p.top, 3), scoreOf(p)) as BS[];
}
/** the cohort's sum of m over a..t (calc/flow.ts cw: the members in cohort order) */
const cw = (X: Cells, C: BS[] | null, m: Col, a: number, t: number) => C ? C.reduce((s, x) => s + X.b(m, x.i, a, t), 0) : X.all(m, a, t);
function cohortText(p: FlowParams, C: BS[] | null): string {
  if (C === null) return 'semua broker';
  if ((p.scope ?? 'topn') === 'selected') { const b = Array.isArray(p.brokers) ? p.brokers : []; return b.length ? `broker pilihan ${b.join(', ')}` : 'broker pilihan (belum ada)' }
  return `${intOf(p.top, 3)} broker dengan ${RANK[p.rank] || 'net beli'} terbesar`;
}
const cohortStep = (p: FlowParams, C: BS[] | null, a: number, t: number, c: FlowContext): Step => C === null
  ? { title:'Kelompok broker', text:'Semua broker dihitung.' }
  : { title:'Kelompok broker', text:`${cap(cohortText(p, C))}, dari ${c.dates[a]} sampai ${c.dates[t]}${(p.scope ?? 'topn') === 'topn' ? ' (dihitung ulang di setiap candle; hanya broker dengan nilai positif)' : ''}.${C.length ? '' : ' Tidak ada broker yang memenuhi, jadi kelompoknya kosong (jumlahnya 0).'}`,
      ...(C.length ? { table:{ head:['Broker', 'Beli', 'Jual', 'Net'], rows:clip(C.map(brokerRow)) } } : {}) };

/* ---- shared ---- */
const div = (a: number, b: number): Num => b !== 0 && Number.isFinite(a) && Number.isFinite(b) ? a / b : null;
const pc = (v: number | null, d = 2) => v === null ? '–' : `${fmt.num(v, d)}%`;                 // a share, no sign
const lot = (v: number) => `${fmt.num(v, Number.isInteger(v) ? 0 : 2)} lot`;
const px = (v: number | null) => v === null ? '–' : `Rp ${fmt.num(v)}`;                         // a price per share
const cnt = (v: number) => fmt.num(v, 0);
const lastData = (R: FlowRows) => { for (let t = R.N - 1; t >= 0; t--) if (R.has[t]) return t; return -1 };
const gap = (rows: string[][]) => ['…', ...Array(Math.max(0, (rows[0]?.length ?? 1) - 1)).fill('')];
/** a long list: the first rows, then '…' */
const clip = (rows: string[][], max = 10) => rows.length <= max ? rows : [...rows.slice(0, max - 1), gap(rows)];
/** a long run of candles: the first and last n, '…' between */
const ends = (rows: string[][], n = 4) => rows.length <= 2 * n + 1 ? rows : [...rows.slice(0, n), gap(rows), ...rows.slice(-n)];
/** the last n rows, '…' before */
const tail = (rows: string[][], n = 8) => rows.length <= n ? rows : [gap(rows), ...rows.slice(-n)];
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
/** where v sits against the reference lines (explain.ts againstLevels, with the lines' own decimals: 2,5 stays 2,5) */
function against(v: number, levels: number[]): string {
  const up = [...levels].sort((x, y) => x - y), over = up.filter(l => v >= l), under = up.filter(l => v < l), f = (l: number) => fmt.num(l, Number.isInteger(l) ? 0 : 2);
  if (!over.length) return `di bawah garis acuan${up.length > 1 ? ' terendah' : ''} (${f(up[0])})`;
  if (!under.length) return `di atas garis acuan${up.length > 1 ? ' tertinggi' : ''} (${f(up[up.length - 1])})`;
  return `di antara garis acuan ${f(over[over.length - 1])} dan ${f(under[0])}`;
}
const readLevels = (p: FlowParams, v: number | null, shown: string): Step[] => {
  const lv = levelsOf(p);
  return v !== null && lv.length ? [{ title:'Baca hasilnya', text:`${shown} berada ${against(v, lv)}.` }] : [];
};
/** calc/flow.ts anchorAt: the first candle on or after the anchor date; not a date: the first candle */
function anchorOf(c: FlowContext, anchor: any): number {
  const d = typeof anchor === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(anchor) ? anchor : c.dates[0];
  const i = c.dates.findIndex(x => x >= d);
  return i < 0 ? c.rows.N : i;
}
/** calc/flow.ts resolveBrokers: a list, a classification (`class:...`), else the fallback */
const brokersOf = (c: FlowContext, v: any, fallback: () => string[]): string[] =>
  Array.isArray(v) ? v : typeof v === 'string' && v.startsWith('class:') ? classBrokers(c, v.slice(6)) : fallback();
/** FL23's default brokers (calc/flow.ts defaultInventoryBrokers): the 3 largest net buyers, every board and investor,
    over the last 20 candles with data */
function inventoryDefault(R: FlowRows): { codes: string[]; from: number; to: number } {
  const idx: number[] = [];
  for (let t = R.N - 1; t >= 0 && idx.length < 20; t--) if (R.has[t]) idx.push(t);
  if (!idx.length) return { codes:[], from:-1, to:-1 };
  const from = idx[idx.length - 1], to = idx[0];
  return { codes:topBy(cellsOf(R, from, to, null, null).list(from, to), 3, net).map(s => s.code), from, to };
}

/* ---- percentile (calc/flow.ts percentile: mid-rank over the baseline candles before t, t excluded) ---- */
interface Pct { x: number; lt: number; eq: number; n: number; hist: number[] }
/** null without x at t, when no x is set at or before t - bsl (fewer than bsl candles since the series' first value),
    or when none of the bsl candles before t has a value */
function pctAt(xAt: (k: number) => Num, isSet: (k: number) => boolean, t: number, bsl: number): Pct | null {
  const x = xAt(t);
  if (x === null) return null;
  let first = false;
  for (let k = 0; k <= t - bsl && !first; k++) first = isSet(k);
  if (!first) return null;
  let lt = 0, eq = 0; const hist: number[] = [];
  for (let k = t - bsl; k < t; k++) { const w = xAt(k); if (w === null) continue; hist.push(w); if (w < x) lt++; else if (w === x) eq++ }
  return hist.length ? { x, lt, eq, n:hist.length, hist } : null;
}
const pctCombine = (v: Record<string, number>) => v.n ? 100 * (v.LT + 0.5 * v.EQ) / v.n : null;
const pctTerms = (r: Pct, xLabel: string, xUnit: Term['unit']): Term[] => [
  { key:'x', label:xLabel, value:r.x, unit:xUnit },
  { key:'LT', label:'Riwayat yang lebih kecil dari x', value:r.lt, unit:'count' },
  { key:'EQ', label:'Riwayat yang sama dengan x', value:r.eq, unit:'count' },
  { key:'n', label:'Riwayat yang punya nilai', value:r.n, unit:'count' }];
function pctSteps(c: FlowContext, t: number, bsl: number, r: Pct, f: (v: number) => string, value: number): Step[] {
  const s = [...r.hist].sort((x, y) => x - y), m = s.length >> 1, med = s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  return [
    { title:'Bandingkan dengan riwayatnya', text:`x dibandingkan dengan x di ${bsl} candle sebelumnya (${c.dates[t - bsl]} sampai ${c.dates[t - 1]}; ${c.dates[t]} sendiri tidak ikut). ${cnt(r.n)} candle punya nilai: ${cnt(r.lt)} lebih kecil dari x (LT), ${cnt(r.eq)} sama (EQ), ${cnt(r.n - r.lt - r.eq)} lebih besar.`,
      table:{ head:['Riwayat', 'x'], rows:[['Terkecil', f(s[0])], ['Tengah (median)', f(med)], ['Terbesar', f(s[s.length - 1])], [`${c.dates[t]} (x)`, f(r.x)]] } },
    { title:'Hitung persentilnya', text:`100 × (${cnt(r.lt)} + 0,5 × ${cnt(r.eq)}) ÷ ${cnt(r.n)} = ${fmt.num(value)}. x di ${c.dates[t]} lebih tinggi dari sekitar ${fmt.num(value, 0)}% riwayatnya.` },
  ];
}

/* FL20-FL39 except FL24 (see explainFlowA.ts for the reference). Each is called with the parameters as computeFlow reads
   them (the registry defaults under the given values) and answers null where the chart has no value. */
const EX: Record<string, FlowExplainer> = {
  /* FL20 Implied Cost · Distance %: 100 (close / FL19 - 1); FL19 from the anchor with the frozen cohort (calc/flow.ts
     impliedCost, frozen, distance) */
  FL20: (c, p, t) => {
    const R = c.rows, a = anchorOf(c, p.anchor), close = c.close[t];
    if (t < a || t >= R.N || !R.has[t] || close === null || close === undefined) return null;
    const last = lastData(R), topn = (p.scope ?? 'topn') === 'topn', X = cellsOf(R, a, Math.max(t, last), p.boards ?? null, p.investors ?? null);
    const C = !topn ? cohortOf(X, p, a, a) : last < a ? [] : topBy(X.list(a, last, p.rank === 'gross_buy_lots' ? ['bv', 'sv', 'bl'] : ['bv', 'sv']), intOf(p.top, 3), scoreOf(p)) as BS[];
    const cc = (m: Col, k: number) => C ? C.reduce((s, x) => s + X.b(m, x.i, k, k), 0) : X.all(m, k, k);
    let Q = 0, K = 0;
    const hist: string[][] = [];
    for (let k = a; k <= t; k++) {
      if (!R.has[k]) continue;
      const bl = cc('bl', k), sl = cc('sl', k), bv = cc('bv', k), q = bl - sl;
      let price: number | null = null;
      if (q > 0) { price = bv / bl; K = Q <= 0 ? Math.max(Q + q, 0) * price : K + q * price }
      else if (q < 0 && Q > 0) K = K * Math.max(Q + q, 0) / Q;
      Q += q;
      hist.push([c.dates[k], lot(q), price === null ? '–' : px(price / 100), lot(Q), fmt.idr(K)]);
    }
    if (!(Q > 0)) return null;
    const IC = K / (100 * Q);
    if (!IC) return null;
    const combine = (v: Record<string, number>) => v.IC ? 100 * (v.C / v.IC - 1) : null, value = combine({ C:close, IC });
    const who = !topn ? (C === null ? 'Semua broker' : cap(cohortText(p, C)))
      : `${intOf(p.top, 3)} broker dengan ${RANK[p.rank] || 'net beli'} terbesar dari ${c.dates[a]} sampai ${c.dates[last]} (candle terakhir yang punya data). Kelompok ini dipilih sekali atas seluruh periode di chart, jadi ikut melihat candle sesudah ${c.dates[t]}`;
    return {
      output:'value', value, expr:'100 × (C ÷ IC − 1)', span:spanOf(c, a, t),
      terms:[{ key:'C', label:'Harga penutupan', value:close, unit:'price' }, { key:'IC', label:'Perkiraan harga pokok kelompok', value:IC, unit:'price' }], combine,
      steps:[
        { title:'Mulai dari tanggal awal', text:`Dihitung mulai ${c.dates[a]}, ${filterText(p)}. Persediaan (Q, lot) dan biaya (K, Rupiah) mulai dari 0.` },
        { title:'Kelompok broker tetap', text:`${who}.`,
          ...(C && C.length ? { table:{ head:['Broker', 'Beli', 'Jual', 'Net'], rows:clip((topn ? C : X.list(a, t).filter(s => C.some(x => x.i === s.i))).map(brokerRow)),
            note:`Beli, jual dan net dari ${c.dates[a]} sampai ${c.dates[topn ? last : t]}.` } } : {}) },
        { title:'Persediaan dan biaya setiap candle', text:`Setiap candle: q = lot beli − lot jual kelompok. Bila q > 0, Q bertambah q lot dengan harga beli candle itu (nilai beli ÷ lot beli), dan bila Q sebelumnya 0 atau kurang biayanya dimulai lagi. Bila q < 0, K turun sebanding dengan lot yang keluar. Sampai ${c.dates[t]}: Q = ${lot(Q)}, K = ${fmt.idr(K)}.`,
          table:{ head:['Tanggal', 'q', 'Harga beli', 'Q', 'K'], rows:tail(hist, 6) } },
        { title:'Harga pokok (Implied Cost)', text:`IC = K ÷ (100 × Q) = ${fmt.idr(K)} ÷ (100 × ${lot(Q)}) = ${px(IC)} per saham.` },
        { title:'Hitung jaraknya', text:`100 × (${px(close)} ÷ ${px(IC)} − 1) = ${fmt.pct(value)}: harga penutupan ${value >= 0 ? 'di atas' : 'di bawah'} harga pokok kelompok.` },
        ...readLevels(p, value, fmt.pct(value)),
      ],
    };
  },

  /* FL21 Net Flow Percentile · vs Turnover: percentile (baseline) of FL11 = 100 (BV(C) - SV(C)) / TBV(boards) */
  FL21: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 1), bsl = intOf(p.baseline, 250);
    if (flowWindow(R, t, W) === null || t - bsl < 0) return null;
    const lo = Math.max(0, t - bsl - W + 1), X = cellsOf(R, lo, t, p.boards ?? null, p.investors ?? null), D = cellsOf(R, lo, t, p.boards ?? null, null);
    const at = (k: number) => {
      const a = flowWindow(R, k, W); if (a === null) return null;
      const C = cohortOf(X, p, a, k), BV = cw(X, C, 'bv', a, k), SV = cw(X, C, 'sv', a, k), TBV = D.all('bv', a, k), v = div(BV - SV, TBV);
      return v === null ? null : { a, C, BV, SV, TBV, x:100 * v };
    };
    const day = bvByCandle(R, p.boards ?? null);
    const isSet = (k: number) => { const a = flowWindow(R, k, W); if (a === null) return false; for (let j = a; j <= k; j++) if (day[j] !== 0) return true; return false };
    const r = pctAt(k => at(k)?.x ?? null, isSet, t, bsl);
    if (!r) return null;
    const now = at(t)!, value = pctCombine({ LT:r.lt, EQ:r.eq, n:r.n });
    return {
      output:'value', value, expr:'100 × (LT + 0,5 × EQ) ÷ n', span:spanOf(c, Math.max(0, t - bsl - W + 1), t),
      terms:pctTerms(r, 'Arus bersih ÷ nilai transaksi di candle ini (x)', 'pct'), combine:pctCombine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[now.a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        cohortStep(p, now.C, now.a, t, c),
        { title:'Hitung x (Net Flow / Turnover)', text:`Net kelompok = ${fmt.idr(now.BV)} − ${fmt.idr(now.SV)} = ${fmt.idr(now.BV - now.SV)}. Nilai beli semua broker (papan terpilih, asing dan domestik) = ${fmt.idr(now.TBV)}. x = 100 × net ÷ nilai beli = ${fmt.pct(r.x)}.` },
        ...pctSteps(c, t, bsl, r, v => fmt.pct(v), value),
        ...readLevels(p, value, fmt.num(value)),
      ],
    };
  },

  /* FL22 Broker Buy Breadth: 100 x (active brokers with net > 0) / active brokers */
  FL22: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 1), a = flowWindow(R, t, W);
    if (a === null) return null;
    const act = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null).list(a, t).filter(s => s.bv > 0 || s.sv > 0);
    const P = act.filter(s => net(s) > 0).length, A = act.length;
    if (!A) return null;
    const combine = (v: Record<string, number>) => v.A ? 100 * v.P / v.A : null, value = combine({ P, A });
    const rows = [...act].sort((x, y) => net(y) - net(x) || (x.code < y.code ? -1 : 1)).map(brokerRow);
    return {
      output:'value', value, expr:'100 × P ÷ A', span:spanOf(c, a, t),
      terms:[{ key:'P', label:'Broker aktif yang net beli', value:P, unit:'count' }, { key:'A', label:'Broker aktif (ada beli atau jual)', value:A, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Net setiap broker aktif', text:`Broker aktif: ada nilai beli atau jual dalam jendela (${cnt(A)} broker). Net = beli − jual; ${cnt(P)} broker net beli (P).`,
          table:{ head:['Broker', 'Beli', 'Jual', 'Net'], rows:ends(rows, 5), note:'Urut dari net terbesar.' } },
        { title:'Hitung nilainya', text:`100 × ${cnt(P)} ÷ ${cnt(A)} = ${pc(value)} broker aktif menjadi pembeli bersih.` },
      ],
    };
  },

  /* FL23 Broker Inventory: per broker from the start candle, cumulative (or the candle's own) buy − sell, lots or rupiah;
     the total sums the lines. Outputs: the broker codes (computeFlow) or the chart's slots b1..b5, and total. */
  FL23: (c, p, t, output) => {
    const R = c.rows, auto = !Array.isArray(p.brokers) && !(typeof p.brokers === 'string' && p.brokers.startsWith('class:'));
    const def = auto ? inventoryDefault(R) : null, list = brokersOf(c, p.brokers, () => def!.codes).slice(0, 5), codes = [...new Set(list)];
    const out = output ?? codes[0] ?? 'total', slot = /^b([1-5])$/.exec(out);
    const code = list.includes(out) ? out : slot ? codes[+slot[1] - 1] : undefined;
    if (out === 'total' ? !p.total || !list.length : code === undefined) return null;
    const s = anchorOf(c, p.start);
    if (t < s || t >= R.N || !R.has[t]) return null;
    const value = p.unit === 'value', daily = p.view === 'daily', X = cellsOf(R, s, t, p.boards ?? null, p.investors ?? null);
    const f = (v: number) => value ? fmt.idr(v) : lot(v), what = value ? 'nilai (Rupiah)' : 'lot';
    const lineOf = (code: string) => {
      const b = R.brokers.indexOf(code), rows: string[][] = [];
      let acc = 0, prev = 0, B = 0, S = 0;
      for (let k = s; k <= t; k++) {
        if (!R.has[k]) continue;
        B = b < 0 ? 0 : X.b(value ? 'bv' : 'bl', b, k, k); S = b < 0 ? 0 : X.b(value ? 'sv' : 'sl', b, k, k);
        const d = B - S; prev = acc; acc += d;
        rows.push([c.dates[k], f(B), f(S), f(d), f(acc)]);
      }
      return { code, B, S, prev, v:daily ? B - S : acc, rows };
    };
    const where = `${auto ? `Broker default: 3 net pembeli terbesar (semua papan dan investor) ${def!.from >= 0 ? `dari ${c.dates[def!.from]} sampai ${c.dates[def!.to]}, 20 candle terakhir yang punya data` : ''}: ${codes.join(', ') || '–'}. ` : ''}Dihitung mulai ${c.dates[s]}, ${filterText(p)}, satuan ${what}${daily ? ', per candle' : ', kumulatif'}.`;
    if (out === 'total') {
      const lines = list.map(lineOf), seen = new Map<string, number>();
      const keys = lines.map(l => { const n = (seen.get(l.code) ?? 0) + 1; seen.set(l.code, n); return n > 1 ? `${l.code}_${n}` : l.code });
      const combine = (v: Record<string, number>) => keys.reduce((x, k) => x + v[k], 0), total = lines.reduce((x, l) => x + l.v, 0);
      return {
        output:out, value:total, expr:keys.join(' + '), span:spanOf(c, s, t),
        terms:lines.map((l, j) => ({ key:keys[j], label:`${daily ? 'Net' : 'Posisi'} ${l.code}`, value:l.v, unit:value ? 'idr' : 'lot' })), combine,
        steps:[
          { title:'Broker dan titik awal', text:where },
          { title:`${daily ? 'Net' : 'Posisi'} setiap broker di ${c.dates[t]}`, text:daily ? 'Net = beli − jual di candle ini.' : 'Posisi = jumlah (beli − jual) setiap candle sejak titik awal.',
            table:{ head:['Broker', daily ? 'Net' : 'Posisi'], rows:lines.map(l => [l.code, f(l.v)]) } },
          { title:'Jumlahkan', text:`${lines.map(l => f(l.v)).join(' + ')} = ${f(total)}.` },
        ],
      };
    }
    const L = lineOf(code!), combine = daily ? (v: Record<string, number>) => v.B - v.S : (v: Record<string, number>) => v.P + (v.B - v.S);
    return {
      output:out, value:L.v, expr:daily ? 'B − S' : 'P + (B − S)', span:spanOf(c, s, t),
      terms:[...(daily ? [] : [{ key:'P', label:'Posisi sampai candle data sebelumnya', value:L.prev, unit:(value ? 'idr' : 'lot') as Term['unit'] }]),
        { key:'B', label:`Beli ${code} di candle ini`, value:L.B, unit:value ? 'idr' : 'lot' }, { key:'S', label:`Jual ${code} di candle ini`, value:L.S, unit:value ? 'idr' : 'lot' }], combine,
      steps:[
        { title:'Broker dan titik awal', text:`${code}. ${where}${R.brokers.includes(code!) ? '' : ` ${code} tidak punya transaksi di data ini, jadi garisnya 0.`}` },
        { title:'Beli dan jual setiap candle', text:`Setiap candle yang punya data: beli − jual ${code}; posisi menjumlahkannya sejak ${c.dates[s]}.`,
          table:{ head:['Tanggal', 'Beli', 'Jual', 'Net', 'Posisi'], rows:tail(L.rows, 8) } },
        { title:'Hitung nilainya', text:daily ? `${f(L.B)} − ${f(L.S)} = ${f(L.v)}.` : `${f(L.prev)} + (${f(L.B)} − ${f(L.S)}) = ${f(L.v)}.` },
      ],
    };
  },

  /* FL25 Bandar Balance · Rupiah: NB + NS (the N largest net buyers' and net sellers' net over the window) */
  FL25: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 10), N = intOf(p.top, 3), a = flowWindow(R, t, W);
    if (a === null) return null;
    const L = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null).list(a, t);
    const buyers = topBy(L, N, net), sellers = topBy(L, N, s => -net(s));
    const NB = buyers.reduce((x, s) => x + net(s), 0), NS = sellers.reduce((x, s) => x + net(s), 0);
    const combine = (v: Record<string, number>) => v.NB + v.NS, value = combine({ NB, NS });
    return {
      output:'value', value, expr:'NB + NS', span:spanOf(c, a, t),
      terms:[{ key:'NB', label:`Net beli ${N} pembeli terbesar`, value:NB, unit:'idr' }, { key:'NS', label:`Net jual ${N} penjual terbesar`, value:NS, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Hitung net setiap broker', text:`Net = nilai beli − nilai jual selama jendela. Ambil ${N} net beli terbesar (NB) dan ${N} net jual terbesar (NS).`,
          table:{ head:['Broker', 'Beli', 'Jual', 'Net'], rows:[...buyers.map(brokerRow), ['NB', '', '', fmt.idr(NB)], ...sellers.map(brokerRow), ['NS', '', '', fmt.idr(NS)]] } },
        { title:'Hitung nilainya', text:`${fmt.idr(NB)} + ${fmt.idr(NS)} = ${fmt.idr(value)}: ${value > 0 ? 'pembeli besar lebih kuat dari penjual besar' : value < 0 ? 'penjual besar lebih kuat dari pembeli besar' : 'pembeli dan penjual besar seimbang'}.` },
      ],
    };
  },

  /* FL26 Net Flow Streak: s_t from s_{t-1} and the candle's net n_t, capped at ±limit; reset after a candle without data */
  FL26: (c, p, t) => {
    const R = c.rows, L = intOf(p.window, 60), topn = (p.scope ?? 'all') === 'topn';
    const valid = (k: number) => k >= 0 && k < R.N && (topn ? flowWindow(R, k, L) !== null : !!R.has[k]);
    if (!valid(t)) return null;
    const X = cellsOf(R, Math.max(0, t - (topn ? 2 * L - 1 : L)), t, p.boards ?? null, p.investors ?? null);
    const at = (k: number) => {
      const C = topn ? cohortOf(X, p, flowWindow(R, k, L)!, k) : cohortOf(X, p, k, k);
      return { C, BV:cw(X, C, 'bv', k, k), SV:cw(X, C, 'sv', k, k) };
    };
    /* the previous streak: the run of candles before t with data and a net of the same sign, at most the limit */
    const run: { k: number; n: number }[] = [];
    if (valid(t - 1)) {
      const n1 = at(t - 1), x1 = n1.BV - n1.SV, sg = Math.sign(x1);
      if (x1 !== 0) {
        run.push({ k:t - 1, n:x1 });
        for (let k = t - 2; run.length < L && valid(k); k--) { const e = at(k), x = e.BV - e.SV; if (Math.sign(x) !== sg) break; run.push({ k, n:x }) }
      }
    }
    const S = run.length ? Math.sign(run[0].n) * run.length : 0, now = at(t), NET = now.BV - now.SV;
    const combine = (v: Record<string, number>) => {
      const s = v.NET > 0 ? (v.S > 0 ? v.S + 1 : 1) : v.NET < 0 ? (v.S < 0 ? v.S - 1 : -1) : 0;
      return Math.max(-v.L, Math.min(v.L, s));
    };
    const value = combine({ S, NET, L }), rows = [...run].reverse().map(r => [c.dates[r.k], fmt.idr(r.n), r.n > 0 ? 'net beli' : 'net jual']);
    const raw = NET > 0 ? (S > 0 ? S + 1 : 1) : NET < 0 ? (S < 0 ? S - 1 : -1) : 0;
    const rule = NET > 0 ? (S > 0 ? `NET > 0 dan S > 0: S + 1 = ${cnt(raw)}` : 'NET > 0 dan S tidak positif: mulai dari 1')
      : NET < 0 ? (S < 0 ? `NET < 0 dan S < 0: S − 1 = ${cnt(raw)}` : 'NET < 0 dan S tidak negatif: mulai dari −1') : 'NET = 0 (tidak ada transaksi kelompok dengan filter ini): 0';
    return {
      output:'value', value, expr:'NET > 0: (S > 0 ? S + 1 : 1) · NET < 0: (S < 0 ? S − 1 : −1) · NET = 0: 0 · batas ±L',
      span:spanOf(c, t - run.length, t),
      terms:[{ key:'S', label:'Streak di candle sebelumnya', value:S, unit:'count' }, { key:'NET', label:'Net kelompok di candle ini', value:NET, unit:'idr' },
        { key:'L', label:'Batas hitungan (limit)', value:L, unit:'count' }], combine,
      steps:[
        { title:'Kelompok dan filter', text:`${cap(cohortText(p, now.C))}${topn ? `, dipilih ulang di setiap candle dari ${L} candle terakhir` : ''}, ${filterText(p)}. Batas hitungan ±${L} candle.` },
        ...(now.C && now.C.length ? [cohortStep(p, now.C, topn ? flowWindow(R, t, L)! : t, t, c)] : []),
        { title:`Net di ${c.dates[t]}`, text:`NET = nilai beli − nilai jual kelompok di candle ini = ${fmt.idr(now.BV)} − ${fmt.idr(now.SV)} = ${fmt.idr(NET)}.` },
        { title:'Streak sebelumnya', text:S ? `${cnt(Math.abs(S))} candle berturut-turut ${S > 0 ? 'net beli' : 'net jual'} sampai ${c.dates[t - 1]}${Math.abs(S) === L ? ' (sudah di batas)' : ''}, jadi S = ${cnt(S)}.`
            : t > 0 && valid(t - 1) ? `Net di ${c.dates[t - 1]} = 0, jadi S = 0.` : `Candle sebelumnya tidak punya data${topn ? ' atau jendela Top-N belum penuh' : ''}; hitungan mulai lagi dari S = 0.`,
          ...(rows.length ? { table:{ head:['Tanggal', 'Net', 'Arah'], rows:tail(rows, 8) } } : {}) },
        { title:'Hitung streak', text:`${rule}${raw !== value ? `, dibatasi menjadi ${cnt(value)}` : ''}. Streak di ${c.dates[t]} = ${cnt(value)}.` },
      ],
    };
  },

  /* FL27 Silent Accumulation: 1 when SMA(volume, recent) / SMA(volume, baseline before it) >= volume x and the close moved
     at most max move % over the recent candles */
  FL27: (c, p, t) => {
    const r = intOf(p.recent, 5), bsl = intOf(p.baseline, 20), volx = Number(p.volx), move = Number(p.move);
    if (t < r + bsl - 1 || t >= c.rows.N) return null;
    const mean = (a: number, b: number) => { let s = 0; for (let k = a; k <= b; k++) { const v = c.volume[k]; if (v === null) return null; s += v } return s / (b - a + 1) };
    const s1 = mean(t - r + 1, t), s0 = mean(t - r - bsl + 1, t - r), c1 = c.close[t], c0 = c.close[t - r];
    if (s1 === null || s0 === null || c1 === null || c0 === null || !s0 || !c0) return null;
    const VR = s1 / s0, M = 100 * Math.abs(c1 / c0 - 1), okV = atLeast(VR, volx), okM = atMost(M, move);
    const combine = (v: Record<string, number>) => atLeast(v.VR, v.X) && atMost(v.M, v.MV) ? 1 : 0, value = combine({ VR, X:volx, M, MV:move });
    return {
      output:'value', value, expr:'VR ≥ X dan M ≤ MV → 1, selain itu 0', span:spanOf(c, t - r - bsl + 1, t),
      terms:[{ key:'VR', label:'Rasio volume (terbaru ÷ pembanding)', value:VR, unit:'num' }, { key:'X', label:'Ambang rasio volume', value:volx, unit:'num' },
        { key:'M', label:'Gerak harga (%)', value:M, unit:'pct' }, { key:'MV', label:'Batas gerak harga (%)', value:move, unit:'pct' }], combine,
      steps:[
        { title:'Volume terbaru', text:`Rata-rata volume ${r} candle terakhir (${c.dates[t - r + 1]} sampai ${c.dates[t]}) = ${cnt(s1)} saham.` },
        { title:'Volume pembanding', text:`Rata-rata volume ${bsl} candle sebelumnya (${c.dates[t - r - bsl + 1]} sampai ${c.dates[t - r]}) = ${cnt(s0)} saham.` },
        { title:'Rasio volume', text:`VR = ${cnt(s1)} ÷ ${cnt(s0)} = ${fmt.num(VR, 4)}; syarat VR ≥ ${fmt.num(volx)}: ${okV ? 'terpenuhi' : 'tidak terpenuhi'}.` },
        { title:'Gerak harga', text:`M = 100 × |${px(c1)} ÷ ${px(c0)} − 1| = ${pc(M)} (close ${c.dates[t]} dibanding ${c.dates[t - r]}); syarat M ≤ ${pc(move)}: ${okM ? 'terpenuhi' : 'tidak terpenuhi'}.` },
        { title:'Hasil', text:value ? 'Kedua syarat terpenuhi: 1, tanda di bawah candle (volume naik, harga hampir diam).' : 'Tidak semua syarat terpenuhi: 0, tidak ada tanda.' },
      ],
    };
  },

  /* FL28 Average Daily Value: SMA(close x volume, sessions) */
  FL28: (c, p, t) => {
    const n = intOf(p.window, 20);
    if (t < n - 1 || t >= c.rows.N) return null;
    let S = 0; const rows: string[][] = [];
    for (let k = t - n + 1; k <= t; k++) {
      const cl = c.close[k], v = c.volume[k];
      if (cl === null || v === null) return null;
      S += cl * v; rows.push([c.dates[k], px(cl), cnt(v), fmt.idr(cl * v)]);
    }
    const combine = (v: Record<string, number>) => v.n ? v.S / v.n : null, value = combine({ S, n });
    return {
      output:'value', value, expr:'S ÷ n', span:spanOf(c, t - n + 1, t),
      terms:[{ key:'S', label:`Jumlah nilai transaksi ${n} sesi`, value:S, unit:'idr' }, { key:'n', label:'Jumlah sesi', value:n, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${n} sesi`, text:`${c.dates[t - n + 1]} sampai ${c.dates[t]}; nilai transaksi setiap sesi = close × volume.`,
          table:{ head:['Tanggal', 'Close', 'Volume', 'Nilai'], rows:ends(rows) } },
        { title:'Jumlahkan', text:`S = ${fmt.idr(S)}.` },
        { title:'Bagi dengan jumlah sesi', text:`${fmt.idr(S)} ÷ ${n} = ${fmt.idr(value)} per sesi.` },
      ],
    };
  },

  /* FL29 Bandar Balance · Accumulation Days: 100 x (candles in the window whose own one-candle balance is above the
     threshold) / days */
  FL29: (c, p, t) => {
    const R = c.rows, N = intOf(p.top, 3), D = intOf(p.window, 20), th = Number(p.threshold) || 0, a = flowWindow(R, t, D);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null), rows: string[][] = [];
    let K = 0;
    for (let k = a; k <= t; k++) {
      if (!R.has[k]) { rows.push([c.dates[k], '–', '–', 'tidak (tanpa data)']); continue }
      const L = X.list(k, k), nb = topBy(L, N, net).reduce((x, s) => x + net(s), 0), ns = topBy(L, N, s => -net(s)).reduce((x, s) => x + net(s), 0);
      const v = div(nb + ns, X.all('bv', k, k)), bal = v === null ? null : 100 * v, up = bal !== null && above(bal, th);
      if (up) K++;
      rows.push([c.dates[k], fmt.idr(nb + ns), bal === null ? '–' : fmt.pct(bal), up ? 'ya' : 'tidak']);
    }
    const combine = (v: Record<string, number>) => v.D ? 100 * v.K / v.D : null, value = combine({ K, D });
    return {
      output:'value', value, expr:'100 × K ÷ D', span:spanOf(c, a, t),
      terms:[{ key:'K', label:`Candle dengan balance di atas ${fmt.num(th)}%`, value:K, unit:'count' }, { key:'D', label:'Jumlah candle (days)', value:D, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${D} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Balance setiap candle', text:`Setiap candle dihitung sendiri: 100 × (NB + NS) ÷ nilai beli semua broker di candle itu, dengan ${N} net pembeli dan ${N} net penjual terbesar candle itu. Candle tanpa data broker dihitung tidak di atas.`,
          table:{ head:['Tanggal', 'NB + NS', 'Balance', `Di atas ${fmt.num(th)}%`], rows:ends(rows, 5) } },
        { title:'Hitung harinya', text:`${cnt(K)} dari ${D} candle punya balance di atas ${fmt.num(th)}% (K).` },
        { title:'Hitung nilainya', text:`100 × ${cnt(K)} ÷ ${D} = ${pc(value)}.` },
      ],
    };
  },

  /* FL30 Crossing Share: 100 BV(Nego + Cash) / BV(all boards), investor filter on both */
  FL30: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 20), a = flowWindow(R, t, W);
    if (a === null) return null;
    const inv = p.investors ?? null, X = cellsOf(R, a, t, ['Nego', 'Cash'], inv).all('bv', a, t), T = cellsOf(R, a, t, null, inv).all('bv', a, t);
    const combine = (v: Record<string, number>) => { const q = div(v.X, v.T); return q === null ? null : 100 * q }, value = combine({ X, T });
    if (value === null) return null;
    const okI = new Set((inv ?? INVESTORS).map(investorIndex)), per = [0, 0, 0];
    for (let k = 0; k < R.n; k++) if (R.t[k] >= a && R.t[k] <= t && okI.has(R.inv[k])) per[R.brd[k]] += R.bv[k];
    return {
      output:'value', value, expr:'100 × X ÷ T', span:spanOf(c, a, t),
      terms:[{ key:'X', label:'Nilai beli papan Nego + Tunai', value:X, unit:'idr' }, { key:'T', label:'Nilai beli semua papan', value:T, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, semua papan, ${!inv || inv.length === INVESTORS.length ? 'asing dan domestik' : inv.join(', ')}.` },
        { title:'Nilai beli per papan', text:'Nego dan Tunai adalah transaksi di luar pasar reguler (sering transaksi blok).',
          table:{ head:['Papan', 'Nilai beli'], rows:[['Reguler', fmt.idr(per[0])], ['Nego', fmt.idr(per[1])], ['Tunai', fmt.idr(per[2])], ['Semua (T)', fmt.idr(T)]] } },
        { title:'Hitung nilainya', text:`100 × ${fmt.idr(X)} ÷ ${fmt.idr(T)} = ${pc(value)} nilai beli terjadi di luar pasar reguler.` },
      ],
    };
  },

  /* FL31 Insider Net Change: insider BUY value − SELL value with a date in the window's candles; 0 when none */
  FL31: (c, p, t) => {
    const N = c.rows.N, w = intOf(p.window, 20);
    if (t < w - 1 || t >= N) return null;
    const per = new Float64Array(N);
    for (const r of c.insider) if (r.t >= 0 && r.t < N) per[r.t] += r.value;
    let value = 0;
    for (let k = t - w + 1; k <= t; k++) value += per[k];
    const ins = c.insider.filter(r => r.t >= t - w + 1 && r.t <= t && r.t < N);
    const B = ins.reduce((x, r) => r.value > 0 ? x + r.value : x, 0), S = ins.reduce((x, r) => r.value < 0 ? x - r.value : x, 0);
    const combine = (v: Record<string, number>) => v.B - v.S;
    return {
      output:'value', value, expr:'B − S', span:spanOf(c, t - w + 1, t),
      terms:[{ key:'B', label:'Nilai beli orang dalam', value:B, unit:'idr' }, { key:'S', label:'Nilai jual orang dalam', value:S, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${w} candle`, text:`${c.dates[t - w + 1]} sampai ${c.dates[t]}: transaksi orang dalam (insider) yang tanggalnya jatuh di candle-candle ini.` },
        ins.length ? { title:'Transaksi orang dalam', text:`${cnt(ins.length)} transaksi: beli ${fmt.idr(B)} (B), jual ${fmt.idr(S)} (S).`,
            table:{ head:['Tanggal', 'Aksi', 'Nilai'], rows:clip([...ins].sort((x, y) => x.t - y.t).map(r => [c.dates[r.t], r.value >= 0 ? 'Beli' : 'Jual', fmt.idr(Math.abs(r.value))])) } }
          : { title:'Transaksi orang dalam', text:'Tidak ada transaksi orang dalam di jendela ini, jadi nilainya 0.' },
        { title:'Hitung nilainya', text:`${fmt.idr(B)} − ${fmt.idr(S)} = ${fmt.idr(value)}${value > 0 ? ': orang dalam lebih banyak membeli' : value < 0 ? ': orang dalam lebih banyak menjual' : ''}.` },
      ],
    };
  },

  /* FL32 Transactions · Spike: BF_t / mean(BF over the baseline candles before t); null when a row lacks counts */
  FL32: (c, p, t) => {
    const R = c.rows, bsl = intOf(p.baseline, 20), a = flowWindow(R, t, bsl + 1);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null);
    if (X.all('miss', a, t) > 0) return null;
    const F = X.all('bf', t, t), FB = X.all('bf', a, t - 1);
    const combine = (v: Record<string, number>) => div(v.F, v.FB / v.n), value = combine({ F, FB, n:bsl });
    if (value === null) return null;
    const rows: string[][] = [];
    for (let k = a; k < t; k++) rows.push([c.dates[k], R.has[k] ? cnt(X.all('bf', k, k)) : '0 (tanpa data)']);
    return {
      output:'value', value, expr:'F ÷ (FB ÷ n)', span:spanOf(c, a, t),
      terms:[{ key:'F', label:'Transaksi beli di candle ini', value:F, unit:'count' }, { key:'FB', label:`Jumlah transaksi beli ${bsl} candle sebelumnya`, value:FB, unit:'count' },
        { key:'n', label:'Candle pembanding (baseline)', value:bsl, unit:'count' }], combine,
      steps:[
        { title:'Ambil candle', text:`${c.dates[t]} dan ${bsl} candle sebelumnya (${c.dates[a]} sampai ${c.dates[t - 1]}), ${filterText(p)}. Jumlah transaksi beli (frekuensi) semua broker.` },
        { title:'Transaksi beli hari ini', text:`F = ${cnt(F)} transaksi beli di ${c.dates[t]}.` },
        { title:'Rata-rata pembanding', text:`FB = ${cnt(FB)}; rata-rata = ${cnt(FB)} ÷ ${bsl} = ${fmt.num(FB / bsl)}. Candle tanpa data broker menambah 0 dan pembaginya tetap ${bsl}.`,
          table:{ head:['Tanggal', 'Transaksi beli'], rows:ends(rows) } },
        { title:'Hitung lonjakannya', text:`${cnt(F)} ÷ ${fmt.num(FB / bsl)} = ${fmt.num(value)}×.` },
        ...readLevels(p, value, `${fmt.num(value)}×`),
      ],
    };
  },

  /* FL33 Transaction Size · Change %: 100 ((BV/BF over the recent candles) / (BV/BF over the baseline before them) - 1) */
  FL33: (c, p, t) => {
    const R = c.rows, r = intOf(p.recent, 5), bsl = intOf(p.baseline, 20), a = flowWindow(R, t, r + bsl);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null);
    if (X.all('miss', a, t) > 0) return null;
    const BV1 = X.all('bv', t - r + 1, t), BF1 = X.all('bf', t - r + 1, t), BV0 = X.all('bv', a, t - r), BF0 = X.all('bf', a, t - r);
    const combine = (v: Record<string, number>) => {
      const now = div(v.BV1, v.BF1), before = div(v.BV0, v.BF0);
      return now === null || before === null || !before ? null : 100 * (now / before - 1);
    };
    const value = combine({ BV1, BF1, BV0, BF0 });
    if (value === null) return null;
    return {
      output:'value', value, expr:'100 × ((BV1 ÷ BF1) ÷ (BV0 ÷ BF0) − 1)', span:spanOf(c, a, t),
      terms:[{ key:'BV1', label:`Nilai beli ${r} candle terakhir`, value:BV1, unit:'idr' }, { key:'BF1', label:`Transaksi beli ${r} candle terakhir`, value:BF1, unit:'count' },
        { key:'BV0', label:`Nilai beli ${bsl} candle sebelumnya`, value:BV0, unit:'idr' }, { key:'BF0', label:`Transaksi beli ${bsl} candle sebelumnya`, value:BF0, unit:'count' }], combine,
      steps:[
        { title:'Ambil candle', text:`Terbaru: ${c.dates[t - r + 1]} sampai ${c.dates[t]} (${r} candle). Pembanding: ${c.dates[a]} sampai ${c.dates[t - r]} (${bsl} candle). ${cap(filterText(p))}, semua broker.` },
        { title:'Ukuran transaksi terbaru', text:`BV1 ÷ BF1 = ${fmt.idr(BV1)} ÷ ${cnt(BF1)} = ${fmt.idr(BV1 / BF1)} per transaksi beli.` },
        { title:'Ukuran transaksi pembanding', text:`BV0 ÷ BF0 = ${fmt.idr(BV0)} ÷ ${cnt(BF0)} = ${fmt.idr(BV0 / BF0)} per transaksi beli.` },
        { title:'Hitung perubahannya', text:`100 × (${fmt.idr(BV1 / BF1)} ÷ ${fmt.idr(BV0 / BF0)} − 1) = ${fmt.pct(value)}: transaksi ${value >= 0 ? 'membesar' : 'mengecil'}.` },
        ...readLevels(p, value, fmt.pct(value)),
      ],
    };
  },

  /* FL34 Institutional vs Retail Net: 100 (net of the institutional brokers − net of the retail brokers) / BV(all) */
  FL34: (c, p, t) => {
    const R = c.rows, inst = brokersOf(c, p.inst, () => classBrokers(c, 'Institutional-heavy')), retail = brokersOf(c, p.retail, () => classBrokers(c, 'Retail-heavy'));
    const sI = new Set(inst), sR = new Set(retail);
    if (!sI.size && !sR.size || [...sI].some(b => sR.has(b))) return null;
    const W = intOf(p.window, 20), a = flowWindow(R, t, W);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null), L = X.list(a, t), I = L.filter(s => sI.has(s.code)), Rt = L.filter(s => sR.has(s.code));
    const sum = (C: BS[], m: Col) => C.reduce((x, s) => x + X.b(m, s.i, a, t), 0);
    const NI = sum(I, 'bv') - sum(I, 'sv'), NR = sum(Rt, 'bv') - sum(Rt, 'sv'), TBV = X.all('bv', a, t);
    const combine = (v: Record<string, number>) => { const q = div(v.NI - v.NR, v.TBV); return q === null ? null : 100 * q }, value = combine({ NI, NR, TBV });
    if (value === null) return null;
    const src = (v: any, cls: string) => Array.isArray(v) ? 'pilihan pengguna' : `klasifikasi ${typeof v === 'string' && v.startsWith('class:') ? v.slice(6) : cls}`;
    const names = (xs: string[]) => xs.length ? (xs.length > 12 ? `${xs.slice(0, 12).join(', ')} … (${xs.length} broker)` : xs.join(', ')) : 'tidak ada';
    const big = (C: BS[]) => [...C].sort((x, y) => Math.abs(net(y)) - Math.abs(net(x)) || (x.code < y.code ? -1 : 1)).slice(0, 3).map(s => `${s.code} ${fmt.idr(net(s))}`).join(', ') || '–';
    return {
      output:'value', value, expr:'100 × (NI − NR) ÷ TBV', span:spanOf(c, a, t),
      terms:[{ key:'NI', label:'Net broker institusi', value:NI, unit:'idr' }, { key:'NR', label:'Net broker ritel', value:NR, unit:'idr' },
        { key:'TBV', label:'Total nilai beli semua broker', value:TBV, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Daftar broker', text:`Institusi (${src(p.inst, 'Institutional-heavy')}): ${names(inst)}. Ritel (${src(p.retail, 'Retail-heavy')}): ${names(retail)}.` },
        { title:'Net setiap kelompok', text:`Net = nilai beli − nilai jual selama jendela. Net terbesar: institusi ${big(I)}; ritel ${big(Rt)}. Total nilai beli semua broker (TBV) = ${fmt.idr(TBV)}.`,
          table:{ head:['Kelompok', 'Beli', 'Jual', 'Net'], rows:[['Institusi', fmt.idr(sum(I, 'bv')), fmt.idr(sum(I, 'sv')), fmt.idr(NI)], ['Ritel', fmt.idr(sum(Rt, 'bv')), fmt.idr(sum(Rt, 'sv')), fmt.idr(NR)]] } },
        { title:'Hitung nilainya', text:`100 × (${fmt.idr(NI)} − ${fmt.idr(NR)}) ÷ ${fmt.idr(TBV)} = ${fmt.pct(value)}: ${value > 0 ? 'institusi lebih dominan' : value < 0 ? 'ritel lebih dominan' : 'seimbang'}.` },
      ],
    };
  },

  /* FL35 Net Buy Persistence · Top Buyer: the largest net buyer over the window; 100 x (its net-buy candles) / days */
  FL35: (c, p, t) => {
    const R = c.rows, D = intOf(p.window, 20), a = flowWindow(R, t, D);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null), L = X.list(a, t), top3 = topBy(L, 3, net) as BS[], b = top3[0];
    if (!b) return null;
    let K = 0; const rows: string[][] = [];
    for (let k = a; k <= t; k++) {
      const n = X.b('bv', b.i, k, k) - X.b('sv', b.i, k, k);
      if (n > 0) K++;
      rows.push([c.dates[k], R.has[k] ? fmt.idr(n) : '– (tanpa data)', n > 0 ? 'ya' : 'tidak']);
    }
    const combine = (v: Record<string, number>) => v.D ? 100 * v.K / v.D : null, value = combine({ K, D });
    return {
      output:'value', value, expr:'100 × K ÷ D', span:spanOf(c, a, t),
      terms:[{ key:'K', label:`Candle ${b.code} net beli`, value:K, unit:'count' }, { key:'D', label:'Jumlah candle (days)', value:D, unit:'count' }], combine,
      steps:[
        { title:`Ambil ${D} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Pembeli terbesar', text:`Broker dengan net beli terbesar selama jendela: ${b.code} (${fmt.idr(net(b))}). Ia tetap dipakai untuk seluruh jendela ini.`,
          table:{ head:['Broker', 'Beli', 'Jual', 'Net'], rows:top3.map(brokerRow) } },
        { title:`Net ${b.code} setiap candle`, text:'Candle tanpa data dihitung bukan candle beli.', table:{ head:['Tanggal', 'Net', 'Net beli'], rows:ends(rows, 5) } },
        { title:'Hitung nilainya', text:`${b.code} net beli di ${cnt(K)} dari ${D} candle: 100 × ${cnt(K)} ÷ ${D} = ${pc(value)}.` },
      ],
    };
  },

  /* FL36 Share · Market Value (Buy + Sell): 100 (BV(C) + SV(C)) / (2 TBV(boards)) */
  FL36: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 20), a = flowWindow(R, t, W);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null), C = cohortOf(X, p, a, t);
    const BV = cw(X, C, 'bv', a, t), SV = cw(X, C, 'sv', a, t), TBV = cellsOf(R, a, t, p.boards ?? null, null).all('bv', a, t);
    const combine = (v: Record<string, number>) => { const q = div(v.BV + v.SV, 2 * v.TBV); return q === null ? null : 100 * q }, value = combine({ BV, SV, TBV });
    if (value === null) return null;
    return {
      output:'value', value, expr:'100 × (BV + SV) ÷ (2 × TBV)', span:spanOf(c, a, t),
      terms:[{ key:'BV', label:'Nilai beli kelompok', value:BV, unit:'idr' }, { key:'SV', label:'Nilai jual kelompok', value:SV, unit:'idr' },
        { key:'TBV', label:'Nilai transaksi semua broker (papan terpilih)', value:TBV, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        cohortStep(p, C, a, t, c),
        { title:'Nilai kelompok dan pasar', text:`Kelompok: beli ${fmt.idr(BV)}, jual ${fmt.idr(SV)}. Nilai transaksi semua broker di papan terpilih, asing dan domestik (TBV) = ${fmt.idr(TBV)}; setiap transaksi punya satu sisi beli dan satu sisi jual, jadi pembaginya 2 × TBV.` },
        { title:'Hitung nilainya', text:`100 × (${fmt.idr(BV)} + ${fmt.idr(SV)}) ÷ (2 × ${fmt.idr(TBV)}) = ${pc(value)}.` },
      ],
    };
  },

  /* FL37 Net Flow Percentile · Rupiah: percentile (baseline) of BV(C) - SV(C) over the net window */
  FL37: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 20), bsl = intOf(p.baseline, 250);
    if (flowWindow(R, t, W) === null || t - bsl < 0) return null;
    const X = cellsOf(R, Math.max(0, t - bsl - W + 1), t, p.boards ?? null, p.investors ?? null);
    const at = (k: number) => {
      const a = flowWindow(R, k, W); if (a === null) return null;
      const C = cohortOf(X, p, a, k), BV = cw(X, C, 'bv', a, k), SV = cw(X, C, 'sv', a, k);
      return { a, C, BV, SV, x:BV - SV };
    };
    const r = pctAt(k => at(k)?.x ?? null, k => flowWindow(R, k, W) !== null, t, bsl);
    if (!r) return null;
    const now = at(t)!, value = pctCombine({ LT:r.lt, EQ:r.eq, n:r.n });
    return {
      output:'value', value, expr:'100 × (LT + 0,5 × EQ) ÷ n', span:spanOf(c, Math.max(0, t - bsl - W + 1), t),
      terms:pctTerms(r, `Net kelompok ${W} candle (x)`, 'idr'), combine:pctCombine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[now.a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        cohortStep(p, now.C, now.a, t, c),
        { title:'Hitung x (net Rupiah)', text:`x = nilai beli − nilai jual kelompok = ${fmt.idr(now.BV)} − ${fmt.idr(now.SV)} = ${fmt.idr(r.x)}.` },
        ...pctSteps(c, t, bsl, r, v => fmt.idr(v), value),
        ...readLevels(p, value, fmt.num(value)),
      ],
    };
  },

  /* FL38 Concentration HHI · Net Buy: Σ (n_b / Σ positive n)^2 over the brokers with a positive net */
  FL38: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 20), a = flowWindow(R, t, W);
    if (a === null) return null;
    const pos = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null).list(a, t).filter(s => net(s) > 0);    // broker order
    const all = pos.reduce((x, s) => x + net(s), 0);
    if (!all) return null;
    const value = pos.reduce((x, s) => x + (net(s) / all) ** 2, 0);
    /* the calculator: the 5 largest net buyers one by one, the others as their total (LAIN) and their own HHI (H_LAIN):
       Σ n² = top² + H_LAIN × LAIN² */
    const ranked = [...pos].sort((x, y) => net(y) - net(x) || (x.code < y.code ? -1 : 1)), top = ranked.slice(0, 5), rest = ranked.slice(5);
    const LAIN = rest.reduce((x, s) => x + net(s), 0), H = LAIN ? rest.reduce((x, s) => x + (net(s) / LAIN) ** 2, 0) : 0, keys = top.map(s => s.code);
    const combine = (v: Record<string, number>) => {
      const xs = keys.map(k => v[k]).filter(x => x > 0), r = v.LAIN > 0 ? v.LAIN : 0, T = xs.reduce((s, x) => s + x, 0) + r;
      return T ? (xs.reduce((s, x) => s + x * x, 0) + (v.H_LAIN ?? 0) * r * r) / (T * T) : null;
    };
    const rows = ranked.map(s => [s.code, fmt.idr(net(s)), pc(100 * net(s) / all), fmt.num((net(s) / all) ** 2, 4)]);
    return {
      output:'value', value,
      expr:`(${[...keys.map(k => `(${k})²`), ...(rest.length ? ['H_LAIN × (LAIN)²'] : [])].join(' + ')}) ÷ (${[...keys, ...(rest.length ? ['LAIN'] : [])].join(' + ')})²`,
      span:spanOf(c, a, t),
      terms:[...top.map(s => ({ key:s.code, label:`Net beli ${s.code}`, value:net(s), unit:'idr' as Term['unit'] })),
        ...(rest.length ? [{ key:'LAIN', label:`Net beli ${rest.length} broker lain`, value:LAIN, unit:'idr' as Term['unit'] },
          { key:'H_LAIN', label:`Keterpusatan (HHI) di antara ${rest.length} broker lain`, value:H, unit:'num' as Term['unit'] }] : [])], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Net beli positif', text:`Net = nilai beli − nilai jual; hanya broker dengan net positif (${cnt(pos.length)} broker, jumlah ${fmt.idr(all)}). Bagian = net ÷ jumlah itu.`,
          table:{ head:['Broker', 'Net', 'Bagian', 'Bagian²'], rows:clip(rows) } },
        { title:'Hitung nilainya', text:`Jumlah kuadrat bagian semua broker = ${fmt.num(value, 4)} (0 = tersebar, 1 = satu broker saja).` },
      ],
    };
  },

  /* FL39 Buy VWAP · Rolling · Distance %: 100 (close / (BV(C) / (100 BL(C))) - 1) */
  FL39: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 10), a = flowWindow(R, t, W);
    if (a === null) return null;
    const X = cellsOf(R, a, t, p.boards ?? null, p.investors ?? null), C = cohortOf(X, p, a, t, ['bv', 'sv', 'bl']);
    const BV = cw(X, C, 'bv', a, t), BL = cw(X, C, 'bl', a, t), VW = div(BV, 100 * BL), close = c.close[t];
    if (VW === null || close === null || close === undefined || !VW) return null;
    const combine = (v: Record<string, number>) => v.VW ? 100 * (v.C / v.VW - 1) : null, value = combine({ C:close, VW });
    return {
      output:'value', value, expr:'100 × (C ÷ VW − 1)', span:spanOf(c, a, t),
      terms:[{ key:'C', label:'Harga penutupan', value:close, unit:'price' }, { key:'VW', label:`Harga rata-rata beli kelompok ${W} candle (VWAP)`, value:VW, unit:'price' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        C === null ? { title:'Kelompok broker', text:'Semua broker dihitung.' }
          : { title:'Kelompok broker', text:`${cap(cohortText(p, C))}${(p.scope ?? 'topn') === 'topn' ? ' (dihitung ulang di setiap candle)' : ''}.`,
              table:{ head:['Broker', 'Beli', 'Lot beli', 'Net'], rows:clip(C.map(s => [s.code, fmt.idr(s.bv), lot(s.bl), fmt.idr(net(s))])) } },
        { title:'Harga rata-rata beli (VWAP)', text:`VW = nilai beli ÷ (100 × lot beli) = ${fmt.idr(BV)} ÷ (100 × ${lot(BL)}) = ${px(VW)} per saham.` },
        { title:'Hitung jaraknya', text:`100 × (${px(close)} ÷ ${px(VW)} − 1) = ${fmt.pct(value)}: harga ${value >= 0 ? 'di atas' : 'di bawah'} harga rata-rata beli kelompok.` },
        ...readLevels(p, value, fmt.pct(value)),
      ],
    };
  },
};

/* the parameters as computeFlow reads them: a value left out (or undefined) takes the registry default */
const paramsOf = (id: string, p: FlowParams): FlowParams =>
  ({ ...flowDefaults(id), ...Object.fromEntries(Object.entries(p || {}).filter(([, v]) => v !== undefined)) });

export const FLOW_EXPLAIN_B: Record<string, FlowExplainer> = Object.fromEntries(Object.entries(EX).map(([id, f]) =>
  [id, ((c, p, t, output) => id !== 'FL23' && output !== undefined && output !== 'value' ? null : f(c, paramsOf(id, p), t, output)) as FlowExplainer]));
