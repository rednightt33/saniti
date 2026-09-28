"""Precursor (pre-event) analysis, publication dates, default source policy, rubric classification, event store."""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app import dates, rubric, sources
from app.config import Settings
from app.event_store import EventStoreError
from app.main import create_app
from app.provider import OpenRouterProvider
from app.store import SqliteStore

from conftest import API_KEY, fake_fetcher

ANCHOR = "2026-09-18"


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {API_KEY}"}


def settings_for(tmp_path, **extra):
    env = {
        "WEB_GOVERNOR_API_KEY": API_KEY,
        "OPENROUTER_API_KEY": "provider-key",
        "WEB_GOVERNOR_STORE_PATH": str(tmp_path / "web.sqlite3"),
        "WEB_OPENROUTER_MODEL": "deepseek/deepseek-v4.1-flash",
        "WEB_SLOT_2_MODEL": "xiaomi/mimo-v2.5",
        "WEB_CLASSIFIER_SLOT": "2",
        "WEB_CLASSIFIER_CHECK_SLOT": "1",
        "WEB_MAX_RESULTS_PER_SEARCH": "30",
        "WEB_MAX_EVIDENCE_ITEMS": "40",
        "WEB_MAX_OUTPUT_CHARACTERS": "64000",
    }
    env.update(extra)
    return Settings.from_env(env)


# --- dates ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("https://www.cnbcindonesia.com/market/20260918154641-17-769090/ultj-beli", (date(2026, 9, 18), "DAY")),
    ("https://market.bisnis.com/read/20260919/192/2005453/x", (date(2026, 9, 19), "DAY")),
    ("https://money.kompas.com/read/2026/09/21/103840126/x", (date(2026, 9, 21), "DAY")),
    ("https://www.example.com/news/2026/03/", (date(2026, 3, 1), "MONTH")),
    ("https://www.idx.co.id/From_EREP/202609/e45bf0b681.pdf", None),
])
def test_publication_date_from_url(url, expected):
    assert dates.from_url(url) == expected


def test_publication_date_priority_text_and_future_rejection():
    assert dates.from_text("Jakarta, 12 September 2026 - PT X announced") == (date(2026, 9, 12), "DAY")
    assert dates.from_text("14 Agu 2026 ... laporan") == (date(2026, 8, 14), "DAY")
    resolved = dates.resolve("2026-05-02T10:00:00Z", None, "https://x.com/2026/06/01/a", None, date(2026, 9, 28))
    assert resolved == {"published_at": "2026-05-02", "published_precision": "DAY", "published_at_source": "PROVIDER"}
    future = dates.resolve(None, None, "https://x.com/2027/01/05/a", None, date(2026, 9, 28))
    assert future["published_at_source"] == "UNKNOWN"


def test_temporal_status_uses_the_whole_publication_period():
    anchor = date(2026, 9, 18)
    assert dates.temporal_status("2026-06-10", "DAY", anchor) == ("PRE_EVENT", 100)
    assert dates.temporal_status("2026-09-18", "DAY", anchor) == ("POST_EVENT_RETROSPECTIVE", None)
    assert dates.temporal_status("2026-08-01", "MONTH", anchor) == ("PRE_EVENT", 48)
    assert dates.temporal_status("2026-09-01", "MONTH", anchor) == ("UNDATED", None)
    assert dates.temporal_status(None, "UNKNOWN", anchor) == ("UNDATED", None)


# --- sources ----------------------------------------------------------------------------------------------------

def test_default_tiers_blocklist_and_copies(monkeypatch):
    assert sources.source_tier("keuangan.kontan.co.id", [], []) == "TRUSTED_SECONDARY"
    assert sources.source_tier("web.ksei.co.id", [], []) == "PRIMARY"
    assert sources.source_tier("emitenhub.com", [], []) == "SECONDARY"
    monkeypatch.setenv("WEB_SOURCE_BLOCKLIST", "copycat.example")
    assert sources.is_blocklisted("www.copycat.example")
    text = "Perseroan berencana mengakuisisi seluruh saham target senilai Rp14 triliun melalui inbreng. " * 4
    evidence = [
        {"evidence_id": "a", "domain": "www.bisnis.com", "source_tier": "TRUSTED_SECONDARY", "excerpt": text},
        {"evidence_id": "b", "domain": "copy.example", "source_tier": "SECONDARY", "excerpt": "Berita: " + text},
    ]
    assert sources.mark_copies(evidence) == 1
    assert evidence[1]["copy_of"] == "a" and evidence[1]["source_verified"] is False
    assert evidence[1]["source_note"].startswith(sources.UNVERIFIED_NOTE)
    assert "copy_of" not in evidence[0]


