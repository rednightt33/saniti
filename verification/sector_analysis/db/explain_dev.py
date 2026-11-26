"""EXEC-SECTOR-ANALYSIS S1: read-only EXPLAIN (ANALYZE, BUFFERS) on dev of the refresh's SELECT part and of the
publisher's reads, before the migration is applied (Feature_08_Group_Daily does not exist there yet).

The refresh's statement is cut from the migration file itself (from `WITH u AS MATERIALIZED` to the `agg` CTE, so the
measured text is the function's), with p_date, v_market and v_prev replaced by literals; the part that reads the
previous rows of Feature_08_Group_Daily (`lv`) is a primary-key lookup per group and cannot run before the table exists.
The publisher's reads come from apps/terminal-publisher/sector.py.

Run through a read-only pgweb connection (a module `pgx` with rows(sql) and q(sql), read-only role, 30 s statement
timeout): python explain_dev.py <out dir> <date> [<date> ...]. Writes one plan per query and date; prints the timings.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'apps/terminal-publisher'))
import sector  # noqa: E402

import pgx  # noqa: E402  (on PYTHONPATH: the read-only pgweb helper, outside the repository)

MIGRATION = (REPO / 'database/migrations/20261126_001_feature_08_group_daily.sql').read_text()


def refresh_select(date: str, prev: str) -> str:
    body = MIGRATION[MIGRATION.index('    WITH u AS MATERIALIZED ('):MIGRATION.index('    ), lv AS (')]
    body = body.replace('p_date', f"DATE '{date}'").replace('v_market', "'IHSG'::text").replace('v_prev', f"DATE '{prev}'")
    # feature_08_weight is created by the migration: its body (overview_stock_size) in its place
    body = re.sub(r'public\.feature_08_weight\(([^)]*)\)',
                  r'(SELECT s.ticker, s.size_value AS weight, s.size_basis AS weight_basis FROM public.overview_stock_size(\1) AS s)',
                  body)
    return body + '    )\n    SELECT * FROM agg'


def literal(sql: str, params) -> str:
    """The publisher's %s placeholders as SQL literals (read-only measurement only)."""
    out = []
    for p in params:
        if isinstance(p, (list, tuple)):
            out.append("ARRAY[" + ','.join(f"'{x}'" for x in p) + "]::text[]" if p else "ARRAY[]::text[]")
        elif p is None:
            out.append('NULL')
        else:
            out.append(f"'{p}'")
    return sql % tuple(out)


def explain(sql: str):
    r = pgx.q('EXPLAIN (ANALYZE, BUFFERS) ' + sql, timeout=200)
    if 'error' in r:
        return None, r['error']
    lines = [row[0] for row in r['rows']]
    return lines, None


def main(out_dir: str, dates: list[str]):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for d in dates:
        prev = pgx.rows("SELECT max(date)::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' "
                        f"AND timeframe = 'Daily' AND is_final AND date < DATE '{d}'")[0][0]
        series = [r[0] for r in pgx.rows("SELECT date::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' "
                                         f"AND timeframe = 'Daily' AND is_final AND date <= DATE '{d}' ORDER BY date DESC LIMIT 3")]
        tickers = [r[0] for r in pgx.rows('SELECT "Ticker" FROM public."IDX_Stock_Universe" WHERE "Security Type" = \'stock\' '
                                          'ORDER BY 1 LIMIT 50 OFFSET 400')]
        queries = {
            'refresh_select': refresh_select(d, prev),
            'day_rows': literal(sector.DAY_SQL, (d,)),
            'weights': literal(sector.WEIGHT_SQL.replace('public.feature_08_weight', 'public.overview_stock_size')
                               .replace('weight, weight_basis', 'size_value, size_basis'), (d,)),
            'fp_f04_window': literal(sector.FP_F04_SQL, (series,)),
            'f04_history_50_tickers': literal(sector.F04_HISTORY_SQL, (tickers, d)),
        }
        for name, sql in queries.items():
            lines, err = explain(sql)
            path = out / f'explain_{name}_{d}.txt'
            path.write_text('\n'.join(lines) + '\n' if lines else f'ERROR {err}\n')
            ex = next((x for x in (lines or []) if x.startswith('Execution Time')), None)
            buf = next((x.strip() for x in (lines or [])[1:4] if 'Buffers' in x), None)
            summary.append({'query': name, 'date': d, 'execution': ex, 'buffers': buf, 'error': err})
            print(json.dumps(summary[-1]), flush=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
