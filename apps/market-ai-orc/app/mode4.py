"""Mode 4 (user decision 2026-09-30): answer first, then research that tests the answer, then one suggestion.

A request without analysis_path (or with MODE4) runs as a pipeline of ordinary orchestrator runs; every sub-run keeps
all of its gates (provenance, value references, findings, claims, audit) and has its own request_id
(<request_id>-m4a, -m4b, ...), so the audit store and the logs show each step.

First round (no pending plan):
  A  analysis     forced_path ANALYSIS: the direct answer to the question.
  B  research plan forced_path RESEARCH, at least two angles, built on A's answer (the angles test or deepen it).
  EXEC-P1 (user approval 2026-10-06): the round ends here; B's plan waits for the user's approval (status
  AWAITING_CONFIRMATION), so nothing is computed before the user agrees. With AI_MODE4_AUTO_RESEARCH (the earlier
  behaviour, decisions 2026-09-30 / 2026-10-02) the round goes on:
  C  execution    B's plan, approved by the backend at once (its rpc2 token is signed and verified as usual).
  D  suggestion   forced_path RESEARCH, exactly one angle (or the count the user asked for), following up on A and C;
                  its plan is returned for the user's confirmation (status AWAITING_CONFIRMATION).
Follow-up round (the reply to the waiting plan, read by the existing reply classifier):
  APPROVE    the plan runs; a next suggestion (D) follows only when the user asks for one ("kasih satu usulan lagi")
             or with AI_MODE4_AUTO_RESEARCH.
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
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from . import conversation_router as router
from . import data_record as records
from . import modes
from . import stop
from .conversations import assistant_text
from .orchestrator import MODE4_PART_TARGET_CHARS, AgentOrchestrator, current_answer_target, current_time_budget, \
    log_event
from .provenance import LABEL_ORDER
from .research_plan import ContinuationIn, ContinuationOut
from .research_plan_v2 import ContinuationInV2, ContinuationOutV2, current_angle_bounds, plan_digest_v2
from .tools.request_data import current_conversation_id, current_turn_id
from .user_words import MESSAGE_SEPARATOR, current_design_changes, current_turn_referent, current_user_words
from .schemas import (MAX_HISTORY_ITEMS, MAX_MESSAGE_CHARACTERS, AgentRunRequest, AgentRunResponse,
                      AnalysisPathExecution, ExecutionMetadata, FinalResponse, HistoryMessage, ModeExecution,
                      ReplyClassifierUsage)

MODE4_VERSION = 1
MIN_STEP_SECONDS = 120  # a step is not started with less time left than this
APPROVAL_MESSAGE = "Setuju, jalankan rencana ini."
NO_DATA_LINE = "Riset tidak dijalankan: jawaban analisis tidak memakai angka dari data, jadi tidak ada temuan untuk diuji."
PATH_MODES = {"ANALYSIS": (2, "ANALYSIS"), "RESEARCH": (3, "RESEARCH"), "MODE4": (4, "MODE4")}
PENDING_LINE = "Usulan riset sebelumnya masih menunggu keputusan Anda; balas \"jalankan\" kapan saja untuk menjalankannya."
STEP_SUFFIX = {"CLARIFY": "m4q", "CONVERSATIONAL": "m4q", "INSIGHT": "m4i", "CONTINUE": "m4n"}
# EXEC-3: the route each quick choice of a first-message ask-back runs, and the steps that get the router's reading of
# the request as a note (not the research steps, whose context is the earlier steps' results)
CHOICE_ROUTES = {"QUICK_SUMMARY": "ANALYSIS", "ANALYSIS": "ANALYSIS", "RESEARCH": "RESEARCH", "EXPLORE": "EXPLORE",
                 "FACT": "FACT"}
INTENT_STEPS = ("analysis", "chat", "fact", "clarify", "conversational", "insight", "continue")
MAX_ASK_BACKS = 2  # a third unclear reply runs the fallback step instead of asking again
ANALYSIS_CHARS, RESEARCH_CHARS = 5000, 6000  # the earlier cut (without the run memory)
METHODOLOGY_MAX = 6000  # FinalResponse.methodology
NUMBER_WORDS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6,
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
SUGGESTION_WORDS = ("opsi", "pilihan", "usulan", "saran", "option", "suggestion", "alternatif")
COUNT_RE = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")\s+(?:buah\s+|more\s+|new\s+)?"
                      r"(angles?|sudut|hipotesis|hypothes[ie]s|opsi|pilihan|usulan|saran|options?|suggestions?"
                      r"|alternatif)\b", re.IGNORECASE)

# EXEC-P1: the suggestion section when no next plan was asked for
NO_SUGGESTION_LINE = ("Usulan riset lanjutan dibuat bila Anda memintanya, misalnya \"beri satu usulan riset "
                      "lanjutan\".")
PLAN_TITLE = "**Rencana riset untuk menguji jawaban ini** (menunggu persetujuan Anda)"
B_CONTEXT = ("Application context (mode 4), not from the user: the question above was already answered by the "
             "descriptive analysis below, which the user has received.\n<analysis>\n{analysis}\n</analysis>\n"
             "Propose a Research Plan whose angles test or deepen what this analysis found: for example whether the "
             "pattern is real and larger than chance, stable over time and across groups, or explained by something "
             "else. Do not repeat the analysis itself. When the user stated a success threshold (a rise of at least "
             "some percent), a hypothesis plan whose experiment carries it as success_rule tests it directly; keep "
             "the outcome horizon the user stated.")
D_CONTEXT = ("Application context (mode 4), not from the user: the user has received the results below.\n"
             "{analysis}<research>\n{research}\n</research>\n"
             "These angles already ran: {ran}.\nPropose a Research Plan with exactly {count} new angle{plural} that "
             "follow{verb} up on these results (what they leave open, a condition to test, a different group or "
             "period). Do not repeat an angle that already ran. Keep the outcome horizon and success threshold the "
             "user stated; a different one is only mentioned as an option. It is a suggestion: the user decides "
             "whether it runs.")


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


def _merge(*lists: list[str], limit: int | None = 20) -> list[str]:
    """The items of the lists once each; EXEC-C item 7: limit None keeps every item (with the run memory)."""
    merged: list[str] = []
    for items in lists:
        for item in items or []:
            if item and item not in merged:
                merged.append(item)
    return merged if limit is None else merged[:limit]


def _ok(result: AgentRunResponse | None, *types: str) -> bool:
    return result is not None and result.status != "FAILED" and result.response is not None \
        and result.response.response_type in types


def _artifacts(*results: AgentRunResponse | None) -> list[dict[str, Any]] | None:
    """D4: the export files of every step of the turn, once each."""
    seen: dict[str, dict[str, Any]] = {}
    for result in results:
        for artifact in (result.artifacts or []) if result is not None else []:
            seen.setdefault(str(artifact.get("export_id")), artifact)
    return list(seen.values()) or None


class Mode4Orchestrator:
    """Wraps AgentOrchestrator: a request with analysis_path MODE4 runs mode 4, every other one goes straight to it.
    Other attributes (analysis_path, conversation_reuse, registry, close, ...) are the inner orchestrator's."""

    mode4 = True
    router = False  # AI_ENABLE_CONVERSATION_ROUTER, set in __init__
    first_router = False  # AI_ENABLE_FIRST_TURN_ROUTER, set in __init__
    ask_back = False  # AI_ENABLE_ASK_BACK (EXEC-3), set in __init__
    auto_research = False  # AI_MODE4_AUTO_RESEARCH (EXEC-P1), set in __init__
    memory = False  # AI_ENABLE_RUN_MEMORY (EXEC-C), set in __init__

    def __init__(self, inner: AgentOrchestrator) -> None:
        self.inner = inner
        limits = inner.research_limits or {}
        self.min_angles, self.max_angles = int(limits.get("min_angles", 2)), int(limits.get("max_angles", 6))
        # the fewest angles the sandbox runs in one plan: a one-angle suggestion needs PY_SANDBOX_RESEARCH_MIN_ANGLES=1
        self.sandbox_min = int(limits.get("sandbox_min_angles") or 2)
        self.router = bool(getattr(inner.settings, "ai_enable_conversation_router", False))
        self.first_router = bool(getattr(inner.settings, "ai_enable_first_turn_router", False))
        self.ask_back = self.first_router and bool(getattr(inner.settings, "ai_enable_ask_back", False))
        # EXEC-P1: the first round's plan runs at once (the earlier behaviour) only with AI_MODE4_AUTO_RESEARCH
        self.auto_research = bool(getattr(inner.settings, "ai_mode4_auto_research", False))
        # EXEC-C (AI_ENABLE_RUN_MEMORY): steps hand each other whole texts, and the router's reading is kept
        self.memory = getattr(inner, "run_memory", None) is not None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def run(self, request: AgentRunRequest, conversation_key: str | None = None,
            data_record: dict[str, Any] | None = None) -> AgentRunResponse:
        """analysis_path MODE4 runs the pipeline; any other request (the mode switcher, app/modes.py, has set its path:
        none for AUTO) goes to the orchestrator unchanged. EXEC-S: every model call of the conversation, the routers
        included, carries the conversation id as its session id."""
        conversation = current_conversation_id.set(current_conversation_id.get() or request.conversation_id)
        try:
            if self.first_router and request.continuation is None and (
                    not request.history or (self.ask_back and router.first_stage(request.history))):
                # EXEC-3: a reply to a first-message ask-back is still the first message's routing
                return self._first_message(request, conversation_key, data_record)
            if request.analysis_path != "MODE4":
                return self.inner.run(request, conversation_key, data_record=data_record)
            return _Mode4Run(self, request, conversation_key, data_record).execute()
        finally:
            current_conversation_id.reset(conversation)

    def _first_message(self, request: AgentRunRequest, conversation_key: str | None,
                       data_record: dict[str, Any] | None, cancelled_plan_id: str | None = None,
                       notes: list[str] | None = None) -> AgentRunResponse:
        """The first-message router (conversation_router.FIRST_ROUTE_RULES): CHAT and FACT run one step without
        warehouse data whatever the caller's analysis_path; a data route runs at the caller's depth, else at the
        route's; a failed router call runs one analysis step. The mode record names the route. EXEC-3
        (AI_ENABLE_ASK_BACK): the router may ask back (a failed call is retried once, then asked back with a fixed
        question); a quick choice runs its route without a router call; the router's reading of the request goes to
        the step that does the work."""
        chosen = request.chosen_option if self.ask_back and request.chosen_option in CHOICE_ROUTES else None
        source, intent = "ROUTER", None
        if chosen is not None:
            route, usage, source = CHOICE_ROUTES[chosen], {"status": "CHOICE", "choice": chosen}, "CHOICE"
        else:
            reply = self.ask_back and bool(request.history) and router.first_stage(request.history)
            route, _, usage = self.inner.classify_first(
                f"{request.request_id[:190]}-m4f",
                router.exchange_text(request.history, request.message) if reply else request.message)
        if self.ask_back and route in (router.ASK_BACK, None):
            asked = sum(router.asked_back(m.content) for m in request.history if m.role == "assistant")
            if asked < MAX_ASK_BACKS:
                return ask_back_response(self.inner, request, usage, first=True, pending=False, failed=route is None,
                                         data_record=data_record)
            route = None  # asked enough: the fallback step, with the reading the router gave
        if self.ask_back:
            intent = {"understood_intent": usage.get("understood_intent"), "assumptions": usage.get("assumptions"),
                      "choice": chosen}
        if chosen is not None:  # the user's choice is the depth (FIRST_ROUTE_RULES 3 is for the router's route)
            step, path = ("FACT", None) if route == "FACT" else ("PATH", router.ROUTE_PATHS[route])
        else:
            step, path = router.first_route_path(route, request.analysis_path)
        if step in ("CHAT", "FACT"):
            run = _Mode4Run(self, request, conversation_key, data_record)
            run.router_usage, run.intent = {**usage, "route": route}, intent
            kind = "CONVERSATIONAL" if step == "CHAT" else "FACT"
            run.turn_kind = kind
            result = run.finish(run.sub(step.lower(), "m4q", request.message, None, turn_kind=kind),
                                round_=step, passthrough=True)
            mode = ModeExecution(mode=4, name="MODE4", source=source, route=chosen or route)
        else:
            number, name = PATH_MODES[path or "ANALYSIS"]
            routed = request.model_copy(update={"analysis_path": path})
            if path == "MODE4":
                run = _Mode4Run(self, routed, conversation_key, data_record)
                run.router_usage, run.intent = {**usage, "route": route}, intent
                run.notes.extend(notes or [])
                result = run.first_round(cancelled_plan_id=cancelled_plan_id)
            else:
                with _reading(intent, usage):
                    result = self.inner.run(routed, conversation_key, data_record=data_record)
                if self.memory:
                    result = _with_reading(result, request.request_id, {**usage, "route": route or "ROUTER_FAILED"})
            mode = ModeExecution(mode=number, name=name, source=source, route=chosen or route or "ROUTER_FAILED")
        log_event("first_message_handled", request_id=request.request_id, route=route or "ROUTER_FAILED",
                  caller_path=request.analysis_path, step=step, analysis_path=path, status=result.status,
                  **({"choice": chosen} if chosen else {}))
        return result.model_copy(update={"execution": result.execution.model_copy(update={"mode": mode})})


