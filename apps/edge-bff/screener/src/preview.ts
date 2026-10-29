/* The stock preview (the prototype's renderDetails, drawChart, perfCard, renderMethod), on POST preview (report 9.3):
   a row click or a lookup asks the worker for the ticker's last 260 bars, IHSG aligned, overlays and event markers per
   active condition, its cells and status and the "Stock vs IHSG" figures, pinned to the table's data version (a 409
   DATA_VERSION_CHANGED re-runs the screen, so chart and table never mix publications). The chart is drawn in the
   browser with lightweight-charts 5.2.1 from npm (the pattern of backtest/src/signals.ts initPriceChart): candles of
   the last 130 sessions, one line per overlay output (dashed for band lines), arrowUp markers per event bar in the
   condition's colour. While a ticker loads the chart is emptied and shows the shared ring (EXEC-BACKTEST-SPIN), never
   the previous ticker's candles. */
import { CandlestickSeries, ColorType, createChart, createSeriesMarkers, LineSeries, type IChartApi, type SeriesMarker, type Time } from 'lightweight-charts';
import type { PerfPeriod, PreviewResponse } from './core/contract.ts';
import { PERF_PERIODS } from './core/contract.ts';
import { esc, hue, nf, sectorTag, sgn, timeText, tone, valueText } from './format.ts';
import { IC, ico } from './icons.ts';
import { activeCards, ctx, definitionOf, entryOf, presetOf, S, savedOf, ui } from './state.ts';
import { condText, optOf, shortName } from './forms.ts';
import { cellRemarkText, methodText, naText, remarkText, remarkTitle, T } from './texts.ts';
import { colorOf } from './builder.ts';
import { toast } from './dialogs.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { ApiFailure, isAbort } from './api/types.ts';
import { savePanel, TERMINAL_SYMBOL } from './storage.ts';
import { searchMatches } from '../../backtest/src/picked.ts';

const $ = (id: string) => document.getElementById(id)!;
let chart: IChartApi | null = null;

/** the preview of the picked ticker: its answer, or the error of its last ask; ticker and definition it answers */
const PV: { ticker: string | null; key: string; answer: PreviewResponse | null; error: string | null; ctl: AbortController | null; timer: ReturnType<typeof setTimeout> | undefined } =
  { ticker:null, key:'', answer:null, error:null, ctl:null, timer:undefined };
const pvKey = (tk: string) => `${tk}|${JSON.stringify(definitionOf())}|${dataVersion()}`;
const dataVersion = () => ctx.R?.run?.versions.price_data || ctx.catalog?.versions.price_data || '';

/** ask the preview of the picked ticker (debounced, latest wins); `force` asks again even for the same key */
export function askPreview(force = false) {
  const tk = S.pick;
  if (!tk || !S.preview || S.dtab !== 'stock' || !ctx.catalog) return;
  const key = pvKey(tk);
  if (!force && key === PV.key && (PV.answer || PV.ctl || PV.error)) return;
  PV.ctl?.abort(); PV.ctl = null; clearTimeout(PV.timer);
  if (PV.ticker !== tk) PV.answer = null;
  PV.ticker = tk; PV.key = key; PV.error = null;
  PV.timer = setTimeout(async () => {
    const ctl = new AbortController(); PV.ctl = ctl;
    try {
      const a = await ctx.api.preview({ schema_version:1, definition:definitionOf(), ticker:tk, data_version:dataVersion() }, { signal:ctl.signal });
      if (PV.ctl !== ctl) return;
      PV.answer = a; PV.ctl = null;
      ui.versionSeen(a.versions);   // 6c.5 item 3: an answer newer than the catalog makes the app ask the catalog again
    } catch (e) {
      if (isAbort(e) || PV.ctl !== ctl) return;
      PV.ctl = null;
      if (e instanceof ApiFailure && e.code === 'DATA_VERSION_CHANGED') { PV.key = ''; ui.schedule(true); return }   // re-run, then ask again
      if (e instanceof ApiFailure && e.code === 'PREVIEW_REPLACED') return;
      PV.error = e instanceof ApiFailure ? e.message : String(e);
    }
    if (S.pick === tk) renderDetails();
  }, 120);
}
export const previewAnswer = () => PV.answer && PV.ticker === S.pick && PV.key === pvKey(S.pick!) ? PV.answer : null;

