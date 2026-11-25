/* EXEC-PINE-INDICATORS (the user 2026-11-23, UD32 "All at once"; the TradingView colour box the user showed): the Style
   tab's colour box. A grid of colours (a grey row, ten hues, four tints and two shades of each), the colours already in
   use on the chart with a custom one (+, the browser's colour chooser), and, where the caller gives them, opacity,
   thickness and line style. The line options are offered on the indicators drawn on the price chart only (the user: "opsi
   garis ini hanya untuk indikator yang ketika ditambahkan akan muncul overlay di chart ya"; UD31). One box for the
   indicators' outputs (app/indicators.ts) and the compare lines (app/assets.ts); the caller places it and closes it. */

export const HUES = ['#f23645', '#ff9800', '#ffeb3b', '#4caf50', '#089981', '#00bcd4', '#2962ff', '#673ab7', '#9c27b0', '#e91e63'];
const HUE_NAMES = ['Red', 'Orange', 'Yellow', 'Green', 'Teal', 'Cyan', 'Blue', 'Purple', 'Violet', 'Pink'];
const GREYS = ['#ffffff', '#e0e0e0', '#bdbdbd', '#9e9e9e', '#787878', '#5d5d5d', '#434343', '#2a2a2a', '#171717', '#000000'];
const hex = (n: number) => Math.round(Math.min(255, Math.max(0, n))).toString(16).padStart(2, '0');
/** `c` moved toward `to` by t (0: c, 1: to) */
export function mix(c: string, to: string, t: number): string {
  const a = parseInt(c.slice(1), 16), b = parseInt(to.slice(1), 16);
  const ch = (x: number, s: number) => (x >> s) & 255;
  return '#' + [16, 8, 0].map(s => hex(ch(a, s) + (ch(b, s) - ch(a, s)) * t)).join('');
}
/** the grid's rows, top to bottom: greys, the hues, their tints (lighter first), their shades */
export const COLOR_GRID: string[][] = [GREYS, HUES, ...[0.8, 0.6, 0.4, 0.2].map(t => HUES.map(h => mix(h, '#ffffff', t))), ...[0.25, 0.5].map(t => HUES.map(h => mix(h, '#000000', t)))];
/** a swatch's spoken name (checker S-9: a screen reader said hex codes): "White", "Grey 3", "Red", "Red light 2", "Red dark 1" */
export const COLOR_NAMES: string[][] = [GREYS.map((_, k) => k === 0 ? 'White' : k === 9 ? 'Black' : `Grey ${k}`), HUE_NAMES,
  ...[4, 3, 2, 1].map(n => HUE_NAMES.map(h => `${h} light ${n}`)), ...[1, 2].map(n => HUE_NAMES.map(h => `${h} dark ${n}`))];
const nameOf = new Map(COLOR_GRID.flatMap((row, r) => row.map((c, k) => [c, COLOR_NAMES[r][k]] as [string, string])));
export const LINE_STYLE_KEYS = ['Solid', 'Dashed', 'Dotted'] as const;
export type LineStyleKey = typeof LINE_STYLE_KEYS[number];
/** The line options an output's colour box offers (UD31): only on an indicator drawn on the price chart (zone overlay) and
    only for an output drawn as a line: opacity and thickness for a line, a stepped segment or dots, the line style for
    the first two (dots have none). Null: the box holds the colours only (panels, histograms, shapes, fills). */
export function lineOptions(zone: string | undefined, kind: string | undefined): { style: boolean } | null {
  if (zone !== 'overlay') return null;
  return kind === 'line' || kind === 'seg' ? { style: true } : kind === 'dots' ? { style: false } : null;
}

export interface PickerOptions {
  label: string;
  /** the colour and its setter; left out for an output coloured by its indicator (a palette): the box then holds the line
      options only (checker S-2/C-2: a colour that changed nothing was offered) */
  color?: () => string; setColor?: (c: string) => void;
  /** colours in use on the chart, shown beside the custom button (none: the row holds the button only) */
  used?: string[];
  opacity?: { get: () => number; set: (v: number) => void };          // 0-100
  width?: { get: () => number; set: (v: number) => void };            // 1-4 px
  lineStyle?: { get: () => LineStyleKey; set: (v: LineStyleKey) => void };
  /** called after every change; `done` true when the box should close (a colour picked in a box without line options) */
  onChange: (done: boolean) => void;
  /** the Done button's action (a touch screen); none: no button */
  onDone?: () => void;
}

