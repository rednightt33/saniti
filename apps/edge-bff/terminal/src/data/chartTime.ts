/* EXEC-INTRADAY-FEATURES C3 (user 2026-11-01): an intraday candle's key is its open time on the exchange's clock
   ('YYYY-MM-DDTHH:MM', timeframe.ts barKey); the page compares and stores keys, and only lightweight-charts sees numbers.
   It is given the key's wall-clock time read as UTC seconds, so its axis and crosshair show the exchange's clock (WIB)
   with no zone of the browser involved, and a time it answers (crosshair, coordinate) comes back as the same key through
   keyOf. A daily, weekly or monthly key ('YYYY-MM-DD') passes unchanged, so the wrapper is a no-op on those charts. */
export const toChart = (t: any) => typeof t === 'string' && t.length > 10 ? Date.parse(t + ':00Z') / 1000 : t;
export const fromChart = (t: number) => new Date(t * 1000).toISOString().slice(0, 16);

const point = (p: any) => p && typeof p.time === 'string' && p.time.length > 10 ? { ...p, time:toChart(p.time) } : p;

function series<S>(s: S): S {
  const x: any = s, set = x.setData.bind(x), update = x.update.bind(x);
  x.setData = (data: any[]) => set(data.map(point));
  x.update = (bar: any, ...rest: any[]) => update(point(bar), ...rest);
  return s;
}

/** a chart whose series, crosshair and time scale take candle keys */
export function keyedChart<C>(chart: C): C {
  const c: any = chart;
  if (c.__keyed) return chart;
  c.__keyed = true;
  const add = c.addSeries.bind(c), cross = c.setCrosshairPosition.bind(c), ts = c.timeScale(), t2c = ts.timeToCoordinate.bind(ts);
  c.addSeries = (...a: any[]) => series(add(...a));
  c.setCrosshairPosition = (price: number, time: any, s: any) => cross(price, toChart(time), s);
  ts.timeToCoordinate = (t: any) => t2c(toChart(t));
  return chart;
}

/** the lightweight-charts module with createChart giving keyed charts (ctx.L on an intraday page) */
export function keyedCharts<T extends { createChart: (...a: any[]) => any }>(L: T): T {
  return { ...L, createChart:(...a: any[]) => keyedChart(L.createChart(...a)) };
}

/** ERRORS M326 (UI audit 2026-11-01): a chart that follows the main chart's time range (the Flow Timeline, an asset's
    Flow pane) ends its time scale where the main chart ends. lightweight-charts limits how far right a chart scrolls from
    its last bar that has a value (whitespace after it does not count), so a follower whose data stops earlier (broker
    data behind the prices: three sessions are about 195 candles on 5M) cannot take the main chart's range: it sits off
    the candles, and with the pointer on it pushes its clipped range back onto the main chart. An invisible series with a
    value on every candle gives the follower the same last bar. It sits on the follower's main price scale (`scale`, the
    one lightweight-charts positions a crosshair set from code against: with no value in the visible range it throws
    "Value is null") and adds nothing to that scale's range (autoscaleInfoProvider null); it draws nothing. Add it after
    the chart's own series: a price scale takes its number format from its first series. */
export function anchorTimeScale(L: any, chart: any, times: any[], scale = 'right') {
  const s = chart.addSeries(L.LineSeries, { priceScaleId:scale, lineVisible:false, pointMarkersVisible:false,
    crosshairMarkerVisible:false, priceLineVisible:false, lastValueVisible:false, autoscaleInfoProvider:() => null });
  s.setData(times.map(time => ({ time, value:0 })));
  return s;
}

/** series markers with candle keys */
export const keyedMarkers = (markers: any[]) => markers.map(point);
