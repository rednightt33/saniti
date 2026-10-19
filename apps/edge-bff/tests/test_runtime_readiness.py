import asyncio
from types import SimpleNamespace

import httpx

from app.client import OrcClient
from app.worker import Worker


class Store:
    def __init__(self):
        self.row = dict(owner_key='owner', request_id='same-id', attempt_count=0,
                        input={'message': 'Calculate'}, state='QUEUED')
        self.events = []

    def job(self, *_):
        return self.row

    def transition(self, row, state, **fields):
        row.update(state=state, **fields)
        self.events.append((state, row['attempt_count'], fields.get('error_code')))
        return row

    def attempted(self, row):
        return True


class Orc:
    def __init__(self, store, mode='recover'):
        self.store, self.mode, self.probes, self.calls = store, mode, 0, []

    def request(self, *_):
        return None

    def execution_ready(self, owner):
        assert owner == 'owner'
        self.probes += 1
        assert self.store.row['attempt_count'] == 0
        if self.mode == 'stop':
            self.store.row['input']['stop_requested'] = True
            return True
        return self.mode == 'recover' and self.probes > 5

    def run(self, owner, request_id, payload):
        self.calls.append(request_id)
        return {'status': 'COMPLETED', 'conversation': {'conversation_id': 'conv', 'persistence': 'SAVED'}}


def worker(store, orc, timeout=1):
    return Worker(SimpleNamespace(orc_timeout_seconds=timeout, lease_seconds=0,
                                  poll_seconds=0.001), store, orc)


def test_waiting_does_not_exhaust_dispatch_attempts_and_recovers_with_the_same_id():
    store = Store()
    orc = Orc(store)
    asyncio.run(worker(store, orc).execute(store.row))
    assert len([e for e in store.events if e[0] == 'RECOVERING']) == 5
    assert all(e[1] == 0 for e in store.events[:-1])
    assert store.row['state'] == 'FINISHED' and store.row['attempt_count'] == 1
    assert orc.calls == ['same-id']


def test_stop_during_readiness_does_not_dispatch():
    store = Store()
    orc = Orc(store, 'stop')
    asyncio.run(worker(store, orc).execute(store.row))
    assert store.row['error_code'] == 'STOPPED_BY_USER'
    assert not orc.calls and store.row['attempt_count'] == 0


def test_dependency_wait_has_a_deadline_without_claiming_remote_cancellation():
    store = Store()
    orc = Orc(store, 'down')
    asyncio.run(worker(store, orc, timeout=0.01).execute(store.row))
    assert store.row['state'] == 'INTERRUPTED' and store.row['error_code'] == 'RECOVERY_TIMEOUT'
    assert not orc.calls and store.row['attempt_count'] == 0


def test_client_reads_readiness_and_allows_an_older_orc_during_rolling_deploy():
    for status, body, expected in [(200, {'status': 'ready'}, True),
                                   (200, {'status': 'initializing'}, False), (404, {}, True)]:
        def handler(request):
            assert request.method == 'GET' and request.url.path == '/v1/agent/readiness'
            assert request.headers['x-saniti-owner'] == 'owner'
            return httpx.Response(status, json=body)
        settings = SimpleNamespace(orc_key='test-key')
        with httpx.Client(base_url='http://orc.test', transport=httpx.MockTransport(handler)) as http:
            assert OrcClient(settings, http).execution_ready('owner') is expected
