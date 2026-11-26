"""EXEC-SECTOR-ANALYSIS S2: the Sector Analysis files (sector.py) and their place in a publisher run. No database: a fake
answers the module's statements from small tables (the Overview's fake for the statements the two share); the SQL ran
on a local PostgreSQL and was measured on dev (verification/sector_analysis/db/REHEARSAL.md, EXPLAIN.md)."""
from __future__ import annotations

import gzip
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import examples  # noqa: E402
import overview  # noqa: E402
import publisher as pub  # noqa: E402
import sector  # noqa: E402
from test_overview import LISTS, MARKET_DATES, SECTORS, OverviewConn, close_of  # noqa: E402
from test_publisher import BROKERS, PRICES, TODAY, UNIVERSE, FakeBucket, no_wait, offline  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[3]
STOCKS = [('AAAA', 'Alpha Bank', 'Financials', 'Banks'), ('BBBB', 'Beta Insurance', 'Financials', 'Insurance'),
          ('CCCC', 'Gamma Tel', 'Infrastructures', 'Telecom'), ('ZZZZ', 'Zed', 'Undefined', 'Undefined')]
TICKERS = [t for t, *_ in STOCKS]
SUSPENDED = {('CCCC', MARKET_DATES[-3])}         # no close, no Feature 04 row
GROUPS = [('MARKET', 'IHSG'), ('SECTOR', 'Financials'), ('SECTOR', 'Infrastructures'), ('INDUSTRY', 'Banks'),
          ('INDUSTRY', 'Insurance'), ('INDUSTRY', 'Telecom')]


