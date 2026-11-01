/* User 2026-11-01 (US10Y screenshot: Flow indicators "Loading broker data", "Volume 0", "No volume for this ticker" on a
   bond chart): "kalau kita buka chart obligasi ... hanya chart aja. Tanpa indikator lain-lain. Kecuali memang indikator
   tersebut berkaitan dengan indikator technical".

   ERRORS M332: the saved indicator list is one list for every ticker, and it was drawn on any ticker whether or not the
   ticker has the data the indicator reads. The rule here is general: an indicator (and the base volume histogram) is
   drawn only on a ticker that has every input it reads. The inputs a ticker has are derived from its loaded data, not
   from a list of asset kinds, so a bond, an index without volume, or a later dataset (macro, cross-asset) is covered
   without a change here:
     O H L C  the candles' prices (every published price row has the four);
     V        a volume on at least one candle (a bond's files carry none: publisher fi_doc, v is always null);
     flow     the ticker's broker and events files (live: the page asks for them, M.later; a bond has none).
   An indicator's needs come from its definition: the registry's `req` letters (indRegistry.json), Flow for the Flow
   indicators and the broker lines. An indicator the ticker cannot feed is kept in the saved list (parked), not
   deleted: it comes back on the next ticker that has its data. */
import type { MarketData } from './types';

export type Input = 'O' | 'H' | 'L' | 'C' | 'V' | 'flow';
/** every input (a ticker with all of them: a stock with broker files) */
export const ALL_INPUTS: ReadonlySet<Input> = new Set<Input>(['O', 'H', 'L', 'C', 'V', 'flow']);

/** the inputs the loaded ticker has */
export function inputsOf(M: Pick<MarketData, 'mode' | 'ohlc' | 'volume' | 'later'>): Set<Input> {
  const have = new Set<Input>();
  const ok = (v: unknown) => typeof v === 'number' && Number.isFinite(v);
  if (M.ohlc.some(b => ok(b.open))) have.add('O');
  if (M.ohlc.some(b => ok(b.high))) have.add('H');
  if (M.ohlc.some(b => ok(b.low))) have.add('L');
  if (M.ohlc.some(b => ok(b.close))) have.add('C');
  if (M.volume.some(v => !v.none && ok(v.value))) have.add('V');
  if (M.mode !== 'live' || M.later) have.add('flow');     // the reference fixture carries its own broker data
  return have;
}

/** what an indicator definition reads: `needs` when it says so, Flow for a Flow indicator, else its registry letters
    ("HLCV": high, low, close, volume); a definition that names nothing reads the close */
export function needsOf(def: { needs?: Input[]; flow?: boolean; reg?: { req?: string } } | null | undefined): Input[] {
  if (!def) return [];
  if (def.needs) return def.needs;
  if (def.flow) return ['flow'];
  const req = String(def.reg?.req || 'C').toUpperCase();
  return [...new Set([...req].filter((c): c is Input => 'OHLCV'.includes(c)))];
}

/** the inputs an indicator reads that the ticker lacks (empty: it can be drawn) */
export const lacking = (needs: Input[], have: ReadonlySet<Input>) => needs.filter(n => !have.has(n));
export const fits = (needs: Input[], have: ReadonlySet<Input>) => lacking(needs, have).length === 0;

/** a saved list split into the entries drawn on this ticker and the ones kept for another (with their place, so a
    save writes the list back in its order) */
export function splitSaved<T>(saved: T[], fitsEntry: (o: T) => boolean) {
  const drawn: T[] = [], parked: { at: number; o: T }[] = [];
  saved.forEach((o, at) => fitsEntry(o) ? drawn.push(o) : parked.push({ at, o }));
  return { drawn, parked };
}
/** the list to save: the drawn entries with the parked ones back at their places */
export function withParked<T>(drawn: T[], parked: { at: number; o: T }[]): T[] {
  const out = [...drawn];
  for (const p of [...parked].sort((a, b) => a.at - b.at)) out.splice(Math.min(p.at, out.length), 0, p.o);
  return out;
}
