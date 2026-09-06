import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from price_update import FetchOutcome, Symbol, monitoring_records, resolve_mode


JAKARTA = ZoneInfo("Asia/Jakarta")


def symbol(ordinal: int, ticker: str, asset_type: str = "stock") -> Symbol:
    return Symbol(ordinal, ticker, ticker, f"IDX:{ticker}", "IDX", asset_type)


class PriceUpdateTests(unittest.TestCase):
    def test_auto_mode_uses_jakarta_hour(self):
        self.assertEqual(
            resolve_mode("daily", datetime(2026, 9, 7, 6, tzinfo=JAKARTA)), "daily"
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 6, tzinfo=JAKARTA)),
            "recovery",
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 17, tzinfo=JAKARTA)),
            "daily",
        )

    def test_daily_monitoring_uses_security_type_groups(self):
        universe = [symbol(1, "AAAA"), symbol(2, "BBBB"), symbol(3, "ETF1", "fund")]
        outcomes = [
            FetchOutcome(universe[0], {"ticker": "AAAA"}, None, None),
            FetchOutcome(universe[1], None, None, "missing"),
            FetchOutcome(universe[2], {"ticker": "ETF1"}, None, None),
        ]
        now = datetime(2026, 9, 7, 10, tzinfo=ZoneInfo("UTC"))
        records = monitoring_records(
            universe, universe, outcomes, "DAILY", now.date(), now, now
        )
        by_type = {record["asset_type"]: record for record in records}
        self.assertEqual(by_type["stock"]["expected_symbols"], 2)
        self.assertEqual(by_type["stock"]["updated_symbols"], 1)
        self.assertEqual(by_type["stock"]["missing_symbol_list"], ["BBBB"])
        self.assertEqual(by_type["stock"]["status"], "PARTIAL")
        self.assertEqual(by_type["fund"]["status"], "SUCCESS")

    def test_recovery_counts_only_missing_scope_as_queried(self):
        universe = [symbol(1, "AAAA"), symbol(2, "BBBB")]
        outcomes = [FetchOutcome(universe[1], {"ticker": "BBBB"}, None, None)]
        now = datetime(2026, 9, 8, 0, tzinfo=ZoneInfo("UTC"))
        records = monitoring_records(
            universe,
            [universe[1]],
            outcomes,
            "RECOVERY",
            now.date(),
            now,
            now,
        )
        self.assertEqual(records[0]["expected_symbols"], 2)
        self.assertEqual(records[0]["queried_symbols"], 1)
        self.assertEqual(records[0]["updated_symbols"], 1)
        self.assertEqual(records[0]["missing_symbols"], 0)
        self.assertEqual(records[0]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
