/* The indicator browser dialog (the prototype's openBrowser / drawBrowser): groups with counts, a list (listbox) and
   the details of the highlighted entry, with real ranges (min / max, the derived caps), typed booleans, the history
   class ("level depends on history start" for cumulative indicators) and, for an entry without data, its reason
   (report 9.2). Keys: arrows move, Enter adds.
   EXEC-SCREENER-V21 (three-panel v21, reference layout.js 327-485, 765-795): the dialog is the "Indicators" window
   (movable, resizable, maximise; layout/window.ts); the list is one scroll of every group and the group list follows
   it (a group click scrolls to it); the detail pane shows section 1 "Parameters" with Default (every parameter, its
   allowed range and value) or Custom (editable fields, checked against the catalog's ranges as the card does); the
   card that is added carries the custom values. Nothing is computed here: the values go into the card and the
   worker evaluates it after Screen now. */
import type { ParamMap, ParamValue, SavedItem } from './core/contract.ts';
import { esc } from './format.ts';
import { IC, ico } from './icons.ts';
import { ctx } from './state.ts';
import { byGroup, GHEAD, GL, GORD, isDefP, matches, optionText, paramError, rangeText, type Entry, type EntryParam } from './entries.ts';
import { condText, defaultOffered, fromWire, newCard } from './forms.ts';
import { T } from './texts.ts';
import { closeDialog, dialog } from './dialogs.ts';
import { makeWindow } from './layout/window.ts';

type Item = [key: string, e: Entry, m?: SavedItem];
const B = { q:'', g:'All', sel:null as string | null };
const $ = (id: string) => document.getElementById(id)!;
/** Default / Custom per indicator while the window is open: custom values as typed (numbers parsed), errors per key */
const CUS = new Map<string, { on: boolean; vals: ParamMap; errs: Record<string, string> }>();

function items(): Item[] {
  const mine: Item[] = [];
  for (const m of ctx.metrics || []) {
    const c = fromWire({ id:'m', enabled:true, test:(m.definition as any).test }, ctx.byKey);
    const e = c.entry ? ctx.byKey.get(c.entry) : undefined;
    if (e) mine.push(['m:' + m.item_id, e, m]);
  }
  return [...mine, ...byGroup(ctx.entries).map(e => [e.key, e] as Item)];
}
const group = ([, e, m]: Item) => m ? 'My metrics' : e.group;
const hit = ([, e, m]: Item, q: string) => !q || (m && m.name.toLowerCase().includes(q)) || matches(e, q);
const visible = () => { const q = B.q.trim().toLowerCase(); return items().filter(x => hit(x, q) && (B.g === 'All' || group(x) === B.g)) };

/** the custom values to add with, or null for the defaults; false when a field is invalid */
function customOf(k: string, e: Entry): ParamMap | null | false {
  const st = CUS.get(k); if (!st?.on || !e.params.length) return null;
  if (Object.keys(st.errs).length) return false;
  const p = { ...Object.fromEntries(e.params.map(x => [x.key, x.default])), ...st.vals } as ParamMap;
  return e.params.some(x => !isDefP(x, p[x.key])) ? p : null;
}

