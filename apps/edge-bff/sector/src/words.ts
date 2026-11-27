/* EXEC-SECTOR-ANALYSIS S4: every word the page shows, in plain English sentence case (the design system: English labels,
   plain words; a refusal or an empty state says what happened and what to do). Decision A (UD67 2A): the rotation map
   carries our own names: "Rotation map", "Relative strength", "Momentum". Decision D1: the weight's name comes from the
   files (meta.weight_label), never written here. Each "How to read" says what the card computes (defects W1-W4: the
   texts that no longer matched). */
import { dateLabel, fnum, pct, pctSigned, pp } from './model.ts';

const up1 = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;
const QW = { Leading: 'Leading', Weakening: 'Weakening', Lagging: 'Lagging', Improving: 'Improving' } as const;
/** a phone or tablet: the hints say tap, not hover, point or Ctrl click (check 1 MX-8); one source for every page (UD81) */
import { TOUCH, tap } from '../../shared/touch-words.ts';
export { TOUCH };
/** the single-sector cards' sector until one is locked */
const AUTO = 'the strongest sector this week until you lock one';
const turnUp = (corner: string | null) => (corner ? `${corner} = turning up: up over the shorter horizon, down over the longer.` : 'The two horizons have the same length.');

export const W = {
  page: {
    title: 'Sector Analysis',
    purpose: 'Which sectors started improving in the last few sessions, against IHSG and against each other.',
    loading: 'Loading the sector analysis',
  },
  tabs: { ov: 'Overview', rs: 'Relative strength', rot: 'Rotation', pm: 'Pair matrix', br: 'Breadth' },
  err: {
    offline: 'The sector analysis could not reach EDGE. Check the connection and reload the page.',
    signedOut: 'Your EDGE session ended. Sign in again, then open Sector Analysis.',
    unavailable: 'The sector analysis could not be read. Try again in a minute.',
    notPublished: 'A file of the sector analysis is not published. Reload the page.',
    boot: 'The sector analysis could not be shown. Reload the page; if it stays, the sector files are not published yet.',
    card: 'This card could not be drawn with the data of this date. Pick another date or reload the page.',
    date: 'That date could not be read. Try again.',
    noDate: 'The sector analysis has no published date yet. It appears after the next price update.',
    retry: 'Try again',
  },
  head: {
    prices: (d: string) => `Prices to ${d}`, pricesTip: 'Daily closes and every price figure',
    breadth: (d: string) => `Breadth to ${d}`, breadthTip: 'The shares of stocks above their EMA50 and EMA200',
    close: 'Close', latest: 'Latest', asOf: 'Data as of', none: 'No data',
    meta: (n: number) => `${n} IDX-IC sectors · benchmark`,
  },
  term: {
    open: 'Open in Terminal',
    headTip: (t: string) => `Open ${t} in the Terminal (the locked sector's index, else the market)`,
    rowTip: (t: string) => `Open ${t} in the Terminal`,
    set: (t: string) => `${t} is set for the Terminal. Open the Terminal page to see it.`,
  },
  kpi: {
    ihSub: 'Benchmark · vs 5 sessions earlier',
    beat: (m: string) => `Beating ${m}`, beatSub: 'Sectors with a 5D return above it',
    best: 'Strongest sector', bestSub: (m: string) => `5D return vs ${m}`, rank1: (n: number) => `rank 1 of ${n}`,
    imp: 'Improving', impTf: 'rotation', impSub: (m: string) => `Below ${m}'s trend, momentum turning up`,
    gain: 'Biggest rank gain', noGain: 'No sector moved up in rank over 5 sessions',
  },
  win: {
    expand: (t: string) => `Expand ${t}`, expandTip: 'Expand', close: 'Close window',
    howTo: 'How to read', example: 'Example', noRows: 'No rows for this selection.',
    na: 'No value: the files of this date do not give it for this row (a missing close, too few sessions, or no EMA yet)',
  },
  sort: {
    tip: tap('Click to sort · again to reverse · a third time to remove · click other columns to add sort levels (up to 3)', 'Tap to sort · again to reverse · a third time to remove · tap other columns to add sort levels (up to 3)'),
    by: (levels: string[]) => `Sorted by ${levels.join(', then ')}`, clear: 'Clear sort',
    byName: 'Sort by sector name', byCol: (h: string) => `Sort by ${h}`,
  },
  search: {
    stock: 'Search stock', pair: 'Search sector or pair',
    none: (q: string) => `No row matches “${q}”. Clear the search to see every row.`,
    shown: (n: number, of: number) => `${n} of ${of} shown`,
  },
  range: {
    title: 'Custom date range', from: 'From', to: 'To', compare: 'Compare with', cancel: 'Cancel', apply: 'Apply', custom: 'Custom',
    // check 1 OR-6, RP-1: the popover prints the card's own range, and a stored range is never replaced silently
    returnNote: 'A return is measured from the close of the session before From, as the Overview’s Custom.',
    // check 2 OV2-3: the range's printed start is the base close; the note names both dates, so the From field (the first
    // session) and the printed start agree in words
    fromClose: (base: string, first: string) => `Measured from the ${base} close, the session before From (${first}), as the Overview’s Custom.`,
    none: (k: string) => `The Custom range has no session up to this date: ${k} is shown.`,
    clampStart: (d: string) => `The Custom range starts before the data: shown from ${d}.`,
    clampEnd: (d: string) => `The Custom range ends after the date shown: shown to ${d}.`,
    noDate: (d: string) => `The compare date ${d} cannot be used with the date shown: 5D is shown.`,
  },
  above: 'Above', below: 'Below', close: 'Close',
  all: (m: string) => `${m} (all stocks)`,
  allShort: (m: string) => `${m} (all)`,
  vs: (x: string) => `vs ${x}`,
  cap: up1,
  sessions: (n: number) => plural(n, 'session'),
  stocks: (n: number) => plural(n, 'stock'),
  quad: QW,
  mom: { Gaining: 'Gaining', Steady: 'Steady', Fading: 'Fading' },
  heading: (h: string) => h,
  col: {
    sector: 'Sector', industry: 'Industry', ticker: 'Ticker', weight: 'Weight', stocks: 'Stocks', ret: 'Return',
    vs: (m: string) => `vs ${m}`, vsH: (m: string, h: string) => `vs ${m} ${h}`, vsSector: (h: string) => `${h} vs sector`, vsEma: (n: number) => `vs EMA${n}`,
    maxdd: 'Max drawdown', best: 'Best day', worst: 'Worst day', updays: 'Up days', reading: 'Reading', rank: (h: string) => `Rank ${h}`,
    avgRank: 'Avg rank', wshare: 'Weight share', up: (h: string) => `Up ${h}`, leader: 'Leader', leader5: 'Leader 5D', gained: 'Places gained',
    avgWeek: 'Avg week', ahead: 'Weeks ahead', bestWeek: 'Best week', worstWeek: 'Worst week', streak: 'Streak',
    quadrant: 'Quadrant', weeksIn: 'Weeks in', dStrength: 'Δ strength', dMomentum: 'Δ momentum', heading: 'Heading', direction: 'Direction',
    close: 'Close', weekEnding: 'Week ending', from: 'From', to: 'To', path: 'Path', pair: 'Pair', aheadRet: 'Ahead', behindRet: 'Behind',
    date: 'Date', cumSpread: 'Cum. spread', bandSd: 'Band (σ)', d: (h: string) => `Δ ${h}`, status: 'Status', change: (h: string) => `Change ${h}`,
    volume: 'Volume', days: 'Days', since: 'Since',
  },

  /* ---------- Overview ---------- */
  rc: {
    title: 'Cumulative return', sub: 'Return since the start of the period',
    togTip: (on: boolean) => (on ? `Coloured · ${tap('click', 'tap')} to set its line back to grey` : `Grey · ${tap('click', 'tap')} to colour its line`),
    ihTip: (on: boolean, m: string) => `${tap('Click', 'Tap')} to ${on ? 'hide' : 'show'} the ${m} line`,
    sectors: (n: number) => plural(n, 'sector'),
    hint: tap('Click a name to colour or grey its line · point at a sector in the list to highlight it', 'Tap a name to colour or grey its line'),
    many: 'Lines past the sixth colour are dashed',
    dTitle: 'Period statistics',
    read: (m: string) => `Return = change over the period; vs ${m} = sector return − ${m} return; max drawdown = the deepest fall from a peak inside the period; up days = the share of sessions that closed higher.`,
    // check 1 OR-9: "returned −11.3%", never "fell −11.3%"
    ex: (n: string, r: number | null, x: number | null, dd: number | null, m: string) => `${n} returned ${pct(r, 1)}, ${pp(x)} vs ${m}, so it did ${(x ?? 0) >= 0 ? 'better' : 'worse'} than ${m}; its deepest fall inside the period was ${pct(dd, 1)}`,
  },
  mm: {
    title: 'Momentum: horizon vs horizon', sub: 'Return over two horizons', xAxis: 'Horizontal axis', yAxis: 'Vertical axis', vs: 'vs',
    axis: (h: string) => `Return ${h}`,
    // check 1 OR-1: the corner names follow which axis holds the shorter horizon (M.hzRead)
    q: { both: 'Up on both', up: 'Turning up', down: 'Down on both', turn: 'Turning down' } as Record<string, string>,
    only: (h: string) => `Up on ${h} only`,
    topLeft: 'Top left', bottomRight: 'Bottom right',
    turnUp,
    foot: (corner: string | null, hid: boolean) => `Top right = up on both · ${corner ? `${corner.toLowerCase()} = turning up` : 'horizons of the same length'}` + (hid ? tap(' · point at a dot for names not shown', ' · tap a dot for names not shown') : ''),
    dTitle: (x: string, y: string) => `${x} vs ${y} by sector`, dSub: (x: string, y: string) => `Horizontal ${x} · vertical ${y}`,
    read: (corner: string | null) => `Each dot = a sector placed at its return over the horizontal horizon (across) and the vertical horizon (up). Top right = up on both. ${turnUp(corner)}`,
    ex: (n: string, x: number | null, y: number | null, X: string, Y: string, q: string) => `${n} is ${pct(x, 1)} over ${X} and ${pct(y, 1)} over ${Y} (“${q}”); the ${Y} return is ${(y ?? 0) - (x ?? 0) >= 0 ? 'higher' : 'lower'} than the ${X} return`,
  },
  hx: {
    title: 'Sector × horizon', sub: `Return per horizon · ${tap('click', 'tap')} a column header to sort`,
    foot: (m: string) => `Colour scaled per column · bottom row: ${m}`,
    na: (h: string) => `No ${h} return: the data hold no close at the start or the end of this horizon`,
    dTitle: (m: string) => `Excess return vs ${m}`, dSub: (m: string) => `Sector return − ${m} return per horizon (pp)`,
    read: (m: string) => `Each cell = sector return − ${m} return over that horizon, in percentage points; green = ahead of ${m}. Avg rank 1 = the strongest across horizons.`,
    ex: (n: string, v: number | null, ar: number | null, m: string) => `${n} 1M ${pp(v, 1)} = over one month it ${(v ?? 0) >= 0 ? 'beat' : 'trailed'} ${m} by that much; avg rank ${ar == null ? '—' : ar.toFixed(1)} = near the ${(ar ?? 6) <= 4 ? 'top' : 'bottom'} on most horizons`,
  },
  mk: {
    title: (s: string) => `${s} · market map`,
    // check 1 OR-12: "the strongest sector ... until you lock one" moved from the legend to the subtitle (one-line legends)
    sub: (w: string, m: string, locked: boolean) => `Tile size = ${w} · colour = 5D return − ${m} · grouped by industry` + (locked ? '' : ` · ${AUTO}`),
    foot: (n: number, k: number, floored: number) => `${plural(n, 'stock')} in ${plural(k, 'industry', 'industries')} · largest 10 per industry`
      + (floored ? ` · ${plural(floored, 'small industry', 'small industries')} drawn at a minimum size` : ''),
    empty: (s: string) => `No stock of ${s} has a weight and a 5D return on this date.`,
    gTip: (n: number, w: string, v: string, m: string) => `${plural(n, 'stock')} · ${w} · 5D vs ${m} (weighted) ${v}`,
    unclassified: 'Unclassified',
    dTitle: (s: string) => `${s} · industries`, dSub: (n: number) => `${plural(n, 'stock')} · 5D, weighted`,
    read: (w: string, m: string) => `Tile size = ${w}; colour = 5D return − ${m}. Weight share = the industry's part of the sector's weight; its 5D return is weighted the same way.`,
    ex: (n: string, sh: number | null, r5: number | null, x: number | null, top: string, tr: number | null, m: string) => `${n} takes ${sh == null ? '—' : sh.toFixed(1) + '%'} of the sector's weight; it moved ${pct(r5, 1)} in 5D (${pp(x)} vs ${m}), led by ${top} at ${pct(tr, 1)}`,
  },

  /* ---------- Relative strength ---------- */
  rsA: {
    title: 'Relative return', window: 'Window', abs: 'Absolute', sector: 'Sector', excess: 'Excess',
    sub: (rel: boolean, n: number, m: string) => (rel ? `Sector return − ${m} return over the last ${n} sessions (pp)` : `Sector index return over the last ${n} sessions · dashed line = ${m}`),
    rank: (k: number, n: number) => `Rank ${k} of ${n}`,
    foot: (rel: boolean, n: number, v: string, m: string) => (rel ? `${m} ${n}D ${v} is the zero line` : `${m} ${n}D ${v}`),
    dTitleRel: 'Relative return by window', dTitleAbs: 'Return by window', dSubRel: (m: string) => `Sector − ${m} (pp)`, dSubAbs: 'Sector index return',
    // check 1 OR-9: plain wording for the rank's window
    read: (rel: boolean, m: string, w: number) => (rel ? `Each value = sector return − ${m} return over that window, in percentage points; positive = ahead of ${m}. The rank column ranks the ${w}D window, the one picked on the card.` : `Each value = the sector index return over that window. The rank column ranks the ${w}D window, the one picked on the card.`),
    ex: (n: string, v: number | null, w: number, rk: number, rel: boolean, m: string) => (rel ? `${n} ${w}D ${pp(v)} = over the last ${w} sessions it ${(v ?? 0) >= 0 ? 'beat' : 'trailed'} ${m} by that much, rank ${rk} on ${w}D` : `${n} ${w}D ${pct(v)} = its index over the last ${w} sessions, rank ${rk} on ${w}D`),
  },
  rsB: {
    title: 'Rank change', up: 'Up 3+ places', down: 'Down 3+ places',
    sub: (n: number, d: string, m: string) => `Rank by ${n}D return vs ${m} · since ${d}`,
    popTitle: 'Compare with a date', pick: 'Pick a date.', before: 'Pick a date before the date shown.',
    starts: (d: string) => `Data starts ${d}. Pick a later date.`,
    note: (d: string, n: number) => `Compares the ranks of ${d} with the page's date, ${plural(n, 'session')} later`,
    tip: (a: number, d: string, b: number, x: number) => `Rank ${a} on ${d} → ${b} · ${x > 0 ? 'up ' + x : x < 0 ? 'down ' + -x : 'no change'}`,
    aria: 'Rank change slope chart', dTitle: 'Rank history', dSub: (n: number, m: string) => `Rank by ${n}D return vs ${m} on each date`,
    read: (n: number, d: string, m: string) => `Rank 1 = the highest ${n}D return vs ${m} on that date. Places gained = rank on ${d} − rank on the date shown (positive = moved up); the highlighted column is ${d}.`,
    ex: (n: string, a: number, d0: string, b: number, d1: string, x: number) => `${n} went from rank ${a} on ${d0} to rank ${b} on ${d1}, so ${x >= 0 ? 'up' : 'down'} ${plural(Math.abs(x), 'place')}`,
  },
  rsW: {
    title: 'Weekly excess return', sub: (m: string) => `Sector − ${m} return per 5-session week (pp)`,
    weekTo: (d: string) => `week to ${d}`, headTip: (d: string) => `5 sessions ending ${d}`,
    defOrder: (m: string) => `Order: 1M vs ${m} (default)`, foot: (n: number) => plural(n, 'week'),
    label: (range: string, n: number) => `${range} · ${plural(n, 'week')}`,
    maxWhy: (w: number) => `Pick at most ${w} weeks (${w * 5} trading days).`,
    dTitle: 'Weekly summary', weeks: (n: number) => plural(n, 'week'), up: (n: number) => `${n} ahead`, down: (n: number) => `${n} behind`,
    read: (m: string) => `Each week = sector return − ${m} return over 5 sessions. Weeks ahead = weeks with a positive gap; streak = the latest run of weeks ahead or behind.`,
    ex: (n: string, a: number | null, b: number, of: number, best: number | null, m: string) => `${n} averaged ${pp(a)} a week vs ${m} and was ahead in ${b} of ${of} weeks; its best week was ${pp(best)}`,
  },
  rsD: {
    title: 'Sector drill-down',
    sub: (m: string) => `Return, return vs ${m} and RS rating (1–99 rank of the 1M return vs ${m}) per sector · open a sector for its industries`,
    // check 1 D-1, D-4: an industry row is not the official index and is rated on another scale; said where both show
    indNote: (w: string, n: number) => `Sector rows are the official IDX sector index. Industry rows are EDGE's own index of their stocks, weighted by ${w}, so an industry can move unlike its sector. An industry's RS ranks it among all ${n} industries.`,
    openAll: 'Open all industries', closeAll: 'Close all industries',
    na: 'No value: the data hold no close at the start or the end of this period, or too few sessions for it',
    cols: { sn: 'Sector', r3d: '3D', r1: '1W', rM: '1M', r3: '3M', ry: 'YTD', rt: 'RS', d4: 'Δ 4W', ema: '> EMA50', qo: 'Rotation', mg: 'Momentum' },
    tips: {
      eM: 'Excess return, 1M (pp)', e3: 'Excess return, 3M (pp)', rt: 'RS rating 1–99: the rank of the 1M excess return; a sector among the 11 sectors, an industry among all industries',
      d4: 'RS rating now − RS rating 4 weeks (20 sessions) earlier', ema: 'Share of the stocks above their 50-day EMA (of the stocks that have one)',
      qo: 'Quadrant on the rotation map: Leading > Improving > Weakening > Lagging', mg: '1W excess − the average week of the 1M excess: Gaining above +0.5 pp, Fading below −0.5 pp',
    },
    momTip: (v: string) => `1W excess − the average week of the 1M excess: ${v} pp`,
    indTip: (n: string, k: number) => `${n} · ${plural(k, 'stock')} on this date · EDGE's index of its stocks, not an IDX index`,
    openInd: (n: string, open: boolean) => (open ? `Close the industries of ${n}` : `Open the industries of ${n}`),
    foot: (m: string) => `vs ${m} in pp · RS = rating 1–99`,
    dTitle: (s: string) => `${s} · stocks`,
    read: (m: string) => `Returns are the stock's own. 5D vs ${m} = stock 5D return − ${m} 5D return. EMA50 = the close above or below its 50-day average. ${tap('Click', 'Tap')} a ticker to open it in the Terminal.`,
    ex: (n: string, r5: number | null, x5: number | null, e50: 0 | 1 | null, m: string) => `${n} moved ${pct(r5, 1)} in 5D, ${pp(x5)} vs ${m}; it closes ${e50 == null ? 'without an EMA50 yet' : e50 ? 'above its EMA50' : 'below its EMA50'}`,
  },
  rsL: {
    title: (s: string) => `${s} · stocks`,
    sub: (d: string, locked: boolean) => `Return since ${d} · the 10 largest by weight` + (locked ? '' : ` · ${AUTO}`),
    foot: 'top/bottom 2 coloured',
    loading: 'Loading the stocks’ daily closes…',
    missing: (ex: boolean) => (ex ? 'The stock lines are not part of the example. Sign in or upgrade to see them.' : 'The stock lines of this sector are not published yet. They appear after the next sector update.'),
    failed: 'The stock lines could not be read. Try again in a minute.',
    none: (s: string) => `No stock of ${s} has daily closes for this period.`,
    index: (s: string) => `${s} index`,
    dTitle: (s: string) => `${s} · the 10 largest by weight`, dSub: 'The stocks drawn in the chart',
    read: 'Lines = each stock’s cumulative return from the start date, from its daily closes; the dashed line is the sector index. 5D vs sector = stock 5D − sector index 5D.',
    ex: (n: string, r5: number | null, vs: number | null) => `${n} moved ${pct(r5, 1)} in 5D, ${pp(vs)} vs its sector index, so it ${(vs ?? 0) >= 0 ? 'led' : 'lagged'} the sector over the week`,
  },

  /* ---------- Rotation ---------- */
  rot: {
    title: 'Rotation map', map: 'Map', timeline: 'Timeline', tail: 'Tail', xAxis: 'Relative strength', yAxis: 'Momentum', formula: 'Formula',
    sub: (m: string, d: string, tw: number) => `Relative strength × momentum vs ${m} · ${d} · tail ${tw}W`,
    subTl: (r: string, d: string) => `Quadrant of each sector per week · ${r} · outlined = ${d}`,
    ihTip: (on: boolean, m: string) => (on ? `Hide the ${m} chart` : `Show the ${m} chart`),
    formulaTip: (m: string) => `Relative strength = 100 × (sector ÷ ${m}) ÷ its 20-session mean; momentum = 100 × relative strength ÷ its value 5 sessions earlier. Above 100 = above its own recent level.`,
    weekEnding: (d: string) => `week ending ${d}`,
    reading: (x: number, y: number) => `Relative strength ${x.toFixed(2)} · momentum ${y.toFixed(2)}`,
    clickPin: tap('Click to lock the sector', 'Tap to lock the sector'), aria: 'Rotation map of the sectors', tlAria: 'Quadrant timeline of the sectors',
    foot: (hid: boolean) => tap(`Click a dot to lock the sector · ${hid ? 'point at a dot for names not shown' : 'point at a dot for its values'}`, 'Tap a dot to lock the sector and read its values'),
    noData: 'Not enough sessions for the rotation map on this date. Pick a later date.',
    stripLabel: (d: string, lvl: string, chg: string, tl: boolean, short = false) => `${d} · ${lvl} · ${chg}` + (short ? '' : ` over ${tl ? 'the period' : 'the tail'}`),
    stripAria: (m: string) => `${m} weekly close; ${tap('click', 'tap')} a week to set the map date`,
    // check 1 RP-6: the hover names the date a click sets (a week too early for the tail sets the first possible one)
    weekOf: (m: string, d: string) => `${m} · week to ${d}`, oneWeek: '1 week',
    tooEarly: (d: string) => `Too early for this tail: a ${tap('click', 'tap')} sets the first map date with a full tail, ${d}`, setDate: (d: string) => tap(`Click to set the map date to ${d}`, `Tap to set the map date to ${d}`),
    inPhase: (s: string, k: string, q: string, d: string) => `${s}: ${k} weeks in ${q} as of ${d}`, phase: 'in phase',
    dTitle: (d: string) => `Rotation readings · ${d}`, dSub: 'One row per sector at the map date · Δ = change over 5 sessions',
    read: (m: string) => `Relative strength above 100 = stronger than its own recent level against ${m}; momentum above 100 = that strength is rising. Leading = both above 100, lagging = both below.`,
    ex: (n: string, rs: number | null, mo: number | null, q: string | null, m: string) => `${n}: relative strength ${fnum(rs)} (${(rs ?? 0) >= 100 ? 'stronger' : 'weaker'} than its recent level vs ${m}) and momentum ${fnum(mo)} (${(mo ?? 0) >= 100 ? 'gaining' : 'losing'} strength) → ${q ? q.toLowerCase() : '—'}`,
  },
  rotD: {
    title: 'Rotation direction and speed', window: 'Window', sort: 'Sort', angle: 'Angle', speed: 'Speed',
    sub: (nw: number, d: string) => `The move on the map over ${nw === 1 ? 'the week' : nw + ' weeks'} to ${d} · 0–90° = strengthening`,
    tip: (deg: string, sp: string, nw: number) => `Direction ${deg}° · speed ${sp} over ${nw}W`,
    deltas: (dx: string, dy: string) => `Δ strength ${dx} · Δ momentum ${dy}`,
    click: tap('Click to highlight · Ctrl or Cmd click to add', 'Tap to highlight'),
    foot: 'Arrow = the move on the map; length = speed; 0° = strength rising, 90° = momentum rising',
    dTitle: 'Direction and speed', dSub: (nw: number, d: string) => `The move over ${plural(nw, 'week')} to ${d}`,
    read: '0° = relative strength rising only, 90° = momentum rising only, 180° and 270° = falling; speed = the length of the move on the map.',
    ex: (n: string, deg: number | null, sp: number | null, hd: string) => `${n} points ${deg == null ? '—' : deg.toFixed(0) + '°'} (${hd.toLowerCase()}) at a speed of ${sp == null ? '—' : sp.toFixed(2)}`,
  },
  rotB: {
    title: 'Rotation detail', previous: 'Previous', now: 'Current quadrant', last: 'Last change', from: 'from', same: 'Same quadrant', clear: 'Clear',
    // check 1 RP-3: the card follows the map date picked on the strip and says so
    sub: (pl: string, pk: number, on: string | null) => (on ? `Quadrant on ${on} (the map date) vs ${pl} earlier` : `Quadrant now vs ${pl} ago`) + ` · speed = distance moved on the map in ${pk} sessions`,
    ago: (h: string) => `${h} ago`, prev: (pl: string) => `Previous (${pl} ago)`,
    qoTip: 'Leading > Improving > Weakening > Lagging', poTip: (d: string) => `Quadrant on ${d}`,
    spTip: (pk: number) => `Distance moved on the map over ${pk} sessions`, liTip: 'Sorted by the date of the last quadrant change',
    rowTip: tap('Click to highlight on the map · Ctrl or Cmd click to add', 'Tap to highlight on the map'),
    defOrder: 'Order: momentum change over 3 sessions (default)',
    highlighted: (n: number) => `${n} highlighted on the map`, hint: tap('Click a sector to highlight it on the map (Ctrl or Cmd click to add)', 'Tap a sector to highlight it on the map'),
    // check 1 MX-8: a window shows no map
    selected: (n: number) => `${n} selected`, rowTipWin: tap('Click to choose · Ctrl or Cmd click to add', 'Tap to choose'),
    speedFoot: (pk: number) => `Speed = distance moved in ${pk} sessions`,
    cw: 'Clockwise', skip: 'Skipped or reversed',
    // the window (C1, user 2026-11-27): a list of the sectors beside their quadrant changes, or all the card's columns
    sectors: 'Sectors', nowShort: 'Now', hintC1: tap('Click to choose · Ctrl or Cmd click to add', 'Tap to choose'),
    changes: 'Changes', allCols: 'All columns', allTitle: 'All sectors',
    allSub: (pl: string, pk: number) => `Quadrant now vs ${pl} ago · speed = distance moved on the map in ${pk} sessions`,
    readAll: (pk: number) => `The card's table with every column: the quadrant at the map date and the chosen sessions earlier, the speed (distance moved on the map in ${pk} sessions) and the last change of quadrant. Choose a sector for its quadrant changes.`,
    exAll: (n: string, q: string, sp: number | null) => `${n} is ${q.toLowerCase()} now and moved ${sp == null ? '—' : sp.toFixed(2)} on the map`,
    dSubC1: (n: number, w: number, names: string[]) => `${plural(n, 'change')} in ${w} weeks · ${names.join(', ')}`,
    noChange: (w: number) => `No change of quadrant in ${w} weeks for this choice.`,
    dTitle: 'Quadrant changes',
    read: 'Each row = a week in which a sector moved to another quadrant. Clockwise = the usual Lagging → Improving → Leading → Weakening order.',
    ex: (d: string, n: string, f: string, t: string, cw: boolean) => `in the week ending ${d}, ${n} moved from ${f.toLowerCase()} to ${t.toLowerCase()}: ${cw ? 'the usual order' : 'not the usual order (it skipped a quadrant or went back)'}`,
  },
  rotC: {
    title: (s: string) => `${s} · stock momentum quadrant`, rel: 'Relative to', secIndex: 'Sector index',
    sub: (bn: string, asOf: string | null) => `Dot = stock · across = 1M − ${bn}, up = 5D − ${bn} (pp) · size = weight · green = 5D above ${bn}` + (asOf ? ` · as of ${asOf}, the page's date (stock returns are the day's)` : ''),
    index: (s: string) => `${s} index`, xAxis: (bn: string) => `1M vs ${bn}`, yAxis: (bn: string) => `5D vs ${bn}`,
    beyond: 'Beyond the axis range: drawn hollow at the edge', aria: (s: string) => `Stock momentum quadrant of ${s}`,
    none: (s: string) => `No stock of ${s} has a 1M and a 5D return on this date.`,
    dTitle: (s: string) => `${s} · stocks by quadrant`,
    read: 'Across = 1M return − benchmark 1M, up = 5D return − benchmark 5D (pp), both over the same sessions. Leading = ahead on both; improving = behind on 1M but ahead on 5D.',
    ex: (n: string, a: number | null, b: number | null, q: string) => `${n} is ${pp(a)} vs the benchmark over 1M ${((a ?? 0) >= 0) === ((b ?? 0) >= 0) ? 'and' : 'but'} ${pp(b)} over 5D → ${q.toLowerCase()}`,
  },

  /* ---------- Pair matrix ---------- */
  pmM: {
    title: 'Sector pair matrix', spread: 'Spread', corr: 'Correlation', leaderFirst: 'leader first',
    subSp: (hz: string) => `Return row − return column, ${hz} (pp) · green = row ahead · ${tap('click', 'tap')} a cell to open the pair`,
    subCo: (w: number) => `Correlation of daily returns, ${w}D · darker = moves together · ${tap('click', 'tap')} a cell to open the pair`,
    sortBy: (y: string) => `Sort rows by ${y}`, isB: (s: string) => `${s} is already B in the pair ratio`, makeA: (s: string) => `Make ${s} sector A of the pair`,
    // user decision UD79 1A: the chosen sector, cell or pair clicked again: no pair chosen (the automatic pair shows)
    unA: (s: string) => `${s} is sector A · ${tap('click', 'tap')} again to choose no pair`, unPair: tap('Click again to choose no pair', 'Tap again to choose no pair'),
    corrW: (w: number) => `Corr ${w}D`, open: tap('Click to open in the pair ratio', 'Tap to open in the pair ratio'),
    footSp: `Value = row return − column return (pp), not a ratio · rows and columns ordered by return · ${tap('click', 'tap')} column names to sort rows (each adds a level)`,
    // check 1 RP-7: in Correlation the order follows the shown window, and a negative value has its own colour
    footCo: `1.00 = identical daily moves · 0 = unrelated · red = opposite moves · ordered by average correlation · ${tap('click', 'tap')} column names to sort rows`,
    dTitle: (n: number) => `All ${n} pairs`,
    read: 'Spread = return of the sector ahead − return of the sector behind over the matrix period (pp). Corr near 1 = the two move together.',
    ex: (a: string, ra: number | null, b: string, rb: number | null, s: number | null, c: number | null) => `${a} returned ${pct(ra, 1)} and ${b} ${pct(rb, 1)}, a spread of ${pp(s)}; corr ${fnum(c)} = they ${(c ?? 0) >= 0.6 ? 'often' : 'rarely'} move together`,
  },
  pmR: {
    sub: 'A ÷ B, start = 100 · line up = A ahead',
    subAuto: 'Automatic pair: the one furthest from its 60-session mean · A ÷ B, start = 100 · line up = A ahead',
    auto: 'Automatic', autoTip: 'No pair is chosen, so this is the pair whose ratio is furthest from its 60-session mean. Choose a sector, a cell or a pair to show another.',
    period: 'period', a: 'Sector A', b: 'Sector B', swap: 'Swap A and B',
    spreadK: (pl: string) => `Spread ${pl} (A − B)`, band: 'Band position', ratio: 'Ratio',
    pos: (p: string, pb: number | null) => (p === 'up' ? 'Above the upper band · stretched' : p === 'dn' ? 'Below the lower band · stretched' : `Inside the band · ${Math.round(pb ?? 0)}% of its width`),
    lineA: 'A / B (start = 100)', bandL: '±2σ band',
    moved: (d: string, ma: number) => `Start moved to ${d}: the MA${ma} needs ${ma} sessions before it`,
    none: 'Not enough sessions for this pair and period. Pick a shorter MA or a later start.',
    aria: (a: string, b: string) => `Ratio of ${a} to ${b} with its moving average and band`,
    dTitle: (a: string, b: string) => `${a} / ${b} · daily log`, dSub: (n: number, ma: number) => `Last ${plural(n, 'session')} · MA${ma} band`,
    read: `Spread = A daily return − B daily return. Ratio = A ÷ B rebased to 100. A band reading beyond ±2σ = the ratio is unusually stretched from its moving average. ${tap('Click', 'Tap')} a date to mark it on the chart.`,
    ex: (d: string, a: string, ra: number | null, b: string, rb: number | null, sp: number | null, z: number | null) => `on ${d}, ${a} ${pct(ra)} and ${b} ${pct(rb)} → spread ${pp(sp)}; band ${fnum(z)} = ${Math.abs(z ?? 0) >= 2 ? 'stretched' : 'within the usual range'}`,
  },
  pmT: {
    title: (bm: string) => `Beta and correlation to ${bm}`, window: 'Window', vs: 'vs', beta: 'Beta', dBeta: 'Δ beta', corr: 'Corr', alpha: 'Alpha',
    sub: (bm: string, l: string) => `β = sector move per 1% ${bm} move, from ${l} daily returns · corr = how closely they move`,
    dBetaTip: 'Beta now − beta over the previous window of the same length (— when the 300 sessions hold no such window)', retTip: 'Sector return over the window',
    // check 1 RP-8: the reason of a dash
    dBetaNa: (w: string) => `No Δ beta: the 300 sessions of data hold no previous ${w} window before this one`,
    exTip: (bm: string) => `Sector return − ${bm} return over the window (pp)`, alTip: (bm: string) => `Return not explained by ${bm}: sector return − beta × ${bm} return (pp)`,
    rowTip: (s: string) => `${tap('Click', 'Tap')} to make ${s} sector A of the pair`, rowUnTip: (s: string) => `${s} is sector A · ${tap('click', 'tap')} again to choose no pair`,
    autoA: 'sector A of the automatic pair (no pair chosen)',
    foot: (bm: string, v: string) => `A / B = the pair in the pair ratio · ${tap('click', 'tap')} a row to make it A, again to choose no pair · dashed line = beta 1.0 · Δ beta red = more sensitive than before · ${bm} ${v} in the window`,
    dTitle: (s: string) => `${s} · stocks`, dSub: (l: string, bm: string, sb: string) => `β ${l} vs ${bm} from each stock's daily closes · sector β ${sb}`,
    loading: 'Loading the stocks’ daily closes for their beta…', missing: 'The stocks’ daily closes of this sector are not published: their beta and correlation are not shown.',
    read: 'β = how much the stock moves per 1% move in the benchmark, from its daily closes over the window; corr near 1 = it moves closely with the benchmark.',
    ex: (n: string, b: number | null, c: number | null) => (b == null ? `${n} has no beta for this window` : `${n} β ${fnum(b)}: when the benchmark moves 1%, ${n} tends to move about ${fnum(b)}%; corr ${fnum(c)}`),
  },
  pmS: {
    title: 'Stretched pairs', rank: 'Rank by', all: 'All', still: 'Leader still ahead', turning: 'Leader behind', show: 'Show', allRows: 'All',
    sub: (h: string) => `Pairs ranked by their return gap over ${h} · each pair reads its 1M leader first (pp)`,
    disabled: 'Ranked by 1M: every pair has its leader ahead', top: (n: number) => `Top ${n}`,
    abs: (h: string) => `|Spread ${h}|`, sp: (h: string) => `Spread ${h}`, rowTip: tap('Click to open in the pair ratio', 'Tap to open in the pair ratio'), rowUnTip: tap('Click again to choose no pair', 'Tap again to choose no pair'),
    defOrder: (h: string) => `Order: |spread ${h}| (default)`,
    foot: (n: number | null, tot: number) => (n == null ? `${plural(tot, 'pair')} · spread = A − B (pp)` : `Top ${n} of ${tot} · spread = A − B (pp)`),
    dTitle: 'Spread across horizons',
    // the window: the card's Rank by, filter and Show rank, filter and limit this table (user 2026-11-27, V7 answers 1-3)
    dSubWin: (shown: number, n: number, all: number, rk: string, filtered: boolean) => `${shown < n ? `Top ${shown} of ${n}` : plural(n, 'pair')}${filtered ? ` (of ${all})` : ''} · ranked by |spread ${rk}| · 1M leader first (pp)`,
    noneTop: (q: string, n: number) => `No pair of the top ${n} matches “${q}”. Choose Show: All to search every pair.`,
    read: 'Each column = the first sector’s return − the second’s over that horizon (pp); the first is the one ahead over 1M. Same sign across = a steady gap; a sign flip = the gap is turning.',
    ex: (a: string, b: string, s: number | null, s1: number | null) => `${a} beat ${b} by ${pp(s, 1)} over 1M, and the 1D gap is ${pp(s1, 1)}`,
  },

  /* ---------- Breadth ---------- */
  brH: {
    title: 'Breadth vs price', show: 'Show', above: '% above', period: 'Period', main: 'Main', setMain: 'Set main', vs5: 'vs 5 sessions',
    sub: (sec: string | null, lab: string, m: string) => `% of ${sec ? sec : 'all'} stocks closing above their ${lab} · ${m} price on the right`,
    showAria: (names: string[]) => `Lines shown: ${names.join(', ')}`, showHead: (n: number) => `Show up to 5 lines · ${n} of 5`,
    showFoot: 'The main line (ink) also sets the selection of the other breadth cards',
    head: (lab: string, d: string) => `above ${lab} on ${d}`,
    legTip: (n: string, v: string, lab: string, d: string) => `${n}: ${v.replace('+', '')} above ${lab} on ${d}`,
    pxTip: (m: string) => `${m} index level, right axis`, hideTip: (t: string, hidden: boolean) => `${t} · ${tap('click', 'tap')} to ${hidden ? 'show' : 'hide'}`,
    price: (m: string) => `${m} price (right)`, aria: (lab: string) => `% of stocks above ${lab}; the mouse wheel or + and − zoom, the arrow keys move`,
    foot: (hi: number, lo: number, ex: boolean) => `Green zone ≥ ${hi}% · red zone ≤ ${lo}%` + (ex ? '' : tap(' · scroll to zoom, drag to move', ' · + and − zoom')),
    zone: (v: number | null, hi: number, lo: number) => (v == null ? '' : v >= hi ? 'Strong zone' : v <= lo ? 'Weak zone' : 'Neutral zone'),
    dTitle: (w: string) => `${w} · daily log`, dSub: (n: number, ms: number) => `Last ${plural(n, 'session')} · % above EMA${ms}`,
    read: `The share of stocks closing above their moving average (of the stocks that have one); 70% or more = strong, 30% or less = weak. Δ = change in percentage points. ${tap('Click', 'Tap')} a date to mark it on the chart.`,
    ex: (d: string, b: number | null, ms: number, d5: number | null) => `on ${d}, ${b == null ? '—' : b.toFixed(1) + '%'} of the stocks closed above their EMA${ms}; Δ 5D ${pp(d5, 1)} = ${(d5 ?? 0) >= 0 ? 'more' : 'fewer'} stocks above it than 5 sessions earlier`,
  },
  brT: {
    title: 'Breadth heatmap table', show: 'Show', count: 'Stock count', dl: 'Δ EMA50 1W', shown: 'Already shown', na: 'No value: no stock of this group has this figure on this date',
    sub: '% of stocks up over 1D, 1W and 1M, and above their EMA50 and EMA200 · green ≥ 50%',
    dx: (ms: number, hz: string) => `Δ EMA${ms} ${hz}`,
    // check 1 D-2, BD-6: Up 1D is Feature 08's count (= the Overview); Up 1W and 1M say their denominator
    cellTip: (n: number, N: number, v: number, of: number | null, hz: string | null) => `${n} of ${N} stocks · ${v.toFixed(1)}%` + (hz && of != null && of > N ? ` · ${of - N} of the ${of} stocks have no ${hz} return and are not counted` : ''),
    colTip: (k: string) => (k === 'u1' ? 'Share of the stocks that closed above their own previous close (as the Overview)' : k.startsWith('u') ? 'Share of the stocks with a return above 0, of the stocks that have that return' : 'Share of the stocks closing above that average (of the stocks that have one)'),
    dlTip: 'Change in % of stocks above EMA50 over 5 sessions (pp)',
    dxTip: (ms: number, hz: string) => `Change in % of stocks above EMA${ms} over ${hz} (pp)`,
    addCol: (n: number) => `+ Column${n ? ' · ' + n : ''}`, addAria: 'Add columns', addHead: 'Change in % of stocks above',
    foot: tap('Hover a cell for the stock count', 'Tap a cell for the stock count') + ' · Δ = change in % above EMA50 over 1 week',
    // check 1 D-7: the market row's stocks without a sector
    other: (m: string, k: number) => `${m} (all) also counts ${plural(k, 'stock')} without an IDX-IC sector, which no sector row shows`,
    dTitle: 'Breadth change', dSub: '% of stocks above EMA50 and EMA200, now and its change',
    read: '> EMA50 / > EMA200 = the share of the stocks closing above that average; Δ = change in percentage points over 1W and 1M.',
    ex: (n: string, a: number | null, d: number | null) => `${n}: ${a == null ? '—' : a.toFixed(1) + '%'} of its stocks are above EMA50, ${pp(d, 1)} vs a week earlier`,
  },
  brA: {
    title: 'Breadth by sector', measure: 'Measure',
    sub: (md: string, ih5: string, m: string, d: string) => (md === 'ema' ? `% of each sector's stocks above their EMA50 on ${d}` : md === 'ihsg' ? `% of each sector's stocks with a 5D return above ${m} (${ih5})` : `% of each sector's stocks with a positive 5D return`),
    tip: (a: number, n: number, v: string, md: string, ih5: string, m: string) => `${a} of ${n} stocks ${md === 'ema' ? 'with an EMA50' : 'with a 5D return'} · ${v}% · ${md === 'ema' ? 'above their EMA50' : md === 'ihsg' ? `5D return above ${m} (${ih5})` : 'a positive 5D return'}`,
    foot: 'Green dot = more than half the stocks · ' + tap('hover a row for the stock count', 'tap a row for the stock count'),
    dTitle: (w: string) => `${w} · stocks`, dSub: (a: number, n: number, b: number) => `${a} of ${n} above EMA50 · ${b} above EMA200`,
    read: '> EMA50 / > EMA200 = the stock closes above that average; vs EMA50 = how far the close is from it (close ÷ EMA50 − 1).',
    ex: (n: string, d: number | null) => `${n} closes ${pctSigned(d, 1)} from its EMA50, so it is ${(d ?? 0) > 0 ? 'above' : 'below'} it`,
  },
  brN: {
    title: 'Advancers and decliners', period: 'Period', up: 'Up', flat: 'Unchanged', down: 'Down', half: 'Tick = 50%',
    sub: (h: string, den: string) => `Stocks up, flat and down over ${h} · sorted by share up · ${den}`,
    hz: { r1d: '1D', r5d: '1W', r1m: '1M' } as Record<string, string>,
    tip: (u: number, f: number, d: number, N: number, of: number | null, hz: string) => `Up ${u} · flat ${f} · down ${d} of ${N}` + (of != null && of > N ? ` · ${of - N} of the ${of} stocks have no ${hz} return` : ''),
    // check 1 D-2, BD-6: 1D as the Overview; 1W and 1M say who is counted
    den1d: '1D vs each stock’s own previous close',
    den: (hz: string, N: number, of: number) => (N < of ? `${N} of ${of} stocks have a ${hz} return` : `every stock has a ${hz} return`),
    dNote: (k: number) => `${plural(k, 'stock')} did not trade on the previous session: counted against ${k === 1 ? 'its' : 'their'} own last close, shown “—” here.`,
    adv: 'Up', dec: 'Down', unch: 'Flat',
    dTitle: (w: string, h: string) => `${w} · stocks ${h}`, dSub: (u: number, f: number, d: number) => `${u} up · ${f} unchanged · ${d} down`,
    read: 'Status = the stock’s move over the chosen period: up, flat or down. 1D compares each stock with its own previous close (as the Overview); 1W and 1M count the stocks that have that return. Close and volume are the day’s.',
    ex: (n: string, c: string, r: number | null, s: number | null) => `${n} closed at ${c}, ${pct(r)} → ${s == null ? 'not counted' : s > 0 ? 'up' : s < 0 ? 'down' : 'flat'}`,
  },
  brD: {
    title: 'Stock detail', status: 'Status', all: 'All', dist: 'Distance from EMA', empty: 'No stock in this selection.',
    sub: (w: string, a: number, N: number, lab: string) => `Close vs EMAs · ${w}: ${a} of ${N} above ${lab}`,
    statusTip: (lab: string) => `Above or below ${lab}`, distTip: (n: number) => `Close vs EMA${n}, %`,
    // check 1 D-3: Days counts market sessions from Since, so the two agree for a thinly traded stock
    daysTip: (lab: string) => `Market sessions in the current status vs ${lab}, from Since to the date shown (300+ = at least 300)`, sinceTip: (lab: string) => `First session of the current status vs ${lab}`,
    // check 1 BD-11: the reason of a dash
    sinceNa: 'The status is older than the 300 sessions of data', distNa: (n: number) => `No EMA${n} yet: fewer than ${n} sessions of history`,
    more: (n: number) => `at least ${n}: the status began before the 300 sessions of data`,
    // check 2 BD2-3: a status older than the data has no start date; the sentence says so instead of "since <reason>"
    tip: (ab: 0 | 1 | null, lab: string, days: string, since: string | null) => (ab == null ? `No ${lab} yet` : `${ab ? 'Above' : 'Below'} ${lab} for ${days} sessions${since ? `, since ${since}` : ': the status began before the 300 sessions of data'}`),
    dists: (a: string, b: string) => `Close vs EMA50 ${a} · EMA200 ${b}`,
    foot: (lab: string) => `Distance = close vs EMA · status uses ${lab}, the “% above” of Breadth vs price · ${tap('click', 'tap')} a stock to open it in the Terminal`,
  },
};
export const fmtDate = dateLabel;
