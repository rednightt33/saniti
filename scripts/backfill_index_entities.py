#!/usr/bin/env python3
"""EXEC-INDEX-GROUP-HISTORY (PLAN.md INDEX-GROUP-HISTORY, user decisions 2026-11-15): the *_INDEX feature rows of the
entities of Feature_Index_Entity other than IHSG: 32 Stockbit indexes and 11 IDX sector indexes (Feature 01-06) and 33
KONGLO groups (Feature 02, 03, 05, 06; no price). IHSG keeps scripts/backfill_index_features.py unchanged.

The formulas are the IHSG ones: the same cloned functions and SQL (backfill_index_features stage2, stage6,
stage_prices) and the same independent checks (validate2, validate3, validate6). Only the input differs: an entity's
broker rows are the sum of its member stocks of that day.

- Members by date (decision 3A and the user's example "tercatat tanggal 28 -> mulai tanggal 29"): a symbol belongs to an
  entity on day d when valid_from <= d < valid_to, from the history tables' pit_valid_from/pit_valid_to (the recorded WIB
  date + 1). A Stockbit list (STOCK_LIST) uses Stock_List_Member_History; its first recorded members also hold before
  that record (the list's earliest pit_valid_from becomes -infinity). A sector (UNIVERSE_SECTOR) uses
  IDX_Stock_Universe_History, Security Type 'stock', Sector = the entity's sector; each stock's first known row also
  holds before it (a stock that entered the universe later still counts in its sector in the past, as 3A asks); a later
  row with another sector moves it from that row's date.
- One read of IDX_Broker_Summary per month for all entities: per date, entity, broker, board and investor type, the
  same sums, gap and frequency coverage as the IHSG read (backfill_index_features.stage_raw). Kept twice:
  `hist6`, summed over brokers, from the first broker date (Feature 06's cumulative nets start there, decision D1 A),
  and `bulk5_all`, by broker, for the warmup window only (Feature 02/03/05: the WARMUP_SESSIONS market sessions before
  the first row written). Entities are read by broker in batches of --batch entities (temporary table size); the first
  batch's read also fills hist6 for every entity.
- Checks before anything is written: the universe members' sums equal Feature 05's stock rows (by broker in the window,
  by board and investor type before it); hist6 equals bulk5_all summed over brokers in the window; no member period
  overlaps; at least 312 sessions of the entity before its first row.
- Feature 06: a first fill computes the whole history from hist6 (refresh_feature_06 with no start, as the full IHSG
  run); a later run continues from the stored rows (their cumulative nets are the anchors, as the IHSG incremental run).
- Written: only dates >= the entity's from date: rows_from (2024-01-02) for a first fill, else the day after its newest
  stored Feature 03 row; prices (Feature 01/04) are staged from the first price bar and written from the same date.

Default is a dry run (nothing public is written). --apply writes each entity with backfill_index_features.apply_chunks
(per year, idempotent, read back)."""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts')]
import backfill_index_features as b  # noqa: E402

MIN_SESSIONS = 312  # the longest window (Feature 02 311 + today, Feature 06 252 + 60)
F05 = '"Feature_05_Foreign_Domestic_Broker_Detail"'
STAGED = ('bulk5', 'index_market_calendar', 'feature_02_v2_daily_base', 'calc1', 'calc2', 'calc3', 'calc4', 'calc5',
          'calc6', 'strict5', 'frequency_daily', 'frequency_masks', 'index_prices', 'collapsed6')
DETAIL_COLS = ('trade_date', 'ticker', 'broker', 'market_board', 'investor_type', 'buy_value', 'sell_value',
               'net_value', 'buy_lots', 'sell_lots', 'net_lots', 'buy_freq', 'sell_freq', 'source_balance_gap',
               'calculated_at') + b.COVER

emit = b.emit