def terminal_api_bucket():
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SectorConn(OverviewConn):
    """OverviewConn (the statements sector.py shares with overview.py) plus Feature 08, Feature 04's rows and the
    weights; the Overview's own family is switched off (tables False)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, tables=False, **kw)
        self.f08_tables, self.backfill_held, self.basis = True, False, 'adv20_value'
        self.no_f08 = set()                        # dates without Feature 08 rows (null in the series)
        self.weight_fn = 'w-1'

    # the fake market: closes, Feature 04 statuses and their history
    def has(self, t, d):
        return (t, d) not in SUSPENDED and d in self.dates

    def close(self, t, d):
        i = self.dates.index(d)
        return 100.0 + 10 * TICKERS.index(t) + i + self.ver.get(('price', d), 0)

    def status(self, t, d, k):
        """1/0 above EMA k, None without an EMA (CCCC has no EMA200 before the 8th date)."""
        i = self.dates.index(d)
        if t == 'AAAA':
            return 1
        if t == 'BBBB':
            return (i // 3) % 2 if k == 50 else 0
        if t == 'CCCC':
            return None if k == 200 and i < 8 else int(i % 5 != 0)
        return 0

    def ema(self, t, d, k):
        s = self.status(t, d, k)
        return None if s is None else self.close(t, d) * (0.9 if s else 1.1)

    def _rows(self, sql, params):
        s = sector
        if sql in (s.PROBE_SQL, s.FILLED_SQL, s.STOCKS_SQL, s.F08_SQL, s.DAY_SQL, s.WEIGHT_SQL, s.F04_HISTORY_SQL,
                   s.FP_F04_SQL, s.F08_FP_SQL, s.WEIGHT_FN_SQL, s.STAMP_SQL):
            self.asked.append((sql, params))
        if sql == s.PROBE_SQL:
            return [(self.f08_tables,)]
        if sql == s.LOCK_FREE_SQL:
            return [(not self.backfill_held,)]
        if sql == s.LOCK_RELEASE_SQL:
            return [(True,)]
        if sql == s.FILLED_SQL:
            return [(params[0] not in self.no_f08,)]
        if sql == s.STOCKS_SQL:
            return list(STOCKS)
        if sql == s.WEIGHT_FN_SQL:
            return [(self.weight_fn,)]
        if sql == s.STAMP_SQL:
            return [(self.dates[-1], self.dates[-1], self.dates[-1], 'stocks')]
        if sql == s.F08_FP_SQL:
            return [(json.dumps([sorted(self.no_f08), self.ver.get('f08', 0)]),)]
        if sql == s.FP_F04_SQL:
            return [(d, f'f04-{d}-{self.ver.get(("f04", d), 0)}') for d in params[0] if d in self.dates]
        if sql == s.F08_SQL:
            lo, hi = params
            out = []
            for i, d in enumerate(self.dates):
                if lo <= d <= hi and d not in self.no_f08:
                    for g, (kind, name) in enumerate(GROUPS):
                        out.append((d, kind, name, 10 + g, 9 + g, 4, 8 + g, 3, 5, 1, 4 + g, 100.0 + i + g / 10))
            return out
        if sql == s.DAY_SQL:
            d = params[0]
            if self.fail_day:
                raise RuntimeError('day read failed')
            return [(t, self.close(t, d), 1000.0 * (j + 1), self.close(t, d), self.ema(t, d, 50), self.ema(t, d, 200))
                    for j, t in enumerate(TICKERS) if self.has(t, d)]
        if sql == s.WEIGHT_SQL:
            return [('AAAA', 1.5e12, self.basis), ('BBBB', 2.0e11, self.basis), ('CCCC', 5.0e10, self.basis)]
        if sql == s.F04_HISTORY_SQL:
            tickers, d = params
            out = []
            for t in tickers:
                own = [x for x in self.dates if x <= d and self.has(t, x)][::-1][:s.STATUS_CAP + 1]
                for x in own:
                    a50, a200 = self.status(t, x, 50), self.status(t, x, 200)
                    out.append((t, x, None if a50 is None else bool(a50), None if a200 is None else bool(a200)))
            return out
        if sql == overview.STOCK_CLOSES_SQL:
            self.asked.append((sql, params))
            return [(t, d, self.close(t, d)) for d in params[0] if d in self.dates for t in TICKERS if self.has(t, d)]
        if sql == overview.TICKER_CLOSES_SQL:
            self.asked.append((sql, params))
            return [(t, d, self.close(t, d)) for t in params[0] for d in self.dates if params[1] <= d <= params[2] and self.has(t, d)]
        return super()._rows(sql, params)

    def reference_days(self, t, d, k):
        """Sessions in the status on d counted back by hand over the stock's own rows (an implementation separate from
        sector.py), capped: (days, since)."""
        s = self.status(t, d, k)
        if s is None or not self.has(t, d):
            return None, None
        own = [x for x in self.dates if x <= d and self.has(t, x)][::-1]
        n, since = 0, None
        for x in own:
            if self.status(t, x, k) != s:
                break
            n, since = n + 1, x
            if n == sector.STATUS_CAP:
                return n, None
        return n, since


@pytest.fixture
def small(monkeypatch):
    """5 picker dates, 10 series dates, a cap of 6 sessions in status, 2 stocks per history statement."""
    monkeypatch.setattr(sector, 'DAY_DATES', 5)
    monkeypatch.setattr(sector, 'SERIES_SESSIONS', 10)
    monkeypatch.setattr(sector, 'STATUS_CAP', 6)
    monkeypatch.setattr(sector, 'HISTORY_TICKERS', 2)
    monkeypatch.setattr(sector, 'F04_HISTORY_SQL', sector.F04_HISTORY_SQL.replace('LIMIT 301', 'LIMIT 7'))


def run(mode='backfill', conn=None, bucket=None):
    conn = conn or SectorConn(PRICES, BROKERS, UNIVERSE)
    conn.stock_lists = LISTS
    bucket = bucket or FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run(mode)
    return p, conn, bucket


def doc(bucket, entry):
    return json.loads(gzip.decompress(bucket.objects[entry['key'][3:]]))


def files_of(bucket):
    index = bucket.get_json('state.json')['sector']
    return index, {n: doc(bucket, e) for n, e in index.items()}


def test_every_file_is_named_content_keyed_and_indexed_as_terminal_api_reads_it(small):
    _, _, bucket = run()
    state = bucket.get_json('state.json')
    index = state['sector']
    days = [f'sector-day-{d}' for d in MARKET_DATES[-5:]]
    assert sorted(index) == sorted(['sector-meta', 'sector-series', 'sector-stocks-idxfinance', 'sector-stocks-idxinfra', *days])
    reader = terminal_api_bucket()
    for name, e in index.items():
        assert sector.NAME.fullmatch(name) and reader.XSECTION_NAME.fullmatch(name), name    # lowercase, <= 32
        assert re.fullmatch(rf'v1/sector/{name}\.{e["sha256"][:16]}\.json\.gz', e['key'])
    assert reader.page_index(index, 'sector') == index == pub.sector_entries(index)
    assert 'sector' in reader.PAGE_FAMILIES and tuple(pub.PAGES) == reader.PAGE_FAMILIES
    assert not {'sector', 'sector_carry', 'sector_stamp'} & set(reader.STATE_FIELDS)
    carry = state['sector_carry']
    assert carry['code'] == sector.CODE and carry['weight_fn'] == 'w-1' and sorted(carry['days']) == MARKET_DATES[-5:]
    assert state['sector_stamp'][-1] == sector.CODE


def test_an_uppercase_stock_file_name_would_be_dropped_by_terminal_api():
    """The coordinator's amendment (CONTRACT 3.4): sector-stocks-<index ticker lowercased>."""
    reader = terminal_api_bucket()
    for t, _ in SECTORS + [('IDXPROPERT', 'Properties & Real Estate'), ('IDXTRANS', 'Transportation & Logistic')]:
        assert reader.XSECTION_NAME.fullmatch(sector.stocks_name(t)) and sector.stocks_name(t) == f'sector-stocks-{t.lower()}'
        assert not reader.XSECTION_NAME.fullmatch(f'sector-stocks-{t}')


