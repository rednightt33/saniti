"""Fetch the parity inputs of tests/calc from the live database (read-only).

For each ticker: final daily OHLCV from public."Price_Stock_Indonesia_IDX" (full history from the
first price row) and the stored Feature 04 values (public."Feature_04_Technical_Indicator", or
"_INDEX" for IHSG), written to <out>/<TICKER>.json.gz. gen_talib.py and gen_html.mjs then add their
sections to the same files.

Run from the repository root (uses verification/terminal_api/pgq.py, which reads the pgweb login
from Railway; nothing secret is written):
  python3 apps/edge-bff/terminal/tests/calc/tools/fetch_live.py --out apps/edge-bff/terminal/tests/calc/fixtures \
      BBCA GOTO IHSG KOCI ISEA UNVR DEWI CLAY
Random tickers: random.Random(20261025).sample(<842 tickers with prices and Feature 04, minus BBCA/GOTO>, 20)
= KOCI ISEA UNVR DEWI CLAY SHIP STAR PBID LION AYAM YPAS KEJU INOV BPFI TRST SMDR BNBR ASBI IBOS LFLO;
the first five are committed, all twenty were run once (PARITY.md).
"""
import argparse, datetime, gzip, json, os, sys

sys.path.insert(0, os.path.join(os.getcwd(), 'verification', 'terminal_api'))
import pgq  # noqa: E402

F04 = ['sma_20', 'sma_50', 'ema_12', 'ema_26', 'ema_50', 'ema_200', 'rsi_14', 'macd', 'macd_signal',
       'macd_histogram', 'atr_14', 'bb_upper_20', 'bb_middle_20', 'bb_lower_20', 'adx_14']


def rows(sql):
    r = pgq.q(sql)
    if 'error' in r:
        raise SystemExit(r['error'])
    return r['rows']


def series(values):
    """Leading nulls dropped: {"s": first index, "v": values from there on}."""
    s = next((i for i, v in enumerate(values) if v is not None), len(values))
    return {'s': s, 'v': values[s:]}


def fetch(ticker):
    assert ticker.isalnum() and ticker.isupper()
    price = rows(f"""select date::text, open::float8, high::float8, low::float8, close::float8, volume::float8
        from public."Price_Stock_Indonesia_IDX" where ticker = '{ticker}' and timeframe = 'Daily' and is_final order by date""")
    table = 'Feature_04_Technical_Indicator_INDEX' if ticker == 'IHSG' else 'Feature_04_Technical_Indicator'
    f04 = rows(f"""select trade_date::text, calculation_version, {', '.join(F04)} from public."{table}"
        where ticker = '{ticker}' and timeframe = 'Daily' order by trade_date""")
    dates = [r[0] for r in price]
    if [r[0] for r in f04] != dates:
        raise SystemExit(f'{ticker}: Feature 04 dates differ from the price dates')
    out = {'ticker': ticker, 'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'feature04_version': sorted({r[1] for r in f04}), 'T': dates}
    for k, j in zip('OHLCV', range(1, 6)):
        out[k] = [r[j] for r in price]
    out['f04'] = {c: series([r[2 + i] for r in f04]) for i, c in enumerate(F04)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('tickers', nargs='+')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for t in a.tickers:
        d = fetch(t)
        with gzip.open(os.path.join(a.out, f'{t}.json.gz'), 'wt') as f:
            json.dump(d, f, separators=(',', ':'))
        print(t, len(d['T']), 'bars', d['T'][0], '..', d['T'][-1], d['feature04_version'])


if __name__ == '__main__':
    main()
