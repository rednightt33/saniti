"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527).

A visitor who is not signed in and the free plan see each data page as it opens, with the data of one past date (30
October 2026 for the Radar, the Screener and the Backtest), and every click asks to sign in or to upgrade: "kayak
semacam static HTML di hari tersebut saja". This module builds the files of a page's opening view for that date, in the
shape the page reads from its live route, and refuses any file that names a later date. The capture job
(verification/edge_multiuser/example_mode/capture_job.py) writes them to edge_bff.example_files (migration
20261121_001), which edge-bff serves (apps/edge-bff/app/examples.py). No publication runs this module. The Market
Overview and the Watchlist show the latest data instead (the user, 2026-11-21: "Untuk table watchlist nggak apa-apa
pakai data latest saja"): edge-bff trims the live publication itself, so nothing here builds them.

  radar      radar-meta, radar-days, radar-board-<as_of>: what the page reads when it opens (src/app.ts boot); the date
             picker and a filter's page are clicks, so the older boards and radar-f-<filter> are not part of the example;
             each file is cut to the board's opening view (radar_opening: the hits at the default level and gate, 20
             sessions of that setting's counts, no measure, no rule; radar-meta the names of the stocks the board shows
             and no stock list, reference_cut)
  backtest   the page's default setup (MAPI, single stock) over the year to as_of, run once by the real Backtest
             worker: backtest-request (built by the page's own code, backtest_request.ts, on a part of the cut
             catalog: built_on must be found in it as it is, outside), backtest-result (the worker's result as
             edge-bff serves a single run, without the run's stamp of the publication it read), backtest-catalog (the
             worker's catalog from the period's first day to as_of, its lists cut to what the request names and its
             Flow indicators to the released ones every plan may read, backtest_catalog) and backtest-bars-<ticker>
             (the ticker's final daily prices of the period: the chart; no broker file, the run's condition tracks
             stand in)