def test_meta_names_the_weight_basis_the_sectors_industries_and_stocks(small):
    _, _, bucket = run()
    _, f = files_of(bucket)
    meta = f['sector-meta']
    assert meta['schema'] == 1 and meta['market'] == 'IHSG' and meta['benchmarks'] == ['IHSG', 'LQ45']
    assert meta['weight_basis'] == 'adv20_value' and meta['weight_label'] == '20-day average traded value'
    assert meta['periods'] == {'1D': 1, '3D': 3, '1W': 5, '2W': 10, '1M': 20, '3M': 60, '6M': 120, '1Y': 252}
    assert meta['sectors'] == [{'name': 'Financials', 'short': 'Financials', 'index': 'IDXFINANCE'},
                               {'name': 'Infrastructures', 'short': 'Infra', 'index': 'IDXINFRA'}]
    assert meta['industries'] == [{'name': 'Banks', 'sector': 'Financials'}, {'name': 'Insurance', 'sector': 'Financials'},
                                  {'name': 'Telecom', 'sector': 'Infrastructures'}]
    assert meta['stocks'] == {'ticker': TICKERS, 'name': [n for _, n, _, _ in STOCKS],
                              'sector': ['Financials', 'Financials', 'Infrastructures', 'Other'],
                              'industry': ['Banks', 'Insurance', 'Telecom', None]}
    assert meta['dates'] == MARKET_DATES[-5:] and meta['prices_through'] == MARKET_DATES[-1]
    assert meta['breadth_through'] == MARKET_DATES[-1]


