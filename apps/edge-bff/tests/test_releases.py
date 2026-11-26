"""EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md sections 8 and 8a): the release catalog and GET /api/v1/catalog/{kind}.

- catalog/releases.json is complete against the registries read from the repository (a new indicator, Flow indicator,
  candlestick pattern, Screener metric or preset fails here until it has an entry) and names no id they lack;
- app/releases.py: an unknown id is 'lab', a malformed file fails at load naming the problem, KIND_OF_FAMILY covers
  every item family of section 8a;
- the route returns exactly the entries the principal holds, 404 NOT_FOUND for an unknown kind, 401 signed out.

The route tests use principals whose `can` this file controls (the auth dependency overridden in the test app): the
Phase 1 Principal (app/principal.py) knows `*` and exact keys only, the item grants of section 8a ({"ids"},
{"stages"}, {"all"}) arrive with the Phase 2 principal. Two tests also go through the real sign-in with the switch off.
"""
import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import releases
from app.catalog import SCREENER_METRICS, SHOWN_ATTRIBUTES
from app.main import create_app
from app.releases import KIND_OF_FAMILY, KINDS, ReleaseFileError, Releases, stage_of
from conftest import FakeOrc
from test_edge import login

BFF = Path(__file__).resolve().parents[1]
FILE = BFF / 'catalog' / 'releases.json'


def ids(path, *keys):
    data = json.loads((BFF / path).read_text(encoding='utf-8'))
    for key in keys:
        data = data[key]
    return [row['id'] for row in data]


def legacy_flow_types():
    """The Backtest's legacy flow cards (backtest/src/core/catalog.ts LEGACY, the entries of group 'flow': fnet, broker
    and top5 today), read from the TypeScript source as data: each `<type>: { group: '<group>', ...` line of the LEGACY
    object. They read broker data, so they are flow items of the catalog (CONTRACT.md 8b "3b follow-up", user decision
    2026-11-18); backtest-worker src/validate.ts legacyItemKind gates them by the same group."""
    src = (BFF / 'backtest/src/core/catalog.ts').read_text(encoding='utf-8')
    block = re.search(r'export const LEGACY: Record<LegacyType, LegacySpec> = \{\n(.*?)\n\};', src, re.S)
    assert block, 'backtest/src/core/catalog.ts: the LEGACY object was not found; update legacy_flow_types()'
    rows = re.findall(r"^\s*(\w+): \{ group: '(\w+)'", block.group(1), re.M)
    assert len(rows) == block.group(1).count('group:'), 'a LEGACY entry is not on one line `<type>: { group: ...`'
    types = re.search(r'export type LegacyType = (.*?);', src).group(1)
    assert {t for t, _ in rows} == set(re.findall(r"'(\w+)'", types)), 'LEGACY and LegacyType differ'
    return [t for t, group in rows if group == 'flow']


def registry_ids():
    """Each kind's ids from the registries the product reads (CONTRACT.md 8a, 'Kinds and their registries')."""
    indicators = ids('terminal/src/data/indRegistry.json')
    # the Backtest and Screener registries are built from indRegistry.json and must carry the same indicator ids
    assert set(ids('backtest/src/core/backtest-registry.json', 'indicators')) == set(indicators)
    assert set(ids('screener/src/core/screener-registry.json', 'indicators')) == set(indicators)
    candles = ids('backtest/src/core/candle-registry.json', 'patterns')
    assert set(ids('screener/src/core/screener-registry.json', 'candles')) == set(candles)
    return {
        'indicator': indicators,
        # the Terminal's FL01-FL52, plus the Screener's own entries (fnet, ksei_net) of screener-registry.json flows,
        # plus the Backtest's legacy flow cards (fnet, broker, top5; 3b follow-up)
        'flow_indicator': list(dict.fromkeys(ids('terminal/src/data/flowRegistry.json', 'indicators')
                                             + ids('screener/src/core/screener-registry.json', 'flows')
                                             + legacy_flow_types())),
        'candle_pattern': candles,
        'screener_metric': ids('screener/src/core/screener-metrics.json', 'metrics'),
        'screener_preset': ids('screener/src/core/presets.json', 'presets'),
    }


def test_every_registry_id_has_an_entry_and_every_entry_names_a_registry_id():
    current = releases.load(FILE)
    registries = registry_ids()
    assert set(registries) == set(KINDS)
    listed = {kind: [e['id'] for e in current.entries(kind)] for kind in KINDS}
    missing = [(kind, i) for kind in KINDS for i in registries[kind] if i not in listed[kind]]
    assert not missing, (
        'These registry items have no release stage in apps/edge-bff/catalog/releases.json (an unlisted item is lab '
        'at run time, but the file must name each one). Add one line per item to "items": "lab" for a beta-only item '
        '(INDICATOR_BETA_TO_LIVE.md part A, a Flow indicator its section "A lab Flow indicator"; not a candle pattern, '
        'LAB_KIND_HELD), "preview" for the admin only (part C), or "released" with the user\'s go '
        '(part B; LIVE_PROMOTION.md section 3):\n'
        + '\n'.join(f'    {{"kind": "{kind}", "id": "{i}", "stage": "lab"}},' for kind, i in missing))
    stale = [(kind, i) for kind in KINDS for i in listed[kind] if i not in registries[kind]]
    assert not stale, ('apps/edge-bff/catalog/releases.json names items no registry has; remove these entries or fix '
                       f'the id: {stale}')


