from __future__ import annotations

import inspect

import pytest

from app.config import ConfigError, Settings
from app.tools import build_default_registry
from conftest import BASE_ENV, make_settings


@pytest.mark.parametrize("missing", ["MARKET_AI_ORC_API_KEY", "OPENROUTER_API_KEY"])
def test_missing_secret_is_rejected(missing: str) -> None:
    env = {key: value for key, value in BASE_ENV.items() if key != missing}
    with pytest.raises(ConfigError, match=missing):
        Settings.from_env(env)


def test_blank_secret_is_rejected() -> None:
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        Settings.from_env({**BASE_ENV, "OPENROUTER_API_KEY": "   "})


def test_valid_configuration_loads_with_defaults() -> None:
    settings = make_settings()
    assert settings.openrouter_api_key == BASE_ENV["OPENROUTER_API_KEY"]
    assert settings.ai_model == "deepseek/deepseek-v4.1-flash"
    assert settings.ai_reasoning_effort == "high"
    assert settings.ai_max_identical_tool_calls == 2
    assert settings.ai_final_response_max_retries == 2
    assert settings.openrouter_http_referer is None
    assert settings.openrouter_x_title == "Saniti Market AI"


def test_overrides_are_applied() -> None:
    settings = make_settings(
        AI_MODEL="openai/gpt-test", AI_REASONING_EFFORT="LOW", AI_MAX_TOOL_CALLS="3",
        AI_FINAL_RESPONSE_MAX_RETRIES="0", OPENROUTER_HTTP_REFERER="https://saniti.example",
    )
    assert settings.ai_model == "openai/gpt-test"
    assert settings.ai_reasoning_effort == "low"
    assert settings.ai_max_tool_calls == 3
    assert settings.ai_final_response_max_retries == 0
    assert settings.openrouter_http_referer == "https://saniti.example"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AI_MAX_TOOL_CALLS", "abc", "must be an integer"),
        ("AI_MAX_TOOL_ITERATIONS", "0", "at least 1"),
        ("AI_MAX_OUTPUT_TOKENS", "-5", "at least 1"),
        ("AI_FINAL_RESPONSE_MAX_RETRIES", "-1", "at least 0"),
        ("AI_MAX_OUTPUT_TOKENS", "70000", "below AI_MAX_CONTEXT_TOKENS"),
        ("AI_MAX_HISTORY_TOKENS", "64000", "below AI_MAX_CONTEXT_TOKENS"),
        ("AI_REQUEST_TIMEOUT_SECONDS", "900", "must not exceed AI_MAX_ANALYSIS_SECONDS"),
        ("AI_REASONING_EFFORT", "extreme", "AI_REASONING_EFFORT must be one of"),
    ],
)
def test_invalid_limits_are_rejected(name: str, value: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**{name: value})


def test_secrets_are_hidden_from_repr() -> None:
    rendered = repr(make_settings())
    assert BASE_ENV["OPENROUTER_API_KEY"] not in rendered
    assert BASE_ENV["MARKET_AI_ORC_API_KEY"] not in rendered


def test_old_backend_variables_are_not_required() -> None:
    settings = Settings.from_env(dict(BASE_ENV))
    fields = set(Settings.__dataclass_fields__)
    assert not {"database_url", "ai_provider", "analytics_bucket_name", "query_sandbox_api_key"} & fields
    assert settings.internal_api_key == BASE_ENV["MARKET_AI_ORC_API_KEY"]


def test_catalog_database_is_optional_and_hidden_from_repr() -> None:
    assert make_settings().catalog_database_url is None
    settings = make_settings(CATALOG_DATABASE_URL="postgresql://market_ai_orc:s3cret@db:5432/railway")
    assert settings.catalog_database_url.startswith("postgresql://")
    assert "s3cret" not in repr(settings)
    assert (settings.catalog_connect_timeout_seconds, settings.catalog_statement_timeout_ms) == (5, 5000)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("CATALOG_DATABASE_URL", "mysql://x@y/z", "postgresql://"),
        ("CATALOG_CONNECT_TIMEOUT_SECONDS", "31", "30 seconds"),
        ("CATALOG_STATEMENT_TIMEOUT_MS", "30001", "30 seconds"),
        ("CATALOG_STATEMENT_TIMEOUT_MS", "50", "at least 100"),
    ],
)
def test_invalid_catalog_settings_are_rejected(name: str, value: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**{name: value})


def test_catalog_paging_and_preview_defaults() -> None:
    settings = make_settings()
    assert (settings.catalog_page_size_default, settings.catalog_page_size_max) == (100, 200)
    assert settings.catalog_page_max_bytes == 16000 and settings.market_data_preview_enabled is True
    assert inspect.signature(build_default_registry).parameters["page_max_bytes"].default == 16000
    assert make_settings(MARKET_DATA_PREVIEW_ENABLED="false").market_data_preview_enabled is False


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("CATALOG_PAGE_SIZE_DEFAULT", "300", "must not exceed CATALOG_PAGE_SIZE_MAX"),
        ("CATALOG_PAGE_SIZE_MAX", "5000", "<= 1000"),
        ("CATALOG_PAGE_MAX_BYTES", "1000", "at least 4096"),
        ("CATALOG_PAGE_MAX_BYTES", "999999", "131072"),
        ("MARKET_DATA_PREVIEW_ENABLED", "yes", "true or false"),
    ],
)
def test_invalid_paging_settings_are_rejected(name: str, value: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**{name: value})


def test_context_soft_limit_ratio_default_and_override() -> None:
    assert make_settings().ai_context_soft_limit_ratio == 0.8
    assert make_settings(AI_CONTEXT_SOFT_LIMIT_RATIO="0.5").ai_context_soft_limit_ratio == 0.5
    assert make_settings(AI_CONTEXT_SOFT_LIMIT_RATIO="0.95").ai_context_soft_limit_ratio == 0.95


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"AI_CONTEXT_SOFT_LIMIT_RATIO": "0.49"}, "between 0.5 and 0.95"),
        ({"AI_CONTEXT_SOFT_LIMIT_RATIO": "0.96"}, "between 0.5 and 0.95"),
        ({"AI_CONTEXT_SOFT_LIMIT_RATIO": "1"}, "between 0.5 and 0.95"),
        ({"AI_CONTEXT_SOFT_LIMIT_RATIO": "high"}, "must be a number"),
        ({"AI_MAX_CONTEXT_TOKENS": "10000", "AI_MAX_OUTPUT_TOKENS": "8000"}, "AI_CONTEXT_SOFT_LIMIT_RATIO"),
    ],
)
def test_invalid_context_soft_limit_is_rejected(overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**overrides)
