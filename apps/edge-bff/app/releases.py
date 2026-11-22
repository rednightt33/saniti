"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 8 and 8a): the release stage of every catalog item.

The stages are hand-kept data in apps/edge-bff/catalog/releases.json (no script writes it; the image copies catalog/
beside app/, so the file is ../catalog/releases.json from this package both in the repository and at /app/catalog in
the image). The file is read once, when this module is imported, so a malformed file stops edge-bff at start with a
message naming the problem rather than refusing items at run time.

- `KINDS`: the item kinds of the file (each with its registry, tests/test_releases.py). The ids of a kind are derived
  there from the registries the product reads; flow_indicator also takes the Backtest's legacy flow cards
  (backtest/src/core/catalog.ts LEGACY, group 'flow': fnet, broker, top5), read from the TypeScript source as data
  (CONTRACT.md 8b "3b follow-up"). The image carries only this file, never the registries, so the derivation is the
  test's, the stages the file's.
- `KIND_OF_FAMILY`: the capability family of an item (`<tab>.<item kind>`, the part before ':' of
  `terminal.indicator:I01`) mapped to its kind; the id space of a kind is shared by every tab.
- `stage_of(kind, item_id)`: 'released' or 'lab'; an id the file does not list reads 'lab' at run time (fail closed). That
  is no way in: no item may be at the lab stage yet (tests/test_releases.py refuses an unlisted one and names what must
  be closed first, FUTURE_PLAN.md "Before the first lab item or tab"), so a new item enters the file as "released" with
  the user's go, or stays off main.
- `entries(kind)`: the file's entries of a kind, in file order, as [{"id", "stage"}].
- `tab_stage(tab)`: the live switch of a tab (the first part of a capability key, `terminal` of `terminal.view`; the
  user, 2026-11-20, EXEC option A: development happens on the beta and reaches the live site only on request). The file's
  optional `tabs` list holds [{"id", "stage"}]; a tab it does not list is 'lab' too, so a new tab is on the beta only
  until it is marked released (principal.beta_only, auth/config hidden_tabs), whatever plan grants it.
  tests/test_live_switch.py fails when a capability tab or a page of the shell has no entry.
