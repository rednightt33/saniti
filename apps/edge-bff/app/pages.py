"""EXEC-RADAR R6, EXEC-OVERVIEW O4: an EDGE page's published files, relayed to the owner's EDGE session.

The files of a page family (the Radar's, the Market Overview's; terminal-publisher PAGES) are presigned by terminal-api
for the EDGE gateway key only (POST /api/terminal/v1/<family>). This gateway, for the owner's EDGE session only, lists
them and relays their bytes, so a page reads everything from this origin (connect-src 'self') and no presigned URL
reaches the browser.

  GET /api/v1/<family>/index              {finished_at, files: {name: {sha256, bytes, rows, as_of}}}
  GET /api/v1/<family>/file/<name>?sha=   the file's gzip JSON bytes (Content-Encoding gzip), checked against the
                                          index's sha256; another sha answers 409 <FAMILY>_FILE_REPLACED

EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b "Page files", section 15): both routes need `<family>.view` (overview.view,
radar.view, watchlist.view), checked by the route's dependency before the handler, so before the process caches shared
by every user (the index, the bytes by sha) and before any terminal-api call. The browser keeps a file only with
`Cache-Control: private, no-cache` and its ETag: it asks again every time, and a `?sha=` request with a matching
If-None-Match is answered 304 only after the check (a year-long immutable copy would hand one user's files to the next
user of the same browser without asking the server). With EDGE_MULTIUSER off the configured owner holds '*'.

EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail"): every terminal-api call carries the principal's headers
(app/terminal_access.py headers: x-terminal-proxy-owner, x-terminal-capabilities), and a request carrying one of them is
refused 400 HEADER_NOT_ALLOWED (terminal_access.guard) before the caches. The shared index is read with the headers of
the principal whose request found it stale; the page files have no ticker or dataset of their own (the family's view
capability gates them).

Re-check fix round (track terminal; verification/edge_multiuser/fix_round/terminal.md):
- R1-1, R1-26, R2-4: every terminal-api answer goes through terminal_access.relayed: a 429 of a grant is 429
  LIMIT_REACHED with details.limit, retry_after_s and Retry-After (CONTRACT.md section 3), an answer terminal-api did
  not acknowledge for a capped principal is <FAMILY>_UNAVAILABLE, any other refusal <FAMILY>_UNAVAILABLE as before
  (logged with terminal-api's code).
- R1-31: the principal's headers are built on every request, before the shared caches, so what edge-bff refuses for a
  principal itself (a quota of 0, an owner key or a header terminal-api cannot take) is refused whether the caches are
  warm or cold.
- R1-5, R1-31: decided by the code and the contract (CONTRACT.md section 15: the caches are shared by every user; QA
  2026-11-14: bytes kept by sha256 so a reload asks no grant): terminal-api grants, counts and audits a page file for the
  principal whose request missed the caches, once per edge-bff process and sha256; a read served from the caches is
  counted against no one's Terminal quota and leaves no terminal-api audit row. That is lenient (it never counts more)
  and leaks nothing (the view capability is checked first). Per-reader counting, if Phase 4's usage counters need it,
  is edge-bff's own record, not a terminal-api call per hit (which would undo the cache).

Every refusal names its cause and the way out (AGENTS.md "Gates and evidence" (d)).
"""
from __future__ import annotations

import hashlib
import re
import time

import httpx
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from . import terminal_access
from .errors import refusal

SHA = re.compile(r'[0-9a-f]{64}')
INDEX_SECONDS = 30          # the index is read again at most this often (terminal-api caches state.json for 60 s)
# QA 2026-11-14: bytes already relayed are kept by sha256 (a file never changes under its sha), so a reload of the page
# asks terminal-api for no grant (each grant counts against the owner's terminal quota); CACHE_BYTES per page at most
CACHE_BYTES = 32 * 1024 * 1024


