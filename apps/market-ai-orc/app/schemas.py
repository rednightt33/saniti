from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

from .research_plan import Action, ContinuationIn, ContinuationOut, ResearchPlan, ResearchPlanFindings
from .research_plan_v2 import AngleStatus, ContinuationInV2, ContinuationOutV2, ResearchPlanV2


MAX_MESSAGE_CHARACTERS = 16000
MAX_HISTORY_ITEMS = 50
MAX_METADATA_BYTES = 8192

ResponseType = Literal["ANSWER", "CLARIFICATION", "RESEARCH_PLAN_CONFIRMATION", "LIMITATION"]
RunStatus = Literal["COMPLETED", "NEEDS_CLARIFICATION", "AWAITING_CONFIRMATION", "LIMITED", "FAILED"]
# AI_ENABLE_ANALYSIS_PATH: the data-need mode a caller fixes for a request (null: the model chooses)
# AUTO: the model chooses (mode 1); MODE4: AI_ENABLE_MODE4 (app/mode4.py); the mode switcher is app/modes.py
AnalysisPath = Literal["AUTO", "ANALYSIS", "RESEARCH", "MODE4"]

STATUS_BY_RESPONSE_TYPE: dict[str, str] = {
    "ANSWER": "COMPLETED",
    "CLARIFICATION": "NEEDS_CLARIFICATION",
    "RESEARCH_PLAN_CONFIRMATION": "AWAITING_CONFIRMATION",
    "LIMITATION": "LIMITED",
}


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARACTERS)


class PlanReply(BaseModel):
    """history_mode SERVER: the user's explicit decision on the conversation's latest Research Plan. The server keeps
    the plan and token and builds the continuation itself (phase H2)."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(pattern=r"^rp_[0-9a-f]{24}$")
    action: Action
    revision_instruction: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _instruction(self) -> "PlanReply":
        if self.revision_instruction is not None and self.action != "REVISE":
            raise ValueError("revision_instruction is only for action REVISE")
        return self


class AgentRunRequest(BaseModel):
    """Caller input. extra="forbid" means callers cannot smuggle in system prompts."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=MAX_HISTORY_ITEMS)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # The user's reply to a Research Plan: the exact plan, plan_id, origin_request_id and token of the latest
    # RESEARCH_PLAN_CONFIRMATION response, plus an explicit action when the caller has one (APPROVE, REVISE, CANCEL).
    # A research_plan/v2 (Multi-Angle Research) continuation also carries the research data plan the backend returned.
    continuation: ContinuationInV2 | ContinuationIn | None = None
    # CLIENT (default): the caller sends the history, as before. SERVER (AI_ENABLE_CONVERSATION_STORE): the service
    # keeps it; send conversation_id (null for a new conversation), a new request_id and the message, no history.
    history_mode: Literal["CLIENT", "SERVER"] = "CLIENT"
    # SERVER only: an explicit APPROVE, REVISE or CANCEL of the latest Research Plan; a free-text reply without it is
    # read by the reply classifier.
    plan_reply: PlanReply | None = None
    # AI_ENABLE_ANALYSIS_PATH: ANALYSIS or RESEARCH fixes this request's data-need mode (a data need in the other mode
    # is refused); null keeps the model's choice. ANALYSIS cannot be combined with a Research Plan reply.
    analysis_path: AnalysisPath | None = None

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

    @field_validator("metadata")
    @classmethod
    def _metadata_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON-serializable") from exc
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata must not exceed {MAX_METADATA_BYTES} bytes")
        return value


Verdict = Literal["SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE", "NOT_EVALUATED"]


