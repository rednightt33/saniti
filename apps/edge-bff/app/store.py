import hashlib
import json
import secrets
import logging
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

TERMINAL = {'FINISHED', 'FAILED', 'INTERRUPTED'}
logger = logging.getLogger('edge_bff.lifecycle')


class StoreError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class Store:
    def __init__(self, url):
        self.url = url

    @contextmanager
    def connect(self):
        with psycopg.connect(self.url, connect_timeout=5, row_factory=dict_row) as c:
            c.execute("SET LOCAL statement_timeout = '5s'")
            yield c

    def ready(self):
        with self.connect() as c:
            c.execute('SELECT 1 FROM edge_bff.jobs LIMIT 0')
            c.execute('SELECT 1 FROM edge_bff.sessions LIMIT 0')
            c.execute('SELECT 1 FROM edge_bff.conversation_ui LIMIT 0')

    def session_create(self, hashed, owner, seconds):
        with self.connect() as c:
            c.execute('INSERT INTO edge_bff.sessions(token_hash,owner_key,expires_at) VALUES (%s,%s,now()+%s*interval \'1 second\')', (hashed, owner, seconds))

    def session(self, hashed):
        with self.connect() as c:
            return c.execute('SELECT owner_key FROM edge_bff.sessions WHERE token_hash=%s AND revoked_at IS NULL AND expires_at>now()', (hashed,)).fetchone()

    def revoke(self, hashed):
        with self.connect() as c:
            c.execute('UPDATE edge_bff.sessions SET revoked_at=now() WHERE token_hash=%s', (hashed,))

    def submit(self, owner, key, payload, after_stop=False):
        """A new job. EXEC-Y Fase 1 (S3): sent with after_stop while a run is active, the message waits inside that
        run (input.next) and becomes its own job, in the same conversation, the moment that run ends (_promote); the
        run is marked to stop. One active job per owner stays a database rule; one waiting message per run."""
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (owner,))
            row = c.execute('SELECT * FROM edge_bff.jobs WHERE owner_key=%s AND submission_key=%s', (owner, key)).fetchone()
            waiting = c.execute("""SELECT * FROM edge_bff.jobs WHERE owner_key=%s AND input->'next'->>'submission_key'=%s""",
                                (owner, key)).fetchone()
            if row or waiting:
                if (row or waiting['input']['next'])['fingerprint'] != fingerprint:
                    raise StoreError('SUBMISSION_CONFLICT')
                return (row or self._waiting(waiting)), False
            active = c.execute("SELECT * FROM edge_bff.jobs WHERE owner_key=%s AND state IN ('QUEUED','RUNNING','RECOVERING')", (owner,)).fetchone()
            if active and (not after_stop or (active['input'] or {}).get('next')):
                raise StoreError('RUN_IN_PROGRESS')
            request_id = 'edge_'+secrets.token_hex(16)
            if active:
                job_input = {**payload, 'after_request_id': active['request_id']}
                nxt = {'request_id': request_id, 'submission_key': key, 'fingerprint': fingerprint, 'input': job_input}
                active = c.execute("""UPDATE edge_bff.jobs SET input=input||jsonb_build_object('stop_requested',true,'next',%s::jsonb)
                    WHERE request_id=%s RETURNING *""", (json.dumps(nxt), active['request_id'])).fetchone()
                return self._waiting(active), True
            row = c.execute('''INSERT INTO edge_bff.jobs(request_id,owner_key,submission_key,fingerprint,input,conversation_id)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING *''',
                (request_id, owner, key, fingerprint, Jsonb(payload), payload.get('conversation_id'))).fetchone()
            return row, True

    @staticmethod
    def _waiting(holder):
        """The message waiting inside an active run, read like a job (QUEUED; FAILED once it was stopped)."""
        nxt = holder['input']['next']
        stopped = bool(nxt.get('stopped'))
        return {'request_id': nxt['request_id'], 'owner_key': holder['owner_key'], 'input': nxt['input'],
                'conversation_id': nxt['input'].get('conversation_id') or holder['conversation_id'],
                'state': 'FAILED' if stopped else 'QUEUED', 'state_version': 0, 'run_status': None,
                'error_code': 'STOPPED_BY_USER' if stopped else None, 'created_at': holder['updated_at'],
                'updated_at': holder['updated_at'], 'completed_at': holder['updated_at'] if stopped else None,
                'attempt_count': 0, 'lease_token': None}

    def _promote(self, c, ended):
        """The waiting message of a run that just ended becomes its own job, in the run's conversation."""
        nxt = (ended['input'] or {}).get('next')
        if not nxt:
            return
        job_input = dict(nxt['input'])
        if not job_input.get('conversation_id') and ended['conversation_id']:
            job_input['conversation_id'] = ended['conversation_id']
        stopped = bool(nxt.get('stopped'))
        c.execute('''INSERT INTO edge_bff.jobs(request_id,owner_key,submission_key,fingerprint,input,conversation_id,
                state,error_code,completed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() END) ON CONFLICT DO NOTHING''',
            (nxt['request_id'], ended['owner_key'], nxt['submission_key'], nxt['fingerprint'], Jsonb(job_input),
             job_input.get('conversation_id'), 'FAILED' if stopped else 'QUEUED',
             'STOPPED_BY_USER' if stopped else None, stopped))

    def job(self, owner, request_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM edge_bff.jobs WHERE owner_key=%s AND request_id=%s', (owner, request_id)).fetchone()
            if not row:
                holder = c.execute("SELECT * FROM edge_bff.jobs WHERE owner_key=%s AND input->'next'->>'request_id'=%s",
                                   (owner, request_id)).fetchone()
                if holder:
                    return self._waiting(holder)
                raise StoreError('RUN_NOT_FOUND', 404)
            return row

    def stop_queued(self, owner, request_id):
        """The stop button on a run no worker has claimed: it ends here and never reaches Orc. None when a worker
        claimed it first (the row lock orders this against claim), so the caller stops it at Orc instead. A message
        waiting inside a run (S3) is marked stopped and becomes a stopped job when that run ends."""
        with self.connect() as c:
            changed = c.execute('''UPDATE edge_bff.jobs SET state='FAILED',error_code='STOPPED_BY_USER',
                state_version=state_version+1,updated_at=now(),completed_at=now()
                WHERE owner_key=%s AND request_id=%s AND state='QUEUED' AND lease_token IS NULL RETURNING *''',
                (owner, request_id)).fetchone()
            if changed:
                self._promote(c, changed)
                logger.info(json.dumps({'event':'job_state', 'request_id':changed['request_id'],
                                        'state':changed['state'], 'version':changed['state_version']}))
                return changed
            holder = c.execute("""UPDATE edge_bff.jobs SET input=jsonb_set(input,'{next,stopped}','true'::jsonb)
                WHERE owner_key=%s AND input->'next'->>'request_id'=%s AND state IN ('QUEUED','RUNNING','RECOVERING')
                RETURNING *""", (owner, request_id)).fetchone()
            return self._waiting(holder) if holder else None

    def claim(self, seconds):
        with self.connect() as c:
            row = c.execute('''SELECT * FROM edge_bff.jobs WHERE state IN ('QUEUED','RUNNING','RECOVERING')
                AND (lease_expires_at IS NULL OR lease_expires_at<now()) ORDER BY created_at
                FOR UPDATE SKIP LOCKED LIMIT 1''').fetchone()
            if not row:
                return None
            token = secrets.token_hex(16)
            return c.execute('''UPDATE edge_bff.jobs SET lease_token=%s,lease_expires_at=now()+%s*interval '1 second',
                state=CASE WHEN attempt_count=0 THEN 'RUNNING' ELSE 'RECOVERING' END,
                state_version=state_version+1,updated_at=now() WHERE request_id=%s RETURNING *''',
                (token, seconds, row['request_id'])).fetchone()

    def active(self, owner):
        with self.connect() as c:
            return c.execute("SELECT request_id FROM edge_bff.jobs WHERE owner_key=%s AND state IN ('QUEUED','RUNNING','RECOVERING')", (owner,)).fetchone()

    def request_stop(self, owner, request_id):
        """Mark a queued or running job to stop (the worker never dispatches a marked job); the job, or None."""
        with self.connect() as c:
            return c.execute("""UPDATE edge_bff.jobs SET input=input||'{"stop_requested":true}'::jsonb
                WHERE owner_key=%s AND request_id=%s AND state IN ('QUEUED','RUNNING','RECOVERING') RETURNING *""",
                (owner, request_id)).fetchone()

    def heartbeat(self, request_id, token, seconds):
        with self.connect() as c:
            return bool(c.execute('''UPDATE edge_bff.jobs SET lease_expires_at=now()+%s*interval '1 second'
                WHERE request_id=%s AND lease_token=%s AND lease_expires_at>now() AND state IN ('RUNNING','RECOVERING')''',
                (seconds, request_id, token)).rowcount)

    def attempted(self, row):
        with self.connect() as c:
            return bool(c.execute('''UPDATE edge_bff.jobs SET attempt_count=attempt_count+1
                WHERE request_id=%s AND lease_token=%s AND lease_expires_at>now() AND state NOT IN ('FINISHED','FAILED','INTERRUPTED')''',
                (row['request_id'], row['lease_token'])).rowcount)

    def transition(self, row, state, *, conversation_id=None, run_status=None, error_code=None):
        terminal = state in TERMINAL
        with self.connect() as c:
            changed = c.execute('''UPDATE edge_bff.jobs SET state=%s,conversation_id=COALESCE(%s,conversation_id),
                run_status=%s,error_code=%s,state_version=state_version+1,updated_at=now(),
                completed_at=CASE WHEN %s THEN now() ELSE NULL END,
                lease_token=CASE WHEN %s THEN NULL ELSE lease_token END,
                lease_expires_at=CASE WHEN %s THEN NULL ELSE lease_expires_at END
                WHERE request_id=%s AND lease_token=%s AND lease_expires_at>now() AND state NOT IN ('FINISHED','FAILED','INTERRUPTED') RETURNING *''',
                (state, conversation_id, run_status, error_code, terminal, terminal, terminal,
                 row['request_id'], row['lease_token'])).fetchone()
            if changed and changed['conversation_id']:
                self._index(c, changed)
            if changed and terminal:
                self._promote(c, changed)
            if changed:
                logger.info(json.dumps({'event':'job_state', 'request_id':changed['request_id'],
                                        'state':changed['state'], 'version':changed['state_version']}))
            return changed

    def _index(self, c, row):
        c.execute('''INSERT INTO edge_bff.conversation_ui(owner_key,conversation_id,title)
            VALUES (%s,%s,%s) ON CONFLICT (owner_key,conversation_id) DO UPDATE SET updated_at=now()''',
            (row['owner_key'], row['conversation_id'], row['input']['message'][:80]))

    def list_conversations(self, owner, query='', bookmarked=False, offset=0, limit=30):
        with self.connect() as c:
            return c.execute('''SELECT * FROM edge_bff.conversation_ui WHERE owner_key=%s
                AND title ILIKE %s AND (NOT %s OR bookmarked) ORDER BY updated_at DESC,conversation_id
                LIMIT %s OFFSET %s''', (owner, '%'+query+'%', bookmarked, limit, offset)).fetchall()

    def conversation(self, owner, conversation_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM edge_bff.conversation_ui WHERE owner_key=%s AND conversation_id=%s',
                            (owner, conversation_id)).fetchone()
            if not row:
                raise StoreError('CONVERSATION_NOT_FOUND', 404)
            return row

    def preferences(self, owner, conversation_id, *, bookmarked=None, title=None, request_id=None, pinned=None):
        with self.connect() as c:
            row = c.execute('SELECT * FROM edge_bff.conversation_ui WHERE owner_key=%s AND conversation_id=%s FOR UPDATE',
                            (owner, conversation_id)).fetchone()
            if not row:
                raise StoreError('CONVERSATION_NOT_FOUND', 404)
            pins = row['pinned_request_ids']
            if request_id:
                pins = [x for x in pins if x != request_id]
                if pinned:
                    pins.append(request_id)
                if len(pins) > 500:
                    raise StoreError('PIN_LIMIT', 422)
            return c.execute('''UPDATE edge_bff.conversation_ui SET bookmarked=%s,title=%s,pinned_request_ids=%s,
                updated_at=now() WHERE owner_key=%s AND conversation_id=%s RETURNING *''',
                (row['bookmarked'] if bookmarked is None else bookmarked, title or row['title'], pins,
                 owner, conversation_id)).fetchone()

    def cleanup_sessions(self):
        with self.connect() as c:
            c.execute('DELETE FROM edge_bff.sessions WHERE expires_at<now() OR revoked_at<now()-interval \'1 day\'')
