"""External-source extension point: contract, states, normalized errors and point-in-time rules. FIXTURE TEST only:
every provider here is an in-memory mock; no network call is made and no real provider is connected."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.external import (DEFAULT_REGISTRY, ExternalError, ExternalObservation, ExternalRequest, ProviderDescriptor,
                          ProviderRegistry, ProviderState, point_in_time_filter)


def descriptor(state: ProviderState = ProviderState.AVAILABLE, **overrides) -> ProviderDescriptor:
    base = {"provider_id": "mock_macro", "dataset_id": "us_treasury_10y", "data_type": "YIELD",
            "source_identity": "FIXTURE (mock provider)", "observation_grain": "daily", "units": "percent",
            "point_in_time": True, "revisions": "VINTAGED", "max_request_entities": 2, "state": state}
    return ProviderDescriptor(**{**base, **overrides})


def observation(day: str, available: str | None, value: float, vintage: str = "v1", published: str | None = None
                ) -> dict:
    return {"provider_id": "mock_macro", "dataset_id": "us_treasury_10y", "entity_id": "UST10Y",
            "observation_timestamp": f"{day}T00:00:00+00:00",
            "publication_timestamp": f"{published}T00:00:00+00:00" if published else None,
            "availability_timestamp": f"{available}T00:00:00+00:00" if available else None,
            "retrieval_timestamp": "2026-09-24T00:00:00+00:00", "vintage": vintage, "value": value, "unit": "percent",
            "provenance": {"provider_id": "mock_macro", "request_hash": "h" * 16, "retrieved_by": "fixture"}}


class MockProvider:
    def __init__(self, state: ProviderState = ProviderState.AVAILABLE, rows: list[dict] | None = None,
                 failure: Exception | None = None) -> None:
        self.descriptor = descriptor(state)
        self.rows = rows or []
        self.failure = failure
        self.calls = 0

    def fetch(self, request: ExternalRequest) -> list[dict]:
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.rows


def request(**overrides) -> ExternalRequest:
    return ExternalRequest(**{"provider_id": "mock_macro", "dataset_id": "us_treasury_10y", "entities": ["UST10Y"],
                              "purpose": "fixture", **overrides})


def test_no_provider_is_connected_by_default() -> None:
    assert DEFAULT_REGISTRY.describe() == []
    with pytest.raises(ExternalError) as error:
        DEFAULT_REGISTRY.fetch(request())
    assert error.value.code == "EXTERNAL_PROVIDER_UNKNOWN"


def test_providers_default_to_disabled_and_are_never_described_as_usable() -> None:
    assert ProviderDescriptor(provider_id="x_source", dataset_id="x_data", data_type="MACRO", source_identity="s",
                              observation_grain="monthly", point_in_time=False).state == ProviderState.DISABLED
    registry = ProviderRegistry([MockProvider(ProviderState.DISABLED)])
    assert registry.describe() == []


@pytest.mark.parametrize(("state", "code"), [
    (ProviderState.DISABLED, "EXTERNAL_PROVIDER_DISABLED"),
    (ProviderState.CONFIGURED, "EXTERNAL_PROVIDER_NOT_CONFIGURED"),
    (ProviderState.AUTHORIZED, "EXTERNAL_PROVIDER_NOT_CONFIGURED"),
    (ProviderState.ERROR, "EXTERNAL_PROVIDER_ERROR"),
])
def test_unavailable_providers_are_refused_before_any_call(state, code) -> None:
    provider = MockProvider(state)
    with pytest.raises(ExternalError) as error:
        ProviderRegistry([provider]).fetch(request())
    assert error.value.code == code and provider.calls == 0


def test_unknown_provider_is_refused() -> None:
    with pytest.raises(ExternalError) as error:
        ProviderRegistry([MockProvider()]).fetch(request(provider_id="no_such"))
    assert error.value.code == "EXTERNAL_PROVIDER_UNKNOWN"


def test_request_size_limit_is_enforced_before_the_call() -> None:
    provider = MockProvider()
    with pytest.raises(ExternalError) as error:
        ProviderRegistry([provider]).fetch(request(entities=["A", "B", "C"]))
    assert error.value.code == "EXTERNAL_REQUEST_TOO_LARGE" and provider.calls == 0


@pytest.mark.parametrize(("failure", "code"), [
    (TimeoutError(), "EXTERNAL_TIMEOUT"),
    (ExternalError("EXTERNAL_RATE_LIMITED", "slow down", retry_after_seconds=30), "EXTERNAL_RATE_LIMITED"),
    (RuntimeError("boom"), "EXTERNAL_PROVIDER_ERROR"),
])
def test_provider_failures_are_normalized(failure, code) -> None:
    with pytest.raises(ExternalError) as error:
        ProviderRegistry([MockProvider(failure=failure)]).fetch(request())
    assert error.value.code == code
    assert error.value.as_dict()["status"] == "REJECTED"


def test_valid_schema_is_accepted_and_provenance_preserved() -> None:
    rows = [observation("2025-03-01", "2025-03-02", 4.21)]
    kept = ProviderRegistry([MockProvider(rows=rows)]).fetch(request())
    assert kept[0].provenance == {"provider_id": "mock_macro", "request_hash": "h" * 16, "retrieved_by": "fixture"}
    assert kept[0].vintage == "v1" and kept[0].retrieval_timestamp == datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_invalid_observations_are_rejected() -> None:
    rows = [{**observation("2025-03-01", "2025-03-02", 4.21), "credential": "x"}]
    with pytest.raises(ExternalError) as error:
        ProviderRegistry([MockProvider(rows=rows)]).fetch(request())
    assert error.value.code == "EXTERNAL_INVALID_RESPONSE"


def test_K_valid_historical_provenance_passes_the_point_in_time_filter() -> None:
    """FIXTURE TEST K: published before the signal date, so usable historically."""
    items = [ExternalObservation.model_validate(observation("2025-02-28", "2025-03-01", 4.21))]
    kept, rejected = point_in_time_filter(items, date(2025, 3, 1))
    assert len(kept) == 1 and rejected == []


def test_L_publication_after_the_signal_date_is_rejected() -> None:
    """FIXTURE TEST L: a value published on 2025-03-15 cannot appear in a signal dated 2025-03-01."""
    items = [ExternalObservation.model_validate(observation("2025-02-28", None, 4.21, published="2025-03-15"))]
    kept, rejected = point_in_time_filter(items, date(2025, 3, 1))
    assert kept == [] and rejected[0]["reason"] == "FUTURE_AVAILABILITY"


def test_missing_point_in_time_metadata_is_not_usable_historically() -> None:
    items = [ExternalObservation.model_validate(observation("2025-02-28", None, 4.21))]
    kept, rejected = point_in_time_filter(items, date(2025, 3, 1))
    assert kept == [] and rejected[0]["reason"] == "NOT_POINT_IN_TIME"


def test_a_later_revision_never_replaces_the_vintage_available_at_the_signal_date() -> None:
    first = ExternalObservation.model_validate(observation("2025-02-28", "2025-03-01", 4.21, "first_release"))
    revised = ExternalObservation.model_validate(observation("2025-02-28", "2025-04-01", 4.35, "revision"))
    kept, rejected = point_in_time_filter([revised, first], date(2025, 3, 10))
    assert [k.vintage for k in kept] == ["first_release"]
    assert rejected[0]["reason"] == "FUTURE_AVAILABILITY"
    later, _ = point_in_time_filter([revised, first], date(2025, 4, 2))
    assert [k.vintage for k in later] == ["revision"]
