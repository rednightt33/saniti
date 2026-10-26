"""EDGE backtest in edge-bff (apps/edge-bff/backtest/CONTRACT.md sections 8, 9 and 11): the public /api/v1/backtests
routes, the job tables of migration 20261026_005, the client of the private backtest worker and the queue loop that
hands one job at a time to it. edge-bff stores the request and the result as JSON and reads only the fields the
contract names for it (result meta versions and trials, events.conditions / events.exits per ticker)."""
import asyncio
from contextlib import contextmanager
import gzip
import hashlib
import json
import logging
import re
import secrets
import time

import httpx
import psycopg
from fastapi import Depends, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from .client import public_data
from .store import StoreError

logger = logging.getLogger('edge_bff.backtest')

JOB_ID = re.compile(r'bt_[0-9a-f]{32}')
SUBMISSION = re.compile(r'[A-Za-z0-9._:-]{1,100}')   # the house submission_key (main.RunInput)
TICKER = re.compile(r'[A-Z0-9]{1,12}')               # terminal-api's ticker rule; a result part is 'events:<ticker>'
HEX64 = re.compile(r'[0-9a-f]{64}')
ENDED = ('FINISHED', 'FAILED', 'CANCELLED')
TABLES = ('backtest_jobs', 'backtest_results', 'backtest_trials')
RESULT_DAYS = 30           # CONTRACT.md section 9: results are kept 30 days
PRUNE_SECONDS = 3600       # as the ORC loop's session cleanup (worker.py): once an hour
WORKER_RETRIES = 3         # consecutive unanswered worker calls before WORKER_LOST (the house's STOP_RETRIES, Orc's 3 attempts)
CONTROL_TIMEOUT = 30       # seconds for one control call to the worker (the terminal gateway's client timeout, main.py)
# Not derivable from the code or the data: the catalog changes when the publisher publishes (daily) or the worker is
# deployed, so one minute bounds how long a new catalog waits; the last one is kept while the worker cannot answer.
CATALOG_CACHE_SECONDS = 60


class BacktestError(Exception):
    """An answer in the contract's error shape {"error": {code, field?, message?, details?}} with its HTTP status."""
    def __init__(self, status, error):
        self.status, self.error = status, error
        super().__init__(error.get('code'))


class WorkerUnavailable(Exception):
    """The worker did not answer as its API says: no connection, a server error, our key refused, or not JSON."""


def _reject(value):
    raise ValueError(f'{value} is not JSON')   # NaN / Infinity: the contract never sends them (contract.ts units)


def loads(raw):
    return json.loads(raw, parse_constant=_reject)


