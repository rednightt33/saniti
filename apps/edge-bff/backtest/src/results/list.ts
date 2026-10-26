/* ---- Trade list and the CSV export, generated in the browser from the result's trades (backtest.html section 11) ---- */
import { cls, nf, pct, rp, toast } from '../format.ts';
import { S } from '../state.ts';
import { DAYS } from './svg.ts';

let sortKey = 'ei', sortDir = 1;
export const tabList = (el: HTMLElement) => {
  const T = [...S.result.trades].sort((a: any,b: any)=>(a[sortKey]>b[sortKey]?1:-1)*sortDir);
  const cols = [['tk','Ticker','l'],['ei','Entry date','l'],['entry','Entry'],['xi','Exit date','l'],['exit','Exit'],['sh','Lots'],['bars','Days'],['ret','Return'],['pnl','P&L'],['mae','MAE'],['mfe','MFE'],['why','Exit reason','l']];
  el.innerHTML = `<div class="trwrap"><table class="trtbl"><thead><tr>${cols.map(([k,l,c])=>`<th class="${c||''}" data-s="${k}">${l}${sortKey===k?(sortDir>0?' ↑':' ↓'):''}</th>`).join('')}</tr></thead><tbody>${T.map(t=>`<tr><td class="l"><b>${t.tk}</b></td><td class="l">${DAYS[t.ei]}</td><td>${nf(t.entry,0)}</td><td class="l">${DAYS[t.xi]}</td><td>${nf(t.exit,0)}</td><td>${nf(t.sh/100,0)}</td><td>${t.bars}</td><td class="${cls(t.ret)}">${pct(t.ret,2)}</td><td class="${cls(t.pnl)}">${rp(t.pnl)}</td><td class="down">${pct(t.mae,1)}</td><td class="up">${pct(t.mfe,1)}</td><td class="l">${t.why}</td></tr>`).join('')}</tbody></table></div><div class="note">Click a column to sort. Prices include slippage; returns include buy/sell fees.</div>`;
  el.querySelectorAll<HTMLElement>('[data-s]').forEach((th: HTMLElement) => th.onclick = () => { if(sortKey===th.dataset.s) sortDir *= -1; else { sortKey = th.dataset.s; sortDir = 1 } tabList(el) });
};
export const exportCsv = () => { const T = S.result.trades, rows = [['ticker','entry_date','entry_price','exit_date','exit_price','shares','days','return','pnl','mae','mfe','exit_reason']].concat(T.map(t=>[t.tk,DAYS[t.ei],t.entry.toFixed(2),DAYS[t.xi],t.exit.toFixed(2),t.sh,t.bars,t.ret.toFixed(5),Math.round(t.pnl),t.mae.toFixed(4),t.mfe.toFixed(4),t.why] as any[]));
  const blob = new Blob([rows.map(r=>r.join(',')).join('\n')], {type:'text/csv'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'backtest_trades.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href), 1000); toast('CSV downloaded') };
