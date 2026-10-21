"""EXEC-RULES-1021 #6 (user 2026-10-21, go "Masukan exec dan eksekusi"; edge_b524513e: y = in_period(load('yields'),
'yields') then y.pivot_table failed with a bare AttributeError): a script error from using the in_period mask as a
table names the mask and the fix (AGENTS.md Gates and evidence (d)); other script errors get no such hint."""
from __future__ import annotations

from app.sessions import HELPERS, IN_PERIOD_HINT
from conftest import requires_root
from test_dataneed_bundles import env  # noqa: F401 - fixture
from test_dataneed_sessions import run, session  # noqa: F401 - fixture

pytestmark = requires_root


def test_the_mask_used_as_a_table_names_the_fix(session) -> None:
    body = run(session, "p = in_period(load('prices'), 'prices')\np.pivot_table(index='date')").json()
    assert body["status"] == "SCRIPT_ERROR" and body["helper_hint"] == IN_PERIOD_HINT, body
    assert "y = y[in_period(y, 'yields')]" in body["helper_hint"]


def test_the_right_use_and_other_errors_get_no_hint(session) -> None:
    ok = run(session, "p = load('prices')\np = p[in_period(p, 'prices')]\nn = len(p)").json()
    assert ok["status"] == "OK" and "helper_hint" not in ok, ok
    other = run(session, "p = load('prices')\np['no_such_column'].sum()").json()
    assert other["status"] == "SCRIPT_ERROR" and "helper_hint" not in other


def test_the_helper_list_says_mask_not_table() -> None:
    entry = next(h for h in HELPERS if h.startswith("in_period("))
    assert "not a table" in entry and "frame[in_period(frame, request)]" in entry
