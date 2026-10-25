/* Price-axis labels next to the legend and the right axis that shows labels only while something lives on it
   (reference lines 2008-2045). */
import type { Ctx } from './context';
import { $ } from './context';

export function initAxis(ctx: Ctx) {
  const { chart, candle, mainLine, closes, active, volCtl } = ctx;
  /* ---- Y-axis labels never run up beside the legend (top-left) ---- */
  {
    const legendEl = document.querySelector('.chart-legend') as HTMLElement, host = $('chart');
    let xhPrice: number | null = null;
    chart.subscribeCrosshairMove(p => { try{ xhPrice = (p.point && p.point.y >= 0) ? candle.coordinateToPrice(p.point.y) : null }catch(e){ xhPrice = null } });
    const legBottom = () => legendEl.getBoundingClientRect().bottom - host.getBoundingClientRect().top;
    void legBottom;
    const near = (a: number, b: number | null | undefined) => b !== null && b !== undefined && Math.abs(a-b) <= Math.max(1e-6, Math.abs(b)*1e-9);
    const label = (v: number) => {
      const txt = ctx.displayMode === 'return' ? v.toFixed(1) + '%' : v.toFixed(2);
      if(active.size) return txt;                                   // compare series live on the other scale; leave labels alone
      try{
        const lastV = ctx.displayMode === 'return' ? (closes.at(-1)!/closes[0]-1)*100 : closes.at(-1)!;
        if(near(v, lastV) || near(v, xhPrice)) return txt;          // last-price badge + crosshair label stay visible

      }catch(e){}
      return txt;
    };
    ctx.axisLabel = label;
    volCtl.relabel = () => [candle, mainLine].forEach((sr: any) => sr.applyOptions({ priceFormat:ctx.formatMode() }));
    volCtl.relabel();
    new ResizeObserver(() => requestAnimationFrame(volCtl.relabel!)).observe(legendEl);
  }

  /* ---- the main pane's right axis shows labels only while something visible lives on it
          (compare series, Net Buy Flow (Line), other right-axis overlays). The axis keeps its width so the
          plot stays aligned with the Flow Timeline below. ---- */
  {
    let shown: boolean | null = null;
    const check = () => {
      let on = false;
      try{ on = chart.panes()[0].getSeries().some(s => { const o: any = s.options(); return o.visible !== false && (o.priceScaleId || 'right') === 'right' && s.data().length > 0 }) }catch(e){}
      if(on === shown) return; shown = on;
      chart.priceScale('right', 0).applyOptions({ textColor:on ? chart.options().layout.textColor : 'rgba(0,0,0,0)', ticksVisible:on });
    };
    setInterval(check, 300); requestAnimationFrame(check);
  }
}
