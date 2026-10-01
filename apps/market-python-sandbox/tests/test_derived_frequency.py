"""IP2 solution 1: weekly and monthly analysis derived from daily rows (resample semantics version 1).

The runtime tests call saniti.resample() in-process on small golden frames whose boundaries are known by hand
(calendar Friday weeks, calendar months, a Friday holiday, a month ending on a weekend, the open current week and
month). The validator tests check the fail-closed DataNeed rules and the contract hash; the last test checks that a
request approved without the flag keeps the legacy behaviour and hash."""
from __future__ import annotations

import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from dataneed_fixtures import data_need_catalog, prices, subset, ytd_spec

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
RULES = {"open": "FIRST", "high": "MAX", "low": "MIN", "close": "LAST", "volume": "SUM"}


@pytest.fixture
def rs():
    """setup(frame_columns, ranges, reference, version=1, **request) -> the configured saniti_session module."""
    sys.path.insert(0, str(RUNTIME))
    import saniti_session as s

    saved = (dict(s.REQUESTS), s.REFERENCE_DATE)

    def setup(ranges=None, reference="2026-09-23", version=1, **extra):
        request = {"data_request_id": "g_A", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
                   "columns": ["ticker", "date", *RULES], "key_columns": ["ticker", "date"],
                   "entity_column": "ticker", "time_column": "date", "source_frequency": "1D",
                   "analysis_frequency": "1W", "resample": "WEEKLY", "resample_rules": dict(RULES),
                   "ranges": ranges if ranges is not None else [
                       {"range_id": "r", "start": "2026-08-01", "end": "2026-09-23",
                        "extract_from": "2026-08-01", "extract_to": "2026-09-23"}], **extra}
        if version is not None:
            request["resample_semantics_version"] = version
        s.REQUESTS.clear()
        s.REQUESTS["g_A"] = request
        s.REFERENCE_DATE = reference
        s._ACCESS.clear()
        return s

    yield setup
    s.REQUESTS.clear()
    s.REQUESTS.update(saved[0])
    s.REFERENCE_DATE = saved[1]


def ohlcv(rows: list[tuple]) -> pd.DataFrame:
    """rows: (ticker, iso date, open, high, low, close, volume)."""
    return pd.DataFrame([{"ticker": t, "date": date.fromisoformat(d), "open": o, "high": h, "low": low, "close": c,
                          "volume": v} for t, d, o, h, low, c, v in rows])


def trading_days(start: str, end: str, skip: tuple[str, ...] = ()) -> list[str]:
    days = pd.bdate_range(start, end)
    return [d.date().isoformat() for d in days if d.date().isoformat() not in skip]


def by(frame: pd.DataFrame, ticker: str, period_end: str) -> dict:
    [row] = frame[(frame["ticker"] == ticker) & (frame["period_end"] == date.fromisoformat(period_end))].to_dict(
        "records")
    return row


# ---------------------------------------------------------------------------------------- aggregation golden tests

def test_weekly_ohlcv_per_entity_on_calendar_friday_weeks(rs) -> None:
    s = rs()
    rows = []
    for i, day in enumerate(trading_days("2026-08-31", "2026-09-11")):  # two full Monday-Friday weeks
        rows.append(("AAAA", day, 100 + i, 110 + i, 90 + i, 105 + i, 1000))
        rows.append(("BBBB", day, 10 + i, 12 + i, 9 + i, 11 + i, 7))
    out = s.resample(ohlcv(rows), "prices")
    first = by(out, "AAAA", "2026-09-04")
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (100, 114, 90, 109, 5000)
    assert first["period_start"] == date(2026, 8, 29) and first["actual_first_date"] == date(2026, 8, 31)
    assert first["actual_last_date"] == date(2026, 9, 4) and first["observations"] == 5 and first["period_complete"]
    other = by(out, "BBBB", "2026-09-11")  # no mixing: BBBB has its own values
    assert (other["open"], other["high"], other["close"], other["volume"]) == (15, 21, 20, 35)
    assert list(out.columns) == ["ticker", "date", *RULES, "period_start", "period_end", "actual_first_date",
                                 "actual_last_date", "observations", "period_complete"]
    assert out["date"].tolist() == out["period_end"].tolist()  # the time column is the period label