def load_entities(db, tickers=None):
    """Feature_Index_Entity rows this script computes (every member source but ALL_SOURCE_SYMBOLS, IHSG's)."""
    rows = db.execute('''SELECT ticker, entity_kind, member_source, list_key, sector, has_price, rows_from
        FROM public."Feature_Index_Entity" WHERE member_source <> 'ALL_SOURCE_SYMBOLS'
        AND (%s::text[] IS NULL OR ticker = ANY(%s::text[])) ORDER BY ticker''', (tickers, tickers)).fetchall()
    found = {r['ticker'] for r in rows}
    unknown = sorted(set(tickers or ()) - found)
    if unknown:
        raise ValueError(f'not entities of Feature_Index_Entity this script computes (IHSG has its own): {unknown}')
    for r in rows:
        if r['rows_from'] is None:
            raise ValueError(f'{r["ticker"]}: rows_from is empty')
        if r['has_price'] and not db.execute('SELECT public.is_universe_index(%s) AS ok', (r['ticker'],)).fetchone()['ok']:
            raise ValueError(f'{r["ticker"]}: has_price but not an index of IDX_Stock_Universe')
    return rows


def stage_members(db, tickers):
    """entity_member(ticker, symbol, valid_from, valid_to): the member periods, half open; see the module text."""
    db.execute('DROP TABLE IF EXISTS entity_member')
    db.execute('''CREATE TEMP TABLE entity_member ON COMMIT PRESERVE ROWS AS
      WITH lists AS (
        SELECT h.list_key, h."Ticker" AS symbol, h.pit_valid_from AS f, coalesce(h.pit_valid_to, 'infinity'::date) AS t
        FROM public."Stock_List_Member_History" h
        WHERE h.list_key IN (SELECT list_key FROM public."Feature_Index_Entity" WHERE ticker = ANY(%(t)s::text[]))
          AND (h.pit_valid_to IS NULL OR h.pit_valid_from < h.pit_valid_to)),
      list_first AS (SELECT list_key, min(f) AS first FROM lists GROUP BY list_key),
      universe AS (
        SELECT h."Ticker" AS symbol, h."Sector" AS sector, h."Security Type" AS kind, h.pit_valid_from AS f,
               coalesce(h.pit_valid_to, 'infinity'::date) AS t
        FROM public."IDX_Stock_Universe_History" h
        WHERE h.pit_valid_to IS NULL OR h.pit_valid_from < h.pit_valid_to),
      stock_first AS (SELECT symbol, min(f) AS first FROM universe GROUP BY symbol)
      SELECT e.ticker, l.symbol, CASE WHEN l.f = lf.first THEN '-infinity'::date ELSE l.f END AS valid_from, l.t AS valid_to
      FROM public."Feature_Index_Entity" e JOIN lists l ON l.list_key = e.list_key JOIN list_first lf ON lf.list_key = e.list_key
      WHERE e.member_source = 'STOCK_LIST' AND e.ticker = ANY(%(t)s::text[])
      UNION ALL
      SELECT e.ticker, u.symbol, CASE WHEN u.f = sf.first THEN '-infinity'::date ELSE u.f END, u.t
      FROM public."Feature_Index_Entity" e JOIN universe u ON u.sector = e.sector AND u.kind = 'stock'
      JOIN stock_first sf ON sf.symbol = u.symbol
      WHERE e.member_source = 'UNIVERSE_SECTOR' AND e.ticker = ANY(%(t)s::text[])''', {'t': tickers})
    db.execute('CREATE INDEX ON entity_member (symbol)')
    db.execute('ANALYZE entity_member')
    overlap = db.execute('''SELECT a.ticker, a.symbol FROM entity_member a JOIN entity_member b ON a.ticker = b.ticker
        AND a.symbol = b.symbol AND a.ctid < b.ctid AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to LIMIT 5''').fetchall()
    if overlap:
        raise RuntimeError(f'overlapping member periods (a stock would be counted twice): {overlap}')
    counts = {r['ticker']: r for r in db.execute('''SELECT ticker, count(DISTINCT symbol) AS symbols,
        count(*) FILTER (WHERE valid_from > '-infinity' OR valid_to < 'infinity') AS dated_periods
        FROM entity_member GROUP BY ticker''')}
    empty = sorted(set(tickers) - set(counts))
    if empty:
        raise RuntimeError(f'entities without members: {empty}')
    emit('members_staged', entities=len(counts), periods=sum(r['symbols'] for r in counts.values()),
         dated_periods={t: r['dated_periods'] for t, r in counts.items() if r['dated_periods']})
    return counts


