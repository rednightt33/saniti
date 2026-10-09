"""research_web (PLAN_2026-10-05.md item 12): the tool exists only with its switch and never next to find_web_fact; it
sends one need with the user turn as the web budget key; every item of its citable envelope becomes a value reference
shown as a web fact with its domain; its numbers describe and are refused in code; the database is checked first; the
prompt sentences of the one-fact tool are replaced only when this tool is offered."""
from __future__ import annotations

import json
import time

import httpx
import pytest

from app import ai_choices as C
from app.config import ConfigError
from app.orchestrator import (OUTSIDE_DATA_RESEARCH_RULE, OUTSIDE_DATA_WEB_RULE, AgentOrchestrator, RunState,
                              build_system_prompt, data_sources_block)
from app.schemas import FinalResponse
from app.tools import ToolOutcome, build_default_registry
from app.tools.request_data import GovernorClient, current_request_id, current_run_deadline, current_turn_id
from app.tools.web_fact import WebFactClient
from app.tools.web_research import MAX_SECONDS, MIN_SECONDS, WebResearchClient, model_view, wait_seconds
from app.value_refs import render
from conftest import ScriptedClient, final_response, make_settings

ENTRY = {"id": "wab12cd34_1", "shape": "SERIES", "subject": "Indonesia", "statement": "Ekspor 2024",
         "series_name": "ekspor", "value": 264.7e9, "value_as_written": "US$264,70 miliar", "unit": "USD",
         "currency": "USD", "scale": "miliar", "kind": "LEVEL", "compared_with": None,
         "period": {"start": "2024-01-01", "end": "2024-12-31", "basis": "ANNUAL"}, "frequency": "annual",
         "release_date": None, "revision": "UNKNOWN", "coverage": None, "label": "WEB_FACT",
         "source": {"url": "https://www.bps.go.id/a", "domain": "bps.go.id", "title": "Ekspor", "date": None,
                    "tier": "OFFICIAL", "official": True},
         "quote": "Januari-Desember 2024 mencapai US$264,70 miliar", "confidence": "HIGH", "chosen_by_ai": None,
         "conflict": "DIFFERENT_PERIOD", "retrieved_at": "2026-10-05T10:00:00+00:00"}
SECOND = {**ENTRY, "id": "wab12cd34_2", "statement": "Ekspor 2023", "value": 258.82e9,
          "value_as_written": "US$258,82 miliar", "period": {"start": "2023-01-01", "end": "2023-12-31",
                                                             "basis": "ANNUAL"}}
FACT = {**ENTRY, "id": "wab12cd34_3", "shape": "FACT", "value": "exports rose 2.3% in 2024", "value_as_written": None,
        "conflict": None, "source": {**ENTRY["source"], "domain": "reuters.com", "tier": "MEDIA", "official": False}}
ANSWER = {"status": "OK", "result_id": "wab12cd34", "need": "nilai ekspor Indonesia", "purpose": "CONTEXT",
          "depth": "QUICK", "escalated": False, "cached": False, "items": [], "citable": [ENTRY, SECOND, FACT],
          "conflicts": [{"about": "ekspor", "kind": "DIFFERENT_PERIOD", "items": [0, 1], "chosen": None,
                         "reason": "two years"}],
          "sources": [{"n": 1, "url": "https://www.bps.go.id/a", "domain": "bps.go.id", "title": "Ekspor",
                       "date": None, "tier": "OFFICIAL", "text": "excerpt never shown"}],
          "budget": {"max_calls": 12, "calls_used": 1, "calls_left": 11, "usd_left": 0.24}, "warnings": [],
          "cost_usd": 0.02, "seconds": 9.1}


def client(handler) -> WebResearchClient:
    return WebResearchClient("http://web", "w" * 40, transport=httpx.MockTransport(handler))


