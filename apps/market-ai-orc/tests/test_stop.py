"""The stop button (user decision 2026-10-09, EXEC.md EXEC-X; app/stop.py): a run stops before its next model call,
the call in flight finishes, and the user gets what was done (or a plain stopped line); only the run's owner can stop
it, and a run that is not running is never revealed."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import stop
from conftest import BASE_ENV, ScriptedClient, make_settings, tool_call_response
from test_orchestrator import orchestrator, request

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}


def test_only_the_owner_stops_a_running_request_and_nothing_else_is_revealed() -> None:
    with stop.running("edge_1", "owner-a") as flag:
        assert stop.stop("edge_1", "owner-b") == "NOT_RUNNING" and not flag.is_set()
        assert stop.stop("edge_2", "owner-a") == "NOT_RUNNING"
        assert stop.stop("edge_1", "owner-a") == "STOPPING" and flag.is_set() and stop.requested()
    assert not stop.requested() and stop.stop("edge_1", "owner-a") == "NOT_RUNNING"  # finished: forgotten


class PressStop(ScriptedClient):
    """The user presses Stop while the first model call is running."""

    def create(self, payload):
        stop.current_stop.get().set()
        return super().create(payload)


def test_a_stopped_run_makes_no_new_model_call_and_says_it_was_stopped() -> None:
    agent, _ = orchestrator([])
    client = PressStop([tool_call_response("get_system_capabilities"), tool_call_response("get_system_capabilities")])
    agent.client = client
    with stop.running("r1", None):
        result = agent.run(request())
    assert len(client.payloads) == 1  # the call in flight finished; none started after the stop
    text = (result.response.answer if result.response else "") + " ".join(result.response.limitations
                                                                           if result.response else [])
    assert "dihentikan oleh Anda" in text


def test_the_stop_route_answers_404_for_a_run_that_is_not_running() -> None:
    from app.main import create_app
    client = TestClient(create_app(make_settings()))
    response = client.post("/v1/agent/run/edge_none/stop", headers=AUTH)
    assert response.status_code == 404 and response.json() == {"status": "NOT_RUNNING"}
    assert client.post("/v1/agent/run/edge_none/stop").status_code in (401, 403)
