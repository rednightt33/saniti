/* EXEC-IND-CARDS IC3: Flow explainers (calc/explain.ts: the interface, the helpers and the rule that the card's number
   is the chart's number). One file per part so they can be written side by side; explainFlowIndex.ts joins them. */
import type { BrokerSums, FlowExplainer, Step, Term } from './explain';
import { againstLevels, brokerRow, filterOf, filterText, flowWindow, fmt, intOf, levelsOf, spanOf, topBy, windowSums, withChange } from './explain';
import type { FlowContext, FlowParams, FlowRows, Series } from './flow';
import { above, atLeast, BOARDS, boardIndex, INVESTORS, investorIndex, lagOf, sideParams, transactionSize } from './flow';

/* ==========================================================================
   FL01-FL19: the chart's sums, re-derived from the rows
   calc/flow.ts adds one broker's rows of one candle in row order (a cell), adds a broker's cells over the window exactly
   and rounds once (bw), adds a group's brokers in the group's order (cw, cc), and for every broker adds the cells of each
   candle in broker order before adding the candles exactly (aw). `book` keeps that order, so a figure of tens of millions
   (rupiah per transaction) comes out to the chart's last digit, not one rounding away.
   ========================================================================== */
const BV = 0, SV = 1, BL = 2, SL = 3, BF = 4, SF = 5, MISS = 6, K7 = 7;
type Num = number | null;

/** a / b, null when b is 0 or a figure is not finite (calc/flow.ts div) */
const div = (a: number, b: number): Num => b !== 0 && Number.isFinite(a) && Number.isFinite(b) ? a / b : null;
const pctOf = (r: Num): Num => r === null ? null : 100 * r;

/* ---- the row filter, as calc/flow.ts grid reads p.boards and p.investors ---- */
interface Filt { okB: boolean[]; okI: boolean[] }
function filt(boards: any, investors: any): Filt {
  const bs = new Set<number>((boards ?? BOARDS).map((b: string) => boardIndex(b)));
  const is = new Set<number>((investors ?? INVESTORS).map((i: string) => investorIndex(i)));
  return { okB:[0, 1, 2].map(x => bs.has(x)), okI:[0, 1].map(x => is.has(x)) };
}
const filterOfP = (p: FlowParams) => filt(p.boards ?? null, p.investors ?? null);
const boardOnlyOf = (p: FlowParams) => filt(p.boards ?? null, null);       // "all investors" denominators
function ftext(f: Filt): string {
  const b = BOARDS.filter((_, k) => f.okB[k]), i = ['asing', 'domestik'].filter((_, k) => f.okI[k]);
  return `${b.length === BOARDS.length ? 'semua papan' : b.length ? 'papan ' + b.join(', ') : 'tanpa papan'}, `
    + `${i.length === 2 ? 'investor asing dan domestik' : i.length ? 'investor ' + i[0] : 'tanpa jenis investor'}`;
}

/** the exact sum of xs, rounded once (compensated, Neumaier) */
function exactSum(xs: ArrayLike<number>): number {
  let s = 0, e = 0;
  for (let k = 0; k < xs.length; k++) {
    const x = xs[k], u = s + x;
    e += Math.abs(s) >= Math.abs(x) ? (s - u) + x : (x - u) + s;
    s = u;
  }
  return s + e;
}
interface Book {
  a: number; L: number;
  per: Map<number, Float64Array>;       // broker -> its sums over a..t [bv, sv, bl, sl, bf, sf, miss] (flow.ts bw)
  all: Float64Array;                    // every broker over a..t (flow.ts aw)
  cand: Float64Array;                   // every broker, per candle: [(k - a) * 7 + m] (flow.ts aw over one candle)
  cells: Map<number, Float64Array>;     // the kept brokers, per candle: [(k - a) * 7 + m] (flow.ts bw over one candle)
}
/** the sums of candles a..t with filter f. bf/sf of a row without both counts are left out and the row counted in
    `miss` (calc/flow.ts build). `keep`: the brokers whose per-candle cells are kept (true = every broker). */
function book(R: FlowRows, a: number, t: number, f: Filt, keep: boolean | Set<number> = false): Book {
  const L = t - a + 1, B = R.brokers.length, start = new Int32Array(B + 1);
  const pass = (k: number) => R.t[k] >= a && R.t[k] <= t && f.okB[R.brd[k]] && f.okI[R.inv[k]];
  for (let k = 0; k < R.n; k++) if (pass(k)) start[R.b[k] + 1]++;
  for (let b = 0; b < B; b++) start[b + 1] += start[b];
  const idx = new Int32Array(start[B]), at = start.slice(0, B);
  for (let k = 0; k < R.n; k++) if (pass(k)) idx[at[R.b[k]]++] = k;          // by broker, row order kept
  const cell = new Float64Array(L * K7), cand = new Float64Array(L * K7), seen = new Uint8Array(L);
  const per = new Map<number, Float64Array>(), cells = new Map<number, Float64Array>();
  for (let b = 0; b < B; b++) {                                              // broker order (aw adds in it)
    if (start[b] === start[b + 1]) continue;
    const js: number[] = [];
    for (let i = start[b]; i < start[b + 1]; i++) {
      const k = idx[i], j = R.t[k] - a, o = j * K7;
      if (!seen[j]) { seen[j] = 1; js.push(j); cell.fill(0, o, o + K7) }
      cell[o + BV] += R.bv[k]; cell[o + SV] += R.sv[k]; cell[o + BL] += R.bl[k]; cell[o + SL] += R.sl[k];
      if (Number.isNaN(R.bf[k]) || Number.isNaN(R.sf[k])) cell[o + MISS] += 1;
      else { cell[o + BF] += R.bf[k]; cell[o + SF] += R.sf[k] }
    }
    js.sort((x, y) => x - y);
    const s = new Float64Array(K7), kept = keep === true || (keep instanceof Set && keep.has(b)) ? new Float64Array(L * K7) : null;
    for (let m = 0; m < K7; m++) s[m] = exactSum(js.map(j => cell[j * K7 + m]));
    for (const j of js) {
      seen[j] = 0;
      for (let m = 0; m < K7; m++) { const x = cell[j * K7 + m]; cand[j * K7 + m] += x; if (kept) kept[j * K7 + m] = x }
    }
    per.set(b, s);
    if (kept) cells.set(b, kept);
  }
  const all = new Float64Array(K7), col = new Float64Array(L);
  for (let m = 0; m < K7; m++) { for (let j = 0; j < L; j++) col[j] = cand[j * K7 + m]; all[m] = exactSum(col) }
  return { a, L, per, all, cand, cells };
}
const ZERO = new Float64Array(K7);

/* ---- the cohort (FORMULAS.md section 2; calc/flow.ts cohort, topOf) ---- */
const RANKS: Record<string, { score: (s: Float64Array) => number; text: string; col: string; f: (v: number) => string }> = {
  net_buy:{ score:s => s[BV] - s[SV], text:'net beli (nilai beli − nilai jual)', col:'Net beli', f:v => fmt.idr(v) },
  gross_buy:{ score:s => s[BV], text:'nilai beli bruto (gross, tanpa dikurangi jual)', col:'Nilai beli bruto', f:v => fmt.idr(v) },
  net_sell:{ score:s => s[SV] - s[BV], text:'net jual (nilai jual − nilai beli)', col:'Net jual', f:v => fmt.idr(v) },
  gross_sell:{ score:s => s[SV], text:'nilai jual bruto (gross, tanpa dikurangi beli)', col:'Nilai jual bruto', f:v => fmt.idr(v) },
  gross_buy_lots:{ score:s => s[BL], text:'lot beli', col:'Lot beli', f:v => lot(v) },
};
/** the n brokers with the highest positive score over the book, ties by code A-Z */
function topIds(R: FlowRows, bk: Book, n: number, score: (s: Float64Array) => number): number[] {
  return [...bk.per.entries()].map(([b, s]) => [b, score(s)] as [number, number]).filter(([, v]) => v > 0)
    .sort((x, y) => y[1] - x[1] || (R.brokers[x[0]] < R.brokers[y[0]] ? -1 : 1)).slice(0, n).map(([b]) => b);
}
interface Cohort { scope: 'topn' | 'selected' | 'all'; ids: number[] | null; N: number; rank: string; want: string[] }
/** the cohort of p over the book's window: null ids = every broker */
function cohortOf(R: FlowRows, p: FlowParams, bk: Book): Cohort {
  const scope = p.scope ?? 'topn', N = intOf(p.top, 3), r = p.rank || 'net_buy', rank = RANKS[r] ? r : 'net_buy';
  if (scope === 'all') return { scope:'all', ids:null, N, rank, want:[] };
  if (scope === 'selected') {
    const want = new Set<string>(p.brokers || []);
    return { scope:'selected', ids:R.brokers.map((b, k) => want.has(b) ? k : -1).filter(k => k >= 0), N, rank, want:[...want] };
  }
  return { scope:'topn', ids:topIds(R, bk, N, RANKS[rank].score), N, rank, want:[] };
}
/** the cohort's sum of measure m over the window (flow.ts cw) */
const cw = (bk: Book, C: Cohort, m: number) => C.ids ? C.ids.reduce((s, b) => s + (bk.per.get(b) ?? ZERO)[m], 0) : bk.all[m];
const sumsOf = (bk: Book, C: Cohort) => Float64Array.from({ length:K7 }, (_, m) => cw(bk, C, m));
/** a row of the cohort in the window lacks the transaction counts (flow.ts cmiss) */
const cmiss = (bk: Book, C: Cohort) => cw(bk, C, MISS) > 0;
/** the cohort's sum of measure m on candle a + j (flow.ts cc) */
const cc = (bk: Book, C: Cohort, m: number, j: number) =>
  C.ids ? C.ids.reduce((s, b) => s + (bk.cells.get(b)?.[j * K7 + m] ?? 0), 0) : bk.cand[j * K7 + m];

