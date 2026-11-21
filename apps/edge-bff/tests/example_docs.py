"""3e, the example mode (ERRORS M527): made-up page files for the example tests, built by the publisher's own builders
(apps/terminal-publisher/radar.py, overview.py, examples.py) from a few invented rows or the Backtest page's synthetic
market, so they have exactly the shapes the pages read. No market data: every ticker, price and figure here is made up."""
import datetime as dt
import functools
import gzip
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                     # apps/edge-bff
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / 'apps' / 'terminal-publisher'))
import examples  # noqa: E402
import overview as ov  # noqa: E402
import radar  # noqa: E402

RADAR_AS_OF = '2026-11-06'
RADAR_DATES = ['2026-11-04', '2026-11-05', RADAR_AS_OF]
TICKERS = [f'T{i:03d}' for i in range(60)]                    # enough rows that a board scrolls


def radar_example():
    """The three files of the Radar's opening view: the publisher's own documents of a made-up board (hits at the default
    level and gate, near misses, left stocks and other levels and gates, every measure), cut by the publisher's own
    examples.radar_opening as the capture cuts them."""
    filters = [('S1', 1, 'S1', 'S1', None, True, 'Heavy foreign accumulation', 'Q1', 'W1', 'z-score', False)]
    rules = [('S1', c, lv, f'{c} at {lv}', t, None, 'decided') for c, t in (('A', 0), ('B', 5)) for lv in radar.LEVELS]
    names = {t: f'Company {t}' for t in TICKERS}
    hits = TICKERS[:-3]
    rows = [(RADAR_AS_OF, 'S1', 'standard', 'broad', t, 'hit', 2, 2, 1, None, None, 3.0 - i / 100, None)
            for i, t in enumerate(hits)]
    # behind a click (the filter page, a segment): a near miss, a stock that left, a Loose hit, a Liquid hit
    rows += [(RADAR_AS_OF, 'S1', 'standard', 'broad', TICKERS[-3], 'near', 1, 2, None, None, None, 1.0, None),
             (RADAR_AS_OF, 'S1', 'standard', 'broad', TICKERS[-2], 'left', 1, 2, None, 'B', None, None, None),
             (RADAR_AS_OF, 'S1', 'loose', 'broad', TICKERS[-1], 'hit', 1, 2, 1, None, None, 0.5, None),
             (RADAR_AS_OF, 'S1', 'standard', 'liquid', TICKERS[-1], 'hit', 2, 2, 1, None, None, 0.4, None)]
    gates = [(d, 900, 1.9e9, 1.8e10, 450, 180) for d in RADAR_DATES]
    prices = {t: [(d, 1000.0 + k) for k, d in enumerate(RADAR_DATES)] for t in TICKERS}
    measures = {t: (RADAR_AS_OF, t, *[float(k) for k in range(len(radar.MEASURES))]) for t in TICKERS}
    meta = radar.meta_doc(filters, rules, names, [('lq45', 'index', 'LQ45', 'LQ45', TICKERS[:45])])
    days = radar.days_doc(gates, [(RADAR_AS_OF, 'S1', 'standard', 'broad', len(hits)), (RADAR_AS_OF, 'S1', 'loose', 'broad', 1)],
                          ['S1'], {'S1': list(radar.LEVELS)}, {d: 7000.0 for d in RADAR_DATES}, RADAR_AS_OF, RADAR_DATES)
    board = radar.board_doc(RADAR_AS_OF, rows, measures, prices)
    meta, days, board = examples.radar_opening(meta, days, board, RADAR_AS_OF)
    return {'radar-meta': meta, 'radar-days': days, f'radar-board-{RADAR_AS_OF}': board}


def weekdays(last, n):
    out, d = [], dt.date.fromisoformat(last)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return out[::-1]


OVERVIEW_DATES = weekdays('2026-11-20', ov.SERIES_SESSIONS)  # 300 sessions, as the publication holds
OVERVIEW_DAYS = OVERVIEW_DATES[-3:]                          # three day files: the example is the newest
SECTORS = [('IDXFINANCE', 'Financials'), ('IDXENERGY', 'Energy'), ('IDXTECHNO', 'Technology')]


def wib(d, hour, minute):
    """The epoch second of a WIB time on date d (the page reads bars as WIB)."""
    return int(dt.datetime.fromisoformat(f'{d}T{hour:02d}:{minute:02d}:00+07:00').timestamp())


