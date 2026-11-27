/* The builder (backtest.html section 5 · BUILDER UI): steps 1-5, condition cards, the add menu, templates, step
   navigation, the strategy summary and the rail; and the two middle views with their view bar. The markup is the
   reference's; ticker, broker and date options come from the catalog instead of the synthetic lists, so every catalog
   string goes into the markup through esc(). In portfolio mode step 1 has the stock picker (picker.ts, PF7) where the
   reference has its Universe select: the picker is a card of its own, the reference's first row keeps its Max positions
   and its second row (Rank candidates by, Min. avg value) is the reference's (review PG-4). */
import type { Card } from './api/types.ts';
import { BROKER_CODES, CAT, STOCKS, catalogReady } from './env.ts';
import { $, COLORS, esc, fmtD, fmtMoney, ico, nf, num, OPS, parseMoney, pct, rp, cls, toast } from './format.ts';
import { CAT_LABEL, CATALOG, catOf, condReady, LEVEL_LINES, opLabel, REG, REG_BY, regReady, sideLbl, switchedOn, withinLimit } from './reg.ts';
import { edits, EXIT_TEMPLATES, mkCond, S, TEMPLATES } from './state.ts';
import { condName, drawLanes, getLastSig, inRange, refreshSignals } from './signals.ts';
import { BX, setExpanded, setPanel } from './layout.ts';
import { renderResults, renderTab } from './results/index.ts';
import { condWinCount, openCondWin } from './condwin.ts';
import { renderHeader } from './header.ts';
import { SC, entryOf, refusalOf, testName } from './grammar.ts';
import { abortRun } from './run.ts';
import { bindPicker, pickerHtml } from './picker.ts';
import { stocksText, tickersLabel } from './picked.ts';
import { tap } from '../../shared/touch-words.ts';   // UD81: touch words on a touch screen

/* =====================================================================
   5 · BUILDER UI
   ===================================================================== */
/** the add box's label: the real number of rows the condition window offers (decision 2a: the design said 53) */
const searchLabel = () => { const n = condWinCount(); return n ? `Search ${n} indicators to add` : 'Search indicators to add' };
const numF = (l: string, k: string, v: number, step: number) => `<label class="fld"><span>${l}</span><input class="inp" type="number" step="${step}" data-k="${k}" value="${v}"></label>`;
const lineF = (l: string, k: string, ref: { id: string; o: string }) => `<label class="fld full"><span>${l}</span><select class="sel" data-line="${k}">${LEVEL_LINES().map(x=>`<option value="${x.id}:${x.o}" ${ref&&ref.id===x.id&&ref.o===x.o?'selected':''}>${esc(x.label)}${x.ready?'':' — not calculated'}</option>`).join('')}</select></label>`;
const exitBlock = (n: string, title: string, help: string, modeKey: string | null, modes: [string, string][] | null, fields: string) => { const cur = modeKey ? modeKey.split('.').reduce((o: any,k)=>o[k], S) : null,
    on = modeKey ? cur!=='none' : n==='4' ? S.exit.hold>0 : true;
  return `<div class="exb ${on?'':'is-off'}"><div class="exb-h"><span class="exn">${n}</span><div><b>${title}</b><small>${help}</small></div><span class="pill ${on?'pos':''}">${on?'On':'Off'}</span></div>${modes?`<div class="seg exseg" data-mode="${modeKey}">${modes.map(([v,l])=>`<button class="${v===cur?'on':''}" data-v="${v}">${l}</button>`).join('')}</div>`:''}${fields?`<div class="exf">${fields}</div>`:''}</div>` };
