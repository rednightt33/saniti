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
                                  "meaning": "Net value of foreign investors (teks Inggris; terjemahan belum ada)",
                                  "unit": "IDR"}
    assert meta["columns"][2]["meaning"] is None
    assert meta["definition"] == {"Periode": "2025-10-10 s.d. 2026-08-31", "Saham": ["BBRI"],
                                  "Catatan": "cum = jumlah berjalan"}
    assert meta["completeness"] == {"status": "UNCHECKED"}  # no Governor and no table facts here
    assert meta["texts"]["completeness_label"] == "Kelengkapan"


SCOPE = {"type": "PREDICATE", "column": "ticker", "operator": "EQ", "values": ["BBRI"]}


class RecountSandbox(ExportSandbox):
    """Answers the file's first and last date (recount MIN / MAX) from the request's metadata."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        import base64
        import json

        if request.url.path == "/v1/stored-tables/recount":
            meta = json.loads(base64.urlsafe_b64decode(request.headers["x-saniti-output-meta"] + "=="))
            self.calls.append({"path": request.url.path, "meta": meta})
            return httpx.Response(200, json={"value": "2025-10-09" if meta["measure"] == "MIN" else "2026-08-31"})
        return super().handler(request)


class Governor:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.specs = answer, error, []

    def summary(self, spec, lineage, timeout=None):
        self.specs.append((spec, lineage))
        if self.error:
            raise self.error
        return self.answer


def facts(tables, columns):
    return {"Feature_03_Stock_Broker_Daily": {"time_column": "date", "row_presence": "ACTIVITY_ONLY",
                                              "groupable": {"ticker", "board_type"}},
            "IDX_Stock_Universe": {"time_column": None, "row_presence": "NOT_APPLICABLE", "groupable": {"Ticker"}}}


def export_xlsx(fake, governor, requests, columns=("date", "board_type", "foreign_net_value"), fmt="XLSX",
                source_columns=None):
    import base64
    import json

    from app.tools.export import export_specs
    from app.tools.registry import ToolRegistry

    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    tools = ToolRegistry()
    for spec in export_specs(sandbox, timeout_seconds=10, max_result_bytes=40000, table_facts=facts,
                             governor=governor):
        tools.register(spec)
    record = {"outputs": [{"ref": "out.o1", "output_id": OUTPUT, "session_id": SESSION, "name": "bbri flow",
                           "type": "TABLE", "columns": list(columns), "definition": {"notes": "x"},
                           "lineage": {"need_id": "need_1", "data_as_of": "2026-08-31"}}],
              "needs": [{"need_id": "need_1", "requests": requests}]}
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_1", store=ExportStore(),
                                           record=record, fetch=lambda sid, oid: b"PAR1"))
    try:
        call(tools, "export_result", {"ref": "o1", "format": fmt, "source_columns": source_columns})
    finally:
        current_results.reset(token)
    sent = [c for c in fake.calls if c["path"] == "/v1/stored-tables/export"][-1]
    return json.loads(base64.urlsafe_b64decode(sent["headers"]["x-saniti-output-meta"] + "=="))


def test_an_xlsx_gets_the_source_days_per_group_over_the_files_own_period() -> None:
    """M128 (d): BBRI foreign flow per board, Nego 210 of 211 days. The export counts, with one Governor summary
    over the file's first and last date and the need's own filter, the days the source has per board."""
    from app.tools.data_planner import sha256_json

    governor = Governor({"status": "OK", "period": {"from": "2025-10-09", "to": "2026-08-31", "calendar_dates": 211},
                         "rows": [{"board_type": "Regular", "row_count": 211, "days_present": 211},
                                  {"board_type": "Nego", "row_count": 211, "days_present": 211}]})
    requests = [{"source_table": "Feature_03_Stock_Broker_Daily", "scope_spec": SCOPE},
                {"source_table": "IDX_Stock_Universe", "scope_spec": {"type": "ALL"}}]
    meta = export_xlsx(RecountSandbox(), governor, requests)
    spec, lineage = governor.specs[0]
    assert spec == {"summary_version": "summary_spec/v1", "source_table": "Feature_03_Stock_Broker_Daily",
                    "scope": SCOPE, "restrictions": [], "group_by": ["board_type"],
                    "measures": [{"column": None, "function": "COUNT", "as": "row_count"}],
                    "period": {"from": "2025-10-09", "to": "2026-08-31"}}
    assert lineage == {"purpose": "EVIDENCE", "recipe_sha256": sha256_json(spec)}
    assert meta["completeness"] == {
        "status": "CHECKED", "time_column": "date", "group_columns": ["board_type"], "from": "2025-10-09",
        "to": "2026-08-31", "calendar_dates": 211, "row_presence": "ACTIVITY_ONLY",
        "groups": [{"key": ["Regular"], "days": 211}, {"key": ["Nego"], "days": 211}]}


def test_completeness_is_not_guessed_when_the_source_cannot_be_counted_the_same_way() -> None:
    """Cases other than the observed one: a filter through another table, a filter too long to keep, a file without
    the table's time column, a Governor refusal or failure, and a CSV (no definition sheet at all)."""
    ok = {"status": "OK", "period": {"calendar_dates": 3}, "rows": [{"row_count": 3, "days_present": 3}]}
    table = "Feature_03_Stock_Broker_Daily"
    for requests, columns, governor in (
            ([{"source_table": table, "scope_spec": SCOPE, "restrictions": ["IDX_Stock_Universe: x"]}],
             ("date", "foreign_net_value"), Governor(ok)),
            ([{"source_table": table}], ("date", "foreign_net_value"), Governor(ok)),
            ([{"source_table": table, "scope_spec": SCOPE}], ("month", "foreign_net_value"), Governor(ok)),
            ([{"source_table": table, "scope_spec": SCOPE}], ("date", "foreign_net_value"),
             Governor({"status": "REJECTED_POLICY", "code": "SCAN_LIMIT"})),
            ([{"source_table": table, "scope_spec": SCOPE}], ("date", "foreign_net_value"),
             Governor(error=RuntimeError("down")))):
        assert export_xlsx(RecountSandbox(), governor, requests, columns)["completeness"] == {"status": "UNCHECKED"}
    whole = export_xlsx(RecountSandbox(), Governor(ok), [{"source_table": table, "scope_spec": SCOPE}],
                        ("date", "foreign_net_value"))["completeness"]
    assert whole["status"] == "CHECKED" and whole["group_columns"] == [] and whole["groups"] == [{"key": [], "days": 3}]
    fake = RecountSandbox()
    csv = export_xlsx(fake, Governor(ok), [{"source_table": table, "scope_spec": SCOPE}], fmt="CSV")
    assert "completeness" not in csv and "texts" not in csv
    assert not [c for c in fake.calls if c["path"] == "/v1/stored-tables/recount"]


