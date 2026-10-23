"""NEW_TABLE_ONBOARDING_PLAN.md validation, Governor level (no model): run the SQL Governor's own extraction code
(market-sql-governor app, staged as an extra) against the live table with the privileges of `market_ai_sql_reader`,
the role the Governor login reads through, and compare what it returns with SQL.

Stage with run_job.sh extras: apps/market-sql-governor/app and apps/market-sql-governor/requirements.txt.

params.json:
  {"table": "Feature_06_Foreign_Domestic_Stock", "columns": ["trade_date", "ticker", "net_value"],
   "entity": "BBCA", "one_days": 365, "all_days": 400, "too_long_days": 2000,
   "filters": {"market_board": "Regular"},
   "env": {"SQL_ESTIMATE_COUNT_ENABLED": "true", "SQL_ESTIMATE_COUNT_TIMEOUT_MS": "7000"}}
  columns   the columns the AI would ask for (the entity and time columns come from the catalog contract);
  filters   equality filters every case carries, as the AI sends them;
  env       the Governor's non-secret limits as set on dev (names and values from `railway variables`, never a key).

Cases:
  A  one entity over one_days: estimate, then extract; rows equal count(*) (G13).
  B  every entity over all_days: estimate; when the Governor splits it, every part is extracted with the planner's
     split (extract.split_window), a part found too large while extracting is split again as the planner does
     (resplits, and the seconds those attempts took), and the parts add up to count(*).
  C  every entity over too_long_days, estimate only: a refusal names a valid narrowing (a next action and a reason).
Prints `OUT {json}` per case, `VERDICT {json}` per case and one `VERDICT_TABLE` line, then JOB_DONE. No secret is
printed: the database URL stays inside the job.
"""
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import date, timedelta

import psycopg
from psycopg import sql

from app import extract as ex
from app.catalog_contract import sha256_json
from app.config import Settings
from app.governor import Database, Extractor, Governor, newest_sql
from app.store import LocalStore

READER_ROLE = "market_ai_sql_reader"
p = json.load(open("params.json"))
table, filters = p["table"], p.get("filters") or {}


class ReaderDatabase(Database):
    """The Governor's session with the reader role's privileges: a column or table the role cannot read fails here as
    it fails in production."""

    @contextmanager
    def session(self):
        with super().session() as connection:
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(READER_ROLE)))
            yield connection


env = {"SQL_GOVERNOR_API_KEY": "onboarding-governor-check-" + "x" * 16, "GOVERNOR_DATABASE_URL": os.environ["DATABASE_URL"],
       "SQL_DATASET_LOCAL_DIR": tempfile.mkdtemp(), **(p.get("env") or {})}
settings = Settings.from_env(env)
governor = Governor(settings, ReaderDatabase(settings), LocalStore(env["SQL_DATASET_LOCAL_DIR"]))
extractor = Extractor(governor)



def admin():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True,
                           options="-c default_transaction_read_only=on -c statement_timeout=300000")


with admin() as connection:
    entity_column, time_column = connection.execute(
        'SELECT entity_column, time_column FROM public."AI_table_catalog" WHERE table_name = %s', (table,)).fetchone()
    newest = connection.execute(newest_sql(table, time_column)).fetchone()[0]


def counted(start: date, end: date, entity: str | None) -> int:
    parts = [sql.SQL("{} BETWEEN {} AND {}").format(sql.Identifier(time_column), sql.Literal(start), sql.Literal(end))]
    parts += [sql.SQL("{} = {}").format(sql.Identifier(k), sql.Literal(v)) for k, v in filters.items()]
    if entity:
        parts.append(sql.SQL("{} = {}").format(sql.Identifier(entity_column), sql.Literal(entity)))
    with admin() as connection:
        return connection.execute(sql.SQL("SELECT count(*) FROM public.{} WHERE {}").format(
            sql.Identifier(table), sql.SQL(" AND ").join(parts))).fetchone()[0]


def scope(entity: str | None) -> dict:
    nodes = [{"type": "PREDICATE", "column": k, "operator": "EQ", "values": [str(v)]} for k, v in filters.items()]
    if entity:
        nodes.append({"type": "PREDICATE", "column": entity_column, "operator": "EQ", "values": [entity]})
    if not nodes:
        return {"type": "ALL"}
    return nodes[0] if len(nodes) == 1 else {"type": "AND", "children": nodes}


def request(case: str, start: date, end: date, entity: str | None) -> dict:
    columns = list(dict.fromkeys([time_column, entity_column, *p["columns"]]))
    return {"extraction_version": "extraction_spec/v1", "data_request_id": f"onboard_{case}",
            "source_table": table, "columns": columns, "scope": scope(entity), "restrictions": [],
            "window": {"from": start.isoformat(), "to": end.isoformat()}, "entity_partition": None, "order_by": []}