export function togglePreview(on: boolean) {
  S.preview = on; savePanel({ preview:on }); ui.renderResults();
  if (on) { renderDetails(); return }
  if (chart) { chart.remove(); chart = null }
  $('dtb').innerHTML = ''; $('dacts').hidden = true;
}
export function pickStock(tk: string) {
  S.pick = tk; S.dtab = 'stock';
  if (!S.preview) { S.preview = true; savePanel({ preview:true }); ui.renderResults() }
  document.querySelectorAll<HTMLElement>('#resPane tr[data-tk]').forEach(tr => tr.classList.toggle('picked', tr.dataset.tk === tk));
  renderDetails();
}

const pvSeg = () => `<span class="seg sm pvseg" role="tablist" aria-label="Panel view"><button class="${S.pvView !== 'perf' ? 'on' : ''}" data-pvv="chart" role="tab" aria-selected="${S.pvView !== 'perf'}" tabindex="${S.pvView !== 'perf' ? 0 : -1}">${ico(IC.chart, 's')}Chart</button><button class="${S.pvView === 'perf' ? 'on' : ''}" data-pvv="perf" role="tab" aria-selected="${S.pvView === 'perf'}" tabindex="${S.pvView === 'perf' ? 0 : -1}">${ico(IC.trend, 's')}Stock vs IHSG</button></span>`;
const plines = (series: { v: number[]; color: string; dash?: string; wd?: number }[], { w = 292, h = 120 } = {}) => {
  const v = series.flatMap(s => s.v), lo = Math.min(...v), hi = Math.max(...v), sp = (hi - lo) || 1;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" preserveAspectRatio="none" style="height:${h}px;display:block" aria-hidden="true">${series.map(s => `<path d="${s.v.map((x, i) => (i ? 'L' : 'M') + (i / (s.v.length - 1) * w).toFixed(1) + ' ' + (h - 3 - (x - lo) / sp * (h - 6)).toFixed(1)).join('')}" fill="none" stroke="${s.color}" stroke-width="${s.wd || 1.6}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ''} vector-effect="non-scaling-stroke"/>`).join('')}</svg>`;
};
/** "Stock vs IHSG" (P14 a: the relabelled performance view): both rebased to 100 over the catalog's session counts
    (P23 a: 21/63/126/252); the totals are the worker's (perf), the lines the answer's closes */
