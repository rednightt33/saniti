"""EXEC-OUTPUT-REUSE (AI_OUTPUT_REUSE; user 2026-10-20: "menjawab pertanyaan tsb tidak perlu data request sebenarnya",
"Kalau sesi lama hilang ... orc membuka sesi itu otomatis", "ensure system prompt di scan ulang ... tidak ada bentrok.
Penolakan juga harus jelas"): open_analysis_session takes input_bundle_id null, a run_python on a session that is gone
opens the conversation's session and runs there, and the prompt says the same thing everywhere (AGENTS.md Gates and
evidence: the rule first, how to pass it, one right and one wrong example)."""
from __future__ import annotations

import httpx

from app.orchestrator import (CITING_LIFETIME, CITING_LIFETIME_OUTPUTS, CONVERSATION_REUSE_OUTPUT_RULES,
                              CONVERSATION_REUSE_RULES, build_system_prompt, conversation_resources_note)
from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.request_data import GovernorClient
from test_analysis_tools import SANDBOX_KEY
from test_session_tools import BUNDLE, SESSION, FakeSandbox, call

NEW = "sess_" + "e" * 24


def registry(fake: FakeSandbox, output_reuse: bool = True):
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    return build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                  session_timeout_seconds=200, output_reuse=output_reuse)


def test_the_open_takes_a_null_bundle_only_with_the_switch() -> None:
    fake = FakeSandbox({"/v1/sessions": (200, {"session_id": NEW, "outputs_only": True})})
    reg = registry(fake)
    assert "output_reuse" in reg.features
    assert call(reg, "open_analysis_session", {"input_bundle_id": None}).ok
    assert fake.calls[-1]["body"] == {"request_id": "run-session-1"}  # no bundle_id: the conversation's session
    assert call(reg, "open_analysis_session", {"input_bundle_id": BUNDLE}).ok
    assert fake.calls[-1]["body"] == {"request_id": "run-session-1", "bundle_id": BUNDLE}
    off = registry(FakeSandbox(), output_reuse=False)
    assert "output_reuse" not in off.features
    assert not call(off, "open_analysis_session", {"input_bundle_id": None}).ok  # a bundle stays required
    schema = next(d for d in reg.definitions() if d["name"] == "open_analysis_session")
    assert "null" in str(schema["parameters"]["properties"]["input_bundle_id"])
    assert "needs no data need" in schema["description"]


def gone(code: str = "SESSION_NOT_FOUND") -> FakeSandbox:
    return FakeSandbox({
        f"/v1/sessions/{SESSION}/execute": (404, {"status": "REJECTED", "error": {
            "code": code, "message": "This session belongs to another message or conversation, or it closed."}}),
        "/v1/sessions": (200, {"session_id": NEW, "outputs_only": True, "carried_output_ids": ["out_" + "c" * 24]}),
        f"/v1/sessions/{NEW}/execute": (200, {"execution_id": "exe_" + "1" * 24, "session_id": NEW,
                                              "status": "OK"})})


def test_a_gone_session_is_replaced_and_the_code_runs_in_the_new_one() -> None:
    fake = gone()
    outcome = call(registry(fake), "run_python", {"session_id": SESSION, "code": "t = load_output('x')"})
    result = outcome.output["result"]
    assert result["status"] == "OK" and result["session_id"] == NEW, result
    assert result["session_opened"]["outputs_only"] is True
    assert f"use {NEW} from now on" in result["note"] and "load_output" in result["note"]
    paths = [c["path"] for c in fake.calls]
    assert paths == [f"/v1/sessions/{SESSION}/execute", "/v1/sessions", f"/v1/sessions/{NEW}/execute"]
    assert fake.calls[1]["body"] == {"request_id": "run-session-1"}


def test_without_the_switch_the_refusal_comes_back_as_before() -> None:
    fake = gone("SESSION_CLOSED")
    result = call(registry(fake, output_reuse=False), "run_python",
                  {"session_id": SESSION, "code": "x = 1"}).output["result"]
    assert result["status"] == "REJECTED" and result["code"] == "SESSION_CLOSED" and len(fake.calls) == 1


def test_an_expired_bundle_names_the_step_without_a_data_need_first() -> None:
    fake = FakeSandbox({f"/v1/sessions/{SESSION}/execute": (410, {"status": "REJECTED", "error": {
        "code": "BUNDLE_EXPIRED", "message": "This bundle expired (bundles are kept about a day)."}})})
    result = call(registry(fake), "run_python", {"session_id": SESSION, "code": "x = 1"}).output["result"]
    assert result["next_action"] == "OPEN_ANALYSIS_SESSION"
    assert "input_bundle_id null" in result["message"] and "raw rows" in result["message"]


def prompt(output_reuse: bool, goal_answers: bool = True) -> str:
    return build_system_prompt(True, dataneed=True, conversation_reuse=True, research_sections=False,
                               goal_answers=goal_answers, output_reuse=output_reuse,
                               tools=frozenset({"open_analysis_session", "run_python", "submit_data_need_spec"}))


def test_the_prompt_states_one_rule_without_the_old_conflicting_ones() -> None:
    on, off = prompt(True), prompt(False)
    # the seven places of the 2026-10-20 scan: reuse items 2 and 3 replaced, item 4 kept as the boundary
    assert "For a new computation on the same data, submit the listed" not in on
    assert "automatically (restored_outputs)" not in on
    assert "needs no data need" in on and "input_bundle_id null" in on
    assert "Right: open_analysis_session with input_bundle_id null" in on
    assert "Wrong: sending the listed data_need_spec again" in on
    assert "Newer data, another period, other columns, entities or filters need" in on
    # CITING AND CHECKS C7: the rule the model reads before it writes
    assert "A session that is gone: open a new one." not in on and "Computing on them needs no data need" in on
    # off: byte for byte the earlier prompt
    assert "For a new computation on the same data, submit the listed" in off and "needs no data need" not in off
    assert CITING_LIFETIME in off and "Computing on them needs no data need" not in off


def test_the_rule_texts_carry_a_right_and_a_wrong_example() -> None:
    for text in (CONVERSATION_REUSE_OUTPUT_RULES, CITING_LIFETIME_OUTPUTS):
        assert "Right:" in text and "Wrong:" in text
    assert CONVERSATION_REUSE_RULES != CONVERSATION_REUSE_OUTPUT_RULES


def test_the_resources_note_puts_the_step_without_a_data_need_first() -> None:
    resources = {"bundles": [{"bundle_id": BUNDLE, "data_need_spec": {"x": 1}}]}
    assert "needs no data need" in conversation_resources_note(resources, True)
    assert "To reuse one without extraction" in conversation_resources_note(resources, False)
