/* Main price chart, compare series and the toolbar groups (reference lines 1137-1384). */
import type { Ctx } from './context';
import { $, hasLogos, logoHtml } from './context';
import type { Point } from '../data/types';
import { barDecimals, priceText } from '../data/priceFormat';

export function initChart(ctx: Ctx) {
  const { L, container, SYMBOL, ohlc, lineData, volume, dates, active } = ctx;

  const asReturn = (data: Point[]) => {
    const base = data[0].value || 1;
    return data.map(p => ({ time: p.time, value: +((p.value / base - 1) * 100).toFixed(2) }));
  };
  // Axis / crosshair text of the price pane. Set per series (not chart-wide) so indicator panes keep their own units.
  // EXEC-FI-TERMINAL: a bond's yield or price has three decimals (US yields 4.108; bills' quotes 4.050)
  const fi = !!ctx.M.fixedIncome;
  /* EXEC-TERMINAL-LOOK 2 (1A): thousands separators and the decimals the instrument's prices carry (shares 0, an index 2);
     a bond keeps its three */
  const PD = ctx.priceDecimals = fi ? 3 : barDecimals(ohlc as any[]);
  ctx.priceText = v => priceText(v, PD);
  ctx.axisLabel = v => ctx.displayMode === 'return' ? v.toFixed(1) + '%' : ctx.priceText(v);
  ctx.formatMode = () => ({ type:'custom', formatter:(v: number) => ctx.axisLabel(v), minMove:ctx.displayMode === 'return' ? .01 : 10 ** -PD });

  const chart = ctx.chart = L.createChart(container, {
    autoSize: true,
    layout: {
      background: { type: L.ColorType.Solid, color: '#fff' },
      textColor: '#666666',
      fontFamily: 'Inter,"Segoe UI",sans-serif',
      attributionLogo: false
    },
    grid: {
      vertLines: { color:'#f2f2f2', style:L.LineStyle.Solid },
      horzLines: { color:'#f2f2f2', style:L.LineStyle.Solid }
    },
    crosshair: {
      mode: L.CrosshairMode.Normal,
      vertLine: { color:'#a1a1a1', width:1, style:L.LineStyle.Dashed, labelBackgroundColor:'#171717' },
      horzLine: { color:'#a1a1a1', width:1, style:L.LineStyle.Dashed, labelBackgroundColor:'#171717' }
    },
    rightPriceScale: { visible:true, borderColor:'#eaeaea', scaleMargins:{ top:.08, bottom:.22 } },
    leftPriceScale: { visible:true, borderColor:'#eaeaea', scaleMargins:{ top:0, bottom:0 } },   // headroom comes from withRoom() below, so the axis labels fill the whole pane
    timeScale: { borderColor:'#eaeaea', rightOffset:3, barSpacing:7, minBarSpacing:.4, timeVisible:false, secondsVisible:false },
    handleScroll: { mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:false },
    handleScale: { axisPressedMouseMove:{ time:true, price:true }, axisDoubleClickReset:{ time:true, price:true }, mouseWheel:true, pinch:true },
    kineticScroll: { mouse:true, touch:true },
    localization: { locale:'en-US' }
  } as any);

  /* Auto-fit with headroom: widen the series' own range by the usual top/bottom share instead of using scale margins.
     Same picture as before, but the price axis then draws labels over the full pane height, like the right axis. */
  const ROOM = { top:.08, bottom:.22 };
  const withRoom = (orig: () => any) => {
    const r = orig(); if(!r || !r.priceRange) return r;
    const lo = r.priceRange.minValue, hi = r.priceRange.maxValue, k = ((hi - lo) || Math.abs(hi) * .02 || 1) / (1 - ROOM.top - ROOM.bottom);
    return { ...r, priceRange:{ minValue:lo - k * ROOM.bottom, maxValue:hi + k * ROOM.top } };
  };
  const candle = ctx.candle = chart.addSeries(L.CandlestickSeries, {
    title:SYMBOL,
    priceScaleId:'left',
    autoscaleInfoProvider:withRoom,
    priceLineVisible:false,
    upColor:'#089981',
    downColor:'#f23645',
    borderUpColor:'#089981',
    borderDownColor:'#f23645',
    wickUpColor:'#089981',
    wickDownColor:'#f23645',
    priceLineColor:'#089981'
  });
  const mainLine = ctx.mainLine = chart.addSeries(L.LineSeries, {
    title:SYMBOL,
    priceScaleId:'left',
    autoscaleInfoProvider:withRoom,
    priceLineVisible:false,
    color:'#089981',
    lineWidth:2,
    visible:false,
    priceLineColor:'#089981'
  });
  const volumeSeries = ctx.volumeSeries = chart.addSeries(L.HistogramSeries, {
    priceScaleId:'volume',
    priceFormat:{ type:'volume' },
    priceLineVisible:false,
    lastValueVisible:false
  });
  candle.setData(ohlc);
  mainLine.setData(lineData);
  volumeSeries.setData(volume);
  chart.priceScale('volume').applyOptions({ scaleMargins:{ top:.82, bottom:0 }, borderVisible:false });

  ctx.chartStyle = 'candle';
  ctx.displayMode = 'price';

  function dataFor(id: string) {
    return ctx.displayMode === 'return' ? asReturn(ctx.rawSeries[id]) : ctx.rawSeries[id];
  }

  ctx.onDisplayMode = () => {};
  ctx.displayHooks = [];                                   // extra listeners (indicators) for price / return switches
  function updateMainDisplay() {
    const useReturn = ctx.displayMode === 'return';
    const mainReturn = asReturn(lineData);
    if (useReturn) {
      candle.applyOptions({ visible:false });
      mainLine.applyOptions({
        visible:true,
        title:SYMBOL + ' return',
        priceScaleId:'left',
        priceFormat:ctx.formatMode()
      });
      mainLine.setData(mainReturn);
    } else {
      mainLine.setData(lineData);
      mainLine.applyOptions({
        visible:ctx.chartStyle === 'line',
        title:SYMBOL,
        priceScaleId:'left',
        priceFormat:ctx.formatMode()
      });
      candle.applyOptions({ visible:ctx.chartStyle === 'candle' });
    }
    ctx.onDisplayMode();
    ctx.displayHooks.forEach(fn => fn());
  }
  ctx.updateMainDisplay = updateMainDisplay;

  function refreshSeries(id: string) {
    const item = active.get(id);
    if (!item) return;
    item.series.setData(dataFor(id));
    item.series.applyOptions({
      title:item.symbol + (ctx.displayMode === 'return' ? ' return' : ''),
      priceFormat:ctx.formatMode()
    });
  }

  function addSeries(id: string) {
    if (!id || active.has(id)) return;
    const spec = ctx.catalog.find(item => item.id === id);
    if (!spec) return;
    if (!ctx.rawSeries[id]) {                                // live: a compare series is downloaded the first time it is added
      ctx.M.loadCompare(id).then(data => { if (data.length) { ctx.rawSeries[id] = data; addSeries(id) } }).catch(() => {});
      return;
    }
    const series = chart.addSeries(L.LineSeries, {
      title:spec.symbol + (ctx.displayMode === 'return' ? ' return' : ''),
      priceScaleId:'right',
      color:spec.color,
      lineWidth:2,
      priceFormat:ctx.formatMode(),
      priceLineVisible:false,
      lastValueVisible:true
    });
    active.set(id, { ...spec, series, visible:true });
    refreshSeries(id);
    chart.priceScale('right').applyOptions({ visible:true, autoScale:true });
    renderSeriesUi();
  }

  function removeSeries(id: string) {
    const item = active.get(id);
    if (!item || active.size <= 1) return;
    try { chart.removeSeries(item.series); } catch(e) { item.series.applyOptions({ visible:false }); }
    active.delete(id);
    renderSeriesUi();
  }

  function toggleSeries(id: string) {
    const item = active.get(id);
    if (!item) return;
    item.visible = !item.visible;
    item.series.applyOptions({ visible:item.visible });
    renderSeriesUi();
  }

  function remainingCatalog() {
    const query = ($('seriesSearch').value || '').trim().toLowerCase();
    return ctx.catalog.filter(item => {
      if (active.has(item.id) || item.symbol === SYMBOL) return false;
      if (!query) return true;
      return item.symbol.toLowerCase().includes(query) || item.name.toLowerCase().includes(query);
    });
  }

  function renderAddChoices() {
    const remaining = remainingCatalog();
    const select = $('addSeriesSelect');
    select.innerHTML = remaining.map(item => '<option value="' + item.id + '">' + item.symbol + ' · ' + item.name + '</option>').join('');
    select.disabled = remaining.length === 0;
    $('addSeriesButton').disabled = remaining.length === 0;
    $('catalogGrid').innerHTML = remaining.slice(0, 6).map(item =>
      '<button type="button" data-quick-add="' + item.id + '" style="--series-color:' + item.color + '">' +
      '<strong><span class="series-dot"></span>' + (hasLogos() ? logoHtml(item.symbol, 'tk-sm') : '') + item.symbol + '</strong><small>' + item.name + '</small></button>'
    ).join('');
  }

  function renderSeriesUi() {
    const tabs = $('seriesTabs');
    tabs.innerHTML = Array.from(active.values()).map(item =>
      '<button class="series-chip ' + (item.visible ? '' : 'off') + '" data-toggle-series="' + item.id + '" style="--series-color:' + item.color + '">' +
      '<span class="series-dot"></span>' + (hasLogos() ? logoHtml(item.symbol, 'tk-sm') : '') + '<span class="series-symbol">' + item.symbol + '</span>' +
      '<span class="chip-x" data-remove-series="' + item.id + '">×</span></button>'
    ).join('');
    $('seriesCount').textContent = active.size + ' active';
    renderAddChoices();
  }

  function activate(group: HTMLElement, button: HTMLElement) {
    group.querySelectorAll('button').forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');
  }

  $('toggleAddPanel').addEventListener('click', () => {
    $('addPanel').classList.toggle('open');
    $('seriesSearch').focus();
  });
  $('closePanel').addEventListener('click', () => {
    $('addPanel').classList.remove('open');
  });
  $('seriesSearch').addEventListener('input', renderAddChoices);
  $('addSeriesButton').addEventListener('click', () => {
    addSeries($('addSeriesSelect').value);
  });
  $('catalogGrid').addEventListener('click', (event: any) => {
    const button = event.target.closest('[data-quick-add]');
    if (button) addSeries(button.dataset.quickAdd);
  });
  $('seriesTabs').addEventListener('click', (event: any) => {
    const remove = event.target.closest('[data-remove-series]');
    if (remove) {
      event.stopPropagation();
      removeSeries(remove.dataset.removeSeries);
      return;
    }
    const toggle = event.target.closest('[data-toggle-series]');
    if (toggle) toggleSeries(toggle.dataset.toggleSeries);
  });
  $('styleGroup').addEventListener('click', (event: any) => {
    const button = event.target.closest('button');
    if (!button) return;
    activate(event.currentTarget, button);
    event.currentTarget.querySelectorAll('button').forEach((b: HTMLElement) => b.setAttribute('aria-pressed', String(b===button)));
    ctx.chartStyle = button.dataset.style;
    updateMainDisplay();
  });
  $('modeGroup').addEventListener('click', (event: any) => {
    const button = event.target.closest('button');
    if (!button) return;
    activate(event.currentTarget, button);
    ctx.displayMode = button.dataset.mode;
    updateMainDisplay();
    active.forEach((_, id) => refreshSeries(id));
    chart.priceScale('left').applyOptions({ autoScale:true });
    chart.priceScale('right').applyOptions({ autoScale:true });
    renderSeriesUi();
  });
  $('timeframeGroup').addEventListener('click', (event: any) => {
    const button = event.target.closest('button');
    if (!button) return;
    activate(event.currentTarget, button);
    const map: Record<string, number> = { '5M':170, '15M':252, '1H':430, '4H':560, D:252, W:756, M:1280 };
    const bars = map[button.dataset.timeframe] || 252;
    chart.timeScale().setVisibleLogicalRange({ from:Math.max(0, dates.length - bars), to:dates.length + 3 });
  });


  updateMainDisplay();
  // EXEC-TERMINAL-WM: about a year of daily candles, two years of weekly, ten years of monthly; EXEC-INTRADAY-FEATURES C3:
  // the reference's bar counts of its intraday buttons (5M 170, 15M 252, 1H 430, 4H 560), and its time on the axis
  const firstBars = ({ D:252, W:104, M:120, '5M':170, '15M':252, '1H':430, '4H':560 } as Record<string, number>)[(ctx.M.tf || 'D').toUpperCase()] || 252;
  if (ctx.M.intraday) chart.applyOptions({ timeScale:{ timeVisible:true, secondsVisible:false } });
  if (ctx.M.intraday) intradayMarks(ctx, chart, [candle, mainLine], dates, container);
  chart.timeScale().setVisibleLogicalRange({ from:Math.max(0, dates.length - firstBars), to:dates.length + 3 });
  ctx.resetRange = () => chart.timeScale().setVisibleLogicalRange({ from:Math.max(0, dates.length - firstBars), to:dates.length + 3 });

  /* EXEC-TERMINAL-SHIFTWHEEL (user 2026-10-29: "kalau saya hold shift and then I scroll the mouse maka fungsinya akan menjadi
     horizontal scroll. Di main chart"), live: Shift + wheel over the chart or a Flow Timeline moves the time range sideways
     (8% of the visible bars per notch, down = later) instead of zooming; the Flow charts follow the chart */
  if (ctx.M.mode === 'live') document.querySelector('.main-col')?.addEventListener('wheel', (e: any) => {
    if (!e.shiftKey || e.ctrlKey || e.metaKey || !e.target.closest('.chart-wrap, .bottom')) return;
    const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY; if (!d) return;
    e.preventDefault(); e.stopPropagation();
    const ts = chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
    const step = Math.sign(d) * Math.max(1, (r.to - r.from) * .08);
    ts.setVisibleLogicalRange({ from:r.from + step, to:r.to + step });
  }, { capture:true, passive:false });
}

