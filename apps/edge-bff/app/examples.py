"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; CONTRACT.md 8b "3e";
ERRORS M527): each data page as it opens, for a principal holding <tab>.example: the free plan, and the guest plan (a
visitor who is not signed in, on a site with guests). A click on the page asks to sign in (the guest) or to upgrade (an
account): the page's own lock and the shell's box. The user: "kayak semacam static HTML di hari tersebut saja".

  GET /api/v1/examples/<tab>/index             {finished_at, as_of, files: {name: {sha256, bytes, rows, as_of}}}
  GET /api/v1/examples/<tab>/file/<name>?sha=  the file's gzip JSON bytes (Content-Encoding gzip), the shape the page
                                               reads from its live route; another sha answers 409 EXAMPLE_FILE_REPLACED

Two sources (TABS):
- stored (the Radar, the Backtest, the Screener): the rows of edge_bff.example_files (migration
  20261121_001), written once by the capture job (verification/edge_multiuser/example_mode/capture_job.py,
  apps/terminal-publisher/examples.py: the files of the page's opening view cut at one past date, none naming a later
  one). Read from the database at most every REFRESH_SECONDS per tab and process and served from memory, so a request
  reads neither the database nor terminal-api: the ceiling of all visitors together (EDGE_GUEST_CALLS_PER_HOUR) counts
  the Terminal's calls to terminal-api and does not apply.
