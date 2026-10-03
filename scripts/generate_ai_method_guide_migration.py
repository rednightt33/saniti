"""Write the method guide migration of the current guides version from the method guides in code
(apps/market-python-sandbox/app/method_guides.py, byte-identical in market-ai-orc). The sandbox test
tests/test_method_guides.py fails when the migration and the guides drift apart.

Version 1 created the table (database/migrations/20261002_001_create_ai_method_guide.sql, applied, frozen: render_create
is kept for the record). A later version adds its rows with a forward migration (render), and the earlier rows stay so a
service still on the earlier version keeps its guides while it is replaced.

Usage: python scripts/generate_ai_method_guide_migration.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sql_text import sql_json, sql_literal  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
CREATE_TARGET = ROOT / "database/migrations/20261002_001_create_ai_method_guide.sql"
# one forward migration per guides version after the first
# what each version changed, for the migration's header (version 2's file is applied and frozen)
VERSION_CHANGES = {
    2: "HIGH_ALERT_IMPLEMENTATION_PLAN.md, user decision 2026-10-02: every released\n-- table or JSON states its "
       "definition; the event study's flow table; event_summary applies the approved plan's\n-- success rule; an "
       "explanation starts from the explained result's own table",
    3: "ROUND_PLAN_2026-10-03.md B2, P26: a research threshold carries its unit (min_effect_unit,\n-- "
       "success_rule.unit); event_study and event_summary use the approved experiment's outcome unit",
    4: "ROUND_PLAN_2026-10-03_FASE_D.md D6: a base table released for each main claim, checked with\n-- "
       "get_evidence (BASE_TABLE or WAREHOUSE)",
}
VERSION_TARGETS = {2: ROOT / "database/migrations/20261003_002_ai_method_guides_v2.sql",
                   3: ROOT / "database/migrations/20261003_004_ai_method_guides_v3.sql",
                   4: ROOT / "database/migrations/20261003_010_ai_method_guides_v4.sql"}
COLUMNS = [
    ("name", "text", "Guide name (free_code, event_study, hypothesis_plan, multi_angle or a session helper's guide)."),
    ("guides_version", "integer", "Version of the method guides content."),
    ("kind", "text", "PATH (an analysis path G1-G4) or HELPER (a session helper)."),
    ("g", "text", "The analysis path G1, G2, G3 or G4; NULL for a helper guide."),
    ("guide", "jsonb", "JSON object: when to use and not, inputs with defaults, limits, what the backend checks and does not, results, common errors and examples."),
    ("guide_sha256", "text", "Hash of this guide; the conversation data record keeps it to carry the version a model opened."),
    ("guides_sha256", "text", "Hash of all guides; market-ai-orc serves them only when it equals the sandbox's and its own."),
    ("is_active", "boolean", "Whether the guide is offered to the model."),
    ("created_at", "timestamp with time zone", "Row creation time."),
    ("updated_at", "timestamp with time zone", "Last update time."),
]
TOOL_INPUT = {"additionalProperties": False, "properties": {"name": {
    "description": "A name from analysis_methods (for example event_study), or a research library method_id while "
                   "multi-angle research is offered.", "type": "string"}},
    "required": ["name"], "type": "object"}
TOOL_OUTPUT = {"description": "The guide (name, version, sha256, the verification level's meaning and the guide), a "
                              "research library method's entry, or REJECTED UNKNOWN_METHOD with the available names.",
               "properties": {"available": {}, "code": {}, "guide": {}, "name": {}, "research_library_method": {},
                              "sha256": {}, "status": {}, "verification_levels": {}, "version": {}},
               "type": "object"}


def load_guides():
    path = ROOT / "apps/market-python-sandbox/app/method_guides.py"
    spec = importlib.util.spec_from_file_location("method_guides", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_sql_text = sql_literal


def render_create() -> str:
    guides = load_guides()
    rows = guides.rows()
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=1)
    assert "$guides$" not in payload
    sha = guides.GUIDES_SHA256
    definitions = "\n".join(f"        WHEN '{name}' THEN '{_sql_text(text)}'" for name, _, text in COLUMNS)
    orc_description = _load_description()
    limits = json.dumps({"design": "G2_G3_REACTIVATION_PLAN.md 4b", "feature_flag": "AI_ENABLE_METHOD_GUIDES",
                         "guides_sha256": sha, "handler": "app/tools/method_guides.py (method_guide_spec)",
                         "registry_state": "Registered in market-ai-orc only when AI_method_guide, the sandbox "
                                           "capability method_guides and market-ai-orc's app/method_guides.py carry "
                                           "the same guides (else method_guides_inactive); is_active=false keeps it "
                                           "out of market-ai-backend tool lists.",
                         "runtime_service": "market-ai-orc"}, sort_keys=True)
    return f"""-- Method guides (G2_G3_REACTIVATION_PLAN.md 4b, user decision 2026-10-02): the model-facing menu and manual of the
