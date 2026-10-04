"""POST /v1/fact (S4b, PLAN_FINAL_2026-10-04.md Fase 4): two searches without a planner, one extraction call, status
decided by code from verbatim quotes, a 30-second deadline, and a cache of settled facts."""
from __future__ import annotations

import json
import threading
import time

from fastapi.testclient import TestClient

from app.fact import FactRequest, FactService, decide, fact_key, verified
from app.main import create_app
from conftest import API_KEY, make_settings

HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def search_reply(results):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK", "annotations": [
        {"type": "url_citation", "url": url, "title": title, "content": text} for url, title, text in results]}]}],
        "usage": {"cost": 0.002}}


def extract_reply(values):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"values": values}),
                                                        "annotations": []}]}], "usage": {"cost": 0.0005}}


OPEN = [("https://www.bisnis.com/a", "BBCA", "Bank Central Asia adalah bank swasta milik Grup Djarum."),
        ("https://kontan.co.id/b", "BCA", "BCA merupakan bank swasta nasional terbesar.")]
OFFICIAL = [("https://www.idx.co.id/c", "Profil", "PT Bank Central Asia Tbk, pemegang saham pengendali PT Dwimuria.")]


class Provider:
    """Scripted Responses API: searches by their allowed domains, then the extraction call."""

    def __init__(self, open_results=OPEN, official=OFFICIAL, values=None, delay=0.0):
        self.open_results, self.official, self.values, self.delay = open_results, official, values, delay
        self.payloads = []
        self.lock = threading.Lock()

    def respond(self, payload, attempts=None):
        with self.lock:
            self.payloads.append(payload)
        time.sleep(self.delay)
        if "tools" in payload:
            domains = payload["tools"][0]["parameters"].get("allowed_domains")
            return search_reply(self.official if domains else self.open_results)
        return extract_reply(self.values or [])

    def close(self):
        pass


class Store:
    def __init__(self):
        self.rows = {}

    def get(self, key):
        return self.rows.get(key)

    def write(self, row):
        self.rows[row["fact_key"]] = dict(row)


def service(tmp_path, provider, store=None, deadline=30.0):
    return FactService(make_settings(str(tmp_path / "s.db")), provider, store, deadline_seconds=deadline)


def ask(svc, refresh=False):
    return svc.fact(FactRequest(request_id="r1", subject="BBCA", attribute="status BUMN atau swasta",
                                refresh=refresh))


def test_two_independent_domains_confirm(tmp_path) -> None:
    provider = Provider(values=[{"source": 1, "value": "swasta", "quote": "adalah bank swasta milik Grup Djarum"},
                                {"source": 2, "value": "swasta", "quote": "merupakan bank swasta nasional"}])
    result = ask(service(tmp_path, provider))
    assert result["status"] == "CONFIRMED" and result["value"] == "swasta"
    assert sorted(result["versions"][0]["domains"]) == ["bisnis.com", "kontan.co.id"]
    # two searches without a planner (one open, one official), then one extraction call without reasoning
    searches = [p for p in provider.payloads if "tools" in p]
    assert len(searches) == 2 and sum(1 for p in searches if p["tools"][0]["parameters"].get("allowed_domains")) == 1
    extraction = [p for p in provider.payloads if "tools" not in p]
    assert len(extraction) == 1 and extraction[0]["reasoning"] == {"enabled": False}


def test_one_official_source_confirms(tmp_path) -> None:
    provider = Provider(values=[{"source": 3, "value": "PT Dwimuria",
                                 "quote": "pemegang saham pengendali PT Dwimuria"}])
    result = ask(service(tmp_path, provider))
    assert result["status"] == "CONFIRMED" and result["versions"][0]["official"]


def test_one_secondary_source_is_partial(tmp_path) -> None:
    provider = Provider(values=[{"source": 1, "value": "swasta", "quote": "adalah bank swasta milik Grup Djarum"}])
    assert ask(service(tmp_path, provider))["status"] == "PARTIAL"


def test_different_values_are_conflicting_with_every_version(tmp_path) -> None:
    provider = Provider(values=[{"source": 1, "value": "swasta", "quote": "adalah bank swasta milik Grup Djarum"},
                                {"source": 2, "value": "BUMN", "quote": "merupakan bank swasta nasional"}])
    result = ask(service(tmp_path, provider))
    assert result["status"] == "CONFLICTING" and result["value"] is None
    assert {v["value"] for v in result["versions"]} == {"swasta", "BUMN"}


def test_a_quote_not_in_the_source_is_dropped(tmp_path) -> None:
    provider = Provider(values=[{"source": 1, "value": "BUMN", "quote": "BBCA adalah bank milik negara"}])
    result = ask(service(tmp_path, provider))
    assert result["status"] == "NOT_FOUND"
    assert any(w["code"] == "QUOTE_NOT_VERBATIM" for w in result["warnings"])