def messages(family, label, names):
    """The refusal texts of a page family, by code suffix."""
    return {
        'UNAVAILABLE': f'The {label} data could not be read from the terminal service. Try again in a minute; nothing '
                       'on this page changed.',
        # plain words only (CONTRACT.md 3; re-check R2-40 item 10): the code <FAMILY>_NOT_CONFIGURED tells the operator
        # that the terminal service's two settings are unset (app/config.py, settings.terminal_url)
        'NOT_CONFIGURED': f'The {label} is not available on this server right now. Nothing on this page changed; try '
                          'again later.',
        'INVALID_NAME': f'That is not a {label} file name. Names: {names}; GET /api/v1/{family}/index lists the '
                        'published ones.',
        'INVALID_SHA': 'The sha parameter must be the 64 lowercase hexadecimal characters of the file\'s sha256 as '
                       f'GET /api/v1/{family}/index lists it; leave it out to get the current file.',
        'FILE_NOT_PUBLISHED': f'This {label} file is not in the current publication. Read GET /api/v1/{family}/index '
                              'for the published files and dates.',
        'FILE_REPLACED': f'A newer {label} publication replaced this file. Read GET /api/v1/{family}/index again and '
                         'ask for the file with its new sha.',
        'FILE_DAMAGED': f'The {label} file read from storage does not match its published checksum. Try again in a '
                        f'minute; if it persists, the publisher must publish the {label} again (mode {family}).',
    }


