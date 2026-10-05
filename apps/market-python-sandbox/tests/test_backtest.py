"""P32 layer 3 (plan 2026-10-05): the trade simulation behind saniti.backtest and its backend recomputation."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import backtest as BT  # noqa: E402

from conftest import requires_root  # noqa: E402
from test_dataneed_bundles import HEADERS, env  # noqa: E402,F401 - env is a fixture
from test_dataneed_sessions import ok, run, session  # noqa: E402,F401 - session is a fixture

COLUMNS = {"open": "open", "high": "high", "low": "low", "close": "close"}
RANGE = [{"range_id": "test", "start": "2020-01-06", "end": "2020-01-17"}]


def bars(rows: list[tuple[str, float, float, float, float]], ticker: str = "BBRI") -> pd.DataFrame:
    return pd.DataFrame([{"ticker": ticker, "date": d, "open": o, "high": h, "low": lo, "close": c}
                         for d, o, h, lo, c in rows])


def flat(dates: list[str], price: float = 100.0) -> list[tuple[str, float, float, float, float]]:
    return [(d, price, price, price, price) for d in dates]


DATES = [d.date().isoformat() for d in pd.bdate_range("2020-01-01", "2020-01-17")]  # 2020-01-01..03 are buffer


def simulate(frame, signals, exits=(), **params):
    p = BT.parameters(params.get("stop"), params.get("target"), params.get("max_hold"), params.get("fee"),
                      params.get("unit", "DECIMAL"))
    return BT.simulate(frame, entity_column="ticker", time_column="date", columns=COLUMNS, ranges=RANGE,
                       signals={("BBRI", d) for d in signals}, exits={("BBRI", d) for d in exits}, params=p)


def test_entry_at_next_open_and_target_at_its_level() -> None:
    rows = flat(DATES)
    rows[5] = ("2020-01-08", 100, 100, 100, 100)                # entry bar (signal on 2020-01-07)
    rows[7] = ("2020-01-10", 101, 111, 100, 109)                # target 110 inside the bar
    trades, summary = simulate(bars(rows), ["2020-01-07"], stop=0.05, target=0.10)
    assert [(t["entry_date"], t["exit_date"], t["exit_reason"], t["exit_price"]) for t in trades] == [
        ("2020-01-08", "2020-01-10", "TARGET", pytest.approx(110.0))]
    assert trades[0]["return"] == pytest.approx(0.10)
    assert summary[0]["trades"] == 1 and summary[0]["win_rate"] == 1.0


def test_stop_first_when_both_levels_are_inside_one_bar_and_a_gap_fills_at_the_open() -> None:
    rows = flat(DATES)
    rows[6] = ("2020-01-09", 100, 120, 90, 100)                 # both 95 and 110 inside: stop first
    trades, _ = simulate(bars(rows), ["2020-01-07"], stop=0.05, target=0.10)
    assert trades[0]["exit_reason"] == "STOP" and trades[0]["exit_price"] == pytest.approx(95.0)
    gap = flat(DATES)
    gap[6] = ("2020-01-09", 90, 92, 88, 91)                     # opens below the stop: filled at the open
    trades, _ = simulate(bars(gap), ["2020-01-07"], stop=0.05)
    assert trades[0]["exit_price"] == pytest.approx(90.0) and trades[0]["return"] == pytest.approx(-0.10)


def test_buffer_bars_never_trade_and_are_counted_apart() -> None:
    trades, summary = simulate(bars(flat(DATES)), ["2020-01-02"])     # a signal in the warm-up buffer
    assert trades == [] and summary[0]["signals"] == 0
    assert summary[0]["bars_in_period"] == 10 and summary[0]["bars_buffer"] == 3


def test_exit_signal_max_hold_open_at_end_and_skipped_signals() -> None:
    trades, summary = simulate(bars(flat(DATES)), ["2020-01-06", "2020-01-08"], exits=["2020-01-09"])
    assert [(t["entry_date"], t["exit_date"], t["exit_reason"]) for t in trades] == [
        ("2020-01-07", "2020-01-10", "EXIT_SIGNAL")]
    assert summary[0]["signals"] == 2 and summary[0]["signals_skipped"] == 1
    trades, _ = simulate(bars(flat(DATES)), ["2020-01-06"], max_hold=3)
    assert trades[0]["exit_date"] == "2020-01-09" and trades[0]["exit_reason"] == "MAX_HOLD"
    trades, _ = simulate(bars(flat(DATES)), ["2020-01-15"])
    assert trades[0]["exit_reason"] == "OPEN_AT_END" and trades[0]["exit_date"] == "2020-01-17"
    trades, summary = simulate(bars(flat(DATES)), ["2020-01-17"])     # no next bar inside the range
    assert trades == [] and summary[0]["signals_skipped"] == 1


def test_fee_percent_unit_and_summary_statistics() -> None:
    rows = flat(DATES)
    rows[7] = ("2020-01-10", 100, 111, 100, 109)
    rows[10] = ("2020-01-15", 100, 100, 94, 95)
    trades, summary = simulate(bars(rows), ["2020-01-06", "2020-01-13"], stop=0.05, target=0.10, fee=0.001,
                          unit="PERCENT")
    win = 110 * 0.999 / (100 * 1.001) - 1
    loss = 95 * 0.999 / (100 * 1.001) - 1
    assert [t["return"] for t in trades] == [pytest.approx(win * 100), pytest.approx(loss * 100)]
    s = summary[0]
    assert s["wins"] == 1 and s["win_rate"] == 0.5
    assert s["profit_factor"] == pytest.approx(win / abs(loss))
    assert s["realized_reward_risk"] == pytest.approx(win / abs(loss))
    assert s["cumulative_return"] == pytest.approx(((1 + win) * (1 + loss) - 1) * 100)
    assert s["max_drawdown"] == pytest.approx(loss * 100)
    assert BT.summary_units("PERCENT")["mean_return"] == "PERCENT"


def test_several_entities_get_an_all_row_without_compounding() -> None:
    frame = pd.concat([bars(flat(DATES)), bars(flat(DATES), "BMRI")])
    p = BT.parameters(None, None, 2, None, "DECIMAL")
    trades, summary = BT.simulate(frame, entity_column="ticker", time_column="date", columns=COLUMNS, ranges=RANGE,
                                  signals={("BBRI", "2020-01-06"), ("BMRI", "2020-01-08")}, exits=set(), params=p)
    assert [s["entity"] for s in summary] == ["BBRI", "BMRI", "ALL"]
    assert summary[-1]["trades"] == 2 and summary[-1]["cumulative_return"] is None


def test_compare_names_the_differing_cells() -> None:
    trades, summary = simulate(bars(flat(DATES)), ["2020-01-15"])
    assert BT.compare(summary, summary, "entity", BT.SUMMARY_COLUMNS) == []
    changed = [{**summary[0], "trades": 2}]
    assert BT.compare(changed, summary, "entity", BT.SUMMARY_COLUMNS)[0]["column"] == "trades"


def test_parameters_are_checked() -> None:
    with pytest.raises(BT.BacktestError, match="fraction"):
        BT.parameters(5, None, None, None, None)
    with pytest.raises(BT.BacktestError, match="max_hold"):
        BT.parameters(None, None, 0, None, None)


# ------------------------------------------------------------------------------------------ in a session


def complete(env) -> dict:  # noqa: F811
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                               headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


TEST = ("full = load('prices')\n"
        "full = full.sort_values(['ticker', 'date'])\n"
        "full['drop'] = full.groupby('ticker')['close'].pct_change() <= -0.01\n"
        "bt = backtest('prices', full, 'drop', stop=0.05, target=0.03, name='dips')\n"
        "banks = load('stock_classification')\n")  # every request of the bundle is read (coverage)


@requires_root
def test_a_backtest_is_rerun_by_the_backend_on_the_bundle_prices(session) -> None:
    body = ok(session, TEST + "print(bt['summary'][-1]['trades'], bt['summary'][-1]['bars_buffer'])")
    names = [o["name"] for o in body["outputs"]]
    assert names[:3] == ["dips_trades", "dips_summary", "backtest_call_dips"]
    trades, buffer = (int(x) for x in body["stdout"].split())
    assert trades > 0 and buffer > 0  # warm-up rows were delivered and did not trade
    result = complete(session)
    assert result["status"] == "COMPLETED", result
    check = result["final_status"]["backtests"][0]
    assert check["status"] == "PASS" and check["mismatched"] == 0 and check["checked"] > 0
    assert {check["trades_output_id"], check["summary_output_id"]} <= set(result["final_status"]["verified_output_ids"])
    assert result["final_status"]["calculation_validation"] in ("PARTIAL", "FORMULA_AND_STATISTICS_VERIFIED")


@requires_root
def test_a_changed_backtest_table_fails_completion(session) -> None:
    ok(session, TEST + "fake = pd.DataFrame(bt['summary'])\nfake['trades'] = fake['trades'] + 1\n"
                       "emit_table('dips_summary', fake, definition={})")
    result = complete(session)
    assert result["status"] == "INCOMPLETE"
    check = result["final_status"]["backtests"][0]
    assert check["status"] == "FAIL" and check["reason"] == "CALCULATION_MISMATCH"
    refused = run(session, "emit_json('backtest_call_x', {'a': 1})").json()
    assert refused["status"] != "OK"
