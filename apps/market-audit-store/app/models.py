"""Audit Store API v1: request and response models (the OpenAPI contract in openapi/audit-store-v1.json is generated
from these). Every producer payload is bounded; hidden model reasoning has no field anywhere."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

API_VERSION = "audit-store/v1"
SOURCES = ("market-ai-orc", "market-sql-governor", "market-python-sandbox", "market-audit-store")
ROLES = ("RAW_INPUT_PARQUET", "EXTRACTION_MANIFEST", "INPUT_BUNDLE_MANIFEST", "APPROVED_DATANEED_CONTRACT",
         "PYTHON_SOURCE", "TOOL_TRACE", "EXECUTION_TRACE", "OUTPUT", "EXECUTION_MANIFEST", "RUNTIME_MANIFEST",
         "FINAL_RESPONSE", "VALIDATION_RESULT", "ERROR_DETAIL")
MEDIA_TYPES = ("application/json", "application/vnd.apache.parquet", "text/x-python", "text/csv", "text/plain",
               "image/png", "image/svg+xml", "application/octet-stream")
RUN_STATUSES = ("OPEN", "FINALIZING", "COMPLETE", "INCOMPLETE")
ARTIFACT_STATES = ("PENDING", "READY", "REJECTED", "DELETED")
RETENTION_CLASSES = ("STANDARD", "PINNED")

REQUEST_ID = r"^[A-Za-z0-9._:-]{1,200}$"
SHA256 = r"^[0-9a-f]{64}$"
EXECUTION_ID = r"^exe_[0-9a-f]{24}$"
SESSION_ID = r"^sess_[0-9a-f]{24}$"
ARTIFACT_ID = r"^art_[0-9a-f]{32}$"
RUN_ID = r"^run_[0-9a-f]{32}$"
EVENT_TYPE = r"^[a-z][a-z0-9_.]{1,63}$"
MAX_EVENT_PAYLOAD = 16384
FORBIDDEN_KEYS = ("reasoning", "reasoning_content", "reasoning_details", "thinking", "chain_of_thought")

Role = Literal[ROLES]  # type: ignore[valid-type]
MediaType = Literal[MEDIA_TYPES]  # type: ignore[valid-type]


def forbidden_key(value: Any) -> str | None:
    """The first key anywhere in a JSON value that names hidden reasoning, or None."""
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return str(key)
            found = forbidden_key(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = forbidden_key(item)
            if found:
                return found
    return None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRegistration(Strict):
    request_id: str = Field(pattern=REQUEST_ID)
    conversation_id: str | None = Field(default=None, pattern=REQUEST_ID)
    turn_index: int | None = Field(default=None, ge=0)
    parent_request_id: str | None = Field(default=None, pattern=REQUEST_ID)


class RunRef(BaseModel):
    run_id: str
    request_id: str
    status: str


class EventIn(Strict):
    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: str = Field(pattern=EVENT_TYPE)
    occurred_at: datetime
    execution_id: str | None = Field(default=None, pattern=EXECUTION_ID)
    artifact_id: str | None = Field(default=None, pattern=ARTIFACT_ID)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(value, separators=(",", ":"), default=str)) > MAX_EVENT_PAYLOAD:
            raise ValueError("payload exceeds 16 KiB: store it as an artifact and reference artifact_id")
        found = forbidden_key(value)
        if found:
            raise ValueError(f"payload may not carry model reasoning ({found})")
        return value


class EventBatch(Strict):
    events: list[EventIn] = Field(min_length=1, max_length=1000)


class EventAck(BaseModel):
    idempotency_key: str
    seq: int
    duplicate: bool


class EventBatchAck(BaseModel):
    run_id: str
    appended: list[EventAck]


class ArtifactPrepare(Strict):
    sha256: str = Field(pattern=SHA256)
    size_bytes: int = Field(ge=0)
    media_type: MediaType
    upload: bool = True


class UploadTarget(BaseModel):
    method: Literal["PUT"] = "PUT"
    url: str
    headers: dict[str, str]
    expires_at: datetime


class ArtifactPrepared(BaseModel):
    artifact_id: str
    state: str
    deduplicated: bool
    upload: UploadTarget | None


class ArtifactVerified(BaseModel):
    artifact_id: str
    state: str
    rejected_reason: str | None = None


class LinkIn(Strict):
    artifact_id: str = Field(pattern=ARTIFACT_ID)
    role: Role
    execution_id: str | None = Field(default=None, pattern=EXECUTION_ID)
    label: str | None = Field(default=None, min_length=1, max_length=200)


class LinkBatch(Strict):
    links: list[LinkIn] = Field(min_length=1, max_length=500)


class LinkBatchAck(BaseModel):
    run_id: str
    linked: int
    duplicates: int


class Distribution(Strict):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)


class RuntimeInventory(Strict):
    python_version: str = Field(min_length=1, max_length=64)
    python_implementation: str = Field(min_length=1, max_length=64)
    os: str = Field(min_length=1, max_length=200)
    arch: str = Field(min_length=1, max_length=64)
    requirements_sha256: str | None = Field(default=None, pattern=SHA256)
    distributions: list[Distribution] = Field(max_length=2000)


class InputChecksum(Strict):
    position: int = Field(ge=0)
    data_request_id: str | None = Field(default=None, max_length=200)
    dataset_id: str | None = Field(default=None, max_length=200)
    sha256: str = Field(pattern=SHA256)
    size_bytes: int | None = Field(default=None, ge=0)
    ordering: list[str] = Field(default_factory=list, max_length=20)


class ExecutionRecord(Strict):
    execution_id: str = Field(pattern=EXECUTION_ID)
    request_id: str = Field(pattern=REQUEST_ID)
    session_id: str = Field(pattern=SESSION_ID)
    bundle_id: str | None = Field(default=None, max_length=200)
    seq: int = Field(ge=1)
    status: str = Field(min_length=1, max_length=64)
    source_sha256: str | None = Field(default=None, pattern=SHA256)
    runtime: RuntimeInventory | None = None
    git_commit: str | None = Field(default=None, max_length=64)
    deployment_id: str | None = Field(default=None, max_length=100)
    random_seed: int | None = None
    timezone: str | None = Field(default=None, max_length=64)
    declared_imports: list[str] = Field(default_factory=list, max_length=500)
    loaded_distributions: list[Distribution] = Field(default_factory=list, max_length=500)
    prebound_packages: list[str] = Field(default_factory=list, max_length=100)
    stdlib_modules: list[str] = Field(default_factory=list, max_length=2000)
    unresolved_modules: list[str] = Field(default_factory=list, max_length=500)
    input_checksums: list[InputChecksum] = Field(default_factory=list, max_length=100)
    contract_sha256: str | None = Field(default=None, pattern=SHA256)
    resample: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    resource_usage: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ExecutionAck(BaseModel):
    execution_id: str
    run_id: str
    runtime_image_id: str | None
    duplicate: bool


class Finalize(Strict):
    expected: dict[str, list[str]] | None = None


class HoldIn(Strict):
    run_id: str | None = Field(default=None, pattern=RUN_ID)
    artifact_id: str | None = Field(default=None, pattern=ARTIFACT_ID)
    reason: str = Field(min_length=3, max_length=500)


class AccessIn(Strict):
    purpose: str = Field(min_length=3, max_length=500)
    run_id: str | None = Field(default=None, pattern=RUN_ID)


class AccessGrant(BaseModel):
    artifact_id: str
    url: str
    expires_at: datetime
