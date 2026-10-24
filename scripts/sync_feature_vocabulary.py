#!/usr/bin/env python3
"""Atomically seed reviewed presentation metadata; default rollback and semantic drift rejection."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_feature_vocabulary_seed import SOURCES,semantic_hash

ROOT=Path(__file__).resolve().parents[1]
MIGRATION='database/migrations/20261025_003_create_feature_vocabulary.sql'
KEYS=('source_schema','source_table','column_name','language_code')

def inventory(db):
    return db.execute('''SELECT f.*,c.ordinal_position FROM public."Feature_Catalog" f
     JOIN information_schema.columns c ON c.table_schema='public' AND c.table_name=f.feature_table AND c.column_name=f.feature_column
     WHERE f.is_active AND f.feature_table=ANY(%s) ORDER BY f.feature_table,c.ordinal_position''',(SOURCES,)).fetchall()

def validate_seed(seed,source):
    current={(r['feature_table'],r['feature_column']):r for r in source}
    proposed={(r['source_table'],r['column_name']):r for r in seed}
    if len(seed)!=391 or len(proposed)!=len(seed) or proposed.keys()!=current.keys():
        raise RuntimeError('Reviewed vocabulary seed does not exactly cover approved physical source columns')
    for key,r in proposed.items():
        if current[key].get('semantic_review_status')!='CALCULATION_VERIFIED':
            raise RuntimeError(f'Source definition is not calculation-verified: {key}')
        if r['review_status']!='VERIFIED' or r['source_semantic_hash']!=semantic_hash(current[key]):
            raise RuntimeError(f'Source semantics changed after vocabulary review: {key}; rebuild and review the seed before publication')
        if r['feature_number']==4 or r['source_table'] not in SOURCES:raise RuntimeError('Vocabulary contains an out-of-scope Feature')
        for c in ('column_name_proper','formula','unit','definition','what_it_tells_us'):
            if not r[c].strip():raise RuntimeError(f'Empty vocabulary field {key}/{c}')

def sync(db,seed):
    names=list(seed[0]);identifier=sql.SQL(',').join(map(sql.Identifier,names))
    updates=sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c),sql.Identifier(c)) for c in names if c not in KEYS)
    old=sql.SQL(',').join(sql.SQL('t.{}').format(sql.Identifier(c)) for c in names)
    new=sql.SQL(',').join(sql.SQL('EXCLUDED.{}').format(sql.Identifier(c)) for c in names)
    statement=sql.SQL('INSERT INTO public."Feature_Vocabulary" AS t ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {},updated_at=statement_timestamp() WHERE ROW({}) IS DISTINCT FROM ROW({})').format(identifier,sql.SQL(',').join(sql.Placeholder() for _ in names),sql.SQL(',').join(map(sql.Identifier,KEYS)),updates,old,new)
    changed=0
    for r in seed:changed+=db.execute(statement,[r[c] for c in names]).rowcount
    return changed

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');a=p.parse_args()
    seed=json.loads((ROOT/'database/feature_vocabulary_seed.json').read_text())
    with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,application_name='feature-vocabulary-approved-sync') as db:
        db.execute("SET LOCAL lock_timeout='10s'");db.execute("SET LOCAL statement_timeout='3min'")
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('feature-vocabulary-sync',0))")
        validate_seed(seed,inventory(db))
        db.execute((ROOT/MIGRATION).read_text(),prepare=False)
        changed=sync(db,seed);rerun=sync(db,seed)
        if rerun:raise RuntimeError('Idempotent vocabulary rerun changed entries')
        actual=db.execute('SELECT * FROM public."Feature_Vocabulary" WHERE source_table=ANY(%s)',(SOURCES,)).fetchall()
        validate_seed(actual,inventory(db))
        expected={(r['source_table'],r['column_name']):r for r in seed}
        for r in actual:
            e=expected[(r['source_table'],r['column_name'])]
            if any(r[c]!=e[c] for c in e):raise RuntimeError('Stored vocabulary payload differs from reviewed seed')
        coverage=db.execute('''SELECT source_table,scope,count(*) AS entries FROM public."Feature_Vocabulary" GROUP BY source_table,scope ORDER BY source_table''').fetchall()
        plan=db.execute('''EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT column_name,column_name_proper,formula,unit,definition,what_it_tells_us FROM public."Feature_Vocabulary"
         WHERE source_schema='public' AND source_table=%s AND language_code='id-ID' ORDER BY display_order''',(SOURCES[-1],)).fetchone()
        if not a.apply:db.rollback()
        print(json.dumps(dict(event='vocabulary_complete',committed=a.apply,entries=len(actual),changed=changed,rerun_modified=rerun,coverage=coverage,query_plan=plan,frontend_changed=False),default=str),flush=True)

if __name__=='__main__':main()
