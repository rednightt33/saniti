"""Research Plan continuation kept by the server (history_mode SERVER; implementation plan 2026-09-27, phase H2).

With the conversation store the caller no longer keeps the plan and token of a RESEARCH_PLAN_CONFIRMATION response.
The conversation state ("AI_conversation".state, key research_plan) keeps the latest plan the backend issued in the
conversation: its id, origin request, token, expiry, the exact plan and a status. The signer, the reply classifier and
the ResearchGuard are unchanged; this module only decides which continuation the orchestrator receives and how the
state moves after a turn.

- A turn with a PENDING, unexpired latest plan gets that plan as its continuation. Without plan_reply the existing
  classifier reads the reply (APPROVE, REVISE, CANCEL, UNRELATED; any doubt approves nothing). An expired plan is not
  attached to a free-text message (it would force every later message into re-planning); an explicit plan_reply to
  it is attached, so the orchestrator's expired-approval path presents the plan again.
- plan_reply {plan_id, action, revision_instruction} must name the latest plan while it is PENDING. A superseded,
  cancelled or executed plan is refused even when its token has not expired: the server knows the plan's state,
  which a stateless token cannot express (CLIENT mode keeps that documented limit).
- A newly issued plan (a first proposal, a revision, a re-plan) replaces the latest plan; the previous one becomes
  SUPERSEDED. A CANCEL turn marks it CANCELLED. An EXECUTE_APPROVED turn that submitted a RESEARCH data need marks it
  EXECUTED whatever the outcome (one that submitted none leaves it PENDING, M19): an
  approval is used once and a new approval never re-runs the experiments by itself (a retry of the same request_id is
  answered from the stored response). A later computation needs a new or revised plan and a new approval. An UNRELATED
  turn returns the same continuation (same token and expiry), so the plan stays PENDING and is never extended.
- A research_plan/v2 (Multi-Angle Research) is stored with the research data plan its rpc2 token binds; its
  continuation carries both back.
- The model never sees or produces any of this; the token is never logged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .research_plan import ContinuationIn, parse_plan
from .research_plan_v2 import PLAN_VERSION_V2, ContinuationInV2, ResearchPlanV2
from .schemas import AgentRunRequest, AgentRunResponse

STATE_KEY = "research_plan"
HISTORY_KEY = "earlier_plans"
MAX_EARLIER_PLANS = 10
PENDING, SUPERSEDED, CANCELLED, EXECUTED = "PENDING", "SUPERSEDED", "CANCELLED", "EXECUTED"


class PlanReplyError(Exception):
    """plan_reply refused before the turn starts: code, message, HTTP status."""

    def __init__(self, code: str, message: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _expired(plan: dict[str, Any], now: datetime) -> bool:
    try:
        return datetime.fromisoformat(plan["expires_at"]) <= now
    except (KeyError, TypeError, ValueError):
        return True


def summary(state: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any] | None:
    """What the caller sees of the latest plan (never the token): plan_id, status, expires_at."""
    plan = (state or {}).get(STATE_KEY)
    if not isinstance(plan, dict):
        return None
    status = plan.get("status")
    if status == PENDING and _expired(plan, now or datetime.now(timezone.utc)):
        status = "EXPIRED"
    return {"plan_id": plan.get("plan_id"), "status": status, "expires_at": plan.get("expires_at")}


def continuation_for(state: dict[str, Any] | None, request: AgentRunRequest,
                     now: datetime | None = None) -> ContinuationIn | ContinuationInV2 | None:
    """The continuation this SERVER turn runs with, or None. Raises PlanReplyError for a plan_reply that does not name
    the latest pending plan."""
    now = now or datetime.now(timezone.utc)
    plan = (state or {}).get(STATE_KEY)
    plan = plan if isinstance(plan, dict) else None
    reply = request.plan_reply
    if reply is not None:
        if plan is None:
            earlier = next((p for p in (state or {}).get(HISTORY_KEY) or [] if p.get("plan_id") == reply.plan_id),
                           None)
            if earlier is None:
                raise PlanReplyError("RESEARCH_PLAN_NOT_FOUND", "This conversation has no Research Plan with this "
                                     "plan_id.", 404)
            raise PlanReplyError("RESEARCH_PLAN_NOT_PENDING", f"This Research Plan is {earlier.get('status')}; ask a "
                                 "new question or reply to the latest plan.")
        if plan.get("plan_id") != reply.plan_id:
            earlier = next((p for p in (state or {}).get(HISTORY_KEY) or [] if p.get("plan_id") == reply.plan_id),
                           None)
            if earlier is None:
                raise PlanReplyError("RESEARCH_PLAN_NOT_FOUND", "This conversation has no Research Plan with this "
                                     "plan_id.", 404)
            raise PlanReplyError("RESEARCH_PLAN_STALE", f"This Research Plan was {earlier.get('status')}; the latest "
                                 f"plan is {plan.get('plan_id')}. Reply to the latest plan.")
        if plan.get("status") != PENDING:
            raise PlanReplyError("RESEARCH_PLAN_NOT_PENDING", f"This Research Plan is {plan.get('status')}; an "
                                 "approval is used once. Ask for a new or revised plan.")
        return _continuation(plan, reply.action, reply.revision_instruction)
    if plan is None or plan.get("status") != PENDING or _expired(plan, now):
        return None
    return _continuation(plan, None, None)


def _continuation(plan: dict[str, Any], action: str | None,
                  instruction: str | None) -> ContinuationIn | ContinuationInV2:
    if (plan.get("plan") or {}).get("plan_version") == PLAN_VERSION_V2:
        return ContinuationInV2(kind="RESEARCH_PLAN", plan_id=plan["plan_id"],
                                origin_request_id=plan["origin_request_id"],
                                plan=ResearchPlanV2.model_validate(plan["plan"]),
                                research_data_plan=plan.get("research_data_plan") or {}, token=plan["token"],
                                action=action, revision_instruction=instruction)
    return ContinuationIn(kind="RESEARCH_PLAN", plan_id=plan["plan_id"], origin_request_id=plan["origin_request_id"],
                          plan=parse_plan(plan["plan"]), token=plan["token"], action=action,
                          revision_instruction=instruction)


def advance(state: dict[str, Any] | None, result: AgentRunResponse, request_id: str,
            turn_index: int) -> dict[str, Any]:
    """The conversation state after a stored turn."""
    state = dict(state or {})
    plan = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), dict) else None
    execution = result.execution.research_plan if result.execution else None
    if execution is None:
        return state
    issued = result.continuation
    response = result.response
    if issued is not None and response is not None and response.response_type == "RESEARCH_PLAN_CONFIRMATION" \
            and response.research_plan is not None and issued.plan_id == execution.issued_plan_id:
        if plan is not None and plan.get("plan_id") != issued.plan_id:
            _retire(state, plan, SUPERSEDED if plan.get("status") == PENDING else plan.get("status"), request_id)
        state[STATE_KEY] = {"plan_id": issued.plan_id, "status": PENDING, "origin_request_id":
                            issued.origin_request_id, "conversation_id": issued.conversation_id, "token": issued.token,
                            "expires_at": issued.expires_at, "issued_turn_index": turn_index,
                            "plan": response.research_plan.model_dump(mode="json")}
        data_plan = getattr(issued, "research_data_plan", None)
        if data_plan is not None:
            state[STATE_KEY]["research_data_plan"] = data_plan
        return state
    if plan is None or plan.get("status") != PENDING:
        return state
    if execution.turn == "EXECUTE_APPROVED" and execution.approved_plan_id == plan.get("plan_id") \
            and execution.research_submitted is not False:  # M19: an approval without any attempt stays pending
        state[STATE_KEY] = {**plan, "status": EXECUTED, "executed_request_id": request_id,
                            "executed_turn_index": turn_index, "run_status": result.status}
    elif execution.turn == "CANCEL":
        state[STATE_KEY] = {**plan, "status": CANCELLED, "closed_request_id": request_id}
    return state


def _retire(state: dict[str, Any], plan: dict[str, Any], status: str | None, request_id: str) -> None:
    earlier = [p for p in state.get(HISTORY_KEY) or [] if isinstance(p, dict)]
    earlier.append({"plan_id": plan.get("plan_id"), "status": status, "closed_request_id": request_id})
    state[HISTORY_KEY] = earlier[-MAX_EARLIER_PLANS:]
