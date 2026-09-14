from __future__ import annotations

from app.compaction import compact_result, decisive_digest


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
    assert compact.get("top_observations")
    assert compact.get("bottom_observations")


def test_decisive_digest_retains_ranked_values_and_audit_references() -> None:
    payload = {
        "table": "Feature_03_Stock_Broker_Daily",
        "rows": [
            {"ticker": "BBCA", "institutional_net_value": 10_000_000},
            {"ticker": "BBRI", "institutional_net_value": -5_000_000},
        ],
        "total_rows": 2,
        "warnings": ["classification is not investor identity"],
        "evidence_id": "evidence-1",
    }
    digest = decisive_digest("screen_features", payload, "query-abc")
    assert digest["query_hash"] == "query-abc"
    assert digest["evidence_id"] == "evidence-1"
    assert digest["warnings"] == payload["warnings"]
    assert digest["decisive_observations"] == payload["rows"]


def test_decisive_digest_normalizes_legacy_query_hash_lists() -> None:
    digest = decisive_digest("compare_periods", {"query_hash": ["a", "b"]})
    assert digest["query_hashes"] == ["a", "b"]
    assert "query_hash" not in digest
