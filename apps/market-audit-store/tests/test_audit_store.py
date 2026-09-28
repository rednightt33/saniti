from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from conftest import GOV, READ, SBX

NOW = "2026-09-28T10:00:00+00:00"
EXE = "exe_" + "1" * 24
SESS = "sess_" + "2" * 24


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_id_of(client, request_id: str = "req-1", **extra) -> str:
    response = client.post("/v1/internal/runs", json={"request_id": request_id, **extra}, headers=SBX)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def upload(client, data: bytes, media: str = "application/json", headers=SBX, *, body: bytes | None = None) -> dict:
    prepared = client.post("/v1/internal/artifacts", headers=headers,
                           json={"sha256": sha(data), "size_bytes": len(data), "media_type": media}).json()
    if prepared["upload"] is not None:
        target = prepared["upload"]
        assert client.put(target["url"], content=data if body is None else body,
                          headers=target["headers"]).status_code == 200
        verified = client.post(f"/v1/internal/artifacts/{prepared['artifact_id']}/verify", headers=headers).json()
        prepared = {**prepared, **verified}
    return prepared


def everything(client, path: str) -> str:
    response = client.get(path, headers=READ)
    assert response.status_code == 200, response.text
    return response.text


# ---------------------------------------------------------------------------------------- service boundaries

def test_health_and_ready(client) -> None:
    assert client.get("/health").json()["contract"] == "audit-store/v1"
    assert client.get("/ready").json() == {"status": "ready"}


def test_each_key_reaches_only_its_endpoints(client) -> None:
    run_id = run_id_of(client)
    assert client.post("/v1/internal/runs", json={"request_id": "x"}).status_code == 401
    assert client.post("/v1/internal/runs", json={"request_id": "x"}, headers=READ).status_code == 401
    assert client.get(f"/v1/runs/{run_id}", headers=GOV).status_code == 401
    assert client.get(f"/v1/runs/{run_id}", headers=SBX).status_code == 401
    assert client.get(f"/v1/runs/{run_id}", headers=READ).status_code == 200


def test_run_registration_is_idempotent_and_fills_identity(client) -> None:
    first = run_id_of(client, "req-a")
    again = run_id_of(client, "req-a", conversation_id="conv_" + "a" * 32, turn_index=2)
    assert first == again
    run = client.get(f"/v1/requests/req-a/run", headers=READ).json()
    assert run["run_id"] == first and run["turn_index"] == 2 and run["status"] == "OPEN"
    child = run_id_of(client, "req-b", parent_request_id="req-a")
    assert client.get(f"/v1/runs/{child}", headers=READ).json()["parent_run_id"] == first


# ---------------------------------------------------------------------------------------- events

def test_events_are_ordered_append_only_and_idempotent(client, clean) -> None:
    run_id = run_id_of(client)
    batch = [{"idempotency_key": f"k{i}", "event_type": "tool.call", "occurred_at": NOW, "payload": {"i": i}}
             for i in range(3)]
    first = client.post(f"/v1/internal/runs/{run_id}/events", json={"events": batch}, headers=SBX).json()
    retry = client.post(f"/v1/internal/runs/{run_id}/events", json={"events": batch[1:] + [
        {"idempotency_key": "k3", "event_type": "tool.call", "occurred_at": NOW}]}, headers=SBX).json()
    assert [a["seq"] for a in first["appended"]] == [1, 2, 3]
    assert [(a["seq"], a["duplicate"]) for a in retry["appended"]] == [(2, True), (3, True), (4, False)]
    events = client.get(f"/v1/runs/{run_id}/events", headers=READ).json()["events"]
    assert [e["seq"] for e in events] == [1, 2, 3, 4] and events[0]["source"] == "market-python-sandbox"
    with psycopg.connect(clean["admin"]) as c:  # append-only even for the owner
        try:
            c.execute("UPDATE ai_audit.event SET payload = '{}'")
            raise AssertionError("event was updated")
        except psycopg.errors.InsufficientPrivilege:
            pass


def test_oversized_or_reasoning_payloads_are_refused(client) -> None:
    run_id = run_id_of(client)
    big = {"idempotency_key": "big", "event_type": "tool.call", "occurred_at": NOW, "payload": {"x": "a" * 17000}}
    thinking = {"idempotency_key": "r", "event_type": "model.call", "occurred_at": NOW,
                "payload": {"output": [{"reasoning_content": "hidden"}]}}
    for event in (big, thinking):
        response = client.post(f"/v1/internal/runs/{run_id}/events", json={"events": [event]}, headers=SBX)
        assert response.status_code == 422
    assert client.get(f"/v1/runs/{run_id}/events", headers=READ).json()["events"] == []