def test_monthly_ohlcv_with_a_month_ending_on_a_weekend(rs) -> None:
    s = rs(analysis_frequency="1M", resample="MONTHLY", ranges=[
        {"range_id": "r", "start": "2026-05-01", "end": "2026-06-30", "extract_from": "2026-05-01",
         "extract_to": "2026-06-30"}], reference="2026-07-15")
    rows = [("AAAA", d, 1.0, 2.0, 0.5, float(i), 10) for i, d in enumerate(trading_days("2026-05-01", "2026-06-30"))]
    out = s.resample(ohlcv(rows), "prices")
    may = by(out, "AAAA", "2026-05-31")  # 31 May 2026 is a Sunday: labelled by the calendar month end
    assert may["actual_last_date"] == date(2026, 5, 29) and may["period_start"] == date(2026, 5, 1)
    assert may["observations"] == 21 and may["close"] == 20.0 and may["volume"] == 210 and may["period_complete"]
    assert by(out, "AAAA", "2026-06-30")["period_complete"]


def test_a_friday_holiday_keeps_the_friday_label(rs) -> None:
    s = rs()
    rows = [("AAAA", d, 1, 1, 1, float(i), 1) for i, d in
            enumerate(trading_days("2026-08-31", "2026-09-11", skip=("2026-09-04",)))]
    out = s.resample(ohlcv(rows), "prices")
    week = by(out, "AAAA", "2026-09-04")
    assert week["actual_last_date"] == date(2026, 9, 3) and week["observations"] == 4 and week["close"] == 3.0
    assert week["period_complete"]  # later data exists, so the holiday week is closed


def test_the_open_current_week_and_month_are_incomplete(rs) -> None:
    s = rs(reference="2026-09-23")  # a Wednesday; data reaches it
    rows = [("AAAA", d, 1, 1, 1, 1.0, 1) for d in trading_days("2026-08-03", "2026-09-23")]
    weekly = s.resample(ohlcv(rows), "prices")
    assert not by(weekly, "AAAA", "2026-09-25")["period_complete"]
    assert by(weekly, "AAAA", "2026-09-18")["period_complete"]
    s = rs(reference="2026-09-23", analysis_frequency="1M", resample="MONTHLY")
    monthly = s.resample(ohlcv(rows), "prices")
    assert not by(monthly, "AAAA", "2026-09-30")["period_complete"]
    assert by(monthly, "AAAA", "2026-08-31")["period_complete"]
    trace = [a for a in s._ACCESS if a["call"] == "resample"][-1]
    assert trace["incomplete_periods"] == 1 and trace["incomplete_period_ends"] == ["2026-09-30"]
    assert trace["semantics_version"] == 1 and trace["input_rows"] == len(rows) and trace["rows"] == 2
    assert len(trace["rules_sha256"]) == 64 and "rows" in trace and "data" not in trace


def test_partly_covered_or_data_lagging_periods_are_not_marked_complete(rs) -> None:
    # the extraction window starts mid-week and the data stops a day before the reference date
    s = rs(ranges=[{"range_id": "r", "start": "2026-09-02", "end": "2026-09-23", "extract_from": "2026-09-02",
                    "extract_to": "2026-09-23"}], reference="2026-09-23")
    rows = [("AAAA", d, 1, 1, 1, 1.0, 1) for d in trading_days("2026-09-02", "2026-09-17")]
    out = s.resample(ohlcv(rows), "prices")
    assert not by(out, "AAAA", "2026-09-04")["period_complete"]  # starts before the window
    assert by(out, "AAAA", "2026-09-11")["period_complete"]
    assert not by(out, "AAAA", "2026-09-18")["period_complete"]  # the data ends Thursday 17th
    s = rs(ranges=[])  # no window: completeness cannot be established
    assert not s.resample(ohlcv(rows), "prices")["period_complete"].any()