export const renderBuilder = () => {
  const b = $('builder');
  b.innerHTML = `
  <div class="bs ${S.step===1?'on':''}" data-step="1"><div class="stephead"><small>Step 1 of 5</small><h3>Universe & period</h3></div>
    <div class="seg" style="width:100%;margin-bottom:10px" id="modeSeg"><button style="flex:1" class="${S.mode==='single'?'on':''}" data-m="single">Single stock</button><button style="flex:1" class="${S.mode==='portfolio'?'on':''}" data-m="portfolio">Portfolio</button></div>
    ${S.mode==='single' ? `<div class="row"><label class="fld"><span>Ticker</span><select class="sel" data-k="ticker">${tickerOptions()}</select></label><label class="fld"><span>Benchmark</span><select class="sel" data-k="bench"><option value="bh" ${S.bench!=='ihsg'?'selected':''}>Buy & hold</option><option value="ihsg" ${S.bench==='ihsg'?'selected':''}>IHSG</option></select></label></div>`
      : `${pickerHtml()}
         <div class="row"><label class="fld"><span>Max positions</span><input class="inp" type="number" min="1" max="${CAT.limits.max_positions}" data-k="maxPos" value="${S.maxPos}"></label></div>
         <div class="row"><label class="fld"><span>Rank candidates by</span><select class="sel" data-k="rankBy"><option value="adx" ${S.rankBy==='adx'?'selected':''}>Highest ADX</option><option value="fnet" ${S.rankBy==='fnet'?'selected':''}>Biggest foreign net 5D</option><option value="vol" ${S.rankBy==='vol'?'selected':''}>Highest volume ratio</option><option value="rsi" ${S.rankBy==='rsi'?'selected':''}>Lowest RSI</option></select></label><label class="fld"><span>Min. avg value</span><input class="inp" type="number" data-k="cost.minVal" value="${S.cost.minVal}" title="Rp billion per day, 20-day average"></label></div>`}
    <div class="row three"><label class="fld"><span>From</span><input class="inp" type="date" data-k="from" value="${esc(S.from)}" min="${esc(CAT.first_date)}" max="${esc(CAT.data_through)}"></label><label class="fld"><span>To</span><input class="inp" type="date" data-k="to" value="${esc(S.to)}" min="${esc(CAT.first_date)}" max="${esc(CAT.data_through)}"></label><label class="fld"><span>Out-of-sample</span><select class="sel" data-k="oos">${[0,20,30,40].map(v=>`<option value="${v}" ${S.oos==v?'selected':''}>${v?`last ${v}%`:'none'}</option>`).join('')}</select></label></div>
  </div>
  <div class="bs ${S.step===2?'on':''}" data-step="2"><div class="stephead"><small>Step 2 of 5</small><h3>Entry conditions <span class="rt">${S.conds.filter(c=>c.on).length} active</span></h3></div>
    <div class="brule"><div class="bmatch"><span class="ml">Match</span><span class="seg sm" role="radiogroup" aria-label="Entry rule">${([['all','All'],['any','Any'],['n','At least']] as const).map(([v,l])=>`<button type="button" role="radio" aria-checked="${S.logic===v}" class="${S.logic===v?'on':''}" data-blogic="${v}">${l}</button>`).join('')}</span>${S.logic==='n'?`<input class="inp" type="number" min="1" data-k="atLeast" value="${S.atLeast}" aria-label="Minimum number of conditions">`:''}<span>of ${S.conds.filter(c=>c.on).length} active</span></div><div class="bmatch"><span class="ml">Within</span><input class="inp" type="number" min="1" max="20" data-k="window" value="${S.window}" aria-label="Window in bars"><span>bars</span><span class="xinfo" tabindex="0" aria-label="About Within N bars"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v6"/><circle cx="12" cy="16.6" r=".6"/></svg><span class="xinfo-tip" role="tooltip">“Within N bars” lets an event (e.g. a divergence) and a state (e.g. ADX &gt; 25) line up even if they happen a few days apart.</span></span></div></div>
    <div class="adder"><button type="button" class="searchbox adder-open" id="wsOpen" aria-haspopup="dialog" title="Open the conditions workspace">${ico('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>')}<span class="ph">${esc(searchLabel())}</span><span class="sb-go">Browse ${ico('<path d="m9 6 6 6-6 6"/>')}</span></button><button type="button" class="bh-add" id="wsOpen2" aria-haspopup="dialog" title="Add a condition from the workspace" aria-label="Add a condition from the workspace">${ico('<path d="M12 5v14M5 12h14"/>')}</button></div>
    <div class="blk-t">Conditions <small>${S.conds.length} total · ${S.conds.filter(c=>c.on).length} active</small></div>
    <div class="condlist">${S.conds.map((c,i)=>condCard(c,i)).join('')}</div>
    <button class="madd" id="addCond" type="button">${ico('<path d="M12 5v14M5 12h14"/>')}Add condition</button>
    <div class="blk-t">Quick-start templates <small>replaces the conditions below</small></div><div class="tpls">${Object.keys(TEMPLATES).map(k=>`<button data-tpl="${k}" title="Replace the conditions below with the “${k}” template">${ico('<path d="M12 3 3 8l9 5 9-5-9-5zM3 16l9 5 9-5M3 12l9 5 9-5"/>')}<span>${k}</span></button>`).join('')}</div>
  </div>
  <div class="bs ${S.step===3?'on':''}" data-step="3"><div class="stephead"><small>Step 3 of 5</small><h3>Exit rules</h3></div>
    ${exitBlock('1','Stop loss','Closes the trade when price falls to this level. Checked intraday; on a gap the open is used.','exit.stopMode',[['pct','Fixed %'],['atr','ATR ×'],['rr','R:R'],['line','Line'],['none','None']],
      S.exit.stopMode==='pct' ? numF('Stop loss %','exit.sl',S.exit.sl,.5)
      : S.exit.stopMode==='atr' ? numF('ATR length','exit.atrLen',S.exit.atrLen,1)+numF('Multiplier (×)','exit.slAtr',S.exit.slAtr,.5)
      : S.exit.stopMode==='rr' ? numF('Reward : risk (1 : x)','exit.slRR',S.exit.slRR,.5)+`<div class="hint full">${S.exit.tpMode==='r'||S.exit.tpMode==='none' ? '<b>Needs a take profit in % or ATR</b> — the stop is placed from the target distance.' : `Stop = target distance ÷ ${nf(S.exit.slRR,S.exit.slRR%1?1:0)}. With the current target that is about ${S.exit.tpMode==='pct'?nf(S.exit.tp/S.exit.slRR,1)+'% below entry':nf(S.exit.tpAtr/S.exit.slRR,2)+' × ATR below entry'}.`}</div>`
      : S.exit.stopMode==='line' ? lineF('Stop sits on','exit.stopLine',S.exit.stopLine)+'<div class="hint full">Uses the line’s value on the signal day; ignored if the line is above the entry price.</div>' : '')}
    ${exitBlock('2','Take profit','Closes the trade when price reaches the target.','exit.tpMode',[['pct','Fixed %'],['r','R:R'],['atr','ATR ×'],['none','None']],
      S.exit.tpMode==='pct' ? numF('Take profit %','exit.tp',S.exit.tp,.5)
      : S.exit.tpMode==='r' ? numF('Reward : risk (1 : x)','exit.tpR',S.exit.tpR,.5)+`<div class="hint full">Risk = entry − stop. ${S.exit.stopMode==='none'||S.exit.stopMode==='rr'?'<b>Needs a stop loss in %, ATR or Line</b> — the target is placed from the stop distance.':`Target = ${nf(S.exit.tpR,S.exit.tpR%1?1:0)} × the stop distance${S.exit.stopMode==='pct'?` (about +${nf(S.exit.sl*S.exit.tpR,1)}%)`:''}.`}</div>`
      : S.exit.tpMode==='atr' ? numF('ATR length','exit.atrLen',S.exit.atrLen,1)+numF('Multiplier (×)','exit.tpAtr',S.exit.tpAtr,.5) : '')}
    ${exitBlock('3','Trailing stop','Moves up with the trade and never down; uses data up to the previous close.','exit.trailMode',[['none','None'],['pct','% peak'],['chand','Chandelier'],['line','Line']],
      S.exit.trailMode==='pct' ? numF('Trail % below peak close','exit.trail',S.exit.trail,.5)
      : S.exit.trailMode==='chand' ? numF('Lookback / ATR length','exit.chLen',S.exit.chLen,1)+numF('Multiplier (×)','exit.chK',S.exit.chK,.5)+'<div class="hint full">Highest high since entry (within the lookback) minus the multiple of ATR — classic setting 22 and 3. A level above the last close waits until price is above it.</div>'
      : S.exit.trailMode==='line' ? lineF('Trail on','exit.trailLine',S.exit.trailLine) : '')}
    ${exitBlock('4','Time exit','Closes a trade at the close once it reaches the holding limit, or lets it run with no limit.',null,null, `<div class="seg exseg full" role="radiogroup" aria-label="Time exit"><button type="button" role="radio" aria-checked="${S.exit.hold>0}" class="${S.exit.hold>0?'on':''}" data-hold="max">Max holding</button><button type="button" role="radio" aria-checked="${!(S.exit.hold>0)}" class="${S.exit.hold>0?'':'on'}" data-hold="none">No holding limit</button></div>` + (S.exit.hold>0 ? numF('Max holding (days)','exit.hold',S.exit.hold,1) : '<div class="hint full">Trades close only on the stop loss, take profit, trailing stop or exit signals.</div>'))}
    <div class="exb ${S.exitConds.some(c=>c.on)?'':'is-off'}"><div class="exb-h"><span class="exn">5</span><div><b>Exit signals</b><small>Indicator or flow conditions from the same catalog as entry. Checked at the close, sold at the next open.</small></div><span class="pill ${S.exitConds.some(c=>c.on)?'pos':''}">${S.exitConds.some(c=>c.on) ? S.exitConds.filter(c=>c.on).length+' active' : 'Off'}</span></div>
      <div class="bmatch"><span class="ml">Exit when</span><span class="seg sm" role="radiogroup" aria-label="Exit rule">${([['any','Any'],['all','All']] as const).map(([v,l])=>`<button type="button" role="radio" aria-checked="${S.exitLogic===v}" class="${S.exitLogic===v?'on':''}" data-bxlogic="${v}">${l}</button>`).join('')}</span><span>of ${S.exitConds.filter(c=>c.on).length} active is true</span></div>
      <div class="adder"><button type="button" class="searchbox adder-open" data-xopen aria-haspopup="dialog" title="Open the conditions workspace on Exit">${ico('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>')}<span class="ph">Search indicators to add as exit</span></button><button type="button" class="bh-add" data-xopen aria-haspopup="dialog" title="Add an exit condition from the workspace" aria-label="Add an exit condition from the workspace">${ico('<path d="M12 5v14M5 12h14"/>')}</button></div>
      <div class="condlist">${S.exitConds.map((c,i)=>condCard(c,i+3)).join('') || '<div class="exempty">No exit signal. Trades close only on the rules above.</div>'}</div>
      <button class="madd" id="addExit" type="button">${ico('<path d="M12 5v14M5 12h14"/>')}Add exit condition</button>
      <div class="blk-t">Quick-start <small>adds a condition</small></div>
      <div class="tpls">${Object.keys(EXIT_TEMPLATES).map(k=>`<button data-xtpl="${esc(k)}" title="Add “${esc(k)}” as an exit signal">${ico('<path d="M12 5v14M5 12h14"/>')}<span>${esc(k)}</span></button>`).join('')}</div>
    </div>
    <div class="hint">If several rules hit on the same day, the order is: stop loss → trailing stop → take profit → time exit → exit signal (conservative).</div>
  </div>
  <div class="bs ${S.step===4?'on':''}" data-step="4"><div class="stephead"><small>Step 4 of 5</small><h3>Sizing</h3></div>
    <div class="row"><label class="fld"><span>Initial capital (Rp)</span><input class="inp num" type="text" inputmode="numeric" data-k="size.capital" data-fmt="money" value="${fmtMoney(S.size.capital)}"></label><label class="fld"><span>${S.mode==='single'?'Equity per trade %':'Per position'}</span>${S.mode==='single'?`<input class="inp" type="number" data-k="size.alloc" value="${S.size.alloc}">`:`<input class="inp" disabled value="1/${S.maxPos} of equity">`}</label></div>
    <div class="hint">Orders round down to whole lots (100 shares).</div>
  </div>
  <div class="bs ${S.step===5?'on':''}" data-step="5"><div class="stephead"><small>Step 5 of 5</small><h3>Costs & execution</h3></div>
    <div class="row three"><label class="fld"><span>Buy fee %</span><input class="inp" type="number" step="0.01" data-k="cost.buy" value="${S.cost.buy}"></label><label class="fld"><span>Sell fee %</span><input class="inp" type="number" step="0.01" data-k="cost.sell" value="${S.cost.sell}"></label><label class="fld"><span>Slippage %</span><input class="inp" type="number" step="0.01" data-k="cost.slip" value="${S.cost.slip}"></label></div>
    <label style="display:flex;gap:8px;align-items:center;font-size:12px;margin-bottom:8px"><input type="checkbox" data-k="cost.ara" ${S.cost.ara?'checked':''}>Skip entries that open ≥ +20% (ARA, approx.)</label>
    <div class="hint">Signal on the close of day t, order filled at the open of day t+1 — no look-ahead. Sell fee includes the 0.1% sales tax.</div>
  </div>`;
  const STEPS = ['Universe & period','Entry conditions','Exit rules','Sizing','Costs & execution'];
  b.querySelectorAll('.bs').forEach((sec: HTMLElement) => { const n = +sec.dataset.step, nav = document.createElement('div'); nav.className = 'stepnav';
    nav.innerHTML = (n>1?`<button class="btn" data-go="${n-1}">← ${STEPS[n-2]}</button>`:'<span></span>') + (n<5?`<button class="btn" data-go="${n+1}">${STEPS[n]} →</button>`:'<span></span>'); sec.appendChild(nav) });
  b.querySelectorAll('[data-go]').forEach((x: HTMLElement) => x.onclick = () => goStep(+x.dataset.go));
  bindBuilder(); bindPicker(); bindDesign(b); renderNav();
};
const STEP_META = [['Universe','<path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/><circle cx="12" cy="12" r="9"/>'],['Entry','<path d="M5 12h14M13 6l6 6-6 6"/>'],['Exit','<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>'],['Sizing','<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>'],['Costs','<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>']];
export const goStep = (n: number) => { S.step = n; $('builder').querySelectorAll('.bs').forEach((x: HTMLElement) => x.classList.toggle('on', +x.dataset.step===n)); $('builder').scrollTop = 0; renderNav() };
/** the picked stocks as the step summary names them (picked.ts tickersLabel; the view bar's title: portfolioTitle) */
const pickedName = () => S.tickers.length ? tickersLabel(S.tickers) : 'No stock picked';
const stepSummary = (n: number) => {
  const yr = (d: string) => fmtD(d);
  // the picked stocks where the reference names its universe ("Demo 10 · max 5")
  if(n===1) return (S.mode==='single' ? `${S.ticker}` : `${pickedName()} · max ${S.maxPos}`) + ` · ${yr(S.from)} → ${yr(S.to)}` + (S.oos?` · OOS ${S.oos}%`:'');
  if(n===2){ const a = S.conds.filter(c=>c.on&&condReady(c)).length; return a ? `${S.logic==='all'?'ALL':S.logic==='any'?'ANY':'≥ '+Math.min(S.atLeast,a)} of ${a} · within ${S.window} bars` : 'No active condition' }
  if(n===3){ const e = S.exit, p: string[] = [], f = (v: number) => nf(v, v%1?1:0);
    p.push(e.stopMode==='pct'?`SL ${f(e.sl)}%`:e.stopMode==='atr'?`SL ${f(e.slAtr)}×ATR`:e.stopMode==='rr'?`SL at 1:${f(e.slRR)} R:R`:e.stopMode==='line'?`SL on ${REG_BY[e.stopLine.id].key.toUpperCase()}`:'No SL');
    if(e.tpMode!=='none') p.push(e.tpMode==='pct'?`TP ${f(e.tp)}%`:e.tpMode==='r'?`TP 1:${f(e.tpR)} R:R`:`TP ${f(e.tpAtr)}×ATR`);
    if(e.trailMode!=='none') p.push(e.trailMode==='pct'?`Trail ${f(e.trail)}%`:e.trailMode==='chand'?`Chandelier ${e.chLen}/${f(e.chK)}`:`Trail ${REG_BY[e.trailLine.id].key.toUpperCase()}`);
    if(e.hold) p.push(`${e.hold}d`); const xs = S.exitConds.filter(c=>c.on&&condReady(c)).length; if(xs) p.push(`${xs} signal${xs>1?'s':''}`); return p.join(' · ') }
  if(n===4) return `${rp(S.size.capital)} · ${S.mode==='single'?S.size.alloc+'% per trade':'1/'+S.maxPos+' per position'}`;
  return `${nf(S.cost.buy,2)}% / ${nf(S.cost.sell,2)}% · slip ${nf(S.cost.slip,2)}% · next open`;
};
export const renderNav = () => {
  const act = S.conds.filter(c=>c.on&&condReady(c)).length, xact = S.exitConds.filter(c=>c.on&&condReady(c)).length, rail = $('rail');
  // Tahap D (design "Builder v2"): underline tabs with the entry and exit counts; arrow keys, Home and End move between them
  rail.innerHTML = STEP_META.map(([l],k) => { const n = k===1 ? act : k===2 ? xact : null, on = S.step===k+1;
    return `<button type="button" role="tab" id="btab${k+1}" aria-selected="${on}" tabindex="${on?0:-1}" data-st="${k+1}">${l}${n===null?'':`<span class="n">${n}</span>`}</button>` }).join('');
  $('bhSub').textContent = `${S.mode==='single' ? 'Single stock · '+S.ticker : 'Portfolio · max '+S.maxPos} · 5 steps`;
  $('bRailN').textContent = String(act); $('bRailN').title = `${act} active entry condition${act===1?'':'s'}`;
  $('sumbox').innerHTML = `<div class="t"><div class="tt"><b>Strategy summary</b></div></div>${BX()?`<div class="bxhint">Focus mode · ${tap('click outside or press Esc', 'tap outside')} to return to the sidebar</div>`:''}` + STEP_META.map(([l],k) => `<button class="sumrow ${S.step===k+1?'on':''}" data-st="${k+1}"><i>${k+1}</i><b>${l}</b><em>${esc(stepSummary(k+1))}</em></button>`).join('');
  const xb = $('expandBtn');
  xb.innerHTML = BX() ? ico('<path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/>') : ico('<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>');
  xb.title = BX() ? 'Back to sidebar (Esc)' : 'Open the builder in the centre'; xb.setAttribute('aria-label', xb.title);
  rail.querySelectorAll('[data-st]').forEach((x: HTMLElement) => x.onclick = () => goStep(+x.dataset.st));
  rail.onkeydown = (e: KeyboardEvent) => { const d = ({ ArrowRight:1, ArrowLeft:-1 } as Record<string, number>)[e.key] ?? (e.key==='Home' ? -9 : e.key==='End' ? 9 : 0);
    if(!d) return; e.preventDefault(); const n = Math.max(1, Math.min(5, Math.abs(d)===9 ? (d>0?5:1) : S.step+d)); goStep(n); $('btab'+n).focus() };
  document.querySelectorAll<HTMLElement>('#sumbox [data-st]').forEach((x: HTMLElement) => x.onclick = () => goStep(+x.dataset.st));
  $('panelTg').onclick = () => setPanel(false); $('bRail').onclick = () => setPanel(true);
  xb.onclick = () => setExpanded(!BX());
};
/* ---- middle: two views ---- */
export const setView = (v: 'signals' | 'results') => { S.view = v; $('main').classList.toggle('vres', v==='results'); $('vSignals').classList.toggle('on', v==='signals'); $('vResults').classList.toggle('on', v==='results');
  $('viewSeg').querySelectorAll('button').forEach((b: HTMLElement) => b.classList.toggle('on', b.dataset.v===v)); $('main').scrollTop = 0; updateViewbar();
  if(v==='signals') requestAnimationFrame(drawLanes); else if(S.result) requestAnimationFrame(renderTab) };
