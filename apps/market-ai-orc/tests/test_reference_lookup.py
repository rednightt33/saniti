"""P34 (plan 2026-10-05 Fase D option A): the database before the web.

lookup_reference reads the static reference tables through the SQL Governor and is offered in every reading step
(effect READS, so the FACT step too). Before find_web_fact runs, one small matcher call compares the asked attribute
with the reference columns derived from the Governor; when one holds it, the web call is refused until the run has
read the reference tables. Every failure lets the web call run. Web facts only describe: a number only a web fact
supplied is refused once in code, and a web list used to filter is shown as a web fact, not as data."""
from __future__ import annotations

import json

import httpx

from app import ai_choices as C
from app import conversation_router as router
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import ToolOutcome, build_default_registry
from app.tools.request_data import GovernorClient
from app.tools.web_fact import WebFactClient, model_view
from conftest import ScriptedClient, final_response, make_settings

TABLES = [{"table": "IDX_Stock_Universe", "description": "Listed stocks.", "entity_column": "Ticker",
           "columns": [{"column": "Ticker", "description": "Stock code.", "semantic_type": "IDENTIFIER",
                        "filter_allowed": True},
                       {"column": "Sector", "description": "Sector classification.", "semantic_type": "DIMENSION",
                        "filter_allowed": True}]}]
ROWS = {"status": "ROWS_READY", "table": "IDX_Stock_Universe", "columns": ["Ticker", "Sector"],
        "rows": [{"Ticker": "BBCA", "Sector": "Finance"}], "matched": 1, "truncated": False}
WEB = {"status": "CONFIRMED", "subject": "BBCA", "attribute": "sector", "value": "Finance", "as_of": "2026-10-05",
       "cached": False, "versions": [{"value": "Finance", "domains": ["a.com"], "official": False, "quotes": []}],
       "sources": [{"n": 1}]}


class Governor:
    def __init__(self, columns_status: int = 200) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.columns_status = columns_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if request.url.path == "/v1/catalog/reference-columns":
            return httpx.Response(self.columns_status, json={"status": "OK", "tables": TABLES})
        return httpx.Response(200, json=ROWS)


def setup(matcher_replies: list, governor: Governor | None = None):
    governor = governor or Governor()
    web_calls: list[dict] = []

    def web(request: httpx.Request) -> httpx.Response:
        web_calls.append(json.loads(request.content))
        return httpx.Response(200, json=WEB)

    registry = build_default_registry(
        governor_client=GovernorClient("http://gov", "k" * 40, 10, transport=httpx.MockTransport(governor)),
        web_fact_client=WebFactClient("http://web", "w" * 40, transport=httpx.MockTransport(web)),
        reference_lookup=True)
    client = ScriptedClient(matcher_replies)
    orc = AgentOrchestrator(make_settings(), client, registry)
    state = RunState(request_id="r1", started=0.0, input_items=[])
    state.tools_offered = True
    return orc, state, client, governor, web_calls


def web_call(orc, state, call_id="c1", attribute="sector"):
    return orc._execute(state, call_id, "find_web_fact", json.dumps({"subject": "BBCA", "attribute": attribute}))


def held(table="IDX_Stock_Universe", column="Sector"):
    return final_response({"held": True, "table": table, "column": column})


