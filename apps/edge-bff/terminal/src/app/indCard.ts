/* EXEC-IND-CARDS IC2 (user go 2026-11-01; mockup verification/terminal_api/indicator_cards/indicator_cards_review.html,
   approved with tabs "Saya minta opsi pertama adalah kalkulator, kedua adalah grafik, ketiga adalah langkah. Ini dibuat
   jadi satu card saja dengan tab untuk ketiganya"; "2b": formula, parameters and cautions as a note under Langkah).

   The card of one indicator, on the ticker and the date the Terminal shows ("samakan dengan bagaimana formula dihitung di
   terminal"). Nothing here computes an indicator: the numbers come from the indicator's own definition (def.compute,
   the series the chart draws; def.explain, calc/explain*.ts, whose value equals the chart's), the formula and the
   specification notes from data/indNotes.json (scripts/build_indicator_notes.py), the parameters from the registries,
   and the cautions from the indicator's parameters.
     Kalkulator  the value, the last step with its terms on sliders, and the parameters (the chart is not changed)
     Grafik      the indicator over the last candles to the date, with the price, its reference lines and marked points
     Langkah     the steps from the data to the value, then the formula, the parameters and the cautions
   Opened from the indicator menu's info button and from an indicator's legend row. */
import NOTES from '../data/indNotes.json';
import { fmt, type Explanation, type Term } from '../calc/explain';
import type { Ctx } from './context';
import { flowPlace, type MenuItem } from './indMenu';
import { FLOW_REG } from './flowIndicators';
import { draggable, fitInView } from './draggable';
import * as spec from '../data/specFormat';

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const dayText = (d: string) => { const t = new Date(d.slice(0, 10) + 'T00:00:00Z'); return isNaN(+t) ? d : t.toLocaleDateString('id-ID', { day:'numeric', month:'short', year:'numeric', timeZone:'UTC' }) + (d.length > 10 ? ' ' + d.slice(11, 16) : '') };
const TABS = ['Kalkulator', 'Grafik', 'Langkah'] as const;

export interface CardSource { def: any; params: Record<string, any>; onChart: boolean; outs: any[] }
interface State { output: string; t: number; tab: number; params: Record<string, any> }

/** the menu row of an indicator definition (an instance's legend row opens the card with it) */
export function itemOfDef(def: any): MenuItem {
  if (def.flow) {
    const r = FLOW_REG.indicators.find(x => x.id === def.id)!;
    return { id:r.id, name:r.name, group:r.family, kind:'Flow', place:flowPlace(r.place), unit:r.unit || '', tip:r.tip || '' };
  }
  const r = def.reg || {};
  return { id:r.id || def.id, name:def.name, group:String(r.cat || '').replace('PriceVolume', 'Price & Volume'), kind:r.id ? 'Technical' : 'Base',
    place:r.zone === 'overlay' ? 'Overlay' : 'Panel', unit:r.unit || '', tip:r.tip || '' };
}

/** the outputs a card can explain: the plotted numeric outputs, in the chart's order */
function outputsOf(src: CardSource, out: Record<string, any>): string[] {
  const keys = Object.keys(out).filter(k => !k.startsWith('_') && Array.isArray(out[k]));
  const ordered = (src.outs || []).map((o: any) => o.k).filter((k: string) => keys.includes(k));
  return ordered.length ? ordered : keys;
}
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** the card writes every number by the EDGE Design Spec v1.2 rules (data/specFormat.ts, user 2026-11-01), chosen from the
    indicator's unit as the legend and the pane axis are */
export function cardFormat(unit: string): (v: number) => string {
  return spec.byUnit(unit);
}

