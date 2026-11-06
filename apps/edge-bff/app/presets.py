"""EDGE Terminal indicator presets (EXEC-IND-PRESETS, user 2026-11-06: "men-save indikator beserta dengan filternya";
"Q1 A" on the EDGE account, "Q2 A").

One indicator with its parameters, filters and style, saved by the signed-in owner under a name
(edge_bff.indicator_presets, migration 20261106_002) and added again from the Indicators window on any ticker. edge-bff
stores the config as the page sent it: it checks the shape ({params, style, on?, fold?}) and the size, never the meaning
(the page drops a parameter it no longer knows when it adds a preset, as it does for a saved chart).

Routes (session; writes also with the CSRF header, as /api/v1/terminal/layouts):
  GET    /api/v1/terminal/presets               {presets: [Preset with config], limit}, favourites first, then most recent use
  PUT    /api/v1/terminal/presets/{preset_id}   {name, def_id, config, summary?, revision?}: create (no revision) or replace
  PATCH  /api/v1/terminal/presets/{preset_id}   {favorite?, used?}: star it, or mark it used (no revision)
  DELETE /api/v1/terminal/presets/{preset_id}
Errors: {"error": {code, field?, message, details?}} (the layouts' shape and handler): 422 INVALID_INPUT by field /
LIMIT_EXCEEDED (PRESET_LIMIT presets, CONFIG_BYTES of config), 404 NOT_FOUND, 409 REVISION_CONFLICT / NAME_TAKEN,
503 PRESETS_NOT_READY (migration not applied). A body over 131,072 bytes is refused before the route (main.py, 413).
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

from .layouts import LayoutError, checked_name, invalid, storable

PRESET_ID = re.compile(r'ipr_[0-9a-f]{32}')         # migration 20261106_002; terminal src/data/presetsApi.ts
DEF_ID = re.compile(r'[A-Za-z0-9_]{1,40}')          # migration 20261106_002 (def_id)
CONFIG_KEYS = {'params', 'style', 'on', 'fold'}
CONFIG_BYTES = 16384                                 # migration 20261106_002 (octet_length(config::text))
SUMMARY_MAX = 300
PRESET_LIMIT = 100
SCHEMA_VERSION = 1
RETRY_SECONDS = 30
FIELDS = ('preset_id', 'name', 'def_id', 'config', 'summary', 'schema_version', 'favorite', 'revision', 'created_at',
          'updated_at', 'used_at')
MESSAGES = {
    'INVALID_INPUT': 'The request is not a valid preset request.',
    'NOT_FOUND': 'No such preset.',
    'REVISION_CONFLICT': 'The preset changed since it was read (another tab or device saved it): read it again.',
    'NAME_TAKEN': 'Another preset has this name: choose another name.',
    'LIMIT_EXCEEDED': 'A limit was reached.',
    'PRESETS_NOT_READY': 'Saved presets are not available yet on this server. Try again in a few minutes; your chart is unchanged.',
}


def failure(code, status, field=None, message=None, details=None, headers=None):
    return LayoutError(status, {'code': code, **({'field': field} if field else {}), 'message': message or MESSAGES[code],
                                **({'details': details} if details else {})}, headers)


def too_large(size=None):
    return failure('LIMIT_EXCEEDED', 422, 'config', f'A preset is at most {CONFIG_BYTES:,} bytes of settings.',
                   {'limit': 'preset_bytes', 'allowed': CONFIG_BYTES, **({'needed': size} if size else {})})


def checked_text_tree(value, depth=0):
    """Every text in the config can be stored (no NUL, no unpaired surrogate); at most 8 levels deep"""
    if depth > 8:
        raise invalid('config', 'config is at most 8 levels deep')
    if isinstance(value, str):
        storable('config', value)
    elif isinstance(value, dict):
        for k, v in value.items():
            storable('config', k)
            checked_text_tree(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            checked_text_tree(v, depth + 1)


def checked_config(config):
    """The page's indicator settings: {params: object, style: object, on?: bool, fold?: bool}"""
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS:
        raise invalid('config', 'config is an object of params, style, on and fold')
    if not isinstance(config.get('params'), dict) or not isinstance(config.get('style', {}), dict):
        raise invalid('config', 'config.params (and config.style) are objects')
    for k in ('on', 'fold'):
        if k in config and not isinstance(config[k], bool):
            raise invalid('config', f'config.{k} is true or false')
    checked_text_tree(config)
    size = len(json.dumps(config, ensure_ascii=False, separators=(', ', ': ')).encode())
    if size > CONFIG_BYTES:
        raise too_large(size)
    return config


def preset_of(row):
    return jsonable_encoder({k: row[k] for k in FIELDS})