function perfCard(tk: string, a: PreviewResponse): string {
  const per = (S.perf || '6M') as PerfPeriod, n = ctx.catalog?.periods[per] ?? 126, c = a.bars.c, b = a.ihsg_close, N = c.length, from = N - 1 - n;
  const f = a.perf[per] || { stock_pct:null, ihsg_pct:null };
  const ra = f.stock_pct, rb = f.ihsg_pct, line = getComputedStyle(document.documentElement).getPropertyValue('--navy').trim() || '#17348c';
  const seg = `<span class="seg sm">${PERF_PERIODS.map(l => `<button class="${per === l ? 'on' : ''}" data-perf="${l}">${l}</button>`).join('')}</span>`;
  let lines = '';
  if (from >= 0 && c[from] != null && b[from] != null) {
    const sa: number[] = [], sb: number[] = [];
    for (let i = 0; i <= n; i++) { const x = c[from + i], y = b[from + i]; sa.push(x == null ? sa[sa.length - 1] ?? 100 : x / c[from]! * 100); sb.push(y == null ? sb[sb.length - 1] ?? 100 : y / b[from]! * 100) }
    lines = plines([{ v:sb, color:'#a1a1a1', dash:'3 3', wd:1.2 }, { v:sa, color:line, wd:1.8 }]);
  } else lines = `<p class="note">Not enough history for ${per} (${n} sessions).</p>`;
  const diff = ra != null && rb != null ? ra - rb : null;
  return `<div class="pcard"><div class="pcard-h"><strong>${esc(tk)} vs IHSG</strong>${seg}</div>${lines}
    <div class="legend2"><span><i style="background:${line}"></i>${esc(tk)} <b class="${tone(ra)}">${sgn(ra, 1)}</b></span><span><i style="background:#a1a1a1"></i>IHSG <b class="${tone(rb)}">${sgn(rb, 1)}</b></span></div>
    <div class="note">${diff == null ? 'No comparison for this period.' : `${diff >= 0 ? 'Outperformed' : 'Underperformed'} IHSG by <b class="${tone(diff)}">${sgn(diff, 1, ' pts')}</b> over ${per} (${n} sessions to ${esc(a.data.evaluation_date)}). Not a screen backtest: the stock is chosen by today's screen.`}</div></div>`;
}
const logoOf = (tk: string) => `<span class="logo" style="--h:${hue(tk)}" aria-hidden="true">${esc(tk.slice(0, 2))}</span>`;
const closeBtn = (label = 'Close preview') => `<button class="iconbtn sm" data-pv="close" title="${label}" aria-label="${label}">${ico(IC.x, 's')}</button>`;
const lookup = () => `<label class="searchbox pvlook">${ico(IC.search, 's')}<input id="pvq" placeholder="Look up a ticker" aria-label="Look up a ticker" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="pvsug"></label><div class="suggest" id="pvsug" role="listbox" hidden></div>`;

