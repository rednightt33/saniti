"""Write a Tool_Catalog migration from market-ai-orc's tool definitions: one entry of ROUNDS per migration, each
registering the new versions of the tools whose contract changed in that round.

- round_b (20261003_005, applied): submit_data_need_spec v7, check_data_feasibility v5, check_research_feasibility v4
  (a time range may end "LATEST", 1b / C06) and run_python v3 (event_study takes the approved outcome unit, P26).
- round_c (20261003_007, applied): submit_data_need_spec v8, check_data_feasibility v6, check_research_feasibility
  v5 (data_as_of_policy: a resumed conversation keeps its data date unless the user asks for newer data, R-STORE C2e).
- round_d (20261003_011, applied): inspect_session v2, get_session_output v2, and the first rows of the new tools get_lineage,
  export_result, query_metric and get_evidence (phase D; "new" entries, no previous version to copy).
- round_e (20261004_001, applied): get_evidence v2 with DAYS (golden test ma-golden-20261003d).
- round_f (20261004_002, applied): the first row of find_web_fact (S4b, PLAN_FINAL_2026-10-04.md Fase 4); no version
  change.
- round_g (20261005_001, applied): get_system_capabilities v2, capabilities derived from the offered tools' effects (P31);
  prepare_data_bundle v2, open_analysis_session v2, run_python v4, complete_analysis orc-v2 (P32 counts, backtest).
- round_h (20261005_003, applied): the first row of lookup_reference and find_web_fact v2 (P34: the database before the
  web).
- round_i (20261005_004, applied): the first rows of check_references (item 10.2) and research_web (item 12),
  lookup_reference v2 and get_system_capabilities v3 (their descriptions name the web without the one-fact tool;
  PLAN_2026-10-05.md).
- round_j (20261006_001, applied): query_metric v2 (a period may start without an end, EXEC-R R5c); get_evidence marked removed
  from the code (EXEC-E, user decision 2026-10-06; its rows stay as history, "retired") and Table_Catalog's
  AI_conversation_evidence noted as no longer written ("table_notes").
- round_k (20261006_004, applied): read_conversation_memory v1, submit_data_need_spec v9 and run_python v5 (EXEC-C,
  EXEC-P5).
- round_l (20261007_001, applied): submit_data_need_spec v10, research_experiments (EXEC-V stage 3: the experiments of
  one hypothesis plan on the same data share one data need).
- round_m (20261008_001): submit_data_need_spec v11 (research_experiments removed, stage 3 revoked),
  open_analysis_session v3 (up to four sessions per answer, close_session_id) and prepare_data_bundle v3 (the same
  Governor SQL is reused within a conversation, data_reuse); EXEC-V revision of 2026-10-08.
- round_n (20261009_001, applied): export_result v2 (column_labels: the reader's column titles of an XLSX; M128b).
- round_o (20261009_003): research_web v2 (no web link in the answer text, the source in the Sources panel; user
  decision B 2026-10-09) and export_result v3 (the XLSX definition sheet says what one row is and how complete each
  group is against the source table; EXEC-Y Fase 3).

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
    "round_d": {
        "target": ROOT / "database/migrations/20261003_011_round_d_tool_catalog.sql",
        "versions": {"inspect_session": ("v1", "v2"), "get_session_output": ("v1", "v2")},
        "contracts": {"inspect_session": ("input_schema", "dataset"),
                      "get_session_output": ("input_schema", "execution_id")},
        # brand-new tools: one first row each (no previous version to copy from)
        "new": {
            "get_lineage": {"family": "AUDIT", "type": "RETRIEVAL", "flag": "AI_ENABLE_LINEAGE_TOOL",
                            "handler": "app/tools/lineage.py",
                            "output": "Where an output's numbers came from: output, execution, bundle datasets, "
                                      "Governor queries, source tables and loaded earlier outputs; no rows."},
            "export_result": {"family": "ADVANCED", "type": "EXPORT", "flag": "AI_ENABLE_EXPORT",
                              "handler": "app/tools/export.py",
                              "output": "export_id, file_name, format, size_bytes and sha256 of a file kept in "
                                        "AI_conversation_export (at most 20 MB); the file never enters the model's "
                                        "context."},
            "query_metric": {"family": "QUERY", "type": "RETRIEVAL", "flag": "AI_ENABLE_QUERY_METRIC",
                             "handler": "app/tools/metric.py",
                             "output": "Per period: rows per dimension (at most 200) with days_present, first_date "
                                       "and last_date, the Governor query id, the metric's unit and review status."},
            "get_evidence": {"family": "QUALITY", "type": "VALIDATION", "flag": "AI_ENABLE_EVIDENCE",
                             "handler": "app/tools/evidence.py",
                             "output": "Per claim: TERCEK, TIDAK_COCOK (with the difference), TIDAK_BISA_DICEK or "
                                       "TIDAK_DICEK_BATAS; the evidence rows go to the user (evidence[]), not the "
                                       "model."},
        },
        "title": "phase D",
        "summary": ["inspect_session v2 (dataset: the column statistics of a dataset, D1) and get_session_output v2",
                    "(ref, output_id without a session, execution_id: earlier results and code from R-STORE, D2);",
                    "new tools get_lineage (D3), export_result (D4), query_metric (D5) and get_evidence (D6)."],
        "limits": {"phase_d": "ROUND_PLAN_2026-10-03_FASE_D.md; every new tool behind its own AI_ENABLE_* flag"},
    },
    "round_e": {
        "target": ROOT / "database/migrations/20261004_001_evidence_days_tool_catalog.sql",
        "versions": {"get_evidence": ("v1", "v2")},
        "contracts": {"get_evidence": ("input_schema", "DAYS")},
        "title": "golden test fix",
        "summary": ["get_evidence v2: a WAREHOUSE recipe may count distinct dates (DAYS) from the summary's own",
                    "coverage (GT ma-golden-20261003d: a count of days checked as a count of rows)."],
        "limits": {"days": "DAYS reads the group's days_present (distinct dates with a row) of the Governor summary"},
    },
    "round_f": {
        "target": ROOT / "database/migrations/20261004_002_web_fact_tool_catalog.sql",
        "versions": {},
        "contracts": {},
        "new": {
            "find_web_fact": {"family": "QUERY", "type": "RETRIEVAL", "flag": "AI_ENABLE_WEB_FACT",
                              "handler": "app/tools/web_fact.py",
                              "output": "status (CONFIRMED, CONFLICTING, PARTIAL, NOT_FOUND) decided by market-web-"
                                        "governor from verbatim quotes, the value, each version's quotes, URLs and "
                                        "domains; at most about 30 seconds; no search excerpts."},
        },
        "title": "final plan phase 4",
        "design": "PLAN_FINAL_2026-10-04.md (Fase 4, S4b)",
        "summary": ["find_web_fact: one fact that is not in the market data (group membership, controlling",
                    "shareholder, company status) from market-web-governor POST /v1/fact (S4b, user decision K8)."],
        "limits": {"web_fact": "one subject and one attribute per call; market-web-governor /v1/fact, 30-second "
                               "deadline, Postgres-E8GM web_fact cache (30 days)"},
    },
    "round_g": {
        "target": ROOT / "database/migrations/20261005_001_round_g_tool_catalog.sql",
        "versions": {"get_system_capabilities": ("v1", "v2"), "prepare_data_bundle": ("v1", "v2"),
                     "open_analysis_session": ("v1", "v2"), "run_python": ("v3", "v4"),
                     "complete_analysis": ("orc-v1", "orc-v2")},
        "contracts": {"get_system_capabilities": ("purpose", "derived from the tools it can call"),
                      "prepare_data_bundle": ("purpose", "rows_in_ranges"),
                      "open_analysis_session": ("purpose", "rows_in_ranges"),
                      "run_python": ("purpose", "in_period"),
                      "complete_analysis": ("purpose", "saniti.backtest")},
        "title": "stress test fix P31",
        "design": "ERRORS_AND_SOLUTIONS.md P31 (router stress test 2026-10-05)",
        "summary": ["get_system_capabilities v2: each capability is derived from the effect of the tools offered in the",
                    "step (no list of tool names); v1 named tools that did not exist and reported no web capability",
                    "while find_web_fact was offered (stress test ma-qa-20261005a q7, P31).",
                    "prepare_data_bundle v2, open_analysis_session v2: row counts name their span (rows_extracted,",
                    "rows_in_ranges, buffer rows per range; P32). run_python v4: in_period and backtest (P32 layers 2-3).",
                    "complete_analysis orc-v2: the backtests are re-run by the backend (final_status.backtests)."],
        "limits": {"capabilities": "derived from ToolSpec.effect of the tools offered in the step (app/tools/system.py "
                                   "EFFECT_CAPABILITIES)"},
    },
    "round_h": {
        "target": ROOT / "database/migrations/20261005_003_round_h_tool_catalog.sql",
        "versions": {"find_web_fact": ("v1", "v2")},
        "contracts": {"find_web_fact": ("purpose", "lookup_reference")},
        "new": {
            "lookup_reference": {"family": "QUERY", "type": "RETRIEVAL", "flag": "AI_ENABLE_REFERENCE_LOOKUP",
                                 "handler": "app/tools/reference.py",
                                 "output": "without table: the static reference tables (no time column) with their "
                                           "AI-allowed columns and catalog descriptions; with table: at most 100 rows "
                                           "through SQL Governor /v1/catalog/reference-rows (catalog, compile and "
                                           "EXPLAIN gates), matched count, truncated flag; current values, not as of "
                                           "past dates."},
        },
        "title": "P34 database before the web",
        "design": "ERRORS_AND_SOLUTIONS.md P34; PLAN_2026-10-05.md item 4 (option A)",
        "summary": ["lookup_reference v1: the database's static reference tables (classifications, profiles), read in",
                    "every reading step including FACT (P34: the FACT step had no database reader and took BBCA's",
                    "sector from the web). find_web_fact v2: refused once while a reference column holds the asked",
                    "attribute (one small matcher call over the catalog's reference columns; fail-open); a web fact",
                    "describes and never enters a calculation."],
        "limits": {"reference_rows": "at most 100 returned, 2000 scanned (else NEEDS_NARROWING), 8 columns, 4 where "
                                     "conditions (EQ or IN of at most 50 values), one text match of 2-60 characters",
                   "web_check": "AI_MODEL, reasoning low, strict schema {held, table, column}; the named column must "
                                "be listed by the Governor, else the web call runs"},
    },
    "round_i": {
        "target": ROOT / "database/migrations/20261005_004_round_i_tool_catalog.sql",
        "versions": {"lookup_reference": ("v1", "v2"), "get_system_capabilities": ("v2", "v3")},
        "contracts": {"lookup_reference": ("purpose", "before a web lookup"),
                      "get_system_capabilities": ("purpose", "look up public information on the web")},
        "new": {
            "check_references": {"family": "QUERY", "type": "RETRIEVAL", "flag": "AI_ENABLE_ADDRESS_MENU",
                                 "handler": "app/tools/references.py",
                                 "output": "per value reference: what the answer would show, or why it does not "
                                           "resolve with the addresses that exist (and the address it was read from "
                                           "when redirected); no model call, no data read."},
            "research_web": {"family": "QUERY", "type": "RETRIEVAL", "flag": "AI_ENABLE_WEB_RESEARCH",
                             "handler": "app/tools/web_research.py",
                             "output": "status (OK, PARTIAL, NOT_FOUND, BUDGET_EXHAUSTED) from market-web-governor "
                                       "POST /v1/orc/web; citable items (fact, number, event, series, list) with "
                                       "their value, value as written, period, source domain and tier, verbatim "
                                       "quote, conflict kind and chosen_by_ai, each a value reference web.<id>; the "
                                       "conflicts by item id, the sources' domains, the web budget left; no search "
                                       "excerpts."},
        },
        "title": "plan 2026-10-05 items 10 and 12",
        "design": "PLAN_2026-10-05.md items 10 and 12; ERRORS_AND_SOLUTIONS.md P35, P36, M83",
        "summary": ["check_references v1: value references rendered before the answer is written (10.2; golden test",
                    "ma-qa-20261005b h_add rewrote a 15,000-token answer for one address composed from memory).",
                    "research_web v1: facts, numbers, events, series and lists from market-web-governor POST",
                    "/v1/orc/web in a citable envelope (item 12; bakrie_bank ran 34 single facts, q7 read a series as",
                    "a conflict). lookup_reference v2, get_system_capabilities v3: descriptions name the web without",
                    "the one-fact tool."],
        "limits": {"check_references": "at most 40 references per call; this run's references only",
                   "web_research": "need 3-500 characters, at most 30 subjects; the web governor bounds calls and "
                                   "cost per user turn (WEB_ORC_MAX_CALLS_PER_RUN, WEB_ORC_MAX_USD_PER_RUN); the "
                                   "orchestrator waits at most 150 s and keeps 15 s of the run for the answer"},
    },
    "round_j": {
        "target": ROOT / "database/migrations/20261006_001_round_j_tool_catalog.sql",
        "versions": {"query_metric": ("v1", "v2")},
        "contracts": {"query_metric": ("input_schema", "null: up to as_of")},
        # tools removed from the code: every row stays (history) and is marked with the removal
        "retired": {"get_evidence": "2026-10-06: removed from market-ai-orc with its switch AI_ENABLE_EVIDENCE and its "
                                    "gate (EXEC.md EXEC-E, user decision); cited figures are written by their address "
                                    "(DIRUJUK) instead"},
        # Table_Catalog.update_rule notes of tables the round's changes stop writing
        "table_notes": {"AI_conversation_evidence": " Not written since 2026-10-06: get_evidence was removed from "
                                                    "market-ai-orc (EXEC-E); the rows stay with their conversation."},
        "title": "EXEC-E and EXEC-R",
        "header": "EXEC.md EXEC-E and EXEC-R (user approval 2026-10-06)",
        "limits_design": "EXEC.md EXEC-E and EXEC-R (user approval 2026-10-06)",
        "summary": ["query_metric v2: a period may start without an end and then runs to as_of (EXEC-R R5c; golden test",
                    "ma-qa-20261006b refused four parallel calls for it, M88). get_evidence: removed from the code",
                    "(EXEC-E, user decision 2026-10-06); its rows stay and carry the removal. Table_Catalog:",
                    "AI_conversation_evidence is no longer written."],
        "limits": {"period": "trading_days, or start_date with end_date optional (null: up to as_of)"},
    },
    "round_k": {
        "target": ROOT / "database/migrations/20261006_004_round_k_tool_catalog.sql",
        "versions": {"submit_data_need_spec": ("v8", "v9"), "run_python": ("v4", "v5")},
        "contracts": {"submit_data_need_spec": ("purpose", "merged_steps"),
                      "run_python": ("input_schema", "complete_analysis at once")},
        "new": {
            "read_conversation_memory": {
                "family": "AUDIT", "type": "RETRIEVAL", "flag": "AI_ENABLE_RUN_MEMORY",
                "handler": "app/tools/memory.py",
                "output": "without run_id: the conversation's runs (run_id, turn, status, response type, error code, "
                          "time, reasoning length), or with section catalog or data_record the conversation's data "
                          "record; with run_id: one section of that run's memory (memo, message, answer, note, plan, "
                          "refusals, decisions, web, code, catalog, sources, reasoning) in pages of 20,000 "
                          "characters with next_offset; for a turn's own request id its message and whole answer. "
                          "No model call, no new data."},
        },
        "title": "EXEC-C and EXEC-P5",
        "header": "EXEC.md EXEC-C and EXEC-P5 (user approval 2026-10-06)",
        "design": "EXEC.md EXEC-C and EXEC-P5 (user approval 2026-10-06)",
        "limits_design": "EXEC.md EXEC-C and EXEC-P5 (user approval 2026-10-06)",
        "summary": ["read_conversation_memory v1: what each earlier run of the conversation kept (EXEC-C, Q1 memo, Q2",
                    "backend + AI); on every desk. submit_data_need_spec v9, run_python v5 (AI_ENABLE_MERGED_STEPS,",
                    "EXEC-P5): an APPROVED data need is followed at once by prepare_data_bundle and",
                    "open_analysis_session, and run_python with complete true by complete_analysis."],
        "limits": {"merged_steps": "the backend runs each step through the same gates and budgets as a call of the "
                                   "model and returns it as merged_steps; the tools stay offered to retry a step",
                   "run_memory": "one row per run in AI_conversation_run_memory (migration 20261006_003), deleted "
                                 "with the conversation; pages of 20,000 characters"},
    },
    "round_l": {
        "target": ROOT / "database/migrations/20261007_001_round_l_tool_catalog.sql",
        "versions": {"submit_data_need_spec": ("v9", "v10")},
        "contracts": {"submit_data_need_spec": ("input_schema", "research_experiments")},
        "title": "EXEC-V stage 3",
        "header": "EXEC.md EXEC-V stage 3 (user approval 2026-10-07)",
        "design": "EXEC.md EXEC-V stage 3 (user approval 2026-10-07)",
        "limits_design": "EXEC.md EXEC-V stage 3 (user approval 2026-10-07)",
        "summary": ["submit_data_need_spec v10: research_experiments, two to four experiments of one approved hypothesis",
                    "plan that read the same data, in one data need, one bundle and one session (offered when the",
                    "sandbox reports research_multi_experiment); complete_analysis returns one finding per experiment."],
        "limits": {"research_experiments": "two to four experiments per data need, each matched against the approved "
                                           "plan and counted as one experiment by the Research Governor; one finding "
                                           "per experiment, the completion passes only when each has one"},
    },
    "round_m": {
        "target": ROOT / "database/migrations/20261008_001_round_m_tool_catalog.sql",
        "versions": {"submit_data_need_spec": ("v10", "v11"), "open_analysis_session": ("v2", "v3"),
                     "prepare_data_bundle": ("v2", "v3")},
        "contracts": {"submit_data_need_spec": ("input_schema", "research_governance"),
                      "open_analysis_session": ("purpose", "never closes another"),
                      "prepare_data_bundle": ("purpose", "data_reuse")},
        "title": "EXEC-V revision",
        "header": "EXEC.md EXEC-V decisions and implementation plan of 2026-10-08",
        "design": "EXEC.md EXEC-V decisions and implementation plan of 2026-10-08",
        "limits_design": "EXEC.md EXEC-V decisions and implementation plan of 2026-10-08",
        "summary": ["submit_data_need_spec v11: research_experiments removed (stage 3 revoked: one experiment, one data",
                    "need, one session). open_analysis_session v3: up to four sessions per answer, opening one never",
                    "closes another, close_session_id after SESSION_LIMIT_PER_REQUEST. prepare_data_bundle v3: within a",
                    "conversation a part with the same Governor SQL whose range ends before today is reused (data_reuse)."],
        "limits": {"sessions_per_answer": "up to PY_SANDBOX_MAX_SESSIONS_PER_REQUEST (dev four) open at once; the open "
                                          "beyond it is refused with the open sessions listed",
                   "part_reuse": "one conversation; same data_sha256 and part_key; range ends before the reference "
                                 "date; copy not expired; same catalog"},
    },
    "round_n": {
        "target": ROOT / "database/migrations/20261009_001_round_n_tool_catalog.sql",
        "versions": {"export_result": ("v1", "v2")},
        "contracts": {"export_result": ("input_schema", "column_labels")},
        "title": "M128b readable Excel files",
        "header": "EXEC.md EXEC-X (go 2026-10-09: \"1 3 dan 4 - jalankan sekarang\"), ERRORS_AND_SOLUTIONS.md M128",
        "design": "EXEC.md EXEC-X, ERRORS_AND_SOLUTIONS.md M128 (b)",
        "limits_design": "EXEC.md EXEC-X, ERRORS_AND_SOLUTIONS.md M128 (b)",
        "summary": ["export_result v2: column_labels, the title of each column in the user's language for an XLSX; the",
                    "backend adds a column sheet (meaning and unit from AI_column_catalog for a column of the source",
                    "tables) and writes the definition and lineage sheets in plain words; CSV and Parquet keep the",
                    "machine column names."],
        "limits": {"columns": "at most 60 columns get a title and a meaning; a label is cut at 80 characters; a label "
                              "for a column the output does not have is ignored"},
    },
    "round_o": {
        "target": ROOT / "database/migrations/20261009_003_round_o_tool_catalog.sql",
        "versions": {"research_web": ("v1", "v2"), "export_result": ("v2", "v3")},
        "contracts": {"research_web": ("purpose", "Sources panel"),
                      "export_result": ("purpose", "how complete each group is")},
        "title": "EXEC-Y Fase 3 and decision B",
        "header": "EXEC.md EXEC-Y (user decisions 2026-10-09: \"Ok untuk B semua link web hilang pindah ke source\"; "
                  "\"E1 ok 2-4\"; go \"gas\")",
        "design": "EXEC.md EXEC-Y Fase 3 and decision B; ERRORS_AND_SOLUTIONS.md M128 (d), M132",
        "limits_design": "EXEC.md EXEC-Y Fase 3 and decision B; ERRORS_AND_SOLUTIONS.md M128 (d), M132",
        "summary": ["research_web v2: a web value is shown without a link and its source page is listed in the answer's",
                    "Sources panel (user decision B 2026-10-09). export_result v3: the XLSX definition sheet says what",
                    "one row is and, from one SQL Governor summary over the file's own period, how complete each group",
                    "is against the source table (EXEC-Y Fase 3 E1)."],
        "limits": {"completeness": "one Governor summary (COUNT) per export, at most 6 group columns and 50 groups; "
                                   "a filter through another table or one longer than 2,000 characters is not "
                                   "checked and the file says so"},
    },
}
NEWEST = "round_o"


def _tools_doc():
    spec = importlib.util.spec_from_file_location("generate_ai_tools_doc", ROOT / "scripts/generate_ai_tools_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def definitions(round_name: str = NEWEST) -> dict[str, dict]:
    wanted = set(ROUNDS[round_name]["versions"]) | set(ROUNDS[round_name].get("new") or {})
    return {name: d for name, d in _tools_doc()._registry().items() if name in wanted}


def _new_tools(spec: dict, found: dict[str, dict]) -> tuple[str, str, str]:
    """(INSERT statement, preflight condition, verify count) of a round's brand-new tools."""
    new = spec.get("new") or {}
    if not new:
        return "", "", ""
    rows = ",\n".join(
        f"    ('{name}', '{info['family']}', '{info['type']}', '{sql_literal(found[name]['description'])}',\n"
        f"     '{schema_text(found[name])}'::jsonb,\n"
        f"     '{sql_json({'description': info['output']}, sort_keys=True, separators=(',', ':'))}'::jsonb,\n"
        f"     'ORCHESTRATOR', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 40000, 200, 40000, NULL,\n"
        f"     false, false, false, '"
        + sql_json({"design": spec.get("design") or f"ROUND_PLAN_2026-10-03.md ({spec['title']})",
                    "feature_flag": info["flag"],
                    "handler": info["handler"], "registry_state": "registered from code (market-ai-orc) under the dev "
                                                                  "flags, inactive here", **spec["limits"]},
                   sort_keys=True, separators=(",", ":"))
        + "'::jsonb, 'v1', false)" for name, info in new.items())
    insert = f"""
INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
) VALUES
{rows};
"""
    names = ", ".join(f"'{n}'" for n in new)
    return insert, f"EXISTS (SELECT 1 FROM public.\"Tool_Catalog\" WHERE tool_name IN ({names}))", \
        f"(SELECT count(*) FROM public.\"Tool_Catalog\" WHERE tool_name IN ({names}) AND version = 'v1' " \
        f"AND NOT is_active) <> {len(new)}"


