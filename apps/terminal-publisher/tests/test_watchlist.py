"""EXEC-WATCHLIST L4: the Watchlist's daily file (watchlist.py) from a fake database that answers its statements."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import watchlist as W  # noqa: E402

DATES = [f'2026-11-{d:02d}' for d in (3, 4, 5, 6, 9, 10, 11, 12, 13)]


class Fake:
    def __init__(self, broker='2026-11-09', price='2026-11-13', radar='2026-11-09'):
        self.broker, self.price, self.radar, self.seen = broker, price, radar, []

    def run(self, sql, params):
        self.seen.append((sql, params))
        a = {
            W.MARKET_SQL: [('IHSG',)], W.PRICE_DATE_SQL: [(self.price,)] if self.price else [],
            W.BROKER_DATE_SQL: [(self.broker,)], W.RADAR_DATE_SQL: [(self.radar,)], W.EVENTS_LOADED_SQL: [('2026-11-09',)],
            W.DATES_SQL: [(d,) for d in reversed(DATES)],
            W.STOCKS_SQL: [('AAAA', 'PT A Tbk', 'Energy'), ('BBBB', 'PT B Tbk', 'Financials'), ('CCCC', 'PT C Tbk', 'Undefined')],
            W.F01_SQL: [('AAAA', 1000.0, 1.23456789, 6.3, 2.0, -14.1, 0.7, 30.5, -18.8),
                        ('BBBB', 50.0, -2.0, -1.6, -3.0, 4.0, 1.6, 50.0, 0.0)],
            W.F04_SQL: [('AAAA', 53.55, 95.3, 20.1, -2.1, -14.1), ('BBBB', 75.0, -1.0, 30.0, 5.0, None)],
            W.F06_SQL: [('AAAA', 523.1e9, 1.2e12, -3.3e12, 95.0), ('BBBB', -1e6, -894.9e6, 0.0, 12.5)],
            W.CLOSES_SQL: [('AAAA', d, 900.0 + i) for i, d in enumerate(DATES)] + [('BBBB', DATES[-1], 50.0)],
            W.EVENTS_SQL: [('AAAA', 'RUPS', '2026-11-17', 'MEETING_DATE'), ('AAAA', 'DIVIDEND', '2026-11-20', 'CUM_DATE')],
            W.RADAR_FILTERS_SQL: [('S1', 'S1', 'Heavy foreign accumulation', 1), ('S6D_RATIO', 'S6Δ', 'Foreign accumulation, strengthening', 5),
                                  ('S7', 'S7', 'Institutions in, retail out', 8)],
            W.RADAR_SQL: [('AAAA', 'S7'), ('AAAA', 'S1'), ('AAAA', 'S6D_RATIO'), ('BBBB', 'S6D_BOTH'), ('BBBB', 'S7')],
        }
        return a[sql]


def test_every_value_is_the_stored_column_at_its_own_date():
    f = Fake()
    doc = W.build(f.run)
    i, j, k = doc['ticker'].index('AAAA'), doc['ticker'].index('BBBB'), doc['ticker'].index('CCCC')
    assert (doc['prices_through'], doc['broker_through'], doc['radar_date']) == ('2026-11-13', '2026-11-09', '2026-11-09')
    assert (doc['last'][i], doc['r1d'][i], doc['r1m'][i]) == (1000.0, 1.2346, 6.3)
    v = doc['values']
    assert (v['rsi'][i], v['macdh'][i], v['adx'][i], v['ema50'][i], v['ema200'][i]) == (53.55, 95.3, 20.1, -2.1, -14.1)
    assert (v['r5d'][i], v['r3m'][i], v['volr'][i], v['vol20'][i], v['dd60'][i]) == (2.0, -14.1, 0.7, 30.5, -18.8)
    assert (v['fn1'][i], v['fn5'][i], v['fn20'][i], v['fp5'][i]) == (523100000000, 1200000000000, -3300000000000, 95.0)
    assert v['ema200'][j] is None                                    # no EMA 200 yet: no value, never a guess
    assert doc['last'][k] is None and all(v[x][k] is None for x in W.KEYS)   # a stock without rows: every value empty
    # the broker figures are read at the broker date, the rest at the price date
    params = {sql: p for sql, p in f.seen}
    assert params[W.F06_SQL] == {'b': '2026-11-09'} and params[W.F01_SQL] == {'p': '2026-11-13'} == params[W.F04_SQL]


def test_trend_holds_the_newest_closes_oldest_first_with_gaps_kept():
    doc = W.build(Fake().run)
    assert doc['dates'] == DATES
    i, j = doc['ticker'].index('AAAA'), doc['ticker'].index('BBBB')
    assert doc['trend'][i] == [900.0 + n for n in range(len(DATES))]
    assert doc['trend'][j] == [None] * (len(DATES) - 1) + [50.0]


def test_radar_badges_follow_the_radar_page_default_board_and_variant():
    f = Fake()
    doc = W.build(f.run)
    # board order (filter position), the board's labels, only default variants (S6D_BOTH is not S6Δ's default)
    assert doc['radar'] == {'AAAA': ['S1', 'S6Δ', 'S7'], 'BBBB': ['S7']}
    assert dict(f.seen)[W.RADAR_SQL] == {'r': '2026-11-09', 'level': 'standard', 'gate': 'broad'}
    assert doc['radar_filters'][1] == {'label': 'S6Δ', 'name': 'Foreign accumulation, strengthening'}


def test_events_and_catalog():
    doc = W.build(Fake().run)
    assert doc['events'] == {'AAAA': [['RUPS', '2026-11-17', 'MEETING_DATE'], ['DIVIDEND', '2026-11-20', 'CUM_DATE']]}
    assert [c['key'] for c in doc['catalog']] == list(W.KEYS) and len(W.KEYS) == 14
    assert set(doc['default']) <= set(W.KEYS) and len(doc['default']) <= 8
    assert {c['date'] for c in doc['catalog'] if c['family'] == 'Foreign flow'} == {'broker'}


def test_no_complete_price_date_gives_no_file_and_no_broker_date_leaves_flow_empty():
    assert W.build(Fake(price=None).run) is None
    out, kept, carry = W.files(None, [], [], stream=Fake(price=None).run)
    assert out == [] and kept == [] and carry == {'code': W.CODE}
    doc = W.build(Fake(broker=None).run)
    assert all(x is None for x in doc['values']['fn5'])


def test_files_and_stamp_are_exact_and_equal_runs_give_equal_bytes():
    out, kept, _ = W.files(None, [], [], stream=Fake().run)
    (name, doc, rows, as_of), = out
    assert W.NAME.fullmatch(name) and rows == 3 and as_of == '2026-11-13' and kept == []

    class Conn:
        def __init__(self, f):
            self.f = f

        def execute(self, sql, params):
            rows = self.f.run(sql, params)
            return type('C', (), {'fetchall': lambda s: rows, 'fetchone': lambda s: rows[0]})()
    a, b = W.stamp(Conn(Fake())), W.stamp(Conn(Fake()))
    assert a == b == [W.digest(doc), W.CODE]
    assert W.stamp(Conn(Fake(broker='2026-11-10')))[0] != a[0]      # any content change changes the stamp
    assert json.dumps(W.build(Fake().run), sort_keys=True) == json.dumps(doc, sort_keys=True)
