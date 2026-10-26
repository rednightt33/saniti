/* The reference page's own synthetic market, demo formulas and mock-up engine (backtest.html app script), for the
   fixture build only (vite build --mode fixture, ?fixture=reference) and the numeric check; never part of dist/
   (tests/bundle.test.mjs checks the production bundle for its markers; CONTRACT.md section 10).
   Every statement below is the reference's own text, in its order, copied by script from these lines of the app script
   (backtest.html 863-1895, app.js lines): 37-63 section 1 (SYNTHETIC MARKET), 68-87 section 2 (INDICATORS), 92-125
   section 3 (CONDITION CATALOG), 140-161 and 170-177 (the registry's demo calculations, regEval, catOf), 383-399
   section 6 (SIGNALS), 484-498, 501-507 and 516-594 section 8 (ENGINE, without its UI lists), 599-647 section 9
   (STATISTICS), 27 and 29 (primaryBench, closeOf) and 656-672 of section 10 (RUN, the body of its setTimeout).
   Only additions: the module wrapper (the page state S is set by setState, as the reference's global S), the trade
   record also keeps cost, proceeds, stop and target (the ledger needs them; no number changes), and run keeps each
   sensitivity cell's backtest (cellRuns). REG_BY is the page's registry (src/reg.ts: the reference's REG, the same
   53 indicators and 126 parameters). Plain JavaScript on purpose: typing it would change the reference's text. */
import { REG_BY } from '../../src/reg.ts';

let S = null;
/** the reference's global S for the functions below (signalsFor, exitSeries, universe, backtest, monteCarlo, run) */
export const setState = s => { S = s };
export const getState = () => S;

/* ---- 1 · SYNTHETIC MARKET ---- */
const TICKERS = [['BBCA',6200,.012,.0004],['BBRI',3400,.016,.0002],['BMRI',3700,.016,.0003],['TLKM',3800,.014,-.0001],['ASII',8100,.016,.0000],['MAPI',780,.022,.0008],['ACES',1400,.021,.0000],['ADRO',1700,.026,.0003],['ANTM',800,.027,.0002],['GOTO',380,.033,-.0006]];
const BROKERS = ['YU','AK','CC','ZP','BK','KZ','RX','DX'];
const DAYS = []; for(let t=Date.UTC(2019,0,2); t<=Date.UTC(2026,9,23); t+=864e5){ const d=new Date(t).getUTCDay(); if(d&&d<6) DAYS.push(new Date(t).toISOString().slice(0,10)) }
const N = DAYS.length;
let seed = 20261025; const rnd = () => ((seed = Math.imul(seed,1664525)+1013904223>>>0)/4294967296);
const gauss = () => { let u=0,v=0; while(!u)u=rnd(); while(!v)v=rnd(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v) };
const mkt = []; { let r=0; for(let i=0;i<N;i++){ const reg = Math.sin(i/180)*.0004; mkt.push(reg + gauss()*.0085) } }
const IHSG = []; { let p=6200; for(let i=0;i<N;i++){ p*=1+mkt[i]+.00012; IHSG.push(p) } }
const DATA = {};
TICKERS.forEach(([tk,p0,vol,drift],k) => {
  const o=[],h=[],l=[],c=[],v=[],fnet=[],br={}; BROKERS.forEach(b=>br[b]=new Float64Array(N));
  // pre-draw idiosyncratic shocks so flows can "see" a little of the next days
  const eps = Array.from({length:N+6},()=>gauss()*vol);
  let p=p0, beta=.7+rnd()*.6, avgVal = p0*4e6*(1+rnd()*3);
  for(let i=0;i<N;i++){
    const r = drift + beta*mkt[i] + eps[i];
    const op = p*(1+gauss()*vol*.25); const cl = Math.max(50, p*(1+r));
    const hi = Math.max(op,cl)*(1+Math.abs(gauss())*vol*.45), lo = Math.min(op,cl)*(1-Math.abs(gauss())*vol*.45);
    const fwd = eps[i+1]+eps[i+2]+eps[i+3];                  // weakly informative flow
    const turnover = avgVal*(1+Math.abs(r)*25+rnd()*.6);
    const fn = turnover*(.22*Math.tanh(fwd/vol*.5)+.10*Math.tanh(r/vol)+gauss()*.18);
    o.push(op); h.push(hi); l.push(lo); c.push(cl); v.push(Math.round(turnover/cl)); fnet.push(fn);
    BROKERS.forEach((b,j)=>{ const w = (j<3?.6:.3)*(j%2?-1:1); br[b][i] = turnover*(.08*w*Math.tanh(fwd/vol*.6)+(j===0?.12:0)*Math.tanh(fwd/vol*.4)+gauss()*.06) });
    p = cl;
  }
  DATA[tk] = {o,h,l,c,v,fnet,br,val:c.map((x,i)=>x*v[i])};
});

