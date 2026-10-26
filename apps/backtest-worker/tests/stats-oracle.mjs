/* The backtest page's statistics (backtest.html, 2026-10-26 upload, section 9 STATISTICS: mean, sd, skew, kurt, quant,
   ncdf, ninv, seriesStats, tradeStats, dsr, monteCarlo) copied as they are, and the arithmetic of run() and the result
   renderers (sections 10 and 11) with the HTML removed. Used only as the test oracle of stats.ts, robustness.ts and
   result.ts. Changes from the page: `export`; monteCarlo takes the trade-return scale (page: S.size.alloc / 100 in
   single mode, 1 / S.maxPos in portfolio mode) and the seed (page: 7) as arguments instead of reading the page state.
   Trades use the page's field names (ret, pnl, riskPct, bars, mae, mfe, cost, tk, ei, xi, why). */
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
export const mean = a => a.reduce((s,x)=>s+x,0)/(a.length||1);
export const sd = a => { const m = mean(a); return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/((a.length-1)||1)) };
export const skew = a => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**3,0)/a.length };
export const kurt = a => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**4,0)/a.length };
export const quant = (a,q) => { const s=[...a].sort((x,y)=>x-y); return s[Math.min(s.length-1, Math.max(0, Math.floor(q*(s.length-1))))] };
export const ncdf = x => { const t=1/(1+.2316419*Math.abs(x)), d=.3989423*Math.exp(-x*x/2), p=d*t*(.3193815+t*(-.3565638+t*(1.781478+t*(-1.821256+t*1.330274)))); return x>0?1-p:p };
export const ninv = p => { const a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.357751867269,-30.66479806614716,2.506628277459239], b=[-54.47609879822406,161.5858368580409,-155.6989798598866,66.80131188771972,-13.28068155288572], c=[-.007784894002430293,-.3223964580411365,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783], d=[.007784695709041462,.3224671290700398,2.445134137142996,3.754408661907416];
  const q = p<.02425 ? Math.sqrt(-2*Math.log(p)) : p>1-.02425 ? Math.sqrt(-2*Math.log(1-p)) : 0;
  if(p<.02425) return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  if(p>1-.02425) return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  const r=p-.5, s=r*r; return (((((a[0]*s+a[1])*s+a[2])*s+a[3])*s+a[4])*s+a[5])*r/(((((b[0]*s+b[1])*s+b[2])*s+b[3])*s+b[4])*s+1) };
