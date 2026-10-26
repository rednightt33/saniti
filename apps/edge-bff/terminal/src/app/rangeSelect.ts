/* EXEC-TERMINAL-PANELS C1 (user 2026-10-26: "kita tinggal draw, maka broker summary dan lain sebagainya langsung
   terupdate di panel sebelah kanan"): drag across the main chart to choose a period. While the mode is on, a layer over
   the chart takes the pointer (the chart neither pans nor zooms), shades the dragged sessions and hands the first and
   last session dates to `done`. Escape or a click without a drag cancels. */
import type { Ctx } from './context';
import { $ } from './context';
import { longDay } from '../ui/calendar';

/** the sessions between two logical positions, clamped to the chart's dates; null when nothing is covered */
export function sessionsBetween(dates: string[], a: number, b: number): [string, string] | null {
  if (!dates.length || !Number.isFinite(a) || !Number.isFinite(b)) return null;
  const lo = Math.max(0, Math.round(Math.min(a, b))), hi = Math.min(dates.length - 1, Math.round(Math.max(a, b)));
  return lo > hi ? null : [dates[lo], dates[hi]];
}

export function initRangeSelect(ctx: Ctx) {
  const { chart } = ctx;
  const wrap = $('chart').parentElement as HTMLElement;
  let active: (() => void) | null = null;

  ctx.selectRangeOnChart = (done: (from: string, to: string) => void) => {
    active?.();
    const layer = document.createElement('div'); layer.className = 'rs-layer';
    const band = document.createElement('div'); band.className = 'rs-band'; band.hidden = true;
    const hint = document.createElement('div'); hint.className = 'rs-hint';
    hint.textContent = 'Drag across the chart to choose the period · Esc to cancel';
    layer.append(band, hint); wrap.appendChild(layer); wrap.classList.add('rs-on');
    // a deep copy: applyOptions merges into the chart's own option objects, so a reference would turn off too
    const opts: any = chart.options(), keep = JSON.parse(JSON.stringify({ handleScroll:opts.handleScroll, handleScale:opts.handleScale }));
    chart.applyOptions({ handleScroll:false, handleScale:false });
    const left = () => chart.priceScale('left').width();
    const xOf = (e: PointerEvent) => e.clientX - $('chart').getBoundingClientRect().left - left();
    const logical = (x: number) => chart.timeScale().coordinateToLogical(x) as number | null;
    let x0: number | null = null;
    const paint = (x1: number) => {
      const a = Math.min(x0!, x1), b = Math.max(x0!, x1);
      band.hidden = false; band.style.left = left() + a + 'px'; band.style.width = Math.max(1, b - a) + 'px';
      const s = sessionsBetween(ctx.dates, logical(a) ?? NaN, logical(b) ?? NaN);
      hint.textContent = s ? `${longDay(s[0])} – ${longDay(s[1])}` : 'Drag across the chart to choose the period · Esc to cancel';
    };
    const down = (e: PointerEvent) => { if (e.button !== 0) return; e.preventDefault(); layer.setPointerCapture(e.pointerId); x0 = xOf(e); paint(x0) };
    const move = (e: PointerEvent) => { if (x0 !== null) paint(xOf(e)) };
    const up = (e: PointerEvent) => {
      if (x0 === null) return;
      const x1 = xOf(e), s = Math.abs(x1 - x0) >= 3 ? sessionsBetween(ctx.dates, logical(x0) ?? NaN, logical(x1) ?? NaN) : null;
      stop(); if (s) done(s[0], s[1]);
    };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') stop() };
    function stop() {
      layer.remove(); wrap.classList.remove('rs-on'); document.removeEventListener('keydown', key);
      chart.applyOptions(keep as any); active = null;
    }
    layer.addEventListener('pointerdown', down); layer.addEventListener('pointermove', move);
    layer.addEventListener('pointerup', up); layer.addEventListener('pointercancel', stop);
    document.addEventListener('keydown', key);
    active = stop;
  };
}