def create_read_tables(db):
    db.execute('DROP TABLE IF EXISTS bulk5_all, bulk5_universe_all, hist6, hist_universe')
    db.execute(f'CREATE TEMP TABLE bulk5_all (LIKE public.{F05} INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS')
    db.execute('ALTER TABLE bulk5_all ' + ','.join(f'ADD COLUMN {c} bigint NOT NULL DEFAULT 0' for c in b.COVER))
    db.execute('CREATE TEMP TABLE hist6 (LIKE bulk5_all INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS')
    db.execute('ALTER TABLE hist6 ADD COLUMN strict_buy_freq bigint, ADD COLUMN strict_sell_freq bigint')
    db.execute('''CREATE TEMP TABLE bulk5_universe_all (ticker text, trade_date date, broker text, investor_type text,
        market_board text, bv numeric, sv numeric, bl numeric, sl numeric, gap boolean) ON COMMIT PRESERVE ROWS''')
    db.execute('''CREATE TEMP TABLE hist_universe (ticker text, trade_date date, investor_type text, market_board text,
        bv numeric, sv numeric, bl numeric, sl numeric, gap boolean) ON COMMIT PRESERVE ROWS''')


READ = '''WITH r AS MATERIALIZED (
    SELECT "Date", "Symbol", "Broker", "Investor Type", "Market Board", "Buy Value", "Sell Value", "Buy Lots",
           "Sell Lots", buy_freq, sell_freq, SUM("Buy Value") OVER w <> SUM("Sell Value") OVER w AS gap,
           "Symbol" IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" u WHERE u."Security Type" <> 'index') AS in_universe
    FROM public."IDX_Broker_Summary"
    WHERE "Date" >= %(lo)s AND "Date" < %(hi)s
      AND "Symbol" IN (SELECT symbol FROM entity_member WHERE ticker = ANY(%(read)s::text[]))
    WINDOW w AS (PARTITION BY "Date", "Symbol", "Market Board")),
 j AS MATERIALIZED (
    SELECT r.*, m.ticker FROM r JOIN entity_member m ON m.symbol = r."Symbol" AND r."Date" >= m.valid_from
      AND r."Date" < m.valid_to WHERE m.ticker = ANY(%(read)s::text[])),
 d AS MATERIALIZED (
    SELECT "Date" AS trade_date, ticker, "Broker"::text AS broker, "Market Board"::text AS market_board,
           "Investor Type"::text AS investor_type, SUM("Buy Value") AS bv, SUM("Sell Value") AS sv,
           SUM("Buy Value" - "Sell Value") AS nv, SUM("Buy Lots") AS bl, SUM("Sell Lots") AS sl,
           SUM("Buy Lots" - "Sell Lots") AS nl, SUM(buy_freq)::bigint AS bf, SUM(sell_freq)::bigint AS sf,
           bool_or(gap) AS gap, COUNT(*) AS n, COUNT(buy_freq) AS nb, COUNT(sell_freq) AS ns
    FROM j GROUP BY 1, 2, 3, 4, 5),
 detail AS (
    INSERT INTO bulk5_all (trade_date, ticker, broker, market_board, investor_type, buy_value, sell_value, net_value,
           buy_lots, sell_lots, net_lots, buy_freq, sell_freq, source_balance_gap, calculated_at, frequency_source_rows,
           buy_freq_known_rows, sell_freq_known_rows, buy_freq_missing_rows, sell_freq_missing_rows)
    SELECT trade_date, ticker, broker, market_board, investor_type, bv, sv, nv, bl, sl, nl, bf, sf, gap,
           statement_timestamp(), n, nb, ns, n - nb, n - ns
    FROM d WHERE ticker = ANY(%(detail)s::text[]) RETURNING 1),
 detail_universe AS (
    INSERT INTO bulk5_universe_all SELECT ticker, "Date", "Broker", "Investor Type", "Market Board", SUM("Buy Value"),
           SUM("Sell Value"), SUM("Buy Lots"), SUM("Sell Lots"), bool_or(gap)
    FROM j WHERE in_universe AND ticker = ANY(%(detail)s::text[]) GROUP BY 1, 2, 3, 4, 5 RETURNING 1),
 collapsed_universe AS (
    INSERT INTO hist_universe SELECT ticker, "Date", "Investor Type", "Market Board", SUM("Buy Value"), SUM("Sell Value"),
           SUM("Buy Lots"), SUM("Sell Lots"), bool_or(gap)
    FROM j WHERE in_universe AND ticker = ANY(%(collapse)s::text[]) GROUP BY 1, 2, 3, 4 RETURNING 1)
INSERT INTO hist6 (trade_date, ticker, broker, market_board, investor_type, buy_value, sell_value, net_value, buy_lots,
       sell_lots, net_lots, buy_freq, sell_freq, source_balance_gap, calculated_at, frequency_source_rows,
       buy_freq_known_rows, sell_freq_known_rows, buy_freq_missing_rows, sell_freq_missing_rows, strict_buy_freq,
       strict_sell_freq)
SELECT trade_date, ticker, '*', market_board, investor_type, SUM(bv), SUM(sv), SUM(nv), SUM(bl), SUM(sl), SUM(nl),
       SUM(bf)::bigint, SUM(sf)::bigint, bool_or(gap), statement_timestamp(), SUM(n), SUM(nb), SUM(ns), SUM(n - nb),
       SUM(n - ns), SUM(CASE WHEN nb = n THEN bf END)::bigint, SUM(CASE WHEN ns = n THEN sf END)::bigint
FROM d WHERE ticker = ANY(%(collapse)s::text[]) GROUP BY trade_date, ticker, market_board, investor_type'''

