"""EXEC-MU-ACCOUNTS 3e, the example mode (examples.py; ERRORS M527): the files of a page's opening view on one past date,
and the check that none names a later date. No database: the Radar fake of test_radar.py with a later result date."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import examples  # noqa: E402
import radar  # noqa: E402
from test_publisher import BROKERS, PRICES, UNIVERSE  # noqa: E402
from test_radar import DATES, LATER, LISTS, NAMES, LaterConn, built  # noqa: E402

AS_OF = DATES[-1]


def conn(**kw):
    return LaterConn(PRICES, BROKERS, UNIVERSE, **kw)


def opening_view(meta, days, board):
    """What the Radar page draws when it opens (apps/edge-bff/radar/src app.ts renderRadar, drawKanban; model.ts columns,
    lists, counts, stockFacts): per column, its default variant's hits at the Standard level and the Broad gate in their
    sort order with each card's figures, and 20 sessions of that setting's counts; the gate cuts and the data dates."""
    date = days['boards'][-1]
    i = days['dates'].index(date)
    shown = examples.radar_shown_filters(meta)
    r, st = board['rows'], board['stocks']
    at = {t: k for k, t in enumerate(st['ticker'])}
    view = {}
    for f in sorted(shown):
        hits = [k for k in range(len(r['filter'])) if r['filter'][k] == f and r['level'][k] == 'standard'
                and r['gate'][k] == 'broad' and r['status'][k] == 'hit']
        cards = []
        for k in hits:
            t = st['ticker'][r['stock'][k]]
            cards.append((t, r['run_day'][k], r['strong'][k], r['flag'][k], r['sort_value'][k], st['close'][at[t]],
                          st['chg_1d'][at[t]], st['spark'][at[t]], meta['names'].get(t)))
        counts = (days['counts'].get(f) or {}).get('standard/broad') or []
        view[f] = (sorted(cards, key=lambda c: (-(c[4] if c[4] is not None else float('-inf')), c[0])),
                   counts[max(0, i - 19):i + 1])
    gate = {k: v[i] for k, v in days['gate'].items()}
    return view, gate, days['prices_through'], days['broker_through'], date, [(f['id'], f['column'], f['name']) for f in meta['filters']]


def test_the_radar_example_is_the_opening_view_of_its_date_as_the_tables_stood_then():
    files = examples.radar_files(conn(), NAMES, LISTS, AS_OF)
    assert [f[0] for f in files] == ['radar-meta', 'radar-days', f'radar-board-{AS_OF}']   # what boot() reads
    cut = built(conn(through=AS_OF))
    got = {n: doc for n, doc, *_ in files}
    whole = (cut['radar-meta'][0], cut['radar-days'][0], cut[f'radar-board-{AS_OF}'][0])
    stored = (got['radar-meta'], got['radar-days'], got[f'radar-board-{AS_OF}'])
    # the page opens on the same view from the stored files as from the publication cut at the date
    assert opening_view(*stored) == opening_view(*whole) and stored[1]['boards'] == [AS_OF]
    # and the files hold nothing else (examples.radar_opening): S1's stock that left on the date is not in the board
    assert stored[2]['rows']['status'] == ['hit'] and 'left' in whole[2]['rows']['status']
    assert stored[0]['rules'] == [] and stored[0]['lists'] == [] and set(stored[0]['names']) == set(stored[2]['stocks']['ticker'])


def test_the_radar_files_keep_only_the_boards_opening_view():
    """The example-mode re-check (ERRORS M527): the board's near misses, left stocks, other levels and gates, a column's
    other variant and the measures are behind a click (the filter page, a segment): none of them is stored, nor the
    counts of another setting, the older days, the IHSG line, the other boards or the rules. Red without radar_opening."""
    filters = [{'id': 'S1', 'position': 1, 'column': 'S1', 'column_label': 'S1', 'variant': None, 'default_variant': True,
                'name': 'n1', 'question': 'q', 'warning': 'w', 'sort_label': 's', 'own_levels': False},
               {'id': 'S6A', 'position': 6, 'column': 'S6', 'column_label': 'S6', 'variant': 'a', 'default_variant': True,
                'name': 'n6a', 'question': 'q', 'warning': 'w', 'sort_label': 's', 'own_levels': False},
               {'id': 'S6B', 'position': 7, 'column': 'S6', 'column_label': 'S6', 'variant': 'b', 'default_variant': False,
                'name': 'n6b', 'question': 'q', 'warning': 'w', 'sort_label': 's', 'own_levels': False}]
    dates = [f'2026-10-{d:02d}' for d in range(1, 31)]
    as_of = dates[-1]
    rows = [  # (filter, ticker, level, gate, status)
        ('S1', 'HIT1', 'standard', 'broad', 'hit'), ('S1', 'NEAR', 'standard', 'broad', 'near'),
        ('S1', 'LEFT', 'standard', 'broad', 'left'), ('S1', 'LOOS', 'loose', 'broad', 'hit'),
        ('S1', 'LIQD', 'standard', 'liquid', 'hit'), ('S6A', 'HIT6', 'standard', 'broad', 'hit'),
        ('S6B', 'VARB', 'standard', 'broad', 'hit')]
    tickers = sorted({t for _, t, *_ in rows})
    board = {'schema': 1, 'date': as_of,
             'stocks': {'ticker': tickers, 'close': [100.0] * len(tickers), 'chg_1d': [1.0] * len(tickers),
                        'spark': [[1.0, 2.0]] * len(tickers)},
             'rows': {'filter': [r[0] for r in rows], 'stock': [tickers.index(r[1]) for r in rows],
                      'level': [r[2] for r in rows], 'gate': [r[3] for r in rows], 'status': [r[4] for r in rows],
                      'met': [3] * len(rows), 'cond_n': [2] * len(rows), 'run_day': [1] * len(rows),
                      'left_reason': ['B' if r[4] == 'left' else None for r in rows], 'strong': [None] * len(rows),
                      'sort_value': [float(k) for k in range(len(rows))], 'flag': [None] * len(rows)},
             'measures': {'columns': list(radar.MEASURES), 'values': [[1.0] * len(radar.MEASURES)] * len(tickers)}}
    settings = [f'{lv}/{g}' for lv in radar.LEVELS for g in radar.GATES]
    days = {'schema': 1, 'dates': dates, 'gate': {'broad_cut': [1e9] * 30, 'liquid_cut': [2e9] * 30, 'universe_n': [900] * 30,
                                                    'broad_n': [450] * 30, 'liquid_n': [180] * 30},
            'counts': {f: {s_: list(range(30)) for s_ in settings} for f in ('S1', 'S6A', 'S6B')},
            'ihsg': [7000.0] * 30, 'broker_through': as_of, 'prices_through': as_of, 'boards': dates[-3:]}
    meta = {'schema': 1, 'levels': list(radar.LEVELS), 'gates': list(radar.GATES), 'filters': filters,
            'rules': [{'filter': 'S1', 'cond': 'A', 'level': 'standard', 'label': 'x', 'threshold': 1.0, 'threshold2': None,
                       'status': 'decided'}],
            'names': {t: f'Company {t}' for t in tickers}, 'lists': [{'key': 'k', 'kind': 'INDEX', 'code': 'C', 'name': 'C', 'members': tickers}]}
    m, d, b = examples.radar_opening(meta, days, board, as_of)
    assert sorted(b['stocks']['ticker']) == ['HIT1', 'HIT6'] and set(b['rows']['status']) == {'hit'}
    assert set(b['rows']['level']) == {'standard'} and set(b['rows']['gate']) == {'broad'} and set(b['rows']['filter']) == {'S1', 'S6A'}
    assert b['measures'] == {'columns': [], 'values': [None, None]} and set(b['rows']['met']) == {None} and set(b['rows']['left_reason']) == {None}
    assert d['dates'] == dates[-20:] and d['boards'] == [as_of] and d['ihsg'] == [None] * 20
    assert d['counts'] == {'S1': {'standard/broad': list(range(10, 30))}, 'S6A': {'standard/broad': list(range(10, 30))}}
    assert all(len(v) == 20 for v in d['gate'].values())
    assert m['rules'] == [] and m['lists'] == [] and set(m['names']) == {'HIT1', 'HIT6'} and m['filters'] == filters
    for planted in ('NEAR', 'LEFT', 'LOOS', 'LIQD', 'VARB'):
        assert planted not in json.dumps([m, d, b]), planted
    assert opening_view(m, d, b) == opening_view(meta, days, board)          # the page draws the same opening view


def test_the_radar_examples_reference_data_holds_no_stock_listed_or_member_added_after_its_date():
    """The example-mode checker (ERRORS M527): the names and the stock lists are today's tables (the lists' history
    starts at their first capture), so a stock listed later and a list's later member would show in a file of a past
    date. radar-meta keeps the names of the board's stocks and no list; red without reference_cut."""
    names = {**NAMES, 'ZLATE': 'Listed after the date'}
    lists = [(k, kind, code, n, [*members, 'ZLATE']) for k, kind, code, n, members in LISTS]
    meta = dict((n, d) for n, d, *_ in examples.radar_files(conn(), names, lists, AS_OF))['radar-meta']
    assert 'ZLATE' not in json.dumps(meta) and meta['lists'] == []
    whole = dict((n, d) for n, d, *_ in radar.build(conn(through=AS_OF), names, lists, as_of=AS_OF))['radar-meta']
    assert 'ZLATE' in json.dumps(whole)                                           # the self-test: the build holds it


