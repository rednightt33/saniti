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
    build_consensus_message,
    parse_consensus_report,
    build_audit_queue_message,
    parse_audit_queue,
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


class NoTradeMessageTests(unittest.TestCase):
    """EXEC-UNIVERSE-BROKER P2: no-trade symbols are named as such, not as missing; a real gap is named first."""

    def test_success_with_no_trade(self):
        text = build_messages(summary(status="SUCCESS", missing_symbols=0, missing_tickers=(), updated_symbols=828,
                                      no_trade_tickers=("ADHI", "PTPP")))[0]
        self.assertIn("✅", text)
        self.assertIn("0 missing • 2 tanpa transaksi", text)
        self.assertIn("Tanpa transaksi (bukan error): ADHI, PTPP", text)
        self.assertNotIn("Missing:", text)

    def test_price_gap_named(self):
        text = build_messages(summary(status="PARTIAL", missing_symbols=0, missing_tickers=(),
                                      price_gaps=("BBBB 2026-11-03",)))[0]
        self.assertIn("Ada transaksi reguler tapi harga tidak ada: BBBB 2026-11-03", text)


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

    def _with_stock_lists(self, stock_lists):
        return StockbitUpdateSummary(
            execution_id="x", mode="APPLY", status="SUCCESS",
            started_at=datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc), token_expires_at=None,
            broker_dates=(), broker_rows=0, features={}, index_result={}, events={}, verify={}, last_error=None,
            stock_lists=stock_lists,
        )

    def test_stock_lists_first_capture_and_changes_are_reported(self):
        """EXEC-STOCK-CATALOG: counts, first captures, changed lists and new lists Stockbit shows."""
        text = build_stockbit_messages(self._with_stock_lists({
            "status": "SUCCESS", "lists": 66, "members": 2100, "added": 3, "removed": 1,
            "changes": {"INDEX:1": {"name": "LQ45", "added": ["BBRI", "BMRI"], "removed": ["ASII"]},
                        "KONGLO:9": {"name": "Salim", "first_capture": True, "members": 30},
                        "KONGLO:7": {"name": "Djarum", "added": ["TOWR"], "removed": []}},
            "unlisted_new": [{"list_key": "INDEX:500", "name": "IDXNEW30"}]}))[0]
        self.assertIn("Indeks & grup: 66 daftar, 2100 anggota • masuk 3, keluar 1", text)
        self.assertIn("Muatan pertama: 1 daftar", text)
        self.assertIn("• LQ45: +BBRI +BMRI −ASII", text)
        self.assertIn("• Djarum: +TOWR", text)
        self.assertNotIn("• Salim", text)
        self.assertIn("Daftar baru di Stockbit (tidak dimuat): IDXNEW30", text)

    def test_many_changed_stock_lists_are_cut(self):
        changes = {f"KONGLO:{i}": {"name": f"G{i}", "added": ["AAAA"], "removed": []} for i in range(11)}
        text = build_stockbit_messages(self._with_stock_lists(
            {"status": "SUCCESS", "lists": 66, "members": 2000, "added": 11, "removed": 0, "changes": changes}))[0]
        self.assertIn("• G7: +AAAA", text)
        self.assertNotIn("• G8:", text)
        self.assertIn("…dan 3 daftar lain berubah", text)

    def test_a_failed_stock_list_step_is_a_warning_of_a_successful_round(self):
        text = build_stockbit_messages(self._with_stock_lists(
            {"status": "FAILED", "run_id": 4, "warning": "StockListError: Stockbit no longer shows INDEX:9 (IDX30)"}))[0]
        self.assertIn("Stockbit update APPLY SUCCESS", text)
        self.assertIn("⚠️ Indeks & grup tidak diperbarui", text)
        self.assertIn("Stockbit no longer shows INDEX:9 (IDX30)", text)

    def test_a_bounded_plan_difference_and_the_index_start_are_shown(self):
        value = StockbitUpdateSummary(
            execution_id="x", mode="APPLY", status="SUCCESS",
            started_at=datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc), token_expires_at=None,
            broker_dates=(), broker_rows=0, verify={}, last_error=None, events={},
            features={"changed_dates": [], "plan_shadow_equal": False,
                      "plan_shadow_bounded": {"changed": ["2026-11-09"], "index": []}},
            index_result={"from_date": "2026-11-10", "newest": {}},
        )
        text = build_stockbit_messages(value)[0]
        self.assertIn("⚠️ Rencana refresh terbatas beda dari rencana penuh", text)
        self.assertIn("INDEX: di-refresh dari 2026-11-10", text)

    def test_a_round_without_the_stock_list_step_has_no_section(self):
        self.assertNotIn("Indeks & grup", build_stockbit_messages(self._with_stock_lists({}))[0])


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
        # EXEC-PUBLISH-FLOW: a run away from the listed times is started by a loader's signal or by hand
        self.assertIn("run di luar jadwal (dipicu cron data atau manual) Thu 29 Oct 2026 22:03 WIB gagal", manual)

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