export function renderDetails() {
  if (chart) { chart.remove(); chart = null }
  if (!S.preview) return;
  const tk = S.pick, row = tk ? ctx.R?.rows.find(r => r.ticker === tk) || null : null, urow = tk ? ctx.universe?.rows.find(r => r.ticker === tk) || null : null;
  if (S.dtab === 'method') {
    $('dtb').innerHTML = `<div class="preview-head"><div><strong>Method & sources</strong><small>How the screen is computed</small></div>${closeBtn('Close panel')}</div>${tk ? `<button class="link" data-dt="stock" style="justify-self:start">← Back to ${esc(tk)}</button>` : ''}` + renderMethod();
    $('dacts').hidden = true; return;
  }
  if (!tk) {
    $('dtb').innerHTML = `<div class="pvtop">${lookup()}</div><div class="preview-head"><div><strong>Preview</strong><small>Stock detail and method</small></div>${closeBtn()}</div><div class="dempty">${ico(IC.chart)}<b style="color:var(--text)">Pick a stock</b>Click a result row — or look up any ticker above — to see its chart, why it passed or failed, and its remarks.</div>`;
    $('dacts').hidden = true; return;
  }
  askPreview();
  const a = previewAnswer(), name = a ? (row?.name ?? urow?.name) : (row?.name ?? urow?.name), sector = row?.sector ?? urow?.sector, industry = row?.industry ?? urow?.industry;
  const A = activeCards(), last = a ? a.bars.c[a.bars.c.length - 1] : row?.last ?? urow?.last ?? null, d1 = row?.chg_1d_pct ?? urow?.chg_1d_pct ?? null;
  const remarks = a?.remarks ?? row?.remarks ?? urow?.remarks ?? [];
  const status = !a ? '' : a.status === 'outside_universe' ? '<span class="pill t-neutral">Outside universe</span>'
    : !A.length ? '<span class="pill t-info">In universe</span>'
    : a.status === 'match' ? `<span class="pill t-positive"><i></i>Match ${a.met}/${A.length}</span>`
    : a.status === 'near' ? `<span class="pill t-warning"><i></i>Near ${a.met}/${A.length}</span>` : `<span class="pill t-negative"><i></i>${a.met}/${A.length}</span>`;
  const head = `<div class="pvtop">${lookup()}</div><div class="preview-head">${logoOf(tk)}<div><strong>${esc(tk)}${sectorTag(sector)}</strong><small>${esc(name || '')}</small></div>${closeBtn()}</div>`;
  const rmk = remarks.length ? `<div class="chips">${remarks.map(r => `<span class="pill t-warning rbadge" title="${esc(remarkTitle(r))}">${ico(IC.warn, 's')}${esc(remarkText(r))}</span>`).join('')}</div>` : '';
  const why = A.length && a ? `<div class="sec-title">Why it ${a.status === 'match' ? 'passed' : 'did not pass'}</div><div class="chk-list">${A.map(c => {
      const x = a.cells.find(y => y.id === c.id), e = entryOf(c), o = e && optOf(e, c), kind = o?.kind || (c.raw as any)?.kind;
      const txt = !x ? '—' : x.status === 'na' ? 'n/a' : kind === 'event' ? (x.bars_ago == null ? (x.status === 'pass' ? 'yes' : '—') : x.bars_ago === 0 ? 'today' : `${x.bars_ago}d ago`)
        : kind === 'state' ? (x.status === 'pass' ? 'Yes' : 'No') : valueText(x.value, x.unit ?? o?.unit, o?.form === 'value_pct_distance');
      const tip = [x?.eval_date ? `Evaluated ${x.eval_date}` : '', x?.event_date ? `Event ${x.event_date}` : '', x?.status === 'na' ? naText(x.reason) : '', x?.remark ? cellRemarkText(x.remark, remarks) : ''].filter(Boolean).join('\n');
      const mark = x?.status === 'pass' ? '<span class="up">✓</span>' : x?.status === 'na' ? '<span class="muted">–</span>' : '<span class="down">✕</span>';
      return `<div title="${esc(tip)}"><i class="cdot" style="background:${colorOf(c)}"></i><span>${esc(condText(e, c))}</span><b>${esc(txt)}${x?.remark ? ` ${ico(IC.warn, 's')}` : ''}</b>${mark}</div>`;
    }).join('')}</div>` : '';
  const facts = `<div class="sec-title">Fundamentals <span class="pill t-neutral" title="${esc(T.noFundamentals)}">no data</span></div><div class="facts">${['Market cap', 'P/E', 'P/B', 'ROE', 'Div. yield', 'EPS growth', 'D/E', 'Piotroski'].map(k => `<div title="${esc(k === 'Market cap' ? T.noCap : k === 'Div. yield' ? 'No data yet: dividends come with Phase 2, after validation.' : T.noFundamentals)}"><span>${k}</span><b class="muted">no data</b></div>`).join('')}</div>`;
  const view = S.pvView === 'perf'
    ? (a ? perfCard(tk, a) : `<div class="pcard">${PV.error ? `<p class="note down" role="alert">${esc(PV.error)}</p>` : spin(`Loading ${esc(tk)}`)}</div>`)
    : `<div><div id="dChart" style="position:relative">${a ? '' : `<span class="ml-boot">${PV.error ? `<span class="note down" role="alert">${esc(PV.error)}</span>` : spin(`Loading ${esc(tk)}`)}</span>`}</div><div class="legend" id="dLegend">${a ? legend(a) : ''}</div></div>`;
  $('dtb').innerHTML = head + `<div class="pquote"><strong>${nf(last)}</strong><span class="${tone(d1)}" style="font-weight:600">${d1 == null ? '' : sgn(d1) + ' today'}</span>${status}</div>
    <div class="note" style="margin-top:-6px">${esc(industry || 'Unclassified')} · <span title="${esc(T.noBoard)}">board: no data</span> · <span title="${esc(T.noIndex)}">indexes: no data</span></div>
    ${rmk}${pvSeg()}${view}${why}${facts}`;
  $('dacts').hidden = false;
  ($('dSend') as HTMLButtonElement).disabled = true; $('dSend').title = T.sendPhase;
  if (S.pvView !== 'perf' && a) drawChart(a);
}
const legend = (a: PreviewResponse) => {
  const A = activeCards(), withEv = A.filter(c => a.markers.some(m => m.condition_id === c.id && m.bars.length));
  return withEv.map(c => `<span><i style="background:${colorOf(c)}"></i>${esc(shortName(entryOf(c), c))}</span>`).join('') || '<span class="muted">Arrows mark event conditions (crosses, breakouts, divergences) over 6 months.</span>';
};

