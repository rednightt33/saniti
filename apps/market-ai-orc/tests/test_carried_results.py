"""Step 5b (user decisions 2026-10-02): results carried from G to G, labels shown with every result, findings with
their figures, and the IN_SAMPLE flag.

- 2d: a research plan names the released tables of the conversation it builds on (carried_inputs, by ref); the
  approval resolves them to output ids and the research sessions are opened with exactly those (the sandbox loads
  nothing else for a RESEARCH need). Plans that name none keep their JSON and hash.
- P5: every released table shown to the model carries its label (CALCULATION_VERIFIED or the completion's evidence
  label), in the tool result and in the data record.
- P3: a finding in the record note shows its key figures, not only its status.
- IN_SAMPLE: a research finding tested on data an earlier step read (overlapping table and dates, or an earlier
  result loaded as test data) is flagged and the answer says so; nothing is refused.
"""
from __future__ import annotations

from app import user_texts as texts
import copy
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app import data_record as records
from app import in_sample as insample
from app.orchestrator import CARRIED_INPUTS_INSTRUCTION, AgentOrchestrator
from app.research_plan import ResearchPlanFindings, canonical_json, plan_sha256
from app.research_plan_v2 import ResearchPlanV2
from app.schemas import AgentRunRequest, ContinuationIn
from app.tools.analysis import SandboxClient
from app.tools.session import session_specs
from conftest import ScriptedClient, final_response, make_settings
from test_hypothesis_plan import DRAFT, dual_registry, v1_response
from test_multi_angle import (MA, QUESTION, RUN_SCRIPT, RunSandbox, call, continuation, data_plan, findings_answer,
                              ma_registry, plan_v2, signer)
from test_research_findings import findings_plan
from test_research_plan import Clock, continuation as continuation_v1, signer as signer_v1

EARLIER = "out_" + "a" * 24
BUNDLE = "bundle_" + "1" * 24
CARRIED = [{"output_ref": "out.o1", "purpose": "The drop days the analysis found, as the events to test."}]


def record_with_output(label: str = "DATA_COVERAGE_VERIFIED") -> dict[str, Any]:
    record = records.empty()
    records.add_output(record, "q-1", alias="o1", output_id=EARLIER, session_id="sess_" + "1" * 24, name="drops",
                       columns=["ticker", "date", "ret"], row_count=42, label=label)
    return record


def record_with_analysis(start: str = "2025-01-01", end: str = "2025-12-31") -> dict[str, Any]:
    record = record_with_output()
    records.add_need(record, "q-1", {"status": "APPROVED", "need_id": "need_" + "e" * 24, "approved": {
        "spec_sha256": "s" * 64, "catalog_sha256": "c" * 64,
        "requests": [{"data_request_id": "prices", "logical_name": "prices",
                      "source_table": "Price_Stock_Indonesia_IDX", "extract_columns": ["ticker", "date", "close"],
                      "ranges": [{"range_id": "study", "start": start, "end": end}], "scope_sha256": "d" * 64}]}},
        "ANALYSIS")
    return record


# ---------------------------------------------------------------- the plan field

@pytest.mark.parametrize("model,body", [(ResearchPlanFindings, findings_plan), (ResearchPlanV2, plan_v2)])
def test_a_plan_without_carried_inputs_keeps_its_json_and_hash(model, body) -> None:
    absent = model.model_validate(body()).model_dump(mode="json")
    null = model.model_validate({**body(), "carried_inputs": None}).model_dump(mode="json")
    empty = model.model_validate({**body(), "carried_inputs": []}).model_dump(mode="json")
    assert "carried_inputs" not in absent and absent == null == empty
    assert canonical_json(absent) == canonical_json(model.model_validate(absent).model_dump(mode="json"))
    named = model.model_validate({**body(), "carried_inputs": CARRIED}).model_dump(mode="json")
    assert named["carried_inputs"] == CARRIED and canonical_json(named) != canonical_json(absent)


def test_a_plan_without_carried_inputs_is_signed_as_before() -> None:
    before = plan_sha256(ResearchPlanFindings.model_validate(findings_plan()))
    assert before == plan_sha256(ResearchPlanFindings.model_validate({**findings_plan(), "carried_inputs": None}))
    # a token issued before 2d verifies against the same plan read back
    issued = signer_v1().issue(ResearchPlanFindings.model_validate(findings_plan()), "run_001", "conv_1")
    signer_v1().verify(ContinuationIn.model_validate(continuation_v1(issued, the_plan=findings_plan())), "conv_1")