def dumps(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def packed(value):
    """Gzip JSON of one stored part; mtime 0 so the same part always gives the same bytes and sha256."""
    return gzip.compress(dumps(value), mtime=0)


def error_of(data):
    """The error object of a worker answer, reduced to the contract's fields (internal addresses redacted as every
    upstream text, client.public_data); None when the answer carries none."""
    found = data.get('error') if isinstance(data, dict) else None
    if not isinstance(found, dict) or not isinstance(found.get('code'), str) or not found['code']:
        return None
    kept = {k: found[k] for k in ('code', 'field', 'message', 'details') if found.get(k) is not None}
    return public_data(kept)


def accepts_gzip(request):
    for token in request.headers.get('accept-encoding', '').lower().split(','):
        name, _, params = token.strip().partition(';')
        if name.strip() in ('gzip', '*'):
            q = params.strip()
            return not (q.startswith('q=') and q[2:].strip() in ('0', '0.0', '0.00', '0.000'))
    return False


def json_part(request, payload):
    """A stored gzip JSON part as the answer: sent as it is when the client takes gzip (every browser), else unpacked."""
    if accepts_gzip(request):
        return Response(payload, media_type='application/json', headers={'Content-Encoding': 'gzip', 'Vary': 'Accept-Encoding'})
    return Response(gzip.decompress(payload), media_type='application/json', headers={'Vary': 'Accept-Encoding'})


def status_of(row):
    """JobStatus (contract.ts) of a job row."""
    return jsonable_encoder({'request_id': row['request_id'], 'state': row['state'], 'progress': row['progress'],
                             'error': row['error'], 'created_at': row['created_at'], 'started_at': row['started_at'],
                             'finished_at': row['finished_at'], 'duration_ms': row['duration_ms'],
                             'result_bytes': row['result_bytes']})


def split_result(result, single_ticker=None):
    """The worker's BacktestResult as the stored parts (CONTRACT.md section 9): 'core' = everything except
    events.conditions and events.exits; 'events:<ticker>' = {conditions, exits} of that ticker, for every ticker of
    the run (meta.tickers) and every ticker the events name. Also the fields edge-bff records: versions, duration and
    the trials. ValueError when the result lacks what the contract says it carries."""
    if not isinstance(result, dict) or result.get('schema_version') != 1:
        raise ValueError('schema_version')
    meta, events = result.get('meta'), result.get('events')
    if not isinstance(meta, dict) or not isinstance(events, dict):
        raise ValueError('meta/events')
    conditions, exits, tickers = events.get('conditions'), events.get('exits'), meta.get('tickers')
    if not isinstance(conditions, list) or not isinstance(exits, dict) or not isinstance(tickers, list):
        raise ValueError('events.conditions/exits, meta.tickers')
    versions = {k: meta.get(k) for k in ('engine_version', 'registry_version', 'data_version')}
    if not all(isinstance(v, str) and 0 < len(v) <= 200 for v in versions.values()) or not HEX64.fullmatch(versions['data_version']):
        raise ValueError('meta versions')
    duration = meta.get('duration_ms')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise ValueError('meta.duration_ms')
    variants = ((meta.get('trials') or {}).get('variants'))
    if not isinstance(variants, list):
        raise ValueError('meta.trials.variants')
    trials = []
    for v in variants:
        if not isinstance(v, dict) or not isinstance(v.get('variant_hash'), str) or not HEX64.fullmatch(v['variant_hash']) \
                or v.get('kind') not in ('run', 'sensitivity'):
            raise ValueError('meta.trials.variants entry')
        sharpe = v.get('sharpe_daily')
        if isinstance(sharpe, bool) or not isinstance(sharpe, (int, float)):
            # a variant without a finite daily Sharpe cannot enter the trial variance; logged, never counted as 0
            logger.warning(json.dumps({'event': 'backtest_trial_without_sharpe', 'variant_hash': v['variant_hash']}))
            continue
        trials.append((v['variant_hash'], float(sharpe), v['kind']))
    parts = {}
    def part(ticker):
        if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
            raise ValueError('ticker')
        return parts.setdefault(ticker, {'conditions': [], 'exits': {}})
    for t in tickers:
        part(t)
    for item in conditions:
        part(item.get('ticker') if isinstance(item, dict) else None)['conditions'].append(item)
    for t, track in exits.items():
        part(t)['exits'][t] = track
    if single_ticker is not None and single_ticker not in parts:
        raise ValueError('single ticker without events')
    core = {**result, 'events': {k: v for k, v in events.items() if k not in ('conditions', 'exits')}}
    stored = [('core', packed(core))] + [(f'events:{t}', packed(p)) for t, p in sorted(parts.items())]
    return {'parts': stored, 'versions': versions, 'duration_ms': int(duration), 'trials': trials,
            'lineage_key': meta.get('lineage_key')}


class WorkerClient:
    """The private backtest worker (CONTRACT.md section 8), every route but /health behind x-backtest-worker-key.
    Blocking calls; the routes and the loop run them in threads (as OrcClient)."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(base_url=settings.backtest_worker_url, timeout=CONTROL_TIMEOUT,
                                             follow_redirects=False, trust_env=False)

    def _send(self, method, path, body, timeout):
        try:
            response = self.client.request(method, path, json=body, timeout=timeout or CONTROL_TIMEOUT,
                                           headers={'x-backtest-worker-key': self.settings.backtest_worker_key})
        except httpx.HTTPError as e:
            raise WorkerUnavailable() from e
        if response.status_code >= 500 or response.status_code == 401:
            if response.status_code == 401:
                logger.error('backtest_worker_key_refused')
            raise WorkerUnavailable()
        return response

    def call(self, method, path, body=None, timeout=None):
        """(status, JSON body) of one call."""
        response = self._send(method, path, body, timeout)
        try:
            return response.status_code, loads(response.content)
        except ValueError as e:
            raise WorkerUnavailable() from e

    def cancel(self, job_id):
        """True when the worker took the cancellation (its answer body is not read)."""
        return 200 <= self._send('POST', f'/v1/jobs/{job_id}/cancel', None, None).status_code < 300

    def result(self, job_id):
        """(status, body bytes) of the finished job's result: the worker sends gzip JSON with Content-Encoding gzip,
        which httpx unpacks. The download may take as long as a job may run."""
        response = self._send('GET', f'/v1/jobs/{job_id}/result', None, self.settings.backtest_timeout_seconds)
        return response.status_code, response.content

    def close(self):
        self.client.close()


class BacktestStore:
    """edge_bff.backtest_jobs / backtest_results / backtest_trials through the house Store's connections. A missing
    table (the migration not applied yet) is BACKTEST_NOT_READY; /ready never reads these tables."""

    def __init__(self, store):
        self.store = store

    @contextmanager
    def connect(self):
        try:
            with self.store.connect() as c:
                yield c
        except psycopg.errors.UndefinedTable as e:
            raise StoreError('BACKTEST_NOT_READY', 503) from e

    def ready(self):
        with self.connect() as c:
            for table in TABLES:
                c.execute(f'SELECT 1 FROM edge_bff.{table} LIMIT 0')

    @staticmethod
    def _log(row, **extra):
        if row:
            logger.info(json.dumps({'event': 'backtest_state', 'request_id': row['request_id'], 'state': row['state'],
                                    **({'code': row['error']['code']} if row.get('error') else {}), **extra}))

    def find(self, owner, key):
        with self.connect() as c:
            return c.execute('SELECT * FROM edge_bff.backtest_jobs WHERE owner_key=%s AND submission_key=%s',
                             (owner, key)).fetchone()

    def submit(self, owner, key, request, lineage_key, variant_hash, queued_limit):
        """A new QUEUED job, or the job this submission key already made (same request; another request under the same
        key is SUBMISSION_CONFLICT). At most queued_limit queued jobs per owner (QUEUE_FULL); one owner's submissions
        are serialised by an advisory lock, as edge_bff.jobs submissions (store.submit)."""
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('backtest:' + owner,))
            row = c.execute('SELECT * FROM edge_bff.backtest_jobs WHERE owner_key=%s AND submission_key=%s',
                            (owner, key)).fetchone()
            if row:
                if row['request'] != request:
                    raise StoreError('SUBMISSION_CONFLICT')
                return row, False
            queued = c.execute("SELECT count(*) AS n FROM edge_bff.backtest_jobs WHERE owner_key=%s AND state='QUEUED'",
                               (owner,)).fetchone()['n']
            if queued >= queued_limit:
                raise StoreError('QUEUE_FULL', 429)
            row = c.execute('''INSERT INTO edge_bff.backtest_jobs(request_id,owner_key,submission_key,request,lineage_key,
                    variant_hash) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *''',
                (('bt_' + secrets.token_hex(16)), owner, key, Jsonb(request), lineage_key, variant_hash)).fetchone()
            self._log(row)
            return row, True

    def job(self, owner, request_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM edge_bff.backtest_jobs WHERE owner_key=%s AND request_id=%s',
                            (owner, request_id)).fetchone() if JOB_ID.fullmatch(request_id or '') else None
        if not row:
            raise StoreError('BACKTEST_NOT_FOUND', 404)
        return row

    def jobs(self, owner, limit):
        with self.connect() as c:
            return c.execute('''SELECT * FROM edge_bff.backtest_jobs WHERE owner_key=%s
                ORDER BY created_at DESC, request_id LIMIT %s''', (owner, limit)).fetchall()

    def cancel(self, owner, request_id):
        """A queued job ends CANCELLED here (it never reaches the worker); a running one is marked and the loop asks
        the worker to stop it. None when the job had already ended."""
        self.job(owner, request_id)
        with self.connect() as c:
            row = c.execute('''UPDATE edge_bff.backtest_jobs SET state='CANCELLED',finished_at=now(),updated_at=now()
                WHERE owner_key=%s AND request_id=%s AND state='QUEUED' RETURNING *''', (owner, request_id)).fetchone()
            if row:
                self._log(row)
                return row
            return c.execute('''UPDATE edge_bff.backtest_jobs SET cancel_requested=true,updated_at=now()
                WHERE owner_key=%s AND request_id=%s AND state='RUNNING' RETURNING *''', (owner, request_id)).fetchone()

    def part(self, request_id, part):
        """The stored gzip bytes of one part, checked against its sha256; None when there is none (pruned, or a ticker
        the run did not have)."""
        with self.connect() as c:
            row = c.execute('SELECT payload, sha256 FROM edge_bff.backtest_results WHERE request_id=%s AND part=%s',
                            (request_id, part)).fetchone()
        if not row:
            return None
        payload = bytes(row['payload'])
        if hashlib.sha256(payload).hexdigest() != row['sha256']:
            raise StoreError('RESULT_INTEGRITY', 500)
        return payload

    def has(self, request_id, part):
        with self.connect() as c:
            return c.execute('SELECT 1 FROM edge_bff.backtest_results WHERE request_id=%s AND part=%s',
                             (request_id, part)).fetchone() is not None

    # ---- the loop's side: claim, lease, progress, end -------------------------------------------------------------

    def reap(self):
        """RUNNING jobs whose lease expired (edge-bff stopped or lost the database while following them): FAILED
        WORKER_LOST, never handed to the worker again. Their ids, so the worker can be told to stop them."""
        with self.connect() as c:
            rows = c.execute('''UPDATE edge_bff.backtest_jobs SET state='FAILED',error=%s,lease_token=NULL,
                lease_expires_at=NULL,finished_at=now(),updated_at=now()
                WHERE state='RUNNING' AND lease_expires_at<now() RETURNING *''', (Jsonb({'code': 'WORKER_LOST'}),)).fetchall()
        for row in rows:
            self._log(row, reason='lease_expired')
        return [r['request_id'] for r in rows]

    def claim(self, seconds):
        """The oldest queued job of an owner with nothing running, RUNNING under a new lease."""
        with self.connect() as c:
            return c.execute('''WITH next AS (
                    SELECT j.request_id FROM edge_bff.backtest_jobs j WHERE j.state='QUEUED' AND NOT EXISTS (
                        SELECT 1 FROM edge_bff.backtest_jobs r WHERE r.owner_key=j.owner_key AND r.state='RUNNING')
                    ORDER BY j.created_at, j.request_id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE edge_bff.backtest_jobs SET state='RUNNING',lease_token=%s,
                    lease_expires_at=now()+%s*interval '1 second',started_at=now(),updated_at=now()
                WHERE request_id=(SELECT request_id FROM next) RETURNING *''',
                (secrets.token_hex(16), seconds)).fetchone()

    _FENCE = 'request_id=%s AND lease_token=%s AND lease_expires_at>now() AND state=\'RUNNING\''

    def heartbeat(self, row, seconds):
        with self.connect() as c:
            return bool(c.execute(f'''UPDATE edge_bff.backtest_jobs SET lease_expires_at=now()+%s*interval '1 second'
                WHERE {self._FENCE}''', (seconds, row['request_id'], row['lease_token'])).rowcount)

    def current(self, row):
        """The job while this lease holds it (None once it is lost or the job ended)."""
        with self.connect() as c:
            return c.execute(f'SELECT * FROM edge_bff.backtest_jobs WHERE {self._FENCE}',
                             (row['request_id'], row['lease_token'])).fetchone()

    def progress(self, row, progress):
        with self.connect() as c:
            return bool(c.execute(f'UPDATE edge_bff.backtest_jobs SET progress=%s,updated_at=now() WHERE {self._FENCE}',
                                  (Jsonb(progress) if progress is not None else None, row['request_id'],
                                   row['lease_token'])).rowcount)

    def prior_trials(self, owner, lineage_key):
        """JobContext.prior_trials: every variant recorded for this owner and strategy line, oldest first."""
        with self.connect() as c:
            rows = c.execute('''SELECT variant_hash, sharpe_daily FROM edge_bff.backtest_trials
                WHERE owner_key=%s AND lineage_key=%s ORDER BY created_at, variant_hash''', (owner, lineage_key)).fetchall()
        return [{'variant_hash': r['variant_hash'], 'sharpe_daily': r['sharpe_daily']} for r in rows]

    def end(self, row, state, error=None, duration_ms=None):
        """FAILED (with its error) or CANCELLED, fenced by the lease; None when the lease was lost."""
        with self.connect() as c:
            changed = c.execute(f'''UPDATE edge_bff.backtest_jobs SET state=%s,error=%s,duration_ms=%s,lease_token=NULL,
                lease_expires_at=NULL,finished_at=now(),updated_at=now() WHERE {self._FENCE} RETURNING *''',
                (state, Jsonb(error) if error else None, duration_ms, row['request_id'], row['lease_token'])).fetchone()
        self._log(changed)
        return changed

    def finish(self, row, split):
        """FINISHED with the result's versions, its stored parts and its trials, in one transaction fenced by the lease
        (a lost lease stores nothing). A variant the line already has keeps its first Sharpe (on conflict do nothing)."""
        parts = split['parts']
        with self.connect() as c:
            changed = c.execute(f'''UPDATE edge_bff.backtest_jobs SET state='FINISHED',engine_version=%s,registry_version=%s,
                data_version=%s,result_bytes=%s,duration_ms=%s,lease_token=NULL,lease_expires_at=NULL,finished_at=now(),
                updated_at=now() WHERE {self._FENCE} RETURNING *''',
                (split['versions']['engine_version'], split['versions']['registry_version'],
                 split['versions']['data_version'], sum(len(p) for _, p in parts), split['duration_ms'],
                 row['request_id'], row['lease_token'])).fetchone()
            if not changed:
                return None
            with c.cursor() as cur:
                cur.executemany('''INSERT INTO edge_bff.backtest_results(request_id,part,payload,bytes,sha256)
                    VALUES (%s,%s,%s,%s,%s)''',
                    [(row['request_id'], name, payload, len(payload), hashlib.sha256(payload).hexdigest())
                     for name, payload in parts])
                cur.executemany('''INSERT INTO edge_bff.backtest_trials(owner_key,lineage_key,variant_hash,sharpe_daily,
                    kind,request_id) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (owner_key,lineage_key,variant_hash) DO NOTHING''',
                    [(row['owner_key'], row['lineage_key'], h, sharpe, kind, row['request_id'])
                     for h, sharpe, kind in split['trials']])
        self._log(changed, parts=len(parts), bytes=changed['result_bytes'])
        return changed

    def prune(self, days=RESULT_DAYS):
        with self.connect() as c:
            return c.execute("DELETE FROM edge_bff.backtest_results WHERE created_at<now()-%s*interval '1 day'",
                             (days,)).rowcount


class BacktestLoop:
    """One job at a time (the worker computes one at a time): claim the oldest queued job under a lease, hand it to the
    worker with its line's prior trials, follow it every EDGE_POLL_SECONDS (progress, cancellation, timeout), store
    the finished result. Never resubmits: a job the worker lost, or a lease that expired, ends FAILED WORKER_LOST."""

    def __init__(self, settings, store, worker):
        self.settings, self.store, self.worker = settings, store, worker
        self.stopping = asyncio.Event()

    async def call(self, fn, *args):
        return await asyncio.to_thread(fn, *args)

    async def sleep(self, seconds):
        try:
            await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self):
        pruned_at, not_ready = 0, False
        while not self.stopping.is_set():
            try:
                if time.monotonic() - pruned_at > PRUNE_SECONDS:
                    await self.call(self.store.prune)
                    pruned_at = time.monotonic()
                for lost in await self.call(self.store.reap):
                    await self.cancel_quietly(lost)    # the worker may still compute it: free it for the next job
                row = await self.call(self.store.claim, self.settings.lease_seconds)
                not_ready = False
                if row:
                    await self.process(row)
                else:
                    await self.sleep(self.settings.poll_seconds)
            except StoreError as e:
                if e.code == 'BACKTEST_NOT_READY' and not not_ready:
                    logger.error('backtest_tables_missing')
                not_ready = e.code == 'BACKTEST_NOT_READY'
                await self.sleep(self.settings.poll_seconds)
            except Exception:
                # Database/client exceptions can contain credentials. No raw traceback/body in service logs.
                logger.error('backtest_queue_operation_failed')
                await self.sleep(self.settings.poll_seconds)

    async def _heartbeat(self, row, task):
        while not task.done() and not self.stopping.is_set():
            await self.sleep(self.settings.heartbeat_seconds)
            if not task.done() and not await self.call(self.store.heartbeat, row, self.settings.lease_seconds):
                task.cancel()   # fenced: the lease is gone, every later write of this follower would be refused
                return

    async def process(self, row):
        task = asyncio.create_task(self.execute(row))
        beat = asyncio.create_task(self._heartbeat(row, task))
        try:
            await task
        except asyncio.CancelledError:
            if self.stopping.is_set() or not task.cancelled():
                raise
        finally:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)

    async def cancel_quietly(self, job_id):
        try:
            return await self.call(self.worker.cancel, job_id)
        except WorkerUnavailable:
            return False

    async def known(self, job_id):
        """Whether the worker has this job (an earlier POST reached it although its answer did not reach us)."""
        code, _ = await self.call(self.worker.call, 'GET', f'/v1/jobs/{job_id}')
        return code == 200

    async def execute(self, row):
        deadline = time.monotonic() + self.settings.backtest_timeout_seconds
        if await self.dispatch(row, deadline):
            await self.follow(row, deadline)

    async def dispatch(self, row, deadline):
        """POST /v1/jobs until the worker has the job; False when the job ended here instead (cancelled before it was
        handed over, refused by the worker, timeout, or the worker unreachable WORKER_RETRIES times in a row)."""
        job_id, failures = row['request_id'], 0
        while not self.stopping.is_set():
            current = await self.call(self.store.current, row)
            if current is None:
                return False
            if current['cancel_requested']:
                await self.call(self.store.end, row, 'CANCELLED')
                return False
            if time.monotonic() >= deadline:
                await self.call(self.store.end, row, 'FAILED', {'code': 'TIMEOUT'})
                return False
            prior = await self.call(self.store.prior_trials, row['owner_key'], row['lineage_key'])
            body = {'job_id': job_id, 'request': row['request'], 'context': {'job_id': job_id, 'prior_trials': prior}}
            try:
                code, data = await self.call(self.worker.call, 'POST', '/v1/jobs', body)
                if 200 <= code < 300:
                    return True
                found = error_of(data)
                if found is None:
                    raise WorkerUnavailable()     # an answer outside the worker's API (e.g. a route it does not have)
                if code == 409 and found['code'] == 'BUSY':
                    # another job computes there; ours only when an earlier, unanswered POST reached the worker
                    if await self.known(job_id):
                        return True
                    failures = 0
                    await self.sleep(self.settings.poll_seconds)
                    continue
                # the worker refused the job (validation or data error at hand-over): its error, as it gave it
                await self.call(self.store.end, row, 'FAILED', found)
                return False
            except WorkerUnavailable:
                failures += 1
                try:
                    if await self.known(job_id):
                        return True
                except WorkerUnavailable:
                    pass
                if failures >= WORKER_RETRIES:
                    await self.call(self.store.end, row, 'FAILED', {'code': 'WORKER_LOST'})
                    return False
                await self.sleep(self.settings.poll_seconds)
        return False

    async def follow(self, row, deadline):
        """GET /v1/jobs/{id} every poll: progress while it runs, the cancellation once asked, the result when it is
        FINISHED, the worker's error or cancellation as the job's end; TIMEOUT after BACKTEST_TIMEOUT_SECONDS."""
        job_id, failures, cancel_sent, shown = row['request_id'], 0, False, row['progress']
        while not self.stopping.is_set():
            await self.sleep(self.settings.poll_seconds)
            if self.stopping.is_set():
                return
            if time.monotonic() >= deadline:
                await self.cancel_quietly(job_id)
                await self.call(self.store.end, row, 'FAILED', {'code': 'TIMEOUT'})
                return
            current = await self.call(self.store.current, row)
            if current is None:
                return
            if current['cancel_requested'] and not cancel_sent:
                cancel_sent = await self.cancel_quietly(job_id)
            try:
                code, data = await self.call(self.worker.call, 'GET', f'/v1/jobs/{job_id}')
            except WorkerUnavailable:
                code, data = None, None
            if code == 404:
                await self.call(self.store.end, row, 'FAILED', {'code': 'WORKER_LOST'})
                return
            state = data.get('state') if code == 200 and isinstance(data, dict) else None
            ended = None
            if state in ('QUEUED', 'RUNNING'):
                progress = data.get('progress') if isinstance(data.get('progress'), dict) else None
                if progress != shown:
                    if not await self.call(self.store.progress, row, progress):
                        return
                    shown = progress
                failures = 0
                continue
            reported = data.get('duration_ms') if state else None
            duration = int(reported) if isinstance(reported, (int, float)) and not isinstance(reported, bool) and reported >= 0 else None
            if state == 'FINISHED':
                ended = await self.ingest(row)
            elif state == 'FAILED':
                ended = await self.call(self.store.end, row, 'FAILED', error_of(data) or {'code': 'WORKER_FAILED'}, duration) or True
            elif state == 'CANCELLED':
                ended = await self.call(self.store.end, row, 'CANCELLED', None, duration) or True
            if ended:
                return
            failures += 1     # no answer, an answer outside the API, or a result that could not be fetched yet
            if failures >= WORKER_RETRIES:
                await self.call(self.store.end, row, 'FAILED', {'code': 'WORKER_LOST'})
                return

    async def ingest(self, row):
        """Fetch, split and store the finished result. True when the job ended (FINISHED, or FAILED RESULT_INVALID /
        WORKER_LOST), None to try again at the next poll (no answer yet)."""
        try:
            code, raw = await self.call(self.worker.result, row['request_id'])
        except WorkerUnavailable:
            return None
        if code == 404:
            await self.call(self.store.end, row, 'FAILED', {'code': 'WORKER_LOST'})
            return True
        if code != 200:
            return None
        single = row['request'].get('single') if row['request'].get('mode') == 'single' else None
        try:
            split = await self.call(lambda: split_result(loads(raw), (single or {}).get('ticker')))
        except (ValueError, TypeError, AttributeError):
            await self.call(self.store.end, row, 'FAILED', {'code': 'RESULT_INVALID'})
            return True
        if split['lineage_key'] != row['lineage_key']:
            logger.warning(json.dumps({'event': 'backtest_lineage_differs', 'request_id': row['request_id']}))
        await self.call(self.store.finish, row, split)
        return True

    def stop(self):
        self.stopping.set()


class Backtests:
    """The backtest feature of one edge-bff app: off (BACKTEST_DISABLED) while BACKTEST_WORKER_URL is empty."""

    def __init__(self, settings, store, worker=None):
        self.settings = settings
        self.store = BacktestStore(store)
        self.worker = worker or (WorkerClient(settings) if settings.backtest_worker_url else None)
        self.loop = BacktestLoop(settings, self.store, self.worker) if self.worker else None
        self.ready = False
        self.catalog = {'at': None, 'data': None}

    def close(self):
        if self.worker:
            self.worker.close()

    async def guard(self):
        if not self.worker:
            raise BacktestError(503, {'code': 'BACKTEST_DISABLED'})
        if not self.ready:
            await asyncio.to_thread(self.store.ready)    # StoreError BACKTEST_NOT_READY while the tables are missing
            self.ready = True

    async def ask(self, method, path, body=None, timeout=None):
        """One relayed worker call: 2xx -> its JSON; a 4xx with an error -> that error and status, as the worker gave
        them (validation 422, data 424, BUSY 409); anything else -> 503 BACKTEST_UNAVAILABLE."""
        try:
            code, data = await asyncio.to_thread(self.worker.call, method, path, body, timeout)
        except WorkerUnavailable:
            raise BacktestError(503, {'code': 'BACKTEST_UNAVAILABLE'})
        if 200 <= code < 300:
            return data
        found = error_of(data)
        if 400 <= code < 500 and found:
            raise BacktestError(code, found)
        raise BacktestError(503, {'code': 'BACKTEST_UNAVAILABLE'})

    @staticmethod
    async def json_object(request):
        try:
            body = loads(await request.body() or b'null')
        except ValueError:
            raise BacktestError(422, {'code': 'INVALID_INPUT'})
        if not isinstance(body, dict):
            raise BacktestError(422, {'code': 'INVALID_INPUT'})
        return body

    def routes(self, app, session, write):
        settings, owner = self.settings, self.settings.owner

        @app.exception_handler(BacktestError)
        async def backtest_error(_, exc):
            return JSONResponse(status_code=exc.status, content={'error': exc.error})

        @app.get('/api/v1/backtests/catalog')
        async def catalog(_=Depends(session)):
            """The worker's Catalog, kept CATALOG_CACHE_SECONDS; while the worker cannot answer the last one is kept."""
            await self.guard()
            now = time.monotonic()
            if self.catalog['data'] is None or now - self.catalog['at'] >= CATALOG_CACHE_SECONDS:
                try:
                    data = await self.ask('GET', '/v1/catalog')
                except BacktestError:
                    if self.catalog['data'] is None:
                        raise
                else:
                    self.catalog.update(at=now, data=data)
            return JSONResponse(self.catalog['data'])

        @app.post('/api/v1/backtests/signals')
        async def signals(request: Request, _=Depends(write)):
            """SignalsPreview of a universe before a run (no job, no trial), computed by the worker while we wait."""
            await self.guard()
            body = await self.json_object(request)
            return JSONResponse(await self.ask('POST', '/v1/signals', body, settings.backtest_timeout_seconds))

        @app.post('/api/v1/backtests', status_code=202)
        async def submit(request: Request, _=Depends(write)):
            """202 {request_id}: the request checked by the worker (its 422 relayed as it is) and queued; the same
            client_request_id returns the same job."""
            await self.guard()
            body = await self.json_object(request)
            key = body.pop('client_request_id', None)
            if key is None:
                key = 'auto:' + secrets.token_hex(16)
            elif not isinstance(key, str) or not SUBMISSION.fullmatch(key):
                raise BacktestError(422, {'code': 'INVALID_INPUT', 'field': 'client_request_id'})
            row = await asyncio.to_thread(self.store.find, owner, key)
            created = False
            if row is None:
                checked = await self.ask('POST', '/v1/validate', {'request': body})
                checked = checked if isinstance(checked, dict) and checked.get('ok') is True else {}
                lineage, variant = checked.get('lineage_key'), checked.get('variant_hash')
                if not all(isinstance(h, str) and HEX64.fullmatch(h) for h in (lineage, variant)):
                    raise BacktestError(503, {'code': 'BACKTEST_UNAVAILABLE'})   # an answer outside the worker's API
                row, created = await asyncio.to_thread(self.store.submit, owner, key, body, lineage, variant,
                                                       settings.backtest_queued_per_owner)
            elif row['request'] != body:
                raise StoreError('SUBMISSION_CONFLICT')
            return JSONResponse(status_code=202, content={'request_id': row['request_id'], 'state': row['state'],
                                                          'created': created})

        @app.get('/api/v1/backtests')
        async def latest(limit: int = Query(default=30, ge=1, le=100), _=Depends(session)):
            """The owner's latest jobs, newest first: each JobStatus with the request it ran."""
            await self.guard()
            rows = await asyncio.to_thread(self.store.jobs, owner, limit)
            return {'items': [{**status_of(r), 'request': r['request']} for r in rows]}

        @app.get('/api/v1/backtests/{request_id}')
        async def status(request_id: str, _=Depends(session)):
            await self.guard()
            return status_of(await asyncio.to_thread(self.store.job, owner, request_id))

        async def finished(request_id):
            row = await asyncio.to_thread(self.store.job, owner, request_id)
            if row['state'] != 'FINISHED':
                raise BacktestError(409, {'code': 'NOT_FINISHED'})
            return row

        @app.get('/api/v1/backtests/{request_id}/result')
        async def result(request_id: str, request: Request, _=Depends(session)):
            """The core part; in single mode with the ticker's events part merged back into events, so the page gets
            the worker's BacktestResult as it was. 410 RESULT_EXPIRED after the 30 days."""
            await self.guard()
            row = await finished(request_id)
            core = await asyncio.to_thread(self.store.part, request_id, 'core')
            if core is None:
                raise BacktestError(410, {'code': 'RESULT_EXPIRED'})
            req = row['request']
            if req.get('mode') == 'single':
                events = await asyncio.to_thread(self.store.part, request_id, f"events:{req['single']['ticker']}")
                if events is None:
                    raise BacktestError(410, {'code': 'RESULT_EXPIRED'})
                def merge():
                    whole, ticker = loads(gzip.decompress(core)), loads(gzip.decompress(events))
                    whole['events'] = {**whole['events'], 'conditions': ticker['conditions'], 'exits': ticker['exits']}
                    return packed(whole)
                core = await asyncio.to_thread(merge)
            return json_part(request, core)

        @app.get('/api/v1/backtests/{request_id}/events')
        async def events(request_id: str, request: Request, ticker: str = Query(pattern=r'^[A-Z0-9]{1,12}$'),
                         _=Depends(session)):
            """{conditions, exits} of one ticker of a finished run (the part events:<ticker>)."""
            await self.guard()
            await finished(request_id)
            payload = await asyncio.to_thread(self.store.part, request_id, f'events:{ticker}')
            if payload is None:
                if not await asyncio.to_thread(self.store.has, request_id, 'core'):
                    raise BacktestError(410, {'code': 'RESULT_EXPIRED'})
                raise BacktestError(404, {'code': 'EVENTS_NOT_FOUND', 'field': 'ticker'})
            return json_part(request, payload)

        @app.post('/api/v1/backtests/{request_id}/cancel')
        async def cancel(request_id: str, _=Depends(write)):
            """202 with the job: a queued job is CANCELLED at once, a running one is stopped at the worker by the loop.
            409 NOT_RUNNING when it had already ended."""
            await self.guard()
            row = await asyncio.to_thread(self.store.cancel, owner, request_id)
            if row is None:
                raise BacktestError(409, {'code': 'NOT_RUNNING'})
            return JSONResponse(status_code=202, content=status_of(row))