- the Market Overview's latest market date (the user: "Semua overview itu menampilkan data di [hari itu]"; "1. tetap
  seperti itu 2. ok"): the live publication's three files of the opening view (overview-meta, overview-series, the
  newest overview-day), read through the page relay (app/pages.py, its caches and its terminal-api grant for the
  principal whose request missed them) and trimmed here to what the page shows when it opens: each series to the
  window of the panel that reads it (breadth's 120 sessions and its start; Sector Performance's 60, null before; the KPI
  strip's 30 turnover sessions; no daily foreign buy or sell); the day's
  stocks to their 1D figures (every other period's values null, a new field null too); the market's flow to its 1D
  period; IHSG's bars to the session's 5-minute bars; the date picker to that day. The older day files and
  overview-stocks (every stock's 300 sessions) stay with overview.view. Trimmed once per publication and process.
- the Watchlist's latest price date (the user, 2026-11-21: "Untuk table watchlist nggak apa-apa pakai data latest
  saja"; "Benar opsi B": the list's stocks with the four default indicators, as the page opens): the live
  watchlist-stocks cut to the example list's stocks, today's LQ45 members as the Market Overview publishes them
  (overview-meta `lists`, read from Stock_List_Member by the publisher), with every column of the page's table, the
  default indicators' values (another indicator's null: adding one is a click) and the members' upcoming corporate
  actions with the date they were loaded (the user, 2026-11-22: "B", as the page shows them); and watchlist-lists, that
  one list. A missing list or a member the file does not hold answers EXAMPLE_UNAVAILABLE: the example names its list
  and never shows another (ERRORS M527). No watchlist-radar (radar.view). Cut once per pair of publications and
  process.

The guarantee is these routes: they hand out only the example's files, and only to a principal holding the tab's
<tab>.example (auth.need(..., guests=True), before the caches); a page's live routes still need <tab>.view, and the
browser keeps a file only with `Cache-Control: private, no-cache` and its ETag (app/pages.py). The shell opens a tab in
example mode when its index answers 200 (static/edge-app.js ExampleTabPage), so a tab without an example, or a principal
without the capability, gets the locked page as before. Every refusal names its cause and the way on (AGENTS.md "Gates
and evidence" (d)).
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import re
import time

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from . import releases, terminal_access
from .errors import Refusal, failure_class

logger = logging.getLogger('edge_bff.examples')

# the tabs whose page reads an example in this build (the page's own example mode: src/main.ts of each), their names in
# the refusals and their source; a tab joins with its page
TABS = {'radar': 'Radar', 'overview': 'Market Overview', 'watchlist': 'Watchlist', 'backtest': 'Backtest', 'screener': 'Screener'}
LATEST = {'overview', 'watchlist'}                      # the latest publication, trimmed; every other tab is stored
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')          # edge_bff.example_files.name (example_files_name)
SHA = re.compile(r'[0-9a-f]{64}')
REFRESH_SECONDS = 300                                   # a capture shows within this long; nothing changes otherwise

LIST_SQL = ('SELECT name, as_of::text AS as_of, rows, bytes, sha256, made_at FROM edge_bff.example_files '
            'WHERE tab = %s ORDER BY name')
BODIES_SQL = 'SELECT name, sha256, body FROM edge_bff.example_files WHERE tab = %s AND sha256 = ANY(%s)'

# The Market Overview's opening view (apps/edge-bff/overview/src/app.ts: DEFAULT, the IHSG period's default and last30;
# tests/test_examples.py reads them there): every period control opens on 1D; breadth opens on 120 sessions (with the
# session before it, its start: the dates and the EMA shares), Sector Performance on 60 (the index and sector lines,
# whose last 30 the KPI strip's lines read too), and the KPI strip's turnover line is 30 broker sessions long. The page
# reads the series by their position in the dates, so a line keeps their length, null before its own window (the
# example-mode re-check, ERRORS M527).
OVERVIEW_PERIOD = '1D'
OVERVIEW_SESSIONS = 120 + 1
OVERVIEW_INDEX_SESSIONS = 60 + 1
OVERVIEW_FLOW_SESSIONS = 30
OVERVIEW_DAY = re.compile(r'overview-day-([0-9]{4}-[0-9]{2}-[0-9]{2})')
OVERVIEW_BARS = '5m'                                    # IHSG's bars of the session (the 1D chart); '1h' is the 5D chart's
# The fields each file keeps, at every depth (the example-mode checker, ERRORS M527: a block copied whole would pass a
# field the publisher adds inside it). A shape is KEEP (a value holding no object, kept as it is: a number, a text, a
# list of them), {key: shape} (an object: only these keys), {'*': shape} (an object whose every key has the shape, the
# index of a ticker) or [shape] (a list of that shape). A field not named is left out, and a value of another shape than
# named (an object where a value was) is null: fail closed. The day's stocks are read by position: a column not named
# is null (STOCK_KEYS).
KEEP = 'keep'
META_SHAPE = {'schema': KEEP, 'market': KEEP, 'benchmark': KEEP, 'stocks': {'ticker': KEEP, 'name': KEEP, 'sector': KEEP},
              'sectors': [{'name': KEEP, 'index': KEEP}],
              'lists': [{'key': KEEP, 'kind': KEEP, 'code': KEEP, 'name': KEEP, 'members': KEEP}],
              'dates': KEEP, 'size_basis': KEEP, 'prices_through': KEEP, 'broker_through': KEEP, 'periods': {'flow': KEEP}}
SERIES_KEYS = ('schema', 'dates', 'index', 'sector', 'above_ema50', 'above_ema200')
# the KPI strip's turnover line (app.ts, model.ts flowEnd): the daily foreign buy and sell are read only by the Foreign
# Flow panel's Custom range, a time control, and 5 or 20 of them sum to its locked 5D and 1M periods
FLOW_KEYS = ('dates', 'turnover')
DAY_SHAPE = {'schema': KEEP, 'date': KEEP, 'prior_date': KEEP, 'size_basis': KEEP,
             'index': {'*': {'open': KEEP, 'high': KEEP, 'low': KEEP, 'close': KEEP, 'prior_close': KEEP}},
             'volatility': {'window': KEEP, 'value': KEEP, 'rank_1y': KEEP},
             'breadth': {'advancers': KEEP, 'decliners': KEEP, 'unchanged': KEEP}}
MARKET_KEYS = ('date', 'turnover', 'turnover_avg20', 'turnover_ratio', 'foreign_net_1d', 'foreign_net_10d')
PERIOD_SHAPE = {'buy': KEEP, 'sell': KEEP, 'net': KEEP, 'from': KEEP}
BARS_SHAPE = {'t': KEEP, 'c': KEEP}
STOCK_KEYS = ('i', 'close', 'r1d', 'size', 'above_ema50', 'above_ema200', 'fnet_1d')
# what the publisher writes and the opening view does not read, per file (a path names an object key, joined by '.'):
# left out, or null where the page reads by position. tests/test_examples.py walks every path the publisher's own
# builders write and fails on one that is neither kept by the shapes above nor named here.
OVERVIEW_LEFT_OUT = {
    'overview-day': ('stocks.r5d', 'stocks.r1m', 'stocks.fnet_5d', 'stocks.fnet_1m', 'stocks.fnet_3m',   # the 5D, 1M, 3M
                     'market.periods.5D', 'market.periods.1M', 'market.periods.3M',                       # period choices
                     'intraday.1h'),                                                                      # the 5D chart
    'overview-series': ('flow.foreign_buy', 'flow.foreign_sell',          # the Foreign Flow's Custom range (a time control)
                        'breadth_n'),                                     # read by no panel
}

# The Watchlist's opening view (module docstring): the example's list, as the user chose it (2026-11-21, "Untuk
# watchlist oke, dengan rekomendasi kamu": one list of the LQ45 members), the list's id on the page, and the fields of
# watchlist-stocks the page reads, at every depth (the shapes above; a field not named is left out). The per-stock
# columns are cut to the list's members, each value kept only where it holds no object.
WATCHLIST_LIST = ('INDEX', 'LQ45')                      # Stock_List (list_kind, code), as overview-meta `lists` names it
WATCHLIST_LIST_ID = 'example-lq45'
WATCHLIST_STOCKS = 'watchlist-stocks'
WATCHLIST_SHAPE = {'schema': KEEP, 'prices_through': KEEP, 'broker_through': KEEP, 'event_days': KEEP, 'dates': KEEP,
                   'catalog': [{'key': KEEP, 'name': KEEP, 'short': KEEP, 'note': KEEP, 'family': KEEP, 'unit': KEEP,
                                'date': KEEP, 'signed': KEEP}],
                   'default': KEEP, 'events_loaded': KEEP}
WATCHLIST_COLUMNS = ('ticker', 'name', 'sector', 'last', 'r1d', 'r1m', 'trend')   # one value per stock (watchlist.py)
# what the publisher writes and the opening view does not show (tests/test_examples.py walks every path), by rule: every
# indicator that is not one of the file's own default ones (null per stock: adding an indicator is a click), and the
# corporate actions of a stock outside the list (`events` is keyed by ticker: only the members' are kept, each event
# a flat [kind, date, role] or dropped)
WATCHLIST_LEFT_OUT = ()
ISO_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


def flat(value):
    """Whether a JSON value holds no object at any depth (an explicit stack)."""
    stack = [value]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            return False
        if isinstance(x, list):
            stack.extend(x)
    return True


def kept(value, shape):
    """value cut to shape (the comment above): the named keys only, at every depth; another shape than named is None."""
    if shape == KEEP:
        return value if flat(value) else None
    if isinstance(shape, list):
        return [kept(x, shape[0]) for x in value] if isinstance(value, list) else None
    if not isinstance(value, dict):
        return None
    if '*' in shape:
        return {k: kept(x, shape['*']) for k, x in value.items()}
    return {k: kept(value[k], s) for k, s in shape.items() if k in value}


def messages(label):
    return {
        'EXAMPLE_NOT_READY': f'The example of the {label} is not ready yet. Sign in or upgrade to use the {label} itself.',
        'EXAMPLE_UNAVAILABLE': f'The example of the {label} could not be read right now. Try again in a minute.',
        'EXAMPLE_INVALID_NAME': f'That is not a file of the {label} example. GET the example\'s index for its files.',
        'EXAMPLE_INVALID_SHA': 'The sha parameter must be the 64 lowercase hexadecimal characters of the file\'s sha256 '
                               'as the example\'s index lists it; leave it out to get the current file.',
        'EXAMPLE_FILE_NOT_FOUND': f'This file is not part of the {label} example. GET the example\'s index for its files.',
        'EXAMPLE_FILE_REPLACED': f'The {label} example was made again. Read its index again and ask for the file with '
                                 'its new sha.',
    }


def encode(doc):
    """The publisher's encoding (apps/terminal-publisher/publisher.py encode): compact JSON, gzip level 9, mtime 0."""
    body = gzip.compress(json.dumps(doc, separators=(',', ':'), allow_nan=False).encode(), compresslevel=9, mtime=0)
    return body, hashlib.sha256(body).hexdigest()


def overview_view(meta, series, day):
    """The three files of the Market Overview's opening view on the day's date, trimmed to it (module docstring)."""
    d = day['date']
    end = max((i for i, x in enumerate(series['dates']) if x <= d), default=-1)
    lo = max(0, end + 1 - OVERVIEW_SESSIONS)
    cut = lambda a: list(a[lo:end + 1]) if end >= 0 and isinstance(a, list) and flat(a) else []
    s = {k: kept(series[k], KEEP) for k in SERIES_KEYS if k in series}
    s['dates'] = cut(series['dates'])
    head = max(0, len(s['dates']) - OVERVIEW_INDEX_SESSIONS)         # a line's points before its own window: null
    line = lambda a: [None if k < head else v for k, v in enumerate(cut(a))]
    for k in ('index', 'sector'):
        s[k] = {name: line(v) for name, v in (series.get(k) or {}).items()} if isinstance(series.get(k) or {}, dict) else {}
    for k in ('above_ema50', 'above_ema200'):
        s[k] = cut(series.get(k) or [])
    market = day.get('market') if isinstance(day.get('market'), dict) else None
    flow = series.get('flow') if isinstance(series.get('flow'), dict) else {}
    fe = (len(flow['dates']) - 1 - flow['dates'][::-1].index(market['date'])
          if market and market.get('date') in (flow.get('dates') or []) else -1)
    flo = max(0, fe + 1 - OVERVIEW_FLOW_SESSIONS)
    s['flow'] = {k: list((flow.get(k) or [])[flo:fe + 1]) if fe >= 0 and flat(flow.get(k) or []) else [] for k in FLOW_KEYS}
    m = kept(meta, META_SHAPE)
    m['dates'] = [d]
    out = kept(day, DAY_SHAPE)
    out['market'] = None if market is None else {
        **{k: kept(market.get(k), KEEP) for k in MARKET_KEYS},
        'periods': {OVERVIEW_PERIOD: kept((market.get('periods') or {}).get(OVERVIEW_PERIOD), PERIOD_SHAPE)}}
    stocks = day['stocks']
    n = len(stocks['i'])
    out['stocks'] = {k: (list(v) if k in STOCK_KEYS and flat(v) else [None] * n) for k, v in stocks.items()}
    bars = (day.get('intraday') or {}).get(OVERVIEW_BARS)
    out['intraday'] = {OVERVIEW_BARS: kept(bars, BARS_SHAPE)} if bars is not None else {}
    return [('overview-meta', m, len(m['stocks']['ticker'])), ('overview-series', s, len(s['dates'])),
            (f'overview-day-{d}', out, n)]


class ExampleDataError(Exception):
    """The live publication cannot give the example as the user set it: `reason` is a fixed word (no value of the data),
    logged with the class; the example answers EXAMPLE_UNAVAILABLE (fail closed: never another list or date)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def list_members(meta, kind, code):
    """The members of the stock list (kind, code) as the Market Overview publishes them (overview-meta `lists`, from
    Stock_List_Member when the publisher ran), or ExampleDataError: no such list, more than one, or no usable members."""
    lists = meta.get('lists') if isinstance(meta, dict) else None
    found = [x for x in lists if isinstance(x, dict) and x.get('kind') == kind and x.get('code') == code] \
        if isinstance(lists, list) else []
    if len(found) != 1:
        raise ExampleDataError('list_missing' if not found else 'list_twice')
    members = found[0].get('members')
    if not (isinstance(members, list) and members and all(isinstance(t, str) for t in members)
            and len(set(members)) == len(members)):
        raise ExampleDataError('list_members_invalid')
    return list(members)


def watchlist_view(stocks, meta):
    """The Watchlist's opening view on the publication's price date (module docstring): watchlist-stocks cut to the
    example list's members, and watchlist-lists, that one list -> [(name, doc, rows)]."""
    kind, code = WATCHLIST_LIST
    members = list_members(meta, kind, code)
    tickers = stocks.get('ticker') if isinstance(stocks, dict) else None
    if not isinstance(tickers, list) or not ISO_DATE.fullmatch(str(stocks.get('prices_through'))):
        raise ExampleDataError('stocks_unreadable')
    at = {t: i for i, t in enumerate(tickers) if isinstance(t, str)}
    if any(t not in at for t in members):
        raise ExampleDataError('member_outside_file')
    keep, n = [at[t] for t in members], len(tickers)

    def pick(column):
        """The members' values of a per-stock column; a column of another length, or a value holding an object: null."""
        if not isinstance(column, list) or len(column) != n:
            return [None] * len(keep)
        return [column[i] if flat(column[i]) else None for i in keep]
    out = kept(stocks, WATCHLIST_SHAPE)
    out.update({k: pick(stocks.get(k)) for k in WATCHLIST_COLUMNS})
    default = out['default'] if isinstance(out.get('default'), list) else []
    values = stocks.get('values') if isinstance(stocks.get('values'), dict) else {}
    out['values'] = {k: (pick(v) if k in default else [None] * len(keep)) for k, v in values.items()}
    events = stocks.get('events') if isinstance(stocks.get('events'), dict) else {}
    out['events'] = {t: [e for e in events[t] if isinstance(e, list) and flat(e)]
                     for t in members if isinstance(events.get(t), list)}
    answer = {'lists': [{'id': WATCHLIST_LIST_ID, 'name': code, 'position': 0, 'indicators': None,
                         'tickers': [{'ticker': t, 'position': i} for i, t in enumerate(members)]}], 'limits': []}
    return [(WATCHLIST_STOCKS, out, len(members)), ('watchlist-lists', answer, 1)]


class Refused(Exception):
    """A source cannot give its example now: `answer` is the refusal to send (from app/pages.py, or this module's)."""

    def __init__(self, answer):
        super().__init__('example refused')
        self.answer = answer


# Lab gap "the stored examples" (FUTURE_PLAN.md "Before the first lab item or tab"; ERRORS M527 records-promotion-3; the
# user's go 2026-11-22, "Celah lab: go untuk butir 1-7 ... OK fix it"): a stored example was cut by the release file as it
# stood at its capture, then served as stored, so an item put at the lab stage later stayed in it for every visitor and
# free account. Each stored file is now held to the release file this process runs (released_view, once per read): a
# list of items (a catalog: the Backtest's Flow indicators, the Screener's indicators, metrics and fundamentals) keeps
# what the narrowest principal sees (catalog.tab_list with no principal: a lab entry and an access 'admin' entry left
# out), a preset not released or reading an entry left out is left out, and a file that still names an item the release
# file does not hold as released (a request, a screen, a result) withholds the tab's example: EXAMPLE_UNAVAILABLE, the
# page's lock as without an example, until the example is captured again. Derived from the release file (every registry
# id has an entry, tests/test_releases.py), so a new item or kind needs no change here.
def _item_lists():
    from .screener import ITEM_LISTS                     # the Screener's lists; screener.py does not import this module
    return (('flow_indicators', ('flow_indicator',), lambda e: 'flow_indicator'),) + tuple(ITEM_LISTS)


def not_released():
    """Every id the release file holds at a stage other than released, of every kind."""
    return frozenset(e['id'] for kind in releases.KINDS for e in releases.entries(kind) if e.get('stage') == releases.LAB)


def _names(value, ids, found):
    """The ids of `ids` a document reads: where the grammars hold an item (a reference {kind, indicator|metric|type|attr},
    screener.REFERENCE_KEYS, the keys the workers' item walks read: backtest-worker grammar.ts ITEM_KEY, screener-worker
    run.ts definitionItems; an indicator or metric named without a kind, as the Backtest's exit lines {indicator,
    output}), a screen's preset, or an entry's own id (a catalog entry, a preset, a preset's items). Free text (a name, a
    synonym, a description) is no reference; 'type' and 'attr' are one only beside a kind ('type' is also a value's)."""
    from .screener import REFERENCE_KEYS
    if isinstance(value, list):
        for v in value:
            _names(v, ids, found)
    elif isinstance(value, dict):
        keys = ('id', 'preset', 'indicator', 'metric') + (REFERENCE_KEYS if isinstance(value.get('kind'), str) else ())
        found |= {value[k] for k in keys if isinstance(value.get(k), str) and value[k] in ids}
        for v in value.values():
            _names(v, ids, found)
    return found


def released_doc(doc, lab):
    """(the document as the narrowest principal sees it under this release file, the ids of `lab` it still names)."""
    from .catalog import tab_list
    from .screener import PRESET_KIND, preset_reads
    if not isinstance(doc, dict):
        return doc, _names(doc, lab, set())
    out, gone = doc, set()
    for name, kinds, fallback in _item_lists():
        if isinstance(doc.get(name), list):
            kept, left = tab_list(None, doc[name], kinds, fallback, False)
            if left:
                out, gone = {**out, name: kept}, gone | left
    if isinstance(doc.get('presets'), list):
        presets = [x for x in doc['presets'] if not (isinstance(x, dict) and isinstance(x.get('id'), str)) or (
            releases.stage_of(PRESET_KIND, x['id']) != releases.LAB and not preset_reads(x, gone | lab))]
        if len(presets) != len(doc['presets']):
            out = {**out, 'presets': presets}
    return out, _names(out, lab, set())


def released_view(tab, index, bodies):
    """(index, bodies) of a stored tab held to the release file (the comment above); a body that changes is encoded
    again (its sha256 and bytes in the index with it). Raises ExampleDataError('item_not_released') when a file still
    names an item that is not released; logs the ids (item ids, no data value)."""
    lab = not_released()
    if index is None or not lab:
        return index, bodies
    named, files, out = set(), dict(index['files']), {}
    for name, (sha, body) in bodies.items():
        doc = json.loads(gzip.decompress(body))
        view, left = released_doc(doc, lab)
        named |= left
        if view is doc:
            out[name] = (sha, body)
            continue
        raw = gzip.compress(json.dumps(view, separators=(',', ':'), ensure_ascii=False).encode(), 6, mtime=0)
        new = hashlib.sha256(raw).hexdigest()
        out[name] = (new, raw)
        files[name] = {**files[name], 'sha256': new, 'bytes': len(raw)}
    if named:
        logger.warning(json.dumps({'event': 'example_withheld', 'tab': tab, 'not_released': sorted(named)[:20]}))
        raise ExampleDataError('item_not_released')
    return {**index, 'files': files}, out


class Stored:
    """One tab's rows of edge_bff.example_files, kept in memory (module docstring)."""

    def __init__(self, store, tab, clock):
        self.store, self.tab, self.clock = store, tab, clock
        self.kept = None                                  # {at, index, bodies: {name: (sha256, bytes)}}
        self.lock = asyncio.Lock()

    def read(self, held):
        """The tab's rows now: (index, bodies), the bodies read only for a sha256 not held already (blocking)."""
        with self.store.connect() as c:
            rows = c.execute(LIST_SQL, (self.tab,)).fetchall()
            want = [r['sha256'] for r in rows if held.get(r['name'], (None,))[0] != r['sha256']]
            fresh = {r['name']: (r['sha256'], bytes(r['body']))
                     for r in c.execute(BODIES_SQL, (self.tab, want)).fetchall()} if want else {}
        bodies = {}
        for r in rows:
            sha, body = fresh.get(r['name']) or held[r['name']]
            if sha != r['sha256'] or hashlib.sha256(body).hexdigest() != sha or len(body) != r['bytes']:
                raise ValueError(f'example file {self.tab}/{r["name"]} does not match its sha256')
            bodies[r['name']] = (sha, body)
        if not rows:
            return None, {}
        days = sorted({r['as_of'] for r in rows})
        index = {'finished_at': max(r['made_at'] for r in rows).isoformat(), 'as_of': days[-1],
                 'files': {r['name']: {'sha256': r['sha256'], 'bytes': r['bytes'], 'rows': r['rows'], 'as_of': r['as_of']}
                           for r in rows}}
        return released_view(self.tab, index, bodies)

    async def current(self, p):
        """The kept example, read again when older than REFRESH_SECONDS; a failed read keeps the last good one. Raises
        when nothing was ever read and the read fails."""
        kept = self.kept
        if kept is not None and self.clock() - kept['at'] < REFRESH_SECONDS:
            return kept
        async with self.lock:
            kept = self.kept
            if kept is not None and self.clock() - kept['at'] < REFRESH_SECONDS:
                return kept
            try:
                index, bodies = await asyncio.to_thread(self.read, kept['bodies'] if kept else {})
            except Exception as e:  # noqa: BLE001 - logged by class; the last good copy stands
                logger.warning(json.dumps({'event': 'example_read_failed', 'tab': self.tab, 'error': failure_class(e)}))
                if kept is None:
                    raise
                kept['at'] = self.clock()                 # ask again after REFRESH_SECONDS, not on every request
                return kept
            self.kept = {'at': self.clock(), 'index': index, 'bodies': bodies}
            return self.kept


class OverviewLatest:
    """The Market Overview's opening view on its latest market date, from the live publication (module docstring)."""

    def __init__(self, pages, not_ready):
        self.pages, self.not_ready = pages, not_ready
        self.made = None                                  # (the live files' sha256s, the example made of them)
        self.lock = asyncio.Lock()

    async def current(self, p):
        pages = self.pages
        if not pages.settings.terminal_url:
            raise Refused(self.not_ready())
        sent = terminal_access.headers(pages.settings, p)   # the principal's own refusals first, caches or not
        data = await pages.index(p, sent)
        if data is None:
            raise RuntimeError('the Market Overview index could not be read')
        files = data['files']
        days = sorted(n for n in files if OVERVIEW_DAY.fullmatch(n))
        if not days or 'overview-meta' not in files or 'overview-series' not in files:
            return {'index': None, 'bodies': {}}
        names = ('overview-meta', 'overview-series', days[-1])
        key = tuple(files[n].get('sha256') for n in names)
        if self.made is not None and self.made[0] == key:
            return self.made[1]
        async with self.lock:
            if self.made is not None and self.made[0] == key:
                return self.made[1]
            docs = []
            for n in names:
                body, failed = await pages.body_of(p, sent, n, files[n].get('sha256'), files[n])
                if failed is not None:
                    raise Refused(failed)
                docs.append(json.loads(gzip.decompress(body)))
            trimmed = overview_view(*docs)
            bodies, entries = {}, {}
            for name, doc, rows in trimmed:
                body, sha = encode(doc)
                bodies[name] = (sha, body)
                entries[name] = {'sha256': sha, 'bytes': len(body), 'rows': rows, 'as_of': docs[2]['date']}
            kept = {'index': {'finished_at': data.get('finished_at'), 'as_of': docs[2]['date'], 'files': entries},
                    'bodies': bodies}
            self.made = (key, kept)
            return kept


class WatchlistLatest:
    """The Watchlist's opening view on its latest price date, from the live publications (module docstring): the
    Watchlist's watchlist-stocks and the Market Overview's overview-meta (the list's members), each read through its
    page relay for the principal (app/pages.py), as OverviewLatest reads its files."""

    def __init__(self, watchlist, overview, not_ready):
        self.watchlist, self.overview, self.not_ready = watchlist, overview, not_ready
        self.made = None                                  # (the two live files' sha256s, the example made of them)
        self.lock = asyncio.Lock()

    async def current(self, p):
        if not self.watchlist.settings.terminal_url:
            raise Refused(self.not_ready())
        sent = terminal_access.headers(self.watchlist.settings, p)   # the principal's own refusals first
        reads = ((self.watchlist, WATCHLIST_STOCKS), (self.overview, 'overview-meta'))
        entries = []
        for pages, name in reads:
            data = await pages.index(p, sent)
            if data is None:
                raise RuntimeError(f'the {pages.family} index could not be read')
            if name not in data['files']:
                return {'index': None, 'bodies': {}}
            entries.append((data, data['files'][name]))
        key = tuple(e.get('sha256') for _, e in entries)
        if self.made is not None and self.made[0] == key:
            return self.made[1]
        async with self.lock:
            if self.made is not None and self.made[0] == key:
                return self.made[1]
            docs = []
            for (pages, name), (_, e) in zip(reads, entries):
                body, failed = await pages.body_of(p, sent, name, e.get('sha256'), e)
                if failed is not None:
                    raise Refused(failed)
                docs.append(json.loads(gzip.decompress(body)))
            stocks, meta = docs
            as_of = stocks.get('prices_through') if isinstance(stocks, dict) else None
            bodies, files = {}, {}
            for name, doc, rows in watchlist_view(stocks, meta):
                body, sha = encode(doc)
                bodies[name] = (sha, body)
                files[name] = {'sha256': sha, 'bytes': len(body), 'rows': rows, 'as_of': as_of}
            kept = {'index': {'finished_at': entries[0][0].get('finished_at'), 'as_of': as_of, 'files': files},
                    'bodies': bodies}
            self.made = (key, kept)
            return kept


class Examples:
    """The example of every tab of TABS (module docstring)."""

    def __init__(self, store, overview, watchlist, clock=time.monotonic):
        self.store, self.overview, self.watchlist, self.clock = store, overview, watchlist, clock

    def routes(self, app, auth):
        for tab, label in TABS.items():
            self.tab_routes(app, auth, tab, label)

    def tab_routes(self, app, auth, tab, label):
        text = messages(label)
        # before the kept files (module docstring); a tab whose example reads terminal-api for the principal (LATEST, the
        # Overview and the Watchlist) passes the guard of every route that calls it: a request carrying a header edge-bff
        # sets itself is refused 400 (terminal_access.guard; the example-mode re-check, ERRORS M527). A stored tab reads
        # the database only.
        base = auth.need(f'{tab}.example', guests=True)
        need = terminal_access.guard(base) if tab in LATEST else base

        def failure(code, status, details=None):
            return JSONResponse(status_code=status, content={'error': {
                'code': code, 'message': text[code], 'details': {'tab': tab, **(details or {})}}})

        not_ready = lambda: failure('EXAMPLE_NOT_READY', 404)
        latest = {'overview': lambda: OverviewLatest(self.overview, not_ready),
                  'watchlist': lambda: WatchlistLatest(self.watchlist, self.overview, not_ready)}
        assert set(latest) == LATEST, 'a LATEST tab needs its source here'
        source = latest[tab]() if tab in LATEST else Stored(self.store, tab, self.clock)

        async def kept_or_failure(p):
            try:
                kept = await source.current(p)
            except Refused as refused:
                return None, refused.answer
            except Refusal:
                # the principal's own refusal (terminal_access.headers: a Terminal limit of 0, the guest's client): the
                # app's handler answers it with its own code and way on, as app/pages.py lets it (the example-mode
                # checker, ERRORS M527; AGENTS.md "Gates and evidence" (d))
                raise
            except Exception as e:  # noqa: BLE001 - the class only; a driver error may carry connection details
                reason = {'reason': e.reason} if isinstance(e, ExampleDataError) else {}
                logger.warning(json.dumps({'event': 'example_unavailable', 'tab': tab, 'error': failure_class(e), **reason}))
                return None, failure('EXAMPLE_UNAVAILABLE', 503)
            if kept['index'] is None:
                return None, failure('EXAMPLE_NOT_READY', 404)
            return kept, None

        async def example_index(p=Depends(need)):
            kept, refused = await kept_or_failure(p)
            if refused is not None:
                return refused
            return JSONResponse(kept['index'], headers={'Cache-Control': 'private, no-cache'})

        async def example_file(name: str, request: Request, sha: str = '', p=Depends(need)):
            if not NAME.fullmatch(name):
                return failure('EXAMPLE_INVALID_NAME', 400, {'name': name[:64]})
            if sha and not SHA.fullmatch(sha):
                return failure('EXAMPLE_INVALID_SHA', 400, {'sha': sha[:80]})
            if sha and request.headers.get('if-none-match') == f'"{sha[:32]}"':
                # the capability was checked (the dependency) and the URL names the content: the browser's copy stands
                return Response(status_code=304, headers={'ETag': f'"{sha[:32]}"', 'Cache-Control': 'private, no-cache'})
            kept, refused = await kept_or_failure(p)
            if refused is not None:
                return refused
            held = kept['bodies'].get(name)
            if held is None:
                return failure('EXAMPLE_FILE_NOT_FOUND', 404, {'name': name})
            current, body = held
            if sha and sha != current:
                return failure('EXAMPLE_FILE_REPLACED', 409, {'name': name, 'sha256': current})
            if not sha and request.headers.get('if-none-match') == f'"{current[:32]}"':
                return Response(status_code=304, headers={'ETag': f'"{current[:32]}"', 'Cache-Control': 'private, no-cache'})
            return Response(body, media_type='application/json', headers={
                'Content-Encoding': 'gzip', 'ETag': f'"{current[:32]}"', 'Cache-Control': 'private, no-cache'})

        app.get(f'/api/v1/examples/{tab}/index', name=f'{tab}_example_index')(example_index)
        app.get(f'/api/v1/examples/{tab}/file/{{name}}', name=f'{tab}_example_file')(example_file)
