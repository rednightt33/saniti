"""EXEC-RADAR R6 (user go 2026-11-14: "Ok go"; the Radar is an admin page, the owner's only): the Radar page's data.

The Radar's files (terminal-publisher radar.py; verification/radar/FILES.md) are presigned by terminal-api for the EDGE
gateway key only (POST /api/terminal/v1/radar). This gateway, for the owner's EDGE session only, lists them and relays
their bytes, so the page reads everything from this origin (connect-src 'self', as the Screener) and no presigned URL
reaches the browser.

  GET /api/v1/radar/index              {finished_at, files: {name: {sha256, bytes, rows, as_of}}}
  GET /api/v1/radar/file/<name>?sha=   the file's gzip JSON bytes (Content-Encoding gzip), checked against the index's
                                       sha256; with ?sha= equal to the published one it is cached for good (the URL
                                       names the content); another sha answers 409 RADAR_FILE_REPLACED (read the index
                                       again)

Every refusal names its cause and the way out (AGENTS.md "Gates and evidence" (d)).
"""
from __future__ import annotations

import hashlib
import re
import time

import httpx
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

NAME = re.compile(r'radar-(?:meta|days|board-[0-9]{4}-[0-9]{2}-[0-9]{2}|f-[a-z0-9_]{1,24})')   # publisher radar.NAME
SHA = re.compile(r'[0-9a-f]{64}')
INDEX_SECONDS = 30          # the index is read again at most this often (terminal-api caches state.json for 60 s)
# QA 2026-11-14: bytes already relayed are kept by sha256 (a file never changes under its sha), so a reload of the page
# asks terminal-api for no grant (each grant counts against the owner's terminal quota); RADAR_CACHE_BYTES at most
RADAR_CACHE_BYTES = 32 * 1024 * 1024
MESSAGES = {
    'RADAR_UNAVAILABLE': 'The Radar data could not be read from the terminal service. Try again in a minute; nothing '
                         'on this page changed.',
    'RADAR_NOT_CONFIGURED': 'The Radar needs the terminal service, which this server is not connected to '
                            '(EDGE_TERMINAL_URL and TERMINAL_PROXY_KEY on edge-bff).',
    'RADAR_INVALID_NAME': 'That is not a Radar file name. Names: radar-meta, radar-days, radar-board-YYYY-MM-DD, '
                          'radar-f-<filter>; GET /api/v1/radar/index lists the published ones.',
    'RADAR_INVALID_SHA': 'The sha parameter must be the 64 lowercase hexadecimal characters of the file\'s sha256 as '
                         'GET /api/v1/radar/index lists it; leave it out to get the current file.',
    'RADAR_QUOTA': 'The terminal account reached its file quota (shared with the Terminal). The Radar files already '
                   'shown stay; try again later in the hour.',
    'RADAR_FILE_NOT_PUBLISHED': 'This Radar file is not in the current publication. Read GET /api/v1/radar/index for '
                                'the published files and dates.',
    'RADAR_FILE_REPLACED': 'A newer Radar publication replaced this file. Read GET /api/v1/radar/index again and ask '
                           'for the file with its new sha.',
    'RADAR_FILE_DAMAGED': 'The Radar file read from storage does not match its published checksum. Try again in a '
                          'minute; if it persists, the publisher must publish the Radar again (mode radar).',
}


def failure(code, status, details=None):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': MESSAGES[code],
                                                               **({'details': details} if details else {})}})


