"""SILO vs POOL vs POOL-SLEEP vs HYBRID: monthly Railway compute cost and cold-start exposure for N = 10, 50, 200
external users (Screener, Backtest, Terminal; AI out of scope). Inputs: measured in this benchmark (bench/raw), FACT from
the repository, or ASSUMPTION (the usage profile). Prices: Railway docs (RAM USD 10/GB-month, CPU USD 20/vCPU-month).
Usage: python3 -I cost_model.py <out.json> [--tail 7.5] [--seed 1]"""
import json, math, random, sys

out = sys.argv[1]
arg = lambda k, d: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
RAM_GB_MIN = 10 / 43200          # USD per GB-minute (FACT, pricing page)
CPU_S = 20 / (30 * 86400)        # USD per vCPU-second (FACT)
MONTH_MIN = 43200

# ---- usage profile (ASSUMPTION; replace with P29 numbers / logs) ----
TD = 21                 # trading days a month; no weekend sessions
S = int(arg('--sessions', 2))   # sessions per user per trading day
L = arg('--minutes', 20.0)       # active minutes per session
TAIL = arg('--tail', 7.5)   # minutes awake after the last request (docs 5-10; probe 4.5-6.5)
SCR_RUNS, SCR_LOOKUPS = 15, 10    # uncached custom screens, default/preset lookups per session
BT_JOBS, BT_PREV = 3, 6           # backtest jobs, server previews per session
H = 0.5                 # pool result-cache hit share for custom screens (6d.9)
PEAK = 0.3              # share of daily users active at the same moment at the peak (6d / capacity report)
REFRESH_PER_USER_DAY = 0.25       # SILO: an awake copy sees a publication land during a session (ASSUMPTION)

# ---- measured / recorded inputs ----
SCR = dict(rss_awake=0.55,        # GB: measured 0.73 at ready (K=1), 0.36 after ~60 s idle; 0.52 steady with K=2/4
           rss_pool=0.52,         # GB per pooled replica, K=2 steady (measured 0.516-0.521)
           cold_cpu=20.0,         # vCPU-s per cold start, data part (measured 19.0-20.7 at K=1; 22.3-25.1 at K=4)
           run_cpu=0.22,          # vCPU-s per uncached 3-condition custom screen (measured 0.19-0.27)
           lookup_cpu=0.005,      # vCPU-s per default lookup (measured 3.4-9.7 ms)
           bytes_per_load=11_758_425)   # proposed xsection price file (measured, this bench)
BT = dict(rss_awake=0.25,         # GB: measured 0.11-0.23 local (price-only); 0.32 dev cold API sequence (README:440)
          rss_pool=0.40,          # GB average, pooled K=2 (INFERENCE between 0.3 idle and 0.1+K*0.3+0.8 busy, backtest.md 6)
          cold_cpu=1.0,           # vCPU-s boot + catalog (INFERENCE; boot 0.26-0.32 s wall, catalog small)
          job_cpu=2.0, prev_cpu=1.0)   # vCPU-s (backtest.md 6 "today 2.0 per job"; preview between 1.6 today and 0.25)
TAPI = dict(usd_copy=1.50)        # terminal-api copy always on: 0.142 GB + 0.004 vCPU (Railway usage, capacity 2.2); its DB pool keeps it awake
R_SCR = 2                         # pooled screener replicas (P32 availability floor)
PUBS = 62                         # publications a month (2 a day, publisher.py:17-18)

def silo(N, tapi_pooled=False):
    sessions = N * TD * S
    awake_min = sessions * (L + TAIL + 0.4)
    scr_ram = awake_min * SCR['rss_awake'] * RAM_GB_MIN
    scr_cold_cpu = sessions * SCR['cold_cpu'] + N * TD * REFRESH_PER_USER_DAY * SCR['cold_cpu']
    scr_work_cpu = sessions * (SCR_RUNS * SCR['run_cpu'] + SCR_LOOKUPS * SCR['lookup_cpu'])     # no cross-user cache
    bt_ram = awake_min * BT['rss_awake'] * RAM_GB_MIN
    bt_cpu = sessions * (BT['cold_cpu'] + BT_JOBS * BT['job_cpu'] + BT_PREV * BT['prev_cpu'])
    tapi = (2 if N >= 200 else 1) * 1.2 if tapi_pooled else N * TAPI['usd_copy']
    usd = dict(screener=scr_ram + (scr_cold_cpu + scr_work_cpu) * CPU_S, backtest=bt_ram + bt_cpu * CPU_S, terminal_api=tapi)
    return dict(model='SILO (screener + backtest per user; terminal-api pooled)' if tapi_pooled else 'SILO (all three per user)', usd=usd, total=sum(usd.values()),
                services=(2 * N + 1) if tapi_pooled else 3 * N, cold_starts=2 * sessions,
                screener_snapshot_builds=sessions + N * TD * REFRESH_PER_USER_DAY,
                screener_download_gb=(sessions + N * TD * REFRESH_PER_USER_DAY) * SCR['bytes_per_load'] / 1e9,
                init_cpu_hours=(scr_cold_cpu + sessions * BT['cold_cpu']) / 3600,
                sessions_with_cold_wait=1.0, db_connections_min=2 if tapi_pooled else 2 * N)