class FindingInterpretation(BaseModel):
    """The model's reading of one experiment (research findings v1); the verdict itself is the backend's."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=2000,
                        description="The direct answer to the user's question in the verdict's terms.")
    evidence: str = Field(min_length=1, max_length=3000,
                          description="What the numbers say: effect size against the baseline, how often the "
                                      "outcome happened against its base rate, and how certain (sample category, "
                                      "uncertainty, smallest detectable effect).")
    usefulness: str = Field(min_length=1, max_length=2000,
                            description="Why it matters for the user's decision, sized in practical terms.")
    follow_up: str = Field(min_length=1, max_length=2000,
                           description="The most informative next step; never a buy or sell recommendation.")

    @field_validator("answer", "evidence", "usefulness", "follow_up")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(min_length=1, max_length=40, description="The approved experiment's hypothesis_id.")
    verdict: Verdict = Field(description="Copied unchanged from the completed analysis's research_findings.")
    interpretation: FindingInterpretation


class AngleFindingEntry(BaseModel):
    """Multi-Angle Research, as the model writes it without value references (the provider schema only)."""

    model_config = ConfigDict(extra="forbid")

    angle_id: str = Field(min_length=1, max_length=40, description="The approved angle's angle_id.")
    status: AngleStatus = Field(description="Copied unchanged from complete_research_run.")
    interpretation: FindingInterpretation


class NarrativeParts(BaseModel):
    """The model's own reading of one angle; the status and the evidence are written by the backend."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=2000,
                        description="The direct answer to the angle's question in its backend status's terms.")
    usefulness: str = Field(min_length=1, max_length=2000,
                            description="Why it matters for the user's decision, sized in practical terms.")
    follow_up: str = Field(min_length=1, max_length=2000,
                           description="The most informative next step; never a buy or sell recommendation.")

    @field_validator("answer", "usefulness", "follow_up")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class AngleNarrative(BaseModel):
    """Multi-Angle Research with value references (#15, 2026-09-30): the model writes the angle id and its reading;
    the orchestrator renders the backend status, sample and statistics (the provider schema only)."""

    model_config = ConfigDict(extra="forbid")

    angle_id: str = Field(min_length=1, max_length=40, description="The approved angle's angle_id.")
    interpretation: NarrativeParts


class AngleInterpretation(BaseModel):
    """One angle's interpretation in a response: evidence is optional while the model writes it (with value
    references the backend renders it)."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=2000)
    evidence: str | None = Field(default=None, max_length=3000)
    usefulness: str = Field(min_length=1, max_length=2000)
    follow_up: str = Field(min_length=1, max_length=2000)

    @field_validator("answer", "usefulness", "follow_up")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class BackendAngleSummary(BaseModel):
    """The backend's finding of one angle, rendered by the orchestrator (never written by the model)."""

    model_config = ConfigDict(extra="forbid")

    status: AngleStatus
    status_reason: str | None = None
    validation_level: str | None = None
    evidence_direction: str | None = None
    effective_sample: float | None = None
    sample_unit: str | None = None
    estimate_kind: str | None = None
    estimate: float | None = None
    ci: list[float | None] | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    confidence_level: float | None = None
    estimate_unit: str | None = None  # P23: FRACTION or PERCENT (the sandbox's declaration); None when unknown


class AngleFindingReport(BaseModel):
    """Multi-Angle Research: one approved angle in the response. The status is the backend's (a model-written status
    that differs is refused by the findings gate); with value references the orchestrator fills status, evidence and
    backend from the backend's finding."""

    model_config = ConfigDict(extra="forbid")

    angle_id: str = Field(min_length=1, max_length=40, description="The approved angle's angle_id.")
    status: AngleStatus | None = Field(default=None, description="Copied unchanged from complete_research_run.")
    interpretation: AngleInterpretation
    backend: BackendAngleSummary | None = None

    @model_serializer(mode="wrap")
    def _without_empty_backend(self, handler: Any) -> Any:
        """backend appears only when the orchestrator rendered it, so responses without value references keep their
        exact shape."""
        data = handler(self)
        if isinstance(data, dict) and data.get("backend") is None:
            data.pop("backend", None)
        return data