/* ---- 2 · INDICATORS ---- */
const cache = {};
const memo = (tk,key,fn) => { const k=tk+'|'+key; return cache[k] ||= fn() };
const sma = (a,n) => { const r=new Float64Array(a.length).fill(NaN); let s=0; for(let i=0;i<a.length;i++){ s+=a[i]; if(i>=n) s-=a[i-n]; if(i>=n-1) r[i]=s/n } return r };
const ema = (a,n) => { const r=new Float64Array(a.length).fill(NaN), k=2/(n+1); let e=a[0]; for(let i=0;i<a.length;i++){ e = i? a[i]*k+e*(1-k) : a[0]; r[i] = i>=n-1? e : NaN } return r };
const rsi = (c,n) => { const r=new Float64Array(c.length).fill(NaN); let g=0,ls=0; for(let i=1;i<c.length;i++){ const d=c[i]-c[i-1], up=Math.max(d,0), dn=Math.max(-d,0); if(i<=n){ g+=up/n; ls+=dn/n; if(i===n) r[i]=100-100/(1+g/(ls||1e-9)) } else { g=(g*(n-1)+up)/n; ls=(ls*(n-1)+dn)/n; r[i]=100-100/(1+g/(ls||1e-9)) } } return r };
const stoch = (D,n,s) => { const {h,l,c}=D, k=new Float64Array(c.length).fill(NaN); for(let i=n-1;i<c.length;i++){ let hh=-1e18,ll=1e18; for(let j=i-n+1;j<=i;j++){ hh=Math.max(hh,h[j]); ll=Math.min(ll,l[j]) } k[i]=(c[i]-ll)/((hh-ll)||1e-9)*100 } return sma(Array.from(k,x=>isNaN(x)?50:x), s) };
const macd = (c,f,s,g) => { const a=ema(c,f), b=ema(c,s), m=Float64Array.from(a,(x,i)=>x-b[i]); const sig=ema(Array.from(m,x=>isNaN(x)?0:x),g); return {m, sig, hist:Float64Array.from(m,(x,i)=>x-sig[i])} };
const adx = (D,n) => { const {h,l,c}=D, len=c.length, out=new Float64Array(len).fill(NaN), pdi=new Float64Array(len).fill(NaN), mdi=new Float64Array(len).fill(NaN);
  let tr=0,pdm=0,mdm=0,ad=0; for(let i=1;i<len;i++){ const up=h[i]-h[i-1], dn=l[i-1]-l[i], t=Math.max(h[i]-l[i],Math.abs(h[i]-c[i-1]),Math.abs(l[i]-c[i-1]));
    const p = up>dn&&up>0?up:0, m = dn>up&&dn>0?dn:0; tr = i<=n? tr+t : tr-tr/n+t; pdm = i<=n? pdm+p : pdm-pdm/n+p; mdm = i<=n? mdm+m : mdm-mdm/n+m;
    if(i>=n){ const P=100*pdm/(tr||1e-9), M=100*mdm/(tr||1e-9), dx=100*Math.abs(P-M)/((P+M)||1e-9); pdi[i]=P; mdi[i]=M; ad = i<2*n? ad+dx/n : (ad*(n-1)+dx)/n; if(i>=2*n-1) out[i]=ad } }
  return {adx:out,pdi,mdi} };
const highest = (a,n) => { const r=new Float64Array(a.length).fill(NaN); for(let i=n;i<a.length;i++){ let m=-1e18; for(let j=i-n;j<i;j++) m=Math.max(m,a[j]); r[i]=m } return r };
const rollsum = (a,n) => { const r=new Float64Array(a.length).fill(NaN); let s=0; for(let i=0;i<a.length;i++){ s+=a[i]; if(i>=n) s-=a[i-n]; if(i>=n-1) r[i]=s } return r };
const stdev = (a,n) => { const m=sma(a,n), r=new Float64Array(a.length).fill(NaN); for(let i=n-1;i<a.length;i++){ let s=0; for(let j=i-n+1;j<=i;j++) s+=(a[j]-m[i])**2; r[i]=Math.sqrt(s/n) } return r };
// bullish divergence: a new swing low in price below the previous swing low while MACD makes a higher low; flagged when the swing low is confirmed (k bars later)
const bullDiv = (D, mline, look, k=3) => { const {l}=D, out=new Uint8Array(l.length), piv=[];
  for(let i=k;i<l.length-k;i++){ let isLow=true; for(let j=1;j<=k;j++) if(l[i]>l[i-j]||l[i]>l[i+j]){ isLow=false; break } if(isLow) piv.push(i) }
  for(let p=1;p<piv.length;p++){ const a=piv[p-1], b=piv[p]; if(b-a>look) continue; if(l[b]<l[a] && mline[b]>mline[a] && !isNaN(mline[a])) out[b+k]=1 }
  return out };

/* ---- 3 · CONDITION CATALOG ---- */
const OPS = {gt:'>',lt:'<',ca:'crosses above',cb:'crosses below'};
const cmpSeries = (s, op, v) => { const r=new Uint8Array(s.length); for(let i=1;i<s.length;i++){ const x=s[i], p=s[i-1]; if(isNaN(x)) continue;
  r[i] = op==='gt'? x>v : op==='lt'? x<v : op==='ca'? (p<=v && x>v) : op==='cb'? (p>=v && x<v) : 0 } return r };
