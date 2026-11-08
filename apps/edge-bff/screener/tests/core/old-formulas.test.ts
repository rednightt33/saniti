/* EXEC-SCREENER-FLOW-CANDLES P5b (verification/screener/P5_FLOW.md section 3; EXEC.md "Rumus lama", user 2026-11-07):
   the old Phase 2 flow formulas the user listed, rebuilt on the Terminal's flow indicators and the universal operators,
   and the eight bandar presets rewritten on them, give the same pass or fail as the old definitions on the same rows.
   Each old formula is written here as a reference function from its definition (verification/screener/AUDIT.md 16.5,
   FLOW_MAP.md), on the stock's own sessions (G2: its price bars inside the broker window, user 2026-11-07; the old D12
   market-session calendar is superseded), and compared with the screener's verdict at every session where the old
   formula is defined (the screener's own evaluation, condition.ts evaluateAt, at that session). The presets read the
   regular board (G1, user 2026-11-07: "Opsi P8B berubah, OK"), so their legs are compared with the old formula on the
   regular board; the other old formulas, and Big Acc once more, on every board on both sides. Rows: three stocks with
   regimes (a few large buyers or sellers, runs of foreign buying or selling, trade-count spikes, a broker that
   accumulates) at prices near the stock's close, every session with broker data. */
import { describe, expect, it } from 'vitest';
import type { Test } from '../../src/core/contract.ts';
import { METRICS_CATALOG, PRESETS } from '../../src/core/catalog.ts';
import { bindCondition } from '../../src/core/condition.ts';
import type { BoundCondition } from '../../src/core/condition.ts';
import { availabilityMap, presetAvailability, validateDefinition, validateTest } from '../../src/core/validate.ts';
import { BROKERS, E, FLOW_CTX, INVESTORS, PRICE_BARS, WINDOW, stock, terminal } from './flow-fixture.ts';
import type { Row, Stock } from './flow-fixture.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rng, rowOf, synth, vctx } from './helpers.ts';

/* ---- the rows --------------------------------------------------------------------------------------------------- */

interface Plan { bandar: 1 | -1 | 0; foreign: 1 | -1 | 0; spike: boolean; yp: number }
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
/** The boards as the rows name them: the regular board alone (the presets, G1) and every board. */
const REG = ['Regular'], ALL = ['Regular', 'Nego', 'Tunai'];
const BANDAR = ['AK', 'BK', 'CC'];
/** Broker rows of one stock on every window date: 8 to 12 of the 14 brokers plus the three bandar brokers and YP, both
    investor types, the Regular board and now and then Nego or Tunai, at prices within 1% of the stock's close; on the
    Regular board the bandar brokers buy (bandar 1) or sell (-1) a block, foreign rows lean to buying (foreign 1) or
    selling (-1), YP buys `yp` lots, and on a spike day the transaction counts are six times larger. Every session then
    balances on each board as the market does (every trade has a buyer and a seller on its board: the brokers' buy value
    and lots equal their sell value and lots, ERRORS M154): broker XL's domestic row of that board takes the other side
    of the difference. */
