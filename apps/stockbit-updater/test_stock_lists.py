"""stock_lists.py and migration 20261109_001 against a scratch PostgreSQL (EXEC-STOCK-CATALOG). Needs
UPDATER_TEST_POSTGRES_URL (or ORC_TEST_POSTGRES_URL) of a server where the user may CREATE DATABASE: each test builds a
fresh database with the live-like dependencies (columns, keys and checks read from dev 2026-11-09) and the real
migration file, and drops it afterwards. Stockbit is a fake answering the four endpoints the step reads."""
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import psycopg
import pytest

import stock_lists
import stockbit_ihsg_daily as source

URL = os.environ.get('UPDATER_TEST_POSTGRES_URL') or os.environ.get('ORC_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='UPDATER_TEST_POSTGRES_URL is not set')
MIGRATION = Path(__file__).resolve().parents[2] / 'database/migrations/20261109_001_stock_list.sql'

BASE = r'''
CREATE EXTENSION IF NOT EXISTS btree_gist;
DO $r$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN CREATE ROLE pgweb_reader NOLOGIN; END IF; END $r$;
CREATE TABLE public."Table_Catalog" (table_schema text NOT NULL DEFAULT 'public'::text, table_name text NOT NULL, category text NOT NULL, definition text, grain text, primary_key_columns text[] NOT NULL DEFAULT '{}'::text[], source_system text, source_tables text[] NOT NULL DEFAULT '{}'::text[], source_code_paths text[] NOT NULL DEFAULT '{}'::text[], update_rule text, related_functions text[] NOT NULL DEFAULT '{}'::text[], documentation_status text NOT NULL DEFAULT 'NEEDS_REVIEW'::text, created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP, readiness_mode text NOT NULL DEFAULT 'NOT_APPLICABLE'::text, readiness_date_column text, observation_date_column text, data_available_at_column text, availability_rule text NOT NULL DEFAULT 'Not applicable.'::text, point_in_time_status text NOT NULL DEFAULT 'NOT_APPLICABLE'::text, historical_metadata_method text,
  CONSTRAINT "Table_Catalog_pkey" PRIMARY KEY (table_schema, table_name),
  CONSTRAINT "Table_Catalog_availability_rule_check" CHECK ((btrim(availability_rule) <> ''::text)),
  CONSTRAINT "Table_Catalog_definition_check" CHECK ((((definition IS NULL) AND (documentation_status = 'NEEDS_REVIEW'::text)) OR ((definition IS NOT NULL) AND (btrim(definition) <> ''::text)))),
  CONSTRAINT "Table_Catalog_documentation_status_check" CHECK ((documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))),
  CONSTRAINT "Table_Catalog_name_check" CHECK ((btrim(table_name) <> ''::text)),
  CONSTRAINT "Table_Catalog_point_in_time_status_check" CHECK ((point_in_time_status = ANY (ARRAY['AVAILABLE'::text, 'PARTIAL'::text, 'UNAVAILABLE'::text, 'NOT_APPLICABLE'::text]))),
  CONSTRAINT "Table_Catalog_readiness_column_check" CHECK ((((readiness_mode = 'DATA_DATE'::text) AND (readiness_date_column IS NOT NULL) AND (btrim(readiness_date_column) <> ''::text)) OR ((readiness_mode <> 'DATA_DATE'::text) AND (readiness_date_column IS NULL)))),
  CONSTRAINT "Table_Catalog_readiness_mode_check" CHECK ((readiness_mode = ANY (ARRAY['DATA_DATE'::text, 'REFERENCE_STATE'::text, 'NOT_APPLICABLE'::text]))),
  CONSTRAINT "Table_Catalog_target_schema_check" CHECK ((table_schema = 'public'::text)),
  CONSTRAINT "Table_Catalog_timestamps_check" CHECK ((updated_at >= created_at)));
CREATE TABLE public."Column_Catalog" (table_schema text NOT NULL, table_name text NOT NULL, column_name text NOT NULL, ordinal_position integer NOT NULL, data_type text NOT NULL, is_nullable boolean NOT NULL, default_expression text, is_primary_key boolean NOT NULL, definition text, source_column_or_expression text, unit text, null_rule text, source_code_paths text[] NOT NULL DEFAULT '{}'::text[], documentation_status text NOT NULL DEFAULT 'NEEDS_REVIEW'::text, created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Column_Catalog_pkey" PRIMARY KEY (table_schema, table_name, column_name),
  CONSTRAINT "Column_Catalog_definition_check" CHECK ((((definition IS NULL) AND (documentation_status = 'NEEDS_REVIEW'::text)) OR ((definition IS NOT NULL) AND (btrim(definition) <> ''::text)))),
  CONSTRAINT "Column_Catalog_documentation_status_check" CHECK ((documentation_status = ANY (ARRAY['VERIFIED'::text, 'PARTIAL'::text, 'NEEDS_REVIEW'::text]))),
  CONSTRAINT "Column_Catalog_name_check" CHECK (((btrim(column_name) <> ''::text) AND (btrim(data_type) <> ''::text))),
  CONSTRAINT "Column_Catalog_position_check" CHECK ((ordinal_position > 0)),
  CONSTRAINT "Column_Catalog_table_fkey" FOREIGN KEY (table_schema, table_name) REFERENCES "Table_Catalog"(table_schema, table_name),
  CONSTRAINT "Column_Catalog_timestamps_check" CHECK ((updated_at >= created_at)));
CREATE TABLE public."IDX_Stock_Universe" ("Region" text NOT NULL, "Country" text NOT NULL, "Company Name" text NOT NULL, "Ticker" text NOT NULL, "Exchange" text NOT NULL, "TradingView Symbol" text NOT NULL, "TradingView URL" text NOT NULL, "Security Type" text NOT NULL, "Type Specs" text NOT NULL, "Is Common Stock" text NOT NULL, "TradingView Country" text NOT NULL, "Currency" text NOT NULL, "Fundamental Currency" text NOT NULL, "ISIN" text NOT NULL, "Sector" text NOT NULL, "Industry" text NOT NULL, price_feed_daily numeric, CONSTRAINT "IDX_Stock_Universe_pkey" PRIMARY KEY ("Ticker"));
CREATE TABLE public."Monitoring_Stockbit_Update" (execution_id uuid NOT NULL, mode text NOT NULL, status text NOT NULL, started_at timestamp with time zone NOT NULL, finished_at timestamp with time zone, deployment_id text, token_expires_at timestamp with time zone, broker jsonb, broker_dates jsonb, broker_rows bigint, features jsonb, index_result jsonb, events jsonb, last_error text, updated_at timestamp with time zone NOT NULL DEFAULT now(), CONSTRAINT "Monitoring_Stockbit_Update_pkey" PRIMARY KEY (execution_id));
INSERT INTO public."Table_Catalog" (table_name, category, definition, documentation_status) VALUES ('Monitoring_Stockbit_Update', 'Monitoring', 'Rounds.', 'VERIFIED'), ('IDX_Stock_Universe', 'Reference', 'Universe.', 'PARTIAL');
INSERT INTO public."IDX_Stock_Universe" SELECT 'Asia', 'Indonesia', 'Company ' || t, t, 'IDX', 'IDX:' || t, 'u', 'stock', 'common', 'Yes', 'ID', 'IDR', 'IDR', 'ID' || t, 'S', 'I', NULL
  FROM unnest(ARRAY['BBCA', 'BBRI', 'TLKM']) t;
'''


def _url(dbname):
    parts = urlsplit(URL)
    return urlunsplit(parts._replace(path='/' + dbname))


@pytest.fixture()
def db():
    name = 'stocklist_' + uuid.uuid4().hex[:10]
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE {name}')
    try:
        with psycopg.connect(_url(name), autocommit=True) as conn:
            conn.execute(BASE)
            conn.execute(MIGRATION.read_text())
            yield conn
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')


class Market:
    """Stockbit as the step reads it: groups and indices from Stock_List, members made up per list (a numbered index
    gets exactly its count), plus lists Stockbit shows that the user did not choose."""

    def __init__(self, conn):
        self.lists = conn.execute('SELECT list_key, list_kind, source_id, name, expected_count FROM public."Stock_List"'
                                  ' ORDER BY list_kind, sort_order').fetchall()
        self.members = {}
        for i, (key, kind, sid, name, expected) in enumerate(self.lists):
            n = expected or (3 + i % 4)
            self.members[key] = ['BBCA', 'BBRI'] + [f'T{i:02d}{j:03d}' for j in range(n - 2)]
        self.extra_index = [('1000005130', 'Suspended')]
        self.extra_group = []
        self.hide = set()
        self.status = 200
        self.calls = 0

    def get_json(self, path):
        self.calls += 1
        if self.status != 200:
            raise source.StockbitError(f'Stockbit authentication failed with HTTP {self.status}')
        url = urlsplit(path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == '/emitten/catalog':
            groups = [(sid, name) for key, kind, sid, name, _ in self.lists if kind == 'KONGLO' and key not in self.hide]
            groups += self.extra_group
            page, per = int(q['page']), 20
            chunk = groups[(page - 1) * per: page * per]
            total_page = max(1, -(-len(groups) // per))
            body = {'data': {'catalogs': [{'id': sid, 'catalog_name': name, 'catalog_code': name.upper()} for sid, name in chunk],
                             'paginate': {'current_page': Decimal(page), 'total_page': Decimal(total_page),
                                          'total_data': Decimal(len(groups))}}}
        elif url.path == '/emitten/sectors/88/subsectors':
            rows = [(sid, name) for key, kind, sid, name, _ in self.lists if kind == 'INDEX' and key not in self.hide]
            body = {'data': [{'id': sid, 'name': name} for sid, name in rows + self.extra_index]}
        elif url.path == '/order-trade/market-mover':
            tickers = self.members[f"KONGLO:{q['catalog_id']}"]
            page, per = int(q['page']), 100
            chunk = tickers[(page - 1) * per: page * per]
            body = {'data': {'mover_list': [{'stock_detail': {'code': t, 'name': 'Name ' + t}} for t in chunk],
                             'pagination': {'page': Decimal(page), 'has_next': page * per < len(tickers)}}}
        elif url.path.startswith('/emitten/v3/sector/88/subsector/'):
            sid = url.path.split('/')[6]
            body = {'data': [{'symbol': t, 'name': 'Name ' + t} for t in self.members[f'INDEX:{sid}']]}
        else:
            raise AssertionError(path)
        return body, b'', 1


def run(conn, market):
    events = []
    out = stock_lists.run(conn, 'token-not-used', uuid.uuid4(), lambda e, **k: events.append((e, k)), fetcher=market)
    return out, events


def one(conn, sql, *args):
    return (conn.execute(sql, args) if args else conn.execute(sql)).fetchone()[0]


def test_migration_seeds_lists_and_catalog(db):
    assert db.execute('SELECT list_kind, count(*), count(expected_count) FROM public."Stock_List" GROUP BY 1 ORDER BY 1'
                      ).fetchall() == [('INDEX', 33, 18), ('KONGLO', 33, 0)]
    assert one(db, '''SELECT count(*) FROM public."Table_Catalog" WHERE table_name LIKE 'Stock_List%' ''') == 5
    assert one(db, '''SELECT count(*) FROM information_schema.columns c WHERE c.table_schema = 'public'
        AND (c.table_name LIKE 'Stock_List%' OR c.column_name = 'stock_lists')
        AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_name = c.table_name
                        AND k.column_name = c.column_name)''') == 0
    assert one(db, '''SELECT has_table_privilege('pgweb_reader', 'public."Stock_List_By_Ticker"', 'SELECT')''') is True
    with pytest.raises(psycopg.errors.RaiseException, match='stock list objects exist'):
        db.execute(MIGRATION.read_text())


def test_first_round_captures_every_list(db):
    market = Market(db)
    out, events = run(db, market)
    total = sum(len(v) for v in market.members.values())
    assert out['status'] == 'SUCCESS' and out['lists'] == 66 and out['members'] == total and out['added'] == total
    assert out['removed'] == 0 and out['first_capture_lists'] == 66
    assert out['unlisted'] == [{'list_key': 'INDEX:1000005130', 'name': 'Suspended'}]
    assert out['unlisted_new'] == out['unlisted'] and events[-1][0] == 'stock_lists_done'
    assert one(db, 'SELECT count(*) FROM public."Stock_List_Member"') == total
    assert db.execute('''SELECT valid_basis, count(*), bool_and(valid_to IS NULL AND recorded_to IS NULL),
        bool_and(pit_valid_from = (timezone('Asia/Jakarta', recorded_from))::date + 1)
        FROM public."Stock_List_Member_History" GROUP BY 1''').fetchall() == [('FIRST_CAPTURE', total, True, True)]
    assert one(db, 'SELECT count(*) FROM public."Stock_List" WHERE member_count IS NULL OR first_seen_at IS NULL') == 0
    by = db.execute('''SELECT "Ticker", in_universe, list_count FROM public."Stock_List_By_Ticker"
                       WHERE "Ticker" IN ('BBCA', 'T00000') ORDER BY 1''').fetchall()
    assert by == [('BBCA', True, 66), ('T00000', False, 1)]
    assert market.calls == out['requests'] and out['requests'] >= 66 + 3


def test_same_data_again_is_no_change(db):
    market = Market(db)
    run(db, market)
    history = one(db, 'SELECT count(*) FROM public."Stock_List_Member_History"')
    out, _ = run(db, market)
    assert out['status'] == 'NO_CHANGE' and out['added'] == 0 and out['removed'] == 0 and out['changes'] == {}
    assert out['unlisted_new'] == [] and out['first_capture_lists'] == 0
    assert one(db, 'SELECT count(*) FROM public."Stock_List_Member_History"') == history


def shift_back(db, days):
    """As if the first round ran `days` days ago (the history's day arithmetic needs another date)."""
    db.execute('''UPDATE public."Stock_List_Member_History" SET valid_from = valid_from - %s,
                  recorded_from = recorded_from - make_interval(days => %s),
                  available_at = available_at - make_interval(days => %s)''', (days, days, days))
    db.execute('''UPDATE public."Stock_List_Member" SET first_seen_date = first_seen_date - %s,
                  last_seen_date = last_seen_date - %s''', (days, days))


def test_a_ticker_leaving_and_one_entering_keep_point_in_time_history(db):
    market = Market(db)
    run(db, market)
    shift_back(db, 3)
    key = 'KONGLO:13'
    left, entered = market.members[key][-1], 'NEWX'
    market.members[key] = market.members[key][:-1] + [entered]
    out, _ = run(db, market)
    assert out['status'] == 'SUCCESS' and out['added'] == 1 and out['removed'] == 1
    assert out['changes'] == {key: {'name': 'Danantara', 'added': [entered], 'removed': [left]}}
    rows = db.execute('''SELECT valid_basis, valid_to IS NULL, recorded_to IS NULL, superseded_reason,
        pit_valid_to IS NULL FROM public."Stock_List_Member_History" WHERE list_key = %s AND "Ticker" = %s
        ORDER BY history_id''', (key, left)).fetchall()
    # the first capture is superseded and kept; current knowledge: the membership closed at today's date
    assert rows == [('FIRST_CAPTURE', True, False, 'CHANGE_CAPTURED', False), ('FIRST_CAPTURE', False, True, None, False)]
    today = one(db, "SELECT (timezone('Asia/Jakarta', now()))::date")
    closed = db.execute('''SELECT valid_to, pit_valid_to FROM public."Stock_List_Member_History" WHERE list_key = %s
        AND "Ticker" = %s AND recorded_to IS NULL''', (key, left)).fetchone()
    assert closed[0] == today
    new = db.execute('''SELECT valid_basis, valid_from, pit_valid_from FROM public."Stock_List_Member_History"
        WHERE list_key = %s AND "Ticker" = %s''', (key, entered)).fetchall()
    assert len(new) == 1 and new[0][0] == 'CHANGE_CAPTURED' and new[0][1] == today
    assert new[0][2] == one(db, "SELECT (timezone('Asia/Jakarta', now()))::date + 1")
    assert one(db, 'SELECT count(*) FROM public."Stock_List_Member" WHERE list_key = %s AND "Ticker" = %s', key, left) == 0
    # a dated read uses every row's pit_valid_from <= date < pit_valid_to (the IDX_Stock_Universe_History rule, no filter
    # on recorded_to): yesterday finds the ticker that left and not the one that entered; tomorrow the reverse
    def members_on(day):
        return db.execute('''SELECT "Ticker" FROM public."Stock_List_Member_History" WHERE list_key = %s
            AND pit_valid_from <= %s AND (pit_valid_to IS NULL OR %s < pit_valid_to) AND "Ticker" IN (%s, %s)''',
                          (key, day, day, left, entered)).fetchall()
    assert members_on(today - timedelta(days=1)) == [(left,)]
    assert members_on(today + timedelta(days=1)) == [(entered,)]


def test_an_entry_removed_the_same_day_leaves_no_current_membership(db):
    market = Market(db)
    run(db, market)
    shift_back(db, 3)
    key = 'INDEX:467'   # IHSG: no count in its name
    market.members[key] = market.members[key] + ['SAME']
    run(db, market)
    market.members[key] = market.members[key][:-1]
    out, _ = run(db, market)
    assert out['removed'] == 1
    rows = db.execute('''SELECT recorded_to IS NULL, superseded_reason FROM public."Stock_List_Member_History"
                         WHERE list_key = %s AND "Ticker" = 'SAME' ''', (key,)).fetchall()
    assert rows == [(False, 'SAME_DAY_REVISION')]


@pytest.mark.parametrize('break_it, reason', [
    (lambda m: m.hide.add('KONGLO:9'), 'Stockbit no longer shows KONGLO:9'),
    (lambda m: m.members.__setitem__('INDEX:550', m.members['INDEX:550'][:-1]), 'INDEX:550 has 44 members, expected 45'),
    (lambda m: m.members.__setitem__('KONGLO:59', []), 'empty list KONGLO:59'),
    (lambda m: m.members.__setitem__('KONGLO:59', ['BBCA', 'BBCA', 'TLKM']), 'ticker given twice KONGLO:59 BBCA'),
    (lambda m: setattr(m, 'status', 401), 'authentication failed with HTTP 401'),
])
def test_a_refused_round_writes_nothing_and_is_a_warning(db, break_it, reason):
    market = Market(db)
    run(db, market)
    before = db.execute('''SELECT (SELECT count(*) FROM public."Stock_List_Member"),
        (SELECT count(*) FROM public."Stock_List_Member_History"),
        (SELECT max(last_seen_at) FROM public."Stock_List")''').fetchone()
    break_it(market)
    out, events = run(db, market)
    assert out['status'] == 'FAILED' and reason in out['warning'] and 'token' not in out['warning'].lower()
    assert events[-1][0] == 'stock_lists_failed'
    after = db.execute('''SELECT (SELECT count(*) FROM public."Stock_List_Member"),
        (SELECT count(*) FROM public."Stock_List_Member_History"),
        (SELECT max(last_seen_at) FROM public."Stock_List")''').fetchone()
    assert after == before
    assert db.execute('''SELECT status, error IS NOT NULL FROM public."Stock_List_Load_Log"
                         ORDER BY run_id DESC LIMIT 1''').fetchone() == ('FAILED', True)


def test_a_new_list_at_stockbit_is_reported_once_and_never_loaded(db):
    market = Market(db)
    run(db, market)
    market.extra_index.append(('1000007081', 'Margin'))
    out, _ = run(db, market)
    assert out['status'] == 'NO_CHANGE' and out['unlisted_new'] == [{'list_key': 'INDEX:1000007081', 'name': 'Margin'}]
    assert one(db, '''SELECT count(*) FROM public."Stock_List" WHERE source_id = '1000007081' ''') == 0
    out, _ = run(db, market)
    assert out['unlisted_new'] == []


def test_a_group_over_one_page_reads_every_page(db):
    market = Market(db)
    market.members['KONGLO:13'] = [f'G{i:04d}' for i in range(150)]
    out, _ = run(db, market)
    assert out['status'] == 'SUCCESS'
    assert one(db, '''SELECT member_count FROM public."Stock_List" WHERE list_key = 'KONGLO:13' ''') == 150


def test_the_step_fails_as_a_warning_without_its_tables(db):
    db.execute('DROP VIEW public."Stock_List_By_Ticker"')
    db.execute('DROP TABLE public."Stock_List_Member_History", public."Stock_List_Member", public."Stock_List_Load_Log",'
               ' public."Stock_List"')
    out, _ = run(db, Market.__new__(Market))
    assert out['status'] == 'FAILED' and 'log not written' in out['warning'] and out['run_id'] is None
