"""C1 adversarial security check of EXEC-MU-ACCOUNTS Phase 0 (M474, M475): failing tests for the findings (no fix
here). Contract: verification/edge_multiuser/access_tiers/CONTRACT.md section 7 "Orc"."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import progress, stop
from app.main import create_app
from conftest import BASE_ENV, make_settings
from test_owner_header import Answers

MAIN_KEY = BASE_ENV["MARKET_AI_ORC_API_KEY"]


def test_c1_a_test_key_equal_to_the_main_key_is_refused_at_start() -> None:
    """authorize() (main.py) marks a caller as the test runner only when the main key does NOT match
    (test_key and not main_key). With MARKET_AI_ORC_TEST_KEY set to the same value as MARKET_AI_ORC_API_KEY (a copy
    of the reference variable by mistake), orc-test-runner holds the full key again and may name any user's owner:
    M475 is silently undone. The configuration must refuse it."""
    with pytest.raises(Exception):
        make_settings(MARKET_AI_ORC_TEST_KEY=MAIN_KEY)


def test_c1_a_short_test_key_is_refused_at_start() -> None:
    """Every other bearer of this service is held to at least 32 characters (config.py SQL_GOVERNOR_API_KEY,
    PY_SANDBOX_API_KEY); MARKET_AI_ORC_TEST_KEY has no length rule, so a guessable key opens every test owner."""
    with pytest.raises(Exception):
        make_settings(MARKET_AI_ORC_TEST_KEY="abc")


def test_c1_equal_keys_let_the_test_runner_name_a_user() -> None:
    """The consequence of the first finding at the route: the 'test' key names u_123 and is not refused."""
    try:
        settings = make_settings(MARKET_AI_ORC_TEST_KEY=MAIN_KEY)
    except Exception:
        return                                                   # fixed by refusing the configuration
    with TestClient(create_app(settings, orchestrator=Answers())) as c:
        r = c.get("/v1/agent/requests/own_1/progress",
                  headers={"Authorization": f"Bearer {MAIN_KEY}", "X-Saniti-Owner": "u_123"})
        assert r.status_code == 403


def test_c1_another_owner_reusing_a_request_id_cannot_unregister_a_running_run() -> None:
    """The stop and progress registries are keyed by request_id alone (stop.py _running, progress.py _runs). A second
    owner (for example the test key's golden-* owner) that sends the request_id of a running run of owner A replaces
    A's entry, and on its own exit removes it: A's stop button then answers NOT_RUNNING while A's run keeps spending,
    and A's progress reads 404. Owner checks must not be defeated by a key collision: key the registries by
    (owner, request_id) or refuse a request_id already registered to another owner."""
    with stop.running("c1_rid", "u_a"):
        with stop.running("c1_rid", "golden-x"):
            pass
        assert stop.stop("c1_rid", "u_a") == "STOPPING"


def test_c1_another_owner_reusing_a_request_id_cannot_hide_a_runs_progress() -> None:
    with progress.tracking("c1_rid2", "u_a"):
        with progress.tracking("c1_rid2", "golden-x"):
            assert progress.snapshot("c1_rid2", "u_a") is not None
