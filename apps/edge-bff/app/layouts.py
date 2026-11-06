"""EDGE Terminal chart layouts (EXEC-TERMINAL-LAYOUTS, user 2026-11-06: "di akun edge. Tidak usah mengganti saham.").

The Terminal page saves its chart settings as named layouts of the signed-in owner in edge_bff.terminal_layouts
(migration 20261106_001) and opens them on whatever ticker is shown. edge-bff stores a layout's state as the page sent it:
it checks the shape (a JSON object of setting name -> string, the page's localStorage values) and the size, never the
meaning (the page drops a setting it no longer knows when it opens a layout).

Routes (session; writes also with the CSRF header, as /api/v1/screener):
  GET    /api/v1/terminal/layouts               {layouts: [Layout without state], limit}, the most recently opened first
  GET    /api/v1/terminal/layouts/{layout_id}   Layout with state
  PUT    /api/v1/terminal/layouts/{layout_id}   {name, state, summary?, revision?}: create (no revision) or replace
  PATCH  /api/v1/terminal/layouts/{layout_id}   {favorite?, opened?}: star it, or mark it opened (no revision)
  DELETE /api/v1/terminal/layouts/{layout_id}
Errors: {"error": {code, field?, message, details?}}: 422 INVALID_INPUT (a field the API does not take, a name, summary or
state out of shape, more than STATE_KEYS settings, text PostgreSQL cannot store: NUL or an unpaired surrogate) /
LIMIT_EXCEEDED (LAYOUT_LIMIT layouts, STATE_BYTES of state), 404 NOT_FOUND, 409 REVISION_CONFLICT (details.revision: the
stored one) / NAME_TAKEN, 503 LAYOUTS_NOT_READY (migration not applied). A body over 131,072 bytes is refused before it
reaches these routes (main.py, 413 REQUEST_TOO_LARGE).
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

LAYOUT_ID = re.compile(r'lay_[0-9a-f]{32}')         # migration 20261106_001; terminal src/data/layoutsApi.ts
SETTING = re.compile(r'ml\.[A-Za-z0-9_.-]{1,80}')   # a stored setting name of the Terminal page (localStorage key)
NAME_MAX = 120                                      # migration 20261106_001: 1-120, trimmed
SUMMARY_MAX = 120
STATE_BYTES = 65536                                 # migration 20261106_001 (octet_length(state::text))
STATE_KEYS = 64
LAYOUT_LIMIT = 50                                   # per owner, as the screener's 50 saved screens
SCHEMA_VERSION = 1
RETRY_SECONDS = 30
FIELDS = ('layout_id', 'name', 'summary', 'schema_version', 'favorite', 'revision', 'created_at', 'updated_at', 'opened_at')

MESSAGES = {
    'INVALID_INPUT': 'The request is not a valid layout request.',
    'NOT_FOUND': 'No such layout.',
    'REVISION_CONFLICT': 'The layout changed since it was read (another tab or device saved it): read it again.',
    'NAME_TAKEN': 'Another layout has this name: choose another name.',
    'LIMIT_EXCEEDED': 'A limit was reached.',
    'LAYOUTS_NOT_READY': 'Saved layouts are not available yet on this server. Try again in a few minutes; your chart is unchanged.',
}


class LayoutError(Exception):
    def __init__(self, status, error, headers=None):
        self.status, self.error, self.headers = status, error, headers
        super().__init__(error.get('code'))


def failure(code, status, field=None, message=None, details=None, headers=None):
    return LayoutError(status, {'code': code, **({'field': field} if field else {}), 'message': message or MESSAGES[code],
                                **({'details': details} if details else {})}, headers)


def invalid(field, message):
    return failure('INVALID_INPUT', 422, field, message)


def too_large(size=None):
    return failure('LIMIT_EXCEEDED', 422, 'state', f'A layout is at most {STATE_BYTES:,} bytes of settings: remove indicators.',
                   {'limit': 'layout_bytes', 'allowed': STATE_BYTES, **({'needed': size} if size else {})})


def storable(field, text):
    """Text PostgreSQL can store (QA round 3, L1: a NUL or an unpaired surrogate reached the database as a 503)"""
    if '\x00' in text or any('\ud800' <= ch <= '\udfff' for ch in text):
        raise invalid(field, f'{field} holds a character that cannot be stored (NUL or an unpaired surrogate)')
    return text


def checked_name(name):
    if not isinstance(name, str) or not name.strip():
        raise invalid('name', 'name is 1 to 120 characters')
    storable('name', name)
    name = ' '.join(name.split())
    if len(name) > NAME_MAX:
        raise invalid('name', f'name is at most {NAME_MAX} characters')
    return name


def checked_state(state):
    """The page's settings: {setting name: string value}, at most STATE_KEYS of them and STATE_BYTES of JSON."""
    if not isinstance(state, dict):
        raise invalid('state', 'state is a JSON object of setting name -> text')
    if len(state) > STATE_KEYS:
        raise invalid('state', f'state holds at most {STATE_KEYS} settings')
    for k, v in state.items():
        if not SETTING.fullmatch(k):
            raise invalid('state', f'{k[:40]!r} is not a Terminal setting name (ml.…)')
        if not isinstance(v, str):
            raise invalid('state', f'the value of {k} is text')
        storable('state', v)
    size = len(json.dumps(state, ensure_ascii=False, separators=(', ', ': ')).encode())
    if size > STATE_BYTES:
        raise too_large(size)
    return state


