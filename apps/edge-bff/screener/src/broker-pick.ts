/* EXEC-SCREENER-BROKER-PICK (user 2026-11-08: "drop-down brokers harus ada opsi selected all dan clear. User bisa pilih
   multiple brokers"): a flow indicator's broker list chosen from the brokers the publisher writes for the Terminal
   (ref/brokers, IDX_Broker_Profile: code, name, domicile), not typed. The screener-worker reads that file and puts the
   list in the catalog (data.brokers), so the page reads it on its own origin (its CSP allows no bucket). The field keeps a hidden input with the caller's
   own attributes (data-ai / data-ap, data-c / data-p), so each caller's change handler reads it with paramFieldValue as
   before; the list opens over the page, searchable, with Select all and Clear. Derived from the published list: a new
   broker needs no change here. */
import { LIST_SEP, listOf, type EntryParam } from './entries.ts';
import { esc } from './format.ts';
import { ctx } from './state.ts';
import type { ParamValue } from './core/contract.ts';
import type { BrokerRef } from './core/contract.ts';

let list: BrokerRef[] | null = null, from: unknown = null;
/** the catalog's broker list (null before the catalog has come; [] when the publication has none) */
function load(): Promise<void> {
  const cat = ctx.catalog;
  if (cat && cat !== from) { from = cat; list = [...(cat.data?.brokers || [])].filter(b => b.code).sort((a, b) => a.code.localeCompare(b.code)) }
  return Promise.resolve();
}
const nameOf = (code: string) => list?.find(b => b.code === code)?.name || '';

/** the field: a button that shows the chosen codes, and the hidden input the caller's handler reads */
export function brokerPickHtml(p: EntryParam, v: ParamValue | undefined, attrs: string, label: string, title: string, invalid = false): string {
  void load();
  const codes = listOf(v), max = p.count?.max ?? null;
  const shown = shownText(codes);
  return `<span class="bpk" data-bpk="${esc(attrs)}"${max != null ? ` data-max="${max}"` : ''}><input type="hidden" value="${esc(codes.join(','))}" ${attrs}>`
    + `<button type="button" class="sel bpk-btn${codes.length ? '' : ' ph'}" data-bpkopen aria-haspopup="listbox" aria-expanded="false" aria-label="${esc(label)}: ${esc(codes.length ? codes.join(', ') : 'none chosen')}"${invalid ? ' aria-invalid="true"' : ''} title="${esc([title, codes.map(c => `${c} ${nameOf(c)}`.trim()).join('\n')].filter(Boolean).join('\n'))}">${esc(shown)}</button></span>`;
}

