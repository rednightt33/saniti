"""R-STORE (round 2026-10-03 C2): released outputs and executions kept with the conversation (Postgres up to 20 MB and
50,000 rows, the bucket beyond), put back into a later session that no longer holds them, deleted with their
conversation (bucket objects first), and the run's wiring: what a run releases is stored at its end and the data
record says so."""
from __future__ import annotations

import hashlib
import secrets

import psycopg
import pytest

from app import result_store as rs
from app.conversations import ConversationStore
from app.orchestrator import AgentOrchestrator
from app.result_store import ResultStore, restore_missing, store_released
from app.schemas import AgentRunRequest
from conftest import ScriptedClient, make_settings
from test_conversations import ADMIN_URL, databases  # noqa: F401
from test_dataneed_orchestrator import OUTPUT, SESSION, Tools, answer, completed, flow
from conftest import final_response


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, keys: list[str]) -> None:
        self.deleted.extend(keys)
        for key in keys:
            self.objects.pop(key, None)


def conversation(admin_url: str) -> str:
    conversation_id = f"conv_{secrets.token_hex(16)}"
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute('INSERT INTO public."AI_conversation" (conversation_id, owner_key, expires_at) '
                           "VALUES (%s, 'default', now() + interval '1 day')", (conversation_id,))
    return conversation_id


def entry(output_id: str, rows: int = 2, **extra) -> dict:
    return {"output_id": output_id, "session_id": "sess_" + "1" * 24, "name": "ytd", "type": "TABLE",
            "format": "PARQUET", "row_count": rows, "columns": ["ticker", "ret"], "label": "DATA_COVERAGE_VERIFIED",
            "definition": {"filters": [], "notes": "x"}, "units": {"ret": "PERCENT"},
            "lineage": {"execution_id": "exe_" + "2" * 24, "need_id": "need_1", "data_as_of": "2026-10-02"}, **extra}


def out(n: int) -> str:
    return "out_" + f"{n:024x}"


pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")


def test_a_table_is_kept_in_postgres_and_a_large_one_in_the_bucket(databases, monkeypatch) -> None:  # noqa: F811
    admin, login = databases
    conversation_id, bucket = conversation(admin), FakeBucket()
    store = ResultStore(login, bucket)
    assert store.save_output(conversation_id, "r1", entry(out(1)), b"small") == "POSTGRES"
    assert store.save_output(conversation_id, "r1", entry(out(1)), b"small") == "ALREADY_STORED"
    # more rows than Postgres keeps: the bucket, under the conversation's prefix
    assert store.save_output(conversation_id, "r1", entry(out(2), rows=rs.POSTGRES_MAX_ROWS + 1), b"many") == "BUCKET"
    assert list(bucket.objects) == [f"outputs/{conversation_id}/{out(2)}.parquet"]
    monkeypatch.setattr(rs, "CONVERSATION_POSTGRES_BUDGET", len(b"small") + 3)  # the conversation's budget is spent
    assert store.save_output(conversation_id, "r1", entry(out(3)), b"other") == "BUCKET"
    tables = {t.output_id: t for t in store.stored_tables(conversation_id)}
    assert set(tables) == {out(1), out(2), out(3)} and tables[out(1)].data_as_of == "2026-10-02"
    assert store.content(conversation_id, tables[out(1)]) == b"small"
    assert store.content(conversation_id, tables[out(2)]) == b"many"
    # a row that cannot be written leaves no object behind
    with pytest.raises(psycopg.Error):
        store.save_output(conversation_id, "bad request id!", entry(out(4), rows=rs.POSTGRES_MAX_ROWS + 1), b"x")
    assert f"outputs/{conversation_id}/{out(4)}.parquet" in bucket.deleted
    assert f"outputs/{conversation_id}/{out(4)}.parquet" not in bucket.objects
    # without a bucket, a large table is refused (and the answer still stands: store_released reports FAILED)
    done = store_released(ResultStore(login), lambda s, o: b"z", conversation_id, "r1",
                          [entry(out(5), rows=rs.POSTGRES_MAX_ROWS + 1)])
    assert done == {out(5): "FAILED"}


