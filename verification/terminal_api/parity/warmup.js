const TA = require('./ta_engine.js'); const data = require('./data.json');
const tests = [['ema_200','ema',{source:'close',length:200},'ema'],['ema_50','ema',{source:'close',length:50},'ema'],['rsi_14','rsi',{source:'close',length:14},'rsi'],['macd_signal','macd',{source:'close',fast_length:12,slow_length:26,signal_length:9},'signal'],['atr_14','atr',{length:14,smoothing_type:'RMA'},'atr'],['adx_14','adx',{di_length:14,adx_smoothing:14},'adx']];
for (const t of ['BBCA','GOTO']) {
  const d = data[t], idx = Object.fromEntries(d.f04cols.map((c,i)=>[c,i]));
  for (const start of ['2021-01-01','2025-01-01']) {
    const k = d.price.findIndex(r => r[0] >= start), P = d.price.slice(k);
    const B = { T:P.map(r=>r[0]), O:P.map(r=>r[1]), H:P.map(r=>r[2]), L:P.map(r=>r[3]), C:P.map(r=>r[4]), V:P.map(r=>r[5]) };
    const F = d.f04.slice(k);
    const row = [];
    for (const [col, fn, p, out] of tests) {
      const h = TA.F[fn](B, p)[out], f = F.map(r => r[idx[col]]);
      let lastBad = null; for (let i = 0; i < h.length; i++) if (h[i] !== null && f[i] !== null && Math.abs(h[i]-f[i])/Math.abs(f[i]) > 1e-3) lastBad = i;
      const bars = lastBad === null ? 0 : lastBad + 1;
      row.push(`${col}: >0.1% diff until ${lastBad===null?'never':B.T[lastBad]} (${bars} bars)`);
    }
    console.log(`${t} loaded from ${start}:\n  ` + row.join('\n  '));
  }
}