# The first lab item (the user, 2026-11-23: "Cabut tes penjaga lab"; EXEC-MU-ACCOUNTS). The four conditions that held
# back every lab item after 3f's checker (ERRORS M523, FUTURE_PLAN.md "Before the first lab item or tab") are closed on
# both sites, each by a deploy of RAILWAY_CHANGELOG.md 2026-11-22 "The round's close":
# - checker L2, CAT-3: the screener-worker that runs the allow walk on the definition as sent (run.ts gateSent) and
#   names nothing outside allow (forAllow): screener-worker 4438dbb0 from main ec739a06, shared by both sites;
# - checker TR-2, B3: both workers load the lab registration point ('@edge-lab', backtest-worker loader/resolve.mjs):
#   backtest-worker df495720 (CLI upload of ec739a06) and screener-worker 4438dbb0, whose watch patterns hold
#   /apps/edge-bff/terminal/src/lab/** (railway config apply, the same record);
# - round 2, CRIT-1: the live site's Terminal parks a saved entry its build lacks (terminal/src/data/inputs.ts
#   restoreList): edge-bff-live 306c1190 runs ec739a06;
# - the example-mode checker (M527): the live site cuts the stored examples to its release file at serve time
#   (app/examples.py released_view): the same live deployment.
# The standing rules stay: an item no worker gates by id is never lab (test_an_item_no_worker_gates_by_id_is_never_lab),
# nor an item the shipped code names or computes (test_an_item_the_shipped_code_names_is_never_lab), and a released
# entry's text names no lab item. The tabs keep their own guard (tests/test_live_switch.py LAB_TAB_HELD_UNTIL).
#
# Per kind (INDICATOR_BETA_TO_LIVE.md, LIVE_PROMOTION.md section 3):
# - indicator: may be lab. Its formula goes into terminal/src/lab/index.ts, which only the lab page builds and the
#   workers load; the public builds leave its registry entry out (shared/release-filter.mjs) and the workers refuse it
#   to a principal whose allow lacks it.
# - candle_pattern, screener_metric: may be lab. Both are data the workers read whole (backtest/src/core/
#   candle-registry.json, screener/src/core/screener-metrics.json) and gate by id (screener-worker run.ts ITEM_REFS
#   pattern, xsection and universe; backtest-worker src/access.ts); the public builds and the catalogs leave a lab one
#   out. A new one that needs new code in the shared cores is named in code and stays released (the CRIT-3 guard).
# - screener_preset: may be lab. No worker gates a preset by id, but a preset is a catalog row whose definition reads
#   items that are gated by their own stages; the lab stage keeps the row off the live site's catalog
#   (catalog.tab_list, app/screener.py PRESET_KIND), nothing more.
# - flow_indicator: may be lab since 2026-11-23 (step 3 of the user's sequence): its formula is registered from
#   terminal/src/lab/index.ts (calc/flow.ts registerFlow, flowKit), its registry entry and tip come from the spreadsheet
#   and scripts/build_flow_registry.py (not shipped), its Screener kinds from flow-kinds.json (read by the workers and
#   the generator only); the public builds and the catalogs leave a lab one out. Proven by the dry run of 2026-11-23
#   (INDICATOR_BETA_TO_LIVE.md "A lab Flow indicator"). Held before: the FLOW map was written to be the one place of
#   every formula (it is exported; the reason recorded earlier, "unexported", was wrong) and had no wrapped entry point.
LAB_KIND_HELD = {
    # the test-out of 2026-11-23 (LLA-F2): the dry run covered an indicator only; a lab candle needs its pair and mirror
    # (backtest core candles.ts), a CASES entry and the count pins of the look-ahead gate, candles.test.ts and the
    # screener-worker's operators.test.ts made derived first; held until one is dry-run like the indicator was
    'candle_pattern': ("a lab candle pattern was not dry-run: its pair and mirror (candles.ts), its CASES entry and the "
                       "count pins of lookahead.test.ts, candles.test.ts and operators.test.ts are not ready for a 21st "
                       "pattern (EXEC-MU-ACCOUNTS, Carried open parts; INDICATOR_BETA_TO_LIVE.md)"),
}


def held_lab(current):
    """The (kind, id) pairs at the lab stage in a kind LAB_KIND_HELD names."""
    return [(kind, e['id']) for kind in KINDS for e in current.entries(kind)
            if e['stage'] == releases.LAB and kind in LAB_KIND_HELD]


def test_an_item_is_at_the_lab_stage_only_in_a_kind_that_has_a_lab_path():
    """User decision 2026-11-17: every item that existed then is released. Since 2026-11-23 (the user's "Cabut tes
    penjaga lab") a new item may enter at the lab stage (the beta only) in every kind but those LAB_KIND_HELD names. The
    preview stage (EXEC-MU-ACCOUNTS "A preview release stage") is open to every kind: its formula is public."""
    current = releases.load(FILE)
    held = held_lab(current)
    assert not held, (f'{held} at the lab stage, in a kind that has no lab path yet: '
                      + '; '.join(f'{kind}: {why}' for kind, why in LAB_KIND_HELD.items())
                      + '. List it as "released" with the user\'s go, or keep it off main.')
    assert set(LAB_KIND_HELD) <= set(KINDS)


def test_the_lab_kind_guard_refuses_a_held_kind_and_lets_the_others_be_lab(tmp_path):
    """Self-test of the guard above on a planted release file: a lab item of every kind, and a preview one of every
    kind, which the guard lets through (a preview Flow indicator included)."""
    entries = ([{'kind': kind, 'id': f'X_{kind}', 'stage': 'lab'} for kind in KINDS]
               + [{'kind': kind, 'id': f'P_{kind}', 'stage': 'preview'} for kind in KINDS])
    planted = tmp_path / 'releases.json'
    planted.write_text(json.dumps({'schema_version': releases.SCHEMA_VERSION, 'tabs': [], 'items': entries}), encoding='utf-8')
    current = releases.load(planted)
    lab = {kind for kind in KINDS for e in current.entries(kind) if e['stage'] == 'lab'}
    assert lab == set(KINDS)
    assert {kind for kind, _ in held_lab(current)} == {'candle_pattern'}
    assert not [i for _, i in held_lab(current) if i.startswith('P_')]
    assert {kind for kind in KINDS for e in current.entries(kind) if e['stage'] == 'preview'} == set(KINDS)


def not_gated_by_id():
    """The Screener metrics no worker gates by their id, read from the catalog both workers load (3f round 2, TRC2-5 and
    CS-5): an entry with a reference template (`ref`, truthy as the core reads it: catalog.ts metricSpec refuses its id,
    so it reaches the wire as the template, hi52 as pct_distance(rolling_max(high, 252))), and a universe attribute
    every answer shows (catalog.SHOWN_ATTRIBUTES, the entries naming their `row`; the Screener worker's walk skips them).
    The screener-worker test "the walk names a Screener metric by its id exactly when its catalog entry has no ref and
    no row" (tests/allow.test.ts) holds the walk to the same two fields."""
    metrics = json.loads(SCREENER_METRICS.read_text(encoding='utf-8'))['metrics']
    return {m['id'] for m in metrics if m.get('ref')}, set(SHOWN_ATTRIBUTES)


