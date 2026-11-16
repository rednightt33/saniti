/* EXEC-BACKTEST-REVAMP Tahap D: the design's condition window ("Add a condition", the design's cw*). Built in D5; until
   then it opens the conditions workspace. */
import { openWS } from './workspace.ts';

/** how many rows the window offers (the add box's label) */
export const condWinCount = (): number => 0;
/** open the window on a condition (or none) for the entry or the exit list */
export const openCondWin = (sel: { kind: string; id: string } | null, side: 'entry' | 'exit' = 'entry') => openWS(sel, side);
