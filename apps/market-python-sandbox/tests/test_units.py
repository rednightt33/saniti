"""Configuration, request schema, source screen, seccomp program, and helper tests (no child process)."""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from app.config import ConfigError, Settings
from app.models import AnalysisRequest, next_action
from app.policy import check_source
from conftest import ACCESS_KEY, API_KEY, base_env

DS = "ds_" + "a" * 24


def test_defaults_match_the_reviewed_starting_points(sandbox_root) -> None:
    s = Settings.from_env(base_env(sandbox_root, PY_SANDBOX_MAX_RUNTIME_SECONDS="120",
                                   PY_SANDBOX_SUBMIT_WAIT_SECONDS="25", PY_SANDBOX_MAX_POLL_WAIT_SECONDS="20"))
    assert (s.max_datasets, s.max_code_chars, s.max_runtime_seconds, s.max_memory_mb) == (4, 20000, 120, 2048)
    assert (s.max_table_preview_rows, s.max_charts, s.max_artifacts, s.result_retention_hours) == (50, 8, 8, 24)
    assert s.max_virtual_memory_mb == 4096 and s.concurrency == 1 and s.require_isolation is True
    assert s.dataset_url_schemes == ("file",)
    assert Settings.from_env({**base_env(sandbox_root), "PY_SANDBOX_DATASET_URL_SCHEMES": ""} | {
        "PY_SANDBOX_DATASET_URL_SCHEMES": "https"}).dataset_url_schemes == ("https",)
    assert API_KEY not in repr(s) and ACCESS_KEY not in repr(s)


def test_there_are_no_database_or_bucket_settings() -> None:
    names = " ".join(Settings.__dataclass_fields__).lower()
    for forbidden in ("database", "postgres", "bucket", "secret_access", "access_key_id"):
        assert forbidden not in names


