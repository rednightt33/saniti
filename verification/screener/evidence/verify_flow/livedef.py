import json, os, sys, urllib.request, urllib.parse, base64
sys.path.insert(0, '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools')
import pgq2
out = sys.argv[1]
for name, sig in [('f06','public.refresh_feature_06(text, date)'),('f02','public.refresh_feature_02(text, date)'),('f05','public.refresh_feature_05(date, date, text[])')]:
    r = pgq2.q(f"select pg_get_functiondef('{sig}'::regprocedure)")
    if 'error' in r: print(name, r['error']); continue
    open(f"{out}/live_{name}.sql",'w').write(r['rows'][0][0])
    print(name, len(r['rows'][0][0]))
r = pgq2.q("select p.oid::regprocedure::text from pg_proc p where proname like 'refresh_feature_03%'")
print(r.get('rows'))
