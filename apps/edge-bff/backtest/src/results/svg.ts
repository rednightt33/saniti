/* The result views' SVG charts and their hover layer (backtest.html section 11: svg helpers, histogram, scatter, bars,
   line chart, one tooltip for every chart), the trade tooltip, and the small statistics the renderers derive for
   display (mean, sd, skew, kurtosis, quantile: the reference's section 9 helpers). */
import { $, cls, esc, fmtD, nf, PAL, pct, pctu, rp } from '../format.ts';

/** the calendar of the result on screen (the reference's DAYS): the renderers index it with the result's days */
export let DAYS: string[] = [];
export const setDays = (d: string[]) => { DAYS = d };

export const mean = (a: number[]) => a.reduce((s,x)=>s+x,0)/(a.length||1);
export const sd = (a: number[]) => { const m = mean(a); return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/((a.length-1)||1)) };
export const skew = (a: number[]) => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**3,0)/a.length };
export const kurt = (a: number[]) => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**4,0)/a.length };
export const quant = (a: number[], q: number) => { const s=[...a].sort((x,y)=>x-y); return s[Math.min(s.length-1, Math.max(0, Math.floor(q*(s.length-1))))] };

/* ---- svg helpers ---- */
export const svgW = 640;
/* ---- hover layer: one tooltip for every chart; content is built per chart from what that chart is for ---- */
/* ttH's title, labels and values are markup (the tooltip shows them as HTML): a caller passes a server string through esc() */
export const ttH = (title: string, rows: [string, string | number, string?][] = [], foot='') => `<div class="tt-t">${title}</div>${rows.map(([l,v,c])=>`<div class="tt-r"><span>${l}</span><b class="${c||''}">${v}</b></div>`).join('')}${foot?`<div class="tt-f">${foot}</div>`:''}`;
export const TT = (h: string) => `data-tt="${esc(h)}"`;
const LC = new Map<string, any>(); let lcSeq = 0;
const axisY = (lo: number, hi: number, H: number, pad: any, fmt: (v: number) => string | number, ticks=4, W=svgW) => { let g=''; for(let k=0;k<=ticks;k++){ const v=lo+(hi-lo)*k/ticks, y=pad.t+(1-(v-lo)/(hi-lo||1))*(H-pad.t-pad.b); g+=`<line x1="${pad.l}" x2="${W-pad.r}" y1="${y}" y2="${y}" stroke="var(--border)"/><text x="${pad.l-6}" y="${y+3}" text-anchor="end" font-size="11" fill="var(--text-3)">${fmt(v)}</text>` } return g };
/* histogram: each bin is a hover column; tooltip = range, count, share, cumulative share (+ normal expectation when drawn) */
export const histogram = (vals: number[], {bins=24, W=svgW, H=220, fmt=(v: number)=>nf(v*100,0)+'%', normal=false, marks=[] as [number, string, string][], unit='Trades', tip=null as null | ((a: number, b: number, c: number, x: { tot: number; cum: number; range: string }) => string)}={}) => {
  if(!vals.length) return '<div class="empty">No data</div>';
  const lo = quant(vals,.01), hi = quant(vals,.99), span = (hi-lo)||1e-6, bw = span/bins, cnt = new Array(bins).fill(0), tot = vals.length;
  vals.forEach(v => cnt[Math.max(0,Math.min(bins-1,Math.floor((v-lo)/bw)))]++);
  const pad = {l:36,r:10,t:10,b:24}, mx = Math.max(...cnt), x = (v: number) => pad.l+(v-lo)/span*(W-pad.l-pad.r), y = (c: number) => pad.t+(1-c/mx)*(H-pad.t-pad.b);
  const m = mean(vals), s = sd(vals), pdf = (v: number) => Math.exp(-(((v-m)/s)**2)/2)/(s*Math.sqrt(2*Math.PI));
  let g = axisY(0,mx,H,pad,v=>Math.round(v),4,W), cum = 0;
  cnt.forEach((c,k) => { const a = lo+k*bw, b = a+bw, x0 = x(a), x1 = x(b), mid = a+bw/2; cum += c;
    const range = k===0 ? `≤ ${fmt(b)}` : k===bins-1 ? `≥ ${fmt(a)}` : `${fmt(a)} to ${fmt(b)}`, exp = normal ? pdf(mid)*tot*bw : null;
    const html = tip ? tip(a,b,c,{tot,cum,range}) : ttH(range, [[unit, nf(c,0)], ['Share', pctu(c/tot,1)], ['At or below this bin', pctu(cum/tot,0)],
      ...(normal ? [['Normal would expect', nf(exp,1)], ['Actual ÷ expected', exp>.05 ? nf(c/exp,1)+'×' : '—', exp>.05 && c/exp>1.5 ? 'down' : '']] as [string, string, string?][] : [])], normal && exp>.05 && c/exp>1.5 ? 'More days here than a normal curve predicts — a fat tail.' : '');
    g += `<g class="hbin" ${TT(html)}><rect class="hhit" x="${x0}" y="${pad.t}" width="${Math.max(1,x1-x0)}" height="${H-pad.t-pad.b}"/><rect class="hbar" x="${x0+1}" y="${y(c)}" width="${Math.max(1,x1-x0-2)}" height="${H-pad.b-y(c)}" rx="2" fill="${mid>=0?PAL.up:PAL.dn}"/></g>` });
  if(normal){ let d = ''; for(let k=0;k<=80;k++){ const v = lo+span*k/80; d += (k?'L':'M')+x(v).toFixed(1)+' '+y(pdf(v)*tot*bw).toFixed(1) } g += `<path d="${d}" fill="none" stroke="var(--text)" stroke-width="1.5" stroke-dasharray="4 3" pointer-events="none"/>` }
  marks.forEach(([v,l,col],mi) => { if(v<lo||v>hi) return; g += `<g pointer-events="none"><line x1="${x(v)}" x2="${x(v)}" y1="${pad.t}" y2="${H-pad.b}" stroke="${col}" stroke-width="1.5" stroke-dasharray="${l==='0'?'':'4 3'}"/><text x="${x(v)+4}" y="${pad.t+10+mi*12}" font-size="11" fill="${col}">${l}</text></g>` });
  for(let k=0;k<=4;k++){ const v = lo+span*k/4; g += `<text x="${x(v)}" y="${H-6}" text-anchor="middle" font-size="11" fill="var(--text-3)">${fmt(v)}</text>` }
  return `<svg class="ch" viewBox="0 0 ${W} ${H}">${g}</svg>` };
