/* INDICATORS — picker UI (reference lines 2047-2125). */
import type { Ctx } from './context';
import { $ } from './context';
import { FLOW_REG } from './flowIndicators';

export function initPicker(ctx: Ctx) {
  const { IND_REG, Ind, volCtl } = ctx;
  /* groups come from the registry categories (01_INDICATORS column B); Flow is our own group */
  const GROUP_COLORS = ['#0070f3', '#7928ca', '#f5a623', '#089981', '#d6409f', '#12a594'];
  const INDICATORS: [string, string, string[], string][] = [];
  IND_REG.forEach((r: any) => {
    let g = INDICATORS.find(x => x[3] === r.cat);
    if(!g) { g = [r.cat.replace(/([a-z])([A-Z])/g, '$1 & $2'), GROUP_COLORS[INDICATORS.length % GROUP_COLORS.length], [], r.cat]; INDICATORS.push(g) }
    g[2].push(r.name);
  });
  (INDICATORS.find(g => g[3] === 'Volume') || [, , []] as any)[2].unshift('Volume');         // the base volume histogram (restore after removing it)
  INDICATORS.push(['Flow', '#12a594', ['Net Buy Flow', 'Net Buy Flow (Line)'], 'Flow']);
  const SEARCH: Record<string, string> = Object.fromEntries(IND_REG.map((r: any) => [r.name, `${r.name} ${r.short} ${r.key}`.toLowerCase()]));
  /* EXEC-TERMINAL-FLOW-IND (user 2026-10-30: the Flow group in subgroups per family, "3. OK"), live: one subgroup per family
     of flowRegistry.json, in its order; the fixture keeps the reference's list (1:1 check) */
  if(ctx.M.mode === 'live') FLOW_REG.families.forEach(f => {
    const items = FLOW_REG.indicators.filter(r => r.family === f);
    if(!items.length) return;
    INDICATORS.push([`Flow · ${f}`, '#12a594', items.map(r => r.name), 'Flow']);
    items.forEach(r => { SEARCH[r.name] = `${r.name} ${r.id} ${f} flow`.toLowerCase() });
  });
  Ind.tips.Volume = 'Batang volume transaksi harian di bagian bawah chart harga.';
  const isActive = (x: string) => x === 'Volume' && !volCtl.removed;      // volume histogram is drawn unless removed with the X
  const btn = $('indBtn'), pop = $('indPop'), list = $('indList'), q = $('indSearch');
  const tip = document.createElement('div'); tip.className = 'ind-tip'; tip.hidden = true; document.body.appendChild(tip);
  const showInfo = (el: HTMLElement) => {
    const name = el.dataset.name as string, t = Ind.tips[name] || '';
    tip.innerHTML = `<b>${name}</b>${t.replace(/[&<>]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;' } as Record<string, string>)[c])}`;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), pr = pop.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let l = pr.right + 8; if(l + w > innerWidth - 8) l = Math.max(8, pr.left - w - 8);
    tip.style.left = l + 'px'; tip.style.top = Math.max(8, Math.min(innerHeight - h - 8, r.top - 8)) + 'px';
  };
  const hideInfo = () => { tip.hidden = true };
  list.addEventListener('pointerover', (e: any) => { const el = e.target.closest('.ind-info'); el ? showInfo(el) : hideInfo() });
  const pick = (e: any) => {
    const it = e.target.closest('.ind-item'); if(!it || e.target.closest('.ind-info')) return;
    if(it.classList.contains('restore')) volCtl.setRemoved(false);
    else if(Ind.byName[it.dataset.ind]){ Ind.add(Ind.byName[it.dataset.ind]); render() }
  };
  list.addEventListener('click', pick);
  list.addEventListener('keydown', (e: any) => { if((e.key==='Enter' || e.key===' ') && e.target.closest('.ind-item')){ e.preventDefault(); pick(e) } });
  volCtl.onChange = () => { if(!pop.hidden) render() };
  Ind.onChange = () => { if(!pop.hidden) render() };
  list.addEventListener('pointerleave', hideInfo); list.addEventListener('scroll', hideInfo, {passive:true});
  list.addEventListener('focusin', (e: any) => { const el = e.target.closest('.ind-info'); if(el) showInfo(el) });
  list.addEventListener('focusout', hideInfo);
  const render = () => {
    const t = q.value.trim().toLowerCase();
    list.innerHTML = INDICATORS.map(([g, color, items]) => {
      const hit = items.filter(x => !t || (SEARCH[x] || x.toLowerCase()).includes(t) || g.toLowerCase().includes(t));
      return hit.length ? `<div class="ind-group" style="--gc:${color}">${g}</div>` + hit.map(x => {
        const def = Ind.byName[x], n = def ? Ind.countOf(def) : 0;
        const tag = x === 'Volume' ? (isActive(x) ? '<span class="ind-added">On chart</span>' : '')
                  : def ? (n ? `<span class="ind-added">${n} on chart</span>` : '')
                  : '<span class="ind-soon">Soon</span>';
        const cls = x === 'Volume' ? (volCtl.removed ? ' restore' : '') : def ? ' act' : '';
        return `<div class="ind-item${cls}" data-ind="${x}" role="button" tabindex="0"><span>${x}</span><span class="ind-right">${tag}<span class="ind-info" tabindex="0" role="img" aria-label="About ${x}" data-name="${x}">!</span></span></div>`;
      }).join('') : '';
    }).join('') || '<div class="ind-empty">No indicators match</div>';
  };
  const place = () => { const r = btn.getBoundingClientRect(); pop.style.top = (r.bottom + 6) + 'px'; pop.style.left = Math.max(8, Math.min(r.left, innerWidth - 348)) + 'px' };
  const open = (o: boolean) => {
    pop.hidden = !o; btn.setAttribute('aria-expanded', String(o)); if(!o) hideInfo();
    if(o){ place(); q.value = ''; render(); q.focus() }
  };
  btn.addEventListener('click', (e: Event) => { e.stopPropagation(); open(pop.hidden) });
  $('indClose').addEventListener('click', () => open(false));
  q.addEventListener('input', render);
  document.addEventListener('pointerdown', e => { if(!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) open(false) });
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && !pop.hidden){ open(false); btn.focus() } });
  addEventListener('resize', () => { if(!pop.hidden) place() });
}
