"""NEW_TABLE_ONBOARDING_PLAN.md validation, planner level (no model): run market-ai-orc's own Execution Planner
preflight (`ExecutionPlanner._preflight`, the path dev runs with AI_ENABLE_PREFLIGHT_PARTS=true) against the SQL
Governor's own extraction code in process, with the privileges of `market_ai_sql_reader`, and report how many estimates
the plan took, how many came back too large, and how many parts it chose. Nothing is extracted (estimates only).

Stage with run_job.sh extras (EXEC-M208-L3 step 0):
  apps/market-ai-orc/app                  as app  (the planner)
  a copy of apps/market-sql-governor/app  as gov  (both packages import relatively, so the copy imports as gov)
  one requirements.txt with the lines of both services' requirements.txt

params.json:
  {"bundle_max_rows": 10000000, "env": {"SQL_ESTIMATE_COUNT_ENABLED": "true", "SQL_ESTIMATE_COUNT_TIMEOUT_MS": "7000"},
   "cases": [{"id": "v5_400", "table": "Feature_05_Foreign_Domestic_Broker_Detail_Stock", "columns": ["net_value"],
              "days": 400, "filters": {}, "restrict_to": null}]}
  bundle_max_rows  the sandbox's PY_SANDBOX_BUNDLE_MAX_ROWS on dev (the planner's G14 budget);
  env              the Governor's non-secret limits as set on dev;
  restrict_to      a catalog table to restrict through (an INNER relationship, as the AI sends it): the relationship
                   row is read from AI_catalog_relationships, never typed here.
Prints `OUT {json}` per case (calls, too-large answers, parts, seconds), then JOB_DONE. No secret is printed.
"""
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

import psycopg
from psycopg import sql

from gov.catalog_contract import sha256_json
from gov.config import Settings
from gov.governor import Database, Extractor, Governor, newest_sql
from gov.store import LocalStore
from app.tools.data_planner import ExecutionPlanner, PlanBudget, PlanStop
from app.tools.request_data import current_request_id

READER_ROLE = "market_ai_sql_reader"
p = json.load(open("params.json"))


class ReaderDatabase(Database):
    @contextmanager
    def session(self):
        with super().session() as connection:
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(READER_ROLE)))
            yield connection


env = {"SQL_GOVERNOR_API_KEY": "onboarding-planner-check-" + "x" * 16, "GOVERNOR_DATABASE_URL": os.environ["DATABASE_URL"],
       "SQL_DATASET_LOCAL_DIR": tempfile.mkdtemp(), **(p.get("env") or {})}
settings = Settings.from_env(env)
extractor = Extractor(Governor(settings, ReaderDatabase(settings), LocalStore(env["SQL_DATASET_LOCAL_DIR"])))


