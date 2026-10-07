"""Conversation reuse on the orchestrator side (AI_ENABLE_CONVERSATION_REUSE; implementation plan 2026-09-27, S1/S2):
the conversation key travels as a header set by the application, the planner asks for an equal-contract bundle before
extracting, the resources note, released outputs of earlier messages as sources, and the fail-closed wiring."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

import json
import re
from typing import Any

import httpx
import pytest

from app.config import ConfigError
from app.conversations import reuse_key
from app.orchestrator import CONVERSATION_REUSE_RULES, AgentOrchestrator, build_system_prompt
from app.schemas import AgentRunRequest
from app.tools.analysis import SandboxClient, current_conversation_key
from app.tools.data_planner import ExecutionPlanner
from app.tools.request_data import current_request_id
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import OUTPUT, SESSION, Tools, answer, call

KEY = "ck_" + "c" * 32
ON = {"AI_ENABLE_DATANEED": "true", "AI_ENABLE_CONVERSATION_STORE": "true",
      "CONVERSATION_DATABASE_URL": "postgresql://u:p@db.test:5432/x", "AI_ENABLE_CONVERSATION_REUSE": "true"}


def test_the_key_is_set_by_the_application_and_scoped_to_the_owner() -> None:
    assert reuse_key("alice", "conv_" + "1" * 32) == reuse_key("alice", "conv_" + "1" * 32)
    assert reuse_key("alice", "conv_" + "1" * 32) != reuse_key("bob", "conv_" + "1" * 32)
    assert reuse_key("alice", "conv_" + "1" * 32).startswith("ck_") and len(reuse_key("a", "b")) == 35


def test_reuse_needs_the_conversation_store() -> None:
    with pytest.raises(ConfigError, match="AI_ENABLE_CONVERSATION_STORE"):
        make_settings(AI_ENABLE_CONVERSATION_REUSE="true")


def test_the_sandbox_client_sends_the_key_only_inside_a_reuse_run() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("X-Saniti-Conversation-Key"))
        return httpx.Response(200, json={"status": "NO_MATCH", "reason": "NO_EQUAL_CONTRACT"})

    client = SandboxClient("http://sandbox.test", "s" * 40, 10, 0, transport=httpx.MockTransport(handler))
    assert client.reuse_bundle("r1", "need_" + "1" * 24) is None
    token = current_conversation_key.set(KEY)
    try:
        assert client.reuse_bundle("r1", "need_" + "1" * 24) is None
    finally:
        current_conversation_key.reset(token)
    assert seen == [None, KEY]


class PlannerSandbox:
    def __init__(self, reused: dict[str, Any] | None) -> None:
        self.reused = reused
        self.calls: list[str] = []

    def get_need(self, need_id: str) -> dict[str, Any]:
        self.calls.append("get_need")
        return {"need_id": need_id, "request_id": "r1", "requests": {}}

    def reuse_bundle(self, request_id: str, need_id: str) -> dict[str, Any] | None:
        self.calls.append("reuse_bundle")
        return self.reused

    def build_bundle(self, request_id: str, need_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("build_bundle")
        return {"status": "READY", "input_bundle_id": "bundle_" + "9" * 24}


def plan(sandbox: PlannerSandbox, key: str | None) -> dict[str, Any]:
    tokens = (current_request_id.set("r1"), current_conversation_key.set(key))
    try:
        return ExecutionPlanner(sandbox, governor=None).prepare("need_" + "1" * 24)
    finally:
        current_request_id.reset(tokens[0])
        current_conversation_key.reset(tokens[1])


def test_the_planner_reuses_an_equal_contract_bundle_before_extracting() -> None:
    reused = {"status": "READY", "input_bundle_id": "bundle_" + "8" * 24, "reused": True,
              "reused_from": {"request_id": "r0"}}
    sandbox = PlannerSandbox(reused)
    result = plan(sandbox, KEY)
    assert result["reused"] is True and result["plan"] == {"reused": True, "extractions": 0}
    assert sandbox.calls == ["get_need", "reuse_bundle"]  # no Governor extraction, no bundle build
    miss = PlannerSandbox(None)
    assert plan(miss, KEY)["input_bundle_id"] == "bundle_" + "9" * 24
    assert miss.calls == ["get_need", "reuse_bundle", "build_bundle"]
    outside = PlannerSandbox(reused)
    plan(outside, None)
    assert "reuse_bundle" not in outside.calls  # without a conversation key reuse is never asked for



def test_a_bundle_reused_under_other_labels_reaches_the_model_with_the_new_labels() -> None:
    """EXEC-V stage 2 (M110): the sandbox recognises the same data by content; the planner passes its view on as is,
    the datasets under this need's labels and aliases naming the earlier ones."""
    reused = {"status": "READY", "input_bundle_id": "bundle_" + "8" * 24, "reused": True,
              "reused_from": {"request_id": "r1"}, "datasets": [{"data_request_id": "exp_b_A", "logical_name": "px"}],
              "aliases": [{"data_request_id": "exp_b_A", "logical_name": "px", "bundle_data_request_id": "exp_a_A",
                           "bundle_logical_name": "prices"}]}
    sandbox = PlannerSandbox(reused)
    result = plan(sandbox, KEY)
    assert result["datasets"] == reused["datasets"] and result["aliases"] == reused["aliases"]
    assert sandbox.calls == ["get_need", "reuse_bundle"]  # the same request's second need: no extraction
    from app.orchestrator import CONVERSATION_REUSE_RULES

    assert "recognised by content, whatever its labels" in " ".join(CONVERSATION_REUSE_RULES.split())