export function openBrowser(q: string, act: { addCond(k: string, params?: ParamMap): void; addMetric(id: string): void }) {
  B.q = q || ''; B.g = 'All'; B.sel = null; CUS.clear();
  const add = (k: string) => {
    if (k.startsWith('m:')) { closeDialog(); act.addMetric(k.slice(2)); return }
    const e = ctx.byKey.get(k); if (!e) return;
    const p = customOf(k, e);
    if (p === false) { ($('bDet').querySelector('[aria-invalid="true"]') as HTMLElement | null)?.focus(); return }
    closeDialog(); p ? act.addCond(k, p) : act.addCond(k);
  };
  dialog(`<div class="dialog xl ib" role="dialog" aria-label="Indicators"><div class="dialog-h"><div style="flex:1"><strong>Indicators</strong><small>Pick an indicator, check its settings, then add it. Parameters can still be changed on the card.</small></div><button class="iconbtn sm" data-close aria-label="Close">${ico(IC.x)}</button></div>
    <div class="ib-top"><label class="searchbox">${ico(IC.search, 's')}<input id="bq" value="${esc(B.q)}" placeholder="Search by name, short name or what it measures" autocomplete="off" aria-label="Search indicators"></label></div>
    <div class="ib-body"><nav class="ib-nav" id="bNav" aria-label="Groups"></nav><div class="ib-list" id="bList" role="listbox" aria-label="Indicators" tabindex="0"></div><div class="ib-det" id="bDet"></div></div></div>`, root => {
    const inp = $('bq') as HTMLInputElement; inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
    inp.oninput = () => { B.q = inp.value; B.sel = null; draw(); $('bList').scrollTop = 0 };
    const box = root.querySelector('.ib') as HTMLElement;
    makeWindow(box);
    box.addEventListener('click', e => {
      const t = e.target as HTMLElement, g = t.closest('[data-bg]') as HTMLElement | null, it = t.closest('[data-bi]') as HTMLElement | null, ad = t.closest('[data-badd]') as HTMLElement | null;
      if (g) { jumpGroup(g.dataset.bg!); return }
      if (it) { B.sel = it.dataset.bi!; draw(); inp.focus({ preventScroll:true }); return }
      const md = t.closest('[data-ibmode]') as HTMLElement | null;
      if (md) { setMode(md.closest('[data-ibkey]')!.getAttribute('data-ibkey')!, md.dataset.ibmode === 'cus'); return }
      const rs = t.closest('[data-ibreset]') as HTMLElement | null;
      if (rs) { CUS.delete(rs.closest('[data-ibkey]')!.getAttribute('data-ibkey')!); drawDetail(); ($('bDet').querySelector('[data-ibmode="def"]') as HTMLElement | null)?.focus(); return }
      if (ad && !(ad as HTMLButtonElement).disabled) add(ad.dataset.badd!);
    });
    box.addEventListener('input', e => { const t = e.target as HTMLInputElement; if (t.dataset.ibp) onField(t) });
    box.addEventListener('change', e => { const t = e.target as HTMLSelectElement; if (t.dataset.ibp) onField(t) });
    box.addEventListener('keydown', e => {
      const t = e.target as HTMLElement;
      if (t.closest('.ibs')) {   // typing in the fields never moves the list
        if (t.dataset.ibmode && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); setMode(t.closest('[data-ibkey]')!.getAttribute('data-ibkey')!, t.dataset.ibmode === 'def'); ($('bDet').querySelector('[data-ibmode][aria-checked="true"]') as HTMLElement | null)?.focus() }
        else if (e.key === 'Enter' && t.matches('input,select')) { e.preventDefault(); const k = B.sel; if (k) add(k) }
        return;
      }
      const vis = visible(); if (!vis.length) return;
      let i = vis.findIndex(x => x[0] === B.sel);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); i = Math.max(0, Math.min(vis.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1))); B.sel = vis[i][0]; draw(); $('bList').querySelector('.on')?.scrollIntoView({ block:'nearest' }) }
      else if (e.key === 'Enter' && B.sel && t.tagName !== 'BUTTON') { e.preventDefault(); const x = vis.find(v => v[0] === B.sel); if (x && x[1].available) add(B.sel) }
    });
    $('bList').addEventListener('scroll', spyGroups, { passive:true });
    draw();
  });
}