-- analysis paths (G1 free code, G2 event study, G3 hypothesis plan, G4 multi-angle plan) and of the main session
-- helpers. public."AI_method_guide" holds one row per guide; market-ai-orc offers the menu at the start of every run
-- and serves a guide through get_method_guide, only when the table, the sandbox and its own copy carry the same hash.
-- It describes, it does not compute. Tool_Catalog registers get_method_guide v1 (inactive like every market-ai-orc
-- row).
-- GENERATED by scripts/generate_ai_method_guide_migration.py from apps/market-python-sandbox/app/method_guides.py
-- (guides_sha256 {sha}); the sandbox test tests/test_method_guides.py fails on drift. Do not edit by hand.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_method_guide"') IS NOT NULL THEN
        RAISE EXCEPTION 'AI_method_guide already exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_catalog_reader') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader role is required';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE tool_name = 'get_method_guide') THEN
        RAISE EXCEPTION 'get_method_guide is already registered';
    END IF;
END
$preflight$;

CREATE TABLE public."AI_method_guide" (
    name text NOT NULL,
    guides_version integer NOT NULL,
    kind text NOT NULL,
    g text,
    guide jsonb NOT NULL,
    guide_sha256 text NOT NULL,
    guides_sha256 text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AI_method_guide_pkey" PRIMARY KEY (name, guides_version),
    CONSTRAINT ai_method_guide_kind CHECK (kind IN ('PATH', 'HELPER')),
    CONSTRAINT ai_method_guide_g CHECK (g IS NULL OR g IN ('G1', 'G2', 'G3', 'G4')),
    CONSTRAINT ai_method_guide_path_has_g CHECK ((kind = 'PATH') = (g IS NOT NULL)),
    CONSTRAINT ai_method_guide_sha CHECK (guide_sha256 ~ '^[0-9a-f]{{64}}$' AND guides_sha256 ~ '^[0-9a-f]{{64}}$'),
    CONSTRAINT ai_method_guide_json CHECK (jsonb_typeof(guide) = 'object' AND guide->>'name' = name),
    CONSTRAINT ai_method_guide_name CHECK (name ~ '^[a-z][a-z0-9_]{{0,62}}$')
);
COMMENT ON TABLE public."AI_method_guide" IS
    'Model-facing menu and manual of the analysis paths and session helpers; generated from code, hash-bound '
    '(guides_sha256). Enforcement stays in code.';

-- market-ai-orc's catalog login inherits this role; the SQL Governor role gets no grant.
GRANT SELECT ON public."AI_method_guide" TO market_ai_catalog_reader;
REVOKE ALL ON public."AI_method_guide" FROM PUBLIC;

INSERT INTO public."AI_method_guide" (name, guides_version, kind, g, guide, guide_sha256, guides_sha256)
SELECT r.name, r.guides_version, r.kind, r.g, r.guide, r.guide_sha256, '{sha}'
FROM jsonb_to_recordset($guides${payload}$guides$::jsonb) AS r(
    name text, guides_version integer, kind text, g text, guide jsonb, guide_sha256 text);

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths,
    update_rule, related_functions, documentation_status,
    readiness_mode, readiness_date_column, observation_date_column,
    data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method
) VALUES (
    'public', 'AI_method_guide', 'Reference',
    'Model-facing menu and manual of the analysis paths (G1-G4) and session helpers: when to use and not, inputs, '
    'limits, what the backend checks, results, common errors and tested examples; bound to the code by guides_sha256.',
    'One row per guide and guides version', ARRAY['name', 'guides_version'],
    'apps/market-python-sandbox/app/method_guides.py (byte-identical in market-ai-orc)',
    ARRAY[]::text[], ARRAY['database/migrations/20261002_001_create_ai_method_guide.sql',
                          'apps/market-python-sandbox/app/method_guides.py',
                          'scripts/generate_ai_method_guide_migration.py'],
    'Regenerated by a forward migration whenever the guides in code change; never edited by hand.',
    ARRAY[]::text[], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, NULL,
    'Metadata only; enforcement is the sandbox helpers, the harness checks and the orchestrator gates in code.',
    'NOT_APPLICABLE', NULL
);

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type,
    is_nullable, default_expression, is_primary_key, definition,
    source_column_or_expression, unit, null_rule, source_code_paths,
    documentation_status
)
SELECT columns.table_schema, columns.table_name, columns.column_name, columns.ordinal_position,
       columns.data_type, columns.is_nullable = 'YES', columns.column_default,
       columns.column_name IN ('name', 'guides_version'),
       CASE columns.column_name
{definitions}
       END,
       'app/method_guides.py (rows())', NULL,
       CASE WHEN columns.column_name = 'g' THEN 'NULL for a HELPER guide.' ELSE 'NULL is not permitted.' END,
       ARRAY['database/migrations/20261002_001_create_ai_method_guide.sql'], 'VERIFIED'
FROM information_schema.columns AS columns
WHERE columns.table_schema = 'public' AND columns.table_name = 'AI_method_guide';

INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
)
VALUES
    ('get_method_guide', 'DISCOVERY', 'RETRIEVAL', '{_sql_text(orc_description)}',
     '{_sql_text(json.dumps(TOOL_INPUT, sort_keys=True, separators=(",", ":")))}'::jsonb,
     '{_sql_text(json.dumps(TOOL_OUTPUT, sort_keys=True, separators=(",", ":")))}'::jsonb,
     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 5, 40000, 8, 40000, NULL,
     false, false, false, '{_sql_text(limits)}'::jsonb, 'v1', false);

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_method_guide" WHERE is_active AND guides_sha256 = '{sha}') <> {len(rows)} THEN
        RAISE EXCEPTION 'Expected {len(rows)} active method guide rows with the guides hash';
    END IF;
    IF (SELECT count(DISTINCT g) FROM public."AI_method_guide" WHERE kind = 'PATH') <> 4 THEN
        RAISE EXCEPTION 'Expected one guide for each of G1, G2, G3 and G4';
    END IF;
    IF (SELECT count(*) FROM public."Column_Catalog" WHERE table_name = 'AI_method_guide'
          AND definition IS NOT NULL) <> {len(COLUMNS)}
       OR NOT EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE table_name = 'AI_method_guide') THEN
        RAISE EXCEPTION 'AI_method_guide lacks its Table_Catalog / Column_Catalog definitions';
    END IF;
    IF NOT has_table_privilege('market_ai_catalog_reader', 'public."AI_method_guide"', 'SELECT')
       OR has_table_privilege('market_ai_catalog_reader', 'public."AI_method_guide"', 'INSERT,UPDATE,DELETE') THEN
        RAISE EXCEPTION 'market_ai_catalog_reader privileges do not match the read-only contract';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_sql_reader')
       AND has_table_privilege('market_ai_sql_reader', 'public."AI_method_guide"', 'SELECT') THEN
        RAISE EXCEPTION 'The SQL Governor unexpectedly reads the method guides';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog" WHERE tool_name = 'get_method_guide' AND version = 'v1'
          AND NOT is_active AND tool_specific_limits->>'runtime_service' = 'market-ai-orc') <> 1 THEN
        RAISE EXCEPTION 'Expected one inactive get_method_guide v1 registration';
    END IF;
END
$verify$;
COMMIT;
"""


def _load_description() -> str:
    """The tool description of market-ai-orc (app/tools/method_guides.py), read without importing the service."""
    import ast

    source = (ROOT / "apps/market-ai-orc/app/tools/method_guides.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "GET_METHOD_GUIDE_DESCRIPTION"
                                                for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("GET_METHOD_GUIDE_DESCRIPTION not found")


def render() -> str:
    """The forward migration that adds the current guides version (version 2 onward)."""
    guides = load_guides()
    rows = guides.rows()
    version = guides.GUIDES_VERSION
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=1)
    assert "$guides$" not in payload
    sha = guides.GUIDES_SHA256
    return f"""-- Method guides version {version} ({VERSION_CHANGES[version]}). Adds the version {version} rows; the earlier
-- version's rows stay, so a market-ai-orc still on it keeps its guides until it is replaced (each service reads the
-- version of its own code).
-- GENERATED by scripts/generate_ai_method_guide_migration.py from apps/market-python-sandbox/app/method_guides.py
-- (guides_sha256 {sha}); the sandbox test tests/test_method_guides.py fails on drift. Do not edit by hand.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF to_regclass('public."AI_method_guide"') IS NULL THEN
        RAISE EXCEPTION 'AI_method_guide does not exist (migration 20261002_001)';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_method_guide" WHERE guides_version = {version}) THEN
        RAISE EXCEPTION 'Method guides version {version} are already registered';
    END IF;
END
$preflight$;

INSERT INTO public."AI_method_guide" (name, guides_version, kind, g, guide, guide_sha256, guides_sha256)
SELECT r.name, r.guides_version, r.kind, r.g, r.guide, r.guide_sha256, '{sha}'
FROM jsonb_to_recordset($guides${payload}$guides$::jsonb) AS r(
    name text, guides_version integer, kind text, g text, guide jsonb, guide_sha256 text);

UPDATE public."Table_Catalog"
SET source_code_paths = (SELECT array_agg(DISTINCT p ORDER BY p) FROM unnest(source_code_paths || ARRAY[
        '{VERSION_TARGETS[version].relative_to(ROOT)}']) AS p)
WHERE table_schema = 'public' AND table_name = 'AI_method_guide';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_method_guide" WHERE is_active AND guides_version = {version}
          AND guides_sha256 = '{sha}') <> {len(rows)} THEN
        RAISE EXCEPTION 'Expected {len(rows)} active method guide rows of version {version} with the guides hash';
    END IF;
    IF (SELECT count(DISTINCT g) FROM public."AI_method_guide" WHERE kind = 'PATH' AND guides_version = {version}) <> 4 THEN
        RAISE EXCEPTION 'Expected one guide for each of G1, G2, G3 and G4';
    END IF;
END
$verify$;
COMMIT;
"""


def target() -> Path:
    return VERSION_TARGETS[load_guides().GUIDES_VERSION]


if __name__ == "__main__":
    target().write_text(render(), encoding="utf-8")
    print(f"wrote {target().relative_to(ROOT)}")
