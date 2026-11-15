"""EXEC-INDEX-GROUP-HISTORY stage 3 (user go 2026-11-15: "go langkah 3"): daily TradingView history of the 43 priced
entities of Feature_Index_Entity (32 Stockbit indexes, 11 IDX sector indexes) into Price_Stock_Indonesia_IDX, one ticker
at a time with scripts/backfill_idx_price_ticker.py (unchanged: index OHLC without volume, dates against the BBCA
calendar, never overwrites a stored row, the price run lock), on orc-test-runner. The pattern of
verification/universe_63/backfill_job.py.

The tickers are derived, not listed: Feature_Index_Entity has_price, not IHSG (its history is stored), read at run time.
One rule is added for an index: the script accepts a BBCA session without a bar as "no trade" when the broker summary
shows no buy of the ticker, which is always true for an index (it has no broker rows). So the job checks completeness
itself: from the index's first bar to `end`, the bars must equal the BBCA sessions (no gap in the middle), the last bar
must be `end` and there are no extra dates. A ticker that fails it is reported and never applied.

params.json: {"mode": "PREFLIGHT" | "APPLY", "start": "2018-01-02", "end": "2026-11-13",
              "fingerprints": {ticker: sha256} (APPLY: the reviewed preflight's; only these tickers are applied)}
Prints one RESULT line per ticker, a SUMMARY line and JOB_DONE."""
import json
import os
import subprocess
import sys
import time

import psycopg

p = json.load(open('params.json'))
mode = p['mode']
assert mode in ('PREFLIGHT', 'APPLY'), mode
start, end = p['start'], p['end']


def bbca_sessions(db, first, last):
    """BBCA's final Daily sessions from first to last: the calendar the script compares against."""
    return db.execute('''SELECT count(*) FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = 'BBCA'
                         AND timeframe = 'Daily' AND is_final AND date BETWEEN %s AND %s''', (first, last)).fetchone()[0]


with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, application_name='index-price-history') as db:
    db.execute('SET default_transaction_read_only = on')
    derived = [r[0] for r in db.execute('''SELECT e.ticker FROM public."Feature_Index_Entity" e
        WHERE e.has_price AND e.ticker <> 'IHSG' AND public.is_universe_index(e.ticker) ORDER BY e.ticker''')]
    tickers = derived if mode == 'PREFLIGHT' else sorted(p['fingerprints'])
    unknown = sorted(set(tickers) - set(derived))
    assert not unknown, f'not priced entities of Feature_Index_Entity: {unknown}'
    print('TICKERS ' + json.dumps({'mode': mode, 'count': len(tickers), 'tickers': tickers}), flush=True)
    results = []
    for ticker in tickers:
        env = {**os.environ, 'TICKER': ticker, 'START_DATE': start, 'END_DATE': end,
               'ACCEPTED_EXTRA_DATES': '[]', 'ACCEPTED_MISSING_DATES': '[]'}
        if mode == 'APPLY':
            env.update(ACTION='apply', EXPECTED_FINGERPRINT=p['fingerprints'][ticker])
        started = time.monotonic()
        run = subprocess.run([sys.executable, 'scripts/backfill_idx_price_ticker.py'], env=env, capture_output=True,
                             text=True, timeout=600)
        events = []
        for line in run.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        pre = next((e for e in events if e.get('event') == 'history_preflight'), {})
        done = next((e for e in events if e.get('event') == 'history_committed'), None)
        error = (run.stderr.strip().splitlines() or [''])[-1][:300] if run.returncode else None
        sessions = bbca_sessions(db, pre['first'], pre['last']) if pre.get('first') else None
        complete = (run.returncode == 0 and sessions is not None and sessions == pre.get('selected_rows')
                    and pre.get('last') == end and not pre.get('extra_vs_bbca'))
        stored = None
        if done:
            stored = db.execute('''SELECT count(*), min(date)::text, max(date)::text, count(*) FILTER (WHERE volume IS NULL)
                FROM public."Price_Stock_Indonesia_IDX" WHERE ticker = %s AND timeframe = 'Daily' AND is_final''',
                                (ticker,)).fetchone()
        result = {'ticker': ticker, 'rc': run.returncode, 'seconds': round(time.monotonic() - started, 1),
                  'provider': pre.get('provider'), 'selected_rows': pre.get('selected_rows'), 'first': pre.get('first'),
                  'last': pre.get('last'), 'bbca_sessions_first_to_last': sessions,
                  'gap_in_history': (sessions - pre['selected_rows']) if sessions is not None else None,
                  'extra': pre.get('extra_vs_bbca'), 'complete': complete, 'fingerprint': pre.get('fingerprint'),
                  'committed': done, 'stored': stored, 'error': error}
        if mode == 'APPLY' and done and stored and stored[0] != sessions:
            result['readback_mismatch'] = True
        results.append(result)
        print('RESULT ' + json.dumps(result, default=str), flush=True)
        time.sleep(1)
summary = {'mode': mode, 'tickers': len(results), 'ok': sum(r['rc'] == 0 for r in results),
           'complete': sum(bool(r['complete']) for r in results),
           'incomplete': [r['ticker'] for r in results if not r['complete']],
           'rows_inserted': sum((r['committed'] or {}).get('inserted_rows', 0) for r in results),
           'readback_mismatch': [r['ticker'] for r in results if r.get('readback_mismatch')]}
print('SUMMARY ' + json.dumps(summary), flush=True)
print('VERDICT ' + ('PASS' if summary['ok'] == len(results) and not summary['incomplete'] and not summary['readback_mismatch']
                    else 'REVIEW'), flush=True)
print('JOB_DONE', mode, flush=True)
