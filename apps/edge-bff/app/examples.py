"""EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; CONTRACT.md 8b "3e";
ERRORS M527): each data page as it opens, with the data of one past date, for a principal holding <tab>.example: the
free plan, and the guest plan (a visitor who is not signed in, on a site with guests). Every click on the page asks to
sign in (the guest) or to upgrade (an account): the page's view-only layer and the shell's box. The user: "kayak
semacam static HTML di hari tersebut saja".

  GET /api/v1/examples/<tab>/index             {finished_at, as_of, files: {name: {sha256, bytes, rows, as_of}}}
  GET /api/v1/examples/<tab>/file/<name>?sha=  the file's gzip JSON bytes (Content-Encoding gzip), the shape the page
                                               reads from its live route; another sha answers 409 EXAMPLE_FILE_REPLACED

The files are the rows of edge_bff.example_files (migration 20261121_001), written once by the capture job
(verification/edge_multiuser/example_mode/capture_job.py, apps/terminal-publisher/examples.py: the files of the page's
opening view cut at that date, none naming a later one). They are read from the database at most every REFRESH_SECONDS
per tab and process and served from this process's memory, so a request reads neither the database nor terminal-api:
the ceiling of all visitors together (EDGE_GUEST_CALLS_PER_HOUR) counts the Terminal's calls to terminal-api and does
not apply here.

The guarantee is these routes: they hand out only the example's files, and only to a principal holding the tab's
<tab>.example (auth.need(..., guests=True), before the caches); a page's live routes still need <tab>.view, and the
browser keeps a file only with `Cache-Control: private, no-cache` and its ETag (app/pages.py). The shell opens a tab in
example mode when its index answers 200 (static/edge-app.js ExampleTabPage), so a tab without rows, or a principal
without the capability, gets the locked page as before. Every refusal names its cause and the way on (AGENTS.md "Gates
and evidence" (d)).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from .errors import failure_class

logger = logging.getLogger('edge_bff.examples')

# the tabs whose page reads an example in this build (the page's own example mode: src/main.ts of each); a tab joins
# with its page
TABS = {'radar': 'Radar'}
NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')          # edge_bff.example_files.name (example_files_name)
SHA = re.compile(r'[0-9a-f]{64}')
REFRESH_SECONDS = 300                                   # a capture shows within this long; nothing changes otherwise

LIST_SQL = ('SELECT name, as_of::text AS as_of, rows, bytes, sha256, made_at FROM edge_bff.example_files '
            'WHERE tab = %s ORDER BY name')
BODIES_SQL = 'SELECT name, sha256, body FROM edge_bff.example_files WHERE tab = %s AND sha256 = ANY(%s)'


def messages(label):
    return {
        'EXAMPLE_NOT_READY': f'The example of the {label} is not ready yet. Sign in or upgrade to use the {label} itself.',
        'EXAMPLE_UNAVAILABLE': f'The example of the {label} could not be read right now. Try again in a minute.',
        'EXAMPLE_INVALID_NAME': f'That is not a file of the {label} example. GET the example\'s index for its files.',
        'EXAMPLE_INVALID_SHA': 'The sha parameter must be the 64 lowercase hexadecimal characters of the file\'s sha256 '
                               'as the example\'s index lists it; leave it out to get the current file.',
        'EXAMPLE_FILE_NOT_FOUND': f'This file is not part of the {label} example. GET the example\'s index for its files.',
        'EXAMPLE_FILE_REPLACED': f'The {label} example was captured again. Read its index again and ask for the file '
                                 'with its new sha.',
    }


class Examples:
    """The example files of every tab of TABS, kept in memory (module docstring)."""

    def __init__(self, store, clock=time.monotonic):
        self.store, self.clock = store, clock
        self.kept: dict[str, dict] = {}                 # tab -> {at, index, bodies: {name: (sha256, bytes)}}
        self.locks = {tab: asyncio.Lock() for tab in TABS}

    def read(self, tab, held):
        """The tab's rows now: (index, bodies), the bodies read only for a sha256 not held already (blocking)."""
        with self.store.connect() as c:
            rows = c.execute(LIST_SQL, (tab,)).fetchall()
            want = [r['sha256'] for r in rows if held.get(r['name'], (None,))[0] != r['sha256']]
            fresh = {r['name']: (r['sha256'], bytes(r['body'])) for r in c.execute(BODIES_SQL, (tab, want)).fetchall()} \
                if want else {}
        bodies = {}
        for r in rows:
            sha, body = fresh.get(r['name']) or held[r['name']]
            if sha != r['sha256'] or hashlib.sha256(body).hexdigest() != sha or len(body) != r['bytes']:
                raise ValueError(f'example file {tab}/{r["name"]} does not match its sha256')
            bodies[r['name']] = (sha, body)
        if not rows:
            return None, {}
        days = sorted({r['as_of'] for r in rows})
        index = {'finished_at': max(r['made_at'] for r in rows).isoformat(), 'as_of': days[-1],
                 'files': {r['name']: {'sha256': r['sha256'], 'bytes': r['bytes'], 'rows': r['rows'], 'as_of': r['as_of']}
                           for r in rows}}
        return index, bodies

    async def current(self, tab):
        """The tab's kept example, read again when older than REFRESH_SECONDS; a failed read keeps the last good one
        (None when there never was one). Raises when nothing was ever read and the read fails."""
        kept = self.kept.get(tab)
        if kept is not None and self.clock() - kept['at'] < REFRESH_SECONDS:
            return kept
        async with self.locks[tab]:
            kept = self.kept.get(tab)
            if kept is not None and self.clock() - kept['at'] < REFRESH_SECONDS:
                return kept
            try:
                index, bodies = await asyncio.to_thread(self.read, tab, kept['bodies'] if kept else {})
            except Exception as e:  # noqa: BLE001 - logged by class; the last good copy stands
                logger.warning(json.dumps({'event': 'example_read_failed', 'tab': tab, 'error': failure_class(e)}))
                if kept is None:
                    raise
                kept['at'] = self.clock()                 # ask again after REFRESH_SECONDS, not on every request
                return kept
            kept = {'at': self.clock(), 'index': index, 'bodies': bodies}
            self.kept[tab] = kept
            return kept

    def routes(self, app, auth):
        for tab, label in TABS.items():
            self.tab_routes(app, auth, tab, label)

    def tab_routes(self, app, auth, tab, label):
        text = messages(label)
        need = auth.need(f'{tab}.example', guests=True)   # before the kept files (module docstring)

        def failure(code, status, details=None):
            return JSONResponse(status_code=status, content={'error': {
                'code': code, 'message': text[code], 'details': {'tab': tab, **(details or {})}}})

        async def kept_or_failure():
            try:
                kept = await self.current(tab)
            except Exception:  # noqa: BLE001 - logged in current()
                return None, failure('EXAMPLE_UNAVAILABLE', 503)
            if kept['index'] is None:
                return None, failure('EXAMPLE_NOT_READY', 404)
            return kept, None

        async def example_index(p=Depends(need)):
            kept, refused = await kept_or_failure()
            if refused is not None:
                return refused
            return JSONResponse(kept['index'], headers={'Cache-Control': 'private, no-cache'})

        async def example_file(name: str, request: Request, sha: str = '', p=Depends(need)):
            if not NAME.fullmatch(name):
                return failure('EXAMPLE_INVALID_NAME', 400, {'name': name[:64]})
            if sha and not SHA.fullmatch(sha):
                return failure('EXAMPLE_INVALID_SHA', 400, {'sha': sha[:80]})
            if sha and request.headers.get('if-none-match') == f'"{sha[:32]}"':
                # the capability was checked (the dependency) and the URL names the content: the browser's copy stands
                return Response(status_code=304, headers={'ETag': f'"{sha[:32]}"', 'Cache-Control': 'private, no-cache'})
            kept, refused = await kept_or_failure()
            if refused is not None:
                return refused
            held = kept['bodies'].get(name)
            if held is None:
                return failure('EXAMPLE_FILE_NOT_FOUND', 404, {'name': name})
            current, body = held
            if sha and sha != current:
                return failure('EXAMPLE_FILE_REPLACED', 409, {'name': name, 'sha256': current})
            if not sha and request.headers.get('if-none-match') == f'"{current[:32]}"':
                return Response(status_code=304, headers={'ETag': f'"{current[:32]}"', 'Cache-Control': 'private, no-cache'})
            return Response(body, media_type='application/json', headers={
                'Content-Encoding': 'gzip', 'ETag': f'"{current[:32]}"', 'Cache-Control': 'private, no-cache'})

        app.get(f'/api/v1/examples/{tab}/index', name=f'{tab}_example_index')(example_index)
        app.get(f'/api/v1/examples/{tab}/file/{{name}}', name=f'{tab}_example_file')(example_file)
