// PPO derived from stored Feature 04 (100*macd/ema_26) vs the terminal ppo; Bollinger WMA basis for the TA-Lib check.
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
for (const t of ['BBCA','TLKM','ANTM','BUMI','BEKS','RANS']) {
  const d = JSON.parse(fs.readFileSync(new URL(`./data/${t}.json`, import.meta.url)));
  const B = JSON.parse(fs.readFileSync(new URL(`./data/${t}.ts.json`, import.meta.url))).bars;
  const c = d.f04.cols, mi = c.indexOf('macd'), ei = c.indexOf('ema_26');
  const ppo = F.ppo(B, {}).ppo; let mx = 0, nm = 0;
  d.f04.rows.forEach((r, i) => { const v = r[mi] === null || r[ei] === null ? null : 100 * r[mi] / r[ei];
    if ((v === null) !== (ppo[i] === null)) { nm++; return } if (v === null) return;
    const rel = v === ppo[i] ? 0 : Math.abs(v - ppo[i]) / Math.max(Math.abs(v), Math.abs(ppo[i])); if (rel > mx) mx = rel });
  console.log(t, 'ppo vs 100*macd/ema_26 (F04): max rel', mx.toExponential(2), 'null mismatch', nm);
  fs.writeFileSync(new URL(`./data/${t}.bbwma.json`, import.meta.url), JSON.stringify(F.bollinger(B, { basis_ma_type: 'WMA' })));
}
