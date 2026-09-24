"""Number provenance: every number in a final answer must trace to a governed source of this run.

Sources are collected only from tool results the application received (never from the model):
- lookup_fact values (FACT for mode VALUE, DATABASE_AGGREGATE for mode AGGREGATE);
- outputs of Python analyses whose execution COMPLETED and whose validation is PASS or UNVERIFIED
  (labelled by their validation level; FAILED and INCOMPLETE outputs are never sources);
- context: numbers in the user's own messages, approved analysis specs, dataset manifests, and the
  counts in validation evidence and scopes.
preview_table_rows results are never sources: previews explain column formats, not answers.

A displayed number matches a source when they agree after rounding to the displayed number of
decimals, allowing decimal <-> percent conversion and a sign stated in words ("turun 2,4%").
Dates, years, list markers, and digits inside identifiers (tickers such as T001, ids) are not
checked.
"""
from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from typing import Any

# Evidence labels, strongest first. A mixed answer carries the weakest label it relies on.
LABEL_ORDER = ["FACT", "DATABASE_AGGREGATE", "CALCULATION_VERIFIED", "SCOPE_VERIFIED", "UNVERIFIED_EXPLORATORY",
               "NOT_VALIDATED"]
CONTEXT = "CONTEXT"
MULTIPLIERS = {"ribu": 1e3, "rb": 1e3, "k": 1e3, "thousand": 1e3, "juta": 1e6, "jt": 1e6, "million": 1e6, "m": 1e6,
               "mn": 1e6, "miliar": 1e9, "milyar": 1e9, "billion": 1e9, "b": 1e9, "bn": 1e9, "triliun": 1e12,
               "trillion": 1e12, "t": 1e12}
MONTHS = (r"jan(?:uari|uary)?|feb(?:ruari|ruary)?|pebruari|mar(?:et|ch)?|apr(?:il)?|mei|may|jun[ei]?|jul[iy]?|"
          r"agu(?:stus)?|agt|ags|aug(?:ust)?|sep(?:t|tember)?|okt(?:ober)?|oct(?:ober)?|nov(?:ember)?|nopember|"
          r"des(?:ember)?|dec(?:ember)?")
DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b",
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",
    rf"\b\d{{1,2}}\s+(?:{MONTHS})\.?(?:\s+\d{{4}})?\b",
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b",
    rf"\b(?:{MONTHS})\.?\s+\d{{4}}\b",
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}\b",
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b",
    r"\b(?:19|20)\d{2}\b",                       # years
    r"\b[qQ][1-4]\b|\b[hH][12]\b",               # quarters and halves
]
DATE_RE = re.compile("|".join(DATE_PATTERNS), re.IGNORECASE)
LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:\(?\d{1,2}[.)]|\d{1,2}\.)\s+|(?:(?<=\s)|^)\(\d{1,2}\)\s")
NUMBER_RE = re.compile(
    r"(?<![\w.,/])([+\-−–]?)(\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w]|[.,]\d)"
    r"(\s?%)?(?:\s?(ribu|rb|k|thousand|juta|jt|million|mn|m|miliar|milyar|billion|bn|b|triliun|trillion|t)\b)?",
    re.IGNORECASE)
JSON_NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")
NEGATIVE_WORDS = re.compile(r"(turun|melemah|minus|negatif|down|fell|declin|drop|lost|rugi|koreksi)", re.IGNORECASE)


@dataclass
class DisplayedNumber:
    text: str
    candidates: list[tuple[float, int]]  # (value, displayed decimals)
    percent: bool


def _interpretations(body: str) -> list[tuple[float, int]]:
    """Readings of one numeric token under Indonesian and English separators: (value, decimals)."""
    compact = body.replace(" ", "")
    out: set[tuple[float, int]] = set()
    if "." in compact and "," in compact:
        decimal = "." if compact.rfind(".") > compact.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        whole, _, frac = compact.replace(thousands, "").partition(decimal)
        out.add((float(f"{whole}.{frac}"), len(frac)))
    elif "." in compact or "," in compact:
        sep = "." if "." in compact else ","
        parts = compact.split(sep)
        if len(parts) == 2:
            out.add((float(f"{parts[0]}.{parts[1]}"), len(parts[1])))  # decimal separator
        if all(len(p) == 3 for p in parts[1:]) and parts[0] not in ("", "0"):
            out.add((float("".join(parts)), 0))  # thousands separators
    else:
        out.add((float(compact), 0))
    return sorted(out)


def parse_numbers(text: str) -> list[DisplayedNumber]:
    """Numbers a reader would take as data values in free text (tables included)."""
    masked = DATE_RE.sub(lambda m: " " * len(m.group(0)), text or "")
    masked = LIST_MARKER_RE.sub(lambda m: " " * len(m.group(0)), masked)
    found: list[DisplayedNumber] = []
    for match in NUMBER_RE.finditer(masked):
        sign, body, percent, unit = match.group(1), match.group(2), match.group(3), match.group(4)
        try:
            readings = _interpretations(body)
        except ValueError:
            continue
        factor = MULTIPLIERS.get((unit or "").lower(), 1.0)
        # "0,31%-2,15%" or "10–20": a dash right after a number is a range separator, not a sign
        range_dash = bool(sign) and match.start() > 0 and masked[match.start() - 1] in "0123456789%"
        negative = sign in ("-", "−", "–") and not range_dash
        candidates = []
        for value, decimals in readings:
            value = -value if negative else value
            if factor != 1.0:
                # "1,25 juta" shows 2 decimals of millions: the rounding step is 0.01 * 1e6.
                candidates.append((value * factor, decimals - int(round(math.log10(factor)))))
            else:
                candidates.append((value, decimals))
        found.append(DisplayedNumber(text=match.group(0).strip(), candidates=candidates, percent=bool(percent)))
    return found


