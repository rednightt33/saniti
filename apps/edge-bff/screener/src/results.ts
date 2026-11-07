/* Card 3: the results (the prototype's renderResults, sortedRows, visibleRows, toggleWatch, exportCsv), on the run's
   rows, or on the universe rows while the screen has no condition (report 6c.4 S5). Kept: meta line, near toggle,
   search, columns, sort, pagination, selection and bulk bar, empty states. Changed (report 9.2): real values with cell
   tooltips (evaluation date, event date, bars ago, NA reason, cell remark); a Remark column when a shown row carries a
   remark (P4); Mkt cap (no data) is not a column since v21: it is listed with its reason under "Not available yet"; the default tie-break is ADV20; pagination
   returns to page 1 only when the row set or its order changes; rows are keyboard-reachable; aria-sort on sortable
   headers; the watchlist is the server's (P12 a). Sort, page, search, near toggle and CSV never call the server. */
import type { Cell } from './core/contract.ts';
import { esc, fmtValue, nf, sectorTag, sgn, slug, tone } from './format.ts';
import { IC, ico } from './icons.ts';
import { activeCards, ctx, entryOf, evalDate, freshUniverse, S, ui, type Row } from './state.ts';
import { condText, isCustom, optOf, paramSummary, shortName, shortPv, type Card } from './forms.ts';
import { cellTitle, chg1dBreakText, extraCellView, extraColumnTitle, remarkBadge, remarkTitle, staleValueText, T } from './texts.ts';
import { formatOfOpt, formatOfSide } from './entries.ts';
import { pageCardOf, screenedCards } from './run.ts';
import { colorOf } from './builder.ts';
import { csvText, metaOf } from './csv.ts';
import { toast } from './dialogs.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { ApiFailure } from './api/types.ts';
import { availableColumns, extraCell, extraSortKey, shownColumns, type ExtraColumnDef } from './extra-columns.ts';
import { applyTable } from './layout/table.ts';
import { layoutHooks } from './layout/prefs.ts';
import { afterPress } from './press.ts';
import { keepField } from './keep-field.ts';
import { cellText, kindOfCard as kindOf } from './cell-text.ts';

const $ = (id: string) => document.getElementById(id)!;

/** the cell of a condition on a row */
export const cellOf = (r: Row, id: string) => r.cells.find(c => c.id === id);
/** a cell's sort key (report 6.9 Sort): the value for VALUE, pass then lhs for STATE, 1000 − bars_ago for EVENT; null last */
export function cellKey(c: Cell | undefined, kind: string | undefined): number | null {
  if (!c || c.status === 'na' || c.status === 'not_evaluated') return null;
  if (kind === 'event') return c.bars_ago == null ? (c.status === 'pass' ? 1000 : null) : 1000 - c.bars_ago;
  if (kind === 'state') return (c.status === 'pass' ? 1 : 0) * 1e15 + (c.lhs ?? 0) / 1e3;
  return c.value ?? null;
}
const kindOfCard = (c: Card) => kindOf(c, entryOf(c));
function rowVal(r: Row, key: string): number | string | null {
  switch (key) {
    case 'match': return r.met + (r.status === 'match' ? 100 : 0);
    case 'sym': return r.ticker;
    case 'last': return r.last;
    case 'd1': return r.chg_1d_pct;
    case 'adv': return r.adv20_idr;
  }
  const id = key.slice(2);
  if (id.startsWith('x:')) return extraSortKey(r.ticker, id.slice(2));    // an extra column (extra-columns.ts)
  const c = screenedCards().find(x => x.id === id);          // the table's conditions, not pending edits (EXEC-SCREENER-V21)
  return cellKey(cellOf(r, id), c ? kindOfCard(c) : undefined);
}
/** the shown rows in the current sort: matches always above near rows; nulls last in both directions; ties by ADV20
    descending, then ticker (report 6.9; the prototype's market-cap tie-break has no data) */