def test_the_rows_carry_the_bytes_the_page_reads_and_say_what_they_are():
    rows = examples.build(conn(), 'radar', AS_OF, NAMES, LISTS)
    for tab, name, as_of, n, size, sha, body in rows:
        assert (tab, as_of) == ('radar', AS_OF) and radar.NAME.fullmatch(name)
        assert size == len(body) and sha == hashlib.sha256(body).hexdigest()
        assert body == radar_bytes(name)                                   # the publisher's own encoding of the file
    board = dict((n, d) for n, d, *_ in examples.radar_files(conn(), NAMES, LISTS, AS_OF))[f'radar-board-{AS_OF}']
    assert [r[3] for r in rows][2] == len(board['rows']['filter']) == 1             # the one hit of the opening view


def radar_bytes(name):
    doc = dict((n, d) for n, d, *_ in examples.radar_files(conn(), NAMES, LISTS, AS_OF))[name]
    return gzip.compress(json.dumps(doc, separators=(',', ':'), allow_nan=False).encode(), compresslevel=9, mtime=0)


@pytest.mark.parametrize('as_of, refused', [
    ('2026-11-08', 'the newest Radar result date up to 2026-11-08 is 2026-11-06'),   # no result on the date itself
    ('2026-11-01', 'the Radar has no result date up to 2026-11-01'),
])
def test_a_date_without_its_own_result_stops_the_capture(as_of, refused):
    with pytest.raises(examples.ExampleError, match=refused):
        examples.build(conn(), 'radar', as_of, NAMES, LISTS)