def pool(N, r_scr=R_SCR):
    sessions = N * TD * S
    scr_ram = r_scr * SCR['rss_pool'] * MONTH_MIN * RAM_GB_MIN
    grace = r_scr * PUBS * 10 * SCR['rss_pool'] * RAM_GB_MIN          # previous snapshot kept 10 min per publication
    scr_cpu = r_scr * PUBS * SCR['cold_cpu'] + sessions * (SCR_RUNS * (1 - H) * SCR['run_cpu'] + SCR_LOOKUPS * SCR['lookup_cpu'])
    bt_ram = BT['rss_pool'] * MONTH_MIN * RAM_GB_MIN
    bt_cpu = sessions * (BT_JOBS * BT['job_cpu'] + BT_PREV * BT['prev_cpu'])
    tapi_n = 2 if N >= 200 else 1
    usd = dict(screener=scr_ram + grace + scr_cpu * CPU_S, backtest=bt_ram + bt_cpu * CPU_S, terminal_api=tapi_n * 1.2)
    # capacity check (6d.9 formula, measured c_run): editing users per replica at K=2, u=0.7, r=0.15/s burst
    per_replica = 2 * 0.7 / (0.15 * (1 - H) * SCR['run_cpu'])
    return dict(model='POOL 24/7', usd=usd, total=sum(usd.values()), services=r_scr and 3, screener_replicas=r_scr,
                peak_users=math.ceil(PEAK * N), screener_editing_users_per_replica=round(per_replica),
                screener_snapshot_builds=r_scr * PUBS, screener_download_gb=r_scr * PUBS * SCR['bytes_per_load'] / 1e9,
                init_cpu_hours=r_scr * PUBS * SCR['cold_cpu'] / 3600, sessions_with_cold_wait=0.0, db_connections_min=2 * tapi_n)

PUB_DONE = (8 * 60 + 5, 20 * 60 + 3)   # WIB: the 07:30 and 19:00 runs finish about 08:05 / 20:03 (ERRORS M250: 13:03 UTC)
def pool_scheduled(N, hours=14.0):
    """Pool with Serverless on, kept awake by a keep-alive ping every <5 min from 08:00 to 22:00 WIB on trading days (inbound
    traffic answered counts as outbound, docs); asleep at night and on non-trading days; one wake per trading day at 08:00."""
    sessions = N * TD * S; aw = TD * hours * 60
    scr_ram = R_SCR * SCR['rss_pool'] * aw * RAM_GB_MIN + R_SCR * TD * 10 * SCR['rss_pool'] * RAM_GB_MIN   # + grace at the evening publication
    scr_cpu = R_SCR * TD * 2 * SCR['cold_cpu'] + sessions * (SCR_RUNS * (1 - H) * SCR['run_cpu'] + SCR_LOOKUPS * SCR['lookup_cpu'])
    bt_ram = BT['rss_pool'] * aw * RAM_GB_MIN
    bt_cpu = sessions * (BT_JOBS * BT['job_cpu'] + BT_PREV * BT['prev_cpu']) + TD * BT['cold_cpu']
    tapi_n = 2 if N >= 200 else 1
    usd = dict(screener=scr_ram + scr_cpu * CPU_S, backtest=bt_ram + bt_cpu * CPU_S, terminal_api=tapi_n * 1.2)
    return dict(model=f'POOL, Serverless + kept awake {hours:g} h on trading days', usd=usd, total=sum(usd.values()), awake_hours_month=TD * hours,
                wakes_month=TD, sessions_with_cold_wait=0.0, screener_snapshot_builds=R_SCR * TD * 2, services=3)

