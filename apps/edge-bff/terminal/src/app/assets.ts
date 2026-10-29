/* ADDED ASSETS — EXEC-TERMINAL-ASSETS (user 2026-10-28, live only; the fixture keeps the reference's Add Series panel).
   "ketika kita add asset, maka yang keluar adalah search box exactly sama seperti kalau kita search ticker ... maksimal 2";
   "Tampilannya seperti screenshot" (legend row: logo, name · IDX, change; settings dialog Inputs / Style / Visibility);
   "Menambah aset hanya menambah flow timeline di bawah. Badge untuk aset flow timeline juga harus jelas" — the right panel
   stays the chart's own ticker. Answers: Q2 at most 2 assets besides the chart's ticker; Q3 (a) each asset has its own
   Flow Timeline, one under the other; Q4 each with its own filters (the same defaults); Q5 each asset on its own scale
   (the first on the right axis, the next on an unlabelled scale of its own; Scale in the Style tab).
     + (toolbar)  the ticker search, picking adds an asset
     legend row   change from the previous candle (or the return in Return mode); eye, settings, remove on hover
     dialog       Inputs: Symbol · Style: chart type, price source, colour and width, price line, scale, min tick ·
                  Visibility: on the chart, Flow Timeline
     Flow pane    one per asset (Visibility → Flow Timeline): net bars and the cumulative line on the chart's sessions,
                  locked to the chart's time range, crosshair and axis widths; its drawings are kept under its ticker */
import type { Ctx, FilterApi } from './context';
import { $, brokerEnd, cls, hasLogos, logoHtml, keyOf, rupiah, spin, store } from './context';
import { cumulativeFrom, FLOW_CUMULATIVE_FROM } from './flow';
import type { Bar, Combo, Instrument } from '../data/types';
import { UNIT } from '../data/timeframe';

export const MAX_ASSETS = 2;
export const ASSET_COLORS = ['#2962ff', '#f57c00'];
export type AssetStyle = 'line' | 'step' | 'area' | 'bars' | 'candles';
export type AssetSource = 'close' | 'open' | 'high' | 'low' | 'hl2' | 'hlc3' | 'ohlc4';
export type AssetScale = 'right' | 'left' | 'own';
export interface AssetOpts {
  style: AssetStyle; source: AssetSource; color: string; width: number; priceLine: boolean;
  minTick: 'default' | '1' | '0.1' | '0.01' | '0.001'; scale: AssetScale; visible: boolean; flow: boolean;
}
const STYLES: [AssetStyle, string][] = [['line', 'Line'], ['step', 'Step line'], ['area', 'Area'], ['bars', 'Bars'], ['candles', 'Candles']];
const SOURCES: [AssetSource, string][] = [['close', 'Close'], ['open', 'Open'], ['high', 'High'], ['low', 'Low'], ['hl2', '(H + L) / 2'], ['hlc3', '(H + L + C) / 3'], ['ohlc4', '(O + H + L + C) / 4']];
const SCALES: [AssetScale, string][] = [['right', 'Right axis'], ['left', 'Left axis (main)'], ['own', 'Own scale (no labels)']];
const TICKS: [AssetOpts['minTick'], string][] = [['default', 'Default'], ['1', '1'], ['0.1', '0.1'], ['0.01', '0.01'], ['0.001', '0.001']];
const PALETTE = ['#2962ff', '#f57c00', '#7928ca', '#12a594', '#d6409f', '#0070f3', '#171717', '#8f8f8f', '#f5a623'];

/** a new asset's settings: the slot's colour; the right axis unless another asset is on it already (Q5) */
export function defaultOpts(slot: number, others: AssetOpts[]): AssetOpts {
  return { style:'line', source:'close', color:ASSET_COLORS[slot % ASSET_COLORS.length], width:2, priceLine:false, minTick:'default',
    scale:others.some(o => o.scale === 'right') ? 'own' : 'right', visible:true, flow:true };
}
export function sourceOf(b: Bar, s: AssetSource): number {
  switch (s) {
    case 'open': return b.open; case 'high': return b.high; case 'low': return b.low;
    case 'hl2': return (b.high + b.low) / 2; case 'hlc3': return (b.high + b.low + b.close) / 3;
    case 'ohlc4': return (b.open + b.high + b.low + b.close) / 4; default: return b.close;
  }
}
/** the legend figure on candle i: the change from the asset's previous candle in %, or in Return mode its return from
    its first candle; null when the asset has no candle there */
