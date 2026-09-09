import io
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime
from zoneinfo import ZoneInfo

from price_update import (
    FetchOutcome,
    Symbol,
    candle_for_target,
    monitoring_records,
    previous_weekday,
    process_exit_code,
    resolve_mode,
    resolve_trigger_source,
    run_entrypoint,
)


JAKARTA = ZoneInfo("Asia/Jakarta")


def symbol(ordinal: int, ticker: str, asset_type: str = "stock") -> Symbol:
    return Symbol(ordinal, ticker, ticker, f"IDX:{ticker}", "IDX", asset_type)


class PriceUpdateTests(unittest.TestCase):
    def test_review_status_is_a_successful_process_exit(self):
        self.assertEqual(process_exit_code(["NEEDS_REVIEW"]), 0)

    def test_failed_status_is_a_failed_process_exit(self):
        self.assertEqual(process_exit_code(["FAILED"]), 1)

    def test_entrypoint_forces_requested_exit_code(self):
        exit_codes = []
        run_entrypoint(lambda: 2, exit_codes.append)
        self.assertEqual(exit_codes, [2])

    def test_entrypoint_forces_failure_exit_after_exception(self):
        exit_codes = []

        def fail():
            raise RuntimeError("test failure")

        with redirect_stderr(io.StringIO()):
            run_entrypoint(fail, exit_codes.append)
        self.assertEqual(exit_codes, [1])

    def test_auto_mode_uses_jakarta_hour(self):
        self.assertEqual(
            resolve_mode("daily", datetime(2026, 9, 7, 6, tzinfo=JAKARTA)), "daily"
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 6, tzinfo=JAKARTA)),
            "recovery",
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 5, tzinfo=JAKARTA)),
            "manual",
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 11, tzinfo=JAKARTA)),
            "manual",
        )
        self.assertEqual(
            resolve_mode("auto", datetime(2026, 9, 7, 17, tzinfo=JAKARTA)),
            "daily",
        )

    def test_target_candle_never_falls_back_to_prior_date(self):
        rows = [
            {
                "date": date(2026, 9, 4),
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            }
        ]
        self.assertIsNone(candle_for_target(rows, date(2026, 9, 7)))

    def test_trigger_source_is_inferred_from_service_schedule_window(self):
        self.assertEqual(
            resolve_trigger_source("daily", datetime(2026, 9, 7, 17, tzinfo=JAKARTA)),
            "SCHEDULED",
        )
        self.assertEqual(
            resolve_trigger_source("daily", datetime(2026, 9, 7, 11, tzinfo=JAKARTA)),
            "MANUAL",
        )
        self.assertEqual(
            resolve_trigger_source("recovery", datetime(2026, 9, 7, 6, tzinfo=JAKARTA)),
            "SCHEDULED",
        )
        self.assertEqual(
            resolve_trigger_source("recovery", datetime(2026, 9, 7, 10, tzinfo=JAKARTA)),
            "MANUAL",
        )

    def test_recovery_targets_previous_weekday_across_weekend(self):
        self.assertEqual(previous_weekday(date(2026, 9, 5)), date(2026, 9, 4))
        self.assertEqual(previous_weekday(date(2026, 9, 6)), date(2026, 9, 4))
        self.assertEqual(previous_weekday(date(2026, 9, 7)), date(2026, 9, 4))
        self.assertEqual(previous_weekday(date(2026, 9, 8)), date(2026, 9, 7))

    def test_daily_monitoring_uses_security_type_groups(self):
        universe = [symbol(1, "AAAA"), symbol(2, "BBBB"), symbol(3, "ETF1", "fund")]
        outcomes = [
            FetchOutcome(universe[0], {"ticker": "AAAA"}, None, None),
            FetchOutcome(universe[1], None, None, "missing"),
            FetchOutcome(universe[2], {"ticker": "ETF1"}, None, None),
        ]
        now = datetime(2026, 9, 7, 10, tzinfo=ZoneInfo("UTC"))
        records = monitoring_records(
            universe,
            universe,
            outcomes,
            "DAILY",
            now.date(),
            now,
            now,
            "execution-1",
            "SCHEDULED",
            now,
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
            "execution-2",
            "SCHEDULED",
            now,
        )
        self.assertEqual(records[0]["expected_symbols"], 2)
        self.assertEqual(records[0]["queried_symbols"], 1)
        self.assertEqual(records[0]["updated_symbols"], 1)
        self.assertEqual(records[0]["missing_symbols"], 0)
        self.assertEqual(records[0]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
