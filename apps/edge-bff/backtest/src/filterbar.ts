/* EXEC-BACKTEST-REVAMP Tahap D (design "Signals v4": the formula bar above the chart, the design's xfb): the entry rule
   (All, Any, At least N) and the first three active entry conditions as chips with their letter (the lanes' A, B, C),
   name and the setting that differs from its default in blue; "+N more" or "Add" opens the condition window. */
import { $, esc, ico } from './format.ts';
import { S } from './state.ts';
import { CATALOG, REG_BY, catOf, condReady } from './reg.ts';
import type { Card } from './api/types.ts';
import { letterOf } from './lanes.ts';
import { condName, refreshSignals } from './signals.ts';
import { markStale, renderBuilder } from './builder.ts';
import { openCondWin } from './condwin.ts';
import { SC, entryOf } from './grammar.ts';
import { condRule, isCustom, shortParts } from '../../screener/src/forms.ts';

const changed = () => { markStale(); renderBuilder(); refreshSignals() };

/** a legacy card that differs from its catalog defaults (value or a parameter): its setting is shown in blue */
const custom = (c: Card) => {
  if (c.type === 'test') { const e = entryOf(c); return !!e && isCustom(e, c.sc) }
  if (c.type === 'reg') return false;
  const d = CATALOG[c.type] as any, lc = c as any;
  return (lc.val != null && d.val != null && lc.val != d.val) || d.params.some((q: unknown[]) => q[2] != null && lc[q[0] as string] != q[2]);
};

export function renderFilterBar() {
  const box = $('xfb');
  if (!box) return;
  const act = S.conds.filter(c => c.on && condReady(c)), na = act.length;
  const chip = (c: Card, k: number) => {
    if (c.type === 'test') {   // Stage D: the Screener's short name and rule (forms.ts shortParts)
      const e = entryOf(c), sp = e ? { base: shortParts(e, c.sc).base, rule: shortParts(e, c.sc).rule || condRule(e, c.sc) } : { base: 'Condition', rule: '' };
      return `<button type="button" class="fchip" data-fc="${c.id}" title="Edit ${esc(condName(c))} in the workspace"><span class="bd">${letterOf(k)}</span><span class="nm">${esc(sp.base)}</span><b class="${custom(c) ? 'cu' : ''}">${esc(sp.rule || '')}</b>${ico('<path d="m6 9 6 6 6-6"/>')}</button>`;
    }
    const t = catOf(c), full = condName(c), lc = c as any;
    const head = c.type === 'reg' ? REG_BY[lc.ind].name : t.label + (t.params.length ? ` (${t.params.map(([q]) => lc[q]).join(',')})` : '');
    const tail = full.startsWith(head) ? full.slice(head.length).replace(/^\s*·\s*/, '').trim() : full;
    // a registry card's short name is the catalog's (the Screener's shortOf: its `short` or an upper-case synonym); the
    // registry's own `short` is a description sentence in the real data
    const nm = c.type === 'reg' ? SC.by.get(lc.ind)?.short || REG_BY[lc.ind].name : t.label.replace(/^Stochastic /, 'Stoch ');
    return `<button type="button" class="fchip" data-fc="${c.id}" title="Edit ${esc(full)} in the workspace"><span class="bd">${letterOf(k)}</span><span class="nm">${esc(nm)}</span><b class="${custom(c) ? 'cu' : ''}">${esc(tail)}</b>${ico('<path d="m6 9 6 6 6-6"/>')}</button>`;
  };
  box.innerHTML = `<span class="lbl">Entry</span><span class="seg sm" role="radiogroup" aria-label="Entry rule">${([['all', 'All'], ['any', 'Any'], ['n', 'At least']] as const).map(([v, l]) => `<button type="button" role="radio" aria-checked="${S.logic === v}" class="${S.logic === v ? 'on' : ''}" data-fl="${v}">${l}</button>`).join('')}</span>${S.logic === 'n' ? `<input class="inp fn" type="number" min="1" max="${Math.max(1, na)}" value="${S.atLeast}" data-fk="atLeast" aria-label="Minimum number of conditions">` : ''}`
    + act.slice(0, 3).map(chip).join('')
    + (na > 3 ? `<button type="button" class="fchip more" id="fcAdd" title="Open the conditions workspace"><span class="k">+${na - 3}</span>more</button>` : `<button type="button" class="fchip add" id="fcAdd" title="Add a condition">${ico('<path d="M12 5v14M5 12h14"/>')}Add</button>`);
  box.querySelectorAll('[data-fl]').forEach((b: HTMLElement) => b.onclick = () => { if (S.logic !== b.dataset.fl) { S.logic = b.dataset.fl as typeof S.logic; changed() } });
  box.querySelectorAll('[data-fk]').forEach((b: HTMLInputElement) => b.onchange = () => { S.atLeast = Math.max(1, Math.round(+b.value || 1)); changed() });
  box.querySelectorAll('[data-fc]').forEach((b: HTMLElement) => b.onclick = () => openCondWin({ kind: 'cond', id: b.dataset.fc! }, 'entry'));
  $('fcAdd').onclick = () => openCondWin(null, 'entry');
}
