"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 8 and 8a): GET /api/v1/catalog/{kind}.

Answers {"kind", "entries": [{"id", "stage"}]} with the release file's entries of the kind (app/releases.py) that the
principal holds in any capability family of that kind: an entry is held when p.can("<family>:<id>") for one of the
kind's families (KIND_OF_FAMILY), so `*` holds every entry at any stage and a plan holding {"stages": ["released"]} on
terminal.indicator holds the released indicators only. An unknown kind answers 404 NOT_FOUND, with the known kinds in
details.known_kinds. Definitions stay in the page bundles until Phase 3 moves them behind this route.
"""
from fastapi import Depends

from . import releases
from .errors import Refusal
from .principal import Principal


def held(p, kind):
    families = releases.FAMILIES_OF_KIND[kind]
    return [e for e in releases.entries(kind) if any(p.can(f'{family}:{e["id"]}') for family in families)]


def routes(app, auth):
    @app.get('/api/v1/catalog/{kind}')
    async def catalog(kind: str, p: Principal = Depends(auth.principal)):
        if kind not in releases.KINDS:
            raise Refusal(404, 'NOT_FOUND', {'kind': kind, 'known_kinds': list(releases.KINDS)})
        return {'kind': kind, 'entries': held(p, kind)}
