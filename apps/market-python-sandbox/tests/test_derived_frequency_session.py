"""IP2 solution 1 end to end in a real confined session: a weekly DataNeedSpec approved with the derived-frequency
flag carries the resample semantics version into the bundle and the session; saniti.resample() leaves a bounded trace;
the final status records how the weekly figures were derived (frequencies, period policy, contract hash, input
checksum, execution ids)."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, prices, ytd_spec
from test_dataneed_bundles import HEADERS, approve, build, ytd_parts

pytestmark = requires_root

CODE = """
daily = saniti.load('prices')
banks = load('stock_classification')
weekly = saniti.resample(daily, 'prices')
returns = saniti.resampled_returns(weekly, 'prices')
emit_table('weekly_returns', returns[returns['period_complete']].head(50), definition={})
"""


@pytest.fixture
def weekly(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true",
                           PY_SANDBOX_DERIVED_FREQUENCY_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    spec = ytd_spec(data_requests=[prices(analysis_frequency="1W", resample="WEEKLY"),
                                   ytd_spec()["data_requests"][1]])
    need = approve(env, spec)
    bundle = build(env, need, ytd_parts(env, need)).json()
    assert bundle["status"] == "READY", bundle
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS)
    assert opened.status_code == 200, opened.text
    env.update(need=need, bundle_id=bundle["input_bundle_id"], session_id=opened.json()["session_id"])
    yield env
    env["dataneed"].sessions.stop()


def test_a_weekly_analysis_records_its_derivation(weekly, caplog) -> None:
    from app.data_need import data_contract_sha256

    assert weekly["need"]["requests"]["data_request_1_A"]["resample_semantics_version"] == 1
    runtime = weekly["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["derived_frequency"] == {"enabled": True, "version": 1}
    with caplog.at_level(logging.INFO):
        body = weekly["api"].post(f"/v1/sessions/{weekly['session_id']}/execute",
                                  json={"request_id": "req_bundle_1", "code": CODE}, headers=HEADERS).json()
    assert body["status"] == "OK", body
    traces = [json.loads(r.getMessage()) for r in caplog.records if '"saniti_resample"' in r.getMessage()]
    assert len(traces) == 1 and traces[0]["target_frequency"] == "1W" and traces[0]["semantics_version"] == 1
    assert traces[0]["input_rows"] > traces[0]["rows"] > 0 and "rows_data" not in traces[0]
    result = weekly["api"].post(f"/v1/sessions/{weekly['session_id']}/complete", json={"request_id": "req_bundle_1"},
                                headers=HEADERS).json()
    assert result["status"] == "COMPLETED", result
    derived = result["final_status"]["derived_frequency"]
    [request] = derived["requests"]
    assert request == request | {"data_request_id": "data_request_1_A", "source_frequency": "1D",
                                 "analysis_frequency": "1W", "resample": "WEEKLY", "resample_semantics_version": 1,
                                 "resample_calls": 1}
    assert "Friday" in request["period_policy"] and "period_complete" in derived["completeness_rule"]
    assert derived["contract_sha256"] == data_contract_sha256(weekly["need"])
    assert derived["input_checksum"] and derived["execution_ids"] == [body["execution_id"]]


def test_without_the_flag_the_final_status_has_no_derivation(make_service, governor) -> None:
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    need = approve(env, ytd_spec(data_requests=[prices(analysis_frequency="1W", resample="WEEKLY"),
                                                ytd_spec()["data_requests"][1]]))
    assert "resample_semantics_version" not in need["requests"]["data_request_1_A"]
    assert client.get("/v1/runtime", headers=HEADERS).json()["derived_frequency"]["enabled"] is False