/* every settings change counts (edits.n), so a run that was started before a change ends as out of date */
export const markStale = () => { edits.n++; if(S.result){ S.stale = true; updateViewbar() } };
export const updateViewbar = () => {
  const R = S.result, lastSig = getLastSig();
  $('vcSig').innerHTML = lastSig ? (() => { let n=0; for(let i=1;i<lastSig.dates.length;i++) if(inRange(lastSig.dates, i) && lastSig.entry[i] && !lastSig.entry[i-1]) n++; return `<b>${n}</b> signals` })() : '';
  $('vcRes').innerHTML = R ? `<b>${R.trades.length}</b> trades` : 'not run';
  // the left header over the chart (header.ts, decision 2a); a portfolio's title is fitted to its column after it
  renderHeader(); if(S.mode==='portfolio') portfolioTitle();
  $('viewCtx').innerHTML = S.view==='results' && R ? `Net <b class="${cls(R.st.tot)}">${pct(R.st.tot)}</b> <i>·</i> Sharpe <b>${num(R.st.sharpe)}</b> <i>·</i> Max DD <b class="down">${pct(R.st.mdd)}</b>` : '';
};
/* The context title of a portfolio, the design's form (the 1:1 reference since 2026-11-15): the picked stocks as the
   step summary names them (up to three tickers, then "+n"), the count and the positions, "BBCA, BBRI, BMRI · 3 stocks ·
   max 5 positions". Review PG-3 shortened it until it took no more lines than backtest.html's title ("Banks · n stocks
   · …"); with the design as the reference it named fewer stocks than the design does (Agent 10, M460 item 5). */