def test_a_result_date_without_its_index_price_or_its_board_rows_stops_the_capture():
    c = conn()
    c.price_dates = [d for d in c.price_dates if d != AS_OF]               # IHSG has no final close on the date
    c.closes = {t: v[:len(c.price_dates)] for t, v in c.closes.items()}
    with pytest.raises(examples.ExampleError, match="IHSG's newest final price up to"):
        examples.build(c, 'radar', AS_OF, NAMES, LISTS)
    c = conn()
    c.results = [r for r in c.results if r[0] != AS_OF]                   # the gate row is there, no result row
    with pytest.raises(examples.ExampleError, match=f'radar-board-{AS_OF} has no row'):
        examples.build(c, 'radar', AS_OF, NAMES, LISTS)


def test_the_check_refuses_a_later_date_in_a_value_a_key_a_deep_list_the_name_or_the_day():
    ok = ('radar-days', {'dates': [AS_OF]}, 1, AS_OF)
    assert examples.stored('radar', [ok], AS_OF)
    for bad in (('radar-days', {'dates': [AS_OF, LATER]}, 1, AS_OF),
                ('radar-days', {'counts': {f'x/{LATER}': [1]}}, 1, AS_OF),
                ('radar-days', {'a': [[[{'b': f'up to {LATER}T00:00:00Z'}]]]}, 1, AS_OF),
                (f'radar-board-{LATER}', {'date': AS_OF}, 1, AS_OF),
                ('radar-days', {'dates': [AS_OF]}, 1, LATER)):
        with pytest.raises(examples.ExampleError, match=f'names dates after {AS_OF}'):
            examples.stored('radar', [bad], AS_OF)
    for bad in ([('overview-meta', {}, 0, AS_OF)], [ok, ok], [('Radar-days', {}, 0, AS_OF)]):
        with pytest.raises(examples.ExampleError, match='is not a file name of the radar example'):
            examples.stored('radar', bad, AS_OF)


def test_the_check_reads_a_document_of_any_depth_and_sees_a_build_without_the_cut():
    doc = [LATER]
    for _ in range(100_000):
        doc = [doc]
    assert examples.dates_after(doc, AS_OF) == [('$' + '[0]' * 100_001, LATER)]
    # the files of a build without as_of name the later date: the check refuses them (the self-test)
    plain = [(n, doc, rows, day) for n, (doc, rows, day) in built(conn()).items() if n == 'radar-days']
    with pytest.raises(examples.ExampleError, match=f'radar-days names dates after {AS_OF}'):
        examples.stored('radar', plain, AS_OF)


def test_only_a_tab_with_a_builder_is_captured():
    with pytest.raises(examples.ExampleError, match="no example builder for the tab 'monitor'"):
        examples.build(conn(), 'monitor', AS_OF, NAMES, LISTS)


# ---- the Watchlist: the LQ45 members on the date, the default indicators, no upcoming corporate actions ---------------
from test_watchlist import CutFake  # noqa: E402
import watchlist as W  # noqa: E402