The reference data in a file of a past date (the example-mode checker, ERRORS M527): the tables of names, stock lists
and tickers hold today's rows, and the stock lists' history starts at their first capture (2026-11-09). A file keeps
only the reference entries its opening view reads (a list behind a click is left out, reference_cut). Where a list's
membership is the page's content (the Watchlist's LQ45), the history cannot give a date before its first capture (the
example-mode checker: the exchange's review of 2 November fell between 30 October and that capture), so that example
shows the latest data and today's members (apps/edge-bff/app/examples.py).

Each builder stops (ExampleError) rather than give another example than the approved one: the newest result date must be
as_of itself, never an earlier one the data happens to end on.
"""
from __future__ import annotations

import gzip
import json
import re

import radar
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


def strings_of(doc):
    """Every string a JSON document holds, as a value or an object key, at any depth (an explicit stack)."""
    out, stack = set(), [doc]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            out.update(k for k in x if isinstance(k, str))
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
        elif isinstance(x, str):
            out.add(x)
    return out


def reference_cut(meta, shown):
    """radar-meta as the example's opening view reads it (module docstring, "The reference data"): the names of the
    stocks the board shows (`shown`: the board's file) and no stock list (the universe menu is a click; the page opens on
    every stock, radar/src/app.ts isDefault)."""
    held = strings_of(shown)
    return {**meta, 'names': {t: n for t, n in meta['names'].items() if t in held}, 'lists': []}


# The Radar's opening view (apps/edge-bff/radar/src: in example mode the page draws only the board, renderRadar and
# drawKanban, at its defaults: every column at its default variant, the Standard level, the Broad gate, all stocks, the
# hits; its spark reads 20 sessions of that setting's counts). The other levels, gates, near misses, left stocks, the
# measures, the rules and the older days sit behind a click (a segment, the filter page, the date menu): the files keep
# none of them (the example-mode re-check, ERRORS M527).
RADAR_LEVEL, RADAR_GATE, RADAR_STATUS = 'standard', 'broad', 'hit'     # model.ts LEVELS[1] and levelOf; app.ts ST
RADAR_SESSIONS = 20                                                       # app.ts drawKanban: counts(..., di, 20)
RADAR_STOCK_KEYS = ('close', 'chg_1d', 'spark')                           # stockFacts: what a board card shows
RADAR_ROW_KEYS = ('filter', 'stock', 'level', 'gate', 'status', 'run_day', 'strong', 'sort_value', 'flag')  # a card's


def radar_shown_filters(meta):
    """The filter each board column opens on: its default variant, then the first by position (model.ts columns)."""
    by_column = {}
    for f in meta['filters']:
        by_column.setdefault(f['column'], []).append(f)
    return {min(fs, key=lambda f: (not f['default_variant'], f['position']))['id'] for fs in by_column.values()}


def radar_opening(meta, days, board, as_of):
    """(meta, days, board) cut to the board's opening view (the comment above): the board keeps the hits of the shown
    filters at the default level and gate, their stocks' card figures and no measure; the days keep the last
    RADAR_SESSIONS dates, that setting's counts and the gate cuts; the meta keeps no rule (reference_cut its names and
    lists). A field a card does not read is null where the page reads by position, left out otherwise."""
    shown, r = radar_shown_filters(meta), board['rows']
    keep = [i for i in range(len(r['filter'])) if r['filter'][i] in shown and r['level'][i] == RADAR_LEVEL
            and r['gate'][i] == RADAR_GATE and r['status'][i] == RADAR_STATUS]
    was = board['stocks']['ticker']
    tickers = sorted({was[r['stock'][i]] for i in keep})
    at_was, at = {t: k for k, t in enumerate(was)}, {t: k for k, t in enumerate(tickers)}
    rows = {k: ([v[i] for i in keep] if k in RADAR_ROW_KEYS else [None] * len(keep)) for k, v in r.items()}
    rows['stock'] = [at[was[r['stock'][i]]] for i in keep]
    stocks = {'ticker': tickers, **{k: [board['stocks'][k][at_was[t]] for t in tickers] for k in RADAR_STOCK_KEYS}}
    cut_board = {**board, 'stocks': stocks, 'rows': rows, 'measures': {'columns': [], 'values': [None] * len(tickers)}}
    end = days['dates'].index(as_of)
    lo = max(0, end + 1 - RADAR_SESSIONS)
    cut = lambda a: list(a[lo:end + 1])
    setting = f'{RADAR_LEVEL}/{RADAR_GATE}'
    cut_days = {**days, 'dates': cut(days['dates']), 'gate': {k: cut(v) for k, v in days['gate'].items()},
                'counts': {f: {setting: cut(c[setting])} for f, c in days['counts'].items() if f in shown and setting in c},
                'ihsg': [None] * (end + 1 - lo), 'boards': [as_of]}
    return reference_cut({**meta, 'rules': []}, cut_board), cut_days, cut_board


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
    meta, days, shown = radar_opening(built['radar-meta'][0], days, built[board][0], as_of)
    if not shown['rows']['filter']:
        raise ExampleError(f'{board} has no hit at the default level and gate: the opening view would be empty')
    return [('radar-meta', meta, *built['radar-meta'][1:]), ('radar-days', days, len(days['dates']), built['radar-days'][2]),
            (board, shown, len(shown['rows']['filter']), built[board][2])]


# ---- the Backtest ---------------------------------------------------------------------------------------------------
BARS_SQL = ('SELECT date::text, open::float8, high::float8, low::float8, close::float8, volume::float8 '
            'FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = %s AND timeframe = \'Daily\' AND is_final '
            'AND date BETWEEN %s AND %s ORDER BY date')
# a share-count change on or after the period's first day: the page and the worker read prices adjusted for it, so the
# final daily prices would not be the chart's (the capture stops; publisher.PRICE_ACTION_TYPES)
BASIS_SQL = ('SELECT annotation_date::text, event_type FROM public.idx_event_annotation WHERE ticker = %s '
             "AND event_family = 'CORPORATE_ACTION' AND annotation_date_role = 'EX_DATE' AND event_type = ANY(%s) "
             'AND annotation_date >= %s ORDER BY 1')
# the result's fields that stamp the publication the run read, not the run's data: left out of the stored copy (the
# example-mode checker, ERRORS M527: the newest bar of the worker's publication is a date after as_of, and the page
# reads none of them: backtest/src reads the result's meta.mode, warnings, duration_ms, trials and tickers). The run
# itself reads for day t only data up to t (the look-ahead gate, AGENTS.md).
RESULT_STAMPS = ('data_through',)


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
    """The worker's catalog from the period's first day to as_of (so the page's default period is that year), the
    broker date no later: the catalog the request's part must be found in (outside)."""
    flow = dict(catalog.get('flow') or {})
    if flow.get('data_through'):
        flow['data_through'] = min(flow['data_through'], as_of)
    return {**catalog, 'first_date': first, 'data_through': as_of, 'flow': flow}


def released_entries(entries, kind, releases):
    """A catalog's list of items as the live site shows it to a principal with no right and no lab item (edge-bff
    catalog.tab_list for p None: an entry marked access 'admin' left out, an id the release file does not list as
    released left out; an entry without a string id stays as it is)."""
    stage = {(i['kind'], i['id']): i['stage'] for i in releases['items']}
    return [e for e in entries if not (isinstance(e, dict) and isinstance(e.get('id'), str))
            or (e.get('access') != 'admin' and stage.get((kind, e['id'])) == 'released')]


def backtest_shown(cut, part, releases):
    """The stored backtest-catalog (module docstring): the cut catalog with its lists as the request's part names them
    (its ticker, the brokers its conditions name, no grouping: the pickers are clicks, and the tickers and groups of the
    tables are today's) and its Flow indicators as the narrowest principal sees them (released_entries; edge-bff
    tests/test_examples.py holds it to rights.catalog_for)."""
    return {**cut, 'tickers': list(part.get('tickers') or []), 'groupings': list(part.get('groupings') or []),
            'flow': {**(cut.get('flow') or {}), 'brokers': list((part.get('flow') or {}).get('brokers') or [])},
            'flow_indicators': released_entries(cut.get('flow_indicators') or [], 'flow_indicator', releases)}


def part_outside(built_on, catalog, first, as_of, releases):
    """Where the request's part is not found as it is (outside), or None: in the worker's catalog cut to the period (its
    ticker, brokers, dates and limits are the worker's), and in the stored catalog (backtest_shown: a Flow indicator
    the narrowest principal does not see is not shown there)."""
    cut = backtest_catalog(catalog, first, as_of)
    return outside(built_on, cut) or outside(built_on, backtest_shown(cut, built_on, releases))


def backtest_files(conn, names, lists, as_of, stream=None, request=None, run=None, catalog=None, built_on=None,
                   releases=None):
    """The Backtest's example -> [(name, doc, rows, day)] (module docstring). request: the page's own request
    (backtest_request.ts) built on built_on; run(request) -> the worker's result; catalog: the worker's catalog;
    releases: the release file."""
    if request is None or run is None or catalog is None or built_on is None or releases is None:
        raise ExampleError('the Backtest example needs the page\'s request, the catalog it was built on, the worker, '
                           'its catalog and the release file')
    q, t = request, (request.get('single') or {}).get('ticker')
    first, last = (q.get('period') or {}).get('from'), (q.get('period') or {}).get('to')
    if q.get('mode') != 'single' or not t or last != as_of or not first:
        raise ExampleError(f'the request is not a single run ending on {as_of}: {q.get("mode")} {t} {first}..{last}')
    cut = backtest_catalog(catalog, first, as_of)
    where = part_outside(built_on, catalog, first, as_of, releases)
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
    shown = backtest_shown(cut, built_on, releases)
    kept = {**result, 'meta': {k: v for k, v in meta.items() if k not in RESULT_STAMPS}}
    return [('backtest-catalog', shown, len(shown['tickers']), as_of),
            ('backtest-request', q, len(q['entry']['conditions']), as_of),
            ('backtest-result', kept, len(days), as_of),
            (f'backtest-bars-{t.lower()}', bars, len(rows), as_of)]


# ---- the Screener: the real worker's answer on its own input files cut at the date ---------------------------------------
# The Screener evaluates every stock at its newest bar and has no evaluation date of its own: its example is the
# screener-worker itself run on its input files as they stood at as_of (screener_capture.ts; apps/screener-worker/tests/
# example-capture.ts: every later price, action and broker day left out, no stock lists, as_of as the publication's
# time). The user: "screener juga oke"; brk52 "52W Breakout + Volume" matched no stock on 30 October, so the user chose
# (2026-11-21, EXEC.md: "A - masukan exec") a technical preset with matches that day: Golden Cross (23).
SCREENER_PRESET = 'golden'
# the catalog's lists of items and the release kinds of their ids (apps/edge-bff/app/screener.py ITEM_LISTS, METRIC_KINDS,
# REFERENCE_KEYS; tests/test_examples.py of edge-bff holds this copy to catalog_for)
SCREENER_METRIC_KINDS = ('flow_indicator', 'candle_pattern', 'screener_metric')
SCREENER_ITEM_LISTS = (('indicators', ('indicator',), lambda e: 'indicator'),
                       ('metrics', SCREENER_METRIC_KINDS, lambda e: 'flow_indicator' if e.get('kind') == 'flow' else 'screener_metric'),
                       ('fundamentals', SCREENER_METRIC_KINDS, lambda e: 'flow_indicator' if e.get('kind') == 'flow' else 'screener_metric'))
SCREENER_REFERENCE_KEYS = ('metric', 'indicator', 'type', 'attr')
# the item kinds a run may read: the released ids of each (the context the capture sends, as the Backtest's)
RUN_ALLOW_KINDS = ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric')


def released_allow(releases):
    """{kind: [released ids]} of the release file (apps/edge-bff/catalog/releases.json) for every kind a run reads."""
    return {k: sorted(i['id'] for i in releases['items'] if i['kind'] == k and i['stage'] == 'released') for k in RUN_ALLOW_KINDS}


def _reads_any(x, ids):
    if isinstance(x, list):
        return any(_reads_any(v, ids) for v in x)
    if isinstance(x, dict):
        if isinstance(x.get('kind'), str) and any(isinstance(x.get(k), str) and x[k] in ids for k in SCREENER_REFERENCE_KEYS):
            return True
        return any(_reads_any(v, ids) for v in x.values())
    return False


def narrowest_catalog(doc, releases):
    """The worker's catalog as the live site shows it to a principal holding screener.view with the released items and no
    right (edge-bff catalog_for(doc, (), released_allow, None)): an entry marked access 'admin' (a point-in-time Flow
    version) or not released is left out; a preset is kept when it is released, its items are all released (one without
    the worker's items keeps no counts) and it reads no entry left out."""
    stage = {(i['kind'], i['id']): i['stage'] for i in releases['items']}
    out, gone = dict(doc), set()
    for name, kinds, fallback in SCREENER_ITEM_LISTS:
        if not isinstance(doc.get(name), list):
            continue
        kept = []
        for e in doc[name]:
            i = e.get('id') if isinstance(e, dict) else None
            if isinstance(i, str):
                kind = next((k for k in kinds if (k, i) in stage), fallback(e))
                if e.get('access') == 'admin' or stage.get((kind, i)) != 'released':
                    gone.add(i)
                    continue
            kept.append(e)
        out[name] = kept
    if isinstance(doc.get('presets'), list):
        allow = released_allow(releases)
        held = lambda it: isinstance(it, dict) and isinstance(it.get('id'), str) and it['id'] in allow.get(it.get('kind'), ())
        presets = []
        for x in doc['presets']:
            if not (isinstance(x, dict) and isinstance(x.get('id'), str)):
                continue
            items = x.get('items')
            if isinstance(items, list):
                if not all(held(it) for it in items):
                    continue
            else:
                x = {**x, 'match_count': None, 'near_count': None}
            if stage.get(('screener_preset', x['id'])) != 'released':
                continue
            if gone and (_reads_any(x.get('definition'), gone) or any(isinstance(it, dict) and it.get('id') in gone for it in items or [])):
                continue
            presets.append(x)
        out['presets'] = presets
    return out


SCREENER_ROW_DATES = ('last_bar_date',)                          # a run row's dates (contract.ts Row)
SCREENER_CELL_DATES = ('eval_date', 'event_date', 'last_event_date')  # its cells' (contract.ts Cell)


def row_dates(row):
    """Every date a run row and its cells carry."""
    out = [row.get(k) for k in SCREENER_ROW_DATES]
    for c in row.get('cells') or []:
        if isinstance(c, dict):
            out += [c.get(k) for k in SCREENER_CELL_DATES]
    return out


def screener_files(conn, names, lists, as_of, stream=None, example=None, releases=None):
    """The Screener's example -> [(name, doc, rows, day)]: screener-catalog (narrowest_catalog), screener-universe,
    screener-screen (the preset the page opens: its id, name and definition) and screener-run (the worker's answer to
    it). example: screener_capture.ts's {catalog, universe, screen, run}; releases: the release file."""
    if example is None or releases is None:
        raise ExampleError("the Screener example needs the worker's answer (screener_capture.ts) and the release file")
    catalog, universe, run, screen = narrowest_catalog(example['catalog'], releases), example['universe'], example['run'], example['screen']
    for what, doc in (('catalog', catalog), ('universe', universe), ('run', run)):
        day = ((doc or {}).get('data') or {}).get('evaluation_date')
        if day != as_of:
            raise ExampleError(f"the worker's {what} is evaluated on {day}, not {as_of}")
    preset = next((x for x in catalog.get('presets') or [] if x.get('id') == SCREENER_PRESET), None)
    if preset is None:
        raise ExampleError(f'the catalog shown has no preset {SCREENER_PRESET} (not released, or it reads an item left out)')
    if screen.get('preset') != SCREENER_PRESET or screen.get('definition') != preset.get('definition'):
        raise ExampleError(f"the example's screen is not the preset {SCREENER_PRESET} of the catalog shown")
    if run.get('mode') != 'screen' or not isinstance(run.get('rows'), list):
        raise ExampleError(f"the worker's answer is not a screen: {run.get('mode')}")
    # the dates a row carries (apps/edge-bff/screener/src/core/contract.ts Row and Cell; the example-mode checker, ERRORS
    # M527: the check read a field the rows do not have, so it saw nothing): a row without its bar's date is refused, as
    # a check of nothing
    bare = sorted({str(r.get('ticker')) for r in run['rows'] if not isinstance(r.get('last_bar_date'), str)
                   or any(not (isinstance(c, dict) and 'eval_date' in c) for c in r.get('cells') or [])})
    if bare:
        raise ExampleError(f"the worker's rows carry no {SCREENER_ROW_DATES[0]} or cell eval_date: {bare[:3]}")
    late = sorted({r.get('ticker') for r in run['rows'] if any(str(d or '') > as_of for d in row_dates(r))})
    if late:
        raise ExampleError(f'rows evaluated after {as_of}: {late[:3]}')
    shown = {'preset': SCREENER_PRESET, 'name': preset.get('name'), 'definition': preset.get('definition')}
    return [('screener-catalog', catalog, len(catalog.get('presets') or []), as_of),
            ('screener-universe', universe, len(universe.get('rows') or []), as_of),
            ('screener-screen', shown, len(shown['definition'].get('conditions') or []), as_of),
            ('screener-run', run, len(run['rows']), as_of)]


BUILDERS = {'radar': radar_files, 'backtest': backtest_files, 'screener': screener_files}
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


def build(conn, tab, as_of, names, lists, stream=None, **extra):
    """The checked rows of one tab's example on as_of (an ISO date); extra: what a builder needs besides the database
    (the Backtest's request, worker and catalog)."""
    if tab not in BUILDERS:
        raise ExampleError(f'no example builder for the tab {tab!r}: {sorted(BUILDERS)}')
    return stored(tab, BUILDERS[tab](conn, names, lists, as_of, stream=stream, **extra), as_of)
