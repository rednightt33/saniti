"""Read-only: CREATE statements of dev tables (columns, generated/identity, constraints, indexes, chosen triggers) and
the functions those triggers call, for a local rehearsal. Prints SQL to stdout."""
import sys
sys.path.insert(0, 'verification/terminal_api')
import pgq

def q(sql):
    r = pgq.q(sql)
    if 'error' in r: raise SystemExit(r['error'] + '\n' + sql)
    return r['rows']

def lit(s): return "'" + s.replace("'", "''") + "'"

tables, keep_triggers = sys.argv[1].split(','), set(sys.argv[2].split(',')) if len(sys.argv) > 2 and sys.argv[2] else set()
out, funcs = [], []
for t in tables:
    cols = q(f"""SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
      a.attgenerated, a.attidentity FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
      WHERE a.attrelid = {lit('public."'+t+'"')}::regclass AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""")
    lines = []
    for name, typ, nn, dflt, gen, ident in cols:
        c = f'"{name}" {typ}'
        if gen == 's': c += f' GENERATED ALWAYS AS ({dflt}) STORED'
        elif ident in ('a', 'd'): c += ' GENERATED ' + ('ALWAYS' if ident == 'a' else 'BY DEFAULT') + ' AS IDENTITY'
        elif dflt: c += f' DEFAULT {dflt}'
        if nn: c += ' NOT NULL'
        lines.append('    ' + c)
    for name, d in q(f"""SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = {lit('public."'+t+'"')}::regclass
                         AND contype IN ('p','u','c','x') ORDER BY contype DESC, conname"""):
        lines.append(f'    CONSTRAINT "{name}" {d}')
    out.append(f'CREATE TABLE public."{t}" (\n' + ',\n'.join(lines) + '\n);')
    for (d,) in q(f"""SELECT pg_get_indexdef(i.indexrelid) FROM pg_index i WHERE i.indrelid = {lit('public."'+t+'"')}::regclass
                     AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)"""):
        out.append(d + ';')
    for name, d, fn in q(f"""SELECT t.tgname, pg_get_triggerdef(t.oid), p.oid::regprocedure::text FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
                            WHERE t.tgrelid = {lit('public."'+t+'"')}::regclass AND NOT t.tgisinternal"""):
        if name in keep_triggers:
            funcs.append(fn); out.append(d + ';')
fks = []
for t in tables:
    for name, d in q(f"""SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = {lit('public."'+t+'"')}::regclass AND contype='f'"""):
        fks.append(f'ALTER TABLE public."{t}" ADD CONSTRAINT "{name}" {d} NOT VALID;')
fdefs = []
for fn in dict.fromkeys(funcs):
    fdefs.append(q(f"SELECT pg_get_functiondef({lit(fn)}::regprocedure)")[0][0] + ';')
print('\n'.join(fdefs + out + fks))
