/* LEFT PANEL — Statistics (visible-range, collapsible, accordion), reference lines 1400-1655. */
import type { Ctx } from './context';
import { $, avgOf, cls, empty, median, pct, row, store } from './context';

export function initStats(ctx: Ctx) {
  const { chart, dates, closes, volume, N, SYMBOL } = ctx;
  const ws = ctx.ws = $('workspace');
  const LEFT_MIN = 240, LEFT_MAX = 560;
  let leftW = parseInt(store.get('ml.stats.w') as string,10) || 0;           // 0 = use the CSS default
  const clampW = (w: number) => Math.max(LEFT_MIN, Math.min(LEFT_MAX, Math.round((ws.clientWidth||1400)*.45), w));
  const applyLeftW = () => {
    if(leftW && !ws.classList.contains('left-collapsed')) ws.style.setProperty('--left-w', leftW+'px');
    else ws.style.removeProperty('--left-w');
  };
  const afterLeftResize = () => { scheduleStats() };
  const setLeftCollapsed = (c: boolean) => {
    ws.classList.toggle('left-collapsed', c);
    applyLeftW();
    $('statsCollapse').setAttribute('aria-expanded', String(!c));
    $('statsExpand').setAttribute('aria-expanded', String(!c));
    store.set('ml.stats.collapsed', c?'1':'0');
    if(!c) scheduleStats();
  };
  $('statsCollapse').onclick = () => setLeftCollapsed(true);
  $('statsExpand').onclick = () => setLeftCollapsed(false);

  {
    const rz = $('statsResize'), side = $('statsPanel');
    const setW = (w: number) => { leftW = clampW(w); applyLeftW(); afterLeftResize() };
    rz.addEventListener('pointerdown', (e: PointerEvent) => {
      e.preventDefault(); rz.setPointerCapture(e.pointerId);
      const x0 = e.clientX, w0 = side.getBoundingClientRect().width;
      ws.classList.add('resizing'); rz.classList.add('active');
      const mv = (ev: PointerEvent) => setW(w0 + ev.clientX - x0);
      const up = () => { rz.removeEventListener('pointermove', mv); rz.removeEventListener('pointerup', up); rz.removeEventListener('pointercancel', up);
        ws.classList.remove('resizing'); rz.classList.remove('active'); store.set('ml.stats.w', String(leftW)) };
      rz.addEventListener('pointermove', mv); rz.addEventListener('pointerup', up); rz.addEventListener('pointercancel', up);
    });
    rz.addEventListener('dblclick', () => { leftW = 0; applyLeftW(); store.set('ml.stats.w','0'); afterLeftResize() });
    rz.addEventListener('keydown', (e: KeyboardEvent) => {
      const cur = side.getBoundingClientRect().width;
      if(e.key==='ArrowLeft'){ setW(cur-16); e.preventDefault() } else if(e.key==='ArrowRight'){ setW(cur+16); e.preventDefault() }
      else if(e.key==='Home'){ setW(LEFT_MIN); e.preventDefault() } else if(e.key==='End'){ setW(LEFT_MAX); e.preventDefault() }
      store.set('ml.stats.w', String(leftW));
    });
  }

  /* ---- hover tip shared by every statistic ---- */
  const stTip = document.createElement('div'); stTip.className = 'st-tip'; stTip.hidden = true; document.body.appendChild(stTip);
  const hideStTip = ctx.hideStTip = () => { stTip.hidden = true };
  const showStTip = ctx.showStTip = (x, y, html) => {
    stTip.innerHTML = html; stTip.hidden = false;
    const w = stTip.offsetWidth, h = stTip.offsetHeight;
    let l = x + 14, t = y + 14;
    if(l + w > innerWidth - 8) l = x - w - 14;
    if(t + h > innerHeight - 8) t = y - h - 14;
    stTip.style.left = Math.max(8,l)+'px'; stTip.style.top = Math.max(8,t)+'px';
  };
  const tipHtml = ctx.tipHtml = s => { const [a,...r] = s.split('|'); return `<b>${a}</b>${r.length?' '+r.join(' '):''}` };
  $('statsPanel').addEventListener('pointermove', (e: any) => {
    if(e.target.closest('.lc-plot')) return;                       // line charts drive their own tip
    const t = e.target.closest('[data-tip]');
    t ? showStTip(e.clientX, e.clientY, tipHtml(t.dataset.tip)) : hideStTip();
  });
  $('statsPanel').addEventListener('pointerleave', hideStTip);
  $('leftScroll').addEventListener('scroll', hideStTip, {passive:true});

  let secState: Record<string, boolean> = {};
  try{ secState = JSON.parse(store.get('ml.stats.sections') || '{}') || {} }catch(e){}
  document.querySelectorAll<HTMLElement>('.st').forEach(sec => {
    const head = sec.querySelector('.st-head') as HTMLElement, key = sec.dataset.sec as string;
    const apply = (collapsed: boolean) => { sec.classList.toggle('collapsed', collapsed); head.setAttribute('aria-expanded', String(!collapsed)) };
    apply(!!secState[key]);
    head.onclick = () => {
      const c = !sec.classList.contains('collapsed');
      apply(c); secState[key] = c; store.set('ml.stats.sections', JSON.stringify(secState));
    };
  });

  /* ---- series derived once over the full history ---- */
  const dayRet = new Float64Array(N);                 // simple daily return
  const logRet = new Float64Array(N);
  for(let i=1;i<N;i++){ dayRet[i] = closes[i]/closes[i-1]-1; logRet[i] = Math.log(closes[i]/closes[i-1]); }
  const vol20 = new Float64Array(N).fill(NaN);        // 20-session annualized realized vol, %
  for(let i=20;i<N;i++){
    let m=0; for(let k=i-19;k<=i;k++) m+=logRet[k]; m/=20;
    let v=0; for(let k=i-19;k<=i;k++) v+=(logRet[k]-m)**2;
    vol20[i] = Math.sqrt(v/19*252)*100;
  }
  const volRatio = new Float64Array(N).fill(NaN);     // volume / trailing 20D average
  for(let i=19;i<N;i++){ let s=0; for(let k=i-19;k<=i;k++) s+=volume[k].value; volRatio[i] = volume[i].value/(s/20); }
  const ihsgSeries = ctx.M.ihsg;
  const monthKey = (i: number) => dates[i].slice(0,7);

  /* ---- inline-SVG chart helpers (viewBox is fixed, so they scale with the panel) ---- */
  const SW = 272, SH = 64;
  const histogram = (vals: number[], bins: number, colorFor: (c: number) => string, fmtEdge: (v: number) => string, unit='sessions', mark?: { v: number; label: string }) => {
    // range is clipped to the 2nd–98th percentile so a few extreme sessions don't squash the shape; outliers land in the edge bins
    const sorted = [...vals].sort((x,y)=>x-y), q = (p: number) => sorted[Math.min(sorted.length-1, Math.floor(p*(sorted.length-1)))];
    let lo = q(.02), hi = q(.98);
    if(hi-lo < 1e-9){ lo = sorted[0]-.5; hi = sorted.at(-1)!+.5 }
    const clipLo = sorted[0] < lo-1e-9, clipHi = sorted.at(-1)! > hi+1e-9;
    const counts = new Array(bins).fill(0);
    vals.forEach(v => counts[Math.max(0, Math.min(bins-1, Math.floor((v-lo)/(hi-lo)*bins)))]++);
    const cmax = Math.max(...counts), bw = SW/bins;
    const bars = counts.map((c,i) => {
      const h = c/cmax*(SH-4), center = lo+(i+.5)*(hi-lo)/bins;
      return `<rect x="${(i*bw+1).toFixed(1)}" y="${(SH-h).toFixed(1)}" width="${(bw-2).toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${colorFor(center)}"/>`;
    }).join('');
    const step = (hi-lo)/bins;
    const hits = counts.map((c,i) => {
      const e0 = lo+i*step, e1 = e0+step;
      const range = (i===0 && clipLo) ? `≤ ${fmtEdge(e1)}` : (i===bins-1 && clipHi) ? `≥ ${fmtEdge(e0)}` : `${fmtEdge(e0)} to ${fmtEdge(e1)}`;
      return `<rect class="hit" x="${(i*bw).toFixed(1)}" y="0" width="${bw.toFixed(1)}" height="${SH}" data-tip="${range}|${c} ${unit} · ${(c/vals.length*100).toFixed(1)}%"/>`;
    }).join('');
    // dotted vertical marker where the latest observation sits (clamped into the clipped range)
    let line = '', tag = '';
    if(mark){
      const f = Math.min(1, Math.max(0, (mark.v-lo)/(hi-lo))), x = (f*SW).toFixed(1);
      line = `<line class="mark" x1="${x}" x2="${x}" y1="0" y2="${SH}" vector-effect="non-scaling-stroke"/>`;
      const al = f < .14 ? 'l' : f > .86 ? 'r' : 'c';
      tag = `<span class="mark-tag ${al}" style="left:${(f*100).toFixed(1)}%">${mark.label}</span>`;
    }
    return { lo, hi, clipLo, clipHi, svg:`<div class="hist"><svg class="spark" viewBox="0 0 ${SW} ${SH}" preserveAspectRatio="none" aria-hidden="true">${bars}${hits}${line}</svg>${tag}</div>` };
  };
  const polyline = (data: number[], lo: number, hi: number, color: string, {dash='',width=1.5}={}) => {
    const span = (hi-lo)||1, n = data.length-1 || 1;
    const pts = data.map((v,i)=>`${(i/n*SW).toFixed(1)},${(SH-4-(v-lo)/span*(SH-8)).toFixed(1)}`).join(' ');
    return `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="${width}" ${dash?`stroke-dasharray="${dash}"`:''} stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
  };
  const areaPath = (data: number[], lo: number, hi: number, fill: string) => {
    const span = (hi-lo)||1, n = data.length-1 || 1;
    const pts = data.map((v,i)=>`${(i/n*SW).toFixed(1)},${(SH-4-(v-lo)/span*(SH-8)).toFixed(1)}`);
    return `<polygon points="0,${SH-4-(0-lo)/span*(SH-8)} ${pts.join(' ')} ${SW},${SH-4-(0-lo)/span*(SH-8)}" fill="${fill}"/>`;
  };
  const fmtDay = (i: number) => new Date(dates[i]+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'2-digit',timeZone:'UTC'});
  const fmtTick = (i: number, long: boolean) => { const d = new Date(dates[i]+'T00:00:00Z');
    return long ? d.toLocaleDateString('en-US',{month:'short',year:'2-digit',timeZone:'UTC'}).replace(' ', " '")
                : d.toLocaleDateString('en-GB',{day:'2-digit',month:'short',timeZone:'UTC'}) };
  const yPct = (v: number, lo: number, hi: number) => (SH-4-(v-lo)/((hi-lo)||1)*(SH-8))/SH*100;
  // c: { series:[{vals,color,dash}], idx:[session index per point], lo, hi, ticks:[...], zero?, area?, fmtY, tipFn(k) }
  const lineChart = (host: HTMLElement, c: any) => {
    const n = c.series[0].vals.length, last = n-1 || 1, long = (c.idx.at(-1)-c.idx[0]) >= 60;
    const grid = c.ticks.map((t: number) => { const y = (SH-4-(t-c.lo)/((c.hi-c.lo)||1)*(SH-8)).toFixed(1), z = c.zero!==undefined && Math.abs(t-c.zero)<1e-9;
      return `<line x1="0" x2="${SW}" y1="${y}" y2="${y}" stroke="${z?'#d4d4d4':'#f0f0f0'}" ${z?'stroke-dasharray="3 3"':''} vector-effect="non-scaling-stroke"/>` }).join('');
    const lines = c.series.map((s: any) => polyline(s.vals, c.lo, c.hi, s.color, {dash:s.dash||''})).join('');
    host.innerHTML = `<div class="lc"><div class="lc-y">${c.ticks.map((t: number)=>`<span style="top:${yPct(t,c.lo,c.hi).toFixed(1)}%">${c.fmtY(t)}</span>`).join('')}</div>`
      + `<div class="lc-plot"><svg class="spark" viewBox="0 0 ${SW} ${SH}" preserveAspectRatio="none" aria-hidden="true">${grid}${c.area||''}${lines}</svg><div class="xh"></div>${c.series.map((s: any)=>`<i class="dot" style="background:${s.color}"></i>`).join('')}</div>`
      + `<div class="lc-x"><span class="l">${fmtTick(c.idx[0],long)}</span><span class="c">${fmtTick(c.idx[Math.floor(last/2)],long)}</span><span class="r">${fmtTick(c.idx[last],long)}</span></div></div>`;
    const plot = host.querySelector('.lc-plot') as HTMLElement, xh = plot.querySelector('.xh') as HTMLElement, dots = [...plot.querySelectorAll<HTMLElement>('.dot')];
    const off = () => { xh.style.display = 'none'; dots.forEach(d => d.style.display = 'none'); hideStTip() };
    plot.onpointermove = e => {
      const r = plot.getBoundingClientRect(), f = Math.min(1, Math.max(0, (e.clientX-r.left)/r.width)), k = Math.round(f*last);
      xh.style.left = (k/last*100)+'%'; xh.style.display = 'block';
      dots.forEach((d,j) => { d.style.left = (k/last*100)+'%'; d.style.top = yPct(c.series[j].vals[k], c.lo, c.hi)+'%'; d.style.display = 'block' });
      showStTip(e.clientX, e.clientY, `<b>${fmtDay(c.idx[k])}</b> ${c.tipFn(k)}`);
    };
    plot.onpointerleave = off;
  };
  const axisLabels = (lo: number, hi: number, fmt: (v: number) => string, zero?: number, clip: { lo?: boolean; hi?: boolean }={}) => {
    let mid = '';
    const pos = zero===undefined ? -1 : (zero-lo)/(hi-lo);
    if(pos > .14 && pos < .86) mid = `<span class="c" style="left:${(pos*100).toFixed(1)}%">${fmt(zero as number)}</span>`;   // skip if it would collide with an edge label
    return `<span class="l">${clip.lo?'≤ ':''}${fmt(lo)}</span>${mid}<span class="r">${clip.hi?'≥ ':''}${fmt(hi)}</span>`;
  };

  /* ---- visible range ---- */
  const visRange = () => {
    const r = chart.timeScale().getVisibleLogicalRange();
    let a = 0, b = N-1;
    if(r){ a = Math.max(0, Math.ceil(r.from)); b = Math.min(N-1, Math.floor(r.to)); }
    if(b-a < 3) a = Math.max(0, b-3);
    return [a,b];
  };

  let seasMode = 'month';
  const renderSeasonality = (a: number, b: number) => {
    const el = $('seasBody');
    let rows: { k: string; v: number | null; n: number; unit: string }[] = [];
    if(seasMode === 'month'){
      // month return = last close of month / last close of previous month, using months that END inside the visible window
      const byMonth = new Map<string, { first: number; last: number }>();
      for(let i=1;i<N;i++){ const k = monthKey(i); const m = byMonth.get(k) || {first:i,last:i}; m.last = i; byMonth.set(k,m) }
      const buckets: number[][] = Array.from({length:12},()=>[]);
      byMonth.forEach(m => {
        if(m.last < a || m.last > b || m.first-1 < 0) return;
        buckets[+dates[m.last].slice(5,7)-1].push(closes[m.last]/closes[m.first-1]-1);
      });
      const names = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
      rows = buckets.map((x,i)=>({k:names[i], v:x.length ? avgOf(x)*100 : null, n:x.length, unit:'monthly observations'}));
    } else {
      const buckets: number[][] = [[],[],[],[],[]];
      for(let i=Math.max(1,a);i<=b;i++){ const d = new Date(dates[i]+'T00:00:00Z').getUTCDay(); if(d>=1&&d<=5) buckets[d-1].push(dayRet[i]) }
      const names = ['MON','TUE','WED','THU','FRI'];
      rows = buckets.map((x,i)=>({k:names[i], v:x.length ? avgOf(x)*100 : null, n:x.length, unit:'sessions'}));
    }
    const mx = Math.max(.05, ...rows.map(r=>Math.abs(r.v||0)));
    el.innerHTML = rows.map(r => {
      if(r.v === null) return `<div class="sz-row" data-tip="${r.k}|no data in range"><span class="k">${r.k}</span><div class="sz-track"></div><span class="sz-v">+0.0%</span></div>`;
      const w = Math.abs(r.v)/mx*50, left = r.v>=0 ? 50 : 50-w, c = r.v>=0 ? 'var(--up)' : 'var(--down)';
      return `<div class="sz-row" data-tip="${r.k}|avg ${pct(r.v,2)} · ${r.n} ${r.unit}"><span class="k">${r.k}</span><div class="sz-track"><div class="sz-bar" style="left:${left}%;width:${w}%;background:${c}"></div></div><span class="sz-v ${cls(r.v)}">${pct(r.v,1)}</span></div>`;
    }).join('');
  };
  $('seasToggle').onclick = (e: any) => {
    const btn = e.target.closest('button'); if(!btn) return;
    seasMode = btn.dataset.mode;
    document.querySelectorAll('#seasToggle button').forEach(x=>x.classList.toggle('active', x===btn));
    const [a,b] = visRange(); renderSeasonality(a,b);
  };

  const renderStats = () => {
    if(ws.classList.contains('left-collapsed')) return;
    const [a,b] = visRange();
    $('statsRange').textContent = `${b-a+1} sessions`;
    $('statsRange').title = `Visible range: ${dates[a]} → ${dates[b]}`;

    /* 1 · Return distribution */
    const rets: number[] = []; for(let i=Math.max(1,a);i<=b;i++) rets.push(dayRet[i]*100);
    if(rets.length >= 3){
      const h = histogram(rets, 10, () => 'rgba(23,52,140,.9)', v=>pct(v,2), 'sessions', {v:rets.at(-1)!, label:'Current'});
      $('distChart').innerHTML = h.svg;
      $('distAxis').innerHTML = axisLabels(h.lo, h.hi, v=>pct(v,1), 0, {lo:h.clipLo, hi:h.clipHi});
      $('distStats').innerHTML = row('Mean', pct(avgOf(rets)), cls(avgOf(rets)), 'Average session return in the visible range')
        + row('Median', pct(median(rets)), cls(median(rets)), 'Middle session return; less affected by outliers')
        + row('Positive sessions', (rets.filter(x=>x>0).length/rets.length*100).toFixed(1)+'%', '', 'Share of sessions that closed up')
        + row('Observations', rets.length, '', 'Number of sessions counted');
    } else { $('distChart').innerHTML = ''; $('distAxis').innerHTML = ''; $('distStats').innerHTML = empty('Not enough sessions in range') }

    /* 2 · Seasonality */
    renderSeasonality(a,b);

    /* 3 · Drawdown (from running peak, measured inside the visible window) */
    const dd: number[] = []; let peak = -Infinity;
    for(let i=a;i<=b;i++){ peak = Math.max(peak, closes[i]); dd.push((closes[i]/peak-1)*100) }
    const ddMin = Math.min(...dd, -.01);
    lineChart($('ddChart'), { series:[{vals:dd,color:'#f23645'}], idx:dd.map((_,k)=>a+k), lo:ddMin, hi:0, ticks:[0, ddMin/2, ddMin], zero:0,
      area:areaPath(dd, ddMin, 0, 'rgba(242,54,69,.14)'), fmtY:(v: number)=>v===0?'0%':v.toFixed(1)+'%', tipFn:(k: number)=>`${pct(dd[k])} from peak` });
    $('ddStats').innerHTML = row('Current drawdown', pct(dd.at(-1)!), cls(dd.at(-1)!), 'Latest close vs the running peak')
      + row('Maximum drawdown', pct(Math.min(...dd)), 'down', 'Deepest peak-to-trough fall in the visible range') + row('Period', 'Visible range', '', 'Drawdown is measured inside the visible window');

    /* 4 · Realized volatility */
    const vv: number[] = [], vi: number[] = []; for(let i=a;i<=b;i++) if(Number.isFinite(vol20[i])){ vv.push(vol20[i]); vi.push(i) }
    if(vv.length >= 3){
      const lo = Math.min(...vv), hi = Math.max(...vv), dp = hi-lo>5 ? 0 : 1;
      lineChart($('volChart'), { series:[{vals:vv,color:'#0070f3'}], idx:vi, lo, hi, ticks:[hi,(hi+lo)/2,lo], fmtY:(v: number)=>v.toFixed(dp)+'%', tipFn:(k: number)=>`${vv[k].toFixed(1)}% annualized` });
      $('volStats').innerHTML = row('Current', vv.at(-1)!.toFixed(1)+'%', '', 'Latest 20-session annualized volatility') + row('Median', median(vv).toFixed(1)+'%', '', 'Middle volatility reading in the visible range')
        + row('Range', `${lo.toFixed(1)}%–${hi.toFixed(1)}%`, '', 'Lowest to highest reading in the visible range');
    } else { $('volChart').innerHTML = ''; $('volStats').innerHTML = empty('Not enough sessions in range') }

    /* 5 · Relative performance vs IHSG (both rebased to the first visible session) */
    const m0 = closes[a], i0 = ihsgSeries[a].value, mp: number[] = [], ip: number[] = [];
    for(let i=a;i<=b;i++){ mp.push((closes[i]/m0-1)*100); ip.push((ihsgSeries[i].value/i0-1)*100) }
    const rlo = Math.min(...mp,...ip), rhi = Math.max(...mp,...ip);
    const zpos = (0-rlo)/((rhi-rlo)||1), rdp = rhi-rlo>5 ? 0 : 1;
    const rticks = (zpos>.18 && zpos<.82) ? [rhi,0,rlo] : [rhi,(rhi+rlo)/2,rlo];
    lineChart($('relChart'), { series:[{vals:ip,color:'#a1a1a1',dash:'4 3'},{vals:mp,color:'#0070f3'}], idx:mp.map((_,k)=>a+k), lo:rlo, hi:rhi, ticks:rticks, zero:0,
      fmtY:(v: number)=>Number(v.toFixed(rdp))===0 ? '0%' : (v>0?'+':'')+v.toFixed(rdp)+'%', tipFn:(k: number)=>`${SYMBOL} ${pct(mp[k],1)} · IHSG ${pct(ip[k],1)} · Δ ${(mp[k]-ip[k]).toFixed(1)} pp` });
    const diff = mp.at(-1)!-ip.at(-1)!;
    $('relStats').innerHTML = `<div class="st-legend"><span><i style="border-color:#0070f3"></i>${SYMBOL}</span><span><i style="border-color:#a1a1a1;border-top-style:dashed"></i>IHSG</span></div>`
      + row(SYMBOL, pct(mp.at(-1)!,1), cls(mp.at(-1)!), `${SYMBOL} return since the first visible session`) + row('IHSG', pct(ip.at(-1)!,1), cls(ip.at(-1)!), 'IHSG return since the first visible session')
      + row('Difference', `${diff>=0?'+':''}${diff.toFixed(1)} pp`, cls(diff), `${SYMBOL} minus IHSG, in percentage points`);

    /* 6 · Volume distribution */
    const vr: number[] = []; for(let i=a;i<=b;i++) if(Number.isFinite(volRatio[i])) vr.push(volRatio[i]);
    if(vr.length >= 3){
      const h = histogram(vr, 10, () => 'rgba(0,112,243,.72)', v=>v.toFixed(2)+'×', 'sessions', {v:vr.at(-1)!, label:'Current'}), cur = vr.at(-1)!;
      $('vdChart').innerHTML = h.svg;
      $('vdAxis').innerHTML = axisLabels(h.lo, h.hi, v=>v.toFixed(1)+'×', 1, {lo:h.clipLo, hi:h.clipHi});
      $('vdStats').innerHTML = row('Current', cur.toFixed(2)+'×', '', 'Latest volume ÷ its 20-day average') + row('Median', median(vr).toFixed(2)+'×', '', 'Middle volume ratio in the visible range')
        + row('Percentile', Math.round(vr.filter(x=>x<=cur).length/vr.length*100), '', 'Share of sessions with a volume ratio at or below the current one') + row('Observations', vr.length, '', 'Number of sessions counted');
    } else { $('vdChart').innerHTML = ''; $('vdAxis').innerHTML = ''; $('vdStats').innerHTML = empty('Not enough sessions in range') }
  };
  let statsRaf = 0;
  const scheduleStats = ctx.scheduleStats = () => { cancelAnimationFrame(statsRaf); statsRaf = requestAnimationFrame(renderStats) };
  chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleStats);
  setLeftCollapsed(store.get('ml.stats.collapsed') === '1');
  scheduleStats();
}