/* EXEC-UI-AUDIT-FIX F8 (user 2026-11-01; plan EXEC-INTRADAY-FEATURES C3, "garis tipis di awal setiap sesi" and "Catatan di
   chart"): on an intraday chart a thin line at the open of every session (the candle whose key starts a new date: the
   candles are packed without the lunch break and the night, so this is where a day begins), and a note with the
   timeframe's history start and its last bar (the candle keys are the exchange's clock, WIB). */
const SESSION_GAP_PX = 24;
const sessionStarts = (keys: string[]) => keys.map((k, i) => i > 0 && k.slice(0, 10) !== keys[i - 1].slice(0, 10) ? i : -1).filter(i => i >= 0);
export { sessionStarts };
function intradayMarks(ctx: Ctx, chart: any, series: any[], keys: string[], container: HTMLElement) {
  const starts = sessionStarts(keys);
  class SessionLines {
    chart: any = null; req: any = null;
    view = { zOrder:() => 'bottom', renderer:() => ({ draw:() => {}, drawBackground:(t: any) => this.paint(t) }) };
    attached(p: any) { this.chart = p.chart; this.req = p.requestUpdate }
    detached() { this.chart = null }
    updateAllViews() {}
    paneViews() { return [this.view] }
    paint(target: any) {
      if (!this.chart) return;
      const ts = this.chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
      const spacing = ts.options().barSpacing, half = spacing / 2;
      const shown = starts.filter(i => i >= r.from - 1 && i <= r.to + 1);
      // lines closer than SESSION_GAP_PX on screen (1H and 4H zoomed out: a line every 2-5 candles) would hide the candles;
      // they come back when the chart is zoomed in
      if (shown.length > 1 && (shown[shown.length - 1] - shown[0]) / (shown.length - 1) * spacing < SESSION_GAP_PX) return;
      target.useBitmapCoordinateSpace(({ context:c, bitmapSize, horizontalPixelRatio:hx }: any) => {
        c.fillStyle = 'rgba(100,116,139,.22)';
        const w = Math.max(1, Math.round(hx));
        for (const i of shown) {
          const x = ts.logicalToCoordinate(i as any); if (x === null) continue;
          c.fillRect(Math.round((x - half) * hx), 0, w, bitmapSize.height);
        }
      });
    }
  }
  series.forEach(s => s.attachPrimitive(new SessionLines()));
  if (!keys.length) return;
  const day = (k: string) => new Date(k.slice(0, 10) + 'T00:00:00Z').toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', timeZone:'UTC' });
  const tf = String(ctx.M.tf || '').toUpperCase(), last = keys[keys.length - 1];
  const note = document.createElement('div');
  note.className = 'tf-note';
  note.textContent = `${tf} history from ${day(keys[0])} · Data through ${day(last)} ${last.slice(11, 16)} WIB`;
  note.title = 'Intraday bars are updated once a day, after the market closes';
  container.parentElement?.appendChild(note);
}