/* scatter: every point carries its own tooltip (p.tt) and grows on hover */
export const scatter = (pts: { x: number; y: number; tt?: string }[], {W=svgW, H=260, xl='', yl='', fx=(v: number)=>nf(v*100,0)+'%', fy=(v: number)=>nf(v*100,0)+'%', diag=false}={}) => {
  if(!pts.length) return '<div class="empty">No trades</div>';
  const pad = {l:42,r:12,t:10,b:30}, xs = pts.map(p=>p.x), ys = pts.map(p=>p.y);
  let xlo = Math.min(0,...xs), xhi = Math.max(0,...xs), ylo = Math.min(0,...ys), yhi = Math.max(0,...ys); const xp=(xhi-xlo)*.05||.01, yp=(yhi-ylo)*.05||.01; xlo-=xp; xhi+=xp; ylo-=yp; yhi+=yp;
  const x = (v: number) => pad.l+(v-xlo)/(xhi-xlo)*(W-pad.l-pad.r), y = (v: number) => pad.t+(1-(v-ylo)/(yhi-ylo))*(H-pad.t-pad.b);
  let g = axisY(ylo,yhi,H,pad,fy,4,W);
  g += `<line x1="${x(0)}" x2="${x(0)}" y1="${pad.t}" y2="${H-pad.b}" stroke="var(--border-2)"/><line x1="${pad.l}" x2="${W-pad.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--border-2)"/>`;
  if(diag){ const a = Math.max(xlo,ylo), b = Math.min(xhi,yhi); g += `<line x1="${x(a)}" y1="${y(a)}" x2="${x(b)}" y2="${y(b)}" stroke="var(--text-3)" stroke-dasharray="4 3"/>` }
  pts.forEach(p => g += `<circle class="pt" cx="${x(p.x).toFixed(1)}" cy="${y(p.y).toFixed(1)}" r="3.6" fill="${p.y>=0?PAL.up:PAL.dn}" ${p.tt?TT(p.tt):''}/>`);
  for(let k=0;k<=4;k++){ const v = xlo+(xhi-xlo)*k/4; g += `<text x="${x(v)}" y="${H-12}" text-anchor="middle" font-size="11" fill="var(--text-3)">${fx(v)}</text>` }
  g += `<text x="${(W+pad.l)/2}" y="${H}" text-anchor="middle" font-size="11" fill="var(--text-2)">${xl}</text><text transform="translate(10 ${H/2}) rotate(-90)" text-anchor="middle" font-size="11" fill="var(--text-2)">${yl}</text>`;
  return `<svg class="ch scat" viewBox="0 0 ${W} ${H}">${g}</svg>` };
