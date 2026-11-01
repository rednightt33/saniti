"""Fixed-income data quality audit (user 2026-11-01: "bisa dilakukan audit dulu, to ensure data quality-nya benar, dan bisa
dilakukan sampling, gunakan script yang digunakan untuk ingest baik price dan yield ke database ... price dan yield itu
tidak semuanya tanggalnya ada ... Siapkan mitigasinya").

Read-only. For every series of Universe_Fixed_income (48: 24 instruments x price and yield):
  1. the database rows of Price_Fixed_Income (1D, through pgweb, read-only);
  2. the source history pulled again with the ingest's own client (apps/fixed-income-price-cron/fixed_income_update.py:
     open_socket, start_chart_session, request_series, the market's source_date_mapping, provider timezone and session
     checks), up to 5000 daily bars;
  3. per date, on the source's session dates (session_date: the label read in the provider's zone against the market's
     provider_session), values equal, dates only in the database, dates only in the source (inside the database's
     range); and how many of the live loader's dates (fixed_income_update.resolve_bar_date with the market's
     source_date_mapping) differ from them;
  4. database checks: OHLC order, weekends, flat bars (O=H=L=C), runs of an unchanged close, day-over-day moves;
  5. price vs yield of the same instrument: dates with only one of them, and whether they move the opposite way.
Writes out/<series>.json and out/summary.json; prints one line per series. No database write.

  RAILWAY_TOKEN=... python verification/fixed_income_audit/audit.py
"""
import json, sys, time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/fixed-income-price-cron'))
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
import fixed_income_update as f  # noqa: E402  (the ingest client)
import pgq  # noqa: E402

OUT = Path(__file__).resolve().parent / 'out'