WL_AS_OF = '2026-11-06'


class WatchlistConn:
    """A connection over test_watchlist's CutFake, with the LQ45 members recorded for each date."""

    def __init__(self, members=('BBBB', 'AAAA'), **kw):
        self.fake, self.members, self.asked = CutFake(broker='2026-11-12', radar='2026-11-12', **kw), list(members), []

    def execute(self, sql, params=()):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows
        if sql == examples.MEMBERS_SQL:
            self.asked.append(params)
            return Rows([(t, '2026-11-01', None) for t in sorted(self.members)])
        return Rows(self.fake.run(sql, params))


def test_the_watchlist_example_is_the_lists_stocks_on_the_date_with_the_default_indicators_only():
    conn = WatchlistConn()
    files = dict((n, d) for n, d, *_ in examples.watchlist_files(conn, NAMES, LISTS, WL_AS_OF))
    assert set(files) == {'watchlist-stocks', 'watchlist-lists'}
    assert conn.asked == [('INDEX', 'LQ45')]                                       # the list's recorded members
    s, full = files['watchlist-stocks'], W.build(CutFake(through=WL_AS_OF, broker='2026-11-12', radar='2026-11-12').run)['watchlist-stocks']
    assert s['ticker'] == ['AAAA', 'BBBB'] and s['prices_through'] == WL_AS_OF and max(s['dates']) == WL_AS_OF
    for k in full['values']:
        want = [full['values'][k][full['ticker'].index(t)] for t in s['ticker']]
        assert s['values'][k] == (want if k in full['default'] else [None, None]), k
    assert s['catalog'] == full['catalog'] and s['default'] == full['default']     # the menu shows what exists
    assert s['events'] == {} and s['events_loaded'] is None and full['events']    # upcoming actions left out
    lists = files['watchlist-lists']['lists']
    assert [(x['id'], x['name'], x['indicators'], [t['ticker'] for t in x['tickers']]) for x in lists] == \
        [(examples.EXAMPLE_LIST_ID, 'LQ45', None, ['AAAA', 'BBBB'])]
    rows = examples.build(conn, 'watchlist', WL_AS_OF, NAMES, LISTS)              # the date check passes
    assert [r[1] for r in rows] == ['watchlist-stocks', 'watchlist-lists']


def test_the_watchlist_example_stops_without_its_date_or_its_members():
    with pytest.raises(examples.ExampleError, match=r'no LQ45 member is recorded \(Stock_List_Member_History\)'):
        examples.watchlist_files(WatchlistConn(members=()), NAMES, LISTS, WL_AS_OF)
    with pytest.raises(examples.ExampleError, match=r'outside the universe of the file: \[.ZZZZ.\]'):
        examples.watchlist_files(WatchlistConn(members=('AAAA', 'ZZZZ')), NAMES, LISTS, WL_AS_OF)
    with pytest.raises(examples.ExampleError, match='2026-11-08 is not complete'):
        examples.watchlist_files(WatchlistConn(), NAMES, LISTS, '2026-11-08')          # no price on the date itself
    # a build that kept the upcoming actions names dates after the example's: the check refuses it (the self-test)
    s = W.build(CutFake(broker='2026-11-12', radar='2026-11-12').run, as_of=WL_AS_OF)['watchlist-stocks']
    with pytest.raises(examples.ExampleError, match=f'watchlist-stocks names dates after {WL_AS_OF}'):
        examples.stored('watchlist', [('watchlist-stocks', s, 2, WL_AS_OF)], WL_AS_OF)


def test_the_members_of_a_date_are_the_rows_covering_it_and_a_date_no_row_covers_stops_the_capture():
    rows = [('AAAA', '2026-11-10', None), ('BBBB', '2026-11-10', '2026-11-20'), ('CCCC', '2026-11-20', None)]
    assert examples.members_on(rows, '2026-11-12', 'LQ45') == (['AAAA', 'BBBB'], 'recorded for 2026-11-12')
    assert examples.members_on(rows, '2026-11-25', 'LQ45')[0] == ['AAAA', 'CCCC']
    # before the first capture no member is known, even when none changed since (the example-mode checker, ERRORS M527:
    # a review effective between the date and the first capture is not in the table)
    still = [('AAAA', '2026-11-10', None), ('BBBB', '2026-11-10', None)]
    for r in (still, rows):
        with pytest.raises(examples.ExampleError, match=r'no recorded LQ45 member covers 2026-10-30 \(its history starts on 2026-11-10\)'):
            examples.members_on(r, '2026-10-30', 'LQ45')
    with pytest.raises(examples.ExampleError, match='no recorded LQ45 member covers 2026-11-30'):
        examples.members_on([('AAAA', '2026-11-10', '2026-11-20')], '2026-11-30', 'LQ45')
    with pytest.raises(examples.ExampleError, match=r'no LQ45 member is recorded'):
        examples.members_on([], '2026-11-12', 'LQ45')


