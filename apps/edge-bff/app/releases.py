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
- `stage_of(kind, item_id)`: 'released' or 'lab'; an id the file does not list is 'lab' (a new item starts in the lab).
- `entries(kind)`: the file's entries of a kind, in file order, as [{"id", "stage"}].
"""
import hashlib
import json
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
        extra = set(data) - {'schema_version', 'note', 'items'}
        if extra:
            fail(f'unknown top-level keys {sorted(extra)}; only schema_version, note and items are allowed')
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
        # a short fingerprint of every (kind, id, stage): part of the principal's version (X-Edge-Entitlements), so a
        # deploy that moves an item between lab and released reaches open pages' catalog caches (C1/C2 Phase 2)
        self.digest = hashlib.sha256(json.dumps(sorted(f'{k}\t{i}\t{st}' for (k, i), st in self._stage.items()),
                                                separators=(',', ':')).encode()).hexdigest()[:12]

    def stage_of(self, kind, item_id):
        return self._stage.get((kind, item_id), LAB)

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