@pytest.mark.parametrize("ref", ["out.out_" + "a" * 24, "o1", "out.o", "finding.a_fall", "out.o12345"])
def test_a_carried_input_is_named_by_its_ref_only(ref) -> None:
    with pytest.raises(ValidationError):
        ResearchPlanV2.model_validate({**plan_v2(), "carried_inputs": [{"output_ref": ref, "purpose": "x"}]})


# ---------------------------------------------------------------- the gate and the approval

def hypothesis_agent(script: list, sandbox: RunSandbox | None = None):
    submitted: list[dict[str, Any]] = []
    registry = dual_registry(submitted)
    sandbox = sandbox or RunSandbox()
    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(sandbox.handler))
    for spec in session_specs(client, timeout_seconds=10, execution_timeout_seconds=10, max_result_bytes=40000):
        if spec.name not in registry._tools:
            registry.register(spec)
    settings = make_settings(**MA, AI_ENABLE_HYPOTHESIS_PLAN="true")
    runner = AgentOrchestrator(settings, ScriptedClient(script), registry, wall_clock=Clock(),
                               draft_reader=lambda draft_id: None)
    return runner, runner.client, sandbox


def test_a_plan_naming_a_table_the_conversation_did_not_release_is_sent_back() -> None:
    unknown = copy.deepcopy(v1_response())
    unknown["research_plan"]["carried_inputs"] = [{"output_ref": "out.o9", "purpose": "x"}]
    known = copy.deepcopy(v1_response())
    known["research_plan"]["carried_inputs"] = CARRIED
    runner, scripted, _ = hypothesis_agent([
        call("check_data_feasibility", {"data_need_spec": {"mode": "RESEARCH"}}, "c1"),
        final_response(unknown), final_response(known)])
    result = runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION),
                        data_record=record_with_output())
    sent_back = str(scripted.payloads[2]["input"][-1])
    assert "out.o9" in sent_back and "out.o1" in sent_back
    assert CARRIED_INPUTS_INSTRUCTION.split(":")[0] in sent_back
    assert result.response.response_type == "RESEARCH_PLAN_CONFIRMATION"
    assert result.continuation is not None
    # the user approves what the research loads
    assert result.response.research_plan.model_dump(mode="json")["carried_inputs"] == CARRIED


def opened_bodies(sandbox: RunSandbox) -> list[dict[str, Any]]:
    return [body for method, path, body in sandbox.calls if method == "POST" and path == "/v1/sessions"]


def test_an_approved_hypothesis_plan_opens_its_sessions_with_the_tables_it_names() -> None:
    plan = {**findings_plan(), "carried_inputs": CARRIED}
    issued = signer_v1().issue(ResearchPlanFindings.model_validate(plan), "run_001", "conv_1")
    runner, _, sandbox = hypothesis_agent([
        call("open_analysis_session", {"input_bundle_id": BUNDLE}, "c1"),
        final_response({"response_type": "LIMITATION", "answer": "Data belum lengkap.", "clarification_question":
                        None, "assumptions": [], "limitations": ["x"], "research_plan": None,
                        "research_findings": None})])
    runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                               continuation=continuation_v1(issued, the_plan=copy.deepcopy(plan), action="APPROVE")),
               data_record=record_with_output())
    assert [b.get("carried_outputs") for b in opened_bodies(sandbox)] == [[EARLIER]]


def test_a_run_without_an_approved_plan_leaves_the_rule_to_the_sandbox() -> None:
    runner, _, sandbox = hypothesis_agent([
        call("open_analysis_session", {"input_bundle_id": BUNDLE}, "c1"),
        final_response({"response_type": "LIMITATION", "answer": "Belum.", "clarification_question": None,
                        "assumptions": [], "limitations": ["x"], "research_plan": None, "research_findings": None})])
    runner.run(AgentRunRequest(request_id="run_001", conversation_id="conv_1", message=QUESTION),
               data_record=record_with_output())
    assert [("carried_outputs" in b) for b in opened_bodies(sandbox)] == [False]


