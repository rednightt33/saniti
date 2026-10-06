"""Variants and the multiple-testing correction (user decision 2026-10-06, "2+5 Varian + koreksi", merged into EXEC-3
and EXEC-A; AI_ENABLE_ASK_BACK): the routers read every design value with ADD, REPLACE or REMOVE; a plan keeps every
value the user named (a missing one is asked for once, then named in the plan's limitations); a removed threshold is
no longer the user's; the working step is told to answer every variant; every test of the conversation is corrected
together and listed, also the ones that do not pass."""
from __future__ import annotations

import copy

import pytest

from app import variant_correction as vc
from app.orchestrator import GateRejection, RunState
from app.schemas import FinalResponse
from app.user_words import MESSAGE_SEPARATOR, current_design_changes, design_values, locked_horizons, variants
from test_research_findings import EXPERIMENT, FINDINGS_VALUES, PLAN, agent, state

FIRST = "Apakah saham bank yang turun 3% dalam sehari cenderung naik dalam 5 hari berikutnya?"
VARIANT_QUESTION = "Kalau volume BBCA minimal 2x dan 3x rata-rata, apakah harganya naik dalam 3 dan 10 hari?"


def words(*messages: str) -> list[str]:
    return [MESSAGE_SEPARATOR.join(messages)]


def change(name: str, value: float | None, unit: str, action: str = "ADD", text: str | None = None) -> dict:
    return {"name": name, "value": value, "unit": unit, "text": text, "action": action}


VARIANT_CHANGES = [change("CONDITION_THRESHOLD", 2, "MULTIPLE"), change("CONDITION_THRESHOLD", 3, "MULTIPLE"),
                   change("OUTCOME_HORIZON", 3, "DAY"), change("OUTCOME_HORIZON", 10, "DAY")]


# ---------------------------------------------------------------- the reading

def test_remove_takes_a_horizon_out_and_replace_with_add_keeps_only_the_new_ones() -> None:
    removed = [change("OUTCOME_HORIZON", 5, "DAY", "REMOVE"), change("OUTCOME_HORIZON", 10, "DAY", "ADD")]
    assert locked_horizons(words(FIRST, "hapus horizon 5 hari, pakai 10 hari"), removed) == ({(10, "DAY")}, None)
    mixed = [change("OUTCOME_HORIZON", 10, "DAY", "REPLACE"), change("OUTCOME_HORIZON", 20, "DAY", "ADD")]
    assert locked_horizons(words(FIRST, "ganti jadi 10 hari dan tambah 20 hari"), mixed)[0] == {(10, "DAY"),
                                                                                                (20, "DAY")}


def test_the_add_of_the_h_add_turn_keeps_both_horizons() -> None:
    """M90 (golden tests 06b and 06e): "tambahkan juga horizon 10 hari, tetap uji yang 3 hari" is ADD."""
    first = "Apakah volume BBCA di atas 2x rata-rata diikuti kenaikan dalam 3 hari ke depan?"
    locked, note = locked_horizons(words(first, "tambahkan juga horizon 10 hari, tetap uji yang 3 hari"),
                                   [change("OUTCOME_HORIZON", 10, "DAY")])
    assert locked == {(3, "DAY"), (10, "DAY")} and note is None


def test_a_first_message_with_two_horizons_locks_both_without_a_disagreement() -> None:
    locked, note = locked_horizons(words(VARIANT_QUESTION), VARIANT_CHANGES)
    assert locked == {(3, "DAY"), (10, "DAY")} and note is None


def test_a_threshold_unit_is_never_read_as_a_horizon() -> None:
    assert locked_horizons(words(FIRST), [change("OUTCOME_HORIZON", 2, "MULTIPLE")])[0] == {(5, "DAY")}


