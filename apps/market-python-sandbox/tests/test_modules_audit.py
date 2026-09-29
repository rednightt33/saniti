"""Item C (EXTRACTION_AND_AUDIT_PLAN.md): every execution records the modules its code imports, read from the syntax
tree without running it; with PY_SANDBOX_MODULES_AUDIT_ENABLED the completion's final status lists the modules of the
session's successful executions. Without the flag the final status keeps its shape."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.sessions import imported_modules
from conftest import requires_root
from dataneed_fixtures import data_need_catalog, ytd_spec
from test_dataneed_bundles import HEADERS, REFERENCE, build, ytd_parts


def test_modules_are_read_from_the_syntax_tree() -> None:
    code = ("import pandas as pd\nimport numpy, scipy.stats\nfrom statsmodels.api import OLS\nfrom . import x\n"
            "def f():\n    import talib\n")
    assert imported_modules(code) == ["numpy", "pandas", "scipy", "statsmodels", "talib"]
    assert imported_modules("x = load('prices')") == []
    assert imported_modules("import (") == []  # code that does not parse records none


def session(make_service, governor, **flags):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", **flags)
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    body = {"request_id": "req_bundle_1", "reference_time": REFERENCE, "timezone": "Asia/Jakarta", "spec": ytd_spec()}
    result = client.post("/v1/data-needs", json=body, headers=HEADERS).json()
    need = env["dataneed"].get_need(result["need_id"])
    bundle = build(env, need, ytd_parts(env, need)).json()
    opened = client.post("/v1/sessions", json={"request_id": "req_bundle_1", "bundle_id": bundle["input_bundle_id"]},
                         headers=HEADERS).json()
    env.update(session_id=opened["session_id"])
    return env


def execute(env, code):
    return env["api"].post(f"/v1/sessions/{env['session_id']}/execute", json={"request_id": "req_bundle_1",
                                                                              "code": code}, headers=HEADERS).json()


def complete(env):
    return env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                           headers=HEADERS).json()


CODE = """
import pandas as pd
import numpy as np
from math import sqrt
prices = load('prices')
load('stock_classification')
emit_table('summary', pd.DataFrame({'n': [len(prices)], 'root': [sqrt(np.float64(4))]}))
"""


@requires_root
def test_the_final_status_lists_the_modules_of_successful_executions(make_service, governor) -> None:
    env = session(make_service, governor, PY_SANDBOX_MODULES_AUDIT_ENABLED="true")
    try:
        assert execute(env, "import json\nraise ValueError('x')")["status"] == "SCRIPT_ERROR"
        assert execute(env, CODE)["status"] == "OK"
        records = env["dataneed"].store.executions_for(env["session_id"])
        assert [r["modules"] for r in records] == [["json"], ["math", "numpy", "pandas"]]
        result = complete(env)
        assert result["status"] == "COMPLETED", result
        assert result["final_status"]["modules_used"] == ["math", "numpy", "pandas"]  # the failed run is not counted
    finally:
        env["dataneed"].sessions.stop()


@requires_root
def test_without_the_flag_the_final_status_keeps_its_shape(make_service, governor) -> None:
    env = session(make_service, governor)
    try:
        assert execute(env, CODE)["status"] == "OK"
        result = complete(env)
        assert result["status"] == "COMPLETED" and "modules_used" not in result["final_status"]
        # the execution record still carries the modules
        assert env["dataneed"].store.executions_for(env["session_id"])[0]["modules"] == ["math", "numpy", "pandas"]
    finally:
        env["dataneed"].sessions.stop()


@pytest.mark.parametrize("code", ["", "   \n"])
def test_empty_code_has_no_modules(code: str) -> None:
    assert imported_modules(code) == []
