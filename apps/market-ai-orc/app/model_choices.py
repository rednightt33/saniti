"""EXEC-MODELS (user 2026-10-13, "kita akan menambahkan model2 ini bisa di toggle model dan intellegence level di
EDGE (Default router tetap low)"; "Ok, go defaultnya adalah deepseek V4.1 flash HIGH ya"): the models a caller may
choose for one message, and the reasoning levels each takes on OpenRouter.

A choice applies to the step that does the work (every call of the agent loop, mode 4 steps included). The routers,
the follow-up suggestions and the small checks keep AI_MODEL with reasoning low. Without a choice a run uses AI_MODEL
(AI_MODEL_SWITCH) and AI_REASONING_EFFORT as before; EDGE starts on deepseek/deepseek-v4.1-flash high (EDGE_DEFAULT),
the server default stays as configured. A model takes reasoning either as a level (effort: low, medium, high) or as on
and off (enabled), as OpenRouter lists its supported parameters (2026-10-13: reasoning_effort for DeepSeek and GLM,
reasoning only for MiMo and Qwen).
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

EFFORT_LEVELS = ("low", "medium", "high")
SWITCH_LEVELS = ("off", "on")


@dataclass(frozen=True)
class ModelOption:
    model: str
    label: str
    form: str  # "effort" or "enabled"

    @property
    def levels(self) -> tuple[str, ...]:
        return EFFORT_LEVELS if self.form == "effort" else SWITCH_LEVELS


MODEL_CHOICES: tuple[ModelOption, ...] = (
    ModelOption("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "effort"),
    ModelOption("z-ai/glm-5.3-flash", "GLM 5.3 Flash", "effort"),
    ModelOption("xiaomi/mimo-v2.6-pro", "MiMo V2.6 Pro", "enabled"),
    ModelOption("xiaomi/mimo-v2.6-flash", "MiMo V2.6 Flash", "enabled"),
    ModelOption("qwen/qwen3.8-flash", "Qwen3.8 Flash", "enabled"),
)
BY_MODEL = {option.model: option for option in MODEL_CHOICES}
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


# set by the API around one request (mode 4 steps run in the same context and inherit it)
current_model_choice: contextvars.ContextVar[ModelChoice | None] = contextvars.ContextVar("current_model_choice",
                                                                                          default=None)


def reasoning_for(option: ModelOption, level: str) -> dict[str, Any]:
    """The OpenRouter reasoning setting of a level in the form the model accepts."""
    return {"effort": level} if option.form == "effort" else {"enabled": level == "on"}


def resolve(model: str | None, level: str | None, settings: Any) -> ModelChoice:
    """A caller's choice checked against MODEL_CHOICES, or the server default when neither is given. A level without a
    model applies to the server's model when that model takes it."""
    if model is None and level is None:
        return ModelChoice(settings.ai_model, settings.reasoning(settings.ai_reasoning_effort), None, False)
    name = model or settings.ai_model
    option = BY_MODEL.get(name)
    if option is None:
        raise ModelChoiceError("MODEL_NOT_ALLOWED", f"model {name} is not offered; the models are "
                               + ", ".join(o.model for o in MODEL_CHOICES) + ".")
    if level is None:
        level = EDGE_DEFAULT["reasoning_level"] if option.form == "effort" else "on"
    if level not in option.levels:
        raise ModelChoiceError("REASONING_LEVEL_NOT_SUPPORTED", f"{option.model} takes the reasoning levels "
                               + ", ".join(option.levels) + f"; {level} is not one of them.")
    return ModelChoice(option.model, reasoning_for(option, level), level, True)
