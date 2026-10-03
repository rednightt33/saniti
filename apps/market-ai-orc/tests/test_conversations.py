"""Server-side conversation history (AI_ENABLE_CONVERSATION_STORE, implementation plan 2026-09-27, phase H1), against
a disposable PostgreSQL database with migration 20260927_002 applied and the market_ai_conversation login provisioned
by scripts/provision_market_ai_conversation_login.py.

Set ORC_TEST_POSTGRES_URL to an admin URL of a disposable server (see test_catalog_postgres.py)."""
from __future__ import annotations

import importlib.util
import os
import secrets
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.conversations import ConversationError, ConversationStore, fingerprint
from app.main import create_app
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from conftest import BASE_ENV, ScriptedClient, final_response, make_settings

ADMIN_URL = os.environ.get("ORC_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = [REPO / "database/migrations/20260927_002_create_ai_conversation_store.sql",
              REPO / "database/migrations/20261003_006_conversation_results.sql"]
AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}

# The columns of the legacy documentation tables the migration writes to (DATABASE_SCHEMA.md).
CATALOG_STUBS = '''
CREATE TABLE public."Table_Catalog" (table_schema text, table_name text, category text, definition text, grain text,
    primary_key_columns text[], source_system text, source_tables text[], source_code_paths text[], update_rule text,
    related_functions text[], documentation_status text, readiness_mode text, readiness_date_column text,
    observation_date_column text, data_available_at_column text, availability_rule text, point_in_time_status text,
    historical_metadata_method text);
CREATE TABLE public."Column_Catalog" (table_schema text, table_name text, column_name text, ordinal_position integer,
    data_type text, is_nullable boolean, default_expression text, is_primary_key boolean, definition text,
    source_column_or_expression text, unit text, null_rule text, source_code_paths text[], documentation_status text);
CREATE TABLE public."Market_Stub" (id integer);
'''