# --- rubric -----------------------------------------------------------------------------------------------------

def answer(**overrides):
    base = {
        "event_type": "M_AND_A", "event_date": "2026-09-18", "event_date_precision": "DAY",
        "attribution": "OFFICIAL_DOCUMENT", "novelty": "NEW", "impact_scope": "ISSUER",
        "relation_to_anchor": "DIRECT", "materiality_metric": "TRANSACTION_TO_EQUITY_PCT",
        "materiality_value": 178.24, "materiality_evidence": "sekitar 178,24% dari ekuitas",
        "rule_id": "R5-SCALE", "impact_level": 5, "confidence": "HIGH", "rationale": "R5-SCALE: 178% of equity.",
    }
    base.update(overrides)
    return base


QUOTE = "Nilai transaksi sekitar 178,24% dari ekuitas Perseroan, sehingga merupakan transaksi material."


def test_rubric_accepts_a_consistent_answer_and_rejects_inconsistent_ones():
    kwargs = {"anchor": True, "material_pct": 20, "critical_pct": 50}
    assert rubric.validate(answer(), QUOTE, **kwargs)["impact_level"] == 5
    bad = [
        answer(impact_level=4),  # level must equal the rule's level
        answer(materiality_evidence="lebih dari 200% ekuitas"),  # not in the quote
        answer(materiality_metric="NONE"),  # value without a metric
        answer(materiality_metric="NONE", materiality_value=None, materiality_evidence=None),  # R5-SCALE needs it
        answer(event_type="TAKEOVER"),  # outside the list
        answer(relation_to_anchor="NOT_APPLICABLE"),  # an anchor task needs a relation
        answer(event_date=None),  # date and precision disagree
        {**answer(), "extra": 1},
    ]
    for item in bad:
        with pytest.raises(rubric.ClassificationInvalid):
            rubric.validate(item, QUOTE, **kwargs)


def test_certainty_is_decided_by_code_and_rumours_are_capped():
    assert rubric.certainty("PRIMARY", True, "ANONYMOUS_SOURCE") == "OFFICIAL"
    assert rubric.certainty("TRUSTED_SECONDARY", True, "OFFICIAL_DOCUMENT") == "REPORTED"
    assert rubric.certainty("TRUSTED_SECONDARY", True, "ANONYMOUS_SOURCE") == "RUMOUR"
    assert rubric.certainty("PRIMARY", False, "OFFICIAL_DOCUMENT") == "UNVERIFIED"
    capped = rubric.apply_caps(answer(), "RUMOUR")
    assert (capped["impact_level"], capped["confidence"], capped["capped"]) == (4, "MEDIUM", True)


def test_prompt_is_general():
    prompt = rubric.system_prompt(20, 50)
    for specific in ("ULTJ", "Ultrajaya", "Frisian", "BCA", "BBCA", "FrieslandCampina"):
        assert specific not in prompt
    assert "20% but below 50%" in prompt


# --- precursor end to end ---------------------------------------------------------------------------------------

def search_reply(annotations):
    return {
        "id": "r", "status": "completed", "model": "deepseek/deepseek-v4.1-flash",
        "output": [{"type": "openrouter:web_search"}, {"type": "message", "content": [{
            "type": "output_text", "text": "ASSESSMENT: SUPPORTED\nSUMMARY: Found earlier signals.",
            "annotations": annotations}]}],
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "cost": 0.001,
                  "server_tool_use_details": {"web_search_requests": 1}},
    }


def citation(url, content, title="t"):
    return {"type": "url_citation", "url": url, "title": title, "content": content}


PRE_RUMOUR = "Sources say Company P is in talks to buy the dairy unit of Company Q, people familiar said on Monday."
PRE_OFFICIAL = "Company P shareholders approved an increase in authorised capital at the meeting held today."
POST_DEAL = QUOTE + " The agreement was announced on 18 September 2026."


class FakeEventStore:
    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail

    def write(self, rows):
        if self.fail:
            raise EventStoreError("event store write failed: OperationalError")
        self.rows.extend(rows)
        return len(rows)


