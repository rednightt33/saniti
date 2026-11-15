"""EXEC-OVERVIEW O2: the Market Overview files (overview.py) and their place in a publisher run. No database: a fake answers
the Overview's statements from small tables; the SQL itself ran on a local copy of dev and was measured on dev
(verification/overview/REHEARSAL.md)."""
from __future__ import annotations

import gzip
import json
import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import overview  # noqa: E402
import publisher as pub  # noqa: E402
from test_publisher import BROKERS, PRICES, TODAY, UNIVERSE, FakeBucket, FakeConn, no_wait, offline  # noqa: E402,F401

MARKET_DATES = [f'2026-10-{d:02d}' for d in (1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28)]
STOCKS = [('BBCA', 'Bank Central Asia', 'Financials'), ('TLKM', 'Telkom Indonesia', 'Infrastructures'),
          ('ZZZZ', 'Unknown Sector', 'Undefined')]
SECTORS = [('IDXFINANCE', 'Financials'), ('IDXINFRA', 'Infrastructures')]
LISTS = [('INDEX:550', 'INDEX', 'LQ45', 'IDX LQ45 Index', 'def', None, ['BBCA', 'TLKM'])]


def close_of(t, i):
    return {'IHSG': 7000 + 10 * i, 'LQ45': 900 + i, 'IDXFINANCE': 1400 + 2 * i, 'IDXINFRA': 1500 - i}[t]


class OverviewConn(FakeConn):
    """FakeConn plus the Overview's statements (overview.py), over MARKET_DATES; every statement is recorded."""

    def __init__(self, *a, tables=True, **kw):
        super().__init__(*a, **kw)
        self.ov_tables, self.dates, self.size_fn = tables, list(MARKET_DATES), 'size-fn-1'
        self.flow = [(d, 3.0e12 + i * 1e10, 2.9e12, 5.0e12) for i, d in enumerate(MARKET_DATES[:-2])]
        self.asked = []
        self.fail_day = False
        self.stocks = list(STOCKS)
        self.no_bars = set()            # sessions whose IHSG bars are not loaded yet (ERRORS M442)
        self.ver = {}                   # (source, date) -> a version: a rewritten row changes its fingerprint

    def _rows(self, sql, params):
        o = overview
        if sql in (o.PROBE_SQL, o.MARKET_SQL, o.DATES_SQL, o.STAMP_SQL, o.FEATURE_DATES_SQL, o.F04_DATES_SQL, o.SIZE_FN_SQL,
                   o.STOCKS_SQL, o.SECTORS_SQL, o.CLOSES_SQL, o.BREADTH_SQL, o.MARKET_FLOW_SQL, o.DAY_SQL, o.SIZE_SQL,
                   o.STOCK_FLOW_SQL, o.INTRADAY_SQL, o.FP_PRICE_SQL, o.FP_F01_SQL, o.FP_F04_SQL, o.FP_F06_SQL, o.FP_BARS_SQL):
            self.asked.append((sql, params))
        if sql == o.PROBE_SQL:
            return [(self.ov_tables,)]
        if sql == o.MARKET_SQL:
            return [('IHSG',)]
        if sql == o.DATES_SQL:
            return [(d,) for d in reversed(self.dates)][:params[1]]
        if sql == o.STAMP_SQL:
            return [(self.dates[-1], self.flow[-1][0], self.dates[-1], self.dates[-1], len(self.dates),
                     ','.join(f'{t}:{sec}' for t, _, sec in self.stocks), 'lists', self.size_fn)]   # as STAMP_SQL's md5
        if sql in (o.FEATURE_DATES_SQL, o.F04_DATES_SQL):
            return [(d,) for d in params[0] if d in self.dates]
        if sql == o.SIZE_FN_SQL:
            return [(self.size_fn,)]
        if sql == o.STOCKS_SQL:
            return list(self.stocks)
        v = lambda kind, d: f'{kind}-{d}-{self.ver.get((kind, d), 0)}'
        if sql in (o.FP_PRICE_SQL, o.FP_F01_SQL):
            kind = 'price' if sql == o.FP_PRICE_SQL else 'f01'
            return [(d, v(kind, d)) for d in params[0] if d in self.dates]
        if sql == o.FP_F04_SQL:
            return [(d, 800, 400 + i + self.ver.get(('f04', d), 0), 790, 300, v('f04', d))
                    for i, d in enumerate(self.dates) if d in params[0]]
        if sql == o.FP_F06_SQL:
            return [(b, v('f06', b)) for b in params[0]]
        if sql == o.FP_BARS_SQL:
            return [(d, tf, v('bars', d)) for d in params[1] if d in self.dates and d not in self.no_bars for tf in ('5m', '1h')]
        if sql == o.SECTORS_SQL:
            return list(SECTORS)
        if sql == o.CLOSES_SQL:
            tickers, lo, hi = params
            return [(t, d, close_of(t, i) - 1, close_of(t, i) + 5, close_of(t, i) - 5, close_of(t, i))
                    for t in tickers for i, d in enumerate(self.dates) if lo <= d <= hi]
        if sql == o.BREADTH_SQL:
            return [(d, 800, 400 + i + self.ver.get(('f04', d), 0), 790, 300) for i, d in enumerate(self.dates) if d in params[0]]
        if sql == o.MARKET_FLOW_SQL:
            return [r for r in self.flow if r[0] >= params[1]]
        if sql == o.DAY_SQL:
            if self.fail_day:
                raise RuntimeError('day read failed')
            return [('BBCA', 9000.0, 1.5, 2.0, 3.0, True, False), ('TLKM', 3000.0, -0.5, -1.0, 4.0, False, None),
                    ('ZZZZ', 50.0, 0.0, 0.0, 0.0, None, None)]
        if sql == o.SIZE_SQL:
            return [('BBCA', 1.6e12, 'adv20_value'), ('TLKM', 6.0e11, 'adv20_value')]
        if sql == o.STOCK_FLOW_SQL:
            return [('BBCA', 1e11, 3e11, 5e11, 9e11), ('TLKM', -2e10, -5e10, -1e11, -3e11)]
        if sql == o.INTRADAY_SQL:
            m, tf, lo, hi = params
            step = 300 if tf == '5m' else 3600
            return [(d, 1_700_000_000 + i * step, 7000.0 + i) for d in self.dates if lo <= d <= hi and d not in self.no_bars
                    for i in range(3)]
        return super()._rows(sql, params)

    def count(self, sql):
        return sum(1 for s, _ in self.asked if s == sql)