const CATALOG = {
  adx:{group:'tech',label:'ADX',desc:'Trend strength',params:[['len','Length',14]],ops:['gt','lt','ca'],val:30,unit:'',
       eval:(tk,p)=>cmpSeries(memo(tk,'adx'+p.len,()=>adx(DATA[tk],p.len)).adx,p.op,p.val)},
  dmi:{group:'tech',label:'DMI direction',desc:'+DI above −DI (uptrend)',params:[['len','Length',14]],ops:['plus','pcross'],opLabels:{plus:'+DI above −DI',pcross:'+DI crosses above −DI'},noVal:true,
       eval:(tk,p)=>{ const a=memo(tk,'adx'+p.len,()=>adx(DATA[tk],p.len)), r=new Uint8Array(N); for(let i=1;i<N;i++) r[i] = p.op==='plus'? a.pdi[i]>a.mdi[i] : (a.pdi[i-1]<=a.mdi[i-1] && a.pdi[i]>a.mdi[i]); return r }},
  stoch:{group:'tech',label:'Stochastic %K',desc:'Momentum oscillator 0–100',params:[['len','Length',14],['smooth','Smooth',3]],ops:['lt','gt','ca','cb'],val:20,
       eval:(tk,p)=>cmpSeries(memo(tk,`st${p.len}_${p.smooth}`,()=>stoch(DATA[tk],p.len,p.smooth)),p.op,p.val)},
  rsi:{group:'tech',label:'RSI',desc:'Relative strength 0–100',params:[['len','Length',14]],ops:['lt','gt','ca','cb'],val:30,
       eval:(tk,p)=>cmpSeries(memo(tk,'rsi'+p.len,()=>rsi(DATA[tk].c,p.len)),p.op,p.val)},
  macd:{group:'tech',label:'MACD',desc:'Divergence, signal cross, histogram',params:[['fast','Fast',12],['slow','Slow',26],['sig','Signal',9]],ops:['bdiv','xsig','hpos'],opLabels:{bdiv:'Bullish divergence',xsig:'Crosses above signal',hpos:'Histogram > 0'},noVal:true,
       eval:(tk,p)=>{ const m=memo(tk,`macd${p.fast}_${p.slow}_${p.sig}`,()=>macd(DATA[tk].c,p.fast,p.slow,p.sig)); if(p.op==='bdiv') return memo(tk,`bdiv${p.fast}_${p.slow}`,()=>bullDiv(DATA[tk],m.m,40));
         const r=new Uint8Array(N); for(let i=1;i<N;i++) r[i] = p.op==='xsig'? (m.m[i-1]<=m.sig[i-1] && m.m[i]>m.sig[i]) : m.hist[i]>0; return r }},
  ma:{group:'tech',label:'Price vs MA',desc:'Close relative to a moving average',params:[['len','MA length',50]],ops:['above','below','xab'],opLabels:{above:'Close above MA',below:'Close below MA',xab:'Close crosses above MA'},noVal:true,
       eval:(tk,p)=>{ const c=DATA[tk].c, m=memo(tk,'sma'+p.len,()=>sma(c,p.len)), r=new Uint8Array(N); for(let i=1;i<N;i++) r[i] = p.op==='above'? c[i]>m[i] : p.op==='below'? c[i]<m[i] : (c[i-1]<=m[i-1] && c[i]>m[i]); return r }},
  macross:{group:'tech',label:'MA cross',desc:'Fast MA vs slow MA',params:[['fast','Fast',20],['slow','Slow',50]],ops:['golden','fabove'],opLabels:{golden:'Golden cross',fabove:'Fast above slow'},noVal:true,
       eval:(tk,p)=>{ const c=DATA[tk].c, a=memo(tk,'sma'+p.fast,()=>sma(c,p.fast)), b=memo(tk,'sma'+p.slow,()=>sma(c,p.slow)), r=new Uint8Array(N); for(let i=1;i<N;i++) r[i] = p.op==='golden'? (a[i-1]<=b[i-1] && a[i]>b[i]) : a[i]>b[i]; return r }},
  volspike:{group:'tech',label:'Volume spike',desc:'Volume ÷ average volume',params:[['len','Avg length',20]],ops:['gt'],val:2,unit:'×',
       eval:(tk,p)=>{ const v=DATA[tk].v, a=memo(tk,'vsma'+p.len,()=>sma(v,p.len)), r=new Uint8Array(N); for(let i=p.len;i<N;i++) r[i] = v[i]/a[i-1] > p.val; return r }},
  breakout:{group:'tech',label:'Breakout',desc:'Close above the highest high of N days',params:[['len','Days',20]],ops:['brk'],opLabels:{brk:'Close > N-day high'},noVal:true,
       eval:(tk,p)=>{ const D=DATA[tk], hh=memo(tk,'hh'+p.len,()=>highest(D.h,p.len)), r=new Uint8Array(N); for(let i=0;i<N;i++) r[i] = D.c[i]>hh[i]; return r }},
  bb:{group:'tech',label:'Bollinger Bands',desc:'Close vs lower band',params:[['len','Length',20],['k','Std dev',2]],ops:['blow','bxin'],opLabels:{blow:'Close below lower band',bxin:'Close back inside lower band'},noVal:true,
       eval:(tk,p)=>{ const c=DATA[tk].c, m=memo(tk,'sma'+p.len,()=>sma(c,p.len)), s=memo(tk,'sd'+p.len,()=>stdev(c,p.len)), r=new Uint8Array(N); for(let i=1;i<N;i++){ const lb=m[i]-p.k*s[i], lb1=m[i-1]-p.k*s[i-1]; r[i] = p.op==='blow'? c[i]<lb : (c[i-1]<lb1 && c[i]>=lb) } return r }},
  dip:{group:'price',label:'Daily drop',desc:'One-day return at or below −X%',params:[],ops:['lt'],val:-3,unit:'%',
       eval:(tk,p)=>{ const c=DATA[tk].c, r=new Uint8Array(N); for(let i=1;i<N;i++) r[i] = (c[i]/c[i-1]-1)*100 <= p.val; return r }},
  fnet:{group:'flow',label:'Foreign net flow',desc:'Sum of foreign net buy over N days',params:[['len','Days',5]],ops:['gt','lt'],val:0,unit:'Rp B',
       eval:(tk,p)=>{ const s=memo(tk,'fn'+p.len,()=>rollsum(DATA[tk].fnet,p.len)); return cmpSeries(Float64Array.from(s,x=>x/1e9),p.op,p.val) }},
  broker:{group:'flow',label:'Broker net buy',desc:'A chosen broker’s net buy over N days',params:[['broker','Broker','YU'],['len','Days',5]],ops:['gt'],val:5,unit:'Rp B',
       eval:(tk,p)=>{ const s=memo(tk,`br${p.broker}${p.len}`,()=>rollsum(DATA[tk].br[p.broker],p.len)); return cmpSeries(Float64Array.from(s,x=>x/1e9),'gt',p.val) }},
  top5:{group:'flow',label:'Top-5 broker accumulation',desc:'Net buy of the 5 biggest buyers minus 5 biggest sellers',params:[['len','Days',10]],ops:['gt'],val:0,unit:'Rp B',
       eval:(tk,p)=>memo(tk,'top5'+p.len+'_'+p.val,()=>{ const D=DATA[tk], r=new Uint8Array(N); const sums=BROKERS.map(b=>rollsum(D.br[b],p.len)); for(let i=p.len;i<N;i++){ const v=sums.map(s=>s[i]).sort((a,b)=>b-a); const acc=v.slice(0,5).filter(x=>x>0).reduce((s,x)=>s+x,0)+v.slice(-5).filter(x=>x<0).reduce((s,x)=>s+x,0); r[i]=acc/1e9>p.val } return r })}
};