# ---- the Backtest: the page's own request, one run of the real worker, the period's prices -----------------------------
BT_AS_OF = '2026-10-30'
BT_DAYS = ['2026-10-27', '2026-10-28', '2026-10-29', BT_AS_OF]
BT_REQUEST = {'schema_version': 1, 'mode': 'single', 'single': {'ticker': 'MAPI', 'benchmark': 'buy_and_hold'},
              'period': {'from': BT_DAYS[0], 'to': BT_AS_OF, 'oos_fraction': 0.3},
              'entry': {'logic': 'all', 'window_bars': 5, 'conditions': [{'id': 'a1', 'enabled': True, 'kind': 'flow', 'type': 'fnet'}]},
              'exit': {'signals': {'logic': 'any', 'conditions': []}}}
BT_CATALOG = {'schema_version': 1, 'first_date': '2018-01-02', 'data_through': '2026-11-20',
              'tickers': [{'ticker': 'MAPI'}, {'ticker': 'BBCA'}, {'ticker': 'ZLATE'}],
              'groupings': [{'id': 'lq45', 'name': 'LQ45', 'members': ['BBCA', 'MAPI', 'ZLATE']}],
              'flow': {'available': True, 'reason': None, 'brokers': ['YU', 'ZZ'], 'data_through': '2026-11-09'},
              'flow_indicators': [{'id': 'FL01', 'access': 'all'}, {'id': 'FL18', 'access': 'admin'}, {'id': 'FL99', 'access': 'all'}],
              'limits': {}}
# the release file (apps/edge-bff/catalog/releases.json): FL99 unlisted, so lab
BT_RELEASES = {'items': [{'kind': 'flow_indicator', 'id': 'FL01', 'stage': 'released'},
                         {'kind': 'flow_indicator', 'id': 'FL18', 'stage': 'released'}]}


# the part of the cut catalog the request was built on (backtest_request.ts reads a catalog whose lists name only what the
# default setup names)
BT_BUILT_ON = {'schema_version': 1, 'first_date': BT_DAYS[0], 'data_through': BT_AS_OF, 'tickers': [{'ticker': 'MAPI'}],
               'groupings': [], 'flow': {'available': True, 'reason': None, 'brokers': ['YU'], 'data_through': BT_AS_OF},
               'limits': {}}


def bt_result(days=BT_DAYS, ticker='MAPI', tracks=True):
    return {'schema_version': 1, 'meta': {'mode': 'single', 'tickers': [ticker], 'data_through': '2026-11-20', 'duration_ms': 3},
            'dates': days, 'equity': [1.0] * len(days),
            'events': {'conditions': [{'condition_id': 'a1', 'ticker': ticker, 'track': {'on': [1], 'runs': [1, 2]}}] if tracks else [],
                       'exits': {}}}


class BacktestConn:
    def __init__(self, bars=BT_DAYS, moved=()):
        self.bars, self.moved, self.asked = list(bars), list(moved), []

    def execute(self, sql, params=()):
        self.asked.append((sql, params))
        rows = ([(d, 'STOCK_SPLIT') for d in self.moved] if sql == examples.BASIS_SQL
                else [(d, 100.0, 110.0, 90.0, 105.0, 1e6) for d in self.bars] if sql == examples.BARS_SQL else [])

        class Rows:
            def fetchall(self_inner):
                return rows
        return Rows()


def bt_build(conn=None, result=None, request=BT_REQUEST, as_of=BT_AS_OF, built_on=BT_BUILT_ON, releases=BT_RELEASES):
    asked = []

    def run(q):
        asked.append(q)
        return bt_result() if result is None else result
    rows = examples.build(conn or BacktestConn(), 'backtest', as_of, NAMES, LISTS, request=request, run=run, catalog=BT_CATALOG,
                          built_on=built_on, releases=releases)
    return {r[1]: json.loads(gzip.decompress(r[6])) for r in rows}, asked


