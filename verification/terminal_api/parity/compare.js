const TA = require('./ta_engine.js');
const data = require('./data.json');
const map = [ // f04 column -> [html fn, params, output]
  ['sma_20','sma',{source:'close',length:20},'sma'], ['sma_50','sma',{source:'close',length:50},'sma'],
  ['ema_12','ema',{source:'close',length:12},'ema'], ['ema_26','ema',{source:'close',length:26},'ema'],
  ['ema_50','ema',{source:'close',length:50},'ema'], ['ema_200','ema',{source:'close',length:200},'ema'],
  ['rsi_14','rsi',{source:'close',length:14},'rsi'],
  ['macd','macd',{source:'close',fast_length:12,slow_length:26,signal_length:9},'macd'],
  ['macd_signal','macd',{source:'close',fast_length:12,slow_length:26,signal_length:9},'signal'],
  ['macd_histogram','macd',{source:'close',fast_length:12,slow_length:26,signal_length:9},'histogram'],
  ['atr_14','atr',{length:14,smoothing_type:'RMA'},'atr'],
  ['bb_upper_20','bollinger',{source:'close',length:20,std_dev:2,basis_ma_type:'SMA'},'upper'],
  ['bb_middle_20','bollinger',{source:'close',length:20,std_dev:2,basis_ma_type:'SMA'},'basis'],
  ['bb_lower_20','bollinger',{source:'close',length:20,std_dev:2,basis_ma_type:'SMA'},'lower'],
  ['adx_14','adx',{di_length:14,adx_smoothing:14},'adx'],
];
for (const [t, d] of Object.entries(data)) {
  const P = d.price, B = { T:P.map(r=>r[0]), O:P.map(r=>r[1]), H:P.map(r=>r[2]), L:P.map(r=>r[3]), C:P.map(r=>r[4]), V:P.map(r=>r[5]) };
  const idx = Object.fromEntries(d.f04cols.map((c,i)=>[c,i]));
  console.log(`== ${t} (${P.length} bars)`);
  for (const [col, fn, p, out] of map) {
    const h = TA.F[fn](B, p)[out], f = d.f04.map(r => r[idx[col]]);
    const fh = h.findIndex(v => v !== null), ff = f.findIndex(v => v !== null);
    let maxAbs = 0, maxRel = 0, nBoth = 0, onlyH = 0, onlyF = 0, last = null, lastBig = null;
    for (let i = 0; i < h.length; i++) {
      const a = h[i], b = f[i];
      if (a === null && b === null) continue;
      if (a === null) { onlyF++; continue } if (b === null) { onlyH++; continue }
      nBoth++; const ad = Math.abs(a - b), rd = ad / Math.max(1e-12, Math.abs(b));
      if (ad > maxAbs) maxAbs = ad; if (rd > maxRel) maxRel = rd; if (rd > 1e-9) lastBig = i;
    }
    console.log(`${col.padEnd(15)} firstValid html=${fh} f04=${ff} | both=${nBoth} onlyHtml=${onlyH} onlyF04=${onlyF} | maxAbs=${maxAbs.toExponential(2)} maxRel=${maxRel.toExponential(2)} lastDiff>1e-9 at ${lastBig===null?'-':B.T[lastBig]}`);
  }
}