const norm = (c: string) => (c || '').toLowerCase();
function swatch(c: string, current: string, pick: (c: string) => void): HTMLButtonElement {
  const s = document.createElement('button'); s.type = 'button'; s.className = 'cpk-sw'; s.style.background = c; s.dataset.c = norm(c);
  const name = nameOf.get(norm(c)) || `Colour ${norm(c)}`; s.setAttribute('aria-label', name); s.title = `${name} ${c}`; s.setAttribute('aria-pressed', String(norm(current) === norm(c)));
  s.onclick = e => { e.preventDefault(); e.stopPropagation(); pick(c) };
  return s;
}
function segment<T extends string | number>(label: string, values: readonly T[], current: T, draw: (v: T) => HTMLElement, set: (v: T) => void): HTMLElement {
  const row = document.createElement('div'); row.className = 'cpk-row';
  const name = document.createElement('span'); name.className = 'cpk-lab'; name.textContent = label;
  const seg = document.createElement('div'); seg.className = 'cpk-seg'; seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', label);
  for (const v of values) {
    const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-pressed', String(v === current)); b.setAttribute('aria-label', `${label} ${v}`);
    b.append(draw(v));
    b.onclick = e => { e.preventDefault(); e.stopPropagation(); seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b))); set(v) };
    seg.append(b);
  }
  row.append(name, seg);
  return row;
}
const stroke = (width: number, style: LineStyleKey) => { const i = document.createElement('i'); i.className = 'cpk-line';
  i.style.borderTop = `${width}px ${style === 'Solid' ? 'solid' : style === 'Dashed' ? 'dashed' : 'dotted'} currentColor`; return i };

/** The box's content (the caller wraps it in its own positioned `.idlg-cpop` and closes it). */
export function buildColorPicker(o: PickerOptions): HTMLElement {
  // re-check NEW-2: a box without colours (a palette line) is named for its line, as its button is
  const box = document.createElement('div'); box.className = 'cpk'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', `${o.label} ${o.color ? 'colour' : 'line'}`);
  const lines = !!(o.opacity || o.width || o.lineStyle);
  if (o.color && o.setColor) {
    const color = o.color, setColor = o.setColor;
    const pick = (c: string) => { setColor(c); box.querySelectorAll<HTMLElement>('.cpk-sw').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.c === norm(c)))); o.onChange(!lines) };
    const grid = document.createElement('div'); grid.className = 'cpk-grid';
    COLOR_GRID.forEach((row, r) => { row.forEach(c => grid.append(swatch(c, color(), pick))); if (r === 1) { const gap = document.createElement('span'); gap.className = 'cpk-gap'; grid.append(gap) } });
    box.append(grid);
    // the colours in use and a custom one: the browser's colour chooser, its value applied as it changes
    const used = document.createElement('div'); used.className = 'cpk-used';
    usedRow(color(), o.used || []).forEach(c => used.append(swatch(c, color(), pick)));
    const add = document.createElement('label'); add.className = 'cpk-add'; add.title = 'Custom colour';
    const inp = document.createElement('input'); inp.type = 'color'; inp.value = /^#[0-9a-f]{6}$/i.test(color()) ? color() : '#2962ff'; inp.setAttribute('aria-label', 'Custom colour');
    inp.oninput = () => { setColor(inp.value); o.onChange(false) };
    inp.onchange = () => { setColor(inp.value); o.onChange(!lines) };
    add.append(inp, document.createTextNode('+'));
    used.append(add);
    box.append(used);
  }
  if (lines) {
    if (o.color) { const hr = document.createElement('hr'); hr.className = 'cpk-hr'; box.append(hr) }
    if (o.opacity) {
      const row = document.createElement('div'); row.className = 'cpk-row';
      const name = document.createElement('span'); name.className = 'cpk-lab'; name.textContent = 'Opacity';
      const r = document.createElement('input'); r.type = 'range'; r.min = '0'; r.max = '100'; r.step = '1'; r.value = String(o.opacity.get()); r.className = 'cpk-range'; r.setAttribute('aria-label', 'Opacity');
      const n = document.createElement('span'); n.className = 'cpk-pct'; n.textContent = `${o.opacity.get()}%`;
      r.oninput = () => { const v = Math.max(0, Math.min(100, Number(r.value))); n.textContent = `${v}%`; o.opacity!.set(v); o.onChange(false) };
      row.append(name, r, n); box.append(row);
    }
    if (o.width) box.append(segment('Thickness', [1, 2, 3, 4] as const, o.width.get() as 1, w => stroke(w, 'Solid'), w => { o.width!.set(w); o.onChange(false) }));
    if (o.lineStyle) box.append(segment('Line style', LINE_STYLE_KEYS, o.lineStyle.get(), k => stroke(2, k), k => { o.lineStyle!.set(k); o.onChange(false) }));
  }
  /* re-check S-3: on a touch screen the box may cover the dialog (no room beside it): a Done button closes it (shown by
     the stylesheet for a coarse pointer only) */
  if (o.onDone) { const done = document.createElement('button'); done.type = 'button'; done.className = 'cpk-done'; done.textContent = 'Done'; done.onclick = e => { e.preventDefault(); e.stopPropagation(); o.onDone!() }; box.append(done) }
  return box;
}

