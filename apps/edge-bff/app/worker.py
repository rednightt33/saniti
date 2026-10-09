"""One managed queue worker. HTTP waits execute in threads, not the SSE event loop."""
import asyncio
import logging
import time
from .client import OrcError

logger = logging.getLogger('edge_bff.worker')


class Worker:
    def __init__(self, settings, store, orc):
        self.settings, self.store, self.orc = settings, store, orc
        self.stopping = asyncio.Event()

    async def call(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def sleep(self, seconds):
        try:
            await asyncio.wait_for(self.stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def run(self):
        cleaned_at = 0
        while not self.stopping.is_set():
            try:
                if time.monotonic() - cleaned_at > 3600:
                    await self.call(self.store.cleanup_sessions)
                    cleaned_at = time.monotonic()
                row = await self.call(self.store.claim, self.settings.lease_seconds)
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

    async def execute(self, row):
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
                                            run_status=found.get('run_status'))
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
                    if not await self.call(self.store.attempted, row):
                        return
                    row['attempt_count'] += 1
                    result = await self.call(self.orc.run, row['owner_key'], row['request_id'], row['input'])
                    if not result or result.get('conversation', {}).get('persistence') != 'SAVED':
                        await self.call(self.store.transition, row, 'FAILED', error_code='RESULT_NOT_SAVED')
                        return
                    await self.call(self.store.transition, row, 'FINISHED',
                                    conversation_id=result['conversation']['conversation_id'], run_status=result['status'])
                    return
            except OrcError as error:
                # 409 can mean existing active execution after an idempotent recovery replay.
                if error.status in (400, 422):
                    await self.call(self.store.transition, row, 'FAILED', error_code=error.code)
                    return
                await self.call(self.store.transition, row, 'RECOVERING', error_code='ORC_RECOVERING')
                await self.sleep(self.settings.poll_seconds)
            if time.monotonic() >= deadline:
                # End the delivery attempt honestly; do not imply upstream cancellation.
                await self.call(self.store.transition, row, 'INTERRUPTED', error_code='RECOVERY_TIMEOUT')
                return

    def stop(self):
        self.stopping.set()