function regimeRows(seed: number, ticker: string, barSeed: number, plan: (k: number) => Plan): Row[] {
  const t = synth(ticker, barSeed, PRICE_BARS, '2026-07-01'), close = new Map(t.dates.map((d, k) => [d, t.bars.C[k] as number]));
  const r = rng(seed), out: Row[] = [];
  WINDOW.forEach((d, k) => {
    const c = close.get(d)!, p = plan(k), n = 8 + Math.floor(r() * 5);
    const picked = new Set([...[...BROKERS].sort(() => r() - 0.5).slice(0, n), ...BANDAR, 'YP']);
    for (const b of picked) for (const i of INVESTORS) {
      const boards = r() < 0.2 ? ['Regular', 'Nego'] : r() < 0.06 ? ['Regular', 'Tunai'] : ['Regular'];
      for (const m of boards) {
        let bl = r() < 0.2 ? Math.round(r() * 3e5) / 100 : Math.round(r() * 3000), sl = r() < 0.2 ? Math.round(r() * 3e5) / 100 : Math.round(r() * 3000);
        if (m === 'Regular') {
          if (BANDAR.includes(b) && p.bandar) { const x = 5000 + Math.round(r() * 4000); if (p.bandar > 0) bl += x; else sl += x }
          if (i === 'Foreign' && p.foreign) { if (p.foreign > 0) bl += 2500; else sl += 2500 }
          if (b === 'YP' && i === 'Domestic') bl += p.yp;
        }
        const f = p.spike ? 6 : 1;
        out.push({ d, b, i, m, bv: Math.round(bl * 100 * c * (1 + 0.02 * (r() - 0.5))), sv: Math.round(sl * 100 * c * (1 + 0.02 * (r() - 0.5))), bl, sl,
          bf: f * (1 + Math.floor(r() * 150)), sf: f * (1 + Math.floor(r() * 150)) });
      }
    }
    for (const m of ALL) {
      const day = out.filter(x => x.d === d && x.m === m), dv = sum(day.map(x => x.bv - x.sv)), dl = sum(day.map(x => x.bl - x.sl));
      if (!day.length) continue;
      let mm = day.find(x => x.b === 'XL' && x.i === 'Domestic');
      if (!mm) out.push(mm = { d, b: 'XL', i: 'Domestic', m, bv: 0, sv: 0, bl: 0, sl: 0, bf: 1, sf: 1 });
      if (dv > 0) mm.sv += dv; else mm.bv -= dv;
      if (dl > 0) mm.sl += dl; else mm.bl -= dl;
    }
  });
  return out;
}
const phase = (k: number, ...spans: [number, number, number][]) => { for (const [a, b, v] of spans) if (k >= a && k <= b) return v; return 0 };
const PLANS: Record<string, [number, (k: number) => Plan]> = {
  OLDA: [31, k => ({ bandar: phase(k, [12, 26, 1], [38, 50, -1], [54, 59, 1]) as 1, foreign: phase(k, [15, 24, 1], [40, 49, -1]) as 1, spike: [25, 33, 47, 58].includes(k), yp: k >= 30 && k <= 44 ? 3000 : 0 })],
  OLDB: [32, k => ({ bandar: (Math.floor(k / 6) % 3 === 0 ? 1 : Math.floor(k / 6) % 3 === 1 ? -1 : 0) as 1, foreign: phase(k, [4, 11, 1], [28, 39, 1], [45, 52, -1]) as 1, spike: [22, 44, 45].includes(k), yp: k >= 8 && k <= 20 ? 2500 : 0 })],
  OLDC: [33, k => ({ bandar: phase(k, [30, 45, 1]) as 1, foreign: phase(k, [20, 28, -1], [50, 59, 1]) as 1, spike: [30, 52].includes(k), yp: k % 7 === 0 ? 4000 : 0 })],
};
const OLD: Record<string, Stock> = Object.fromEntries(Object.entries(PLANS).map(([id, [seed, plan]], j) => [id, stock(id, 40 + j, regimeRows(300 + j, id, 40 + j, plan))]));

/* ---- the old formulas (AUDIT.md 16.5), on the stock's sessions ------------------------------------------------------- */

/** The rows of each of the stock's sessions in the window (its price bars; a broker row on another date is not counted). */
const sessionsOf = (st: Stock) => { const T = terminal(st); return { T, rows: T.candles.map(d => st.rows.filter(r => r.d === d)) } };
/** Each broker's net value (bv - sv) over sessions a..t on the boards, every investor type. */
function nets(rows: Row[][], a: number, t: number, boards: string[]): Map<string, number> {
  const n = new Map<string, number>();
  for (let k = a; k <= t; k++) for (const r of rows[k]) if (boards.includes(r.m)) n.set(r.b, (n.get(r.b) ?? 0) + r.bv - r.sv);
  return n;
}
const byCode = (x: [string, number], y: [string, number]) => x[0] < y[0] ? -1 : 1;
/** Old FL01 fnet: the foreign investors' net value over the last D sessions on the boards (the old default: every
    board). Each old formula below takes the board set its definition reads, so it is compared on the board set the
    rebuilt condition uses. */