class FinalResponse(BaseModel):
    """Runtime validator matching FINAL_RESPONSE_SCHEMA exactly."""

    model_config = ConfigDict(extra="forbid")

    response_type: ResponseType
    answer: str
    # M40 (suite20c, 2026-09-30): like the other null fields, an omitted clarification_question reads as null; the
    # response-type checks below still require it for a CLARIFICATION and refuse it elsewhere
    clarification_question: str | None = None
    assumptions: list[str]
    limitations: list[str]

    @field_validator("assumptions", "limitations", mode="before")
    @classmethod
    def _one_item_list(cls, value: Any) -> Any:
        """M40 (suite20c r01): null where a list is expected is read as an empty list, a single string as a list of
        one; a LIMITATION still needs at least one limitation."""
        if value is None:
            return []
        return [value] if isinstance(value, str) and value.strip() else value
    # Only for RESEARCH_PLAN_CONFIRMATION; every other response carries null. A model that omits the field (the
    # schema without Research Plan confirmation does not list it) is read as null.
    research_plan: ResearchPlanV2 | ResearchPlanFindings | ResearchPlan | None = None
    # AI_ENABLE_METHODOLOGY: how an answer resting on an analysis was reached, in plain words (model-written; its
    # numbers are checked by the provenance gate). Null for clarifications, plans and answers without an analysis.
    methodology: str | None = Field(default=None, max_length=6000)
    # AI_ENABLE_RESEARCH_FINDINGS: one entry per completed research experiment (backend verdict + interpretation);
    # null for every other response. Absent (read as null) when the feature is off. Multi-Angle Research: one
    # AngleFindingReport per approved angle instead.
    research_findings: list[ResearchFinding] | list[AngleFindingReport] | None = None

    @model_serializer(mode="wrap")
    def _without_empty_findings(self, handler: Any) -> Any:
        """research_findings appears only when set, so responses without the feature keep their exact shape."""
        data = handler(self)
        if isinstance(data, dict) and data.get("research_findings") is None:
            data.pop("research_findings", None)
        return data

    @model_validator(mode="after")
    def _consistent_with_type(self) -> "FinalResponse":
        if self.research_findings is not None and len(self.research_findings) > (
                6 if any(isinstance(f, AngleFindingReport) for f in self.research_findings) else 4):
            raise ValueError("research_findings has more entries than a Research Plan allows")
        # a LIMITATION forced by the findings gate keeps the backend's per-angle findings (P09, 2026-09-29); the gate
        # drops any research_findings the model itself puts on a response other than an ANSWER
        backend_limitation = self.response_type == "LIMITATION" and self.research_findings is not None \
            and all(isinstance(f, AngleFindingReport) for f in self.research_findings)
        if self.research_findings is not None and self.response_type != "ANSWER" and not backend_limitation:
            raise ValueError(f"{self.response_type} requires research_findings to be null")
        if self.methodology is not None and self.response_type in ("CLARIFICATION", "RESEARCH_PLAN_CONFIRMATION"):
            raise ValueError(f"{self.response_type} requires methodology to be null")
        if self.response_type == "RESEARCH_PLAN_CONFIRMATION":
            if self.research_plan is None:
                raise ValueError("RESEARCH_PLAN_CONFIRMATION requires research_plan")
            if self.clarification_question is not None:
                raise ValueError("RESEARCH_PLAN_CONFIRMATION requires clarification_question to be null")
            if not self.answer.strip():
                raise ValueError("RESEARCH_PLAN_CONFIRMATION requires the plan rendered for the user in answer")
            return self
        if self.research_plan is not None:
            raise ValueError(f"{self.response_type} requires research_plan to be null")
        if self.response_type == "CLARIFICATION":
            if not (self.clarification_question or "").strip():
                raise ValueError("CLARIFICATION requires a non-empty clarification_question")
            return self
        if self.clarification_question is not None:
            raise ValueError(f"{self.response_type} requires clarification_question to be null")
        if self.response_type == "ANSWER" and not self.answer.strip():
            raise ValueError("ANSWER requires a non-empty answer")
        if self.response_type == "LIMITATION" and not self.limitations:
            raise ValueError("LIMITATION requires at least one limitation")
        return self


FINAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "response_type": {
            "type": "string",
            "enum": ["ANSWER", "CLARIFICATION", "LIMITATION"],
            "description": (
                "ANSWER when the request is answered; CLARIFICATION when a material ambiguity "
                "prevents a reliable answer; LIMITATION when a required capability is unavailable."
            ),
        },
        "answer": {
            "type": "string",
            "description": (
                "The answer for the user. For LIMITATION, what can reliably be said. "
                "Empty string for CLARIFICATION."
            ),
        },
        "clarification_question": {
            "type": ["string", "null"],
            "description": "One focused question when response_type is CLARIFICATION; otherwise null.",
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Reasonable non-material assumptions made to answer.",
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Limitations of the answer, including unavailable capabilities.",
        },
    },
    "required": ["response_type", "answer", "clarification_question", "assumptions", "limitations"],
}


METHODOLOGY_PROPERTY: dict[str, Any] = {
    "type": ["string", "null"],
    "description": (
        "For an ANSWER or LIMITATION that rests on an analysis: how it was reached, in plain words (the data and "
        "period used, filters and exclusions, the calculation steps, statistical methods and their parameters). "
        "Otherwise null."),
}


def final_response_schema(research_plan_confirmation: bool, methodology: bool = False,
                          research_findings: bool = False, multi_angle: bool = False,
                          value_references: bool = False, hypothesis_plans: bool = False) -> dict[str, Any]:
    """FINAL_RESPONSE_SCHEMA, or with Research Plan confirmation the same schema plus RESEARCH_PLAN_CONFIRMATION and a
    required nullable research_plan, and with AI_ENABLE_METHODOLOGY a required nullable methodology; with research
    findings (only together with plan confirmation) the plan's experiments carry the findings values and a required
    nullable research_findings is added. Without the flags the schema is byte-identical to the one before the
    features. Multi-Angle Research (only with plan confirmation) replaces the plan with research_plan/v2 and the
    findings with one AngleFindingReport per angle. G3 (AI_ENABLE_HYPOTHESIS_PLAN, 2026-10-02): with hypothesis_plans
    beside Multi-Angle Research both plan forms and both findings forms are accepted."""
    multi_angle = multi_angle and research_plan_confirmation
    dual = hypothesis_plans and multi_angle and research_findings
    schema = _plan_schema(research_plan_confirmation, research_findings and research_plan_confirmation, multi_angle,
                          dual)
    if methodology:
        schema = {**schema, "properties": {**schema["properties"], "methodology": METHODOLOGY_PROPERTY},
                  "required": [*schema["required"], "methodology"]}
    if dual:
        angles, hypotheses = angle_findings_property(value_references), research_findings_property()
        schema = {**schema, "properties": {**schema["properties"], "research_findings": {
            "anyOf": [angles["anyOf"][0], hypotheses["anyOf"][0], {"type": "null"}],
            "description": "For an ANSWER that rests on completed research: one entry per approved angle of a "
                           "multi-angle run, or one per experiment of a hypothesis plan; otherwise null."}},
                  "required": [*schema["required"], "research_findings"]}
    elif multi_angle:
        schema = {**schema, "properties": {**schema["properties"],
                                           "research_findings": angle_findings_property(value_references)},
                  "required": [*schema["required"], "research_findings"]}
    elif research_findings and research_plan_confirmation:
        schema = {**schema, "properties": {**schema["properties"], "research_findings": research_findings_property()},
                  "required": [*schema["required"], "research_findings"]}
    return schema


def research_findings_property() -> dict[str, Any]:
    from .tools.registry import strict_parameters_schema

    return {"anyOf": [{"type": "array", "items": strict_parameters_schema(ResearchFinding)}, {"type": "null"}],
            "description": "For an ANSWER that rests on completed research experiments: one entry per experiment "
                           "with the backend verdict unchanged and your interpretation; otherwise null."}


