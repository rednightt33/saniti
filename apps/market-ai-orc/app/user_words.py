"""The user's own words in a run, and the outcome horizons they state (M69 tahap 1, round 2026-10-03; B3).

Mode 4 runs its steps as sub-runs whose message is the user's question plus application context (the analysis the
user received, the research results). That context is the model's own text: a number in it is not the user's. The
gates that bind a plan to the user's words (the success threshold, H2; the outcome horizon) read current_user_words
when a pipeline set it, else the run's message.

Golden test g6_revise (2026-10-02): the user asked for a rise "within 10 days"; the follow-up suggestion changed the
horizon to 5 days on the model's own initiative. A horizon the user stated is a design value of theirs, like the
success threshold: every experiment and angle uses it until the user states another.
"""
from __future__ import annotations

import re
from contextvars import ContextVar

current_user_words: ContextVar[str | None] = ContextVar("current_user_words", default=None)
# between the user's messages in current_user_words (oldest first), so the newest statement can be found
MESSAGE_SEPARATOR = "\n\u241e\n"
# M82 (user decision 2026-10-05): the conversation router's structured reading of the newest message
# ([{name, value, unit, action}]; None when no router read it, then the pattern reading below decides alone)
current_design_changes: ContextVar[list[dict] | None] = ContextVar("current_design_changes", default=None)
# 10.6 (plan 2026-10-05, user decision): the conversation router's referent of the newest message (NEWEST_RESULT when it
# builds on the latest result, "pakai angka hasil analisa kamu barusan"); None when no router read it
current_turn_referent: ContextVar[str | None] = ContextVar("current_turn_referent", default=None)

NUMBER = r"(\d{1,3})"
UNITS = {"DAY": r"(?:hari(?:\s+(?:bursa|perdagangan|kerja))?|trading\s+days?|business\s+days?|days?|d)",
         "WEEK": r"(?:minggu|pekan|weeks?|w)", "MONTH": r"(?:bulan|months?)"}
# a span counts as an outcome horizon only with a forward cue before or after it (a lookback such as "MA 20 hari"
# or "RSI 14 hari" has none)
# 2026-10-05 (stress test s3): a change of horizon ("ubah horizonnya jadi 10 hari", "horizon to 10 days") is a stated
# horizon too
BEFORE = (r"(?:dalam|within|in\s+the\s+next|next|selama|holding|hold|setelah|after|over\s+the\s+next"
          r"|(?:horizon|horison|periode\s+hasil|jangka(?:\s+waktu)?)\w*(?:\s+(?:uji|hasil))?"
          r"(?:\s+(?:jadi|menjadi|ke|to|of|=|:|diubah\s+(?:jadi|ke)))?)")
AFTER = (r"(?:ke\s*depan|berikutnya|selanjutnya|setelahnya|setelah|kemudian|mendatang|later|ahead|after|forward"
         r"|holding|horizon)")
PATTERNS = [(unit, re.compile(rf"\b{BEFORE}\s+{NUMBER}\s*-?\s*{word}\b", re.IGNORECASE)) for unit, word in UNITS.items()]
PATTERNS += [(unit, re.compile(rf"\b{NUMBER}\s*-?\s*{word}\s+{AFTER}\b", re.IGNORECASE)) for unit, word in UNITS.items()]
# periods of one analysis period per stated unit (a week is five trading days on daily data)
PERIODS = {"DAILY": {"DAY": 1, "WEEK": 5}, "WEEKLY": {"WEEK": 1}, "MONTHLY": {"MONTH": 1}}


def stated_horizons(*texts: str | None) -> set[tuple[int, str]]:
    """{(number, unit)} of the forward time spans written in the texts."""
    found: set[tuple[int, str]] = set()
    for text in texts:
        for unit, pattern in PATTERNS:
            found.update((int(m.group(1)), unit) for m in pattern.finditer(text or "") if int(m.group(1)) > 0)
    return found


def latest_horizons(*texts: str | None) -> set[tuple[int, str]]:
    """The horizons of the newest statement (texts oldest first; a text may hold several messages joined with
    MESSAGE_SEPARATOR): a horizon the user changes replaces the earlier one (stress test s3, 2026-10-05: "ubah horizonnya
    jadi 10 hari" was locked back to the first question's 5 days)."""
    for text in reversed(texts):
        for message in reversed((text or "").split(MESSAGE_SEPARATOR)):
            found = stated_horizons(message)
            if found:
                return found
    return set()


