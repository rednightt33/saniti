"""EXEC-TABLE (user decision 2026-10-13): a table instruction in the answer becomes a Markdown table of code-written
value references, rendered and checked like any other reference; behind AI_ENABLE_TABLE_DIRECTIVES (default false)."""
from __future__ import annotations

import pytest

from app import table_directives as td
from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import ToolOutcome
from app.tools.references import check
from app.value_refs import UNRESOLVED, ReferenceSources, render
from conftest import ScriptedClient, make_settings
from test_multi_angle import Clock, RunSandbox, ma_registry
from test_value_references import REFS

SECTORS = [{"sector": "Energy", "median_pct": 4.26, "n": 12, "share": 0.30},
           {"sector": "Finance", "median_pct": 1.5, "n": 20, "share": 0.50},
           {"sector": "Tech", "median_pct": None, "n": 3, "share": 0.075},
           {"sector": "Basic | Ind", "median_pct": 7.0, "n": 5, "share": 0.125}]


def released(state: RunState, orc: AgentOrchestrator, rows: list[dict], units: dict | None = None,
             row_count: int | None = None) -> None:
    content = {"output_id": "out_sector", "name": "sector_median", "type": "TABLE", "rows": [dict(r) for r in rows],
               "row_count": row_count or len(rows)}
    if units:
        content["units"] = units
    orc._track_references(state, "complete_analysis", ToolOutcome(
        call_id="c", name="complete_analysis", ok=True,
        output={"result": {"status": "COMPLETED", "session_id": "sess_1", "released_contents": [content]}}))


def tracked(rows=SECTORS, units=None, row_count=None, reader=None) -> tuple[AgentOrchestrator, RunState]:
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    orc.row_reader = reader
    state = RunState(request_id="r", started=0.0, input_items=[])
    released(state, orc, rows, units or {"median_pct": "PERCENT", "share": "FRACTION"}, row_count)
    return orc, state


def shown(text: str, state: RunState) -> tuple[td.Expansion, str]:
    expansion = td.expand(text, state.ref_sources, marks=False)
    return expansion, render(expansion.text, state.ref_sources).text


def test_an_instruction_becomes_a_sorted_table_of_formatted_values() -> None:
    _, state = tracked()
    expansion, text = shown("Median per sektor:\n{{table out.o1; Sektor = sector; Median = median_pct|pctv:1; "
                            "sort -median_pct; top 3}}\nSelesai.", state)
    assert expansion.problems == [] and expansion.refs == ["out.o1"]
    lines = text.splitlines()
    assert lines[0] == "Median per sektor:" and lines[2] == "| Sektor | Median |" and lines[3] == "|---|---|"
    assert lines[4:7] == ["| Basic / Ind | 7,0% |", "| Energy | 4,3% |", "| Finance | 1,5% |"]
    assert "_Menampilkan 3 dari 4 baris._" in text and text.endswith("Selesai.")


def test_cells_are_references_by_position_so_every_figure_is_a_source() -> None:
    _, state = tracked()
    expansion = td.expand("{{table out.o1; Sektor = sector; Saham = n|int}}", state.ref_sources)
    assert "{{out.o1.rows[_row=0].n\\|int}}" in expansion.text  # code-written, escaped for a Markdown table
    rendering = render(expansion.text, state.ref_sources)
    assert rendering.problems == [] and {v.value for v in rendering.values} >= {12.0, 20.0, 3.0, 5.0}


def test_units_decide_the_display_and_a_joined_cell_holds_two_columns() -> None:
    _, state = tracked()
    _, text = shown("{{table out.o1; Sektor = sector; Saham (porsi) = {n|int} ({share|pct:1}); "
                    "Median = median_pct|pp:2; sort sector}}", state)
    assert "| Energy | 12 (30,0%) | 4,26 pp |" in text
    assert "| Tech | 3 (7,5%) | – |" in text  # a missing value is a dash, not a reference
    assert "Menampilkan" not in text  # nothing was cut


