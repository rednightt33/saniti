/* EXEC-TERMINAL-POPOUT W1 + I2 (user 2026-10-27: "setiap panel di sebelah kanan harus bisa di-expand ... window
   terpisah di dalam browsernya ... panel dynamic agar bisa melihat data tersebut dengan lebih besar"; "Jendela di dalam
   halaman terminal. Yes, diperbesar dan ditambahkan fungsi-fungsi lain yang lebih detail. + W1 + I2"; "tanpa frekuensi
   dulu."), live: the ⤢ button of Broker summary, Top brokers and Broker inventory opens that panel as a window over
   the page (src/ui/floatwin.ts), larger and with more detail. The panel stays where it is. Each window keeps its own
   choices; the brokers drawn in Broker inventory are the panel's (one list), and a broker clicked in any window or
   panel joins it. Windows follow the chart's ticker, timeframe, visible range and crosshair. Open windows, their
   places and their choices are remembered across reloads. */
import type { Ctx } from './context';
import { $, keyOf, nfCompact, spin, store, tickCompact, visibleBars } from './context';
import { longDay, openRangeCalendar } from '../ui/calendar';
import { getWin, isWinOpen, openWin, type Win } from '../ui/floatwin';
import { aggregate, avgPrice, FD_DP, fdShown, inventory, invStats, sessionSpan, sidesTable, SPLIT_LEGEND, splitFill, toCsv, type SumKey, type SumRow, type SumSide } from '../data/brokerAgg';
import { fdTrail, niceTicks } from './broker';
import { fdCls, fdPct, mapLimit, trailDay, trailDeltas, trailSvg, type TrailPoint } from './fdMap';

type Key = 'bs' | 'acc' | 'inv' | 'fd';
const KEYS: Key[] = ['bs', 'acc', 'inv', 'fd'];
const TITLE: Record<Key, string> = { bs:'Broker summary', acc:'Top brokers', inv:'Broker inventory', fd:'Foreign × Domestic map' };
const SIZE: Record<Key, { w: number; h: number }> = { bs:{ w:880, h:520 }, acc:{ w:640, h:460 }, inv:{ w:720, h:560 }, fd:{ w:860, h:540 } };
const ICON = {
  pop:'<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 2.5h4v4M13.5 2.5L9 7M6.5 13.5h-4v-4M2.5 13.5L7 9"/></svg>',
  csv:'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5"/><path d="M11 5V3.5A1 1 0 0 0 10 2.5H3.5a1 1 0 0 0-1 1V10a1 1 0 0 0 1 1H5"/></svg>'
};
const OPEN_KEY = 'ml.win.open';
const cv = (v: number) => nfCompact.format(Math.abs(v));
const sgn = (v: number) => { const c = cv(v); return c === '0' ? '0' : (v < 0 ? '−' : '+') + c };            // QA round 3: one minus sign, as the panel
const price = (v: number | null) => v == null ? '–' : v.toLocaleString('en-US', { maximumFractionDigits:v < 100 ? 2 : 0 });
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const INVESTORS = ['All', 'Foreign', 'Domestic'], BOARDS = ['All', 'Regular', 'Nego', 'Cash'];
const select = (k: string, cur: string, opts: string[], all: string, label: string) =>
  `<select class="rp-sel" data-k="${k}" aria-label="${label}">${opts.map(v => `<option value="${v}"${v === cur ? ' selected' : ''}>${v === 'All' ? all : v}</option>`).join('')}</select>`;
const seg = (k: string, cur: string, opts: [string, string][], label: string) =>
  `<div class="seg" role="group" aria-label="${label}">${opts.map(([v, t]) => `<button type="button" data-k="${k}" data-v="${v}" class="${v === cur ? 'active' : ''}" aria-pressed="${v === cur}">${t}</button>`).join('')}</div>`;

/** a window's period: a preset of the last n sessions, the chart's visible sessions, or chosen dates */
interface Period { n: string; from?: string; to?: string }

