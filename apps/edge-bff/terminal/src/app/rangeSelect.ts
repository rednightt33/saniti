/* EXEC-TERMINAL-PANELS C1 (user 2026-10-26: "kita tinggal draw, maka broker summary dan lain sebagainya langsung
   terupdate di panel sebelah kanan"): drag across the main chart to choose a period. While the mode is on, a layer over
   the chart takes the pointer (the chart neither pans nor zooms), shades the chosen sessions and hands the first and
   last session dates to `done`. Escape cancels. */
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
    layer.append(band, hint); wrap.appendChild(layer); wrap.classList.add('rs-on');
    // a deep copy: applyOptions merges into the chart's own option objects, so a reference would turn off too
    const opts: any = chart.options(), keep = JSON.parse(JSON.stringify({ handleScroll:opts.handleScroll, handleScale:opts.handleScale }));
    chart.applyOptions({ handleScroll:false, handleScale:false });
    const left = () => chart.priceScale('left').width();
    const xOf = (e: PointerEvent) => e.clientX - $('chart').getBoundingClientRect().left - left();
    const logical = (x: number) => chart.timeScale().coordinateToLogical(x) as number | null;
    /* EXEC-TERMINAL-PANELS-2 (user 2026-10-27: "tinggal click sekali dan click sekali lagi pada tanggal yang sama"): a
       drag picks its sessions at once; a click without a drag sets the first day, the next click the last day (the
       same day gives a one-day period). The band follows the pointer between the two clicks. */
    const HINT = 'Drag, or click the first and the last day (twice the same day for one day) · Esc to cancel';
    hint.textContent = HINT;
    let x0: number | null = null, pressed = false, firstClick = false;
    const sessions = (a: number, b: number) => sessionsBetween(ctx.dates, logical(Math.min(a, b)) ?? NaN, logical(Math.max(a, b)) ?? NaN);
    // EXEC-TERMINAL-WM: a weekly or monthly candle's period runs to its last session
    const endOf = (start: string) => ctx.endDates[ctx.idxByTime.get(start) ?? -1] ?? start;
    const paint = (x1: number) => {
      const s = sessions(x0!, x1);
      // the band spans whole sessions: from the left edge of the first to the right edge of the last
      const ts = chart.timeScale(), w = Math.max(2, ts.options().barSpacing);
      const xa = s ? ts.timeToCoordinate(s[0] as any) : null, xb = s ? ts.timeToCoordinate(s[1] as any) : null;
      const a = xa != null ? xa - w / 2 : Math.min(x0!, x1), b = xb != null ? xb + w / 2 : Math.max(x0!, x1);
      band.hidden = false; band.style.left = left() + a + 'px'; band.style.width = Math.max(1, b - a) + 'px';
      const e = s ? endOf(s[1]) : '';
      hint.textContent = s ? (s[0] === e ? longDay(s[0]) : `${longDay(s[0])} – ${longDay(e)}`) + (firstClick ? ' · click the last day' : '') : HINT;
    };
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault(); layer.setPointerCapture(e.pointerId); pressed = true;
      if (!firstClick) { x0 = xOf(e); paint(x0) }
    };
    const move = (e: PointerEvent) => { if (x0 !== null && (pressed || firstClick)) paint(xOf(e)) };
    const up = (e: PointerEvent) => {
      if (x0 === null || !pressed) return;
      pressed = false;
      const x1 = xOf(e);
      if (!firstClick && Math.abs(x1 - x0) < 3) { firstClick = true; paint(x1); return }   // the first click: wait for the second
      const s = sessions(x0, x1);
      stop(); if (s) done(s[0], endOf(s[1]));
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
