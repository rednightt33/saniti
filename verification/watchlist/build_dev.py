"""EXEC-WATCHLIST: build watchlist-stocks from dev with the publisher's own module, read-only through pgweb (no database
login). Parameters are written as SQL literals here only for pgweb; the publisher binds them. Usage:
python3 verification/watchlist/build_dev.py OUT.json"""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher'))
import radar_formulas_doc as r  # noqa: E402
import watchlist as W  # noqa: E402


def lit(v):
    if isinstance(v, (list, tuple)):
        return 'ARRAY[' + ','.join(lit(x) for x in v) + ']::text[]'
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def run(sql, params):
    for k, v in params.items():
        sql = sql.replace(f'%({k})s', lit(v))
    return [tuple(x) for x in r.query(sql)]


if __name__ == '__main__':
    doc = W.build(run)
    Path(sys.argv[1]).write_text(json.dumps(doc, separators=(',', ':')))
    print(doc['prices_through'], doc['broker_through'], doc['radar_date'], doc['events_loaded'], len(doc['ticker']),
          'stocks;', sum(v is not None for v in doc['last']), 'priced;', len(doc['events']), 'with events;',
          len(doc['radar']), 'in Radar;', len(json.dumps(doc, separators=(',', ':'))) // 1024, 'KB')