class ConsensusReportTests(unittest.TestCase):
    """EXEC-FI-DATE B (user go 2026-11-01, ERRORS M324): the weekly fixed-income consensus check, fixed shapes only."""

    RUN = "fi-consensus-US-2026-11-08-0000"

    def details(self, **over):
        return {"market": "US", "series": 26, "revised": 719, "missing": 1, "extra": 5, "unstable": 3,
                "items": [{"series": "US10Y/yield_to_maturity", "kind": "revised", "count": 719,
                           "first": "2016-01-04", "last": "2021-12-31"},
                          {"series": "US02Y/price", "kind": "missing", "count": 1, "first": "2026-10-21",
                           "last": "2026-10-21"}],
                "more_items": 0, "failed_series": [], "pulls": 3, "minutes": 9, "run_time": "2026-11-08 07:00", **over}

    def test_report_reads_in_plain_words(self):
        text = build_consensus_message(parse_consensus_report(self.RUN, self.details()))
        self.assertIn("⚠️ Cek konsensus fixed income mingguan — US, Sun 08 Nov 2026 07:00 WIB", text)
        self.assertIn("26 seri dibandingkan dengan 3 tarikan ulang TradingView (9 menit). Tidak ada data yang ditulis.", text)
        self.assertIn("Perlu keputusan: 719 nilai beda dari sumber, 1 tanggal tidak ada di database, 5 tanggal tidak ada di sumber", text)
        self.assertIn("• US10Y yield: 719 nilai beda dari sumber (04 Jan 2016 – 31 Dec 2021)", text)
        self.assertIn("• US02Y price: 1 tanggal tidak ada di database (21 Oct 2026)", text)
        self.assertIn("persetujuan Anda", text)
        clean = build_consensus_message(parse_consensus_report(
            "fi-consensus-manual-ID-2026-11-01-1130",
            self.details(market="ID", revised=0, missing=0, extra=0, unstable=0, items=[], run_time="2026-11-01 18:30")))
        self.assertIn("✅ Cek konsensus fixed income (manual) — ID", clean)
        self.assertIn("Semua seri sama dengan sumber.", clean)
        failed = build_consensus_message(parse_consensus_report(
            self.RUN, {"market": "US", "error": "ConnectionError", "pulls": 3, "minutes": 0, "run_time": "2026-11-08 07:00"}))
        self.assertIn("❌", failed)
        self.assertIn("Gagal: ConnectionError. Tidak ada data yang ditulis.", failed)

    def test_anything_but_the_fixed_shapes_is_refused(self):
        item = lambda **o: [{"series": "US02Y/price", "kind": "missing", "count": 1, "first": "2026-10-21",
                             "last": "2026-10-21", **o}]
        bad = [
            ("fi-consensus-ID-2026-11-08-0000", self.details()),           # market differs from the id
            ("consensus-US-2026-11-08", self.details()),
            (self.RUN, self.details(error="OSError: password=x")),
            (self.RUN, self.details(extra_field="x")),
            (self.RUN, self.details(revised=-1)),
            (self.RUN, self.details(series=True)),
            (self.RUN, self.details(items=item(series="../etc"))),
            (self.RUN, self.details(items=item(kind="deleted"))),
            (self.RUN, self.details(items=item(first="yesterday"))),
            (self.RUN, self.details(items=item(note="x"))),
            (self.RUN, self.details(failed_series=["drop table"])),
            (self.RUN, self.details(run_time="Sunday")),
            (self.RUN, "report"),
        ]
        for execution_id, details in bad:
            with self.assertRaises(ValueError, msg=(execution_id, details)):
                parse_consensus_report(execution_id, details)



