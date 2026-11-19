"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 8 and 8a): GET /api/v1/catalog/{kind}.

Answers {"kind", "entries": [{"id", "stage"}]} with the release file's entries of the kind (app/releases.py) that the
principal holds in any capability family of that kind: an entry is held when p.can("<family>:<id>") for one of the
kind's families (KIND_OF_FAMILY), so `*` holds every entry at any stage and a plan holding {"stages": ["released"]} on
terminal.indicator holds the released indicators only. An unknown kind answers 404 NOT_FOUND, with the known kinds in
details.known_kinds. Definitions stay in the page bundles until Phase 3 moves them behind this route.
"""
import json

from fastapi import Depends

from . import releases
from .errors import Refusal
from .principal import EVERYTHING, Principal


def holds_entry(p, kind, item_id):
    """Whether the principal holds an item of a kind in any capability family of that kind: the one rule of every answer
    that lists items (this route, and the tab catalogs that list them: the Screener's presets, re-check R1-32)."""
    return any(p.can(f'{family}:{item_id}') for family in releases.FAMILIES_OF_KIND[kind])


def holds_every(p, kind):
    """Whether the principal holds every item of a kind whatever its id or stage ('*', or a family value {"all": true}),
    so nothing of that kind is left out of an answer."""
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