export const seriesStats = (vals, benchVals) => {
  const r = []; for(let k=1;k<vals.length;k++) r.push(vals[k]/vals[k-1]-1);
  const br = []; if(benchVals) for(let k=1;k<benchVals.length;k++) br.push(benchVals[k]/benchVals[k-1]-1);
  const years = vals.length/252, tot = vals.at(-1)/vals[0]-1, cagr = Math.pow(1+tot, 1/Math.max(years,.01))-1;
  const vol = sd(r)*Math.sqrt(252), down = Math.sqrt(mean(r.map(x=>Math.min(0,x)**2)))*Math.sqrt(252);
  let peak = vals[0], mdd = 0, dd = [], ddDur = 0, curDur = 0, maxDur = 0, ulc = 0;
  vals.forEach(v => { peak = Math.max(peak,v); const d = v/peak-1; dd.push(d); mdd = Math.min(mdd,d); ulc += d*d; curDur = d<0? curDur+1 : 0; maxDur = Math.max(maxDur,curDur) });
  const sharpe = sd(r) ? mean(r)/sd(r)*Math.sqrt(252) : 0, srd = sd(r) ? mean(r)/sd(r) : 0;
  const sk = r.length>3 ? skew(r) : 0, ku = r.length>3 ? kurt(r) : 3, n = r.length;
  const psr = (sr0) => ncdf(((srd - sr0)*Math.sqrt(n-1))/Math.sqrt(Math.max(1e-9, 1 - sk*srd + (ku-1)/4*srd*srd)));
  let beta = null, alpha = null, corr = null;
  if(br.length===r.length && br.length>2){ const mb = mean(br), mr = mean(r); let cov=0, vb=0, vr=0; for(let k=0;k<r.length;k++){ cov+=(r[k]-mr)*(br[k]-mb); vb+=(br[k]-mb)**2; vr+=(r[k]-mr)**2 } beta = cov/(vb||1); corr = cov/Math.sqrt((vb||1)*(vr||1)); alpha = (mr - beta*mb)*252 }
  const var95 = r.length ? quant(r,.05) : 0, tail = r.filter(x=>x<=var95);
  return {r, tot, cagr, vol, sharpe, sortino: down? mean(r)*252/down : 0, mdd, calmar: mdd? cagr/Math.abs(mdd) : 0, maxDur, ulcer:Math.sqrt(ulc/vals.length), var95, cvar95: tail.length?mean(tail):0, skew:sk, kurt:ku, beta, alpha, corr, dd, psr, srd, n,
          best: r.length?Math.max(...r):0, worst: r.length?Math.min(...r):0, pos: r.filter(x=>x>0).length/(r.length||1)};
};
export const tradeStats = T => {
  const w = T.filter(t=>t.ret>0), l = T.filter(t=>t.ret<=0), gp = w.reduce((s,t)=>s+t.pnl,0), gl = -l.reduce((s,t)=>s+t.pnl,0);
  const fallbackRisk = Math.max(.01, sd(T.map(x=>x.ret))||.01), R = T.map(t=>t.ret/(t.riskPct||fallbackRisk));
  let cw=0, cl=0, mw=0, ml=0; T.forEach(t => { if(t.ret>0){ cw++; cl=0 } else { cl++; cw=0 } mw=Math.max(mw,cw); ml=Math.max(ml,cl) });
  const wr = T.length ? w.length/T.length : 0, aw = w.length?mean(w.map(t=>t.ret)):0, al = l.length?mean(l.map(t=>t.ret)):0;
  return {n:T.length, wins:w.length, losses:l.length, wr, aw, al, payoff: al? aw/Math.abs(al) : 0, pf: gl? gp/gl : (gp?Infinity:0), gp, gl, net:gp-gl,
    exp: T.length?mean(T.map(t=>t.ret)):0, expRp: T.length?(gp-gl)/T.length:0, sqn: R.length>1 ? Math.sqrt(Math.min(R.length,100))*mean(R)/(sd(R)||1) : 0, expR: R.length?mean(R):0,
    mw, ml, best: T.length?Math.max(...T.map(t=>t.ret)):0, worst: T.length?Math.min(...T.map(t=>t.ret)):0,
    hold: T.length?mean(T.map(t=>t.bars)):0, holdW: w.length?mean(w.map(t=>t.bars)):0, holdL: l.length?mean(l.map(t=>t.bars)):0,
    kelly: al&&aw ? wr - (1-wr)/(aw/Math.abs(al)) : 0, mae: T.length?mean(T.map(t=>t.mae)):0, mfe: T.length?mean(T.map(t=>t.mfe)):0 };
};
export const dsr = (st, trials, srs) => { // Deflated Sharpe (Bailey & López de Prado): PSR against the expected max SR of `trials` attempts
  const N_ = Math.max(2, trials), v = srs.length>1 ? sd(srs)**2 : (1/st.n), g = .5772156649;
  const sr0 = Math.sqrt(v)*((1-g)*ninv(1-1/N_) + g*ninv(1-1/(N_*Math.E)));
  return {sr0: sr0*Math.sqrt(252), dsr: st.psr(sr0)} };
export const monteCarlo = (T, cap0, runs=1000, scale, seed=7) => { if(T.length<3) return null; const n = T.length, paths = [], mdds = [], fin = []; let s2 = seed;
  const r2 = () => ((s2 = Math.imul(s2,1664525)+1013904223>>>0)/4294967296);
  for(let k=0;k<runs;k++){ let v = 1, pk = 1, md = 0; const path = [1]; for(let j=0;j<n;j++){ const t = T[Math.floor(r2()*n)]; v *= 1 + t.ret*(t.cost? 1 : 1)*(scale); pk = Math.max(pk,v); md = Math.min(md, v/pk-1); path.push(v) } paths.push(path); mdds.push(md); fin.push(v-1) }
  const bands = [.05,.25,.5,.75,.95].map(q => Array.from({length:n+1},(_,j)=>quant(paths.map(p=>p[j]),q)));
  const below = Array.from({length:n+1},(_,j)=>paths.filter(p=>p[j]<1).length/runs);
  const actual = [1]; T.forEach(t => actual.push(actual.at(-1)*(1+t.ret*(scale))));
  return {bands, mdds, fin, n, below, actual} };

/* ---- section 10 (run) and section 11 (renderers): the arithmetic only, statements kept as on the page, HTML
   dropped. R is the page's S.result shape: eq [[day index, equity]], vals, bench, expo, cap0, trades {tk, ei, xi,
   ret, pnl, bars, why, ...}; DAYS the page's calendar. */