export function sortRows(list: Row[], sort: { key: string; dir: 'asc' | 'desc' }): Row[] {
  const d = sort.dir === 'desc' ? -1 : 1;
  return [...list].sort((a, b) => {
    if ((a.status === 'match') !== (b.status === 'match')) return a.status === 'match' ? -1 : 1;
    const x = rowVal(a, sort.key), y = rowVal(b, sort.key);
    if (x !== y) {
      if (x == null) return 1; if (y == null) return -1;
      const c = (typeof x === 'string' ? x.localeCompare(y as string) : x - (y as number)) * d;
      if (c) return c;
    }
    const av = (b.adv20_idr ?? -Infinity) - (a.adv20_idr ?? -Infinity);
    return av || a.ticker.localeCompare(b.ticker);
  });
}
export function visibleRows(): Row[] {
  const R = ctx.R; if (!R) return [];
  const screen = !!R.run && R.run.mode === 'screen';
  const list = screen ? R.rows.filter(r => r.status === 'match' || (S.nearMiss && r.status === 'near')) : R.rows;
  const q = S.q.trim().toLowerCase(), all = sortRows(list, S.sort);
  return q ? all.filter(r => (r.ticker + ' ' + (r.name || '')).toLowerCase().includes(q)) : all;
}

/* the page returns to 1 only when the row set or its order changes (report 9.2) */
let orderKey = ''; let lastOrder = '';
const orderOf = () => `${ctx.R?.defHash}|${ctx.R?.run?.versions.price_data}|${S.q}|${S.nearMiss}|${S.sort.key}|${S.sort.dir}`;

/** A condition's cell. The value is written in the format the catalog gives the condition's output or metric
    (entries.ts formatOfOpt), never from the wire's coarse Cell.unit ('dimensionless' for a percent: data audit D-1). */
function cellHtml(r: Row, c: Card): string {
  const x = cellOf(r, c.id), e = entryOf(c), o = e && optOf(e, c), kind = kindOfCard(c);
  if (!x) return `<td class="fail" title="Not in this result"><span>—</span></td>`;
  // the one cell text (cell-text.ts): an event that did not happen within reach fails as "No", like a state (user
  // 2026-11-06: "Dengan tulisan no"); one that happened, but earlier than the window, keeps "N sessions ago"
  const txt = cellText(e, c, x);
  const side = formatOfSide(e, o);
  const tip = [
    kind === 'state' && x.lhs != null ? `${fmtValue(x.lhs, side)} vs ${fmtValue(x.rhs, side)}` : '',
    cellTitle(x, r.remarks, evalDate()),
  ].filter(Boolean).join('\n');
  const mark = x.remark ? ` <i class="rmk" aria-label="Distorted value">${ico(IC.warn, 's')}</i>` : '';
  return `<td class="${x.status === 'pass' ? '' : 'fail'}" title="${esc(tip)}"><span>${esc(txt)}</span>${mark}</td>`;
}
/* ---- EXEC-SCREENER-V21 extra columns: header and cells from extra-columns.ts, nothing computed here ---------- */
const extraDefs = (): ExtraColumnDef[] => { const all = new Map(availableColumns().map(d => [d.id, d])); return shownColumns().map(id => all.get(id)).filter((d): d is ExtraColumnDef => !!d) };
function extraTh(d: ExtraColumnDef, sortTh: (key: string, label: string, cls?: string, title?: string) => string): string {
  const title = `${extraColumnTitle(d.label, d.format, d.paramText)}\nDrag to move`;
  return sortTh('c:x:' + d.id, `<b class="xbadge">${esc(d.short || d.label)}</b>`, 'xcol g-' + slug(d.group).split('-')[0], title)
    .replace('<th ', `<th data-xid="${esc(d.id)}" `)
    .replace(/<\/th>$/, `<button type="button" class="xcol-x" data-xdel="${esc(d.id)}" aria-label="Remove column ${esc(d.label)}" title="Remove column">×</button></th>`);
}
/** An extra column's cell: the worker's cell of a value test, in the column's catalog format (texts.ts extraCellView),
    never the test's pass or fail; NA with its reason, loading, failed or missing are never written as a number. */
function extraTd(r: Row, d: ExtraColumnDef): string {
  const st = extraCell(r.ticker, d.id);
  if (st.kind === 'loading') return `<td class="xcol" title="Loading this column">${spin('')}</td>`;
  const v = extraCellView(st, d.format, r.remarks, evalDate());
  const mark = v.mark ? ` <i class="rmk" aria-label="Distorted value">${ico(IC.warn, 's')}</i>` : '';
  const hid = st.kind === 'error' ? `<span class="vh">${esc(v.title)}</span>` : '';
  return `<td class="xcol${v.muted ? ' muted' : ''}${v.tone ? ' ' + v.tone : ''}" title="${esc(v.title)}"><span>${esc(v.text)}</span>${mark}${hid}</td>`;
}

