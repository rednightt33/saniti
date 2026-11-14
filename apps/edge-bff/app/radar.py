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
from fastapi import Depends
from fastapi.responses import JSONResponse, Response

NAME = re.compile(r'radar-(?:meta|days|board-\d{4}-\d{2}-\d{2}|f-[a-z0-9_]{1,24})')   # publisher radar.NAME
SHA = re.compile(r'[0-9a-f]{64}')
INDEX_SECONDS = 30          # the index is read again at most this often (terminal-api caches state.json for 60 s)
MESSAGES = {
    'RADAR_UNAVAILABLE': 'The Radar data could not be read from the terminal service. Try again in a minute; nothing '
                         'on this page changed.',
    'RADAR_NOT_CONFIGURED': 'The Radar needs the terminal service, which this server is not connected to '
                            '(EDGE_TERMINAL_URL and TERMINAL_PROXY_KEY on edge-bff).',
    'RADAR_INVALID_NAME': 'That is not a Radar file name. Names: radar-meta, radar-days, radar-board-YYYY-MM-DD, '
                          'radar-f-<filter>; GET /api/v1/radar/index lists the published ones.',
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
        async def radar_file(name: str, sha: str = '', _=Depends(session)):
            if not self.settings.terminal_url:
                return failure('RADAR_NOT_CONFIGURED', 503)
            if not NAME.fullmatch(name) or (sha and not SHA.fullmatch(sha)):
                return failure('RADAR_INVALID_NAME', 400, {'name': name[:64]})
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
            try:
                granted = await self.terminal('POST', 'radar', body=f'{{"names": ["{name}"]}}'.encode())
                if granted.status_code == 404:
                    return failure('RADAR_FILE_REPLACED', 409, {'name': name})
                if granted.status_code != 200:
                    return failure('RADAR_UNAVAILABLE', 503)
                f = granted.json()['files'][0]
                stored = await self.client().request('GET', f['url'])
            except (httpx.HTTPError, ValueError, KeyError, IndexError):
                return failure('RADAR_UNAVAILABLE', 503)
            body = stored.content
            if stored.status_code != 200 or hashlib.sha256(body).hexdigest() != f.get('sha256'):
                return failure('RADAR_FILE_DAMAGED', 502, {'name': name})
            return Response(body, media_type='application/json', headers={
                'Content-Encoding': 'gzip', 'ETag': f'"{f["sha256"][:32]}"',
                'Cache-Control': 'private, max-age=31536000, immutable' if sha else 'private, no-cache'})
