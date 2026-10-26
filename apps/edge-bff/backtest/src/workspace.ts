/* ENTRY WORKSPACE (backtest.html section 1A): catalog + search | all conditions | detail & inputs. Entry and exit use
   the same catalog; the parameter forms are generated from the registry (integer/number → bounded number, enum →
   select, boolean → switch, fixed → read-only). "True on" and the signal counts are the API's series on the shown
   ticker. */
import type { Card } from './api/types.ts';
import type { RegCard } from './core/catalog.ts';
import { DATA } from './env.ts';
import { $, COLORS, esc, ico, nf, OPS, toast } from './format.ts';
import { CAT_LABEL, CATALOG, catOf, condReady, evalCond, EV_LABEL, EXTRA_GROUPS, mkReg, opLabel, OUT_LABEL, priceLbl, REG, REG_BY, regDefaults, regReady, sideLbl, ZONE_LABEL, type RegParam, type RegRow } from './reg.ts';
import { mkCond, S } from './state.ts';
import { exitSeries, getLastSig, inRange, refreshSignals } from './signals.ts';
import { condCard, markStale, renderBuilder } from './builder.ts';

const WS: { q: string; cat: string; sel: { kind: string; id: string } | null; side: 'entry' | 'exit'; draft?: RegCard | null } = {q:'', cat:'All', sel:null, side:'entry'};
const WL = () => WS.side==='exit' ? S.exitConds : S.conds;
const setWL = (a: Card[]) => { if(WS.side==='exit') S.exitConds = a; else S.conds = a };
interface WsItem { kind: string; id: string; cat: string; name: string; key: string; desc: string; r?: RegRow }
const wsAll = (): WsItem[] => [...REG.map(r => ({kind:'reg', id:r.id, cat:CAT_LABEL[r.cat]||r.cat, name:r.name, key:r.key, desc:r.short, r})),
  ...EXTRA_GROUPS.flatMap(([g, keys]) => keys.map(k => ({kind:'legacy', id:k as string, cat:g, name:CATALOG[k].label, key:k as string, desc:CATALOG[k].desc})))];
const wsMatch = (it: WsItem, q: string) => { if(!q) return {ok:true, hits:[] as string[]}; const t = q.toLowerCase(), hay = [it.name, it.key, it.cat, it.desc, it.r?.detail].join(' ').toLowerCase();
  const hits = it.r ? it.r.p.filter(x => [x.l, x.k, x.m].join(' ').toLowerCase().includes(t)).map(x => x.l) : (CATALOG[it.id]?.params||[]).filter(([k,l]) => (k+' '+l).toLowerCase().includes(t)).map(([,l]) => l);
  return {ok: hay.includes(t) || hits.length>0, hits} };
export const openWS = (sel: { kind: string; id: string } | null, side?: 'entry' | 'exit') => { if(side && side!==WS.side){ WS.side = side; WS.sel = null } if(sel) WS.sel = sel; else if(!WS.sel && WL()[0]) WS.sel = {kind:'cond', id:WL()[0].id}; $('ews').hidden = false; document.body.classList.add('wsopen'); renderWS(); setTimeout(() => $('wsQ')?.focus(), 30) };
const closeWS = () => { $('ews').hidden = true; document.body.classList.remove('wsopen') };
const afterCondChange = (full=true) => { markStale(); refreshSignals(); renderBuilder(); if(full) renderWS(); else renderWSMid() };
const condStats = (c: Card) => { if(!condReady(c)) return {txt:'Not calculated', cls:'warn'}; if(!c.on) return {txt:'Off', cls:'neu'};
  const D = DATA[S.sigTicker] ? DATA[S.sigTicker].dates : [], s = evalCond(S.sigTicker, c); let n = 0, span = 0; for(let i=1;i<D.length;i++) if(inRange(D, i)){ span++; if(s[i]) n++ } return {txt:`${nf(n/span*100,1)}% of days`, cls:'pos', n} };