def lab_not_gated(current):
    ref, shown = not_gated_by_id()
    return sorted(i for i in ref | shown if current.stage_of('screener_metric', i) != 'released')


def test_an_item_no_worker_gates_by_id_is_never_lab():
    """A standing rule, not one of LAB_KIND_HELD (3f round 2, TRC2-5 and CS-5): a lab item is held by its holders
    only through the workers' checks by id (allow.KINDS), so an item every principal reads or computes whatever its plan
    can never be at the lab stage; it stays out of the catalogs only in name. (A preset is outside this rule: a run
    carries a definition, never a preset id, and a lab preset is held by hiding its definition.)"""
    ref, shown = not_gated_by_id()
    assert ref and shown, 'the catalog has no ref entry or no row entry: not_gated_by_id reads the wrong fields'
    planted = sorted({min(ref), min(shown)})
    for stage in ('lab', 'preview'):                    # never preview either (check of steps 2-3, PV-4)
        data = json.loads(FILE.read_text(encoding='utf-8'))
        data['items'] = [{**it, 'stage': stage} if it['kind'] == 'screener_metric' and it['id'] in planted else it
                         for it in data['items']]
        assert lab_not_gated(Releases(data)) == planted, stage                           # the guard's self-test
    lab = lab_not_gated(releases.load(FILE))
    assert not lab, (
        f'{lab} at the lab stage in apps/edge-bff/catalog/releases.json, but no worker gates them by id: a universe '
        'attribute that names its `row` is shown in every /universe and result row, and a metric with a `ref` reaches '
        'the wire as that composition of the Screener\'s own transforms, so every principal reads or runs it whatever '
        'its plan. Set them "released". To stage a new one in the lab, give it an id the workers gate: a universe '
        'attribute without `row` (its value out of /universe and the result rows until it is released; '
        'screener-worker tests/shown.test.ts), or a new computation as a pattern, cross-section metric or indicator, '
        'not a `ref` of existing transforms (CONTRACT.md 8b O3b-2, R1-35).')


# The lab gap "items code names or computes" (3f round 2, CRIT-3; FUTURE_PLAN.md; the user's go 2026-11-22): an item the
# public page code or a worker names in code (every Flow formula keyed by its id in terminal/src/calc/flow.ts, the page
# modules' ids, a built-in computing a registry indicator as BY_ID.I07) runs or ships for every principal whatever its
# stage, so it can never be at the lab stage. Derived from the code: an id with a digit (I07, FL51) counts where it
# stands as a word, an id without one (a Screener metric such as 'close') only as a quoted literal; comments, tests and
# the lab folder (terminal/src/lab, built only into the lab builds) are not code that ships to everyone.
CODE_DIRS = tuple(BFF / d / 'src' for d in ('terminal', 'backtest', 'screener', 'radar', 'overview', 'sector', 'watchlist',
                                            'admin')) + (
    BFF.parent / 'backtest-worker' / 'src', BFF.parent / 'screener-worker' / 'src')


def _code(src):
    src = re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)
    return re.sub(r'(?m)(^|[^:\'"])//.*$', r'\1', src)


def key_aliases():
    """{(kind, id): key} of the registry entries that the code may look up by a key of their own (an indicator's `key`,
    'donchian' for I10): a built-in computing calc.out('donchian') computes I10 without naming its id (test-out
    wf_c72ae04c-a73, CRIT-3). Derived from every registry list REGISTRIES names."""
    out = {}
    for kind, e in registry_entries():
        k = e.get('key')
        if isinstance(k, str) and k and k != e['id']:
            out[(kind, e['id'])] = k
    return out


# The public formula files where a preview or released item's formula is defined (INDICATOR_BETA_TO_LIVE.md Part C): an
# indicator's `<key>: def('<key>', ...)` line in calc/indicators.ts, a Flow indicator's `FLnn:` entry of FLOW in
# calc/flow.ts. A preview item's own definition there is its public formula by design (CONTRACT 8 "Preview"); any other
# code that names or computes it (another formula built on it, a built-in, a worker, a page list) still refuses it
# (check of steps 2-3, 2026-11-23, PV-1 and F5).
FORMULA_HOME = {'indicator': BFF / 'terminal' / 'src' / 'calc' / 'indicators.ts',
                'flow_indicator': BFF / 'terminal' / 'src' / 'calc' / 'flow.ts'}


def own_definition(kind, item_id, key):
    """The pattern of an item's own formula definition in its FORMULA_HOME, or None."""
    if kind == 'indicator' and key:
        return re.compile(rf'(?m)^[ \t]*{re.escape(key)}[ \t]*:[ \t]*def\(.*$')
    if kind == 'flow_indicator':
        return re.compile(rf'(?m)^([ \t]*){re.escape(item_id)}(?=[ \t]*:)')
    return None


