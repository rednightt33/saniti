"""Rejection messages say what is wrong, why and what to do (user 2026-10-20: "Rejection message boleh ketika AI masih
gagal, tapi harus jelas what it should do"; B2 "Ok untk B1 dan B2"; the expiry finding "dimana penjelasan kenapa
bundle bisa expired?")."""
from __future__ import annotations

from types import SimpleNamespace

import httpx

from app.orchestrator import AgentOrchestrator
from app.tools.registry import error_outcome
from app.tools.session import EXPIRY_RECOVERY, _call

SESSION, OTHER = "sess_" + "1" * 24, "sess_" + "2" * 24


def state():
    return SimpleNamespace(sessions={SESSION: {"need_id": "need_1"}, OTHER: {"closed_by_model": True}},
                           data_record={"outputs": [{"ref": "out.o1", "output_id": "out_" + "3" * 24}],
                                        "needs": [{"need_id": "need_1", "bundle_id": "bundle_" + "4" * 24}]})


def refused(message: str):
    return error_outcome("c1", "get_session_output", "INVALID_ARGUMENTS", message)


def test_a_refused_id_names_the_valid_ids_and_where_to_copy_them_from() -> None:
    outcome = refused("Tool arguments failed validation: session_id: String should match pattern '^sess_' "
                      "(expected JSON string); output_id: String should match pattern '^out_'")
    AgentOrchestrator._name_valid_ids(state(), outcome)
    message = outcome.output["error"]["message"]
    assert message.startswith("Tool arguments failed validation: session_id")  # the registry's own reason first
    assert SESSION in message and OTHER not in message  # a closed session is not offered
    assert "out.o1 (out_" in message and "CONVERSATION RESOURCES" in message and "never compose" in message
    bundle = refused("Tool arguments failed validation: input_bundle_id: String should match pattern '^bundle_'")
    AgentOrchestrator._name_valid_ids(state(), bundle)
    assert "need_1 -> bundle_" in bundle.output["error"]["message"]


def test_other_refusals_are_left_as_they_are() -> None:
    other = error_outcome("c1", "run_python", "SCRIPT_ERROR", "NameError: x")
    plain = refused("Tool arguments failed validation: code: Field required")
    for outcome in (other, plain):
        before = dict(outcome.output["error"])
        AgentOrchestrator._name_valid_ids(state(), outcome)
        assert outcome.output["error"] == before


class Sandbox:
    def __init__(self, status: int, code: str) -> None:
        self.status, self.code = status, code

    def _call(self, method, path, **kwargs):
        return httpx.Response(self.status, json={"status": "REJECTED", "error": {
            "code": self.code, "message": "The bundle has expired; prepare it again."}})

    @staticmethod
    def _json(response):
        return response.json()


def test_an_expired_bundle_says_why_it_is_gone_and_how_to_get_it_back() -> None:
    result = _call(Sandbox(410, "BUNDLE_EXPIRED"), "POST", "/v1/sessions")
    assert result["code"] == "BUNDLE_EXPIRED" and result["next_action"] == "RESUBMIT_DATA_NEED"
    assert result["message"].startswith("The bundle has expired; prepare it again. The sandbox keeps the data")
    assert "about a day" in result["message"] and "submit_arguments" in result["message"]
    assert set(EXPIRY_RECOVERY) == {"BUNDLE_EXPIRED", "BUNDLE_NOT_FOUND", "OUTPUT_EXPIRED"}
    other = _call(Sandbox(409, "SESSION_BUSY"), "POST", "/v1/sessions")
    assert other["message"] == "The bundle has expired; prepare it again." and other["next_action"] == "REPORT_LIMITATION"


def test_a_final_reply_written_as_prose_is_told_so_first() -> None:
    """edge_b6559a4f: the first final reply was prose; the re-ask now opens with what was wrong."""
    from app.orchestrator import PROSE_REASK_INSTRUCTION
    from app.schemas import AgentRunRequest
    from conftest import ScriptedClient, final_response, make_settings
    from test_dataneed_orchestrator import answer, completed, flow
    from test_fastlane import Counting
    prose = {"id": "p", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": "Return YTD BBCA naik, BBRI turun."}]}], "usage": {"output_tokens": 9}}
    client = ScriptedClient([*flow(), prose, final_response(answer("Return YTD BBCA 12,35%."))])
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), client, Counting([completed()]).registry())
    result = agent.run(AgentRunRequest(request_id="pr", message="Return YTD BBCA?"))
    asked = [i["content"] for i in client.payloads[-1]["input"] if i.get("role") == "user"]
    assert result.status == "COMPLETED" and any(a.startswith(PROSE_REASK_INSTRUCTION) for a in asked)
