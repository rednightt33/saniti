"""G14: DuckDB first. A result too large for one pandas frame in the session's memory is refused before anything is
loaded (MaterializationLimitExceeded), the session and its data stay, and the opened session and requests() say per
dataset whether load() may read it whole (DIRECT) or it must be reduced in DuckDB first (AGGREGATE_FIRST). A need of
the same request with the same data contract reuses the bundle instead of extracting it again."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.sessions import FRAME_DEFAULT_BYTES, FRAME_TYPE_BYTES, frame_estimate, frame_type_bytes
from conftest import requires_root


@pytest.fixture
def runtime():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
    import duckdb

    import saniti_session

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE prices AS SELECT 'T' || (i % 50) AS ticker, DATE '2020-01-01' + (i // 50)::INTEGER AS "
                "date, i * 1.0 AS close, i AS volume FROM range(20000) t(i)")
    saniti_session._CONNECTION = con
    saniti_session.REQUESTS.clear()
    saniti_session.REQUESTS.update({"g_A": {
        "data_request_id": "g_A", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
        "columns": ["ticker", "date", "close", "volume"], "entity_column": "ticker", "time_column": "date",
        "rows": 20000, "ranges": [{"range_id": "all", "start": "2020-01-01", "end": "2021-12-31",
                                   "extract_from": "2020-01-01", "extract_to": "2021-12-31"}]}})
    saniti_session._ACCESS.clear()
    saniti_session._WARNINGS.clear()
    saniti_session._FRAMES.clear()
    # one row of prices is about 72 + 64 + 8 + 8 = 152 bytes; 1 MB holds about 6,900 rows
    saniti_session._FRAMES.update({"budget_mb": 1, "budget_bytes": 1 << 20, "type_bytes": FRAME_TYPE_BYTES,
                                   "default_bytes": FRAME_DEFAULT_BYTES})
    yield saniti_session
    saniti_session._FRAMES.clear()
    saniti_session._CONNECTION = None
    con.close()


def test_a_frame_over_the_budget_is_refused_before_it_is_loaded(runtime) -> None:
    with pytest.raises(runtime.MaterializationLimitExceeded) as refused:
        runtime.load("g_A")
    message = str(refused.value)
    assert "load('g_A')" in message and "Nothing was loaded" in message
    assert "GROUP BY ticker, date" in message and "Do not prepare the data again" in message
    assert runtime._ACCESS == []  # nothing was read, so nothing counts as processed
    assert runtime._WARNINGS[-1]["code"] == "MATERIALIZATION_LIMIT_EXCEEDED"
    with pytest.raises(runtime.MaterializationLimitExceeded):
        runtime.range("g_A", "all")
    with pytest.raises(runtime.MaterializationLimitExceeded):
        runtime.sql("SELECT * FROM prices")


def test_the_reduced_result_is_materialized(runtime) -> None:
    daily = runtime.sql("SELECT ticker, sum(volume) AS volume FROM prices GROUP BY ticker")
    assert len(daily) == 50
    narrow = runtime.load("g_A", columns=["close"])  # 8 bytes a row: 20,000 rows fit 1 MB
    assert len(narrow) == 20000


def test_requests_say_how_each_dataset_may_be_materialized(runtime) -> None:
    [prices] = runtime.requests()
    assert prices["materialize"] == "AGGREGATE_FIRST" and prices["frame_budget_mb"] == 1
    assert prices["frame_mb"] > 1
    runtime._FRAMES.update(budget_mb=64, budget_bytes=64 << 20)
    assert runtime.requests()[0]["materialize"] == "DIRECT"
    runtime._FRAMES.clear()  # without a budget (an older session.json) nothing changes
    assert "materialize" not in runtime.requests()[0] and len(runtime.load("g_A")) == 20000


def test_the_estimate_shown_before_code_uses_the_same_type_table() -> None:
    assert [frame_type_bytes(t) for t in ("bigint", "double precision", "date", "text", "boolean", "numeric")] == \
        [8, 8, 64, 72, 1, 8]
    small = frame_estimate(1_000, ["text", "date", "numeric"], 819)
    big = frame_estimate(5_000_000, ["text", "date", "numeric", "numeric", "text"], 819)
    assert small["materialize"] == "DIRECT" and big["materialize"] == "AGGREGATE_FIRST"
    assert big["frame_mb"] == round(5_000_000 * (72 + 64 + 8 + 8 + 72) / (1 << 20), 1)


@requires_root
def test_the_session_shows_the_estimate_and_a_refusal_keeps_the_data(make_service, governor) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from dataneed_fixtures import data_need_catalog
    from test_dataneed_bundles import HEADERS, approve, build, ytd_parts

    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        need = approve(env)
        bundle = build(env, need, ytd_parts(env, need)).json()
        opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                   "bundle_id": bundle["input_bundle_id"]}, headers=HEADERS).json()
        assert all(d["materialize"] == "DIRECT" and d["frame_budget_mb"] == service.settings.frame_budget_mb
                   for d in opened["datasets"])
        execute = f"/v1/sessions/{opened['session_id']}/execute"
        client.post(execute, json={"request_id": "req_bundle_1", "code": "prices = load('prices')"},
                    headers=HEADERS)
        refused = client.post(execute, json={"request_id": "req_bundle_1",
                                             "code": "raise saniti.MaterializationLimitExceeded('too large')"},
                              headers=HEADERS).json()
        assert refused["status"] == "SCRIPT_ERROR" and refused["error_type"] == "MaterializationLimitExceeded"
        assert refused["next_action"] == "AGGREGATE_IN_SQL"
        assert "PREPARE_DATA_BUNDLE" in refused["forbidden_actions"]
        after = client.post(execute, json={"request_id": "req_bundle_1", "code": "print(len(prices) > 0)"},
                            headers=HEADERS).json()
        assert after["status"] == "OK" and after["stdout"].strip() == "True"  # the session and its variables stay
    finally:
        env["dataneed"].sessions.stop()


@requires_root
def test_a_need_prepared_again_in_its_request_gets_its_bundle_back(make_service, governor) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from dataneed_fixtures import data_need_catalog
    from test_conversation_reuse import approve as approve_in_conversation
    from test_conversation_reuse import post
    from test_dataneed_bundles import build, ytd_parts

    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_ENABLE_CONVERSATION_REUSE="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    try:
        first = approve_in_conversation(env, "req_same")
        bundle = build(env, first, ytd_parts(env, first), request_id="req_same").json()
        assert bundle["status"] == "READY"
        extracted = len(governor.datasets)
        again = approve_in_conversation(env, "req_same")  # the same spec again: the same approved need
        assert again["need_id"] == first["need_id"]
        reused = post(env, "/v1/bundles/reuse", {"request_id": "req_same", "need_id": again["need_id"]}).json()
        assert reused["status"] == "READY" and reused["input_bundle_id"] == bundle["input_bundle_id"], reused
        assert reused["replayed"] is True and "already prepared in this request" in reused["note"]
        assert len(governor.datasets) == extracted  # no new extraction
    finally:
        env["dataneed"].sessions.stop()