@pytest.mark.parametrize('basis,label', [('market_cap', 'market capitalisation'), ('free_float', 'free_float')])
def test_the_weight_basis_is_pluggable_and_the_label_follows_it(small, basis, label):
    conn = SectorConn(PRICES, BROKERS, UNIVERSE)
    conn.basis = basis
    _, _, bucket = run(conn=conn)
    meta = files_of(bucket)[1]['sector-meta']
    assert meta['weight_basis'] == basis and meta['weight_label'] == label


def test_series_holds_the_closes_the_breadth_and_the_industry_levels(small):
    conn = SectorConn(PRICES, BROKERS, UNIVERSE)
    conn.no_f08 = {MARKET_DATES[-2]}                   # Feature 08 not refreshed for that date yet
    _, _, bucket = run(conn=conn)
    s = files_of(bucket)[1]['sector-series']
    dates = MARKET_DATES[-10:]
    assert s['dates'] == dates
    assert s['index']['IHSG'] == [close_of('IHSG', i) for i in range(10, 20)] and len(s['index']['LQ45']) == 10
    assert list(s['sector']) == ['Financials', 'Infrastructures'] and s['sector']['Financials'][0] == close_of('IDXFINANCE', 10)
    assert list(s['breadth']) == ['IHSG', 'Financials', 'Infrastructures']
    b = s['breadth']['Financials']
    assert set(b) == {'members', 'n50', 'a50', 'n200', 'a200', 'adv', 'unch', 'dec'}
    assert b['members'][-1] == 11 and b['n50'][-1] == 10 and b['a50'][-1] == 4 and b['dec'][-1] == 5
    assert all(v[-2] is None for v in b.values())       # the date without a row is null, never another date's
    assert list(s['industry']) == ['Banks', 'Insurance', 'Telecom']
    assert s['industry']['Banks']['level'][-1] == round(100.0 + 19 + 0.3, 6) and s['industry']['Telecom']['members'][0] == 15


def test_a_day_file_holds_returns_weights_ema_distances_and_sessions_in_status(small):
    _, conn, bucket = run()
    f = files_of(bucket)[1]
    for d in MARKET_DATES[-5:]:
        day = f[f'sector-day-{d}']
        st = day['stocks']
        i = MARKET_DATES.index(d)
        held = [t for t in TICKERS if conn.has(t, d)]
        assert day['date'] == d and day['prior_date'] == MARKET_DATES[i - 1]
        assert st['i'] == [TICKERS.index(t) for t in held]          # aligned by meta.stocks
        for n, t in enumerate(held):
            c = conn.close(t, d)
            assert st['close'][n] == round(c, 2) and st['volume'][n] == 1000.0 * (TICKERS.index(t) + 1)
            for key, k in sector.RETURNS:
                base = MARKET_DATES[i - k] if i - k >= 10 else None    # 10 series dates in the fixture
                want = None if base is None or not conn.has(t, base) else round((c / conn.close(t, base) - 1) * 100, 4)
                assert st[key][n] == want, (d, t, key)
            for k in (50, 200):
                s = conn.status(t, d, k)
                assert st[f'above_ema{k}'][n] == s
                assert st[f'd_ema{k}'][n] == (None if s is None else round((c / conn.ema(t, d, k) - 1) * 100, 4))
                assert (st[f'days{k}'][n], st[f'since{k}'][n]) == conn.reference_days(t, d, k), (d, t, k)
        assert st['weight'][:2] == [1.5e12, 2.0e11]
        assert st['weight'][held.index('ZZZZ')] is None                # no weight: null
    newest = f[f'sector-day-{MARKET_DATES[-1]}']['stocks']
    assert newest['days50'][0] == 6 and newest['since50'][0] is None     # AAAA: always above, at the cap ("300+")


