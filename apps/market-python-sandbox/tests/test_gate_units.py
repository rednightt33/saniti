"""Execution Validation Gate logic without child processes: spec contract, intent review, logical
datasets, reference calculations, and the validator's preflight/postflight decisions."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import reference
import validator
from app.intent import extract, review
from app.logical import BindingError, GrantedFile, bind
from app.spec import (AnalysisSpec, SpecInvalid, add_months, derived_feature_definitions, normalize, output_contract,
                      required_input, resolve_period)
from conftest import FakeGovernor, price_frame, zscore_spec

REF = date(2026, 9, 23)
THREE_MONTHS = "Calculate rolling 20-day z-scores for all IDX stocks over the last three months."


def normalized(spec: dict) -> dict:
    return normalize(AnalysisSpec.model_validate(spec), REF)


def reviewed(spec: dict, *messages: str, roles: list[str] | None = None):
    roles = roles or ["user"] * len(messages)
    result, _ = review(normalized(spec), [{"role": r, "content": m} for r, m in zip(roles, messages)], REF)
    return result


# ---------------------------------------------------------------- spec contract

def test_method_defaults_are_filled_as_approved_defaults() -> None:
    spec = normalized(zscore_spec())
    params = {p["name"]: p for p in spec["calculations"][0]["params"]}
    assert params["window"]["value"] == 20 and params["window"]["provenance"] == "USER_EXPLICIT"
    # z-score conventions come from AI_formula_reference (TA-Lib has no z-score): ddof=1, and a price z-score
    # includes the current observation (CALC_054)
    assert params["ddof"] == {"name": "ddof", "value": 1, "provenance": "APPROVED_DEFAULT",
                              "default_id": "DEFAULT_ZSCORE_DDOF"}
    assert params["include_current"]["value"] is True
    assert spec["calculations"][0]["covers"] == ["ZSCORE", "SMA", "STD"]
    assert spec["outputs"][0]["entity_column"] == "ticker" and spec["outputs"][0]["date_column"] == "date"


@pytest.mark.parametrize(("change", "problem"), [
    (lambda s: s["calculations"][0].update(method="CUSTOM"), "CUSTOM calculations need a formula"),
    (lambda s: s["calculations"][0]["params"].append({"name": "ddof", "value": 0, "provenance": "APPROVED_DEFAULT",
                                                      "default_id": "DEFAULT_ZSCORE_DDOF"}), "not the approved default"),
    (lambda s: s["calculations"][0]["params"].append({"name": "alpha", "value": 1, "provenance": "AI_INFERRED"}),
     "unknown parameters"),
    (lambda s: s["calculations"][0].update(columns=["open"]), "not listed in input"),
    (lambda s: s["outputs"][0].update(calculations=["nope"]), "unknown calculation"),
    (lambda s: s.update(analysis_period={"mode": "EXPLICIT_DATES", "start": "2026-06-01", "end": "2026-10-31",
                                         "provenance": "USER_EXPLICIT"}), "after the reference date"),
    (lambda s: s["universe"].update(provenance="APPROVED_DEFAULT", default_id="MADE_UP"), "APPROVED_DEFAULT needs"),
    (lambda s: s["outputs"][0].update(grain="ENTITY_PAIR"), "ENTITY_PAIR outputs need a TICKERS universe"),
    (lambda s: s["outputs"][0].update(coverage="SELECTION"), "SELECTION coverage needs selection predicates"),
    (lambda s: s["calculations"][0]["params"].__setitem__(0, {"name": "window", "value": 1.5,
                                                              "provenance": "USER_EXPLICIT"}), "must be an integer"),
])
def test_invalid_specs_are_refused_with_every_problem(change, problem: str) -> None:
    spec = zscore_spec()
    change(spec)
    with pytest.raises(SpecInvalid) as info:
        normalized(spec)
    assert any(problem in p for p in info.value.problems), info.value.problems


def test_null_parameter_values_take_the_approved_default() -> None:
    spec = zscore_spec(window=20)
    spec["calculations"] = [{"id": "corr", "method": "CORRELATION", "dataset": "prices", "columns": ["close"],
                             "output_column": "correlation", "provenance": "USER_EXPLICIT",
                             "params": [{"name": n, "value": None, "provenance": "USER_EXPLICIT"}
                                        for n in ("method", "transform", "min_overlap")]}]
    spec["universe"] = {"type": "TICKERS", "tickers": ["BBCA", "BBRI"], "provenance": "USER_EXPLICIT"}
    spec["outputs"] = [{"name": "pair", "grain": "ENTITY_PAIR", "calculations": ["corr"],
                        "pair_columns": ["ticker_a", "ticker_b"]}]
    params = {p["name"]: p for p in normalize(AnalysisSpec.model_validate(spec), REF)["calculations"][0]["params"]}
    assert {n: (p["value"], p["provenance"], p["default_id"]) for n, p in params.items()} == {
        "method": ("PEARSON", "APPROVED_DEFAULT", "DEFAULT_CORRELATION_METHOD"),
        "transform": ("SIMPLE_RETURN", "APPROVED_DEFAULT", "DEFAULT_CORRELATION_TRANSFORM"),
        "min_overlap": (20, "APPROVED_DEFAULT", "DEFAULT_CORRELATION_MIN_OVERLAP")}
    required = zscore_spec()
    required["calculations"][0]["params"] = [{"name": "window", "value": None, "provenance": "USER_EXPLICIT"}]
    with pytest.raises(SpecInvalid) as caught:
        normalize(AnalysisSpec.model_validate(required), REF)
    assert any("parameter window is required" in p for p in caught.value.problems)


def test_period_resolution_and_required_history() -> None:
    assert add_months(date(2026, 5, 31), -3) == date(2026, 2, 28)
    trailing = resolve_period({"mode": "TRAILING", "unit": "MONTH", "count": 3}, REF)
    assert (trailing["start"], trailing["end"]) == ("2026-06-24", "2026-09-23")
    assert resolve_period({"mode": "TRAILING", "unit": "WEEK", "count": 2}, REF)["start"] == "2026-09-10"
    assert resolve_period({"mode": "TRADING_DAYS", "count": 10}, REF)["resolution"] == "FROM_INPUT_CALENDAR"
    spec = normalized(zscore_spec())
    needs = required_input(spec, trailing, REF)["prices"]
    assert (needs["minimum_warmup_observations"], needs["lookahead_observations"]) == (19, 0)
    assert needs["recommended_request_date_range"] == {"from": "2026-05-15", "to": "2026-09-23"}
    rsi = zscore_spec()
    rsi["calculations"] = [{"id": "rsi", "method": "RSI", "dataset": "prices", "columns": ["close"],
                            "output_column": "rsi_14", "provenance": "USER_EXPLICIT"}]
    rsi["outputs"][0]["calculations"] = ["rsi"]
    rsi_needs = required_input(normalized(rsi), trailing, REF)["prices"]
    assert (rsi_needs["minimum_warmup_observations"], rsi_needs["recommended_warmup_observations"]) == (14, 140)


def test_chained_calculations_add_their_warmup_and_features_are_defined() -> None:
    spec = zscore_spec()
    spec["calculations"] = [
        {"id": "ret", "method": "RETURN", "dataset": "prices", "columns": ["close"], "output_column": "ret_1d",
         "provenance": "AI_INFERRED"},
        {"id": "vol", "method": "ROLLING_STD", "dataset": "prices", "input_calculation": "ret",
         "params": [{"name": "window", "value": 20, "provenance": "USER_EXPLICIT"}], "output_column": "vol_20",
         "provenance": "USER_EXPLICIT"}]
    spec["outputs"][0]["calculations"] = ["vol"]
    norm = normalized(spec)
    needs = required_input(norm, resolve_period(norm["analysis_period"], REF), REF)["prices"]
    assert needs["minimum_warmup_observations"] == 20  # 1 for the return + 19 for the window
    features = {f["name"]: f for f in derived_feature_definitions(norm)}
    assert features["vol_20"]["source"]["input_calculation"] == "ret"
    assert features["vol_20"]["status"] == "EXPLORATORY_UNVALIDATED" and features["vol_20"]["origin"] == \
        "DERIVED_IN_ANALYSIS"
    assert features["ret_1d"]["output_grain"] == ["NOT_EMITTED"] and len(features["vol_20"]["definition_sha256"]) == 64


# ---------------------------------------------------------------- intent review

def test_matching_spec_is_approved() -> None:
    result = reviewed(zscore_spec(), THREE_MONTHS)
    assert result.status == "APPROVED", result.unverified + result.mismatches


def test_three_months_requested_two_months_proposed_is_a_mismatch() -> None:
    spec = zscore_spec(period={"mode": "TRAILING", "unit": "MONTH", "count": 2, "provenance": "USER_EXPLICIT"})
    result = reviewed(spec, THREE_MONTHS)
    assert result.status == "ANALYSIS_SPEC_MISMATCH"
    assert result.mismatches[0]["requirement"] == "analysis_period"
    assert result.mismatches[0]["code"] == "ANALYSIS_SCOPE_MISMATCH"


def test_explicit_dates_equal_to_the_trailing_window_match() -> None:
    spec = zscore_spec(period={"mode": "EXPLICIT_DATES", "start": "2026-06-24", "end": "2026-09-23",
                               "provenance": "USER_EXPLICIT"})
    assert reviewed(spec, THREE_MONTHS).status == "APPROVED"


@pytest.mark.parametrize(("spec", "code"), [
    (zscore_spec(window=10), "CALCULATION_PARAMETER_MISMATCH"),
    (zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI"]), "UNIVERSE_MISMATCH"),
])
def test_parameter_and_universe_contradictions_are_mismatches(spec: dict, code: str) -> None:
    result = reviewed(spec, THREE_MONTHS)
    assert result.status == "ANALYSIS_SPEC_MISMATCH" and result.mismatches[0]["code"] == code


def test_named_tickers_must_be_analysed_and_extra_tickers_are_disclosed() -> None:
    message = "Hitung z-score rolling 20 hari BBCA dan BBRI selama 3 bulan terakhir"
    assert reviewed(zscore_spec(), message).mismatches[0]["code"] == "UNIVERSE_MISMATCH"
    ok = reviewed(zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI"]), message)
    assert ok.status == "APPROVED"
    extra = reviewed(zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI", "TLKM"]), message)
    assert extra.status == "APPROVED_WITH_UNVERIFIED" and "TLKM" in extra.unverified[0]["detail"]


def test_ambiguous_or_missing_periods_need_clarification() -> None:
    assert reviewed(zscore_spec(), "How volatile have IDX stocks been recently? use 20-day z-scores for all stocks"
                    ).status == "NEEDS_CLARIFICATION"
    assert reviewed(zscore_spec(), "Rolling 20-day z-scores for all IDX stocks").status == "NEEDS_CLARIFICATION"
    latest = zscore_spec(period={"mode": "LATEST", "provenance": "AI_INFERRED"}, output_grain="ENTITY")
    screen = reviewed(latest, "Which IDX stocks have a 20-day z-score above 2 for all stocks?")
    assert screen.status == "APPROVED_WITH_UNVERIFIED"
    assert any(u["requirement"] == "analysis_period" for u in screen.unverified)


def test_a_clarified_period_in_a_later_turn_is_accepted() -> None:
    result = reviewed(zscore_spec(), "Hitung z-score rolling 20 hari untuk semua saham",
                      "Periode berapa lama?", "3 bulan terakhir", roles=["user", "assistant", "user"])
    assert result.status == "APPROVED"


def test_ai_chosen_parameters_are_unverified_and_approved_defaults_are_reported() -> None:
    unstated = reviewed(zscore_spec(window_provenance="AI_INFERRED"),
                        "Calculate rolling z-scores for all IDX stocks over the last three months.")
    assert unstated.status == "APPROVED_WITH_UNVERIFIED"
    assert any(u["requirement"] == "calculation.z20.window" for u in unstated.unverified)
    rsi = zscore_spec(question="RSI")
    rsi["calculations"] = [{"id": "rsi", "method": "RSI", "dataset": "prices", "columns": ["close"],
                            "output_column": "rsi_14", "provenance": "USER_EXPLICIT"}]
    rsi["outputs"][0]["calculations"] = ["rsi"]
    result = reviewed(rsi, "Show RSI for all IDX stocks over the last three months")
    assert any(c["requirement"] == "calculation.rsi.period" and c["result"] == "DEFAULT_APPLIED" for c in result.checks)


def test_requested_methods_and_thresholds_must_be_in_the_spec() -> None:
    rsi_request = "Screen all IDX stocks where the latest RSI(14) is below 30"
    missing = reviewed(zscore_spec(period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY"),
                       rsi_request)
    assert any(m["code"] == "MISSING_REQUESTED_CALCULATION" for m in missing.mismatches)
    spec = zscore_spec(period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY",
                       selection=[{"calculation": "rsi", "op": "<", "value": 20, "provenance": "USER_EXPLICIT"}])
    spec["calculations"] = [{"id": "rsi", "method": "RSI", "dataset": "prices", "columns": ["close"],
                             "params": [{"name": "period", "value": 14, "provenance": "USER_EXPLICIT"}],
                             "output_column": "rsi_14", "provenance": "USER_EXPLICIT"}]
    spec["outputs"][0]["calculations"] = ["rsi"]
    wrong = reviewed(spec, rsi_request)
    assert any(m["requirement"] == "threshold.RSI" for m in wrong.mismatches)
    spec["outputs"][0]["selection"][0]["value"] = 30
    assert reviewed(spec, rsi_request).status == "APPROVED"


def test_unqualified_day_counts_are_accepted_but_disclosed() -> None:
    spec = zscore_spec(period={"mode": "TRADING_DAYS", "count": 10, "provenance": "USER_EXPLICIT"})
    result = reviewed(spec, "Hitung z-score rolling 20 hari semua saham untuk 10 hari terakhir")
    assert result.status == "APPROVED_WITH_UNVERIFIED"
    assert "trading" in result.unverified[0]["detail"]


def test_the_expected_requirements_record_holds_phrases_not_messages() -> None:
    found = extract([{"role": "user", "content": THREE_MONTHS + " My secret note."}], REF)
    record = json.dumps(found.record())
    assert "secret" not in record and "over the last 3 months" in record


# ---------------------------------------------------------------- logical datasets

def manifests(gov: FakeGovernor, *ids: str) -> dict[str, GrantedFile]:
    return {ds: GrantedFile(ds, {**gov.datasets[ds]["manifest"]}, f"input_{i:03d}.parquet")
            for i, ds in enumerate(ids, start=1)}


def test_compatible_files_form_one_logical_dataset_with_lineage(sandbox_root) -> None:
    gov = FakeGovernor(sandbox_root)
    frame = price_frame({"AAAA": ("2026-01-01", 60)})
    first = gov.add(frame.iloc[:30], requested_from="2026-01-01")
    second = gov.add(frame.iloc[30:], requested_from="2026-02-01")
    logical = bind(normalized(zscore_spec()), [{"name": "prices", "dataset_ids": [first, second]}],
                   manifests(gov, first, second), 8)["prices"]
    assert [f["dataset_id"] for f in logical["files"]] == [first, second]
    assert logical["grain"] == ["ticker", "date"] and logical["key_columns"] == ["ticker", "date"]
    assert logical["series_key"] == ["ticker", "date"] and logical["duplicate_policy"] == "ERROR_ON_CONFLICT"
    assert logical["contract"]["frequency"] == "1D" and logical["files"][0]["checksum_sha256"]


@pytest.mark.parametrize(("second_kwargs", "code"), [
    ({"source_table": "Feature_01_Stock_Daily"}, "SOURCE_TABLE_MISMATCH"),
    ({"aggregation": {"close": "AVG"}}, "INCOMPATIBLE_LOGICAL_DATASET"),
    ({"source_columns": {"close": "open"}}, "INCOMPATIBLE_LOGICAL_DATASET"),
])
def test_incompatible_files_are_never_merged(sandbox_root, second_kwargs: dict, code: str) -> None:
    gov = FakeGovernor(sandbox_root)
    frame = price_frame({"AAAA": ("2026-01-01", 40)})
    first = gov.add(frame.iloc[:20])
    second = gov.add(frame.iloc[20:], **second_kwargs)
    with pytest.raises(BindingError) as info:
        bind(normalized(zscore_spec()), [{"name": "prices", "dataset_ids": [first, second]}],
             manifests(gov, first, second), 8)
    assert info.value.code == code


def test_binding_checks_names_columns_types_and_file_limits(sandbox_root) -> None:
    gov = FakeGovernor(sandbox_root)
    ds = gov.add(price_frame({"AAAA": ("2026-01-01", 10)}))
    no_close = gov.add(price_frame({"AAAA": ("2026-01-01", 10)}).drop(columns=["close"]))
    text_close = gov.add(price_frame({"AAAA": ("2026-01-01", 10)}).assign(close="x"))
    spec = normalized(zscore_spec())
    cases = [([{"name": "other", "dataset_ids": [ds]}], {ds}, "INPUT_BINDING_MISMATCH"),
             ([{"name": "prices", "dataset_ids": [no_close]}], {no_close}, "REQUIRED_COLUMNS_MISSING"),
             ([{"name": "prices", "dataset_ids": [text_close]}], {text_close}, "COLUMN_TYPE_MISMATCH")]
    for bindings, ids, code in cases:
        with pytest.raises(BindingError) as info:
            bind(spec, bindings, manifests(gov, *ids), 8)
        assert info.value.code == code
    with pytest.raises(BindingError, match="At most 1 input files"):
        bind(spec, [{"name": "prices", "dataset_ids": [ds, no_close]}], manifests(gov, ds, no_close), 1)


def test_database_features_are_distinguished_from_derived_ones(sandbox_root) -> None:
    gov = FakeGovernor(sandbox_root)
    frame = price_frame({"AAAA": ("2026-01-01", 10)}).rename(columns={"volume": "return_1d_pct"})
    ds = gov.add(frame, source_table="Feature_01_Stock_Daily")
    spec = zscore_spec()
    spec["inputs"][0].update(source_table="Feature_01_Stock_Daily", columns=["ticker", "date", "close", "return_1d_pct"])
    logical = bind(normalized(spec), [{"name": "prices", "dataset_ids": [ds]}], manifests(gov, ds), 8)["prices"]
    assert set(logical["database_features"]) == {"close", "date", "return_1d_pct", "ticker"}


# ---------------------------------------------------------------- reference calculations

def test_reference_calculations_match_talib_and_pandas_on_known_series() -> None:
    import talib

    rng = np.random.default_rng(3)
    x = 1000 + np.cumsum(rng.normal(0, 12, 400))
    series = pd.Series(x)
    np.testing.assert_allclose(reference.sma(x, 20), talib.SMA(x, 20), rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(reference.rolling_std(x, 20, 0), talib.STDDEV(x, 20), rtol=1e-10, equal_nan=True)
    np.testing.assert_allclose(reference.rolling_std(x, 20, 1), series.rolling(20).std(), rtol=1e-10, equal_nan=True)
    np.testing.assert_allclose(reference.rsi_wilder(x, 14), talib.RSI(x, 14), rtol=1e-12, equal_nan=True)
    z = (series - series.rolling(20).mean()) / series.rolling(20).std()
    np.testing.assert_allclose(reference.rolling_zscore(x, 20, 1, True), z, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(reference.forward_returns(x, 5, "SIMPLE", True), (series.shift(-5) / series - 1) * 100,
                               rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(reference.returns(x, 1, "LOG", False), np.log(series / series.shift(1)), rtol=1e-12,
                               equal_nan=True)
    y = x[::-1].copy()
    np.testing.assert_allclose(reference.rolling_correlation(x, y, 30, "PEARSON", "NONE"),
                               series.rolling(30).corr(pd.Series(y)), rtol=1e-8, equal_nan=True)


def test_reference_invariants_and_deterministic_cases() -> None:
    flat = np.full(30, 100.0)
    assert reference.rsi_wilder(flat, 14)[-1] == 0.0          # no change: both averages zero
    assert reference.rsi_wilder(np.linspace(100, 130, 30), 14)[-1] == 100.0
    rsi = reference.rsi_wilder(1000 + np.cumsum(np.random.default_rng(1).normal(0, 10, 300)), 14)
    assert np.nanmin(rsi) >= 0 and np.nanmax(rsi) <= 100 and np.isnan(rsi[:14]).all()
    assert np.isnan(reference.rolling_zscore(flat, 5, 1, True)[-1])   # zero deviation: undefined, not infinite
    assert reference.sma(np.arange(1, 6, dtype=float), 5)[-1] == 3.0
    assert reference.rolling_std(np.array([2, 4, 4, 4, 5, 5, 7, 9], dtype=float), 8, 0)[-1] == 2.0
    assert reference.pair_correlation(np.arange(30.0), np.arange(30.0) * 2 + 1, "PEARSON", 20) == pytest.approx(1.0)
    assert np.isnan(reference.pair_correlation(np.arange(5.0), np.arange(5.0), "PEARSON", 20))


# ---------------------------------------------------------------- validator decisions (in-process)

class Job:
    """A job workspace with harness files, built without starting any process."""

    def __init__(self, root: Path, spec: dict, bindings: list[tuple[str, list[dict]]],
                 message: str = THREE_MONTHS) -> None:
        self.root = root
        self.gov = FakeGovernor(root)
        norm = normalized(spec)
        ids, all_ids = [], []
        for name, files in bindings:
            group = [self.gov.add(**{k: v for k, v in f.items() if k != "_policy"}) for f in files]
            ids.append({"name": name, "dataset_ids": group,
                        "duplicate_policy": files[0].get("_policy", "ERROR_ON_CONFLICT")})
            all_ids += group
        granted = manifests(self.gov, *all_ids)
        self.job = root / "job"
        (self.job / "input").mkdir(parents=True)
        (self.job / "validation" / "outputs").mkdir(parents=True)
        for ds, file in granted.items():
            (self.job / "input" / file.local_name).write_bytes(self.gov.datasets[ds]["path"].read_bytes())
        logical = bind(norm, [{k: v for k, v in b.items()} for b in ids], granted, 8)
        resolved = resolve_period(norm["analysis_period"], REF)
        self.manifest = {"logical_datasets": logical}
        self.analysis_spec = {"spec": norm, "resolved_period": resolved, "required_input": required_input(
            norm, resolved, REF), "reference": {"date": REF.isoformat(), "timezone": "Asia/Jakarta"}}

    def preflight(self) -> dict:
        return validator.preflight(str(self.job), self.analysis_spec, self.manifest)

    def postflight(self, outputs: dict[str, pd.DataFrame]) -> dict:
        request = {"outputs": {}}
        for i, (name, frame) in enumerate(outputs.items(), start=1):
            path = self.job / "validation" / "outputs" / f"out_{i:03d}.parquet"
            pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)
            request["outputs"][name] = f"validation/outputs/out_{i:03d}.parquet"
        return validator.postflight(str(self.job), self.analysis_spec, self.manifest, request)


def zscores(frame: pd.DataFrame, window: int = 20, start: str = "2026-06-24", partition: bool = True) -> pd.DataFrame:
    df = frame.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"])
    if partition:
        g = df.groupby("ticker")["close"]
        mean, std = g.transform(lambda s: s.rolling(window).mean()), g.transform(lambda s: s.rolling(window).std())
    else:
        mean, std = df["close"].rolling(window).mean(), df["close"].rolling(window).std()
    df[f"zscore_{20}"] = (df["close"] - mean) / std
    return df[df["date"] >= pd.Timestamp(start)][["ticker", "date", "zscore_20"]]


FULL = price_frame({f"T{i:02d}": ("2026-04-01", 125) for i in range(12)})


def full_job(root: Path, spec: dict | None = None, frame: pd.DataFrame = FULL, **file_kwargs) -> Job:
    return Job(root, spec or zscore_spec(), [("prices", [{"data": frame, "requested_from": "2026-04-01",
                                                          "requested_to": "2026-09-23", **file_kwargs}])])


def test_correct_output_passes_with_calculation_verified(sandbox_root) -> None:
    job = full_job(sandbox_root)
    assert job.preflight()["blocking"] == []
    result = job.postflight({"zscores": zscores(FULL)})
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED")
    output = result["outputs"][0]
    assert output["entities"] == 12 and output["date_range"] == ["2026-06-24", "2026-09-22"]
    assert output["values_checked"] == output["in_period_rows"] == 12 * 65


def test_A_two_of_three_months_is_an_analysis_scope_mismatch(sandbox_root) -> None:
    result = full_job(sandbox_root).postflight({"zscores": zscores(FULL, start="2026-07-24")})
    assert result["validation_status"] == "FAILED" and "ANALYSIS_SCOPE_MISMATCH" in result["reasons"]
    coverage = next(e for e in result["evidence"] if e["check"] == "output.zscores.coverage")
    assert coverage["classification"] == "LOST_IN_TRANSFORMATION"
    assert coverage["expected_range"] == ["2026-06-24", "2026-09-23"]
    assert coverage["actual_range"][0] == "2026-07-24"


def test_B_missing_warmup_blocks_before_execution_with_the_date_to_request(sandbox_root) -> None:
    late = price_frame({f"T{i:02d}": ("2026-06-24", 65) for i in range(3)})
    job = Job(sandbox_root, zscore_spec(), [("prices", [{"data": late, "requested_from": "2026-06-24"}])])
    pre = job.preflight()
    assert [b["code"] for b in pre["blocking"]] == ["INSUFFICIENT_WARMUP_HISTORY"]
    assert "2026-05-15" in pre["blocking"][0]["message"] and pre["warmup"]["prices"]["not_extracted_count"] == 3


def test_B_source_limited_history_is_reported_not_hidden(sandbox_root) -> None:
    frame = pd.concat([FULL, price_frame({"NEWW": ("2026-07-01", 58)}, seed=5)], ignore_index=True)
    job = full_job(sandbox_root, frame=frame)
    pre = job.preflight()
    assert pre["blocking"] == [] and pre["warmup"]["prices"]["source_limited"] == ["NEWW"]
    assert pre["warmup"]["prices"]["affected_observations"] == 19
    result = job.postflight({"zscores": zscores(frame)})  # undefined values kept as nulls
    assert result["validation_status"] == "PASS"
    assert result["reasons"] == {"INSUFFICIENT_WARMUP_HISTORY": "WARNING"}
    omitted = full_job(sandbox_root / "o", frame=frame).postflight({"zscores": zscores(frame).dropna()})
    assert omitted["validation_status"] == "PASS" and omitted["reasons"]["UNDEFINED_VALUES_OMITTED"] == "WARNING"


def test_B_source_limited_history_of_a_requested_ticker_is_incomplete(sandbox_root) -> None:
    frame = price_frame({"BBCA": ("2026-04-01", 125), "NEWW": ("2026-07-01", 58)})
    spec = zscore_spec(universe="TICKERS", tickers=["BBCA", "NEWW"])
    job = Job(sandbox_root, spec, [("prices", [{"data": frame, "requested_from": "2026-04-01",
                                                "entities": ["BBCA", "NEWW"]}])])
    assert job.postflight({"zscores": zscores(frame)})["validation_status"] == "INCOMPLETE"


def test_C_a_subset_of_the_universe_is_a_universe_mismatch(sandbox_root) -> None:
    subset = zscores(FULL)
    result = full_job(sandbox_root).postflight({"zscores": subset[subset.ticker.isin(["T00", "T01", "T02"])]})
    assert result["validation_status"] == "FAILED"
    universe = next(e for e in result["evidence"] if e["check"] == "output.zscores.universe")
    assert (universe["code"], universe["missing_entities"], universe["actual_entities"]) == ("UNIVERSE_MISMATCH", 9, 3)


def test_C_documented_exclusions_are_legitimate(sandbox_root) -> None:
    spec = zscore_spec(exclusions=[{"rule": "EXCLUDE_TICKERS", "value": ["T00"], "provenance": "USER_EXPLICIT"}])
    output = zscores(FULL)
    result = full_job(sandbox_root, spec).postflight({"zscores": output[output.ticker != "T00"]})
    assert result["validation_status"] == "PASS" and result["reasons"] == {"DOCUMENTED_EXCLUSION": "WARNING"}


def test_C_extracting_a_subset_for_an_all_stocks_spec_is_blocked(sandbox_root) -> None:
    job = full_job(sandbox_root, entities=["T00", "T01"])
    assert [b["code"] for b in job.preflight()["blocking"]] == ["UNIVERSE_MISMATCH"]


def test_D_a_ten_observation_window_is_a_calculation_mismatch_with_diagnosis(sandbox_root) -> None:
    result = full_job(sandbox_root).postflight({"zscores": zscores(FULL, window=10)})
    assert result["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in result["reasons"]
    check = next(e for e in result["evidence"] if e.get("code") == "CALCULATION_MISMATCH")
    assert check["diagnosis"] == {"finding": "PARAMETER_DIFFERS", "parameter": "window", "spec_value": 20,
                                  "values_match": 10}
    assert result["validation_level"] == "SCOPE_VERIFIED"  # the scope was right; the values were not


def test_cross_entity_contamination_is_detected(sandbox_root) -> None:
    # ZNEW sorts after the other tickers, so an unpartitioned rolling window leaks their prices into its first rows.
    frame = pd.concat([FULL, price_frame({"ZNEW": ("2026-06-24", 65)}, seed=5)], ignore_index=True)
    result = full_job(sandbox_root, frame=frame).postflight({"zscores": zscores(frame, partition=False)})
    assert result["validation_status"] == "FAILED"
    check = next(e for e in result["evidence"] if e.get("code") == "CALCULATION_MISMATCH")
    assert check["examples"][0]["entity"] == "ZNEW" and check["mismatched"] == 19


def test_rows_outside_the_period_and_duplicate_keys_fail(sandbox_root) -> None:
    with_warmup = zscores(FULL, start="2026-05-01")
    result = full_job(sandbox_root).postflight({"zscores": with_warmup})
    assert "ANALYSIS_SCOPE_MISMATCH" in result["reasons"]
    doubled = pd.concat([zscores(FULL), zscores(FULL).head(3)])
    assert "OUTPUT_GRAIN_VIOLATION" in full_job(sandbox_root / "b").postflight({"zscores": doubled})["reasons"]


def test_H_self_reported_metadata_is_ignored(sandbox_root) -> None:
    job = full_job(sandbox_root)
    subset = zscores(FULL)
    result = job.postflight({"zscores": subset[subset.ticker == "T00"], "claims": pd.DataFrame(
        {"entities_analyzed": [844], "complete": [True]})})
    assert result["validation_status"] == "FAILED" and "UNIVERSE_MISMATCH" in result["reasons"]
    missing = full_job(sandbox_root / "m").postflight({})
    assert "REQUIRED_OUTPUT_MISSING" in missing["reasons"]


def test_H_nothing_checkable_is_unverified_not_pass(sandbox_root) -> None:
    spec = zscore_spec(output_grain="UNSPECIFIED")
    result = full_job(sandbox_root, spec).postflight({"zscores": pd.DataFrame({"claimed_entities": [844]})})
    assert (result["validation_status"], result["validation_level"]) == ("UNVERIFIED", "EXECUTION_ONLY")


def test_custom_methods_can_reach_scope_verified_but_never_calculation_verified(sandbox_root) -> None:
    spec = zscore_spec()
    spec["calculations"] = [{"id": "z20", "method": "CUSTOM", "dataset": "prices", "columns": ["close"],
                             "params": [{"name": "warmup_observations", "value": 19, "provenance": "AI_INFERRED"}],
                             "output_column": "zscore_20", "formula": "(close - mean20) / std20",
                             "time_alignment": "trailing 20 observations", "covers": ["ZSCORE"],
                             "provenance": "AI_INFERRED"}]
    result = full_job(sandbox_root, spec).postflight({"zscores": zscores(FULL)})
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "SCOPE_VERIFIED")


def test_latest_selection_screens_are_recomputed(sandbox_root) -> None:
    spec = zscore_spec(period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY",
                       selection=[{"calculation": "z20", "op": ">", "value": 0.5, "provenance": "USER_EXPLICIT"}])
    latest = zscores(FULL, start="2026-01-01").sort_values("date").groupby("ticker").tail(1)
    chosen = latest[latest["zscore_20"] > 0.5]
    assert full_job(sandbox_root, spec).postflight({"zscores": chosen})["validation_status"] == "PASS"
    wrong = latest[latest["zscore_20"] > 0.0]
    result = full_job(sandbox_root / "w", spec).postflight({"zscores": wrong})
    if len(wrong) != len(chosen):
        assert "SELECTION_MISMATCH" in result["reasons"]


def test_mixed_screens_still_check_the_recalculable_predicates(sandbox_root) -> None:
    spec = zscore_spec(period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY",
                       selection=[{"calculation": "z20", "op": ">", "value": 0.0, "provenance": "USER_EXPLICIT"},
                                  {"calculation": "flag", "op": "==", "value": 1, "provenance": "AI_INFERRED"}])
    spec["calculations"].append({"id": "flag", "method": "CUSTOM", "dataset": "prices", "columns": ["close"],
                                 "output_column": "flag", "formula": "1 if close > previous close else 0",
                                 "time_alignment": "current and previous observation", "provenance": "AI_INFERRED"})
    spec["outputs"][0]["calculations"] = ["z20", "flag"]
    latest = zscores(FULL, start="2026-01-01").sort_values("date").groupby("ticker").tail(1).assign(flag=1)
    good = latest[latest["zscore_20"] > 0.0]
    result = full_job(sandbox_root, spec).postflight({"zscores": good})
    assert (result["validation_status"], result["validation_level"]) == ("UNVERIFIED", "EXECUTION_ONLY")
    checks = {e["check"]: e for e in result["evidence"]}
    assert checks["output.zscores.selection.checkable"]["result"] == "PASS"
    assert checks["output.zscores.selection"]["result"] == "SKIPPED"
    bad = latest[latest["zscore_20"] <= 0.0].head(1)
    assert len(bad), "fixture needs an entity with a non-positive latest z-score"
    result = full_job(sandbox_root / "bad", spec).postflight({"zscores": pd.concat([good, bad])})
    assert result["validation_status"] == "FAILED" and "SELECTION_MISMATCH" in result["reasons"]


def test_pair_correlation_outputs_are_recomputed(sandbox_root) -> None:
    frame = price_frame({"BBCA": ("2026-04-01", 125), "BBRI": ("2026-04-01", 125), "TLKM": ("2026-04-01", 125)})
    spec = zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI", "TLKM"])
    spec["calculations"] = [{"id": "corr", "method": "CORRELATION", "dataset": "prices", "columns": ["close"],
                             "output_column": "correlation", "provenance": "USER_EXPLICIT"}]
    spec["outputs"] = [{"name": "matrix", "grain": "ENTITY_PAIR", "calculations": ["corr"],
                        "pair_columns": ["ticker_a", "ticker_b"]}]
    job = Job(sandbox_root, spec, [("prices", [{"data": frame, "requested_from": "2026-04-01",
                                                "entities": ["BBCA", "BBRI", "TLKM"]}])])
    df = frame.assign(date=pd.to_datetime(frame["date"])).sort_values(["ticker", "date"])
    df["ret"] = df.groupby("ticker")["close"].pct_change()
    wide = df[df["date"] >= "2026-06-24"].pivot(index="date", columns="ticker", values="ret")
    rows = [{"ticker_a": a, "ticker_b": b, "correlation": wide[a].corr(wide[b])}
            for a, b in (("BBCA", "BBRI"), ("BBCA", "TLKM"), ("BBRI", "TLKM"))]
    result = job.postflight({"matrix": pd.DataFrame(rows)})
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED")
    rows[0]["correlation"] += 0.1
    assert "CALCULATION_MISMATCH" in Job(sandbox_root / "x", spec, [("prices", [{
        "data": frame, "requested_from": "2026-04-01", "entities": ["BBCA", "BBRI", "TLKM"]}])]).postflight(
        {"matrix": pd.DataFrame(rows)})["reasons"]


def _pair_job(root: Path) -> tuple[Job, pd.DataFrame]:
    frame = price_frame({"BBCA": ("2026-04-01", 125), "BBRI": ("2026-04-01", 125), "TLKM": ("2026-04-01", 125)})
    spec = zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI", "TLKM"])
    spec["calculations"] = [{"id": "corr", "method": "CORRELATION", "dataset": "prices", "columns": ["close"],
                             "output_column": "correlation", "provenance": "USER_EXPLICIT"}]
    spec["outputs"] = [{"name": "matrix", "grain": "ENTITY_PAIR", "calculations": ["corr"],
                        "pair_columns": ["ticker_a", "ticker_b"]}]
    return Job(root, spec, [("prices", [{"data": frame, "requested_from": "2026-04-01",
                                         "entities": ["BBCA", "BBRI", "TLKM"]}])]), frame


def _pairs(frame: pd.DataFrame, start: str = "2026-06-24", warmup: bool = True, log: bool = False) -> pd.DataFrame:
    df = frame.assign(date=pd.to_datetime(frame["date"])).sort_values(["ticker", "date"])
    if not warmup:
        df = df[df["date"] >= start]
    close = df.groupby("ticker")["close"]
    df["ret"] = close.transform(lambda s: np.log(s).diff()) if log else close.pct_change()
    wide = df[df["date"] >= start].pivot(index="date", columns="ticker", values="ret")
    return pd.DataFrame([{"ticker_a": a, "ticker_b": b, "correlation": wide[a].corr(wide[b])}
                         for a, b in (("BBCA", "BBRI"), ("BBCA", "TLKM"), ("BBRI", "TLKM"))])


@pytest.mark.parametrize("kwargs, finding, parameter", [
    ({"warmup": False}, "WARMUP_NOT_USED", None),
    ({"log": True}, "PARAMETER_DIFFERS", "transform"),
])
def test_pair_correlation_mismatches_are_diagnosed(sandbox_root, kwargs: dict, finding: str, parameter) -> None:
    job, frame = _pair_job(sandbox_root)
    result = job.postflight({"matrix": _pairs(frame, **kwargs)})
    assert result["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in result["reasons"]
    item = next(e for e in result["evidence"] if e.get("code") == "CALCULATION_MISMATCH")
    assert item["diagnosis"]["finding"] == finding
    if parameter:
        assert item["diagnosis"]["parameter"] == parameter and item["diagnosis"]["values_match"] == "LOG_RETURN/PEARSON"


def test_the_output_contract_names_the_columns_the_validator_reads() -> None:
    spec = normalize(AnalysisSpec.model_validate(zscore_spec()), REF)
    contract = output_contract(spec)
    assert contract == [{"name": "zscores", "grain": "ENTITY_DATE", "key_columns": ["ticker", "date"],
                         "value_columns": ["zscore_20"], "coverage": "FULL", "emit": "emit_table"}]
    latest = normalize(AnalysisSpec.model_validate(zscore_spec(
        period={"mode": "LATEST", "provenance": "USER_EXPLICIT"}, output_grain="ENTITY",
        selection=[{"calculation": "z20", "op": ">", "value": 0.5, "provenance": "USER_EXPLICIT"}])), REF)
    item = output_contract(latest)[0]
    assert item["key_columns"] == ["ticker"] and item["optional_columns"] == ["date"]
    assert item["coverage"] == "SELECTION" and item["selection"][0]["op"] == ">"


def test_in_period_keeps_the_approved_period_and_each_entitys_latest_row(monkeypatch) -> None:
    import saniti

    monkeypatch.setattr(saniti, "INPUTS", {"prices": {"entity_column": "ticker", "date_column": "date"}})
    frame = pd.DataFrame({"ticker": ["A", "A", "A", "B", "B", "C"],
                          "date": [date(2026, 8, 27), date(2026, 8, 28), date(2026, 9, 1), date(2026, 8, 26),
                                   date(2026, 8, 27), date(2026, 8, 28)]})
    monkeypatch.setattr(saniti, "ANALYSIS_START", "2026-08-27")
    monkeypatch.setattr(saniti, "ANALYSIS_END", "2026-08-28")
    monkeypatch.setattr(saniti, "_PERIOD_MODE", "EXPLICIT_DATES")
    assert saniti.in_period(frame).tolist() == [True, True, False, False, True, True]
    as_text = frame.assign(date=frame["date"].astype(str))
    assert saniti.in_period(as_text).tolist() == saniti.in_period(frame).tolist()
    monkeypatch.setattr(saniti, "ANALYSIS_START", "2026-08-28")
    monkeypatch.setattr(saniti, "_PERIOD_MODE", "LATEST")
    # newest row on or before the period end per entity; B's stale latest row is still its latest
    assert saniti.in_period(frame).tolist() == [False, True, False, False, True, True]
    monkeypatch.setattr(saniti, "INPUTS", {"a": {"date_column": "date"}, "b": {"date_column": "day"}})
    with pytest.raises(saniti.SanitiError, match="date_column"):
        saniti.in_period(frame)


def test_F_overlapping_snapshots_deduplicate_identical_rows_and_refuse_conflicts(sandbox_root) -> None:
    first, second = FULL[FULL.date < date(2026, 8, 1)], FULL[FULL.date >= date(2026, 7, 1)]
    job = Job(sandbox_root, zscore_spec(), [("prices", [
        {"data": first, "requested_from": "2026-04-01", "requested_to": "2026-07-31"},
        {"data": second, "requested_from": "2026-07-01", "requested_to": "2026-09-23"}])])
    pre = job.preflight()
    assert pre["blocking"] == []
    stats = next(e for e in pre["evidence"] if e["check"] == "input.prices")
    assert stats["files"] == 2 and stats["identical_duplicates_removed"] == 12 * 23 and stats["rows_used"] == len(FULL)
    assert job.postflight({"zscores": zscores(FULL)})["validation_status"] == "PASS"
    changed = second.copy()
    changed.loc[changed.date < date(2026, 8, 1), "close"] += 1
    conflict = Job(sandbox_root / "c", zscore_spec(), [("prices", [
        {"data": first, "requested_from": "2026-04-01"}, {"data": changed, "requested_from": "2026-07-01"}])])
    assert [b["code"] for b in conflict.preflight()["blocking"]] == ["DUPLICATE_CONFLICT"]
    newest = Job(sandbox_root / "n", zscore_spec(), [("prices", [
        {"data": first, "requested_from": "2026-04-01", "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
         "_policy": "PREFER_LATEST_SNAPSHOT"},
        {"data": changed, "requested_from": "2026-07-01", "created_at": datetime(2026, 9, 2, tzinfo=timezone.utc)}])])
    assert newest.preflight()["blocking"] == []


def test_F_rows_without_the_full_grain_are_ambiguous(sandbox_root) -> None:
    boards = pd.concat([FULL.assign(market_board="Regular"), FULL.assign(market_board="Nego")], ignore_index=True)
    spec = zscore_spec()
    spec["inputs"][0].update(source_table="Feature_03_Stock_Broker_Daily")
    job = Job(sandbox_root, spec, [("prices", [{"data": boards, "requested_from": "2026-04-01",
                                                "source_table": "Feature_03_Stock_Broker_Daily"}])])
    assert [b["code"] for b in job.preflight()["blocking"]] == ["GRAIN_AMBIGUOUS"]
