"""Read-only: does TradingView send older intraday bars after request_more_data (pagination beyond one request)?"""
import json, sys, time, random
from datetime import datetime, timezone
from pathlib import Path as _P; sys.path.insert(0, str(_P(__file__).resolve().parents[2] / 'apps' / 'idx-price-cron'))
from price_update import open_socket, start_chart_session, frame, parse_frames, JAKARTA

def series(ws, cs, sym, tf, n, more_rounds, more_n, timeout=40):
    alias, sid = f's_{random.randrange(10**6)}', f'x{random.randrange(10**6)}'
    ws.send(frame('resolve_symbol', [cs, alias, '=' + json.dumps({'symbol': sym, 'adjustment': 'splits', 'session': 'regular'})]))
    ws.send(frame('create_series', [cs, sid, sid, alias, tf, n]))
    got, rounds, done_count, end = {}, 0, 0, time.monotonic() + timeout * (more_rounds + 1)
    while time.monotonic() < end:
        try: raw = ws.recv()
        except Exception: continue
        objs, hb = parse_frames(raw)
        for h in hb: ws.send(h)
        for o in objs:
            if o.get('m') == 'timescale_update':
                for p in o['p'][1].get(sid, {}).get('s', []):
                    got[int(p['v'][0])] = p['v']
            elif o.get('m') == 'series_completed' and sid in o.get('p', []):
                done_count += 1
                first = datetime.fromtimestamp(min(got), timezone.utc).astimezone(JAKARTA) if got else None
                print(json.dumps({'tf': tf, 'round': rounds, 'bars': len(got), 'first': str(first)}), flush=True)
                if rounds >= more_rounds:
                    return got
                rounds += 1
                ws.send(frame('request_more_data', [cs, sid, more_n]))
            elif o.get('m') in ('critical_error', 'series_error', 'symbol_error'):
                print('error', str(o)[:300]); return got
    print('timeout after rounds', rounds, 'bars', len(got)); return got

ws = open_socket(60, False); cs = start_chart_session(ws)
for tf in ('15', '60'):
    series(ws, cs, 'IDX:BBCA', tf, 5000, 4, 5000)
ws.close()