export const runDerived = (res, oosPct) => {   // run(): vals, st, bst, cut, ins, oos, cutDay, ts, tsIn, tsOut
  const vals = res.eq.map(x=>x[1]), st = seriesStats(vals, res.bench), bst = seriesStats(res.bench);
  const cut = oosPct ? Math.floor(vals.length*(1-oosPct/100)) : vals.length;
  const ins = cut>20 ? seriesStats(vals.slice(0,cut), res.bench.slice(0,cut)) : null, oos = oosPct && vals.length-cut>20 ? seriesStats(vals.slice(cut-1), res.bench.slice(cut-1)) : null;
  const cutDay = res.eq[cut-1] ? res.eq[cut-1][0] : null;
  const T = res.trades, ts = tradeStats(T), tsIn = tradeStats(T.filter(t=>cutDay==null||t.ei<=cutDay)), tsOut = tradeStats(T.filter(t=>cutDay!=null&&t.ei>cutDay));
  return {vals, st, bst, cut, ins, oos, cutDay, ts, tsIn, tsOut};
};
export const benchOf = (bc, eq, cap0) => { const bm = eq.map(([i]) => bc[i]); const b0 = bm[0]; return bm.map(v=>v/b0*cap0) };   // backtest() tail
export const exposureMean = R => mean(R.expo);                                                       // KPI 'Exposure'

// GRID_Y and the axes of the sensitivity grid (run()); X = the page's S.exit (sl in percent)
export const GRID_Y = X => X.stopMode==='pct' ? {k:'sl', lbl:'SL %', u:'%', step:2, min:1} : X.stopMode==='atr' ? {k:'slAtr', lbl:'SL × ATR', u:'×', step:.5, min:.5} : X.stopMode==='rr' ? {k:'slRR', lbl:'R:R (1 : x)', u:'', step:.5, min:.5} : {k:'hold', lbl:'Max hold (days)', u:'d', step:5, min:2};
export const gridAxes = (c0val, X) => { const base = c0val, step = Math.max(1, Math.abs(base)*.2 || 1), xs = [-2,-1,0,1,2].map(k=>+(base+k*step).toFixed(2)), yk = GRID_Y(X), y0 = X[yk.k], ys = [-2,-1,0,1,2].map(k=>+Math.max(yk.min, y0+k*yk.step).toFixed(2)); return {xs, ys, yk} };
export const gridCell = r => { const v = r.eq.map(e=>e[1]); const s = seriesStats(v); const t = tradeStats(r.trades); return {sharpe:s.sharpe, cagr:s.cagr, pf:t.pf, n:t.n, mdd:s.mdd} };

// tabOverview: monthly heatmap (per month r, br, year to date; per year total, benchmark, best, worst, positive months)
export const heatmap = (R, DAYS) => {
  const m = {}; R.eq.forEach(([i,v],k) => { const ym = DAYS[i].slice(0,7); const o = (m[ym] ||= {s:k?R.eq[k-1][1]:v, e:v, bs:k?R.bench[k-1]:R.bench[0], be:R.bench[k]}); o.e = v; o.be = R.bench[k] });
  const years = [...new Set(Object.keys(m).map(k=>k.slice(0,4)))];
  return years.map(y=>{ let yr=1; const ms=[]; const cells = Array.from({length:12},(_,k)=>{ const e = m[`${y}-${String(k+1).padStart(2,'0')}`]; if(!e) return null; const r = e.e/e.s-1, br = e.be/e.bs-1; yr *= 1+r; ms.push([MONTHS[k], r]); return {month:k+1, r, br, ytd:yr-1} }).filter(Boolean);
    const ys = Object.keys(m).filter(k=>k.startsWith(y)), b0 = m[ys[0]].bs, b1 = m[ys.at(-1)].be, by = b1/b0-1, best = ms.reduce((a,b)=>b[1]>a[1]?b:a, ms[0]), worst = ms.reduce((a,b)=>b[1]<a[1]?b:a, ms[0]), up = ms.filter(x=>x[1]>0).length;
    return {y, cells, total:yr-1, by, best:[MONTHS.indexOf(best[0])+1, best[1]], worst:[MONTHS.indexOf(worst[0])+1, worst[1]], up, months:ms.length} });
};
// tabOverview: annual bars and their tooltip (without the browser-only comparison lines)
export const annual = (R, DAYS, years) => years.map(y => { const ks = R.eq.map((e,k)=>[e,k]).filter(([e])=>DAYS[e[0]].startsWith(y)); const a = ks[0][1], b = ks.at(-1)[1]; const s0 = a? R.vals[a-1] : R.vals[0], b0 = a? R.bench[a-1] : R.bench[0]; let pk = s0, mdd = 0; for(let k=a;k<=b;k++){ pk = Math.max(pk, R.vals[k]); mdd = Math.min(mdd, R.vals[k]/pk-1) }
  const v = R.vals[b]/s0-1, bb = R.bench[b]/b0-1, tr = R.trades.filter(t=>DAYS[t.xi].startsWith(y));
  return {y, v, b:bb, mdd, closed:tr.length, wr:tr.length?tr.filter(t=>t.ret>0).length/tr.length:null} });
