"""stockbit-updater (EXEC-STOCKBIT-UPDATER, user go 2026-10-25): one round per deployment.

The user replaces the Railway variable STOCKBIT_TOKEN and deploys (decision K2 A); this process then
1. checks the token's expiry (the JWT `exp`, never printed),
2. loads the IDX_Broker_Summary dates the data says are missing (broker_import.py),
3. refreshes Feature 05 -> 02 -> 03, 05 -> 06 and the INDEX tables for every date that changed (refresh.py),
4. reloads the Stockbit corporate actions, insider movements and idx_event_annotation (K4,
   apps/stockbit-event-annotation/job.py, its own full pull and reconciliation),
4b. reloads the stock groups and indices the user chose (stock_lists.py, EXEC-STOCK-CATALOG); a failure of this step is
   a warning in the stock_lists column, the round stays SUCCESS (decision D2),
5. refreshes Database_Table_Status and records the round in Monitoring_Stockbit_Update, then asks telegram-monitor
   to send the summary (K5),
and exits. Restart policy NEVER: a failed round is not retried with the same token.

UPDATER_MODE=VERIFY with UPDATER_VERIFY_DATE fetches one stored date and compares it with the table, writing nothing
but the monitoring row. A secret is never printed.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg.types.json import Jsonb

sys.path[:0] = ['/app/updater', '/app/scripts']
import broker_import  # noqa: E402
import refresh  # noqa: E402
import stock_lists  # noqa: E402

MONITOR = 'public."Monitoring_Stockbit_Update"'
EVENTS_JOB = Path('/app/events/job.py')
# ERRORS M413: a RUNNING row is a claim that a round is working; terminal-publisher waits while one is fresh. The round
# stamps updated_at every HEARTBEAT_SECONDS from a connection of its own (the steps run up to an hour between their own
# records), so a round whose process died stops stamping and its row goes stale within minutes. The end of a round is
# written on a new connection when the round's own died (Postgres restarted or killed for memory), retried while
# Postgres recovers, and telegram-monitor is always asked to send the summary.
HEARTBEAT_SECONDS = 60
HEARTBEAT_SQL = f"UPDATE {MONITOR} SET updated_at = now() WHERE execution_id = %s AND status = 'RUNNING'"
FINISH_WAITS = (10, 20, 40, 60, 60, 60)


class Stopped(Exception):
    """SIGTERM: Railway stops the deployment (a redeploy, a removal, a usage limit)."""


def emit(event: str, **fields) -> None:
    print(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'event': event, **fields}, default=str),
          flush=True)


def token_expiry(token: str) -> datetime:
    token = token.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError('STOCKBIT_TOKEN is not a JWT')
    payload = parts[1] + '=' * (-len(parts[1]) % 4)
    return datetime.fromtimestamp(json.loads(base64.urlsafe_b64decode(payload))['exp'], timezone.utc)


def record(pg, execution_id: str, **fields) -> None:
    sets = ', '.join(f'{k} = %({k})s' for k in fields)
    pg.execute(f'UPDATE {MONITOR} SET {sets}, updated_at = now() WHERE execution_id = %(id)s',
               {**{k: Jsonb(v) if isinstance(v, (dict, list)) else v for k, v in fields.items()}, 'id': execution_id})


def connect(purpose: str = 'stockbit-updater', timeout_ms: int = 900000):
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=30, application_name=purpose,
                           options=f'-c statement_timeout={timeout_ms}')


class Heartbeat:
    """Stamps the RUNNING row's updated_at every `every` seconds while the round lives (ERRORS M413). Its own
    connection, opened again after a failure, so a Postgres restart costs at most a few missed beats."""

    def __init__(self, execution_id: str, open_conn, every: float = HEARTBEAT_SECONDS):
        self.execution_id, self.open_conn, self.every = execution_id, open_conn, every
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name='heartbeat', daemon=True)

    def start(self) -> 'Heartbeat':
        self.thread.start()
        return self

    def stop(self) -> None:
        self.done.set()
        self.thread.join(timeout=10)

    def _run(self) -> None:
        conn = None
        while not self.done.wait(self.every):
            try:
                if conn is None or conn.closed:
                    conn = self.open_conn()
                conn.execute(HEARTBEAT_SQL, (self.execution_id,))
            except Exception as exc:  # noqa: BLE001 - a missed beat is logged; the next one reconnects
                emit('heartbeat_failed', error=type(exc).__name__)
                conn = _close(conn)
        _close(conn)


def _close(conn) -> None:
    try:
        if conn is not None:
            conn.close()
    except Exception:  # noqa: BLE001 - closing a dead connection
        pass


def finish(pg, execution_id: str, open_conn, sleep=time.sleep, **fields) -> bool:
    """Writes the round's end. When the round's connection is dead, on a new one, retried over FINISH_WAITS while
    Postgres recovers (ERRORS M413). False when every try failed; the caller still notifies."""
    try:
        record(pg, execution_id, **fields)
        return True
    except Exception as exc:  # noqa: BLE001
        emit('finish_retry', attempt=0, error=type(exc).__name__)
    for attempt, wait in enumerate(FINISH_WAITS, 1):
        try:
            conn = open_conn()
            try:
                record(conn, execution_id, **fields)
            finally:
                _close(conn)
            return True
        except Exception as exc:  # noqa: BLE001
            emit('finish_retry', attempt=attempt, error=type(exc).__name__)
            sleep(wait)
    return False


def _on_sigterm(signum, frame):
    raise Stopped('Round dihentikan: Railway menghentikan deployment (redeploy, dihapus atau batas pemakaian)')


def run_events(token: str) -> dict:
    """The event loader's own job (full pull + reconcile + refresh_idx_event_annotation, one transaction)."""
    with tempfile.TemporaryDirectory() as work:
        Path(work, 'params.json').write_text(json.dumps({'mode': 'APPLY'}))
        env = {**os.environ, 'STOCKBIT_TOKEN': token, 'PYTHONPATH': '/app/events'}
        proc = subprocess.run([sys.executable, '-u', str(EVENTS_JOB)], cwd=work, env=env, capture_output=True,
                              text=True, timeout=3 * 3600)
    keep = {}
    for line in proc.stdout.splitlines():
        if line.startswith(('OUT ', 'ERR ')):
            print(line, flush=True)
            item = json.loads(line[4:])
            if item.get('q') in ('reconcile_corporate_action', 'reconcile_insider', 'refresh_annotation', 'committed'):
                keep[item['q']] = {k: v for k, v in item.items() if k != 'q'}
            if line.startswith('ERR '):
                keep.setdefault('errors', []).append(item)
    if proc.returncode != 0 or 'committed' not in keep:
        tail = (proc.stderr or '')[-1500:]
        raise RuntimeError(f'Event load failed (exit {proc.returncode}): {keep.get("errors") or tail}')
    return keep