/* ---- the cautions that follow from the indicator's parameters and the chart (not typed per indicator) ---- */
function cautions(ctx: Ctx, item: MenuItem, src: CardSource): string[] {
  const out: string[] = [], tf = ctx.M.tf || 'D', N = ctx.dates.length;
  if (item.kind === 'Flow') {
    const r: any = FLOW_REG.indicators.find(x => x.id === item.id), keys = new Set((r?.params || []).map((q: any) => q.key));
    const p = src.params;
    out.push('Candle tanpa data broker tidak punya nilai (kosong, bukan 0).');
    if (ctx.brokerEnd >= 0 && ctx.brokerEnd < N - 1) out.push(`Data broker terakhir: ${dayText(ctx.dates[ctx.brokerEnd])}; candle sesudahnya kosong sampai data berikutnya dimuat.`);
    if (r?.needs_frequency) out.push('Butuh jumlah transaksi (frekuensi) di file broker; candle yang tidak punya angka itu kosong.');
    const anchored = (r?.params || []).some((q: any) => q.kind === 'date');
    if (keys.has('top') && anchored) out.push('Kelompok broker dipilih sekali dari seluruh periode di chart (sampai candle terakhir): angkanya memakai informasi sesudah tanggal itu.');
    else if (keys.has('top') && (p.scope ?? 'topn') === 'topn') out.push('Kelompok Top-N dihitung ulang di setiap candle; anggotanya bisa berganti dari hari ke hari.');
    if (keys.has('baseline')) out.push(`Butuh ${p.baseline ?? ''} candle sebelumnya sebagai pembanding; sebelum itu nilainya kosong.`.replace('Butuh  ', 'Butuh '));
    if (Array.isArray(p.boards) && p.boards.some((b: string) => b !== 'Regular')) out.push('Transaksi papan Nego dan Tunai (sering transaksi blok) ikut dihitung.');
  } else {
    const n = NOTES.technical[item.id as keyof typeof NOTES.technical] as any;
    for (const x of n?.notes || []) out.push(x);
    const lens = Object.entries(src.params).filter(([k, v]) => /length|period|window/.test(k) && isNum(v)).map(([, v]) => v as number);
    if (lens.length) out.push(`Nilai kosong sampai ada cukup candle untuk jendela terpanjang (${Math.max(...lens)} candle).`);
    if (/EMA|RMA|Wilder|seed|\[t-1\]/.test(n?.formula || '')) out.push('Nilai berantai: dihitung dari seluruh riwayat sejak data pertama, jadi angka awal yang dipakai (seed) ikut memengaruhi.');
  }
  if (tf === 'W' || tf === 'M') out.push(`Di grafik ${tf === 'W' ? 'mingguan' : 'bulanan'}, satu candle menjumlahkan atau merangkum sesi-sesinya.`);
  if (ctx.M.intraday && item.kind === 'Flow') out.push('Di grafik intraday angka Flow tetap harian: setiap candle menampilkan angka sesinya.');
  return out;
}

