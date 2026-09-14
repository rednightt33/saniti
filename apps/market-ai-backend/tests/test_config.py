from __future__ import annotations

import os

import pytest

from app.config import Settings


def test_default_limits_are_three_separate_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(("QUERY_", "LLM_", "AI_", "ANALYTICS_")):
            monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env(require_runtime_secrets=False)
    assert settings.query_max_rows == 5000
    assert settings.llm_tool_result_max_rows == 200
    assert settings.ai_max_output_tokens == 3000
    assert settings.ai_max_feature_metadata_tokens == 5000
    assert settings.ai_max_cumulative_input_tokens == 500000
    assert settings.ai_context_compaction_mode == "PRESERVE_DECISIVE"
    assert settings.ai_final_response_max_retries == 2
    assert settings.ai_finalization_tool_result_reserve_tokens == 1000
    assert settings.ai_finalization_output_reserve_tokens == 4000
    assert settings.ai_target_context_tokens < settings.ai_context_compaction_threshold_tokens < settings.ai_max_context_tokens
    assert settings.ai_max_cumulative_input_tokens > settings.ai_max_context_tokens
    assert settings.ai_cumulative_compaction_threshold_percent == 75
    assert settings.ai_store_reasoning_details is True
    assert settings.ai_reasoning_retention_days == 30
    assert settings.ai_reasoning_max_bytes_per_call == 65536
    assert settings.ai_analysis_mode == "QUICK"
    assert settings.ai_min_insight_data_calls == 2
    assert settings.ai_max_analysis_seconds == 600
    assert settings.condition_runs_max_date_range_days == 7305
    assert settings.condition_runs_max_episodes == 200
    assert settings.query_sandbox_max_rows == 100000
    assert settings.statistical_max_rows == 500000
    assert settings.query_sandbox_max_memory_mb < settings.statistical_max_memory_mb


def test_invalid_context_order_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TARGET_CONTEXT_TOKENS", "40000")
    monkeypatch.setenv("AI_CONTEXT_COMPACTION_THRESHOLD_TOKENS", "32000")
    with pytest.raises(RuntimeError, match="context target"):
        Settings.from_env(require_runtime_secrets=False)


def test_openrouter_uses_deepseek_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("AI_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    settings = Settings.from_env(require_runtime_secrets=False)
    assert settings.ai_model == "deepseek/deepseek-v4.1-flash"
    assert settings.ai_reasoning_effort == "high"


def test_invalid_analysis_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ANALYSIS_MODE", "ENDLESS")
    with pytest.raises(RuntimeError, match="AI_ANALYSIS_MODE"):
        Settings.from_env(require_runtime_secrets=False)


def test_invalid_cumulative_compaction_percent_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT", "100")
    with pytest.raises(RuntimeError, match="below 100"):
        Settings.from_env(require_runtime_secrets=False)


def test_invalid_compaction_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_CONTEXT_COMPACTION_MODE", "LOSSY")
    with pytest.raises(RuntimeError, match="AI_CONTEXT_COMPACTION_MODE"):
        Settings.from_env(require_runtime_secrets=False)


def test_finalization_reserves_must_fit_their_parent_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_MAX_TOOL_RESULT_TOKENS_TOTAL", "1000")
    monkeypatch.setenv("AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS", "1000")
    with pytest.raises(RuntimeError, match="TOOL_RESULT"):
        Settings.from_env(require_runtime_secrets=False)

    monkeypatch.setenv("AI_MAX_TOOL_RESULT_TOKENS_TOTAL", "12000")
    monkeypatch.setenv("AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS", "1000")
    monkeypatch.setenv("AI_MAX_CUMULATIVE_OUTPUT_TOKENS", "4000")
    monkeypatch.setenv("AI_FINALIZATION_OUTPUT_RESERVE_TOKENS", "4000")
    with pytest.raises(RuntimeError, match="OUTPUT_RESERVE"):
        Settings.from_env(require_runtime_secrets=False)


def test_invalid_reasoning_storage_boolean_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_STORE_REASONING_DETAILS", "sometimes")
    with pytest.raises(RuntimeError, match="true or false"):
        Settings.from_env(require_runtime_secrets=False)