def test_missing_days_and_nulls_are_deterministic(rs) -> None:
    s = rs()
    frame = ohlcv([("AAAA", "2026-09-07", 1, 5, 1, 2.0, 10), ("AAAA", "2026-09-08", None, 6, None, 3.0, None),
                   ("AAAA", "2026-09-11", 2, None, 0.5, None, 5),
                   ("BBBB", "2026-09-07", 1, 1, 1, 1.0, None), ("BBBB", "2026-09-08", 1, 1, 1, 1.0, None),
                   ("AAAA", "2026-09-14", 1, 1, 1, 1.0, 1), ("BBBB", "2026-09-14", 1, 1, 1, 1.0, 1)])
    shuffled = frame.sample(frac=1, random_state=7)
    out = s.resample(shuffled, "prices")
    week = by(out, "AAAA", "2026-09-11")
    # FIRST/LAST skip nulls in date order; MAX/MIN ignore nulls; SUM of the non-null values
    assert (week["open"], week["high"], week["low"], week["close"], week["volume"]) == (1, 6, 0.5, 3.0, 15)
    assert week["observations"] == 3  # Wednesday and Thursday are missing: counted, never filled
    assert math.isnan(by(out, "BBBB", "2026-09-11")["volume"])  # all null stays null, not zero
    assert out.equals(s.resample(frame, "prices"))  # input order does not change the result


def test_full_grain_groups_never_mix_brokers(rs) -> None:
    s = rs(columns=["ticker", "broker", "date", "net_value_1d"], key_columns=["ticker", "broker", "date"],
           resample_rules={"net_value_1d": "SUM"})
    frame = pd.DataFrame([{"ticker": "AAAA", "broker": b, "date": date.fromisoformat(d), "net_value_1d": v}
                          for b, d, v in (("YP", "2026-09-07", 10), ("YP", "2026-09-08", -3), ("CC", "2026-09-07", 4))])
    out = s.resample(frame, "prices")
    assert sorted(zip(out["broker"], out["net_value_1d"])) == [("CC", 4), ("YP", 7)]
    with pytest.raises(s.ResampleError) as dropped:
        s.resample(frame.drop(columns=["broker"]), "prices")
    assert dropped.value.code == "RESAMPLE_KEY_MISSING"


def test_asia_jakarta_trading_dates(rs) -> None:
    s = rs()
    frame = ohlcv([("AAAA", "2026-09-07", 1, 1, 1, 1.0, 1)])
    frame["date"] = [pd.Timestamp(datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc))]  # Saturday 5 Sep in Jakarta
    out = s.resample(frame, "prices")
    assert out["actual_first_date"].tolist() == [date(2026, 9, 5)] and out["period_end"].tolist() == [date(2026, 9, 11)]


# ---------------------------------------------------------------------------------------- fail closed

def test_duplicates_missing_rules_non_daily_sources_and_re_resampling_are_refused(rs) -> None:
    s = rs()
    rows = [("AAAA", "2026-09-07", 1, 1, 1, 1.0, 1), ("AAAA", "2026-09-07", 2, 2, 2, 2.0, 2)]
    with pytest.raises(s.ResampleError) as duplicate:
        s.resample(ohlcv(rows), "prices")
    assert duplicate.value.code == "DUPLICATE_ENTITY_DATE"
    frame = ohlcv(rows[:1]).assign(return_1d_pct=0.5)
    with pytest.raises(s.ResampleRuleMissing):
        s.resample(frame, "prices")
    weekly = s.resample(ohlcv(rows[:1]), "prices")
    with pytest.raises(s.ResampleError) as again:
        s.resample(weekly, "prices", "1M")  # monthly is never built from weekly
    assert again.value.code == "RESAMPLE_ALREADY_RESAMPLED"
    s = rs(source_frequency="1W")
    with pytest.raises(s.ResampleError) as weekly_source:
        s.resample(ohlcv(rows[:1]), "prices")
    assert weekly_source.value.code == "RESAMPLE_SOURCE_NOT_DAILY"


