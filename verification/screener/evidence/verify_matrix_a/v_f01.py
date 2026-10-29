import importlib.util, json, subprocess
spec = importlib.util.spec_from_file_location('pgq2', '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/tools/pgq2.py')
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
D = '/tmp/claude-0/-home-user-saniti/65bd49d0-9dca-5072-b7db-b62314cf2cd3/scratchpad/audit/verify_matrix_a/data/'
for t in ('BBRI', 'BLTA', 'GOTO'):
    r = pg.q(f"""select date::text, return_5d_pct, return_20d_pct, return_60d_pct from public."Feature_01_Stock_Daily" where ticker='{t}' order by date""")
    json.dump(r['rows'], open(D + t + '.f01.json', 'w')); print(t, len(r['rows']), r['_ms'])
