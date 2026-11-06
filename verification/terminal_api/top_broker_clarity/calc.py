import json, collections
R=json.load(open('bbri60.json'))['rows']; PX=dict((d,c) for d,c in json.load(open('bbri_px.json'))['rows'])
dates=sorted({r[0] for r in R})
by=collections.defaultdict(list)
for d,b,i,bv,sv in R: by[d].append((b,i,bv,sv))
def agg(ds, inv=None):
    m=collections.defaultdict(lambda:[0.0,0.0])
    for d in ds:
        for b,i,bv,sv in by[d]:
            if inv and i!=inv: continue
            m[b][0]+=bv; m[b][1]+=sv
    return m
def bal(m,n=3):
    nets=sorted(((v[0]-v[1],b) for b,v in m.items()), key=lambda x:(-x[0],x[1]))
    buyers=[x for x in nets if x[0]>0][:n]; sellers=sorted([x for x in nets if x[0]<0])[:n]
    buy=sum(x[0] for x in buyers); sell=-sum(x[0] for x in sellers); total=sum(v[0] for v in m.values())
    return dict(buyers=[(b,round(v)) for v,b in buyers], sellers=[(b,round(v)) for v,b in sellers], buy=buy, sell=sell, total=total, ratio=(buy-sell)/total if total else 0,
                allbuy=sum(x[0] for x in nets if x[0]>0))
def verdict(r): a=abs(r); return 'Neutral' if a<.06 else ('Big ' if a>=.10 else '')+('Acc' if r>0 else 'Dist')
out={'dates':dates[-20:],'px':{d:PX.get(d) for d in dates}}
for W in (5,20):
    ds=dates[-W:]
    A=bal(agg(ds)); F=bal(agg(ds,'Foreign')); D=bal(agg(ds,'Domestic'))
    # per-broker foreign/domestic split of the top buyers/sellers
    fa=agg(ds,'Foreign'); da=agg(ds,'Domestic')
    split={b:(round(fa[b][0]-fa[b][1]), round(da[b][0]-da[b][1])) for b,_ in A['buyers']+A['sellers']}
    # history: every rolling W window in 60 sessions
    hist=[bal(agg(dates[k-W:k]))['ratio'] for k in range(W, len(dates)+1)]
    pct=sum(1 for h in hist if h<=A['ratio'])/len(hist)
    # daily ratios (all, foreign, domestic) and persistence
    daily=[(d, bal(agg([d]))['ratio'], bal(agg([d],'Foreign'))['ratio'], bal(agg([d],'Domestic'))['ratio']) for d in ds]
    pos=sum(1 for x in daily if x[1]>0)
    # group consistency: the window's top-3 buyers, days their combined net >0
    grp=[b for b,_ in A['buyers']]
    gdays=sum(1 for d in ds if sum(agg([d])[b][0]-agg([d])[b][1] for b in grp)>0)
    avgbuy=sum(sum(x[2] for x in by[d]) for d in ds)/W
    fnet=sum(v[0]-v[1] for v in fa.values())
    p0=PX.get(dates[-W-1]); p1=PX.get(ds[-1])
    out[W]=dict(all=A,foreign=F,domestic=D,split=split,hist_n=len(hist),hist_min=min(hist),hist_max=max(hist),pct=pct,
        daily=daily,pos=pos,gdays=gdays,grp=grp,avgbuy=avgbuy,fnet=fnet,dnet=-fnet,pxchg=(p1/p0-1) if p0 and p1 else None,
        days_turn=(A['buy']-A['sell'])/avgbuy, top1share=A['buyers'][0][1]/A['buy'] if A['buyers'] else 0, top3share=A['buy']/A['allbuy'] if A['allbuy'] else 0,
        v_all=verdict(A['ratio']),v_f=verdict(F['ratio']),v_d=verdict(D['ratio']))
    o=out[W]; print(W, 'all',round(A['ratio']*100,2),o['v_all'],'F',round(F['ratio']*100,2),o['v_f'],'D',round(D['ratio']*100,2),o['v_d'],
        'pct',round(pct*100),'hist',round(o['hist_min']*100,1),round(o['hist_max']*100,1),'pos',pos,'gdays',gdays,grp,'px',o['pxchg'] and round(o['pxchg']*100,2),
        'turn',round(o['days_turn'],2),'top1',round(o['top1share']*100),'top3',round(o['top3share']*100),'fnet',round(fnet/1e9,1))
    print('  buyers',A['buyers'],'sellers',A['sellers']); print('  split',{k:(round(a/1e9,1),round(b/1e9,1)) for k,(a,b) in split.items()})
    print('  F buyers',F['buyers'][:3],'D buyers',D['buyers'][:3])
json.dump(out,open('topbk.json','w'),default=str)
for W in (5,20):
    o=out[W]
    for side in ('Foreign','Domestic'):
        h=[bal(agg(dates[k-W:k],side))['ratio'] for k in range(W,len(dates)+1)]
        cur=o['foreign' if side=='Foreign' else 'domestic']['ratio']
        o['pct_'+side[0]]=sum(1 for x in h if x<=cur)/len(h); o['hmin_'+side[0]]=min(h); o['hmax_'+side[0]]=max(h)
    print(W,'pctF',round(o['pct_F']*100),round(o['hmin_F']*100,1),round(o['hmax_F']*100,1),'pctD',round(o['pct_D']*100),round(o['hmin_D']*100,1),round(o['hmax_D']*100,1))
json.dump(out,open('topbk.json','w'),default=str)
