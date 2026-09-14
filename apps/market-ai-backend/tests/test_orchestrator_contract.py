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


def test_reported_single_call_context_usage_is_accounted_before_audit_enforces_ceiling() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    state = RunState("request", "question", {"META"}, [])
    response = {
        "id": "resp_test",
        "usage": {"input_tokens": orchestrator.settings.ai_max_context_tokens + 1, "output_tokens": 1},
    }
    usage = orchestrator._add_usage(state, response)
    assert usage["input_tokens"] == orchestrator.settings.ai_max_context_tokens + 1
    assert state.cumulative_input == usage["input_tokens"]


def test_analysis_wall_clock_is_a_separate_circuit_breaker() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    state = RunState("request", "question", {"META"}, [])
    state.started_monotonic -= orchestrator.settings.ai_max_analysis_seconds + 1
    with pytest.raises(RuntimeError, match="wall-clock"):
        orchestrator._enforce_budgets(state)


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


def test_missing_definitions_are_auto_loaded_without_model_retry() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    state = RunState("request", "question", {"QUERY"}, [])
    expected = {
        ("Feature_01_Stock_Daily", "date"),
        ("Feature_01_Stock_Daily", "ticker"),
        ("Feature_01_Stock_Daily", "return_20d_pct"),
    }

    class SemanticTools:
        @staticmethod
        def semantic_summaries(features):
            assert features == expected
            return [
                {"feature_table": table, "feature_column": column, "definition": column}
                for table, column in sorted(features)
            ]

    orchestrator.tools = SemanticTools()
    rows = orchestrator._auto_load_definitions(
        state,
        "rank_features",
        {"table": "Feature_01_Stock_Daily", "column": "return_20d_pct"},
    )
    assert len(rows) == 3
    assert state.loaded_feature_definitions == expected
    assert orchestrator._auto_load_definitions(
        state,
        "rank_features",
        {"table": "Feature_01_Stock_Daily", "column": "return_20d_pct"},
    ) == []


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


def test_direct_retrieval_does_not_expose_screening_schemas_until_needed() -> None:
    direct = AnalysisOrchestrator._initial_families("Find BBCA close on the ready date")
    screen = AnalysisOrchestrator._initial_families("Screen top saham berdasarkan return")
    assert "QUERY" in direct and "SCREENING" not in direct
    assert {"QUERY", "SCREENING"} <= screen


def test_run_state_enters_finalization_only_after_completion_signal() -> None:
    state = RunState("request", "question", {"QUERY"}, [])
    assert state.finalization_ready is False
    state.recorded_evidence_ids.add("evidence-1")
    assert state.finalization_ready is False
    state.finalization_ready = True
    assert state.finalization_ready is True


def test_insight_completion_requires_distinct_followup_query() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    state = RunState(
        "request", "screen saham dengan return tertinggi", {"SCREENING"}, [],
        analysis_mode="INSIGHT",
    )
    state.recorded_evidence_ids.add("evidence-1")
    arguments = {
        "evidence_sufficient": True,
        "necessary_followups_completed": True,
        "completion_reason": "Screen completed",
        "remaining_uncertainties": [],
        "optional_next_analysis": [],
    }
    state.analytical_query_hashes.add("query-1")
    with pytest.raises(Exception, match="distinct successful analytical queries"):
        orchestrator._validate_completion(state, arguments)
    state.analytical_query_hashes.add("query-2")
    orchestrator._validate_completion(state, arguments)


def test_condition_runs_requires_only_condition_semantics() -> None:
    arguments = {
        "table": "Feature_01_Stock_Daily",
        "conditions": [
            {"column": "return_1d_pct", "operator": "gt", "value": 0},
            {"column": "volume_ratio_20d", "operator": "gte", "value": 1.5},
        ],
    }
    assert AnalysisOrchestrator._semantic_requirements(
        "find_condition_runs", arguments
    ) == {
        ("Feature_01_Stock_Daily", "date"),
        ("Feature_01_Stock_Daily", "ticker"),
        ("Feature_01_Stock_Daily", "return_1d_pct"),
        ("Feature_01_Stock_Daily", "volume_ratio_20d"),
    }


def test_streak_language_exposes_screening_tool_family() -> None:
    families = AnalysisOrchestrator._initial_families(
        "Kapan BBCA return positif 7 hari berturut-turut?"
    )
    assert {"QUERY", "SCREENING"} <= families


def test_impossible_quality_fail_blocks_completion_but_warning_does_not() -> None:
    orchestrator = object.__new__(AnalysisOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    state = RunState("request", "question", {"QUERY"}, [])
    state.recorded_evidence_ids.add("evidence-1")
    arguments = {
        "evidence_sufficient": True,
        "necessary_followups_completed": True,
        "completion_reason": "Direct evidence is sufficient",
        "remaining_uncertainties": [],
        "optional_next_analysis": [],
    }
    orchestrator._validate_completion(state, arguments)
    state.quality_failures.append({"table": "Feature_01_Stock_Daily"})
    with pytest.raises(Exception, match="FAIL blocks finalization"):
        orchestrator._validate_completion(state, arguments)


def test_cumulative_pressure_triggers_context_compaction_once() -> None:
    class FakeTools:
        @staticmethod
        def definitions(_families):
            return []

    class FakeOrchestrator(AnalysisOrchestrator):
        def _log_step(self, *_args, **_kwargs):
            return None

        def _persist_usage(self, _state):
            return None

    orchestrator = object.__new__(FakeOrchestrator)
    orchestrator.settings = Settings.from_env(require_runtime_secrets=False)
    orchestrator.tools = FakeTools()
    state = RunState("request", "question", {"META"}, [{"role": "user", "content": "detail"}])
    state.cumulative_input = (
        orchestrator.settings.ai_max_cumulative_input_tokens
        * orchestrator.settings.ai_cumulative_compaction_threshold_percent
        // 100
    )
    orchestrator._compact_context_if_needed(state)
    assert state.compactions == 1
    assert state.cumulative_pressure_compacted is True
    orchestrator._compact_context_if_needed(state)
    assert state.compactions == 1


def test_malformed_provider_tool_arguments_are_recoverable_and_not_stored_raw() -> None:
    class FakeOrchestrator(AnalysisOrchestrator):
        logged_arguments = None

        def _log_step(self, _state, _step, _name, arguments, *_args, **_kwargs):
            self.logged_arguments = arguments

        def _persist_usage(self, _state):
            return None

    orchestrator = object.__new__(FakeOrchestrator)
    state = RunState("request", "question", {"META"}, [])
    raw = '{"claim":"unterminated'
    result = orchestrator._recover_malformed_tool_arguments(
        state,
        "record_evidence",
        {"arguments": raw},
        ValueError("bad json"),
    )
    assert result["recoverable"] is True
    assert state.tool_calls == 1
    assert raw not in str(orchestrator.logged_arguments)
    assert orchestrator.logged_arguments["argument_characters"] == len(raw)