/* Checker round 1 (2026-11-23), S-1/C-1/S-3: the box ran off the bottom of the window (its line options out of reach) and
   covered the colour buttons of the rows below. It now sits beside the dialog where the window has room (never over
   the dialog's own controls), else under or over its button, always inside the window; a box taller than the window
   scrolls. All in window coordinates. */
export interface Rect { left: number; top: number; right: number; bottom: number }
export function placeColorBox(vp: { w: number; h: number }, dlg: Rect, btn: Rect, size: { w: number; h: number }) {
  const M = 8, h = Math.min(size.h, vp.h - 2 * M), maxH = size.h > vp.h - 2 * M ? vp.h - 2 * M : null;
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  const nearBtn = clamp(btn.top - 12, M, vp.h - h - M);
  if (dlg.right + M + size.w <= vp.w - M) return { left: dlg.right + M, top: nearBtn, maxH, side: 'right' as const };
  if (dlg.left - M - size.w >= M) return { left: dlg.left - M - size.w, top: nearBtn, maxH, side: 'left' as const };
  const left = clamp(btn.right - size.w, M, vp.w - size.w - M);
  if (btn.bottom + 6 + h <= vp.h - M) return { left, top: btn.bottom + 6, maxH, side: 'below' as const };
  if (btn.top - 6 - h >= M) return { left, top: btn.top - 6 - h, maxH, side: 'above' as const };
  return { left, top: Math.max(M, vp.h - h - M), maxH, side: 'inside' as const };
}

/* One open colour box per dialog, for the indicators' Style tab (app/indicators.ts) and the compare lines (app/assets.ts):
   opened from a button, closed by a press elsewhere in the dialog, Escape, a second press on its button, or a colour
   picked in a box without line options; the focus returns to its button (checker S-4). A press on the backdrop while a
   box is open closes the box only (checker S-7): `backdropDown` says so, and the dialog skips that click. */
/** The box's row of colours in use (beyond the grid, at most nine): its own colour first, so it always has its selected
    swatch (re-check round 2, T2-2: a hidden indicator draws nothing, so its colour was not in `used` and the focus fell on
    the next control), then the colours drawn on the chart, each once, as #rrggbb. */
export function usedRow(current: string, used: readonly string[]): string[] {
  const inGrid = new Set(COLOR_GRID.flat().map(norm));
  return [...new Set([current, ...used].map(norm))].filter(c => /^#[0-9a-f]{6}$/.test(c) && !inGrid.has(c)).slice(0, 9);
}

export class ColorBoxHost {
  box: (HTMLDivElement & { owner?: HTMLElement }) | null = null;
  private swallow = false;
  constructor(private dlg: HTMLElement) {
    dlg.addEventListener('pointerdown', (e: any) => { if (this.box && !this.box.contains(e.target) && !this.box.owner!.contains(e.target)) this.close() });
  }
  get open() { return !!this.box }
  close(refocus = false) {
    if (!this.box) return;
    const owner = this.box.owner!; owner.classList.remove('open'); this.box.remove(); this.box = null;
    if (refocus) owner.focus();
  }
  /** Escape: true when it closed a box (the dialog then stays open) */
  escape(): boolean { if (!this.box) return false; this.close(true); return true }
  /** the backdrop's mousedown: closes an open box; the click that follows on the backdrop is then the box's, not the dialog's */
  backdropDown(e: any) { this.swallow = false; if (this.box && !this.box.contains(e.target) && e.target !== this.box.owner) { this.swallow = e.target === e.currentTarget; this.close() } }
  /** the backdrop's click: true when it is the click of the press that closed a box; only a click on the backdrop itself
      (re-check NEW-1: a press released elsewhere left the mark, and the next Enter on Ok was swallowed) */
  swallowClick(e: any): boolean { const s = this.swallow && e.target === e.currentTarget; this.swallow = false; return s }
  toggle(owner: HTMLElement, o: PickerOptions) {
    const was = this.box && this.box.owner === owner; this.close(); if (was) return;
    const box = document.createElement('div') as HTMLDivElement & { owner?: HTMLElement };
    box.className = 'idlg-cpop has-cpk'; box.owner = owner; owner.classList.add('open'); this.box = box;
    box.appendChild(buildColorPicker({ ...o, onChange: done => { o.onChange(done); if (done) this.close(true) }, onDone: () => this.close(true) }));
    this.dlg.appendChild(box);
    const b = owner.getBoundingClientRect(), d = this.dlg.getBoundingClientRect();
    const at = placeColorBox({ w: innerWidth, h: innerHeight }, d, b, { w: box.offsetWidth, h: box.offsetHeight });
    if (at.maxH) { box.style.maxHeight = at.maxH + 'px'; box.style.overflowY = 'auto' }
    box.dataset.side = at.side;
    box.style.left = (at.left - d.left) + 'px'; box.style.top = (at.top - d.top) + 'px';
    (box.querySelector('[aria-pressed="true"]') as HTMLElement | null ?? box.querySelector('button,input') as HTMLElement | null)?.focus();
  }
}