def test_the_line_under_a_cut_table_waits_for_the_gates() -> None:
    _, state = tracked()
    expansion = td.expand("{{table out.o1; Sektor = sector; top 2}}", state.ref_sources)
    assert "Menampilkan" not in expansion.text and "[[tabel-baris-a]]" in expansion.text
    assert not any(ch.isdigit() for ch in "[[tabel-baris-a]]")
    assert td.put_footers(expansion.text, expansion.footers).endswith("_Menampilkan 2 dari 4 baris._")


@pytest.mark.parametrize("instruction,needle", [
    ("{{table out.o7; Sektor = sector}}", "no released table has this ref; the released tables are out.o1"),
    ("{{table out.o1; Sektor = sektor}}", "column sektor does not exist; its columns are sector, median_pct"),
    ("{{table out.o1; Sektor = sector|pct}}", "format pct does not fit column sector (a text column"),
    ("{{table out.o1; Sektor = sector; Median = median_pct|pcx}}", "unknown format"),
    ("{{table out.o1; Sektor = sector; sort -median}}", "sort column median does not exist"),
    ("{{table out.o1 Sektor = sector}}", "Table instruction cannot be read"),
    ("{{table out.o1; Sektor}}", "is neither Title = column, sort nor top"),
])
def test_a_wrong_instruction_is_refused_with_what_exists(instruction, needle) -> None:
    _, state = tracked()
    expansion = td.expand("Lihat:\n" + instruction, state.ref_sources)
    assert expansion.text.endswith(UNRESOLVED) and len(expansion.failed) == 1
    assert needle in expansion.problems[0] and expansion.problems[0].endswith(td.FIX_ONLY)


def test_a_p_value_column_takes_only_p() -> None:
    _, state = tracked(rows=[{"t": "A", "p": 0.0004}, {"t": "B", "p": 0.2}], units={"p": "P_VALUE"})
    refused = td.expand("{{table out.o1; T = t; P = p|pct}}", state.ref_sources)
    assert "a p-value cannot be shown" in refused.problems[0]
    _, text = shown("{{table out.o1; T = t; P = p|p}}", state)
    assert "| A | p < 0,001 |" in text and "| B | p = 0,20 |" in text


def test_rows_beyond_the_first_page_are_read_from_the_released_table() -> None:
    table = [{"ticker": f"T{i:03d}", "ret": float(i)} for i in range(450)]

    def read(session_id, output_id, request_id, offset, limit):
        return {"released": True, "rows": [dict(r) for r in table[offset:offset + limit]], "row_count": len(table)}

    _, state = tracked(rows=table[:200], units={}, row_count=450, reader=read)
    _, text = shown("{{table out.o1; Saham = ticker; Return = ret|dec:0; sort -ret; top 2}}", state)
    assert "| T449 | 449 |" in text and "| T448 | 448 |" in text
    assert "_Menampilkan 2 dari 450 baris._" in text


def test_a_table_given_as_a_list_is_read_by_index() -> None:
    refs = ReferenceSources()
    refs.add("out", "out_x", {"rows": [{"v": 2.0}, {"v": 1.0}]}, "CALCULATION_VERIFIED")
    refs.alias("out", "o1", "out_x")
    expansion = td.expand("{{table out.o1; Nilai = v|dec:1; sort v}}", refs, marks=False)
    assert "rows.1.v" in expansion.text
    assert render(expansion.text, refs).text.splitlines()[2:] == ["| 1,0 |", "| 2,0 |"]


def test_the_model_written_tables_are_counted() -> None:
    assert td.typed_tables("| a | b |\n|---|---|\n| 1 | 2 |\n\n| c |\n| :--- |\n| 3 |") == 2