def _with(url: str, database: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc.split("@")[-1]
    if user:
        netloc = f"{user}:{password}@{netloc}" if password else f"{user}@{netloc}"
    elif "@" in parts.netloc:
        netloc = parts.netloc
    return urlunsplit((parts.scheme, netloc, f"/{database}", parts.query, parts.fragment))


@pytest.fixture(scope="module")
def databases() -> Iterator[tuple[str, str]]:
    """(admin URL, conversation-login URL) of a fresh database with the migration applied."""
    name = f"orc_conversations_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    admin_url = _with(ADMIN_URL, name)
    try:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(CATALOG_STUBS)
            for migration in MIGRATIONS:
                connection.execute(migration.read_text())
        password = secrets.token_hex(24)
        spec = importlib.util.spec_from_file_location("provision", REPO / "scripts/provision_market_ai_conversation_login.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        previous = {key: os.environ.get(key) for key in ("DATABASE_URL", "MARKET_AI_CONVERSATION_DB_PASSWORD")}
        os.environ.update(DATABASE_URL=admin_url, MARKET_AI_CONVERSATION_DB_PASSWORD=password)
        try:
            module.main()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        yield admin_url, _with(ADMIN_URL, name, "market_ai_conversation", password)
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def store_for(url: str, lease_seconds: int = 900) -> ConversationStore:
    return ConversationStore(url, retention_days=30, lease_seconds=lease_seconds)


def answer(text: str) -> dict:
    return {"response_type": "ANSWER", "answer": text, "clarification_question": None, "assumptions": [],
            "limitations": []}


class Api:
    def __init__(self, store: ConversationStore | None, finals: list[dict]) -> None:
        self.scripted = ScriptedClient([final_response(item, response_id=f"resp_{i}") for i, item in enumerate(finals)])
        settings = make_settings()
        self.agent = AgentOrchestrator(settings, self.scripted, build_default_registry())
        self.seen: list[AgentRunRequest] = []
        run = self.agent.run
        self.agent.run = lambda request: (self.seen.append(request), run(request))[1]
        self.client = TestClient(create_app(settings, orchestrator=self.agent, conversations=store))

    def post(self, body: dict, owner: str | None = None):
        headers = {**AUTH, **({"X-Saniti-Owner": owner} if owner else {})}
        return self.client.post("/v1/agent/run", json=body, headers=headers)


def server(request_id: str, message: str, conversation_id: str | None = None, **extra) -> dict:
    return {"request_id": request_id, "message": message, "conversation_id": conversation_id,
            "history_mode": "SERVER", **extra}


def test_client_mode_is_unchanged_and_needs_no_store() -> None:
    api = Api(None, [answer("Tanpa riwayat server.")])
    body = api.post({"request_id": "legacy-1", "message": "Halo"}).json()
    assert "conversation" not in body and body["status"] == "COMPLETED"
    refused = api.post(server("s-1", "Halo"))
    assert refused.status_code == 400 and refused.json()["detail"]["code"] == "HISTORY_MODE_UNAVAILABLE"


def test_the_server_keeps_the_history_and_the_caller_sends_only_the_message(databases) -> None:
    _, login = databases
    api = Api(store_for(login), [answer("Pertama dijawab."), answer("Kedua dijawab.")])
    first = api.post(server("h1-a", "Pertanyaan pertama")).json()
    conversation = first["conversation"]
    assert conversation["turn_index"] == 0 and conversation["persistence"] == "SAVED"
    assert conversation["conversation_id"].startswith("conv_") and api.seen[0].history == []
    second = api.post(server("h1-b", "Pertanyaan kedua", conversation["conversation_id"])).json()
    assert second["conversation"]["turn_index"] == 1 and second["response"]["answer"] == "Kedua dijawab."
    assert [(m.role, m.content) for m in api.seen[1].history] == [("user", "Pertanyaan pertama"),
                                                                   ("assistant", "Pertama dijawab.")]
    assert api.seen[1].conversation_id == conversation["conversation_id"]  # a Research Plan binds to it


def test_server_mode_refuses_a_caller_history(databases) -> None:
    _, login = databases
    api = Api(store_for(login), [])
    refused = api.post(server("h2-a", "Halo", history=[{"role": "user", "content": "x"}]))
    assert refused.status_code == 400 and refused.json()["detail"]["code"] == "HISTORY_SOURCE_CONFLICT"
    assert api.scripted.payloads == []


def test_a_retry_returns_the_stored_response_and_a_changed_retry_is_refused(databases) -> None:
    _, login = databases
    api = Api(store_for(login), [answer("Sekali saja.")])
    first = api.post(server("h3-a", "Hitung sekali"))
    again = api.post(server("h3-a", "Hitung sekali"))
    assert again.json()["conversation"]["replayed"] is True and len(api.scripted.payloads) == 1
    assert again.json()["response"] == first.json()["response"]
    changed = api.post(server("h3-a", "Pesan lain"))
    assert changed.status_code == 409 and changed.json()["detail"]["code"] == "REQUEST_ID_CONFLICT"


def test_another_owner_cannot_continue_or_read_a_conversation(databases) -> None:
    _, login = databases
    api = Api(store_for(login), [answer("Milik A.")])
    conversation_id = api.post(server("h4-a", "Milik A"), owner="user-a").json()["conversation"]["conversation_id"]
    stolen = api.post(server("h4-b", "Saya B", conversation_id), owner="user-b")
    assert stolen.status_code == 404 and stolen.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"
    assert api.client.get(f"/v1/conversations/{conversation_id}/messages",
                          headers={**AUTH, "X-Saniti-Owner": "user-b"}).status_code == 404
    assert api.client.get(f"/v1/conversations/{conversation_id}/messages", headers=AUTH).status_code == 404
    own = api.client.get(f"/v1/conversations/{conversation_id}/messages", headers={**AUTH, "X-Saniti-Owner": "user-a"})
    assert own.status_code == 200 and own.json()["messages"][0]["user_message"] == "Milik A"
    bad = api.post(server("h4-c", "x"), owner="user a; drop")
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "INVALID_OWNER"


def test_one_message_runs_at_a_time_and_a_lapsed_lease_is_taken_over_with_fencing(databases) -> None:
    admin, login = databases
    store = store_for(login)
    first_request = AgentRunRequest(request_id="h5-a", message="Lama", history_mode="SERVER")
    first = store.begin("owner-5", first_request, fingerprint(first_request))
    second_request = AgentRunRequest(request_id="h5-b", message="Baru", history_mode="SERVER",
                                     conversation_id=first.conversation_id)
    with pytest.raises(ConversationError) as busy:
        store.begin("owner-5", second_request, fingerprint(second_request))
    assert busy.value.code == "CONVERSATION_BUSY"
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('UPDATE public."AI_conversation" SET lease_expires_at = now() - interval \'1 second\' '
                           'WHERE conversation_id = %s', (first.conversation_id,))
    second = store.begin("owner-5", second_request, fingerprint(second_request))
    assert second.generation == first.generation + 1 and second.turn_index == 1
    api = Api(store, [answer("Hasil lama."), answer("Hasil baru.")])
    assert store.finish(first, "h5-a", api.agent.run(first_request)) is False     # the stale runner is fenced
    assert store.finish(second, "h5-b", api.agent.run(second_request)) is True
    with psycopg.connect(admin) as connection:
        rows = dict(connection.execute('SELECT request_id, status FROM public."AI_conversation_turn" '
                                       "WHERE request_id IN ('h5-a', 'h5-b')").fetchall())
    assert rows == {"h5-a": "INTERRUPTED", "h5-b": "COMPLETED"}


def test_a_retry_of_a_turn_whose_runner_died_ends_it_instead_of_waiting(databases) -> None:
    admin, login = databases
    store = store_for(login)
    request = AgentRunRequest(request_id="h5b-a", message="Mati di tengah", history_mode="SERVER")
    start = store.begin("owner-5b", request, fingerprint(request))
    with pytest.raises(ConversationError) as running:
        store.begin("owner-5b", request, fingerprint(request))
    assert running.value.code == "TURN_IN_PROGRESS"
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('UPDATE public."AI_conversation" SET lease_expires_at = now() - interval \'1 second\' '
                           'WHERE conversation_id = %s', (start.conversation_id,))
    with pytest.raises(ConversationError) as ended:
        store.begin("owner-5b", request, fingerprint(request))
    assert ended.value.code == "TURN_NOT_COMPLETED" and "INTERRUPTED" in ended.value.message
    follow = AgentRunRequest(request_id="h5b-b", message="Lagi", history_mode="SERVER",
                             conversation_id=start.conversation_id)
    assert store.begin("owner-5b", follow, fingerprint(follow)).turn_index == 1  # the lease was released


def test_a_clarification_becomes_history_through_its_question(databases) -> None:
    _, login = databases
    clarify = {"response_type": "CLARIFICATION", "answer": "", "clarification_question": "Periode yang mana?",
               "assumptions": [], "limitations": []}
    api = Api(store_for(login), [clarify, answer("Terima kasih.")])
    conversation_id = api.post(server("h6-a", "Return saham?")).json()["conversation"]["conversation_id"]
    api.post(server("h6-b", "Tahun ini", conversation_id))
    assert [(m.role, m.content) for m in api.seen[1].history] == [("user", "Return saham?"),
                                                                   ("assistant", "Periode yang mana?")]


def test_messages_are_paged_in_turn_order(databases) -> None:
    _, login = databases
    api = Api(store_for(login), [answer(f"Jawaban {word}.") for word in ("satu", "dua", "tiga")])
    conversation_id = api.post(server("h7-a", "Satu")).json()["conversation"]["conversation_id"]
    api.post(server("h7-b", "Dua", conversation_id))
    api.post(server("h7-c", "Tiga", conversation_id))
    page = api.client.get(f"/v1/conversations/{conversation_id}/messages?limit=2", headers=AUTH).json()
    assert [m["user_message"] for m in page["messages"]] == ["Satu", "Dua"] and page["has_more"] is True
    rest = api.client.get(f"/v1/conversations/{conversation_id}/messages?after={page['next_after']}",
                          headers=AUTH).json()
    assert [m["user_message"] for m in rest["messages"]] == ["Tiga"] and rest["has_more"] is False
    assert rest["messages"][0]["response"]["response"]["answer"] == "Jawaban tiga."


def test_upkeep_interrupts_lapsed_turns_and_deletes_expired_conversations(databases) -> None:
    admin, login = databases
    store = store_for(login)
    request = AgentRunRequest(request_id="h8-a", message="Terputus", history_mode="SERVER")
    start = store.begin("owner-8", request, fingerprint(request))
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('UPDATE public."AI_conversation" SET lease_expires_at = now() - interval \'1 second\' '
                           'WHERE conversation_id = %s', (start.conversation_id,))
    assert store.recover() == 1
    with psycopg.connect(admin, autocommit=True) as connection:
        assert connection.execute('SELECT status FROM public."AI_conversation_turn" WHERE request_id = %s',
                                  ("h8-a",)).fetchone()[0] == "INTERRUPTED"
        connection.execute('UPDATE public."AI_conversation" SET created_at = now() - interval \'40 days\', '
                           'expires_at = now() - interval \'1 day\' WHERE conversation_id = %s',
                           (start.conversation_id,))
    assert store.cleanup() >= 1
    with psycopg.connect(admin) as connection:
        assert connection.execute('SELECT count(*) FROM public."AI_conversation_turn" WHERE request_id = %s',
                                  ("h8-a",)).fetchone()[0] == 0
    # nothing of the deleted conversation is left: the same request_id now opens a new conversation
    assert store.begin("owner-8", request, fingerprint(request)).conversation_id != start.conversation_id


def test_the_login_reaches_the_conversation_tables_only(databases) -> None:
    _, login = databases
    with psycopg.connect(login) as connection:
        for table in ("Table_Catalog", "Market_Stub"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(f'SELECT 1 FROM public."{table}"')
            connection.rollback()
        for table in ("AI_conversation", "AI_conversation_turn", "AI_conversation_output", "AI_conversation_execution",
                      "AI_conversation_export"):
            assert connection.execute(f'SELECT count(*) FROM public."{table}"').fetchone()[0] >= 0


def test_an_unavailable_store_refuses_server_mode_only() -> None:
    api = Api(store_for("postgresql://nobody@127.0.0.1:1/none"), [answer("Klien tetap jalan.")])
    refused = api.post(server("h9-a", "Halo"))
    assert refused.status_code == 503 and refused.json()["detail"]["code"] == "CONVERSATION_STORE_UNAVAILABLE"
    assert api.post({"request_id": "h9-b", "message": "Halo"}).json()["status"] == "COMPLETED"


def test_history_keeps_the_assumptions_limitations_and_methodology() -> None:
    """M63 (golden test 2026-10-02): the limitation "the boards are combined" was dropped from history and the next
    turn guessed the Regular board; a later turn now sees the whole answer."""
    from types import SimpleNamespace

    from app.conversations import assistant_text

    answer = SimpleNamespace(response_type="ANSWER", answer="TF tertinggi.", clarification_question=None,
                             assumptions=["Hari crash = median return <= -1%."],
                             limitations=["Market Board (Regular/Nego/Tunai) digabung."],
                             methodology="Net value per broker per hari dijumlahkan.")
    text = assistant_text(SimpleNamespace(response=answer))
    assert text.startswith("TF tertinggi.")
    assert "Batasan:\n- Market Board (Regular/Nego/Tunai) digabung." in text
    assert "Asumsi:\n- Hari crash" in text and "Metodologi:\nNet value per broker" in text
    question = SimpleNamespace(response_type="CLARIFICATION", answer="", clarification_question="Periode mana?",
                               assumptions=["x"], limitations=["y"], methodology=None)
    assert assistant_text(SimpleNamespace(response=question)) == "Periode mana?"
    assert assistant_text(SimpleNamespace(response=None)) is None