# Feature 05 (stock) of the universe members of the entities, by broker / by board and investor type: the cross-check
CHECK_DETAIL = f'''WITH a AS (
    SELECT m.ticker, f.trade_date, f.broker, f.investor_type, f.market_board, SUM(f.buy_value) AS bv,
           SUM(f.sell_value) AS sv, SUM(f.buy_lots) AS bl, SUM(f.sell_lots) AS sl, bool_or(f.source_balance_gap) AS gap
    FROM public.{F05} f JOIN entity_member m ON m.symbol = f.ticker AND f.trade_date >= m.valid_from
      AND f.trade_date < m.valid_to AND m.ticker = ANY(%(t)s::text[])
    WHERE f.trade_date >= %(lo)s AND f.trade_date < %(hi)s
      AND f.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" u WHERE u."Security Type" <> 'index')
    GROUP BY 1, 2, 3, 4, 5),
 c AS (SELECT * FROM bulk5_universe_all WHERE trade_date >= %(lo)s AND trade_date < %(hi)s)
SELECT count(*) AS n FROM ((SELECT * FROM a EXCEPT SELECT * FROM c) UNION ALL (SELECT * FROM c EXCEPT SELECT * FROM a)) x'''
CHECK_COLLAPSED = f'''WITH a AS (
    SELECT m.ticker, f.trade_date, f.investor_type, f.market_board, SUM(f.buy_value) AS bv, SUM(f.sell_value) AS sv,
           SUM(f.buy_lots) AS bl, SUM(f.sell_lots) AS sl, bool_or(f.source_balance_gap) AS gap
    FROM public.{F05} f JOIN entity_member m ON m.symbol = f.ticker AND f.trade_date >= m.valid_from
      AND f.trade_date < m.valid_to AND m.ticker = ANY(%(t)s::text[])
    WHERE f.trade_date >= %(lo)s AND f.trade_date < %(hi)s
      AND f.ticker IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" u WHERE u."Security Type" <> 'index')
    GROUP BY 1, 2, 3, 4),
 c AS (SELECT * FROM hist_universe WHERE trade_date >= %(lo)s AND trade_date < %(hi)s)
SELECT count(*) AS n FROM ((SELECT * FROM a EXCEPT SELECT * FROM c) UNION ALL (SELECT * FROM c EXCEPT SELECT * FROM a)) x'''