# ---------------------------------------------------------------------------------------- period returns

def test_period_returns_use_period_closes_not_summed_daily_returns(rs) -> None:
    s = rs()
    closes = {"2026-08-31": 100.0, "2026-09-01": 110.0, "2026-09-02": 99.0, "2026-09-03": 104.5, "2026-09-04": 105.0,
              "2026-09-07": 94.5, "2026-09-11": 126.0, "2026-09-21": 126.0}
    frame = ohlcv([("AAAA", d, c, c, c, c, 1) for d, c in closes.items()])
    weekly = s.resample(frame, "prices")
    returns = s.resampled_returns(weekly, "prices")
    rows = returns.to_dict("records")
    assert rows[0]["calculation_status"] == "NO_PRIOR_PERIOD" and math.isnan(rows[0]["return_decimal"])
    assert rows[1]["base_period_end"] == date(2026, 9, 4) and rows[1]["base_value"] == 105.0
    assert rows[1]["return_decimal"] == pytest.approx(126.0 / 105.0 - 1)  # week closes: 105 -> 126
    daily = pd.Series(list(closes.values())[:7]).pct_change().iloc[5:7].sum()
    assert rows[1]["return_decimal"] != pytest.approx(daily)  # not the sum of daily returns
    assert rows[2]["periods_between"] == 1 and rows[2]["return_decimal"] == pytest.approx(0.0)  # a week without trades
    assert "previous period" in [a for a in s._ACCESS if a["call"] == "resampled_returns"][0]["formula"]
    s = rs(resample_rules={**RULES, "close": "MAX"})
    with pytest.raises(s.ResampleError):
        s.resampled_returns(s.resample(frame, "prices"), "prices")


# ---------------------------------------------------------------------------------------- validator and contract

def weekly_spec(columns: list[str], **request) -> dict:
    fields = {"analysis_frequency": "1W", "resample": "WEEKLY", **request}
    return ytd_spec(data_requests=[prices(columns=["ticker", "date", *columns], **fields)], relationships=[])


def validate(spec: dict, derived: bool):
    return validate_with(spec, derived, None)


def validate_with(spec: dict, derived: bool, price_columns: dict | None):
    from app.data_need import Limits, validate as run

    catalog = data_need_catalog()
    if price_columns is not None:
        catalog["columns"]["Price_Stock_Indonesia_IDX"] = price_columns
    return run(spec, subset(catalog, ["Price_Stock_Indonesia_IDX"]), date(2026, 9, 25),
               Limits(derived_frequency=derived))


def test_the_validator_fails_closed_on_missing_rules_and_non_daily_sources() -> None:
    from app.data_need import data_contract_sha256

    ok = validate(weekly_spec(["open", "close", "volume"]), True)
    assert ok.status == "APPROVED" and ok.approved["requests"]["data_request_1_A"]["resample_semantics_version"] == 1
    catalog_columns = data_need_catalog()["columns"]["Price_Stock_Indonesia_IDX"]
    catalog_columns["open"]["resample_aggregation"] = None
    missing = validate_with(weekly_spec(["close", "open"]), True, catalog_columns)
    assert missing.status == "REVISION_REQUIRED" and [i["code"] for i in missing.issues] == ["RESAMPLE_RULE_MISSING"]
    assert missing.issues[0]["rejected_value"] == "open"
    assert validate_with(weekly_spec(["close", "open"]), False, catalog_columns).status == "APPROVED"  # flag off
    not_daily = validate(weekly_spec(["close"], source_frequency="1W", analysis_frequency="1M", resample="MONTHLY"),
                         True)
    assert "RESAMPLE_SOURCE_NOT_DAILY" in [i["code"] for i in not_daily.issues]
    # the semantics version is part of the data contract hash, only where it is set
    legacy = validate(weekly_spec(["open", "close", "volume"]), False).approved
    assert "resample_semantics_version" not in legacy["requests"]["data_request_1_A"]
    assert data_contract_sha256(legacy) != data_contract_sha256(ok.approved)
    monthly = validate(weekly_spec(["open", "close", "volume"], analysis_frequency="1M", resample="MONTHLY"), True)
    assert data_contract_sha256(monthly.approved) != data_contract_sha256(ok.approved)
    changed = dict(ok.approved, requests={k: {**v, "resample_rules": {**v["resample_rules"], "close": "MAX"}}
                                          for k, v in ok.approved["requests"].items()})
    assert data_contract_sha256(changed) != data_contract_sha256(ok.approved)
    bumped = dict(ok.approved, requests={k: {**v, "resample_semantics_version": 2}
                                         for k, v in ok.approved["requests"].items()})
    assert data_contract_sha256(bumped) != data_contract_sha256(ok.approved)