/* ---- the card's words and numbers ---- */
const lot = (v: number) => fmt.num(v, Number.isInteger(v) ? 0 : 2);
const cnt = (v: number) => fmt.num(v, 0);
const share = (v: Num) => v === null ? '–' : fmt.num(v, 2) + '%';
/** a ratio (×): four decimals near 1, where two would read as 1,00 */
const times = (v: Num) => v === null ? '–' : fmt.num(v, Math.abs(v - 1) < 0.01 ? 4 : 2) + '×';
const ell = (cols: number, text: string) => [text, ...Array(cols - 1).fill('')];
/** at most `max` rows: the first ones, then how many are left out */
const headRows = (rows: string[][], max = 9) => rows.length <= max ? rows : [...rows.slice(0, max - 1), ell(rows[0].length, `… ${rows.length - max + 1} lainnya`)];
/** at most `max` rows: the last ones, after how many are left out */
const tailRows = (rows: string[][], max = 9) => rows.length <= max ? rows : [ell(rows[0].length, `… ${rows.length - max + 1} sebelumnya`), ...rows.slice(-(max - 1))];

function windowStep(c: FlowContext, a: number, t: number, f: Filt): Step {
  const n = t - a + 1;
  return { title:`Ambil ${n} candle`, text:`${n === 1 ? c.dates[t] : `${c.dates[a]} sampai ${c.dates[t]}`}, ${ftext(f)}.` };
}
/** a column: its head, its figure, and the ranking it repeats (left out of the table when the cohort is ranked by it) */
type Cols = [string, (s: Float64Array) => string, string?][];
/** the cohort with the figures the indicator reads; `rk` = the book the ranking was made on (the window when left out) */
function cohortStep(R: FlowRows, bk: Book, C: Cohort, cols0: Cols, o: { rk?: Book; text?: string; title?: string } = {}): Step {
  const rank = RANKS[C.rank], topn = C.scope === 'topn', rk = o.rk ?? bk;
  const cols = cols0.filter(x => !(topn && rk === bk && x[2] === C.rank));
  const head = ['Broker', ...(topn ? [rk === bk ? rank.col : `${rank.col} (peringkat)`] : []), ...cols.map(x => x[0])];
  const rows = headRows((C.ids ?? []).map(b => {
    const s = bk.per.get(b) ?? ZERO;
    return [R.brokers[b], ...(topn ? [rank.f(rank.score(rk.per.get(b) ?? ZERO))] : []), ...cols.map(x => x[1](s))];
  }));
  const tot = sumsOf(bk, C);
  rows.push([C.ids ? 'Kelompok' : 'Semua broker', ...(topn ? [rank.f(rank.score(sumsOf(rk, C)))] : []), ...cols.map(x => x[1](tot))]);
  const n = C.ids?.length ?? 0;
  const text = o.text ?? (C.scope === 'all' ? 'Semua broker dihitung.'
    : C.scope === 'selected' ? (n ? `Broker pilihan: ${C.ids!.map(b => R.brokers[b]).join(', ')}.`
      : C.want.length ? `Broker pilihan (${C.want.join(', ')}) tidak ada dalam data saham ini: kelompok kosong.` : 'Belum ada broker yang dipilih: kelompok kosong.')
    : `Urutkan broker menurut ${rank.text} selama jendela; ${C.N} teratas yang bernilai positif menjadi kelompok (dihitung ulang di setiap candle).`
      + (n === 0 ? ' Tidak ada broker bernilai positif: kelompok kosong.' : n < C.N ? ` Hanya ${n} broker yang bernilai positif.` : ''));
  const who = C.rank === 'net_sell' || C.rank === 'gross_sell' ? 'penjual' : 'broker';                  // the Sell side's cohort is sellers
  return { title:o.title ?? (C.scope === 'all' ? 'Kelompok: semua broker' : C.scope === 'selected' ? 'Kelompok: broker pilihan' : `Kelompok: ${C.N} ${who} teratas`),
    text, table:{ head, rows } };
}
const levelStep = (p: FlowParams, v: Num, show: (v: number) => string, note = ''): Step[] => {
  const lv = levelsOf(p);
  return v !== null && lv.length ? [{ title:'Baca hasilnya', text:`${show(v)} berada ${againstLevels(v, lv)}.${note ? ' ' + note : ''}` }] : [];
};
const MISS_TEXT = 'Sebagian baris dalam jendela tidak punya jumlah transaksi, jadi nilainya kosong.';

/** the output asked of a Buy/Sell indicator; left out, the side the parameters draw (calc/flow.ts sided) */
const sideOf = (p: FlowParams, out?: string): 'buy' | 'sell' | null => {
  const o = out ?? (p.side === 'sell' ? 'sell' : 'buy');
  return o === 'buy' || o === 'sell' ? o : null;
};
const SIDE = { buy:{ w:'beli', L:'BL', V:'BV', F:'BF', l:BL, v:BV, f:BF }, sell:{ w:'jual', L:'SL', V:'SV', F:'SF', l:SL, v:SV, f:SF } } as const;

/** the window, filter, book and cohort of candle t (null: no value, as calc/flow.ts each/win) */
function prep(c: FlowContext, p: FlowParams, t: number, Wd: number, keep = false) {
  const R = c.rows, W = intOf(p.window, Wd), a = flowWindow(R, t, W);
  if (a === null) return null;
  const f = filterOfP(p), bk = book(R, a, t, f, keep), C = cohortOf(R, p, bk);
  return { R, W, a, f, bk, C };
}

/* ---- the percentile at t (FORMULAS.md section 2; calc/flow.ts percentile): x = the history series, v = the value at t ---- */
function pctAt(x: Series, v: Num, t: number, base: number) {
  let first = -1;
  for (let k = 0; k < x.length; k++) if (x[k] !== null) { first = k; break }
  const out = { value:null as Num, first, lt:0, eq:0, n:0, hist:[] as number[], ready:false };
  if (v === null || first < 0 || t - base < first) return out;
  out.ready = true;
  for (let k = t - base; k < t; k++) {
    const w = x[k]; if (w === null) continue;
    out.n++; out.hist.push(w);
    if (w < v) out.lt++; else if (w === v) out.eq++;
  }
  if (out.n) out.value = 100 * (out.lt + 0.5 * out.eq) / out.n;
  return out;
}
const pctCombine = (v: Record<string, number>) => v.N ? 100 * (v.LT + 0.5 * v.EQ) / v.N : null;
/** the history's spread in words: smallest, middle, largest */
function spread(h: number[], f: (v: number) => string) {
  if (!h.length) return '';
  const s = [...h].sort((x, y) => x - y), mid = s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
  return ` Terkecil ${f(s[0])}, tengah ${f(mid)}, terbesar ${f(s[s.length - 1])}.`;
}

