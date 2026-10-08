"""EXEC-W A4 (M122 items 1 and 3, user decision 2026-10-08): the registry reads a value the model wrote as text where the
tool's schema expects another JSON type ("null", "[...]", "20"), and a refusal names the expected type and the sibling
field a value belongs to. The arguments below are the ones the audit store recorded for the six answers that reached the
repair budget (2026-09-30..10-05)."""
from __future__ import annotations

import json

from app.tools.catalog import DiscoverArguments
from app.tools.library import ResearchLibraryArgs
from app.tools.lineage import GetLineageArgs
from app.tools.registry import ToolRegistry, ToolSpec, decode_text_values


def registry_with(name: str, model) -> tuple[ToolRegistry, list]:
    seen: list = []
    registry = ToolRegistry()
    registry.register(ToolSpec(name=name, description=name, arguments_model=model,
                               handler=lambda arguments: seen.append(arguments) or {"status": "OK"}))
    return registry, seen


def test_text_null_and_text_numbers_are_read_as_json_for_discover_catalog() -> None:
    registry, seen = registry_with("discover_catalog", DiscoverArguments)
    logged = {"query": "daily price volume stock", "data_domain": "MARKET", "entity_type": "STOCK",
              "asset_type": "null", "page_size": "20", "cursor": "null"}  # ma-golden-20261002c g6 m4a
    outcome = registry.execute("c1", "discover_catalog", json.dumps(logged))
    assert outcome.ok, outcome.output
    [arguments] = seen
    assert arguments.cursor is None and arguments.asset_type is None and arguments.page_size == 20
    assert set(outcome.output["text_values_decoded"]) == {"asset_type", "page_size", "cursor"}


def test_a_list_written_as_text_is_read_as_a_list() -> None:
    registry, seen = registry_with("get_research_library", ResearchLibraryArgs)
    logged = {"method_ids": "[\"streak_persistence\", \"conditional_distribution\"]"}  # ma-suite20 r02
    outcome = registry.execute("c1", "get_research_library", json.dumps(logged))
    assert outcome.ok, outcome.output
    assert seen[0].method_ids == ["streak_persistence", "conditional_distribution"]


def test_text_that_is_not_the_expected_type_stays_and_is_refused_with_the_type() -> None:
    registry, _ = registry_with("get_research_library", ResearchLibraryArgs)
    outcome = registry.execute("c1", "get_research_library", json.dumps({"method_ids": "streak_persistence"}))
    assert not outcome.ok
    message = outcome.output["error"]["message"]
    assert "expected JSON array" in message and "send the value itself, not as text" in message


def test_a_value_in_the_form_of_a_sibling_field_is_named() -> None:
    registry, _ = registry_with("get_lineage", GetLineageArgs)
    logged = {"ref": None, "output_id": "out.o35", "execution_id": None}  # ma-golden-20261004a g5 turn 8
    outcome = registry.execute("c1", "get_lineage", json.dumps(logged))
    assert not outcome.ok
    assert "this value has the form of ref: put it in ref" in outcome.output["error"]["message"]


def test_a_real_string_field_keeps_the_word_null_out_of_reach_only_when_nullable() -> None:
    schema = {"type": "object", "properties": {"note": {"type": "string"}, "tag": {"type": ["string", "null"]}}}
    data = {"note": "null", "tag": "NULL"}
    assert decode_text_values(schema, data) == ["tag"] and data == {"note": "null", "tag": None}
