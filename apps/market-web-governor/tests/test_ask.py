import dataclasses
import json
import re
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from datetime import date

from app.ask import (AskRequest, AskService, AskStoreError, check_dates, clean_citations, drill_windows,
                     history_windows, merge_sources, parse_when,
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
                 reviews=None, sectors=None, forward=None, implications=None, fail_implications=False,
                 reads=None, history=False, former=None, claims=None, cost=0.001, follow_ups=None):
        self.payloads = []
        self.history = history
        self.claims = claims or []
        self.cost = cost
        self.former = former or []
        self.reads = reads or []
        self.follow_ups = follow_ups or []
        self.answer = answer
        self.reviews = list(reviews or [])
        self.sectors = sectors or []
        self.forward = forward or []
        self.implications = implications or {"impacts": [], "scenarios": [], "timeline": []}
        self.fail_implications = fail_implications

    def respond(self, payload, attempts=None):
        self.payloads.append(payload)
        if "text" in payload and payload["text"]["format"]["name"] == "next_searches":
            entry = self.reviews.pop(0) if self.reviews else []
            queries, marks = (entry.get("queries", []), entry.get("claims", [])) if isinstance(entry, dict) else (entry, [])
            text = json.dumps({"claims": marks,
                               "queries": [{"query": q[0], "reason": "context", "year": q[1]} if isinstance(q, tuple)
                                           else {"query": q, "reason": "context", "year": None} for q in queries]})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": self.cost}}
        if "text" in payload and payload["text"]["format"]["name"] == "sources_to_read":
            text = json.dumps({"sources": [{"n": n, "reason": "conflicting figure"} for n in self.reads]})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.001}}
        if "text" in payload and payload["text"]["format"]["name"] == "follow_ups":
            text = json.dumps({"questions": [{"question": q, "why": "it decides the outlook"} for q in self.follow_ups]})
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.001}}
        if "text" in payload and payload["text"]["format"]["name"] == "implications":
            text = "not json" if self.fail_implications else json.dumps(self.implications)
            return {"output": [{"content": [{"type": "output_text", "text": text}]}], "usage": {"cost": 0.002}}
        if "text" in payload:
            text = json.dumps({"queries": ["Company P akuisisi", "Company P acquisition talks"], "subject": "Company P",
                               "sectors": self.sectors, "forward_queries": self.forward, "after": None,
                               "before": None, "history": self.history, "former_names": self.former,
                               "claims": self.claims})
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
    # model calls: plan, article selection, answer, two implications attempts (none returned, so retried) and the
    # follow-up questions
    assert result["usage"]["model_calls"] == 6 and result["usage"]["review_calls"] == 1
    assert result["usage"]["search_calls"] == 2 and result["usage"]["news_requests"] == 2 * 8 + 4 * 2
    assert len(result["plan"]["windows"]) == 8 and [t["turn"] for t in result["plan"]["turns"]] == [0, 1]
    # The same headline from Google News and Exa is one source; oldest first.
    assert [s["date"] for s in result["sources"]] == ["2025-10-07", "2026-09-18", "2026-09-18"]
    assert result["citations"][0] == {"n": 1, "date": "2025-10-07", "publisher": "News One",
                                      "title": "Company P dikabarkan jajaki penjualan saham",
                                      "url": "https://news.google.com/a1", "via": "google_news"}
    assert {w["code"] for w in result["warnings"]} == {"UNKNOWN_CITATION", "IMPLICATIONS_EMPTY"}
    # Source numbers become "(source)" links to the cited headlines.
    assert result["answer"] == ("Talks were reported on 2025-10-07 ([source](https://news.google.com/a1)); the deal "
                                "was announced on 2026-09-18 ([source](https://wire.example/2026/09/18/p-deal)).")
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
    result = service(tmp_path, provider, seen=seen, ask_max_turns=3).ask(
        AskRequest(request_id="ask-test-0006", question="kenapa saham ptro naik 1 tahun terakhir",
                   as_of=date(2026, 9, 29)))
    turns = result["plan"]["turns"]
    # "Company P akuisisi" was already used in turn 0 and is dropped; with a 3-turn limit turn 3 is the last one.
    assert [t["turn"] for t in turns] == [0, 1, 2, 3]
    assert result["plan"]["stop"]["reason"] == "max_turns"
    assert [t["queries"] for t in turns[:1] + turns[2:]] == [["Company P akuisisi", "Company P acquisition talks"],
                                                           ["Petrosea kontrak tambang"], ["harga batu bara"]]
    assert result["usage"]["review_calls"] == 3  # turns 2 and 3, then a final review for the claim marks
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
    assert "search turn 2 of at most 3" in reviews[0] and "search turn 3 of at most 3" in reviews[1]
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
    assert "## Implikasi & yang perlu dipantau" in result["answer"]
    assert not re.search(r"\[\d+\]", result["answer"]) and "([source](" in result["answer"]
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