const oldFnet = (rows: Row[][], t: number, D: number, boards: string[]) => sum(rows.slice(t - D + 1, t + 1).flat().filter(r => r.i === 'Foreign' && boards.includes(r.m)).map(r => r.bv - r.sv));
/** Old FL04 fstreak: +k when the foreign net was above 0 on each of the last k sessions, -k below 0, 0 when today's is 0;
    capped at 60 (a session without a trade counts 0 and ends the run). */
function oldFstreak(rows: Row[][], t: number, boards: string[]): number {
  const F = (k: number) => sum(rows[k].filter(r => r.i === 'Foreign' && boards.includes(r.m)).map(r => r.bv - r.sv)), s = Math.sign(F(t));
  let k = 0;
  while (s !== 0 && t - k >= 0 && Math.sign(F(t - k)) === s && k < 60) k++;
  return s * k;
}
/** Old FL09 bandar balance: 100 x (B_N + S_N) / V over D sessions on the boards; B_N the N largest positive broker nets,
    S_N the N most negative, V every broker's buy value. States: Big Acc >= 10, Acc >= 6, Dist <= -6, Big Dist <= -10. */
function oldBandar(rows: Row[][], t: number, D: number, N: number, boards: string[]): number {
  const n = [...nets(rows, t - D + 1, t, boards)];
  const B = n.filter(x => x[1] > 0).sort((x, y) => y[1] - x[1] || byCode(x, y)).slice(0, N), S = n.filter(x => x[1] < 0).sort((x, y) => x[1] - y[1] || byCode(x, y)).slice(0, N);
  const V = sum(rows.slice(t - D + 1, t + 1).flat().filter(r => boards.includes(r.m)).map(r => r.bv));
  return 100 * (sum(B.map(x => x[1])) + sum(S.map(x => x[1]))) / V;
}
/** Old FL13 bavg: 100 x (close / VWAP - 1), VWAP = the top-N net buyers' buy value / (their buy lots x 100) over D
    sessions, the Regular board (D7). */
function oldBavg(rows: Row[][], t: number, D: number, N: number, close: number): number {
  const top = [...nets(rows, t - D + 1, t, ['Regular'])].filter(x => x[1] > 0).sort((x, y) => y[1] - x[1] || byCode(x, y)).slice(0, N).map(x => x[0]);
  const reg = rows.slice(t - D + 1, t + 1).flat().filter(r => r.m === 'Regular' && top.includes(r.b));
  return 100 * (close / (sum(reg.map(r => r.bv)) / (sum(reg.map(r => r.bl)) * 100)) - 1);
}
/** Old FL16 freq: today's trades (every broker's buy_freq on the boards) / the mean of the 20 sessions before. */
const oldFreq = (rows: Row[][], t: number, boards: string[]) => { const f = (rs: Row[]) => sum(rs.filter(r => boards.includes(r.m)).map(r => r.bf!)); return f(rows[t]) / (f(rows.slice(t - 20, t).flat()) / 20) };
/** Old FL06 broker: one broker's net value over D sessions, both investor types, on the boards. */
const oldBroker = (rows: Row[][], t: number, D: number, b: string, boards: string[]) => sum(rows.slice(t - D + 1, t + 1).flat().filter(r => r.b === b && boards.includes(r.m)).map(r => r.bv - r.sv));
/** Old FL10: the HHI of the positive broker nets over D sessions on the boards; its effective number of net buyers 1/H;
    NULL when no broker is a net buyer. */
function oldHhi(rows: Row[][], t: number, D: number, boards: string[]): number | null {
  const pos = [...nets(rows, t - D + 1, t, boards)].sort(byCode).map(x => x[1]).filter(x => x > 0), all = sum(pos);
  return pos.length ? sum(pos.map(x => (x / all) ** 2)) : null;
}
/** Old FL15's distribution days: the sessions of the last D whose own daily top-N balance (old FL09 on one session) is
    below -x. */
const oldDistDays = (rows: Row[][], t: number, D: number, N: number, x: number, boards: string[]) => { let n = 0; for (let k = t - D + 1; k <= t; k++) if (oldBandar(rows, k, 1, N, boards) < -x) n++; return n };

