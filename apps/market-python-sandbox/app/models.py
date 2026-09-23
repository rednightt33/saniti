from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .spec import IDENT, SPEC_ID

DatasetId = Annotated[str, StringConstraints(pattern=r"^ds_[0-9a-f]{24}$")]
OutputType = Literal["TABLE", "METRICS", "CHART", "ARTIFACT"]
ExecutionStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED"]
ValidationStatus = Literal["PENDING", "PASS", "INCOMPLETE", "FAILED", "UNVERIFIED"]
ValidationLevel = Literal["EXECUTION_ONLY", "SCOPE_VERIFIED", "CALCULATION_VERIFIED"]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}
ANALYSIS_ID = r"^ana_[0-9a-f]{24}$"
REQUEST_ID = r"^[A-Za-z0-9._:-]{1,128}$"

# Deterministic next step for the model, a pure function of both statuses and the codes.
DATA_ERRORS = {"DATASET_NOT_FOUND", "DATASET_EXPIRED"}
SERVICE_ERRORS = {"SANDBOX_RESTARTED", "SANDBOX_ISOLATION_UNAVAILABLE", "DATASET_UNAVAILABLE",
                  "DATASET_INTEGRITY_ERROR", "DATASET_STORAGE_UNAVAILABLE", "INTERNAL_ERROR", "VALIDATOR_ERROR",
                  "REQUEST_BUDGET_EXCEEDED"}
DATA_SHORTFALL = {"INSUFFICIENT_WARMUP_HISTORY", "PERIOD_NOT_COVERED", "NOT_EXTRACTED"}


def next_action(execution_status: str, validation_status: str | None, error_code: str | None,
                reason_codes: list[str] | None = None) -> str:
    reasons = set(reason_codes or [])
    if execution_status in {"QUEUED", "RUNNING"} or validation_status == "PENDING":
        return "GET_ANALYSIS_RESULT"
    if execution_status == "COMPLETED":
        if validation_status == "PASS":
            return "USE_ANALYSIS_RESULT"
        if validation_status == "UNVERIFIED":
            return "USE_RESULT_WITH_VALIDATION_LIMITATION"
        if validation_status == "INCOMPLETE":
            return "REQUEST_MORE_DATA_OR_REPORT_INCOMPLETE" if reasons & DATA_SHORTFALL else "REPORT_INCOMPLETE_RESULT"
        return "REVISE_ANALYSIS"
    if execution_status == "EXPIRED":
        return "RERUN_ANALYSIS_IF_NEEDED"
    if execution_status == "CANCELLED":
        return "STOP_OR_REFORMULATE"
    if error_code in DATA_ERRORS:
        return "REQUEST_DATA_AGAIN"
    if error_code in SERVICE_ERRORS:
        return "REPORT_LIMITATION"
    if error_code in {"INPUT_LIMIT_EXCEEDED", "INPUT_VALIDATION_FAILED"}:
        return "REVISE_DATA_REQUEST"
    if error_code in {"SPEC_NOT_FOUND", "INPUT_BINDING_MISMATCH"}:
        return "REVISE_SPEC_OR_INPUTS"
    return "REVISE_ANALYSIS"


class InputBinding(BaseModel):
    """One logical input of the approved spec, bound to the Governor dataset_ids that hold it."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(pattern=IDENT)]
    dataset_ids: list[DatasetId] = Field(min_length=1, max_length=8)
    duplicate_policy: Literal["ERROR_ON_CONFLICT", "PREFER_LATEST_SNAPSHOT"] = "ERROR_ON_CONFLICT"

    @field_validator("dataset_ids")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("dataset_ids must be unique")
        return values


class AnalysisRequest(BaseModel):
    """What market-ai-orc submits. Resource limits are never part of a request."""

    model_config = ConfigDict(extra="forbid")

    request_id: Annotated[str, StringConstraints(pattern=REQUEST_ID)]
    spec_id: Annotated[str, StringConstraints(pattern=SPEC_ID)]
    inputs: list[InputBinding] = Field(min_length=1, max_length=4)
    python_code: Annotated[str, StringConstraints(min_length=1, max_length=20000)]
    expected_outputs: list[OutputType] = Field(min_length=1, max_length=4)

    @field_validator("expected_outputs")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("values must be unique")
        return values

    @property
    def dataset_ids(self) -> list[str]:
        return [ds for binding in self.inputs for ds in binding.dataset_ids]


class AnalysisError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    analysis_frames: list[dict[str, Any]] = []


class AnalysisResult(BaseModel):
    """The model-facing analysis record (bounded; no paths, URLs, or credentials)."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    spec_id: str | None = None
    spec_sha256: str | None = None
    execution_status: ExecutionStatus
    validation_status: ValidationStatus
    validation_level: ValidationLevel
    reason_codes: list[str] = []
    next_action: str
    request_id: str
    question: str
    inputs: dict[str, list[str]] = {}
    dataset_ids: list[str]
    expected_outputs: list[str]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    runtime_ms: int | None = None
    retry_after_seconds: int | None = None
    expected_scope: dict[str, Any] = {}
    actual_scope: dict[str, Any] = {}
    outputs: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    validation_evidence: list[dict[str, Any]] = []
    error: AnalysisError | None = None
    diagnostics: dict[str, str] | None = None
    derived_features: list[dict[str, Any]] = []
    derived_feature_definitions: dict[str, Any] | None = None  # harness-written JSON artifact of the definitions
    database_features: list[dict[str, Any]] = []
    self_reported: dict[str, Any] = {}
    lineage: dict[str, Any] = {}
    resource_usage: dict[str, Any] = {}
    outputs_expire_at: str | None = None
