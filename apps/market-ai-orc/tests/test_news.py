"""EXEC-Y Fase 2 (app/news.py): the /v1/ask client and the backend-written sections; only http(s) links, a figure without a
source dropped, failures leave no section."""
from __future__ import annotations

import httpx

from app import news
from test_mode4_plan_first import NEWS


def test_the_client_posts_the_question_with_its_key_and_date() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(path=request.url.path, auth=request.headers["authorization"], body=request.read())
        return httpx.Response(200, json=NEWS)

    client = news.NewsClient("http://web", "k", transport=httpx.MockTransport(handler))
    text, summary = news.run(client, "edge_1-m4w", "Outlook 2027?", "2026-10-09")
    assert seen["path"] == "/v1/ask" and seen["auth"] == "Bearer k" and b'"as_of":"2026-10-09"' in seen["body"]
    assert "Riwayat dan konteks berita" in text and summary["sources"] == 2 and summary["timeline"] == 1


def test_a_failure_or_an_unsafe_link_never_reaches_the_reader() -> None:
    client = news.NewsClient("http://web", "k", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    text, summary = news.run(client, "edge_1-m4w", "Q?", None)
    assert text == "" and summary["status"] == "FAILED"
    unsafe = {**NEWS, "citations": [{"n": 1, "publisher": "x", "url": "javascript:alert(1)"}],
              "answer_cited": "Fakta [1].", "plan": {}}
    text, summary = news.sections(unsafe)
    assert text == "" and summary["sources"] == 0 and summary["evidence"] == []
