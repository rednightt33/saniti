"""EXEC-WATCHLIST L3 (user go 2026-11-16: "Go"): the Watchlist page's lists and data.

  /api/v1/watchlist/index, /api/v1/watchlist/file/<name>   the publisher's watchlist-stocks file (app/pages.py PageFiles,
                                                           as the Overview's)
  /api/v1/watchlist/lists ...                              the account's named lists (edge_bff.watchlist_lists/_items,
                                                           migration 20261116_001)

Every statement names the account (owner_key), so one account never reads or changes another's lists (decision 1A:
built for the owner now, ready for EDGE-MULTIUSER). Limits are guarantees (AGENTS.md "Gates and evidence"): each is
published with its rule, how to pass it and one right and one wrong example (GET /lists `limits`), and a refusal names
the limit and the fix. The indicator keys belong to the data file's catalog: this module checks only their shape and
count, so a new indicator needs no change here (WATCHLIST_FORMULAS.md).
"""
from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import contextmanager

import psycopg
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder

from .pages import PageFiles

NAME = re.compile(r'watchlist-stocks')                       # publisher watchlist.NAME
LISTS = 20                                                  # lists per account
PER_LIST = 50                                               # stocks per list (the design's)
INDICATORS = 8                                              # indicators per list (the design's)
NAME_CHARS = 40
TICKER = re.compile(r'[A-Z0-9]{1,12}')
KEY = re.compile(r'[a-z0-9_]{1,24}')
TABLES_RETRY_SECONDS = 30
FIRST_LIST = 'Watchlist'                                    # the list the Screener's star creates when none exists

MESSAGES = {
    'WATCHLIST_NOT_READY': 'The watchlist tables are not installed yet; retry after the stated seconds.',
    'NOT_FOUND': 'This list no longer exists; reload the page.',
    'NAME_TAKEN': 'Another list already has this name. Pick another name.',
    'LAST_LIST': 'The last list cannot be deleted. Create another list first.',
    'LIMIT_EXCEEDED': 'A limit was reached.',
    'INVALID_INPUT': 'The request is not valid.',
}


def limits():
    """The limits with their rule and one right and one wrong example (the wrong one ends with the fix)."""
    return [
        {'name': 'lists', 'value': LISTS, 'unit': 'lists',
         'rule': f'at most {LISTS} lists', 'example_ok': f'creating a list while you have {LISTS - 1}',
         'example_refused': f'creating a list while you have {LISTS} (delete one first)'},
        {'name': 'tickers', 'value': PER_LIST, 'unit': 'stocks',
         'rule': f'at most {PER_LIST} stocks in one list', 'example_ok': f'adding a stock to a list of {PER_LIST - 1}',
         'example_refused': f'adding a stock to a list of {PER_LIST} (remove one or use another list)'},
        {'name': 'indicators', 'value': INDICATORS, 'unit': 'indicators',
         'rule': f'1 to {INDICATORS} indicators per list', 'example_ok': f'saving {INDICATORS} indicators',
         'example_refused': f'saving {INDICATORS + 1} indicators (remove one) or none (choose at least one)'},
        {'name': 'name', 'value': NAME_CHARS, 'unit': 'characters',
         'rule': f'a list name has 1 to {NAME_CHARS} characters and differs from your other lists (ignoring case)',
         'example_ok': 'Banks', 'example_refused': '"banks" next to "Banks" (pick another name)'},
    ]


class WatchlistError(Exception):
    def __init__(self, status, error, headers=None):
        super().__init__(error.get('code'))
        self.status, self.error, self.headers = status, error, headers


def failure(code, status, field=None, message=None, details=None, headers=None):
    return WatchlistError(status, {'code': code, **({'field': field} if field else {}), 'message': message or MESSAGES[code],
                                   **({'details': details} if details else {})}, headers)


def invalid(field, message):
    return failure('INVALID_INPUT', 422, field, message)


