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
