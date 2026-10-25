/* SYMBOL SEARCH — Ctrl/Cmd+K, the search bar or the symbol pill (reference lines 3557-3629).
   Choosing a ticker stores it and reloads, as in the reference; the list is the instrument master (live: the
   published ticker reference with its sector). */
import type { Ctx } from './context';
import { $, store } from './context';

export function initSearch(ctx: Ctx) {
  const { SYMBOL, INSTRUMENTS } = ctx;
  $('symText').textContent = SYMBOL;
  document.title = `${SYMBOL} · Market Lab`;
  const ICON = '<svg viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2L17 17"/></svg>';
  let layer = null, opener = null;
  function openSearch(from?, seed?) {
    if(layer) return;
    opener = from || document.activeElement;
    let query = seed || '', grouped = false, active = 0;
    layer = document.createElement('div'); layer.className = 'gp-backdrop';
    layer.innerHTML = `<div class="gp-dialog" role="dialog" aria-modal="true" aria-label="Search markets">
        <div class="gp-searchbar">${ICON}<input type="text" placeholder="Search ticker or company name" role="combobox" aria-expanded="true" aria-controls="gp-results" autocomplete="off" spellcheck="false">
          <div class="gp-shortcuts"><kbd>Ctrl K</kbd><span>/</span><kbd>⌘ K</kbd></div></div>
        <div class="gp-section-head"><span class="gp-label"></span>
          <button type="button" class="gp-toggle" aria-pressed="false"><span>Group by sector</span><span class="gp-track" aria-hidden="true"><span class="gp-knob"></span></span></button></div>
        <div class="gp-results" id="gp-results" role="listbox"></div>
        <div class="gp-foot"><span>↑↓ Navigate · Enter Select · Esc Close</span><span>Search by ticker, company or sector</span></div></div>`;
    document.body.appendChild(layer);
    const input = layer.querySelector('input'), results = layer.querySelector('.gp-results'), toggle = layer.querySelector('.gp-toggle');
    const esc = t => t.replace(/[&<>]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;' }[c]));
    const matches = () => { const n = query.trim().toLowerCase(); return INSTRUMENTS.filter(r => `${r[0]} ${r[1]} ${r[2]}`.toLowerCase().includes(n)) };
    let shown = [];
    function render() {
      const found = matches();
      const groups = grouped ? [...found.reduce((m, r) => m.set(r[2], [...(m.get(r[2]) || []), r]), new Map())] : [];
      shown = grouped ? groups.flatMap(g => g[1]) : found;
      active = Math.min(active, Math.max(shown.length - 1, 0));
      const row = r => { const i = shown.indexOf(r);
        return `<button type="button" class="gp-row${i === active ? ' is-active' : ''}" role="option" aria-selected="${i === active}" data-i="${i}">
            <span class="gp-avatar">${r[0].slice(0, 2)}</span>
            <span class="gp-meta"><span class="gp-ticker">${r[0]}${r[0] === SYMBOL ? '<span class="gp-cur">Current</span>' : ''}</span><span class="gp-company">${esc(r[1])}</span></span>
            <span class="gp-rightmeta">${grouped ? '' : `<span class="gp-sector">${esc(r[2])}</span>`}<span class="gp-market">IDX · Equity</span></span></button>` };
      results.innerHTML = !shown.length ? '<p class="gp-empty">No instruments found</p>'
        : grouped ? groups.map(([sec, rows]) => `<div class="gp-group">${esc(sec)}</div>` + rows.map(row).join('')).join('') : found.map(row).join('');
      layer.querySelector('.gp-label').textContent = query ? 'Results' : 'Available instruments';
      toggle.classList.toggle('active', grouped); toggle.setAttribute('aria-pressed', String(grouped));
      const cur = results.querySelector('.is-active'); if(cur) cur.scrollIntoView({ block:'nearest' });
    }
    const choose = r => { close(); if(r && r[0] !== SYMBOL){ store.set('ml.symbol', r[0]); location.reload() } };
    function close() { if(!layer) return; layer.remove(); layer = null; document.removeEventListener('keydown', onKey, true); if(opener && opener.focus) opener.focus() }
    const onKey = (e: any) => { if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); close() } else if(e.key === 'Tab'){ e.preventDefault(); input.focus() } };
    document.addEventListener('keydown', onKey, true);
    input.addEventListener('input', () => { query = input.value; active = 0; render() });
    input.addEventListener('keydown', (e: any) => {
      if((e.key === 'ArrowDown' || e.key === 'ArrowUp') && shown.length){ e.preventDefault(); active = (active + (e.key === 'ArrowDown' ? 1 : -1) + shown.length) % shown.length; render() }
      else if(e.key === 'Enter' && shown[active]){ e.preventDefault(); choose(shown[active]) }
    });
    results.addEventListener('mousemove', (e: any) => { const b = e.target.closest('.gp-row'); if(b && +b.dataset.i !== active){ active = +b.dataset.i; results.querySelectorAll('.gp-row').forEach(x => { const on = +x.dataset.i === active; x.classList.toggle('is-active', on); x.setAttribute('aria-selected', String(on)) }) } });
    results.addEventListener('click', (e: any) => { const b = e.target.closest('.gp-row'); if(b) choose(shown[+b.dataset.i]) });
    toggle.addEventListener('mousedown', (e: any) => e.preventDefault());
    toggle.addEventListener('click', () => { grouped = !grouped; active = 0; render(); input.focus() });
    layer.addEventListener('mousedown', (e: any) => { if(e.target === layer) close() });
    input.value = query; render(); input.focus(); input.setSelectionRange(query.length, query.length);
  }
  $('symSearch').addEventListener('click', (e: any) => openSearch(e.currentTarget));
  const pill = $('symbolPill');
  pill.addEventListener('click', () => openSearch(pill));
  pill.addEventListener('keydown', (e: any) => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); openSearch(pill) } });
  document.addEventListener('keydown', (e: any) => { if((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k'){ e.preventDefault(); openSearch() } });
  /* typing anywhere (no field focused) opens the search with that first character */
  document.addEventListener('keydown', (e: any) => {
    if(layer || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || !/^[a-z0-9]$/i.test(e.key)) return;
    const t = e.target;
    if(/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable || t.closest('[role=dialog],.cs-pop,.fl-pop,.dr-menu')) return;
    if(document.querySelector('.idlg-back:not([hidden])')) return;     // settings dialog open
    e.preventDefault(); openSearch(null, e.key);
  });
}