def angle_findings_property(narrative: bool = False) -> dict[str, Any]:
    from .tools.registry import strict_parameters_schema

    if narrative:
        return {"anyOf": [{"type": "array", "items": strict_parameters_schema(AngleNarrative)}, {"type": "null"}],
                "description": "For an ANSWER that rests on a completed multi-angle research run: your reading of "
                               "each approved angle (the backend adds its status, sample and statistics); otherwise "
                               "null."}
    return {"anyOf": [{"type": "array", "items": strict_parameters_schema(AngleFindingEntry)}, {"type": "null"}],
            "description": "For an ANSWER that rests on a completed multi-angle research run: one entry per approved "
                           "angle with the backend status unchanged and your interpretation; otherwise null."}


def _plan_schema(research_plan_confirmation: bool, research_findings: bool = False,
                 multi_angle: bool = False, dual: bool = False) -> dict[str, Any]:
    if not research_plan_confirmation:
        return FINAL_RESPONSE_SCHEMA
    from .tools.registry import strict_parameters_schema

    plan = strict_parameters_schema(ResearchPlanV2 if multi_angle
                                    else ResearchPlanFindings if research_findings else ResearchPlan)
    plans = [plan, strict_parameters_schema(ResearchPlanFindings)] if dual else [plan]
    properties = dict(FINAL_RESPONSE_SCHEMA["properties"])
    properties["response_type"] = {
        "type": "string", "enum": ["ANSWER", "CLARIFICATION", "RESEARCH_PLAN_CONFIRMATION", "LIMITATION"],
        "description": (
            "ANSWER when the request is answered; CLARIFICATION when a material ambiguity prevents a reliable "
            "answer; RESEARCH_PLAN_CONFIRMATION when a research question needs the user's approval of a Research "
            "Plan before any data is used; LIMITATION when a required capability is unavailable."),
    }
    properties["research_plan"] = {
        "anyOf": [*plans, {"type": "null"}],
        "description": "The Research Plan for RESEARCH_PLAN_CONFIRMATION (answer renders it for the user); "
                       "otherwise null.",
    }
    return {**FINAL_RESPONSE_SCHEMA, "properties": properties,
            "required": [*FINAL_RESPONSE_SCHEMA["required"], "research_plan"]}


class AnalysisSummary(BaseModel):
    """One Python analysis of this run, with execution and validation kept separate."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    spec_id: str | None = None
    execution_status: str
    validation_status: str | None = None
    validation_level: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class NumberProvenance(BaseModel):
    """How many numbers in the final answer were checked, and which had no governed source."""

    model_config = ConfigDict(extra="forbid")

    checked: int
    unsupported: list[str] = Field(default_factory=list)


EvidenceLabel = Literal["FACT", "DATABASE_AGGREGATE", "CALCULATION_VERIFIED", "SCOPE_VERIFIED",
                        "DATA_COVERAGE_VERIFIED", "UNVERIFIED_EXPLORATORY", "NOT_VALIDATED"]


V2_EXPERIMENT_FIELDS = ("payload_version", "angle_id", "method_id", "method_family", "status", "status_reason",
                        "bundle_group_id", "research_run_id")


class ExperimentSummary(BaseModel):
    """One analysis spec of the run: the Research Governor's decision, validation, evidence, and whether the final
    answer relies on it (RETAINED: the answer cites its numbers). A Multi-Angle Research run reports one entry per
    approved angle with payload_version research_findings/v2; the v2 fields are omitted otherwise."""

    model_config = ConfigDict(extra="forbid")

    spec_id: str
    evidence_standard: str
    hypothesis_id: str | None = None
    followup_of: str | None = None
    governor_decision: str | None = None
    analysis_id: str | None = None
    execution_status: str | None = None
    validation_status: str | None = None
    validation_level: str | None = None
    evidence_decision: str | None = None
    evidence_level: str | None = None
    retained: Literal["RETAINED", "DISCARDED", "FOLLOWED_UP", "NOT_RUN"]
    payload_version: str | None = None
    angle_id: str | None = None
    method_id: str | None = None
    method_family: str | None = None
    status: str | None = None
    status_reason: str | None = None
    bundle_group_id: str | None = None
    research_run_id: str | None = None

    @model_serializer(mode="wrap")
    def _without_unused_v2(self, handler: Any) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for key in V2_EXPERIMENT_FIELDS:
                if data.get(key) is None:
                    data.pop(key, None)
        return data


class ResearchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiments: list[ExperimentSummary] = Field(default_factory=list)


class ModeExecution(BaseModel):
    """Produced by code (app/modes.py): the mode that answered the request (1 AUTO, 2 ANALYSIS, 3 RESEARCH, 4 MODE4)
    and why: the caller's analysis_path, the mode of the plan the request replied to, the AI_MODE_SWITCH default, or
    AUTO because the default cannot run on this deployment."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal[1, 2, 3, 4]
    name: Literal["AUTO", "ANALYSIS", "RESEARCH", "MODE4"]
    source: Literal["CALLER", "CONTINUATION", "SWITCH", "FALLBACK"]


