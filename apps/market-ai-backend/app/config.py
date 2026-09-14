from __future__ import annotations

import os
from dataclasses import dataclass


def _integer(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class Settings:
    database_url: str
    internal_api_key: str
    ai_provider: str
    ai_api_key: str
    ai_model: str
    ai_reasoning_effort: str
    query_default_rows: int
    query_max_rows: int
    query_max_tickers: int
    query_max_columns: int
    query_max_date_range_days: int
    query_max_unfiltered_date_range_days: int
    query_max_estimated_rows: int
    query_timeout_seconds: int
    query_max_output_bytes: int
    query_max_groups: int
    query_max_periods: int
    condition_runs_max_date_range_days: int
    condition_runs_max_episodes: int
    llm_tool_result_max_rows: int
    llm_tool_result_max_bytes: int
    ai_max_output_tokens: int
    ai_max_tool_result_tokens_per_call: int
    ai_max_tool_result_tokens_total: int
    ai_finalization_tool_result_reserve_tokens: int
    ai_max_history_tokens: int
    ai_max_feature_metadata_tokens: int
    ai_context_reserve_tokens: int
    ai_target_context_tokens: int
    ai_context_compaction_threshold_tokens: int
    ai_max_context_tokens: int
    ai_max_cumulative_input_tokens: int
    ai_max_cumulative_output_tokens: int
    ai_finalization_output_reserve_tokens: int
    ai_cumulative_compaction_threshold_percent: int
    ai_context_compaction_mode: str
    ai_final_response_max_retries: int
    ai_store_reasoning_details: bool
    ai_reasoning_retention_days: int
    ai_reasoning_max_bytes_per_call: int
    ai_reasoning_cleanup_interval_seconds: int
    ai_max_tool_iterations: int
    ai_max_tool_calls: int
    ai_analysis_mode: str
    ai_min_insight_data_calls: int
    ai_max_analysis_seconds: int
    ai_request_timeout_seconds: int
    worker_poll_seconds: int
    worker_lease_seconds: int
    analytics_enabled: bool
    analytics_worker_api_key: str
    query_sandbox_api_key: str
    statistical_worker_api_key: str
    analytics_bucket_name: str
    analytics_bucket_endpoint: str
    analytics_bucket_access_key_id: str
    analytics_bucket_secret_access_key: str
    analytics_bucket_region: str
    analytics_max_rows: int
    analytics_max_columns: int
    analytics_max_input_bytes: int
    analytics_max_estimated_rows: int
    analytics_max_date_range_days: int
    analytics_max_datasets: int
    analytics_max_runtime_seconds: int
    analytics_max_memory_mb: int
    analytics_max_result_rows: int
    analytics_max_result_bytes: int
    analytics_job_wait_seconds: int
    analytics_job_poll_milliseconds: int
    analytics_snapshot_retention_hours: int
    analytics_terminal_snapshot_grace_seconds: int
    analytics_result_retention_days: int
    query_sandbox_max_rows: int
    query_sandbox_max_columns: int
    query_sandbox_max_input_bytes: int
    query_sandbox_max_estimated_rows: int
    query_sandbox_max_date_range_days: int
    query_sandbox_max_tickers: int
    query_sandbox_max_datasets: int
    query_sandbox_max_runtime_seconds: int
    query_sandbox_max_memory_mb: int
    query_sandbox_max_result_rows: int
    query_sandbox_max_result_bytes: int
    statistical_max_rows: int
    statistical_max_columns: int
    statistical_max_input_bytes: int
    statistical_max_estimated_rows: int
    statistical_max_date_range_days: int
    statistical_max_tickers: int
    statistical_max_datasets: int
    statistical_max_runtime_seconds: int
    statistical_max_memory_mb: int
    statistical_max_result_rows: int
    statistical_max_result_bytes: int
    ai_max_discovery_calls: int

    @classmethod
    def from_env(cls, *, require_runtime_secrets: bool = True) -> "Settings":
        provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
        if provider not in {"openai", "openrouter"}:
            raise RuntimeError("AI_PROVIDER must be openai or openrouter")
        secret_name = "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_DEEPSEEK"
        default_model = "gpt-5.6-terra" if provider == "openai" else "deepseek/deepseek-v4.1-flash"
        required = {
            "DATABASE_URL": os.getenv("DATABASE_URL", ""),
            "MARKET_AI_INTERNAL_API_KEY": os.getenv("MARKET_AI_INTERNAL_API_KEY", ""),
            secret_name: os.getenv(secret_name, ""),
        }
        if require_runtime_secrets:
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise RuntimeError(f"Missing required variables: {', '.join(missing)}")
        settings = cls(
            database_url=required["DATABASE_URL"],
            internal_api_key=required["MARKET_AI_INTERNAL_API_KEY"],
            ai_provider=provider,
            ai_api_key=required[secret_name],
            ai_model=os.getenv("AI_MODEL") or (
                os.getenv("OPENAI_MODEL", default_model) if provider == "openai" else default_model
            ),
            ai_reasoning_effort=os.getenv(
                "AI_REASONING_EFFORT"
            ) or (
                os.getenv("OPENAI_REASONING_EFFORT", "medium") if provider == "openai" else "high"
            ),
            query_default_rows=_integer("QUERY_DEFAULT_ROWS", 500),
            query_max_rows=_integer("QUERY_MAX_ROWS", 5000),
            query_max_tickers=_integer("QUERY_MAX_TICKERS", 20),
            query_max_columns=_integer("QUERY_MAX_COLUMNS", 20),
            query_max_date_range_days=_integer("QUERY_MAX_DATE_RANGE_DAYS", 1825),
            query_max_unfiltered_date_range_days=_integer("QUERY_MAX_UNFILTERED_DATE_RANGE_DAYS", 31),
            query_max_estimated_rows=_integer("QUERY_MAX_ESTIMATED_ROWS", 100000),
            query_timeout_seconds=_integer("QUERY_TIMEOUT_SECONDS", 15),
            query_max_output_bytes=_integer("QUERY_MAX_OUTPUT_BYTES", 1048576),
            query_max_groups=_integer("QUERY_MAX_GROUPS", 1000),
            query_max_periods=_integer("QUERY_MAX_PERIODS", 6),
            condition_runs_max_date_range_days=_integer(
                "CONDITION_RUNS_MAX_DATE_RANGE_DAYS", 7305
            ),
            condition_runs_max_episodes=_integer("CONDITION_RUNS_MAX_EPISODES", 200),
            llm_tool_result_max_rows=_integer("LLM_TOOL_RESULT_MAX_ROWS", 200),
            llm_tool_result_max_bytes=_integer("LLM_TOOL_RESULT_MAX_BYTES", 131072),
            ai_max_output_tokens=_integer("AI_MAX_OUTPUT_TOKENS", 3000),
            ai_max_tool_result_tokens_per_call=_integer("AI_MAX_TOOL_RESULT_TOKENS_PER_CALL", 4000),
            ai_max_tool_result_tokens_total=_integer("AI_MAX_TOOL_RESULT_TOKENS_TOTAL", 12000),
            ai_finalization_tool_result_reserve_tokens=_integer(
                "AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS", 1000
            ),
            ai_max_history_tokens=_integer("AI_MAX_HISTORY_TOKENS", 4000),
            ai_max_feature_metadata_tokens=_integer("AI_MAX_FEATURE_METADATA_TOKENS", 5000),
            ai_context_reserve_tokens=_integer("AI_CONTEXT_RESERVE_TOKENS", 8000),
            ai_target_context_tokens=_integer("AI_TARGET_CONTEXT_TOKENS", 24000),
            ai_context_compaction_threshold_tokens=_integer("AI_CONTEXT_COMPACTION_THRESHOLD_TOKENS", 32000),
            ai_max_context_tokens=_integer("AI_MAX_CONTEXT_TOKENS", 64000),
            ai_max_cumulative_input_tokens=_integer("AI_MAX_CUMULATIVE_INPUT_TOKENS", 500000),
            ai_max_cumulative_output_tokens=_integer("AI_MAX_CUMULATIVE_OUTPUT_TOKENS", 12000),
            ai_finalization_output_reserve_tokens=_integer(
                "AI_FINALIZATION_OUTPUT_RESERVE_TOKENS", 4000
            ),
            ai_cumulative_compaction_threshold_percent=_integer(
                "AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT", 75
            ),
            ai_context_compaction_mode=os.getenv(
                "AI_CONTEXT_COMPACTION_MODE", "PRESERVE_DECISIVE"
            ).strip().upper(),
            ai_final_response_max_retries=_integer("AI_FINAL_RESPONSE_MAX_RETRIES", 2),
            ai_store_reasoning_details=_boolean("AI_STORE_REASONING_DETAILS", True),
            ai_reasoning_retention_days=_integer("AI_REASONING_RETENTION_DAYS", 30),
            ai_reasoning_max_bytes_per_call=_integer(
                "AI_REASONING_MAX_BYTES_PER_CALL", 65536
            ),
            ai_reasoning_cleanup_interval_seconds=_integer(
                "AI_REASONING_CLEANUP_INTERVAL_SECONDS", 3600
            ),
            ai_max_tool_iterations=_integer("AI_MAX_TOOL_ITERATIONS", 8),
            ai_max_tool_calls=_integer("AI_MAX_TOOL_CALLS", 12),
            ai_analysis_mode=os.getenv("AI_ANALYSIS_MODE", "QUICK").strip().upper(),
            ai_min_insight_data_calls=_integer("AI_MIN_INSIGHT_DATA_CALLS", 2),
            ai_max_analysis_seconds=_integer("AI_MAX_ANALYSIS_SECONDS", 600),
            ai_request_timeout_seconds=_integer("AI_REQUEST_TIMEOUT_SECONDS", 180),
            worker_poll_seconds=_integer("WORKER_POLL_SECONDS", 2),
            worker_lease_seconds=_integer("WORKER_LEASE_SECONDS", 300),
            analytics_enabled=_boolean("ANALYTICS_ENABLED", False),
            analytics_worker_api_key=os.getenv("ANALYTICS_WORKER_API_KEY", ""),
            query_sandbox_api_key=os.getenv("QUERY_SANDBOX_API_KEY", ""),
            statistical_worker_api_key=os.getenv(
                "STATISTICAL_WORKER_API_KEY", os.getenv("ANALYTICS_WORKER_API_KEY", "")
            ),
            analytics_bucket_name=os.getenv("ANALYTICS_BUCKET_NAME", ""),
            analytics_bucket_endpoint=os.getenv("ANALYTICS_BUCKET_ENDPOINT", ""),
            analytics_bucket_access_key_id=os.getenv("ANALYTICS_BUCKET_ACCESS_KEY_ID", ""),
            analytics_bucket_secret_access_key=os.getenv("ANALYTICS_BUCKET_SECRET_ACCESS_KEY", ""),
            analytics_bucket_region=os.getenv("ANALYTICS_BUCKET_REGION", "auto"),
            analytics_max_rows=_integer("ANALYTICS_MAX_ROWS", 50000),
            analytics_max_columns=_integer("ANALYTICS_MAX_COLUMNS", 30),
            analytics_max_input_bytes=_integer("ANALYTICS_MAX_INPUT_BYTES", 20971520),
            analytics_max_estimated_rows=_integer("ANALYTICS_MAX_ESTIMATED_ROWS", 2000000),
            analytics_max_date_range_days=_integer("ANALYTICS_MAX_DATE_RANGE_DAYS", 3653),
            analytics_max_datasets=_integer("ANALYTICS_MAX_DATASETS", 4),
            analytics_max_runtime_seconds=_integer("ANALYTICS_MAX_RUNTIME_SECONDS", 120),
            analytics_max_memory_mb=_integer("ANALYTICS_MAX_MEMORY_MB", 2048),
            analytics_max_result_rows=_integer("ANALYTICS_MAX_RESULT_ROWS", 500),
            analytics_max_result_bytes=_integer("ANALYTICS_MAX_RESULT_BYTES", 262144),
            analytics_job_wait_seconds=_integer("ANALYTICS_JOB_WAIT_SECONDS", 150),
            analytics_job_poll_milliseconds=_integer("ANALYTICS_JOB_POLL_MILLISECONDS", 500, 100),
            analytics_snapshot_retention_hours=_integer("ANALYTICS_SNAPSHOT_RETENTION_HOURS", 24),
            analytics_terminal_snapshot_grace_seconds=_integer(
                "ANALYTICS_TERMINAL_SNAPSHOT_GRACE_SECONDS", 3600
            ),
            analytics_result_retention_days=_integer("ANALYTICS_RESULT_RETENTION_DAYS", 90),
            query_sandbox_max_rows=_integer("QUERY_SANDBOX_MAX_ROWS", 100000),
            query_sandbox_max_columns=_integer("QUERY_SANDBOX_MAX_COLUMNS", 40),
            query_sandbox_max_input_bytes=_integer("QUERY_SANDBOX_MAX_INPUT_BYTES", 41943040),
            query_sandbox_max_estimated_rows=_integer("QUERY_SANDBOX_MAX_ESTIMATED_ROWS", 3000000),
            query_sandbox_max_date_range_days=_integer("QUERY_SANDBOX_MAX_DATE_RANGE_DAYS", 7305),
            query_sandbox_max_tickers=_integer("QUERY_SANDBOX_MAX_TICKERS", 100),
            query_sandbox_max_datasets=_integer("QUERY_SANDBOX_MAX_DATASETS", 6),
            query_sandbox_max_runtime_seconds=_integer("QUERY_SANDBOX_MAX_RUNTIME_SECONDS", 90),
            query_sandbox_max_memory_mb=_integer("QUERY_SANDBOX_MAX_MEMORY_MB", 1024),
            query_sandbox_max_result_rows=_integer("QUERY_SANDBOX_MAX_RESULT_ROWS", 500),
            query_sandbox_max_result_bytes=_integer("QUERY_SANDBOX_MAX_RESULT_BYTES", 262144),
            statistical_max_rows=_integer("STATISTICAL_MAX_ROWS", 500000),
            statistical_max_columns=_integer("STATISTICAL_MAX_COLUMNS", 60),
            statistical_max_input_bytes=_integer("STATISTICAL_MAX_INPUT_BYTES", 209715200),
            statistical_max_estimated_rows=_integer("STATISTICAL_MAX_ESTIMATED_ROWS", 10000000),
            statistical_max_date_range_days=_integer("STATISTICAL_MAX_DATE_RANGE_DAYS", 7305),
            statistical_max_tickers=_integer("STATISTICAL_MAX_TICKERS", 1000),
            statistical_max_datasets=_integer("STATISTICAL_MAX_DATASETS", 8),
            statistical_max_runtime_seconds=_integer("STATISTICAL_MAX_RUNTIME_SECONDS", 300),
            statistical_max_memory_mb=_integer("STATISTICAL_MAX_MEMORY_MB", 4096),
            statistical_max_result_rows=_integer("STATISTICAL_MAX_RESULT_ROWS", 1000),
            statistical_max_result_bytes=_integer("STATISTICAL_MAX_RESULT_BYTES", 524288),
            ai_max_discovery_calls=_integer("AI_MAX_DISCOVERY_CALLS", 4),
        )
        if not (
            settings.ai_target_context_tokens
            < settings.ai_context_compaction_threshold_tokens
            < settings.ai_max_context_tokens
        ):
            raise RuntimeError("AI context target must be below compaction threshold and hard ceiling")
        if settings.ai_context_reserve_tokens >= settings.ai_max_context_tokens:
            raise RuntimeError("AI_CONTEXT_RESERVE_TOKENS must be below AI_MAX_CONTEXT_TOKENS")
        if settings.ai_cumulative_compaction_threshold_percent >= 100:
            raise RuntimeError("AI_CUMULATIVE_COMPACTION_THRESHOLD_PERCENT must be below 100")
        if settings.ai_context_compaction_mode not in {"DISABLED", "PRESERVE_DECISIVE"}:
            raise RuntimeError(
                "AI_CONTEXT_COMPACTION_MODE must be DISABLED or PRESERVE_DECISIVE"
            )
        if (
            settings.ai_finalization_tool_result_reserve_tokens
            >= settings.ai_max_tool_result_tokens_total
        ):
            raise RuntimeError(
                "AI_FINALIZATION_TOOL_RESULT_RESERVE_TOKENS must be below "
                "AI_MAX_TOOL_RESULT_TOKENS_TOTAL"
            )
        if (
            settings.ai_finalization_output_reserve_tokens
            >= settings.ai_max_cumulative_output_tokens
        ):
            raise RuntimeError(
                "AI_FINALIZATION_OUTPUT_RESERVE_TOKENS must be below "
                "AI_MAX_CUMULATIVE_OUTPUT_TOKENS"
            )
        if settings.query_default_rows > settings.query_max_rows:
            raise RuntimeError("QUERY_DEFAULT_ROWS must not exceed QUERY_MAX_ROWS")
        if settings.ai_provider == "openrouter" and settings.ai_reasoning_effort not in {"low", "high", "max"}:
            raise RuntimeError("OpenRouter DeepSeek reasoning effort must be low, high, or max")
        if settings.ai_analysis_mode not in {"QUICK", "INSIGHT"}:
            raise RuntimeError("AI_ANALYSIS_MODE must be QUICK or INSIGHT")
        if settings.analytics_enabled:
            analytics_required = {
                "QUERY_SANDBOX_API_KEY": settings.query_sandbox_api_key,
                "STATISTICAL_WORKER_API_KEY": settings.statistical_worker_api_key,
                "ANALYTICS_BUCKET_NAME": settings.analytics_bucket_name,
                "ANALYTICS_BUCKET_ENDPOINT": settings.analytics_bucket_endpoint,
                "ANALYTICS_BUCKET_ACCESS_KEY_ID": settings.analytics_bucket_access_key_id,
                "ANALYTICS_BUCKET_SECRET_ACCESS_KEY": settings.analytics_bucket_secret_access_key,
            }
            missing = [name for name, value in analytics_required.items() if not value]
            if missing:
                raise RuntimeError(
                    "ANALYTICS_ENABLED requires variables: " + ", ".join(missing)
                )
        if settings.analytics_max_result_rows > settings.analytics_max_rows:
            raise RuntimeError("ANALYTICS_MAX_RESULT_ROWS must not exceed ANALYTICS_MAX_ROWS")
        if settings.query_sandbox_max_result_rows > settings.query_sandbox_max_rows:
            raise RuntimeError("QUERY_SANDBOX_MAX_RESULT_ROWS must not exceed QUERY_SANDBOX_MAX_ROWS")
        if settings.statistical_max_result_rows > settings.statistical_max_rows:
            raise RuntimeError("STATISTICAL_MAX_RESULT_ROWS must not exceed STATISTICAL_MAX_ROWS")
        return settings
