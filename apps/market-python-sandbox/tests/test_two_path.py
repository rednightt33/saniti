"""Two-path analysis (Analysis Spec V2): catalog-bound specs, generic attribute scope, scope lineage proven from the
Governor's executed scope, group aggregation and top-N ranking recalculated by the validator (profile Y).

Nothing here knows about sectors, industries or banks: the catalog fixture uses those column names because the
real IDX_Stock_Universe does, and every check is the same for any catalog-approved dimension or value.
"""
from __future__ import annotations

import copy
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.logical import BindingError, GrantedFile, bind
from app.spec import AnalysisSpec, SpecInvalid
from app.spec_v2 import AnalysisSpecV2, SpecRequestAny, canonical_value, normalize_v2, scope_sha256
from app.spec import resolve_period
from conftest import CATALOG, SOURCE_CONTRACTS, FakeGovernor, catalog_subset, price_frame, requires_root, zscore_spec

REF = date(2026, 9, 23)
REFERENCE = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)
Q2 = "Berapa jumlah saham per sektor?"
Q5 = "Sebutkan 5 saham perbankan dengan kenaikan harga terbesar dalam 1 bulan terakhir."
PRICE, UNIVERSE = "Price_Stock_Indonesia_IDX", "IDX_Stock_Universe"
SUBJECT = {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"}
SCOPE_ALL = {"selection_type": "ALL_ELIGIBLE", "entities": None, "predicates": None, "provenance": "APPROVED_DEFAULT",
             "default_id": "DEFAULT_UNIVERSE_ALL_IN_SOURCE"}


def param(name, value, provenance="USER_EXPLICIT"):
    return {"name": name, "value": value, "provenance": provenance, "default_id": None}


def q2_spec(**overrides) -> dict:
    spec = {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": Q2, "subject": dict(SUBJECT),
        "inputs": [{"name": "universe", "source_table": UNIVERSE, "role": "UNIVERSE", "entity_column": None,
                    "date_column": None, "columns": ["Ticker", "Sector"]}],
        "relationships": [], "scope": dict(SCOPE_ALL), "time_scope": None,
        "calculations": [{"id": "stock_count", "method": "GROUP_AGGREGATE", "dataset": "universe", "columns": ["Ticker"],
                          "input_calculation": None, "params": [param("function", "COUNT_DISTINCT")],
                          "output_column": "stock_count", "group_by": [{"input": "universe", "column": "Sector"}],
                          "provenance": "USER_EXPLICIT"}],
        "outputs": [{"name": "stocks_per_sector", "grain": "GROUP", "coverage": "FULL", "calculations": ["stock_count"],
                     "key_columns": ["Sector"]}],
        "exclusion_rules": [], "research": None,
    }
    spec.update(overrides)
    return spec


def q5_spec(value: str = "Banks", **overrides) -> dict:
    spec = {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": Q5, "subject": dict(SUBJECT),
        "inputs": [{"name": "universe", "source_table": UNIVERSE, "role": "UNIVERSE", "entity_column": None,
                    "date_column": None, "columns": ["Ticker", "Industry"]},
                   {"name": "prices", "source_table": PRICE, "role": "PRIMARY_DATA", "entity_column": None,
                    "date_column": None, "columns": ["ticker", "date", "close"]}],
        "relationships": [{"relationship_id": 2}],
        "scope": {"selection_type": "ATTRIBUTE_FILTER", "entities": None, "provenance": "USER_EXPLICIT",
                  "default_id": None,
                  "predicates": [{"input": "universe", "table": UNIVERSE, "column": "Industry", "operator": "EQ",
                                  "value": value, "provenance": "CATALOG_RESOLVED", "user_text": "saham perbankan"}]},
        "time_scope": {"mode": "TRAILING", "count": 1, "unit": "MONTH", "frequency": "1D",
                       "provenance": "USER_EXPLICIT"},
        "calculations": [{"id": "period_return", "method": "PERIOD_RETURN", "dataset": "prices", "columns": ["close"],
                          "input_calculation": None, "params": [], "output_column": "period_return",
                          "provenance": "USER_EXPLICIT"}],
        "outputs": [{"name": "top_banks", "grain": "ENTITY", "coverage": "SELECTION", "calculations": ["period_return"],
                     "key_columns": ["ticker"],
                     "ranking": {"calculation": "period_return", "direction": "DESC", "limit": 5,
                                 "provenance": "USER_EXPLICIT"}}],
        "exclusion_rules": [], "research": None,
    }
    spec.update(overrides)
    return spec


def v2(spec: dict) -> dict:
    model = AnalysisSpecV2.model_validate(spec)
    tables = sorted({i["source_table"] for i in spec["inputs"]} |
                    {p["table"] for p in (spec["scope"].get("predicates") or [])})
    return normalize_v2(model, REF, catalog_subset(tables))


def problems(spec: dict) -> str:
    with pytest.raises(SpecInvalid) as info:
        v2(spec)
    return " | ".join(info.value.problems)


# ---------------------------------------------------------------- spec and catalog

def test_analysis_with_a_research_block_is_rejected() -> None:
    research = {"evidence_standard": "HISTORICAL_PATTERN", "objective": "x",
                "hypothesis": {"id": "H1", "statement": "s"}}
    assert "ANALYSIS_TYPE_RESEARCH_MISMATCH" in problems(q2_spec(research=research))


def test_research_without_a_research_block_is_rejected() -> None:
    assert "RESEARCH_BLOCK_REQUIRED" in problems(q2_spec(analysis_type="RESEARCH"))


def test_a_subject_that_does_not_match_the_catalog_table_is_rejected() -> None:
    assert "SUBJECT_TABLE_MISMATCH" in problems(q2_spec(subject={**SUBJECT, "entity_type": "BROKER"}))
    assert "SUBJECT_TABLE_MISMATCH" in problems(q2_spec(subject={**SUBJECT, "asset_type": "CRYPTO"}))


@pytest.mark.parametrize(("change", "code"), [
    (lambda s: s["inputs"][0].update(source_table="Invented_Table"), "UNKNOWN_TABLE"),
    (lambda s: s["inputs"][0].update(columns=["Ticker", "Sector", "made_up"]), "UNKNOWN_COLUMN"),
    (lambda s: s["inputs"][0].update(entity_column="Name"), "KEY_COLUMN_MISMATCH"),
    (lambda s: s.update(relationships=[{"relationship_id": 99}]), "UNKNOWN_RELATIONSHIP"),
])
def test_invented_catalog_names_are_rejected(change, code) -> None:
    spec = q2_spec()
    change(spec)
    assert code in problems(spec)


def test_an_invented_frequency_or_relationship_on_a_dated_spec_is_rejected() -> None:
    spec = q5_spec()
    spec["time_scope"]["frequency"] = "1W"
    assert "FREQUENCY_NOT_SUPPORTED" in problems(spec)
    spec = q5_spec(relationships=[{"relationship_id": 1}])  # Price <-> Feature_01, not an input pair
    text = problems(spec)
    assert "RELATIONSHIP_NOT_APPLICABLE" in text and "SCOPE_NOT_APPLICABLE_TO_INPUT" in text


def test_a_static_grouped_count_needs_no_time_scope() -> None:
    spec = v2(q2_spec())
    assert spec["analysis_period"]["mode"] == "STATIC" and spec["time_scope"] is None
    assert spec["outputs"][0]["key_columns"] == ["Sector"] and spec["data_plan"]["universe"]["filters"] == []
    assert resolve_period(spec["analysis_period"], REF)["mode"] == "STATIC"


def test_a_static_spec_must_not_invent_a_period() -> None:
    spec = q2_spec(time_scope={"mode": "TRAILING", "count": 1, "unit": "MONTH", "frequency": "1D",
                               "provenance": "AI_INFERRED"})
    assert "TIME_SCOPE_NOT_APPLICABLE" in problems(spec)


def test_a_temporal_metric_without_a_time_scope_is_rejected() -> None:
    assert "TIME_SCOPE_REQUIRED" in problems(q5_spec(time_scope=None))


def test_a_macro_series_without_any_stock_ticker_is_valid() -> None:
    spec = {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": "Rata-rata nilai seri CPI 12 bulan terakhir",
        "subject": {"data_domain": "MACRO", "entity_type": "SERIES", "asset_type": None},
        "inputs": [{"name": "series", "source_table": "Macro_Series_Monthly", "role": "PRIMARY_DATA",
                    "entity_column": None, "date_column": None, "columns": ["series_id", "period", "value"]}],
        "relationships": [], "scope": {"selection_type": "ENTITY_LIST", "entities": ["CPI_YOY"], "predicates": None,
                                       "provenance": "USER_EXPLICIT"},
        "time_scope": {"mode": "TRAILING", "count": 12, "unit": "MONTH", "frequency": "1M",
                       "provenance": "USER_EXPLICIT"},
        "calculations": [{"id": "cpi_avg", "method": "CUSTOM", "dataset": "series", "columns": ["value"],
                          "input_calculation": None, "params": [], "output_column": "cpi_avg",
                          "formula": "mean(value over the period)", "time_alignment": "period values only",
                          "provenance": "USER_EXPLICIT"}],
        "outputs": [{"name": "cpi", "grain": "UNSPECIFIED", "coverage": "FULL", "calculations": ["cpi_avg"]}],
        "exclusion_rules": [], "research": None,
    }
    canonical = v2(spec)
    assert canonical["subject"]["asset_type"] is None
    assert canonical["data_plan"]["series"]["filters"] == [
        {"table": "Macro_Series_Monthly", "column": "series_id", "operator": "IN", "values": ["CPI_YOY"],
         "data_type": "text"}]


def test_v1_specs_stay_v1_and_v2_specs_are_v2() -> None:
    common = {"request_id": "r", "reference_time": REFERENCE, "user_messages": [{"role": "user", "content": Q2}]}
    assert isinstance(SpecRequestAny.model_validate({**common, "spec": zscore_spec()}).spec, AnalysisSpec)
    assert isinstance(SpecRequestAny.model_validate({**common, "spec": q2_spec()}).spec, AnalysisSpecV2)
    with pytest.raises(Exception):
        SpecRequestAny.model_validate({**common, "spec": {**q2_spec(), "universe": {"type": "ALL_IN_SOURCE"}}})


def test_attribute_predicates_are_typed_and_must_be_filterable() -> None:
    spec = q5_spec()
    spec["scope"]["predicates"][0].update(column="Shares", value="many")
    assert "INVALID_PREDICATE_VALUE" in problems(spec)
    spec = q5_spec()
    spec["inputs"][1]["columns"].append("query_date")
    spec["scope"]["predicates"].append({"input": "prices", "table": PRICE, "column": "query_date", "operator": "EQ",
                                        "value": "2026-09-01", "provenance": "AI_INFERRED", "user_text": None})
    assert "FILTER_NOT_ALLOWED" in problems(spec)
    spec = q5_spec()
    spec["scope"]["predicates"][0]["user_text"] = None
    assert "PREDICATE_USER_TEXT_REQUIRED" in problems(spec)


def test_the_attribute_scope_compiles_into_the_same_plan_for_every_scoped_input() -> None:
    spec = v2(q5_spec())
    plan = spec["data_plan"]
    predicate = {"table": UNIVERSE, "column": "Industry", "operator": "EQ", "values": ["Banks"], "data_type": "text"}
    assert plan["universe"]["filters"] == [predicate] and plan["universe"]["joins"] == []
    assert plan["prices"]["filters"] == [predicate]
    assert plan["prices"]["joins"] == [{"table": UNIVERSE, "relationship_id": 2}]
    # any other catalog value or dimension gives the same shape: nothing is special about this one
    other = v2(q5_spec(value="Industry-3"))["data_plan"]["prices"]
    assert other["filters"][0]["values"] == ["Industry-3"] and other["joins"] == plan["prices"]["joins"]


def test_the_scope_hash_changes_with_the_predicate_and_nothing_else() -> None:
    ref_period = {"mode": "TRAILING", "start": "2026-08-24", "end": "2026-09-23"}
    banks, again, other = (scope_sha256(v2(q5_spec(value)), ref_period) for value in ("Banks", "Banks", "Energy"))
    assert banks == again and banks != other


def test_canonical_values_equal_the_governor_implementation() -> None:
    path = Path(__file__).resolve().parents[2] / "market-sql-governor" / "app" / "catalog_contract.py"
    module_spec = importlib.util.spec_from_file_location("governor_catalog_contract", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    for value in ("Banks", 5, 5.0, 0.1, 1e-7, -0.0, True, False, date(2026, 9, 1), 12345678901234):
        assert canonical_value(value) == module.canonical_value(value)


# ---------------------------------------------------------------- scope lineage at binding

def contract_for(spec: dict, spec_id: str = "spec_" + "a" * 24) -> dict:
    canonical = v2(spec)
    plan = canonical.pop("data_plan")
    for entry in plan.values():
        entry["date_range"] = {"column": entry["time_column"], "from": "2026-08-12", "to": "2026-09-23"} \
            if entry["time_column"] else None
    return {"spec_id": spec_id, "spec_sha256": "b" * 64, "spec_version": "analysis_spec/v2", "scope_sha256": "c" * 64,
            "data_plan": plan, "spec": canonical,
            "catalog": {"tables": {t: m["catalog_table_sha256"] for t, m in CATALOG["tables"].items()},
                        "source_contracts": {}}}


def executed(plan: dict, date_range: tuple[str, str] | None = None, *, filters: list | None = None,
             joins: list | None = None, table: str | None = None) -> dict:
    items = copy.deepcopy(plan["filters"] if filters is None else filters)
    if date_range:
        items.append({"table": plan["source_table"], "column": plan["time_column"], "operator": "BETWEEN",
                      "values": list(date_range)})
    return {"source_table": table or plan["source_table"],
            "tables": [plan["source_table"]] + [j["table"] for j in (plan["joins"] if joins is None else joins)],
            "joins": plan["joins"] if joins is None else joins, "filters": items, "group_by": []}


def lineage(contract: dict, name: str, part: int = 1, count: int = 1, **overrides) -> dict:
    return {"spec_id": contract["spec_id"], "spec_sha256": contract["spec_sha256"],
            "scope_sha256": contract["scope_sha256"], "data_plan_id": "plan_" + "d" * 24, "logical_input_name": name,
            "part_index": part, "part_count": count, "request_sha256": "e" * 64, **overrides}


def prices_file(governor, contract, *, parts=((1, 1, ("2026-08-12", "2026-09-23")),), frame=None, **changes):
    plan = contract["data_plan"]["prices"]
    frame = frame if frame is not None else price_frame({"BBCA": ("2026-08-01", 40)})
    ids = []
    for part, count, window in parts:
        scope = executed(plan, window, filters=changes.get("filters"), joins=changes.get("joins"),
                         table=changes.get("table"))
        ids.append(governor.add(frame, lineage=changes.get("lineage") or lineage(contract, "prices", part, count),
                                executed_scope=scope, source_contracts=contracts(scope)))
    return ids


def contracts(scope: dict) -> dict:
    """The Governor attaches the source contract of every table it read, joined tables included."""
    return {t: SOURCE_CONTRACTS[t] for t in scope["tables"]}


def bind_prices(governor, contract, ids):
    files = {ds: GrantedFile(ds, governor.datasets[ds]["manifest"], f"input_{i}.parquet") for i, ds in enumerate(ids)}
    scope = executed(contract["data_plan"]["universe"])
    universe = governor.add(pd.DataFrame({"Ticker": ["BBCA"], "Industry": ["Banks"]}), source_table=UNIVERSE,
                            lineage=lineage(contract, "universe"), executed_scope=scope,
                            source_contracts=contracts(scope))
    files[universe] = GrantedFile(universe, governor.datasets[universe]["manifest"], "input_u.parquet")
    return bind(contract["spec"], [{"name": "prices", "dataset_ids": ids},
                                   {"name": "universe", "dataset_ids": [universe]}], files, 8, contract)


def test_the_approved_attribute_scope_is_proven_from_the_executed_scope(sandbox_root) -> None:
    governor, contract = FakeGovernor(sandbox_root), contract_for(q5_spec())
    logical = bind_prices(governor, contract, prices_file(governor, contract))
    evidence = logical["prices"]["scope_evidence"]
    assert evidence["result"] == "PASS" and evidence["joins"] == [[UNIVERSE, 2]]
    assert evidence["filters"] == [{"table": UNIVERSE, "column": "Industry", "operator": "EQ", "values": ["Banks"],
                                    "data_type": "text"}]
    assert logical["prices"]["grain"] == ["ticker", "date"]  # from the Governor's source contract, not a dictionary


@pytest.mark.parametrize(("changes", "code"), [
    ({"filters": [{"table": UNIVERSE, "column": "Industry", "operator": "EQ", "values": ["Energy"]}]},
     "EXECUTED_SCOPE_MISMATCH"),                                             # predicate changed after approval
    ({"filters": []}, "EXECUTED_SCOPE_MISMATCH"),                            # predicate dropped
    ({"joins": []}, "EXECUTED_SCOPE_MISMATCH"),                              # relationship dropped
    ({"table": "Feature_01_Stock_Daily"}, "EXECUTED_SCOPE_MISMATCH"),        # another source table
])
def test_any_change_between_approved_and_executed_scope_refuses_the_binding(sandbox_root, changes, code) -> None:
    governor, contract = FakeGovernor(sandbox_root), contract_for(q5_spec())
    with pytest.raises(BindingError) as info:
        bind_prices(governor, contract, prices_file(governor, contract, **changes))
    assert info.value.code == code


def test_a_dataset_prepared_for_another_spec_or_without_lineage_is_refused(sandbox_root) -> None:
    governor, contract = FakeGovernor(sandbox_root), contract_for(q5_spec())
    other = lineage(contract, "prices", spec_id="spec_" + "f" * 24)
    with pytest.raises(BindingError) as info:
        bind_prices(governor, contract, prices_file(governor, contract, lineage=other))
    assert info.value.code == "SCOPE_LINEAGE_MISMATCH"
    plain = governor.add(price_frame({"BBCA": ("2026-08-01", 40)}))
    with pytest.raises(BindingError) as info:
        bind_prices(governor, contract, [plain])
    assert info.value.code == "SCOPE_LINEAGE_MISSING"


def test_a_different_catalog_version_is_refused(sandbox_root) -> None:
    governor, contract = FakeGovernor(sandbox_root), contract_for(q5_spec())
    contract["catalog"]["tables"][PRICE] = "9" * 64
    with pytest.raises(BindingError) as info:
        bind_prices(governor, contract, prices_file(governor, contract))
    assert info.value.code == "CATALOG_VERSION_MISMATCH"


def test_partitions_must_cover_the_plan_without_gaps_or_overlaps(sandbox_root) -> None:
    governor, contract = FakeGovernor(sandbox_root), contract_for(q5_spec())
    halves = ((1, 2, ("2026-08-12", "2026-08-31")), (2, 2, ("2026-09-01", "2026-09-23")))
    logical = bind_prices(governor, contract, prices_file(governor, contract, parts=halves))
    assert logical["prices"]["scope_evidence"]["parts"] == 2
    cases = {
        "PARTITION_MISSING": halves[:1],
        "PARTITION_GAP": ((1, 2, ("2026-08-12", "2026-08-30")), (2, 2, ("2026-09-01", "2026-09-23"))),
        "PARTITION_OVERLAP": ((1, 2, ("2026-08-12", "2026-09-02")), (2, 2, ("2026-09-01", "2026-09-23"))),
        "DATE_RANGE_NOT_COVERED": ((1, 1, ("2026-08-20", "2026-09-23")),),
    }
    for code, parts in cases.items():
        with pytest.raises(BindingError) as info:
            bind_prices(governor, contract, prices_file(governor, contract, parts=parts))
        assert info.value.code == code, code


# ---------------------------------------------------------------- end to end through the service (profile Y)

UNIVERSE_ROWS = pd.DataFrame({
    "Ticker": [f"B{i:02d}" for i in range(8)] + [f"E{i:02d}" for i in range(5)] + ["X01", "X02"],
    "Sector": ["Financials"] * 8 + ["Energy"] * 5 + ["0", None],
    "Industry": ["Banks"] * 8 + ["Oil"] * 5 + ["Other", "Other"],
})
Q2_CODE = '''
df = saniti.load("universe", columns=["Ticker", "Sector"])
out = df.groupby("Sector", dropna=False)["Ticker"].nunique().reset_index(name="stock_count")
saniti.emit_table("stocks_per_sector", out)
'''
Q5_CODE = '''
df = saniti.load("prices", columns=["ticker", "date", "close"])
df["date"] = pd.to_datetime(df["date"])
start, end = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
rows = []
for ticker, g in df.sort_values("date").groupby("ticker"):
    before, inside = g[g["date"] < start], g[(g["date"] >= start) & (g["date"] <= end)]
    if len(before) and len(inside):
        rows.append({"ticker": ticker, "date": inside["date"].iloc[-1].date(),
                     "period_return": inside["close"].iloc[-1] / before["close"].iloc[-1] - 1})
out = pd.DataFrame(rows).sort_values(["period_return", "ticker"], ascending=[False, True])
'''


def approve(service, spec: dict, message: str, request_id: str = "req") -> dict:
    review = service.create_spec(SpecRequestAny.model_validate({
        "request_id": request_id, "reference_time": REFERENCE,
        "user_messages": [{"role": "user", "content": message}], "spec": spec}))
    assert review.get("spec_id"), review
    return review


def prepare(service, governor, review: dict, frames: dict[str, pd.DataFrame], request_id: str = "req"):
    """What market-ai-orc's compiler + the Governor produce for an approved plan (lineage + executed scope)."""
    stored = service.get_spec(review["spec_id"])
    inputs = []
    for name, entry in stored["data_plan"].items():
        window = entry["date_range"]
        scope = executed(entry, (window["from"], window["to"]) if window else None)
        ds = governor.add(frames[name], source_table=entry["source_table"], source_contracts=contracts(scope),
                          requested_from=window["from"] if window else None,
                          requested_to=window["to"] if window else None,
                          lineage={"spec_id": review["spec_id"], "spec_sha256": stored["spec_sha256"],
                                   "scope_sha256": stored["scope_sha256"], "data_plan_id": "plan_" + "1" * 24,
                                   "logical_input_name": name, "part_index": 1, "part_count": 1,
                                   "request_sha256": "2" * 64},
                          executed_scope=scope)
        inputs.append({"name": name, "dataset_ids": [ds], "duplicate_policy": "ERROR_ON_CONFLICT"})
    return inputs


def run(service, review, inputs, code, request_id: str = "req") -> dict:
    from app.models import AnalysisRequest

    return service.submit(AnalysisRequest(request_id=request_id, spec_id=review["spec_id"], python_code=code,
                                          inputs=inputs, expected_outputs=["TABLE"]))


def bank_prices() -> pd.DataFrame:
    return price_frame({f"B{i:02d}": ("2026-08-03", 38) for i in range(8)}, seed=5)


@requires_root
def test_q2_count_per_group_is_calculation_verified_without_a_period(make_service, governor) -> None:
    service = make_service()
    review = approve(service, q2_spec(), Q2)
    assert review["validation_profile"] == "Y_ANALYSIS" and review["resolved_period"]["mode"] == "STATIC"
    assert review["next_action"] == "PREPARE_DATA_THEN_RUN_ANALYSIS"
    result = run(service, review, prepare(service, governor, review, {"universe": UNIVERSE_ROWS}), Q2_CODE)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    checks = {e["check"]: e for e in result["validation_evidence"]}
    assert checks["output.stocks_per_sector.groups"]["groups"] == 4  # Financials, Energy, "0", and the null group
    assert checks["scope.lineage.universe"]["result"] == "PASS"


@requires_root
def test_q2_omitted_groups_and_cross_group_contamination_fail(make_service, governor) -> None:
    service = make_service()
    review = approve(service, q2_spec(), Q2)
    inputs = prepare(service, governor, review, {"universe": UNIVERSE_ROWS})
    omitted = run(service, review, inputs, Q2_CODE.replace("reset_index(name=\"stock_count\")",
                                                         "reset_index(name=\"stock_count\").dropna()"))
    assert omitted["validation_status"] == "FAILED" and "GROUP_COVERAGE_MISMATCH" in omitted["reason_codes"]
    moved = Q2_CODE.replace("saniti.emit_table", "out.loc[out['Sector'] == 'Energy', 'stock_count'] += 1\n"
                                                 "out.loc[out['Sector'] == 'Financials', 'stock_count'] -= 1\n"
                                                 "saniti.emit_table")
    contaminated = run(service, review, inputs, moved)
    assert contaminated["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in contaminated["reason_codes"]


@requires_root
def test_q2_unknown_values_follow_the_declared_policy(make_service, governor) -> None:
    service = make_service()
    spec = q2_spec()
    spec["calculations"][0]["params"] += [param("unknown_group_values", ["0"], "AI_INFERRED"),
                                          param("missing_group_policy", "EXCLUDE", "AI_INFERRED")]
    review = approve(service, spec, Q2)
    inputs = prepare(service, governor, review, {"universe": UNIVERSE_ROWS})
    code = Q2_CODE.replace('df = saniti.load("universe", columns=["Ticker", "Sector"])',
                           'df = saniti.load("universe", columns=["Ticker", "Sector"])\n'
                           'df = df[df["Sector"].notna() & (df["Sector"] != "0")]')
    result = run(service, review, inputs, code)
    assert result["validation_status"] == "PASS", result["validation_evidence"]
    assert {e["check"]: e for e in result["validation_evidence"]}["output.stocks_per_sector.groups"]["groups"] == 2


@requires_root
def test_q5_top_five_of_the_complete_attribute_scope_passes(make_service, governor) -> None:
    service = make_service()
    review = approve(service, q5_spec(), Q5)
    assert review["status"] == "APPROVED_WITH_UNVERIFIED"  # the catalog-resolved predicate is disclosed
    disclosed = [u["requirement"] for u in review["unverified_requirements"]]
    assert "scope.IDX_Stock_Universe.Industry" in disclosed
    frames = {"universe": UNIVERSE_ROWS[UNIVERSE_ROWS["Industry"] == "Banks"][["Ticker", "Industry"]],
              "prices": bank_prices()}
    result = run(service, review, prepare(service, governor, review, frames),
                 Q5_CODE + 'saniti.emit_table("top_banks", out.head(5))\n')
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    checks = {e["check"]: e for e in result["validation_evidence"]}
    assert checks["output.top_banks.ranking"]["candidates"] == 8
    assert checks["scope.lineage.prices"]["filters"][0]["values"] == ["Banks"]
    assert checks["scope.population"]["members"] == 8


@requires_root
def test_q5_a_wrong_top_five_with_exactly_five_rows_fails(make_service, governor) -> None:
    service = make_service()
    review = approve(service, q5_spec(), Q5)
    frames = {"universe": UNIVERSE_ROWS[UNIVERSE_ROWS["Industry"] == "Banks"][["Ticker", "Industry"]],
              "prices": bank_prices()}
    inputs = prepare(service, governor, review, frames)
    # ranks 2-6: still five rows, values all correct, but not the top five of the population
    result = run(service, review, inputs, Q5_CODE + 'saniti.emit_table("top_banks", out.iloc[1:6])\n')
    assert result["validation_status"] == "FAILED" and "RANKING_MISMATCH" in result["reason_codes"]


@requires_root
def test_q5_a_dataset_whose_predicate_was_dropped_cannot_pass(make_service, governor) -> None:
    service = make_service()
    review = approve(service, q5_spec(), Q5)
    frames = {"universe": UNIVERSE_ROWS[["Ticker", "Industry"]], "prices": bank_prices()}
    inputs = prepare(service, governor, review, frames)
    # the prices dataset claims this spec's lineage but was extracted without the attribute predicate
    ds = inputs[1]["dataset_ids"][0] if inputs[1]["name"] == "prices" else inputs[0]["dataset_ids"][0]
    governor.datasets[ds]["manifest"]["validator_manifest"]["executed_scope"]["filters"] = [
        f for f in governor.datasets[ds]["manifest"]["validator_manifest"]["executed_scope"]["filters"]
        if f["column"] != "Industry"]
    result = run(service, review, inputs, Q5_CODE + 'saniti.emit_table("top_banks", out.head(5))\n')
    assert result["validation_status"] == "FAILED" and result["reason_codes"] == ["EXECUTED_SCOPE_MISMATCH"]


@requires_root
def test_ordinary_analysis_does_not_consume_a_research_experiment(make_service, governor) -> None:
    service = make_service()
    approve(service, q2_spec(), Q2)
    approve(service, q5_spec(), Q5)
    summary = service.run_summary("req")
    assert summary["budget"]["research"]["experiments"]["used"] == 0


# ---------------------------------------------------------------- period statistics, segments, group series (Q3/Q6/Q7)

Q3 = "Sektor mana yang memiliki rata-rata return tertinggi selama Agustus 2026? Tampilkan 3 sektor teratas."
Q3_ASKED = ("Apakah yang dimaksud (a) return total tiap saham selama Agustus lalu dirata-rata per sektor, atau (b) "
            "rata-rata return harian tiap saham?")
Q6 = ("Bandingkan volatilitas harian (standar deviasi return harian) rata-rata saham sektor energi dengan sektor "
      "teknologi selama 3 bulan terakhir.")
Q7 = ("Berapa korelasi return harian antara rata-rata sektor perbankan dan rata-rata sektor properti sejak 1 Juli "
      "2026?")
GROUPED = pd.DataFrame({
    "Ticker": [f"B{i:02d}" for i in range(6)] + ["F00", "F01"] + [f"E{i:02d}" for i in range(4)] +
              [f"T{i:02d}" for i in range(4)] + [f"P{i:02d}" for i in range(4)],
    "Sector": ["Financials"] * 8 + ["Energy"] * 4 + ["Technology"] * 4 + ["Properties & Real Estate"] * 4,
    "Industry": ["Banks"] * 6 + ["Insurance"] * 2 + ["Oil"] * 4 + ["Software"] * 4 + ["Real Estate"] * 4,
})


def grouped_prices() -> pd.DataFrame:
    return price_frame({t: ("2026-06-01", 83) for t in GROUPED["Ticker"]}, seed=9)


def two_inputs(universe_columns: list[str]) -> list[dict]:
    return [{"name": "universe", "source_table": UNIVERSE, "role": "UNIVERSE", "entity_column": None,
             "date_column": None, "columns": ["Ticker", *universe_columns]},
            {"name": "prices", "source_table": PRICE, "role": "PRIMARY_DATA", "entity_column": None,
             "date_column": None, "columns": ["ticker", "date", "close"]}]


def calc(cid, method, *, columns=None, upstream=None, params=(), provenance="USER_EXPLICIT", **extra) -> dict:
    return {"id": cid, "method": method, "dataset": "prices", "columns": columns or [], "input_calculation": upstream,
            "params": list(params), "output_column": cid, "provenance": provenance, **extra}


def q3_spec(measure: str = "PERIOD", provenance: str = "AI_INFERRED") -> dict:
    if measure == "PERIOD":
        per_stock = [calc("stock_return", "PERIOD_RETURN", columns=["close"], provenance=provenance)]
    else:
        per_stock = [calc("daily_return", "RETURN", columns=["close"], params=[param("horizon", 1, "AI_INFERRED")]),
                     calc("stock_return", "PERIOD_STAT", upstream="daily_return", params=[param("function", "AVG")],
                          provenance=provenance)]
    return {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": Q3, "subject": dict(SUBJECT),
        "inputs": two_inputs(["Sector"]), "relationships": [{"relationship_id": 2}], "scope": dict(SCOPE_ALL),
        "time_scope": {"mode": "EXPLICIT_DATES", "start": "2026-08-01", "end": "2026-08-31", "frequency": "1D",
                       "provenance": "USER_EXPLICIT"},
        "calculations": per_stock + [calc("sector_avg", "GROUP_AGGREGATE", upstream="stock_return",
                                          params=[param("function", "AVG")],
                                          group_by=[{"input": "universe", "column": "Sector"}])],
        "outputs": [{"name": "top_sectors", "grain": "GROUP", "coverage": "SELECTION", "calculations": ["sector_avg"],
                     "key_columns": ["Sector"],
                     "ranking": {"calculation": "sector_avg", "direction": "DESC", "limit": 3,
                                 "provenance": "USER_EXPLICIT"}}],
        "exclusion_rules": [], "research": None,
    }


def q6_spec(function: str = "STD") -> dict:
    return {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": Q6, "subject": dict(SUBJECT),
        "inputs": two_inputs(["Sector"]), "relationships": [{"relationship_id": 2}],
        "scope": {"selection_type": "ATTRIBUTE_FILTER", "entities": None, "provenance": "USER_EXPLICIT",
                  "predicates": [{"input": "universe", "table": UNIVERSE, "column": "Sector", "operator": "IN",
                                  "value": ["Energy", "Technology"], "provenance": "CATALOG_RESOLVED",
                                  "user_text": "sektor energi dengan sektor teknologi"}]},
        "time_scope": {"mode": "TRAILING", "count": 3, "unit": "MONTH", "frequency": "1D", "provenance": "USER_EXPLICIT"},
        "calculations": [calc("daily_return", "RETURN", columns=["close"], params=[param("horizon", 1)]),
                         calc("volatility", "PERIOD_STAT", upstream="daily_return", params=[param("function", function)]),
                         calc("sector_volatility", "GROUP_AGGREGATE", upstream="volatility",
                              params=[param("function", "AVG")], group_by=[{"input": "universe", "column": "Sector"}])],
        "outputs": [{"name": "sector_volatility", "grain": "GROUP", "coverage": "FULL",
                     "calculations": ["sector_volatility"], "key_columns": ["Sector"]}],
        "exclusion_rules": [], "research": None,
    }


def segment(label: str, column: str, value, words: str) -> dict:
    return {"label": label, "predicates": [{"input": "universe", "column": column, "operator": "EQ", "value": value}],
            "provenance": "CATALOG_RESOLVED", "user_text": words}


def q7_spec(segments: list | None = None) -> dict:
    segments = segments or [segment("banks", "Industry", "Banks", "sektor perbankan"),
                            segment("property", "Sector", "Properties & Real Estate", "sektor properti")]
    return {
        "spec_version": "2.0", "analysis_type": "ANALYSIS", "question": Q7, "subject": dict(SUBJECT),
        "inputs": two_inputs(["Sector", "Industry"]), "relationships": [{"relationship_id": 2}],
        "scope": dict(SCOPE_ALL),
        "time_scope": {"mode": "EXPLICIT_DATES", "start": "2026-07-01", "end": "2026-09-23", "frequency": "1D",
                       "provenance": "USER_EXPLICIT"},
        "calculations": [calc("daily_return", "RETURN", columns=["close"], params=[param("horizon", 1)]),
                         calc("group_return", "GROUP_AGGREGATE", upstream="daily_return",
                              params=[param("function", "AVG"), param("per_date", True)], segments=segments),
                         calc("correlation", "GROUP_CORRELATION", upstream="group_return")],
        "outputs": [{"name": "group_series", "grain": "GROUP_DATE", "coverage": "FULL", "calculations": ["group_return"],
                     "key_columns": ["segment", "date"]},
                    {"name": "series_correlation", "grain": "GROUP_PAIR", "coverage": "FULL",
                     "calculations": ["correlation"], "key_columns": ["segment_a", "segment_b"]}],
        "exclusion_rules": [], "research": None,
    }


def ask(service, spec: dict, *messages: str, request_id: str = "req") -> dict:
    roles = ["user", "assistant"] * len(messages)
    return service.create_spec(SpecRequestAny.model_validate({
        "request_id": request_id, "reference_time": REFERENCE, "spec": spec,
        "user_messages": [{"role": role, "content": text} for role, text in zip(roles, messages)]}))


PRICE_RETURNS = '''
prices = saniti.load("prices", columns=["ticker", "date", "close"])
uni = saniti.load("universe")
prices["date"] = pd.to_datetime(prices["date"])
prices = prices.sort_values(["ticker", "date"])
prices["daily_return"] = prices.groupby("ticker")["close"].pct_change(fill_method=None)
start, end = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
inside = prices[(prices["date"] >= start) & (prices["date"] <= end)].merge(uni, left_on="ticker", right_on="Ticker")
'''
Q3_CODE = '''
prices = saniti.load("prices", columns=["ticker", "date", "close"])
uni = saniti.load("universe")
prices["date"] = pd.to_datetime(prices["date"])
start, end = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
rows = []
for ticker, g in prices.sort_values("date").groupby("ticker"):
    before, inside = g[g["date"] < start], g[(g["date"] >= start) & (g["date"] <= end)]
    if len(before) and len(inside):
        rows.append({"ticker": ticker, "stock_return": inside["close"].iloc[-1] / before["close"].iloc[-1] - 1})
per_stock = pd.DataFrame(rows).merge(uni, left_on="ticker", right_on="Ticker")
out = per_stock.groupby("Sector")["stock_return"].mean().reset_index(name="sector_avg")
out = out.sort_values(["sector_avg", "Sector"], ascending=[False, True]).head(3)
saniti.emit_table("top_sectors", out)
'''
Q6_CODE = PRICE_RETURNS + '''
vol = inside.groupby(["ticker", "Sector"])["daily_return"].std(ddof=1).reset_index(name="volatility")
out = vol.groupby("Sector")["volatility"].mean().reset_index(name="sector_volatility")
saniti.emit_table("sector_volatility", out)
'''
Q7_CODE = PRICE_RETURNS + '''
members = {"banks": inside["Industry"] == "Banks", "property": inside["Sector"] == "Properties & Real Estate"}
series = pd.concat([inside[m].groupby("date")["daily_return"].mean().rename(k) for k, m in members.items()], axis=1)
long = series.reset_index().melt(id_vars="date", var_name="segment", value_name="group_return")
saniti.emit_table("group_series", long)
pair = pd.DataFrame([{"segment_a": "banks", "segment_b": "property",
                      "correlation": series["banks"].corr(series["property"])}])
saniti.emit_table("series_correlation", pair)
'''


def test_period_stat_and_group_correlation_normalize_generically() -> None:
    q6 = v2(q6_spec())
    vol = next(c for c in q6["calculations"] if c["id"] == "volatility")
    assert vol["covers"] == ["STD"] and {p["name"]: p["value"] for p in vol["params"]}["ddof"] == 1
    assert "annualized" in vol["formula"] and vol["params"][0]["default_id"] in (None, "DEFAULT_PERIOD_STD_DDOF")
    mean = next(c for c in v2(q6_spec("MEAN"))["calculations"] if c["id"] == "volatility")
    assert "ddof" not in {p["name"] for p in mean["params"]} and mean["covers"] == []
    q7 = v2(q7_spec())
    series = next(c for c in q7["calculations"] if c["id"] == "group_return")
    assert [p["name"] for p in series["params"]] == ["function", "per_date", "min_observations"]
    assert series["segments"][0]["predicates"] == [{"input": "universe", "column": "Industry", "operator": "EQ",
                                                    "values": ["Banks"], "data_type": "text"}]
    outputs = {o["name"]: o for o in q7["outputs"]}
    assert outputs["group_series"]["key_columns"] == ["segment", "date"]
    assert outputs["series_correlation"]["key_columns"] == ["segment_a", "segment_b"]
    assert "Industry" in q7["data_plan"]["universe"]["columns"]


@pytest.mark.parametrize(("change", "code"), [
    (lambda s: s["calculations"][1].update(group_by=[{"input": "universe", "column": "Sector"}]), "either group_by"),
    (lambda s: s["calculations"][1]["segments"][0]["predicates"][0].update(column="Invented"), "UNKNOWN_COLUMN"),
    (lambda s: s["calculations"][1]["segments"][0]["predicates"][0].update(input="prices", column="query_date"),
     "FILTER_NOT_ALLOWED"),
    (lambda s: s["calculations"][1]["segments"][0]["predicates"][0].update(value=["Banks"]),
     "INVALID_PREDICATE_VALUE"),
    (lambda s: s["calculations"][1]["segments"][1].update(label="BANKS"), "labels must be unique"),
    (lambda s: s["calculations"][1]["segments"][0].update(user_text=None), "PREDICATE_USER_TEXT_REQUIRED"),
    (lambda s: s["calculations"][1]["params"].pop(), "per_date GROUP_AGGREGATE"),
    (lambda s: s["calculations"][2].update(input_calculation="daily_return"), "per_date GROUP_AGGREGATE"),
    (lambda s: s["outputs"][1].update(grain="GROUP"), "GROUP_CORRELATION calculations produce GROUP_PAIR"),
    (lambda s: s["calculations"].append(calc("bad", "PERIOD_STAT", upstream="group_return",
                                             params=[param("function", "MEAN")])), "per group, not per entity"),
])
def test_invalid_segments_and_group_series_are_rejected(change, code) -> None:
    spec = q7_spec()
    change(spec)
    assert code in problems(spec)


def test_period_stat_rejects_a_period_without_a_start_and_ddof_outside_std() -> None:
    spec = q6_spec()
    spec["time_scope"] = {"mode": "LATEST", "frequency": "1D", "provenance": "USER_EXPLICIT"}
    assert "PERIOD_STAT needs a period with a start" in problems(spec)
    spec = q6_spec("MEAN")
    spec["calculations"][1]["params"].append(param("ddof", 1))
    assert "ddof applies to PERIOD_STAT function STD only" in problems(spec)


def test_v1_specs_cannot_use_segments() -> None:
    spec = zscore_spec()
    spec["calculations"].append({"id": "g", "method": "GROUP_AGGREGATE", "dataset": "prices", "columns": ["close"],
                                 "input_calculation": None, "params": [param("function", "AVG")], "output_column": "g",
                                 "provenance": "AI_INFERRED",
                                 "segments": [{"label": "a", "predicates": [{"input": "prices", "column": "ticker",
                                                                             "operator": "EQ", "value": "BBCA"}]}]})
    from app.spec import normalize
    with pytest.raises(SpecInvalid) as info:
        normalize(AnalysisSpec.model_validate(spec), REF)
    assert "segments need an Analysis Spec V2" in info.value.problems[0]


def test_segment_membership_matches_the_governor_canonical_values() -> None:
    import numpy as np
    sys_path = str(Path(__file__).resolve().parents[1] / "runtime")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    import validator

    for value in ("Banks", 5, 5.0, 0.1, 1e-7, -0.0, True, False, 12345678901234, np.int64(5), np.float64(5.0)):
        assert validator._canonical(value, None) == canonical_value(value.item() if hasattr(value, "item") else value)
    assert validator._canonical(pd.Timestamp("2026-09-01"), "date") == canonical_value(date(2026, 9, 1))
    predicate = {"operator": "GTE", "values": ["10"], "data_type": "numeric"}
    assert validator._segment_mask([9.5, 10, 10.0, None, 11], predicate).tolist() == [False, True, True, False, True]
    predicate = {"operator": "IN", "values": ["Banks", "Oil"], "data_type": "text"}
    assert validator._segment_mask(["Banks", "Bank", None, "Oil"], predicate).tolist() == [True, False, False, True]


def test_q3_an_unstated_return_basis_needs_clarification(make_service) -> None:
    service = make_service()
    review = ask(service, q3_spec(), Q3)
    assert review["status"] == "NEEDS_CLARIFICATION" and review["next_action"] == "ASK_USER_CLARIFICATION"
    assert "PERIOD_RETURN" in review["clarification_needed"][0] and "spec_id" not in review
    daily = ask(service, q3_spec("DAILY"), Q3)
    assert daily["status"] == "NEEDS_CLARIFICATION"


def test_q3_a_stated_basis_must_match_the_spec(make_service) -> None:
    service = make_service()
    stated = Q3.replace("rata-rata return", "rata-rata return harian")
    review = ask(service, q3_spec("PERIOD"), stated)
    assert review["status"] == "ANALYSIS_SPEC_MISMATCH"
    assert [m["code"] for m in review["mismatches"]] == ["RETURN_BASIS_MISMATCH"]
    assert ask(service, q3_spec("DAILY"), stated)["status"] in ("APPROVED", "APPROVED_WITH_UNVERIFIED")


def test_q3_a_clarification_reply_settles_the_basis(make_service) -> None:
    service = make_service()
    worded = ask(service, q3_spec(), Q3, Q3_ASKED, "Return total tiap saham selama Agustus, lalu rata-rata per sektor.")
    assert worded.get("spec_id"), worded
    checks = {c["requirement"]: c for c in worded["checks"]}
    assert checks["calculation.sector_avg.return_basis"]["result"] == "MATCH"
    chosen = ask(service, q3_spec(provenance="USER_CLARIFIED"), Q3, Q3_ASKED, "Yang (a).", request_id="req2")
    assert chosen.get("spec_id") and chosen["status"] == "APPROVED_WITH_UNVERIFIED"
    unclaimed = ask(service, q3_spec(), Q3, Q3_ASKED, "Yang (a).", request_id="req3")
    assert unclaimed["status"] == "NEEDS_CLARIFICATION"  # the reply exists, but the spec does not claim it


def test_q6_volatility_must_be_a_standard_deviation_of_daily_returns(make_service) -> None:
    service = make_service()
    review = ask(service, q6_spec("MEAN"), Q6)  # a different endpoint statistic instead of the standard deviation
    assert review["status"] == "ANALYSIS_SPEC_MISMATCH"
    assert "MISSING_REQUESTED_CALCULATION" in {m["code"] for m in review["mismatches"]}


@requires_root
def test_q3_top_three_groups_of_period_returns_are_calculation_verified(make_service, governor) -> None:
    service = make_service()
    review = ask(service, q3_spec(), Q3, Q3_ASKED, "Return total tiap saham selama Agustus, lalu rata-rata per sektor.")
    frames = {"universe": GROUPED[["Ticker", "Sector"]], "prices": grouped_prices()}
    inputs = prepare(service, governor, review, frames)
    result = run(service, review, inputs, Q3_CODE)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    checks = {e["check"]: e for e in result["validation_evidence"]}
    assert checks["output.top_sectors.ranking"]["candidates"] == 4
    wrong = run(service, review, inputs, Q3_CODE.replace(".head(3)", ".iloc[1:4]"))
    assert wrong["validation_status"] == "FAILED" and "RANKING_MISMATCH" in wrong["reason_codes"]


@requires_root
def test_q6_group_average_of_period_volatility_is_calculation_verified(make_service, governor) -> None:
    service = make_service()
    review = ask(service, q6_spec(), Q6)
    assert review.get("spec_id"), review
    kept = GROUPED[GROUPED["Sector"].isin(["Energy", "Technology"])]
    prices = grouped_prices()
    frames = {"universe": kept[["Ticker", "Sector"]], "prices": prices[prices["ticker"].isin(kept["Ticker"])]}
    inputs = prepare(service, governor, review, frames)
    result = run(service, review, inputs, Q6_CODE)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    assert {e["check"]: e for e in result["validation_evidence"]}["output.sector_volatility.groups"]["groups"] == 2
    annualized = run(service, review, inputs, Q6_CODE.replace('.std(ddof=1)', '.std(ddof=1).mul(252 ** 0.5)'))
    assert annualized["validation_status"] == "FAILED"
    failed = next(e for e in annualized["validation_evidence"] if e.get("code") == "CALCULATION_MISMATCH")
    assert failed["diagnosis"]["factor"] == "ANNUALIZED_SQRT_252"
    warmup_dropped = run(service, review, inputs, Q6_CODE.replace(
        'prices["daily_return"] = prices.groupby("ticker")["close"].pct_change(fill_method=None)',
        'prices = prices[prices["date"] >= pd.Timestamp(ANALYSIS_START)]\n'
        'prices["daily_return"] = prices.groupby("ticker")["close"].pct_change(fill_method=None)'))
    assert warmup_dropped["validation_status"] == "FAILED"


@requires_root
def test_q7_aligned_group_series_and_their_correlation_are_calculation_verified(make_service, governor) -> None:
    service = make_service()
    review = ask(service, q7_spec(), Q7)
    assert review.get("spec_id"), review
    frames = {"universe": GROUPED[["Ticker", "Sector", "Industry"]], "prices": grouped_prices()}
    inputs = prepare(service, governor, review, frames)
    result = run(service, review, inputs, Q7_CODE)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    checks = {e["check"]: e for e in result["validation_evidence"]}
    assert checks["output.series_correlation.series"]["groups"] == ["banks", "property"]
    assert checks["output.group_series.segments"]["segment_members"] == {"banks": 6, "property": 4}
    assert checks["calculation.correlation.series_correlation"]["result"] == "PASS"
    # a bank counted in the property segment changes both series and the correlation
    moved = run(service, review, inputs, Q7_CODE.replace('inside["Sector"] == "Properties & Real Estate"',
                                                         '(inside["Sector"] == "Properties & Real Estate") | '
                                                         '(inside["Ticker"] == "B00")'))
    assert moved["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in moved["reason_codes"]
    levels = run(service, review, inputs, Q7_CODE.replace('series["banks"].corr(series["property"])',
                                                          'inside[members["banks"]].groupby("date")["close"].mean()'
                                                          '.corr(inside[members["property"]].groupby("date")["close"]'
                                                          '.mean())'))
    assert levels["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in levels["reason_codes"]


@requires_root
def test_q7_an_empty_segment_is_incomplete_not_an_answer(make_service, governor) -> None:
    service = make_service()
    spec = q7_spec([segment("banks", "Industry", "Bank", "sektor perbankan"),
                    segment("property", "Sector", "Properties & Real Estate", "sektor properti")])
    review = ask(service, spec, Q7)
    frames = {"universe": GROUPED[["Ticker", "Sector", "Industry"]], "prices": grouped_prices()}
    inputs = prepare(service, governor, review, frames)
    code = Q7_CODE.replace('inside["Industry"] == "Banks"', 'inside["Industry"] == "Bank"')
    result = run(service, review, inputs, code)
    assert result["validation_status"] == "INCOMPLETE" and "SEGMENT_EMPTY" in result["reason_codes"]


# ---------------------------------------------------------------- repair friction (root causes of the live test)

def test_every_shared_spec_problem_names_a_machine_code() -> None:
    """Uncoded problems made the orchestrator's repair ledger lump unrelated rejections into INVALID_SPEC:UNSPECIFIED."""
    import ast
    import re

    source = (Path(__file__).resolve().parents[1] / "app" / "spec.py").read_text()
    uncoded = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "problems":
            argument = node.args[0]
            while isinstance(argument, ast.BinOp):
                argument = argument.right
            if isinstance(argument, ast.JoinedStr):
                argument = argument.values[-1]
            text = argument.value if isinstance(argument, ast.Constant) else ""
            if not re.search(r"\([A-Z][A-Z0-9_]+\)$", text):
                uncoded.append(node.lineno)
    assert uncoded == []


def test_spec_review_returns_codes_for_shared_rules(make_service) -> None:
    service = make_service()
    spec = q7_spec()
    spec["outputs"].append(dict(spec["outputs"][0]))  # duplicate output name
    review = ask(service, spec, Q7)
    assert review["status"] == "INVALID_SPEC" and "DUPLICATE_NAME" in review["problem_codes"]


def test_parameters_with_a_method_default_have_an_approved_default_id() -> None:
    spec = q7_spec()
    spec["calculations"][1]["params"][1] = {"name": "per_date", "value": True, "provenance": "USER_EXPLICIT",
                                            "default_id": None}
    spec["calculations"][1]["params"].append({"name": "min_observations", "value": 1,
                                              "provenance": "APPROVED_DEFAULT",
                                              "default_id": "DEFAULT_GROUP_MIN_OBSERVATIONS"})
    assert v2(spec)["calculations"][1]["segments"]
    q6 = q6_spec()
    q6["calculations"][2]["params"].append({"name": "per_date", "value": False, "provenance": "APPROVED_DEFAULT",
                                            "default_id": "DEFAULT_GROUP_PER_DATE"})
    grouped = next(c for c in v2(q6)["calculations"] if c["id"] == "sector_volatility")
    assert {"name": "per_date", "value": False, "provenance": "APPROVED_DEFAULT",
            "default_id": "DEFAULT_GROUP_PER_DATE"} in grouped["params"]
    q6["calculations"][2]["params"][-1]["default_id"] = "DEFAULT_RETURN_HORIZON"
    text = problems(q6)
    assert "its approved default is DEFAULT_GROUP_PER_DATE (False)" in text and "(DEFAULT_ID_INVALID)" in text


def test_mean_is_accepted_as_avg_everywhere() -> None:
    spec = q7_spec()
    spec["calculations"][1]["params"][0]["value"] = "MEAN"
    grouped = next(c for c in v2(spec)["calculations"] if c["id"] == "group_return")
    assert {p["name"]: p["value"] for p in grouped["params"]}["function"] == "AVG"
    q6 = q6_spec("mean")
    stat = next(c for c in v2(q6)["calculations"] if c["id"] == "volatility")
    assert {p["name"]: p["value"] for p in stat["params"]}["function"] == "AVG"


def test_a_scope_resolved_from_the_catalog_may_say_so() -> None:
    spec = q5_spec()
    spec["scope"]["provenance"] = "CATALOG_RESOLVED"
    assert v2(spec)["scope"]["provenance"] == "CATALOG_RESOLVED"
