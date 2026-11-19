"""EXEC-MU-ACCOUNTS fix round, track guest (decision 1 of 2026-11-19; verification/edge_multiuser/fix_round/guest.md):
terminal-api's part of the guest Terminal and of the whole ticker list.

- The ticker list is whole for every owner (every plan that holds terminal.view, and the guest); the reference files
  that carry data per ticker keep the plan's filter. Which file is which is derived from its own columns
  (refcut.names_only), checked here against the columns the publisher really writes.
- x-terminal-client: the visitors of the guest plan share one owner row, and each is counted on its own (usage, lock,
  audit row); a call without the key is counted on the owner's row as a whole (stricter, never wider).
"""
import ast
import os
import re
from pathlib import Path

import pytest

from app import quota, refcut
from app.entitlements import Capabilities
from app.main import API, DATASETS
from test_phase3c import ADMIN_CAPS, GATEWAY, CutBucket, OwnerStore, caps, make, owner

PUBLISHER = Path(__file__).resolve().parents[2] / 'terminal-publisher' / 'publisher.py'
VISITOR_A, VISITOR_B = 'a' * 32, 'b' * 32
GUEST_OWNER = 'edge-guest'


def publisher_columns():
    """The columns of each reference file as publisher.py writes them, read from its source (no import: the publisher
    needs its own dependencies)."""
    text = PUBLISHER.read_text()
    tree = ast.parse(text)
    consts = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id in ('FI_COLUMNS', 'STOCK_LIST_COLUMNS')}
    tickers = ast.literal_eval(re.search(r"names = (\['ticker', 'name'[^\]]*\])", text).group(1))
    brokers = ast.literal_eval(re.search(r"brokers_doc = \{'schema_version': SCHEMA_VERSION, 'columns': (\[[^\]]*\])",
                                         text).group(1))
    logos = ast.literal_eval(re.search(r"doc = \{'schema_version': SCHEMA_VERSION, 'columns': (\['ticker', 'file'[^\]]*\])",
                                       text).group(1))
    return {'tickers': tickers, 'brokers': brokers, 'logos': logos, 'fixed_income': consts['FI_COLUMNS'],
            'stock_lists': consts['STOCK_LIST_COLUMNS']}


SAMPLE = {                       # one realistic value per column, of the type the publisher writes
    'ticker': 'TLKM', 'name': 'Telkom Indonesia', 'type': 'stock', 'sector': 'Infrastructures', 'industry': 'Telecom',
    'instrument': 'common', 'file': 'TLKM.png', 'sha256': 'c' * 64, 'source': 'stockbit', 'fetched_at': '2026-11-01',
    'country': 'ID', 'yield_unit': 'PCT', 'price_unit': 'PCTPAR', 'yield_first': '2010-01-04',
    'yield_last': '2026-11-17', 'price_first': '2010-01-04', 'price_last': '2026-11-17', 'code': 'YP',
    'classification': 'Retail-heavy', 'list_key': 'INDEX:LQ45', 'kind': 'INDEX', 'definition': 'LQ45',
    'as_of': '2026-11-17', 'members': ['BBCA', 'TLKM'],
}
FREE_CAPS = Capabilities('db-0123456789ab', False, frozenset({'BBCA'}), frozenset({'price'}), 730, ())


def test_the_ticker_list_is_whole_and_every_file_with_data_per_ticker_keeps_the_plans_filter():
    """The rule read on the publisher's own columns: the ticker list names its instruments only (whole); the logos (an
    index of published images), the bonds (their data dates) follow the plan's tickers; the broker list follows the
    broker dataset; the stock lists have no rule (no rows)."""
    columns = publisher_columns()
    assert set(columns) == set(re.findall(r"'([a-z_]+)'", re.search(r'^REF_NAMES = \(([^)]*)\)', PUBLISHER.read_text(),
                                                                      re.M).group(1)))
    kept = {}
    for name, cols in columns.items():
        doc = {'schema_version': 1, 'columns': cols, **{c: [SAMPLE[c], SAMPLE[c]] for c in cols}}
        if 'ticker' in cols:
            doc['ticker'] = ['BBCA', 'TLKM']
        kept[name] = refcut.keep(doc, name, FREE_CAPS, DATASETS)
    assert kept == {'tickers': [0, 1], 'logos': [0], 'fixed_income': [0], 'brokers': [], 'stock_lists': []}, kept
    assert refcut.names_only({'columns': columns['tickers'], **{c: [SAMPLE[c]] for c in columns['tickers']}},
                             columns['tickers'], DATASETS)