class Radar:
    def __init__(self, settings, clock=time.monotonic):
        self.settings, self.clock = settings, clock
        self.http = None
        self.cached, self.cached_at = None, None
        self.bodies: dict[str, bytes] = {}                # sha256 -> gzip bytes relayed (oldest first)

    async def aclose(self):
        if self.http is not None:
            await self.http.aclose()
            self.http = None

    def keep(self, sha, body):
        self.bodies.pop(sha, None)
        self.bodies[sha] = body
        while sum(len(b) for b in self.bodies.values()) > RADAR_CACHE_BYTES and len(self.bodies) > 1:
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
        answer = await self.client().request(
            method, f'{self.settings.terminal_url}/api/terminal/v1/{path}', content=body,
            headers={'content-type': 'application/json', 'x-terminal-proxy-key': self.settings.terminal_proxy_key})
        return answer

    async def index(self, fresh=False):
        """terminal-api's Radar index, kept INDEX_SECONDS; None when terminal-api cannot answer."""
        now = self.clock()
        if not fresh and self.cached is not None and now - self.cached_at < INDEX_SECONDS:
            return self.cached
        try:
            answer = await self.terminal('GET', 'radar')
            data = answer.json() if answer.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            return None
        self.cached, self.cached_at = data, now
        return data

    def routes(self, app, session):
        @app.get('/api/v1/radar/index')
        async def radar_index(_=Depends(session)):
            if not self.settings.terminal_url:
                return failure('RADAR_NOT_CONFIGURED', 503)
            data = await self.index()
            if data is None:
                return failure('RADAR_UNAVAILABLE', 503)
            return JSONResponse({'finished_at': data.get('finished_at'), 'files': data['files']})

        @app.get('/api/v1/radar/file/{name}')
        async def radar_file(name: str, request: Request, sha: str = '', _=Depends(session)):
            if not self.settings.terminal_url:
                return failure('RADAR_NOT_CONFIGURED', 503)
            if not NAME.fullmatch(name):
                return failure('RADAR_INVALID_NAME', 400, {'name': name[:64]})
            if sha and not SHA.fullmatch(sha):
                return failure('RADAR_INVALID_SHA', 400, {'sha': sha[:80]})
            data = await self.index()
            if data is None:
                return failure('RADAR_UNAVAILABLE', 503)
            entry = data['files'].get(name)
            if sha and (entry is None or entry.get('sha256') != sha):
                data = await self.index(fresh=True) or data              # a publication may have come out since
                entry = data['files'].get(name)
            if entry is None:
                return failure('RADAR_FILE_NOT_PUBLISHED', 404, {'name': name})
            if sha and entry.get('sha256') != sha:
                return failure('RADAR_FILE_REPLACED', 409, {'name': name, 'sha256': entry.get('sha256')})
            current = entry.get('sha256')
            if not sha and request.headers.get('if-none-match') == f'"{str(current)[:32]}"':
                return Response(status_code=304, headers={'ETag': f'"{str(current)[:32]}"', 'Cache-Control': 'private, no-cache'})
            body = self.bodies.get(current)
            if body is None:
                try:
                    granted = await self.terminal('POST', 'radar', body=f'{{"names": ["{name}"]}}'.encode())
                    if granted.status_code == 404:
                        return failure('RADAR_FILE_REPLACED', 409, {'name': name})
                    if granted.status_code == 429:
                        return failure('RADAR_QUOTA', 429)
                    if granted.status_code != 200:
                        return failure('RADAR_UNAVAILABLE', 503)
                    f = granted.json()['files'][0]
                    # QA 2026-11-14: the grant names the file of the publication terminal-api reads now; when that is
                    # not the one this answer is for, the page reads the index again (never new bytes under an old sha)
                    if f.get('sha256') != current:
                        self.cached = None
                        return failure('RADAR_FILE_REPLACED', 409, {'name': name, 'sha256': f.get('sha256')})
                    body = await self.fetch(f['url'], int(f.get('bytes') or entry.get('bytes') or 0))
                except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, IndexError, TypeError):
                    return failure('RADAR_UNAVAILABLE', 503)
                if body is None or hashlib.sha256(body).hexdigest() != current:
                    return failure('RADAR_FILE_DAMAGED', 502, {'name': name})
                self.keep(current, body)
            return Response(body, media_type='application/json', headers={
                'Content-Encoding': 'gzip', 'ETag': f'"{current[:32]}"',
                'Cache-Control': 'private, max-age=31536000, immutable' if sha == current else 'private, no-cache'})