# ---------------------------------------------------------------------------------------- artifacts

def test_upload_is_verified_here_deduplicated_and_never_exposes_the_object_key(client, settings) -> None:
    data = b'{"code": "print(1)"}'
    first = upload(client, data)
    assert first["state"] == "READY" and first["deduplicated"] is False
    again = client.post("/v1/internal/artifacts", headers=GOV, json={
        "sha256": sha(data), "size_bytes": len(data), "media_type": "application/json"}).json()
    assert again == {"artifact_id": first["artifact_id"], "state": "READY", "deduplicated": True, "upload": None}
    stored = Path(settings.local_object_dir) / "objects" / "sha256" / sha(data)[:2] / sha(data)
    assert stored.read_bytes() == data
    assert not [p for p in (Path(settings.local_object_dir) / "staging").rglob("*") if p.is_file()]
    run_id = run_id_of(client)
    client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=SBX,
                json={"links": [{"artifact_id": first["artifact_id"], "role": "PYTHON_SOURCE", "execution_id": EXE}]})
    listing = everything(client, f"/v1/runs/{run_id}/artifacts")
    assert "objects/sha256" not in listing and "staging/" not in listing and sha(data) in listing


def test_wrong_checksum_or_size_is_rejected_and_can_be_retried(client) -> None:
    data = b"expected content"
    wrong = upload(client, data, "text/plain", body=b"tampered content")
    assert wrong["state"] == "REJECTED" and wrong["rejected_reason"] == "CHECKSUM_MISMATCH"
    short = upload(client, data, "text/plain", body=b"short")
    assert short["state"] == "REJECTED" and short["rejected_reason"] == "SIZE_MISMATCH"
    conflict = client.post("/v1/internal/artifacts", headers=SBX,
                           json={"sha256": sha(data), "size_bytes": len(data) + 1, "media_type": "text/plain"})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "ARTIFACT_SIZE_CONFLICT"
    assert upload(client, data, "text/plain")["state"] == "READY"


def test_upload_urls_are_single_object_short_lived_and_cannot_replace_a_ready_object(client, settings) -> None:
    data = b"final bytes"
    prepared = client.post("/v1/internal/artifacts", headers=SBX, json={
        "sha256": sha(data), "size_bytes": len(data), "media_type": "text/plain"}).json()
    url = prepared["upload"]["url"]
    token = url.rsplit("/", 1)[1]
    assert client.put(url[:-3] + "xyz", content=data).status_code == 403          # tampered signature
    assert client.get(url).status_code == 403                                      # a PUT URL cannot read
    assert client.put(url, content=data).status_code == 200
    assert client.post(f"/v1/internal/artifacts/{prepared['artifact_id']}/verify",
                       headers=SBX).json()["state"] == "READY"
    # the old URL now writes a staging key nothing reads; the content address keeps the verified bytes
    assert client.put(url, content=b"overwrite!!").status_code == 200
    stored = Path(settings.local_object_dir) / "objects" / "sha256" / sha(data)[:2] / sha(data)
    assert stored.read_bytes() == data
    from app.storage import LocalStore

    store = LocalStore(settings.local_object_dir, settings.local_signing_key, "http://testserver")
    expired = store.token("staging/x/y", "PUT", -1, "text/plain")
    assert client.put(f"/v1/local/objects/{expired}", content=b"x").status_code == 403
    outside = store.token("objects/sha256/ab/" + "a" * 64, "PUT", 60, "text/plain")
    assert client.put(f"/v1/local/objects/{outside}", content=b"x").status_code == 403
    assert token


def test_access_is_logged_and_only_for_ready_artifacts(client, clean) -> None:
    ready = upload(client, b"output,1\n", "text/csv")
    pending = client.post("/v1/internal/artifacts", headers=SBX, json={
        "sha256": sha(b"never"), "size_bytes": 5, "media_type": "text/plain", "upload": False}).json()
    grant = client.post(f"/v1/artifacts/{ready['artifact_id']}/access", json={"purpose": "replay check"},
                        headers={**READ, "X-Audit-Accessor": "analyst@saniti"})
    assert grant.status_code == 200 and client.get(grant.json()["url"]).content == b"output,1\n"
    refused = client.post(f"/v1/artifacts/{pending['artifact_id']}/access", json={"purpose": "x" * 5}, headers=READ)
    assert refused.status_code == 409
    with psycopg.connect(clean["admin"]) as c:
        rows = c.execute("SELECT accessor, purpose FROM ai_audit.artifact_access").fetchall()
    assert rows == [("reader:analyst@saniti", "replay check")]


