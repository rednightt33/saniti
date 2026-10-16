"""E9 (EXEC-1018B, M176; user decisions 2026-10-16): the data behind a result can be exported without the model writing
code. export_result(data_request=...) exports the rows a data request delivered (from its bundle, or the same approved
need extracted again when the bundle expired); a supporting table is exported from its kept copy, and after its 30 days
rebuilt by running the stored code of its session again, exported only when it matches the original byte for byte."""
from __future__ import annotations

import base64
import hashlib
import json

import httpx

from app.tools.analysis import SandboxClient
from app.tools.artifacts import RunResults, current_results
from app.tools.export import export_specs
from app.tools.registry import ToolRegistry
from test_analysis_tools import SANDBOX_KEY
from test_export import XLSX, ExportStore
from test_session_tools import call

NEED, NEW_NEED = "need_" + "1" * 24, "need_" + "2" * 24
OLD_BUNDLE, NEW_BUNDLE = "bundle_" + "a" * 24, "bundle_" + "b" * 24
SESSION, NEW_SESSION = "sess_" + "a" * 24, "sess_" + "e" * 24
SUPPORT, REBUILT = "out_" + "d" * 24, "out_" + "f" * 24
ROWS = b"PAR1 daily rows"
TABLE = b"PAR1 working table"


class Sandbox:
    def __init__(self, bundle_alive: bool = False, rebuilt: bytes = TABLE, run_status: str = "OK") -> None:
        self.bundle_alive, self.rebuilt, self.run_status = bundle_alive, rebuilt, run_status
        self.calls: list[tuple[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        meta = {"rows": 3, "columns": ["date", "broker", "net"], "rows_identity": "same", "ranges": [
            {"range_id": "r1", "start": "2026-08-01", "end": "2026-08-31"}]}
        if path == f"/v1/bundles/{OLD_BUNDLE}/datasets/data_request_1_A/file":
            if self.bundle_alive:
                return httpx.Response(200, content=ROWS, headers={"X-Saniti-Dataset-Meta": base64.urlsafe_b64encode(
                    json.dumps(meta).encode()).decode()})
            return httpx.Response(410, json={"status": "REJECTED", "error": {
                "code": "BUNDLE_EXPIRED", "message": "gone", "rows_identity": "same"}})
        if path == f"/v1/bundles/{NEW_BUNDLE}/datasets/data_request_1_A/file":
            return httpx.Response(200, content=ROWS, headers={"X-Saniti-Dataset-Meta": base64.urlsafe_b64encode(
                json.dumps(meta).encode()).decode()})
        if path == f"/v1/data-needs/{NEED}/carry":
            return httpx.Response(200, json={"status": "APPROVED", "need_id": NEW_NEED, "carried_from": NEED})
        if path == "/v1/sessions":
            return httpx.Response(200, json={"session_id": NEW_SESSION, "status": "ACTIVE"})
        if path.endswith("/execute"):
            return httpx.Response(200, json={"status": self.run_status, "error_message": "boom"})
        if path.endswith("/complete"):
            return httpx.Response(200, json={"status": "COMPLETED", "released_outputs": [
                {"output_id": REBUILT, "name": "daily_rows", "support": True,
                 "checksum_sha256": hashlib.sha256(self.rebuilt).hexdigest()}]})
        if path == "/v1/stored-tables/export":
            return httpx.Response(200, content=XLSX, headers={"content-type": "application/octet-stream",
                                                              "X-Saniti-Extension": "xlsx"})
        return httpx.Response(404, json={"status": "REJECTED", "error": {"code": "NOT_FOUND", "message": path}})


class Store(ExportStore):
    def executions_of_session(self, conversation_id, session_id):
        return [{"execution_id": "exe_1", "request_id": "req_old", "code": "save_table('daily_rows', load('a'))",
                 "code_truncated": False, "status": "OK"},
                {"execution_id": "exe_2", "request_id": "req_old", "code": "x = 1", "code_truncated": False,
                 "status": "SCRIPT_ERROR"},
                {"execution_id": "exe_3", "request_id": "req_later", "code": "y = 2", "code_truncated": False,
                 "status": "OK"}]


def record() -> dict:
    return {"needs": [{"need_id": NEED, "bundle_id": OLD_BUNDLE, "requests": [
        {"data_request_id": "data_request_1_A", "logical_name": "broker_flow", "source_table": "IDX_Broker_Summary",
         "columns": ["date", "broker", "net"], "scope": "Ticker = ADRO"}]}],
        "outputs": [{"ref": "out.o4", "output_id": SUPPORT, "session_id": SESSION, "name": "daily_rows",
                     "type": "SUPPORT", "request_id": "req_old", "row_count": 3, "columns": ["date"],
                     "lineage": {"need_id": NEED, "execution_id": "exe_1"},
                     "support": {"checksum_sha256": hashlib.sha256(TABLE).hexdigest(), "keep_until": "2026-11-15"}}]}


def run(fake: Sandbox, arguments: dict, fetch=None, rebuilds: list | None = None):
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    client.supporting_data = True
    rebuilds = rebuilds if rebuilds is not None else []

    def rebuild(need_id: str) -> dict:
        rebuilds.append(need_id)
        return {"status": "READY", "input_bundle_id": NEW_BUNDLE}

    registry = ToolRegistry()
    for spec in export_specs(client, timeout_seconds=10, max_result_bytes=200_000, rebuild=rebuild):
        registry.register(spec)
    store = Store()
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_now", store=store,
                                           record=record(), fetch=fetch))
    try:
        return call(registry, "export_result", arguments).output["result"], store
    finally:
        current_results.reset(token)


