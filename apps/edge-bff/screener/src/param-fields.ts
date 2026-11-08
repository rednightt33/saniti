/* The fields of a flow indicator's parameters that the catalog's four kinds do not cover (EXEC-SCREENER-FLOW-CANDLES
   P5c; entries.ts FlowParamType), one copy for the Add a condition window and the condition card: the boards and the
   investor types as a group of checkboxes (at least one on), an anchor date as a date field limited to the loaded broker
   data (empty: its first session), broker codes as a text field (empty: the Terminal's default). Each control carries
   the caller's own attributes (data-ap / data-ai, data-c / data-p), so the caller's change handler reads it back with
   paramFieldValue, as for its other fields. Markup only, no handler: the page's CSP allows no inline script. */
import type { ParamValue } from './core/contract.ts';
import { isFlowType, LIST_SEP, listOf, optionText, rangeText, type EntryParam } from './entries.ts';
import { esc } from './format.ts';

/** The control of a parameter of a FlowParamType (null for the catalog's own kinds, which the caller draws). `attrs`:
    the caller's data attributes; `label`: its accessible name; `title`: its tooltip (the rule, the default). */
export function flowControlHtml(p: EntryParam, v: ParamValue | undefined, attrs: string, label: string, title: string, invalid = false): string | null {
  if (!isFlowType(p)) return null;
  const inv = invalid ? ' aria-invalid="true"' : '', tip = title ? ` title="${esc(title)}"` : '';
  if (p.type === 'multi') {
    const on = new Set(listOf(v));
    return `<span class="msel" role="group" aria-label="${esc(label)}"${inv}${tip}>${(p.options || []).map(o =>
      `<label class="mopt"><input type="checkbox" ${attrs} data-mv="${esc(o)}" ${on.has(o) ? 'checked' : ''} aria-label="${esc(`${label}: ${optionText(p, o)}`)}"><span>${esc(optionText(p, o))}</span></label>`).join('')}</span>`;
  }
  if (p.type === 'date') {
    const w = p.dates, val = v === 'view' || v == null ? '' : String(v);
    return `<input class="inp inp-date" type="date" ${w?.first ? `min="${esc(w.first)}"` : ''} ${w?.last ? `max="${esc(w.last)}"` : ''} value="${esc(val)}" ${attrs} aria-label="${esc(label)}"${inv} title="${esc([title, 'Empty: the first session of the broker data'].filter(Boolean).join(' · '))}">`;
  }
  return `<input class="inp inp-codes" type="text" autocomplete="off" spellcheck="false" placeholder="default" value="${esc(listOf(v).join(', '))}" ${attrs} aria-label="${esc(label)}"${inv} title="${esc([title, 'Broker codes separated by commas, e.g. YP, AK; empty: the default'].filter(Boolean).join(' · '))}">`;
}
/** A parameter's tooltip: its range or window, and its default (or the value a card opens with). */
export const paramTitle = (p: EntryParam, def: ParamValue | undefined, word = 'default') => `${rangeText(p) ? rangeText(p) + ' · ' : ''}${word} ${optionText(p, def)}`;

/** A parameter field's value as the card keeps it: a list from its checkbox group (in the options' order), an anchor
    date ('view' when empty), broker codes in capitals joined by commas; an option, true / false, or a number (NaN when
    empty, so the check names it) for the catalog's own kinds. */
export function paramFieldValue(p: EntryParam, el: HTMLInputElement | HTMLSelectElement): ParamValue {
  if (p.type === 'multi') {
    const box = el.closest('.msel'), on = new Set([...(box?.querySelectorAll<HTMLInputElement>('input[type="checkbox"]') ?? [])].filter(x => x.checked).map(x => x.dataset.mv || ''));
    return (p.options || []).filter(o => on.has(o)).join(LIST_SEP);
  }
  if (p.type === 'date') return el.value.trim() === '' ? 'view' : el.value.trim();
  if (p.type === 'brokers') return el.value.split(/[\s,;]+/).map(x => x.trim().toUpperCase()).filter(Boolean).join(LIST_SEP);
  return p.type === 'boolean' ? el.value === 'true' : p.options || p.type === 'enum' ? el.value : el.value.trim() === '' ? NaN : Number(el.value);
}