def test_the_tool_exists_only_with_its_switch_and_reads_in_every_reading_step() -> None:
    gov = GovernorClient("http://gov", "k" * 40, 10, transport=httpx.MockTransport(Governor()))
    assert "lookup_reference" not in build_default_registry(governor_client=gov).names()
    registry = build_default_registry(governor_client=gov, reference_lookup=True)
    assert registry.get("lookup_reference").effect == "READS"
    assert "lookup_reference" in registry.names_with_effect(router.READ_EFFECTS)
    web = WebFactClient("http://web", "w" * 40, transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with_ref = build_default_registry(governor_client=gov, reference_lookup=True, web_fact_client=web)
    assert "lookup_reference" in with_ref.get("find_web_fact").description
    assert "lookup_reference" not in build_default_registry(web_fact_client=web).get("find_web_fact").description
    assert make_settings(AI_ENABLE_REFERENCE_LOOKUP="true").ai_enable_reference_lookup
    assert not make_settings().ai_enable_reference_lookup


def test_lookup_reference_lists_then_reads_rows() -> None:
    orc, state, _, governor, _ = setup([])
    listed = orc.registry.execute("c1", "lookup_reference", json.dumps(
        {"table": None, "columns": [], "where": [], "match": None}))
    assert listed.ok and listed.output["result"]["tables"] == TABLES
    rows = orc.registry.execute("c2", "lookup_reference", json.dumps(
        {"table": "IDX_Stock_Universe", "columns": ["Sector"], "where": [{"column": "Ticker", "values": ["BBCA"]}],
         "match": None}))
    assert rows.ok and rows.output["result"]["rows"] == ROWS["rows"]
    sent = governor.calls[-1][1]
    assert sent["where"] == [{"column": "Ticker", "operator": "EQ", "value": "BBCA"}] and sent["match"] is None
    orc.registry.execute("c3", "lookup_reference", json.dumps(
        {"table": "IDX_Stock_Universe", "columns": [], "where": [{"column": "Ticker", "values": ["BBCA", "BBRI"]}],
         "match": {"column": "Sector", "text": "fin"}}))
    sent = governor.calls[-1][1]
    assert sent["columns"] == ["Ticker", "Sector"]  # empty columns: the table's listed columns
    assert sent["where"][0] == {"column": "Ticker", "operator": "IN", "value": ["BBCA", "BBRI"]}
    assert sent["match"] == {"column": "Sector", "text": "fin"}


def test_an_attribute_the_database_holds_is_refused_until_the_table_is_read() -> None:
    orc, state, client, _, web_calls = setup([held(), held()])
    refused = web_call(orc, state)
    assert not refused.ok and refused.output["error"]["code"] == "DATABASE_HOLDS_THIS_ATTRIBUTE"
    assert refused.output["error"]["next_action"] == "CALL:lookup_reference"
    assert refused.output["error"]["suggested_call"]["table"] == "IDX_Stock_Universe"
    assert refused.output["error"]["suggested_call"]["columns"] == ["Sector"] and web_calls == []
    payload = client.payloads[0]
    assert payload["text"]["format"]["strict"] is True and "Sector classification." in payload["input"][0]["content"]
    assert state.input_tokens > 0  # the matcher's usage counts in the run
    assert not web_call(orc, state, "c2").ok and web_calls == []  # not read yet: refused again
    orc._execute(state, "c3", "lookup_reference", json.dumps(
        {"table": "IDX_Stock_Universe", "columns": ["Sector"], "where": [{"column": "Ticker", "values": ["BBCA"]}],
         "match": None}))
    assert state.reference_reads == 1
    assert web_call(orc, state, "c4").ok and len(web_calls) == 1  # after the read the web may still answer


def test_an_attribute_the_database_does_not_hold_goes_to_the_web() -> None:
    orc, state, _, _, web_calls = setup([final_response({"held": False, "table": "", "column": ""})])
    assert web_call(orc, state, attribute="controlling shareholder").ok and len(web_calls) == 1


def test_every_failure_lets_the_web_call_run() -> None:
    # a matcher that names a column the catalog does not list
    orc, state, _, _, web_calls = setup([held(column="Owner")])
    assert web_call(orc, state).ok and len(web_calls) == 1
    # the matcher call fails
    orc, state, _, _, web_calls = setup([RuntimeError("provider down")])
    assert web_call(orc, state).ok and len(web_calls) == 1
    # the Governor cannot list the columns (no matcher call is made)
    orc, state, client, _, web_calls = setup([], Governor(columns_status=503))
    assert web_call(orc, state).ok and len(web_calls) == 1 and client.payloads == []


def test_no_check_when_lookup_reference_is_not_offered_in_this_step() -> None:
    orc, state, client, _, web_calls = setup([])
    state.tool_filter = frozenset({"find_web_fact"})
    assert web_call(orc, state).ok and client.payloads == [] and len(web_calls) == 1


def test_reference_rows_are_a_source_of_the_answer() -> None:
    orc, state, _, _, _ = setup([])
    outcome = ToolOutcome(call_id="c1", name="lookup_reference", ok=True,
                          output={"result": {**ROWS, "rows": [{"Ticker": "BBCA", "listed": 2000}]}})
    orc._track_sources(state, "lookup_reference", {}, outcome)
    assert state.facts[-1]["kind"] == "FACT" and 2000.0 in state.facts[-1]["values"]


# ------------------------------------------------------------------ web facts only describe

def web_fact(orc, state, value: str) -> None:
    orc._track_choices(state, "find_web_fact", {}, ToolOutcome(
        call_id="w1", name="find_web_fact", ok=True,
        output={"result": model_view({**WEB, "value": value, "versions": [{"value": value, "domains": ["a.com"]}]})}))


def test_a_number_only_a_web_fact_supplied_is_refused_once_in_code() -> None:
    orc, state, _, _, _ = setup([])
    web_fact(orc, state, "holds 56.7% of the shares")
    assert 56.7 in state.web_numbers and 56.7 not in state.context_numbers
    code = json.dumps({"session_id": "s", "code": "x = df[df['own'] > 56.7]"})
    refused = orc._execute(state, "c1", "run_python", code)
    assert not refused.ok and refused.output["error"]["code"] == "WEB_NUMBER_IN_CALCULATION"
    assert "56.7" in refused.output["error"]["message"]
    second = orc._execute(state, "c2", "run_python", code)  # once per run: the next call is not refused for it
    assert second.output.get("error", {}).get("code") != "WEB_NUMBER_IN_CALCULATION"


def test_a_web_number_the_user_or_the_data_also_gave_is_not_refused() -> None:
    values = C.typed_values("x = df[df['own'] > 56.7]")
    assert C.web_numbers_in_code(values, "", [56.7], []) == [56.7]
    assert C.web_numbers_in_code(values, "kepemilikan di atas 56,7%", [56.7], []) == []
    assert C.web_numbers_in_code(values, "", [56.7], [56.7]) == []
    assert C.web_numbers_in_code(C.typed_values("x = df[df['a'] > 1]"), "", [1.0], []) == []


def test_a_web_list_used_to_filter_is_shown_as_a_web_fact_not_as_data() -> None:
    orc, state, _, _, _ = setup([])
    orc._track_choices(state, "find_web_fact", {}, ToolOutcome(
        call_id="w1", name="find_web_fact", ok=True,
        output={"result": {**model_view(WEB), "value": "BUMI", "versions": [
            {"value": "BUMI", "domains": ["a.com"]}, {"value": "BRMS", "domains": ["b.com"]}]}}))
    code = "group = ['BUMI', 'BRMS']\nsel = df[df['ticker'].isin(group)]"
    orc._track_choices(state, "run_python", {"code": code}, ToolOutcome(
        call_id="c1", name="run_python", ok=True, output={"result": {"status": "OK"}}))
    assert state.ai_choices and state.ai_choices[0]["origin"] == "WEB"
    final = FinalResponse(response_type="ANSWER", answer="ok", clarification_question=None, assumptions=[],
                          limitations=[])
    lines = orc._with_ai_choices(state, final).assumptions
    assert any(line.startswith("Fakta web dipakai di kode") and "BUMI, BRMS" in line for line in lines)
    assert not any(line.startswith("Pilihan AI") for line in lines)
