/* Dropdown lists: one neutral component for every <select> (reference lines 3631-3683). */
export function initSelect() {
  const pop = document.createElement('div');
  pop.className = 'cs-pop'; pop.hidden = true; pop.setAttribute('role', 'listbox'); pop.tabIndex = -1; document.body.appendChild(pop);
  let cur = null, kb = -1;
  const items = () => [...pop.querySelectorAll('.cs-opt')];
  const mark = i => { kb = i; items().forEach((o, k) => o.classList.toggle('kb', k === i)); const o = items()[i]; if(o) o.scrollIntoView({ block:'nearest' }) };
  const close = refocus => { if(!cur) return; const s = cur; cur = null; s.classList.remove('cs-open'); pop.hidden = true; if(refocus) s.focus() };
  const choose = o => {
    if(!cur || o.getAttribute('aria-disabled') === 'true') return;
    const s = cur; s.value = o.dataset.v; close(true);
    s.dispatchEvent(new Event('input', { bubbles:true })); s.dispatchEvent(new Event('change', { bubbles:true }));
  };
  function open(sel) {
    if(cur) cur.classList.remove('cs-open');
    cur = sel; sel.classList.add('cs-open'); pop.innerHTML = '';
    [...sel.options].forEach(o => {
      const b = document.createElement('div');
      b.className = 'cs-opt'; b.setAttribute('role', 'option'); b.dataset.v = o.value; b.textContent = o.textContent;
      b.setAttribute('aria-selected', String(o.value === sel.value)); if(o.disabled) b.setAttribute('aria-disabled', 'true');
      pop.appendChild(b);
    });
    const r = sel.getBoundingClientRect();
    pop.hidden = false; pop.style.minWidth = r.width + 'px';
    const h = Math.min(pop.scrollHeight + 2, 280), below = innerHeight - r.bottom - 8;
    pop.style.top = (below >= h || below >= r.top - 8 ? r.bottom + 4 : Math.max(8, r.top - h - 4)) + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, innerWidth - pop.offsetWidth - 8)) + 'px';
    mark(Math.max(0, [...sel.options].findIndex(o => o.value === sel.value))); pop.focus({ preventScroll:true });
  }
  document.addEventListener('mousedown', (e: any) => {
    const sel = e.target.closest && e.target.closest('select');
    if(sel && !sel.disabled && !sel.multiple) { e.preventDefault(); cur === sel ? close(true) : open(sel) }
  }, true);
  document.addEventListener('keydown', (e: any) => {
    const t = e.target;
    if(t && t.tagName === 'SELECT' && !t.disabled && [' ', 'Enter', 'ArrowDown', 'ArrowUp'].includes(e.key)) { e.preventDefault(); open(t) }
  }, true);
  pop.addEventListener('click', (e: any) => { const o = e.target.closest('.cs-opt'); if(o) choose(o) });
  pop.addEventListener('mousemove', (e: any) => { const o = e.target.closest('.cs-opt'); if(o) mark(items().indexOf(o)) });
  pop.addEventListener('keydown', (e: any) => {
    const n = items().length;
    if(e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true) }
    else if(e.key === 'ArrowDown') { e.preventDefault(); mark((kb + 1) % n) }
    else if(e.key === 'ArrowUp') { e.preventDefault(); mark((kb + n - 1) % n) }
    else if(e.key === 'Home') { e.preventDefault(); mark(0) }
    else if(e.key === 'End') { e.preventDefault(); mark(n - 1) }
    else if(e.key === 'Enter' || e.key === ' ') { e.preventDefault(); const o = items()[kb]; if(o) choose(o) }
    else if(e.key === 'Tab') close(false);
  });
  document.addEventListener('pointerdown', (e: any) => { if(cur && !pop.contains(e.target) && e.target !== cur) close(false) });
  addEventListener('resize', () => close(false)); addEventListener('blur', () => close(false));
  document.addEventListener('scroll', (e: any) => { if(cur && !pop.contains(e.target)) close(false) }, true);
}