def test_a_new_date_builds_one_day_and_reads_only_the_new_rows(small):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['sector']
    conn.dates.append('2026-10-29')
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['sector']
    built = [p[0] for s, p in conn.asked if s == sector.DAY_SQL]
    assert built == ['2026-10-29']
    assert 'sector-day-2026-10-29' in now and f'sector-day-{MARKET_DATES[-5]}' not in now
    for d in MARKET_DATES[-4:]:
        assert now[f'sector-day-{d}'] == first[f'sector-day-{d}']
    # closes: carried from the previous sector-stocks files; the recheck window's dates read again, the Other stock
    # (no sector file holds it) read by ticker
    closes = [p[0] for s, p in conn.asked if s == overview.STOCK_CLOSES_SQL]
    assert sorted(sum(closes, [])) == sorted(['2026-10-27', '2026-10-28', '2026-10-29'])
    assert [p[0] for s, p in conn.asked if s == overview.TICKER_CLOSES_SQL] == [['ZZZZ']]
    # the sessions in status: one more session on the previous day file; CCCC was suspended two sessions before the new
    # date, so only the stocks missing from yesterday's file are counted back (none here)
    assert [p for s, p in conn.asked if s == sector.F04_HISTORY_SQL] == []
    day = doc(bucket, now['sector-day-2026-10-29'])['stocks']
    for n, i in enumerate(day['i']):
        t = TICKERS[i]
        for k in (50, 200):
            assert (day[f'days{k}'][n], day[f'since{k}'][n]) == conn.reference_days(t, '2026-10-29', k), (t, k)


def test_a_stock_missing_from_the_previous_day_is_counted_back_from_its_own_rows(small):
    _, conn, bucket = run()
    # the newest day file was built on yesterday's: CCCC (suspended on MARKET_DATES[-3]) is counted back on the date after
    history = [p for s, p in sector_asks(conn, sector.F04_HISTORY_SQL)]
    assert (['CCCC'], MARKET_DATES[-2]) in history
    st = files_of(bucket)[1][f'sector-day-{MARKET_DATES[-2]}']['stocks']
    n = st['i'].index(TICKERS.index('CCCC'))
    assert (st['days50'][n], st['since50'][n]) == conn.reference_days('CCCC', MARKET_DATES[-2], 50)


def sector_asks(conn, sql):
    return [(s, p) for s, p in conn.asked if s == sql]


def test_the_first_run_counts_every_stock_back_once_in_bounded_statements(small):
    _, conn, _ = run()
    oldest = [p for s, p in sector_asks(conn, sector.F04_HISTORY_SQL) if p[1] == MARKET_DATES[-5]]
    assert [p[0] for p in oldest] == [TICKERS[:2], TICKERS[2:]]          # HISTORY_TICKERS per statement


def test_an_unchanged_stamp_writes_nothing(small, capsys):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['sector']
    n = len(bucket.puts)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert bucket.get_json('state.json')['sector'] == first
    assert not [k for k in bucket.puts[n:] if k.startswith('sector/')]
    assert '"event": "sector", "built": false, "reason": "unchanged"' in capsys.readouterr().out


def test_a_rewritten_feature_04_row_in_the_window_rebuilds_that_day_and_the_later_ones(small):
    _, conn, bucket = run()
    conn.ver[('f04', MARKET_DATES[-2])] = 1
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert [p[0] for s, p in conn.asked if s == sector.DAY_SQL] == MARKET_DATES[-2:]


def test_feature_08_changes_republish_the_series_and_a_new_weight_basis_rebuilds_every_day(small):
    _, conn, bucket = run()
    conn.ver['f08'] = 1
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert sector_asks(conn, sector.F08_SQL) and not sector_asks(conn, sector.DAY_SQL)
    conn.weight_fn = 'w-2'
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert len(sector_asks(conn, sector.DAY_SQL)) == 5


def test_the_manual_mode_rebuilds_everything_from_the_database(small):
    _, conn, bucket = run()
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('sector')
    assert len(sector_asks(conn, sector.DAY_SQL)) == 5
    closes = [p[0] for s, p in conn.asked if s == overview.STOCK_CLOSES_SQL]
    assert sorted(sum(closes, [])) == MARKET_DATES[-10:]                  # every series date read again
    counted = [p for _, p in sector_asks(conn, sector.F04_HISTORY_SQL)]
    assert [p[0] for p in counted if p[1] == MARKET_DATES[-5]] == [TICKERS[:2], TICKERS[2:]]   # no previous file read


