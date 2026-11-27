/* Touch areas (the user 2026-11-27, UD72 "3A": "invisible, no visual or layout change"; the design system's decision 14;
   check 2 MX2-4, MX2-5). On a touch screen every small control of the page takes a tap area up to 44 × 44 px around its
   middle, an invisible box (its ::after, or for a chart's dot a transparent circle), and nothing moves. Each side reaches
   at most the room before the nearest other tap target on that side: all of it when that neighbour keeps its own box (a
   table row, a heat cell, a chart's box), half of it when the neighbour has a tap area too, so no two areas overlap and no
   area covers another target. So where controls touch (the buttons of a segmented control, the rows of a list, the cells of
   a heatmap) a side gets nothing and the area stays the control's own size on that axis; the outer sides still reach out.
   The sides are written on the control as --hit-t / --hit-r / --hit-b / --hit-l (sector.css reads them under
   pointer: coarse, else --hit-y / --hit-x as the canonical layer). Run after a card or a window is drawn (app.ts, windows.ts). */
import { TOUCH } from './words.ts';

/** the page's own small controls (they take the class .hit on a touch screen); the shared ones are the canonical list */
export const OWN = ['.ovx-tog', '.ovx-hm .nm[data-n]', '.rsw .nm', '.pmg .nm', '.pmg .hd', '.tk', '.sxw', '.fw-sel', '.fw-q', '.bdq',
  '.menu-item', '#tabs [role=tab]', '#datebtn', '#termbtn', '.c1-chip', '.ihq', '.bxl', '.bms', '.dchip', '.pmbar .sw', '.clr', '.rsr', '.car', '.fwx', '.ovx-hm .hd', '.rsw .hd[data-k]'].join(',');
const SHARED = '.seg button,.tog,.iconbtn,.btn.sm,.btn.xs,button.pill';
/** what a finger can aim at: a control, a field, an element with a hint, a chart's box */
const TAPS = 'button,a[href],input,select,textarea,label,[role=button],[role=tab],[role=menuitemradio],[tabindex="0"],[data-tip],[data-chart],[data-map],[data-strip]';
/** a chart's dots that are controls: a transparent circle under the visible dot is their area */
const DOTS = 'g.pt,g.ovx-dot,g.dt';
/** what stays over the page while it scrolls (app.ts measures the cards again when the page stops scrolling) */
const PINNED = '.bar1';
const MAX = 22;

type Box = { l: number; t: number; r: number; b: number };
const box = (e: Element): Box => { const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom } };
const shown = (b: Box) => b.r - b.l > 0.5 && b.b - b.t > 0.5;

/** the four sides one control may reach: on each side the room before the nearest target within 44 px of its band (half
    of it when that target has an area too), inside what is pinned over the page (`pin`); then the 44 px of each axis are
    shared, half a side, and a side with less room leaves the rest of its half to the other (so a control at an edge of a
    row still reaches 44 px where the other side has the room) */
