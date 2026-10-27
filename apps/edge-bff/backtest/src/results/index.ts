/* RESULTS UI (backtest.html section 11): the results card (KPIs, tabs) and the definitions shown on hover. The numbers
   are the server's (the result adapter maps them to the reference's names); the renderers are the reference's. */
import { $, cls, esc, fmtD, ico, nf, num, pct, pctu, rp } from '../format.ts';
import { S } from '../state.ts';
import { universe } from '../signals.ts';
import { stocksText } from '../picked.ts';
import { DAYS, mean, setDays } from './svg.ts';
import { tabOverview } from './overview.ts';
import { tabReturns } from './returns.ts';
import { tabTrades } from './trades.ts';
import { tabRisk } from './risk.ts';
import { tabRobust } from './robust.ts';
import { exportCsv, tabList } from './list.ts';

export const TIPS: Record<string, string> = {
  'Sharpe':'Annualised mean daily return ÷ its volatility (rf = 0).', 'Sortino':'Like Sharpe, but only downside volatility counts.', 'Calmar':'CAGR ÷ |max drawdown|.',
  'Profit factor':'Gross profit ÷ gross loss. Above 1.5 is generally solid.', 'Expectancy':'Average return per trade (after costs).', 'SQN':'System Quality Number (Van Tharp): √n × mean(R) ÷ sd(R), n capped at 100. >2 good, >3 excellent.',
  'Payoff ratio':'Average win ÷ |average loss|.', 'Kelly':'Optimal fraction of capital by the Kelly formula — use a fraction of it in practice.', 'Ulcer index':'Depth and length of drawdowns (RMS of drawdown).',
  'VaR 95% (1D)':'Daily loss exceeded on 5% of days.', 'CVaR 95% (1D)':'Average loss on the worst 5% of days.', 'PSR':'Probabilistic Sharpe Ratio: chance the true Sharpe is above 0, given skew, fat tails and sample length.',
  'Deflated Sharpe':'PSR against the Sharpe you would expect from luck after trying this many variants (Bailey & López de Prado).', 'Exposure':'Share of days with money in the market.',
  'MAE':'Maximum adverse excursion — worst move against the trade before exit.', 'MFE':'Maximum favourable excursion — best move in favour before exit.'
};
export const renderResults = () => {
  const R = S.result, el = $('resCard');
  if(!R){ el.innerHTML = `<div class="card-h"><h2>Backtest results</h2><span class="sub">Set your conditions, check the arrows on the chart, then press <b>Run backtest</b>.</span></div><div class="empty">No results yet.</div>`; return }
  setDays(R.days);
  const st = R.st, ts = R.ts, bst = R.bst;
  const kpi = (l: string, v: string, sub: string, c='') => `<div class="kpi"><span>${l}</span><b class="${c}">${v}</b><small>${sub||''}</small></div>`;
  el.innerHTML = `<div class="card-h"><h2>Backtest results</h2><span class="sub">${S.mode==='single'?esc(S.ticker):`Portfolio · ${stocksText(universe().length)} · max ${S.maxPos} positions`} · ${esc(fmtD(DAYS[R.eq[0][0]]))} – ${esc(fmtD(DAYS[R.eq.at(-1)[0]]))} · ${ts.n} trades</span><span class="sp"></span><button class="btn" id="csvBtn">${ico('<path d="M12 4v12M6 11l6 6 6-6M4 20h16"/>')}Export trades (CSV)</button></div>
  <div class="kpis">${kpi('Net return', pct(st.tot), `Benchmark ${pct(bst.tot)}`, cls(st.tot))}${kpi('CAGR', pct(st.cagr), `Benchmark ${pct(bst.cagr)}`, cls(st.cagr))}${kpi('Max drawdown', pct(st.mdd), `Benchmark ${pct(bst.mdd)}`, 'down')}${kpi('Sharpe', num(st.sharpe), `Benchmark ${num(bst.sharpe)}`)}${kpi('Win rate', pctu(ts.wr,0), `${ts.wins} W · ${ts.losses} L`)}${kpi('Profit factor', ts.pf===Infinity?'∞':num(ts.pf), `Payoff ${num(ts.payoff)}`)}${kpi('Expectancy', pct(ts.exp,2), `per trade · ${rp(ts.expRp)}`, cls(ts.exp))}${kpi('Exposure', pctu(mean(R.expo),0), `Avg hold ${nf(ts.hold,1)} d`)}</div>
  <div class="tabs" id="rtabs">${[['overview','Overview'],['returns','Returns & distribution'],['trades','Trade analysis'],['risk','Risk & ratios'],['robust','Robustness'],['list','Trade list']].map(([k,l])=>`<button class="${S.tab===k?'on':''}" data-tab="${k}">${l}</button>`).join('')}</div>
  <div class="card-b" id="rbody"></div>`;
  $('rtabs').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-tab]') as HTMLElement; if(!b) return; S.tab = b.dataset.tab; $('rtabs').querySelectorAll('button').forEach((x: HTMLElement)=>x.classList.toggle('on',x===b)); renderTab() };
  $('csvBtn').onclick = exportCsv;
  renderTab();
};
export const renderTab = () => { const f = {overview:tabOverview, returns:tabReturns, trades:tabTrades, risk:tabRisk, robust:tabRobust, list:tabList}[S.tab]; $('rbody').innerHTML = ''; f($('rbody')); bindTips() };
export const bindTips = () => document.querySelectorAll<HTMLElement>('[data-tip]').forEach((x: HTMLElement) => { x.onmouseenter = e => { const t=$('tip'); t.textContent = x.dataset.tip; t.hidden=false; const r=x.getBoundingClientRect(); t.style.left=Math.min(innerWidth-310,r.left)+'px'; t.style.top=(r.bottom+6)+'px' }; x.onmouseleave = () => $('tip').hidden = true });
