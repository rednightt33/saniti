/* EXEC-TERMINAL-SPIN (user 2026-10-26: "lingkaran berputar dengan cepat"): a spinning ring with a short text, for
   anything still loading. EXEC-BACKTEST-SPIN: shared by every rack page (styles/spin.css). `msg` is markup: escape any
   text that is not the page's own. */
export const spin = (msg: string) => `<span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>${msg}</span>`;
