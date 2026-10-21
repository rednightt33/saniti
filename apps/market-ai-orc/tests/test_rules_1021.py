"""EXEC-RULES-1021 (user 2026-10-21, go "Masukan exec dan eksekusi"; edge_b524513e): #6 in_period is a row mask, not a
table, and #7 emit_json declares units like emit_table. The rule is where the model reads it before it writes (the
run_python description, the data-need steps, CITING AND CHECKS), with one right and one wrong example (AGENTS.md Gates
and evidence a-c); the sandbox's script-error hint is (d)."""
from __future__ import annotations

from app.orchestrator import CITING_CHECKS_RULES, build_system_prompt
from app.tools.session import RUN_DESCRIPTION


def test_the_run_python_description_says_mask_with_a_right_and_a_wrong_example() -> None:
    assert "a mask (True/False per row), not a table" in RUN_DESCRIPTION
    assert "right y = load('yields'); y = y[in_period(y, 'yields')]" in RUN_DESCRIPTION
    assert "wrong y = in_period(load('yields'), 'yields')" in RUN_DESCRIPTION


def test_the_run_python_description_says_emit_json_declares_units() -> None:
    assert "every column (emit_json: every field)" in RUN_DESCRIPTION
    assert "units={'median_gap_pct': 'PERCENT'}" in RUN_DESCRIPTION and "without units and then cited" in RUN_DESCRIPTION


def test_citing_and_checks_names_emit_json_with_a_right_and_a_wrong_example() -> None:
    rule = next(line for line in CITING_CHECKS_RULES.splitlines() if line.startswith("3. A share"))
    assert "field (emit_json)" in rule and "Right:" in rule and "Wrong:" in rule
    assert not any(ch.isdigit() for ch in rule.split("Right:")[1].split("`{{")[0])  # no figure becomes a prompt source


def test_the_prompts_no_longer_list_in_period_as_a_data_reader() -> None:
    for fast in (False, True):
        prompt = build_system_prompt(True, dataneed=True, value_references=True, goal_answers=fast)
        assert "load_range,\nin_period, sql" not in prompt and "in_period, sql, join" not in prompt
        assert "frame[in_period(frame, request)]" in prompt
        assert "released with units= in emit_table or emit_json" in prompt
