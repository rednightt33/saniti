# Backtest monthly cost model (INFERENCE; inputs listed in backtest.md section 6)
RAM, CPU, EGR, VOL, BKT = 10.0, 20.0/2_592_000, 0.05, 0.15, 0.015   # USD per GB-month, per vCPU-s, per GB, per GB-month (volume), per GB-month (bucket)
BUSY_H, DAYS = 4, 22
Z = 120                                   # think time between runs of an active user (s): central
JOBS_PER_UH = 3600 / Z                    # 30
PREV_PER_UH = 0.5 * 0.5 * 240             # half the users edit portfolios, half of the time, one server preview per 15 s -> 60
for U in (10, 50, 200):
    jobs = U * JOBS_PER_UH * BUSY_H * DAYS
    prev = U * PREV_PER_UH * BUSY_H * DAYS
    # today: 2.0 vCPU-s per job (mix 70 % single 0.5 s, 30 % 12-stock flow portfolio 5.5 s), 1.6 per preview
    cpu_t = (jobs * 2.0 + prev * 1.6) * CPU
    # proposed: 0.7 per job, 0.25 per preview (decoded cache), minus reuse 10 % of jobs
    cpu_p = (jobs * 0.9 * 0.7 + prev * 0.25) * CPU
    # RAM today: 1 replica, 2 threads with per-thread gzip caches ~0.5 GB each when warm, base 0.1 -> ~1.1 GB resident all month
    ram_t = 1.1 * RAM
    K = {10: 2, 50: 4, 200: 8}[U]
    peak = 0.1 + K * 0.3 + 0.8
    avg = (BUSY_H * DAYS * peak + (720 - BUSY_H * DAYS) * 0.3) / 720
    ram_p = avg * RAM
    # results: 136 KB per job (FACT average), 30-day retention in Postgres; proposed per-owner cap 50 newest (owners ~ 3U daily)
    res_gb_t = jobs * 136e3 / 1e9
    res_gb_cap = min(res_gb_t, 3 * U * 50 * 136e3 / 1e9)
    egress_gb = jobs * 0.15e6 / 1e9          # one result view per job, about 150 KB gzip
    grants_t = jobs * 4.1 + prev * 8
    print(f"U={U}: jobs/month {jobs:,.0f}  previews/month {prev:,.0f}  K={K}")
    print(f"   CPU today USD {cpu_t:6.2f}   proposed USD {cpu_p:6.2f}")
    print(f"   RAM today USD {ram_t:6.2f}   proposed USD {ram_p:6.2f} (peak {peak:.1f} GB busy hours, avg {avg:.2f} GB)")
    print(f"   results today {res_gb_t:6.1f} GB = USD {res_gb_t*VOL:5.2f} (Postgres volume)  with cap {res_gb_cap:5.1f} GB = USD {res_gb_cap*VOL:5.2f}; in a bucket USD {res_gb_t*BKT:5.2f}")
    print(f"   egress results {egress_gb:6.1f} GB = USD {egress_gb*EGR:5.2f}")
    print(f"   terminal-api grants today {grants_t:,.0f}/month = {grants_t/(BUSY_H*DAYS*3600):.1f}/s in busy hours")
    tot_t = cpu_t + ram_t + res_gb_t*VOL + egress_gb*EGR
    tot_p = cpu_p + ram_p + res_gb_cap*VOL + egress_gb*EGR
    print(f"   TOTAL today-architecture USD {tot_t:6.2f} (if it could serve it)  proposed USD {tot_p:6.2f}  (+ USD 3-5 for a 2nd replica if chosen)")