def test_answer_dates_must_match_the_cited_source():
    items = [{"date": "2025-12-23", "title": "a", "text": ""}, {"date": "2026-01-05", "title": "b", "text": ""},
             {"date": None, "title": "c", "text": ""}]
    text = ("- Dilema nikel (2026-12-23) [1]\n- Harga naik (2026-01-05) [2]\n- Dua sumber (2027-01-01) [1][2]\n"
            "- Tanpa sumber 2026-12-23")
    fixed, fixes = check_dates(text, items)
    assert fixed.splitlines() == ["- Dilema nikel (2025-12-23) [1]", "- Harga naik (2026-01-05) [2]",
                                  "- Dua sumber () [1][2]", "- Tanpa sumber 2026-12-23"]
    assert fixes == 2
    clean, _, _ = clean_citations(fixed, 3)
    assert "Dua sumber\n" in clean + "\n"


def test_repeated_date_markers_collapse():
    text = "Ekspor (2026-05-07) [1] (2026-05-07) [2] (2026-05-07) [3]. Suntikan (2026-09-15) [4] (tanpa tanggal) [5]."
    clean, _, _ = clean_citations(text, 5)
    assert clean == "Ekspor (2026-05-07). Suntikan (2026-09-15)."


def test_timeline_rules_exclude_forecasts_and_past_events():
    from app.ask import implications_instructions
    text = implications_instructions(date(2026, 9, 29))
    assert "Not forecasts" in text and "already happened" in text


def test_chosen_articles_are_read_only_when_the_search_finds_the_same_headline(tmp_path):
    provider = FakeProvider(reads=[1, 3, 99])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0020", question="Company P", as_of=date(2026, 9, 29)))
    # [1] and [3] are Google News headlines the Exa search result ("Company P announces acquisition") does not
    # match, so nothing is attached; [99] does not exist and is dropped.
    read = result["plan"]["read"]
    assert [entry["read"] for entry in read] == [False, False]
    assert {w["code"] for w in result["warnings"]} >= {"READ_NONE"}
    provider = FakeProvider(reads=[2])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0021", question="Company P", as_of=date(2026, 9, 29)))
    # [2] is the Exa item "Company P announces acquisition": its search result has the same title.
    assert result["plan"]["read"] == [{"title": "Company P announces acquisition", "reason": "conflicting figure",
                                       "read": True}]
    assert "Company P said on Friday" in answer_payload(provider)["input"]


def test_the_answer_call_reasons_and_can_be_switched_back(tmp_path):
    provider = FakeProvider()
    service(tmp_path, provider).ask(AskRequest(request_id="ask-test-0022", question="Company P",
                                               as_of=date(2026, 9, 29)))
    payload = answer_payload(provider)
    assert payload["reasoning"] == {"enabled": True, "effort": "high"} and payload["max_output_tokens"] == 20000
    assert "what each one measures" in payload["instructions"]
    provider = FakeProvider()
    service(tmp_path, provider, ask_answer_reasoning=False, ask_read_articles=0).ask(
        AskRequest(request_id="ask-test-0023", question="Company P", as_of=date(2026, 9, 29)))
    assert answer_payload(provider)["reasoning"] == {"enabled": False}
    assert not any("text" in p and p["text"]["format"]["name"] == "sources_to_read" for p in provider.payloads)


