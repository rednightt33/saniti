"""Write a Tool_Catalog migration from market-ai-orc's tool definitions: one entry of ROUNDS per migration, each
registering the new versions of the tools whose contract changed in that round.

- round_b (20261003_005, applied): submit_data_need_spec v7, check_data_feasibility v5, check_research_feasibility v4
  (a time range may end "LATEST", 1b / C06) and run_python v3 (event_study takes the approved outcome unit, P26).
- round_c (20261003_007): submit_data_need_spec v8, check_data_feasibility v6, check_research_feasibility v5
  (data_as_of_policy: a resumed conversation keeps its data date unless the user asks for newer data, R-STORE C2e).

Registered from the code with every switch of the dev environment on (the registry of scripts/generate_ai_tools_doc.py,
one source for both). An applied migration is frozen (database/migrations/APPLIED.sha256); market-ai-orc's
tests/test_data_need_tool.py checks the newest round against the code.

Usage: apps/market-ai-orc venv python scripts/generate_tool_catalog_migration.py [round]   (default: the newest)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sql_text import sql_json, sql_literal  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ROUNDS = {
    "round_b": {
        "target": ROOT / "database/migrations/20261003_005_round_b_tool_catalog.sql",
        "versions": {"submit_data_need_spec": ("v6", "v7"), "check_data_feasibility": ("v4", "v5"),
                     "check_research_feasibility": ("v3", "v4"), "run_python": ("v2", "v3")},
        # what each new version must carry (checked by the migration itself after the insert)
        "contracts": {"submit_data_need_spec": ("input_schema", "LATEST"),
                      "check_data_feasibility": ("input_schema", "LATEST"),
                      "check_research_feasibility": ("input_schema", "LATEST"),
                      "run_python": ("purpose", "outcome_unit=None")},
        "title": "phase B",
        "summary": ["submit_data_need_spec v7, check_data_feasibility v5, check_research_feasibility v4: a time range may "
                    "end \"LATEST\"",
                    "(1b / C06; the sandbox binds it to the reference date and the bundle reports the actual last "
                    "date).",
                    "run_python v3: event_study takes the approved experiment's outcome unit (P26)."],
        "limits": {"time_range_end": "YYYY-MM-DD or LATEST, bound to the reference date by the sandbox (1b)",
                   "outcome_unit": "event_study and event_summary use the approved experiment's outcome unit (P26)"},
    },
    "round_c": {
        "target": ROOT / "database/migrations/20261003_007_round_c_tool_catalog.sql",
        "versions": {"submit_data_need_spec": ("v7", "v8"), "check_data_feasibility": ("v5", "v6"),
                     "check_research_feasibility": ("v4", "v5")},
        "contracts": {"submit_data_need_spec": ("input_schema", "data_as_of_policy"),
                      "check_data_feasibility": ("input_schema", "data_as_of_policy"),
                      "check_research_feasibility": ("input_schema", "data_as_of_policy")},
        "title": "phase C",
        "summary": ["submit_data_need_spec v8, check_data_feasibility v6, check_research_feasibility v5:",
                    "data_as_of_policy (R-STORE C2e, user decision 4): a resumed conversation keeps its data date;",
                    "NEWEST when the user asks for newer data, and the answer states both dates."],
        "limits": {"data_as_of_policy": "CONVERSATION (default) binds LATEST to the conversation's data date; NEWEST "
                                        "to the reference date (R-STORE C2e)"},
    },
}
NEWEST = "round_c"


def _tools_doc():
    spec = importlib.util.spec_from_file_location("generate_ai_tools_doc", ROOT / "scripts/generate_ai_tools_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def definitions(round_name: str = NEWEST) -> dict[str, dict]:
    versions = ROUNDS[round_name]["versions"]
    return {name: d for name, d in _tools_doc()._registry().items() if name in versions}


def schema_text(definition: dict) -> str:
    return sql_json(definition["parameters"], sort_keys=True, separators=(",", ":"))


def render(round_name: str = NEWEST) -> str:
    spec = ROUNDS[round_name]
    VERSIONS, CONTRACTS = spec["versions"], spec["contracts"]
    found = definitions(round_name)
    assert set(found) == set(VERSIONS), found.keys()
    limits = {"design": f"ROUND_PLAN_2026-10-03.md ({spec['title']})",
              "registry_state": "registered from code (market-ai-orc) under the dev flags, inactive here",
              **spec["limits"]}
    rows = ",\n".join(
        f"    ('{name}', '{old}', '{new}', '{schema_text(found[name])}',\n"
        f"     '{sql_literal(found[name]['description'])}')"
        for name, (old, new) in VERSIONS.items())
    previous = ", ".join(f"('{n}', '{old}')" for n, (old, _) in VERSIONS.items())
    registered = " OR ".join(f"(tool_name = '{n}' AND version = '{new}')" for n, (_, new) in VERSIONS.items())
    carried = "\n       OR ".join(
        f"NOT EXISTS (SELECT 1 FROM public.\"Tool_Catalog\" WHERE tool_name = '{n}' AND version = '{VERSIONS[n][1]}'"
        f" AND {column}::text LIKE '%{sql_literal(text)}%')" for n, (column, text) in CONTRACTS.items())
    summary = "\n".join(f"-- {line}" for line in spec["summary"])
    title = spec["title"]
    return f"""-- Round 2026-10-03 {title} (ROUND_PLAN_2026-10-03.md): the tool contracts the code now offers.
{summary}
-- Inactive like every market-ai-orc row; input schema and purpose from the code, every other column copied from the
-- previous version.
-- GENERATED by scripts/generate_tool_catalog_migration.py; market-ai-orc tests/test_data_need_tool.py fails on
-- drift. Do not edit by hand.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog" WHERE (tool_name, version) IN ({previous})) <> {len(VERSIONS)} THEN
        RAISE EXCEPTION 'Expected the previous tool versions {sql_literal(previous)}';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE {registered}) THEN
        RAISE EXCEPTION 'The {title} tool versions are already registered';
    END IF;
END
$preflight$;

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
)
SELECT tool_name, tool_family, tool_type, next.purpose, next.input_schema::jsonb, output_schema,
       execution_type, handler_name, default_output_rows, max_output_rows,
       max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
       timeout_seconds, max_output_bytes, max_llm_result_rows,
       max_llm_result_bytes, max_llm_result_tokens,
       requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
       tool_specific_limits || '{sql_json(limits, sort_keys=True, separators=(",", ":"))}'::jsonb, next.version, false
FROM public."Tool_Catalog" AS previous
JOIN (VALUES
{rows}
) AS next(name, from_version, version, input_schema, purpose)
  ON previous.tool_name = next.name AND previous.version = next.from_version;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog" WHERE NOT is_active AND ({registered})) <> {len(VERSIONS)} THEN
        RAISE EXCEPTION 'The {title} tool versions were not registered';
    END IF;
    IF {carried} THEN
        RAISE EXCEPTION 'The {title} contracts are not in the registered rows';
    END IF;
END
$verify$;

COMMIT;
"""


def main() -> None:
    round_name = sys.argv[1] if len(sys.argv) > 1 else NEWEST
    target = ROUNDS[round_name]["target"]
    target.write_text(render(round_name))
    print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