export const CHART_BARS = 130;
function drawChart(a: PreviewResponse) {
  const el = document.getElementById('dChart'); if (!el) return;
  const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  chart = createChart(el, { autoSize:true, localization:{ locale:'en-US' }, layout:{ background:{ type:ColorType.Solid, color:css('--surface') }, textColor:css('--text-3'), fontFamily:'Inter, sans-serif', fontSize:11, attributionLogo:false },
    grid:{ vertLines:{ visible:false }, horzLines:{ visible:false } }, rightPriceScale:{ borderColor:css('--border') }, timeScale:{ borderColor:css('--border') }, handleScroll:false, handleScale:false });
  const N = a.bars.d.length, from = Math.max(0, N - CHART_BARS), days = a.bars.d.slice(from);
  const cs = chart.addSeries(CandlestickSeries, { upColor:'#089981', downColor:'#f23645', borderVisible:false, wickUpColor:'#089981', wickDownColor:'#f23645', priceLineVisible:false, priceFormat:{ type:'price', precision:0, minMove:1 } });
  cs.setData(days.map((d, k) => {
    const i = from + k, o = a.bars.o[i], h = a.bars.h[i], l = a.bars.l[i], c = a.bars.c[i];
    return o == null || h == null || l == null || c == null ? { time:d as Time } : { time:d as Time, open:o, high:h, low:l, close:c };
  }));
  const A = activeCards(), seen = new Map<string, number>();
  for (const ov of a.overlays) {
    const c = A.find(x => x.id === ov.condition_id); if (!c) continue;
    const j = seen.get(c.id) ?? 0; seen.set(c.id, j + 1);
    const s = chart.addSeries(LineSeries, { color:colorOf(c), lineWidth:1, lineStyle:j ? 2 : 0, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false });
    s.setData(days.map((d, k) => { const v = ov.values[from + k]; return v != null && Number.isFinite(v) ? { time:d as Time, value:v } : { time:d as Time } }));
  }
  const first = days[0] || '', mk: SeriesMarker<Time>[] = [];
  for (const m of a.markers) {
    const c = A.find(x => x.id === m.condition_id); if (!c) continue;
    for (const b of m.bars) if (b.date >= first) mk.push({ time:b.date as Time, position:'belowBar', color:colorOf(c), shape:'arrowUp', size:.8 });
  }
  mk.sort((x, y) => (x.time as string) < (y.time as string) ? -1 : 1);
  createSeriesMarkers(cs, mk);
  chart.timeScale().fitContent();
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', `${a.ticker}: daily candles of the last ${days.length} sessions to ${days[days.length - 1] || ''}${mk.length ? `, ${mk.length} event marker${mk.length > 1 ? 's' : ''}` : ''}`);
}

/** Method & sources (report 9.2): "How conditions work" in the real semantics, the data status, the limits with their
    rule and examples (published before the user meets them, AGENTS.md "Gates and evidence"), the preset sources */
