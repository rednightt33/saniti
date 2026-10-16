"""EXEC-1018B Fase 1 (go 2026-10-16 "Jalankan."): router cards follow the insight v2 switch (E4), the METRICS menu states
query_metric's limits (E5) and goes only to a turn that offers the tool (E8), and every value limit the arguments are
validated against reaches the model in the field's description (U6)."""
from types import SimpleNamespace

from app import conversation_router as router
from app import lanes
from app.orchestrator import AgentOrchestrator as Orchestrator
from app.tools.metric import MAX_ENTITIES, QueryMetricArgs, limits_text, menu
from app.tools.registry import strict_parameters_schema

METRIC = {"metric_id": "net_foreign_value", "label": "Net beli asing", "description": "Net value.",
          "allowed_dimensions": ["ticker", "market_board"], "default_dimensions": ["ticker", "market_board"],
          "entity_column": "ticker", "unit": "IDR", "review_status": "INFERRED", "misuse_warning": "Boards apart."}


def test_the_router_cards_follow_the_insight_switch() -> None:
    for ask_back in (False, True):
        on, off = router.router_instructions(ask_back, True), router.router_instructions(ask_back, False)
        assert "forms its own hypotheses" in on and f"up to {lanes.EXPLORE_MAX_ANGLES} angles" not in on
        assert f"up to {lanes.EXPLORE_MAX_ANGLES} angles" in off and "forms its own hypotheses" not in off
        first_off = router.first_instructions(ask_back, False)
        assert f"tests up to {lanes.EXPLORE_MAX_ANGLES} angles" in first_off
        assert router.first_instructions(ask_back) == router.first_instructions(ask_back, True)


def test_the_metric_menu_states_the_limits_the_tool_and_the_governor_enforce() -> None:
    text = menu([METRIC])
    assert limits_text() in text and f"at most {MAX_ENTITIES} entities" in text and MAX_ENTITIES == 100
    assert "at most 200 rows" in text and "use submit_data_need_spec" in text


def _brief_state(tool_filter):
    menu_text = menu([METRIC])
    return SimpleNamespace(plan_meta={"turn_kind": "CLARIFY"}, metric_note=menu_text, tool_filter=tool_filter,
                           input_items=[{"role": "user", "content": menu_text}, {"role": "user", "content": "q"}],
                           turn_notes=[], request_id="r1"), menu_text


def test_the_metric_menu_reaches_only_a_turn_that_offers_query_metric() -> None:
    state, text = _brief_state(frozenset({"get_session_output", "export_result"}))
    Orchestrator._insert_turn_brief(state)
    assert all(item["content"] != text for item in state.input_items) and state.metric_note is None
    state, text = _brief_state(frozenset({"query_metric", "submit_data_need_spec"}))
    Orchestrator._insert_turn_brief(state)
    assert any(item["content"] == text for item in state.input_items)
    state, text = _brief_state(None)  # no filter: every registered tool is offered
    Orchestrator._insert_turn_brief(state)
    assert any(item["content"] == text for item in state.input_items)


def test_every_value_limit_reaches_the_model_in_the_field_description() -> None:
    properties = strict_parameters_schema(QueryMetricArgs)["properties"]
    assert properties["entities"]["description"].endswith(f"Limits: at most {MAX_ENTITIES} items.")
    assert "Limits: 1 to 4 items." in properties["periods"]["description"]
    period = properties["periods"]["items"]["properties"]
    assert "from 1 to 260" in period["trading_days"]["description"]
    assert "matching" in period["start_date"]["description"]


# Fase 2


def _completion(*outputs: tuple[str, str, float]) -> dict:
    return {"status": "COMPLETED", "session_id": "sess_1",
            "released_outputs": [{"output_id": i, "name": n, "type": "JSON"} for i, n, _ in outputs],
            "released_contents": [{"output_id": i, "name": n, "type": "JSON", "content": {"share": v}}
                                  for i, n, v in outputs]}


def test_an_output_released_again_under_its_name_replaces_the_earlier_address() -> None:
    """E6 (M174): a later completion of the same session in the same request that releases a name again replaces the
    earlier output: it leaves the data record and its address is refused with the new one."""
    from app.orchestrator import RunState
    from app.tools import ToolOutcome, build_default_registry
    from app.value_refs import render

    orc = Orchestrator.__new__(Orchestrator)
    orc.row_reader, orc.registry = None, build_default_registry()
    state = RunState(request_id="r1", started=0.0, input_items=[])

    def track(result):
        orc._track_references(state, "complete_analysis", ToolOutcome("c", "complete_analysis", True,
                                                                      {"result": result}), {"session_id": "sess_1"})

    track(_completion(("out_a", "summary", 0.1), ("out_k", "kept", 0.3)))
    second = _completion(("out_b", "summary", 0.2))
    track(second)
    assert second["replaced_outputs"] == [{"ref": "out.o1", "replaced_by": "out.o3"}]
    assert [o["output_id"] for o in state.data_record["outputs"]] == ["out_k", "out_b"]
    stale = render("{{out.o1.content.share|dec:1}}", state.ref_sources)
    assert stale.problems and "replaced in this request by out.o3" in " ".join(map(str, stale.problems))
    assert render("{{out.o3.content.share|dec:1}} {{out.o2.content.share|dec:1}}",
                  state.ref_sources).text == "0,2 0,3"