def numbers_in(value: Any, ints_only: bool = False, depth: int = 0) -> list[float]:
    """Numeric leaves of a JSON value (numeric strings count; free text does not)."""
    out: list[float] = []
    if depth > 12:
        return out
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)) and (not ints_only or float(value).is_integer()):
            out.append(float(value))
    elif isinstance(value, str):
        text = value.strip()
        if len(text) <= 40 and JSON_NUMBER_RE.match(text):
            number = float(text)
            if math.isfinite(number) and (not ints_only or number.is_integer()):
                out.append(number)
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(numbers_in(item, ints_only, depth + 1))
    elif isinstance(value, (list, tuple)):
        for item in value:
            out.extend(numbers_in(item, ints_only, depth + 1))
    return out


@dataclass
class SourceIndex:
    """Sorted source values per evidence kind (FACT, DATABASE_AGGREGATE, an analysis label, or CONTEXT)."""

    values: dict[str, list[float]] = field(default_factory=dict)

    def add(self, kind: str, numbers: list[float]) -> None:
        bucket = self.values.setdefault(kind, [])
        for number in numbers:
            for variant in (number, number * 100.0, number / 100.0):  # decimal <-> percent
                bisect.insort(bucket, variant)

    def kinds_matching(self, shown: DisplayedNumber, negative_in_words: bool) -> set[str]:
        kinds: set[str] = set()
        for value, decimals in shown.candidates:
            tolerance = 0.5 * 10.0 ** (-decimals) * (1 + 1e-9) + 1e-12
            targets = {value}
            if negative_in_words and value > 0:
                targets.add(-value)
            for kind, bucket in self.values.items():
                if kind in kinds:
                    continue
                for target in targets:
                    index = bisect.bisect_left(bucket, target - tolerance)
                    if index < len(bucket) and bucket[index] <= target + tolerance:
                        kinds.add(kind)
                        break
        return kinds


@dataclass
class ProvenanceResult:
    checked: int
    unsupported: list[str]
    data_kinds: list[str]  # the strongest source kind of each number that matched a data source


def check_answer(text: str, index: SourceIndex) -> ProvenanceResult:
    numbers = parse_numbers(text)
    unsupported: list[str] = []
    kinds: list[str] = []
    for shown in numbers:
        start = text.find(shown.text)
        window = text[max(0, start - 40):start] if start >= 0 else ""
        matched = index.kinds_matching(shown, bool(NEGATIVE_WORDS.search(window)))
        if not matched:
            unsupported.append(shown.text)
            continue
        data = [k for k in matched if k != CONTEXT]
        if data:
            kinds.append(min(data, key=LABEL_ORDER.index))
    return ProvenanceResult(checked=len(numbers), unsupported=list(dict.fromkeys(unsupported)), data_kinds=kinds)


def weakest(labels: list[str]) -> str | None:
    return max(labels, key=LABEL_ORDER.index) if labels else None


def analysis_label(execution_status: str | None, validation_status: str | None, level: str | None) -> str | None:
    """The evidence label of an analysis result, or None when its outputs are not a source at all."""
    if execution_status != "COMPLETED":
        return None
    if validation_status == "PASS":
        return {"CALCULATION_VERIFIED": "CALCULATION_VERIFIED", "SCOPE_VERIFIED": "SCOPE_VERIFIED"}.get(
            level or "", "UNVERIFIED_EXPLORATORY")
    if validation_status == "UNVERIFIED":
        return "UNVERIFIED_EXPLORATORY"
    return None  # FAILED, INCOMPLETE, PENDING


# ---------------------------------------------------------------- routing guard
# The method-family patterns are the sandbox's deterministic intent rules
# (apps/market-python-sandbox/app/intent.py FAMILY_PATTERNS; a contract test keeps them identical).
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
# Orc-only additions: rankings and derived comparisons need the analysis path; a plain average over
# an explicit scope may also come from a database aggregate (lookup_fact AVG).
RANKING_PATTERN = (r"\b(?:top|bottom|rank(?:ing|ed)?|peringkat|tertinggi|terendah|terbesar|terkecil|teratas|"
                   r"terbawah|paling (?:tinggi|rendah|besar|kecil|banyak|sedikit)|highest|lowest|largest|smallest|"
                   r"terbaik|terburuk|best|worst|urutkan|sort(?:ed)?)\b")
CHANGE_PATTERN = r"\b(?:persentase perubahan|percent(?:age)? change|pct change|% change|perubahan persen)\b"
AVERAGE_PATTERN = r"\b(?:rata-rata|rerata|average|mean|avg)\b"


def requested_statistics(text: str) -> tuple[set[str], bool]:
    """(statistic families that need an analysis, whether a plain average is requested)."""
    lowered = (text or "").lower()
    families = {name for name, pattern in FAMILY_PATTERNS.items() if re.search(pattern, lowered)}
    if re.search(RANKING_PATTERN, lowered):
        families.add("RANKING")
    if re.search(CHANGE_PATTERN, lowered):
        families.add("RETURN")
    plain_average = bool(re.search(AVERAGE_PATTERN, lowered)) and "SMA" not in families
    return families, plain_average