# ---------------------------------------------------------------------------------------- executions, runtime

RUNTIME = {"python_version": "3.12.7", "python_implementation": "CPython", "os": "Linux-6.1", "arch": "x86_64",
           "requirements_sha256": "c" * 64,
           "distributions": [{"name": "pandas", "version": "2.3.2"}, {"name": "numpy", "version": "2.3.3"}]}


def execution(execution_id: str = EXE, request_id: str = "req-1", **extra) -> dict:
    return {"execution_id": execution_id, "request_id": request_id, "session_id": SESS, "bundle_id": "bundle_1",
            "seq": 1, "status": "OK", "source_sha256": "d" * 64, "runtime": RUNTIME, "random_seed": 20260924,
            "timezone": "Asia/Jakarta", "declared_imports": ["pandas", "scipy.stats"],
            "loaded_distributions": [{"name": "scipy", "version": "1.16.2"}],
            "prebound_packages": ["pandas", "numpy", "duckdb", "saniti"], "stdlib_modules": ["statistics"],
            "unresolved_modules": [], "input_checksums": [{"position": 0, "data_request_id": "prices",
                                                           "sha256": "e" * 64, "ordering": ["ticker", "date"]}],
            "started_at": NOW, "finished_at": NOW, **extra}


def test_library_versions_are_queryable_per_execution_and_runtimes_are_shared(client, clean) -> None:
    first = client.post("/v1/internal/executions", json=execution(), headers=SBX).json()
    again = client.post("/v1/internal/executions", json=execution(), headers=SBX).json()
    other = client.post("/v1/internal/executions", json=execution("exe_" + "9" * 24, seq=2), headers=SBX).json()
    assert again["duplicate"] is True and first["runtime_image_id"] == other["runtime_image_id"]
    runtime = client.get(f"/v1/executions/{EXE}/runtime", headers=READ).json()
    assert {"name": "pandas", "version": "2.3.2"} in runtime["runtime"]["distributions"]
    libraries = runtime["libraries"]
    assert libraries["declared_imports"] == ["pandas", "scipy.stats"]
    assert libraries["loaded_distributions"] == [{"name": "scipy", "version": "1.16.2"}]
    assert "saniti" in libraries["prebound_packages"] and "whether or not" in libraries["evidence_note"]
    with psycopg.connect(clean["admin"]) as c:
        assert c.execute("SELECT count(*) FROM ai_audit.runtime_image").fetchone()[0] == 1


# ---------------------------------------------------------------------------------------- orc outbox

def orc_insert(clean, request_id: str, **payload) -> None:
    body = {"schema": "saniti.audit.run_finished/v1", "request_id": request_id, "conversation_id": "conv_" + "c" * 32,
            "turn_index": 0, "started_at": NOW, "finished_at": NOW, "model": "provider/model",
            "provider": "openrouter", "deployment": {"git_commit": "abc123"},
            "summary": {"status": "COMPLETED", "response_type": "ANSWER", "tool_call_count": 1,
                        "reasoning_token_count": 12, "total_tokens": 900},
            "events": [{"type": "tool.call", "occurred_at": NOW, "tool": "run_python",
                        "arguments": {"session_id": SESS}, "ok": True,
                        "result_summary": {"execution_id": EXE, "status": "OK"},
                        "reasoning": "must never be stored"}],
            "final_response": {"answer": "Return 12,35%."}, "expected": {}, **payload}
    with psycopg.connect(clean["orc"]) as c:  # market-ai-orc's own privilege: INSERT only
        c.execute("""INSERT INTO ai_audit.ingest_outbox (source, idempotency_key, request_id, kind, payload)
                     VALUES ('market-ai-orc', %s, %s, 'RUN_FINISHED', %s) ON CONFLICT DO NOTHING""",
                  (f"{request_id}:RUN_FINISHED", request_id, json.dumps(body)))


def test_a_finished_run_without_executions_completes_and_carries_no_reasoning(client, clean, settings) -> None:
    orc_insert(clean, "req-o")
    orc_insert(clean, "req-o")  # a retried insert is ignored
    assert client.app.state.consumer.drain() == {"complete": 1, "retry": 0, "incomplete": 0}
    run = client.get("/v1/requests/req-o/run", headers=READ).json()
    assert run["status"] == "COMPLETE" and run["conversation_id"] == "conv_" + "c" * 32
    artifacts = client.get(f"/v1/runs/{run['run_id']}/artifacts", headers=READ).json()["artifacts"]
    assert {a["role"] for a in artifacts} == {"TOOL_TRACE", "FINAL_RESPONSE"}
    stored = b"".join(p.read_bytes() for p in (Path(settings.local_object_dir) / "objects").rglob("*") if p.is_file())
    events = everything(client, f"/v1/runs/{run['run_id']}/events")
    assert b"must never be stored" not in stored and "must never be stored" not in events
    assert "reasoning_token_count" in json.dumps(run["summary"])  # a count, not content