@pytest.fixture
def small(monkeypatch):
    """Short windows over the fake's 20 market dates (5 day files, 10 series dates, 5-session turnover base)."""
    monkeypatch.setattr(overview, 'DAY_DATES', 5)
    monkeypatch.setattr(overview, 'SERIES_SESSIONS', 10)
    monkeypatch.setattr(overview, 'TURNOVER_BASE', 5)
    monkeypatch.setattr(overview, 'FOREIGN_SUM', 3)
    monkeypatch.setattr(overview, 'FLOW_PERIODS', (('1D', 1), ('5D', 5)))


def run(mode='backfill', conn=None, bucket=None):
    conn = conn or OverviewConn(PRICES, BROKERS, UNIVERSE)
    conn.stock_lists = LISTS
    bucket = bucket or FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run(mode)
    return p, conn, bucket


def doc(bucket, entry):
    return json.loads(gzip.decompress(bucket.objects[entry['key'][3:]]))


def test_every_file_is_content_keyed_and_indexed_with_what_the_next_run_reuses(small):
    _, conn, bucket = run()
    state = bucket.get_json('state.json')
    index = state['overview']
    days = [f'overview-day-{d}' for d in MARKET_DATES[-5:]]
    assert sorted(index) == sorted(['overview-meta', 'overview-series', *days])
    for name, e in index.items():
        assert overview.NAME.fullmatch(name)
        assert re.fullmatch(rf'v1/overview/{name}\.{e["sha256"][:16]}\.json\.gz', e['key'])
    carry = state['overview_carry']
    assert carry['code'] == overview.CODE and carry['size_fn'] == 'size-fn-1'
    assert sorted(carry['breadth']) == MARKET_DATES[-10:]
    newest = carry['days'][MARKET_DATES[-1]]
    assert newest['base'][:2] == [MARKET_DATES[-3], True]                    # its broker date is two sessions older
    assert sorted(newest['win']) == sorted([*(f'price:{d}' for d in MARKET_DATES[-3:]), *(f'bars:{d}:{tf}' for d in MARKET_DATES[-3:]
                                                                                             for tf in ('5m', '1h')),
                                            f'f01:{MARKET_DATES[-1]}', f'f04:{MARKET_DATES[-1]}', f'f06:{MARKET_DATES[-3]}'])
    assert state['overview_stamp'][-1] == overview.CODE
    assert pub.overview_entries(index) == {n: {**e} for n, e in index.items()}


