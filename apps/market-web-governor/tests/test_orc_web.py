"""POST /v1/orc/web (PLAN_2026-10-05.md item 12): five shapes, a verbatim quote check in code, false and real
conflicts named by the model, escalation from quick to research, subjects in parallel, a budget per run, a deadline,
a cache, and a store that may be missing."""
from __future__ import annotations

import dataclasses
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.main import create_app
from app.orc_web import (MemoryOrcStore, OrcWebRequest, OrcWebService, OrcWebStoreError, PostgresOrcStore, cache_key,
                         tier, uniform)
from conftest import API_KEY, make_settings

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

BPS = ("https://www.bps.go.id/ekspor", "Ekspor Indonesia",
       "Nilai ekspor Indonesia Januari-Desember 2024 mencapai US$264,70 miliar. Ekspor 2023 sebesar US$258,82 miliar. "
       "Ekspor 2019 sebesar US$167,53 miliar.")
REUTERS = ("https://www.reuters.com/a", "Exports", "Indonesia's exports rose 2.3% in 2024, data showed on Jan 15.")
KONTAN = ("https://kontan.co.id/b", "Bakrie", "Grup Bakrie mengendalikan Bank Pundi dan Bank Nusantara Parahyangan.")


def search_reply(results, cost=0.002):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "OK", "annotations": [
        {"type": "url_citation", "url": url, "title": title, "content": text} for url, title, text in results]}]}],
        "usage": {"cost": cost}}


def reading_reply(reading, cost=0.0005):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(reading),
                                                        "annotations": []}]}], "usage": {"cost": cost}}


def item(shape, source, quote, subject="Indonesia", statement="s", number=None, event=None, members=None,
         text_value=None, series_name=None, confidence="HIGH"):
    return {"shape": shape, "subject": subject, "statement": statement, "series_name": series_name,
            "text_value": text_value, "members": members, "number": number, "event": event, "source": source,
            "quote": quote, "confidence": confidence}


def number(value, written, scale="miliar", start=None, end=None, basis="ANNUAL", kind="LEVEL"):
    return {"value": value, "value_as_written": written, "unit": "USD", "currency": "USD", "scale": scale,
            "kind": kind, "compared_with": None, "period_start": start, "period_end": end, "period_basis": basis,
            "frequency": "annual", "release_date": None, "revision": "UNKNOWN", "coverage": None}


def reading(items, conflicts=(), needs_research=False):
    return {"items": list(items), "conflicts": list(conflicts), "needs_research": needs_research, "note": ""}


class Provider:
    """Scripted Responses API. `searches(query, domains)` gives the results of one search; `readings` are returned
    in order (the last one repeats), or `reading_for(input)` picks one by the reading's input."""

    def __init__(self, searches=None, readings=(), reading_for=None, delay=0.0, delay_for=None):
        self.searches = searches or (lambda query, domains: [BPS] if domains else [REUTERS])
        self.readings = list(readings)
        self.reading_for = reading_for
        self.delay = delay
        self.delay_for = delay_for or (lambda payload: 0.0)
        self.payloads = []
        self.lock = threading.Lock()

    def respond(self, payload, attempts=None):
        with self.lock:
            self.payloads.append(payload)
        time.sleep(self.delay + self.delay_for(payload))
        if "tools" in payload:
            parameters = payload["tools"][0]["parameters"]
            return search_reply(self.searches(payload["input"], parameters.get("allowed_domains")))
        if self.reading_for:
            return reading_reply(self.reading_for(payload["input"]))
        with self.lock:
            chosen = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        return reading_reply(chosen)

    def close(self):
        pass

    def search_payloads(self):
        return [p for p in self.payloads if "tools" in p]

    def reading_payloads(self):
        return [p for p in self.payloads if "tools" not in p]


def settings_with(tmp_path, **env):
    base = {"WEB_GOVERNOR_API_KEY": API_KEY, "WEB_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test-key",
            "WEB_GOVERNOR_STORE_PATH": str(tmp_path / "s.db"), "WEB_OPENROUTER_MODEL": "test/model"}
    return Settings.from_env({**base, **env})


def request(need="nilai ekspor Indonesia per tahun", **kw):
    return OrcWebRequest(request_id=kw.pop("request_id", "r1"), budget_key=kw.pop("budget_key", "turn-1"), need=need,
                         purpose=kw.pop("purpose", "CONTEXT"), **kw)


