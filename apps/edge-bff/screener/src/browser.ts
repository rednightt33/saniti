/* The indicator browser dialog (the prototype's openBrowser / drawBrowser): groups with counts, a list (listbox) and
   the details of the highlighted entry, with real ranges (min / max, the derived caps), typed booleans, the history
   class ("level depends on history start" for cumulative indicators) and, for an entry without data, its reason
   (report 9.2). Keys: arrows move, Enter adds. */
import type { SavedItem } from './core/contract.ts';
import { esc } from './format.ts';
import { IC, ico } from './icons.ts';
import { ctx } from './state.ts';
import { byGroup, GHEAD, GL, GORD, matches, rangeText, type Entry } from './entries.ts';
import { condText, fromWire, newCard } from './forms.ts';
import { closeDialog, dialog } from './dialogs.ts';

type Item = [key: string, e: Entry, m?: SavedItem];
const B = { q:'', g:'All', sel:null as string | null };
const $ = (id: string) => document.getElementById(id)!;

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

export function openBrowser(q: string, act: { addCond(k: string): void; addMetric(id: string): void }) {
  B.q = q || ''; B.g = 'All'; B.sel = null;
  const add = (k: string) => { closeDialog(); k.startsWith('m:') ? act.addMetric(k.slice(2)) : act.addCond(k) };
  dialog(`<div class="dialog xl ib" role="dialog" aria-label="Browse indicators"><div class="dialog-h"><div style="flex:1"><strong>Indicators</strong><small>Pick a group, choose an indicator, check its settings, then add it. Parameters can still be changed on the card.</small></div><button class="iconbtn sm" data-close aria-label="Close">${ico(IC.x)}</button></div>
    <div class="ib-top"><label class="searchbox">${ico(IC.search, 's')}<input id="bq" value="${esc(B.q)}" placeholder="Search by name, short name or what it measures" autocomplete="off" aria-label="Search indicators"></label></div>
    <div class="ib-body"><nav class="ib-nav" id="bNav" aria-label="Groups"></nav><div class="ib-list" id="bList" role="listbox" aria-label="Indicators" tabindex="0"></div><div class="ib-det" id="bDet"></div></div></div>`, root => {
    const inp = $('bq') as HTMLInputElement; inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
    inp.oninput = () => { B.q = inp.value; B.sel = null; draw() };
    const box = root.querySelector('.ib') as HTMLElement;
    box.addEventListener('click', e => {
      const t = e.target as HTMLElement, g = t.closest('[data-bg]') as HTMLElement | null, it = t.closest('[data-bi]') as HTMLElement | null, ad = t.closest('[data-badd]') as HTMLElement | null;
      if (g) { B.g = g.dataset.bg!; B.sel = null; draw(); inp.focus({ preventScroll:true }); return }
      if (it) { B.sel = it.dataset.bi!; draw(); inp.focus({ preventScroll:true }); return }
      if (ad && !(ad as HTMLButtonElement).disabled) add(ad.dataset.badd!);
    });
    box.addEventListener('keydown', e => {
      const vis = visible(); if (!vis.length) return;
      let i = vis.findIndex(x => x[0] === B.sel);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); i = Math.max(0, Math.min(vis.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1))); B.sel = vis[i][0]; draw(); $('bList').querySelector('.on')?.scrollIntoView({ block:'nearest' }) }
      else if (e.key === 'Enter' && B.sel && (e.target as HTMLElement).tagName !== 'BUTTON') { e.preventDefault(); const x = vis.find(v => v[0] === B.sel); if (x && x[1].available) add(B.sel) }
    });
    draw();
  });
}

function draw() {
  const q = B.q.trim().toLowerCase(), all = items().filter(x => hit(x, q)), groups = ['All', 'My metrics', ...GORD], vis = visible();
  if (!vis.some(x => x[0] === B.sel)) B.sel = vis[0]?.[0] || null;
  $('bNav').innerHTML = groups.map(g => {
    const n = g === 'All' ? all.length : all.filter(x => group(x) === g).length;
    return g === 'My metrics' && !n && !(ctx.metrics || []).length ? '' : `<button class="${B.g === g ? 'on' : ''}" data-bg="${esc(g)}" aria-pressed="${B.g === g}"><span>${g === 'All' ? 'All indicators' : esc(GHEAD(g))}</span><small>${n}</small></button>`;
  }).join('');
  let last = '';
  $('bList').innerHTML = vis.length ? vis.map(x => {
    const [k, e, m] = x, g = group(x), hd = B.g === 'All' && g !== last ? `<div class="hd">${esc(GHEAD(g))}</div>` : ''; last = g;
    return hd + `<button class="${B.sel === k ? 'on' : ''} ${e.available ? '' : 'na'}" data-bi="${esc(k)}" role="option" aria-selected="${B.sel === k}"><b>${esc(m ? m.name : e.label)}</b><small>${esc(m ? e.label : e.available ? e.desc : `No data · ${e.reason}`)}</small></button>`;
  }).join('') : `<div class="empty" style="padding:24px 12px">No indicator matches “${esc(B.q)}”.</div>`;
  const x = vis.find(v => v[0] === B.sel);
  if (!x) { $('bDet').innerHTML = ''; return }
  const [k, e, m] = x;
  const card = m ? fromWire({ id:'m', enabled:true, test:(m.definition as any).test }, ctx.byKey) : newCard(e, []);
  const p = card.params;
  const fact = (pp: Entry['params'][number]) => `<div><span>${esc(pp.label || pp.key)}${rangeText(pp) ? ` <small class="muted">${esc(rangeText(pp))}</small>` : ''}</span><b>${esc(p[pp.key])}${pp.options ? ` <small class="muted">of ${pp.options.length}</small>` : ''}</b></div>`;
  $('bDet').innerHTML = `<div class="ib-h"><span class="tag ${esc(e.group)}">${esc(GL(e.group))}</span>${e.xid ? `<span class="muted">${esc(e.xid)}</span>` : ''}</div><h4>${esc(m ? m.name : e.label)}</h4><p class="muted">${esc(e.desc)}</p>
    ${e.available ? '' : `<p class="note down">${esc(e.reason || 'Not available.')}</p>`}${e.history ? `<p class="note">${esc(e.history)}</p>` : ''}
    <div class="sec-title">${m ? 'Saved parameters' : 'Default parameters'}</div>${e.params.length ? `<div class="facts">${e.params.map(fact).join('')}</div>` : '<p class="muted">Fixed definition — nothing to tune.</p>'}
    <div class="sec-title">Conditions you can test</div><ul class="ib-ops">${e.opts.map(o => `<li${o.disabled ? ` class="muted" title="${esc(o.disabled)}"` : ''}>${esc(o.label)}${o.disabled ? ' — not offered' : ''}</li>`).join('')}</ul>
    <div class="sec-title">Starts as</div><p class="ib-start">${esc(condText(e, card))}</p>
    <div class="ib-foot"><button class="btn primary" data-badd="${esc(k)}" style="width:100%" ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${ico(IC.plus, 's')}Add to screen</button><p class="note" style="margin:4px 0 0">Enter adds the highlighted indicator · ↑ ↓ to move</p></div>`;
}
