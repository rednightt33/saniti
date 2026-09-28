"""Publication dates: read deterministically from provider metadata, the page's own metadata, the URL, or the text,
and always recorded with where they came from."""
from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = {
    "jan": 1, "januari": 1, "january": 1, "feb": 2, "februari": 2, "february": 2, "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4, "mei": 5, "may": 5, "jun": 6, "juni": 6, "june": 6, "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "agustus": 8, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "okt": 10,
    "oktober": 10, "oct": 10, "october": 10, "nov": 11, "november": 11, "des": 12, "desember": 12, "dec": 12,
    "december": 12,
}
_MONTH_WORDS = "|".join(sorted(MONTHS, key=len, reverse=True))


def _valid(year: int, month: int, day: int) -> date | None:
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    return value if 1990 <= year <= 2100 else None


def from_iso(value: str | None) -> date | None:
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    return _valid(*map(int, match.groups())) if match else None


def from_url(url: str) -> tuple[date, str] | None:
    """Dates that news sites put in their URLs: /2026/09/18/, /read/20260918/, /20260918154641-..."""
    match = re.search(r"/(20\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?:/|$|[^0-9])", url)
    if match:
        value = _valid(*map(int, match.groups()))
        if value:
            return value, "DAY"
    match = re.search(r"(?<![0-9])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?=\d{0,6}(?:[^0-9]|$))", url)
    if match:
        value = _valid(*map(int, match.groups()))
        if value:
            return value, "DAY"
    match = re.search(r"/(20\d{2})/(0[1-9]|1[0-2])/", url)
    if match:
        value = _valid(int(match.group(1)), int(match.group(2)), 1)
        if value:
            return value, "MONTH"
    return None


def from_text(text: str | None, window: int = 160) -> tuple[date, str] | None:
    """A dateline at the start of an excerpt ("Jakarta, 12 September 2026 -", "14 Sep 2026 ...")."""
    if not text:
        return None
    head = text[:window].lower()
    match = re.search(rf"(?<![0-9])(\d{{1,2}})\s+({_MONTH_WORDS})\.?\s+(20\d{{2}})", head)
    if match:
        value = _valid(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1)))
        if value:
            return value, "DAY"
    match = re.search(r"(?<![0-9])(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?![0-9])", head)
    if match:
        value = _valid(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if value:
            return value, "DAY"
    return None


def resolve(provider_value: str | None, page_value: str | None, url: str, text: str | None,
            latest: date | None = None) -> dict[str, object]:
    """Pick the most reliable publication date. A date after `latest` (the task's as-of date) is rejected."""
    candidates: list[tuple[date, str, str]] = []
    if (value := from_iso(provider_value)):
        candidates.append((value, "DAY", "PROVIDER"))
    if (value := from_iso(page_value)):
        candidates.append((value, "DAY", "HTML_META"))
    if (found := from_url(url)):
        candidates.append((found[0], found[1], "URL"))
    if (found := from_text(text)):
        candidates.append((found[0], found[1], "TEXT"))
    for value, precision, source in candidates:
        if latest and value > latest:
            continue
        return {"published_at": value.isoformat(), "published_precision": precision, "published_at_source": source}
    return {"published_at": None, "published_precision": "UNKNOWN", "published_at_source": "UNKNOWN"}


def temporal_status(published: str | None, precision: str, anchor: date | None) -> tuple[str | None, int | None]:
    """PRE_EVENT only when the whole publication period ends before the anchor date."""
    if anchor is None:
        return None, None
    value = from_iso(published)
    if value is None or precision == "UNKNOWN":
        return "UNDATED", None
    if precision == "MONTH":
        next_month = date(value.year + (value.month == 12), value.month % 12 + 1, 1)
        if next_month <= anchor:
            return "PRE_EVENT", (anchor - value).days
        if value >= anchor.replace(day=1) and value.month == anchor.month and value.year == anchor.year:
            return "UNDATED", None
        return "POST_EVENT_RETROSPECTIVE", None
    if value < anchor:
        return "PRE_EVENT", (anchor - value).days
    return "POST_EVENT_RETROSPECTIVE", None


def today() -> date:
    return datetime.now().date()
