/* ---- Overview: equity + underwater (Lightweight Charts), comparison lines, monthly heatmap, annual returns ----
   (backtest.html section 11). The comparison lines (S.cmp, up to 2) are display only: the published closes of those
   tickers as of each day of the result (BacktestApi.closes, CONTRACT.md D-X2); KPIs stay against the primary benchmark. */
import * as L from 'lightweight-charts';
import { $, CMP_COLORS, cls, css, esc, fmtD, ico, MONTHS, nf, PAL, pct, pctu, rp, toast } from '../format.ts';
import { API, STOCKS } from '../env.ts';
import { S } from '../state.ts';
import type { PageResult } from '../api/adapt.ts';
import { bars, DAYS, TT, ttH } from './svg.ts';
import { bindTips } from './index.ts';

/* benchmark series: one function for the primary benchmark and the comparison lines */
export const primaryBench = () => S.mode==='single' ? (S.bench==='ihsg' ? 'IHSG' : S.ticker) : 'IHSG';
/** markup (legends, the hover legend, tooltips): the ticker escaped */
export const primaryBenchLabel = () => S.mode==='single' && S.bench!=='ihsg' ? 'Buy & hold '+esc(S.ticker) : 'IHSG';

/** the published closes of the comparison tickers on the result's days (loaded once per result) */
export const ensureCmp = async (R: PageResult, keys: string[]) => {
  await Promise.all(keys.filter(k => !R.cmp.has(k)).map(async k => { R.cmp.set(k, await API.closes(k, R.days)) }));
};

