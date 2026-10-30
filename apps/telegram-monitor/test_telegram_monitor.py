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
    StockbitUpdateSummary,
    build_stockbit_messages,
    BrokerFreshnessSummary,
    TelegramMonitor,
    build_freshness_message,
    build_publisher_message,
    parse_publisher_health,
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

    def test_stockbit_update_round_is_reported_with_its_counts(self):
        value = StockbitUpdateSummary(
            execution_id="7b0c0d3e-0000-4000-8000-000000000001", mode="APPLY", status="SUCCESS",
            started_at=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 26, 11, 5, tzinfo=timezone.utc),
            token_expires_at=datetime(2026, 10, 27, 5, 42, tzinfo=timezone.utc),
            broker_dates=("2026-10-26",), broker_rows=24000,
            features={"changed_dates": ["2026-10-26"]}, index_result={"newest": {}},
            events={"reconcile_corporate_action": {"new": 3, "changed": 1, "removed": 0},
                    "reconcile_insider": {"new": 40, "changed": 0, "removed": 0}},
            verify={}, last_error=None,
        )
        text = build_stockbit_messages(value)[0]
        self.assertIn("Stockbit update APPLY SUCCESS", text)
        self.assertIn("Broker Summary: 2026-10-26 • rows 24000", text)
        self.assertIn("1 tanggal di-refresh (dari 2026-10-26)", text)
        self.assertIn("Corporate action: baru 3, berubah 1", text)
        self.assertIn("27 Oct 2026 12:42 WIB", text)

    def test_an_incomplete_broker_date_is_named_with_its_remark(self):
        """EXEC-LOADER-M217: a date the database remarked INCOMPLETE is listed under the round; the load stands."""
        value = StockbitUpdateSummary(
            execution_id="x", mode="APPLY", status="SUCCESS",
            started_at=datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 29, 10, 30, tzinfo=timezone.utc), token_expires_at=None,
            broker_dates=("2026-10-28", "2026-10-29"), broker_rows=48000, features={}, index_result={}, events={},
            verify={}, last_error=None,
            incomplete=(("2026-10-29", "Muatan tidak lengkap: broker 40 (biasanya 89)."),),
        )
        text = build_stockbit_messages(value)[0]
        self.assertIn("⚠️ 2026-10-29: Muatan tidak lengkap: broker 40 (biasanya 89).", text)
        self.assertNotIn("2026-10-28: Muatan", text)

    def test_stockbit_update_failure_names_the_error(self):
        value = StockbitUpdateSummary(
            execution_id="x", mode="APPLY", status="FAILED",
            started_at=datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 10, 26, 10, 0, 5, tzinfo=timezone.utc), token_expires_at=None,
            broker_dates=(), broker_rows=None, features={}, index_result={}, events={}, verify={},
            last_error="RuntimeError: Token Stockbit kedaluwarsa",
        )
        text = build_stockbit_messages(value)[0]
        self.assertIn("FAILED", text)
        self.assertIn("Error: RuntimeError: Token Stockbit kedaluwarsa", text)


class BrokerFreshnessTests(unittest.TestCase):
    """EXEC-TERMINAL-FRESH (user 2026-10-27): the evening warning when broker data lags the prices."""

    def test_message_names_both_dates_the_gap_and_the_way_to_load(self):
        text = build_freshness_message(BrokerFreshnessSummary("terminal-2026-10-27", date(2026, 10, 23), date(2026, 10, 27), 2))
        self.assertIn("tertinggal 2 sesi", text)
        self.assertIn("Broker sampai Fri 23 Oct 2026", text)
        self.assertIn("harga sampai Tue 27 Oct 2026", text)
        self.assertIn("stockbit-updater", text)

    def test_nothing_is_sent_or_logged_when_broker_is_current(self):
        import telegram_monitor as tm
        sent = []

        class Conn:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monitor = TelegramMonitor.__new__(TelegramMonitor)
        monitor.database_url, monitor.token, monitor.chat_id = "postgresql://unused", "t", "c"
        monitor.send_message = lambda *a, **k: sent.append(a) or 1
        original_connect, original_fetch = tm.psycopg.connect, tm.fetch_broker_freshness
        tm.psycopg.connect = lambda *a, **k: Conn()
        tm.fetch_broker_freshness = lambda c, e: BrokerFreshnessSummary(e, date(2026, 10, 27), date(2026, 10, 27), 0)
        try:
            self.assertEqual(monitor.notify("Terminal_Broker_Freshness", "terminal-2026-10-27"), ("not_needed", 0))
        finally:
            tm.psycopg.connect, tm.fetch_broker_freshness = original_connect, original_fetch
        self.assertEqual(sent, [])


