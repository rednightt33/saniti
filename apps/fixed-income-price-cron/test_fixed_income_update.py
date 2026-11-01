from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("fixed_income_update.py")
SPEC = importlib.util.spec_from_file_location("fixed_income_update", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

RECOVERY_PATH = Path(__file__).with_name("recovery_window.py")
RECOVERY_SPEC = importlib.util.spec_from_file_location("fixed_recovery_window", RECOVERY_PATH)
recovery_module = importlib.util.module_from_spec(RECOVERY_SPEC)
assert RECOVERY_SPEC.loader is not None
RECOVERY_SPEC.loader.exec_module(recovery_module)


def schedule(
    code="ID",
    zone="Asia/Jakarta",
    close=time(16),
    delay=60,
    mapping="CURRENT_OR_PREVIOUS_BUSINESS_DAY",
):
    return module.MarketSchedule(code, "Indonesia", zone, close, delay, mapping, True, 5)


def test_recovery_window_includes_unobserved_latest_candidate():
    observed = [date(2026, 9, day) for day in (7, 8, 9, 10, 11)]
    assert recovery_module.correction_target_dates(
        observed, date(2026, 9, 14), 5
    ) == [*observed[1:], date(2026, 9, 14)]


def test_recovery_window_includes_both_missing_recent_sessions():
    observed = [date(2026, 10, day) for day in (5, 6, 7, 8, 9)]
    assert recovery_module.correction_target_dates(observed, date(2026, 10, 13), 5) == [
        date(2026, 10, day) for day in (7, 8, 9, 12, 13)
    ]


@pytest.mark.parametrize("raw,expected", [
    (datetime(2026, 10, 12, 21, tzinfo=timezone.utc), date(2026, 10, 13)),
    (datetime(2026, 10, 11, 21, tzinfo=timezone.utc), date(2026, 10, 12)),
    (datetime(2026, 1, 11, 22, tzinfo=timezone.utc), date(2026, 1, 12)),
    (datetime(2026, 10, 12, 23, tzinfo=timezone.utc), date(2026, 10, 13)),
])
def test_observed_provider_session_anchors(raw, expected):
    assert module.resolve_bar_date(
        int(raw.timestamp()), "America/New_York", "NEXT_BUSINESS_DAY"
    ) == expected


def test_latest_completed_session_waits_for_close_delay():
    item = schedule()
    assert module.latest_completed_session(
        item, datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc)
    ) == date(2026, 10, 9)
    assert module.latest_completed_session(
        item, datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    ) == date(2026, 10, 12)


def test_latest_completed_session_maps_weekend_to_friday():
    assert module.latest_completed_session(
        schedule(), datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    ) == date(2026, 10, 9)


def test_us_market_close_tracks_dst():
    us = schedule("US", "America/New_York", time(17), 60)
    assert module.market_close_at(us, date(2026, 1, 12)) == datetime(
        2026, 1, 12, 22, 0, tzinfo=timezone.utc
    )
    assert module.market_close_at(us, date(2026, 7, 13)) == datetime(
        2026, 7, 13, 21, 0, tzinfo=timezone.utc
    )


def test_scheduled_detection_allows_fixed_utc_cron_across_us_dst():
    us = schedule("US", "America/New_York", time(17), 60)
    assert module.resolve_trigger_source(
        "daily", us, datetime(2026, 1, 12, 23, 0, tzinfo=timezone.utc), 90
    ) == "SCHEDULED"
    assert module.resolve_trigger_source(
        "daily", us, datetime(2026, 7, 13, 23, 0, tzinfo=timezone.utc), 90
    ) == "SCHEDULED"


def test_provider_timezone_resolves_session_date():
    timestamp = int(datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc).timestamp())
    assert module.resolve_bar_date(
        timestamp, "America/New_York", "CURRENT_OR_PREVIOUS_BUSINESS_DAY"
    ) == date(2026, 10, 9)


