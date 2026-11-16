"""EXEC-RADAR R6, EXEC-OVERVIEW O4: an EDGE page's published files, relayed to the owner's EDGE session.

The files of a page family (the Radar's, the Market Overview's; terminal-publisher PAGES) are presigned by terminal-api
for the EDGE gateway key only (POST /api/terminal/v1/<family>). This gateway, for the owner's EDGE session only, lists
them and relays their bytes, so a page reads everything from this origin (connect-src 'self') and no presigned URL
reaches the browser.

  GET /api/v1/<family>/index              {finished_at, files: {name: {sha256, bytes, rows, as_of}}}
  GET /api/v1/<family>/file/<name>?sha=   the file's gzip JSON bytes (Content-Encoding gzip), checked against the
                                          index's sha256; with ?sha= equal to the published one it is cached for good
                                          (the URL names the content); another sha answers 409 <FAMILY>_FILE_REPLACED

Every refusal names its cause and the way out (AGENTS.md "Gates and evidence" (d)).
"""
from __future__ import annotations

import hashlib
import re
import time

import httpx
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

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
        'NOT_CONFIGURED': f'The {label} needs the terminal service, which this server is not connected to '
                          '(EDGE_TERMINAL_URL and TERMINAL_PROXY_KEY on edge-bff).',
        'INVALID_NAME': f'That is not a {label} file name. Names: {names}; GET /api/v1/{family}/index lists the '
                        'published ones.',
        'INVALID_SHA': 'The sha parameter must be the 64 lowercase hexadecimal characters of the file\'s sha256 as '
                       f'GET /api/v1/{family}/index lists it; leave it out to get the current file.',
        'QUOTA': f'The terminal account reached its file quota (shared with the Terminal). The {label} files already '
                 'shown stay; try again later in the hour.',
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

    async def terminal(self, method, path, body=None):
        return await self.client().request(
            method, f'{self.settings.terminal_url}/api/terminal/v1/{path}', content=body,
            headers={'content-type': 'application/json', 'x-terminal-proxy-key': self.settings.terminal_proxy_key})

    async def index(self, fresh=False):
        """terminal-api's index of the family, kept INDEX_SECONDS; None when terminal-api cannot answer."""
        now = self.clock()
        if not fresh and self.cached is not None and now - self.cached_at < INDEX_SECONDS:
            return self.cached
        try:
            answer = await self.terminal('GET', self.family)
            data = answer.json() if answer.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            return None
        self.cached, self.cached_at = data, now
        return data

    def routes(self, app, auth):
        family = self.family

        async def page_index(_=Depends(auth.principal)):
            if not self.settings.terminal_url:
                return self.failure('NOT_CONFIGURED', 503)
            data = await self.index()
            if data is None:
                return self.failure('UNAVAILABLE', 503)
            return JSONResponse({'finished_at': data.get('finished_at'), 'files': data['files']})

        async def page_file(name: str, request: Request, sha: str = "", _=Depends(auth.principal)):
            if not self.settings.terminal_url:
                return self.failure('NOT_CONFIGURED', 503)
            if not self.name.fullmatch(name):
                return self.failure('INVALID_NAME', 400, {'name': name[:64]})
            if sha and not SHA.fullmatch(sha):
                return self.failure('INVALID_SHA', 400, {'sha': sha[:80]})
            data = await self.index()
            if data is None:
                return self.failure('UNAVAILABLE', 503)
            entry = data['files'].get(name)
            if sha and (entry is None or entry.get('sha256') != sha):
                data = await self.index(fresh=True) or data              # a publication may have come out since
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
                    granted = await self.terminal('POST', family, body=f'{{"names": ["{name}"]}}'.encode())
                    if granted.status_code == 404:
                        return self.failure('FILE_REPLACED', 409, {'name': name})
                    if granted.status_code == 429:
                        return self.failure('QUOTA', 429)
                    if granted.status_code != 200:
                        return self.failure('UNAVAILABLE', 503)
                    f = granted.json()['files'][0]
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
                'Content-Encoding': 'gzip', 'ETag': f'"{current[:32]}"',
                'Cache-Control': 'private, max-age=31536000, immutable' if sha == current else 'private, no-cache'})

        app.get(f'/api/v1/{family}/index', name=f'{family}_index')(page_index)
        app.get(f'/api/v1/{family}/file/{{name}}', name=f'{family}_file')(page_file)