/* ---- the open list ------------------------------------------------------------------------------------------ */
let pop: HTMLElement | null = null, key = '', scope = '', chosen = new Set<string>(), q = '', maxN: number | null = null, opener: HTMLElement | null = null;
const SCOPES = ['.pe6', '.qwin', '#condList'];
/** the field again after its owner redrew (a row, a card, the header box): the same attributes in the same place */
function field(): HTMLElement | null {
  const root = scope ? document.querySelector(scope) : document;
  return root?.querySelector<HTMLElement>(`[data-bpk="${CSS.escape(key)}"]`) ?? null;
}
function shownList(): BrokerRef[] {
  const s = q.trim().toLowerCase();
  return (list || []).filter(b => !s || b.code.toLowerCase().includes(s) || (b.name || '').toLowerCase().includes(s));
}
function draw() {
  if (!pop) return;
  const L = shownList(), full = maxN != null && chosen.size >= maxN;
  const body = list == null ? '<div class="bpk-none">Loading brokers…</div>'
    : !list.length ? `<div class="bpk-none">The broker list is not published yet: the screen still runs on the Terminal's default brokers.</div>`
    : !L.length ? `<div class="bpk-none">No broker matches “${esc(q)}”</div>`
    : L.map(b => { const on = chosen.has(b.code), off = !on && full;
      return `<label class="bpk-o${off ? ' off' : ''}"><input type="checkbox" data-bpkc="${esc(b.code)}"${on ? ' checked' : ''}${off ? ' disabled' : ''}><b>${esc(b.code)}</b><span>${esc(b.name || '')}</span>${b.type ? `<i>${esc(b.type)}</i>` : ''}</label>` }).join('');
  pop.querySelector('.bpk-l')!.innerHTML = body;
  pop.querySelector('.bpk-n')!.textContent = `${chosen.size} selected${maxN != null ? ` · at most ${maxN}` : ''}`;
}
function commit() {
  const f = field(), inp = f?.querySelector<HTMLInputElement>('input[type="hidden"]');
  if (!inp) return;
  // in the published list's order (by code), as a list param keeps its order stable
  inp.value = [...chosen].sort().join(',');
  inp.dispatchEvent(new Event('change', { bubbles:true }));
  // an owner that keeps its field (the header box updates in place) shows the choice too
  const btn = field()?.querySelector<HTMLElement>('[data-bpkopen]'), codes = [...chosen].sort();
  if (btn) { btn.textContent = shownText(codes); btn.classList.toggle('ph', !codes.length) }
}
const shownText = (codes: string[]) => codes.length ? (codes.length <= 3 ? codes.join(', ') : `${codes.slice(0, 3).join(', ')} +${codes.length - 3}`) : 'Choose brokers';
function place() {
  if (!pop) return;
  const btn = field()?.querySelector<HTMLElement>('[data-bpkopen]'); if (!btn) { close(false); return }
  const r = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
  const x = Math.min(Math.max(8, r.left), innerWidth - w - 8);
  let y = r.bottom + 4; if (y + h > innerHeight - 8 && r.top - h - 4 > 8) y = r.top - h - 4;
  pop.style.left = x + 'px'; pop.style.top = Math.max(8, y) + 'px';
}
function open(btn: HTMLElement) {
  const f = btn.closest<HTMLElement>('[data-bpk]'); if (!f) return;
  close(false);
  key = f.dataset.bpk || ''; scope = SCOPES.find(s => f.closest(s)) || ''; opener = btn;
  maxN = f.dataset.max != null ? Number(f.dataset.max) : null;
  chosen = new Set(listOf(f.querySelector<HTMLInputElement>('input[type="hidden"]')?.value.split(',').join(LIST_SEP) || ''));
  q = '';
  pop = document.createElement('div'); pop.className = 'bpk-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', 'Choose brokers');
  pop.innerHTML = `<label class="searchbox bpk-q"><input type="text" placeholder="Search code or name" autocomplete="off" spellcheck="false" aria-label="Search brokers"></label>
    <div class="bpk-a"><button type="button" class="link" data-bpkall>Select all</button><button type="button" class="link" data-bpkclear>Clear</button><span class="bpk-n"></span></div>
    <div class="bpk-l" role="listbox" aria-multiselectable="true"></div>
    <div class="bpk-f"><button type="button" class="btn sm" data-bpkdone>Done</button></div>`;
  document.body.appendChild(pop);
  btn.setAttribute('aria-expanded', 'true');
  draw(); place();
  const qi = pop.querySelector<HTMLInputElement>('.bpk-q input')!;
  qi.addEventListener('input', () => { q = qi.value; draw() });
  qi.focus();
}
function close(back = true) {
  if (!pop) return;
  pop.remove(); pop = null;
  const btn = field()?.querySelector<HTMLElement>('[data-bpkopen]'); btn?.setAttribute('aria-expanded', 'false');
  if (back) (btn || opener)?.focus({ preventScroll:true });
}
export const brokerPickOpen = () => !!pop;

let bound = false;
/** one set of page listeners (the fields are redrawn often; their list is one, over the page) */
export function bindBrokerPick() {
  if (bound) return; bound = true;
  // capture: the row under the button is never added, the card never toggled, by a click meant for the list
  document.addEventListener('click', e => {
    const t = e.target as HTMLElement;
    const b = t.closest<HTMLElement>('[data-bpkopen]');
    if (b) { e.preventDefault(); e.stopPropagation(); pop && field()?.contains(b) ? close() : open(b); return }
    if (!pop || !pop.contains(t)) return;
    if (t.closest('[data-bpkall]')) { for (const x of shownList()) { if (maxN != null && chosen.size >= maxN) break; chosen.add(x.code) } draw(); commit(); return }
    if (t.closest('[data-bpkclear]')) { chosen.clear(); draw(); commit(); return }
    if (t.closest('[data-bpkdone]')) { close(); return }
  }, true);
  document.addEventListener('change', e => {
    const t = e.target as HTMLInputElement;
    if (!pop || !pop.contains(t) || !t.dataset.bpkc) return;
    e.stopPropagation();
    t.checked ? chosen.add(t.dataset.bpkc) : chosen.delete(t.dataset.bpkc);
    draw(); commit();
  }, true);
  // a press outside the list closes it (the choices are already applied); inside it, nothing behind it hears it
  document.addEventListener('pointerdown', e => {
    if (!pop) return;
    const t = e.target as HTMLElement;
    if (pop.contains(t)) { e.stopPropagation(); return }
    if (!t.closest('[data-bpkopen]')) close(false);
  }, true);
  document.addEventListener('mousedown', e => { if (pop?.contains(e.target as Node)) e.stopPropagation() }, true);
  document.addEventListener('keydown', e => { if (pop && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close() } }, true);
  addEventListener('resize', () => place());
  document.addEventListener('scroll', e => { if (pop && !pop.contains(e.target as Node)) place() }, true);
}