def test_us_daily_label_uses_utc_calendar_component():
    timestamp = int(datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc).timestamp())
    assert module.resolve_bar_date(
        timestamp, "America/New_York", "CURRENT_OR_PREVIOUS_BUSINESS_DAY"
    ) == date(2026, 10, 9)


def test_weekend_bond_bar_timestamp_maps_to_friday_observation():
    timestamp = int(datetime(2026, 10, 11, 0, 0, tzinfo=timezone.utc).timestamp())
    assert module.resolve_bar_date(
        timestamp, "Etc/UTC", "CURRENT_OR_PREVIOUS_BUSINESS_DAY"
    ) == date(2026, 10, 9)


def test_us_source_label_maps_to_next_business_day():
    thursday = int(datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc).timestamp())
    friday = int(datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc).timestamp())
    assert module.resolve_bar_date(
        thursday, "America/New_York", "NEXT_BUSINESS_DAY"
    ) == date(2026, 10, 9)
    assert module.resolve_bar_date(
        friday, "America/New_York", "NEXT_BUSINESS_DAY"
    ) == date(2026, 10, 5)


def test_invalid_provider_timezone_fails_closed():
    with pytest.raises(ValueError, match="invalid timezone"):
        module.resolve_bar_date(
            0, "Not/A_Zone", "CURRENT_OR_PREVIOUS_BUSINESS_DAY"
        )


def test_unknown_source_date_mapping_fails_closed():
    with pytest.raises(ValueError, match="Unsupported source date mapping"):
        module.resolve_bar_date(0, "Etc/UTC", "UNKNOWN")


def test_candle_selection_requires_exact_target_date():
    prior = {
        "date": date(2026, 10, 8),
        "open": 99,
        "high": 100,
        "low": 98,
        "close": 99,
        "volume": None,
    }
    assert module.candle_for_target([prior], date(2026, 10, 9)) is None


def test_candle_validation_preserves_nullable_bond_volume():
    row = {
        "date": date(2026, 10, 9),
        "open": "99",
        "high": "100",
        "low": "98",
        "close": "99.5",
        "volume": None,
    }
    result = module.candle_for_target([row], date(2026, 10, 9))
    assert result["close"] == Decimal("99.5")
    assert result["volume"] is None


def test_invalid_ohlc_fails_closed():
    row = {"open": 101, "high": 100, "low": 98, "close": 99, "volume": 0}
    with pytest.raises(ValueError, match="open"):
        module.validate_price_row(row)


@pytest.mark.parametrize(
    ("queried", "verified", "expected"),
    [(0, 0, "SKIPPED"), (10, 10, "SUCCESS"), (10, 0, "FAILED"), (10, 8, "PARTIAL")],
)
def test_monitoring_status(queried, verified, expected):
    assert module.monitoring_status(queried, verified) == expected


def test_partition_keeps_every_series_once():
    items = list(range(11))
    chunks = module.partition(items, 4)
    assert [x for chunk in chunks for x in chunk] == items
    assert max(map(len, chunks)) - min(map(len, chunks)) <= 1


def test_parse_frames_returns_payload_and_heartbeat():
    event = module.frame("series_completed", ["cs", "s1"])
    heartbeat = "~h~42"
    raw = event + f"~m~{len(heartbeat)}~m~{heartbeat}"
    objects, heartbeats = module.parse_frames(raw)
    assert objects == [{"m": "series_completed", "p": ["cs", "s1"]}]
    assert heartbeats == [f"~m~{len(heartbeat)}~m~{heartbeat}"]


class FakeSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    def send(self, value):
        self.sent.append(value)

    def recv(self):
        return next(self.messages)

    def settimeout(self, _value):
        pass


class FakeCopy:
    def __init__(self):
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write_row(self, row):
        self.rows.append(row)


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.copy_context = FakeCopy()
        self.results = iter([(1,), (1,)])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query):
        self.queries.append(query)

    def copy(self, query):
        self.queries.append(query)
        return self.copy_context

    def fetchone(self):
        return next(self.results)