def layout_of(row, with_state=False):
    return jsonable_encoder({k: row[k] for k in FIELDS} | ({'state': row['state']} if with_state else {}))


class LayoutStore:
    """edge_bff.terminal_layouts through the house Store's connections. Every statement names the owner, so one owner
    never reads, replaces or deletes another's rows. A missing table is 503 LAYOUTS_NOT_READY; /ready never reads it."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise failure('LAYOUTS_NOT_READY', 503, headers={'Retry-After': str(RETRY_SECONDS)}) from e

    def list(self, owner):
        with self.connect() as c:
            return c.execute(f'''SELECT {", ".join(FIELDS)} FROM edge_bff.terminal_layouts WHERE owner_key=%s
                ORDER BY opened_at DESC, layout_id''', (owner,)).fetchall()

    def get(self, owner, layout_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM edge_bff.terminal_layouts WHERE owner_key=%s AND layout_id=%s',
                            (owner, layout_id)).fetchone()
        if not row:
            raise failure('NOT_FOUND', 404)
        return row

    def put(self, owner, layout_id, name, state, summary, revision):
        """Create (revision None) or replace (the revision it was read with), serialised per owner. (row, created)."""
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('layouts:' + owner,))
            row = c.execute('SELECT revision FROM edge_bff.terminal_layouts WHERE owner_key=%s AND layout_id=%s FOR UPDATE',
                            (owner, layout_id)).fetchone()
            try:
                if revision is None:
                    if row:
                        raise failure('REVISION_CONFLICT', 409, details={'revision': row['revision']})
                    held = c.execute('SELECT count(*) AS n FROM edge_bff.terminal_layouts WHERE owner_key=%s',
                                     (owner,)).fetchone()['n']
                    if held >= LAYOUT_LIMIT:
                        raise failure('LIMIT_EXCEEDED', 422, message=f'At most {LAYOUT_LIMIT} layouts: delete one before saving another.',
                                      details={'limit': 'layouts', 'allowed': LAYOUT_LIMIT, 'needed': held + 1})
                    created = c.execute('''INSERT INTO edge_bff.terminal_layouts(layout_id,owner_key,name,state,summary,schema_version)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (layout_id) DO NOTHING RETURNING *''',
                        (layout_id, owner, name, Jsonb(state), summary, SCHEMA_VERSION)).fetchone()
                    if created is None:
                        raise failure('REVISION_CONFLICT', 409)    # another owner's id: the same answer, nothing learned
                    return created, True
                if not row:
                    raise failure('NOT_FOUND', 404)
                if row['revision'] != revision:
                    raise failure('REVISION_CONFLICT', 409, 'revision', details={'revision': row['revision']})
                return c.execute('''UPDATE edge_bff.terminal_layouts SET name=%s,state=%s,summary=%s,schema_version=%s,
                        revision=revision+1,updated_at=now(),opened_at=now() WHERE owner_key=%s AND layout_id=%s RETURNING *''',
                        (name, Jsonb(state), summary, SCHEMA_VERSION, owner, layout_id)).fetchone(), False
            except psycopg.errors.UniqueViolation as e:
                if e.diag.constraint_name == 'terminal_layouts_owner_name':
                    raise failure('NAME_TAKEN', 409, 'name') from e
                raise
            except psycopg.errors.CheckViolation as e:
                if e.diag.constraint_name == 'terminal_layouts_state_size':
                    raise too_large() from e
                raise

    def mark(self, owner, layout_id, favorite, opened):
        sets = [*(['favorite=%s'] if favorite is not None else []), *(['opened_at=now()'] if opened else [])]
        with self.connect() as c:
            row = c.execute(f'''UPDATE edge_bff.terminal_layouts SET {", ".join(sets)} WHERE owner_key=%s AND layout_id=%s
                RETURNING {", ".join(FIELDS)}''', (*([favorite] if favorite is not None else []), owner, layout_id)).fetchone()
        if not row:
            raise failure('NOT_FOUND', 404)
        return row

    def delete(self, owner, layout_id):
        with self.connect() as c:
            gone = c.execute('DELETE FROM edge_bff.terminal_layouts WHERE owner_key=%s AND layout_id=%s',
                             (owner, layout_id)).rowcount
        if not gone:
            raise failure('NOT_FOUND', 404)


class Layouts:
    def __init__(self, settings, store):
        self.settings, self.store = settings, LayoutStore(store)

    @staticmethod
    async def body(request):
        raw = await request.body()           # at most 131,072 bytes: main.py refuses a larger body first (413)
        try:
            body = json.loads(raw or b'null')
        except (ValueError, RecursionError):
            raise invalid(None, 'The body is not JSON a layout can carry.')
        if not isinstance(body, dict):
            raise invalid(None, 'The body is a JSON object.')
        return body

    @staticmethod
    def layout_id(layout_id):
        if not LAYOUT_ID.fullmatch(layout_id):
            raise invalid('layout_id', 'layout_id is lay_ followed by 32 lowercase hexadecimal digits')
        return layout_id

    def routes(self, app, session, write):
        owner, store = self.settings.owner, self.store

        @app.exception_handler(LayoutError)
        async def layout_error(_, exc):
            return JSONResponse(status_code=exc.status, content={'error': exc.error}, headers=exc.headers)

        @app.get('/api/v1/terminal/layouts')
        async def layouts(_=Depends(session)):
            rows = await asyncio.to_thread(store.list, owner)
            return JSONResponse({'layouts': [layout_of(r) for r in rows], 'limit': LAYOUT_LIMIT})

        @app.get('/api/v1/terminal/layouts/{layout_id}')
        async def layout(layout_id: str, _=Depends(session)):
            return JSONResponse(layout_of(await asyncio.to_thread(store.get, owner, self.layout_id(layout_id)), True))

        @app.put('/api/v1/terminal/layouts/{layout_id}')
        async def put_layout(layout_id: str, request: Request, _=Depends(write)):
            body = await self.body(request)
            unknown = set(body) - {'name', 'state', 'summary', 'revision'}
            if unknown:
                raise invalid(sorted(unknown)[0], 'a layout has name, state, summary and revision only')
            summary = body.get('summary', '')
            if not isinstance(summary, str) or len(summary) > SUMMARY_MAX:
                raise invalid('summary', f'summary is text of at most {SUMMARY_MAX} characters')
            storable('summary', summary)
            revision = body.get('revision')
            if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 1):
                raise invalid('revision', 'revision is the positive whole number the layout was read with')
            row, created = await asyncio.to_thread(store.put, owner, self.layout_id(layout_id), checked_name(body.get('name')),
                                                   checked_state(body.get('state')), summary.strip(), revision)
            return JSONResponse(layout_of(row, True), status_code=201 if created else 200)

        @app.patch('/api/v1/terminal/layouts/{layout_id}')
        async def mark_layout(layout_id: str, request: Request, _=Depends(write)):
            body = await self.body(request)
            favorite, opened = body.get('favorite'), body.get('opened')
            if set(body) - {'favorite', 'opened'} or (favorite is not None and not isinstance(favorite, bool)) \
                    or opened not in (None, True) or (favorite is None and not opened):
                raise invalid(None, 'send favorite (true or false) and/or opened (true)')
            return JSONResponse(layout_of(await asyncio.to_thread(store.mark, owner, self.layout_id(layout_id), favorite, bool(opened))))

        @app.delete('/api/v1/terminal/layouts/{layout_id}', status_code=204)
        async def delete_layout(layout_id: str, _=Depends(write)):
            await asyncio.to_thread(store.delete, owner, self.layout_id(layout_id))
            return Response(status_code=204)
