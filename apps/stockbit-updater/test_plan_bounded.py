"""EXEC-INDEX-INCREMENTAL (2): the bounded refresh plan (candidate dates from broker_summary_date_quality.checked_at
since the last successful refresh) must equal the full plan in every case it is used, and fall back to the full plan
when it cannot know (no watermark, a universe change, no full plan for 7 days, an error). Scratch database on
UPDATER_TEST_POSTGRES_URL's server; the stamping trigger is a stand-in for broker_summary_remark_new (same timing:
one stamp per date written by a statement)."""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import psycopg
import pytest

import refresh
import test_universe_only as base

URL = base.URL
pytestmark = pytest.mark.skipif(not URL, reason='UPDATER_TEST_POSTGRES_URL is not set')
D0, D1, D2 = date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)
EXTRA = '''
CREATE TABLE public."Monitoring_Stockbit_Update" (execution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), mode text,
 status text, started_at timestamptz, features jsonb);
CREATE TABLE public.broker_summary_date_quality (trade_date date PRIMARY KEY, checked_at timestamptz NOT NULL);
CREATE FUNCTION public.stamp() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  INSERT INTO public.broker_summary_date_quality SELECT DISTINCT "Date", statement_timestamp() FROM changed_rows
  ON CONFLICT (trade_date) DO UPDATE SET checked_at = EXCLUDED.checked_at; RETURN NULL; END $$;
CREATE TRIGGER s_ins AFTER INSERT ON public."IDX_Broker_Summary" REFERENCING NEW TABLE AS changed_rows
  FOR EACH STATEMENT EXECUTE FUNCTION public.stamp();
CREATE TRIGGER s_upd AFTER UPDATE ON public."IDX_Broker_Summary" REFERENCING NEW TABLE AS changed_rows
  FOR EACH STATEMENT EXECUTE FUNCTION public.stamp();
CREATE TRIGGER s_del AFTER DELETE ON public."IDX_Broker_Summary" REFERENCING OLD TABLE AS changed_rows
  FOR EACH STATEMENT EXECUTE FUNCTION public.stamp();
CREATE TABLE public."IDX_Stock_Universe_History" ("Ticker" text, recorded_from timestamptz NOT NULL, recorded_to timestamptz);
INSERT INTO public."IDX_Stock_Universe_History" VALUES ('AAAA', now() - interval '30 days', NULL);
'''


@pytest.fixture()
def db():
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {base.SCRATCH}')
        admin.execute(f'CREATE DATABASE {base.SCRATCH}')
    url = psycopg.conninfo.make_conninfo(URL, dbname=base.SCRATCH)
    old = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = url
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(base.BASE)
        c.execute(base.MIGRATION.read_text())
        c.execute(EXTRA)
        yield c
    if old is None:
        os.environ.pop('DATABASE_URL', None)
    else:
        os.environ['DATABASE_URL'] = old
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {base.SCRATCH}')


def refreshed(c, plan_used='FULL', ago='0 seconds'):
    """Feature 05 and the INDEX table up to date, and a successful round recorded (the watermark)."""
    for (d,) in c.execute('SELECT DISTINCT "Date" FROM public."IDX_Broker_Summary"').fetchall():
        c.execute('SELECT public.refresh_feature_05(%s, %s)', (d, d + timedelta(days=1)))
    base.build_index(c)
    c.execute("""INSERT INTO public."Monitoring_Stockbit_Update" (mode, status, started_at, features)
                 VALUES ('APPLY', 'SUCCESS', now() - %s::interval, %s)""", (ago, json.dumps({'plan_used': plan_used})))


def both(c):
    cands, why = refresh.bounded_candidates(c)
    full = refresh.plan(c.execute(refresh.PER_DATE_FULL).fetchall())
    bounded = refresh.plan(c.execute(refresh.PER_DATE_BOUNDED, {'dates': cands}).fetchall()) if cands is not None else None
    return cands, why, full, bounded


def start(c):
    base.load(c, [base.row(D0, 'AAAA'), base.row(D1, 'AAAA'), base.row(D2, 'AAAA', buy=300)])
    refreshed(c)   # the round starts after these writes: they are older than the watermark


