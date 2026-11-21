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

Each builder stops (ExampleError) rather than give another example than the approved one: the newest result date must be
as_of itself, never an earlier one the data happens to end on.
"""
from __future__ import annotations

import gzip
import json
import re

import radar
import watchlist
from publisher import encode

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


BUILDERS = {'radar': radar_files, 'watchlist': watchlist_files}
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
        late += [f'{p}: {d}' for p, d in dates_after(json.loads(gzip.decompress(body)), as_of)]
        if late:
            raise ExampleError(f'{name} names dates after {as_of}: {late[:3]}')
        if len(body) > MAX_BYTES:
            raise ExampleError(f'{name} is {len(body)} bytes, more than {MAX_BYTES}')
        out.append((tab, name, as_of, int(rows), len(body), sha, body))
    return out


def build(conn, tab, as_of, names, lists, stream=None):
    """The checked rows of one tab's example on as_of (an ISO date)."""
    if tab not in BUILDERS:
        raise ExampleError(f'no example builder for the tab {tab!r}: {sorted(BUILDERS)}')
    return stored(tab, BUILDERS[tab](conn, names, lists, as_of, stream=stream), as_of)
