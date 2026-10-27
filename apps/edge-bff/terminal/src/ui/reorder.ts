/* EXEC-TERMINAL-PANELS A1 (user 2026-10-26: "klik kolom header untuk rearrange ... broker summary mau dipindah ke urutan
   nomor 2"): pressing a section's header and dragging moves the section (EXEC-TERMINAL-PANELS-2 D: no grip); a plain
   click on the header still folds it. Alt+↑/↓ on a header moves it by keyboard. The order is remembered per panel. */
import { $, store } from '../app/context';

const DRAG_PX = 5, HOLD_MS = 250;
const swallow = (e: Event) => { e.stopPropagation(); e.preventDefault() };
const PANELS: [scrollId: string, storeKey: string][] = [['leftScroll', 'ml.stats.order'], ['rightScroll', 'ml.broker.order']];

/** the sections in `saved` order first, then any section the saved list does not name, in page order */
export function orderedKeys(page: string[], saved: string[]): string[] {
  const known = saved.filter(k => page.includes(k));
  return [...known, ...page.filter(k => !known.includes(k))];
}

export function initReorder() {
  for (const [id, key] of PANELS) {
    const box = $(id) as HTMLElement | null;
    if (!box) continue;
    const sections = () => [...box.querySelectorAll(':scope > .st')] as HTMLElement[];
    const keys = () => sections().map(s => s.dataset.sec as string);
    const save = () => store.set(key, JSON.stringify(keys()));
    let saved: string[] = [];
    try { saved = JSON.parse(store.get(key) || '[]') || [] } catch { /* a broken entry is the page order */ }
    const bySec = new Map(sections().map(s => [s.dataset.sec as string, s]));
    orderedKeys(keys(), saved).forEach(k => box.appendChild(bySec.get(k)!));

    for (const sec of sections()) {
      const head = sec.querySelector('.st-head') as HTMLElement;
      head.setAttribute('aria-keyshortcuts', 'Alt+ArrowUp Alt+ArrowDown');
      head.title = 'Click to fold · press and drag to move';
      head.addEventListener('keydown', e => {
        if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
        e.preventDefault();
        const sib = (e.key === 'ArrowUp' ? sec.previousElementSibling : sec.nextElementSibling) as HTMLElement | null;
        if (!sib?.classList.contains('st')) return;
        e.key === 'ArrowUp' ? box.insertBefore(sec, sib) : box.insertBefore(sib, sec);
        head.focus(); save();
      });
      /* EXEC-TERMINAL-PANELS-2 D (user 2026-10-27: "kalau kita klik dan hold di column header saja maka bisa menaikan/
         menurunkan"): the whole header is the handle. A press that moves DRAG_PX moves the section (touch: after a
         HOLD_MS hold, so a swipe still scrolls the panel); a press that does not move stays a click and folds it. */
      head.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        const y0 = e.clientY, t0 = performance.now(), touch = e.pointerType === 'touch';
        let top0 = 0, moved = false, ty = 0;                           // ty: the section's current offset
        const move = (ev: PointerEvent) => {
          if (!moved) {
            if (Math.abs(ev.clientY - y0) < DRAG_PX || (touch && performance.now() - t0 < HOLD_MS)) return;
            moved = true; top0 = sec.getBoundingClientRect().top; sec.classList.add('st-drag'); document.body.classList.add('st-dragging');
          }
          ev.preventDefault();
          // the section goes before the first other section whose middle lies below the pointer
          const after = sections().find(s => { if (s === sec || s.hidden) return false; const r = s.getBoundingClientRect(); return ev.clientY < r.top + r.height / 2 }) ?? null;
          if (after !== sec.nextElementSibling && !(after === null && sec === box.lastElementChild)) box.insertBefore(sec, after);
          const natural = sec.getBoundingClientRect().top - ty;     // where the section sits without the offset
          ty = ev.clientY - y0 - (natural - top0);                   // it follows the pointer
          sec.style.transform = `translateY(${ty}px)`;
        };
        const up = () => {
          document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', up);
          if (!moved) return;                                          // a click: the header's own handler folds it
          sec.classList.remove('st-drag'); document.body.classList.remove('st-dragging'); sec.style.transform = '';
          save();
          // the click that ends a drag must not fold the section
          // (the browser sends that click in the same task as this pointerup; the listener is dropped right after, so a
          // drag released off the header, which sends no click, does not swallow the next real one)
          addEventListener('click', swallow, { capture:true, once:true });
          setTimeout(() => removeEventListener('click', swallow, true), 0);
        };
        // listened on the document: moving the section in the page would drop a pointer capture on the header
        document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.addEventListener('pointercancel', up);
      });
    }
  }
}
