"""Event study (G2, 2026-10-02): the shared statistics (runtime/event_study.py), the session helper
saniti.event_study() and the backend's independent recalculation at complete_analysis
(app/event_study_validation.py).

The unit cases build their own frames, including a series without an entity column and with other column names (a
rate, not a stock price), so nothing here depends on one table or asset."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import event_study as ES  # noqa: E402
import research_engines as E  # noqa: E402
import research_inputs  # noqa: E402

from conftest import requires_root  # noqa: E402
from test_dataneed_bundles import HEADERS, env  # noqa: E402,F401 - env is a fixture
from test_dataneed_sessions import ok, run, session  # noqa: E402,F401 - session is a fixture


def frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "entity", "condition", "outcome"])


def days(n: int, start: str = "2025-01-01") -> list[pd.Timestamp]:
    return list(pd.bdate_range(start, periods=n))


def summary(data: pd.DataFrame, **params) -> tuple[dict, pd.DataFrame]:
    rows, events = ES.summarize(data, ES.parameters(**params))
    return {r["segment"]: r for r in rows}, events


# ------------------------------------------------------------------------------------------ parameters


@pytest.mark.parametrize("kwargs", [{"horizon": 0}, {"horizon": True}, {"horizon": 261}, {"horizon": 1.5},
                                    {"horizon": 5, "overlap_policy": "SOME"}, {"horizon": 5, "baseline": "OTHER"},
                                    {"horizon": 5, "min_events": 0}, {"horizon": 5, "holdout_start": "2025-13-01"}])
def test_parameters_outside_the_policy_are_refused(kwargs) -> None:
    with pytest.raises(ES.EventStudyError) as caught:
        ES.parameters(**kwargs)
    assert caught.value.code == "PARAMETER_INVALID"


def test_the_defaults_are_recorded_policy_values() -> None:
    assert ES.parameters(5) == {"horizon": 5, "overlap_policy": "NON_OVERLAPPING", "baseline": "ALL_ELIGIBLE",
                                "min_events": ES.DEFAULT_MIN_EVENTS, "holdout_start": None}


# ------------------------------------------------------------------------------------------ events, overlap, censoring


def test_non_overlapping_keeps_an_entitys_next_event_only_a_horizon_after_the_last_kept_one() -> None:
    d = days(10)
    hits = {0, 1, 2, 5, 6}
    data = frame([(d[i], "A", i in hits, float(i)) for i in range(10)])
    kept, events = summary(data, horizon=3)
    assert kept["ALL"]["event_count"] == 2 and kept["ALL"]["overlapping_dropped"] == 3
    assert list(events["outcome"]) == [0.0, 5.0] and kept["ALL"]["mean"] == 2.5
    every, events = summary(data, horizon=3, overlap_policy="ALL")
    assert every["ALL"]["event_count"] == 5 and every["ALL"]["overlapping_dropped"] == 0
    assert every["ALL"]["mean"] == pytest.approx(np.mean([0, 1, 2, 5, 6]))


def test_overlap_is_counted_per_entity() -> None:
    d = days(4)
    data = frame([(d[i], e, i in (0, 1), float(i)) for e in ("A", "B") for i in range(4)])
    kept, _ = summary(data, horizon=2)
    assert kept["ALL"]["event_count"] == 2 and kept["ALL"]["overlapping_dropped"] == 2


def test_an_event_whose_outcome_runs_past_the_data_is_censored_not_counted() -> None:
    d = days(6)
    data = frame([(d[i], "A", i in (1, 5), float(i) if i < 4 else math.nan) for i in range(6)])
    kept, _ = summary(data, horizon=1, min_events=1)
    assert kept["ALL"]["event_count"] == 1 and kept["ALL"]["censored_count"] == 1
    assert kept["ALL"]["baseline_count"] == 4  # rows with a defined condition and outcome
    assert kept["ALL"]["meets_min_events"] is True


def test_the_baseline_is_every_eligible_row_or_only_the_rows_without_the_event() -> None:
    d = days(8)
    data = frame([(d[i], "A", i % 2 == 0, float(i)) for i in range(8)] + [(d[0], "B", None, 1.0)])
    eligible, _ = summary(data, horizon=1, overlap_policy="ALL")
    non_event, _ = summary(data, horizon=1, overlap_policy="ALL", baseline="NON_EVENT")
    assert eligible["ALL"]["baseline_count"] == 8  # the row with an unknown condition is not eligible
    assert non_event["ALL"]["baseline_count"] == 4
    assert non_event["ALL"]["baseline_mean"] == pytest.approx(np.mean([1, 3, 5, 7]))
    assert eligible["ALL"]["delta_mean"] == pytest.approx(np.mean([0, 2, 4, 6]) - np.mean(range(8)))


def test_a_holdout_date_adds_in_sample_and_out_of_sample_rows_that_add_up() -> None:
    d = days(40)
    rng = np.random.default_rng(3)
    data = frame([(d[i], e, bool(rng.random() < 0.3), float(rng.normal())) for e in ("A", "B", "C")
                  for i in range(40)])
    rows, _ = summary(data, horizon=2, holdout_start=d[25].date().isoformat())
    assert list(rows) == ["ALL", "IN_SAMPLE", "OUT_OF_SAMPLE"]
    for column in ("event_count", "baseline_count", "censored_count", "overlapping_dropped"):
        assert rows["IN_SAMPLE"][column] + rows["OUT_OF_SAMPLE"][column] == rows["ALL"][column], column


def test_many_events_on_one_date_are_one_observation_not_many() -> None:
    """Copies of every row across more entities on the same dates add no information; a CI over independent rows
    would narrow by the square root of the copies, the date-clustered one stays the same."""
    rng = np.random.default_rng(11)
    d = days(120)
    base = [(d[i], "E0", bool(rng.random() < 0.25), float(rng.normal())) for i in range(120)]
    one, _ = summary(frame(base), horizon=1, overlap_policy="ALL")
    copies, _ = summary(frame([(day, f"E{k}", c, o) for k in range(10) for day, _, c, o in base]), horizon=1,
                        overlap_policy="ALL")
    assert copies["ALL"]["event_count"] == 10 * one["ALL"]["event_count"]
    assert copies["ALL"]["event_dates"] == one["ALL"]["event_dates"]
    assert copies["ALL"]["delta_mean"] == pytest.approx(one["ALL"]["delta_mean"])
    assert copies["ALL"]["delta_ci_low"] == pytest.approx(one["ALL"]["delta_ci_low"])
    assert copies["ALL"]["delta_ci_high"] == pytest.approx(one["ALL"]["delta_ci_high"])


def test_the_effective_count_thins_dates_closer_than_the_horizon() -> None:
    d = days(30)
    data = frame([(d[i], "A", True, float(i)) for i in range(30)])
    daily, _ = summary(data, horizon=1, overlap_policy="ALL")
    weekly, _ = summary(data, horizon=5, overlap_policy="ALL")
    assert daily["ALL"]["effective_event_dates"] == 30 and weekly["ALL"]["effective_event_dates"] == 6


def test_two_rows_for_one_entity_and_date_are_refused() -> None:
    d = days(3)
    data = frame([(d[0], "A", True, 1.0), (d[0], "A", False, 2.0), (d[1], "A", False, 0.5)])
    with pytest.raises(ES.EventStudyError) as caught:
        summary(data, horizon=1)
    assert caught.value.code == "DUPLICATE_ENTITY_DATE"


# ------------------------------------------------------------------------------------------ input from a declaration


def test_a_series_without_entities_and_with_other_column_names_is_studied_from_its_declaration() -> None:
    """Not a stock: one rate series, its own time column name, a rise of at least 1% as the event."""
    stamps = days(12)
    rate = [100, 101.5, 101, 102.2, 102, 102, 103.5, 103, 103, 104.2, 104, 104]
    rows = pd.DataFrame({"observed_on": [t.date() for t in stamps], "rate": rate})
    window = {"range_id": "r1", "start": stamps[1].date().isoformat(), "end": stamps[9].date().isoformat(),
              "extract_from": stamps[0].date().isoformat(), "extract_to": stamps[11].date().isoformat()}
    declaration = {"request": "fx", "range_id": None,
                   "roles": {"condition": "rate / lag(rate, 1) - 1 >= 0.01", "outcome": {"forward_return": "rate"}}}
    built, info = ES.build_input(research_inputs, declaration, rows, entity_column=None, time_column="observed_on",
                                 columns=["rate"], ranges=[window], horizon=2, unit="DECIMAL")
    assert info["rows"] == 9 and set(built["entity"]) == {"_all"}
    rows_, events = summary(built, horizon=2, overlap_policy="ALL", min_events=1)
    rises = [i for i in range(1, 10) if rate[i] / rate[i - 1] - 1 >= 0.01]
    assert rises == [1, 3, 6, 9]
    expected = [rate[i + 2] / rate[i] - 1 for i in rises]
    assert list(events["outcome"]) == pytest.approx(expected)
    assert rows_["ALL"]["mean"] == pytest.approx(np.mean(expected))


def test_each_range_reads_only_its_own_window_so_a_forward_return_never_joins_two_ranges() -> None:
    """Two ranges a year apart: the last events of the first range are censored, not completed with the price of the
    next range."""
    first, second = days(10, "2024-03-01"), days(10, "2025-03-03")
    rows = pd.DataFrame({"ticker": "A", "date": [t.date() for t in first + second],
                         "close": [100.0 - i for i in range(10)] + [500.0 + i for i in range(10)]})
    ranges = [{"range_id": "earlier", "start": first[0].date().isoformat(), "end": first[-1].date().isoformat(),
               "extract_from": first[0].date().isoformat(), "extract_to": first[-1].date().isoformat()},
              {"range_id": "later", "start": second[0].date().isoformat(), "end": second[-1].date().isoformat(),
               "extract_from": second[0].date().isoformat(), "extract_to": second[-1].date().isoformat()}]
    declaration = {"request": "prices", "range_id": None,
                   "roles": {"condition": "close < lag(close, 1)", "outcome": {"forward_return": "close"}}}
    built, info = ES.build_input(research_inputs, declaration, rows, entity_column="ticker", time_column="date",
                                 columns=["close"], ranges=ranges, horizon=2, unit="PERCENT")
    early = built[built["date"] <= pd.Timestamp(first[-1])]
    assert early["outcome"].tail(2).isna().all()  # censored at the end of its own window
    assert early["outcome"].dropna().max() < 0  # a falling series stays a loss; never a jump to the next range
    assert info["censored_outcome_rows"] == 4 and [r["range_id"] for r in info["ranges"]] == ["earlier", "later"]


def test_overlapping_ranges_ask_for_one_range() -> None:
    ranges = [{"range_id": "a", "start": "2025-01-01", "end": "2025-03-31"},
              {"range_id": "b", "start": "2025-03-01", "end": "2025-06-30"}]
    with pytest.raises(ES.EventStudyError) as caught:
        ES.build_input(research_inputs, {}, pd.DataFrame(), entity_column=None, time_column="date", columns=[],
                       ranges=ranges, horizon=1, unit="PERCENT")
    assert caught.value.code == "RANGES_OVERLAP"


# ------------------------------------------------------------------------------------------ comparison


def test_compare_names_each_changed_cell_and_each_missing_or_extra_segment() -> None:
    d = days(30)
    data = frame([(d[i], "A", i % 3 == 0, float(i % 7)) for i in range(30)])
    rows, events = ES.summarize(data, ES.parameters(1, overlap_policy="ALL"))
    assert ES.compare(rows, rows) == []
    changed = [{**rows[0], "mean": rows[0]["mean"] + 0.01, "event_count": rows[0]["event_count"] + 1}]
    assert {m["column"] for m in ES.compare(changed, rows)} == {"mean", "event_count"}
    assert ES.compare([], rows) == [{"segment": "ALL", "column": "segment", "expected": "ALL", "actual": None}]
    extra = rows + [{**rows[0], "segment": "OTHER"}]
    assert ES.compare(extra, rows)[0]["column"] == "segment"
    released = events.assign(date=events["date"].dt.date).to_dict("records")
    assert ES.compare_events(released, events) == []
    released[0]["outcome"] += 1.0
    assert [m["row"] for m in ES.compare_events(released, events)] == [0]
    assert ES.compare_events(released[1:], events)[0]["column"] == "rows"


def test_the_summary_uses_the_research_engines_statistics() -> None:
    rng = np.random.default_rng(5)
    d = days(60)
    data = frame([(d[i], e, bool(rng.random() < 0.3), float(rng.normal(0.2))) for e in ("A", "B") for i in range(60)])
    rows, _ = summary(data, horizon=1, overlap_policy="ALL")
    events = data[data["condition"]]
    assert rows["ALL"]["mean"] == pytest.approx(events["outcome"].mean())
    assert rows["ALL"]["hit_rate"] == pytest.approx((events["outcome"] > 0).mean())
    assert 0 <= rows["ALL"]["delta_p_value"] <= 1 and rows["ALL"]["delta_ci_low"] < rows["ALL"]["delta_ci_high"]
    assert E.ALPHA == 0.05


# ------------------------------------------------------------------------------------------ in a session


def complete(env) -> dict:  # noqa: F811
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                               headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


STUDY = ("study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', {'forward_return': 'close'}, 3, "
         "name='drops', min_events=1EXTRA)\nbanks = load('stock_classification')\n")


def expected_events(env) -> pd.DataFrame:
    """The same study computed here with plain pandas from the delivered bundle files, range by range."""
    import pyarrow.parquet as pq

    manifest = env["dataneed"].get_bundle(env["bundle_id"])
    prices = next(d for d in manifest["datasets"] if d["logical_name"] == "prices")
    rows = pd.concat([pq.read_table(env["dataneed"].bundles.path_of(env["bundle_id"], p["file"])).to_pandas()
                      for p in prices["partitions"]], ignore_index=True)
    rows["date"] = pd.to_datetime(rows["date"])
    found = []
    for window in prices["ranges"]:
        part = rows[(rows["date"] >= pd.Timestamp(window["extract_from"]))
                    & (rows["date"] <= pd.Timestamp(window["extract_to"]))].sort_values(["ticker", "date"])
        for ticker, series in part.groupby("ticker"):
            close = series["close"].to_numpy()
            dates = series["date"].to_numpy()
            last_kept = None
            for i in range(1, len(close)):
                inside = pd.Timestamp(window["start"]) <= dates[i] <= pd.Timestamp(window["end"])
                if not inside or close[i] / close[i - 1] - 1 > -0.01 or i + 3 >= len(close):
                    continue
                if last_kept is not None and i - last_kept < 3:
                    continue
                last_kept = i
                found.append({"date": pd.Timestamp(dates[i]), "entity": ticker,
                              "outcome": (close[i + 3] / close[i] - 1) * 100})
    return pd.DataFrame(found).sort_values(["entity", "date"]).reset_index(drop=True)


@requires_root
def test_an_event_study_is_recomputed_by_the_backend_and_its_tables_are_verified(session) -> None:
    body = ok(session, STUDY.replace("EXTRA", "") + "emit_table('other', banks)\n"
                                                    "print(study['summary'][0]['event_count'])")
    names = [o["name"] for o in body["outputs"]]
    assert names[:4] == ["drops", "drops_events", "drops_baseline", "event_study_call_drops"] and names[-1] == "other"
    expected = expected_events(session)
    assert int(body["stdout"].strip()) == len(expected) > 0
    result = complete(session)
    final = result["final_status"]
    assert result["status"] == "COMPLETED", result
    study = final["event_studies"][0]
    assert study["status"] == "PASS" and study["mismatched"] == 0 and study["checked"] > len(expected)
    ids = {o["name"]: o["output_id"] for o in body["outputs"]}
    assert final["verified_output_ids"] == [ids["drops"], ids["drops_events"], ids["drops_baseline"]]
    assert final["calculation_validation"] == "PARTIAL"  # the other table was not recomputed
    assert "event_study_call_drops" not in [o["name"] for o in result["released_outputs"]]
    assert "the calculation was independently verified" not in final["claims_forbidden"]
    assert any("other than the event studies ['drops']" in c for c in final["claims_forbidden"])
    assert any("event studies ['drops'] were recomputed" in c for c in final["claims_allowed"])
    page = session["api"].get(f"/v1/sessions/{session['session_id']}/outputs/{ids['drops_events']}",
                              params={"request_id": "req_bundle_1", "limit": 500}, headers=HEADERS).json()
    assert page["label"] == "CALCULATION_VERIFIED" and "recomputed" in page["label_meaning"]  # P5
    released = pd.DataFrame(page["rows"])
    assert list(released["entity"]) == list(expected["entity"])
    assert list(released["outcome"]) == pytest.approx(list(expected["outcome"]))


@requires_root
def test_a_completion_of_event_study_tables_only_is_formula_verified(session) -> None:
    ok(session, STUDY.replace("EXTRA", ", holdout_start='2026-02-01'"))
    result = complete(session)
    final = result["final_status"]
    assert result["status"] == "COMPLETED" and final["calculation_validation"] == "FORMULA_AND_STATISTICS_VERIFIED"
    rows = session["api"].get(f"/v1/sessions/{session['session_id']}/outputs/"
                              f"{final['event_studies'][0]['summary_output_id']}",
                              params={"request_id": "req_bundle_1"}, headers=HEADERS).json()["rows"]
    assert [r["segment"] for r in rows] == ["ALL", "IN_SAMPLE", "OUT_OF_SAMPLE"]


@requires_root
def test_a_changed_event_study_table_fails_completion_until_the_study_is_run_again(session) -> None:
    ok(session, STUDY.replace("EXTRA", "") + "fake = pd.DataFrame(study['summary'])\nfake['mean'] = fake['mean'] + 1\n"
                                          "emit_table('drops', fake)")
    result = complete(session)
    assert result["status"] == "INCOMPLETE" and result["next_action"] == "RUN_PYTHON"
    study = result["final_status"]["event_studies"][0]
    assert study["status"] == "FAIL" and study["reason"] == "CALCULATION_MISMATCH"
    assert {m["column"] for m in study["examples"]} == {"mean"}
    assert "drops (CALCULATION_MISMATCH" in result["message"] and result["released_outputs"] == []
    ok(session, STUDY.replace("EXTRA", ""))
    again = complete(session)
    assert again["status"] == "COMPLETED" and again["final_status"]["event_studies"][0]["status"] == "PASS"


@requires_root
def test_the_record_names_are_reserved_and_a_bad_declaration_is_a_script_error(session) -> None:
    refused = run(session, "emit_json('event_study_call_x', {'a': 1})").json()
    assert refused["status"] == "SCRIPT_ERROR" and refused["error_type"] == "InvalidOutput"
    bad = run(session, "event_study('prices', 'close <= lag(nothing, 1)', {'forward_return': 'close'}, 1)").json()
    assert bad["status"] == "SCRIPT_ERROR" and bad["error_type"] == "SanitiError"
    assert "EXPRESSION_INVALID" in str(bad) and "unknown name 'nothing'" in str(bad)
    shared = run(session, "event_study('prices', 'close < 0', {'forward_return': 'close'}, 1, "
                          "overlap_policy='SOMETIMES')").json()
    assert shared["status"] == "SCRIPT_ERROR" and "PARAMETER_INVALID" in str(shared)


@requires_root
def test_a_changed_baseline_table_fails_completion(session) -> None:
    ok(session, STUDY.replace("EXTRA", "") + "fake = study['baseline'].copy()\nfake['outcome'] = fake['outcome'] + 1\n"
                                          "emit_table('drops_baseline', fake)")
    study = complete(session)["final_status"]["event_studies"][0]
    assert study["status"] == "FAIL" and {m.get("table") for m in study["examples"]} == {"baseline"}
