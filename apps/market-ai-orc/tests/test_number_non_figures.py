"""P28 D (final golden test 2026-10-04): a confidence or significance level, a number naming an object and the first day
of a day range are not data figures; the provenance gate refused "95%", "relasi 17" and "24–31 Agustus" although the
answers were right. Other wordings of the same classes are covered, and figures next to them are still read."""
from __future__ import annotations

import pytest

from app.provenance import parse_numbers


def shown(text: str) -> list[str]:
    return [n.text for n in parse_numbers(text)]


@pytest.mark.parametrize("text", [
    "95% CI", "interval kepercayaan 99%", "selang kepercayaan 90%", "confidence level 95%", "CI 95%",
    "α = 0,05", "taraf nyata 5%", "significance level 0.01",
    "relasi 17", "relationship #24", "versi 4", "ID 3",
    "24–31 Agustus", "1 s.d. 5 Mei", "3 sampai 7 Oktober", "10-14 Aug",
])
def test_a_non_figure_is_not_read(text: str) -> None:
    assert shown(text) == []


@pytest.mark.parametrize("text, figures", [
    ("rata-rata 0,19% (95% CI 0,1–0,3)", ["0,19%", "0,1", "0,3"]),  # the interval's bounds stay figures
    ("naik 95% dalam setahun", ["95%"]),  # a percentage that is no confidence level
    ("24 saham bank, 7 naik", ["24", "7"]),
    ("kode 1.234 saham", ["1.234"]),  # a thousands figure after the word is no identifier
    ("RB beli bersih 116 dari 132 hari pada 24–31 Agustus", ["116", "132"]),
])
def test_figures_beside_them_are_still_read(text: str, figures: list[str]) -> None:
    assert shown(text) == figures
