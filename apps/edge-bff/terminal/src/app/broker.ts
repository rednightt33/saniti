/* RIGHT PANEL — Broker activity (reference lines 3685-3985). The fixture is the reference's dummy history built around
   a real BBCA day; live data is the published broker summary of the ticker (the last sessions in its files). */
import type { Ctx } from './context';
import { $, keyOf, nfCompact, pct, row, spin, store } from './context';
import { closeRangeCalendar, longDay, openRangeCalendar } from '../ui/calendar';
import { aggregate, SPLIT_LEGEND, splitFill } from '../data/brokerAgg';

/** four to seven round tick values covering lo..hi (Broker inventory y-axis, EXEC-TERMINAL-PANELS-2 C) */
export function niceTicks(lo: number, hi: number): number[] {
  const span = (hi - lo) || 1, raw = span / 6, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(x => x >= raw)!;
  const out: number[] = [];
  for(let k = Math.ceil(lo / step); k * step <= hi + step * 1e-9; k++) out.push(k === 0 ? 0 : k * step);
  return out;
}

export function initBroker(ctx: Ctx) {
  const { M, ws, showStTip, hideStTip, tipHtml, makeFilter } = ctx;
  if(M.hide.bandar) ($('brokerPanel').querySelector('.st[data-sec="bd"]') as HTMLElement).hidden = true;   // live: formula not approved yet
  const rpAside = $('brokerPanel');
  // panel state kept across redraws (declared before the first draw below can run)
  const live = M.mode === 'live';
  const kept: Record<string, { bn: string; f: string; t: string }> = {};      // each panel's period, by date
  const RS = { d:0, inv:'All', board:'All', mode:'net', more:false, accSide:'buy', accBoard:'All', bdN:5, broker:null, invUnit:'lot', invInv:'All', invBoard:'All' };
  const invSel = new Set<string>();                                 // brokers drawn in Broker inventory (max INV_MAX)
  const INV_MAX = 5, INV_COLORS = ['#0070f3', '#f5a623', '#7928ca', '#12a594', '#d6409f'];
  /* EXEC-TERMINAL-POPOUT: the panel and its windows share the inventory brokers and the highlighted broker; a change
     redraws the panel (when drawn) and every open window */
  const listeners: (() => void)[] = [];
  let panelRefresh = () => {};
  const changed = () => { if(rendered) panelRefresh(); listeners.forEach(fn => fn()) };
  const brokerCodes = () => { const B = M.broker, s = new Set<string>(); for(let d = 0; d < B.dates.length; d++) for(const r of B.rows(d)) s.add(r[0]); return [...s].sort() };
  // no broker chosen: the three biggest net accumulators of the last 20 sessions (the panel's first period)
  const ensureDefaults = () => {
    const n = M.broker.dates.length;
    if(invSel.size || !n) return;
    const top = aggregate(M.broker.rows, Math.max(0, n - 20), n - 1).sort((a,b) => (b.bv-b.sv)-(a.bv-a.sv)).slice(0,3);
    top.forEach(o => invSel.add(o.b)); RS.broker = top.length ? top[0].b : brokerCodes()[0] ?? null;
  };
  ctx.brokerShared = { invSel, max:INV_MAX, colors:INV_COLORS, changed, ensureDefaults, brokers:brokerCodes,
    pick(b){ RS.broker = b; if(!invSel.has(b)){ if(invSel.size >= INV_MAX) invSel.delete(invSel.values().next().value!); invSel.add(b) } changed() },
    listen:fn => { listeners.push(fn) }, ready:() => ready, selected:() => RS.broker };
  let applyChartRange = (_f: string, _t: string) => {};
  /* EXEC-TERMINAL-BS-SIDE (user 2026-10-28: "Bisa nggak dibuatkan shortcut seperti alt apa kek? ... tombol select on
     chart buat lihat broker summary keluar"; "Alt+B sama persis dengan menekan Custom → Select on chart di panel kanan"),
     live: Alt+B starts choosing a period on the chart for the right panel's four panels, then shows Broker summary.
     Not while typing, and not before the broker data has come. Pop-out windows keep their own Custom button. */
  const showBS = () => {
    if($('workspace').classList.contains('right-collapsed')) $('rpExpand').click();
    const sec = $('bsBody').closest('.st') as HTMLElement | null;
    if(sec?.classList.contains('collapsed')) (sec.querySelector('.st-head') as HTMLElement).click();
    sec?.scrollIntoView({ block:'nearest', behavior:'smooth' });
  };
  if(live) document.addEventListener('keydown', (e: any) => {
    if(!e.altKey || e.ctrlKey || e.metaKey || e.code !== 'KeyB' || e.repeat || !ready) return;
    if(/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable) return;
    e.preventDefault(); closeRangeCalendar();
    ctx.selectRangeOnChart((f, t) => { showBS(); applyChartRange(f, t) });   // a collapsed panel draws itself on opening
  });
  /* EXEC-TERMINAL-PANELS-2 C: Broker inventory follows the chart (its visible range and its crosshair), live */
  let invFollow: (() => void) | null = null, invOnCross: ((t: string | null) => void) | null = null, invRaf = 0;
  if(live){
    ctx.chart.timeScale().subscribeVisibleLogicalRangeChange(() => { if(!invRaf) invRaf = requestAnimationFrame(() => { invRaf = 0; invFollow?.() }) });
    ctx.chart.subscribeCrosshairMove((p: any) => invOnCross?.(p && p.time != null && p.point && p.point.x >= 0 ? keyOf(p.time) : null));
  }
  const RIGHT_MIN = 260, RIGHT_MAX = 520;
  let rightW = parseInt(store.get('ml.broker.w'),10) || 0;
  const clampR = w => Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, Math.round((ws.clientWidth||1400)*.4), w));
  const applyRightW = () => {
    if(rightW && !ws.classList.contains('right-collapsed')) ws.style.setProperty('--right-w', rightW+'px');
    else ws.style.removeProperty('--right-w');
  };
  const setRightCollapsed = c => {
    ws.classList.toggle('right-collapsed', c);
    applyRightW();
    $('rpCollapse').setAttribute('aria-expanded', String(!c));
    $('rpExpand').setAttribute('aria-expanded', String(!c));
    store.set('ml.broker.collapsed', c?'1':'0');
    if(!c) renderWhenReady();
  };
  $('rpCollapse').onclick = () => setRightCollapsed(true);
  $('rpExpand').onclick = () => setRightCollapsed(false);
  /* EXEC-TERMINAL-UI-1026 U5: live, the panel starts closed and is filled when it is opened (the user's last choice is
     remembered); the fixture keeps the reference's open panel */
  let ready = !M.later, rendered = false;
  function renderWhenReady() {
    if(!ready || rendered || ws.classList.contains('right-collapsed')) return;
    rendered = true; renderData();
  }
  /* EXEC-TERMINAL-PANELS B1: the panel gets the recent broker years first and the full two years after them; a second
     answer redraws it with the user's choices (periods by date, filters, picked brokers) kept */
  ctx.setBrokerPanelData = broker => { M.broker = broker; ready = true; rendered = false; ensureDefaults(); renderWhenReady(); listeners.forEach(fn => fn()) };
  if(M.later){
    $('rpSub').textContent = `${M.broker.label} · loading`;
    // the hidden Bandar section gets no ring: nothing would ever replace it
    ['bsBody','accBody','invBody', ...(M.hide.bandar ? [] : ['bdBody'])].forEach(id => { $(id).innerHTML = `<div class="rp-empty">${spin('Loading')}</div>` });
  }
  setRightCollapsed((store.get('ml.broker.collapsed') ?? (M.later ? '1' : '0')) === '1');
  {
    const rz = $('rpResize');
    const setW = w => { rightW = clampR(w); applyRightW() };
    rz.addEventListener('pointerdown', e => {
      e.preventDefault(); rz.setPointerCapture(e.pointerId);
      const x0 = e.clientX, w0 = rpAside.getBoundingClientRect().width;
      ws.classList.add('resizing'); rz.classList.add('active');
      const mv = ev => setW(w0 - (ev.clientX - x0));
      const up = () => { rz.removeEventListener('pointermove', mv); rz.removeEventListener('pointerup', up); rz.removeEventListener('pointercancel', up);
        ws.classList.remove('resizing'); rz.classList.remove('active'); store.set('ml.broker.w', String(rightW)) };
      rz.addEventListener('pointermove', mv); rz.addEventListener('pointerup', up); rz.addEventListener('pointercancel', up);
    });
    rz.addEventListener('dblclick', () => { rightW = 0; applyRightW(); store.set('ml.broker.w','0') });
    rz.addEventListener('keydown', e => {
      const cur = rpAside.getBoundingClientRect().width;
      if(e.key==='ArrowLeft'){ setW(cur+16); e.preventDefault() } else if(e.key==='ArrowRight'){ setW(cur-16); e.preventDefault() }
      else if(e.key==='Home'){ setW(RIGHT_MAX); e.preventDefault() } else if(e.key==='End'){ setW(RIGHT_MIN); e.preventDefault() }
      store.set('ml.broker.w', String(rightW));
    });
  }
  rpAside.addEventListener('pointermove', e => {
    const t = e.target.closest('[data-tip]');
    t ? showStTip(e.clientX, e.clientY, tipHtml(t.dataset.tip)) : hideStTip();
  });
  rpAside.addEventListener('pointerleave', hideStTip);
  $('rightScroll').addEventListener('scroll', hideStTip, {passive:true});

  let rpSec = {};
  try{ rpSec = JSON.parse(store.get('ml.broker.sections') || '{}') || {} }catch(e){}
  rpAside.querySelectorAll('.st').forEach(sec => {
    const head = sec.querySelector('.st-head'), key = sec.dataset.sec;
    const apply = c => { sec.classList.toggle('collapsed', c); head.setAttribute('aria-expanded', String(!c)) };
    apply(!!rpSec[key]);
    head.onclick = () => { const c = !sec.classList.contains('collapsed'); apply(c); rpSec[key] = c; store.set('ml.broker.sections', JSON.stringify(rpSec)) };
  });

  function renderData() {
  // (body kept at its reference indentation: its template strings are the panel's markup, compared 1:1)
  /* ---- broker-summary history: fixture = the reference's last real day (BK_BASE) + 29 synthetic sessions before it;
          live = the last sessions of the published broker files ---- */
  const bkDates = M.broker.dates;
  const BK_DAYS = bkDates.length;
  const bkCat = M.broker.category;
  const bkRows = M.broker.rows;
  if(!BK_DAYS){                                                   // live: a ticker with no broker summary (an index)
    $('rpSub').textContent = `${M.broker.label} · no broker data`;
    ['bsBody','accBody','invBody','bdBody'].forEach(id => { $(id).innerHTML = `<div class="rp-empty">Tidak ada data</div>` });
    ['bsRange','accRange','invRange','bdRange'].forEach(id => { $(id).innerHTML = '' });
    return;
  }
  const bkAgg = (d, inv='All', board='All') => {
    const m = new Map();
    for(const r of bkRows(d)){
      if(inv!=='All' && r[1]!==inv) continue;
      if(board!=='All' && r[2]!==board) continue;
      const o = m.get(r[0]) || {b:r[0], bv:0, sv:0, bl:0, sl:0};
      o.bv += r[3]; o.sv += r[4]; o.bl += r[5]; o.sl += r[6]; m.set(r[0], o);
    }
    return [...m.values()];
  };
  const bkList = [...new Set(Array.from({ length:BK_DAYS }, (_, d) => bkRows(d).map(r=>r[0])).flat())].sort();
  // broker summary over a date range (from..to inclusive), summed per broker
  const bkAggRange = (f, t, inv, board) => {
    const m = new Map();
    for(let d=f; d<=t; d++) for(const o of bkAgg(d, inv, board)){
      const x = m.get(o.b) || {b:o.b, bv:0, sv:0, bl:0, sl:0};
      x.bv += o.bv; x.sv += o.sv; x.bl += o.bl; x.sl += o.sl; m.set(o.b, x);
    }
    return [...m.values()];
  };
  const netOf = o => o.bv - o.sv;
  const netLotOf = o => o.bl - o.sl;

  /* ---- state ---- */
  RS.d = BK_DAYS-1;
  const bkFmtDay = d => { const t = new Date(bkDates[d]+'T00:00:00Z'); return t.toLocaleDateString('en-GB',{weekday:'short',day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}) };
  const dayShort = d => new Date(bkDates[d]+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'});
  const cv = v => nfCompact.format(Math.abs(v));
  const sgn = v => (v<0?'-':'+') + cv(v);
  const bkTag = (b) => `<span class="bk ${bkCat(b)}"><i></i>${b}</span>`;
  const verdict = r => {
    const a = Math.abs(r); if(a < .03) return ['Neutral','neu'];
    const size = a < .06 ? 'Small' : a < .12 ? 'Normal' : 'Big';
    return [`${size} ${r>0?'Acc':'Dist'}`, r>0?'acc':'dist'];
  };

  /* ---- period picker shared by every panel: presets + custom from/to (default = the latest session) ---- */
  const makeRange = (root, { key, presets, def, nav = false, onChange }) => {
    const last = BK_DAYS - 1;
    const st = { bn:String(def), bf:0, bt:last };
    /* live (EXEC-TERMINAL-PANELS D1): Custom opens one range calendar (with "Select on chart"); the fixture keeps the
       reference's two date fields (1:1 check) */
    root.innerHTML = `${nav ? `<div class="rp-ctl"><button class="rp-btn" data-act="prev" aria-label="Previous period" title="Previous period">‹</button><span class="rp-date"></span><button class="rp-btn" data-act="next" aria-label="Next period" title="Next period">›</button></div>` : ''}
      <div class="rp-ctl"><div class="seg" role="group" aria-label="Period">${presets.map(n => `<button data-n="${n}">${n}D</button>`).join('')}<button data-n="custom"${live ? ' aria-haspopup="dialog" title="Choose a period · Alt + B: select it on the chart"' : ''}>Custom</button></div></div>
      ${live ? '<div class="rp-note" hidden></div>' : '<div class="rp-ctl rp-custom" hidden><input class="rp-sel" type="date" aria-label="From date"><span class="rp-dash">–</span><input class="rp-sel" type="date" aria-label="To date"></div>'}`;
    const $q = s => root.querySelector(s), from = $q('input:first-of-type'), to = root.querySelectorAll('input')[1];
    const days = () => st.bt - st.bf + 1;
    // live periods may span two years: the year is written when the ends fall in different years
    const yearOf = d => bkDates[d].slice(0, 4);
    const text = () => days() === 1 ? dayShort(st.bt) : live && yearOf(st.bf) !== yearOf(st.bt)
      ? `${dayShort(st.bf)} ${yearOf(st.bf)} – ${dayShort(st.bt)} ${yearOf(st.bt)}` : `${dayShort(st.bf)} – ${dayShort(st.bt)}`;
    const note = (msg = '') => { const n = $q('.rp-note'); if(n){ n.textContent = msg; n.hidden = !msg } };
    const save = () => { kept[key] = { bn:st.bn, f:bkDates[st.bf], t:bkDates[st.bt] } };
    const preset = n => { st.bn = String(n); if(st.bn !== 'custom') st.bf = Math.max(0, st.bt - (+st.bn) + 1) };
    const render = () => {
      root.querySelectorAll('.seg button').forEach(b => b.classList.toggle('active', b.dataset.n === st.bn));
      if(!live){
      root.querySelector('.rp-custom').hidden = st.bn !== 'custom';
      from.value = bkDates[st.bf]; to.value = bkDates[st.bt];
      from.min = to.min = bkDates[0]; from.max = to.max = bkDates[last];
      }
      save();
      if(nav){ $q('.rp-date').textContent = days() === 1 ? bkFmtDay(st.bt) : `${text()} ${bkDates[st.bt].slice(0,4)} · ${days()}D`;
        $q('[data-act=prev]').disabled = st.bf <= 0; $q('[data-act=next]').disabled = st.bt >= last }
    };
    const shift = dir => {
      const n = days(); let f = st.bf + dir*n, t = st.bt + dir*n;
      if(f < 0){ f = 0; t = n-1 } if(t > last){ t = last; f = t-n+1 }
      st.bf = f; st.bt = t;
    };
    const idxOnOrAfter = v => { const i = bkDates.findIndex(x => x >= v); return i < 0 ? last : i };
    const idxOnOrBefore = v => { let r = 0; bkDates.forEach((x,i) => { if(x <= v) r = i }); return r };
    const setIdx = (f, t, msg = '') => { st.bf = f; st.bt = t; st.bn = 'custom'; note(msg); render(); onChange() };
    /* a period chosen by date (calendar or chart): clipped to the panel's broker dates, with a note when it was */
    const setDates = (fd, td) => {
      if(td < bkDates[0] || fd > bkDates[last]) { note(`${longDay(fd)} – ${longDay(td)} is outside the panels' two years (${longDay(bkDates[0])} – ${longDay(bkDates[last])}); nothing changed.`); return }
      const f = idxOnOrAfter(fd), t = idxOnOrBefore(td);
      // no session inside the chosen days (a weekend or a holiday): the last session before them, with a note
      if(f > t) return setIdx(t, t, `No trading session in ${fd === td ? longDay(fd) : `${longDay(fd)} – ${longDay(td)}`}; showing ${longDay(bkDates[t])}.`);
      setIdx(f, t, fd < bkDates[0] ? `Starts ${longDay(bkDates[0])}: the panels cover the last two years.` : '');
    };
    root.querySelectorAll('.seg button').forEach(b => b.onclick = () => {
      if(live && b.dataset.n === 'custom'){
        openRangeCalendar({ anchor:b, dates:bkDates, from:bkDates[st.bf], to:bkDates[st.bt], onPick:setDates,
          onChart:() => ctx.selectRangeOnChart((f, t) => applyChartRange(f, t)) });
        return;
      }
      note(); preset(b.dataset.n); render(); onChange();
    });
    if(nav) root.querySelectorAll('[data-act]').forEach(b => b.onclick = () => { note(); shift(b.dataset.act === 'prev' ? -1 : 1); render(); onChange() });
    const custom = () => {
      if(!from.value || !to.value) return;
      let f = idxOnOrAfter(from.value), t = idxOnOrBefore(to.value); if(f > t) [f, t] = [t, f];
      st.bf = f; st.bt = t; st.bn = 'custom'; render(); onChange();
    };
    if(from) { from.onchange = custom; to.onchange = custom }
    const k = kept[key];
    if(k && k.bn !== 'custom' && k.bn !== String(def)) preset(k.bn);
    else if(k && k.bn === 'custom') { st.bf = idxOnOrAfter(k.f); st.bt = idxOnOrBefore(k.t); st.bn = 'custom'; if(st.bf > st.bt) preset(def) }
    else preset(def);
    render();
    return Object.assign(st, { text, days, setDates });
  };

  /* ---- Broker summary ---- */
  const bsRange = makeRange($('bsRange'), { key:'bs', presets:[1,5,20], def:1, nav:true, onChange:() => renderBS() });
  function renderBS(){
    const list = bkAggRange(bsRange.bf, bsRange.bt, RS.inv, RS.board);
    const totBuy = list.reduce((s,o)=>s+o.bv,0);
    // broker action gauge: top-5 net buyers vs top-5 net sellers
    const nets = list.map(netOf).sort((a,b)=>b-a);
    const t5b = nets.filter(x=>x>0).slice(0,5).reduce((s,x)=>s+x,0);
    const t5s = -nets.filter(x=>x<0).slice(-5).reduce((s,x)=>s+x,0);
    const g = totBuy ? Math.max(-1, Math.min(1, (t5b-t5s)/totBuy*4)) : 0;
    const [gt, gc] = g>.6?['Big Acc','acc']:g>.2?['Acc','acc']:g<-.6?['Big Dist','dist']:g<-.2?['Dist','dist']:['Neutral','neu'];
    const gross = RS.mode==='gross';
    const buyers = list.filter(o=> gross ? o.bv>0 : netOf(o)>0).sort((a,b)=> gross ? b.bv-a.bv : netOf(b)-netOf(a));
    const sellers = list.filter(o=> gross ? o.sv>0 : netOf(o)<0).sort((a,b)=> gross ? b.sv-a.sv : netOf(a)-netOf(b));
    const N = RS.more ? 10 : 5;
    const rowsHtml = (arr, side) => arr.slice(0,N).map(o => {
      const val = gross ? (side==='b'?o.bv:o.sv) : Math.abs(netOf(o));
      const lot = gross ? (side==='b'?o.bl:o.sl) : Math.abs(netLotOf(o));
      const avg = lot ? Math.round(val/(lot*100)) : 0;
      return `<tr data-b="${o.b}" class="${o.b===RS.broker?'sel':''}" data-tip="${o.b}|Buy ${cv(o.bv)} · Sell ${cv(o.sv)} · Net ${sgn(netOf(o))}"><td>${bkTag(o.b)}</td><td>${cv(lot)}</td><td class="${side==='b'?'up':'down'}">${cv(val)}</td><td>${avg.toLocaleString('en-US')}</td></tr>`;
    }).join('') || `<tr><td colspan="4" class="rp-empty">Tidak ada data</td></tr>`;
    const head = `<thead><tr><th>Broker</th><th>Lot</th><th>Value</th><th>Avg</th></tr></thead>`;
    const can = Math.max(buyers.length, sellers.length) > 5;
    $('bsBody').innerHTML = (M.hide.brokerGauge ? '' : `
      <div class="rp-gauge"><div class="rp-gauge-top"><span>Broker action</span><span class="tag ${gc}">${gt}</span></div>
        <div class="rp-track" data-tip="Broker action|${g>=0?'+':''}${g.toFixed(2)} (−1 … +1)"><b style="left:${((g+1)/2*100).toFixed(1)}%"></b></div></div>`) + `
      <div class="rp-sub"><span>${gross?'Top buyers · gross':'Top net buyers'}</span><span>${buyers.length} brokers</span></div>
      <table class="rp-t">${head}<tbody>${rowsHtml(buyers,'b')}</tbody></table>
      <div class="rp-sub"><span>${gross?'Top sellers · gross':'Top net sellers'}</span><span>${sellers.length} brokers</span></div>
      <table class="rp-t">${head}<tbody>${rowsHtml(sellers,'s')}</tbody></table>
      ${can?`<button class="rp-more" id="bsMore">${RS.more?'Show less':'Show top 10'}</button>`:''}`;
    $('bsHint').textContent = (gross ? 'Gross' : 'Net') + ' · ' + bsRange.text();
    const mb = $('bsMore'); if(mb) mb.onclick = () => { RS.more = !RS.more; renderBS() };
    $('bsBody').querySelectorAll('tr[data-b]').forEach(tr => tr.onclick = () => selectBroker(tr.dataset.b));
  }

  /* ---- Top accumulators / distributors ---- */
  const accRange = makeRange($('accRange'), { key:'acc', presets:[1,5,20], def:5, onChange:() => renderAcc() });
  /* EXEC-TERMINAL-PANELS-2 E (user 2026-10-27: "top accumulators dan distributors digabung saja tidak usah pakai
     switcher ... Top accumulators|Value|Bar Buy (ke kiri)|Bar Sell (ke kanan)|Sell|Top Distributors"), live: one table,
     rank k pairs the k-th accumulator with the k-th distributor; both bars share one scale. The fixture keeps the
     reference's Buy/Sell switch (1:1 check). */
  /* EXEC-TERMINAL-TOPSPLIT (user 2026-10-28: "di bagian top broker bisa ditambahkan filter lagi untuk boards", 2026-10-29
     "All boards", "pakai versi ini saja, tapi di balik ya, yang tebal = domestic"), live: a Board choice (All boards by
     default) where the fixture has its Buy/Sell switch, and each bar split into Domestic (solid) and Foreign (faded) */
  if(live){
    $('accTitle').textContent = 'Top brokers';
    const ctl = $('accSide').closest('.rp-ctl') as HTMLElement;
    ctl.innerHTML = `<select class="rp-sel" id="accBoard" aria-label="Board"><option value="All">All boards</option><option value="Regular">Regular</option><option value="Nego">Nego</option><option value="Cash">Cash</option></select>`;
    $('accBoard').onchange = e => { RS.accBoard = e.target.value; renderAcc() };
  }
  function renderAccPaired(){
    const board = RS.accBoard, part = inv => new Map(bkAggRange(accRange.bf, accRange.bt, inv, board).map(o => [o.b, netOf(o)]));
    const fm = part('Foreign'), dm = part('Domestic');
    const all = bkAggRange(accRange.bf, accRange.bt, 'All', board).map(o => ({ b:o.b, net:netOf(o), lot:netLotOf(o), f:fm.get(o.b) || 0, d:dm.get(o.b) || 0 }));
    const buy = all.filter(x => x.net > 0).sort((a,b) => b.net-a.net).slice(0,8);
    const sell = all.filter(x => x.net < 0).sort((a,b) => a.net-b.net).slice(0,8);
    const mx = Math.max(1, ...buy.map(x => x.net), ...sell.map(x => -x.net));
    const cell = (x, side) => x ? `<span class="pa-b" data-b="${x.b}" data-tip="${x.b}|${accRange.text()}${board === 'All' ? '' : ' ' + board} net ${sgn(x.net)} · ${sgn(x.lot)} lot · Domestic ${sgn(x.d)} · Foreign ${sgn(x.f)}">${bkTag(x.b)}</span>` : '<span class="pa-b"></span>';
    const val = (x, side) => `<span class="v ${side==='buy'?'up':'down'}">${x ? sgn(x.net) : ''}</span>`;
    const bar = (x, side) => `<div class="trk ${side}">${x ? splitFill(Math.abs(x.net)/mx*100, x.f, x.d, side) : ''}</div>`;
    const n = Math.max(buy.length, sell.length);
    $('accBody').innerHTML = n ? `<div class="pa-head"><span class="l"><i class="up"></i>Top accumulators</span><span class="r">Top distributors<i class="down"></i></span></div>`
      + Array.from({ length:n }, (_, k) => { const b = buy[k], s = sell[k];
        return `<div class="pa-row">${cell(b,'buy')}${val(b,'buy')}${bar(b,'buy')}${bar(s,'sell')}${val(s,'sell')}${cell(s,'sell')}</div>` }).join('')
        + `<div class="acc-leg">${SPLIT_LEGEND}</div>`
      : `<div class="rp-empty">Tidak ada data</div>`;
    $('accBody').querySelectorAll('.pa-b[data-b]').forEach(el => { el.classList.toggle('sel', el.dataset.b === RS.broker); el.onclick = () => selectBroker(el.dataset.b) });
    $('accHint').textContent = `${accRange.text()} · net`;
  }
  function renderAcc(){
    if(live) return renderAccPaired();
    const buy = RS.accSide === 'buy';
    const l = bkAggRange(accRange.bf, accRange.bt, 'All', 'All').map(o => ({ b:o.b, net:netOf(o), lot:netLotOf(o) }))
      .filter(x => buy ? x.net > 0 : x.net < 0).sort((a,b) => buy ? b.net-a.net : a.net-b.net).slice(0,8);
    const mx = Math.max(1, ...l.map(x => Math.abs(x.net)));
    $('accTitle').textContent = buy ? 'Top accumulators' : 'Top distributors';
    $('accBody').innerHTML = l.length ? l.map(x => {
      const w = Math.abs(x.net)/mx*50;
      return `<div class="rp-bar ${x.b===RS.broker?'sel':''}" data-b="${x.b}" data-tip="${x.b}|${accRange.text()} net ${sgn(x.net)} · ${sgn(x.lot)} lot"><span>${bkTag(x.b)}</span><div class="trk"><div class="fill" style="${buy?`left:50%;width:${w}%;background:#089981`:`right:50%;width:${w}%;background:#f23645`}"></div></div><span class="v ${buy?'up':'down'}">${sgn(x.net)}</span></div>`;
    }).join('') : `<div class="rp-empty">Tidak ada data</div>`;
    $('accHint').textContent = `${accRange.text()} · net`;
    $('accBody').querySelectorAll('.rp-bar').forEach(el => el.onclick = () => selectBroker(el.dataset.b));
  }

  /* ---- Broker inventory: cumulative net position of up to 5 brokers over the chosen period ---- */
  const invRange = makeRange($('invRange'), { key:'inv', presets:[10,20,30], def:20, onChange:() => renderInv() });
  const invFilter = makeFilter($('invFilter'), { title:'Broker', searchable:true, placeholder:'Search broker code…', grid:true, mono:true, max:INV_MAX,
    getOptions:() => bkList.map(b => ({ id:b, label:b })), state:invSel,
    summary:s => s.size ? [...s].slice(0,3).join(', ') + (s.size > 3 ? ` +${s.size-3}` : '') : 'None', onChange:() => changed() });
  /* EXEC-TERMINAL-POPOUT F1 (user 2026-10-27: "broker inventory di filter"), live: investor type and board filters, one
     line per broker as before; the fixture keeps the reference's panel (1:1 check) */
  if(live && !$('invInv')){
    const row = document.createElement('div'); row.className = 'rp-ctl';
    row.innerHTML = '<select class="rp-sel" id="invInv" aria-label="Investor type"><option value="All">All investors</option><option value="Foreign">Foreign</option><option value="Domestic">Domestic</option></select>'
      + '<select class="rp-sel" id="invBoard" aria-label="Board"><option value="All">All boards</option><option value="Regular">Regular</option><option value="Nego">Nego</option><option value="Cash">Cash</option></select>';
    $('invFilter').closest('.rp-ctl').after(row);
  }
  if(live){
    $('invInv').value = RS.invInv; $('invBoard').value = RS.invBoard;
    $('invInv').onchange = e => { RS.invInv = e.target.value; renderInv() };
    $('invBoard').onchange = e => { RS.invBoard = e.target.value; renderInv() };
  }
  const invSeries = b => {
    const out = []; let cum = 0;
    for(let d = invRange.bf; d <= invRange.bt; d++){
      const o = bkAgg(d, RS.invInv, RS.invBoard).find(x => x.b === b), v = o ? (RS.invUnit === 'lot' ? netLotOf(o) : netOf(o)) : 0;
      cum += v; out.push({ d, v, cum });
    }
    return out;
  };
  /* EXEC-TERMINAL-PANELS-2 C (user 2026-10-27: "C2", "C3 + begitupun kalau kita hover di broker inventory, crosshair di
     main chart ... boleh gerak"), live: the period is the chart's visible sessions inside the broker window (no presets);
     the chart has a y-axis with ticks and a vertical line at the crosshair session, both ways with the main chart */
  if(live) ($('invRange') as HTMLElement).hidden = true;
  function renderInvLive(){
    const picks = [...invSel], r = ctx.chart.timeScale().getVisibleLogicalRange();
    const a = r ? Math.max(0, Math.ceil(r.from)) : 0, b = r ? Math.min(ctx.N - 1, Math.floor(r.to)) : ctx.N - 1;
    const va = ctx.dates[a], vb = ctx.endDates[b];          // EXEC-TERMINAL-WM: to the last session of the last candle
    const f = bkDates.findIndex(x => x >= va);
    let t = -1; for(let i = 0; i < BK_DAYS && bkDates[i] <= vb; i++) t = i;
    const none = f < 0 || t < 0 || f > t;
    if(!none){ invRange.bf = f; invRange.bt = t }                    // invSeries reads the period from invRange
    const n = none ? 0 : t - f + 1, all = none ? [] : picks.map(invSeries);
    const scope = [RS.invInv, RS.invBoard].filter(v => v !== 'All').join(' · ');      // F1: the filters in force
    $('invHint').textContent = `${picks.length}/${INV_MAX}${scope ? ' · ' + scope : ''} · ${none ? 'no broker data in view' : invRange.text()}`;
    const chips = (i = null) => picks.map((bk, k) => {
      const p = all[k] ? (i === null ? all[k].at(-1) : all[k][i]) : null, v = p ? p.cum : 0;
      return `<span class="rp-chip" style="--c:${INV_COLORS[k]}"><i></i>${bk}<b class="${v>=0?'up':'down'}">${sgn(v)}</b><button type="button" data-rm="${bk}" aria-label="Remove ${bk}">×</button></span>`;
    }).join('');
    const wireChips = () => $('invLegend').querySelectorAll('[data-rm]').forEach(x => x.onclick = () => { invSel.delete(x.dataset.rm); changed() });
    $('invLegend').innerHTML = chips(); wireChips();
    invOnCross = null;
    if(!picks.length){ $('invBody').innerHTML = `<div class="rp-empty">Pilih 1–${INV_MAX} broker untuk melihat pergerakannya.</div>`; return }
    if(none){ $('invBody').innerHTML = `<div class="rp-empty">The chart shows ${longDay(va)} – ${longDay(vb)}; broker data covers ${longDay(bkDates[0])} – ${longDay(bkDates[BK_DAYS-1])} (the last two years).</div>`; return }
    if(n < 2){ $('invBody').innerHTML = `<div class="rp-empty">Zoom the chart out to at least 2 sessions with broker data.</div>`; return }
    const W = 272, H = 120;
    const flat = all.flatMap(s => s.map(p => p.cum)), lo = Math.min(0, ...flat), hi = Math.max(0, ...flat), sp = (hi-lo) || 1;
    const x = i => i/(n-1)*W, y = v => H-6-(v-lo)/sp*(H-12);
    const ticks = niceTicks(lo, hi);
    const lines = all.map((s, k) => `<path d="${s.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.cum).toFixed(1)).join('')}" fill="none" stroke="${INV_COLORS[k]}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>`).join('');
    const grid = ticks.map(v => `<line x1="0" x2="${W}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${v === 0 ? '#d4d4d4' : '#f0f0f0'}"${v === 0 ? ' stroke-dasharray="3 3"' : ''} vector-effect="non-scaling-stroke"/>`).join('');
    $('invBody').innerHTML = `
      <div class="rp-invwrap live"><div class="rp-yax">${ticks.map(v => `<span style="top:${(y(v)/H*100).toFixed(2)}%">${v === 0 ? '0' : sgn(v)}</span>`).join('')}</div>
        <svg class="rp-inv" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">${grid}${lines}
          <line class="inv-xh" x1="0" x2="0" y1="0" y2="${H}" stroke="#9ca3af" stroke-dasharray="3 3" vector-effect="non-scaling-stroke" visibility="hidden"/></svg>
        <span class="rp-invdate" hidden></span></div>
      <div class="axis"><span class="l">${bkDates[f].slice(5)}</span><span class="r">${bkDates[t].slice(5)}</span></div>`;
    const svg = $('invBody').querySelector('svg'), xh = svg.querySelector('.inv-xh'), lab = $('invBody').querySelector('.rp-invdate');
    const show = i => {
      if(i === null){ xh.setAttribute('visibility', 'hidden'); lab.hidden = true; $('invLegend').innerHTML = chips(); wireChips(); return }
      xh.setAttribute('x1', x(i).toFixed(1)); xh.setAttribute('x2', x(i).toFixed(1)); xh.setAttribute('visibility', 'visible');
      lab.hidden = false; lab.textContent = longDay(bkDates[f + i]); lab.style.left = (svg.getBoundingClientRect().left - svg.parentElement.getBoundingClientRect().left + i/(n-1)*svg.clientWidth).toFixed(1) + 'px';
      $('invLegend').innerHTML = chips(i); wireChips();
    };
    // the main chart's crosshair (also when it follows the Flow chart or this panel)
    invOnCross = d => { const k = d ? bkDates.indexOf(d) : -1; show(k >= f && k <= t ? k - f : null) };
    svg.addEventListener('pointermove', e => {
      const rc = svg.getBoundingClientRect(), i = Math.max(0, Math.min(n-1, Math.round((e.clientX - rc.left) / rc.width * (n-1))));
      const d = bkDates[f + i], ci = ctx.idxByTime.get(ctx.M.barOf ? ctx.M.barOf(d) ?? d : d);   // W/M: the candle holding the day
      if(ci !== undefined) ctx.crosshairAt(ci); else show(i);
    });
    svg.addEventListener('pointerleave', () => { ctx.crosshairAt(null); show(null) });
  }
  invFollow = live ? () => { if(rendered) renderInvLive() } : null;
  function renderInv(){
    if(live) return renderInvLive();
    const picks = [...invSel], n = invRange.days();
    $('invHint').textContent = `${picks.length}/${INV_MAX} · ${invRange.text()}`;
    $('invLegend').innerHTML = picks.map((b, k) => {
      const s = invSeries(b), end = s.at(-1) ? s.at(-1).cum : 0;
      return `<span class="rp-chip" style="--c:${INV_COLORS[k]}"><i></i>${b}<b class="${end>=0?'up':'down'}">${sgn(end)}</b><button type="button" data-rm="${b}" aria-label="Remove ${b}">×</button></span>`;
    }).join('');
    $('invLegend').querySelectorAll('[data-rm]').forEach(x => x.onclick = () => { invSel.delete(x.dataset.rm); invFilter.refresh(); renderInv() });
    if(!picks.length){ $('invBody').innerHTML = `<div class="rp-empty">Pilih 1–${INV_MAX} broker untuk melihat pergerakannya.</div>`; return }
    if(n < 2){ $('invBody').innerHTML = `<div class="rp-empty">Pilih periode minimal 2 hari.</div>`; return }
    const all = picks.map(invSeries), W = 272, H = 120;
    const flat = all.flatMap(s => s.map(p => p.cum)), lo = Math.min(0, ...flat), hi = Math.max(0, ...flat), sp = (hi-lo) || 1;
    const x = i => i/(n-1)*W, y = v => H-6-(v-lo)/sp*(H-12);
    const lines = all.map((s, k) => `<path d="${s.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.cum).toFixed(1)).join('')}" fill="none" stroke="${INV_COLORS[k]}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>`).join('');
    const unit = RS.invUnit === 'lot' ? 'lot' : '';
    const hits = Array.from({ length:n }, (_, i) => {
      const d = invRange.bf + i, rows = picks.map((b,k) => `${b} ${all[k][i].cum<0?'-':'+'}${cv(all[k][i].cum)}`).join('<br>');
      return `<rect class="hit" x="${(x(i)-W/(n-1)/2).toFixed(1)}" y="0" width="${(W/(n-1)).toFixed(1)}" height="${H}" data-tip="${bkDates[d].slice(5)}|<br>${rows}"></rect>`;
    }).join('');
    $('invBody').innerHTML = `
      <div class="rp-invwrap"><span class="rp-ymax">${hi>0?'+'+cv(hi):'0'}</span><span class="rp-ymin">${lo<0?'-'+cv(lo):'0'}</span>
        <svg class="rp-inv" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">
          <line x1="0" x2="${W}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}" stroke="#d4d4d4" stroke-dasharray="3 3"/>${lines}${hits}</svg></div>
      <div class="axis"><span class="l">${bkDates[invRange.bf].slice(5)}</span><span class="r">${bkDates[invRange.bt].slice(5)}</span></div>`;
  }
  $('invUnit').querySelectorAll('button').forEach(b => b.onclick = () => {
    RS.invUnit = b.dataset.unit; $('invUnit').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); renderInv();
  });
  ensureDefaults();               // the three biggest net accumulators of the default period (shared with the windows)
  invFilter.refresh();

  /* ---- Bandar detector ---- */
  const bdRange = makeRange($('bdRange'), { key:'bd', presets:[1,5,20], def:1, onChange:() => renderBD() });
  function renderBD(){
    if(M.hide.bandar) return;
    const list = bkAggRange(bdRange.bf, bdRange.bt, 'All', 'All');
    const totBuy = list.reduce((s,o)=>s+o.bv,0) || 1;
    const nets = list.map(o=>({b:o.b, n:netOf(o)}));
    const topB = nets.filter(x=>x.n>0).sort((a,b)=>b.n-a.n).slice(0,RS.bdN);
    const topS = nets.filter(x=>x.n<0).sort((a,b)=>a.n-b.n).slice(0,RS.bdN);
    const sb = topB.reduce((s,x)=>s+x.n,0), ss = -topS.reduce((s,x)=>s+x.n,0);
    const r = (sb-ss)/totBuy, [vt, vc] = verdict(r);
    const mx = Math.max(sb, ss, 1);
    const bar = (lab, v, color) => `<div class="rp-bar nz" style="cursor:default" data-tip="${lab}|Top ${RS.bdN} · ${cv(v)}"><span>${lab}</span><div class="trk"><div class="fill" style="left:0;width:${(v/mx*100).toFixed(1)}%;background:${color}"></div></div><span class="v">${cv(v)}</span></div>`;
    const fshare = sb ? topB.filter(x=>bkCat(x.b)==='F').reduce((s,x)=>s+x.n,0)/sb*100 : 0;
    $('bdBody').innerHTML = `
      <div class="rp-gauge-top" style="margin-top:2px"><span>Top ${RS.bdN} verdict</span><span class="tag ${vc}">${vt}</span></div>
      ${bar('Buy', sb, '#089981')}${bar('Sell', ss, '#f23645')}
      ${row('Net', sgn(sb-ss), sb>=ss?'up':'down')}
      ${row('Ratio to total buy', pct(r*100), r>=0?'up':'down')}
      ${row('Foreign share of buyers', fshare.toFixed(0)+'%')}
      <div class="rp-sub"><span>Top ${RS.bdN} buyers</span><span>click to inspect</span></div>
      <div>${topB.map(x=>`<div class="rp-bar ${x.b===RS.broker?'sel':''}" data-b="${x.b}" data-tip="${x.b}|Net ${sgn(x.n)}"><span>${bkTag(x.b)}</span><div class="trk"><div class="fill" style="left:50%;width:${(x.n/mx*50).toFixed(1)}%;background:#089981"></div></div><span class="v up">${sgn(x.n)}</span></div>`).join('') || '<div class="rp-empty">Tidak ada data</div>'}</div>`;
    $('bdHint').textContent = `${bdRange.text()} · ${vt}`;
    $('bdBody').querySelectorAll('.rp-bar[data-b]').forEach(el => el.onclick = () => selectBroker(el.dataset.b));
  }

  /* ---- wiring ---- */
  $('rpSub').textContent = `${M.broker.label} · ${bkDates[RS.d].slice(8)} ${new Date(bkDates[RS.d]+'T00:00:00Z').toLocaleDateString('en-GB',{month:'short',timeZone:'UTC'})} ${bkDates[RS.d].slice(0,4)}`;
  const renderAll = () => { renderBS(); renderAcc(); renderInv(); renderBD() };
  // EXEC-TERMINAL-PANELS C1: a period dragged on the chart applies to every panel (each can change it again)
  applyChartRange = (f, t) => { closeRangeCalendar(); [bsRange, accRange, invRange, bdRange].forEach(r => r.setDates(f, t)) };
  // clicking a broker anywhere highlights it and adds it to the inventory chart (oldest one drops out past 5)
  panelRefresh = () => { invFilter.refresh(); renderAll() };
  const selectBroker = b => ctx.brokerShared!.pick(b);
  $('bsInv').onchange = e => { RS.inv = e.target.value; renderBS() };
  $('bsBoard').onchange = e => { RS.board = e.target.value; renderBS() };
  const segWire = (id, attr, fn) => $(id).querySelectorAll('button').forEach(btn => btn.onclick = () => {
    $(id).querySelectorAll('button').forEach(x=>x.classList.toggle('active', x===btn)); fn(btn.dataset[attr]);
  });
  segWire('bsMode','mode', v => { RS.mode = v; renderBS() });
  if($('accSide')) segWire('accSide','side', v => { RS.accSide = v; renderAcc() });   // live: the Board choice took its place
  segWire('bdTop','n', v => { RS.bdN = +v; renderBD() });
  renderAll();
  }
  renderWhenReady();
}
