"""Save the Overview files of a rehearsal database for the fixture build (look check only; nothing is committed).

  DATABASE_URL=... python apps/edge-bff/overview/tests/fixture/save.py
Builds them with the publisher's own code (apps/terminal-publisher/overview.py), as a run without a previous
publication would (every series date counted once)."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
import psycopg  # noqa: E402
import overview  # noqa: E402
import publisher as pub  # noqa: E402

OUT = Path(__file__).resolve().parent / 'data'
OUT.mkdir(exist_ok=True)
with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as c:
    try:
        lists = [tuple(r[:4]) + (list(r[6] or []),) for r in c.execute(pub.STOCK_LISTS_SQL).fetchall()]
    except psycopg.Error:  # a rehearsal database without the list definitions: the lists and members alone
        mem = {}
        for k, t in c.execute('SELECT list_key, "Ticker" FROM public."Stock_List_Member"').fetchall():
            mem.setdefault(k, []).append(t)
        lists = [(k, kind, code, name, mem.get(k, [])) for k, kind, code, name in c.execute(
            'SELECT list_key, list_kind, code, name FROM public."Stock_List" WHERE is_enabled ORDER BY sort_order, list_key').fetchall()]
    files, _kept, _carry = overview.files(c, {}, lists, stream=lambda sql, params: list(pub.stream_rows(c, sql, params)))
index = {}
for name, doc, rows, as_of in files:
    body, sha = pub.encode(doc)
    (OUT / f'{name}.json').write_text(json.dumps(doc, separators=(',', ':')))
    index[name] = {'sha256': sha, 'bytes': len(body), 'rows': rows, 'as_of': as_of}
(OUT / 'index.json').write_text(json.dumps({'finished_at': 'fixture', 'files': index}))
print(len(index), 'files saved to', OUT)