/* ---- HHI of one side over the window (calc/flow.ts hhi): every broker's share of the total, squared, added ---- */
function hhiOf(R: FlowRows, bk: Book, m: number) {
  const tot = bk.all[m], list: { b: number; v: number; x: number }[] = [];
  if (!tot) return { tot, value:null as Num, list, terms:[] as Term[] };
  let s = 0;
  for (const [b, v] of bk.per) { const x = v[m] / tot; s += x * x; if (v[m]) list.push({ b, v:v[m], x }) }   // broker order
  list.sort((p, q) => q.x - p.x || (R.brokers[p.b] < R.brokers[q.b] ? -1 : 1));
  const top = list.slice(0, 3), rest = list.slice(3).reduce((r, e) => r + e.x * e.x, 0);
  const terms: Term[] = [...top.map((e, k) => ({ key:`S${k + 1}`, label:`Porsi broker ${R.brokers[e.b]} (ke-${k + 1} terbesar)`, value:e.x, unit:'num' as const })),
    { key:'SR', label:`Jumlah kuadrat porsi ${list.length - top.length} broker lainnya`, value:rest, unit:'num' }];
  return { tot, value:s as Num, list, terms };
}
/** to-do 5: the HHI part of a cohort: the members' squared shares of every broker's total (calc/flow.ts hhi); all brokers
    (ids null) = hhiOf */
function hhiPart(R: FlowRows, bk: Book, C: Cohort, m: number) {
  if (!C.ids) return { ...hhiOf(R, bk, m), cohort:false };
  const tot = bk.all[m], list: { b: number; v: number; x: number }[] = [];
  if (!tot || !C.ids.length) return { tot, value:null as Num, list, terms:[] as Term[], cohort:true };     // no member: no value
  let s = 0;
  for (const b of C.ids) { const v = (bk.per.get(b) ?? ZERO)[m], x = v / tot; s += x * x; list.push({ b, v, x }) }
  const terms: Term[] = list.map((e, k) => ({ key:`S${k + 1}`, label:`Porsi broker ${R.brokers[e.b]}`, value:e.x, unit:'num' as const }));
  return { tot, value:s as Num, list, terms, cohort:true };
}
const hhiCombine = (v: Record<string, number>) => Object.keys(v).reduce((s, k) => s + (k === 'SR' ? v[k] : v[k] * v[k]), 0);
const hhiExpr = (terms: Term[]) => terms.map(x => x.key === 'SR' ? 'SR' : `${x.key}²`).join(' + ');
function hhiTable(R: FlowRows, h: ReturnType<typeof hhiOf>, w: string, value = false) {
  return { head:['Broker', `${value ? 'Nilai' : 'Lot'} ${w}`, 'Porsi', 'Porsi²'],
    rows:headRows(h.list.map(e => [R.brokers[e.b], value ? fmt.idr(e.v) : lot(e.v), share(100 * e.x), fmt.num(e.x * e.x, 4)])) };
}

/* ---- the frozen cohort of FL18-FL19 (calc/flow.ts anchorAt, frozen) ---- */
function anchorAt(c: FlowContext, anchor: any): number {
  const d = typeof anchor === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(anchor) ? anchor : c.dates[0];
  const i = c.dates.findIndex(x => x >= d);
  return i < 0 ? c.rows.N : i;
}
const lastData = (R: FlowRows) => { for (let t = R.N - 1; t >= 0; t--) if (R.has[t]) return t; return -1 };
function frozenOf(c: FlowContext, p: FlowParams, a: number, f: Filt) {
  const R = c.rows, scope = p.scope ?? 'topn', last = lastData(R);
  if (scope !== 'topn') { const rk = book(R, a, a, f); return { C:cohortOf(R, p, rk), rk, last } }
  if (last < a) return { C:{ scope:'topn', ids:[], N:intOf(p.top, 3), rank:RANKS[p.rank || 'net_buy'] ? p.rank || 'net_buy' : 'net_buy', want:[] } as Cohort, rk:null, last };
  const rk = book(R, a, last, f);
  return { C:cohortOf(R, p, rk), rk, last };
}
const frozenTitle = (C: Cohort) => C.scope === 'topn' ? `Kelompok tetap: ${C.N} broker teratas` : undefined;
function frozenText(c: FlowContext, C: Cohort, a: number, t: number, last: number) {
  if (C.scope !== 'topn') return undefined;
  const n = C.ids!.length;
  return `Urutkan broker menurut ${RANKS[C.rank].text} dari ${c.dates[a]} sampai candle data terakhir`
    + (last >= 0 ? ` (${c.dates[last]})` : '') + `, sekali untuk seluruh grafik; ${C.N} teratas yang bernilai positif menjadi kelompok tetap.`
    + (last > t ? ` Peringkat ini ikut membaca candle sesudah ${c.dates[t]}.` : '')
    + (n === 0 ? ' Tidak ada broker bernilai positif: kelompok kosong.' : n < C.N ? ` Hanya ${n} broker yang bernilai positif.` : '');
}

/* ---- explainers built from one shape: window, cohort, sums, last step ---- */
/** FL01, FL02: lots or rupiah per transaction of the cohort (calc/flow.ts sizeLot, FL02) */
function perTx(kind: 'lot' | 'value'): FlowExplainer {
  return (c, p, t, out) => {
    const o = sideOf(p, out); if (!o) return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, S = SIDE[o], m = kind === 'lot' ? S.l : S.v, kX = kind === 'lot' ? S.L : S.V, kF = S.F;
    const X = cw(bk, C, m), F = cw(bk, C, S.f), gap = cmiss(bk, C), fx = kind === 'lot' ? lot : fmt.idr;
    const combine = (v: Record<string, number>) => div(v[kX], v[kF]);
    const value = gap ? null : combine({ [kX]:X, [kF]:F });
    const show = (v: number) => kind === 'lot' ? `${fmt.num(v, 2)} lot` : fmt.idr(v);
    return {
      output:o, value, expr:`${kX} ÷ ${kF}`, span:spanOf(c, a, t),
      terms:[{ key:kX, label:`${kind === 'lot' ? 'Lot' : 'Nilai'} ${S.w} kelompok`, value:X, unit:kind === 'lot' ? 'lot' : 'idr' },
             { key:kF, label:`Jumlah transaksi ${S.w} kelompok`, value:F, unit:'count' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [[`${kind === 'lot' ? 'Lot' : 'Nilai'} ${S.w}`, s => fx(s[m]), kind === 'value' && o === 'buy' ? 'gross_buy' : undefined], [`Transaksi ${S.w}`, s => cnt(s[S.f])]]),
        { title:'Jumlahkan kelompok', text:`${kind === 'lot' ? 'Lot' : 'Nilai'} ${S.w} ${kX} = ${fx(X)}; transaksi ${S.w} ${kF} = ${cnt(F)}.` },
        { title:'Hitung nilainya', text:gap ? MISS_TEXT : value === null ? `Kelompok tidak punya transaksi ${S.w} (${kF} = 0), jadi tidak ada nilai.`
          : `${fx(X)} ÷ ${cnt(F)} transaksi = ${show(value)} per transaksi ${S.w}.` },
      ],
    };
  };
}
/** FL03, FL04: the cohort's share of every broker's lots or transactions, same filter (calc/flow.ts FL03, FL04) */
function shareOf(kind: 'lot' | 'tx'): FlowExplainer {
  return (c, p, t, out) => {
    const o = sideOf(p, out); if (!o) return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, S = SIDE[o], m = kind === 'lot' ? S.l : S.f, k = kind === 'lot' ? S.L : S.F, kT = 'T' + k;
    const X = cw(bk, C, m), T = bk.all[m], gap = kind === 'tx' && bk.all[MISS] > 0, fx = kind === 'lot' ? lot : cnt;
    const what = kind === 'lot' ? `lot ${S.w}` : `transaksi ${S.w}`;
    const combine = (v: Record<string, number>) => pctOf(div(v[k], v[kT]));
    const value = gap ? null : combine({ [k]:X, [kT]:T });
    return {
      output:o, value, expr:`100 × ${k} ÷ ${kT}`, span:spanOf(c, a, t),
      terms:[{ key:k, label:`${kind === 'lot' ? 'Lot' : 'Transaksi'} ${S.w} kelompok`, value:X, unit:kind === 'lot' ? 'lot' : 'count' },
             { key:kT, label:`${kind === 'lot' ? 'Lot' : 'Transaksi'} ${S.w} semua broker`, value:T, unit:kind === 'lot' ? 'lot' : 'count' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [[kind === 'lot' ? `Lot ${S.w}` : `Transaksi ${S.w}`, s => fx(s[m])]]),
        { title:'Bandingkan dengan semua broker', text:`${what[0].toUpperCase() + what.slice(1)} kelompok ${k} = ${fx(X)}; ${what} semua broker dengan filter yang sama ${kT} = ${fx(T)}.` },
        { title:'Hitung nilainya', text:gap ? MISS_TEXT : value === null ? `Tidak ada ${what} dalam jendela (${kT} = 0), jadi tidak ada nilai.`
          : `100 × ${fx(X)} ÷ ${fx(T)} = ${share(value)} dari seluruh ${what}.` },
      ],
    };
  };
}
/** FL05: the cohort's share of lots over its share of transactions (calc/flow.ts sizeVsMarket) */
const vsMarket: FlowExplainer = (c, p, t, out) => {
  const o = sideOf(p, out); if (!o) return null;
  const x = prep(c, p, t, 1); if (!x) return null;
  const { R, a, f, bk, C } = x, S = SIDE[o], kL = S.L, kF = S.F, kTL = 'T' + S.L, kTF = 'T' + S.F;
  const L = cw(bk, C, S.l), F = cw(bk, C, S.f), TL = bk.all[S.l], TF = bk.all[S.f], gap = cmiss(bk, C) || bk.all[MISS] > 0;
  const combine = (v: Record<string, number>) => { const vs = div(v[kL], v[kTL]), fs = div(v[kF], v[kTF]); return vs === null || fs === null ? null : div(vs, fs) };
  const value = gap ? null : combine({ [kL]:L, [kF]:F, [kTL]:TL, [kTF]:TF });
  const vs = div(L, TL), fs = div(F, TF);
  return {
    output:o, value, expr:`(${kL} ÷ ${kTL}) ÷ (${kF} ÷ ${kTF})`, span:spanOf(c, a, t),
    terms:[{ key:kL, label:`Lot ${S.w} kelompok`, value:L, unit:'lot' }, { key:kTL, label:`Lot ${S.w} semua broker`, value:TL, unit:'lot' },
           { key:kF, label:`Transaksi ${S.w} kelompok`, value:F, unit:'count' }, { key:kTF, label:`Transaksi ${S.w} semua broker`, value:TF, unit:'count' }], combine,
    steps:[
      windowStep(c, a, t, f),
      cohortStep(R, bk, C, [[`Lot ${S.w}`, s => lot(s[S.l])], [`Transaksi ${S.w}`, s => cnt(s[S.f])]]),
      { title:'Porsi lot dan porsi transaksi', text:`Porsi lot = ${lot(L)} ÷ ${lot(TL)} = ${share(pctOf(vs))}; porsi transaksi = ${cnt(F)} ÷ ${cnt(TF)} = ${share(pctOf(fs))} (semua broker dengan filter yang sama).` },
      { title:'Hitung nilainya', text:gap ? MISS_TEXT : value === null ? 'Salah satu porsi kosong atau 0, jadi tidak ada nilai.'
        : `${share(pctOf(vs))} ÷ ${share(pctOf(fs))} = ${times(value)}: transaksi kelompok rata-rata ${value > 1 ? 'lebih besar dari' : value < 1 ? 'lebih kecil dari' : 'sama dengan'} transaksi pasar.` },
      ...levelStep(p, value, times),
    ],
  };
};
/** FL07 and FL11's denominator: the board filter with every investor (default), or the board and investor filter */
const denomBook = (c: FlowContext, p: FlowParams, x: { a: number; bk: Book }, t: number) =>
  p.denom === 'filter' ? x.bk : book(c.rows, x.a, t, boardOnlyOf(p));
