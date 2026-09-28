"""IP2 solution 2 in the sandbox: the harness archives executions and completions to market-audit-store.

A fake audit store (httpx.MockTransport) records every call. The end-to-end tests run a real confined session."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audit import classify_modules, declared_imports, runtime_inventory
from app.audit_client import AuditClient
from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog
from test_dataneed_bundles import HEADERS, approve, build, ytd_parts

KEY = "s" * 40
CODE = """import statistics
import scipy.stats
prices = load('prices')
banks = load('stock_classification')
last = prices.groupby('ticker', as_index=False)['close'].last()
print(statistics.mean(last['close']), scipy.stats.__name__)
emit_table('last_close', last)
"""


class FakeAuditStore:
    def __init__(self) -> None:
        self.down = False
        self.calls: list[tuple[str, str, object]] = []
        self.uploads: dict[str, bytes] = {}
        self.pending: dict[str, str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        body = json.loads(request.content) if request.method == "POST" and request.content else None
        self.calls.append((request.method, request.url.path, body))
        path = request.url.path
        if request.method == "PUT":
            self.uploads[path.rsplit("/", 1)[1]] = request.content
            return httpx.Response(200)
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        if path == "/v1/internal/runs":
            return httpx.Response(200, json={"run_id": "run_" + "2" * 32, "request_id": body["request_id"],
                                             "status": "OPEN"})
        if path == "/v1/internal/artifacts":
            artifact = "art_" + body["sha256"][:32]
            self.pending[artifact] = body["sha256"]
            upload = {"method": "PUT", "url": f"https://bucket.test/staging/{artifact}", "headers": {},
                      "expires_at": "2026-09-28T12:00:00Z"} if body.get("upload", True) else None
            return httpx.Response(200, json={"artifact_id": artifact, "state": "PENDING", "deduplicated": False,
                                             "upload": upload})
        if path.endswith("/verify"):
            artifact = path.split("/")[-2]
            ok = hashlib.sha256(self.uploads.get(artifact, b"")).hexdigest() == self.pending[artifact]
            return httpx.Response(200, json={"artifact_id": artifact, "state": "READY" if ok else "REJECTED"})
        return httpx.Response(200, json={"run_id": "run_" + "2" * 32, "execution_id": "x", "runtime_image_id": "x",
                                          "duplicate": False, "appended": [], "linked": 1, "duplicates": 0})

    def posted(self, suffix: str) -> list:
        return [body for method, path, body in self.calls if method == "POST" and path.endswith(suffix)]


# ---------------------------------------------------------------------------------------- library evidence units

def test_declared_imports_come_from_the_ast() -> None:
    assert declared_imports(CODE) == ["scipy.stats", "statistics"]
    assert declared_imports("from . import x\nimport a.b as c\nfrom d.e import f") == ["a.b", "d.e"]
    assert declared_imports("def (") == []  # a syntax error declares nothing, it does not fail


def test_observed_modules_are_classified_without_claiming_use() -> None:
    classes = classify_modules(["scipy.stats._stats", "scipy", "statistics", "json.decoder", "not_a_package_x",
                                "saniti_session", "_socket"])
    assert "scipy" in {d["name"] for d in classes["loaded_distributions"]}
    assert classes["stdlib_modules"] == ["json", "statistics"]
    assert classes["unresolved_modules"] == ["not_a_package_x"]  # runtime helpers and private modules are left out


def test_the_runtime_inventory_lists_installed_versions_and_the_lock_hash(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-analysis.txt"
    lock.write_text("pandas==2.3.2\n")
    inventory = runtime_inventory([lock])
    names = {d["name"].lower(): d["version"] for d in inventory["distributions"]}
    assert "pandas" in names and "numpy" in names
    assert inventory["requirements_sha256"] == hashlib.sha256(b"requirements-analysis.txt\0pandas==2.3.2\n").hexdigest()
    assert inventory["python_version"] and inventory["arch"]


def test_audit_settings_are_required_only_while_on(make_service) -> None:
    from app.config import ConfigError, Settings

    service = make_service(start=False)
    assert service.settings.audit_store_enabled is False
    env = {k: v for k, v in os.environ.items()}
    with pytest.raises(ConfigError):
        Settings.from_env({**env, "PY_SANDBOX_API_KEY": "a" * 40, "SQL_GOVERNOR_URL": "http://g",
                           "SQL_GOVERNOR_DATASET_ACCESS_KEY": "b" * 40, "PY_SANDBOX_AUDIT_STORE_ENABLED": "true",
                           "PY_SANDBOX_DATANEED_ENABLED": "true"})


# ---------------------------------------------------------------------------------------- end to end (real session)

@pytest.fixture
def audited(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", PY_SANDBOX_AUDIT_STORE_ENABLED="true",
                           AUDIT_STORE_URL="https://audit.test", AUDIT_STORE_SANDBOX_KEY=KEY)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    dataneed = client.app.state.dataneed
    fake = FakeAuditStore()
    dataneed.audit.client = AuditClient("https://audit.test", KEY, transport=httpx.MockTransport(fake))
    env = {"api": client, "governor": governor, "dataneed": dataneed, "service": service, "fake": fake}
    need = approve(env)
    bundle = build(env, need, ytd_parts(env, need)).json()
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS).json()
    env.update(session_id=opened["session_id"], bundle=bundle)
    yield env
    dataneed.sessions.stop()


def execute(env, code: str) -> dict:
    return env["api"].post(f"/v1/sessions/{env['session_id']}/execute",
                           json={"request_id": "req_bundle_1", "code": code}, headers=HEADERS).json()


@requires_root
def test_code_runtime_inputs_and_outputs_reach_the_audit_store(audited) -> None:
    body = execute(audited, CODE)
    assert body["status"] == "OK", body
    result = audited["api"].post(f"/v1/sessions/{audited['session_id']}/complete",
                                 json={"request_id": "req_bundle_1"}, headers=HEADERS).json()
    assert result["status"] == "COMPLETED"
    outbox, fake = audited["dataneed"].audit, audited["fake"]
    assert outbox.drain() == {"complete": 2, "retry": 0, "incomplete": 0}
    [record] = fake.posted("/v1/internal/executions")
    assert record["execution_id"] == body["execution_id"] and record["declared_imports"] == ["scipy.stats",
                                                                                              "statistics"]
    assert "scipy" in {d["name"] for d in record["loaded_distributions"]}  # observed, not only declared
    assert "statistics" in record["stdlib_modules"] and "pandas" in record["prebound_packages"]
    assert record["random_seed"] is not None and record["timezone"] == "UTC"
    assert record["source_sha256"] == hashlib.sha256(CODE.encode()).hexdigest()
    assert CODE.encode() in fake.uploads.values()  # the exact source, byte for byte
    assert {d["name"].lower() for d in record["runtime"]["distributions"]} >= {"pandas", "numpy", "duckdb"}
    inputs = record["input_checksums"]
    assert [i["position"] for i in inputs] == list(range(len(inputs))) and all(i["sha256"] for i in inputs)
    references = [b for b in fake.posted("/v1/internal/artifacts") if b.get("upload") is False]
    assert {r["sha256"] for r in references} == {i["sha256"] for i in inputs}  # linked by content, not re-uploaded
    roles = {link["role"] for body in fake.posted("/artifacts") if "links" in body for link in body["links"]}
    assert roles >= {"PYTHON_SOURCE", "RUNTIME_MANIFEST", "EXECUTION_TRACE", "RAW_INPUT_PARQUET", "OUTPUT",
                     "EXECUTION_MANIFEST", "VALIDATION_RESULT", "APPROVED_DATANEED_CONTRACT",
                     "INPUT_BUNDLE_MANIFEST"}
    [expected] = fake.posted("/finalize")
    assert len(expected["expected"]["output_sha256"]) == 1


@requires_root
def test_the_analysis_process_never_sees_the_audit_key_or_the_spool(audited) -> None:
    spool = audited["dataneed"].audit.spool
    body = execute(audited, f"""import os
