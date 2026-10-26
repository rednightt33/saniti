/* FLOW TIMELINE — broksum-shaped data layer (reference lines 2127-2470 and 2585-2604).
   Schema (one entry per broker × investor type × market board):
     { broker, investor:'Foreign'|'Domestic', board:'Regular'|'Nego'|'Cash', net: Float64Array(N) }
   Fixture: the reference's synthetic series. Live: the published broker files (bv − sv per session); sessions before
   the first broker date have no rows and count as 0, as in the reference's setBroksumRows. */
import type { Ctx, FilterApi } from './context';
import { $, cls, keyOf, nfCompact, rupiah, spin, store } from './context';

export function initFlow(ctx: Ctx) {
  const { L, chart, ohlc, volume, dates, N, idxByTime, closes } = ctx;
  const BOARDS = ctx.BOARDS = [{id:'Regular',label:'Regular'},{id:'Nego',label:'Nego'},{id:'Cash',label:'Cash (Tunai)'}];
  const INVESTORS = ctx.INVESTORS = [{id:'Foreign',label:'Foreign'},{id:'Domestic',label:'Domestic'}];
  const normBoard = (s: string) => /nego/i.test(s) ? 'Nego' : /cash|tunai/i.test(s) ? 'Cash' : 'Regular';
  const normInvestor = (s: string) => /foreign|asing/i.test(s) ? 'Foreign' : 'Domestic';

  ctx.COMBOS = ctx.M.combos;
  ctx.flowSource = ctx.M.flowSource;

  /* ---- filter state ---- */
  const allBrokers = ctx.allBrokers = () => [...new Set(ctx.COMBOS.map(c=>c.broker))].sort();
  const flt = { brokers:new Set(allBrokers()), boards:new Set(BOARDS.map(b=>b.id)), investors:new Set(['Foreign']) };
  const isDefault = () => flt.brokers.size===allBrokers().length && flt.boards.size===BOARDS.length
    && flt.investors.size===1 && flt.investors.has('Foreign');

  /* ---- flow chart ---- */
  const flowChart = ctx.flowChart = L.createChart($('flowChart'), {
    autoSize:true,
    layout:{ background:{type:L.ColorType.Solid,color:'#fff'}, textColor:'#666666', fontFamily:'Inter,"Segoe UI",sans-serif', attributionLogo:false },
    grid:{ vertLines:{color:'#f2f2f2',style:L.LineStyle.Solid}, horzLines:{color:'#f2f2f2',style:L.LineStyle.Solid} },
    crosshair:{ mode:L.CrosshairMode.Normal,
      vertLine:{color:'#a1a1a1',width:1,style:L.LineStyle.Dashed,labelBackgroundColor:'#171717'},
      horzLine:{color:'#a1a1a1',width:1,style:L.LineStyle.Dashed,labelVisible:false} },
    rightPriceScale:{ visible:true, borderColor:'#eaeaea', ticksVisible:false, scaleMargins:{top:.08,bottom:.08} },
    leftPriceScale:{ visible:true, borderColor:'#eaeaea', ticksVisible:false, scaleMargins:{top:.08,bottom:.08} },
    timeScale:{ borderColor:'#eaeaea', rightOffset:3, barSpacing:7, minBarSpacing:.4, timeVisible:false, secondsVisible:false },
    handleScroll:{ mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:false },
    handleScale:{ axisPressedMouseMove:{time:true,price:true}, axisDoubleClickReset:{time:true,price:true}, mouseWheel:true, pinch:true },
    kineticScroll:{ mouse:true, touch:true },
    localization:{ locale:'en-US' }
  } as any);
  // axis text is padded to a fixed length with figure spaces so every axis label / badge box has the same width
  const axisText = (v: number, n=10) => rupiah(v).padStart(n, ' ');
  // the top BAND px of the plot is reserved for the legend: scale margin keeps data below it, and tick labels that would land inside it are blanked
  const LEGEND_BAND = 44;
  const badgeVals = new Set<number>();                      // current values of the hover badges — these must always keep their text
  const axisTextFor = (get: () => any, v: number, n=10) => {
    try{ const y = get().priceToCoordinate(v); if(y !== null && y < LEGEND_BAND - 2 && !badgeVals.has(v)) return ''.padStart(n, ' ') }catch(e){}
    return axisText(v, n);
  };
  const flowBars: any = flowChart.addSeries(L.HistogramSeries, {
    priceScaleId:'right', priceLineVisible:false, lastValueVisible:false,
    priceFormat:{ type:'custom', formatter:(v: number)=>axisTextFor(()=>flowBars, v, 8), minMove:1 }
  });
  (ctx as any).flowSeries = flowBars;                     // the Flow chart's drawing anchor (C4 prototype)
  const flowCum: any = flowChart.addSeries(L.LineSeries, {
    priceScaleId:'left', color:'#171717', lineWidth:2, priceLineVisible:false, lastValueVisible:false,
    crosshairMarkerRadius:3, priceFormat:{ type:'custom', formatter:(v: number)=>axisTextFor(()=>flowCum, v), minMove:1 }
  });
  let flowNet = new Float64Array(N), flowCumArr = new Float64Array(N);
  const fitTopMargin = () => {
    const h = $('flowChart').clientHeight; if(!h) return;
    const top = Math.min(.5, Math.max(.08, LEGEND_BAND / h));
    ['leftPriceScale','rightPriceScale'].forEach(k => flowChart.applyOptions({ [k]:{ scaleMargins:{ top, bottom:.08 } } }));
  };
  new ResizeObserver(fitTopMargin).observe($('flowChart')); fitTopMargin();
  // left-axis badge follows the hovered bar (falls back to the last bar when the pointer is away)
  const netBadge = flowBars.createPriceLine({ price:0, lineVisible:false, axisLabelVisible:true, axisLabelColor:'#089981', axisLabelTextColor:'#ffffff', title:'' });
  const cumBadge = flowCum.createPriceLine({ price:0, color:'#171717', lineVisible:false, axisLabelVisible:true, axisLabelColor:'#171717', axisLabelTextColor:'#ffffff', title:'' });

  /* EXEC-TERMINAL-UI-1026 U3 (user 2026-10-26: "Period total net dan AVG daily net harusnya menghitung yang di
     terdisplay saja, sama seperti bagian statistics"): the period is the chart's visible range, the daily average
     counts the visible sessions that have broker data (live data before the first broker date has no rows); each
     figure has an info mark that says in one sentence how it is computed */
  let flowFrom = ctx.M.flowFrom, flowTo = N - 1;         // flowTo: the last session with broker rows (C2)
  let flowLoading = !!ctx.M.later;                        // live: the broker files arrive after the first draw
  let flowMore = false;                                   // F5: the recent years are in, the older ones still loading
  const visible = () => {
    const r = chart.timeScale().getVisibleLogicalRange();
    return r ? [Math.max(0, Math.ceil(r.from)), Math.min(N-1, Math.floor(r.to))] : [0, N-1];
  };
  const FLOW_INFO: Record<string, string> = {
    'Latest day net': 'Net value (buy − sell) on the latest session, for the selected brokers, boards and investor type.',
    'Period net total': 'Sum of the daily net value (buy − sell) over the sessions visible on the chart, for the selected filters.',
    'Avg daily net': 'Period net total divided by the number of visible sessions that have broker data.'
  };
  const info = (l: string) => `<span class="flow-info" tabindex="0" role="img" aria-label="${FLOW_INFO[l]}" data-tip="${l}|${FLOW_INFO[l]}"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M8 4.6v4.2"/><circle cx="8" cy="11.2" r=".5"/></svg></span>`;
  const LIVE = ctx.M.mode === 'live';                      // the fixture keeps the reference's whole-series figures (1:1 check)
  const flowSummary = () => {
    /* EXEC-TERMINAL-1026C C2 (user 2026-10-26: "kalau negatif ya di show saja huruf merah. Dengan minus"): live, the latest
       day is the last session with broker rows (the newest price session may not have them yet) and carries its date;
       a negative figure is red with its minus, zero is neutral */
    const [a, b0] = LIVE ? visible() : [0, N-1], b = LIVE ? Math.min(b0, flowTo) : b0, from = Math.max(a, flowFrom);
    let total = 0; for(let i=from;i<=b;i++) total += flowNet[i];
    const lastI = LIVE ? flowTo : N-1, last = lastI >= 0 ? flowNet[lastI] : 0, avg = total/(b - from + 1 > 0 ? b - from + 1 : 1);
    const tone = (v: number) => LIVE ? (v > 0 ? 'up' : v < 0 ? 'down' : 'flat') : (v>=0?'up':'down');
    const day = (l: string) => LIVE && l === 'Latest day net' && lastI >= 0 && lastI < N ? ` <span class="flow-stat-day">${fmtDMY(lastI)}</span>` : '';
    const stat = (l: string, v: number) => `<div class="flow-stat"><span class="flow-stat-label">${l}${day(l)}${LIVE ? info(l) : ''}</span><span class="flow-stat-val ${tone(v)}">${rupiah(v)}</span></div>`;
    $('flowSummary').innerHTML = stat('Latest day net', last) + stat('Period net total', total) + stat('Avg daily net', avg);
  };
  let summaryRaf = 0;
  if(LIVE) chart.timeScale().subscribeVisibleLogicalRangeChange(() => { cancelAnimationFrame(summaryRaf); summaryRaf = requestAnimationFrame(flowSummary) });
  {
    const host = $('flowSummary'), tip = (t: HTMLElement | null, x: number, y: number) => t ? ctx.showStTip(x, y, ctx.tipHtml(t.dataset.tip!)) : ctx.hideStTip();
    host.addEventListener('pointermove', (e: any) => tip(e.target.closest('.flow-info'), e.clientX, e.clientY));
    host.addEventListener('pointerleave', () => ctx.hideStTip());
    host.addEventListener('focusin', (e: any) => { const t = e.target.closest('.flow-info'); if(t){ const r = t.getBoundingClientRect(); tip(t, r.left, r.bottom) } });
    host.addEventListener('focusout', () => ctx.hideStTip());
  }
  const recomputeFlow = () => {
    flowNet = new Float64Array(N);
    let used = 0;
    ctx.COMBOS.forEach(c => {
      if(!flt.brokers.has(c.broker) || !flt.boards.has(c.board) || !flt.investors.has(c.investor)) return;
      used++; for(let i=0;i<N;i++) flowNet[i] += c.net[i];
    });
    let run = 0; flowCumArr = new Float64Array(N);
    for(let i=0;i<N;i++){ run += flowNet[i]; flowCumArr[i] = run }
    flowBars.setData(ohlc.map((b,i)=>({ time:b.time, value:Math.round(flowNet[i]), color: flowNet[i]>=0 ? 'rgba(8,153,129,.9)' : 'rgba(242,54,69,.9)' })));
    flowCum.setData(ohlc.map((b,i)=>({ time:b.time, value:Math.round(flowCumArr[i]) })));
    flowSummary();
    const note = $('flowNote');
    const everything = flt.brokers.size===allBrokers().length && flt.boards.size===BOARDS.length && flt.investors.size===INVESTORS.length;
    note.hidden = !(flowLoading || flowMore || everything || used===0);
    if(flowLoading || flowMore) note.innerHTML = spin(flowLoading ? 'Loading broker data' : 'Loading earlier broker data');
    else note.textContent = used===0 ? 'No flow matches the current filters' : 'All brokers, boards and investor types net to zero by definition';
    showTip(ctx.lastTipIdx);
  };

  /* ---- hover read-out ---- */
  ctx.lastTipIdx = N-1;
  let cumOn = store.get('ml.flow.cum') !== '0';
  const fmtDMY = (i: number) => new Date(dates[i]+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).replace(',', '');   // 28 Nov 2025
  ctx.tipHooks = [];                                       // crosshair listeners (indicator legend values)
  const showTip = (i: number) => {
    ctx.lastTipIdx = i;
    ctx.tipHooks.forEach(fn => fn(i));
    const vb = $('volVal'); if(vb){ vb.textContent = nfCompact.format(volume[i].value); vb.className = ohlc[i].close >= ohlc[i].open ? 'up' : 'down' }
    badgeVals.clear(); badgeVals.add(Math.round(flowCumArr[i])); badgeVals.add(Math.round(flowNet[i]));
    cumBadge.applyOptions({ price: Math.round(flowCumArr[i]), axisLabelVisible: cumOn });
    netBadge.applyOptions({ price: Math.round(flowNet[i]), axisLabelColor: flowNet[i] >= 0 ? '#089981' : '#f23645' });
    $('flowTip').innerHTML = `<b>${fmtDMY(i)}</b> &nbsp; Net <b class="${cls(flowNet[i])}">${rupiah(flowNet[i])}</b>`
      + (cumOn ? ` &nbsp; Cumulative <b>${rupiah(flowCumArr[i])}</b>` : '');
  };

  /* ---- keep the two charts locked: time range, price-scale widths, crosshair ---- */
  let rangeLock = false;
  const pushRange = ctx.pushRange = (from, to) => {
    if(rangeLock) return;
    const r = from.timeScale().getVisibleLogicalRange(); if(!r) return;
    rangeLock = true; try{ to.timeScale().setVisibleLogicalRange(r) } finally { rangeLock = false }
  };
  chart.timeScale().subscribeVisibleLogicalRangeChange(() => pushRange(chart,flowChart));
  flowChart.timeScale().subscribeVisibleLogicalRangeChange(() => pushRange(flowChart,chart));

  // Same left/right axis widths in both charts => identical plot area => bars sit exactly under their candles.
  const axisW: Record<string, number> = { left:112, right:0 };   // 112 = toolbar (41) + breathing room before the price labels
  [chart,flowChart].forEach(c => c.applyOptions({ leftPriceScale:{ minimumWidth:axisW.left } }));
  const syncAxisWidths = ctx.syncAxisWidths = () => {
    (['left','right'] as const).forEach(side => {
      let w = 0;
      try{ w = Math.max(chart.priceScale(side).width(), flowChart.priceScale(side).width()) }catch(e){ return }
      if(w > axisW[side]){
        axisW[side] = w;
        const opt = { [side+'PriceScale']:{ minimumWidth:w } };
        chart.applyOptions(opt); flowChart.applyOptions(opt);
      }
    });
    document.documentElement.style.setProperty('--ax-l', (axisW.left + 8) + 'px'); document.documentElement.style.setProperty('--ax-r', axisW.right + 'px'); document.documentElement.style.setProperty('--lab-l', Math.max(10, axisW.left - 64) + 'px');   // left edge of the Y-axis labels   // overlays (legend, tooltip) sit just right of the left axis
  };
  [chart,flowChart].forEach(c => { c.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(syncAxisWidths)) });

  new ResizeObserver(() => requestAnimationFrame(syncAxisWidths)).observe($('chart'));

  let xhLock = false;
  const mainRef = (i: number): [any, number] => ctx.displayMode === 'return'
    ? [ctx.mainLine, (closes[i]/closes[0]-1)*100]
    : [ctx.chartStyle === 'line' ? ctx.mainLine : ctx.candle, closes[i]];
  chart.subscribeCrosshairMove(p => {
    if(xhLock) return;
    xhLock = true;
    try{
      const k = keyOf(p.time), i = k ? idxByTime.get(k) : undefined;
      if(i === undefined || !p.point || p.point.x < 0){ flowChart.clearCrosshairPosition(); showTip(N-1) }
      else { flowChart.setCrosshairPosition(flowNet[i], p.time as any, flowBars); showTip(i) }
    } finally { xhLock = false }
  });
  flowChart.subscribeCrosshairMove(p => {
    if(xhLock) return;
    xhLock = true;
    try{
      const k = keyOf(p.time), i = k ? idxByTime.get(k) : undefined;
      if(i === undefined || !p.point || p.point.x < 0){ chart.clearCrosshairPosition(); showTip(N-1) }
      else { const [s,v] = mainRef(i); chart.setCrosshairPosition(v, p.time as any, s); showTip(i) }
    } finally { xhLock = false }
  });

  /* ---- filter popovers (multi-select, search, select-all / clear) ---- */
  const openPops = new Set<FilterApi>();
  const closeAll = (except?: FilterApi) => { openPops.forEach(p => { if(p !== except) p.close() }) };
  document.addEventListener('click', e => { if(![...openPops].some(p => p.root.contains(e.target as Node))) closeAll() });
  document.addEventListener('keydown', e => { if(e.key === 'Escape') closeAll() });

  const makeFilter = ctx.makeFilter = (root: HTMLElement, { title, searchable, placeholder, grid, mono, max, getOptions, state, summary, onChange }: any) => {
    root.innerHTML = `<button class="fl-btn" aria-haspopup="true" aria-expanded="false"><span class="fl-k">${title}</span><span class="fl-v"></span><i class="chev"></i></button>
      <div class="fl-pop" hidden>${searchable?`<input class="fl-search" type="search" placeholder="${placeholder||'Search…'}" aria-label="${title} search" autocomplete="off">`:''}
        <div class="fl-actions">${max?'':'<button data-act="all">Select all</button>'}<button data-act="none">Clear</button><span class="fl-count"></span></div>
        <div class="fl-list${grid?' grid':''}" role="group" aria-label="${title}"></div></div>`;
    const btn = root.querySelector('.fl-btn') as HTMLElement, pop = root.querySelector('.fl-pop') as HTMLElement, list = root.querySelector('.fl-list') as HTMLElement;
    const search = root.querySelector('.fl-search') as HTMLInputElement | null, count = root.querySelector('.fl-count') as HTMLElement;
    const api: FilterApi = { root, close(){ pop.hidden = true; btn.setAttribute('aria-expanded','false'); openPops.delete(api) }, refresh(){} };
    const visible = () => {
      const q = search ? search.value.trim().toLowerCase() : '';
      return getOptions().filter((o: any) => !q || o.label.toLowerCase().includes(q) || o.id.toLowerCase().includes(q));
    };
    const renderList = () => {
      const opts = visible();
      list.innerHTML = opts.length
        ? opts.map((o: any) => `<label class="fl-opt${mono?' mono':''}${max && !state.has(o.id) && state.size>=max?' off':''}"><input type="checkbox" value="${o.id}" ${state.has(o.id)?'checked':''} ${max && !state.has(o.id) && state.size>=max?'disabled':''}><span>${o.label}</span></label>`).join('')
        : `<div class="fl-empty">No matches</div>`;
      count.textContent = max ? `${state.size}/${max} max` : `${state.size}/${getOptions().length}`;
    };
    const refreshButton = () => { (btn.querySelector('.fl-v') as HTMLElement).textContent = summary(state); root.classList.toggle('mod', summary.isModified ? summary.isModified(state) : false) };
    api.refresh = () => { renderList(); refreshButton() };
    btn.onclick = e => {
      e.stopPropagation();
      const open = pop.hidden;
      closeAll(api);
      pop.hidden = !open; btn.setAttribute('aria-expanded', String(open));
      if(open){ openPops.add(api); renderList(); if(search){ search.value=''; renderList(); search.focus() } } else openPops.delete(api);
    };
    if(search) search.oninput = renderList;
    list.onchange = (e: any) => {
      const cb = e.target.closest('input'); if(!cb) return;
      cb.checked ? state.add(cb.value) : state.delete(cb.value);
      if(max) renderList(); else count.textContent = `${state.size}/${getOptions().length}`; refreshButton(); onChange();
    };
    (root.querySelector('.fl-actions') as HTMLElement).onclick = (e: any) => {
      const act = e.target.closest('button')?.dataset.act; if(!act) return;
      visible().forEach((o: any) => act==='all' ? state.add(o.id) : state.delete(o.id));
      renderList(); refreshButton(); onChange();
    };
    pop.onclick = e => e.stopPropagation();
    api.refresh();
    return api;
  };

  const brokerSummary: any = (s: Set<string>) => { const total = allBrokers().length;
    if(s.size === total) return `All (${total})`; if(s.size === 0) return 'None';
    return s.size <= 2 ? [...s].sort().join(', ') : `${s.size} selected` };
  brokerSummary.isModified = (s: Set<string>) => s.size !== allBrokers().length;
  const listSummary = (all: number, def?: Set<string>) => { const f: any = (s: Set<string>) => s.size===all ? `All (${all})` : s.size===0 ? 'None' : [...s].map(x=>x==='Cash'?'Cash':x).join(', ');
    f.isModified = (s: Set<string>) => def ? !(s.size===def.size && [...def].every(x=>s.has(x))) : s.size!==all; return f };
  const onFilter = () => { recomputeFlow(); $('flReset').hidden = isDefault() };

  const fBroker = makeFilter($('flBroker'), { title:'Broker', searchable:true, placeholder:'Search broker code…', grid:true, mono:true,
    getOptions:()=>allBrokers().map(b=>({id:b,label:b})), state:flt.brokers, summary:brokerSummary, onChange:onFilter });
  const fBoard = makeFilter($('flBoard'), { title:'Board', getOptions:()=>BOARDS, state:flt.boards,
    summary:listSummary(BOARDS.length), onChange:onFilter });
  const fInv = makeFilter($('flInvestor'), { title:'Investor', getOptions:()=>INVESTORS, state:flt.investors,
    summary:listSummary(INVESTORS.length, new Set(['Foreign'])), onChange:onFilter });
  $('flReset').onclick = () => {
    flt.brokers.clear(); allBrokers().forEach(b=>flt.brokers.add(b));
    flt.boards.clear(); BOARDS.forEach(b=>flt.boards.add(b.id));
    flt.investors.clear(); flt.investors.add('Foreign');
    [fBroker,fBoard,fInv].forEach(f=>f.refresh()); onFilter();
  };

  const setBadge = () => {
    (document.querySelector('.flow-title strong') as HTMLElement).title = ctx.flowSource === 'synthetic'
      ? 'Daily flow is synthetic, seeded from the real 2023-12-18 broker profile. Load real rows with MarketLab.setBroksumRows(rows).' : '';
  };
  setBadge();

  /* Public hook for real data. rows: [{date, broker, investor, board, net}] (also accepts the xlsx headers
     'Date','Broker','Investor Type','Market Board','Net Value'). Dates outside the chart's session list are skipped. */
  (window as any).MarketLab = {
    setBroksumRows(rows: any[]){
      const map = new Map<string, any>();
      rows.forEach(r => {
        const i = idxByTime.get(String(r.date ?? r.Date).slice(0,10)); if(i === undefined) return;
        const broker = r.broker ?? r.Broker, investor = normInvestor(r.investor ?? r['Investor Type']), board = normBoard(r.board ?? r['Market Board']);
        const key = `${broker}|${investor}|${board}`;
        if(!map.has(key)) map.set(key, { broker, investor, board, gross:0, tilt:0, net:new Float64Array(N) });
        map.get(key).net[i] += Number(r.net ?? r['Net Value']) || 0;
      });
      ctx.COMBOS = [...map.values()]; ctx.flowSource = 'real'; setBadge();
      flt.brokers.clear(); allBrokers().forEach(b=>flt.brokers.add(b));
      [fBroker,fBoard,fInv].forEach(f=>f.refresh()); onFilter();
    }
  };
  /* live: the broker files read by the worker after the first draw (EXEC-TERMINAL-UI-1026 U5) */
  ctx.setFlowData = (combos, from, more = false, to = N - 1) => {
    const wasAll = flt.brokers.size === allBrokers().length;   // a broker choice the user made survives the full history
    ctx.COMBOS = combos; flowFrom = from; flowTo = to; flowLoading = false; flowMore = more;
    if(wasAll){ flt.brokers.clear(); allBrokers().forEach(b=>flt.brokers.add(b)) }
    [fBroker,fBoard,fInv].forEach(f=>f.refresh()); onFilter();
    ctx.refreshFlowIndicators?.();
  };


  /* ---- pill toggle (T02): show / hide the cumulative line ---- */
  const setCum = (on: boolean) => {
    cumOn = on; flowCum.applyOptions({ visible:on }); $('tglCum').checked = on;
    // keep the axis width (so plot areas stay aligned) but blank its labels when there is no line to read them against
    flowChart.applyOptions({ leftPriceScale:{ textColor: on ? '#666666' : 'rgba(0,0,0,0)' } } as any);
    store.set('ml.flow.cum', on ? '1' : '0'); showTip(ctx.lastTipIdx);
  };
  $('tglCum').onchange = (e: any) => setCum(e.target.checked);
  setCum(cumOn);

  /* ---- resizable split: drag the Flow Timeline header / grip to raise or lower the panel ---- */
  const mainCol = document.querySelector('.main-col') as HTMLElement, flowPanel = $('flowPanel'), grip = $('flowGrip');
  /* EXEC-TERMINAL-UI-1026 U1 (user 2026-10-26: "Ok rasio chart no 1"): the page fills the screen (html.fit) and the split
     is a ratio, chart 70 : Flow 30 of the column below the toolbar, Flow 180–346 px; a height the user drags is kept as
     a ratio, so it carries to another screen. The fixture keeps the reference's fixed 976 px column (1:1 check). */
  const FIT = document.documentElement.classList.contains('fit');
  const FLOW_MIN = FIT ? 180 : 260, FLOW_MAX = 346, FLOW_RATIO = .3, CHART_MIN = 240 + 46;   // 46 = toolbar row inside the centre column
  const avail = () => Math.max(1, mainCol.clientHeight - 46);
  const maxFlow = () => Math.max(FLOW_MIN, mainCol.clientHeight - CHART_MIN);
  const saveFlowH = (h: number) => FIT ? store.set('ml.flow.ratio', (h / avail()).toFixed(4)) : store.set('ml.flow.h', String(h));
  const setFlowH = (h: number, save = true) => {
    h = Math.round(Math.max(FLOW_MIN, Math.min(maxFlow(), h)));
    mainCol.style.setProperty('--flow-h', h + 'px');
    grip.setAttribute('aria-valuemin', FLOW_MIN); grip.setAttribute('aria-valuemax', maxFlow()); grip.setAttribute('aria-valuenow', h);
    if(save) saveFlowH(h);
    return h;
  };
  const fitFlowH = () => setFlowH(Math.min(FLOW_MAX, avail() * (Number(store.get('ml.flow.ratio')) || FLOW_RATIO)), false);
  if(FIT){ fitFlowH(); new ResizeObserver(() => { if(!drag) fitFlowH() }).observe(mainCol) }
  else setFlowH(Number(store.get('ml.flow.h')) || FLOW_MAX, false);
  let drag: { y: number; h: number; el: HTMLElement } | null = null;
  const startDrag = (e: any) => {
    if(e.button !== undefined && e.button !== 0) return;
    if(mainCol.classList.contains('flow-collapsed')) return;
    if(e.target.closest('.flow-filters, button, input, select, a, label')) return;     // never hijack the filters / toggles
    drag = { y:e.clientY, h:flowPanel.getBoundingClientRect().height, el:e.currentTarget };
    drag.el.setPointerCapture(e.pointerId); mainCol.classList.add('dragging'); e.preventDefault();
  };
  const moveDrag = (e: PointerEvent) => { if(drag) setFlowH(drag.h + (drag.y - e.clientY), false) };          // drag up = taller panel
  const endDrag = (e: PointerEvent) => {
    if(!drag) return;
    try{ drag.el.releasePointerCapture(e.pointerId) }catch(_){}
    drag = null; mainCol.classList.remove('dragging');
    saveFlowH(Math.round(flowPanel.getBoundingClientRect().height));
  };
  [grip, $('flowHead')].forEach((el: HTMLElement) => { el.addEventListener('pointerdown', startDrag); el.addEventListener('pointermove', moveDrag);
    el.addEventListener('pointerup', endDrag); el.addEventListener('pointercancel', endDrag);
    el.addEventListener('dblclick', (e: any) => { if(!e.target.closest('.flow-filters, button, input, select, a, label')) setFlowH(FIT ? Math.min(FLOW_MAX, avail() * FLOW_RATIO) : FLOW_MAX) }) });
  grip.addEventListener('keydown', (e: KeyboardEvent) => {
    const cur = flowPanel.getBoundingClientRect().height;
    if(e.key === 'ArrowUp'){ setFlowH(cur + 16); e.preventDefault() }
    else if(e.key === 'ArrowDown'){ setFlowH(cur - 16); e.preventDefault() }
    else if(e.key === 'Home'){ setFlowH(FLOW_MIN); e.preventDefault() }
    else if(e.key === 'End'){ setFlowH(maxFlow()); e.preventDefault() }
  });

  return { recomputeFlow, mainCol, axisW };
}