const denomText = (p: FlowParams) => p.denom === 'filter' ? 'papan dan jenis investor yang sama' : 'papan yang sama, semua jenis investor';

/* ---- Flow explainers (FL ids of flowRegistry.json) ---- */
/* FL01-FL19 (FL24 is the reference explainer, kept here) */
export const FLOW_EXPLAIN_A: Record<string, FlowExplainer> = {
  /* FL01 Transaction Size · Lot: BL(C) / BF(C), Sell SL / SF (calc/flow.ts sizeLot) */
  FL01:perTx('lot'),
  /* FL02 Transaction Size · Value: BV(C) / BF(C), Sell SV / SF (calc/flow.ts FL02) */
  FL02:perTx('value'),
  /* FL03 Share · Volume: 100 BL(C) / BL(A), A with the same filter */
  FL03:shareOf('lot'),
  /* FL04 Share · Transactions: 100 BF(C) / BF(A); null when any row of the window lacks the counts */
  FL04:shareOf('tx'),
  /* FL05 Transaction Size · vs Market: (BL(C) / BL(A)) / (BF(C) / BF(A)) */
  FL05:vsMarket,

  /* FL06 Transaction Size · Buy/Sell Ratio: (BL(C) / BF(C)) / (SL(C) / SF(C)) */
  FL06:(c, p, t, out) => {
    if (out !== undefined && out !== 'ratio') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, gap = cmiss(bk, C);
    const BLc = cw(bk, C, BL), BFc = cw(bk, C, BF), SLc = cw(bk, C, SL), SFc = cw(bk, C, SF);
    const combine = (v: Record<string, number>) => { const b = div(v.BL, v.BF), s = div(v.SL, v.SF); return b === null || s === null ? null : div(b, s) };
    const value = gap ? null : combine({ BL:BLc, BF:BFc, SL:SLc, SF:SFc }), b = div(BLc, BFc), s = div(SLc, SFc);
    return {
      output:'ratio', value, expr:'(BL ÷ BF) ÷ (SL ÷ SF)', span:spanOf(c, a, t),
      terms:[{ key:'BL', label:'Lot beli kelompok', value:BLc, unit:'lot' }, { key:'BF', label:'Transaksi beli kelompok', value:BFc, unit:'count' },
             { key:'SL', label:'Lot jual kelompok', value:SLc, unit:'lot' }, { key:'SF', label:'Transaksi jual kelompok', value:SFc, unit:'count' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Lot beli', s => lot(s[BL])], ['Trx beli', s => cnt(s[BF])], ['Lot jual', s => lot(s[SL])], ['Trx jual', s => cnt(s[SF])]]),
        { title:'Ukuran transaksi beli dan jual', text:`Beli: ${lot(BLc)} ÷ ${cnt(BFc)} = ${b === null ? '–' : fmt.num(b, 2)} lot per transaksi; jual: ${lot(SLc)} ÷ ${cnt(SFc)} = ${s === null ? '–' : fmt.num(s, 2)} lot per transaksi.` },
        { title:'Hitung nilainya', text:gap ? MISS_TEXT : value === null ? 'Kelompok tidak punya transaksi beli atau jual dalam jendela, jadi tidak ada nilai.'
          : `${fmt.num(b, 2)} ÷ ${fmt.num(s, 2)} = ${times(value)}: transaksi beli kelompok ${value > 1 ? 'lebih besar dari' : value < 1 ? 'lebih kecil dari' : 'sama dengan'} transaksi jualnya.` },
        ...levelStep(p, value, times),
      ],
    };
  },

  /* FL07 Share · Market Volume: 100 BL(C) / BL(A); A: the board filter, all investors (default) or the whole filter */
  FL07:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, d = denomBook(c, p, x, t), X = cw(bk, C, BL), T = d.all[BL];
    const combine = (v: Record<string, number>) => pctOf(div(v.BL, v.TBL)), value = combine({ BL:X, TBL:T });
    return {
      output:'value', value, expr:'100 × BL ÷ TBL', span:spanOf(c, a, t),
      terms:[{ key:'BL', label:'Lot beli kelompok', value:X, unit:'lot' }, { key:'TBL', label:'Lot beli seluruh pasar', value:T, unit:'lot' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Lot beli', s => lot(s[BL])]]),
        { title:'Bandingkan dengan volume pasar', text:`Lot beli kelompok BL = ${lot(X)}; lot beli semua broker di ${denomText(p)} TBL = ${lot(T)}.` },
        { title:'Hitung nilainya', text:value === null ? 'Tidak ada lot beli di pasar dalam jendela (TBL = 0), jadi tidak ada nilai.'
          : `100 × ${lot(X)} ÷ ${lot(T)} = ${share(value)} dari volume beli.` },
      ],
    };
  },

  /* FL08 Transaction Size · Percentile: mid-rank percentile (baseline) of FL01's x = BL(C) / BF(C) (Sell SL / SF).
     The history is the chart's series (flow.ts transactionSize): the value at t is re-derived, the baseline before it is read. */
  FL08:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, side = p.side === 'sell' ? 'sell' : 'buy', S = SIDE[side], base = intOf(p.baseline, 250);
    const Lc = cw(bk, C, S.l), Fc = cw(bk, C, S.f), gap = cmiss(bk, C), xt = gap ? null : div(Lc, Fc);
    const hist = transactionSize(c, p, side), P = pctAt(hist, xt, t, base);
    const value = P.value, from = Math.max(0, t - base);
    const why = xt === null ? (gap ? MISS_TEXT : `Kelompok tidak punya transaksi ${S.w}, jadi ukuran candle ini kosong.`)
      : !P.ready ? `Riwayat belum cukup: perlu ${base} candle sebelum ${c.dates[t]} sejak nilai pertama (${c.dates[P.first]}).`
      : 'Tidak ada nilai pembanding dalam riwayat.';
    return {
      output:'value', value, expr:'100 × (LT + ½ × EQ) ÷ N', span:spanOf(c, a, t),
      terms:[{ key:'LT', label:'Candle riwayat dengan ukuran lebih kecil', value:P.lt, unit:'count' },
             { key:'EQ', label:'Candle riwayat dengan ukuran sama', value:P.eq, unit:'count' },
             { key:'N', label:'Candle riwayat yang punya nilai', value:P.n, unit:'count' }], combine:pctCombine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [[`Lot ${S.w}`, s => lot(s[S.l])], [`Transaksi ${S.w}`, s => cnt(s[S.f])]]),
        { title:'Ukuran transaksi candle ini', text:xt === null ? why : `x = ${lot(Lc)} ÷ ${cnt(Fc)} = ${fmt.num(xt, 2)} lot per transaksi ${S.w}.` },
        ...(xt === null ? [] : [{ title:`Bandingkan dengan ${base} candle sebelumnya`,
          text:!P.ready || !P.n ? why : `${c.dates[from]} sampai ${c.dates[t - 1]}: ${P.n} candle punya nilai (N); ${P.lt} lebih kecil dari x (LT), ${P.eq} sama (EQ).`
            + spread(P.hist, v => fmt.num(v, 2)) }]),
        ...(value === null ? [] : [{ title:'Hitung nilainya', text:`100 × (${P.lt} + ½ × ${P.eq}) ÷ ${P.n} = ${fmt.num(value, 1)}: ukuran candle ini lebih besar dari ${fmt.num(value, 0)}% riwayatnya.` }]),
        ...levelStep(p, value, v => fmt.num(v, 1)),
      ],
    };
  },

  /* FL09 Block Money Candidate: 1 when FL08 Buy >= pct_min, FL05 Buy >= ratio_min, FL07 (board denominator) >= part_min,
     FL11 (board denominator) > flow_min and, if chosen, FL10 >= imb_min; else 0; null when an input is null */
  FL09:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, base = intOf(p.baseline, 250), useImb = !!p.use_imb, d = book(R, a, t, boardOnlyOf(p));
    const BLc = cw(bk, C, BL), BFc = cw(bk, C, BF), SFc = cw(bk, C, SF), BVc = cw(bk, C, BV), SVc = cw(bk, C, SV), gap = cmiss(bk, C);
    const xt = gap ? null : div(BLc, BFc), P = pctAt(transactionSize(c, p, 'buy'), xt, t, base);
    const vs = div(BLc, bk.all[BL]), fs = div(BFc, bk.all[BF]);
    const ratio = gap || bk.all[MISS] > 0 || vs === null || fs === null ? null : div(vs, fs);
    const part = pctOf(div(BLc, d.all[BL])), flow = pctOf(div(BVc - SVc, d.all[BV])), imb = useImb ? (gap ? null : div(BFc - SFc, BFc + SFc)) : null;
    const th = { P:Number(p.pct_min), R:Number(p.ratio_min), S:Number(p.part_min), F:Number(p.flow_min), I:Number(p.imb_min) };
    const keys = ['P', 'R', 'S', 'F', ...(useImb ? ['I'] : [])];
    const pass = (k: string, v: number) => k === 'F' ? above(v, th.F) : atLeast(v, (th as any)[k]);
    const combine = (v: Record<string, number>) => keys.some(k => typeof v[k] !== 'number' || Number.isNaN(v[k])) ? null : keys.every(k => pass(k, v[k])) ? 1 : 0;
    const ins: Record<string, Num> = { P:P.value, R:ratio, S:part, F:flow, I:imb };
    const ok = keys.every(k => ins[k] !== null), value = ok ? combine(ins as Record<string, number>) : null;
    const LABEL: Record<string, [string, string, (v: number) => string]> = {
      P:['Persentil ukuran transaksi beli', '≥', v => fmt.num(v, 1)], R:['Ukuran beli vs pasar', '≥', times],
      S:['Porsi volume beli', '≥', v => share(v)], F:['Net flow / turnover', '>', v => fmt.pct(v)], I:['Imbalance transaksi', '≥', v => fmt.num(v, 2)] };
    const terms: Term[] = keys.filter(k => ins[k] !== null).map(k => ({ key:k, label:LABEL[k][0], value:ins[k]!, unit:k === 'S' || k === 'F' ? 'pct' : 'num' }));
    const failed = keys.filter(k => ins[k] !== null && !pass(k, ins[k]!)).map(k => LABEL[k][0].toLowerCase());
    return {
      output:'value', value, expr:keys.map(k => `${k} ${LABEL[k][1]} ${fmt.num(th[k as keyof typeof th], k === 'I' || k === 'R' ? 2 : 0)}`).join(' dan '), span:spanOf(c, a, t),
      terms, combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Lot beli', s => lot(s[BL])], ['Trx beli', s => cnt(s[BF])], ['Net', s => fmt.idr(s[BV] - s[SV]), 'net_buy']]),
        { title:'Ukuran transaksi dan persentilnya (P)', text:xt === null ? (gap ? MISS_TEXT : 'Kelompok tidak punya transaksi beli, jadi ukurannya kosong.')
          : `x = ${lot(BLc)} ÷ ${cnt(BFc)} = ${fmt.num(xt, 2)} lot per transaksi; dibanding ${P.n} nilai dari ${base} candle sebelumnya: ${P.lt} lebih kecil, ${P.eq} sama`
            + (P.value === null ? `, riwayat belum cukup.` : `, P = 100 × (${P.lt} + ½ × ${P.eq}) ÷ ${P.n} = ${fmt.num(P.value, 1)}.`) },
        { title:'Ukuran vs pasar (R)', text:ratio === null ? 'Kosong: transaksi tidak lengkap atau porsinya 0.'
          : `(${lot(BLc)} ÷ ${lot(bk.all[BL])}) ÷ (${cnt(BFc)} ÷ ${cnt(bk.all[BF])}) = ${times(ratio)}.` },
        { title:'Porsi volume beli (S) dan net flow (F)', text:`Pembagi: ${ftext(boardOnlyOf(p))}. S = 100 × ${lot(BLc)} ÷ ${lot(d.all[BL])} = ${share(part)}; `
          + `F = 100 × (${fmt.idr(BVc)} − ${fmt.idr(SVc)}) ÷ ${fmt.idr(d.all[BV])} = ${fmt.pct(flow)}.`
          + (useImb ? ` Imbalance I = (${cnt(BFc)} − ${cnt(SFc)}) ÷ (${cnt(BFc)} + ${cnt(SFc)}) = ${imb === null ? '–' : fmt.num(imb, 2)}.` : '') },
        { title:'Periksa syaratnya', text:value === null ? 'Ada masukan yang kosong, jadi tidak ada tanda.'
          : value === 1 ? 'Semua syarat terpenuhi: nilai 1, tanda muncul di bawah candle.' : `Tidak terpenuhi: ${failed.join(', ')}. Nilai 0, tanpa tanda.`,
          table:{ head:['Syarat', 'Nilai', 'Batas', 'Terpenuhi'],
            rows:keys.map(k => [`${LABEL[k][0]} (${k})`, ins[k] === null ? '–' : LABEL[k][2](ins[k]!), `${LABEL[k][1]} ${LABEL[k][2](th[k as keyof typeof th])}`,
              ins[k] === null ? '–' : pass(k, ins[k]!) ? 'ya' : 'tidak']) } },
      ],
    };
  },

  /* FL10 Transactions · Buy/Sell Imbalance: (BF(C) − SF(C)) / (BF(C) + SF(C)) */
  FL10:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, gap = cmiss(bk, C), BFc = cw(bk, C, BF), SFc = cw(bk, C, SF);
    const combine = (v: Record<string, number>) => div(v.BF - v.SF, v.BF + v.SF), value = gap ? null : combine({ BF:BFc, SF:SFc });
    return {
      output:'value', value, expr:'(BF − SF) ÷ (BF + SF)', span:spanOf(c, a, t),
      terms:[{ key:'BF', label:'Transaksi beli kelompok', value:BFc, unit:'count' }, { key:'SF', label:'Transaksi jual kelompok', value:SFc, unit:'count' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Trx beli', s => cnt(s[BF])], ['Trx jual', s => cnt(s[SF])]]),
        { title:'Hitung nilainya', text:gap ? MISS_TEXT : value === null ? 'Kelompok tidak punya transaksi dalam jendela, jadi tidak ada nilai.'
          : `(${cnt(BFc)} − ${cnt(SFc)}) ÷ (${cnt(BFc)} + ${cnt(SFc)}) = ${fmt.num(value, 2)}: transaksi ${value > 0 ? 'beli lebih banyak' : value < 0 ? 'jual lebih banyak' : 'beli dan jual sama banyak'}.` },
        ...levelStep(p, value, v => fmt.num(v, 2)),
      ],
    };
  },

  /* FL11 Net Flow / Turnover Ratio: 100 (BV(C) − SV(C)) / TBV; TBV per the denominator option */
  FL11:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, d = denomBook(c, { ...p, denom:'board' }, x, t), BVc = cw(bk, C, BV), SVc = cw(bk, C, SV), T = d.all[BV];
    const combine = (v: Record<string, number>) => pctOf(div(v.BV - v.SV, v.TBV)), value = combine({ BV:BVc, SV:SVc, TBV:T });
    return {
      output:'value', value, expr:'100 × (BV − SV) ÷ TBV', span:spanOf(c, a, t),
      terms:[{ key:'BV', label:'Nilai beli kelompok', value:BVc, unit:'idr' }, { key:'SV', label:'Nilai jual kelompok', value:SVc, unit:'idr' },
             { key:'TBV', label:'Nilai beli bruto seluruh pasar (semua investor)', value:T, unit:'idr' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Beli', s => fmt.idr(s[BV]), 'gross_buy'], ['Jual', s => fmt.idr(s[SV])], ['Net', s => fmt.idr(s[BV] - s[SV]), 'net_buy']]),
        { title:'Bandingkan dengan nilai transaksi', text:`Net kelompok BV − SV = ${fmt.idr(BVc - SVc)}; nilai beli semua broker di ${denomText({ denom:'board' })} TBV = ${fmt.idr(T)}.` },
        { title:'Hitung nilainya', text:value === null ? 'Tidak ada transaksi dalam jendela (TBV = 0), jadi tidak ada nilai.'
          : `100 × (${fmt.idr(BVc)} − ${fmt.idr(SVc)}) ÷ ${fmt.idr(T)} = ${fmt.pct(value)}.` },
      ],
    };
  },

  /* FL12 Net Buy Persistence · Cohort: 100 × (candles in the window where the cohort's own net > 0) / W; the cohort is
     ranked over the whole window */
  FL12:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 5, true); if (!x) return null;
    const { R, W, a, f, bk, C } = x, rows: string[][] = [];
    let H = 0;
    for (let k = a; k <= t; k++) {
      const j = k - a, n = cc(bk, C, BV, j) - cc(bk, C, SV, j);
      if (n > 0) H++;
      rows.push([c.dates[k], R.has[k] ? fmt.idr(n) : 'tanpa data', n > 0 ? 'ya' : 'tidak']);
    }
    const combine = (v: Record<string, number>) => v.W ? 100 * v.H / v.W : null, value = combine({ H, W });
    return {
      output:'value', value, expr:'100 × H ÷ W', span:spanOf(c, a, t),
      terms:[{ key:'H', label:'Candle dengan net beli kelompok', value:H, unit:'count' }, { key:'W', label:'Candle dalam jendela', value:W, unit:'count' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Net', s => fmt.idr(s[BV] - s[SV]), 'net_buy']]),
        { title:'Net kelompok per candle', text:'Candle dihitung bila net (nilai beli − nilai jual) kelompok pada candle itu di atas 0; candle tanpa transaksi kelompok tidak dihitung.',
          table:{ head:['Tanggal', 'Net kelompok', 'Dihitung'], rows:tailRows(rows) } },
        { title:'Hitung nilainya', text:`100 × ${H} ÷ ${W} = ${share(value)} dari candle dalam jendela.` },
      ],
    };
  },

  /* FL13 Concentration HHI · Gross: Σ_b (BL(b) / BL(A))², Sell with SL; A with the filter */
  FL13:(c, p, t, out) => {
    const o = sideOf(p, out); if (!o) return null;
    const x = prep(c, p, t, 1); if (!x) return null;
    const { R, a, f, bk, C } = x, S = SIDE[o], money = p.unit === 'value', m = money ? S.v : S.l, h = hhiPart(R, bk, C, m), value = h.value;
    const what = money ? `nilai ${S.w}` : `lot ${S.w}`, tot = money ? fmt.idr(h.tot) : `${lot(h.tot)} lot`;
    return {
      output:o, value, expr:h.terms.length ? hhiExpr(h.terms) : 'Σ porsi²', span:spanOf(c, a, t), terms:h.terms, combine:hhiCombine,
      steps:[
        windowStep(c, a, t, f),
        ...(h.cohort ? [cohortStep(R, bk, C, [[money ? `Nilai ${S.w}` : `Lot ${S.w}`, s => money ? fmt.idr(s[m]) : lot(s[m])]])] : []),
        { title:`Porsi ${what} setiap broker${h.cohort ? ' kelompok' : ''}`, text:`Porsi = ${what} bruto broker ÷ ${what} bruto semua broker (${tot}).${h.cohort && C.scope === 'topn' ? ` Rank (net atau bruto, selalu dalam Rupiah) hanya memilih siapa yang masuk kelompok; yang diukur tetap ${what} bruto.` : ''}`, ...(h.list.length ? { table:hhiTable(R, h, S.w, money) } : {}) },
        { title:'Hitung nilainya', text:value === null ? `Tidak ada ${what} dalam jendela, jadi tidak ada nilai.`
          : h.cohort ? `Jumlah porsi² ${h.list.length} broker kelompok = ${fmt.num(value, 4)} (bagian kelompok dari keterpusatan semua broker).`
          : `Jumlah porsi² semua ${h.list.length} broker = ${fmt.num(value, 4)}, setara ${fmt.num(1 / value, 1)} broker berporsi sama (1 = satu broker menguasai semua).` },
      ],
    };
  },

  /* FL14 Concentration HHI · Buy − Sell: FL13 Buy of the top buyers − FL13 Sell of the top sellers (to-do 5, K2) */
  FL14:(c, p, t, out) => {
    if (out !== undefined && out !== 'asym') return null;
    const R = c.rows, W = intOf(p.window, 1), a = flowWindow(R, t, W); if (a === null) return null;
    const f = filterOfP(p), bk = book(R, a, t, f), money = p.unit === 'value';
    const Cb = cohortOf(R, sideParams(p, 'buy'), bk), Cs = cohortOf(R, sideParams(p, 'sell'), bk);
    const hb = hhiPart(R, bk, Cb, money ? BV : BL), hs = hhiPart(R, bk, Cs, money ? SV : SL);
    const combine = (v: Record<string, number>) => v.HB - v.HS;
    const value = hb.value === null || hs.value === null ? null : combine({ HB:hb.value, HS:hs.value });
    const top = (h: ReturnType<typeof hhiOf>) => h.list.slice(0, 3).map(e => `${R.brokers[e.b]} ${share(100 * e.x)}`).join(', ');
    const w = (side: string) => money ? `nilai ${side}` : `lot ${side}`, who = (h: { cohort: boolean }, k: string) => h.cohort ? `${k} kelompok` : 'semua broker';
    return {
      output:'asym', value, expr:'HB − HS', span:spanOf(c, a, t),
      terms:[...(hb.value === null ? [] : [{ key:'HB', label:`HHI ${w('beli')}`, value:hb.value, unit:'num' as const }]),
             ...(hs.value === null ? [] : [{ key:'HS', label:`HHI ${w('jual')}`, value:hs.value, unit:'num' as const }])], combine,
      steps:[
        windowStep(c, a, t, f),
        ...(hb.cohort ? [cohortStep(R, bk, Cb, [[money ? 'Nilai beli' : 'Lot beli', s => money ? fmt.idr(s[BV]) : lot(s[BL])]], { title:'Kelompok sisi beli' })] : []),
        { title:'Keterpusatan sisi beli (HB)', text:hb.value === null ? `Tidak ada ${w('beli')} dalam jendela.`
          : `Jumlah porsi² ${w('beli')} ${who(hb, 'pembeli')} (${hb.list.length} broker) = ${fmt.num(hb.value, 4)}. Terbesar: ${top(hb)}.`, ...(hb.list.length ? { table:hhiTable(R, hb, 'beli', money) } : {}) },
        ...(hs.cohort ? [cohortStep(R, bk, Cs, [[money ? 'Nilai jual' : 'Lot jual', s => money ? fmt.idr(s[SV]) : lot(s[SL])]], { title:'Kelompok sisi jual' })] : []),
        { title:'Keterpusatan sisi jual (HS)', text:hs.value === null ? `Tidak ada ${w('jual')} dalam jendela.`
          : `Jumlah porsi² ${w('jual')} ${who(hs, 'penjual')} (${hs.list.length} broker) = ${fmt.num(hs.value, 4)}. Terbesar: ${top(hs)}.`, ...(hs.list.length ? { table:hhiTable(R, hs, 'jual', money) } : {}) },
        { title:'Hitung nilainya', text:value === null ? 'Salah satu sisi kosong, jadi tidak ada nilai.'
          : `${fmt.num(hb.value, 4)} − ${fmt.num(hs.value, 4)} = ${fmt.num(value, 4)}: ${value > 0 ? 'pembelian lebih terpusat dari penjualan' : value < 0 ? 'penjualan lebih terpusat dari pembelian' : 'sama terpusat'}.` },
        ...levelStep(p, value, v => fmt.num(v, 4)),
      ],
    };
  },

  /* FL15 Concentration Top-N · Gross Buy: 100 × (the N largest BL(b)) / BL(A), or in Rupiah (to-do 6); U3: minus N/k */
  FL15:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const R = c.rows, W = intOf(p.window, 1), a = flowWindow(R, t, W); if (a === null) return null;
    const money = p.unit === 'value', m = money ? BV : BL, show = (v: number) => money ? fmt.idr(v) : lot(v), w = money ? 'Nilai beli' : 'Lot beli';
    const f = filterOfP(p), bk = book(R, a, t, f), N = intOf(p.top, 3), top = topIds(R, bk, N, (money ? RANKS.gross_buy : RANKS.gross_buy_lots).score);
    const X = top.reduce((s, b) => s + bk.per.get(b)![m], 0), T = bk.all[m];
    let K = 0; for (const [, v] of bk.per) if (v[m] > 0) K++;
    const even = !!p.even, combine = (v: Record<string, number>) => { const x = pctOf(div(v.XN, v.TX)); return x === null ? null : x - (even && v.K ? 100 * v.NE / v.K : 0) };
    const value = combine({ XN:X, TX:T, NE:top.length, K }), raw = pctOf(div(X, T));
    return {
      output:'value', value, expr:even ? '100 × XN ÷ TX − 100 × NE ÷ K' : '100 × XN ÷ TX', span:spanOf(c, a, t),
      terms:[{ key:'XN', label:`${w} ${N} pembeli terbesar`, value:X, unit:money ? 'idr' : 'lot' }, { key:'TX', label:`${w} semua broker`, value:T, unit:money ? 'idr' : 'lot' },
        ...(even ? [{ key:'NE', label:'Broker yang diambil', value:top.length, unit:'count' as const }, { key:'K', label:'Broker yang membeli', value:K, unit:'count' as const }] : [])], combine,
      steps:[
        windowStep(c, a, t, f),
        { title:`Ambil ${N} pembeli terbesar`, text:`Urutkan broker menurut ${w.toLowerCase()} selama jendela dan ambil ${N} teratas.${top.length < N ? ` Hanya ${top.length} broker yang membeli.` : ''}`,
          table:{ head:['Broker', w, 'Porsi'], rows:[...headRows(top.map(b => [R.brokers[b], show(bk.per.get(b)![m]), share(pctOf(div(bk.per.get(b)![m], T)))])), [`Jumlah ${top.length} broker (XN)`, show(X), share(raw)]] } },
        { title:'Hitung porsinya', text:raw === null ? `Tidak ada ${w.toLowerCase()} dalam jendela (TX = 0), jadi tidak ada nilai.`
          : `100 × ${show(X)} ÷ ${show(T)} = ${share(raw)} pembelian dikuasai ${top.length} broker.` },
        ...(even && raw !== null ? [{ title:'Kurangi bagian merata', text:`${K} broker membeli; bila sama rata, ${top.length} broker memegang 100 × ${top.length} ÷ ${K} = ${share(K ? 100 * top.length / K : 0)}. ${share(raw)} − ${share(K ? 100 * top.length / K : 0)} = ${fmt.num(value, 2)} poin di atas bagian merata.` }] : []),
      ],
    };
  },

  /* FL16 Concentration Top-N · Net Buy: n_b = BV(b) − SV(b) (or BL − SL, to-do 6); 100 × (the N largest positive n_b) /
     (all positive n_b); U3: minus N/k */
  FL16:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const R = c.rows, W = intOf(p.window, 1), a = flowWindow(R, t, W); if (a === null) return null;
    const lots = p.unit === 'lot', show = (v: number) => lots ? lot(v) : fmt.idr(v), w = lots ? 'Net lot beli' : 'Net beli';
    const f = filterOfP(p), bk = book(R, a, t, f), N = intOf(p.top, 3), pos: { b: number; n: number }[] = [];
    for (const [b, s] of bk.per) { const n = lots ? s[BL] - s[SL] : s[BV] - s[SV]; if (n > 0) pos.push({ b, n }) }
    pos.sort((x, y) => y.n - x.n || (R.brokers[x.b] < R.brokers[y.b] ? -1 : 1));
    const taken = pos.slice(0, N), NP = pos.reduce((s, e) => s + e.n, 0), NT = taken.reduce((s, e) => s + e.n, 0), even = !!p.even;
    const combine = (v: Record<string, number>) => { const x = pctOf(div(v.NT, v.NP)); return x === null ? null : x - (even && v.K ? 100 * v.NE / v.K : 0) };
    const value = combine({ NT, NP, NE:taken.length, K:pos.length }), raw = pctOf(div(NT, NP));
    return {
      output:'value', value, expr:even ? '100 × NT ÷ NP − 100 × NE ÷ K' : '100 × NT ÷ NP', span:spanOf(c, a, t),
      terms:[{ key:'NT', label:`${w} ${N} pembeli bersih terbesar`, value:NT, unit:lots ? 'lot' : 'idr' }, { key:'NP', label:`${w} semua pembeli bersih`, value:NP, unit:lots ? 'lot' : 'idr' },
        ...(even ? [{ key:'NE', label:'Broker yang diambil', value:taken.length, unit:'count' as const }, { key:'K', label:'Pembeli bersih', value:pos.length, unit:'count' as const }] : [])], combine,
      steps:[
        windowStep(c, a, t, f),
        { title:`${w} setiap broker`, text:`Net = ${lots ? 'lot beli − lot jual' : 'nilai beli − nilai jual'} selama jendela. ${pos.length} broker bernilai positif, jumlahnya NP = ${show(NP)}; ambil ${N} terbesar (NT).`,
          table:{ head:['Broker', w, 'Porsi'], rows:[...headRows(taken.map(e => [R.brokers[e.b], show(e.n), share(pctOf(div(e.n, NP)))])), ['NT', show(NT), share(raw)]] } },
        { title:'Hitung porsinya', text:raw === null ? 'Tidak ada broker dengan net beli positif, jadi tidak ada nilai.'
          : `100 × ${show(NT)} ÷ ${show(NP)} = ${share(raw)} pembelian bersih berasal dari ${taken.length} broker.` },
        ...(even && raw !== null ? [{ title:'Kurangi bagian merata', text:`${pos.length} pembeli bersih; bila sama rata, ${taken.length} broker memegang 100 × ${taken.length} ÷ ${pos.length} = ${share(100 * taken.length / pos.length)}. ${share(raw)} − ${share(100 * taken.length / pos.length)} = ${fmt.num(value, 2)} poin di atas bagian merata.` }] : []),
      ],
    };
  },

  /* FL17 Buy VWAP · Rolling: BV(C) / (100 BL(C)), IDR per share */
  FL17:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const x = prep(c, p, t, 20); if (!x) return null;
    const { R, a, f, bk, C } = x, BVc = cw(bk, C, BV), BLc = cw(bk, C, BL);
    const combine = (v: Record<string, number>) => div(v.BV, 100 * v.BL), value = combine({ BV:BVc, BL:BLc });
    const close = c.close[t];
    return {
      output:'value', value, expr:'BV ÷ (100 × BL)', span:spanOf(c, a, t),
      terms:[{ key:'BV', label:'Nilai beli kelompok', value:BVc, unit:'idr' }, { key:'BL', label:'Lot beli kelompok', value:BLc, unit:'lot' }], combine,
      steps:[
        windowStep(c, a, t, f),
        cohortStep(R, bk, C, [['Nilai beli', s => fmt.idr(s[BV]), 'gross_buy'], ['Lot beli', s => lot(s[BL])], ['Harga rata-rata', s => { const v = div(s[BV], 100 * s[BL]); return v === null ? '–' : fmt.num(v, 2) }]]),
        { title:'Hitung nilainya', text:value === null ? 'Kelompok tidak membeli dalam jendela (BL = 0), jadi tidak ada nilai.'
          : `${fmt.idr(BVc)} ÷ (100 × ${lot(BLc)} lot) = Rp ${fmt.num(value, 2)} per lembar` + (close !== null && close !== undefined ? `; harga penutupan ${fmt.num(close, 0)}.` : '.') },
      ],
    };
  },

  /* FL18 Buy VWAP · Anchored: the frozen cohort (ranked once, anchor to the last candle with data); from the anchor to t:
     BV(C) / (100 BL(C)) */
  FL18:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const R = c.rows, a = anchorAt(c, p.anchor);
    if (t < a || t >= R.N || !R.has[t]) return null;
    const f = filterOfP(p), { C, rk, last } = frozenOf(c, p, a, f), bk = book(R, a, t, f), BVc = cw(bk, C, BV), BLc = cw(bk, C, BL);
    const combine = (v: Record<string, number>) => div(v.BV, 100 * v.BL), value = combine({ BV:BVc, BL:BLc });
    return {
      output:'value', value, expr:'BV ÷ (100 × BL)', span:spanOf(c, a, t),
      terms:[{ key:'BV', label:'Nilai beli kelompok sejak jangkar', value:BVc, unit:'idr' }, { key:'BL', label:'Lot beli kelompok sejak jangkar', value:BLc, unit:'lot' }], combine,
      steps:[
        { title:'Mulai dari jangkar', text:`Jangkar ${c.dates[a]}; jumlahkan ${t - a + 1} candle sampai ${c.dates[t]}, ${ftext(f)}.` },
        cohortStep(R, bk, C, [['Nilai beli', s => fmt.idr(s[BV])], ['Lot beli', s => lot(s[BL])]], { rk:rk ?? undefined, text:frozenText(c, C, a, t, last), title:frozenTitle(C) }),
        { title:'Hitung nilainya', text:value === null ? 'Kelompok belum membeli sejak jangkar (BL = 0), jadi tidak ada nilai.'
          : `${fmt.idr(BVc)} ÷ (100 × ${lot(BLc)} lot) = Rp ${fmt.num(value, 2)} per lembar.` },
      ],
    };
  },

  /* FL19 Implied Cost · Anchored: the frozen cohort's modelled inventory from the anchor (Q, K start at 0). Per candle
     q = BL_k − SL_k: q > 0 buys at BV_k / BL_k (Q <= 0 restarts the cost at max(Q + q, 0) lots); q < 0 with Q > 0 sells
     at cost (K × max(Q + q, 0) / Q); Q += q. Value K / (100 Q) while Q > 0 */
  FL19:(c, p, t, out) => {
    if (out !== undefined && out !== 'value') return null;
    const R = c.rows, a = anchorAt(c, p.anchor);
    if (t < a || t >= R.N || !R.has[t]) return null;
    const f = filterOfP(p), { C, rk, last } = frozenOf(c, p, a, f), bk = book(R, a, t, f, C.ids ? new Set(C.ids) : false);
    let Q = 0, K = 0;
    const rows: string[][] = [];
    for (let k = a; k <= t; k++) {
      if (!R.has[k]) continue;
      const j = k - a, bl = cc(bk, C, BL, j), sl = cc(bk, C, SL, j), bv = cc(bk, C, BV, j), q = bl - sl;
      let price: Num = null;
      if (q > 0) { price = bv / bl; K = Q <= 0 ? Math.max(Q + q, 0) * price : K + q * price }
      else if (q < 0 && Q > 0) K = K * Math.max(Q + q, 0) / Q;
      Q += q;
      rows.push([c.dates[k], lot(q), price === null ? '–' : fmt.num(price / 100, 2), lot(Q), Q > 0 ? fmt.num(K / (100 * Q), 2) : '–']);
    }
    const combine = (v: Record<string, number>) => v.Q > 0 ? v.K / (100 * v.Q) : null, value = combine({ K, Q });
    return {
      output:'value', value, expr:'K ÷ (100 × Q)', span:spanOf(c, a, t),
      terms:[{ key:'K', label:'Biaya persediaan kelompok', value:K, unit:'idr' }, { key:'Q', label:'Persediaan kelompok (lot)', value:Q, unit:'lot' }], combine,
      steps:[
        { title:'Mulai dari jangkar', text:`Jangkar ${c.dates[a]} dengan persediaan awal 0; ikuti ${t - a + 1} candle sampai ${c.dates[t]}, ${ftext(f)}.` },
        cohortStep(R, bk, C, [['Lot beli', s => lot(s[BL])], ['Lot jual', s => lot(s[SL])]], { rk:rk ?? undefined, text:frozenText(c, C, a, t, last), title:frozenTitle(C) }),
        { title:'Ikuti persediaan per candle', text:'q = lot beli − lot jual kelompok. Bila q > 0, biaya K bertambah q × harga beli rata-rata candle itu (bila persediaan Q ≤ 0, biaya mulai lagi dari sisa lot yang positif). '
          + 'Bila q < 0 dan Q > 0, K berkurang sebanding lot yang dijual. Lalu Q bertambah q.',
          table:{ head:['Tanggal', 'q (lot)', 'Harga beli', 'Q (lot)', 'Harga pokok'], rows:tailRows(rows) } },
        { title:'Hitung nilainya', text:value === null ? `Persediaan kelompok Q = ${lot(Q)} lot (0 atau kurang), jadi tidak ada harga pokok.`
          : `${fmt.idr(K)} ÷ (100 × ${lot(Q)} lot) = Rp ${fmt.num(value, 2)} per lembar.` },
      ],
    };
  },

  /* FL24 Bandar Balance · %: 100 (NB + NS) / TBV(filter) (calc/flow.ts balancePct, bandar) */
  FL24: (c, p, t) => {
    const R = c.rows, W = intOf(p.window, 10), N = intOf(p.top, 3), a = flowWindow(R, t, W);
    if (a === null) return null;
    const { brokers, total } = windowSums(R, a, t, filterOf(p, 'boards'), filterOf(p, 'investors'));
    const net = (s: BrokerSums) => s.bv - s.sv;
    const buyers = topBy(brokers, N, net), sellers = topBy(brokers, N, s => -net(s));
    const NB = buyers.reduce((x, s) => x + net(s), 0), NS = sellers.reduce((x, s) => x + net(s), 0), TBV = total.bv;
    const combine = (v: Record<string, number>) => v.TBV ? 100 * (v.NB + v.NS) / v.TBV : null;
    const value = combine({ NB, NS, TBV }), lv = levelsOf(p);
    return {
      output:'value', value, expr:'100 × (NB + NS) ÷ TBV', span:spanOf(c, a, t),
      terms:[{ key:'NB', label:`Net beli ${N} pembeli terbesar`, value:NB, unit:'idr' },
             { key:'NS', label:`Net jual ${N} penjual terbesar`, value:NS, unit:'idr' },
             { key:'TBV', label:'Total nilai beli semua broker', value:TBV, unit:'idr' }], combine,
      steps:[
        { title:`Ambil ${W} candle`, text:`${c.dates[a]} sampai ${c.dates[t]}, ${filterText(p)}.` },
        { title:'Hitung net setiap broker', text:`Net = nilai beli − nilai jual selama jendela. Ambil ${N} net beli terbesar (NB) dan ${N} net jual terbesar (NS).`,
          table:{ head:['Broker', 'Beli', 'Jual', 'Net'],
            rows:[...buyers.map(brokerRow), ['NB', '', '', fmt.idr(NB)], ...sellers.map(brokerRow), ['NS', '', '', fmt.idr(NS)]] } },
        { title:'Bandingkan dengan seluruh transaksi', text:`Total nilai beli semua broker (TBV) dalam jendela: ${fmt.idr(TBV)}.` },
        { title:'Hitung nilainya', text:`100 × (${fmt.idr(NB)} + ${fmt.idr(NS)}) ÷ ${fmt.idr(TBV)} = ${fmt.pct(value)}.` },
        ...(value !== null && lv.length ? [{ title:'Baca hasilnya', text:`${fmt.pct(value)} berada ${againstLevels(value, lv)}.` }] : []),
      ],
    };
  },
};

/* EXEC-TERMINAL-IND-EDIT K1/R1 (calc/flow.ts sideParams): the Buy line's cohort is the top buyers, the Sell line's the top
   sellers; the card ranks the cohort of the line it explains */
for (const id of ['FL01', 'FL02', 'FL03', 'FL04', 'FL05', 'FL08', 'FL13']) {
  const f = FLOW_EXPLAIN_A[id];
  FLOW_EXPLAIN_A[id] = (c, p, t, out) => {
    const side = id === 'FL08' ? (p.side === 'sell' ? 'sell' : 'buy') : sideOf(p, out);      // FL08 draws one line, its Side
    return f(c, side ? sideParams(p, side) : p, t, out);
  };
}
FLOW_EXPLAIN_A.FL11 = withChange(FLOW_EXPLAIN_A.FL11, lagOf);