def test_executions_keep_their_code_and_the_hash_of_the_whole(databases) -> None:  # noqa: F811
    admin, login = databases
    conversation_id = conversation(admin)
    store = ResultStore(login)
    code = "x = 1\n" * 20_000  # longer than 65,536 characters
    store.save_execution(conversation_id, "r1", {"execution_id": "exe_" + "9" * 24, "code": code, "status": "OK",
                                                 "modules": ["pandas"]})
    with psycopg.connect(admin) as connection:
        row = connection.execute('SELECT length(code), code_truncated, code_sha256 FROM '
                                 'public."AI_conversation_execution" WHERE execution_id = %s',
                                 ("exe_" + "9" * 24,)).fetchone()
    assert row == (rs.MAX_CODE_CHARS, True, hashlib.sha256(code.encode()).hexdigest())


def test_the_stored_tables_a_session_lacks_are_restored(databases) -> None:  # noqa: F811
    admin, login = databases
    conversation_id = conversation(admin)
    store = ResultStore(login, FakeBucket())
    for n in (201, 202, 203):  # output_id is unique across conversations, as the sandbox's are
        store.save_output(conversation_id, "r1", entry(out(n)), f"table {n}".encode())
    uploads = []

    def upload(session_id, meta, data):
        uploads.append((session_id, meta["output_id"], data, meta["data_as_of"], meta["origin"]["evidence_label"]))
        return {"status": "RESTORED"}

    view = {"session_id": "sess_" + "7" * 24, "carried_output_ids": [out(201)]}
    done = restore_missing(store, upload, conversation_id, "r2", view["session_id"], view, None)
    assert sorted(r["output_id"] for r in done) == [out(202), out(203)]  # out(201) is still in the sandbox
    assert {u[1] for u in uploads} == {out(202), out(203)} and uploads[0][3] == "2026-10-02"
    assert uploads[0][4] == "DATA_COVERAGE_VERIFIED"
    # a research session takes only the tables its approved plan names
    uploads.clear()
    restore_missing(store, upload, conversation_id, "r3", view["session_id"], {"carried_output_ids": []}, [out(203)])
    assert [u[1] for u in uploads] == [out(203)]


def test_the_cleanup_deletes_bucket_objects_before_the_rows(databases) -> None:  # noqa: F811
    admin, login = databases
    conversation_id, bucket = conversation(admin), FakeBucket()
    store = ResultStore(login, bucket)
    store.save_output(conversation_id, "r1", entry(out(9), rows=rs.POSTGRES_MAX_ROWS + 1), b"big")
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute('UPDATE public."AI_conversation" SET created_at = now() - interval \'2 days\', '
                           "updated_at = now() - interval '2 days', expires_at = now() - interval '1 day' "
                           "WHERE conversation_id = %s", (conversation_id,))
    conversations = ConversationStore(login, retention_days=30, lease_seconds=900)
    seen = []
    conversations.before_delete = lambda ids: (seen.extend(ids), bucket.delete(store.object_keys(ids)))
    assert conversations.cleanup() >= 1 and conversation_id in seen
    assert bucket.objects == {} and store.stored_tables(conversation_id) == []


# ------------------------------------------------------------------------------------------ the run's wiring

class MemoryStore:
    def __init__(self) -> None:
        self.outputs, self.executions = {}, []

    def save_output(self, conversation_id, request_id, entry, data):
        self.outputs[entry["output_id"]] = (conversation_id, entry, data)
        return "POSTGRES"

    def save_execution(self, conversation_id, request_id, execution):
        self.executions.append(execution)


