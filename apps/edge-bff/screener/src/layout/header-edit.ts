/* EXEC-SCREENER-V21 layout: change a condition's parameters from its column header (reference layout.js 1102-1205).
   The header's parameter chip shows the values; hovering it shows them in a small card, a click (or Enter) opens an
   editor. Its fields carry the condition card's own attributes (data-c with data-p / data-p2 / data-k) and go through
   the builder's own handler (builder.ts onBuilderField): the same validation, markDirty and refresh as an edit on the
   card, so the change is a pending edit that waits for Screen now like any other. Nothing is computed here. */
import { esc } from '../format.ts';
import { ctx, entryOf, S } from '../state.ts';
import { optionText, rangeText, type Entry, type EntryParam } from '../entries.ts';
import { cardName, optOf, displayUnit, type Card } from '../forms.ts';
import { onBuilderField, colorOf, openCardToEdit } from '../builder.ts';
import { toast } from '../dialogs.ts';

let box: HTMLElement | null = null, id: string | null = null, tip: HTMLElement | null = null, tipT: ReturnType<typeof setTimeout> | undefined;
const cardOf = (cid: string | null) => S.cards.find(c => c.id === cid);
const chipOf = (cid: string | null) => cid ? document.querySelector(`#resPane [data-pedit="${CSS.escape(cid)}"]`) as HTMLElement | null : null;
const withinMax = () => ctx.catalog?.limits.find(l => l.name === 'within_max')?.value ?? 130;

interface PF { p: EntryParam; two: boolean; v: unknown; d: unknown; ch: boolean; err: string | undefined }
function fields(e: Entry, c: Card): PF[] {
  const o = optOf(e, c), two = o?.form === 'state_instance' || o?.form === 'event_instance', errs = S.errors[c.id] || {};
  const L = e.params.map(p => ({ p, two:false })); if (two) for (const p of e.params) L.push({ p, two:true });
  return L.map(x => {
    const v = x.two ? c.second[x.p.key] : c.params[x.p.key];
    const d = x.two ? ((o?.defaults as Record<string, unknown> | undefined)?.[x.p.key] ?? x.p.default) : x.p.default;
    return { ...x, v, d, ch:String(v) !== String(d), err:errs[(x.two ? '2.' : '') + x.p.key] };
  });
}
/** the rule and the numbers it needs, each with the catalog default of this indicator */
function rule(e: Entry, c: Card) {
  const o = optOf(e, c), u = displayUnit(o?.unit), errs = S.errors[c.id] || {};
  const L: { f: 'value' | 'value2' | 'within'; label: string; unit: string }[] = [];
  if (o?.value === 'input') { if (o.between) L.push({ f:'value', label:'From', unit:u }, { f:'value2', label:'To', unit:u }); else L.push({ f:'value', label:'Value', unit:u }) }
  if (o?.within) L.push({ f:'within', label:'Within', unit:'sessions' });
  const def = (f: string) => f === 'value2' ? (e.def.value2 === '' ? e.def.value : e.def.value2) : f === 'within' ? e.def.within : e.def.value;
  return { o, ruleChg:c.opt !== e.def.opt, thr:L.map(l => ({ ...l, v:c[l.f], d:def(l.f), ch:String(c[l.f]) !== String(def(l.f)), err:errs[l.f] })) };
}
const changed = (e: Entry, c: Card) => { const r = rule(e, c); return fields(e, c).some(x => x.ch) || r.ruleChg || r.thr.some(t => t.ch) };

