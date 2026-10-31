"""Read-only: TradingView intraday depth and bar shape for a few IDX symbols (the price job's own client)."""
import json, sys, time, random
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parents[2] / 'apps' / 'idx-price-cron'))
import price_update as pu
from price_update import Symbol, open_socket, start_chart_session, frame, parse_frames, JAKARTA

def bars(ws, cs, sym, tf, n, timeout=60):
    alias, sid = f's_{random.randrange(10**6)}', f'x{random.randrange(10**6)}'
    ws.send(frame('resolve_symbol', [cs, alias, '=' + json.dumps({'symbol': sym, 'adjustment': 'splits', 'session': 'regular'})]))
    ws.send(frame('create_series', [cs, sid, sid, alias, tf, n]))
    got, done, end = {}, False, time.monotonic() + timeout
    while not done and time.monotonic() < end:
        try: raw = ws.recv()
        except Exception: continue
        objs, hb = parse_frames(raw)
        for h in hb: ws.send(h)
        for o in objs:
            if o.get('m') == 'timescale_update':
                for p in o['p'][1].get(sid, {}).get('s', []):
                    v = p['v']; got[int(v[0])] = v
            elif o.get('m') == 'series_completed' and sid in o.get('p', []): done = True
            elif o.get('m') in ('critical_error', 'series_error'): raise RuntimeError(str(o)[:300])
    ws.send(frame('remove_series', [cs, sid]))
    return [got[k] for k in sorted(got)]

ws = open_socket(60, False); cs = start_chart_session(ws)
for sym in ('IDX:BBCA', 'IDX:WIFI'):
    for tf in ('5', '15', '60', '240'):
        b = bars(ws, cs, sym, tf, 20000)
        loc = [datetime.fromtimestamp(v[0], timezone.utc).astimezone(JAKARTA) for v in b]
        days = Counter(t.date() for t in loc)
        last_day = max(days); times = sorted({t.strftime('%H:%M') for t in loc if t.date() == last_day})
        fri = sorted({t.strftime('%H:%M') for t in loc if t.date() == date(2026, 10, 30)})
        print(json.dumps({'symbol': sym, 'tf': tf, 'bars': len(b), 'first': str(loc[0]), 'last': str(loc[-1]),
                          'days': len(days), 'median_bars_per_day': sorted(days.values())[len(days)//2],
                          'last_day_times': times[:4] + ['...'] + times[-4:], 'friday_30oct_times': fri[:3] + ['...'] + fri[-3:],
                          'vol_last': b[-1][5] if len(b[-1]) > 5 else None}), flush=True)
ws.close()
