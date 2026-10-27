/* ---- Risk & ratios table (All / IS / OOS / Benchmark) and the five deepest drawdowns (backtest.html section 11) ---- */
import { esc, num, pct, pctu } from '../format.ts';
import { S } from '../state.ts';
import type { PageResult } from '../api/adapt.ts';
import { DAYS } from './svg.ts';
import { TIPS } from './index.ts';

export const tabRisk = (el: HTMLElement) => {
  const R = S.result, cols: [string, any][] = [['Strategy',R.st],['In-sample',R.ins],['Out-of-sample',R.oos],['Benchmark',R.bst]];
  const g = (title: string, rows: [string, (s: any) => string][]) => `<tr class="grp"><td colspan="5">${title}</td></tr>` + rows.map(([l,f])=>`<tr><td ${TIPS[l]?`data-tip="${esc(TIPS[l])}"`:''}>${l}</td>${cols.map(([,s])=>`<td>${s?f(s):'—'}</td>`).join('')}</tr>`).join('');
  el.innerHTML = `<div class="grid2" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)"><div class="panel"><h4>Risk-adjusted performance</h4><div class="sub">Daily series, annualised with 252 trading days · rf = 0</div><table class="mt"><thead><tr><th></th>${cols.map(c=>`<th>${c[0]}</th>`).join('')}</tr></thead><tbody>
    ${g('Return',[['Total return',s=>pct(s.tot)],['CAGR',s=>pct(s.cagr)],['Best day',s=>pct(s.best,2)],['Worst day',s=>pct(s.worst,2)],['Positive days',s=>pctu(s.pos,0)]])}
    ${g('Risk',[['Volatility (ann.)',s=>pctu(s.vol)],['Max drawdown',s=>pct(s.mdd)],['Longest drawdown',s=>s.maxDur+' days'],['Ulcer index',s=>pctu(s.ulcer,2)],['VaR 95% (1D)',s=>pct(s.var95,2)],['CVaR 95% (1D)',s=>pct(s.cvar95,2)],['Skew',s=>num(s.skew)],['Kurtosis',s=>num(s.kurt)]])}
    ${g('Ratios',[['Sharpe',s=>num(s.sharpe)],['Sortino',s=>num(s.sortino)],['Calmar',s=>num(s.calmar)],['PSR',s=>pctu(s.psr(0),0)]])}
    ${g('Versus benchmark',[['Beta',s=>s.beta==null?'—':num(s.beta)],['Alpha (ann.)',s=>s.alpha==null?'—':pct(s.alpha)],['Correlation',s=>s.corr==null?'—':num(s.corr)]])}
    </tbody></table></div>
    <div class="panel"><h4>Drawdown periods</h4><div class="sub">Five deepest peak-to-trough declines</div>${ddTable(R)}</div></div>`;
};
const ddTable = (R: PageResult) => { const v = R.vals, out: { s: number; t: number; e: number | null; d: number }[] = []; let pk = 0, inDD = false, st = 0, trough = 0;
  for(let k=1;k<v.length;k++){ if(v[k]>=v[pk]){ if(inDD){ out.push({s:st, t:trough, e:k, d:v[trough]/v[st]-1}); inDD=false } pk = k } else { if(!inDD){ inDD = true; st = pk; trough = k } if(v[k]<v[trough]) trough = k } }
  if(inDD) out.push({s:st, t:trough, e:null, d:v[trough]/v[st]-1});
  out.sort((a,b)=>a.d-b.d);
  return `<table class="mt"><thead><tr><th>Peak</th><th>Trough</th><th>Recovered</th><th>Depth</th><th>Days</th></tr></thead><tbody>${out.slice(0,5).map(d=>`<tr><td>${esc(DAYS[R.eq[d.s][0]])}</td><td>${esc(DAYS[R.eq[d.t][0]])}</td><td>${d.e!=null?esc(DAYS[R.eq[d.e][0]]):'<span class="pill warn">Not yet</span>'}</td><td class="down">${pct(d.d)}</td><td>${(d.e??R.eq.length-1)-d.s}</td></tr>`).join('')}</tbody></table>` };