def test_names_only_is_read_from_the_columns_never_from_the_files_name():
    """A ticker-keyed file is whole only while every other column holds text: a figure, a list, a dataset's column or a
    column of digests makes it a file with data per ticker (fail closed for a new column)."""
    base = {'columns': ['ticker', 'name'], 'ticker': ['BBCA', 'TLKM'], 'name': ['BCA', 'Telkom']}
    assert refcut.names_only(base, base['columns'], DATASETS)
    for column, values in (('last_close', [9150.0, 2950.0]), ('members', [['A'], ['B']]),
                           ('price_last', ['2026-11-17', '2026-11-17']), ('digest', ['d' * 64, 'e' * 64]),
                           ('broker_top', ['YP', 'CC'])):
        doc = {**base, 'columns': base['columns'] + [column], column: values}
        assert not refcut.names_only(doc, doc['columns'], DATASETS), column
        assert refcut.keep(doc, 'tickers', FREE_CAPS, DATASETS) == [0], column
    # a column of nothing yet (every value null) still names nothing
    empty = {**base, 'columns': ['ticker', 'name', 'sector'], 'sector': [None, None]}
    assert refcut.keep(empty, 'tickers', FREE_CAPS, DATASETS) == [0, 1]


def test_the_test_fixtures_carry_the_publishers_columns():
    from test_terminal_fix_round import REFERENCE_FILES
    columns = publisher_columns()
    assert REFERENCE_FILES['fixed_income']['columns'] == columns['fixed_income']
    assert REFERENCE_FILES['logos']['columns'] == columns['logos']


# ---- x-terminal-client: the guest plan's visitors are counted one by one ----------------------------------------------

class VisitorStore(OwnerStore):
    """OwnerStore with the visitor key of migration 20261119_170 (terminal.access_log.client_key)."""
    def lock_subscriber(self, c, sid, client=None):
        self.events.append(('lock', sid, client))

    def usage(self, c, sid, client=None):
        mine = [a for a in self.access if a['sid'] == sid and (client is None or a.get('client') == client)]
        tickers = frozenset(a['ticker'] for a in mine if a['ticker'] != quota.REF)
        return quota.Usage(sum(a.get('files', 1) for a in mine if a['kind'] == 'file'), tickers, tickers,
                           sum(a['bytes'] for a in mine), sum(1 for a in mine if a['kind'].startswith('history')))

    def log_access(self, c, sid, kind, ticker, ip, dataset=None, year=None, key=None, bytes_=0, keys=None, version=None,
                   client=None):
        super().log_access(c, sid, kind, ticker, ip, dataset, year, key, bytes_, keys, version)
        self.access[-1]['client'] = client


GUEST_CAPS = caps(tickers=['BBCA'], datasets=['price'], history_days=None, quota={'files_per_hour': 1})


def guest(visitor=None):
    return {**owner(GUEST_OWNER, GUEST_CAPS), **({'x-terminal-client': visitor} if visitor else {})}


def bundle(client, headers):
    return client.post(f'{API}/bundle', headers=headers, json={'ticker': 'BBCA', 'datasets': ['price'], 'packs': True})


def test_each_visitor_of_the_guest_owner_has_its_own_quota_and_a_call_without_a_key_shares_the_owners():
    client, store, _ = make(CutBucket(), VisitorStore())
    assert bundle(client, guest(VISITOR_A)).status_code == 200
    r = bundle(client, guest(VISITOR_A))
    assert r.status_code == 429 and r.json()['quota'] == 'files_per_hour', r.text           # the visitor's own hour
    assert bundle(client, guest(VISITOR_B)).status_code == 200                              # another visitor: its own
    rows = [a for a in store.access if a['kind'] == 'file']
    assert [a['client'] for a in rows] == [VISITOR_A, VISITOR_B]
    assert len({a['sid'] for a in rows}) == 1                                               # one guest owner row
    assert ('lock', rows[0]['sid'], VISITOR_A) in store.events and ('lock', rows[0]['sid'], VISITOR_B) in store.events
    # the owner without a visitor key: every visitor's rows of its row count (fail closed: stricter, never wider)
    r = bundle(client, guest())
    assert r.status_code == 429 and r.json()['quota'] == 'files_per_hour'