def test_the_metadata_header_stays_within_the_sandboxs_limit() -> None:
    """M133: the sandbox reads at most 16 KiB of headers; 60 columns with long meanings and 50 groups fit by
    shortening the meanings first, then dropping the completeness groups."""
    from app.tools.export import META_HEADER_BYTES, _header_bytes, fit_header

    columns = [{"label": f"Kolom {i}", "name": f"col_{i}", "meaning": "m" * 300, "unit": "IDR"} for i in range(60)]
    small = {"format": "PARQUET", "columns": columns[:3], "completeness": {"status": "UNCHECKED"}}
    assert fit_header(small) == small
    fitted = fit_header({"format": "PARQUET", "columns": columns, "completeness": {"status": "UNCHECKED"}})
    assert _header_bytes(fitted) <= META_HEADER_BYTES and 0 < len(fitted["columns"][0]["meaning"]) < 300
    groups = {"status": "CHECKED", "groups": [{"key": ["x" * 200], "days": 1}] * 50}
    fitted = fit_header({"format": "PARQUET", "columns": columns, "completeness": groups})
    assert _header_bytes(fitted) <= META_HEADER_BYTES and fitted["completeness"] == {"status": "UNCHECKED"}


def test_renamed_source_columns_are_counted_under_the_names_the_model_gives() -> None:
    """Live check 2026-10-09 (edge_58b3a299…): the analysis renamed Date to trading_date and Market Board to
    market_board, so both files said "not checked". The model names the source column of each copied column; the
    Governor is asked with the source names, the sandbox counts under the file's names; a mapping to a column the
    table cannot be grouped by is not used as a group."""
    governor = Governor({"status": "OK", "period": {"calendar_dates": 211},
                         "rows": [{"board_type": "Nego", "row_count": 900, "days_present": 210}]})
    requests = [{"source_table": "Feature_03_Stock_Broker_Daily", "scope_spec": SCOPE}]
    meta = export_xlsx(RecountSandbox(), governor, requests, ("trading_date", "board", "net"),
                       source_columns=[{"column": "trading_date", "source_column": "date"},
                                       {"column": "board", "source_column": "board_type"},
                                       {"column": "net", "source_column": "foreign_net_value"},
                                       {"column": "nope", "source_column": "ticker"}])
    spec = governor.specs[0][0]
    assert spec["group_by"] == ["board_type"]
    assert meta["completeness"]["time_column"] == "trading_date"
    assert meta["completeness"]["group_columns"] == ["board"]
    assert meta["completeness"]["groups"] == [{"key": ["Nego"], "days": 210}]


def test_a_renamed_source_column_keeps_its_catalog_meaning() -> None:
    import base64
    import json

    from app.tools import _column_meanings
    from app.tools.export import export_specs
    from app.tools.registry import ToolRegistry

    reader = Rows([{"column_name": "Date", "description_id": "Tanggal transaksi", "unit": None},
                   {"column_name": "Net Value", "description": "Net traded value", "unit": "IDR"}])
    fake = ExportSandbox()
    sandbox = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    tools = ToolRegistry()
    for spec in export_specs(sandbox, timeout_seconds=10, max_result_bytes=40000,
                             column_meanings=_column_meanings(reader)):
        tools.register(spec)
    record = {"outputs": [{"ref": "out.o1", "output_id": OUTPUT, "session_id": SESSION, "name": "flow", "type": "TABLE",
                           "columns": ["trading_date", "net_sum"], "lineage": {"need_id": "need_1"}}],
              "needs": [{"need_id": "need_1", "requests": [{"source_table": "IDX_Broker_Summary"}]}]}
    token = current_results.set(RunResults(conversation_id="conv_1", request_id="req_1", store=ExportStore(),
                                           record=record, fetch=lambda sid, oid: b"PAR1"))
    try:
        call(tools, "export_result", {"ref": "o1", "format": "XLSX", "source_columns": [
            {"column": "trading_date", "source_column": "Date"}]})
    finally:
        current_results.reset(token)
    meta = json.loads(base64.urlsafe_b64decode(fake.calls[-1]["headers"]["x-saniti-output-meta"] + "=="))
    assert reader.asked[0][1] == ["Date", "net_sum", "trading_date"]
    assert [c["meaning"] for c in meta["columns"]] == ["Tanggal transaksi", None]  # a computed column gets none