def named_in_code(current, preview_home=False):
    """{(kind, id): [files]} of the release file's items the shipped code names (the comment above): by the id, or by
    the item's own registry key (key_aliases) as a quoted literal or a property (terminal/src/lab/index.ts registers a
    lab formula as F.my_key). With preview_home, an item's own formula definition in its FORMULA_HOME is not counted
    (the rule for a preview item; a lab item's formula lives in the lab folder, so nothing is left out for it)."""
    files = [p for d in CODE_DIRS if d.exists() for p in d.rglob('*') if p.suffix in ('.ts', '.tsx', '.js', '.mjs')
             and 'lab' not in p.relative_to(d).parts and 'tests' not in p.relative_to(d).parts]
    files += sorted((BFF / 'static').glob('edge-*.js'))
    assert len(files) > 50, f'only {len(files)} code files found: CODE_DIRS reads the wrong folders'
    texts = {p: _code(p.read_text(encoding='utf-8', errors='ignore')) for p in files}
    assert all(p in texts for p in FORMULA_HOME.values()), 'a FORMULA_HOME file is not among the code files read'
    aliases = key_aliases()
    found = {}
    for kind in KINDS:
        for e in current.entries(kind):
            i = e['id']
            patterns = [re.compile(rf'\b{re.escape(i)}\b' if re.search(r'\d', i) else rf'[\'"`]{re.escape(i)}[\'"`]')]
            if (kind, i) in aliases:            # by its key: a quoted literal, or a property of a formula map (F.donchian)
                key = re.escape(aliases[(kind, i)])
                patterns += [re.compile(rf'[\'"`]{key}[\'"`]'), re.compile(rf'\.{key}\b')]
            own = own_definition(kind, i, aliases.get((kind, i))) if preview_home else None
            hits = []
            for p, t in texts.items():
                if own is not None and p == FORMULA_HOME.get(kind):
                    t = own.sub(lambda m: m.group(1) if m.groups() else '', t)
                if any(x.search(t) for x in patterns):
                    hits.append(p.relative_to(BFF.parent.parent).as_posix())
            if hits:
                found[(kind, i)] = hits
    return found


def all_released():
    """The repository's release file with every item released: the self-tests below plant their own stages on it, so
    they hold whatever the file holds today (check of steps 2-3, F10)."""
    data = json.loads(FILE.read_text(encoding='utf-8'))
    data['items'] = [{**it, 'stage': 'released'} for it in data['items']]
    return data


def test_an_item_the_shipped_code_names_is_never_lab():
    current = releases.load(FILE)
    named = named_in_code(current)
    assert ('flow_indicator', 'FL51') in named and any(k == 'indicator' for k, _ in named), (
        'the scan finds neither FL51 (terminal/src/calc/flow.ts) nor a registry indicator (signals.ts BY_ID.I07): it '
        'reads the wrong files or the wrong shape')
    # by key (test-out wf_c72ae04c-a73, CRIT-3): the Screener's breakdown and squeeze patterns compute I10 and I29 as
    # t.calc.out('donchian') and t.calc.out('bollinger_width') (screener/src/core/transforms.ts) without naming the ids
    assert key_aliases()[('indicator', 'I10')] == 'donchian' and key_aliases()[('indicator', 'I29')] == 'bollinger_width'
    for i in ('I10', 'I29'):
        assert any(f.endswith('screener/src/core/transforms.ts') for f in named.get(('indicator', i), [])), (i, named.get(('indicator', i)))
    data0 = all_released()
    data0['items'] = [{**it, 'stage': 'lab'} if (it['kind'], it['id']) in {('indicator', 'I10'), ('indicator', 'I29')} else it
                      for it in data0['items']]
    trial0 = Releases(data0)
    assert sorted(k for k in named if trial0.stage_of(*k) != 'released') == [('indicator', 'I10'), ('indicator', 'I29')]
    data = all_released()
    planted = next(iter(sorted(named)))
    data['items'] = [{**it, 'stage': 'lab'} if (it['kind'], it['id']) == planted else it for it in data['items']]
    trial = Releases(data)
    assert [k for k in named if trial.stage_of(*k) != 'released'] == [planted]            # the guard's self-test
    # a preview item may be named by its own formula definition only (FORMULA_HOME): an indicator and a Flow indicator
    # whose only hit is that definition pass at preview and are refused at lab; one another formula or a built-in
    # computes (I10 by transforms.ts, FL23 by FL52 and the Backtest's point-in-time spec) is refused at preview too
    home = named_in_code(current, preview_home=True)
    home_rel = {k: p.relative_to(BFF.parent.parent).as_posix() for k, p in FORMULA_HOME.items()}
    only_home = {kind: sorted(i for (k, i), files in named.items() if k == kind and files == [home_rel[kind]])
                 for kind in FORMULA_HOME}
    assert only_home['indicator'] and only_home['flow_indicator'], only_home
    for kind, ids in only_home.items():
        assert (kind, ids[0]) not in home, (kind, ids[0], home.get((kind, ids[0])))
    assert ('indicator', 'I10') in home and ('flow_indicator', 'FL23') in home, 'built-ins and other formulas still count'
    lab = {k: named[k][:3] for k in named if current.stage_of(*k) == releases.LAB}
    preview = {k: home[k][:3] for k in home if current.stage_of(*k) == releases.PREVIEW}
    assert not preview, (
        f'{preview} at the preview stage in apps/edge-bff/catalog/releases.json, but code that ships to every principal '
        'names or computes them beyond their own formula definition (the files listed): a preview item is held by the '
        'admin only, so another formula, a built-in or a page list must not compute or name it for everyone. Set them '
        '"released", or move that code first (INDICATOR_BETA_TO_LIVE.md Part C).')
    assert not lab, (
        f'{lab} at the lab stage in apps/edge-bff/catalog/releases.json, but the code that ships to every principal '
        'names them (the files listed): a lab stage would keep them in the public bundles or running for everyone. Set '
        'them "released", or move the code that names them into the lab folder (terminal/src/lab, registered through '
        'its one registration point) and out of the shared code first.')


# 3f checker CAT-5 (the lab gaps' optional row; the user's go 2026-11-22): a released entry's own text (its name, tip,
# description, synonyms) ships to every principal, so it must not name a lab item, by id or by name. The registry files
# and their lists are read from the release filter's own list (shared/release-filter.mjs REGISTRIES: a file with one list
# and its kind, several lists with their kinds, or an object keyed by item id), so a file added there is scanned here
# too (test-out wf_c72ae04c-a73: a list kept by hand here had left out screener/src/core/screener-registry.json).
RELEASE_FILTER = BFF / 'shared' / 'release-filter.mjs'


PARTS = 'keyedParts'


