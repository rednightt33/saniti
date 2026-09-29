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
AnalysisPath = Literal["ANALYSIS", "RESEARCH"]

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


class AngleFindingReport(BaseModel):
    """Multi-Angle Research: the model's reading of one approved angle; the status is the backend's."""

    model_config = ConfigDict(extra="forbid")

    angle_id: str = Field(min_length=1, max_length=40, description="The approved angle's angle_id.")
    status: AngleStatus = Field(description="Copied unchanged from complete_research_run.")
    interpretation: FindingInterpretation


class FinalResponse(BaseModel):
    """Runtime validator matching FINAL_RESPONSE_SCHEMA exactly."""

    model_config = ConfigDict(extra="forbid")

    response_type: ResponseType
    answer: str
    clarification_question: str | None
    assumptions: list[str]
    limitations: list[str]
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
        if self.research_findings is not None and self.response_type != "ANSWER":
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
                          research_findings: bool = False, multi_angle: bool = False) -> dict[str, Any]:
    """FINAL_RESPONSE_SCHEMA, or with Research Plan confirmation the same schema plus RESEARCH_PLAN_CONFIRMATION and a
    required nullable research_plan, and with AI_ENABLE_METHODOLOGY a required nullable methodology; with research
    findings (only together with plan confirmation) the plan's experiments carry the findings values and a required
    nullable research_findings is added. Without the flags the schema is byte-identical to the one before the
    features. Multi-Angle Research (only with plan confirmation) replaces the plan with research_plan/v2 and the
    findings with one AngleFindingReport per angle."""
    multi_angle = multi_angle and research_plan_confirmation
    schema = _plan_schema(research_plan_confirmation, research_findings and research_plan_confirmation, multi_angle)
    if methodology:
        schema = {**schema, "properties": {**schema["properties"], "methodology": METHODOLOGY_PROPERTY},
                  "required": [*schema["required"], "methodology"]}
    if multi_angle:
        schema = {**schema, "properties": {**schema["properties"], "research_findings": angle_findings_property()},
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


def angle_findings_property() -> dict[str, Any]:
    from .tools.registry import strict_parameters_schema

    return {"anyOf": [{"type": "array", "items": strict_parameters_schema(AngleFindingReport)}, {"type": "null"}],
            "description": "For an ANSWER that rests on a completed multi-angle research run: one entry per approved "
                           "angle with the backend status unchanged and your interpretation; otherwise null."}


def _plan_schema(research_plan_confirmation: bool, research_findings: bool = False,
                 multi_angle: bool = False) -> dict[str, Any]:
    if not research_plan_confirmation:
        return FINAL_RESPONSE_SCHEMA
    from .tools.registry import strict_parameters_schema

    plan = strict_parameters_schema(ResearchPlanV2 if multi_angle
                                    else ResearchPlanFindings if research_findings else ResearchPlan)
    properties = dict(FINAL_RESPONSE_SCHEMA["properties"])
    properties["response_type"] = {
        "type": "string", "enum": ["ANSWER", "CLARIFICATION", "RESEARCH_PLAN_CONFIRMATION", "LIMITATION"],
        "description": (
            "ANSWER when the request is answered; CLARIFICATION when a material ambiguity prevents a reliable "
            "answer; RESEARCH_PLAN_CONFIRMATION when a research question needs the user's approval of a Research "
            "Plan before any data is used; LIMITATION when a required capability is unavailable."),
    }
    properties["research_plan"] = {
        "anyOf": [plan, {"type": "null"}],
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
    # Research Plan confirmation: what this request did with a plan (null when confirmation is off or unused).
    research_plan: "ResearchPlanExecution | None" = None
    # AI_ENABLE_ANALYSIS_PATH: present only when the caller fixed the path (omitted, not null, otherwise)
    analysis_path: AnalysisPathExecution | None = None

    @model_serializer(mode="wrap")
    def _without_unused_path(self, handler: Any) -> Any:
        """analysis_path appears only when set, so runs without it keep their exact shape."""
        data = handler(self)
        if isinstance(data, dict) and data.get("analysis_path") is None:
            data.pop("analysis_path", None)
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


ExecutionMetadata.model_rebuild()