def answering(seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((request.url.path, json.loads(request.content), request.headers["Authorization"]))
        return httpx.Response(200, json=ANSWER)
    return handler


def call(registry, need="nilai ekspor Indonesia per tahun", **extra):
    return registry.execute("c1", "research_web", json.dumps({"need": need, "purpose": "CONTEXT",
                                                              "expected_shape": "SERIES", "subjects": [], **extra}))


# ------------------------------------------------------------------------------------------------- tool and switch

def test_the_tool_exists_only_with_its_client_and_never_next_to_find_web_fact() -> None:
    assert "research_web" not in build_default_registry().names()
    registry = build_default_registry(web_research_client=client(answering()))
    assert registry.get("research_web").effect == "FETCHES_WEB"
    web_fact = WebFactClient("http://web", "w" * 40, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    both = build_default_registry(web_research_client=client(answering()), web_fact_client=web_fact)
    assert "research_web" in both.names() and "find_web_fact" not in both.names()  # the newer tool replaces it


def test_the_switches_are_exclusive() -> None:
    assert make_settings(AI_ENABLE_WEB_RESEARCH="true").ai_enable_web_research
    assert not make_settings().ai_enable_web_research
    with pytest.raises(ConfigError):
        make_settings(AI_ENABLE_WEB_RESEARCH="true", AI_ENABLE_WEB_FACT="true")


def test_the_description_names_only_what_the_run_offers() -> None:
    plain = build_default_registry(web_research_client=client(answering())).get("research_web").description
    assert "{{<ref>" not in plain and "lookup_reference" not in plain and "find_web_fact" not in plain
    cited = build_default_registry(web_research_client=client(answering()),
                                   value_references=True).get("research_web").description
    assert "{{<ref>.value_as_written}}" in cited
    gov = GovernorClient("http://gov", "k" * 40, 10, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    checked = build_default_registry(governor_client=gov, reference_lookup=True,
                                     web_research_client=client(answering())).get("research_web").description
    assert "lookup_reference" in checked


def test_the_call_reaches_v1_orc_web_with_the_turn_as_budget_key() -> None:
    seen: list = []
    registry = build_default_registry(web_research_client=client(answering(seen)))
    request, turn = current_request_id.set("ma-1-m4b"), current_turn_id.set("ma-1")
    try:
        outcome = call(registry, subjects=[" BBRI ", ""])
    finally:
        current_request_id.reset(request)
        current_turn_id.reset(turn)
    path, body, auth = seen[0]
    assert outcome.ok and path == "/v1/orc/web" and auth == "Bearer " + "w" * 40
    assert body["request_id"] == "ma-1-m4b" and body["budget_key"] == "ma-1" and body["subjects"] == ["BBRI"]
    assert body["purpose"] == "CONTEXT" and body["expected_shape"] == "SERIES"
    # outside a mode 4 run the run's own id is the budget key
    token = current_request_id.set("ma-2")
    try:
        call(registry)
    finally:
        current_request_id.reset(token)
    assert seen[-1][1]["budget_key"] == "ma-2"


def test_the_model_reads_items_conflicts_by_id_and_no_excerpts() -> None:
    view = model_view(ANSWER)
    assert [item["id"] for item in view["citable"]] == ["wab12cd34_1", "wab12cd34_2", "wab12cd34_3"]
    first = view["citable"][0]
    assert first["value_as_written"] == "US$264,70 miliar" and first["source"]["domain"] == "bps.go.id"
    assert "compared_with" not in first and "retrieved_at" not in first  # empty or internal fields are left out
    assert view["conflicts"][0]["items"] == ["wab12cd34_1", "wab12cd34_2"] and view["conflicts"][0]["chosen"] is None
    assert "text" not in json.dumps(view["sources"]) and view["budget"]["calls_left"] == 11


def test_an_unreachable_web_governor_is_a_named_error() -> None:
    outcome = call(build_default_registry(web_research_client=client(lambda r: httpx.Response(503))))
    assert not outcome.ok and outcome.output["error"]["code"] == "WEB_RESEARCH_UNAVAILABLE"


def test_a_lookup_waits_at_most_until_the_run_deadline() -> None:
    assert wait_seconds() == MAX_SECONDS
    now = time.monotonic()
    token = current_run_deadline.set(now + 100)
    try:
        assert wait_seconds(now) == pytest.approx(85.0)
        assert wait_seconds(now + 95) == MIN_SECONDS
    finally:
        current_run_deadline.reset(token)


# ------------------------------------------------------------------------------------------------- envelope

def tracked(orc=None, state=None):
    orc = orc or AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry())
    state = state or RunState(request_id="r1", started=0.0, input_items=[])
    state.tools_offered = True
    result = model_view(ANSWER)
    outcome = ToolOutcome(call_id="c1", name="research_web", ok=True, output={"result": result})
    arguments = {"need": "nilai ekspor Indonesia per tahun sejak 2018", "purpose": "CONTEXT"}
    orc._track_choices(state, "research_web", arguments, outcome)
    orc._track_references(state, "research_web", outcome, arguments)
    return orc, state, result


def test_every_item_is_a_value_reference_shown_as_a_web_fact() -> None:
    _, state, result = tracked()
    assert [item["ref"] for item in result["citable"]] == ["web.wab12cd34_1", "web.wab12cd34_2", "web.wab12cd34_3"]
    shown = render("Ekspor 2024 {{web.wab12cd34_1.value_as_written}}, 2023 {{web.wab12cd34_2.value_as_written}}.",
                   state.ref_sources)
    # user decision 2026-10-09 (B): a web value is shown without its source's name or link (Sources lists the page)
    assert shown.problems == [] and shown.text == "Ekspor 2024 US$264,70 miliar, 2023 US$258,82 miliar."
    table = render("| 2024 | {{web.wab12cd34_1.value_as_written}} |\n| 2023 | {{web.wab12cd34_2.value_as_written}} |",
                   state.ref_sources)
    assert "](" not in table.text and "bps.go.id" not in table.text
    # M132: a figure the sentence already shows is not printed again; the reference still sources it
    again = render("Ekspor 2024 mencapai US$264,70 miliar {{web.wab12cd34_1.value_as_written}}.", state.ref_sources)
    assert again.text == "Ekspor 2024 mencapai US$264,70 miliar." and again.deduplicated == ["US$264,70 miliar"]
    other = render("Ekspor 2023 US$258,82 miliar; 2024 {{web.wab12cd34_1.value_as_written}}.", state.ref_sources)
    assert other.text == "Ekspor 2023 US$258,82 miliar; 2024 US$264,70 miliar."  # a different figure is shown
    # a statement is said in the reader's words and cited by its link only; its figures stay sources
    fact = render("Ekspor naik 2,3% pada 2024 {{web.wab12cd34_3.value}}.", state.ref_sources)
    assert fact.problems == [] and fact.cited == ["web.wab12cd34_3.value"]
    assert fact.text == "Ekspor naik 2,3% pada 2024."
    assert 2.3 in {value.value for value in fact.values}
    # a web value is a context source: never a data label
    assert {value.label for value in shown.values} == {"WEB_FACT"}
    assert "fakta web" not in render("{{diff(web.wab12cd34_1.value, web.wab12cd34_2.value)|dec:0}}",
                                     state.ref_sources).text


def test_web_values_pass_provenance_as_context_and_keep_the_data_label() -> None:
    orc, state, _ = tracked()
    rendered = render("Ekspor {{web.wab12cd34_1.value_as_written}}.", state.ref_sources)
    state.ref_values.extend(rendered.values)
    from app.provenance import check_answer
    checked = check_answer(rendered.text, orc._source_index(state))
    assert checked.unsupported == [] and checked.data_kinds == []


def test_web_numbers_are_refused_in_code_and_years_of_a_fact_are_not() -> None:
    orc, state, _ = tracked()
    assert 264.7e9 in state.web_numbers and 264.7 in state.web_numbers and 2.3 in state.web_numbers
    assert 2024.0 not in state.web_numbers
    year = orc._execute(state, "c2", "run_python", json.dumps({"session_id": "s", "code": "x = df[df.year == 2024]"}))
    assert year.output.get("error", {}).get("code") != "WEB_NUMBER_IN_CALCULATION"
    refused = orc._execute(state, "c3", "run_python",
                           json.dumps({"session_id": "s", "code": "x = df[df.exports > 264.7]"}))
    assert not refused.ok and refused.output["error"]["code"] == "WEB_NUMBER_IN_CALCULATION"


def test_the_system_names_the_web_lookups_of_the_run() -> None:
    orc, state, _ = tracked()
    final = FinalResponse(response_type="ANSWER", answer="Ekspor naik.", clarification_question=None,
                          assumptions=[], limitations=[])
    line = orc._with_ai_choices(state, final).assumptions[0]
    # P3 (2026-10-08): the reader sees how many topics, how they ended and the sites; never the model's search text
    assert line == "Dicari di web (bukan dari data pasar): 1 topik, 1 ditemukan; sumber: bps.go.id, reuters.com."
    assert "nilai ekspor" not in line and "[OK" not in line
    assert C.describe_web_research([]) is None


# ------------------------------------------------------------------------------------------------- database first

TABLES = [{"table": "IDX_Stock_Universe", "description": "Listed stocks.", "entity_column": "Ticker",
           "columns": [{"column": "Sector", "description": "Sector classification.", "semantic_type": "DIMENSION",
                        "filter_allowed": True}]}]


def test_the_database_is_checked_before_research_web() -> None:
    def governor(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "OK", "tables": TABLES})

    calls: list = []
    registry = build_default_registry(
        governor_client=GovernorClient("http://gov", "k" * 40, 10, transport=httpx.MockTransport(governor)),
        web_research_client=client(answering(calls)), reference_lookup=True)
    matcher = ScriptedClient([final_response({"held": True, "table": "IDX_Stock_Universe", "column": "Sector"}),
                              final_response({"held": False, "table": "", "column": ""})])
    orc = AgentOrchestrator(make_settings(), matcher, registry)
    state = RunState(request_id="r1", started=0.0, input_items=[])
    state.tools_offered = True
    refused = orc._execute(state, "c1", "research_web", json.dumps(
        {"need": "sektor", "purpose": "CITE", "expected_shape": "FACT", "subjects": ["BBCA", "BBRI"]}))
    assert not refused.ok and refused.output["error"]["code"] == "DATABASE_HOLDS_THIS_ATTRIBUTE"
    assert "research_web runs after that read" in refused.output["error"]["message"] and calls == []
    assert "BBCA, BBRI" in matcher.payloads[0]["input"][0]["content"]
    assert orc._execute(state, "c2", "research_web", json.dumps(
        {"need": "nilai ekspor Indonesia", "purpose": "CONTEXT", "expected_shape": "SERIES", "subjects": []})).ok
    assert len(calls) == 1


# ------------------------------------------------------------------------------------------------- prompt

def test_the_one_fact_sentences_leave_only_with_research_web() -> None:
    research = data_sources_block(frozenset({"research_web"}))
    assert " ".join(OUTSIDE_DATA_RESEARCH_RULE.split()) in research and "find_web_fact" not in research
    assert "never becomes a series" not in research and "is not in the database: say so" not in research
    one_fact = data_sources_block(frozenset({"find_web_fact"}))
    assert " ".join(OUTSIDE_DATA_WEB_RULE.split()) in one_fact and "research_web" not in one_fact
    spec_path = build_system_prompt(lookup_fact=False, tools=frozenset({"research_web"}))
    assert "research_web" in spec_path and "find_web_fact" not in spec_path


def test_a_percent_web_value_declares_its_unit() -> None:
    from app.orchestrator import AgentOrchestrator as Orc  # noqa: F401 - the same orchestrator as tracked()

    percent = {**ENTRY, "id": "wab12cd34_9", "value": 2.92, "value_as_written": "2,92%", "unit": "persen",
               "unit_code": "PERCENT", "scale": None}
    orc = AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry())
    state = RunState(request_id="r1", started=0.0, input_items=[])
    result = model_view({**ANSWER, "citable": [percent]})
    orc._track_references(state, "research_web", ToolOutcome(call_id="c1", name="research_web", ok=True,
                                                             output={"result": result}), {})
    assert result["citable"][0]["unit_code"] == "PERCENT"
    assert render("{{web.wab12cd34_9.value|pct}}", state.ref_sources).text.startswith("2,92%")


