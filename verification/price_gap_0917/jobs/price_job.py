"""EXEC-PRICE-GAP-0917 S1, prices (runs on orc-test-runner through scripts/onboarding/run_job.sh; see the EXEC entry).

A. The two missing sessions go through the daily job's own code path: `price_update.py --mode manual --target-date D`
   (monitoring rows, Feature 04 run binding and the Telegram notice exactly as a daily run).
B. Stocks whose whole stored history is on another scale than TradingView now (user decision 2026-10-31: the current
   TradingView version is correct) get every stored row replaced with TradingView's candle of the same date, one
   transaction per stock, with the same columns as `bulk_upsert_prices`.

Scope is derived, not listed: B takes the stocks named in params.json but checks each one again before writing, and a
stock that does not show the expected pattern is not written. The pattern: every stored date exists in TradingView;
stored close / TradingView close is one constant ratio != 1 up to some date and exactly 1 after it; the only dates
TradingView has inside the stored range and storage lacks are the missing sessions of part A.

params.json: {"dates": [...], "six": [...], "request_bars": 40, "dry_run": true|false}
Prints OUT/ERR/VERDICT lines and ends with JOB_DONE. No secret is printed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone

import psycopg

import price_update as pu

P = json.load(open('params.json'))
DRY = bool(P['dry_run'])
GAP = [date.fromisoformat(d) for d in P['dates']]


def out(kind, event, **fields):
    print(f'{kind} ' + json.dumps({'event': event, **fields}, default=str), flush=True)


def part_a():
    """The standard manual run per missing session; its own JSON events are passed through."""
    for d in GAP:
        cmd = [sys.executable, '-u', 'price_update.py', '--mode', 'manual', '--target-date', d.isoformat(),
               '--request-bars', str(P['request_bars'])] + (['--dry-run'] if DRY else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        for line in r.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get('event') in ('run_started', 'run_completed', 'run_skipped', 'telegram_notify_accepted',
                                   'telegram_notify_failed', 'telegram_notify_skipped'):
                out('OUT', 'price_run_' + ev['event'], date=d, **{k: v for k, v in ev.items() if k != 'event'})
            elif ev.get('event') == 'dry_run_completed':
                for rec in ev['records']:
                    out('OUT', 'price_dry_run', date=d, asset_type=rec['asset_type'], status=rec['status'],
                        expected=rec['expected_symbols'], updated=rec['updated_symbols'],
                        missing=rec['missing_symbols'], missing_list=rec['missing_symbol_list'][:40])
        if r.returncode:
            out('ERR', 'price_run_failed', date=d, code=r.returncode, stderr=r.stderr[-1500:])
            raise SystemExit(1)


def segments(stored, tv):
    """[(first, last, ratio, days)] of stored close / TradingView close over the stored dates, in date order."""
    segs = []
    # the missing sessions part A has just written take TradingView's scale (ratio 1); they are not stored history
    for d in sorted(x for x in stored if x not in GAP):
        r = round(float(stored[d]) / float(tv[d]['close']), 6)
        if segs and segs[-1][2] == r:
            segs[-1][1] = d; segs[-1][3] += 1
        else:
            segs.append([d, d, r, 1])
    return segs


def part_b(conn):
    schedule = pu.read_market_schedule(conn)
    universe = {s.ticker: s for s in pu.read_universe(conn)}
    query_date = datetime.now(pu.JAKARTA).date()
    ws = pu.open_socket(90, False)
    cs = pu.start_chart_session(ws)
    written = skipped = 0
    for ticker in P['six']:
        sym = universe.get(ticker)
        if sym is None or sym.asset_type == 'index':
            out('ERR', 'six_not_in_universe', ticker=ticker); skipped += 1; continue
        stored = {r[0]: r[1] for r in conn.execute(
            'SELECT date, close FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s AND timeframe=%s AND is_final',
            (ticker, pu.PRICE_TIMEFRAME)).fetchall()}
        tv = {r['date']: r for r in pu.request_symbol(ws, cs, sym, 5000, 90, query_date)}
        if not stored or not tv:
            out('ERR', 'six_no_data', ticker=ticker, stored=len(stored), tv=len(tv)); skipped += 1; continue
        lo, hi = min(stored), max(stored)
        absent = sorted(d for d in stored if d not in tv)
        extra = sorted(d for d in tv if lo <= d <= hi and d not in stored)
        segs = segments(stored, tv) if not absent else []
        pattern = (not absent and set(extra) <= set(GAP) and len(segs) >= 2 and segs[-1][2] == 1.0
                   and all(s[2] != 1.0 for s in segs[:-1]) and len({s[2] for s in segs[:-1]}) <= 2)
        # PBSA carries one stored candle that TradingView now gives at another ratio (M313); a stock may have at most
        # one such one-day segment before its ex-date, everything else must be one constant ratio
        if pattern and len({s[2] for s in segs[:-1]}) == 2:
            main = max(segs[:-1], key=lambda s: s[3])[2]
            pattern = sum(s[3] for s in segs[:-1] if s[2] != main) <= 1
        out('OUT', 'six_check', ticker=ticker, stored=len(stored), first=lo, last=hi, absent_in_tv=len(absent),
            new_dates=extra, segments=[s for s in segs if s[2] != 1.0][:4], after_ratio_1_days=segs[-1][3] if segs else 0,
            pattern=pattern)
        if not pattern:
            skipped += 1; continue
        # A day whose ratio differs from the stock's main ratio is a TradingView candle that contradicts its own
        # adjustment (M313, PBSA 2026-10-08; user 2026-10-31 "Harga asli ÷ 2"): that day takes the stored candle
        # converted with the main ratio, exactly as TradingView converts every other day of the stock.
        main = max(segs[:-1], key=lambda s: s[3])[2]
        odd = {s[0]: main for s in segs[:-1] if s[2] != main}
        rows = []
        finalized_at = datetime.now(timezone.utc)
        for d in sorted(set(stored) | set(extra)):
            row = dict(tv[d])
            if d in odd:
                o, h, l, c, v = conn.execute(
                    'SELECT open, high, low, close, volume FROM public."Price_Stock_Indonesia_IDX" '
                    'WHERE ticker=%s AND date=%s AND timeframe=%s', (ticker, d, pu.PRICE_TIMEFRAME)).fetchone()
                k = pu.Decimal(str(odd[d]))
                row.update(open=o / k, high=h / k, low=l / k, close=c / k, volume=(v * k).to_integral_value())
                out('OUT', 'six_odd_day', ticker=ticker, date=d, ratio=odd[d],
                    tv_close=tv[d]['close'], written_close=str(row['close']), written_volume=str(row['volume']))
            row = pu.validate_price_row(row)
            row.update(market_code=schedule.market_code, market_close_at=pu.market_close_at(schedule, d),
                       is_final=True, finalized_at=finalized_at)
            rows.append(row)
        if DRY:
            out('OUT', 'six_dry_run', ticker=ticker, rows=len(rows), sample=[(str(r['date']), str(r['close'])) for r in rows[-3:]])
            continue
        with conn.transaction():
            cols = ', '.join(pu.PRICE_COLUMNS)
            updates = ', '.join(f'{c} = EXCLUDED.{c}' for c in pu.PRICE_COLUMNS if c not in ('ticker', 'date'))
            conn.execute(f'CREATE TEMP TABLE six_stage (LIKE {pu.PRICE_TABLE} INCLUDING DEFAULTS) ON COMMIT DROP')
            with conn.cursor().copy(f'COPY six_stage ({cols}) FROM STDIN') as copy:
                for row in rows:
                    copy.write_row(tuple(row[c] for c in pu.PRICE_COLUMNS))
            n = conn.execute(f'''INSERT INTO {pu.PRICE_TABLE} ({cols}, ingestion_time)
                                 SELECT {cols}, statement_timestamp() FROM six_stage
                                 ON CONFLICT (ticker, date) DO UPDATE SET {updates},
                                 ingestion_time = EXCLUDED.ingestion_time''').rowcount
            back = conn.execute(
                f'SELECT count(*), count(*) FILTER (WHERE s.close IS DISTINCT FROM p.close OR s.open IS DISTINCT FROM p.open '
                f'OR s.high IS DISTINCT FROM p.high OR s.low IS DISTINCT FROM p.low OR s.volume IS DISTINCT FROM p.volume) '
                f'FROM six_stage s JOIN {pu.PRICE_TABLE} p USING (ticker, date)').fetchone()
            if n != len(rows) or back[0] != len(rows) or back[1]:
                raise RuntimeError(f'{ticker}: wrote {n}, read back {back[0]} rows, {back[1]} differ; rolled back')
        written += 1
        out('OUT', 'six_written', ticker=ticker, rows=n, new_dates=extra)
    ws.close()
    return written, skipped


def main():
    out('OUT', 'job_started', dry_run=DRY, dates=P['dates'], six=P['six'])
    if not P.get('skip_part_a'):
        part_a()
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.autocommit = True
        # the price jobs' own lock: no daily or recovery run writes prices while this runs
        if not pu.try_acquire_run_lock(conn):
            out('ERR', 'price_lock_busy'); raise SystemExit(1)
        written, skipped = part_b(conn)
    out('VERDICT', 'six', written=written, skipped=skipped, dry_run=DRY)


if __name__ == '__main__':
    try:
        main()
    finally:
        print('JOB_DONE', flush=True)
