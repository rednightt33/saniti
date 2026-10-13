"""EXEC-FASTLANE (user 2026-10-13: "Jangan sampai merubah cara research bekerja. Retain existing condition, kita buat
jalur baru saja untuk nanti A/B test"; "harus selalu ada fallback"): the lane of one message.

STANDARD is the current behaviour and the fallback: with AI_ENABLE_FASTLANE off, or a message that names no lane or
the standard one, nothing differs from before. FAST (only with the switch on) answers a data question in one turn:
the analysis step runs on the FASTLANE desk with the lane note (no Research Plan, no approval, results labelled
exploratory), the calls after the first one think at a lower level, a call is cut at FAST_CALL_SECONDS and asked
again once with lower reasoning, and a data request too large for one extraction is told how much would fit.
"""
from __future__ import annotations

import contextvars
from typing import Any

STANDARD, FAST = "standard", "fast"
LANES = (STANDARD, FAST)
FAST_CALL_SECONDS = 90.0  # R4: a longer call is cut and asked again once with lower reasoning

# set by the API around one request (mode 4 steps run in the same context and inherit it)
current_lane: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_lane", default=None)


class LaneError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve(lane: str | None, settings: Any) -> str | None:
    """The lane of a message: None (no lane named: the current behaviour), STANDARD, or FAST when switched on."""
    if lane is None or lane == STANDARD:
        return lane
    if lane == FAST and not getattr(settings, "ai_enable_fastlane", False):
        raise LaneError("LANE_NOT_AVAILABLE", "the fast lane is not switched on (AI_ENABLE_FASTLANE).")
    if lane not in LANES:
        raise LaneError("LANE_NOT_AVAILABLE", f"lane {lane} is not one of {', '.join(LANES)}.")
    return lane


def is_fast() -> bool:
    return current_lane.get() == FAST