def series_3(source=2):
    """Three years of exports quoted from the BPS page (source 2 in a quick reading: open first, then trusted)."""
    return reading([
        item("SERIES", source, "Januari-Desember 2024 mencapai US$264,70 miliar", series_name="ekspor",
             number=number(264.70, "US$264,70 miliar", start="2024-01-01", end="2024-12-31")),
        item("SERIES", source, "Ekspor 2023 sebesar US$258,82 miliar", series_name="ekspor",
             number=number(258.82, "US$258,82 miliar", start="2023-01-01", end="2023-12-31")),
        item("SERIES", source, "Ekspor 2019 sebesar US$167,53 miliar", series_name="ekspor",
             number=number(167.53, "US$167,53 miliar", start="2019-01-01", end="2019-12-31"))],
        conflicts=[{"about": "nilai ekspor", "kind": "DIFFERENT_PERIOD", "items": [1, 2, 3], "chosen": None,
                    "reason": "three different years"}])


SERIES_3 = series_3()


# ------------------------------------------------------------------------------------------------- pure helpers

def test_uniform_applies_the_written_scale() -> None:
    assert uniform(number(167.03, "US$167,03 miliar")) == pytest.approx(167.03e9)
    assert uniform(number(5.2, "5.2 bn", scale="bn")) == pytest.approx(5.2e9)
    assert uniform(number(12.5, "12,5%", scale=None)) == 12.5
    assert uniform(number(None, "n/a")) is None and uniform(None) is None


def test_tiers_come_from_the_route_lists_not_the_model(tmp_path) -> None:
    settings = settings_with(tmp_path)
    assert tier("bps.go.id", settings) == "OFFICIAL" and tier("satudata.kemendag.go.id", settings) == "OFFICIAL"
    assert tier("census.gov", settings) == "OFFICIAL" and tier("idx.co.id", settings) == "OFFICIAL"
    assert tier("imf.org", settings) == "INTERNATIONAL" and tier("data.worldbank.org", settings) == "INTERNATIONAL"
    assert tier("reuters.com", settings) == "MEDIA" and tier("example.com", settings) == "OTHER"


def test_the_cache_key_ignores_case_punctuation_and_subject_order() -> None:
    one = request("Nilai ekspor, Indonesia?", subjects=["BBRI", "BMRI"])
    two = request("nilai  ekspor indonesia", subjects=["bmri", "bbri"])
    assert cache_key(one) == cache_key(two)
    assert cache_key(one) != cache_key(request("nilai ekspor indonesia", purpose="CITE", subjects=["BBRI", "BMRI"]))


def test_settings_have_defaults_and_are_validated(tmp_path) -> None:
    settings = settings_with(tmp_path)
    assert (settings.orc_web_quick_seconds, settings.orc_web_research_seconds, settings.orc_web_workers) == (30, 120, 6)
    assert settings.orc_web_max_calls_per_run == 12 and settings.orc_web_max_usd_per_run == 0.25
    assert "kemendag.go.id" in settings.orc_web_official_domains and "imf.org" in settings.orc_web_international_domains
    custom = settings_with(tmp_path, WEB_ORC_MEDIA_DOMAINS="Reuters.com | kontan.co.id")
    assert custom.orc_web_media_domains == ("reuters.com", "kontan.co.id")
    with pytest.raises(ConfigError):
        settings_with(tmp_path, WEB_ORC_OFFICIAL_DOMAINS="not a domain")
    with pytest.raises(ConfigError):
        settings_with(tmp_path, WEB_ORC_QUICK_SECONDS="60", WEB_ORC_RESEARCH_SECONDS="60")
    with pytest.raises(ConfigError):
        settings_with(tmp_path, WEB_ORC_SLOT="3")


# ------------------------------------------------------------------------------------------------- shapes

