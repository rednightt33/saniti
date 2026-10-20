"""H1 (M63): a consistency claim is checked against the definitions of the results produced and opened."""
from __future__ import annotations

from app import definition_check as D

REGULAR = {"filters": [{"column": "market_board", "operator": "EQ", "value": "Regular"}]}
ALL_BOARDS = {"filters": [], "notes": "boards combined"}


def test_a_claim_with_another_definition_is_a_problem() -> None:
    """The golden-test turn 3: Regular only, "agar konsisten dengan jawaban sebelumnya", the ranking had all boards."""
    text = "Analisis dibatasi pada board Regular agar konsisten dengan jawaban sebelumnya."
    found = D.problems(text, [{"name": "top15", "definition": REGULAR}], [{"name": "ranking", "definition": ALL_BOARDS}])
    assert found and "top15" in found[0] and "Regular" in found[0] and "ranking" in found[0]


def test_the_same_definition_or_no_claim_passes() -> None:
    same = D.problems("Definisi yang sama dengan tabel tadi.", [{"name": "x", "definition": {**ALL_BOARDS, "notes": "y"}}],
                      [{"name": "ranking", "definition": ALL_BOARDS}])
    assert same == []  # notes are free text and not compared
    assert D.problems("TF tertinggi karena sering membeli.", [{"name": "x", "definition": REGULAR}],
                      [{"name": "ranking", "definition": ALL_BOARDS}]) == []


def test_a_claim_without_an_opened_result_cannot_be_checked() -> None:
    found = D.problems("Hasil ini consistent with the previous answer.", [{"name": "x", "definition": REGULAR}], [])
    assert found and "opened no earlier result" in found[0]
    assert D.problems("Cakupan yang sama.", [{"name": "x", "definition": REGULAR}],
                      [{"name": "ranking", "definition": None}])[0].startswith("the earlier")


def test_a_run_that_produced_no_new_result_is_not_checked() -> None:
    """M151 (run edge_80e733ba): an export of earlier tables says they follow the earlier definition; nothing new was
    produced, so nothing can differ."""
    assert D.problems("File ini memakai definisi yang sama dengan hasil sebelumnya.", [], []) == []
    assert D.problems("Cakupan yang sama.", [], [{"name": "ranking", "definition": None}]) == []


BANKS = {"filters": [], "period": {"start": "2026-01-02", "end": "2026-10-16"}, "entities": ["BBCA", "BBRI", "BMRI"]}
WITH_BBNI = {**BANKS, "entities": ["BBCA", "BBRI", "BMRI", "BBNI"]}


def test_stocks_the_user_asked_to_add_are_not_a_different_definition() -> None:
    """M192 (2) (edge_43d32073…-m4n: "Tambahkan BBNI ke perbandingan tadi, dengan cara hitung yang sama")."""
    text = "Dengan rumus, periode dan filter yang sama seperti jawaban sebelumnya, BBNI ditambahkan."
    produced, opened = [{"name": "bank_returns_4", "definition": WITH_BBNI}], [{"name": "r", "definition": BANKS}]
    assert D.findings(text, produced, opened, scope_added=True) == []
    found = D.findings(text, produced, opened)  # without the user's addition the list of stocks differs
    assert [f["fields"] for f in found] == [["entities"]]
    other = {**WITH_BBNI, "period": {"start": "2025-01-02", "end": "2026-10-16"}}
    assert D.findings(text, [{"name": "x", "definition": other}], opened, scope_added=True)[0]["fields"] == ["period"]


def test_the_refusal_can_quote_the_sentence_that_made_the_claim() -> None:
    text = "BBNI naik 5%. Dengan rumus yang sama seperti jawaban sebelumnya, urutannya tetap. Selesai."
    assert D.claim_sentence(text) == "Dengan rumus yang sama seperti jawaban sebelumnya, urutannya tetap."


def test_the_note_under_the_answer_is_plain_indonesian_without_json() -> None:
    """M192 (4): it used to append `bank_returns_4 uses {"entities": ...}`."""
    from app import user_texts as T
    from test_user_texts import problems as language_problems
    found = D.findings("Cakupan yang sama.", [{"name": "x", "definition": REGULAR}],
                       [{"name": "ranking", "definition": ALL_BOARDS}])
    note = T.definition_note(found[0])
    assert note.startswith("Catatan sistem: jawaban menyebut hasil ini sama dengan hasil sebelumnya, padahal filter")
    assert "Regular" in note and "tanpa filter" in note and "{" not in note and language_problems(note) == []
    stocks = T.definition_note({"kind": "DIFFERENT", "fields": ["entities"], "mine": WITH_BBNI, "earlier": BANKS})
    assert "4 saham (BBCA, BBRI, BMRI, BBNI)" in stocks and "3 saham" in stocks
    assert language_problems(T.definition_note({"kind": "NOT_OPENED"})) == []