const portfolioTitle = () => {
  const el = $('ctxTitle'), max = `max ${S.maxPos} positions`;
  el.textContent = S.tickers.length ? `${tickersLabel(S.tickers)} · ${stocksText(S.tickers.length)} · ${max}` : `No stock picked · ${max}`;
};
export const bindViewSeg = () => { $('viewSeg').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-v]') as HTMLElement; if(b) setView(b.dataset.v as 'signals' | 'results') } };
/* a flow card without published broker data: the reference's "not calculated" pill with the catalog's reason */
const flowNote = (c: Card) => `<span class="pill warn">${esc(CAT.flow.reason || 'Not calculated')}</span> ignored on Run`;
/** the cards whose fields are open (design: compact cards that expand on click) */
const opened = new Set<string>();
export const condCard = (c: Card, i: number) => {
  const C = catOf(c), col = COLORS[i % COLORS.length], x = opened.has(c.id);
  const open = `<div class="cond mc ${c.on?'':'off'} ${x?'x':''}" data-id="${c.id}" data-card="${c.id}" tabindex="0" role="group" aria-expanded="${x}" aria-label="${esc(C.label)}, press Enter to ${x?'close':'edit'}" title="${x?'':tap('Click', 'Tap')+' to edit'}">`;
  const head = (tag: string) => `<div class="cond-h"><span class="dot" style="background:${col}"></span><b>${esc(C.label)}</b>${tag}<label class="sw" title="Enable / disable"><input type="checkbox" data-c="${c.id}" data-p="on" ${c.on?'checked':''} aria-label="Enable condition"><span></span></label><button class="x" type="button" data-del="${c.id}" title="Remove" aria-label="Remove condition">${ico('<path d="M6 6l12 12M18 6 6 18"/>')}</button></div><div class="msum">${esc(condName(c))}</div>`;
  // Stage D (D5): a test card (the shared grammar, computed by the worker): its rule in the Screener's words, edited in
  // the condition window; why it cannot run, from the engine and the catalogs (grammar.ts refusalOf)
  if(c.type==='test'){ const e = entryOf(c), why = !e ? (SC.state === 'ready' ? 'Not in the catalog of this account.' : 'Loading the catalog…') : refusalOf(e);
    return open + head(`<span class="tag ${C.group}">${C.group==='tech'?'Technical':C.group==='flow'?'Flow':'Price'}</span>`) + `<span class="cf-stat" id="cf-${c.id}"></span><div class="cond-b"><div class="regrule">${esc(testName(c))}</div>
    <div class="cond-f"><span>${why ? `<span class="pill warn">Not in backtest</span> ${esc(why)}` : esc(C.desc)}</span><button class="btn sm" data-ws="${c.id}">Edit in workspace</button></div></div></div>` }
  if(c.type==='reg') return open + head(`<span class="tag tech">${esc(CAT_LABEL[REG_BY[c.ind].cat]||REG_BY[c.ind].cat)}</span>`) + `<span class="cf-stat" id="cf-${c.id}" hidden></span><div class="cond-b"><div class="regrule">${esc(sideLbl(REG_BY[c.ind],c.lhs))} <b>${OPS[c.op]}</b> ${esc(sideLbl(REG_BY[c.ind],c.rhs))}</div><div class="regpar">${REG_BY[c.ind].p.filter(x=>x.t!=='fixed').map(x=>`<span>${esc(x.l)} <b>${esc(String(c.p[x.k]))}</b></span>`).join('')}</div>
    <div class="cond-f"><span>${regReady(c.ind)?esc(C.desc):'<span class="pill warn">Not calculated</span> ignored on Run'}</span><button class="btn sm" data-ws="${c.id}">Edit in workspace</button></div></div></div>`;
  const lc = c as any;
  const params = C.params.map(([k,l]) => k==='broker' ? `<label class="fld"><span>${l}</span><select class="sel inp sm" data-c="${c.id}" data-p="${k}">${brokerOptions(lc[k])}</select></label>` : `<label class="fld"><span>${l}</span><input class="inp sm" type="number" step="${k==='k'?0.5:1}" data-c="${c.id}" data-p="${k}" value="${lc[k]}"></label>`).join('');
  const op = `<label class="fld op"><span>Condition</span><select class="sel inp sm" data-c="${c.id}" data-p="op">${C.ops.map(o=>`<option value="${o}" ${o===lc.op?'selected':''}>${opLabel(c,o)}</option>`).join('')}</select></label>`;
  const val = C.noVal ? '' : `<label class="fld"><span>Value${C.unit?` (${C.unit})`:''}</span><input class="inp sm" type="number" step="${C.unit==='×'?0.1:1}" data-c="${c.id}" data-p="val" value="${lc.val}"></label>`;
  return open + head(`<span class="tag ${C.group}">${C.group==='tech'?'Technical':C.group==='flow'?'Flow':'Price'}</span>`) + `<span class="cf-stat" id="cf-${c.id}"></span><div class="cond-b">${C.params.length?`<div class="cg cg-p">${params}</div>`:''}<div class="cg cg-op ${C.noVal?'nv':''}">${op}${val}</div><div class="cond-f"><span>${condReady(c)?C.desc:flowNote(c)}</span></div></div></div>`;
};
/** the design's controls of steps 2 and 3: the Match and Exit-when choices, the add boxes, the time exit choice and the
    compact cards (bxp) */
