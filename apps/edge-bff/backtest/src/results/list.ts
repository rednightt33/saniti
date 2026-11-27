/* ---- Trade list and the CSV export, generated in the browser from the result's trades (backtest.html section 11) ---- */
import { cls, esc, nf, pct, rp, toast } from '../format.ts';
import { S } from '../state.ts';
import { DAYS } from './svg.ts';
import type { PageTrade } from '../api/adapt.ts';
import { tap } from '../../../shared/touch-words.ts';   // UD81: touch words on a touch screen

/* EXEC-PRICE-DISTORTION (user 2026-11-24, UD41 A: "value harus tetap ditampilkan as is dengan badge"): a trade that read
   a distorted value carries a badge beside its ticker; the values are as computed. The words follow the Screener's row
   badges (screener/src/texts.ts remarkBadge) and the run's warnings (PRICE_DISTORTIONS, FLOW_BASIS_CHANGE). */
const DIST_BADGE: Record<PageTrade['dist'][number]['kind'], string> = { flow:'Flow distorted', unadjusted:'Price break', uncertain:'Possible break', anomaly:'Price anomaly' };
const DIST_WHY: Record<PageTrade['dist'][number]['kind'], string> = {
  flow:'a Flow value on the signal day reads broker lots across a corporate action whose broker basis is not settled yet',
  unadjusted:'a split, bonus share or rights issue whose price jump is still in the published history',
  uncertain:'a corporate action too small to measure from the prices, so the history may not be adjusted for it',
  anomaly:'a one-day move beyond 35 % with no corporate action recorded',
};
/** The trade's badges, one per kind, its title naming the dates (empty when it read nothing distorted). */
export function distBadges(t: Pick<PageTrade, 'dist'>): string {
  const by = new Map<string, string[]>();
  for (const d of t.dist) by.set(d.kind, [...(by.get(d.kind) ?? []), d.date]);
  return [...by].map(([k, ds]) => { const kind = k as PageTrade['dist'][number]['kind'];
    return ` <span class="pill warn" title="${esc(`${DIST_BADGE[kind]} on ${ds.join(', ')}: ${DIST_WHY[kind]}. The trade is computed with the values as published.`)}">${esc(DIST_BADGE[kind])}</span>` }).join('');
}

let sortKey = 'ei', sortDir = 1;
export const tabList = (el: HTMLElement) => {
  const T = [...S.result.trades].sort((a: any,b: any)=>(a[sortKey]>b[sortKey]?1:-1)*sortDir);
  const cols = [['tk','Ticker','l'],['ei','Entry date','l'],['entry','Entry'],['xi','Exit date','l'],['exit','Exit'],['sh','Lots'],['bars','Days'],['ret','Return'],['pnl','P&L'],['mae','MAE'],['mfe','MFE'],['why','Exit reason','l']];
  el.innerHTML = `<div class="trwrap"><table class="trtbl"><thead><tr>${cols.map(([k,l,c])=>`<th class="${c||''}" data-s="${k}">${l}${sortKey===k?(sortDir>0?' ↑':' ↓'):''}</th>`).join('')}</tr></thead><tbody>${T.map(t=>`<tr><td class="l"><b>${esc(t.tk)}</b>${distBadges(t)}</td><td class="l">${esc(DAYS[t.ei])}</td><td>${nf(t.entry,0)}</td><td class="l">${esc(DAYS[t.xi])}</td><td>${nf(t.exit,0)}</td><td>${nf(t.sh/100,0)}</td><td>${t.bars}</td><td class="${cls(t.ret)}">${pct(t.ret,2)}</td><td class="${cls(t.pnl)}">${rp(t.pnl)}</td><td class="down">${pct(t.mae,1)}</td><td class="up">${pct(t.mfe,1)}</td><td class="l">${esc(t.why)}</td></tr>`).join('')}</tbody></table></div><div class="note">${tap('Click', 'Tap')} a column to sort. Prices include slippage; returns include buy/sell fees.</div>`;
  el.querySelectorAll<HTMLElement>('[data-s]').forEach((th: HTMLElement) => th.onclick = () => { if(sortKey===th.dataset.s) sortDir *= -1; else { sortKey = th.dataset.s; sortDir = 1 } tabList(el) });
};
export const exportCsv = () => { const T = S.result.trades, rows = [['ticker','entry_date','entry_price','exit_date','exit_price','shares','days','return','pnl','mae','mfe','exit_reason','distortions']].concat(T.map(t=>[t.tk,DAYS[t.ei],t.entry.toFixed(2),DAYS[t.xi],t.exit.toFixed(2),t.sh,t.bars,t.ret.toFixed(5),Math.round(t.pnl),t.mae.toFixed(4),t.mfe.toFixed(4),t.why,(t.dist ?? []).map(d=>`${d.kind} ${d.date}`).join('; ')] as any[]));
  const blob = new Blob([rows.map(r=>r.join(',')).join('\n')], {type:'text/csv'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'backtest_trades.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href), 1000); toast('CSV downloaded') };
