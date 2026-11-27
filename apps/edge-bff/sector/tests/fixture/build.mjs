/* EXEC-SECTOR-ANALYSIS S4, tests only: the sector files in the exact shapes of verification/sector_analysis/CONTRACT.md
   section 3, built from daily closes and volumes the way the contract defines them (breadth counts per group and date,
   the industry index chain-linked on the previous date's weights, the 20 day files, one stock file per sector). It never
   reads a database: its input is made-up data (make.mjs) or, for the local look check only, the user's prototype data
   (from_prototype.mjs, written to a folder git ignores). */

export const PERIODS = { '1D': 1, '3D': 3, '1W': 5, '2W': 10, '1M': 20, '3M': 60, '6M': 120, '1Y': 252 };
export const SECTORS = [
  ['Basic Materials', 'Basic Mat.', 'IDXBASIC'], ['Consumer Cyclicals', 'Cons. Cyc', 'IDXCYCLIC'], ['Consumer Non-Cyclicals', 'Non-Cyc', 'IDXNONCYC'],
  ['Energy', 'Energy', 'IDXENERGY'], ['Financials', 'Financials', 'IDXFINANCE'], ['Healthcare', 'Health', 'IDXHEALTH'], ['Industrials', 'Industrials', 'IDXINDUST'],
  ['Infrastructures', 'Infra', 'IDXINFRA'], ['Properties & Real Estate', 'Property', 'IDXPROPERT'], ['Technology', 'Tech', 'IDXTECHNO'], ['Transportation & Logistic', 'Transport', 'IDXTRANS'],
];

/** a stable 64-hex stand-in for a file's sha256 (the page only passes it back) */
export function fakeSha(text) {
  let h = 0x811c9dc5, out = '';
  for (let k = 0; k < 8; k++) { for (let i = 0; i < text.length; i += 1 + k) h = Math.imul(h ^ text.charCodeAt(i) ^ k, 16777619) >>> 0; out += h.toString(16).padStart(8, '0') }
  return out;
}
const ema = (c, n) => { const k = 2 / (n + 1), out = []; let e = null, seen = 0; for (const v of c) { if (v == null) { out.push(e == null || seen < n ? null : e); continue } e = e == null ? v : v * k + e * (1 - k); seen++; out.push(seen >= n ? e : null) } return out };
const r2 = v => (v == null ? null : Math.round(v * 100) / 100);
const ret = (c, i, n) => (i - n >= 0 && c[i] != null && c[i - n] != null && c[i - n] > 0 ? r2((c[i] / c[i - n] - 1) * 100) : null);

/**
 * input: { market, lq45, dates[], index: {IHSG: closes, LQ45: closes}, sector: {name: closes}, industries: [{name, sector}],
 *          stocks: [{t, n, sec, ind, close: [], volume: []}], days = 20, weightLabel }
 * output: { index: {finished_at, files}, files: {name: doc} }
 */
