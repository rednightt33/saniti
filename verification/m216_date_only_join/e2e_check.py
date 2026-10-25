"""EXEC-M216 end-to-end check, no model: the sandbox's DataNeed validator approves (or refuses) a date-only data need
against the SQL Governor's live catalog contract, the Governor's own extractor runs the approved restriction with the
privileges of market_ai_sql_reader, and the rows are compared with an independent SQL query. Read-only."""
import json, os, sys, tempfile, uuid
from contextlib import contextmanager
from datetime import date
sys.path.insert(0, "/job/sbx")
import psycopg
from psycopg import sql
import pyarrow.parquet as pq
from gov import extract as ex
from gov.catalog_contract import sha256_json
from gov.config import Settings
from gov.governor import Database, Extractor, Governor
from gov.store import LocalStore
from app.data_need import validate

def out(q, **kw): print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)

class ReaderDatabase(Database):
    @contextmanager
    def session(self):
        with super().session() as connection:
            connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier("market_ai_sql_reader")))
            yield connection

root = tempfile.mkdtemp()
env = {"SQL_GOVERNOR_API_KEY": "m216-e2e-" + "x" * 24, "GOVERNOR_DATABASE_URL": os.environ["DATABASE_URL"],
       "SQL_DATASET_LOCAL_DIR": root}
settings = Settings.from_env(env)
governor = Governor(settings, ReaderDatabase(settings), LocalStore(root))
extractor = Extractor(governor)
REF = date(2026, 10, 25)
START, END = "2026-01-01", "2026-10-23"

def pred(c, o, v): return {"type": "PREDICATE", "column": c, "operator": o, "value": v}

def req(rid, name, table, entity, time, columns, scope):
    return {"data_request_id": rid, "logical_name": name, "source_table": table, "entity_column": entity,
            "time_column": time, "columns": columns, "scope": scope,
            "time_ranges": [{"range_id": "window", "start": START, "end": END}], "source_frequency": "1D",
            "analysis_frequency": "1D", "resample": None, "history_buffer": None, "future_buffer": None,
            "ordering": [], "sampling_allowed": False}

def spec(left, right, rel):
    return {"spec_version": "data_need_spec/v2", "request_group_id": "m216_check", "revision": 1, "mode": "ANALYSIS",
            "question": "EXEC-M216 date-only join check", "subject": {"data_domain": "MARKET", "entity_type": "STOCK",
            "asset_type": "IDX_EQUITY"}, "data_requests": [left, right], "relationships": [rel]}

def relationship(contract, left_table, right_table):
    return next(r for r in contract["relationships"] if r["left_table"] == left_table and r["right_table"] == right_table)

def extract(approved, rid):
    entry = approved["requests"][rid]
    w = entry["windows"][0]
    body = {"extraction_version": "extraction_spec/v1", "data_request_id": rid, "source_table": entry["source_table"],
            "columns": entry["extract_columns"], "scope": entry["scope"], "restrictions": entry["restrictions"],
            "window": {"from": w["extract_from"], "to": w["extract_to"]}, "entity_partition": None, "order_by": []}
    lineage = {"need_id": "need_" + uuid.uuid4().hex[:24], "spec_sha256": approved["spec_sha256"],
               "request_group_id": approved["request_group_id"], "revision": 1, "data_request_id": rid,
               "logical_name": entry["logical_name"], "scope_sha256": entry["scope_sha256"],
               "restriction_sha256": entry["restriction_sha256"], "plan_id": "plan_" + uuid.uuid4().hex[:24],
               "part_key": ex.part_key(body["window"], None),
               "envelope": {"from": w["extract_from"], "to": w["extract_to"], "range_ids": ["window"]},
               "catalog_sha256": approved.get("catalog_sha256"), "extraction_sha256": ex.extraction_sha256(body)}
    outcome = extractor.handle("m216-e2e", body, lineage, part_count=1)
    if outcome.get("status") != "APPROVED":
        return outcome, None
    path = os.path.join(root, "datasets", outcome["dataset"]["dataset_id"], "data.parquet")
    return outcome, pq.read_table(path).to_pylist()

