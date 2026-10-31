import io
import os
import unittest
from contextlib import redirect_stderr
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from price_update import (
    FetchOutcome,
    validate_price_row,
    request_symbol,
    frame,
    MarketSchedule,
    Symbol,
    bulk_upsert_prices,
    candle_for_target,
    monitoring_records,
    latest_completed_session,
    notify_telegram_monitor,
    prepare_feature04_monitoring,
    seal_feature04_monitoring,
    previous_weekday,
    process_exit_code,
    resolve_mode,
    resolve_trigger_source,
    run_entrypoint,
)
from unittest.mock import patch
from recovery_window import (
    calendar_window, correction_target_dates, index_calendar, recovery_targets, refill_sessions, short_sessions,
)
import price_update


JAKARTA = ZoneInfo("Asia/Jakarta")


def symbol(ordinal: int, ticker: str, asset_type: str = "stock") -> Symbol:
    return Symbol(ordinal, ticker, ticker, f"IDX:{ticker}", "IDX", asset_type)


class PriceUpdateTests(unittest.TestCase):
    def test_recovery_window_includes_five_observed_sessions(self):
        observed = [date(2026, 9, day) for day in (7, 8, 9, 10, 11)]
        self.assertEqual(
            correction_target_dates(observed, date(2026, 9, 14), 5),
            observed + [date(2026, 9, 14)],
        )
        self.assertEqual(
            correction_target_dates(observed, date(2026, 9, 11), 5), observed
        )

    def test_a_calendar_session_without_any_stored_row_is_a_recovery_target(self):
        # ERRORS M238: 2026-09-17/18 had no stored row, so the stored-dates window never named them
        calendar = [date(2026, 9, d) for d in (11, 14, 15, 16, 17, 18)]
        observed = [date(2026, 9, d) for d in (10, 11, 14, 15, 16)]
        window = calendar_window(calendar, date(2026, 9, 18), 5)
        self.assertEqual(window, [date(2026, 9, d) for d in (14, 15, 16, 17, 18)])
        self.assertEqual(
            recovery_targets(observed, calendar, date(2026, 9, 18), 5),
            [date(2026, 9, d) for d in (10, 11, 14, 15, 16, 17, 18)],
        )

    def test_short_sessions_are_the_old_ones_below_the_share_of_the_median(self):
        calendar = [date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9, 10)]
        counts = {day: 830 for day in calendar}
        counts[date(2026, 9, 2)] = 0          # a wholly missing session
        counts[date(2026, 9, 3)] = 400        # half missing
        counts[date(2026, 9, 4)] = 815        # a normal day without some illiquid stocks
        counts[date(2026, 9, 9)] = 0          # missing but inside the correction window: the recovery writes it
        window = {date(2026, 9, 9), date(2026, 9, 10)}
        self.assertEqual(
            short_sessions(calendar, counts, window),
            [(date(2026, 9, 2), 0, 830), (date(2026, 9, 3), 400, 830)],
        )
        self.assertEqual(short_sessions([], counts, window), [])

    def test_the_audit_refills_short_window_sessions_except_the_latest(self):
        calendar = [date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9, 10)]
        counts = {day: 830 for day in calendar}
        counts[date(2026, 9, 2)] = 0      # old: reported, not refilled
        counts[date(2026, 9, 8)] = 0      # inside the window: refilled
        counts[date(2026, 9, 10)] = 100   # the latest session: the recovery run itself takes it
        window = set(calendar_window(calendar, date(2026, 9, 10), 3))
        self.assertEqual(refill_sessions(calendar, counts, window, date(2026, 9, 10)), [date(2026, 9, 8)])

    def test_the_session_audit_follows_only_a_scheduled_recovery(self):
        calls = []
        cases = [(["price_update.py", "--mode", "recovery"], 1),
                 (["price_update.py", "--mode", "recovery", "--target-date", "2026-09-17"], 0),
                 (["price_update.py", "--mode", "recovery", "--dry-run"], 0),
                 (["price_update.py", "--mode", "daily"], 0)]
        for argv, expected in cases:
            calls.clear()
            with patch("sys.argv", argv), patch.object(price_update, "main", return_value=0), \
                    patch.dict(os.environ, {"DATABASE_URL": "postgresql://x"}), \
                    patch("recovery_window.audit_sessions", side_effect=lambda url: calls.append(url) or 0):
                self.assertEqual(price_update.main_with_session_audit(), 0)
            self.assertEqual(len(calls), expected, argv)

    def test_index_calendar_takes_the_first_index_that_answers_up_to_the_latest_session(self):
        first, second, third = symbol(1, "IHSG", "index"), symbol(2, "LQ45", "index"), symbol(3, "IDX30", "index")

        def fetch(sym, bars):
            if sym is first:
                raise TimeoutError("no answer")
            if sym is third:   # answers, but only with a candle after the latest completed session
                return [{"date": date(2026, 9, 21)}]
            return [{"date": date(2026, 9, d)} for d in (16, 17, 18, 21)]

        with redirect_stderr(io.StringIO()), patch("builtins.print"):
            self.assertEqual(
                index_calendar([first, second], date(2026, 9, 18), 10, fetch),
                [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)],
            )
            self.assertEqual(index_calendar([first], date(2026, 9, 18), 10, fetch), [])
            self.assertEqual(
                index_calendar([third, second], date(2026, 9, 18), 10, fetch),
                [date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)],
            )

    def test_feature04_monitoring_is_bound_to_price_transaction(self):
        calls = []

        class Connection:
            def execute(self, statement, params=None):
                calls.append((statement, params))

        records = [{
            "run_type": "DAILY", "trigger_source": "SCHEDULED",
            "update_for_date": date(2026, 9, 11),
        }]
        prepare_feature04_monitoring(Connection(), records, "price-run")
        seal_feature04_monitoring(Connection(), "price-run")
        self.assertTrue(any("set_config" in statement for statement, _ in calls))
        self.assertTrue(any("Monitoring_Feature04_Ticker" in statement for statement, _ in calls))
        self.assertTrue(all("f04-price-run" in params for _, params in calls))

    def test_bulk_upsert_sets_database_ingestion_time_for_insert_and_update(self):
        executed = []
        copied_rows = []

        class Copy:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def write_row(self, row):
                copied_rows.append(row)

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, params=None):
                executed.append((sql, params))

            def copy(self, sql):
                executed.append((sql, None))
                return Copy()

            def fetchone(self):
                return (1,)

        class Connection:
            def cursor(self):
                return Cursor()

        row = {
            "company_name": "Example",
            "ticker": "TEST",
            "tradingview_symbol": "IDX:TEST",
            "date": date(2026, 9, 11),
            "open": 100,
            "high": 110,
            "low": 90,
            "close": 105,
            "volume": 1000,
            "source": "TradingView",
            "query_date": date(2026, 9, 13),
            "timeframe": "Daily",
            "market_code": "IDX",
            "source_bar_time": datetime(2026, 9, 11, tzinfo=timezone.utc),
            "market_close_at": datetime(2026, 9, 11, 9, tzinfo=timezone.utc),
            "is_final": True,
            "finalized_at": datetime(2026, 9, 11, 10, tzinfo=timezone.utc),
        }

        self.assertEqual(
            bulk_upsert_prices(Connection(), [row], date(2026, 9, 11)),
            1,
        )
        insert_sql = next(sql for sql, _ in executed if "ON CONFLICT" in sql)
        self.assertIn("ingestion_time", insert_sql)
        self.assertIn("statement_timestamp()", insert_sql)
        self.assertIn("ingestion_time = EXCLUDED.ingestion_time", insert_sql)
        self.assertEqual(len(copied_rows), 1)
        self.assertEqual(len(copied_rows[0]), 17)

    def test_latest_completed_session_waits_for_finality_delay(self):
        schedule = MarketSchedule("IDX", "Asia/Jakarta", time(16), 60, 5)
        self.assertEqual(
            latest_completed_session(
                schedule, datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)
            ),
            date(2026, 9, 11),
        )
        self.assertEqual(
            latest_completed_session(
                schedule, datetime(2026, 9, 14, 10, 1, tzinfo=timezone.utc)
            ),
            date(2026, 9, 14),
        )

    def test_notifier_is_optional(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(notify_telegram_monitor("execution-1"))

    def test_notifier_posts_execution_id_and_secret(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"status":"sent"}'

        def opener(request, timeout):
            captured["body"] = request.data
            captured["secret"] = request.get_header("X-notify-secret")
            captured["timeout"] = timeout
            return Response()

        env = {
            "TELEGRAM_NOTIFY_URL": "http://telegram-monitor/notify",
            "TELEGRAM_NOTIFY_SECRET": "shared-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(notify_telegram_monitor("execution-2", opener=opener))

        self.assertIn(b'"execution_id": "execution-2"', captured["body"])
        self.assertEqual(captured["secret"], "shared-secret")
        self.assertEqual(captured["timeout"], 20.0)

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

    def test_index_ohlc_without_volume_and_stock_volume_requirement(self):
        row = dict(open=100, high=110, low=90, close=105, volume=None, security_type="index")
        self.assertIsNone(validate_price_row(row)["volume"])
        with self.assertRaises(ValueError):
            validate_price_row(dict(row, security_type="stock"))
        with self.assertRaises(ValueError):
            validate_price_row(dict(row, volume=-1))

    def test_index_wire_ohlc_is_kept_and_uses_no_split_adjustment(self):
        class Socket:
            sent = []
            def send(self, message): self.sent.append(message)
            def settimeout(self, value): pass
            def recv(self):
                return frame("timescale_update", ["cs_test", {"s1": {"s": [{"v": [1792720800, 100, 110, 90, 105]}]}}]) + frame("series_completed", ["cs_test", "s1"])
        ws = Socket()
        index = Symbol(1, "Index", "IHSG", "IDX:COMPOSITE", "IDX", "index")
        rows = request_symbol(ws, "cs_test", index, 7, 5, date(2026, 10, 23))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["volume"])
        self.assertEqual(rows[0]["security_type"], "index")
        self.assertIn('none', ws.sent[0])
        stock_rows = request_symbol(Socket(), "cs_test", symbol(1, "TEST"), 7, 5, date(2026, 10, 23))
        self.assertEqual(stock_rows, [])

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