def test_history_windows_keep_two_years_of_quarters_and_add_older_years():
    spans = history_windows(date(2026, 9, 29))
    assert len(spans) == 8 + 5
    assert spans[0] == (date(2026, 6, 29), date(2026, 9, 29)) and spans[7] == (date(2024, 9, 29), date(2024, 12, 29))
    assert spans[8] == (date(2023, 9, 29), date(2024, 9, 29)) and spans[-1] == (date(2019, 9, 29), date(2020, 9, 29))
    assert drill_windows(2022, date(2026, 9, 29)) == [(date(2022, 10, 1), date(2023, 1, 1)),
                                                      (date(2022, 7, 1), date(2022, 10, 1)),
                                                      (date(2022, 4, 1), date(2022, 7, 1)),
                                                      (date(2022, 1, 1), date(2022, 4, 1))]
    # Cut to the one-year range: the earliest year starts on the range's first day, the latest ends two years back.
    assert drill_windows(2019, date(2026, 9, 29)) == [(date(2019, 10, 1), date(2020, 1, 1)),
                                                      (date(2019, 9, 29), date(2019, 10, 1))]
    assert drill_windows(2024, date(2026, 9, 29))[0] == (date(2024, 7, 1), date(2024, 9, 29))
    assert drill_windows(2025, date(2026, 9, 29)) == [] and drill_windows(2012, date(2026, 9, 29)) == []