def test_no_watermark_means_full(db):
    base.load(db, [base.row(D1, 'AAAA')])
    cands, why, full, _ = both(db)
    assert cands is None and why == 'no earlier successful refresh' and full == ([D1], [D1])


def test_nothing_changed_is_empty_and_equal(db):
    start(db)
    cands, why, full, bounded = both(db)
    assert cands == [] and why is None and full == bounded == ([], [])


def test_new_date_old_date_upload_and_one_row_correction(db):
    start(db)
    d3 = date(2026, 9, 2)
    base.load(db, [base.row(d3, 'AAAA')])                                             # a new date
    base.load(db, [base.row(D0, 'AAAA', broker='ZZ')])                                 # a manual upload to an old date
    db.execute('UPDATE public."IDX_Broker_Summary" SET "Buy Value" = 999 WHERE "Date" = %s', (D1,))  # a correction
    cands, why, full, bounded = both(db)
    assert why is None and set(cands) == {D0, D1, d3}
    assert bounded == full == ([D0, D1, d3], [D0, D1, d3])


def test_a_deleted_date_is_seen(db):
    start(db)
    db.execute('DELETE FROM public."IDX_Broker_Summary" WHERE "Date" = %s', (D2,))
    cands, why = refresh.bounded_candidates(db)
    assert why is None and cands == [D2]
    with pytest.raises(refresh.RefreshFailed):   # Feature 05 holds a date the source lost: both plans stop
        refresh.plan(db.execute(refresh.PER_DATE_BOUNDED, {'dates': cands}).fetchall())
    with pytest.raises(refresh.RefreshFailed):
        refresh.plan(db.execute(refresh.PER_DATE_FULL).fetchall())


def test_universe_change_means_full(db):
    start(db)
    db.execute("""INSERT INTO public."IDX_Stock_Universe_History" VALUES ('CCCC', now(), NULL)""")
    cands, why, _, _ = both(db)
    assert cands is None and why == 'IDX_Stock_Universe changed since the last refresh'


def test_no_full_plan_for_seven_days_means_full(db):
    base.load(db, [base.row(D1, 'AAAA')])
    refreshed(db, plan_used='BOUNDED', ago='1 hour')
    db.execute("""UPDATE public."Monitoring_Stockbit_Update" SET features = '{"plan_used": "FULL"}' """)
    db.execute("""UPDATE public."Monitoring_Stockbit_Update" SET started_at = now() - interval '8 days' """)
    cands, why, _, _ = both(db)
    assert cands is None and why == 'no full plan in the last 7 days'


@pytest.mark.parametrize('mode', ['SHADOW', 'BOUNDED', 'FULL'])
def test_changed_dates_modes(db, mode, monkeypatch):
    start(db)
    base.load(db, [base.row(date(2026, 9, 2), 'AAAA')])
    monkeypatch.setenv('PLAN_MODE', mode)
    events = []
    dates = refresh.changed_dates(lambda e, **kw: events.append(kw))
    info = dict(refresh.PLAN_INFO)
    assert dates == [date(2026, 9, 2)] and refresh.INDEX_DUE == [date(2026, 9, 2)]
    if mode == 'SHADOW':
        assert info['plan_used'] == 'FULL' and info['plan_shadow_equal'] is True and info['plan_bounded_seconds'] is not None
    elif mode == 'BOUNDED':
        assert info['plan_used'] == 'BOUNDED' and info['plan_full_seconds'] is None
    else:
        assert info['plan_used'] == 'FULL' and info['plan_candidates'] is None


def test_bounded_error_falls_back_to_full(db, monkeypatch):
    start(db)
    db.execute('DROP TABLE public.broker_summary_date_quality CASCADE')
    db.execute('DROP TRIGGER s_ins ON public."IDX_Broker_Summary"')
    base.load(db, [base.row(date(2026, 9, 2), 'AAAA')])
    monkeypatch.setenv('PLAN_MODE', 'BOUNDED')
    dates = refresh.changed_dates(lambda e, **kw: None)
    assert dates == [date(2026, 9, 2)] and refresh.PLAN_INFO['plan_used'] == 'FULL'
    assert refresh.PLAN_INFO['plan_why_full'].startswith('bounded plan unavailable')