class AnalysisPathExecution(BaseModel):
    """Produced by code: the path the caller fixed and how many data needs in the other mode were refused."""

    model_config = ConfigDict(extra="forbid")

    requested: AnalysisPath
    source: Literal["CALLER"] = "CALLER"
    mismatches_refused: int = 0


class ExecutionMetadata(BaseModel):
    """Produced deterministically by code, never by the model."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openrouter"] = "openrouter"
    model: str
    provider_response_id: str | None = None
    iterations: int = 0
    tool_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    # Provider-side prompt caching: input tokens read from / written to the provider's cache (part of
    # input_tokens), and the cost OpenRouter reported for the run's model calls (null when none reported).
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float | None = None
    duration_ms: int = 0
    # Why tools were withdrawn before the final answer: TOOL_CALL_BUDGET or CONTEXT_BUDGET.
    tools_withdrawn_reason: Literal["TOOL_CALL_BUDGET", "CONTEXT_BUDGET"] | None = None
    # Every Python analysis of the run, and what the validation gate did to the final response.
    analyses: list[AnalysisSummary] = Field(default_factory=list)
    validation_gate: Literal["NOT_APPLICABLE", "PASSED", "ANNOTATED", "FORCED_LIMITATION"] = "NOT_APPLICABLE"
    # The answer's numbers checked against governed sources (null when the gate did not check numbers).
    number_provenance: NumberProvenance | None = None
    # AI_ENABLE_METHODOLOGY: the numbers of the methodology note checked the same way (null when there is no note).
    methodology_provenance: NumberProvenance | None = None
    # The run's analysis specs as research experiments (null when no spec was created).
    research: ResearchSummary | None = None
    # DataNeed flow: the final status of the latest complete_analysis (data coverage, sandbox execution,
    # calculation_validation NOT_PERFORMED, evidence label, warnings); null when no analysis was completed.
    analysis_final_status: dict[str, Any] | None = None
    # M25: every completion of the run (analysis_final_status is the latest); absent when there was none
    analysis_final_statuses: list[dict[str, Any]] | None = None
    # Research Plan confirmation: what this request did with a plan (null when confirmation is off or unused).
    research_plan: "ResearchPlanExecution | None" = None
    # AI_ENABLE_ANALYSIS_PATH: present only when the caller fixed the path (omitted, not null, otherwise)
    analysis_path: AnalysisPathExecution | None = None
    # the mode switcher (app/modes.py): which mode answered; set by the API, omitted when not set
    mode: ModeExecution | None = None

    @model_serializer(mode="wrap")
    def _without_unused_path(self, handler: Any) -> Any:
        """analysis_path, mode and analysis_final_statuses appear only when set, so runs without them keep their exact
        shape."""
        data = handler(self)
        if isinstance(data, dict):
            for key in ("analysis_path", "mode", "analysis_final_statuses"):
                if data.get(key) is None:
                    data.pop(key, None)
        return data


class ReplyClassifierUsage(BaseModel):
    """The small classifier that reads a free-text reply to a Research Plan (no tools). Its tokens and cost are also
    included in the run totals above."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "FAILED"]
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None
    latency_ms: int = 0


