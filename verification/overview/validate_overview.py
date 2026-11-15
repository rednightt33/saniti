"""EXEC-OVERVIEW O6: independent recalculation of the Market Overview files against dev (read-only, pgweb).

Written from OVERVIEW_FORMULAS.md, not from apps/terminal-publisher/overview.py: its own SQL and its own arithmetic.
For each chosen date it recomputes from the source tables and compares with the files:
  meta     the common stocks (name, sector; "Undefined" -> "Other"), the 11 sectors, every stock list's members, the
           price and broker dates, the 20 picker dates;
  day      IHSG and LQ45 OHLC and prior close, breadth, the broker date, turnover and its 20-date average and ratio,
           foreign net 1D and 10D, the four flow periods, the 20-day volatility and its rank in its own 252 values,
           every stock's close, 1D/5D/1M return, EMA50/EMA200 flag, size (20 market sessions of close x volume / 20)
           and Regular foreign net 1D/5D/20D/60D, the 5-minute and 1-hour IHSG bars;
  series   the closes of IHSG, LQ45 and the sector indexes, % above EMA50/EMA200 and the market flow on that date.
With --page URL it also opens the page (the fixture or a served build showing these files) and compares what it shows
in its default view (LQ45, 1D, newest date) with values computed here: the KPI strip, the Financials heading of the
market map, Top Movers and the Foreign Flow lists.

  python3 verification/overview/validate_overview.py DIR [--dates D1,D2,D3] [--page URL] [--out report.json]
DIR holds overview-meta.json, overview-series.json and overview-day-<date>.json (decoded JSON). Exit 0 when nothing
differs."""
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/terminal_api'))
from pgq import q  # noqa: E402

STOCK = '(SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\')'
DIFFS, CHECKED = [], [0]


def rows(sql):
    r = q(sql)
    if 'error' in r:
        raise SystemExit(f'pgweb refused: {str(r["error"])[:300]}\n{sql[:300]}')
    return r['rows']


def f(v):
    return None if v is None else float(v)


def same(where, got, want, tol=0.0):
    """Record one comparison; numbers within tol (the files round), None only equals None."""
    CHECKED[0] += 1
    if isinstance(want, float) or isinstance(got, float):
        ok = (got is None and want is None) or (got is not None and want is not None and abs(float(got) - float(want)) <= tol + 1e-9)
    else:
        ok = got == want
    if not ok:
        DIFFS.append(f'{where}: file {got!r}, dev {want!r}')
    return ok


def lit(d):
    return "'" + d + "'"


def ihsg_dates(upto, n):
    return [r[0] for r in rows("SELECT date::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' "
                               f"AND timeframe = 'Daily' AND is_final AND date <= {lit(upto)} ORDER BY date DESC LIMIT {n}")][::-1]


def check_meta(meta):
    st = rows('SELECT "Ticker", "Company Name", "Sector" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\' ORDER BY 1')
    sectors = rows("SELECT ticker, sector FROM public.\"Feature_Index_Entity\" WHERE entity_kind = 'SECTOR' ORDER BY sector")
    known = {s for _, s in sectors}
    same('meta.stocks.ticker', meta['stocks']['ticker'], [r[0] for r in st])
    same('meta.stocks.name', meta['stocks']['name'], [r[1] for r in st])
    same('meta.stocks.sector', meta['stocks']['sector'], [r[2] if r[2] in known else 'Other' for r in st])
    same('meta.sectors', [(s['name'], s['index']) for s in meta['sectors']], [(s, t) for t, s in sectors] + [('Other', None)])
    mem = {}
    for k, t in rows('SELECT m.list_key, m."Ticker" FROM public."Stock_List_Member" m JOIN public."Stock_List" l '
                     'ON l.list_key = m.list_key WHERE l.is_enabled'):
        mem.setdefault(k, set()).add(t)
    enabled = {r[0] for r in rows('SELECT list_key FROM public."Stock_List" WHERE is_enabled')}
    same('meta.lists keys', sorted(l['key'] for l in meta['lists']), sorted(enabled))
    for l in meta['lists']:
        same(f'meta.lists[{l["key"]}].members', sorted(l['members']), sorted(mem.get(l['key'], set())))
    same('meta.prices_through', meta['prices_through'], ihsg_dates('9999-12-31', 1)[0])
    same('meta.broker_through', meta['broker_through'], rows("SELECT max(trade_date)::text FROM public.\"Feature_06_Foreign_Domestic_INDEX\" "
                                                             "WHERE ticker = 'IHSG' AND market_board = 'Regular'")[0][0])
    recent = ihsg_dates('9999-12-31', 40)
    with_f01 = {r[0] for r in rows('SELECT DISTINCT date::text FROM public."Feature_01_Stock_Daily" WHERE date >= ' + lit(recent[0]))}
    same('meta.dates', meta['dates'], [d for d in recent if d in with_f01][-20:])


