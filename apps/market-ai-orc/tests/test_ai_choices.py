"""S4 "Pilihan AI" (PLAN_FINAL_2026-10-04.md Fase 3, K6): the values the model typed into code that ran, to filter,
group or set a threshold, are traced to their origin by the system; what is neither the user's nor the data's is shown
as the AI's choice, and such a typed parameter is no longer a reason to refuse the answer (P25)."""
from __future__ import annotations

from app import ai_choices as C
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import ToolOutcome, build_default_registry
from conftest import ScriptedClient, make_settings

# the g5.6 code (golden test ma-golden-20261004a): the BUMN list and the 95th percentile were the model's
G5_6 = """
bumn = ['BBCA','BBRI','BMRI','BBNI','BBTN','BRIS']
present = [t for t in bumn if t in set(uni['Ticker'])]
flow_b = flow[flow['Symbol'].isin(present)]
daily = flow_b.groupby('Date')['Net Value'].sum().sort_index()
thr = float(np.percentile(daily.values, 95))
summary = daily.agg(['count', 'mean'])
"""
# the g6 code: RSI below 30, a gain of at least 3% in 10 days, all from the user's question
G6 = """
elig = df[df['rsi14'].notna()]
events = elig[elig['rsi14'] < 30]
base = elig[elig['rsi14'] >= 30]
events['succ'] = events['fwd10'] >= 0.03
"""
G6_WORDS = "Apakah saham dengan RSI di bawah 30 cenderung naik minimal 3% dalam 10 hari bursa?"


def choices(code: str, words: str = "", seen_strings=(), seen_sets=(), numbers=()):
    return C.classify(C.typed_values(code), words, set(seen_strings), set(seen_sets), list(numbers))


def test_the_g5_6_list_and_percentile_are_the_ais_choices() -> None:
    found = choices(G5_6, "Uji ide saya: efeknya hanya di bank BUMN.")
    assert {"kind": "LIST", "value": ["BBCA", "BBRI", "BMRI", "BBNI", "BBTN", "BRIS"], "position": "LIST"} in found
    assert any(c["kind"] == "NUMBER" and c["value"] == 95.0 for c in found)
    assert not any(c["value"] == ["count", "mean"] for c in found)  # statistic names are not values
    line = C.describe(found)
    assert line.startswith("Pilihan AI") and "BBCA, BBRI, BMRI, BBNI, BBTN, BRIS" in line and "percentile 95" in line


def test_the_users_thresholds_are_not_shown() -> None:
    assert choices(G6, G6_WORDS) == []  # 30 and 3% (0.03) are the user's words


def test_a_broker_code_list_typed_in_code_is_shown() -> None:
    code = "brokers = ['AK', 'BK', 'ZP']\nsel = flow[flow['Broker'].isin(brokers)]"
    found = choices(code, "Cari broker yang akumulasi, kamu yang tentukan berdasarkan net value")
    assert found and found[0]["value"] == ["AK", "BK", "ZP"]


def test_a_list_the_data_returned_whole_is_from_the_data() -> None:
    """The model typed the tickers a ranking tool returned: data, not a choice."""
    code = "top = ['BBCA', 'BBRI', 'BMRI']\nsel = df[df['ticker'].isin(top)]"
    seen: set[frozenset[str]] = set()
    C.string_sets({"rows": [{"ticker": "BBCA"}, {"ticker": "BBRI"}, {"ticker": "BMRI"}]}, seen)
    assert choices(code, "", seen_sets=seen) == []
    # a subset of what the data returned is still a choice
    assert choices("pick = ['BBCA', 'BBRI']\nx = df[df.ticker.isin(pick)]", "", seen_sets=seen)


def test_a_value_chosen_by_code_from_the_data_is_not_a_literal() -> None:
    code = "top = df.groupby('ticker')['value'].sum().nlargest(10).index\nsel = df[df['ticker'].isin(top)]"
    assert choices(code, "10 saham paling likuid") == []


