"""D4 (round 2026-10-03): export_result writes an output as a download file through the sandbox, keeps it in
AI_conversation_export (Postgres, user decision 2), shows the model only its id, name, size and format, lists it in the
API response's artifacts, and serves it to the conversation's owner only."""
from __future__ import annotations

import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import AgentOrchestrator
from app.result_store import ResultStore
from app.tools import build_default_registry
from app.tools.analysis import SandboxClient
from app.tools.artifacts import RunResults, current_results
from app.tools.request_data import GovernorClient
from conftest import BASE_ENV, ScriptedClient, make_settings
from test_analysis_tools import SANDBOX_KEY
from test_artifacts import FakeSandbox, FakeStore
from test_conversations import ADMIN_URL, databases  # noqa: F401
from test_result_store import conversation
from test_session_tools import OUTPUT, SESSION, call

AUTH = {"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}"}
XLSX = b"PK\x03\x04 fake workbook"


class ExportSandbox(FakeSandbox):
    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/stored-tables/export":
            self.calls.append({"path": request.url.path, "headers": dict(request.headers), "body": request.content})
            status, payload = self.answers.get(request.url.path, (200, None))
            if payload is not None:
                return httpx.Response(status, json=payload)
            return httpx.Response(200, content=XLSX, headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "X-Saniti-Extension": "xlsx"})
        return super().handler(request)


class ExportStore(FakeStore):
    def __init__(self) -> None:
        super().__init__()
        self.saved: list[dict] = []

    def save_export(self, conversation_id, request_id, source_ref, fmt, file_name, mime_type, data, includes):
        self.saved.append({"source_ref": source_ref, "format": fmt, "file_name": file_name, "data": data,
                           "includes": includes})
        return {"export_id": "exp_" + "1" * 24, "file_name": file_name, "format": fmt, "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}


def registry(fake: FakeSandbox, enabled: bool = True):
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    governor = GovernorClient("http://governor.test", "g" * 40, 10, transport=httpx.MockTransport(
        lambda r: httpx.Response(404)))
    return build_default_registry(sandbox_client=sandbox, governor_client=governor, dataneed_enabled=True,
                                  session_timeout_seconds=200, export=enabled)


def export(fake: FakeSandbox, store, arguments: dict, fetch=None):
    record = {"outputs": [{"ref": "out.o3", "output_id": OUTPUT, "session_id": SESSION, "name": "crash days",
                           "type": "TABLE", "definition": {"notes": "crash days"},
                           "lineage": {"need_id": "need_1", "data_as_of": "2026-08-31"}}],
              "needs": [{"need_id": "need_1", "requests": [{"source_table": "IDX_Broker_Summary"}]}]}
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_1", store=store, record=record,
                                           fetch=fetch))
    try:
        return call(registry(fake), "export_result", arguments)
    finally:
        current_results.reset(token)


def test_the_tool_exists_only_behind_its_switch() -> None:
    assert "export_result" in registry(FakeSandbox()).names()
    assert "export_result" not in registry(FakeSandbox(), enabled=False).names()


def test_an_output_is_exported_and_the_model_sees_no_content() -> None:
    fake, store = ExportSandbox(), ExportStore()
    result = export(fake, store, {"ref": "o3", "format": "XLSX"}, fetch=lambda sid, oid: b"PAR1").output["result"]
    assert result["status"] == "EXPORTED" and result["file_name"] == "crash_days.xlsx"
    assert result["size_bytes"] == len(XLSX) and "PK" not in str(result)
    assert store.saved[0]["data"] == XLSX and store.saved[0]["source_ref"] == "out.o3"
    import base64
    import json

    meta = json.loads(base64.urlsafe_b64decode(fake.calls[-1]["headers"]["x-saniti-output-meta"] + "=="))
    assert meta["target"] == "XLSX" and meta["definition"] == {"Catatan": "crash days"}
    assert meta["lineage"]["Tabel sumber"] == "IDX_Broker_Summary" and meta["lineage"]["Data per"] == "2026-08-31"
    assert "need_id=need_1" in meta["lineage"]["Kode audit (untuk tim teknis)"]
    assert meta["checksum_sha256"] == hashlib.sha256(b"PAR1").hexdigest()


def test_an_expired_output_is_exported_from_the_store() -> None:
    fake, store = ExportSandbox(), ExportStore()

    def gone(session_id: str, output_id: str) -> bytes:
        raise RuntimeError("expired")

    result = export(fake, store, {"output_id": OUTPUT, "format": "CSV"}, fetch=gone).output["result"]
    assert result["status"] == "EXPORTED" and fake.calls[-1]["body"] == b"PAR1"  # the stored copy


def test_a_file_over_the_limit_is_refused_with_a_next_step() -> None:
    fake = ExportSandbox({"/v1/stored-tables/export": (413, {"status": "REJECTED", "error": {
        "code": "EXPORT_TOO_LARGE", "message": "too big"}, "next_action": "Export fewer columns or rows."})})
    result = export(fake, ExportStore(), {"ref": "o3", "format": "CSV"},
                    fetch=lambda sid, oid: b"PAR1").output["result"]
    assert result["code"] == "EXPORT_TOO_LARGE" and result["next_action"]


