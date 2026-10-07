"""Mode switcher (user decision 2026-09-30, app/modes.py): AI_MODE_SWITCH sets the default mode (1 AUTO, 2 ANALYSIS,
3 RESEARCH, 4 MODE4), analysis_path chooses per request (AUTO is new), a reply continues in the mode of its plan, and
a default the deployment cannot run falls back to AUTO. execution.mode records the mode and why."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError
from app.main import create_app
from app.modes import effective_default, is_mode4_plan, path_for, resolve_mode
from app.orchestrator import AgentOrchestrator
from conftest import ScriptedClient, final_response, make_settings
from test_analysis_path import AUTH
from test_mode4 import ANALYSIS, BROKER, FIRST_ROUND, MODE4, mode4_agent
from test_multi_angle import MA, RunSandbox, ma_registry

MODE4_PLAN = SimpleNamespace(origin_request_id="q1-m4d")
OLD_PLAN = SimpleNamespace(origin_request_id="q1")
# M105 (golden test 2026-10-07): since EXEC-P1 the waiting plan comes from step B; C revises, a CONTINUE step proposes
STEP_PLANS = [SimpleNamespace(origin_request_id=f"q1-{suffix}") for suffix in ("m4b", "m4c", "m4n")]


@pytest.mark.parametrize("requested,continuation,default,expected", [
    ("AUTO", None, 4, (1, "CALLER")), ("ANALYSIS", None, 4, (2, "CALLER")), ("RESEARCH", None, 1, (3, "CALLER")),
    ("MODE4", None, 1, (4, "CALLER")), ("AUTO", MODE4_PLAN, 4, (1, "CALLER")),    # the caller always wins
    (None, MODE4_PLAN, 1, (4, "CONTINUATION")), (None, OLD_PLAN, 4, (1, "CONTINUATION")),
    (None, OLD_PLAN, 2, (1, "CONTINUATION")),                                      # "Setuju" is never lost to ANALYSIS
    (None, None, 1, (1, "SWITCH")), (None, None, 2, (2, "SWITCH")), (None, None, 3, (3, "SWITCH")),
    (None, None, 4, (4, "SWITCH"))])
def test_the_mode_of_a_request(requested, continuation, default, expected) -> None:
    assert resolve_mode(requested, continuation, default) == expected


@pytest.mark.parametrize("plan", STEP_PLANS)
def test_a_reply_to_a_plan_of_any_mode4_step_stays_in_mode4(plan) -> None:
    assert is_mode4_plan(plan) and resolve_mode(None, plan, 1) == (4, "CONTINUATION")
    assert not is_mode4_plan(SimpleNamespace(origin_request_id="q1-m4a")) \
        and not is_mode4_plan(SimpleNamespace(origin_request_id="q1-m4q"))  # steps that never issue a plan


def test_paths_plans_and_fallback() -> None:
    assert [path_for(m) for m in (1, 2, 3, 4)] == [None, "ANALYSIS", "RESEARCH", "MODE4"]
    assert is_mode4_plan(MODE4_PLAN) and not is_mode4_plan(OLD_PLAN) and not is_mode4_plan(None)
    plain = SimpleNamespace(analysis_path=False)
    assert effective_default(4, plain) == 1 and effective_default(2, plain) == 1
    assert effective_default(3, SimpleNamespace(analysis_path=True)) == 3
    assert effective_default(4, SimpleNamespace(analysis_path=True, mode4=True)) == 4


@pytest.mark.parametrize("env,message", [
    ({"AI_MODE_SWITCH": "0"}, "AI_MODE_SWITCH must be"), ({"AI_MODE_SWITCH": "5"}, "must be 1"),
    ({"AI_MODE_SWITCH": "x"}, "integer"),
    ({"AI_MODE_SWITCH": "4"}, "needs AI_ENABLE_MODE4"), ({"AI_MODE_SWITCH": "2"}, "needs AI_ENABLE_ANALYSIS_PATH")])
def test_an_invalid_switch_stops_startup(env, message) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**env)


def test_switch_1_is_the_default() -> None:
    assert make_settings().ai_mode_switch == 1 and make_settings(**MODE4).ai_mode_switch == 1


def post(app, body: dict) -> dict:
    with TestClient(app) as client:
        response = client.post("/v1/agent/run", json=body, headers=AUTH)
        assert response.status_code == 200, response.text
        return response.json()


def test_switch_4_runs_mode4_and_auto_runs_the_model_choice() -> None:
    runner, scripted, _ = mode4_agent(FIRST_ROUND)
    app = create_app(make_settings(**MODE4, AI_MODE_SWITCH="4"), orchestrator=runner.inner)
    body = post(app, {"request_id": "s1", "conversation_id": "conv_1", "message": BROKER})
    assert body["mode4"]["round"] == "FIRST" and body["status"] == "AWAITING_CONFIRMATION"
    assert body["execution"]["mode"] == {"mode": 4, "name": "MODE4", "source": "SWITCH"}
    runner, scripted, _ = mode4_agent([final_response(ANALYSIS)])
    app = create_app(make_settings(**MODE4, AI_MODE_SWITCH="4"), orchestrator=runner.inner)
    body = post(app, {"request_id": "s2", "message": BROKER, "analysis_path": "AUTO"})
    assert "mode4" not in body and body["response"]["response_type"] == "ANSWER"
    assert body["execution"]["mode"] == {"mode": 1, "name": "AUTO", "source": "CALLER"}
    assert "analysis_path" not in body["execution"]  # AUTO is the model's own choice, no path is fixed
    assert "ANALYSIS path" not in str(scripted.payloads[0]["input"])


def test_switch_1_keeps_the_old_default_and_mode4_is_chosen_per_request() -> None:
    runner, scripted, _ = mode4_agent([final_response(ANALYSIS)])
    app = create_app(make_settings(**MODE4), orchestrator=runner.inner)
    body = post(app, {"request_id": "s3", "message": BROKER})
    assert "mode4" not in body and body["execution"]["mode"]["source"] == "SWITCH"
    runner, scripted, _ = mode4_agent(FIRST_ROUND)
    app = create_app(make_settings(**MODE4), orchestrator=runner.inner)
    body = post(app, {"request_id": "s4", "conversation_id": "conv_1", "message": BROKER, "analysis_path": "MODE4"})
    assert body["mode4"]["round"] == "FIRST" and body["execution"]["mode"]["name"] == "MODE4"


def test_switch_2_answers_through_the_analysis_path() -> None:
    runner, scripted, _ = mode4_agent([final_response(ANALYSIS)])
    app = create_app(make_settings(**MODE4, AI_MODE_SWITCH="2"), orchestrator=runner.inner)
    body = post(app, {"request_id": "s5", "message": BROKER})
    assert body["execution"]["mode"] == {"mode": 2, "name": "ANALYSIS", "source": "SWITCH"}
    assert body["execution"]["analysis_path"]["requested"] == "ANALYSIS"


def test_a_default_the_deployment_cannot_run_falls_back_to_auto() -> None:
    # AI_ENABLE_MODE4 is on but the orchestrator has no caller-chosen paths, so mode 4 cannot run
    settings = make_settings(**MA, AI_ENABLE_MODE4="true", AI_ENABLE_ANALYSIS_PATH="true", AI_MODE_SWITCH="4")
    inner = AgentOrchestrator(make_settings(**MA), ScriptedClient([final_response(ANALYSIS)]),
                              ma_registry(RunSandbox()))
    body = post(create_app(settings, orchestrator=inner), {"request_id": "s6", "message": BROKER})
    assert body["execution"]["mode"] == {"mode": 1, "name": "AUTO", "source": "FALLBACK"}
    assert "mode4" not in body
