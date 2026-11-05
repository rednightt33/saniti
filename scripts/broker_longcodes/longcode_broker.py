#!/usr/bin/env python3
"""EXEC-UNIVERSE-BROKER S3, stage 1: IDX_Broker_Summary rows of the codes that are not four letters (warrants,
structured warrants, ...) for the dates the Railway loader skipped (2026-09-01 onwards; decision K1: the loader takes
four-letter codes only).

Runs anywhere with Python 3.10+ and the standard library (the user's PC, decision K1). No database access: the dates
come from dates.json (made from the table), the codes are discovered from Stockbit itself, and the output is a set of
checked files for the later upload (stage U6, after S2).

Steps, each resumable (state in OUT/state.sqlite; a stopped run continues where it stopped):
  discover  broker-first, every broker x Domestic/Foreign x Regular/Nego/Tunai per date (/order-trade/broker/activity,
            stockbit_ihsg_daily.StockbitFetcher.activity): which codes traded that day, with each broker's buy/sell
            value and frequency. This also finds codes issued after the user's CSV.
  fetch     ticker-first, the six filters for every (date, code) found (/marketdetectors/{code},
            broker_import.BrokerImport.fetch_symbol_once, the loader's own fetch and checks, unchanged): the 15
            columns of IDX_Broker_Summary (lots and average prices exist only here).
  check     no write anywhere but OUT: unique table key (Date, Symbol, Broker, Investor Type, Market Board); required
            columns present; response date = requested date; every found (date, code) fetched; the two Stockbit
            sources agree key by key on buy/sell value and frequency (a key one source has and the other lacks, or a
            different number, is reported, never uploaded). Writes OUT/rows/<date>.csv.gz and OUT/check_report.json.
  status    progress and the measured request rate.
  probe     a small test (one date, a few brokers, a few codes) that prints the request rate; writes nothing to OUT
            but its own probe folder.

The Stockbit token is read from STOCKBIT_TOKEN, from --token-file, or from a hidden prompt; it is never printed or
written. An authentication failure (HTTP 401/403, an expired token) stops the step; run it again with a new token.

Usage:
  python longcode_broker.py discover --out OUT [--dates dates.json] [--workers 6]
  python longcode_broker.py fetch    --out OUT [--workers 6]
  python longcode_broker.py check    --out OUT
  python longcode_broker.py status   --out OUT
  python longcode_broker.py probe    --out OUT [--brokers 3] [--codes 3]
"""
from __future__ import annotations

import argparse
import csv
import getpass
import gzip
import json
import os
import re
import sqlite3
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPDATER = HERE.parents[1] / 'apps' / 'stockbit-updater'
sys.path.insert(0, str(UPDATER))
try:
    import psycopg  # noqa: F401 - broker_import imports psycopg.sql for its upload, not used here
except ImportError:  # the PC needs no database driver for these steps
    stub = types.ModuleType('psycopg')
    stub.sql = types.ModuleType('psycopg.sql')
    sys.modules['psycopg'], sys.modules['psycopg.sql'] = stub, stub.sql
import broker_import  # noqa: E402
import stockbit_ihsg_daily as source  # noqa: E402

FOUR = re.compile(r'^[A-Z]{4}$')
COLS = broker_import.COLS
REQUIRED = COLS[:11]                      # Date .. Net Lots; Avg Buy/Sell are NULL for a side with no trade
AUTH = ('authentication', 'http 401', 'http 403')
INVESTORS = ('DOMESTIC', 'FOREIGN')
BOARDS = ('REGULER', 'NEGO', 'TUNAI')


def use_proxy_when_set() -> None:
    """Only where HTTPS_PROXY is set (a test from a cloud machine): tunnel the fetcher's connections through it. A PC
    without a proxy connects directly, as stockbit_ihsg_daily does."""
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if not proxy:
        return
    import http.client
    import ssl
    from urllib.parse import urlparse
    p = urlparse(proxy)
    context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or None)

    def connection(self):
        conn = getattr(self.local, 'connection', None)
        if conn is None:
            conn = http.client.HTTPSConnection(p.hostname, p.port, timeout=self.timeout, context=context)
            conn.set_tunnel(source.HOST)
            self.local.connection = conn
            self.local.last_finished = 0.0
        return conn

    source.StockbitFetcher._connection = connection


