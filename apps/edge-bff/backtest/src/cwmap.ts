/* The page's own card for a registry choice of the condition window (the design's cwMap): the Screener's option key is
   `${form}|${output}|${op}`. Its own module so that a test reads it without the window's DOM (condwin.ts). */
import type { RegCard } from './core/catalog.ts';
import { REG_BY } from './reg.ts';

const OPM: Record<string, RegCard['op']> = { gt: 'gt', lt: 'lt', crosses_above: 'ca', crosses_below: 'cb' };
/* ERRORS M554: the other output of an output-vs-output choice is the option's `with_output`, the Screener registry's own
   partner (MACD's signal, Alpha Volatile's upper_z or lower_z), never guessed from the label's words or taken as the
   first output not named `direction` (which would pair Alpha Volatile's distance with its decile). */
export function cwMap(code: string, opt: { key: string; with_output?: string } | undefined): Pick<RegCard, 'lhs' | 'op' | 'rhs'> | null {
  const t = REG_BY[code], key = opt?.key;
  if (!t || !key) return null;
  const q = key.split('|'), kind = q[0], o = q[1], op = OPM[q[q.length - 1]];
  if (!op || !t.out.includes(o)) return null;
  const ev = op === 'ca' || op === 'cb';
  if ((kind === 'value' && !ev) || (kind === 'event_value' && ev)) return { lhs: { t: 'out', o }, op, rhs: { t: 'val', v: 0 } };
  if ((kind === 'state_level' && !ev) || (kind === 'event_level' && ev)) return { lhs: { t: 'price' }, op, rhs: { t: 'out', o } };
  if (kind === 'state_output' || kind === 'event_output') {
    const oth = opt!.with_output;
    if (oth && oth !== o && t.out.includes(oth) && ((kind === 'state_output' && !ev) || (kind === 'event_output' && ev))) return { lhs: { t: 'out', o }, op, rhs: { t: 'out', o: oth } };
  }
  return null;
}
