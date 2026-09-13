from __future__ import annotations

from app.compaction import compact_result


def test_compaction_keeps_summary_and_ordered_extremes() -> None:
    payload = {"rows": [{"ticker": f"T{i:03}", "score": i} for i in range(500)], "query_hash": "abc"}
    compact, tokens, changed = compact_result(payload, max_rows=20, max_bytes=100_000, max_tokens=10_000)
    assert changed is True
    assert compact["total_rows"] == 500
    assert compact["selection"]["method"] == "ordered_top_and_bottom"
    assert compact["rows"][0]["ticker"] == "T000"
    assert compact["rows"][-1]["ticker"] == "T499"
    assert tokens > 0


def test_byte_budget_uses_semantic_summary_not_broken_json() -> None:
    payload = {"rows": [{"ticker": f"T{i}", "detail": "x" * 500, "score": i} for i in range(100)]}
    compact, _, changed = compact_result(payload, max_rows=100, max_bytes=2000, max_tokens=600)
    assert changed is True
    assert compact["selection"]["method"] == "semantic_summary"
    assert compact["total_rows"] == 100
