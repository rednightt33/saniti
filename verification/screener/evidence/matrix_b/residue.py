import json, os, numpy as np, talib
D = os.path.dirname(os.path.abspath(__file__))
def arr(x): return np.array([np.nan if v is None else v for v in x], dtype=np.float64)
for t in ['BNBR','GOTO','BLTA']:
    d = json.load(open(f'{D}/data/{t}.json')); r = json.load(open(f'{D}/ts/{t}.json'))['res']
    H, L, C, V = (arr(d[k]) for k in 'HLCV')
    a = arr(r['adr']['adr']); b = talib.SMA(H-L, 14)
    m = ~np.isnan(a) & ~np.isnan(b) & (np.abs(a-b) > 0)
    print(t, 'ADR: bars TS!=TA-Lib', int(m.sum()), 'max abs diff', float(np.nanmax(np.abs(a-b))), 'TS min', float(np.nanmin(a)), 'TS negatives', int((a<0).sum()), 'TS tiny nonzero (0<|x|<1e-9)', int(((np.abs(a)>0)&(np.abs(a)<1e-9)).sum()), 'TA-Lib negatives', int((b<0).sum()), 'TA-Lib tiny', int(((np.abs(b)>0)&(np.abs(b)<1e-9)).sum()))
    c = arr(r['cmf']['cmf']); print(t, 'CMF tiny nonzero (0<|x|<1e-12)', int(((np.abs(c)>0)&(np.abs(c)<1e-12)).sum()), 'exact zeros', int((c==0).sum()))
    s = arr(r['stddev']['stddev']); print(t, 'STDDEV tiny (0<x<1e-4)', int(((s>0)&(s<1e-4)).sum()), 'zeros', int((s==0).sum()))
    p = arr(r['bollinger_pctb']['percent_b']); w = arr(r['bollinger_width']['bandwidth']); print(t, '%B null after warmup', int(np.isnan(p[19:]).sum()), 'bandwidth zeros', int((w==0).sum()), 'bandwidth tiny(0<x<1e-3)', int(((w>0)&(w<1e-3)).sum()), '%B abs>5', int((np.abs(p)>5).sum()))
