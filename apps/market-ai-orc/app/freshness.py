"""Freshness of a catalog dataset: SEGAR, TERLAMBAT or BASI (1c / D06, round 2026-10-03; ROUND_PLAN B4).

Derived when the catalog is read, from AI_table_catalog.freshness_sla and the dataset's last date in
AI_data_coverage (actual_max_date, else expected_max_date for a derived dataset), against the run's reference date:
SEGAR when the age is at most the SLA, TERLAMBAT up to twice the SLA, BASI beyond. Without an SLA or a last date the
status is UNKNOWN; a SNAPSHOT dataset has no date range (NOT_APPLICABLE).

Age: for an SLA shorter than a week (a daily market table), the weekdays after the last date up to the reference date,
so a weekend does not make Monday's data late; public holidays are not in the catalog, so the day after a holiday
reads one day older than it is. For an SLA of a week or more, calendar days.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

INTERVAL = re.compile(r"(?:(\d+)\s+years?)?\s*(?:(\d+)\s+mons?)?\s*(?:(\d+)\s+days?)?\s*(?:(\d+):(\d+)(?::[\d.]+)?)?$")
WEEKDAY_BASIS_BELOW_DAYS = 7


def sla_days(text: Any) -> float | None:
    """A PostgreSQL interval's text ("1 day", "30 days", "1 day 12:00:00", "1 mon") in days."""
    if not isinstance(text, str) or not text.strip():
        return None
    match = INTERVAL.fullmatch(text.strip())
    if not match or not any(match.groups()):
        return None
    years, months, days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    total = years * 365 + months * 30 + days + hours / 24 + minutes / 1440
    return total if total > 0 else None


def _weekdays_after(last: date, today: date) -> int:
    return sum(1 for n in range(1, (today - last).days + 1) if (last + timedelta(days=n)).weekday() < 5)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def freshness(row: dict[str, Any], sla: Any, today: date) -> dict[str, Any]:
    """{status, last_date, age_days, age_basis, sla_days} of one coverage row."""
    if row.get("coverage_mode") == "SNAPSHOT":
        return {"status": "NOT_APPLICABLE", "reason": "SNAPSHOT: current-state data without a date range."}
    last = _as_date(row.get("actual_max_date")) or _as_date(row.get("expected_max_date"))
    limit = sla_days(sla)
    if last is None or limit is None:
        return {"status": "UNKNOWN", "reason": "no freshness SLA" if limit is None else "no last date"}
    weekdays = limit < WEEKDAY_BASIS_BELOW_DAYS
    age = _weekdays_after(last, today) if weekdays else max((today - last).days, 0)
    status = "SEGAR" if age <= limit else "TERLAMBAT" if age <= 2 * limit else "BASI"
    return {"status": status, "last_date": last.isoformat(), "age_days": age,
            "age_basis": "WEEKDAYS" if weekdays else "CALENDAR_DAYS", "sla_days": limit, "as_of": today.isoformat()}
