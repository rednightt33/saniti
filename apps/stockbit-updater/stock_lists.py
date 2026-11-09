"""Stock list step of a stockbit-updater round (EXEC-STOCK-CATALOG, user go 2026-11-09: D1-D4, "Opsi B").

The lists are the rows of public."Stock_List" that are enabled (migration 20261109_001: 33 indices and 33 KONGLO
groups the user chose). Each round reads them all from Stockbit, the way stockbit.com/stock-group and
stockbit.com/catalog/indeks read them (endpoints found in those pages' code, 2026-11-02):
- groups: GET /emitten/catalog?catalog_type=CATALOG_TYPE_KONGLO&page=n (every page), members
  GET /order-trade/market-mover?catalog_type=CATALOG_TYPE_KONGLO&mover_type=MOVER_TYPE_CATALOG&catalog_id=..&limit=100
  &page=n (every page);
- indices: GET /emitten/sectors/88/subsectors (the Indeks lists), members GET /emitten/v3/sector/88/subsector/{id}/company.
The snapshot goes to public.apply_stock_list_snapshot, which writes all lists or none (an enabled list missing, an empty
list or a numbered index with another count refuses the round). A refused or failed step writes a FAILED
Stock_List_Load_Log row and returns a warning: the stockbit-updater round stays SUCCESS (decision D2), because the
Broker Summary and the events it loaded are valid on their own. Lists Stockbit shows outside Stock_List are reported,
never loaded. The token is never printed or stored.
"""
from __future__ import annotations

import time
from decimal import Decimal
from urllib.parse import urlencode

from psycopg.types.json import Jsonb

import stockbit_ihsg_daily as source

MAX_PAGES = 20


class StockListError(RuntimeError):
    pass


def _data(body, kind, path):
    data = body.get('data')
    if not isinstance(data, kind):
        raise StockListError(f'{path}: no {kind.__name__} in data')
    return data


def _int(value, default=0):
    return int(value) if isinstance(value, (int, Decimal)) or (isinstance(value, str) and value.isdigit()) else default


class Reader:
    """The Stockbit reads of one round; counts its requests."""

    def __init__(self, fetch):
        self.fetch, self.requests = fetch, 0

    def get(self, path):
        self.requests += 1
        body, _, _ = self.fetch.get_json(path)
        return body

    def groups(self):
        out, page = [], 1
        while True:
            path = '/emitten/catalog?' + urlencode({'catalog_type': 'CATALOG_TYPE_KONGLO', 'page': page})
            data = _data(self.get(path), dict, '/emitten/catalog')
            catalogs, paginate = data.get('catalogs'), data.get('paginate') or {}
            if not isinstance(catalogs, list):
                raise StockListError('/emitten/catalog: no catalogs array')
            out += catalogs
            if page >= _int(paginate.get('total_page'), 1):
                total = _int(paginate.get('total_data'), len(out))
                if total != len(out):
                    raise StockListError(f'/emitten/catalog: {len(out)} groups read, Stockbit says {total}')
                return [{'id': str(c.get('id')), 'name': str(c.get('catalog_name') or c.get('catalog_code') or '')}
                        for c in out]
            page += 1
            if page > MAX_PAGES:
                raise StockListError('/emitten/catalog: more pages than expected')

    def index_lists(self):
        rows = _data(self.get('/emitten/sectors/88/subsectors'), list, '/emitten/sectors/88/subsectors')
        return [{'id': str(r.get('id')), 'name': str(r.get('name') or '')} for r in rows if isinstance(r, dict)]

    def group_members(self, source_id):
        out, page = [], 1
        while True:
            path = '/order-trade/market-mover?' + urlencode({
                'catalog_type': 'CATALOG_TYPE_KONGLO', 'mover_type': 'MOVER_TYPE_CATALOG', 'catalog_id': source_id,
                'limit': 100, 'page': page})
            data = _data(self.get(path), dict, '/order-trade/market-mover')
            movers = data.get('mover_list')
            if not isinstance(movers, list):
                raise StockListError(f'group {source_id}: no mover_list')
            for row in movers:
                detail = row.get('stock_detail') if isinstance(row, dict) else None
                if not isinstance(detail, dict) or not detail.get('code'):
                    raise StockListError(f'group {source_id}: a member without stock_detail.code')
                out.append({'ticker': str(detail['code']).strip().upper(), 'name': str(detail.get('name') or ''),
                            'order': len(out) + 1})
            if not (data.get('pagination') or {}).get('has_next'):
                return out
            page += 1
            if page > MAX_PAGES:
                raise StockListError(f'group {source_id}: more pages than expected')

    def index_members(self, source_id):
        path = f'/emitten/v3/sector/88/subsector/{source_id}/company'
        rows = _data(self.get(path), list, path)
        out = []
        for row in rows:
            if not isinstance(row, dict) or not row.get('symbol'):
                raise StockListError(f'index {source_id}: a member without symbol')
            out.append({'ticker': str(row['symbol']).strip().upper(), 'name': str(row.get('name') or ''),
                        'order': len(out) + 1})
        return out