export function sides(me: Box, others: { b: Box; area: boolean }[], pin: Box | null = null): { t: number; r: number; b: number; l: number } {
  const w = me.r - me.l, h = me.b - me.t, s = { t: MAX, b: MAX, l: MAX, r: MAX };
  for (const o of others) {
    const k = o.area ? 0.5 : 1, b = o.b;
    const xBand = b.l < me.r + 44 && b.r > me.l - 44, yBand = b.t < me.b + 44 && b.b > me.t - 44;
    if (xBand && b.b <= me.t + 0.5) s.t = Math.min(s.t, Math.max(0, (me.t - b.b) * k));
    if (xBand && b.t >= me.b - 0.5) s.b = Math.min(s.b, Math.max(0, (b.t - me.b) * k));
    if (yBand && b.r <= me.l + 0.5) s.l = Math.min(s.l, Math.max(0, (me.l - b.r) * k));
    if (yBand && b.l >= me.r - 0.5) s.r = Math.min(s.r, Math.max(0, (b.l - me.r) * k));
    // a target that overlaps the control's own box (a sticky cell over a scrolled one) leaves it no room on that axis
    if (b.l < me.r - 0.5 && b.r > me.l + 0.5 && b.t < me.b - 0.5 && b.b > me.t + 0.5) { s.t = s.b = s.l = s.r = 0 }
  }
  if (pin) { s.t = Math.min(s.t, Math.max(0, me.t - pin.t)); s.b = Math.min(s.b, Math.max(0, pin.b - me.b)); s.l = Math.min(s.l, Math.max(0, me.l - pin.l)); s.r = Math.min(s.r, Math.max(0, pin.r - me.r)) }
  const share = (a: number, b: number, need: number): [number, number] => { const half = need / 2, x = Math.min(a, half), y = Math.min(b, half); return [Math.min(a, need - y), Math.min(b, need - x)] };
  [s.t, s.b] = share(s.t, s.b, Math.max(0, 44 - h)); [s.l, s.r] = share(s.l, s.r, Math.max(0, 44 - w));
  return s;
}

/** a dot's area: a circle as large as 44 px around its middle allows, up to half the distance to another dot and up to the
    edge of another target of the same chart (a trail point's hint), never under the dot itself */
export function dotRadius(p: { x: number; y: number; r: number }, dots: { x: number; y: number }[], plain: Box[]): number {
  let R = MAX;
  for (const q of dots) if (q !== p) R = Math.min(R, Math.hypot(p.x - q.x, p.y - q.y) / 2);
  for (const b of plain) R = Math.min(R, Math.hypot(Math.max(b.l, Math.min(p.x, b.r)) - p.x, Math.max(b.t, Math.min(p.y, b.b)) - p.y));
  return Math.max(p.r, R);
}

/** the box of the control itself or its nearest ancestor that is sticky or fixed in the page (not a window: a window's
    content does not scroll under its frame), or null */
export function pinned(e: Element): Box | null {
  for (let a: Element | null = e; a && a !== document.body; a = a.parentElement) {
    if (a.classList.contains('fw')) return null;
    if (/sticky|fixed/.test(getComputedStyle(a).position)) return box(a);
  }
  return null;
}
/** the box the control's area can show in: its pinned box, cut by every ancestor that clips its content (a scroller, a
    card): an area past it would never take a tap, so its side gives that share to the other side */
export function room(e: Element): Box | null {
  let k = pinned(e);
  for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
    const s = getComputedStyle(a); if ((s.overflowX === 'visible' && s.overflowY === 'visible') || s.display === 'contents') continue;
    const r = a.getBoundingClientRect(), c = { l: r.left + a.clientLeft, t: r.top + a.clientTop, r: r.left + a.clientLeft + a.clientWidth, b: r.top + a.clientTop + a.clientHeight };
    k = k ? { l: Math.max(k.l, c.l), t: Math.max(k.t, c.t), r: Math.min(k.r, c.r), b: Math.min(k.b, c.b) } : c;
  }
  return k;
}

const wired = new WeakSet<Element>(), scrolled = new WeakSet<Element>();
/** the tap areas of every small control in `parts` (a card, a window, the header with the tab bar), measured against the
    targets in the same parts; nothing on a mouse or pen */