def refresh_table_status() -> int:
    import sync_database_schema as s
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        s.ensure_status_table(db, 'public')
        names = s.table_names(db, 'public')
        s.refresh_status(db, 'public', names, datetime.now(timezone.utc).replace(microsecond=0))
        db.commit()
    return len(names)


def notify(execution_id: str) -> None:
    url, secret = os.environ.get('TELEGRAM_NOTIFY_URL', '').strip(), os.environ.get('TELEGRAM_NOTIFY_SECRET', '').strip()
    if not url or not secret:
        emit('telegram_notify_skipped', reason='not_configured')
        return
    body = json.dumps({'source_table': 'Monitoring_Stockbit_Update', 'execution_id': execution_id}).encode()
    for attempt in range(1, 5):
        try:
            req = Request(url, data=body, method='POST',
                          headers={'Content-Type': 'application/json', 'X-Notify-Secret': secret})
            with urlopen(req, timeout=20) as resp:
                emit('telegram_notify_accepted', attempt=attempt, status=resp.status)
                return
        except HTTPError as exc:
            emit('telegram_notify_failed', attempt=attempt, status=exc.code)
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                return
        except (URLError, TimeoutError, OSError) as exc:
            emit('telegram_notify_failed', attempt=attempt, error=type(exc).__name__)
        time.sleep(2 ** attempt)