def test_daily_requests_are_unchanged_by_the_flag() -> None:
    from app.data_need import data_contract_sha256

    daily = ytd_spec(data_requests=[prices()], relationships=[])
    on, off = validate(daily, True), validate(daily, False)
    assert on.status == off.status == "APPROVED" and on.approved == off.approved
    assert data_contract_sha256(on.approved) == data_contract_sha256(off.approved)


def test_legacy_resample_keeps_its_shape_without_a_semantics_version(rs) -> None:
    s = rs(version=None)
    rows = [("AAAA", d, 1, 2 + i, 0, float(i), 1) for i, d in enumerate(trading_days("2026-08-31", "2026-09-11"))]
    rows += [("BBBB", "2026-09-07", 5, 5, 5, 5.0, 3)]
    out = s.resample(ohlcv(rows), "prices")
    # legacy output: entity, period label, one column per rule, observations; P13 (user decision 2026-10-01) adds the
    # same period columns as the derived semantics after them, values unchanged; still no trace
    assert list(out.columns) == ["ticker", "date", *RULES, "observations", "actual_first_date", "actual_last_date",
                                 "period_end", "period_start", "period_complete"]
    assert out[out["ticker"] == "AAAA"]["period_start"].tolist() == [date(2026, 8, 29), date(2026, 9, 5)]
    assert out[out["ticker"] == "AAAA"]["actual_first_date"].tolist() == [date(2026, 8, 31), date(2026, 9, 7)]
    aaaa = out[out["ticker"] == "AAAA"]
    assert aaaa["date"].tolist() == [date(2026, 9, 4), date(2026, 9, 11)] and aaaa["close"].tolist() == [4.0, 9.0]
    assert aaaa["high"].tolist() == [6, 11] and aaaa["volume"].tolist() == [5, 5]
    assert out[out["ticker"] == "BBBB"]["volume"].tolist() == [3]  # S09: rules no longer crossed with columns
    assert not [a for a in s._ACCESS if a.get("call") == "resample"]


def test_app_and_runtime_share_the_semantics_constants() -> None:
    sys.path.insert(0, str(RUNTIME))
    import saniti_session as runtime

    from app import data_need

    for name in ("RESAMPLE_SEMANTICS_VERSION", "NULL_POLICY", "PERIOD_POLICY", "COMPLETENESS_RULE"):
        assert getattr(runtime, name) == getattr(data_need, name), name
    assert "resampled_returns" not in runtime.__all__  # not pre-bound: the flag-off namespace is unchanged


def test_legacy_resample_groups_by_grain_columns_instead_of_asking_for_their_rule(rs) -> None:
    """P13 (e02, ma-flags-20261001a): market_board is part of the grain; it was refused as a value without a rule."""
    s = rs(version=None)
    s.REQUESTS["g_A"]["key_columns"] = ["ticker", "date", "market_board"]
    rows = [("AAAA", d, 1, 2, 0, 1.0, 1) for d in trading_days("2026-08-31", "2026-09-04")]
    frame = ohlcv(rows)
    frame = pd.concat([frame.assign(market_board="Regular"), frame.assign(market_board="Nego", volume=7)])
    out = s.resample(frame, "prices")
    assert sorted(out["market_board"]) == ["Nego", "Regular"]
    assert out.set_index("market_board")["volume"].to_dict() == {"Nego": 35, "Regular": 5}
