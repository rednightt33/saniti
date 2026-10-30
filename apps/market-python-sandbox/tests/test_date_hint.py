"""EXEC-C3 (go 2026-10-29): a datetime idiom that fails on the session's date columns (datetime.date, object dtype)
names those columns and the fix; other script errors get no date hint. The patterns are checked against the messages
the installed pandas raises, so a pandas upgrade that rewords them fails here instead of silently losing the hint."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from app.sessions import DATE_DTYPE_ERROR, DATE_DTYPE_HINT
from conftest import requires_root
from test_dataneed_bundles import env  # noqa: F401 - fixture
from test_dataneed_sessions import run, session  # noqa: F401 - fixture

DATES = pd.DataFrame({"t": ["A", "B"], "d": [dt.date(2026, 10, 1), dt.date(2026, 10, 2)]})
TIMES = DATES.assign(d=pd.to_datetime(DATES["d"]))
IDIOMS = {
    "merge_asof on date objects": lambda: pd.merge_asof(DATES, DATES, on="d", by="t"),
    "merge of object and datetime64": lambda: DATES.merge(TIMES, on=["t", "d"]),
    ".dt on date objects": lambda: DATES["d"].dt.year,
    ".resample on a date-object index": lambda: DATES.set_index("d").resample("W").size(),
}


@pytest.mark.parametrize("idiom", list(IDIOMS))
def test_every_pandas_date_idiom_error_is_recognised(idiom: str) -> None:
    with pytest.raises(Exception) as failed:
        IDIOMS[idiom]()
    assert DATE_DTYPE_ERROR.search(str(failed.value)), str(failed.value)


def test_other_errors_are_not_date_errors() -> None:
    assert not DATE_DTYPE_ERROR.search("KeyError: 'close'")
    assert not DATE_DTYPE_ERROR.search("unsupported operand type(s) for +: 'int' and 'str'")


@requires_root
@pytest.mark.parametrize("code", [
    "p = load('prices')\np['date'].dt.year",
    "import pandas as pd\np = load('prices').sort_values('date')\npd.merge_asof(p, p, on='date')",
])
def test_a_failed_date_idiom_names_the_sessions_date_columns(session, code: str) -> None:  # noqa: F811
    body = run(session, code).json()
    assert body["status"] == "SCRIPT_ERROR" and "date_hint" in body, body
    assert body["date_hint"].startswith(DATE_DTYPE_HINT.split("({columns})")[0]) and "prices.date" in body["date_hint"]
    assert "pd.to_datetime(frame[col])" in body["date_hint"]


@requires_root
def test_another_script_error_gets_no_date_hint(session) -> None:  # noqa: F811
    body = run(session, "p = load('prices')\np['no_such_column'].sum()").json()
    assert body["status"] == "SCRIPT_ERROR" and "date_hint" not in body
