"""Method guides in market-ai-orc (G2_G3_REACTIVATION_PLAN.md 4b, 2026-10-02): served only when the table, the
sandbox and this service hold the same guides; only the methods this deployment offers; the menu at the start of every
run and in get_system_capabilities; an opened manual carried in the conversation's data record in its current version;
and the tool definition equal to its Tool_Catalog row."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from app import data_record as records
from app import method_guides as G
from app.orchestrator import METHOD_MENU_HEADER, AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry
from app.tools.method_guides import active_guides, guides_problem, menu, method_guide_spec
from app.tools.system import capabilities_spec
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_dataneed_orchestrator import Tools, answer

CAPABILITY = {"enabled": True, "version": G.GUIDES_VERSION, "sha256": G.GUIDES_SHA256}
ALL = dict(dataneed=True, event_study=True, hypothesis_plan=True, multi_angle=True, period_return=True)


def stored_rows() -> list[dict]:
    return [{**row, "guides_sha256": G.GUIDES_SHA256} for row in copy.deepcopy(G.rows())]


def test_the_guides_are_served_only_when_table_sandbox_and_code_agree() -> None:
    assert guides_problem(stored_rows(), CAPABILITY) is None
    assert "does not report" in guides_problem(stored_rows(), None)
    assert "differ" in guides_problem(stored_rows(), {**CAPABILITY, "sha256": "0" * 64})
    assert "apply its forward migration" in guides_problem(stored_rows()[1:], CAPABILITY)
    edited = stored_rows()
    edited[0]["guide"] = {**edited[0]["guide"], "title": "edited by hand"}
    assert "differs from its hash" in guides_problem(edited, CAPABILITY)


def test_only_the_methods_this_deployment_offers_are_listed() -> None:
    assert active_guides(**ALL) == [g["name"] for g in G.GUIDES]
    plain = active_guides(**{**ALL, "event_study": False, "hypothesis_plan": False, "multi_angle": False,
                             "period_return": False})
    assert plain == ["free_code", "resample", "join_and_preaggregate", "reading_data"]
    assert active_guides(**{**ALL, "dataneed": False}) == []


def test_the_tool_opens_a_guide_a_library_method_or_names_what_exists() -> None:
    spec = method_guide_spec(["free_code", "event_study"], library_rows=[{"method_id": "lead_lag", "x": 1,
                                                                         "library_sha256": "a" * 64}])
    opened = spec.handler(spec.arguments_model(name="event_study"))
    assert opened["guide"] == G.by_name()["event_study"] and opened["sha256"] == G.guide_sha256(opened["guide"])
    assert list(opened["verification_levels"]) == ["FORMULA_AND_STATISTICS_VERIFIED"]
    library = spec.handler(spec.arguments_model(name="lead_lag"))
    assert library["research_library_method"] == {"method_id": "lead_lag", "x": 1}
    refused = spec.handler(spec.arguments_model(name="multi_angle"))  # not offered here
    assert refused["code"] == "UNKNOWN_METHOD" and refused["available"] == ["event_study", "free_code", "lead_lag"]


def test_the_tool_definition_is_its_tool_catalog_row() -> None:
    script = Path(__file__).resolve().parents[3] / "scripts" / "generate_ai_method_guide_migration.py"
    if not script.exists():
        return  # outside the monorepo
    module_spec = importlib.util.spec_from_file_location("generate_ai_method_guide_migration", script)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    registry = ToolRegistry()
    registry.register(method_guide_spec(["free_code"]))
    [definition] = registry.definitions()
    assert definition["parameters"] == module.TOOL_INPUT
    assert definition["description"] == module._load_description()


def guided_registry(names: list[str]) -> ToolRegistry:
    registry = Tools([]).registry()
    registry.register(method_guide_spec(names))
    registry.register(capabilities_spec(registry))
    registry.method_guides = {"names": names, "menu": menu(names)}
    return registry


def run(script: list, record: dict | None = None, names: list[str] | None = None):
    scripted = ScriptedClient(script)
    registry = guided_registry(names or ["free_code", "event_study"])
    orchestrator = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted, registry)
    result = orchestrator.run(AgentRunRequest(request_id="mg", message="Halo"), data_record=record)
    return result, scripted


def notes(payload: dict) -> list[str]:
    return [i.get("content") for i in payload["input"] if isinstance(i, dict) and isinstance(i.get("content"), str)]


def test_the_menu_starts_every_run_and_an_opened_manual_is_carried() -> None:
    first, scripted = run([tool_call_response("get_method_guide", json.dumps({"name": "event_study"}),
                                              call_id="c1"), final_response(answer("Halo."))])
    menu_note = next(n for n in notes(scripted.payloads[0]) if n.startswith(METHOD_MENU_HEADER))
    assert '"name": "event_study"' in menu_note.replace('":"', '": "') or '"event_study"' in menu_note
    assert "MaterializationLimitExceeded" not in menu_note  # the menu is layer one, not the manual
    record = first.data_record
    assert [m["name"] for m in record["manuals"]] == ["event_study"]
    # the next turn (or mode 4 step) gets the manual without opening it again
    second, scripted = run([final_response(answer("Halo."))], record=record)
    carried = next(n for n in notes(scripted.payloads[0]) if n.startswith(records.MANUALS_HEADER))
    assert "CALCULATION_MISMATCH" in carried and second.data_record["manuals"][0]["name"] == "event_study"


def test_a_manual_of_an_older_version_is_replaced_and_one_no_longer_offered_is_left_out() -> None:
    record = records.empty()
    records.add_manual(record, "r0", name="event_study", version=0, sha256="0" * 64, guide={"name": "event_study"})
    records.add_manual(record, "r0", name="multi_angle", version=1, sha256="1" * 64, guide={"name": "multi_angle"})
    result, scripted = run([final_response(answer("Halo."))], record=record)
    carried = next(n for n in notes(scripted.payloads[0]) if n.startswith(records.MANUALS_HEADER))
    assert "CALCULATION_MISMATCH" in carried and "multi_angle" not in carried
    entry = next(m for m in result.data_record["manuals"] if m["name"] == "event_study")
    assert entry["sha256"] == G.guide_sha256(G.by_name()["event_study"])


def test_capabilities_list_the_menu() -> None:
    registry = guided_registry(["free_code"])
    capabilities = registry.get("get_system_capabilities").handler(None)
    assert [m["name"] for m in capabilities["analysis_methods"]] == ["free_code"]


def test_without_the_guides_nothing_is_added() -> None:
    scripted = ScriptedClient([final_response(answer("Halo."))])
    AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted, Tools([]).registry()).run(
        AgentRunRequest(request_id="mg", message="Halo"))
    assert not any(n.startswith(METHOD_MENU_HEADER) for n in notes(scripted.payloads[0]))


def test_a_large_set_of_manuals_is_bounded_with_a_visible_marker() -> None:
    record = records.empty()
    current = {}
    for index in range(10):
        guide = {"name": f"g{index}", "text": "x" * 3000}
        sha = f"{index:064d}"
        records.add_manual(record, "r", name=f"g{index}", version=1, sha256=sha, guide=guide)
        current[f"g{index}"] = {"sha256": sha, "version": 1, "guide": guide}
    note, _ = records.manuals_note(record, current)
    assert len(note) <= records.MAX_MANUAL_NOTE_CHARS and "more opened earlier, not shown here" in note
    assert "- g9 " in note  # newest first


def test_startup_reads_and_checks_the_guides() -> None:
    from contextlib import contextmanager

    from app.main import _method_guides

    class Catalog:
        def __init__(self, rows):
            self.rows = rows

        @contextmanager
        def read_only(self):
            yield lambda sql, params: self.rows

    class Sandbox:
        def __init__(self, capability):
            self.capability = capability

        def runtime(self):
            return {"method_guides": self.capability}

    flags = dict(dataneed=True, event_study=False, hypothesis_plan=False, multi_angle=True, period_return=False)
    guides, _ = _method_guides(Sandbox(CAPABILITY), Catalog(stored_rows()), **flags)
    assert guides["names"] == ["free_code", "multi_angle", "resample", "join_and_preaggregate", "reading_data"]
    assert [m["name"] for m in guides["menu"]] == guides["names"]
    none, reason = _method_guides(Sandbox(None), Catalog(stored_rows()), **flags)
    assert none is None and "does not report" in reason
