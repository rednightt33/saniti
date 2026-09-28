from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.provider import ProviderResult
from app.store import SqliteStore


API_KEY = "w" * 40


def make_settings(path: str) -> Settings:
    return Settings.from_env({
        "WEB_GOVERNOR_API_KEY": API_KEY,
        "WEB_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "WEB_GOVERNOR_STORE_PATH": path,
        "WEB_OPENROUTER_MODEL": "test/model",
        "WEB_MAX_CRITERIA": "6",
        "WEB_MAX_SEARCHES": "6",
    })


class FakeProvider:
    name = "openrouter"
    adapter_version = "fake-v1"

    def __init__(self):
        self.prompts = []

    def research_criterion(self, web_need_id, spec, criterion, provider_call_id):
        self.prompts.append((spec, criterion))
        return ProviderResult(
            assessment="SUPPORTED",
            summary="The filing supports the criterion.",
            annotations=[{
                "url": "https://www.idx.co.id/filing.pdf?utm_source=test",
                "title": "Issuer filing",
                "content": "Verified filing excerpt.",
                "published_at": "2026-09-20",
            }],
            provider_call={
                "provider_call_id": provider_call_id,
                "criterion_id": criterion.criterion_id,
                "operation": "SEARCH",
                "provider": "openrouter",
                "adapter_version": "fake-v1",
                "model": "test/model",
                "provider_response_id": "resp_test",
                "status": "SUCCEEDED",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                          "server_tool_use": {"web_search_requests": 1}},
                "response_sha256": "a" * 64,
                "started_at": "2026-09-28T10:00:00+00:00",
                "completed_at": "2026-09-28T10:00:01+00:00",
            },
            applied_policy={"engine": "exa", "max_results": 5, "max_uses": 1,
                            "allowed_domains": [], "excluded_domains": []},
        )

    def fetch_url(self, url, objective, locale, provider_call_id):
        result = self.research_criterion(
            "fetch", type("Spec", (), {})(), type("Criterion", (), {"criterion_id": "fetch"})(), provider_call_id
        )
        return ProviderResult(result.assessment, result.summary, [{
            "url": url, "title": "Fetched page", "content": "Fetched source excerpt.", "published_at": None
        }], result.provider_call | {"operation": "FETCH"}, {"exact_url": url})


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(tmp_path, provider):
    settings = make_settings(str(tmp_path / "web.sqlite3"))
    app = create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {API_KEY}"}
