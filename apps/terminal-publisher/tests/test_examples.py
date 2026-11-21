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


def test_the_radar_example_is_the_opening_view_of_its_date_as_the_tables_stood_then():
    files = examples.radar_files(conn(), NAMES, LISTS, AS_OF)
    assert [f[0] for f in files] == ['radar-meta', 'radar-days', f'radar-board-{AS_OF}']   # what boot() reads
    cut = built(conn(through=AS_OF))
    assert {n: (doc, rows, day) for n, doc, rows, day in files} == {n: cut[n] for n, *_ in files}
    assert files[1][1]['boards'][-1] == AS_OF                                               # the board the page opens


def test_the_rows_carry_the_bytes_the_page_reads_and_say_what_they_are():
    rows = examples.build(conn(), 'radar', AS_OF, NAMES, LISTS)
    for tab, name, as_of, n, size, sha, body in rows:
        assert (tab, as_of) == ('radar', AS_OF) and radar.NAME.fullmatch(name)
        assert size == len(body) and sha == hashlib.sha256(body).hexdigest()
        assert body == radar_bytes(name)                                   # the publisher's own encoding of the file
    assert [r[3] for r in rows][2] == len(built(conn(through=AS_OF))[f'radar-board-{AS_OF}'][0]['rows']['filter'])


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


def test_the_members_of_a_date_are_the_rows_covering_it_or_before_the_first_capture_the_unchanged_earliest():
    rows = [('AAAA', '2026-11-10', None), ('BBBB', '2026-11-10', '2026-11-20'), ('CCCC', '2026-11-20', None)]
    assert examples.members_on(rows, '2026-11-12', 'LQ45') == (['AAAA', 'BBBB'], 'recorded for 2026-11-12')
    assert examples.members_on(rows, '2026-11-25', 'LQ45')[0] == ['AAAA', 'CCCC']
    # before the first capture: the earliest members when nothing changed since, else no answer
    still = [('AAAA', '2026-11-10', None), ('BBBB', '2026-11-10', None)]
    assert examples.members_on(still, '2026-10-30', 'LQ45') == (
        ['AAAA', 'BBBB'], 'earliest recorded (2026-11-10), unchanged since; none recorded for 2026-10-30')
    with pytest.raises(examples.ExampleError, match=r'LQ45 changed after its first recording on 2026-11-10'):
        examples.members_on(rows, '2026-10-30', 'LQ45')
    with pytest.raises(examples.ExampleError, match='no LQ45 member covers 2026-11-30 although its history starts'):
        examples.members_on([('AAAA', '2026-11-10', '2026-11-20')], '2026-11-30', 'LQ45')