def read_months(db, first, last, detail, collapse, window_first):
    """One pass over IDX_Broker_Summary [first, last]: collapsed rows (hist6) for `collapse` entities every month, broker
    rows (bulk5_all) for `detail` entities from window_first. Each month is cross-checked before the next."""
    read = sorted(set(detail) | set(collapse))
    for lo, hi in b.month_ranges(first, last):
        started = time.monotonic()
        months_detail = detail if hi > window_first else []
        if not months_detail and not collapse:
            continue
        args = {'lo': lo, 'hi': hi, 'read': sorted(set(months_detail) | set(collapse)), 'detail': months_detail,
                'collapse': list(collapse)}
        db.execute(READ, args)
        bad = 0
        if months_detail:
            bad += db.execute(CHECK_DETAIL, {'t': months_detail, 'lo': lo, 'hi': hi}).fetchone()['n']
        if collapse:
            bad += db.execute(CHECK_COLLAPSED, {'t': list(collapse), 'lo': lo, 'hi': hi}).fetchone()['n']
        if bad:
            raise RuntimeError(f'members raw/Feature 05 mismatch {lo}: {bad} keys (entities {read})')
        emit('raw_month_staged', start=lo, detail_entities=len(months_detail), collapsed_entities=len(collapse),
             seconds=round(time.monotonic() - started, 2))
    db.execute('CREATE INDEX IF NOT EXISTS bulk5_all_ticker ON bulk5_all (ticker, trade_date)')
    db.execute('CREATE INDEX IF NOT EXISTS hist6_ticker ON hist6 (ticker, trade_date)')
    db.execute('ANALYZE bulk5_all')
    db.execute('ANALYZE hist6')


def drop_staged(db):
    for name in STAGED:
        db.execute(sql.SQL('DROP TABLE IF EXISTS pg_temp.{}').format(sql.Identifier(name)))


F06_INDEX = '"Feature_06_Foreign_Domestic_INDEX"'


def continuation_start(db, ticker, from_date):
    """The MIN_SESSIONS-th session of the entity before from_date (hist6): Feature 06 of a continuing entity is staged
    from it, so refresh_feature_06's own range start (312 sessions before from_date) is exactly this date."""
    r = db.execute('''SELECT count(*) AS n, min(d) AS s0 FROM (SELECT DISTINCT trade_date AS d FROM hist6
        WHERE ticker = %s AND trade_date < %s ORDER BY d DESC LIMIT %s) x''', (ticker, from_date, MIN_SESSIONS)).fetchone()
    if r['n'] < MIN_SESSIONS:
        raise RuntimeError(f'{ticker}: {r["n"]} sessions before {from_date}, {MIN_SESSIONS} needed')
    return r['s0']


SEED_ANCHOR = f'''INSERT INTO calc6 (trade_date, ticker, market_board, foreign_buy_1d, foreign_sell_1d, foreign_net_1d,
      domestic_buy_1d, domestic_sell_1d, domestic_net_1d, foreign_cumulative_net, domestic_cumulative_net,
      source_balance_gap)
    WITH last AS (SELECT DISTINCT ON (market_board) market_board, foreign_cumulative_net AS c_f,
           domestic_cumulative_net AS c_d FROM public.{F06_INDEX} WHERE ticker = %(t)s AND trade_date < %(f)s
           ORDER BY market_board, trade_date DESC),
         win AS (SELECT market_board, SUM(net_value) FILTER (WHERE investor_type = 'Foreign') AS n_f,
           SUM(net_value) FILTER (WHERE investor_type = 'Domestic') AS n_d FROM collapsed6
           WHERE trade_date >= %(s0)s AND trade_date < %(f)s GROUP BY market_board)
    SELECT %(s0)s::date - 1, %(t)s, l.market_board, 0, 0, 0, 0, 0, 0, l.c_f - coalesce(w.n_f, 0),
           l.c_d - coalesce(w.n_d, 0), false
    FROM last l LEFT JOIN win w USING (market_board)'''


