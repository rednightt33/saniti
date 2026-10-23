import os,json,gzip,base64,sys,runpy,hashlib
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
payload=''.join(os.environ[f'BUNDLE_{i}'] for i in range(int(os.environ['BUNDLE_COUNT'])))
files=json.loads(gzip.decompress(base64.b64decode(payload)))
base=Path('/tmp/ihsg_bundle');base.mkdir(exist_ok=True)
for name,code in files.items():
 p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(code)
sys.path[:0]=[str(base/'features/feature04'),str(base/'apps/feature-04-worker'),str(base/'scripts')]
mode=os.environ['MODE'];ticker=os.environ['TICKER']
def emit(event,**values):print(json.dumps({'event':event,**values},default=str),flush=True)
if mode in ('migration_dry_run','migration_apply'):
 migration=files['database/migrations/20261023_007_idx_index_optional_volume.sql']
 body=migration.strip().removeprefix('BEGIN;').removesuffix('COMMIT;')
 with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as db:
  existing=db.execute("SELECT count(*) FROM pg_trigger WHERE tgname IN ('idx_price_optional_volume_guard','feature01_optional_volume_guard')").fetchone()[0]
  if existing and mode=='migration_apply':
   if existing!=2:raise RuntimeError('Partial volume guard installation')
   emit('migration_already_applied')
  else:
   db.execute('BEGIN')
   try:
    db.execute(body,prepare=False)
    try:
     with db.transaction():
      db.execute('UPDATE public."Price_Stock_Indonesia_IDX" SET volume=NULL WHERE ticker=%s AND date=(SELECT min(date) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s)',('BBCA','BBCA'))
    except psycopg.errors.CheckViolation:pass
    else:raise RuntimeError('Stock NULL volume was not rejected')
    nullable=db.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('Price_Stock_Indonesia_IDX','Feature_01_Stock_Daily') AND column_name='volume' AND is_nullable='YES'").fetchone()[0]
    if nullable!=2:raise RuntimeError('Expected two nullable source-volume columns')
    db.execute('COMMIT' if mode=='migration_apply' else 'ROLLBACK')
    emit('migration_verified',mode=mode,nullable_columns=nullable,stock_null_volume_rejected=True,sha256=hashlib.sha256(migration.encode()).hexdigest())
   except BaseException:
    db.execute('ROLLBACK');raise
elif mode in ('prices_preflight','prices_apply'):
 os.environ['ACTION']='apply' if mode=='prices_apply' else 'preflight'
 runpy.run_path(str(base/'scripts/backfill_idx_price_ticker.py'),run_name='__main__')
elif mode=='initialize_feature04':
 import backfill
 import uuid
 with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,autocommit=True) as db:
  result=backfill.process_ticker(db,ticker,uuid.UUID(os.environ['BACKFILL_RUN_ID']),write=True)
  emit('feature04_initial_history',**result)
 import bootstrap_states
 sys.argv=['bootstrap_states.py','--ticker',ticker,'--require-stored-match']
 bootstrap_states.main()
 with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as db:
  with db.transaction():
   dates=[r[0] for r in db.execute('SELECT date FROM public."Price_Stock_Indonesia_IDX" WHERE ticker=%s ORDER BY date DESC LIMIT 5',(ticker,))]
   changed=db.execute('''UPDATE public."Feature04_Calculation_Queue" SET status='PENDING',dirty_from_date=%s,work_revision=work_revision+1,requested_columns=NULL,source_attempt_count=0,next_attempt_at=CURRENT_TIMESTAMP,claimed_at=NULL,claim_token=NULL,claim_expires_at=NULL,last_error=NULL,last_error_code=NULL,updated_at=CURRENT_TIMESTAMP WHERE asset_type='equity' AND ticker=%s AND timeframe='Daily' AND status<>'PROCESSING' ''',(min(dates),ticker)).rowcount
   if changed!=1:raise RuntimeError('Could not scope normal worker verification to the latest five index sessions')
   db.execute('''UPDATE public."Feature04_Column_Status" SET status='PENDING',dirty_from_date=%s,last_error=NULL,last_error_code=NULL,updated_at=CURRENT_TIMESTAMP WHERE asset_type='equity' AND ticker=%s AND timeframe='Daily' ''',(min(dates),ticker))
  emit('feature04_latest_five_queued',ticker=ticker,dirty_from_date=min(dates))
elif mode=='audit_catalog':
 runpy.run_path(str(base/'scripts/audit_feature_catalog_semantics.py'),run_name='__main__')
else:raise RuntimeError('Unknown operation')