/* ---- the screener's verdict at each session ------------------------------------------------------------------------ */

const STOCK_LIST = Object.values(OLD), INDEX = synth('IHSG', 2, PRICE_BARS, '2026-07-01'), ROWS = STOCK_LIST.map(s => rowOf(s.t, E));
const ENV = memoryEnv(STOCK_LIST.map(s => s.t), INDEX, ROWS, E, { flow: FLOW_CTX });
const VCTX = { ...vctx(STOCK_LIST.map(s => s.t.ticker)), availability: availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX), flow: FLOW_CTX };
/** The test as validation normalizes it, bound with the loaded window (K1). */
const bound = (test: unknown): BoundCondition => bindCondition({ id: 'a', enabled: true, test: validateTest(test, 't', VCTX) }, 'c', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX });
/** Whether the bound test passes at the stock's window session k (condition.ts evaluateAt at that bar). */
function passes(b: BoundCondition, st: Stock, k: number): boolean {
  const T = terminal(st), t = ENV.bars(st.t.ticker)!, row = ROWS.find(x => x.ticker === st.t.ticker)!;
  return b.evaluateAt({ ticker: t.ticker, dates: t.dates, bars: t.bars as never, at: T.lo + k, row, ihsgCalendar: INDEX.dates, series: r => ENV.series(r, t), xsection: () => null }).cell.status === 'pass';
}
/** The screener's verdict equals the old formula's at every session k >= from of every stock; both verdicts occur. */
function sameVerdicts(name: string, test: unknown, from: number, old: (rows: Row[][], k: number, st: Stock) => boolean): void {
  const b = bound(test), seen = { pass: 0, fail: 0 }, diff: string[] = [];
  for (const st of STOCK_LIST) {
    const { T, rows } = sessionsOf(st);
    for (let k = from; k < T.candles.length; k++) {
      const want = old(rows, k, st), got = passes(b, st, k);
      if (want !== got) diff.push(`${st.t.ticker} ${T.candles[k]}: old ${want}, screener ${got}`);
      seen[want ? 'pass' : 'fail']++;
    }
  }
  expect([name, diff]).toEqual([name, []]);
  expect([name, seen.pass > 0, seen.fail > 0]).toEqual([name, true, true]);
}
const closeAt = (st: Stock, k: number) => { const T = terminal(st); return T.ctx.close[k] as number };
const presetTest = (id: string, leg: string) => PRESETS.presets.find(p => p.id === id)!.definition.conditions.find(c => c.id === leg)!.test;