def test_variants_and_design_values() -> None:
    assert variants(VARIANT_CHANGES) == {"CONDITION_THRESHOLD": ["2 MULTIPLE", "3 MULTIPLE"],
                                         "OUTCOME_HORIZON": ["3 DAY", "10 DAY"]}
    assert variants([change("OUTCOME_HORIZON", 3, "DAY")]) == {}
    assert variants([change("SCOPE", None, "NONE", text="BBCA"), change("SCOPE", None, "NONE", text="BBRI")]) == {
        "SCOPE": ["BBCA", "BBRI"]}
    assert design_values(VARIANT_CHANGES, "CONDITION_THRESHOLD", "ADD") == [2.0, 3.0]
    assert design_values(VARIANT_CHANGES, "CONDITION_THRESHOLD", "REMOVE") == []


# ---------------------------------------------------------------- the plan gate

def plan_of(*experiments: tuple[str, int, str], success: float | None = None) -> FinalResponse:
    plan = copy.deepcopy(PLAN)
    plan["original_question"] = VARIANT_QUESTION
    plan["experiments"] = []
    for index, (condition, horizon, outcome) in enumerate(experiments, start=1):
        experiment = {**copy.deepcopy(EXPERIMENT), **FINDINGS_VALUES, "experiment_id": f"experiment_{index}",
                      "hypothesis_id": f"h{index}", "condition": condition, "outcome": outcome,
                      "outcome_horizon_periods": horizon}
        if success is not None:
            experiment["success_rule"] = {"operator": ">=", "value": success}
        plan["experiments"].append(experiment)
    return FinalResponse.model_validate({"response_type": "RESEARCH_PLAN_CONFIRMATION", "answer": "Rencana uji.",
                                         "clarification_question": None, "assumptions": [], "limitations": [],
                                         "research_plan": plan})


def gate(plan: FinalResponse, changes: list[dict], text: str = VARIANT_QUESTION, rejected: bool = False):
    orchestrator = agent()
    orchestrator.audit_outbox, orchestrator.ask_back = None, True
    s = state(orchestrator)
    s.user_text = text
    if rejected:
        s.gate_kinds_rejected.add("PLAN_VARIANT_COVERAGE")
    token = current_design_changes.set(changes)
    try:
        return orchestrator._plan_gate(s, plan)
    finally:
        current_design_changes.reset(token)


TWO_BY_TWO = [("Volume at least 2 times its average.", 3, "Return over 3 days."),
              ("Volume at least 2 times its average.", 10, "Return over 10 days."),
              ("Volume at least 3 times its average.", 3, "Return over 3 days."),
              ("Volume at least 3 times its average.", 10, "Return over 10 days.")]


def test_a_plan_with_every_variant_passes() -> None:
    passed = gate(plan_of(*TWO_BY_TWO), VARIANT_CHANGES)
    assert passed.response_type == "RESEARCH_PLAN_CONFIRMATION" and passed.limitations == []


def test_a_missing_variant_is_asked_for_once_then_named_in_the_plan() -> None:
    plan = plan_of(*TWO_BY_TWO[:1])
    with pytest.raises(GateRejection, match="PLAN_VARIANT_COVERAGE|outcome horizon 10 periods") as raised:
        gate(plan, VARIANT_CHANGES)
    assert "condition threshold 3" in str(raised.value)
    passed = gate(plan, VARIANT_CHANGES, rejected=True)
    assert passed.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert passed.limitations == ["Varian yang diminta user tetapi tidak ada di rencana ini: outcome horizon 10 "
                                  "periods, condition threshold 3."]


def test_without_the_switch_or_without_a_router_reading_no_variant_is_required() -> None:
    plan = plan_of(*TWO_BY_TWO[:1])
    assert gate(plan, None).limitations == []
    orchestrator = agent()
    orchestrator.audit_outbox = None  # ask_back off
    s = state(orchestrator)
    s.user_text = VARIANT_QUESTION
    token = current_design_changes.set(VARIANT_CHANGES)
    try:
        assert orchestrator._plan_gate(s, plan).limitations == []
    finally:
        current_design_changes.reset(token)


