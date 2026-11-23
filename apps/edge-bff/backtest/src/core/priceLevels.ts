/* The outputs of an indicator that are price levels (ERRORS M554, 2026-11-23): the ones the unit probe of the Screener's
   registry generator marks as unit price, comparable with close (they scale with the price and move with a shift of
   it), written to compare-lag.json `price_levels` in the registry's order. The Backtest's price lines (engine.ts
   LEVEL_LINES and lineOf, the page's reg.ts LEVEL_LINES), the lines a stop or a trailing stop can sit on, are the
   price levels of the indicators drawn on the price. Derived, not named: the rule it replaces offered every output but
   one named `direction`, so a 0/1 flag of an indicator drawn on the price (Inside Bar's `ib`) became a stop line. An
   output the probe marks later is covered without a code change. */
import lagDoc from './compare-lag.json' with { type: 'json' };

const LEVELS = (lagDoc as { price_levels: Record<string, string[]> }).price_levels;
/** the price-level outputs of an indicator, in the registry's order (none for an indicator the probe marks none of) */
export const priceLevels = (id: string): readonly string[] => LEVELS[id] ?? [];
