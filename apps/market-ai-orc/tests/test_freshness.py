"""1c / D06 (round 2026-10-03): a dataset's freshness is derived from its catalog SLA and last date when the catalog is
read; 1b: a range ending LATEST overlaps every later dated range."""
from __future__ import annotations

from datetime import date

from app.freshness import freshness, sla_days
from app.in_sample import _overlap

MONDAY = date(2026, 10, 5)


def test_sla_text_in_days() -> None:
    assert sla_days("1 day") == 1 and sla_days("30 days") == 30 and sla_days("365 days") == 365
    assert sla_days("1 day 12:00:00") == 1.5 and sla_days("1 mon") == 30 and sla_days("12:00:00") == 0.5
    assert sla_days(None) is None and sla_days("") is None and sla_days("soon") is None


def test_a_daily_table_counts_weekdays() -> None:
    row = {"coverage_mode": "ACTUAL_SOURCE", "actual_max_date": "2026-10-02"}  # Friday
    assert freshness(row, "1 day", MONDAY)["status"] == "SEGAR"  # the weekend is not lateness
    assert freshness({**row, "actual_max_date": "2026-10-01"}, "1 day", MONDAY)["status"] == "TERLAMBAT"
    stale = freshness({**row, "actual_max_date": "2026-09-28"}, "1 day", MONDAY)
    assert stale["status"] == "BASI" and stale["age_days"] == 5 and stale["age_basis"] == "WEEKDAYS"


def test_a_derived_table_uses_its_expected_date_and_a_long_sla_calendar_days() -> None:
    derived = {"coverage_mode": "EXPECTED_DERIVED", "actual_max_date": None, "expected_max_date": "2026-10-02"}
    assert freshness(derived, "1 day", MONDAY)["last_date"] == "2026-10-02"
    monthly = freshness({"coverage_mode": "ACTUAL_SOURCE", "actual_max_date": "2026-08-20"}, "30 days", MONDAY)
    assert monthly["status"] == "TERLAMBAT" and monthly["age_basis"] == "CALENDAR_DAYS"


def test_unknown_and_not_applicable() -> None:
    assert freshness({"coverage_mode": "ACTUAL_SOURCE", "actual_max_date": "2026-10-02"}, None,
                     MONDAY)["status"] == "UNKNOWN"
    assert freshness({"coverage_mode": "ACTUAL_SOURCE"}, "1 day", MONDAY)["status"] == "UNKNOWN"
    assert freshness({"coverage_mode": "SNAPSHOT"}, "30 days", MONDAY)["status"] == "NOT_APPLICABLE"


def test_a_latest_end_overlaps_later_ranges() -> None:
    assert _overlap(("2026-01-01", "LATEST"), ("2026-09-01", "2026-10-02"))
    assert not _overlap(("2026-01-01", "LATEST"), ("2025-01-01", "2025-12-31"))
