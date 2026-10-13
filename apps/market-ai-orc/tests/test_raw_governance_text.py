"""M149 (EXEC-MODELS quality check 2026-10-13, ma-quality-20261013a ab5/ab6 with xiaomi/mimo-v2.6-pro): the model wrote
research_governance as text ("null"); the tool registry decoded its own copy, but the data-need tracker read the raw
arguments and called .get on the text, so the whole run ended in INTERNAL_ERROR (AttributeError)."""
from __future__ import annotations

import pytest

from app.orchestrator import AgentOrchestrator, RunState
from app.tools import ToolOutcome


@pytest.mark.parametrize("governance", ["null", '{"hypothesis_id": "h1"}', 7, ["x"], None])
def test_a_research_governance_written_as_text_never_breaks_the_run(governance) -> None:
    state = RunState(request_id="r", started=0.0, input_items=[])
    outcome = ToolOutcome(call_id="c", name="submit_data_need_spec", ok=True,
                          output={"result": {"status": "ACCEPTED", "need_id": "need_1"}})
    AgentOrchestrator._track_dataneed(state, "submit_data_need_spec",
                                      {"mode": "ANALYSIS", "research_governance": governance}, outcome)
    assert state.needs["need_1"]["hypothesis_id"] is None


def test_a_research_governance_object_keeps_its_hypothesis() -> None:
    state = RunState(request_id="r", started=0.0, input_items=[])
    outcome = ToolOutcome(call_id="c", name="submit_data_need_spec", ok=True,
                          output={"result": {"status": "ACCEPTED", "need_id": "need_2"}})
    AgentOrchestrator._track_dataneed(state, "submit_data_need_spec",
                                      {"mode": "RESEARCH", "research_governance": {"hypothesis_id": "h1"}}, outcome)
    assert state.needs["need_2"]["hypothesis_id"] == "h1"
