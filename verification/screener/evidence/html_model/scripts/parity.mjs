// Read-only parity harness: prototype screener engine (XI + legacy helpers) vs repo indicators.ts F, on real OHLCV.
import fs from 'node:fs'; import vm from 'node:vm';
import { F, DEFAULTS } from '/home/user/saniti/apps/edge-bff/terminal/src/calc/indicators.ts';
const HTML = '/root/.claude/uploads/65bd49d0-9dca-5072-b7db-b62314cf2cd3/9c79bf9c-screener_EDGE_layout.html';
const DATA = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/html_model/data/';
const lines = fs.readFileSync(HTML, 'utf8').split('\n');
const code = lines.slice(749, 776).join('\n') + '\n' + lines.slice(865, 968).join('\n') +
  '\nglobalThis.__X = {XI, RSI, STOCH, MACD, DMI, ATR, BB, SUPERTREND, MFI, CMF, OBV};';
const xp = lines[863]; const XPARAM = JSON.parse(xp.slice(xp.indexOf('{'), xp.lastIndexOf('}') + 1));
const MAP = { sma:{line:'sma'}, ema:{line:'ema'}, wma:{line:'wma'}, hma:{line:'hma'}, kama:{line:'kama'}, macd:{a:'macd',b:'signal',hist:'histogram'},
  adx:{v:'adx',a:'plus_di',b:'minus_di'}, aroon:{a:'aroon_up',b:'aroon_down'}, supertrend:{line:'supertrend',dir:'direction'}, donchian:{upper:'upper',basis:'basis',lower:'lower'},
  keltner:{upper:'upper',basis:'basis',lower:'lower'}, psar:{line:'sar',dir:'direction'}, rsi:{v:'rsi'}, stoch_rsi:{a:'k',b:'d'}, stochastic:{a:'k',b:'d'}, williams_r:{v:'williams_r'},
  roc:{v:'roc'}, momentum:{v:'momentum'}, cci:{v:'cci'}, cmo:{v:'cmo'}, tsi:{a:'tsi',b:'signal'}, trix:{v:'trix'}, ultimate_osc:{v:'uo'}, awesome_osc:{v:'ao'},
  ppo:{a:'ppo',b:'signal',hist:'histogram'}, bop:{v:'bop'}, bollinger:{upper:'upper',basis:'basis',lower:'lower'}, bollinger_pctb:{v:'percent_b'}, bollinger_width:{v:'bandwidth'},
  atr:{v:'atr'}, natr:{v:'natr'}, stddev:{v:'stddev'}, hist_vol:{v:'historical_volatility'}, adr:{v:'adr'}, volume_sma:{line:'volume_sma'}, volume_ema:{line:'volume_ema'},
  rvol:{v:'rvol'}, pvo:{a:'pvo',b:'signal',hist:'histogram'}, volume_roc:{v:'volume_roc'}, obv:{line:'obv'}, pvt:{line:'pvt'}, vwma:{line:'vwma'},
  vwap:{basis:'vwap',upper:'upper1',lower:'lower1'}, adl:{line:'adl'}, cmf:{v:'cmf'}, chaikin_osc:{v:'chaikin_osc'}, mfi:{v:'mfi'}, force_index:{v:'force_index'},
  eom:{v:'eom'}, nvi:{line:'nvi'}, pvi:{line:'pvi'}, kvo:{a:'kvo',b:'signal'}, market_fi:{v:'market_fi'} };
const fin = v => typeof v === 'number' && Number.isFinite(v);
function load(tk){ const rows = fs.readFileSync(DATA + tk + '.txt', 'utf8').split('\n').filter(l => /^\d{4}-/.test(l)).map(l => l.split(','));
  const d = rows.map(r => r[0]), o = rows.map(r => +r[1]), h = rows.map(r => +r[2]), l = rows.map(r => +r[3]), c = rows.map(r => +r[4]), v = rows.map(r => +r[5]);
  return {d, o, h, l, c, v} }
function proto(b){ const N = b.c.length, ctx = vm.createContext({N, DAYS:b.d}); vm.runInContext(code, ctx); return ctx.__X }
const variant = process.argv[2] || 'default';
function params(key){ const pp = {}, pf = {}; for(const x of XPARAM[key] || []){ pp[x.k] = x.def; } Object.assign(pf, DEFAULTS[key]);
  if(variant === 'custom'){ for(const x of XPARAM[key] || []){ if(/length|smoothing|smooth_k|smooth_d/.test(x.k) && typeof x.def === 'number'){ const n = Math.round(x.def * 1.5) + 1; pp[x.k] = n; pf[x.k] = n } } }
  if(key === 'keltner'){ pf.use_exponential_ma = pp.use_exponential_ma === 'true' }
  for(const k of ['timeframe','reference_method','include_current_bar']) delete pf[k];
  return {pp, pf} }
