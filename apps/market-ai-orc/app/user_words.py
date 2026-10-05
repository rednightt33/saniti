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
    values; ADD: the earlier horizons and its values); the pattern reading cross-checks it. When the two disagree, both
    readings are allowed (a wrong lock would force the wrong horizon) and the note names the disagreement. Without a
    router reading (changes None: a first message, an explicit API action, a failed router call) the newest statement
    found by the patterns wins."""
    messages = [m for text in texts for m in (text or "").split(MESSAGE_SEPARATOR)]
    newest = stated_horizons(messages[-1]) if messages else set()
    earlier = latest_horizons(*messages[:-1])
    if changes is None:
        return (newest or earlier), None
    routed = [c for c in changes if c.get("name") == "OUTCOME_HORIZON" and int(c.get("value") or 0) > 0]
    values = {(int(c["value"]), str(c["unit"])) for c in routed}
    if routed:
        locked = values if all(c.get("action") == "REPLACE" for c in routed) else earlier | values
    else:
        locked = set(earlier)
    if newest and newest != values:
        return locked | newest, (f"router read {sorted(values) or 'no horizon'}, the message's words "
                                 f"{sorted(newest)}")
    return locked, None


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
