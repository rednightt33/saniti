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


def schedule(
    code="ID",
    zone="Asia/Jakarta",
    close=time(16),
    delay=60,
    mapping="CURRENT_OR_PREVIOUS_BUSINESS_DAY",
):
    return module.MarketSchedule(code, "Indonesia", zone, close, delay, mapping, True)


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


def test_tls_cannot_be_disabled(monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_VERIFY_TLS", "false")
    with pytest.raises(RuntimeError, match="must remain enabled"):
        module.open_socket(1, False)
