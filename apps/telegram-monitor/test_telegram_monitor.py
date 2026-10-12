import json
import unittest
from datetime import date, datetime, timezone

from telegram_monitor import (
    Feature04Summary,
    MonitoringSummary,
    aggregate_status,
    build_messages,
    format_header,
    format_timing,
    build_feature04_messages,
    edit_telegram_message,
    feature04_markup,
    fetch_fixed_income_summary,
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
        "started_at": datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 9, 9, 10, 1, 10, tzinfo=timezone.utc),
        "duration_seconds": 192,
        "last_error": None,
    }
    values.update(overrides)
    return MonitoringSummary(**values)


class TelegramMonitorTests(unittest.TestCase):
    def test_edit_message_uses_original_message_and_retry_markup(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{"ok":true,"result":{"message_id":77}}'

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return Response()

        message_id = edit_telegram_message(
            "token", "123", 77, "final",
            {"inline_keyboard": [[{"text": "Retry", "callback_data": "f04:status"}]]},
            opener=opener,
        )
        self.assertEqual(message_id, 77)
        self.assertTrue(captured["url"].endswith("/bottoken/editMessageText"))
        self.assertEqual(captured["body"]["message_id"], 77)
        self.assertEqual(captured["body"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "f04:status")

    def test_fixed_income_summary_maps_series_and_missing_metric(self):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args): return None
            def fetchone(self):
                started = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
                return ('DAILY', 'SCHEDULED', date(2026, 10, 9), 48, 48, 47, 1,
                        [{'ticker': 'ID10Y', 'metric_type': 'price'}], 'PARTIAL',
                        started, started.replace(minute=1), None, 'ID')
        class Connection:
            def cursor(self): return Cursor()
        value = fetch_fixed_income_summary(Connection(), '00000000-0000-0000-0000-000000000001')
        self.assertEqual(value.exchange, 'FIXED INCOME/ID')
        self.assertEqual(value.missing_tickers, ('ID10Y/price',))

    def test_failure_status_has_priority(self):
        self.assertEqual(aggregate_status(["SUCCESS", "PARTIAL", "FAILED"]), "FAILED")

    def test_daily_message_is_compact_and_lists_missing_tickers(self):
        messages = build_messages(summary())
        self.assertEqual(len(messages), 1)
        self.assertIn("⚠️ IDX DAILY PARTIAL", messages[0])
        self.assertIn("842/844 updated", messages[0])
        self.assertIn(
            "Triggered at: 09 Sep 2026 17:00 WIB • Finished at: 09 Sep 2026 17:01 WIB",
            messages[0],
        )
        self.assertIn("\n\nMissing: ", messages[0])
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

    def test_timing_is_converted_to_jakarta(self):
        self.assertEqual(
            format_timing(summary()),
            "Triggered at: 09 Sep 2026 17:00 WIB • Finished at: 09 Sep 2026 17:01 WIB",
        )

    def test_long_missing_list_is_split_under_limit(self):
        tickers = tuple(f"TICKER{i:04d}" for i in range(500))
        messages = build_messages(
            summary(missing_symbols=len(tickers), missing_tickers=tickers), max_length=200
        )
        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= 200 for message in messages))
        self.assertIn("Missing (cont.):", messages[1])

    def test_feature04_message_lists_terminal_ticker_failures(self):
        value = Feature04Summary(
            execution_id="f04-run", delivery_key="scheduled:IDX_EQUITY:2026-09-09",
            market_key="IDX_EQUITY", run_type="DAILY", trigger_source="SCHEDULED",
            update_for_date=date(2026, 9, 9), eligible_tickers=844,
            completed_tickers=843, failed_tickers=1, blocked_tickers=0,
            failed_details=("BBCA.JK [adx_14] (FORMULA_GROUP_FAILED)",), status="PARTIAL",
            started_at=datetime(2026, 9, 9, 10, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 9, 10, 2, tzinfo=timezone.utc),
            duration_seconds=60, last_error=None,
        )
        text = build_feature04_messages(value)[0]
        self.assertIn("Feature04 IDX_EQUITY DAILY PARTIAL", text)
        self.assertIn("Eligible: 844 • Success: 843", text)
        self.assertIn("FINAL", text)
        self.assertIn("BBCA.JK [adx_14]", text)
        self.assertEqual(
            feature04_markup(value)["inline_keyboard"][0][0]["callback_data"],
            "f04:status",
        )

    def test_feature04_failure_details_are_capped_in_one_message(self):
        failures = tuple(f"equity/T{i:02d}.JK [adx_14]" for i in range(15))
        value = Feature04Summary(
            execution_id="f04-run", delivery_key="scheduled:IDX_EQUITY:2026-09-09",
            market_key="IDX_EQUITY", run_type="RECOVERY", trigger_source="SCHEDULED",
            update_for_date=date(2026, 9, 9), eligible_tickers=15,
            completed_tickers=0, failed_tickers=15, blocked_tickers=0,
            failed_details=failures, status="FAILED",
            started_at=datetime(2026, 9, 9, 10, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 9, 10, 2, tzinfo=timezone.utc),
            duration_seconds=60, last_error=None,
        )
        messages = build_feature04_messages(value)
        self.assertEqual(len(messages), 1)
        self.assertIn("…and 5 more", messages[0])
        self.assertNotIn("T10.JK", messages[0])


if __name__ == "__main__":
    unittest.main()
