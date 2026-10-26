"""IDX_Broker_Summary loader of the stockbit-updater service (EXEC-STOCKBIT-UPDATER).

The fetch, validation and per-date upload are the user's importer (import_full_broker_summary.py, the loader that
filled 2026-09-01..10-23, FULL_BROKER_IMPORT.md), unchanged in what they check:
- ticker-first /marketdetectors/{symbol}, Domestic/Foreign x Regular/Nego/Tunai, six filters per symbol and date;
- every symbol of a date must finish before the date is staged; one transaction per date; the staged rows and the
  table are compared both ways on all 15 columns; a row Stockbit stopped returning stops the date (never deleted);
- negative gross values, fractional frequency, identity mismatch and 401/403 stop the run.

What changed to run on Railway instead of the user's PC:
- dates are derived from the data: daily price dates newer than the newest Broker Summary date, plus recent price
  dates that have no Broker Summary row at all (a gap), never a date the price table does not hold yet;
- the symbol list is derived from the database (four-letter symbols of IDX_Stock_Universe, of recent prices and of
  recent Broker Summary rows), not from SQLite files on the PC; non-four-letter symbols are loaded by the user
  separately (decision K1) and are never touched here;
- raw responses and the fetch checkpoint live on the service volume and are pruned after RAW_RETENTION_DAYS (K3);
- VERIFY mode fetches one stored date and compares it with the table without writing.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from psycopg import sql

import stockbit_ihsg_daily as source

COLS = ['Date', 'Symbol', 'Broker', 'Investor Type', 'Market Board', 'Buy Value', 'Sell Value', 'Net Value',
        'Buy Lots', 'Sell Lots', 'Net Lots', 'Avg Buy', 'Avg Sell', 'buy_freq', 'sell_freq']
KEYS = COLS[:5]
FOUR = '^[A-Z]{4}$'
GAP_LOOKBACK_DAYS = 30
MIN_SYMBOLS, MIN_ACTIVE = 500, 100
STOP = threading.Event()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrokerImport:
    def __init__(self, pg, token: str, state_dir: Path, workers: int, emit, raw_retention_days: int):
        self.pg, self.emit, self.workers = pg, emit, workers
        self.state = state_dir
        self.raw = state_dir / 'raw'
        self.raw.mkdir(parents=True, exist_ok=True)
        self.prune_raw(raw_retention_days)
        self.cache = sqlite3.connect(state_dir / 'checkpoint.sqlite', check_same_thread=False)
        self.cache.execute('PRAGMA journal_mode=WAL')
        self.cache.execute('CREATE TABLE IF NOT EXISTS fetched (day text, symbol text, manifest text, payload text, '
                           'updated_at text, PRIMARY KEY(day, symbol, manifest))')
        self.cache.commit()
        self.lock = threading.Lock()
        self.fetch = source.StockbitFetcher(token, 45, .25, 1000)

    def prune_raw(self, days: int) -> None:
        cutoff = time.time() - days * 86400
        removed = 0
        for d in self.raw.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d)
                removed += 1
        self.emit('raw_pruned', directories=removed, retention_days=days)

    # ---------------------------------------------------------------- what to load, derived from the data
    def check_target(self) -> None:
        actual = [r[0] for r in self.pg.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='IDX_Broker_Summary' ORDER BY ordinal_position""").fetchall()]
        if actual != COLS:
            raise ValueError('IDX_Broker_Summary differs from the verified 15-column template')
        pk = self.pg.execute("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid='public."IDX_Broker_Summary"'::regclass AND contype='p'""").fetchone()
        if not pk or pk[0] != 'PRIMARY KEY ("Date", "Symbol", "Broker", "Investor Type", "Market Board")':
            raise ValueError('IDX_Broker_Summary primary key not verified')

    def pending_dates(self) -> list[str]:
        rows = self.pg.execute(f"""
            WITH newest AS (SELECT max("Date") AS d FROM public."IDX_Broker_Summary"),
                 prices AS (SELECT DISTINCT date FROM public."Price_Stock_Indonesia_IDX"
                            WHERE lower(timeframe) IN ('daily','1d','d') AND date >= current_date - {GAP_LOOKBACK_DAYS})
            SELECT p.date::text FROM prices p, newest n
            WHERE p.date > n.d OR NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Summary" b WHERE b."Date" = p.date)
            ORDER BY 1""").fetchall()
        return [r[0] for r in rows]

    def symbols(self) -> list[str]:
        rows = self.pg.execute(f"""
            SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Ticker" ~ '{FOUR}'
            UNION SELECT ticker FROM public."Price_Stock_Indonesia_IDX"
                  WHERE date >= current_date - {GAP_LOOKBACK_DAYS} AND ticker ~ '{FOUR}'
            UNION SELECT "Symbol" FROM public."IDX_Broker_Summary"
                  WHERE "Date" >= (SELECT max("Date") FROM public."IDX_Broker_Summary") - {GAP_LOOKBACK_DAYS}
                    AND "Symbol" ~ '{FOUR}'""").fetchall()
        symbols = sorted({r[0] for r in rows})
        if len(symbols) < MIN_SYMBOLS:
            raise ValueError(f'Unexpectedly small symbol universe: {len(symbols)}')
        return symbols

    # ---------------------------------------------------------------- the user's fetch, unchanged in its checks
    def number(self, item, field, nullable=False):
        v = item.get(field)
        if nullable and v in (None, ''):
            return None
        return source.decimal_value(v, field)

    def fetch_symbol_once(self, day: str, symbol: str) -> dict:
        rows, issues = {}, []
        folder = self.raw / day
        folder.mkdir(exist_ok=True)
        for inv in ('DOMESTIC', 'FOREIGN'):
            for board in ('REGULER', 'NEGO', 'TUNAI'):
                if STOP.is_set():
                    raise RuntimeError('Import stopping')
                params = urlencode({'transaction_type': 'TRANSACTION_TYPE_GROSS',
                                    'market_board': f'MARKET_BOARD_{board}', 'investor_type': f'INVESTOR_TYPE_{inv}',
                                    'limit': '1000', 'from': day, 'to': day, '_': str(time.time_ns())})
                body, raw, _ = self.fetch.get_json('/marketdetectors/' + symbol + '?' + params)
                path = folder / f'{symbol}_{inv}_{board}.json.gz'
                temp = path.with_suffix('.tmp')
                with gzip.open(temp, 'wb') as f:
                    f.write(raw)
                temp.replace(path)
                data = body.get('data')
                summary = data.get('broker_summary') if isinstance(data, dict) else None
                if not isinstance(summary, dict) or data.get('from') != day or data.get('to') != day:
                    raise ValueError(f'Missing summary/date mismatch: {day}/{symbol}/{inv}/{board}')
                seen = set()
                for side, value, lot, avg, indices in (
                        ('brokers_buy', 'bval', 'blot', 'netbs_buy_avg_price', (5, 8, 11, 13)),
                        ('brokers_sell', 'sval', 'slot', 'netbs_sell_avg_price', (6, 9, 12, 14))):
                    entries = summary.get(side)
                    if not isinstance(entries, list) or len(entries) >= 1000:
                        raise ValueError('Missing side or potential truncation')
                    for item in entries:
                        broker = item.get('netbs_broker_code')
                        if not broker or not re.fullmatch('[A-Z0-9]{2}', broker):
                            raise ValueError('Invalid broker key')
                        if (side, broker) in seen:
                            raise ValueError('Duplicate source broker-side key')
                        seen.add((side, broker))
                        if item.get('netbs_stock_code') != symbol or str(item.get('netbs_date')) != day.replace('-', ''):
                            raise ValueError('Response identity mismatch')
                        key = (symbol, broker, source.INVESTORS[inv], source.BOARDS[board])
                        row = rows.setdefault(key, [day, *key, Decimal(0), Decimal(0), Decimal(0), Decimal(0),
                                                    Decimal(0), Decimal(0), None, None, 0, 0])
                        v = self.number(item, value)
                        lots = self.number(item, lot)
                        a = self.number(item, avg, True)
                        freq = self.number(item, 'freq')
                        if freq != freq.to_integral_value():
                            raise ValueError('Fractional frequency cannot be stored without alteration')
                        if min(v, lots, freq) < 0 or (a is not None and a < 0):
                            raise ValueError(f'Negative source numeric conflicts with target constraints: '
                                             f'{day}/{symbol}/{broker}; raw saved; no ABS applied')
                        if v > 0 and a is None:
                            issues.append({'broker': broker, 'investor': inv, 'board': board,
                                           'issue': 'missing average on positive trade'})
                        for index, number in zip(indices, (v, lots, a, int(freq))):
                            row[index] = number
        for row in rows.values():
            row[7] = row[5] - row[6]
            row[10] = row[8] - row[9]
        totals = [sum((r[i] for r in rows.values()), Decimal(0)) for i in (5, 6, 13, 14)]
        if totals[0] != totals[1] or totals[2] != totals[3]:
            issues.append({'issue': 'raw API aggregate imbalance retained', 'buy': totals[0], 'sell': totals[1],
                           'buy_freq': totals[2], 'sell_freq': totals[3]})
        return {'rows': list(rows.values()), 'issues': issues, 'filters': 6, 'checked_at': now()}

    def fetch_symbol(self, day: str, symbol: str) -> dict:
        for attempt in range(1, 4):
            try:
                return self.fetch_symbol_once(day, symbol)
            except Exception as exc:  # noqa: BLE001 - the user's bounded retry, terminal errors re-raised
                msg = str(exc)
                if any(t in msg.lower() for t in ('authentication', 'http 401', 'http 403', 'http 404',
                                                  'negative source', 'fractional frequency', 'identity mismatch')):
                    raise
                if attempt == 3:
                    raise
                time.sleep(60 if '429' in msg else 5 * attempt)

    @staticmethod
    def restore(payload: dict) -> list[tuple]:
        rows = []
        for r in payload['rows']:
            r = list(r)
            for i in range(5, 13):
                if r[i] is not None:
                    r[i] = Decimal(r[i])
            rows.append(tuple(r))
        return rows

    def fetch_day(self, day: str, symbols: list[str], manifest: str) -> list[dict]:
        cached = {s: json.loads(p) for s, p in self.cache.execute(
            'SELECT symbol, payload FROM fetched WHERE day=? AND manifest=?', (day, manifest))}
        pending = [s for s in symbols if s not in cached]
        self.emit('date_started', date=day, expected_symbols=len(symbols), cached_symbols=len(cached))
        executor = ThreadPoolExecutor(max_workers=self.workers)
        last = time.monotonic()
        try:
            futures = {executor.submit(self.fetch_symbol, day, s): s for s in pending}
            for future in as_completed(futures):
                symbol = futures[future]
                payload = json.loads(json.dumps(future.result(), default=str))
                cached[symbol] = payload
                with self.lock:
                    self.cache.execute('INSERT OR REPLACE INTO fetched VALUES (?,?,?,?,?)',
                                       (day, symbol, manifest, json.dumps(payload), now()))
                    self.cache.commit()
                if time.monotonic() - last > 30 or len(cached) == len(symbols):
                    self.emit('fetch_progress', date=day, completed_symbols=len(cached), expected_symbols=len(symbols))
                    last = time.monotonic()
        except BaseException:
            STOP.set()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        return [cached[s] for s in symbols]

    # ---------------------------------------------------------------- the user's upload, unchanged in its checks
    def upload_day(self, day: str, symbols: list[str], payloads: list[dict], manifest: str) -> dict:
        rows = [r for p in payloads for r in self.restore(p)]
        if not rows:
            raise ValueError(f'No activity for observed trading date {day}')
        if len({tuple(r[:5]) for r in rows}) != len(rows):
            raise ValueError('Duplicate source primary key')
        if len({r[1] for r in rows}) < MIN_ACTIVE:
            raise ValueError('Unexpectedly small active symbol coverage')
        issues = [{'symbol': s, **i} for s, p in zip(symbols, payloads) for i in p['issues']]
        (self.state / f'issues_{day}.json').write_text(json.dumps(issues, default=str))
        cols = sql.SQL(',').join(map(sql.Identifier, COLS))
        keys = sql.SQL(',').join(map(sql.Identifier, KEYS))
        updates = sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c))
                                    for c in COLS[5:])
        target_values = sql.SQL(',').join(sql.SQL('t.{}').format(sql.Identifier(c)) for c in COLS[5:])
        incoming = sql.SQL(',').join(sql.SQL('EXCLUDED.{}').format(sql.Identifier(c)) for c in COLS[5:])
        with self.pg.transaction():
            self.pg.execute("SET LOCAL lock_timeout='20s'")
            self.pg.execute("SET LOCAL statement_timeout='5min'")
            self.pg.execute('CREATE TEMP TABLE stage_full_broker (LIKE public."IDX_Broker_Summary" INCLUDING DEFAULTS) '
                            'ON COMMIT DROP')
            with self.pg.cursor() as cur:
                with cur.copy(sql.SQL('COPY stage_full_broker ({}) FROM STDIN').format(cols)) as copy:
                    for row in rows:
                        copy.write_row(row)
            existing = self.pg.execute(sql.SQL('''SELECT {} FROM public."IDX_Broker_Summary"
                WHERE "Date"=%s AND "Symbol" ~ '^[A-Z]{{4}}$' ''').format(cols), (day,)).fetchall()
            if existing:
                before = self.state / f'before_{day}.json.gz'
                if not before.exists():
                    with gzip.open(before, 'wt', encoding='utf-8') as f:
                        json.dump(existing, f, default=str)
            result = self.pg.execute(sql.SQL('''INSERT INTO public."IDX_Broker_Summary" AS t ({}) SELECT {}
                FROM stage_full_broker ON CONFLICT ({}) DO UPDATE SET {} WHERE ({}) IS DISTINCT FROM ({})''').format(
                cols, cols, keys, updates, target_values, incoming))
            different = self.pg.execute(sql.SQL('''SELECT count(*) FROM ((SELECT {} FROM stage_full_broker
                EXCEPT SELECT {} FROM public."IDX_Broker_Summary" WHERE "Date"=%s) UNION ALL
                (SELECT {} FROM public."IDX_Broker_Summary" WHERE "Date"=%s AND "Symbol" ~ '^[A-Z]{{4}}$'
                EXCEPT SELECT {} FROM stage_full_broker)) x''').format(cols, cols, cols, cols), (day, day)).fetchone()[0]
            if different:
                raise ValueError(f'Full date source/target mismatch: {different}; rolled back')
            self.pg.execute('''INSERT INTO public.stockbit_full_broker_import_status
                (trade_date, manifest_hash, state, expected_symbols, completed_symbols, row_count, anomaly_symbols,
                 heartbeat_at, completed_at)
                VALUES (%s,%s,'completed',%s,%s,%s,%s,now(),now()) ON CONFLICT (trade_date) DO UPDATE SET
                manifest_hash=excluded.manifest_hash, state='completed', expected_symbols=excluded.expected_symbols,
                completed_symbols=excluded.completed_symbols, row_count=excluded.row_count,
                anomaly_symbols=excluded.anomaly_symbols, heartbeat_at=now(), completed_at=now(), error_message=NULL''',
                (day, manifest, len(payloads), len(payloads), len(rows), len({i['symbol'] for i in issues})))
        saved = self.pg.execute('SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Date"=%s AND "Symbol" ~ %s',
                                (day, FOUR)).fetchone()[0]
        if saved != len(rows):
            raise ValueError('Post-commit row count changed')
        summary = dict(date=day, rows=len(rows), changed_rows=result.rowcount, active_symbols=len({r[1] for r in rows}),
                       anomaly_symbols=len({i['symbol'] for i in issues}))
        self.emit('date_committed', **summary)
        return summary

    def compare_day(self, day: str, payloads: list[dict]) -> dict:
        """VERIFY: the freshly fetched rows against the stored four-letter rows of the date, both ways, no write."""
        fetched = {tuple(r[:5]): r for p in payloads for r in self.restore(p)}
        cols = sql.SQL(',').join(map(sql.Identifier, COLS))
        stored = {}
        for r in self.pg.execute(sql.SQL('''SELECT {} FROM public."IDX_Broker_Summary"
                WHERE "Date"=%s AND "Symbol" ~ '^[A-Z]{{4}}$' ''').format(cols), (day,)).fetchall():
            r = list(r)
            r[0] = str(r[0])
            for i in range(5, 15):
                if r[i] is not None:
                    r[i] = Decimal(str(r[i])) if i < 13 else int(r[i])
            stored[tuple(r[:5])] = tuple(r)
        norm = {k: tuple(str(v[0]) if i == 0 else v[i] for i in range(15)) for k, v in fetched.items()}
        missing = stored.keys() - norm.keys()
        extra = norm.keys() - stored.keys()
        different = [k for k in norm.keys() & stored.keys() if norm[k] != stored[k]]
        result = dict(date=day, fetched_rows=len(norm), stored_rows=len(stored), missing_in_fetch=len(missing),
                      new_in_fetch=len(extra), different=len(different),
                      examples=[{'key': list(k), 'columns': [COLS[i] for i in range(15) if norm[k][i] != stored[k][i]]}
                                for k in sorted(different)[:3]])
        self.emit('verify_compare', **result)
        return result

    # ---------------------------------------------------------------- one round
    def run(self, verify_date: str | None = None) -> dict:
        self.check_target()
        symbols = self.symbols()
        manifest = hashlib.sha256(json.dumps(symbols).encode()).hexdigest()
        if verify_date:
            payloads = self.fetch_day(verify_date, symbols, manifest)
            return {'mode': 'VERIFY', 'symbols': len(symbols), 'verify': self.compare_day(verify_date, payloads)}
        if not self.pg.execute("SELECT pg_try_advisory_lock(hashtext('stockbit-full-broker-summary-import'))").fetchone()[0]:
            raise RuntimeError('Another full broker-summary importer is active')
        dates = self.pending_dates()
        self.emit('broker_plan', dates=dates, symbols=len(symbols))
        loaded = []
        for day in dates:
            self.pg.execute('''INSERT INTO public.stockbit_full_broker_import_status (trade_date, manifest_hash, state,
                expected_symbols) VALUES (%s,%s,'fetching',%s) ON CONFLICT (trade_date) DO UPDATE SET
                manifest_hash=excluded.manifest_hash, state='fetching', expected_symbols=excluded.expected_symbols,
                heartbeat_at=now(), error_message=NULL''', (day, manifest, len(symbols)))
            try:
                payloads = self.fetch_day(day, symbols, manifest)
                loaded.append(self.upload_day(day, symbols, payloads, manifest))
            except BaseException as exc:
                self.pg.execute('''UPDATE public.stockbit_full_broker_import_status SET state='failed',
                    error_message=%s, heartbeat_at=now() WHERE trade_date=%s''', (str(exc)[:2000], day))
                raise
        self.pg.execute("SELECT pg_advisory_unlock(hashtext('stockbit-full-broker-summary-import'))")
        return {'mode': 'APPLY', 'symbols': len(symbols), 'dates': dates, 'loaded': loaded,
                'rows': sum(x['rows'] for x in loaded)}