function html(c: Card, e: Entry): string {
  const F = fields(e, c), R = rule(e, c), n = S.cards.indexOf(c) + 1, ch = changed(e, c), defO = e.opts.find(x => x.key === e.def.opt);
  const fld = (x: PF) => {
    const a = x.two ? 'data-p2' : 'data-p', q = x.p, lab = (x.two ? '2nd ' : '') + (q.label || q.key);
    const ctl = q.options ? `<select class="sel" data-c="${c.id}" ${a}="${esc(q.key)}">${q.options.map(v => `<option value="${esc(v)}"${String(v) === String(x.v) ? ' selected' : ''}>${esc(optionText(q, v))}</option>`).join('')}</select>`
      : q.type === 'boolean' ? `<select class="sel" data-c="${c.id}" ${a}="${esc(q.key)}"><option value="true"${x.v === true ? ' selected' : ''}>true</option><option value="false"${x.v === false ? ' selected' : ''}>false</option></select>`
      : `<input class="inp" type="number" ${q.min != null ? `min="${q.min}"` : ''} ${q.max != null ? `max="${q.max}"` : ''} step="${q.step ?? (q.integer ? 1 : 'any')}" data-c="${c.id}" ${a}="${esc(q.key)}" value="${esc(x.v)}" aria-invalid="${!!x.err}">`;
    return `<label class="pf6${x.ch ? ' chg' : ''}" data-pf6="${x.two ? '2.' : ''}${esc(q.key)}"><span>${esc(lab)}</span>${ctl}<small>default ${esc(optionText(q, x.d))}${rangeText(q) ? `<i class="rng"> · ${esc(rangeText(q))}</i>` : ''}</small><em class="pf6-err" role="alert"${x.err ? '' : ' hidden'}>${esc(x.err || '')}</em></label>`;
  };
  return `<div class="pe6-h"><i class="cdot" style="background:${colorOf(c)}"></i><b>${esc(cardName(e, c))}</b><span class="pe6-st">${ch ? '<span class="st6 on">Changed</span>' : '<span class="st6">Default</span>'}</span></div>
    <div class="pe6-sub">Condition ${n} in the Screen builder</div>
    <div class="pe6-sec">Parameters</div>
    <div class="pe6-g">${F.map(fld).join('')}</div>
    <div class="pe6-sec">Condition</div>
    <label class="pf6 w${R.ruleChg ? ' chg' : ''}" data-pf6="k.op"><span>Rule</span><select class="sel" data-c="${c.id}" data-k="op" aria-label="Condition">${e.opts.map(x => `<option value="${esc(x.key)}"${x.key === c.opt ? ' selected' : ''}${x.disabled ? ` disabled title="${esc(x.disabled)}"` : ''}>${esc(x.label)}${x.disabled ? ' — not offered' : ''}</option>`).join('')}</select><small>default ${esc(defO?.label || '')}</small></label>
    ${R.thr.length ? `<div class="pe6-g">${R.thr.map(t => `<label class="pf6${t.ch ? ' chg' : ''}" data-pf6="k.${t.f}"><span>${esc(t.label)}${t.unit ? ` (${esc(t.unit)})` : ''}</span><input class="inp" type="number" step="${t.f === 'within' ? 1 : 'any'}" ${t.f === 'within' ? `min="1" max="${withinMax()}"` : ''} data-c="${c.id}" data-k="${t.f}" value="${esc(t.v ?? '')}" aria-invalid="${!!t.err}"><small>default ${esc(t.d ?? '')}</small><em class="pf6-err" role="alert"${t.err ? '' : ' hidden'}>${esc(t.err || '')}</em></label>`).join('')}</div>` : `<div class="pe6-none">No threshold for this rule</div>`}
    <div class="pe6-f"><button type="button" class="link" data-pe6reset${ch ? '' : ' disabled'}>Reset to default</button><span class="sp"></span><button type="button" class="btn sm" data-pe6done>Done</button></div>
    <div class="pe6-note">Also changes the condition card in the Screen builder. Press Screen now to update the table.</div>`;
}
/** keep the editor under its chip (the table re-renders after every change) */
export function placeEditor() {
  if (!box) return;
  const ch = chipOf(id);
  if (!ch || !cardOf(id)) { closeEditor(false); return }
  ch.setAttribute('aria-expanded', 'true');
  const r = ch.getBoundingClientRect(); if (r.bottom < 0 || r.top > innerHeight) { closeEditor(false); return }
  const w = box.offsetWidth, h = box.offsetHeight; let x = Math.min(Math.max(8, r.right - w), innerWidth - w - 8), y = r.bottom + 6;
  if (y + h > innerHeight - 8 && r.top - h - 6 > 8) y = r.top - h - 6;
  box.style.left = x + 'px'; box.style.top = Math.max(8, y) + 'px';
}
/** after the builder handled a change: states and errors, without rebuilding the focused field */
function sync() {
  if (!box) return; const c = cardOf(id), e = c && entryOf(c); if (!c || !e) { closeEditor(false); return }
  for (const x of fields(e, c)) {
    const f = box.querySelector(`[data-pf6="${x.two ? '2.' : ''}${CSS.escape(x.p.key)}"]`); if (!f) continue;
    f.classList.toggle('chg', x.ch); f.querySelector('.inp')?.setAttribute('aria-invalid', String(!!x.err));
    const er = f.querySelector('.pf6-err') as HTMLElement; er.textContent = x.err || ''; er.hidden = !x.err;
  }
  const R = rule(e, c); box.querySelector('[data-pf6="k.op"]')?.classList.toggle('chg', R.ruleChg);
  for (const t of R.thr) { const f = box.querySelector(`[data-pf6="k.${t.f}"]`); if (!f) continue; f.classList.toggle('chg', t.ch); const er = f.querySelector('.pf6-err') as HTMLElement | null; if (er) { er.textContent = t.err || ''; er.hidden = !t.err } }
  const ch = changed(e, c);
  box.querySelector('.pe6-st')!.innerHTML = ch ? '<span class="st6 on">Changed</span>' : '<span class="st6">Default</span>';
  box.querySelector('[data-pe6reset]')!.toggleAttribute('disabled', !ch);
  placeEditor();
}
export function openEditor(cid: string) {
  const c = cardOf(cid), e = c && entryOf(c); if (!c || !e) return;
  hideTip();
  if (box && id === cid) { closeEditor(); return }
  closeEditor(false); id = cid;
  box = document.createElement('div'); box.className = 'pe6'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', `Change parameters: ${cardName(e, c)}`);
  box.innerHTML = html(c, e); document.body.appendChild(box); placeEditor();
  (box.querySelector('.inp,.sel') as HTMLElement | null)?.focus();
  box.addEventListener('keydown', trap);
}
export function closeEditor(restore = true) {
  if (!box) return; const cid = id; box.remove(); box = null; id = null;
  const ch = chipOf(cid); ch?.setAttribute('aria-expanded', 'false'); if (restore) ch?.focus();
}
/** Tab stays inside the editor; Escape closes it (focus back on the chip) */
function trap(e: KeyboardEvent) {
  if (!box) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeEditor(); return }
  if (e.key !== 'Tab') return;
  const list = [...box.querySelectorAll<HTMLElement>('input,select,button:not([disabled])')]; if (!list.length) return;
  const first = list[0], last = list[list.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}
