"""One managed queue worker (the AI job loop) and the hourly housekeeping. HTTP waits execute in threads, not the SSE
event loop."""
import asyncio
import json
import logging
import time
from .client import OrcError
from .errors import Refusal
from .monitor import ModelCatalog, run_refusal
from .principal import owner_principal
from .store import PURGE_BATCH, PURGES

MONITOR_CHAT = 'monitor.chat'   # main.py MONITOR_CHAT: the capability a run needs (CONTRACT.md 8b, decision D5)

logger = logging.getLogger('edge_bff.worker')


def router_title(response):
    """EXEC-UI-1012 C: the short title Orc's first-message router wrote (only a conversation's first question has
    one), folded to one line and at most 80 characters; None when absent."""
    router = ((response or {}).get('mode4') or {}).get('router') or {}
    title = ' '.join(str(router.get('title') or '').split())[:80]
    return title or None


class Worker:
    def __init__(self, settings, store, orc, models=None):
        self.settings, self.store, self.orc = settings, store, orc
        self.models = models or ModelCatalog(orc)
        # EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b): owner key -> its principal now (main.py sets the app's
        # Auth.owner_principal; on its own, as a test builds it, the switch-off mapping)
        self.access = lambda owner: owner_principal(settings, None, owner)
        # EXEC-MU-ACCOUNTS beta/live: the claim of the next queued run (main.py sets the app's, which claims only this
        # site's runs, store.claim(seconds, site); on its own, as a test builds it, the store's own claim)
        self.claim = lambda seconds: self.store.claim(seconds)
        self.stopping = asyncio.Event()

    async def call(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def sleep(self, seconds):
        try:
            await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self):
        # ERRORS R2-33: the hourly purges are no longer made here (Housekeeping, its own task): a purge that fails can
        # never stop the claim of the queued runs
        while not self.stopping.is_set():
            try:
                row = await self.call(self.claim, self.settings.lease_seconds)
                if row:
                    await self.process(row)
                else:
                    await self.sleep(self.settings.poll_seconds)
            except Exception:
                # Database/client exceptions can contain credentials. No raw traceback/body in service logs.
                logger.error('queue_operation_failed')
                await self.sleep(self.settings.poll_seconds)

    async def _heartbeat(self, row, task):
        while not task.done() and not self.stopping.is_set():
            await self.sleep(self.settings.heartbeat_seconds)
            if not task.done() and not await self.call(self.store.heartbeat, row['request_id'], row['lease_token'], self.settings.lease_seconds):
                task.cancel()  # Fence this delivery; a dispatched Orc run may still finish remotely.
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

    async def refused(self, row):
        """Phase 3a (CONTRACT.md 8b, decision D5): before a run is sent to Orc, its owner must still hold monitor.chat
        and the run's model (app/monitor.py); a plan lowered while the run waited ends it FAILED CAPABILITY_REQUIRED
        (or PLAN_EXPIRED) with no Orc run. True when the run was ended here. With the switch off the configured owner
        holds '*' (EDGE_ADMIN_OWNERS, default the one owner), so nothing changes for it."""
        p = await self.call(self.access, row['owner_key'])
        refusal = None if p.can(MONITOR_CHAT) else p.refusal(MONITOR_CHAT)
        if refusal is None:
            # OrcError when the default model cannot be read now: the run is RECOVERING and checked again
            refusal = await run_refusal(p, (row['input'] or {}).get('model'), self.models)
        if refusal is None:
            return False
        code = refusal.code if isinstance(refusal, Refusal) else 'CAPABILITY_REQUIRED'
        logger.info('job_refused_at_dispatch')
        await self.call(self.store.transition, row, 'FAILED', error_code=code)
        return True

    async def execute(self, row):
        if not row['attempt_count']:
            # never dispatched: checked before any Orc call (a recovered run is checked before it is sent again, below)
            try:
                if await self.refused(row):
                    return
            except OrcError:
                pass                                    # the loop below reaches the same check and its recovery
        deadline = time.monotonic() + self.settings.orc_timeout_seconds + self.settings.lease_seconds
        failures = 0
        while not self.stopping.is_set():
            try:
                found = await self.call(self.orc.request, row['owner_key'], row['request_id'])
                if found:
                    conv = found['conversation_id']
                    if found['turn_status'] == 'COMPLETED':
                        if found.get('response'):
                            await self.call(self.store.transition, row, 'FINISHED', conversation_id=conv,
                                            run_status=found.get('run_status'), title=router_title(found.get('response')))
                        else:
                            await self.call(self.store.transition, row, 'FAILED', conversation_id=conv, error_code='RESULT_NOT_SAVED')
                        return
                    if found['turn_status'] in ('FAILED', 'INTERRUPTED'):
                        await self.call(self.store.transition, row, found['turn_status'], conversation_id=conv,
                                        run_status=found.get('run_status'), error_code='ORC_RUN_INTERRUPTED')
                        return
                    if conv != row.get('conversation_id') or row['state'] != 'RUNNING':
                        updated = await self.call(self.store.transition, row, 'RUNNING', conversation_id=conv)
                        if not updated:
                            return
                        row = updated
                    # Already executing: never POST again while Orc reports RUNNING.
                    await self.sleep(self.settings.poll_seconds)
                else:
                    # Ambiguous first dispatch: two bounded missing reads before replaying the SAME payload/id.
                    if row['attempt_count'] and failures < 2:
                        failures += 1
                        await self.sleep(self.settings.poll_seconds)
                        continue
                    if row['attempt_count'] >= 3:
                        await self.call(self.store.transition, row, 'INTERRUPTED', error_code='DISPATCH_UNCERTAIN')
                        return
                    current = await self.call(self.store.job, row['owner_key'], row['request_id'])
                    if (current['input'] or {}).get('stop_requested'):
                        # EXEC-Y Fase 1: stopped before it reached Orc; nothing is dispatched
                        await self.call(self.store.transition, row, 'FAILED', error_code='STOPPED_BY_USER')
                        return
                    if await self.refused(row):
                        return
                    if not await self.call(self.orc.execution_ready, row['owner_key']):
                        # No dispatch took place. Waiting cannot exhaust the three
                        # ambiguous-POST attempts or spend provider tokens.
                        raise OrcError('SERVICES_INITIALIZING')
                    current = await self.call(self.store.job, row['owner_key'], row['request_id'])
                    if (current['input'] or {}).get('stop_requested'):
                        await self.call(self.store.transition, row, 'FAILED', error_code='STOPPED_BY_USER')
                        return
                    if time.monotonic() >= deadline:
                        await self.call(self.store.transition, row, 'INTERRUPTED', error_code='RECOVERY_TIMEOUT')
                        return
                    if not await self.call(self.store.attempted, row):
                        return
                    row['attempt_count'] += 1
                    result = await self.call(self.orc.run, row['owner_key'], row['request_id'], row['input'])
                    if not result or result.get('conversation', {}).get('persistence') != 'SAVED':
                        await self.call(self.store.transition, row, 'FAILED', error_code='RESULT_NOT_SAVED')
                        return
                    await self.call(self.store.transition, row, 'FINISHED',
                                    conversation_id=result['conversation']['conversation_id'], run_status=result['status'],
                                    title=router_title(result))
                    return
            except OrcError as error:
                # 409 can mean existing active execution after an idempotent recovery replay.
                if error.status in (400, 422):
                    await self.call(self.store.transition, row, 'FAILED', error_code=error.code)
                    return
                await self.call(self.store.transition, row, 'RECOVERING', error_code=(
                    'SERVICES_INITIALIZING' if error.code == 'SERVICES_INITIALIZING' else 'ORC_RECOVERING'))
                await self.sleep(self.settings.poll_seconds)
            if time.monotonic() >= deadline:
                # End the delivery attempt honestly; do not imply upstream cancellation.
                await self.call(self.store.transition, row, 'INTERRUPTED', error_code='RECOVERY_TIMEOUT')
                return

    def stop(self):
        self.stopping.set()