def registry_specs():
    """[(file, [(key or None, kind)], keyed)] of REGISTRIES, read from release-filter.mjs's source (one spec per line); a
    keyedParts spec gives [(key, kinds)] and keyed PARTS."""
    src = RELEASE_FILTER.read_text(encoding='utf-8')
    block = src[src.index('export const REGISTRIES = ['):]
    block = block[:block.index('\n];') + 3]
    lines = [ln for ln in block.splitlines() if re.match(r'\s*\{ file: ', ln)]
    specs = []
    for ln in lines:
        file = re.search(r"file: '([^']+)'", ln).group(1)
        kind = re.search(r"kind: '([^']+)'", ln)
        keyed = re.search(r"keyed: '([^']+)'", ln)
        if 'keyedParts: [' in ln:
            # objects keyed by item id, each part with the kinds its ids may be of (step 3 of 2026-11-23), and lists that
            # name their item by a field (`lists: [[key, kind, field]]`, check of steps 2-3, P4)
            keyed_src, _, lists_src = ln.partition('lists: [')
            parts = re.findall(r"\['(\w+)', \[([^\]]*)\]\]", keyed_src)
            fields = re.findall(r"\['(\w+)', '(\w+)'(?:, '(\w+)')?\]", lists_src)
            specs.append((file, [(key, tuple(re.findall(r"'(\w+)'", kinds))) for key, kinds in parts]
                          + [(key, (kind,), field or 'id') for key, kind, field in fields], PARTS))
            assert specs[-1][1], ln
            continue
        if 'lists: [' in ln:
            lists = re.findall(r"\['(\w+)', '(\w+)'\]", ln)
        elif 'asList(' in ln:
            lists = [(re.search(r"asList\('(\w+)'\)", ln).group(1), kind.group(1))]
        elif keyed:
            lists = [(None, kind.group(1))]
        elif re.search(r'list: d => d\b', ln):
            lists = [(None, kind.group(1))]
        else:
            raise AssertionError(f'release-filter.mjs REGISTRIES line not understood (list, lists, keyed, keyedParts or asList): {ln}')
        assert lists, ln
        specs.append((file, lists, keyed.group(1) if keyed else None))
    assert len(specs) == block.count('{ file: ') >= 8, f'REGISTRIES read {len(specs)} specs from {block.count("{ file: ")}'
    return specs


def registry_entries(only=None):
    """[(kind, entry)] of every registry list REGISTRIES names (an object keyed by id gives {id, value})."""
    out = []
    for file, lists, keyed in registry_specs():
        if only is not None and file != only:
            continue
        doc = json.loads((BFF / file).read_text(encoding='utf-8'))
        if keyed == PARTS:
            for key, kinds, *field in lists:
                if field:                   # a list naming its item by a field: the entry as it is, its id read there
                    out += [(kinds[0], {**e, 'id': e[field[0]]}) for e in doc[key]
                            if isinstance(e, dict) and isinstance(e.get(field[0]), str)]
                    continue
                # an id is of the first kind the release file lists it under (shared/release-filter.mjs filtered)
                out += [(releases.kind_of(i, kinds) or kinds[0], {'id': i, 'value': v}) for i, v in doc[key].items()]
            continue
        for key, kind in lists:
            if keyed:
                part = [{'id': i, 'value': v} for i, v in doc[keyed].items()]
            else:
                part = doc if key is None else doc.get(key, [])
            out += [(kind, e) for e in part if isinstance(e, dict) and isinstance(e.get('id'), str)]
    return out


NAME_FIELDS = ('name', 'label', 'short')


def released_text_naming_lab(current, entries):
    # an item may have an entry in several files (a registry entry and an overlay keyed by its id): its names are those of
    # every entry, so one without a name field takes none away (step 3 of 2026-11-23, keyedParts)
    lab = {}
    for k, e in entries:
        if current.stage_of(k, e['id']) != 'released':
            lab.setdefault((k, e['id']), []).append(e)
    marks = {}
    for (k, i), es in lab.items():
        # every display field a registry names an item by: name (indicators, Flow, candles), label and short (Screener
        # metrics, presets) (test-out of 2026-11-23, LLA-F3: a lab metric named by its label passed)
        marks[i] = [re.compile(rf'\b{re.escape(i)}\b')] + [re.compile(re.escape(e[f])) for e in es for f in NAME_FIELDS
                                                         if isinstance(e.get(f), str) and len(e[f]) > 3]
    hits = []
    for k, e in entries:
        if (k, e['id']) in lab:
            continue
        text = json.dumps({f: v for f, v in e.items() if f not in ('id', 'key')}, ensure_ascii=False)
        hits += [(k, e['id'], i) for i, pats in marks.items() if i != e['id'] and any(p.search(text) for p in pats)]
    return sorted(hits)


def test_a_released_entrys_text_names_no_lab_item():
    entries = registry_entries()
    assert len(entries) > 150, f'only {len(entries)} registry entries read: REGISTRY_FILES reads the wrong lists'
    # the guard's self-test: an indicator put at the lab stage whose id another entry's text names
    data = json.loads(FILE.read_text(encoding='utf-8'))
    text_ids = {i for k, e in entries for i in re.findall(r'\b[A-Z]{1,3}\d{2}\b', json.dumps(
        {f: v for f, v in e.items() if f not in ('id', 'key')}))}
    named = sorted(i for k, e in entries if k == 'indicator' and e['id'] in text_ids for i in [e['id']])
    if named:
        planted = named[0]
        for stage in ('lab', 'preview'):                # a released text names no preview item either (PV-4)
            trial = json.loads(FILE.read_text(encoding='utf-8'))
            trial['items'] = [{**it, 'stage': stage} if (it['kind'], it['id']) == ('indicator', planted) else it
                              for it in trial['items']]
            assert any(h[2] == planted for h in released_text_naming_lab(Releases(trial), entries)), stage
    # every file REGISTRIES names is read: a sentence planted in the first entry of each, naming an indicator set to the
    # lab stage, is caught (test-out wf_c72ae04c-a73: "Compare with I02." in I01's description of screener-registry.json)
    for file, lists, keyed in registry_specs():
        own = registry_entries(only=file)
        assert own, f'{file}: no entry read'
        first = own[0]
        target = next(i for k, e in entries if k == 'indicator' for i in [e['id']] if i != first[1]['id'])
        planted = [x for f2, _, _ in registry_specs() for x in (
            [(first[0], {**first[1], 'description': f'Compare with {target}.'})] + own[1:] if f2 == file else registry_entries(only=f2))]
        data = json.loads(FILE.read_text(encoding='utf-8'))
        data['items'] = [{**it, 'stage': 'lab'} if (it['kind'], it['id']) == ('indicator', target) else it for it in data['items']]
        assert (first[0], first[1]['id'], target) in released_text_naming_lab(Releases(data), planted), file
    # a lab item named by its display label (a Screener metric's label or short), not its id (LLA-F3)
    for field in ('label', 'short'):
        lab_one = next((k, e) for k, e in entries if isinstance(e.get(field), str) and len(e[field]) > 3)
        other = next((k, e) for k, e in entries if (k, e['id']) != (lab_one[0], lab_one[1]['id']))
        planted = [(k, {**e, 'misuse': f'Read it with {lab_one[1][field]}.'}) if (k, e['id']) == (other[0], other[1]['id'])
                   else (k, e) for k, e in entries]
        data = json.loads(FILE.read_text(encoding='utf-8'))
        data['items'] = [{**it, 'stage': 'lab'} if (it['kind'], it['id']) == lab_one[:1] + (lab_one[1]['id'],) else it
                         for it in data['items']]
        assert (other[0], other[1]['id'], lab_one[1]['id']) in released_text_naming_lab(Releases(data), planted), field
    hits = released_text_naming_lab(releases.load(FILE), entries)
    assert not hits, (f'released entries whose own text names a lab item ({hits[:5]}): that text ships to every '
                      'principal. Reword it, or release the item first.')


