/* Main price chart, compare series and the toolbar groups (reference lines 1137-1384). */
import type { Ctx } from './context';
import { $ } from './context';
import type { Point } from '../data/types';

export function initChart(ctx: Ctx) {
  const { L, container, SYMBOL, ohlc, lineData, volume, dates, active } = ctx;

  const asReturn = (data: Point[]) => {
    const base = data[0].value || 1;
    return data.map(p => ({ time: p.time, value: +((p.value / base - 1) * 100).toFixed(2) }));
  };
  // Axis / crosshair text of the price pane. Set per series (not chart-wide) so indicator panes keep their own units.
  ctx.axisLabel = v => ctx.displayMode === 'return' ? v.toFixed(1) + '%' : v.toFixed(2);
  ctx.formatMode = () => ({ type:'custom', formatter:(v: number) => ctx.axisLabel(v), minMove:ctx.displayMode === 'return' ? .01 : .1 });

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
      '<strong><span class="series-dot"></span>' + item.symbol + '</strong><small>' + item.name + '</small></button>'
    ).join('');
  }

  function renderSeriesUi() {
    const tabs = $('seriesTabs');
    tabs.innerHTML = Array.from(active.values()).map(item =>
      '<button class="series-chip ' + (item.visible ? '' : 'off') + '" data-toggle-series="' + item.id + '" style="--series-color:' + item.color + '">' +
      '<span class="series-dot"></span><span class="series-symbol">' + item.symbol + '</span>' +
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
  chart.timeScale().setVisibleLogicalRange({ from:Math.max(0, dates.length - 252), to:dates.length + 3 });
}