WINDOWS = [(8 * 60, 10 * 60, 0.45), (15 * 60 + 30, 17 * 60 + 30, 0.25), (19 * 60, 22 * 60, 0.30)]   # WIB, ASSUMPTION
def awake_union(N, rng, prewarm=True):
    """One trading day: each user's S sessions in S distinct windows (weighted), uniform start; the pool is awake over
    the union of [start, start + L + TAIL]; a cron pre-warm at 08:00 opens [480, 480 + TAIL]. Returns (awake minutes,
    wakes, sessions that start while the pool sleeps)."""
    iv, starts = [], []
    if prewarm: iv.append((480.0, 480.0 + TAIL + 0.4))
    for _ in range(N):
        ws = rng.choices(range(3), weights=[w[2] for w in WINDOWS], k=10)
        chosen = []
        for w in ws:
            if w not in chosen: chosen.append(w)
            if len(chosen) == S: break
        for w in chosen:
            a, b, _ = WINDOWS[w]; s = rng.uniform(a, b - L); starts.append(s); iv.append((s, s + L + TAIL))
    iv.sort(); merged = []
    for a, b in iv:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], b)
        else: merged.append([a, b])
    awake = sum(b - a for a, b in merged)
    opened = sum(1 for a, b in merged if any(abs(a - s) < 1e-9 for s in starts))   # sessions that wake a sleeping pool
    pubs = sum(1 for t in PUB_DONE if any(a <= t <= b for a, b in merged))          # publications landing while awake
    return awake, len(merged), opened, pubs

def pool_sleep(N, rng, days=200):
    sessions = N * TD * S
    aw, wk, cold, pa = 0.0, 0.0, 0.0, 0.0
    for _ in range(days):
        a, w, c, p = awake_union(N, rng); aw += a; wk += w; cold += c; pa += p
    aw, wk, cold, pubs_awake = aw / days * TD, wk / days * TD, cold / days * TD, pa / days * TD
    scr_ram = R_SCR * SCR['rss_pool'] * aw * RAM_GB_MIN
    scr_cpu = R_SCR * (wk + pubs_awake) * SCR['cold_cpu'] + sessions * (SCR_RUNS * (1 - H) * SCR['run_cpu'] + SCR_LOOKUPS * SCR['lookup_cpu'])
    bt_ram = BT['rss_pool'] * aw * RAM_GB_MIN
    bt_cpu = sessions * (BT_JOBS * BT['job_cpu'] + BT_PREV * BT['prev_cpu']) + wk * BT['cold_cpu']
    tapi_n = 2 if N >= 200 else 1
    usd = dict(screener=scr_ram + scr_cpu * CPU_S, backtest=bt_ram + bt_cpu * CPU_S, terminal_api=tapi_n * 1.2)
    return dict(model='POOL, serverless + 08:00 pre-warm', usd=usd, total=sum(usd.values()), awake_hours_month=round(aw / 60, 1),
                wakes_month=round(wk, 1), sessions_opening_a_cold_pool=round(cold, 1), sessions_month=sessions,
                sessions_with_cold_wait=round(cold / sessions, 4), screener_snapshot_builds=round(R_SCR * (wk + pubs_awake), 1))

def hybrid(N, base, P=None):
    P = P if P is not None else max(1, round(0.1 * N))   # premium/heavy users with a dedicated, always-on backtest worker
    ded = P * BT['rss_pool'] * MONTH_MIN * RAM_GB_MIN
    usd = dict(base['usd']); usd['dedicated_backtest'] = ded
    return dict(model=f'HYBRID ({base["model"]} + {P} dedicated always-on backtest workers)', usd=usd, total=sum(usd.values()),
                dedicated=P, sessions_with_cold_wait=base['sessions_with_cold_wait'], services=3 + P)

rng = random.Random(int(arg('--seed', 1)))
res = {'params': dict(TD=TD, S=S, L=L, TAIL=TAIL, SCR=SCR, BT=BT, TAPI=TAPI, H=H, PEAK=PEAK, WINDOWS=WINDOWS, R_SCR=R_SCR), 'rows': []}
for N in (10, 50, 200):
    s, s2, p = silo(N), silo(N, True), pool(N)
    ps, pk = pool_sleep(N, rng), pool_scheduled(N)
    for r in (s, s2, p, ps, pk, hybrid(N, pk, 1), hybrid(N, pk)):
        r['N'] = N; r['per_user'] = r['total'] / N
        r['usd'] = {k: round(v, 2) for k, v in r['usd'].items()}; r['total'] = round(r['total'], 2); r['per_user'] = round(r['per_user'], 3)
        res['rows'].append(r)
json.dump(res, open(out, 'w'), indent=1)
for r in res['rows']:
    print(json.dumps({k: r[k] for k in r if k not in ('params',)}))
