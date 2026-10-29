# Shared terminal-api subscriber lock in today's design, with the backtest worker's grants on the same account (INFERENCE).
# hold per grant = 2 ms + 0.26 ms per 1,000 rows of the subscriber's last 24 h (terminal.md section 8, from FACT 0.85 ms at
# 3,271 rows); people 209 grant rows per daily user and day, 4 grants per open, peak opens 0.01 per daily user per second
# (terminal.md sections 7-8); worker grants from backtest.md section 6 (jobs x 4.1 + previews x 8 a month, 88 busy hours).
def lock(U):
    N = U / 0.3
    jobs = U * 30 * 4 * 22; prev = U * 60 * 4 * 22
    worker_month = jobs * 4.1 + prev * 8
    worker_day = worker_month / 22
    rows_day = 209 * N + worker_day
    hold_ms = 2 + 0.26 * rows_day / 1000
    demand = worker_month / (88 * 3600) + 0.01 * N * 4
    return rows_day, hold_ms, demand, demand * hold_ms / 1000
for U in (10, 20, 30, 40, 50, 60, 70, 80, 100, 200):
    r, h, d, rho = lock(U)
    print(f'U={U:3d} rows/day {r:9,.0f} hold {h:6.1f} ms demand {d:5.1f}/s busy {rho*100:6.0f} %')
# with T1 (service account with counters) the worker's rows leave the people's aggregate; with T2 every person has their own lock