class FakeConnection:
    def __init__(self):
        self.cursor_context = FakeCursor()

    def cursor(self):
        return self.cursor_context


def test_bulk_upsert_stage_does_not_inherit_unwritten_required_columns():
    row = {column: None for column in module.PRICE_COLUMNS}
    row.update(
        {
            "Country": "United States",
            "instrument_name": "US 10Y",
            "ticker": "US10Y",
            "tradingview_symbol": "TVC:US10",
            "date": date(2026, 10, 9),
            "open": Decimal("99"),
            "high": Decimal("100"),
            "low": Decimal("98"),
            "close": Decimal("99.5"),
            "source": "TradingView",
            "query_date": date(2026, 10, 12),
            "metric_type": "price",
            "value_unit": "PCTPAR",
            "Timeframe": "1D",
            "source_bar_time": datetime(2026, 10, 8, tzinfo=timezone.utc),
            "market_close_at": datetime(2026, 10, 9, 21, tzinfo=timezone.utc),
            "is_final": True,
            "finalized_at": datetime(2026, 10, 12, tzinfo=timezone.utc),
        }
    )
    connection = FakeConnection()
    assert module.bulk_upsert_prices(connection, [row]) == (1, 1)
    create_stage = connection.cursor_context.queries[0]
    assert "WITH NO DATA" in create_stage
    assert " LIKE " not in create_stage
    assert len(connection.cursor_context.copy_context.rows) == 1


def test_request_series_keeps_source_timestamp_and_exact_session(monkeypatch):
    monkeypatch.setattr(module.random, "randrange", lambda _n: 1)
    timestamp = int(datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc).timestamp())
    resolved = module.frame(
        "symbol_resolved",
        ["cs", "symbol_1_1", {"timezone": "America/New_York"}],
    )
    updated = module.frame(
        "timescale_update",
        ["cs", {"s1": {"s": [{"v": [timestamp, 99, 100, 98, 99.5, None]}]}}],
    )
    completed = module.frame("series_completed", ["cs", "s1"])
    ws = FakeSocket([resolved, updated, completed])
    series = module.Series(1, "United States", "US 10Y", "US10Y", "TVC:US10", "price", "PCTPAR")
    final_at = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)
    rows, provider_zone = module.request_series(
        ws,
        "cs",
        series,
        7,
        5,
        date(2026, 10, 9),
        date(2026, 10, 9),
        datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc),
        final_at,
        "NEXT_BUSINESS_DAY",
    )
    assert provider_zone == "America/New_York"
    assert rows[0]["date"] == date(2026, 10, 9)
    assert rows[0]["source_bar_time"] == datetime.fromtimestamp(timestamp, timezone.utc)
    assert rows[0]["is_final"] is True
    assert rows[0]["finalized_at"] == final_at


@pytest.mark.parametrize("actual_zone,actual_session", [
    ("Etc/UTC", "1700-1700"),
    ("America/New_York", "1900-1730"),
    ("America/New_York", None),
])
def test_source_session_drift_is_rejected(monkeypatch, actual_zone, actual_session):
    monkeypatch.setattr(module.random, "randrange", lambda _n: 1)
    ws = FakeSocket([
        module.frame("symbol_resolved", ["cs", "symbol_1_1", {
            "timezone": actual_zone, "session": actual_session,
        }]),
        module.frame("series_completed", ["cs", "s1"]),
    ])
    series = module.Series(1, "Indonesia", "ID 10Y", "ID10Y", "TVC:ID10", "price", "PCTPAR")
    stamp = datetime(2026, 10, 13, 10, tzinfo=timezone.utc)
    with pytest.raises(RuntimeError, match="SOURCE_SESSION_MISMATCH"):
        module.request_series(
            ws, "cs", series, 7, 5, stamp.date(), stamp.date(), stamp, stamp,
            "NEXT_BUSINESS_DAY", "America/New_York", "1700-1700",
        )


