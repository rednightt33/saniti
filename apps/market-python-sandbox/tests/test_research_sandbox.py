"""Research AI integration scenarios A-J through the real service: isolated analysis and validator processes, the
Research Governor, event-study recalculation, evidence assessment, the leakage re-run, and the run audit.

FIXTURE TEST: every dataset is synthetic (deterministic random walks served by the fake Governor); nothing here
is live market data."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import AnalysisRequest
from app.service import ServiceUnavailable
from app.spec import SpecRequest
from conftest import API_KEY, requires_root, zscore_spec
from test_research_units import custom_ratio_spec, event_study_spec

pytestmark = requires_root
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
REFERENCE = datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc)
EVENT_QUESTION = ("Event study for all IDX stocks from 2025-01-02 to 2026-06-30: after a 20-day z-score below -1.5, "
                  "what is the 5-day forward return?")


def ohlc(tickers: int = 12, start: str = "2024-06-03", days: int = 540, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(tickers):
        dates = pd.bdate_range(start, periods=days)
        close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, days)))
        open_ = close * np.exp(rng.normal(0, 0.005, days))
        frames.append(pd.DataFrame({"ticker": f"T{i:02d}", "date": dates.date, "open": open_, "close": close,
                                    "volume": rng.integers(1000, 90000, days).astype(float)}))
    return pd.concat(frames, ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def flows(tickers: int = 6, start: str = "2026-04-01", days: int = 125, seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(tickers):
        dates = pd.bdate_range(start, periods=days)
        frames.append(pd.DataFrame({"ticker": f"F{i:02d}", "date": dates.date,
                                    "net_value": rng.normal(0, 5e8, days), "value": rng.uniform(5e9, 2e10, days)}))
    return pd.concat(frames, ignore_index=True)


def create(service, spec: dict, message: str, request_id: str = "run-1") -> dict:
    return service.create_spec(SpecRequest(request_id=request_id, reference_time=REFERENCE,
                                           user_messages=[{"role": "user", "content": message}], spec=spec))


def submit(service, spec_id: str, ds: str, code: str, request_id: str = "run-1", name: str = "prices") -> dict:
    return service.submit(AnalysisRequest(request_id=request_id, spec_id=spec_id, python_code=code,
                                          inputs=[{"name": name, "dataset_ids": [ds],
                                                   "duplicate_policy": "ERROR_ON_CONFLICT"}],
                                          expected_outputs=["TABLE"]))


EVENT_CODE = '''
H = 5
THRESHOLD = {threshold}
df = load("prices", columns=["ticker", "date", "open", "close"])
df = df[~df["ticker"].isin({exclude})]
g = df.groupby("ticker")
mean = g["close"].transform(lambda s: s.rolling(20).mean())
std = g["close"].transform(lambda s: s.rolling(20).std())
df["z"] = (df["close"] - mean) / std
df["fwd"] = g["close"].shift(-H) / g["open"].shift(-1) - 1
df["pos"] = g.cumcount()
period = df[in_period(df)]
signal = period["z"].notna()
eligible = period[signal & period["fwd"].notna()]
raw = period[signal & (period["z"] < THRESHOLD)]
events = raw[raw["fwd"].notna()]
kept = []
for _, part in events.groupby("ticker"):
    last = None
    for index, row in part.iterrows():
        if {overlap} and last is not None and row["pos"] < last + H:
            continue
        kept.append(index)
        last = row["pos"]
chosen = events.loc[kept]
emit_table("summary", pd.DataFrame([{{
    "segment": "ALL", "event_count": len(chosen), "mean": chosen["fwd"].mean(), "median": chosen["fwd"].median(),
    "hit_rate": (chosen["fwd"] > 0).mean(), "baseline_count": len(eligible), "baseline_mean": eligible["fwd"].mean(),
    "baseline_median": eligible["fwd"].median(), "delta_mean": chosen["fwd"].mean() - eligible["fwd"].mean(),
    "censored_count": int(raw["fwd"].isna().sum()), "overlapping_dropped": len(events) - len(chosen)}}]))
'''


def event_code(threshold: float = -1.5, respect_overlap: bool = True, exclude: tuple = ()) -> str:
    return EVENT_CODE.format(threshold=threshold, overlap="True" if respect_overlap else "False",
                             exclude=list(exclude))


def event_dataset(governor, **kwargs) -> str:
    return governor.add(ohlc(**kwargs), requested_from="2024-06-03", requested_to="2026-09-23")


# ---------------------------------------------------------------- A: standard calculation

def test_A_standard_calculation_stays_minimal_and_is_supported(make_service, governor) -> None:
    """FIXTURE TEST A: a documented, tested method: no research block, no hypothesis, no loop."""
    service = make_service()
    review = create(service, zscore_spec(), "Calculate rolling 20-day z-scores for all IDX stocks over the last "
                                            "three months.")
    assert review["status"] == "APPROVED" and "governor" not in review
    ds = governor.add(ohlc(days=160, start="2026-02-02"), requested_from="2026-02-02", requested_to="2026-09-23")
    code = ('df = load("prices", columns=["ticker", "date", "close"])\ng = df.groupby("ticker")["close"]\n'
            'df["zscore_20"] = (df["close"] - g.transform(lambda s: s.rolling(20).mean())) / '
            'g.transform(lambda s: s.rolling(20).std())\nemit_table("zscores", df[in_period(df)][["ticker", "date", '
            '"zscore_20"]])\n')
    result = submit(service, review["spec_id"], ds, code)
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED")
    evidence = result["evidence_assessment"]
    assert (evidence["claim_type"], evidence["decision"], evidence["evidence_level"]) == (
        "CALCULATION", "SUPPORTED", "OBSERVATION")
    assert evidence["checks"]["minimum_sample"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------- B: custom formula

def test_B_custom_formula_is_recalculated_and_labelled_as_a_validated_custom_result(make_service, governor) -> None:
    """FIXTURE TEST B: a niche ratio absent from AI_formula_reference, defined by the AI as an expression."""
    service = make_service()
    review = create(service, custom_ratio_spec(), "Foreign accumulation ratio for all stocks over the last three "
                                                  "months.")
    assert review["status"] in ("APPROVED", "APPROVED_WITH_UNVERIFIED"), review
    ds = governor.add(flows(), source_table="Feature_03_Stock_Broker_Daily", requested_from="2026-04-01",
                      requested_to="2026-09-23", units={"net_value": "IDR", "value": "IDR"})
    code = ('df = load("flows", columns=["ticker", "date", "net_value", "value"])\ng = df.groupby("ticker")\n'
            'df["foreign_accumulation_ratio"] = g["net_value"].transform(lambda s: s.rolling(20).sum()) / '
            'g["value"].transform(lambda s: s.rolling(20).sum())\n'
            'emit_table("ratios", df[in_period(df)][["ticker", "date", "foreign_accumulation_ratio"]])\n')
    result = submit(service, review["spec_id"], ds, code, name="flows")
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    feature = result["derived_features"][0]
    assert feature["formula_status"] == "VALIDATED_CUSTOM_FORMULA_RESULT"
    assert feature["independent_check_result"] == "RECALCULATED_MATCH"
    # the same formula written with a wrong window is a mismatch, never a pre-tested implementation
    wrong = submit(service, review["spec_id"], ds, code.replace("rolling(20)", "rolling(10)"), name="flows")
    assert wrong["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in wrong["reason_codes"]
    assert wrong["derived_features"][0]["formula_status"] == "CUSTOM_FORMULA"


def test_B_units_that_do_not_add_up_stop_the_analysis(make_service, governor) -> None:
    service = make_service()
    spec = custom_ratio_spec(expression_text="net_value + value", unit="IDR")
    review = create(service, spec, "Net value plus traded value for all stocks over the last three months.")
    ds = governor.add(flows(), source_table="Feature_03_Stock_Broker_Daily", requested_from="2026-04-01",
                      requested_to="2026-09-23", units={"net_value": "IDR", "value": "lots"})
    result = submit(service, review["spec_id"], ds, 'emit_table("ratios", load("flows"))\n', name="flows")
    assert result["validation_status"] == "FAILED" and "UNIT_MISMATCH" in result["reason_codes"]


# ---------------------------------------------------------------- C: multi-asset grouping

def test_C_cross_asset_shift_is_detected(make_service, governor) -> None:
    """FIXTURE TEST C: a 5-day return computed with shift() on the concatenated panel mixes entities."""
    service = make_service()
    spec = custom_ratio_spec(expression_text="close / lag(close, 5) - 1", unit="ratio")
    spec["inputs"] = [{"name": "prices", "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker",
                       "date_column": "date", "columns": ["ticker", "date", "close"]}]
    spec["calculations"][0].update(dataset="prices", columns=["close"], output_column="ret_5")
    spec["outputs"] = [{"name": "returns", "grain": "ENTITY_DATE", "calculations": ["far"]}]
    review = create(service, spec, "Five-day price change for all stocks over the last three months.")
    # a ticker listed inside the period: its first rows follow another ticker's last rows in the sorted panel,
    # so an unpartitioned shift(5) gives it values where it has no 5-day history
    listed_late = ohlc(tickers=1, start="2026-07-15", days=50, seed=8).assign(ticker="ZNEW")
    panel = pd.concat([ohlc(tickers=5, days=160, start="2026-02-02"), listed_late], ignore_index=True)
    ds = governor.add(panel, requested_from="2026-02-02", requested_to="2026-09-23")
    body = 'df = load("prices", columns=["ticker", "date", "close"])\n{calc}\nemit_table("returns", ' \
           'df[in_period(df)][["ticker", "date", "ret_5"]])\n'
    wrong = submit(service, review["spec_id"], ds, body.format(calc='df["ret_5"] = df["close"] / df["close"]'
                                                                    '.shift(5) - 1'))
    assert wrong["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in wrong["reason_codes"]
    right = submit(service, review["spec_id"], ds, body.format(calc='df["ret_5"] = df["close"] / df.groupby('
                                                                    '"ticker")["close"].shift(5) - 1'))
    assert (right["validation_status"], right["validation_level"]) == ("PASS", "CALCULATION_VERIFIED")


# ---------------------------------------------------------------- D and E: event study

def test_D_event_study_is_recalculated_and_assessed(make_service, governor) -> None:
    """FIXTURE TEST D: event definition, forward outcome, baseline, overlap, censoring, coverage, chronology."""
    service = make_service()
    review = create(service, event_study_spec(), EVENT_QUESTION)
    assert review["status"] in ("APPROVED", "APPROVED_WITH_UNVERIFIED"), review
    assert review["governor"]["decision"] == "APPROVED"
    assert review["output_contract"][0]["key_columns"] == ["segment"]
    result = submit(service, review["spec_id"], event_dataset(governor), event_code())
    assert (result["validation_status"], result["validation_level"]) == ("PASS", "CALCULATION_VERIFIED"), \
        result["validation_evidence"]
    assessment = result["evidence_assessment"]
    stats = assessment["statistics"]["segments"]["ALL"]
    assert assessment["claim_type"] == "HISTORICAL_PATTERN" and assessment["source"] == "VALIDATOR"
    assert stats["event_count"] >= 30 and stats["baseline_count"] > stats["event_count"]
    assert set(assessment["checks"]) >= {"minimum_sample", "baseline", "coverage", "overlap", "censoring",
                                         "uncertainty", "multiple_testing"}
    assert assessment["decision"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    assert "Describe the result as a historical association, not causation." in assessment["reporting_constraints"]
    assert any(w["code"] == "CORPORATE_ACTIONS_NOT_ADJUSTED" for w in result["warnings"])


def test_E_incorrect_event_study_is_rejected_and_never_supported(make_service, governor) -> None:
    """FIXTURE TEST E: overlapping events counted despite NON_OVERLAPPING; the validator recomputes and fails it."""
    service = make_service()
    review = create(service, event_study_spec(), EVENT_QUESTION)
    result = submit(service, review["spec_id"], event_dataset(governor), event_code(respect_overlap=False))
    assert result["validation_status"] == "FAILED" and "CALCULATION_MISMATCH" in result["reason_codes"]
    assert result["evidence_assessment"]["decision"] == "INVALID"


# ---------------------------------------------------------------- F: future leakage

def _custom_zscore_spec() -> dict:
    spec = custom_ratio_spec(expression=None, formula="(close - mean) / std", unit="ratio")
    spec["inputs"] = [{"name": "prices", "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker",
                       "date_column": "date", "columns": ["ticker", "date", "close"]}]
    spec["calculations"][0].update(dataset="prices", columns=["close"], output_column="score",
                                   params=[{"name": "warmup_observations", "value": 20, "provenance": "AI_INFERRED"}])
    spec["outputs"] = [{"name": "scores", "grain": "ENTITY_DATE", "calculations": ["far"]}]
    return spec


def test_F_future_information_in_a_custom_signal_is_detected(make_service, governor) -> None:
    """FIXTURE TEST F: normalising with the full-sample mean uses the future; the prefix re-run exposes it."""
    service = make_service()
    review = create(service, _custom_zscore_spec(), "A normalised price score for all stocks over the last three "
                                                    "months.")
    ds = governor.add(ohlc(days=160, start="2026-02-02"), requested_from="2026-02-02", requested_to="2026-09-23")
    body = 'df = load("prices", columns=["ticker", "date", "close"])\ng = df.groupby("ticker")["close"]\n{calc}\n' \
           'emit_table("scores", df[in_period(df)][["ticker", "date", "score"]])\n'
    leaking = submit(service, review["spec_id"], ds, body.format(
        calc='df["score"] = (df["close"] - g.transform("mean")) / g.transform("std")'))
    assert leaking["validation_status"] == "FAILED" and "TEMPORAL_LEAKAGE_DETECTED" in leaking["reason_codes"]
    assert leaking["leakage_check"]["result"] == "FAIL" and leaking["evidence_assessment"]["decision"] == "INVALID"
    trailing = submit(service, review["spec_id"], ds, body.format(
        calc='df["score"] = (df["close"] - g.transform(lambda s: s.rolling(20).mean())) / '
             'g.transform(lambda s: s.rolling(20).std())'))
    assert trailing["leakage_check"]["result"] == "PASS" and "TEMPORAL_LEAKAGE_DETECTED" not in \
        trailing["reason_codes"]
    # a free-form CUSTOM passes on scope only; its values are still not recalculated
    assert (trailing["validation_status"], trailing["validation_level"]) == ("PASS", "SCOPE_VERIFIED")


# ---------------------------------------------------------------- G: incomplete dataset

def test_G_truncated_and_incomplete_inputs_are_reported(make_service, governor) -> None:
    """FIXTURE TEST G: the dataset stops before the period ends, and a requested ticker is missing."""
    service = make_service()
    review = create(service, event_study_spec(), EVENT_QUESTION)
    short = governor.add(ohlc(days=300), requested_from="2024-06-03", requested_to="2025-07-31")
    result = submit(service, review["spec_id"], short, event_code())
    assert result["validation_status"] == "INCOMPLETE" and "ANALYSIS_SCOPE_MISMATCH" in result["reason_codes"]
    assert result["evidence_assessment"]["decision"] == "INSUFFICIENT_EVIDENCE"
    spec = event_study_spec(universe={"type": "TICKERS", "tickers": ["T00", "T01", "ZZZZ"],
                                      "provenance": "USER_EXPLICIT", "default_id": None})
    review = create(service, spec, EVENT_QUESTION.replace("all IDX stocks", "T00, T01 and ZZZZ"),
                    request_id="run-g2")
    partial = governor.add(ohlc(tickers=2), requested_from="2024-06-03", requested_to="2026-09-23",
                           entities=["T00", "T01", "ZZZZ"], missing=["ZZZZ"])
    result = submit(service, review["spec_id"], partial, event_code(), request_id="run-g2")
    assert result["validation_status"] == "INCOMPLETE" and "UNIVERSE_SOURCE_UNAVAILABLE" in result["reason_codes"]


# ---------------------------------------------------------------- H: governor bypass

def test_H_execution_without_approval_fails_deterministically(make_service, governor) -> None:
    """FIXTURE TEST H: a rejected experiment has no spec_id; a made-up or foreign spec_id cannot run."""
    service = make_service(PY_SANDBOX_RESEARCH_MAX_EXPERIMENTS="1")
    first = create(service, event_study_spec(), EVENT_QUESTION)
    second_research = {**event_study_spec()["research"], "hypothesis": {"id": "H2", "statement": "another"}}
    second = create(service, event_study_spec(second_research), EVENT_QUESTION)
    assert (second["status"], second["governor"]["reason_code"]) == ("REJECTED", "RESEARCH_BUDGET_EXCEEDED")
    assert "spec_id" not in second and second["next_action"] == "REPORT_LIMITATION"
    ds = event_dataset(governor)
    for spec_id, request_id in (("spec_" + "f" * 24, "run-1"), (first["spec_id"], "someone-else")):
        with pytest.raises(ServiceUnavailable) as error:
            submit(service, spec_id, ds, event_code(), request_id=request_id)
        assert error.value.code == "SPEC_NOT_FOUND"


# ---------------------------------------------------------------- I: bounded follow-up

def test_I_follow_up_research_is_governed_and_bounded(make_service, governor) -> None:
    """FIXTURE TEST I: initial experiment -> approved follow-up -> second result -> budget exhausted."""
    service = make_service(PY_SANDBOX_RESEARCH_MAX_FOLLOWUPS_PER_HYPOTHESIS="1")
    ds = event_dataset(governor)
    first = create(service, event_study_spec(), EVENT_QUESTION)
    early = {**event_study_spec()["research"], "followup_of": first["spec_id"]}

    def without(tickers: list[str]) -> dict:  # a follow-up the user did not state: an AI-chosen exclusion
        return event_study_spec(early, exclusion_rules=[{"rule": "EXCLUDE_TICKERS", "value": tickers,
                                                         "provenance": "AI_INFERRED"}])

    too_early = create(service, without(["T10", "T11"]), EVENT_QUESTION)
    assert too_early["governor"]["reason_code"] == "FOLLOWUP_PARENT_NOT_COMPLETED" and "spec_id" not in too_early
    submit(service, first["spec_id"], ds, event_code())
    follow = create(service, without(["T10", "T11"]), EVENT_QUESTION)
    assert follow["governor"]["decision"] == "APPROVED" and follow["spec_id"]
    second = submit(service, follow["spec_id"], ds, event_code(exclude=("T10", "T11")))
    assert second["validation_status"] == "PASS", second["validation_evidence"]
    assert second["evidence_assessment"]["statistics"]["tests_on_hypothesis"] == 2
    third = create(service, without(["T09", "T10", "T11"]), EVENT_QUESTION)
    assert (third["status"], third["governor"]["reason_code"]) == ("REJECTED", "FOLLOWUP_LIMIT_EXCEEDED")
    summary = service.run_summary("run-1")
    assert [e["research"]["followup_of"] for e in summary["experiments"]] == [None, first["spec_id"]]
    assert summary["budget"]["research"]["followups"] == {"H1": 1}


# ---------------------------------------------------------------- J: retry and restart

def test_J_retries_do_not_double_count_and_state_survives_a_restart(make_service, governor) -> None:
    """FIXTURE TEST J: a retried spec or analysis reuses the first; a restarted service reports the same run."""
    service = make_service()
    first = create(service, event_study_spec(), EVENT_QUESTION)
    retry = create(service, event_study_spec(), EVENT_QUESTION)
    assert retry["spec_id"] == first["spec_id"] and retry["replayed"] is True
    assert service.records.count_specs("run-1") == 1
    ds = event_dataset(governor)
    one = submit(service, first["spec_id"], ds, event_code())
    two = submit(service, first["spec_id"], ds, event_code())
    assert one["analysis_id"] == two["analysis_id"] and service.records.request_usage("run-1")["analyses"] == 1
    api = TestClient(create_app(service.settings, service=service, run_workers=False))
    report = {"status": "COMPLETED", "response_type": "ANSWER", "evidence_label": "CALCULATION_VERIFIED",
              "validation_gate": "PASSED", "question_sha256": "a" * 64, "question": EVENT_QUESTION,
              "answer_sha256": "b" * 64, "answer": "x", "limitations": [], "experiments": [], "model": "m",
              "tool_call_count": 4, "total_tokens": 10, "duration_ms": 5}
    assert api.post("/v1/runs/run-1/report", json=report, headers=HEADERS).json()["stored"] is True
    assert api.post("/v1/runs/run-1/report", json={**report, "answer": "changed"}, headers=HEADERS).json()[
        "stored"] is False
    service.stop()
    restarted = make_service()
    summary = restarted.run_summary("run-1")
    assert summary["status"] == "REPORTED" and summary["report"]["answer"] == "x"
    assert [a["analysis_id"] for a in summary["analyses"]] == [one["analysis_id"]]
    assert summary["analyses"][0]["evidence"]["claim_type"] == "HISTORICAL_PATTERN"
    assert summary["experiments"][0]["governor"]["decision"] == "APPROVED"
    again = create(restarted, event_study_spec(), EVENT_QUESTION)
    assert again["spec_id"] == first["spec_id"] and restarted.records.count_specs("run-1") == 1
    api = TestClient(create_app(restarted.settings, service=restarted, run_workers=False))
    assert api.get("/v1/runs/run-1", headers=HEADERS).json()["request_id"] == "run-1"
    assert api.get("/v1/runs/unknown-run", headers=HEADERS).status_code == 404