def over(limit, allowed, needed, message):
    return failure('LIMIT_EXCEEDED', 422, limit, message, {'limit': limit, 'allowed': allowed, 'needed': needed})


# ---- input shapes (the body is checked here, field by field, so a refusal names the field and the fix) ---------------

def name_of(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= NAME_CHARS:
        raise invalid('name', f'Enter a list name of 1 to {NAME_CHARS} characters.')
    return value.strip()


def tickers_of(value, field='tickers'):
    if not isinstance(value, list) or not all(isinstance(t, str) and TICKER.fullmatch(t) for t in value):
        raise invalid(field, 'Each stock code is 1 to 12 capital letters or digits, e.g. BBCA.')
    out = list(dict.fromkeys(value))
    if len(out) > PER_LIST:
        raise over('tickers', PER_LIST, len(out), f'At most {PER_LIST} stocks in one list: this request has {len(out)}. '
                   'Remove some or use another list.')
    return out


def indicators_of(value):
    if value is None:
        return None                                     # the data file's default
    if not isinstance(value, list) or not all(isinstance(k, str) and KEY.fullmatch(k) for k in value):
        raise invalid('indicators', 'Indicators are keys from the indicator list, e.g. rsi.')
    out = list(dict.fromkeys(value))
    if not 1 <= len(out) <= INDICATORS:
        raise over('indicators', INDICATORS, len(out), f'Choose 1 to {INDICATORS} indicators: this has {len(out)}.')
    return out


def list_id_of(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise failure('NOT_FOUND', 404) from None


def position_of(value, field='position'):
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1_000_000:
        raise invalid(field, 'position is a whole number from 0.')
    return value


class WatchlistStore:
    """edge_bff.watchlist_lists / watchlist_items through the house Store's connections; every write of an account is
    serialised by an advisory lock on its key, so two tabs cannot pass a limit together."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise failure('WATCHLIST_NOT_READY', 503, headers={'Retry-After': str(TABLES_RETRY_SECONDS)}) from e
        except psycopg.errors.UndefinedColumn as e:          # watchlist_items before migration 20261116_001
            raise failure('WATCHLIST_NOT_READY', 503, headers={'Retry-After': str(TABLES_RETRY_SECONDS)}) from e

    @staticmethod
    def lock(c, owner):
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('watchlist:' + owner,))

    @staticmethod
    def _lists(c, owner):
        lists = c.execute('''SELECT list_id::text AS id, name, position, indicators, created_at, updated_at
            FROM edge_bff.watchlist_lists WHERE owner_key=%s ORDER BY position, created_at, list_id''', (owner,)).fetchall()
        items = c.execute('''SELECT list_id::text AS id, ticker, position FROM edge_bff.watchlist_items WHERE owner_key=%s
            ORDER BY position, added_at, ticker''', (owner,)).fetchall()
        by = {r['id']: [] for r in lists}
        for r in items:
            by.setdefault(r['id'], []).append({'ticker': r['ticker'], 'position': r['position']})
        return [{**r, 'tickers': by.get(r['id'], [])} for r in lists]

    @staticmethod
    def _one(c, owner, list_id):
        row = c.execute('SELECT list_id::text AS id FROM edge_bff.watchlist_lists WHERE owner_key=%s AND list_id=%s',
                        (owner, list_id)).fetchone()
        if not row:
            raise failure('NOT_FOUND', 404)

    def lists(self, owner):
        with self.connect() as c:
            return self._lists(c, owner)

    def create(self, owner, name, tickers, indicators, position):
        with self.connect() as c:
            self.lock(c, owner)
            held = c.execute('SELECT count(*) AS n, coalesce(max(position), -1) AS top FROM edge_bff.watchlist_lists '
                             'WHERE owner_key=%s', (owner,)).fetchone()
            if held['n'] >= LISTS:
                raise over('lists', LISTS, held['n'] + 1, f'At most {LISTS} lists: you have {held["n"]}. Delete one first.')
            try:
                row = c.execute('''INSERT INTO edge_bff.watchlist_lists(owner_key, name, position, indicators)
                    VALUES (%s,%s,%s,%s) RETURNING list_id::text AS id''',
                                (owner, name, held['top'] + 1 if position is None else position, indicators)).fetchone()
            except psycopg.errors.UniqueViolation as e:
                raise failure('NAME_TAKEN', 409, 'name') from e
            for n, t in enumerate(tickers):
                c.execute('INSERT INTO edge_bff.watchlist_items(owner_key, list_id, ticker, position) VALUES (%s,%s,%s,%s)',
                          (owner, row['id'], t, n))
            return next(x for x in self._lists(c, owner) if x['id'] == row['id'])

    def update(self, owner, list_id, name=None, indicators=...):
        with self.connect() as c:
            self.lock(c, owner)
            self._one(c, owner, list_id)
            try:
                if name is not None:
                    c.execute('UPDATE edge_bff.watchlist_lists SET name=%s, updated_at=now() WHERE owner_key=%s AND list_id=%s',
                              (name, owner, list_id))
            except psycopg.errors.UniqueViolation as e:
                raise failure('NAME_TAKEN', 409, 'name') from e
            if indicators is not ...:
                c.execute('UPDATE edge_bff.watchlist_lists SET indicators=%s, updated_at=now() WHERE owner_key=%s AND list_id=%s',
                          (indicators, owner, list_id))
            return next(x for x in self._lists(c, owner) if x['id'] == list_id)

    def indicators_all(self, owner, indicators):
        with self.connect() as c:
            self.lock(c, owner)
            c.execute('UPDATE edge_bff.watchlist_lists SET indicators=%s, updated_at=now() WHERE owner_key=%s',
                      (indicators, owner))
            return self._lists(c, owner)

    def delete(self, owner, list_id):
        with self.connect() as c:
            self.lock(c, owner)
            self._one(c, owner, list_id)
            n = c.execute('SELECT count(*) AS n FROM edge_bff.watchlist_lists WHERE owner_key=%s', (owner,)).fetchone()['n']
            if n <= 1:
                raise failure('LAST_LIST', 409)
            c.execute('DELETE FROM edge_bff.watchlist_lists WHERE owner_key=%s AND list_id=%s', (owner, list_id))

    def add(self, owner, list_id, tickers, position):
        """Add stocks to a list (a stock already in it stays where it is). position: where the first new one goes (Undo
        puts a removed stock back at its old place); default after the last."""
        with self.connect() as c:
            self.lock(c, owner)
            self._one(c, owner, list_id)
            have = c.execute('SELECT ticker, position FROM edge_bff.watchlist_items WHERE owner_key=%s AND list_id=%s',
                             (owner, list_id)).fetchall()
            known = {r['ticker'] for r in have}
            new = [t for t in tickers if t not in known]
            if len(have) + len(new) > PER_LIST:
                raise over('tickers', PER_LIST, len(have) + len(new),
                           f'At most {PER_LIST} stocks in one list: it has {len(have)}, these would make {len(have) + len(new)}. '
                           'Remove some or use another list.')
            start = (max((r['position'] for r in have), default=-1) + 1) if position is None else position
            for n, t in enumerate(new):
                c.execute('INSERT INTO edge_bff.watchlist_items(owner_key, list_id, ticker, position) VALUES (%s,%s,%s,%s)',
                          (owner, list_id, t, start + n))
            return {'added': new, 'already': [t for t in tickers if t in known],
                    'list': next(x for x in self._lists(c, owner) if x['id'] == list_id)}

    def remove(self, owner, list_id, ticker):
        with self.connect() as c:
            self.lock(c, owner)
            self._one(c, owner, list_id)
            c.execute('DELETE FROM edge_bff.watchlist_items WHERE owner_key=%s AND list_id=%s AND ticker=%s',
                      (owner, list_id, ticker))

    # ---- the Screener's star (decision 2A): the first list, created when the account has none -----------------------

    @staticmethod
    def first(c, owner, create):
        row = c.execute('''SELECT list_id::text AS id FROM edge_bff.watchlist_lists WHERE owner_key=%s
            ORDER BY position, created_at, list_id LIMIT 1''', (owner,)).fetchone()
        if row or not create:
            return row and row['id']
        name = FIRST_LIST
        while c.execute('SELECT 1 FROM edge_bff.watchlist_lists WHERE owner_key=%s AND lower(name)=lower(%s)',
                        (owner, name)).fetchone():
            name += ' 2'
        return c.execute('''INSERT INTO edge_bff.watchlist_lists(owner_key, name, position) VALUES (%s,%s,0)
            RETURNING list_id::text AS id''', (owner, name)).fetchone()['id']


def page_files(settings, clock=None):
    kw = {'clock': clock} if clock else {}
    return PageFiles(settings, 'watchlist', NAME, 'Watchlist', 'watchlist-stocks', **kw)


class Watchlist:
    def __init__(self, settings, store, clock=None):
        self.settings, self.store = settings, WatchlistStore(store)
        self.files = page_files(settings, clock)

    async def aclose(self):
        await self.files.aclose()

    def routes(self, app, session, write):
        owner = self.settings.owner
        self.files.routes(app, session)

        def answer(body, status=200):
            return JSONResponse(status_code=status, content=jsonable_encoder(body))

        async def body_of(request):
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001 - any unreadable body is one refusal
                raise invalid('body', 'Send a JSON object.') from None
            if not isinstance(body, dict):
                raise invalid('body', 'Send a JSON object.')
            return body

        async def refused(request, e):
            return JSONResponse(status_code=e.status, content={'error': e.error}, headers=e.headers)
        app.add_exception_handler(WatchlistError, refused)

        @app.get('/api/v1/watchlist/lists')
        async def lists(_=Depends(session)):
            return answer({'lists': await asyncio.to_thread(self.store.lists, owner), 'limits': limits()})

        @app.post('/api/v1/watchlist/lists')
        async def create(request: Request, _=Depends(write)):
            b = await body_of(request)
            made = await asyncio.to_thread(self.store.create, owner, name_of(b.get('name')), tickers_of(b.get('tickers', [])),
                                           indicators_of(b.get('indicators')), position_of(b.get('position')))
            return answer({'list': made}, 201)

        @app.patch('/api/v1/watchlist/lists/{list_id}')
        async def update(list_id: str, request: Request, _=Depends(write)):
            b = await body_of(request)
            name = name_of(b['name']) if 'name' in b else None
            ind = indicators_of(b['indicators']) if 'indicators' in b else ...
            return answer({'list': await asyncio.to_thread(self.store.update, owner, list_id_of(list_id), name, ind)})

        @app.put('/api/v1/watchlist/indicators')
        async def indicators_all(request: Request, _=Depends(write)):
            b = await body_of(request)
            return answer({'lists': await asyncio.to_thread(self.store.indicators_all, owner, indicators_of(b.get('indicators')))})

        @app.delete('/api/v1/watchlist/lists/{list_id}')
        async def delete(list_id: str, _=Depends(write)):
            await asyncio.to_thread(self.store.delete, owner, list_id_of(list_id))
            return Response(status_code=204)

        @app.post('/api/v1/watchlist/lists/{list_id}/tickers')
        async def add(list_id: str, request: Request, _=Depends(write)):
            b = await body_of(request)
            got = await asyncio.to_thread(self.store.add, owner, list_id_of(list_id), tickers_of(b.get('tickers')),
                                          position_of(b.get('position')))
            return answer(got)

        @app.delete('/api/v1/watchlist/lists/{list_id}/tickers/{ticker}')
        async def remove(list_id: str, ticker: str, _=Depends(write)):
            if not TICKER.fullmatch(ticker):
                raise invalid('ticker', 'A stock code is 1 to 12 capital letters or digits, e.g. BBCA.')
            await asyncio.to_thread(self.store.remove, owner, list_id_of(list_id), ticker)
            return Response(status_code=204)
