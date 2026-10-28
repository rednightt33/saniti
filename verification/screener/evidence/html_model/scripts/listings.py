import sys, re
html = open(sys.argv[1], encoding='utf-8').read().split('\n')
start = [i for i,l in enumerate(html) if l.startswith('const LISTINGS = `')][0]
rows = []
for i in range(start, start+200):
    l = html[i]
    if i == start: l = l.split('`',1)[1]
    end = '`' in l
    l = l.split('`')[0]
    if l.strip(): rows.append(l.split('|'))
    if end: break
D = sys.argv[2]
uni = {}
for l in open(D+'/universe.txt', encoding='utf-8'):
    p = l.rstrip('\n').split('|')
    if len(p) == 4 and p[0] != 'r': uni[p[0]] = p
last = {}
for l in open(D+'/lastclose.txt'):
    p = l.strip().split('|')
    if len(p) == 3 and p[0] != 'r': last[p[0]] = float(p[1])
print('listings:', len(rows))
flags = {'L':0,'3':0,'8':0,'S':0}
missing=[]; secmis=[]; indmis=set(); pxdiff=[]
for r in rows:
    tk,name,sec,ind,px,cap,fl,board = r
    for k in flags:
        if k in fl: flags[k]+=1
    if tk not in uni: missing.append(tk); continue
    u = uni[tk]
    if u[2] != sec: secmis.append((tk, sec, u[2]))
    if u[3] != ind: indmis.add((ind, u[3]))
    if tk in last: pxdiff.append((tk, float(px), last[tk], round(float(px)/last[tk]-1,3)))
print('flag counts L/3/8(raw)/S:', flags, ' IDX80 effective (8 or L):', sum(1 for r in rows if '8' in r[6] or 'L' in r[6]))
print('boards:', {b: sum(1 for r in rows if r[7]==b) for b in set(r[7] for r in rows)})
print('tickers not in IDX_Stock_Universe:', missing)
print('sector mismatches:', secmis)
print('industry label mismatches (prototype -> DB):', len(indmis)); [print('  ', a, '->', b) for a,b in sorted(indmis)]
big = [x for x in pxdiff if abs(x[3])>0.25]
print('price vs DB last close, |diff|>25%:', len(big), big[:30])