@pytest.mark.skipif(not ADMIN_URL, reason="ORC_TEST_POSTGRES_URL not set")
def test_the_owner_downloads_the_file_and_no_one_else(databases) -> None:  # noqa: F811
    admin, login = databases
    conversation_id = conversation(admin)  # owner "default"
    store = ResultStore(login)
    data = b"a,b\n" + b"1,2\n" * 300_000  # about 1.2 MB: more than one chunk
    saved = store.save_export(conversation_id, "req_1", "out.o3", "CSV", "flow.csv", "text/csv", data,
                              {"definition": False, "lineage": True})
    assert store.export(conversation_id, saved["export_id"])["size_bytes"] == len(data)
    assert b"".join(store.export_chunks(conversation_id, saved["export_id"], chunk=100_000)) == data
    agent = AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry(), result_store=store,
                              output_fetcher=lambda *a: b"", carried_uploader=lambda *a: {})
    with TestClient(create_app(make_settings(), orchestrator=agent)) as api:
        got = api.get(f"/v1/exports/{saved['export_id']}/download", headers=AUTH)
        assert got.status_code == 200 and got.content == data
        assert got.headers["content-disposition"] == 'attachment; filename="flow.csv"'
        assert got.headers["x-saniti-sha256"] == hashlib.sha256(data).hexdigest()
        other = api.get(f"/v1/exports/{saved['export_id']}/download", headers={**AUTH, "X-Saniti-Owner": "someone"})
        assert other.status_code == 404
        assert api.get(f"/v1/exports/{saved['export_id']}/download").status_code == 401


def test_a_run_lists_its_exports_in_the_response() -> None:
    from pydantic import BaseModel, ConfigDict

    from app.schemas import AgentRunRequest
    from app.tools.registry import ToolRegistry, ToolSpec
    from conftest import ANSWER, final_response, tool_call_response

    class NoArgs(BaseModel):
        model_config = ConfigDict(extra="forbid")

    registry = ToolRegistry()
    registry.register(ToolSpec(name="export_result", description="x", arguments_model=NoArgs, handler=lambda a: {
        "status": "EXPORTED", "export_id": "exp_" + "2" * 24, "file_name": "flow.xlsx", "format": "XLSX",
        "size_bytes": 10, "sha256": "c" * 64, "download": "/v1/exports/exp_" + "2" * 24 + "/download"}))
    client = ScriptedClient([tool_call_response("export_result"), final_response(ANSWER)])
    result = AgentOrchestrator(make_settings(), client, registry).run(
        AgentRunRequest(request_id="req_export", message="export it"))
    assert result.artifacts == [{"export_id": "exp_" + "2" * 24, "file_name": "flow.xlsx", "format": "XLSX",
                                 "size_bytes": 10, "sha256": "c" * 64,
                                 "download_path": "/v1/exports/exp_" + "2" * 24 + "/download"}]
    assert "artifacts" in result.model_dump(mode="json")



class Rows:
    """A catalog reader whose one query answers the AI column catalog's rows."""

    def __init__(self, rows):
        self.rows, self.asked = rows, []

    def read_only(self):
        import contextlib

        @contextlib.contextmanager
        def session():
            def run(sql, params):
                self.asked.append(params)
                return self.rows
            yield run
        return session()


def test_an_xlsx_carries_the_readers_titles_and_the_catalogs_column_meanings() -> None:
    """M128b (Excel run 2026-10-08): the file's headers were foreign_net_value, foreign_net_value_cum and turnover_idr.
    The model gives the titles; a column a source table has gets the catalog's meaning and unit; a column the
    analysis made gets none (its meaning stays in the definition's notes); a label for an unknown column is ignored."""
    import base64
    import json

    from app.tools import _column_meanings
    from app.tools.export import export_specs
    from app.tools.registry import ToolRegistry

    reader = Rows([{"column_name": "foreign_net_value", "description": "Net value of foreign investors", "unit": "IDR"}])
    fake, store = ExportSandbox(), ExportStore()
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    tools = ToolRegistry()
    for spec in export_specs(sandbox, timeout_seconds=10, max_result_bytes=40000,
                             column_meanings=_column_meanings(reader)):
        tools.register(spec)
    record = {"outputs": [{"ref": "out.o1", "output_id": OUTPUT, "session_id": SESSION, "name": "bbri flow",
                           "type": "TABLE", "columns": ["date", "foreign_net_value", "foreign_net_value_cum"],
                           "definition": {"period": {"start": "2025-10-10", "end": "2026-08-31"}, "entities": ["BBRI"],
                                          "filters": [], "notes": "cum = jumlah berjalan"},
                           "lineage": {"need_id": "need_1", "data_as_of": "2026-08-31"}}],
              "needs": [{"need_id": "need_1", "requests": [{"source_table": "Feature_03_Stock_Broker_Daily"}]}]}
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_1", store=store, record=record,
                                           fetch=lambda sid, oid: b"PAR1"))
    try:
        call(tools, "export_result", {"ref": "o1", "format": "XLSX", "column_labels": [
            {"column": "foreign_net_value", "label": "Net beli asing (Rp)"}, {"column": "nope", "label": "x"}]})
    finally:
        current_results.reset(token)
    meta = json.loads(base64.urlsafe_b64decode(fake.calls[-1]["headers"]["x-saniti-output-meta"] + "=="))
    assert reader.asked[0][0] == ["Feature_03_Stock_Broker_Daily"]
    assert meta["headers"] == {"date": "Date", "foreign_net_value": "Net beli asing (Rp)",
                               "foreign_net_value_cum": "Foreign net value cum"}
    assert meta["columns"][1] == {"label": "Net beli asing (Rp)", "name": "foreign_net_value",
                                  "meaning": "Net value of foreign investors", "unit": "IDR"}
    assert meta["columns"][2]["meaning"] is None
    assert meta["definition"] == {"Periode": "2025-10-10 s.d. 2026-08-31", "Saham": ["BBRI"],
                                  "Catatan": "cum = jumlah berjalan"}