F01, F01I = "Feature_01_Stock_Daily", "Feature_01_Stock_Daily_INDEX"
F06, F06I = "Feature_06_Foreign_Domestic_Stock", "Feature_06_Foreign_Domestic_INDEX"
with psycopg.connect(os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on") as db:
    # 1. date only: BBCA and BBRI on the days IHSG fell more than 1 %
    contract = governor.catalog_contract("m216-e2e", [F01, F01I])
    rel = relationship(contract, F01, F01I)
    out("relationship", id=rel["relationship_id"], left=rel["left_columns"], right=rel["right_columns"])
    link = {"relationship_id": rel["relationship_id"], "left_request_id": "m216_check_A", "right_request_id": "m216_check_B",
            "left_columns": [], "right_columns": [], "join_type": "INNER", "join_semantics": "EXACT_DATE",
            "left_time_column": "date", "right_time_column": "date", "as_of_direction": None,
            "effective_from_column": None, "effective_to_column": None}
    stocks = req("m216_check_A", "stocks", F01, "ticker", "date", ["ticker", "date", "return_1d_pct"],
                 pred("ticker", "IN", ["BBCA", "BBRI"]))
    falls = {"type": "AND", "children": [pred("ticker", "EQ", "IHSG"), pred("return_1d_pct", "LT", -1)]}
    loose = validate(spec(stocks, req("m216_check_B", "ihsg", F01I, "ticker", "date", ["ticker", "date", "return_1d_pct"],
                                      pred("return_1d_pct", "LT", -1)), link), contract, REF)
    out("no_ticker_refused", codes=[i["code"] for i in loose.issues], note=next((i.get("note") for i in loose.issues
                                                                                 if i["code"] == "ONE_SIDE_NOT_UNIQUE"), None))
    ok = validate(spec(stocks, req("m216_check_B", "ihsg", F01I, "ticker", "date", ["ticker", "date", "return_1d_pct"],
                                   falls), link), contract, REF)
    out("approved", ok=bool(ok.approved), issues=ok.issues, warnings=[w.get("code") for w in ok.warnings])
    if ok.approved:
        outcome, rows = extract(ok.approved, "m216_check_A")
        expected = db.execute(f'''SELECT ticker, date FROM public."{F01}" WHERE ticker IN ('BBCA', 'BBRI')
            AND date BETWEEN %s AND %s AND date IN (SELECT date FROM public."{F01I}" WHERE ticker = 'IHSG' AND return_1d_pct < -1)
            ORDER BY 1, 2''', (START, END)).fetchall()
        got = sorted((r["ticker"], r["date"]) for r in rows or [])
        out("date_only_rows", status=outcome.get("status"), code=outcome.get("code"), rows=len(got),
            expected=len(expected), equal=got == [tuple(e) for e in expected], dates=sorted({str(d) for _, d in got})[:8])
        outcome_b, rows_b = extract(ok.approved, "m216_check_B")
        out("reverse_side", status=outcome_b.get("status"), rows=len(rows_b or []),
            tickers=sorted({r["ticker"] for r in rows_b or []}))
    # 2. market board pair: BBCA Regular on days the market's foreign net was negative on Regular
    contract6 = governor.catalog_contract("m216-e2e", [F06, F06I])
    rel6 = relationship(contract6, F06, F06I)
    pairs = [c for c in rel6["left_columns"] if c != "trade_date"]
    link6 = {**link, "relationship_id": rel6["relationship_id"], "left_columns": pairs, "right_columns": pairs,
             "left_time_column": "trade_date", "right_time_column": "trade_date"}
    bbca = req("m216_check_A", "bbca", F06, "ticker", "trade_date", ["ticker", "market_board", "trade_date", "foreign_net_1d"],
               {"type": "AND", "children": [pred("ticker", "EQ", "BBCA"), pred("market_board", "EQ", "Regular")]})
    market = req("m216_check_B", "market", F06I, "ticker", "trade_date", ["ticker", "market_board", "trade_date", "foreign_net_1d"],
                 {"type": "AND", "children": [pred("ticker", "EQ", "IHSG"), pred("foreign_net_1d", "LT", 0)]})
    ok6 = validate(spec(bbca, market, link6), contract6, REF)
    out("board_approved", ok=bool(ok6.approved), pairs=pairs, issues=ok6.issues)
    if ok6.approved:
        outcome, rows = extract(ok6.approved, "m216_check_A")
        expected = db.execute(f'''SELECT s.trade_date FROM public."{F06}" s WHERE s.ticker = 'BBCA' AND s.market_board = 'Regular'
            AND s.trade_date BETWEEN %s AND %s AND EXISTS (SELECT 1 FROM public."{F06I}" i WHERE i.ticker = 'IHSG'
            AND i.market_board = s.market_board AND i.trade_date = s.trade_date AND i.foreign_net_1d < 0) ORDER BY 1''',
            (START, END)).fetchall()
        got = sorted(r["trade_date"] for r in rows or [])
        out("board_rows", status=outcome.get("status"), code=outcome.get("code"), rows=len(got), expected=len(expected),
            equal=got == [e[0] for e in expected])
print("JOB_DONE", flush=True)