def test_ingest_is_idempotent_when_a_row_is_processed_twice(client, clean) -> None:
    orc_insert(clean, "req-i")
    client.app.state.consumer.drain()
    with psycopg.connect(clean["admin"]) as c:
        c.execute("UPDATE ai_audit.ingest_outbox SET status = 'PENDING', processed_at = NULL")
    client.app.state.consumer.drain()
    run = client.get("/v1/requests/req-i/run", headers=READ).json()
    assert run["counts"]["events"] == 2 and run["counts"]["artifacts"] == 2


def test_a_run_stays_incomplete_until_the_sandbox_evidence_is_verified(client, clean) -> None:
    orc_insert(clean, "req-1", expected={"execution_ids": [EXE], "completion_ids": ["cmp_1"]})
    client.app.state.consumer.drain()
    run = client.get("/v1/requests/req-1/run", headers=READ).json()
    assert run["status"] == "INCOMPLETE" and run["missing"]["executions"] == [EXE]
    client.post("/v1/internal/executions", json=execution(), headers=SBX)
    source = upload(client, b"print('x')\n", "text/x-python")
    manifest = upload(client, b'{"runtime": 1}')
    raw = upload(client, b"PAR1-raw-input", "application/vnd.apache.parquet", headers=GOV)
    run_id = run["run_id"]
    client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=SBX, json={"links": [
        {"artifact_id": source["artifact_id"], "role": "PYTHON_SOURCE", "execution_id": EXE},
        {"artifact_id": manifest["artifact_id"], "role": "RUNTIME_MANIFEST", "execution_id": EXE}]})
    run = client.get(f"/v1/runs/{run_id}", headers=READ).json()
    assert run["status"] == "INCOMPLETE" and set(run["missing"]) == {"raw_inputs", "execution_manifests"}
    # the execution's input checksum is what must be archived: link the matching Parquet
    client.post("/v1/internal/executions", json=execution("exe_" + "8" * 24, input_checksums=[
        {"position": 0, "sha256": sha(b"PAR1-raw-input")}]), headers=SBX)
    with psycopg.connect(clean["admin"]) as c:
        c.execute("UPDATE ai_audit.execution SET input_checksums = %s WHERE execution_id = %s",
                  (json.dumps([{"position": 0, "sha256": sha(b"PAR1-raw-input")}]), EXE))
    client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=GOV, json={"links": [
        {"artifact_id": raw["artifact_id"], "role": "RAW_INPUT_PARQUET", "label": "ds_1"}]})
    completion = upload(client, b'{"completion": "cmp_1"}')
    client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=SBX, json={"links": [
        {"artifact_id": completion["artifact_id"], "role": "EXECUTION_MANIFEST", "label": "cmp_1"}]})
    assert client.get(f"/v1/runs/{run_id}", headers=READ).json()["status"] == "COMPLETE"
    # a producer adding an expectation that is not met brings it back to INCOMPLETE (never a silent COMPLETE)
    finalize = client.post(f"/v1/internal/runs/{run_id}/finalize", headers=SBX,
                           json={"expected": {"output_sha256": ["f" * 64]}}).json()
    assert finalize["status"] == "INCOMPLETE" and finalize["missing"] == {"outputs": ["f" * 64]}


def test_a_malformed_row_is_incomplete_and_a_transient_failure_is_retried(client, clean, monkeypatch) -> None:
    with psycopg.connect(clean["orc"]) as c:
        c.execute("""INSERT INTO ai_audit.ingest_outbox (source, idempotency_key, request_id, kind, payload)
                     VALUES ('market-ai-orc', 'bad', 'req-bad', 'RUN_FINISHED', '{"schema": "other"}')""")
    orc_insert(clean, "req-t")
    consumer = client.app.state.consumer
    calls = {"n": 0}
    original = consumer.service.store_own

    def flaky(payload, media):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("bucket unavailable")
        return original(payload, media)

    monkeypatch.setattr(consumer.service, "store_own", flaky)
    assert consumer.drain() == {"complete": 0, "retry": 1, "incomplete": 1}
    with psycopg.connect(clean["admin"]) as c:
        statuses = dict(c.execute("SELECT request_id, status FROM ai_audit.ingest_outbox").fetchall())
        assert statuses == {"req-bad": "INCOMPLETE", "req-t": "FAILED_RETRYABLE"}
        c.execute("UPDATE ai_audit.ingest_outbox SET next_attempt_at = now() WHERE request_id = 'req-t'")
    assert consumer.drain() == {"complete": 1, "retry": 0, "incomplete": 0}