/* ---- registry: the demo calculations ---- */
const srcOf = (D, s='close') => s==='open'?D.o : s==='high'?D.h : s==='low'?D.l : s==='hl2'?D.h.map((h,i)=>(h+D.l[i])/2) : s==='hlc3'?D.h.map((h,i)=>(h+D.l[i]+D.c[i])/3) : s==='ohlc4'?D.o.map((o,i)=>(o+D.h[i]+D.l[i]+D.c[i])/4) : D.c;
const lagDiff = (a, n, f) => Float64Array.from(a, (x,i) => i>=n ? f(x, a[i-n]) : NaN);
const roll = (a, n, f) => { const r = new Float64Array(a.length).fill(NaN); for(let i=n-1;i<a.length;i++){ let m = a[i]; for(let j=i-n+1;j<=i;j++) m = f(m, a[j]); r[i] = m } return r };
const REG_CALC = {
  I01:(D,p)=>({sma:sma(srcOf(D,p.source),p.length)}),
  I02:(D,p)=>({ema:ema(srcOf(D,p.source),p.length)}),
  I06:(D,p)=>{ const m = macd(srcOf(D,p.source),p.fast_length,p.slow_length,p.signal_length); return {macd:m.m, signal:m.sig, histogram:m.hist} },
  I07:(D,p)=>{ const a = adx(D,p.di_length); return {adx:a.adx, plus_di:a.pdi, minus_di:a.mdi} },
  I10:(D,p)=>{ const u = roll(D.h,p.length,Math.max), l = roll(D.l,p.length,Math.min); return {upper:u, lower:l, basis:Float64Array.from(u,(x,i)=>(x+l[i])/2)} },
  I13:(D,p)=>({rsi:rsi(srcOf(D,p.source),p.length)}),
  I15:(D,p)=>{ const k = stoch(D,p.k_length,p.smooth_k); return {k, d:sma(Array.from(k,x=>isNaN(x)?50:x),p.d_length)} },
  I17:(D,p)=>({roc:lagDiff(srcOf(D,p.source),p.length,(x,y)=>(x/y-1)*100)}),
  I18:(D,p)=>({momentum:lagDiff(srcOf(D,p.source),p.length,(x,y)=>x-y)}),
  I27:(D,p)=>{ const s = srcOf(D,p.source), b = sma(s,p.length), d = stdev(s,p.length); return {basis:b, upper:Float64Array.from(b,(x,i)=>x+p.std_dev*d[i]), lower:Float64Array.from(b,(x,i)=>x-p.std_dev*d[i])} },
  I28:(D,p)=>{ const s = srcOf(D,p.source), b = sma(s,p.length), d = stdev(s,p.length); return {percent_b:Float64Array.from(s,(x,i)=>(x-(b[i]-p.std_dev*d[i]))/((2*p.std_dev*d[i])||1e-9))} },
  I32:(D,p)=>({stddev:stdev(srcOf(D,p.source),p.length)}),
  I35:(D,p)=>({volume_sma:sma(D.v,p.length)}),
  I36:(D,p)=>({volume_ema:ema(D.v,p.length)}),
  I40:(D)=>{ const r = new Float64Array(N); for(let i=1;i<N;i++) r[i] = r[i-1] + Math.sign(D.c[i]-D.c[i-1])*D.v[i]; return {obv:r} }
};
const regReady = id => !!REG_CALC[id];
const regDefaults = r => Object.fromEntries(r.p.filter(x=>x.t!=='fixed').map(x => [x.k, x.d ?? (x.t==='boolean'?false:x.t==='enum'?(x.opt||[''])[0]:'')]));
const regEval = (tk, c) => { const r = REG_BY[c.ind]; if(!regReady(c.ind)) return new Uint8Array(N);
  const D = DATA[tk], outs = memo(tk, 'reg'+c.ind+JSON.stringify(c.p), () => REG_CALC[c.ind](D, c.p));
  const ser = s => s.t==='price' ? (r.zone==='volume'?D.v:D.c) : s.t==='out' ? outs[s.o] : null;
  const a = ser(c.lhs), b = ser(c.rhs), v = +c.rhs.v, o = new Uint8Array(N), at = i => b ? b[i] : v;
  for(let i=1;i<N;i++){ const x = a[i], y = at(i), px = a[i-1], py = at(i-1); if(isNaN(x)||isNaN(y)) continue;
    o[i] = c.op==='gt' ? x>y : c.op==='lt' ? x<y : c.op==='ca' ? (px<=py && x>y) : (px>=py && x<y) }
  return o };
const catOf = c => c.type!=='reg' ? CATALOG[c.type] : { group:'tech', reg:true, label:REG_BY[c.ind].name, desc:REG_BY[c.ind].short, params:[], ops:[], noVal:true, unit:'', eval:regEval };

/* ---- 6 · SIGNALS ---- */
const inRange = i => DAYS[i] >= S.from && DAYS[i] <= S.to;
const condReady = c => c.type!=='reg' || regReady(c.ind);
const signalsFor = tk => {
  const active = S.conds.filter(c=>c.on && condReady(c));
  const series = active.map(c => ({c, s: catOf(c).eval(tk, c)}));
  const need = S.logic==='all' ? active.length : S.logic==='any' ? 1 : Math.min(S.atLeast, active.length);
  const W = Math.max(1, S.window|0), entry = new Uint8Array(N);
  if(active.length){
    const recent = series.map(() => -1e9);
    for(let i=0;i<N;i++){
      let met = 0; series.forEach((x,k) => { if(x.s[i]) recent[k] = i; if(i - recent[k] < W) met++ });
      entry[i] = met >= need ? 1 : 0;
    }
  }
  return {series, entry};
};
const universe = () => S.mode==='single' ? [S.ticker] : (S.universe==='BANK' ? ['BBCA','BBRI','BMRI'] : TICKERS.map(t=>t[0]));