def flow_rows(upto):
    return [(d, f(b), f(s), f(db)) for d, b, s, db in rows(
        'SELECT trade_date::text, foreign_buy_1d, foreign_sell_1d, domestic_buy_1d FROM public."Feature_06_Foreign_Domestic_INDEX" '
        f"WHERE ticker = 'IHSG' AND market_board = 'Regular' AND trade_date <= {lit(upto)} ORDER BY 1 DESC LIMIT 61")][::-1]


def vol_and_rank(closes):
    """20-day volatility of the last close and the % of the 252 previous values strictly below it."""
    def v(k):
        r = [closes[j] / closes[j - 1] - 1 for j in range(k - 19, k + 1)]
        return statistics.stdev(r) * math.sqrt(252) * 100
    e = len(closes) - 1
    now = v(e)
    hist = [v(k) for k in range(e - 252, e)]
    return now, 100 * sum(1 for h in hist if h < now) / 252


def check_day(meta, day, series, d):
    w = f'day {d}'
    sess = ihsg_dates(d, 273)
    same(f'{w}.prior_date', day['prior_date'], sess[-2])
    for t in ('IHSG', 'LQ45'):
        o = rows(f'SELECT date::text, open, high, low, close FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = {lit(t)} '
                 f"AND timeframe = 'Daily' AND is_final AND date IN ({lit(sess[-2])}, {lit(d)}) ORDER BY 1")
        by = {r[0]: r for r in o}
        for k, col in (('open', 1), ('high', 2), ('low', 3), ('close', 4)):
            same(f'{w}.index.{t}.{k}', day['index'][t].get(k), f(by[d][col]), 0.005)
        same(f'{w}.index.{t}.prior_close', day['index'][t]['prior_close'], f(by[sess[-2]][4]), 0.005)
    up, down, flat = rows(f'SELECT count(*) FILTER (WHERE return_1d_pct > 0), count(*) FILTER (WHERE return_1d_pct < 0), '
                          f'count(*) FILTER (WHERE return_1d_pct = 0) FROM public."Feature_01_Stock_Daily" WHERE date = {lit(d)} AND ticker IN {STOCK}')[0]
    same(f'{w}.breadth', [day['breadth'][k] for k in ('advancers', 'decliners', 'unchanged')], [int(up), int(down), int(flat)])
    # volatility from the IHSG closes
    closes = [f(r[0]) for r in rows("SELECT close FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' AND timeframe = 'Daily' "
                                    f'AND is_final AND date <= {lit(d)} ORDER BY date DESC LIMIT 273')][::-1]
    v, rank = vol_and_rank(closes)
    same(f'{w}.volatility.value', day['volatility']['value'], v, 5e-5)
    same(f'{w}.volatility.rank_1y', day['volatility']['rank_1y'], rank, 0.005)
    # the market at the broker date
    fl = flow_rows(d)
    b = fl[-1][0]
    m = day['market']
    same(f'{w}.market.date', m['date'], b)
    to = lambda r: r[1] + r[3]
    same(f'{w}.market.turnover', m['turnover'], to(fl[-1]), 0.5)
    avg = sum(to(r) for r in fl[-21:-1]) / 20
    same(f'{w}.market.turnover_avg20', m['turnover_avg20'], avg, 0.5)
    same(f'{w}.market.turnover_ratio', m['turnover_ratio'], to(fl[-1]) / avg, 5e-5)
    same(f'{w}.market.foreign_net_1d', m['foreign_net_1d'], fl[-1][1] - fl[-1][2], 0.5)
    same(f'{w}.market.foreign_net_10d', m['foreign_net_10d'], sum(r[1] - r[2] for r in fl[-10:]), 0.5)
    for p, n in (('1D', 1), ('5D', 5), ('1M', 20), ('3M', 60)):
        part = fl[-n:]
        got = m['periods'][p]
        same(f'{w}.market.periods.{p}', (got['from'], got['buy'], got['sell'], got['net']),
             (part[0][0], round(sum(r[1] for r in part)), round(sum(r[2] for r in part)), round(sum(r[1] - r[2] for r in part))))
    # every stock
    tick = meta['stocks']['ticker']
    f01 = {r[0]: r for r in rows(f'SELECT ticker, close, return_1d_pct, return_5d_pct, return_20d_pct FROM public."Feature_01_Stock_Daily" '
                                 f'WHERE date = {lit(d)} AND ticker IN {STOCK}')}
    ema = {r[0]: r for r in rows(f'SELECT ticker, close > ema_50, close > ema_200 FROM public."Feature_04_Technical_Indicator" '
                                 f"WHERE trade_date = {lit(d)} AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK}")}
    twenty = ','.join(lit(x) for x in sess[-20:])
    size = {r[0]: f(r[1]) for r in rows(f'SELECT ticker, sum(close * volume) / 20 FROM public."Price_Stock_Indonesia_IDX" '
                                        f"WHERE date IN ({twenty}) AND timeframe = 'Daily' AND is_final AND volume IS NOT NULL "
                                        'GROUP BY ticker HAVING sum(close * volume) > 0')}
    fn = {r[0]: r for r in rows(f'SELECT ticker, foreign_net_1d, foreign_net_5d, foreign_net_20d, foreign_net_60d FROM '
                                f"public.\"Feature_06_Foreign_Domestic\" WHERE trade_date = {lit(b)} AND market_board = 'Regular' AND ticker IN {STOCK}")}
    s = day['stocks']
    same(f'{w}.stocks (who)', sorted(tick[i] for i in s['i']), sorted(f01))
    flag = lambda v: None if v is None else int(bool(v))
    for k, i in enumerate(s['i']):
        t = tick[i]
        r = f01[t]
        for key, col, tol in (('close', 1, 0.005), ('r1d', 2, 5e-5), ('r5d', 3, 5e-5), ('r1m', 4, 5e-5)):
            same(f'{w}.{t}.{key}', s[key][k], f(r[col]), tol)
        same(f'{w}.{t}.above_ema50', s['above_ema50'][k], flag(ema[t][1]) if t in ema else None)
        same(f'{w}.{t}.above_ema200', s['above_ema200'][k], flag(ema[t][2]) if t in ema else None)
        same(f'{w}.{t}.size', s['size'][k], size.get(t), 0.5)
        for key, col in (('fnet_1d', 1), ('fnet_5d', 2), ('fnet_1m', 3), ('fnet_3m', 4)):
            same(f'{w}.{t}.{key}', s[key][k], f(fn[t][col]) if t in fn else None, 0.5)
    # IHSG bars
    for tf, lo in (('5m', d), ('1h', sess[-5])):
        bars = rows(f'SELECT extract(epoch FROM bar_time)::bigint, close FROM public.price_stock_idx_intraday WHERE ticker = \'IHSG\' '
                    f"AND timeframe = '{tf}' AND session_date BETWEEN {lit(lo)} AND {lit(d)} ORDER BY bar_time")
        same(f'{w}.intraday.{tf}.t', day['intraday'][tf]['t'], [int(r[0]) for r in bars])
        same(f'{w}.intraday.{tf}.c', [round(x, 2) for x in day['intraday'][tf]['c']], [round(f(r[1]), 2) for r in bars])
    # the series on that date
    e = series['dates'].index(d)
    for t, closes_ in (('IHSG', series['index']['IHSG']), ('LQ45', series['index']['LQ45'])):
        same(f'series {d}.index.{t}', closes_[e], f(day['index'][t]['close']), 0.005)
    sec = {r[0]: f(r[1]) for r in rows(f'SELECT e.sector, p.close FROM public."Feature_Index_Entity" e JOIN public."Price_Stock_Indonesia_IDX" p '
                                       f"ON p.ticker = e.ticker AND p.timeframe = 'Daily' AND p.is_final AND p.date = {lit(d)} WHERE e.entity_kind = 'SECTOR'")}
    for name, c in series['sector'].items():
        same(f'series {d}.sector.{name}', c[e], sec.get(name), 0.005)
    n50, a50, n200, a200 = rows(f'SELECT count(ema_50), count(*) FILTER (WHERE close > ema_50), count(ema_200), '
                                f'count(*) FILTER (WHERE close > ema_200) FROM public."Feature_04_Technical_Indicator" WHERE trade_date = {lit(d)} '
                                f"AND timeframe = 'Daily' AND asset_type = 'equity' AND ticker IN {STOCK}")[0]
    same(f'series {d}.above_ema50', series['above_ema50'][e], 100 * int(a50) / int(n50), 0.005)
    same(f'series {d}.above_ema200', series['above_ema200'][e], 100 * int(a200) / int(n200), 0.005)
    same(f'series {d}.breadth_n', series['breadth_n'][e], [int(n50), int(n200)])
    k = series['flow']['dates'].index(b)
    same(f'series flow {b}', (series['flow']['foreign_buy'][k], series['flow']['foreign_sell'][k], series['flow']['turnover'][k]),
         (round(fl[-1][1]), round(fl[-1][2]), round(to(fl[-1]))))