class AuditQueueHealthTests(unittest.TestCase):
    """EXEC-M334-ALERT (user go 2026-11-02: "OK A, Jalankan"; ERRORS M334): the audit queues' alarm, fixed shapes only."""

    STUCK = "audit-queue-audit-store-stuck-2026-11-02"

    def details(self, **overrides):
        values = {"service": "audit-store", "status": "stuck", "waiting": 566, "oldest_minutes": 7260, "gave_up": 0,
                  "error": "ClientError", "limit_minutes": 60}
        values.update(overrides)
        return values

    def test_each_kind_reads_in_plain_words_with_the_service_to_check(self):
        stuck = build_audit_queue_message(parse_audit_queue(self.STUCK, self.details()))
        self.assertIn("macet", stuck)
        self.assertIn("566 item menunggu", stuck)
        self.assertIn("121 jam 0 menit", stuck)
        self.assertIn("ClientError", stuck)
        self.assertIn("market-audit-store", stuck)
        self.assertIn("M334", stuck)
        gave_up = build_audit_queue_message(parse_audit_queue(
            "audit-queue-sandbox-gaveup-2026-11-02",
            self.details(service="sandbox", status="gave_up", gave_up=3, oldest_minutes=None, error="AuditUnavailable")))
        self.assertIn("3 item berhenti dicoba", gave_up)
        self.assertIn("market-python-sandbox", gave_up)
        unread = build_audit_queue_message(parse_audit_queue(
            "audit-queue-sql-governor-stuck-2026-11-02", self.details(service="sql-governor", waiting=None)))
        self.assertIn("jumlahnya tidak terbaca", unread)
        recovered = build_audit_queue_message(parse_audit_queue(
            "audit-queue-audit-store-recovered-2026-11-02", self.details(status="recovered", waiting=0,
                                                                         oldest_minutes=None, error=None)))
        self.assertIn("pulih", recovered)
        self.assertIn("tidak ada yang masih menunggu", recovered)

    def test_anything_but_the_fixed_shapes_is_refused(self):
        for execution_id, details in (
            (self.STUCK, self.details(service="sandbox")),                          # service differs from the id
            (self.STUCK, self.details(status="recovered")),                         # status differs from the id
            ("audit-queue-orc-stuck-2026-11-02", self.details(service="orc")),      # not an audit queue
            (self.STUCK, self.details(error="ClientError: An error occurred (403) bucket x")),   # free text
            (self.STUCK, self.details(waiting=-1)),
            (self.STUCK, self.details(oldest_minutes=None)),                        # stuck needs its age
            ("audit-queue-audit-store-gaveup-2026-11-02", self.details(status="gave_up", gave_up=0)),
            (self.STUCK, self.details(note="hello")),                               # unknown field
            (self.STUCK, None),
        ):
            with self.subTest(execution_id=execution_id, details=details):
                with self.assertRaises(ValueError):
                    parse_audit_queue(execution_id, details)

    def test_the_monitor_sends_it_once_per_id(self):
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
            self.assertEqual(monitor.notify(tm.AUDIT_QUEUE_SOURCE, self.STUCK, self.details())[0], "sent")
            self.assertEqual(monitor.notify(tm.AUDIT_QUEUE_SOURCE, self.STUCK, self.details())[0], "duplicate")
        finally:
            tm.psycopg.connect, tm.claim_delivery, tm.mark_sent = saved
        self.assertEqual(len(sent), 1)