class InProcessGovernor:
    """The orc Governor client's extract() (request_data.py) answered by the Governor's own Extractor; every call is
    timed and kept for the report."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def extract(self, spec, lineage, *, planned_parts=1, estimate_only=False, count_cap=None):
        started = time.monotonic()
        response = extractor.handle(current_request_id.get(), spec, lineage, part_count=planned_parts,
                                    estimate_only=estimate_only, count_cap=count_cap)
        estimates = response.get("estimates") or {}
        self.calls.append({"window": spec.get("window"), "status": response.get("status"),
                           "row_basis": estimates.get("row_basis"), "result_rows": estimates.get("result_rows"),
                           "parts_asked": (response.get("partitioning") or {}).get("parts"),
                           "sample": estimates.get("sample"), "ms": int((time.monotonic() - started) * 1000)})
        return response


def admin():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, options="-c default_transaction_read_only=on")


def restriction(source: str, right: str, connection) -> dict:
    """The INNER restriction the AI would send, built from the catalog relationship between the two tables."""
    row = connection.execute(
        'SELECT relationship_id, left_table, left_columns, right_columns, supported_join_semantics '
        'FROM public."AI_catalog_relationships" WHERE is_allowed AND ((left_table = %s AND right_table = %s) '
        'OR (left_table = %s AND right_table = %s)) ORDER BY relationship_id LIMIT 1',
        (source, right, right, source)).fetchone()
    if row is None:
        raise SystemExit(f"no allowed relationship between {source} and {right}")
    rid, left_table, lcols, rcols, semantics = row
    if "CURRENT_STATE" not in (semantics or []):
        raise SystemExit(f"relationship {rid} has no CURRENT_STATE semantics")
    if left_table != source:
        lcols, rcols = rcols, lcols
    keys = ({"left_column": lcols[0], "right_column": rcols[0]} if len(lcols) == 1
            else {"left_columns": list(lcols), "right_columns": list(rcols)})
    scope = {"type": "ALL"}
    return {"relationship_id": rid, "join_semantics": "CURRENT_STATE", **keys, "left_time_column": None,
            "right_time_column": None, "as_of_direction": None, "effective_from_column": None,
            "effective_to_column": None, "right_table": right, "right_scope": scope,
            "right_scope_sha256": sha256_json(scope)}


def run_case(case: dict) -> dict:
    table = case["table"]
    with admin() as connection:
        entity_column, time_column = connection.execute(
            'SELECT entity_column, time_column FROM public."AI_table_catalog" WHERE table_name = %s',
            (table,)).fetchone()
        newest = connection.execute(newest_sql(table, time_column)).fetchone()[0]
        restrictions = [restriction(table, case["restrict_to"], connection)] if case.get("restrict_to") else []
    nodes = [{"type": "PREDICATE", "column": k, "operator": "EQ", "values": [str(v)]}
             for k, v in (case.get("filters") or {}).items()]
    scope = {"type": "ALL"} if not nodes else nodes[0] if len(nodes) == 1 else {"type": "AND", "children": nodes}
    start = newest - timedelta(days=int(case["days"]))
    entry = {"data_request_id": f"pc_{case['id']}"[:40] + "_A", "logical_name": "planner_check",
             "source_table": table, "time_column": time_column,
             "extract_columns": list(dict.fromkeys([time_column, entity_column, *case["columns"]])),
             "scope": scope, "scope_sha256": sha256_json(scope), "restrictions": restrictions,
             "restriction_sha256": sha256_json(restrictions), "ordering": [],
             "windows": [{"range_id": "r1", "extract_from": start.isoformat(), "extract_to": newest.isoformat()}]}
    source = {"need_id": "need_" + uuid.uuid4().hex[:24], "spec_sha256": "0" * 64, "request_group_id": "planner_check",
              "revision": 1, "catalog_sha256": None}
    governor = InProcessGovernor()
    planner = ExecutionPlanner(sandbox=None, governor=governor, preflight=True,
                               limits={"bundle_max_rows": p.get("bundle_max_rows")})
    budget = PlanBudget(planner.max_bundle_rows)
    token = current_request_id.set(f"planner-check-{uuid.uuid4().hex[:12]}")
    started = time.monotonic()
    result = {"case": case["id"], "table": table, "window": [start.isoformat(), newest.isoformat()],
              "restricted_by": case.get("restrict_to")}
    try:
        parts, rows = planner._preflight(source, f"plan_{uuid.uuid4().hex[:24]}", entry, budget)
        result.update(outcome="PLANNED", parts=len(parts), estimated_rows=rows)
    except PlanStop as stop:
        result.update(outcome="STOPPED", stop={k: stop.outcome.get(k) for k in ("status", "code", "message")
                                                 if stop.outcome.get(k) is not None})
    finally:
        current_request_id.reset(token)
    calls = governor.calls
    too_large = [c for c in calls if c["status"] != "WITHIN_LIMITS"]
    result.update(seconds=round(time.monotonic() - started, 1), estimates=len(calls),
                  too_large=len(too_large), too_large_ms=sum(c["ms"] for c in too_large),
                  within_ms=sum(c["ms"] for c in calls if c["status"] == "WITHIN_LIMITS"),
                  first=calls[0] if calls else None, too_large_calls=too_large[:8],
                  samples=[c["sample"] for c in calls if c.get("sample")][:4])
    return result


for case in p["cases"]:
    print("OUT " + json.dumps(run_case(case), default=str), flush=True)
print("JOB_DONE PLANNER_CHECK", flush=True)