describe('the eight bandar presets keep their meaning: each rewritten leg gives the old definition\'s verdict on the same rows', () => {
  it('every session of every stock has broker data (the old formulas read a session without a trade as 0; the Terminal\'s indicators as missing)', () => {
    for (const st of STOCK_LIST) expect([st.t.ticker, [...terminal(st).ctx.rows.has].every(x => x === 1), terminal(st).candles.length]).toEqual([st.t.ticker, true, 60]);
  });
  it('every leg of the eight reads the regular board (G1, user 2026-11-07: the flow default board follows the Terminal)', () => {
    for (const id of ['bigacc', 'fstreak', 'silent', 'freq', 'bavg', 'follow', 'qflow', 'vacc']) for (const c of PRESETS.presets.find(p => p.id === id)!.definition.conditions) {
      const flows = JSON.stringify(c.test).match(/"kind":"flow"[^}]*/g) ?? [];
      for (const f of flows) expect([id, c.id, f.includes('"boards":["Regular"]')]).toEqual([id, c.id, true]);
    }
  });
  it('bigacc: Bandar Balance · % (top 3, 10 sessions) inside 10..100 is old FL09 Big Acc (>= 10), on the regular board; on every board when both sides read every board', () => {
    sameVerdicts('bigacc.a', presetTest('bigacc', 'a'), 9, (rows, k) => oldBandar(rows, k, 10, 3, REG) >= 10);
    const all = { kind: 'value', metric: { kind: 'flow', metric: 'FL24', params: { top: 3, window: 10, boards: ['Regular', 'Nego', 'Cash'] } }, op: 'between', value: 10, value2: 100 };
    sameVerdicts('bigacc.a every board', all, 9, (rows, k) => oldBandar(rows, k, 10, 3, ALL) >= 10);
    // the two board sets give other verdicts on some sessions of these rows (a Nego block moves the balance)
    const b1 = bound(presetTest('bigacc', 'a')), b2 = bound(all);
    expect(STOCK_LIST.some(st => terminal(st).candles.some((_, k) => k >= 9 && passes(b1, st, k) !== passes(b2, st, k)))).toBe(true);
  });
  it('vacc and bavg: inside 6..100 is old FL09 Acc or Big Acc (>= 6); silent: above 0 is a positive old balance (regular board)', () => {
    sameVerdicts('vacc.c', presetTest('vacc', 'c'), 9, (rows, k) => oldBandar(rows, k, 10, 3, REG) >= 6);
    sameVerdicts('bavg.b', presetTest('bavg', 'b'), 9, (rows, k) => oldBandar(rows, k, 10, 3, REG) >= 6);
    sameVerdicts('silent.b', presetTest('silent', 'b'), 9, (rows, k) => oldBandar(rows, k, 10, 3, REG) > 0);
  });
  it('fstreak: Net Flow Streak (every broker, Foreign, cap 60) above 4 is old FL04 above 4; fnet over 20 sessions above 0 is old FL01 above 0 (qflow too), on the regular board', () => {
    sameVerdicts('fstreak.a', presetTest('fstreak', 'a'), 0, (rows, k) => oldFstreak(rows, k, REG) > 4);
    sameVerdicts('fstreak.b', presetTest('fstreak', 'b'), 19, (rows, k) => oldFnet(rows, k, 20, REG) > 0);
    sameVerdicts('qflow.c', presetTest('qflow', 'c'), 19, (rows, k) => oldFnet(rows, k, 20, REG) > 0);
  });
  it('freq: Activity Spike (transactions, buy, 20-session baseline) crossing above 2.5 within 3 sessions is old FL16 crossing above 2.5 within 3, on the regular board', () =>
    sameVerdicts('freq.a', presetTest('freq', 'a'), 23, (rows, k) => [k - 2, k - 1, k].some(s => oldFreq(rows, s - 1, REG) <= 2.5 && oldFreq(rows, s, REG) > 2.5)));
  it('bavg: Buy VWAP · Rolling · Distance % (top 3 net buyers, 10 sessions, Regular) inside -3..3 is old FL13 inside -3..3', () =>
    sameVerdicts('bavg.a', presetTest('bavg', 'a'), 9, (rows, k, st) => { const v = oldBavg(rows, k, 10, 3, closeAt(st, k)); return v >= -3 && v <= 3 }));
  it('follow: Broker Inventory series a of YP over a 5-session lookback (rupiah) above Rp 1 B is old FL06 broker(5, YP) above Rp 1 B, on the regular board', () =>
    sameVerdicts('follow.a', presetTest('follow', 'a'), 4, (rows, k) => oldBroker(rows, k, 5, 'YP', REG) > 1e9));
  it('each of the eight validates and binds against a loaded window, and is AVAILABLE when its other legs are (qflow and vacc wait for fundamentals)', () => {
    const a = availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX);
    for (const id of ['bigacc', 'fstreak', 'silent', 'freq', 'bavg', 'follow', 'qflow', 'vacc']) {
      const p = PRESETS.presets.find(x => x.id === id)!;
      const flowLegs = p.definition.conditions.filter(c => JSON.stringify(c.test).includes('"kind":"flow"')).map(c => c.id);
      const legs = presetAvailability(p, a).unavailable_legs;
      expect([id, flowLegs.length > 0, flowLegs.filter(l => legs.includes(l))]).toEqual([id, true, []]);
      if (!legs.length) expect(validateDefinition(p.definition, VCTX).conditions.length).toBe(p.definition.conditions.length);
      for (const c of p.definition.conditions.filter(x => flowLegs.includes(x.id))) expect(() => bound(c.test)).not.toThrow();
    }
  });
});

