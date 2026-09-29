import dataclasses
import json
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from datetime import date

from app.ask import (AskRequest, AskService, AskStoreError, clean_citations, merge_sources, parse_when,
                     render_implications, validate_implications, windows)
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
                 reviews=None, sectors=None, forward=None, implications=None, fail_implications=False):
        self.payloads = []
        self.answer = answer
        self.reviews = list(reviews or [])
        self.sectors = sectors or []
        self.forward = forward or []
        self.implications = implications or {"impacts": [], "scenarios": [], "timeline": []}
        self.fail_implications = fail_implications

    def respond(self, payload):
        self.payloads.append(payload)
        if "text" in payload and payload["text"]["format"]["name"] == "next_searches":
            queries = self.reviews.pop(0) if self.reviews else []
            text = json.dumps({"queries": [{"query": q, "reason": "context"} for q in queries]})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.001}}
        if "text" in payload and payload["text"]["format"]["name"] == "implications":
            text = "not json" if self.fail_implications else json.dumps(self.implications)
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.002}}
        if "text" in payload:
            text = json.dumps({"queries": ["Company P akuisisi", "Company P acquisition talks"], "subject": "Company P",
                               "sectors": self.sectors, "forward_queries": self.forward, "after": None,
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


def news_client(body=RSS, seen=None, fail_after=None):
    def handler(request):
        if seen is not None:
            seen.append(str(request.url.params["q"]))
        if fail_after and "after:2024" in str(request.url.params["q"]):
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def service(tmp_path, provider=None, store=None, body=RSS, seen=None, fail_after=None, **settings):
    base = dataclasses.replace(make_settings(str(tmp_path / "s.sqlite3")), **settings)
    return AskService(base, provider or FakeProvider(), store, news_client(body, seen, fail_after))


def answer_payload(provider):
    return next(p for p in reversed(provider.payloads) if "text" not in p and "tools" not in p)


def test_ask_answers_from_numbered_sources_and_takes_dates_from_the_list(tmp_path):
    provider, store = FakeProvider(), MemoryStore()
    result = service(tmp_path, provider, store).ask(
        AskRequest(request_id="ask-test-0001", question="apakah ada pembicaraan sebelum akuisisi Company P?",
                   as_of=date(2026, 9, 29)))

    assert result["status"] == "ANSWERED" and result["stored"] is True
    # Plan, one review (empty: no turn 2), answer, implications; two Exa searches. Turn 0: 2 subject queries x 8
    # windows; turn 1: 4 subject templates x the 2 newest windows.
    assert [("text" in p, "tools" in p) for p in provider.payloads].count((False, True)) == 2
    # model calls: plan, answer and two implications attempts (the fake returns none, so it is retried once)
    assert result["usage"]["model_calls"] == 4 and result["usage"]["review_calls"] == 1
    assert result["usage"]["search_calls"] == 2 and result["usage"]["news_requests"] == 2 * 8 + 4 * 2
    assert len(result["plan"]["windows"]) == 8 and [t["turn"] for t in result["plan"]["turns"]] == [0, 1]
    # The same headline from Google News and Exa is one source; oldest first.
    assert [s["date"] for s in result["sources"]] == ["2025-10-07", "2026-09-18", "2026-09-18"]
    assert result["citations"][0] == {"n": 1, "date": "2025-10-07", "publisher": "News One",
                                      "title": "Company P dikabarkan jajaki penjualan saham",
                                      "url": "https://news.google.com/a1", "via": "google_news"}
    assert {w["code"] for w in result["warnings"]} == {"UNKNOWN_CITATION", "IMPLICATIONS_EMPTY"}
    assert result["answer"] == "Talks were reported on 2025-10-07; the deal was announced on 2026-09-18."
    assert result["answer_cited"] == "Talks were reported on 2025-10-07 [1]; the deal was announced on 2026-09-18 [2]."
    assert [c["n"] for c in result["citations"]] == [1, 2]
    payload = answer_payload(provider)
    assert "[1] 2025-10-07 | News One |" in payload["input"]
    assert "never assign it one" in payload["instructions"]
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
    # "Company P akuisisi" was already used in turn 0 and is dropped; turn 3 is the last one.
    assert [t["turn"] for t in turns] == [0, 1, 2, 3]
    assert [t["queries"] for t in turns[:1] + turns[2:]] == [["Company P akuisisi", "Company P acquisition talks"],
                                                           ["Petrosea kontrak tambang"], ["harga batu bara"]]
    assert result["usage"]["review_calls"] == 2
    assert result["usage"]["news_requests"] == 2 * 8 + 4 * 2 + 8 + 8
    assert sum("harga batu bara" in q for q in seen) == 8
    assert any("after:2024-09-29 before:2024-12-29" in q for q in seen)
    answer_rules = answer_payload(provider)["instructions"]
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
    assert turns[2]["queries"] == ["industri susu olahan", "industri susu olahan regulasi pemerintah"]
    assert turns[2]["reasons"] == ["required: sector", "required: sector regulation"]
    assert len(turns) == 3                                       # turn 3 stays optional: empty review stops
    assert sum(q.startswith("industri susu olahan regulasi pemerintah ") for q in seen) == 8


def test_required_sector_queries_come_first_and_turn_two_is_capped(tmp_path):
    provider = FakeProvider(sectors=["sektor a", "sektor b"], reviews=[["x one", "x two", "x three"], []])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0009", question="Company P", as_of=date(2026, 9, 29)))
    assert result["plan"]["turns"][2]["queries"] == [
        "sektor a", "sektor a regulasi pemerintah", "sektor b", "sektor b regulasi pemerintah", "x one"]


def test_no_sectors_and_an_empty_review_stop_after_turn_one(tmp_path):
    result = service(tmp_path, FakeProvider(reviews=[[]])).ask(
        AskRequest(request_id="ask-test-0010", question="apa BI rate terakhir", as_of=date(2026, 9, 29)))
    assert [t["turn"] for t in result["plan"]["turns"]] == [0, 1]


def test_backward_and_forward_sources_keep_their_shares_when_wider_turns_flood_the_budget():
    spans = windows(date(2026, 9, 29))

    def group(name, count, turn):
        return [{"title": f"{name} {i}", "url": f"https://{name}.example/{i}", "publisher": name, "date": "2026-05-01",
                 "text": "", "via": "google_news", "turn": turn} for i in range(count)]

    merged = merge_sources([group("back", 80, 0), group("fwd", 80, 1), group("wide", 400, 2)], spans, 100)
    assert [sum(item["turn"] == t for item in merged) for t in (0, 1, 2)] == [50, 20, 30]
    few = merge_sources([group("back", 10, 0), group("fwd", 5, 1), group("wide", 400, 2)], spans, 100)
    assert [sum(item["turn"] == t for item in few) for t in (0, 1, 2)] == [10, 5, 85]   # unused shares pass over
    no_wide = merge_sources([group("back", 80, 0), group("fwd", 80, 1)], spans, 100)
    assert [sum(item["turn"] == t for item in no_wide) for t in (0, 1)] == [80, 20]      # and back again


def test_clean_citations_removes_and_renumbers_source_numbers():
    text = "Held at 5.75% [435][486], after hikes [496], [444]; see (source [9]) and [999]."
    clean, cited, order = clean_citations(text, 500)
    assert clean == "Held at 5.75%, after hikes; see (source) and."
    assert cited == "Held at 5.75% [1][2], after hikes [3], [4]; see (source [5]) and ."
    assert order == [435, 486, 496, 444, 9]


def test_answer_rules_ask_for_an_industry_and_policy_section(tmp_path):
    provider = FakeProvider()
    service(tmp_path, provider).ask(AskRequest(request_id="ask-test-0011", question="Company P"))
    assert "Industry & policy context" in answer_payload(provider)["instructions"]


def test_turn_one_runs_ai_forward_queries_and_templates_together_over_the_newest_windows(tmp_path):
    seen = []
    provider = FakeProvider(sectors=["industri susu olahan"],
                            forward=["cukai MBDK 2027", "Company P ekspansi 2027", "Company P rencana 2025"])
    result = service(tmp_path, provider, seen=seen).ask(
        AskRequest(request_id="ask-test-0012", question="Company P", as_of=date(2026, 9, 29)))
    turn1 = result["plan"]["turns"][1]
    assert turn1["queries"][:2] == ["cukai MBDK 2027", "Company P ekspansi 2027"]
    assert "Company P rencana 2027" in turn1["queries"] and "industri susu olahan akan berlaku" in turn1["queries"]
    assert turn1["reasons"][:2] == ["forward: ai", "forward: ai"] and "forward: template" in turn1["reasons"]
    assert len(turn1["queries"]) == 2 + 4 + 4 and turn1["news_requests"] == 10 * 2   # the 2025 query is dropped
    assert "Company P rencana 2025" not in turn1["queries"]
    windows_used = {q.split(" after:")[1] for q in seen if q.startswith("cukai MBDK 2027 ")}
    assert windows_used == {"2026-06-29 before:2026-09-29", "2026-03-29 before:2026-06-29"}
    assert "forward_queries" in provider.payloads[0]["instructions"]


def test_templates_can_be_switched_off_and_a_fallback_runs_when_nothing_else_does(tmp_path):
    only_ai = service(tmp_path, FakeProvider(forward=["cukai MBDK 2027"]), ask_forward_templates=False).ask(
        AskRequest(request_id="ask-test-0013", question="Company P", as_of=date(2026, 9, 29)))
    assert only_ai["plan"]["turns"][1]["queries"] == ["cukai MBDK 2027"]
    nothing = service(tmp_path, FakeProvider(), ask_forward_templates=False).ask(
        AskRequest(request_id="ask-test-0014", question="Company P", as_of=date(2026, 9, 29)))
    assert nothing["plan"]["turns"][1]["queries"] == ["Company P 2027"]
    assert nothing["plan"]["turns"][1]["reasons"] == ["forward: fallback"]


def test_parse_when_reads_days_months_parts_of_years_and_years():
    assert parse_when("23 Oktober 2026") == (date(2026, 10, 23), date(2026, 10, 23))
    assert parse_when("awal 2027") == (date(2027, 1, 1), date(2027, 3, 31))
    assert parse_when("semester II 2026") == (date(2026, 7, 1), date(2026, 12, 31))
    assert parse_when("2027") == (date(2027, 1, 1), date(2027, 12, 31))
    assert parse_when("tahun depan") is None
    assert parse_when("2H25") == (date(2025, 7, 1), date(2025, 12, 31))
    assert parse_when("Q1 26") == (date(2026, 1, 1), date(2026, 3, 31))


def test_implications_keep_only_cited_items_and_future_times_written_in_the_sources():
    items = [{"title": "DPR setujui cukai minuman berpemanis berlaku pada 2027", "text": "", "date": "2026-09-27"},
             {"title": "Tender wajib digelar awal 2027", "text": "", "date": "2026-09-18"},
             {"title": "Laba 2025 naik", "text": "rapat digelar 15 Agustus 2026", "date": "2026-03-01"}]
    parsed = {
        "impacts": [{"affected": "emiten minuman", "direction": "negatif", "channel": "cukai -> harga -> volume",
                     "sources": [1]},
                    {"affected": "tanpa sumber", "direction": "?", "channel": "", "sources": [9]}],
        "scenarios": [{"name": "base", "description": "cukai berlaku", "trigger": "PMK terbit", "sources": [1]}],
        "timeline": [{"event": "Cukai MBDK berlaku", "when_text": "2027", "status": "dijadwalkan", "sources": [1]},
                     {"event": "Tender wajib", "when_text": "awal 2027", "status": "dijadwalkan", "sources": [2]},
                     {"event": "Karangan", "when_text": "Maret 2027", "status": "direncanakan", "sources": [1]},
                     {"event": "Sudah lewat", "when_text": "15 Agustus 2026", "status": "dijadwalkan", "sources": [3]},
                     {"event": "Belum ada tanggal", "when_text": "", "status": "diusulkan", "sources": [2]}],
    }
    out = validate_implications(parsed, items, date(2026, 9, 29))
    assert [e["affected"] for e in out["impacts"]] == ["emiten minuman"]
    assert [e["event"] for e in out["timeline"]] == ["Cukai MBDK berlaku", "Tender wajib", "Belum ada tanggal"]
    text = render_implications(out)
    assert "## Implikasi & yang perlu dipantau" in text and "- 2027 — Cukai MBDK berlaku (dijadwalkan) [1]" in text
    assert "Tanggal belum diumumkan — Belum ada tanggal" in text and "Base: cukai berlaku (pemicu: PMK terbit)" in text


def test_implications_are_appended_without_numbers_and_a_failure_keeps_the_answer(tmp_path):
    implications = {"impacts": [{"affected": "Company P", "direction": "positif", "channel": "akuisisi",
                                 "sources": [2]}], "scenarios": [], "timeline": []}
    result = service(tmp_path, FakeProvider(implications=implications)).ask(
        AskRequest(request_id="ask-test-0015", question="Company P", as_of=date(2026, 9, 29)))
    assert "## Implikasi & yang perlu dipantau" in result["answer"] and "[" not in result["answer"]
    assert "- Company P: positif — akuisisi [2]" in result["answer_cited"]
    assert result["plan"]["implications"]["impacts"][0]["sources"] == [2]
    failed = service(tmp_path, FakeProvider(fail_implications=True)).ask(
        AskRequest(request_id="ask-test-0016", question="Company P", as_of=date(2026, 9, 29)))
    assert failed["status"] == "ANSWERED" and "IMPLICATIONS_FAILED" in {w["code"] for w in failed["warnings"]}
    assert "Implikasi" not in failed["answer"]


def test_empty_implications_are_retried_once_and_flagged(tmp_path):
    provider = FakeProvider()
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0017", question="Company P", as_of=date(2026, 9, 29)))
    calls = [p for p in provider.payloads if "text" in p and p["text"]["format"]["name"] == "implications"]
    assert len(calls) == 2 and len(result["plan"]["implications_attempts"]) == 2
    assert "IMPLICATIONS_EMPTY" in {w["code"] for w in result["warnings"]}