def test_the_files_hold_the_figures_of_the_formulas(small):
    _, conn, bucket = run()
    index = bucket.get_json('state.json')['overview']
    meta = doc(bucket, index['overview-meta'])
    assert meta['stocks']['sector'] == ['Financials', 'Infrastructures', 'Other']        # decision 5: Undefined -> Other
    assert [s['name'] for s in meta['sectors']] == ['Financials', 'Infrastructures', 'Other']
    assert meta['lists'][0]['code'] == 'LQ45' and meta['size_basis'] == 'adv20_value'
    assert meta['dates'] == MARKET_DATES[-5:] and meta['broker_through'] == MARKET_DATES[-3]
    series = doc(bucket, index['overview-series'])
    assert series['dates'] == MARKET_DATES[-10:]
    assert series['index']['IHSG'][-1] == close_of('IHSG', 19) and series['sector']['Infrastructures'][0] == close_of('IDXINFRA', 10)
    assert series['above_ema50'][-1] == round(100 * (400 + 19) / 800, 2) and series['above_ema200'][-1] == round(100 * 300 / 790, 2)
    day = doc(bucket, index[f'overview-day-{MARKET_DATES[-1]}'])
    assert day['prior_date'] == MARKET_DATES[-2]
    assert day['index']['IHSG'] == {'open': close_of('IHSG', 19) - 1, 'high': close_of('IHSG', 19) + 5,
                                    'low': close_of('IHSG', 19) - 5, 'close': close_of('IHSG', 19),
                                    'prior_close': close_of('IHSG', 18)}
    assert day['breadth'] == {'advancers': 1, 'decliners': 1, 'unchanged': 1}
    m = day['market']
    assert m['date'] == MARKET_DATES[-3]                                          # the newest broker date up to the day
    flow = conn.flow
    turnover = lambda r: r[1] + r[3]
    at = len(flow) - 1
    avg = sum(turnover(r) for r in flow[at - 5:at]) / 5
    assert m['turnover'] == round(turnover(flow[at])) and m['turnover_avg20'] == round(avg)
    assert m['turnover_ratio'] == round(turnover(flow[at]) / avg, 4)
    assert m['foreign_net_1d'] == round(flow[at][1] - flow[at][2])
    assert m['foreign_net_10d'] == round(sum(r[1] - r[2] for r in flow[at - 2:at + 1]))     # FOREIGN_SUM 3 here
    assert m['periods']['5D'] == {'buy': round(sum(r[1] for r in flow[at - 4:at + 1])),
                                  'sell': round(sum(r[2] for r in flow[at - 4:at + 1])),
                                  'net': round(sum(r[1] - r[2] for r in flow[at - 4:at + 1])), 'from': flow[at - 4][0]}
    s = day['stocks']
    assert s['i'] == [0, 1, 2] and s['size'] == [1.6e12, 6.0e11, None] and s['above_ema50'] == [1, 0, None]
    assert s['above_ema200'] == [0, None, None] and s['fnet_3m'] == [9e11, -3e11, None]
    assert day['intraday']['5m']['c'] == [7000.0, 7001.0, 7002.0] and len(day['intraday']['1h']['t']) == 15


def test_an_unchanged_stamp_writes_nothing_and_carries_the_index(small, capsys):
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['overview']
    n = len(bucket.puts)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert bucket.get_json('state.json')['overview'] == first
    assert not [k for k in bucket.puts[n:] if k.startswith('overview/')]
    assert '"reason": "unchanged"' in capsys.readouterr().out


