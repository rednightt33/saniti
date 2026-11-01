"""EXEC-FI-DATE M324 (user go 2026-11-01: "Ok untuk koreksi 323 324"): correct Price_Fixed_Income against a fresh pull
of the source with the ingest's own client and date rule (PROVIDER_SESSION_START, migration 20261101_002).

Every series is pulled PULLS times (params "pulls", default 3; a new socket each). A stored bar equal to any pulled version
is kept; other dates are used only when every pull agrees, else reported as unstable and left as stored. For every series
of Universe_Fixed_income, inside [the series' first stored date, the market's latest completed session]:
  - a source bar whose date is missing in the table, or whose open/high/low/close differ, is written through the
    loader's own bulk_upsert_prices (validated by validate_price_row; market_close_at per date);
  - a stored 1D row on a date the source does not have (inside the source's range) is deleted.
Nothing else is touched (rows equal to the source keep their ingestion_time). The changes come from the comparison,
no date is listed by hand. DRYRUN reports and writes nothing; APPLY does it in one transaction and reads back.
params.json: {"mode": "DRYRUN"|"APPLY"}. Prints OUT lines, then JOB_DONE. No secret is printed.
"""
import json, os, time
from datetime import datetime, timezone
import psycopg
import fixed_income_update as f

params = json.load(open('params.json'))
mode = params['mode']
PULLS = int(params.get('pulls', 3))
assert mode in ('DRYRUN', 'APPLY')
now = datetime.now(timezone.utc)
tol = lambda a, b: abs(float(a) - float(b)) <= max(1e-9, abs(float(b)) * 1e-9)
upserts, deletes, report = [], [], []
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    markets = [r[0] for r in conn.execute('SELECT market_code FROM public."Fixed_Income_Market_Schedule" WHERE enabled ORDER BY 1').fetchall()]
    ws = None; cs = None
    for market in markets:
        schedule = f.read_schedule(conn, market)
        last = f.latest_completed_session(schedule, now)
        for s in f.read_universe(conn, schedule):
            # PULLS independent pulls (a new socket each). TVC:US10Y yield answers two different 2016-2024 histories
            # alternately (measured 2026-11-01) and the stored history mixes them by year, so one pull is not "the
            # source". A stored bar equal to ANY pulled version is a source value and is kept; a stored bar unlike every
            # version is corrected only when all pulls agree; a date is added only when every pull has it with one bar
            # and deleted only when no pull has it. Dates the pulls disagree on are reported as unstable.
            pulls = []
            for _ in range(PULLS):
                for attempt in range(3):
                    try:
                        try:
                            if ws: ws.close()
                        except Exception: pass
                        ws = f.open_socket(30, False); cs = f.start_chart_session(ws)
                        rows_, _ = f.request_series(ws, cs, s, 5000, 90, now.date(), last, now, now, schedule.source_date_mapping,
                                                    schedule.provider_timezone_name, schedule.provider_session)
                        pulls.append({r['date']: r for r in rows_})
                        break
                    except Exception:
                        if attempt == 2: raise
                        time.sleep(3)
            ohlc = lambda r: tuple(float(r[k]) for k in ('open', 'high', 'low', 'close'))
            same = lambda a, b: all(tol(x, y) for x, y in zip(a, b))
            db = {d: tuple(float(x) for x in v) for d, *v in conn.execute(
                'SELECT date, open, high, low, close FROM public."Price_Fixed_Income" WHERE tradingview_symbol = %s '
                'AND metric_type = %s AND "Timeframe" = %s', (s.tradingview_symbol, s.metric_type, f.TIMEFRAME)).fetchall()}
            if not db or not pulls[0]:
                report.append({'series': f'{s.ticker}/{s.metric_type}', 'skipped': 'no stored rows' if not db else 'no source bars'}); continue
            first = min(db)
            src_first = max(min(p) for p in pulls)
            dates = sorted(set().union(*pulls))
            changed, missing, unstable = [], [], []
            for d in dates:
                if d < first or d > last:
                    continue
                versions = [ohlc(p[d]) for p in pulls if d in p]
                agree = len(versions) == PULLS and all(same(v, versions[0]) for v in versions)
                if d in db and any(same(db[d], v) for v in versions):
                    continue                                   # the stored bar is one of the source's versions
                if not agree:
                    unstable.append(d); continue
                (missing if d not in db else changed).append(d)
                row = dict(pulls[0][d]); row['market_close_at'] = f.market_close_at(schedule, d); row['finalized_at'] = now
                upserts.append(f.validate_price_row(row))
            unstable_in_range = unstable
            gone = sorted(d for d in db if src_first <= d <= last and not any(d in p for p in pulls))
            deletes += [(s.tradingview_symbol, d, s.metric_type) for d in gone]
            report.append({'series': f'{s.ticker}/{s.metric_type}', 'changed': len(changed), 'missing': len(missing),
                           'deleted': len(gone), 'unstable_dates': len(unstable_in_range),
                           'unstable_years': sorted({d.year for d in unstable_in_range}), 'samples': [str(x) for x in (changed[:3] + missing[:3] + gone[:3])],
                           'changed_by_year': {y: sum(1 for d in changed if d.year == y) for y in sorted({d.year for d in changed})}})
            time.sleep(0.3)
    if ws: ws.close()
    for r in report:
        if r.get('changed') or r.get('missing') or r.get('deleted') or r.get('skipped') or r.get('unstable_dates'):
            print('OUT ' + json.dumps(r), flush=True)
    print('OUT ' + json.dumps({'mode': mode, 'series': len(report), 'upserts': len(upserts), 'deletes': len(deletes),
                               'unchanged_series': sum(1 for r in report if not (r.get('changed') or r.get('missing') or r.get('deleted')))}), flush=True)
    if mode == 'APPLY' and (upserts or deletes):
        # the cron's own per-market run lock: no daily or recovery run writes the table at the same time
        for market in markets:
            if not f.try_acquire_run_lock(conn, market):
                raise SystemExit(f'a fixed-income run for {market} holds its lock; try again after it')
        with conn.transaction():
            verified, written = f.bulk_upsert_prices(conn, upserts) if upserts else (0, 0)
            gone = 0
            for sym, d, metric in deletes:
                gone += conn.execute('DELETE FROM public."Price_Fixed_Income" WHERE tradingview_symbol = %s AND date = %s '
                                     'AND metric_type = %s AND "Timeframe" = %s', (sym, d, metric, f.TIMEFRAME)).rowcount
        print('OUT ' + json.dumps({'applied': True, 'verified': verified, 'written': written, 'deleted': gone}), flush=True)
print('JOB_DONE', mode, flush=True)