def test_check_references_previews_a_table_only_with_the_flag() -> None:
    _, state = tracked()
    token = td.current_table_directives.set(True)
    try:
        result = check(["table out.o1; Sektor = sector; Saham = n|int; top 1"], state.ref_sources)
        assert result["results"][0]["ok"] and "| Energy | 12 |" in result["results"][0]["shows"]
        assert "_Menampilkan 1 dari 4 baris._" in result["results"][0]["shows"]
        refused = check(["{{table out.o1; Sektor = sektor}}"], state.ref_sources)
        assert not refused["results"][0]["ok"] and "column sektor does not exist" in refused["results"][0]["error"]
    finally:
        td.current_table_directives.reset(token)
    assert not check(["table out.o1; Sektor = sector"], state.ref_sources)["results"][0]["ok"]


# ---------------------------------------------------------------- the orchestrator and the wayback

def orchestrator(on: bool) -> AgentOrchestrator:
    flags = {**REFS, **({"AI_ENABLE_TABLE_DIRECTIVES": "true"} if on else {})}
    return AgentOrchestrator(make_settings(**flags), ScriptedClient([]), ma_registry(RunSandbox()),
                             wall_clock=Clock(), draft_reader=lambda draft_id: None)


def test_with_the_flag_off_the_prompt_is_the_one_before_exec_table() -> None:
    off, on = orchestrator(False), orchestrator(True)
    assert "## TABLES" not in off.system_prompt and "{{table out.o2;" not in off.system_prompt
    assert "## TABLES" in on.system_prompt and "{{table out.o2;" in on.system_prompt
    start = on.system_prompt.index("\n\n## TABLES")
    end = on.system_prompt.find("\n\n## ", start + 2)
    section = on.system_prompt[start:end if end != -1 else None]
    assert on.system_prompt.replace(section, "") == off.system_prompt  # the only difference is the TABLES section
    assert not off.table_directives and on.table_directives


def answer(text: str) -> FinalResponse:
    return FinalResponse(response_type="ANSWER", answer=text, assumptions=[], limitations=[])


def test_the_answer_shows_the_table_cites_it_once_and_types_no_figure() -> None:
    orc = orchestrator(True)
    state = RunState(request_id="r", started=0.0, input_items=[])
    released(state, orc, SECTORS, {"median_pct": "PERCENT", "share": "FRACTION"})
    final, forced = orc._resolve_references(state, answer(
        "Energi memimpin.\n\n{{table out.o1; Sektor = sector; Median = median_pct|pctv:1; sort -median_pct; "
        "top 2}}"))
    assert not forced and "| Basic / Ind | 7,0% |\n| Energy | 4,3% |" in final.answer
    assert state.referenced == ["out.o1"]  # evidence names the table, not each cell
    assert "7,0" not in (state.typed_answer or "") and "4,3" not in (state.typed_answer or "")
    assert "{{table" in state.raw_final["answer"]  # the model's own draft is kept for an edit
    done = orc._finalize_findings(state, final)
    assert done.answer.endswith("_Menampilkan 2 dari 4 baris._") and "[[tabel-baris-" not in done.answer


def test_a_wrong_instruction_goes_to_the_reference_repair() -> None:
    from app.orchestrator import GateRejection

    orc = orchestrator(True)
    state = RunState(request_id="r", started=0.0, input_items=[])
    released(state, orc, SECTORS)
    with pytest.raises(GateRejection) as refused:
        orc._resolve_references(state, answer("{{table out.o1; Sektor = sektor}}"))
    assert "column sektor does not exist" in str(refused.value) and td.FIX_ONLY.strip() in str(refused.value)


def test_with_the_flag_off_an_instruction_is_not_built() -> None:
    orc = orchestrator(False)
    state = RunState(request_id="r", started=0.0, input_items=[])
    released(state, orc, SECTORS)
    from app.orchestrator import GateRejection

    with pytest.raises(GateRejection):  # as before EXEC-TABLE: an unreadable reference
        orc._resolve_references(state, answer("{{out.o1.rows[sector=Energy].n|int}} {{table out.o1; S = sector}}"))