# ---------------------------------------------------------------------------------------- joins and replay

def test_conversation_run_execution_code_runtime_and_output_join(client, clean) -> None:
    orc_insert(clean, "req-1", expected={"execution_ids": [EXE]})
    client.app.state.consumer.drain()
    client.post("/v1/internal/executions", json=execution(input_checksums=[]), headers=SBX)
    run_id = client.get("/v1/requests/req-1/run", headers=READ).json()["run_id"]
    source = upload(client, b"x = 1\n", "text/x-python")
    output = upload(client, b"ticker,ret\nBBCA,0.1\n", "text/csv")
    client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=SBX, json={"links": [
        {"artifact_id": source["artifact_id"], "role": "PYTHON_SOURCE", "execution_id": EXE},
        {"artifact_id": output["artifact_id"], "role": "OUTPUT", "execution_id": EXE, "label": "ret"}]})
    runs = client.get(f"/v1/conversations/conv_{'c' * 32}/runs", headers=READ).json()["runs"]
    assert [r["run_id"] for r in runs] == [run_id]
    replay = client.get(f"/v1/runs/{run_id}/replay-manifest", headers=READ).json()
    [entry] = replay["executions"]
    assert entry["python_source"][0]["sha256"] == sha(b"x = 1\n")
    assert entry["outputs"][0]["sha256"] == sha(b"ticker,ret\nBBCA,0.1\n")
    assert entry["random_seed"] == 20260924 and entry["timezone"] == "Asia/Jakarta"
    assert entry["runtime_fingerprint"].startswith("rt_") and entry["package_manifest"]
    assert "may not be reproducible" in replay["determinism_note"]


# ---------------------------------------------------------------------------------------- retention

def test_retention_report_never_offers_shared_or_held_objects_and_deletes_nothing(client, clean, settings) -> None:
    shared, held, alone = (upload(client, data) for data in (b'{"s":1}', b'{"h":1}', b'{"a":1}'))
    expired, live = run_id_of(client, "old"), run_id_of(client, "new")
    for run_id, artifacts in ((expired, (shared, held, alone)), (live, (shared,))):
        client.post(f"/v1/internal/runs/{run_id}/artifacts", headers=SBX, json={"links": [
            {"artifact_id": a["artifact_id"], "role": "OUTPUT"} for a in artifacts]})
    with psycopg.connect(clean["admin"]) as c:
        c.execute("UPDATE ai_audit.run SET created_at = now() - interval '200 days', "
                  "expires_at = now() - interval '1 day' WHERE run_id = %s", (expired,))
    hold = client.post("/v1/retention-holds", json={"artifact_id": held["artifact_id"], "reason": "legal hold"},
                       headers=READ).json()
    report = client.get("/v1/retention/report", headers=READ).json()
    assert report["dry_run"] is True and report["eligible_sample"] == [alone["artifact_id"]]
    assert report["artifacts"]["HELD"]["artifacts"] == 1
    assert report["artifacts"]["REFERENCED_BY_UNEXPIRED_RUN"]["artifacts"] == 1
    objects = [p for p in (Path(settings.local_object_dir) / "objects").rglob("*") if p.is_file()]
    assert len(objects) == 3  # nothing deleted
    client.post(f"/v1/retention-holds/{hold['hold_id']}/release", headers=READ)
    assert len(client.get("/v1/retention/report", headers=READ).json()["eligible_sample"]) == 2


# ---------------------------------------------------------------------------------------- contract

def test_the_published_openapi_contract_matches_the_service(client) -> None:
    published = json.loads((Path(__file__).resolve().parents[1] / "openapi" / "audit-store-v1.json").read_text())
    assert published == json.loads(json.dumps(client.app.openapi())), (
        "regenerate with: python -m app.export_openapi")


def test_timestamps_are_utc(client) -> None:
    run = client.get(f"/v1/runs/{run_id_of(client)}", headers=READ).json()
    created = datetime.fromisoformat(run["created_at"])
    assert created.utcoffset() == timedelta(0) and created <= datetime.now(timezone.utc)