def test_the_same_name_in_another_request_or_session_is_not_replaced() -> None:
    from app.orchestrator import RunState
    from app.tools import ToolOutcome, build_default_registry

    orc = Orchestrator.__new__(Orchestrator)
    orc.row_reader, orc.registry = None, build_default_registry()
    state = RunState(request_id="r2", started=0.0, input_items=[])
    state.data_record["outputs"].append({"ref": "out.o1", "output_id": "out_old", "session_id": "sess_1",
                                         "name": "summary", "request_id": "r1", "seq": 1})
    result = _completion(("out_new", "summary", 0.2))
    orc._track_references(state, "complete_analysis", ToolOutcome("c", "complete_analysis", True, {"result": result}),
                          {"session_id": "sess_1"})
    assert "replaced_outputs" not in result
    assert {o["output_id"] for o in state.data_record["outputs"]} == {"out_old", "out_new"}


def test_a_supporting_table_gets_an_export_address_and_cannot_be_cited() -> None:
    """E9(e): a working table released as a supporting table is listed apart in the data record with its 30-day keep,
    exported by its ref, and refused when the answer cites it; it is stored as SUPPORT (never restored as a result)."""
    from app import data_record as records
    from app.orchestrator import RunState
    from app.tools import ToolOutcome, build_default_registry
    from app.value_refs import render

    orc = Orchestrator.__new__(Orchestrator)
    orc.row_reader, orc.registry = None, build_default_registry()
    state = RunState(request_id="r1", started=0.0, input_items=[])
    result = {"status": "COMPLETED", "session_id": "sess_1", "released_outputs": [
        {"output_id": "out_r", "name": "result", "type": "JSON"},
        {"output_id": "out_s", "name": "daily_rows", "type": "TABLE", "support": True, "row_count": 3,
         "columns": ["date", "net"], "checksum_sha256": "c" * 64, "lineage": {"need_id": "need_1"}}],
        "released_contents": [{"output_id": "out_r", "name": "result", "type": "JSON", "content": {"share": 0.5}}]}
    orc._track_references(state, "complete_analysis", ToolOutcome("c", "complete_analysis", True, {"result": result}),
                          {"session_id": "sess_1"})
    support = next(o for o in state.data_record["outputs"] if o["output_id"] == "out_s")
    assert support["ref"] == "out.o2" and support["type"] == "SUPPORT"
    assert support["support"]["checksum_sha256"] == "c" * 64 and support["support"]["keep_until"]
    assert "out.o2" in result["supporting_tables_note"] and "never cite" in result["supporting_tables_note"]
    cited = render("{{out.o2.rows[0].net|int}}", state.ref_sources)
    assert cited.problems and "supporting table" in " ".join(map(str, cited.problems))
    note = records.full_note(state.data_record)
    assert records.SUPPORT_HEADER in note and "out.o2 \"daily_rows\"" in note
    released_section = note.split(records.SUPPORT_HEADER)[0]
    assert "daily_rows" not in released_section.split("Released outputs")[-1]


def test_a_need_records_the_bundle_that_delivered_it() -> None:
    from app import data_record as records

    record = records.empty()
    record["needs"].append({"need_id": "need_1", "requests": [{"data_request_id": "data_request_1_A",
                                                               "logical_name": "flow", "source_table": "T"}]})
    records.set_bundle(record, "need_1", "bundle_x")
    assert record["needs"][0]["bundle_id"] == "bundle_x"
    assert "[data_request_1_A]" in records.full_note(record)


def test_a_supporting_table_is_stored_as_support() -> None:
    from app.orchestrator import RunState
    from app.tools import ToolOutcome

    orc = Orchestrator.__new__(Orchestrator)
    state = RunState(request_id="r1", started=0.0, input_items=[])
    result = {"status": "COMPLETED", "session_id": "sess_1", "released_outputs": [
        {"output_id": "out_r", "name": "result", "type": "TABLE"},
        {"output_id": "out_s", "name": "daily_rows", "type": "TABLE", "support": True}]}
    orc._track_results(state, "complete_analysis", ToolOutcome("c", "complete_analysis", True, {"result": result}),
                       {"session_id": "sess_1"})
    assert {o["output_id"]: o["type"] for o in state.store_outputs} == {"out_r": "TABLE", "out_s": "SUPPORT"}
