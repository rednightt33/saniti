"""M143 (EXEC-M143 (a), user decision 2026-10-13 "(a) + (c)"): a scale word typed right after a reference to a number
shown without a unit is part of that figure; its value times the scale is a source of that reference only, so a
reference's own value is never refused by the PROVENANCE gate. A figure typed without a reference is still refused."""
from __future__ import annotations

from app.provenance import CONTEXT, SourceIndex, check_answer
from app.value_refs import ReferenceSources, render

ROW = {"ticker": "BBRI", "median_volume_juta": 349.1, "total_net_asing_miliar": 1975.4, "net": 1975400000000.0}


def sources() -> ReferenceSources:
    refs = ReferenceSources()
    refs.add("out", "out_a", {"rows": [dict(ROW), {**ROW, "ticker": "BBCA"}]}, "CALCULATION_VERIFIED")
    refs.alias("out", "o1", "out_a")
    return refs


def checked(text: str):
    rendering = render(text, sources())
    index = SourceIndex()
    index.add("CALCULATION_VERIFIED", [v.value for v in rendering.values])
    index.add(CONTEXT, [])
    return rendering, check_answer(rendering.text, index)


def test_the_run_b_figures_with_a_scale_word_are_their_own_source() -> None:
    rendering, result = checked(
        "Median volume {{out.o1.rows[ticker=BBRI].median_volume_juta|dec:0}} juta saham; net asing "
        "Rp {{out.o1.rows[ticker=BBRI].total_net_asing_miliar|dec:1}} miliar dan "
        "Rp{{out.o1.rows[ticker=BBRI].total_net_asing_miliar|dec:1}} miliar.")
    assert rendering.text == "Median volume 349 juta saham; net asing Rp 1.975,4 miliar dan Rp1.975,4 miliar."
    assert len(rendering.scaled) == 3
    assert not result.unsupported, result.unsupported


def test_rp_is_unchanged_and_adds_no_scaled_value() -> None:
    rendering, result = checked("Net {{out.o1.rows[ticker=BBRI].net|rp}}.")
    assert rendering.text == "Net Rp 1,98 triliun." and rendering.scaled == [] and not result.unsupported


def test_a_typed_scaled_figure_is_still_refused() -> None:
    _, result = checked("Net {{out.o1.rows[ticker=BBRI].total_net_asing_miliar|dec:1}} dan Rp 2.500 miliar.")
    assert any("2.500" in n for n in result.unsupported)


def test_a_scale_word_not_next_to_the_reference_adds_nothing() -> None:
    rendering, result = checked("Volume {{out.o1.rows[ticker=BBRI].median_volume_juta|dec:0}} saham, sekitar juta.")
    assert rendering.scaled == []