export function renderResults() {
  if (afterPress('results', renderResults)) return;   // never under a pressed pointer (press.ts, ERRORS M357)
  // the condition columns are the table's own conditions (the definition it answers), not the page's pending edits
  const R = ctx.R, A = screenedCards(), screen = !!R?.run && R.run.mode === 'screen';
  const rows = visibleRows(), ok = orderOf();
  if (ok !== orderKey) { orderKey = ok; S.page = 1 }
  const pages = Math.max(1, Math.ceil(rows.length / S.perPage)); S.page = Math.min(Math.max(1, S.page), pages);
  const pr = rows.slice((S.page - 1) * S.perPage, S.page * S.perPage);
  const conds = screen ? A.filter(c => R!.run!.conditions.some(s => s.id === c.id)) : [];
  const th = (key: string, label: string, cls = '', title = '', chip = '') => {
    const on = S.sort.key === key, sortAttr = on ? (S.sort.dir === 'desc' ? 'descending' : 'ascending') : 'none';
    const ar = `<span class="ar ${on ? 'on' : ''}">${ico(on ? (S.sort.dir === 'desc' ? IC.down : IC.up) : IC.sort, 's')}</span>`;
    // EXEC-SCREENER-V21: an indicator header is [name: sort] [parameters chip: edit] [arrow: sort] (reference 1102-1343)
    if (chip) return `<th class="${cls} hsplit" aria-sort="${sortAttr}"><div class="hs"><button data-sort="${esc(key)}" title="${esc(title || 'Sort')}">${label}</button>${chip}<button class="hs-ar" data-sort="${esc(key)}" title="Sort" aria-label="Sort">${ar}</button></div></th>`;
    return `<th class="${cls}" aria-sort="${sortAttr}"><button data-sort="${esc(key)}" title="${esc(title || 'Sort')}">${label}${ar}</button></th>`;
  };
  const xdefs = R && rowsShown(R) ? extraDefs() : [];
  const m = R?.rows.filter(r => r.status === 'match') || [], near = R?.rows.filter(r => r.status === 'near') || [];
  const allSel = pr.length > 0 && pr.every(r => S.sel.has(r.ticker));
  const lg = R?.def?.logic ?? S.logic;                        // the logic of the definition the table answers
  const logicTxt = lg === 'all' ? 'all' : lg === 'any' ? 'any' : 'at least ' + (R?.run?.need ?? S.atLeast);
  const watchOk = ctx.watch != null;
  // a disabled star or bulk button says why: the watchlist is loading, or it could not be loaded (and how to fix)
  const watchNo = watchOk ? '' : `disabled title="${esc(ctx.watchError ? `Watchlist unavailable: ${ctx.watchError}` : 'Loading your watchlist…')}"`;
  $('bulk').innerHTML = S.sel.size ? `<div class="bulk"><strong>${S.sel.size} selected</strong><span class="sp"></span><button class="btn sm" data-act="watchsel" ${watchNo}>${ico(IC.plus, 's')}Add to Watchlist</button><button class="btn sm" data-act="send" disabled title="${esc(T.sendPhase)}">${ico(IC.send, 's')}Send to Backtest</button><button class="btn sm" data-act="csvsel">${ico(IC.dl, 's')}Export CSV</button><button class="btn sm" data-act="clearsel">Clear selection</button></div>` : '';
  const busy = ctx.running ? `<span class="sbox">${spin(T.running)}</span>` : '';
  const out = ctx.stale && R ? `<span class="pill t-warning" title="The screen changed since this result. Press Screen now to update the table.">${T.outOfDate}</span>` : '';
  const warns = (R?.run?.warnings || []).filter(w => w.code !== 'NO_PRUNING_FOR_ANY').map(w => `<span class="pill t-warning" title="${esc(w.message)}">${esc(w.code === 'PRICE_BREAKS_IN_RESULT' ? 'Price breaks shown' : w.code === 'FLOW_LAGGED' ? 'Flow lags price' : w.code)}</span>`).join('');
  const metaL = !R ? `<strong>…</strong><small class="muted">${ctx.runError ? '' : T.loadingResults}</small>${busy}`
    : `<strong>${screen ? `${nf(m.length)} match${m.length === 1 ? '' : 'es'}` : `${nf(R.eligible)} instruments`}</strong><small class="muted">${screen ? `meet ${logicTxt} of ${conds.length} condition${conds.length > 1 ? 's' : ''} · ${nf(R.eligible)} in universe` : 'in the universe · pick a preset to screen them'}${S.q ? ` · filtered by “${esc(S.q)}”` : ''}</small>
      ${screen ? `<span class="stats"><span>Near misses <b>${nf(near.length)}</b></span></span>` : ''}${out}${warns}${busy}`;
  const nx = shownColumns().length;
  const colBtn = `<button type="button" class="btn sm colbtn" data-act="cols" aria-haspopup="dialog" aria-controls="colPop" aria-expanded="${!$('colPop').hidden}"><span class="colbtn-ic" aria-hidden="true">${ico(IC.cols, 's')}<i>+</i></span>Add column${nx ? ` <span class="count">${nx}</span>` : ''}</button>`;
  const nmInfo = `<button type="button" class="nm-info" aria-label="What are near misses?" aria-describedby="nmTip"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">${IC.info}</svg></button>`;
  const metaR = `${colBtn}${screen ? `<label><span class="sw"><input type="checkbox" id="nearT" ${S.nearMiss ? 'checked' : ''}><span></span></span>Near misses</label>${nmInfo}` : ''}${S.preview ? '' : `<button class="btn sm" data-act="pvopen">${ico(IC.eye, 's')}Show preview</button>`}`;
  const remarkCol = pr.some(r => r.remarks.length);
  let body: string;
  if (ctx.runError && (!R || !rows.length)) body = `<div class="empty" role="alert"><strong>The screen could not run</strong>${esc(ctx.runError)}<div class="acts"><button class="btn sm" data-act="retry">${ico(IC.reset, 's')}${T.retry}</button></div></div>`;
  else if (!R) body = `<div class="empty">${spin(T.loadingResults)}</div>`;
  else if (rows.length) body = `${ctx.runError ? `<div class="note down" role="alert" style="padding:8px 16px">${esc(ctx.runError)} <button class="link" data-act="retry">${T.retry}</button></div>` : ''}<div class="tbl-wrap"><table class="res"><thead><tr><th class="l" style="width:34px"><span><input type="checkbox" id="selAll" ${allSel ? 'checked' : ''} aria-label="Select visible rows"></span></th><th class="l" style="width:54px"><span>Watch</span></th>${th('sym', 'Symbol', 'l')}<th class="l"><span>Company</span></th><th class="l"><span>Sector</span></th>${th('last', 'Last')}${th('d1', '1D')}${th('adv', 'Avg value', '', 'Average daily traded value over 20 sessions, in billions of rupiah (Rp B)')}${remarkCol ? '<th class="l"><span>Remark</span></th>' : ''}${conds.length ? th('match', 'Met', '', 'Conditions met') : ''}${conds.map(c => {
      const e = entryOf(c), pv = shortPv(e, c), cus = e && isCustom(e, c) ? 'cus' : '';
      // a card with parameters (not a My metric, whose parameters are its own) gets the editor chip, only when the page
      // has this same condition (pageCardOf: same id, entry and form; a preset reuses ids, QA M1)
      const ed = !!(e && e.params.length && pageCardOf(c)), lb = pv || (ed ? e!.params.map(p => String(c.params[p.key])).join('/') : '');
      const chip = ed ? `<button type="button" class="pvchip ${cus}" data-pedit="${esc(c.id)}" aria-haspopup="dialog" aria-expanded="false" aria-label="Change parameters: ${esc(paramSummary(e!, c.params))}"><span class="pv ${cus}">${esc(lb)}</span></button>` : '';
      return th('c:' + c.id, `<i class="cdot" style="background:${colorOf(c)}"></i>${esc(shortName(e, c))}${!ed && pv ? ` <span class="pv ${cus}">${esc(pv)}</span>` : ''}`, '', `${condText(e, c)} · ${e?.params.length ? (isCustom(e, c) ? 'custom parameters: ' : 'default parameters: ') + paramSummary(e, c.params) : 'fixed definition'}`, chip);
    }).join('')}${xdefs.map(d => extraTh(d, th)).join('')}</tr></thead>
      <tbody>${pr.map(r => {
        const w = ctx.watch?.has(r.ticker) ?? false, nearRow = r.status === 'near';
        return `<tr data-tk="${esc(r.ticker)}" tabindex="0" class="${nearRow ? 'near' : ''} ${S.pick === r.ticker && S.preview ? 'picked' : ''}${r.stale ? ' stale' : ''}"><td class="l"><input type="checkbox" data-sel="${esc(r.ticker)}" ${S.sel.has(r.ticker) ? 'checked' : ''} aria-label="Select ${esc(r.ticker)}"></td><td class="l"><button class="watch-dot ${w ? 'on' : ''}" data-watch="${esc(r.ticker)}" ${watchOk ? `title="${w ? 'In Watchlist — click to remove' : 'Add to Watchlist'}"` : watchNo} aria-label="${w ? 'Remove ' + esc(r.ticker) + ' from' : 'Add ' + esc(r.ticker) + ' to'} Watchlist" aria-pressed="${w}">${ico(w ? IC.check : IC.plus, 's')}</button></td>
          <td class="l"><span class="sym">${esc(r.ticker)}</span>${nearRow ? ' <span class="pill nearp">near</span>' : ''}</td><td class="l co" title="${esc(r.name || '')}">${esc(r.name || '')}</td><td class="l">${sectorTag(r.sector)}</td>${lastTd(r)}${d1Td(r)}<td title="Rp ${r.adv20_idr == null ? '—' : nf(r.adv20_idr / 1e9, 1) + ' billion'} a session (20-session average)">${r.adv20_idr == null ? '—' : nf(r.adv20_idr / 1e9, 1) + 'B'}</td>
          ${remarkCol ? `<td class="l">${r.remarks.map(x => `<span class="pill t-warning rbadge" title="${esc(remarkTitle(x))}">${ico(IC.warn, 's')}${esc(remarkBadge(x))}</span> <small class="muted">${esc(x.code === 'STALE' ? x.last_bar_date : x.ex_date)}</small>`).join(' ')}</td>` : ''}
          ${conds.length ? `<td><span class="dots">${conds.map(c => `<i class="${cellOf(r, c.id)?.status === 'pass' ? 'y' : ''}" style="--c:${colorOf(c)}"></i>`).join('')}</span> <b style="margin-left:4px">${r.met}/${conds.length}</b></td>` : ''}${conds.map(c => cellHtml(r, c)).join('')}${xdefs.map(d => extraTd(r, d)).join('')}</tr>`;
      }).join('')}</tbody></table></div>
    <div class="tbl-foot"><span>Showing ${nf((S.page - 1) * S.perPage + 1)}–${nf(Math.min(S.page * S.perPage, rows.length))} of ${nf(rows.length)}</span><div class="acts"><label style="display:flex;align-items:center;gap:6px">Rows per page<select class="sel" id="perPage">${[10, 25, 50, 100].map(n => `<option value="${n}" ${n === S.perPage ? 'selected' : ''}>${n}</option>`).join('')}</select></label><button class="iconbtn sm" data-pg="-1" ${S.page === 1 ? 'disabled' : ''} title="Previous page" aria-label="Previous page">${ico(IC.left, 's')}</button><span>${S.page} / ${pages}</span><button class="iconbtn sm" data-pg="1" ${S.page === pages ? 'disabled' : ''} title="Next page" aria-label="Next page">${ico(IC.right, 's')}</button></div></div>`;
  else if (S.q) body = `<div class="empty"><strong>No stock matches “${esc(S.q)}”</strong>The search only looks inside the current results.<div class="acts"><button class="btn sm" data-act="tqclear2">Clear search</button></div></div>`;
  else if (screen) body = `<div class="empty"><strong>No stock meets ${conds.length === 1 ? 'the condition' : lg === 'all' ? `all ${conds.length} conditions` : `${logicTxt} of ${conds.length} conditions`}</strong>Loosen a threshold, switch the match to Any / At least, or show near misses.<div class="acts"><button class="btn sm" data-act="near">Show near misses (${nf(near.length)})</button>${conds.length > 1 ? `<button class="btn sm" data-act="any">Match at least ${Math.max(1, conds.length - 1)}</button>` : ''}</div></div>`;
  else body = `<div class="empty"><strong>The universe is empty</strong>Every listing is filtered out. Loosen a filter or reset the universe.<div class="acts"><button class="btn sm" data-act="resetU2">Reset universe</button></div></div>`;
  // the table keeps its scroll position across a re-render (values arriving, a sort, an extra column)
  const ow = $('resPane').querySelector('.tbl-wrap') as HTMLElement | null, sx = ow?.scrollLeft ?? 0, sy = ok === lastOrder ? ow?.scrollTop ?? 0 : 0; lastOrder = ok;
  keepField($('resTools'), () => { $('resTools').innerHTML = metaR });   // keep-field.ts, ERRORS M373
  $('resMeta').innerHTML = metaL; keepField($('resPane'), () => { $('resPane').innerHTML = body }); $('tqClear').hidden = !S.q;
  // the table's scroll is put back only when it was scrolled: writing a scroll offset lays the new table out at once, and
  // at 0 (the boot, most redraws) that layout was half of a long task (ERRORS M364)
  const nw = $('resPane').querySelector('.tbl-wrap') as HTMLElement | null; if (nw && (sx || sy)) { nw.scrollLeft = sx; nw.scrollTop = sy }
  $('preview').hidden = !S.preview; document.body.classList.toggle('has-pv', S.preview); sizePreview();
  const tbl = $('resPane').querySelector('table.res') as HTMLTableElement | null; if (tbl) applyTable(tbl);
  layoutHooks.afterResults();
}
/** the 1-day change, marked when the stock's last session is the ex-date of an unadjusted corporate action (the move
    is distorted; texts.ts chg1dBreakText) */