class PageFiles:
    """One page family's index and files for the owner's session (routes)."""

    def __init__(self, settings, family, name, label, names, clock=time.monotonic):
        self.settings, self.family, self.name, self.label, self.clock = settings, family, name, label, clock
        self.prefix = family.upper()
        self.text = messages(family, label, names)
        self.http = None
        self.cached, self.cached_at = None, None
        self.bodies: dict[str, bytes] = {}                # sha256 -> gzip bytes relayed (oldest first)

    def failure(self, suffix, status, details=None):
        return JSONResponse(status_code=status, content={'error': {
            'code': f'{self.prefix}_{suffix}', 'message': self.text[suffix], **({'details': details} if details else {})}})

    async def aclose(self):
        if self.http is not None:
            await self.http.aclose()
            self.http = None

    def keep(self, sha, body):
        self.bodies.pop(sha, None)
        self.bodies[sha] = body
        while sum(len(b) for b in self.bodies.values()) > CACHE_BYTES and len(self.bodies) > 1:
            self.bodies.pop(next(iter(self.bodies)))

    async def fetch(self, url, size):
        """The object's bytes, read as a stream and never more than its published size (None if it is larger)."""
        out = bytearray()
        async with self.client().stream('GET', url) as r:
            if r.status_code != 200:
                return None
            async for chunk in r.aiter_bytes():
                out += chunk
                if len(out) > size:
                    return None
        return bytes(out)

    def client(self):
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=30)
        return self.http

    async def terminal(self, sent, method, path, body=None):
        """A terminal-api call with the headers `sent` (terminal_access.headers of the request's principal)."""
        return await self.client().request(
            method, f'{self.settings.terminal_url}/api/terminal/v1/{path}', content=body, headers=sent)

    async def index(self, p, sent, fresh=False):
        """terminal-api's index of the family, kept INDEX_SECONDS; None when terminal-api cannot answer (or answers
        without acknowledging the principal's header, terminal_access.relayed)."""
        now = self.clock()
        if not fresh and self.cached is not None and now - self.cached_at < INDEX_SECONDS:
            return self.cached
        try:
            answer = await self.terminal(sent, 'GET', self.family)
            data = answer.json() if answer.status_code == 200 else None
            if terminal_access.relayed(p, answer.status_code, data, answer.headers, self.family) is not None:
                data = None
        except (httpx.HTTPError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            return None
        self.cached, self.cached_at = data, now
        return data

    def routes(self, app, auth):
        family = self.family
        # Phase 3a: before the shared caches (docstring); Phase 3c: the page-sent terminal headers refused first
        view = terminal_access.guard(auth.need(f'{family}.view'))

        async def page_index(p=Depends(view)):
            if not self.settings.terminal_url:
                return self.failure('NOT_CONFIGURED', 503)
            sent = terminal_access.headers(self.settings, p)      # R1-31: the principal's own refusals, caches or not
            data = await self.index(p, sent)
            if data is None:
                return self.failure('UNAVAILABLE', 503)
            return JSONResponse({'finished_at': data.get('finished_at'), 'files': data['files']})

        async def page_file(name: str, request: Request, sha: str = "", p=Depends(view)):
            if not self.settings.terminal_url:
                return self.failure('NOT_CONFIGURED', 503)
            if not self.name.fullmatch(name):
                return self.failure('INVALID_NAME', 400, {'name': name[:64]})
            if sha and not SHA.fullmatch(sha):
                return self.failure('INVALID_SHA', 400, {'sha': sha[:80]})
            sent = terminal_access.headers(self.settings, p)      # R1-31: the principal's own refusals, caches or not
            if sha and request.headers.get('if-none-match') == f'"{sha[:32]}"':
                # the URL names the content and the capability was checked: the browser's copy stands (no index read,
                # no grant), as the year-long copy did before, but now only after the server's check
                return Response(status_code=304, headers={'ETag': f'"{sha[:32]}"', 'Cache-Control': 'private, no-cache'})
            data = await self.index(p, sent)
            if data is None:
                return self.failure('UNAVAILABLE', 503)
            entry = data['files'].get(name)
            if sha and (entry is None or entry.get('sha256') != sha):
                data = await self.index(p, sent, fresh=True) or data        # a publication may have come out since
                entry = data['files'].get(name)
            if entry is None:
                return self.failure('FILE_NOT_PUBLISHED', 404, {'name': name})
            if sha and entry.get('sha256') != sha:
                return self.failure('FILE_REPLACED', 409, {'name': name, 'sha256': entry.get('sha256')})
            current = entry.get('sha256')
            if not sha and request.headers.get('if-none-match') == f'"{str(current)[:32]}"':
                return Response(status_code=304, headers={'ETag': f'"{str(current)[:32]}"', 'Cache-Control': 'private, no-cache'})
            body = self.bodies.get(current)
            if body is None:
                try:
                    granted = await self.terminal(sent, 'POST', family, body=f'{{"names": ["{name}"]}}'.encode())
                    if granted.status_code == 404 and terminal_access.acknowledged(p, granted.headers):
                        return self.failure('FILE_REPLACED', 409, {'name': name})
                    try:
                        answer = granted.json()
                    except ValueError:
                        answer = None
                    refused = terminal_access.relayed(p, granted.status_code, answer, granted.headers, family)
                    if refused is not None and refused.code == 'LIMIT_REACHED':
                        # R1-26: the Terminal quota the page files count against (CONTRACT.md section 3)
                        return refusal(refused.status, refused.code, refused.details, refused.headers)
                    if refused is not None or granted.status_code != 200:
                        return self.failure('UNAVAILABLE', 503)
                    f = answer['files'][0]
                    # QA 2026-11-14: the grant names the file of the publication terminal-api reads now; when that is
                    # not the one this answer is for, the page reads the index again (never new bytes under an old sha)
                    if f.get('sha256') != current:
                        self.cached = None
                        return self.failure('FILE_REPLACED', 409, {'name': name, 'sha256': f.get('sha256')})
                    body = await self.fetch(f['url'], int(f.get('bytes') or entry.get('bytes') or 0))
                except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError):
                    return self.failure('UNAVAILABLE', 503)
                if body is None or hashlib.sha256(body).hexdigest() != current:
                    return self.failure('FILE_DAMAGED', 502, {'name': name})
                self.keep(current, body)
            return Response(body, media_type='application/json', headers={
                'Content-Encoding': 'gzip', 'ETag': f'"{current[:32]}"', 'Cache-Control': 'private, no-cache'})

        app.get(f'/api/v1/{family}/index', name=f'{family}_index')(page_index)
        app.get(f'/api/v1/{family}/file/{{name}}', name=f'{family}_file')(page_file)
