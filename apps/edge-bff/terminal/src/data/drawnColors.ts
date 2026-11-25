/* Checker S-6 and its re-check (wf_c2fe2424-bf4/terminal:S-6): the colours an indicator draws on the chart now, for the
   "used" row of both colour boxes (an indicator's settings and a compare line's). They are read from what is drawn, the
   way each kind of output draws (app/indicators.ts refreshMulti, refreshLines, refreshPlot), not from every colour its
   saved style holds: a colour a saved entry carries that nothing draws is not offered. Before, every colour of the style
   was: a registry indicator's old top-level `style.color` (kept by a saved list or a layout), an output turned off or
   one the indicator no longer has, and Net Buy Flow (Line)'s style colour (its lines take a colour per broker).
     - an indicator hidden by its eye or folded draws nothing;
     - a registry indicator, per output drawn (`part`): its four quadrant colours (FL49), its palette where the indicator
       colours the line per bar (Alpha KAMA), the state colours of a state histogram, both colours of a histogram, a
       strip, cells, a two-colour line and dots that follow a direction, else its one colour;
     - lines per broker: the lines' colours; one series: its colour, and its sell colour as bars. */

export interface ShownNow { inst: boolean; part: (pt: any) => boolean }

export function drawnColors(inst: any, shown: ShownNow, stateColors: readonly string[] = []): string[] {
  if (!inst || !shown.inst) return [];
  const st = inst.style || {};
  if (inst.def?.multi) return (inst.parts || []).flatMap((pt: any) => {
    const s = st.out?.[pt.o.k];
    if (!s || !shown.part(pt)) return [];
    const two = [s.color, s.color2 || s.color];
    if (pt.o.quad) return [0, 1, 2, 3].map(v => s.quad?.[v] || pt.o.quad[v]);
    if (pt.kind === 'line' && Array.isArray(pt.o.palette) && pt.o.paletteFrom) return pt.o.palette;
    if (pt.kind === 'hist') return s.states && /optional_state/.test(pt.o.rule || '') ? [...stateColors, s.color] : two;
    if (pt.kind === 'strip' || pt.kind === 'cells' || pt.kind === 'seg') return two;
    if (pt.kind === 'dots') return inst.disp?.direction ? two : [s.color];
    return [s.color];
  }).filter(Boolean);
  if (inst.def?.lines) return (inst.lines || []).map((l: any) => l.color).filter(Boolean);
  return (inst.sType === 'hist' ? [st.color, st.colorNeg] : [st.color]).filter(Boolean);
}
