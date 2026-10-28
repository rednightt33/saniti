"""EDGE screener in edge-bff (EXEC-SCREENER, go 2026-10-28; report API CONTRACT section 8, TARGET ARCHITECTURE 6.14 and
6.16, PAGE LOAD SEQUENCE 6c.5): the public /api/v1/screener routes, the relay to the private screener-worker (its
catalog, universe, run, preview, validate and counts) and the store of the owner's saved items and watchlist (migration
20261028_001). edge-bff computes nothing: it relays the worker's answers as the worker gave them and reads of them only
the fields named here (of every answer its versions; of a validation its definition_hash; of an error its code, field,
message and details). Wire types: apps/edge-bff/screener/src/core/contract.ts."""
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
import functools
import gzip
import hashlib
import json
import logging
import re
import time

import httpx
import psycopg
from fastapi import Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from .backtest import (CONTROL_TIMEOUT, PREVIEW_PAGES, Backtests, BacktestError, CallerGone, PreviewReplaced, accepts_gzip,
                       dumps, error_of, loads, preview_order)

logger = logging.getLogger('edge_bff.screener')

ITEM_ID = re.compile(r'scr_[0-9a-f]{32}')          # migration 20261028_001; contract.ts ITEM_ID
TICKER = re.compile(r'[A-Z0-9]{1,12}')             # terminal-api's ticker rule (migration 20261028_001; contract.ts TICKER)
HEX64 = re.compile(r'[0-9a-f]{64}')
KINDS = ('screen', 'metric')
TABLES = ('screener_items', 'watchlist_items')
SCHEMA_VERSION = 1                                  # contract.ts SCHEMA_VERSION
WORKER_KEY_HEADER = 'x-screener-worker-key'         # contract.ts WORKER_KEY_HEADER
NAME_MAX = 120                                      # migration 20261028_001: length 1-120, trimmed
DEFINITION_BYTES = 65536                            # migration 20261028_001 (octet_length(definition::text)); report 8.9
REQUEST_BYTES = 131072                              # main.py protections (the house body cap); report 8.9
# Report 8.4: edge-bff asks the worker's /health for its versions at most every 60 s and refetches the catalog and the
# universe only when they changed (the Backtest's 60 s catalog time-to-live replaced by a version check).
HEALTH_SECONDS = 60
# P12 (a), user 2026-10-28; values set in Phase 1 (report 13 P12: "PROPOSED: the PIN_LIMIT precedent, at most 500
# each"; report 11b: SCREENER_MAX_COUNTS is at least SCREEN_LIMIT, so every saved screen is counted in one counts call,
# initially 50). SCREEN_LIMIT holds for each kind: at most 50 saved screens and 50 My metrics per owner.
SCREEN_LIMIT = 50
WATCHLIST_LIMIT = 500                               # store.py PIN_LIMIT precedent (500)
# Not derivable: the Retry-After of 503 SCREENER_NOT_READY. A missing table waits for a migration (minutes at least);
# a worker without a snapshot that names no wait of its own loads one in seconds to a few minutes (report 6.5, 11b S14).
TABLES_RETRY_SECONDS = 60
WORKER_RETRY_SECONDS = 10
GZIP_MIN_BYTES = 1024          # smaller answers go as they are (gzip would add more than it saves)
INLINE_BYTES = 65536           # larger answers are parsed and packed in a thread, not on the event loop
REVIEWS_KEPT = 4096            # re-validation results kept in memory (per definition and registry versions)
# The universe a My metric (one test) is validated in: the required fields of contract.ts UniverseDef only, so the
# validation is the test's own (the worker checks the test as it checks a condition of a screen).
METRIC_UNIVERSE = {'security_types': ['stock'], 'traded_on_eval_date': True, 'exclude_price_breaks': True}
METRIC_CONDITION = 'conditions[0].test'

# Report 8.8: every refusal edge-bff itself gives names the field where there is one and the fix (AGENTS.md "Gates and
# evidence" (d)); the worker's refusals are relayed as it gave them.
MESSAGES = {
    'SCREENER_DISABLED': 'The screener is switched off on this environment.',
    'SCREENER_NOT_READY': 'The screener is starting; retry after the stated seconds.',
    'SCREENER_UNAVAILABLE': 'The screener service cannot be reached; retry shortly.',
    'SCREEN_REPLACED': 'A newer request replaced this one.',
    'PREVIEW_REPLACED': 'A newer request replaced this one.',
    'NOT_FOUND': 'This saved item no longer exists; reload the list.',
    'REVISION_CONFLICT': 'This item was changed or saved elsewhere; reload it, or save it as a copy.',
    'NAME_TAKEN': 'A saved item of this kind already has this name; choose another name, or open that item and replace it.',
    'REQUEST_TOO_LARGE': 'The definition is too large: remove conditions or filters.',
}
REPLACED = {'run': 'SCREEN_REPLACED', 'preview': 'PREVIEW_REPLACED'}


