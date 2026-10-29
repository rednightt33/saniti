// Same-bar vs prior-bar Donchian/Keltner/Bollinger breakouts through the backtest's own compare() (conditions.ts).
import fs from 'node:fs';
const { F } = await import('/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts');
const { compare } = await import('/home/user/saniti/apps/edge-bff/backtest/src/core/conditions.ts');
for (const t of ['BBCA','TLKM','ANTM','BUMI','BEKS']) {
  const B = JSON.parse(fs.readFileSync(new URL(`./data/${t}.ts.json`, import.meta.url))).bars, n = B.C.length;
  const d = F.donchian(B, {}), lag = [null, ...d.upper.slice(0, -1)], lagL = [null, ...d.lower.slice(0, -1)];
  const cnt = s => s.reduce((a, b) => a + b, 0);
  console.log(t, 'C crosses_above donchian.upper (same bar):', cnt(compare(B.C, 'crosses_above', d.upper, 0, n)),
    '| C gt upper:', cnt(compare(B.C, 'gt', d.upper, 0, n)), '| C lt lower:', cnt(compare(B.C, 'lt', d.lower, 0, n)),
    '| C gt upper[t-1]:', cnt(compare(B.C, 'gt', lag, 0, n)), '| C lt lower[t-1]:', cnt(compare(B.C, 'lt', lagL, 0, n)),
    '| BB C crosses_above upper:', cnt(compare(B.C, 'crosses_above', F.bollinger(B, {}).upper, 0, n)));
}
