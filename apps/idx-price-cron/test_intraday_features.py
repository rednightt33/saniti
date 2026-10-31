"""EXEC-INTRADAY-FEATURES: the intraday Feature 04 adaptor, the migration's columns and the loader's queue."""
import random
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import intraday_features as f
import intraday_update

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20261031_004_intraday_features.sql"

try:
    ENGINE, INCREMENTAL = f.load_engine()
except ImportError:  # TA-Lib is in the intraday image and the dev venvs, not in the price crons' image
    ENGINE = INCREMENTAL = None


def series(n, seed=7, start=datetime(2026, 7, 6, 2, 0, tzinfo=timezone.utc)):
    """BARS_SQL-shaped rows: a random walk with gaps of a lunch break and a night between sessions."""
    rnd, price, out, t = random.Random(seed), 1000.0, [], start
    for i in range(n):
        o = price
        c = max(50.0, o * (1 + rnd.gauss(0, 0.004)))
        h, l = max(o, c) * (1 + abs(rnd.gauss(0, 0.002))), min(o, c) * (1 - abs(rnd.gauss(0, 0.002)))
        out.append((t, t.date(), Decimal(f"{o:.2f}"), Decimal(f"{h:.2f}"), Decimal(f"{l:.2f}"), Decimal(f"{c:.2f}"),
                    Decimal(rnd.randint(100, 50000) * 100), "IDX:TEST"))
        price = c
        t += timedelta(hours=1) if i % 7 != 6 else timedelta(hours=18)
    return out


class SyntheticDateTests(unittest.TestCase):
    def test_positions_map_to_consecutive_weekdays_and_back(self):
        self.assertEqual(f.synthetic_date(0), date(1970, 1, 5))
        self.assertEqual(f.synthetic_date(4), date(1970, 1, 9))
        self.assertEqual(f.synthetic_date(5), date(1970, 1, 12))
        days = [f.synthetic_date(p) for p in range(0, 200_000, 37)]
        self.assertTrue(all(d.isoweekday() <= 5 for d in days))
        self.assertTrue(all(a < b for a, b in zip(days, days[1:])))
        self.assertEqual([f.position_of(d) for d in days], list(range(0, 200_000, 37)))
        with self.assertRaises(ValueError):
            f.position_of(date(1970, 1, 10))      # a Saturday is never a bar


@unittest.skipIf(ENGINE is None, "TA-Lib not installed")
class EngineAdaptorTests(unittest.TestCase):
    def test_full_and_chained_calculation_agree_on_every_column(self):
        bars = series(700)
        src = f.engine_rows("TEST", bars, 0)
        full = ENGINE.calculate(src, calculated_at=datetime.now(timezone.utc))
        k = 640
        _, _, state, _ = INCREMENTAL.calculate_incremental(src[:k], state_only=True, checkpoint_limit=1)
        tail, outcomes, _, _ = INCREMENTAL.calculate_incremental(f.engine_rows("TEST", bars[k:], k), checkpoint=state,
                                                                 checkpoint_limit=1)
        self.assertFalse(f.failed_groups(outcomes))
        cols = [c for c in ENGINE.COLUMNS if c not in f.NOT_STORED]
        for a, b in zip(full[k:], tail):
            for c in cols:
                x, y = a[c], b[c]
                if isinstance(x, float) and isinstance(y, float):
                    self.assertAlmostEqual(x, y, delta=1e-9 * max(1.0, abs(x)), msg=c)
                else:
                    self.assertEqual(x, y, c)
        # the outputs come back in bar order: position_of(trade_date) is the bar's index
        self.assertEqual([f.position_of(o["trade_date"]) for o in full], list(range(700)))

    def test_the_table_holds_every_engine_output_and_nothing_else(self):
        sql = MIGRATION.read_text()
        body = sql[sql.index('CREATE TABLE public."Feature_04_Technical_Indicator_Intraday" ('):]
        body = body[:body.index(") PARTITION BY")]
        cols = [m.group(1) for m in re.finditer(r"^\s{4}([a-z0-9_]+) ", body, re.M)
                if m.group(1) not in f.IDENTITY + ("calculated_at",)]
        f.check_columns(ENGINE, cols)            # raises on a drift
        with self.assertRaises(RuntimeError):
            f.check_columns(ENGINE, cols[:-1])


class QueueTests(unittest.TestCase):
    def test_the_loader_queues_the_first_changed_bar_of_each_series_in_the_same_statement(self):
        src = Path(intraday_update.__file__).read_text()
        self.assertIn("RETURNING t.ticker, t.timeframe, t.bar_time", src)
        self.assertIn("min(bar_time) FROM written", src)
        self.assertIn("NOT public.is_universe_index(ticker)", src)
        self.assertIn("least(q.dirty_from, EXCLUDED.dirty_from)", src)

    def test_the_migration_refuses_an_index_and_never_stores_the_daily_identity(self):
        sql = MIGRATION.read_text()
        self.assertEqual(sql.count("EXECUTE FUNCTION public.validate_stock_feature_identity()"), 2)
        for table in ("Feature_01_Stock_Intraday", "Feature_04_Technical_Indicator_Intraday"):
            body = sql[sql.index(f'CREATE TABLE public."{table}" ('):]
            body = body[:body.index(") PARTITION BY")]
            for column in ("trade_date", "asset_type", "calculation_version", "sector", "industry"):
                self.assertNotRegex(body, rf"\n    {column} ")


if __name__ == "__main__":
    unittest.main()
