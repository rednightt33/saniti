"""M119 (user decisions 2026-10-08 "M119 solusi A dan B - ensure AI aware of this", "1.000 tabel turunan ... OK";
go 2026-10-09 "lanjut fase 4"): GT1 BBRI turn 1 typed the ids of tables its own session had just emitted and
load_output refused them as "not a carried table ... (a research plan's session ...)" in an analysis session (8 such
refusals in 170 runs). Now a session reads its own tables by output_id or name from its next execution, keeps working
tables by name within a disk quota (never released, never outputs), and a helper's result names every table it
emitted; the research suffix appears only in a research session."""
from __future__ import annotations

from conftest import requires_root
from test_dataneed_bundles import env  # noqa: F401 - fixture
from test_dataneed_sessions import ok, run, session  # noqa: F401 - fixtures

pytestmark = requires_root


def test_a_session_loads_its_own_tables_by_id_or_name_from_its_next_execution(session) -> None:  # noqa: F811
    first = ok(session, "t = load('prices').groupby('ticker', as_index=False)['close'].last()\n"
                        "emit_table('last_close', t, definition={})")
    [output] = [o for o in first["outputs"] if o["name"] == "last_close"]
    body = ok(session, f"a = load_output({output['output_id']!r})\nb = load_output('last_close')\n"
                       "print(len(a), len(b), a.attrs['label'], [e.get('own') for e in carried()])")
    rows, rows_by_name, label, own = body["stdout"].split(maxsplit=3)
    assert rows == rows_by_name == str(output["row_count"]) and label == "NOT_RELEASED" and "True" in own
    missing = run(session, "load_output('out_' + '0' * 24)").json()
    assert missing["status"] == "SCRIPT_ERROR" and "save_table" in str(missing)
    assert "research plan" not in str(missing)  # an analysis session gets no research suffix


def test_working_tables_are_kept_by_name_within_a_quota_and_never_become_outputs(session) -> None:  # noqa: F811
    saved = ok(session, "full = load('prices')\nprint(save_table('all_prices', full)['label'])")
    assert saved["stdout"].strip() == "NOT_RELEASED" and saved["outputs"] == []
    again = ok(session, "t = load_table('all_prices', columns=['ticker', 'close'])\n"
                        "print(len(t), t.attrs['label'], [s['name'] for s in saved_tables()])")
    count, label, names = again["stdout"].split(maxsplit=2)
    assert int(count) > 0 and label == "NOT_RELEASED" and "all_prices" in names
    assert ok(session, "print(drop_table('all_prices'), saved_tables())")["stdout"].strip() == "True []"
    unknown = run(session, "load_table('nope')").json()
    assert unknown["status"] == "SCRIPT_ERROR" and "save_table" in str(unknown)
    # the quota: a table above it is refused and nothing is written
    refused = run(session, "import numpy as np\nbig = pd.DataFrame({'x': np.random.rand(3_000_000)})\n"
                           "saniti._LIMITS['working_table_bytes'] = 1000\nsave_table('big', big)").json()
    assert refused["status"] == "SCRIPT_ERROR" and "drop_table" in str(refused)
    assert ok(session, "print(saved_tables())")["stdout"].strip() == "[]"
    assert session["opened"]["limits"]["working_table_bytes"] > 0


def test_event_study_returns_every_table_it_emitted_by_name(session) -> None:  # noqa: F811
    body = ok(session, "s = event_study('prices', 'close / lag(close, 1) - 1 <= -0.02', {'forward_return': 'close'}, "
                       "2, name='dips')\nload('stock_classification')\n"
                       "print(sorted(s['tables'].values()), list(s['flow'].columns)[:2])")
    assert "'dips_flow'" in body["stdout"] and "'dips'" in body["stdout"]
    later = ok(session, "print(len(load_output('dips_flow')))")
    assert int(later["stdout"].strip()) >= 1
