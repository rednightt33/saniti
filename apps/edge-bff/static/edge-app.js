/* EDGE shell app, loaded at the end of static/index.html after edge-session.js, edge-client.js, edge-labels.js and
   edge-view.js (re-check R2-19: the shell has no inline script, so its policy keeps script-src 'self' without
   'unsafe-inline'). The look stays in index.html; the preview tool inlines this file like the others. */
/* Edge Workstation — vanilla DOM views, original data and behavior. */
(() => {
"use strict";
// Native DOM utilities: real elements, explicit view state, and event listeners.
// No virtual DOM, runtime compiler, npm, or frontend framework is used.
let currentView = null;
// MONITOR-REVAMP (user 2026-10-29: "Terang"): a browser with no saved choice starts light; a saved choice is kept
let themeState = {theme:'light', toggle:()=>{}};
const views = new Map();
let pendingRefresh = false;
const fragment = Symbol('fragment');
const svgTags = new Set(['svg','path','circle','rect','g','line','polyline','polygon','text','defs','clipPath','linearGradient','stop','ellipse']);
const svgAttributes = {strokeWidth:'stroke-width',strokeLinecap:'stroke-linecap',strokeLinejoin:'stroke-linejoin',textAnchor:'text-anchor',fillRule:'fill-rule',clipRule:'clip-rule'};
const unitless = new Set(['opacity','zIndex','fontWeight','lineHeight','flex','flexGrow','flexShrink','order','strokeWidth']);

// Hash routes also work under file:// and a plain static server, including subfolders.
const entryUrl = new URL(document.currentScript.src || location.href);
const baseUrl = new URL('./', entryUrl);
const entryDocument = document.currentScript.src ? 'index.html' : entryUrl.pathname.split('/').pop() || 'index.html';
// EXEC-CHAT-URL (user 2026-10-24: "B saja ya"): served by the BFF the page uses plain paths (/monitor, /c/<id>), so
// every conversation has its own address; the preview (one file whose scripts are inlined, no server) keeps hash
// routes. Served means its scripts come from the server. A hash route opened on the server (an older link) is still read.
const pathRoutes = location.protocol !== 'file:' && Boolean(document.querySelector('script[src="/edge-client.js"]'));
function routeLocation() {
  if (location.hash.startsWith('#/')) { const url = new URL(location.hash.slice(1), 'https://edge.local'); return {pathname:url.pathname, search:url.search}; }
  // served by the BFF the page path is "/" or "/index.html"; without it (a static copy) the page is the entry file
  const root = pathRoutes ? ['/', '/index.html'].includes(location.pathname)
    : location.pathname === baseUrl.pathname || location.pathname === baseUrl.pathname+entryDocument;
  return {pathname:root ? '/' : location.pathname, search:location.search};
}
function staticUrl(route) {
  if (pathRoutes) return new URL(route, location.origin).href;
  const url = new URL(entryDocument,baseUrl); url.hash = route; return url.href;
}
const routeHistory = {
  pushState(state,title,path) { history.pushState(state,title,staticUrl(path)); },
  replaceState(state,title,path) { history.replaceState(state,title,staticUrl(path)); }
};
function initialValue(view,name,create) {
  if (!Object.hasOwn(view.state,name)) view.state[name]=create();
  return view.state[name];
}
function updateValue(view,name,next) {
  if (!views.has(view.id)) return;
  const previous=view.state[name];
  const result=typeof next==='function'?next(previous):next;
  if(Object.is(previous,result))return;
  view.state[name]=result;
  if(!pendingRefresh){pendingRefresh=true;queueMicrotask(()=>{pendingRefresh=false;refresh()})}
}
function sameValues(a,b) {return a&&b&&a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]));}
function cachedValue(view,name,create,deps) {
  const old=view.cache[name];
  if(!old||!sameValues(old.deps,deps))view.cache[name]={value:create(),deps};
  return view.cache[name].value;
}
function onLifecycle(view,name,setup,deps) {
  const old=view.lifecycle[name];
  if(!old||!sameValues(old.deps,deps))view.pending.push({name,setup,deps});
}
function dispose(view) {for(const effect of Object.values(view.lifecycle))effect.cleanup?.();}
function cloneGraphic(node) {return node.cloneNode(true);}

function element(tag,props,...children) {
  props=props||{};
  if(typeof tag==='function') {
    const parent=currentView;
    const name=tag.name;
    const count=parent?(parent.counts[name]=(parent.counts[name]||0)+1):1;
    const id=(parent?parent.id+'/':'')+name+':'+(props.key??count);
    let view=views.get(id);
    if(!view){view={id,state:{},refs:{},cache:{},lifecycle:{},pending:[],counts:{},seen:true};views.set(id,view)}
    view.seen=true;view.counts={};view.pending=[];
    currentView=view;
    let result;
    try{result=tag({...props,children:children.length===0?undefined:children.length===1?children[0]:children});}
    finally{currentView=parent;}
    if(result instanceof Element&&!result._key)result._key=id;
    return result;
  }
  const node=tag===fragment?document.createDocumentFragment():svgTags.has(tag)?document.createElementNS('http://www.w3.org/2000/svg',tag):document.createElement(tag);
  node._props=props;
  if(props.key!=null)node._key=String(props.key);
  if(tag!==fragment)applyProps(node,props);
  const append=child=>{
    if(Array.isArray(child)){child.forEach(append);return;}
    if(child==null||typeof child==='boolean'||child==='')return;
    node.appendChild(child instanceof Node?child:document.createTextNode(String(child)));
  };
  children.forEach(append);
  if(tag==='select'&&props.value!=null)node.value=String(props.value);
  else if(tag==='select'&&props.defaultValue!=null)node.value=String(props.defaultValue);
  return node;
}
function applyProps(node,props) {
  node._events??={};
  for(const [name,value] of Object.entries(props)) {
    if(name==='children'||name==='key')continue;
    if(name==='ref'){node._ref=value;if(value)value.current=node;continue;}
    if(/^on[A-Z]/.test(name)) {
      let event=name.slice(2).toLowerCase();
      if(name==='onDoubleClick')event='dblclick';
      if(name==='onChange'&&(node.tagName==='INPUT'||node.tagName==='TEXTAREA'))event='input';
      const old=node._events[event];
      if(old)node.removeEventListener(event,old);
      if(typeof value==='function'){node.addEventListener(event,value);node._events[event]=value;}else delete node._events[event];
      continue;
    }
    if(name==='style') {
      node.removeAttribute('style');
      for(const [key,val] of Object.entries(value||{})){
        if(key.startsWith('--'))node.style.setProperty(key,val);
        else node.style[key]=typeof val==='number'&&!unitless.has(key)?val+'px':val;
      }
      continue;
    }
    if(name==='value'||name==='checked'){const applied=name==='value'&&value!=null?String(value):value;if(name==='value'&&node.tagName==='OPTION'&&applied!=null)node.setAttribute('value',applied);else if(applied!=null&&node[name]!==applied)node[name]=applied;continue;}
    if(name==='defaultValue'){if(!node.isConnected&&!node._defaultApplied){node.value=value;node._defaultApplied=true;}continue;}
    const attr=name==='className'?'class':name==='htmlFor'?'for':svgAttributes[name]||name;
    if(value==null || (value===false&&!attr.startsWith('aria-')&&!attr.startsWith('data-')))node.removeAttribute(attr);
    else {
      let text=value===true&&!attr.startsWith('aria-')&&!attr.startsWith('data-')?'':String(value);
      if((attr==='src'&&node.tagName==='IFRAME'||attr==='href'&&node.tagName==='A')&&text.startsWith('/')&&!text.startsWith('/api/'))text=staticUrl(text); // EXEC-EXPORT: an API link (a download) stays a real request
      else if(attr==='href'&&node.tagName==='A'&&text.startsWith('#')&&!text.startsWith('#/'))text=staticUrl(routeLocation().pathname+routeLocation().search+text);
      if(node.getAttribute(attr)!==text)node.setAttribute(attr,text);
    }
  }
}
function transferRefs(node) {
  if(node._ref)node._ref.current=node;
  for(const child of node.childNodes)transferRefs(child);
  if(node.tagName==='SELECT'&&node._props?.value!=null)node.value=String(node._props.value);
  else if(node.tagName==='SELECT'&&node._props?.defaultValue!=null&&!node._connectedDefaultApplied){node.value=String(node._props.defaultValue);node._connectedDefaultApplied=true;}
}
const readerStateAttributes=new Set(['open']);
function patchNode(old,node) {
  if(old.nodeType!==node.nodeType||old.nodeName!==node.nodeName||old._key!==node._key){old.replaceWith(node);transferRefs(node);return node;}
  if(old.nodeType===Node.TEXT_NODE){if(old.data!==node.data)old.data=node.data;return old;}
  if(old.nodeType!==Node.ELEMENT_NODE)return old;
  // M156: an attribute the browser toggles for the reader (open on <details>/<dialog>) belongs to the reader unless the
  // render declares it; a render that does not mention it must not undo the reader's click
  for(const attr of Array.from(old.attributes))if(!node.hasAttribute(attr.name)&&!(attr.name==='style'&&!Object.hasOwn(old._props||{},'style')&&!Object.hasOwn(node._props||{},'style'))&&!(readerStateAttributes.has(attr.name)&&!Object.hasOwn(node._props||{},attr.name)))old.removeAttribute(attr.name);
  for(const attr of Array.from(node.attributes))if(old.getAttribute(attr.name)!==attr.value)old.setAttribute(attr.name,attr.value);
  for(const [event,listener] of Object.entries(old._events||{}))old.removeEventListener(event,listener);
  old._events={};
  old._props=node._props;old._ref=node._ref;
  applyProps(old,node._props||{});
  patchChildren(old,node);
  if(old.tagName==='SELECT'&&node._props?.value!=null)old.value=String(node._props.value);
  transferRefs(old);
  return old;
}
function patchChildren(parent,next) {
  const wanted=Array.from(next.childNodes);
  let cursor=parent.firstChild;
  for(const [index,node] of wanted.entries()) {
    if(!cursor){parent.appendChild(node);transferRefs(node);continue;}
    if(cursor._ref&&cursor._ref!==node._ref&&wanted.slice(index+1).some(next=>next._ref===cursor._ref)){
      parent.insertBefore(node,cursor);transferRefs(node);continue;
    }
    if(node._ref&&cursor._ref!==node._ref){const match=Array.from(parent.childNodes).find(child=>child._ref===node._ref);if(match)parent.insertBefore(match,cursor);if(match)cursor=match;}
    if(node._key&&cursor._key!==node._key){
      const match=Array.from(parent.childNodes).find(child=>child._key===node._key);
      if(match)parent.insertBefore(match,cursor);
      else parent.insertBefore(node,cursor);
      const actual=match?patchNode(match,node):node;
      transferRefs(actual);
      cursor=actual.nextSibling;
    } else {const actual=patchNode(cursor,node);cursor=actual.nextSibling;}
  }
  while(cursor){const nextNode=cursor.nextSibling;cursor.remove();cursor=nextNode;}
}
function refresh() {
  for(const view of views.values())view.seen=false;
  // EXEC-TYPING: patching may move the focused element (a moved node loses focus), e.g. the message box while an
  // answer arrives; the element that had focus gets it back with its caret, before the effects that move focus on purpose
  const focused=document.activeElement;let caret=null;
  try{if(focused&&typeof focused.selectionStart==='number')caret=[focused.selectionStart,focused.selectionEnd,focused.selectionDirection];}catch{}
  const tree=element(App,null);
  const container=document.createDocumentFragment();container.appendChild(tree);
  patchChildren(document.getElementById('root'),container);
  if(focused&&focused!==document.body&&focused.isConnected&&document.activeElement!==focused){
    focused.focus({preventScroll:true});
    if(caret)try{focused.setSelectionRange(...caret);}catch{}
  }
  for(const [id,view] of views){if(!view.seen){dispose(view);views.delete(id)}}
  for(const view of views.values())for(const {name,setup,deps} of view.pending){
    view.lifecycle[name]?.cleanup?.();
    view.lifecycle[name]={deps,cleanup:setup()};
  }
  // Keep previews and public anchors portable without changing their UI.
  for(const frame of document.querySelectorAll('iframe')){
    const src=frame.getAttribute('src');if(src?.startsWith('/'))frame.src=staticUrl(src);
  }
  for(const link of document.querySelectorAll('a[href^="/"]:not([href^="/api/"])'))link.href=staticUrl(link.getAttribute('href')); // EXEC-EXPORT: API links stay real requests
}
addEventListener('hashchange',()=>dispatchEvent(new PopStateEvent('popstate')));