def test_a_data_request_is_exported_from_its_bundle_while_the_sandbox_keeps_it() -> None:
    fake = Sandbox(bundle_alive=True)
    result, store = run(fake, {"data_request": "data_request_1_A", "format": "XLSX"})
    assert result["status"] == "EXPORTED" and result["data_status"] == "STORED" and result["rows"] == 3
    assert store.saved[0]["source_ref"] == f"{NEED}:data_request_1_A"
    assert not [c for c in fake.calls if "carry" in c[1]]


def test_an_expired_bundle_is_extracted_again_from_the_same_need() -> None:
    fake, rebuilds = Sandbox(), []
    result, _ = run(fake, {"data_request": "data_request_1_A", "format": "CSV"}, rebuilds=rebuilds)
    assert result["status"] == "EXPORTED" and result["data_status"] == "REBUILT"
    assert result["same_rows_as_original"] is True and rebuilds == [NEW_NEED]


def test_an_unknown_data_request_is_refused_with_the_known_ones() -> None:
    result, _ = run(Sandbox(), {"data_request": "data_request_9", "format": "CSV"})
    assert result["code"] == "DATA_REQUEST_NOT_FOUND" and "data_request_1_A" in result["message"]


def test_a_kept_supporting_table_is_exported_as_stored() -> None:
    result, _ = run(Sandbox(), {"ref": "out.o4", "format": "CSV"}, fetch=lambda sid, oid: TABLE)
    assert result["status"] == "EXPORTED" and result["data_status"] == "STORED"


def gone(session_id: str, output_id: str) -> bytes:
    if output_id == REBUILT:
        return TABLE
    raise RuntimeError("expired")


def test_an_expired_supporting_table_is_rebuilt_from_the_stored_code_and_exported_on_a_match() -> None:
    fake = Sandbox()
    store_gone = Store()
    store_gone.outputs = {}
    result, _ = run(fake, {"ref": "out.o4", "format": "CSV"}, fetch=gone)
    assert result["status"] == "EXPORTED" and result["data_status"] == "REBUILT", result
    executed = [c for c in fake.calls if c[1].endswith("/execute")]
    assert len(executed) == 1  # only the OK runs up to the table's own request


def test_a_rebuilt_table_that_differs_is_not_exported() -> None:
    result, _ = run(Sandbox(rebuilt=b"PAR1 other rows"), {"ref": "out.o4", "format": "CSV"}, fetch=gone)
    assert result["status"] == "REJECTED" and result["data_status"] == "EXPIRED_NOT_REBUILDABLE"
    assert "differs" in result["message"]


def test_a_failed_rerun_is_refused_with_its_reason() -> None:
    result, _ = run(Sandbox(run_status="SCRIPT_ERROR"), {"ref": "out.o4", "format": "CSV"}, fetch=gone)
    assert result["code"] == "EXPIRED_NOT_REBUILDABLE" and "exe_1" in result["message"]


class InputSandbox(Sandbox):
    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/stored-tables/export":
            self.meta = json.loads(base64.urlsafe_b64decode(request.headers["x-saniti-output-meta"] + "=="))
            statuses = [{"data_request_id": "data_request_1_A", "sheet": "broker_flow", "status": "NOT_INCLUDED",
                         "reason": "BUNDLE_EXPIRED"}]
            return httpx.Response(200, content=XLSX, headers={
                "X-Saniti-Extension": "xlsx",
                "X-Saniti-Inputs": base64.urlsafe_b64encode(json.dumps(statuses).encode()).decode()})
        return super().handler(request)


def test_an_xlsx_of_a_result_asks_for_its_input_sheets_and_reports_each() -> None:
    """E1: the export of a result names the inputs of its need; an input the sandbox could not add is reported with
    the way to get its rows."""
    fake = InputSandbox()
    rec = record()
    rec["outputs"].append({"ref": "out.o5", "output_id": "out_" + "9" * 24, "session_id": SESSION, "name": "ret",
                           "type": "TABLE", "request_id": "req_old", "lineage": {"need_id": NEED}})
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    client.supporting_data = True
    registry = ToolRegistry()
    for spec in export_specs(client, timeout_seconds=10, max_result_bytes=200_000, rebuild=lambda n: {}):
        registry.register(spec)
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_now", store=Store(), record=rec,
                                           fetch=lambda sid, oid: b"PAR1"))
    try:
        result = call(registry, "export_result", {"ref": "out.o5", "format": "XLSX"}).output["result"]
    finally:
        current_results.reset(token)
    assert fake.meta["inputs"] == [{"bundle_id": OLD_BUNDLE, "data_request_id": "data_request_1_A",
                                    "sheet": "broker_flow"}]
    assert result["status"] == "EXPORTED" and result["inputs"][0]["status"] == "NOT_INCLUDED"
    assert "data_request" in result["inputs_note"]