def fetch_snapshot(reader, lists):
    """lists: (list_key, list_kind, source_id, name, is_enabled) of every Stock_List row."""
    shown = {('KONGLO', g['id']): g['name'] for g in reader.groups()}
    shown.update({('INDEX', x['id']): x['name'] for x in reader.index_lists()})
    known = {(kind, sid) for _, kind, sid, _, _ in lists}
    unlisted = sorted(({'list_key': f'{kind}:{sid}', 'name': name} for (kind, sid), name in shown.items()
                       if (kind, sid) not in known), key=lambda x: x['list_key'])
    enabled = [row for row in lists if row[4]]
    gone = [f'{key} ({name})' for key, kind, sid, name, _ in enabled if (kind, sid) not in shown]
    if gone:
        raise StockListError('Stockbit no longer shows ' + ', '.join(gone))
    snapshot = []
    for key, kind, sid, _, _ in enabled:
        members = reader.group_members(sid) if kind == 'KONGLO' else reader.index_members(sid)
        snapshot.append({'list_key': key, 'members': members})
    return {'lists': snapshot, 'unlisted': unlisted}


def previous_unlisted(pg):
    row = pg.execute("""SELECT unlisted FROM public."Stock_List_Load_Log" WHERE status <> 'FAILED'
                        ORDER BY run_id DESC LIMIT 1""").fetchone()
    return {x['list_key'] for x in (row[0] if row else [])}


def run(pg, token, execution_id, emit, fetcher=None):
    """One stock list round; never raises (decision D2). Returns the summary kept in Monitoring_Stockbit_Update."""
    started = time.monotonic()
    reader = None
    try:
        lists = pg.execute("""SELECT list_key, list_kind, source_id, name, is_enabled FROM public."Stock_List"
                              ORDER BY list_kind, sort_order""").fetchall()
        if not any(row[4] for row in lists):
            raise StockListError('Stock_List has no enabled list')
        reader = Reader(fetcher or source.StockbitFetcher(token, 45, .25, 1000))
        snapshot = fetch_snapshot(reader, lists)
        before = previous_unlisted(pg)
        result = pg.execute('SELECT public.apply_stock_list_snapshot(%s, %s)',
                            (Jsonb(snapshot), execution_id)).fetchone()[0]
        result['unlisted_new'] = [x for x in snapshot['unlisted'] if x['list_key'] not in before]
        result.update(requests=reader.requests, seconds=round(time.monotonic() - started, 1))
        emit('stock_lists_done', run_id=result['run_id'], status=result['status'], lists=result['lists'],
             members=result['members'], added=result['added'], removed=result['removed'],
             unlisted_new=len(result['unlisted_new']), requests=reader.requests)
        return result
    except Exception as exc:  # noqa: BLE001 - the step's failure is a warning of the round (D2), recorded and returned
        error = f'{type(exc).__name__}: {exc}'[:1500]
        run_id = None
        try:
            run_id = pg.execute("""INSERT INTO public."Stock_List_Load_Log" (execution_id, status, finished_at, error)
                                   VALUES (%s, 'FAILED', clock_timestamp(), %s) RETURNING run_id""",
                                (execution_id, error)).fetchone()[0]
        except Exception as log_exc:  # noqa: BLE001 - e.g. the table is missing; the warning still reaches the round
            error += f' (log not written: {type(log_exc).__name__})'
        emit('stock_lists_failed', error=error, run_id=run_id)
        return {'status': 'FAILED', 'run_id': run_id, 'warning': error,
                'requests': reader.requests if reader else 0, 'seconds': round(time.monotonic() - started, 1)}