def test_an_approved_plan_naming_no_table_opens_its_sessions_with_none() -> None:
    plan = findings_plan()
    issued = signer_v1().issue(ResearchPlanFindings.model_validate(plan), "run_001", "conv_1")
    runner, _, sandbox = hypothesis_agent([
        call("open_analysis_session", {"input_bundle_id": BUNDLE}, "c1"),
        final_response({"response_type": "LIMITATION", "answer": "Belum.", "clarification_question": None,
                        "assumptions": [], "limitations": ["x"], "research_plan": None, "research_findings": None})])
    runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                               continuation=continuation_v1(issued, the_plan=copy.deepcopy(plan), action="APPROVE")),
               data_record=record_with_output())
    assert [b.get("carried_outputs") for b in opened_bodies(sandbox)] == [[]]  # fail closed: nothing carried


class CarriedRunSandbox(RunSandbox):
    """A research run whose session loaded an earlier result (the completion's carried_inputs)."""

    def __init__(self, used: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.used = used or []

    def handler(self, request: httpx.Request) -> httpx.Response:
        response = super().handler(request)
        if request.url.path.endswith("/complete") and self.used:
            body = json.loads(response.content)
            body["final_status"]["carried_inputs"] = self.used
            return httpx.Response(200, json=body)
        return response


def approved_v2(record: dict[str, Any], sandbox: RunSandbox, carried: list[dict[str, Any]] | None = None,
                **settings: str):
    plan = {**plan_v2(), **({"carried_inputs": carried} if carried else {})}
    issued = signer().issue(ResearchPlanV2.model_validate(plan), data_plan(), "run_001", "conv_1")
    # with value references on, the typed figures of findings_answer are asked for once (EXEC-E TYPED_FIGURES); the
    # answer is then sent again unchanged and delivered with the backend's note
    scripted = ScriptedClient([*RUN_SCRIPT, final_response(findings_answer()), final_response(findings_answer())])
    runner = AgentOrchestrator(make_settings(**MA, **settings), scripted, ma_registry(sandbox), wall_clock=Clock(),
                               draft_reader=lambda draft_id: None)
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                                        continuation=continuation(issued, the_plan=copy.deepcopy(plan),
                                                                  action="APPROVE")),
                        data_record=record)
    return result


def test_an_approved_multi_angle_plan_opens_its_sessions_with_the_tables_it_names() -> None:
    sandbox = RunSandbox()
    result = approved_v2(record_with_output(), sandbox, CARRIED)
    assert result.status == "COMPLETED", result.response
    assert [b.get("carried_outputs") for b in opened_bodies(sandbox)] == [[EARLIER]]


# ---------------------------------------------------------------- IN_SAMPLE

def test_a_research_test_over_a_period_an_earlier_analysis_read_is_flagged() -> None:
    sandbox = RunSandbox()
    result = approved_v2(record_with_analysis(), sandbox)
    line = next(x for x in result.response.limitations if x.startswith(texts.IN_SAMPLE_LINE[:40]))
    # a_fall and a_rank read the prices 2021-2026, which the analysis read for 2025; a_lag reads index prices. M125: the
    # user reads the periods; the angles and the table stay in the data record and the log
    assert "periode uji 2021-01-04 s/d 2026-09-25 bertumpuk dengan 2025-01-01 s/d 2025-12-31" in line
    assert "Price_Stock_Indonesia_IDX" not in line and "a_fall" not in line
    findings = {f["id"]: f["finding"] for f in result.data_record["findings"]}
    assert findings["a_fall"]["in_sample"][0]["analysis_request_id"] == "q-1"
    assert "in_sample" not in findings["a_lag"]
    assert result.response.response_type == "ANSWER"  # flagged, not refused


def test_a_research_test_on_another_period_is_not_flagged() -> None:
    result = approved_v2(record_with_analysis("2019-01-01", "2020-12-31"), RunSandbox())
    assert not any(x.startswith(texts.IN_SAMPLE_LINE[:40]) for x in result.response.limitations)
    assert not any("in_sample" in f["finding"] for f in result.data_record["findings"])


def test_a_research_test_that_loaded_an_earlier_result_is_flagged() -> None:
    used = [{"output_id": EARLIER, "name": "drops", "kind": "G1", "label": "DATA_COVERAGE_VERIFIED"}]
    result = approved_v2(record_with_output(), CarriedRunSandbox(used), CARRIED)
    line = next(x for x in result.response.limitations if x.startswith(texts.IN_SAMPLE_LINE[:40]))
    assert texts.IN_SAMPLE_CARRIED in line and "out.o1" not in line
    findings = {f["id"]: f["finding"] for f in result.data_record["findings"]}
    assert all("in_sample" in findings[a] for a in ("a_fall", "a_lag", "a_rank"))  # one bundle group holds the three