def test_the_backtest_example_is_the_pages_request_its_run_the_period_and_the_catalog_cut_to_it():
    files, asked = bt_build()
    assert asked == [BT_REQUEST] and set(files) == {'backtest-catalog', 'backtest-request', 'backtest-result', 'backtest-bars-mapi'}
    assert files['backtest-request'] == BT_REQUEST
    # the result as the worker gave it, without the stamp of the publication the run read (a later date)
    assert files['backtest-result'] == {**bt_result(), 'meta': {k: v for k, v in bt_result()['meta'].items() if k != 'data_through'}}
    cat = files['backtest-catalog']
    assert (cat['first_date'], cat['data_through'], cat['flow']['data_through']) == (BT_DAYS[0], BT_AS_OF, BT_AS_OF)
    # its lists as the request names them (no later listing, no group: today's tables), the Flow indicators released
    # and every plan's (no admin-only version, no lab one)
    assert (cat['tickers'], cat['groupings'], cat['flow']['brokers']) == ([{'ticker': 'MAPI'}], [], ['YU'])
    assert [f['id'] for f in cat['flow_indicators']] == ['FL01'] and 'ZLATE' not in json.dumps(cat)
    assert {k: v for k, v in cat.items() if k not in ('tickers', 'groupings', 'flow', 'flow_indicators', 'first_date', 'data_through')} == \
        {k: v for k, v in BT_CATALOG.items() if k not in ('tickers', 'groupings', 'flow', 'flow_indicators', 'first_date', 'data_through')}
    bars = files['backtest-bars-mapi']
    assert bars['dates'] == BT_DAYS and bars['c'] == [105.0] * 4 and set(bars) == {'ticker', 'dates', 'o', 'h', 'l', 'c', 'v'}
    # any later date in a stored file is refused, the run stamp's place included (no exemption)
    late = bt_result()
    late['meta']['warnings'] = [{'code': 'X', 'message': 'published through 2026-11-20'}]
    with pytest.raises(examples.ExampleError, match=r'backtest-result names dates after 2026-10-30: \[.\$\.meta\.warnings'):
        bt_build(result=late)
    with pytest.raises(examples.ExampleError, match=r'backtest-result names dates after 2026-10-30: \[.\$\.meta\.data_through'):
        examples.stored('backtest', [('backtest-result', bt_result(), 4, BT_AS_OF)], BT_AS_OF)


@pytest.mark.parametrize('change, refused', [
    (dict(request={**BT_REQUEST, 'mode': 'portfolio'}), 'is not a single run ending on 2026-10-30'),
    (dict(request={**BT_REQUEST, 'period': {**BT_REQUEST['period'], 'to': '2026-10-29'}}), 'is not a single run ending on'),
    (dict(conn=BacktestConn(moved=['2026-11-12'])), r'MAPI changed its share basis on \[.2026-11-12 STOCK_SPLIT.\]'),
    (dict(result=bt_result(days=BT_DAYS[:-1])), r"the run's days are"),
    (dict(result=bt_result(ticker='BBCA')), 'is not a single run of MAPI'),
    (dict(result=bt_result(tracks=False)), 'the run has no condition track of MAPI'),
    (dict(conn=BacktestConn(bars=BT_DAYS[:-1])), 'MAPI has no final daily price on 2026-10-30'),
    # the request was built on another catalog than the worker's, cut to the period: the page would build another one
    (dict(built_on={**BT_BUILT_ON, 'data_through': '2026-10-29'}), r'does not hold at \$\.data_through'),
    (dict(built_on={**BT_BUILT_ON, 'limits': {'monte_carlo_runs': 500}}), r'does not hold at \$\.limits\.monte_carlo_runs'),
    (dict(built_on={**BT_BUILT_ON, 'tickers': [{'ticker': 'MAPI', 'type': 'stock'}]}), r'does not hold at \$\.tickers\[0\]'),
    (dict(built_on={**BT_BUILT_ON, 'flow': {**BT_BUILT_ON['flow'], 'brokers': ['QQ']}}), r'at \$\.flow\.brokers\[0\]'),
    (dict(built_on={**BT_BUILT_ON, 'flow': {**BT_BUILT_ON['flow'], 'data_through': '2026-11-09'}}), r'at \$\.flow\.data_through'),
    (dict(built_on={**BT_BUILT_ON, 'flow_indicators': [{'id': 'FL18', 'access': 'admin'}]}), r'at \$\.flow_indicators\[0\]'),
    # a lab Flow indicator (not released) is not in the stored catalog: the page would not build the request on it
    (dict(built_on={**BT_BUILT_ON, 'flow_indicators': [{'id': 'FL99', 'access': 'all'}]}), r'at \$\.flow_indicators\[0\]'),
])
def test_the_backtest_capture_stops_on_another_run_another_basis_or_a_missing_day(change, refused):
    with pytest.raises(examples.ExampleError, match=refused):
        bt_build(**change)
    with pytest.raises(examples.ExampleError, match="needs the page's request, the catalog it was built on, the worker"):
        examples.build(BacktestConn(), 'backtest', BT_AS_OF, NAMES, LISTS)
    with pytest.raises(examples.ExampleError, match='the catalog it was built on'):
        examples.build(BacktestConn(), 'backtest', BT_AS_OF, NAMES, LISTS, request=BT_REQUEST, run=bt_result, catalog=BT_CATALOG)
    with pytest.raises(examples.ExampleError, match='and the release file'):
        examples.build(BacktestConn(), 'backtest', BT_AS_OF, NAMES, LISTS, request=BT_REQUEST, run=bt_result, catalog=BT_CATALOG,
                       built_on=BT_BUILT_ON)


