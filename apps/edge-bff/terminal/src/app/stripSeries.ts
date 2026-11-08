/* EXEC-RP-LOOK-2 C (user 2026-11-08: "Strip panas satu baris hanya untuk FL26"; "bisa buat persis seperti di HTML ... jadi
   tingginya jangan setinggi itu"): a one-row heat strip as a custom series of the chart library. Each candle is a small
   rounded cell of a fixed height near the pane's foot (as in verification/terminal_api/flow_dots/flow_day_count_options.html
   option 5), its colour given per point (the direction, and the strength of the value); the value itself is read in
   the legend. A histogram cannot draw this: its bars always fill the pane's height and have square corners. */
import type * as LWC from 'lightweight-charts';

export interface StripPoint { time: LWC.Time; value: number; color: string }
const CELL_PX = 18, FOOT_PX = 6, RADIUS_PX = 3;

class StripRenderer implements LWC.ICustomSeriesPaneRenderer {
  data: LWC.PaneRendererCustomData<LWC.Time, StripPoint> | null = null;
  draw(target: any) {
    const d = this.data; if (!d || !d.visibleRange) return;
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
}

export class StripSeries implements LWC.ICustomSeriesPaneView<LWC.Time, StripPoint, LWC.CustomSeriesOptions> {
  private r = new StripRenderer();
  constructor(private defaults: LWC.CustomSeriesOptions) {}
  renderer() { return this.r }
  update(data: LWC.PaneRendererCustomData<LWC.Time, StripPoint>) { this.r.data = data }
  priceValueBuilder() { return [0, 1] }                     // a fixed scale: the cells sit at a fixed pixel height anyway
  isWhitespace(d: any): d is LWC.CustomSeriesWhitespaceData<LWC.Time> { return d.value === undefined }
  defaultOptions() { return this.defaults }
}
/** the pane height a strip needs: its legend row above, one row of cells and the foot */
export const STRIP_PANE_PX = (rowPx: number) => Math.max(56, Math.ceil(rowPx) + CELL_PX + FOOT_PX + 8);
