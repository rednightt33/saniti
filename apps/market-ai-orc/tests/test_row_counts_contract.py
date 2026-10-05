"""P32 (2026-10-05): the row counts the tool descriptions name are the fields the sandbox's real bundle view returns
(contract test on apps/market-python-sandbox/app/bundles.py model_view, the M68 pattern)."""
from __future__ import annotations

import pytest

from app.tools.data_planner import PREPARE_BUNDLE_DESCRIPTION
from app.tools.session import OPEN_DESCRIPTION, RUN_DESCRIPTION

pytest.importorskip("pyarrow")
from test_analysis_tools import sandbox_module  # noqa: E402


def manifest() -> dict:
    ranges = [{"range_id": "test", "requested_start": "2020-01-02", "requested_end": "2026-10-02",
               "extract_from": "2019-09-20", "extract_to": "2026-10-02", "actual_start": "2020-01-02",
               "actual_end": "2026-10-02", "rows": 1623, "buffer_rows_before": 70, "buffer_rows_after": 0,
               "entities": 1, "status": "OK"}]
    dataset = {"data_request_id": "r1", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
               "rows": 1693, "columns": [{"name": "close"}], "partitions": [], "quality_manifest_id": "q",
               "quality": {"rows": 1693, "rows_in_ranges": 1623, "requested_ranges": ranges}}
    return {"status": "READY", "input_bundle_id": "b", "need_id": "n", "request_group_id": "g", "revision": 1,
            "datasets": [dataset], "expires_at": "2026-10-06T00:00:00Z"}


def test_the_bundle_view_names_the_span_of_every_row_count() -> None:
    view = sandbox_module("bundles").model_view(manifest())
    dataset = view["datasets"][0]
    assert (dataset["rows_extracted"], dataset["rows_in_ranges"]) == (1693, 1623)
    assert dataset["ranges"][0]["buffer_rows_before"] == 70 and dataset["ranges"][0]["rows"] == 1623
    assert "rows_in_ranges" in view["row_counts"]
    for field in ("rows_extracted", "rows_in_ranges"):
        assert field in PREPARE_BUNDLE_DESCRIPTION and field in OPEN_DESCRIPTION
    assert "in_period" in RUN_DESCRIPTION
