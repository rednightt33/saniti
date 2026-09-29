import json
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.ask import MAX_SOURCES, AskRequest, AskService, AskStoreError, merge_sources
from app.main import create_app
from tests.conftest import API_KEY, make_settings

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Company P dikabarkan jajaki penjualan saham - News One</title><link>https://news.google.com/a1</link>
<pubDate>Tue, 07 Oct 2025 03:00:00 GMT</pubDate><source url="https://newsone.example">News One</source></item>
<item><title>Company P umumkan akuisisi - News Two</title><link>https://news.google.com/a2</link>
<pubDate>Fri, 18 Sep 2026 09:00:00 GMT</pubDate><source url="https://newstwo.example">News Two</source></item>
</channel></rss>"""


class FakeProvider:
    def __init__(self, answer="Talks were reported on 2025-10-07 [1]; the deal was announced on 2026-09-18 [2]. [9]"):
        self.payloads = []
        self.answer = answer

    def respond(self, payload):
        self.payloads.append(payload)
        if "text" in payload:
            text = json.dumps({"queries": ["Company P akuisisi", "Company P acquisition talks"], "after": None,
                               "before": None})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.001}}
        if "tools" in payload:
            annotation = {"type": "url_citation", "url": "https://wire.example/2026/09/18/p-deal",
                          "title": "Company P announces acquisition", "content": "Company P said on Friday ..."}
            return {"output": [{"content": [{"type": "output_text", "text": "OK", "annotations": [annotation]}]}],
                    "usage": {"cost": 0.002}}
        return {"output": [{"content": [{"type": "output_text", "text": self.answer}]}], "usage": {"cost": 0.003}}


class MemoryStore:
    def __init__(self, fail=False):
        self.rows = {}
        self.fail = fail

    def get(self, request_id):
        return self.rows.get(request_id)

    def write(self, row):
        if self.fail:
            raise AskStoreError("ask store write failed: OperationalError")
        self.rows[row["request_id"]] = row


def news_client(body=RSS):
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)))


def service(tmp_path, provider=None, store=None, body=RSS):
    return AskService(make_settings(str(tmp_path / "s.sqlite3")), provider or FakeProvider(), store,
                      news_client(body))


def test_ask_answers_from_numbered_sources_and_takes_dates_from_the_list(tmp_path):
    provider, store = FakeProvider(), MemoryStore()
    result = service(tmp_path, provider, store).ask(
        AskRequest(request_id="ask-test-0001", question="apakah ada pembicaraan sebelum akuisisi Company P?"))

    assert result["status"] == "ANSWERED" and result["stored"] is True
    # Two model calls (plan, answer) plus two Exa searches; Google News is fetched by code.
    assert [("text" in p, "tools" in p) for p in provider.payloads].count((False, True)) == 2
    assert result["usage"]["model_calls"] == 2 and result["usage"]["search_calls"] == 4
    # The same headline from Google News and Exa is one source; oldest first.
    assert [s["date"] for s in result["sources"]] == ["2025-10-07", "2026-09-18", "2026-09-18"]
    assert result["citations"][0] == {"n": 1, "date": "2025-10-07", "publisher": "News One",
                                      "title": "Company P dikabarkan jajaki penjualan saham",
                                      "url": "https://news.google.com/a1", "via": "google_news"}
    assert {w["code"] for w in result["warnings"]} == {"UNKNOWN_CITATION"}
    answer_payload = provider.payloads[-1]
    assert "[1] 2025-10-07 | News One |" in answer_payload["input"]
    assert "never assign it one" in answer_payload["instructions"]
    row = store.rows["ask-test-0001"]
    assert row["expires_at"] - datetime.now(UTC) > timedelta(days=29, hours=23)


def test_the_same_request_id_is_replayed_without_calls(tmp_path):
    provider, store = FakeProvider(), MemoryStore()
    ask = service(tmp_path, provider, store)
    first = ask.ask(AskRequest(request_id="ask-test-0002", question="apa keputusan BI rate terakhir"))
    calls = len(provider.payloads)
    second = ask.ask(AskRequest(request_id="ask-test-0002", question="apa keputusan BI rate terakhir"))
    assert len(provider.payloads) == calls
    assert second["replayed"] is True and second["answer"] == first["answer"]


def test_a_store_failure_still_returns_the_answer(tmp_path):
    result = service(tmp_path, store=MemoryStore(fail=True)).ask(
        AskRequest(request_id="ask-test-0003", question="apa narasi pasar suku bunga US"))
    assert result["status"] == "ANSWERED" and result["stored"] is False
    assert "ASK_STORE_WRITE_FAILED" in {w["code"] for w in result["warnings"]}


def test_a_feed_with_a_doctype_is_refused(tmp_path):
    body = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss><channel></channel></rss>'
    result = service(tmp_path, body=body).ask(AskRequest(request_id="ask-test-0004", question="latest Fed release"))
    assert "SEARCH_FAILED" in {w["code"] for w in result["warnings"]}
    assert all(source["via"] == "exa" for source in result["sources"])


def test_merge_keeps_the_newest_sources_and_respects_before():
    items = [{"title": f"headline {i}", "url": f"https://x.example/{i}", "publisher": "x",
              "date": (datetime(2026, 1, 1) + timedelta(days=i)).date().isoformat(), "text": "", "via": "google_news"}
             for i in range(MAX_SOURCES + 20)]
    merged = merge_sources([items], None)
    assert len(merged) == MAX_SOURCES and merged[-1]["title"] == f"headline {MAX_SOURCES + 19}"
    assert all(item["date"] <= "2026-01-10" for item in merge_sources([items], "2026-01-10"))


def test_ask_endpoint_requires_authorization(tmp_path):
    settings = make_settings(str(tmp_path / "s.sqlite3"))
    app = create_app(settings, ask_service=service(tmp_path))
    with TestClient(app) as client:
        assert client.post("/v1/ask", json={"request_id": "ask-test-0005", "question": "x y z"}).status_code == 401
        response = client.post("/v1/ask", json={"request_id": "ask-test-0005", "question": "apa BI rate"},
                               headers={"Authorization": f"Bearer {API_KEY}"})
        assert response.status_code == 200 and response.json()["status"] == "ANSWERED"
