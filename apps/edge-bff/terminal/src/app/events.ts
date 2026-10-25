/* EVENTS — corporate actions drawn on the price chart, chosen per type (reference lines 2470-2582).
     { id, type, date:'YYYY-MM-DD', title, rows:[[label, value], ...] }
   type ∈ stocksplit | reversesplit | rightissue | bonus | dividend | rups | tenderoffer | warrant
   Fixture: the reference's mock list. Live: idx_event_annotation's corporate actions (data/live.ts). */
import type { Ctx } from './context';
import { $, store } from './context';
import type { MarketEvent } from '../data/types';

export const EVENT_TYPES = [
  { id:'dividend',     label:'Dividend',      letter:'D',  color:'#089981' },
  { id:'stocksplit',   label:'Stock split',   letter:'S',  color:'#171717' },
  { id:'reversesplit', label:'Reverse split', letter:'RS', color:'#737373' },
  { id:'rightissue',   label:'Rights issue',  letter:'RI', color:'#e08a00' },
  { id:'bonus',        label:'Bonus shares',  letter:'B',  color:'#8b5cf6' },
  { id:'rups',         label:'RUPS',          letter:'R',  color:'#b45309' },
  { id:'tenderoffer',  label:'Tender offer',  letter:'T',  color:'#db2777' },
  { id:'warrant',      label:'Warrant',       letter:'W',  color:'#0891b2' }
];