# ------------------------------------------------------------------------------------------------- M126 citations

def m126_sources():
    """The shapes of the live answer of 2026-10-08 (g13 and the macro outlook): a long statement, a short name, a list,
    and a reference-table name (a database value)."""
    from app.value_refs import ReferenceSources
    sources = ReferenceSources()
    statement = ("Pemegang Saham PT Dwimuria Investama Andalan adalah Sdr. Robert Budi Hartono dan Sdr. Bambang "
                 "Hartono, sehingga pengendali terakhir BCA adalah Sdr. Robert Budi Hartono.")
    for key, value, extra in (
            ("w1_1", statement, {"statement": statement, "shape": "FACT"}),
            ("w1_2", "BCA is the largest private bank in Indonesia", {"statement": "BCA private bank", "shape": "FACT"}),
            ("w1_3", "Bank Mandiri", {"statement": "Pemegang saham mayoritas BSI"}),
            ("w1_4", "BMRI, BBNI, BBRI", {"statement": "Pemegang saham BSI", "members": ["BMRI", "BBNI", "BBRI"],
                                          "shape": "LIST"})):
        entry = {"id": key, "value": value, "label": "WEB_FACT", "quote": value, **extra}
        sources.add("web", key, entry, "WEB_FACT", origin="bca.co.id", link=f"https://www.bca.co.id/{key}")
    sources.add("reference", "r1", {"rows": [{"Ticker": "BRIS", "Company Name": "PT Bank Syariah Indonesia Tbk"}]},
                "FACT")
    return sources