def locked_horizons(texts: list[str | None], changes: list[dict] | None) -> tuple[set[tuple[int, str]], str | None]:
    """The outcome horizons a plan must use (texts oldest first; the last message of the last text is the newest) and
    a disagreement note. M82: the conversation router's structured change of the newest message decides (REPLACE: its
    values; ADD: the earlier horizons and its values; variants, 2026-10-06: REMOVE takes a horizon out); the pattern
    reading cross-checks it. When the two disagree, both readings are allowed (a wrong lock would force the wrong
    horizon) and the note names the disagreement. Without a router reading (changes None: an explicit API action, a
    failed router call, AI_ENABLE_ASK_BACK off for a first message) the newest statement found by the patterns wins."""
    messages = [m for text in texts for m in (text or "").split(MESSAGE_SEPARATOR)]
    newest = stated_horizons(messages[-1]) if messages else set()
    earlier = latest_horizons(*messages[:-1])
    if changes is None:
        return (newest or earlier), None
    added, replaced, removed = (horizon_changes(changes, action) for action in ("ADD", "REPLACE", "REMOVE"))
    values = added | replaced
    if values or removed:
        locked = ((set() if replaced else set(earlier)) | values) - removed
    else:
        locked = set(earlier)
    if newest and newest != values and not newest <= values | removed:
        return locked | (newest - removed), (f"router read {sorted(values) or 'no horizon'}, the message's words "
                                             f"{sorted(newest)}")
    return locked, None


def horizon_changes(changes: list[dict] | None, action: str) -> set[tuple[int, str]]:
    """{(number, unit)} of the router's OUTCOME_HORIZON changes with this action (a non-positive value or a unit that
    is not a time unit is ignored)."""
    found = set()
    for change in changes or []:
        if change.get("name") != "OUTCOME_HORIZON" or change.get("action") != action \
                or change.get("unit") not in UNITS:
            continue
        try:
            value = int(round(float(change.get("value") or 0)))
        except (TypeError, ValueError):
            continue
        if value > 0:
            found.add((value, str(change["unit"])))
    return found


def design_values(changes: list[dict] | None, name: str, *actions: str) -> list[float]:
    """The numeric values of the router's changes of one design value name (CONDITION_THRESHOLD, SUCCESS_THRESHOLD,
    MIN_EFFECT) with these actions."""
    found = []
    for change in changes or []:
        if change.get("name") != name or change.get("action") not in actions:
            continue
        try:
            found.append(float(change.get("value")))
        except (TypeError, ValueError):
            continue
    return found


def variants(changes: list[dict] | None) -> dict[str, list[str]]:
    """Variants (2026-10-06): the design values the newest message names more than once (ADD or REPLACE), as text per
    name ({"OUTCOME_HORIZON": ["3 DAY", "10 DAY"], ...}); empty when every value is named once."""
    named: dict[str, list[str]] = {}
    for change in changes or []:
        if change.get("action") not in ("ADD", "REPLACE"):
            continue
        value = change.get("value")
        text = f"{value:g} {change.get('unit')}".replace(" NONE", "") if isinstance(value, (int, float)) \
            else str(change.get("text") or "").strip()
        if text and text not in named.setdefault(str(change.get("name")), []):
            named[str(change.get("name"))].append(text)
    return {name: texts for name, texts in named.items() if len(texts) > 1}


def frequency_of(analysis_frequency: str | None) -> str:
    """DAILY, WEEKLY or MONTHLY from a plan's free-text analysis_frequency (daily when unstated)."""
    text = (analysis_frequency or "").casefold()
    if any(w in text for w in ("week", "minggu", "pekan", "1w")):
        return "WEEKLY"
    if any(w in text for w in ("month", "bulan", "1m")):
        return "MONTHLY"
    return "DAILY"


def allowed_periods(stated: set[tuple[int, str]], analysis_frequency: str | None) -> set[int]:
    """The outcome_horizon_periods values the stated horizons allow at this frequency (empty: nothing locked)."""
    per = PERIODS[frequency_of(analysis_frequency)]
    return {n * per[unit] for n, unit in stated if unit in per}


# EXEC-W A2 (M117, user decision 2026-10-08 "Oke untuk M117"): a design value is the user's when the router quotes the
# user's own words for it (text) and those words are in the user's message; basis says whether the value is written
# there (STATED) or follows from the words without a number (IMPLIED: "naik" is a success threshold above 0). The quote
# is checked by matching the normalised text, never by a list of words, so new phrasings need no code.
_QUOTE_EDGES = " \t\r\n\"'“”‘’`.,;:!?()[]"


def _normalised(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip(_QUOTE_EDGES)


def quoted_in(text: str | None, sources: list[str | None]) -> bool:
    """The quote occurs in one of the user's texts (case, spacing and edge punctuation aside)."""
    quote = _normalised(text)
    return bool(quote) and any(quote in _normalised(source) for source in sources)


def user_values(changes: list[dict] | None, name: str, sources: list[str | None]) -> list[tuple[float, str, str]]:
    """(value, basis, quote) of the router's ADD or REPLACE changes of one design value whose quote is the user's
    words; a change without a valid quote is not the user's (its value then needs the user's confirmation)."""
    found = []
    for change in changes or []:
        if change.get("name") != name or change.get("action") not in ("ADD", "REPLACE"):
            continue
        try:
            value = float(change.get("value"))
        except (TypeError, ValueError):
            continue
        if quoted_in(change.get("text"), sources):
            found.append((value, str(change.get("basis") or "STATED"), str(change.get("text"))))
    return found