export const renderWS = () => { renderWSHead(); renderWSCat(); renderWSMid(); renderWSDet() };
const renderWSHead = () => {
  const L = WL(), act = L.filter(c=>c.on&&condReady(c)).length, nc = L.filter(c=>!condReady(c)).length;
  $('wsTabs').innerHTML = [['entry','Entry',S.conds.length],['exit','Exit',S.exitConds.length]].map(([k,l,n])=>`<button class="${WS.side===k?'on':''}" data-wside="${k}">${l}<span>${n}</span></button>`).join('');
  $('wsTabs').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-wside]') as HTMLElement; if(b && b.dataset.wside!==WS.side){ WS.side = b.dataset.wside as 'entry' | 'exit'; WS.sel = WL()[0] ? {kind:'cond', id:WL()[0].id} : null; renderWS() } };
  let sig = 0;
  if(WS.side==='entry'){ const lastSig = getLastSig(); if(lastSig) for(let i=1;i<lastSig.dates.length;i++) if(inRange(lastSig.dates, i) && lastSig.entry[i] && !lastSig.entry[i-1]) sig++;
    $('wsRule').innerHTML = `<span>Enter when</span><select class="sel" data-wk="logic"><option value="all" ${S.logic==='all'?'selected':''}>ALL</option><option value="any" ${S.logic==='any'?'selected':''}>ANY</option><option value="n" ${S.logic==='n'?'selected':''}>AT LEAST</option></select>${S.logic==='n'?`<input class="inp" type="number" min="1" data-wk="atLeast" value="${S.atLeast}">`:''}<span>conditions are met within</span><input class="inp" type="number" min="1" max="20" data-wk="window" value="${S.window}"><span>bars</span>` }
  else { const D = DATA[S.sigTicker] ? DATA[S.sigTicker].dates : [], x = exitSeries(S.sigTicker); for(let i=1;i<D.length;i++) if(inRange(D, i) && x[i] && !x[i-1]) sig++;
    $('wsRule').innerHTML = `<span>Exit when</span><select class="sel" data-wk="exitLogic"><option value="any" ${S.exitLogic==='any'?'selected':''}>ANY</option><option value="all" ${S.exitLogic==='all'?'selected':''}>ALL</option></select><span title="Checked at the close, sold at the next open">of these is true</span>` }
  $('wsStats').innerHTML = `<div class="lr-s"><span>Conditions</span><b>${L.length}</b></div><div class="lr-s"><span>Counted on Run</span><b>${act}</b></div><div class="lr-s"><span>Not calculated</span><b class="${nc?'amber':''}">${nc}</b></div><div class="lr-s"><span>${WS.side==='entry'?'Entry':'Exit'} signals · ${esc(S.sigTicker)}</span><b>${sig}</b></div>`;
  $('wsRule').querySelectorAll('[data-wk]').forEach((el: HTMLInputElement) => el.onchange = () => { (S as any)[el.dataset.wk] = el.tagName==='SELECT' ? el.value : +el.value; afterCondChange() });
};
const renderWSCat = () => {
  const items = wsAll(), cats = ['All', ...new Set(items.map(i=>i.cat))];
  $('wsCats').innerHTML = cats.map(c => { const n = items.filter(i => (c==='All'||i.cat===c) && wsMatch(i,WS.q).ok).length; return `<button class="${WS.cat===c?'on':''}" data-wc="${esc(c)}">${esc(c)}<span>${n}</span></button>` }).join('');
  const shown = items.filter(i => (WS.cat==='All'||i.cat===WS.cat)).map(i => ({i, m:wsMatch(i,WS.q)})).filter(x => x.m.ok);
  const used = new Set(WL().map(c => c.type==='reg' ? c.ind : c.type));
  const groups = [...new Set(shown.map(x=>x.i.cat))];
  $('wsList').innerHTML = shown.length ? groups.map(g => `<div class="wl-g">${esc(g)}<span>${shown.filter(x=>x.i.cat===g).length}</span></div>` + shown.filter(x=>x.i.cat===g).map(({i,m}) => {
      const sel = WS.sel && WS.sel.kind!=='cond' && WS.sel.id===i.id, ready = i.kind==='legacy' ? condReady({type:i.id} as Card) : regReady(i.id);
      return `<div class="wl-i ${sel?'on':''}" data-wi="${i.kind}:${i.id}" role="button" tabindex="0"><div class="wl-t"><b>${esc(i.name)}</b>${used.has(i.id)?'<span class="pill neu">In use</span>':''}${ready?'':'<span class="pill warn">Not calculated</span>'}</div><div class="wl-d">${esc(i.desc||'')}</div>${m.hits.length?`<div class="wl-h">Input match: ${m.hits.map(h=>`<b>${esc(h)}</b>`).join(', ')}</div>`:''}<button class="wl-add" data-wadd="${i.kind}:${i.id}" title="Add as a condition">${ico('<path d="M12 5v14M5 12h14"/>')}Add</button></div>` }).join('')).join('')
    : `<div class="empty">No indicator or input matches “${esc(WS.q)}”.</div>`;
  $('wsCats').onclick = (e: MouseEvent) => { const b = (e.target as HTMLElement).closest('[data-wc]') as HTMLElement; if(b){ WS.cat = b.dataset.wc; renderWSCat() } };
  $('wsList').querySelectorAll('[data-wi]').forEach((el: HTMLElement) => { const go = () => { const [k,id] = el.dataset.wi.split(':'); WS.sel = {kind:k, id}; renderWSCat(); renderWSDet() }; el.onclick = e => { if(!(e.target as HTMLElement).closest('[data-wadd]')) go() }; el.onkeydown = e => { if(e.key==='Enter') go() } });
  $('wsList').querySelectorAll('[data-wadd]').forEach((b: HTMLElement) => b.onclick = () => { const [k, id] = b.dataset.wadd.split(':'); wsAdd(k, id) });
};
const wsAdd = (kind: string, id: string) => { const c = kind==='reg' ? mkReg(id) : mkCond(id); WL().push(c); WS.sel = {kind:'cond', id:c.id}; afterCondChange(); toast(`${kind==='reg'?REG_BY[id].name:CATALOG[id].label} added`) };
export const renderWSMid = () => {
  $('wsCount').textContent = `${WS.side==='entry'?'Entry':'Exit'} · ${WL().length} condition${WL().length===1?'':'s'}`;
  $('wsTable').innerHTML = WL().length ? `<table class="wst"><thead><tr><th></th><th>Indicator</th><th>Rule</th><th>Inputs</th><th>True on</th><th>On</th><th></th></tr></thead><tbody>${WL().map((c,i) => { const C = catOf(c), st = condStats(c), r = c.type==='reg' ? REG_BY[c.ind] : null, lc = c as any;
      const rule = r ? `${esc(sideLbl(r,lc.lhs))} <b>${OPS[lc.op]}</b> ${esc(sideLbl(r,lc.rhs))}` : esc(C.noVal ? opLabel(c,lc.op) : `${OPS[lc.op]||lc.op} ${lc.val}${C.unit?' '+C.unit:''}`);
      const inputs = r ? r.p.filter(x=>x.t!=='fixed').map(x=>`${esc(x.l)} ${esc(String(lc.p[x.k]))}`).join(' · ') : C.params.map(([k,l])=>`${esc(l)} ${esc(String(lc[k]))}`).join(' · ');
      const sel = WS.sel && WS.sel.kind==='cond' && WS.sel.id===c.id;
      return `<tr class="${sel?'on':''} ${c.on?'':'off'}" data-wsel="${c.id}"><td><i class="sq" style="background:${COLORS[i%COLORS.length]}"></i></td><td><b>${esc(C.label)}</b><small>${esc(r?(CAT_LABEL[r.cat]||r.cat):(C.group==='flow'?'Flow':C.group==='price'?'Price action':'Technical'))}</small></td><td>${rule}</td><td class="mut">${inputs||'—'}</td><td><span class="pill ${st.cls}">${st.txt}</span></td><td><label class="sw"><input type="checkbox" data-won="${c.id}" ${c.on?'checked':''}><span></span></label></td><td class="act"><button class="x" data-wdup="${c.id}" title="Duplicate">${ico('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>')}</button><button class="x" data-wdel="${c.id}" title="Remove">${ico('<path d="M6 6l12 12M18 6 6 18"/>')}</button></td></tr>` }).join('')}</tbody></table>`
    : `<div class="empty">No conditions yet. Pick an indicator on the left and press <b>Add</b>.</div>`;
  const T = $('wsTable');
  T.querySelectorAll('[data-wsel]').forEach((tr: HTMLElement) => tr.onclick = e => { if((e.target as HTMLElement).closest('button,label,input')) return; WS.sel = {kind:'cond', id:tr.dataset.wsel}; renderWSMid(); renderWSDet() });
  T.querySelectorAll('[data-won]').forEach((x: HTMLInputElement) => x.onchange = () => { WL().find(c=>c.id===x.dataset.won).on = x.checked; afterCondChange() });
  T.querySelectorAll('[data-wdel]').forEach((x: HTMLElement) => x.onclick = () => { setWL(WL().filter(c=>c.id!==x.dataset.wdel)); if(WS.sel?.id===x.dataset.wdel) WS.sel = null; afterCondChange() });
  T.querySelectorAll('[data-wdup]').forEach((x: HTMLElement) => x.onclick = () => { const c = WL().find(c=>c.id===x.dataset.wdup), d = JSON.parse(JSON.stringify(c)); d.id = Math.random().toString(36).slice(2,8); WL().splice(WL().indexOf(c)+1, 0, d); WS.sel = {kind:'cond', id:d.id}; afterCondChange() });
  renderWSHead();
};
/* one form, generated from 02_PARAMETERS: integer/number → bounded number, enum → select, boolean → switch, fixed → read-only */
const paramField = (x: RegParam, v: unknown, attr: string) => { const ev = EV_LABEL[x.ev], badge = ev ? `<span class="pill ${ev[1]}" title="${esc(x.ev)}">${ev[0]}</span>` : '';
  const help = `<small>${[x.m, x.min!=null&&x.max!=null?`range ${x.min}–${x.max}`:x.min!=null?`min ${x.min}`:x.max!=null?`max ${x.max}`:'', x.note].filter(Boolean).map(esc).join(' · ')}</small>`;
  const ctl = x.t==='fixed' ? `<input class="inp" disabled value="${esc(String(x.d??'fixed'))}">`
    : x.t==='enum' ? `<select class="sel" ${attr}>${(x.opt||[]).map(o=>`<option ${String(o)===String(v)?'selected':''}>${esc(o)}</option>`).join('')}</select>`
    : x.t==='boolean' ? `<label class="sw"><input type="checkbox" ${attr} ${v?'checked':''}><span></span></label>`
    : `<input class="inp" type="number" ${attr} value="${esc(String(v??''))}" ${x.min!=null?`min="${x.min}"`:''} ${x.max!=null?`max="${x.max}"`:''} step="${x.step ?? (x.t==='integer'?1:'any')}">`;
  return `<div class="pf"><div class="pf-l"><b>${esc(x.l)}</b><code>${esc(x.k)}</code>${badge}</div>${ctl}${help}</div>` };