def test_a_history_question_adds_older_years_and_drills_into_chosen_years(tmp_path):
    seen = []
    provider = FakeProvider(history=True, former=["Gojek"],
                            reviews=[[("Company P buyback", 2021), ("Company P buyback", 2025), "Company P RUPS"]])
    result = service(tmp_path, provider, seen=seen).ask(
        AskRequest(request_id="ask-test-0030", question="apakah Company P pernah buyback?", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert plan["history"] is True and len(plan["windows"]) == 13
    # Turn 0: two plan queries plus the former name over 8 quarters and 5 older years; turn 1 over 2 quarters.
    assert plan["turns"][0]["queries"] == ["Company P akuisisi", "Company P acquisition talks", "Gojek"]
    assert plan["turns"][0]["news_requests"] == 3 * 13
    assert "Gojek after:2019-09-29 before:2020-09-29" in seen
    assert "Gojek after:2026-06-29 before:2026-09-29" in seen
    # Turn 2: 2021 drills into its 4 quarters; 2025 is already searched by quarter, so it runs as a plain query over
    # every window, like "Company P RUPS".
    turn2 = plan["turns"][2]
    assert turn2["queries"] == ["Company P buyback", "Company P buyback", "Company P RUPS"]
    assert turn2["years"] == [2021, None, None]
    assert "Company P buyback after:2021-04-01 before:2021-07-01" in seen
    assert turn2["news_requests"] == 4 + 13 * 2


def test_an_ordinary_question_ignores_years_from_the_review(tmp_path):
    seen = []
    provider = FakeProvider(reviews=[[("Company P buyback", 2022)]])
    result = service(tmp_path, provider, seen=seen).ask(
        AskRequest(request_id="ask-test-0031", question="Company P", as_of=date(2026, 9, 29)))
    assert result["plan"]["history"] is False and len(result["plan"]["windows"]) == 8
    assert result["plan"]["turns"][2]["years"] == [None]
    assert not any("after:2022-04-01" in q for q in seen)


def covered(index, *sources):
    return {"index": index, "status": "covered", "sources": list(sources)}


def missing(index):
    return {"index": index, "status": "missing", "sources": []}


def test_claims_are_capped_and_default_to_the_question(tmp_path):
    result = service(tmp_path, FakeProvider(claims=[f"point {i}" for i in range(12)])).ask(
        AskRequest(request_id="ask-test-0040", question="Company P", as_of=date(2026, 9, 29)))
    assert [c["claim"] for c in result["plan"]["claims"]] == [f"point {i}" for i in range(8)]
    result = service(tmp_path, FakeProvider()).ask(
        AskRequest(request_id="ask-test-0041", question="apakah Company P pernah buyback?", as_of=date(2026, 9, 29)))
    assert [c["claim"] for c in result["plan"]["claims"]] == ["apakah Company P pernah buyback?"]


def test_the_search_stops_once_every_claim_is_settled_after_the_fixed_turns(tmp_path):
    provider = FakeProvider(claims=["plan", "result"], reviews=[
        {"queries": ["Company P RUPS"], "claims": [covered(1, 1), missing(2)]},
        {"queries": ["never run"], "claims": [covered(1, 1), covered(2, 2)]}])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0042", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert [t["turn"] for t in plan["turns"]] == [0, 1, 2]
    assert plan["stop"]["reason"] == "all_claims_settled" and plan["stop"]["turn"] == 3
    assert [(c["status"], c["sources"]) for c in plan["claims"]] == [("covered", [1]), ("covered", [2])]
    # The answer call gets the checklist with evidence numbers of the final source list.
    assert "CLAIMS:\n1. plan | covered [1]\n2. result | covered [2]" in answer_payload(provider)["input"]
    assert "Tidak terjawab" in answer_payload(provider)["instructions"]


def test_claims_cannot_be_covered_without_sources_or_given_up_before_turn_four(tmp_path):
    provider = FakeProvider(claims=["a", "b"], reviews=[
        {"queries": ["q two"], "claims": [{"index": 1, "status": "covered", "sources": [999]},
                                          {"index": 2, "status": "not_in_news", "sources": []}]},
        {"queries": ["q three"], "claims": [covered(1, 1), {"index": 2, "status": "not_in_news", "sources": []}]},
        {"queries": ["q four"], "claims": [covered(1, 1), {"index": 2, "status": "not_in_news", "sources": []}]}])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0043", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    # Turns 2 and 3 run (claim b cannot be given up before turn 4); at turn 4 it may, so the search stops.
    assert [t["turn"] for t in plan["turns"]] == [0, 1, 2, 3]
    assert plan["stop"] == {**plan["stop"], "reason": "all_claims_settled", "turn": 4}
    assert [c["status"] for c in plan["claims"]] == ["covered", "not_in_news"]


def test_two_turns_without_new_evidence_stop_the_search(tmp_path):
    provider = FakeProvider(claims=["a", "b"], reviews=[
        {"queries": ["q two"], "claims": [covered(1, 1), missing(2)]},
        {"queries": ["q three"], "claims": [covered(1, 1), missing(2)]},
        {"queries": ["q four"], "claims": [covered(1, 1), missing(2)]},
        {"queries": ["q five"], "claims": [covered(1, 1), missing(2)]},
        {"queries": ["q six"], "claims": [covered(1, 1), missing(2)]}])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0044", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    # Reviews at turns 4 and 5 add no evidence: saturated before searching turn 5.
    assert [t["turn"] for t in plan["turns"]] == [0, 1, 2, 3, 4]
    assert plan["stop"]["reason"] == "saturated" and plan["stop"]["turn"] == 5
    assert [c["status"] for c in plan["claims"]] == ["covered", "missing"]


def test_the_search_runs_to_the_turn_limit_and_records_it(tmp_path):
    # A missing point gets evidence in turns 2-4 (no saturation), point d stays missing; the limit is 5 turns.
    done = [covered(1, 1), covered(2, 2), covered(3, 3)]
    reviews = [{"queries": [f"q {n}"], "claims": done[:min(n - 1, 3)] + [missing(4)]} for n in range(2, 7)]
    provider = FakeProvider(claims=["a", "b", "c", "d"], reviews=reviews)
    result = service(tmp_path, provider, ask_max_turns=5).ask(
        AskRequest(request_id="ask-test-0045", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert [t["turn"] for t in plan["turns"]] == [0, 1, 2, 3, 4, 5]
    assert plan["stop"]["reason"] == "max_turns" and plan["stop"]["turn"] == 6
    assert result["usage"]["review_calls"] == 5  # turns 2-5 and the final claim review


def test_the_news_request_limit_trims_a_turn_and_then_stops(tmp_path):
    provider = FakeProvider(claims=["a"], reviews=[{"queries": ["q2 a", "q2 b", "q2 c"]}, {"queries": ["q3 a"]}])
    # Turns 0 and 1 use 2 x 8 + 4 x 2 = 24 requests; a limit of 50 leaves room for 3 queries x 8 windows = 24.
    result = service(tmp_path, provider, ask_max_news_requests=50).ask(
        AskRequest(request_id="ask-test-0046", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert plan["turns"][2]["queries"] == ["q2 a", "q2 b", "q2 c"]
    assert plan["stop"]["reason"] == "max_news_requests" and result["usage"]["news_requests"] == 48
    assert result["status"] == "ANSWERED"


def test_cost_and_time_limits_stop_the_search_but_still_answer(tmp_path):
    provider = FakeProvider(claims=["a"], cost=0.2, reviews=[["q two"], ["q three"], ["q four"]])
    result = service(tmp_path, provider, ask_search_budget_usd=0.5).ask(
        AskRequest(request_id="ask-test-0047", question="Company P", as_of=date(2026, 9, 29)))
    # After two reviews at USD 0.2 (0.405 spent), a third would pass the USD 0.5 search budget: stop before turn 4.
    assert result["plan"]["stop"]["reason"] == "max_cost" and result["plan"]["stop"]["turn"] == 4
    assert result["status"] == "ANSWERED"
    ticks = iter(range(0, 10000, 100))
    ask = service(tmp_path, FakeProvider(claims=["a"], reviews=[["q two"], ["q three"]]), ask_max_seconds=180)
    ask.clock = lambda: next(ticks)
    result = ask.ask(AskRequest(request_id="ask-test-0048", question="Company P", as_of=date(2026, 9, 29)))
    # The clock moves 100 s per reading, and every model call reads it twice for the step timing, so 180 s are
    # gone before turn 2 starts.
    assert result["plan"]["stop"]["reason"] == "max_seconds" and result["plan"]["stop"]["turn"] == 2
    assert result["status"] == "ANSWERED"


def test_evidence_for_a_claim_is_always_kept_in_the_final_sources():
    # An undated turn-2 headline among many dated ones gets no share of a small budget, unless it is evidence.
    old = {"title": "the evidence", "url": "u0", "publisher": "p", "date": None, "text": "", "via": "x", "turn": 2}
    crowd = [{"title": f"news {i}", "url": f"u{i}", "publisher": "p", "date": "2026-09-01", "text": "", "via": "x",
              "turn": 0 if i < 60 else 2} for i in range(1, 110)]
    spans = windows(date(2026, 9, 29))
    assert all(item["title"] != "the evidence" for item in merge_sources([crowd, [old]], spans, 12))
    kept = merge_sources([crowd, [old]], spans, 12, {"theevidence"})
    assert len(kept) == 12 and kept[-1]["title"] == "the evidence"  # undated sorts last


def test_costs_are_counted_per_call_and_per_step_against_three_budgets(tmp_path):
    provider = FakeProvider(claims=["a"], reads=[2], reviews=[["q two"], ["q three"]])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0050", question="Company P", as_of=date(2026, 9, 29)))
    steps = result["usage"]["cost_by_step"]
    assert set(steps) >= {"plan", "review", "exa_search", "answer", "implications", "follow_up"}
    assert round(sum(steps.values()), 6) == round(result["usage"]["cost_usd"], 6)
    timing = result["plan"]["timing"]["steps"]
    assert timing["review"]["costs"] == [0.001] * timing["review"]["calls"]
    assert all(round(sum(entry["costs"]), 6) == steps[step] for step, entry in timing.items())
    budget = result["plan"]["budget"]
    assert budget["max_usd"] == 0.06 and budget["skipped"] == []
    assert budget["search"]["max_usd"] == 0.035 and budget["answer"]["max_usd"] == 0.02
    assert budget["follow_up"] == {"max_usd": 0.005, "spent_usd": 0.001, "over_usd": 0.0}
    assert budget["answer"]["spent_usd"] == round(steps["answer"] + steps["implications"], 6)


def test_the_search_stops_before_a_review_that_would_pass_its_budget(tmp_path):
    # Plan 0.001 + two Exa searches 0.004, then reviews at USD 0.01: after two reviews (0.025 spent) a third
    # (forecast 0.035) passes the 0.028 search budget, so the search stops before turn 4.
    provider = FakeProvider(claims=["a"], cost=0.01, reads=[2], reviews=[["q two"], ["q three"], ["q four"]])
    result = service(tmp_path, provider, ask_search_budget_usd=0.028).ask(
        AskRequest(request_id="ask-test-0051", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert plan["stop"]["reason"] == "max_cost" and plan["stop"]["turn"] == 4
    assert plan["budget"]["search"]["spent_usd"] <= 0.028
    # The search budget has 0.003 left, too little for article selection and a read; the answer budget is
    # separate, so the answer still reasons.
    assert plan["budget"]["skipped"] == ["read"] and "read" not in plan
    assert answer_payload(provider)["reasoning"] == {"enabled": True, "effort": "high"}
    assert result["status"] == "ANSWERED"


def test_a_small_answer_budget_answers_without_reasoning_and_skips_what_does_not_fit(tmp_path):
    provider = FakeProvider(claims=["a"])
    result = service(tmp_path, provider, ask_answer_budget_usd=0.002, ask_followup_budget_usd=0.0).ask(
        AskRequest(request_id="ask-test-0054", question="Company P", as_of=date(2026, 9, 29)))
    plan = result["plan"]
    assert answer_payload(provider)["reasoning"] == {"enabled": False}
    # The answer (USD 0.003) spends the 0.002 answer budget: no implications; no follow-up budget at all.
    assert plan["budget"]["skipped"] == ["answer_reasoning", "implications", "follow_up"]
    assert plan["budget"]["answer"]["over_usd"] == 0.001
    assert all(p.get("text", {}).get("format", {}).get("name") not in ("implications", "follow_ups")
               for p in provider.payloads)
    assert result["status"] == "ANSWERED"


def test_reading_is_cut_to_what_the_search_budget_allows(tmp_path):
    provider = FakeProvider(claims=["a"], reads=[1, 2, 3])
    # Exa searches cost 0.002 each; a search budget of 0.012 leaves about 0.012 - 0.0x spent for reads.
    result = service(tmp_path, provider, ask_search_budget_usd=0.012).ask(
        AskRequest(request_id="ask-test-0052", question="Company P", as_of=date(2026, 9, 29)))
    select = next(p for p in provider.payloads if "text" in p and p["text"]["format"]["name"] == "sources_to_read")
    assert "at most" in select["instructions"]
    read_calls = [p for p in provider.payloads if "tools" in p and p["tools"][0]["parameters"]["max_results"] == 1]
    assert len(read_calls) <= 3 and all(p["tools"][0]["parameters"]["max_results"] == 1 for p in read_calls)


def test_follow_up_questions_come_from_the_final_answer_and_close_it(tmp_path):
    provider = FakeProvider(claims=["a"], follow_ups=["Kapan RUPS Company P?", "kapan rups company p?",
                                                      "Berapa harga akuisisi final?"])
    result = service(tmp_path, provider).ask(
        AskRequest(request_id="ask-test-0055", question="Company P", as_of=date(2026, 9, 29)))
    call = next(p for p in provider.payloads if p.get("text", {}).get("format", {}).get("name") == "follow_ups")
    assert call["input"].startswith("QUESTION: Company P\n\nFINAL ANSWER:\n")
    assert "SOURCES" not in call["input"] and call["reasoning"] == {"enabled": False}
    assert [q["question"] for q in result["plan"]["follow_ups"]] == ["Kapan RUPS Company P?",
                                                                     "Berapa harga akuisisi final?"]
    assert result["answer"].endswith("## Pertanyaan lanjutan\n1. Kapan RUPS Company P? — it decides the outlook\n"
                                     "2. Berapa harga akuisisi final? — it decides the outlook")
    assert result["plan"]["answer_cited"].endswith("2. Berapa harga akuisisi final? — it decides the outlook")


def test_latest_value_questions_are_not_history_and_single_facts_get_few_claims():
    from app.ask import plan_instructions
    text = plan_instructions(date(2026, 9, 30))
    assert "is NOT a history question" in text and "'terakhir kali'" in text
    assert "1 to 3 points about exactly what is asked" in text


def test_saturation_counts_only_new_evidence_for_missing_points(tmp_path):
    # Point a keeps gaining sources, but it is already covered; point b stays missing: saturated after turn 4.
    reviews = [{"queries": [f"q {n}"], "claims": [covered(1, *range(1, min(n, 4))), missing(2)]} for n in range(2, 8)]
    result = service(tmp_path, FakeProvider(claims=["a", "b"], reviews=reviews)).ask(
        AskRequest(request_id="ask-test-0053", question="Company P", as_of=date(2026, 9, 29)))
    assert result["plan"]["stop"]["reason"] == "saturated" and result["plan"]["stop"]["turn"] == 5


def test_date_markers_left_by_removed_numbers_are_merged():
    clean, _, _ = clean_citations("BI menahan 5,75% (23 Sep 2026) [1] (24 Sep 2026) [2] (tanpa tanggal) [3].", 3)
    assert clean == "BI menahan 5,75% (23 Sep 2026, 24 Sep 2026)."
    clean, _, _ = clean_citations("Total 100 bps (23 Sep 2026) [4] dan (tanpa tanggal) [5].", 5)
    assert clean == "Total 100 bps (23 Sep 2026)."


def test_citation_runs_become_source_links():
    urls = ["https://a/x", "https://b/y", "https://c/(z)"]
    clean, cited, _ = clean_citations("Rp32 pada Rabu [1][2]. Reda di Rp28 [3].", 3, urls)
    assert clean == "Rp32 pada Rabu ([source](https://a/x), [source](https://b/y)). Reda di Rp28 ([source](https://c/(z%29))."
    assert cited == "Rp32 pada Rabu [1][2]. Reda di Rp28 [3]."


def test_time_and_attempts_are_recorded_per_step(tmp_path):
    class Slow(FakeProvider):
        def respond(self, payload, attempts=None):
            if attempts is not None and "text" not in payload and "tools" not in payload:
                attempts += [{"seconds": 180.0, "error": "deadline"}, {"seconds": 20.0, "error": None}]
            elif attempts is not None:
                attempts.append({"seconds": 0.1, "error": None})
            return super().respond(payload)

    result = service(tmp_path, Slow()).ask(
        AskRequest(request_id="ask-test-0070", question="Company P", as_of=date(2026, 9, 29)))
    steps = result["plan"]["timing"]["steps"]
    assert steps["answer"]["calls"] == 1 and steps["answer"]["attempts"] == 2
    assert steps["answer"]["failed"] == [{"seconds": 180.0, "error": "deadline"}]
    assert {"plan", "exa_search", "review", "implications"} <= set(steps)
    assert result["plan"]["timing"]["total_seconds"] >= 0


def test_provider_records_each_attempt():
    from app.provider import OpenRouterProvider
    from tests.conftest import make_settings
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"output": [], "usage": {"cost": 0}})

    import tempfile
    provider = OpenRouterProvider(make_settings(tempfile.mkdtemp() + "/s.sqlite3"),
                                  httpx.Client(transport=httpx.MockTransport(handler)))
    attempts = []
    provider.respond({"model": "m", "input": "x"}, attempts)
    assert [a["error"] for a in attempts] == ["HTTP 502", None]
