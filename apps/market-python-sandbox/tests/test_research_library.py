"""The research library (C07, 2026-09-29): the model-facing description of the eight methods must match the code
that computes them, and stay byte-identical with market-ai-orc's copy."""
from __future__ import annotations

import sys
from pathlib import Path

from app import research_library as L
from app.research_methods import METHODS, OPTIONAL_USES, USES

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import research_engines  # noqa: E402
import research_inputs  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


def test_the_library_describes_exactly_the_registered_methods() -> None:
    rows = L.by_method()
    assert {m: r["method_family"] for m, r in rows.items()} == METHODS == research_engines.METHODS


def test_roles_and_parameters_match_the_code() -> None:
    for method_id, row in L.by_method().items():
        required = tuple(r["role"] for r in row["input_roles"] if r["required"])
        optional = tuple(r["role"] for r in row["input_roles"] if not r["required"])
        assert set(required) == set(research_inputs.ROLES[method_id]), method_id
        assert set(optional) == set(research_inputs.OPTIONAL.get(method_id, ())), method_id
        params = {p["name"] for p in row["required_parameters"]}
        optional_params = {p["name"] for p in row["optional_parameters"]}
        assert params == set(USES[method_id]) - set(OPTIONAL_USES.get(method_id, ())), method_id
        assert optional_params == set(OPTIONAL_USES.get(method_id, ())), method_id


def test_data_requirements_match_the_engines() -> None:
    rows = L.by_method()
    entity_required = {m for m, r in rows.items() if r["data_requirements"]["entity_column"] == "REQUIRED"}
    assert entity_required == {"cohort_comparison", "quantile_ranking"}  # prepare(..., entity_required=True)
    assert rows["regime_comparison"]["data_requirements"]["label"] == "CONSTANT_PER_DATE"
    assert rows["cohort_comparison"]["data_requirements"]["label"] == "CONSTANT_PER_ENTITY"
    assert L.forward_return_role("streak_persistence") is None
    assert L.forward_return_role("lead_lag") == "follower" and L.forward_return_role("quantile_ranking") == "outcome"
    assert rows["quantile_ranking"]["secondary_checks"] == ["monotonicity"]


def test_the_hash_is_stable_and_every_row_is_complete() -> None:
    assert L.LIBRARY_SHA256 == L.library_sha256() and len(L.LIBRARY_SHA256) == 64
    for row in L.rows():
        for key in ("question_shape", "interpretation", "misuse_warning", "example_question", "sample_unit"):
            assert isinstance(row[key], str) and row[key].strip(), (row["method_id"], key)


def test_the_orchestrator_copy_is_identical() -> None:
    other = HERE.parent / "market-ai-orc" / "app" / "research_library.py"
    if other.exists():  # in the monorepo; each service builds from its own directory
        assert other.read_bytes() == (HERE / "app" / "research_library.py").read_bytes()


def test_the_migration_holds_the_library_of_the_code() -> None:
    repo = HERE.parents[1]
    migration = repo / "database" / "migrations" / "20260930_001_create_ai_research_library.sql"
    if not migration.exists():  # the service image holds only its own directory
        return
    import importlib.util
    import json
    import re

    text = migration.read_text(encoding="utf-8")
    body = re.search(r"\$library\$(\[.*\])\$library\$", text, re.S)
    assert body and json.loads(body.group(1)) == L.rows()
    assert set(re.findall(r"'([0-9a-f]{64})'", text)) == {L.LIBRARY_SHA256}
    spec = importlib.util.spec_from_file_location(
        "generate_ai_research_library_migration", repo / "scripts" / "generate_ai_research_library_migration.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.render() == text, "regenerate with scripts/generate_ai_research_library_migration.py"
