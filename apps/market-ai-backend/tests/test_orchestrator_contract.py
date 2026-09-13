from __future__ import annotations

import pytest

from app.config import Settings
from app.orchestrator import AnalysisOrchestrator, RunState


def test_extracts_structured_output_text() -> None:
    response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"answer":"ok"}'}]}]}
    assert AnalysisOrchestrator._output_text(response) == '{"answer":"ok"}'


def _valid_final_json() -> str:
    return '''{"answer":"ok","conclusion":"test","confidence":"LOW","analysis_ready_date":null,"evidence_ids":[],"warnings":[],"recommended_next_analysis":[]}'''


def test_accepts_bare_or_exact_json_fence_and_validates_schema() -> None:
    expected = AnalysisOrchestrator._parse_final_output(_valid_final_json())
    assert expected["answer"] == "ok"
    fenced = AnalysisOrchestrator._parse_final_output(f"```json\n{_valid_final_json()}\n```")
    assert fenced == expected


def test_rejects_prose_or_extra_final_fields() -> None:
    with pytest.raises(RuntimeError, match="validation failed"):
        AnalysisOrchestrator._parse_final_output("Here is the answer: " + _valid_final_json())
    with pytest.raises(RuntimeError, match="validation failed"):
        AnalysisOrchestrator._parse_final_output(_valid_final_json()[:-1] + ',"extra":true}')


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


def test_final_contract_requires_recorded_and_exact_evidence_ids() -> None:
    state = RunState("request", "question", {"QUERY"}, [])
    answer = AnalysisOrchestrator._parse_final_output(_valid_final_json())
    assert "record_evidence" in AnalysisOrchestrator._final_contract_issue(state, answer)

    state.recorded_evidence_ids.add("evidence-1")
    assert "at least one" in AnalysisOrchestrator._final_contract_issue(state, answer)

    answer["evidence_ids"] = ["invented"]
    assert "unverified" in AnalysisOrchestrator._final_contract_issue(state, answer)

    answer["evidence_ids"] = ["evidence-1"]
    assert AnalysisOrchestrator._final_contract_issue(state, answer) is None


def test_direct_retrieval_starts_with_query_tools_without_advanced_tools() -> None:
    assert AnalysisOrchestrator._initial_stage("Find BBCA close on the ready date") == "SCREENING"
    assert AnalysisOrchestrator._initial_stage("Laporkan return BBCA") == "SCREENING"
    assert AnalysisOrchestrator._initial_stage("What features are available?") == "DISCOVERY"


def test_run_state_enters_finalization_only_after_evidence_signal() -> None:
    state = RunState("request", "question", {"QUERY"}, [])
    assert state.finalization_ready is False
    state.recorded_evidence_ids.add("evidence-1")
    state.finalization_ready = True
    assert state.finalization_ready is True