def test_tls_cannot_be_disabled(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_VERIFY_TLS", "false")
    with pytest.raises(RuntimeError, match="must remain enabled"):
        module.open_socket(1, False)


# EXEC-FI-DATE (ERRORS M323, user go 2026-11-01): the session-start rule on the labels TradingView actually gives
# (verification/fixed_income_audit/REPORT.md), on both sides of the daylight-saving switches and around holidays.
@pytest.mark.parametrize("raw,session,expected", [
    (datetime(2025, 10, 30, 23, tzinfo=timezone.utc), "1900-1730", date(2025, 10, 31)),   # US EDT: 19:00 NY Thu -> Fri
    (datetime(2025, 11, 3, 0, tzinfo=timezone.utc), "1900-1730", date(2025, 11, 3)),      # US EST: 19:00 NY Sun -> Mon
    (datetime(2026, 3, 6, 0, tzinfo=timezone.utc), "1900-1730", date(2026, 3, 6)),        # US EST Fri
    (datetime(2026, 3, 8, 23, tzinfo=timezone.utc), "1900-1730", date(2026, 3, 9)),       # US EDT Sun -> Mon
    (datetime(2016, 1, 15, 0, tzinfo=timezone.utc), "1900-1730", date(2016, 1, 15)),      # Fri before the MLK holiday
    (datetime(2016, 1, 19, 0, tzinfo=timezone.utc), "1900-1730", date(2016, 1, 19)),      # Tue after it
    (datetime(2016, 3, 6, 22, tzinfo=timezone.utc), "1700-1700", date(2016, 3, 7)),       # ID EST Sun 17:00 NY -> Mon
    (datetime(2016, 7, 3, 21, tzinfo=timezone.utc), "1700-1700", date(2016, 7, 4)),       # ID EDT Sun -> Mon
    (datetime(2026, 10, 29, 21, tzinfo=timezone.utc), "1700-1700", date(2026, 10, 30)),   # ID Thu evening -> Fri
])
def test_session_start_rule_reads_the_label_in_the_provider_zone(raw, session, expected):
    assert module.resolve_bar_date(int(raw.timestamp()), "America/New_York", "PROVIDER_SESSION_START", session) == expected


def test_session_start_rule_gives_one_date_per_bar_across_the_march_switch():
    labels = [datetime(2026, 3, 5, 0, tzinfo=timezone.utc), datetime(2026, 3, 6, 0, tzinfo=timezone.utc),
              datetime(2026, 3, 8, 23, tzinfo=timezone.utc), datetime(2026, 3, 9, 23, tzinfo=timezone.utc)]
    dates = [module.resolve_bar_date(int(t.timestamp()), "America/New_York", "PROVIDER_SESSION_START", "1900-1730") for t in labels]
    assert dates == [date(2026, 3, 5), date(2026, 3, 6), date(2026, 3, 9), date(2026, 3, 10)]
    old = [module.resolve_bar_date(int(t.timestamp()), "America/New_York", "NEXT_BUSINESS_DAY") for t in labels]
    assert old.count(date(2026, 3, 9)) == 2                                           # the collision M323 found


def test_session_start_rule_needs_the_session():
    with pytest.raises(ValueError, match="needs the provider session"):
        module.resolve_bar_date(0, "America/New_York", "PROVIDER_SESSION_START", None)


def test_two_bars_on_one_date_refuse_the_series():
    rows = [{"date": date(2026, 3, 9)}, {"date": date(2026, 3, 9)}]
    with pytest.raises(RuntimeError, match="SOURCE_DATE_COLLISION"):
        module.check_unique_dates(rows, "TVC:US10Y")
    module.check_unique_dates([{"date": date(2026, 3, 9)}, {"date": date(2026, 3, 10)}], "TVC:US10Y")