const apply = (el: HTMLInputElement | HTMLSelectElement) => {
  onBuilderField(el);
  if (el.matches('[data-k="op"]')) { requestAnimationFrame(() => { const c = cardOf(id), e = c && entryOf(c); if (!box || !c || !e) return; box.innerHTML = html(c, e); placeEditor(); (box.querySelector('[data-k="op"]') as HTMLElement | null)?.focus() }); return }
  requestAnimationFrame(sync);
};
function reset() {
  const c = cardOf(id), e = c && entryOf(c); if (!box || !c || !e) return;
  // each changed field back to its default through the card's own handler, rule first (it decides the thresholds)
  if (c.opt !== e.def.opt) { const sel = box.querySelector('[data-k="op"]') as HTMLSelectElement | null; if (sel) { sel.value = e.def.opt; onBuilderField(sel); box.innerHTML = html(c, e) } }
  for (const t of rule(e, c).thr.filter(t => t.ch)) { const el = box.querySelector(`[data-k="${t.f}"]`) as HTMLInputElement | null; if (el) { el.value = String(t.d); onBuilderField(el) } }
  for (const x of fields(e, c).filter(x => x.ch)) { const el = box.querySelector(`[data-pf6="${x.two ? '2.' : ''}${CSS.escape(x.p.key)}"] :is(.inp,.sel)`) as HTMLInputElement | null; if (!el) continue; el.value = String(x.d); onBuilderField(el) }
  box.innerHTML = html(c, e); placeEditor(); toast('Parameters and condition back to default');
  (box.querySelector('.inp,.sel') as HTMLElement | null)?.focus();
}

