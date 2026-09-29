import json
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from datetime import date

from app.ask import AskRequest, AskService, AskStoreError, merge_sources, windows
from app.main import create_app
from tests.conftest import API_KEY, make_settings

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Company P dikabarkan jajaki penjualan saham - News One</title><link>https://news.google.com/a1</link>
<pubDate>Tue, 07 Oct 2025 03:00:00 GMT</pubDate><source url="https://newsone.example">News One</source></item>
<item><title>Company P umumkan akuisisi - News Two</title><link>https://news.google.com/a2</link>
<pubDate>Fri, 18 Sep 2026 09:00:00 GMT</pubDate><source url="https://newstwo.example">News Two</source></item>
</channel></rss>"""


class FakeProvider:
    def __init__(self, answer="Talks were reported on 2025-10-07 [1]; the deal was announced on 2026-09-18 [2]. [9]",
                 reviews=None, sectors=None):
        self.payloads = []
        self.answer = answer
        self.reviews = list(reviews or [])
        self.sectors = sectors or []

    def respond(self, payload):
        self.payloads.append(payload)
        if "text" in payload and payload["text"]["format"]["name"] == "next_searches":
            queries = self.reviews.pop(0) if self.reviews else []
            text = json.dumps({"queries": [{"query": q, "reason": "context"} for q in queries]})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.001}}
        if "text" in payload:
            text = json.dumps({"queries": ["Company P akuisisi", "Company P acquisition talks"], "subject": "Company P",
                               "sectors": self.sectors, "after": None, "before": None})
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


def news_client(body=RSS, seen=None, fail_after=None):
    def handler(request):
        if seen is not None:
            seen.append(str(request.url.params["q"]))
        if fail_after and "after:2024" in str(request.url.params["q"]):
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def service(tmp_path, provider=None, store=None, body=RSS, seen=None, fail_after=None):
    return AskService(make_settings(str(tmp_path / "s.sqlite3")), provider or FakeProvider(), store,
                      news_client(body, seen, fail_after))


def test_ask_answers_from_numbered_sources_and_takes_dates_from_the_list(tmp_path):
    provider, store = FakeProvider(), MemoryStore()
    result = service(tmp_path, provider, store).ask(
        AskRequest(request_id="ask-test-0001", question="apakah ada pembicaraan sebelum akuisisi Company P?"))

    assert result["status"] == "ANSWERED" and result["stored"] is True
    # Plan, one review (empty: no second turn), answer; two Exa searches; Google News per query and window by code.
    assert [("text" in p, "tools" in p) for p in provider.payloads].count((False, True)) == 2
    assert result["usage"]["model_calls"] == 2 and result["usage"]["review_calls"] == 1
    assert result["usage"]["search_calls"] == 2 and result["usage"]["news_requests"] == 2 * 8
    assert len(result["plan"]["windows"]) == 8 and [t["turn"] for t in result["plan"]["turns"]] == [1]
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


def test_windows_reach_two_years_back_from_the_question_date_in_three_month_steps():
    spans = windows(date(2026, 9, 29))
    assert len(spans) == 8
    assert spans[0] == (date(2026, 6, 29), date(2026, 9, 29)) and spans[-1] == (date(2024, 9, 29), date(2024, 12, 29))
    stated = windows(date(2026, 9, 29), "2026-01-01", "2026-06-30")
    assert stated[0][1] == date(2026, 6, 30) and stated[-1][0] == date(2026, 1, 1) and len(stated) == 2


def test_merge_shares_the_budget_across_windows():
    spans = windows(date(2026, 9, 29))
    busy = [{"title": f"recent {i}", "url": f"https://x.example/r{i}", "publisher": "x", "date": "2026-09-01",
             "text": "", "via": "google_news"} for i in range(300)]
    quiet = [{"title": f"old {i}", "url": f"https://x.example/o{i}", "publisher": "x", "date": "2024-11-01",
              "text": "", "via": "google_news"} for i in range(5)]
    undated = [{"title": f"undated {i}", "url": f"https://x.example/u{i}", "publisher": "x", "date": None,
                "text": "", "via": "exa"} for i in range(50)]
    late = [{"title": "after the question", "url": "https://x.example/late", "publisher": "x", "date": "2026-10-05",
             "text": "", "via": "google_news"}]
    merged = merge_sources([busy, quiet, undated, late], spans, 100)
    assert len(merged) == 100
    assert sum(1 for item in merged if item["title"].startswith("old")) == 5       # the quiet window keeps all
    assert sum(1 for item in merged if item["date"] is None) == 10                 # a tenth for undated
    assert all(item["title"] != "after the question" for item in merged)
    assert merged[0]["date"] == "2024-11-01"                                       # oldest first


def test_review_turns_broaden_the_search_and_stop_at_three(tmp_path):
    seen = []
    provider = FakeProvider(reviews=[["Petrosea kontrak tambang", "Company P akuisisi"], ["harga batu bara"],
                                     ["never asked"]])
    result = service(tmp_path, provider, seen=seen).ask(
        AskRequest(request_id="ask-test-0006", question="kenapa saham ptro naik 1 tahun terakhir",
                   as_of=date(2026, 9, 29)))
    turns = result["plan"]["turns"]
    # "Company P akuisisi" was already used in turn 1 and is dropped; turn 3 is the last one.
    assert [t["queries"] for t in turns] == [["Company P akuisisi", "Company P acquisition talks"],
                                            ["Petrosea kontrak tambang"], ["harga batu bara"]]
    assert result["usage"]["review_calls"] == 2 and result["usage"]["news_requests"] == 4 * 8
    assert sum("harga batu bara" in q for q in seen) == 8
    assert any("after:2024-09-29 before:2024-12-29" in q for q in seen)
    answer_rules = provider.payloads[-1]["instructions"]
    assert "Separate facts about the subject" in answer_rules
    assert "lead with what is material to an investor" in answer_rules
    assert "mark it as an inference from the cited sources" in answer_rules
    plan_rules = provider.payloads[0]["instructions"]
    assert "both the company's name and its ticker" in plan_rules
    reviews = [p["instructions"] for p in provider.payloads
               if "text" in p and p["text"]["format"]["name"] == "next_searches"]
    assert "search turn 2 of 3" in reviews[0] and "search turn 3 of 3" in reviews[1]
    assert "industry or sector and one on government policy or regulation" in reviews[0]


def test_a_failed_window_is_a_warning_not_an_error(tmp_path):
    result = service(tmp_path, fail_after=True).ask(
        AskRequest(request_id="ask-test-0007", question="apa BI rate terakhir", as_of=date(2026, 9, 29)))
    assert result["status"] == "ANSWERED"
    warning = next(w for w in result["warnings"] if w["code"] == "SEARCH_FAILED")
    assert warning["message"].startswith("4 searches failed")


def test_ask_endpoint_requires_authorization(tmp_path):
    settings = make_settings(str(tmp_path / "s.sqlite3"))
    app = create_app(settings, ask_service=service(tmp_path))
    with TestClient(app) as client:
        assert client.post("/v1/ask", json={"request_id": "ask-test-0005", "question": "x y z"}).status_code == 401
        response = client.post("/v1/ask", json={"request_id": "ask-test-0005", "question": "apa BI rate"},
                               headers={"Authorization": f"Bearer {API_KEY}"})
        assert response.status_code == 200 and response.json()["status"] == "ANSWERED"


def test_turn_two_always_searches_the_sectors_and_their_regulation(tmp_path):
    seen = []
    provider = FakeProvider(sectors=["industri susu olahan"], reviews=[[], []])
    result = service(tmp_path, provider, seen=seen).ask(
        AskRequest(request_id="ask-test-0008", question="Company P", as_of=date(2026, 9, 29)))
    turns = result["plan"]["turns"]
    assert result["plan"]["sectors"] == ["industri susu olahan"]
    assert turns[1]["queries"] == ["industri susu olahan", "industri susu olahan regulasi pemerintah"]
    assert turns[1]["reasons"] == ["required: sector", "required: sector regulation"]
    assert len(turns) == 2                                       # turn 3 stays optional: empty review stops
    assert sum(q.startswith("industri susu olahan regulasi pemerintah ") for q in seen) == 8


def test_required_sector_queries_come_first_and_turn_two_is_capped(tmp_path):
    provider = FakeProvider(sectors=["sektor a", "sektor b"], reviews=[["x one", "x two", "x three"], []])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0009", question="Company P", as_of=date(2026, 9, 29)))
    assert result["plan"]["turns"][1]["queries"] == [
        "sektor a", "sektor a regulasi pemerintah", "sektor b", "sektor b regulasi pemerintah", "x one"]


def test_no_sectors_and_an_empty_review_stop_after_turn_one(tmp_path):
    result = service(tmp_path, FakeProvider(reviews=[[]])).ask(
        AskRequest(request_id="ask-test-0010", question="apa BI rate terakhir", as_of=date(2026, 9, 29)))
    assert [t["turn"] for t in result["plan"]["turns"]] == [1]
