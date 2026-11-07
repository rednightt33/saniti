/* A condition's cell as text, the one copy the result table and the preview's "Why it passed" both write (QA5
   2026-11-07 D1: the preview had its own copy, which did not know the universal operators and read an operator card
   by the card's default condition: "Yes"/"No" for a rank, "-2.1" for a z-score the table writes "-2.07σ"). Display
   only: the value comes from the worker's cell, its format from the catalog (an operator card's from operators.ts). */
import type { Cell } from './core/contract.ts';
import type { Entry } from './entries.ts';
import { formatOfOpt } from './entries.ts';
import { fmtValue } from './format.ts';
import { optOf, type Card } from './forms.ts';
import { opValueText } from './operators.ts';
import { eventText } from './texts.ts';

/** The test kind a card's cells are: an operator card's test (a cross is an event, ever / K of N / in a row a window),
    else its condition's kind, else a kept card's wire kind. */
export const kindOfCard = (c: Card, e: Entry | undefined): string | undefined => {
  if (c.op) return c.op.test === 'cross' ? 'event' : c.op.test === 'ever' || c.op.test === 'at_least' || c.op.test === 'streak' ? 'window' : 'value';
  const o = e && optOf(e, c); return o?.kind || (c.raw as { kind?: string } | undefined)?.kind;
};
/** The cell's text: n/a, the event's age ("No" when none within reach), Yes / No for a state, an operator's value in its
    unit ("Yes · 3/5" for a window), else the value in the condition's format. */
export function cellText(e: Entry | undefined, c: Card, x: Cell | undefined): string {
  if (!x) return '—';
  if (x.status === 'na') return 'n/a';
  if (x.status === 'not_evaluated') return '·';
  const kind = kindOfCard(c, e);
  if (kind === 'event') return x.status !== 'pass' && x.bars_ago == null ? 'No' : eventText(x);
  if (kind === 'state') return x.status === 'pass' ? 'Yes' : 'No';
  if (c.op && e?.ops) return opValueText(e.ops, e, c.op, x.value, x.status === 'pass');
  return fmtValue(x.value, formatOfOpt(e, e ? optOf(e, c) : undefined));
}