// tabReturns: weekday bars, rolling Sharpe (+ its tooltip: 6-month return, share of time above 1), trade-return legend
export const weekday = (R, DAYS) => [1,2,3,4,5].map(d => { const rr = []; R.eq.forEach(([i],k) => { if(k && new Date(DAYS[i]).getUTCDay()===d) rr.push(R.vals[k]/R.vals[k-1]-1) }); const mu = mean(rr);
  return {d, mean:mu, median:quant(rr,.5), pos:rr.filter(x=>x>0).length/(rr.length||1), days:rr.length, best:Math.max(...rr), worst:Math.min(...rr)} });
export const rolling = st => { const roll = []; const W = 126; for(let k=0;k<st.r.length;k++){ if(k<W){ roll.push(NaN); continue } const s = st.r.slice(k-W,k); roll.push(sd(s)?mean(s)/sd(s)*Math.sqrt(252):0) }
  const ret = roll.map((v,k) => { if(!isFinite(v)) return NaN; const win = st.r.slice(Math.max(0,k-126),k); return win.reduce((p,x)=>p*(1+x),1)-1 });
  return {roll, ret, above:roll.filter(x=>x>=1).length/roll.filter(isFinite).length} };
export const tradeReturns = T => { const tr = T.map(t=>t.ret); return {mean:mean(tr), median:quant(tr,.5), sd:sd(tr), skew:T.length>3?skew(tr):null} };
// tabTrades: exit reasons (bars + tooltip + legend), P&L by stock (portfolio), win/loss streaks (single)
export const exitReasons = T => { const why = {}; T.forEach(t => why[t.why] = (why[t.why]||0)+1);
  return Object.entries(why).map(([k,v])=>{ const tt = T.filter(t=>t.why===k), pnl = tt.reduce((s,t)=>s+t.pnl,0); return {why:k, n:v, wins:tt.filter(t=>t.ret>0).length, avg:mean(tt.map(t=>t.ret)), pnl, bars:mean(tt.map(t=>t.bars))} }) };
export const byTicker = T => { const byTk = {}; T.forEach(t => (byTk[t.tk] ||= []).push(t));
  return Object.entries(byTk).map(([k,v])=>{ const p = v.reduce((s,t)=>s+t.pnl,0); return {tk:k, pnl:p, share:p/(T.reduce((s,t)=>s+t.pnl,0)||1), n:v.length, wins:v.filter(t=>t.ret>0).length, avg:mean(v.map(t=>t.ret))} }) };
export const streaks = T => { let run = 0, prev = null; const pos = T.map(t => { const w = t.ret>0; run = w===prev ? run+1 : 1; prev = w; return run });
  const len = pos.map((p,i) => { let j = i; while(j+1<pos.length && pos[j+1]>pos[j]) j++; return pos[j] }); return {pos, len} };
// tabRisk: ddTable (five deepest drawdowns, deepest first)
export const ddTable = R => { const v = R.vals, out = []; let pk = 0, inDD = false, st = 0, trough = 0;
  for(let k=1;k<v.length;k++){ if(v[k]>=v[pk]){ if(inDD){ out.push({s:st, t:trough, e:k, d:v[trough]/v[st]-1}); inDD=false } pk = k } else { if(!inDD){ inDD = true; st = pk; trough = k } if(v[k]<v[trough]) trough = k } }
  if(inDD) out.push({s:st, t:trough, e:null, d:v[trough]/v[st]-1});
  out.sort((a,b)=>a.d-b.d);
  return out.slice(0,5).map(d => ({...d, days:(d.e??R.eq.length-1)-d.s})) };
// tabRobust: Monte Carlo legends
export const mcLegend = mc => { const fin = mc.fin, mdd = mc.mdds; return {p50:quant(fin,.5), p05:quant(fin,.05), p95:quant(fin,.95), loss:fin.filter(x=>x<0).length/fin.length, mdd50:quant(mdd,.5), mdd05:quant(mdd,.05)} };
// updateViewbar: the portfolio signals table (trades, wins, P&L of one ticker)
export const tickerRow = (T, t) => { const tr = T.filter(x=>x.tk===t); const w = tr.filter(x=>x.ret>0).length; return {n:tr.length, wins:w, pnl:tr.reduce((s,x)=>s+x.pnl,0)} };