def expected_page(meta, d):
    """What the page's default view (LQ45, 1D) must show on date d, computed here from dev."""
    lq = {r[0] for r in rows("SELECT m.\"Ticker\" FROM public.\"Stock_List_Member\" m JOIN public.\"Stock_List\" l ON l.list_key = m.list_key "
                             "WHERE l.is_enabled AND l.list_kind = 'INDEX' AND l.code = 'LQ45'")}
    f01 = {r[0]: f(r[1]) for r in rows(f'SELECT ticker, return_1d_pct FROM public."Feature_01_Stock_Daily" WHERE date = {lit(d)} AND ticker IN {STOCK}')}
    sess = ihsg_dates(d, 20)
    twenty = ','.join(lit(x) for x in sess)
    size = {r[0]: f(r[1]) for r in rows(f'SELECT ticker, sum(close * volume) / 20 FROM public."Price_Stock_Indonesia_IDX" '
                                        f"WHERE date IN ({twenty}) AND timeframe = 'Daily' AND is_final AND volume IS NOT NULL "
                                        'GROUP BY ticker HAVING sum(close * volume) > 0')}
    sector = dict(zip(meta['stocks']['ticker'], meta['stocks']['sector']))
    ret = {t: round(f01[t], 4) for t in lq if t in f01 and f01[t] is not None}
    up = sorted((t for t in ret if ret[t] > 0), key=lambda t: (-ret[t], t))[:5]
    down = sorted((t for t in ret if ret[t] < 0), key=lambda t: (-ret[t], t))[-5:]
    fin = [t for t in ret if sector.get(t) == 'Financials' and size.get(t)]
    w = sum(round(size[t]) * ret[t] for t in fin) / sum(round(size[t]) for t in fin)
    b = flow_rows(d)[-1][0]
    fn = {r[0]: f(r[1]) for r in rows(f'SELECT ticker, foreign_net_1d FROM public."Feature_06_Foreign_Domestic" WHERE trade_date = {lit(b)} '
                                      f"AND market_board = 'Regular' AND ticker IN {STOCK}")}
    buy = sorted((t for t in fn if fn[t] and fn[t] > 0), key=lambda t: (-fn[t], t))[:4]
    sell = sorted((t for t in fn if fn[t] and fn[t] < 0), key=lambda t: (fn[t], t))[:4]
    return {'movers_up': up, 'movers_down': down, 'financials': w, 'ff_buy': buy, 'ff_sell': sell, 'universe': len(lq)}