/* bars: each category is one hover column (whole height), tooltip from it.tt or the series values */
export const bars = (items: any[], {W=svgW, H=220, fmt=(v: number)=>nf(v*100,0)+'%' as string | number, series=[['v',PAL.navy]] as [string, string][], names=null as string[] | null}={}) => {
  const pad = {l:40,r:10,t:10,b:24}, vals = items.flatMap(it=>series.map(([k])=>it[k]||0)), lo = Math.min(0,...vals), hi = Math.max(0,...vals), y = (v: number) => pad.t+(1-(v-lo)/((hi-lo)||1))*(H-pad.t-pad.b);
  const gw = (W-pad.l-pad.r)/items.length, bw = gw*.7/series.length;
  let g = axisY(lo,hi,H,pad,fmt,4,W);
  items.forEach((it,i) => { const html = it.tt || ttH(esc(it.l), series.map(([k],j)=>[names?names[j]:'Value', fmt(it[k]||0), (it[k]||0)>=0?'up':'down'] as [string, string | number, string]));
    g += `<g class="bgrp" ${TT(html)}><rect class="bhit" x="${pad.l+i*gw}" y="${pad.t}" width="${gw}" height="${H-pad.t-pad.b}"/>`;
    series.forEach(([k,col],j) => { const v = it[k]||0, x0 = pad.l+i*gw+gw*.15+j*bw; g += `<rect class="bbar" x="${x0}" y="${Math.min(y(0),y(v))}" width="${bw-2}" height="${Math.abs(y(v)-y(0))}" rx="2" fill="${col==='sign'?(v>=0?PAL.up:PAL.dn):col}"/>` });
    g += `</g><text x="${pad.l+i*gw+gw/2}" y="${H-6}" text-anchor="middle" font-size="11" fill="var(--text-3)" pointer-events="none">${esc(it.l)}</text>` });
  return `<svg class="ch" viewBox="0 0 ${W} ${H}">${g}</svg>` };
/* line chart: crosshair snaps to the nearest point, dots mark each series, tooltip from opts.tip(k) */
export const lineChart = (lines: { v: number[]; c: string; w?: number; dash?: boolean }[], {W=svgW, H=200, fmt=(v: number)=>nf(v,2), zero=true, labels=null as [number, string][] | null, area=null as [number[], number[], string] | null, tip=null as null | ((k: number) => string)}={}) => {
  const pad = {l:40,r:10,t:10,b:22}, all = lines.flatMap(l=>l.v.filter(isFinite)); let lo = Math.min(...all), hi = Math.max(...all); if(zero){ lo = Math.min(lo,0); hi = Math.max(hi,0) }
  const n = Math.max(...lines.map(l=>l.v.length)), x = (k: number) => pad.l+k/(n-1||1)*(W-pad.l-pad.r), y = (v: number) => pad.t+(1-(v-lo)/((hi-lo)||1))*(H-pad.t-pad.b);
  let g = axisY(lo,hi,H,pad,fmt,4,W);
  if(area){ const [a,b,col] = area; let d = ''; a.forEach((v,k)=> d += (k?'L':'M')+x(k).toFixed(1)+' '+y(v).toFixed(1)); for(let k=b.length-1;k>=0;k--) d += 'L'+x(k).toFixed(1)+' '+y(b[k]).toFixed(1); g += `<path d="${d}Z" fill="${col}"/>` }
  lines.forEach(l => { let d = ''; l.v.forEach((v,k) => { if(isFinite(v)) d += (d?'L':'M')+x(k).toFixed(1)+' '+y(v).toFixed(1) }); g += `<path d="${d}" fill="none" stroke="${l.c}" stroke-width="${l.w||1.6}" ${l.dash?'stroke-dasharray="4 3"':''}/>` });
  if(labels) labels.forEach(([k,t]) => g += `<text x="${x(k)}" y="${H-5}" text-anchor="middle" font-size="11" fill="var(--text-3)">${esc(t)}</text>`);
  let hov = '';
  if(tip){ const id = 'lc'+(++lcSeq); LC.set(id, {n, W, pad, tip, ys:lines.map(l=>l.v.map(v=>isFinite(v)?y(v):null)), cols:lines.map(l=>l.c), x});
    hov = `<g class="lc-ui" data-for="${id}" style="display:none" pointer-events="none"><line class="lc-x" y1="${pad.t}" y2="${H-pad.b}" stroke="var(--text-3)" stroke-dasharray="3 3"/>${lines.map(l=>`<circle r="4" fill="${l.c}" stroke="var(--surface)" stroke-width="2"/>`).join('')}</g><rect class="lc-hit" data-lc="${id}" x="${pad.l}" y="${pad.t}" width="${W-pad.l-pad.r}" height="${H-pad.t-pad.b}" fill="transparent"/>` }
  return `<svg class="ch" viewBox="0 0 ${W} ${H}">${g}${hov}</svg>` };
