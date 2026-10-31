"""Read-only: do TradingView's intraday bars add up to its daily candle (volume sum, open/close/high/low)?"""
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parents[2] / 'apps' / 'idx-price-cron'))
exec(open(str(_P(__file__).with_name('intraday_probe.py'))).read().split("ws = open_socket")[0])
ws = open_socket(60, False); cs = start_chart_session(ws)
for sym in ('IDX:BBCA', 'IDX:WIFI', 'IDX:GOTO'):
    daily = {datetime.fromtimestamp(v[0], timezone.utc).astimezone(JAKARTA).date(): v for v in bars(ws, cs, sym, '1D', 30)}
    for tf in ('5', '15', '60', '240'):
        per = defaultdict(list)
        for v in bars(ws, cs, sym, tf, 400):
            per[datetime.fromtimestamp(v[0], timezone.utc).astimezone(JAKARTA).date()].append(v)
        res = []
        for d in sorted(per)[-6:-1]:
            b, D = per[d], daily.get(d)
            if not D: continue
            vol = sum(x[5] for x in b)
            res.append((str(d)[5:], round(vol / D[5], 4), b[0][1] == D[1], b[-1][4] == D[4], max(x[2] for x in b) == D[2], min(x[3] for x in b) == D[3]))
        print(sym, tf, 'day: vol_sum/daily_vol, open=, close=, high=, low=', res)
ws.close()
