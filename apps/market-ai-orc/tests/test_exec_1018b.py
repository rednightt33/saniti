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