/* ---- the group list follows the scrolling list; a group click scrolls to it -------------------------------- */
let spyLock = 0;
function spyGroups() {
  if (Date.now() < spyLock) return;
  const list = document.getElementById('bList'), nav = document.getElementById('bNav'); if (!list || !nav) return;
  const hds = [...list.querySelectorAll<HTMLElement>('.hd[data-g]')]; if (!hds.length) return;
  let cur = hds[0]; for (const h of hds) if (h.offsetTop - list.offsetTop <= list.scrollTop + 12) cur = h;
  if (list.scrollTop + list.clientHeight >= list.scrollHeight - 2) cur = hds[hds.length - 1];
  const g = list.scrollTop < 4 ? 'All' : cur.dataset.g!;
  nav.querySelectorAll<HTMLElement>('[data-bg]').forEach(b => { const on = b.dataset.bg === g; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)) });
  (nav.querySelector('.on') as HTMLElement | null)?.scrollIntoView({ block:'nearest' });
}
function jumpGroup(g: string) {
  const list = $('bList');
  if (B.g !== 'All') { B.g = 'All'; draw() }
  const h = g === 'All' ? null : list.querySelector(`.hd[data-g="${CSS.escape(g)}"]`) as HTMLElement | null;
  spyLock = Date.now() + 600;
  list.scrollTo({ top:h ? h.offsetTop - list.offsetTop : 0, behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  $('bNav').querySelectorAll<HTMLElement>('[data-bg]').forEach(b => { const on = b.dataset.bg === g; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)) });
}

function draw() {
  const q = B.q.trim().toLowerCase(), all = items().filter(x => hit(x, q)), groups = ['All', 'My metrics', ...GORD], vis = visible();
  if (!vis.some(x => x[0] === B.sel)) B.sel = vis[0]?.[0] || null;
  $('bNav').innerHTML = groups.map(g => {
    const n = g === 'All' ? all.length : all.filter(x => group(x) === g).length;
    return (g === 'My metrics' && !n && !(ctx.metrics || []).length) || (g !== 'All' && !n) ? '' : `<button class="${g === 'All' ? 'on' : ''}" data-bg="${esc(g)}" aria-pressed="${g === 'All'}"><span>${g === 'All' ? 'All indicators' : esc(GHEAD(g))}</span><small>${n}</small></button>`;
  }).join('');
  let last = '';
  $('bList').innerHTML = vis.length ? vis.map(x => {
    const [k, e, m] = x, g = group(x), hd = g !== last ? `<div class="hd" data-g="${esc(g)}">${esc(GHEAD(g))}</div>` : ''; last = g;
    return hd + `<button class="${B.sel === k ? 'on' : ''} ${e.available ? '' : 'na'}" data-bi="${esc(k)}" role="option" aria-selected="${B.sel === k}"><b>${esc(m ? m.name : e.label)}</b><small>${esc(m ? e.label : e.available ? e.desc : `No data · ${e.reason}`)}</small></button>`;
  }).join('') : `<div class="empty" style="padding:24px 12px">No indicator matches “${esc(B.q)}”.</div>`;
  drawDetail();
  requestAnimationFrame(spyGroups);
}