def lineage(spec: dict, envelope: dict) -> dict:
    return {"need_id": "need_" + "0" * 24, "spec_sha256": "0" * 64, "request_group_id": "onboard",
            "revision": 1, "data_request_id": spec["data_request_id"], "logical_name": "onboard",
            "scope_sha256": sha256_json(spec["scope"]), "restriction_sha256": sha256_json([]),
            "plan_id": "plan_" + "0" * 24, "part_key": ex.part_key(spec["window"], spec["entity_partition"]),
            "envelope": {**envelope, "range_ids": ["r1"]}, "catalog_sha256": None,
            "extraction_sha256": ex.extraction_sha256(spec)}


def brief(outcome: dict) -> dict:
    return {k: outcome.get(k) for k in ("status", "code", "message", "next_action", "partitioning", "estimates",
                                        "warnings") if outcome.get(k) is not None}


def run_case(case: str, start: date, end: date, entity: str | None, estimate_only: bool = False) -> dict:
    spec = request(case, start, end, entity)
    envelope = dict(spec["window"])
    started = time.monotonic()
    estimate = extractor.handle(f"onboard-{case}", spec, lineage(spec, envelope), estimate_only=True)
    result = {"case": case, "window": spec["window"], "entity": entity, "estimate": brief(estimate)}
    if estimate_only:
        result["refused"] = estimate["status"] not in ("WITHIN_LIMITS", "APPROVED_WITH_PARTITIONING")
        return result
    parts = [spec]
    if estimate["status"] == "APPROVED_WITH_PARTITIONING":
        split = estimate["partitioning"]
        if split["kind"] != "DATE":
            result["unhandled_split"] = split
            return result
        parts = [{**spec, "data_request_id": f"onboard_{case}{i}", "window": {"from": a.isoformat(),
                                                                            "to": b.isoformat()}}
                 for i, (a, b) in enumerate(ex.split_window(start, end, split["parts"]))]
    elif estimate["status"] != "WITHIN_LIMITS":
        result["refused"] = True
        return result
    # the planner's loop (market-ai-orc data_planner.py _request_parts/_split): a part the Governor still finds too
    # large while extracting is split again and requeued, until it fits or the parts limit stops the plan
    queue, done, rows, refusals, resplits, wasted = list(parts), 0, 0, [], 0, 0.0
    while queue:
        part = queue.pop(0)
        began = time.monotonic()
        outcome = extractor.handle(f"onboard-{case}", part, lineage(part, envelope), part_count=done + len(queue) + 1)
        if outcome["status"] == "APPROVED":
            rows += int(outcome["dataset"]["row_count"])
            done += 1
        elif outcome["status"] == "APPROVED_WITH_PARTITIONING" and outcome["partitioning"]["kind"] == "DATE":
            resplits += 1
            wasted += time.monotonic() - began
            a, b = date.fromisoformat(part["window"]["from"]), date.fromisoformat(part["window"]["to"])
            queue = [{**part, "data_request_id": f"{part['data_request_id']}s{i}"[:52],
                      "window": {"from": x.isoformat(), "to": y.isoformat()}}
                     for i, (x, y) in enumerate(ex.split_window(a, b, outcome["partitioning"]["parts"]))] + queue
        else:
            refusals.append(brief(outcome))
    result.update(parts_planned=len(parts), parts_extracted=done, resplits=resplits,
                  seconds_in_resplit_parts=round(wasted, 1), governor_rows=rows, part_refusals=refusals,
                  sql_count=counted(start, end, entity), seconds=round(time.monotonic() - started, 1))
    return result


one = run_case("one", newest - timedelta(days=int(p.get("one_days", 365))), newest, p.get("entity"))
every = run_case("all", newest - timedelta(days=int(p.get("all_days", 400))), newest, None)
too_long = run_case("long", newest - timedelta(days=int(p.get("too_long_days", 2000))), newest, None,
                    estimate_only=True)
verdicts = []
for result in (one, every):
    print("OUT " + json.dumps(result, default=str), flush=True)
    fail = []
    if result.get("refused") or result.get("unhandled_split"):
        fail.append(f"not extracted: {result['estimate'].get('code')} {result['estimate'].get('message')}")
    elif result.get("part_refusals"):
        fail.append(f"{len(result['part_refusals'])} part(s) refused")
    elif result["governor_rows"] != result["sql_count"]:
        fail.append(f"Governor rows {result['governor_rows']} differ from count(*) {result['sql_count']}")
    verdicts.append({"case": result["case"], "verdict": "FAIL" if fail else "PASS", "fail": fail})
print("OUT " + json.dumps(too_long, default=str), flush=True)
refusal = too_long["estimate"]
named = bool(too_long.get("refused") and refusal.get("next_action") and refusal.get("message"))
verdicts.append({"case": "long", "verdict": "PASS" if named or not too_long.get("refused") else "FAIL",
                 "fail": [] if named or not too_long.get("refused") else ["refusal without a next action"],
                 "note": refusal.get("status") if not too_long.get("refused") else refusal.get("code")})
for v in verdicts:
    print("VERDICT " + json.dumps(v), flush=True)
print("VERDICT_TABLE " + json.dumps({"table": table, "verdict": "FAIL" if any(v["fail"] for v in verdicts)
                                     else "PASS"}), flush=True)
print("JOB_DONE GOVERNOR_CHECK", flush=True)