def test_a_quick_need_returns_citable_items_in_every_shape(tmp_path) -> None:
    provider = Provider(readings=[reading([
        item("NUMBER", 2, "Januari-Desember 2024 mencapai US$264,70 miliar",
             number=number(264.70, "US$264,70 miliar", start="2024-01-01", end="2024-12-31")),
        item("FACT", 1, "exports rose 2.3% in 2024", text_value="exports rose 2.3% in 2024"),
        item("EVENT", 1, "data showed on Jan 15", event={"announced": "2025-01-15", "effective": None, "ended": None,
                                                         "status": "COMPLETED", "stages": []}),
        item("LIST", 2, "Ekspor 2023 sebesar US$258,82 miliar", members=["2023", "2024"])])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert result["status"] == "OK" and result["depth"] == "QUICK" and not result["escalated"]
    shapes = {entry["shape"]: entry for entry in result["citable"]}
    assert set(shapes) == {"NUMBER", "FACT", "EVENT", "LIST"}
    exports = shapes["NUMBER"]
    assert exports["value"] == pytest.approx(264.70e9) and exports["value_as_written"] == "US$264,70 miliar"
    assert exports["period"] == {"start": "2024-01-01", "end": "2024-12-31", "basis": "ANNUAL"}
    assert exports["label"] == "WEB_FACT" and exports["source"]["domain"] == "bps.go.id"
    assert exports["source"]["official"] and exports["source"]["tier"] == "OFFICIAL"
    assert exports["id"] == f"{result['result_id']}_1"
    assert shapes["FACT"]["value"] == "exports rose 2.3% in 2024" and shapes["FACT"]["source"]["tier"] == "MEDIA"
    assert shapes["EVENT"]["event"]["announced"] == "2025-01-15"
    assert shapes["LIST"]["members"] == ["2023", "2024"] and shapes["LIST"]["value"] == "2023, 2024"
    # quick: two searches (open; official and international domains), then one strict reading without reasoning
    searches = provider.search_payloads()
    assert len(searches) == 2
    allowed = [p["tools"][0]["parameters"].get("allowed_domains") for p in searches]
    assert None in allowed and any(a and "bps.go.id" in a and "imf.org" in a for a in allowed)
    readings = provider.reading_payloads()
    assert len(readings) == 1 and readings[0]["reasoning"] == {"enabled": False}
    assert readings[0]["text"]["format"]["strict"] is True
    assert result["budget"]["calls_used"] == 1 and result["cost_usd"] == pytest.approx(0.0045)


def test_a_quote_not_in_its_source_is_dropped(tmp_path) -> None:
    provider = Provider(readings=[reading([
        item("NUMBER", 2, "ekspor Indonesia 2024 naik ke rekor", number=number(300, "US$300 miliar")),
        item("FACT", 1, "exports rose 2.3% in 2024", text_value="naik 2,3%")])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert [entry["shape"] for entry in result["citable"]] == ["FACT"]
    assert any(w["code"] == "QUOTE_NOT_VERBATIM" for w in result["warnings"])


def test_a_quote_naming_a_source_that_does_not_exist_is_dropped(tmp_path) -> None:
    provider = Provider(readings=[reading([item("FACT", 9, "exports rose 2.3% in 2024", text_value="x")])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert result["status"] == "NOT_FOUND" and result["citable"] == []


# ------------------------------------------------------------------------------------------------- conflicts

def test_different_periods_are_a_series_not_a_conflict(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(expected_shape="SERIES"))
    assert result["status"] == "OK" and len(result["citable"]) == 3
    assert {entry["conflict"] for entry in result["citable"]} == {"DIFFERENT_PERIOD"}
    assert all(entry["chosen_by_ai"] is None for entry in result["citable"])
    assert result["conflicts"][0]["items"] == [0, 1, 2]


def test_a_real_conflict_keeps_every_version_and_marks_the_choice(tmp_path) -> None:
    provider = Provider(readings=[reading([
        item("NUMBER", 2, "Januari-Desember 2024 mencapai US$264,70 miliar", number=number(264.70, "US$264,70 miliar")),
        item("NUMBER", 1, "exports rose 2.3% in 2024", number=number(266.0, "US$266 billion", scale="billion"))],
        conflicts=[{"about": "ekspor 2024", "kind": "REAL", "items": [1, 2], "chosen": 1,
                    "reason": "official statistics first"}])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    first, second = result["citable"]
    assert (first["conflict"], first["chosen_by_ai"]) == ("REAL", True)
    assert (second["conflict"], second["chosen_by_ai"]) == ("REAL", False)
    assert result["conflicts"][0]["reason"] == "official statistics first"


def test_a_real_conflict_without_a_choice_is_conflicting(tmp_path) -> None:
    provider = Provider(readings=[reading([
        item("NUMBER", 2, "Januari-Desember 2024 mencapai US$264,70 miliar", number=number(264.70, "x")),
        item("NUMBER", 1, "exports rose 2.3% in 2024", number=number(266.0, "y"))],
        conflicts=[{"about": "ekspor 2024", "kind": "REAL", "items": [1, 2], "chosen": None, "reason": "equal"}])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert {(e["conflict"], e["chosen_by_ai"]) for e in result["citable"]} == {("CONFLICTING", None)}


def test_a_conflict_with_a_dropped_item_is_not_a_conflict(tmp_path) -> None:
    provider = Provider(readings=[reading([
        item("NUMBER", 2, "Januari-Desember 2024 mencapai US$264,70 miliar", number=number(264.70, "x")),
        item("NUMBER", 1, "not in the source at all", number=number(266.0, "y"))],
        conflicts=[{"about": "ekspor 2024", "kind": "REAL", "items": [1, 2], "chosen": 2, "reason": "r"}])])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert result["conflicts"] == [] and result["citable"][0]["conflict"] is None


# ------------------------------------------------------------------------------------------------- depth

def test_a_short_quick_reading_escalates_to_research(tmp_path) -> None:
    def searches(query, domains):
        if domains is None:
            return [REUTERS]
        if "imf.org" in domains and "bps.go.id" in domains:
            return [BPS]
        if "imf.org" in domains:
            return [("https://www.imf.org/x", "IMF", "Indonesia exports grew in 2022 by 26%.")]
        if "bps.go.id" in domains:
            return [BPS, ("https://satudata.kemendag.go.id/y", "Kemendag", "Ekspor 2022 sebesar US$291,98 miliar.")]
        return [KONTAN]

    provider = Provider(searches=searches, readings=[
        reading([item("FACT", 1, "exports rose 2.3% in 2024", text_value="x")], needs_research=True), series_3(1)])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(expected_shape="SERIES"))
    assert result["depth"] == "RESEARCH" and result["escalated"] and result["status"] == "OK"
    # quick: open + trusted; research: official, international and media searches; two readings
    assert len(provider.search_payloads()) == 5 and len(provider.reading_payloads()) == 2
    # the research reading sees official sources first, renumbered from 1
    assert [s["domain"] for s in result["sources"]] == ["bps.go.id", "satudata.kemendag.go.id", "imf.org",
                                                        "reuters.com", "kontan.co.id"]
    assert [s["n"] for s in result["sources"]] == [1, 2, 3, 4, 5]
    assert {e["source"]["domain"] for e in result["citable"]} == {"bps.go.id"} and len(result["citable"]) == 3


def test_research_reading_uses_the_ranked_numbering(tmp_path) -> None:
    def searches(query, domains):
        if domains is None:
            return [REUTERS]
        if "imf.org" in domains and "bps.go.id" in domains:
            return []
        if "bps.go.id" in domains:
            return [BPS]
        return []

    research = reading([item("SERIES", 1, "Januari-Desember 2024 mencapai US$264,70 miliar", series_name="ekspor",
                             number=number(264.7, "x", start="2024-01-01", end="2024-12-31"))])
    provider = Provider(searches=searches, readings=[reading([], needs_research=True), research])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert result["depth"] == "RESEARCH"
    assert [s["domain"] for s in result["sources"]] == ["bps.go.id", "reuters.com"]
    assert result["citable"][0]["source"]["domain"] == "bps.go.id" and result["escalation"] == "NOTHING_FOUND"
    assert result["status"] == "PARTIAL"  # a series of one period is still short after research


def test_a_found_number_is_not_researched_on_the_model_word_alone(tmp_path) -> None:
    """Smoke run orcweb-smoke-20261005a: the latest BI-Rate, found in the quick reading, escalated to 24 items of
    history in 104 s because the model asked for more."""
    found = reading([item("NUMBER", 2, "Januari-Desember 2024 mencapai US$264,70 miliar",
                          number=number(264.70, "US$264,70 miliar"))], needs_research=True)
    provider = Provider(readings=[found])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(expected_shape="NUMBER"))
    assert result["depth"] == "QUICK" and result["escalation"] is None and result["status"] == "OK"
    assert len(provider.search_payloads()) == 2 and len(provider.reading_payloads()) == 1
    # where coverage is the point (a series, a list, an unknown shape) the model's word still widens the search
    provider = Provider(readings=[{**SERIES_3, "needs_research": True}])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request("ekspor", expected_shape="SERIES"))
    assert result["escalation"] == "MODEL_ASKED" and len(provider.search_payloads()) > 2


def test_a_good_quick_reading_does_not_escalate(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(expected_shape="SERIES"))
    assert result["depth"] == "QUICK" and len(provider.search_payloads()) == 2


def test_research_without_new_sources_keeps_the_quick_reading(tmp_path) -> None:
    provider = Provider(readings=[reading([item("FACT", 1, "exports rose 2.3% in 2024", text_value="x")],
                                          needs_research=True)])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request())
    assert result["depth"] == "QUICK" and len(result["citable"]) == 1
    assert result["status"] == "PARTIAL" and len(provider.reading_payloads()) == 1


# ------------------------------------------------------------------------------------------------- subjects

def test_subjects_run_in_parallel_in_one_call(tmp_path) -> None:
    pages = {name: (f"https://www.idx.co.id/{name}", name, f"{name} adalah bank swasta nasional.")
             for name in ("BBCA", "BNGA", "BDMN")}

    def reading_for(text):
        name = next(n for n in pages if f"Subject: {n}" in text)
        return reading([item("FACT", 1, f"{name} adalah bank swasta", subject="", text_value="swasta")])

    provider = Provider(searches=lambda query, domains: [pages[query.split()[0]]], reading_for=reading_for,
                        delay=0.4)
    started = time.monotonic()
    result = OrcWebService(settings_with(tmp_path), provider).answer(
        request("status BUMN atau swasta", purpose="CITE", subjects=list(pages), expected_shape="FACT"))
    elapsed = time.monotonic() - started
    assert elapsed < 2.0  # three subjects of two 0.4 s calls each, sequentially 2.4 s
    assert result["status"] == "OK" and len(result["citable"]) == 3
    by_subject = {entry["subject"]: entry for entry in result["citable"]}
    assert set(by_subject) == set(pages)
    for name, entry in by_subject.items():
        assert entry["source"]["url"] == pages[name][0] and entry["quote"].startswith(name)
    assert result["budget"]["calls_used"] == 3 and len(provider.search_payloads()) == 3


def test_subject_conflicts_are_renumbered(tmp_path) -> None:
    def reading_for(text):
        if "Subject: A" in text:
            return reading([item("FACT", 1, "exports rose 2.3% in 2024", text_value="x")])
        return reading([item("NUMBER", 1, "exports rose 2.3% in 2024", number=number(2.3, "2.3%", scale=None)),
                        item("NUMBER", 1, "data showed on Jan 15", number=number(2.4, "2.4%", scale=None))],
                       conflicts=[{"about": "growth", "kind": "REAL", "items": [1, 2], "chosen": 2, "reason": "r"}])

    provider = Provider(reading_for=reading_for)
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(subjects=["A", "B"]))
    assert result["conflicts"][0]["items"] == [1, 2] and result["conflicts"][0]["chosen"] == 2
    assert [e["chosen_by_ai"] for e in result["citable"]] == [None, False, True]


# ------------------------------------------------------------------------------------------------- budget, deadline

def test_the_run_budget_counts_calls_across_requests(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    service = OrcWebService(settings_with(tmp_path, WEB_ORC_MAX_CALLS_PER_RUN="2"), provider)
    assert service.answer(request("need one"))["budget"]["calls_left"] == 1
    assert service.answer(request("need two"))["budget"]["calls_left"] == 0
    calls = len(provider.payloads)
    spent = service.answer(request("need three"))
    assert spent["status"] == "BUDGET_EXHAUSTED" and spent["citable"] == []
    assert any(w["code"] == "ORC_WEB_BUDGET_EXHAUSTED" for w in spent["warnings"])
    assert len(provider.payloads) == calls
    # another run has its own budget
    assert service.answer(request("need three", budget_key="turn-2"))["status"] == "OK"


def test_subjects_beyond_the_budget_are_cut(tmp_path) -> None:
    provider = Provider(reading_for=lambda text: reading([item("FACT", 1, "exports rose 2.3% in 2024",
                                                               text_value="x")]))
    service = OrcWebService(settings_with(tmp_path, WEB_ORC_MAX_CALLS_PER_RUN="2"), provider)
    result = service.answer(request(subjects=["A", "B", "C", "A"]))
    assert result["status"] == "PARTIAL" and len(result["citable"]) == 2
    assert any(w["code"] == "ORC_WEB_SUBJECTS_CUT" and w["message"].startswith("1 ") for w in result["warnings"])


def test_the_usd_budget_stops_the_run(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    service = OrcWebService(settings_with(tmp_path, WEB_ORC_MAX_USD_PER_RUN="0.01"), provider)
    statuses = [service.answer(request(f"need {n}"))["status"] for n in range(4)]
    assert statuses[:2] == ["OK", "OK"] and statuses[-1] == "BUDGET_EXHAUSTED"


def test_the_deadline_returns_the_subjects_that_finished(tmp_path) -> None:
    settings = dataclasses.replace(settings_with(tmp_path), orc_web_quick_seconds=1, orc_web_research_seconds=2)
    provider = Provider(reading_for=lambda text: reading([item("FACT", 1, "exports rose 2.3% in 2024",
                                                               text_value="x")]),
                        delay_for=lambda payload: 3.0 if "SLOW" in payload["input"] else 0.0)
    started = time.monotonic()
    result = OrcWebService(settings, provider).answer(request(subjects=["FAST", "SLOW"]))
    assert time.monotonic() - started < 3.5
    assert result["status"] == "PARTIAL" and [e["subject"] for e in result["citable"]] == ["FAST"]
    assert any(w["code"] == "ORC_WEB_DEADLINE" for w in result["warnings"])


# ------------------------------------------------------------------------------------------------- cache and store

def test_a_complete_result_is_cached_and_refresh_reads_again(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    service = OrcWebService(settings_with(tmp_path), provider)
    first = service.answer(request(expected_shape="SERIES"))
    calls = len(provider.payloads)
    second = service.answer(request(expected_shape="SERIES", budget_key="turn-2"))
    assert second["cached"] and second["result_id"] == first["result_id"] and second["cost_usd"] == 0.0
    assert second["citable"] == first["citable"] and len(provider.payloads) == calls
    assert second["budget"]["calls_used"] == 0
    third = service.answer(request(expected_shape="SERIES", refresh=True))
    assert not third["cached"] and len(provider.payloads) > calls


def test_a_partial_result_is_not_cached(tmp_path) -> None:
    provider = Provider(reading_for=lambda text: reading([item("FACT", 1, "exports rose 2.3% in 2024",
                                                               text_value="x")]))
    service = OrcWebService(settings_with(tmp_path, WEB_ORC_MAX_CALLS_PER_RUN="1"), provider)
    service.answer(request(subjects=["A", "B"]))
    assert service.memory.results == {}


class BrokenStore:
    def __getattr__(self, name):
        def fail(*args):
            raise OrcWebStoreError(f"orc web store {name} failed: OperationalError")
        return fail


def test_a_missing_store_falls_back_to_memory_with_a_warning(tmp_path) -> None:
    provider = Provider(readings=[SERIES_3])
    service = OrcWebService(settings_with(tmp_path), provider, BrokenStore())
    result = service.answer(request(expected_shape="SERIES"))
    assert result["status"] == "OK"
    assert [w["code"] for w in result["warnings"]].count("ORC_WEB_STORE_UNAVAILABLE") == 1
    assert service.memory.budget["turn-1"][0] == 1 and len(service.memory.results) == 1


def test_the_postgres_store_reports_an_unreachable_database_as_a_store_error() -> None:
    store = PostgresOrcStore("postgresql://nobody@127.0.0.1:1/none")
    with pytest.raises(OrcWebStoreError):
        store.spent("turn-1")


def test_the_memory_store_expires_results() -> None:
    store = MemoryOrcStore()
    store.put_result("k", "need", "CITE", {"status": "OK"}, "m", 0.0, 0)
    assert store.get_result("k") is None


# ------------------------------------------------------------------------------------------------- endpoint

def test_the_endpoint(tmp_path) -> None:
    settings = make_settings(str(tmp_path / "s.db"))
    provider = Provider(readings=[SERIES_3])
    app = create_app(settings, orc_web_service=OrcWebService(settings, provider))
    body = {"request_id": "r1", "budget_key": "turn-1", "need": "nilai ekspor Indonesia per tahun",
            "purpose": "CONTEXT", "expected_shape": "SERIES"}
    with TestClient(app) as client:
        answered = client.post("/v1/orc/web", json=body, headers=HEADERS)
        assert answered.status_code == 200 and answered.json()["status"] == "OK"
        assert len(answered.json()["citable"]) == 3
        assert client.post("/v1/orc/web", json=body).status_code == 401
        assert client.post("/v1/orc/web", json={**body, "purpose": "OTHER"}, headers=HEADERS).status_code == 422
        assert client.post("/v1/orc/web", json={**body, "subjects": ["x"] * 51}, headers=HEADERS).status_code == 422


def test_the_benchmark_cases_are_valid_requests() -> None:
    from pathlib import Path

    cases = json.loads((Path(__file__).parent / "fixtures" / "orc_web_cases.json").read_text())["cases"]
    assert len(cases) >= 20 and len({case["id"] for case in cases}) == len(cases)
    known = {"depth", "shapes", "min_items", "min_periods", "conflicts", "official", "subjects_answered"}
    for case in cases:
        OrcWebRequest(request_id="r", budget_key="b", need=case["need"], purpose=case["purpose"],
                      expected_shape=case.get("expected_shape"), subjects=case.get("subjects") or [])
        assert set(case["labels"]) <= known and case["labels"]["depth"] in ("QUICK", "RESEARCH", "ANY")
        assert case["expected"]


def test_a_real_conflict_between_dated_periods_is_a_series(tmp_path) -> None:
    """Benchmark orcweb-bench-20261006a (q7 repeat): six yearly export values were called one REAL conflict."""
    conflicting = {**SERIES_3, "conflicts": [{"about": "ekspor", "kind": "REAL", "items": [1, 2, 3], "chosen": None,
                                              "reason": "sources differ"}]}
    result = OrcWebService(settings_with(tmp_path), Provider(readings=[conflicting])).answer(
        request(expected_shape="SERIES"))
    assert result["conflicts"][0]["kind"] == "DIFFERENT_PERIOD" and result["conflicts"][0]["chosen"] is None
    assert {e["conflict"] for e in result["citable"]} == {"DIFFERENT_PERIOD"} and result["status"] == "OK"


def test_undated_series_items_are_counted_by_their_text(tmp_path) -> None:
    """Benchmark orcweb-bench-20261006a (inflation): twelve months without period dates counted as one period."""
    months = reading([item("SERIES", 2, quote, series_name="ekspor", number=number(value, written, start=None,
                                                                                   end=None))
                      for quote, value, written in (("Januari-Desember 2024 mencapai US$264,70 miliar", 264.7, "a"),
                                                    ("Ekspor 2023 sebesar US$258,82 miliar", 258.82, "b"),
                                                    ("Ekspor 2019 sebesar US$167,53 miliar", 167.53, "c"))])
    provider = Provider(readings=[months])
    result = OrcWebService(settings_with(tmp_path), provider).answer(request(expected_shape="SERIES"))
    assert result["depth"] == "QUICK" and result["escalation"] is None and len(provider.reading_payloads()) == 1


def test_the_written_figure_decides_its_value_when_unambiguous() -> None:
    from app.orc_web import written_number

    assert written_number("282,9") == 282.9 and written_number("US$258.774,4 juta") == 258774.4
    assert written_number("291,979,090,608") == 291979090608 and written_number("2.92%") == 2.92
    assert written_number("−1,5 persen") == -1.5 and written_number("12") == 12
    assert written_number("264.700") is None and written_number("Januari 2025 0,76 persen") is None
    assert written_number("") is None and written_number(None) is None


def test_a_misread_decimal_comma_is_corrected(tmp_path) -> None:
    """Benchmark orcweb-bench-20261006b (q7): "282,9" miliar read as 282900, a thousand times too large."""
    misread = reading([item("NUMBER", 2, "Ekspor 2023 sebesar US$258,82 miliar",
                            number=number(258820, "US$258,82 miliar", start="2023-01-01", end="2023-12-31"))])
    result = OrcWebService(settings_with(tmp_path), Provider(readings=[misread])).answer(request())
    assert result["citable"][0]["value"] == pytest.approx(258.82e9)
    assert any(w["code"] == "VALUE_FROM_WRITTEN" for w in result["warnings"])


def test_only_a_misreading_overrides_the_reading() -> None:
    from app.orc_web import _misread

    assert _misread({"value": 282900, "value_as_written": "282,9", "scale": "miliar"})  # decimal comma misread
    assert _misread({"value": 282.9e9, "value_as_written": "282,9", "scale": "miliar"})  # scale applied twice
    assert _misread({"value": None, "value_as_written": "282,9", "scale": "miliar"})
    assert not _misread({"value": 282.9, "value_as_written": "282,9", "scale": "miliar"})
    # a written figure in full with a scale given by the reading: a different difference, left to the reading
    assert not _misread({"value": 264.7, "value_as_written": "264,700,000,000", "scale": "miliar"})