@pytest.mark.parametrize(("overrides", "message"), [
    ({"PY_SANDBOX_API_KEY": "short"}, "at least 32"),
    ({"SQL_GOVERNOR_DATASET_ACCESS_KEY": API_KEY}, "must differ"),
    ({"SQL_GOVERNOR_URL": "ftp://x"}, "http"),
    ({"PY_SANDBOX_DATASET_URL_SCHEMES": "https,s3"}, "subset"),
    ({"PY_SANDBOX_MAX_CODE_CHARS": "50000"}, "between 100 and 20000"),
    ({"PY_SANDBOX_MAX_MEMORY_MB": "4096", "PY_SANDBOX_MAX_VIRTUAL_MEMORY_MB": "2048"}, "between 4096"),
    ({"PY_SANDBOX_MAX_TABLE_PREVIEW_ROWS": "100", "PY_SANDBOX_MAX_TABLE_OUTPUT_ROWS": "50"}, "must not exceed"),
    ({"PY_SANDBOX_REQUIRE_ISOLATION": "maybe"}, "true or false"),
])
def test_invalid_configuration_is_rejected(sandbox_root, overrides: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(base_env(sandbox_root, **overrides))


def request(**overrides) -> dict:
    return {"request_id": "r1", "purpose": "p", "dataset_ids": [DS], "python_code": "x = 1",
            "expected_outputs": ["TABLE"], **overrides}


@pytest.mark.parametrize("bad", [
    {"purpose": "x" * 1001}, {"dataset_ids": []}, {"dataset_ids": [DS, DS]}, {"dataset_ids": ["ds_123"]},
    {"python_code": "x" * 20001}, {"python_code": ""}, {"expected_outputs": ["TEXT"]},
    {"expected_outputs": ["TABLE", "TABLE"]}, {"expected_outputs": []}, {"max_runtime_seconds": 999},
    {"request_id": "bad id!"},
])
def test_request_schema_is_strict(bad: dict) -> None:
    with pytest.raises(ValueError):
        AnalysisRequest.model_validate(request(**bad))


def test_next_action_is_deterministic() -> None:
    assert next_action("COMPLETED", None) == "USE_ANALYSIS_RESULT"
    assert next_action("RUNNING", None) == next_action("QUEUED", None) == "GET_ANALYSIS_RESULT"
    assert next_action("FAILED", "DATASET_EXPIRED") == "REQUEST_DATA_AGAIN"
    assert next_action("FAILED", "INSUFFICIENT_HISTORY") == "REVISE_ANALYSIS"
    assert next_action("FAILED", "SANDBOX_RESTARTED") == "REPORT_LIMITATION"
    assert next_action("FAILED", "INPUT_LIMIT_EXCEEDED") == "REVISE_DATA_REQUEST"


@pytest.mark.parametrize(("source", "code"), [
    ("def f(:\n  pass", "SYNTAX_ERROR"),
    ("import subprocess", "FORBIDDEN_IMPORT"),
    ("import socket", "FORBIDDEN_IMPORT"),
    ("from urllib.request import urlopen", "FORBIDDEN_IMPORT"),
    ("import requests", "FORBIDDEN_IMPORT"),
    ("import httpx", "FORBIDDEN_IMPORT"),
    ("import multiprocessing.pool", "FORBIDDEN_IMPORT"),
    ("import ctypes", "FORBIDDEN_IMPORT"),
    ("import psycopg", "FORBIDDEN_IMPORT"),
    ("import boto3", "FORBIDDEN_IMPORT"),
    ("import os\nos.system('id')", "FORBIDDEN_OPERATION"),
    ("import os\nprint(os.environ)", "FORBIDDEN_OPERATION"),
    ("from os import fork", "FORBIDDEN_OPERATION"),
    ("__import__('socket')", "FORBIDDEN_OPERATION"),
    ("x = (" * 300 + ")" * 300, "SYNTAX_ERROR"),
])
def test_source_screen_rejects_clearly_dangerous_code(source: str, code: str) -> None:
    violation = check_source(source)
    assert violation is not None and violation.code == code


def test_source_screen_allows_ordinary_analysis() -> None:
    source = ("import numpy as np, pandas as pd, polars as pl, duckdb, talib, scipy.stats as st\n"
              "import statsmodels.api as sm\nimport matplotlib.pyplot as plt\nimport os.path\n"
              "from saniti import load_dataset, iter_series, emit_table\n")
    assert check_source(source) is None


def test_seccomp_program_shape() -> None:
    import seccomp

    program = seccomp.build_filter()
    assert 20 < len(program) < 4096 and all(len(i) == 8 for i in program)
    for name in ("execve", "fork", "ptrace", "bpf", "io_uring_setup", "unshare", "mount"):
        assert name in seccomp.DENIED.values()


# ---------------------------------------------------------------- saniti helpers (in-process)

@pytest.fixture
def helpers(tmp_path):
    import saniti

    saniti._INDEX.clear()
    saniti._WARNINGS.clear()
    for key in saniti._COUNTS:
        saniti._COUNTS[key] = 0
    saniti._configure({"datasets": {}, "seed": 0, "expected_outputs": ["TABLE", "METRICS", "CHART", "ARTIFACT"],
                       "limits": {"max_tables": 2, "max_metrics": 2, "max_charts": 1, "max_artifacts": 1,
                                  "max_table_output_rows": 100, "max_table_preview_rows": 5,
                                  "max_metrics_bytes": 500, "max_artifact_bytes": 1 << 20}}, str(tmp_path))
    return saniti


def panel():
    return pd.DataFrame({"t": ["B", "A", "B", "A", "A", "C"],
                         "d": pd.to_datetime(["2026-01-02", "2026-01-02", "2026-01-01", "2026-01-01", "2026-01-03",
                                              "2026-01-01"]),
                         "v": [2.0, 20.0, 1.0, 10.0, 30.0, None]})


def test_iter_series_separates_and_orders_each_entity(helpers) -> None:
    got = {k: list(g["v"]) for k, g in helpers.iter_series(panel(), "t", "d", min_history=2)}
    assert got == {"A": [10.0, 20.0, 30.0], "B": [1.0, 2.0]}          # sorted by date, never mixed
    assert helpers._WARNINGS[-1]["code"] == "INSUFFICIENT_HISTORY" and "C" in helpers._WARNINGS[-1]["message"]


def test_minimum_history_and_duplicates_are_explicit(helpers) -> None:
    with pytest.raises(helpers.InsufficientHistory):
        list(helpers.iter_series(panel(), "t", "d", min_history=10))
    dup = pd.concat([panel(), panel().iloc[[0]]])
    with pytest.raises(helpers.DuplicateObservations):
        helpers.prepare_panel(dup, "t", "d")
    kept = helpers.prepare_panel(dup, "t", "d", on_duplicate="keep_last")
    assert len(kept) == len(panel()) and helpers._WARNINGS[-1]["code"] == "DUPLICATES_RESOLVED"
    report = helpers.panel_check(panel(), "t", "d", ["v"])
    assert report["entities_not_date_ordered"] == 2 and report["null_values"] == {"v": 1}
    assert helpers.prepare_panel(panel(), "t", "d")["v"].isna().sum() == 1   # never filled


def test_emit_writes_a_bounded_index(helpers, tmp_path) -> None:
    helpers.emit_table("screen", pd.DataFrame({"x": range(20), "when": pd.date_range("2026-01-01", periods=20)}))
    helpers.emit_metrics({"n": 20, "mean": float("nan"), "nested": {"a": [1, 2]}})
    index = json.loads((tmp_path / "index.json").read_text())
    table, metrics = index["outputs"]
    assert table["row_count"] == 20 and len(table["preview_rows"]) == 5 and table["preview_rows"][0][1].startswith("2026")
    assert metrics["values"] == {"n": 20, "mean": None, "nested": {"a": [1, 2]}}
    assert os.path.exists(tmp_path / "table_1.parquet")
    with pytest.raises(helpers.OutputLimitExceeded):
        helpers.emit_table("big", pd.DataFrame({"x": range(101)}))
    with pytest.raises(helpers.OutputLimitExceeded):
        helpers.emit_metrics({"k": "x" * 600, "l": list(range(100))})


def test_undeclared_outputs_are_refused(helpers) -> None:
    helpers._EXPECTED.discard("CHART")
    with pytest.raises(helpers.UndeclaredOutput):
        helpers.emit_chart()