def test_the_overlap_is_derived_per_table_and_date() -> None:
    seen = [{"table": "T", "start": "2025-01-01", "end": "2025-06-30", "request_id": "q-1"}]
    assert insample.overlaps(seen, [{"table": "T", "start": "2025-06-30", "end": "2025-12-31"}])  # one shared day
    assert not insample.overlaps(seen, [{"table": "T", "start": "2025-07-01", "end": "2025-12-31"}])
    assert not insample.overlaps(seen, [{"table": "U", "start": "2025-01-01", "end": "2025-06-30"}])
    assert not insample.overlaps(seen, [{"table": "T", "start": None, "end": None}])  # no dates: nothing claimed
    many = {str(i): [{"table": f"T{i}", "carried_output": f"out.o{i}"}] for i in range(5)}
    assert insample.details(many).endswith("; 2 more")


def test_this_requests_own_analysis_and_earlier_research_are_not_the_reference() -> None:
    record = record_with_analysis()
    record["needs"][0]["request_id"] = "q-now"
    assert insample.analysis_ranges(record, "q-now") == []
    record["needs"][0]["request_id"], record["needs"][0]["mode"] = "q-1", "RESEARCH"
    assert insample.analysis_ranges(record, "q-now") == []


# ---------------------------------------------------------------- P3 and P5 in the record

def test_a_finding_in_the_note_shows_its_figures_and_flags() -> None:
    record = records.empty()
    records.add_finding(record, "q-2", kind="HYPOTHESIS", finding_id="gap_down", recorded_at="2026-10-02T10:00:00",
                        finding={"method_id": "event_summary", "status": "COMPLETE", "verdict": "SUPPORTED",
                                 "validation_level": "STATISTICS_VERIFIED",
                                 "estimates": {"primary": {"estimate": 0.0125, "ci": [0.004, 0.021],
                                                           "p_adjusted": 0.003}},
                                 "sample": {"effective": 118}, "in_sample": [{"table": "T"}]})
    line = records.finding_line(record["findings"][0])
    assert line.startswith("- finding.gap_down (HYPOTHESIS, q-2, 2026-10-02T10:00:00): method_id=event_summary")
    for part in ("verdict=SUPPORTED", "estimate=0.0125", "ci=[0.004, 0.021]", "p=0.003", "effective_sample=118",
                 "IN_SAMPLE"):
        assert part in line
    assert line in records.note(record)


def test_an_angle_finding_shows_its_difference() -> None:
    entry = {"id": "a_fall", "kind": "ANGLE", "request_id": "q-3", "finding": {
        "status": "SUPPORTED", "angle_a": {"difference": 1.25, "ci_low": 0.4, "ci_high": 2.1, "p_value": 0.01}}}
    assert "difference=1.25; ci=[0.4, 2.1]; unadjusted p=0.01" in records.finding_line(entry)


def test_an_interval_and_a_p_value_stay_in_the_pair_they_belong_to() -> None:
    """M65 (golden test rerun ma-golden-20261002b, turn 9): the note printed the unadjusted CI beside the adjusted p and
    the answer paired them ("selang −0,27 pp sampai 0,76 pp, p = 0,856"). A multi-threshold angle shows both pairs,
    labelled, and the estimate's unit."""
    entry = {"id": "broad_selling_side", "kind": "ANGLE", "request_id": "q-5", "finding": {
        "status": "INSUFFICIENT_EVIDENCE", "estimates": {
            "kind": "MEAN_DIFFERENCE", "units": {"estimate": "PERCENT"},
            "primary": {"estimate": 0.24, "ci": [-0.27, 0.76], "p_value": 0.354, "ci_adjusted": [-0.39, 0.87],
                        "p_adjusted": 0.856}}}}
    line = records.finding_line(entry)
    assert "estimate=0.24 (PERCENT)" in line
    assert "adjusted for multiple testing: ci=[-0.39, 0.87], p=0.856" in line
    assert "unadjusted: ci=[-0.27, 0.76], p=0.354" in line
    assert "ci=[-0.27, 0.76], p=0.856" not in line
    single = {"id": "one", "kind": "ANGLE", "finding": {"estimates": {"primary": {
        "estimate": 0.1, "ci": [0.02, 0.18], "p_value": 0.01, "p_adjusted": None, "ci_adjusted": None}}}}
    assert "ci=[0.02, 0.18], p=0.01" in records.finding_line(single) and "adjusted" not in records.finding_line(single)


