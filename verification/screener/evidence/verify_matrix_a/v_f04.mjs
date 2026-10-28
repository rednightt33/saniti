// Verifier: F04 columns vs terminal F on independently fetched tickers. Reports first valid index, null mismatches, max rel/abs diff.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const dir = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/';
const fv = s => s.findIndex(v => v !== null && v !== undefined);
for (const t of process.argv.slice(2)) {
  const d = JSON.parse(fs.readFileSync(dir + t + '.json'));
  const P = d.price.rows, fc = d.f04.cols, fr = d.f04.rows;
  const B = { T: P.map(r => r[0]), O: P.map(r => r[1]), H: P.map(r => r[2]), L: P.map(r => r[3]), C: P.map(r => r[4]), V: P.map(r => r[5]) };
  const sameDates = fr.length === P.length && fr.every((r, i) => r[0] === P[i][0]);
  const versions = [...new Set(fr.map(r => r[fc.indexOf('calculation_version')]))];
  const m = F.macd(B, {}), bb = F.bollinger(B, {});
  const pairs = { sma_20: F.sma(B, { length: 20 }).sma, sma_50: F.sma(B, { length: 50 }).sma, ema_12: F.ema(B, { length: 12 }).ema,
    ema_26: F.ema(B, { length: 26 }).ema, ema_50: F.ema(B, { length: 50 }).ema, ema_200: F.ema(B, { length: 200 }).ema,
    rsi_14: F.rsi(B, {}).rsi, macd: m.macd, macd_signal: m.signal, macd_histogram: m.histogram, atr_14: F.atr(B, {}).atr,
    adx_14: F.adx(B, {}).adx, bb_upper_20: bb.upper, bb_middle_20: bb.basis, bb_lower_20: bb.lower, close: B.C };
  console.log(`== ${t} bars=${P.length} f04rows=${fr.length} sameDates=${sameDates} versions=${versions.join(',')}`);
  for (const [k, ts] of Object.entries(pairs)) {
    const f4 = fr.map(r => r[fc.indexOf(k)]);
    let nm = 0, maxr = 0, maxa = 0, at = -1, n = 0;
    for (let i = 0; i < ts.length; i++) {
      const a = ts[i], b = f4[i];
      if ((a === null) !== (b === null)) { nm++; continue }
      if (a === null) continue;
      n++; const ad = Math.abs(a - b), r = a === b ? 0 : ad / Math.max(Math.abs(a), Math.abs(b));
      if (r > maxr) { maxr = r; at = i } if (ad > maxa) maxa = ad;
    }
    console.log(`${k.padEnd(15)} fvTS=${fv(ts)} fvF04=${fv(f4)} n=${n} nullMismatch=${nm} maxRel=${maxr.toExponential(2)} maxAbs=${maxa.toExponential(2)} at=${at >= 0 ? P[at][0] : '-'}`);
  }
}