function renderMethod(): string {
  const p = S.source?.kind === 'preset' ? presetOf(S.source.id) : null, s = S.source?.kind === 'saved' ? savedOf(S.source.item_id) : null;
  const A = activeCards(), cat = ctx.catalog, d = cat?.data;
  const ctxBox = p ? `<div class="side-ctx"><b>${esc(p.name)}</b> · ${esc(p.category)}<br>${esc(p.why)}</div>`
    : `<div class="side-ctx"><b>${esc(s?.name || S.name)}</b><br>${A.length ? A.map(c => esc(condText(entryOf(c), c))).join(' · ') : 'No conditions yet.'}</div>`;
  const limits = (cat?.limits || []).map(l => `<div class="src"><b>${esc(l.rule)}</b><small>✓ ${esc(l.example_ok)}</small><small>✕ ${esc(l.example_refused)}</small></div>`).join('');
  const refresh = d?.refresh === 'failed_keeping_previous' ? 'The latest publication failed its checks; the previous one is kept.' : '';   // 'refreshing' is reported on /health only (report 8.3, 6d.4 rule 4)
  // the prototype's global bandar thresholds, kept visible and disabled with the reason: they become each bandar
  // condition's own parameters with the flow definitions (report 9.2 Method & sources; P9, Phase 3)
  const bandar = `<div class="sec"><h6>Bandar status thresholds</h6><div class="mini2"><label class="fld" title="${esc(T.bandarPhase)}"><span>Accumulation ≥ %</span><input class="inp" type="number" disabled placeholder="Phase 3" aria-label="Accumulation threshold: ${esc(T.bandarPhase)}"></label><label class="fld" title="${esc(T.bandarPhase)}"><span>Big accumulation ≥ %</span><input class="inp" type="number" disabled placeholder="Phase 3" aria-label="Big accumulation threshold: ${esc(T.bandarPhase)}"></label></div><p class="note" style="margin:0">${esc(T.bandarPhase)}</p></div>`;
  return `${ctxBox}${bandar}
    <div class="sec"><h6>How conditions work</h6><p class="note" style="margin:0">${esc(methodText(d?.evaluation_date || '—'))}</p></div>
    <div class="sec"><h6>Data</h6><div class="facts"><div><span>Evaluation date</span><b>${esc(d?.evaluation_date || '—')}</b></div><div><span>Prices through</span><b>${esc(d?.price_through || '—')}</b></div><div><span>Flow through</span><b>${esc(d?.flow_through || 'not yet (Phase 2)')}</b></div><div><span>Published</span><b>${esc(timeText(d?.published_at))}</b></div><div><span>Listings</span><b>${nf(ctx.universe?.rows.length)}</b></div></div>${refresh ? `<p class="note">${esc(refresh)}</p>` : ''}
      <p class="note" style="margin:0">Fundamentals, market cap, index membership, listing board and special notation have no data yet; they are shown disabled with their reason.</p></div>
    ${limits ? `<div class="sec"><h6>Limits</h6>${limits}</div>` : ''}
    <div class="sec"><h6>Preset sources</h6>${[['Stockbit & Ajaib screeners', 'Bandarmology, valuation and technical categories'], ['Mark Minervini', 'Trend template'], ['Joel Greenblatt', 'Magic Formula: earnings yield + return on capital'], ['Benjamin Graham', 'Defensive investor: P/E × P/B < 22.5'], ['Joseph Piotroski', 'F-score, 9 binary tests'], ['William O’Neil', 'CANSLIM (loosened for IDX)']].map(([x, y]) => `<div class="src"><b>${x}</b><small>${y}</small></div>`).join('')}</div>`;
}

/* ---- lookup (the prototype's global search, moved into the panel; backtest picked.ts searchMatches) -------- */
let lookIdx = 0;
function drawLookup(q: string) {
  const box = document.getElementById('pvsug'), inp = document.getElementById('pvq'); if (!box) return;
  const rows = (ctx.universe?.rows || []).map(r => ({ ticker:r.ticker, name:r.name || '' }));
  const { shown } = searchMatches(rows as any, q, 8);
  if (!q.trim()) { box.hidden = true; inp?.setAttribute('aria-expanded', 'false'); return }
  const matchSet = new Set((ctx.R?.rows || []).filter(r => r.status === 'match').map(r => r.ticker));
  lookIdx = Math.min(lookIdx, Math.max(0, shown.length - 1));
  box.innerHTML = shown.length ? shown.map((s, i) => `<button class="${i === lookIdx ? 'act' : ''}" data-g="${esc(s.ticker)}" role="option" aria-selected="${i === lookIdx}"><span class="tag ${matchSet.has(s.ticker) ? 'Flow' : 'Technical'}">${matchSet.has(s.ticker) ? 'Match' : 'Stock'}</span>${esc(s.ticker)}<small>${esc(s.name || '')}</small></button>`).join('')
    : `<div class="note" style="padding:10px">No ticker “${esc(q.trim().toUpperCase())}”.</div>`;
  box.hidden = false; inp?.setAttribute('aria-expanded', 'true');
}