def test_a_removed_success_threshold_is_no_longer_the_users() -> None:
    text = MESSAGE_SEPARATOR.join(["Naik minimal 3% dalam 5 hari?", "hapus syarat 3%, cukup naik saja"])
    plan = plan_of(("A fall of more than five percent in a day.", 5, "Return over five days."), success=3.0)
    with pytest.raises(GateRejection, match="success_rule value 3"):
        gate(plan, [change("SUCCESS_THRESHOLD", 3, "PERCENT", "REMOVE")], text=text)


# ---------------------------------------------------------------- the working step's note

def test_the_working_step_is_told_to_answer_every_variant() -> None:
    orchestrator = agent()
    orchestrator.ask_back = True
    s = RunState(request_id="q", started=0.0, input_items=[{"role": "user", "content": "m"}])
    token = current_design_changes.set(VARIANT_CHANGES)
    try:
        orchestrator._apply_turn_kind(s)
    finally:
        current_design_changes.reset(token)
    note = s.input_items[0]["content"]
    assert note.startswith("Application note (router)") and "CONDITION_THRESHOLD: 2 MULTIPLE, 3 MULTIPLE" in note
    assert "rows[variant=...]" in note and "also those that do not pass" in note


# ---------------------------------------------------------------- the correction

def test_holm_and_benjamini_hochberg() -> None:
    assert vc.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert vc.benjamini_hochberg([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.04, 0.04])
    assert vc.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def ledger(*tests: tuple[str, float, str]) -> dict:
    return {"findings": [{"id": hid, "kind": "HYPOTHESIS", "request_id": rid, "seq": i, "finding": {
        "hypothesis_id": hid, "angle_a": {"p_value": p}, "parameters": {"horizon_periods": 3,
                                                                       "multiple_testing_policy": "NONE"}}}
        for i, (hid, p, rid) in enumerate(tests)]}


def test_every_test_of_the_conversation_is_corrected_together_and_listed() -> None:
    record = ledger(("h1", 0.01, "t1"), ("h2", 0.04, "t2"), ("h3", 0.03, "t2"))
    correction = vc.correct(record)
    assert correction["policy"] == "HOLM" and correction["family_size"] == 3
    assert [t["p_adjusted"] for t in correction["tests"]] == pytest.approx([0.03, 0.06, 0.06])
    assert record["findings"][1]["finding"]["conversation_correction"] == {"policy": "HOLM", "family_size": 3,
                                                                          "p_adjusted": 0.06}
    line = vc.line(correction)
    assert "h1 p 0,01 → 0,03;" in line and "h2 p 0,04 → 0,06 (tidak lolos)" in line
    assert "Semua uji ditampilkan" in line
    assert vc.correct(ledger(("h1", 0.01, "t1"))) is None


def test_a_benjamini_hochberg_policy_switches_the_correction() -> None:
    record = ledger(("h1", 0.01, "t1"), ("h2", 0.04, "t2"))
    record["findings"][1]["finding"]["parameters"]["multiple_testing_policy"] = "BENJAMINI_HOCHBERG"
    assert vc.correct(record)["policy"] == "BENJAMINI_HOCHBERG"


def test_the_answer_lists_the_correction_only_when_this_run_tested() -> None:
    orchestrator = agent()
    orchestrator.ask_back = True
    answer = FinalResponse(response_type="ANSWER", answer="Hasil.", clarification_question=None, assumptions=[],
                           limitations=["Batas data."])
    s = RunState(request_id="t2", started=0.0, input_items=[])
    s.data_record = ledger(("h1", 0.01, "t1"), ("h2", 0.04, "t2"))
    out = orchestrator._conversation_correction(s, answer)
    assert out.limitations[0] == "Batas data." and out.limitations[1].startswith("Koreksi uji berganda")
    s.request_id = "t3"
    assert orchestrator._conversation_correction(s, answer) == answer
    orchestrator.ask_back = False
    s.request_id = "t2"
    assert orchestrator._conversation_correction(s, answer) == answer