export function buildFiles(src) {
  const D = src.dates, n = D.length, E = n - 1, market = src.market || 'IHSG', S = src.stocks;
  const sectors = SECTORS.filter(([name]) => src.sector[name]).map(([name, short, index]) => ({ name, short, index }));
  // per stock: EMAs, weight (20-day average traded value, a day without trades counts 0)
  for (const s of S) {
    s.e50 = ema(s.close, 50); s.e200 = ema(s.close, 200);
    s.w = D.map((_, i) => { if (s.close[i] == null) return null; let v = 0; for (let k = Math.max(0, i - 19); k <= i; k++) v += (s.close[k] ?? 0) * (s.volume[k] ?? 0); return Math.round(v / 20) });
  }
  const groups = [[market, () => true], ...sectors.map(x => [x.name, s => s.sec === x.name])];
  const breadth = {};
  for (const [g, inG] of groups) {
    const b = { members: [], n50: [], a50: [], n200: [], a200: [], adv: [], unch: [], dec: [] };
    for (let i = 0; i < n; i++) {
      let m = 0, n50 = 0, a50 = 0, n200 = 0, a200 = 0, adv = 0, unch = 0, dec = 0;
      for (const s of S) {
        if (!inG(s) || s.close[i] == null) continue;
        m++;
        if (s.e50[i] != null) { n50++; if (s.close[i] > s.e50[i]) a50++ }
        if (s.e200[i] != null) { n200++; if (s.close[i] > s.e200[i]) a200++ }
        // as Feature 08 (CONTRACT 2): each stock against its own previous final close, which can be sessions back
        let pv = null; for (let k = i - 1; k >= 0 && pv == null; k--) pv = s.close[k];
        if (pv != null) { if (s.close[i] > pv) adv++; else if (s.close[i] < pv) dec++; else unch++ }
      }
      b.members.push(m); b.n50.push(n50); b.a50.push(a50); b.n200.push(n200); b.a200.push(a200); b.adv.push(adv); b.unch.push(unch); b.dec.push(dec);
    }
    breadth[g] = b;
  }
  // the industry index: level 100 on its first date, then x (1 + the return weighted by the previous date's weights)
  const industry = {};
  for (const x of src.industries) {
    const ms = S.filter(s => s.ind === x.name), level = [], members = [];
    let lv = null;
    for (let i = 0; i < n; i++) {
      members.push(ms.filter(s => s.close[i] != null).length);
      let sw = 0, sr = 0;
      for (const s of ms) if (i > 0 && s.close[i] != null && s.close[i - 1] != null && s.w[i - 1] > 0) { sw += s.w[i - 1]; sr += s.w[i - 1] * (s.close[i] / s.close[i - 1] - 1) }
      // as Feature_08_Group_Daily (CONTRACT 2): NULL on a date without a member that has both closes; the level carries
      let moved = false;
      if (lv == null) { if (members[i]) { lv = 100; moved = true } } else if (sw > 0) { lv = lv * (1 + sr / sw); moved = true }
      level.push(lv == null || !moved ? null : Math.round(lv * 1e4) / 1e4);
    }
    industry[x.name] = { level, members };
  }
  const tickers = S.map(s => s.t), files = {};
  const dates20 = D.slice(Math.max(0, n - (src.days || 20)));
  files['sector-meta'] = {
    schema: 1, market, benchmarks: [market, src.lq45 || 'LQ45'], weight_basis: 'adv20_value', weight_label: src.weightLabel || '20-day average traded value',
    periods: PERIODS, sectors, industries: src.industries,
    stocks: { ticker: tickers, name: S.map(s => s.n), sector: S.map(s => s.sec || 'Other'), industry: S.map(s => s.ind ?? null) },
    dates: dates20, prices_through: D[E], breadth_through: D[E],
  };
  files['sector-series'] = { schema: 1, dates: D, index: src.index, sector: src.sector, breadth, industry };
  for (const d of dates20) {
    const i = D.indexOf(d), rows = { i: [], close: [], volume: [], r1d: [], r5d: [], r1m: [], r3m: [], weight: [], above_ema50: [], above_ema200: [], d_ema50: [], d_ema200: [], days50: [], days200: [], since50: [], since200: [] };
    S.forEach((s, k) => {
      if (s.close[i] == null) return;
      rows.i.push(k); rows.close.push(s.close[i]); rows.volume.push(s.volume[i]); rows.weight.push(s.w[i]);
      rows.r1d.push(ret(s.close, i, 1)); rows.r5d.push(ret(s.close, i, 5)); rows.r1m.push(ret(s.close, i, 20)); rows.r3m.push(ret(s.close, i, 60));
      for (const [e, a, dd, dy, sn] of [[s.e50, 'above_ema50', 'd_ema50', 'days50', 'since50'], [s.e200, 'above_ema200', 'd_ema200', 'days200', 'since200']]) {
        if (e[i] == null) { rows[a].push(null); rows[dd].push(null); rows[dy].push(null); rows[sn].push(null); continue }
        // as the publisher (sector.py run_length): counted back over the stock's own rows (a session without a close is not
        // a row), at most 300 ("300+", no first session)
        const up = s.close[i] > e[i];
        let j = i, bars = 1;
        for (let k = i - 1; k >= 0 && bars < 300; k--) { if (s.close[k] == null) continue; if (e[k] == null || (s.close[k] > e[k]) !== up) break; j = k; bars++ }
        rows[a].push(up ? 1 : 0); rows[dd].push(r2((s.close[i] / e[i] - 1) * 100)); rows[dy].push(bars); rows[sn].push(bars >= 300 ? null : D[j]);
      }
    });
    files[`sector-day-${d}`] = { schema: 1, date: d, prior_date: i > 0 ? D[i - 1] : null, stocks: rows };
  }
  for (const x of sectors) {
    const ms = S.filter(s => s.sec === x.name);
    files[`sector-stocks-${x.index.toLowerCase()}`] = { schema: 1, sector: x.name, dates: D, ticker: ms.map(s => s.t), close: ms.map(s => s.close) };
  }
  const index = { finished_at: 'fixture', files: {} };
  for (const [name, doc] of Object.entries(files)) {
    const text = JSON.stringify(doc);
    index.files[name] = { sha256: fakeSha(name + text.length + text.slice(0, 2000)), bytes: text.length, rows: 0, as_of: doc.date || D[E] };
  }
  return { index, files };
}