/** the date the rows are of: the run's evaluation date, else the catalog's */
const rowsDate = () => ctx.R?.run?.data.evaluation_date ?? evalDate();
/** a stale row's value (Last, 1D) says the date it is of, in its title and to a screen reader (QA M4) */
const staleNote = (r: Row, what: 'close' | 'change') => r.stale ? staleValueText(what, r.last_bar_date, rowsDate()) : null;
function d1Td(r: Row): string {
  const why = chg1dBreakText(r.remarks, r.last_bar_date), old = staleNote(r, 'change');
  const title = [old, why].filter(Boolean).join('\n');
  return `<td class="${tone(r.chg_1d_pct)}"${title ? ` title="${esc(title)}"` : ''}>${sgn(r.chg_1d_pct)}${why ? ` <i class="rmk" aria-label="Distorted value">${ico(IC.warn, 's')}</i>` : ''}${old ? `<span class="vh">, ${esc(old)}</span>` : ''}</td>`;
}
function lastTd(r: Row): string {
  const old = staleNote(r, 'close');
  return `<td${old ? ` title="${esc(old)}"` : ''}>${nf(r.last)}${old ? `<span class="vh">, ${esc(old)}</span>` : ''}</td>`;
}
/** whether the table holds rows (extra columns are shown beside a table only) */
const rowsShown = (R: NonNullable<typeof ctx.R>) => R.rows.length > 0;
/** the detail panel runs from its top edge to the bottom of the window (the prototype). It reads the layout, so it
    runs once per frame after the frame's DOM writes, never as a forced layout inside a render (6c.9 long tasks). */
