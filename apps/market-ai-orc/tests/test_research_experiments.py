"""EXEC-V stage 3 (M110, user decision 2026-10-07: "1 data ... di sandbox yang sama"): with the sandbox capability
research_multi_experiment, a RESEARCH data need may carry research_experiments, the experiments of one approved
hypothesis plan that read the same data. Each experiment is matched against the approved plan (P-g), the sandbox gets
the list, and the prompt tells the model so; without the capability nothing changes."""
from __future__ import annotations

import copy
import json

import httpx

from app.orchestrator import (MULTI_EXPERIMENT_STEP, MULTI_EXPERIMENT_VARIANTS, VARIANT_NOTE, build_system_prompt,
                              markdown_prompt)
from app.research_plan import ResearchGuard, current_research_guard, parse_plan
from app.tools import ToolRegistry, build_default_registry
from app.tools.analysis import SandboxClient, current_run_context, run_context
from app.tools.data_need import data_need_specs
from app.tools.request_data import GovernorClient, current_request_id
from test_data_need_tool import ytd_arguments
from test_research_findings import EXPERIMENT, FINDINGS_VALUES, findings_plan
from test_research_plan import NEED, NOW, Sandbox

SECOND = {**EXPERIMENT, "experiment_id": "experiment_2", "hypothesis_id": "gap_down_ten",
          "outcome": "Forward return over ten trading days."}


def plan() -> dict:
    body = findings_plan()
    body["experiments"].append({**SECOND, **FINDINGS_VALUES, "outcome_horizon_periods": 10})
    return body


APPROVED = parse_plan(plan())


def governance(experiment: dict, **overrides) -> dict:
    body = {key: experiment[key] for key in ("hypothesis_id", "hypothesis", "objective", "condition", "outcome",
                                             "baseline", "candidate_count", "pairwise_comparisons",
                                             "multiple_testing_policy")}
    body.update(holdout=None, minimum_sample=None, followup_of=None, success_rule=None, **FINDINGS_VALUES)
    body.update(overrides)
    return body


def experiments(**second) -> list[dict]:
    return [governance(EXPERIMENT), governance(SECOND, outcome_horizon_periods=10, **second)]


def tool_call(sandbox: Sandbox, arguments: dict, multi: bool = True):
    registry = ToolRegistry()
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    for spec in data_need_specs(client, timeout_seconds=10, max_result_bytes=40000, research_findings=True,
                                multi_experiment=multi):
        registry.register(spec)
    guard = ResearchGuard(required=True, plan=APPROVED, plan_id="rp_1")
    tokens = (current_request_id.set("run_2"), current_research_guard.set(guard),
              current_run_context.set(run_context(NOW, "Asia/Jakarta", [], "q")))
    try:
        return registry.execute("c1", "submit_data_need_spec", json.dumps(arguments))
    finally:
        current_request_id.reset(tokens[0])
        current_research_guard.reset(tokens[1])
        current_run_context.reset(tokens[2])


def research(**overrides) -> dict:
    return ytd_arguments(mode="RESEARCH", **{"research_governance": None, **overrides})


def test_the_experiments_of_one_plan_on_the_same_data_reach_the_sandbox_in_one_need() -> None:
    sandbox = Sandbox()
    outcome = tool_call(sandbox, research(research_experiments=experiments()))
    assert outcome.output["result"]["need_id"] == NEED, outcome.output
    [sent] = sandbox.calls
    assert "research_governance" not in sent["body"]
    assert [e["hypothesis_id"] for e in sent["body"]["research_experiments"]] == ["gap_down", "gap_down_ten"]
    assert sent["body"]["research_experiments"][1]["outcome_horizon_periods"] == 10


def test_every_experiment_is_matched_against_the_approved_plan() -> None:
    sandbox = Sandbox()
    changed = tool_call(sandbox, research(research_experiments=experiments(outcome="Return over twenty days.")))
    error = changed.output["result"]["error"]
    assert error["code"] == "RESEARCH_PLAN_MISMATCH" and sandbox.calls == []
    assert error["issues"][0]["field_path"] == "research_experiments[1].outcome"
    outside = [governance(EXPERIMENT), governance({**SECOND, "hypothesis_id": "not_in_plan"})]
    refused = tool_call(sandbox, research(research_experiments=outside)).output["result"]
    assert refused["error"]["code"] == "RESEARCH_PLAN_REAPPROVAL_REQUIRED" and sandbox.calls == []
    both = tool_call(sandbox, research(research_governance=governance(EXPERIMENT),
                                       research_experiments=experiments())).output["result"]
    assert both["status"] == "REVISION_REQUIRED" and sandbox.calls == []


def test_one_experiment_per_need_is_unchanged_and_the_field_needs_the_capability() -> None:
    sandbox = Sandbox()
    single = tool_call(sandbox, research(research_governance=governance(EXPERIMENT)))
    assert single.output["result"]["need_id"] == NEED
    assert sandbox.calls[-1]["body"]["research_governance"]["hypothesis_id"] == "gap_down"
    assert "research_experiments" not in sandbox.calls[-1]["body"]
    without = tool_call(sandbox, research(research_experiments=experiments()), multi=False)
    assert without.ok is False or without.output["result"]["status"] == "REVISION_REQUIRED"
    assert len(sandbox.calls) == 1  # without the capability the list never reaches the sandbox

    t = httpx.MockTransport(lambda r: httpx.Response(404))

    def schema(multi: bool) -> dict:
        registry = build_default_registry(
            object(), cursor_secret=b"x" * 32, governor_client=GovernorClient("http://g", "k" * 40, 90, transport=t),
            sandbox_client=SandboxClient("http://s", "s" * 40, 45, 20, transport=t), dataneed_enabled=True,
            plan_feasibility=True, composite_keys=True, point_in_time=True, research_findings=True,
            research_multi_experiment=multi)
        return {d["name"]: d["parameters"] for d in registry.definitions()}["submit_data_need_spec"]

    assert "research_experiments" in schema(True)["properties"]
    assert "research_experiments" not in schema(False)["properties"]


def test_the_prompt_names_the_shared_data_need_only_with_the_capability() -> None:
    flags = dict(dataneed=True, plan_confirmation=True, plan_feasibility=True, research_findings=True,
                 multi_angle=True, hypothesis_plans=True)
    on, off = build_system_prompt(False, **flags, multi_experiment=True), build_system_prompt(False, **flags)
    flat = " ".join(on.split())
    assert " ".join(MULTI_EXPERIMENT_STEP.split()) in flat and "research_experiments" not in off
    assert markdown_prompt(on) == on and not any(ch.isdigit() for ch in MULTI_EXPERIMENT_STEP)
    # step three keeps its approval sentence, the shared need follows it
    assert flat.index("Any other change needs a revised plan and a new approval.") < flat.index(
        "Experiments of the plan that read the same data")
    assert "research_experiments" in MULTI_EXPERIMENT_VARIANTS and "{variants}" in VARIANT_NOTE
    assert copy.deepcopy(APPROVED).experiments[1].hypothesis_id == "gap_down_ten"