def _retired(spec: dict) -> tuple[str, str, str]:
    """(UPDATE statements, preflight condition, verify condition) marking removed tools and the tables they wrote."""
    retired, notes = spec.get("retired") or {}, spec.get("table_notes") or {}
    if not retired and not notes:
        return "", "", ""
    updates, missing, unmarked = [], [], []
    for name, reason in retired.items():
        mark = sql_json({"removed": reason}, sort_keys=True, separators=(",", ":"))
        updates.append(f"UPDATE public.\"Tool_Catalog\" SET tool_specific_limits = tool_specific_limits || '{mark}'::jsonb,\n"
                       f"    is_active = false\nWHERE tool_name = '{name}';")
        missing.append(f"NOT EXISTS (SELECT 1 FROM public.\"Tool_Catalog\" WHERE tool_name = '{name}')")
        missing.append(f"EXISTS (SELECT 1 FROM public.\"Tool_Catalog\" WHERE tool_name = '{name}' "
                       f"AND tool_specific_limits ? 'removed')")
        unmarked.append(f"EXISTS (SELECT 1 FROM public.\"Tool_Catalog\" WHERE tool_name = '{name}' "
                        f"AND (is_active OR NOT tool_specific_limits ? 'removed'))")
    for table, note in notes.items():
        updates.append(f"UPDATE public.\"Table_Catalog\" SET update_rule = update_rule || '{sql_literal(note)}'\n"
                       f"WHERE table_schema = 'public' AND table_name = '{table}';")
        missing.append(f"(SELECT count(*) FROM public.\"Table_Catalog\" WHERE table_schema = 'public' "
                       f"AND table_name = '{table}' AND update_rule NOT LIKE '%Not written since%') <> 1")
        unmarked.append(f"NOT EXISTS (SELECT 1 FROM public.\"Table_Catalog\" WHERE table_schema = 'public' "
                        f"AND table_name = '{table}' AND update_rule LIKE '%Not written since 2026-10-06%')")
    return "\n" + "\n".join(updates) + "\n", "\n       OR ".join(missing), "\n       OR ".join(unmarked)


