from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    question: str = Field(min_length=3, max_length=8000)
    user_reference: str | None = Field(default=None, max_length=200)


class AnalysisAccepted(BaseModel):
    request_id: str
    status: Literal["PENDING"] = "PENDING"


class AnalysisStatus(BaseModel):
    request_id: str
    status: str
    current_stage: str
    analysis_ready_date: str | None = None
    answer: dict[str, Any] | None = None
    recommended_next_analysis: list[Any] = []
    error_message: str | None = None
    usage: dict[str, int]


FINAL_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "conclusion": {"type": "string"},
        "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "analysis_ready_date": {"type": ["string", "null"]},
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
