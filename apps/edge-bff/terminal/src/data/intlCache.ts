/* One Intl formatter per locale and option set, made once and kept (EXEC-TERMINAL-LAG-2 U4, user 2026-11-22: "U1 + U2 +
   U4 go"). Making the formatter is the cost: Number#toLocaleString and Date#toLocaleDateString build a new one on every
   call, and the Terminal formats prices, values and dates on every crosshair move and pan frame (the price formatter took
   416 ms of a 6.3 s drag with the CPU four times slower, BBCA). The text is the same as toLocaleString /
   toLocaleDateString with the same arguments (tests/data/intl_cache.test.ts); tests/data/intl_cache.test.ts also refuses a
   toLocale*() call or a formatter made inside a function anywhere in src/, so a new formatting path uses these. */
const numbers = new Map<string, Intl.NumberFormat>();
const dates = new Map<string, Intl.DateTimeFormat>();

/** the formatter of `value.toLocaleString(locale, opts)` */
export function numberFormat(locale: string, opts: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const k = locale + JSON.stringify(opts);
  let f = numbers.get(k);
  if (!f) numbers.set(k, f = new Intl.NumberFormat(locale, opts));
  return f;
}

/** the formatter of `date.toLocaleDateString(locale, opts)`: as that method, options naming no part of a date get the
    numeric day, month and year */
export function dateFormat(locale: string, opts: Intl.DateTimeFormatOptions = {}): Intl.DateTimeFormat {
  const k = locale + JSON.stringify(opts);
  let f = dates.get(k);
  if (!f) {
    const o = opts.weekday || opts.year || opts.month || opts.day ? opts : { ...opts, year: 'numeric', month: 'numeric', day: 'numeric' } as Intl.DateTimeFormatOptions;
    dates.set(k, f = new Intl.DateTimeFormat(locale, o));
  }
  return f;
}
