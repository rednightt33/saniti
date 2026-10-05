"""M82 (user decision 2026-10-05): the plan gate locks the outcome horizon from the conversation router's structured
reading of the newest message, cross-checked by the pattern reading; without a router reading the newest statement
found by the patterns wins."""
from __future__ import annotations

from app.conversation_router import TurnClassification
from app.user_words import MESSAGE_SEPARATOR, locked_horizons

FIRST = "Apakah saham bank yang turun 3% dalam sehari cenderung naik dalam 5 hari berikutnya?"


def words(*messages: str) -> list[str]:
    return [MESSAGE_SEPARATOR.join(messages)]


def change(value: int, unit: str = "DAY", action: str = "REPLACE") -> dict:
    return {"name": "OUTCOME_HORIZON", "value": value, "unit": unit, "action": action}


def test_router_replace_wins_and_agrees_with_the_words() -> None:
    assert locked_horizons(words(FIRST, "ubah horizonnya jadi 10 hari"), [change(10)]) == ({(10, "DAY")}, None)


def test_router_add_keeps_the_earlier_horizon() -> None:
    locked, note = locked_horizons(words(FIRST, "bandingkan juga dengan 20 hari ke depan"), [change(20, action="ADD")])
    assert locked == {(5, "DAY"), (20, "DAY")} and note is None


def test_a_message_without_a_horizon_keeps_the_earlier_one() -> None:
    assert locked_horizons(words(FIRST, "ok setuju, jalankan"), []) == ({(5, "DAY")}, None)


def test_a_condition_window_the_router_ignores_never_unlocks_or_replaces_the_horizon() -> None:
    # the words read "setelah 3 hari" as a horizon; the router does not: both are allowed and the note says so
    locked, note = locked_horizons(words(FIRST, "pakai kejadian setelah 3 hari turun berturut-turut"), [])
    assert (5, "DAY") in locked and note is not None


def test_a_lookback_period_in_a_later_message_does_not_drop_the_horizon() -> None:
    locked, _ = locked_horizons(words(FIRST, "pakai jangka waktu 3 bulan terakhir"), [])
    assert (5, "DAY") in locked


def test_router_and_words_disagree_both_are_allowed() -> None:
    locked, note = locked_horizons(words(FIRST, "horizonnya 2 minggu"), [change(14)])
    assert locked == {(14, "DAY"), (2, "WEEK")} and "router read" in note


def test_without_a_router_reading_the_newest_statement_wins() -> None:
    assert locked_horizons(words(FIRST, "ubah horizonnya jadi 10 hari"), None) == ({(10, "DAY")}, None)
    assert locked_horizons(words(FIRST, "jalankan"), None) == ({(5, "DAY")}, None)


def test_a_non_positive_router_value_is_ignored_not_a_failed_routing() -> None:
    parsed = TurnClassification.model_validate({"turn_kind": "REVISE", "revision_instruction": "x", "referent":
                                                "PENDING_SUGGESTION", "design_value_changes": [change(0)]})
    assert locked_horizons(words(FIRST, "ubah"), [c.model_dump() for c in parsed.design_value_changes]) == (
        {(5, "DAY")}, None)


def test_the_router_reply_without_changes_still_parses() -> None:
    parsed = TurnClassification.model_validate({"turn_kind": "CLARIFY", "revision_instruction": None,
                                                "referent": "NEWEST_RESULT"})
    assert parsed.design_value_changes == []