class PublisherHealthTests(unittest.TestCase):
    """EXEC-PUBLISHER-SPEED (user go 2026-10-29, ERRORS M303): terminal-publisher's alerts, in fixed shapes only."""

    RUN = "terminal-publish-2026-10-29-1900"

    def details(self, **over):
        return {"status": "failed", "run_time": "2026-10-29 19:00", "manual": False, "stage": "files",
                "error": "ReadTimeoutError", "last_published": "2026-10-29T00:36:12.5+00:00", **over}

    def test_each_kind_reads_in_plain_words_with_the_run_time_and_the_last_publication_in_wib(self):
        failed = build_publisher_message(parse_publisher_health(self.RUN, self.details()))
        self.assertIn("publikasi Thu 29 Oct 2026 19:00 WIB gagal", failed)
        self.assertIn("Tahap: menulis file data • galat: ReadTimeoutError", failed)
        self.assertIn("memakai publikasi Thu 29 Oct 2026 07:36 WIB", failed)
        missing = build_publisher_message(parse_publisher_health(self.RUN, self.details(status="missing", stage=None, error=None)))
        self.assertIn("belum terbit", missing)
        self.assertIn("Publikasi terakhir: Thu 29 Oct 2026 07:36 WIB", missing)
        slow = build_publisher_message(parse_publisher_health(self.RUN + "-slow", self.details(status="slow", stage="packs", minutes=30, error=None)))
        self.assertIn("masih berjalan setelah 30 menit", slow)
        self.assertIn("Tahap: menulis paket harga", slow)
        partial = build_publisher_message(parse_publisher_health(self.RUN + "-partial", {"status": "partial", "run_time": "2026-10-29 19:00", "manual": False, "files": ["price", "logos"]}))
        self.assertIn("terbit tanpa file harga lintas-saham (Screener), daftar logo", partial)
        manual = build_publisher_message(parse_publisher_health("terminal-publish-manual-2026-10-29-2203", self.details(run_time="2026-10-29 22:03", manual=True)))
        self.assertIn("run manual Thu 29 Oct 2026 22:03 WIB gagal", manual)

    def test_anything_but_the_fixed_shapes_is_refused(self):
        bad = [
            (self.RUN, self.details(error="OSError: password=x")),          # free text
            (self.RUN, self.details(stage="somewhere")),
            (self.RUN, self.details(extra="x")),
            (self.RUN, self.details(status="slow")),                         # the id has no -slow
            (self.RUN + "-slow", self.details()),                            # failed under a -slow id
            (self.RUN, self.details(manual=True)),                           # not a manual id
            (self.RUN, self.details(last_published="yesterday")),
            (self.RUN, self.details(last_published="2026-10-29T00:36:12")),  # no zone
            (self.RUN, self.details(minutes=True)),
            (self.RUN, self.details(files=["../x"])),
            ("terminal-2026-10-29", self.details()),
            (self.RUN, "failed"),
        ]
        for execution_id, details in bad:
            with self.assertRaises(ValueError, msg=(execution_id, details)):
                parse_publisher_health(execution_id, details)

    def test_one_message_per_run_time_and_kind(self):
        import telegram_monitor as tm
        sent, claims = [], {}

        class Conn:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def claim(connection, source, execution_id):
            if (source, execution_id) in claims:
                return "duplicate", claims[(source, execution_id)]
            claims[(source, execution_id)] = len(claims) + 1
            return "claimed", claims[(source, execution_id)]

        monitor = TelegramMonitor.__new__(TelegramMonitor)
        monitor.database_url, monitor.token, monitor.chat_id = "postgresql://unused", "t", "c"
        monitor.send_message = lambda token, chat, text, *a: sent.append(text) or len(sent)
        saved = tm.psycopg.connect, tm.claim_delivery, tm.mark_sent
        tm.psycopg.connect = lambda *a, **k: Conn()
        tm.claim_delivery, tm.mark_sent = claim, lambda c, log_id, ids: None
        try:
            self.assertEqual(monitor.notify(tm.HEALTH_SOURCE, self.RUN, self.details())[0], "sent")
            # the check tick finds the same run time unpublished: the same id, so no second message
            self.assertEqual(monitor.notify(tm.HEALTH_SOURCE, self.RUN, self.details(status="missing"))[0], "duplicate")
            with self.assertRaises(ValueError):
                monitor.notify(tm.HEALTH_SOURCE, self.RUN, None)
        finally:
            tm.psycopg.connect, tm.claim_delivery, tm.mark_sent = saved
        self.assertEqual(len(sent), 1)
        self.assertIn("gagal", sent[0])


if __name__ == "__main__":
    unittest.main()
