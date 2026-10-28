/* Dialogs, menu and toast (the prototype's dialog / closeDialog / openMenu / toast), with the accessibility the port
   adds (report 9.2: aria-modal, a focus trap, focus back to the opener; the toast is aria-live polite), and the save
   dialogs over the server's saved items (P12 a; report 9.5): Save screen, Save as My metric, delete confirmation. */
import type { SavedItem, ScreenItemDefinition } from './core/contract.ts';
import { ApiFailure } from './api/types.ts';
import { esc } from './format.ts';
import { IC, ico } from './icons.ts';
import { ctx, definitionOf, entryOf, S, ui } from './state.ts';
import { condRule, paramSummary, toWire, type Card } from './forms.ts';
import { errorText } from './texts.ts';

const $ = (id: string) => document.getElementById(id)!;

let toastT: ReturnType<typeof setTimeout> | undefined;
export function toast(m: string) {
  const t = $('toast'); t.textContent = m; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true }, 2200);
}

let opener: HTMLElement | null = null;
const FOCUSABLE = 'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea,[tabindex]:not([tabindex="-1"])';
/** Open a dialog: `html` is one `.dialog` element (role=dialog); `bind` wires it. Escape and the backdrop close it. */
export function dialog(html: string, bind?: (root: HTMLElement) => void) {
  const prev = document.activeElement as HTMLElement | null;
  closeDialog(false);
  opener = prev;
  const o = $('overlay');
  o.innerHTML = `<div class="backdrop">${html}</div>`;
  o.hidden = false;
  const box = o.querySelector('.dialog') as HTMLElement | null;
  box?.setAttribute('aria-modal', 'true');
  o.querySelector('.backdrop')!.addEventListener('mousedown', e => { if ((e.target as HTMLElement).classList.contains('backdrop')) closeDialog() });
  o.querySelectorAll<HTMLElement>('[data-close]').forEach(b => { b.onclick = () => closeDialog(); if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', 'Close') });
  // focus trap: Tab and Shift+Tab stay inside the dialog
  o.addEventListener('keydown', trap);
  bind?.(o);
  if (box && !box.contains(document.activeElement)) (box.querySelector(FOCUSABLE) as HTMLElement | null)?.focus();
}
function trap(e: KeyboardEvent) {
  if (e.key !== 'Tab') return;
  const box = $('overlay').querySelector('.dialog'); if (!box) return;
  const list = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(x => x.offsetParent !== null);
  if (!list.length) return;
  const first = list[0], last = list[list.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}
export function closeDialog(restore = true) {
  const o = $('overlay');
  if (o.hidden && !o.innerHTML) return;
  o.hidden = true; o.innerHTML = '';
  o.removeEventListener('keydown', trap);
  if (restore && opener && document.contains(opener)) opener.focus({ preventScroll:true });
  if (restore) opener = null;
}
export const dialogOpen = () => !$('overlay').hidden;

/** A menu under `anchor`; null items are separators; an item with a reason is shown disabled with it as its title. */
export type MenuItem = [string, string, () => void, string?] | null;
export function openMenu(anchor: HTMLElement, items: MenuItem[]) {
  const m = $('menu'), r = anchor.getBoundingClientRect();
  m.innerHTML = items.map((it, i) => it ? `<button data-mi="${i}" role="menuitem" ${it[3] ? `disabled title="${esc(it[3])}"` : ''}>${ico(it[1], 's')}${esc(it[0])}</button>` : '<hr>').join('');
  m.setAttribute('role', 'menu');
  m.hidden = false;
  m.style.top = r.bottom + 6 + 'px';
  m.style.left = Math.max(8, Math.min(innerWidth - 240, r.right - 220)) + 'px';
  m.onclick = e => { const b = (e.target as HTMLElement).closest('[data-mi]') as HTMLElement | null; if (!b || (b as HTMLButtonElement).disabled) return; m.hidden = true; items[+b.dataset.mi!]![2]() };
  (m.querySelector('button:not([disabled])') as HTMLElement | null)?.focus({ preventScroll:true });
}

/** A confirmation (report 9.2: Delete asks, a server delete cannot be undone). */
export function confirmDialog(title: string, body: string, action: string, go: () => void | Promise<void>) {
  dialog(`<div class="dialog" role="dialog" aria-label="${esc(title)}"><div class="dialog-h"><div style="flex:1"><strong>${esc(title)}</strong><small>${esc(body)}</small></div><button class="iconbtn sm" data-close>${ico(IC.x)}</button></div>
    <div class="dialog-f"><button class="btn" data-close>Cancel</button><button class="btn dark" id="cfGo">${esc(action)}</button></div></div>`, () => {
    $('cfGo').onclick = async () => { closeDialog(); await go() };
  });
}

const newItemId = () => {
  const b = new Uint8Array(16); crypto.getRandomValues(b);
  return 'scr_' + [...b].map(x => x.toString(16).padStart(2, '0')).join('');
};
export { newItemId };
const failText = (e: unknown) => e instanceof ApiFailure ? e.message : errorText('SCREENER_UNAVAILABLE');

/** Save screen (prototype openSave over PUT items; report 9.5): same name replaces that saved screen (with its
    revision); a stale revision answers 409 and the dialog offers reload or save as a copy. */
export function openSave() {
  const saved = ctx.saved || [], src = S.source?.kind === 'saved' ? saved.find(s => s.item_id === (S.source as any).item_id) : null;
  const base = src ? src.name : S.source ? `${S.name} (my version)` : S.name === 'Untitled screen' ? '' : S.name;
  dialog(`<div class="dialog" role="dialog" aria-label="Save screen"><div class="dialog-h"><div style="flex:1"><strong>Save screen</strong><small>Universe, conditions, parameters, match logic, sort and near-miss view — saved to your EDGE account.</small></div><button class="iconbtn sm" data-close>${ico(IC.x)}</button></div>
    <form class="dialog-b" id="saveForm"><label class="fld"><span>Name</span><input class="inp" id="saveName" value="${esc(base)}" maxlength="120" placeholder="LQ45 oversold with accumulation"></label><div class="note" id="saveNote" aria-live="polite"></div></form>
    <div class="dialog-f" id="saveFoot"><button class="btn" data-close>Cancel</button><button class="btn dark" id="saveGo">${ico(IC.save, 's')}Save</button></div></div>`, () => {
    const inp = $('saveName') as HTMLInputElement, note = $('saveNote'), goBtn = $('saveGo') as HTMLButtonElement;
    inp.focus(); inp.select();
    const chk = () => { const v = inp.value.trim(); note.textContent = saved.some(s => s.name === v) ? 'A screen with this name exists — saving replaces it.' : ''; goBtn.disabled = !v };
    inp.oninput = chk; chk();
    const put = async (id: string, name: string, revision?: number) => {
      const definition: ScreenItemDefinition = { definition:definitionOf(), view:{ sort:{ key:S.sort.key, dir:S.sort.dir }, show_near:S.nearMiss } };
      return ctx.api.putItem(id, { kind:'screen', name, definition, ...(revision != null ? { revision } : {}) });
    };
    const done = (it: SavedItem) => {
      ctx.saved = [...(ctx.saved || []).filter(s => s.item_id !== it.item_id), it];
      S.name = it.name; S.source = { kind:'saved', item_id:it.item_id, revision:it.revision }; S.dirty = false; S.pcat = 'My screens';
      closeDialog(); ui.renderPresets(); ui.renderHeader(); toast(`${it.name} saved to My screens`);
    };
    const go = async (e?: Event) => {
      e?.preventDefault();
      const v = inp.value.trim(); if (!v) return;
      const same = saved.find(s => s.name === v);
      goBtn.disabled = true;
      try { done(await put(same ? same.item_id : newItemId(), v, same?.revision)) }
      catch (err) {
        goBtn.disabled = false;
        if (err instanceof ApiFailure && err.code === 'REVISION_CONFLICT') {
          note.textContent = err.message;
          $('saveFoot').innerHTML = `<button class="btn" data-close>Cancel</button><button class="btn" id="saveReload">${ico(IC.reset, 's')}Reload saved version</button><button class="btn dark" id="saveCopy">${ico(IC.dup, 's')}Save as a copy</button>`;
          $('saveFoot').querySelector('[data-close]')!.addEventListener('click', () => closeDialog());
          $('saveReload').onclick = async () => { closeDialog(); await reloadSaved(); const it = (ctx.saved || []).find(s => s.name === v); if (it) ui.openSource('s:' + it.item_id) };
          $('saveCopy').onclick = async () => { try { done(await put(newItemId(), uniqueName(v + ' (copy)'))) } catch (e2) { note.textContent = failText(e2) } };
          return;
        }
        note.textContent = failText(err);
      }
    };
    ($('saveForm') as HTMLFormElement).onsubmit = go; goBtn.onclick = go;
  });
}
const uniqueName = (n: string) => { const all = new Set((ctx.saved || []).map(s => s.name)); let x = n; while (all.has(x)) x += '′'; return x };
export async function reloadSaved() {
  try { ctx.saved = (await ctx.api.items('screen')).items } catch (e) { toast(failText(e)) }
  ui.renderPresets();
}

/** Save as My metric (prototype openSaveMetric over PUT items kind 'metric'): a named test of one card; the same name
    (any case) replaces that metric; linked cards follow the new name. */
export function openSaveMetric(c: Card) {
  const e = entryOf(c); if (!e) return;
  const all = ctx.metrics || [], base = c.metric?.name || `${e.label} ${e.params.filter(p => p.type !== 'enum' && p.type !== 'boolean').map(p => c.params[p.key]).join('/')}`.trim();
  dialog(`<div class="dialog" role="dialog" aria-label="Save as My metric"><div class="dialog-h"><div style="flex:1"><strong>Save as My metric</strong><small>A named ${esc(e.label)} with these parameters. It appears under “My metrics” in the Add box, saved to your EDGE account.</small></div><button class="iconbtn sm" data-close>${ico(IC.x)}</button></div>
    <form class="dialog-b" id="mForm"><label class="fld"><span>Name</span><input class="inp" id="mName" value="${esc(base)}" maxlength="40" placeholder="Slow stochastic 50"></label>
      <div class="note"><b>Parameters:</b> ${esc(paramSummary(e, c.params))}<br><b>Starting condition:</b> ${esc(condRule(e, c) || '—')}</div><div class="note" id="mNote" aria-live="polite"></div></form>
    <div class="dialog-f"><button class="btn" data-close>Cancel</button><button class="btn dark" id="mGo">${ico(IC.star, 's')}Save metric</button></div></div>`, () => {
    const inp = $('mName') as HTMLInputElement, note = $('mNote'), goBtn = $('mGo') as HTMLButtonElement;
    inp.focus(); inp.select();
    const chk = () => { const v = inp.value.trim(); note.textContent = all.some(m => m.name.toLowerCase() === v.toLowerCase()) ? 'A metric with this name exists — saving replaces it.' : ''; goBtn.disabled = !v };
    inp.oninput = chk; chk();
    const go = async (ev?: Event) => {
      ev?.preventDefault();
      const v = inp.value.trim(); if (!v) return;
      const old = all.find(m => m.name.toLowerCase() === v.toLowerCase());
      goBtn.disabled = true;
      try {
        const it = await ctx.api.putItem(old?.item_id || newItemId(), { kind:'metric', name:v, definition:{ test:toWire(e, c).test }, ...(old ? { revision:old.revision } : {}) });
        ctx.metrics = [...(ctx.metrics || []).filter(m => m.item_id !== it.item_id), it];
        for (const x of S.cards) if (x.metric?.item_id === it.item_id && x !== c) {
          if (JSON.stringify(x.params) === JSON.stringify(c.params)) x.metric = { item_id:it.item_id, name:v, params:{ ...c.params } }; else delete x.metric;
        }
        c.metric = { item_id:it.item_id, name:v, params:{ ...c.params } };
        ui.markDirty(); closeDialog(); ui.refresh('conds'); toast(`${v} saved to My metrics`);
      } catch (err) { goBtn.disabled = false; note.textContent = failText(err) }
    };
    ($('mForm') as HTMLFormElement).onsubmit = go; goBtn.onclick = go;
  });
}