def test_a_statement_is_cited_by_its_link_and_never_pasted_in() -> None:
    shown = render("BCA dikendalikan keluarga Hartono {{web.w1_1.value}}. BCA bank swasta terbesar {{web.w1_2.value}}.",
                   m126_sources())
    assert shown.problems == [] and "Pemegang Saham" not in shown.text and "largest" not in shown.text
    assert shown.text == "BCA dikendalikan keluarga Hartono. BCA bank swasta terbesar."


def test_a_name_and_a_list_are_shown_with_their_link_once_per_sentence() -> None:
    shown = render("Pemegang mayoritas BSI adalah {{web.w1_3.value}}; pemegang sahamnya {{web.w1_4.value}} dan "
                   "{{web.w1_3.value}}.", m126_sources())
    assert shown.text == "Pemegang mayoritas BSI adalah Bank Mandiri; pemegang sahamnya BMRI, BBNI, BBRI dan Bank Mandiri."


def test_a_name_the_answer_already_wrote_is_not_written_twice() -> None:
    shown = render("BRIS tercatat sebagai PT Bank Syariah Indonesia Tbk "
                   "{{reference.r1.rows[Ticker=BRIS].Company Name}} (sektor Financials).", m126_sources())
    assert shown.text == "BRIS tercatat sebagai PT Bank Syariah Indonesia Tbk (sektor Financials)."
    assert shown.deduplicated == ["PT Bank Syariah Indonesia Tbk"]
    # a database name the answer did not write is shown, without a source mark (choice C)
    assert render("BRIS: {{reference.r1.rows[Ticker=BRIS].Company Name}}.", m126_sources()).text \
        == "BRIS: PT Bank Syariah Indonesia Tbk."