/* ---- detail pane ------------------------------------------------------------------------------------------- */
const valueOf = (p: EntryParam, v: unknown) => optionText(p, v);
function paramsSection(k: string, e: Entry): string {
  const st = CUS.get(k) || { on:false, vals:{}, errs:{} }, n = e.params.length;
  const changed = st.on && e.params.some(p => st.vals[p.key] !== undefined && !isDefP(p, st.vals[p.key]));
  const head = `<div class="ibs-h"><i class="ibs-n" aria-hidden="true">1</i><div class="ibs-t"><b>Parameters</b><small>${n ? `How it is calculated · ${n} setting${n > 1 ? 's' : ''}` : 'How it is calculated'}</small></div><span class="ibr-state">${changed ? `<span class="pill info">Changed</span><button type="button" class="ibs-link" data-ibreset>Reset</button>` : `<span class="pill">${defaultOffered(e) ? 'Default' : 'Starting values'}</span>`}</span></div>`;
  if (!n) return `<section class="ibc ibs" data-ibkey="${esc(k)}" aria-label="Parameters">${head}<div class="ibs-b"><p class="ibs-note">Fixed definition. This indicator has no settings to change.</p></div></section>`;
  const seg = `<span class="seg sm ibs-seg" role="radiogroup" aria-label="Parameters"><button type="button" role="radio" data-ibmode="def" aria-checked="${!st.on}" class="${st.on ? '' : 'on'}" tabindex="${st.on ? -1 : 0}">Default</button><button type="button" role="radio" data-ibmode="cus" aria-checked="${st.on}" class="${st.on ? 'on' : ''}" tabindex="${st.on ? 0 : -1}">Custom</button></span>`;
  const cls = `ibc ibs ${st.on ? 'is-custom' : ''} ${changed ? 'is-changed' : ''}`;
  if (!st.on) return `<section class="${cls}" data-ibkey="${esc(k)}" aria-label="Parameters">${head}<div class="ibs-b">${seg}<div class="ibp-list" role="table" aria-label="Parameters">${e.params.map(p => `<div class="ibp-row" role="row"><span role="cell">${esc(p.label || p.key)}</span><small role="cell">${esc(rangeText(p) || (p.options ? `${p.options.length} options` : p.type === 'boolean' ? 'on or off' : ''))}</small><b role="cell">${esc(valueOf(p, p.default))}</b></div>`).join('')}</div>
    <p class="ibs-note">${defaultOffered(e) ? 'Standard settings.' : esc(T.noDefault)} Choose Custom to change them.</p></div></section>`;
  const fld = (p: EntryParam) => {
    const v = st.vals[p.key] ?? p.default, err = st.errs[p.key], chg = !isDefP(p, v as ParamValue);
    const ctl = p.options ? `<select class="sel" data-ibp="${esc(p.key)}">${p.options.map(o => `<option value="${esc(o)}" ${String(o) === String(v) ? 'selected' : ''}>${esc(optionText(p, o))}</option>`).join('')}</select>`
      : p.type === 'boolean' ? `<select class="sel" data-ibp="${esc(p.key)}"><option value="true" ${v === true ? 'selected' : ''}>true</option><option value="false" ${v === false ? 'selected' : ''}>false</option></select>`
      : `<input class="inp" type="number" data-ibp="${esc(p.key)}" value="${esc(v)}" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="${p.step ?? (p.integer ? 1 : 'any')}" aria-invalid="${!!err}">`;
    return `<label class="ibf ${chg ? 'chg' : ''}" data-ibf="${esc(p.key)}"><span>${esc(p.label || p.key)}</span>${ctl}<small>default ${esc(valueOf(p, p.default))}${rangeText(p) ? `<i class="rng"> · ${esc(rangeText(p))}</i>` : ''}</small><em class="ibf-err" role="alert" ${err ? '' : 'hidden'}>${esc(err || '')}</em></label>`;
  };
  return `<section class="${cls}" data-ibkey="${esc(k)}" aria-label="Parameters">${head}<div class="ibs-b">${seg}<div class="ibc-g">${e.params.map(fld).join('')}</div></div></section>`;
}
function setMode(k: string, on: boolean) {
  const st = CUS.get(k) || { on:false, vals:{}, errs:{} }; st.on = on; if (!on) { st.vals = {}; st.errs = {} } CUS.set(k, st);
  drawDetail();
  ($('bDet').querySelector(on ? '[data-ibp]' : '[data-ibmode="def"]') as HTMLElement | null)?.focus();
}
/** a custom field changed: check it against the catalog's range, mark it, update the start text and the Add label */
function onField(el: HTMLInputElement | HTMLSelectElement) {
  const box = el.closest('[data-ibkey]') as HTMLElement, k = box.dataset.ibkey!, e = ctx.byKey.get(k); if (!e) return;
  const p = e.params.find(x => x.key === el.dataset.ibp); if (!p) return;
  const st = CUS.get(k)!; const raw = el.value;
  const v: ParamValue = p.type === 'boolean' ? raw === 'true' : p.type === 'enum' ? raw : raw.trim() === '' ? NaN : Number(raw);
  const msg = paramError(p, v);
  if (msg) st.errs[p.key] = msg; else { delete st.errs[p.key]; st.vals[p.key] = v }
  const f = box.querySelector(`[data-ibf="${CSS.escape(p.key)}"]`)!, em = f.querySelector('.ibf-err') as HTMLElement;
  em.textContent = msg || ''; em.hidden = !msg; el.setAttribute('aria-invalid', String(!!msg));
  f.classList.toggle('chg', !msg && !isDefP(p, v));
  const changed = e.params.some(x => st.vals[x.key] !== undefined && !isDefP(x, st.vals[x.key]));
  box.classList.toggle('is-changed', changed);
  const stt = box.querySelector('.ibr-state')!;
  stt.innerHTML = changed ? `<span class="pill info">Changed</span><button type="button" class="ibs-link" data-ibreset>Reset</button>` : `<span class="pill">${defaultOffered(e) ? 'Default' : 'Starting values'}</span>`;
  footer(k, e);
}
function footer(k: string, e: Entry) {
  const add = $('bDet').querySelector('[data-badd]') as HTMLButtonElement | null, start = $('bDet').querySelector('.ib-start');
  const p = customOf(k, e), card = newCard(e, [], p ? { params:p } : {});
  if (start) start.textContent = condText(e, card);
  if (add && e.available) add.innerHTML = `${ico(IC.plus, 's')}${p ? 'Add with custom settings' : 'Add to screen'}`;
}
function drawDetail() {
  const vis = visible(), x = vis.find(v => v[0] === B.sel);
  if (!x) { $('bDet').innerHTML = ''; return }
  const [k, e, m] = x;
  const card = m ? fromWire({ id:'m', enabled:true, test:(m.definition as any).test }, ctx.byKey) : newCard(e, []);
  const p = card.params;
  const fact = (pp: Entry['params'][number]) => `<div><span>${esc(pp.label || pp.key)}${rangeText(pp) ? ` <small class="muted">${esc(rangeText(pp))}</small>` : ''}</span><b>${esc(optionText(pp, p[pp.key]))}${pp.options ? ` <small class="muted">of ${pp.options.length}</small>` : ''}</b></div>`;
  const params = m ? `<div class="sec-title">Saved parameters</div>${e.params.length ? `<div class="facts">${e.params.map(fact).join('')}</div>` : '<p class="muted">Fixed definition — nothing to tune.</p>'}`
    : e.available ? paramsSection(k, e)
    : `<div class="sec-title">${defaultOffered(e) ? 'Default parameters' : 'Starting parameters'}</div>${e.params.length ? `<div class="facts">${e.params.map(fact).join('')}</div>` : '<p class="muted">Fixed definition — nothing to tune.</p>'}`;
  $('bDet').innerHTML = `<div class="ib-h"><span class="tag ${esc(e.group)}">${esc(GL(e.group))}</span>${e.xid ? `<span class="muted">${esc(e.xid)}</span>` : ''}</div><h4>${esc(m ? m.name : e.label)}</h4><p class="muted">${esc(e.desc)}</p>
    ${e.available ? '' : `<p class="note down">${esc(e.reason || 'Not available.')}</p>`}${e.history ? `<p class="note">${esc(e.history)}</p>` : ''}
    ${params}
    <div class="sec-title">Conditions you can test</div><ul class="ib-ops">${e.opts.map(o => `<li${o.disabled ? ` class="muted" title="${esc(o.disabled)}"` : ''}>${esc(o.label)}${o.disabled ? ' — not offered' : ''}</li>`).join('')}</ul>
    <div class="sec-title">Starts as</div><p class="ib-start">${esc(condText(e, card))}</p>
    <div class="ib-foot"><button class="btn primary" data-badd="${esc(k)}" style="width:100%" ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${ico(IC.plus, 's')}Add to screen</button><p class="note" style="margin:4px 0 0">Enter adds the highlighted indicator · ↑ ↓ to move</p></div>`;
  if (!m && e.available) footer(k, e);
}
