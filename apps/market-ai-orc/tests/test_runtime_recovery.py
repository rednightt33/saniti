from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, progress
from app.runtime_recovery import RuntimeRecovery
from app.tools.analysis import SandboxClient
from app.tools.session import open_with_wait
from conftest import ANSWER, BASE_ENV, ScriptedClient, final_response, make_settings


@pytest.mark.parametrize("metadata", [{}, [], {"versions": {}},
    {"versions": {}, "isolation": []}, {"versions": {}, "isolation": {"isolation_enforced": False}}])
def test_invalid_or_unisolated_runtime_never_publishes_an_agent(metadata):
    sandbox = SimpleNamespace(ready=lambda: True, runtime=lambda: metadata)
    built = []
    recovery = RuntimeRecovery(lambda _: built.append(True), sandbox)
    assert recovery.get() is None and not built


def test_real_client_uses_one_successful_snapshot_for_all_capability_reads():
    reads = []
    def handler(request):
        reads.append(request.url.path)
        if request.url.path == "/ready":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json={"versions": {"python": "3.12"},
                                        "isolation": {"isolation_enforced": True}})
    client = SandboxClient("http://sandbox.test", "test-key", 5, 0, transport=httpx.MockTransport(handler))
    try:
        def build(sandbox):
            assert sandbox.runtime() == sandbox.runtime()
            return object()
        recovery = RuntimeRecovery(build, client)
        assert recovery.get() is recovery.get()
        assert reads == ["/ready", "/v1/runtime"]
    finally:
        client.close()


def test_missing_dependency_recovers_once_without_an_idle_thread():
    state = {"ready": False, "time": 0, "reads": 0, "builds": 0}
    def metadata():
        state["reads"] += 1
        return {"versions": {"python": "3.12"}, "isolation": {"isolation_enforced": True}}
    sandbox = SimpleNamespace(ready=lambda: state["ready"], runtime=metadata)
    def build(client):
        state["builds"] += 1
        assert client.runtime_snapshot == {"versions": {"python": "3.12"}, "isolation": {"isolation_enforced": True}}
        return object()
    recovery = RuntimeRecovery(build, sandbox, clock=lambda: state["time"])
    assert recovery.get() is None
    state["ready"] = True
    assert recovery.get() is None  # cooldown, not a busy loop
    assert state["reads"] == state["builds"] == 0
    state["time"] = 5
    ready = recovery.get()
    state["ready"] = False
    assert recovery.get() is ready  # never withdraw a registered runtime
    assert state["reads"] == state["builds"] == 1


def test_unreadable_runtime_is_not_cached_as_a_permanent_capability():
    sandbox = SimpleNamespace(ready=lambda: True, runtime=lambda: {})
    built = []
    recovery = RuntimeRecovery(lambda client: built.append(client) or object(), sandbox, retry_seconds=0)
    assert recovery.get() is None and not built
    assert not hasattr(sandbox, "runtime_snapshot")
    sandbox.runtime = lambda: {"versions": {"python": "3.12"}, "isolation": {"isolation_enforced": True}}
    assert recovery.get() is not None and len(built) == 1


def test_concurrent_requests_cannot_publish_a_partial_runtime_or_build_twice():
    started, release = Event(), Event()
    def build(_):
        started.set()
        assert release.wait(5)
        return object()
    recovery = RuntimeRecovery(build, None)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(recovery.get)
        assert started.wait(5)
        assert recovery.get() is None
        release.set()
        result = first.result(5)
        assert recovery.get() is result


def test_http_stays_up_and_request_recovers_full_registry_without_a_restart(monkeypatch):
    state = {"ready": False, "reads": 0}
    monkeypatch.setattr(SandboxClient, "ready", lambda _: state["ready"])
    def runtime(_):
        state["reads"] += 1
        return {"versions": {"python": "3.12"}, "isolation": {"isolation_enforced": True}}
    monkeypatch.setattr(SandboxClient, "runtime", runtime)
    monkeypatch.setattr(main, "RuntimeRecovery", lambda *a, **kw: RuntimeRecovery(*a, **kw, retry_seconds=0))
    scripted = ScriptedClient([final_response(ANSWER)])
    scripted.close = lambda: None
    monkeypatch.setattr(main, "OpenRouterClient", lambda *a, **kw: scripted)
    monkeypatch.setattr(main.ModelPrices, "start", lambda _: None)
    monkeypatch.setattr(main.CreditMonitor, "start", lambda _: None)
    monkeypatch.setattr(main.CreditMonitor, "stop", lambda _: None)
    app = main.create_app(make_settings(PY_SANDBOX_URL="http://sandbox.test", PY_SANDBOX_API_KEY="s" * 32))
    auth = {"Authorization": "Bearer " + BASE_ENV["MARKET_AI_ORC_API_KEY"]}
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/v1/agent/readiness").status_code == 401
        assert client.get("/v1/agent/readiness", headers=auth).json() == {"status": "initializing"}
        body = {"request_id": "recovery-test", "message": "Hello"}
        assert client.post("/v1/agent/run", json=body, headers=auth).status_code == 503
        assert not scripted.payloads
        state["ready"] = True
        assert client.get("/v1/agent/readiness", headers=auth).json() == {"status": "ready"}
        ready = app.state.orchestrator
        assert "run_python_analysis" in ready.registry.names()
        assert client.post("/v1/agent/run", json=body, headers=auth).status_code == 200
        assert app.state.orchestrator is ready
        assert state["reads"] == 1


def test_session_progress_wraps_the_real_open_and_is_owner_scoped():
    class Client:
        open_wait_seconds = 0
        _json = staticmethod(SandboxClient._json)
        def _call(self, method, path, **kwargs):
            assert method == "POST" and path == "/v1/sessions"
            live = progress.snapshot("session-progress", "owner")
            assert live["steps"][-1]["label"] == "Initiating sandbox session."
            assert live["steps"][-1]["state"] == "running"
            import httpx
            return httpx.Response(200, json={"status": "READY", "session_id": "ses_test"})
    with progress.tracking("session-progress", "owner"):
        assert open_with_wait(Client(), {"request_id": "session-progress"}, 5)["session_id"] == "ses_test"
        assert progress.snapshot("session-progress", "other") is None
    assert progress.snapshot("session-progress", "owner")["steps"][-1]["state"] == "done"
