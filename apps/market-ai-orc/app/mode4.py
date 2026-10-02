"""Mode 4 (user decision 2026-09-30): answer first, then research that tests the answer, then one suggestion.

A request without analysis_path (or with MODE4) runs as a pipeline of ordinary orchestrator runs; every sub-run keeps
all of its gates (provenance, value references, findings, claims, audit) and has its own request_id
(<request_id>-m4a, -m4b, ...), so the audit store and the logs show each step.

First round (no pending plan):
  A  analysis     forced_path ANALYSIS: the direct answer to the question.
  B  research plan forced_path RESEARCH, at least two angles, built on A's answer (the angles test or deepen it).
  C  execution    B's plan, approved by the backend at once (its rpc2 token is signed and verified as usual).
  D  suggestion   forced_path RESEARCH, exactly one angle (or the count the user asked for), following up on A and C;
                  its plan is returned for the user's confirmation (status AWAITING_CONFIRMATION).
Follow-up round (the reply to D's suggestion, read by the existing reply classifier):
  APPROVE    the suggestion runs, then a new D.
  REVISE     the suggestion is revised and returned for confirmation (the user's angle count applies).
  CANCEL     acknowledged; nothing runs.
  UNRELATED  a new question (decision C): the suggestion is cancelled and the message starts a new first round.
With AI_ENABLE_CONVERSATION_ROUTER (4d, user decision 2026-10-02) every later turn, with or without a pending
suggestion, is read by the conversation router (app/conversation_router.py) instead: CLARIFY and CONVERSATIONAL answer
from the conversation without data tools, INSIGHT runs one analysis step, CONTINUE one free step (any of G1-G4, plans
for the user's approval), APPROVE / REVISE / CANCEL act on the pending suggestion as above, NEW_TOPIC starts a new
first round. Only CONTINUE, APPROVE and NEW_TOPIC can start research; a pending suggestion survives the other classes.

A failed step degrades the answer instead of failing it: without A nothing else runs; without B or C the answer
keeps the analysis and a note; without D the answer has no suggestion and says why. AI_MODE4_MAX_SECONDS bounds the
whole request (each sub-run also keeps AI_MAX_ANALYSIS_SECONDS). The combined response keeps the public shape: answer
has three titled sections, status is AWAITING_CONFIRMATION when a suggestion is pending, continuation is D's, and
the mode4 block lists the steps.
"""
from __future__ import annotations

import re
from typing import Any

from . import conversation_router as router
from .orchestrator import AgentOrchestrator, current_time_budget, log_event
from .provenance import LABEL_ORDER
from .research_plan_v2 import ContinuationInV2, ContinuationOutV2, current_angle_bounds, plan_digest_v2
from .schemas import (MAX_HISTORY_ITEMS, MAX_MESSAGE_CHARACTERS, AgentRunRequest, AgentRunResponse,
                      AnalysisPathExecution, HistoryMessage, ReplyClassifierUsage)

MODE4_VERSION = 1
MIN_STEP_SECONDS = 120  # a step is not started with less time left than this
APPROVAL_MESSAGE = "Setuju, jalankan rencana ini."
PENDING_LINE = "Usulan riset sebelumnya masih menunggu keputusan Anda; balas \"jalankan\" kapan saja untuk menjalankannya."
STEP_SUFFIX = {"CLARIFY": "m4q", "CONVERSATIONAL": "m4q", "INSIGHT": "m4i", "CONTINUE": "m4n"}
ANALYSIS_CHARS, RESEARCH_CHARS = 5000, 6000
NUMBER_WORDS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
SUGGESTION_WORDS = ("opsi", "pilihan", "usulan", "saran", "option", "suggestion", "alternatif")
COUNT_RE = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s+(?:buah\s+|more\s+|new\s+)?"
                      r"(angles?|sudut|hipotesis|hypothes[ie]s|opsi|pilihan|usulan|saran|options?|suggestions?"
                      r"|alternatif)\b", re.IGNORECASE)

