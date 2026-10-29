import sys, math
import numpy as np, talib
def load(path):
    rows=[]; cols=None
    for line in open(path):
        line=line.rstrip('\n')
        if line.startswith('(') or line=='---' or not line: continue
        parts=line.split(' | ')
        if cols is None: cols=parts; continue
        rows.append(parts)
    return cols, rows
def f(x):
    return float(x) if x not in ('',None) else np.nan
def rel(a,b):
    m=~(np.isnan(a)|np.isnan(b))
    if not m.any(): return (0,None)
    d=np.abs(a[m]-b[m])/np.maximum(np.maximum(np.abs(a[m]),np.abs(b[m])),1e-300)
    return int(m.sum()), float(d.max())
for t in sys.argv[1:]:
    cols, rows = load(f'v18_{t}.out')
    A={c: np.array([f(r[i]) for r in rows]) for i,c in enumerate(cols) if c!='date'}
    c=A['close']; h=A['high']; l=A['low']
    print('==',t,len(rows),'rows')
    # stored vs talib full history
    for name,ref in [('sma_20',talib.SMA(c,20)),('ema_12',talib.EMA(c,12)),('ema_200',talib.EMA(c,200)),('rsi_14',talib.RSI(c,14)),('atr_14',talib.ATR(h,l,c,14)),('adx_14',talib.ADX(h,l,c,14))]:
        print(' stored',name,'vs talib(full):',rel(A[name],ref))
    # derived from F04
    sd=talib.STDDEV(c,20,1)
    print(' stddev20 derived (upper-middle)/2 vs STDDEV:',rel((A['bb_upper_20']-A['bb_middle_20'])/2, sd))
    print(' natr derived 100*atr/close vs NATR:',rel(100*A['atr_14']/c, talib.NATR(h,l,c,14)))
    up,mid,lo=talib.BBANDS(c,20,2,2,0)
    pctb=(c-lo)/(up-lo); pctb_d=(c-A['bb_lower_20'])/(A['bb_upper_20']-A['bb_lower_20'])
    print(' %B derived vs BBANDS-based:',rel(pctb_d,pctb), 'abs max', float(np.nanmax(np.abs(pctb_d-pctb))))
    ppo=talib.PPO(c,12,26,1)
    print(' ppo line derived 100*(ema12-ema26)/ema26 vs TA PPO(EMA):',rel(100*(A['ema_12']-A['ema_26'])/A['ema_26'],ppo))
    # seed dependence: start the EMA-family on a shorter window (last 500 bars)
    for n in (500, 260):
        cs=c[-n:]; hs=h[-n:]; ls=l[-n:]
        for name,fn in [('ema_200',lambda: talib.EMA(cs,200)),('ema_50',lambda: talib.EMA(cs,50)),('rsi_14',lambda: talib.RSI(cs,14)),('adx_14',lambda: talib.ADX(hs,ls,cs,14)),('macd',lambda: talib.EMA(cs,12)-talib.EMA(cs,26))]:
            r=fn(); s=A[name][-n:]
            print(f'  last-{n}-bars recompute {name}: last-bar rel diff', abs(r[-1]-s[-1])/max(abs(s[-1]),1e-12))