def check_page(url, meta, day):
    from playwright.sync_api import sync_playwright
    want = expected_page(meta, day['date'])
    pct = lambda v: ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.2f}%'
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
        p = br.new_page(viewport={'width': 1440, 'height': 1100})
        p.goto(url, wait_until='networkidle')
        p.wait_for_selector('body[data-ready="1"]')
        p.wait_for_timeout(500)
        got = p.evaluate("""() => ({
          kpis: [...document.querySelectorAll('#kpis .k .v')].map(e => e.textContent),
          up: [...document.querySelectorAll('#tmvb .tmv-g:first-child .tmv-r .tk')].map(e => e.textContent),
          down: [...document.querySelectorAll('#tmvb .tmv-g:last-child .tmv-r .tk')].map(e => e.textContent),
          heads: Object.fromEntries([...document.querySelectorAll('#tm .sh')].map(e => [e.firstChild.textContent, e.querySelector('i')?.textContent])),
          buy: [...document.querySelectorAll('#ffb .ff-r > .tk:not(.r)')].map(e => e.textContent).filter(Boolean),
          sell: [...document.querySelectorAll('#ffb .ff-r > .tk.r')].map(e => e.textContent).filter(Boolean),
          date: document.querySelector('#dlab').textContent })""")
        br.close()
    m = day['market']
    rp = lambda v, signed=False: (('+' if v > 0 else '−' if v < 0 else '') if signed else '') + 'Rp ' + (
        f'{abs(v) / 1e12:.2f}T' if abs(v) >= 1e12 else f'{abs(v) / 1e9:.1f}B')
    vol = day['volatility']['value']
    same('page KPI strip', got['kpis'], [f"{day['index']['IHSG']['close']:,.2f}", f"{day['index']['LQ45']['close']:,.2f}",
                                         f"{day['breadth']['advancers']} / {day['breadth']['decliners']}", rp(m['turnover']),
                                         rp(m['foreign_net_1d'], True), f'{vol:.1f}%'])
    same('page Top Movers up', got['up'], want['movers_up'])
    same('page Top Movers down', got['down'], want['movers_down'])
    same('page map heading Financials', got['heads'].get('Financials'), pct(want['financials']))
    same('page Foreign Flow buy', got['buy'], want['ff_buy'])
    same('page Foreign Flow sell', got['sell'], want['ff_sell'])
    print(f"page {got['date']}: KPI strip, LQ45 Top Movers ({len(got['up'])} up, {len(got['down'])} down), Financials "
          f"heading {got['heads'].get('Financials')}, Foreign Flow {len(got['buy'])} buy / {len(got['sell'])} sell compared")
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--dates', default='')
    ap.add_argument('--page', default='')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    d = Path(a.dir)
    meta = json.loads((d / 'overview-meta.json').read_text())
    series = json.loads((d / 'overview-series.json').read_text())
    dates = a.dates.split(',') if a.dates else [meta['dates'][1], meta['dates'][len(meta['dates']) // 2], meta['dates'][-1]]
    check_meta(meta)
    for x in dates:
        before = len(DIFFS)
        check_day(meta, json.loads((d / f'overview-day-{x}.json').read_text()), series, x)
        print(f'{x}: {len(DIFFS) - before} differences')
    if a.page:
        check_page(a.page, meta, json.loads((d / f'overview-day-{meta["dates"][-1]}.json').read_text()))
    for x in DIFFS[:40]:
        print('DIFF', x)
    print(f'OVERVIEW_VALIDATION {"OK" if not DIFFS else "DIFFERS"}: {CHECKED[0]} comparisons, {len(DIFFS)} differences, dates {", ".join(dates)}')
    if a.out:
        Path(a.out).write_text(json.dumps({'dates': dates, 'checked': CHECKED[0], 'differences': DIFFS}, indent=1))
    return 1 if DIFFS else 0


if __name__ == '__main__':
    raise SystemExit(main())
