from __future__ import annotations

import pytest

from app.config import Settings
from app.orchestrator import AnalysisOrchestrator, RunState


def test_extracts_structured_output_text() -> None:
    response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"answer":"ok"}'}]}]}
    assert AnalysisOrchestrator._output_text(response) == '{"answer":"ok"}'


def test_reported_single_call_context_ceiling_is_enforced() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    state = RunState("request", "question", {"META"}, [])
    response = {
        "id": "resp_test",
        "usage": {"input_tokens": orchestrator.settings.ai_max_context_tokens + 1, "output_tokens": 1},
    }
    with pytest.raises(RuntimeError, match="AI_MAX_CONTEXT_TOKENS"):
        orchestrator._add_usage(state, response)
