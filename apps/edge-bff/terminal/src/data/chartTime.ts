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

/** series markers with candle keys */
export const keyedMarkers = (markers: any[]) => markers.map(point);