def test_nothing_found(tmp_path) -> None:
    result = ask(service(tmp_path, Provider(open_results=[], official=[])))
    assert result["status"] == "NOT_FOUND" and result["sources"] == []


def test_the_deadline_returns_what_there_is(tmp_path) -> None:
    started = time.monotonic()
    result = ask(service(tmp_path, Provider(delay=3.0), deadline=4.0))
    assert time.monotonic() - started < 6.0
    assert result["status"] in ("PARTIAL", "NOT_FOUND")
    assert any(w["code"] == "FACT_DEADLINE" for w in result["warnings"]) or result["sources"] == []


def test_a_settled_fact_is_cached_and_refresh_reads_again(tmp_path) -> None:
    store = Store()
    values = [{"source": 1, "value": "swasta", "quote": "adalah bank swasta milik Grup Djarum"},
              {"source": 2, "value": "swasta", "quote": "merupakan bank swasta nasional"}]
    provider = Provider(values=values)
    svc = service(tmp_path, provider, store)
    first = ask(svc)
    calls = len(provider.payloads)
    second = ask(svc)
    assert second["cached"] and second["value"] == first["value"] and len(provider.payloads) == calls
    ask(svc, refresh=True)
    assert len(provider.payloads) > calls


def test_the_key_ignores_case_and_punctuation() -> None:
    assert fact_key("BBCA", "Status BUMN?") == fact_key(" bbca ", "status   bumn")
    assert verified("Bank  Swasta milik", "adalah bank swasta MILIK grup") and not verified("bank", "bank swasta")


def test_decide_counts_domains_not_sources() -> None:
    sources = [{"n": 1, "url": "https://a.com/1", "domain": "a.com", "source_tier": "SECONDARY"},
               {"n": 2, "url": "https://a.com/2", "domain": "a.com", "source_tier": "SECONDARY"}]
    status, _, _ = decide([{"source": 1, "value": "x", "quote": "q"}, {"source": 2, "value": "x", "quote": "q"}],
                          sources)
    assert status == "PARTIAL"


def test_the_endpoint(tmp_path) -> None:
    from conftest import FakeProvider  # noqa: F401 - the app's other services are not used here

    provider = Provider(values=[{"source": 3, "value": "PT Dwimuria",
                                 "quote": "pemegang saham pengendali PT Dwimuria"}])
    settings = make_settings(str(tmp_path / "s.db"))
    app = create_app(settings, fact_service=FactService(settings, provider, None))
    with TestClient(app) as client:
        body = client.post("/v1/fact", json={"request_id": "r1", "subject": "BBCA", "attribute": "pengendali"},
                           headers=HEADERS)
        assert body.status_code == 200 and body.json()["status"] == "CONFIRMED"
        assert client.post("/v1/fact", json={"request_id": "r1", "subject": "BBCA", "attribute": "x"}).status_code == 401


def _src(n, domain, tier="SECONDARY"):
    return {"n": n, "url": f"https://{domain}/{n}", "domain": domain, "source_tier": tier}


def test_the_same_answer_in_other_words_is_one_version() -> None:
    """fact-bench-20261004b: four false conflicts."""
    sources = [_src(1, "a.com"), _src(2, "b.com"), _src(3, "c.com")]
    e = lambda n, v: {"source": n, "value": v, "quote": "q"}  # noqa: E731
    # punctuation
    assert decide([e(1, "CIMB Group Sdn Bhd"), e(2, "CIMB Group Sdn. Bhd.")], sources)[0] == "CONFIRMED"
    # less detail
    status, value, _ = decide([e(1, "2003"), e(2, "10 November 2003")], sources)
    assert status == "CONFIRMED" and value == "10 November 2003"
    # a value that only repeats the question is no answer
    status, value, _ = decide([e(1, "Jardine Cycle & Carriage"), e(2, "Jardine Cycle & Carriage Limited"),
                               e(3, "Pemegang Saham Pengendali")], sources, "pemegang saham pengendali")
    assert status == "CONFIRMED" and value == "Jardine Cycle & Carriage Limited"


def test_different_answers_stay_a_conflict() -> None:
    """The case this change does not touch: two different entities (direct holder vs the family behind it)."""
    sources = [_src(1, "a.com"), _src(2, "b.com")]
    status, _, versions = decide([{"source": 1, "value": "PT Dwimuria Investama Andalan", "quote": "q"},
                                  {"source": 2, "value": "Robert Budi Hartono", "quote": "q"}], sources)
    assert status == "CONFLICTING" and len(versions) == 2