def test_a_link_the_model_typed_to_a_page_the_run_did_not_read_keeps_only_its_words() -> None:
    from app.value_refs import registered_links_only
    allowed = set(m126_sources().links.values())
    text, removed = registered_links_only("Lihat [laporan BI](https://contoh.example/x) dan "
                                          "[BCA](https://www.bca.co.id/w1_1).", allowed)
    assert text == "Lihat laporan BI dan [BCA](https://www.bca.co.id/w1_1)."
    assert removed == ["https://contoh.example/x"]
    _, state, _ = tracked()
    final = FinalResponse(response_type="ANSWER", answer="Sumber: [x](https://evil.example/a).",
                          clarification_question=None, assumptions=["[y](https://www.bps.go.id/a)"], limitations=[])
    cleaned = AgentOrchestrator._registered_links_only(state, final)
    assert cleaned.answer == "Sumber: x." and cleaned.assumptions == ["y"]  # B: no web link stays in the text


def test_only_http_links_are_registered() -> None:
    from app.value_refs import ReferenceSources
    sources = ReferenceSources()
    sources.add("web", "a", {"value": 1}, "WEB_FACT", origin="x.id", link="javascript:alert(1)")
    sources.add("web", "b", {"value": 1}, "WEB_FACT", origin="x.id", link="https://x.id/b")
    assert sources.links == {("web", "b"): "https://x.id/b"}


