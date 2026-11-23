/* EXEC-PINE-INDICATORS (the user 2026-11-23, UD32 "All at once"; the TradingView colour box the user showed): the Style
   tab's colour box. A grid of colours (a grey row, ten hues, four tints and two shades of each), the colours already in
   use on the chart with a custom one (+, the browser's colour chooser), and, where the caller gives them, opacity,
   thickness and line style. The line options are offered on the indicators drawn on the price chart only (the user: "opsi
   garis ini hanya untuk indikator yang ketika ditambahkan akan muncul overlay di chart ya"; UD31). One box for the
   indicators' outputs (app/indicators.ts) and the compare lines (app/assets.ts); the caller places it and closes it. */

export const HUES = ['#f23645', '#ff9800', '#ffeb3b', '#4caf50', '#089981', '#00bcd4', '#2962ff', '#673ab7', '#9c27b0', '#e91e63'];
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
  color: () => string; setColor: (c: string) => void;
  /** colours in use on the chart, shown beside the custom button (none: the row holds the button only) */
  used?: string[];
  opacity?: { get: () => number; set: (v: number) => void };          // 0-100
  width?: { get: () => number; set: (v: number) => void };            // 1-4 px
  lineStyle?: { get: () => LineStyleKey; set: (v: LineStyleKey) => void };
  /** called after every change; `done` true when the box should close (a colour picked in a box without line options) */
  onChange: (done: boolean) => void;
}

const norm = (c: string) => (c || '').toLowerCase();
function swatch(c: string, current: string, pick: (c: string) => void): HTMLButtonElement {
  const s = document.createElement('button'); s.type = 'button'; s.className = 'cpk-sw'; s.style.background = c;
  s.setAttribute('aria-label', c); s.setAttribute('aria-pressed', String(norm(current) === norm(c)));
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
  const box = document.createElement('div'); box.className = 'cpk'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', `${o.label} colour`);
  const lines = !!(o.opacity || o.width || o.lineStyle);
  const pick = (c: string) => { o.setColor(c); box.querySelectorAll('.cpk-sw').forEach(x => x.setAttribute('aria-pressed', String(norm(x.getAttribute('aria-label') || '') === norm(c)))); o.onChange(!lines) };
  const grid = document.createElement('div'); grid.className = 'cpk-grid';
  COLOR_GRID.forEach((row, r) => { row.forEach(c => grid.append(swatch(c, o.color(), pick))); if (r === 1) { const gap = document.createElement('span'); gap.className = 'cpk-gap'; grid.append(gap) } });
  box.append(grid);
  // the colours in use and a custom one: the browser's colour chooser, its value applied as it changes
  const used = document.createElement('div'); used.className = 'cpk-used';
  const inGrid = new Set(COLOR_GRID.flat().map(norm));
  [...new Set((o.used || []).map(norm))].filter(c => /^#[0-9a-f]{6}$/.test(c) && !inGrid.has(c)).slice(0, 9).forEach(c => used.append(swatch(c, o.color(), pick)));
  const add = document.createElement('label'); add.className = 'cpk-add'; add.title = 'Custom colour';
  const inp = document.createElement('input'); inp.type = 'color'; inp.value = /^#[0-9a-f]{6}$/i.test(o.color()) ? o.color() : '#2962ff'; inp.setAttribute('aria-label', 'Custom colour');
  inp.oninput = () => { o.setColor(inp.value); o.onChange(false) };
  inp.onchange = () => { o.setColor(inp.value); o.onChange(!lines) };
  add.append(inp, document.createTextNode('+'));
  used.append(add);
  box.append(used);
  if (lines) {
    const hr = document.createElement('hr'); hr.className = 'cpk-hr'; box.append(hr);
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
  return box;
}