def schema_text(definition: dict) -> str:
    return sql_json(definition["parameters"], sort_keys=True, separators=(",", ":"))


def render(round_name: str = NEWEST) -> str:
    spec = ROUNDS[round_name]
    VERSIONS, CONTRACTS = spec["versions"], spec["contracts"]
    found = definitions(round_name)
    assert set(found) == set(VERSIONS) | set(spec.get("new") or {}), found.keys()
    new_insert, new_exists, new_count = _new_tools(spec, found)
    retired_sql, retired_missing, retired_unmarked = _retired(spec)
    extra_exists = f" OR {new_exists}" if new_exists else ""
    extra_count = f"\n       OR {new_count}" if new_count else ""
    retired_preflight = (f"\n    IF {retired_missing} THEN\n        RAISE EXCEPTION 'The removed tools or their "
                         f"tables are missing or already marked';\n    END IF;") if retired_missing else ""
    retired_verify = (f"\n    IF {retired_unmarked} THEN\n        RAISE EXCEPTION 'The removed tools or their tables "
                      f"were not marked';\n    END IF;") if retired_unmarked else ""
    # a later round names its own design document ("limits_design", "header"); older rounds keep their text
    limits = {"design": spec.get("limits_design") or f"ROUND_PLAN_2026-10-03.md ({spec['title']})",
              "registry_state": "registered from code (market-ai-orc) under the dev flags, inactive here",
              **spec["limits"]}
    if not VERSIONS:
        return _render_new_only(spec, new_insert, new_exists, new_count)
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
    header = spec.get("header") or f"Round 2026-10-03 {title} (ROUND_PLAN_2026-10-03.md)"
    return f"""-- {header}: the tool contracts the code now offers.
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
    IF EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE {registered}){extra_exists} THEN
        RAISE EXCEPTION 'The {title} tool versions are already registered';
    END IF;{retired_preflight}
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
{new_insert}{retired_sql}
DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Tool_Catalog" WHERE NOT is_active AND ({registered})) <> {len(VERSIONS)}{extra_count} THEN
        RAISE EXCEPTION 'The {title} tool versions were not registered';
    END IF;
    IF {carried} THEN
        RAISE EXCEPTION 'The {title} contracts are not in the registered rows';
    END IF;{retired_verify}
END
$verify$;

COMMIT;
"""


def _render_new_only(spec: dict, new_insert: str, new_exists: str, new_count: str) -> str:
    """A round that only adds brand-new tools (no previous version to copy)."""
    summary = "\n".join(f"-- {line}" for line in spec["summary"])
    title = spec["title"]
    return f"""-- {title} (PLAN_FINAL_2026-10-04.md): the first Tool_Catalog rows of new tools.
{summary}
-- Inactive like every market-ai-orc row; input schema and purpose from the code.
-- GENERATED by scripts/generate_tool_catalog_migration.py; market-ai-orc tests/test_data_need_tool.py fails on
-- drift. Do not edit by hand.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF {new_exists} THEN
        RAISE EXCEPTION 'The {title} tools are already registered';
    END IF;
END
$preflight$;
{new_insert}
DO $verify$
BEGIN
    IF {new_count} THEN
        RAISE EXCEPTION 'The {title} tools were not registered';
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