B_CONTEXT = ("Application context (mode 4), not from the user: the question above was already answered by the "
             "descriptive analysis below, which the user has received.\n<analysis>\n{analysis}\n</analysis>\n"
             "Propose a Research Plan whose angles test or deepen what this analysis found: for example whether the "
             "pattern is real and larger than chance, stable over time and across groups, or explained by something "
             "else. Do not repeat the analysis itself.")
D_CONTEXT = ("Application context (mode 4), not from the user: the user has received the results below.\n"
             "{analysis}<research>\n{research}\n</research>\n"
             "These angles already ran: {ran}.\nPropose a Research Plan with exactly {count} new angle{plural} that "
             "follow{verb} up on these results (what they leave open, a condition to test, a different group or "
             "period). Do not repeat an angle that already ran. It is a suggestion: the user decides whether it "
             "runs.")


def requested_count(message: str) -> tuple[str, int] | None:
    """An explicit count in the user's message ("cari 2 angle lain", "kasih tiga opsi"): (ANGLE or SUGGESTION, 1-6),
    or None."""
    match = COUNT_RE.search(message or "")
    if match is None:
        return None
    raw, noun = match.group(1).lower(), match.group(2).lower()
    count = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
    kind = "SUGGESTION" if noun.startswith(SUGGESTION_WORDS) else "ANGLE"
    return kind, min(max(count, 1), 6)


def _weakest(labels: list[str | None]) -> str | None:
    known = [label for label in labels if label in LABEL_ORDER]
    return max(known, key=LABEL_ORDER.index) if known else None


def _merge(*lists: list[str], limit: int = 20) -> list[str]:
    merged: list[str] = []
    for items in lists:
        for item in items or []:
            if item and item not in merged:
                merged.append(item)
    return merged[:limit]


def _ok(result: AgentRunResponse | None, *types: str) -> bool:
    return result is not None and result.status != "FAILED" and result.response is not None \
        and result.response.response_type in types


class Mode4Orchestrator:
    """Wraps AgentOrchestrator: a request with analysis_path MODE4 runs mode 4, every other one goes straight to it.
    Other attributes (analysis_path, conversation_reuse, registry, close, ...) are the inner orchestrator's."""

    mode4 = True
    router = False  # AI_ENABLE_CONVERSATION_ROUTER, set in __init__

    def __init__(self, inner: AgentOrchestrator) -> None:
        self.inner = inner
        limits = inner.research_limits or {}
        self.min_angles, self.max_angles = int(limits.get("min_angles", 2)), int(limits.get("max_angles", 6))
        # the fewest angles the sandbox runs in one plan: a one-angle suggestion needs PY_SANDBOX_RESEARCH_MIN_ANGLES=1
        self.sandbox_min = int(limits.get("sandbox_min_angles") or 2)
        self.router = bool(getattr(inner.settings, "ai_enable_conversation_router", False))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run(self, request: AgentRunRequest, conversation_key: str | None = None,
            data_record: dict[str, Any] | None = None) -> AgentRunResponse:
        """analysis_path MODE4 runs the pipeline; any other request (the mode switcher, app/modes.py, has set its path:
        none for AUTO) goes to the orchestrator unchanged."""
        if request.analysis_path != "MODE4":
            return self.inner.run(request, conversation_key, data_record=data_record)
        return _Mode4Run(self, request, conversation_key, data_record).execute()