def failure(code, status, field=None, message=None, details=None, headers=None):
    error = {'code': code, **({'field': field} if field else {}), 'message': message or MESSAGES[code],
             **({'details': details} if details else {})}
    return ScreenerError(status, error, headers)


class ScreenerError(Exception):
    """An answer in the contract's error shape {"error": {code, field?, message?, details?}} with its HTTP status (and
    headers: Retry-After of 503 SCREENER_NOT_READY)."""
    def __init__(self, status, error, headers=None):
        self.status, self.error, self.headers = status, error, headers
        super().__init__(error.get('code'))


def invalid(field, message):
    return failure('INVALID_INPUT', 422, field, message)


class WorkerUnavailable(Exception):
    """The worker did not answer as its API says: no connection, a server error, our key refused, or not JSON."""


class WorkerTimeout(WorkerUnavailable):
    """The worker's own 504 TIMEOUT (the call took longer than its SCREENER_DEADLINE_MS): relayed as 504."""
    def __init__(self, error):
        self.error = error
        super().__init__(error['code'])


class WorkerNotReady(WorkerUnavailable):
    """The worker's own 503 SCREENER_NOT_READY (no snapshot loaded yet), with the seconds it names: relayed as 503 with
    Retry-After."""
    def __init__(self, error, retry_after):
        self.error, self.retry_after = error, retry_after
        super().__init__(error['code'])


async def parsed(raw):
    """loads(raw), in a thread when the answer is large (a whole-universe run answer reaches a few MB of JSON)."""
    return loads(raw) if len(raw) <= INLINE_BYTES else await asyncio.to_thread(loads, raw)


def seconds_of(value):
    """A Retry-After value in whole seconds, 1 to 3600, or None."""
    try:
        seconds = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return min(max(seconds, 1), 3600)


