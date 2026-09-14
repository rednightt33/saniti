from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCreate(BaseModel):
    question: str = Field(min_length=3, max_length=8000)
    user_reference: str | None = Field(default=None, max_length=200)


class AnalysisAccepted(BaseModel):
    request_id: str
    status: Literal["PENDING"] = "PENDING"


class AnalyticsWorkerClaim(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)


class AnalyticsWorkerCompletion(BaseModel):
    lease_token: str = Field(min_length=10, max_length=100)
    result: dict[str, Any]


class AnalyticsWorkerFailure(BaseModel):
    lease_token: str = Field(min_length=10, max_length=100)
    error_class: str = Field(min_length=1, max_length=200)
    error_message: str = Field(min_length=1, max_length=2000)


class AnalysisStatus(BaseModel):
    request_id: str
    status: str
    current_stage: str
    analysis_ready_date: str | None = None
    answer: dict[str, Any] | None = None
    recommended_next_analysis: list[Any] = []
    error_message: str | None = None
    usage: dict[str, int]


class RecommendedNextAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    reason: str
    classification: Literal["OPTIONAL", "REQUIRES_NEW_DATA"]


class FinalAnalysis(BaseModel):
    """Runtime validator matching FINAL_RESPONSE_SCHEMA exactly."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    conclusion: str
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    analysis_ready_date: date | None
    evidence_ids: list[str]
    warnings: list[str]
    recommended_next_analysis: list[RecommendedNextAnalysis]


FINAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "conclusion": {"type": "string"},
        "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "analysis_ready_date": {"type": ["string", "null"], "format": "date"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "recommended_next_analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "reason": {"type": "string"},
                    "classification": {"type": "string", "enum": ["OPTIONAL", "REQUIRES_NEW_DATA"]},
                },
                "required": ["description", "reason", "classification"],
            },
        },
    },
    "required": ["answer", "conclusion", "confidence", "analysis_ready_date", "evidence_ids", "warnings", "recommended_next_analysis"],
}