/* ---- 8 · ENGINE ---- */
const atrS = (D, n) => { const tr = Float64Array.from(D.c, (c,i) => i ? Math.max(D.h[i]-D.l[i], Math.abs(D.h[i]-D.c[i-1]), Math.abs(D.l[i]-D.c[i-1])) : D.h[i]-D.l[i]);
  const r = new Float64Array(N).fill(NaN); let a = 0; for(let i=0;i<N;i++){ if(i<n){ a += tr[i]/n; if(i===n-1) r[i] = a } else { a = (a*(n-1)+tr[i])/n; r[i] = a } } return r };
Object.assign(REG_CALC, {
  I30:(D,p)=>({atr:atrS(D,p.length)}),
  I09:(D,p)=>{ const a = atrS(D,p.atr_length), st = new Float64Array(N).fill(NaN), dir = new Float64Array(N).fill(NaN); let up = 0, dn = 0, d = 1;
    for(let i=0;i<N;i++){ if(isNaN(a[i])) continue; const m = (D.h[i]+D.l[i])/2, bu = m + p.factor*a[i], bl = m - p.factor*a[i];
      up = (i && D.c[i-1] < up) ? Math.min(bu, up||bu) : bu; dn = (i && D.c[i-1] > dn) ? Math.max(bl, dn) : bl;
      if(d===1 && D.c[i] < dn) d = -1; else if(d===-1 && D.c[i] > up) d = 1; st[i] = d===1 ? dn : up; dir[i] = d } return {supertrend:st, direction:dir} },
  I12:(D,p)=>{ const sar = new Float64Array(N).fill(NaN), dir = new Float64Array(N).fill(NaN), s0 = +p.start||.02, inc = +p.increment||.02, mx = +p.maximum||.2;
    let up = true, af = s0, ep = D.h[0], s = D.l[0];
    for(let i=1;i<N;i++){ s = s + af*(ep - s);
      if(up){ s = Math.min(s, D.l[i-1], D.l[Math.max(0,i-2)]); if(D.l[i] < s){ up = false; s = ep; ep = D.l[i]; af = s0 } else if(D.h[i] > ep){ ep = D.h[i]; af = Math.min(mx, af+inc) } }
      else { s = Math.max(s, D.h[i-1], D.h[Math.max(0,i-2)]); if(D.h[i] > s){ up = true; s = ep; ep = D.h[i]; af = s0 } else if(D.l[i] < ep){ ep = D.l[i]; af = Math.min(mx, af+inc) } }
      sar[i] = s; dir[i] = up ? 1 : -1 } return {sar, direction:dir} }
});
const lineSeries = (tk, ref) => { if(!ref || !regReady(ref.id)) return null; const r = REG_BY[ref.id], p = ref.p || regDefaults(r);
  return memo(tk, 'reg'+ref.id+JSON.stringify(p), () => REG_CALC[ref.id](DATA[tk], p))[ref.o] };
const chandelierS = (tk, n, k) => memo(tk, `ch${n}_${k}`, () => { const D = DATA[tk], a = atrS(D,n), hh = roll(D.h,n,Math.max); return Float64Array.from(a, (x,i) => hh[i] - k*x) });
const atrOf = (tk, n) => memo(tk, 'atrS'+n, () => atrS(DATA[tk], n));
/* exit signals: same condition model and catalog as entry */
const exitSeries = tk => { const r = new Uint8Array(N), act = S.exitConds.filter(c => c.on && condReady(c)); if(!act.length) return r;
  const ss = act.map(c => catOf(c).eval(tk, c)); for(let i=0;i<N;i++){ const hit = ss.filter(s => s[i]).length; r[i] = S.exitLogic==='all' ? hit===ss.length : hit>0 } return r };
/* one place turns the exit settings into price levels for a position (entry bar e, signal bar s = e-1) */
const exitLevels = (X, tk, entry, s) => {
  let stop = -1, risk = null;
  if(X.stopMode==='pct' && X.sl>0) stop = entry*(1-X.sl/100);
  else if(X.stopMode==='atr'){ const a = atrOf(tk, X.atrLen)[s]; if(isFinite(a)) stop = entry - X.slAtr*a }
  else if(X.stopMode==='line'){ const L = lineSeries(tk, X.stopLine); if(L && isFinite(L[s]) && L[s] < entry) stop = L[s] }
  let tgt = 1e18;
  if(X.tpMode==='pct' && X.tp>0) tgt = entry*(1+X.tp/100);
  else if(X.tpMode==='atr'){ const a = atrOf(tk, X.atrLen)[s]; if(isFinite(a)) tgt = entry + X.tpAtr*a }
  if(X.stopMode==='rr' && tgt<1e18 && X.slRR>0) stop = entry - (tgt-entry)/X.slRR;   // stop placed from the target: reward : risk = 1 : x
  if(stop>0) risk = entry - stop;
  if(X.tpMode==='r' && risk) tgt = entry + X.tpR*risk;
  return {stop, tgt, risk} };
const trailLevel = (X, tk, p, i) => {   // uses data up to bar i-1 only (no look-ahead), ratchets up
  let t = -1;
  if(X.trailMode==='pct' && X.trail>0) t = p.peak*(1-X.trail/100);
  else if(X.trailMode==='chand'){ const D = DATA[tk], a = atrOf(tk, X.chLen)[i-1]; let hh = -1; for(let j=Math.max(p.ei, i-X.chLen); j<i; j++) hh = Math.max(hh, D.h[j]); if(isFinite(a)) t = hh - X.chK*a }   // highest high since entry (within lookback) − k×ATR
  else if(X.trailMode==='line'){ const L = lineSeries(tk, X.trailLine); if(L && isFinite(L[i-1])) t = L[i-1] }
  if(!(t < DATA[tk].c[i-1])) t = -1;   // a trailing level above the last close is not a stop yet — it activates once price is above it
  return Math.max(p.trail||-1, t) };

