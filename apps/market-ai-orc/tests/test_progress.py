"""Run progress for EDGE (EXEC-IMPL-1016 Fase 4.3, UI-1015B; app/progress.py): a run's steps in plain words while
it runs (understanding the question, each model call, each tool by what it does), readable only by the run's owner,
kept a short while after the run ends, never with arguments or values."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import progress, user_texts
from conftest import BASE_ENV, ScriptedClient, make_settings, tool_call_response
from test_orchestrator import orchestrator, request

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}


def test_only_the_owner_reads_a_runs_steps_and_a_finished_run_stays_readable() -> None:
    with progress.tracking("edge_p1", "owner-a"):
        with progress.step("Langkah satu"):
            seen = progress.snapshot("edge_p1", "owner-a")
            assert seen["status"] == "RUNNING" and seen["steps"][0]["state"] == "running"
        with progress.step("Langkah dua") as mark:
            mark("refused")
        assert progress.snapshot("edge_p1", "owner-b") is None and progress.snapshot("edge_x", "owner-a") is None
    done = progress.snapshot("edge_p1", "owner-a")
    assert done["status"] == "FINISHED"
    assert [(s["label"], s["state"]) for s in done["steps"]] == [("Langkah satu", "done"), ("Langkah dua", "refused")]
    with progress.step("outside a run"):  # nothing is recorded without a tracked run
        pass


def test_a_step_that_raises_is_failed_and_a_long_run_keeps_its_newest_steps(monkeypatch) -> None:
    monkeypatch.setattr(progress, "MAX_STEPS", 3)
    with progress.tracking("edge_p2", None):
        try:
            with progress.step("Gagal"):
                raise RuntimeError("x")
        except RuntimeError:
            pass
        for index in range(4):
            with progress.step(f"s{index}"):
                pass
    view = progress.snapshot("edge_p2", None)
    assert [s["label"] for s in view["steps"]] == ["s1", "s2", "s3"] and view["earlier_steps"] == 2


def test_a_run_records_its_model_calls_and_tools_in_plain_words() -> None:
    agent, _ = orchestrator([])
    agent.client = ScriptedClient([tool_call_response("get_system_capabilities")])
    with progress.tracking("edge_p3", None):
        agent.run(request())
    steps = progress.snapshot("edge_p3", None)["steps"]
    labels = [s["label"] for s in steps]
    assert labels[0] == user_texts.PROGRESS_THINKING
    assert user_texts.PROGRESS_EFFECTS["READS"] in labels  # get_system_capabilities is named by what it does
    assert all(s["state"] != "running" for s in steps)
    assert "get_system_capabilities" not in json.dumps(steps)  # plain words, never a tool name


def test_every_tool_effect_has_a_progress_label() -> None:
    from app.tools.system import EFFECT_CAPABILITIES
    assert set(EFFECT_CAPABILITIES) == set(user_texts.PROGRESS_EFFECTS)
    assert progress.tool_label("run_python", "COMPUTES") == user_texts.HURDLE_STEPS["run_python"]
    assert progress.tool_label("unknown_tool", None) == user_texts.HURDLE_TOOL_STEP


def test_the_progress_route_reads_a_run_and_hides_others() -> None:
    from app.main import create_app

    seen: dict = {}

    class Peeks:
        def run(self, request, **_):
            with progress.step("Bekerja"):
                seen["inside"] = client.get(f"/v1/agent/requests/{request.request_id}/progress", headers=AUTH).json()
            agent, _ = orchestrator([])
            agent.client = ScriptedClient([tool_call_response("get_system_capabilities")])
            return agent.run(request)

    client = TestClient(create_app(make_settings(), orchestrator=Peeks()))
    client.post("/v1/agent/run", headers=AUTH, json={"request_id": "edge_p4", "message": "Harga BBCA?",
                                                    "history_mode": "CLIENT"})
    assert seen["inside"]["status"] == "RUNNING" and seen["inside"]["steps"][-1]["label"] == "Bekerja"
    after = client.get("/v1/agent/requests/edge_p4/progress", headers=AUTH)
    assert after.status_code == 200 and after.json()["status"] == "FINISHED"
    assert client.get("/v1/agent/requests/edge_none/progress", headers=AUTH).status_code == 404
    assert client.get("/v1/agent/requests/edge_p4/progress").status_code in (401, 403)
