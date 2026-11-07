"""EDGE Terminal drawings on the EDGE account (EXEC-DRAW-PANES, user 2026-11-07: "semua gambar harus di simpan di akun
EDGE, sama seperti trading view"; "3 jalankan dulu").

The trend lines, rays, brush strokes and texts the signed-in owner draws, one set per ticker and place
(edge_bff.terminal_drawings, migration 20261107_001): 'chart' (the price chart), 'flow' (the Flow Timeline) or 'pane_' and
an indicator pane's 16 hexadecimal digits. edge-bff stores the drawing library's list as the page sent it: it checks the
shape (a list of objects) and the size, never the meaning.

Routes (session; writes also with the CSRF header, as /api/v1/terminal/layouts):
  GET    /api/v1/terminal/drawings?ticker=BBRI          {sets: [{ticker, set_id, drawings, revision, updated_at}], limits}
  PUT    /api/v1/terminal/drawings/{ticker}/{set_id}    {drawings, revision?}: create (no revision) or replace
  DELETE /api/v1/terminal/drawings/{ticker}/{set_id}
Errors: {"error": {code, field?, message, details?}} (the layouts' shape and handler): 422 INVALID_INPUT by field /
LIMIT_EXCEEDED (SET_LIMIT sets, SET_BYTES per set), 404 NOT_FOUND, 409 REVISION_CONFLICT, 503 DRAWINGS_NOT_READY
(migration not applied). A body over 131,072 bytes is refused before the route (main.py, 413).
"""
import asyncio
from contextlib import contextmanager
import json
import re

import psycopg
from fastapi import Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from .layouts import LayoutError, invalid, storable

TICKER = re.compile(r'[A-Z0-9]{1,12}')                   # terminal-api's ticker rule; migration 20261107_001
SET_ID = re.compile(r'chart|flow|pane_[0-9a-f]{16}')     # migration 20261107_001; terminal src/data/drawingsApi.ts
SET_BYTES = 100000                                        # migration 20261107_001 (octet_length(drawings::text))
SET_LIMIT = 5000                                          # sets per owner (tickers x places)
DEPTH = 10
SCHEMA_VERSION = 1
RETRY_SECONDS = 30
FIELDS = ('ticker', 'set_id', 'drawings', 'schema_version', 'revision', 'created_at', 'updated_at')
MESSAGES = {
    'INVALID_INPUT': 'The request is not a valid drawings request.',
    'NOT_FOUND': 'No such set of drawings.',
    'REVISION_CONFLICT': 'These drawings changed since they were read (another tab or device saved them): read them again.',
    'LIMIT_EXCEEDED': 'A limit was reached.',
    'DRAWINGS_NOT_READY': 'Saved drawings are not available yet on this server. Try again in a few minutes; your chart is unchanged.',
}


def failure(code, status, field=None, message=None, details=None, headers=None):
    return LayoutError(status, {'code': code, **({'field': field} if field else {}), 'message': message or MESSAGES[code],
                                **({'details': details} if details else {})}, headers)


def too_large(size=None):
    return failure('LIMIT_EXCEEDED', 422, 'drawings', f'The drawings of one place are at most {SET_BYTES:,} bytes: remove a few, '
                   'or a long brush stroke, and they save again.',
                   {'limit': 'set_bytes', 'allowed': SET_BYTES, **({'needed': size} if size else {})})