export function initPopout(ctx: Ctx) {
  const S = ctx.brokerShared;
  if (ctx.M.mode !== 'live' || !S) return;
  const B = () => ctx.M.broker;
  /* EXEC-QA5-FIX (QA 2026-11-07, S-03): an index ticker (IHSG) has no lots that add up and no price per share (user
     2026-11-03, the panels' rule): its windows show Rupiah only, without lots or average prices */
  const IDX = !!ctx.M.index;
  const state: Record<Key, any> = {
    bs:{ p:{ n:'5' }, inv:'All', board:'Regular', mode:'net', limit:'20', q:'' },
    acc:{ p:{ n:'5' }, inv:'All', board:'Regular', unit:'value', limit:'10' },
    inv:{ inv:'All', board:'Regular', unit:'lot', view:'cum' },
    fd:{ p:{ n:'5' }, top:'3', span:'20', view:'level', board:'Regular' }
  };
  // 2A (user 2026-11-06): windows start on the Regular board; a window state already saved keeps its own choice
  KEYS.forEach(k => { try { Object.assign(state[k], JSON.parse(store.get('ml.winst.' + k) || '{}') || {}) } catch { /* the defaults */ } });
  // EXEC-TERMINAL-BS-SIDE: a Broker summary window remembered before the two sides (sorted by a column) keeps its
  // Net or Gross choice: "% of value" was Gross
  if ('sort' in state.bs) { state.bs.mode = state.bs.sort === 'share' ? 'gross' : 'net'; delete state.bs.sort; delete state.bs.desc }
  const keep = (k: Key) => store.set('ml.winst.' + k, JSON.stringify({ ...state[k], q:'' }));
  const remember = () => store.set(OPEN_KEY, JSON.stringify(KEYS.filter(isWinOpen)));
  const renders: Partial<Record<Key, () => void>> = {};

  /* ---- the chart's visible sessions as broker session indexes (Broker inventory, and the "Chart" period) ---- */
  /** the date of the first candle in view (before the broker data, the inventory says the data starts later) */
  const viewStart = () => ctx.dates[visibleBars(ctx.chart.timeScale().getVisibleLogicalRange(), ctx.N)[0]].slice(0, 10);
  const visibleSpan = (): [number, number] | null => {
    const [a, b] = visibleBars(ctx.chart.timeScale().getVisibleLogicalRange(), ctx.N);
    return a > b ? null : sessionSpan(B().dates, ctx.dates[a].slice(0, 10), ctx.endDates[b]);
  };
  const resolve = (p: Period): [number, number] | null => {
    const d = B().dates, last = d.length - 1;
    if (p.n === 'view') return visibleSpan();
    if (p.n === 'custom' && p.from && p.to) return sessionSpan(d, p.from, p.to);
    const n = +p.n || 5;
    return [Math.max(0, last - n + 1), last];
  };
  /* QA S-12: a chosen range without a session names its days, as the panel's note does */
  const noSession = (p: Period) => p.n === 'custom' && p.from && p.to ? `No trading session in ${p.from === p.to ? longDay(p.from) : `${longDay(p.from)} – ${longDay(p.to)}`}` : 'No broker session in the chosen days';
  const spanText = (f: number, t: number) => {
    const d = B().dates;
    return f === t ? longDay(d[f]) : `${longDay(d[f])} – ${longDay(d[t])} · ${t - f + 1} sessions`;
  };
  // EXEC-INTRADAY-FEATURES C4: on an intraday chart the broker figures stay daily
  const tf = ctx.M.intraday ? ` · daily figures, ${ctx.M.tf!.toUpperCase()} chart` : ctx.M.tf && ctx.M.tf !== 'D' ? ` · ${ctx.M.tf === 'W' ? 'weekly' : 'monthly'} chart` : '';
  const bkTag = (b: string) => `<span class="bk ${B().category(b)}"><i></i>${b}</span>`;
  const periodCtl = (k: Key) => seg('p', state[k].p.n, [['1', '1D'], ['5', '5D'], ['20', '20D'], ['view', 'Chart'], ['custom', 'Custom']], 'Period');
  /** no data yet, an index without broker data, or no session in the period: the message, else null */
  const blocked = (): string | null => !S.ready() ? spin('Loading') : !B().dates.length ? 'No broker data for this ticker' : null;

  /* the period buttons: presets, the chart's view, or the range calendar (with "Select on chart") */
  const wirePeriod = (k: Key, w: Win, render: () => void) => w.body.querySelectorAll('[data-k=p]').forEach((b: any) => b.onclick = () => {
    const st = state[k];
    if (b.dataset.v !== 'custom') { st.p = { n:b.dataset.v }; keep(k); render(); return }
    const d = B().dates, cur = resolve(st.p);
    if (!d.length) return;
    const set = (f: string, t: string) => { st.p = { n:'custom', from:f, to:t }; keep(k); render() };
    openRangeCalendar({ anchor:b, dates:d, from:d[cur ? cur[0] : 0], to:d[cur ? cur[1] : d.length - 1], onPick:set,
      onChart:() => ctx.selectRangeOnChart(set) });
  });
  const wireCtl = (k: Key, w: Win, render: () => void) => {
    w.body.querySelectorAll('select[data-k]').forEach((s: any) => s.onchange = () => { state[k][s.dataset.k] = s.value; keep(k); render() });
    w.body.querySelectorAll('button[data-k]:not([data-k=p])').forEach((b: any) => b.onclick = () => { state[k][b.dataset.k] = b.dataset.v; keep(k); render() });
    wirePeriod(k, w, render);
    w.body.querySelectorAll('[data-b]').forEach((el: any) => el.onclick = () => S.pick(el.dataset.b));
  };

  /* ---- Broker summary (EXEC-TERMINAL-BS-SIDE, user 2026-10-28: "dijajarin aja kiri dan kanan"; "Opsi B: Ringkas +
     % of value"): every broker of the period, the buyers on the left beside the sellers on the right like Top brokers,
     the largest first; per side the broker, its two values, the average prices and its share of the period's value.
     The CSV keeps every column. ---- */
  const COLS: [SumKey, string, string][] = [['b', 'Broker', ''], ['bl', 'Buy lot', 'Lots bought'], ['bv', 'Buy value', 'Value bought (Rp)'],
    ['ba', 'Buy avg', 'Average buy price = buy value ÷ (buy lots × 100)'], ['sl', 'Sell lot', 'Lots sold'], ['sv', 'Sell value', 'Value sold (Rp)'],
    ['sa', 'Sell avg', 'Average sell price = sell value ÷ (sell lots × 100)'], ['nv', 'Net value', 'Buy value − sell value'],
    ['nl', 'Net lot', 'Buy lots − sell lots'], ['share', '% of value', "The broker's buy + sell value ÷ the period's buy + sell value"]];
  const colOf = (k: SumKey) => COLS.find(c => c[0] === k)!;
  let bsTable: ReturnType<typeof sidesTable> | null = null;
  function renderBS(w: Win) {
    const st = state.bs, msg = blocked(), net = st.mode !== 'gross', scope = [st.inv === 'All' ? 'all investors' : st.inv, st.board === 'All' ? 'all boards' : st.board].join(' · ');
    const head = `<div class="pw-ctl">${periodCtl('bs')}${select('inv', st.inv, INVESTORS, 'All investors', 'Investor type')}${select('board', st.board, BOARDS, 'All boards', 'Board')}
      ${seg('mode', net ? 'net' : 'gross', [['net', 'Net'], ['gross', 'Gross']], 'Net or gross')}
      ${seg('limit', st.limit, [['10', 'Top 10'], ['20', 'Top 20'], ['all', 'All']], 'Rows')}
      <input class="rp-sel pw-search" type="search" placeholder="Search broker…" aria-label="Search broker" value="${esc(st.q)}" autocomplete="off"></div>`;
    const span = msg ? null : resolve(st.p);
    if (msg || !span) {
      w.body.innerHTML = head + `<div class="rp-empty">${msg || (st.p.n === 'view' ? 'No broker session in the chart’s view' : noSession(st.p))}</div>`;
      w.setSub(B().label + ' · ' + scope + tf); bsTable = null; wire(); return;
    }
    const [f, t] = span;
    bsTable = sidesTable(aggregate(B().rows, f, t, st.inv, st.board), { mode:net ? 'net' : 'gross', limit:st.limit === 'all' ? null : +st.limit, search:st.q });
    const { left, right } = bsTable, sel = S.selected();
    // the left side reads outward from its broker; the right side is its mirror, its broker on the far right
    const noIdx = (k: string) => !(IDX && ['nl', 'bl', 'sl', 'ba', 'sa'].includes(k));      // S-03: Rupiah only on an index
    const L: SumKey[] = (net ? ['b', 'nv', 'nl', 'ba', 'sa', 'share'] : ['b', 'bv', 'bl', 'ba', 'sa', 'share']).filter(noIdx) as SumKey[];
    const R: SumKey[] = (net ? ['b', 'nv', 'nl', 'ba', 'sa', 'share'] : ['b', 'sv', 'sl', 'ba', 'sa', 'share']).filter(noIdx).reverse() as SumKey[];
    const cell = (r: SumRow | undefined, k: SumKey, edge = '') => {
      if (!r) return `<td${edge}></td>`;
      const tot = r.b === 'Total', on = !tot && r.b === sel ? ' sel' : '', at = tot ? '' : ` data-b="${r.b}"`;
      // EXEC-QA5-FIX (S-04): the Total names how many brokers it sums (all of its side, not only the rows shown)
      const totText = (side: SumSide) => `Total · all ${side.count}`;
      const cls = (k === 'nv' || k === 'nl' ? (r[k] >= 0 ? 'up' : 'down') : '') + on;
      const v = k === 'b' ? (tot ? totText(r === left.total ? left : right) : bkTag(r.b)) : k === 'ba' || k === 'sa' ? price(r[k]) : k === 'share' ? r.share.toFixed(1) + '%'
        : k === 'nv' || k === 'nl' ? sgn(r[k]) : cv(r[k]);
      return `<td class="${cls.trim()}${edge}"${at}>${v}</td>`;
    };
    const half = (r: SumRow | undefined, keys: SumKey[], right: boolean) => keys.map((k, j) => cell(r, k, right && j === 0 ? ' pw-mid' : '')).join('');
    const th = (k: SumKey, right: boolean, j: number) => { const [, label0, tip0] = colOf(k), mid = right && j === 0 ? ' pw-mid' : '';
      // S-05: in Gross each side's share is of its own side
      const [label, tip] = k === 'share' && !net ? (right ? ['% of sell', "The broker's sell value ÷ the period's sell value"] : ['% of buy', "The broker's buy value ÷ the period's buy value"]) : [label0, tip0];
      if (k === 'b') return `<th class="${right ? 'r' : 'l'}">${right ? `${net ? 'Net sellers' : 'Sellers'}<i class="down"></i>` : `<i class="up"></i>${net ? 'Net buyers' : 'Buyers'}`}</th>`;
      return `<th class="${mid.trim()}"${tip ? ` data-tip="${label}|${tip}"` : ''}>${label}</th>` };
    const n = Math.max(left.rows.length, right.rows.length);
    const rows = Array.from({ length:n }, (_, i) => `<tr><td class="pw-rank">${i + 1}</td>${half(left.rows[i], L, false)}${half(right.rows[i], R, true)}</tr>`).join('');
    const word = net ? ['net buyers', 'net sellers'] : ['buyers', 'sellers'];
    w.body.innerHTML = head + (n ? `<div class="pw-scroll"><table class="pw-t pw-acc pw-bs"><thead><tr><th></th>${L.map((k, j) => th(k, false, j)).join('')}${R.map((k, j) => th(k, true, j)).join('')}</tr></thead>
      <tbody>${rows}</tbody><tfoot><tr><td class="pw-rank"></td>${half(left.total, L, false)}${half(right.total, R, true)}</tr></tfoot></table></div>
      <div class="pw-foot">${left.rows.length} of ${left.count} ${word[0]} · ${right.rows.length} of ${right.count} ${word[1]} · largest first${net ? '' : ' (buy value, sell value)'} · each Total sums every broker of its side · click a broker to add it to Broker inventory${st.board === 'Nego' || st.board === 'All' ? ' · Nego trades are priced by negotiation, so an average can sit outside the market range' : ''}</div>`
      : `<div class="rp-empty">${st.q ? 'No broker matches the search' : net && bsTable.total.bv > 0 ? 'Trades exist, but every broker nets to 0 (crossing)' : `No ${word[0]} or ${word[1]} in this period`}</div>`);
    w.setSub(`${B().label} · ${spanText(f, t)}${st.p.n === 'view' ? ' · follows chart' : ''} · ${scope}${tf}`);
    wire();
    function wire() {
      wireCtl('bs', w, () => renderBS(w));
      const q = w.body.querySelector('.pw-search') as HTMLInputElement | null;
      if (q) q.oninput = () => { st.q = q.value; renderBS(w); const n = w.body.querySelector('.pw-search') as HTMLInputElement; n.focus(); n.setSelectionRange(n.value.length, n.value.length) };
    }
  }
  const csvBS = () => {
    if (!bsTable) return '';
    const num = (side: string) => (r: SumRow) => [side, r.b, r.bl, r.bv, r.ba == null ? '' : +r.ba.toFixed(2), r.sl, r.sv, r.sa == null ? '' : +r.sa.toFixed(2), r.nv, r.nl, +r.share.toFixed(4)];
    const st = state.bs, net = st.mode !== 'gross', [lw, rw] = net ? ['Net buyer', 'Net seller'] : ['Buyer', 'Seller'];
    // S-07: what the table is, on the first line; S-03: no lots or averages for an index
    const span = resolve(st.p), keep = (r: any[]) => IDX ? r.filter((_, j) => ![2, 4, 5, 7, 9].includes(j)) : r;
    const context = `${B().label} · ${span ? spanText(span[0], span[1]) : ''} · ${st.inv === 'All' ? 'all investors' : st.inv} · ${st.board === 'All' ? 'all boards' : st.board} · ${net ? 'Net' : 'Gross'}`;
    return toCsv(keep(['Side', ...COLS.map(c => c[1])]), [...bsTable.left.rows.map(num(lw)), num(lw)(bsTable.left.total), ...bsTable.right.rows.map(num(rw)), num(rw)(bsTable.right.total), num('All')(bsTable.total)].map(keep), context);
  };

  /* ---- Top brokers: the period's largest net buyers beside its largest net sellers ---- */
  function renderAcc(w: Win) {
    const st = state.acc, msg = blocked();
    const head = `<div class="pw-ctl">${periodCtl('acc')}${select('inv', st.inv, INVESTORS, 'All investors', 'Investor type')}${select('board', st.board, BOARDS, 'All boards', 'Board')}
      ${IDX ? '' : seg('unit', st.unit, [['value', 'Value'], ['lot', 'Lot']], 'Unit')}${seg('limit', st.limit, [['10', 'Top 10'], ['20', 'Top 20']], 'Rows')}</div>`;
    const span = msg ? null : resolve(st.p);
    if (msg || !span) { w.body.innerHTML = head + `<div class="rp-empty">${msg || (st.p.n === 'view' ? 'No broker session in the chart’s view' : noSession(st.p))}</div>`; w.setSub(B().label + tf); wireCtl('acc', w, () => renderAcc(w)); return }
    const [f, t] = span, lot = !IDX && st.unit === 'lot', N = +st.limit;
    // EXEC-TERMINAL-TOPSPLIT: with All investors each bar is split into Domestic (solid) and Foreign (faded)
    const split = st.inv === 'All', part = (inv: string) => new Map(split ? aggregate(B().rows, f, t, inv, st.board).map(o => [o.b, lot ? o.bl - o.sl : o.bv - o.sv] as [string, number]) : []);
    const fm = part('Foreign'), dm = part('Domestic');
    const all = aggregate(B().rows, f, t, st.inv, st.board).map(o => ({ b:o.b, net:lot ? o.bl - o.sl : o.bv - o.sv, ba:avgPrice(o.bv, o.bl), sa:avgPrice(o.sv, o.sl), f:fm.get(o.b) || 0, d:dm.get(o.b) || 0 }));
    // QA F12: ties by code A-Z, as the panel
    const byCode = (a: any, b: any) => a.b < b.b ? -1 : a.b > b.b ? 1 : 0;
    const buy = all.filter(x => x.net > 0).sort((a, b) => b.net - a.net || byCode(a, b)).slice(0, N), sell = all.filter(x => x.net < 0).sort((a, b) => a.net - b.net || byCode(a, b)).slice(0, N);
    const mx = Math.max(1, ...buy.map(x => x.net), ...sell.map(x => -x.net)), sel = S.selected();
    const bar = (x: any, side: 'buy' | 'sell') => `<td class="pw-bar"><div class="trk ${side}">${!x ? '' : split ? splitFill(Math.abs(x.net) / mx * 100, x.f, x.d, side) : `<div class="fill" style="width:${(Math.abs(x.net) / mx * 100).toFixed(1)}%"></div>`}</div></td>`;
    const rows = Array.from({ length:Math.max(buy.length, sell.length) }, (_, i) => { const b = buy[i], s = sell[i];
      return `<tr><td class="pw-rank">${i + 1}</td><td>${b ? `<span class="pa-b${b.b === sel ? ' sel' : ''}" data-b="${b.b}">${bkTag(b.b)}</span>` : ''}</td><td class="up">${b ? sgn(b.net) : ''}</td>${IDX ? '' : `<td>${b ? price(b.ba) : ''}</td>`}${bar(b, 'buy')}${bar(s, 'sell')}
        ${IDX ? '' : `<td>${s ? price(s.sa) : ''}</td>`}<td class="down">${s ? sgn(s.net) : ''}</td><td>${s ? `<span class="pa-b${s.b === sel ? ' sel' : ''}" data-b="${s.b}">${bkTag(s.b)}</span>` : ''}</td></tr>` }).join('');
    w.body.innerHTML = head + (rows ? `<div class="pw-scroll"><table class="pw-t pw-acc"><thead><tr><th></th><th class="l"><i class="up"></i>Top accumulators</th><th>Net ${lot ? 'lot' : 'value'}</th>${IDX ? '' : '<th data-tip="Avg buy|Buy value ÷ (buy lots × 100)">Avg buy</th>'}<th></th>
        <th></th>${IDX ? '' : '<th data-tip="Avg sell|Sell value ÷ (sell lots × 100)">Avg sell</th>'}<th>Net ${lot ? 'lot' : 'value'}</th><th class="r">Top distributors<i class="down"></i></th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="pw-foot">Both bars share one scale · click a broker to add it to Broker inventory${split ? ' · ' + SPLIT_LEGEND : ''}</div>` : `<div class="rp-empty">No net buyer or seller in this period</div>`);
    w.setSub(`${B().label} · ${spanText(f, t)}${st.p.n === 'view' ? ' · follows chart' : ''}${tf}`);
    wireCtl('acc', w, () => renderAcc(w));
  }

  /* ---- Broker inventory: the chosen brokers over the chart's visible sessions, larger, with a table ---- */
  let invCross: ((d: string | null) => void) | null = null, invFilter: any = null;
  function renderInv(w: Win) {
    const st = state.inv, msg = blocked();
    if (!w.body.querySelector('.pw-invctl')) {          // the controls are built once, so the broker list stays open while it changes
      w.body.innerHTML = `<div class="pw-ctl pw-invctl"><div class="fl rp-fl pw-fl"></div>${select('inv', st.inv, INVESTORS, 'All investors', 'Investor type')}${select('board', st.board, BOARDS, 'All boards', 'Board')}
        ${IDX ? '' : seg('unit', st.unit, [['lot', 'Lot'], ['value', 'Value']], 'Unit')}${seg('view', st.view, [['cum', 'Cumulative'], ['day', 'Daily']], 'Cumulative or daily')}</div>
        <div class="rp-legend pw-legend"></div><div class="pw-inv"></div>`;
      invFilter = ctx.makeFilter(w.body.querySelector('.pw-fl') as HTMLElement, { title:'Broker', searchable:true, placeholder:'Search broker code…', grid:true, mono:true, max:S.max,
        getOptions:() => S.brokers().map(b => ({ id:b, label:b })), state:S.invSel,
        summary:(s: Set<string>) => s.size ? [...s].slice(0, 5).join(', ') : 'None', onChange:() => S.changed() });
      w.body.querySelectorAll('select[data-k]').forEach((s: any) => s.onchange = () => { st[s.dataset.k] = s.value; keep('inv'); renderInv(w) });
      w.body.querySelectorAll('button[data-k]').forEach((b: any) => b.onclick = () => {
        st[b.dataset.k] = b.dataset.v; keep('inv');
        w.body.querySelectorAll(`button[data-k=${b.dataset.k}]`).forEach((x: any) => { x.classList.toggle('active', x === b); x.setAttribute('aria-pressed', String(x === b)) });
        renderInv(w);
      });
    }
    invFilter?.refresh();
    const box = w.body.querySelector('.pw-inv') as HTMLElement, legend = w.body.querySelector('.pw-legend') as HTMLElement;
    invCross = null;
    const picks = [...S.invSel] as string[], span = msg ? null : visibleSpan();
    const scope = [st.inv, st.board].filter((v: string) => v !== 'All').join(' · ');
    w.setSub(`${B().label}${span ? ' · ' + spanText(span[0], span[1]) : ''} · follows chart${scope ? ' · ' + scope : ''}${IDX ? ' · Rupiah' : ''}${tf}`);
    if (msg) { legend.innerHTML = ''; box.innerHTML = `<div class="rp-empty">${msg}</div>`; return }
    const lot = !IDX && st.unit === 'lot', cum = st.view === 'cum';
    const series = span ? inventory(B().rows, span[0], span[1], picks, st.inv, st.board, lot ? 'lot' : 'value') : [];
    const val = (k: number) => cum ? series[k].cum : series[k].daily;
    const chips = (i: number | null) => picks.map((b, k) => { const v = series[k] ? (i === null ? val(k).at(-1) ?? 0 : val(k)[i]) : 0;
      return `<span class="rp-chip" style="--c:${S.colors[k]}"><i></i>${b}<b class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${sgn(v)}</b><button type="button" data-rm="${b}" aria-label="Remove ${b}">×</button></span>` }).join('');
    const paintLegend = (i: number | null) => { legend.innerHTML = chips(i) + (i === null ? '' : `<span class="pw-at">${longDay(B().dates[span![0] + i])}</span>`);
      legend.querySelectorAll('[data-rm]').forEach((x: any) => x.onclick = () => { S.invSel.delete(x.dataset.rm); S.changed() }) };
    paintLegend(null);
    if (!picks.length) { box.innerHTML = `<div class="rp-empty">Choose 1–${S.max} brokers to see their net buying.</div>`; return }
    if (!span) { box.innerHTML = `<div class="rp-empty">The chart’s view has no broker session; broker data covers ${longDay(B().dates[0])} – ${longDay(B().dates.at(-1)!)}.</div>`; return }
    const n = span[1] - span[0] + 1;
    if (n < 2) { box.innerHTML = `<div class="rp-empty">Zoom the chart out to at least 2 sessions with broker data.</div>`; return }
    /* the chart, drawn at the window's own pixel size so its text stays sharp */
    const W = Math.max(200, box.clientWidth || 640), H = Math.max(140, Math.min(420, (w.body.clientHeight || 480) - 230));
    const AX = 58, PB = 20, PT = 8, pw = W - AX - 8, ph = H - PB - PT;
    const flat = series.flatMap((_, k) => val(k)), lo = Math.min(0, ...flat), hi = Math.max(0, ...flat), sp = (hi - lo) || 1;
    const x = (i: number) => AX + i / (n - 1) * pw, y = (v: number) => PT + ph - (v - lo) / sp * ph;
    const ticks = niceTicks(lo, hi), d = B().dates;
    const xt = Array.from({ length:Math.min(6, n) }, (_, j) => Math.round(j * (n - 1) / Math.max(1, Math.min(6, n) - 1)));
    const svg = `<svg class="pw-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      ${ticks.map(v => `<line x1="${AX}" x2="${W - 8}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${v === 0 ? '#d4d4d4' : '#f0f0f0'}"${v === 0 ? ' stroke-dasharray="3 3"' : ''}/><text x="${AX - 6}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end">${v === 0 ? '0' : tickCompact(v)}</text>`).join('')}
      ${xt.map(i => `<text x="${x(i).toFixed(1)}" y="${H - 5}" text-anchor="${i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}">${new Date(d[span[0] + i] + 'T00:00:00Z').toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'2-digit', timeZone:'UTC' }).replace('Sept', 'Sep')}</text>`).join('')}
      ${series.map((_, k) => `<path d="${val(k).map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join('')}" fill="none" stroke="${S.colors[k]}" stroke-width="1.8"/>`).join('')}
      <line class="inv-xh" x1="0" x2="0" y1="${PT}" y2="${PT + ph}" stroke="#9ca3af" stroke-dasharray="3 3" visibility="hidden"/>
      <rect class="pw-hit" x="${AX}" y="0" width="${pw}" height="${H}" fill="transparent"/></svg>`;
    const u = lot ? 'lot' : 'Rp';
    const rows = series.map((s, k) => { const v = invStats(val(k)), a = s.agg;
      return `<tr data-b="${s.b}"><td><span class="rp-dot" style="background:${S.colors[k]}"></span><b class="pw-code">${s.b}</b></td><td class="${v.end >= 0 ? 'up' : 'down'}">${sgn(v.end)}</td><td>${sgn(v.hi)}</td><td>${sgn(v.lo)}</td>
        <td>${cv(lot ? a.bl : a.bv)}</td><td>${cv(lot ? a.sl : a.sv)}</td>${IDX ? '' : `<td>${price(avgPrice(a.bv, a.bl))}</td><td>${price(avgPrice(a.sv, a.sl))}</td>`}</tr>` }).join('');
    /* EXEC-QA5-FIX H2 (QA 2026-11-07, S-02): a cumulative line is net buying added up from the first session in view, not the
       shares held; it changes with the zoom, so the start date is said and the word "position" is not used */
    const from = longDay(d[span[0]]), word = cum ? `net since ${from}` : 'daily net';
    box.innerHTML = `<div class="pw-chart">${svg}</div>
      <table class="rp-t pw-t"><thead><tr><th>Broker</th><th data-tip="End|The ${word} on the last session in view (${u})">End</th><th data-tip="High|The highest ${word} (${u})">High</th><th data-tip="Low|The lowest ${word} (${u})">Low</th>
        <th>Bought (${u})</th><th>Sold (${u})</th>${IDX ? '' : '<th data-tip="Avg buy|Buy value ÷ (buy lots × 100)">Avg buy</th><th data-tip="Avg sell|Sell value ÷ (sell lots × 100)">Avg sell</th>'}</tr></thead><tbody>${rows}</tbody></table>
      <div class="pw-foot">${cum ? `Each line adds up the broker's net ${lot ? 'lots' : 'value'} from ${from}, the first session in view${viewStart() < B().dates[0] ? ' (broker data starts here)' : ''}: net buying since then, not the shares held. Zooming the chart changes the start.` : `Each point is the broker's net ${lot ? 'lots' : 'value'} on that session.`}</div>`;
    const svgEl = box.querySelector('svg') as SVGSVGElement, xh = svgEl.querySelector('.inv-xh') as SVGLineElement;
    const show = (i: number | null) => {
      if (i === null) { xh.setAttribute('visibility', 'hidden'); paintLegend(null); return }
      xh.setAttribute('x1', x(i).toFixed(1)); xh.setAttribute('x2', x(i).toFixed(1)); xh.setAttribute('visibility', 'visible'); paintLegend(i);
    };
    invCross = day => { const k = day ? d.indexOf(day.slice(0, 10)) : -1; show(k >= span[0] && k <= span[1] ? k - span[0] : null) };
    svgEl.addEventListener('pointermove', e => {
      const rc = svgEl.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - rc.left - AX) / pw * (n - 1))));
      const day = d[span[0] + i], ci = ctx.idxByTime.get(ctx.M.barOf ? ctx.M.barOf(day) ?? day : day);
      if (ci !== undefined) ctx.crosshairAt(ci);
      show(i);                                          // EXEC-TERMINAL-LAG: a code-set chart crosshair fires no event back here
    });
    svgEl.addEventListener('pointerleave', () => { ctx.crosshairAt(null); show(null) });
    box.querySelectorAll('tr[data-b]').forEach((tr: any) => tr.onclick = () => S.pick(tr.dataset.b));
  }

  /* ---- Foreign × Domestic map (EXEC-FD-WINDOW, user 2026-11-07: "Peta + jejak 20 sesi (opsi 2) dan ada toggle untuk switch
     it ke Tabel penggerak per sesi (opsi A)"; "pake seperti HTML terlampir"): the map with one point per session for the
     last 5, 10 or 20 sessions, each the chosen period (1D, 5D, 20D or the custom number of sessions) ending that session,
     beside a table of those points (Level) or of each session's change and the side that drove it (Change (Δ)). The
     Top N, the board and every figure are the panel's formula (fdAt). ---- */
  const pt = (v: number) => { const r = +v.toFixed(FD_DP); return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(FD_DP)} pt` };
  function renderFD(w: Win) {
    const st = state.fd, msg = blocked(), N = +st.top || 3, span = +st.span || 20;
    const head = `<div class="pw-ctl">${seg('p', st.p.n, [['1', '1D'], ['5', '5D'], ['20', '20D'], ['custom', 'Custom']], 'Period')}
      ${seg('top', st.top, [['3', 'Top 3'], ['5', 'Top 5'], ['10', 'Top 10']], 'Top N brokers')}
      ${seg('span', st.span, [['5', '5'], ['10', '10'], ['20', '20 sessions']], 'Sessions on the map')}
      ${seg('view', st.view, [['level', 'Level'], ['delta', 'Change (Δ)']], 'Table view')}${select('board', st.board, BOARDS, 'All boards', 'Board')}</div>`;
    const pr = msg ? null : resolve(st.p.n === 'view' ? { n:'5' } : st.p);
    if (msg || !pr) { w.body.innerHTML = head + `<div class="rp-empty">${msg || noSession(st.p)}</div>`; w.setSub(B().label + tf); wireCtl('fd', w, () => renderFD(w)); return }
    const d = B().dates, len = pr[1] - pr[0] + 1, board = st.board;
    /* EXEC-QA5-FIX (QA F4): every session stays in the list; one without buy value shows "—", has no point on the map and
       no change, so a change is never taken across it */
    const T: TrailPoint[] = fdTrail((f, t, inv) => aggregate(B().rows, f, t, inv, board), pr[1], len, span, N)
      .map(p => ({ d:d[p.t], x:p.x, y:p.y, r:p.r, empty:!(p.total > 0) }));
    w.setSub(`${B().label} · ${T.length ? `${trailDay(T[0].d)} – ${trailDay(T.at(-1)!.d)} · ` : ''}rolling ${len}D · Top ${N} · ${board === 'All' ? 'all boards' : board}${tf}`);
    const nEmpty = T.filter(p => p.empty).length;
    if (!T.length || nEmpty === T.length) { w.body.innerHTML = head + `<div class="rp-empty">No buy value in these sessions</div>`; wireCtl('fd', w, () => renderFD(w)); return }
    const lim = mapLimit(T.filter(p => !p.empty).flatMap(p => [p.x, p.y])), lv = st.view !== 'delta', to = `${len}D to`;
    const tag = (k: 'fx' | 'dm' | null) => k ? `<span class="tag fdw-${k}">${k === 'fx' ? 'Foreign' : 'Domestic'}</span>` : '<span class="fdw-none" data-tip="Driver|The verdict did not change">—</span>';
    const dash = (n: number) => '<td>—</td>'.repeat(n);
    // EXEC-QA5-FIX (QA F1-F3, F10): two decimals as Top brokers, the parts adding up on screen, colours and driver from them
    const table = lv
      ? `<thead><tr><th>${to}</th><th class="fdw-fx">Foreign</th><th class="fdw-dm">Domestic</th><th>Verdict</th></tr></thead><tbody>${T.map((p, i) => ({ p, i })).reverse().map(({ p, i }) => {
          if (p.empty) return `<tr data-i="${i}" class="fdw-gap" data-tip="${trailDay(p.d)}|No buy value in this period: no point and no change">${'<td>' + trailDay(p.d) + '</td>'}${dash(3)}</tr>`;
          const v = fdShown(p.x, p.y, p.r);
          return `<tr data-i="${i}"><td>${trailDay(p.d)}</td><td class="${fdCls(v.x)}">${fdPct(v.x)}</td><td class="${fdCls(v.y)}">${fdPct(v.y)}</td><td class="${fdCls(v.r)}">${fdPct(v.r)}</td></tr>` }).join('')}</tbody>`
      : `<thead><tr><th>${to}</th><th>Verdict</th><th>Δ Verdict</th><th class="fdw-fx">Δ Foreign</th><th class="fdw-dm">Δ Domestic</th><th data-tip="Driver|The side whose change is larger: Δ Verdict = Δ Foreign + Δ Domestic; Foreign on a tie, none when the verdict did not move">Driver</th></tr></thead><tbody>${trailDeltas(T).map((s, k) =>
        s.dr === null ? `<tr data-i="${s.i}" class="fdw-gap${k ? '' : ' cur'}"><td>${trailDay(s.d)}</td>${s.r === null ? '<td>—</td>' : `<td class="${fdCls(s.r)}">${fdPct(s.r)}</td>`}<td colspan="4" class="fdw-why">${s.r === null ? 'No buy value' : 'Session before has no buy value'}</td></tr>`
        : `<tr data-i="${s.i}"${k ? '' : ' class="cur"'}><td>${trailDay(s.d)}</td><td class="${fdCls(s.r!)}">${fdPct(s.r!)}</td><td class="${fdCls(s.dr)}">${pt(s.dr)}</td><td class="${fdCls(s.dx!)}">${pt(s.dx!)}</td><td class="${fdCls(s.dy!)}">${pt(s.dy!)}</td><td>${tag(s.driver)}</td></tr>`).join('')}</tbody>`;
    const gaps = nEmpty ? ` ${nEmpty} without buy value (—).` : '';
    const cap = lv ? `${T.length} session${T.length > 1 ? 's' : ''};${gaps} the list scrolls. Newest first.`
      : T.length > 1 ? `${T.length - 1} change${T.length > 2 ? 's' : ''};${gaps} the list scrolls. Δ = change from the session before, in percentage points. Δ Verdict = Δ Foreign + Δ Domestic.` : 'One session: no change to show yet.';
    w.body.innerHTML = head + `<div class="pw-fdw"><div class="pw-fd"><div class="pw-fd-map">${trailSvg(T, lim)}</div>
      <div class="pw-fd-side"><div class="pw-scroll"><table class="pw-t pw-fdt">${table}</table></div><p class="pw-foot">${cap}</p></div></div></div>`;
    wireCtl('fd', w, () => renderFD(w));
    const box = w.body.querySelector('.pw-fd-map') as HTMLElement;
    w.body.querySelectorAll('.pw-fdt tbody tr[data-i]').forEach((tr: any) => {
      tr.onpointerenter = () => { box.innerHTML = trailSvg(T, lim, +tr.dataset.i); tr.classList.add('hl') };
      tr.onpointerleave = () => { box.innerHTML = trailSvg(T, lim); tr.classList.remove('hl') };
    });
  }

  /* ---- opening, closing, docking ---- */
  const host: Record<Key, () => HTMLElement> = { bs:() => $('bsBody'), acc:() => $('accBody'), inv:() => $('invBody'), fd:() => $('fdBody') };
  const dock = (k: Key) => {
    if ($('workspace').classList.contains('right-collapsed')) $('rpExpand').click();
    const sec = host[k]().closest('.st') as HTMLElement;
    if (sec.classList.contains('collapsed')) (sec.querySelector('.st-head') as HTMLElement).click();
    sec.scrollIntoView({ block:'nearest', behavior:'smooth' });
    sec.classList.add('st-flash'); setTimeout(() => sec.classList.remove('st-flash'), 900);
  };
  function openKey(k: Key) {
    if (isWinOpen(k)) { getWin(k)!.front(); return }
    const n = KEYS.indexOf(k), rp = $('brokerPanel').getBoundingClientRect();
    // a cascade from the widest window's place left of the panel: each later window starts 36 px left of and below the
    // one before, so a part of every window stays in view to be clicked
    const s = SIZE[k], x = Math.max(16, (rp.left > 400 ? rp.left : innerWidth) - SIZE.bs.w - 24 - n * 36), y = 64 + n * 36;
    const w = openWin({ id:k, title:TITLE[k], w:s.w, h:s.h, x, y, minW:k === 'bs' ? 520 : 420, minH:280,
      tools:k === 'bs' ? [{ act:'csv', label:'Copy the table as CSV', icon:ICON.csv }] : [],
      onTool:async (act, btn) => {
        if (act !== 'csv') return;
        const text = csvBS(); if (!text) return;
        try { await navigator.clipboard.writeText(text); btn.title = 'Copied'; btn.classList.add('ok') }
        catch { btn.title = 'The browser did not allow copying'; btn.classList.add('err') }
        setTimeout(() => { btn.title = 'Copy the table as CSV'; btn.classList.remove('ok', 'err') }, 1500);
      },
      onDock:() => dock(k), onClose:() => { delete renders[k]; if (k === 'inv') { invCross = null; invFilter = null } remember() },
      onResize:() => { if (k === 'inv') renders.inv?.() } });
    w.el.addEventListener('pointermove', e => { const t = (e.target as HTMLElement).closest('[data-tip]') as HTMLElement | null; t ? ctx.showStTip(e.clientX, e.clientY, ctx.tipHtml(t.dataset.tip!)) : ctx.hideStTip() });
    w.el.addEventListener('pointerleave', ctx.hideStTip);
    renders[k] = k === 'bs' ? () => renderBS(w) : k === 'acc' ? () => renderAcc(w) : k === 'fd' ? () => renderFD(w) : () => renderInv(w);
    if (k === 'inv') S.ensureDefaults();
    renders[k]!(); remember();
  }

  /* the ⤢ button in each panel's header (a sibling of the header button: a button cannot hold another) */
  KEYS.forEach(k => {
    const sec = host[k]()?.closest('.st') as HTMLElement;
    if (!sec || sec.querySelector('.st-pop')) return;
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'icon-btn st-pop'; b.innerHTML = ICON.pop;
    b.title = `Open ${TITLE[k]} in a window`; b.setAttribute('aria-label', b.title);
    b.onclick = () => openKey(k);
    sec.classList.add('has-pop'); sec.appendChild(b);
  });

  /* every window redraws on new data, on a broker change, and (raf) on the chart's range */
  const all = () => Object.values(renders).forEach(r => r!());
  S.listen(all);
  let raf = 0;
  ctx.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    if (raf) return;
    raf = requestAnimationFrame(() => { raf = 0; renders.inv?.(); if (state.bs.p.n === 'view') renders.bs?.(); if (state.acc.p.n === 'view') renders.acc?.() });
  });
  ctx.chart.subscribeCrosshairMove((p: any) => invCross?.(p && p.time != null && p.point && p.point.x >= 0 ? keyOf(p.time) : null));
  let reopen: Key[] = [];
  try { reopen = JSON.parse(store.get(OPEN_KEY) || '[]') || [] } catch { /* none */ }
  reopen.filter(k => k in TITLE).forEach(openKey);
}
