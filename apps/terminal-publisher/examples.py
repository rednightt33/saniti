"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527).

A visitor who is not signed in and the free plan see each data page as it opens, with the data of one past date (30
October 2026 for the Radar, the Watchlist, the Screener and the Backtest), and every click asks to sign in or to
upgrade: "kayak semacam static HTML di hari tersebut saja". This module builds the files of a page's opening view for
that date, in the shape the page reads from its live route, and refuses any file that names a later date. The capture
job (verification/edge_multiuser/example_mode/capture_job.py) writes them to edge_bff.example_files (migration
20261121_001), which edge-bff serves (apps/edge-bff/app/examples.py). No publication runs this module.

  radar   radar-meta, radar-days, radar-board-<as_of>: what the page reads when it opens (src/app.ts boot); the date
          picker and a filter's page are clicks, so the older boards and radar-f-<filter> are not part of the example

Each builder stops (ExampleError) rather than give another example than the approved one: the newest result date must be
as_of itself, never an earlier one the data happens to end on.
"""
from __future__ import annotations

import gzip
import json
import re

import radar
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


BUILDERS = {'radar': radar_files}


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