const rankScore = (tk,i) => { const D = DATA[tk];
  if(S.rankBy==='adx') return memo(tk,'adx14',()=>adx(D,14)).adx[i] || 0;
  if(S.rankBy==='fnet') return memo(tk,'fn5',()=>rollsum(D.fnet,5))[i] || 0;
  if(S.rankBy==='vol') { const a = memo(tk,'vsma20',()=>sma(D.v,20)); return D.v[i]/(a[i-1]||1) }
  return -(memo(tk,'rsi14',()=>rsi(D.c,14))[i] || 50) };
const backtest = (over={}) => {
  const P = {...S, exit:{...S.exit, ...(over.exit||{})}, conds: over.conds || S.conds};
  const saved = S.conds; S.conds = P.conds;
  const U = universe(), sigs = {}, exits = {}; U.forEach(t => { sigs[t] = signalsFor(t).entry; exits[t] = exitSeries(t) }); S.conds = saved;
  const maxPos = S.mode==='single' ? 1 : S.maxPos, cap0 = S.size.capital;
  const fb = S.cost.buy/100, fs = S.cost.sell/100, sl = S.cost.slip/100;
  let cash = cap0; const pos = []; const trades = []; const eq = []; const expo = [];
  const avgVal = t => memo(t,'val20',()=>sma(DATA[t].val,20));
  let first = -1;
  for(let i=1;i<N;i++){
    if(!inRange(i)) continue; if(first<0) first = i;
    // 1) exits on bar i (stops intraday, then time / signal at the close)
    for(let k=pos.length-1;k>=0;k--){ const p = pos[k], D = DATA[p.tk];
      if(i === p.ei){ p.peak = Math.max(p.peak, D.c[i]) }
      let px = null, why = '';
      if(i > p.ei) p.trail = trailLevel(P.exit, p.tk, p, i); const stop = p.stop, tgt = p.tgt, tr = p.trail||-1;
      p.mae = Math.min(p.mae, D.l[i]/p.entry-1); p.mfe = Math.max(p.mfe, D.h[i]/p.entry-1);
      if(i > p.ei || i === p.ei){
        const lvl = Math.max(stop, tr);
        if(lvl>0 && D.l[i] <= lvl){ px = Math.min(D.o[i], lvl); why = lvl===stop?'Stop loss':'Trailing stop' }
        else if(D.h[i] >= tgt){ px = Math.max(D.o[i], tgt); why = 'Take profit' }
        else if(P.exit.hold>0 && i - p.ei + 1 >= P.exit.hold){ px = D.c[i]; why = 'Time exit' }
        else if(p.pendingExit){ px = D.o[i]; why = 'Exit signal' }
      }
      if(px==null && exits[p.tk][i] && i>p.ei) p.pendingExit = true;   // exit signal at close → sell next open
      if(px==null && i===N-1) { px = D.c[i]; why = 'End of test' }
      if(px==null && DAYS[i+1] && DAYS[i+1] > S.to){ px = D.c[i]; why = 'End of test' }
      if(px!=null){ const fill = px*(1-sl), proceeds = fill*p.sh*(1-fs); cash += proceeds; const cost = p.entry*p.sh*(1+fb)/(1-sl)*(1-sl);
        const pnl = proceeds - p.cost; trades.push({tk:p.tk, ei:p.ei, xi:i, entry:p.entry, exit:fill, sh:p.sh, pnl, ret:pnl/p.cost, cost:p.cost, proceeds, stop:p.stop, tgt:p.tgt, bars:i-p.ei+1, mae:p.mae, mfe:p.mfe, why, sig:p.sig, riskPct:p.risk?p.risk/p.entry:null}); pos.splice(k,1) }
      else p.peak = Math.max(p.peak, D.c[i]);
    }
    // 2) entries: signals on the close of i-1 fill at the open of i
    const slots = maxPos - pos.length;
    if(slots>0){
      let cand = U.filter(t => sigs[t][i-1] && !pos.find(p=>p.tk===t) && inRange(i-1));
      if(S.mode==='portfolio') cand = cand.filter(t => (avgVal(t)[i-1]||0)/1e9 >= S.cost.minVal);
      cand.sort((a,b)=>rankScore(b,i-1)-rankScore(a,i-1));
      for(const t of cand.slice(0,slots)){ const D = DATA[t];
        if(S.cost.ara && D.o[i] >= D.c[i-1]*1.2) continue;
        const equityNow = cash + pos.reduce((s,p)=>s+p.sh*DATA[p.tk].o[i],0);
        const budget = S.mode==='single' ? Math.min(cash, equityNow*S.size.alloc/100) : Math.min(cash, equityNow/maxPos);
        const fill = D.o[i]*(1+sl), sh = Math.floor(budget/(fill*(1+fb))/100)*100; if(sh<100) continue;
        const cost = fill*sh*(1+fb); cash -= cost;
        const lv = exitLevels(P.exit, t, fill, i-1); pos.push({tk:t, ei:i, entry:fill, sh, cost, peak:fill, mae:0, mfe:0, sig:i-1, stop:lv.stop, tgt:lv.tgt, risk:lv.risk, trail:-1});
      }
    }
    const mv = pos.reduce((s,p)=>s+p.sh*DATA[p.tk].c[i],0);
    eq.push([i, cash+mv]); expo.push(mv/(cash+mv));
  }
  // benchmark: buy & hold of the stock (single) or IHSG (portfolio)
  const bc = closeOf(primaryBench()), bm = eq.map(([i]) => bc[i]); const b0 = bm[0];
  return {trades, eq, bench:bm.map(v=>v/b0*cap0), expo, cap0, first};
};

