#!/usr/bin/env python3
"""One-shot Railway entrypoint; prepare and apply are separate deployments.

No server, cron or arbitrary SQL endpoint. Persistent stage markers prevent an
accidental restart from repeating work. All scope/settings come from reviewed
runtime variables; source and database credentials are never logged.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import psycopg
import repair_fixed_income_dates as repair
from engine import library_contract


def save(path, value):
    with path.open('xb') as output:
        output.write(repair.encoded(value))
        output.flush()
        os.fsync(output.fileno())


def main():
    stage = os.environ['FI_REPAIR_STAGE']
    if stage not in {'prepare', 'apply'}:
        raise ValueError('Stage must be prepare or apply')
    run = os.environ['FI_REPAIR_RUN']
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run):
        raise ValueError('Invalid operator run name')
    storage = Path(os.environ.get('FI_REPAIR_STORAGE', '/repair'))
    if not os.path.ismount(storage):
        raise ValueError('A persistent repair volume must be mounted before running')
    directory = storage / run
    directory.mkdir(exist_ok=True, mode=0o700)
    started = directory / (stage + '-started.json')
    if started.exists():
        print(json.dumps({'status': 'STAGE_ALREADY_STARTED', 'stage': stage, 'run': run}), flush=True)
        return
    now = datetime.now(timezone.utc)
    plan_path = directory / 'plan.json'
    contract = library_contract()
    print(json.dumps({'event': 'repair_job_start', 'stage': stage, 'run': run, 'libraries': contract}, default=str), flush=True)
    if stage == 'prepare':
        save(started, {'started_at': now.isoformat()})
        policy = json.loads(repair.POLICY.read_text())
        markets = sorted(set(os.environ['FI_REPAIR_MARKETS'].split()))
        if not markets or any(market not in policy for market in markets):
            raise ValueError('Specify markets in the reviewed provider policy')
        dates = repair.normalized_dates(os.environ['FI_REPAIR_DATES'].split())
        with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as connection:
            connection.execute('SET default_transaction_read_only=on')
            plan = repair.prepare(connection, markets, dates, policy, now,
                                  int(os.environ.get('FI_REPAIR_REQUEST_BARS', '60')))
        repair.validate_plan(plan, now)
        save(plan_path, plan)
        result = {'status': 'PREPARED_READ_ONLY', 'operator_run': run, 'run_id': plan['run_id'],
                  'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                  'markets': markets, 'dates': [str(day) for day in dates],
                  'replacement_price_yield_rows': len(plan['replacements']),
                  'tickers': len(plan['tickers']), 'existing_selected_price_rows': len(plan['before']['prices']),
                  'affected_feature_rows': sum(len(item['rows']) for item in plan['calculations'].values())}
    else:
        content = plan_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != os.environ['FI_REPAIR_EXPECTED_SHA256']:
            raise ValueError('Reviewed plan hash differs; no migration or repair performed')
        plan = repair.restore_types(json.loads(content))
        repair.validate_plan(plan, now)
        migration_path = repair.ROOT / 'database/migrations/20261013_011_verify_fixed_income_sessions.sql'
        migration = migration_path.read_bytes()
        if hashlib.sha256(migration).hexdigest() != os.environ['FI_REPAIR_MIGRATION_SHA256']:
            raise ValueError('Reviewed migration hash differs; no write performed')
        save(started, {'started_at': now.isoformat(), 'plan_sha256': hashlib.sha256(content).hexdigest()})
        with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as connection:
            if connection.execute('SHOW transaction_read_only').fetchone()[0] == 'on':
                raise ValueError('Apply requires the reviewed write-capable operator connection')
            # Durable before-image exists before even the schema migration.
            save(directory / 'pre-migration-backup.json', {'before': plan['before'],
                'market_schedules': repair.records(connection, 'SELECT * FROM public."Fixed_Income_Market_Schedule" ORDER BY market_code')})
            columns = connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='Fixed_Income_Market_Schedule' AND column_name IN ('provider_timezone_name','provider_session')").fetchone()[0]
            if columns == 0:
                connection.execute(migration.decode())
                print(json.dumps({'event': 'migration_applied', 'sha256': hashlib.sha256(migration).hexdigest()}), flush=True)
            elif columns != 2:
                raise ValueError('Partial migration detected; inspect before applying')
            result = repair.apply(connection, plan, directory / 'before.json', now)
            # Separate post-commit connection verifies persistence, not just staged writes.
        with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as connection:
            for ticker in plan['tickers']:
                repair.assert_feature_values(repair.feature_suffix(connection, [ticker], min(plan['dates'])),
                                             plan['calculations'][ticker]['rows'])
            logs = connection.execute('SELECT count(*) FROM public."Feature04_Calculation_Log" WHERE detail=%s AND result=%s',
                                      ('selected-date-repair:' + plan['run_id'], 'SUCCESS')).fetchone()[0]
            if logs != len(plan['tickers']):
                raise ValueError('Post-commit calculation log coverage differs')
            result['post_commit_verified'] = True
    save(directory / (stage + '-result.json'), result)
    print(json.dumps(result, default=str), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Error messages name the source series/date, but never expose connection strings.
        message = re.sub(r'postgres(?:ql)?://[^\s\"\']+', '[database URL redacted]', str(error))
        print(json.dumps({'status': 'FAILED', 'error_type': type(error).__name__, 'message': message[:1000]}), flush=True)
        sys.exit(1)
