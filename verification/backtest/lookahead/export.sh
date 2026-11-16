#!/bin/bash
# EXEC-BACKTEST-REVAMP P6.4: one ticker's daily prices and broker rows from dev, read-only through the pgweb service's
# HTTP API (the read-only role pgweb_reader), as the JSON the look-ahead check reads (real_data.ts).
#   PGWEB_HOST=<pgweb public host> PGWEB_AUTH=<user:password> ./export.sh BBRI 2016-01-01 2026-12-31 out/BBRI
# The host and the credentials are the pgweb service's variables on Railway (PGWEB_AUTH_USER, PGWEB_AUTH_PASS); they
# are read from the environment and never written anywhere. Only SELECT statements are sent.
set -euo pipefail
T=$1; FROM=$2; TO=$3; OUT=$4
[[ $T =~ ^[A-Z0-9]{1,12}$ && $FROM =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ && $TO =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "usage: export.sh TICKER FROM TO OUTDIR" >&2; exit 2; }
: "${PGWEB_HOST:?set PGWEB_HOST}" "${PGWEB_AUTH:?set PGWEB_AUTH}"
mkdir -p "$OUT"
q() { curl -sS -m 280 -u "$PGWEB_AUTH" --data-urlencode "query=$1" "https://$PGWEB_HOST/api/query"; }
q "SELECT to_char(date,'YYYY-MM-DD') AS date, open, high, low, close, volume FROM \"Price_Stock_Indonesia_IDX\" WHERE ticker='$T' AND timeframe='Daily' AND date BETWEEN '$FROM' AND '$TO' ORDER BY date" > "$OUT/px.json"
# year by year (the pgweb statement timeout), merged into one file
python3 - "$OUT" "$T" "$FROM" "$TO" <<'PY'
import json, os, subprocess, sys
out, t, a, b = sys.argv[1:5]
rows, cols = [], None
for y in range(int(a[:4]), int(b[:4]) + 1):
    lo, hi = max(a, f'{y}-01-01'), min(b, f'{y}-12-31')
    sql = (f'SELECT to_char("Date",\'YYYY-MM-DD\') AS trade_date, "Broker" AS broker, "Investor Type" AS investor_type, "Market Board" AS market_board, '
           f'"Buy Value" AS buy_value, "Sell Value" AS sell_value, "Buy Lots" AS buy_lots, "Sell Lots" AS sell_lots, buy_freq, sell_freq '
           f'FROM "IDX_Broker_Summary" WHERE "Symbol"=\'{t}\' AND "Date" BETWEEN \'{lo}\' AND \'{hi}\' ORDER BY 1, 2, 3, 4')
    d = json.loads(subprocess.run(['curl', '-sS', '-m', '280', '-u', os.environ['PGWEB_AUTH'], '--data-urlencode', f'query={sql}',
                                   f'https://{os.environ["PGWEB_HOST"]}/api/query'], capture_output=True, check=True).stdout)
    if 'rows' not in d: sys.exit(f'{t} {y}: {d}')
    cols = d['columns']; rows += d['rows'] or []
json.dump({'columns': cols, 'rows': rows}, open(f'{out}/br.json', 'w'))
print(t, len(rows), 'broker rows')
PY
