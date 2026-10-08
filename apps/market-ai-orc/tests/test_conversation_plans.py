"""Research Plan continuation kept by the server (history_mode SERVER; implementation plan 2026-09-27, phase H2),
against a disposable PostgreSQL database with the conversation store (see test_conversations.py)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from conftest import BASE_ENV, ScriptedClient, final_response, make_settings, tool_call_response
from test_conversations import ADMIN_URL, databases, store_for  # noqa: F401 - the module-scoped fixture
from test_research_plan import ON, Clock, Sandbox, answer, classifier, clarification, plan_response, registry
from test_research_plan import research_arguments

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}
QUESTION = "Apakah RSI di bawah 30 dan hammer menghasilkan return lebih tinggi?"


class Api:
    """The real app and orchestrator with Research Plan confirmation on; the model is scripted across turns."""

    def __init__(self, url: str, script: list, clock: Clock | None = None) -> None:
        self.sandbox = Sandbox()
        self.scripted = ScriptedClient(script)
        settings = make_settings(**ON)
        self.agent = AgentOrchestrator(settings, self.scripted, registry(self.sandbox),
                                       wall_clock=clock or Clock(datetime.now(timezone.utc)))
        self.seen: list[AgentRunRequest] = []
        run = self.agent.run
        self.agent.run = lambda request, **_: (self.seen.append(request), run(request))[1]
        self.client = TestClient(create_app(settings, orchestrator=self.agent, conversations=store_for(url)))

    def post(self, request_id: str, message: str, conversation_id: str | None = None, **extra):
        body = {"request_id": request_id, "message": message, "conversation_id": conversation_id,
                "history_mode": "SERVER", **extra}
        return self.client.post("/v1/agent/run", json=body, headers=AUTH)


def plan_turn(api: Api, request_id: str = "h2-1") -> dict:
    body = api.post(request_id, QUESTION).json()
    assert body["status"] == "AWAITING_CONFIRMATION", body
    return body


def submit() -> dict:
    return tool_call_response("submit_data_need_spec", json.dumps(research_arguments()), call_id="s1")


def turns(url: str, conversation_id: str) -> int:
    with psycopg.connect(url) as connection:
        return connection.execute('SELECT count(*) FROM public."AI_conversation_turn" WHERE conversation_id = %s',
                                  (conversation_id,)).fetchone()[0]


def test_a_free_text_approval_runs_the_stored_plan_and_uses_it_once(databases) -> None:
    admin_url, url = databases
    api = Api(url, [final_response(plan_response()), classifier("APPROVE"), submit(),
                    final_response(answer("Eksperimen disetujui dan dijalankan.", "LIMITATION"))])
    first = plan_turn(api)
    conversation_id = first["conversation"]["conversation_id"]
    plan_id = first["continuation"]["plan_id"]
    assert first["conversation"]["research_plan"] == {"plan_id": plan_id, "status": "PENDING",
                                                      "expires_at": first["continuation"]["expires_at"]}
    assert first["continuation"]["conversation_id"] == conversation_id  # the token is bound to the conversation
    second = api.post("h2-2", "Setuju, lanjutkan.", conversation_id).json()
    # the caller sent no plan or token: the server built the continuation from the stored plan
    sent = api.seen[-1].continuation
    assert sent is not None and sent.plan_id == plan_id and sent.token == first["continuation"]["token"]
    assert sent.action is None  # the existing classifier read the free-text reply
    assert second["execution"]["research_plan"]["turn"] == "EXECUTE_APPROVED"
    assert second["execution"]["research_plan"]["approved_plan_id"] == plan_id
    assert [c["path"] for c in api.sandbox.calls] == ["/v1/data-needs"]
    # EXEC-W A3 (M121 c, user decision 2026-10-08): the research did not complete, so the plan stays approvable
    assert second["execution"]["research_plan"]["research_completed"] is False
    assert second["conversation"]["research_plan"]["status"] == "PENDING"
    # the same approval request again is answered from the stored response, without a run
    replay = api.post("h2-2", "Setuju, lanjutkan.", conversation_id).json()
    assert replay["conversation"]["replayed"] is True and len(api.seen) == 2
    # "lanjutkan" approves it again: the research runs again
    api.scripted.responses.extend([submit(), final_response(answer("Dijalankan lagi.", "LIMITATION"))])
    third = api.post("h2-3", "Lanjutkan.", conversation_id, plan_reply={"plan_id": plan_id, "action": "APPROVE"})
    assert third.status_code == 200 and third.json()["execution"]["research_plan"]["turn"] == "EXECUTE_APPROVED"
    assert len(api.sandbox.calls) == 2
    # a completed research consumes the approval: a later approval is refused and leaves no turn behind
    import psycopg
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("""UPDATE public."AI_conversation" SET state = jsonb_set(state, '{research_plan,status}',
                              '"EXECUTED"') WHERE conversation_id = %s""", (conversation_id,))
    before = turns(admin_url, conversation_id)
    fourth = api.post("h2-4", "Setuju lagi.", conversation_id,
                      plan_reply={"plan_id": plan_id, "action": "APPROVE"})
    assert fourth.status_code == 409 and fourth.json()["detail"]["code"] == "RESEARCH_PLAN_NOT_PENDING"
    assert turns(admin_url, conversation_id) == before and len(api.sandbox.calls) == 2
    # a later free-text message runs without the executed plan
    api.scripted.responses.append(final_response(answer("Halo.")))
    api.post("h2-5", "Terima kasih.", conversation_id)
    assert api.seen[-1].continuation is None
    messages = api.client.get(f"/v1/conversations/{conversation_id}/messages", headers=AUTH).json()
    assert messages["research_plan"]["status"] == "EXECUTED"


def test_approve_but_change_the_period_is_a_revision_not_an_approval_of_the_old_plan(databases) -> None:
    _, url = databases
    revised = plan_response(time_scope="Lima tahun terakhir")
    api = Api(url, [final_response(plan_response()), classifier("REVISE", "periode lima tahun"),
                    final_response(revised), submit(), final_response(answer("Dijalankan.", "LIMITATION"))])
    first = plan_turn(api, "h2-r1")
    conversation_id, old_id = first["conversation"]["conversation_id"], first["continuation"]["plan_id"]
    second = api.post("h2-r2", "Setuju, tetapi ubah periodenya jadi lima tahun.", conversation_id).json()
    assert second["execution"]["research_plan"]["turn"] == "REVISE" and api.sandbox.calls == []
    new_id = second["continuation"]["plan_id"]
    assert new_id != old_id and second["conversation"]["research_plan"]["status"] == "PENDING"
    # the old plan is superseded: refused even though its token has not expired
    stale = api.post("h2-r3", "Setuju.", conversation_id, plan_reply={"plan_id": old_id, "action": "APPROVE"})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "RESEARCH_PLAN_STALE"
    assert new_id in stale.json()["detail"]["message"]
    approved = api.post("h2-r4", "Setuju.", conversation_id, plan_reply={"plan_id": new_id, "action": "APPROVE"})
    body = approved.json()
    assert body["execution"]["research_plan"]["action_source"] == "EXPLICIT"
    assert body["execution"]["research_plan"]["approved_plan_id"] == new_id and len(api.sandbox.calls) == 1
    assert api.seen[-1].continuation.plan.time_scope == "Lima tahun terakhir"


def test_cancel_and_an_unrelated_reply(databases) -> None:
    _, url = databases
    api = Api(url, [final_response(plan_response()), classifier("UNRELATED"),
                    final_response(clarification("Setujui, ubah, atau batalkan rencana riset tadi?")),
                    final_response(answer("Rencana dibatalkan.")), final_response(answer("Halo."))])
    first = plan_turn(api, "h2-c1")
    conversation_id, plan_id = first["conversation"]["conversation_id"], first["continuation"]["plan_id"]
    unrelated = api.post("h2-c2", "Berapa harga BBCA?", conversation_id).json()
    # the same continuation comes back unchanged (same token and expiry), and the plan stays pending
    assert unrelated["continuation"]["token"] == first["continuation"]["token"]
    assert unrelated["conversation"]["research_plan"]["status"] == "PENDING"
    cancelled = api.post("h2-c3", "Batal.", conversation_id, plan_reply={"plan_id": plan_id, "action": "CANCEL"})
    assert cancelled.json()["conversation"]["research_plan"]["status"] == "CANCELLED"
    api.post("h2-c4", "Halo.", conversation_id)
    assert api.seen[-1].continuation is None and api.sandbox.calls == []


def test_an_expired_plan_goes_with_a_reply_and_a_new_question_is_answered_as_one(databases) -> None:
    """R-STORE C2e (resume): a free-text reply after the plan expired carries it, so an approval the next day presents
    it again (REPLAN) instead of reaching the model with no plan; an unrelated question is answered as one."""
    _, url = databases
    past = Clock(datetime.now(timezone.utc) - timedelta(hours=3))  # the plan's hour-long token expired
    api = Api(url, [final_response(plan_response()), classifier("UNRELATED"), final_response(answer("Halo.")),
                    classifier("APPROVE"),
                    final_response(plan_response(answer="Rencana ini dibuat sebelumnya dan kedaluwarsa; setujui lagi?")),
                    final_response(plan_response(answer="Rencana riset yang sama, perlu persetujuan baru."))],
              clock=past)
    first = plan_turn(api, "h2-e1")
    conversation_id, plan_id = first["conversation"]["conversation_id"], first["continuation"]["plan_id"]
    assert first["conversation"]["research_plan"]["status"] == "EXPIRED"
    past.moment = datetime.now(timezone.utc)  # the signer and the run clock move to the present
    hello = api.post("h2-e2", "Halo.", conversation_id).json()
    assert api.seen[-1].continuation is not None  # the expired plan went with the reply ...
    assert hello["execution"]["research_plan"]["turn"] == "PROPOSE"  # ... and a new question is answered as one
    again = api.post("h2-e2b", "jalankan", conversation_id).json()
    assert again["execution"]["research_plan"]["turn"] == "REPLAN"
    assert again["execution"]["research_plan"]["verification"] == "RESEARCH_PLAN_TOKEN_EXPIRED"
    plan_id = again["continuation"]["plan_id"]
    assert again["conversation"]["research_plan"]["status"] == "PENDING" and api.sandbox.calls == []


def test_plan_reply_and_continuation_belong_to_one_history_mode_each(databases) -> None:
    admin_url, url = databases
    api = Api(url, [])
    plan_id = "rp_" + "a" * 24
    client_mode = api.client.post("/v1/agent/run", headers=AUTH, json={
        "request_id": "h2-m1", "message": "Setuju.", "plan_reply": {"plan_id": plan_id, "action": "APPROVE"}})
    assert client_mode.status_code == 400 and client_mode.json()["detail"]["code"] == "PLAN_REPLY_NEEDS_SERVER_MODE"
    token = {"kind": "RESEARCH_PLAN", "plan_id": plan_id, "origin_request_id": "x", "token": "rpc1.x.y",
             "plan": plan_response()["research_plan"], "action": "APPROVE"}
    conflict = api.post("h2-m2", "Setuju.", continuation=token)
    assert conflict.status_code == 400 and conflict.json()["detail"]["code"] == "CONTINUATION_SOURCE_CONFLICT"
    # a plan_reply that opens a new conversation creates nothing
    with psycopg.connect(admin_url) as connection:
        before = connection.execute('SELECT count(*) FROM public."AI_conversation"').fetchone()[0]
    missing = api.post("h2-m3", "Setuju.", plan_reply={"plan_id": plan_id, "action": "APPROVE"})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "RESEARCH_PLAN_NOT_FOUND"
    with psycopg.connect(admin_url) as connection:
        assert connection.execute('SELECT count(*) FROM public."AI_conversation"').fetchone()[0] == before
    bad = api.post("h2-m4", "Setuju.", plan_reply={"plan_id": plan_id, "action": "APPROVE",
                                                   "revision_instruction": "x"})
    assert bad.status_code == 422 and api.seen == []