const sideCtl = (r: RegRow, s: any, which: string, id: string) => { const opts = [...(r.zone!=='panel'?[['price',priceLbl(r)]]:[]), ...r.out.map(o=>['out:'+o, OUT_LABEL(o)]), ...(which==='rhs'?[['val','A value']]:[])];
  const cur = s.t==='out' ? 'out:'+s.o : s.t;
  return `<select class="sel" data-wside="${which}" data-cid="${id}">${opts.map(([v,l])=>`<option value="${v}" ${v===cur?'selected':''}>${esc(l)}</option>`).join('')}</select>` };
const renderWSDet = () => {
  const el = $('wsDet'), sel = WS.sel;
  if(!sel){ el.innerHTML = `<div class="empty">Select an indicator or a condition to see its definition and inputs.</div>`; return }
  const c = sel.kind==='cond' ? WL().find(x=>x.id===sel.id) : null;
  if(sel.kind==='cond' && !c){ WS.sel = null; return renderWSDet() }
  if(c && c.type!=='reg'){ const i = WL().indexOf(c), C = CATALOG[c.type], lc = c as any;
    el.innerHTML = `<div class="wd-h"><span class="pill neu">${C.group==='flow'?'Flow':C.group==='price'?'Price action':'Technical'}</span><h3>${esc(C.label)}</h3><p>${esc(C.desc)}</p></div><div class="wd-sec">Inputs & condition</div>${condCard(c,i)}`;
    el.querySelectorAll('[data-c]').forEach((x: HTMLInputElement) => x.onchange = () => { const p = x.dataset.p; lc[p] = p==='on' ? x.checked : (p==='op'||p==='broker') ? x.value : +x.value; afterCondChange() });
    el.querySelectorAll('[data-del]').forEach((x: HTMLElement) => x.onclick = () => { setWL(WL().filter(k=>k!==c)); WS.sel = null; afterCondChange() });
    return }
  if(sel.kind==='legacy'){ const C = CATALOG[sel.id];
    el.innerHTML = `<div class="wd-h"><span class="pill neu">${C.group==='flow'?'Flow':'Price action'}</span><h3>${esc(C.label)}</h3><p>${esc(C.desc)}</p></div><div class="wd-sec">Inputs</div><div class="pfs">${C.params.map(([k,l,d])=>`<div class="pf"><div class="pf-l"><b>${esc(l)}</b><code>${esc(k)}</code></div><input class="inp" disabled value="${esc(String(d))}"></div>`).join('')||'<div class="mut">No inputs</div>'}</div><button class="btn dark wd-add" data-wadd="legacy:${sel.id}">${ico('<path d="M12 5v14M5 12h14"/>')}Add to ${WS.side} conditions</button>`;
    (el.querySelector('[data-wadd]') as HTMLElement).onclick = () => wsAdd('legacy', sel.id); return }
  const rc = c as RegCard, r = REG_BY[rc ? rc.ind : sel.id], vals = rc ? rc.p : regDefaults(r), ready = regReady(r.id), draft = rc || mkReg(r.id);
  el.innerHTML = `<div class="wd-h"><div class="wd-tags"><span class="pill neu">${esc(CAT_LABEL[r.cat]||r.cat)}</span><span class="pill neu">${ZONE_LABEL[r.zone]||r.zone}</span><span class="pill neu" title="Required data">Data: ${esc(r.data)}</span>${ready?'':'<span class="pill warn">Not calculated in this mock-up</span>'}</div><h3>${esc(r.name)} <code>${esc(r.id)} · ${esc(r.key)}</code></h3><p>${esc(r.short)}</p><details><summary>Detailed definition</summary><p>${esc(r.detail)}</p><p class="mut">Display: ${esc(r.disp)}</p></details></div>
    <div class="wd-sec">Condition</div>
    <div class="wd-rule">${sideCtl(r,draft.lhs,'lhs',draft.id)}<select class="sel" data-wop>${['gt','lt','ca','cb'].map(o=>`<option value="${o}" ${o===draft.op?'selected':''}>${OPS[o]}</option>`).join('')}</select>${sideCtl(r,draft.rhs,'rhs',draft.id)}${draft.rhs.t==='val'?`<input class="inp" type="number" step="any" data-wval value="${draft.rhs.v}">`:''}</div>
    <div class="wd-sec">Inputs <small>${r.p.length} from the registry</small></div>
    <div class="pfs">${r.p.map(x => paramField(x, vals[x.k], `data-wp="${x.k}"`)).join('')}</div>
    <div class="wd-sec">Outputs</div><div class="wd-outs">${r.out.map(o=>`<span class="pill neu">${esc(OUT_LABEL(o))}</span>`).join('')}</div>
    ${rc ? '' : `<button class="btn dark wd-add" id="wdAdd">${ico('<path d="M12 5v14M5 12h14"/>')}Add to ${WS.side} conditions</button>`}`;
  const tgt: any = rc || draft, apply = () => { if(rc) afterCondChange(); else renderWSDet() };
  el.querySelectorAll('[data-wp]').forEach((x: HTMLInputElement) => x.onchange = () => { const p = r.p.find(q=>q.k===x.dataset.wp); let v: any = x.type==='checkbox' ? x.checked : p.t==='integer' ? Math.round(+x.value) : p.t==='number' ? +x.value : x.value;
    if(typeof v==='number'){ if(p.min!=null) v = Math.max(p.min, v); if(p.max!=null) v = Math.min(p.max, v); x.value = v } tgt.p[p.k] = v; if(!rc) WS.draft = tgt; if(rc) afterCondChange(false) });
  el.querySelectorAll('[data-wside]').forEach((x: HTMLSelectElement) => x.onchange = () => { const v = x.value; tgt[x.dataset.wside] = v==='price' ? {t:'price'} : v==='val' ? {t:'val', v:0} : {t:'out', o:v.slice(4)}; if(!rc) WS.draft = tgt; apply() });
  (el.querySelector('[data-wop]') as HTMLSelectElement).onchange = e => { tgt.op = (e.target as HTMLSelectElement).value; if(!rc) WS.draft = tgt; if(rc) afterCondChange(false) };
  const vi = el.querySelector('[data-wval]') as HTMLInputElement; if(vi) vi.onchange = () => { tgt.rhs.v = +vi.value; if(!rc) WS.draft = tgt; if(rc) afterCondChange(false) };
  const add = $('wdAdd'); if(add) add.onclick = () => { const d = (WS.draft && WS.draft.ind===r.id) ? WS.draft : tgt; WS.draft = null; d.id = Math.random().toString(36).slice(2,8); WL().push(d); WS.sel = {kind:'cond', id:d.id}; afterCondChange(); toast(`${r.name} added`) };
  if(!rc && !(WS.draft && WS.draft.ind===r.id)) WS.draft = draft; else if(!rc) Object.assign(draft, WS.draft);
};
/** the workspace's own listeners (the reference wires them at start) */
export const bindWS = () => {
  $('wsQ').oninput = (e: Event) => { WS.q = (e.target as HTMLInputElement).value.trim(); renderWSCat() };
  $('wsClose').onclick = closeWS; $('wsDone').onclick = closeWS;
  document.addEventListener('keydown', e => { if(e.key==='Escape' && !$('ews').hidden){ e.stopImmediatePropagation(); closeWS() } }, true);
};
