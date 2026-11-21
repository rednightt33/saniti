"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527).

A visitor who is not signed in and the free plan see each data page as it opens, with the data of one past date (30
October 2026 for the Radar, the Watchlist, the Screener and the Backtest), and every click asks to sign in or to
upgrade: "kayak semacam static HTML di hari tersebut saja". This module builds the files of a page's opening view for
that date, in the shape the page reads from its live route, and refuses any file that names a later date. The capture
job (verification/edge_multiuser/example_mode/capture_job.py) writes them to edge_bff.example_files (migration
20261121_001), which edge-bff serves (apps/edge-bff/app/examples.py). No publication runs this module.

  radar      radar-meta, radar-days, radar-board-<as_of>: what the page reads when it opens (src/app.ts boot); the date
             picker and a filter's page are clicks, so the older boards and radar-f-<filter> are not part of the example
  watchlist  watchlist-stocks of as_of cut to the example list's stocks (the LQ45 members on that date, point in time:
             Stock_List_Member_History; before its first capture, the earliest recorded members when none changed
             since, members_on) and its default indicators (the other indicators' values null: adding one is a
             click), without the upcoming corporate actions (they are dates after as_of by nature: the example leaves
             them out, the user told); watchlist-lists, the one list in the shape of GET /api/v1/watchlist/lists. No
             watchlist-radar: it goes only with radar.view, which the example's plans do not hold
  backtest   the page's default setup (MAPI, single stock) over the year to as_of, run once by the real Backtest
             worker: backtest-request (built by the page's own code, backtest_request.ts, on a part of the cut
             catalog: built_on must be found in it as it is, outside), backtest-result (the worker's result as
             edge-bff serves a single run), backtest-catalog (the worker's catalog from the period's first day to
             as_of, the Flow indicators every plan may read) and backtest-bars-<ticker> (the ticker's final daily
             prices of the period: the chart; no broker file, the run's condition tracks stand in)

Each builder stops (ExampleError) rather than give another example than the approved one: the newest result date must be
as_of itself, never an earlier one the data happens to end on.
"""
from __future__ import annotations

import gzip
import json
import re

import radar
import watchlist
from publisher import PRICE_ACTION_TYPES, encode

ISO = re.compile(r'(?<![0-9])([0-9]{4}-[0-9]{2}-[0-9]{2})(?![0-9])')
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')                 # edge_bff.example_files.name (example_files_name)
MAX_BYTES = 8 * 1024 * 1024                                     # example_files_bytes


class ExampleError(RuntimeError):
    """The data does not give the example the user approved; the job stops and writes nothing."""


def dates_after(doc, as_of):
    """Every place a JSON document names an ISO date after as_of, as sorted [(path, date)]: in a value or an object key,
    at any depth (an explicit stack: no document is too deep to check)."""
    out, stack = [], [('$', doc)]
    while stack:
        path, x = stack.pop()
        if isinstance(x, dict):
            for k, v in x.items():
                out += [(f'{path}.{k} (key)', d) for d in ISO.findall(str(k)) if d > as_of]
                stack.append((f'{path}.{k}', v))
        elif isinstance(x, list):
            stack.extend((f'{path}[{i}]', v) for i, v in enumerate(x))
        elif isinstance(x, str):
            out += [(path, d) for d in ISO.findall(x) if d > as_of]
    return sorted(out)


def radar_files(conn, names, lists, as_of, stream=None):
    """The Radar's opening view on as_of -> [(name, doc, rows, day)]: radar-meta, radar-days and the board of as_of."""
    built = {n: (doc, rows, day) for n, doc, rows, day in radar.build(conn, names, lists, stream=stream, as_of=as_of)}
    if 'radar-days' not in built:
        raise ExampleError(f'the Radar has no result date up to {as_of}')
    days = built['radar-days'][0]
    if days['dates'][-1] != as_of:
        raise ExampleError(f"the newest Radar result date up to {as_of} is {days['dates'][-1]}: {as_of} has no result")
    if days['prices_through'] != as_of:
        raise ExampleError(f"IHSG's newest final price up to {as_of} is {days['prices_through']}, not {as_of}")
    board = f'radar-board-{as_of}'
    if board not in built or not built[board][0]['rows']['filter']:
        raise ExampleError(f'{board} has no row under the current rule version')
    return [(n, *built[n]) for n in ('radar-meta', 'radar-days', board)]


# the Watchlist's example list (the user, 2026-11-21: "Untuk watchlist oke, dengan rekomendasi kamu": one list of the
# LQ45 members with the default indicators), its members on as_of as recorded then (pit_valid_*, the table's own rule)
WATCHLIST_LIST = ('INDEX', 'LQ45')
# every recorded membership row of the list: the members on as_of are the rows that cover it (pit_valid_from <= as_of <
# pit_valid_to). The history starts at the list's first capture (2026-11-09, migration 20261109_001: "Holds nothing
# before the first capture"), so for an earlier as_of no row covers it: the earliest recorded members are taken when no
# change was recorded since (an index list changes only at its periodic review; ERRORS M527), else the capture stops.
MEMBERS_SQL = ('SELECT h."Ticker", h.pit_valid_from::text, h.pit_valid_to::text FROM public."Stock_List_Member_History" '
               'AS h JOIN public."Stock_List" AS l USING (list_key) WHERE l.list_kind = %s AND l.code = %s ORDER BY 2, 1')


def members_on(rows, as_of, code):
    """(members, basis) of the list on as_of from its MEMBERS_SQL rows (comment above), or ExampleError."""
    covering = sorted(t for t, a, b in rows if a <= as_of and (b is None or b > as_of))
    if covering:
        return covering, f'recorded for {as_of}'
    if not rows:
        raise ExampleError(f'no {code} member is recorded (Stock_List_Member_History)')
    first = min(a for _, a, _ in rows)
    if first <= as_of:
        raise ExampleError(f'no {code} member covers {as_of} although its history starts on {first}')
    changed = [t for t, a, b in rows if a != first or b is not None]
    if changed:
        raise ExampleError(f'{code} changed after its first recording on {first} ({changed[:5]}): its members on '
                           f'{as_of} cannot be known')
    return sorted(t for t, _, _ in rows), f'earliest recorded ({first}), unchanged since; none recorded for {as_of}'
# the list the page reads (watchlist/src/types.ts ListsAnswer): one list, its stocks in order, the default indicators
EXAMPLE_LIST_ID = 'example-lq45'


def watchlist_files(conn, names, lists, as_of, stream=None):
    """The Watchlist's opening view on as_of -> [(name, doc, rows, day)]: watchlist-stocks of the example list and
    watchlist-lists (module docstring)."""
    run = lambda sql, params: conn.execute(sql, params).fetchall()
    docs = watchlist.build(run, as_of=as_of)
    if docs is None:
        raise ExampleError(f'the Watchlist has no complete price date up to {as_of}')
    s = docs['watchlist-stocks']
    if s['prices_through'] != as_of or s['broker_through'] != as_of:
        raise ExampleError(f"the Watchlist's price date up to {as_of} is {s['prices_through']} and its broker date "
                           f"{s['broker_through']}: {as_of} is not complete")
    kind, code = WATCHLIST_LIST
    members, basis = members_on([tuple(r) for r in run(MEMBERS_SQL, (kind, code))], as_of, code)
    NOTES.append(f'{code} members: {len(members)}, {basis}')
    at = {t: i for i, t in enumerate(s['ticker'])}
    outside = [t for t in members if t not in at]
    if outside:
        raise ExampleError(f'{code} members on {as_of} outside the universe of the file: {outside[:5]}')
    keep = [at[t] for t in members]
    pick = lambda a: [a[i] for i in keep]
    doc = {**s, 'ticker': members, 'name': pick(s['name']), 'sector': pick(s['sector']), 'last': pick(s['last']),
           'r1d': pick(s['r1d']), 'r1m': pick(s['r1m']), 'trend': pick(s['trend']),
           'values': {k: (pick(v) if k in s['default'] else [None] * len(keep)) for k, v in s['values'].items()},
           'events': {}, 'events_loaded': None}
    answer = {'lists': [{'id': EXAMPLE_LIST_ID, 'name': code, 'position': 0, 'indicators': None,
                         'tickers': [{'ticker': t, 'position': i} for i, t in enumerate(members)]}], 'limits': []}
    return [('watchlist-stocks', doc, len(members), as_of), ('watchlist-lists', answer, 1, as_of)]


# ---- the Backtest ---------------------------------------------------------------------------------------------------
BARS_SQL = ('SELECT date::text, open::float8, high::float8, low::float8, close::float8, volume::float8 '
            'FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = %s AND timeframe = \'Daily\' AND is_final '
            'AND date BETWEEN %s AND %s ORDER BY date')
# a share-count change on or after the period's first day: the page and the worker read prices adjusted for it, so the
# final daily prices would not be the chart's (the capture stops; publisher.PRICE_ACTION_TYPES)
BASIS_SQL = ('SELECT annotation_date::text, event_type FROM public.idx_event_annotation WHERE ticker = %s '
             "AND event_family = 'CORPORATE_ACTION' AND annotation_date_role = 'EX_DATE' AND event_type = ANY(%s) "
             'AND annotation_date >= %s ORDER BY 1')
# run stamps, not data dates (allowed after as_of by name, stored as the run reported them): the newest bar the
# worker's publication held when the run read it. The run itself reads for day t only data up to t (the look-ahead
# gate, AGENTS.md), and the page shows no such stamp.
RUN_STAMPS = {'backtest-result': ('$.meta.data_through',)}


def outside(part, whole, at='$'):
    """The first place where `part` is not found in `whole` as it is, or None: every key of an object with a value
    found in the same key's (recursively), every element of a list found in some element of the other list, any other
    value equal. The Backtest's request is built on a part of the catalog (backtest_request.ts: its lists cut to what the
    default setup names); found in the worker's cut catalog, the page builds the same request on the stored catalog."""
    if isinstance(part, dict):
        if not isinstance(whole, dict):
            return at
        for k, v in part.items():
            where = f'{at}.{k}' if k not in whole else outside(v, whole[k], f'{at}.{k}')
            if where:
                return where
        return None
    if isinstance(part, list):
        if not isinstance(whole, list):
            return at
        for i, v in enumerate(part):
            if all(outside(v, w) for w in whole):
                return f'{at}[{i}]'
        return None
    return None if part == whole and type(part) is type(whole) else at


def backtest_catalog(catalog, first, as_of):
    """The worker's catalog as the example's page reads it: from the period's first day to as_of (so the page's
    default period is that year), the broker date no later, the Flow indicators every plan may read."""
    flow = dict(catalog.get('flow') or {})
    if flow.get('data_through'):
        flow['data_through'] = min(flow['data_through'], as_of)
    return {**catalog, 'first_date': first, 'data_through': as_of, 'flow': flow,
            'flow_indicators': [f for f in catalog.get('flow_indicators') or [] if f.get('access') == 'all']}


def backtest_files(conn, names, lists, as_of, stream=None, request=None, run=None, catalog=None, built_on=None):
    """The Backtest's example -> [(name, doc, rows, day)] (module docstring). request: the page's own request
    (backtest_request.ts) built on built_on; run(request) -> the worker's result; catalog: the worker's catalog."""
    if request is None or run is None or catalog is None or built_on is None:
        raise ExampleError('the Backtest example needs the page\'s request, the catalog it was built on, the worker and '
                           'its catalog')
    q, t = request, (request.get('single') or {}).get('ticker')
    first, last = (q.get('period') or {}).get('from'), (q.get('period') or {}).get('to')
    if q.get('mode') != 'single' or not t or last != as_of or not first:
        raise ExampleError(f'the request is not a single run ending on {as_of}: {q.get("mode")} {t} {first}..{last}')
    where = outside(built_on, backtest_catalog(catalog, first, as_of))
    if where:
        raise ExampleError(f'the request was built on a catalog the worker\'s does not hold at {where}: build it again '
                           'on the worker\'s catalog (backtest_request.ts)')
    moved = conn.execute(BASIS_SQL, (t, list(PRICE_ACTION_TYPES), first)).fetchall()
    if moved:
        raise ExampleError(f'{t} changed its share basis on {[f"{d} {k}" for d, k in moved][:3]}: its prices on the '
                           'chart would need the adjustment the page applies')
    result = run(q)
    meta = (result or {}).get('meta') or {}
    days = (result or {}).get('dates') or []
    if result.get('schema_version') != 1 or meta.get('mode') != 'single' or meta.get('tickers') != [t]:
        raise ExampleError(f'the worker\'s answer is not a single run of {t}')
    if not days or days[0] < first or days[-1] != as_of:
        raise ExampleError(f"the run's days are {days[:1]}..{days[-1:]}, not {first}..{as_of}")
    if not [c for c in (result.get('events') or {}).get('conditions') or [] if c.get('ticker') == t]:
        raise ExampleError(f'the run has no condition track of {t}')
    rows = conn.execute(BARS_SQL, (t, first, as_of)).fetchall()
    if not rows or rows[-1][0] != as_of:
        raise ExampleError(f'{t} has no final daily price on {as_of}')
    col = lambda k: [r[k] for r in rows]
    bars = {'ticker': t, 'dates': col(0), 'o': col(1), 'h': col(2), 'l': col(3), 'c': col(4), 'v': col(5)}
    return [('backtest-catalog', backtest_catalog(catalog, first, as_of), len(catalog.get('tickers') or []), as_of),
            ('backtest-request', q, len(q['entry']['conditions']), as_of),
            ('backtest-result', result, len(days), as_of),
            (f'backtest-bars-{t.lower()}', bars, len(rows), as_of)]


BUILDERS = {'radar': radar_files, 'watchlist': watchlist_files, 'backtest': backtest_files}
NOTES: list[str] = []                       # what a builder took as given, for the capture job's log (no data value)


def stored(tab, files, as_of):
    """The rows of edge_bff.example_files for one tab, [(tab, name, as_of, rows, bytes, sha256, body)], each checked: a
    name of the tab's family, its day not after as_of, at most MAX_BYTES, and no date after as_of in the document as its
    stored bytes hold it."""
    out, seen = [], set()
    for name, doc, rows, day in files:
        if not (NAME.fullmatch(name) and name.startswith(f'{tab}-')) or name in seen:
            raise ExampleError(f'{name!r} is not a file name of the {tab} example, or comes twice')
        seen.add(name)
        late = [d for d in ISO.findall(name) + ([str(day)] if day is not None else []) if d > as_of]
        body, sha = encode(doc)
        stamps = set(RUN_STAMPS.get(name, ()))
        late += [f'{p}: {d}' for p, d in dates_after(json.loads(gzip.decompress(body)), as_of) if p not in stamps]
        if late:
            raise ExampleError(f'{name} names dates after {as_of}: {late[:3]}')
        if len(body) > MAX_BYTES:
            raise ExampleError(f'{name} is {len(body)} bytes, more than {MAX_BYTES}')
        out.append((tab, name, as_of, int(rows), len(body), sha, body))
    return out


def build(conn, tab, as_of, names, lists, stream=None, **extra):
    """The checked rows of one tab's example on as_of (an ISO date); extra: what a builder needs besides the database
    (the Backtest's request, worker and catalog)."""
    if tab not in BUILDERS:
        raise ExampleError(f'no example builder for the tab {tab!r}: {sorted(BUILDERS)}')
    return stored(tab, BUILDERS[tab](conn, names, lists, as_of, stream=stream, **extra), as_of)