/* ---- 9 · STATISTICS ---- */
const mean = a => a.reduce((s,x)=>s+x,0)/(a.length||1);
const sd = a => { const m = mean(a); return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/((a.length-1)||1)) };
const skew = a => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**3,0)/a.length };
const kurt = a => { const m=mean(a), s=sd(a); return a.reduce((t,x)=>t+((x-m)/s)**4,0)/a.length };
const quant = (a,q) => { const s=[...a].sort((x,y)=>x-y); return s[Math.min(s.length-1, Math.max(0, Math.floor(q*(s.length-1))))] };
const ncdf = x => { const t=1/(1+.2316419*Math.abs(x)), d=.3989423*Math.exp(-x*x/2), p=d*t*(.3193815+t*(-.3565638+t*(1.781478+t*(-1.821256+t*1.330274)))); return x>0?1-p:p };
const ninv = p => { const a=[-39.69683028665376,220.9460984245205,-275.9285104469687,138.357751867269,-30.66479806614716,2.506628277459239], b=[-54.47609879822406,161.5858368580409,-155.6989798598866,66.80131188771972,-13.28068155288572], c=[-.007784894002430293,-.3223964580411365,-2.400758277161838,-2.549732539343734,4.374664141464968,2.938163982698783], d=[.007784695709041462,.3224671290700398,2.445134137142996,3.754408661907416];
  const q = p<.02425 ? Math.sqrt(-2*Math.log(p)) : p>1-.02425 ? Math.sqrt(-2*Math.log(1-p)) : 0;
  if(p<.02425) return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  if(p>1-.02425) return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1);
  const r=p-.5, s=r*r; return (((((a[0]*s+a[1])*s+a[2])*s+a[3])*s+a[4])*s+a[5])*r/(((((b[0]*s+b[1])*s+b[2])*s+b[3])*s+b[4])*s+1) };
const seriesStats = (vals, benchVals) => {
  const r = []; for(let k=1;k<vals.length;k++) r.push(vals[k]/vals[k-1]-1);
  const br = []; if(benchVals) for(let k=1;k<benchVals.length;k++) br.push(benchVals[k]/benchVals[k-1]-1);
  const years = vals.length/252, tot = vals.at(-1)/vals[0]-1, cagr = Math.pow(1+tot, 1/Math.max(years,.01))-1;
  const vol = sd(r)*Math.sqrt(252), down = Math.sqrt(mean(r.map(x=>Math.min(0,x)**2)))*Math.sqrt(252);
  let peak = vals[0], mdd = 0, dd = [], ddDur = 0, curDur = 0, maxDur = 0, ulc = 0;
  vals.forEach(v => { peak = Math.max(peak,v); const d = v/peak-1; dd.push(d); mdd = Math.min(mdd,d); ulc += d*d; curDur = d<0? curDur+1 : 0; maxDur = Math.max(maxDur,curDur) });
  const sharpe = sd(r) ? mean(r)/sd(r)*Math.sqrt(252) : 0, srd = sd(r) ? mean(r)/sd(r) : 0;
  const sk = r.length>3 ? skew(r) : 0, ku = r.length>3 ? kurt(r) : 3, n = r.length;
  const psr = (sr0) => ncdf(((srd - sr0)*Math.sqrt(n-1))/Math.sqrt(Math.max(1e-9, 1 - sk*srd + (ku-1)/4*srd*srd)));
  let beta = null, alpha = null, corr = null;
  if(br.length===r.length && br.length>2){ const mb = mean(br), mr = mean(r); let cov=0, vb=0, vr=0; for(let k=0;k<r.length;k++){ cov+=(r[k]-mr)*(br[k]-mb); vb+=(br[k]-mb)**2; vr+=(r[k]-mr)**2 } beta = cov/(vb||1); corr = cov/Math.sqrt((vb||1)*(vr||1)); alpha = (mr - beta*mb)*252 }
  const var95 = r.length ? quant(r,.05) : 0, tail = r.filter(x=>x<=var95);
  return {r, tot, cagr, vol, sharpe, sortino: down? mean(r)*252/down : 0, mdd, calmar: mdd? cagr/Math.abs(mdd) : 0, maxDur, ulcer:Math.sqrt(ulc/vals.length), var95, cvar95: tail.length?mean(tail):0, skew:sk, kurt:ku, beta, alpha, corr, dd, psr, srd, n,
          best: r.length?Math.max(...r):0, worst: r.length?Math.min(...r):0, pos: r.filter(x=>x>0).length/(r.length||1)};
};
const tradeStats = T => {
  const w = T.filter(t=>t.ret>0), l = T.filter(t=>t.ret<=0), gp = w.reduce((s,t)=>s+t.pnl,0), gl = -l.reduce((s,t)=>s+t.pnl,0);
  const fallbackRisk = Math.max(.01, sd(T.map(x=>x.ret))||.01), R = T.map(t=>t.ret/(t.riskPct||fallbackRisk));
  let cw=0, cl=0, mw=0, ml=0; T.forEach(t => { if(t.ret>0){ cw++; cl=0 } else { cl++; cw=0 } mw=Math.max(mw,cw); ml=Math.max(ml,cl) });
  const wr = T.length ? w.length/T.length : 0, aw = w.length?mean(w.map(t=>t.ret)):0, al = l.length?mean(l.map(t=>t.ret)):0;
  return {n:T.length, wins:w.length, losses:l.length, wr, aw, al, payoff: al? aw/Math.abs(al) : 0, pf: gl? gp/gl : (gp?Infinity:0), gp, gl, net:gp-gl,
    exp: T.length?mean(T.map(t=>t.ret)):0, expRp: T.length?(gp-gl)/T.length:0, sqn: R.length>1 ? Math.sqrt(Math.min(R.length,100))*mean(R)/(sd(R)||1) : 0, expR: R.length?mean(R):0,
    mw, ml, best: T.length?Math.max(...T.map(t=>t.ret)):0, worst: T.length?Math.min(...T.map(t=>t.ret)):0,
    hold: T.length?mean(T.map(t=>t.bars)):0, holdW: w.length?mean(w.map(t=>t.bars)):0, holdL: l.length?mean(l.map(t=>t.bars)):0,
    kelly: al&&aw ? wr - (1-wr)/(aw/Math.abs(al)) : 0, mae: T.length?mean(T.map(t=>t.mae)):0, mfe: T.length?mean(T.map(t=>t.mfe)):0 };
};
const dsr = (st, trials, srs) => { // Deflated Sharpe (Bailey & López de Prado): PSR against the expected max SR of `trials` attempts
  const N_ = Math.max(2, trials), v = srs.length>1 ? sd(srs)**2 : (1/st.n), g = .5772156649;
  const sr0 = Math.sqrt(v)*((1-g)*ninv(1-1/N_) + g*ninv(1-1/(N_*Math.E)));
  return {sr0: sr0*Math.sqrt(252), dsr: st.psr(sr0)} };
