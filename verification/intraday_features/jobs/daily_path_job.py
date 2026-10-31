"""EXEC-INTRADAY-FEATURES: the daily path against the live database, every step ROLLED BACK (orc-test-runner;
extras: apps/idx-price-cron/{intraday_update,intraday_features,price_update}.py, features/feature04, requirements.txt).

Two transactions on BBCA 1h, each rolled back:
  A. write_rows with the last stored bar changed and one new bar after it -> 2 bars written, the queue item starts at
     the changed bar (at or before the last calculated bar), run_queue takes the full path.
  B. write_rows with one new bar only -> 1 bar written, the queue item starts after the last calculated bar,
     run_queue takes the chained path, and the new bar's Feature 04 equals a full calculation of the series.
Prints OUT/ERR lines, a VERDICT and JOB_DONE. No secret is printed.
"""
import json
import os
from datetime import timedelta
from decimal import Decimal

import psycopg

import intraday_features as f
import intraday_update as u

TICKER, TF = "BBCA", "1h"


def out(kind, event, **fields):
    print(f"{kind} " + json.dumps({"event": event, **fields}, default=str), flush=True)


def last_rows(conn, n):
    cols = ", ".join(u.COLUMNS)
    rows = conn.execute(f"SELECT {cols} FROM {u.TABLE} WHERE ticker = %s AND timeframe = %s "
                        "ORDER BY bar_time DESC LIMIT %s", (TICKER, TF, n)).fetchall()
    return [dict(zip(u.COLUMNS, r)) for r in reversed(rows)]


def new_bar(after):
    bar = dict(after)
    bar["bar_time"] = after["bar_time"] + timedelta(hours=1)
    bar.update(open=after["close"], high=after["close"], low=after["close"], volume=Decimal(100))
    return bar


def run(label, change_last):
    ok = True
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:       # not autocommit: one outer transaction
        state_before = conn.execute(f"SELECT last_bar_time, bars FROM {f.STATE} WHERE ticker = %s AND timeframe = %s",
                                    (TICKER, TF)).fetchone()
        rows = last_rows(conn, 3)
        batch = []
        if change_last:
            changed = dict(rows[-1])
            changed["volume"] = changed["volume"] + 100           # a real change (a close equal to its low may not be)
            batch.append(changed)
        batch.append(new_bar(rows[-1]))
        n = u.write_rows(conn, batch)
        queue = conn.execute(f"SELECT dirty_from, status FROM {f.QUEUE} WHERE ticker = %s AND timeframe = %s",
                             (TICKER, TF)).fetchone()
        expect_from = batch[0]["bar_time"]
        out("OUT", f"{label}_write", written=n, expected=len(batch), queue=queue, expected_from=expect_from,
            state_before=state_before)
        ok &= n == len(batch) and queue is not None and queue[0] == expect_from and queue[1] == "PENDING"
        summary = f.run_queue(conn, [TF])
        state_after = conn.execute(f"SELECT last_bar_time, bars FROM {f.STATE} WHERE ticker = %s AND timeframe = %s",
                                   (TICKER, TF)).fetchone()
        status = conn.execute(f"SELECT status, attempts, last_error FROM {f.QUEUE} WHERE ticker = %s AND timeframe = %s",
                              (TICKER, TF)).fetchone()
        expect_full = change_last
        out("OUT", f"{label}_queue", summary={k: v for k, v in summary.items() if k != "failed"},
            failed=summary["failed"], state_after=state_after, queue_after=status)
        ok &= (not summary["failed"] and summary["full"] == int(expect_full) and status[0] == "DONE"
               and state_after[0] == batch[-1]["bar_time"] and state_after[1] == state_before[1] + 1)
        # the new bar against a full calculation of the series as it stands in this transaction
        engine, _ = f.load_engine()
        bars = conn.execute(f.BARS_SQL, (TICKER, TF, f.EPOCH - timedelta(days=1))).fetchall()
        full = engine.calculate(f.engine_rows(TICKER, bars, 0))[-1]
        cols = f.stored_columns(conn)
        stored = conn.execute(f"SELECT {', '.join(cols)} FROM {f.F04} WHERE ticker = %s AND timeframe = %s "
                              "AND bar_time = %s", (TICKER, TF, batch[-1]["bar_time"])).fetchone()
        diff = [c for c, v in zip(cols, stored) if not (
            (v is None and full[c] is None) or (v is not None and full[c] is not None
                                                and abs(float(v) - float(full[c])) <= 1e-9 * max(1.0, abs(float(v)))))]
        f01 = conn.execute('SELECT close, return_1bar_pct, bars_per_year FROM public."Feature_01_Stock_Intraday" '
                           "WHERE ticker = %s AND timeframe = %s AND bar_time = %s",
                           (TICKER, TF, batch[-1]["bar_time"])).fetchone()
        out("OUT", f"{label}_new_bar", f04_columns_differ=diff, f01=f01)
        ok &= not diff and f01 is not None
        conn.rollback()
    out("OUT", f"{label}_rolled_back")
    return ok


if __name__ == "__main__":
    try:
        a = run("A_changed_and_new", True)
        b = run("B_new_only", False)
        print("VERDICT " + json.dumps({"A": a, "B": b}), flush=True)
    except Exception as exc:  # noqa: BLE001
        print("ERR " + json.dumps({"error": f"{type(exc).__name__}: {exc}"[:1500]}), flush=True)
    finally:
        print("JOB_DONE", flush=True)
