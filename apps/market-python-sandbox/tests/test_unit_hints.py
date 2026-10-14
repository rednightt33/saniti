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