class ResearchPlanExecution(BaseModel):
    """Produced by code. turn: what this request was allowed to do (PROPOSE: no plan yet; EXECUTE_APPROVED: a verified
    approval; REVISE; REPLAN: the approval could not be verified; CANCEL; UNRELATED). verification: of the
    continuation the caller sent (NOT_PRESENTED without one). guard_rejections: research data needs the guard refused."""

    model_config = ConfigDict(extra="forbid")

    turn: Literal["PROPOSE", "EXECUTE_APPROVED", "REVISE", "REPLAN", "CANCEL", "UNRELATED"]
    verification: Literal["NOT_PRESENTED", "VERIFIED", "RESEARCH_PLAN_TOKEN_INVALID", "RESEARCH_PLAN_TOKEN_EXPIRED"]
    action: Literal["APPROVE", "REVISE", "CANCEL", "UNRELATED"] | None = None
    action_source: Literal["EXPLICIT", "CLASSIFIER"] | None = None
    approved_plan_id: str | None = None
    issued_plan_id: str | None = None
    guard_rejections: int = 0
    classifier: ReplyClassifierUsage | None = None
    # EXECUTE_APPROVED only: whether a RESEARCH data need was submitted (M19: an approval without any attempt stays
    # pending); null on other turns
    research_submitted: bool | None = None
    # the feasibility draft the issued plan was bound to, or the one the approved turn started from
    draft_id: str | None = None
    # Multi-Angle Research only (omitted otherwise): the plan version, the research data plan hash and the research run
    plan_version: str | None = None
    research_data_plan_sha256: str | None = None
    research_run_id: str | None = None

    @model_serializer(mode="wrap")
    def _without_unused_v2(self, handler: Any) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for key in ("plan_version", "research_data_plan_sha256", "research_run_id"):
                if data.get(key) is None:
                    data.pop(key, None)
        return data


class RunError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ClaimAnnotation(BaseModel):
    """P17 (user decision 2026-10-01): one claim the answer makes that the evidence does not support, marked in italics
    in `answer` (start/end of the italic text in `answer`) for a front-end hover; set by code, never by the model."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["CAUSAL", "PREDICTIVE", "PROOF", "VERIFIED_CALCULATION"]
    quote: str
    start: int
    end: int
    note: str


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: RunStatus
    response: FinalResponse | None
    execution: ExecutionMetadata
    error: RunError | None = None
    # Set by code from the evidence the answer's numbers trace to (weakest wins), never by the model.
    # null for clarifications and answers without data-derived numbers.
    evidence_label: EvidenceLabel | None = None
    # Backend-signed continuation of a RESEARCH_PLAN_CONFIRMATION response (never generated by the model); null
    # otherwise. The caller sends plan_id, origin_request_id, the exact plan and the token back with the reply.
    continuation: ContinuationOutV2 | ContinuationOut | None = None
    # Mode 4 (app/mode4.py): the steps of the turn (analysis, research, suggestion) with their own results; absent
    # otherwise, so other responses keep their exact shape
    mode4: dict[str, Any] | None = None
    # P17: claims marked in italics in response.answer; absent when there is none, so other responses keep their shape
    annotations: list[ClaimAnnotation] | None = None
    # M47 (user decision 2026-10-01): the conversation's data record after this run (tables and columns used and read,
    # approved data needs, released outputs with their ref, research angles' data); absent when empty
    data_record: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def _without_mode4(self, handler: Any) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for key in ("mode4", "annotations", "data_record"):
                if data.get(key) is None:
                    data.pop(key, None)
        return data


ExecutionMetadata.model_rebuild()