def test_a_new_date_reads_and_writes_only_what_changed(small):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['overview']
    conn.dates.append('2026-10-29')                     # a new market date; the broker data stays at the 26th
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['overview']
    assert conn.count(overview.BREADTH_SQL) == 0          # the new date is in the recheck window: counted with its fingerprint
    series = doc(bucket, now['overview-series'])
    assert series['dates'][-1] == '2026-10-29' and series['above_ema50'][-1] == round(100 * (400 + 20) / 800, 2)
    assert conn.count(overview.DAY_SQL) == 1               # only the new day file is built
    assert 'overview-day-2026-10-29' in now and f'overview-day-{MARKET_DATES[-5]}' not in now   # the oldest leaves
    for d in MARKET_DATES[-4:]:
        assert now[f'overview-day-{d}'] == first[f'overview-day-{d}']                       # kept as they were


def test_a_newer_broker_date_rebuilds_the_day_files_that_now_read_it(small):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['overview']
    conn.flow.append((MARKET_DATES[-2], 3.5e12, 3.0e12, 5.5e12))
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['overview']
    built = sorted(p[0] for s, p in conn.asked if s == overview.DAY_SQL)
    assert built == MARKET_DATES[-2:]                      # the two days whose newest broker date moved
    assert conn.count(overview.BREADTH_SQL) == 0
    assert now[f'overview-day-{MARKET_DATES[-3]}'] == first[f'overview-day-{MARKET_DATES[-3]}']
    assert doc(bucket, now[f'overview-day-{MARKET_DATES[-1]}'])['market']['date'] == MARKET_DATES[-2]


def test_the_manual_mode_and_a_new_formula_count_and_build_everything_again(small, monkeypatch):
    _, conn, bucket = run()
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('overview')
    assert conn.count(overview.DAY_SQL) == 5 and [p for s, p in conn.asked if s == overview.BREADTH_SQL] == [(MARKET_DATES[-10:-3],)]
    monkeypatch.setattr(overview, 'CODE', 'another-formula')
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert conn.count(overview.DAY_SQL) == 5 and conn.count(overview.BREADTH_SQL) == 1
    conn.size_fn = 'size-fn-2'                             # decision 2: a new size source rebuilds every day file
    conn.asked.clear()
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert conn.count(overview.DAY_SQL) == 5


def test_a_failed_build_keeps_the_published_files_and_is_a_partial_publication(small):
    _, conn, bucket = run()
    first = bucket.get_json('state.json')['overview']
    conn.dates.append('2026-10-29')
    conn.fail_day = True
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    assert p.overview_failed == 'build' and bucket.get_json('state.json')['overview'] == first
    assert 'overview' in pub.partial_files(p)


def test_without_the_size_function_there_is_no_overview(small):
    conn = OverviewConn(PRICES, BROKERS, UNIVERSE, tables=False)
    p, _, bucket = run(conn=conn)
    assert bucket.get_json('state.json')['overview'] == {} and p.overview_failed is None


def test_volatility_is_feature_01s_formula_and_its_rank_counts_previous_values_below():
    closes = [100 * (1.01 if i % 2 else 0.99) ** i for i in range(25)]
    rets = [closes[k] / closes[k - 1] - 1 for k in range(5, 25)]
    mean = sum(rets) / 20
    want = math.sqrt(sum((r - mean) ** 2 for r in rets) / 19) * math.sqrt(252) * 100
    assert overview.volatility(closes, 24) == pytest.approx(want)
    assert overview.volatility(closes, 19) is None and overview.volatility(closes[:5] + [None] + closes[6:], 24) is None
    assert overview.below_rank(5.0, [1, 2, 5, 7]) == 50.0 and overview.below_rank(5.0, [1, None]) is None


def test_terminal_api_reads_every_page_index_as_written_and_serves_the_same_families(small):
    import importlib.util
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', root / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    assert tuple(pub.PAGES) == reader.PAGE_FAMILIES                              # one list of page families
    _, _, bucket = run()
    index = bucket.get_json('state.json')['overview']
    assert reader.page_index(index, 'overview') == index == pub.overview_entries(index)
    good = index['overview-meta']
    raw = {**index, 'overview-x': {**good}, 'overview-y': {**good, 'key': good['key'].replace('overview/', 'radar/')}}
    assert pub.overview_entries(raw) == reader.page_index(raw, 'overview') == index
    assert not {'overview', 'overview_carry', 'overview_stamp'} & set(reader.STATE_FIELDS)


