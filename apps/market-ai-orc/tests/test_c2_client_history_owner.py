"""C2 isolation check (EXEC-MU-ACCOUNTS Phase 0, CONTRACT.md section 7, M475): a CLIENT-history run names its
conversation_id in the body, and the orchestrator then opens that conversation's kept results, run memory and exports
(result_store / run_memory are keyed by conversation_id only; orchestrator.py RunResults, _restorer, _store_results).
Nothing checks that the request's owner holds that conversation, so a holder of MARKET_AI_ORC_TEST_KEY, limited to test
owners, reaches a user's (u_...) conversation by naming its id with history_mode CLIENT. The run must be refused, or
reach the orchestrator without that conversation."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings
from test_owner_header import TESTER, TEST_KEY

USER_CONVERSATION = "conv_" + "a" * 32   # a conversation of owner u_7f3a (the test key may not name that owner)


def test_a_client_history_run_never_opens_a_conversation_its_owner_does_not_hold() -> None:
    seen: dict = {}

    class Records:
        class registry:  # noqa: N801 - what the app's shutdown closes
            @staticmethod
            def close() -> None:
                pass

        def run(self, request, **_):
            seen["conversation_id"] = request.conversation_id
            raise RuntimeError("stop here: only the conversation the run would open matters")

    app = create_app(make_settings(MARKET_AI_ORC_TEST_KEY=TEST_KEY), orchestrator=Records())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/v1/agent/run", headers={**TESTER, "X-Saniti-Owner": "golden-suite"},
                               json={"request_id": "c2_client_1", "message": "Harga BBCA?", "history_mode": "CLIENT",
                                     "conversation_id": USER_CONVERSATION})
    assert seen.get("conversation_id") != USER_CONVERSATION, (
        "the test key's golden-suite run reached a user's conversation through history_mode CLIENT "
        f"(status {response.status_code})")