def classification_for(quote):
    if quote == PRE_RUMOUR:
        return answer(attribution="ANONYMOUS_SOURCE", relation_to_anchor="DIRECT", materiality_metric="NONE",
                      materiality_value=None, materiality_evidence=None, rule_id="R2-SMALL", impact_level=2,
                      event_date=None, event_date_precision="UNKNOWN", confidence="LOW",
                      rationale="R2-SMALL: talks reported without an amount.")
    if quote == PRE_OFFICIAL:
        return answer(event_type="CAPITAL_RAISE", relation_to_anchor="INDIRECT", materiality_metric="NONE",
                      materiality_value=None, materiality_evidence=None, rule_id="R4-CAPITAL", impact_level=4,
                      event_date=None, event_date_precision="UNKNOWN", rationale="R4-CAPITAL: authorised capital.")
    return answer(materiality_evidence="178,24% dari ekuitas")


def app_client(tmp_path, event_store, bad_first=False, check_disagrees=False):
    settings = settings_for(tmp_path)
    calls = []
    state = {"bad": bad_first}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if "text" in payload:  # structured-output classification, several items per call
            context = json.loads(payload["input"])
            entries = []
            for item in context["items"]:
                result = classification_for(item["quote"])
                if state["bad"] and item["quote"] == PRE_RUMOUR:
                    state["bad"] = False
                    result = {**result, "impact_level": 5}  # inconsistent with R2-SMALL: rejected, then retried
                if check_disagrees and payload["model"] == "deepseek/deepseek-v4.1-flash":
                    result = {**result, "rule_id": "R3-SCALE", "impact_level": 3,
                              "materiality_evidence": "178,24% dari ekuitas"}
                entries.append({"item_index": item["item_index"], **result})
            return httpx.Response(200, request=request, json={
                "id": "c", "status": "completed", "model": payload["model"],
                "output": [{"type": "message", "content": [{"type": "output_text",
                                                             "text": json.dumps({"items": entries})}]}],
                "usage": {"input_tokens": 50, "output_tokens": 20, "total_tokens": 70, "cost": 0.0001},
            })
        return httpx.Response(200, request=request, json=search_reply([
            citation("https://www.reuters.com/business/2026/03/02/talks/", PRE_RUMOUR),
            citation("https://www.idx.co.id/news/2026/05/20/agm/", PRE_OFFICIAL),
            citation("https://market.bisnis.com/read/20260919/192/1/deal", POST_DEAL),
        ]))

    provider = OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    app = create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider,
                     fetcher=fake_fetcher(settings), event_store=event_store)
    return TestClient(app), calls


def precursor_request(request_id="pre-1", max_searches=6):
    return {
        "contract_version": "v1", "request_id": request_id,
        "web_need": {
            "objective": "Indications before the announcement that Company P would acquire Company Q's unit.",
            "analysis_mode": "EVENT_PRECURSOR",
            "anchor_event": {"description": "Company P announced the acquisition of Company Q's dairy unit",
                             "event_date": ANCHOR, "tickers": ["PPPP"]},
            "entities": [{"entity_type": "ISSUER", "entity_id": "Company P"},
                         {"entity_type": "COMPANY", "entity_id": "Company Q"}],
            "evidence_standard": "SINGLE_SOURCE",
            "source_policy": {"minimum_independent_sources": 1},
            "budget": {"max_searches": max_searches, "max_results_per_search": 5, "max_evidence_items": 40,
                       "max_output_characters": 64000},
        },
    }


def test_precursor_plan_uses_the_general_template_and_a_twelve_month_window(tmp_path, auth):
    client, _ = app_client(tmp_path, FakeEventStore())
    with client:
        planned = client.post("/v1/web-needs", headers=auth, json=precursor_request()).json()
        too_small = client.post("/v1/web-needs", headers=auth, json=precursor_request("pre-2", max_searches=3))
    assert [task["criterion_id"] for task in planned["plan"]["tasks"]] == [
        "direct_reports", "party_intentions", "capital_and_governance", "existing_ties", "filings_and_regulators",
        "counter_indications"]
    assert all("Before 2026-09-18" in task["search_intent"] for task in planned["plan"]["tasks"])
    assert too_small.status_code == 422 and too_small.json()["code"] == "PRECURSOR_BUDGET_TOO_LOW"