const bindDesign = (b: HTMLElement) => {
  b.querySelectorAll<HTMLElement>('[data-blogic]').forEach((x: HTMLElement) => x.onclick = () => { if(S.logic!==x.dataset.blogic){ S.logic = x.dataset.blogic as typeof S.logic; markStale(); renderBuilder(); refreshSignals() } });
  b.querySelectorAll<HTMLElement>('[data-bxlogic]').forEach((x: HTMLElement) => x.onclick = () => { if(S.exitLogic!==x.dataset.bxlogic){ S.exitLogic = x.dataset.bxlogic as typeof S.exitLogic; markStale(); renderBuilder(); refreshSignals() } });
  b.querySelectorAll<HTMLElement>('#wsOpen2').forEach((x: HTMLElement) => x.onclick = () => openCondWin(null, 'entry'));
  b.querySelectorAll<HTMLElement>('[data-xopen]').forEach((x: HTMLElement) => x.onclick = () => openCondWin(null, 'exit'));
  b.querySelectorAll<HTMLElement>('[data-hold]').forEach((x: HTMLElement) => x.onclick = () => { const on = x.dataset.hold==='max';
    if(on===(S.exit.hold>0)) return;
    if(on) S.exit.hold = S.exit.holdKeep || 20; else { S.exit.holdKeep = S.exit.hold; S.exit.hold = 0 }
    markStale(); renderBuilder(); refreshSignals() });
  b.querySelectorAll<HTMLElement>('.cond[data-card]').forEach((el: HTMLElement) => {
    const flip = () => { const id = el.dataset.card!, x = !opened.has(id); if(x) opened.add(id); else opened.delete(id); el.classList.toggle('x', x); el.setAttribute('aria-expanded', String(x)); el.title = x ? '' : tap('Click', 'Tap') + ' to edit' };
    el.onclick = (e: MouseEvent) => { if(!(e.target as HTMLElement).closest('input,select,textarea,button,label,a,.cond-b')) flip() };
    el.onkeydown = (e: KeyboardEvent) => { if(e.target===el && (e.key==='Enter' || e.key===' ')){ e.preventDefault(); flip() } };
  });
};
/* EXEC-BACKTEST-LOAD (user 2026-10-27: "user klik dulu ticker, kemudian ada tulisan loading ticker"): before the catalog
   answers, a list the catalog fills shows the current choice and a line saying it is loading */
