"""EXEC-SECTOR-ANALYSIS S1: before the migration is applied, the refresh's SELECT (cut from the migration, as
explain_dev.py measures it) against an independent Python recomputation from the raw rows (validate_feature_08.expected),
both read on dev through a read-only pgweb connection (a module `pgx` with rows(sql), outside the repository).

  python dev_crosscheck.py <date> [<date> ...]     prints one OUT line per date and a VERDICT
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import explain_dev  # noqa: E402
import validate_feature_08 as v  # noqa: E402
import pgx  # noqa: E402


def lit(p):
    if p is None:
        return 'NULL'
    if isinstance(p, dt.date):
        return f"DATE '{p.isoformat()}'"
    if isinstance(p, (list, tuple)):
        if p and all(isinstance(x, dt.date) for x in p):
            return 'ARRAY[' + ','.join(f"DATE '{x.isoformat()}'" for x in p) + ']::date[]'
        return 'ARRAY[' + ','.join("'" + str(x).replace("'", "''") + "'" for x in p) + ']::text[]'
    return "'" + str(p).replace("'", "''") + "'"


def q(sql, params=()):
    return pgx.rows(sql % tuple(lit(p) for p in params) if params else sql)


def main(dates):
    bad = 0
    for d in dates:
        day = dt.date.fromisoformat(d)
        prev = q("SELECT max(date)::text FROM public.\"Price_Stock_Indonesia_IDX\" WHERE ticker = 'IHSG' "
                 "AND timeframe = 'Daily' AND is_final AND date < %s", (day,))[0][0]
        cols = ('group_kind', 'group_name') + v.COLS
        rows = pgx.rows(explain_dev.refresh_select(d, prev))
        stored = {}
        for r in rows:
            row = dict(zip(('group_kind', 'group_name', 'sector', 'members', 'n_ema50', 'above_ema50', 'n_ema200',
                            'above_ema200', 'adv_1d', 'unch_1d', 'dec_1d', 'weight_sum', 'ret_1d_w'), r))
            row['weight_basis'] = 'adv20_value' if row['weight_sum'] is not None else None
            stored[(row['group_kind'], row['group_name'])] = {k: row[k] for k in cols[2:]}
        want = v.expected(q, day)
        diffs = v.compare(stored, want) if want is not None else [('*', 'date', None, 'not a market date')]
        bad += len(diffs)
        market = stored.get(('MARKET', 'IHSG'), {})
        print('OUT ' + json.dumps({'date': d, 'groups': len(stored), 'differences': len(diffs), 'first': diffs[:5],
                                   'market': {k: market.get(k) for k in ('members', 'n_ema50', 'above_ema50', 'n_ema200',
                                                                         'above_ema200', 'adv_1d', 'unch_1d', 'dec_1d', 'ret_1d_w')}},
                                  default=str), flush=True)
    print('VERDICT ' + ('CROSSCHECK_OK' if not bad else f'CROSSCHECK_DIFF {bad}'), flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