const monteCarlo = (T, cap0, runs=1000) => { if(T.length<3) return null; const n = T.length, paths = [], mdds = [], fin = []; let s2 = 7;
  const r2 = () => ((s2 = Math.imul(s2,1664525)+1013904223>>>0)/4294967296);
  for(let k=0;k<runs;k++){ let v = 1, pk = 1, md = 0; const path = [1]; for(let j=0;j<n;j++){ const t = T[Math.floor(r2()*n)]; v *= 1 + t.ret*(t.cost? 1 : 1)*(S.mode==='single'?S.size.alloc/100:1/S.maxPos); pk = Math.max(pk,v); md = Math.min(md, v/pk-1); path.push(v) } paths.push(path); mdds.push(md); fin.push(v-1) }
  const bands = [.05,.25,.5,.75,.95].map(q => Array.from({length:n+1},(_,j)=>quant(paths.map(p=>p[j]),q)));
  const below = Array.from({length:n+1},(_,j)=>paths.filter(p=>p[j]<1).length/runs);
  const actual = [1]; T.forEach(t => actual.push(actual.at(-1)*(1+t.ret*(S.mode==='single'?S.size.alloc/100:1/S.maxPos))));
  return {bands, mdds, fin, n, below, actual} };

/* ---- benchmark series ---- */
const primaryBench = () => S.mode==='single' ? (S.bench==='ihsg' ? 'IHSG' : S.ticker) : 'IHSG';
const closeOf = k => k==='IHSG' ? IHSG : DATA[k].c;

/* ---- 10 · RUN: the body of run()'s setTimeout, with the page state already set; returns the reference's S.result
   and the sensitivity cells' backtests in the grid's order (row by row) ---- */
export const runMockup = () => {
    const cellRuns = [];
    const t0 = performance.now();
    const res = backtest(); S.trials++;
    const vals = res.eq.map(x=>x[1]), st = seriesStats(vals, res.bench), bst = seriesStats(res.bench);
    const cut = S.oos ? Math.floor(vals.length*(1-S.oos/100)) : vals.length;
    const ins = cut>20 ? seriesStats(vals.slice(0,cut), res.bench.slice(0,cut)) : null, oos = S.oos && vals.length-cut>20 ? seriesStats(vals.slice(cut-1), res.bench.slice(cut-1)) : null;
    const cutDay = res.eq[cut-1] ? res.eq[cut-1][0] : null;
    const T = res.trades, ts = tradeStats(T), tsIn = tradeStats(T.filter(t=>cutDay==null||t.ei<=cutDay)), tsOut = tradeStats(T.filter(t=>cutDay!=null&&t.ei>cutDay));
    // sensitivity grid: first numeric threshold × stop loss (each cell is a full backtest; all count as trials)
    const GRID_Y = () => S.exit.stopMode==='pct' ? {k:'sl', lbl:'SL %', u:'%', step:2, min:1} : S.exit.stopMode==='atr' ? {k:'slAtr', lbl:'SL × ATR', u:'×', step:.5, min:.5} : S.exit.stopMode==='rr' ? {k:'slRR', lbl:'R:R (1 : x)', u:'', step:.5, min:.5} : {k:'hold', lbl:'Max hold (days)', u:'d', step:5, min:2};
    const c0 = S.conds.find(c=>c.on && !catOf(c).noVal);
    let grid = null;
    if(c0){ const base = c0.val, step = Math.max(1, Math.abs(base)*.2 || 1), xs = [-2,-1,0,1,2].map(k=>+(base+k*step).toFixed(2)), yk = GRID_Y(), y0 = S.exit[yk.k], ys = [-2,-1,0,1,2].map(k=>+Math.max(yk.min, y0+k*yk.step).toFixed(2));
      grid = {cond:c0, xs, ys, yk, cells:ys.map(y => xs.map(x => { const conds = S.conds.map(c=>c.id===c0.id?{...c,val:x}:c); const r = backtest({conds, exit:{[yk.k]:y}}); cellRuns.push(r); const v = r.eq.map(e=>e[1]); const s = seriesStats(v); const t = tradeStats(r.trades); return {sharpe:s.sharpe, cagr:s.cagr, pf:t.pf, n:t.n, mdd:s.mdd} }))};
      S.trials += 25;
    }
    const srs = grid ? grid.cells.flat().map(c=>c.sharpe/Math.sqrt(252)) : [];
    S.result = {...res, vals, st, bst, ins, oos, cut, cutDay, ts, tsIn, tsOut, grid, mc: monteCarlo(T, res.cap0), ds: dsr(st, S.trials, srs), ms: Math.round(performance.now()-t0)};
    return { R: S.result, cellRuns };
};

export { TICKERS, BROKERS, DAYS, N, IHSG, DATA, cache, memo, sma, ema, rsi, stoch, macd, adx, highest, rollsum, stdev, bullDiv, OPS, cmpSeries, CATALOG,
  srcOf, lagDiff, roll, REG_CALC, regReady, regDefaults, regEval, catOf, inRange, condReady, signalsFor, universe, atrS, lineSeries, chandelierS, atrOf,
  exitSeries, exitLevels, trailLevel, rankScore, backtest, mean, sd, skew, kurt, quant, ncdf, ninv, seriesStats, tradeStats, dsr, monteCarlo, primaryBench, closeOf };
