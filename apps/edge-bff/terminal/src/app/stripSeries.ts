/* EXEC-RP-LOOK-2 C (user 2026-11-08: "Strip panas satu baris hanya untuk FL26"; "bisa buat persis seperti di HTML ... jadi
   tingginya jangan setinggi itu"): a one-row heat strip as a custom series of the chart library. Each candle is a small
   rounded cell of a fixed height near the pane's foot (as in verification/terminal_api/flow_dots/flow_day_count_options.html
   option 5), its colour given per point (the direction, and the strength of the value); the value itself is read in
   the legend. A histogram cannot draw this: its bars always fill the pane's height and have square corners. */
import type * as LWC from 'lightweight-charts';

export interface StripPoint { time: LWC.Time; value: number; color: string }
const CELL_PX = 18, FOOT_PX = 6, RADIUS_PX = 3, TOP_PX = 30;   // TOP_PX: the legend row's room above the cells

class StripRenderer implements LWC.ICustomSeriesPaneRenderer {
  data: LWC.PaneRendererCustomData<LWC.Time, StripPoint> | null = null;
  constructor(private mode: 'strip' | 'cells') {}
  draw(target: any) {
    const d = this.data; if (!d || !d.visibleRange) return;
    if (this.mode === 'cells') return this.cells(target, d);
    target.useBitmapCoordinateSpace((scope: any) => {
      const c = scope.context as CanvasRenderingContext2D, hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
      const step = d.barSpacing, gap = step >= 6 ? Math.max(1, step * 0.22) : step >= 3 ? 1 : 0;   // cells apart when there is room
      const w = Math.max(1, (step - gap) * hr), h = Math.round(CELL_PX * vr), y = Math.round(scope.bitmapSize.height - (FOOT_PX + CELL_PX) * vr);
      const r = Math.min(RADIUS_PX * hr, w / 2, h / 2);
      for (let i = d.visibleRange.from; i < d.visibleRange.to; i++) {
        const b = d.bars[i]; if (!b) continue;
        const p = b.originalData as StripPoint, col = (b as any).barColor || p.color;   // the library hands the point's colour as barColor
        if (p.value === undefined || !col) continue;
        const x = Math.round(b.x * hr - w / 2);
        c.fillStyle = col; c.beginPath();
        if (r >= 1 && (c as any).roundRect) (c as any).roundRect(x, y, w, h, r); else c.rect(x, y, w, h);
        c.fill();
      }
    });
  }
  /* EXEC-RP-LOOK-2 C ("Kolom kotak tanpa ruang kosong", option 2 of the HTML): one square per unit of the value, stacked
     up from the zero line for a positive value and down for a negative one; the square fits the candle's width and the
     longest column in the data (both sides) fits the pane, so a zoom never cuts a column */
  private cells(target: any, d: LWC.PaneRendererCustomData<LWC.Time, StripPoint>) {
    let up = 0, dn = 0;
    for (const b of d.bars) { const v = (b.originalData as StripPoint).value; if (v === undefined) continue; if (v > up) up = v; if (-v > dn) dn = -v }
    if (!up && !dn) return;
    target.useBitmapCoordinateSpace((scope: any) => {
      const c = scope.context as CanvasRenderingContext2D, hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
      const top = Math.round(TOP_PX * vr), foot = Math.round(FOOT_PX * vr), H = scope.bitmapSize.height - top - foot;
      const gap = Math.max(1, Math.round(1.5 * hr)), byH = Math.floor(H / (up + dn)), byW = Math.floor(d.barSpacing * hr * 0.85);
      const cell = Math.max(2, Math.min(byH, byW)), side = Math.max(1, cell - gap), y0 = top + up * cell;
      const r = Math.min(RADIUS_PX * hr, side / 3);
      for (let i = d.visibleRange!.from; i < d.visibleRange!.to; i++) {
        const b = d.bars[i]; if (!b) continue;
        const p = b.originalData as StripPoint, col = (b as any).barColor || p.color; if (p.value === undefined || !col) continue;
        const n = Math.round(Math.abs(p.value)), x = Math.round(b.x * hr - side / 2);
        c.fillStyle = col;
        for (let k = 0; k < n; k++) {
          const y = p.value > 0 ? y0 - (k + 1) * cell + gap : y0 + k * cell + gap;
          c.beginPath(); if (r >= 1 && (c as any).roundRect) (c as any).roundRect(x, y, side, side, r); else c.rect(x, y, side, side); c.fill();
        }
      }
      c.fillStyle = 'rgba(143,143,143,.6)'; c.fillRect(0, y0 + Math.floor(gap / 2), scope.bitmapSize.width, Math.max(1, Math.round(vr)));   // the zero line
    });
  }
}

export class StripSeries implements LWC.ICustomSeriesPaneView<LWC.Time, StripPoint, LWC.CustomSeriesOptions> {
  private r: StripRenderer;
  constructor(private defaults: LWC.CustomSeriesOptions, mode: 'strip' | 'cells' = 'strip') { this.r = new StripRenderer(mode) }
  renderer() { return this.r }
  update(data: LWC.PaneRendererCustomData<LWC.Time, StripPoint>) { this.r.data = data }
  priceValueBuilder() { return [0, 1] }                     // a fixed scale: the cells sit at a fixed pixel height anyway
  isWhitespace(d: any): d is LWC.CustomSeriesWhitespaceData<LWC.Time> { return d.value === undefined }
  defaultOptions() { return this.defaults }
}
/** the pane height a strip needs: its legend row above, one row of cells and the foot */
export const STRIP_PANE_PX = (rowPx: number) => Math.max(56, Math.ceil(rowPx) + CELL_PX + FOOT_PX + 8);
