"""EXEC-MODELS (user 2026-10-13, "kita akan menambahkan model2 ini bisa di toggle model dan intellegence level di
EDGE (Default router tetap low)"; "Ok, go defaultnya adalah deepseek V4.1 flash HIGH ya"): the models a caller may
choose for one message, and the reasoning levels each takes on OpenRouter.

A choice applies to the step that does the work (every call of the agent loop, mode 4 steps included). The routers,
the follow-up suggestions and the small checks keep AI_MODEL with reasoning low. Without a choice a run uses AI_MODEL
(AI_MODEL_SWITCH) and AI_REASONING_EFFORT as before; EDGE starts on deepseek/deepseek-v4.1-flash high (EDGE_DEFAULT),
the server default stays as configured. A model takes reasoning either as a level (effort) or as on and off (enabled),
as OpenRouter lists its supported parameters (2026-10-13: reasoning_effort for DeepSeek and GLM, reasoning only for
MiMo and Qwen).

EXEC-LOGOS (user 2026-10-13, levels "Rendah / Tinggi / Maks"; "Keluarin saja Mimo pro ya, the rest sudah OK"): the
levels are the ones OpenRouter lists for DeepSeek and GLM (supported_efforts max, high, low). MiMo V2.6 Pro is no longer
offered (M150: request edge_7bc93daf… spent 405 s and 23,999 reasoning tokens on one call with no output). A model with
on and off keeps its thinking bounded: MiMo Flash "on" by a lower output cap per call (the cap includes reasoning, and
MiMo takes no reasoning budget), Qwen "on" by a reasoning budget (reasoning.max_tokens, supports_max_tokens).
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

EFFORT_LEVELS = ("low", "high", "max")  # OpenRouter supported_efforts of DeepSeek and GLM
SWITCH_LEVELS = ("off", "on")


@dataclass(frozen=True)
class ModelOption:
    model: str
    label: str
    form: str  # "effort" or "enabled"
    output_cap: int | None = None  # max_output_tokens per call when reasoning is on (lower than AI_MAX_OUTPUT_TOKENS)
    reasoning_budget: int | None = None  # reasoning.max_tokens when on

    @property
    def levels(self) -> tuple[str, ...]:
        return EFFORT_LEVELS if self.form == "effort" else SWITCH_LEVELS


MODEL_CHOICES: tuple[ModelOption, ...] = (
    ModelOption("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "effort"),
    # EXEC-SHARE-UI (user 2026-10-19: "DeepSeek: DeepSeek V4.1 Flash 1017"); low, high and max each accepted by
    # OpenRouter on 2026-10-19 (one small call per level, reasoning tokens 18, 29, 36)
    ModelOption("deepseek/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash 1017", "effort"),
    ModelOption("z-ai/glm-5.3-flash", "GLM 5.3 Flash", "effort"),
    ModelOption("xiaomi/mimo-v2.6-flash", "MiMo V2.6 Flash", "enabled", output_cap=12000),
    ModelOption("qwen/qwen3.8-flash", "Qwen3.8 Flash", "enabled", reasoning_budget=8000),
)
BY_MODEL = {option.model: option for option in MODEL_CHOICES}
# EXEC-MANUAL (user 2026-10-17): Claude answers as the model, offered only with AI_ENABLE_MANUAL_AGENT (troubleshooting)
MANUAL_OPTION = ModelOption("saniti/claude-manual", "Claude (manual)", "enabled")


def offered(settings: Any) -> tuple[ModelOption, ...]:
    """The models a message may choose now: MODEL_CHOICES, and the manual option when its switch is on."""
    return MODEL_CHOICES + ((MANUAL_OPTION,) if getattr(settings, "ai_enable_manual_agent", False) else ())
EDGE_DEFAULT = {"model": "deepseek/deepseek-v4.1-flash", "reasoning_level": "high"}


class ModelChoiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelChoice:
    """The model and reasoning of one run's agent loop. chosen: the caller picked them (else the server default)."""
    model: str
    reasoning: dict[str, Any]
    level: str | None
    chosen: bool
    output_cap: int | None = None  # the output cap of each loop call when lower than AI_MAX_OUTPUT_TOKENS
    lowered: dict[str, Any] | None = None  # the reasoning of one call after a runaway (orchestrator, M150)


# set by the API around one request (mode 4 steps run in the same context and inherit it)
current_model_choice: contextvars.ContextVar[ModelChoice | None] = contextvars.ContextVar("current_model_choice",
                                                                                          default=None)


def reasoning_for(option: ModelOption, level: str, budget: int | None = None) -> dict[str, Any]:
    """The OpenRouter reasoning setting of a level in the form the model accepts. budget (AI_MAX_REASONING_TOKENS)
    replaces the option's own reasoning budget."""
    if option.form == "effort":
        return {"effort": level}
    if level == "on" and option.reasoning_budget:
        # enabled is implied; OpenRouter takes effort or max_tokens
        return {"max_tokens": budget or option.reasoning_budget}
    return {"enabled": level == "on"}


def lowered_reasoning(option: ModelOption | None, settings: Any) -> dict[str, Any]:
    """M150: the reasoning of the one call after a runaway: off for a model with on and off, low for a model with levels
    (GLM cannot turn it off), and low for the server default."""
    if option is not None and option.form == "enabled":
        return {"enabled": False}
    if option is not None:
        return {"effort": "low"}
    return settings.reasoning("low")


def resolve(model: str | None, level: str | None, settings: Any) -> ModelChoice:
    """A caller's choice checked against MODEL_CHOICES, or the server default when neither is given. A level without a
    model applies to the server's model when that model takes it."""
    if model is None and level is None:
        return ModelChoice(settings.ai_model, settings.reasoning(settings.ai_reasoning_effort), None, False,
                           lowered=lowered_reasoning(BY_MODEL.get(settings.ai_model), settings))
    name = model or settings.ai_model
    option = next((o for o in offered(settings) if o.model == name), None)
    if option is None:
        raise ModelChoiceError("MODEL_NOT_ALLOWED", f"model {name} is not offered; the models are "
                               + ", ".join(o.model for o in offered(settings)) + ".")
    if level is None:
        level = EDGE_DEFAULT["reasoning_level"] if option.form == "effort" else "on"
    if level not in option.levels:
        raise ModelChoiceError("REASONING_LEVEL_NOT_SUPPORTED", f"{option.model} takes the reasoning levels "
                               + ", ".join(option.levels) + f"; {level} is not one of them.")
    cap = option.output_cap if level == "on" and option.output_cap else None
    budget = getattr(settings, "ai_max_reasoning_tokens", None)
    return ModelChoice(option.model, reasoning_for(option, level, budget), level, True, output_cap=cap,
                       lowered=lowered_reasoning(option, settings))