print(sorted(k for k in os.environ if 'AUDIT' in k or 'KEY' in k))
try:
    os.listdir({str(spool)!r})
    print('SPOOL READABLE')
except PermissionError:
    print('SPOOL DENIED')
""")
    assert body["status"] == "OK" and body["stdout"].split("\n")[:2] == ["[]", "SPOOL DENIED"]
    assert KEY not in json.dumps(body)


@requires_root
def test_an_audit_outage_never_fails_the_analysis_and_is_retried(audited) -> None:
    audited["fake"].down = True
    body = execute(audited, "x = load('prices')\nprint(len(x) > 0)")
    assert body["status"] == "OK" and body["stdout"].strip() == "True"
    outbox = audited["dataneed"].audit
    assert outbox.drain() == {"complete": 0, "retry": 1, "incomplete": 0}
    assert outbox.status() == {"FAILED_RETRYABLE": 1}
    audited["fake"].down = False
    outbox._db.execute("UPDATE items SET next_attempt_at = 0")
    assert outbox.drain()["complete"] == 1 and outbox.status() == {"COMPLETE": 1}


@requires_root
def test_without_the_flag_nothing_is_observed_or_archived(make_service, governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    dataneed = client.app.state.dataneed
    assert dataneed.audit is None and dataneed.sessions.audit is None
    assert not (Path(service.settings.data_dir) / "audit_outbox.sqlite3").exists()
