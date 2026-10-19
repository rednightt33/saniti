"""EXEC-ORC-BUDGET: resolve the executor's token contract once, retaining the caller's model and level.

The combined limit includes reasoning. Effort/on-off providers offer no guaranteed reservation for the answer.
Only a model with an explicit supported numeric budget sends reasoning.max_tokens; this is not a hard answer cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model_choices import ModelChoice

POLICY_VERSION = "orc-budget-v1"


@dataclass(frozen=True)
class ExecutionBudget:
    model: str
    level: str
    total_tokens: int
    reasoning_items: tuple[tuple[str, Any], ...]
    presentation_target_tokens: int

    @property
    def reasoning(self) -> dict[str, Any]:
        return dict(self.reasoning_items)

    def metadata(self) -> dict[str, Any]:
        numeric = self.reasoning.get("max_tokens")
        return {"version": POLICY_VERSION, "mode": "numeric_reasoning" if numeric is not None else "shared",
                "total_output_tokens": self.total_tokens, "reasoning_max_tokens": numeric,
                "presentation_target_tokens": self.presentation_target_tokens,
                "minimum_non_reasoning_capacity": max(self.total_tokens - numeric, 0) if numeric is not None else None,
                "split_guaranteed": False, "hard_answer_cap": False}


def resolve(choice: ModelChoice | None, settings: Any) -> ExecutionBudget:
    model = choice.model if choice is not None else settings.ai_model
    level = choice.level if choice is not None and choice.chosen else settings.ai_reasoning_effort
    reasoning = dict(choice.reasoning) if choice is not None else settings.reasoning(settings.ai_reasoning_effort)
    if "max_tokens" in reasoning and reasoning["max_tokens"] > settings.ai_max_output_tokens:
        raise ValueError("numeric reasoning budget exceeds the combined output limit")
    return ExecutionBudget(model, str(level), settings.ai_max_output_tokens, tuple(reasoning.items()),
                           settings.ai_max_presentation_tokens)
