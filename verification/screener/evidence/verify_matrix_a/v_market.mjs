// Verifier, full market: (1) F04 (since 2026-04-01) vs terminal F for every ticker; (2) Donchian same-bar vs prior-bar breakout counts
// via the backtest compare(); (3) timing of all 27 defaults; (4) H=L / zero-volume stats; (5) IHSG behaviour.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const { compare } = await import('/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data_all/';
const files = fs.readdirSync(dir).filter(f => f.startsWith('price_')).sort();
const bars = {}; const f04 = {};
for (const f of files) {
  const p = JSON.parse(fs.readFileSync(dir + f)); for (const r of p.rows) { (bars[r[0]] ||= []).push(r) }
  const q = JSON.parse(fs.readFileSync(dir + f.replace('price_', 'f04_'))); f04.cols = q.cols; for (const r of q.rows) { (f04[r[0]] ||= []).push(r) }
}
const tickers = Object.keys(bars).sort();
const toB = P => ({ T: P.map(r => r[1]), O: P.map(r => r[2]), H: P.map(r => r[3]), L: P.map(r => r[4]), C: P.map(r => r[5]), V: P.map(r => r[6]) });
const C4 = f04.cols; const ix = n => C4.indexOf(n);
const agg = {}; let tickersCmp = 0, rowsCmp = 0, missingF04 = [];
const KEYS27 = ['sma','ema','wma','hma','kama','macd','adx','aroon','supertrend','donchian','keltner','psar','rsi','stoch_rsi','stochastic','williams_r','roc','momentum','cci','cmo','tsi','trix','ultimate_osc','awesome_osc','ppo','bop','bollinger'];
let tAll = 0, nBars = 0; const don = { gt: 0, xa: 0, lt: 0, xb: 0, gtPrev: 0, xaPrev: 0, ltPrev: 0, xbPrev: 0, tickers: 0 };
const lastBar = {}; // latest-bar values for screening stats
for (const t of tickers) {
  const P = bars[t], B = toB(P); nBars += P.length;
  const t0 = performance.now(); const outs = {}; for (const k of KEYS27) outs[k] = F[k](B, {}); tAll += performance.now() - t0;
  lastBar[t] = { date: P[P.length - 1][1], n: P.length, rsi: outs.rsi.rsi.at(-1), uo: outs.ultimate_osc.uo.at(-1), cmo: outs.cmo.cmo.at(-1), bop: outs.bop.bop.at(-1), hl: P.at(-1)[3] === P.at(-1)[4] };
  // Donchian through compare()
  if (t !== 'IHSG' && P.length > 25) {
    const d = outs.donchian, n = P.length, C = B.C; don.tickers++;
    const prevU = d.upper.map((v, i) => i ? d.upper[i - 1] : null), prevL = d.lower.map((v, i) => i ? d.lower[i - 1] : null);
    const s = (a, op, b) => compare(a, op, b, 0, n).reduce((x, y) => x + y, 0);
    don.gt += s(C, 'gt', d.upper); don.xa += s(C, 'crosses_above', d.upper); don.lt += s(C, 'lt', d.lower); don.xb += s(C, 'crosses_below', d.lower);
    don.gtPrev += s(C, 'gt', prevU); don.xaPrev += s(C, 'crosses_above', prevU); don.ltPrev += s(C, 'lt', prevL); don.xbPrev += s(C, 'crosses_below', prevL);
  }
  const R = f04[t]; if (!R) { missingF04.push(t); continue }
  const pos = new Map(P.map((r, i) => [r[1], i]));
  const m = outs.macd, bb = outs.bollinger;
  const pairs = { sma_20: outs.sma.sma, sma_50: F.sma(B, { length: 50 }).sma, ema_12: F.ema(B, { length: 12 }).ema, ema_26: F.ema(B, { length: 26 }).ema,
    ema_50: F.ema(B, { length: 50 }).ema, ema_200: F.ema(B, { length: 200 }).ema, rsi_14: outs.rsi.rsi, macd: m.macd, macd_signal: m.signal,
    macd_histogram: m.histogram, atr_14: F.atr(B, {}).atr, adx_14: outs.adx.adx, bb_upper_20: bb.upper, bb_middle_20: bb.basis, bb_lower_20: bb.lower };
  tickersCmp++;
  for (const r of R) {
    const i = pos.get(r[1]); if (i === undefined) { (agg._datesMissing ||= 0); agg._datesMissing++; continue }
    rowsCmp++;
    for (const [k, s] of Object.entries(pairs)) {
      const a = s[i], b = r[ix(k)]; const g = (agg[k] ||= { nm: 0, maxr: 0, n: 0, worst: '' });
      if ((a === null) !== (b === null)) { g.nm++; continue } if (a === null) continue;
      g.n++; const rel = a === b ? 0 : Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b)); if (rel > g.maxr) { g.maxr = rel; g.worst = t + ' ' + r[1] }
    }
  }
}
console.log(`tickers=${tickers.length} bars=${nBars} f04 tickers compared=${tickersCmp} rows=${rowsCmp} missingF04=${missingF04.join(',')} datesMissing=${agg._datesMissing || 0}`);
for (const [k, g] of Object.entries(agg)) if (k[0] !== '_') console.log(`${k.padEnd(15)} n=${g.n} nullMismatch=${g.nm} maxRel=${g.maxr.toExponential(2)} worst=${g.worst}`);
console.log(`ALL 27 defaults over full history: total ${(tAll / 1000).toFixed(2)} s for ${tickers.length} tickers (${(tAll / tickers.length).toFixed(2)} ms/ticker), one core`);
console.log('Donchian (compare(), all tickers except IHSG):', JSON.stringify(don));
const lb = Object.entries(lastBar).filter(([t, v]) => v.date === '2026-10-27' && t !== 'IHSG');
console.log(`latest-bar 2026-10-27 stocks=${lb.length} rsi<30=${lb.filter(([, v]) => v.rsi !== null && v.rsi < 30).length} rsi==0=${lb.filter(([, v]) => v.rsi === 0).length} uo<0=${lb.filter(([, v]) => v.uo !== null && v.uo < 0).length} uo null=${lb.filter(([, v]) => v.uo === null).length} cmo null=${lb.filter(([, v]) => v.cmo === null).length} bop==0=${lb.filter(([, v]) => v.bop === 0).length} H=L today=${lb.filter(([, v]) => v.hl).length}`);
fs.writeFileSync(dir + '../lastbar.json', JSON.stringify(lastBar));
const ih = bars['IHSG'] && toB(bars['IHSG']);
if (ih) for (const [k, p] of [['bollinger', { basis_ma_type: 'VWMA' }], ['bollinger', {}], ['bop', {}], ['adx', {}], ['rsi', {}]]) { const o = F[k](ih, p); console.log('IHSG', k, JSON.stringify(p), Object.fromEntries(Object.entries(o).map(([a, s]) => [a, s.filter(v => v !== null).length]))) }