let sizeFrame = 0;
export function sizePreview() {
  if (!sizeFrame) sizeFrame = requestAnimationFrame(() => { sizeFrame = 0; sizeNow() });
}
function sizeNow() {
  const el = $('preview');
  if (el.hidden || innerWidth <= 900) { el.style.height = ''; return }
  const top = Math.max(16, el.getBoundingClientRect().top);
  el.style.height = Math.max(320, innerHeight - top - 16) + 'px';
}

/** add or remove tickers in the server watchlist (P12 a): shown at once, put back when the server refuses */
export async function toggleWatch(list: string[], addOnly = false) {
  const W = ctx.watch; if (!W || !list.length) return;
  const add = addOnly || !W.has(list[0]);
  const changed = list.filter(k => W.has(k) !== add);
  changed.forEach(k => add ? W.add(k) : W.delete(k)); renderResults();
  try {
    await Promise.all(changed.map(k => ctx.api.watch(k, add)));
    toast(list.length > 1 ? `${list.length} stocks added to Watchlist` : `${list[0]} ${add ? 'added to' : 'removed from'} Watchlist`);
  } catch (e) {
    changed.forEach(k => add ? W.delete(k) : W.add(k)); renderResults();
    toast(e instanceof ApiFailure ? e.message : 'The watchlist could not be changed.');
  }
}