def test_a_catalog_part_is_found_in_the_whole_as_it_is():
    whole = {'n': 1, 'l': [{'t': 'MAPI', 'x': 2}, {'t': 'BBCA'}], 'f': {'b': ['YU', 'CC']}, 'on': True}
    assert examples.outside({'n': 1, 'l': [{'t': 'MAPI'}], 'f': {'b': ['CC']}, 'on': True}, whole) is None
    assert examples.outside({}, whole) is None and examples.outside({'l': []}, whole) is None
    assert [examples.outside(p, whole) for p in ({'n': 2}, {'m': 1}, {'l': [{'t': 'X'}]}, {'f': {'b': 'YU'}}, {'on': 1},
                                                 {'n': '1'}, {'l': {'t': 'MAPI'}})] == \
        ['$.n', '$.m', '$.l[0]', '$.f.b', '$.on', '$.n', '$.l']


# ---- the Screener: the worker's answer on its input cut at the date, its catalog as the live site shows it -------------
SC_AS_OF = '2026-10-30'
SP = examples.SCREENER_PRESET                                   # the example's preset (the user's choice)
SC_RELEASES = {'schema_version': 1, 'items': [
    {'kind': 'indicator', 'id': 'I01', 'stage': 'released'}, {'kind': 'indicator', 'id': 'I99', 'stage': 'lab'},
    {'kind': 'candle_pattern', 'id': 'breakout', 'stage': 'released'}, {'kind': 'candle_pattern', 'id': 'volspike', 'stage': 'released'},
    {'kind': 'flow_indicator', 'id': 'FL01', 'stage': 'released'}, {'kind': 'flow_indicator', 'id': 'FL18', 'stage': 'released'},
    {'kind': 'screener_metric', 'id': 'rs', 'stage': 'released'},
    {'kind': 'screener_preset', 'id': SP, 'stage': 'released'}, {'kind': 'screener_preset', 'id': 'labby', 'stage': 'lab'},
    {'kind': 'screener_preset', 'id': 'pit', 'stage': 'released'}, {'kind': 'screener_preset', 'id': 'old', 'stage': 'released'}]}
SC_DEF = {'universe': {'security_types': ['stock']}, 'conditions': [
    {'id': 'a', 'enabled': True, 'test': {'kind': 'event', 'signal': {'pattern': {'kind': 'pattern', 'type': 'breakout', 'params': {'length': 252}}}, 'within': 3}},
    {'id': 'b', 'enabled': True, 'test': {'kind': 'state', 'pattern': {'kind': 'pattern', 'type': 'volspike', 'params': {'length': 20, 'threshold': 1.5}}}}],
    'logic': 'all'}


def sc_catalog():
    data = {'evaluation_date': SC_AS_OF, 'published_at': SC_AS_OF, 'price_through': SC_AS_OF}
    return {'schema_version': 1, 'data': data,
            'indicators': [{'id': 'I01', 'name': 'SMA'}, {'id': 'I99', 'name': 'lab one'}],
            'metrics': [{'id': 'FL01', 'kind': 'flow', 'access': 'all'}, {'id': 'FL18', 'kind': 'flow', 'access': 'admin'}, {'id': 'rs'}],
            'fundamentals': [],
            'presets': [{'id': SP, 'name': 'The example preset', 'definition': SC_DEF, 'match_count': 3,
                         'items': [{'kind': 'candle_pattern', 'id': 'breakout'}, {'kind': 'candle_pattern', 'id': 'volspike'}]},
                        {'id': 'labby', 'name': 'lab', 'definition': SC_DEF, 'items': []},
                        {'id': 'pit', 'name': 'reads the point-in-time version', 'definition': {'conditions': [{'test': {'metric': {'kind': 'flow', 'metric': 'FL18'}}}]},
                         'items': [{'kind': 'flow_indicator', 'id': 'FL18'}]},
                        {'id': 'old', 'name': 'no items', 'definition': SC_DEF, 'match_count': 9, 'near_count': 2}]}


