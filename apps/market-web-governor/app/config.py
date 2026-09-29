from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


MODEL_SLOT_COUNT = 7
REASONING_EFFORTS = {"minimal", "low", "medium", "high"}
ENGINES = {"auto", "native", "exa", "firecrawl", "parallel", "perplexity"}


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


def _effort(value: str) -> str | None:
    """off: reasoning disabled (the default for the classifier: the rubric decides, the form is small);
    none/empty: send no reasoning parameter; otherwise an effort level."""
    value = value.strip().lower()
    if not value or value == "none":
        return None
    if value != "off" and value not in REASONING_EFFORTS:
        raise ConfigError(f"WEB_CLASSIFIER_REASONING_EFFORT must be off, none or one of {sorted(REASONING_EFFORTS)}")
    return value


@dataclass(frozen=True)
class ModelSlot:
    """One selectable model configuration. Every slot calls OpenRouter with the service's own key."""

    slot: int
    model: str | None
    label: str
    enabled: bool
    max_output_tokens: int
    reasoning_effort: str | None
    engine: str

    def public(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "label": self.label,
            "model": self.model,
            "enabled": self.enabled,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "engine": self.engine,
        }


def _slots(env: Mapping[str, str], default_model: str, default_tokens: int, default_engine: str) -> tuple[ModelSlot, ...]:
    slots = []
    for number in range(1, MODEL_SLOT_COUNT + 1):
        prefix = f"WEB_SLOT_{number}_"
        model = _optional(env, prefix + "MODEL")
        if number == 1 and not model:
            model = default_model  # slot 1 keeps the pre-slot WEB_OPENROUTER_MODEL configuration
        enabled_raw = env.get(prefix + "ENABLED", "true" if model else "false").strip().lower()
        if enabled_raw not in {"true", "false"}:
            raise ConfigError(f"{prefix}ENABLED must be true or false")
        effort = _optional(env, prefix + "REASONING_EFFORT")
        if effort and effort.lower() not in REASONING_EFFORTS:
            raise ConfigError(f"{prefix}REASONING_EFFORT must be one of {sorted(REASONING_EFFORTS)}")
        engine = (_optional(env, prefix + "ENGINE") or default_engine).lower()
        if engine not in ENGINES:
            raise ConfigError(f"{prefix}ENGINE is not supported")
        enabled = enabled_raw == "true"
        if enabled and not model:
            raise ConfigError(f"{prefix}MODEL is required when the slot is enabled")
        slots.append(ModelSlot(
            slot=number,
            model=model,
            label=_optional(env, prefix + "LABEL") or (model or f"slot {number} (empty)"),
            enabled=enabled,
            max_output_tokens=_integer(env, prefix + "MAX_OUTPUT_TOKENS", default_tokens, minimum=256, maximum=8000),
            reasoning_effort=effort.lower() if effort else None,
            engine=engine,
        ))
    return tuple(slots)


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
    slots: tuple[ModelSlot, ...] = ()
    default_slot: int = 1
    fetch_timeout_seconds: int = 20
    fetch_max_bytes: int = 5_000_000
    fetch_max_redirects: int = 3
    fetch_max_pdf_pages: int = 60
    fetch_max_characters: int = 200_000
    fetch_model_characters: int = 60_000
    fetch_max_quotes: int = 8
    classifier_slot: int = 1
    classifier_check_slot: int = 0
    classifier_workers: int = 4
    rubric_material_pct: float = 20.0
    rubric_critical_pct: float = 50.0
    event_store_url: str | None = field(default=None, repr=False)
    openrouter_total_seconds: int = 180
    classifier_max_output_tokens: int = 3000
    classify_deadline_seconds: int = 420
    stale_running_seconds: int = 1800
    classifier_batch_size: int = 6
    date_lookup_max: int = 15
    classifier_reasoning_effort: str | None = "off"
    ask_retention_days: int = 30
    ask_max_sources: int = 500

    def slot(self, number: int | None) -> ModelSlot:
        wanted = number or self.default_slot
        for candidate in self.slots:
            if candidate.slot == wanted:
                return candidate
        raise KeyError(wanted)

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
        if engine not in ENGINES:
            raise ConfigError("WEB_OPENROUTER_ENGINE is not supported")
        model = env.get("WEB_OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash").strip()
        max_output_tokens = _integer(env, "WEB_OPENROUTER_MAX_OUTPUT_TOKENS", 1800, maximum=8000)

        settings = cls(
            api_key=api_key,
            provider=provider,
            store_path=env.get("WEB_GOVERNOR_STORE_PATH", "/data/web-governor.sqlite3").strip(),
            openrouter_api_key=openrouter_api_key,
            openrouter_base_url=env.get("WEB_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            openrouter_model=model,
            openrouter_engine=engine,
            openrouter_timeout_seconds=_integer(env, "WEB_OPENROUTER_TIMEOUT_SECONDS", 40, maximum=120),
            openrouter_max_retries=_integer(env, "WEB_OPENROUTER_MAX_RETRIES", 3, minimum=1, maximum=5),
            max_criteria=_integer(env, "WEB_MAX_CRITERIA", 6, maximum=8),
            max_searches=_integer(env, "WEB_MAX_SEARCHES", 6, maximum=8),
            max_results_per_search=_integer(env, "WEB_MAX_RESULTS_PER_SEARCH", 5, maximum=30),
            max_evidence_items=_integer(env, "WEB_MAX_EVIDENCE_ITEMS", 20, maximum=40),
            max_output_characters=_integer(env, "WEB_MAX_OUTPUT_CHARACTERS", 32000, maximum=64000),
            max_excerpt_characters=_integer(env, "WEB_MAX_EXCERPT_CHARACTERS", 2500, maximum=5000),
            max_output_tokens=max_output_tokens,
            retention_hours=_integer(env, "WEB_RETENTION_HOURS", 168, maximum=720),
            cleanup_interval_seconds=_integer(
                env, "WEB_CLEANUP_INTERVAL_SECONDS", 3600, minimum=0, maximum=86400
            ),
            app_url=_optional(env, "WEB_GOVERNOR_APP_URL"),
            slots=_slots(env, model, max_output_tokens, engine),
            default_slot=_integer(env, "WEB_DEFAULT_SLOT", 1, maximum=MODEL_SLOT_COUNT),
            fetch_timeout_seconds=_integer(env, "WEB_FETCH_TIMEOUT_SECONDS", 20, maximum=60),
            fetch_max_bytes=_integer(env, "WEB_FETCH_MAX_BYTES", 5_000_000, minimum=10_000, maximum=20_000_000),
            fetch_max_redirects=_integer(env, "WEB_FETCH_MAX_REDIRECTS", 3, minimum=0, maximum=5),
            fetch_max_pdf_pages=_integer(env, "WEB_FETCH_MAX_PDF_PAGES", 60, maximum=300),
            fetch_max_characters=_integer(env, "WEB_FETCH_MAX_CHARACTERS", 200_000, minimum=1000, maximum=1_000_000),
            fetch_model_characters=_integer(env, "WEB_FETCH_MODEL_CHARACTERS", 60_000, minimum=1000, maximum=400_000),
            fetch_max_quotes=_integer(env, "WEB_FETCH_MAX_QUOTES", 8, maximum=20),
            classifier_slot=_integer(env, "WEB_CLASSIFIER_SLOT", 1, maximum=MODEL_SLOT_COUNT),
            classifier_check_slot=_integer(env, "WEB_CLASSIFIER_CHECK_SLOT", 0, minimum=0, maximum=MODEL_SLOT_COUNT),
            classifier_workers=_integer(env, "WEB_CLASSIFIER_WORKERS", 4, maximum=8),
            rubric_material_pct=float(_integer(env, "WEB_RUBRIC_MATERIAL_PCT", 20, maximum=100)),
            rubric_critical_pct=float(_integer(env, "WEB_RUBRIC_CRITICAL_PCT", 50, maximum=100)),
            event_store_url=_optional(env, "WEB_EVENT_STORE_URL"),
            openrouter_total_seconds=_integer(env, "WEB_OPENROUTER_TOTAL_SECONDS", 180, maximum=900),
            classifier_max_output_tokens=_integer(env, "WEB_CLASSIFIER_MAX_OUTPUT_TOKENS", 3000, minimum=256,
                                                  maximum=8000),
            classify_deadline_seconds=_integer(env, "WEB_CLASSIFY_DEADLINE_SECONDS", 420, maximum=1800),
            stale_running_seconds=_integer(env, "WEB_STALE_RUNNING_SECONDS", 1800, minimum=60, maximum=86400),
            classifier_batch_size=_integer(env, "WEB_CLASSIFIER_BATCH_SIZE", 6, maximum=20),
            date_lookup_max=_integer(env, "WEB_DATE_LOOKUP_MAX", 15, minimum=0, maximum=50),
            classifier_reasoning_effort=_effort(env.get("WEB_CLASSIFIER_REASONING_EFFORT", "off")),
            ask_retention_days=_integer(env, "WEB_ASK_RETENTION_DAYS", 30, maximum=365),
            ask_max_sources=_integer(env, "WEB_ASK_MAX_SOURCES", 500, minimum=20, maximum=1000),
        )
        if not settings.store_path:
            raise ConfigError("WEB_GOVERNOR_STORE_PATH must not be empty")
        if not settings.openrouter_model:
            raise ConfigError("WEB_OPENROUTER_MODEL must not be empty")
        if settings.max_searches < settings.max_criteria:
            raise ConfigError("WEB_MAX_SEARCHES must be at least WEB_MAX_CRITERIA")
        if not settings.slot(settings.default_slot).enabled:
            raise ConfigError("WEB_DEFAULT_SLOT must name an enabled slot")
        if not settings.slot(settings.classifier_slot).enabled:
            raise ConfigError("WEB_CLASSIFIER_SLOT must name an enabled slot")
        if settings.classifier_check_slot and not settings.slot(settings.classifier_check_slot).enabled:
            raise ConfigError("WEB_CLASSIFIER_CHECK_SLOT must name an enabled slot or be 0")
        if settings.rubric_material_pct >= settings.rubric_critical_pct:
            raise ConfigError("WEB_RUBRIC_MATERIAL_PCT must be below WEB_RUBRIC_CRITICAL_PCT")
        return settings