def _with_reading(result: AgentRunResponse, request_id: str, usage: dict[str, Any] | None) -> AgentRunResponse:
    """EXEC-C item 13: the router's reading of the message, kept in the data record for the turns after it."""
    record = records.normalize(result.data_record)
    records.add_reading(record, request_id, usage)
    return result.model_copy(update={"data_record": records.public(record)})


@contextmanager
def _reading(intent: dict[str, Any] | None, usage: dict[str, Any] | None) -> Iterator[None]:
    """EXEC-3: the router's reading around one run outside the pipeline (the note and the plan gates' design values)."""
    tokens: list[tuple[Any, Any]] = [(router.current_intent, router.current_intent.set(intent))]
    if usage is not None and "design_value_changes" in usage:
        tokens += [(current_design_changes, current_design_changes.set(usage["design_value_changes"])),
                   (current_turn_referent, current_turn_referent.set(usage.get("referent")))]
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def ask_back_response(inner: AgentOrchestrator, request: AgentRunRequest, usage: dict[str, Any], *, first: bool,
                      pending: bool, failed: bool, data_record: dict[str, Any] | None,
                      notes: list[str] | None = None) -> AgentRunResponse:
    """EXEC-3: one question with quick choices, nothing run (status NEEDS_CLARIFICATION). The router's question
    whenever the router asked one (EXEC-M109: never replaced because its choices do not fit the buttons); its choices
    as buttons when at least two usable ones have distinct routes, else as numbered lines of the question
    (conversation_router.offered_choices). Only after a failed router call (retried once) or without a question: the
    fixed question (conversation_router.FALLBACK_QUESTION) with the fixed choices."""
    allowed = router.FIRST_OPTION_ROUTES if first else router.TURN_OPTION_ROUTES
    question = None if failed else (str(usage.get("question") or "").strip() or None)
    options, labels = router.offered_choices(usage.get("options") or [], allowed, pending) if question else ([], [])
    if question is None:
        options = router.fallback_options(first, pending)
    text = router.question_text(question, options or [{"label": label, "route": ""} for label in labels])
    response = FinalResponse(response_type="CLARIFICATION", answer=text, clarification_question=text,
                             assumptions=[str(a) for a in usage.get("assumptions") or []][:5],
                             limitations=list(notes or []))
    tokens_in, tokens_out = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    execution = ExecutionMetadata(
        model=inner.settings.ai_model, input_tokens=tokens_in, output_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out, cost=usage.get("cost"), duration_ms=int(usage.get("latency_ms") or 0),
        mode=ModeExecution(mode=4, name="MODE4", source="ROUTER", route="ROUTER_FAILED" if failed else "ASK_BACK")
        if first else None)
    log_event("ask_back", request_id=request.request_id, first=first, failed=failed, pending=pending,
              router_question=question is not None, options=[o["route"] for o in options], text_choices=len(labels),
              router_status=usage.get("status"), latency_ms=usage.get("latency_ms"))
    if getattr(inner, "run_memory", None) is not None:
        # EXEC-C item 13: an ask-back runs no step, so its reading goes straight to the data record
        record = records.normalize(data_record)
        records.add_reading(record, request.request_id, {**usage, "route": "ROUTER_FAILED" if failed else "ASK_BACK"})
        data_record = records.public(record)
    return AgentRunResponse(
        request_id=request.request_id, status="NEEDS_CLARIFICATION", response=response, execution=execution,
        options=options, data_record=data_record or None,
        mode4={"version": MODE4_VERSION, "round": "ASK_BACK", "steps": [], "notes": list(notes or []),
               "turn_kind": None if first else "ASK_BACK", "router": usage, "analysis": None, "research": None,
               "suggestion": None, "cancelled_plan_id": None})


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
        # EXEC-3: the router's reading of the request (note for the working step), and the plan-reply reader's
        # reading when no router read the message (P3b)
        self.intent: dict[str, Any] | None = None
        self.reading: dict[str, Any] | None = None
        self.base_id = request.request_id[:190]
        # EXEC-P1: B's plan is the waiting suggestion of the first round; no next plan was asked for after a run
        self.plan_waiting = False
        self.suggestion_skipped = False
        # EXEC-C items 7 and 8: the analysis and plan steps of the round, for the next steps and the combined answer
        self.analysis_result: AgentRunResponse | None = None
        self.plan_result: AgentRunResponse | None = None

    # ------------------------------------------------------------------------------------------------ plumbing

    def remaining(self) -> float:
        return self.settings.ai_mode4_max_seconds - (self.inner.clock() - self.started)

    def sub(self, step: str, suffix: str, message: str, analysis_path: str | None, *,
            continuation: ContinuationInV2 | ContinuationIn | None = None, history: list[HistoryMessage] | None = None,
            bounds: tuple[int, int] | None = None, turn_kind: str | None = None) -> AgentRunResponse | None:
        request_id = f"{self.base_id}-{suffix}"
        left = self.remaining()
        if stop.requested():  # the stop button: the steps not started are skipped (app/stop.py)
            self.steps.append({"step": step, "request_id": request_id, "status": "SKIPPED",
                               "reason": "STOPPED_BY_USER"})
            log_event("mode4_step_skipped", request_id=self.request.request_id, step=step, reason="STOPPED_BY_USER")
            return None
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
        # M69 tahap 1 / H2: the plan gates bind thresholds and horizons to the user's messages, not to this step's
        # application context (the model's own analysis and research text)
        words = current_user_words.set(MESSAGE_SEPARATOR.join(
            [m.content for m in self.request.history if m.role == "user"] + [self.request.message]))
        # M82: the router's structured reading of this message (None when no conversation router read it); P3b: else
        # the plan-reply reader's
        reading = self.router_usage if self.router_usage is not None else (self.reading or {})
        changes = current_design_changes.set(reading.get("design_value_changes"))
        referent = current_turn_referent.set(reading.get("referent"))
        intent = router.current_intent.set(self.intent if step in INTENT_STEPS else None)
        turn = current_turn_id.set(self.base_id)  # item 12: one web budget for every step of this message
        target = current_answer_target.set(MODE4_PART_TARGET_CHARS)  # EXEC-P2 P2e: each part of the reply
        try:
            result = self.inner.run(sub_request, self.key, data_record=self.record)
        finally:
            current_answer_target.reset(target)
            current_time_budget.reset(budget)
            current_angle_bounds.reset(angle_bounds)
            router.current_turn_kind.reset(kind)
            current_user_words.reset(words)
            current_design_changes.reset(changes)
            current_turn_referent.reset(referent)
            router.current_intent.reset(intent)
            current_turn_id.reset(turn)
        response, execution = result.response, result.execution
        plan_exec = execution.research_plan
        self.steps.append({
            "step": step, "request_id": request_id, "status": result.status,
            "response_type": response.response_type if response else None, "evidence_label": result.evidence_label,
            "turn": plan_exec.turn if plan_exec else None,
            "plan_id": result.continuation.plan_id if result.continuation else None,
            "angles": len(self._angles(response.research_plan)) if response and response.research_plan is not None
            else None,
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
            # a research_plan/v1 plan (a hypothesis plan): the plan-reply reader, as on the path it was issued on, with the
            # conversation's data record (M105: until mode 4's plans all stayed in mode 4, this path never had one)
            return self.inner.run(self.request, self.key, data_record=self.record)
        if self.owner.router and (continuation is not None or self.request.history):
            return self.routed(continuation)
        if continuation is None:
            return self.first_round()
        return self.follow_up(continuation)

    def routed(self, continuation: ContinuationInV2 | None) -> AgentRunResponse:
        """4d: a later turn, classified by the conversation router and handled by the backend's rules."""
        pending = continuation is not None
        explicit = continuation.action if pending else None
        chosen = self.request.chosen_option if self.owner.ask_back \
            and self.request.chosen_option in router.TURN_OPTION_ROUTES else None
        if explicit is not None:
            kind, instruction = explicit, continuation.revision_instruction
        elif chosen is not None:
            # EXEC-3: a quick choice of the latest ask-back question runs its class without a router call
            kind, instruction = router.apply_rules(chosen, pending), None
            self.router_usage = {"status": "CHOICE", "choice": chosen}
        else:
            # M64: the results produced after the pending suggestion, from the data record's own order
            newer = records.results_after_suggestion(self.record, continuation.plan_id) if pending else None
            history = list(self.request.history)
            asked = history[-1].content if self.owner.ask_back and history and history[-1].role == "assistant" \
                and router.asked_back(history[-1].content) else None
            context = router.context(self.record, history, plan_digest_v2(continuation.plan) if pending else None,
                                     newer, asked)
            raw, instruction, self.router_usage = self.inner.classify_turn(f"{self.base_id}-m4r",
                                                                           self.request.message, context)
            if self.owner.ask_back and raw in (router.ASK_BACK, None):
                # EXEC-3: asked back, or the router failed twice: a question (fixed after a failure), nothing runs
                return ask_back_response(self.inner, self.request, self.router_usage or {}, first=False,
                                         pending=pending, failed=raw is None, data_record=self.record,
                                         notes=[PENDING_LINE] if pending else None)
            if self.owner.ask_back:
                self.intent = {"understood_intent": (self.router_usage or {}).get("understood_intent")}
            kind = router.apply_rules(raw, pending, newer, (self.router_usage or {}).get("referent"))
            if kind != raw and raw in ("APPROVE", "REVISE") and newer:
                log_event("mode4_stale_suggestion", request_id=self.request.request_id, router_kind=raw,
                          referent=(self.router_usage or {}).get("referent"), newer_results=newer[-5:])
        self.turn_kind = kind
        log_event("mode4_turn_routed", request_id=self.request.request_id, turn_kind=kind, pending=pending,
                  source="EXPLICIT" if explicit else "ROUTER")
        if kind in router.NEEDS_PENDING:
            assert continuation is not None
            return self.follow_up(continuation.model_copy(update={
                "action": kind, "revision_instruction": instruction if kind == "REVISE" else None}))
        if kind == "NEW_TOPIC":
            if self.owner.first_router:
                # a new topic is routed like a first message (AI_ROUTER.md): no default mode inside a conversation
                # either; a pending suggestion stays pending unless the new topic runs mode 4's first round
                return self.owner._first_message(
                    self.request.model_copy(update={"continuation": None,
                                                    "analysis_path": modes.current_caller_path.get()}),
                    self.key, self.record,
                    cancelled_plan_id=continuation.plan_id if pending else None,
                    notes=["Usulan riset sebelumnya dibatalkan karena ada pertanyaan baru."] if pending else None)
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
        self.analysis_result = analysis
        if not _ok(analysis, "ANSWER", "LIMITATION"):
            # M43 (user decision 2026-09-30): a LIMITATION still carries the analysis and its limits, so the research
            # runs on it; a clarification (the user must answer first) or a failure ends the round
            self.notes.append("Riset tidak dijalankan karena analisis tidak menghasilkan jawaban.")
            return self.finish(analysis, round_="FIRST", cancelled_plan_id=cancelled_plan_id)
        assert analysis is not None and analysis.response is not None
        if analysis.evidence_label is None:
            # M79 (user decision 2026-10-04): research tests what the data showed; an answer without figures from
            # data (a fact, a definition, small talk, a refusal) has nothing to test, so B-D do not run
            self.notes.append(NO_DATA_LINE)
            log_event("mode4_research_skipped", request_id=self.request.request_id, reason="NO_DATA_FIGURES",
                      response_type=analysis.response.response_type)
            return self.finish(analysis, round_="FIRST", cancelled_plan_id=cancelled_plan_id)
        answer = analysis.response.answer
        low = max(2, self.owner.min_angles)
        if count and count[0] == "ANGLE":
            low = min(max(2, count[1]), self.owner.max_angles)
            bounds = (low, low)
        else:
            bounds = (low, self.owner.max_angles)
        plan = self.sub("research_plan", "m4b", question + "\n\n" + B_CONTEXT.format(
            analysis=self._step_text(analysis, MAX_MESSAGE_CHARACTERS - len(question) - len(B_CONTEXT) - 200)
            if self.owner.memory else answer[:ANALYSIS_CHARS]), "RESEARCH", bounds=bounds)
        if not self.owner.auto_research:
            # EXEC-P1 (user approval 2026-10-06): the plan waits for the user's approval; nothing runs before it
            if _ok(plan, "RESEARCH_PLAN_CONFIRMATION") and plan is not None and plan.continuation is not None:
                self.plan_waiting = True
                return self.finish(analysis, suggestion=plan, round_="FIRST", cancelled_plan_id=cancelled_plan_id)
            self.notes.append("Rencana riset tidak dapat dibuat: " + self._reason(plan))
            return self.finish(analysis, round_="FIRST", cancelled_plan_id=cancelled_plan_id)
        self.plan_result = plan
        research = None
        if _ok(plan, "RESEARCH_PLAN_CONFIRMATION") and isinstance(plan.continuation, (ContinuationOutV2,
                                                                                         ContinuationOut)):
            issued = plan.continuation
            # M69 tahap 1: a hypothesis plan (the user's success threshold) is approved the same way as a multi-angle
            # plan; its token is signed and verified as usual
            approval = ContinuationInV2(kind="RESEARCH_PLAN", plan_id=issued.plan_id,
                                        origin_request_id=issued.origin_request_id, plan=plan.response.research_plan,
                                        research_data_plan=issued.research_data_plan, token=issued.token,
                                        action="APPROVE") if isinstance(issued, ContinuationOutV2) else ContinuationIn(
                kind="RESEARCH_PLAN", plan_id=issued.plan_id, origin_request_id=issued.origin_request_id,
                plan=plan.response.research_plan, token=issued.token, action="APPROVE")
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
            self.reading = (self.classifier or {}).pop("reading", None)  # P3b
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
        if not self.owner.auto_research and not (count and count[0] == "SUGGESTION"):
            # EXEC-P1: no next plan unless the user asks for one
            self.suggestion_skipped = True
            return self.finish(None, research=research, round_="FOLLOW_UP")
        suggestion = self.suggest(continuation.plan.original_question, None, research,
                                  self._angles(continuation.plan), count[1] if count else 1)
        return self.finish(None, research=research, suggestion=suggestion, round_="FOLLOW_UP")

    def suggest(self, question: str, analysis: str | None, research: AgentRunResponse | None, ran: list[str],
                wanted: int) -> AgentRunResponse | None:
        count = min(max(wanted, self.owner.sandbox_min), self.owner.max_angles)
        if count != wanted:
            self.notes.append(f"Usulan memakai {count} angle (batas minimum sandbox).")
        room = MAX_MESSAGE_CHARACTERS - len(question) - len(D_CONTEXT) - len("; ".join(ran)) - 300
        if _ok(research, "ANSWER", "LIMITATION"):
            assert research is not None and research.response is not None
            text = self._step_text(research, room - min(len(analysis or ""), room // 2)) if self.owner.memory \
                else research.response.answer[:RESEARCH_CHARS]
        else:
            text = "(the research could not be completed: " + self._reason(research) + ")"
        if analysis and self.owner.memory:
            analysis = self._step_text(self.analysis_result, room - len(text)) if self.analysis_result is not None \
                else analysis[:max(room - len(text), 0)]
        context = D_CONTEXT.format(
            analysis=(f"<analysis>\n{analysis if self.owner.memory else analysis[:ANALYSIS_CHARS]}\n</analysis>\n"
                      if analysis else ""),
            research=text, ran="; ".join(ran) or "none", count=count,
            plural="s" if count > 1 else "", verb="" if count > 1 else "s")
        suggestion = self.sub("suggestion", "m4d", question + "\n\n" + context, "RESEARCH", bounds=(count, count))
        if not (_ok(suggestion, "RESEARCH_PLAN_CONFIRMATION") and suggestion is not None
                and suggestion.continuation is not None):
            self.notes.append("Tidak ada usulan riset berikutnya: " + self._reason(suggestion))
            return None
        return suggestion

    # ------------------------------------------------------------------------------------------------ response

    @staticmethod
    def _step_text(result: AgentRunResponse | None, limit: int) -> str:
        """EXEC-C item 8: a step's whole answer for the next step (with its assumptions, limitations and methodology),
        within limit; a longer one is shortened in its body with a pointer to the full text in the run memory."""
        if result is None or result.response is None:
            return ""
        return assistant_text(result, max(limit, 2000), memory_tool=True) or ""

    @staticmethod
    def _angles(plan: Any) -> list[str]:
        """What ran or is proposed: the angles of a multi-angle plan, the experiments of a hypothesis plan."""
        return [f"{a.angle_id}: {a.title}" for a in getattr(plan, "angles", None) or []] + [
            f"{e.hypothesis_id}: {e.hypothesis}" for e in getattr(plan, "experiments", None) or []]

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
        if self.owner.memory and self.router_usage:
            # EXEC-C item 13: how the router read this message, for the turns after it
            self.record = records.normalize(self.record)
            records.add_reading(self.record, self.request.request_id,
                                {**self.router_usage, "turn_kind": self.turn_kind})
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
            if result is None and stop.requested():  # stopped before the first step began
                result = self.inner._failed(_empty_state(self.inner, self.request), "STOPPED_BY_USER",
                                            "stopped by the user before the first step")
            elif result is None:  # nothing ran: the budget was spent before the first step
                result = self.inner._failed(_empty_state(self.inner, self.request), "ANALYSIS_TIMEOUT",
                                            "AI_MODE4_MAX_SECONDS exhausted before the first step")
            response, status = result.response, result.status
        else:
            result = base
            response = self._combined_response(base, analysis, research if research_ok else None, suggestion)
            status = {"RESEARCH_PLAN_CONFIRMATION": "AWAITING_CONFIRMATION", "ANSWER": "COMPLETED",
                      "LIMITATION": "LIMITED"}[response.response_type]
        execution = self._execution(result, research if round_ == "FOLLOW_UP" else None)
        # EXEC-W A1 (M121): a step that paused pauses the turn (its question is in that step's section); a later step's
        # record must not clear it
        pause = next((r.execution.pause for r in (analysis, research, suggestion, main)
                      if r is not None and r.execution is not None and r.execution.pause), None)
        if pause is not None:
            execution = execution.model_copy(update={"pause": pause})
            self.record = {**records.normalize(self.record), "pause": pause}
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
            mode4=block, data_record=self.record or None,
            artifacts=_artifacts(analysis, research, suggestion, result),
            evidence=[e for r in (analysis, research, suggestion) if r is not None for e in r.evidence or []]
            or (result.evidence if base is None else None) or None)
        log_event("mode4_completed", request_id=self.request.request_id, round=round_, status=combined.status,
                  steps=[(s["step"], s["status"]) for s in self.steps], cost=execution.cost,
                  duration_ms=execution.duration_ms, suggestion=suggestion is not None)
        return combined

    def _combined_response(self, base: AgentRunResponse, analysis: AgentRunResponse | None,
                           research: AgentRunResponse | None, suggestion: AgentRunResponse | None) -> Any:
        sections = []
        if analysis is not None and analysis.response is not None:
            sections.append("**Jawaban**\n\n" + analysis.response.answer)
        if self.plan_waiting and research is None and suggestion is not None and suggestion.response is not None:
            # EXEC-P1: the answer and the plan that waits for the user's approval
            sections.append(PLAN_TITLE + "\n\n" + suggestion.response.answer)
        else:
            sections.append("**Hasil riset**\n\n" + (
                research.response.answer if research is not None and research.response is not None
                else "\n".join(n for n in self.notes if n.startswith("Riset")) or "Riset tidak dijalankan."))
            sections.append("**Usulan riset berikutnya**\n\n" + (
                suggestion.response.answer if suggestion is not None and suggestion.response is not None
                else NO_SUGGESTION_LINE if self.suggestion_skipped
                else "\n".join(n for n in self.notes if n.startswith("Tidak ada usulan")) or "Tidak ada usulan."))
        parts = [r.response for r in (analysis, research, suggestion) if r is not None and r.response is not None]
        assert base.response is not None
        limit = None if self.owner.memory else 20  # EXEC-C item 7: every assumption and limitation
        update: dict[str, Any] = {
            "answer": "\n\n".join(sections), "assumptions": _merge(*[p.assumptions for p in parts], limit=limit),
            "limitations": _merge(*[p.limitations for p in parts], self.notes, limit=limit)}
        if self.owner.memory and base.response.response_type != "RESEARCH_PLAN_CONFIRMATION":
            update["methodology"] = self._methodology(analysis, research)
        return base.response.model_copy(update=update)

    def _methodology(self, analysis: AgentRunResponse | None, research: AgentRunResponse | None) -> str | None:
        """EXEC-C item 7: the methodology of every step of the turn (it used to be one step's), with the plan that ran
        (step B, when the round ran it at once); within the response's limit, a longer one names where the rest is."""
        parts = []
        for title, result in (("Analisis", analysis), ("Riset", research)):
            if result is not None and result.response is not None and result.response.methodology:
                parts.append((f"{title}: {result.response.methodology}", result.request_id))
        if self.plan_result is not None and self.plan_result.response is not None and research is not None:
            plan = self.plan_result.response.research_plan
            ran = "; ".join(self._angles(plan)) if plan is not None else ""
            objective = getattr(plan, "objective", None) or ""
            parts.append((f"Rencana yang dijalankan (langkah B): {objective}" + (f" Sudut: {ran}." if ran else ""),
                          self.plan_result.request_id))
        if not parts:
            return None
        text = "\n\n".join(t for t, _ in parts)
        if len(text) <= METHODOLOGY_MAX:
            return text
        room = (METHODOLOGY_MAX - 200 * len(parts)) // len(parts)
        return "\n\n".join(t if len(t) <= room else t[:room].rstrip() + f" [… lengkapnya: read_conversation_memory("
                           f"run_id=\"{rid}\", section=\"answer\")]" for t, rid in parts)[:METHODOLOGY_MAX]

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