def main() -> int:
    mode = os.environ.get('UPDATER_MODE', 'APPLY').upper()
    verify_date = os.environ.get('UPDATER_VERIFY_DATE', '').strip() or None
    state = Path(os.environ.get('STATE_DIR', '/data'))
    retention = int(os.environ.get('RAW_RETENTION_DAYS', '3'))
    workers = int(os.environ.get('UPDATER_WORKERS', '6'))
    token = os.environ.get('STOCKBIT_TOKEN', '')
    execution_id = str(uuid.uuid4())
    pg = connect()
    pg.execute(f"""INSERT INTO {MONITOR} (execution_id, mode, status, started_at, deployment_id)
                   VALUES (%s, %s, 'RUNNING', now(), %s)""",
               (execution_id, mode, os.environ.get('RAILWAY_DEPLOYMENT_ID')))
    emit('round_started', execution_id=execution_id, mode=mode)
    signal.signal(signal.SIGTERM, _on_sigterm)
    beat = Heartbeat(execution_id, lambda: connect('stockbit-updater-heartbeat', 30000)).start()
    status, error, steps = 'SUCCESS', None, {}
    try:
        expires = token_expiry(token)
        record(pg, execution_id, token_expires_at=expires)
        if expires <= datetime.now(timezone.utc):
            raise RuntimeError(f'Token Stockbit kedaluwarsa sejak {expires:%Y-%m-%d %H:%M} UTC; ganti STOCKBIT_TOKEN lalu Deploy')
        loader = broker_import.BrokerImport(pg, token, state, workers, emit, retention)
        if mode == 'VERIFY':
            if not verify_date:
                raise ValueError('UPDATER_MODE=VERIFY needs UPDATER_VERIFY_DATE')
            steps['broker'] = loader.run(verify_date)
            v = steps['broker']['verify']
            if v['missing_in_fetch'] or v['new_in_fetch'] or v['different']:
                status = 'FAILED'
                error = 'VERIFY: data Stockbit berbeda dengan tabel'
            record(pg, execution_id, broker=steps['broker'])
        else:
            steps['broker'] = loader.run()
            record(pg, execution_id, broker=steps['broker'], broker_dates=steps['broker']['dates'],
                   broker_rows=steps['broker']['rows'])
            steps['features'] = refresh.refresh_broker_features(emit)
            record(pg, execution_id, features=steps['features'])
            if refresh.index_needed(bool(steps['features']['changed_dates'])):
                steps['index'] = refresh.refresh_index(emit)
            else:
                steps['index'] = {'skipped': 'no changed broker date and no newer IHSG price'}
            record(pg, execution_id, index_result=steps['index'])
            steps['events'] = run_events(token)
            record(pg, execution_id, events=steps['events'])
            steps['stock_lists'] = stock_lists.run(pg, token, execution_id, emit)
            record(pg, execution_id, stock_lists=steps['stock_lists'])
            steps['table_status'] = {'tables': refresh_table_status()}
    except Exception as exc:  # noqa: BLE001 - every failure ends the round with a recorded, notified status
        status, error = 'FAILED', f'{type(exc).__name__}: {exc}'[:2000]
        emit('round_failed', error=error, trace=traceback.format_exc()[-3000:])
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)     # the end is written and sent before Railway's SIGKILL
        beat.stop()
    try:
        recorded = finish(pg, execution_id, lambda: connect('stockbit-updater', 30000), status=status,
                          last_error=error, finished_at=datetime.now(timezone.utc))
        emit('round_finished', execution_id=execution_id, status=status, steps=list(steps), recorded=recorded)
    finally:
        _close(pg)
        notify(execution_id)
    return 0 if status == 'SUCCESS' else 1


if __name__ == '__main__':
    sys.exit(main())
