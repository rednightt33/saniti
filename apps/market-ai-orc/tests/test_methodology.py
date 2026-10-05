"""The methodology note (AI_ENABLE_METHODOLOGY): a model-written account of how a DataNeed answer was reached, required
when the answer rests on a completed analysis, and checked for number provenance against the answer's sources plus
the parameters of the code that ran. A bad note never forces a LIMITATION on a sound answer."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.orchestrator import METHODOLOGY_RULES, AgentOrchestrator, build_system_prompt, response_contract
from app.schemas import AgentRunRequest, FinalResponse, final_response_schema
from app.tools import ToolSpec
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import SESSION, Tools, answer, call, completed, flow

import pytest

ON = {"AI_ENABLE_DATANEED": "true", "AI_ENABLE_METHODOLOGY": "true"}
CODE = "df = saniti.load('prices')\nwindow = 37\nr = df.close.pct_change(window)\n"


class CodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    code: str


class CodeTools(Tools):
    """run_python takes the code, so its parameters can be read by the methodology check."""

    def __init__(self, completions: list[dict[str, Any]], status: str = "OK") -> None:
        super().__init__(completions)
        self.status = status

    def registry(self):
        registry = super().registry()
        registry._tools["run_python"] = ToolSpec(
            name="run_python", description="run_python", arguments_model=CodeArgs,
            handler=lambda a: {"execution_id": "exe_1", "session_id": SESSION, "status": self.status, "outputs": []})
        return registry


def steps(code: str = CODE) -> list:
    base = flow(run=False, complete=False)
    return base + [call("run_python", {"session_id": SESSION, "code": code}, "c4"),
                   call("complete_analysis", {"session_id": SESSION}, "c5")]


def noted(text: str, methodology: str | None, kind: str = "ANSWER") -> dict[str, Any]:
    return {**answer(text, kind), "methodology": methodology}


def run(script: list, tools: Tools | None = None, **settings: str):
    scripted = ScriptedClient(script)
    agent = AgentOrchestrator(make_settings(**{**ON, **settings}), scripted,
                              (tools or CodeTools([completed()])).registry())
    return agent.run(AgentRunRequest(request_id="m1", message="Berapa return YTD BBCA dan BBRI?")), scripted, agent


GOOD = ("Data harga harian BBCA dan BBRI dari bundle yang disetujui. Return dihitung dengan jendela 37 hari "
        "perdagangan; BBCA tercatat 12,35%.")


def test_the_note_is_part_of_the_contract_only_when_on() -> None:
    assert final_response_schema(False)["required"] == ["response_type", "answer", "clarification_question",
                                                        "assumptions", "limitations"]
    assert "methodology" in final_response_schema(False, methodology=True)["required"]
    assert "methodology:" in response_contract(False, True) and "methodology" not in response_contract(False)
    assert build_system_prompt(False, True, methodology=True).endswith(markdown_prompt(METHODOLOGY_RULES))
    assert markdown_prompt(METHODOLOGY_RULES) not in build_system_prompt(False, True)
    # the rules add no source numbers to the system prompt (list markers are skipped)
    import re
    assert not any(ch.isdigit() for ch in re.sub(r"(?m)^\d+\. ", "", METHODOLOGY_RULES))
    _, _, agent = run([final_response(noted("x", None, "LIMITATION"))])
    assert agent.methodology and agent.final_schema["properties"]["methodology"]
    off = AgentOrchestrator(make_settings(AI_ENABLE_METHODOLOGY="true"), ScriptedClient([]), Tools([]).registry())
    assert off.methodology is False  # needs the DataNeed flow


def test_a_sound_note_is_returned_with_its_own_provenance() -> None:
    result, _, _ = run(steps() + [final_response(noted("BBCA naik 12,35%.", GOOD))])
    assert result.response.response_type == "ANSWER"
    assert result.response.methodology == GOOD
    # 37 comes only from the code that ran: a source for the note, never for the answer
    assert result.execution.methodology_provenance.unsupported == []
    assert result.execution.number_provenance.unsupported == []


def test_code_parameters_are_not_sources_for_the_answer() -> None:
    result, _, _ = run(steps() + [final_response(noted("BBCA naik 12,35% dalam 37 hari.", GOOD)),
                                  final_response(noted("BBCA naik 12,35% dalam 37 hari.", GOOD))])
    assert result.response.response_type == "LIMITATION"
    assert "37" in result.execution.number_provenance.unsupported


def test_a_missing_note_is_asked_for_once_then_the_answer_stands_with_a_limitation() -> None:
    result, scripted, _ = run(steps() + [final_response(noted("BBCA naik 12,35%.", None)),
                                         final_response(noted("BBCA naik 12,35%.", "  "))])
    assert "methodology is empty" in str(scripted.payloads[-1]["input"][-1])
    assert result.response.response_type == "ANSWER" and result.response.methodology is None
    assert "No methodology note was provided for this response." in result.response.limitations


def test_a_note_with_an_unsourced_number_is_repaired_or_withheld() -> None:
    bad = GOOD + " Sampelnya 812 hari."
    repaired, _, _ = run(steps() + [final_response(noted("BBCA naik 12,35%.", bad)),
                                    final_response(noted("BBCA naik 12,35%.", GOOD))])
    assert repaired.response.methodology == GOOD
    withheld, _, _ = run(steps() + [final_response(noted("BBCA naik 12,35%.", bad)),
                                    final_response(noted("BBCA naik 12,35%.", bad))])
    assert withheld.response.response_type == "ANSWER" and withheld.response.methodology is None
    assert any("withheld" in line and "812" in line for line in withheld.response.limitations)


def test_code_that_failed_is_not_a_source() -> None:
    result, _, _ = run(steps() + [final_response(noted("x", GOOD, "LIMITATION")),
                                  final_response(noted("x", GOOD, "LIMITATION"))],
                       tools=CodeTools([completed()], status="SCRIPT_ERROR"))
    assert result.response.methodology is None
    assert any("withheld" in line for line in result.response.limitations)


def test_no_analysis_needs_no_note() -> None:
    result, _, _ = run([final_response(noted("Data belum tersedia.", None, "LIMITATION"))])
    assert result.response.methodology is None
    assert not any("methodology" in line for line in result.response.limitations)


def test_plans_and_clarifications_carry_no_note() -> None:
    with pytest.raises(ValueError, match="methodology to be null"):
        FinalResponse.model_validate({"response_type": "CLARIFICATION", "answer": "", "clarification_question": "?",
                                      "assumptions": [], "limitations": [], "methodology": "x"})