/* ---- hover card: the column's parameters, read-only ------------------------------------------------------- */
function showTip(ch: HTMLElement) {
  const c = cardOf(ch.dataset.pedit!), e = c && entryOf(c); if (!c || !e || box) return;
  hideTip(); tip = document.createElement('div'); tip.className = 'pvtip6'; tip.setAttribute('role', 'tooltip');
  tip.innerHTML = `<div class="pvtip6-l">${fields(e, c).map(x => `<span>${esc((x.two ? '2nd ' : '') + (x.p.label || x.p.key))} <b class="${x.ch ? 'cus' : ''}">${esc(optionText(x.p, x.v))}</b></span>`).join('')}</div><div class="pvtip6-h"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Z"/></svg>Click to change</div>`;
  document.body.appendChild(tip);
  const r = ch.getBoundingClientRect(), w = tip.offsetWidth;
  tip.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8) + 'px'; tip.style.top = (r.bottom + 6) + 'px';
}
function hideTip() { clearTimeout(tipT); tip?.remove(); tip = null }

let debounce: ReturnType<typeof setTimeout> | undefined;
export function bindHeaderEdit() {
  const pane = document.getElementById('resPane')!;
  pane.addEventListener('click', e => { const ch = (e.target as HTMLElement).closest('[data-pedit]') as HTMLElement | null; if (ch) { e.preventDefault(); e.stopPropagation(); openEditor(ch.dataset.pedit!) } }, true);
  pane.addEventListener('click', e => { const ch = (e.target as HTMLElement).closest('[data-pcard]') as HTMLElement | null; if (ch) { e.preventDefault(); e.stopPropagation(); closeEditor(false); openCardToEdit(ch.dataset.pcard!) } }, true);
  pane.addEventListener('mouseover', e => { const ch = (e.target as HTMLElement).closest('[data-pedit]') as HTMLElement | null; if (!ch || ch.contains(e.relatedTarget as Node)) return; clearTimeout(tipT); tipT = setTimeout(() => showTip(ch), 250) });
  pane.addEventListener('mouseout', e => { const ch = (e.target as HTMLElement).closest('[data-pedit]') as HTMLElement | null; if (!ch || ch.contains(e.relatedTarget as Node)) return; hideTip() });
  document.addEventListener('change', e => { const t = e.target as HTMLInputElement; if (box?.contains(t) && t.matches('[data-c]')) { clearTimeout(debounce); apply(t) } });
  document.addEventListener('input', e => { const t = e.target as HTMLInputElement; if (box?.contains(t) && t.matches('input[data-c]')) { clearTimeout(debounce); debounce = setTimeout(() => apply(t), 350) } });
  document.addEventListener('click', e => {
    if (!box || !box.contains(e.target as Node)) return;
    const t = e.target as HTMLElement;
    if (t.closest('[data-pe6done]')) closeEditor();
    else if (t.closest('[data-pe6reset]')) reset();
  });
  document.addEventListener('pointerdown', e => { const t = e.target as HTMLElement; if (box && !box.contains(t) && !t.closest('#resPane [data-pedit]')) closeEditor(false) }, true);
  document.addEventListener('scroll', () => { placeEditor(); hideTip() }, true);
  addEventListener('resize', placeEditor);
}
