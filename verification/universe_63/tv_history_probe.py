"""EXEC-UNIVERSE-BROKER S1.0 (read-only): the TradingView daily history of the 63 active 4-letter codes outside
IDX_Stock_Universe, compared with BBCA's sessions (the price loader's own fetch, apps/idx-price-cron/price_update.py
request_symbol). Per code: bars, first and last date, sessions of its own life without a bar (BBCA had one), zero-volume
bars, and the same over the last 60 BBCA sessions (what the daily price cron would meet). Writes OUT/probe.json.

Usage: python3 tv_history_probe.py OUT CODES.json   (CODES.json: [[code, kind], ...])"""
import json, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/idx-price-cron')); sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
import price_update as price  # noqa: E402
import pgq  # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
codes = json.load(open(sys.argv[2]))
bbca = [date.fromisoformat(r[0]) for r in pgq.q("""SELECT date::text FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='BBCA'
        AND timeframe='Daily' AND is_final ORDER BY 1""")['rows']]
last60 = set(bbca[-60:])
today = datetime.now(timezone.utc).astimezone(price.JAKARTA).date()
report = []
ws = price.open_socket(90, False)
try:
    session = price.start_chart_session(ws)
    for i, (code, kind) in enumerate(codes, 1):
        sym = price.Symbol(i, code, code, f'IDX:{code}', 'IDX', 'stock')
        try:
            rows = price.request_symbol(ws, session, sym, 5000, 90, today)
        except Exception as e:  # noqa: BLE001
            report.append({'code': code, 'kind': kind, 'error': type(e).__name__ + ': ' + str(e)[:120]}); continue
        dates = {r['date'] for r in rows}
        if not dates:
            report.append({'code': code, 'kind': kind, 'bars': 0}); continue
        first, last = min(dates), max(dates)
        life = [d for d in bbca if first <= d <= last]
        report.append({'code': code, 'kind': kind, 'bars': len(rows), 'first': first.isoformat(), 'last': last.isoformat(),
                       'life_sessions': len(life), 'life_missing': sum(d not in dates for d in life),
                       'zero_volume': sum((r['volume'] or 0) == 0 for r in rows),
                       'last60_missing': sum(d not in dates for d in last60 if d >= first),
                       'extra_vs_bbca': sum(d not in set(bbca) for d in dates)})
        print(json.dumps(report[-1]), flush=True)
        time.sleep(0.3)
finally:
    ws.close()
(out / 'probe.json').write_text(json.dumps(report, indent=1))
