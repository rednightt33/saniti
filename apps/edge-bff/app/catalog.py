"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 8 and 8a): GET /api/v1/catalog/{kind}.

Answers {"kind", "entries": [{"id", "stage"}]} with the release file's entries of the kind (app/releases.py) that the
principal holds in any capability family of that kind: an entry is held when p.can("<family>:<id>") for one of the
kind's families (KIND_OF_FAMILY), so `*` holds every entry at any stage and a plan holding {"stages": ["released"]} on
terminal.indicator holds the released indicators only. An unknown kind answers 404 NOT_FOUND, with the known kinds in
details.known_kinds. The definitions of released and preview items stay in the page bundles (a preview one marked
`release: 'preview'`); a lab item's definition and formula are never in a public bundle (3f, CONTRACT 8 "Lab code": the
page build filters the registries by stage, and the admin's page loads them from its app's lab route). The tab catalogs
list items with the same rule (tab_list): an item held back (releases.held_back: lab or preview) is listed only to a
principal who holds it, with its stage as `release`.
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
    never holds a lab item) and a preview one, which only a principal holding it by its id or `*` holds (an ungated item
    is never lab or preview, tests/test_releases.py; this keeps the rule closed if one were)."""
    stage = releases.stage_of(kind, item_id)
    if ungated(kind, item_id) and stage != releases.PREVIEW \
            and not (getattr(p, 'live', False) and stage == releases.LAB):
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
    # a family value {"all": true} holds no preview item (EXEC UD28): every item only while the kind has none
    return not releases.any_at(kind, releases.PREVIEW) and any(
        p.kinds.get(f) == 'items' and p.grants[f].get('all') is True for f in releases.FAMILIES_OF_KIND[kind])


def holds_every_item(p):
    """3f (CONTRACT.md 8 "Lab code"): whether the principal holds every item of every kind at any stage (holds_every for
    each of releases.KINDS). A page's lab build carries every item's definition and the lab formulas, so it goes only to
    a principal every catalog lists each of them to; one holding a lab item by its id or stage only is served the public
    build (fail closed)."""
    return all(holds_every(p, kind) for kind in releases.KINDS)


def held(p, kind):
    return [e for e in releases.entries(kind) if holds_entry(p, kind, e['id'])]


# 3f (EXEC option A item 4; CONTRACT 8a "Tab catalogs"; ERRORS M520): the tab catalogs the workers answer (the Screener's,
# the Backtest's) list items too. edge-bff decides each entry itself with the rule of this route: its release stage from
# the release file and the principal's hold from holds_entry. The workers' own mark access 'admin' (the point-in-time
# Flow versions) needs the right flow_point_in_time (rights.py), as before. A kept entry held back (lab or preview)
# carries its stage as `release`.
def tab_kind(item_id, kinds, fallback):
    """The release kind of a tab catalog's entry: the one of `kinds` listing the id (releases.kind_of), else `fallback`
    (an unlisted id is lab in every kind)."""
    return releases.kind_of(item_id, kinds) or fallback


def tab_hidden(p, kind, entry, point_in_time):
    """Whether a tab catalog's entry is left out for a principal: marked access 'admin' without the right
    flow_point_in_time (point_in_time: the principal's rights hold it), or an item held back (lab or preview,
    releases.held_back) that the principal does not hold (an id the release file does not list is lab; without a
    principal, p None, no held-back item is held)."""
    if entry.get('access') == 'admin' and not point_in_time:
        return True
    if releases.held_back(releases.stage_of(kind, entry['id'])):
        return p is None or not holds_entry(p, kind, entry['id'])
    return False


def tab_list(p, entries, kinds, fallback, point_in_time):
    """(the entries a principal sees, the ids left out): a tab catalog's list of items decided entry by entry
    (tab_hidden); an entry without a string id is not an item and stays as it is; a kept entry held back carries its
    stage as `release` ('lab' or 'preview')."""
    kept, out = [], set()
    for e in entries:
        if not (isinstance(e, dict) and isinstance(e.get('id'), str)):
            kept.append(e)
            continue
        kind = tab_kind(e['id'], kinds, fallback(e))
        stage = releases.stage_of(kind, e['id'])
        if tab_hidden(p, kind, e, point_in_time):
            out.add(e['id'])
        elif releases.held_back(stage):
            kept.append({**e, 'release': stage})
        else:
            kept.append(e)
    return kept, out


def routes(app, auth):
    # track guest: the Terminal reads which indicators the principal holds here, so a visitor (the guest plan's
    # principal, auth.visitor) reaches it too
    @app.get('/api/v1/catalog/{kind}')
    async def catalog(kind: str, p: Principal = Depends(auth.visitor)):
        if kind not in releases.KINDS:
            raise Refusal(404, 'NOT_FOUND', {'kind': kind, 'known_kinds': list(releases.KINDS)})
        return {'kind': kind, 'entries': held(p, kind)}
