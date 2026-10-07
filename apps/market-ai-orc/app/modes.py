"""Mode switcher (user decision 2026-09-30): which mode answers a request.

Modes: 1 AUTO (the model chooses ANALYSIS or RESEARCH, the behaviour before mode 4), 2 ANALYSIS, 3 RESEARCH,
4 MODE4 (app/mode4.py). A request chooses one with analysis_path ("AUTO", "ANALYSIS", "RESEARCH", "MODE4"); otherwise
a reply to a pending Research Plan continues in the mode its plan was issued in (a plan of any mode 4 step in MODE4,
any other plan in AUTO, which reads approvals); otherwise AI_MODE_SWITCH decides. A default the deployment cannot run
(mode 4 or the paths inactive at startup) falls back to AUTO, logged at startup."""
from __future__ import annotations

import contextvars
from typing import Any

MODES = {1: "AUTO", 2: "ANALYSIS", 3: "RESEARCH", 4: "MODE4"}
# the analysis_path the caller itself sent (None when the mode came from AI_MODE_SWITCH or a plan): a later turn reaches
# mode 4 with the switch's MODE4, which is not the caller's depth for a re-routed new topic (AI_ROUTER.md)
current_caller_path: contextvars.ContextVar[str | None] = contextvars.ContextVar("caller_path", default=None)
NUMBERS = {name: number for number, name in MODES.items()}
# app/mode4.py: the request_id suffixes of the steps that issue plans: B (the first round's plan, which waits for the
# user since EXEC-P1), C (a revised plan), D (a suggestion) and a later turn's CONTINUE step. M105 (golden test
# 2026-10-07): with step D alone, a reply to step B's plan ran in AUTO and never reached mode 4's turn router
MODE4_PLAN_SUFFIXES = ("-m4b", "-m4c", "-m4d", "-m4n")


def is_mode4_plan(continuation: Any) -> bool:
    """A continuation issued by a mode 4 step (its origin request id is bound by the signed token)."""
    origin = getattr(continuation, "origin_request_id", None)
    return isinstance(origin, str) and origin.endswith(MODE4_PLAN_SUFFIXES)


def available(orchestrator: Any) -> set[int]:
    """The modes this deployment can run."""
    modes = {1}
    if getattr(orchestrator, "analysis_path", False):
        modes |= {2, 3}
    if getattr(orchestrator, "mode4", False):
        modes.add(4)
    return modes


def effective_default(switch: int, orchestrator: Any) -> int:
    """AI_MODE_SWITCH, or AUTO when the deployment cannot run that mode."""
    return switch if switch in available(orchestrator) else 1


def resolve_mode(requested: str | None, continuation: Any, default: int) -> tuple[int, str]:
    """(mode number, source): the caller's analysis_path, else the mode of the plan being replied to, else the
    deployment's default."""
    if requested is not None:
        return NUMBERS[requested], "CALLER"
    if continuation is not None:
        return (4 if is_mode4_plan(continuation) else 1), "CONTINUATION"
    return default, "SWITCH"


def path_for(mode: int) -> str | None:
    """The analysis_path the orchestrator receives for a mode (AUTO: none)."""
    return None if mode == 1 else MODES[mode]
