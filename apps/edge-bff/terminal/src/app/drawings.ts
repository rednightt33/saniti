/* DRAWING TOOLS — host layer around `lightweight-charts-drawing` (reference lines 2607-2962).
   The library owns: tool geometry, hit tests, placement rules, selection, magnet, JSON model.
   This block owns what the library leaves to the host:
     repo      load/save adapter (Promise-based; swap the bodies for REST calls)
     history   undo / redo (Ctrl/Cmd+Z, Ctrl+Shift+Z, Ctrl+Y)
     toolbar   buttons generated from TOOLBAR + magnet + remove
     text      inline editor for the Text tool
     drag      press-drag-release also finishes a 2-point tool (TradingView behaviour) */
import * as Lib from 'lightweight-charts-drawing';
import type { Ctx } from './context';
import { store } from './context';

export function initDrawings(ctx: Ctx) {
  const { chart, candle, container, SYMBOL, dates, Hist, volCtl, Ind } = ctx;
  const LibAny = Lib as any;
  const wrap = container.parentElement as HTMLElement;

  /* ---- persistence adapter (backend: replace the bodies with fetch calls) ---- */
  const repo = {
    key: (symbol: string) => `ml.drawings.${symbol}`,
    load: (symbol: string) => Promise.resolve(store.get(repo.key(symbol)) || '[]'),
    save: (symbol: string, json: string) => { store.set(repo.key(symbol), json); return Promise.resolve() }
  };

  const prefs = { magnet: store.get('ml.draw.magnet') === '1' };
  /* every new drawing starts black; fib levels follow, semantic colours (long/short position) are kept */
  const INK = '#171717';
  LibAny.setDefaultStyleOverride((kind: string) => {
    const base = LibAny.factoryStyleFor(kind), o: any = { color:INK, textColor:INK };
    if(Array.isArray(base.levels)){ o.levels = base.levels.map((l: any) => ({ ...l, color:INK })); o.fillBackground = false }   // black bands would stack into a grey slab
    return o;
  });
  const dm = new LibAny.DrawingManager(chart, candle, { magnet: prefs.magnet ? 'weak' : 'off', stayInDrawingMode: false });
  const listeners: ((json: string) => void)[] = [];

  /* ---- history: one snapshot per finished gesture / command ---- */
  let base = dm.exportJSON(), pressed = false, timer: any = 0;
  const setDrawings = (json: string) => { dm.importJSON(json); base = dm.exportJSON(); repo.save(SYMBOL, base); listeners.forEach(fn => fn(base)); syncRemove() };
  const settle = () => {
    const now = dm.exportJSON();
    if(now === base) return;
    const before = base; base = now;
    Hist.push({ undo:() => setDrawings(before), redo:() => setDrawings(now) });
    repo.save(SYMBOL, now); listeners.forEach(fn => fn(now)); syncRemove();
  };
  const queueSettle = () => { clearTimeout(timer); timer = setTimeout(settle, 0) };
  dm.on('change', () => { if(!pressed) queueSettle() });
  container.addEventListener('pointerdown', () => { pressed = true }, true);
  window.addEventListener('pointerup', () => { pressed = false; queueSettle() });

  /* ---- drag-release finishes a 2-point tool (the library places a point on press only) ---- */
  const isTwoPoint = (kind: string | null) => { const s = kind && LibAny.OVERLAY_SPECS[kind]; return !!s && s.pointCount === 2 && !s.variableLength && !s.freehand };
  let press: { x: number; y: number; count: number; synthetic: boolean } | null = null;
  container.addEventListener('pointerdown', (e: any) => {
    const kind = dm.tool();
    press = (e.button === 0 && isTwoPoint(kind)) ? { x:e.clientX, y:e.clientY, count:dm.drawings().length, synthetic:!!e.__synthetic } : null;
  }, true);
  window.addEventListener('pointerup', (e: any) => {
    const p = press; press = null;
    if(!p || e.__synthetic || !isTwoPoint(dm.tool()) || dm.drawings().length !== p.count) return;   // first point not pending any more
    if(Math.hypot(e.clientX - p.x, e.clientY - p.y) < 6) return;                                       // a plain click: wait for the 2nd click
    const target = document.elementFromPoint(e.clientX, e.clientY) || container;
    const fire = (type: string) => { const ev: any = new PointerEvent(type, { bubbles:true, cancelable:true, composed:true, clientX:e.clientX, clientY:e.clientY, button:0, buttons:type === 'pointerdown' ? 1 : 0, pointerId:1, isPrimary:true, pointerType:e.pointerType }); ev.__synthetic = true; target.dispatchEvent(ev) };
    fire('pointerdown'); fire('pointerup');
  });

  /* ---- text editor ---- */
  const input = document.createElement('input');
  input.className = 'dr-text'; input.hidden = true; input.placeholder = 'Text'; input.setAttribute('aria-label', 'Drawing text');
  wrap.appendChild(input);
  let editing: { id: string } | null = null;
  const closeText = (save: boolean) => {
    if(!editing) return;
    const { id } = editing, v = input.value.trim(); editing = null; input.hidden = true;
    const cur = dm.get(id); if(!cur) return;
    if(save && v) dm.update({ ...cur, text:v }); else if(!cur.text) dm.remove(id);
  };
  dm.on('textEdit', (d: any, at: any) => {
    editing = { id:d.id };
    input.style.left = (chart.priceScale('left').width() + at.x) + 'px'; input.style.top = at.y + 'px';
    input.value = d.text || ''; input.hidden = false; setTimeout(() => { input.focus(); input.select() }, 0);
  });
  input.addEventListener('keydown', e => { if(e.key === 'Enter'){ e.preventDefault(); closeText(true) } else if(e.key === 'Escape'){ e.stopPropagation(); closeText(false) } });
  input.addEventListener('blur', () => closeText(true));

  /* ---- toolbar (generated) ---- */
  const svg = (body: string) => `<svg viewBox="0 0 28 28" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  const TOOLBAR = [
    { kind:null,              label:'Crosshair',       icon:svg('<path d="M14 5v6.5M14 16.5V23M5 14h6.5M16.5 14H23"/>') },
    { kind:'trend-line',      label:'Trend line',      icon:svg('<path d="M8.5 19.5L19.5 8.5"/><circle cx="7" cy="21" r="2"/><circle cx="21" cy="7" r="2"/>') },
    { kind:'fib-retracement', label:'Fib retracement', icon:svg('<path d="M9.5 9h13M9.5 14h13M9.5 19h13"/><circle cx="7" cy="9" r="1.8"/><circle cx="7" cy="19" r="1.8"/>') },
    { kind:'xabcd-pattern',   label:'XABCD pattern',   icon:svg('<path d="M6.5 19.5l3.5-11 6 9 3-8 3.5 9.5"/><circle cx="6.5" cy="19.5" r="1.7"/><circle cx="10" cy="8.5" r="1.7"/><circle cx="16" cy="17.5" r="1.7"/><circle cx="19" cy="9.5" r="1.7"/><circle cx="22.5" cy="19" r="1.7"/>') },
    { kind:'long-position',   label:'Long position',   icon:svg('<path d="M10 8h12M10 14h12M10 21h12"/><circle cx="7" cy="8" r="1.8"/><circle cx="7" cy="21" r="1.8"/><path d="M15.5 15.5v4h3"/>') },
    { kind:'brush',           label:'Brush',           icon:svg('<path d="M6 21c4-2 5-10 9-10 3 0 2.5 5-.5 8"/><path d="M19 8l2 2 3.5-3.5"/>') },
    { kind:'text',            label:'Text',            icon:svg('<path d="M8 8h12M14 8v13"/>') }
  ];
  const bar = document.createElement('div');
  bar.className = 'dr-bar'; bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', 'Drawing tools'); bar.setAttribute('aria-orientation', 'vertical');
  const button = (label: string, icon: string, onclick: () => void) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'dr-btn'; b.dataset.label = label; b.setAttribute('aria-label', label); b.innerHTML = icon; b.onclick = onclick; bar.appendChild(b); return b;
  };
  const separator = () => { const i = document.createElement('i'); i.className = 'dr-sep'; bar.appendChild(i) };
  TOOLBAR.forEach(t => { const b = button(t.label, t.icon, () => dm.setTool(t.kind && dm.tool() !== t.kind ? t.kind : null)); b.dataset.tool = t.kind || '' });
  separator();
  const magnet = button('Magnet', svg('<path d="M9 7v7a5 5 0 0 0 10 0V7"/><path d="M9 7h3.5v7a1.5 1.5 0 0 0 3 0V7H19"/>'), () => { prefs.magnet = !prefs.magnet; store.set('ml.draw.magnet', prefs.magnet ? '1' : '0'); syncMagnet() });
  separator();
  const rm = button('Remove drawings', svg('<path d="M8.5 10h11M12 10V8h4v2M10 10l.8 10h6.4l.8-10"/>'), () => {
    const sel = dm.selection(); sel.length ? sel.forEach((id: string) => dm.remove(id)) : dm.clear();
  });
  wrap.appendChild(bar);

  function syncTool(kind: string | null) {
    if(LINES.some(l => l.id === kind)){ lineType = kind as string; store.set('ml.draw.line', kind as string); syncLineButton() }
    const inGroup = (id: string | undefined) => id === 'trend-line' && LINES.some(l => l.id === kind);
    bar.querySelectorAll<HTMLElement>('.dr-btn[data-tool]').forEach(b => { const on = b.dataset.tool === (kind || '') || inGroup(b.dataset.tool); b.classList.toggle('active', on); b.setAttribute('aria-pressed', String(on)) });
    wrap.classList.toggle('dr-tool', !!kind);
    applyCursor();
  }
  function syncMagnet() {
    dm.setMagnet(prefs.magnet ? 'weak' : 'off');
    magnet.classList.toggle('active', prefs.magnet); magnet.setAttribute('aria-pressed', String(prefs.magnet));
    magnet.dataset.label = prefs.magnet ? 'Magnet on (snaps to candles)' : 'Magnet off';
  }
  function syncRemove() {
    const sel = dm.selection().length > 0, any = dm.drawings().length > 0;
    rm.disabled = !sel && !any;
    rm.dataset.label = sel ? 'Remove selected drawing' : 'Remove all drawings'; rm.setAttribute('aria-label', rm.dataset.label);
  }
  const fitBar = () => { bar.style.bottom = chart.timeScale().height() + 'px' };
  new ResizeObserver(fitBar).observe(container); fitBar();

  /* ---- cursor type (Cross / Dot / Arrow / Demonstration) ----
     One setting, applied in one place (applyCursor): crosshair lines + axis labels on both charts,
     the native mouse cursor (CSS classes) and a small overlay canvas for Dot and Demonstration.
     While a drawing tool is armed the cursor falls back to Cross, so placing points stays precise. */
  const CURSORS = [
    { id:'cross', label:'Cross',         icon:svg('<path d="M14 5v6.5M14 16.5V23M5 14h6.5M16.5 14H23"/>') },
    { id:'dot',   label:'Dot',           icon:svg('<circle cx="14" cy="14" r="2.8" fill="currentColor" stroke="none"/>') },
    { id:'arrow', label:'Arrow',         icon:svg('<path d="M9.5 6.5v15l3.8-3.6 2.9 5.8 2.5-1.2-2.9-5.6h5.2z"/>') },
    { id:'demo',  label:'Demonstration', icon:svg('<circle cx="14" cy="14" r="10"/><path d="M11.2 9.8v8.6l2.3-2.1 1.8 3.4 1.5-.8-1.8-3.2h3.1z"/>') }
  ];
  let cursorType = store.get('ml.draw.cursor') as string; if(!CURSORS.some(c => c.id === cursorType)) cursorType = 'cross';
  const effCursor = () => dm.tool() ? 'cross' : cursorType;

  const fx = document.createElement('canvas'); fx.className = 'dr-fx'; wrap.insertBefore(fx, bar);
  const fxc = fx.getContext('2d') as CanvasRenderingContext2D;
  let mouse: { x: number; y: number } | null = null, trail: { x: number; y: number; t: number }[] = [], raf = 0;
  const sizeFx = () => { const r = wrap.getBoundingClientRect(), k = window.devicePixelRatio || 1; fx.width = r.width * k; fx.height = r.height * k; fxc.setTransform(k, 0, 0, k, 0, 0) };
  new ResizeObserver(sizeFx).observe(wrap); sizeFx();
  const plotBox = () => {                                   // chart-plot rectangle in wrap coordinates
    const w = wrap.clientWidth, h = wrap.clientHeight;
    const l = chart.priceScale('left').width(), r = chart.priceScale('right').width(), b = chart.timeScale().height();
    return { x0:l, x1:w - r, y0:0, y1:h - b };
  };
  function paintFx(now: number) {
    fxc.clearRect(0, 0, fx.width, fx.height);
    const t = effCursor();
    if(!mouse || (t !== 'dot' && t !== 'demo')) { trail = []; return }
    if(t === 'dot') {
      fxc.beginPath(); fxc.arc(mouse.x, mouse.y, 2.5, 0, 7); fxc.fillStyle = '#171717'; fxc.fill();
      fxc.lineWidth = 1.5; fxc.strokeStyle = '#fff'; fxc.stroke(); return;
    }
    trail = trail.filter(p => now - p.t < 650);
    for(let i = 1; i < trail.length; i++) {
      const a = trail[i - 1], b = trail[i], age = (now - b.t) / 650;
      fxc.beginPath(); fxc.moveTo(a.x, a.y); fxc.lineTo(b.x, b.y);
      fxc.strokeStyle = `rgba(238,64,64,${(1 - age) * .55})`; fxc.lineWidth = 6 * (1 - age) + 1; fxc.lineCap = 'round'; fxc.stroke();
    }
    fxc.beginPath(); fxc.arc(mouse.x, mouse.y, 13, 0, 7); fxc.fillStyle = 'rgba(238,64,64,.28)'; fxc.fill();
    fxc.lineWidth = 1.5; fxc.strokeStyle = 'rgba(238,64,64,.9)'; fxc.stroke();
    fxc.beginPath(); fxc.arc(mouse.x, mouse.y, 3, 0, 7); fxc.fillStyle = '#ee4040'; fxc.fill();
    if(trail.length) raf = requestAnimationFrame(paintFx);
  }
  const repaint = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(paintFx) };
  wrap.addEventListener('pointermove', (e: any) => {
    const r = wrap.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, b = plotBox();
    const live = x > Math.max(b.x0, 41) && x < b.x1 && y > b.y0 && y < b.y1 && !e.target.closest('.dr-bar,.dr-menu');
    wrap.classList.toggle('cur-live', live);
    mouse = live ? { x, y } : null;
    if(mouse && effCursor() === 'demo') trail.push({ x, y, t:performance.now() });
    repaint();
  });
  wrap.addEventListener('pointerleave', () => { mouse = null; wrap.classList.remove('cur-live'); trail = []; repaint() });

  function applyCursor() {
    const t = effCursor(), lines = t === 'cross', labels = t === 'cross' || t === 'dot';
    chart.applyOptions({ crosshair:{ vertLine:{ visible:lines, labelVisible:labels }, horzLine:{ visible:lines, labelVisible:labels } } });
    ctx.flowChart.applyOptions({ crosshair:{ vertLine:{ visible:lines, labelVisible:labels }, horzLine:{ visible:lines } } });
    CURSORS.forEach(c => wrap.classList.toggle('cur-' + c.id, c.id === t));
    const cur = CURSORS.find(c => c.id === cursorType)!;
    cb.innerHTML = cur.icon; cb.dataset.label = 'Cursor: ' + cur.label; cb.setAttribute('aria-label', cb.dataset.label);
    cursorMenu.check(cursorType);
    repaint();
  }

  /* ---- toolbar pop-up menus (cursor type, line tools) share one small factory ---- */
  interface MenuItem { id: string; label: string; icon: string; keys?: string }
  interface Menu { el: HTMLElement; items: MenuItem[]; check(id: string): void; close(refocus: boolean): void; open(): void }
  const menus: Menu[] = [];
  function popMenu(btn: HTMLElement, items: MenuItem[], opt: { label: string; wide?: boolean; beforeOpen?: () => void; pick: (it: any) => void }) {
    const el = document.createElement('div');
    el.className = 'dr-menu' + (opt.wide ? ' wide' : ''); el.hidden = true; el.setAttribute('role', 'menu'); el.setAttribute('aria-label', opt.label);
    btn.classList.add('has-menu'); btn.setAttribute('aria-haspopup', 'menu'); btn.setAttribute('aria-expanded', 'false');
    items.forEach(it => {
      const m = document.createElement('button');
      m.type = 'button'; m.className = 'dr-mi'; m.dataset.id = it.id; m.setAttribute('role', 'menuitemradio');
      m.innerHTML = it.icon + '<span>' + it.label + '</span>' + (it.keys ? '<kbd>' + it.keys + '</kbd>' : '');
      m.onclick = () => { close(true); opt.pick(it) };
      el.appendChild(m);
    });
    wrap.appendChild(el);
    const api: Menu = { el, items,
      check: id => el.querySelectorAll<HTMLElement>('.dr-mi').forEach(m => m.setAttribute('aria-checked', String(m.dataset.id === id))),
      close, open };
    function close(refocus: boolean) { el.hidden = true; btn.setAttribute('aria-expanded', 'false'); if(refocus) btn.focus() }
    function open() {
      menus.forEach(x => x !== api && x.close(false));
      el.style.top = (bar.offsetTop + btn.offsetTop) + 'px'; el.hidden = false; btn.setAttribute('aria-expanded', 'true');
      ((el.querySelector('[aria-checked="true"]') || el.firstChild) as HTMLElement).focus();
    }
    btn.onclick = () => { if(el.hidden){ if(opt.beforeOpen) opt.beforeOpen(); open() } else close(false) };
    document.addEventListener('pointerdown', e => { if(!el.hidden && !el.contains(e.target as Node) && !btn.contains(e.target as Node)) close(false) });
    el.addEventListener('keydown', e => {
      const list = [...el.children] as HTMLElement[], k = list.indexOf(document.activeElement as HTMLElement);
      if(e.key === 'Escape') { e.stopPropagation(); close(true) }
      else if(e.key === 'ArrowDown') { e.preventDefault(); list[(k + 1) % list.length].focus() }
      else if(e.key === 'ArrowUp') { e.preventDefault(); list[(k + list.length - 1) % list.length].focus() }
    });
    menus.push(api); return api;
  }

  /* cursor menu: the first toolbar button */
  const cb = bar.querySelector('.dr-btn[data-tool=""]') as HTMLElement;
  const cursorMenu = popMenu(cb, CURSORS, {
    label:'Cursor type',
    beforeOpen: () => dm.setTool(null),                       // opening the cursor menu leaves any armed drawing tool
    pick: c => { cursorType = c.id; store.set('ml.draw.cursor', c.id); dm.setTool(null); applyCursor() }
  });

  /* line menu: the Trend line button groups the line-type tools */
  const LINES: MenuItem[] = [
    { id:'trend-line',      label:'Trend line',      keys:'Alt + T', icon:TOOLBAR.find(t => t.kind === 'trend-line')!.icon },
    { id:'horizontal-line', label:'Horizontal line', keys:'Alt + H', icon:svg('<path d="M5 14h6.8M16.2 14H23"/><circle cx="14" cy="14" r="2.2"/>') },
    { id:'horizontal-ray',  label:'Horizontal ray',  keys:'Alt + J', icon:svg('<circle cx="7" cy="14" r="2.2"/><path d="M9.2 14H23"/>') },
    { id:'vertical-line',   label:'Vertical line',   keys:'Alt + V', icon:svg('<path d="M14 5v6.8M14 16.2V23"/><circle cx="14" cy="14" r="2.2"/>') }
  ];
  let lineType = store.get('ml.draw.line') as string; if(!LINES.some(l => l.id === lineType)) lineType = 'trend-line';
  const lb = bar.querySelector('.dr-btn[data-tool="trend-line"]') as HTMLElement;
  const lineMenu = popMenu(lb, LINES, { label:'Lines', wide:true, pick: l => dm.setTool(l.id) });
  function syncLineButton() {
    const l = LINES.find(x => x.id === lineType)!;
    lb.innerHTML = l.icon; lb.dataset.label = l.label; lb.setAttribute('aria-label', l.label); lineMenu.check(lineType);
  }
  /* the reference subscribes these after its menus exist; events before then cannot happen (no tool is armed yet) */
  dm.on('tool', syncTool); dm.on('selection', syncRemove); dm.on('change', syncRemove);
  let lastPtr: { x: number; y: number; t: number } | null = null;
  document.addEventListener('keydown', (e: any) => {
    if(!e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const hit = ({ KeyT:'trend-line', KeyH:'horizontal-line', KeyJ:'horizontal-ray', KeyV:'vertical-line' } as Record<string, string>)[e.code];
    if(!hit) return;
    e.preventDefault(); dm.setTool(hit);
    /* one-click lines are placed straight away at the pointer, like TradingView; Alt+T just arms the tool */
    if(hit !== 'trend-line' && lastPtr && Date.now() - lastPtr.t < 60000){
      const el = document.elementFromPoint(lastPtr.x, lastPtr.y);
      if(el && container.contains(el)){
        const o: any = { bubbles:true, cancelable:true, composed:true, view:window, clientX:lastPtr.x, clientY:lastPtr.y, button:0, buttons:1, pointerId:1, pointerType:'mouse', isPrimary:true };
        el.dispatchEvent(new PointerEvent('pointerdown', o)); el.dispatchEvent(new MouseEvent('mousedown', o));
        o.buttons = 0;
        el.dispatchEvent(new PointerEvent('pointerup', o)); el.dispatchEvent(new MouseEvent('mouseup', o)); el.dispatchEvent(new MouseEvent('click', o));
      }
    }
  });
  container.addEventListener('pointermove', e => { lastPtr = { x:e.clientX, y:e.clientY, t:Date.now() } });
  container.addEventListener('pointerleave', () => { lastPtr = null });

  /* ---- vertical pan for the left (candle) price scale ----
     Lightweight Charts only moves the default (right) scale when you drag the chart up/down.
     Once the left axis has been dragged by hand (auto-fit off), the same drag moves it too, so both axes behave alike. */
  {
    let pan: { y: number; from: number; to: number; h: number } | null = null;
    const leftManual = () => { const o: any = chart.priceScale('left').options(); return o.autoScale === false && o.mode === 0 };
    container.addEventListener('pointerdown', e => {
      /* pressing the left axis freezes its current range (auto-fit off) — what a press on the right axis does for the lines */
      if(e.button === 0 && !dm.tool()){
        const ps0 = chart.priceScale('left'), r0 = container.getBoundingClientRect(), o0: any = ps0.options(), v0 = ps0.getVisibleRange();
        if(e.clientX - r0.left < ps0.width() && o0.autoScale !== false && o0.mode === 0 && v0) ps0.setVisibleRange({ from:v0.from, to:v0.to });
      }
      if(e.button !== 0 || dm.tool() || !leftManual()) return;
      const r = container.getBoundingClientRect(), pane = chart.panes()[0], ps = chart.priceScale('left'), v = ps.getVisibleRange();
      if(!pane || !v || e.clientY - r.top > pane.getHeight()) return;                // axis strips / time axis keep their own behaviour
      const rightW = chart.priceScale('right').width(), leftW = ps.width();
      if(e.clientX - r.left < leftW || r.right - e.clientX < rightW) return;
      pan = { y:e.clientY, from:v.from, to:v.to, h:pane.getHeight() };
    }, true);
    window.addEventListener('pointermove', e => {
      if(!pan) return;
      const m: any = chart.priceScale('left').options().scaleMargins, inner = pan.h * (1 - m.top - m.bottom), d = (e.clientY - pan.y) / inner * (pan.to - pan.from);
      chart.priceScale('left').setVisibleRange({ from:pan.from + d, to:pan.to + d });
    });
    ['pointerup', 'pointercancel'].forEach(t => window.addEventListener(t, () => { pan = null }));
  }

  /* ---- right-click menu: Reset chart view / Remove drawings / Remove indicators ---- */
  /* "home" = the view the chart settles into after it opens (bars shown, latest bar at the right edge) */
  let home: { span: number; end: number } | null = null;
  setTimeout(() => { const r = chart.timeScale().getVisibleLogicalRange(); if(r) home = { span:r.to - r.from, end:r.to - dates.length } }, 1200);
  function resetView() {
    if(home) chart.timeScale().setVisibleLogicalRange({ from:dates.length + home.end - home.span, to:dates.length + home.end });
    else chart.timeScale().resetTimeScale();
    ['left','right'].forEach(id => chart.priceScale(id).applyOptions({ autoScale:true }));
  }
  const iconReset = svg('<path d="M8.5 14a5.5 5.5 0 1 0 1.8-4.1"/><path d="M8.5 7.5v3.4h3.4"/>');
  const iconTrash = svg('<path d="M8.5 10h11M12 10V8h4v2M10 10l.8 10h6.4l.8-10"/>');
  const iconInd   = svg('<path d="M5.5 18l4.5-5 3 3 5-7 4 4.5"/>');
  const menuEl = document.createElement('div');
  menuEl.className = 'dr-menu ctx'; menuEl.tabIndex = -1; menuEl.hidden = true; menuEl.setAttribute('role', 'menu'); menuEl.setAttribute('aria-label', 'Chart actions');
  wrap.appendChild(menuEl);
  const closeCtx = () => { menuEl.hidden = true };
  function ctxItem(icon: string, label: string, keys: string, enabled: boolean, run: () => void, into: HTMLElement = menuEl) {
    const m = document.createElement('button');
    m.type = 'button'; m.className = 'dr-mi'; m.setAttribute('role', 'menuitem'); m.disabled = !enabled;
    m.innerHTML = icon + '<span>' + label + '</span>' + (keys ? '<kbd>' + keys + '</kbd>' : '');
    m.onclick = () => { into.hidden = true; run() }; into.appendChild(m);
  }
  function openCtx(x: number, y: number) {
    const sel = dm.selection().length, all = dm.drawings().length, n = sel || all, ind = (volCtl.removed ? 0 : 1) + Ind.count();
    menuEl.innerHTML = '';
    ctxItem(iconReset, 'Reset chart view', 'Alt + R', true, resetView);
    menuEl.appendChild(Object.assign(document.createElement('i'), { className:'dr-msep' }));
    ctxItem(iconTrash, n ? `Remove ${n} drawing${n > 1 ? 's' : ''}` : 'Remove drawings', '', n > 0, () => { sel ? dm.selection().forEach((id: string) => dm.remove(id)) : dm.clear() });
    ctxItem(iconInd, ind ? `Remove ${ind} indicator${ind > 1 ? 's' : ''}` : 'Remove indicators', '', ind > 0, () => { volCtl.setRemoved(true); Ind.removeAll() });
    menuEl.hidden = false;
    const w = wrap.clientWidth, h = wrap.clientHeight;
    menuEl.style.left = Math.max(4, Math.min(x, w - menuEl.offsetWidth - 4)) + 'px';
    menuEl.style.top  = Math.max(4, Math.min(y, h - menuEl.offsetHeight - 4)) + 'px';
    menuEl.focus({ preventScroll:true });                     // keyboard users press ↓ to enter the list; no focus ring after a mouse click
  }
  wrap.addEventListener('contextmenu', (e: any) => {
    if(e.target.closest('.dr-bar,.dr-menu,.dr-text')) return;
    e.preventDefault(); menus.forEach(m => m.close(false));
    const r = wrap.getBoundingClientRect(); openCtx(e.clientX - r.left, e.clientY - r.top);
  });
  document.addEventListener('pointerdown', e => { if(!menuEl.hidden && !menuEl.contains(e.target as Node)) closeCtx() });
  window.addEventListener('blur', closeCtx); window.addEventListener('resize', closeCtx);
  const menuKeys = (el: HTMLElement) => el.addEventListener('keydown', e => {
    const list = [...el.querySelectorAll<HTMLElement>('.dr-mi:not([disabled])')], k = list.indexOf(document.activeElement as HTMLElement);
    if(!list.length) return;
    if(e.key === 'Escape'){ e.stopPropagation(); el.hidden = true }
    else if(e.key === 'ArrowDown'){ e.preventDefault(); list[(k + 1) % list.length].focus() }
    else if(e.key === 'ArrowUp'){ e.preventDefault(); list[(k + list.length - 1) % list.length].focus() }
  });
  menuKeys(menuEl);

  /* EXEC-TERMINAL-UI-1026 U2 (user 2026-10-26: "klik kanan reset chart view di panel flow timeline maka akan reset chart
     dibawah agar rapih"; option A): the Flow Timeline's own menu resets its value scales only; the price chart and the
     shared time range stay as they are */
  {
    const fwrap = document.getElementById('flowChart')!.parentElement as HTMLElement;   // .flow-wrap
    let fmenu: HTMLElement | null = null;                     // built on the first right-click (the page's markup stays the reference's)
    const menu = () => {
      if(fmenu) return fmenu;
      const el = fmenu = document.createElement('div');
      el.className = 'dr-menu ctx'; el.tabIndex = -1; el.hidden = true; el.setAttribute('role', 'menu'); el.setAttribute('aria-label', 'Flow Timeline actions');
      fwrap.appendChild(el); menuKeys(el);
      document.addEventListener('pointerdown', e => { if(!el.hidden && !el.contains(e.target as Node)) el.hidden = true });
      window.addEventListener('blur', () => { el.hidden = true }); window.addEventListener('resize', () => { el.hidden = true });
      return el;
    };
    const resetFlow = () => ['left', 'right'].forEach(id => ctx.flowChart.priceScale(id).applyOptions({ autoScale:true }));
    fwrap.addEventListener('contextmenu', (e: any) => {
      if(e.target.closest('.dr-menu')) return;
      e.preventDefault(); closeCtx(); menus.forEach(m => m.close(false));
      const el = menu();
      el.innerHTML = ''; ctxItem(iconReset, 'Reset chart view', '', true, resetFlow, el);
      el.hidden = false;
      const r = fwrap.getBoundingClientRect();
      el.style.left = Math.max(4, Math.min(e.clientX - r.left, fwrap.clientWidth - el.offsetWidth - 4)) + 'px';
      el.style.top  = Math.max(4, Math.min(e.clientY - r.top, fwrap.clientHeight - el.offsetHeight - 4)) + 'px';
      el.focus({ preventScroll:true });
    });
  }
  document.addEventListener('keydown', (e: any) => { if(e.altKey && e.code === 'KeyR' && !e.ctrlKey && !e.metaKey && !/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)){ e.preventDefault(); resetView() } });

  syncTool(null); syncMagnet(); syncRemove(); syncLineButton(); applyCursor();

  /* drawings are price-based: hide them while the chart shows % returns */
  ctx.onDisplayMode = () => dm.setDrawingsVisible(ctx.displayMode !== 'return');

  repo.load(SYMBOL).then(json => { dm.importJSON(json); base = dm.exportJSON(); syncRemove() });

  /* public surface for the backend integration (the reference's importJSON also cleared an undefined history list,
     which threw; the undo timeline is shared with the indicators and is left as is) */
  const Drawings = {
    exportJSON: () => dm.exportJSON(),
    importJSON: (json: string) => { dm.importJSON(json); base = dm.exportJSON(); syncRemove() },
    onChange: (fn: (json: string) => void) => listeners.push(fn),
    manager: dm
  };
  (window as any).marketLabDrawings = Drawings;
  return Drawings;
}