/* ---- the chart tab: inline SVG of the price and the indicator over the last candles to t ---- */
function chartSvg(ctx: Ctx, item: MenuItem, series: Record<string, any[]>, outs: string[], main: string, t: number, guides: number[], fmtV: (v: number) => string) {
  const W = 420, padL = 8, padR = 56, a = Math.max(0, t - 79), idx = Array.from({ length:t - a + 1 }, (_, k) => a + k);
  const flowPlaceOf = item.kind === 'Flow' ? (FLOW_REG.indicators.find(r => r.id === item.id)?.place || 'pane') : '';
  const overlay = item.place === 'Overlay' && flowPlaceOf !== 'marker';     // a Flow mark is a 0/1 flag: a band of its own
  const top1 = 16, h1 = overlay ? 170 : 62, gap = 20, top2 = top1 + h1 + gap, h2 = overlay ? 0 : 120, H = (overlay ? top1 + h1 : top2 + h2) + 22;
  const x = (k: number) => padL + (idx.length < 2 ? 0 : k * (W - padL - padR) / (idx.length - 1));
  const close = idx.map(i => ctx.ohlc[i]?.close);
  const lines = outs.slice(0, 4).map(k => ({ k, v:idx.map(i => isNum(series[k]?.[i]) ? series[k][i] as number : null) }));
  const scale = (vals: (number | null | undefined)[], top: number, h: number, extra: number[] = []) => {
    const v = [...vals.filter(isNum), ...extra]; let lo = Math.min(...v), hi = Math.max(...v);
    if (!isFinite(lo)) { lo = 0; hi = 1 } if (hi === lo) { hi += 1; lo -= 1 }
    return (y: number) => top + h - (y - lo) / (hi - lo) * h;
  };
  const path = (vals: (number | null | undefined)[], f: (y: number) => number) => {
    let d = '', pen = false;
    vals.forEach((v, k) => { if (isNum(v)) { d += `${pen ? 'L' : 'M'}${x(k).toFixed(1)},${f(v).toFixed(1)}`; pen = true } else pen = false });
    return d;
  };
  const COL = ['var(--accent)', '#f57c00', '#7928ca', '#12a594'];
  const yc = overlay ? scale([...close, ...lines.flatMap(l => l.v)], top1, h1) : scale(close, top1, h1);
  const yv = overlay ? yc : scale(lines.flatMap(l => l.v), top2, h2, guides);
  const m = lines.find(l => l.k === main) || lines[0];
  let hiK = -1, loK = -1;
  m?.v.forEach((v, k) => { if (!isNum(v)) return; if (hiK < 0 || v > (m.v[hiK] as number)) hiK = k; if (loK < 0 || v < (m.v[loK] as number)) loK = k });
  const last = idx.length - 1;
  const dot = (k: number, lab: string, below: boolean) => !m || !isNum(m.v[k]) ? '' :
    `<circle cx="${x(k)}" cy="${yv(m.v[k] as number)}" r="3.4" fill="var(--text)"/><text x="${Math.min(W - padR - 2, Math.max(padL + 2, x(k)))}" y="${yv(m.v[k] as number) + (below ? 14 : -7)}" font-size="10" font-weight="600" fill="var(--text)" text-anchor="${k > idx.length * .7 ? 'end' : 'start'}" paint-order="stroke" stroke="var(--surface)" stroke-width="3">${esc(lab)}</text>`;
  const axis = (f: (y: number) => number, v: number, txt: string) => `<line x1="${padL}" x2="${W - padR}" y1="${f(v)}" y2="${f(v)}" stroke="var(--border-2)" stroke-dasharray="3 3"/><text x="${W - padR + 4}" y="${f(v) + 3}" font-size="9" fill="var(--text-3)">${esc(txt)}</text>`;
  const cl = close.filter(isNum) as number[];
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(item.name)} dan harga ${esc(ctx.SYMBOL)}">
    <text x="${padL}" y="10" font-size="9" fill="var(--text-3)">${esc(overlay ? `${ctx.SYMBOL} dan ${item.name}` : `Close ${ctx.SYMBOL}`)}</text>
    ${cl.length ? `<text x="${W - padR + 4}" y="${yc(Math.max(...cl)) + 3}" font-size="9" fill="var(--text-3)">${esc(fmt.num(Math.max(...cl), 0))}</text><text x="${W - padR + 4}" y="${yc(Math.min(...cl)) + 3}" font-size="9" fill="var(--text-3)">${esc(fmt.num(Math.min(...cl), 0))}</text>` : ''}
    <path d="${path(close, yc)}" fill="none" stroke="var(--text-3)" stroke-width="1.3"/>
    ${overlay ? '' : `<text x="${padL}" y="${top2 - 5}" font-size="9" fill="var(--text-3)">${esc(item.name)}</text>${guides.map(g => axis(yv, g, fmtV(g))).join('')}`}
    ${lines.map((l, j) => `<path d="${path(l.v, yv)}" fill="none" stroke="${COL[j]}" stroke-width="${l.k === main ? 1.9 : 1.2}"/>`).join('')}
    ${hiK >= 0 && hiK !== last ? dot(hiK, fmtV(m.v[hiK] as number), false) : ''}${loK >= 0 && loK !== last && loK !== hiK ? dot(loK, fmtV(m.v[loK] as number), true) : ''}${dot(last, fmtV((m?.v[last] ?? 0) as number), false)}
    <text x="${padL}" y="${H - 5}" font-size="9" fill="var(--text-3)">${esc(dayText(ctx.dates[a]))}</text>
    <text x="${W - padR}" y="${H - 5}" font-size="9" fill="var(--text-3)" text-anchor="end">${esc(dayText(ctx.dates[t]))}</text>
  </svg>`;
}

/** the terms' keys as whole words of the formula line (a key `n` never matches inside another word) */
export function termWords(terms: Term[]): RegExp {
  const keys = [...terms].map(x => x.key).sort((a, b) => b.length - a.length).map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`(?<![\\p{L}\\p{N}_])(${keys.join('|')})(?![\\p{L}\\p{N}_])`, 'gu');
}

/* ---- the calculator's slider range for a term: around its value, never across zero for a one-signed term ---- */
function rangeOf(x: Term, all: Term[]): [number, number, number] {
  const v = x.value, ref = Math.max(...all.map(y => Math.abs(y.value)).filter(n => n > 0), 1);
  if (x.unit === 'count') { const hi = Math.max(3, Math.ceil(v * 3)); return [Math.max(0, x.key === 'n' ? 1 : 0), hi, 1] }
  const lo = v > 0 ? 0 : v < 0 ? 3 * v : -ref, hi = v > 0 ? 3 * v : v < 0 ? 0 : ref;
  return [lo, hi, (hi - lo) / 400 || 1];
}

/** render the card of `item` into `host`; `uid` = the chart instance whose parameters it reads (else the first one) */
export function renderCard(host: HTMLElement, ctx: Ctx, item: MenuItem, src: CardSource) {
  const def = src.def, N = ctx.dates.length;
  const compute = (p: Record<string, any>) => { try { return def.compute ? def.compute(p) || {} : {} } catch { return {} } };
  let series = compute(src.params);
  const outs0 = outputsOf(src, series);
  const startAt = (out: string) => {
    let t = Math.min(isNum(ctx.lastTipIdx) && ctx.lastTipIdx >= 0 ? ctx.lastTipIdx : N - 1, N - 1);
    for (let k = 0; t >= 0 && k < 600 && !isNum(series[out]?.[t]); k++) t--;
    return t < 0 ? N - 1 : t;
  };
  const st: State = { output:outs0[0] || '', t:startAt(outs0[0] || ''), tab:0, params:{ ...src.params } };
  const fmtV = cardFormat(item.unit);
  const notes: any = item.kind === 'Flow' ? (NOTES.flow as any)[item.id] : (NOTES.technical as any)[item.id];

  function explanation(): Explanation | null | undefined {
    if (!def.explain) return undefined;
    try { return def.explain(st.params, st.t, st.output) } catch { return null }
  }
  function head(e: Explanation | null | undefined) {
    const outs = outputsOf(src, series), title = def.title ? def.title(st.params) : item.name;
    return `<div class="icd-ex-h"><button type="button" class="icd-nav" data-nav="-1" aria-label="Candle sebelumnya">‹</button>
      <span>Contoh · ${esc(ctx.SYMBOL)} · ${esc(e?.span ? `${dayText(e.span.from)}–${dayText(e.span.to)}` : dayText(ctx.dates[st.t]))} · ${esc(title)}</span>
      <button type="button" class="icd-nav" data-nav="1" aria-label="Candle berikutnya">›</button></div>
      ${outs.length > 1 ? `<label class="icd-out">Output <select data-out>${outs.map(k => `<option value="${esc(k)}"${k === st.output ? ' selected' : ''}>${esc(outLabel(k))}</option>`).join('')}</select></label>` : ''}`;
  }
  const valueAt = () => series[st.output]?.[st.t];
  /* an output's name: Broker Inventory's lines are slots b1..b5 on the chart, named by their broker codes (_labels) */
  const outLabel = (k: string) => /^b\d$/.test(k) && Array.isArray(series._labels) ? series._labels[+k[1] - 1] || k : k === 'total' ? 'Total' : k;

  function calcPane(e: Explanation | null | undefined) {
    const v = valueAt();
    const big = `<div class="icd-big"><b data-big>${isNum(v) ? esc(fmtV(v)) : '–'}</b><span class="icd-delta" data-delta></span></div>`;
    const expr = e ? `<div class="icd-expr" data-expr></div>` : '';
    const sliders = e ? e.terms.map((x, j) => { const [lo, hi, step] = rangeOf(x, e.terms);
      return `<label class="icd-field"><span class="icd-fr">${esc(x.label)} <code>${esc(x.key)}</code><b data-tv="${j}"></b></span>
        <input type="range" data-term="${j}" min="${lo}" max="${hi}" step="${step}" value="${x.value}"></label>` }).join('') : '';
    const params = (def.inputs || []).filter((f: any) => f.kind === 'int' || f.kind === 'num').map((f: any) =>
      `<label class="icd-param"><span>${esc(f.label)}</span><input type="number" data-param="${esc(f.key)}" value="${esc(st.params[f.key])}" ${f.min !== undefined ? `min="${f.min}"` : ''} ${f.max !== undefined ? `max="${f.max}"` : ''} step="${f.kind === 'int' ? 1 : 'any'}"></label>`).join('');
    return `<div class="icd-box">${head(e)}${big}${expr}</div>
      ${e ? `<div class="icd-sub">Geser angka penyusunnya</div>${sliders}` : `<p class="icd-note">${def.explain ? `Tidak ada nilai di ${esc(dayText(ctx.dates[st.t]))}.` : 'Langkah hitung untuk indikator ini belum tersedia; angka di atas adalah angka di chart.'}</p>`}
      ${params ? `<div class="icd-sub">Parameter (hanya di kartu ini; chart tidak berubah)</div><div class="icd-params">${params}</div>` : ''}
      <div class="icd-row"><button type="button" class="icd-btn" data-reset>Kembali ke angka ${esc(ctx.SYMBOL)}</button></div>`;
  }
  function chartPane(e: Explanation | null | undefined) {
    const outs = outputsOf(src, series), m = series[st.output] || [];
    const guides = (def.reg?.guides || []).filter(isNum) as number[];
    const a = Math.max(0, st.t - 79), win = m.slice(a, st.t + 1);
    let hi = -1, lo = -1;
    win.forEach((v: any, k: number) => { if (!isNum(v)) return; if (hi < 0 || v > win[hi]) hi = k; if (lo < 0 || v < win[lo]) lo = k });
    const li = (k: number, what: string) => k < 0 ? '' : `<li><b>${esc(dayText(ctx.dates[a + k]))}</b>: ${what} ${esc(fmtV(win[k]))}</li>`;
    return `<div class="icd-chart">${chartSvg(ctx, item, series, outs, st.output, st.t, guides, fmtV)}</div>
      <ul class="icd-bul">${li(st.t - a, 'nilai di tanggal ini')}${li(hi, 'tertinggi dalam 80 candle terakhir')}${li(lo, 'terendah dalam 80 candle terakhir')}
        ${e?.span ? `<li>Setiap titik memakai ${e.span.candles} candle yang berakhir di tanggal itu.</li>` : ''}
        ${guides.length ? `<li>Garis putus-putus: garis acuan ${guides.map(g => esc(fmtV(g))).join(', ')}.</li>` : ''}</ul>`;
  }
  function stepsPane(e: Explanation | null | undefined) {
    const steps = e ? `<ol class="icd-steps">${e.steps.map(s => `<li><b>${esc(s.title)}</b><p>${esc(s.text)}</p>${s.table ? `<table class="icd-tbl"><thead><tr>${s.table.head.map((h, j) => `<th${j ? '' : ' class="l"'}>${esc(h)}</th>`).join('')}</tr></thead><tbody>${s.table.rows.map(r => `<tr>${r.map((c, j) => `<td${j ? '' : ' class="l"'}>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>${s.table.note ? `<p class="icd-note">${esc(s.table.note)}</p>` : ''}` : ''}</li>`).join('')}</ol>`
      : `<p class="icd-note">${def.explain ? `Tidak ada nilai di ${esc(dayText(ctx.dates[st.t]))}, jadi tidak ada langkah hitung.` : 'Langkah hitung dengan angka untuk indikator ini belum tersedia.'}</p>`;
    const inputs = (def.inputs || []).filter((f: any) => !['fixed', 'button', 'color'].includes(f.kind));
    const val = (v: any) => Array.isArray(v) ? (v.length ? v.join(', ') : 'semua') : v === undefined || v === null || v === '' ? '–' : String(v);
    const rng = (f: any) => Array.isArray(f.options) ? f.options.join(', ') : typeof f.options === 'function' ? '' : f.min !== undefined && f.kind !== 'select' ? `${f.min}–${f.max}` : '';
    const params = inputs.length ? `<table class="icd-tbl"><thead><tr><th class="l">Parameter</th><th>Dipakai</th><th>Default</th><th>Pilihan / rentang</th></tr></thead><tbody>${inputs.map((f: any) =>
      `<tr><td class="l">${esc(f.label)}</td><td>${esc(val(st.params[f.key]))}</td><td>${esc(val(f.def))}</td><td class="muted">${esc(rng(f))}</td></tr>`).join('')}</tbody></table>` : '<p class="icd-note">Tanpa parameter.</p>';
    const warn = cautions(ctx, item, { ...src, params:st.params });
    return `<div class="icd-box">${head(e)}</div>${steps}
      <div class="icd-notes"><h5>Rumus (seperti dihitung Terminal)</h5>
        <div class="icd-formula">${esc(notes?.formula || 'Tidak ada rumus di spesifikasi.')}</div>
        <h5>Parameter (default Terminal)</h5>${params}
        <p class="icd-note">Tampil ${item.place === 'Overlay' ? 'di atas grafik harga' : 'di panel sendiri di bawah grafik'}${item.unit ? `, satuan ${esc(item.unit)}` : ''}${src.onChart ? '; parameter "Dipakai" adalah milik indikator di chart' : ''}.</p>
        ${warn.length ? `<h5>Hati-hati</h5><ul class="icd-bul">${warn.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
        <p class="icd-note">Kode: <code>${item.kind === 'Flow' ? 'calc/flow.ts' : 'calc/indicators.ts'}</code> ${esc(item.kind === 'Flow' ? item.id : def.id)}; sumber rumus: ${esc(notes?.source || '–')}.</p></div>`;
  }

  function render() {
    const e = explanation();
    host.innerHTML = `<div class="icd" data-id="${esc(item.id)}">
      <div class="icd-h"><div class="icd-eyebrow">${esc(item.kind === 'Flow' ? 'Flow' : 'Technical')} · ${esc(item.group)}<span class="icd-code">${esc(item.kind === 'Base' ? '' : item.id)}</span></div>
        <h4>${esc(item.name)}</h4><p>${esc(def.reg?.info || item.tip)}</p></div>
      <div class="icd-tabs" role="tablist">${TABS.map((x, j) => `<button type="button" role="tab" data-tab="${j}" aria-selected="${j === st.tab}">${x}</button>`).join('')}</div>
      <div class="icd-pane" data-pane="0"${st.tab === 0 ? '' : ' hidden'}>${calcPane(e)}</div>
      <div class="icd-pane" data-pane="1"${st.tab === 1 ? '' : ' hidden'}>${chartPane(e)}</div>
      <div class="icd-pane" data-pane="2"${st.tab === 2 ? '' : ' hidden'}>${stepsPane(e)}</div></div>`;
    wire(e);
  }
  function wire(e: Explanation | null | undefined) {
    host.querySelectorAll<HTMLElement>('[data-tab]').forEach(b => b.onclick = () => {
      st.tab = +b.dataset.tab!;
      host.querySelectorAll<HTMLElement>('[data-tab]').forEach(x => x.setAttribute('aria-selected', String(x === b)));
      host.querySelectorAll<HTMLElement>('[data-pane]').forEach(p => p.hidden = p.dataset.pane !== b.dataset.tab);
    });
    host.querySelectorAll<HTMLElement>('[data-nav]').forEach(b => b.onclick = () => {
      const d = +b.dataset.nav!, m = series[st.output] || [];
      let t = st.t + d; while (t >= 0 && t < N && !isNum(m[t])) t += d;
      if (t >= 0 && t < N) { st.t = t; render() }
    });
    host.querySelectorAll<HTMLSelectElement>('[data-out]').forEach(s => s.onchange = () => { st.output = s.value; render() });
    let timer: any = null;
    host.querySelectorAll<HTMLInputElement>('[data-param]').forEach(i => i.oninput = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const f = (def.inputs || []).find((x: any) => x.key === i.dataset.param), v = Number(i.value);
        if (!f || !Number.isFinite(v) || (f.min !== undefined && v < f.min) || (f.max !== undefined && v > f.max)) return;
        st.params = { ...st.params, [f.key]:f.kind === 'int' ? Math.round(v) : v };
        series = compute(st.params); render();
      }, 300);
    });
    const reset = host.querySelector<HTMLElement>('[data-reset]');
    if (reset) reset.onclick = () => { st.params = { ...src.params }; series = compute(st.params); render() };
    if (!e) return;
    const vals = Object.fromEntries(e.terms.map(x => [x.key, x.value])), base = valueAt();
    const paint = () => {
      const v = e.combine(vals), big = host.querySelector<HTMLElement>('[data-big]')!, delta = host.querySelector<HTMLElement>('[data-delta]')!;
      big.textContent = v === null ? '–' : fmtV(v);
      delta.textContent = v !== null && isNum(base) && Math.abs(v - base) > 1e-12 * Math.max(1, Math.abs(base)) ? `asli ${fmtV(base)}` : '';
      const expr = e.expr.replace(termWords(e.terms), k => { const x = e.terms.find(y => y.key === k)!; return fmt.of(vals[k], x.unit) });
      host.querySelector<HTMLElement>('[data-expr]')!.textContent = `${e.expr}  =  ${expr}  =  ${v === null ? '–' : fmtV(v)}`;
      e.terms.forEach((x, j) => { const el = host.querySelector<HTMLElement>(`[data-tv="${j}"]`); if (el) el.textContent = fmt.of(vals[x.key], x.unit) });
    };
    host.querySelectorAll<HTMLInputElement>('[data-term]').forEach(i => i.oninput = () => { vals[e.terms[+i.dataset.term!].key] = Number(i.value); paint() });
    paint();
  }
  render();
}