def seed_anchors(db, ticker, s0, from_date):
    """Feature 06 of a continuing entity: its stored rows start at rows_from, so the anchor refresh_feature_06 reads
    (the last row before its range start) is derived: per board the stored cumulative net of the last row before
    from_date minus the daily nets from s0 to from_date (exact numeric), as a row the day before s0 that is never
    written. The stored rows from s0 are copied too (the accepted sample compares them)."""
    db.execute(SEED_ANCHOR, {'t': ticker, 'f': from_date, 's0': s0})
    temp = {r['attname'] for r in db.execute("""SELECT attname FROM pg_attribute WHERE attrelid = 'pg_temp.calc6'::regclass
        AND attnum > 0 AND NOT attisdropped""")}
    common = sql.SQL(',').join(sql.Identifier(c) for c in b.cols(db, 'Feature_06_Foreign_Domestic_INDEX') if c in temp)
    db.execute(sql.SQL('INSERT INTO calc6 ({}) SELECT {} FROM public.{} WHERE ticker=%s AND trade_date>=%s AND trade_date<%s').format(
        common, common, sql.Identifier('Feature_06_Foreign_Domestic_INDEX')), (ticker, s0, from_date))


def stage_entity(db, e, window_first, from_date, mode, broker_first, history_first):
    """The per-entity session tables in the names the IHSG stages read, then the features and their checks.
    broker_first: the first broker date; history_first: where hist6 starts in this run."""
    ticker = e['ticker']
    drop_staged(db)
    db.execute(f'CREATE TEMP TABLE bulk5 (LIKE public.{F05} INCLUDING ALL) ON COMMIT PRESERVE ROWS')
    db.execute('ALTER TABLE bulk5 ' + ','.join(f'ADD COLUMN {c} bigint NOT NULL DEFAULT 0' for c in b.COVER))
    names = sql.SQL(',').join(map(sql.Identifier, DETAIL_COLS))
    db.execute(sql.SQL('INSERT INTO bulk5 ({}) SELECT {} FROM bulk5_all WHERE ticker=%s AND trade_date>=%s').format(
        names, names), (ticker, window_first))
    db.execute('ANALYZE bulk5')
    db.execute('''CREATE TEMP TABLE index_market_calendar ON COMMIT PRESERVE ROWS AS
        SELECT DISTINCT trade_date AS date FROM bulk5''')
    db.execute('CREATE UNIQUE INDEX ON index_market_calendar(date)')
    before = db.execute('SELECT count(*) AS n FROM index_market_calendar WHERE date < %s', (from_date,)).fetchone()['n']
    if before < MIN_SESSIONS:
        raise RuntimeError(f'{ticker}: {before} sessions before {from_date} in the window, {MIN_SESSIONS} needed')
    consistent = db.execute('''WITH d AS (SELECT trade_date, market_board, investor_type, SUM(buy_value) bv, SUM(sell_value) sv,
          SUM(net_value) nv, SUM(buy_lots) bl, SUM(sell_lots) sl, SUM(net_lots) nl, SUM(buy_freq) bf, SUM(sell_freq) sf,
          bool_or(source_balance_gap) g, SUM(frequency_source_rows) n, SUM(buy_freq_known_rows) nb, SUM(sell_freq_known_rows) ns,
          SUM(CASE WHEN buy_freq_known_rows = frequency_source_rows THEN buy_freq END) xb,
          SUM(CASE WHEN sell_freq_known_rows = frequency_source_rows THEN sell_freq END) xs
          FROM bulk5 GROUP BY 1, 2, 3),
        c AS (SELECT trade_date, market_board, investor_type, buy_value, sell_value, net_value, buy_lots, sell_lots, net_lots,
          buy_freq::numeric, sell_freq::numeric, source_balance_gap, frequency_source_rows::numeric, buy_freq_known_rows::numeric,
          sell_freq_known_rows::numeric, strict_buy_freq::numeric, strict_sell_freq::numeric FROM hist6
          WHERE ticker = %s AND trade_date >= %s)
        SELECT count(*) AS n FROM ((SELECT * FROM d EXCEPT SELECT * FROM c) UNION ALL (SELECT * FROM c EXCEPT SELECT * FROM d)) x''',
                            (ticker, window_first)).fetchone()['n']
    if consistent:
        raise RuntimeError(f'{ticker}: broker rows and collapsed rows differ on {consistent} keys in the window')
    b.create_stages(db)
    # Feature 06 from the collapsed rows: the whole history (first fill), or from continuation_start with derived
    # anchors (continuation). A continuing entity with a board traded in the window but never stored (its cumulative
    # before rows_from is not in the stored rows) is recomputed from the first broker date instead.
    anchored = s0 = None
    if mode == 'continue':
        s0 = continuation_start(db, ticker, from_date)
        missing = [r['market_board'] for r in db.execute(f'''SELECT DISTINCT market_board FROM hist6 WHERE ticker = %s
            AND trade_date >= %s AND market_board NOT IN (SELECT DISTINCT market_board FROM public.{F06_INDEX}
            WHERE ticker = %s AND trade_date < %s)''', (ticker, s0, ticker, from_date))]
        if missing:
            emit('feature6_full_history', ticker=ticker, boards_without_stored_rows=missing)
            if history_first > broker_first:
                read_months(db, broker_first, history_first - timedelta(days=1), [], [ticker], history_first)
            s0 = None
        else:
            anchored = from_date
    db.execute('CREATE TEMP TABLE collapsed6 ON COMMIT PRESERVE ROWS AS SELECT * FROM hist6 WHERE ticker=%s AND trade_date>=%s',
               (ticker, s0 or broker_first))
    db.execute('ANALYZE collapsed6')
    if anchored:
        seed_anchors(db, ticker, s0, from_date)
    started = time.monotonic()
    b.stage2(db, ticker, whole=True)
    f2 = round(time.monotonic() - started, 1)
    freq = b.stage6(db, ticker, anchored, s0, collapsed='collapsed6', seed=False)
    price_rows = len(b.stage_prices(db, ticker)) if e['has_price'] else 0
    b.validate2(db)
    b.validate3(db)
    b.validate6(db, freq, anchored, s0)
    if mode == 'continue':
        sample = db.execute('SELECT max(date) AS d FROM index_market_calendar WHERE date<%s', (from_date,)).fetchone()['d']
        b.compare_sample(db, ticker, sample, {1, 2, 3, 4, 5, 6} if e['has_price'] else {2, 3, 5, 6})
    staged = {f: db.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE {}>=%s').format(
        sql.Identifier('calc' + str(f)), sql.Identifier('date' if f in (1, 2, 3) else 'trade_date')), (from_date,)).fetchone()['n']
        for f in features_of(e)}
    emit('entity_validated', ticker=ticker, mode=mode, from_date=from_date, window_first=window_first,
         sessions_before=before, price_rows=price_rows, rows_to_write=staged, f02_seconds=f2,
         seconds=round(time.monotonic() - started, 1))
    return staged