def checked_tree(value, depth=0):
    """Every text can be stored (no NUL, no unpaired surrogate); at most DEPTH levels deep"""
    if depth > DEPTH:
        raise invalid('drawings', f'drawings are at most {DEPTH} levels deep')
    if isinstance(value, str):
        storable('drawings', value)
    elif isinstance(value, dict):
        for k, v in value.items():
            storable('drawings', k)
            checked_tree(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            checked_tree(v, depth + 1)


def checked_drawings(drawings):
    """The drawing library's list: a list of objects, within the size"""
    if not isinstance(drawings, list) or not all(isinstance(d, dict) for d in drawings):
        raise invalid('drawings', 'drawings is a list of drawing objects')
    checked_tree(drawings)
    size = len(json.dumps(drawings, ensure_ascii=False, separators=(', ', ': ')).encode())
    if size > SET_BYTES:
        raise too_large(size)
    return drawings


def set_of(row):
    return jsonable_encoder({k: row[k] for k in FIELDS})


class DrawingStore:
    """edge_bff.terminal_drawings; every statement names the owner. A missing table is 503 DRAWINGS_NOT_READY."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise failure('DRAWINGS_NOT_READY', 503, headers={'Retry-After': str(RETRY_SECONDS)}) from e

    def list(self, owner, ticker):
        with self.connect() as c:
            return c.execute(f'''SELECT {", ".join(FIELDS)} FROM edge_bff.terminal_drawings WHERE owner_key=%s AND ticker=%s
                ORDER BY set_id''', (owner, ticker)).fetchall()

    def put(self, owner, ticker, set_id, drawings, revision):
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('drawings:' + owner,))
            row = c.execute('''SELECT revision FROM edge_bff.terminal_drawings WHERE owner_key=%s AND ticker=%s AND set_id=%s
                FOR UPDATE''', (owner, ticker, set_id)).fetchone()
            try:
                if revision is None:
                    if row:
                        raise failure('REVISION_CONFLICT', 409, details={'revision': row['revision']})
                    held = c.execute('SELECT count(*) AS n FROM edge_bff.terminal_drawings WHERE owner_key=%s',
                                     (owner,)).fetchone()['n']
                    if held >= SET_LIMIT:
                        raise failure('LIMIT_EXCEEDED', 422, message=f'Drawings are kept for at most {SET_LIMIT:,} places '
                                      '(tickers, Flow Timelines and panes): clear the drawings of a ticker you no longer use.',
                                      details={'limit': 'sets', 'allowed': SET_LIMIT, 'needed': held + 1})
                    return c.execute('''INSERT INTO edge_bff.terminal_drawings(owner_key,ticker,set_id,drawings,schema_version)
                        VALUES (%s,%s,%s,%s,%s) RETURNING *''', (owner, ticker, set_id, Jsonb(drawings), SCHEMA_VERSION)).fetchone(), True
                if not row:
                    raise failure('NOT_FOUND', 404)
                if row['revision'] != revision:
                    raise failure('REVISION_CONFLICT', 409, 'revision', details={'revision': row['revision']})
                return c.execute('''UPDATE edge_bff.terminal_drawings SET drawings=%s,schema_version=%s,revision=revision+1,
                        updated_at=now() WHERE owner_key=%s AND ticker=%s AND set_id=%s RETURNING *''',
                        (Jsonb(drawings), SCHEMA_VERSION, owner, ticker, set_id)).fetchone(), False
            except psycopg.errors.CheckViolation as e:
                if e.diag.constraint_name == 'terminal_drawings_size':
                    raise too_large() from e
                raise

    def delete(self, owner, ticker, set_id):
        with self.connect() as c:
            gone = c.execute('DELETE FROM edge_bff.terminal_drawings WHERE owner_key=%s AND ticker=%s AND set_id=%s',
                             (owner, ticker, set_id)).rowcount
        if not gone:
            raise failure('NOT_FOUND', 404)


class Drawings:
    def __init__(self, settings, store):
        self.settings, self.store = settings, DrawingStore(store)

    @staticmethod
    def ticker(ticker):
        if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
            raise invalid('ticker', 'ticker is 1 to 12 capital letters or digits')
        return ticker

    @staticmethod
    def set_id(set_id):
        if not SET_ID.fullmatch(set_id):
            raise invalid('set_id', 'set_id is chart, flow, or pane_ followed by 16 lowercase hexadecimal digits')
        return set_id

    def routes(self, app, session, write):
        owner, store = self.settings.owner, self.store      # LayoutError answers through the layouts' handler

        @app.get('/api/v1/terminal/drawings')
        async def drawings(ticker: str = '', _=Depends(session)):
            rows = await asyncio.to_thread(store.list, owner, self.ticker(ticker))
            return JSONResponse({'sets': [set_of(r) for r in rows], 'limits': {'set_bytes': SET_BYTES, 'sets': SET_LIMIT}})

        @app.put('/api/v1/terminal/drawings/{ticker}/{set_id}')
        async def put_drawings(ticker: str, set_id: str, request: Request, _=Depends(write)):
            try:
                body = json.loads(await request.body() or b'null')
            except (ValueError, RecursionError):
                raise invalid(None, 'The body is not JSON drawings can carry.')
            if not isinstance(body, dict):
                raise invalid(None, 'The body is a JSON object.')
            unknown = set(body) - {'drawings', 'revision'}
            if unknown:
                raise invalid(sorted(unknown)[0], 'a set of drawings has drawings and revision only')
            revision = body.get('revision')
            if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 1):
                raise invalid('revision', 'revision is the positive whole number the drawings were read with')
            row, created = await asyncio.to_thread(store.put, owner, self.ticker(ticker), self.set_id(set_id),
                                                   checked_drawings(body.get('drawings')), revision)
            return JSONResponse(set_of(row), status_code=201 if created else 200)

        @app.delete('/api/v1/terminal/drawings/{ticker}/{set_id}', status_code=204)
        async def delete_drawings(ticker: str, set_id: str, _=Depends(write)):
            await asyncio.to_thread(store.delete, owner, self.ticker(ticker), self.set_id(set_id))
            return Response(status_code=204)