/* ---- the card on its own (from an indicator's legend row) ---- */
let dialog: HTMLElement | null = null;
export function openCardDialog(ctx: Ctx, item: MenuItem, src: CardSource) {
  if (!dialog) {
    dialog = document.createElement('div');
    dialog.className = 'icd-back'; dialog.hidden = true;
    dialog.innerHTML = `<div class="icd-dlg" role="dialog" aria-modal="true" aria-label="Indicator card"><div class="icd-dlg-h"><span>Indicator card</span><button type="button" class="icd-x" aria-label="Close the card">×</button></div><div class="icd-dlg-b"></div></div>`;
    document.body.appendChild(dialog);
    draggable(dialog.querySelector('.icd-dlg'), dialog.querySelector('.icd-dlg-h'));   // user 2026-11-01: moved by its header
    const close = () => { dialog!.hidden = true };
    dialog.addEventListener('click', e => { if (e.target === dialog || (e.target as HTMLElement).closest('.icd-x')) close() });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && dialog && !dialog.hidden) { e.stopPropagation(); close() } }, true);
  }
  renderCard(dialog.querySelector('.icd-dlg-b') as HTMLElement, ctx, item, src);
  dialog.hidden = false;
  fitInView(dialog.querySelector('.icd-dlg'));
  (dialog.querySelector('[data-tab="0"]') as HTMLElement)?.focus();
}