def test_every_released_output_in_the_note_shows_its_label() -> None:
    record = record_with_output("CALCULATION_VERIFIED")
    records.add_output(record, "q-1", alias="o2", output_id="out_" + "b" * 24, session_id=None, name="other",
                       columns=["x"], row_count=1)
    note = records.note(record)
    assert "out.o1 = " + EARLIER in note and "label CALCULATION_VERIFIED" in note
    assert record["outputs"][1].get("label") is None  # an older record without labels still reads


# ---------------------------------------------------------------- A: every released output is listed

def test_every_released_output_gets_its_ref_also_beyond_the_preview_and_charts() -> None:
    """A (user decision 2026-10-02): the preview shows the first ten tables, JSON and text and never a chart; before,
    only previewed outputs got a ref and a data-record entry, so the eleventh table and every chart were lost to the
    answer and to later turns."""
    from app.orchestrator import CONTENTS_NOT_SHOWN_NOTE, RunState
    from app.tools import ToolOutcome
    from app.value_refs import render
    from test_value_references import tracker

    session = "sess_" + "1" * 24
    ids = [f"out_{i:024d}" for i in range(13)]
    released = [{"output_id": ids[i], "name": f"t{i}", "type": "TABLE", "row_count": 3,
                 "columns": [{"name": "ticker", "type": "VARCHAR"}, {"name": "ret", "type": "DOUBLE"}]}
                for i in range(12)] + [{"output_id": ids[12], "name": "trend", "type": "CHART"}]
    contents = [{"output_id": ids[i], "name": f"t{i}", "type": "TABLE", "row_count": 3,
                 "rows": [{"ticker": "BBCA", "ret": 0.01 * i}], "truncated": True} for i in range(10)]
    reads: list[tuple] = []

    def reader(session_id, output_id, request_id, offset, limit):
        reads.append((session_id, output_id, offset))
        return {"released": True, "row_count": 3, "rows": [{"ticker": "BBRI", "ret": 0.0567}]}

    state = RunState(request_id="r", started=0.0, input_items=[])
    completion = {"result": {"status": "COMPLETED", "session_id": session, "final_status": {},
                             "released_outputs": released, "released_contents": contents}}
    tracker(reader)._track_references(state, "complete_analysis", ToolOutcome(
        call_id="c", name="complete_analysis", ok=True, output=completion))
    result = completion["result"]
    assert [o.get("ref") for o in result["released_outputs"][10:]] == ["out.o11", "out.o12", "out.o13"]
    assert all(o["content_shown"] is False for o in result["released_outputs"][10:])
    assert not any("content_shown" in c for c in contents)  # the previewed ones are shown
    assert result["contents_not_shown_note"] == CONTENTS_NOT_SHOWN_NOTE
    recorded = {o["ref"]: o for o in state.data_record["outputs"]}
    assert len(recorded) == 13 and recorded["out.o11"]["columns"] == ["ticker", "ret"]
    assert recorded["out.o13"]["type"] == "CHART" and 'CHART (None rows' in records.note(state.data_record)
    # a row of a table whose content was not shown is read on demand, from its own session
    out = render("BBRI {{out.o11.rows[ticker=BBRI].ret|pct:2}}", state.ref_sources)
    assert out.text == "BBRI 5,67%" and out.problems == [] and reads[0][:2] == (session, ids[10])


def test_a_research_run_lists_its_released_outputs_with_refs() -> None:
    sandbox = RunSandbox()
    original = sandbox.handler

    def handler(request: httpx.Request) -> httpx.Response:
        response = original(request)
        if request.url.path.endswith("/complete"):
            body = json.loads(response.content)
            session = request.url.path.split("/")[3]
            body["released_outputs"] = [{"output_id": "out_" + session[-24:], "name": f"in_{session[-2:]}",
                                         "type": "TABLE", "row_count": 5}]
            return httpx.Response(200, json=body)
        return response

    sandbox.handler = handler
    result = approved_v2(records.empty(), sandbox, AI_ENABLE_VALUE_REFERENCES="true")
    assert result.status == "COMPLETED", result.response
    assert [(o["ref"], o["name"]) for o in result.data_record["outputs"]] == [("out.o1", "in_01")]
