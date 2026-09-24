"""External data sources: the contract a future provider must meet. No provider is connected.

External data would reach an analysis only the way market data does: as a governed dataset whose
manifest carries the provenance below, never as rows handed to the model. This module defines that
contract and the policies the Governor would enforce; it is not wired to any endpoint or tool, and
the provider registry is empty. Every provider starts DISABLED and is usable only once its
configuration and authorization are verified (AVAILABLE).

Point-in-time integrity: for a historical signal dated D, an observation may be used only if it was
available on or before D (availability_timestamp, or publication_timestamp as a declared proxy). A
revised value never replaces the vintage that was available at D. Retrieval time is recorded but
never makes data historically available.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ProviderState(str, Enum):
    DISABLED = "DISABLED"
    CONFIGURED = "CONFIGURED"
    AUTHORIZED = "AUTHORIZED"
    AVAILABLE = "AVAILABLE"
    ERROR = "ERROR"


class ExternalError(Exception):
    """Normalized external-data error: a stable code the orchestrator can act on."""

    CODES = ("EXTERNAL_PROVIDER_UNKNOWN", "EXTERNAL_PROVIDER_DISABLED", "EXTERNAL_PROVIDER_NOT_CONFIGURED",
             "EXTERNAL_PROVIDER_ERROR", "EXTERNAL_RATE_LIMITED", "EXTERNAL_TIMEOUT", "EXTERNAL_RESPONSE_TOO_LARGE",
             "EXTERNAL_REQUEST_TOO_LARGE", "EXTERNAL_INVALID_RESPONSE")

    def __init__(self, code: str, message: str, *, retry_after_seconds: int | None = None) -> None:
        assert code in self.CODES, code
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds

    def as_dict(self) -> dict[str, Any]:
        return {"status": "REJECTED", "reason_code": self.code, "message": str(self),
                "retry_after_seconds": self.retry_after_seconds}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderDescriptor(Strict):
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    dataset_id: str = Field(pattern=r"^[a-z][a-z0-9_.]{1,80}$")
    data_type: Literal["MACRO", "YIELD", "FX", "COMMODITY", "FUNDAMENTAL", "NEWS", "ESTIMATE", "OTHER"]
    source_identity: str = Field(min_length=1, max_length=200, description="Publisher of the data.")
    geography: str | None = Field(default=None, max_length=40)
    entity_id_scheme: str | None = Field(default=None, max_length=40, description="e.g. ISIN, IDX ticker, series id")
    observation_grain: str = Field(max_length=40, description="e.g. daily, monthly, per filing")
    units: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    historical_start: date | None = None
    historical_end: date | None = None
    update_frequency: str | None = Field(default=None, max_length=40)
    point_in_time: bool = Field(description="Whether the provider supplies availability or publication times and "
                                            "vintages suitable for historical tests.")
    revisions: Literal["NONE", "VINTAGED", "OVERWRITTEN"] = "NONE"
    entitlements: list[str] = Field(default_factory=list, max_length=20)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_response_bytes: int = Field(default=16_777_216, ge=1024, le=268_435_456)
    max_request_entities: int = Field(default=100, ge=1, le=10_000)
    state: ProviderState = ProviderState.DISABLED


class ExternalObservation(Strict):
    provider_id: str
    dataset_id: str
    entity_id: str | None = Field(default=None, max_length=80)
    observation_timestamp: datetime = Field(description="The period or moment the value describes.")
    publication_timestamp: datetime | None = Field(default=None, description="When the source published it.")
    availability_timestamp: datetime | None = Field(default=None, description="When it could first be used.")
    retrieval_timestamp: datetime = Field(description="When Saniti retrieved it (never makes data historical).")
    vintage: str | None = Field(default=None, max_length=40, description="Revision or release identifier.")
    value: float | str | None
    unit: str | None = Field(default=None, max_length=40)
    provenance: dict[str, Any] = Field(description="provider_id, request hash, retrieved_by; no credentials.")


class ExternalRequest(Strict):
    provider_id: str
    dataset_id: str
    entities: list[str] = Field(default_factory=list, max_length=10_000)
    start: date | None = None
    end: date | None = None
    purpose: str = Field(min_length=1, max_length=300)


class Provider(Protocol):
    descriptor: ProviderDescriptor

    def fetch(self, request: ExternalRequest) -> list[dict[str, Any]]: ...


class ProviderRegistry:
    """The providers the Governor may use. Empty by default: no external source is connected."""

    def __init__(self, providers: list[Provider] | None = None) -> None:
        self._providers = {p.descriptor.provider_id: p for p in providers or []}

    def describe(self) -> list[dict[str, Any]]:
        """What the model may be told: only AVAILABLE providers appear as usable."""
        return [{"provider_id": p.descriptor.provider_id, "dataset_id": p.descriptor.dataset_id,
                 "data_type": p.descriptor.data_type, "state": p.descriptor.state.value}
                for p in self._providers.values() if p.descriptor.state == ProviderState.AVAILABLE]

    def require(self, provider_id: str) -> Provider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ExternalError("EXTERNAL_PROVIDER_UNKNOWN", f"No external provider {provider_id!r} is registered.")
        state = provider.descriptor.state
        if state == ProviderState.DISABLED:
            raise ExternalError("EXTERNAL_PROVIDER_DISABLED", f"External provider {provider_id!r} is disabled.")
        if state in (ProviderState.CONFIGURED, ProviderState.AUTHORIZED):
            raise ExternalError("EXTERNAL_PROVIDER_NOT_CONFIGURED",
                                f"External provider {provider_id!r} is not verified as available ({state.value}).")
        if state == ProviderState.ERROR:
            raise ExternalError("EXTERNAL_PROVIDER_ERROR", f"External provider {provider_id!r} is in an error state.")
        return provider

    def fetch(self, request: ExternalRequest) -> list[ExternalObservation]:
        provider = self.require(request.provider_id)
        descriptor = provider.descriptor
        if request.dataset_id != descriptor.dataset_id:
            raise ExternalError("EXTERNAL_PROVIDER_UNKNOWN", f"{request.provider_id} does not serve "
                                                             f"{request.dataset_id!r}.")
        if len(request.entities) > descriptor.max_request_entities:
            raise ExternalError("EXTERNAL_REQUEST_TOO_LARGE", f"At most {descriptor.max_request_entities} entities "
                                                              f"per request.")
        try:
            raw = provider.fetch(request)
        except ExternalError:
            raise
        except TimeoutError as exc:
            raise ExternalError("EXTERNAL_TIMEOUT", f"{request.provider_id} did not answer within "
                                                    f"{descriptor.timeout_seconds} s.") from exc
        except Exception as exc:  # noqa: BLE001 - every provider failure is normalized
            raise ExternalError("EXTERNAL_PROVIDER_ERROR", f"{request.provider_id} failed "
                                                           f"({type(exc).__name__}).") from exc
        observations = []
        for item in raw:
            try:
                observation = ExternalObservation.model_validate(item)
            except Exception as exc:  # noqa: BLE001
                raise ExternalError("EXTERNAL_INVALID_RESPONSE", "The provider returned an observation that does "
                                                                 "not meet the external-data contract.") from exc
            if observation.provider_id != descriptor.provider_id:
                raise ExternalError("EXTERNAL_INVALID_RESPONSE", "Observation provenance names another provider.")
            observations.append(observation)
        return observations


def available_at(observation: ExternalObservation) -> datetime | None:
    """When the observation could first be used: availability, else publication (declared proxy)."""
    return observation.availability_timestamp or observation.publication_timestamp


def point_in_time_filter(observations: list[ExternalObservation], signal_date: date
                         ) -> tuple[list[ExternalObservation], list[dict[str, Any]]]:
    """Keep only observations usable for a signal dated signal_date (end of that day, UTC), with one vintage per
    entity and observation period: the latest one available at the signal date. Returns (kept, rejected)."""
    cutoff = datetime.combine(signal_date, time.max, tzinfo=timezone.utc)
    kept: dict[tuple[Any, ...], ExternalObservation] = {}
    rejected: list[dict[str, Any]] = []
    for observation in observations:
        moment = available_at(observation)
        key = (observation.entity_id, observation.observation_timestamp)
        if moment is None:
            rejected.append({"entity_id": observation.entity_id, "reason": "NOT_POINT_IN_TIME",
                             "observation_timestamp": observation.observation_timestamp.isoformat()})
            continue
        moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        if moment > cutoff:
            rejected.append({"entity_id": observation.entity_id, "reason": "FUTURE_AVAILABILITY",
                             "observation_timestamp": observation.observation_timestamp.isoformat(),
                             "available_at": moment.isoformat()})
            continue
        current = kept.get(key)
        if current is None or (available_at(current) or moment) < moment:
            if current is not None:
                rejected.append({"entity_id": observation.entity_id, "reason": "SUPERSEDED_VINTAGE",
                                 "observation_timestamp": current.observation_timestamp.isoformat()})
            kept[key] = observation
        else:
            rejected.append({"entity_id": observation.entity_id, "reason": "SUPERSEDED_VINTAGE",
                             "observation_timestamp": observation.observation_timestamp.isoformat()})
    return list(kept.values()), rejected


DEFAULT_REGISTRY = ProviderRegistry()  # no external provider is connected
