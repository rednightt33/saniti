/* When the indicators that follow the view are computed again (every definition with `viewBound`: an anchor or a start on
   the first candle in view, FL18-FL20, FL23, FL44, FL45, FL51, FL52 today). ERRORS M538, EXEC-TERMINAL-LAG-2 U1 (user
   2026-11-22: "U1 + U2 + U4 go"):
   - never while a pointer is held on the page (a drag of the chart, a pane or the time axis): the view is still moving;
   - `quiet` ms after the last move when no pointer is held (the release, a wheel, a key, the glide of a touch);
   - `hold` ms after the last move while the pointer is still held (the user stopped but did not let go; also the way out
     when the release happened outside the frame and was never seen).
   A time gap alone was not enough: with the CPU four times slower the frames of one drag are more than 150 ms apart, so
   the 1-1.7 s recompute ran in the middle of the drag (BBCA, the owner's 4 Flow indicators, 1 to 8 times per drag). */
export interface FollowTimers { set: (fn: () => void, ms: number) => unknown; clear: (id: unknown) => void }
export interface FollowOptions { quiet?: number; hold?: number; timers?: FollowTimers }
const realTimers: FollowTimers = { set: (fn, ms) => setTimeout(fn, ms), clear: id => clearTimeout(id as ReturnType<typeof setTimeout>) };

export function viewFollower(settle: () => void, { quiet = 150, hold = 1000, timers = realTimers }: FollowOptions = {}) {
  let held = false, timer: unknown = null;
  const fire = () => { timer = null; settle() };
  const arm = (ms: number) => { if (timer !== null) timers.clear(timer); timer = timers.set(fire, ms) };
  return {
    /** the visible range changed */
    moved() { arm(held ? hold : quiet) },
    /** a pointer went down: a waiting recompute waits for the release */
    down() { held = true; if (timer !== null) arm(hold) },
    /** the pointer was released: a waiting recompute runs `quiet` ms later (each further move restarts it) */
    up() { if (!held) return; held = false; if (timer !== null) arm(quiet) },
    get held() { return held },
    get pending() { return timer !== null },
  };
}

/** the page's pointer: down on any primary pointer, up on its release, its cancel, a move with no button (released outside
    the frame) or the window losing focus */
export function followPointer(f: { down(): void; up(): void }, doc: Document = document, win: Window = window) {
  doc.addEventListener('pointerdown', e => { if (e.isPrimary) f.down() }, true);
  doc.addEventListener('pointerup', e => { if (e.isPrimary) f.up() }, true);
  doc.addEventListener('pointercancel', e => { if (e.isPrimary) f.up() }, true);
  doc.addEventListener('pointermove', e => { if (e.buttons === 0) f.up() }, true);
  win.addEventListener('blur', () => f.up());
}