def test_a_single_filter_value_from_a_tool_result_is_from_the_data() -> None:
    seen: set[str] = set()
    C.string_leaves({"values": ["Regular", "Negotiated"]}, seen)
    assert choices("x = df[df['board'] == 'Regular']", "", seen_strings=seen) == []
    assert choices("x = df[df['board'] == 'Regular']", "") != []


def orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry())


def ran(code: str, status: str = "OK") -> ToolOutcome:
    return ToolOutcome(call_id="c1", name="run_python", ok=True,
                       output={"result": {"status": status, "execution_id": "exe_1", "stdout": "BBCA BBRI"}})


def test_the_system_writes_the_line_and_a_typed_percentile_is_no_longer_refused() -> None:
    """P25 (golden 2026-10-02): "persentil ke-90" forced a LIMITATION; now it is shown as the AI's choice."""
    orc = orchestrator()
    state = RunState(request_id="r1", started=0.0, input_items=[], user_text="Broker mana yang beli besar?")
    orc._track_choices(state, "run_python", {"code": "thr = df['net'].quantile(0.9)\nbig = df[df['net'] > thr]"},
                       ran(""))
    assert state.ai_choices == [{"kind": "NUMBER", "value": 0.9, "position": "CALL:quantile"}]
    from app.provenance import check_answer
    assert check_answer("Ambang persentil ke-90 dipakai.", orc._source_index(state)).unsupported == []
    final = FinalResponse(response_type="ANSWER", answer="Ambang persentil ke-90 dipakai.",
                          clarification_question=None, assumptions=["data harian"], limitations=[])
    out = orc._with_ai_choices(state, final)
    assert out.assumptions[0].startswith("Pilihan AI") and out.assumptions[1] == "data harian"


def test_failed_code_and_printed_text_are_not_read() -> None:
    orc = orchestrator()
    state = RunState(request_id="r1", started=0.0, input_items=[])
    orc._track_choices(state, "run_python", {"code": "x = df[df.v > 42]"}, ran("", status="ERROR"))
    assert state.ai_choices == []
    orc._track_choices(state, "run_python", {"code": "x = df[df.v > 42]"}, ran(""))
    assert state.ai_choices and "BBCA BBRI" not in state.seen_strings  # its stdout is not data


# ------------------------------------------------------------------ S4c: reasoning replayed within one run (K7)

def replay_run(*extra_responses, **settings):
    from conftest import ANSWER, final_response, tool_call_response
    from test_orchestrator import orchestrator, request
    responses = [tool_call_response("get_system_capabilities", call_id="c1"), *extra_responses, final_response(ANSWER)]
    agent, client = orchestrator(responses, **settings)
    result = agent.run(request())
    return result, client


def test_reasoning_goes_back_with_its_calls_when_switched_on() -> None:
    _, client = replay_run(AI_REPLAY_REASONING="true")
    second = client.payloads[1]["input"]
    kinds = [item.get("type") for item in second if item.get("type")]
    assert kinds[-3:] == ["reasoning", "function_call", "function_call_output"]
    assert second[kinds.index("reasoning") - len(kinds) + len(second)]["summary"][0]["text"] == "hidden"


def test_reasoning_stays_out_by_default() -> None:
    _, client = replay_run()
    assert not any(item.get("type") == "reasoning" for item in client.payloads[1]["input"])


def test_a_provider_that_refuses_replayed_reasoning_falls_back_for_the_run() -> None:
    from app.openrouter_client import ProviderError
    result, client = replay_run(ProviderError("bad input item", code="PROVIDER_REJECTED", status_code=400),
                                AI_REPLAY_REASONING="true")
    assert result.status == "COMPLETED"
    assert any(i.get("type") == "reasoning" for i in client.payloads[1]["input"])  # refused
    assert not any(i.get("type") == "reasoning" for i in client.payloads[2]["input"])  # retried without
