/* The side a Flow indicator reads, as its title writes it (EXEC-FL51-TITLE, ERRORS M540; the user 2026-11-23: "M540
   masukan exec untuk diperbaiki", wording "B1"). Derived from the registry's own options of the `side` parameter, never
   from a list of values: the first option is the indicator's own reading and is not written (Buy for the buy/sell
   indicators, Loaders for FL51 Loaders); `both` joins the labels of the other options ("Buy & Sell", "Loaders &
   Sellers"); any other option is its label ("Sell", "Sellers"). The fixed rule it replaces wrote every value but buy
   and both as "Sell", so FL51 on Loaders read "Loaders (Top 3, Sell, …)". */
export type SideOptions = ReadonlyArray<readonly [string, string]>;

export function sideWord(options: SideOptions | undefined, value: string | null | undefined): string | null {
  if (!value || !options?.length) return null;
  if (value === options[0][0]) return null;
  if (value === 'both') return options.filter(([v]) => v !== 'both').map(([, label]) => label).join(' & ') || null;
  return options.find(([v]) => v === value)?.[1] ?? value;
}