def held_back_in_one_kind_only(current):
    """The ids the release file lists under more than one kind whose stages differ in being held back (lab or preview in
    one kind, released in another)."""
    by_id = {}
    for kind in KINDS:
        for e in current.entries(kind):
            by_id.setdefault(e['id'], []).append((kind, releases.held_back(e['stage'])))
    return sorted(i for i, ks in by_id.items() if len(ks) > 1 and len({h for _, h in ks}) > 1)


def test_an_id_two_kinds_share_is_held_back_in_both_or_in_neither():
    """check of steps 2-3 (2026-11-23, PV-5): the stored examples match an item by its bare id (app/examples.py
    not_released, _names), and three ids are both a Screener metric and a preset (squeeze, silent, piotroski). One of them
    held back in one kind only would read as held back in the other too: a released metric's example withheld (fail
    closed), or, the other way, a check by kind elsewhere that trusts the bare id. Until the examples match by kind
    (EXEC-MU-ACCOUNTS, Carried open parts), such an id is held back in both kinds or in neither."""
    current = releases.load(FILE)
    shared = sorted({e['id'] for k in KINDS for e in current.entries(k)} & {
        e['id'] for k1 in KINDS for k2 in KINDS if k1 < k2 for e in current.entries(k1)
        if any(x['id'] == e['id'] for x in current.entries(k2))})
    assert shared, 'no id is listed under two kinds: the rule has nothing to hold (remove it with the carried part)'
    data = all_released()
    data['items'] = [{**it, 'stage': 'preview'} if (it['kind'], it['id']) == ('screener_preset', shared[0]) else it
                     for it in data['items']]
    assert held_back_in_one_kind_only(Releases(data)) == [shared[0]]                       # the guard's self-test
    found = held_back_in_one_kind_only(current)
    assert not found, (f'{found} are listed under two kinds and held back (lab or preview) in only one: the stored '
                       'examples match by the bare id, so the released one reads as held back too. Hold both back, or '
                       'give the new item an id of its own.')


def test_the_flow_registry_is_numbered_without_gaps():
    """The source file of the Terminal's Flow registry (every stage) holds FL01..FLnn without a gap; a new Flow indicator
    takes the next free id (INDICATOR_BETA_TO_LIVE.md "A lab Flow indicator"). The page tests read the public build's
    view, where a lab one is left out, so they check order only (check of steps 2-3, 2026-11-23, P2 and F4)."""
    ids = ids_of_flow_source()
    assert ids == [f'FL{k:02d}' for k in range(1, len(ids) + 1)], ids


def ids_of_flow_source():
    return [e['id'] for e in json.loads((BFF / 'terminal' / 'src' / 'data' / 'flowRegistry.json').read_text())['indicators']]


def test_the_module_loads_the_repository_file_and_an_unknown_id_is_lab():
    assert releases.PATH == FILE and releases.CURRENT.entries('indicator') == releases.load(FILE).entries('indicator')
    assert stage_of('indicator', 'I01') == 'released'
    assert stage_of('flow_indicator', 'FL24') == 'released'
    assert stage_of('indicator', 'I99999') == 'lab'
    assert stage_of('no_such_kind', 'I01') == 'lab'
    with pytest.raises(KeyError):
        releases.entries('no_such_kind')


def test_kind_of_family_covers_every_item_family_of_section_8a():
    # the 3b follow-up (user decision 2026-11-18, "gate-nya adalah terminal"): the indicator and Flow items of every tab
    # are the Terminal's families; migration 20261118_001 removed backtest/screener.indicator and .flow_indicator
    assert KIND_OF_FAMILY == {
        'terminal.indicator': 'indicator', 'terminal.flow_indicator': 'flow_indicator',
        'backtest.candle_pattern': 'candle_pattern', 'screener.candle_pattern': 'candle_pattern',
        'screener.metric': 'screener_metric', 'screener.preset': 'screener_preset'}
    assert set(KIND_OF_FAMILY.values()) == set(KINDS)
    # every item family the seed names (8a "Capability rows", less the four of 20261118_001), terminal.dataset and
    # monitor.model excepted (they have no release stage: data sets and models, not catalog items)
    seeded = {'terminal.indicator', 'terminal.flow_indicator', 'terminal.dataset', 'backtest.candle_pattern',
              'screener.candle_pattern', 'screener.metric', 'screener.preset', 'monitor.model'}
    assert seeded - set(KIND_OF_FAMILY) == {'terminal.dataset', 'monitor.model'}
    assert set(KIND_OF_FAMILY) - seeded == set()