@pytest.mark.parametrize('headers, field', [
    ({**GATEWAY, 'x-terminal-client': VISITOR_A}, 'x-terminal-client'),                     # no owner headers
    ({**owner(GUEST_OWNER, ADMIN_CAPS), 'x-terminal-client': VISITOR_A}, 'x-terminal-client'),   # an owner holding *
    ({**owner(GUEST_OWNER, GUEST_CAPS), 'x-terminal-client': '10.0.0.1'}, 'x-terminal-client'),   # an address, not a key
    ({**owner(GUEST_OWNER, GUEST_CAPS), 'x-terminal-client': 'A' * 32}, 'x-terminal-client'),
])
def test_a_visitor_key_that_breaks_its_rule_is_refused_naming_the_header(headers, field):
    client, _, _ = make(CutBucket(), VisitorStore())
    r = client.get(f'{API}/manifest/BBCA', headers=headers)
    assert r.status_code == 400, r.text
    body = r.json()
    assert body['error'] == 'invalid_owner_headers' and body['field'] == field
    assert 'Fix:' in body['message'] and 'Example:' in body['message'] and '10.0.0.1' not in body['message']


def test_a_service_key_or_a_cookie_never_names_a_visitor():
    from test_api import BACKTEST_KEY, services_client
    client, _, _ = services_client()
    r = client.get(f'{API}/state', headers={'x-terminal-proxy-key': BACKTEST_KEY, 'x-terminal-client': VISITOR_A})
    assert r.status_code == 400 and r.json()['error'] == 'owner_not_allowed'
    r = client.get(f'{API}/state', headers={'x-terminal-client': VISITOR_A})
    assert r.status_code in (400, 403) and r.json()['error'] in ('owner_not_allowed', 'direct_access_closed')


# ---- on a real server: the store counts and locks per visitor -----------------------------------------------------

def test_the_store_counts_each_visitor_apart_on_a_real_server():
    url = os.environ.get('TERMINAL_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TERMINAL_TEST_POSTGRES_URL is not set')
    from app.store import Store
    store = Store(url, max_size=2)
    store.open()
    try:
        with store.tx() as c:
            sid = store.owner_account(c, f'edge-guest-{os.getpid()}')['subscriber_id']
            for visitor, ticker in ((VISITOR_A, 'BBCA'), (VISITOR_A, 'BBRI'), (VISITOR_B, 'BBCA')):
                store.lock_subscriber(c, sid, client=visitor)
                store.log_access(c, sid, 'file', ticker, None, dataset='bundle', bytes_=10, keys=['k1', 'k2'],
                                 version='db-0123456789ab', client=visitor)
            a, b, whole = store.usage(c, sid, client=VISITOR_A), store.usage(c, sid, client=VISITOR_B), store.usage(c, sid)
            assert (a.files_hour, a.tickers_hour, a.bytes_day) == (4, frozenset({'BBCA', 'BBRI'}), 20)
            assert (b.files_hour, b.tickers_hour) == (2, frozenset({'BBCA'}))
            assert whole.files_hour == 6                                    # the owner as a whole: every visitor
            refusal = quota.Refusal('files_per_hour', 4, 'hour', 1)
            assert 3500 < store.frees_in(c, sid, refusal, client=VISITOR_A) <= 3600
            assert 3500 < store.frees_in(c, sid, quota.Refusal('tickers_per_hour', 1, 'hour'), client=VISITOR_B) <= 3600
            rows = c.execute('SELECT client_key FROM terminal.access_log WHERE subscriber_id = %s ORDER BY access_id',
                             (sid,)).fetchall()
            assert [r['client_key'] for r in rows] == [VISITOR_A, VISITOR_A, VISITOR_B]
            plan = '\n'.join(r['QUERY PLAN'] for r in c.execute(
                "EXPLAIN SELECT count(*) FROM terminal.access_log WHERE subscriber_id = %s AND client_key = %s "
                "AND at > now() - interval '1 day'", (sid, VISITOR_A)).fetchall())
            assert 'access_log_client_at' in plan or 'Seq Scan' in plan                 # tiny table: either is fine
            c.execute('DELETE FROM terminal.access_log WHERE subscriber_id = %s', (sid,))
            c.execute('DELETE FROM terminal.subscriber WHERE subscriber_id = %s', (sid,))
            with pytest.raises(Exception):
                with c.transaction():
                    c.execute("INSERT INTO terminal.access_log(subscriber_id, kind, ticker, ip, client_key) "
                              "VALUES (%s, 'file', 'BBCA', NULL, '10.0.0.1')", (sid,))
    finally:
        store.close()