class ScreenerWorker:
    """The private screener-worker (report 8.11): every route but /health behind x-screener-worker-key, a private host
    only. Every call is awaited on the event loop (httpx.AsyncClient), never in a thread: a run may wait for the worker
    up to its deadline, and calls holding threads of the default pool would hold up every request that checks the
    session there (main.py session; the backtest.py WorkerClient.acall rule)."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client      # made on first use, on the loop that uses it

    async def call(self, method, path, body=None, timeout=None, key=True):
        """(status, raw JSON bytes, parsed JSON) of one call whose answer is the worker's: its 504 TIMEOUT is
        WorkerTimeout, its 503 SCREENER_NOT_READY WorkerNotReady, any other server error, our key refused (401) or an
        answer that is not JSON WorkerUnavailable."""
        if self.client is None:
            self.client = httpx.AsyncClient(base_url=self.settings.screener_worker_url, timeout=CONTROL_TIMEOUT,
                                            follow_redirects=False, trust_env=False)
        headers = {WORKER_KEY_HEADER: self.settings.screener_worker_key} if key else {}
        if body is not None:
            headers['content-type'] = 'application/json'
        try:
            response = await self.client.request(method, path, content=dumps(body) if body is not None else None,
                                                 headers=headers, timeout=timeout or CONTROL_TIMEOUT)
            raw = response.content
        except httpx.HTTPError as e:        # no connection, a timeout, a broken gzip stream
            raise WorkerUnavailable() from e
        status = response.status_code
        try:
            data = await parsed(raw)
        except ValueError:
            data = None
        found = error_of(data)
        if status == 504 and found and found['code'] == 'TIMEOUT':
            raise WorkerTimeout(found)
        if status == 503 and found and found['code'] == 'SCREENER_NOT_READY':
            details = found.get('details') if isinstance(found.get('details'), dict) else {}
            retry = seconds_of(response.headers.get('retry-after')) or seconds_of(details.get('retry_after_seconds'))
            raise WorkerNotReady(found, retry or WORKER_RETRY_SECONDS)
        if status == 401:
            logger.error('screener_worker_key_refused')
        if status >= 500 or status == 401 or data is None:
            raise WorkerUnavailable()
        return status, raw, data

    async def aclose(self):
        if self.client is not None:
            await self.client.aclose()


def name_error(name):
    """Why a saved item's name is refused (None when it is accepted): 1-120 characters, no space at either end and no
    control character (the migration's CHECK keeps 1-120 and no space at either end)."""
    if not isinstance(name, str) or not 1 <= len(name) <= NAME_MAX:
        return f'name is 1 to {NAME_MAX} characters'
    if name != name.strip():
        return 'name has no space at its start or end'
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        return 'name has no control character (line break, tab)'
    return None


def has_nul(value):
    """Whether a JSON value holds the character U+0000 in a key or a string (PostgreSQL text and jsonb refuse it)."""
    if isinstance(value, str):
        return '\x00' in value
    if isinstance(value, list):
        return any(has_nul(v) for v in value)
    if isinstance(value, dict):
        return any('\x00' in k or has_nul(v) for k, v in value.items())
    return False


def checked_item(body):
    """kind, name, definition and revision of a PUT items body (contract.ts PutItemRequest); 422 INVALID_INPUT naming the
    field otherwise. The definition's own fields are the worker's to check (/v1/validate); here only its envelope:
    kind 'screen' {definition, view?}, kind 'metric' {test}."""
    unknown = sorted(set(body) - {'kind', 'name', 'definition', 'revision'})
    if unknown:
        raise invalid(unknown[0], f'{unknown[0]} is not a field of a saved item (kind, name, definition, revision)')
    kind, name, definition, revision = body.get('kind'), body.get('name'), body.get('definition'), body.get('revision')
    if kind not in KINDS:
        raise invalid('kind', 'kind is screen or metric')
    problem = name_error(name)
    if problem:
        raise invalid('name', problem)
    if not isinstance(definition, dict):
        raise invalid('definition', 'definition is an object')
    if kind == 'screen':
        extra = sorted(set(definition) - {'definition', 'view'})
        if extra:
            raise invalid(f'definition.{extra[0]}', 'a saved screen holds definition and view only')
        if not isinstance(definition.get('definition'), dict):
            raise invalid('definition.definition', 'a saved screen holds its screen definition (an object)')
        if 'view' in definition and not isinstance(definition['view'], dict):
            raise invalid('definition.view', 'view is an object')
    else:
        if set(definition) != {'test'} or not isinstance(definition['test'], dict):
            raise invalid('definition.test', 'a My metric holds one test (an object) and nothing else')
    if has_nul(definition):
        raise invalid('definition', 'the definition holds the character U+0000, which cannot be saved; remove it')
    if revision is not None and (type(revision) is not int or not 1 <= revision <= 2 ** 63 - 1):
        raise invalid('revision', 'revision is the whole number the item was read with (none to create the item)')
    size = len(dumps(definition))
    if size > DEFINITION_BYTES:
        raise too_large(size)
    return kind, name, definition, revision


def too_large(size=None):
    return failure('LIMIT_EXCEEDED', 422, 'definition',
                   f'A saved definition is at most {DEFINITION_BYTES:,} bytes of JSON: remove conditions or filters.',
                   {'limit': 'saved_definition_bytes', 'allowed': DEFINITION_BYTES, **({'needed': size} if size else {})})


def validated_definition(kind, definition):
    """The Definition /v1/validate checks for a saved item: a screen's own definition; for a My metric its one test as
    the one condition of a screen of the required universe fields."""
    if kind == 'screen':
        return definition['definition']
    return {'universe': METRIC_UNIVERSE, 'conditions': [{'id': 'm', 'enabled': True, 'test': definition['test']}],
            'logic': 'all'}


def item_of(row, review):
    """SavedItem (contract.ts) of a stored row."""
    return jsonable_encoder({k: row[k] for k in ('item_id', 'kind', 'name', 'definition', 'schema_version', 'registry_version',
                                                 'screener_registry_version', 'definition_hash', 'revision', 'created_at',
                                                 'updated_at')} | {'needs_review': review})


class ScreenerStore:
    """edge_bff.screener_items / watchlist_items through the house Store's connections. Every statement names the owner
    (owner_key), so one owner never reads, replaces or deletes another's rows. A missing table (the migration not applied
    yet) is 503 SCREENER_NOT_READY; /ready never reads these tables."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise failure('SCREENER_NOT_READY', 503, message='The screener tables are not installed yet; retry after the stated seconds.',
                          headers={'Retry-After': str(TABLES_RETRY_SECONDS)}) from e

    def ready(self):
        with self.connect() as c:
            for table in TABLES:
                c.execute(f'SELECT 1 FROM edge_bff.{table} LIMIT 0')

    def items(self, owner, kind=None):
        with self.connect() as c:
            if kind:
                return c.execute('''SELECT * FROM edge_bff.screener_items WHERE owner_key=%s AND kind=%s
                    ORDER BY updated_at DESC, item_id''', (owner, kind)).fetchall()
            return c.execute('''SELECT * FROM edge_bff.screener_items WHERE owner_key=%s
                ORDER BY kind, updated_at DESC, item_id''', (owner,)).fetchall()

    def put(self, owner, item_id, kind, name, definition, checked, revision):
        """Create (revision None) or replace (the revision the item was read with) one item of the owner, serialised per
        owner by an advisory lock. (row, created). Refusals: 409 REVISION_CONFLICT (the id exists, or a stale revision),
        404 NOT_FOUND (replace of an item the owner does not have), 422 INVALID_INPUT kind (an item keeps its kind),
        409 NAME_TAKEN (another item of the kind has the name), 422 LIMIT_EXCEEDED saved_items (limit per kind)."""
        limit = SCREEN_LIMIT
        values = (name, Jsonb(definition), SCHEMA_VERSION, checked['registry'], checked['screener_registry'],
                  checked['definition_hash'])
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('screener:' + owner,))
            row = c.execute('SELECT kind, revision FROM edge_bff.screener_items WHERE owner_key=%s AND item_id=%s FOR UPDATE',
                            (owner, item_id)).fetchone()
            try:
                if revision is None:
                    if row:
                        raise failure('REVISION_CONFLICT', 409, details={'revision': row['revision']})
                    held = c.execute('SELECT count(*) AS n FROM edge_bff.screener_items WHERE owner_key=%s AND kind=%s',
                                     (owner, kind)).fetchone()['n']
                    if held >= limit:
                        noun = 'saved screens' if kind == 'screen' else 'My metrics'
                        raise failure('LIMIT_EXCEEDED', 422, message=f'At most {limit} {noun}: delete one before saving another.',
                                      details={'limit': 'saved_items', 'allowed': limit, 'needed': held + 1})
                    created = c.execute('''INSERT INTO edge_bff.screener_items(item_id,owner_key,kind,name,definition,
                            schema_version,registry_version,screener_registry_version,definition_hash)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (item_id) DO NOTHING RETURNING *''',
                        (item_id, owner, kind, *values)).fetchone()
                    if created is None:
                        # the id is another owner's: the same answer as for an id of one's own, so nothing is learned
                        raise failure('REVISION_CONFLICT', 409)
                    return created, True
                if not row:
                    raise failure('NOT_FOUND', 404)
                if row['kind'] != kind:
                    raise invalid('kind', f'this item is a {row["kind"]}; an item keeps its kind (save a new item instead)')
                if row['revision'] != revision:
                    raise failure('REVISION_CONFLICT', 409, 'revision', details={'revision': row['revision']})
                return c.execute('''UPDATE edge_bff.screener_items SET name=%s,definition=%s,schema_version=%s,
                        registry_version=%s,screener_registry_version=%s,definition_hash=%s,revision=revision+1,
                        updated_at=now() WHERE owner_key=%s AND item_id=%s RETURNING *''',
                        (*values, owner, item_id)).fetchone(), False
            except psycopg.errors.UniqueViolation as e:
                if e.diag.constraint_name == 'screener_items_owner_kind_name':
                    raise failure('NAME_TAKEN', 409, 'name') from e
                raise
            except psycopg.errors.CheckViolation as e:
                if e.diag.constraint_name == 'screener_items_definition_size':
                    raise too_large() from e
                raise

    def delete(self, owner, item_id):
        with self.connect() as c:
            gone = c.execute('DELETE FROM edge_bff.screener_items WHERE owner_key=%s AND item_id=%s',
                             (owner, item_id)).rowcount
        if not gone:
            raise failure('NOT_FOUND', 404)

    def watchlist(self, owner):
        with self.connect() as c:
            return c.execute('''SELECT ticker, added_at FROM edge_bff.watchlist_items WHERE owner_key=%s
                ORDER BY added_at, ticker''', (owner,)).fetchall()

    def watch(self, owner, ticker):
        """Add a ticker (idempotent: a watched one stays as it was); at most WATCHLIST_LIMIT per owner (422
        LIMIT_EXCEEDED)."""
        limit = WATCHLIST_LIMIT
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('watchlist:' + owner,))
            if c.execute('SELECT 1 FROM edge_bff.watchlist_items WHERE owner_key=%s AND ticker=%s', (owner, ticker)).fetchone():
                return
            held = c.execute('SELECT count(*) AS n FROM edge_bff.watchlist_items WHERE owner_key=%s', (owner,)).fetchone()['n']
            if held >= limit:
                raise failure('LIMIT_EXCEEDED', 422, 'ticker', f'At most {limit} tickers in the watchlist: remove one before adding another.',
                              {'limit': 'watchlist', 'allowed': limit, 'needed': held + 1})
            c.execute('INSERT INTO edge_bff.watchlist_items(owner_key,ticker) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                      (owner, ticker))

    def unwatch(self, owner, ticker):
        with self.connect() as c:
            c.execute('DELETE FROM edge_bff.watchlist_items WHERE owner_key=%s AND ticker=%s', (owner, ticker))


@dataclass
class Doc:
    """One cached worker document (catalog or universe) as edge-bff sends it: its JSON bytes, their gzip, the ETag
    (sha256 of the JSON bytes, PAGE LOAD SEQUENCE 6c.5 item 5), the worker state it was fetched at (key) and its
    price_data."""
    key: str | None
    raw: bytes
    gz: bytes
    etag: str
    price_data: str | None


def own_limits():
    """edge-bff's own limits as catalog limits[] entries (contract.ts LimitEntry; report 8.4 and 8.9: every limit is
    published with its rule, one right and one wrong example before the user meets it, AGENTS.md "Gates and evidence"),
    generated from the values."""
    return [
        {'name': 'saved_items', 'value': SCREEN_LIMIT, 'unit': 'items of each kind',
         'rule': f'at most {SCREEN_LIMIT} saved screens and {SCREEN_LIMIT} My metrics',
         'example_ok': f'saving a new screen while {SCREEN_LIMIT - 1} are saved',
         'example_refused': f'saving a new screen while {SCREEN_LIMIT} are saved (delete one first)'},
        {'name': 'watchlist', 'value': WATCHLIST_LIMIT, 'unit': 'tickers',
         'rule': f'at most {WATCHLIST_LIMIT} tickers in the watchlist',
         'example_ok': f'watching a new ticker while {WATCHLIST_LIMIT - 1} are watched',
         'example_refused': f'watching a new ticker while {WATCHLIST_LIMIT} are watched (remove one first)'},
        {'name': 'saved_definition_bytes', 'value': DEFINITION_BYTES, 'unit': 'bytes',
         'rule': f'a saved screen or My metric is at most {DEFINITION_BYTES:,} bytes of JSON',
         'example_ok': f'a saved definition of {DEFINITION_BYTES:,} bytes',
         'example_refused': f'a saved definition of {DEFINITION_BYTES + 1:,} bytes (remove conditions or filters)'},
        {'name': 'request_bytes', 'value': REQUEST_BYTES, 'unit': 'bytes',
         'rule': f'a request to the screener is at most {REQUEST_BYTES:,} bytes',
         'example_ok': f'a run request of {REQUEST_BYTES:,} bytes',
         'example_refused': f'a run request of {REQUEST_BYTES + 1:,} bytes (remove conditions or filters)'},
    ]


def with_own_limits(data):
    """The worker's catalog with edge-bff's limits added to limits[] (a limit the worker already lists is kept as it is)."""
    limits = data.get('limits')
    if not isinstance(limits, list):
        return data
    named = {x.get('name') for x in limits if isinstance(x, dict)}
    return {**data, 'limits': limits + [x for x in own_limits() if x['name'] not in named]}


def etag_matches(request, etag):
    """If-None-Match names this ETag (strong or weak) or '*'."""
    header = request.headers.get('if-none-match')
    if not header:
        return False
    return any(t == '*' or t.removeprefix('W/') == etag for t in (part.strip() for part in header.split(',')))


def price_data_of(data):
    versions = data.get('versions') if isinstance(data, dict) else None
    price = versions.get('price_data') if isinstance(versions, dict) else None
    return price if isinstance(price, str) else None


def versions_key(versions, refresh):
    return json.dumps({'versions': versions, 'refresh': refresh}, sort_keys=True)


class Screeners:
    """The screener feature of one edge-bff app: off (SCREENER_DISABLED) while SCREENER_WORKER_URL is empty."""

    def __init__(self, settings, store, worker=None):
        self.settings = settings
        self.store = ScreenerStore(store)
        self.worker = worker or (ScreenerWorker(settings) if settings.screener_worker_url else None)
        self.ready = False
        self.health = {'at': None, 'versions': None, 'key': None}   # the worker's /health, read at most every HEALTH_SECONDS
        self.docs = {}                 # 'catalog' | 'universe' -> Doc
        self.locks = {}                # one fetch at a time per document (and for /health): concurrent pages wait for it
        self.flight = {}               # (owner, lane) -> its call in flight (latest)
        self.pages = {}                # (owner, lane) -> {page: the highest seq that arrived}, PREVIEW_PAGES at most
        self.reviews = {}              # (definition, versions) -> needs_review of a saved item validated again on load

    async def aclose(self):
        if self.worker:
            await self.worker.aclose()

    def lock(self, name):
        if name not in self.locks:
            self.locks[name] = asyncio.Lock()
        return self.locks[name]

    async def guard(self):
        if not self.worker:
            raise failure('SCREENER_DISABLED', 503)
        if not self.ready:
            await asyncio.to_thread(self.store.ready)    # 503 SCREENER_NOT_READY while the tables are missing
            self.ready = True

    # ---- relay ------------------------------------------------------------------------------------------------------

    async def ask(self, method, path, body=None):
        """One relayed worker call: 2xx -> (its JSON bytes, its JSON); a 4xx with an error -> that error and status, as the
        worker gave them (validation 422, data 424, BUSY 409, DATA_VERSION_CHANGED 409); its 504 TIMEOUT -> 504 with its
        error; its 503 SCREENER_NOT_READY -> 503 with Retry-After; anything else -> 503 SCREENER_UNAVAILABLE. The worker
        answers within its deadline (SCREENER_DEADLINE_MS, which SCREENER_TIMEOUT_SECONDS states here) or with its 504,
        so its answer is awaited that long plus one control call (backtest.py ask); connecting stays one control call."""
        wait = httpx.Timeout(CONTROL_TIMEOUT, read=self.settings.screener_timeout_seconds + CONTROL_TIMEOUT)
        try:
            status, raw, data = await self.worker.call(method, path, body, wait)
        except WorkerTimeout as e:
            raise ScreenerError(504, e.error)
        except WorkerNotReady as e:
            raise ScreenerError(503, e.error, {'Retry-After': str(e.retry_after)})
        except WorkerUnavailable:
            raise failure('SCREENER_UNAVAILABLE', 503)
        if 200 <= status < 300:
            self.saw(data)
            return raw, data
        found = error_of(data)
        if 400 <= status < 500 and found:
            raise ScreenerError(status, found)
        raise failure('SCREENER_UNAVAILABLE', 503)

    def saw(self, data):
        """PAGE LOAD SEQUENCE 6c.5 item 4: a worker answer at another price_data than a cached document's means the worker
        swapped its snapshot; that document is dropped and /health is read again at the next catalog or universe."""
        price = price_data_of(data)
        if price is None:
            return
        for name, doc in list(self.docs.items()):
            if doc.price_data is not None and doc.price_data != price:
                del self.docs[name]
                self.health['at'] = None

    async def respond(self, request, raw, status=200, headers=None):
        """The worker's JSON bytes as they are; gzip when the client takes it (every browser)."""
        headers = {'Vary': 'Accept-Encoding', **(headers or {})}
        if accepts_gzip(request) and len(raw) >= GZIP_MIN_BYTES:
            pack = functools.partial(gzip.compress, raw, 6, mtime=0)
            raw = pack() if len(raw) <= INLINE_BYTES else await asyncio.to_thread(pack)
            headers['Content-Encoding'] = 'gzip'
        return Response(raw, status_code=status, media_type='application/json', headers=headers)

    # ---- catalog and universe: kept per worker state, ETag ----------------------------------------------------------

    async def current(self):
        """The worker's state from its /health ({versions, refresh}), read at most every HEALTH_SECONDS; the last one
        read while the worker does not answer (None before any, or while it has no snapshot)."""
        if self.health['at'] is not None and time.monotonic() - self.health['at'] < HEALTH_SECONDS:
            return self.health['key']
        async with self.lock('health'):
            if self.health['at'] is not None and time.monotonic() - self.health['at'] < HEALTH_SECONDS:
                return self.health['key']
            try:
                status, _, data = await self.worker.call('GET', '/health', key=False)
                versions = data.get('versions') if 200 <= status < 300 and isinstance(data, dict) else None
                if isinstance(versions, dict):
                    self.health.update(versions=versions, key=versions_key(versions, data.get('refresh')))
                else:
                    self.health.update(versions=None, key=None)
            except WorkerUnavailable:
                pass                       # the last state read is kept
            self.health['at'] = time.monotonic()
            return self.health['key']

    async def doc(self, name, path):
        """The cached document while the worker's state is the one it was fetched at; else fetched again (one fetch at a
        time; the pages that ask meanwhile get its answer). While the worker cannot answer, or has no snapshot, the last
        one is kept."""
        key = await self.current()
        cached = self.docs.get(name)
        if cached is not None and (key is None or cached.key == key):
            return cached
        async with self.lock(name):
            cached = self.docs.get(name)
            if cached is not None and (key is None or cached.key == key):
                return cached
            try:
                raw, data = await self.ask('GET', path)
            except ScreenerError:
                if cached is not None:
                    return cached
                raise
            built = await asyncio.to_thread(self.build, name, raw, data, key)
            self.docs[name] = built
            return built

    @staticmethod
    def build(name, raw, data, key):
        if name == 'catalog' and isinstance(data, dict):
            mine = with_own_limits(data)
            if mine is not data:
                raw = dumps(mine)
        return Doc(key=key, raw=raw, gz=gzip.compress(raw, 6, mtime=0), etag='"' + hashlib.sha256(raw).hexdigest() + '"',
                   price_data=price_data_of(data))

    @staticmethod
    def doc_answer(request, doc):
        """200 with the document (gzip when taken), or 304 with no body when If-None-Match names its ETag. The house
        Cache-Control: no-store stays: the page keeps the bytes itself and sends If-None-Match (6c.5 item 5)."""
        headers = {'ETag': doc.etag, 'Vary': 'Accept-Encoding'}
        if etag_matches(request, doc.etag):
            return Response(status_code=304, headers=headers)
        if accepts_gzip(request):
            return Response(doc.gz, media_type='application/json', headers={**headers, 'Content-Encoding': 'gzip'})
        return Response(doc.raw, media_type='application/json', headers=headers)

    # ---- run and preview: latest wins per owner ---------------------------------------------------------------------

    @staticmethod
    def order_of(value):
        """client_order {page, seq} (backtest.py preview_order); 422 INVALID_INPUT client_order otherwise."""
        try:
            return preview_order(value)
        except BacktestError:
            raise invalid('client_order', 'client_order is {page, seq}: page an id of 1-100 characters A-Z a-z 0-9 . _ : -, '
                                          'seq a whole number from 0')

    async def latest(self, lane, owner, request, body, order, path):
        """The owner's call of this lane (run or preview), latest wins (report 8.1, 8.9: one screen and one preview in
        flight per owner), as the Backtest's signals preview (backtest.py latest_preview): a new call ends the one still
        in flight, which answers 409 SCREEN_REPLACED / PREVIEW_REPLACED and whose worker call is closed, and is sent once
        that one has ended. Latest is the page's own order where the body carries client_order; a call its page had
        already sent a newer one of answers 409 at once and never reaches the worker. The lanes are independent."""
        code = REPLACED[lane]
        if order is not None:
            page, seq = order
            pages = self.pages.setdefault((owner, lane), {})
            if seq < pages.get(page, seq):
                raise failure(code, 409)
            pages.pop(page, None)
            pages[page] = seq
            while len(pages) > PREVIEW_PAGES:
                del pages[next(iter(pages))]
        mine = {'replaced': asyncio.Event(), 'ended': asyncio.Event()}
        older = self.flight.get((owner, lane))
        self.flight[(owner, lane)] = mine
        if older:
            older['replaced'].set()
        async def relay():
            if older:
                await older['ended'].wait()
            return await self.ask('POST', path, body)
        try:
            return await Backtests.unless_gone(request, relay(), mine['replaced'])
        except PreviewReplaced:
            raise failure(code, 409)
        finally:
            mine['ended'].set()
            if self.flight.get((owner, lane)) is mine:
                del self.flight[(owner, lane)]

    @staticmethod
    async def json_object(request):
        try:
            body = loads(await request.body() or b'null')
        except ValueError:
            raise invalid(None, 'The body is not JSON the screener can read (no NaN or Infinity, no number beyond a '
                                'double, no unpaired surrogate).')
        if not isinstance(body, dict):
            raise invalid(None, 'The body is a JSON object.')
        return body

    # ---- saved items ------------------------------------------------------------------------------------------------

    async def versions_now(self):
        """The worker's current versions (from /health, at most HEALTH_SECONDS old), or None."""
        await self.current()
        return self.health['versions']

    async def validated(self, kind, definition):
        """{definition_hash, registry, screener_registry} of a saved item's definition, checked by the worker's
        /v1/validate; its 422 is relayed (for a My metric with the field named from its test, not from the screen it is
        validated in)."""
        try:
            _, data = await self.ask('POST', '/v1/validate', {'schema_version': SCHEMA_VERSION,
                                                              'definition': validated_definition(kind, definition)})
        except ScreenerError as e:
            field = e.error.get('field')
            if kind == 'metric' and isinstance(field, str) and METRIC_CONDITION in field:
                raise ScreenerError(e.status, {**e.error, 'field': field.replace(METRIC_CONDITION, 'test', 1)}, e.headers)
            raise
        found = data if isinstance(data, dict) else {}
        digest = found.get('definition_hash')
        if found.get('valid') is not True or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise failure('SCREENER_UNAVAILABLE', 503)       # an answer outside the worker's API
        versions = found.get('versions')
        if not (isinstance(versions, dict) and all(isinstance(versions.get(k), str) for k in ('registry', 'screener_registry'))):
            versions = await self.versions_now()
        if not (isinstance(versions, dict) and all(isinstance(versions.get(k), str) and 0 < len(versions[k]) <= 200
                                                   for k in ('registry', 'screener_registry'))):
            raise failure('SCREENER_UNAVAILABLE', 503)
        return {'definition_hash': digest, 'registry': versions['registry'], 'screener_registry': versions['screener_registry']}

    async def reviewed(self, rows):
        """SavedItem of each row with needs_review (report 8.7): an item saved under the registry versions the worker
        has now passed its validation then and needs none; one saved under others is validated again, and each refusal
        is listed with its field. Nothing is adjusted: the stored definition stays as saved. While the worker cannot
        answer an item is not reviewed (needs_review empty, nothing kept)."""
        current = await self.versions_now() if rows else None
        out = []
        for row in rows:
            review = []
            if isinstance(current, dict) and (row['registry_version'], row['screener_registry_version']) != (
                    current.get('registry'), current.get('screener_registry')):
                review = await self.review(row, current)
            out.append(item_of(row, review))
        return out

    async def review(self, row, current):
        key = (row['kind'], hashlib.sha256(dumps(row['definition'])).hexdigest(), current.get('registry'),
               current.get('screener_registry'))
        if key in self.reviews:
            return self.reviews[key]
        try:
            await self.validated(row['kind'], row['definition'])
            found = []
        except ScreenerError as e:
            if e.status != 422:
                return []                  # not reviewed now: the worker did not answer the question
            error = e.error
            found = [{'field': error.get('field') or 'definition', 'reason': error['code'],
                      **{k: error[k] for k in ('message', 'details') if error.get(k) is not None}}]
        if len(self.reviews) >= REVIEWS_KEPT:
            self.reviews.clear()
        self.reviews[key] = found
        return found

    # ---- routes -----------------------------------------------------------------------------------------------------

    def routes(self, app, session, write):
        owner = self.settings.owner

        @app.exception_handler(ScreenerError)
        async def screener_error(_, exc):
            return JSONResponse(status_code=exc.status, content={'error': exc.error}, headers=exc.headers)

        @app.get('/api/v1/screener/catalog')
        async def catalog(request: Request, _=Depends(session)):
            """CatalogResponse (report 8.4) with edge-bff's own limits added, kept while the worker's state (versions and
            refresh, its /health) is the one it was fetched at; ETag and If-None-Match -> 304."""
            await self.guard()
            return self.doc_answer(request, await self.doc('catalog', '/v1/catalog'))

        @app.get('/api/v1/screener/universe')
        async def universe(request: Request, _=Depends(session)):
            """UniverseResponse (report 8.4), kept as the catalog is; ETag and If-None-Match -> 304."""
            await self.guard()
            return self.doc_answer(request, await self.doc('universe', '/v1/universe'))

        async def lane(lane, path, request):
            await self.guard()
            body = await self.json_object(request)
            order = self.order_of(body.get('client_order'))
            try:
                raw, _ = await self.latest(lane, owner, request, body, order, path)
            except CallerGone:
                return Response(status_code=204)    # never sent: uvicorn drops an answer to a closed connection
            return await self.respond(request, raw)

        @app.post('/api/v1/screener/run')
        async def run(request: Request, _=Depends(write)):
            """RunResponse of one screen (report 8.5), latest wins per owner (409 SCREEN_REPLACED); the body goes to the
            worker as sent (contract.ts RunRequest, client_order included)."""
            return await lane('run', '/v1/run', request)

        @app.post('/api/v1/screener/preview')
        async def preview(request: Request, _=Depends(write)):
            """PreviewResponse of one ticker (report 8.6), latest wins per owner (409 PREVIEW_REPLACED)."""
            return await lane('preview', '/v1/preview', request)

        @app.post('/api/v1/screener/validate')
        async def validate(request: Request, _=Depends(write)):
            await self.guard()
            raw, _ = await self.ask('POST', '/v1/validate', await self.json_object(request))
            return await self.respond(request, raw)

        @app.post('/api/v1/screener/counts')
        async def counts(request: Request, _=Depends(write)):
            await self.guard()
            raw, _ = await self.ask('POST', '/v1/counts', await self.json_object(request))
            return await self.respond(request, raw)

        @app.get('/api/v1/screener/items')
        async def items(kind: str | None = None, _=Depends(session)):
            """{items: SavedItem[]} of the owner, one kind or both, the latest changed first, each with needs_review."""
            await self.guard()
            if kind is not None and kind not in KINDS:
                raise invalid('kind', 'kind is screen or metric (or left out for both)')
            rows = await asyncio.to_thread(self.store.items, owner, kind)
            return JSONResponse({'items': await self.reviewed(rows)})

        @app.put('/api/v1/screener/items/{item_id}')
        async def put_item(item_id: str, request: Request, _=Depends(write)):
            """PutItemRequest -> the stored SavedItem: created without revision, replaced with the revision it was read
            with; the definition validated by the worker first (its refusal relayed as it is)."""
            await self.guard()
            if not ITEM_ID.fullmatch(item_id):
                raise invalid('item_id', 'item_id is scr_ followed by 32 lowercase hexadecimal digits')
            kind, name, definition, revision = checked_item(await self.json_object(request))
            checked = await self.validated(kind, definition)
            row, _ = await asyncio.to_thread(self.store.put, owner, item_id, kind, name, definition, checked, revision)
            return JSONResponse(item_of(row, []))

        @app.delete('/api/v1/screener/items/{item_id}', status_code=204)
        async def delete_item(item_id: str, _=Depends(write)):
            await self.guard()
            if not ITEM_ID.fullmatch(item_id):
                raise failure('NOT_FOUND', 404)
            await asyncio.to_thread(self.store.delete, owner, item_id)
            return Response(status_code=204)

        @app.get('/api/v1/screener/watchlist')
        async def watchlist(_=Depends(session)):
            await self.guard()
            rows = await asyncio.to_thread(self.store.watchlist, owner)
            return JSONResponse(jsonable_encoder({'tickers': [{'ticker': r['ticker'], 'added_at': r['added_at']} for r in rows]}))

        def ticker_of(ticker):
            if not TICKER.fullmatch(ticker):
                raise invalid('ticker', 'ticker is 1 to 12 capital letters or digits')
            return ticker

        @app.put('/api/v1/screener/watchlist/{ticker}', status_code=204)
        async def watch(ticker: str, _=Depends(write)):
            await self.guard()
            await asyncio.to_thread(self.store.watch, owner, ticker_of(ticker))
            return Response(status_code=204)

        @app.delete('/api/v1/screener/watchlist/{ticker}', status_code=204)
        async def unwatch(ticker: str, _=Depends(write)):
            await self.guard()
            await asyncio.to_thread(self.store.unwatch, owner, ticker_of(ticker))
            return Response(status_code=204)