def test_precursor_execution_builds_a_dated_timeline_and_stores_rows(tmp_path, auth):
    store = FakeEventStore()
    client, calls = app_client(tmp_path, store, bad_first=True, check_disagrees=True)
    with client:
        planned = client.post("/v1/web-needs", headers=auth, json=precursor_request()).json()
        result = client.post(f"/v1/web-needs/{planned['web_need_id']}/execute", headers=auth,
                             json={"contract_version": "v1", "request_id": "pre-1"}).json()
        evidence_id = result["timeline"]["pre_event"][0]["evidence_id"]
        stored = client.get(f"/v1/evidence/{evidence_id}", headers=auth).json()

    timeline = result["timeline"]
    assert [entry["published_at"] for entry in timeline["pre_event"]] == ["2026-03-02", "2026-05-20"]
    assert timeline["earliest_direct_signal"]["domain"] == "www.reuters.com"
    assert timeline["earliest_direct_signal"]["lead_time_days"] == 200
    assert timeline["earliest_indirect_signal"]["source_tier"] == "PRIMARY"
    assert [entry["published_at"] for entry in timeline["retrospective_leads"]] == ["2026-09-19"]
    assert "not show that the event was predictable" in timeline["note"]

    classify_calls = [call for call in calls if "text" in call]
    assert all(call["text"]["format"]["type"] == "json_schema" and call["text"]["format"]["strict"]
               for call in classify_calls)
    assert all("tools" not in call for call in classify_calls)
    assert {call["model"] for call in classify_calls} == {"xiaomi/mimo-v2.5", "deepseek/deepseek-v4.1-flash"}
    assert all(call["reasoning"] == {"enabled": False} for call in classify_calls)
    # three distinct sources in one batch: one call and one retry for the rejected item; the two level 4-5
    # sources go to the check model in one call, whose answer for the capital item cites a figure absent from its
    # quote, so it is rejected and retried once
    assert len(classify_calls) == 4

    by_quote = {item["excerpt"]: item["classification"] for item in result["evidence"]}
    rumour = by_quote[PRE_RUMOUR]
    assert rumour["certainty"] == "RUMOUR" and rumour["impact_level"] == 2  # retried after an invalid answer
    official = by_quote[PRE_OFFICIAL]
    assert official["certainty"] == "OFFICIAL"
    assert official["review_status"] == "NEEDS_REVIEW"  # level 4, the check model disagreed
    assert stored["classification"]["status"] == "CLASSIFIED"

    assert len(store.rows) == 3
    row = next(row for row in store.rows if row["quote"] == PRE_RUMOUR)
    assert (row["temporal_status"], row["relation_to_anchor"], row["certainty"]) == ("PRE_EVENT", "DIRECT", "RUMOUR")
    assert row["tickers"] == ["PPPP"] and row["anchor_event_date"] == ANCHOR
    assert [row["card_rank"] for row in store.rows] == [1, 2, 3]
    assert result["event_store"]["written"] == 3


def test_invalid_classifications_are_stored_unclassified_and_store_failures_are_reported(tmp_path, auth):
    store = FakeEventStore(fail=True)
    client, _ = app_client(tmp_path, store)
    original = rubric.validate

    def always_invalid(*args, **kwargs):
        raise rubric.ClassificationInvalid("forced")

    rubric.validate = always_invalid
    try:
        with client:
            planned = client.post("/v1/web-needs", headers=auth, json=precursor_request("pre-x")).json()
            result = client.post(f"/v1/web-needs/{planned['web_need_id']}/execute", headers=auth,
                                 json={"contract_version": "v1", "request_id": "pre-x"}).json()
    finally:
        rubric.validate = original
    assert {item["classification"]["status"] for item in result["evidence"]} == {"UNCLASSIFIED"}
    codes = {warning["code"] for warning in result["warnings"]}
    assert {"CLASSIFICATION_INCOMPLETE", "EVENT_STORE_WRITE_FAILED"} <= codes


# --- hang protection (live 2026-09-28: an execution stopped making calls and never finished, W13) ---------------

def test_a_provider_call_that_trickles_bytes_hits_the_total_deadline(tmp_path):
    import time as _time

    from app.provider import ProviderError

    settings = settings_for(tmp_path, WEB_OPENROUTER_TOTAL_SECONDS="1", WEB_OPENROUTER_MAX_RETRIES="1")

    def trickle():
        for _ in range(20):
            _time.sleep(0.2)
            yield b" "

    def handler(request):
        return httpx.Response(200, request=request, content=trickle())

    provider = OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    started = _time.monotonic()
    with pytest.raises(ProviderError) as exc:
        provider._request({"model": "m", "input": "x"})
    assert exc.value.code == "PROVIDER_TIMEOUT"
    assert _time.monotonic() - started < 3