/* delegated handlers: one place shows / positions / hides the tooltip */
const tipShow = (html: string, e: MouseEvent) => { const t = $('tip'); t.innerHTML = html; t.hidden = false; t.classList.add('rich');
  const w = t.offsetWidth, h = t.offsetHeight; let L = e.clientX + 14, T = e.clientY + 14; if(L + w > innerWidth - 8) L = e.clientX - w - 14; if(T + h > innerHeight - 8) T = e.clientY - h - 14; t.style.left = Math.max(8,L)+'px'; t.style.top = Math.max(8,T)+'px' };
const tipHide = () => { const t = $('tip'); if(t.classList.contains('rich')){ t.hidden = true; t.classList.remove('rich') } };
export const bindHover = () => {
  document.addEventListener('mousemove', e => {
    const tg = e.target as Element, hit = tg.closest && tg.closest('.lc-hit') as SVGElement;
    document.querySelectorAll<HTMLElement>('.lc-ui').forEach((u: HTMLElement) => { if(!hit || u.dataset.for!==hit.dataset.lc) u.style.display = 'none' });
    if(hit){ const d = LC.get(hit.dataset.lc); if(!d) return; const svg = (hit as SVGGraphicsElement).ownerSVGElement, r = svg.getBoundingClientRect(), lx = (e.clientX - r.left) / r.width * d.W;
      const k = Math.max(0, Math.min(d.n-1, Math.round((lx - d.pad.l) / (d.W - d.pad.l - d.pad.r) * (d.n-1)))), ui = svg.querySelector(`.lc-ui[data-for="${hit.dataset.lc}"]`) as HTMLElement, px = d.x(k);
      ui.style.display = ''; const ln = ui.querySelector('.lc-x'); ln.setAttribute('x1', px); ln.setAttribute('x2', px);
      ui.querySelectorAll('circle').forEach((c: SVGCircleElement,j) => { const yy = d.ys[j][k]; c.style.display = yy==null ? 'none' : ''; if(yy!=null){ c.setAttribute('cx', px); c.setAttribute('cy', yy) } });
      tipShow(d.tip(k), e); return }
    const el = tg.closest && tg.closest('[data-tt]') as HTMLElement;
    if(el) tipShow(el.dataset.tt, e); else tipHide() }, {passive:true});
  document.addEventListener('scroll', tipHide, true);
};
/* shared trade tooltip (used by every trade-level chart) */
export const tradeTT = (t: any, extra: [string, string | number, string?][] = []) => ttH(`${esc(t.tk)} · ${esc(fmtD(DAYS[t.ei]))} → ${esc(fmtD(DAYS[t.xi]))}`, [['Return', pct(t.ret,2), cls(t.ret)], ['P&L', rp(t.pnl), cls(t.pnl)], ['Worst move against (MAE)', pct(t.mae,1), 'down'], ['Best move in favour (MFE)', pct(t.mfe,1), 'up'], ...extra, ['Days held', t.bars], ['Exit', esc(t.why)]]);
export const labelsFor = (eq: [number, number][]) => { const out: [number, string][] = []; let last = ''; eq.forEach(([i],k) => { const y = DAYS[i].slice(0,4); if(y!==last){ last = y; out.push([k, y]) } }); return out };