RESOURCES = {"conversation_reuse": True, "warm_sessions": 1,
             "released_outputs": [{"output_id": OUTPUT, "session_id": SESSION, "name": "ytd", "type": "TABLE",
                                   "columns": ["ticker", "ytd_return"], "row_count": 2, "completion_id": "cmp_1",
                                   "completed_at": "2026-09-27T09:00:00+00:00",
                                   "evidence_label": "DATA_COVERAGE_VERIFIED", "warnings": []}],
             "bundles": [{"bundle_id": "bundle_" + "2" * 24, "extracted_at": "2026-09-27T08:59:00+00:00",
                          "expires_at": "2026-09-28T08:59:00+00:00", "mode": "ANALYSIS",
                          "warm_session": {"session_id": SESSION}, "datasets": [],
                          "data_need_spec": {"request_group_id": "g", "question": "YTD bank"}}]}


class Released(Tools):
    """get_session_output answers a released output of an earlier message (READ_RELEASED)."""

    def registry(self):
        registry = super().registry()
        spec = registry._tools["get_session_output"]
        registry._tools["get_session_output"] = type(spec)(
            name=spec.name, description=spec.description, arguments_model=spec.arguments_model,
            handler=lambda a: {"output_id": a.output_id, "name": "ytd", "released": True,
                               "read_mode": "READ_RELEASED",
                               "origin": {"completion_id": "cmp_1", "request_id": "turn-1",
                                          "completed_at": "2026-09-27T09:00:00+00:00",
                                          "evidence_label": "DATA_COVERAGE_VERIFIED", "warnings": []},
                               "rows": [{"ticker": "BBCA", "ytd_return": 0.123456},
                                        {"ticker": "BBRI", "ytd_return": -0.04321}]})
        return registry


def reuse_run(script: list, resources: dict | None = RESOURCES, key: str | None = KEY,
              message: str = "Dari hasil tadi, return YTD mana yang positif?"):
    scripted = ScriptedClient(script)
    agent = AgentOrchestrator(make_settings(**ON), scripted, Released([]).registry(),
                              conversation_resources=lambda k: resources if k == KEY else None)
    history = [{"role": "user", "content": "Berapa return YTD BBCA dan BBRI?"},
               {"role": "assistant", "content": "BBCA naik, BBRI turun."}]
    result = agent.run(AgentRunRequest(request_id="turn-2", conversation_id="conv_" + "1" * 32, message=message,
                                       history=history, history_mode="SERVER"), conversation_key=key)
    return result, scripted, agent


