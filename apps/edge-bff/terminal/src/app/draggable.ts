/* User 2026-11-01: "pop up box indicator harus bisa di hover kiri kanan atas bawah dengan ngeklik header". A dialog box
   moves with its header: press on the header (not on a button or a field in it) and drag left, right, up or down. The
   box keeps at least 80 px of its header on screen, so it can always be dragged back. A box that stays in the page keeps
   its place while the page is open; a box built anew on each opening starts centred. */
export function draggable(box: HTMLElement | null, handle: HTMLElement | null): void {
  if (!box || !handle || (handle as any)._drag) return;
  (handle as any)._drag = true;
  let x = 0, y = 0;
  /* the place kept from an earlier drag, pulled back on screen (the window was narrowed, a phone turned): the same limits */
  const fit = () => {
    [x, y] = shiftOf(box);
    if (!x && !y) return;
    const r = box.getBoundingClientRect(); if (!r.width) return;            // hidden: fitted when shown
    const left = r.left - x, top = r.top - y;
    x = Math.min(Math.max(x, 80 - left - r.width, -left), Math.max(innerWidth - left - r.width, 80 - left - r.width));
    y = Math.min(Math.max(y, -top), innerHeight - 40 - top);
    box.style.translate = x || y ? `${x}px ${y}px` : '';
  };
  (box as any).fitInView = fit;
  addEventListener('resize', fit);
  handle.style.cursor = 'move';
  handle.style.touchAction = 'none';
  handle.style.userSelect = 'none';
  handle.addEventListener('pointerdown', (e: PointerEvent) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button, input, select, textarea, a, [role="tab"]')) return;
    e.preventDefault();
    [x, y] = shiftOf(box);                                   // a resize may have moved it
    const r = box.getBoundingClientRect(), left = r.left - x, top = r.top - y, sx = e.clientX - x, sy = e.clientY - y;
    handle.setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      x = Math.min(Math.max(ev.clientX - sx, 80 - left - r.width), innerWidth - 80 - left);
      y = Math.min(Math.max(ev.clientY - sy, -top), innerHeight - 40 - top);
      box.style.translate = `${x}px ${y}px`;
    };
    const up = () => {
      handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up); handle.removeEventListener('pointercancel', up);
    };
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up); handle.addEventListener('pointercancel', up);
  });
}

/** a box made draggable: bring it back on screen when it is shown again (call after unhiding it) */
export const fitInView = (box: HTMLElement | null) => { (box as any)?.fitInView?.() };

/** the box's shift (its `translate`): the browser writes "75px 0px" back as "75px", so a missing y is 0 */
export function shiftOf(box: HTMLElement): [number, number] {
  const [a, b] = (box.style.translate || '').split(/\s+/).map(v => parseFloat(v));
  return [Number.isFinite(a) ? a : 0, Number.isFinite(b) ? b : 0];
}