def features_of(e):
    return (1, 2, 3, 4, 5, 6) if e['has_price'] else (2, 3, 5, 6)


def market_window_start(db, before, sessions=b.WARMUP_SESSIONS):
    """The sessions-th broker date before `before` (IDX_Broker_Summary, the market calendar), one index probe per date;
    None with fewer dates."""
    r = db.execute('''WITH RECURSIVE s(d, n) AS (
          SELECT max("Date"), 1 FROM public."IDX_Broker_Summary" WHERE "Date" < %s
          UNION ALL
          SELECT (SELECT max("Date") FROM public."IDX_Broker_Summary" WHERE "Date" < s.d), n + 1 FROM s
          WHERE s.d IS NOT NULL AND n < %s)
        SELECT count(d) AS n, min(d) AS w FROM s''', (before, sessions)).fetchone()
    return r['w'] if r['n'] == sessions else None


def plan(db, ents, until=None, since=None):
    """Per entity its mode and first date written; the common warmup window and the broker range. since: recompute a
    continuing entity from that date (raw rows of older dates changed), never before its rows_from."""
    bounds = db.execute('SELECT MIN("Date") AS first, MAX("Date") AS last FROM public."IDX_Broker_Summary"').fetchone()
    last = min(bounds['last'], until) if until else bounds['last']
    for e in ents:
        newest = db.execute('SELECT max(date) AS d FROM public."Feature_03_Stock_Broker_Daily_INDEX" WHERE ticker=%s',
                            (e['ticker'],)).fetchone()['d']
        e['mode'] = 'continue' if newest else 'first'
        nxt = newest + timedelta(days=1) if newest else None
        e['from_date'] = max(min(since, nxt) if since else nxt, e['rows_from']) if newest else e['rows_from']
    start = min(e['from_date'] for e in ents)
    window_first = market_window_start(db, start)
    if window_first is None:
        raise RuntimeError(f'fewer than {b.WARMUP_SESSIONS} broker dates before {start}')
    todo = [e for e in ents if e['from_date'] <= last]
    return {'first': bounds['first'], 'last': last, 'window_first': window_first, 'entities': todo,
            'up_to_date': [e['ticker'] for e in ents if e['from_date'] > last]}


