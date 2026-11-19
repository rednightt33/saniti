"""Independent check of the beta/live split before the 3c deploy (lens "site": EXEC-MU-ACCOUNTS "Production environment",
CONTRACT.md section 17). Failing tests of the defects found; each names the rule it holds.

1. The two websites share one backtest-worker (option A, "go with option A"), and each runs its own backtest loop
   (CONTRACT.md 17: "each site claims, reaps and prunes only its own"). The worker keeps one job: POST /v1/jobs answers
   409 BUSY while one runs, a new job replaces the finished one, and then "404 UNKNOWN_JOB for any job but the latest"
   and "410 RESULT_GONE for the job it replaced" (apps/backtest-worker/src/server.ts:16-27, :376-410). edge-bff's
   follower ends a job WORKER_LOST at the first 404 or 410 (app/backtest.py follow, ingest). One loop (one edge-bff, as
   before the split) never posts while it still follows a job; two loops do: the other site's BUSY retry lands between
   the finish of this site's job and its follower's next poll, replaces it, and the finished backtest is lost.
2. The live mask (principal.live_view) takes '*' out of a principal's `capabilities` so the shell shows no Monitor; the
   Terminal header reads '*' from there (terminal_access.admin), so user #1, whose plan holds '*', is sent to
   terminal-api as a capped owner with no quota of its own: terminal-api's terminal.quota defaults (30 tickers an hour,
   60 files an hour, 300 MB a day; migration 20261025_100), below the paid plan (D6: 60, 300, 500), on the one owner row
   the beta's admin usage is counted on too. The rule (CONTRACT.md 8b "3c in detail", "Quotas (decision D6)"; terminal-api
   main.py:29): an owner holding * gets the gateway subscriber's own limits. The Terminal is no beta-only tab.
3. The live site never holds a lab item, '*' included (CONTRACT.md 17). catalog.holds_every reads '*' and {"all": true}
   from the grants without the live mask (allow.allow_of has it, `whole`), so the Screener catalog's preset filter
   (Screeners.catalog_for, grant_key None) is skipped there and a lab-stage preset is listed on the live site.
4. On the live site '*' reads as the catalog's flag capabilities (live_view `flags`, Auth.flags), which only
   Auth.refresh_names fills; a failure of it at the start is logged and the start goes on, so user #1 then holds no
   capability in its session answer (the shell shows no tab) until a refusal reads the names again.
"""
import asyncio
import dataclasses
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import psycopg
from fastapi.testclient import TestClient

from app import releases, terminal_access
from app.allow import allow_of
from app.backtest import BacktestLoop, BacktestStore, WorkerClient
from app.main import create_app
from app.principal import switch_off_principal
from app.rights import rights_of
from app.screener import Doc
from conftest import FakeOrc
from test_backtest import KEY, backtest_tables, lineage_of, result_of, single, variant_of  # noqa: F401 - fixture
from test_beta_live_site import live_of, sign_in_admin
from test_phase3a_gates import override, paid_user


