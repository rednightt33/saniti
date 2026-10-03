"""D2 (round 2026-10-03): get_session_output opens an output of an earlier answer by its value reference or id after the
sandbox deleted it (from the conversation's store, paged by the sandbox's stored-table operation), and the code an
execution ran; without a results context it reads the sandbox only, as before."""
from __future__ import annotations

import json

import httpx

from app.result_store import StoredOutput
from app.tools.artifacts import RunResults, current_results
from test_session_tools import OUTPUT, SESSION, call, registry
from test_session_tools import FakeSandbox as JsonSandbox

EXECUTION = "exe_" + "e" * 24
GONE = (404, {"status": "REJECTED", "error": {"code": "OUTPUT_NOT_FOUND", "message": "expired"}})


class FakeSandbox(JsonSandbox):
    """The session tools' fake sandbox, also taking an uploaded file (not JSON) as a request body."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/stored-tables/"):
            self.calls.append({"method": request.method, "path": request.url.path, "body": request.content,
                               "headers": dict(request.headers)})
            status, payload = self.answers.get(request.url.path, (404, {}))
            return httpx.Response(status, json=payload)
        return super().handler(request)


class FakeStore:
    def __init__(self) -> None:
        self.outputs = {OUTPUT: StoredOutput(
            output_id=OUTPUT, name="crash_days", format="PARQUET", byte_count=4, checksum_sha256="a" * 64,
            storage="POSTGRES", object_key=None, label="DATA_COVERAGE_VERIFIED",
            definition={"filters": [], "notes": "crash days"}, units={"net": "IDR"},
            lineage={"execution_id": EXECUTION, "need_id": "need_1", "data_as_of": "2026-09-30"},
            data_as_of="2026-09-30", request_id="req_old", execution_id=EXECUTION)}
        self.code = "rows = load('broker_flow')\n" + "x = 1\n" * 5000

    def output(self, conversation_id: str, output_id: str):
        return self.outputs.get(output_id) if conversation_id == "conv_1" else None

    def content(self, conversation_id: str, stored) -> bytes:
        return b"PAR1"

    def execution(self, conversation_id: str, execution_id: str):
        if conversation_id != "conv_1" or execution_id != EXECUTION:
            return None
        return {"execution_id": EXECUTION, "request_id": "req_old", "session_id": SESSION, "code": self.code,
                "code_truncated": False, "code_sha256": "b" * 64, "modules": ["pandas"],
                "access": {"reads": [{"kind": "range", "data_request_id": "data_request_1_A"}]}, "status": "OK"}

    def outputs_of_execution(self, conversation_id: str, execution_id: str):
        return [{"output_id": OUTPUT, "name": "crash_days", "output_type": "TABLE", "format": "PARQUET",
                 "row_count": 132}]


def page_answer(fake: FakeSandbox) -> None:
    fake.answers[f"/v1/sessions/{SESSION}/outputs/{OUTPUT}"] = GONE
    fake.answers["/v1/stored-tables/page"] = (200, {"format": "PARQUET", "row_count": 132, "offset": 0,
                                                    "rows": [{"date": "2026-01-02", "net": 5}], "next_offset": 1})


def with_results(fn):
    record = {"outputs": [{"ref": "out.o3", "output_id": OUTPUT, "session_id": SESSION}]}
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="run-session-1", store=FakeStore(),
                                           record=record))
    try:
        return fn()
    finally:
        current_results.reset(token)


def test_an_expired_output_opens_by_its_ref_from_the_store() -> None:
    fake = FakeSandbox()
    page_answer(fake)
    reg = registry(fake)
    outcome = with_results(lambda: call(reg, "get_session_output", {"ref": "out.o3", "limit": 1}))
    result = outcome.output["result"]
    assert outcome.ok and result["rows"] == [{"date": "2026-01-02", "net": 5}] and result["row_count"] == 132
    assert result["read_mode"] == "READ_RELEASED" and result["origin"]["source"] == "STORE"
    assert result["data_as_of"] == "2026-09-30" and result["lineage"]["execution_id"] == EXECUTION
    assert result["session_id"] == SESSION  # the owner, for value references
    upload = [c for c in fake.calls if c["path"] == "/v1/stored-tables/page"][0]
    assert upload["method"] == "POST"


def test_an_output_still_in_the_sandbox_is_read_there() -> None:
    fake = FakeSandbox({f"/v1/sessions/{SESSION}/outputs/{OUTPUT}": (200, {"output_id": OUTPUT, "released": True,
                                                                          "rows": [{"a": 1}]})})
    reg = registry(fake)
    result = with_results(lambda: call(reg, "get_session_output", {"session_id": SESSION, "output_id": OUTPUT}))
    assert result.output["result"]["rows"] == [{"a": 1}]
    assert not [c for c in fake.calls if c["path"].startswith("/v1/stored-tables")]


def test_without_a_results_context_only_the_sandbox_is_read() -> None:
    fake = FakeSandbox()
    page_answer(fake)
    result = call(registry(fake), "get_session_output", {"session_id": SESSION, "output_id": OUTPUT})
    assert result.output["result"]["status"] == "REJECTED"
    assert not [c for c in fake.calls if c["path"].startswith("/v1/stored-tables")]


def test_an_unknown_ref_and_a_missing_source_are_refused_with_a_next_step() -> None:
    reg = registry(FakeSandbox())
    unknown = with_results(lambda: call(reg, "get_session_output", {"ref": "o9"})).output["result"]
    assert unknown["code"] == "REF_NOT_FOUND" and unknown["next_action"] == "FIX_ARGUMENTS"
    both = call(reg, "get_session_output", {"ref": "o3", "output_id": OUTPUT})
    assert not both.ok and both.error_code == "INVALID_ARGUMENTS"


def test_an_execution_opens_its_code_reads_and_outputs() -> None:
    reg = registry(FakeSandbox())
    meta = with_results(lambda: call(reg, "get_session_output", {"execution_id": EXECUTION})).output["result"]
    assert meta["kind"] == "SCRIPT" and "code" not in meta and meta["modules"] == ["pandas"]
    assert meta["outputs"][0]["output_id"] == OUTPUT and meta["reads"][0]["data_request_id"] == "data_request_1_A"
    full = with_results(lambda: call(reg, "get_session_output", {"execution_id": EXECUTION,
                                                                 "include_content": True})).output["result"]
    assert len(full["code"]) == 20_000 and full["code_chars"] > 20_000 and full["note"]
    other = call(reg, "get_session_output", {"execution_id": EXECUTION}).output["result"]
    assert other["code"] == "OUTPUT_NOT_AVAILABLE"
    json.dumps(full)