class Housekeeping:
    """The hourly housekeeping (EXEC-MU-ACCOUNTS; ERRORS R2-33), its own task beside the loops (main.py; switch
    EDGE_HOUSEKEEPING_ENABLED): each purge of store.PURGES (expired and old revoked sessions, throttle rows older than 2
    days, registrations never verified after 24 h, the outbox rows of an address with no account after 24 h, and every
    outbox row, used email code and webhook delivery after 30 days) runs at the start, whatever the clock reads, then
    once an hour.

    - Each purge is tried on its own (store.purge: its own transaction, batches of store.PURGE_BATCH rows, at most
      MAX_BATCHES a turn), so a failing one (a timeout, a lock wait, a grant a migration left out) stops neither the
      others nor any queue; it is tried again after a backoff that doubles from EDGE_POLL_SECONDS up to the hour, and
      each failure is logged by its class (housekeeping_failed).
    - A batch another instance holds (the other website, running the same purge) is skipped until the next turn.
    """

    EVERY_SECONDS = 3600
    MAX_BATCHES = 20

    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.stopping = asyncio.Event()
        # name -> (next attempt on time.monotonic(), failures in a row); None: due now (never 0, see run)
        self.due = {}

    async def sleep(self, seconds):
        try:
            await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def turn(self, name):
        """One purge to its end (or MAX_BATCHES batches); True when it was made, False when another instance held it."""
        for _ in range(self.MAX_BATCHES):
            done = await asyncio.to_thread(self.store.purge, name, PURGE_BATCH)
            if done is None:
                return False
            if done < PURGE_BATCH:
                break
        return True

    async def run(self):
        while not self.stopping.is_set():
            for name in PURGES:
                if self.stopping.is_set():
                    return
                # None: not purged yet, so at the start. Never 0: time.monotonic() counts from an unspecified point (on
                # Linux the host's boot), so on a host up for less than an hour a 0 would skip the start's purge.
                at, failures = self.due.get(name, (None, 0))
                if at is not None and time.monotonic() < at:
                    continue
                try:
                    await self.turn(name)
                    self.due[name] = (time.monotonic() + self.EVERY_SECONDS, 0)
                except Exception as e:                     # noqa: BLE001 - its class only (no secret in the log)
                    failures += 1
                    wait = min(self.EVERY_SECONDS, self.settings.poll_seconds * 2 ** failures)
                    self.due[name] = (time.monotonic() + wait, failures)
                    logger.error(json.dumps({'event': 'housekeeping_failed', 'purge': name,
                                             'error': type(e).__name__, 'failures': failures, 'retry_s': round(wait, 3)}))
            # the due times are looked at every EDGE_POLL_SECONDS (no database call unless one is due)
            await self.sleep(self.settings.poll_seconds)

    def stop(self):
        self.stopping.set()