def test_the_prompt_teaches_reuse_only_when_it_is_active() -> None:
    assert markdown_prompt(CONVERSATION_REUSE_RULES) not in build_system_prompt(False, True)
    assert build_system_prompt(False, True, conversation_reuse=True).endswith(markdown_prompt(CONVERSATION_REUSE_RULES))
    # the system prompt is a number source: no digits besides the list markers the provenance check skips
    assert not any(ch.isdigit() for ch in re.sub(r"(?m)^\d+\. ", "", CONVERSATION_REUSE_RULES))
    _, _, agent = reuse_run([final_response(answer("x", "LIMITATION"))])
    assert agent.conversation_reuse and agent.system_prompt.endswith(markdown_prompt(CONVERSATION_REUSE_RULES))
    off = AgentOrchestrator(make_settings(**ON), ScriptedClient([]), Tools([]).registry())
    assert off.conversation_reuse is False and markdown_prompt(CONVERSATION_REUSE_RULES) not in off.system_prompt


def test_a_redisplay_answers_from_a_released_output_of_an_earlier_message() -> None:
    script = [call("get_session_output", {"session_id": SESSION, "output_id": OUTPUT}, "c1"),
              final_response(answer("Yang positif hanya BBCA dengan return YTD 12,35%."))]
    result, scripted, _ = reuse_run(script)
    first = scripted.payloads[0]["input"]
    note = next(i["content"] for i in first if i.get("role") == "user"
                and str(i.get("content")).startswith("CONVERSATION RESOURCES"))
    assert OUTPUT in note and "data_need_spec" in note and first[-1]["content"].startswith("Dari hasil tadi")
    # no new analysis ran, yet the routing gate accepts it and provenance finds 12,35% in the released rows
    assert result.response.response_type == "ANSWER", result.response
    assert result.evidence_label == "DATA_COVERAGE_VERIFIED"
    assert any("computed in an earlier message (completion cmp_1" in line for line in result.response.limitations)
    assert result.execution.number_provenance.unsupported == []


def test_numbers_of_the_resources_note_are_not_sources() -> None:
    script = [final_response(answer("Tabel ytd punya 2 baris.")), final_response(answer("Tabel ytd punya 2 baris."))]
    result, _, _ = reuse_run(script, message="Berapa baris tabel ytd tadi?")
    assert result.response.response_type == "LIMITATION"  # row_count 2 appears only in the note


def test_without_a_key_or_resources_the_run_is_a_fresh_one() -> None:
    _, scripted, _ = reuse_run([final_response(answer("x", "LIMITATION"))], key=None)
    assert not any(str(i.get("content", "")).startswith("CONVERSATION RESOURCES")
                   for i in scripted.payloads[0]["input"])
    _, scripted, _ = reuse_run([final_response(answer("x", "LIMITATION"))], resources=None)
    assert not any(str(i.get("content", "")).startswith("CONVERSATION RESOURCES")
                   for i in scripted.payloads[0]["input"])


def test_the_note_is_bounded_and_drops_older_specs_first() -> None:
    from app.orchestrator import MAX_RESOURCES_NOTE_CHARS, conversation_resources_note

    big = {"released_outputs": [], "bundles": [
        {"bundle_id": f"bundle_{i}", "datasets": [], "data_need_spec": {"question": "x" * 6000}} for i in range(3)]}
    note = conversation_resources_note(big)
    assert len(note) <= MAX_RESOURCES_NOTE_CHARS and note.count("omitted for size") >= 1
    assert json.dumps({"question": "x" * 6000}, separators=(",", ":"))[:50] in note  # the newest spec is kept
