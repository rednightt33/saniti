"""EXEC-FASTLANE Mode Jawab v2 (5B): emit_table gives the standard helper columns their unit and warns about a numeric
column named like a share, rate, percent, ratio or return without a declared unit (ma-explore-20261014-on i1 showed
"-0,107" for -10.7%). Nothing is refused: the warning reaches the model in the run_python result."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

import saniti_session as S  # noqa: E402

from conftest import requires_root  # noqa: E402
from test_explore_tests import open_session, run  # noqa: E402


@pytest.mark.parametrize("column, expected", [
    ("net_asing_pct_transaksi", True), ("porsi_5_hari_masuk_terbesar", True), ("return_periode_pct", True),
    ("win_rate", True), ("share_of_total_move", True), ("mean_return", True),
    ("jumlah_hari", False), ("return_count", False), ("close", False), ("net_asing_total", False),
    ("effective_event_dates", False), ("n_return", False)])
def test_unit_like_names(column, expected) -> None:
    assert S._unit_like(column) is expected


@pytest.fixture
def plain(make_service, governor):
    env = open_session(make_service, governor)
    yield env
    env["dataneed"].sessions.stop()


CODE = """
import pandas as pd
load('prices'); load('stock_classification')
frame = pd.DataFrame({'ticker': ['BBRI'], 'net_asing_pct_transaksi': [-0.107], 'jumlah_hari': [91],
                      'return_pct': [-6.07], 'return_decimal': [-0.0607]})
"""


@requires_root
def test_standard_columns_get_their_unit_and_a_share_without_one_is_warned(plain) -> None:
    body = run(plain, CODE + "emit_table('konteks', frame, definition={})")
    assert body["status"] == "OK", body
    table = next(o for o in body["outputs"] if o["name"] == "konteks")
    assert table["units"] == {"return_pct": "PERCENT", "return_decimal": "FRACTION"}
    warned = [w for w in body["warnings"] if w["code"] == "UNIT_UNDECLARED"]
    assert len(warned) == 1 and "net_asing_pct_transaksi" in warned[0]["message"]
    assert "jumlah_hari" not in warned[0]["message"]


@requires_root
def test_declared_units_and_helper_tables_are_not_warned(plain) -> None:
    body = run(plain, CODE + "emit_table('ok', frame, units={'net_asing_pct_transaksi': 'FRACTION'}, definition={})\n"
                             "study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', "
                             "{'forward_return': 'close'}, 3, name='dips', min_events=1)\n"
                             "ytd = period_return('prices', 'current_ytd')\nemit_table('ytd', ytd, definition={})")
    assert body["status"] == "OK", body
    assert not [w for w in body["warnings"] if w["code"] == "UNIT_UNDECLARED"], body["warnings"]
    ytd = next(o for o in body["outputs"] if o["name"] == "ytd")
    assert ytd["units"] == {"return_pct": "PERCENT", "return_decimal": "FRACTION"}


# M167 (go 2026-10-15, EXEC-IMPL-1016 Fase 1): a decimal column is warned by its values too, at release, with only the
# repairs the answer's UNITS check accepts (edge_b90899…: range_before 0.034 released without a unit)
@pytest.mark.parametrize("values, warned", [
    ([0.034, -0.012, None], True), ([0.5, 1.2], True),
    ([2.7, 0.4], False), ([1.0, 0.0, 1.0], False), ([float("nan"), None], False), ([1500.0, 1510.5], False)])
def test_a_decimal_column_is_judged_by_its_values(values, warned) -> None:
    import pyarrow as pa

    S._WARNINGS.clear()
    S._unit_hints("t", pa.table({"range_before": pa.array(values, pa.float64())}), {})
    assert bool([w for w in S._WARNINGS if w["code"] == "UNIT_UNDECLARED"]) is warned
    S._WARNINGS.clear()
    S._unit_hints("t", pa.table({"range_before": pa.array(values, pa.float64())}), {"range_before": "FRACTION"})
    assert not S._WARNINGS


def test_the_warning_offers_only_repairs_the_answer_accepts_and_is_never_cut() -> None:
    import pyarrow as pa

    S._WARNINGS.clear()
    columns = {f"a_rather_long_column_name_{i}": [0.03, 0.05] for i in range(12)}
    S._unit_hints("n" * 64, pa.table(columns), {})
    message = S._WARNINGS[-1]["message"]
    assert len(message) <= S.WARNING_CHARS and message.endswith("is refused in the answer.")
    assert "units={'a_rather_long_column_name_0': 'FRACTION'}" in message and "|dec or |x" in message
    assert "|pct if" not in message  # a percent format is not offered as a repair
    S._WARNINGS.clear()


def test_a_json_number_is_judged_like_a_column() -> None:
    S._WARNINGS.clear()
    S._warn_units("JSON 'j'", [], {"spread": [0.021]})
    assert "spread (0.021)" in S._WARNINGS[-1]["message"]
    S._WARNINGS.clear()


@requires_root
def test_emit_json_warns_about_an_undeclared_decimal_field(plain) -> None:
    body = run(plain, "emit_json('ringkas', {'spread': 0.021, 'hari': 12, 'harga': 1510.5}, definition={})\n"
                      "emit_json('ok', {'spread': 0.021}, units={'spread': 'FRACTION'}, definition={})")
    assert body["status"] == "OK", body
    warned = [w["message"] for w in body["warnings"] if w["code"] == "UNIT_UNDECLARED"]
    assert len(warned) == 1 and "JSON 'ringkas'" in warned[0] and "hari" not in warned[0]
