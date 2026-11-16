"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md section 4b, user decision 2026-11-16: "ketika user ID login,
kalau dia sudah save metric dan lain-lain, ... maka otomatis tersebut back in place"): an account's preferences and
saved items on the server, edge_bff.user_preferences (migration 20261116_003), restored on any device.

- GET /api/v1/preferences: every key of the principal's owner, {preferences: {key: {value, version, updated_at}},
  limits}.
- PUT /api/v1/preferences/{key} (writer): body {value, version}. version is the one the page read (omitted or null for
  a key the page has not seen); a stale version answers 409 PREFERENCE_CONFLICT with the current value and version in
  details.current, so the page merges and writes again. 201 when the key was created, else 200.
- Limits per owner (422 PREFERENCE_LIMIT, details.limit names which): KEYS keys, VALUE_BYTES bytes per value, TOTAL_BYTES
  for all values together (sizes as PostgreSQL stores the JSON text).

The key is a storage key of the page registry (shared/edge-session.ts STORAGE, class user and sync); the server checks
its shape only, so a new registry key needs no server change. Every statement names the owner.
"""
import asyncio
import json
import re

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from .errors import Refusal
from .principal import Principal

KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}')     # the migration's pref_key CHECK
KEYS = 64
VALUE_BYTES = 65536                                        # the migration's value CHECK
TOTAL_BYTES = 1048576
LIMITS = {'keys': KEYS, 'value_bytes': VALUE_BYTES, 'total_bytes': TOTAL_BYTES}


def invalid(field, why):
    return Refusal(422, 'INVALID_INPUT', {'fields': [field], 'reason': why})


def limit_reached(limit, needed=None):
    return Refusal(422, 'PREFERENCE_LIMIT', {'limit': limit, 'allowed': LIMITS[limit],
                                             **({'needed': needed} if needed is not None else {})})


def checked_key(key):
    if not KEY.fullmatch(key):
        raise invalid('key', 'A preference key is 1 to 64 letters, digits, . _ : or -, starting with a letter or digit.')
    return key


def checked_body(raw):
    """(value, version) of a PUT body: a JSON object with value (any JSON) and version (a positive whole number, or
    null/omitted for a new key); the value storable by PostgreSQL (no NUL, no unpaired surrogate)."""
    def refuse_constant(name):
        raise ValueError(name)
    try:
        body = json.loads(raw or b'null', parse_constant=refuse_constant)
    except (ValueError, RecursionError):
        raise invalid('body', 'Send a JSON object {"value": ..., "version": n}.') from None
    if not isinstance(body, dict) or 'value' not in body or set(body) - {'value', 'version'}:
        raise invalid('body', 'Send a JSON object with value and version only.')
    version = body.get('version')
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 1):
        raise invalid('version', 'version is the positive whole number the preference was read with, or null for a new key.')
    text = json.dumps(body['value'], ensure_ascii=False, separators=(',', ':'))
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise invalid('value', 'The value holds a character that cannot be stored (an unpaired surrogate).') from None
    if '\\u0000' in text:
        raise invalid('value', 'The value holds a character that cannot be stored (NUL).')
    return body['value'], version


def item_of(row):
    return {'value': row['value'], 'version': row['version'], 'updated_at': row['updated_at']}


class PreferenceStore:
    def __init__(self, store):
        self.store = store

    def all(self, owner):
        with self.store.connect() as c:
            return c.execute('''SELECT pref_key, value, version, updated_at FROM edge_bff.user_preferences
                WHERE owner_key=%s ORDER BY pref_key''', (owner,)).fetchall()

    def put(self, owner, key, value, version):
        """(row, created) after an optimistic write, serialised per owner (the limits count every key of the owner).
        Refusals: 409 PREFERENCE_CONFLICT (stale or missing version) with the current row, 422 PREFERENCE_LIMIT."""
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('preferences:' + owner,))
            size = c.execute('SELECT octet_length(%s::jsonb::text) AS n', (Jsonb(value),)).fetchone()['n']
            if size > VALUE_BYTES:
                raise limit_reached('value_bytes', size)
            current = c.execute('''SELECT pref_key, value, version, updated_at FROM edge_bff.user_preferences
                WHERE owner_key=%s AND pref_key=%s FOR UPDATE''', (owner, key)).fetchone()
            if (current['version'] if current else None) != version:
                raise Refusal(409, 'PREFERENCE_CONFLICT', {'key': key, 'current': jsonable_encoder(item_of(current))
                                                           if current else None})
            held = c.execute('''SELECT count(*) AS keys, coalesce(sum(octet_length(value::text)), 0) AS bytes
                FROM edge_bff.user_preferences WHERE owner_key=%s AND pref_key<>%s''', (owner, key)).fetchone()
            if current is None and held['keys'] + 1 > KEYS:
                raise limit_reached('keys', held['keys'] + 1)
            if held['bytes'] + size > TOTAL_BYTES:
                raise limit_reached('total_bytes', held['bytes'] + size)
            if current is None:
                return c.execute('''INSERT INTO edge_bff.user_preferences(owner_key, pref_key, value) VALUES (%s,%s,%s)
                    RETURNING pref_key, value, version, updated_at''', (owner, key, Jsonb(value))).fetchone(), True
            return c.execute('''UPDATE edge_bff.user_preferences SET value=%s, version=version+1, updated_at=now()
                WHERE owner_key=%s AND pref_key=%s RETURNING pref_key, value, version, updated_at''',
                             (Jsonb(value), owner, key)).fetchone(), False


class Preferences:
    def __init__(self, store):
        self.store = PreferenceStore(store)

    def routes(self, app, auth):
        @app.get('/api/v1/preferences')
        async def preferences(p: Principal = Depends(auth.principal)):
            rows = await asyncio.to_thread(self.store.all, p.owner_key)
            return JSONResponse(jsonable_encoder({'preferences': {r['pref_key']: item_of(r) for r in rows},
                                                  'limits': LIMITS}))

        @app.put('/api/v1/preferences/{key}')
        async def put_preference(key: str, request: Request, p: Principal = Depends(auth.writer)):
            value, version = checked_body(await request.body())
            row, created = await asyncio.to_thread(self.store.put, p.owner_key, checked_key(key), value, version)
            return JSONResponse(jsonable_encoder({'key': row['pref_key'], **item_of(row)}),
                                status_code=201 if created else 200)