def run(db, tickers=None, apply=False, batch=10, until=None, since=None, snapshot=None):
    snapshot = snapshot or uuid.uuid4()
    ents = load_entities(db, tickers)
    for e in ents:
        if not db.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok', ('index-bulk:' + e['ticker'],)).fetchone()['ok']:
            raise RuntimeError(f'Another INDEX writer is active for {e["ticker"]}')
    p = plan(db, ents, until, since)
    todo = p['entities']
    emit('plan', broker_first=p['first'], last=p['last'], window_first=p['window_first'], entities=len(todo),
         up_to_date=p['up_to_date'], modes={e['ticker']: [e['mode'], e['from_date']] for e in todo}, apply=apply)
    if not todo:
        return {'entities': 0, 'written': {}}
    stage_members(db, [e['ticker'] for e in todo])
    first_fill = [e['ticker'] for e in todo if e['mode'] == 'first']
    history_first = p['first'] if first_fill else p['window_first']
    written = {}
    batches = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    for k, group in enumerate(batches):
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            create_read_tables(db) if k == 0 else db.execute('TRUNCATE bulk5_all, bulk5_universe_all')
            names = [e['ticker'] for e in group]
            # the first batch's pass reads every month and fills hist6 for all entities; later batches read the window
            read_months(db, history_first if k == 0 else p['window_first'], p['last'], names,
                        [e['ticker'] for e in todo] if k == 0 else [], p['window_first'])
        for e in group:
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                staged = stage_entity(db, e, p['window_first'], e['from_date'], e['mode'], p['first'], history_first)
            if apply:
                b.apply_chunks(db, e['ticker'], snapshot, from_date=e['from_date'], features=features_of(e),
                               all_features=True, catalog=False)
            written[e['ticker']] = staged if apply else {}
    emit('complete', committed=apply, entities=len(todo), snapshot_id=snapshot)
    return {'entities': len(todo), 'written': written, 'window_first': p['window_first'], 'last': p['last']}


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--tickers', help='comma separated; default every entity but IHSG')
    a.add_argument('--batch', type=int, default=10, help='entities read by broker at a time (temporary table size)')
    a.add_argument('--until', type=date.fromisoformat, help='last broker date read (default the newest)')
    a.add_argument('--since', type=date.fromisoformat, help='recompute continuing entities from this date')
    a.add_argument('--apply', action='store_true', help='write; default a dry run')
    args = a.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(',')] if args.tickers else None
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, autocommit=True,
                         application_name='index-entities-backfill') as db:
        db.execute("SET statement_timeout='30min'")
        db.execute("SET lock_timeout='10s'")
        db.execute("SET work_mem='64MB'")
        db.execute('SET max_parallel_workers_per_gather=0')
        run(db, tickers, args.apply, args.batch, args.until, args.since)


if __name__ == '__main__':
    main()