class PresetStore:
    """edge_bff.indicator_presets; every statement names the owner. A missing table is 503 PRESETS_NOT_READY."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise failure('PRESETS_NOT_READY', 503, headers={'Retry-After': str(RETRY_SECONDS)}) from e

    def list(self, owner):
        with self.connect() as c:
            return c.execute(f'''SELECT {", ".join(FIELDS)} FROM edge_bff.indicator_presets WHERE owner_key=%s
                ORDER BY favorite DESC, used_at DESC, preset_id''', (owner,)).fetchall()

    def put(self, owner, preset_id, name, def_id, config, summary, revision):
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('presets:' + owner,))
            row = c.execute('SELECT revision FROM edge_bff.indicator_presets WHERE owner_key=%s AND preset_id=%s FOR UPDATE',
                            (owner, preset_id)).fetchone()
            try:
                if revision is None:
                    if row:
                        raise failure('REVISION_CONFLICT', 409, details={'revision': row['revision']})
                    held = c.execute('SELECT count(*) AS n FROM edge_bff.indicator_presets WHERE owner_key=%s',
                                     (owner,)).fetchone()['n']
                    if held >= PRESET_LIMIT:
                        raise failure('LIMIT_EXCEEDED', 422, message=f'At most {PRESET_LIMIT} presets: delete one before saving another.',
                                      details={'limit': 'presets', 'allowed': PRESET_LIMIT, 'needed': held + 1})
                    created = c.execute('''INSERT INTO edge_bff.indicator_presets(preset_id,owner_key,name,def_id,config,summary,schema_version)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (preset_id) DO NOTHING RETURNING *''',
                        (preset_id, owner, name, def_id, Jsonb(config), summary, SCHEMA_VERSION)).fetchone()
                    if created is None:
                        raise failure('REVISION_CONFLICT', 409)    # another owner's id: the same answer, nothing learned
                    return created, True
                if not row:
                    raise failure('NOT_FOUND', 404)
                if row['revision'] != revision:
                    raise failure('REVISION_CONFLICT', 409, 'revision', details={'revision': row['revision']})
                return c.execute('''UPDATE edge_bff.indicator_presets SET name=%s,def_id=%s,config=%s,summary=%s,schema_version=%s,
                        revision=revision+1,updated_at=now(),used_at=now() WHERE owner_key=%s AND preset_id=%s RETURNING *''',
                        (name, def_id, Jsonb(config), summary, SCHEMA_VERSION, owner, preset_id)).fetchone(), False
            except psycopg.errors.UniqueViolation as e:
                if e.diag.constraint_name == 'indicator_presets_owner_name':
                    raise failure('NAME_TAKEN', 409, 'name') from e
                raise
            except psycopg.errors.CheckViolation as e:
                if e.diag.constraint_name == 'indicator_presets_config_size':
                    raise too_large() from e
                raise

    def mark(self, owner, preset_id, favorite, used):
        sets = [*(['favorite=%s'] if favorite is not None else []), *(['used_at=now()'] if used else [])]
        with self.connect() as c:
            row = c.execute(f'''UPDATE edge_bff.indicator_presets SET {", ".join(sets)} WHERE owner_key=%s AND preset_id=%s
                RETURNING {", ".join(FIELDS)}''', (*([favorite] if favorite is not None else []), owner, preset_id)).fetchone()
        if not row:
            raise failure('NOT_FOUND', 404)
        return row

    def delete(self, owner, preset_id):
        with self.connect() as c:
            gone = c.execute('DELETE FROM edge_bff.indicator_presets WHERE owner_key=%s AND preset_id=%s',
                             (owner, preset_id)).rowcount
        if not gone:
            raise failure('NOT_FOUND', 404)


class Presets:
    def __init__(self, settings, store):
        self.settings, self.store = settings, PresetStore(store)

    @staticmethod
    async def body(request):
        try:
            body = json.loads(await request.body() or b'null')
        except (ValueError, RecursionError):
            raise invalid(None, 'The body is not JSON a preset can carry.')
        if not isinstance(body, dict):
            raise invalid(None, 'The body is a JSON object.')
        return body

    @staticmethod
    def preset_id(preset_id):
        if not PRESET_ID.fullmatch(preset_id):
            raise invalid('preset_id', 'preset_id is ipr_ followed by 32 lowercase hexadecimal digits')
        return preset_id

    def routes(self, app, session, write):
        owner, store = self.settings.owner, self.store      # LayoutError answers through the layouts' handler

        @app.get('/api/v1/terminal/presets')
        async def presets(_=Depends(session)):
            rows = await asyncio.to_thread(store.list, owner)
            return JSONResponse({'presets': [preset_of(r) for r in rows], 'limit': PRESET_LIMIT})

        @app.put('/api/v1/terminal/presets/{preset_id}')
        async def put_preset(preset_id: str, request: Request, _=Depends(write)):
            body = await self.body(request)
            unknown = set(body) - {'name', 'def_id', 'config', 'summary', 'revision'}
            if unknown:
                raise invalid(sorted(unknown)[0], 'a preset has name, def_id, config, summary and revision only')
            def_id = body.get('def_id')
            if not isinstance(def_id, str) or not DEF_ID.fullmatch(def_id):
                raise invalid('def_id', 'def_id is the indicator id: 1 to 40 letters, digits or _')
            summary = body.get('summary', '')
            if not isinstance(summary, str) or len(summary) > SUMMARY_MAX:
                raise invalid('summary', f'summary is text of at most {SUMMARY_MAX} characters')
            storable('summary', summary)
            revision = body.get('revision')
            if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 1):
                raise invalid('revision', 'revision is the positive whole number the preset was read with')
            row, created = await asyncio.to_thread(store.put, owner, self.preset_id(preset_id), checked_name(body.get('name')),
                                                   def_id, checked_config(body.get('config')), summary.strip(), revision)
            return JSONResponse(preset_of(row), status_code=201 if created else 200)

        @app.patch('/api/v1/terminal/presets/{preset_id}')
        async def mark_preset(preset_id: str, request: Request, _=Depends(write)):
            body = await self.body(request)
            favorite, used = body.get('favorite'), body.get('used')
            if set(body) - {'favorite', 'used'} or (favorite is not None and not isinstance(favorite, bool)) \
                    or used not in (None, True) or (favorite is None and not used):
                raise invalid(None, 'send favorite (true or false) and/or used (true)')
            return JSONResponse(preset_of(await asyncio.to_thread(store.mark, owner, self.preset_id(preset_id), favorite, bool(used))))

        @app.delete('/api/v1/terminal/presets/{preset_id}', status_code=204)
        async def delete_preset(preset_id: str, _=Depends(write)):
            await asyncio.to_thread(store.delete, owner, self.preset_id(preset_id))
            return Response(status_code=204)
