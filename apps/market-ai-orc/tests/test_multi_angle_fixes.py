"""Multi-Angle Research fixes after suite20 (2026-09-29; MULTI_ANGLE_FIX_PLAN.md, ERRORS_AND_SOLUTIONS.md).

M36: the first finalize while an approved angle is unrecorded names what is missing. M38: each angle's design is
checked by check_research_feasibility and the plan must carry exactly the checked design. P09: an agreement phrase
negated in its clause is not a claim, and a LIMITATION forced by the findings gate keeps the backend's per-angle
findings. Item 7: fewer angles and the optional method-family coverage. C07: the research library is the model's
source of the methods, bound to the table, the sandbox and this service by one hash."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app import research_library as L
from app.config import ConfigError
from app.main import _with_research_library
from app.orchestrator import NEGATION_PATTERN, AGREEMENT_WORDING, negated_in_clause
from app.research_plan_v2 import (LIBRARY_COLUMNS, design_differences, design_sha256, library_problem)
from app.schemas import AgentRunRequest
from app.tools.catalog import RESEARCH_REFERENCE_ONLY, CatalogTools
from app.tools.library import ResearchLibraryArgs, research_library_spec
from app.tools.registry import ToolError
from conftest import final_response, make_settings
from test_multi_angle import (QUESTION, RUN_SCRIPT, RunSandbox, agent, angles, approved_run, call, data_plan, design,
                              executor, feasibility_args, findings_answer, plan_response, planner, run_plan,
                              two_groups)
from app.tools.request_data import current_request_id

HERE = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- M36

def test_an_early_finalize_is_refused_once_and_only_while_calls_remain() -> None:
    sandbox = RunSandbox(complete_status="INCOMPLETE")
    run = executor(sandbox, dp=two_groups())
    token = current_request_id.set("run_002")
    try:
        run.start()
        early = run.complete(True)
        assert early["status"] == "INCOMPLETE" and early["code"] == "ANGLES_NOT_RECORDED"
        assert early["missing_angle_ids"] == ["a_lag"] and early["groups_not_run"] == ["g2"]
        assert "finalize false" in early["message"] and early["next_action"] == "RECORD_MISSING_ANGLES"
        # nothing was closed or recorded as NOT_RUN by the refusal
        assert not [c for c in sandbox.calls if c[1].endswith("/close")]
        sandbox.complete_status = "COMPLETED"
        done = run.complete(True)
        assert done["status"] == "COMPLETED"
    finally:
        current_request_id.reset(token)
    # with one tool call left the model could not record the angle: finalize is accepted at once
    sandbox = RunSandbox(complete_status="COMPLETED")
    run = executor(sandbox, dp=two_groups())
    token = current_request_id.set("run_002")
    try:
        run.start()
        assert run.complete(True, calls_left=1)["status"] == "COMPLETED"
    finally:
        current_request_id.reset(token)


def test_the_run_reminder_asks_for_finalize_false_first() -> None:
    from app.orchestrator import RESEARCH_RUN_INCOMPLETE_INSTRUCTION, MULTI_ANGLE_PLAN_RULES

    assert "finalize false" in RESEARCH_RUN_INCOMPLETE_INSTRUCTION
    assert "finalize true records every angle" not in RESEARCH_RUN_INCOMPLETE_INSTRUCTION
    assert "complete_research_run with finalize false" in " ".join(MULTI_ANGLE_PLAN_RULES.split())


def test_the_orchestrator_tells_the_executor_how_many_calls_remain() -> None:
    script = [call("start_research_run", {}, "c1"),
              call("run_research_code", {"bundle_group_id": "g1", "code": "saniti.research_conditional(...)"}, "c2"),
              call("complete_research_run", {"finalize": True}, "c3"),
              final_response(findings_answer())]
    result, scripted, sandbox, _ = approved_run(script)
    # AI_MAX_TOOL_CALLS 14 in the test settings: the single group completes without finalize, nothing is missing
    assert result.response.response_type == "ANSWER"
    completes = [c for c in sandbox.calls if c[1].endswith("/complete")]
    assert completes and completes[0][2]["finalize"] is False


# ---------------------------------------------------------------- M38

def design_codes(outcome: dict[str, Any]) -> list[str]:
    return [i["code"] for i in outcome["view"]["issues"]]


def test_the_feasibility_check_applies_the_rules_the_final_plan_enforces() -> None:
    base = feasibility_args()["angles"]
    # suite20 r06/r12: a holdout with a single range
    holdout = copy.deepcopy(base)
    holdout[0]["design"]["holdout_required"] = True
    outcome = run_plan(planner()[0], feasibility_args(holdout))
    assert outcome["status"] == "REVISION_REQUIRED" and design_codes(outcome) == ["HOLDOUT_NEEDS_TWO_RANGES"]
    assert outcome["view"]["issues"][0]["angle_id"] == "a_fall"
    two_ranges = copy.deepcopy(holdout)
    two_ranges[0]["data_requests"][0]["time_ranges"] = [
        {"range_id": "fit", "start": "2021-01-04", "end": "2024-12-30"},
        {"range_id": "holdout", "start": "2025-01-02", "end": "2026-09-25"}]
    assert run_plan(planner()[0], feasibility_args(two_ranges))["status"] == "FEASIBLE"
    # suite20 r10/e04: regime_comparison without groups / comparison, pairwise below what the groups imply
    regime = copy.deepcopy(base)
    regime[0]["design"].update(method_id="regime_comparison", parameters={**regime[0]["design"]["parameters"],
                                                                         "baseline_mode": None})
    outcome = run_plan(planner()[0], feasibility_args(regime))
    messages = [i["message"] for i in outcome["view"]["issues"]]
    assert "regime_comparison needs groups" in messages and "regime_comparison needs comparison" in messages
    regime[0]["design"]["parameters"].update(groups=["BULL", "BEAR", "FLAT"], comparison="PAIRWISE")
    regime[0]["design"].update(multiple_testing_policy="HOLM")
    outcome = run_plan(planner()[0], feasibility_args(regime))
    assert outcome["view"]["issues"][0]["message"] == \
        "pairwise_comparisons 0 is below the 3 comparisons the groups imply"
    # several comparisons need a multiple-testing policy
    lag = copy.deepcopy(base)
    lag[2]["design"]["multiple_testing_policy"] = "NONE"
    assert design_codes(run_plan(planner()[0], feasibility_args(lag))) == ["MULTIPLE_TESTING_POLICY_REQUIRED"]


def test_the_feasibility_check_applies_the_library_data_requirements() -> None:
    base = feasibility_args()["angles"]
    no_entity = copy.deepcopy(base)
    no_entity[1]["data_requests"][0]["entity_column"] = None
    assert "ENTITY_COLUMN_REQUIRED" in design_codes(run_plan(planner()[0], feasibility_args(no_entity)))
    no_price = copy.deepcopy(base)
    no_price[0]["design"]["outcome_price"] = None
    assert design_codes(run_plan(planner()[0], feasibility_args(no_price))) == ["OUTCOME_PRICE_REQUIRED"]
    wrong_column = copy.deepcopy(base)
    wrong_column[0]["design"]["outcome_price"]["column"] = "adj_close"
    assert design_codes(run_plan(planner()[0], feasibility_args(wrong_column))) == ["OUTCOME_PRICE_COLUMN_MISSING"]
    other_request = copy.deepcopy(base)
    other_request[0]["design"]["outcome_price"]["data_request_id"] = "a_rank_A"
    assert design_codes(run_plan(planner()[0], feasibility_args(other_request))) == ["OUTCOME_PRICE_REQUEST_UNKNOWN"]


def test_a_forward_return_widens_a_short_future_buffer_and_says_so() -> None:
    args = feasibility_args()
    args["angles"][0]["design"]["outcome_horizon_periods"] = 20
    planner_, sandbox = planner()
    outcome = run_plan(planner_, args)
    assert outcome["status"] == "FEASIBLE"
    [adjustment] = outcome["view"]["adjustments"]
    assert adjustment["angle_id"] == "a_fall" and adjustment["future_buffer"] == {"value": 20,
                                                                                 "unit": "TRADING_OBSERVATIONS"}
    merged = [r for spec in sandbox.checks for r in spec["data_requests"] if r["source_table"] ==
              "Price_Stock_Indonesia_IDX"]
    assert merged and all(r["future_buffer"]["value"] >= 20 for r in merged)
    assert args["angles"][0]["data_requests"][0]["future_buffer"]["value"] == 5  # the caller's arguments unchanged


def test_the_data_plan_binds_every_checked_design() -> None:
    dp = data_plan()
    assert set(dp["angle_design_sha256s"]) == {"a_fall", "a_rank", "a_lag"}
    for plan_angle in angles():
        assert dp["angle_design_sha256s"][plan_angle["angle_id"]] == design_sha256(plan_angle)
    changed = {**angles()[2], "parameters": {**angles()[2]["parameters"], "primary_lag": 3}}
    assert design_sha256(changed) != dp["angle_design_sha256s"]["a_lag"]
    assert design_differences(changed, design("a_lag", "a_lag_A")) == ["parameters"]


def test_a_plan_whose_design_differs_from_the_checked_one_gets_two_repairs() -> None:
    changed = angles()
    changed[2]["parameters"]["lags"] = [1, 2, 3, 4]
    changed[2]["candidate_count"] = 4
    runner, scripted, _ = agent([call("check_research_feasibility", feasibility_args(), "c1"),
                                 final_response(plan_response(angles=changed)),
                                 final_response(plan_response(angles=changed)),
                                 final_response(plan_response())])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION))
    first, second = str(scripted.payloads[2]["input"][-1]), str(scripted.payloads[3]["input"][-1])
    assert "a_lag: parameters, candidate_count differ from the design check_research_feasibility checked" in first
    assert "a_lag: parameters" in second  # PLAN_FEASIBILITY_2, not a forced LIMITATION
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION" and result.continuation is not None


# ---------------------------------------------------------------- item 7

def test_two_angles_are_enough_and_family_coverage_is_optional() -> None:
    two = feasibility_args(feasibility_args()["angles"][:2])
    assert run_plan(planner()[0], two)["status"] == "FEASIBLE"
    planner_, _ = planner()
    planner_.min_families = 3
    outcome = run_plan(planner_, two)
    assert outcome["status"] == "REVISION_REQUIRED" and design_codes(outcome) == ["FAMILY_COVERAGE"]
    planner_.min_families = 2
    assert run_plan(planner_, two)["status"] == "FEASIBLE"


def test_the_angle_and_family_settings_are_validated() -> None:
    base = make_settings()
    assert base.ai_research_min_angles == 2 and base.ai_research_min_families == 0
    with pytest.raises(ConfigError, match="2 <= min"):
        make_settings(AI_RESEARCH_MIN_ANGLES="1")
    with pytest.raises(ConfigError, match="AI_RESEARCH_MIN_FAMILIES"):
        make_settings(AI_RESEARCH_MIN_FAMILIES="6")
    assert make_settings(AI_RESEARCH_MIN_FAMILIES="5").ai_research_min_families == 5


# ---------------------------------------------------------------- P09

R08 = ("Peta sintesis tidak mengizinkan pernyataan bahwa sudut-sudut saling mendukung, karena hanya satu sudut yang "
       "didukung.")


def test_an_agreement_phrase_negated_in_its_clause_is_not_a_claim() -> None:
    match = re.search(AGREEMENT_WORDING, R08, re.IGNORECASE)
    assert match is not None and match.start() - R08.index("tidak") > 40  # the r08 distance
    assert negated_in_clause(R08, match.start())
    claim = "Data 2020 tidak lengkap. Semua sudut saling mendukung hipotesis."
    assert not negated_in_clause(claim, re.search(AGREEMENT_WORDING, claim, re.IGNORECASE).start())
    contrast = "Hasil ini tidak berlaku untuk 2020, tetapi semua angle saling mendukung."
    assert not negated_in_clause(contrast, re.search(AGREEMENT_WORDING, contrast, re.IGNORECASE).start())
    assert re.search(NEGATION_PATTERN, "bukan", re.IGNORECASE)


def test_the_r08_sentence_passes_the_findings_gate() -> None:
    answer = findings_answer(text="Dari tiga sudut, hanya a_fall mendukung hipotesis: return 1.25 persen lebih tinggi "
                                  "(sampel efektif 120). " + R08)
    result, scripted, _, _ = approved_run([*RUN_SCRIPT, final_response(answer)])
    assert result.response.response_type == "ANSWER"
    assert result.execution.validation_gate in ("PASSED", "ANNOTATED")


def test_a_forced_findings_limitation_keeps_the_backend_statuses() -> None:
    wrong = findings_answer({"a_fall": "SUPPORTED", "a_rank": "SUPPORTED", "a_lag": "NOT_RUN"})
    result, _, _, _ = approved_run([*RUN_SCRIPT, final_response(wrong), final_response(wrong), final_response(wrong)])
    response = result.response
    assert response.response_type == "LIMITATION" and result.execution.validation_gate == "FORCED_LIMITATION"
    assert [(f.angle_id, f.status) for f in response.research_findings] == [
        ("a_fall", "SUPPORTED"), ("a_lag", "NOT_RUN"), ("a_rank", "INSUFFICIENT_EVIDENCE")]
    rank = response.research_findings[2].interpretation
    assert "CI_INCLUDES_ZERO" in rank.answer and "effective sample 120" in rank.evidence
    assert "not confirmed" in rank.usefulness
    dumped = result.model_dump(mode="json")
    assert dumped["response"]["research_findings"][1]["status"] == "NOT_RUN"


def test_a_model_limitation_never_carries_its_own_findings() -> None:
    limitation = {**findings_answer(), "response_type": "LIMITATION", "answer": "Tidak bisa disimpulkan.",
                  "limitations": ["Interpretasi belum lengkap."]}
    result, _, _, _ = approved_run([*RUN_SCRIPT, final_response(limitation)])
    assert result.response.response_type == "LIMITATION" and result.response.research_findings is None


# ---------------------------------------------------------------- C07: the research library

def library_rows(**changes: Any) -> list[dict[str, Any]]:
    rows = [{**row, "library_sha256": L.LIBRARY_SHA256} for row in copy.deepcopy(L.rows())]
    for key, value in changes.items():
        rows[0][key] = value
    return rows


def test_the_library_must_equal_this_service_and_the_table() -> None:
    assert library_problem(library_rows()) is None
    assert "no active rows" in library_problem([])
    assert "another library_sha256" in library_problem(library_rows(library_sha256="0" * 64))
    assert "content differs" in library_problem(library_rows(interpretation="edited by hand"))
    assert "content differs" in library_problem(library_rows()[:-1])
    assert set(LIBRARY_COLUMNS) == set(L.rows()[0])


class FakeCatalog:
    def __init__(self, rows: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        self.rows, self.fail, self.statements = rows, fail, []

    def read_only(self):
        from contextlib import contextmanager

        @contextmanager
        def session():
            if self.fail:
                raise ToolError("The catalog database is currently unavailable.")

            def run(statement: Any, params: tuple[Any, ...]) -> list[dict[str, Any]]:
                self.statements.append((statement, params))
                return copy.deepcopy(self.rows or [])
            yield run
        return session()


def test_startup_enables_multi_angle_only_with_the_same_library() -> None:
    settings = {"max_groups": 3, "min_angles": 2, "max_angles": 6}
    ok, reason = _with_research_library(settings, FakeCatalog(library_rows()))
    assert reason is None and len(ok["library"]) == 8
    assert _with_research_library(settings, None)[1].startswith("no catalog database")
    assert "could not be read" in _with_research_library(settings, FakeCatalog(fail=True))[1]
    assert _with_research_library(settings, FakeCatalog([]))[0] is None
    edited = library_rows(misuse_warning="changed")
    assert "content differs" in _with_research_library(settings, FakeCatalog(edited))[1]


def test_get_research_library_serves_the_table_rows() -> None:
    spec = research_library_spec(library_rows())
    everything = spec.handler(ResearchLibraryArgs(method_ids=None))
    assert everything["library_sha256"] == L.LIBRARY_SHA256 and everything["method_count"] == 8
    assert everything["common_requirements"] == L.COMMON_REQUIREMENTS
    assert "library_sha256" not in everything["methods"][0] and "input_roles" in everything["methods"][0]
    one = spec.handler(ResearchLibraryArgs(method_ids=["lead_lag"]))
    assert [m["method_id"] for m in one["methods"]] == ["lead_lag"]
    assert len(json.dumps(everything)) < 40000  # fits a tool result


def test_the_prompt_names_no_method_and_the_plan_turn_offers_the_library() -> None:
    from app.orchestrator import DISCOVERY_TOOLS, MULTI_ANGLE_PLAN_RULES

    for method in L.by_method():
        assert method not in MULTI_ANGLE_PLAN_RULES
    assert "get_research_library" in DISCOVERY_TOOLS


def test_the_catalog_research_section_is_labelled_reference_only_while_the_library_is_served() -> None:
    class Reader:
        def read_only(self):
            from contextlib import contextmanager

            @contextmanager
            def session():
                yield lambda statement, params: [{"method_id": "m1", "method_name": "M", "category": "c",
                                                  "purpose": "p", "implementation_status": "REFERENCE_ONLY",
                                                  "total_matching": 1}]
            return session()

    from app.tools.catalog import CatalogDetailsArguments

    arguments = CatalogDetailsArguments.model_validate({"table_names": [], "sections": ["RESEARCH"],
                                                        "method_ids": None, "column_names": None,
                                                        "entity_ids": None})
    served = CatalogTools(Reader(), research_library=True).details(arguments)
    plain = CatalogTools(Reader()).details(arguments)
    assert RESEARCH_REFERENCE_ONLY in json.dumps(served) and RESEARCH_REFERENCE_ONLY not in json.dumps(plain)


def test_the_orchestrator_copy_of_the_library_is_identical_and_matches_the_migration() -> None:
    sandbox = HERE.parent / "market-python-sandbox" / "app" / "research_library.py"
    if sandbox.exists():
        assert sandbox.read_bytes() == (HERE / "app" / "research_library.py").read_bytes()
    migration = HERE.parents[1] / "database" / "migrations" / "20260930_001_create_ai_research_library.sql"
    if migration.exists():
        text = migration.read_text(encoding="utf-8")
        body = re.search(r"\$library\$(\[.*\])\$library\$", text, re.S)
        assert body and json.loads(body.group(1)) == L.rows()
        assert set(re.findall(r"'([0-9a-f]{64})'", text)) == {L.LIBRARY_SHA256}
