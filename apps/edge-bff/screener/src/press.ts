/* EXEC-SCREENER-V21 QA H1 (ERRORS M357): a control the page re-creates between the press and the release of a pointer
   loses its click. The browser sends the click to the nearest parent the pressed and the released node share, so a
   button replaced in between never hears it. The page redraws an area in three cases that can fall inside a press:
   - the blur and change of the field the press leaves (the press itself moves the focus);
   - the 350 ms debounce of a number field;
   - a run, preview or column answer.
   A drawing that only adds content can lose the click too: the out-of-date bar appearing above the table pushes the
   pressed column header down, and the release lands on another node.
   Seen on the fixture page: type a value, then click Screen now or a column header, and the first click did nothing.
   So every area renderer (app.ts refresh and renderHeader, results.ts renderResults, builder.ts renderConds,
   universe-ui.ts renderUniverse, presets-ui.ts renderPresets, preview.ts renderDetails, screen-gate.ts renderScreen)
   asks afterPress first. While a pointer is pressed, the drawing waits and runs once after the click; the last request
   of each area wins. The state an edit changes (S, the gate's flags: run.ts sync) is set at once; only the drawing
   waits.
   The Screen now controls are also patched in place (screen-gate.ts renderScreen), so they are never re-created by
   a drawing outside a press either (a run answer, a keyboard edit), and keep the focus.
   A press that never ends (released outside the window, a native scrollbar) ends by itself after LONG_PRESS_MS; then
   the page draws as before, under the pointer. */
export const LONG_PRESS_MS = 2000;

let down = false;
let safety: ReturnType<typeof setTimeout> | undefined;
const waiting = new Map<string, () => void>();

/** whether a pointer is pressed now */
export function pressHeld(): boolean { return down }

/** While a pointer is pressed, keep `draw` to run once the press ends (after its click) and return true; else return
    false and let the caller draw now. One draw per area: a later request of the same area replaces the earlier one. */
export function afterPress(area: string, draw: () => void): boolean {
  if (!down) return false;
  waiting.set(area, draw);
  return true;
}

function start() {
  down = true;
  clearTimeout(safety); safety = setTimeout(end, LONG_PRESS_MS);
}
function end() {
  if (!down) return;
  down = false; clearTimeout(safety);
  // pointerup, mouseup and click are sent in one task, so a timer of 0 runs after the click
  setTimeout(release, 0);
}
function release() {
  if (down || !waiting.size) return;                 // a new press began: its own end draws
  const draws = [...waiting.values()]; waiting.clear();
  for (const d of draws) d();
}

/** Watch the presses of `doc` (capture phase, before any handler of the page) and the window's loss of focus. A tap
    on a touch screen sends pointerdown and pointerup, then mousedown, mouseup and click in one later task: mousedown
    starts a press again, so the focus moved by the tap waits too. */
export function bindPress(doc: EventTarget, win?: EventTarget) {
  for (const n of ['pointerdown', 'mousedown']) doc.addEventListener(n, start, true);
  for (const n of ['pointerup', 'mouseup', 'pointercancel', 'dragstart']) doc.addEventListener(n, end, true);
  win?.addEventListener('blur', end);
}

/** tests: forget any press and any waiting draw */
export function resetPress() { down = false; clearTimeout(safety); waiting.clear() }
