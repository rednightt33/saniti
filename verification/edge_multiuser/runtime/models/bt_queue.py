import math
def erlang_c(c, a):
    # probability an arrival waits, M/M/c, offered load a = lambda*s
    if a >= c: return 1.0
    s = sum(a**k/math.factorial(k) for k in range(c))
    top = a**c/math.factorial(c) * c/(c-a)
    return top/(s+top)
def p95_wait(c, lam, s, cs2):
    a = lam*s
    if a >= c: return float('inf'), 1.0, a/c
    C = erlang_c(c, a)
    mu = 1/s
    if C <= 0.05: t = 0.0
    else: t = math.log(C/0.05)/(c*mu - lam)
    # Allen-Cunneen style variability correction (arrivals Poisson ca2=1)
    t *= (1+cs2)/2
    return t, C, a/c
scen = {
 'T0 today: K=1, polling 2 s, no decoded cache': (1, 3.6, 0.26),
 'T1: event-driven waits, K=1': (1, 1.9, 0.9),
 'T2: + decoded cache, K=1': (1, 1.0, 1.0),
 'T2: K=2': (2, 1.0, 1.0),
 'T2: K=4': (4, 1.0, 1.0),
 'T2: K=8': (8, 1.0, 1.0),
}
for Z in (60, 120):
  print('think time Z =', Z, 's')
  for U in (10, 50, 200):
    lam = U/Z
    print(f'  U={U} lambda={lam:.3f}/s ({lam*3600:.0f} jobs/h)')
    for name,(c,s,cs2) in scen.items():
        t,C,rho = p95_wait(c, lam, s, cs2)
        print(f'    {name:48s} rho={rho:5.2f} P(wait)={C:5.3f} p95 wait={t:7.1f} s')
# capacity: jobs/hour per replica at rho=0.7
for name,(c,s,cs2) in scen.items():
    print(name, 'jobs/h at 70% =', round(0.7*c/s*3600))
# preview threads: previews of portfolio editors
print('previews')
for U in (10,50,200):
    lamp = U*0.5/10  # half the users edit portfolios, one preview per 10 s
    for c,s in ((1,3.0),(1,0.3),(2,0.3),(4,0.3)):
        t,C,rho = p95_wait(c, lamp, s, 1.0)
        print(f'  U={U} lam={lamp:.2f}/s P={c} s={s} rho={rho:.2f} p95 wait={t:.1f} s')