/** CSV of the visible rows (or the selected ones) in the current sort (report 9.6) */
export function exportCsv(onlySel = false) {
  const R = ctx.R; if (!R) { toast('Nothing to export yet'); return }
  const all = visibleRows(), rows = onlySel ? sortRows(R.rows.filter(r => S.sel.has(r.ticker)), S.sort) : all;
  if (!rows.length) { toast('Nothing to export yet'); return }
  const conds = R.run?.mode === 'screen' ? screenedCards().filter(c => R.run!.conditions.some(s => s.id === c.id)).map(c => ({ id:c.id, text:condText(entryOf(c), c) })) : [];
  // the file describes its rows: an out-of-date table is named after the screen it answers (its date and versions are
  // the run's already, csv.ts metaOf); a table that answers the page takes the page's name, renamed or not (QA M2)
  const name = ctx.stale ? R.name ?? S.name : S.name;
  const meta = metaOf(name, R.run, { evaluation_date:evalDate(), published_at:ctx.catalog?.data.published_at ?? null, versions:ctx.catalog?.versions ?? null });
  download(`${slug(name)}-${meta.evaluation_date || 'undated'}.csv`, csvText(rows, conds, meta));
  toast(`${rows.length} rows exported`);
}
export function download(name: string, text: string, type = 'text/csv') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function onResultsClick(e: Event) {
  const t = e.target as HTMLElement;
  const s = t.closest('[data-sort]') as HTMLElement | null;
  if (s) { const k = s.dataset.sort as typeof S.sort.key; S.sort = S.sort.key === k ? { key:k, dir:S.sort.dir === 'desc' ? 'asc' : 'desc' } : { key:k, dir:k === 'sym' ? 'asc' : 'desc' }; renderResults(); return }
  if (t.matches('input,select,label,.sw,.sw *')) return;
  const pg = t.closest('[data-pg]') as HTMLElement | null;
  if (pg) { S.page += +pg.dataset.pg!; renderResults(); $('cardR').scrollIntoView({ block:'nearest' }); return }
  const a = t.closest('[data-act]') as HTMLElement | null;
  if (a) {
    switch (a.dataset.act) {
      case 'watchsel': toggleWatch([...S.sel], true); return;
      case 'csvsel': exportCsv(true); return;
      case 'clearsel': S.sel.clear(); renderResults(); return;
      case 'near': S.nearMiss = true; renderResults(); return;
      case 'any': S.logic = 'at_least'; S.atLeast = Math.max(1, activeCards().length - 1); ui.markDirty(); ui.refresh('conds'); return;
      case 'pvopen': ui.togglePreview(true); return;
      case 'tqclear2': S.q = ''; ($('tq') as HTMLInputElement).value = ''; renderResults(); return;
      case 'resetU2': S.universe = freshUniverse(); ui.markDirty(); ui.refresh('universe'); return;
      case 'retry': ui.schedule(true); return;
    }
  }
  const w = t.closest('[data-watch]') as HTMLElement | null;
  if (w) { toggleWatch([w.dataset.watch!]); return }
  const tr = t.closest('tr[data-tk]') as HTMLElement | null;
  if (tr) ui.pickStock(tr.dataset.tk!);
}
export function onResultsChange(e: Event) {
  const t = e.target as HTMLInputElement;
  if (t.id === 'nearT') { S.nearMiss = t.checked; renderResults(); return }
  if (t.id === 'perPage') { S.perPage = +t.value; S.page = 1; renderResults(); return }
  if (t.dataset.sel) { const k = t.dataset.sel; t.checked ? S.sel.add(k) : S.sel.delete(k); renderResults(); return }
  if (t.id === 'selAll') { visibleRows().slice((S.page - 1) * S.perPage, S.page * S.perPage).forEach(r => t.checked ? S.sel.add(r.ticker) : S.sel.delete(r.ticker)); renderResults() }
}
export function onResultsKey(e: KeyboardEvent) {
  const tr = (e.target as HTMLElement).closest?.('tr[data-tk]') as HTMLElement | null;
  if (!tr || e.target !== tr) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ui.pickStock(tr.dataset.tk!) }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); ((e.key === 'ArrowDown' ? tr.nextElementSibling : tr.previousElementSibling) as HTMLElement | null)?.focus() }
}
