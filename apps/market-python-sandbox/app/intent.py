"""Independent intent check: explicit user constraints versus the proposed Analysis Spec.

The extractor is deterministic and reads only the user's own messages (sent by market-ai-orc from
the run, never written by the model). It recognises a bounded set of English and Indonesian
phrasings: analysis periods, trading-day counts, "latest", explicit dates and months, tickers,
"all stocks", frequency, method keywords, windows/periods/horizons bound to a method, and
thresholds. Anything it does not recognise is never assumed to match: a requirement it cannot
confirm is reported as UNVERIFIED_REQUIREMENT, a contradiction as ANALYSIS_SPEC_MISMATCH, and a
materially ambiguous request as NEEDS_CLARIFICATION.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .spec import APPROVED_DEFAULTS, METHODS, add_months, param_values, resolve_period

# ---------------------------------------------------------------- vocabulary

DIGITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60,
          "ninety": 90, "hundred": 100}
ID_DIGITS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7, "delapan": 8,
             "sembilan": 9}
MONTHS = {
    "january": 1, "jan": 1, "januari": 1, "february": 2, "feb": 2, "februari": 2, "pebruari": 2, "march": 3,
    "mar": 3, "maret": 3, "april": 4, "apr": 4, "may": 5, "mei": 5, "june": 6, "jun": 6, "juni": 6, "july": 7,
    "jul": 7, "juli": 7, "august": 8, "aug": 8, "agustus": 8, "agu": 8, "agt": 8, "ags": 8, "september": 9,
    "sep": 9, "sept": 9, "october": 10, "oct": 10, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
    "nopember": 11, "december": 12, "dec": 12, "desember": 12, "des": 12,
}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
UNIT_RE = (r"(trading days?|trading sessions?|sessions?|hari perdagangan|hari bursa|hari trading|hari kerja|bars?|"
           r"candles?|days?|hari|weeks?|minggu|pekan|months?|bulan|years?|tahun)")
RANGE_SEP = r"(?:-|–|—|to|until|through|thru|sampai(?: dengan)?|hingga|s/d|s\.d\.?|sd|and|dan)"
TICKER_STOP = {
    "IHSG", "MACD", "VWAP", "OHLC", "HIGH", "OPEN", "LAST", "DATE", "DATA", "SELL", "HOLD", "WITH", "FROM", "THAT",
    "THIS", "WHAT", "WHEN", "SHOW", "LIST", "FIND", "BEST", "GOOD", "NEWS", "JSON", "NULL", "TRUE", "NONE", "ALSO",
    "BISA", "CARI", "BELI", "JUAL", "HARI", "LALU", "SAYA", "MANA", "AKAN", "YANG", "DARI", "ATAU", "PADA", "UNTUK",
    "BARU", "RATA", "NAIK", "TURUN", "TINGGI", "SEMUA", "SAHAM", "IDR", "USD", "HAKA", "HAKI", "BUY", "PLUS",
    "EXCEL", "TABLE", "CHART", "ROLL", "MEAN", "STDEV", "ZSCORE", "SMA", "EMA", "RSI", "ATR", "OBV", "ROC", "YTD",
    "MTD", "QTD", "EOD", "API", "SQL", "CSV", "ETF", "IPO", "ARB", "ARA", "LOSS", "GAIN", "RISK", "BULL", "BEAR",
    "TREN", "TREND", "LONG", "SHORT", "BOTH", "EACH", "THAN", "OVER", "UNDER", "ABOVE", "BELOW", "LESS", "MORE",
}
FAMILY_PATTERNS = {
    "RSI": r"\brsi\b|relative strength index",
    "SMA": (r"\bsma\b|\bma ?\d{1,3}\b|moving average|rolling (?:mean|average)|rata-rata (?:bergerak|rolling|\d{1,3} "
            r"hari)|\b\d{1,3}[- ]?(?:day|hari) (?:mean|average)\b"),
    "STD": (r"\bstd\b|\bstdev\b|standard deviations?|standar deviasi|deviasi standar|simpangan baku|\d\s*sd\b|"
            r"\bsd\s+(?:above|below|di atas|di bawah|diatas|dibawah)\b|volatility|volatilitas"),
    "ZSCORE": r"\bz-?scores?\b",
    "RETURN": r"\breturns?\b|imbal hasil|perubahan harga",
    "FORWARD_RETURN": r"forward returns?|returns? (?:\d{1,3} )?(?:hari |day )?(?:ke depan|ahead)|future returns?",
    "CORRELATION": r"\bcorrelations?\b|\bkorelasi\b|\bcorr\b",
    "EVENT_STUDY": r"\bevent[- ]stud(?:y|ies)\b|\bstudi peristiwa\b",
}
FAMILY_SATISFIED_BY = {
    "RSI": {"RSI"}, "SMA": {"SMA", "ROLLING_ZSCORE"}, "STD": {"ROLLING_STD", "ROLLING_ZSCORE"},
    "ZSCORE": {"ROLLING_ZSCORE"}, "RETURN": {"RETURN", "FORWARD_RETURN", "CORRELATION"},
    "FORWARD_RETURN": {"FORWARD_RETURN", "EVENT_STUDY"}, "CORRELATION": {"CORRELATION", "ROLLING_CORRELATION"},
    "EVENT_STUDY": {"EVENT_STUDY"},
}
WINDOW_PARAM = {"SMA": "window", "ROLLING_STD": "window", "ROLLING_ZSCORE": "window", "RSI": "period",
                "ROLLING_CORRELATION": "window", "RETURN": "horizon", "FORWARD_RETURN": "horizon"}
AMBIGUOUS_PERIOD = (r"\b(?:recently|recent|lately|akhir-akhir ini|belakangan ini|baru-baru ini|beberapa (?:hari|minggu|"
                    r"bulan|tahun)|a few (?:days|weeks|months|years)|several (?:days|weeks|months|years)|jangka "
                    r"(?:pendek|panjang)|short[- ]term|long[- ]term)\b")
LATEST = (r"\b(?:latest|terbaru|terkini|most recent|hari ini|today|saat ini|sekarang|currently|current|last "
          r"(?:close|closing|price|bar|candle)|(?:closing|close|harga|penutupan|data|bar|candle|candlestick) "
          r"terakhir)\b")
UNIVERSE_NOUNS = r"(?:stocks?|saham|tickers?|emiten|equities|companies|perusahaan|symbols?|idx|bursa|market|pasar)"
UNIVERSE_ALL = (rf"\b(?:all|entire|whole|semua|seluruh)\b(?:\s+[\w-]+){{0,3}}?\s+{UNIVERSE_NOUNS}\b|\buniverse\b|"
                r"\bseluruh bursa\b")
# "each/every stock" is distributive: with tickers named in the same message it means each of those tickers
# ("nilai terakhir tiap saham"); without named tickers it still means all stocks.
UNIVERSE_EACH = rf"\b(?:every|each|setiap|tiap|masing-masing)\b(?:\s+[\w-]+){{0,3}}?\s+{UNIVERSE_NOUNS}\b"
OPS = {"<": "<", "<=": "<=", ">": ">", ">=": ">=", "below": "<", "under": "<", "less than": "<", "lower than": "<",
       "kurang dari": "<", "di bawah": "<", "dibawah": "<", "lebih rendah dari": "<", "above": ">", "over": ">",
       "greater than": ">", "more than": ">", "higher than": ">", "lebih dari": ">", "lebih besar dari": ">",
       "di atas": ">", "diatas": ">", "lebih tinggi dari": ">", "at least": ">=", "minimal": ">=", "minimum": ">=",
       "paling sedikit": ">=", "at most": "<=", "maksimal": "<=", "maximum": "<=", "paling banyak": "<="}
OP_RE = "|".join(re.escape(k) for k in sorted(OPS, key=len, reverse=True))
NUMBER = r"(-?\d+(?:[.,]\d+)?)"


# ---------------------------------------------------------------- extraction

@dataclass
class Turn:
    index: int
    text: str       # lower-case, numbers normalised
    original: str
    clarified: bool  # a user reply that follows an assistant turn


@dataclass
class Extracted:
    periods: list[dict[str, Any]] = field(default_factory=list)
    latest: list[int] = field(default_factory=list)
    ambiguous_periods: list[dict[str, Any]] = field(default_factory=list)
    tickers: dict[str, int] = field(default_factory=dict)
    universe_all: list[int] = field(default_factory=list)
    frequency: list[dict[str, Any]] = field(default_factory=list)
    families: dict[str, int] = field(default_factory=dict)
    windows: list[dict[str, Any]] = field(default_factory=list)
    thresholds: list[dict[str, Any]] = field(default_factory=list)
    ddof: list[dict[str, Any]] = field(default_factory=list)
    return_kind: list[dict[str, Any]] = field(default_factory=list)
    clarified_turns: list[int] = field(default_factory=list)
    user_text: str = ""

    def record(self) -> dict[str, Any]:
        """The expected-requirements record: matched phrases only, never whole messages."""
        return {
            "periods": self.periods, "latest_requested": bool(self.latest),
            "ambiguous_periods": self.ambiguous_periods, "tickers": sorted(self.tickers),
            "universe_all_requested": bool(self.universe_all), "frequency": self.frequency,
            "method_families": sorted(self.families), "windows": self.windows, "thresholds": self.thresholds,
            "ddof": self.ddof, "return_kind": self.return_kind, "clarified_turns": self.clarified_turns,
        }


def normalise_numbers(text: str) -> str:
    text = text.lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"\b(dua|tiga|empat|lima|enam|tujuh|delapan|sembilan) puluh(?: (satu|dua|tiga|empat|lima|enam|tujuh|"
                  r"delapan|sembilan))?\b",
                  lambda m: str(ID_DIGITS[m.group(1)] * 10 + (ID_DIGITS[m.group(2)] if m.group(2) else 0)), text)
    text = re.sub(r"\b(dua|tiga|empat|lima|enam|tujuh|delapan|sembilan) belas\b",
                  lambda m: str(10 + ID_DIGITS[m.group(1)]), text)
    text = re.sub(r"\bsebelas\b", "11", text)
    text = re.sub(r"\bsepuluh\b", "10", text)
    text = re.sub(r"\bseratus\b", "100", text)
    text = re.sub(r"\bse(hari|minggu|pekan|bulan|tahun)\b", r"1 \1", text)
    text = re.sub(r"\b(satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan)\b",
                  lambda m: str(ID_DIGITS[m.group(1)]), text)
    text = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|sixty|"
                  r"ninety|hundred)\b", lambda m: str(DIGITS[m.group(1)]), text)
    text = re.sub(r"\b(past|last|previous|over the past|over the last|in the past|in the last)\s+(?:a|an)\s+"
                  r"(day|week|month|year)\b", r"\1 1 \2", text)
    return text


def _unit(token: str) -> str:
    token = token.lower()
    if token.startswith(("trading", "hari perdagangan", "hari bursa", "hari trading", "hari kerja", "session", "sesi",
                         "bar", "candle")):
        return "TRADING_DAY"
    if token.startswith(("day", "hari")):
        return "DAY_UNQUALIFIED"
    if token.startswith(("week", "minggu", "pekan")):
        return "WEEK"
    if token.startswith(("month", "bulan")):
        return "MONTH"
    return "YEAR"


def _month_range(first: str, first_year: str | None, last: str, last_year: str | None, ref: date
                 ) -> tuple[date, date, bool]:
    m1, m2 = MONTHS[first], MONTHS[last]
    inferred = not (first_year or last_year)
    y2 = int(last_year or first_year or 0)
    if not y2:
        y2 = ref.year if m2 <= ref.month else ref.year - 1
    y1 = int(first_year) if first_year else (y2 if m1 <= m2 else y2 - 1)
    start = date(y1, m1, 1)
    end = add_months(date(y2, m2, 1), 1) - timedelta(days=1)
    return start, min(end, ref), inferred


def extract(messages: list[dict[str, str]], ref: date) -> Extracted:
    found = Extracted()
    turns: list[Turn] = []
    previous_role = None
    for index, message in enumerate(messages):
        if message["role"] == "user":
            turns.append(Turn(index, normalise_numbers(message["content"]), message["content"],
                              clarified=previous_role == "assistant"))
            if previous_role == "assistant":
                found.clarified_turns.append(index)
        previous_role = message["role"]
    found.user_text = "\n".join(t.text for t in turns)
    for turn in turns:
        _extract_turn(turn, ref, found)
    return found


def _extract_turn(turn: Turn, ref: date, found: Extracted) -> None:
    text, used = turn.text, []

    def taken(span: tuple[int, int]) -> bool:
        return any(span[0] < b and a < span[1] for a, b in used)

    def add_period(kind: dict[str, Any], match: re.Match) -> None:
        if taken(match.span()):
            return
        used.append(match.span())
        found.periods.append({**kind, "turn": turn.index, "clarified": turn.clarified, "text": match.group(0)[:80]})

    # explicit dates: two ISO / d/m/Y dates, "since <date>", month ranges, "Month YYYY", years, YTD
    iso = r"(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})/(\d{1,2})/(\d{4})"

    def as_date(groups: tuple) -> date | None:
        try:
            if groups[0]:
                return date(int(groups[0]), int(groups[1]), int(groups[2]))
            return date(int(groups[5]), int(groups[4]), int(groups[3]))
        except (TypeError, ValueError):
            return None

    for match in re.finditer(rf"({iso})\s*{RANGE_SEP}\s*({iso})", text):
        start, end = as_date(match.groups()[1:7]), as_date(match.groups()[8:14])
        if start and end:
            add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": min(end, ref).isoformat()}, match)
    for match in re.finditer(rf"\b(?:since|sejak|from|dari|mulai)\s+(?:tanggal\s+)?({iso})", text):
        start = as_date(match.groups()[1:7])
        if start:
            add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": ref.isoformat(),
                        "end_implied": True}, match)
    def day(year: str | int, month: str, number: str) -> date | None:
        try:
            return date(int(year), MONTHS[month], int(number))
        except (KeyError, ValueError):
            return None

    def add_day_range(start: date | None, end: date | None, match: re.Match, year_stated_once: bool) -> None:
        if start and end and year_stated_once and start > end:  # "1 Desember sampai 31 Januari 2026"
            start = day(start.year - 1, next(m for m, n in MONTHS.items() if n == start.month), str(start.day))
        if start and end and start <= end:
            add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": min(end, ref).isoformat()}, match)

    suffix = r"(?:st|nd|rd|th)?"
    for match in re.finditer(rf"\b(\d{{1,2}})\s+({MONTH_RE})\b\.?(?:\s+(\d{{4}}))?\s*{RANGE_SEP}\s*(\d{{1,2}})\s+"
                             rf"({MONTH_RE})\b\.?\s+(\d{{4}})\b", text):
        d1, m1, y1, d2, m2, y2 = match.groups()
        add_day_range(day(y1 or y2, m1, d1), day(y2, m2, d2), match, y1 is None)
    for match in re.finditer(rf"\b({MONTH_RE})\.?\s+(\d{{1,2}}){suffix},?(?:\s+(\d{{4}}))?\s*{RANGE_SEP}\s*"
                             rf"({MONTH_RE})\.?\s+(\d{{1,2}}){suffix},?\s+(\d{{4}})\b", text):
        m1, d1, y1, m2, d2, y2 = match.groups()
        add_day_range(day(y1 or y2, m1, d1), day(y2, m2, d2), match, y1 is None)
    for match in re.finditer(rf"\b(\d{{1,2}})\s*{RANGE_SEP}\s*(\d{{1,2}})\s+({MONTH_RE})\b\.?\s+(\d{{4}})\b", text):
        d1, d2, month, year = match.groups()
        add_day_range(day(year, month, d1), day(year, month, d2), match, False)
    for match in re.finditer(rf"\b(?:since|sejak|from|dari|mulai)\s+(?:tanggal\s+)?(\d{{1,2}})\s+({MONTH_RE})\b\.?\s+"
                             rf"(\d{{4}})\b", text):
        start = day(match.group(3), match.group(2), match.group(1))
        if start:
            add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": ref.isoformat(),
                        "end_implied": True}, match)
    for match in re.finditer(rf"\b(\d{{1,2}})\s+({MONTH_RE})\b\.?\s+(\d{{4}})\b", text):
        single = day(match.group(3), match.group(2), match.group(1))
        if single:
            add_period({"mode": "EXPLICIT_DATES", "start": single.isoformat(), "end": single.isoformat()}, match)
    month_range = rf"\b({MONTH_RE})\b\.?\s*(\d{{4}})?\s*{RANGE_SEP}\s*\b({MONTH_RE})\b\.?\s*(\d{{4}})?"
    for match in re.finditer(month_range, text):
        start, end, inferred = _month_range(match.group(1), match.group(2), match.group(3), match.group(4), ref)
        add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": end.isoformat(),
                    "year_inferred": inferred}, match)
    for match in re.finditer(rf"\b(?:since|sejak|from|dari|mulai)\s+({MONTH_RE})\b\.?\s*(\d{{4}})?", text):
        start, _, inferred = _month_range(match.group(1), match.group(2), match.group(1), match.group(2), ref)
        add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": ref.isoformat(),
                    "end_implied": True, "year_inferred": inferred}, match)
    for match in re.finditer(rf"\b({MONTH_RE})\b\.?\s+(\d{{4}})\b", text):
        start, end, _ = _month_range(match.group(1), match.group(2), match.group(1), match.group(2), ref)
        add_period({"mode": "EXPLICIT_DATES", "start": start.isoformat(), "end": end.isoformat()}, match)
    for match in re.finditer(r"\b(?:tahun|year|in|during|selama|sepanjang)\s+((?:19|20)\d{2})\b", text):
        year = int(match.group(1))
        add_period({"mode": "EXPLICIT_DATES", "start": date(year, 1, 1).isoformat(),
                    "end": min(date(year, 12, 31), ref).isoformat()}, match)
    for match in re.finditer(r"\b(?:ytd|year[- ]to[- ]date|sejak awal tahun|dari awal tahun)\b", text):
        add_period({"mode": "EXPLICIT_DATES", "start": date(ref.year, 1, 1).isoformat(), "end": ref.isoformat()},
                   match)

    # relative periods
    relative = [
        rf"\b(?:last|past|previous|prior|trailing|over the last|over the past|in the last|in the past|for the last|"
        rf"for the past|during the last|during the past|within the last|within the past)\s+(\d{{1,4}})\s*[- ]?\s*{UNIT_RE}",
        rf"\b(\d{{1,4}})\s*[- ]?\s*{UNIT_RE}\s+(?:terakhir|ke ?belakang|belakangan|sebelumnya)",
        rf"\b(?:selama|dalam|sepanjang)\s+(\d{{1,4}})\s*{UNIT_RE}",
        rf"\b(?:sejak|dari|since)\s+(\d{{1,4}})\s*{UNIT_RE}\s+(?:lalu|yang lalu|ago)",
    ]
    for pattern in relative:
        for match in re.finditer(pattern, text):
            count, unit = int(match.group(1)), _unit(match.group(2))
            # "dalam 5 hari berikutnya" is an outcome horizon and "turun 7% dalam sehari" a move within one day;
            # neither is the analysis period.
            if re.match(r"\s*(?:berikutnya|ke ?depan|mendatang|setelahnya|selanjutnya|after|ahead|later)\b",
                        text[match.end():]) or (match.group(0).startswith("dalam") and count == 1
                                                 and unit in ("DAY", "DAY_UNQUALIFIED", "TRADING_DAY")):
                continue
            if unit == "TRADING_DAY":
                add_period({"mode": "TRADING_DAYS", "count": count}, match)
            else:
                add_period({"mode": "TRAILING", "unit": unit, "count": count}, match)
    for match in re.finditer(r"\b(?:the past|over the past|over the last|in the past|in the last|during the past|"
                             r"within the past)\s+(day|week|month|year)\b", text):
        add_period({"mode": "TRAILING", "unit": _unit(match.group(1)), "count": 1}, match)
    for match in re.finditer(r"\b(?:last|previous|prior) (week|month|year)\b|\b(minggu|bulan|tahun) lalu\b", text):
        if not taken(match.span()):
            found.ambiguous_periods.append({"text": match.group(0), "turn": turn.index,
                                            "reason": "calendar period or trailing window"})
    for match in re.finditer(AMBIGUOUS_PERIOD, text):
        found.ambiguous_periods.append({"text": match.group(0), "turn": turn.index, "reason": "no stated length"})
    if re.search(LATEST, text):
        found.latest.append(turn.index)

    # universe
    named = [m.group(1) for m in re.finditer(r"\b([A-Z]{4})(?:\.JK)?\b", turn.original) if m.group(1) not in TICKER_STOP]
    if re.search(UNIVERSE_ALL, text) or (not named and re.search(UNIVERSE_EACH, text)):
        found.universe_all.append(turn.index)
    for ticker in named:
        found.tickers.setdefault(ticker, turn.index)

    # frequency, method families, parameters
    for value, pattern in (("1D", r"\b(?:daily|harian|per hari|setiap hari)\b"),
                           ("1W", r"\b(?:weekly|mingguan|per minggu|setiap minggu)\b"),
                           ("1M", r"\b(?:monthly|bulanan|per bulan|setiap bulan)\b")):
        if re.search(pattern, text):
            found.frequency.append({"value": value, "turn": turn.index})
    for family, pattern in FAMILY_PATTERNS.items():
        if re.search(pattern, text):
            found.families.setdefault(family, turn.index)
    if "FORWARD_RETURN" in found.families:
        rest = re.sub(r"forward returns?|future returns?|returns? (?:\d{1,3} )?(?:hari |day )?(?:ke depan|ahead)", "",
                      text)
        if not re.search(FAMILY_PATTERNS["RETURN"], rest):
            found.families.pop("RETURN", None)

    day = r"(?:[- ]?(?:day|hari|period|periode|bar|observation|observasi)s?)"
    windows = [
        ("RSI", rf"\brsi\s*(?:\(|\[)?\s*(?:period[e]?|length|window)?\s*(\d{{1,3}})\b"),
        ("RSI", rf"\b(\d{{1,3}}){day}\s+rsi\b"),
        ("SMA", r"\b(?:sma|ma)\s*\(?\s*(\d{1,3})\b"),
        ("SMA", rf"\b(\d{{1,3}}){day}\s+(?:simple\s+)?(?:moving average|ma|sma|rolling mean|rolling average|"
                r"rata-rata(?: bergerak)?|average|mean)\b"),
        ("SMA", rf"(?:moving average|rata-rata(?: bergerak)?|rolling mean|rolling average)\s+(?:\w+\s+)?(\d{{1,3}}){day}"),
        ("STD", rf"\b(\d{{1,3}}){day}\s+(?:rolling\s+)?(?:std|stdev|standard deviation|standar deviasi|deviasi standar|"
                r"simpangan baku|volatility|volatilitas)\b"),
        ("STD", rf"(?:std|stdev|standard deviation|standar deviasi|deviasi standar|simpangan baku|volatility|volatilitas)"
                rf"\s+(?:rolling\s+)?(\d{{1,3}}){day}"),
        ("ZSCORE", rf"\b(\d{{1,3}}){day}\s+(?:rolling\s+)?z-?scores?\b"),
        ("ZSCORE", rf"\bz-?scores?\s+(?:rolling\s+)?(\d{{1,3}}){day}?"),
        ("CORRELATION", rf"\b(\d{{1,3}}){day}\s+(?:rolling\s+)?(?:correlation|korelasi)\b"),
        ("CORRELATION", rf"(?:correlation|korelasi)\s+(?:rolling\s+)?(\d{{1,3}}){day}"),
        ("FORWARD_RETURN", r"\b(\d{1,3})[- ]?(?:day|hari)\s+(?:forward|ahead|ke depan)\s+returns?\b"),
        ("FORWARD_RETURN", r"\bforward\s+returns?\s+(\d{1,3})\s*[- ]?(?:day|hari)?"),
        ("FORWARD_RETURN", r"\breturns?\s+(\d{1,3})\s*(?:day|hari)\s+(?:ke depan|forward|ahead)"),
        ("RETURN", r"\b(\d{1,3})[- ]?(?:day|hari)\s+returns?\b"),
        ("RETURN", r"\breturns?\s+(\d{1,3})\s*[- ]?(?:day|hari)\b(?!\s+(?:ke depan|forward|ahead|terakhir|perdagangan|"
                   r"bursa|trading))"),
        ("GENERIC", rf"\brolling\s+(?:window\s+)?(?:of\s+)?(\d{{1,3}}){day}?"),
        ("GENERIC", rf"\b(\d{{1,3}}){day}\s+rolling\b"),
        ("GENERIC", r"\bwindow\s+(?:of\s+)?(\d{1,3})\b"),
        ("GENERIC", r"\b(?:jendela|lookback|periode|period|length)\s+(\d{1,3})\b"),
    ]
    for family, pattern in windows:
        for match in re.finditer(pattern, text):
            if taken(match.span(1)):
                continue
            used.append(match.span(1))
            found.windows.append({"family": family, "value": int(match.group(1)), "turn": turn.index,
                                  "text": match.group(0)[:60]})
    for match in re.finditer(r"\b(?:daily returns?|returns? harian|harian returns?)\b", text):
        found.windows.append({"family": "RETURN", "value": 1, "turn": turn.index, "text": match.group(0)})

    # thresholds: "RSI < 30", "RSI di bawah 30", "more than 2 standard deviations above", "z > 2"
    subject = (r"(rsi|z-?scores?|returns?|volatility|volatilitas|correlation|korelasi|std|sd|standard deviation|"
               r"standar deviasi)")
    for match in re.finditer(rf"\b{subject}\b[^.;\n]{{0,25}}?({OP_RE})\s*{NUMBER}", text):
        found.thresholds.append(_threshold(match.group(1), OPS[match.group(2)], match.group(3), turn, match))
    for match in re.finditer(rf"({OP_RE})\s*{NUMBER}\s*(?:x\s*)?(?:sd|std|standard deviations?|standar deviasi|"
                             rf"deviasi standar|simpangan baku|sigma)\b(?:\s+(above|di atas|diatas|below|di bawah|dibawah))?",
                             text):
        value = float(match.group(2).replace(",", "."))
        side = match.group(3) or ""
        op = OPS[match.group(1)]
        if side in ("below", "di bawah", "dibawah"):
            op, value = {">": "<", ">=": "<=", "<": ">", "<=": ">="}[op], -value
        found.thresholds.append({"family": "ZSCORE", "op": op, "value": value, "turn": turn.index,
                                 "text": match.group(0)[:60]})
    for match in re.finditer(rf"{NUMBER}\s*(?:x\s*)?(?:sd|std|standard deviations?|standar deviasi|deviasi standar|"
                             rf"simpangan baku|sigma)\s+(above|di atas|diatas|below|di bawah|dibawah)", text):
        if any(t["text"] and match.group(0) in t["text"] for t in found.thresholds):
            continue
        value = float(match.group(1).replace(",", "."))
        above = match.group(2) in ("above", "di atas", "diatas")
        found.thresholds.append({"family": "ZSCORE", "op": ">" if above else "<", "value": value if above else -value,
                                 "turn": turn.index, "text": match.group(0)[:60], "strictness_inferred": True})

    if re.search(r"population standard deviation|standar deviasi populasi|deviasi standar populasi|ddof\s*=?\s*0",
                 text):
        found.ddof.append({"value": 0, "turn": turn.index})
    if re.search(r"sample standard deviation|standar deviasi sampel|deviasi standar sampel|ddof\s*=?\s*1", text):
        found.ddof.append({"value": 1, "turn": turn.index})
    if re.search(r"\blog[- ]?returns?\b|\blogarithmic\b|\blogaritmik\b|\breturn log\b", text):
        found.return_kind.append({"value": "LOG", "turn": turn.index})
    if re.search(r"\bsimple returns?\b|\breturn sederhana\b|\barithmetic returns?\b", text):
        found.return_kind.append({"value": "SIMPLE", "turn": turn.index})


def _threshold(subject: str, op: str, number: str, turn: Turn, match: re.Match) -> dict[str, Any]:
    subject = subject.lower()
    family = ("RSI" if subject == "rsi" else "ZSCORE" if subject.replace("-", "").rstrip("s") == "zscore"
              else "RETURN" if subject.startswith("return") else "CORRELATION" if subject in ("correlation", "korelasi")
              else "STD")
    return {"family": family, "op": op, "value": float(number.replace(",", ".")), "turn": turn.index,
            "text": match.group(0)[:60]}


# ---------------------------------------------------------------- review

@dataclass
class Review:
    checks: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    unverified: list[dict[str, Any]] = field(default_factory=list)
    clarifications: list[str] = field(default_factory=list)

    def add(self, requirement: str, result: str, expected: Any, proposed: Any, detail: str,
            code: str | None = None) -> None:
        item = {"requirement": requirement, "result": result, "expected": expected, "proposed": proposed,
                "detail": detail[:300]}
        if code:
            item["code"] = code
        self.checks.append(item)
        if result == "MISMATCH":
            self.mismatches.append({**item, "code": code or "ANALYSIS_SPEC_MISMATCH"})
        elif result == "UNVERIFIED":
            self.unverified.append({**item, "code": "UNVERIFIED_REQUIREMENT"})

    @property
    def status(self) -> str:
        if self.mismatches:
            return "ANALYSIS_SPEC_MISMATCH"
        if self.clarifications:
            return "NEEDS_CLARIFICATION"
        return "APPROVED_WITH_UNVERIFIED" if self.unverified else "APPROVED"


def _latest_turn_values(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    last = max(i["turn"] for i in items)
    return [i for i in items if i["turn"] == last]


def _claimed_user(item: dict[str, Any]) -> bool:
    return item.get("provenance") in ("USER_EXPLICIT", "USER_CLARIFIED")


def _default_ok(item: dict[str, Any], expected_default: str) -> bool:
    return item.get("provenance") == "APPROVED_DEFAULT" and item.get("default_id") == expected_default


def review(spec: dict[str, Any], messages: list[dict[str, str]], ref: date) -> tuple[Review, Extracted]:
    found = extract(messages, ref)
    result = Review()
    resolved = resolve_period(spec["analysis_period"], ref)
    _review_universe(spec, found, result)
    _review_period(spec, found, resolved, ref, result)
    _review_frequency(spec, found, result)
    _review_methods(spec, found, result)
    _review_parameters(spec, found, result)
    _review_thresholds(spec, found, result)
    for rule in spec["exclusion_rules"]:
        if not _claimed_user(rule):
            result.add(f"exclusion_rule.{rule['rule']}", "UNVERIFIED", None, rule["value"],
                       "An exclusion rule chosen by the AI, not stated by the user; its exclusions are reported.")
    return result, found


def _review_universe(spec: dict[str, Any], found: Extracted, result: Review) -> None:
    universe = spec["universe"]
    text = found.user_text
    named = set(found.tickers)
    if found.universe_all and not (named and max(found.tickers.values()) > max(found.universe_all)):
        if universe["type"] == "ALL_IN_SOURCE":
            result.add("universe", "MATCH", "ALL", "ALL_IN_SOURCE",
                       "The user asked for all stocks; interpreted as " + APPROVED_DEFAULTS[
                           "DEFAULT_UNIVERSE_ALL_IN_SOURCE"]["meaning"])
        else:
            result.add("universe", "MISMATCH", "ALL", universe["tickers"],
                       "The user asked for all stocks but the spec analyses a list of tickers.", "UNIVERSE_MISMATCH")
        return
    if named:
        if universe["type"] == "ALL_IN_SOURCE":
            result.add("universe", "MISMATCH", sorted(named), "ALL_IN_SOURCE",
                       "The user named specific tickers but the spec analyses every ticker.", "UNIVERSE_MISMATCH")
            return
        proposed = set(universe["tickers"])
        missing = sorted(named - proposed)
        extra = sorted(t for t in proposed - named if not re.search(rf"\b{t.lower()}\b", text))
        if missing:
            result.add("universe", "MISMATCH", sorted(named), sorted(proposed),
                       f"Tickers named by the user are missing from the spec: {missing}", "UNIVERSE_MISMATCH")
        elif extra:
            result.add("universe", "UNVERIFIED", sorted(named), sorted(proposed),
                       f"The spec adds tickers the user did not name: {extra}")
        else:
            result.add("universe", "MATCH", sorted(named), sorted(proposed), "Tickers match the user's request.")
        return
    if universe["type"] == "TICKERS":
        listed = [t for t in universe["tickers"] if re.search(rf"\b{t.lower()}\b", text)]
        if len(listed) == len(universe["tickers"]):
            result.add("universe", "MATCH", universe["tickers"], universe["tickers"], "Tickers appear in the request.")
            return
    result.add("universe", "UNVERIFIED", None, universe["tickers"] or universe["type"],
               "The request does not state which stocks to analyse; the universe was chosen by the AI.")


def _period_equal(expected: dict[str, Any], resolved: dict[str, Any], spec_period: dict[str, Any],
                  ref: date) -> bool | None:
    """True/False when comparable; None when the day unit is ambiguous but the count agrees."""
    mode = expected["mode"]
    if mode == "TRADING_DAYS":
        return spec_period["mode"] == "TRADING_DAYS" and spec_period["count"] == expected["count"]
    if mode == "TRAILING" and expected["unit"] == "DAY_UNQUALIFIED":
        if spec_period["mode"] == "TRADING_DAYS" and spec_period["count"] == expected["count"]:
            return None
        if spec_period["mode"] == "TRAILING" and spec_period["unit"] == "DAY" and spec_period["count"] == expected["count"]:
            return None
        return False
    if mode == "TRAILING":
        if spec_period["mode"] == "TRAILING":
            return spec_period["unit"] == expected["unit"] and spec_period["count"] == expected["count"]
        target = resolve_period({"mode": "TRAILING", "unit": expected["unit"], "count": expected["count"]}, ref)
        return resolved.get("start") == target["start"] and resolved.get("end") == target["end"]
    return resolved.get("start") == expected["start"] and resolved.get("end") == expected["end"]


def _review_period(spec: dict[str, Any], found: Extracted, resolved: dict[str, Any], ref: date,
                   result: Review) -> None:
    period = spec["analysis_period"]
    proposed = {k: v for k, v in resolved.items() if k in ("mode", "start", "end", "trading_days")}
    candidates = _latest_turn_values(found.periods)
    if candidates:
        distinct = {tuple(sorted((k, v) for k, v in c.items() if k in ("mode", "unit", "count", "start", "end")))
                    for c in candidates}
        if len(distinct) > 1:
            if any(_period_equal(c, resolved, period, ref) is not False for c in candidates):
                result.add("analysis_period", "UNVERIFIED", [c["text"] for c in candidates], proposed,
                           "The request mentions several periods; the spec uses one of them.")
            else:
                result.add("analysis_period", "MISMATCH", [c["text"] for c in candidates], proposed,
                           "None of the periods in the request matches the spec.", "ANALYSIS_SCOPE_MISMATCH")
            return
        expected = candidates[0]
        same = _period_equal(expected, resolved, period, ref)
        shown = {k: v for k, v in expected.items() if k in ("mode", "unit", "count", "start", "end")}
        if same is False:
            result.add("analysis_period", "MISMATCH", shown, proposed,
                       f"The user asked for '{expected['text']}' but the spec uses a different period.",
                       "ANALYSIS_SCOPE_MISMATCH")
        elif same is None:
            result.add("analysis_period", "UNVERIFIED", shown, proposed,
                       f"'{expected['text']}' does not say trading or calendar days; the spec chose "
                       f"{'trading' if period['mode'] == 'TRADING_DAYS' else 'calendar'} days.")
        else:
            note = " (month year inferred as its most recent occurrence)" if expected.get("year_inferred") else ""
            result.add("analysis_period", "MATCH", shown, proposed, f"Matches '{expected['text']}'{note}.")
            if expected.get("year_inferred") and not _default_ok(period, "DEFAULT_MONTH_WITHOUT_YEAR"):
                result.add("analysis_period.year", "UNVERIFIED", shown, proposed,
                           "The request names months without a year.")
        return
    ambiguous = [a for a in found.ambiguous_periods if not found.periods]
    if ambiguous:
        result.clarifications.append(
            f"The request says '{ambiguous[-1]['text']}' ({ambiguous[-1]['reason']}). Ask the user for the exact "
            f"analysis period.")
        result.add("analysis_period", "UNVERIFIED", [a["text"] for a in ambiguous], proposed,
                   "The requested period is ambiguous.")
        return
    period_end_only = all(o["grain"] in ("ENTITY", "UNSPECIFIED") for o in spec["outputs"])
    if found.latest:
        if period["mode"] == "LATEST" or (period["mode"] == "TRADING_DAYS" and period["count"] == 1):
            result.add("analysis_period", "MATCH", "LATEST", proposed,
                       "The user asked for the latest data; " + APPROVED_DEFAULTS["DEFAULT_LATEST"]["meaning"])
        else:
            result.add("analysis_period", "MISMATCH", "LATEST", proposed,
                       "The user asked for the latest data but the spec analyses a longer period.",
                       "ANALYSIS_SCOPE_MISMATCH")
        return
    if period["mode"] == "LATEST" and period_end_only:
        result.add("analysis_period", "UNVERIFIED", None, proposed,
                   "The request states no period; the spec evaluates each entity's latest observation.")
        return
    result.clarifications.append("The request does not state the analysis period for a time-series result. Ask the "
                                 "user which period to analyse.")
    result.add("analysis_period", "UNVERIFIED", None, proposed, "No analysis period is stated in the request.")


def _review_frequency(spec: dict[str, Any], found: Extracted, result: Review) -> None:
    frequency = spec["frequency"]
    stated = {f["value"] for f in _latest_turn_values(found.frequency)}
    if len(stated) == 1:
        (value,) = stated
        # "daily returns over N weeks" is still daily data; weekly/monthly words may describe periods.
        if value == frequency["value"]:
            result.add("frequency", "MATCH", value, frequency["value"], "Matches the stated frequency.")
        elif value == "1D":
            result.add("frequency", "MISMATCH", value, frequency["value"],
                       "The user asked for daily data.", "ANALYSIS_SCOPE_MISMATCH")
        else:
            result.add("frequency", "UNVERIFIED", value, frequency["value"],
                       "The request mentions a non-daily frequency; the spec uses daily observations.")
        return
    if frequency["value"] == "1D" and _default_ok(frequency, "DEFAULT_FREQUENCY_DAILY"):
        result.add("frequency", "DEFAULT_APPLIED", None, "1D", APPROVED_DEFAULTS["DEFAULT_FREQUENCY_DAILY"]["meaning"])
    elif frequency["value"] == "1D":
        result.add("frequency", "DEFAULT_APPLIED", None, "1D", "Daily observations (the only stored frequency).")
    else:
        result.add("frequency", "UNVERIFIED", None, frequency["value"], "Frequency chosen by the AI.")


def _review_methods(spec: dict[str, Any], found: Extracted, result: Review) -> None:
    calcs = spec["calculations"]
    for family in sorted(found.families):
        satisfied = [c["id"] for c in calcs
                     if c["method"] in FAMILY_SATISFIED_BY[family] or family in (c.get("covers") or [])]
        if satisfied:
            result.add(f"method.{family}", "MATCH", family, satisfied, "A calculation covers this requested method.")
        else:
            result.add(f"method.{family}", "MISMATCH", family, [c["method"] for c in calcs],
                       f"The request mentions {family} but no calculation in the spec computes it.",
                       "MISSING_REQUESTED_CALCULATION")
    for calc in calcs:
        families = set(calc.get("covers") or [])
        if not families & set(found.families):
            result.add(f"calculation.{calc['id']}", "UNVERIFIED", None, calc["method"],
                       "This calculation is not mentioned in the request (chosen by the AI).")
        elif calc["method"] == "CUSTOM":
            result.add(f"calculation.{calc['id']}", "UNVERIFIED", sorted(families & set(found.families)), "CUSTOM",
                       "A CUSTOM method cannot be checked against the request or recalculated independently.")


def _review_parameters(spec: dict[str, Any], found: Extracted, result: Review) -> None:
    latest_windows = _latest_turn_values(found.windows)
    for calc in spec["calculations"]:
        if calc["method"] == "CUSTOM":
            continue
        params = param_values(calc)
        families = set(calc.get("covers") or [])
        name = WINDOW_PARAM.get(calc["method"])
        if name:
            value = params[name]
            entry = next(p for p in calc["params"] if p["name"] == name)
            bound = sorted({w["value"] for w in latest_windows if w["family"] in families})
            if calc["method"] == "RETURN":
                bound = sorted({w["value"] for w in latest_windows if w["family"] == "RETURN"})
            generic = sorted({w["value"] for w in latest_windows if w["family"] == "GENERIC"})
            requirement = f"calculation.{calc['id']}.{name}"
            if bound:
                if value in bound:
                    result.add(requirement, "MATCH", bound, value, "Matches the value stated in the request.")
                else:
                    result.add(requirement, "MISMATCH", bound, value,
                               f"The request states {name} {bound} for this method.", "CALCULATION_PARAMETER_MISMATCH")
            elif generic and calc["method"] not in ("RETURN", "FORWARD_RETURN"):
                if value in generic:
                    result.add(requirement, "MATCH", generic, value, "Matches the rolling window in the request.")
                elif len(generic) == 1:
                    result.add(requirement, "MISMATCH", generic, value, "The request states a different rolling window.",
                               "CALCULATION_PARAMETER_MISMATCH")
                else:
                    result.add(requirement, "UNVERIFIED", generic, value, "Several windows are mentioned.")
            elif entry["provenance"] == "APPROVED_DEFAULT":
                result.add(requirement, "DEFAULT_APPLIED", None, value, APPROVED_DEFAULTS[entry["default_id"]]["meaning"])
            else:
                result.add(requirement, "UNVERIFIED", None, value, f"{name} is not stated in the request.")
        if "ddof" in params:
            stated = {d["value"] for d in _latest_turn_values(found.ddof)}
            if stated and params["ddof"] not in stated:
                result.add(f"calculation.{calc['id']}.ddof", "MISMATCH", sorted(stated), params["ddof"],
                           "The request states a different standard deviation type.", "CALCULATION_PARAMETER_MISMATCH")
        if "kind" in params:
            stated = {d["value"] for d in _latest_turn_values(found.return_kind)}
            if stated and params["kind"] not in stated:
                result.add(f"calculation.{calc['id']}.kind", "MISMATCH", sorted(stated), params["kind"],
                           "The request states a different return type.", "CALCULATION_PARAMETER_MISMATCH")


def _review_thresholds(spec: dict[str, Any], found: Extracted, result: Review) -> None:
    calcs = {c["id"]: c for c in spec["calculations"]}
    predicates = [(o["name"], p) for o in spec["outputs"] for p in (o.get("selection") or [])]
    predicates += [(f"calculation.{c['id']}", p) for c in spec["calculations"] for p in (c.get("signal") or [])]
    stated = _latest_turn_values(found.thresholds)
    for threshold in stated:
        family = threshold["family"]
        relevant = [(name, p) for name, p in predicates
                    if family in (calcs[p["calculation"]].get("covers") or [])]
        requirement = f"threshold.{family}"
        if not relevant:
            result.add(requirement, "UNVERIFIED", f"{family} {threshold['op']} {threshold['value']:g}", None,
                       "The stated threshold is not a selection predicate of any output, so the screen cannot be "
                       "checked independently.")
            continue
        exact = [p for _, p in relevant if p["op"] == threshold["op"] and p["value"] == threshold["value"]]
        loose = [p for _, p in relevant if p["value"] == threshold["value"]]
        if exact and not threshold.get("strictness_inferred"):
            result.add(requirement, "MATCH", f"{threshold['op']} {threshold['value']:g}",
                       [f"{p['op']} {p['value']:g}" for p in exact], "Matches the stated threshold.")
        elif exact or loose:
            result.add(requirement, "UNVERIFIED", f"{threshold['op']} {threshold['value']:g}",
                       [f"{p['op']} {p['value']:g}" for p in loose],
                       "The threshold value matches; whether the bound is inclusive is not stated.")
        else:
            result.add(requirement, "MISMATCH", f"{threshold['op']} {threshold['value']:g}",
                       [f"{p['op']} {p['value']:g}" for _, p in relevant],
                       "The selection threshold differs from the request.", "CALCULATION_PARAMETER_MISMATCH")
    stated_families = {t["family"] for t in stated}
    for name, predicate in predicates:
        family = set(calcs[predicate["calculation"]].get("covers") or [])
        if not family & stated_families:
            where = f"{name}.signal" if name.startswith("calculation.") else f"output.{name}.selection"
            result.add(where, "UNVERIFIED", None, f"{predicate['op']} {predicate['value']:g}",
                       "A selection threshold chosen by the AI, not stated in the request.")


def messages_sha256(messages: list[dict[str, str]]) -> str:
    material = "\x1e".join(f"{m['role']}\x1f{m['content']}" for m in messages)
    return hashlib.sha256(material.encode()).hexdigest()