def now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def emit(event: str, **fields) -> None:
    print(json.dumps({'event': event, 'at': now(), **fields}, default=str), flush=True)


def read_token(path: str | None) -> str:
    token = (os.environ.get('STOCKBIT_TOKEN') or '').strip()
    if not token and path:
        token = Path(path).read_text().strip()
    if not token:
        token = getpass.getpass('Stockbit token (hidden): ').strip()
    return token


def is_auth(exc: BaseException) -> bool:
    return any(t in str(exc).lower() for t in AUTH)


class State:
    """OUT/state.sqlite: what is done, so every step resumes."""

    def __init__(self, out: Path):
        out.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(out / 'state.sqlite', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.lock = threading.Lock()
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS dates (day text PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS brokers (code text PRIMARY KEY, name text);
            CREATE TABLE IF NOT EXISTS discover_task (day text, broker text, investor text, board text, status text,
                requests integer, pages integer, sha256 text, error text, at text,
                PRIMARY KEY (day, broker, investor, board));
            CREATE TABLE IF NOT EXISTS discover_row (day text, symbol text, broker text, investor text, board text,
                buy_value text, sell_value text, buy_freq text, sell_freq text, anomaly integer, remarks text,
                PRIMARY KEY (day, symbol, broker, investor, board));
            CREATE TABLE IF NOT EXISTS fetched (day text, symbol text, status text, payload text, error text, at text,
                seconds real, PRIMARY KEY (day, symbol));
        ''')
        self.db.commit()

    def write(self, sql_text: str, rows) -> None:
        with self.lock:
            self.db.executemany(sql_text, rows)
            self.db.commit()

    def all(self, sql_text: str, args=()) -> list:
        with self.lock:
            return self.db.execute(sql_text, args).fetchall()


def ticker_importer(raw_dir: Path, token: str) -> broker_import.BrokerImport:
    """The loader's own fetch (fetch_symbol_once) without its database and checkpoint."""
    imp = broker_import.BrokerImport.__new__(broker_import.BrokerImport)
    imp.raw = raw_dir
    imp.raw.mkdir(parents=True, exist_ok=True)
    imp.fetch = source.StockbitFetcher(token, 45, .25, 1000)
    return imp


def run_pool(items, work, workers: int, label: str):
    """Runs work(item) in threads; an authentication failure stops everything at once."""
    stop = threading.Event()
    done = failed = 0
    started = last = time.monotonic()

    def guarded(item):
        if stop.is_set():
            return item, None, 'stopped'
        try:
            return item, work(item), None
        except Exception as exc:  # noqa: BLE001 - recorded per item; authentication stops the step
            if is_auth(exc):
                stop.set()
                broker_import.STOP.set()
            return item, None, f'{type(exc).__name__}: {str(exc)[:300]}'

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item, _, error in (f.result() for f in as_completed([pool.submit(guarded, i) for i in items])):
            done += 1
            failed += error is not None and error != 'stopped'
            if time.monotonic() - last > 30 or done == len(items):
                rate = done / max(1e-9, time.monotonic() - started)
                emit(f'{label}_progress', done=done, of=len(items), failed=failed, items_per_second=round(rate, 2),
                     eta_minutes=round((len(items) - done) / max(rate, 1e-9) / 60, 1))
                last = time.monotonic()
    if stop.is_set():
        emit('stopped_authentication', step=label,
             note='the token was refused (expired or revoked); run the same step again with a new token')
        raise SystemExit(2)
    return failed


# ---------------------------------------------------------------- discover (broker-first)
def discover(args) -> None:
    st = State(Path(args.out))
    days = json.loads(Path(args.dates).read_text())
    st.write('INSERT OR IGNORE INTO dates VALUES (?)', [(d,) for d in days])
    fetcher = source.StockbitFetcher(read_token(args.token_file), 45, .25, 1000)
    brokers = fetcher.broker_directory()
    st.write('INSERT OR REPLACE INTO brokers VALUES (?,?)', [(b['code'], b['name']) for b in brokers])
    codes = [b['code'] for b in brokers][: args.limit_brokers or None]
    done = {tuple(r) for r in st.all("SELECT day, broker, investor, board FROM discover_task WHERE status='done'")}
    tasks = [source.FilterTask(d, b, inv, board) for d in days for b in codes for inv in INVESTORS for board in BOARDS
             if (d, b, inv, board) not in done]
    emit('discover_plan', dates=len(days), brokers=len(codes), tasks=len(tasks), already_done=len(done))

    def work(task):
        result = fetcher.activity(task)
        rows = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]) for r in result.rows
                if not FOUR.match(r[1])]
        with st.lock:
            st.db.execute('DELETE FROM discover_row WHERE day=? AND broker=? AND investor=? AND board=?',
                          (task.trade_date, task.broker, source.INVESTORS[task.investor], source.BOARDS[task.board]))
            st.db.executemany('INSERT INTO discover_row VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows)
            st.db.execute('INSERT OR REPLACE INTO discover_task VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (task.trade_date, task.broker, task.investor, task.board, 'done', result.requests,
                           result.pages, result.response_sha256, None, now()))
            st.db.commit()

    failed = run_pool(tasks, work, args.workers, 'discover')
    pairs = st.all('SELECT count(*), count(DISTINCT symbol) FROM (SELECT DISTINCT day, symbol FROM discover_row)')[0]
    emit('discover_done', failed_tasks=failed, code_days=pairs[0], codes=pairs[1],
         note='failed tasks are retried by running discover again')


# ---------------------------------------------------------------- fetch (ticker-first)
def fetch(args) -> None:
    st = State(Path(args.out))
    open_tasks = st.all("SELECT count(*) FROM dates d, brokers b WHERE NOT EXISTS (SELECT 1 FROM discover_task t "
                        "WHERE t.day=d.day AND t.broker=b.code AND t.status='done')")[0][0]
    if open_tasks and not args.allow_partial_discovery:
        raise SystemExit(f'discover is not finished ({open_tasks} broker x date groups open); run discover first')
    imp = ticker_importer(Path(args.out) / 'raw', read_token(args.token_file))
    done = {tuple(r) for r in st.all("SELECT day, symbol FROM fetched WHERE status='done'")}
    pairs = [tuple(r) for r in st.all('SELECT DISTINCT day, symbol FROM discover_row ORDER BY 1, 2')
             if tuple(r) not in done]
    pairs = pairs[: args.limit or None]
    emit('fetch_plan', pairs=len(pairs), already_done=len(done), requests=len(pairs) * 6)

    def work(pair):
        day, symbol = pair
        t0 = time.monotonic()
        try:
            payload = imp.fetch_symbol(day, symbol)
        except Exception as exc:
            st.write('INSERT OR REPLACE INTO fetched VALUES (?,?,?,?,?,?,?)',
                     [(day, symbol, 'error', None, f'{type(exc).__name__}: {str(exc)[:300]}', now(),
                       time.monotonic() - t0)])
            raise
        st.write('INSERT OR REPLACE INTO fetched VALUES (?,?,?,?,?,?,?)',
                 [(day, symbol, 'done', json.dumps(payload, default=str), None, now(), time.monotonic() - t0)])

    failed = run_pool(pairs, work, args.workers, 'fetch')
    emit('fetch_done', failed_pairs=failed, note='failed pairs are retried by running fetch again')


# ---------------------------------------------------------------- check (no network)
def check(args) -> None:
    out = Path(args.out)
    st = State(out)
    rows_dir = out / 'rows'
    rows_dir.mkdir(exist_ok=True)
    report = {'checked_at': now(), 'dates': {}, 'problems': [], 'totals': {}}
    days = [r[0] for r in st.all('SELECT day FROM dates ORDER BY 1')]
    open_tasks = st.all("SELECT day, count(*) FROM dates d, brokers b WHERE NOT EXISTS (SELECT 1 FROM discover_task t "
                        "WHERE t.day=d.day AND t.broker=b.code AND t.status='done') GROUP BY 1")
    for day, n in open_tasks:
        report['problems'].append({'date': day, 'problem': 'discover not finished', 'open_broker_groups': n})
    total_rows = 0
    for day in days:
        disc = {}
        for r in st.all('SELECT symbol, broker, investor, board, buy_value, sell_value, buy_freq, sell_freq '
                        'FROM discover_row WHERE day=?', (day,)):
            disc[(r[0], r[1], r[2], r[3])] = tuple(Decimal(x) for x in r[4:])
        found = sorted({k[0] for k in disc})
        got = {s: (status, payload, error) for s, status, payload, error in
               st.all('SELECT symbol, status, payload, error FROM fetched WHERE day=?', (day,))}
        bad_codes, rows = set(), []
        for symbol in found:
            status, payload, error = got.get(symbol, (None, None, None))
            if status != 'done':
                bad_codes.add(symbol)
                report['problems'].append({'date': day, 'code': symbol, 'problem': 'not fetched', 'error': error})
                continue
            p = json.loads(payload)
            for issue in p.get('issues', []):
                report['problems'].append({'date': day, 'code': symbol, 'problem': 'source note', **issue})
            for r in p['rows']:
                rows.append(r)
        keys = [tuple(r[:5]) for r in rows]
        dup = len(keys) - len(set(keys))
        if dup:
            report['problems'].append({'date': day, 'problem': 'duplicate table key', 'count': dup})
        for r in rows:
            missing = [c for c, v in zip(COLS, r) if c in REQUIRED and v in (None, '')]
            if missing:
                bad_codes.add(r[1])
                report['problems'].append({'date': day, 'code': r[1], 'broker': r[2], 'problem': 'missing value',
                                           'columns': missing})
            if r[0] != day:
                bad_codes.add(r[1])
                report['problems'].append({'date': day, 'code': r[1], 'problem': 'row date differs', 'row_date': r[0]})
        tick = {(r[1], r[2], r[3], r[4]): (Decimal(str(r[5])), Decimal(str(r[6])), Decimal(str(r[13])),
                                           Decimal(str(r[14]))) for r in rows}
        for key in sorted(set(disc) | set(tick)):
            if key[0] in bad_codes:
                continue
            a, b = disc.get(key), tick.get(key)
            if a != b:
                bad_codes.add(key[0])
                report['problems'].append({'date': day, 'code': key[0], 'broker': key[1], 'investor': key[2],
                                           'board': key[3], 'problem': 'sources disagree',
                                           'broker_first': [str(x) for x in a] if a else None,
                                           'ticker_first': [str(x) for x in b] if b else None})
        good = [r for r in rows if r[1] not in bad_codes]
        with gzip.open(rows_dir / f'{day}.csv.gz', 'wt', newline='') as f:
            w = csv.writer(f)
            w.writerow(COLS)
            for r in sorted(good, key=lambda r: (r[1], r[2], r[3], r[4])):
                w.writerow(['' if v is None else (source.plain_decimal(Decimal(str(v))) if i >= 5 else v)
                            for i, v in enumerate(r)])
        total_rows += len(good)
        report['dates'][day] = {'codes_found': len(found), 'codes_ready': len(found) - len(bad_codes),
                                'codes_held_back': sorted(bad_codes), 'rows_ready': len(good)}
    report['totals'] = {'dates': len(days), 'rows_ready': total_rows,
                        'codes_held_back': sum(len(v['codes_held_back']) for v in report['dates'].values()),
                        'problems': len(report['problems'])}
    (out / 'check_report.json').write_text(json.dumps(report, indent=1, default=str))
    emit('check_done', **report['totals'], report=str(out / 'check_report.json'))


def status(args) -> None:
    st = State(Path(args.out))
    q = lambda s: st.all(s)[0]  # noqa: E731
    total_tasks = q('SELECT (SELECT count(*) FROM dates) * (SELECT count(*) FROM brokers) * 6')[0]
    emit('status',
         dates=q('SELECT count(*) FROM dates')[0], brokers=q('SELECT count(*) FROM brokers')[0],
         discover_done=q("SELECT count(*) FROM discover_task WHERE status='done'")[0], discover_total=total_tasks,
         code_days_found=q('SELECT count(*) FROM (SELECT DISTINCT day, symbol FROM discover_row)')[0],
         codes_found=q('SELECT count(DISTINCT symbol) FROM discover_row')[0],
         fetched_done=q("SELECT count(*) FROM fetched WHERE status='done'")[0],
         fetched_error=q("SELECT count(*) FROM fetched WHERE status='error'")[0],
         seconds_per_code_day=q("SELECT round(avg(seconds), 2) FROM fetched WHERE status='done'")[0])


# ---------------------------------------------------------------- probe (small test)
def probe(args) -> None:
    token = read_token(args.token_file)
    out = Path(args.out) / 'probe'
    out.mkdir(parents=True, exist_ok=True)
    fetcher = source.StockbitFetcher(token, 45, .25, 1000)
    brokers = fetcher.broker_directory()
    day = args.date
    t0 = time.monotonic()
    found, disc, requests = {}, {}, 0
    chosen = args.broker_list.split(',') if args.broker_list else [x['code'] for x in brokers][: args.brokers]
    for b in chosen:
        for inv in INVESTORS:
            for board in BOARDS:
                res = fetcher.activity(source.FilterTask(day, b, inv, board))
                requests += res.requests
                for r in res.rows:
                    if not FOUR.match(r[1]):
                        found.setdefault(r[1], 0)
                        found[r[1]] += 1
                        disc[(r[1], r[2], r[3], r[4])] = (Decimal(r[5]), Decimal(r[6]), Decimal(r[7]), Decimal(r[8]))
    t_disc = time.monotonic() - t0
    imp = ticker_importer(out / 'raw', token)
    codes = sorted(found, key=lambda s: -found[s])[: args.codes]
    t1 = time.monotonic()
    agree = disagree = 0
    for c in codes:
        payload = imp.fetch_symbol_once(day, c)
        for r in payload['rows']:
            key = (r[1], r[2], r[3], r[4])
            if key in disc:
                same = disc[key] == (Decimal(str(r[5])), Decimal(str(r[6])), Decimal(str(r[13])), Decimal(str(r[14])))
                agree += same
                disagree += not same
    t_tick = time.monotonic() - t1
    emit('probe', date=day, brokers_in_directory=len(brokers), brokers_probed=chosen,
         discover_requests=requests, discover_seconds=round(t_disc, 1),
         seconds_per_request=round(t_disc / max(requests, 1), 2), long_codes_seen=len(found),
         codes_fetched=codes, ticker_requests=len(codes) * 6, ticker_seconds=round(t_tick, 1),
         keys_agree=agree, keys_disagree=disagree)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=['discover', 'fetch', 'check', 'status', 'probe'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--dates', default=str(HERE / 'dates.json'))
    ap.add_argument('--token-file')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--limit', type=int, default=0, help='fetch: at most this many (date, code) pairs (a test)')
    ap.add_argument('--limit-brokers', type=int, default=0, help='discover: only the first N brokers (a test)')
    ap.add_argument('--allow-partial-discovery', action='store_true', help='fetch: allowed only for a test')
    ap.add_argument('--date', default='2026-11-03', help='probe: the date')
    ap.add_argument('--brokers', type=int, default=3, help='probe: brokers to ask')
    ap.add_argument('--codes', type=int, default=3, help='probe: codes to fetch ticker-first')
    ap.add_argument('--broker-list', help='probe: comma-separated broker codes instead of the first N')
    args = ap.parse_args()
    use_proxy_when_set()
    {'discover': discover, 'fetch': fetch, 'check': check, 'status': status, 'probe': probe}[args.step](args)


if __name__ == '__main__':
    main()