"use strict";
const paths = {
    // EXEC-CHOICES: a choice sent at once (arrow) and a choice the user completes in the message box (pen)
    arrow: element("path", { d: "M5 12h14M13 6l6 6-6 6" }),
    pen: element("path", { d: "M4 20h4L19 9l-4-4L4 16z" }),
    // MONITOR-REVAMP: the glyphs of AI_revamp.html where it draws the same thing
    search: element(fragment, null,
        element("circle", { cx: "11", cy: "11", r: "7" }),
        element("path", { d: "m20 20-3.5-3.5" })),
    bell: element(fragment, null,
        element("path", { d: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" }),
        element("path", { d: "M10 21h4" })),
    help: element(fragment, null,
        element("circle", { cx: "12", cy: "12", r: "9" }),
        element("path", { d: "M9.7 9a2.5 2.5 0 1 1 3.8 2.1c-1.5.9-1.5 1.4-1.5 2.4M12 17h.01" })),
    settings: element(fragment, null,
        element("circle", { cx: "12", cy: "12", r: "3" }),
        element("path", { d: "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" })),
    user: element(fragment, null,
        element("circle", { cx: "12", cy: "8", r: "4" }),
        element("path", { d: "M4 21a8 8 0 0 1 16 0" })),
    bookmark: element("path", { d: "M6 3h12v18l-6-4-6 4z" }),
    pin: element("path", {d:"M12 17v5M9 3h6l-1 6 4 4H6l4-4z"}),
    copy: element(fragment,null,element("rect",{x:9,y:9,width:12,height:12,rx:2}),element("path",{d:"M5 15V5a2 2 0 0 1 2-2h10"})),
    share: element(fragment, null,
        element("circle", { cx: "18", cy: "5", r: "3" }),
        element("circle", { cx: "6", cy: "12", r: "3" }),
        element("circle", { cx: "18", cy: "19", r: "3" }),
        element("path", { d: "m8.6 13.5 6.8 4M15.4 6.5l-6.8 4" })),
    panel: element(fragment, null, element("rect", { x: "3", y: "4", width: "18", height: "16", rx: "2" }), element("path", { d: "M15 4v16" })),
    database: element(fragment, null, element("ellipse", { cx: "12", cy: "5", rx: "8", ry: "3" }), element("path", { d: "M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" })),
    history: element(fragment, null, element("path", { d: "M3 12a9 9 0 1 0 3-6.7L3 8" }), element("path", { d: "M3 3v5h5M12 7v5l3 2" })),
    fork: element("path", { d: "M4 4v6a4 4 0 0 0 4 4h12M16 9l4 5-4 5" }),
    plus: element("path", { d: "M12 5v14M5 12h14" }), more: element(fragment, null,
        element("circle", { cx: "5", cy: "12", r: "1" }),
        element("circle", { cx: "12", cy: "12", r: "1" }),
        element("circle", { cx: "19", cy: "12", r: "1" })),
    chevron: element("path", { d: "m6 9 6 6 6-6" }), close: element("path", { d: "M6 6l12 12M18 6 6 18" }),
    download: element("path", { d: "M12 4v12M6 11l6 6 6-6M4 20h16" }),
    expand: element(fragment, null,
        element("path", { d: "M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" })),
    spark: element("path", { d: "m3 16 4-5 4 3 5-8 5 3" }), filter: element("path", { d: "M3 5h18l-7 8v6l-4 2v-8Z" }),
    // EXEC-NAV-LEFT (user 2026-11-09, icon set 2; Screener the funnel): the pages' icons in the left menu
    navMonitor: element(fragment, null, element("path", { d: "M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z" }), element("path", { d: "M18.5 15l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z" })),
    navTerminal: element(fragment, null, element("rect", { x: "3", y: "4", width: "18", height: "16", rx: "2" }), element("path", { d: "M6.5 15.5l3.5-4 3 2.5 4.5-6" })),
    navBacktest: element(fragment, null, element("circle", { cx: "12", cy: "13", r: "7.5" }), element("path", { d: "M12 9.5V13l2.5 1.5M9.5 3h5M12 3v2.5" })),
    navScreener: element("path", { d: "M4 5h16l-6 7.5V19l-4 1.5v-8z" }),
    // EXEC-OVERVIEW O4: the Market Overview icon of the design (four tiles, the market map)
    navOverview: element(fragment, null, element("rect", { x: "4", y: "4", width: "7", height: "7", rx: "1.5" }), element("rect", { x: "13", y: "4", width: "7", height: "7", rx: "1.5" }), element("rect", { x: "4", y: "13", width: "7", height: "7", rx: "1.5" }), element("rect", { x: "13", y: "13", width: "7", height: "7", rx: "1.5" })),
    // EXEC-WATCHLIST L5: the Watchlist icon of the design (the eye, i-watch)
    navWatchlist: element(fragment, null, element("path", { d: "M2.5 12S6.2 5.5 12 5.5 21.5 12 21.5 12 17.8 18.5 12 18.5 2.5 12 2.5 12z" }), element("circle", { cx: "12", cy: "12", r: "3" })),
    // EXEC-RADAR R7: the Radar icon of R10 (user 2026-11-14: "Untuk icon sudah oke")
    navRadar: element(fragment, null, element("path", { d: "M4 4a16 16 0 0 1 16 16" }), element("path", { d: "M4 10.5a9.5 9.5 0 0 1 9.5 9.5" }), element("path", { d: "M4 20 13 11" }), element("circle", { cx: "16.3", cy: "8.2", r: "1.3" }), element("circle", { cx: "4", cy: "20", r: ".6" })),
    export: element(fragment, null,
        element("path", { d: "M12 15V3m-4 4 4-4 4 4" }),
        element("path", { d: "M5 13v7h14v-7" })), save: element(fragment, null,
        element("path", { d: "M5 4h12l2 2v14H5Z" }),
        element("path", { d: "M8 4v6h8V4M8 20v-6h8v6" })),
    refresh: element("path", { d: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" }), check: element("path", { d: "m5 12 5 5 9-10" }),
    stop: element("rect", { x: "6", y: "6", width: "12", height: "12", rx: "2" }), send: element("path", { d: "M12 19V5M5 12l7-7 7 7" }),
    attach: element("path", { d: "m21 12-8.5 8.5a5 5 0 0 1-7-7L14 5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 8" }),
    trend: element("path", { d: "m3 17 6-6 4 4 8-9" }), eye: element(fragment, null,
        element("path", { d: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12" }),
        element("circle", { cx: "12", cy: "12", r: "3" })),
    chart: element(fragment, null,
        element("path", { d: "M4 20V10M10 20V4M16 20v-7M22 20H2" })),
    cursor: element("path", { d: "m5 3 13 9-6 1-3 6Z" }), line: element("path", { d: "M4 19 20 5" }), rect: element("rect", { x: "4", y: "5", width: "16", height: "14", rx: "1" }),
    text: element(fragment, null,
        element("path", { d: "M5 5h14M12 5v14M8 19h8" })), measure: element(fragment, null,
        element("path", { d: "m4 16 12-12 4 4L8 20Z" }),
        element("path", { d: "m12 8 2 2m-5 1 2 2m-5 1 2 2" })),
    erase: element(fragment, null,
        element("path", { d: "m4 15 9-10 7 7-7 8H8Z" }),
        element("path", { d: "M11 20h10" })), camera: element(fragment, null,
        element("path", { d: "M4 7h4l2-3h4l2 3h4v12H4Z" }),
        element("circle", { cx: "12", cy: "13", r: "4" })),
    maximize: element("path", { d: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" }), sliders: element(fragment, null,
        element("path", { d: "M4 6h7m4 0h5M4 12h3m4 0h9M4 18h10m4 0h2" }),
        element("circle", { cx: "13", cy: "6", r: "2" }),
        element("circle", { cx: "9", cy: "12", r: "2" }),
        element("circle", { cx: "16", cy: "18", r: "2" })),
    menu: element("path", { d: "M4 7h16M4 12h16M4 17h16" }),
    theme: element(fragment, null,
        element("circle", { cx: "12", cy: "12", r: "4" }),
        element("path", { d: "M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" })),
    "arrow-right": element("path", { d: "M5 12h14m-5-5 5 5-5 5" }),
    "arrow-left": element("path", { d: "M19 12H5m5-5-5 5 5 5" }),
    "arrow-up": element("path", { d: "M12 19V5m-5 5 5-5 5 5" }),
    "arrow-down": element("path", { d: "M12 5v14M6 13l6 6 6-6" }),
    play: element("path", { d: "m8 5 11 7-11 7Z" }),
    sort: element("path", { d: "m8 9 4-4 4 4M8 15l4 4 4-4" }),
    "sort-arrows": element("path", { d: "M8 18V6M5 9l3-3 3 3M16 6v12m-3-3 3 3 3-3" }),
    trash: element("path", { d: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" }),
    info: element(fragment, null,
        element("circle", { cx: "12", cy: "12", r: "9" }),
        element("path", { d: "M12 11v5M12 8h.01" })),
    // EXEC-ASK-BRANCH: Branch (a fork) and the side chat (a speech bubble)
    branch: element(fragment, null,
        element("circle", { cx: "6", cy: "5", r: "2" }), element("circle", { cx: "6", cy: "19", r: "2" }),
        element("circle", { cx: "18", cy: "8", r: "2" }), element("path", { d: "M6 7v10M18 10c0 4-6 3-12 7" })),
    chat: element("path", { d: "M21 12a8 8 0 0 1-11.5 7.2L4 21l1.8-5.5A8 8 0 1 1 21 12z" }),
    alert: element("path", { d: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" }),
    pause: element(fragment, null, element("circle", { cx: "12", cy: "12", r: "9" }), element("path", { d: "M10 9v6M14 9v6" })),
    flask: element("path", { d: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3" }),
    bulb: element("path", { d: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" }),
    reply: element("path", { d: "M9 14 4 9l5-5M4 9h11a5 5 0 0 1 5 5v6" }),
    mailbox: element(fragment, null,
        element("path", { d: "M7 6h10a4 4 0 0 1 4 4v7H3v-7a4 4 0 0 1 8 0v7" }),
        element("path", { d: "M15 6V3h3v2h-3M12 17v4M5.5 11h3" })),
    support: element(fragment, null,
        element("path", { d: "M4 13v-1a8 8 0 0 1 16 0v1" }),
        element("path", { d: "M4 13h3v5H5a1 1 0 0 1-1-1Zm16 0h-3v5h2a1 1 0 0 0 1-1Z" }),
        element("path", { d: "M17 18c0 1.5-1.5 2.5-4 2.5" })),
    // Phase 4: the admin page (the beta's admin only)
    shield: element(fragment, null,
        element("path", { d: "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z" }),
        element("path", { d: "M9 12l2 2 4-4" })),
};
function Icon({ name, size = 16 }) {
    return element("svg", { className: "icon", width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.7", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true }, cloneGraphic(paths[name]));
}
function Button({ children, icon, endIcon, kind = "secondary", onClick, disabled, title, ariaLabel, type = "button" }) {
    return element("button", { type: type, className: `btn ${kind} ${endIcon ? "has-end-icon" : ""}`, onClick: onClick, disabled: disabled, title: title, "aria-label": ariaLabel },
        icon && element(Icon, { name: icon }),
        " ",
        children !== undefined && element("span", { className: "btn-label" }, children),
        endIcon && element("span", { className: "btn-end-icon" },
            element(Icon, { name: endIcon })));
}
function IconButton({ icon, selected, onClick, title, buttonRef, disabled }) {
    return element("button", { ref: buttonRef, className: `icon-btn ${selected ? "selected" : ""}`, onClick: onClick, title: title, "aria-label": title, "aria-pressed": selected, disabled: disabled },
        element(Icon, { name: icon }));
}
function Search({ placeholder, value, onChange, onFocus, conversation = false }) {
    return element("label", { className: "search" },
        element(Icon, { name: "search" }),
        element("input", { value: value, onChange: e => onChange?.(e.target.value), onFocus: onFocus, placeholder: placeholder }),
        element("kbd", null, conversation ? element(fragment, null, element("span", null, "\u2318"), element("span", null, "K")) : "\u2318 K"));
}
function Tabs({ items, active, onChange }) {
    return element("div", { className: "tabs", role: "tablist" }, items.map(x => element("button", { role: "tab", "aria-selected": active === x, className: active === x ? "active" : "", onClick: () => onChange(x), key: x }, x)));
}
function Pill({ children, tone = "" }) { return element("span", { className: `pill ${tone}` }, children); }
function SectionTitle({ children, action }) { return element("div", { className: "section-title" },
    element("span", null, children),
    action); }
// EXEC-TERMINAL-API T3 (user 2026-10-25: "buat tab terpisah di sebelah monitor"): the financial terminal tab
// EDGE backtest (CONTRACT.md section 10): the Backtest tab next to Terminal; EXEC-SCREENER: the Screener tab next to Backtest
// EXEC-OVERVIEW O4 (decision 7, 2026-11-15: "OK"): the Overview tab first in the rail; EXEC-WATCHLIST L5: Watchlist after it
const nav = [[EdgeLabels.overview.nav, "overview"], [EdgeLabels.watchlist.nav, "watchlist"], ["Monitor", "monitor"], [EdgeLabels.terminal.nav, "terminal"], [EdgeLabels.backtest.nav, "backtest"], [EdgeLabels.screener.nav, "screener"], [EdgeLabels.radar.nav, "radar"]];
// EXEC-RADAR R7, EXEC-OVERVIEW O4: an owner page shows only when the session says its data can be read
// (/api/v1/auth/session capabilities)
const OWNER_PAGES = ["overview", "watchlist", "radar"];
// live checker S1: a tab this site does not offer (the live site: the Monitor) is never in the rail (Edge.offers).
// 3e (CONTRACT 8b, "every tab is always shown"): an owner page is left out only where the session says its data cannot be
// read at all (capabilities[r] false: no terminal-api); a visitor sees it too, and a tab the principal cannot open shows
// LockedTabPage
const navShown = ([, r]) => Edge.offers(r) && (!OWNER_PAGES.includes(r) || Edge.auth?.capabilities?.[r] !== false);
// the tab of a workspace path, its name in the rail, and whether the principal may open it (<tab>.view)
const TAB_PATHS = {"/terminal":"terminal", "/backtest":"backtest", "/screener":"screener", "/radar":"radar",
    "/overview":"overview", "/watchlist":"watchlist", "/monitor":"monitor"};
const tabName = tab => (nav.find(([, r]) => r === tab) || [tab])[0];
const homeRoute = () => Edge.offers("monitor") ? "monitor" : "terminal";
// the tab of a page frame, from its /<tab>-app/ address (3e, the example mode: the lock box's sender)
const frameTab = frame => { try { return (new URL(frame.getAttribute("src") || "", location.href).pathname.match(/^\/([a-z]+)-app\//) || [])[1] || ""; } catch { return ""; } };
// ERRORS M425 (EXEC-RADAR R7): a sub-app page in one of this shell's frames (Screener, Radar) asks for another page with
// {type:"edge-nav", route}; only this origin, only from a frame of this document, only to a page of the rail. One
// listener for the page's life; shellGo is the current page switch (set by the app on every render).
let shellGo = null;
addEventListener("message", e => {
    if (e.origin !== location.origin || e.data?.type !== "edge-nav" || !shellGo) return;
    const frames = [...document.querySelectorAll("iframe.terminal-frame")].map(f => f.contentWindow);
    if (!frames.includes(e.source) || !["terminal", "backtest", "screener", "radar", "overview", "watchlist"].includes(e.data.route)) return;
    shellGo(e.data.route);
});
function Shell({ route, go, children, chart = false, mobilePanelOpen = false, guest = false }) {
    const viewRecord = currentView;
    // track guest (decision 1 of 2026-11-19): the box the Terminal asks for when the principal does not hold a ticker, an
    // indicator or a feature it chose ({type:"locked", kind, id, name} from its frame, this origin only): sign in for a
    // visitor without an account (guest), upgrade for an account (LockedDialog)
    const locked = initialValue(viewRecord, "locked", () => null), setLocked = next => updateValue(viewRecord, "locked", next);
    onLifecycle(viewRecord, "locked-box", () => {
        // 3e, the example mode (ERRORS M527): from the frame of whichever page is shown, its message naming that page's
        // own tab (the frame's /<tab>-app/ path), so a page in example mode asks for the same box
        const onMsg = e => { const frame = document.querySelector(".terminal-page iframe.terminal-frame");
            if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow || e.data?.type !== "locked" || !e.data.source || e.data.source !== frameTab(frame)) return;
            const name = typeof e.data.name === "string" ? e.data.name.slice(0, 120) : "", id = typeof e.data.id === "string" ? e.data.id.slice(0, 64) : "";
            setLocked({kind: String(e.data.kind || ""), id, name: name || id}); };
        addEventListener("message", onMsg);
        return () => removeEventListener("message", onMsg);
    }, []);
    const { theme, toggle } = themeState;
    const accountOpen = initialValue(viewRecord, "accountOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setAccountOpen = next => updateValue(viewRecord, "accountOpen", next);
    const accountView = initialValue(viewRecord, "accountView", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setAccountView = next => updateValue(viewRecord, "accountView", next);
    const settingsOpen = initialValue(viewRecord, "settingsOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setSettingsOpen = next => updateValue(viewRecord, "settingsOpen", next);
    // re-check R2-20: the password and sign-in page, offered while accounts are on (GET /api/v1/auth/config)
    const securityOpen = initialValue(viewRecord, "securityOpen", () => false), setSecurityOpen = next => updateValue(viewRecord, "securityOpen", next);
    const accountsOn = initialValue(viewRecord, "accountsOn", () => false);
    onLifecycle(viewRecord, "accountsOn", () => { let live = true; Edge.config().then(c => { if (live) updateValue(viewRecord, "accountsOn", c.multiuser === true); }); return () => { live = false; }; }, []);
    const toast = initialValue(viewRecord, "toast", () => ((() => { const seed = ""; return typeof seed === "function" ? seed() : seed; })())), setToast = next => updateValue(viewRecord, "toast", next);
    const supportOpen = initialValue(viewRecord, "supportOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setSupportOpen = next => updateValue(viewRecord, "supportOpen", next);
    const globalSearchOpen = initialValue(viewRecord, "globalSearchOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setGlobalSearchOpen = next => updateValue(viewRecord, "globalSearchOpen", next);
    const notificationsOpen = initialValue(viewRecord, "notificationsOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setNotificationsOpen = next => updateValue(viewRecord, "notificationsOpen", next);
    const notificationsRead = initialValue(viewRecord, "notificationsRead", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setNotificationsRead = next => updateValue(viewRecord, "notificationsRead", next);
    // EXEC-OVERVIEW QA (user 2026-11-15: "1B"): the pages menu of the phone's EDGE bar
    const pagesOpen = initialValue(viewRecord, "pagesOpen", () => false), setPagesOpen = next => updateValue(viewRecord, "pagesOpen", next);
    const pagesRef = (viewRecord.refs.pagesRef ??= { current: null });
    const closePages = (restoreFocus=true) => { setPagesOpen(false); if(restoreFocus)requestAnimationFrame(() => pagesRef.current?.focus()); };
    const supportRef = (viewRecord.refs.supportRef ??= { current: null });
    const avatarRef = (viewRecord.refs.avatarRef ??= { current: null });
    const settingsRef = (viewRecord.refs.settingsRef ??= { current: null });
    const closeAccount = (restoreFocus=true) => { setAccountOpen(false); if(restoreFocus)requestAnimationFrame(() => avatarRef.current?.focus()); };
    const openAccountView = (view) => { closeAccount(); setAccountView(view); };
    const notify = (message) => { setToast(message); window.setTimeout(() => setToast(""), 1800); };
    // Phase 4, the contact-support panel (the user, 2026-11-22: "apabila user unlogin tries to click it maka akan disuruh
    // login dulu"): a visitor gets the sign-in box, an account without support.send the upgrade box, else the dialog
    const openSupport = () => guest ? setLocked({ kind: "support", id: "support", name: EdgeLabels.support.open })
        : !Edge.can("support.send") ? setLocked({ kind: "feature", id: "support.send", name: EdgeLabels.support.open })
        : setSupportOpen(true);
    const marketSoon=initialValue(viewRecord,"marketSoon",()=>false),setMarketSoon=next=>updateValue(viewRecord,"marketSoon",next);
    const marketSoonTimer=cachedValue(viewRecord,"marketSoonTimer",()=>({id:null}),[]);
    const showMarketSoon=()=>{window.clearTimeout(marketSoonTimer.id);setMarketSoon(true);marketSoonTimer.id=window.setTimeout(()=>setMarketSoon(false),3000);};
    onLifecycle(viewRecord,"market-soon-cleanup",()=>()=>window.clearTimeout(marketSoonTimer.id),[]);
    const marketSearchRef=cachedValue(viewRecord,"marketSearchRef",()=>({current:null}),[]);
    const closeMarketSoon=()=>{window.clearTimeout(marketSoonTimer.id);setMarketSoon(false);};
    onLifecycle(viewRecord,"market-soon-dismiss",()=>{
        if(!marketSoon)return;
        const dismiss=event=>{if(event.button===0&&!marketSearchRef.current?.contains(event.target))closeMarketSoon();};
        document.addEventListener("pointerdown",dismiss);
        return ()=>document.removeEventListener("pointerdown",dismiss);
    },[marketSoon]);
    onLifecycle(viewRecord, "effect0", () => { const onKey = (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        // MONITOR-REVAMP (user 2026-10-30, AI_revamp.html): on the Monitor page ⌘K goes to "Search conversations"
        const search = document.querySelector(".conversation-panel .search input");
        if (search && search.offsetParent) { search.focus(); search.select(); } else showMarketSoon();
    } }; document.addEventListener("keydown", onKey); return () => document.removeEventListener("keydown", onKey); }, []);
    /* EXEC-NAV-LEFT option 1 (user 2026-11-09: "Ok opsi 1", then for every page: "1"): the EDGE bar is not shown; its logo,
       Research, theme, settings and account sit in the left menu, the same on every page. Not on a phone (≤ 720 px), where
       the left menu is hidden and the EDGE bar stays the way to the pages' actions and the account */
    const slim = !(typeof matchMedia === "function" && matchMedia("(max-width:720px)").matches);
    /* EXEC-NAV-LEFT (user 2026-11-09: "kalau diterminal dia ada statistics bisa buat seperti terlampir"): the Terminal's
       Statistics button in this menu; the Terminal (same origin, its frame) says whether its panel is open */
    const statsOpen = initialValue(viewRecord, "statsOpen", () => false), setStatsOpen = next => updateValue(viewRecord, "statsOpen", next);
    const statsReady = initialValue(viewRecord, "statsReady", () => false), setStatsReady = next => updateValue(viewRecord, "statsReady", next);
    const termFrame = () => document.querySelector(".terminal-page iframe.terminal-frame");
    onLifecycle(viewRecord, "terminal-stats", () => {
        if (!slim || route !== "terminal") return;
        /* the Terminal answers once its chart is up (ERRORS M412: it may load longer than any fixed wait): EDGE says hello
           until the first answer, and its Statistics button works from then on */
        let again = 0; setStatsReady(false);                      // a Terminal opened again answers again
        const onMsg = e => { if (e.origin === location.origin && e.source === termFrame()?.contentWindow && e.data?.source === "terminal" && e.data.type === "stats") { clearInterval(again); setStatsReady(true); setStatsOpen(!!e.data.open); } };
        const hello = () => termFrame()?.contentWindow?.postMessage({ source: "edge", type: "rail" }, location.origin);
        addEventListener("message", onMsg);
        const f = termFrame(); f?.addEventListener("load", hello); hello();
        again = setInterval(hello, 1000);
        return () => { removeEventListener("message", onMsg); f?.removeEventListener("load", hello); clearInterval(again); };
    }, [slim, route]);
    return element("div", { className: `app ${theme === "dark" ? "dark" : ""} ${chart ? "chart-app" : ""} ${slim ? "slim-top" : ""}` },
        !slim && element("header", { className: "topbar", inert: mobilePanelOpen },
            element("button", { type: "button", ref: pagesRef, className: `pages-btn ${pagesOpen ? "open" : ""}`, onClick: () => setPagesOpen(!pagesOpen),
                "aria-label": pagesOpen ? EdgeLabels.shell.closePages : EdgeLabels.shell.openPages, "aria-haspopup": "menu", "aria-expanded": pagesOpen },
                element(Icon, { name: "menu", size: 20 })),
            pagesOpen && element(PagesMenu, { route: route, go: go, trigger: pagesRef, close: closePages }),
            element("button", { className: "brand", onClick: () => go(homeRoute()) },
                element("span", { className: "brand-mark" }, "E"),
                element("strong", null, "EDGE")),
            element("div", { className: "top-actions" },
                element("span",{className:"market-search-anchor"},
                    element("button",{type:"button",ref:marketSearchRef,className:`search market-search-inactive ${marketSoon?"active":""}`,onClick:()=>marketSoon?closeMarketSoon():showMarketSoon(),"aria-label":"Search markets — coming soon","aria-describedby":marketSoon?"market-search-coming-soon":undefined},
                        element(Icon,{name:"search"}),element("span",{className:"market-search-placeholder"},"Search markets"),element("kbd",null,"⌘ K")),
                    marketSoon&&element("span",{id:"market-search-coming-soon",className:"market-search-ribbon",role:"status","aria-live":"polite"},
                        element("span",null,"Coming soon"),element("button",{type:"button",className:"market-search-ribbon-close","aria-label":"Close Coming soon notification",onClick:closeMarketSoon},element(Icon,{name:"close"})))),
                element(IconButton,{icon:"bell",disabled:true,title:"Notifications unavailable"}),
Edge.offers("monitor") && element(Button, { kind: "ghost", icon: "spark", onClick: () => { sessionStorage.removeItem("edge-research-context"); go("monitor"); } }, "Research"),
                Edge.offers("support") && element(IconButton, { icon: "mailbox", title: EdgeLabels.support.open, selected: supportOpen, onClick: openSupport, buttonRef: supportRef }),
                element(IconButton, { icon: "theme", onClick: toggle, title: `Switch to ${theme === "dark" ? "light" : "dark"} theme` }),
                element(IconButton, { icon: "settings", selected: settingsOpen, onClick: () => setSettingsOpen(true), title: "Settings", buttonRef: settingsRef }),
                guest ? element(Button, { kind: "primary", onClick: () => go("/login") }, EdgeLabels.auth.login.signInTop) :
                element("button", { ref: avatarRef, className: `avatar ${accountOpen ? "open" : ""}`, onClick: () => setAccountOpen(!accountOpen), "aria-label": "Account menu", "aria-haspopup": "menu", "aria-expanded": accountOpen }, "E"),
                accountOpen && element(AccountMenu, { trigger: avatarRef, close: closeAccount, openSettings: () => setSettingsOpen(true), openSecurity: accountsOn ? () => setSecurityOpen(true) : null, openAdmin: adminOpen() ? () => go("admin") : null, openView: openAccountView, signOut: async () => { try { await Edge.signout(); closeAccount(); go("/login"); } catch(e) { notify(e.message); } } }))),
        /* EXEC-NAV-LEFT (user 2026-11-09: "kita akan pindahkan 4 tersebut ke kiri", menu A: icons only, the name in the
           tooltip): the four pages in a 56 px menu on the left, under the top bar */
        element("nav", { className: "side-nav", "aria-label": "Pages", inert: mobilePanelOpen },
            slim && element("button", { type: "button", className: "side-brand", "data-tip": Edge.offers("monitor") ? "EDGE · Monitor" : "EDGE · Terminal", "aria-label": Edge.offers("monitor") ? "EDGE: Monitor" : "EDGE: Terminal", onClick: () => go(homeRoute()) }, element("span", { className: "brand-mark" }, "E")),
            slim && route === "terminal" && element("button", { type: "button", className: `side-stats ${statsOpen ? "active" : ""}`, "data-tip": !statsReady ? "Statistics: loading…" : statsOpen ? "Close Statistics" : "Open Statistics", "aria-label": "Statistics", "aria-expanded": statsOpen, "aria-disabled": !statsReady,
                onClick: () => statsReady && termFrame()?.contentWindow?.postMessage({ source: "edge", type: "stats", open: !statsOpen }, location.origin) },
                element("span", { className: "side-stats-chev" }, statsOpen ? "«" : "»"), element("span", { className: "side-stats-label" }, "Statistics")),
            slim && route === "terminal" && element("span", { className: "side-sep", "aria-hidden": true }),
            nav.filter(navShown).map(([label, r]) => { const active = route === "monitor" ? label === "Monitor" : route === r;
            return element("button", { key: label, type: "button", "aria-current": active ? "page" : undefined, "aria-label": label, "data-tip": label, className: `nav-${label.toLowerCase()} ${active ? "active" : ""}`, onClick: () => go(r) },
                element(Icon, { name: `nav${r[0].toUpperCase()}${r.slice(1)}`, size: 22 })); }),
            slim && element("div", { className: "side-actions" },
                Edge.offers("monitor") && element("button", { type: "button", "data-tip": "Research", "aria-label": "Research", onClick: () => { sessionStorage.removeItem("edge-research-context"); go("monitor"); } }, element(Icon, { name: "spark", size: 20 })),
                adminOpen() && element("button", { type: "button", className: `side-admin ${route === "admin" ? "active" : ""}`, "data-tip": EdgeLabels.admin.nav, "aria-label": EdgeLabels.admin.nav, "aria-current": route === "admin" ? "page" : undefined, onClick: () => go("admin") }, element(Icon, { name: "shield", size: 20 })),
                Edge.offers("support") && element("button", { type: "button", ref: supportRef, className: `side-support ${supportOpen ? "active" : ""}`, "data-tip": EdgeLabels.support.open, "aria-label": EdgeLabels.support.open, "aria-haspopup": "dialog", onClick: openSupport }, element(Icon, { name: "mailbox", size: 20 })),
                element("button", { type: "button", "data-tip": theme === "dark" ? "Light theme" : "Dark theme", "aria-label": `Switch to ${theme === "dark" ? "light" : "dark"} theme`, onClick: toggle }, element(Icon, { name: "theme", size: 20 })),
                element("button", { type: "button", ref: settingsRef, "data-tip": "Settings", "aria-label": "Settings", className: settingsOpen ? "active" : "", onClick: () => setSettingsOpen(true) }, element(Icon, { name: "settings", size: 20 })),
                element("span", { className: "side-account" },
                    guest ? element("button", { type: "button", className: "avatar side-signin", "data-tip": EdgeLabels.auth.login.signInTop, "aria-label": EdgeLabels.auth.login.signInTop, onClick: () => go("/login") }, element(Icon, { name: "user" })) :
                    element("button", { ref: avatarRef, className: `avatar ${accountOpen ? "open" : ""}`, "data-tip": accountOpen ? undefined : "Account", onClick: () => setAccountOpen(!accountOpen), "aria-label": "Account menu", "aria-haspopup": "menu", "aria-expanded": accountOpen }, "E"),
                    accountOpen && element(AccountMenu, { trigger: avatarRef, close: closeAccount, openSettings: () => setSettingsOpen(true), openSecurity: accountsOn ? () => setSecurityOpen(true) : null, openAdmin: adminOpen() ? () => go("admin") : null, openView: openAccountView, signOut: async () => { try { await Edge.signout(); closeAccount(); go("/login"); } catch(e) { notify(e.message); } } })))),
        children,
        false && element(AccountDialog, { view: accountView, setView: setAccountView, close: () => setAccountView(null), returnFocusRef: avatarRef }),
        settingsOpen && element(SettingsDialog, { close: () => setSettingsOpen(false), notify: notify, returnFocusRef: settingsRef }),
        securityOpen && element(SecurityDialog, { close: () => setSecurityOpen(false), returnFocusRef: avatarRef, go, signedOut: () => { setSecurityOpen(false); go("/login"); } }),
        locked && element(LockedDialog, { item: locked, guest, go, close: () => setLocked(null) }),
        edgeTableDialog && element(TableDialog, { key: "edge-table-dialog", spec: edgeTableDialog }),
        supportOpen && element(SupportDialog, { close: () => setSupportOpen(false), returnFocusRef: supportRef }),
        false && element(GlobalMarketSearch, { go: go, close: () => setGlobalSearchOpen(false) }),
        toast && element("div", { className: "toast", role: "status" },
            element(Icon, { name: "check" }),
            toast));
}

/* EXEC-OVERVIEW QA (user 2026-11-15: "1B"): the pages of the left menu, for a phone, where that menu is hidden. The same
   list and rule (nav, navShown); closes on a choice, a tap outside or Escape; arrows move between the pages */
function PagesMenu({ route, go, close, trigger }) {
 const view = currentView, menu = (view.refs.menu ??= { current: null });
 onLifecycle(view, "dismiss", () => {
   const outside = e => { if (!menu.current?.contains(e.target) && !trigger.current?.contains(e.target)) close(false); };
   const key = e => {
     if (e.key === "Escape") { e.preventDefault(); close(); return; }
     if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
     const items = [...(menu.current?.querySelectorAll("button") || [])], i = items.indexOf(document.activeElement);
     if (!items.length) return;
     e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
   };
   document.addEventListener("pointerdown", outside); document.addEventListener("keydown", key);
   requestAnimationFrame(() => (menu.current?.querySelector('[aria-current="page"]') || menu.current?.querySelector("button"))?.focus());
   return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", key); };
 }, []);
 return element("div", { ref: menu, className: "pages-menu", role: "menu", "aria-label": EdgeLabels.shell.pagesMenu },
   nav.filter(navShown).map(([label, r]) => { const active = route === "monitor" ? label === "Monitor" : route === r;
     return element("button", { key: label, type: "button", role: "menuitem", "aria-current": active ? "page" : undefined,
       className: `pages-${r} ${active ? "active" : ""}`, onClick: () => { close(false); go(r); } },
       element(Icon, { name: `nav${r[0].toUpperCase()}${r.slice(1)}`, size: 18 }), element("span", null, label)); }));
}

function AccountMenu({signOut,close,trigger,openSettings,openSecurity,openAdmin}) {
 const view=currentView,menu=(view.refs.menu ??= {current:null});
 onLifecycle(view,"dismiss",()=>{
   const outside=e=>{if(!menu.current?.contains(e.target)&&!trigger.current?.contains(e.target))close(false);};
   const key=e=>{if(e.key==="Escape"){e.preventDefault();close();}};
   document.addEventListener("pointerdown",outside);document.addEventListener("keydown",key);
   requestAnimationFrame(()=>menu.current?.querySelector("button")?.focus());
   return()=>{document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",key);};
 },[]);
 return element("div",{ref:menu,className:"account-menu",role:"menu"},
   // EXEC-UI-1015C (phone): settings left the phone header and opens here
   openSettings&&element("button",{role:"menuitem",className:"account-settings",onClick:()=>{close();openSettings();}},edgeUi().accountSettings),
   openSecurity&&element("button",{role:"menuitem",className:"account-security",onClick:()=>{close();openSecurity();}},EdgeLabels.auth.account.menu),
   // Phase 4: the admin page, for the beta's admin (on every width; the rail's shield is the desktop's shortcut)
   openAdmin&&element("button",{role:"menuitem",className:"account-admin",onClick:()=>{close();openAdmin();}},EdgeLabels.admin.menu),
   element("button",{role:"menuitem",className:"sign-out",onClick:signOut},"Sign out"));
}
function DialogShell({ title, description, close, children, className = "", returnFocusRef }) {
    const viewRecord = currentView;
    const dialog = (viewRecord.refs.dialog ??= { current: null });
    const closeRef = (viewRecord.refs.closeRef ??= { current: close });
    closeRef.current = close;
    onLifecycle(viewRecord, "effect0", () => { const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null; const onKey = (e) => { if (e.key === "Escape") {
        e.preventDefault();
        closeRef.current();
        return;
    } if (e.key !== "Tab" || !dialog.current)
        return; const focusable = Array.from(dialog.current.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')); if (!focusable.length) {
        e.preventDefault();
        dialog.current.focus();
        return;
    } const first = focusable[0], last = focusable[focusable.length - 1]; if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    }
    else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    } }; document.addEventListener("keydown", onKey); requestAnimationFrame(() => { const initial = dialog.current?.querySelector("[data-dialog-initial-focus]"); (initial ?? dialog.current)?.focus(); }); return () => { document.removeEventListener("keydown", onKey); requestAnimationFrame(() => { (returnFocusRef?.current ?? previousFocus)?.focus(); }); }; }, []);
    return element("div", { className: "dialog-backdrop", onMouseDown: e => { if (e.target === e.currentTarget)
            close(); } },
        element("div", { className: `dialog ${className}`, role: "dialog", "aria-modal": "true", "aria-labelledby": "dialog-title", "aria-describedby": "dialog-description", tabIndex: -1, ref: dialog },
            element("div", { className: "dialog-head" },
                element("div", null,
                    element("strong", { id: "dialog-title" }, title),
                    element("small", { id: "dialog-description" }, description)),
                element(IconButton, { icon: "close", title: "Close", onClick: close })),
            children));
}
// track guest (decision 1 of 2026-11-19; words EdgeLabels.locked; the look the design system's dialog, the shell's
// DialogShell): a visitor without an account is asked to sign in (or to create an account while registration is open,
// GET /api/v1/auth/config), an account is told the item is not in its plan, upgrading is coming soon (D7 "segera hadir")
// and the contact of EDGE_UPGRADE_CONTACT, shown as text, or that it comes soon
function LockedDialog({ item, guest, go, close }) {
    const v = currentView, L = EdgeLabels.locked, A = EdgeLabels.access;
    const config = initialValue(v, "config", () => null);
    onLifecycle(v, "config", () => { let live = true; Edge.config().then(c => { if (live) updateValue(v, "config", c); }); return () => { live = false; }; }, []);
    // 3e, the example mode: a click on an example page names the page by its name in the rail, not the Terminal
    const example = item.kind === "example", X = EdgeLabels.example;
    const name = (example && TAB_PATHS[`/${item.id}`] && tabName(item.id)) || (item.kind === "feature" && L.features[item.id]) || item.name || item.id;
    // Phase 4: the rail's mailbox asks a visitor to sign in (kind "support")
    const support = item.kind === "support";
    const title = support && guest ? L.supportGuestTitle : (guest ? L.guestTitle : L.upgradeTitle).replace("{name}", name);
    const open = config?.registration === true;
    // the dialog's first focus is its main button (DialogShell focuses [data-dialog-initial-focus])
    const primary = (text, onClick) => element("button", { type: "button", className: "btn primary", "data-dialog-initial-focus": true, onClick },
        " ", element("span", { className: "btn-label" }, text));
    const guestLead = support ? (open ? L.supportGuestLead : L.supportGuestLeadClosed)
        : example ? (open ? X.dialogGuestLead : X.dialogGuestLeadClosed).replace(/\{name\}/g, name) : open ? L.guestLead : L.guestLeadClosed;
    if (guest) return element(DialogShell, { title, description: guestLead, close, className: "locked-dialog" },
        element("div", { className: "locked-actions" },
            open && element(Button, { onClick: () => { close(); go("/register"); } }, L.register),
            primary(L.signIn, () => { close(); go("/login"); })));
    const contact = config?.upgradeContact || null;
    // the 3e checker 3E-CW-1, every lock surface (the example-mode checker, ERRORS M527): an ended plan renews
    const ended = endedPlan(false);
    if (ended) return element(DialogShell, { title: L.tabEndedTitle.replace("{name}", name),
            description: (example ? X.dialogEndedLead : L.tabEndedLead).replace(/\{name\}/g, name).replace("{plan}", ended), close, className: "locked-dialog" },
        element("div", { className: "locked-body" },
            element("p", { className: "locked-contact" }, contact ? [L.contactRenew, " ", element("strong", null, contact)] : L.contactSoon)),
        element("div", { className: "locked-actions" },
            primary(L.close, close)));
    return element(DialogShell, { title, description: example ? X.dialogUpgradeLead.replace(/\{name\}/g, name) : L.upgradeLead, close, className: "locked-dialog" },
        element("div", { className: "locked-body" },
            element("span", { className: "pill locked-soon" }, A.comingSoon),
            contact ? element("p", { className: "locked-contact" }, L.contact, " ", element("strong", null, contact))
                : element("p", { className: "locked-contact" }, L.contactSoon)),
        element("div", { className: "locked-actions" },
            primary(L.close, close)));
}
// EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527): a tab the
// principal cannot open shows its example when the server serves one to this principal (GET
// /api/v1/examples/<tab>/index answers 200: it holds <tab>.example and the example has files, app/examples.py); any
// other answer, or none, shows LockedTabPage as before. The page runs in its frame with ?example=1 and stays a view of
// one day (shared/example-view.ts): a click there asks for the lock box (kind "example"). The index is asked again on
// every show (the server keeps it in memory), so the note follows a new publication or capture (the Overview's latest
// date: the example-mode checker, ERRORS M527); the last answer per tab and identity shows while the new one comes.
const exampleKnown = new Map();
const exampleIndex = (tab, who) => {
    const key = `${who}\t${tab}`;
    return fetch(`/api/v1/examples/${encodeURIComponent(tab)}/index`, {credentials:"same-origin", headers:{accept:"application/json"}})
        .then(r => r.json().catch(() => null).then(d => r.ok && d && typeof d.files === "object" && d.files && Object.keys(d.files).length ? d : null))
        .catch(() => null)
        .then(d => { if (d) exampleKnown.set(key, d); else exampleKnown.delete(key); return d; });
};
// the 3e checker 3E-CW-1 on every lock surface (LockedTabPage, ExampleTabPage, LockedDialog; the example-mode checker,
// ERRORS M527): an account whose plan ended (access.expired_plan) is told so and to renew, not to upgrade
const endedPlan = guest => !guest && typeof Edge.auth?.access?.expired_plan === "string" && Edge.auth.access.expired_plan ? Edge.auth.access.expired_plan : null;
// the decision came from the access the shell holds: an account's access read again on every show of a locked tab or its
// example (a plan raised or lowered meanwhile, a second factor now needed: access.next), and the shell decides again
// with it (the edge-auth event), so a raised plan opens the tab without a reload; the 3e checker SHELL-2: the person
// comes back to this browser tab (a plan raised meanwhile, after a call to sales): read again once per return, never on
// a timer
const freshAccess = (v, guest, route) => onLifecycle(v, "fresh", () => {
    if (guest) return;
    Edge.refresh();
    const back = () => { if (document.visibilityState === "visible") Edge.refresh(); };
    document.addEventListener("visibilitychange", back);
    return () => document.removeEventListener("visibilitychange", back); }, [route]);
// an ISO date as the design system writes a data date: "Fri 30 Oct 2026"
const exampleDate = iso => { const d = typeof iso === "string" && /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00Z`) : null;
    return d && !isNaN(d) ? d.toLocaleDateString("en-GB", {weekday:"short", day:"numeric", month:"short", year:"numeric", timeZone:"UTC"}).replace(/,/g, "") : ""; };
function ExampleTabPage({ go, route, guest = false }) {
    const v = currentView, X = EdgeLabels.example, L = EdgeLabels.locked, name = tabName(route);
    const who = guest ? "guest:" : `user:${Edge.auth?.login || ""}`;
    const found = initialValue(v, "found", () => ({}));
    const config = initialValue(v, "config", () => null);
    onLifecycle(v, "config", () => { let live = true; Edge.config().then(c => { if (live) updateValue(v, "config", c); }); return () => { live = false; }; }, []);
    freshAccess(v, guest, route);
    onLifecycle(v, "example", () => { let live = true;
        exampleIndex(route, who).then(d => { if (live) updateValue(v, "found", was => ({...was, [`${who}\t${route}`]: d || false})); });
        return () => { live = false; }; }, [route, who]);
    const key = `${who}\t${route}`, index = key in found ? found[key] : exampleKnown.get(key);
    if (index === undefined) return element(Shell, { route, go, guest },
        element("main", { className: "locked-tab", "data-example-tab": route, "aria-busy": "true" },
            element("span", { className: "ml-loading", role: "status" }, X.loading.replace("{name}", name))));
    if (!index) return element(LockedTabPage, { go, route, guest });
    const open = config?.registration === true, contact = config?.upgradeContact || null;
    const date = exampleDate(index.as_of), ended = endedPlan(guest);
    return element(Shell, { route, go, chart: true, guest },
        element("main", { className: "terminal-page example-page", "data-example-tab": route },
            element("div", { className: "example-bar", role: "note" },
                element("span", { className: "pill example-pill" }, X.badge),
                element("span", { className: "example-text" }, (date ? X.banner : X.bannerNoDate).replace("{name}", name).replace("{date}", date), " ",
                    guest ? (open ? X.guest : X.guestClosed).replace("{name}", name)
                          : ended ? [X.ended.replace(/\{name\}/g, name).replace("{plan}", ended), " ", contact ? [L.contactRenew, " ", element("strong", null, contact)] : L.contactSoon]
                          : [X.account.replace("{name}", name), contact ? [" ", L.contact, " ", element("strong", null, contact)] : null]),
                guest && element("span", { className: "example-actions" },
                    open && element(Button, { onClick: () => go("/register") }, L.register),
                    element(Button, { kind: "primary", onClick: () => go("/login") }, L.signIn))),
            element("iframe", { className: "terminal-frame", src: `/${route}-app/?example=1`, title: X.frameTitle.replace("{name}", name) })));
}
// 3e (CONTRACT 8b, "the rail and the frames"; decision 1 of 2026-11-19): a tab the principal cannot open keeps its place
// in the rail and opens this page instead of its app (whose data routes would refuse): a visitor is asked to sign in (or
// to create an account while registration is open), an account is told the tab is not in its plan, upgrading is coming
// soon (D7) and the contact (EDGE_UPGRADE_CONTACT) or that it comes soon. The words are EdgeLabels.locked; the look is the
// design system's empty state. The example mode (decision D4) is to take its place for a tab whose example the plan holds
function LockedTabPage({ go, route, guest = false }) {
    const v = currentView, L = EdgeLabels.locked, A = EdgeLabels.access, name = tabName(route);
    const config = initialValue(v, "config", () => null);
    onLifecycle(v, "config", () => { let live = true; Edge.config().then(c => { if (live) updateValue(v, "config", c); }); return () => { live = false; }; }, []);
    freshAccess(v, guest, route);                       // this page asks the server nothing else (freshAccess above)
    const open = config?.registration === true, contact = config?.upgradeContact || null;
    const ended = endedPlan(guest);
    const terminal = route !== "terminal" && element(Button, { onClick: () => go("/terminal") }, L.openTerminal);
    const body = guest
        ? [element("h1", { className: "locked-tab-title", id: "locked-tab-title" }, L.guestTitle.replace("{name}", name)),
           element("p", { className: "locked-tab-lead" }, (open ? L.tabGuestLead : L.tabGuestLeadClosed).replace("{name}", name)),
           element("div", { className: "locked-actions" }, terminal,
               open && element(Button, { onClick: () => go("/register") }, L.register),
               element(Button, { kind: "primary", onClick: () => go("/login") }, L.signIn))]
        : ended
        ? [element("h1", { className: "locked-tab-title", id: "locked-tab-title" }, L.tabEndedTitle.replace("{name}", name)),
           element("p", { className: "locked-tab-lead" }, L.tabEndedLead.replace("{name}", name).replace("{plan}", ended)),
           element("p", { className: "locked-contact" }, contact ? [L.contactRenew, " ", element("strong", null, contact)] : L.contactSoon),
           element("div", { className: "locked-actions" }, terminal)]
        : [element("h1", { className: "locked-tab-title", id: "locked-tab-title" }, L.upgradeTitle.replace("{name}", name)),
           element("p", { className: "locked-tab-lead" }, L.tabUpgradeLead.replace("{name}", name)),
           element("span", { className: "pill locked-soon" }, A.comingSoon),
           element("p", { className: "locked-contact" }, contact ? [L.contact, " ", element("strong", null, contact)] : L.contactSoon),
           element("div", { className: "locked-actions" }, terminal)];
    return element(Shell, { route, go, guest },
        element("main", { className: "locked-tab", "data-locked-tab": route },
            element("section", { className: "locked-tab-card", "aria-labelledby": "locked-tab-title" }, ...body)));
}
function SettingsDialog({close,returnFocusRef}) {
 return element(DialogShell,{title:"Appearance",description:"Preferences for this browser",close,returnFocusRef},element(Button,{onClick:themeState.toggle},"Switch theme"));
}
// re-check R2-20 (CONTRACT.md section 4): the password change (the other sessions end; this one stays) and sign-out on
// every device, in the shell's dialog; the words are EdgeLabels.auth.account, a refusal shows its server message
// Phase 4, the contact-support panel (the user, 2026-11-22: "Kira2 kalau di klik fungsinya sama seperti SS terlampir";
// "lampiran hanya 2A"; app/support.py): an account's message to the EDGE team, an issue type, a subject, a description and
// at most SUPPORT_LIMITS.images images, with the page's technical details. The checks here only spare a round trip: the
// server checks every field again and names the one to fix (details.reasons), shown under it. SUPPORT_LIMITS is the
// server's (app/support.py IMAGES, IMAGE_BYTES, SUBJECT_CHARS, BODY_CHARS, PAGE_DETAILS; tests/test_support.py holds
// them equal); keep it on one line, JSON
const SUPPORT_LIMITS = {"images":3,"image_bytes":5242880,"subject":120,"body":5000,"types":["image/png","image/jpeg","image/webp"],"details":{"page":200,"frame":200,"viewport":20,"timezone":60,"language":35}};
const supportWords = text => text.replace("{images}", SUPPORT_LIMITS.images).replace("{mb}", SUPPORT_LIMITS.image_bytes / 1048576);
// the type a file's first bytes say (the server's own rule, app/support.py SIGNATURES), or ""
const supportType = async file => {
    const b = new Uint8Array(await file.slice(0, 12).arrayBuffer());
    const at = (i, text) => [...text].every((ch, k) => b[i + k] === ch.charCodeAt(0));
    return b[0] === 0x89 && at(1, "PNG\r\n\x1a\n") ? "image/png" : b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff ? "image/jpeg"
        : at(0, "RIFF") && at(8, "WEBP") ? "image/webp" : "";
};
const supportData = file => new Promise((resolve, reject) => { const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || ""); r.onerror = () => reject(r.error); r.readAsDataURL(file); });
// what the message says about the page it was sent from (the server adds the browser, the build, the site and the plan)
const supportDetails = () => {
    const cut = (key, text) => String(text || "").slice(0, SUPPORT_LIMITS.details[key]);
    let frame = "", zone = "";
    try { const f = document.querySelector(".terminal-page iframe.terminal-frame"); frame = f ? new URL(f.getAttribute("src") || "", location.href).pathname : ""; } catch { /* none */ }
    try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { /* none */ }
    return { page: cut("page", location.pathname), frame: cut("frame", frame), viewport: cut("viewport", `${innerWidth}x${innerHeight}`),
        timezone: cut("timezone", zone), language: cut("language", navigator.language) };
};
const supportSize = bytes => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
// the dialog follows the support dialog of EDGE's own design, whose styles index.html kept (.support-form, .support-body,
// .support-field, .support-attach, .support-files, .support-error, .support-success, .support-foot)
function SupportField({ id, label, note, error, children }) {
    return element("div", { className: "support-field" },
        element("label", { htmlFor: id }, label),
        children,
        error ? element("small", { className: "support-field-error", id: `${id}-note`, role: "alert" }, error)
            : note ? element("small", { className: "support-helper", id: `${id}-note` }, note) : null);
}
function SupportDialog({ close, returnFocusRef }) {
    const v = currentView, S = EdgeLabels.support;
    const f = initialValue(v, "f", () => ({ kind: "bug", subject: "", body: "" })), set = (name, value) => updateValue(v, "f", old => ({ ...old, [name]: value }));
    const files = initialValue(v, "files", () => []), bad = initialValue(v, "bad", () => ({}));
    const busy = initialValue(v, "busy", () => ""), error = initialValue(v, "error", () => ""), sent = initialValue(v, "sent", () => null);
    const picker = (v.refs.picker ??= { current: null });
    const fix = name => { if (bad[name]) updateValue(v, "bad", old => ({ ...old, [name]: "" })); };
    // the chosen files, each checked as the server checks it; the reason of the last one refused stays under the list
    const attach = async list => {
        const chosen = [...(list || [])];
        if (picker.current) picker.current.value = "";
        if (!chosen.length || busy) return;
        updateValue(v, "busy", "attach");
        const next = [...files];
        let problem = "";
        for (const file of chosen) {
            if (next.length >= SUPPORT_LIMITS.images) { problem = supportWords(S.errors.tooMany); break; }
            const type = await supportType(file).catch(() => "");
            if (!SUPPORT_LIMITS.types.includes(type)) { problem = S.errors.type.replace("{name}", file.name); continue; }
            if (file.size > SUPPORT_LIMITS.image_bytes) { problem = supportWords(S.errors.size).replace("{name}", file.name); continue; }
            try { next.push({ name: file.name, size: file.size, type, data: await supportData(file) }); }
            catch { problem = S.errors.read.replace("{name}", file.name); }
        }
        updateValue(v, "files", next); updateValue(v, "bad", old => ({ ...old, images: problem })); updateValue(v, "busy", "");
    };
    const remove = index => { updateValue(v, "files", old => old.filter((_, k) => k !== index)); fix("images"); };
    const send = async e => {
        e.preventDefault();
        if (busy) return;
        const problems = {};
        if (!f.subject.trim()) problems.subject = S.errors.subject;
        if (!f.body.trim()) problems.body = S.errors.body;
        updateValue(v, "bad", problems); updateValue(v, "error", "");
        if (Object.keys(problems).length) { document.getElementById(problems.subject ? "support-subject" : "support-body")?.focus(); return; }
        updateValue(v, "busy", "send");
        let answer;
        try {
            answer = await Edge.sendSupport({ kind: f.kind, subject: f.subject, body: f.body, details: supportDetails(),
                images: files.map(x => ({ name: x.name, type: x.type, data: x.data })) });
        } catch (err) {
            // a field's reason under its field; a reason of what the page itself sent (details, request), or a refusal of
            // the whole message (the hourly limit, the storage), above the actions
            const fields = fieldsOf(err), elsewhere = Object.keys(fields).filter(k => !["kind", "subject", "body", "images"].includes(k));
            updateValue(v, "busy", ""); updateValue(v, "bad", fields);
            updateValue(v, "error", elsewhere.length ? fields[elsewhere[0]] : Object.keys(fields).length ? ""
                : (err?.info?.message || err?.text || S.errors.fallback));
            return;
        }
        updateValue(v, "busy", "");
        updateValue(v, "sent", { ticket: answer?.ticket_id, kind: f.kind, subject: f.subject.trim().replace(/\s+/g, " ") });
        requestAnimationFrame(() => document.querySelector(".support-success .btn.primary")?.focus());
    };
    if (sent) return element(DialogShell, { title: S.title, description: S.lead, close, returnFocusRef, className: "support-dialog" },
        element("div", { className: "support-success", role: "status" },
            element("p", null, S.sent),
            element("dl", null,
                element("dt", null, S.ticket), element("dd", null, `#${sent.ticket}`),
                element("dt", null, S.kind), element("dd", null, S.kinds[sent.kind] || sent.kind),
                element("dt", null, S.subject), element("dd", null, sent.subject)),
            element("div", { className: "support-foot end" },
                element(Button, { kind: "primary", onClick: close }, S.close))));
    const described = id => bad[id.replace("support-", "")] || { "support-subject": S.subjectHint, "support-body": S.bodyHint }[id] ? `${id}-note` : undefined;
    return element(DialogShell, { title: S.title, description: S.lead, close, returnFocusRef, className: "support-dialog" },
        element("form", { className: "support-form", onSubmit: send, noValidate: true },
            element("div", { className: "support-body" },
                element(SupportField, { id: "support-kind", label: S.kind, error: bad.kind },
                    element("span", { className: "settings-select" },
                        element("select", { id: "support-kind", value: f.kind, disabled: !!busy, "data-dialog-initial-focus": true, onChange: e => set("kind", e.target.value) },
                            Object.entries(S.kinds).map(([key, words]) => element("option", { key, value: key }, words))),
                        element(Icon, { name: "chevron" }))),
                element(SupportField, { id: "support-subject", label: S.subject, note: S.subjectHint, error: bad.subject },
                    element("input", { id: "support-subject", className: "settings-input", value: f.subject, maxLength: SUPPORT_LIMITS.subject, autoComplete: "off", disabled: !!busy,
                        "aria-invalid": !!bad.subject, "aria-describedby": described("support-subject"), onChange: e => { set("subject", e.target.value); fix("subject"); } })),
                element(SupportField, { id: "support-body", label: S.body, note: S.bodyHint, error: bad.body },
                    element("textarea", { id: "support-body", className: "settings-input", value: f.body, maxLength: SUPPORT_LIMITS.body, rows: 5, disabled: !!busy,
                        "aria-invalid": !!bad.body, "aria-describedby": described("support-body"), onChange: e => { set("body", e.target.value); fix("body"); } })),
                element("div", { className: "support-field" },
                    element("input", { ref: picker, id: "support-images", type: "file", accept: SUPPORT_LIMITS.types.join(","), multiple: true, hidden: true, onChange: e => attach(e.target.files) }),
                    element("button", { type: "button", className: "support-attach", disabled: !!busy || files.length >= SUPPORT_LIMITS.images, onClick: () => picker.current?.click() },
                        busy === "attach" ? element("span", { className: "support-progress", "aria-hidden": true }) : element(Icon, { name: "attach", size: 14 }), S.attach),
                    files.length > 0 && element("ul", { className: "support-files", "aria-label": S.attached },
                        files.map((x, index) => element("li", { key: `${index}-${x.name}` },
                            element(Icon, { name: "attach", size: 12 }),
                            element("span", { title: x.name }, x.name),
                            element("small", null, supportSize(x.size)),
                            element("button", { type: "button", disabled: !!busy, "aria-label": S.remove.replace("{name}", x.name), title: S.remove.replace("{name}", x.name), onClick: () => remove(index) },
                                element(Icon, { name: "close", size: 12 }))))),
                    bad.images ? element("small", { className: "support-field-error", role: "alert" }, bad.images) : element("small", { className: "support-helper" }, supportWords(S.attachHint))),
                element("p", { className: "support-helper support-note" }, element(Icon, { name: "info", size: 13 }), element("span", null, S.note)),
                error && element("div", { className: "support-error", role: "alert" }, element("span", null, error))),
            element("div", { className: "support-foot actions" },
                element(Button, { onClick: close, disabled: busy === "send" }, S.cancel),
                element(Button, { kind: "primary", type: "submit", disabled: !!busy }, busy === "send" ? S.sending : S.send))));
}
function SecurityDialog({close, returnFocusRef, signedOut, go}) {
  const v = currentView, A = EdgeLabels.auth.account, L = EdgeLabels.auth;
  const f = initialValue(v, "f", () => ({current:"", password:"", repeat:""})), set = (name, value) => updateValue(v, "f", old => ({...old, [name]:value}));
  const busy = initialValue(v, "busy", () => ""), error = initialValue(v, "error", () => ""), done = initialValue(v, "done", () => ""), bad = initialValue(v, "bad", () => ({}));
  const change = async e => { e.preventDefault(); if (busy) return;
    const problem = passwordProblem(f.password, f.repeat); if (problem) { updateValue(v, "error", problem); return; }
    updateValue(v, "busy", "change"); updateValue(v, "error", ""); updateValue(v, "done", ""); updateValue(v, "bad", {});
    try { await Edge.changePassword(f.current, f.password, f.repeat); updateValue(v, "done", A.changed); }
    catch (err) { updateValue(v, "error", authText(err)); updateValue(v, "bad", fieldsOf(err)); }
    finally { updateValue(v, "busy", ""); updateValue(v, "f", {current:"", password:"", repeat:""}); } };
  const everywhere = async () => { if (busy) return; updateValue(v, "busy", "all"); updateValue(v, "error", "");
    try { await Edge.signoutEverywhere(); signedOut(); } catch (err) { updateValue(v, "error", authText(err)); updateValue(v, "busy", ""); } };
  return element(DialogShell, {title:A.title, description:A.lead, close, returnFocusRef, className:"security-dialog"},
    element("form", {onSubmit:change},
      element(AuthField, {label:A.current, error:bad.current_password}, element("input", {id:"auth-current-password", type:"password", autoComplete:"current-password", maxLength:256, value:f.current, required:true, disabled:!!busy, "data-dialog-initial-focus":true, onChange:e => set("current", e.target.value)})),
      element(AuthField, {label:A.password, support:A.passwordHint, error:bad.password}, element("input", {id:"auth-new-password", type:"password", autoComplete:"new-password", maxLength:256, value:f.password, required:true, disabled:!!busy, onChange:e => set("password", e.target.value)})),
      element(AuthField, {label:A.repeat, error:bad.password_repeat}, element("input", {id:"auth-repeat-new-password", type:"password", autoComplete:"new-password", maxLength:256, value:f.repeat, required:true, disabled:!!busy, onChange:e => set("repeat", e.target.value)})),
      done && element("p", {className:"auth-note", role:"status"}, done),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      element(Button, {kind:"primary", type:"submit", disabled:!!busy}, busy === "change" ? A.busy : A.submit)),
    Edge.auth?.access?.mfa_enrolled === true && element(SettingsHeading, {title:A.mfaTitle, description:A.mfaLead}),
    Edge.auth?.access?.mfa_enrolled === true && element(Button, {disabled:!!busy, onClick:() => { authFlow.enrolling = true; close(); go("/mfa"); }}, A.mfaNew),
    element(SettingsHeading, {title:A.allTitle, description:A.allLead}),
    element(Button, {onClick:everywhere, disabled:!!busy}, busy === "all" ? A.allBusy : A.all));
}
function SettingsHeading({ title, description }) { return element("div", { className: "settings-heading" },
    element("strong", null, title),
    element("p", null, description)); }
function SettingsRow({ name, description, children }) { return element("div", { className: "settings-row" },
    element("div", null,
        element("strong", null, name),
        description && element("small", null, description)),
    element("div", null, children)); }
function SettingsSelect({ label, value, options, onChange, disabledOptions = [] }) { return element("label", { className: "settings-select" },
    element("span", { className: "sr-only" }, label),
    element("select", { "aria-label": label, value: value, onChange: e => onChange(e.target.value) }, options.map(x => element("option", { key: x, disabled: disabledOptions.includes(x) }, x))),
    element(Icon, { name: "chevron" })); }
function Switch({ label, checked, onChange }) { return element("button", { className: `switch ${checked ? "checked" : ""}`, role: "switch", "aria-label": label, "aria-checked": checked, onClick: () => onChange(!checked) },
    element("span", null)); }
function AppLink({ to, go, children, className = "" }) {
    const available = ["/", "/login", "/monitor", "/markets"].includes(to);
    return element("a", { href: available ? staticUrl(to === "/" ? "/login" : to) : undefined,
        className, "aria-disabled": !available, title: available ? undefined : "Page not included in this extract",
        onClick: event => { event.preventDefault(); if (available) go(to); } }, children);
}
function PublicBrand({ go }) {
    return element(AppLink, { to: "/", go: go, className: "brand public-brand" },
        element("span", { className: "brand-mark" }, "E"),
        element("strong", null, "EDGE"));
}
function PublicThemeButton() {
    const { theme, toggle } = themeState;
    return element(IconButton, { icon: "theme", onClick: toggle, title: `Switch to ${theme === "dark" ? "light" : "dark"} theme` });
}

// EXEC-MU-ACCOUNTS Phase 1 (contract sections 4 and 12): the account pages share the sign-in page's look. One mode per
// route (ROUTES): login, register, verify (the email code), forgot, reset (code and new password), mfa (the admin's
// authenticator: enrol with a QR code drawn here, or verify). The words are EdgeLabels.auth; a refusal shows the
// server's message (error.message) and the code's words only when it sends none. The email being verified lives in
// this page's memory (authFlow), never in storage or the address.
const authFlow = {email:"", purpose:"register", sentAt:0, notice:"", resendAfter:60, mfaEnrolled:null, enrolling:false};
const CODE_SECONDS = 300, RESEND_SECONDS = 60;
const authText = error => error?.info?.message || EdgeLabels.auth.errors[error?.info?.code || error?.code] || error?.text || EdgeLabels.auth.errors.fallback;
// re-check R2-14 (decision D1: the assistant is the admin's): a sign-in lands on the Monitor only for an account whose
// access holds it ('*' or monitor.view; the switch-off owner holds '*'); any other account lands on the Terminal
// Phase 4 (the user, 2026-11-22; the Telegram summary links /admin?ticket=<id>): a sign-in shown at a workspace page
// stays on it, its address and query kept, when the account can open that page (opens: the site offers it and the
// account holds what opens it, the route's `needs` or <title>.view); an account page (login, verify, mfa) or a page the
// account cannot open still leads to the landing page
const opens = r => !!r && r.auth === true && Edge.offers(r.title) && Edge.can(r.needs || `${r.title}.view`);
const landing = () => { const here = routeLocation().pathname, r = routeOf(here);
    if (r && r.path === here && opens(r)) return r.path;
    const caps = Edge.auth?.access?.capabilities;
    return !Array.isArray(caps) || caps.includes("*") || caps.includes("monitor.view") ? "/monitor" : "/terminal"; };
const passwordProblem = (password, repeat) => { const C = EdgeLabels.auth.check;
  return password.length < 8 ? C.short : password.length > 256 ? C.long : password !== repeat ? C.mismatch : ""; };
// a code was sent: the server says when a new one may be asked for (resend_after_s, 60 s)
const codeSent = (email, purpose, answer) => { authFlow.email = email; authFlow.purpose = purpose; authFlow.sentAt = Date.now();
  authFlow.resendAfter = Number.isFinite(answer?.resend_after_s) ? answer.resend_after_s : RESEND_SECONDS; };
// a refusal by field (details.fields, details.reasons[field]): the reason is shown under its field
const fieldsOf = error => { const d = error?.info?.details || {}, reasons = d.reasons && typeof d.reasons === "object" ? d.reasons : {};
  return Object.fromEntries((Array.isArray(d.fields) ? d.fields : Object.keys(reasons)).filter(f => typeof reasons[f] === "string").map(f => [f, reasons[f]])); };
// the QR code library (static/qrcode-generator.js, MIT, served from this origin) is read only by the /mfa page
let qrLibrary = null;
const loadQr = () => qrLibrary || (qrLibrary = window.qrcode ? Promise.resolve(window.qrcode) : new Promise((ok, no) => {
  const script = document.createElement("script"); script.src = "/qrcode-generator.js"; script.onload = () => window.qrcode ? ok(window.qrcode) : no(new Error("qr"));
  script.onerror = () => { qrLibrary = null; no(new Error("qr")); }; document.head.appendChild(script); }));
function QrCode({text}) {
  const v = currentView, cells = initialValue(v, "cells", () => null), failed = initialValue(v, "failed", () => false);
  onLifecycle(v, "draw", () => { let live = true;
    loadQr().then(qrcode => { const qr = qrcode(0, "M"); qr.addData(text); qr.make(); const n = qr.getModuleCount(), out = [];
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) out.push(`M${c} ${r}h1v1h-1z`);
      if (live) updateValue(v, "cells", {n, d:out.join("")}); }).catch(() => { if (live) updateValue(v, "failed", true); });
    return () => { live = false; }; }, [text]);
  if (failed) return element("p", {className:"auth-note"}, EdgeLabels.auth.mfa.qrFailed);
  if (!cells) return element("div", {className:"auth-qr auth-qr-wait", "aria-hidden":"true"});
  return element("svg", {className:"auth-qr", viewBox:`0 0 ${cells.n + 8} ${cells.n + 8}`, role:"img", "aria-label":"QR code"},
    element("rect", {width:cells.n + 8, height:cells.n + 8, fill:"#fff"}),
    element("path", {d:cells.d, fill:"#000", transform:"translate(4 4)"}));
}
function AuthShell({title, lead, children, go}) {
  return element("div",{className:"auth-page"},element("div",{className:"auth-top"},element(PublicBrand,{go}),element(PublicThemeButton)),
    element("main",{className:"auth-shell"},element("div",{className:"auth-form-wrap"},
      element("div",{className:"auth-heading"},element("h1",null,title),lead&&element("p",null,lead)),children)),element(AuthFooter));
}
const authLink = (go, to, text) => element("a", {href:to, className:"auth-link", onClick:e => { e.preventDefault(); go(to); }}, text);
function AuthPage({go, mode = "login"}) {
  const L = EdgeLabels.auth;
  if (mode === "closed") return element(AuthShell, {go, title:L.closed.title, lead:L.closed.lead},
    element("p", {className:"auth-switch"}, authLink(go, "/terminal", L.closed.terminal), " · ", authLink(go, "/login", L.closed.back)));
  if (mode === "register") return element(RegisterForm, {go, L});
  if (mode === "verify") return element(CodeForm, {go, L});
  if (mode === "forgot") return element(ForgotForm, {go, L});
  if (mode === "reset") return element(ResetForm, {go, L});
  if (mode === "mfa") return element(MfaForm, {go, L});
  return element(LoginForm, {go, L});
}
function LoginForm({go, L}) {
 const v=currentView,login=initialValue(v,"login",()=>""),password=initialValue(v,"password",()=>""),busy=initialValue(v,"busy",()=>false),error=initialValue(v,"error",()=>""),open=initialValue(v,"open",()=>false),hint=initialValue(v,"hint",()=>false);
 // track guest: "Create account" only while registration is open (not in the pre-launch mode), "Forgot password?" with
 // accounts on, and the Terminal without an account where the site has guests
 const registration=initialValue(v,"registration",()=>false),guests=initialValue(v,"guests",()=>false);
 onLifecycle(v,"config",()=>{let live=true;Edge.config().then(c=>{if(live){updateValue(v,"open",c.multiuser);updateValue(v,"registration",c.registration===true);updateValue(v,"guests",c.guests===true);}});return()=>{live=false;};},[]);
 const notice=authFlow.notice;
 const submit=async e=>{e.preventDefault();if(busy)return;updateValue(v,"busy",true);updateValue(v,"error","");authFlow.notice="";
  try{await Edge.signin(login,password);updateValue(v,"password","");go(landing());}
  catch(e){const code=e.info?.code;
   if(code==="MFA_REQUIRED"){authFlow.mfaEnrolled=typeof e.info.details?.mfa_enrolled==="boolean"?e.info.details.mfa_enrolled:null;updateValue(v,"password","");go("/mfa");return;}
   // a pending registration answers the same 401 as a wrong password (no enumeration; the server emails a new code):
   // the page says where the code goes, with registration open only
   updateValue(v,"hint",code==="INVALID_CREDENTIALS");
   if(code==="INVALID_CREDENTIALS"){authFlow.email=login.includes("@")?login.trim():"";authFlow.purpose="register";authFlow.sentAt=0;}
   updateValue(v,"error",e.info?authText(e):e.message);}
  finally{updateValue(v,"busy",false);}};
 return element(AuthShell,{go,title:L.login.title,lead:L.login.lead},
  element("form",{onSubmit:submit},
   notice&&element("p",{className:"auth-note",role:"status"},notice),
   element(AuthField,{label:L.login.login},element("input",{id:"auth-login",autoComplete:"username",value:login,required:true,disabled:busy,onChange:e=>updateValue(v,"login",e.target.value)})),
   element(AuthField,{label:L.login.password},element("input",{id:"auth-password",type:"password",autoComplete:"current-password",value:password,required:true,disabled:busy,onChange:e=>updateValue(v,"password",e.target.value)})),
   open&&element("div",{className:"auth-row-end"},authLink(go,"/forgot",L.login.forgot)),
   error&&element("p",{className:"auth-error",role:"alert"},error),
   error&&hint&&open&&element("p",{className:"auth-note"},L.login.justRegistered," ",authLink(go,"/verify",L.login.verifyLink),"."),
   element(Button,{kind:"primary",type:"submit",disabled:busy},busy?L.login.busy:L.login.submit)),
  registration&&element("p",{className:"auth-switch"},L.login.noAccount," ",authLink(go,"/register",L.login.create)),
  guests&&element("p",{className:"auth-switch"},authLink(go,"/terminal",L.login.guest)));
}
function RegisterForm({go, L}) {
  const v = currentView, R = L.register, f = initialValue(v, "f", () => ({username:"", first_name:"", last_name:"", email:"", phone:"", password:"", password_repeat:""}));
  const busy = initialValue(v, "busy", () => false), error = initialValue(v, "error", () => ""), bad = initialValue(v, "bad", () => ({}));
  const set = name => e => { updateValue(v, "f", old => ({...old, [name]:e.target.value})); if (bad[name]) updateValue(v, "bad", old => ({...old, [name]:undefined})); };
  const submit = async e => { e.preventDefault(); if (busy) return;
    const problem = passwordProblem(f.password, f.password_repeat); if (problem) { updateValue(v, "error", problem); return; }
    updateValue(v, "busy", true); updateValue(v, "error", ""); updateValue(v, "bad", {});
    try { const answer = await Edge.register({...f, username:f.username.trim().toLowerCase(), email:f.email.trim()}); codeSent(f.email.trim(), "register", answer);
      updateValue(v, "f", old => ({...old, password:"", password_repeat:""})); go("/verify"); }
    catch (e) { updateValue(v, "error", authText(e)); updateValue(v, "bad", fieldsOf(e)); } finally { updateValue(v, "busy", false); } };
  const field = (label, name, extra = {}, support) => element(AuthField, {label, support, error:bad[name]},
    element("input", {id:`auth-${label.toLowerCase().replaceAll(" ", "-")}`, value:f[name], required:true, disabled:busy, onChange:set(name), ...extra}));
  return element(AuthShell, {go, title:R.title, lead:R.lead},
    element("form", {onSubmit:submit},
      field(R.username, "username", {autoComplete:"username", pattern:"[a-z0-9_]{3,30}", maxLength:30, autoCapitalize:"none"}, R.usernameHint),
      element("div", {className:"auth-pair"}, field(R.firstName, "first_name", {autoComplete:"given-name"}), field(R.lastName, "last_name", {autoComplete:"family-name"})),
      field(R.email, "email", {type:"email", autoComplete:"email"}),
      field(R.phone, "phone", {type:"tel", autoComplete:"tel", inputMode:"tel"}, R.phoneHint),
      field(R.password, "password", {type:"password", autoComplete:"new-password", maxLength:256}, R.passwordHint),
      field(R.repeat, "password_repeat", {type:"password", autoComplete:"new-password", maxLength:256}),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      element(Button, {kind:"primary", type:"submit", disabled:busy}, busy ? R.busy : R.submit)),
    element("p", {className:"auth-switch"}, R.haveAccount, " ", authLink(go, "/login", R.signIn)));
}
// the seconds left of the code (5 minutes) and before a new one may be sent (60 s), counted on this page each second
function useClock(v) {
  const now = initialValue(v, "now", () => Date.now());
  onLifecycle(v, "clock", () => { const t = setInterval(() => updateValue(v, "now", Date.now()), 1000); return () => clearInterval(t); }, []);
  const since = authFlow.sentAt ? Math.floor((now - authFlow.sentAt) / 1000) : null;
  return {left:since === null ? null : Math.max(0, CODE_SECONDS - since), wait:since === null ? 0 : Math.max(0, authFlow.resendAfter - since)};
}
const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
function CodeInput({id = "auth-code", value, disabled, onChange}) {
  return element("input", {id, value, required:true, disabled, inputMode:"numeric", autoComplete:"one-time-code", pattern:"[0-9]{6}",
    onChange:e => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))});
}
function Resend({v, L, wait, purpose}) {
  const busy = initialValue(v, "resending", () => false);
  const resend = async () => { if (busy || wait > 0 || !authFlow.email) return; updateValue(v, "resending", true);
    try { codeSent(authFlow.email, purpose, await Edge.resendCode(authFlow.email, purpose)); updateValue(v, "info", L.verify.resent); updateValue(v, "error", ""); }
    catch (e) { updateValue(v, "error", authText(e)); } finally { updateValue(v, "resending", false); } };
  return element("p", {className:"auth-switch"}, wait > 0 ? `${L.verify.resendIn} ${wait} s.`
    : element("button", {type:"button", className:"text-link", disabled:busy || !authFlow.email, onClick:resend}, L.verify.resend));
}
function CodeForm({go, L}) {
  const v = currentView, V = L.verify, code = initialValue(v, "code", () => ""), email = initialValue(v, "email", () => authFlow.email);
  // USERNAME_TAKEN (decided only after the code is proved): the code owner chooses another username here
  const taken = initialValue(v, "taken", () => false), username = initialValue(v, "username", () => "");
  const busy = initialValue(v, "busy", () => false), error = initialValue(v, "error", () => ""), info = initialValue(v, "info", () => ""), bad = initialValue(v, "bad", () => ({}));
  const {left, wait} = useClock(v);
  const submit = async e => { e.preventDefault(); if (busy) return; if (!/^\d{6}$/.test(code)) { updateValue(v, "error", L.check.code); return; }
    authFlow.email = email.trim(); updateValue(v, "busy", true); updateValue(v, "error", ""); updateValue(v, "bad", {});
    try { await Edge.verifyEmail(authFlow.email, code, taken ? username.trim().toLowerCase() : undefined); authFlow.notice = ""; go(landing()); }
    catch (e) { if (e.info?.code === "USERNAME_TAKEN") { updateValue(v, "taken", true); updateValue(v, "error", e.info.message || V.usernameTaken); }
      else { updateValue(v, "error", authText(e)); updateValue(v, "bad", fieldsOf(e)); } } finally { updateValue(v, "busy", false); } };
  const notice = authFlow.notice;
  return element(AuthShell, {go, title:V.title, lead:authFlow.email ? `${V.sentTo} ${authFlow.email}.` : V.sent},
    element("form", {onSubmit:submit},
      notice && element("p", {className:"auth-note", role:"status"}, notice),
      element("p", {className:"auth-note"}, V.sameBrowser),
      !authFlow.email && element(AuthField, {label:V.email, error:bad.email}, element("input", {id:"auth-email", type:"email", autoComplete:"email", value:email, required:true, disabled:busy,
        onChange:e => { updateValue(v, "email", e.target.value); authFlow.email = e.target.value.trim(); }})),
      element(AuthField, {label:V.code, support:V.codeHint, error:bad.code}, element(CodeInput, {value:code, disabled:busy, onChange:next => updateValue(v, "code", next)})),
      taken && element(AuthField, {label:V.username, support:L.register.usernameHint, error:bad.username}, element("input", {id:"auth-new-username", value:username, required:true, disabled:busy,
        autoComplete:"username", pattern:"[a-z0-9_]{3,30}", maxLength:30, autoCapitalize:"none", onChange:e => updateValue(v, "username", e.target.value)})),
      left !== null && element("p", {className:"auth-countdown", role:"timer", "aria-live":"off"}, left > 0 ? `${V.expiresIn} ${mmss(left)}.` : V.expired),
      info && element("p", {className:"auth-note", role:"status"}, info),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      element(Button, {kind:"primary", type:"submit", disabled:busy}, busy ? V.busy : V.submit)),
    element(Resend, {v, L, wait, purpose:"register"}),
    element("p", {className:"auth-switch"}, authLink(go, "/login", V.back)));
}
function ForgotForm({go, L}) {
  const v = currentView, F = L.forgot, email = initialValue(v, "email", () => authFlow.email), busy = initialValue(v, "busy", () => false), error = initialValue(v, "error", () => "");
  const submit = async e => { e.preventDefault(); if (busy) return; updateValue(v, "busy", true); updateValue(v, "error", "");
    try { codeSent(email.trim(), "reset", await Edge.forgotPassword(email.trim())); go("/reset"); }
    catch (e) { updateValue(v, "error", authText(e)); } finally { updateValue(v, "busy", false); } };
  return element(AuthShell, {go, title:F.title, lead:F.lead},
    element("form", {onSubmit:submit},
      element(AuthField, {label:F.email}, element("input", {id:"auth-email", type:"email", autoComplete:"email", value:email, required:true, disabled:busy, onChange:e => updateValue(v, "email", e.target.value)})),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      element(Button, {kind:"primary", type:"submit", disabled:busy}, busy ? F.busy : F.submit)),
    element("p", {className:"auth-switch"}, authLink(go, "/login", F.back)));
}
function ResetForm({go, L}) {
  const v = currentView, P = L.reset, f = initialValue(v, "f", () => ({email:authFlow.email, code:"", password:"", password_repeat:""}));
  const busy = initialValue(v, "busy", () => false), error = initialValue(v, "error", () => ""), info = initialValue(v, "info", () => ""), bad = initialValue(v, "bad", () => ({}));
  const {left, wait} = useClock(v);
  const set = (name, value) => updateValue(v, "f", old => ({...old, [name]:value}));
  const submit = async e => { e.preventDefault(); if (busy) return;
    if (!/^\d{6}$/.test(f.code)) { updateValue(v, "error", L.check.code); return; }
    const problem = passwordProblem(f.password, f.password_repeat); if (problem) { updateValue(v, "error", problem); return; }
    authFlow.email = f.email.trim(); updateValue(v, "busy", true); updateValue(v, "error", "");
    try { await Edge.resetPassword(authFlow.email, f.code, f.password, f.password_repeat); authFlow.sentAt = 0; authFlow.notice = L.login.resetDone; go("/login"); }
    catch (e) { updateValue(v, "error", authText(e)); updateValue(v, "bad", fieldsOf(e)); } finally { updateValue(v, "busy", false); set("password", ""); set("password_repeat", ""); } };
  return element(AuthShell, {go, title:P.title, lead:authFlow.email ? `${P.sentTo} ${authFlow.email}.` : L.verify.sent},
    element("form", {onSubmit:submit},
      element("p", {className:"auth-note"}, P.sameBrowser),
      !authFlow.email && element(AuthField, {label:L.forgot.email}, element("input", {id:"auth-email", type:"email", autoComplete:"email", value:f.email, required:true, disabled:busy,
        onChange:e => { set("email", e.target.value); authFlow.email = e.target.value.trim(); }})),
      element(AuthField, {label:P.code, support:L.verify.codeHint, error:bad.code}, element(CodeInput, {value:f.code, disabled:busy, onChange:next => set("code", next)})),
      left !== null && element("p", {className:"auth-countdown", role:"timer", "aria-live":"off"}, left > 0 ? `${L.verify.expiresIn} ${mmss(left)}.` : L.verify.expired),
      element(AuthField, {label:P.password, support:P.passwordHint, error:bad.password}, element("input", {id:"auth-new-password", type:"password", autoComplete:"new-password", maxLength:256, value:f.password, required:true, disabled:busy, onChange:e => set("password", e.target.value)})),
      element(AuthField, {label:P.repeat, error:bad.password_repeat}, element("input", {id:"auth-repeat-new-password", type:"password", autoComplete:"new-password", maxLength:256, value:f.password_repeat, required:true, disabled:busy, onChange:e => set("password_repeat", e.target.value)})),
      info && element("p", {className:"auth-note", role:"status"}, info),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      element(Button, {kind:"primary", type:"submit", disabled:busy}, busy ? P.busy : P.submit)),
    element(Resend, {v, L, wait, purpose:"reset"}),
    element("p", {className:"auth-note"}, P.noMail),
    element("p", {className:"auth-switch"}, authLink(go, "/login", P.back)));
}
function MfaForm({go, L}) {
  const v = currentView, M = L.mfa, code = initialValue(v, "code", () => ""), recovery = initialValue(v, "recovery", () => false);
  const busy = initialValue(v, "busy", () => false), error = initialValue(v, "error", () => ""), enrol = initialValue(v, "enrol", () => null), saved = initialValue(v, "saved", () => false);
  // MFA_LOCKED: the server's message and its unlock time (details.unlock_at, shown in this viewer's local time);
  // details.use names the way still open ("recovery_code" or "code"), and with none Continue waits for the unlock (or a
  // password reset by email, which clears the lock: the Forgot password? link stays on this page)
  const locked = initialValue(v, "locked", () => ""), unlockAt = initialValue(v, "unlockAt", () => "");
  // an account without an authenticator yet (access.mfa_enrolled false) starts on the set-up
  onLifecycle(v, "start", () => { if (Edge.auth?.access?.mfa_enrolled === false || authFlow.mfaEnrolled === false || authFlow.enrolling) startEnrol();
    return () => { authFlow.enrolling = false; }; }, []);
  // a new authenticator beside a confirmed one needs a code entered in the last minutes (MFA_REQUIRED with
  // details.recent_s): the code form below takes it, and its success starts the set-up again here (resumeEnrol)
  const resumeEnrol = initialValue(v, "resumeEnrol", () => false);
  async function startEnrol() { if (busy) return; updateValue(v, "busy", true); updateValue(v, "error", "");
    try { const a = await Edge.mfaEnroll(); authFlow.enrolling = true; updateValue(v, "resumeEnrol", false); updateValue(v, "enrol", {uri:a.otpauth_uri || "", secret:a.secret || "", codes:Array.isArray(a.recovery_codes) ? a.recovery_codes : []}); updateValue(v, "recovery", false); }
    catch (e) { if (e.info?.code === "MFA_REQUIRED" && typeof e.info.details?.recent_s === "number") { updateValue(v, "resumeEnrol", true); authFlow.enrolling = true; }
      updateValue(v, "error", authText(e)); } finally { updateValue(v, "busy", false); } }
  const submit = async e => { e.preventDefault(); if (busy) return;
    if (!recovery && !/^\d{6}$/.test(code)) { updateValue(v, "error", L.check.code); return; }
    updateValue(v, "busy", true); updateValue(v, "error", "");
    try { await Edge.mfaVerify(recovery ? {recovery_code:code.trim()} : {code}); updateValue(v, "enrol", null); authFlow.mfaEnrolled = null;
      if (resumeEnrol && !enrol) { updateValue(v, "code", ""); updateValue(v, "busy", false); await startEnrol(); return; }
      authFlow.enrolling = false; go(landing()); }
    catch (e) {
      // MFA_LOCKED: details.locked names the locked way ("code" or "recovery_code"); details.use the way still open as the
      // server found it: "recovery_code" (the codes locked) or "code" (the recovery codes locked, the authenticator open,
      // ACC-2), none when both are locked (ERRORS M519: the page no longer guesses the other way from the locked one)
      if (e.info?.code === "MFA_LOCKED") { const d = e.info.details || {}, useRecovery = d.use === "recovery_code", useCode = d.use === "code";
        const at = typeof d.unlock_at === "string" && !Number.isNaN(Date.parse(d.unlock_at)) ? new Date(d.unlock_at).toLocaleString([], {dateStyle:"medium", timeStyle:"short"}) : "";
        updateValue(v, "locked", useRecovery ? "code" : useCode ? "recovery" : "all"); updateValue(v, "unlockAt", at); updateValue(v, "code", "");
        if (useRecovery) updateValue(v, "recovery", true);
        if (useCode) updateValue(v, "recovery", false);
        updateValue(v, "error", e.info.message || (useRecovery ? M.lockedCode : useCode ? M.lockedRecovery : M.lockedAll)); }
      else updateValue(v, "error", authText(e)); } finally { updateValue(v, "busy", false); } };
  const secret = enrol?.secret || (enrol?.uri ? (new URLSearchParams(enrol.uri.split("?")[1] || "").get("secret") || "") : "");
  const needsSave = Boolean(enrol && enrol.codes.length && !saved);
  return element(AuthShell, {go, title:enrol ? M.enrolTitle : M.title, lead:enrol ? M.enrolLead : M.lead},
    enrol && element("div", {className:"auth-enrol"},
      enrol.uri && element(QrCode, {text:enrol.uri}),
      secret && element("p", {className:"auth-note"}, M.secret, ": ", element("code", {className:"auth-secret"}, secret)),
      enrol.codes.length > 0 && element("div", {className:"auth-codes"},
        element("strong", null, M.codesTitle), element("p", null, M.codesLead),
        element("ol", null, enrol.codes.map((c, i) => element("li", {key:i}, element("code", null, c)))),
        element("label", {className:"auth-check"}, element("input", {type:"checkbox", checked:saved, onChange:e => updateValue(v, "saved", e.target.checked)}), M.saved))),
    element("form", {onSubmit:submit},
      element(AuthField, {label:recovery ? M.recovery : M.code, support:recovery ? null : M.codeHint}, recovery
        ? element("input", {id:"auth-recovery-code", value:code, required:true, disabled:busy, autoComplete:"one-time-code", autoCapitalize:"none", onChange:e => updateValue(v, "code", e.target.value)})
        : element(CodeInput, {value:code, disabled:busy, onChange:next => updateValue(v, "code", next)})),
      error && element("p", {className:"auth-error", role:"alert"}, error),
      locked && unlockAt && element("p", {className:"auth-note", role:"status"}, M.unlockAt, " ", unlockAt, "."),
      element(Button, {kind:"primary", type:"submit", disabled:busy || needsSave || locked === "all"}, busy ? M.busy : M.submit)),
    !enrol && !locked && element("p", {className:"auth-switch"},
      element("button", {type:"button", className:"text-link", onClick:() => { updateValue(v, "recovery", !recovery); updateValue(v, "code", ""); }}, recovery ? M.useCode : M.useRecovery)),
    !enrol && element("p", {className:"auth-switch"}, element("button", {type:"button", className:"text-link", disabled:busy, onClick:startEnrol}, busy ? M.busySetup : M.setup)),
    element("p", {className:"auth-switch"}, authLink(go, "/forgot", L.login.forgot)),
    element("p", {className:"auth-switch"}, authLink(go, "/login", L.verify.back)));
}
function AuthField({ label, error, support, children }) {
    const id = label.toLowerCase().replaceAll(" ", "-");
    return element("div", { className: "auth-field" },
        element("label", { htmlFor: `auth-${id}` }, label),
        children,
        error ? element("small", { className: "field-error", id: `${id}-error` }, error) : support ? element("small", { id: `${id}-support` }, support) : null);
}
function AuthFooter() {
    return element("footer", { className: "auth-footer" },
        element("span", null, "Understand the market, understand your edge."),
        // the user, 2026-11-20 (EXEC option A): a link only once its text exists (EDGE_PRIVACY_URL, EDGE_TERMS_URL)
        element("div", null,
            Edge.legal?.().privacy && element("a", { href: Edge.legal().privacy }, EdgeLabels.auth.legal.privacy),
            Edge.legal?.().terms && element("a", { href: Edge.legal().terms }, EdgeLabels.auth.legal.terms)));
}
function loadConversations(){return [];}
// EXEC-ASK-BRANCH (user 2026-10-24): #/monitor?c=<conversation> opens that conversation (a Branch opens in a new tab);
// &view=side shows only the conversation and its message box (the side chat's frame)
// EXEC-CHAT-URL: a conversation's address is /c/<id> (the side chat's frame adds ?view=side); ?c=<id> of the first
// links still opens
function edgeLink(){const r=routeLocation(),q=new URLSearchParams(r.search),c=(r.pathname.match(/^\/c\/([^/]+)$/)||[])[1]||q.get("c");
  return {conversationId:/^conv_[0-9a-f]{32}$/.test(c||"")?c:null,side:q.get("view")==="side"};}
function conversationRoute(id,side=false){return "/c/"+encodeURIComponent(id)+(side?"?view=side":"");}
function conversationUrl(id,side=false){return staticUrl(conversationRoute(id,side));}
const latestRun = (conversation) => conversation?.runs.at(-1);
const formatDuration = (milliseconds) => milliseconds === undefined ? "—" : milliseconds < 1000 ? `${milliseconds}ms` : `${(milliseconds / 1000).toFixed(2)}s`;
const relativeTime = (iso) => { if (!iso)
    return "Not completed"; const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000)); if (seconds < 60)
    return "Updated just now"; if (seconds < 3600)
    return `Updated ${Math.floor(seconds / 60)}m ago`; if (seconds < 86400)
    return `Updated ${Math.floor(seconds / 3600)}h ago`; return `Updated ${Math.floor(seconds / 86400)}d ago`; };
const conversationGroup = (iso) => { const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000); return days < 1 ? "Today" : days < 2 ? "Yesterday" : days < 7 ? "Previous 7 Days" : "Older"; };
// EXEC-TERMINAL-API T3/T5: the terminal is its own page (/terminal-app/, built from apps/edge-bff/terminal) shown in a
// same-origin frame under the EDGE top bar, so its stylesheet and EDGE's never mix; its data comes through
// /api/terminal/... with this EDGE session.
function TerminalPage({ go, guest = false }) {
    return element(Shell, { route: "terminal", go: go, chart: true, guest },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/terminal-app/?in=edge", title: EdgeLabels.terminal.frameTitle })));
}
// EDGE backtest (CONTRACT.md section 10): the backtest is its own page (/backtest-app/, built from apps/edge-bff/backtest)
// in the same kind of same-origin frame as the terminal; its jobs and data go through /api/v1/backtests and
// /api/terminal/... with this EDGE session.
function BacktestPage({ go }) {
    return element(Shell, { route: "backtest", go: go, chart: true },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/backtest-app/", title: EdgeLabels.backtest.frameTitle })));
}
// EXEC-SCREENER (report FRONTEND INTEGRATION 9.1, 9.7): the screener is its own page (/screener-app/, built from
// apps/edge-bff/screener) in the same kind of same-origin frame; its screens, saved items and watchlist go through
// /api/v1/screener with this EDGE session.
function ScreenerPage({ go }) {
    return element(Shell, { route: "screener", go: go, chart: true },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/screener-app/", title: EdgeLabels.screener.frameTitle })));
}
// EXEC-RADAR R7 (user go 2026-11-14): the Radar is its own page (/radar-app/, built from apps/edge-bff/radar) in the same
// kind of same-origin frame; its data comes from /api/v1/radar with this EDGE session (the owner's only).
function RadarPage({ go }) {
    return element(Shell, { route: "radar", go: go, chart: true },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/radar-app/", title: EdgeLabels.radar.frameTitle })));
}
// EXEC-OVERVIEW O4 (user go 2026-11-15): the Market Overview is its own page (/overview-app/, built from
// apps/edge-bff/overview) in the same kind of same-origin frame; its data comes from /api/v1/overview (the owner's only).
function OverviewPage({ go }) {
    return element(Shell, { route: "overview", go: go, chart: true },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/overview-app/", title: EdgeLabels.overview.frameTitle })));
}
// EXEC-WATCHLIST L5 (user go 2026-11-16): the Watchlist is its own page (/watchlist-app/, built from apps/edge-bff/watchlist)
// in the same kind of same-origin frame; its lists come from /api/v1/watchlist/lists and its figures from the publisher's
// watchlist-stocks file (/api/v1/watchlist, the owner's only).
function WatchlistPage({ go }) {
    return element(Shell, { route: "watchlist", go: go, chart: true },
        element("main", { className: "terminal-page" },
            element("iframe", { className: "terminal-frame", src: "/watchlist-app/", title: EdgeLabels.watchlist.frameTitle })));
}
// EXEC-MU-ACCOUNTS Phase 4 (the user, 2026-11-22: "1A, 2B, 3A"): the admin page of the beta is its own page
// (/admin-app/, built from apps/edge-bff/admin, whose files edge-bff serves to the admin only) in the same kind of
// same-origin frame; the ticket of this address (/admin?ticket=<id>, the Telegram summary's link) opens first. Every
// word and data path of the page is in its own build, none in this shell.
const adminTicket = () => (/(?:^\?|&)ticket=(\d{1,15})(?:&|$)/.exec(routeLocation().search) || [])[1] || "";
const adminOpen = () => Edge.offers("admin") && Edge.can("admin.access");
function AdminPage({ go }) {
    const ticket = adminTicket();
    return element(Shell, { route: "admin", go: go, chart: true },
        element("main", { className: "terminal-page" },
            adminOpen() ? element("iframe", { className: "terminal-frame", src: `/admin-app/${ticket ? `?ticket=${ticket}` : ""}`, title: EdgeLabels.admin.frameTitle })
                : element("div", { className: "admin-closed", role: "status" }, EdgeLabels.admin.closed)));
}
function Monitor({ go }) {
    const viewRecord = currentView;
    const initialContext = undefined;
    const demoDataAt = cachedValue(viewRecord, "demoDataAt", () => new Date().toISOString(), []);
    const context = initialValue(viewRecord, "context", () => ((() => { const seed = initialContext; return typeof seed === "function" ? seed() : seed; })())), setContext = next => updateValue(viewRecord, "context", next);
    const items = initialValue(viewRecord, "items", () => ((() => { const seed = loadConversations; return typeof seed === "function" ? seed() : seed; })())), setItems = next => updateValue(viewRecord, "items", next);
    const selectedId = initialValue(viewRecord, "selectedId", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setSelectedId = next => updateValue(viewRecord, "selectedId", next);
    const autoOpenRunId = initialValue(viewRecord, "autoOpenRunId", () => null), setAutoOpenRunId = next => updateValue(viewRecord, "autoOpenRunId", next);
    const selectedRunId = initialValue(viewRecord, "selectedRunId", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setSelectedRunId = next => updateValue(viewRecord, "selectedRunId", next);
    const prompt = initialValue(viewRecord, "prompt", () => ((() => { const seed = ""; return typeof seed === "function" ? seed() : seed; })())), setPrompt = next => updateValue(viewRecord, "prompt", next);
    // EXEC-TYPING: a keystroke stores the text; only a change between empty and non-empty (the box style and the
    // Submit button) redraws the page, so typing stays fast in a long conversation
    const typePrompt = next => { const previous = viewRecord.state.prompt || ""; if (Boolean(previous.trim()) !== Boolean(next.trim())) setPrompt(next); else viewRecord.state.prompt = next; };
    const query = initialValue(viewRecord, "query", () => ((() => { const seed = ""; return typeof seed === "function" ? seed() : seed; })())), setQuery = next => updateValue(viewRecord, "query", next);
    const searchQuery = initialValue(viewRecord, "searchQuery", () => ((() => { const seed = ""; return typeof seed === "function" ? seed() : seed; })())), setSearchQuery = next => updateValue(viewRecord, "searchQuery", next);
    const listFilter = initialValue(viewRecord, "listFilter", () => ((() => { const seed = "All"; return typeof seed === "function" ? seed() : seed; })())), setListFilter = next => updateValue(viewRecord, "listFilter", next);
    const detailsTab = initialValue(viewRecord, "detailsTab", () => ((() => { const seed = "Flow"; return typeof seed === "function" ? seed() : seed; })())), setDetailsTab = next => updateValue(viewRecord, "detailsTab", next);
    const detailsOpen = initialValue(viewRecord, "detailsOpen", () => ((() => { const seed = () => sessionStorage.getItem("edge-details-open") !== "false"; return typeof seed === "function" ? seed() : seed; })())), setDetailsOpen = next => updateValue(viewRecord, "detailsOpen", next);
    const narrow = initialValue(viewRecord,"narrow",()=>matchMedia("(max-width:1050px)").matches), setNarrow=next=>updateValue(viewRecord,"narrow",next);
    const historyOpen=initialValue(viewRecord,"historyOpen",()=>false),setHistoryOpen=next=>updateValue(viewRecord,"historyOpen",next);
    const mobileDetailsOpen=initialValue(viewRecord,"mobileDetailsOpen",()=>false),setMobileDetailsOpen=next=>updateValue(viewRecord,"mobileDetailsOpen",next);
    onLifecycle(viewRecord,"responsive",()=>{const media=matchMedia("(max-width:1050px)");const change=()=>setNarrow(media.matches);media.addEventListener("change",change);return()=>media.removeEventListener("change",change);},[]);
    onLifecycle(viewRecord,"panel-focus",()=>{
      if(!narrow||(!historyOpen&&!mobileDetailsOpen))return;
      const previous=document.activeElement,panel=document.getElementById(historyOpen?"edge-conversations":"edge-details");
      const focusable=()=>[...panel.querySelectorAll('button:not([disabled]),input,[tabindex="0"],summary')].filter(n=>n.getClientRects().length);
      requestAnimationFrame(()=>focusable()[0]?.focus());
      const key=e=>{if(e.key==="Escape"){e.preventDefault();setHistoryOpen(false);setMobileDetailsOpen(false);}else if(e.key==="Tab"){const nodes=focusable(),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}};
      document.addEventListener("keydown",key);
      return()=>{document.removeEventListener("keydown",key);requestAnimationFrame(()=>previous?.isConnected&&previous.focus());};
    },[narrow,historyOpen,mobileDetailsOpen]);
    // EXEC-DETAILS (user 2026-10-12): the Pinned responses / Response History split can be dragged, and each part
    // collapses; the choice is kept in this browser only
    const stored = (key, fallback) => { try { const value = localStorage.getItem(key); return value === null ? fallback : JSON.parse(value); } catch { return fallback; } };
    const keep = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
    const pinsHeight = initialValue(viewRecord, "pinsHeight", () => stored("edge-pins-height", null)), setPinsHeight = next => updateValue(viewRecord, "pinsHeight", next);
    const pinsOpen = initialValue(viewRecord, "pinsOpen", () => stored("edge-pins-open", true) !== false), flowOpen = initialValue(viewRecord, "flowOpen", () => stored("edge-flow-open", true) !== false);
    const togglePins = () => { keep("edge-pins-open", !pinsOpen); updateValue(viewRecord, "pinsOpen", !pinsOpen); };
    const toggleFlow = () => { keep("edge-flow-open", !flowOpen); updateValue(viewRecord, "flowOpen", !flowOpen); };
    const detailsWidth = initialValue(viewRecord,"detailsWidth",()=>Math.min(560,Math.max(280,Number(localStorage.getItem("edge-details-width"))||340))), setDetailsWidth=next=>updateValue(viewRecord,"detailsWidth",next);
    const collapsed = initialValue(viewRecord, "collapsed", () => ((() => { const seed = () => localStorage.getItem("edge-monitor-collapsed") === "true"; return typeof seed === "function" ? seed() : seed; })())), setCollapsed = next => updateValue(viewRecord, "collapsed", next);
    const sidebarWidth = initialValue(viewRecord, "sidebarWidth", () => ((() => { const seed = () => Math.min(360, Math.max(180, Number(localStorage.getItem("edge-monitor-width")) || 272)); return typeof seed === "function" ? seed() : seed; })())), setSidebarWidth = next => updateValue(viewRecord, "sidebarWidth", next);
    const expandedRuns = initialValue(viewRecord, "expandedRuns", () => ((() => { const seed = []; return typeof seed === "function" ? seed() : seed; })())), setExpandedRuns = next => updateValue(viewRecord, "expandedRuns", next);
    const shareOpen = initialValue(viewRecord, "shareOpen", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setShareOpen = next => updateValue(viewRecord, "shareOpen", next);
    const attachments = initialValue(viewRecord, "attachments", () => ((() => { const seed = []; return typeof seed === "function" ? seed() : seed; })())), setAttachments = next => updateValue(viewRecord, "attachments", next);
    const sourceDetail = initialValue(viewRecord, "sourceDetail", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setSourceDetail = next => updateValue(viewRecord, "sourceDetail", next);
    const activeSection = initialValue(viewRecord, "activeSection", () => ((() => { const seed = "conditions"; return typeof seed === "function" ? seed() : seed; })())), setActiveSection = next => updateValue(viewRecord, "activeSection", next);
    const autoFollow = initialValue(viewRecord, "autoFollow", () => ((() => { const seed = true; return typeof seed === "function" ? seed() : seed; })())), setAutoFollow = next => updateValue(viewRecord, "autoFollow", next);
    const loadingConversation = initialValue(viewRecord, "loadingConversation", () => ((() => { const seed = false; return typeof seed === "function" ? seed() : seed; })())), setLoadingConversation = next => updateValue(viewRecord, "loadingConversation", next);
    const tableMenu = initialValue(viewRecord, "tableMenu", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setTableMenu = next => updateValue(viewRecord, "tableMenu", next);
    const expandedTable = initialValue(viewRecord, "expandedTable", () => ((() => { const seed = null; return typeof seed === "function" ? seed() : seed; })())), setExpandedTable = next => updateValue(viewRecord, "expandedTable", next);
    const composerHeight=initialValue(viewRecord,"composerHeight",()=>null),setComposerHeight=next=>updateValue(viewRecord,"composerHeight",next);
    const composerRef = (viewRecord.refs.composerRef ??= { current: null });
    const composerPanelRef = (viewRecord.refs.composerPanelRef ??= {current:null});
    onLifecycle(viewRecord,"composer-size",()=>{
      const panel=composerPanelRef.current,workspace=panel?.closest(".research-workspace");
      if(!panel||!workspace)return;
      // EXEC-UI-1015 U5: the phone model menu lines up with the composer, so its place and width are shared too
      const update=()=>{const box=panel.getBoundingClientRect(),scroll=workspace.querySelector(".research-scroll"),field=composerRef.current;
        workspace.style.setProperty("--edge-conversation-scrollbar",((scroll?.offsetWidth??0)-(scroll?.clientWidth??0))+"px");
        if(field)workspace.style.setProperty("--edge-composer-text-max",Math.max(parseFloat(getComputedStyle(field).minHeight),workspace.clientHeight-(box.height-field.getBoundingClientRect().height)-110)+"px");
        workspace.style.setProperty("--edge-composer-height",box.height+"px");
        workspace.style.setProperty("--edge-composer-left",box.left+"px");workspace.style.setProperty("--edge-composer-width",box.width+"px");};
      const observer=new ResizeObserver(update);observer.observe(panel);observer.observe(workspace);const scroll=workspace.querySelector(".research-scroll");if(scroll)observer.observe(scroll);update();
      addEventListener("resize",update);
      return()=>{observer.disconnect();removeEventListener("resize",update);};
    },[]);
    const fileInput = (viewRecord.refs.fileInput ??= { current: null });
    const shareRef = (viewRecord.refs.shareRef ??= { current: null });
    const scrollRef = (viewRecord.refs.scrollRef ??= { current: null });
    const historyScrollRef = (viewRecord.refs.historyScrollRef ??= { current: null });
    const abortRef = (viewRecord.refs.abortRef ??= { current: null });
    const selected = items.find(item => item.id === selectedId);
    const run = selected?.runs.find(item => item.id === selectedRunId) ?? latestRun(selected);
    const runNumber = run && selected ? selected.runs.findIndex(item => item.id === run.id) + 1 : 0;
    // MONITOR-REVAMP (user 2026-10-30): the sidebar's Share shares the conversation's latest answer
    const shareRun = selected?.runs.findLast(item => item.status === "completed" && !item.stopped && item.raw);
    const executionRun = items.flatMap(c=>c.runs).findLast(item => ["submitted", "running"].includes(item.status));
    const active = Boolean(executionRun);

    onLifecycle(viewRecord, "effect1", () => { const timer = window.setTimeout(() => setSearchQuery(query), 180); return () => window.clearTimeout(timer); }, [query]);
    onLifecycle(viewRecord, "effect2", () => { sessionStorage.setItem("edge-details-open", String(detailsOpen)); }, [detailsOpen]);
    // EXEC 2026-10-20 (user screenshot 5): a running answer's progress grows without changing the conversation; while
    // the page follows the latest message, every change in the conversation keeps it at the bottom
    onLifecycle(viewRecord, "follow-growth", () => {
        const scroller = scrollRef.current; if (!scroller) return;
        let frame = 0;
        const follow = () => { if (frame || !viewRecord.state.autoFollow) return; frame = requestAnimationFrame(() => { frame = 0;
            if (viewRecord.state.autoFollow && scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight > 1) scroller.scrollTop = scroller.scrollHeight; }); };
        const watch = new MutationObserver(follow); watch.observe(scroller, {childList:true, subtree:true, characterData:true});
        return () => { watch.disconnect(); cancelAnimationFrame(frame); };
    }, [scrollRef.current]);
    onLifecycle(viewRecord, "effect3", () => { if (autoFollow)
        requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })); }, [items, selectedId, autoFollow]);
    onLifecycle(viewRecord, "reveal-new-history", () => {
        if (!autoOpenRunId || !detailsOpen) return;
        const frame = requestAnimationFrame(() => {
            const container = historyScrollRef.current, item = document.getElementById(`edge-history-${autoOpenRunId}`);
            if (!container || !item) return;
            // History is newest first; reveal the new entry below its fixed header.
            container.scrollTo({top:0,behavior:"auto"});
        });
        return () => cancelAnimationFrame(frame);
    }, [autoOpenRunId, detailsOpen]);
    const filtered = items.filter(item => (listFilter === "All" || item.bookmarked) && `${item.title} ${item.messages.filter(message => message.role === "user").map(message => message.content).join(" ")}`.toLowerCase().includes(searchQuery.toLowerCase()));
    const updateConversation = (id, update) => setItems(current => current.map(item => item.id === id ? update(item) : item));
    const submitting = initialValue(viewRecord,"submitting",()=>false), setSubmitting=next=>updateValue(viewRecord,"submitting",next);
    const apiError=initialValue(viewRecord,"apiError",()=>""), setApiError=next=>updateValue(viewRecord,"apiError",next);
    // The stop button (EXEC-X 2026-10-09): holds the id of the run being stopped; the run's own snapshot ends it.
    const stoppingId=initialValue(viewRecord,"stoppingId",()=>null), setStoppingId=next=>updateValue(viewRecord,"stoppingId",next);
    const followRef=(viewRecord.refs.followRef ??= {current:null});
    const submissionRef=(viewRecord.refs.submissionRef ??= {current:null});
    // E11 (EXEC-1018B, M178): what each sent message carried (its text and attachments), so a run that fails or is
    // stopped gives them back to the composer instead of losing them
    const sentRef=(viewRecord.refs.sentRef ??= {current:{}});
    const giveBack=requestId=>{const sent=sentRef.current[requestId];if(!sent)return;delete sentRef.current[requestId];
      if(sent.attachments.length)setAttached(current=>Array.isArray(current)&&current.length?current:sent.attachments);
      setPrompt(current=>current&&current.trim()?current:sent.question);};
    const pendingReply=initialValue(viewRecord,"pendingReply",()=>null),setPendingReply=next=>updateValue(viewRecord,"pendingReply",next);
    // EXEC-IMPL-1016 Fase 4.2 (EDGE-CTX A), EXEC-IMPL-1017 Fase 3: what the user attached to the next question, from a
    // selection anywhere in an answer (at most 5; each chip can be removed)
    const attachedValue=initialValue(viewRecord,"attached",()=>[]),attached=Array.isArray(attachedValue)?attachedValue:[];
    const setAttached=next=>updateValue(viewRecord,"attached",next);
    // EXEC-UI-1024 2a: mark the attached passages after each change of the attachments or of the shown answers
    onLifecycle(viewRecord,"highlightAttached",()=>{const frame=requestAnimationFrame(()=>EdgeHighlight.show(attached));return()=>cancelAnimationFrame(frame);},[attached,selectedId,items]);
    const addAttached=item=>{if(!item)return;if(attached.length>=5){setInputHint(edgeUi().attachLimit);return;}
      setAttached([...attached,item]);focusComposer();};
    viewRecord.refs.attachHandler=addAttached;
    if(!viewRecord.refs.attachInstalled){viewRecord.refs.attachInstalled=true;
      window.addEventListener("edge-attach",event=>viewRecord.refs.attachHandler?.(event.detail));}
    const inputHint=initialValue(viewRecord,"inputHint",()=>null),setInputHint=next=>updateValue(viewRecord,"inputHint",next);
    // EXEC-ASK-BRANCH: a conversation not in the list (opened by link, a side chat) joins it when selected
    // ERRORS M510: the page itself opening the conversation of its address (/c/<id>, at load) is not the user choosing
    // it, so it leaves the panels as the user has them; on a slow phone the user may open the history before the load
    // ends, and the load closed it again. A choice from the history, Back/Forward or a branch link still closes it.
    const selectConversation = async (id,{byPage=false}={}) => {if(!byPage)setHistoryOpen(false);setLoadingConversation(true);setApiError("");setSelectedId(id);setSelectedRunId(null);setPendingReply(null);try{const loaded=await Edge.messages(id);setItems(current=>current.some(x=>x.id===id)?current.map(x=>x.id===id?loaded:x):[loaded,...current]);}catch(e){setApiError(e.message);}finally{setLoadingConversation(false);}};
    // EXEC-ASK-BRANCH (user 2026-10-24: Branch "satu tab baru terpisah sama seperti feature chat GPT"; a side chat "untuk
    // nanya jawaban yang dikasih oleh AI"). The tab is opened before the request so no pop-up blocker stops it.
    const link=cachedValue(viewRecord,"edgeLink",()=>edgeLink(),[]);
    const sidePanel=initialValue(viewRecord,"sidePanel",()=>null),setSidePanel=next=>updateValue(viewRecord,"sidePanel",next);
    const carryTitle=(template,run)=>template.replace("{title}",Edge.shortTitle(run.result?.title||run.question,60));
    const branchRun=async run=>{const tab=window.open("","_blank");
      try{const made=await Edge.branch(run.id,"BRANCH",carryTitle(edgeUi().branchTitle,run));const url=conversationUrl(made.conversation_id);
        setItems(current=>[{id:made.conversation_id,title:made.title,bookmarked:false,createdAt:made.created_at,updatedAt:made.updated_at,messages:[],runs:[]},...current.filter(x=>x.id!==made.conversation_id)]);
        if(tab){tab.opener=null;tab.location.href=url;}else selectConversation(made.conversation_id);}
      catch(e){tab?.close();setApiError(e.message);}};
    const askRun=async (run,attach=null)=>{try{const made=await Edge.branch(run.id,"SIDE",carryTitle(edgeUi().askTitle,run));
        if(attach){try{sessionStorage.setItem("edge-side-attach:"+made.conversation_id,JSON.stringify([attach]));}catch{/* the passage is then not attached */}}
        setSidePanel({conversationId:made.conversation_id,runId:run.id,key:Date.now()});}catch(e){setApiError(e.message);}};
    // closing the side chat refreshes the answers' side-chat links (how many questions each holds)
    const closeSide=async()=>{setSidePanel(null);const id=selectedId;if(!id?.startsWith("conv_"))return;try{const loaded=await Edge.messages(id);setItems(current=>current.map(x=>x.id===id?{...x,sideChats:loaded.sideChats}:x));}catch{/* the links refresh on the next load */}};
    // a branch shows the turns it continues; a side chat (its frame) only the answer it asks about. The divider names
    // where the continued turns come from and heads the conversation
    // EXEC-UI-1025 (user 2026-10-24: a side chat opens empty, "seperti how Claude works"): the side chat shows only its
    // own questions; the answer it is about stays its context (Orc reads it) and is named above them
    const shownMessages=conversation=>{const asked=conversation.messages.filter(m=>m.role==="user");
      return link.side?asked.filter(m=>!m.inherited):asked;};
    const branchDivider=conversation=>{const from=conversation.messages.find(m=>m.inherited)?.inherited;if(!from)return null;
      const ui=edgeUi(),asked=conversation.messages.filter(m=>m.inherited).at(-1);
      const text=conversation.kind==="SIDE"?ui.sideFrom.replace("{title}",Edge.shortTitle(asked?.content||from.title||"",90)):ui.branchedFrom.replace("{title}",from.title||"");
      return element("div",{key:"edge-branch-divider",className:"edge-branch-divider",role:"separator"},
        link.side?element("span",null,text):element(fragment,null,element(Icon,{name:"fork"}),element("span",null,element("button",{type:"button",onClick:()=>selectConversation(from.conversationId)},text),conversation.kind==="SIDE"?null:ui.branchedNote)));};
    const withDivider=(conversation,nodes)=>{const divider=branchDivider(conversation);if(!divider)return nodes;
      if(link.side&&!nodes.length)return [divider,element("p",{key:"edge-side-empty",className:"edge-side-empty"},edgeUi().sideEmpty)];
      // MONITOR-REVAMP (user 2026-10-30, AI_revamp.html lineage): the bar heads the branch, above the turns it continues
      return [divider,...nodes];};
    viewRecord.refs.askHandler=detail=>{const run=items.find(x=>x.id===selectedId)?.runs.find(r=>r.id===detail?.request_id);if(run)askRun(run,detail);};
    if(!viewRecord.refs.askInstalled){viewRecord.refs.askInstalled=true;
      window.addEventListener("edge-ask",event=>viewRecord.refs.askHandler?.(event.detail));}
    onLifecycle(viewRecord,"sideView",()=>{document.documentElement.classList.toggle("edge-side-view",link.side);
      if(link.side&&link.conversationId){try{const key="edge-side-attach:"+link.conversationId,held=JSON.parse(sessionStorage.getItem(key)||"[]");sessionStorage.removeItem(key);if(Array.isArray(held)&&held.length)setAttached(held.slice(0,5));}catch{/* nothing attached */}}},[]);
    // EXEC-DELETE (user 2026-10-12): the trash button asks first, then hides the conversation from this list only
    const hideTarget = initialValue(viewRecord, "hideTarget", () => null), setHideTarget = next => updateValue(viewRecord, "hideTarget", next);
    const hideConversation=async item=>{try{await Edge.hideConversation(item.id);setHideTarget(null);setItems(current=>current.filter(x=>x.id!==item.id));if(selectedId===item.id)newConversation();}catch(e){setHideTarget(null);setApiError(e.message);}};
    const toggleBookmark=async (id=selectedId)=>{const item=items.find(x=>x.id===id);if(!item || id.startsWith("draft:"))return;try{const ui=await Edge.bookmark(id,!item.bookmarked);updateConversation(id,x=>({...x,bookmarked:ui.bookmarked}));}catch(e){setApiError(e.message);}};
    const newConversation=()=>{setHistoryOpen(false);setSelectedId(null);setSelectedRunId(null);setPrompt("");setPendingReply(null);setApiError("");requestAnimationFrame(()=>composerRef.current?.focus());};
    // EXEC-CHAT-URL (user 2026-10-24: "B saja ya"): the address follows the conversation shown: /c/<id> for a
    // conversation (switching adds a history entry, so Back and Forward move between conversations), /monitor for a new
    // one; an older #/monitor?c=<id> link is rewritten. The side chat's frame never writes the address.
    onLifecycle(viewRecord,"chatUrl",()=>{const left=viewRecord.refs.urlShown;viewRecord.refs.urlShown=selectedId;
      if(link.side||selectedId?.startsWith("draft:"))return;
      const shown=edgeLink().conversationId,legacy=pathRoutes&&location.hash.startsWith("#/");
      if(selectedId){if(shown!==selectedId||legacy)routeHistory[shown&&!legacy?"pushState":"replaceState"]({},"",conversationRoute(selectedId));}
      else if(shown&&left?.startsWith("conv_"))routeHistory.pushState({},"","/monitor");},[selectedId]);
    viewRecord.refs.popHandler=()=>{if(link.side)return;const shown=edgeLink().conversationId;
      if(shown&&shown!==selectedId)selectConversation(shown);else if(!shown&&selectedId?.startsWith("conv_"))newConversation();};
    if(!viewRecord.refs.popInstalled){viewRecord.refs.popInstalled=true;
      window.addEventListener("popstate",()=>viewRecord.refs.popHandler?.());}
    const updateRun=(conversationId,runId,update)=>updateConversation(conversationId,x=>({...x,runs:x.runs.map(r=>r.id===runId?update(r):r)}));
    const togglePin=async (target,pinned=!target.pinned)=>{try{await Edge.pin(target.id,pinned);setItems(current=>current.map(c=>({...c,runs:c.runs.map(r=>r.id===target.id?{...r,pinned}:r)})));}catch(e){setApiError(e.message);}};
    const followRun=(initialId,requestId)=>{
      let conversationId=initialId;
      followRef.current?.();  // M153: one watcher at a time
      followRef.current=Edge.follow(requestId,snapshot=>{
        if(snapshot.conversation_id && conversationId!==snapshot.conversation_id){const old=conversationId;conversationId=snapshot.conversation_id;setItems(current=>current.map(c=>c.id===old?{...c,id:conversationId}:c));setSelectedId(current=>current===old?conversationId:current);}
        updateRun(conversationId,requestId,r=>Edge.stateRun(snapshot,r));
        // E11: whether the run answered is read from the saved run as the conversation shows it (the queue's FINISHED
        // only says delivery ended; Orc's own status says whether there is an answer)
        const settle=status=>{if(status==="completed")delete sentRef.current[requestId];else giveBack(requestId);};
        if(Edge.terminal(snapshot) && snapshot.conversation_id){Edge.messages(snapshot.conversation_id).then(loaded=>{setItems(current=>current.map(c=>c.id===loaded.id?loaded:c));
          settle(loaded.runs.find(r=>r.id===requestId)?.status ?? Edge.stateRun(snapshot,{}).status);}).catch(e=>{settle(Edge.stateRun(snapshot,{}).status);setApiError(e.message);});}
        else if(Edge.terminal(snapshot))settle(Edge.stateRun(snapshot,{}).status);
      },e=>setApiError(e.message));
    };
    onLifecycle(viewRecord,"backend-init",()=>{
      let disposed=false;
      (async()=>{try{const loaded=await Edge.conversations();if(disposed)return;setItems(loaded);const {active:running}=await Edge.api("/runs");if(disposed)return;
        // EXEC-ASK-BRANCH: a linked conversation opens first; a run elsewhere is followed only in its own conversation
        if(link.conversationId){await selectConversation(link.conversationId,{byPage:true});if(!running || running.conversation_id!==link.conversationId)return;}
        if(!running)return;
        let id=running.conversation_id || "draft:"+running.request_id;
        let conversation=running.conversation_id ? await Edge.messages(id) : {id,title:"Request in progress",bookmarked:false,createdAt:running.created_at,updatedAt:running.updated_at,messages:[],runs:[]};
        if(!conversation.runs.some(r=>r.id===running.request_id)){const r={id:running.request_id,question:running.message || "Request in progress",status:"running",mode:"Standard",createdAt:running.created_at,attachments:[],sources:[],steps:[]};conversation.runs.push(r);conversation.messages.push({id:r.id+"-user",role:"user",content:r.question,createdAt:r.createdAt,runId:r.id});}
        if(disposed)return;setItems(current=>[conversation,...current.filter(x=>x.id!==id)]);setSelectedId(id);followRun(id,running.request_id);
      }catch(e){if(!disposed)setApiError(e.message);}})();
      return ()=>{disposed=true;followRef.current?.();};
    },[]);
    // EXEC-Y Fase 1 (S3): afterStop sends while a run is active: that run stops and this message runs next in its
    // conversation. Enter never does this; only the Stop & send button.
    const submit=async (extra={},messageOverride=null,{plain=false,afterStop=false}={})=>{
      const question=(messageOverride || viewRecord.state.prompt || "").trim();if(!question || submitting || (active && !afterStop))return;
      setSubmitting(true);setApiError("");
      const holder=afterStop && executionRun ? items.find(c=>c.runs.some(r=>r.id===executionRun.id)) : null;
      const target=holder ? holder.id : selectedId;
      const existing=target?.startsWith("conv_")?target:null;
      const payload={message:question,...edgeModelChoice(),...(existing?{conversation_id:existing}:{}),...(afterStop?{after_stop:true}:{}),...(attached.length&&!plain?{attachments:EdgeView.attachmentsPayload(attached)}:{}),...extra,...(pendingReply&&!plain?{plan_reply:{...pendingReply,revision_instruction:question.slice(0,2000)}}:{})};
      const fingerprint=JSON.stringify(payload);
      const pending=submissionRef.current?.fingerprint===fingerprint?submissionRef.current:{fingerprint,key:crypto.randomUUID()};submissionRef.current=pending;
      try{const accepted=await Edge.createRun({...payload,submission_key:pending.key});const now=new Date().toISOString(),id=accepted.conversation_id || existing || holder?.id || "draft:"+accepted.request_id;
        if(afterStop && accepted.after_request_id)setStoppingId(accepted.after_request_id);
        sentRef.current[accepted.request_id]={question,attachments:attached.length&&!plain?attached:[]};
        const r={id:accepted.request_id,question,status:"submitted",mode:"Standard",createdAt:now,attachments:[],sources:[],steps:[{id:"queued",label:"Queued",status:"running",detail:"Accepted by server"}]};
        setItems(current=>{const found=current.find(c=>c.id===id);if(found)return current.map(c=>c.id===id && !c.runs.some(x=>x.id===r.id)?{...c,messages:[...c.messages,{id:r.id+"-user",role:"user",content:question,createdAt:now,runId:r.id}],runs:[...c.runs,r]}:c);return [{id,title:Edge.shortTitle(question),bookmarked:false,createdAt:now,updatedAt:now,messages:[{id:r.id+"-user",role:"user",content:question,createdAt:now,runId:r.id}],runs:[r]},...current];});
        setSelectedId(id);setSelectedRunId(r.id);setAutoOpenRunId(r.id);setPrompt("");setPendingReply(null);setInputHint(null);if(!plain)setAttached([]);submissionRef.current=null;followRun(id,r.id);
        // V5 (user 2026-10-14: "ketika saya click enter, chat tidak otomatis ke scroll ke bawah"): the new question is shown
        setAutoFollow(true);requestAnimationFrame(()=>requestAnimationFrame(()=>scrollRef.current?.scrollTo({top:scrollRef.current.scrollHeight,behavior:"auto"})));
      }catch(e){setApiError(e.message);}finally{setSubmitting(false);}
    };
    const stopRun=async ()=>{
      const id=executionRun?.id;if(!id || stoppingId===id)return;
      setStoppingId(id);setApiError("");
      try{await Edge.stopRun(id);}catch(e){setStoppingId(null);setApiError(e.status===409?edgeUi().stopNotYet:e.message);}
    };
    // EXEC-X: every choice the view shows carries one action (EdgeView); this is the only place that sends it.
    // route: a quick choice of an ask-back question; plan: a Research Plan reply; message: the choice's words as the
    // user's message (a pause reads it); input: the user writes first, with the choice as the composer's hint.
    const focusComposer=()=>requestAnimationFrame(()=>composerRef.current?.focus());
    const act=action=>{
      if(action.type==="attach"){addAttached(action.selection);return;}
      if(action.type==="route")return void submit({chosen_option:action.route},action.message,{plain:true});
      if(action.type==="message")return void submit({},action.message,{plain:true});
      if(action.type==="input"){setPendingReply(null);setInputHint(action.hint);setPrompt("");focusComposer();return;}
      if(action.type==="plan"&&action.planId){
        if(action.plan==="REVISE"){setInputHint(null);setPendingReply({plan_id:action.planId,action:"REVISE"});setPrompt("");focusComposer();}
        else void submit({plan_reply:{plan_id:action.planId,action:action.plan}},action.message);
      }
    };
    const planIndex=EdgeView.planIndex(selected?.runs.map(r=>r.raw));
    const retry=target=>{setPendingReply(null);submissionRef.current=null;setPrompt(target.question);requestAnimationFrame(()=>composerRef.current?.focus());};
    // EXEC-M181 (user 2026-10-20: "user perlu tahu bahwa penyedia timeout dan diberikan opsi untuk retry panggilan"): a run
    // whose AI provider stopped sending output is sent again at once with the same model and level, or its question goes
    // back to the message box with the model menu open
    const retryNow=target=>{const execution=target.raw?.execution||{};submissionRef.current=null;
      void submit(execution.model?{model:execution.model,...(execution.reasoning_level?{reasoning_level:execution.reasoning_level}:{})}:{},target.question,{plain:true});};
    const changeModel=target=>{retry(target);requestAnimationFrame(()=>{const trigger=document.querySelector(".composer .edge-model-trigger");if(trigger&&trigger.getAttribute("aria-expanded")!=="true")trigger.click();});};
    const startResize = (event) => { if (collapsed)
        return; event.preventDefault(); const startX = event.clientX, startWidth = sidebarWidth; let nextWidth = startWidth; const move = (pointer) => { nextWidth = Math.min(360, Math.max(180, startWidth + pointer.clientX - startX)); setSidebarWidth(nextWidth); }; const up = () => { localStorage.setItem("edge-monitor-width", String(nextWidth)); document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up); }; document.addEventListener("pointermove", move); document.addEventListener("pointerup", up); };
    const toggleCollapsed = () => setCollapsed(current => { localStorage.setItem("edge-monitor-collapsed", String(!current)); return !current; });
    const onResearchScroll = (event) => { const element = event.currentTarget;
        // A scroll the page started (a jump to a response, a pin, a section) decides auto-follow only where it lands: its
        // first steps are still near the bottom and must not switch auto-follow back on (live 2026-10-15).
        if (element._edgeTarget != null && Math.abs(element.scrollTop - element._edgeTarget) > 2 && performance.now() < element._edgeUntil) return;
        element._edgeTarget = null;
        setAutoFollow(element.scrollHeight - element.scrollTop - element.clientHeight < 90); if (run?.result) {
        const threshold = element.getBoundingClientRect().top + 40, ids = ["conditions", "statistics", "observation", "distribution", "methodology"];
        const visible = ids.findLast(id => { const node = document.getElementById(`${run.id}-${id}`); return node ? node.getBoundingClientRect().top <= threshold : false; });
        if (visible)
            setActiveSection(visible);
    } };
    // V5 pins and EXEC-UI-1015C (user 2026-10-15): one way to bring a response into view, from the pins and from Response
    // History; on a phone the Details sheet covers the chat, so it closes first; a run without an answer shows its exchange
    const scrollResearchTo = top => { const container = scrollRef.current; if (!container) return;
        const target = Math.max(0, Math.min(top, container.scrollHeight - container.clientHeight));
        container._edgeTarget = target; container._edgeUntil = performance.now() + 1500;
        container.scrollTo({ top: target, behavior: "smooth" }); };
    const jumpToRun = id => {setSelectedRunId(id);setAutoFollow(false);
        if(narrow&&mobileDetailsOpen)setMobileDetailsOpen(false);
        requestAnimationFrame(()=>requestAnimationFrame(()=>{const node=document.getElementById(id+"-response")||document.getElementById("edge-exchange-"+id),container=scrollRef.current;if(node&&container){scrollResearchTo(container.scrollTop+node.getBoundingClientRect().top-container.getBoundingClientRect().top-24);node.focus?.({preventScroll:true});}}));};
    const scrollToResearchSection = (sectionId) => { if (!run || !scrollRef.current)
        return; const section = document.getElementById(`${run.id}-${sectionId}`), container = scrollRef.current; if (!section)
        return; const top = section.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 24; setActiveSection(sectionId); scrollResearchTo(top); };
    return element(Shell, { route: "monitor", go: go, mobilePanelOpen:narrow&&(historyOpen||mobileDetailsOpen) },
        element("main", { className: `monitor-layout ${collapsed ? "sidebar-collapsed" : ""} ${detailsOpen ? "" : "details-closed"} ${historyOpen ? "mobile-history-open" : ""} ${mobileDetailsOpen ? "mobile-details-open" : ""}`, style: { gridTemplateColumns: `${collapsed ? 52 : sidebarWidth}px minmax(0,1fr)${detailsOpen ? ` clamp(280px,${detailsWidth}px,max(280px,calc(100vw - ${collapsed ? 52 : sidebarWidth}px - 560px)))` : ""}` } },
            element("aside", { id:"edge-conversations",className: "conversation-panel",role:narrow&&historyOpen?"dialog":undefined,"aria-modal":narrow&&historyOpen?true:undefined,"aria-label":"Conversation history",inert:narrow&&mobileDetailsOpen },
                element("div", { className: "panel-head" },
                    element("div", null,
                        element("span", { className: "eyebrow" }, "Workspace"),
                        element("strong", null, "Edge Research")),
                    element(IconButton, { icon: "menu", onClick: () => narrow ? setHistoryOpen(!historyOpen) : toggleCollapsed(), title: narrow ? historyOpen ? "Close history" : "Open history" : collapsed ? "Expand sidebar" : "Collapse sidebar" }),
                    // MONITOR-REVAMP (AI_revamp.html nav-acts): an open desktop sidebar carries Details and Share beside its menu
                    // button; the rail under "+" keeps them when the sidebar is folded, and on a phone
                    !collapsed && !narrow && element("span", { className: "edge-nav-acts" },
                        element(IconButton, { icon: "panel", selected: detailsOpen, title: detailsOpen ? edgeUi().railHideDetails : edgeUi().railDetails, onClick: () => setDetailsOpen(!detailsOpen) }),
                        selected && (shareRun ? element(ShareAction, { key: shareRun.id, run: shareRun, iconTitle: edgeUi().railShare }) : element(IconButton, { icon: "share", disabled: true, onClick: () => {}, title: edgeUi().railShare })))),
                element(Button, { kind: "primary", icon: "plus", ariaLabel:"New Chat", onClick: newConversation }, collapsed && !(narrow && historyOpen) ? undefined : "New Chat"),
                // EXEC-UI-1015C (desktop): Details, bookmark and share sit in the rail under menu and "+"
                (collapsed || narrow) && element("div", { className: "edge-rail-actions" },
                    element(IconButton, { icon: "sliders", selected: narrow ? mobileDetailsOpen : detailsOpen, title: (narrow ? mobileDetailsOpen : detailsOpen) ? edgeUi().railHideDetails : edgeUi().railDetails, onClick: () => { if (narrow) { setHistoryOpen(false); setDetailsOpen(true); setMobileDetailsOpen(!mobileDetailsOpen); } else setDetailsOpen(!detailsOpen); } }),
                    element(IconButton, { icon: "bookmark", selected: selected?.bookmarked, disabled: !selected || selected.id.startsWith("draft:"), onClick: () => toggleBookmark(), title: edgeUi().railBookmark }),
                    shareRun ? element(ShareAction, { key: shareRun.id, run: shareRun, iconTitle: edgeUi().railShare }) : element(IconButton, { icon: "share", disabled: true, onClick: () => {}, title: edgeUi().railShare })),
                (!collapsed || (narrow && historyOpen)) && element(Search, { placeholder: "Search conversations", value: query, onChange: setQuery, conversation: true }),
                " ",
                (!collapsed || (narrow && historyOpen)) && element("div", { className: "mini-tabs" },
                    element("button", { className: listFilter === "All" ? "active" : "", "aria-pressed": listFilter === "All", onClick: () => setListFilter("All") },
                        "All ",
                        element("b", null, items.length)),
                    element("button", { className: listFilter === "Bookmarked" ? "active" : "", "aria-pressed": listFilter === "Bookmarked", onClick: () => setListFilter("Bookmarked") },
                        "Bookmarked ",
                        element("b", null, items.filter(item => item.bookmarked).length))),
                element("div", { className: "conversation-list" },
                    !filtered.length && element("div", { className: "conversation-empty" }, query ? "No matching conversations" : listFilter === "Bookmarked" ? "No bookmarked conversations" : "No conversations"),
                    element(ConversationHistoryList, { items: filtered, selectedId: selectedId, select: selectConversation, toggleBookmark: toggleBookmark, requestHide: setHideTarget }),
                    hideTarget && element(DialogShell, { title: "Delete conversation?", description: `\u201c${hideTarget.title}\u201d will be removed from your list.`, close: () => setHideTarget(null), className: "confirm-dialog" },
                        element("div", { className: "confirm-dialog-actions" },
                            element(Button, { kind: "secondary", onClick: () => setHideTarget(null) }, "Cancel"),
                            element("button", { type: "button", className: "btn primary danger", "data-dialog-initial-focus": true, onClick: () => hideConversation(hideTarget) }, "Delete")))),
                element("div", { className: "sidebar-foot" },
                    element("span", { className: "status-dot demo" }),
                    element("span", null, "Private workspace"),
                    element("small", null, "Saved history")),
                element("div", { className: "sidebar-resizer", onPointerDown: startResize, onDoubleClick: () => { setSidebarWidth(272); localStorage.setItem("edge-monitor-width", "272"); }, title: "Drag to resize \u00B7 double-click to reset" })),
            element("section", { className: "research-workspace",inert:narrow&&(historyOpen||mobileDetailsOpen) },
                element("div", { className: "workspace-tools" },
                    element("div", null,
                        // M317 (user 2026-10-31): the dot takes the run's colour; on a phone the label is dropped and the
                        // state sits at the right of the Details row (CSS "M317")
                        element("span", { className: `${active ? "pulse" : "live-dot"} edge-tone-${run ? Edge.statusTone(run.status, run.domainStatus, run.paused, run.stopped) : "new"}` }),
                        element("span", { className: "edge-session-label" }, " Research session "),
                        // user 2026-10-31 ("hapus huruf draft"): no "Draft" label before the first question
                        run && element(Pill, null, `Run ${runNumber} · ${Edge.statusLabel(run.status, run.domainStatus, run.paused)}`)),
                    element("div", null,
                        (!detailsOpen || narrow) && element(Button, { kind: "ghost", icon: "sliders", ariaLabel:"Show Details", onClick: () => {setHistoryOpen(false);setDetailsOpen(true);setMobileDetailsOpen(true);} }, "Details"),
                        element("span", { className: "share-anchor conversation-bookmark-anchor" },
                            element(IconButton, { icon: "bookmark", selected: selected?.bookmarked, disabled: !selected || selected.id.startsWith("draft:"), onClick: () => toggleBookmark(), title: "Bookmark" }),
                            element(IconButton, { icon: "share", selected: shareOpen, disabled: true, onClick: () => {}, title: "Public sharing unavailable", buttonRef: shareRef }),
                            shareOpen && selected && run && element(ShareResearchPopover, { trigger: shareRef, close: () => setShareOpen(false), conversation: selected, run: run })))),
                element("div", { className: "research-scroll", ref: scrollRef, onScroll: onResearchScroll }, loadingConversation ? element("div", { className: "research-loading" }, "Loading research\u2026") : !selected ? element("div", { className: "research-empty" },
                    element("span", { className: "block-icon" },
                        element(Icon, { name: "spark" })),
                    element("strong", null, "Start a research session"),
                    element("p", null, "Ask a research question to create a conversation. No thread is created until you submit."),
                    /* user 2026-10-31 ("hapus huruf draft"): the empty page shows no "Draft" label */ null) : withDivider(selected, shownMessages(selected).map(message => { const messageRun = selected.runs.find(item => item.id === message.runId); return element("div", { className: `research-exchange ${messageRun?.id === run?.id ? "selected-run" : ""}${message.inherited ? " inherited" : ""}`, key: message.id, id: messageRun ? `edge-exchange-${messageRun.id}` : undefined },
                    element("div", { className: "user-message" },
                        element("span", { className: "message-label" },
                            "You"),
                        element("p", null, message.content),
                        messageRun?.attachments.length ? element("div", { className: "message-attachments" }, messageRun.attachments.map(file => element("span", { key: file },
                            element(Icon, { name: "attach" }),
                            file))) : null),
                    element("div", {className:"user-message-footer"},element("div", { className:"user-sent-at" }, formatMessageJakarta(message.createdAt)),element(MessageClipboardActions,{getText:()=>message.content,kind:"user"})),
                    messageRun && element(fragment, null,
                        element(RunStatus, { run: messageRun, stopping: stoppingId === messageRun.id, expanded: expandedRuns.includes(messageRun.id), toggle: () => { setSelectedRunId(messageRun.id); setSourceDetail(null); setActiveSection("conditions"); setExpandedRuns(current => current.includes(messageRun.id) ? current.filter(id => id !== messageRun.id) : [...current, messageRun.id]); }, retry: () => retry(messageRun), retryNow: () => retryNow(messageRun), changeModel: () => changeModel(messageRun), enabled: !active && !submitting }),
                        messageRun.result && element(ResearchDocument, { run: messageRun, conversationId: selected.id, togglePin: () => togglePin(messageRun), act, planIndex, carry: link.side || messageRun.status !== "completed" ? null : {branch: () => branchRun(messageRun), ask: () => askRun(messageRun), side: selected.sideChats?.[messageRun.id]}, enabled: !active && !submitting && messageRun.id === latestRun(selected)?.id, planEnabled: !active && !submitting && (!selected.plan || selected.plan.status === "PENDING") && messageRun.id === latestRun(selected)?.id, tableMenu: tableMenu, setTableMenu: setTableMenu, expand: () => setExpandedTable(messageRun) }))); }))),
                !autoFollow && element("button", { className: "jump-latest", onClick: () => { setAutoFollow(true); scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); } },
                    element(Icon, { name: "arrow-down" }),
                    "Jump to latest"),
                apiError && element("div",{className:"auth-error",role:"alert"},apiError),
                pendingReply && element("div",{className:"composer-status"},"Describe the plan revision",element("button",{onClick:()=>setPendingReply(null)},"Dismiss")),
                inputHint && element("div",{className:"composer-status"},inputHint,element("button",{onClick:()=>setInputHint(null)},"Dismiss")),
                element("div", { key: "research-composer", ref:composerPanelRef, className: `composer ${active ? "running" : ""} ${prompt.trim() ? "has-text" : ""}` },
                    element(ComposerResizeHandle,{fieldRef:composerRef,height:composerHeight,setHeight:setComposerHeight}),
                    // MONITOR-REVAMP (AI_revamp.html): no running line in the box; the answer shows its steps and the hint
                    // beside the send button says what the button does now
                    // EXEC-UI-1024 2c: each attachment carries its own comment; the message stays the general question. The
                    // comment is kept on the item as typed (no redraw per keystroke) and sent with it
                    // EXEC-UI-1025 (user 2026-10-24: "dibuat lebih nice"; ChatGPT/Claude benchmark): each attachment is a
                    // quote (accent bar, the passage in two lines) with its note written under it, without a boxed field
                    attached.map((item,index)=>element("div",{key:`attached-${index}`,className:"edge-attached-chip"},
                    element("div",{className:"edge-attached-quote"},
                        element("span",{className:"edge-attached-text",title:item.kind==="TEXT"?item.quote:undefined},item.kind==="TEXT"?item.quote:EdgeView.selectionLabel(item)),
                        item.kind==="TEXT"&&(item.figures||[]).length>0&&element("span",{className:"edge-attached-meta"},edgeUi().attachFigures.replace("{n}",String(item.figures.length))),
                        element("button",{type:"button",className:"edge-attached-remove","aria-label":edgeUi().attachRemove,title:edgeUi().attachRemove,onClick:()=>setAttached(attached.filter((_,i)=>i!==index))},element(Icon,{name:"close",size:12}))),
                    element("textarea",{className:"edge-attached-comment",rows:1,maxLength:500,value:item.comment||"",placeholder:edgeUi().attachComment,"aria-label":edgeUi().attachComment,
                        onInput:event=>{item.comment=event.target.value.slice(0,500);event.target.style.height="auto";event.target.style.height=event.target.scrollHeight+"px";}}))),
                    context && element("div", { className: "research-context" },
                        element("span", null, "Context"),
                        element("strong", null,
                            context.symbol,
                            " \u00B7 ",
                            context.name),
                        element("button", { onClick: () => { setContext(undefined); sessionStorage.removeItem("edge-research-context"); }, "aria-label": "Remove research context" },
                            element(Icon, { name: "close" }))),
                    attachments.map(file => element("div", { className: "attachment-row", key: file.name },
                        element(Icon, { name: "attach" }),
                        element("span", null,
                            element("strong", null, file.name),
                            element("small", null,
                                Math.max(1, Math.round(file.size / 1024)),
                                " KB \u00B7 ",
                                file.state === "uploading" ? "Uploading" : file.state === "ready" ? "Ready" : "Failed")),
                        element("button", { onClick: () => setAttachments(current => current.filter(item => item.name !== file.name)), "aria-label": `Remove ${file.name}` },
                            element(Icon, { name: "close" })))),
                    element("textarea", { ref: composerRef, rows: 1, value: prompt, style:composerHeight===null?undefined:{height:composerHeight+"px"}, onChange: event => { typePrompt(event.target.value); if(composerHeight===null){event.target.style.height = "auto"; event.target.style.height = `${Math.min(event.target.scrollHeight, 140)}px`;} }, placeholder: context ? `Ask anything about ${context.symbol}…` : "Ask a research question…", onKeyDown: event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !touchKeyboard()) {
                            event.preventDefault();
                            submit();
                        } } }),
                    element("div", null,
                        element("div", null,
                            // EXEC-SHARE-UI (user 2026-10-19, screenshot 2: "item tersebut di remove saja"): no Research Mode menu
                            element(EdgeModelSelector, null),
                            element(Button, { kind: "ghost", icon: "database", disabled: true, title: "Data Scope is not available yet" }, "Data scope"),
                            element(IconButton, { icon: "attach", disabled: true, title: "Attachments are not available yet" })),
                        // MONITOR-REVAMP (AI_revamp.html .cbar): a hint, then one square button (send; stop in red; Stop & send
                        // when text waits while a run goes on); its name stays in its label
                        element("div", { className: "edge-send-group" },
                            element("span", { className: "edge-send-hint" }, active && !submitting ? (prompt.trim() ? edgeUi().stopAndSend : edgeUi().runningHint) : edgeUi().sendHint),
                            active && !submitting ? (prompt.trim() ? element("button", { type: "button", className: "edge-send", "aria-label": edgeUi().stopAndSend, title: edgeUi().stopAndSend, onClick: () => submit({}, null, {afterStop: true}) }, element(Icon, { name: "send" })) : element("button", { type: "button", className: "edge-send stop", disabled: stoppingId === executionRun.id, "aria-label": stoppingId === executionRun.id ? edgeUi().stopping : edgeUi().stop, title: stoppingId === executionRun.id ? edgeUi().stopping : edgeUi().stop, onClick: stopRun }, element(Icon, { name: "stop" }))) : element("button", { type: "button", className: "edge-send", disabled: active || submitting || !prompt.trim(), "aria-label": submitting ? "Processing…" : edgeUi().send, title: submitting ? "Processing…" : edgeUi().send, onClick: () => submit() }, element(Icon, { name: "send" })))))),
            detailsOpen && element("aside", { id:"edge-details",className: `details-panel${pinsOpen ? "" : " pins-collapsed"}${flowOpen || detailsTab !== "Flow" ? "" : " flow-collapsed"}`,role:narrow&&mobileDetailsOpen?"dialog":undefined,"aria-modal":narrow&&mobileDetailsOpen?true:undefined,"aria-label":"Response details",inert:narrow&&historyOpen },
                element(DetailsResizeHandle,{width:detailsWidth,setWidth:setDetailsWidth}),
                // MONITOR-REVAMP (AI_revamp.html .dt-h): the tabs and the close button share the panel's first row
                element("div", { className: "details-head" },
                    element(Tabs, { items: ["Flow", "Sources"], active: detailsTab, onChange: value => { setDetailsTab(value); setSourceDetail(null); } }),
                    element(IconButton, { icon: "close", onClick: () => {setMobileDetailsOpen(false);setDetailsOpen(false);}, title: "Close details" })),
                // MONITOR-REVAMP (AI_revamp.html): Pinned responses belong to the Flow tab (Outline there); Sources shows its parts only
                detailsTab === "Flow" && element(PinnedResponses, { open:pinsOpen, toggle:togglePins, height:pinsHeight, runs:selected?.runs ?? [], unpin:id=>togglePin(selected.runs.find(r=>r.id===id),false), jump:jumpToRun }),
                detailsTab === "Flow" && pinsOpen && flowOpen && element(PinsResizeHandle, { height:pinsHeight, setHeight:value => { setPinsHeight(value); keep("edge-pins-height", value); } }),
                element("div", {className:"edge-details-upper",ref:historyScrollRef}, run ? detailsTab === "Sources" ? element(Sources,{run,act}) : element(ResponseFlows, { runs:selected?.runs ?? [], autoOpenRunId, open:flowOpen, toggle:toggleFlow, jump:jumpToRun }) : element("div", { className: "details-empty" }, "Open or start a conversation to see its outline, sources and run details."))),
            // EXEC-ASK-BRANCH: the side chat of one answer: the same EDGE, showing only that conversation (Q2: it is not
            // in the conversation list; the answer links to it)
            sidePanel && element("aside",{className:"edge-side-chat","aria-label":edgeUi().askAbout},
                element("div",{className:"edge-side-head"},element("strong",null,edgeUi().askAbout),
                    element(IconButton,{icon:"close",title:edgeUi().sideClose,onClick:closeSide})),
                element("iframe",{key:sidePanel.key,className:"edge-side-frame",src:conversationUrl(sidePanel.conversationId,true),title:edgeUi().askAbout})),
            (historyOpen || mobileDetailsOpen) && element("button",{className:"edge-panel-backdrop",tabIndex:-1,"aria-label":"Close panel",onClick:()=>{setHistoryOpen(false);setMobileDetailsOpen(false);}}),
            expandedTable && element(ResearchTableDialog, { run: expandedTable, close: () => setExpandedTable(null) })));
}
function ConversationHistoryList({ items, selectedId, select, toggleBookmark, requestHide }) {
    // MONITOR-REVAMP (user 2026-10-30, AI_revamp.html renderNav): a branch sits under the conversation it continues, in
    // that conversation's group, with the branch icon; a branch whose parent is not in the list stays in its own group
    const shown = new Set(items.map(item => item.id));
    const nested = item => item.kind === "BRANCH" && item.parent?.conversationId && item.parent.conversationId !== item.id && shown.has(item.parent.conversationId);
    const row = (item, child) => { const itemRun = latestRun(item), last = itemRun ?? item.lastRun; return element("div", { key: item.id, role: "button", tabIndex: 0, "aria-selected": item.id === selectedId, className: `conversation ${item.id === selectedId ? "active" : ""}${child ? " child" : ""}`, onClick: () => select(item.id), onKeyDown: event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                select(item.id);
            } } },
            // M317 (user 2026-10-31): the dot's colour is the state of the latest question (Edge.statusTone), also for a
            // conversation not opened yet (the list API's last_state/last_run_status); never grey
            element("i", { className: `conversation-state ${itemRun?.status ?? "draft"} edge-tone-${last ? Edge.statusTone(last.status, last.domainStatus, last.paused, last.stopped) : "new"}` }),
            element("span", null,
                element("strong", null, item.kind === "BRANCH" && element(Icon, { name: "branch", size: 12 }), item.title),
                element("small", null, item.messages.findLast(message => message.role === "user")?.content ?? item.lastMessage)),
            element("span", { className: `conversation-actions${item.bookmarked ? " keep" : ""}` },
            element("button", { className: `conversation-bookmark ${item.bookmarked ? "active" : ""}`, "aria-label": `${item.bookmarked ? "Remove" : "Add"} bookmark`, "aria-pressed":Boolean(item.bookmarked), onClick: event => { event.stopPropagation(); toggleBookmark(item.id); } },
                element(Icon, { name: "bookmark" })),
            element("button", { className: "conversation-bookmark conversation-delete", "aria-label": `Delete ${item.title}`, title: "Delete conversation", disabled: ["submitted", "running", "streaming"].includes(itemRun?.status) || item.id.startsWith("draft:"), onClick: event => { event.stopPropagation(); requestHide?.(item); } },
                element(Icon, { name: "trash" })))); };
    // a branch of a branch follows its own parent; each conversation shows once
    const withChildren = (item, child, seen) => { if (seen.has(item.id)) return []; seen.add(item.id);
        return [row(item, child), ...items.filter(other => nested(other) && other.parent.conversationId === item.id).flatMap(other => withChildren(other, true, seen))]; };
    const seen = new Set();
    return element(fragment, null, ["Today", "Yesterday", "Previous 7 Days", "Older"].map(group => { const conversations = items.filter(item => !nested(item) && conversationGroup(item.updatedAt) === group); return conversations.length ? element("div", { className: "conversation-group", key: group },
        element("span", null, group),
        conversations.flatMap(item => withChildren(item, false, seen))) : null; }));
}

function formatMessageJakarta(iso) {
    const value = new Date(iso);
    if (Number.isNaN(value.getTime())) return "Timestamp unavailable";
    return new Intl.DateTimeFormat("en-GB", {timeZone:"Asia/Jakarta",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(value) + " UTC+7";
}
// EXEC-MODELS (user 2026-10-13): the model and reasoning level of the next message, chosen next to the composer and kept
// in this browser; the models, their levels and prices come from Orc (GET /api/v1/models, prices read every hour). EDGE
// starts on Orc's edge_default (DeepSeek V4.1 Flash, high); without the list no choice is sent (the server default runs).
const MODEL_CHOICE_KEY = "edge-model-choice";
let edgeModelsAwaited = false;
const edgeModels = {get data(){return Edge.modelList().data;}, get failed(){return Edge.modelList().failed;}};
function loadEdgeModels(){
  // read at sign-in (edge-client.js); a list still on its way when the page showed redraws it once on arrival
  if(edgeModels.data||edgeModels.failed||edgeModelsAwaited)return;
  edgeModelsAwaited=true;Edge.loadModels().then(()=>{edgeModelsAwaited=false;refresh();});
}
function edgeDefaultLevel(option){
  const fallback=edgeModels.data?.edge_default||{};
  return option.model===fallback.model&&option.reasoning_levels.includes(fallback.reasoning_level)?fallback.reasoning_level:option.reasoning_levels.at(-1);
}
function edgeModelChoice(){
  const data=edgeModels.data;if(!data)return {};
  let saved=null;try{saved=JSON.parse(localStorage.getItem(MODEL_CHOICE_KEY)||"null");}catch{saved=null;}
  const pick=model=>data.models.find(option=>option.model===model);
  const option=pick(saved?.model)||pick(data.edge_default?.model)||data.models[0];
  const level=saved?.model===option.model&&option.reasoning_levels.includes(saved?.reasoning_level)?saved.reasoning_level:edgeDefaultLevel(option);
  return {model:option.model,reasoning_level:level,...(data.lane_selection?{lane:edgeLane()}:{})};
}
// EXEC-UI-1015D (user 2026-10-15, "bisa buat semua jalur cepat fastlane latest V by default, sehingga kita tidak perlu ada
// opsi jalur"): every EDGE message runs the fast lane while Orc reports lane_selection (otherwise no lane is sent); the
// standard lane stays in Orc as the fallback for other callers. A lane kept by the old toggle is ignored.
function edgeLane(){return "fast";}
// EXEC-LOGOS (user 2026-10-13, "kasih logo untuk setiap model ya di HP"): each model's brand logo (LobeHub icons, MIT),
// served from static/model-logos/. A one-colour logo is drawn as a mask in the text colour, so it shows in light and
// dark; a model without a logo keeps its initial letter.
const MODEL_LOGOS = {deepseek:{file:"deepseek-color.svg"}, "z-ai":{file:"zai.svg",mono:true},
  xiaomi:{file:"xiaomimimo.svg",mono:true}, qwen:{file:"qwen-color.svg"}};
function EdgeModelLogo({option}){
  const logo=MODEL_LOGOS[option.model.split("/")[0]],url="/model-logos/"+(logo?logo.file:"");
  if(!logo)return element("span",{className:"edge-model-initial","aria-hidden":"true"},(option.label||option.model).charAt(0));
  return logo.mono?element("span",{className:"edge-model-logo mono",role:"img","aria-label":option.label,style:{"--logo":`url("${url}")`}})
    :element("img",{className:"edge-model-logo",src:url,alt:option.label});
}
// EXEC-UI-1013B (gambar 2): the model of an answer, for its logo in the answer's header; a model no longer offered
// keeps its id as label and its brand logo by prefix
function edgeModelOption(model){
  return edgeModels.data?.models?.find(option=>option.model===model)||{model:String(model||""),label:String(model||"")};
}
// EXEC-UI-1013B (gambar 2): a spreadsheet mark left of a Download link of an Excel file (decorative: the link's name stays
// "Download <file>"); other files keep the download icon
function FileTypeIcon({label}){
  const ext=String(label||"").toLowerCase().split(".").pop();
  if(ext!=="xlsx"&&ext!=="xls")return element(Icon,{name:"download"});
  return element("svg",{className:"edge-file-icon xlsx",width:16,height:16,viewBox:"0 0 24 24","aria-hidden":"true"},
    element("rect",{x:"3",y:"3",width:"18",height:"18",rx:"3",fill:"#1D6F42"}),
    element("path",{d:"M8.5 8l7 8M15.5 8l-7 8",stroke:"#FFFFFF",strokeWidth:"2.2",strokeLinecap:"round",fill:"none"}));
}
// contract 4b: the choice is an account preference (EdgeSession SYNC_KEYS), copied to the account a moment later
function keepModelChoice(choice){try{localStorage.setItem(MODEL_CHOICE_KEY,JSON.stringify(choice));}catch{}Edge.notePreference?.(MODEL_CHOICE_KEY);refresh();}
const edgeModelTime=new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Jakarta",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
function edgeModelPrice(value){return value==null?"–":"$"+(value<1?value.toFixed(3):value.toFixed(2));}
function EdgeModelSelector(){
  const view=currentView,ui=edgeUi();
  loadEdgeModels();
  const open=initialValue(view,"open",()=>false),setOpen=next=>updateValue(view,"open",next);
  const anchor=cachedValue(view,"anchor",()=>({current:null}),[]);
  onLifecycle(view,"outside",()=>{
    if(!open)return;
    const close=event=>{if(event.type==="keydown"?event.key==="Escape":!anchor.current?.contains(event.target))setOpen(false);};
    document.addEventListener("mousedown",close);document.addEventListener("keydown",close);
    return ()=>{document.removeEventListener("mousedown",close);document.removeEventListener("keydown",close);};
  },[open]);
  const data=edgeModels.data;
  if(!data){
    if(edgeModels.failed)return null;
    // while the list loads the trigger keeps its place, so its arrival redraws text only and never moves the composer
    return element("span",{className:"edge-model-anchor",ref:anchor},
      element("button",{type:"button",className:"edge-model-trigger",disabled:true,title:ui.modelTitle},
        element("span",{className:"edge-model-initial"},"\u2026"),element("span",{className:"edge-model-name"},ui.modelHead),
        element("span",{className:"edge-model-level"},""),element(Icon,{name:"chevron"})));
  }
  const choice=edgeModelChoice(),current=data.models.find(option=>option.model===choice.model);
  const levelName=level=>ui.modelLevels?.[level]??level;
  const updated=data.prices_fetched_at?new Date(data.prices_fetched_at):null;
  return element("span",{className:"edge-model-anchor",ref:anchor},
    element("button",{type:"button",className:"edge-model-trigger","aria-expanded":open,"aria-haspopup":"dialog",title:ui.modelTitle,onClick:()=>setOpen(!open)},
      element(EdgeModelLogo,{option:current}),
      element("span",{className:"edge-model-name"},current.label),
      element("span",{className:"edge-model-level"},levelName(choice.reasoning_level)),
      element(Icon,{name:"chevron"})),
    open&&element("div",{className:"edge-model-menu",role:"dialog","aria-label":ui.modelTitle},
      element("div",{className:"edge-model-head"},element("strong",null,ui.modelHead),
        element("small",null,ui.modelPricesNote+(updated&&!Number.isNaN(updated.getTime())?" · "+ui.modelUpdated+" "+edgeModelTime.format(updated)+" WIB":""))),
      // EXEC-UI-1015 U5 (user 2026-10-15): the cards keep their design; the thinking level and the lane sit in the
      // right-hand space of the chosen card ("kotak A"), so the choice and its settings read as one
      element("div",{className:"edge-model-options"},data.models.map(option=>{
        const chosen=option.model===choice.model;
        return element("div",{key:option.model,className:`edge-model-card${chosen?" chosen":""}`},
          element("button",{type:"button",className:"edge-model-option","aria-pressed":chosen,
              onClick:()=>keepModelChoice({model:option.model,reasoning_level:chosen?choice.reasoning_level:edgeDefaultLevel(option)})},
            element("span",{className:"edge-model-brand"},element(EdgeModelLogo,{option}),
              element("span",null,element("small",null,option.model.split("/")[0]),element("strong",null,option.label))),
            element("span",{className:"edge-model-stats"},
              element("span",null,element("small",null,ui.modelInput),element("b",null,edgeModelPrice(option.input_per_million))),
              element("span",null,element("small",null,ui.modelOutput),element("b",null,edgeModelPrice(option.output_per_million)))),
            element("span",{className:"edge-model-id"},option.model)),
          chosen&&element("div",{className:"edge-model-controls"},
            element("div",{className:"edge-model-levels",role:"radiogroup","aria-label":ui.modelLevel},
              element("small",null,ui.modelLevel),
              option.reasoning_levels.map(level=>element("button",{key:level,type:"button",role:"radio","aria-checked":level===choice.reasoning_level,
                onClick:()=>keepModelChoice({model:option.model,reasoning_level:level})},levelName(level)))),
            ));
      }))));
}
function ResearchScrollMarker({ scrollRef, conversationId }) {
    const view = currentView, markerRef = cachedValue(view, "marker", () => ({ current: null }), []);
    onLifecycle(view, "marker-scroll", () => {
        const viewport = scrollRef.current, marker = markerRef.current;
        if (!viewport || !marker) return;
        const labels = { conditions:"Signal Conditions", statistics:"Summary Statistics", observation:"Key Observation", distribution:"Observation Distribution", methodology:"Methodology" };
        let drag = null;
        const update = () => {
            const max = Math.max(0, viewport.scrollHeight - viewport.clientHeight), ratio = max ? Math.min(1, Math.max(0, viewport.scrollTop / max)) : 0;
            marker.hidden = !viewport.querySelector(".user-message") || max < 1;
            const markerY = 24 + ratio * Math.max(0, viewport.clientHeight - 48);
            marker.style.top = (viewport.offsetTop + markerY) + "px";
            const points = [...viewport.querySelectorAll(".user-message, .result-kicker, .content-block[id]")];
            const threshold = viewport.getBoundingClientRect().top + markerY;
            let active = points[0];
            for (const point of points) if (point.getBoundingClientRect().top <= threshold) active = point;
            const label = active?.classList.contains("user-message") ? edgeUi().markerQuestion : active?.classList.contains("result-kicker") ? edgeUi().markerAnswer : labels[active?.id.split("-").at(-1)] ?? "Research";
            marker.textContent = label;
            marker.setAttribute("aria-valuenow", String(Math.round(ratio * 100)));
            marker.setAttribute("aria-valuetext", label);
        };
        const down = event => { if (event.button !== 0) return; event.preventDefault(); marker.focus({preventScroll:true}); drag = { id:event.pointerId, y:event.clientY, scroll:viewport.scrollTop }; marker.setPointerCapture(event.pointerId); marker.classList.add("dragging"); viewport.classList.add("edge-dragging"); };
        const move = event => { if (!drag || event.pointerId !== drag.id) return; const max = Math.max(0, viewport.scrollHeight - viewport.clientHeight), travel = Math.max(1, viewport.clientHeight - 48); viewport.scrollTop = Math.max(0, Math.min(max, drag.scroll + (event.clientY - drag.y) * max / travel)); update(); };
        const end = event => { if (!drag || event.pointerId !== drag.id) return; drag = null; marker.classList.remove("dragging"); viewport.classList.remove("edge-dragging"); if (marker.hasPointerCapture(event.pointerId)) marker.releasePointerCapture(event.pointerId); };
        const key = event => { const destinations = { ArrowDown:viewport.scrollTop+40, ArrowUp:viewport.scrollTop-40, PageDown:viewport.scrollTop+viewport.clientHeight*.9, PageUp:viewport.scrollTop-viewport.clientHeight*.9, Home:0, End:viewport.scrollHeight-viewport.clientHeight }; if (event.key in destinations) { event.preventDefault(); viewport.scrollTo({top:destinations[event.key],behavior:"instant"}); update(); } };
        viewport.addEventListener("scroll", update, {passive:true});
        marker.addEventListener("pointerdown", down); marker.addEventListener("pointermove", move); marker.addEventListener("pointerup", end); marker.addEventListener("pointercancel", end); marker.addEventListener("lostpointercapture", end); marker.addEventListener("keydown", key);
        const resize = new ResizeObserver(update); resize.observe(viewport);
        const mutation = new MutationObserver(update); mutation.observe(viewport,{childList:true,subtree:true,characterData:true});
        window.addEventListener("resize",update); update();
        return () => { resize.disconnect(); mutation.disconnect(); viewport.removeEventListener("scroll",update); window.removeEventListener("resize",update); marker.removeEventListener("pointerdown",down);marker.removeEventListener("pointermove",move);marker.removeEventListener("pointerup",end);marker.removeEventListener("pointercancel",end);marker.removeEventListener("lostpointercapture",end);marker.removeEventListener("keydown",key);viewport.classList.remove("edge-dragging"); };
    }, [conversationId]);
    return element("div", {ref:markerRef,className:"edge-scroll-marker",role:"scrollbar",tabIndex:0,"aria-label":edgeUi().markerLabel,"aria-orientation":"vertical","aria-valuemin":0,"aria-valuemax":100}, edgeUi().markerQuestion);
}

// EXEC-IMPL-1016 Fase 4.3 (UI-1015B): while an answer runs, Orc's steps are read every PROGRESS_POLL_MS through the
// BFF: the time so far, the step running now, and the finished steps (folded)
const PROGRESS_POLL_MS = 2500;
function RunProgress({ run }) {
    const viewRecord = currentView;
    const data = initialValue(viewRecord, "data", () => null);
    onLifecycle(viewRecord, "poll", () => {
        let stopped = false, timer = null;
        const poll = async () => {
            try { const next = await Edge.api(`/runs/${encodeURIComponent(run.id)}/progress`); if (!stopped) updateValue(viewRecord, "data", next && {...next, receivedAt: performance.now()}); }
            catch { /* progress is a convenience: a failed read keeps the last one */ }
            if (!stopped) timer = setTimeout(poll, PROGRESS_POLL_MS);
        };
        poll();
        return () => { stopped = true; clearTimeout(timer); };
    }, [run.id]);
    const view = EdgeView.progressView(data);
    if (!view) return null;
    // MONITOR-REVAMP (AI_revamp.html running card): "EDGE" with a blue "Running · <time>" pill, then the finished steps
    // (a check and their time) and the step running now (a spinner); EXEC-UI-1024 1A: the running step shows its label only
    return element("div", { className: "edge-run-progress" },
        element("div", { className: "edge-run-progress-now" },
            element(Icon, { name: "spark" }), element("span", null, edgeUi().answerKicker),
            element("span", { className: "edge-badge info" }, element("i", { className: "edge-badge-dot", "aria-hidden": "true" }), edgeUi().running,
                view.elapsed && element(fragment, null, " \u00B7 ", element(RunClock, { elapsedMs: data.elapsed_ms, at: data.receivedAt })))),
        element("div", { className: "edge-run-steps" },
            view.earlier && element("small", { className: "edge-run-earlier" }, view.earlier),
            view.done.map((step, index) => element("div", { key: index, className: `edge-run-step done${step.note ? " warn" : ""}` },
                element("span", { className: "edge-run-step-mark", "aria-hidden": "true" }, step.note ? "!" : element(Icon, { name: "check" })),
                element("span", null, step.label), step.note && element("em", null, step.note),
                step.duration && element("time", null, step.duration))),
            view.current && element("div", { className: "edge-run-step now" }, element("span", { className: "edge-run-step-mark", "aria-hidden": "true" }),
                element("span", { className: "edge-run-progress-step" }, element("span", null, /[.…!?]$/.test(view.current) ? view.current : view.current + "\u2026")))),
        element("p", { className: "edge-run-note" }, edgeUi().runNote));
}

// E12 (EXEC-1018B, user 2026-10-16 "as smooth as 1 detik"): each server reading implies when the run started (the
// time it arrived minus its elapsed time); the clock keeps the earliest start any reading implied, so a reading that
// lags (sent before its arrival) neither stalls the clock nor moves it back. It redraws at each whole second (aligned
// to the clock, so a background tab is right when it comes back)
function RunClock({ elapsedMs, at, className = "edge-run-progress-time edge-run-clock", prefix = "" }) {
    const viewRecord = currentView;
    const shown = initialValue(viewRecord, "shown", () => 0);
    const startRef = (viewRecord.refs.start ??= { current: Infinity });
    startRef.current = Math.min(startRef.current, (at || performance.now()) - (Number(elapsedMs) || 0));
    onLifecycle(viewRecord, "tick", () => {
        let timer = null, stopped = false;
        const tick = () => {
            if (stopped) return;
            const ms = Math.max(0, performance.now() - startRef.current);
            updateValue(viewRecord, "shown", previous => Math.max(previous || 0, Math.floor(ms / 1000)));
            timer = setTimeout(tick, 1000 - (ms % 1000) + 5);
        };
        tick();
        return () => { stopped = true; clearTimeout(timer); };
    }, [elapsedMs, at]);
    return element("span", { className: `${className} ${shown % 2 ? "odd" : "even"}`,
        "data-seconds": String(shown) }, prefix + EdgeView.durationText(shown * 1000));
}

const PROVIDER_STALL_CODES = new Set(["PROVIDER_STALLED", "PROVIDER_TIMEOUT", "REASONING_RUNAWAY"]);
function RunStatus({ run, stopping, expanded, toggle, retry, retryNow, changeModel, enabled = true }) {
    const active = ["submitted", "running", "streaming"].includes(run.status);
    // MONITOR-REVAMP (AI_revamp.html running card): the running answer is a card like an answer
    if (active) return element("div", { className: "edge-inline-progress-wrap edge-run-card" },
        element("div", { className: "edge-inline-progress", role: "status", "aria-live": "polite" },
        // user 2026-10-30 ("buat sama dengan terminal speednya"): the Terminal's ring, one turn in 0.15 s
        element("span", { className: "edge-run-ring", "aria-hidden": "true" }),
        element("span", null, stopping ? edgeUi().stoppingHint : run.status === "streaming" ? "Streaming research result…" : run.steps.find(step => step.status === "running")?.label ?? "Submitted")),
        run.status === "running" && !stopping && element(RunProgress, { key: run.id, run }));
    // EXEC-Y Fase 1 (S1): an answer stopped by the user offers its question back to edit and resend
    if (run.stopped && run.status === "completed") return element("div", { className: "run-inline-state cancelled", role: "status" },
        element("div", null, element("strong", null, edgeUi().stopped), element("span", null, edgeUi().stoppedHint)),
        element(Button, { icon: "refresh", onClick: retry }, edgeUi().editResend));
    // EXEC-M181: the AI provider timed out (after Orc's one automatic retry) or kept thinking without answering
    if (run.status === "failed" && PROVIDER_STALL_CODES.has(run.error) && retryNow) {
        const ui = edgeUi(), runaway = run.error === "REASONING_RUNAWAY";
        return element("div", { className: "run-inline-state failed edge-provider-stalled", role: "status", "data-error": run.error },
            element("div", null, element("strong", null, runaway ? ui.runawayStalled : ui.providerStalled),
                element("span", null, runaway ? ui.runawayStalledHint : ui.providerStalledHint)),
            element("div", { className: "edge-stalled-actions" },
                element(Button, { icon: "refresh", kind: "primary", onClick: retryNow, disabled: !enabled }, ui.retry),
                element(Button, { onClick: changeModel, disabled: !enabled }, ui.changeModel)));
    }
    if (run.status === "failed" || run.status === "cancelled") return element("div", { className: `run-inline-state ${run.status}`, role: "status" },
        element("div", null, element("strong", null, run.status === "failed" ? "Research failed" : "Research cancelled"), element("span", null, run.error === "STOPPED_BY_USER" ? edgeUi().stopped : run.errorText || run.error)),
        element(Button, { icon: "refresh", onClick: retry }, "Retry"));
    return null;
}
function DetailsResizeHandle({width,setWidth}) {
    const view=currentView,drag=cachedValue(view,"drag",()=>({cleanup:null}),[]);
    const commit=value=>{setWidth(value);localStorage.setItem("edge-details-width",String(value));};
    const start=event=>{
        if(event.button!==0)return;
        event.preventDefault();drag.cleanup?.();
        const startX=event.clientX,startWidth=width;
        const layout=event.currentTarget.closest(".monitor-layout"),left=layout?.querySelector(".conversation-panel");
        const maxWidth=Math.max(280,Math.min(560,(layout?.clientWidth||1120)-(left?.clientWidth||272)-560));
        let nextWidth=width;
        const move=e=>{nextWidth=Math.min(maxWidth,Math.max(280,startWidth+startX-e.clientX));setWidth(nextWidth);};
        const end=()=>{localStorage.setItem("edge-details-width",String(nextWidth));drag.cleanup?.();};
        const oldCursor=document.body.style.cursor,oldSelect=document.body.style.userSelect;
        document.body.style.cursor="col-resize";document.body.style.userSelect="none";
        drag.cleanup=()=>{document.removeEventListener("pointermove",move);document.removeEventListener("pointerup",end);document.removeEventListener("pointercancel",end);document.body.style.cursor=oldCursor;document.body.style.userSelect=oldSelect;drag.cleanup=null;};
        document.addEventListener("pointermove",move);document.addEventListener("pointerup",end);document.addEventListener("pointercancel",end);
    };
    onLifecycle(view,"resize-cleanup",()=>()=>drag.cleanup?.(),[]);
    return element("div",{className:"edge-details-resizer",role:"separator",tabIndex:0,"aria-label":"Resize Details panel","aria-orientation":"vertical","aria-valuemin":280,"aria-valuemax":560,"aria-valuenow":width,onPointerDown:start,onDoubleClick:()=>commit(340),onKeyDown:e=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();commit(Math.min(560,Math.max(280,width+(e.key==="ArrowLeft"?20:-20))));}},title:"Drag to resize · double-click to reset"});
}
function DisclosureChevron() {
    return element("svg",{className:"edge-disclosure-chevron",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.6,strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true"},element("path",{d:"m6 9 6 6 6-6"}));
}
// EXEC-DURATION: a finished run's processing time (Orc's duration), else its saved start-to-finish time
const runDuration=run=>{if(run.status==="running"||run.status==="submitted")return null;
    const orc=run.raw?.execution?.duration_ms;if(typeof orc==="number")return EdgeView.durationText(orc);
    const start=Date.parse(run.createdAt),end=Date.parse(run.completedAt);return Number.isFinite(start)&&Number.isFinite(end)&&end>=start?EdgeView.durationText(end-start):null;};
// MONITOR-REVAMP (AI_revamp.html .hist): a response is a raised card: a green check when it completed (a coloured dot
// otherwise), its title in two lines, then its status, time and processing time
function ResponseFlowItem({run,initiallyOpen=false,jump}) {
    const view=currentView,expanded=initialValue(view,"expanded",()=>initiallyOpen);
    const label=Edge.statusLabel(run.status,run.domainStatus,run.paused),done=run.status==="completed"&&!run.paused&&!["AWAITING_CONFIRMATION","NEEDS_CLARIFICATION","FAILED","LIMITED"].includes(run.domainStatus);
    // M317: the same colour as the conversation list and the session row (Edge.statusTone); never grey
    const tone=Edge.statusTone(run.status,run.domainStatus,run.paused,run.stopped);
    return element("details",{id:`edge-history-${run.id}`,className:"edge-flow-accordion",open:expanded,onToggle:event=>updateValue(view,"expanded",event.currentTarget.open)},
        element("summary",null,
            done?element("b",{className:"edge-okmark",role:"img","aria-label":label},element("svg",{viewBox:"0 0 24 24","aria-hidden":"true"},element("path",{d:"m5 12 4.5 4.5L19 7"})))
                :element("i",{className:`edge-history-dot ${tone}`,"aria-hidden":"true"}),
            element("div",null,
            element("strong",{title:run.result?.title ?? run.question},run.result?.title ?? run.question),
            element("small",null,label," · ",formatMessageJakarta(run.completedAt ?? run.createdAt),runDuration(run)?" · "+runDuration(run):"")),element(DisclosureChevron)),
        element(Flow,{run}),
        // EXEC-UI-1015C: back to this response in the conversation
        jump&&element("button",{type:"button",className:"edge-history-jump",onClick:()=>jump(run.id)},edgeUi().historyJump,element(Icon,{name:"arrow-right",size:13})));
}
// EXEC-DETAILS: a section title that collapses and expands its section
function SectionToggle({label,open,toggle,controls,icon=null,count=null}) {
    // Some touch browsers suppress the compatibility click immediately after a drag. Handle an unmoved
    // touch release directly; suppress only its later click, while keyboard/mouse activation stays native.
    const touch=cachedValue(currentView,"touch",()=>({start:null,released:false,ignoreUntil:0}),[]);
    const down=event=>{if(event.pointerType==="touch"){touch.released=false;touch.start={id:event.pointerId,x:event.clientX,y:event.clientY};}};
    const up=event=>{const start=touch.start;touch.start=null;if(!start||start.id!==event.pointerId)return;
        const box=event.currentTarget.getBoundingClientRect();
        if(Math.hypot(event.clientX-start.x,event.clientY-start.y)>8||event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)return;
        touch.released=true;};
    const end=event=>{if(!touch.released)return;touch.released=false;event.preventDefault();touch.ignoreUntil=performance.now()+750;toggle();};
    const click=event=>{if(event.detail===0||(event.pointerType==="mouse"&&!event.sourceCapabilities?.firesTouchEvents)||performance.now()>touch.ignoreUntil)toggle();};
    return element("button",{type:"button",className:"edge-section-toggle","aria-expanded":open,"aria-controls":controls,onPointerDown:down,onPointerUp:up,onPointerCancel:()=>{touch.start=null;touch.released=false;},onTouchEnd:end,onTouchCancel:()=>{touch.start=null;touch.released=false;},onClick:click},
        icon&&element(Icon,{name:icon}),element("span",null,label),count!=null&&element("span",{className:"edge-section-count","aria-hidden":"true"},String(count)),element(DisclosureChevron));
}
function ResponseFlows({runs,autoOpenRunId,open=true,toggle,jump}) {
    return element("div",{className:"edge-flow-list"},element("div",{className:"edge-history-head"},element(SectionToggle,{label:"Response history",icon:"history",count:runs.length,open,toggle,controls:"edge-flow-items"})),
        open&&element("div",{id:"edge-flow-items"},[...runs].reverse().map(run=>element(ResponseFlowItem,{key:run.id,run,initiallyOpen:run.id===autoOpenRunId,jump}))));
}
function PinnedResponses({runs,unpin,jump,open=true,toggle,height}) {
    const pinned=runs.filter(run=>run.pinned&&run.result);
    return element("section",{className:"edge-pins","aria-label":"Pinned responses",style:open&&height?{flex:`0 0 ${height}px`,height:`${height}px`}:undefined},
        element("div",{className:"edge-pins-head"},element(SectionToggle,{label:"Pinned responses",icon:"pin",count:pinned.length,open,toggle,controls:"edge-pins-items"})),
        open&&element("div",{id:"edge-pins-items"},pinned.length?pinned.map(run=>element(PinnedResponseCard,{key:run.id,run,unpin:()=>unpin(run.id),jump:()=>jump(run.id)})):element("p",{className:"edge-pins-empty"},"Pin an answer to keep it here.")));
}
function ComposerResizeHandle({fieldRef,height,setHeight}) {
    const view=currentView,drag=cachedValue(view,"drag",()=>({cleanup:null}),[]);
    onLifecycle(view,"drag-cleanup",()=>()=>drag.cleanup?.(),[]);
    const bounds=()=>{const field=fieldRef.current,style=field&&getComputedStyle(field);
        const panel=field?.closest(".composer"),workspace=field?.closest(".research-workspace"),chrome=panel&&field?panel.getBoundingClientRect().height-field.getBoundingClientRect().height:0;
        return {field,min:parseFloat(style?.minHeight)||24,max:Math.max(parseFloat(style?.minHeight)||24,Math.min(innerHeight*.5,(workspace?.clientHeight??600)-chrome-110))};};
    const start=event=>{
        if(event.button!==0)return;
        const {field,min,max}=bounds();if(!field)return;
        event.preventDefault();drag.cleanup?.();
        const handle=event.currentTarget,pointer=event.pointerId,startY=event.clientY,startHeight=field.getBoundingClientRect().height;
        let next=startHeight;
        handle.setPointerCapture?.(pointer);
        const move=e=>{if(e.pointerId!==pointer)return;next=Math.round(Math.min(max,Math.max(min,startHeight+startY-e.clientY)));field.style.height=next+"px";handle.setAttribute("aria-valuenow",String(next));};
        const end=e=>{if(e.pointerId!==pointer)return;drag.cleanup?.();setHeight(next);};
        const oldSelect=document.body.style.userSelect;document.body.style.userSelect="none";handle.classList.add("dragging");
        drag.cleanup=()=>{document.removeEventListener("pointermove",move);document.removeEventListener("pointerup",end);document.removeEventListener("pointercancel",end);if(handle.hasPointerCapture?.(pointer))handle.releasePointerCapture(pointer);document.body.style.userSelect=oldSelect;handle.classList.remove("dragging");drag.cleanup=null;};
        document.addEventListener("pointermove",move);document.addEventListener("pointerup",end);document.addEventListener("pointercancel",end);
    };
    const key=event=>{if(event.key!=="ArrowUp"&&event.key!=="ArrowDown")return;event.preventDefault();
        const {field,min,max}=bounds();if(field)setHeight(Math.min(max,Math.max(min,field.getBoundingClientRect().height+(event.key==="ArrowUp"?24:-24))));};
    const {field,min,max}=bounds();
    return element("div",{className:"edge-composer-resizer",role:"separator","aria-orientation":"horizontal","aria-label":edgeUi().composerResize,title:edgeUi().composerResizeHint,tabIndex:0,"aria-valuemin":Math.round(min),"aria-valuemax":Math.round(max),"aria-valuenow":Math.round(field?.getBoundingClientRect().height??height??min),onPointerDown:start,onKeyDown:key});
}
// EXEC-DETAILS: press and drag the line between Pinned responses and Response History up or down (touch or mouse);
// arrow keys move it too
function PinsResizeHandle({height,setHeight}) {
    const view=currentView,drag=cachedValue(view,"drag",()=>({cleanup:null}),[]);
    const bounds=handle=>{const panel=handle.closest(".details-panel"),pins=panel?.querySelector(".edge-pins"),top=pins?.getBoundingClientRect().top??0;
        return {pins,min:90,max:Math.max(120,(panel?.getBoundingClientRect().bottom??600)-top-120)};};
    const start=event=>{
        if(event.button!==0)return;
        event.preventDefault();drag.cleanup?.();
        const handle=event.currentTarget,{pins,min,max}=bounds(handle),startY=event.clientY,startHeight=pins?.getBoundingClientRect().height??180;
        handle.setPointerCapture?.(event.pointerId);
        let next=startHeight;
        const move=e=>{next=Math.round(Math.min(max,Math.max(min,startHeight+e.clientY-startY)));if(pins){pins.style.flex=`0 0 ${next}px`;pins.style.height=`${next}px`;}};
        const end=()=>{drag.cleanup?.();setHeight(next);};
        const oldSelect=document.body.style.userSelect;document.body.style.userSelect="none";handle.classList.add("dragging");
        drag.cleanup=()=>{document.removeEventListener("pointermove",move);document.removeEventListener("pointerup",end);document.removeEventListener("pointercancel",end);document.body.style.userSelect=oldSelect;handle.classList.remove("dragging");drag.cleanup=null;};
        document.addEventListener("pointermove",move);document.addEventListener("pointerup",end);document.addEventListener("pointercancel",end);
    };
    const key=event=>{if(event.key!=="ArrowUp"&&event.key!=="ArrowDown")return;event.preventDefault();
        const {pins,min,max}=bounds(event.currentTarget),current=height??Math.round(pins?.getBoundingClientRect().height??180);
        setHeight(Math.min(max,Math.max(min,current+(event.key==="ArrowDown"?24:-24))));};
    return element("div",{className:"edge-pins-resizer",role:"separator","aria-orientation":"horizontal","aria-label":"Resize pinned responses",tabIndex:0,onPointerDown:start,onKeyDown:key});
}
function PinnedResponseCard({run,unpin,jump}) {
    const view=currentView,expanded=initialValue(view,"expanded",()=>false),setExpanded=next=>updateValue(view,"expanded",next);
    return element("div",{className:"edge-pin-card"},
        element("div",{className:"edge-pin-top"},element(Icon,{name:"pin"}),
            element("button",{className:"edge-pin-title",onClick:jump,title:run.result.title},run.result.title),
            element("button",{className:"small",onClick:()=>setExpanded(!expanded),"aria-expanded":expanded,"aria-label":"Expand pinned response"},element(DisclosureChevron)),
            element("button",{className:"small",onClick:unpin,"aria-label":"Unpin response"},"×")),
        expanded&&element("div",{className:"edge-pin-body"},element(Markdown,{text:run.result.condition}),element("button",{onClick:jump},"View full response →")));
}
function MessageClipboardActions({getText,kind}) {
 const view=currentView,status=initialValue(view,"clipboardStatus",()=>""),setStatus=next=>updateValue(view,"clipboardStatus",next);
 const copy=async event=>{const text=getText(event.currentTarget);try{
  if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
  else {const field=document.createElement("textarea");field.value=text;field.style.position="fixed";field.style.opacity="0";document.body.append(field);field.select();const ok=document.execCommand("copy");field.remove();if(!ok)throw new Error("Copy unavailable");}
  setStatus(edgeUi().copied);
 }catch(error){setStatus("Copy unavailable. Select the message and copy manually.");}};
 return element("span",{className:"message-clipboard-actions"},
  // EXEC-UI-1019B (user 2026-10-19 "'Copy AI response' --> Ini hanya 'Copy'"): the answer's copy button says Copy
  kind==="user"
   ?element("button",{className:"result-action clipboard-action",type:"button",onClick:copy,title:"Copy question","aria-label":"Copy question"},element(Icon,{name:"copy"}))
   :element("button",{className:"result-action clipboard-action with-label",type:"button",onClick:copy},element(Icon,{name:"copy"}),edgeUi().copy),
  element("span",{className:"clipboard-status",role:"status"},status));
}
function responseCopyText(button) {
 const article=button.closest('.result').cloneNode(true);
 article.querySelectorAll('.result-actions,.result-kicker,.result-metadata,button').forEach(node=>node.remove());
 return (article.innerText||Array.from(article.children).map(node=>node.textContent).join("\n\n")).trim();
}
// EXEC-SHARE-UI (user 2026-10-19: the share button in the answer's action row; "PDF dan PNG alright"; "masukan juga logo
// edge ... di pojok kiri atau kanan atas"): the answer as a card without EDGE's bars, composer or panels: the EDGE logo,
// the question, the answer with every table row and its assumptions and methodology open, and a footer (data date,
// request, not investment advice). PDF is the browser's print of the card alone (stage 1, no new dependency); PNG is
// drawn in the browser by html-to-image (MIT, static/html-to-image.js, loaded on first use because the CSP allows scripts
// from this origin only) at 540 CSS px and up to 2x, then shared with the Web Share API or downloaded.
// EXEC share card (user 2026-10-20: "Ya lanjutkan untuk pengerjaan kartu share"; .docx asli, PNG lebih tajam): A the logo
// inline (an outside image came out empty in a user's PNG), B a black question box, C no title, D the evidence line in
// black with its green check on the right, E Assumptions and Limitations closed, F no "Made by EDGE AI"; PNG at up to 3x;
// Word (.docx) from static/edge-docx.js, loaded on first use, with every section open.
const EDGE_LOGO_SVG = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 152 64\" width=\"152\" height=\"64\"><circle cx=\"32\" cy=\"32\" r=\"26\" fill=\"#030213\"/><path d=\"M25.15138671875 42.2146484375V21.7853515625H38.82119140625V25.254218750000003H29.33322265625V30.19015625H38.09451171875V33.6041796875H29.33322265625V38.74578125H38.848613281249996V42.2146484375Z\" fill=\"#FFFFFF\"/><path d=\"M68.197265625 42.905V21.078828125H82.376953125V24.3747265625H72.1083984375V30.2633984375H81.615234375V33.5153515625H72.1083984375V39.6091015625H82.435546875V42.905Z\" fill=\"#030213\"/><path d=\"M94.344140625 42.905H86.961328125V21.078828125H94.490625Q97.742578125 21.078828125 100.0716796875 22.3825390625Q102.40078125 23.68625 103.65322265625 26.1325390625Q104.9056640625 28.578828125 104.9056640625 31.9626171875Q104.9056640625 35.375703125 103.65322265625 37.82931640625Q102.40078125 40.2829296875 100.03505859375 41.59396484375Q97.6693359375 42.905 94.344140625 42.905ZM90.8724609375 39.5212109375H94.1537109375Q96.4388671875 39.5212109375 97.96962890625 38.67892578125Q99.500390625 37.836640625 100.2767578125 36.15939453125Q101.053125 34.4821484375 101.053125 31.9626171875Q101.053125 29.4723828125 100.2767578125 27.8024609375Q99.500390625 26.1325390625 97.99892578125 25.297578125Q96.4974609375 24.4626171875 94.25625 24.4626171875H90.8724609375Z\" fill=\"#030213\"/><path d=\"M118.64531249999999 43.19796875Q115.62773437499999 43.19796875 113.35722656249999 41.8356640625Q111.08671874999999 40.473359375 109.81230468749999 37.9684765625Q108.53789062499999 35.46359375 108.53789062499999 32.0212109375Q108.53789062499999 28.4909375 109.84892578124999 25.97873046875Q111.15996093749999 23.4665234375 113.41582031249999 22.12619140625Q115.67167968749999 20.785859375 118.52812499999999 20.785859375Q120.32988281249999 20.785859375 121.88994140624999 21.313203125Q123.44999999999999 21.840546875 124.67314453124999 22.81466796875Q125.89628906249999 23.7887890625 126.67998046874999 25.121796875Q127.46367187499999 26.4548046875 127.71269531249999 28.051484375H123.71367187499999Q123.44999999999999 27.172578125 122.98857421874999 26.4841015625Q122.52714843749999 25.795625 121.87529296874999 25.297578125Q121.22343749999999 24.79953125 120.39580078124999 24.54318359375Q119.56816406249999 24.2868359375 118.57207031249999 24.2868359375Q116.81425781249999 24.2868359375 115.42998046874999 25.180390625Q114.04570312499999 26.0739453125 113.25468749999999 27.7878125Q112.46367187499999 29.5016796875 112.46367187499999 31.9919140625Q112.46367187499999 34.4528515625 113.25468749999999 36.17404296875Q114.04570312499999 37.895234375 115.43730468749999 38.79611328125Q116.82890624999999 39.6969921875 118.65996093749999 39.6969921875Q120.32988281249999 39.6969921875 121.55302734374999 39.0524609375Q122.77617187499999 38.4079296875 123.44999999999999 37.22140625Q124.07988281249999 36.0934765625 124.10917968749999 34.5700390625H119.07011718749999V31.4938671875H127.90312499999999V34.1159375Q127.90312499999999 36.9137890625 126.70927734374999 38.95724609375Q125.51542968749999 41.000703125 123.42802734374999 42.0993359375Q121.34062499999999 43.19796875 118.64531249999999 43.19796875Z\" fill=\"#030213\"/><path d=\"M132.29707031249998 42.905V21.078828125H146.47675781249998V24.3747265625H136.20820312499998V30.2633984375H145.71503906249998V33.5153515625H136.20820312499998V39.6091015625H146.53535156249998V42.905Z\" fill=\"#030213\"/></svg>";
const EdgeShare = (() => {
  const WIDTH = 760, MAX_PIXELS = 16e6, MAX_RATIO = 3;  // EXEC-UI-1019B: wider, so text wraps less and the card is shorter  // the canvas area every phone browser draws (iOS Safari: 16,777,216)
  const DROP = ".result-actions,.result-metadata,.result-kicker,.edge-next,.edge-choices,.edge-choices-help,"
    + ".edge-table-more,.edge-table-tools,.message-clipboard-actions,.edge-plan-actions,script";
  const text = (tag, className, value) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = value; return node; };
  // the card's labels and dates are the interface's (English); the question and the answer keep their language
  const today = () => new Date().toLocaleDateString("en-GB", {day:"numeric", month:"long", year:"numeric"});
  const longDate = iso => { const [y, m, d] = String(iso).split("-").map(Number); return y && m && d ? new Date(y, m - 1, d).toLocaleDateString("en-GB", {day:"numeric", month:"long", year:"numeric"}) : String(iso); };
  // EXEC-UI-1019B (user 2026-10-19: the row under the answer's title, without the cost): Request, the model's logo, name
  // and level, tokens, duration; a logo drawn as a CSS mask becomes an image, which the PNG renderer draws
  const meta = source => {
    const row = source.querySelector(".result-metadata")?.cloneNode(true);
    if (!row) return null;
    row.className = "edge-share-meta";
    row.querySelectorAll(".edge-cost").forEach(node => node.remove());
    row.querySelectorAll(".edge-model-logo.mono").forEach(node => {
      const image = document.createElement("img");
      image.src = (node.style.getPropertyValue("--logo").match(/url\("?([^")]+)"?\)/) || [])[1] || "";
      image.alt = node.getAttribute("aria-label") || "";
      node.replaceWith(image);
    });
    row.querySelectorAll("[title]").forEach(node => node.removeAttribute("title"));
    return row;
  };
  const fileName = run => ("EDGE " + (run.result?.title || run.question || run.id)).replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  const inlineLogo = () => {
    const svg = document.importNode(new DOMParser().parseFromString(EDGE_LOGO_SVG, "image/svg+xml").documentElement, true);
    svg.setAttribute("height", "30"); svg.setAttribute("width", String(Math.round(30 * 152 / 64)));
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "EDGE"); svg.classList.add("edge-share-logo");
    return svg;
  };
  // notesOpen: Word has no folded sections, so Assumptions and Limitations are written out there
  const card = (run, {notesOpen = false} = {}) => {
    const source = document.getElementById(run.id + "-response");
    if (!source) return null;
    const ui = edgeUi(), info = EdgeView.shareInfo(run.raw);
    const root = document.createElement("div");
    root.className = "edge-share-card";
    const head = document.createElement("div");
    head.className = "edge-share-head";
    head.append(inlineLogo(), text("span", null, today()));
    const row = meta(source);
    const body = source.cloneNode(true);
    body.removeAttribute("id"); body.removeAttribute("tabindex");
    body.className = "edge-share-body";
    body.querySelectorAll(DROP).forEach(node => node.remove());
    [...body.children].filter(node => node.tagName === "H1").forEach(node => node.remove());
    body.querySelectorAll(".edge-evidence-line > svg").forEach(check => check.parentElement.append(check));
    body.querySelectorAll("details").forEach(node => { node.open = notesOpen || !node.matches(".edge-notes[data-section]"); });
    body.querySelectorAll("tr.edge-row-folded").forEach(row => row.classList.remove("edge-row-folded"));
    body.querySelectorAll("button").forEach(button => button.replaceWith(document.createTextNode(button.textContent)));
    body.querySelectorAll("[id]").forEach(node => node.removeAttribute("id"));
    const question = document.createElement("div");
    question.className = "edge-share-question";
    question.append(text("span", null, ui.shareQuestion), text("p", null, run.question || ""));
    const foot = document.createElement("div");
    foot.className = "edge-share-foot";
    [info.dataAsOf && ui.shareDataAsOf.replace("{date}", longDate(info.dataAsOf)), ui.shareRequest.replace("{id}", run.id),
      ui.shareFooter].filter(Boolean).forEach(line => foot.append(text("span", null, line)));
    root.append(...[head, row, question, body, foot].filter(Boolean));
    return root;
  };
  const stage = node => { const holder = document.createElement("div"); holder.className = "edge-share-stage"; holder.append(node); document.body.append(holder); return holder; };
  const pdf = run => {
    const node = card(run);
    if (!node) return false;
    const holder = stage(node), title = document.title;
    let cleaned = false;
    const done = () => { if (cleaned) return; cleaned = true; document.body.classList.remove("edge-share-printing"); document.title = title; holder.remove(); };
    document.body.classList.add("edge-share-printing");
    document.title = fileName(run);  // the name the browser offers for "Save as PDF"
    addEventListener("afterprint", done, {once:true});
    window.print();
    // a phone browser may return before its print sheet closes and send no afterprint: tidy up when the page is back
    setTimeout(() => addEventListener("focus", done, {once:true}), 1000);
    return true;
  };
  let loading = null;
  const library = () => window.htmlToImage ? Promise.resolve(window.htmlToImage) : (loading ??= new Promise((ok, fail) => {
    const script = document.createElement("script");
    script.src = "/html-to-image.js";
    script.onload = () => window.htmlToImage ? ok(window.htmlToImage) : fail(new Error("html-to-image missing"));
    script.onerror = () => { loading = null; fail(new Error("html-to-image unavailable")); };
    document.head.append(script);
  }));
  const download = file => {
    const link = document.createElement("a"), url = URL.createObjectURL(file);
    link.href = url; link.download = file.name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  };
  const png = async run => {
    const node = card(run);
    if (!node) return "missing";
    const holder = stage(node);
    try {
      const draw = await library();
      await document.fonts?.ready;
      const ratio = Math.max(1, Math.min(MAX_RATIO, Math.sqrt(MAX_PIXELS / (WIDTH * Math.max(node.offsetHeight, 1)))));
      // skipFonts: the web font lives on another origin the CSP does not let the page fetch; the system font draws it
      const blob = await draw.toBlob(node, {pixelRatio:ratio, backgroundColor:"#ffffff", skipFonts:true});
      if (!blob || !blob.size) throw new Error("empty image");
      const file = new File([blob], fileName(run) + ".png", {type:"image/png"});
      if (navigator.canShare?.({files:[file]})) {
        try { await navigator.share({files:[file], title:fileName(run)}); return "shared"; }
        catch (error) { if (error?.name === "AbortError") return "cancelled"; }  // otherwise the file is downloaded
      }
      download(file);
      return "downloaded";
    } finally {
      holder.remove();
    }
  };
  let docxLoading = null;
  const docxLibrary = () => window.EdgeDocx ? Promise.resolve(window.EdgeDocx) : (docxLoading ??= new Promise((ok, fail) => {
    const script = document.createElement("script");
    script.src = "/edge-docx.js";
    script.onload = () => window.EdgeDocx ? ok(window.EdgeDocx) : fail(new Error("edge-docx missing"));
    script.onerror = () => { docxLoading = null; fail(new Error("edge-docx unavailable")); };
    document.head.append(script);
  }));
  // the logo as PNG bytes for Word (Word draws no SVG without a PNG fallback), drawn at 3x from the inline SVG
  const logoPng = () => new Promise(resolve => {
    const image = new Image(), width = 71, height = 30;
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width * 3; canvas.height = height * 3;
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(blob => blob ? blob.arrayBuffer().then(buffer => resolve({bytes:new Uint8Array(buffer), width, height}))
        : resolve(null), "image/png");
    };
    image.onerror = () => resolve(null);
    image.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(EDGE_LOGO_SVG);
  });
  const docx = async run => {
    const node = card(run, {notesOpen:true});
    if (!node) return "missing";
    const [builder, logo] = await Promise.all([docxLibrary(), logoPng()]);
    const pick = selector => node.querySelector(selector);
    const blob = builder.build({logo, date:pick(".edge-share-head span")?.textContent || today(),
      meta:[...(pick(".edge-share-meta")?.children || [])].map(span => span.textContent.replace(/\s+/g, " ").trim())
        .filter(Boolean).join("  ·  "),
      questionLabel:edgeUi().shareQuestion, question:run.question || "", body:pick(".edge-share-body"),
      foot:[...node.querySelectorAll(".edge-share-foot span")].map(span => span.textContent)});
    download(new File([blob], fileName(run) + ".docx", {type:blob.type}));
    return "downloaded";
  };
  return {card, pdf, png, docx};
})();
// MONITOR-REVAMP (user 2026-10-30, AI_revamp.html navShare): with an icon title, the same menu opens from an icon
// button (the sidebar's Share, for the conversation's latest answer)
function ShareAction({run,iconTitle}) {
 const view=currentView,ui=edgeUi();
 const open=initialValue(view,"shareOpen",()=>false),setOpen=next=>updateValue(view,"shareOpen",next);
 const status=initialValue(view,"shareStatus",()=>""),setStatus=next=>updateValue(view,"shareStatus",next);
 // the sidebar clips what overflows it, so the icon button's menu is placed on the page under the button
 const at=initialValue(view,"shareAt",()=>null),setAt=next=>updateValue(view,"shareAt",next);
 const pick=async kind=>{setOpen(false);
  if(kind==="pdf"){EdgeShare.pdf(run);return;}
  setStatus(kind==="docx"?ui.shareWordPreparing:ui.sharePreparing);
  try{await (kind==="docx"?EdgeShare.docx(run):EdgeShare.png(run));setStatus("");}
  catch(error){setStatus(kind==="docx"?ui.shareWordFailed:ui.shareFailed);}};
 return element("span",{className:"edge-share-anchor"},
  iconTitle?element("button",{className:`icon-btn ${open?"selected":""}`,type:"button",title:iconTitle,"aria-label":iconTitle,"aria-haspopup":"menu","aria-expanded":Boolean(open),onClick:event=>{const r=event.currentTarget.getBoundingClientRect();setAt({top:r.bottom+6,left:Math.max(8,Math.min(r.left,innerWidth-236))});setOpen(!open);}},element(Icon,{name:"share"}))
   :element("button",{className:"result-action",type:"button","aria-haspopup":"menu","aria-expanded":Boolean(open),onClick:()=>setOpen(!open)},element(Icon,{name:"share"}),ui.share),
  open&&element("div",{className:"edge-share-menu",role:"menu","aria-label":ui.share,style:iconTitle&&at?{position:"fixed",top:at.top+"px",left:at.left+"px"}:undefined},
   element("div",{className:"edge-menu-title","aria-hidden":"true"},ui.shareTitle),
   element("button",{type:"button",role:"menuitem",onClick:()=>pick("pdf")},element(Icon,{name:"download"}),ui.sharePdf),
   element("button",{type:"button",role:"menuitem",onClick:()=>pick("png")},element(Icon,{name:"download"}),ui.sharePng),
   element("button",{type:"button",role:"menuitem",onClick:()=>pick("docx")},element(Icon,{name:"download"}),ui.shareWord)),
  status&&element("span",{className:"clipboard-status",role:"status"},status));
}
function ResponseActions({run,togglePin,artifacts=[],carry=null}) {
 const ui=edgeUi();
 return element("div",{className:"result-actions"},element("button",{className:"result-action",onClick:togglePin,"aria-pressed":Boolean(run.pinned)},element(Icon,{name:"pin"}),run.pinned?"Pinned":"Pin"),element(MessageClipboardActions,{getText:responseCopyText,kind:"ai"}),element(ShareAction,{run}),
  // EXEC-ASK-BRANCH (user 2026-10-24): continue this answer in a new tab, or ask about it in a side chat
  carry&&element("button",{className:"result-action edge-branch-action",title:ui.branchHint,onClick:carry.branch},element(Icon,{name:"branch"}),ui.branch),
  carry&&element("button",{className:"result-action edge-ask-action",title:ui.askHint,onClick:()=>carry.ask()},element(Icon,{name:"chat"}),carry.side?ui.sideChat.replace("{n}",String(carry.side.questions)):ui.askAboutShort),
  artifacts.map(file=>{const href=Edge.exportUrl(file.id);return href&&element("a",{className:"result-action",href},element(FileTypeIcon,{label:file.label}),"Download "+file.label);}));
}
// EXEC-X (M124): the answer view renders the view model of static/edge-view.js (EdgeView.toView), the only code that
// reads Orc's response; words come from static/edge-labels.js. Text from the AI becomes DOM nodes through element()
// only (never innerHTML). A field the view does not know yet still shows, readably named, through the generic view.
const edgeFormat = () => EdgeView.format;
const edgeUi = () => EdgeLabels.ui;
function edgeVerdict(verdict) {
  // MONITOR-REVAMP: the Design Spec pill (solid fill, a dot, the label)
  return element("span", {className:`edge-badge ${verdict.tone}`, title:verdict.code}, element("i", {className:"edge-badge-dot", "aria-hidden":"true"}), verdict.label);
}
// MONITOR-REVAMP (AI_revamp.html fmtTok): a token count as 900, 12K or 1.25M
const edgeTokens = n => typeof n !== "number" || !Number.isFinite(n) ? String(n ?? "") : n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n);

// EXEC-IMPL-1017 Fase 3 (user 2026-10-16: "select as context ... fungsinya klik kanan kayak claude"; "di ponsel memakai
// tombol mengambang"): on text selected in an answer, a right click opens EDGE's menu (Copy, Attach selection as
// context); on a touch screen a small bar floats under the selection. The menu lives outside the app's view tree and
// builds its buttons with textContent only. Attaching sends the passage with the value reference of every figure and
// table cell inside it (data-fig-ref) to the composer.
const EdgeSelection = (() => {
  let menu = null, timer = null;
  const close = () => { if (menu) { menu.remove(); menu = null; } };
  const current = () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    const range = selection.getRangeAt(0), base = range.commonAncestorContainer;
    const node = base.nodeType === 1 ? base : base.parentElement;
    const article = node?.closest?.("article.result");
    const text = selection.toString().trim();
    return article && text ? {range, article, text} : null;
  };
  const build = ({range, article, text}) => {
    const figures = [...article.querySelectorAll("[data-fig-ref]")].filter(node => range.intersectsNode(node))
      .map(node => ({ref:node.getAttribute("data-fig-ref"), shown:node.textContent.trim()}));
    const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
    const section = start?.closest?.("[data-section]")?.getAttribute("data-section") || "OTHER";
    return EdgeView.textSelection({requestId:article.id.replace(/-response$/, ""), section, quote:text, figures});
  };
  const show = (x, y, info, floating) => {
    close();
    const ui = edgeUi();
    menu = document.createElement("div");
    menu.className = "edge-selection-menu" + (floating ? " floating" : "");
    menu.setAttribute("role", "menu");
    // MONITOR-REVAMP (AI_revamp.html selection menu): each item starts with its icon (copy, reply, chat)
    const GLYPHS = {copy:'<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
      reply:'<path d="M9 14 4 9l5-5M4 9h11a5 5 0 0 1 5 5v6"/>', chat:'<path d="M21 12a8 8 0 0 1-11.5 7.2L4 21l1.8-5.5A8 8 0 1 1 21 12z"/>'};
    const item = (label, run, glyph) => {
      const button = document.createElement("button");
      button.type = "button"; button.setAttribute("role", "menuitem");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "icon"); svg.setAttribute("aria-hidden", "true");
      svg.innerHTML = GLYPHS[glyph] || ""; button.append(svg, document.createTextNode(label));
      button.addEventListener("mousedown", event => event.preventDefault());
      button.addEventListener("click", () => { run(); close(); });
      menu.appendChild(button);
    };
    item(ui.selectionCopy, () => navigator.clipboard?.writeText(info.text).catch(() => {}), "copy");
    item(ui.selectionAttach, () => {
      window.dispatchEvent(new CustomEvent("edge-attach", {detail:build(info)}));
      window.getSelection()?.removeAllRanges();
    }, "reply");
    // EXEC-ASK-BRANCH: the passage opens the answer's side chat, attached there (not inside the side chat itself)
    if (!document.documentElement.classList.contains("edge-side-view")) item(ui.selectionAsk, () => {
      window.dispatchEvent(new CustomEvent("edge-ask", {detail:build(info)}));
      window.getSelection()?.removeAllRanges();
    }, "chat");
    document.body.appendChild(menu);
    menu.style.left = Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8)) + "px";
    menu.style.top = Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8)) + "px";
  };
  const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  if (typeof document !== "undefined") {
    document.addEventListener("contextmenu", event => {
      const info = current();
      if (!info || !info.range.intersectsNode(event.target)) { close(); return; }
      event.preventDefault();
      show(event.clientX, event.clientY, info, false);
    });
    document.addEventListener("selectionchange", () => {
      if (!coarse()) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        const info = current();
        if (!info) { close(); return; }
        const box = info.range.getBoundingClientRect();
        const below = box.bottom + 12, visible = box.bottom > 0 && below < innerHeight - 140;
        show(visible ? box.left : 16, visible ? below : innerHeight - 150, info, true);
      }, 350);
    });
    document.addEventListener("mousedown", event => { if (menu && !menu.contains(event.target)) close(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
  }
  return {close};
})();

// EXEC-UI-1024 2a (user 2026-10-24: attached text "disorot kuning"): each attached passage is marked in its own answer
// with the CSS Custom Highlight API, so the answer's DOM is never changed. The passage is found again from its text
// (spaces ignored, as the selection's text and the page's text break lines differently); a browser without the API
// shows no mark and the attachment works as before.
const EdgeHighlight = (() => {
  const NAME = "edge-attached";
  const rangeOf = (root, quote) => {
    const wanted = String(quote || "").replace(/\s+/g, "");
    if (!root || !wanted) return null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const map = []; let text = "";
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const value = node.nodeValue;
      for (let i = 0; i < value.length; i++) if (!/\s/.test(value[i])) { text += value[i]; map.push([node, i]); }
    }
    const at = text.indexOf(wanted);
    if (at < 0) return null;
    const [startNode, startOffset] = map[at], [endNode, endOffset] = map[at + wanted.length - 1];
    const range = document.createRange();
    range.setStart(startNode, startOffset); range.setEnd(endNode, endOffset + 1);
    return range;
  };
  const show = items => {
    if (typeof CSS === "undefined" || !CSS.highlights || typeof Highlight !== "function") return 0;
    const ranges = (items || []).filter(item => item && item.kind === "TEXT" && item.request_id)
      .map(item => rangeOf(document.getElementById(item.request_id + "-response"), item.quote)).filter(Boolean);
    if (ranges.length) CSS.highlights.set(NAME, new Highlight(...ranges)); else CSS.highlights.delete(NAME);
    return ranges.length;
  };
  return {show, rangeOf, NAME};
})();

// ---- Markdown: blocks, then inline spans; anything else stays plain text ----
const MD_INLINE = [
  ["code", /`([^`\n]+)`/],
  ["link", /\[([^\]\n]+)\]\(([^)\s]+)\)/],
  ["strong", /\*\*(?=\S)([\s\S]+?)\*\*|(?<![\w])__(?=\S)([\s\S]+?)__(?![\w])/],
  ["em", /\*(?=[^\s*])([^*\n]+?)\*|(?<![\w])_(?=[^\s_])([^_\n]+?)_(?![\w])/]
];
// EXEC-IMPL-1017 Fase 3: the answer's figures (Orc's answer_figures, in order) become spans that carry their value
// reference, so a selected passage knows where each of its figures comes from. A figure is matched as a whole number
// (no digit or decimal mark next to it); one Orc lists but the text no longer shows is skipped
const MD_FIGURE_EDGE = /[\d.,]/;
function mdFigures(text, ctx) {
  const queue = ctx?.figures;
  if (!queue || queue.next >= queue.list.length) return [text];
  const out = [];
  let rest = String(text);
  const find = shown => {
    for (let from = 0; ; ) {
      const at = rest.indexOf(shown, from);
      if (at < 0) return -1;
      const before = at ? rest[at - 1] : "", after = rest[at + shown.length] ?? "";
      if (!(/\d/.test(shown[0]) && MD_FIGURE_EDGE.test(before)) && !(/\d/.test(shown.at(-1)) && /\d/.test(after))) return at;
      from = at + 1;
    }
  };
  while (rest && queue.next < queue.list.length) {
    let hit = -1, at = -1;
    for (let k = queue.next; k < Math.min(queue.list.length, queue.next + 4); k++) {
      const shown = String(queue.list[k]?.shown || "");
      const found = shown ? find(shown) : -1;
      if (found >= 0) { hit = k; at = found; break; }
    }
    if (hit < 0) break;
    const figure = queue.list[hit];
    if (at) out.push(rest.slice(0, at));
    out.push(element("span", {className:"edge-fig", "data-fig-ref":figure.ref}, figure.shown));
    rest = rest.slice(at + figure.shown.length);
    queue.next = hit + 1;
  }
  if (rest) out.push(rest);
  return out;
}
function mdInline(text, ctx) {
  const out = [];
  let rest = String(text);
  while (rest) {
    let best = null;
    for (const [kind, pattern] of MD_INLINE) {
      const match = pattern.exec(rest);
      if (match && (!best || match.index < best.match.index)) best = {kind, match};
    }
    if (!best) { out.push(...mdFigures(rest, ctx)); break; }
    const {kind, match} = best, inner = match[1] ?? match[2];
    if (match.index) out.push(...mdFigures(rest.slice(0, match.index), ctx));
    if (kind === "code") out.push(element("code", null, inner));
    else if (kind === "link") {
      const href = Edge.safeUrl(match[2]);
      out.push(href ? element("a", {href, target:"_blank", rel:"noopener noreferrer"}, mdInline(inner, ctx)) : match[0]);
    } else if (kind === "strong") out.push(element("strong", null, mdInline(inner, ctx)));
    else {
      // P17: an italic span the backend marked as an unsupported claim carries its note
      const note = ctx?.claims?.get(inner.trim());
      out.push(note ? element("em", {className:"edge-claim", tabIndex:0, title:note, "aria-label":`${inner} (${edgeUi().claimNote}: ${note})`}, mdInline(inner, ctx)) : element("em", null, mdInline(inner, ctx)));
    }
    rest = rest.slice(match.index + match[0].length);
  }
  return out;
}
const MD_LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const MD_RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
// a date or a year as a label: "31 Mei 2024", "Mei 2024", "2024-05-31", "31/05/2024", "2019", "Q1 2024"
const MD_DATE = /^(?:\d{1,2}\s+\p{L}{3,}\.?\s+\d{4}|\p{L}{3,}\.?\s+\d{4}|\d{4}-\d{2}(?:-\d{2})?|\d{1,2}[\/.]\d{1,2}[\/.]\d{2,4}|(?:19|20)\d{2}|Q[1-4]\s+\d{4}|\d{4}\s+Q[1-4]|\d{1,2}\s+\p{L}{3,}\.?)$/u;
const MD_NUMERIC = /^[\s\d.,%+\-−–×x\[\];:()p=<>≥≤±$]*\d[\s\d.,%+\-−–×x\[\];:()p=<>≥≤±$]*$/;
const MD_TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const mdCells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
function mdList(lines, start, ctx) {
  const indent = lines[start].match(MD_LIST)[1].length, ordered = /\d/.test(lines[start].match(MD_LIST)[2]);
  const items = [];
  let index = start;
  while (index < lines.length) {
    const match = lines[index].match(MD_LIST);
    if (!match || match[1].length < indent) break;
    if (match[1].length > indent && items.length) {
      const nested = mdList(lines, index, ctx);
      items.at(-1).push(nested.node);
      index = nested.next;
      continue;
    }
    const item = [mdInline(match[3], ctx)];
    index++;
    while (index < lines.length && lines[index].trim() && !MD_LIST.test(lines[index]) && /^\s{2,}/.test(lines[index])) item.push(element("br"), mdInline(lines[index++].trim(), ctx));
    items.push(item);
  }
  return {node:element(ordered ? "ol" : "ul", null, items.map(children => element("li", null, children))), next:index};
}
// V4 (user 2026-10-14, iPhone: "pencet kembali malah send message"): on a touch device Enter (Return) adds a line and
// the send button sends; with a mouse or trackpad Enter sends and Shift+Enter adds a line
function touchKeyboard() {
  return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches && !matchMedia("(any-pointer: fine)").matches;
}
// EXEC-FASTLANE V5 (user 2026-10-14; a month "September 2024"; a year "2020", not "2.020"): dates in an answer are
// written out; code, links and times are left as they are. User 2026-10-30 ("format date ... DD MMMM YYYY", chose
// "19 October 2026"): every answer, whatever its lane, with the month in English like the rest of the page
const FAST_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const FAST_DAY = /(?<![\w/.:-])(\d{4})-(\d{2})-(\d{2})(?![\w/-]|:\d)/g;
const FAST_MONTH = /(?<![\w/.:-])(\d{4})-(\d{2})(?![\w/-]|:\d)/g;
function fastDatePart(part) {
  return part.replace(FAST_DAY, (all, y, m, d) => +m >= 1 && +m <= 12 && +d >= 1 && +d <= 31 ? `${+d} ${FAST_MONTHS[+m - 1]} ${y}` : all)
    .replace(FAST_MONTH, (all, y, m) => +m >= 1 && +m <= 12 ? `${FAST_MONTHS[+m - 1]} ${y}` : all);
}
function fastDates(text) {
  // fenced blocks and inline code keep their text; a link target (](...)) and a bare URL too
  return String(text ?? "").split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`|\]\([^)\s]*\)|https?:\/\/\S+)/g)
    .map((part, index) => index % 2 ? part : fastDatePart(part)).join("");
}
const FAST_YEAR_HEAD = /^(tahun|year|thn)\b/i;
const FAST_GROUPED_YEAR = /^(\*\*)?([12])\.(\d{3})(\*\*)?$/;
function fastYearCell(cell) {
  const m = String(cell ?? "").trim().match(FAST_GROUPED_YEAR);
  return m && +(m[2] + m[3]) >= 1900 && +(m[2] + m[3]) <= 2100 ? `${m[1] ?? ""}${m[2]}${m[3]}${m[4] ?? ""}` : cell;
}
function renderMarkdown(text, ctx = {}) {
  if (!ctx.datesDone) { text = fastDates(text); ctx = {...ctx, datesDone:true}; }
  const lines = String(text ?? "").replace(/\r\n?/g, "\n").split("\n"), blocks = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    const fence = line.match(/^\s*(```|~~~)/);
    if (fence) {
      const body = [];
      index++;
      while (index < lines.length && !lines[index].trim().startsWith(fence[1])) body.push(lines[index++]);
      index++;
      blocks.push(element("pre", {className:"edge-md-code"}, element("code", null, body.join("\n"))));
      continue;
    }
    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) { blocks.push(element(heading[1].length <= 2 ? "h3" : "h4", {className:"edge-md-heading"}, mdInline(heading[2], ctx))); index++; continue; }
    if (MD_RULE.test(line)) { blocks.push(element("hr")); index++; continue; }
    if (line.includes("|") && index + 1 < lines.length && MD_TABLE_SEP.test(lines[index + 1]) && lines[index + 1].includes("-")) {
      // V4 (user 2026-10-14): the expanded table's title is the label line right above it ("**Tabel X**", "...:"),
      // else the nearest heading above it in the same section (not past an earlier table)
      let above = index - 1;
      while (above >= 0 && !lines[above].trim()) above--;
      const label = above >= 0 ? lines[above].trim() : "";
      let title = (/^\*\*[^*]+\*\*:?$/.test(label) || (label.endsWith(":") && label.length <= 120)) ? label : "";
      for (let back = above; !title && back >= 0 && !MD_TABLE_SEP.test(lines[back]); back--) {
        const found = lines[back].match(/^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/);
        if (found) title = found[1];
      }
      const head = mdCells(line), align = mdCells(lines[index + 1]).map(cell => cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : null);
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) rows.push(mdCells(lines[index++]));
      head.forEach((name, column) => { if (FAST_YEAR_HEAD.test(name.replace(/[*_`]/g, "").trim())) rows.forEach(row => { if (column < row.length) row[column] = fastYearCell(row[column]); }); });
      // a column's alignment as written; otherwise one alignment per column (Fase 5 QA 2026-10-09: "211" right and
      // "Rp 83,27 triliun" left in one column): figures right when every cell of the column is one, words left
      const figure = value => MD_NUMERIC.test(value) || (/\d/.test(value) && value.length <= 40 && value.trim().split(/\s+/).length <= 5);
      // EXEC-TABLE-ALIGN (user 2026-10-16, "seragamkan ... sesuai jenis teks"): a column of quantities (numbers,
      // percents, amounts) is right-aligned with its title; text, codes, dates and years stay left. Decided from the
      // cells, never from the alignment a writer typed, so every table reads the same way
      const numeric = head.map((_, column) => { const values = rows.map(row => (row[column] ?? "").replace(/[*_`]/g, "").trim()).filter(Boolean); return values.length > 0 && values.every(figure) && !values.every(value => MD_DATE.test(value)); });
      ctx.tableCount = (ctx.tableCount || 0) + 1;
      // EXEC-IMPL-1016 Fase 4.2: a table Orc built from a table instruction can be attached to the next question
      // the table download (user 2026-10-20): a table Orc kept can be downloaded whole as Excel
      const found = ctx.attach || ctx.conversationId ? EdgeView.tableSource(ctx.tables, head, rows.length, ctx.usedTables || []) : null;
      const source = ctx.attach ? found : null;
      const download = ctx.conversationId && /^out_[0-9a-f]{24}$/.test(found?.output_id || "") ? {conversationId:ctx.conversationId, table:found} : null;
      blocks.push(element(MdTable, {key:`t${ctx.tableCount}-${mdHash(line + "\n" + rows.map(row => row.join("|")).join("\n"))}`, head, align, rows, numeric, ctx, source, download,
        title:title.replace(/[*_`]/g, "").replace(/:$/, "").trim()}));
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quoted = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) quoted.push(lines[index++].replace(/^\s*>\s?/, ""));
      blocks.push(element("blockquote", null, renderMarkdown(quoted.join("\n"), ctx)));
      continue;
    }
    if (MD_LIST.test(line)) { const list = mdList(lines, index, ctx); blocks.push(list.node); index = list.next; continue; }
    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !MD_LIST.test(lines[index]) && !/^\s*(#{1,6}\s|>|```|~~~)/.test(lines[index]) && !MD_RULE.test(lines[index])
           && !(lines[index].includes("|") && index + 1 < lines.length && MD_TABLE_SEP.test(lines[index + 1]))) paragraph.push(lines[index++]);
    blocks.push(element("p", null, paragraph.flatMap((part, i) => i ? [element("br"), mdInline(part, ctx)] : [mdInline(part, ctx)])));
  }
  return blocks;
}
// ---- EXEC-SORT (user 2026-10-12): a table in an answer sorts by a click on its column title ----
// first click descending, second ascending, third the original order; the look of the table is unchanged
const SORT_SCALE = {ribu:1e3, rb:1e3, juta:1e6, jt:1e6, miliar:1e9, milyar:1e9, triliun:1e12};
const SORT_MONTHS = {jan:0, feb:1, mar:2, apr:3, mei:4, may:4, jun:5, jul:6, agu:7, agt:7, aug:7, sep:8, okt:9, oct:9, nov:10, des:11, dec:11};
const SORT_NUMBER = /^([+-])?\s*(?:rp\.?\s*)?([+-])?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s*(%|pp|kali|x)?\s*([a-z]+)?\.?$/i;
const SORT_TOTAL = /^(total|jumlah|rata-rata keseluruhan)\b/i;
const sortCollator = new Intl.Collator("id", {numeric:true, sensitivity:"base"});
function mdHash(text) { let h = 0; for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }
function sortValue(raw) {
  const text = String(raw ?? "").replace(/[*_`]/g, "").replace(/\u00a0/g, " ").replace(/[\u2212\u2013\u2014]/g, "-").trim();
  if (!text || /^-+$/.test(text)) return {kind:"empty"};  // EXEC-TABLE: a dash marks a missing value
  let m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return {kind:"date", value:Date.UTC(+m[1], +m[2] - 1, +m[3])};
  m = text.match(/^(\d{1,2})\s+([a-z]{3})[a-z]*\.?\s+(\d{4})$/i);
  if (m && m[2].toLowerCase() in SORT_MONTHS) return {kind:"date", value:Date.UTC(+m[3], SORT_MONTHS[m[2].toLowerCase()], +m[1])};
  m = text.match(/^([a-z]{3})[a-z]*\.?\s+(\d{4})$/i);  // V5: a month written out ("September 2024")
  if (m && m[1].toLowerCase() in SORT_MONTHS) return {kind:"date", value:Date.UTC(+m[2], SORT_MONTHS[m[1].toLowerCase()], 1)};
  m = text.match(/^(\d{4})-(\d{2})$/);
  if (m) return {kind:"date", value:Date.UTC(+m[1], +m[2] - 1, 1)};
  m = text.match(SORT_NUMBER);
  if (m && (!m[6] || m[6].toLowerCase() in SORT_SCALE)) {
    let value = Number(m[3].replace(/\./g, "") + (m[4] ? "." + m[4] : "")) * (SORT_SCALE[(m[6] || "").toLowerCase()] || 1);
    if ((m[1] || m[2]) === "-") value = -value;
    return {kind:"number", value};
  }
  return {kind:"text", value:text};
}
// V4 (user 2026-10-14): a table opened wide, drawn by the app root beside the other dialogs (inside the answer the
// top bar and the composer stayed above it on a phone)
let edgeTableDialog = null;
function openTableDialog(spec) { edgeTableDialog = spec; refresh(); }
function closeTableDialog() { edgeTableDialog = null; refresh(); }
function TableDialog({spec}) {
  return element(DialogShell, {title:spec.title, description:spec.description, close:closeTableDialog,
    className:"edge-table-dialog", returnFocusRef:spec.returnFocusRef},
    element("div", {className:"edge-table-dialog-body edge-md-table"}, element(MdTable, {...spec.table, plain:true})));
}
const TABLE_VISIBLE_ROWS = 10;
const TABLE_SHORT_CELL = 16;  // characters: a cell this short reads as a code, date or number
const TABLE_TITLE_LINE = 14;  // characters: a longer column title wraps at 14ch (EXEC-UI-1019B "label width >X maka teks di wrapped"; was 28)
// The table download (user 2026-10-20: "tambah ICON download ... excel", "Ok gapapa"): Orc writes every row of the
// kept table with the columns and titles shown here, the definition sheet and the input sheets; the file then downloads
const TABLE_DOWNLOAD_NOTE_MS = 6000;
function downloadTableColumns(table) {
  const columns = [], titles = [];
  (table.columns || []).forEach((column, index) => {
    if (typeof column === "string" && column && !columns.includes(column)) { columns.push(column); titles.push(String(table.titles?.[index] ?? column).slice(0, 200)); }
  });
  return {columns:columns.slice(0, 60), titles:titles.slice(0, 60)};
}
async function downloadTable(view, download) {
  if (view.state.download === "preparing") return;
  updateValue(view, "download", "preparing");
  try {
    const {columns, titles} = downloadTableColumns(download.table);
    const file = await Edge.exportTable(download.conversationId, download.table.output_id, columns, titles);
    const url = Edge.exportUrl(file.export_id);
    if (!url) throw new Error("EXPORT_FAILED");
    const link = document.createElement("a");
    link.href = url; link.download = file.file_name || ""; link.rel = "noopener";
    document.body.append(link); link.click(); link.remove();
    updateValue(view, "download", null);
  } catch (error) {
    const state = (error?.code ?? error?.message) === "EXPORT_IN_PROGRESS" ? "busy" : "failed";
    updateValue(view, "download", state);
    setTimeout(() => { if (view.state.download === state) updateValue(view, "download", null); }, TABLE_DOWNLOAD_NOTE_MS);
  }
}
function MdTable({head, align, rows, numeric, ctx, title = "", plain = false, initialSort = null, source = null, download = null}) {
  const view = currentView;
  // EXEC-IMPL-1017 Fase 3 (user 2026-10-16: "tanpa ada menu tambahan"): a table has no attach controls; its cells carry
  // their value reference and are attached by selecting them (right click, or the bar on a phone)
  ctx = ctx ? {...ctx, figures:null} : ctx;
  const sort = initialValue(view, "sort", () => initialSort ?? ({column:null, dir:null}));
  const expandRef = initialValue(view, "expandRef", () => ({current:null}));
  const setSort = next => updateValue(view, "sort", next);
  const indexed = rows.map((row, index) => ({row, index}));
  const pinned = indexed.filter(item => SORT_TOTAL.test(String(item.row[0] ?? "").replace(/[*_`]/g, "").trim()));
  const free = indexed.filter(item => !pinned.includes(item));
  const kinds = head.map((_, column) => {
    const found = new Set(free.map(item => sortValue(item.row[column]).kind).filter(kind => kind !== "empty"));
    return found.size === 1 && (found.has("number") || found.has("date")) ? [...found][0] : "text";
  });
  const compare = (a, b, column, dir) => {
    const x = sortValue(a.row[column]), y = sortValue(b.row[column]);
    if (x.kind === "empty" || y.kind === "empty") return x.kind === y.kind ? a.index - b.index : x.kind === "empty" ? 1 : -1;
    const result = kinds[column] !== "text" && typeof x.value === "number" && typeof y.value === "number"
      ? x.value - y.value : sortCollator.compare(String(x.value), String(y.value));
    return result === 0 ? a.index - b.index : (dir === "ascending" ? result : -result);
  };
  const ordered = sort.column == null ? free : [...free].sort((a, b) => compare(a, b, sort.column, sort.dir));
  const next = column => sort.column !== column ? {column, dir:"descending"} : sort.dir === "descending" ? {column, dir:"ascending"} : {column:null, dir:null};
  // EXEC-UI-1015D (user 2026-10-15, "jarak antara kolom tidak compact"): a column whose cells are all short (codes,
  // dates, numbers) never wraps; a longer text column wraps between words within a readable width (CSS)
  const shortColumn = head.map((_, column) => numeric[column] || kinds[column] !== "text"
    || free.every(item => String(item.row[column] ?? "").replace(/[*_`]/g, "").trim().length <= TABLE_SHORT_CELL));
  const cellProps = (column, extra = {}) => {
    const classes = [extra.className, numeric[column] ? "num" : null, shortColumn[column] ? "edge-col-short" : "edge-col-text"].filter(Boolean).join(" ");
    return {...extra, className:classes};
  };
  const header = (value, column) => {
    const active = sort.column === column;
    const long = String(value).replace(/[*_`]/g, "").trim().length > TABLE_TITLE_LINE;
    return element("th", cellProps(column, {className:`edge-sortable${active ? " sorted" : ""}${long ? " edge-title-long" : ""}`, "aria-sort":active ? sort.dir : "none"}),
      element("button", {type:"button", className:"edge-sort", onClick:() => setSort(next(column)),
        "aria-label":`${String(value).replace(/[*_`]/g, "")}: ${active && sort.dir === "descending" ? edgeUi().sortAscending : active ? edgeUi().sortRestore : edgeUi().sortDescending}`},
        element("span", {className:"edge-sort-label"}, mdInline(value, ctx),
          element("span", {className:"edge-sort-icon"}, element(Icon, {name:active ? (sort.dir === "descending" ? "arrow-down" : "arrow-up") : "sort-arrows", size:13})))));
  };
  // EXEC-UI-1015 U4 (user 2026-10-15): an answer table shows its first rows in the current order, the rest fold behind
  // a button; a total row stays visible, sorting reorders every row, and the wide dialog and print show them all
  const folds = !plain && free.length > TABLE_VISIBLE_ROWS;
  const showAll = initialValue(view, "showAll", () => false);
  const folded = item => folds && !showAll && !pinned.includes(item) && ordered.indexOf(item) >= TABLE_VISIBLE_ROWS;
  const table = () => element("table", {className:"data-table"},
    element("thead", null, element("tr", null, head.map((value, column) => header(value, column)))),
    element("tbody", null, [...ordered, ...pinned].map(item => element("tr", {key:`r${item.index}`,
      className:folded(item) ? "edge-row-folded" : undefined},
      head.map((_, column) => { const ref = source ? EdgeView.cellRef(source, item.index, column) : null;
        return element("td", cellProps(column, ref ? {"data-fig-ref":ref} : {}), mdInline(item.row[column] ?? "", ctx)); })))));
  if (plain) return table();
  const ui = edgeUi();
  const hidden = free.length - TABLE_VISIBLE_ROWS;
  const open = () => openTableDialog({title:title || ui.tableTitle, description:ui.tableRows.replace("{n}", rows.length),
    returnFocusRef:expandRef, table:{head, align, rows, numeric, ctx, initialSort:sort}});
  const fileState = download ? initialValue(view, "download", () => null) : null;
  const fileNote = {preparing:ui.tableDownloadPreparing, failed:ui.tableDownloadFailed, busy:ui.tableDownloadBusy}[fileState];
  return element("div", {className:"edge-md-table-frame"},
    element("div", {className:"edge-table-tools"},
      fileNote && element("span", {className:`edge-table-file-note${fileState === "failed" ? " failed" : ""}`, role:"status"}, fileNote),
      download && element("button", {type:"button", className:"edge-table-download", title:ui.tableDownload, "aria-label":ui.tableDownload,
        "aria-busy":fileState === "preparing", disabled:fileState === "preparing", onClick:() => downloadTable(view, download)},
        element(Icon, {name:"download", size:14})),
      element("button", {type:"button", className:"edge-table-expand", ref:expandRef, title:ui.tableExpand,
        "aria-label":ui.tableExpand, onClick:open}, element(Icon, {name:"maximize", size:14}))),
    element("div", {className:"edge-md-table"}, table()),
    folds && element("button", {type:"button", className:"edge-table-more", "aria-expanded":showAll,
      onClick:() => updateValue(view, "showAll", !showAll)},
      showAll ? ui.tableFewerRows : ui.tableMoreRows.replace("{n}", hidden)));
}

function Markdown({text, claims, className = "", tables = null, attach = null, figures = null, conversationId = null}) {
  return element("div", {className:`edge-md ${className}`}, renderMarkdown(text, {claims, tables, attach, conversationId, usedTables:[],
    figures:Array.isArray(figures) && figures.length ? {list:figures, next:0} : null}));
}

// ---- One generic view for structured data ----
function DataValue({value, depth = 0}) {
  const {empty, valueText} = edgeFormat();
  if (empty(value)) return element("span", {className:"edge-muted"}, "—");
  if (typeof value === "string") {
    const href = /^https?:\/\//.test(value) ? Edge.safeUrl(value) : null;
    return href ? element("a", {href, target:"_blank", rel:"noopener noreferrer"}, value) : element("span", {className:"edge-text"}, fastDates(valueText(value)));
  }
  if (typeof value !== "object") return element("span", null, valueText(value));
  if (Array.isArray(value)) {
    if (value.every(item => item == null || typeof item !== "object")) return value.length <= 3 && value.every(item => typeof item === "number")
      ? element("span", null, value.map(valueText).join("; "))
      : element("ul", {className:"edge-list"}, value.map(item => element("li", null, valueText(item))));
    return element("div", {className:"edge-data-cards"}, value.map(item => element("div", {className:"edge-data-card"}, DataRows({value:item, depth:depth + 1}))));
  }
  return depth > 3 ? element("code", {className:"edge-inline-json"}, JSON.stringify(value)) : DataRows({value, depth:depth + 1});
}
function DataRows({value, depth = 0, skip = []}) {
  const {empty, label} = edgeFormat();
  if (value == null || typeof value !== "object" || Array.isArray(value)) return DataValue({value, depth});
  const keys = Object.keys(value).filter(key => !skip.includes(key) && !empty(value[key]));
  return element("dl", {className:"edge-data-rows"}, keys.map(key => element("div", {className:"edge-data-row"},
    element("dt", null, label(key)), element("dd", null, DataValue({value:value[key], depth})))));
}
function TechnicalDetail({value, label}) {
  return edgeFormat().empty(value) ? null : element("details", {className:"edge-technical"}, element("summary", null, label ?? edgeUi().technical),
    element("pre", null, JSON.stringify(value, null, 2)));
}
const edgeMore = (value, label) => value ? element("details", {className:"edge-more"}, element("summary", null, label), DataRows({value})) : null;

// ---- Research plan ----
function PlanItem({item}) {
  return element("section", {className:"edge-plan-item"},
    element("div", {className:"edge-plan-item-head"}, element("span", {className:"edge-step"}, item.step), typeof item.key === "string" && element(fragment, null, " \u00B7 ", element("code", null, item.key))),
    element("p", {className:"edge-plan-question"}, item.title),
    item.question && element("p", {className:"edge-plan-question"}, item.question),
    item.objective && element("p", {className:"edge-plan-question"}, item.objective),
    element("dl", {className:"edge-facts"}, item.facts.map(fact => element("div", null, element("dt", {className: "edge-fact-label"}, fact.label),
      element("dd", null, fact.value, fact.note && element("small", null, fact.note))))),
    edgeMore(item.more, item.moreLabel));
}
function PlanCard({plan, actions, pending, notes}) {
  return element(fragment, null, element("section", {className:"edge-plan", "aria-label":plan.label},
    element("div", {className:"edge-plan-head"}, element(Icon, {name:"flask"}), element("span", {className:"edge-eyebrow"}, plan.label), pending && element("span", {className:"edge-badge warning"}, element("i", {className:"edge-badge-dot", "aria-hidden":"true"}), plan.pendingLabel)),
    plan.summary.length > 0 && element("dl", {className:"edge-facts edge-plan-summary"}, plan.summary.map(fact => element("div", null, element("dt", null, fact.label), " ", element("dd", null, fact.value)))),
    plan.objective && element("p", {className:"edge-plan-objective"}, plan.objective),
    plan.root && element("p", {className:"edge-plan-question edge-plan-root"}, element("strong", null, plan.root.label + ": "), plan.root.text),
    plan.items.map(item => element(PlanItem, {key:item.key, item:{...item, moreLabel:plan.itemMoreLabel}})),
    plan.carried && element("div", {className:"edge-plan-notes edge-plan-carried"}, element("strong", null, plan.carried.label), DataValue({value:plan.carried.value})),
    edgeMore(plan.more, plan.moreLabel),
    notes),
    actions);
}

// ---- Research findings ----
function FindingCard({finding, claims}) {
  return element("section", {className:"edge-finding"},
    element("div", {className:"edge-finding-head"}, element("strong", null, finding.title), edgeVerdict(finding.verdict)),
    finding.metrics.length > 0 && element("div", {className:"edge-metrics"}, finding.metrics.map(metric => element("div", null, element("span", null, metric.label), element("strong", null, metric.value)))),
    finding.parts.length > 0 && element("div", {className:"edge-finding-parts"}, finding.parts.map(part => element("div", {className:"edge-finding-part"}, element("span", {className:"edge-eyebrow"}, part.label), element(Markdown, {text:part.text, claims})))),
    finding.other && DataRows({value:finding.other}),
    edgeMore(finding.backendMore, finding.backendMoreLabel));
}

// ---- Choices the backend offers: each carries an action the page runs (act), whatever its source ----
// EXEC-CHOICES (user 2026-10-13, the "Response choices" design, applied where the system asks the user: an ask-back
// question, a Research Plan to approve, a paused answer, and the suggestions what to ask next): a choice is either sent
// at once (arrow) or completed in the message box first (pen: a plan revision, a pause choice that needs the user's
// words, "Tulis jawaban lain"); the chosen one stays marked once the reply went out
const edgeChosen = new Map();
function edgeChoiceDraft(action){return action?.type==="input"||(action?.type==="plan"&&action.plan==="REVISE");}
function ChoiceBar({choices, enabled, act, scope}) {
  const ui=edgeUi();
  return element("div", {className:"edge-choices", role:"group", "aria-label":ui.choices},
    choices.map((choice, index) => {
      const draft=edgeChoiceDraft(choice.action), id=(scope||"")+":"+(choice.key ?? index), chosen=edgeChosen.get(scope)===id;
      return element("button", {key:choice.key ?? index, type:"button", className:`edge-choice${choice.primary?" primary":""}${chosen?" sent":""}`,
          disabled:!enabled, "aria-pressed":chosen, title:enabled ? choice.title : ui.choicesDisabled,
          "aria-label":choice.label,
          onClick:() => {if(scope)edgeChosen.set(scope,id);act(choice.action);}},
        element("span",{className:"edge-choice-icon"},element(Icon,{name:draft?"pen":"arrow"})),
        // MONITOR-REVAMP (AI_revamp.html .choice): every choice says what it does under its label ("Sends right away")
        element("span",{className:"edge-choice-copy"},element("strong",null,choice.label),
          element("small",null,chosen?(draft?ui.choiceChosenDraft:ui.choiceChosen):(choice.note||(draft?(choice.hint||ui.choiceDraft):ui.choiceSends)))));
    }));
}
function ResponseChoices({title, prompt, choices, enabled, act, scope, help, boundary=true, kind=""}) {
  const ui=edgeUi();
  return element("section",{className:"edge-response-choices"+(boundary?"":" no-boundary")+(kind?" "+kind:""),"aria-label":title||ui.choicesTitle},
    element("div",{className:"edge-choices-title"},boundary?ui.nextAction+" \u00B7 "+(title||ui.choicesTitle):title||ui.choicesTitle),
    prompt,
    choices.length>0&&element("div",{className:"edge-choice-area"},element(ChoiceBar,{choices,enabled,act,scope})),
    (help||(enabled&&boundary))&&element("p",{className:"edge-choices-help"},help||ui.pauseHint));
}
function PauseCard({pause, enabled, act, scope}) {
  // MONITOR-REVAMP (AI_revamp.html .pause, .next): the paused line names the reason; its choices follow as "Response choices"
  return element(fragment,null,element("div",{className:"edge-pause-line",role:"note","aria-label":pause.region},element(Icon,{name:"pause"}),
      element("div",null,element("b",null,pause.label+"."),pause.reason?" "+pause.reason:null)),
    element(ResponseChoices,{kind:"pause",scope,enabled,act,help:pause.hint,
    choices:(()=>{const first=pause.choices.findIndex(choice=>!edgeChoiceDraft(choice.action));
      return pause.choices.map((choice,index)=>({...choice,primary:index===first}));})()}));  // the first choice sent at once leads
}
// MONITOR-REVAMP (AI_revamp.html followUps): the icon of each kind of suggestion
const EDGE_FOLLOW_KIND = {FOLLOW_UP:["reply","",""], INSIGHT_IDEA:["bulb","info",""], DATA_TEST:["flask","warning",""]};
function FollowUps({groups, enabled, act, scope}) {
  // user 2026-10-30 ("suggested next question dan insight idea bisa disamakan? bisa collapse dan expand each"): one
  // folded section per kind, closed at first, drawn like Assumptions and Limitations; a click still sends the words
  const ui=edgeUi(), titles={FOLLOW_UP:ui.suggestedNext, INSIGHT_IDEA:ui.insightIdeas, DATA_TEST:ui.dataTest};
  return element("div",{className:"content-block edge-next edge-discs"},groups.map(group=>{const title=titles[group.key]||group.label;
    return element("details",{key:group.key,className:"edge-more edge-notes edge-fup-group","data-kind":group.key},
      element("summary",null,`${title} (${group.choices.length})`),
      element("div",{className:"edge-fups",role:"group","aria-label":title},group.choices.map(choice=>{
        const [icon]=EDGE_FOLLOW_KIND[group.key]||EDGE_FOLLOW_KIND.FOLLOW_UP, id=scope+":"+choice.key, chosen=edgeChosen.get(scope)===id;
        return element("button",{key:choice.key,type:"button",className:`edge-fup${chosen?" sent":""}`,disabled:!enabled,"aria-pressed":chosen,"aria-label":choice.label,
            title:enabled?undefined:ui.choicesDisabled,onClick:()=>{edgeChosen.set(scope,id);act(choice.action);}},
          element(Icon,{name:icon}),element("span",{className:"edge-fup-label"},choice.label));})));}));
}
function ResearchDocument({run,togglePin,act,enabled,planEnabled,planIndex,conversationId,carry=null}) {
 const v=EdgeView.toView(run.raw,{domainStatus:run.domainStatus,planIndex}), claims=new Map(v.claims);
 const items=values=>element("ul",{className:"edge-list"},values.map(x=>element("li",null,typeof x==="string"?mdInline(fastDates(x),{claims}):DataValue({value:x}))));
 // EXEC-STYLE S3: assumptions and limitations sit folded under the answer, with their count
 const list=part=>element("details",{key:part.label,className:"edge-more edge-notes","data-section":part.label===edgeUi().limitations?"LIMITATIONS":"ASSUMPTIONS"},element("summary",null,`${part.label} (${part.items.length})`),items(part.items));
 const notes=v.plan&&[v.plan.notes.assumptions,v.plan.notes.limitations].some(part=>part.items.length)?element("div",{className:"edge-plan-notes"},
   [v.plan.notes.assumptions,v.plan.notes.limitations].map(part=>part.items.length>0&&element("div",null,element("span",{className:"edge-eyebrow"},part.label),items(part.items)))):null;
 return element("article",{className:"result",id:run.id+"-response",tabIndex:-1},
  // user 2026-10-21 (screenshot): a completed answer says "EDGE" only; any other status (Limited, Paused, Failed, ...) stays named
  // MONITOR-REVAMP (AI_revamp.html .kick): the status of any other answer is a pill after "EDGE"
  element("div",{className:"result-kicker"},element(Icon,{name:"spark"}),element("span",null,edgeUi().answerKicker),v.status.code!=="COMPLETED"&&element("span",{className:`edge-badge ${v.status.tone}`},element("i",{className:"edge-badge-dot","aria-hidden":"true"}),v.status.label)),
  element("h1",null,run.result.title),
  element("div",{className:"result-metadata"},element("span",null,"Request "+run.id),v.meta.model&&element("span",{className:"edge-run-model"},element(EdgeModelLogo,{option:edgeModelOption(v.meta.model)}),element("span",null,element("span",{className:"edge-run-model-name",title:v.meta.model},edgeModelOption(v.meta.model).label),v.meta.reasoningLevel?element("span",{className:"edge-run-model-level"}," \u00B7 "+(edgeUi().modelLevels?.[v.meta.reasoningLevel]??v.meta.reasoningLevel)):null)),v.meta.tokens!==undefined&&element("span",{className:"edge-tokens"},"Tokens ",element("b",null,edgeTokens(v.meta.tokens))),v.meta.cost!=null&&element("span",{className:"edge-cost"},element("span",{className:"edge-cost-label"},"Reported cost"),element("span",{className:"edge-cost-badge"},"$"+v.meta.cost)),v.meta.duration&&element("span",{className:"edge-duration",title:"Processing time"},element("svg",{className:"icon",width:12,height:12,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"1.6",strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true"},element("circle",{cx:"12",cy:"12",r:"9"}),element("path",{d:"M12 7v5l3 2"})),element("b",null,v.meta.duration))),
  // MONITOR-REVAMP (AI_revamp.html .evline): the evidence label as text, a positive one followed by its green check
  v.evidence&&element("div",{className:"edge-tags edge-evidence-line"},element("span",{className:"edge-evidence-text",title:v.evidence.code},v.evidence.label),v.evidence.positive&&element("svg",{className:"edge-evidence-check",width:12,height:12,viewBox:"0 0 16 16","aria-hidden":"true"},element("circle",{cx:"8",cy:"8",r:"8",fill:"#087f5b"}),element("path",{d:"M4.6 8.3l2.2 2.2 4.6-4.8",fill:"none",stroke:"#ffffff",strokeWidth:"1.9",strokeLinecap:"round",strokeLinejoin:"round"}))),
  v.attached.length>0&&element("div",{className:"edge-attached-line"},element(Icon,{name:"attach",size:13}),
    element("span",null,edgeUi().attachedPrefix+": "+v.attached.join("; "))),
  v.answer&&element("div",{className:"content-block edge-answer","data-section":"ANSWER"},element(Markdown,{text:v.answer,claims,
    tables:run.raw?.answer_tables,attach:act?(selection=>act({type:"attach",selection})):null,figures:run.raw?.answer_figures,
    conversationId:conversationId&&!String(conversationId).startsWith("draft:")?conversationId:null})),
  v.reproduced.map((line,index)=>element("div",{key:`reproduced-${index}`,className:"edge-reproduced"},element(Icon,{name:"check",size:13}),element("span",null,line))),
  v.clarification&&element(ResponseChoices,{scope:run.id+":clarify",enabled,act,
    prompt:element("div",{className:"edge-choices-prompt"},element(Markdown,{text:v.clarification.text,claims})),
    choices:v.clarification.choices.length?[...v.clarification.choices,{key:"WRITE_OTHER",label:edgeUi().writeOther,action:{type:"input",hint:edgeUi().writeOtherHint}}]:[]}),
  v.pause&&element(PauseCard,{pause:v.pause,enabled,act,scope:run.id+":pause"}),
  v.plan&&element(PlanCard,{plan:v.plan,pending:planEnabled,actions:element(ResponseChoices,{scope:run.id+":plan",enabled:planEnabled,act,
    title:edgeUi().planChoicesTitle,choices:v.plan.choices,prompt:v.plan.confirmation&&element("p",{className:"edge-choices-prompt"},v.plan.confirmation)}),notes}),
  v.findings&&element("section",{className:"content-block edge-block"},element(SectionTitle,null,v.findings.label," ",element("span",{className:"edge-muted edge-count"},`(${v.findings.items.length})`)),
    v.findings.items.map(finding=>element(FindingCard,{key:finding.key,finding,claims}))),
  // the suggestions, one folded section per kind (user 2026-10-30); a click sends its words, as before (EXEC-Y Fase 2)
  v.next&&element(FollowUps,{groups:v.next,enabled,act,scope:run.id+":next"}),
  // MONITOR-REVAMP (AI_revamp.html .discs): Assumptions, Limitations and Methodology fold the same way, in that order
  (v.lists.length>0||v.methodology)&&element("div",{className:"content-block edge-discs"},v.lists.map(list),
    v.methodology&&element("details",{className:"edge-more edge-notes edge-methodology"},element("summary",null,v.methodology.label),element(Markdown,{text:v.methodology.text,claims}))),
  element(ResponseActions,{run,togglePin,artifacts:v.artifacts,carry}));
}
function ShareResearchPopover({run,close}) {return element("div",{className:"share-popover"},element("p",null,"Public sharing unavailable"),element(Button,{onClick:close},"Close"));}
function SourceItem({item, act}) {
 return element("div",{className:"edge-source"},
  element("div",{className:"edge-source-head"},element(item.code?"code":"strong",null,item.title),item.status&&edgeVerdict(item.status)),
  item.ref&&element("code",{className:"edge-source-ref"},item.ref),
  DataRows({value:item.rows}),
  item.action&&act&&element("button",{type:"button",className:"edge-source-action",onClick:()=>act(item.action)},item.actionLabel));
}
// MONITOR-REVAMP (AI_revamp.html .sec .tg, DEFAULT_CLOSED): every part of Sources folds under its title and count; a part
// starts folded and this browser keeps whether the user opened it
function SourceFold({title, children}) {
 const m=/^(.*) \((\d+)\)$/.exec(title), label=m?m[1]:title, count=m?m[2]:null, key="edge-sources-open:"+label;
 let open=false;try{open=localStorage.getItem(key)==="true";}catch{/* folded */}
 return element("details",{className:"content-block edge-source-fold",open,onToggle:event=>{try{localStorage.setItem(key,String(event.currentTarget.open));}catch{/* not kept */}}},
  element("summary",null,element("span",null,label),count!=null&&element("span",{className:"edge-section-count","aria-hidden":"true"},count),element(DisclosureChevron)),
  children);
}
function Sources({run, act}) {
 const v=EdgeView.sources(run.raw);
 // EXEC-UI-1024 1C: the empty state sits where the panel's content starts (left, the sources' own padding)
 if(v.empty)return element("p",{className:"sources-empty"},v.emptyText);
 const items=section=>section.items.map((item,index)=>element(SourceItem,{key:index,item,act}));
 return element("div",{className:"sources"},
  v.sections.map(section=>element(SourceFold,{key:section.title.replace(/ \(\d+\)$/,""),title:section.title},items(section))),
  v.record&&element(SourceFold,{key:"record",title:v.record.title},DataRows({value:v.record.summary}),element(TechnicalDetail,{value:v.record.raw,label:v.record.technicalLabel})));
}

function SourceSection({ title, count, children }) {
    const viewRecord = currentView;
    const open = initialValue(viewRecord, "open", () => ((() => { const seed = true; return typeof seed === "function" ? seed() : seed; })())), setOpen = next => updateValue(viewRecord, "open", next);
    return element("section", { className: "source-section" },
        element("button", { className: "source-section-head", "aria-expanded": open, onClick: () => setOpen(!open) },
            element("span", null,
                title,
                " ",
                element("small", null,
                    "(",
                    count,
                    ")")),
            element(Icon, { name: "chevron" })),
        open && children);
}
function Flow({ run }) {
    return element("div", { className: "flow" }, run.steps.map(step => element("div", { className: `flow-step ${step.status}`, key: step.id },
        element("span", { className: "flow-node" },
            step.status === "running" ? element("span", {className:"edge-flow-spinner", "aria-label":"Running"}) : step.status === "pending" ? element("span", {className:"edge-flow-pending", "aria-label":"Pending"}) : element(Icon, { name: step.status === "completed" ? "check" : step.status === "failed" ? "close" : step.status === "cancelled" ? "stop" : "more" })),
        element("div", null,
            element("strong", {className:"edge-flow-title"}, step.label,
                step.status === "completed" && element("span", {className:"edge-flow-done", role:"img", "aria-label":"Completed"},element(Icon,{name:"check"}))),
            element("small", null,
                step.detail,
                step.durationMs !== undefined && ` · ${formatDuration(step.durationMs)}`)))));
}

// EXEC-MU-ACCOUNTS Phase 1 (contract section 12): the one route table that go() and currentPath read. `auth`: the page
// needs a session; `open`: an account page shown only while registration is open (GET /api/v1/auth/config, else the
// sign-in page); `title`: EdgeLabels.pages. /c/<id> is the Monitor (EXEC-CHAT-URL). main.py serves each path.
const ROUTES = [
    {path:"/monitor", names:["monitor","markets","/markets"], auth:true, title:"monitor"},
    {path:"/terminal", names:["terminal"], auth:true, title:"terminal"},
    {path:"/backtest", names:["backtest"], auth:true, title:"backtest"},
    {path:"/screener", names:["screener"], auth:true, title:"screener"},
    {path:"/radar", names:["radar"], auth:true, title:"radar"},
    {path:"/overview", names:["overview"], auth:true, title:"overview"},
    {path:"/watchlist", names:["watchlist"], auth:true, title:"watchlist"},
    // Phase 4: the admin page of the beta (main.py /admin; the live site answers 404); opened by admin.access
    {path:"/admin", names:["admin"], auth:true, title:"admin", needs:"admin.access"},
    {path:"/login", names:["login","/"], auth:false, mode:"login", title:"signIn"},
    {path:"/register", names:["register"], auth:false, mode:"register", open:true, title:"register"},
    {path:"/verify", names:["verify"], auth:false, mode:"verify", open:true, title:"verify"},
    {path:"/forgot", names:["forgot"], auth:false, mode:"forgot", open:true, title:"forgot"},
    {path:"/reset", names:["reset"], auth:false, mode:"reset", open:true, title:"reset"},
    {path:"/mfa", names:["mfa"], auth:false, mode:"mfa", title:"mfa"}
];
const routeOf = name => ROUTES.find(r => r.path === name || r.names.includes(name)) || null;
function App() {
    const viewRecord = currentView;
    const currentPath = () => { const p = routeLocation().pathname; return p.startsWith("/c/") ? "/monitor" : routeOf(p)?.path === p ? p : p === "/markets" ? "/monitor" : "/login"; };
    const authenticated=initialValue(viewRecord,"authenticated",()=>false),checked=initialValue(viewRecord,"checked",()=>false),open=initialValue(viewRecord,"open",()=>false);
    // track guest: the pre-launch mode closes the register and verify pages (they say registration opens soon), and a
    // visitor without an account opens the Terminal where the site has guests (GET /api/v1/auth/config)
    const prelaunch=initialValue(viewRecord,"prelaunch",()=>false),guests=initialValue(viewRecord,"guests",()=>false);
    onLifecycle(viewRecord,"config",()=>{let live=true;Edge.config().then(c=>{if(live){updateValue(viewRecord,"open",c.multiuser);updateValue(viewRecord,"prelaunch",c.prelaunch===true);updateValue(viewRecord,"guests",c.guests===true);}});return()=>{live=false;};},[]);
    onLifecycle(viewRecord,"auth",()=>{const sync=()=>{updateValue(viewRecord,"authenticated",Boolean(Edge.auth));updateValue(viewRecord,"accessVersion",Edge.auth?.access?.version ?? null);};addEventListener("edge-auth",sync);Promise.all([Edge.session(),Edge.config()]).then(()=>{sync();updateValue(viewRecord,"checked",true);});return()=>removeEventListener("edge-auth",sync);},[]);
    const path = initialValue(viewRecord, "path", currentPath), setPath = next => updateValue(viewRecord, "path", next);
    // which account page shows, or null for a workspace page: a session that waits for the authenticator (access.next
    // "mfa") always shows /mfa; signed in, the account pages lead to the workspace; an `open` page needs registration
    // open; /mfa also shows without a session (a sign-in answered MFA_REQUIRED and holds a pending session)
    const authMode = () => { const r = routeOf(path), next = Edge.auth?.access?.next;
        // a new authenticator being set up (authFlow.enrolling) keeps /mfa: the verify of the current code (or a recovery
        // code) answers a fresh session, and without this the workspace would replace the page before the new QR code
        // shows (live checker after the switch-on, ACC-1)
        if (authenticated && (next === "mfa" || (authFlow.enrolling && r?.mode === "mfa"))) return "mfa";
        if (authenticated) return null;
        if (!r || r.auth !== false) return "login";
        if (r.open && !open) return "login";
        if (prelaunch && (r.mode === "register" || r.mode === "verify")) return "closed";
        return r.mode; };
    const theme = initialValue(viewRecord, "theme", () => localStorage.getItem("edge-auth-monitor-theme") || "light"), setTheme = next => updateValue(viewRecord, "theme", next);
    onLifecycle(viewRecord, "navigation", () => {
        const sync = () => setPath(currentPath());
        addEventListener("popstate", sync);
        return () => removeEventListener("popstate", sync);
    }, []);
    onLifecycle(viewRecord, "theme", () => {
        document.documentElement.classList.toggle("dark", theme === "dark");
        document.documentElement.style.colorScheme = theme;
    }, [theme]);
    // EXEC-TERMINAL-IND-EDIT (user 2026-11-05): the browser tab names the page; the words are in edge-labels.js (pages)
    onLifecycle(viewRecord, "title", () => {
        const P = EdgeLabels.pages, r = routeOf(path), m = authMode();
        document.title = !checked ? P.loading : !authenticated && guests && TAB_PATHS[path] ? P[r?.title] || P.terminal
            : !authenticated || r?.auth === false ? P[m === "login" ? "signIn" : m] || P.signIn : P[r?.title] || P.monitor;
    }, [checked, authenticated, path, open, guests, prelaunch]);
    const go = route => {
        const target = routeOf(route);
        if (!target) return;
        const nextPath = target.path;
        // the 3e checker SHELL-2: a press on the tab already shown adds no history entry; on a locked tab it reads the
        // session again (a plan raised meanwhile opens it now)
        if (nextPath === path && routeLocation().pathname === nextPath) {
            const tab = TAB_PATHS[nextPath];
            if (tab && Edge.auth && !Edge.can(`${tab}.view`)) Edge.refresh();
            return;
        }
        // EXEC-CHAT-URL: signing in at /c/<id> stays on that conversation
        if (!(nextPath === "/monitor" && routeLocation().pathname.startsWith("/c/"))) routeHistory.pushState({}, "", nextPath);
        setPath(nextPath);
        window.scrollTo(0, 0);
    };
    const toggle = () => setTheme(current => {
        const next = current === "dark" ? "light" : "dark";
        localStorage.setItem("edge-auth-monitor-theme", next);
        return next;
    });
    themeState = { theme, toggle };
    shellGo = go;                                     // the edge-nav listener (below nav) switches pages with it
    if (!checked) return element("div",{className:"auth-page"},"Checking session…");
    // track guest: a visitor without an account on the Terminal page, where the site has guests; 3e: every other tab of
    // the rail shows the sign-in page in its place (LockedTabPage), the rail kept; an account page asks to sign in
    if (!authenticated && guests && TAB_PATHS[path] && Edge.offers(TAB_PATHS[path]))
        return path === "/terminal" ? element(TerminalPage,{go,guest:true}) : element(ExampleTabPage,{go,route:TAB_PATHS[path],guest:true});
    const mode = authMode();
    if (!authenticated || mode !== null) return element(AuthPage,{mode:mode || "login",go,key:mode || "login"});
    // signed in on an account page (a reload at /login): the account's landing page (re-check R2-14)
    const shown = routeOf(path)?.auth === false ? landing() : path;
    // 3e: a tab the account cannot open (<tab>.view; '*' opens every tab) shows LockedTabPage in its place
    const tab = TAB_PATHS[shown];
    // 3e, the example mode (ERRORS M527): its example where the server serves one (ExampleTabPage), else LockedTabPage
    if (tab && Edge.offers(tab) && Array.isArray(Edge.auth?.access?.capabilities) && !Edge.can(`${tab}.view`))
        return element(ExampleTabPage,{go,route:tab});
    return shown === "/terminal" ? element(TerminalPage,{go}) : shown === "/backtest" ? element(BacktestPage,{go}) : shown === "/screener" ? element(ScreenerPage,{go}) : shown === "/radar" ? element(RadarPage,{go}) : shown === "/overview" ? element(OverviewPage,{go}) : shown === "/watchlist" ? element(WatchlistPage,{go}) : shown === "/admin" ? element(AdminPage,{go}) : Edge.offers("monitor") ? element(Monitor,{go}) : element(TerminalPage,{go});
}

refresh();
})();
