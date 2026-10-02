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
    assert D.problems("Cakupan yang sama.", [], [{"name": "ranking", "definition": None}])[0].startswith("the earlier")
