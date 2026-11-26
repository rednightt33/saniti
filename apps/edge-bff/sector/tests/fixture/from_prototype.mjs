/* EXEC-SECTOR-ANALYSIS S4, the local look check only: the sector files made from the user's final prototype's data
   (window.SX in its app file, kept outside Git), written to tests/fixture/data/ (git ignores it: it holds market data).

     node tests/fixture/from_prototype.mjs <path to the prototype's app_overview.txt>

   Real, from the prototype: the dates, IHSG, LQ45 and the 11 sector index closes, the stock list with its sector and
   industry, and each stock's last close, 1D / 5D / 1M returns and weight on the last date. The prototype has no stock
   history: each stock's earlier closes are a seeded walk around its sector index, bent to meet those real returns, so the
   breadth, the industry indexes, the EMA distances and the earlier day files are FIXTURES built from it (build.mjs). */
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { buildFiles, SECTORS } from './build.mjs';
import { rng } from './make.mjs';

const path = process.argv[2];
if (!path) { console.error('usage: node tests/fixture/from_prototype.mjs <app_overview.txt>'); process.exit(2) }
const text = readFileSync(path, 'utf8'), at = text.indexOf('window.SX='), end = text.indexOf('</script>', at);
const SX = JSON.parse(text.slice(at + 'window.SX='.length, end).replace(/;\s*$/, ''));
const { series: S, meta: MT, day: DY, ind = {} } = SX, dates = S.dates, n = dates.length, E = dates.indexOf(DY.date);
const r = rng(11), names = SECTORS.map(x => x[0]).filter(x => S.sector[x]);
const industries = [], seen = new Set();
MT.stocks.ticker.forEach((t, i) => { const sec = MT.stocks.sector[i], g = ind[t]; if (g && names.includes(sec) && !seen.has(g)) { seen.add(g); industries.push({ name: g, sector: sec }) } });
industries.sort((a, b) => a.sector.localeCompare(b.sector) || a.name.localeCompare(b.name));
const row = new Map(DY.stocks.i.map((ix, k) => [ix, k]));
const stocks = MT.stocks.ticker.map((t, ix) => {
  const sec = MT.stocks.sector[ix], k = row.get(ix), base = S.sector[sec] || S.index.IHSG;
  if (k == null || DY.stocks.close[k] == null) return { t, n: MT.stocks.name[ix], sec, ind: ind[t] ?? null, close: Array(n).fill(null), volume: Array(n).fill(null) };
  const beta = 0.5 + r() * 1.0, vol = 0.008 + r() * 0.014, w = [100];
  for (let i = 1; i < n; i++) { const m = base[i] / base[i - 1] - 1, z = (r() + r() + r() - 1.5) * 2; w.push(Math.max(0.01, w[i - 1] * (1 + beta * m + vol * z))) }
  const C = DY.stocks.close[k], anchors = [[E, C]];
  for (const [lag, key] of [[1, 'r1d'], [5, 'r5d'], [20, 'r1m']]) { const v = DY.stocks[key][k]; if (v != null && E - lag >= 0) anchors.push([E - lag, C / (1 + v / 100)]) }
  anchors.sort((a, b) => a[0] - b[0]);
  const lf = anchors.map(([i, c]) => [i, Math.log(c / w[i])]);
  const f = i => { if (i <= lf[0][0]) return lf[0][1]; for (let j = 1; j < lf.length; j++) if (i <= lf[j][0]) { const [a, x] = lf[j - 1], [b, y] = lf[j]; return x + ((y - x) * (i - a)) / (b - a || 1) } return lf[lf.length - 1][1] };
  const close = w.map((v, i) => (i > E ? null : Math.max(1, Math.round(v * Math.exp(f(i))))));
  const size = DY.stocks.size[k] || 0;
  return { t, n: MT.stocks.name[ix], sec, ind: ind[t] ?? null, close, volume: close.map(c => (c == null ? null : Math.round((size / c) * (0.6 + r() * 0.8)))) };
});
const out = buildFiles({ market: MT.market, lq45: MT.benchmark || 'LQ45', dates: dates.slice(0, E + 1), index: Object.fromEntries(Object.entries(S.index).map(([k, v]) => [k, v.slice(0, E + 1)])),
  sector: Object.fromEntries(names.map(x => [x, S.sector[x].slice(0, E + 1)])), industries, stocks: stocks.map(s => ({ ...s, close: s.close.slice(0, E + 1), volume: s.volume.slice(0, E + 1) })) });
const dir = new URL('./data/', import.meta.url);
mkdirSync(dir, { recursive: true });
for (const [name, doc] of Object.entries(out.files)) writeFileSync(new URL(`${name}.json`, dir), JSON.stringify(doc));
writeFileSync(new URL('index.json', dir), JSON.stringify(out.index));
console.log(Object.keys(out.files).length, 'files written to', dir.pathname);