def overview_files():
    """Every file of a made-up Market Overview publication: meta, series, three day files and overview-stocks."""
    stocks = [(t, f'Company {t}', SECTORS[i % len(SECTORS)][1]) for i, t in enumerate(TICKERS)]
    lists = [('lq45', 'INDEX', 'LQ45', 'LQ45', TICKERS[:20]), ('big', 'KONGLO', 'BIG', 'Big group', TICKERS[20:30])]
    tickers = ['IHSG', ov.BENCHMARK, *(t for t, _ in SECTORS)]
    closes = {t: {d: (7000 + k + j, 7010 + k + j, 6990 + k + j, 7005 + k + j * 2) for k, d in enumerate(OVERVIEW_DATES)}
              for j, t in enumerate(tickers)}
    breadth = {d: (900, 400 + k % 90, 880, 380 + k % 70) for k, d in enumerate(OVERVIEW_DATES)}
    flow = [(d, 1.0e12 + k * 1e9, 0.9e12 + k * 2e9, 5.0e12) for k, d in enumerate(OVERVIEW_DATES)]
    files = {'overview-meta': ov.meta_doc(stocks, SECTORS, lists, 'IHSG', OVERVIEW_DAYS, 'market_cap',
                                          OVERVIEW_DATES[-1], OVERVIEW_DATES[-1]),
             'overview-series': ov.series_doc(OVERVIEW_DATES, closes, SECTORS, 'IHSG', breadth, flow)}
    index = {t: i for i, t in enumerate(TICKERS)}
    for j, d in enumerate(OVERVIEW_DAYS):
        prev = OVERVIEW_DATES[OVERVIEW_DATES.index(d) - 1]
        rows = [(t, 1000.0 + i + j, (i % 7 - 3) * 0.5, (i % 5 - 2) * 1.1, (i % 9 - 4) * 1.7, i % 2 == 0, i % 3 == 0)
                for i, t in enumerate(TICKERS)]
        sizes = {t: 1e12 * (i + 1) for i, t in enumerate(TICKERS)}
        stock_flow = {t: (t, (i % 5 - 2) * 1e9, (i % 7 - 3) * 2e9, (i % 3 - 1) * 5e9, (i % 4 - 2) * 9e9)
                      for i, t in enumerate(TICKERS)}
        bars = {'5m': [(wib(d, 9, 0) + 300 * k, 7000.0 + k) for k in range(60)],
                '1h': [(wib(x, 10, 0), 7000.0 + n) for n, x in enumerate(OVERVIEW_DATES[-5:])]}
        files[f'overview-day-{d}'] = ov.day_doc(d, prev, index, rows, sizes, 'market_cap', stock_flow, closes, 'IHSG',
                                                (14.2 + j, 55.0), ov.market_figures(flow, d), bars)
    files['overview-stocks'] = {'schema': ov.STOCKS_SCHEMA, 'ticker': TICKERS, 'dates': OVERVIEW_DATES,
                                'fnet_dates': OVERVIEW_DATES, 'close': [[1000.0] * len(OVERVIEW_DATES)] * len(TICKERS),
                                'fnet': [[1.0e9] * len(OVERVIEW_DATES)] * len(TICKERS)}
    return files


WATCHLIST_DATES = OVERVIEW_DATES[-30:]                       # the trend line's 30 sessions, to the Overview's newest day
WATCHLIST_AS_OF = WATCHLIST_DATES[-1]
WATCHLIST_BROKER = '2026-11-09'                              # the broker date lags the prices, as on dev (2026-11-21)


