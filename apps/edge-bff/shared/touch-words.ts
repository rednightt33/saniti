/* The words of a hint follow the screen's pointer: on a phone or tablet (a coarse pointer, no mouse) a hint says tap, not
   click, double-click or hover (EXEC-SECTOR-ANALYSIS check 2 MX2-8 on the Sector page; its other pages by the user's
   2026-11-27 "ud 81 oke dgn rekomendasi": the Watchlist, the Screener and the Backtest). One source for every EDGE page
   but the Terminal ("Terminal jangan disentuh"). Read once, at load: a page is not moved between a mouse and a touch
   screen while it is open. */
export const TOUCH = typeof matchMedia !== 'undefined' && matchMedia('(pointer: coarse)').matches;
/** the mouse words, or the touch words on a touch screen */
export const tap = (mouse: string, touch: string): string => (TOUCH ? touch : mouse);