export function initEvents(ctx: Ctx) {
  const { chart } = ctx;
  const TYPES = EVENT_TYPES;
  const T = Object.fromEntries(TYPES.map(t => [t.id, t]));
  const KEY = 'ml.events.v1';
  const pref: { on: boolean; types: Record<string, boolean> } = { on:true, types:Object.fromEntries(TYPES.map(t => [t.id, true])) };
  try{ const v = JSON.parse(store.get(KEY) || 'null'); if(v){ pref.on = v.on !== false; TYPES.forEach(t => { if(v.types && v.types[t.id] === false) pref.types[t.id] = false }) } }catch(e){}
  const save = () => store.set(KEY, JSON.stringify(pref));

  let EVENTS: MarketEvent[] = [];
  const loadEvents = () => ctx.M.loadEvents();       // backend hook
  const setEvents = (list: MarketEvent[]) => { EVENTS = list; renderList(); schedule() };

  /* ---- popover ---- */
  const btn = $('evBtn'), pop = $('evPop'), master = $('evMaster'), list = $('evList');
  const CHECK = '<svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.2l2.4 2.4 4.6-5"/></svg>';
  function renderList() {
    const cnt = (id: string) => EVENTS.filter(e => e.type === id).length;
    list.innerHTML = TYPES.map(t => `<button type="button" class="ev-row" data-id="${t.id}" aria-pressed="${pref.types[t.id]}">
        <span class="ev-chip" style="background:${t.color}">${t.letter}</span><span class="ev-name">${t.label}</span><span class="ev-cnt">${cnt(t.id)}</span><span class="ev-chk">${CHECK}</span></button>`).join('');
    const shown = TYPES.filter(t => pref.types[t.id]).length;
    $('evSummary').textContent = pref.on ? `${shown} of ${TYPES.length} types shown` : 'Events hidden';
    master.checked = pref.on; btn.setAttribute('aria-pressed', String(pref.on && shown > 0));
    list.style.opacity = pref.on ? '' : '.5';
  }
  const commit = () => { save(); renderList(); schedule() };
  list.addEventListener('click', (e: any) => { const b = e.target.closest('.ev-row'); if(!b) return; pref.types[b.dataset.id] = !pref.types[b.dataset.id]; if(!pref.on && pref.types[b.dataset.id]) pref.on = true; commit() });
  master.addEventListener('change', () => { pref.on = master.checked; commit() });
  $('evAll').addEventListener('click', () => { TYPES.forEach(t => pref.types[t.id] = true); pref.on = true; commit() });
  $('evNone').addEventListener('click', () => { TYPES.forEach(t => pref.types[t.id] = false); commit() });
  const place = () => { const r = btn.getBoundingClientRect(); pop.style.top = (r.bottom + 6) + 'px'; pop.style.left = Math.max(8, Math.min(r.left, innerWidth - 328)) + 'px' };
  const openPop = (on: boolean) => { pop.hidden = !on; btn.setAttribute('aria-expanded', String(on)); if(on) place() };
  btn.addEventListener('click', (e: Event) => { e.stopPropagation(); openPop(pop.hidden) });
  document.addEventListener('mousedown', e => { if(!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) openPop(false) });
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && !pop.hidden){ openPop(false); btn.focus() } });
  addEventListener('resize', () => { if(!pop.hidden) place() });

  /* ---- markers on the chart ---- */
  const wrapEl = $('chart').parentElement;
  const layer = document.createElement('div'); layer.className = 'ev-layer'; wrapEl.appendChild(layer);
  const tip = $('evTip');
  const esc = (t: unknown) => String(t).replace(/[&<>]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;' } as Record<string, string>)[c]);
  function showTip(el: HTMLElement, group: MarketEvent[]) {
    tip.innerHTML = `<div class="d">${group[0].date}${group.length > 1 ? ` · ${group.length} events` : ''}</div>` + group.map(e => `<div class="it"><div class="t"><span class="ev-chip" style="background:${T[e.type].color}">${T[e.type].letter}</span>${esc(e.title)}</div><dl>${e.rows.map(r => `<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')}</dl></div>`).join('');
    tip.hidden = false;
    const r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px';
    tip.style.top = Math.max(8, r.top - h - 10) + 'px';
  }
  let sig = '';
  function layout() {
    raf = 0;
    const ts = chart.timeScale(), pane = chart.panes()[0];
    const left = chart.priceScale('left').width(), H = pane ? pane.getHeight() : 0, W = ts.width();
    const rng = ts.getVisibleLogicalRange();
    sig = [left, H, W, $('chart').clientHeight, rng && rng.from.toFixed(2), rng && rng.to.toFixed(2), pref.on, TYPES.map(t => +pref.types[t.id]).join(''), EVENTS.length].join('|');
    layer.replaceChildren(); tip.hidden = true;
    if(!pref.on || !H) return;
    const pts = EVENTS.filter(e => pref.types[e.type]).map(e => ({ e, x:ts.timeToCoordinate((e.at || e.date) as any) })).filter(p => p.x != null && p.x >= 0 && p.x <= W).sort((a, b) => (a.x as number) - (b.x as number));
    const groups: { x: number; items: MarketEvent[] }[] = [];
    pts.forEach(p => { const g = groups[groups.length - 1]; if(g && (p.x as number) - g.x < 22) g.items.push(p.e); else groups.push({ x:p.x as number, items:[p.e] }) });
    const y = $('chart').clientHeight - Math.round(ts.height() / 2);       // centre of the time-axis strip, below every pane and the volume bars
    groups.forEach(g => {
      const one = g.items.length === 1, t = T[g.items[0].type], x = left + g.x;
      const el = document.createElement('div'); el.className = 'ev-mk'; el.style.left = x + 'px'; el.style.top = y + 'px';
      el.style.background = one ? t.color : '#171717'; el.textContent = one ? t.letter : String(g.items.length);
      el.setAttribute('aria-label', g.items.map(i => i.title).join(', '));
      let ln: HTMLElement | null = null;
      el.addEventListener('mouseenter', () => { showTip(el, g.items); ln = document.createElement('div'); ln.className = 'ev-line'; ln.style.left = x + 'px'; ln.style.top = '0'; ln.style.height = (y - 12) + 'px'; layer.appendChild(ln) });
      el.addEventListener('mouseleave', () => { tip.hidden = true; if(ln) ln.remove() });
      layer.appendChild(el);
    });
  }
  let raf = 0;
  function schedule() { if(!raf) raf = requestAnimationFrame(layout) }
  chart.timeScale().subscribeVisibleLogicalRangeChange(schedule);
  chart.timeScale().subscribeSizeChange(schedule);
  addEventListener('resize', schedule);
  setInterval(() => {                                   // axis width / pane height change without any chart event (indicator panes, panel collapse)
    const ts = chart.timeScale(), pane = chart.panes()[0], r = ts.getVisibleLogicalRange();
    const now = [chart.priceScale('left').width(), pane ? pane.getHeight() : 0, ts.width(), $('chart').clientHeight, r && r.from.toFixed(2), r && r.to.toFixed(2), pref.on, TYPES.map(t => +pref.types[t.id]).join(''), EVENTS.length].join('|');
    if(now !== sig) schedule();
  }, 300);
  (window as any).marketLabEvents = { types:TYPES.map(t => t.id), set:setEvents, get:() => EVENTS.slice(), preference:() => JSON.parse(JSON.stringify(pref)) };
  renderList();
  loadEvents().then(setEvents).catch(() => setEvents([]));
}