class PostgresRestartTests(unittest.TestCase):
    """EXEC-PG-RESTART-CRON (user go 2026-11-03): postgres-memory-cron's reports, fixed shapes only."""

    def report(self, kind="scheduled", event="success", **overrides):
        values = {"kind": kind, "event": event, "mode": "apply", "auto": True, "times_wib": "09:45,20:45",
                  "memory_gb": 3.9, "waited_minutes": 0, "seconds": 14, "edge_ready": 200, "memory_after_gb": 0.12}
        values.update(overrides)
        return f"pg-restart-{kind}-20261103T1345-{event}", values

    def message(self, kind="scheduled", event="success", **overrides):
        import telegram_monitor as tm
        return tm.build_postgres_restart_message(tm.parse_postgres_restart(*self.report(kind, event, **overrides)))

    def test_each_event_reads_in_plain_words(self):
        success = self.message()
        self.assertIn("✅ Restart Postgres sukses (terjadwal)", success)
        self.assertIn("14 detik", success)
        self.assertIn("3.90 GB → 0.12 GB", success)
        self.assertIn("Restart otomatis ON, jam 09:45 dan 20:45 WIB", success)
        manual = self.message("manual-telegram", "manual", seconds=None, edge_ready=None, memory_after_gb=None)
        self.assertIn("🔔 Permintaan restart Postgres diterima (manual dari tombol Telegram)", manual)
        started = self.message("manual-railway", "started", waited_minutes=10)
        self.assertIn("⏳ Restart Postgres dimulai (manual dari dashboard Railway)", started)
        self.assertIn("Sudah menunggu 10 menit", started)
        refused = self.message("manual-telegram", "refused", reasons=["cron_due", "user_runs"], auto=False)
        self.assertIn("⚠️ Restart Postgres tidak dijalankan", refused)
        self.assertIn("ada cron lain dalam 45 menit; ada pertanyaan user yang sedang berjalan di EDGE", refused)
        self.assertIn("Restart otomatis OFF", refused)
        failed = self.message(event="failed", reasons=["postgres_not_back"])
        self.assertIn("❌", failed)
        self.assertIn("tidak hidup kembali", failed)
        check = self.message(event="check", mode="check", would_restart=False, reasons=["memory_low"])
        self.assertIn("🧪 Uji restart Postgres", check)
        self.assertIn("tidak akan dijalankan (memori rendah", check)

    def test_anything_but_the_fixed_shapes_is_refused(self):
        import telegram_monitor as tm
        bad = [
            self.report(kind="scheduled", event="success", kind_="x"),                 # unknown field
            self.report(event="refused"),                                             # refused needs a reason
            self.report(event="check", mode="check"),                                 # check needs would_restart
            self.report(reasons=["rm -rf"]),                                          # free text as a reason
            self.report(times_wib="9:45; drop"),
            self.report(memory_gb=-1),
            self.report(seconds=True),
            self.report(mode="force"),
            ("pg-restart-other-20261103T1345-success", self.report()[1]),            # unknown kind
            (self.report()[0], dict(self.report()[1], event="started")),             # event differs from the id
            (self.report()[0], None),
        ]
        for execution_id, details in bad:
            with self.subTest(execution_id=execution_id, details=details):
                with self.assertRaises(ValueError):
                    tm.parse_postgres_restart(execution_id, details)

    def test_the_monitor_sends_it_once_per_id(self):
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
            self.assertEqual(monitor.notify(tm.POSTGRES_RESTART_SOURCE, *self.report())[0], "sent")
            self.assertEqual(monitor.notify(tm.POSTGRES_RESTART_SOURCE, *self.report())[0], "duplicate")
        finally:
            tm.psycopg.connect, tm.claim_delivery, tm.mark_sent = saved
        self.assertEqual(len(sent), 1)
        self.assertIn("sukses", sent[0])