def test_a_run_stores_what_it_released_and_the_record_says_so() -> None:
    store, fetched = MemoryStore(), []

    def fetch(session_id, output_id, request_id):
        fetched.append((session_id, output_id, request_id))
        return b"parquet bytes"

    done = completed()
    done["released_outputs"][0]["lineage"] = {"execution_id": "exe_1", "data_as_of": "2026-10-02"}
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true"),
                                     ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))]),
                                     Tools([done]).registry(), result_store=store, output_fetcher=fetch,
                                     carried_uploader=lambda *a: {"status": "RESTORED"})
    result = orchestrator.run(AgentRunRequest(request_id="dn", message="Berapa return YTD BBCA?",
                                              conversation_id="conv_" + "a" * 32))
    assert fetched == [(SESSION, OUTPUT, "dn")]
    conversation_id, kept, data = store.outputs[OUTPUT]
    assert conversation_id == "conv_" + "a" * 32 and data == b"parquet bytes"
    assert kept["lineage"]["data_as_of"] == "2026-10-02" and kept["label"] == "DATA_COVERAGE_VERIFIED"
    [recorded] = result.data_record["outputs"]
    assert recorded["stored"] is True and recorded["data_as_of"] == "2026-10-02"


def test_without_a_conversation_nothing_is_stored() -> None:
    store = MemoryStore()
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"),
                                     ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))]),
                                     Tools([completed()]).registry(), result_store=store,
                                     output_fetcher=lambda *a: b"x", carried_uploader=lambda *a: {})
    orchestrator.run(AgentRunRequest(request_id="dn", message="Berapa return YTD BBCA?"))
    assert store.outputs == {}


# ------------------------------------------------------------------------------------------ C2e: the data date

def test_a_data_need_body_carries_the_conversation_data_date_until_newest_is_asked() -> None:
    from app.tools.analysis import DataDate, current_data_date, pinned_body, take_data_date_policy

    token = current_data_date.set(DataDate("2026-10-01"))
    try:
        assert pinned_body({"spec": {}})["as_of_date"] == "2026-10-01"
        payload = {"spec_version": "data_need_spec/v1", "data_as_of_policy": None}
        take_data_date_policy(payload)
        assert "data_as_of_policy" not in payload and pinned_body({})["as_of_date"] == "2026-10-01"
        take_data_date_policy({"data_as_of_policy": "NEWEST"})  # the user asked for newer data
        assert "as_of_date" not in pinned_body({}) and current_data_date.get().newest
    finally:
        current_data_date.reset(token)
    assert pinned_body({"spec": {}}) == {"spec": {}}  # no conversation date: nothing pinned


def _record_with(output_date: str) -> dict:
    from app import data_record as records

    record = records.empty()
    records.add_output(record, "earlier", alias="o1", output_id=out(300), session_id="sess_" + "1" * 24,
                       name="ytd", columns=["ticker"], row_count=2, lineage={"data_as_of": output_date})
    return record


def _run_with(record: dict, released_date: str, message: str = "Berapa return YTD BBCA?"):
    store = MemoryStore()
    done = completed()
    done["released_outputs"][0]["lineage"] = {"execution_id": "exe_1", "data_as_of": released_date}
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", AI_ENABLE_VALUE_REFERENCES="true"),
                                     ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))]),
                                     Tools([done]).registry(), result_store=store, output_fetcher=lambda *a: b"x",
                                     carried_uploader=lambda *a: {})
    return orchestrator.run(AgentRunRequest(request_id="dn", message=message, conversation_id="conv_" + "b" * 32),
                            data_record=record)


def test_a_changed_data_date_is_stated_by_the_backend() -> None:
    from app.orchestrator import DATA_DATE_CHANGED_LINE

    result = _run_with(_record_with("2026-09-25"), "2026-10-02")
    assert DATA_DATE_CHANGED_LINE.format(new="2026-10-02", old="2026-09-25") in result.response.limitations


def test_an_old_kept_data_date_offers_a_recomputation_and_the_answer_is_noted() -> None:
    from app.orchestrator import DATA_DATE_PINNED_LINE

    result = _run_with(_record_with("2020-01-02"), "2020-01-02")
    assert DATA_DATE_PINNED_LINE.format(date="2020-01-02") in result.response.limitations
    [noted] = result.data_record["answers"]
    assert noted["request_id"] == "dn" and noted["question"] == "Berapa return YTD BBCA?"
    assert noted["summary"].startswith("Return YTD BBCA") and noted["data_as_of"] == "2020-01-02"
    from app import data_record as records

    assert "Earlier answers of this conversation" in records.note(result.data_record)
