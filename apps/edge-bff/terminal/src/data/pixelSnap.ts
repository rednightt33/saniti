/* EXEC-PINE-INDICATORS checker V1-7 and its re-checks (wf_c2fe2424-bf4/terminal:NEW-1): a box drawn on a chart canvas in
   media pixels (a label of Alpha Extract or Alpha Divergence, a broker's tag at a line's end) sits on whole pixels of
   that canvas. Each axis has its own ratio, the canvas's bitmap size over its media size (a pane of a fractional height
   has a vertical ratio other than its horizontal one: 135 bitmap rows for 135.19 media px), and every edge is snapped:
   the left and top edges by their position, the width and height by their size, so the right and bottom edges land on
   the grid as well and a box keeps its size while the chart moves. Before, the height stayed as given: an 18 px box at
   a vertical ratio of 0.9986 ended 0.025 bitmap px off its row (12 of 46 boxes at device scale 1.25 and 1.5). */

export interface PixelRatio { h: number; v: number }
/** `v` media px on the nearest whole pixel of a canvas whose ratio on that axis is `r` */
export const snapTo = (v: number, r: number) => Math.round(v * r) / r;
/** the box (left, top, width, height in media px) with every edge on a whole pixel of the canvas */
export function snapBox(x: number, y: number, w: number, h: number, ratio: PixelRatio) {
  return { x:snapTo(x, ratio.h), y:snapTo(y, ratio.v), w:snapTo(w, ratio.h), h:snapTo(h, ratio.v) };
}