class PublishSignalTests(unittest.TestCase):
    """EXEC-PUBLISH-FLOW (user go 2026-11-05: "kalau cron selesai, dia trigger ke publisher")."""

    class Conn:
        def __init__(self, inserted=True, changed_series=0):
            self.sql, self.inserted, self.changed_series, self.commits = [], inserted, changed_series, 0

        def execute(self, sql, params=()):
            self.sql.append((sql, params))
            conn = self
            class Result:
                def fetchone(self):
                    return (7,) if "INSERT INTO" in sql and conn.inserted else None
            return Result()

        def cursor(self):
            conn = self
            class Cursor:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def execute(self, sql, params=()): conn.sql.append((sql, params))
                def fetchone(self): return (conn.changed_series,)
            return Cursor()

        def commit(self): self.commits += 1
        def rollback(self): pass

    def monitor(self, run_now=None):
        import os
        sent = []
        m = TelegramMonitor.__new__(TelegramMonitor)
        m.token, m.chat_id = "t", "c"
        m.send_message = lambda token, chat, text, *a: sent.append(text) or 1
        m.run_now = run_now or (lambda token, instance: True)
        os.environ["PUBLISH_RAILWAY_TOKEN"] = "x" * 36
        os.environ["TERMINAL_PUBLISHER_SERVICE_INSTANCE_ID"] = "33466de4-5f96-4a01-bb9c-e851f2be2d3f"
        os.environ.pop("PUBLISH_TRIGGER_ENABLED", None)
        return m, sent

    def tearDown(self):
        import os
        for name in ("PUBLISH_RAILWAY_TOKEN", "TERMINAL_PUBLISHER_SERVICE_INSTANCE_ID", "PUBLISH_TRIGGER_ENABLED"):
            os.environ.pop(name, None)

    def test_a_finished_run_that_changed_data_records_one_signal_and_presses_run_now(self):
        pressed = []
        m, sent = self.monitor(lambda token, instance: pressed.append(instance) or True)
        conn = self.Conn()
        self.assertEqual(m.request_publication(conn, "Monitoring_Price_ALL", "e1", "DAILY", 845), "triggered")
        self.assertEqual(pressed, ["33466de4-5f96-4a01-bb9c-e851f2be2d3f"])
        self.assertIn("TRIGGERED", conn.sql[-1][1])
        self.assertEqual(sent, [])

    def test_nothing_starts_without_a_change_twice_or_when_switched_off(self):
        import os
        pressed = []
        m, _ = self.monitor(lambda token, instance: pressed.append(1) or True)
        self.assertEqual(m.request_publication(self.Conn(), "Monitoring_Fixed_Income", "e2", "RECOVERY", 0), "not_needed")
        self.assertEqual(m.request_publication(self.Conn(inserted=False), "Monitoring_Price_ALL", "e1", "DAILY", 9),
                         "duplicate")
        os.environ["PUBLISH_TRIGGER_ENABLED"] = "false"
        self.assertEqual(m.request_publication(self.Conn(), "Monitoring_Price_ALL", "e3", "DAILY", 9), "disabled")
        self.assertEqual(pressed, [])

    def test_a_refused_run_now_is_told_at_once_and_a_missing_token_is_recorded(self):
        import os
        def refused(token, instance):
            raise RuntimeError("Railway API refused the Run Now request")
        m, sent = self.monitor(refused)
        conn = self.Conn()
        self.assertEqual(m.request_publication(conn, "Monitoring_Stockbit_Update", "e4", None, 23000), "failed")
        self.assertIn("RuntimeError", conn.sql[-1][1])
        self.assertEqual(len(sent), 1)
        self.assertIn("Pemicu Terminal publisher gagal", sent[0])
        self.assertNotIn("x" * 36, sent[0])
        m, sent = self.monitor()
        os.environ.pop("PUBLISH_RAILWAY_TOKEN")
        conn = self.Conn()
        self.assertEqual(m.request_publication(conn, "Monitoring_Price_ALL", "e5", "DAILY", 3), "not_configured")
        self.assertEqual(sent, [])

    def test_what_changed_comes_from_each_loader_s_own_facts(self):
        from telegram_monitor import publish_changed
        price = summary(updated_symbols=844, run_type="RECOVERY")
        self.assertEqual(publish_changed(self.Conn(), "Monitoring_Price_ALL", "e", price), (844, "RECOVERY"))
        fi = summary(updated_symbols=26, run_type="RECOVERY")
        self.assertEqual(publish_changed(self.Conn(changed_series=0), "Monitoring_Fixed_Income",
                                         "00000000-0000-0000-0000-000000000000", fi), (0, "RECOVERY"))
        failed = StockbitUpdateSummary("e", "APPLY", "FAILED", datetime(2026, 11, 5, tzinfo=timezone.utc),
                                       datetime(2026, 11, 5, tzinfo=timezone.utc), None, (), None, {}, {}, {}, {}, "x")
        self.assertEqual(publish_changed(self.Conn(), "Monitoring_Stockbit_Update", "e", failed), (0, None))
        done = StockbitUpdateSummary("e", "APPLY", "SUCCESS", datetime(2026, 11, 5, tzinfo=timezone.utc),
                                     datetime(2026, 11, 5, tzinfo=timezone.utc), None, ("2026-11-04",), 23000, {}, {},
                                     {}, {}, None)
        self.assertEqual(publish_changed(self.Conn(), "Monitoring_Stockbit_Update", "e", done), (23000, None))

    def test_the_intraday_request_has_a_fixed_shape(self):
        from telegram_monitor import parse_publish_request
        self.assertEqual(parse_publish_request("intraday-1", {"loader": "idx-intraday-cron", "changed": 38505}),
                         ("idx-intraday-cron", 38505))
        for details in ({"loader": "idx-intraday-cron"}, {"loader": "Bad Name", "changed": 1},
                        {"loader": "idx-intraday-cron", "changed": -1}, {"loader": "x", "changed": True},
                        {"loader": "x", "changed": 1, "note": "free text"}, None):
            with self.assertRaises(ValueError):
                parse_publish_request("intraday-1", details)

    def test_the_publisher_waiting_alert_reads_in_plain_words(self):
        health = parse_publisher_health("terminal-publish-manual-2026-11-05-1702-waiting",
                                        {"status": "waiting", "run_time": "2026-11-05 17:02", "manual": True,
                                         "stage": "loaders", "minutes": 45})
        text = build_publisher_message(health)
        self.assertIn("menunggu cron data selesai lebih dari 45 menit", text)
        self.assertIn("dipicu cron data", text)

if __name__ == "__main__":
    unittest.main()


def test_the_radar_step_is_one_line_and_its_failure_a_warning():
    """EXEC-RADAR R2: features.radar of the round (QA 2026-11-14: a Radar failure no longer fails the round)."""
    import telegram_monitor as tm
    assert tm.radar_lines(None) == [] and tm.radar_lines({"skipped": "not backfilled"}) == []
    assert tm.radar_lines({"tickers": 2, "since": "2026-11-06", "dates": ["2026-11-06", "2026-11-09"]}) == [
        "Radar: 2 tanggal dihitung ulang (dari 2026-11-06)"]
    line = tm.radar_lines({"failed": "RefreshFailed: Feature 07 reconcile"})[0]
    assert line.startswith("⚠️ Radar tidak diperbarui") and "RefreshFailed" in line
