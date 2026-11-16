"""M475 (ERRORS_AND_SOLUTIONS.md; EXEC-MU-ACCOUNTS contract section 7): every route that takes an owner refuses a
missing or blank X-Saniti-Owner (400 OWNER_REQUIRED, never the shared owner "default"); a caller holding
MARKET_AI_ORC_TEST_KEY may name only test owners (403 OWNER_NOT_ALLOWED); progress and stop store the normalised owner
and never match a run or a caller without one; a CLIENT-history run registers its owner too."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import progress, stop
from app.conversations import TEST_OWNER_RE, ConversationError, owner_from_header
from app.main import create_app
from app.manual_agent import ManualAgent
from conftest import BASE_ENV, ScriptedClient, make_settings, tool_call_response
from test_orchestrator import orchestrator

TEST_KEY = "test-runner-key-" + "t" * 24
MAIN = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}
TESTER = {"Authorization": f"Bearer {TEST_KEY}"}
RUN_BODY = {"request_id": "own_1", "message": "Harga BBCA?", "history_mode": "CLIENT"}

# every route that takes an owner (method, path, json body); the walk below checks none is missing
OWNER_ROUTES = [
    ("POST", "/v1/agent/run", RUN_BODY),
    ("POST", "/v1/agent/run/own_1/stop", None),
    ("GET", "/v1/agent/requests/own_1/progress", None),
    ("GET", "/v1/agent/requests/own_1", None),
    ("GET", "/v1/conversations/conv_" + "0" * 32 + "/messages", None),
    ("POST", "/v1/conversations/conv_" + "0" * 32 + "/branch", {"through_turn": 1}),
    ("POST", "/v1/conversations/conv_" + "0" * 32 + "/outputs/out_1/export", {"columns": [], "titles": []}),
    ("GET", "/v1/exports/exp_" + "0" * 24 + "/download", None),
    ("GET", "/v1/dev/manual/steps", None),
    ("POST", "/v1/dev/manual/steps/abc", {"response": {"output": []}}),
]


class Answers:
    """A stand-in orchestrator: one model call that reads the capabilities."""

    class registry:  # noqa: N801 - what the app's shutdown closes
        @staticmethod
        def close() -> None:
            pass

    def run(self, request, **_):
        agent, _ = orchestrator([])
        agent.client = ScriptedClient([tool_call_response("get_system_capabilities")])
        return agent.run(request)


def client_for(**env: str) -> TestClient:
    settings = make_settings(MARKET_AI_ORC_TEST_KEY=TEST_KEY, AI_ENABLE_MANUAL_AGENT="true",
                             AI_MANUAL_AGENT_WAIT_SECONDS="30", **env)
    return TestClient(create_app(settings, orchestrator=Answers(),
                                 manual_agent=ManualAgent(ScriptedClient([]), settings)))


def call(client: TestClient, method: str, path: str, body, headers: dict):
    return client.request(method, path, headers=headers, json=body)


def test_the_route_list_covers_every_route_that_reads_the_owner_header() -> None:
    app = create_app(make_settings(), orchestrator=Answers())
    reading = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is not None and any(p.alias.lower() == "x-saniti-owner" for p in dependant.header_params):
            reading.update((method, route.path) for method in route.methods)
    assert reading == {
        ("POST", "/v1/agent/run"), ("POST", "/v1/agent/run/{request_id}/stop"),
        ("GET", "/v1/agent/requests/{request_id}/progress"), ("GET", "/v1/agent/requests/{request_id}"),
        ("GET", "/v1/conversations/{conversation_id}/messages"), ("POST", "/v1/conversations/{conversation_id}/branch"),
        ("POST", "/v1/conversations/{conversation_id}/outputs/{output_id}/export"),
        ("GET", "/v1/exports/{export_id}/download"), ("GET", "/v1/dev/manual/steps"),
        ("POST", "/v1/dev/manual/steps/{step_id}")}
    assert len(OWNER_ROUTES) == len(reading)  # one concrete call per route in the parametrised tests below


@pytest.mark.parametrize("method,path,body", OWNER_ROUTES)
@pytest.mark.parametrize("owner", [None, "", "   "])
def test_a_missing_or_blank_owner_is_refused_on_every_route(method, path, body, owner) -> None:
    headers = {**MAIN, **({} if owner is None else {"X-Saniti-Owner": owner})}
    with client_for() as client:
        response = call(client, method, path, body, headers)
    assert response.status_code == 400, (path, response.text)
    error = response.json()["error"]
    assert error["code"] == "OWNER_REQUIRED" and "X-Saniti-Owner: u_123" in error["message"]
    assert response.json()["detail"]["code"] == "OWNER_REQUIRED"  # the shape current callers read


def test_owner_from_header_never_returns_a_shared_default() -> None:
    for value in (None, "", "  \t"):
        with pytest.raises(ConversationError) as raised:
            owner_from_header(value)
        assert raised.value.code == "OWNER_REQUIRED" and raised.value.http_status == 400
    assert owner_from_header("  u_123 ") == "u_123"  # normalised
    with pytest.raises(ConversationError) as raised:
        owner_from_header("two words")
    assert raised.value.code == "INVALID_OWNER"


def test_the_test_key_names_only_test_owners() -> None:
    allowed = ["golden-multi-angle", "test-a.b:c@d-1", "someone-else"]
    refused = ["u_123", "default", "golden-", "test-", "someone-else-2", "Golden-x", "owner-a", "edge-owner"]
    assert all(TEST_OWNER_RE.fullmatch(o) for o in allowed) and not any(TEST_OWNER_RE.fullmatch(o) for o in refused)
    for value in allowed:
        assert owner_from_header(value, test_key=True) == value
    for value in refused:
        with pytest.raises(ConversationError) as raised:
            owner_from_header(value, test_key=True)
        assert raised.value.code == "OWNER_NOT_ALLOWED" and raised.value.http_status == 403
        assert owner_from_header(value) == value  # the main key keeps every owner


@pytest.mark.parametrize("method,path,body", OWNER_ROUTES)
def test_the_test_key_naming_a_user_owner_is_refused_on_every_route(method, path, body) -> None:
    with client_for() as client:
        response = call(client, method, path, body, {**TESTER, "X-Saniti-Owner": "u_7f3a"})
    assert response.status_code == 403, (path, response.text)
    error = response.json()["error"]
    assert error["code"] == "OWNER_NOT_ALLOWED" and "golden-" in error["message"] and "u_123" in error["message"]


def test_the_test_key_runs_for_a_test_owner_and_the_main_key_for_any_owner() -> None:
    with client_for() as client:
        tester = client.post("/v1/agent/run", headers={**TESTER, "X-Saniti-Owner": "golden-suite"},
                             json={**RUN_BODY, "request_id": "own_t"})
        main = client.post("/v1/agent/run", headers={**MAIN, "X-Saniti-Owner": "u_7f3a"},
                           json={**RUN_BODY, "request_id": "own_m"})
        # the test key reads the progress of its own test owner, not of the user's run
        own = client.get("/v1/agent/requests/own_t/progress", headers={**TESTER, "X-Saniti-Owner": "golden-suite"})
        user = client.get("/v1/agent/requests/own_m/progress", headers={**TESTER, "X-Saniti-Owner": "u_7f3a"})
    assert tester.status_code == 200 and main.status_code == 200
    assert own.status_code == 200 and user.status_code == 403


def test_without_the_test_key_configured_it_does_not_authenticate() -> None:
    with TestClient(create_app(make_settings(), orchestrator=Answers())) as client:
        response = client.post("/v1/agent/run", headers={**TESTER, "X-Saniti-Owner": "golden-suite"}, json=RUN_BODY)
        wrong = client.post("/v1/agent/run", headers={"Authorization": "Bearer " + TEST_KEY[:-1] + "x",
                                                      "X-Saniti-Owner": "golden-suite"}, json=RUN_BODY)
    assert response.status_code == 401 and wrong.status_code == 401


def test_the_test_key_is_never_shown_in_the_settings_repr() -> None:
    settings = make_settings(MARKET_AI_ORC_TEST_KEY=TEST_KEY)
    assert settings.internal_test_api_key == TEST_KEY and TEST_KEY not in repr(settings)
    assert make_settings().internal_test_api_key is None


def test_a_client_history_run_registers_its_owner_for_progress_and_stop() -> None:
    """A CLIENT-history run (no conversation store) used to register no owner, so every caller read and stopped it;
    now only its own owner does, and a request without the header no longer sees it either."""
    seen: dict = {}

    class Peeks:
        def run(self, request, **_):
            with progress.step("Bekerja"):
                path = f"/v1/agent/requests/{request.request_id}/progress"
                seen["owner"] = client.get(path, headers={**MAIN, "X-Saniti-Owner": "owner-a"}).status_code
                seen["other"] = client.get(path, headers={**MAIN, "X-Saniti-Owner": "owner-b"}).status_code
                seen["none"] = client.get(path, headers=MAIN).status_code
                seen["stop_other"] = client.post(f"/v1/agent/run/{request.request_id}/stop",
                                                 headers={**MAIN, "X-Saniti-Owner": "owner-b"}).status_code
                seen["stop_none"] = client.post(f"/v1/agent/run/{request.request_id}/stop", headers=MAIN).status_code
                seen["stopped"] = stop.requested()
            return Answers().run(request)

    client = TestClient(create_app(make_settings(), orchestrator=Peeks()))
    response = client.post("/v1/agent/run", headers={**MAIN, "X-Saniti-Owner": "owner-a"},
                           json={**RUN_BODY, "request_id": "own_c"})
    assert response.status_code == 200
    assert seen == {"owner": 200, "other": 404, "none": 400, "stop_other": 404, "stop_none": 400, "stopped": False}


def test_a_registry_entry_without_an_owner_never_matches() -> None:
    with progress.tracking("own_none", None), stop.running("own_none", None) as flag:
        assert progress.snapshot("own_none", None) is None and progress.snapshot("own_none", "owner-a") is None
        assert stop.stop("own_none", None) == "NOT_RUNNING" and stop.stop("own_none", "owner-a") == "NOT_RUNNING"
        assert not flag.is_set()
    with stop.running("own_a", "owner-a") as flag:
        assert stop.stop("own_a", None) == "NOT_RUNNING" and not flag.is_set()
