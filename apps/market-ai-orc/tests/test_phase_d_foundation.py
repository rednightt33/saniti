"""D0 (round 2026-10-03, ROUND_PLAN_2026-10-03_FASE_D.md): the reads every phase D tool shares (one stored output,
one stored execution, an output's file from the sandbox or the durable copy) and the kejedot index counted by code."""
from __future__ import annotations

import pytest

from app import friction
from app.result_store import ResultStore, output_bytes
from app.tools.registry import ToolOutcome, error_outcome
from test_conversations import ADMIN_URL, databases  # noqa: F401
from test_result_store import FakeBucket, conversation, entry, out


def ok(name: str, result: dict) -> ToolOutcome:
    return ToolOutcome(call_id="c1", name=name, ok=True, output={"ok": True, "tool": name, "result": result})


@pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
def test_one_output_and_one_execution_are_read_only_within_their_conversation(databases) -> None:  # noqa: F811
    admin, login = databases
    mine, other = conversation(admin), conversation(admin)
    store = ResultStore(login, FakeBucket())
    store.save_output(mine, "r1", entry(out(301), format="JSON", type="JSON"), b'{"a": 1}')
    store.save_execution(mine, "r1", {"execution_id": "exe_" + "2" * 24, "code": "print(1)", "modules": ["pandas"],
                                      "access": {"reads": [{"kind": "range", "data_request_id": "a"}]},
                                      "status": "OK"})
    stored = store.output(mine, out(301))
    assert stored is not None and stored.format == "JSON" and stored.execution_id == "exe_" + "2" * 24
    assert store.output(other, out(301)) is None
    execution = store.execution(mine, "exe_" + "2" * 24)
    assert execution["code"] == "print(1)" and execution["modules"] == ["pandas"]
    assert store.execution(other, "exe_" + "2" * 24) is None
    assert [o["output_id"] for o in store.outputs_of_execution(mine, "exe_" + "2" * 24)] == [out(301)]


@pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
def test_an_output_file_comes_from_the_sandbox_first_then_from_the_store(databases) -> None:  # noqa: F811
    admin, login = databases
    conversation_id = conversation(admin)
    store = ResultStore(login, FakeBucket())
    store.save_output(conversation_id, "r1", entry(out(302)), b"durable")

    def sandbox_has_it(session_id: str, output_id: str) -> bytes:
        return b"live"

    def expired(session_id: str, output_id: str) -> bytes:
        raise RuntimeError("404")

    assert output_bytes(store, sandbox_has_it, conversation_id, out(302), "sess_" + "1" * 24) == (b"live", None)
    data, stored = output_bytes(store, expired, conversation_id, out(302), "sess_" + "1" * 24)
    assert data == b"durable" and stored.output_id == out(302)
    with pytest.raises(LookupError):
        output_bytes(store, expired, conversation(admin), out(302), "sess_" + "1" * 24)  # another conversation


def test_without_a_store_an_expired_output_is_a_lookup_error() -> None:
    def expired(session_id: str, output_id: str) -> bytes:
        raise RuntimeError("404")

    with pytest.raises(LookupError):
        output_bytes(None, expired, "conv_x", out(303), "sess_" + "1" * 24)


def test_the_kejedot_index_counts_rejections_capacity_and_repeated_orders() -> None:
    counts = friction.empty()
    record = {"needs": [{"need_id": "need_old", "requests": [
        {"source_table": "IDX_Broker_Summary", "scope_sha256": "s1"}]}]}
    friction.count_tool(counts, "prepare_data_bundle", error_outcome("c1", "prepare_data_bundle", "TOOL_TIMEOUT",
                                                                     "slow"), record)
    friction.count_tool(counts, "open_analysis_session", ok("open_analysis_session", {
        "status": "REJECTED", "code": "SESSION_CAPACITY_EXCEEDED", "error": {"code": "SESSION_CAPACITY_EXCEEDED"}}),
        record)
    # the same tables and row filter as the earlier need: ordered again (g7)
    same = {"status": "APPROVED", "need_id": "need_new", "approved": {"requests": [
        {"source_table": "IDX_Broker_Summary", "scope_sha256": "s1"}]}}
    friction.count_tool(counts, "submit_data_need_spec", ok("submit_data_need_spec", same), record)
    # another row filter is a new order, not a repeat
    other = {"status": "APPROVED", "need_id": "need_b", "approved": {"requests": [
        {"source_table": "IDX_Broker_Summary", "scope_sha256": "s2"}]}}
    friction.count_tool(counts, "submit_data_need_spec", ok("submit_data_need_spec", other), record)
    friction.count_tool(counts, "run_python", ok("run_python", {"status": "OK"}), record)
    assert counts == {"rejected_tool_calls": 2, "gate_repairs": 0, "repeated_data_orders": 1,
                      "capacity_refusals": 1}
