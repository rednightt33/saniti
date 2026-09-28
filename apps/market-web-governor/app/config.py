from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    pass


def _integer(
    env: Mapping[str, str], name: str, default: int, *, minimum: int = 1, maximum: int | None = None
) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ConfigError(f"{name} must be {bound}")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    provider: str
    store_path: str
    openrouter_api_key: str = field(repr=False)
    openrouter_base_url: str
    openrouter_model: str
    openrouter_engine: str
    openrouter_timeout_seconds: int
    openrouter_max_retries: int
    max_criteria: int
    max_searches: int
    max_results_per_search: int
    max_evidence_items: int
    max_output_characters: int
    max_excerpt_characters: int
    max_output_tokens: int
    retention_hours: int
    cleanup_interval_seconds: int
    app_url: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        api_key = env.get("WEB_GOVERNOR_API_KEY", "").strip()
        provider = env.get("WEB_PROVIDER", "openrouter").strip().lower()
        openrouter_api_key = env.get("OPENROUTER_API_KEY", "").strip()
        missing = []
        if not api_key:
            missing.append("WEB_GOVERNOR_API_KEY")
        if provider == "openrouter" and not openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if missing:
            raise ConfigError(f"Missing required variables: {', '.join(missing)}")
        if len(api_key) < 32:
            raise ConfigError("WEB_GOVERNOR_API_KEY must be at least 32 characters")
        if provider != "openrouter":
            raise ConfigError("WEB_PROVIDER must currently be openrouter")

        engine = env.get("WEB_OPENROUTER_ENGINE", "exa").strip().lower()
        if engine not in {"auto", "native", "exa", "firecrawl", "parallel", "perplexity"}:
            raise ConfigError("WEB_OPENROUTER_ENGINE is not supported")

        settings = cls(
            api_key=api_key,
            provider=provider,
            store_path=env.get("WEB_GOVERNOR_STORE_PATH", "/data/web-governor.sqlite3").strip(),
            openrouter_api_key=openrouter_api_key,
            openrouter_base_url=env.get("WEB_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_model=env.get("WEB_OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash").strip(),
            openrouter_engine=engine,
            openrouter_timeout_seconds=_integer(env, "WEB_OPENROUTER_TIMEOUT_SECONDS", 40, maximum=120),
            openrouter_max_retries=_integer(env, "WEB_OPENROUTER_MAX_RETRIES", 3, minimum=1, maximum=5),
            max_criteria=_integer(env, "WEB_MAX_CRITERIA", 6, maximum=8),
            max_searches=_integer(env, "WEB_MAX_SEARCHES", 6, maximum=8),
            max_results_per_search=_integer(env, "WEB_MAX_RESULTS_PER_SEARCH", 5, maximum=10),
            max_evidence_items=_integer(env, "WEB_MAX_EVIDENCE_ITEMS", 20, maximum=40),
            max_output_characters=_integer(env, "WEB_MAX_OUTPUT_CHARACTERS", 32000, maximum=64000),
            max_excerpt_characters=_integer(env, "WEB_MAX_EXCERPT_CHARACTERS", 2500, maximum=5000),
            max_output_tokens=_integer(env, "WEB_OPENROUTER_MAX_OUTPUT_TOKENS", 1800, maximum=4000),
            retention_hours=_integer(env, "WEB_RETENTION_HOURS", 168, maximum=720),
            cleanup_interval_seconds=_integer(
                env, "WEB_CLEANUP_INTERVAL_SECONDS", 3600, minimum=0, maximum=86400
            ),
            app_url=_optional(env, "WEB_GOVERNOR_APP_URL"),
        )
        if not settings.store_path:
            raise ConfigError("WEB_GOVERNOR_STORE_PATH must not be empty")
        if not settings.openrouter_model:
            raise ConfigError("WEB_OPENROUTER_MODEL must not be empty")
        if settings.max_searches < settings.max_criteria:
            raise ConfigError("WEB_MAX_SEARCHES must be at least WEB_MAX_CRITERIA")
        return settings
