"""P10 (2026-10-01, ma-steps 2-m4a): submit_data_need_spec arrived as {"data_request_id": ..., "data_need_spec":
"<the spec as JSON text>"} and was refused with 9 missing and 2 unknown fields, the shape the conversation resources
note used to show. A tool may name the key its whole argument object can be wrapped under; the object is taken out
only when no other key is one of its arguments, and is then validated like any call."""
from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from app.tools.registry import ToolRegistry, ToolSpec


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    question: str


def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec(name="submit", description="d", arguments_model=Args,
                          handler=lambda a: {"mode": a.mode, "question": a.question}, envelope_key="data_need_spec"))
    return reg


def test_an_argument_object_wrapped_under_the_envelope_key_is_taken_out() -> None:
    spec = {"mode": "ANALYSIS", "question": "q"}
    for wrapped in ({"data_need_spec": spec}, {"data_request_id": "x", "data_need_spec": json.dumps(spec)}):
        outcome = registry().execute("c1", "submit", json.dumps(wrapped))
        assert outcome.ok and outcome.output["result"] == spec
        assert outcome.output["unwrapped_arguments"]["envelope"] == "data_need_spec"


def test_anything_else_is_refused_as_before() -> None:
    reg = registry()
    assert not reg.execute("c1", "submit", json.dumps({"mode": "A", "data_need_spec": {"mode": "A",
                                                                                         "question": "q"}})).ok
    assert not reg.execute("c2", "submit", json.dumps({"data_need_spec": "not json"})).ok
    assert not reg.execute("c3", "submit", json.dumps({"data_need_spec": {"mode": "A"}})).ok  # the inner object
    assert reg.execute("c4", "submit", json.dumps({"mode": "A", "question": "q"})).ok          # a plain call


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_table_rows_are_cut_before_a_large_result_is_refused() -> None:
    """P6 (ma-steps 2-m4c): complete_research_run over its 40,000-byte limit was refused whole."""
    rows = [{"broker": f"B{i}", "value": i} for i in range(200)]
    result = {"status": "COMPLETED", "findings": [{"angle_id": "a", "estimate": 1.5}],
              "released_contents": [{"output_id": "out_1", "row_count": 200, "rows": rows}]}
    reg = ToolRegistry()
    reg.register(ToolSpec(name="complete", description="d", arguments_model=NoArgs, handler=lambda a: result,
                          max_result_bytes=2_000))
    outcome = reg.execute("c1", "complete", "{}")
    assert outcome.ok
    content = outcome.output["result"]["released_contents"][0]
    assert content["rows_truncated"] and content["read_more"] == "get_session_output" and len(content["rows"]) <= 20
    assert outcome.output["result"]["findings"] == result["findings"]  # findings are never cut
    huge = {"status": "COMPLETED", "findings": [{"angle_id": "a", "note": "x" * 5_000}]}
    reg.register(ToolSpec(name="huge", description="d", arguments_model=NoArgs, handler=lambda a: huge,
                          max_result_bytes=2_000))
    refused = reg.execute("c2", "huge", "{}")
    assert not refused.ok and "largest parts: findings" in refused.output["error"]["message"]
