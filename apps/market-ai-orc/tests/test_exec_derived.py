"""EXEC-DERIVED (user 2026-10-13, "masukan exec dan jalankan"): a number without a source that equals a difference, an
absolute value, a relative change or a ratio of this run's referable values is named with that reference in the
refusal and in the draft check, never put in by the backend (A/B 3 ab5: "654" = 1.498 − 844; A/B 2 ab3: "selisih 1,04
poin persen" of two returns)."""
from __future__ import annotations

import pytest

from app.orchestrator import DERIVED_MAX_MATCHES, AgentOrchestrator, GateRejection, RunState
from app.schemas import FinalResponse
from app.tools import ToolOutcome
from test_day_counts_and_draft_check import orchestrator


def tracked(content: dict, rows: list[dict] | None = None) -> tuple[AgentOrchestrator, RunState]:
    orc, state = orchestrator(), RunState(request_id="r", started=0.0, input_items=[])
    released = [{"output_id": "out_sum", "name": "summary", "type": "JSON", "content": content}]
    if rows is not None:
        released.append({"output_id": "out_rank", "name": "rank", "type": "TABLE", "rows": rows})
    orc._track_references(state, "complete_analysis", ToolOutcome(
        call_id="c", name="complete_analysis", ok=True,
        output={"result": {"status": "COMPLETED", "session_id": "s", "released_contents": released}}))
    values = [v for v in content.values() if isinstance(v, (int, float))]
    values += [v for r in rows or [] for v in r.values() if isinstance(v, (int, float))]
    state.analysis_values["completion:c"] = {"label": "DATA_COVERAGE_VERIFIED", "values": values}
    return orc, state


def test_a_difference_of_two_counts_is_named() -> None:
    orc, state = tracked({"ticker_arus_asing": 1498, "ticker_berharga": 844})
    found = orc._derived_readings(state, ["654"], "Dari 1.498 ticker, 844 punya harga; 654 tanpa harga.")
    assert found == {"654": ["diff(out.o1.content.ticker_arus_asing, out.o1.content.ticker_berharga)"]}


def test_a_return_gap_written_without_its_sign_is_named_in_both_orders_of_reading() -> None:
    orc, state = tracked({}, rows=[{"ticker": "BBCA", "ret": -0.0593}, {"ticker": "BBRI", "ret": -0.0489}])
    found = orc._derived_readings(state, ["1,04"], "BBCA −5,93%, BBRI −4,89%; selisih 1,04 poin persen.")
    assert found["1,04"] and all(r.startswith(("diff(", "chg(", "ratio(")) for r in found["1,04"])
    assert any("rows" in r and "BBRI" in r and r.startswith("diff(") for r in found["1,04"])


def test_a_negative_value_written_without_its_sign_is_its_absolute_value() -> None:
    orc, state = tracked({"selisih_pp": -1.04})
    assert orc._derived_readings(state, ["1,04"], "Selisihnya −1,04 pp, jadi selisih 1,04.") == {
        "1,04": ["abs(out.o1.content.selisih_pp)"]}
    assert orc._derived_readings(state, ["1,04"], "Selisih 1,04.") == {}  # its operand is not in the text


def test_a_number_with_many_readings_is_not_named_because_the_match_may_be_chance() -> None:
    orc, state = tracked({f"n{i}": float(i) for i in range(40)})
    text = ", ".join(str(i) for i in range(40))
    assert orc._derived_readings(state, ["5"], text) == {}  # 5 = 6 − 1 = 7 − 2 = … : chance, not meaning
    assert orc._derived_readings(state, ["123456"], text) == {}  # nothing equals it


def test_the_methodology_refusal_names_the_reading_and_the_answer_is_not_changed() -> None:
    orc, state = tracked({"ticker_arus_asing": 1498, "ticker_berharga": 844})
    orc.methodology = True
    final = FinalResponse(response_type="ANSWER", answer="Ringkasan.", assumptions=[], limitations=[],
                          methodology="Dari 1.498 ticker, 844 punya harga dan 654 tanpa harga.")
    state.completions["c"] = {"status": "COMPLETED"}
    with pytest.raises(GateRejection) as refused:
        orc._methodology_gate(state, final)
    message = str(refused.value)
    assert "654 equals {{diff(out.o1.content.ticker_arus_asing, out.o1.content.ticker_berharga)}}" in message
    assert "if that is what the number means" in message
    assert state.referenced == [] and "654" in final.methodology  # suggested, never put in


def test_the_draft_check_lists_the_derived_reference() -> None:
    orc, state = tracked({"ticker_arus_asing": 1498, "ticker_berharga": 844})
    report = orc._check_draft(state, "Dari 1.498 ticker, 844 punya harga dan 654 tanpa harga.")
    assert report["status"] == "WOULD_BE_REFUSED"
    assert report["derived_references"]["654"] == [
        "{{diff(out.o1.content.ticker_arus_asing, out.o1.content.ticker_berharga)}}"]


def test_a_relative_change_is_named_only_for_a_percent_and_never_by_chance_for_a_plain_number() -> None:
    orc, state = tracked({"awal": 3270.0, "akhir": 3110.0, "kecil": 0.0864675897282483, "besar": 0.651592972722763})
    text = "Dari Rp 3.270 ke Rp 3.110 (−4,9%); nilai 0,0865 dan 0,6516; 654."
    assert orc._derived_readings(state, ["−4,9%"], text) == {"−4,9%": ["chg(out.o1.content.akhir, out.o1.content.awal)"]}
    assert orc._derived_readings(state, ["654"], text) == {}  # besar / kecil − 1 = 6,54: chance, not 654
