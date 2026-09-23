from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}


class ConfigError(RuntimeError):
    pass


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int = 1) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


def _ratio(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def _boolean(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise ConfigError(f"{name} must be true or false")
    return raw == "true"


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    internal_api_key: str = field(repr=False)
    openrouter_api_key: str = field(repr=False)
    ai_model: str
    ai_reasoning_effort: str
    ai_request_timeout_seconds: int
    ai_max_output_tokens: int
    ai_max_tool_iterations: int
    ai_max_tool_calls: int
    ai_max_identical_tool_calls: int
    ai_max_analysis_seconds: int
    ai_max_context_tokens: int
    ai_context_soft_limit_ratio: float
    ai_max_history_tokens: int
    ai_final_response_max_retries: int
    openrouter_http_referer: str | None
    openrouter_x_title: str
    catalog_database_url: str | None = field(repr=False)
    catalog_connect_timeout_seconds: int
    catalog_statement_timeout_ms: int
    catalog_page_size_default: int
    catalog_page_size_max: int
    catalog_page_max_bytes: int
    market_data_preview_enabled: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        secrets = {
            "MARKET_AI_ORC_API_KEY": env.get("MARKET_AI_ORC_API_KEY", ""),
            "OPENROUTER_API_KEY": env.get("OPENROUTER_API_KEY", ""),
        }
        missing = [name for name, value in secrets.items() if not value.strip()]
        if missing:
            raise ConfigError(f"Missing required variables: {', '.join(missing)}")

        settings = cls(
            internal_api_key=secrets["MARKET_AI_ORC_API_KEY"],
            openrouter_api_key=secrets["OPENROUTER_API_KEY"],
            ai_model=env.get("AI_MODEL", "").strip() or "deepseek/deepseek-v4.1-flash",
            ai_reasoning_effort=env.get("AI_REASONING_EFFORT", "").strip().lower() or "high",
            ai_request_timeout_seconds=_integer(env, "AI_REQUEST_TIMEOUT_SECONDS", 180),
            ai_max_output_tokens=_integer(env, "AI_MAX_OUTPUT_TOKENS", 3000),
            ai_max_tool_iterations=_integer(env, "AI_MAX_TOOL_ITERATIONS", 8),
            ai_max_tool_calls=_integer(env, "AI_MAX_TOOL_CALLS", 12),
            ai_max_identical_tool_calls=_integer(env, "AI_MAX_IDENTICAL_TOOL_CALLS", 2),
            ai_max_analysis_seconds=_integer(env, "AI_MAX_ANALYSIS_SECONDS", 600),
            ai_max_context_tokens=_integer(env, "AI_MAX_CONTEXT_TOKENS", 64000),
            ai_context_soft_limit_ratio=_ratio(env, "AI_CONTEXT_SOFT_LIMIT_RATIO", 0.8, 0.5, 0.95),
            ai_max_history_tokens=_integer(env, "AI_MAX_HISTORY_TOKENS", 4000),
            ai_final_response_max_retries=_integer(
                env, "AI_FINAL_RESPONSE_MAX_RETRIES", 2, minimum=0
            ),
            openrouter_http_referer=_optional(env, "OPENROUTER_HTTP_REFERER"),
            openrouter_x_title=_optional(env, "OPENROUTER_X_TITLE") or "Saniti Market AI",
            catalog_database_url=_optional(env, "CATALOG_DATABASE_URL"),
            catalog_connect_timeout_seconds=_integer(env, "CATALOG_CONNECT_TIMEOUT_SECONDS", 5),
            catalog_statement_timeout_ms=_integer(env, "CATALOG_STATEMENT_TIMEOUT_MS", 5000, minimum=100),
            catalog_page_size_default=_integer(env, "CATALOG_PAGE_SIZE_DEFAULT", 100),
            catalog_page_size_max=_integer(env, "CATALOG_PAGE_SIZE_MAX", 200),
            catalog_page_max_bytes=_integer(env, "CATALOG_PAGE_MAX_BYTES", 16000, minimum=4096),
            market_data_preview_enabled=_boolean(env, "MARKET_DATA_PREVIEW_ENABLED", True),
        )
        if settings.ai_reasoning_effort not in REASONING_EFFORTS:
            raise ConfigError(
                "AI_REASONING_EFFORT must be one of: " + ", ".join(sorted(REASONING_EFFORTS))
            )
        if settings.ai_max_output_tokens >= settings.ai_max_context_tokens:
            raise ConfigError("AI_MAX_OUTPUT_TOKENS must be below AI_MAX_CONTEXT_TOKENS")
        if settings.ai_max_output_tokens >= settings.ai_max_context_tokens * settings.ai_context_soft_limit_ratio:
            raise ConfigError(
                "AI_MAX_OUTPUT_TOKENS must be below AI_MAX_CONTEXT_TOKENS x AI_CONTEXT_SOFT_LIMIT_RATIO"
            )
        if settings.ai_max_history_tokens >= settings.ai_max_context_tokens:
            raise ConfigError("AI_MAX_HISTORY_TOKENS must be below AI_MAX_CONTEXT_TOKENS")
        if settings.catalog_database_url and not settings.catalog_database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ConfigError("CATALOG_DATABASE_URL must be a postgresql:// connection URL")
        if settings.catalog_connect_timeout_seconds > 30 or settings.catalog_statement_timeout_ms > 30000:
            raise ConfigError("Catalog connect/statement timeouts must not exceed 30 seconds")
        if settings.catalog_page_size_default > settings.catalog_page_size_max:
            raise ConfigError("CATALOG_PAGE_SIZE_DEFAULT must not exceed CATALOG_PAGE_SIZE_MAX")
        if settings.catalog_page_size_max > 1000 or settings.catalog_page_max_bytes > 131072:
            raise ConfigError("CATALOG_PAGE_SIZE_MAX must be <= 1000 and CATALOG_PAGE_MAX_BYTES <= 131072")
        if settings.ai_request_timeout_seconds > settings.ai_max_analysis_seconds:
            raise ConfigError("AI_REQUEST_TIMEOUT_SECONDS must not exceed AI_MAX_ANALYSIS_SECONDS")
        return settings