let eqc: L.IChartApi | null = null;
export const getEqc = () => eqc;
/* a line point; a day without a value (before the ticker's first bar) is left empty */
const pt = (time: string, value: number) => isFinite(value) ? {time, value} : {time};
export const tabOverview = (el: HTMLElement) => {
  S.cmp = S.cmp.filter(k => k!==primaryBench());   // a comparison line never duplicates the primary benchmark
  const R = S.result, st = R.st, ts = R.ts;
  const good = [st.sharpe>1, ts.pf>1.3, st.cagr>R.bst.cagr, R.ds.dsr>.9, (R.oos?R.oos.sharpe>0.5:true)];
  const score = good.filter(Boolean).length, tone = score>=4?'pos':score>=2?'warn':'neg';
  void tone;
  el.innerHTML = `
    <div class="panel" style="padding:0;overflow:hidden"><div style="display:flex;align-items:center;gap:14px;padding:10px 14px;border-bottom:1px solid var(--border)"><h4 style="margin:0">Equity vs benchmark</h4><div class="legend" style="margin:0"><span><i style="background:${PAL.navy}"></i>Strategy</span><span><i style="background:${PAL.bm}"></i>${primaryBenchLabel()}</span>${S.cmp.map((k,j)=>`<span><i style="background:${CMP_COLORS[j]}"></i>${esc(k)}</span>`).join('')}${R.oos?'<span><i style="background:rgba(245,166,35,.35)"></i>Out-of-sample</span>':''}<span><i style="background:rgba(${PAL.dnRgb},.5)"></i>Drawdown (lower pane)</span></div><span style="flex:1"></span><div class="cmpbox" id="cmpBox"></div></div><div style="position:relative"><div class="eqleg" id="eqLeg"></div><div id="eqChart"></div></div></div>
    <div class="grid2" style="margin-top:16px"><div class="panel"><h4>Monthly returns</h4><div class="sub">Strategy return per month (%), with the yearly total</div><div id="heat"></div></div>
    <div class="panel"><h4>Annual returns</h4><div class="sub">Strategy vs benchmark per calendar year</div><div id="annual"></div><div class="legend"><span><i style="background:${PAL.navy}"></i>Strategy</span><span><i style="background:#c4c4c4"></i>${primaryBenchLabel()}</span>${S.cmp.map((k,j)=>`<span><i style="background:${CMP_COLORS[j]}"></i>${esc(k)}</span>`).join('')}</div></div></div>`;
  // comparison benchmarks (up to 2): drawn next to the primary benchmark; KPIs stay against the primary benchmark
  const cmpSeries = S.cmp.map(k => { const c = R.cmp.get(k) || [], c0 = c[R.eq[0][0]]; return R.eq.map(([i]) => c[i]==null||c0==null ? NaN : c[i]/c0*R.cap0) });
  const opts = [...STOCKS(), 'IHSG'].filter(k => k!==primaryBench() && !S.cmp.includes(k));
  $('cmpBox').innerHTML = S.cmp.map((k,j)=>`<span class="cmpchip"><i style="background:${CMP_COLORS[j]}"></i>${esc(k)}<button data-cdel="${esc(k)}" title="Remove ${esc(k)}">${ico('<path d="M6 6l12 12M18 6 6 18"/>')}</button></span>`).join('')
    + (S.cmp.length<2 ? `<select class="sel cmpadd" id="cmpAdd" title="Compare with up to 2 more tickers"><option value="">+ Compare with…</option>${opts.map(k=>`<option value="${esc(k)}">${esc(k)}</option>`).join('')}</select>` : `<span class="cmpmax">Max 2</span>`);
  const reTab = () => { if(S.result!==R || S.tab!=='overview') return; tabOverview(el); bindTips() };
  const ca = $('cmpAdd'); if(ca) ca.onchange = () => { if(ca.value){ S.cmp.push(ca.value); ensureCmp(R, S.cmp).then(reTab, e => { toast(e.message); S.cmp = S.cmp.filter(k => R.cmp.has(k)); reTab() }) } };
  $('cmpBox').querySelectorAll('[data-cdel]').forEach((b: HTMLElement) => b.onclick = () => { S.cmp = S.cmp.filter(k=>k!==b.dataset.cdel); reTab() });
  // equity chart
  if(eqc){ eqc.remove(); eqc = null }
  eqc = L.createChart($('eqChart'), {autoSize:true, localization:{locale:'id-ID'}, layout:{background:{type:L.ColorType.Solid,color:css('--surface')}, textColor:css('--text-3'), fontFamily:'Inter, "Segoe UI", system-ui, sans-serif', attributionLogo:false, panes:{separatorColor:css('--border')}}, grid:{vertLines:{visible:false},horzLines:{color:css('--border')+'80'}}, rightPriceScale:{borderColor:css('--border')}, timeScale:{borderColor:css('--border')}});
  if(R.oos){ const sh = eqc.addSeries(L.HistogramSeries, {color:'rgba(245,166,35,.07)', priceScaleId:'shade', priceLineVisible:false, lastValueVisible:false}); eqc.priceScale('shade').applyOptions({visible:false, scaleMargins:{top:0,bottom:0}}); sh.setData(R.eq.map(([i],k)=>({time:DAYS[i], value:k>=R.cut?1:0}))) }
  const bm = eqc.addSeries(L.LineSeries, {color:PAL.bm, lineWidth:1.5 as L.LineWidth, priceLineVisible:false, priceFormat:{type:'custom', formatter:(v: number)=>rp(v)}});
  bm.setData(R.eq.map(([i],k)=>({time:DAYS[i], value:R.bench[k]})));
  cmpSeries.forEach((ser,j) => { const ln = eqc.addSeries(L.LineSeries, {color:CMP_COLORS[j], lineWidth:1.5 as L.LineWidth, lineStyle:2, priceLineVisible:false, priceFormat:{type:'custom', formatter:(v: number)=>rp(v)}}); ln.setData(R.eq.map(([i],k)=>pt(DAYS[i], ser[k]))) });
  const se = eqc.addSeries(L.AreaSeries, {lineColor:PAL.navy, topColor:`rgba(${PAL.navyRgb},.16)`, bottomColor:`rgba(${PAL.navyRgb},0)`, lineWidth:2, priceLineVisible:false, priceFormat:{type:'custom', formatter:(v: number)=>rp(v)}});
  se.setData(R.eq.map(([i,v])=>({time:DAYS[i], value:v})));
  const dd = eqc.addSeries(L.AreaSeries, {lineColor:PAL.dn, topColor:`rgba(${PAL.dnRgb},0)`, bottomColor:`rgba(${PAL.dnRgb},.30)`, lineWidth:1, priceLineVisible:false, invertFilledArea:true, priceFormat:{type:'custom', formatter:(v: number)=>nf(v*100,1)+'%'}}, 1);
  dd.setData(R.eq.map(([i],k)=>({time:DAYS[i], value:R.st.dd[k]})));
  eqc.panes()[1].setHeight(90); eqc.timeScale().fitContent();
  // hover legend: what the equity curve is for = how the strategy stands vs the benchmark on any date
  const kOf = new Map(R.eq.map(([i],k) => [DAYS[i], k]));
  const eqLeg = (k: number) => { const v = R.vals[k], b = R.bench[k], sr = v/R.cap0-1, br = b/R.cap0-1;
    $('eqLeg').innerHTML = `<b>${esc(fmtD(DAYS[R.eq[k][0]]))}</b>${R.oos && k>=R.cut ? '<span class="pill warn">Out-of-sample</span>' : ''}<span>Strategy <b>${rp(v)}</b> <em class="${cls(sr)}">${pct(sr)}</em></span><span>${primaryBenchLabel()} <b>${rp(b)}</b> <em class="${cls(br)}">${pct(br)}</em></span>${cmpSeries.map((ser,j)=>{ const r = ser[k]/R.cap0-1; return `<span><i class="lgd" style="background:${CMP_COLORS[j]}"></i>${esc(S.cmp[j])} <em class="${cls(r)}">${pct(r)}</em></span>` }).join('')}<span>Excess <b class="${cls(sr-br)}">${(sr-br>=0?'+':'')+nf((sr-br)*100,1)} pp</b></span><span>Drawdown <b class="down">${pct(R.st.dd[k],1)}</b></span>` };
  eqLeg(R.eq.length-1);
  eqc.subscribeCrosshairMove(p => { const k = p.time ? kOf.get(p.time as string) : undefined; eqLeg(k==null ? R.eq.length-1 : k) });
  // monthly heatmap
  const m: Record<string, { s: number; e: number; bs: number; be: number }> = {}; R.eq.forEach(([i,v],k) => { const ym = DAYS[i].slice(0,7); const o = (m[ym] ||= {s:k?R.eq[k-1][1]:v, e:v, bs:k?R.bench[k-1]:R.bench[0], be:R.bench[k]}); o.e = v; o.be = R.bench[k] });
  const years = [...new Set(Object.keys(m).map(k=>k.slice(0,4)))];
  const col = (v: number) => v==null?'transparent':v>=0?`rgba(${PAL.upRgb},${Math.min(.85,.12+v*6)})`:`rgba(${PAL.dnRgb},${Math.min(.85,.12-v*6)})`;
  $('heat').innerHTML = `<table class="heat"><tr><th></th>${['J','F','M','A','M','J','J','A','S','O','N','D'].map(x=>`<th>${x}</th>`).join('')}<th>Year</th></tr>${years.map(y=>{ let yr=1; const ms: [string, number][]=[]; const cells = Array.from({length:12},(_,k)=>{ const e = m[`${y}-${String(k+1).padStart(2,'0')}`]; if(!e) return '<td></td>'; const r = e.e/e.s-1, br = e.be/e.bs-1; yr *= 1+r; ms.push([MONTHS[k], r]); return `<td style="background:${col(r)}" ${TT(ttH(`${MONTHS[k]} ${esc(y)}`, [['Strategy', pct(r,2), cls(r)], ['Benchmark', pct(br,2), cls(br)], ['Excess', (r-br>=0?'+':'')+nf((r-br)*100,1)+' pp', cls(r-br)], ['Year to date', pct(yr-1,1), cls(yr-1)]]))}>${nf(r*100,1)}</td>` }).join('');
    const ys = Object.keys(m).filter(k=>k.startsWith(y)), b0 = m[ys[0]].bs, b1 = m[ys.at(-1)].be, by = b1/b0-1, best = ms.reduce((a,b)=>b[1]>a[1]?b:a, ms[0]), worst = ms.reduce((a,b)=>b[1]<a[1]?b:a, ms[0]), up = ms.filter(x=>x[1]>0).length;
    return `<tr><td class="y">${esc(y)}</td>${cells}<td class="tot ${cls(yr-1)}" ${TT(ttH(`${esc(y)} total`, [['Strategy', pct(yr-1,1), cls(yr-1)], ['Benchmark', pct(by,1), cls(by)], ['Excess', (yr-1-by>=0?'+':'')+nf((yr-1-by)*100,1)+' pp', cls(yr-1-by)], ['Best month', `${best[0]} ${pct(best[1],1)}`, 'up'], ['Worst month', `${worst[0]} ${pct(worst[1],1)}`, 'down'], ['Positive months', `${up} of ${ms.length}`]]))}>${nf(Math.round((yr-1)*1000)/10,1)}</td></tr>` }).join('')}</table>`;
  const ann = years.map(y => { const ks = R.eq.map((e,k)=>[e,k] as [[number, number], number]).filter(([e])=>DAYS[e[0]].startsWith(y)); const a = ks[0][1], b = ks.at(-1)[1]; const s0 = a? R.vals[a-1] : R.vals[0], b0 = a? R.bench[a-1] : R.bench[0]; let pk = s0, mdd = 0; for(let k=a;k<=b;k++){ pk = Math.max(pk, R.vals[k]); mdd = Math.min(mdd, R.vals[k]/pk-1) }
    const v = R.vals[b]/s0-1, bb = R.bench[b]/b0-1, tr = R.trades.filter(t=>DAYS[t.xi].startsWith(y));
    const cx = cmpSeries.map(ser => ser[b]/(a? ser[a-1] : ser[0])-1);
    return {l:y.slice(2), v, b:bb, c0:cx[0], c1:cx[1], tt:ttH(esc(y), [['Strategy', pct(v,1), cls(v)], [primaryBenchLabel(), pct(bb,1), cls(bb)], ...cx.map((r,j)=>[esc(S.cmp[j]), pct(r,1), cls(r)] as [string, string, string]), ['Excess', (v-bb>=0?'+':'')+nf((v-bb)*100,1)+' pp', cls(v-bb)], ['Max drawdown in year', pct(mdd,1), 'down'], ['Trades closed', tr.length], ['Win rate', tr.length?pctu(tr.filter(t=>t.ret>0).length/tr.length,0):'—']])} });
  $('annual').innerHTML = bars(ann, {series:[['v',PAL.navy],['b','#c4c4c4'], ...S.cmp.map((k,j)=>['c'+j, CMP_COLORS[j]] as [string, string])]});
};