export function fitTouch(...parts: (HTMLElement | null)[]) {
  const roots = parts.filter((p): p is HTMLElement => !!p && p.isConnected);
  if (!TOUCH || !roots.length) return;
  // measured again once a scroller inside stops: a sticky head or column moves over the rows that scroll under it
  for (const r of roots) if (!scrolled.has(r)) {
    scrolled.add(r); let t = 0;
    r.addEventListener('scroll', () => { clearTimeout(t); t = window.setTimeout(() => fitTouch(...parts), 120) }, { capture: true, passive: true });
  }
  const all = <T extends Element>(sel: string) => roots.flatMap(r => [...r.querySelectorAll<T>(sel)]);
  all(OWN).forEach(e => e.classList.add('hit'));
  const areas = all<HTMLElement>(`.hit,${SHARED}`).filter(e => shown(box(e)));
  // the page's pinned bars (the tab bar) count as a target for the cards that scroll under them (not in a window, which
  // lies over the page)
  const inWindow = roots.some(r => !!r.closest('.fw'));
  // (the tab bar measured with the header is a target for the header's buttons too: it stays over them as the page scrolls)
  const bars = inWindow ? [] : [...document.querySelectorAll(PINNED)].filter(o => !roots.some(r => o !== r && (o.contains(r) || r.contains(o))));
  const set = new Set<Element>(areas), taps = [...new Set([...all(TAPS), ...areas, ...bars])].map(e => ({ e, b: box(e) })).filter(x => shown(x.b));      // every area is a target too
  const fixed = areas.map(e => {
    const me = box(e);
    const others = taps.filter(x => x.e !== e && !x.e.contains(e) && !e.contains(x.e)).map(x => ({ b: x.b, area: set.has(x.e) }));
    // an area stays inside what is pinned over the page (the tab bar, a sticky name column: the page scrolls under it) and
    // inside what clips it (its scroller, its card)
    return [e, sides(me, others, room(e))] as const;
  });
  // the ::after sits on the padding box: a side reaches past the border by its width less the border's
  for (const [e, s] of fixed) {
    const cs = getComputedStyle(e), bw = { t: cs.borderTopWidth, r: cs.borderRightWidth, b: cs.borderBottomWidth, l: cs.borderLeftWidth } as Record<string, string>;
    for (const [k, v] of Object.entries(s)) e.style.setProperty('--hit-' + k, (v > 0 ? v + (parseFloat(bw[k]) || 0) : 0).toFixed(1) + 'px');
  }
  // a select inside an area opens from the area too (the area is the wrapper's, a select has no box of its own to grow)
  for (const e of areas) {
    const sel = e.querySelector('select');
    if (!sel || wired.has(e)) continue;
    wired.add(e);
    e.addEventListener('click', ev => {
      if ((ev.target as Element).closest('select')) return;
      try { (sel as HTMLSelectElement & { showPicker?: () => void }).showPicker?.() } catch { /* not allowed: the focus below */ }
      sel.focus();
    });
  }
  // the dots of each chart
  all<SVGSVGElement>('svg').forEach(svg => {
    const gs = [...svg.querySelectorAll<SVGGElement>(DOTS)];
    if (!gs.length) return;
    const pts = gs.map(g => {
      const v = g.querySelector('circle.v, circle.dot, circle:not(.hc):not(.hal)') as SVGCircleElement | null;
      if (!v) return null;
      const r = v.getBoundingClientRect();
      return { g, x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2, v };
    }).filter(Boolean) as { g: SVGGElement; x: number; y: number; r: number; v: SVGCircleElement }[];
    const plain = [...svg.querySelectorAll('[data-tip]')].filter(e => !e.closest(DOTS)).map(box).filter(shown);
    const k = svg.getBoundingClientRect(), sx = (svg.viewBox?.baseVal?.width || k.width) / (k.width || 1);
    for (const p of pts) {
      const R = dotRadius(p, pts, plain) * sx;
      let hc = p.g.querySelector(':scope > circle.hc') as SVGCircleElement | null;
      if (!hc) { hc = document.createElementNS('http://www.w3.org/2000/svg', 'circle'); hc.setAttribute('class', 'hc'); hc.setAttribute('fill', 'transparent'); p.g.prepend(hc) }
      hc.setAttribute('cx', p.v.getAttribute('cx') || '0'); hc.setAttribute('cy', p.v.getAttribute('cy') || '0'); hc.setAttribute('r', R.toFixed(1));
    }
  });
}
