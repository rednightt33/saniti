"""EXEC-BACKTEST-REVAMP P9.3: the broker basis block of an exported ticker (verification/backtest/lookahead/export.sh:
px.json, br.json) with the publisher's own rule (apps/terminal-publisher/publisher.py broker_basis), from the ticker's
price actions in idx_event_annotation (pgweb read-only role, credentials from the environment as export.sh, one
SELECT). Writes basis.json beside the export, which real_data.ts reads.
  PGWEB_HOST=<host> PGWEB_AUTH=<user:password> python3 basis_from_export.py OUTDIR/COCO ..."""
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'apps' / 'terminal-publisher'))
import publisher as pub  # noqa: E402


def actions(ticker):
    sql = pub.BASIS_ACTIONS_SQL.replace('%s', f"'{ticker}'", 1).replace('%s', 'ARRAY[' + ','.join(f"'{t}'" for t in pub.PRICE_ACTION_TYPES) + ']', 1)
    out = subprocess.run(['curl', '-sS', '-m', '120', '-u', os.environ['PGWEB_AUTH'], '--data-urlencode', f'query={sql}',
                          f'https://{os.environ["PGWEB_HOST"]}/api/query'], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    if 'rows' not in d:
        raise SystemExit(f'{ticker}: {d}')
    num = lambda x: None if x in (None, '') else float(x)
    return [(r[0][:10], r[1], num(r[2]), num(r[3]), num(r[4])) for r in d['rows'] or []]


for folder in sys.argv[1:]:
    t = Path(folder).name
    px, br = json.load(open(f'{folder}/px.json')), json.load(open(f'{folder}/br.json'))
    bars = {r[0]: (float(r[2]), float(r[3]), float(r[4])) for r in px['rows'] if r[2] is not None}
    agg = defaultdict(lambda: [0.0, 0.0])
    for r in br['rows']:
        if r[3] == 'Regular':
            a = agg[r[0]]; a[0] += float(r[4] or 0) + float(r[5] or 0); a[1] += float(r[6] or 0) + float(r[7] or 0)
    days = [(d, v / (100 * n) if n else None, *bars[d]) for d, (v, n) in sorted(agg.items()) if d in bars]
    rows = pub.broker_basis(actions(t), days, max(agg) if agg else None)
    json.dump(pub.basis_block(rows), open(f'{folder}/basis.json', 'w'))
    print(t, [dict(zip(pub.BASIS_COLUMNS, r)) for r in rows])