@pytest.mark.parametrize('why', ['backfill', 'not filled'])
def test_never_half_filled_feature_08(small, capsys, why):
    conn = SectorConn(PRICES, BROKERS, UNIVERSE)
    if why == 'backfill':
        conn.backfill_held = True
    else:
        conn.no_f08 = {MARKET_DATES[-10]}               # the first series date has no row: the backfill has not run
    _, _, bucket = run(conn=conn)
    assert bucket.get_json('state.json')['sector'] == {}
    out = capsys.readouterr().out
    assert ('the Feature 08 backfill is running' if why == 'backfill' else 'run the backfill') in out


def test_without_feature_08_there_is_no_sector_analysis(small):
    conn = SectorConn(PRICES, BROKERS, UNIVERSE)
    conn.f08_tables = False
    p, _, bucket = run(conn=conn)
    assert bucket.get_json('state.json')['sector'] == {} and p.sector_failed is None


def test_a_failed_build_keeps_the_published_files(small):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['sector']
    conn.dates.append('2026-10-29')
    conn.fail_day = True
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    assert p.sector_failed == 'build' and bucket.get_json('state.json')['sector'] == first
    assert 'sector' in pub.partial_files(p)


def test_the_sector_stock_files_hold_every_members_closes_by_date(small):
    _, conn, bucket = run()
    f = files_of(bucket)[1]
    fin = f['sector-stocks-idxfinance']
    assert fin['schema'] == 1 and fin['sector'] == 'Financials' and fin['ticker'] == ['AAAA', 'BBBB']
    assert fin['dates'] == MARKET_DATES[-10:] and fin['close'][0] == [round(conn.close('AAAA', d), 2) for d in MARKET_DATES[-10:]]
    infra = f['sector-stocks-idxinfra']
    assert infra['ticker'] == ['CCCC'] and infra['close'][0][MARKET_DATES[-10:].index(MARKET_DATES[-3])] is None


def test_equal_tables_give_equal_bytes(small):
    _, _, a = run()
    _, _, b = run()
    assert {n: e['sha256'] for n, e in a.get_json('state.json')['sector'].items()} == \
           {n: e['sha256'] for n, e in b.get_json('state.json')['sector'].items()}


def test_the_short_names_are_the_overview_pages():
    model = (ROOT / 'apps/edge-bff/overview/src/model.ts').read_text()
    body = re.search(r'export const SHORT[^=]*= \{(.*?)\};', model, re.S).group(1)
    assert dict(re.findall(r"'([^']+)': '([^']+)'", body)) == sector.SHORT


def test_the_example_is_the_latest_publication_trimmed_by_edge_bff_as_the_overviews():
    """CONTRACT 3.5: the example of one market date is made as the Overview's (edge-bff trims the live publication, S3),
    so the publisher's example builders hold none; the names it would serve pass the example store's rules."""
    assert 'sector' not in examples.BUILDERS and 'overview' not in examples.BUILDERS
    assert 'Sector Analysis' in examples.__doc__
    for name in ('sector-meta', 'sector-series', f'sector-day-{MARKET_DATES[-1]}'):
        assert examples.NAME.fullmatch(name) and name.startswith('sector-')


def test_the_page_documents_name_the_same_periods_as_the_overview_page():
    model = (ROOT / 'apps/edge-bff/overview/src/model.ts').read_text()
    assert re.search(r'export const YEAR = (\d+);', model).group(1) == str(sector.PERIODS['1Y'])
    assert sector.DAY_DATES == overview.DAY_DATES and sector.SERIES_SESSIONS == overview.SERIES_SESSIONS