/* collapse / expand the Flow Timeline (keeps its header: title + totals), then the first draw — the reference runs
   this after the Events block */
export function finishFlow(ctx: Ctx, flow: ReturnType<typeof initFlow>) {
  const { chart, flowChart } = ctx, { recomputeFlow, mainCol, axisW } = flow;
  const pushRange = ctx.pushRange, syncAxisWidths = ctx.syncAxisWidths;
  const collapseBtn = $('flowCollapse');
  function setCollapsed(on: boolean, save = true) {
    mainCol.classList.toggle('flow-collapsed', on);
    collapseBtn.setAttribute('aria-expanded', String(!on));
    const t = on ? 'Expand Flow Timeline' : 'Collapse Flow Timeline';
    collapseBtn.setAttribute('aria-label', t); collapseBtn.title = t;
    if(save) store.set('ml.flow.collapsed', on ? '1' : '0');
    // the main chart grows / shrinks with the panel; re-sync the shared time range and axis widths afterwards
    requestAnimationFrame(() => requestAnimationFrame(() => { try{ pushRange(chart, flowChart); syncAxisWidths() }catch(_){} }));
  }
  collapseBtn.addEventListener('click', () => setCollapsed(!mainCol.classList.contains('flow-collapsed')));
  // U1: on a short screen (frame under 650 px) the Flow Timeline starts folded until the user opens it (remembered)
  const folded = store.get('ml.flow.collapsed');
  if(folded === '1' || (folded === null && document.documentElement.classList.contains('fit') && innerHeight < 650)) setCollapsed(true, false);

  recomputeFlow();
  pushRange(chart, flowChart);
  setTimeout(() => { pushRange(chart, flowChart); syncAxisWidths(); syncAxisWidths() }, 60);
  // The shared axis width only ever grew, so a one-off wide label left a big empty gutter on the right.
  // Re-measure the right axis from its real labels once, so the gutter fits the text.
  setTimeout(() => {
    axisW.right = 0; const o = { rightPriceScale:{ minimumWidth:0 } };
    chart.applyOptions(o); flowChart.applyOptions(o);
    requestAnimationFrame(() => { syncAxisWidths(); requestAnimationFrame(syncAxisWidths) });
  }, 200);
}
