"""The table download of an answer (user 2026-10-20: "tambah ICON download ... excel", "hanya kolom yang tampil di
jawaban dengan judulnya, ditambah sheet definisi", "Ok, opsi A", "Ok gapapa"): every row of a kept table as XLSX with
the answer's columns and titles, its input sheets extracted again when the sandbox no longer keeps them, no model."""
from __future__ import annotations

import base64
import json
import threading

import httpx
import pytest

from app import data_record as records
from app import user_texts as texts
from app.conversations import ConversationError
from app.table_export import TableExportError, TableExportRequest, export_table
from app.tools.analysis import SandboxClient
from app.tools.export import export_specs
from app.result_store import StoredOutput
from app.tools.registry import ToolRegistry
from test_analysis_tools import SANDBOX_KEY
from test_export import XLSX
from test_export_supporting import NEED, NEW_BUNDLE, NEW_NEED, OLD_BUNDLE, SESSION, Sandbox, Store, record

RESULT = "out_" + "9" * 24


class Inputs(Sandbox):
    """The sandbox: the old bundle is gone (its input sheet NOT_INCLUDED), the new one is read."""

    def __init__(self) -> None:
        super().__init__()
        self.exports: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/stored-tables/export":
            meta = json.loads(base64.urlsafe_b64decode(request.headers["x-saniti-output-meta"] + "=="))
            self.exports.append(meta)
            fresh = all(i["bundle_id"] == NEW_BUNDLE for i in meta.get("inputs") or [])
            statuses = [{"data_request_id": "data_request_1_A", "sheet": "broker_flow",
                         **({"status": "INCLUDED", "rows": 3} if fresh else
                            {"status": "NOT_INCLUDED", "reason": "BUNDLE_EXPIRED"})}]
            return httpx.Response(200, content=XLSX, headers={
                "X-Saniti-Extension": "xlsx",
                "X-Saniti-Inputs": base64.urlsafe_b64encode(json.dumps(statuses).encode()).decode()})
        return super().handler(request)


class Conversations:
    def __init__(self, rec: dict) -> None:
        self.rec = rec

    def data_record(self, owner: str, conversation_id: str) -> dict:
        if owner != "owner-a" or conversation_id != "conv_1":
            raise ConversationError("CONVERSATION_NOT_FOUND", "No such conversation for this owner.", 404)
        return self.rec


def setup(fake: Sandbox, rebuilds: list):
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    client.supporting_data = True

    def rebuild(need_id: str) -> dict:
        rebuilds.append(need_id)
        return {"status": "READY", "input_bundle_id": NEW_BUNDLE}
    registry = ToolRegistry()
    for spec in export_specs(client, timeout_seconds=10, max_result_bytes=200_000, rebuild=rebuild):
        registry.register(spec)
    rec = {**records.empty(), **record()}  # a kept data record carries its version
    rec["outputs"].append({"ref": "out.o5", "output_id": RESULT, "session_id": SESSION, "name": "ret_sektor",
                           "type": "TABLE", "request_id": "req_old", "row_count": 400,
                           "columns": ["sector", "median_pct", "n", "share"], "lineage": {"need_id": NEED}})
    store = Store()
    store.outputs[RESULT] = StoredOutput(
        output_id=RESULT, name="ret_sektor", format="PARQUET", byte_count=4, checksum_sha256="a" * 64,
        storage="POSTGRES", object_key=None, label="DATA_COVERAGE_VERIFIED", definition={"filters": []}, units={},
        lineage={"need_id": NEED, "data_as_of": "2026-10-16"}, data_as_of="2026-10-16", request_id="req_old",
        execution_id=None)
    return registry, store, Conversations(rec)


def request(**kwargs) -> TableExportRequest:
    return TableExportRequest(columns=["sector", "median_pct"], titles=["Sektor", "Median (%)"], **kwargs)


def test_the_download_keeps_the_answers_columns_and_titles_and_rebuilds_expired_inputs() -> None:
    fake, rebuilds = Inputs(), []
    registry, store, conversations = setup(fake, rebuilds)
    body = export_table(registry=registry, result_store=store, conversations=conversations, owner="owner-a",
                        conversation_id="conv_1", output_id=RESULT, request=request())
    assert body["export_id"] and body["download"].endswith("/download") and body["size_bytes"] == len(XLSX)
    first, second = fake.exports
    assert first["select"] == ["sector", "median_pct"] and first["headers"] == {"sector": "Sektor",
                                                                                 "median_pct": "Median (%)"}
    assert first["inputs"][0]["bundle_id"] == OLD_BUNDLE and second["inputs"][0]["bundle_id"] == NEW_BUNDLE
    assert rebuilds == [NEW_NEED] and body["inputs_data_status"] == {"status": "REBUILT"}
    assert body["inputs"][0]["status"] == "INCLUDED"
    assert second["definition"][texts.INPUTS_REBUILT_FIELD].startswith("ditarik ulang dari sumber pada ")
    assert len(store.saved) == 1  # one file kept, the second write


