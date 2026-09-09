import unittest
from datetime import date

from telegram_monitor import (
    MonitoringSummary,
    aggregate_status,
    build_messages,
    format_header,
)


def summary(**overrides) -> MonitoringSummary:
    values = {
        "execution_id": "execution-1",
        "exchange": "IDX",
        "run_type": "DAILY",
        "trigger_source": "SCHEDULED",
        "update_for_date": date(2026, 9, 9),
        "expected_symbols": 844,
        "queried_symbols": 844,
        "updated_symbols": 842,
        "missing_symbols": 2,
        "missing_tickers": ("AAAA", "BBBB"),
        "status": "PARTIAL",
        "duration_seconds": 192,
        "last_error": None,
    }
    values.update(overrides)
    return MonitoringSummary(**values)


class TelegramMonitorTests(unittest.TestCase):
    def test_failure_status_has_priority(self):
        self.assertEqual(aggregate_status(["SUCCESS", "PARTIAL", "FAILED"]), "FAILED")

    def test_daily_message_is_compact_and_lists_missing_tickers(self):
        messages = build_messages(summary())
        self.assertEqual(len(messages), 1)
        self.assertIn("⚠️ IDX DAILY PARTIAL", messages[0])
        self.assertIn("842/844 updated", messages[0])
        self.assertTrue(messages[0].endswith("Missing: AAAA, BBBB"))

    def test_recovery_uses_queried_symbols_as_denominator(self):
        text = format_header(
            summary(
                run_type="RECOVERY",
                status="NEEDS_REVIEW",
                queried_symbols=12,
                updated_symbols=0,
                missing_symbols=12,
            )
        )
        self.assertIn("0/12 recovered", text)
        self.assertIn("12 still missing", text)

    def test_manual_run_is_visible(self):
        self.assertIn("DAILY MANUAL", format_header(summary(trigger_source="MANUAL")))

    def test_long_missing_list_is_split_under_limit(self):
        tickers = tuple(f"TICKER{i:04d}" for i in range(500))
        messages = build_messages(
            summary(missing_symbols=len(tickers), missing_tickers=tickers), max_length=200
        )
        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= 200 for message in messages))
        self.assertIn("Missing (cont.):", messages[1])


if __name__ == "__main__":
    unittest.main()
