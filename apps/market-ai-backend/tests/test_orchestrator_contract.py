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


def test_semantic_preflight_requires_only_relevant_columns() -> None:
    arguments = {
        "table": "Feature_01_Stock_Daily",
        "columns": ["ticker", "return_20d_pct"],
        "filters": [{"column": "sector", "operator": "eq", "value": "Financials"}],
        "order_by": [{"column": "return_20d_pct", "direction": "desc"}],
    }
    assert AnalysisOrchestrator._semantic_requirements("query_features", arguments) == {
        ("Feature_01_Stock_Daily", "ticker"),
        ("Feature_01_Stock_Daily", "return_20d_pct"),
        ("Feature_01_Stock_Daily", "sector"),
    }


def test_loaded_definition_gate_is_recoverable() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    state = RunState("request", "question", {"QUERY"}, [])
    with pytest.raises(Exception, match="get_feature_definition"):
        orchestrator._require_loaded_definitions(
            state,
            "rank_features",
            {"table": "Feature_01_Stock_Daily", "column": "return_20d_pct"},
        )
    state.loaded_feature_definitions.update({
        ("Feature_01_Stock_Daily", "date"),
        ("Feature_01_Stock_Daily", "ticker"),
        ("Feature_01_Stock_Daily", "return_20d_pct"),
    })
    orchestrator._require_loaded_definitions(
        state,
        "rank_features",
        {"table": "Feature_01_Stock_Daily", "column": "return_20d_pct"},
    )
