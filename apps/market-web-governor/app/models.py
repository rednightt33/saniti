from __future__ import annotations

import ipaddress
import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


CONTRACT_VERSION = "v1"
Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Domain = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253)]


ModelSlotNumber = Annotated[int, Field(ge=1, le=7)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceStandard(StrEnum):
    SINGLE_SOURCE = "SINGLE_SOURCE"
    MULTI_SOURCE = "MULTI_SOURCE"
    CORROBORATED = "CORROBORATED"
    PRIMARY_REQUIRED = "PRIMARY_REQUIRED"


class EvidenceDirection(StrEnum):
    SUPPORT = "SUPPORT"
    REFUTE = "REFUTE"
    BOTH = "BOTH"


class SourceTier(StrEnum):
    PRIMARY = "PRIMARY"
    TRUSTED_SECONDARY = "TRUSTED_SECONDARY"
    SECONDARY = "SECONDARY"
    UNKNOWN = "UNKNOWN"


class Entity(StrictModel):
    entity_type: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")]
    entity_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    aliases: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=10
    )


class Hypothesis(StrictModel):
    hypothesis_id: Id
    statement: ShortText
    falsification_test: ShortText | None = None


class TimeWindow(StrictModel):
    start: date | None = None
    end: date | None = None
    as_of: date | None = None

    @model_validator(mode="after")
    def valid_order(self) -> "TimeWindow":
        if self.start and self.end and self.start > self.end:
            raise ValueError("time_window.start must be on or before time_window.end")
        return self


def _clean_domain(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if "://" in candidate or "/" in candidate or candidate.startswith("."):
        raise ValueError("domains must be hostnames without scheme or path")
    if not re.fullmatch(r"(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", candidate):
        raise ValueError("invalid domain")
    return candidate


class SourcePolicy(StrictModel):
    profile: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")] = "GENERAL"
    minimum_primary_sources: int = Field(default=0, ge=0, le=5)
    minimum_independent_sources: int = Field(default=1, ge=1, le=10)
    allowed_domains: list[Domain] = Field(default_factory=list, max_length=20)
    excluded_domains: list[Domain] = Field(default_factory=list, max_length=20)
    primary_domains: list[Domain] = Field(default_factory=list, max_length=20)
    trusted_secondary_domains: list[Domain] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_domains", "excluded_domains", "primary_domains", "trusted_secondary_domains")
    @classmethod
    def clean_domains(cls, values: list[str]) -> list[str]:
        cleaned = [_clean_domain(value) for value in values]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("domain lists must not contain duplicates")
        return cleaned

    @model_validator(mode="after")
    def no_direct_conflict(self) -> "SourcePolicy":
        overlap = set(self.allowed_domains) & set(self.excluded_domains)
        if overlap:
            raise ValueError(f"allowed_domains and excluded_domains overlap: {sorted(overlap)}")
        return self


class EvidenceCriterion(StrictModel):
    criterion_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")]
    question: ShortText
    required: bool = True
    direction: EvidenceDirection = EvidenceDirection.BOTH
    minimum_sources: int = Field(default=1, ge=1, le=5)
    preferred_source_tiers: list[SourceTier] = Field(default_factory=list, max_length=4)
    document_types: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=8
    )
    inclusion_terms: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=12
    )
    exclusion_terms: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=12
    )


class WebBudget(StrictModel):
    max_searches: int = Field(default=3, ge=1, le=8)
    max_results_per_search: int = Field(default=5, ge=1, le=30)
    max_evidence_items: int = Field(default=12, ge=1, le=40)
    max_output_characters: int = Field(default=32000, ge=4000, le=64000)


class StopConditions(StrictModel):
    all_required_criteria_covered: bool = True
    stop_on_primary_source: bool = False


class WebNeedSpec(StrictModel):
    objective: ShortText
    hypothesis: Hypothesis | None = None
    entities: list[Entity] = Field(default_factory=list, max_length=30)
    time_window: TimeWindow | None = None
    evidence_standard: EvidenceStandard = EvidenceStandard.CORROBORATED
    criteria: list[EvidenceCriterion] = Field(min_length=1, max_length=8)
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)
    budget: WebBudget = Field(default_factory=WebBudget)
    stop_conditions: StopConditions = Field(default_factory=StopConditions)
    locale: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")] = "id-ID"
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] = "Asia/Jakarta"
    model_slot: ModelSlotNumber | None = None

    @model_validator(mode="after")
    def unique_criteria(self) -> "WebNeedSpec":
        ids = [criterion.criterion_id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion_id values must be unique")
        if self.budget.max_searches < len(self.criteria):
            raise ValueError("budget.max_searches must cover every criterion")
        return self


class CreateWebNeedRequest(StrictModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    request_id: Id
    conversation_id: Id | None = None
    web_need: WebNeedSpec


class ExecuteWebNeedRequest(StrictModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    request_id: Id


class FastSearchRequest(StrictModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    request_id: Id
    conversation_id: Id | None = None
    query: ShortText
    time_window: TimeWindow | None = None
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)
    budget: WebBudget = Field(default_factory=WebBudget)
    locale: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")] = "id-ID"
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] = "Asia/Jakarta"
    model_slot: ModelSlotNumber | None = None


def validate_fetch_url(value: str) -> str:
    if len(value) > 2048:
        raise ValueError("url is too long")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("url must be an https URL without user information")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local and private hosts are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address:
        raise ValueError("IP-address URLs are not allowed")
    return value


class FetchRequest(StrictModel):
    contract_version: Literal["v1"] = CONTRACT_VERSION
    request_id: Id
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
    objective: ShortText
    locale: Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")] = "id-ID"
    model_slot: ModelSlotNumber | None = None

    @field_validator("url")
    @classmethod
    def public_https_url(cls, value: str) -> str:
        return validate_fetch_url(value)