export function legendPct(bars: Bar[], at: number, source: AssetSource, ret: boolean): number | null {
  const b = bars[at]; if (!b) return null;
  const v = sourceOf(b, source);
  if (ret) { const base = sourceOf(bars[0], source); return base ? (v / base - 1) * 100 : null }
  const p = bars[at - 1]; if (!p) return null;
  const pv = sourceOf(p, source); return pv ? (v / pv - 1) * 100 : null;
}
const KEY = 'ml.assets.v1', DEF_KEY = 'ml.assets.defaults';
const fmtPct = (v: number | null) => v === null || !Number.isFinite(v) ? '' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) + '%';
const esc = (t: string) => String(t).replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]!));
const rgba = (hex: string, a: number) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})` };

interface FlowPane {
  el: HTMLElement; chart: any; bars: any; cum: any; netBadge: any; cumBadge: any;
  combos: Combo[]; from: number; to: number; end: number; state: 'loading' | 'more' | 'ready' | 'failed';
  flt: { brokers: Set<string>; boards: Set<string>; investors: Set<string> }; filters: FilterApi[];
  net: Float64Array; cumArr: Float64Array<ArrayBuffer>; drawings: { detach(): void } | null; collapsed: boolean; alive: boolean;
  synced: boolean;                                       // the pane has taken the chart's range once: from then on it moves the chart too
  over: boolean;                                         // the pointer is on the pane (only then it moves the chart: EXEC-TERMINAL-LAG)
  through?: string; noData: HTMLElement; placeNoData: () => void;
}
interface Asset { ticker: string; name: string; opts: AssetOpts; bars: Bar[]; at: Map<string, number>; series: any; row: HTMLElement;
  state: 'loading' | 'ready' | 'failed'; pane: FlowPane | null }

export function initAssets(ctx: Ctx) {
  if (ctx.M.mode !== 'live' || !ctx.M.loadAsset) return;
  const { L, chart, SYMBOL, dates, N, idxByTime, INSTRUMENTS } = ctx;
  const assets: Asset[] = [];
  const nameOf = (t: string) => (INSTRUMENTS.find(r => r[0] === t) || [t, t])[1] as string;
  const known = new Set(INSTRUMENTS.map(r => r[0]));
  const save = () => store.set(KEY, JSON.stringify(assets.map(a => ({ ticker:a.ticker, opts:a.opts }))));
  const savedDefaults = (): Partial<AssetOpts> => { try { return JSON.parse(store.get(DEF_KEY) || '{}') } catch { return {} } };
  const ret = () => ctx.displayMode === 'return';
  const barAt = (a: Asset, i: number) => { const k = a.at.get(dates[i]); return k === undefined ? -1 : k };

  /* ---- the + button: the ticker search; at most MAX_ASSETS ---- */
  const plus = $('toggleAddPanel') as HTMLButtonElement;
  const syncPlus = () => {
    const full = assets.length >= MAX_ASSETS;
    plus.classList.toggle('as-full', full); plus.setAttribute('aria-disabled', String(full));
    plus.title = full ? `At most ${MAX_ASSETS} assets: remove one to add another` : 'Add asset';
    plus.setAttribute('aria-label', plus.title);
  };
  const tag = (t: string) => t === SYMBOL ? 'Current' : assets.some(a => a.ticker === t) ? 'Added' : '';
  plus.addEventListener('click', e => {
    e.stopImmediatePropagation();                            // the reference's Add Series panel stays closed
    if (assets.length >= MAX_ASSETS) return;
    ctx.openTickerSearch?.(plus, { label:'Add asset', tag, pick:(r: Instrument) => { if (!tag(r[0])) add(r[0]) } });
  }, true);

  /* ---- legend rows, under the chart's own tooltip row ---- */
  const rows = document.createElement('div'); rows.className = 'as-rows';
  $('flowTip').after(rows);
  const EYE = $('volEye').innerHTML, XICON = $('volX').innerHTML;
  const GEAR = '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2.6l6.4 3.7v7.4L10 17.4l-6.4-3.7V6.3z"/><circle cx="10" cy="10" r="2.3"/></svg>';
  function buildRow(a: Asset) {
    const r = document.createElement('div');
    r.className = 'ind-row as-row';
    r.innerHTML = `${hasLogos() ? logoHtml(a.ticker, 'tk-sm') : ''}<span class="ind-k as-name"></span><b class="as-chg"></b>`
      + `<button class="ind-eye" type="button" data-act="eye" aria-pressed="true" data-label="Hide" aria-label="Show or hide">${EYE}</button>`
      + `<button class="ind-eye ind-cfg" type="button" data-act="cfg" data-label="Settings" aria-label="Settings">${GEAR}</button>`
      + `<button class="ind-eye ind-x" type="button" data-act="del" data-label="Remove" aria-label="Remove">${XICON}</button>`;
    r.addEventListener('click', (e: any) => {
      const b = e.target.closest('[data-act]'); if (!b) return;
      if (b.dataset.act === 'eye') { a.opts.visible = !a.opts.visible; apply(a); save() }
      else if (b.dataset.act === 'cfg') openSettings(a);
      else remove(a);
    });
    r.addEventListener('dblclick', (e: any) => { if (!e.target.closest('[data-act]')) openSettings(a) });
    return r;
  }
  function paintRow(a: Asset, i = ctx.lastTipIdx) {
    const r = a.row;
    (r.querySelector('.as-name') as HTMLElement).textContent = `${a.name} · IDX`;
    (r.querySelector('.as-name') as HTMLElement).title = a.ticker;
    const b = r.querySelector('.as-chg') as HTMLElement;
    if (a.state === 'loading') b.innerHTML = spin('Loading');
    else if (a.state === 'failed') b.textContent = 'Could not be loaded';
    else b.textContent = fmtPct(legendPct(a.bars, barAt(a, Math.min(i, N - 1)), a.opts.source, ret()));
    b.style.color = a.state === 'ready' ? a.opts.color : '';
    b.title = ret() ? 'Return from the first candle' : 'Change from the previous candle';
    r.classList.toggle('off', !a.opts.visible);
    const eye = r.querySelector('[data-act="eye"]') as HTMLElement;
    eye.setAttribute('aria-pressed', String(a.opts.visible)); eye.dataset.label = a.opts.visible ? 'Hide' : 'Show';
  }

  /* ---- the series on the chart ---- */
  const scaleId = (a: Asset) => a.opts.scale === 'own' ? `asset-${a.ticker}` : a.opts.scale;
  const priceFormat = (a: Asset): any => ret() ? ctx.formatMode()
    : a.opts.minTick === 'default' ? { type:'price', precision:2, minMove:.01 }
    : { type:'price', precision:Math.max(0, -Math.log10(+a.opts.minTick)), minMove:+a.opts.minTick };
  function dataOf(a: Asset) {
    const o = a.opts, r = ret(), base = a.bars.length ? (o.style === 'bars' || o.style === 'candles' ? a.bars[0].close : sourceOf(a.bars[0], o.source)) : 1;
    const v = (x: number) => r ? +((x / base - 1) * 100).toFixed(4) : x;
    if (o.style === 'bars' || o.style === 'candles') return a.bars.map(b => ({ time:b.time, open:v(b.open), high:v(b.high), low:v(b.low), close:v(b.close) }));
    return a.bars.map(b => ({ time:b.time, value:v(sourceOf(b, o.source)) }));
  }
  function apply(a: Asset) {
    if (a.series) { try { chart.removeSeries(a.series) } catch (_) {} a.series = null }
    if (a.state === 'ready') {
      const o = a.opts, base = { priceScaleId:scaleId(a), priceLineVisible:o.priceLine, priceLineColor:o.color,
        // an own scale has no axis: its last-value label would sit on the chart's axis as if it were that price
        lastValueVisible:o.scale !== 'own', visible:o.visible, title:'', priceFormat:priceFormat(a) };
      a.series = o.style === 'area' ? chart.addSeries(L.AreaSeries, { ...base, lineColor:o.color, lineWidth:o.width as any, topColor:rgba(o.color, .22), bottomColor:rgba(o.color, 0) })
        : o.style === 'bars' ? chart.addSeries(L.BarSeries, { ...base, upColor:o.color, downColor:o.color })
        : o.style === 'candles' ? chart.addSeries(L.CandlestickSeries, { ...base, upColor:o.color, downColor:rgba(o.color, .25), borderUpColor:o.color, borderDownColor:o.color, wickUpColor:o.color, wickDownColor:o.color })
        : chart.addSeries(L.LineSeries, { ...base, color:o.color, lineWidth:o.width as any, lineType:o.style === 'step' ? L.LineType.WithSteps : L.LineType.Simple, crosshairMarkerRadius:3 });
      if (o.scale === 'own') chart.priceScale(scaleId(a)).applyOptions({ scaleMargins:{ top:.08, bottom:.22 } });
      a.series.setData(dataOf(a));
    }
    paintRow(a);
    setPane(a, a.opts.flow);
  }
  ctx.displayHooks.push(() => assets.forEach(a => { if (a.series) { a.series.setData(dataOf(a)); a.series.applyOptions({ priceFormat:priceFormat(a) }) } paintRow(a) }));
  ctx.tipHooks.push(i => assets.forEach(a => { paintRow(a, i); if (a.pane) paneTip(a, i) }));

  function add(ticker: string, saved?: Partial<AssetOpts>, slot = assets.length) {
    if (!known.has(ticker) || ticker === SYMBOL || assets.some(a => a.ticker === ticker) || assets.length >= MAX_ASSETS) return;
    const others = assets.map(x => x.opts);
    const used = new Set(others.map(o => o.color));
    const opts: AssetOpts = { ...defaultOpts(slot, others), ...savedDefaults(), ...(saved || {}) };
    if (!saved && used.has(opts.color)) opts.color = ASSET_COLORS.find(c => !used.has(c)) || opts.color;
    if (!saved && opts.scale === 'right' && others.some(o => o.scale === 'right')) opts.scale = 'own';
    const a: Asset = { ticker, name:nameOf(ticker), opts, bars:[], at:new Map(), series:null, row:null as any, state:'loading', pane:null };
    a.row = buildRow(a);
    assets.splice(Math.min(slot, assets.length), 0, a);
    rows.replaceChildren(...assets.map(x => x.row));
    paintRow(a); syncPlus(); save();
    setPane(a, a.opts.flow);
    ctx.M.loadAsset!(ticker).then(bars => {
      if (!assets.includes(a)) return;
      a.bars = bars; a.at = new Map(bars.map((b, k) => [b.time, k])); a.state = bars.length ? 'ready' : 'failed'; apply(a);
    }, () => { if (assets.includes(a)) { a.state = 'failed'; paintRow(a) } });
  }
  function remove(a: Asset) {
    const k = assets.indexOf(a); if (k < 0) return;
    assets.splice(k, 1);
    if (a.series) { try { chart.removeSeries(a.series) } catch (_) {} }
    setPane(a, false); a.row.remove(); syncPlus(); save();
  }
  function replace(a: Asset, ticker: string) {
    const slot = assets.indexOf(a), opts = { ...a.opts };
    remove(a); add(ticker, opts, slot);
  }

  /* ---- the settings dialog (the indicators' dialog: same look) ---- */
  const back: any = document.createElement('div');
  back.className = 'idlg-back'; back.hidden = true; document.body.appendChild(back);
  function openSettings(a: Asset) {
    const snap = JSON.stringify(a.opts);
    let tab = 'Inputs';
    back.innerHTML = `<div class="idlg" role="dialog" aria-modal="true" aria-label="${esc(a.name)} settings">
        <div class="idlg-head"><h2></h2><button class="idlg-x" type="button" aria-label="Close">${XICON}</button></div>
        <div class="idlg-tabs" role="tablist">${['Inputs', 'Style', 'Visibility'].map(t => `<button type="button" role="tab" data-tab="${t}">${t}</button>`).join('')}</div>
        <div class="idlg-body"></div>
        <div class="idlg-foot"><select class="idlg-in sm as-defaults" aria-label="Defaults"><option value="" selected disabled>Defaults</option><option value="reset">Reset settings</option><option value="save">Save as default</option></select><span class="sp"></span><button class="idlg-btn" type="button" data-act="cancel">Cancel</button><button class="idlg-btn pri" type="button" data-act="ok">Ok</button></div></div>`;
    back.querySelector('h2').textContent = `${a.name} · IDX`;
    const body = back.querySelector('.idlg-body'), dlg = back.querySelector('.idlg');
    const o = a.opts;
    const live = () => apply(a);
    const row = (label: string, ctl: HTMLElement) => { const l = document.createElement('label'); l.className = 'idlg-row'; const s = document.createElement('span'); s.textContent = label; l.append(s, ctl); return l };
    const sel = (options: [string, string][], value: string, onChange: (v: string) => void, small = false) => {
      const s = document.createElement('select'); s.className = 'idlg-in' + (small ? ' sm' : '');
      options.forEach(([v, t]) => s.add(new Option(t, v, false, v === value))); s.onchange = () => onChange(s.value); return s;
    };
    const check = (on: boolean, onChange: (v: boolean) => void, label: string) => { const c = document.createElement('input'); c.type = 'checkbox'; c.className = 'idlg-cb'; c.checked = on; c.setAttribute('aria-label', label); c.onchange = () => onChange(c.checked); return c };
    const toggle = (on: boolean, onChange: (v: boolean) => void) => {
      const t = document.createElement('span'); t.className = 'toggle t02';
      t.innerHTML = `<input type="checkbox" role="switch" ${on ? 'checked' : ''}><span class="track"></span><span class="thumb"></span>`;
      (t.querySelector('input') as HTMLInputElement).onchange = (e: any) => onChange(e.target.checked); return t;
    };
    let cpop: any = null;
    const closeCpop = () => { if (cpop) { cpop.owner.classList.remove('open'); cpop.remove(); cpop = null } };
    const colorBtn = () => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'idlg-cbtn'; b.setAttribute('aria-label', 'Line colour'); b.style.setProperty('--c', o.color);
      b.onclick = (e: any) => {
        e.preventDefault(); e.stopPropagation(); const was = cpop && cpop.owner === b; closeCpop(); if (was) return;
        cpop = document.createElement('div'); cpop.className = 'idlg-cpop'; cpop.owner = b; b.classList.add('open');
        PALETTE.forEach(c => { const s = document.createElement('button'); s.type = 'button'; s.style.background = c; s.setAttribute('aria-label', c); s.setAttribute('aria-pressed', String(o.color === c));
          s.onclick = (ev: any) => { ev.preventDefault(); ev.stopPropagation(); o.color = c; b.style.setProperty('--c', c); closeCpop(); live() }; cpop.appendChild(s) });
        dlg.appendChild(cpop);
        const br = b.getBoundingClientRect(), dr = dlg.getBoundingClientRect();
        cpop.style.top = (br.bottom - dr.top + 6) + 'px'; cpop.style.left = Math.max(8, br.right - dr.left - cpop.offsetWidth) + 'px';
      };
      return b;
    };
    function paint() {
      closeCpop();
      back.querySelectorAll('[data-tab]').forEach((b: any) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
      body.innerHTML = '';
      if (tab === 'Inputs') {
        const b = document.createElement('button'); b.type = 'button'; b.className = 'idlg-in as-sym';
        b.innerHTML = `${hasLogos() ? logoHtml(a.ticker, 'tk-sm') : ''}<span>${a.ticker}</span>`;
        b.title = 'Change the asset';
        b.onclick = () => ctx.openTickerSearch?.(b, { label:'Change asset', tag, pick:(r: Instrument) => {
          if (tag(r[0])) return;
          close(true); replace(a, r[0]);
        } });
        body.appendChild(row('Symbol', b));
      } else if (tab === 'Style') {
        const ohlcStyle = o.style === 'bars' || o.style === 'candles';
        body.appendChild(row('Style', sel(STYLES, o.style, v => { o.style = v as AssetStyle; live(); paint() })));
        const src = sel(SOURCES, o.source, v => { o.source = v as AssetSource; live() });
        src.disabled = ohlcStyle; if (ohlcStyle) src.title = 'Bars and candles draw open, high, low and close';
        body.appendChild(row('Price source', src));
        const line = document.createElement('span'); line.className = 'idlg-ctl';
        line.append(colorBtn());
        if (!ohlcStyle) line.append(sel([['1', '1 px'], ['2', '2 px'], ['3', '3 px'], ['4', '4 px']], String(o.width), v => { o.width = +v; live() }, true));
        body.appendChild(row(ohlcStyle ? 'Colour' : 'Line', line));
        const pl = document.createElement('div'); pl.className = 'idlg-row compact';
        const lab = document.createElement('label'); lab.className = 'idlg-lab'; lab.append(check(o.priceLine, v => { o.priceLine = v; live() }, 'Price line'), document.createTextNode('Price line'));
        pl.append(lab); body.appendChild(pl);
        body.appendChild(row('Scale', sel(SCALES, o.scale, v => { o.scale = v as AssetScale; live() })));
        body.appendChild(row('Override min tick', sel(TICKS, o.minTick, v => { o.minTick = v as AssetOpts['minTick']; live() })));
      } else {
        body.appendChild(row('Show on the chart', toggle(o.visible, v => { o.visible = v; live() })));
        body.appendChild(row('Flow Timeline below the chart', toggle(o.flow, v => { o.flow = v; live() })));
      }
    }
    const close = (keep: boolean) => {
      closeCpop();
      if (!keep && assets.includes(a)) { Object.assign(a.opts, JSON.parse(snap)); apply(a) }
      save(); back.hidden = true; document.removeEventListener('keydown', onKey, true);
      if (assets.includes(a)) (a.row.querySelector('[data-act="cfg"]') as HTMLElement).focus();
    };
    const onKey = (e: any) => {
      if (document.querySelector('.gp-backdrop')) return;          // the ticker search (Inputs → Symbol) is open
      if (cpop && e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); const ow = cpop.owner; closeCpop(); ow.focus(); return }
      if (document.querySelector('.cs-pop:not([hidden])')) return;
      if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); close(false) }
    };
    back.onmousedown = (e: any) => { if (cpop && !cpop.contains(e.target) && e.target !== cpop.owner) closeCpop() };
    back.onclick = (e: any) => {
      const t = e.target.closest('[data-tab]'), act = e.target.closest('[data-act]');
      if (e.target === back) close(false);
      else if (t) { tab = t.dataset.tab; paint() }
      else if (e.target.closest('.idlg-x')) close(false);
      else if (act && act.dataset.act === 'ok') close(true);
      else if (act && act.dataset.act === 'cancel') close(false);
    };
    const defs = back.querySelector('.as-defaults') as HTMLSelectElement;
    defs.onchange = () => {
      if (defs.value === 'reset') {
        const slot = assets.indexOf(a), fresh = defaultOpts(slot, assets.filter(x => x !== a).map(x => x.opts));
        Object.assign(o, fresh, { visible:o.visible, flow:o.flow }); live(); paint();
      } else if (defs.value === 'save') {
        const { style, source, width, priceLine, minTick } = o;
        store.set(DEF_KEY, JSON.stringify({ style, source, width, priceLine, minTick }));
      }
      defs.value = '';
    };
    document.addEventListener('keydown', onKey, true);
    back.hidden = false; paint();
    (back.querySelector(`[data-tab="${tab}"]`) as HTMLElement).focus();
  }

  /* ---- Flow Timeline of an asset ---- */
  const mainCol = document.querySelector('.main-col') as HTMLElement;
  const U = UNIT[ctx.M.tf || 'D'];
  const panes = () => assets.map(a => a.pane).filter(Boolean) as FlowPane[];
  /* a pane's crosshair on session i (none while it has no broker data: a series of empty points has no value to sit on) */
  const crossAt = (q: FlowPane, i: number | undefined) => i === undefined || !q.combos.length ? q.chart.clearCrosshairPosition()
    : q.chart.setCrosshairPosition(q.net[i] || 0, dates[i] as any, q.bars);
  ctx.extraFlowCharts = () => panes().map(p => p.chart);
  ctx.extraFlowHeight = () => panes().reduce((s, p) => s + p.el.getBoundingClientRect().height, 0);
  const paneH = () => Math.round(Math.max(130, Math.min(200, (mainCol.clientHeight - 46) * .18)));
  const fitPanes = () => { mainCol.style.setProperty('--af-h', paneH() + 'px'); ctx.refitFlow?.() };
  new ResizeObserver(() => requestAnimationFrame(fitPanes)).observe(mainCol);
  /* the chart's own Flow Timeline names its ticker too, so every Flow Timeline says whose flow it is */
  const mainBadge = document.createElement('span');
  mainBadge.className = 'af-badge main'; mainBadge.innerHTML = `${hasLogos() ? logoHtml(SYMBOL, 'tk-sm') : ''}<b>${SYMBOL}</b>`;
  mainBadge.title = `${nameOf(SYMBOL)} (the chart's ticker; the right panel is its broker activity)`;
  const syncMainBadge = () => { const t = document.querySelector('#flowHead .flow-title') as HTMLElement; if (panes().length) t.appendChild(mainBadge); else mainBadge.remove() };

  function visibleRange(): [number, number] {
    const r = chart.timeScale().getVisibleLogicalRange();
    return r ? [Math.max(0, Math.ceil(r.from)), Math.min(N - 1, Math.floor(r.to))] : [0, N - 1];
  }
  const cumFrom = FLOW_CUMULATIVE_FROM === 'view' && new URLSearchParams(location.search).get('cum') !== 'history' ? 'view' : 'history';
  const cumOn = () => ($('tglCum') as HTMLInputElement).checked;

  function setPane(a: Asset, on: boolean) {
    if (on && !a.pane) a.pane = buildPane(a);
    else if (!on && a.pane) { destroyPane(a.pane); a.pane = null }
    else if (a.pane) paintPaneHead(a);
    // the panes follow the order of the assets
    let at: Element = $('flowPanel');
    assets.forEach(x => { if (x.pane) { at.after(x.pane.el); at = x.pane.el } });
    syncMainBadge();
    requestAnimationFrame(() => { fitPanes(); ctx.syncAxisWidths(); requestAnimationFrame(ctx.syncAxisWidths) });
  }

  function buildPane(a: Asset): FlowPane {
    const el = document.createElement('section');
    el.className = 'bottom af'; el.setAttribute('aria-label', `Flow Timeline · ${a.ticker}`);
    el.innerHTML = `<div class="flow-grip af-grip" role="separator" aria-orientation="horizontal" tabindex="0"
        aria-label="Resize the ${a.ticker} Flow Timeline (drag, or arrow up/down; double-click to reset)"><i></i></div>
      <div class="flow-head af-head">
        <div class="flow-title"><strong>Flow Timeline</strong><span class="af-badge"></span></div>
        <div class="flow-summary"></div>
        <span class="flow-note" hidden></span>
        <div class="flow-filters"><div class="fl"></div><div class="fl"></div><div class="fl"></div><button class="fl-reset" type="button" hidden>Reset</button></div>
        <button class="flow-collapse" type="button" aria-expanded="true"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.5l4 4 4-4"/></svg></button>
      </div>
      <div class="flow-wrap af-wrap"><div class="flow-chart af-chart"></div><div class="flow-tip af-tip"></div></div>`;
    const host = el.querySelector('.af-chart') as HTMLElement;
    const fc = L.createChart(host, {
      autoSize:true,
      layout:{ background:{ type:L.ColorType.Solid, color:'#fff' }, textColor:'#666666', fontFamily:'Inter,"Segoe UI",sans-serif', attributionLogo:false },
      grid:{ vertLines:{ color:'#f2f2f2', style:L.LineStyle.Solid }, horzLines:{ color:'#f2f2f2', style:L.LineStyle.Solid } },
      crosshair:{ mode:L.CrosshairMode.Normal,
        vertLine:{ color:'#a1a1a1', width:1, style:L.LineStyle.Dashed, labelBackgroundColor:'#171717' },
        horzLine:{ color:'#a1a1a1', width:1, style:L.LineStyle.Dashed, labelVisible:false } },
      rightPriceScale:{ visible:true, borderColor:'#eaeaea', ticksVisible:false, scaleMargins:{ top:.16, bottom:.08 }, minimumWidth:ctx.axisWidths?.right || 0 },
      leftPriceScale:{ visible:true, borderColor:'#eaeaea', ticksVisible:false, scaleMargins:{ top:.16, bottom:.08 }, minimumWidth:ctx.axisWidths?.left || 112 },
      timeScale:{ borderColor:'#eaeaea', rightOffset:3, barSpacing:7, minBarSpacing:.4, timeVisible:false, secondsVisible:false },
      handleScroll:{ mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:false },
      handleScale:{ axisPressedMouseMove:{ time:true, price:true }, axisDoubleClickReset:{ time:true, price:true }, mouseWheel:true, pinch:true },
      kineticScroll:{ mouse:true, touch:true },
      localization:{ locale:'en-US' }
    } as any);
    const axisText = (v: number, n = 10) => rupiah(v).padStart(n, ' ');
    const bars = fc.addSeries(L.HistogramSeries, { priceScaleId:'right', priceLineVisible:false, lastValueVisible:false,
      priceFormat:{ type:'custom', formatter:(v: number) => axisText(v, 8), minMove:1 } });
    const cum = fc.addSeries(L.LineSeries, { priceScaleId:'left', color:'#171717', lineWidth:2, priceLineVisible:false, lastValueVisible:false,
      crosshairMarkerRadius:3, priceFormat:{ type:'custom', formatter:(v: number) => axisText(v), minMove:1 } });
    const pane: FlowPane = {
      el, chart:fc, bars, cum,
      netBadge:bars.createPriceLine({ price:0, lineVisible:false, axisLabelVisible:false, axisLabelColor:'#089981', axisLabelTextColor:'#ffffff', title:'' }),
      cumBadge:cum.createPriceLine({ price:0, color:'#171717', lineVisible:false, axisLabelVisible:false, axisLabelColor:'#171717', axisLabelTextColor:'#ffffff', title:'' }),
      combos:[], from:N, to:-1, end:-1, state:'loading',
      flt:{ brokers:new Set(), boards:new Set(ctx.BOARDS.map(b => b.id)), investors:new Set(['Foreign']) }, filters:[],
      net:new Float64Array(N), cumArr:new Float64Array(N).fill(NaN), drawings:null,
      collapsed:store.get(`ml.assets.flow.collapsed.${a.ticker}`) === '1', alive:true, synced:false, over:false,
      noData:document.createElement('div'), placeNoData:() => {}
    };
    /* the sessions after the asset's broker data are hatched, as on the chart's own Flow Timeline (EXEC-TERMINAL-FRESH) */
    const noData = pane.noData;
    noData.className = 'flow-nodata'; noData.hidden = true; noData.innerHTML = '<span>Broker data not yet loaded</span>';
    (el.querySelector('.af-wrap') as HTMLElement).appendChild(noData);
    let placeRaf = 0;
    const place = () => {
      if (!pane.alive || pane.state === 'loading' || !pane.combos.length || pane.end >= N - 1) { noData.hidden = true; return }
      const ts = fc.timeScale(), c = ts.logicalToCoordinate(pane.end as any), w = ts.width();
      const x = c === null ? null : c + ts.options().barSpacing / 2;
      if (x === null || x >= w) { noData.hidden = true; return }
      const left = fc.priceScale('left').width(), from = Math.max(0, x);
      noData.hidden = false; noData.style.left = (left + from) + 'px'; noData.style.width = (w - from) + 'px';
      noData.style.height = (host.clientHeight - ts.height()) + 'px';
      noData.classList.toggle('narrow', w - from < 150);
    };
    // placed after the chart has drawn its new data or range (a coordinate read right after setData is the old one)
    pane.placeNoData = () => { cancelAnimationFrame(placeRaf); placeRaf = requestAnimationFrame(() => { placeRaf = requestAnimationFrame(place) }) };
    new ResizeObserver(pane.placeNoData).observe(host);
    /* the chart's sessions from the start (no values yet), so the pane's time scale is the chart's before any data arrives;
       an empty pane would otherwise hand its own default range to the chart */
    const blank = ctx.ohlc.map(b => ({ time:b.time }));
    bars.setData(blank); cum.setData(blank);
    /* filters: the chart's own Flow Timeline's, with their own choice (Q4) */
    const allBrokers = () => [...new Set(pane.combos.map(c => c.broker))].sort();
    const isDefault = () => pane.flt.brokers.size === allBrokers().length && pane.flt.boards.size === ctx.BOARDS.length && pane.flt.investors.size === 1 && pane.flt.investors.has('Foreign');
    const brokerSummary: any = (s: Set<string>) => { const t = allBrokers().length; return s.size === t ? `All (${t})` : s.size === 0 ? 'None' : s.size <= 2 ? [...s].sort().join(', ') : `${s.size} selected` };
    brokerSummary.isModified = (s: Set<string>) => s.size !== allBrokers().length;
    const listSummary = (all: number, def?: Set<string>) => { const f: any = (s: Set<string>) => s.size === all ? `All (${all})` : s.size === 0 ? 'None' : [...s].join(', ');
      f.isModified = (s: Set<string>) => def ? !(s.size === def.size && [...def].every(x => s.has(x))) : s.size !== all; return f };
    const reset = el.querySelector('.fl-reset') as HTMLElement;
    const onFilter = () => { recompute(a); reset.hidden = isDefault() };
    const [fb, fbo, fi] = [...el.querySelectorAll('.flow-filters .fl')] as HTMLElement[];
    pane.filters = [
      ctx.makeFilter(fb, { title:'Broker', searchable:true, placeholder:'Search broker code…', grid:true, mono:true,
        getOptions:() => allBrokers().map(b => ({ id:b, label:b })), state:pane.flt.brokers, summary:brokerSummary, onChange:onFilter }),
      ctx.makeFilter(fbo, { title:'Board', getOptions:() => ctx.BOARDS, state:pane.flt.boards, summary:listSummary(ctx.BOARDS.length), onChange:onFilter }),
      ctx.makeFilter(fi, { title:'Investor', getOptions:() => ctx.INVESTORS, state:pane.flt.investors, summary:listSummary(ctx.INVESTORS.length, new Set(['Foreign'])), onChange:onFilter })
    ];
    reset.onclick = () => {
      pane.flt.brokers.clear(); allBrokers().forEach(b => pane.flt.brokers.add(b));
      pane.flt.boards.clear(); ctx.BOARDS.forEach(b => pane.flt.boards.add(b.id));
      pane.flt.investors.clear(); pane.flt.investors.add('Foreign');
      pane.filters.forEach(f => f.refresh()); onFilter();
    };
    /* collapse to the header */
    const btn = el.querySelector('.flow-collapse') as HTMLElement;
    const setCollapsed = (on: boolean) => {
      pane.collapsed = on; el.classList.toggle('collapsed', on); btn.setAttribute('aria-expanded', String(!on));
      const t = on ? `Expand the ${a.ticker} Flow Timeline` : `Collapse the ${a.ticker} Flow Timeline`; btn.title = t; btn.setAttribute('aria-label', t);
      store.set(`ml.assets.flow.collapsed.${a.ticker}`, on ? '1' : '0');
      requestAnimationFrame(() => requestAnimationFrame(() => { fitPanes(); syncRange(chart, fc); ctx.syncAxisWidths() }));
    };
    btn.onclick = () => setCollapsed(!pane.collapsed);
    setCollapsed(pane.collapsed);
    /* raise or lower the pane (user 2026-10-28: "flow timeline aset kedua dan aset ketiga bisa juga dinaikkan dan
       diturunkan"): the grip at its top edge, as on the chart's own Flow Timeline; the height is kept per ticker, a
       double-click goes back to the shared height */
    const grip = el.querySelector('.af-grip') as HTMLElement, hKey = `ml.assets.flow.h.${a.ticker}`, AF_MIN = 110;
    const maxH = () => Math.max(AF_MIN, mainCol.clientHeight - 46 - 240 - ($('flowPanel') as HTMLElement).getBoundingClientRect().height
      - panes().filter(q => q !== pane).reduce((t, q) => t + q.el.getBoundingClientRect().height, 0));
    const setH = (h: number | null, save = true) => {
      if (h === null) { el.style.removeProperty('height'); if (save) store.set(hKey, '') }
      else { h = Math.round(Math.max(AF_MIN, Math.min(maxH(), h))); el.style.height = h + 'px'; if (save) store.set(hKey, String(h)) }
      grip.setAttribute('aria-valuenow', String(Math.round(el.getBoundingClientRect().height)));
      requestAnimationFrame(() => { ctx.refitFlow?.(); ctx.syncAxisWidths(); pane.placeNoData() });
    };
    const savedH = Number(store.get(hKey)); if (savedH) el.style.height = savedH + 'px';
    let drag: { y: number; h: number } | null = null;
    grip.addEventListener('pointerdown', (e: PointerEvent) => {
      if (e.button !== 0 || pane.collapsed) return;
      drag = { y:e.clientY, h:el.getBoundingClientRect().height }; grip.setPointerCapture(e.pointerId); mainCol.classList.add('dragging'); e.preventDefault();
    });
    grip.addEventListener('pointermove', (e: PointerEvent) => { if (drag) setH(drag.h + (drag.y - e.clientY), false) });   // drag up = taller pane
    const endDrag = (e: PointerEvent) => {
      if (!drag) return; drag = null; mainCol.classList.remove('dragging');
      try { grip.releasePointerCapture(e.pointerId) } catch (_) {}
      setH(el.getBoundingClientRect().height);
    };
    grip.addEventListener('pointerup', endDrag); grip.addEventListener('pointercancel', endDrag);
    grip.addEventListener('dblclick', () => setH(null));
    grip.addEventListener('keydown', (e: KeyboardEvent) => {
      const cur = el.getBoundingClientRect().height;
      if (e.key === 'ArrowUp') { setH(cur + 16); e.preventDefault() } else if (e.key === 'ArrowDown') { setH(cur - 16); e.preventDefault() }
    });
    /* time range, crosshair */
    fc.timeScale().subscribeVisibleLogicalRangeChange(() => { if (pane.synced && pane.over) syncRange(fc, chart); requestAnimationFrame(ctx.syncAxisWidths); pane.placeNoData() });
    /* only a pointer over this pane moves the others: a crosshair put here from code (the chart's hover) also fires this
       event a frame later, which sent it back to the chart and redrew everything again (EXEC-TERMINAL-LAG) */
    host.addEventListener('pointerenter', () => { pane.over = true }); host.addEventListener('pointerleave', () => { pane.over = false });
    fc.subscribeCrosshairMove((p: any) => {
      if (xLock || !pane.over) return;
      const k = keyOf(p.time), i = k ? idxByTime.get(k) : undefined;
      xLock = true;
      try {
        if (i === undefined || !p.point || p.point.x < 0) { baseCrosshairAt(null); panes().forEach(q => q !== pane && q.chart.clearCrosshairPosition()) }
        else { baseCrosshairAt(i); panes().forEach(q => q !== pane && crossAt(q, i)) }
      } finally { xLock = false }
    });
    pane.drawings = ctx.attachFlowDrawings?.(fc, bars, host, a.ticker) || null;
    paintPaneHead(a, pane);
    requestAnimationFrame(() => { syncRange(chart, fc); requestAnimationFrame(() => requestAnimationFrame(() => { pane.synced = true })) });
    load(a, pane);
    return pane;
  }
  function destroyPane(p: FlowPane) {
    p.alive = false; p.drawings?.detach();
    p.filters.forEach(f => f.close());
    try { p.chart.remove() } catch (_) {}
    p.el.remove();
  }
  function paintPaneHead(a: Asset, p = a.pane!) {
    // the same badge as the chart's own ticker (user 2026-10-28: "ticker badge bisa disamakan saja dengan ticker main asset")
    const b = p.el.querySelector('.af-badge') as HTMLElement;
    b.innerHTML = `${hasLogos() ? logoHtml(a.ticker, 'tk-sm') : ''}<b>${a.ticker}</b>`;
    b.title = `${a.name}: added asset (the right panel stays ${SYMBOL})`;
  }
  function load(a: Asset, p: FlowPane) {
    const note = p.el.querySelector('.flow-note') as HTMLElement;
    const say = (html: string) => { note.innerHTML = html; note.hidden = !html };
    say(spin('Loading broker data'));
    const set = (part: { combos: Combo[]; flowFrom: number; flowTo: number }, more: boolean) => {
      if (!p.alive) return;
      const wasAll = p.flt.brokers.size === new Set(p.combos.map(c => c.broker)).size;
      p.combos = part.combos; p.from = part.flowFrom; p.to = part.flowTo; p.state = more ? 'more' : 'ready';
      if (wasAll) { p.flt.brokers.clear(); p.combos.forEach(c => p.flt.brokers.add(c.broker)) }
      p.filters.forEach(f => f.refresh());
      recompute(a);
      say(more ? spin('Loading earlier broker data') : !p.combos.length ? `No broker data is published for ${a.ticker}` : '');
      // nothing to draw (an index): the pane keeps its header line only
      const none = !more && !p.combos.length;
      if (none !== p.el.classList.contains('nodata')) { p.el.classList.toggle('nodata', none); requestAnimationFrame(() => { fitPanes(); ctx.syncAxisWidths() }) }
    };
    const failed = () => { if (!p.alive) return; p.state = 'failed'; say('Broker data could not be loaded. Remove the asset and add it again to retry.') };
    ctx.M.loadAssetFlow!(a.ticker).then(f => {
      if (!p.alive) return;
      p.end = brokerEnd(dates, f.through); p.through = f.through;
      f.recent.then(r => { set(r, true); f.all.then(all => set(all, false), failed) }, failed);
    }, failed);
  }
  function recompute(a: Asset) {
    const p = a.pane; if (!p) return;
    p.net = new Float64Array(N);
    p.combos.forEach(c => {
      if (!p.flt.brokers.has(c.broker) || !p.flt.boards.has(c.board) || !p.flt.investors.has(c.investor)) return;
      for (let i = 0; i < N; i++) p.net[i] += c.net[i];
    });
    const E = p.end;
    p.bars.setData(ctx.ohlc.map((b, i) => i > E || i < p.from ? { time:b.time } : { time:b.time, value:Math.round(p.net[i]), color:p.net[i] >= 0 ? 'rgba(8,153,129,.9)' : 'rgba(242,54,69,.9)' }));
    computeCum(p);
    syncRange(chart, p.chart);                            // new data never moves the shared range
    paneSummary(p);
    paneTip(a, ctx.lastTipIdx);
    p.placeNoData();
  }
  function computeCum(p: FlowPane) {
    const start = cumFrom === 'view' ? visibleRange()[0] : 0, E = p.end;
    p.cumArr = cumulativeFrom(p.net, start);
    p.cum.setData(ctx.ohlc.map((b, i) => i > E || i < start || i < p.from ? { time:b.time } : { time:b.time, value:Math.round(p.cumArr[i]) }));
    p.cum.applyOptions({ visible:cumOn() });
    p.chart.applyOptions({ leftPriceScale:{ textColor:cumOn() ? '#666666' : 'rgba(0,0,0,0)' } } as any);
  }
  function paneSummary(p: FlowPane) {
    const [a0, b0] = visibleRange(), b = Math.min(b0, p.end), from = Math.max(a0, p.from);
    let total = 0; for (let i = from; i <= b; i++) total += p.net[i];
    const last = p.end >= 0 && p.end >= p.from ? p.net[p.end] : 0, avg = total / (b - from + 1 > 0 ? b - from + 1 : 1);
    const tone = (v: number) => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
    const stat = (l: string, v: number) => `<div class="flow-stat"><span class="flow-stat-label">${l}</span><span class="flow-stat-val ${tone(v)}">${p.state === 'loading' || !p.combos.length ? '–' : rupiah(v)}</span></div>`;
    (p.el.querySelector('.flow-summary') as HTMLElement).innerHTML = stat(`Latest ${U.one} net`, last) + stat('Period net total', total) + stat(`Avg ${U.adj} net`, avg);
  }
  function paneTip(a: Asset, i: number) {
    const p = a.pane; if (!p) return;
    const tip = p.el.querySelector('.af-tip') as HTMLElement;
    if (p.state === 'loading' || !p.combos.length) { tip.innerHTML = ''; return }
    if (i > p.end || i < p.from) {
      p.netBadge.applyOptions({ axisLabelVisible:false }); p.cumBadge.applyOptions({ axisLabelVisible:false });
      const through = p.through ? new Date(p.through + 'T00:00:00Z').toLocaleDateString('en-GB', { weekday:'short', day:'2-digit', month:'short', timeZone:'UTC' }).replace(',', '') : '';
      tip.innerHTML = `<b>${a.ticker}</b> &nbsp; <span class="flow-nodata-tip">${i > p.end && through ? `No broker data yet (through ${through})` : `No broker data on this ${U.one}`}</span>`; return;
    }
    const hasCum = Number.isFinite(p.cumArr[i]);
    p.netBadge.applyOptions({ price:Math.round(p.net[i]), axisLabelVisible:true, axisLabelColor:p.net[i] >= 0 ? '#089981' : '#f23645' });
    p.cumBadge.applyOptions(hasCum ? { price:Math.round(p.cumArr[i]), axisLabelVisible:cumOn() } : { axisLabelVisible:false });
    tip.innerHTML = `<b>${a.ticker}</b> &nbsp; Net <b class="${cls(p.net[i])}">${rupiah(p.net[i])}</b>`
      + (cumOn() && hasCum ? ` &nbsp; Cumulative <b>${rupiah(p.cumArr[i])}</b>` : '');
  }

  /* the asset panes move with the chart: time range (both ways), crosshair, the cumulative line's start, the totals */
  let rLock = false, xLock = false;
  function syncRange(from: any, to: any) {
    if (rLock) return;
    const r = from.timeScale().getVisibleLogicalRange(); if (!r) return;
    // EXEC-TERMINAL-LAG: the same range again would fire another change on the other chart, and back
    const c = to.timeScale().getVisibleLogicalRange(); if (c && Math.abs(c.from - r.from) < 1e-6 && Math.abs(c.to - r.to) < 1e-6) return;
    rLock = true; try { to.timeScale().setVisibleLogicalRange(r) } finally { rLock = false }
  }
  let raf = 0;
  chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    panes().forEach(p => syncRange(chart, p.chart));
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => assets.forEach(a => { if (a.pane) { if (cumFrom === 'view') computeCum(a.pane); paneSummary(a.pane); paneTip(a, ctx.lastTipIdx) } }));
  });
  const follow = (p: any) => {
    if (xLock) return;
    const k = keyOf(p.time), i = k ? idxByTime.get(k) : undefined;
    xLock = true;
    try { panes().forEach(q => crossAt(q, p.point ? i : undefined)) }
    finally { xLock = false }
  };
  chart.subscribeCrosshairMove(follow);
  ctx.flowChart.subscribeCrosshairMove(follow);
  /* a crosshair put on the chart from code (Broker inventory hover) fires no crosshair event (lightweight-charts 5.2.1,
     ERRORS EXEC-TERMINAL-BS-SIDE): ctx.crosshairAt moves the asset panes too */
  const baseCrosshairAt = ctx.crosshairAt;
  ctx.crosshairAt = (i: number | null) => { baseCrosshairAt(i); xLock = true; try { panes().forEach(q => crossAt(q, i === null ? undefined : i)) } finally { xLock = false } };
  ($('tglCum') as HTMLInputElement).addEventListener('change', () => assets.forEach(a => { if (a.pane) { computeCum(a.pane); paneTip(a, ctx.lastTipIdx) } }));

  /* the assets of the last visit come back (the chart's own ticker is skipped) */
  let saved: { ticker: string; opts: Partial<AssetOpts> }[] = [];
  try { saved = JSON.parse(store.get(KEY) || '[]') } catch { saved = [] }
  saved.filter(s => s && known.has(s.ticker) && s.ticker !== SYMBOL).slice(0, MAX_ASSETS).forEach(s => add(s.ticker, s.opts));
  save(); syncPlus();
}