def test_classification_deadline_marks_unfinished_items_and_classifier_tokens_are_capped(tmp_path, auth):
    import time as _time

    settings = settings_for(tmp_path, WEB_CLASSIFY_DEADLINE_SECONDS="1", WEB_CLASSIFIER_MAX_OUTPUT_TOKENS="2000",
                            WEB_OPENROUTER_MAX_OUTPUT_TOKENS="8000",
                            WEB_CLASSIFIER_CHECK_SLOT="0")
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        if "text" in payload:
            seen.append(payload["max_output_tokens"])
            _time.sleep(3)  # slower than the classification deadline
            return httpx.Response(200, request=request, json={"id": "c", "status": "completed", "output": []})
        return httpx.Response(200, request=request, json=search_reply([
            citation("https://www.reuters.com/business/2026/03/02/talks/", PRE_RUMOUR)]))

    provider = OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    app = create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider,
                     fetcher=fake_fetcher(settings), event_store=FakeEventStore())
    started = _time.monotonic()
    with TestClient(app) as client:
        planned = client.post("/v1/web-needs", headers=auth, json=precursor_request("pre-slow")).json()
        result = client.post(f"/v1/web-needs/{planned['web_need_id']}/execute", headers=auth,
                             json={"contract_version": "v1", "request_id": "pre-slow"}).json()
    assert _time.monotonic() - started < 3.0  # the request did not wait for the slow call
    assert result["evidence"][0]["classification"] == {"status": "UNCLASSIFIED", "reason": "DEADLINE"}
    assert seen and set(seen) == {2000}


def test_a_stale_running_need_can_run_again(tmp_path):
    store = SqliteStore(str(tmp_path / "s.sqlite3"), stale_running_seconds=60)
    row = {"web_need_id": "wn_1", "request_id": "r1", "request_fingerprint": "f", "conversation_id": None,
           "status": "APPROVED", "spec": {}, "plan": {}, "created_at": "2026-09-28T00:00:00+00:00",
           "updated_at": "2026-09-28T00:00:00+00:00"}
    store.create_need(row)
    assert store.begin_execution("wn_1")["status"] == "RUNNING"
    with pytest.raises(RuntimeError):
        store.begin_execution("wn_1")  # fresh RUNNING stays locked
    with store._connect() as connection:
        connection.execute("UPDATE web_need SET updated_at = '2026-09-28 00:00:00' WHERE web_need_id = 'wn_1'")
    assert store.begin_execution("wn_1")["status"] == "RUNNING"  # stale RUNNING may run again


def test_undated_sources_get_their_date_from_the_page_itself(tmp_path, auth):
    settings = settings_for(tmp_path, WEB_CLASSIFIER_CHECK_SLOT="0")
    page = (b'<html><head><meta property="article:published_time" content="2026-06-15T08:00:00+07:00">'
            b"</head><body><p>" + b"Perusahaan P dikabarkan menjajaki pembelian unit susu. " * 10 + b"</p></body></html>")
    undated_url = "https://katadata.example.id/berita/p-dikabarkan-gandeng-q"

    def handler(request):
        payload = json.loads(request.content)
        if "text" in payload:
            items = json.loads(payload["input"])["items"]
            return httpx.Response(200, request=request, json={"id": "c", "status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"items": [
                    {"item_index": item["item_index"], **classification_for(PRE_RUMOUR)} for item in items]})}]}]})
        return httpx.Response(200, request=request, json=search_reply([citation(undated_url, PRE_RUMOUR)]))

    provider = OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    fetcher = fake_fetcher(settings, {undated_url: (200, {"content-type": "text/html"}, page)})
    app = create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider, fetcher=fetcher,
                     event_store=FakeEventStore())
    with TestClient(app) as client:
        planned = client.post("/v1/web-needs", headers=auth, json=precursor_request("pre-date")).json()
        result = client.post(f"/v1/web-needs/{planned['web_need_id']}/execute", headers=auth,
                             json={"contract_version": "v1", "request_id": "pre-date"}).json()
    entry = result["timeline"]["pre_event"][0]
    assert (entry["published_at"], entry["published_at_source"], entry["lead_time_days"]) == (
        "2026-06-15", "HTML_META", 95)
    assert "DATES_READ_FROM_PAGES" in {warning["code"] for warning in result["warnings"]}