def session_date(label, provider_tz, provider_session):
    """The trading date a daily bar belongs to, from its raw label (the session's start in the provider's zone,
    Fixed_Income_Market_Schedule.provider_session 'HHMM-HHMM'): a label at or after the session start opens the next
    day's session; weekends roll forward. Independent of daylight saving (US labels are 19:00 New York: 23:00 UTC in
    EDT, 00:00 UTC of the trading day in EST)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    local = label.astimezone(ZoneInfo(provider_tz))
    start = int(provider_session[:2]) * 60 + int(provider_session[2:4])
    d = local.date() + timedelta(days=1) if local.hour * 60 + local.minute >= start else local.date()
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d
OUT.mkdir(exist_ok=True)


def rows(sql):
    r = pgq.q(sql)
    if 'error' in r:
        raise RuntimeError(r['error'][:300])
    return r['rows']


universe = rows('SELECT country, instrument_name, ticker, tradingview_symbol, metric_type, value_unit '
                'FROM public."Universe_Fixed_income" ORDER BY country, ticker, metric_type')
schedule = {r[0]: r for r in rows('SELECT country, market_code, source_date_mapping, provider_timezone_name, provider_session '
                                   'FROM public."Fixed_Income_Market_Schedule"')}
summary = []
ws = f.open_socket(30, False)
cs = f.start_chart_session(ws)
now = datetime.now(timezone.utc)
for k, (country, name, ticker, symbol, metric, unit) in enumerate(universe, 1):
    _, market, mapping, ptz, psess = schedule[country]
    s = f.Series(k, country, name, ticker, symbol, metric, unit)
    for attempt in range(3):
        try:
            src, tz = f.request_series(ws, cs, s, 5000, 90, date.today(), date.today(), now, now, mapping, ptz, psess)
            break
        except Exception as e:  # noqa: BLE001 - a dropped socket is opened again
            if attempt == 2:
                raise
            try: ws.close()
            except Exception: pass
            time.sleep(3); ws = f.open_socket(30, False); cs = f.start_chart_session(ws)
    # the live loader's dates (v4: source_date_mapping) and the session dates; the comparison uses the session dates
    v4_dates = [r['date'].isoformat() for r in src]
    v4_collisions = len(v4_dates) - len(set(v4_dates))
    v4_wrong = sum(1 for r in src if r['date'] != session_date(r['source_bar_time'], tz, psess))
    source = {}
    for r in src:
        source[session_date(r['source_bar_time'], tz, psess).isoformat()] = (
            float(r['open']), float(r['high']), float(r['low']), float(r['close']), r['source_bar_time'].isoformat())
    db = {d: (float(o), float(h), float(l), float(c), sbt, fin, tf) for d, o, h, l, c, sbt, fin, tf in rows(
        f"""SELECT date::text, open::float8, high::float8, low::float8, close::float8, source_bar_time::text, is_final, "Timeframe"
            FROM public."Price_Fixed_Income" WHERE tradingview_symbol = '{symbol}' AND metric_type = '{metric}' ORDER BY date""")}
    d1 = {d: v for d, v in db.items() if v[6] == '1D'}
    lo, hi = (min(d1), max(d1)) if d1 else (None, None)
    both = sorted(set(d1) & set(source))
    tol = lambda a, b: abs(a - b) <= max(1e-9, abs(b) * 1e-9)
    diff = [d for d in both if not all(tol(d1[d][i], source[d][i]) for i in range(4))]
    close_diff = [d for d in both if not tol(d1[d][3], source[d][3])]
    db_only = sorted(set(d1) - set(source))
    src_only = sorted(d for d in source if lo and lo <= d <= hi and d not in d1)
    after = sorted(d for d in source if hi and d > hi)
    dates = sorted(d1)
    closes = [d1[d][3] for d in dates]
    flat = [d for d in dates if d1[d][0] == d1[d][1] == d1[d][2] == d1[d][3]]
    weekend = [d for d in dates if date.fromisoformat(d).weekday() >= 5]
    bad_ohlc = [d for d in dates if not (d1[d][2] <= min(d1[d][0], d1[d][3]) and max(d1[d][0], d1[d][3]) <= d1[d][1])]
    nonfinal = [d for d in dates if not d1[d][5]]
    run, longest, at = 1, 1, None
    for i in range(1, len(closes)):
        run = run + 1 if closes[i] == closes[i - 1] else 1
        if run > longest: longest, at = run, dates[i]
    moves = sorted(((abs(closes[i] - closes[i - 1]), dates[i], closes[i - 1], closes[i]) for i in range(1, len(closes))), reverse=True)[:5]
    flat_db_only = [d for d in db_only if d in flat]
    res = {'country': country, 'ticker': ticker, 'symbol': symbol, 'metric': metric, 'unit': unit, 'provider_tz': tz,
           'db_rows': len(d1), 'db_first': lo, 'db_last': hi, 'source_rows': len(source),
           'source_first': min(source) if source else None, 'source_last': max(source) if source else None,
           'matched_dates': len(both), 'value_mismatch': len(diff), 'close_mismatch': len(close_diff),
           'mismatch_samples': [{'date': d, 'db': d1[d][:4], 'source': source[d][:4]} for d in diff[:8]],
           'db_only': len(db_only), 'db_only_samples': db_only[:12], 'db_only_flat': len(flat_db_only),
           'v4_dates_differing_from_session_dates': v4_wrong, 'v4_date_collisions': v4_collisions,
           'source_only_in_range': len(src_only), 'source_only_samples': src_only[:12], 'source_after_db_last': after,
           'flat_bars': len(flat), 'weekend_rows': weekend[:5], 'bad_ohlc': bad_ohlc[:5], 'non_final': len(nonfinal),
           'other_timeframes': sorted({v[6] for v in db.values()} - {'1D'}),
           'longest_unchanged_close_run': [longest, at], 'largest_moves': moves}
    (OUT / f'{ticker}_{metric}.json').write_text(json.dumps(res, indent=1, default=str))
    summary.append(res)
    print(json.dumps({k2: res[k2] for k2 in ('ticker', 'metric', 'db_rows', 'source_rows', 'matched_dates', 'close_mismatch',
                                             'value_mismatch', 'db_only', 'db_only_flat', 'source_only_in_range', 'flat_bars',
                                             'v4_dates_differing_from_session_dates', 'v4_date_collisions')}), flush=True)
    time.sleep(0.3)
ws.close()

# price vs yield of the same instrument (database dates)
pairs = []
by = {}
for r in summary:
    by.setdefault(r['ticker'], {})[r['metric']] = r
for ticker, m in sorted(by.items()):
    if set(m) != {'price', 'yield_to_maturity'}:
        continue
    p = json.loads((OUT / f'{ticker}_price.json').read_text()); y = json.loads((OUT / f'{ticker}_yield_to_maturity.json').read_text())
    pd = {x[0] for x in rows(f"""SELECT date::text FROM public."Price_Fixed_Income" WHERE ticker = '{ticker}' AND metric_type = 'price' AND "Timeframe" = '1D'""")}
    yd = {x[0] for x in rows(f"""SELECT date::text FROM public."Price_Fixed_Income" WHERE ticker = '{ticker}' AND metric_type = 'yield_to_maturity' AND "Timeframe" = '1D'""")}
    common = sorted(pd & yd)
    pc = dict(map(tuple, rows(f"""SELECT date::text, close::float8 FROM public."Price_Fixed_Income" WHERE ticker = '{ticker}' AND metric_type = 'price' AND "Timeframe" = '1D'""")))
    yc = dict(map(tuple, rows(f"""SELECT date::text, close::float8 FROM public."Price_Fixed_Income" WHERE ticker = '{ticker}' AND metric_type = 'yield_to_maturity' AND "Timeframe" = '1D'""")))
    same = opp = flat = 0
    for a, b in zip(common, common[1:]):
        dp, dy = pc[b] - pc[a], yc[b] - yc[a]
        if dp == 0 or dy == 0: flat += 1
        elif (dp > 0) == (dy > 0): same += 1
        else: opp += 1
    only_p, only_y = sorted(pd - yd), sorted(yd - pd)
    pairs.append({'ticker': ticker, 'price_unit': m['price']['unit'], 'price_dates': len(pd), 'yield_dates': len(yd), 'both': len(common),
                  'price_only': len(only_p), 'price_only_samples': only_p[:10], 'price_only_first': only_p[0] if only_p else None,
                  'price_only_last': only_p[-1] if only_p else None,
                  'yield_only': len(only_y), 'yield_only_samples': only_y[:10], 'yield_only_first': only_y[0] if only_y else None,
                  'yield_only_last': only_y[-1] if only_y else None,
                  'moves_opposite': opp, 'moves_same_direction': same, 'one_unchanged': flat})
    print(json.dumps({k2: pairs[-1][k2] for k2 in ('ticker', 'price_unit', 'price_dates', 'yield_dates', 'both', 'price_only', 'yield_only',
                                                    'moves_opposite', 'moves_same_direction')}), flush=True)
(OUT / 'summary.json').write_text(json.dumps({'series': summary, 'pairs': pairs, 'run_at': now.isoformat()}, indent=1, default=str))
print('AUDIT_DONE', len(summary), 'series', len(pairs), 'pairs')
