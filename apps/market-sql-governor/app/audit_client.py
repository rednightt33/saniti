"""Producer client of market-audit-store (contract audit-store/v1).

The published contract is apps/market-audit-store/openapi/audit-store-v1.json. This small client lives inside this
service's root on purpose: Railway rebuilds a service only from its own root, so a shared package outside it would
not be rebuilt. tests/test_audit_contract.py checks every operation and field used here against the published
contract, so a contract change fails this service's tests until the client is updated.

Only single-object, short-lived upload URLs are ever received; this client never lists or reads the audit bucket
and never learns an object key. The audit store verifies every upload itself before it is READY."""
from __future__ import annotations

import hashlib
from typing import Any

import httpx

CONTRACT = "audit-store/v1"
# (method, path) -> request model the body follows; checked against the published contract
OPERATIONS = {
    ("post", "/v1/internal/runs"): "RunRegistration",
    ("post", "/v1/internal/runs/{run_id}/events"): "EventBatch",
    ("post", "/v1/internal/artifacts"): "ArtifactPrepare",
    ("post", "/v1/internal/artifacts/{artifact_id}/verify"): None,
    ("post", "/v1/internal/runs/{run_id}/artifacts"): "LinkBatch",
    ("post", "/v1/internal/executions"): "ExecutionRecord",
    ("post", "/v1/internal/runs/{run_id}/finalize"): "Finalize",
}
FIELDS = {"RunRegistration": {"request_id"}, "EventIn": {"idempotency_key", "event_type", "occurred_at", "payload"},
          "ArtifactPrepare": {"sha256", "size_bytes", "media_type", "upload"},
          "LinkIn": {"artifact_id", "role", "label"}}


class AuditUnavailable(Exception):
    """Retryable: the audit store or the bucket could not be reached, or answered 5xx / 409 (not yet ready)."""


class AuditRejected(Exception):
    """Not retryable as is: the audit store refused the request (4xx) or the upload failed verification."""


class AuditClient:
    def __init__(self, base_url: str, key: str, timeout_seconds: float = 30.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {key}"}
        self._http = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._http.post(self.base_url + path, json=body or {}, headers=self._headers)
        except httpx.HTTPError as exc:
            raise AuditUnavailable(type(exc).__name__) from exc
        if response.status_code >= 500 or response.status_code in (408, 409, 429):
            raise AuditUnavailable(f"HTTP {response.status_code}: {_code(response)}")
        if response.status_code >= 400:
            raise AuditRejected(f"HTTP {response.status_code}: {_code(response)}")
        return response.json()

    def register_run(self, request_id: str) -> str:
        return self._post("/v1/internal/runs", {"request_id": request_id})["run_id"]

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        self._post(f"/v1/internal/runs/{run_id}/events", {"events": events})

    def store_artifact(self, data: bytes, media_type: str) -> str:
        """Upload once (deduplicated by sha256 and size) and wait for the audit store's own verification."""
        prepared = self._post("/v1/internal/artifacts", {"sha256": hashlib.sha256(data).hexdigest(),
                                                         "size_bytes": len(data), "media_type": media_type})
        if prepared["state"] == "READY":
            return prepared["artifact_id"]
        target = prepared.get("upload") or {}
        try:
            uploaded = self._http.put(target["url"], content=data, headers=target.get("headers") or {})
        except (httpx.HTTPError, KeyError) as exc:
            raise AuditUnavailable(f"upload {type(exc).__name__}") from exc
        if uploaded.status_code >= 300:
            raise AuditUnavailable(f"upload HTTP {uploaded.status_code}")
        verified = self._post(f"/v1/internal/artifacts/{prepared['artifact_id']}/verify")
        if verified["state"] != "READY":
            raise AuditRejected(f"verification {verified.get('rejected_reason')}")
        return prepared["artifact_id"]

    def link(self, run_id: str, links: list[dict[str, Any]]) -> None:
        self._post(f"/v1/internal/runs/{run_id}/artifacts", {"links": links})

    def register_execution(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/internal/executions", record)

    def expect(self, run_id: str, expected: dict[str, list[str]]) -> None:
        self._post(f"/v1/internal/runs/{run_id}/finalize", {"expected": expected})


def _code(response: httpx.Response) -> str:
    try:
        return str((response.json().get("error") or {}).get("code") or response.json().get("detail"))[:200]
    except ValueError:
        return "unreadable body"