const out = [];
for(const tk of (process.argv[3] || 'BBCA,GOTO,MTDL,DADA,ADRO').split(',')){
  const b = load(tk), N = b.c.length, X = proto(b), t = {tk, o:b.o, h:b.h, l:b.l, c:b.c, v:b.v, tp:b.c.map((x, i) => (x + b.h[i] + b.l[i]) / 3)};
  const B = {O:b.o, H:b.h, L:b.l, C:b.c, V:b.v, T:b.d};
  for(const key of Object.keys(MAP)){
    const {pp, pf} = params(key); const po = X.XI[key](t, pp), fo = F[key](B, pf);
    for(const [pk, fk] of Object.entries(MAP[key])){
      const a = po[pk], c2 = fo[fk]; if(!a || !c2){ out.push([tk, key, pk+'/'+fk, 'MISSING']); continue }
      const firstP = Array.from(a).findIndex(fin), firstF = c2.findIndex(fin);
      let maxRel = 0, nb = 0, diffBars = 0; let sc = 1e-12; for(let i = Math.max(0, N - 250); i < N; i++) if(fin(c2[i])) sc = Math.max(sc, Math.abs(c2[i])); for(let i = Math.max(0, N - 250); i < N; i++){ const x = a[i], y = c2[i]; if(!fin(x) && !fin(y)) continue; if(fin(x) !== fin(y)){ diffBars++; continue } nb++; const r = Math.abs(x - y) / sc; if(r > 1e-9) diffBars++; if(r > maxRel) maxRel = r }
      const lp = a[N - 1], lf = c2[N - 1];
      out.push([tk, key, pk + '/' + fk, firstP, firstF, fin(lp) ? +lp.toPrecision(8) : String(lp), fin(lf) ? +lf.toPrecision(8) : String(lf), maxRel.toExponential(2), diffBars]);
    }
  }
  // legacy technical helpers vs F
  const leg = [['RSI14', X.RSI(t.c, 14), F.rsi(B, {length:14}).rsi], ['STOCH.k', X.STOCH(t, 14, 3, 3).k, F.stochastic(B, {}).k], ['STOCH.d', X.STOCH(t, 14, 3, 3).d, F.stochastic(B, {}).d],
    ['MACD.m', X.MACD(t.c, 12, 26, 9).m, F.macd(B, {}).macd], ['MACD.sig', X.MACD(t.c, 12, 26, 9).sig, F.macd(B, {}).signal], ['MACD.hist', X.MACD(t.c, 12, 26, 9).hist, F.macd(B, {}).histogram],
    ['DMI.adx', X.DMI(t, 14).adx, F.adx(B, {}).adx], ['DMI.pdi', X.DMI(t, 14).pdi, F.adx(B, {}).plus_di], ['ATR14', X.ATR(t, 14), F.atr(B, {}).atr], ['BB.up', X.BB(t.c, 20, 2).up, F.bollinger(B, {}).upper],
    ['ST.dir', Array.from(X.SUPERTREND(t, 10, 3)), F.supertrend(B, {}).direction], ['MFI14', X.MFI(t, 14), F.mfi(B, {}).mfi], ['CMF20', X.CMF(t, 20), F.cmf(B, {}).cmf], ['OBV', X.OBV(t), F.obv(B, {}).obv]];
  for(const [nm, a, c2] of leg){ let maxRel = 0, diffBars = 0; let sc = 1e-12; for(let i = Math.max(0, N - 250); i < N; i++) if(fin(c2[i])) sc = Math.max(sc, Math.abs(c2[i])); for(let i = Math.max(0, N - 250); i < N; i++){ const x = a[i], y = c2[i]; if(!fin(x) && !fin(y)) continue; if(fin(x) !== fin(y)){ diffBars++; continue } const r = Math.abs(x - y) / sc; if(r > 1e-9) diffBars++; if(r > maxRel) maxRel = r }
    out.push([tk, 'LEGACY', nm, Array.from(a).findIndex(fin), c2.findIndex(fin), fin(a[N-1]) ? +a[N-1].toPrecision(8) : String(a[N-1]), fin(c2[N-1]) ? +c2[N-1].toPrecision(8) : String(c2[N-1]), maxRel.toExponential(2), diffBars]) }
}
console.log(['ticker','key','output','firstValidProto','firstValidF','lastProto','lastF','maxDiffLast250_scaledByMaxAbsF','barsDiffLast250'].join('\t'));
for(const r of out) console.log(r.join('\t'));