"""
import hashlib
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / 'catalog' / 'releases.json'
SCHEMA_VERSION = 1
STAGES = ('lab', 'released')
LAB = 'lab'
KINDS = ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric', 'screener_preset')
KIND_OF_FAMILY = {
    # the indicator and Flow items of every tab are granted by the Terminal's families (3b follow-up, user decision
    # 2026-11-18; migration 20261118_001 removed backtest/screener.indicator and backtest/screener.flow_indicator)
    'terminal.indicator': 'indicator', 'terminal.flow_indicator': 'flow_indicator',
    'backtest.candle_pattern': 'candle_pattern', 'screener.candle_pattern': 'candle_pattern',
    'screener.metric': 'screener_metric',
    'screener.preset': 'screener_preset',
}
FAMILIES_OF_KIND = {kind: tuple(f for f, k in KIND_OF_FAMILY.items() if k == kind) for kind in KINDS}
TAB = re.compile(r'[a-z][a-z0-9_]{0,31}')


class ReleaseFileError(ValueError):
    """The release file cannot be used; the message names the file, the item and how to fix it."""


class Releases:
    """The parsed release file: (kind, id) -> stage, and each kind's entries in file order."""

    def __init__(self, data, source='releases.json'):
        def fail(why):
            raise ReleaseFileError(f'{source}: {why}')
        if not isinstance(data, dict):
            fail('the file must be a JSON object {"schema_version": 1, "note": "...", "items": [...]}')
        if data.get('schema_version') != SCHEMA_VERSION:
            fail(f'schema_version must be {SCHEMA_VERSION}, found {data.get("schema_version")!r}')
        extra = set(data) - {'schema_version', 'note', 'items', 'tabs'}
        if extra:
            fail(f'unknown top-level keys {sorted(extra)}; only schema_version, note, items and tabs are allowed')
        items = data.get('items')
        if not isinstance(items, list):
            fail('items must be a list of {"kind", "id", "stage"}')
        self._stage, self._entries = {}, {kind: [] for kind in KINDS}
        for n, item in enumerate(items):
            where = f'items[{n}]'
            if not isinstance(item, dict) or set(item) != {'kind', 'id', 'stage'}:
                fail(f'{where} must be an object with exactly kind, id and stage, found {item!r}')
            kind, item_id, stage = item['kind'], item['id'], item['stage']
            if kind not in KINDS:
                fail(f'{where} has the unknown kind {kind!r}; the kinds are {", ".join(KINDS)}')
            if not isinstance(item_id, str) or not item_id or item_id != item_id.strip():
                fail(f'{where} needs a non-empty id without surrounding spaces, found {item_id!r}')
            if stage not in STAGES:
                fail(f'{where} ({kind} {item_id}) has the unknown stage {stage!r}; a stage is "lab" or "released"')
            if (kind, item_id) in self._stage:
                fail(f'{where} repeats {kind} {item_id!r}; keep one entry per kind and id')
            self._stage[(kind, item_id)] = stage
            self._entries[kind].append({'id': item_id, 'stage': stage})
        # required (LIVE_PROMOTION.md section 3): an unlisted tab is lab, so a file without its tabs would hold every
        # tab off the live site; a missing list is refused at load (the deploy then fails its health check and the
        # running one stays) instead of switching the site off
        tabs = data.get('tabs')
        if not isinstance(tabs, list):
            fail('tabs must be a list of {"id", "stage"}, one per tab: an unlisted tab is lab, so a file without tabs '
                 'would switch every tab off on the live site (LIVE_PROMOTION.md)')
        self._tabs = {}
        for n, tab in enumerate(tabs):
            where = f'tabs[{n}]'
            if not isinstance(tab, dict) or set(tab) != {'id', 'stage'}:
                fail(f'{where} must be an object with exactly id and stage, found {tab!r}')
            if not isinstance(tab['id'], str) or not TAB.fullmatch(tab['id']):
                fail(f'{where} needs a tab name (lowercase letters, digits, _), found {tab["id"]!r}')
            if tab['stage'] not in STAGES:
                fail(f'{where} ({tab["id"]}) has the unknown stage {tab["stage"]!r}; a stage is "lab" or "released"')
            if tab['id'] in self._tabs:
                fail(f'{where} repeats the tab {tab["id"]!r}; keep one entry per tab')
            self._tabs[tab['id']] = tab['stage']
        # a short fingerprint of every (kind, id, stage) and tab stage: part of the principal's version
        # (X-Edge-Entitlements), so a deploy that moves an item between lab and released reaches open pages' catalog
        # caches (C1/C2 Phase 2)
        self.digest = hashlib.sha256(json.dumps(sorted([f'{k}\t{i}\t{st}' for (k, i), st in self._stage.items()]
                                                       + [f'tab\t{t}\t{st}' for t, st in self._tabs.items()]),
                                                separators=(',', ':')).encode()).hexdigest()[:12]

    def stage_of(self, kind, item_id):
        return self._stage.get((kind, item_id), LAB)

    def kind_of(self, item_id, kinds):
        return next((k for k in kinds if (k, item_id) in self._stage), None)

    def tab_stage(self, tab):
        return self._tabs.get(tab, LAB)

    def lab_tabs(self):
        return frozenset(t for t, st in self._tabs.items() if st == LAB)

    def tabs(self):
        return dict(self._tabs)

    def entries(self, kind):
        if kind not in KINDS:
            raise KeyError(kind)
        return [dict(e) for e in self._entries[kind]]


def load(path=PATH):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ReleaseFileError(f'{path}: the release file is missing (the image copies apps/edge-bff/catalog to '
                               '/app/catalog)') from None
    except json.JSONDecodeError as exc:
        raise ReleaseFileError(f'{path}: not valid JSON ({exc})') from None
    return Releases(data, str(path))


CURRENT = load()


def stage_of(kind: str, item_id: str) -> str:
    """'released' or 'lab' of an item; an id (or kind) the file does not list is 'lab'."""
    return CURRENT.stage_of(kind, item_id)


def entries(kind):
    """The release file's entries of a kind ([{"id", "stage"}], file order); KeyError for an unknown kind."""
    return CURRENT.entries(kind)


def kind_of(item_id, kinds):
    """The first of `kinds` whose entries list the id, or None: an id the file does not list is lab in any kind (3f, a
    tab catalog's entry whose list holds several kinds; the ids of those kinds do not repeat across them)."""
    return CURRENT.kind_of(item_id, kinds)


def tab_stage(tab: str) -> str:
    """The live switch of a tab: 'released' or 'lab'; a tab the file does not list is 'lab' (beta only)."""
    return CURRENT.tab_stage(tab)


def lab_tabs():
    """The tabs the file lists at the lab stage (the live site hides them, auth/config hidden_tabs)."""
    return CURRENT.lab_tabs()