class _Mode4Run:
    def __init__(self, owner: Mode4Orchestrator, request: AgentRunRequest, conversation_key: str | None,
                 data_record: dict[str, Any] | None = None) -> None:
        self.owner, self.inner, self.request, self.key = owner, owner.inner, request, conversation_key
        # M47: the data record each step hands to the next (tables, columns, needs, outputs, research data)
        self.record = data_record
        self.settings = owner.inner.settings
        self.started = self.inner.clock()
        self.steps: list[dict[str, Any]] = []
        self.results: list[AgentRunResponse] = []
        self.notes: list[str] = []
        self.classifier: dict[str, Any] | None = None
        self.turn_kind: str | None = None
        self.router_usage: dict[str, Any] | None = None
        self.base_id = request.request_id[:190]

    # ------------------------------------------------------------------------------------------------ plumbing

    def remaining(self) -> float:
        return self.settings.ai_mode4_max_seconds - (self.inner.clock() - self.started)

    def sub(self, step: str, suffix: str, message: str, analysis_path: str | None, *,
            continuation: ContinuationInV2 | None = None, history: list[HistoryMessage] | None = None,
            bounds: tuple[int, int] | None = None, turn_kind: str | None = None) -> AgentRunResponse | None:
        request_id = f"{self.base_id}-{suffix}"
        left = self.remaining()
        if left < MIN_STEP_SECONDS:
            self.steps.append({"step": step, "request_id": request_id, "status": "SKIPPED",
                               "reason": "AI_MODE4_MAX_SECONDS"})
            log_event("mode4_step_skipped", request_id=self.request.request_id, step=step, seconds_left=int(left))
            return None
        history = list(self.request.history if history is None else history)[-MAX_HISTORY_ITEMS:]
        sub_request = AgentRunRequest(request_id=request_id, conversation_id=self.request.conversation_id,
                                      message=message[:MAX_MESSAGE_CHARACTERS], history=history,
                                      metadata=self.request.metadata, continuation=continuation,
                                      analysis_path=analysis_path)
        budget, angle_bounds = current_time_budget.set(left), current_angle_bounds.set(bounds)
        kind = router.current_turn_kind.set(turn_kind)
        try:
            result = self.inner.run(sub_request, self.key, data_record=self.record)
        finally:
            current_time_budget.reset(budget)
            current_angle_bounds.reset(angle_bounds)
            router.current_turn_kind.reset(kind)
        response, execution = result.response, result.execution
        plan_exec = execution.research_plan
        self.steps.append({
            "step": step, "request_id": request_id, "status": result.status,
            "response_type": response.response_type if response else None, "evidence_label": result.evidence_label,
            "turn": plan_exec.turn if plan_exec else None,
            "plan_id": result.continuation.plan_id if result.continuation else None,
            "angles": len(response.research_plan.angles) if response and response.research_plan is not None
            and hasattr(response.research_plan, "angles") else None,
            "error_code": result.error.code if result.error else None, "cost": execution.cost,
            "duration_ms": execution.duration_ms})
        log_event("mode4_step", request_id=self.request.request_id, **{k: v for k, v in self.steps[-1].items()
                                                                          if k != "request_id"},
                  sub_request_id=request_id)
        self.results.append(result)
        if result.data_record:
            self.record = result.data_record
        return result

    # ------------------------------------------------------------------------------------------------ rounds

    def execute(self) -> AgentRunResponse:
        continuation = self.request.continuation
        if continuation is not None and not isinstance(continuation, ContinuationInV2):
            return self.inner.run(self.request, self.key)  # a research_plan/v1 plan: the path it was issued on
        if self.owner.router and (continuation is not None or self.request.history):
            return self.routed(continuation)
        if continuation is None:
            return self.first_round()
        return self.follow_up(continuation)

    def routed(self, continuation: ContinuationInV2 | None) -> AgentRunResponse:
        """4d: a later turn, classified by the conversation router and handled by the backend's rules."""
        pending = continuation is not None
        explicit = continuation.action if pending else None
        if explicit is not None:
            kind, instruction = explicit, continuation.revision_instruction
        else:
            context = router.context(self.record, list(self.request.history),
                                     plan_digest_v2(continuation.plan) if pending else None)
            raw, instruction, self.router_usage = self.inner.classify_turn(f"{self.base_id}-m4r",
                                                                           self.request.message, context)
            kind = router.apply_rules(raw, pending)
        self.turn_kind = kind
        log_event("mode4_turn_routed", request_id=self.request.request_id, turn_kind=kind, pending=pending,
                  source="EXPLICIT" if explicit else "ROUTER")
        if kind in router.NEEDS_PENDING:
            assert continuation is not None
            return self.follow_up(continuation.model_copy(update={
                "action": kind, "revision_instruction": instruction if kind == "REVISE" else None}))
        if kind == "NEW_TOPIC":
            if pending:
                self.notes.append("Usulan riset sebelumnya dibatalkan karena ada pertanyaan baru.")
            return self.first_round(cancelled_plan_id=continuation.plan_id if pending else None)
        result = self.sub(kind.lower(), STEP_SUFFIX[kind], self.request.message,
                          "ANALYSIS" if kind == "INSIGHT" else None, turn_kind=kind)
        if pending and result is not None and result.response is not None \
                and result.response.response_type in ("ANSWER", "LIMITATION"):
            # rule 4: the suggestion is still pending (the conversation store keeps it)
            self.notes.append(PENDING_LINE)
            result = result.model_copy(update={"response": result.response.model_copy(update={
                "limitations": _merge(result.response.limitations, [PENDING_LINE])})})
            self.results[-1] = result
        return self.finish(result, round_=kind, passthrough=True)

    def first_round(self, cancelled_plan_id: str | None = None) -> AgentRunResponse:
        question = self.request.message
        count = requested_count(question)
        analysis = self.sub("analysis", "m4a", question, "ANALYSIS")
        if not _ok(analysis, "ANSWER", "LIMITATION"):
            # M43 (user decision 2026-09-30): a LIMITATION still carries the analysis and its limits, so the research
            # runs on it; a clarification (the user must answer first) or a failure ends the round
            self.notes.append("Riset tidak dijalankan karena analisis tidak menghasilkan jawaban.")
            return self.finish(analysis, round_="FIRST", cancelled_plan_id=cancelled_plan_id)
        assert analysis is not None and analysis.response is not None
        answer = analysis.response.answer
        low = max(2, self.owner.min_angles)
        if count and count[0] == "ANGLE":
            low = min(max(2, count[1]), self.owner.max_angles)
            bounds = (low, low)
        else:
            bounds = (low, self.owner.max_angles)
        plan = self.sub("research_plan", "m4b", question + "\n\n" + B_CONTEXT.format(
            analysis=answer[:ANALYSIS_CHARS]), "RESEARCH", bounds=bounds)
        research = None
        if _ok(plan, "RESEARCH_PLAN_CONFIRMATION") and isinstance(plan.continuation, ContinuationOutV2):
            issued = plan.continuation
            approval = ContinuationInV2(kind="RESEARCH_PLAN", plan_id=issued.plan_id,
                                        origin_request_id=issued.origin_request_id, plan=plan.response.research_plan,
                                        research_data_plan=issued.research_data_plan, token=issued.token,
                                        action="APPROVE")
            history = [*self.request.history, HistoryMessage(role="user", content=question[:MAX_MESSAGE_CHARACTERS]),
                       HistoryMessage(role="assistant", content=answer[:MAX_MESSAGE_CHARACTERS])]
            research = self.sub("research", "m4c", APPROVAL_MESSAGE, None, continuation=approval, history=history)
            if not _ok(research, "ANSWER", "LIMITATION"):
                self.notes.append("Riset tidak dapat diselesaikan: " + self._reason(research))
        else:
            self.notes.append("Riset tidak dijalankan: " + self._reason(plan))
        ran = self._angles(plan.response.research_plan) if _ok(plan, "RESEARCH_PLAN_CONFIRMATION") else []
        wanted = count[1] if count and count[0] == "SUGGESTION" else 1
        suggestion = self.suggest(question, answer, research, ran, wanted)
        return self.finish(analysis, research=research, suggestion=suggestion, round_="FIRST",
                           cancelled_plan_id=cancelled_plan_id)

    def follow_up(self, continuation: ContinuationInV2) -> AgentRunResponse:
        count = requested_count(self.request.message)
        if continuation.action is None:
            action, instruction, self.classifier = self.inner.classify_reply(
                f"{self.base_id}-m4r", self.request.message, continuation.plan)
            if action == "UNRELATED":
                # decision C: a new question instead of a reply cancels the pending suggestion
                log_event("mode4_suggestion_cancelled", request_id=self.request.request_id,
                          plan_id=continuation.plan_id)
                self.notes.append("Usulan riset sebelumnya dibatalkan karena ada pertanyaan baru.")
                return self.first_round(cancelled_plan_id=continuation.plan_id)
            continuation = continuation.model_copy(update={
                "action": action, "revision_instruction": instruction if action == "REVISE" else None})
        bounds = None
        if continuation.action == "REVISE":
            low = max(count[1] if count else 1, self.owner.sandbox_min)
            bounds = (low, low) if count else (low, self.owner.max_angles)
        research = self.sub("research", "m4c", self.request.message, None, continuation=continuation, bounds=bounds)
        turn = research.execution.research_plan.turn if research and research.execution.research_plan else None
        if turn != "EXECUTE_APPROVED":
            return self.finish(research, round_="FOLLOW_UP", passthrough=True)
        if not _ok(research, "ANSWER", "LIMITATION"):
            self.notes.append("Riset tidak dapat diselesaikan: " + self._reason(research))
        suggestion = self.suggest(continuation.plan.original_question, None, research,
                                  self._angles(continuation.plan), count[1] if count else 1)
        return self.finish(None, research=research, suggestion=suggestion, round_="FOLLOW_UP")

    def suggest(self, question: str, analysis: str | None, research: AgentRunResponse | None, ran: list[str],
                wanted: int) -> AgentRunResponse | None:
        count = min(max(wanted, self.owner.sandbox_min), self.owner.max_angles)
        if count != wanted:
            self.notes.append(f"Usulan memakai {count} angle (batas minimum sandbox).")
        if _ok(research, "ANSWER", "LIMITATION"):
            assert research is not None and research.response is not None
            text = research.response.answer
        else:
            text = "(the research could not be completed: " + self._reason(research) + ")"
        context = D_CONTEXT.format(
            analysis=f"<analysis>\n{analysis[:ANALYSIS_CHARS]}\n</analysis>\n" if analysis else "",
            research=text[:RESEARCH_CHARS], ran="; ".join(ran) or "none", count=count,
            plural="s" if count > 1 else "", verb="" if count > 1 else "s")
        suggestion = self.sub("suggestion", "m4d", question + "\n\n" + context, "RESEARCH", bounds=(count, count))
        if not (_ok(suggestion, "RESEARCH_PLAN_CONFIRMATION") and suggestion is not None
                and suggestion.continuation is not None):
            self.notes.append("Tidak ada usulan riset berikutnya: " + self._reason(suggestion))
            return None
        return suggestion

    # ------------------------------------------------------------------------------------------------ response

    @staticmethod
    def _angles(plan: Any) -> list[str]:
        return [f"{a.angle_id}: {a.title}" for a in getattr(plan, "angles", None) or []]

    @staticmethod
    def _reason(result: AgentRunResponse | None) -> str:
        if result is None:
            return "waktu mode 4 habis."
        if result.error is not None:
            return f"{result.error.code}."
        response = result.response
        if response is None:
            return result.status + "."
        if response.response_type == "CLARIFICATION":
            return "model meminta klarifikasi: " + (response.clarification_question or "")[:500]
        return (response.limitations[0] if response.limitations else response.response_type)[:500]

    def finish(self, main: AgentRunResponse | None, *, research: AgentRunResponse | None = None,
               suggestion: AgentRunResponse | None = None, round_: str, cancelled_plan_id: str | None = None,
               passthrough: bool = False) -> AgentRunResponse:
        """The combined response: the three sections in answer, D's plan and continuation when a suggestion is
        pending, run totals over every sub-run, and the mode4 block. A step that left nothing to combine (the analysis
        did not answer, a follow-up that revised or cancelled) is returned as it came, with the block."""
        analysis = main if round_ == "FIRST" else None
        block: dict[str, Any] = {
            "version": MODE4_VERSION, "round": round_, "steps": self.steps, "notes": self.notes,
            "turn_kind": self.turn_kind, "router": self.router_usage,
            "analysis": self._part(analysis), "research": self._part(research),
            "suggestion": self._part(suggestion), "cancelled_plan_id": cancelled_plan_id}
        research_ok = _ok(research, "ANSWER", "LIMITATION")
        base = None
        if not passthrough and (_ok(analysis, "ANSWER", "LIMITATION")
                                or (round_ == "FOLLOW_UP" and (research_ok or suggestion))):
            base = suggestion or (research if _ok(research, "ANSWER") else None) or analysis \
                or (research if research_ok else None)
        if base is None:
            result = main or research or suggestion
            if result is None:  # nothing ran: the budget was spent before the first step
                result = self.inner._failed(_empty_state(self.inner, self.request), "ANALYSIS_TIMEOUT",
                                            "AI_MODE4_MAX_SECONDS exhausted before the first step")
            response, status = result.response, result.status
        else:
            result = base
            response = self._combined_response(base, analysis, research if research_ok else None, suggestion)
            status = {"RESEARCH_PLAN_CONFIRMATION": "AWAITING_CONFIRMATION", "ANSWER": "COMPLETED",
                      "LIMITATION": "LIMITED"}[response.response_type]
        execution = self._execution(result, research if round_ == "FOLLOW_UP" else None)
        labels = [r.evidence_label for r in (analysis, research) if r is not None and r.response is not None
                  and r.response.response_type in ("ANSWER", "LIMITATION")]
        combined = AgentRunResponse(
            request_id=self.request.request_id, status=status, response=response, execution=execution,
            error=result.error if response is None else None,
            evidence_label=_weakest(labels) if base is not None and labels else result.evidence_label,
            continuation=result.continuation if response is not None
            and response.response_type == "RESEARCH_PLAN_CONFIRMATION" else None,
            annotations=self._annotations(response, (analysis, research, suggestion) if base is not None
                                          else (result,)) or None,
            mode4=block, data_record=self.record or None)
        log_event("mode4_completed", request_id=self.request.request_id, round=round_, status=combined.status,
                  steps=[(s["step"], s["status"]) for s in self.steps], cost=execution.cost,
                  duration_ms=execution.duration_ms, suggestion=suggestion is not None)
        return combined

    def _combined_response(self, base: AgentRunResponse, analysis: AgentRunResponse | None,
                           research: AgentRunResponse | None, suggestion: AgentRunResponse | None) -> Any:
        sections = []
        if analysis is not None and analysis.response is not None:
            sections.append("**Jawaban**\n\n" + analysis.response.answer)
        sections.append("**Hasil riset**\n\n" + (
            research.response.answer if research is not None and research.response is not None
            else "\n".join(n for n in self.notes if n.startswith("Riset")) or "Riset tidak dijalankan."))
        sections.append("**Usulan riset berikutnya**\n\n" + (
            suggestion.response.answer if suggestion is not None and suggestion.response is not None
            else "\n".join(n for n in self.notes if n.startswith("Tidak ada usulan")) or "Tidak ada usulan."))
        parts = [r.response for r in (analysis, research, suggestion) if r is not None and r.response is not None]
        assert base.response is not None
        return base.response.model_copy(update={
            "answer": "\n\n".join(sections), "assumptions": _merge(*[p.assumptions for p in parts]),
            "limitations": _merge(*[p.limitations for p in parts], self.notes)})

    @staticmethod
    def _annotations(response: Any, parts: tuple[AgentRunResponse | None, ...]) -> list[Any]:
        """P17: each step's claim annotations, moved to where that step's answer sits in the combined answer."""
        if response is None:
            return []
        moved = []
        for part in parts:
            if part is None or not part.annotations or part.response is None:
                continue
            base = response.answer.find(part.response.answer)
            if base < 0:
                continue
            moved += [a.model_copy(update={"start": a.start + base, "end": a.end + base}) for a in part.annotations]
        return moved

    def _part(self, result: AgentRunResponse | None) -> dict[str, Any] | None:
        if result is None or result.response is None:
            return None
        response = result.response
        part: dict[str, Any] = {"request_id": result.request_id, "status": result.status,
                                "response_type": response.response_type, "answer": response.answer,
                                "evidence_label": result.evidence_label}
        if response.research_plan is not None:
            part["research_plan"] = response.research_plan.model_dump(mode="json")
            part["plan_id"] = result.continuation.plan_id if result.continuation else None
        if response.research_findings is not None:
            part["research_findings"] = [f.model_dump(mode="json") for f in response.research_findings]
        if response.methodology:
            part["methodology"] = response.methodology
        return part

    def _execution(self, result: AgentRunResponse, executed: AgentRunResponse | None) -> Any:
        """result's metadata with totals over every sub-run (and the reply classifier). In a follow-up round the
        research_plan block records both the approval that ran and the plan issued next, so the conversation store
        retires the approved plan as EXECUTED and keeps the suggestion PENDING."""
        runs = [r.execution for r in self.results]
        costs = [e.cost for e in runs if e.cost is not None]
        if (self.router_usage or {}).get("cost") is not None:
            costs.append(self.router_usage["cost"])
        classifier = self.classifier or {}
        if classifier.get("cost") is not None:
            costs.append(classifier["cost"])
        totals = {key: sum(getattr(e, key) for e in runs) for key in (
            "iterations", "tool_call_count", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
            "cached_input_tokens", "cache_write_tokens")}
        totals["input_tokens"] += int(classifier.get("input_tokens") or 0)
        totals["output_tokens"] += int(classifier.get("output_tokens") or 0)
        totals["total_tokens"] += int(classifier.get("input_tokens") or 0) + int(classifier.get("output_tokens") or 0)
        update: dict[str, Any] = {
            **totals, "cost": round(sum(costs), 6) if costs else None,
            "duration_ms": int((self.inner.clock() - self.started) * 1000),
            "analyses": [a for e in runs for a in e.analyses],
            "analysis_path": AnalysisPathExecution(requested="MODE4",
                                                   mismatches_refused=sum(e.analysis_path.mismatches_refused
                                                                          for e in runs if e.analysis_path))}
        plan_exec = result.execution.research_plan
        ran = executed.execution.research_plan if executed is not None else None
        if plan_exec is not None and ran is not None and ran is not plan_exec and ran.turn == "EXECUTE_APPROVED":
            plan_exec = plan_exec.model_copy(update={
                "turn": ran.turn, "verification": ran.verification, "action": ran.action,
                "action_source": ran.action_source, "approved_plan_id": ran.approved_plan_id,
                "research_submitted": ran.research_submitted, "research_run_id": ran.research_run_id})
        if plan_exec is not None and self.classifier:
            plan_exec = plan_exec.model_copy(update={
                "action_source": "CLASSIFIER", "classifier": ReplyClassifierUsage(**self.classifier)})
        update["research_plan"] = plan_exec
        return result.execution.model_copy(update=update)


def _empty_state(inner: AgentOrchestrator, request: AgentRunRequest) -> Any:
    from .orchestrator import RunState

    return RunState(request_id=request.request_id, started=inner.clock(), input_items=[])