def test_a_full_count_reads_feature_04_in_bounded_chunks_each_date_once(small, monkeypatch):
    """The publisher login's statement timeout is 120 s on dev; a first run's breadth count is split so no statement
    grows with the number of dates (BREADTH_CHUNK)."""
    monkeypatch.setattr(overview, 'BREADTH_CHUNK', 4)
    _, conn, bucket = run()
    chunks = [p[0] for s, p in conn.asked if s == overview.BREADTH_SQL]
    assert [len(c) for c in chunks] == [4, 3]                   # the 3 newest dates come with their fingerprints
    assert sum(chunks, []) == MARKET_DATES[-10:-3]
    series = doc(bucket, bucket.get_json('state.json')['overview']['overview-series'])
    assert all(v is not None for v in series['above_ema50'])


def built(conn):
    return sorted(p[0] for s, p in conn.asked if s == overview.DAY_SQL)


def test_late_intraday_bars_rebuild_the_day_that_had_none(small):
    """ERRORS M442: the publisher runs on the price signal (17:00 WIB), the IHSG bars load at 17:30 WIB."""
    conn = OverviewConn(PRICES, BROKERS, UNIVERSE)
    conn.no_bars = {MARKET_DATES[-1]}
    _, conn, bucket = run(conn=conn)
    first = bucket.get_json('state.json')['overview']
    assert doc(bucket, first[f'overview-day-{MARKET_DATES[-1]}'])['intraday']['5m'] == {'t': [], 'c': []}
    conn.no_bars, conn.asked = set(), []
    pub.Publisher(conn, bucket, today=TODAY).run('daily')                 # the stamp sees the bars: a run, not 'unchanged'
    now = bucket.get_json('state.json')['overview']
    assert built(conn) == [MARKET_DATES[-1]]
    assert len(doc(bucket, now[f'overview-day-{MARKET_DATES[-1]}'])['intraday']['5m']['c']) == 3


def test_a_feature_fill_or_rewrite_in_the_window_rebuilds_its_days_and_recounts_breadth(small):
    _, conn, bucket = run()
    conn.ver[('f01', MARKET_DATES[-1])] = 1                                  # the Feature 01 fill completed after the run
    conn.ver[('f04', MARKET_DATES[-2])] = 7                                  # 7 more stocks above EMA50 on the day before
    conn.asked = []
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['overview']
    assert built(conn) == MARKET_DATES[-2:]
    series = doc(bucket, now['overview-series'])
    assert series['above_ema50'][-2] == round(100 * (400 + 18 + 7) / 800, 2)
    assert conn.count(overview.BREADTH_SQL) == 0
    conn.ver[('price', MARKET_DATES[-3])] = 1                                # a price recovery of the oldest window date:
    conn.asked = []                                                          # every day that reads it (sizes, closes)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert built(conn) == MARKET_DATES[-3:]
    conn.ver[('f06', MARKET_DATES[-3])] = 1                                  # the broker round rewrote its date
    conn.asked = []
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert built(conn) == MARKET_DATES[-3:]                                  # the days whose broker date it is (22 and 23 Oct read their own)


def test_a_new_stock_rebuilds_every_day_file_so_positions_match_the_meta(small):
    """ERRORS M442 (review finding 1): day files hold positions in meta.stocks; a stock listed ahead of others moves them."""
    _, conn, bucket = run()
    conn.stocks = [('AAAA', 'New Listing', 'Financials'), *STOCKS]
    conn.asked = []
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['overview']
    assert built(conn) == MARKET_DATES[-5:]
    meta = doc(bucket, now['overview-meta'])
    for d in MARKET_DATES[-5:]:
        day = doc(bucket, now[f'overview-day-{d}'])
        assert [meta['stocks']['ticker'][i] for i in day['stocks']['i']] == ['BBCA', 'TLKM', 'ZZZZ']


def test_a_date_leaving_the_window_rebuilds_nothing(small):
    _, conn, bucket = run()
    conn.dates.append('2026-10-29')
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    conn.dates.append('2026-10-30')
    conn.asked = []
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert built(conn) == ['2026-10-30']