class OneSlotWorker:
    """The backtest worker's job routes as server.ts serves them: one job kept at a time (`job`), 409 BUSY while it runs,
    a new job replaces a finished one (`replaced`), 404 UNKNOWN_JOB for any other id and 410 RESULT_GONE for the
    replaced one's result. A job runs until the test lets it finish (its id put in `finished`)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job, self.replaced, self.finished, self.requests = None, None, set(), {}
        self.busy, self.on_poll, self.polls = [], None, {}
        worker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, body=None, raw=None):
                data = raw if raw is not None else json.dumps(body).encode() if body is not None else b''
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                if raw is not None:
                    self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('content-length') or 0)) or b'null')
                with worker.lock:
                    if self.path == '/v1/jobs':
                        if worker.job == body['job_id']:
                            return self.answer(202, {'job_id': body['job_id']})
                        if worker.job is not None and worker.job not in worker.finished:
                            worker.busy.append(body['job_id'])
                            return self.answer(409, {'error': {'code': 'BUSY', 'message': 'Another backtest is running.'}})
                        worker.replaced = worker.job if worker.job in worker.finished else None
                        worker.job = body['job_id']
                        worker.requests[body['job_id']] = body['request']
                        return self.answer(202, {'job_id': body['job_id']})
                    if self.path.endswith('/cancel'):
                        return self.answer(202, {})
                return self.answer(404, {'error': {'code': 'NOT_FOUND'}})

            def do_GET(self):
                parts = self.path.split('/')
                job_id, sub = parts[3], parts[4:]
                with worker.lock:
                    current = worker.job == job_id
                    if not current and sub == ['result'] and job_id == worker.replaced:
                        return self.answer(410, {'error': {'code': 'RESULT_GONE'}})
                    if not current:
                        return self.answer(404, {'error': {'code': 'UNKNOWN_JOB'}})
                    state = 'FINISHED' if job_id in worker.finished else 'RUNNING'
                    request = worker.requests[job_id]
                if sub == ['result']:
                    return self.answer(200, raw=gzip.compress(json.dumps(result_of(job_id, request)).encode()))
                worker.polls[job_id] = worker.polls.get(job_id, 0) + 1
                self.answer(200, {'request_id': job_id, 'state': state, 'progress': None, 'error': None,
                                  'duration_ms': None, 'result_bytes': None})
                if worker.on_poll:
                    worker.on_poll(job_id)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_a_backtest_of_one_site_is_not_lost_when_the_other_sites_loop_uses_the_shared_worker(settings, store,
                                                                                             backtest_tables):
    worker = OneSlotWorker()
    try:
        with psycopg.connect(backtest_tables) as c:
            c.execute('TRUNCATE edge_bff.backtest_results, edge_bff.backtest_trials, edge_bff.backtest_jobs')
        configured = dataclasses.replace(settings, backtest_worker_url=worker.url, backtest_worker_key=KEY,
                                         backtest_timeout_seconds=30, backtest_max_result_bytes=2 ** 20)
        beta, live = BacktestStore(store, 'beta'), BacktestStore(store, 'live')
        request = single()
        # control: one loop (one edge-bff, as before the split) follows each job to its end before the next hand-over,
        # so this worker serves two jobs one after the other
        worker.on_poll = lambda job_id: worker.finished.add(job_id) if worker.polls[job_id] >= 2 else None
        for key in ('control-1', 'control-2'):
            one = BacktestLoop(dataclasses.replace(configured, poll_seconds=0.02), beta, WorkerClient(configured))
            beta.submit(configured.owner, key, request, lineage_of(request), variant_of(request), 3)
            asyncio.run(one.process(beta.claim(90)))
        with store.connect() as c:
            assert [r['state'] for r in c.execute('SELECT state FROM edge_bff.backtest_jobs').fetchall()] == ['FINISHED'] * 2
            c.execute('TRUNCATE edge_bff.backtest_results, edge_bff.backtest_trials, edge_bff.backtest_jobs')
        worker.job, worker.replaced, worker.finished, worker.polls = None, None, set(), {}
        # the admin's backtest on the beta, a paid account's on the live site (different owners: one running each)
        a, _ = beta.submit(configured.owner, 'beta-job', request, lineage_of(request), variant_of(request), 3)
        b, _ = live.submit('u_0123456789abcdef01234567', 'live-job', request, lineage_of(request), variant_of(request), 3)
        row_a, row_b = beta.claim(90), live.claim(90)
        assert (row_a['request_id'], row_b['request_id']) == (a['request_id'], b['request_id'])
        # each site's loop at the same EDGE_POLL_SECONDS; the live loop's principal holds backtest.run (not the subject)
        beta_loop = BacktestLoop(dataclasses.replace(configured, poll_seconds=0.3), beta, WorkerClient(configured))
        live_loop = BacktestLoop(dataclasses.replace(configured, poll_seconds=0.3), live, WorkerClient(configured))
        live_loop.access = lambda owner: switch_off_principal(configured, configured.owner)

        def on_poll(job_id):
            # the beta's job finishes on the worker right after a status read of its follower, once the live job waits
            if job_id == a['request_id'] and worker.busy:
                worker.finished.add(job_id)
            if job_id == b['request_id'] and worker.polls[job_id] >= 2:
                worker.finished.add(job_id)
        worker.on_poll = on_poll

        async def both():
            follow_a = asyncio.create_task(beta_loop.process(row_a))
            for _ in range(500):
                if worker.job == a['request_id']:
                    break
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.15)                       # the live loop's turn falls between the beta's polls
            await asyncio.wait_for(asyncio.gather(follow_a, live_loop.process(row_b)), timeout=20)
        asyncio.run(both())
        with store.connect() as c:
            ended = {r['request_id']: (r['state'], r['error']) for r in
                     c.execute('SELECT request_id, state, error FROM edge_bff.backtest_jobs').fetchall()}
        assert ended[b['request_id']][0] == 'FINISHED', ended
        # the beta's backtest finished on the worker; the live site's hand-over replaced it before its follower
        # fetched the result, so it ends FAILED WORKER_LOST
        assert ended[a['request_id']] == ('FINISHED', None), ended
    finally:
        worker.close()


def test_user_one_on_the_live_site_keeps_the_terminal_quota_of_an_owner_holding_everything(settings, store):
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        assert c.get('/api/v1/auth/session').status_code == 200
        p = app.state.auth.owner_principal(settings.owner)
        assert p.can('terminal.view') and p.grants.get('*') is True        # its plan holds '*' (the seed's plan)
        caps = terminal_access.capabilities(p)
        # sent today: {"admin": false, "quota": {}} -> terminal-api's defaults, below the paid plan's quota
        assert caps['admin'] is True, caps


def test_a_lab_preset_is_not_listed_on_the_live_site(settings, store, monkeypatch):
    presets = releases.entries('screener_preset')
    lab, released = presets[0]['id'], presets[1]['id']
    items = [{'kind': kind, 'id': e['id'], 'stage': 'lab' if (kind, e['id']) == ('screener_preset', lab) else e['stage']}
             for kind in releases.KINDS for e in releases.entries(kind)]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({'schema_version': 1, 'items': items}))
    raw = json.dumps({'presets': [{'id': lab, 'items': []}, {'id': released, 'items': []}], 'metrics': []}).encode()
    doc = Doc(key='k', raw=raw, gz=gzip.compress(raw), etag='"e"', price_data=None)
    app = create_app(live_of(settings), store, FakeOrc())
    with TestClient(app) as c:
        sign_in_admin(c, store)
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'screener.preset', '{"all": true}')
        for owner in (alice['owner_key'], settings.owner):
            p = app.state.auth.owner_principal(owner)
            assert not p.can(f'screener.preset:{lab}')                       # the mask: never held on live
            shown = json.loads(app.state.screeners.catalog_for(doc, rights_of(p), allow_of(p, 'screener'), p).raw)
            assert [x['id'] for x in shown['presets']] == [released], (owner, shown['presets'])


def test_a_catalog_read_that_fails_at_the_start_leaves_user_one_with_its_tabs_on_the_live_site(settings, store,
                                                                                                monkeypatch):
    """Item 4 of the module docstring: the names' read fails once at the start (main.py start_up logs
    capability_names_failed and goes on); it is read again only after a refusal, at most every NAMES_SECONDS, and user #1
    (holding '*') meets no refusal on the tabs of its plan."""
    app = create_app(live_of(settings), store, FakeOrc())
    real, calls = app.state.auth.refresh_names, {'n': 0}

    def flaky(force=True):
        calls['n'] += 1
        if calls['n'] == 1:
            raise psycopg.OperationalError('the connection was closed')
        return real(force)
    monkeypatch.setattr(app.state.auth, 'refresh_names', flaky)
    with TestClient(app) as c:
        assert c.get('/ready').status_code == 200
        sign_in_admin(c, store)
        for _ in range(3):
            caps = c.get('/api/v1/auth/session').json()['access']['capabilities']
        assert 'terminal.view' in caps, caps