def test_the_legacy_flow_cards_are_flow_items_and_the_technical_cards_are_not():
    """3b follow-up: the Backtest's built-in cards that read broker data are flow items of the catalog, released; the
    technical ones (macd, dip and the cards mapped to registry indicators) are part of the Backtest (CONTRACT.md 8b)."""
    assert legacy_flow_types() == ['fnet', 'broker', 'top5']
    flows = {e['id']: e['stage'] for e in releases.load(FILE).entries('flow_indicator')}
    assert all(flows.get(t) == 'released' for t in legacy_flow_types())
    listed = {e['id'] for kind in KINDS for e in releases.load(FILE).entries(kind)}
    assert not {'macd', 'dip', 'adx', 'rsi'} & listed


def item(kind='indicator', id='I01', stage='released'):
    return {'kind': kind, 'id': id, 'stage': stage}


@pytest.mark.parametrize('data, words', [
    ({'schema_version': 1, 'items': [item(), item()]}, 'repeats indicator'),
    ({'schema_version': 1, 'items': [item(kind='widget')]}, "unknown kind 'widget'"),
    ({'schema_version': 1, 'items': [item(stage='beta')]}, "unknown stage 'beta'"),
    # EXEC-MU-ACCOUNTS "A preview release stage": a tab is lab or released only
    ({'schema_version': 1, 'items': [], 'tabs': [{'id': 'terminal', 'stage': 'preview'}]}, 'a tab has no preview stage'),
    ({'schema_version': 1, 'items': [item(id='')]}, 'non-empty id'),
    ({'schema_version': 1, 'items': [item(id=' I01')]}, 'non-empty id'),
    ({'schema_version': 1, 'items': [{'kind': 'indicator', 'id': 'I01'}]}, 'exactly kind, id and stage'),
    ({'schema_version': 1, 'items': [{**item(), 'extra': 1}]}, 'exactly kind, id and stage'),
    ({'schema_version': 2, 'items': []}, 'schema_version must be 1'),
    ({'schema_version': 1, 'items': {}}, 'items must be a list'),
    ({'schema_version': 1, 'items': [], 'stages': {}}, 'unknown top-level keys'),
    ({'schema_version': 1, 'items': []}, 'tabs must be a list'),       # LIVE_PROMOTION.md: without tabs, every tab is lab
    ([], 'must be a JSON object'),
])
def test_a_malformed_file_fails_at_load_with_a_clear_message(tmp_path, data, words):
    path = tmp_path / 'releases.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ReleaseFileError, match='releases.json') as caught:
        releases.load(path)
    assert words in str(caught.value)


def test_a_file_that_is_not_json_or_missing_fails_at_load(tmp_path):
    path = tmp_path / 'releases.json'
    path.write_text('{"schema_version": 1, "items": [')
    with pytest.raises(ReleaseFileError, match='not valid JSON'):
        releases.load(path)
    with pytest.raises(ReleaseFileError, match='missing'):
        releases.load(tmp_path / 'absent.json')


def test_a_preview_item_is_preview_and_held_back_with_lab():
    r = Releases({'schema_version': 1, 'items': [item(id='I01', stage='preview'), item(id='I02')], 'tabs': []})
    assert r.stage_of('indicator', 'I01') == 'preview' and r.entries('indicator')[0] == {'id': 'I01', 'stage': 'preview'}
    assert [releases.held_back(st) for st in ('lab', 'preview', 'released', 'beta')] == [True, True, False, True]
    assert releases.STAGES == ('lab', 'preview', 'released') and releases.TAB_STAGES == ('lab', 'released')
    assert releases.GRANT_STAGES == ('lab', 'released')
    assert Releases({'schema_version': 1, 'items': [], 'tabs': []}).digest != r.digest


def test_a_lab_item_is_lab_and_entries_keep_file_order():
    r = Releases({'schema_version': 1, 'items': [item(id='I02'), item(id='I01', stage='lab'), item('screener_preset',
                                                                                                    'brk52')],
                  'tabs': []})
    assert r.stage_of('indicator', 'I01') == 'lab' and r.stage_of('indicator', 'I02') == 'released'
    assert r.stage_of('indicator', 'I03') == 'lab'
    assert r.entries('indicator') == [{'id': 'I02', 'stage': 'released'}, {'id': 'I01', 'stage': 'lab'}]
    assert r.entries('candle_pattern') == []


# ---- the route ----------------------------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class StubPrincipal:
    """A principal holding the section 8a grants: `*`, flag keys, and per family an items value {"ids", "stages",
    "all"} (an item <family>:<id> is held when its id is in ids, its release stage in stages, or all is true)."""
    grants: dict
    owner_key: str = 'test-catalog-owner'

    def can(self, key):
        if '*' in self.grants or self.grants.get(key) is True:
            return True
        family, _, item_id = key.partition(':')
        value = self.grants.get(family)
        if not item_id or not isinstance(value, dict) or family not in KIND_OF_FAMILY:
            return False
        return (item_id in value.get('ids', ()) or value.get('all') is True
                or stage_of(KIND_OF_FAMILY[family], item_id) in value.get('stages', ()))


@pytest.fixture
def lab_file(tmp_path, monkeypatch):
    """A release file with one lab indicator (I02) beside released ones, in place of the repository's."""
    path = tmp_path / 'releases.json'
    path.write_text(json.dumps({'schema_version': 1, 'note': 'test', 'items': [
        item(id='I01'), item(id='I02', stage='lab'), item(id='I03'), item('flow_indicator', 'FL24'),
        item('candle_pattern', 'CP01'), item('candle_pattern', 'CP02', 'lab'),
        item('screener_metric', 'rs'), item('screener_preset', 'brk52', 'lab')],
        'tabs': [{'id': t, 'stage': st} for t, st in releases.load().tabs().items()]}))
    monkeypatch.setattr(releases, 'CURRENT', releases.load(path))


def app_as(settings, store, principal):
    """The app with every request resolved to `principal`: the session dependency and, since track guest (decision 1 of
    2026-11-19, "1a"), the visitor one, which the catalog route depends on (tests/test_route_table.py GUEST_OPEN)."""
    app = create_app(settings, store, FakeOrc())
    app.dependency_overrides[app.state.session_dependency] = lambda: principal
    app.dependency_overrides[app.state.visitor_dependency] = lambda: principal
    return app