def sc_example(**over):
    run = {'schema_version': 1, 'mode': 'screen', 'data': {'evaluation_date': SC_AS_OF, 'published_at': SC_AS_OF},
           'rows': [{'ticker': 'AAAA', 'last_bar_date': SC_AS_OF, 'cells': [{'id': 'a', 'eval_date': SC_AS_OF, 'event_date': '2026-10-27'}]},
                    {'ticker': 'STAL', 'last_bar_date': '2026-10-28', 'cells': [{'id': 'a', 'eval_date': '2026-10-28'}]}],
           'match_count': 1}
    ex = {'catalog': sc_catalog(), 'universe': {'data': {'evaluation_date': SC_AS_OF}, 'rows': [['AAAA'], ['STAL']]},
          'screen': {'preset': SP, 'name': 'The example preset', 'definition': SC_DEF}, 'run': run}
    ex.update(over)
    return ex


def sc_build(example=None, releases=SC_RELEASES):
    rows = examples.build(None, 'screener', SC_AS_OF, NAMES, LISTS, example=example or sc_example(), releases=releases)
    return {r[1]: json.loads(gzip.decompress(r[6])) for r in rows}


def test_the_screener_example_is_the_workers_answer_and_its_catalog_as_the_live_site_shows_it():
    files = sc_build()
    assert set(files) == {'screener-catalog', 'screener-universe', 'screener-screen', 'screener-run'}
    cat = files['screener-catalog']
    assert [e['id'] for e in cat['indicators']] == ['I01']                    # a lab indicator left out
    assert [e['id'] for e in cat['metrics']] == ['FL01', 'rs']                 # the point-in-time version left out
    assert [p['id'] for p in cat['presets']] == [SP, 'old']               # a lab preset, one reading a left-out item
    assert cat['presets'][1]['match_count'] is None and cat['presets'][0]['match_count'] == 3   # no items: no counts
    assert files['screener-screen'] == {'preset': SP, 'name': 'The example preset', 'definition': SC_DEF}
    assert files['screener-run'] == sc_example()['run'] and files['screener-universe'] == sc_example()['universe']


@pytest.mark.parametrize('change, refused', [
    (dict(run={**sc_example()['run'], 'data': {'evaluation_date': '2026-10-29'}}), "run is evaluated on 2026-10-29"),
    (dict(universe={'data': {'evaluation_date': '2026-11-20'}, 'rows': []}), 'universe is evaluated on 2026-11-20'),
    (dict(run={**sc_example()['run'], 'rows': [{'ticker': 'LATE', 'last_bar_date': '2026-11-02', 'cells': []}]}), r"rows evaluated after 2026-10-30: \['LATE'\]"),
    (dict(run={**sc_example()['run'], 'rows': [{'ticker': 'CELL', 'last_bar_date': SC_AS_OF,
                                                'cells': [{'id': 'a', 'eval_date': SC_AS_OF, 'last_event_date': '2026-11-02'}]}]}),
     r"rows evaluated after 2026-10-30: \['CELL'\]"),
    # a row without the dates the check reads (a renamed field) is refused, never checked as nothing
    (dict(run={**sc_example()['run'], 'rows': [{'ticker': 'BARE', 'eval_date': SC_AS_OF}]}), r"carry no last_bar_date or cell eval_date: \['BARE'\]"),
    (dict(run={**sc_example()['run'], 'rows': [{'ticker': 'CEL2', 'last_bar_date': SC_AS_OF, 'cells': [{'id': 'a'}]}]}), r"\['CEL2'\]"),
    (dict(run={**sc_example()['run'], 'mode': 'universe_only'}), 'is not a screen: universe_only'),
    (dict(screen={'preset': SP, 'name': 'x', 'definition': {**SC_DEF, 'logic': 'any'}}), f'is not the preset {SP}'),
    (dict(screen={'preset': 'old', 'name': 'x', 'definition': SC_DEF}), f'is not the preset {SP}'),
])
def test_the_screener_capture_stops_on_another_date_preset_or_answer(change, refused):
    with pytest.raises(examples.ExampleError, match=refused):
        sc_build(sc_example(**change))


def test_the_screener_capture_stops_when_the_preset_is_not_shown_or_a_file_names_a_later_date():
    lab = {**SC_RELEASES, 'items': [i if i['id'] != SP else {**i, 'stage': 'lab'} for i in SC_RELEASES['items']]}
    with pytest.raises(examples.ExampleError, match=f'has no preset {SP}'):
        sc_build(releases=lab)
    late = sc_example()
    late['catalog']['stock_lists'] = {'availability': 'AVAILABLE', 'as_of': '2026-11-10', 'lists': []}
    with pytest.raises(examples.ExampleError, match=r'screener-catalog names dates after 2026-10-30'):
        sc_build(late)
    with pytest.raises(examples.ExampleError, match="needs the worker's answer"):
        examples.build(None, 'screener', SC_AS_OF, NAMES, LISTS)
