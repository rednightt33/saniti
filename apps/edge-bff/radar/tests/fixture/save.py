"""Save the Radar files of a rehearsal database for the fixture build (look check only; nothing is committed).

  DATABASE_URL=... python apps/edge-bff/radar/tests/fixture/save.py
Builds them with the publisher's own code (apps/terminal-publisher/radar.py), as a run would."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
import psycopg  # noqa: E402
import publisher as pub  # noqa: E402
import radar  # noqa: E402

OUT = Path(__file__).resolve().parent / 'data'
OUT.mkdir(exist_ok=True)
with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as c:
    names = {t: n for t, n in c.execute('SELECT "Ticker", coalesce("Company Name", "Ticker") FROM public."IDX_Stock_Universe"').fetchall()}
    try:
        lists = [tuple(r[:4]) + (list(r[6] or []),) for r in c.execute(pub.STOCK_LISTS_SQL).fetchall()]
    except Exception:  # noqa: BLE001 - the rehearsal database may have no stock lists: a saved copy (LISTS_JSON)
        # a saved copy read through pgweb holds the members as PostgreSQL array text ('{AALI,BBCA}'), not a list
        arr = lambda v: v if isinstance(v, list) else [x for x in str(v or '').strip('{}').split(',') if x]
        lists = [tuple(r[:4]) + (arr(r[6]),) for r in json.load(open(os.environ['LISTS_JSON']))] if os.environ.get('LISTS_JSON') else []
    files = radar.build(c, names, lists, stream=lambda sql, params: list(pub.stream_rows(c, sql, params)))
index = {}
for name, doc, rows, as_of in files:
    body, sha = pub.encode(doc)
    (OUT / f'{name}.json').write_text(json.dumps(doc, separators=(',', ':')))
    index[name] = {'sha256': sha, 'bytes': len(body), 'rows': rows, 'as_of': as_of}
(OUT / 'index.json').write_text(json.dumps({'finished_at': 'fixture', 'files': index}))
print(len(index), 'files saved to', OUT)