def test_a_table_whose_inputs_are_still_kept_is_written_once() -> None:
    class Alive(Inputs):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/stored-tables/export":
                self.exports.append(json.loads(base64.urlsafe_b64decode(request.headers["x-saniti-output-meta"]
                                                                        + "==")))
                statuses = [{"data_request_id": "data_request_1_A", "status": "INCLUDED", "rows": 3}]
                return httpx.Response(200, content=XLSX, headers={"X-Saniti-Extension": "xlsx", "X-Saniti-Inputs":
                                                                   base64.urlsafe_b64encode(json.dumps(
                                                                       statuses).encode()).decode()})
            return super().handler(request)
    fake, rebuilds = Alive(), []
    registry, store, conversations = setup(fake, rebuilds)
    body = export_table(registry=registry, result_store=store, conversations=conversations, owner="owner-a",
                        conversation_id="conv_1", output_id=RESULT, request=request())
    assert len(fake.exports) == 1 and rebuilds == [] and "inputs_data_status" not in body


@pytest.mark.parametrize("owner,output_id,code,status", [
    ("owner-b", RESULT, "CONVERSATION_NOT_FOUND", 404),
    ("owner-a", "out_" + "0" * 24, "OUTPUT_NOT_FOUND", 404),
    ("owner-a", "../etc", "OUTPUT_NOT_FOUND", 404)])
def test_another_owner_or_an_unknown_table_is_refused(owner, output_id, code, status) -> None:
    registry, store, conversations = setup(Inputs(), [])
    with pytest.raises(TableExportError) as raised:
        export_table(registry=registry, result_store=store, conversations=conversations, owner=owner,
                     conversation_id="conv_1", output_id=output_id, request=request())
    assert (raised.value.code, raised.value.status) == (code, status)


def test_one_download_of_a_table_runs_at_a_time() -> None:
    gate, inside = threading.Event(), threading.Event()

    class Slow(Inputs):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/stored-tables/export":
                inside.set()
                gate.wait(5)
            return super().handler(request)
    registry, store, conversations = setup(Slow(), [])
    args = dict(registry=registry, result_store=store, conversations=conversations, owner="owner-a",
                conversation_id="conv_1", output_id=RESULT, request=request())
    worker = threading.Thread(target=lambda: export_table(**args), daemon=True)
    worker.start()
    assert inside.wait(5)
    with pytest.raises(TableExportError) as raised:
        export_table(**args)
    assert raised.value.code == "EXPORT_IN_PROGRESS" and raised.value.status == 409
    gate.set()
    worker.join(5)
    assert export_table(**args)["export_id"]  # free again once the first one ended


def test_without_the_stores_the_route_says_downloads_are_not_available() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.orchestrator import AgentOrchestrator
    from app.tools import build_default_registry
    from conftest import BASE_ENV, ScriptedClient, make_settings
    config = make_settings()
    with TestClient(create_app(config, orchestrator=AgentOrchestrator(config, ScriptedClient([]),
                                                                      build_default_registry()))) as app:
        reply = app.post(f"/v1/conversations/conv_1/outputs/{RESULT}/export", json={"columns": ["a"]},
                         headers={"Authorization": f"Bearer {BASE_ENV['MARKET_AI_ORC_API_KEY']}",
                                  "X-Saniti-Owner": "owner-a"})
    assert reply.status_code == 404 and reply.json()["detail"]["code"] == "EXPORT_NOT_AVAILABLE"


def test_a_need_keeps_its_bundles_expiry() -> None:
    rec = {**records.empty(), "needs": [{"need_id": NEED}]}
    records.set_bundle(rec, NEED, OLD_BUNDLE, "2026-10-21T07:00:00+00:00")
    assert rec["needs"][0] == {"need_id": NEED, "bundle_id": OLD_BUNDLE, "bundle_expires_at": "2026-10-21T07:00:00+00:00"}
    records.set_bundle(rec, NEED, NEW_BUNDLE)
    assert rec["needs"][0] == {"need_id": NEED, "bundle_id": NEW_BUNDLE}  # an unknown expiry is not kept
