# Combined monthly cost of the Terminal, Backtest and Screener runtime (INFERENCE; inputs cited in RUNTIME.md section 6).
# One basis for all three: U = users active at the same moment in busy hours; daily users N = U / 0.3 (the 30 % at-peak
# ratio used by terminal.md section 7 and 06d.9). Prices: Railway docs read 2026-10-28 (06d.1).
RAM, CPU_S, EGR, VOL, BKT = 10.0, 20.0 / 2_592_000, 0.05, 0.15, 0.015
PEAK_SHARE = 0.3
TRADING_DAYS_T, TRADING_DAYS_S, BT_DAYS, BT_BUSY_H = 21, 21, 22, 4

def terminal(U, proposed):
    N = U / PEAK_SHARE
    api = 2.4 if proposed else 1.2                         # 1 replica USD 1.2 (7-day metrics); 2 replicas (D-T3)
    pub, bucket = 0.75, 0.01
    egress = N * 0.056 * EGR                               # 56 MB per daily user-month (terminal.md section 7)
    pg = N * ((0.06 if proposed else 0.21) / 200)          # grant rows kept 90 days, scaled from terminal.md (200 daily)
    cpu = N * ((0.02 if proposed else 0.07) / 200)         # grant CPU, same scaling
    fixed = api + pub + bucket
    return fixed, egress + pg + cpu

def backtest(U, proposed):
    jobs = U * 30 * BT_BUSY_H * BT_DAYS                    # one job per 120 s per active user (backtest.md section 6)
    prev = U * 60 * BT_BUSY_H * BT_DAYS                    # half edit portfolios, half the time, one preview per 15 s
    if proposed:
        K = {10: 2, 50: 4, 200: 8}[U]
        peak = 0.1 + K * 0.3 + 0.8
        busy_h = BT_BUSY_H * BT_DAYS
        fixed = (720 - busy_h) / 720 * 0.3 * RAM           # idle floor (B3 idle trim), whole month at 0.3 GB outside busy hours
        ram_busy = busy_h / 720 * peak * RAM
        cpu = (jobs * 0.9 * 0.7 + prev * 0.25) * CPU_S
        res = min(jobs * 136e3, 3 * U * 50 * 136e3) / 1e9 * VOL   # B11: newest 50 per owner, about 3U owners
        grants_api = 0.0                                   # B7: warm runs make no grants
        grants_log = 0.0
    else:
        fixed = 1.1 * RAM                                  # two per-thread gzip caches resident all month
        ram_busy = 0.0
        cpu = (jobs * 2.0 + prev * 1.6) * CPU_S
        res = jobs * 136e3 / 1e9 * VOL                     # 30 days in Postgres
        grants = jobs * 4.1 + prev * 8                     # grants per month (backtest.md section 6)
        grants_api = grants * 0.010 * CPU_S                # about 10 ms terminal-api CPU per grant (terminal.md 4.5)
        grants_log = grants * 3 * 357 / 1e9 * VOL          # access_log rows kept 90 days, 357 B per row
    egress = jobs * 0.15e6 / 1e9 * EGR
    return fixed, ram_busy + cpu + res + egress + grants_api + grants_log, jobs, prev

def screener(U):
    N = U / PEAK_SHARE
    # replicas and K: P32 two replicas from the first external user; K chosen so the worker queue p95 stays <= 300 ms
    # (M/M/c with the bt_queue.py correction, rt_cost.py screener_queue below); RSS 0.4 + 0.1 x K GB per replica,
    # interpolated from 06d.4 (0.6 GB at K = 2, 0.8 GB at K = 4)
    R, K = {10: (2, 2), 50: (2, 3), 200: (2, 8)}[U]
    rss = 0.4 + 0.1 * K
    fixed = R * rss * RAM
    runs_uncached = N * 200 * 0.5 * TRADING_DAYS_S          # 06d.9: 200 runs a day, half from a cache
    cpu = runs_uncached * 0.5 * CPU_S + R * 62 * 20 * CPU_S
    egress = N * 0.1 * EGR                                  # 100 MB per daily user-month
    bucket = 0.1 * BKT
    return fixed, cpu + egress + bucket, R, K

def screener_queue(U, R, K, s=0.5):
    import math
    lam = U / R * 0.15 * 0.5                                # 06d.9: r = 0.15 runs/s per editing user, half uncached
    a = lam * s
    if a >= K: return float('inf')
    tot = sum(a ** k / math.factorial(k) for k in range(K)); top = a ** K / math.factorial(K) * K / (K - a)
    C = top / (tot + top)
    return 0.0 if C <= 0.05 else math.log(C / 0.05) / (K / s - lam)

def edge_bff(U):
    # today USD 1.0 a month for all tabs (capacity audit 2.2); at U = 200 a second uvicorn process (+0.1 GB) (INFERENCE)
    return 1.0 + (1.0 if U == 200 else 0.0), 0.0

if __name__ == '__main__':
    for U in (10, 50, 200):
        N = U / PEAK_SHARE
        tf, tv = terminal(U, True); tf0, tv0 = terminal(U, False)
        bf, bv, jobs, prev = backtest(U, True); bf0, bv0, _, _ = backtest(U, False)
        sf, sv, R, K = screener(U)
        ef, ev = edge_bff(U)
        fixed = tf + bf + sf + ef; var = tv + bv + sv + ev
        print(f'U={U} at once, N={N:.0f} daily users')
        print(f'  Terminal  proposed fixed {tf:5.2f} var {tv:5.2f} = {tf+tv:6.2f} | today design {tf0+tv0:6.2f}')
        print(f'  Backtest  proposed fixed {bf:5.2f} var {bv:5.2f} = {bf+bv:6.2f} | today design {bf0+bv0:6.2f} (jobs {jobs:,.0f}, previews {prev:,.0f})')
        print(f'  Screener  proposed fixed {sf:5.2f} var {sv:5.2f} = {sf+sv:6.2f} (R={R}, K={K}, queue p95 {screener_queue(U, R, K):.2f} s)')
        print(f'  edge-bff  fixed {ef:5.2f}')
        print(f'  TOTAL proposed {fixed+var:6.2f} (fixed {fixed:5.2f}, variable {var:5.2f}); per daily user {(fixed+var)/N:5.3f}, variable per daily user {var/N:5.3f}')
