"""EXEC-PROSE (user 2026-10-13, "both usulan 1 dan 2 ok", "2a + yg tadi kamu mention"): the router names a period in
words (A/B 2 and 3 ab6: "30 hari kalender terakhir" reached the answer and PROVENANCE refused it); check_references
checks a draft's methodology as METHODOLOGY_PROVENANCE does and says when a draft is shortened (A/B 3 ab6: "..." left
the sentence with "30" unchecked; ab5: "654" in the methodology); the TABLES section keeps the text around a table
short, with new figures from the analysis or diff/ratio/abs/chg of references."""
from __future__ import annotations

from app import conversation_router as router
from app.orchestrator import TABLE_DIRECTIVE_RULES
from app.tools.references import CheckReferencesArguments, check
from app.tools.request_data import current_draft_checker
from test_day_counts_and_draft_check import tracked


def test_every_router_that_reads_the_intent_names_a_period_in_words() -> None:
    assert "never as a count of days" in router.PERIOD_WORDS_RULE
    assert router.PERIOD_WORDS_RULE in router.FIRST_INSTRUCTIONS_ASK_BACK
    assert router.PERIOD_WORDS_RULE in router.ROUTER_INSTRUCTIONS_ASK_BACK


def test_the_intent_note_says_its_own_numbers_are_not_a_source() -> None:
    note = router.intent_note({"understood_intent": "Net buy broker BBRI sebulan terakhir.",
                               "assumptions": ["sebulan terakhir = bulan data terakhir yang tersedia"]})
    assert note.endswith("A number in this note that the user did not write is the router's reading, not a source: "
                         "never repeat it in the answer.")


def test_the_methodology_of_a_draft_is_checked_like_the_methodology_gate() -> None:
    orc, state = tracked()
    state.code_numbers.append(844.0)  # a number in the code of a successful run_python call is a methodology source
    report = orc._check_draft(state, "", "Dari 1.498 ticker, 844 punya harga; 654 tanpa harga.")
    assert report["status"] == "WOULD_BE_REFUSED"
    assert "654" in report["methodology_numbers_without_source"] and "1.498" in report["methodology_numbers_without_source"]
    assert "844" not in report["methodology_numbers_without_source"] and report["numbers_without_source"] == []
    clean = orc._check_draft(state, "", "Periode {{data.flows.august.dates|int}} hari bursa; 844 ticker berharga.")
    assert clean["status"] == "OK" and clean["methodology_numbers_without_source"] == []


def test_a_shortened_draft_is_said_to_be_one() -> None:
    orc, state = tracked()
    report = orc._check_draft(state, "Periode {{data.flows.august.dates|int}} hari bursa ... (sisanya sama).")
    assert report["status"] == "SHORTENED" and "not checked" in report["shortened_note"]
    full = orc._check_draft(state, "Periode {{data.flows.august.dates|int}} hari bursa.")
    assert full["status"] == "OK" and "shortened_note" not in full


def test_check_references_takes_a_methodology_alone() -> None:
    orc, state = tracked()
    token = current_draft_checker.set(lambda text, methodology="": orc._check_draft(state, text, methodology))
    try:
        result = check([], state.ref_sources, None, "Sebanyak 654 ticker tanpa harga.")
        assert result["draft"]["methodology_numbers_without_source"] == ["654"]
    finally:
        current_draft_checker.reset(token)
    assert CheckReferencesArguments(references=[], draft=None, methodology="Langkah.").methodology == "Langkah."


def test_the_tables_section_keeps_the_text_around_a_table_short() -> None:
    assert "the text around it stays short" in TABLE_DIRECTIVE_RULES
    assert "diff, ratio, abs or chg of references" in TABLE_DIRECTIVE_RULES
    assert "an example amount is said in words" in TABLE_DIRECTIVE_RULES