def watchlist_files():
    """The two files of a made-up Watchlist publication (watchlist-stocks, watchlist-radar), built by the publisher's own
    watchlist.build from invented rows of TICKERS, the Market Overview's made-up universe (so overview_files' LQ45 list
    names stocks this file holds): every indicator filled, upcoming corporate actions for two stocks, Radar badges for
    a few. A new list each call (tests change them)."""
    import watchlist as W
    dates = WATCHLIST_DATES
    stocks = [(t, f'Company {t}', SECTORS[i % len(SECTORS)][1]) for i, t in enumerate(TICKERS)]
    answers = {
        W.MARKET_SQL: [('IHSG',)], W.RECENT_SQL: [(d,) for d in reversed(dates[-W.COMPLETE_SCAN:])],
        W.BROKER_DATE_SQL: [(WATCHLIST_BROKER,)], W.RADAR_DATE_SQL: [(dates[-1],)], W.EVENTS_LOADED_SQL: [(dates[-1],)],
        W.DATES_SQL: [(d,) for d in reversed(dates)], W.STOCKS_SQL: stocks,
        W.F01_SQL: [(t, 1000.0 + i, (i % 7 - 3) * 0.5, (i % 5 - 2) * 1.1, (i % 9 - 4) * 0.7, (i % 11 - 5) * 1.3,
                     0.5 + i % 4, 20.0 + i % 9, -(i % 13) * 1.5) for i, t in enumerate(TICKERS)],
        W.F04_SQL: [(t, 30.0 + i % 40, (i % 6 - 3) * 2.5, 15.0 + i % 30, (i % 8 - 4) * 1.2, (i % 10 - 5) * 2.0)
                    for i, t in enumerate(TICKERS)],
        W.F06_SQL: [(t, (i % 5 - 2) * 1e9, (i % 7 - 3) * 2e9, (i % 3 - 1) * 5e9, float(i % 100)) for i, t in enumerate(TICKERS)],
        W.CLOSES_SQL: [(t, d, 1000.0 + i + k) for i, t in enumerate(TICKERS) for k, d in enumerate(dates)],
        W.EVENTS_SQL: [(TICKERS[1], 'DIVIDEND', '2026-11-27', 'CUM_DATE'), (TICKERS[25], 'RUPS', '2026-12-03', 'MEETING_DATE')],
        W.RADAR_FILTERS_SQL: [('S1', 'S1', 'Heavy foreign accumulation', 1), ('S7', 'S7', 'Institutions in, retail out', 8)],
        W.RADAR_SQL: [(TICKERS[0], 'S1'), (TICKERS[2], 'S7')],
    }
    run = lambda sql, params: [(len(TICKERS),) * 3] if sql == W.COUNTS_SQL else answers[sql]
    return W.build(run)


BACKTEST_AS_OF, BACKTEST_FIRST = '2026-10-23', '2025-10-23'   # the synthetic market's last day, one year before it


@functools.cache
def backtest_made_up():
    """The Backtest page's made-up example (backtest/tests/example-made-up.ts): the page's own default request on the part
    of the synthetic market's catalog cut to one year, that market's run of it, its bars and the catalog before the
    cut."""
    out = subprocess.run(['node', '--experimental-transform-types', '--no-warnings=ExperimentalWarning', '--import',
                          './apps/backtest-worker/loader/register.mjs', 'apps/edge-bff/backtest/tests/example-files.ts',
                          BACKTEST_AS_OF, BACKTEST_FIRST], cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise RuntimeError(f'example-files.ts failed: {out.stderr[-2000:]}')
    return json.loads(out.stdout)


def backtest_example():
    """The four files of the Backtest's example, made by the publisher's own builder (examples.py backtest_files, its
    stored() checks) from the made-up example: what the capture job writes from the worker."""
    made = backtest_made_up()

    class Conn:                                                 # no share-basis change; the ticker's bars of the period
        def execute(self, sql, params=()):
            rows = [tuple(r) for r in made['bars']] if sql == examples.BARS_SQL else []
            return type('Rows', (), {'fetchall': lambda self: rows})()
    releases = json.loads((ROOT / 'catalog' / 'releases.json').read_text())
    rows = examples.build(Conn(), 'backtest', BACKTEST_AS_OF, {}, [], request=made['request'],
                          run=lambda q: made['result'], catalog=made['raw'], built_on=made['built_on'], releases=releases)
    docs = {r[1]: json.loads(gzip.decompress(r[6])) for r in rows}
    if docs['backtest-catalog'] != made['catalog']:
        raise AssertionError('the publisher cuts the catalog unlike example-files.ts')
    return docs


SCREENER_AS_OF = '2026-10-27'                                   # the made-up market's last day (example-files.ts AS_OF)


@functools.cache
def screener_made_up():
    """The Screener's made-up example (apps/screener-worker/tests/example-files.ts): the worker itself on that suite's
    made-up market (a stock drawn for each preset the example may show), the example's preset (examples.py
    SCREENER_PRESET), the released items of the release file."""
    out = subprocess.run(['node', '--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import',
                          './apps/backtest-worker/loader/register.mjs', 'apps/screener-worker/tests/example-files.ts',
                          examples.SCREENER_PRESET],
                         cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise RuntimeError(f'example-files.ts failed: {out.stderr[-2000:]}')
    return json.loads(out.stdout)


def screener_example():
    """The four files of the Screener's example, made by the publisher's own builder (examples.py screener_files, its
    stored() checks) from the made-up example and the release file: what the capture job writes from the real one."""
    releases = json.loads((ROOT / 'catalog' / 'releases.json').read_text())
    rows = examples.build(None, 'screener', SCREENER_AS_OF, {}, [], example=screener_made_up(), releases=releases)
    return {r[1]: json.loads(gzip.decompress(r[6])) for r in rows}
