from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MESSAGE_CHARACTERS = 16000
MAX_HISTORY_ITEMS = 50
MAX_METADATA_BYTES = 8192

ResponseType = Literal["ANSWER", "CLARIFICATION", "LIMITATION"]
RunStatus = Literal["COMPLETED", "NEEDS_CLARIFICATION", "LIMITED", "FAILED"]

STATUS_BY_RESPONSE_TYPE: dict[str, str] = {
    "ANSWER": "COMPLETED",
    "CLARIFICATION": "NEEDS_CLARIFICATION",
    "LIMITATION": "LIMITED",
}


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARACTERS)


class AgentRunRequest(BaseModel):
    """Caller input. extra="forbid" means callers cannot smuggle in system prompts."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=MAX_HISTORY_ITEMS)
    metadata: dict[str, Any] = Field(default_factory=dict)

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


class FinalResponse(BaseModel):
    """Runtime validator matching FINAL_RESPONSE_SCHEMA exactly."""

    model_config = ConfigDict(extra="forbid")

    response_type: ResponseType
    answer: str
    clarification_question: str | None
    assumptions: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def _consistent_with_type(self) -> "FinalResponse":
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
                        "UNVERIFIED_EXPLORATORY", "NOT_VALIDATED"]


class ExperimentSummary(BaseModel):
    """One analysis spec of the run: the Research Governor's decision, validation, evidence, and whether the final
    answer relies on it (RETAINED: the answer cites its numbers)."""

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


class ResearchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiments: list[ExperimentSummary] = Field(default_factory=list)


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
    # The run's analysis specs as research experiments (null when no spec was created).
    research: ResearchSummary | None = None


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