describe('the other old formulas of "Rumus lama" (user 2026-11-07), rebuilt on the operators (every board on both sides, the old default)', () => {
  const F = (metric: string, params: Record<string, unknown>, output?: string) => ({ kind: 'flow', metric, params, ...(output ? { output } : {}) });
  it('one broker\'s net over N sessions: Broker Inventory series a of that broker over an N-session lookback (rupiah, every board)', () => {
    for (const [N, b, x] of [[3, 'YP', 0], [8, 'AK', 2e9], [1, 'BK', -1e8]] as const)
      sameVerdicts(`broker(${N}, ${b}) > ${x}`, { kind: 'value', metric: F('FL23', { holders: 'selected', brokers: [b], unit: 'value', series: 'cum', lookback: N, boards: ['Regular', 'Nego', 'Cash'] }), op: 'gt', value: x }, N - 1,
        (rows, k) => oldBroker(rows, k, N, b, ALL) > x);
  });
  it('the effective number of net buyers 1/H at least k: Concentration HHI · Net Buy (every broker, 20 sessions, every board) at most 1/k', () => {
    for (const k0 of [3, 5]) sameVerdicts(`1/H >= ${k0}`, { kind: 'value', metric: F('FL38', { scope: 'all', window: 20, unit: 'value', boards: ['Regular', 'Nego', 'Cash'] }), op: 'le', value: 1 / k0 }, 19,
      (rows, k) => { const h = oldHhi(rows, k, 20, ALL); return h !== null && 1 / h >= k0 });
  });
  it('the named Bandar states as ranges of Bandar Balance · % (top 3, 10 sessions, every board): Big Acc 10..100, Acc or better 6..100, Dist or worse -100..-6, Big Dist -100..-10', () => {
    const bandar = F('FL24', { top: 3, window: 10, boards: ['Regular', 'Nego', 'Cash'] });
    for (const [name, lo, hi, old] of [['Big Acc', 10, 100, (v: number) => v >= 10], ['Acc or better', 6, 100, (v: number) => v >= 6], ['Dist or worse', -100, -6, (v: number) => v <= -6], ['Big Dist', -100, -10, (v: number) => v <= -10]] as const)
      sameVerdicts(name, { kind: 'value', metric: bandar, op: 'between', value: lo, value2: hi }, 9, (rows, k) => old(oldBandar(rows, k, 10, 3, ALL)));
  });
  it('distribution days: at least K of the last 20 sessions with a daily top-3 balance below -x is Persistence (at least K of 20) of Bandar Balance · % over 1 session below -x', () => {
    for (const [K, x] of [[3, 0], [6, 0], [2, 8]] as const)
      sameVerdicts(`dist days >= ${K} (x ${x})`, { kind: 'window', mode: 'at_least', length: 20, count: K, test: { kind: 'value', metric: F('FL24', { top: 3, window: 1, boards: ['Regular', 'Nego', 'Cash'] }), op: 'lt', value: -x } }, 19,
        (rows, k) => oldDistDays(rows, k, 20, 3, x, ALL) >= K);
  });
  it('the old breadth entry is gone (Broker Buy Breadth FL22 replaces it); nothing in the catalog or the presets names an old Phase 2 entry', () => {
    const gone = ['fpct', 'fpart', 'fstreak', 'fsurprise', 'broker', 'topacc', 'buy_intensity', 'bandar', 'net_buy_hhi', 'conc_gap', 'breadth', 'bavg', 'dominant_persistence', 'acc_days', 'freq',
      'trade_size_change', 'crossing_share', 'inst_retail', 'insider_net'];
    const flows = METRICS_CATALOG.metrics.filter(m => m.kind === 'flow').map(m => m.id);
    expect(gone.filter(id => flows.includes(id))).toEqual([]);
    expect(flows.includes('FL22') && flows.includes('fnet')).toBe(true);
    const named = PRESETS.presets.flatMap(p => JSON.stringify(p.definition).match(/"metric":"[^"]+"/g) ?? []).map(x => x.slice(10, -1));
    expect([...new Set(named)].filter(id => gone.includes(id))).toEqual([]);
  });
});
