/* EXEC-TERMINAL-PANELS A1 (user 2026-10-26: "klik kolom header untuk rearrange ... broker summary mau dipindah ke urutan
   nomor 2"): each section of a side panel gets a grip (⋮⋮) in its header. Dragging the grip moves the section; a plain
   click on the header still folds it. Alt+↑/↓ on a header moves it by keyboard. The order is remembered per panel. */
import { $, store } from '../app/context';

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
      const grip = document.createElement('span');
      grip.className = 'st-grip'; grip.title = 'Drag to move'; grip.setAttribute('aria-hidden', 'true');
      head.prepend(grip);
      head.setAttribute('aria-keyshortcuts', 'Alt+ArrowUp Alt+ArrowDown');
      head.addEventListener('keydown', e => {
        if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
        e.preventDefault();
        const sib = (e.key === 'ArrowUp' ? sec.previousElementSibling : sec.nextElementSibling) as HTMLElement | null;
        if (!sib?.classList.contains('st')) return;
        e.key === 'ArrowUp' ? box.insertBefore(sec, sib) : box.insertBefore(sib, sec);
        head.focus(); save();
      });
      grip.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        e.preventDefault(); e.stopPropagation();
        const y0 = e.clientY, top0 = sec.getBoundingClientRect().top;
        let moved = false, ty = 0;                                     // ty: the section's current offset
        sec.classList.add('st-drag');
        const move = (ev: PointerEvent) => {
          if (!moved && Math.abs(ev.clientY - y0) < 4) return;
          moved = true;
          // the section goes before the first other section whose middle lies below the pointer
          const after = sections().find(s => { if (s === sec || s.hidden) return false; const r = s.getBoundingClientRect(); return ev.clientY < r.top + r.height / 2 }) ?? null;
          if (after !== sec.nextElementSibling && !(after === null && sec === box.lastElementChild)) box.insertBefore(sec, after);
          const natural = sec.getBoundingClientRect().top - ty;     // where the section sits without the offset
          ty = ev.clientY - y0 - (natural - top0);                   // it follows the pointer
          sec.style.transform = `translateY(${ty}px)`;
        };
        const up = () => {
          document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', up);
          sec.classList.remove('st-drag'); sec.style.transform = '';
          if (moved) save();
        };
        // listened on the document: moving the section in the page would drop a pointer capture on the grip
        document.addEventListener('pointermove', move); document.addEventListener('pointerup', up); document.addEventListener('pointercancel', up);
      });
      // a drag ends on the header: its click must not fold the section
      grip.addEventListener('click', e => e.stopPropagation());
    }
  }
}