def test_a_cited_web_fact_shows_its_page_date_and_quote_in_the_evidence() -> None:
    orc, state, _ = tracked()
    state.referenced = ["web.wab12cd34_1.value_as_written", "web.wab12cd34_3.value"]
    items = orc._evidence(state)
    assert [item["label"] for item in items] == ["Fakta web · bps.go.id", "Fakta web · reuters.com"]
    first = items[0]["source"]
    assert first["url"] == "https://www.bps.go.id/a" and first["official"] is True
    assert first["quote"] == "Januari-Desember 2024 mencapai US$264,70 miliar"


def test_an_output_figure_is_named_by_its_table_never_by_its_evidence_status() -> None:
    """Excel run 2026-10-08: the output's "label" is its evidence status; the Sources label read
    "Angka dari DATA_COVERAGE_VERIFIED: total foreign net value, rows[market board=regular]"."""
    orc, state, _ = tracked()
    state.data_record = {"outputs": [{"ref": "out.o2", "name": "bbri_foreign_flow_by_board", "output_id": "out_2c",
                                      "label": "DATA_COVERAGE_VERIFIED", "data_as_of": "2026-08-31"}]}
    state.referenced = ["out.o2.rows[market_board=Regular].total_foreign_net_value"]
    item = orc._evidence(state)[0]
    assert item["label"] == "Dari bbri foreign flow by board: total foreign net value (Regular)"
    assert "label" not in item["source"] and "DATA_COVERAGE_VERIFIED" not in json.dumps(item)


def test_the_digits_of_a_link_are_never_read_as_figures() -> None:
    """Live web test 2026-10-08 (BI-Rate, outlook 2027, coal prices): the links P1 adds carried digits in their
    addresses, and the provenance gate reported "75", "52, 9" and "0050012026" as untraced figures."""
    from app.provenance import parse_numbers
    text = ("BI-Rate 5,75% ([bi.go.id](https://www.bi.go.id/id/iru/Pages/BI--Rate-Tetap-5.75-Memperkuat.aspx)); OECD "
            "([ekonomi.bisnis.com](https://ekonomi.bisnis.com/read/20260926/9/2007406/oecd-capai-52-inflasi-3-pada-2027)); "
            "107,7 ([thedocs.worldbank.org](https://thedocs.worldbank.org/en/doc/18675f-0050012025/CMO-January-2026.pdf)) "
            "dan https://contoh.example/a/2024/77.")
    assert [n.text for n in parse_numbers(text)] == ["5,75%", "107,7"]


def test_a_figure_inside_a_cited_statement_may_be_written_in_the_readers_words() -> None:
    """Outlook 2027 (2026-10-08): the model wrote "sekitar lima persen" because it read a statement's figures as
    unreachable; a figure of the cited statement or its quote is a source when the statement is cited."""
    _, state, _ = tracked()
    from app.provenance import check_answer
    orc, _, _ = tracked()
    rendered = render("Ekspor naik 2,3% pada 2024 {{web.wab12cd34_3.value}}.", state.ref_sources)
    state.ref_values.extend(rendered.values)
    assert check_answer(rendered.text, orc._source_index(state)).unsupported == []


def test_a_web_date_the_sentence_already_writes_is_not_printed_again() -> None:
    """M132 (live 2026-10-09: "berlaku sejak 23 September 2026 2026-09-23"): the same day in any written form."""
    from app.value_refs import _already_in_sentence
    assert _already_in_sentence("2026-09-23", "berlaku sejak 23 September 2026 ")
    assert _already_in_sentence("2026-09-23", "berlaku sejak 23 Sep 2026 ")
    assert not _already_in_sentence("2026-09-23", "berlaku sejak 22 September 2026 ")
    assert not _already_in_sentence("2026-09-23", "Keputusan itu. Berlaku sejak ")  # an earlier sentence does not count
    assert _already_in_sentence("5.75 %", "BI-Rate 5,75% ")