export function bindPreview() {
  const dtb = $('dtb');
  dtb.addEventListener('click', e => {
    const t = e.target as HTMLElement, g = t.closest('[data-g]') as HTMLElement | null;
    if (g) { pickStock(g.dataset.g!); return }
    const b = t.closest('[data-dt],[data-pv],[data-pvv],[data-perf]') as HTMLElement | null; if (!b) return;
    if (b.dataset.perf) { S.perf = b.dataset.perf as typeof S.perf; savePanel({ perf:S.perf }); renderDetails(); return }
    if (b.dataset.pvv) { S.pvView = b.dataset.pvv as typeof S.pvView; savePanel({ pvView:S.pvView }); renderDetails(); (dtb.querySelector(`[data-pvv="${S.pvView}"]`) as HTMLElement | null)?.focus(); return }
    if (b.dataset.pv) { togglePreview(false); return }
    S.dtab = b.dataset.dt as typeof S.dtab; renderDetails();
  });
  dtb.addEventListener('input', e => { const t = e.target as HTMLInputElement; if (t.id === 'pvq') { lookIdx = 0; drawLookup(t.value) } });
  dtb.addEventListener('keydown', e => {
    const t = e.target as HTMLElement;
    if (t.getAttribute('role') === 'tab' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      e.preventDefault(); S.pvView = S.pvView === 'perf' ? 'chart' : 'perf'; renderDetails(); (dtb.querySelector(`[data-pvv="${S.pvView}"]`) as HTMLElement | null)?.focus(); return;
    }
    if (t.id !== 'pvq') return;
    const inp = t as HTMLInputElement, list = [...(document.getElementById('pvsug')?.querySelectorAll<HTMLElement>('[data-g]') || [])];
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && list.length) { e.preventDefault(); lookIdx = (lookIdx + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length; drawLookup(inp.value) }
    else if (e.key === 'Enter' && list[lookIdx]) { e.preventDefault(); pickStock(list[lookIdx].dataset.g!) }
    else if (e.key === 'Escape') { inp.value = ''; drawLookup('') }
  });
  $('dCopy').onclick = async () => {
    const tk = S.pick; if (!tk) return;
    const a = previewAnswer(), A = activeCards(), row = ctx.R?.rows.find(r => r.ticker === tk), last = a ? a.bars.c[a.bars.c.length - 1] : row?.last;
    const lines = A.map(c => { const x = a?.cells.find(y => y.id === c.id); return `${x?.status === 'pass' ? '✓' : x?.status === 'na' ? '–' : '✕'} ${condText(entryOf(c), c)} → ${x ? (x.status === 'na' ? 'n/a' : valueText(x.value ?? x.lhs, x.unit)) : '—'}` });
    const text = `${tk} ${row?.name || ''} · ${nf(last)} · evaluated ${a?.data.evaluation_date || ctx.catalog?.data.evaluation_date || ''}\n${lines.join('\n')}`;
    try { await navigator.clipboard.writeText(text); toast('Summary copied') } catch { toast('Copy blocked by the browser') }
  };
  $('dTerm').onclick = () => {
    const tk = S.pick; if (!tk) return;
    try { localStorage.setItem(TERMINAL_SYMBOL, tk) } catch { /* storage off: the Terminal opens on its own symbol */ }
    // the shell accepts edge-nav only from its own frame and origin, for routes backtest and terminal (report 9.4)
    try { parent.postMessage({ type:'edge-nav', route:'terminal' }, location.origin) } catch { /* not framed */ }
    toast(`${tk} opens in the Terminal`);
  };
  document.addEventListener('pointerdown', e => { if (!(e.target as HTMLElement).closest('.pvtop')) { const b = document.getElementById('pvsug'); if (b) b.hidden = true } });
}
export const resetPreview = () => { PV.key = ''; PV.answer = null; PV.error = null; PV.ctl?.abort(); PV.ctl = null };
