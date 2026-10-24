"""EXEC-ASK-BRANCH (user 2026-10-24: "Ok untuk Q1 dan Q2"): a conversation continued in a new one from one of its
answers (EDGE Branch, and the side chat "Ask about this answer"). The new conversation's history is the turns up to that
answer, its data record the one that answer had, and it reads the results made up to that answer and none made after;
nothing is copied, writes stay its own, and the conversations it continues are kept as long as it is.

Against a disposable PostgreSQL database (ORC_TEST_POSTGRES_URL), like test_conversations.py."""
from __future__ import annotations

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.conversations import ConversationError
from app.result_store import ResultStore
from app.run_memory import MemoryStore
from test_conversations import ADMIN_URL, AUTH, Api, answer, databases, server, store_for  # noqa: F401
from test_result_store import entry, out

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
RECORD = {"version": 1, "outputs": [{"ref": "out.o1", "output_id": out(1)}]}


def parent_with_three_turns(admin: str, login: str, p: str) -> tuple[Api, str]:
    """A conversation of three answered turns (request ids <p>-0 .. <p>-2); the answer of turn 1 had a data record."""
    api = Api(store_for(login), [answer("Satu."), answer("Dua."), answer("Tiga."), answer("Cabang."),
                                 answer("Cabang dua.")])
    conversation = api.post(server(f"{p}-0", "Pertanyaan satu")).json()["conversation"]["conversation_id"]
    api.post(server(f"{p}-1", "Pertanyaan dua", conversation))
    api.post(server(f"{p}-2", "Pertanyaan tiga", conversation))
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('''UPDATE public."AI_conversation_turn" SET response = response || %s
                              WHERE request_id = %s''', (Jsonb({"data_record": RECORD}), f"{p}-1"))
    return api, conversation


def branch(api: Api, conversation: str, turn: int, owner: str | None = None):
    headers = {**AUTH, **({"X-Saniti-Owner": owner} if owner else {})}
    return api.client.post(f"/v1/conversations/{conversation}/branch", json={"through_turn": turn}, headers=headers)


def test_a_branch_continues_from_the_chosen_answer_and_never_sees_what_came_after(databases) -> None:
    admin, login = databases
    api, parent = parent_with_three_turns(admin, login, "b1")
    made = branch(api, parent, 1)
    assert made.status_code == 200, made.text
    child = made.json()["conversation_id"]
    assert made.json()["lineage"] == [{"conversation_id": parent, "through_turn": 1}]
    with psycopg.connect(admin) as connection:  # the data record that answer had
        state = connection.execute('SELECT state FROM public."AI_conversation" WHERE conversation_id = %s',
                                   (child,)).fetchone()[0]
    assert state == {"data_record": RECORD}
    api.post(server("b1-c0", "Lanjut dari jawaban dua", child))
    history = [(m.role, m.content) for m in api.seen[-1].history]
    assert history == [("user", "Pertanyaan satu"), ("assistant", "Satu."), ("user", "Pertanyaan dua"),
                       ("assistant", "Dua.")]  # turn 2 of the parent came after the branch point
    page = api.client.get(f"/v1/conversations/{child}/messages", headers=AUTH).json()
    assert [m["request_id"] for m in page["messages"]] == ["b1-c0"] and page["lineage"][0]["through_turn"] == 1
    shown = api.client.get(f"/v1/conversations/{parent}/messages?through=1", headers=AUTH).json()
    assert [m["request_id"] for m in shown["messages"]] == ["b1-0", "b1-1"]
    # the parent is untouched
    assert [m["request_id"] for m in api.client.get(f"/v1/conversations/{parent}/messages", headers=AUTH)
            .json()["messages"]] == ["b1-0", "b1-1", "b1-2"]


def test_a_branch_reads_the_results_made_up_to_its_answer_and_writes_its_own(databases) -> None:
    admin, login = databases
    api, parent = parent_with_three_turns(admin, login, "b2")
    child = branch(api, parent, 1).json()["conversation_id"]
    store = ResultStore(login)
    store.save_output(parent, "b2-0", entry(out(1)), b"before")
    store.save_output(parent, "b2-2", entry(out(2)), b"after")
    memory = MemoryStore(login)
    for run_id in ("b2-0", "b2-2"):
        memory.save(parent, run_id, run_id, status="COMPLETED", response_type="ANSWER", error_code=None,
                    memo=f"## {run_id}", content={}, sources={}, note=None, reasoning=None)
    with psycopg.connect(admin, autocommit=True) as connection:  # each result made during its own turn
        for table, key, value, request in (("AI_conversation_output", "output_id", out(1), "b2-0"),
                                           ("AI_conversation_output", "output_id", out(2), "b2-2"),
                                           ("AI_conversation_run_memory", "run_id", "b2-0", "b2-0"),
                                           ("AI_conversation_run_memory", "run_id", "b2-2", "b2-2")):
            connection.execute(
                f'''UPDATE public."{table}" SET created_at = (SELECT created_at FROM public."AI_conversation_turn"
                    WHERE request_id = %s) WHERE {key} = %s''', (request, value))
    assert store.output(child, out(1)) is not None and store.content(child, store.output(child, out(1))) == b"before"
    assert store.output(child, out(2)) is None  # made after the branch point
    assert [t.output_id for t in store.stored_tables(child)] == [out(1)]
    assert [m["run_id"] for m in memory.load(child)] == ["b2-0"]
    assert memory.read(child, "b2-2") is None and memory.read(child, "b2-1")["content"]["message"] == "Pertanyaan dua"
    store.save_output(child, "b2-c0", entry(out(3)), b"mine")
    assert store.output(parent, out(3)) is None and store.output(child, out(3)) is not None  # writes stay its own


def test_a_branch_of_a_branch_reads_the_whole_line_and_keeps_it(databases) -> None:
    admin, login = databases
    api, parent = parent_with_three_turns(admin, login, "b3")
    child = branch(api, parent, 0).json()["conversation_id"]
    api.post(server("b3-c0", "Di cabang", child))
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('''UPDATE public."AI_conversation" SET expires_at = now() + interval '1 hour'
                              WHERE conversation_id = %s''', (parent,))
    grandchild = branch(api, child, 0).json()
    assert "lineage" in grandchild, grandchild
    assert [a["conversation_id"] for a in grandchild["lineage"]] == [parent, child]
    api.post(server("b3-g0", "Di cabang dari cabang", grandchild["conversation_id"]))
    assert [m.content for m in api.seen[-1].history] == ["Pertanyaan satu", "Satu.", "Di cabang", "Cabang."]
    with psycopg.connect(admin) as connection:
        days = connection.execute('''SELECT extract(day FROM expires_at - now()) FROM public."AI_conversation"
                                     WHERE conversation_id = %s''', (parent,)).fetchone()[0]
    assert days >= 29  # kept as long as the conversations that continue it


def test_only_a_finished_answer_of_the_owners_conversation_can_be_continued(databases) -> None:
    admin, login = databases
    api, parent = parent_with_three_turns(admin, login, "b4")
    assert branch(api, parent, 1, owner="someone-else").json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"
    assert branch(api, parent, 7).json()["detail"]["code"] == "TURN_NOT_BRANCHABLE"
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('''UPDATE public."AI_conversation_turn" SET status = 'FAILED' WHERE request_id = 'b4-2' ''')
    refused = branch(api, parent, 2)
    assert refused.status_code == 409 and "finished" in refused.json()["detail"]["message"]
    with pytest.raises(ConversationError):
        store_for(login).branch("default", "conv_nothing", 0)
