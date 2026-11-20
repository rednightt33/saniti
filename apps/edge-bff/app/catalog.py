"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 8 and 8a): GET /api/v1/catalog/{kind}.

Answers {"kind", "entries": [{"id", "stage"}]} with the release file's entries of the kind (app/releases.py) that the
principal holds in any capability family of that kind: an entry is held when p.can("<family>:<id>") for one of the
kind's families (KIND_OF_FAMILY), so `*` holds every entry at any stage and a plan holding {"stages": ["released"]} on
terminal.indicator holds the released indicators only. An unknown kind answers 404 NOT_FOUND, with the known kinds in
details.known_kinds. Definitions stay in the page bundles until Phase 3 moves them behind this route.
"""
import json
from pathlib import Path

from fastapi import Depends

from . import releases
from .errors import Refusal
from .principal import EVERYTHING, Principal

# EXEC-MU-ACCOUNTS (CONTRACT.md 8b O3b-2, re-check R1-35, user 2026-11-19 "1a": the Screener conditions on the attributes
# every result row and /universe show are not gated by id): the Screener catalog itself (the image copies the file to
# the same place, Dockerfile), whose universe entries name the /universe row field that shows their value (`row`); the
# screener core reads the same entries (screener/src/core/catalog.ts SHOWN_ATTRIBUTES, the worker's allow walk skips them)
SCREENER_METRICS = Path(__file__).resolve().parent.parent / 'screener' / 'src' / 'core' / 'screener-metrics.json'
SCREENER_METRIC = 'screener_metric'


def shown_attributes(path=SCREENER_METRICS):
    """The ids of the universe attributes whose value every Screener answer shows (the catalog entries of kind
    'universe' that name their `row`), read once at import: a file that cannot be read stops edge-bff at start."""
    try:
        metrics = json.loads(Path(path).read_text())['metrics']
        return frozenset(m['id'] for m in metrics if m.get('kind') == 'universe' and isinstance(m.get('row'), str))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f'{path}: the Screener catalog cannot be read ({e.__class__.__name__}); the image copies '
                           'screener/src/core/screener-metrics.json beside app/ (Dockerfile)') from None


SHOWN_ATTRIBUTES = shown_attributes()


def ungated(kind, item_id):
    """Whether an item is part of its tab itself, held by every principal whatever its plan: a universe attribute every
    Screener answer shows (SHOWN_ATTRIBUTES). The one rule of allow.allow_of (what the workers are told) and holds_entry
    (what the catalogs list), so the two never differ."""
    return kind == SCREENER_METRIC and item_id in SHOWN_ATTRIBUTES


def holds_entry(p, kind, item_id):
    """Whether the principal holds an item of a kind in any capability family of that kind: the one rule of every answer
    that lists items (this route, and the tab catalogs that list them: the Screener's presets, re-check R1-32). An item
    that is part of its tab (ungated) is held by everyone, except a lab-stage one on the live site (principal.live_view
    never holds a lab item)."""
    if ungated(kind, item_id) and not (getattr(p, 'live', False) and releases.stage_of(kind, item_id) == releases.LAB):
        return True
    return any(p.can(f'{family}:{item_id}') for family in releases.FAMILIES_OF_KIND[kind])


def holds_every(p, kind):
    """Whether the principal holds every item of a kind whatever its id or stage ('*', or a family value {"all": true}),
    so nothing of that kind is left out of an answer. Never on the live site: its principal holds no lab item, '*'
    included (principal.live_view; CONTRACT.md 17), so each item is decided on its own there (3c check C3-13), as
    allow.allow_of does."""
    if getattr(p, 'live', False):
        return False
    if EVERYTHING in p.capabilities or p.grants.get(EVERYTHING) is True:
        return True
    return any(p.kinds.get(f) == 'items' and p.grants[f].get('all') is True for f in releases.FAMILIES_OF_KIND[kind])


def grant_key(p, kind):
    """A cache key part of what decides a principal's items of a kind: None when it holds every one, else its grants
    of the kind's families (two principals with the same grants hold the same items)."""
    if holds_every(p, kind):
        return None
    return json.dumps({f: p.grants.get(f) for f in releases.FAMILIES_OF_KIND[kind]}, sort_keys=True,
                      separators=(',', ':'))


def held(p, kind):
    return [e for e in releases.entries(kind) if holds_entry(p, kind, e['id'])]


def routes(app, auth):
    # track guest: the Terminal reads which indicators the principal holds here, so a visitor (the guest plan's
    # principal, auth.visitor) reaches it too
    @app.get('/api/v1/catalog/{kind}')
    async def catalog(kind: str, p: Principal = Depends(auth.visitor)):
        if kind not in releases.KINDS:
            raise Refusal(404, 'NOT_FOUND', {'kind': kind, 'known_kinds': list(releases.KINDS)})
        return {'kind': kind, 'entries': held(p, kind)}