def entries_of(c, kind):
    r = c.get(f'/api/v1/catalog/{kind}')
    assert r.status_code == 200, r.text
    assert r.json()['kind'] == kind
    return r.json()['entries']


def test_a_worker_refusal_names_a_lab_item_by_its_family_and_id_only(lab_file):
    """3f checker L2, CAT-3: the worker names an item outside allow by its id; edge-bff's named() adds the display name,
    which is errors.display_name of the capability (the family's words and the id once the catalog's names are read, a
    plain phrase before), never the item's own catalog name, for a lab item too."""
    from app.allow import named
    import app.errors as errors_module
    out = named({'code': 'CAPABILITY_REQUIRED', 'message': 'definition.x: the indicator I02 is not included in your plan.',
                 'details': {'kind': 'indicator', 'id': 'I02', 'capability': 'terminal.indicator:I02'}})
    registry = json.loads((BFF / 'terminal' / 'src' / 'data' / 'indRegistry.json').read_text(encoding='utf-8'))
    entries = registry
    name = next(e.get('name') for e in entries if isinstance(e, dict) and e.get('id') == 'I02')
    assert name and name not in json.dumps(out), (name, out)
    assert errors_module.display_name('terminal.indicator:I02') == out['details']['display_name']


def test_everything_holds_every_entry_at_any_stage(settings, store, lab_file):
    with TestClient(app_as(settings, store, StubPrincipal({'*': True}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I02', 'stage': 'lab'},
                                              {'id': 'I03', 'stage': 'released'}]
        assert entries_of(c, 'screener_preset') == [{'id': 'brk52', 'stage': 'lab'}]
        assert entries_of(c, 'candle_pattern') == [{'id': 'CP01', 'stage': 'released'}, {'id': 'CP02', 'stage': 'lab'}]


def test_released_stage_on_one_family_holds_only_released_entries_of_that_kind(settings, store, lab_file):
    p = StubPrincipal({'terminal.indicator': {'stages': ['released']}})
    with TestClient(app_as(settings, store, p)) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I03', 'stage': 'released'}]
        for kind in ('flow_indicator', 'screener_metric', 'screener_preset', 'candle_pattern'):
            assert entries_of(c, kind) == []


def test_a_preview_entry_is_held_by_everything_or_its_id_and_never_by_the_released_stage(settings, store, monkeypatch):
    """EXEC-MU-ACCOUNTS "A preview release stage": the route lists a preview entry with its stage to `*` and to a grant of
    its id; a plan of the released stage (paid) does not hold it, and no grant can name the preview stage."""
    monkeypatch.setattr(releases, 'CURRENT', Releases({'schema_version': 1, 'items': [
        item(id='I01'), item(id='I02', stage='preview'), item('flow_indicator', 'FL24', 'preview')], 'tabs': []}))
    with TestClient(app_as(settings, store, StubPrincipal({'*': True}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}, {'id': 'I02', 'stage': 'preview'}]
        assert entries_of(c, 'flow_indicator') == [{'id': 'FL24', 'stage': 'preview'}]
    p = StubPrincipal({'terminal.indicator': {'stages': ['released']}, 'terminal.flow_indicator': {'stages': ['released']}})
    with TestClient(app_as(settings, store, p)) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}]
        assert entries_of(c, 'flow_indicator') == []
    with TestClient(app_as(settings, store, StubPrincipal({'terminal.indicator': {'ids': ['I02']}}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I02', 'stage': 'preview'}]


def test_ids_grant_holds_exactly_those_ids_and_any_family_of_the_kind_counts(settings, store, lab_file):
    with TestClient(app_as(settings, store, StubPrincipal({'terminal.indicator': {'ids': ['I01']}}))) as c:
        assert entries_of(c, 'indicator') == [{'id': 'I01', 'stage': 'released'}]
        assert entries_of(c, 'flow_indicator') == []
    # a lab id granted by id in another tab's family of the same kind is held too (the candlestick patterns keep a
    # family per tab; the indicators have only the Terminal's since the 3b follow-up)
    p = StubPrincipal({'backtest.candle_pattern': {'ids': ['CP01']}, 'screener.candle_pattern': {'ids': ['CP02']},
                       'screener.preset': {'all': True}})
    with TestClient(app_as(settings, store, p)) as c:
        assert entries_of(c, 'candle_pattern') == [{'id': 'CP01', 'stage': 'released'}, {'id': 'CP02', 'stage': 'lab'}]
        assert entries_of(c, 'screener_preset') == [{'id': 'brk52', 'stage': 'lab'}]
        assert entries_of(c, 'indicator') == []


def test_an_unknown_kind_is_not_found_and_names_the_known_kinds(settings, store):
    with TestClient(app_as(settings, store, StubPrincipal({'*': True}))) as c:
        r = c.get('/api/v1/catalog/feature')
        assert r.status_code == 404
        error = r.json()['error']
        assert error['code'] == 'NOT_FOUND' and error['message']
        assert error['details'] == {'kind': 'feature', 'known_kinds': list(KINDS)}


def test_signed_out_is_unauthenticated(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for kind in ('indicator', 'feature'):
            r = c.get(f'/api/v1/catalog/{kind}')
            assert r.status_code == 401 and r.json()['error']['code'] == 'UNAUTHENTICATED'


def test_switch_off_sign_in_through_the_real_principal(settings, store):
    """The real Phase 1 principal: an owner EDGE_ADMIN_OWNERS does not list has no capability (an empty catalog); listed
    there (the conftest settings, as production's default) it holds `*` and every entry of the repository file."""
    with TestClient(create_app(dataclasses.replace(settings, admin_owners=('another-owner',)), store, FakeOrc())) as c:
        login(c)
        assert entries_of(c, 'indicator') == []
    admins = dataclasses.replace(settings, admin_owners=(settings.owner,))
    with TestClient(create_app(admins, store, FakeOrc())) as c:
        login(c)
        assert entries_of(c, 'flow_indicator') == releases.entries('flow_indicator')
        assert entries_of(c, 'indicator') == releases.entries('indicator')            # '*': every entry, a lab one too
