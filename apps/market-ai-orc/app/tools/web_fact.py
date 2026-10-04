"""find_web_fact (S4b, PLAN_FINAL_2026-10-04.md Fase 4, user decision K8): one fact that is not in the market data
(group membership, controlling shareholder, company status) from market-web-governor POST /v1/fact, in about 30
seconds. The web governor decides the status from verbatim quotes (CONFIRMED, CONFLICTING, PARTIAL, NOT_FOUND); the
model gets the value, the quotes and their domains, never a guess. The fact is shown to the user as a web source
by the orchestrator ("Fakta web"). lookup_fact is the warehouse's own fact lookup; this tool never reads the data."""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolError, ToolSpec
from .request_data import current_request_id

DESCRIPTION = (
    "One fact that is not in the market data, from the web in about 30 seconds: for example whether a company is "
    "state-owned, its controlling shareholder, its listing status or index membership. The backend searches, keeps "
    "only values quoted verbatim from their sources and returns CONFIRMED (two independent sites or one official), "
    "CONFLICTING (every version), PARTIAL (one site) or NOT_FOUND. Ask one subject and one attribute per call; never "
    "use it for prices, volumes or any figure the database holds.")


class WebFactArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=2, max_length=200, description="The company, ticker or entity, e.g. 'BBCA'.")
    attribute: str = Field(min_length=2, max_length=200,
                           description="What to find about it, e.g. 'state-owned (BUMN) or private'.")


class WebFactClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 40.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport,
                                   headers={"Authorization": f"Bearer {api_key}"})

    def fact(self, request_id: str, subject: str, attribute: str) -> dict[str, Any]:
        try:
            response = self.client.post("/v1/fact", json={"request_id": request_id, "subject": subject,
                                                          "attribute": attribute})
        except httpx.HTTPError as exc:
            raise ToolError(f"the web governor did not answer ({type(exc).__name__})",
                            code="WEB_FACT_UNAVAILABLE") from None
        if response.status_code != 200:
            raise ToolError(f"the web governor returned HTTP {response.status_code}", code="WEB_FACT_UNAVAILABLE")
        return response.json()


def model_view(result: dict[str, Any]) -> dict[str, Any]:
    """What the model reads: the status, the value and each version's quotes and domains (no excerpts)."""
    return {
        "status": result.get("status"), "subject": result.get("subject"), "attribute": result.get("attribute"),
        "value": result.get("value"), "as_of": result.get("as_of"), "cached": result.get("cached"),
        "versions": [{"value": v.get("value"), "domains": v.get("domains"), "official": v.get("official"),
                      "quotes": [{"quote": q.get("quote"), "url": q.get("url"), "date": q.get("date")}
                                 for q in (v.get("quotes") or [])[:3]]}
                     for v in (result.get("versions") or [])[:4]],
        "sources_read": len(result.get("sources") or []),
        "note": ("Cite this as a web source with its domains. CONFLICTING: state every version. PARTIAL or "
                 "NOT_FOUND: say the fact is not confirmed; do not fill it in from memory."),
    }


def web_fact_spec(client: WebFactClient) -> ToolSpec:
    def handler(arguments: WebFactArguments) -> dict[str, Any]:
        result = client.fact(current_request_id.get() or "unknown", arguments.subject, arguments.attribute)
        return model_view(result)

    return ToolSpec(name="find_web_fact", effect="FETCHES_DATA", description=DESCRIPTION, arguments_model=WebFactArguments,
                    handler=handler, timeout_seconds=45.0)