const LOADING = (what: string) => `<option disabled>Loading ${what}…</option>`;
const tickerOptions = () => catalogReady() ? STOCKS().map(t=>`<option ${t===S.ticker?'selected':''}>${esc(t)}</option>`).join('')
  : `<option selected>${esc(S.ticker)}</option>${LOADING('tickers')}`;
const brokerOptions = (cur: string) => catalogReady() ? BROKER_CODES().map(b=>`<option ${b===cur?'selected':''}>${esc(b)}</option>`).join('')
  : `<option selected>${esc(cur)}</option>${LOADING('brokers')}`;
const setPath = (path: string, v: unknown) => { const ks = path.split('.'); let o: any = S; ks.slice(0,-1).forEach(k=>o=o[k]); o[ks.at(-1)] = v };
const bindBuilder = () => {
  const b = $('builder');
  b.querySelectorAll('[data-fmt="money"]').forEach((el: HTMLInputElement) => el.oninput = () => { const v = parseMoney(el.value); el.value = v ? fmtMoney(v) : '' });
  b.querySelectorAll('[data-k]').forEach((el: HTMLInputElement) => el.onchange = () => {
    const k = el.dataset.k; let v: any = el.type==='checkbox' ? el.checked : el.type==='number' ? +el.value : el.dataset.fmt==='money' ? parseMoney(el.value) : el.value;
    if(el.dataset.fmt==='money') el.value = fmtMoney(v);
    if(k==='oos') v = +v;
    setPath(k, v);
    if(k==='ticker'){ S.sigTicker = v }
    if(['logic','ticker','maxPos'].includes(k)) renderBuilder();
    markStale(); refreshSignals();
  });
  b.querySelector('#modeSeg').onclick = (e: MouseEvent) => { const x = (e.target as HTMLElement).closest('[data-m]') as HTMLElement; if(!x) return; abortRun(); S.mode = x.dataset.m as 'single' | 'portfolio'; if(S.mode==='single') S.sigTicker = S.ticker; renderBuilder(); refreshSignals(); S.result=null; renderResults() };
  b.querySelectorAll('[data-mode]').forEach((sg: HTMLElement) => sg.onclick = (e: MouseEvent) => { const x = (e.target as HTMLElement).closest('[data-v]') as HTMLElement; if(!x) return; setPath(sg.dataset.mode, x.dataset.v); markStale(); renderBuilder(); refreshSignals() });
  b.querySelectorAll('[data-line]').forEach((el: HTMLSelectElement) => el.onchange = () => { const [id,o] = el.value.split(':'); setPath(el.dataset.line, {id, o}); markStale(); refreshSignals(); renderNav() });
  b.querySelectorAll('[data-xtpl]').forEach((x: HTMLElement) => x.onclick = () => { const add = EXIT_TEMPLATES[x.dataset.xtpl](); if(!withinLimit(S.exitConds, [...S.exitConds, ...add])) return; S.exitConds.push(...add); markStale(); renderBuilder(); refreshSignals(); toast(`Exit signal “${x.dataset.xtpl}” added`) });
  const ax = b.querySelector('#addExit'); if(ax) ax.onclick = () => openCondWin(null, 'exit');
  b.querySelectorAll('[data-c]').forEach((el: HTMLInputElement) => el.onchange = () => { const c: any = [...S.conds, ...S.exitConds].find(x=>x.id===el.dataset.c), p = el.dataset.p;
    if(p==='on' && el.checked){ const list = S.conds.includes(c) ? S.conds : S.exitConds; if(!withinLimit(list, switchedOn(list, c))){ el.checked = false; return } }
    c[p] = p==='on' ? el.checked : (p==='op'||p==='broker') ? el.value : +el.value; if(p==='on') el.closest('.cond').classList.toggle('off', !el.checked); markStale(); refreshSignals() });
  $('wsOpen').onclick = () => openCondWin(null, 'entry');
  b.querySelectorAll('[data-ws]').forEach((x: HTMLElement) => x.onclick = () => openCondWin({kind:'cond', id:x.dataset.ws}, S.exitConds.some(c=>c.id===x.dataset.ws)?'exit':'entry'));
  b.querySelectorAll('[data-del]').forEach((x: HTMLElement) => x.onclick = () => { S.exitConds = S.exitConds.filter(c=>c.id!==x.dataset.del); S.conds = S.conds.filter(c=>c.id!==x.dataset.del); markStale(); renderBuilder(); refreshSignals() });
  b.querySelectorAll('[data-tpl]').forEach((x: HTMLElement) => x.onclick = () => { const cards = TEMPLATES[x.dataset.tpl](); if(!withinLimit(S.conds, cards)) return; S.conds = cards; markStale(); renderBuilder(); refreshSignals(); toast(`Template “${x.dataset.tpl}” loaded`) });
  $('addCond').onclick = (e: MouseEvent) => { const m = $('menu'), r = (e.currentTarget as HTMLElement).getBoundingClientRect(); const groups = [['tech','Technical'],['flow','Flow & bandarmology'],['price','Price action']];
    m.innerHTML = groups.map(([g,l])=>`<div class="hd">${l}</div>`+Object.entries(CATALOG).filter(([,c])=>c.group===g).map(([k,c])=>`<button data-add="${k}">${c.label}<small>${c.desc}</small></button>`).join('')).join('');
    m.hidden = false; m.style.left = r.left+'px'; m.style.top = Math.max(8, Math.min(innerHeight-430, r.bottom+6))+'px';
    m.onclick = (ev: MouseEvent) => { const a = (ev.target as HTMLElement).closest('[data-add]') as HTMLElement; if(!a) return; m.hidden = true; const c = mkCond(a.dataset.add); if(!withinLimit(S.conds, [...S.conds, c])) return; S.conds.push(c); markStale(); renderBuilder(); refreshSignals(); $('builder').scrollTop = $('builder').scrollHeight } };
};
export const bindMenuClose = () => document.addEventListener('pointerdown', e => { const t = e.target as HTMLElement; if(!t.closest('#menu') && !t.closest('#addCond')) $('menu').hidden = true });
