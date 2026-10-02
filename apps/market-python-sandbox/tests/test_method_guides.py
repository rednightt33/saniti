"""Method guides (G2_G3_REACTIVATION_PLAN.md 4b, 2026-10-02): the menu and manual the model reads must match the code.
Every input a guide lists for a helper is a parameter of that helper with the same default, every runnable example
runs in a real session, the copy in market-ai-orc and the migration hold the same guides, and the runtime reports
their hash."""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import method_guides as G
from app.event_study_validation import EVENT_STUDY_VERSION
from app.main import create_app
from conftest import requires_root
from dataneed_fixtures import data_need_catalog
from test_dataneed_bundles import HEADERS, approve, build, ytd_parts

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import event_study as runtime_event_study  # noqa: E402
import saniti_session  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
MISSING = object()


def test_every_helper_input_is_a_parameter_with_its_default() -> None:
    for guide in G.GUIDES:
        for helper in guide["helpers"]:
            signature = inspect.signature(getattr(saniti_session, helper))
            listed = {i["name"]: i for i in guide["inputs"] if i.get("of") == helper}
            assert set(listed) == set(signature.parameters), (guide["name"], helper)
            for name, parameter in signature.parameters.items():
                default = MISSING if parameter.default is inspect.Parameter.empty else parameter.default
                assert listed[name].get("default", MISSING) == default, (guide["name"], helper, name)
        assert {i.get("of") for i in guide["inputs"] if i.get("of")} <= set(guide["helpers"]), guide["name"]


def test_the_guides_are_complete_and_cover_the_four_paths() -> None:
    assert sorted(g["g"] for g in G.GUIDES if g["kind"] == "PATH") == ["G1", "G2", "G3", "G4"]
    for guide in G.GUIDES:
        for key in ("title", "use_when", "avoid_when", "limits", "results", "common_errors"):
            assert guide[key], (guide["name"], key)
        assert guide["verification"]["level"] in G.VERIFICATION_LEVELS
        assert guide["verification"]["checked"] and guide["verification"]["not_checked"], guide["name"]
        entry = G.menu_entry(guide)
        assert entry["sha256"] == G.guide_sha256(guide) and entry["version"] == G.GUIDES_VERSION
    assert G.GUIDES_SHA256 == G.guides_sha256() and len(G.GUIDES_SHA256) == 64


def test_the_event_study_guide_names_the_code_policies() -> None:
    guide = G.by_name()["event_study"]
    text = str(guide)
    for value in (*runtime_event_study.OVERLAP_POLICIES, *runtime_event_study.BASELINES):
        assert value in text
    for column in runtime_event_study.SUMMARY_COLUMNS:
        assert column in guide["results"], column
    assert EVENT_STUDY_VERSION == runtime_event_study.VERSION


def test_the_orchestrator_copy_is_identical() -> None:
    other = HERE.parent / "market-ai-orc" / "app" / "method_guides.py"
    if other.exists():  # in the monorepo; each service builds from its own directory
        assert other.read_bytes() == (HERE / "app" / "method_guides.py").read_bytes()


def test_the_migration_holds_the_guides_of_the_code() -> None:
    repo = HERE.parents[1]
    script = repo / "scripts" / "generate_ai_method_guide_migration.py"
    if not script.exists():
        pytest.skip("outside the monorepo")
    spec = importlib.util.spec_from_file_location("generate_ai_method_guide_migration", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.target().read_text(encoding="utf-8") == module.render(), \
        "regenerate with scripts/generate_ai_method_guide_migration.py (a new guides version is a new forward migration)"
    # the applied creation migration is frozen: it still holds the version 1 table and registration
    assert "CREATE TABLE public.\"AI_method_guide\"" in module.CREATE_TARGET.read_text(encoding="utf-8")


@pytest.fixture
def guided(make_service, governor):
    governor.catalog = data_need_catalog()
    service = make_service(start=False, PY_SANDBOX_DATANEED_ENABLED="true", PY_SANDBOX_RESEARCH_FINDINGS_ENABLED="true")
    client = TestClient(create_app(service.settings, service=service, run_workers=False))
    env = {"api": client, "governor": governor, "dataneed": client.app.state.dataneed, "service": service}
    yield env
    env["dataneed"].sessions.stop()


@requires_root
def test_the_runtime_reports_the_guides_and_every_runnable_example_runs(guided) -> None:
    runtime = guided["api"].get("/v1/runtime", headers=HEADERS).json()
    assert runtime["method_guides"] == {"enabled": True, "version": G.GUIDES_VERSION, "sha256": G.GUIDES_SHA256}
    assert runtime["event_study"] == {"enabled": True, "version": EVENT_STUDY_VERSION}
    examples = [(g["name"], e) for g in G.GUIDES for e in g["examples"] if e["runnable"]]
    assert {name for name, _ in examples} >= {"free_code", "event_study", "hypothesis_plan", "period_return",
                                              "reading_data"}
    need = approve(guided)
    bundle = build(guided, need, ytd_parts(guided, need)).json()
    for name, example in examples:
        opened = guided["api"].post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                          "bundle_id": bundle["input_bundle_id"]}, headers=HEADERS)
        assert opened.status_code == 200, opened.text
        session_id = opened.json()["session_id"]
        body = guided["api"].post(f"/v1/sessions/{session_id}/execute",
                                  json={"request_id": "req_bundle_1", "code": example["code"]}, headers=HEADERS).json()
        assert body["status"] == "OK", (name, example["title"], body)
        guided["api"].post(f"/v1/sessions/{session_id}/close", json={"request_id": "req_bundle_1"}, headers=HEADERS)
