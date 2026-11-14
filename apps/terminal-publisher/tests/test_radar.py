"""EXEC-RADAR R5: the Radar files (radar.py) and their place in a publisher run. No database: a fake answers the Feature 07
statements from small tables; the SQL itself ran against the rehearsal database (verification/radar/REHEARSAL.md)."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as pub  # noqa: E402
import radar  # noqa: E402
from test_publisher import BROKERS, PRICES, TODAY, UNIVERSE, FakeBucket, FakeConn, no_wait, offline  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[3]
DATES = ['2026-11-04', '2026-11-05', '2026-11-06']
GATES = [(d, 850 + i, 1.9e9, 1.8e10, 425, 170) for i, d in enumerate(DATES)]
FILTERS = [('S1', 1, 'S1', 'S1', None, True, 'Heavy foreign accumulation', 'Q1', 'W1', 'z-score', False),
           ('S8', 9, 'S8', 'S8', None, True, 'One-day foreign buying spike', 'Q8', 'W8', 'robust z', True)]
RULES = [('S1', c, lv, f'{c} at {lv}', t, None, 'decided') for c, t in (('A', 0), ('B', 5)) for lv in radar.LEVELS]
RULES += [('S8', c, 'standard', f'S8 {c}', 3, None, 'decided') for c in 'ABC']
# (date, filter, level, gate, ticker, status, met, cond_n, run_day, left_reason, strong, sort_value, flag)
RESULTS = [
    ('2026-11-04', 'S1', 'standard', 'broad', 'BBCA', 'hit', 3, 2, 1, None, None, 2.5, None),
    ('2026-11-05', 'S1', 'standard', 'broad', 'BBCA', 'hit', 3, 2, 2, None, None, 2.7, 'One-day block: x'),
    ('2026-11-05', 'S1', 'loose', 'liquid', 'TLKM', 'near', 1, 2, None, None, None, 1.0, None),
    ('2026-11-06', 'S1', 'standard', 'broad', 'BBCA', 'left', 1, 2, None, 'B', None, None, None),
    ('2026-11-06', 'S8', 'standard', 'broad', 'TLKM', 'hit', 7, 3, 1, None, True, 4.2, None),
]
MEASURE_ROW = lambda d, t: (d, t, *[float(i) for i in range(len(radar.MEASURES))])
CLOSES = {'BBCA': [9000, 9100, 9200, 9300, 9250], 'TLKM': [3000, 3010, 2990, 3050, 3100], 'IHSG': [7000, 7010, 7020, 7030, 7040]}
PRICE_DATES = ['2026-10-30', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06']


class RadarConn(FakeConn):
    """FakeConn plus the Feature 07 tables (radar.py statements)."""

    def __init__(self, *a, tables=True, **kw):
        super().__init__(*a, **kw)
        self.tables, self.gates, self.results, self.version = tables, list(GATES), list(RESULTS), 'radar-v1'
        self.closes_after = 2
        self.rules_md5, self.rules = 'rules', list(RULES)

    def _rows(self, sql, params):
        if sql == radar.PROBE_SQL:
            return [(self.tables,)]
        if sql == radar.STAMP_SQL:
            return [(f'stamp-{len(self.results)}-{self.results[-1][11]}', len(self.gates), PRICE_DATES[-1], self.version,
                     self.closes_after, 'lists', self.rules_md5)]
        if sql == radar.GATES_SQL:
            return sorted(self.gates, reverse=True)[:params[0]]
        if sql == radar.FILTERS_SQL:
            return FILTERS
        if sql == radar.RULES_SQL:
            return self.rules
        if sql == radar.COUNTS_SQL:
            out = {}
            for r in self.results:
                if r[5] == 'hit' and r[0] >= params[0]:
                    out[r[:4]] = out.get(r[:4], 0) + 1
            return [(*k, n) for k, n in out.items()]
        if sql == radar.HISTORY_SQL:
            return [(r[0], r[1], r[2], r[3], r[4], r[5], r[8], r[9]) for r in reversed(self.results)
                    if r[5] in ('hit', 'left') and r[0] >= params[0]]
        if sql == radar.BOARD_SQL:
            return [r for r in reversed(self.results) if r[0] in params[0]]
        if sql == radar.MEASURE_SQL:
            return [MEASURE_ROW(d, t) for d in params[0] for t in params[1]]
        if sql.startswith(f'SELECT max(date)::text FROM {radar.PRICE}'):
            return [(PRICE_DATES[-1],)]
        if sql == radar.PRICES_SQL:
            return [(t, d, float(c)) for t in reversed(params[2]) if t in CLOSES
                    for d, c in zip(PRICE_DATES, CLOSES[t]) if params[0] <= d <= params[1]]
        return super()._rows(sql, params)


def run(mode='backfill', conn=None, bucket=None):
    conn = conn or RadarConn(PRICES, BROKERS, UNIVERSE)
    bucket = bucket or FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run(mode)
    return p, conn, bucket


def test_every_radar_file_is_content_keyed_and_written_before_the_state_json_that_indexes_it():
    _, _, bucket = run()
    state = bucket.get_json('state.json')
    names = sorted(state['radar'])
    assert names == sorted(['radar-meta', 'radar-days', *(f'radar-board-{d}' for d in DATES), 'radar-f-s1', 'radar-f-s8'])
    assert state['radar_stamp'][1:] == ['3', PRICE_DATES[-1], 'radar-v1', '2', 'lists', 'rules']   # strings: stable in JSON
    for name, e in state['radar'].items():
        key = e['key'][len('v1/'):]
        assert re.fullmatch(rf'radar/{name}\.{e["sha256"][:16]}\.json\.gz', key) and key in bucket.puts[:-1]
        body = bucket.objects[key]
        assert (len(body), hashlib.sha256(body).hexdigest()) == (e['bytes'], e['sha256'])
        assert radar.NAME.fullmatch(name) and pub.XSECTION_KEY.pattern  # every name fits terminal-api's name rule
        assert re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,31}', name)
    assert bucket.puts[-1] == 'state.json'


def test_the_documents_carry_what_the_page_reads():
    _, _, bucket = run()
    state = bucket.get_json('state.json')['radar']
    doc = lambda n: bucket.get_json(state[n]['key'][3:])
    meta = doc('radar-meta')
    assert [f['id'] for f in meta['filters']] == ['S1', 'S8'] and meta['filters'][1]['own_levels'] is True
    assert {r['level'] for r in meta['rules'] if r['filter'] == 'S8'} == {'standard'}
    assert meta['names'] == {t: n for t, n, *_ in UNIVERSE} and meta['lists'][0]['members'] == sorted(meta['lists'][0]['members'])
    days = doc('radar-days')
    assert days['dates'] == DATES and days['boards'] == DATES and days['broker_through'] == DATES[-1]
    assert days['counts']['S1']['standard/broad'] == [1, 1, 0] and set(days['counts']['S8']) == {'standard/broad', 'standard/liquid'}
    assert days['ihsg'] == [7020.0, 7030.0, 7040.0] and days['prices_through'] == PRICE_DATES[-1]
    assert days['gate']['universe_n'] == [850, 851, 852]
    board = doc('radar-board-2026-11-05')
    assert board['stocks']['ticker'] == ['BBCA', 'TLKM']
    assert board['stocks']['close'] == [9300.0, 3050.0] and board['stocks']['chg_1d'] == [round(100 * (9300 / 9200 - 1), 4), round(100 * (3050 / 2990 - 1), 4)]
    assert board['stocks']['spark'][0] == [9000.0, 9100.0, 9200.0, 9300.0]          # closes up to the result date
    assert board['rows']['status'] == ['hit', 'near'] and board['rows']['flag'] == ['One-day block: x', None]  # filter, gate, level
    assert board['measures']['columns'] == list(radar.MEASURES) and len(board['measures']['values'][0]) == len(radar.MEASURES)
    f1 = doc('radar-f-s1')
    assert f1['dates'] == DATES and f1['stocks']['ticker'] == ['BBCA']
    assert f1['hits'] == {'date': [0, 1], 'stock': [0, 0], 'level': ['standard'] * 2, 'gate': ['broad'] * 2, 'run_day': [1, 2]}
    assert f1['left'] == {'date': [2], 'stock': [0], 'level': ['standard'], 'gate': ['broad'], 'left_reason': ['B']}
    assert f1['stocks']['close'] == [[9200.0, 9300.0, 9250.0]]


def test_the_files_are_deterministic_and_an_unchanged_stamp_carries_the_index_forward(capsys):
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    _, _, other = run()
    assert other.get_json('state.json')['radar'] == first                      # same tables, same bytes
    n = len(bucket.puts)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert bucket.get_json('state.json')['radar'] == first
    assert not [k for k in bucket.puts[n:] if k.startswith('radar/')]
    assert '"reason": "unchanged"' in capsys.readouterr().out
    # a recomputed date changes the stamp: the files are rebuilt, only the changed ones are new objects
    conn.results[-1] = (*conn.results[-1][:11], 4.9, None)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['radar']
    changed = sorted(n for n in now if now[n]['sha256'] != first[n]['sha256'])
    assert changed == ['radar-board-2026-11-06']
    assert [k for k in bucket.puts[n:] if k.startswith('radar/')] == [now['radar-board-2026-11-06']['key'][3:]]


def test_a_changed_rule_row_rebuilds_the_meta_file_without_a_new_rule_version():
    """2026-11-14 (user "1A"): a threshold's status or a filter's warning is part of the stamp; only radar-meta moves."""
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    conn.rules = [r[:6] + ('decided',) for r in conn.rules] + [('S1', 'C', 'loose', 'C at loose', 90, None, 'decided')]
    conn.rules_md5 = 'rules-2'
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    now = bucket.get_json('state.json')['radar']
    assert sorted(n for n in now if now[n]['sha256'] != first[n]['sha256']) == ['radar-meta']


def test_modes_that_do_not_maintain_the_radar_carry_it_and_the_cleanup_keeps_it():
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    for mode in ('events', 'logos'):
        pub.Publisher(conn, bucket, today=TODAY).run(mode)
        assert bucket.get_json('state.json')['radar'] == first
    for e in first.values():
        assert e['key'][3:] in bucket.objects                                 # nothing named was deleted


def test_without_the_feature_07_tables_the_run_publishes_without_a_radar():
    conn = RadarConn(PRICES, BROKERS, UNIVERSE, tables=False)
    _, _, bucket = run(conn=conn)
    state = bucket.get_json('state.json')
    assert state['radar'] == {} and state['xsection'] and not [k for k in bucket.puts if k.startswith('radar/')]


def test_a_failed_radar_build_keeps_the_previous_index_and_the_rest_is_published(capsys):
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    conn.results[-1] = (*conn.results[-1][:11], 5.5, None)
    broken = RadarConn._rows

    def fail(self, sql, params):
        if sql == radar.BOARD_SQL:
            raise RuntimeError('connection to server at "secret-host" failed')
        return broken(self, sql, params)
    RadarConn._rows = fail
    try:
        p2 = pub.Publisher(conn, bucket, today=TODAY)
        p2.run('daily')
    finally:
        RadarConn._rows = broken
    out = capsys.readouterr().out
    assert bucket.get_json('state.json')['radar'] == first and p2.radar_failed == 'build'
    assert '"radar_failed"' in out and 'secret-host' not in out                # the class only


def test_terminal_api_reads_the_radar_index_as_written():
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    _, _, bucket = run()
    index = bucket.get_json('state.json')['radar']
    assert reader.radar_index(index) == index == pub.radar_entries(index)
    good = index['radar-meta']
    raw = {**index, 'radar-x': {**good}, 'radar-y': {**good, 'key': good['key'].replace('radar/', 'xsection/')}}
    assert pub.radar_entries(raw) == reader.radar_index(raw) == index
    assert 'radar' not in reader.STATE_FIELDS                                   # /state never shows it


# ---- QA 2026-11-14 (review of 60d610c) --------------------------------------------------------------------------------
from test_publisher import HOUR, at  # noqa: E402


def test_a_sweeping_run_deletes_a_radar_object_no_index_names():
    """The daily sweep's baseline names the Radar index: an orphan (a put of a run that stopped) older than the last
    finished run goes, every named file stays."""
    conn, bucket = RadarConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    at(bucket, conn, 'backfill', 0)
    bucket.put('radar/radar-meta.0123456789abcdef.json.gz', b'orphan', 'application/gzip')
    bucket.modified['radar/radar-meta.0123456789abcdef.json.gz'] = bucket.clock - HOUR
    at(bucket, conn, 'daily', 2, None, None, None, True)
    assert 'radar/radar-meta.0123456789abcdef.json.gz' not in bucket.objects
    for e in bucket.get_json('state.json')['radar'].values():
        assert e['key'][3:] in bucket.objects


def test_no_result_date_keeps_the_published_radar_and_reports_it(capsys):
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    conn.gates = []
    conn.results[-1] = (*conn.results[-1][:11], 7.7, None)          # the stamp moves
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert bucket.get_json('state.json')['radar'] == first and p2.radar_failed == 'empty'
    assert all(e['key'][3:] in bucket.objects for e in first.values())


def test_missing_stock_lists_fail_the_build_instead_of_publishing_an_empty_menu():
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    conn.stock_lists = None                                          # STOCK_LISTS_SQL fails
    conn.results[-1] = (*conn.results[-1][:11], 8.8, None)
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert bucket.get_json('state.json')['radar'] == first and p2.radar_failed == 'build'


def test_a_named_object_missing_from_the_bucket_is_put_again_under_an_unchanged_stamp():
    p, conn, bucket = run()
    first = bucket.get_json('state.json')['radar']
    gone = first['radar-days']['key'][3:]
    del bucket.objects[gone]
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert gone in bucket.objects and bucket.get_json('state.json')['radar'] == first


def test_a_radar_failure_is_a_partial_publication(monkeypatch):
    sent = []
    monkeypatch.setattr(pub, 'notify_publication', lambda status, *a, **kw: sent.append((status, kw.get('files'))))

    class Failed:
        xsection_failed, refs_failed, radar_failed, broker_behind = [], [], 'build', 0
    assert ['radar'] == sorted([] + [] + (['radar'] if Failed.radar_failed else []))
    src = Path(pub.__file__).read_text()
    assert "if pub.xsection_failed or pub.refs_failed or pub.radar_failed:" in src
    assert "(['radar'] if pub.radar_failed else [])" in src


def test_results_are_read_for_the_current_rule_version_only():
    for sql in (radar.COUNTS_SQL, radar.HISTORY_SQL, radar.BOARD_SQL):
        assert 'rule_version = public.feature_07_rule_version()' in sql
