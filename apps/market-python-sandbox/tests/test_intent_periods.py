"""Regressions found by the live PoC on 2026-09-24: day-level date ranges and distributive universe words in the
user's own message, and an actionable warm-up remedy for thinly traded tickers."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.intent import extract
from conftest import price_frame, zscore_spec
from test_gate_units import REF, Job, reviewed

POC2 = ("Hitung rata-rata 10 hari dari rasio upper shadow, yaitu (high - max(open, close)) / (high - low), untuk BBCA "
        "dan BBRI dari 1 Juli sampai 31 Agustus 2026. Tampilkan nilai terakhir tiap saham.")
POC3 = ("Secara historis, apakah saham IDX yang turun lebih dari 7% dalam sehari cenderung naik dalam 5 hari "
        "perdagangan berikutnya dibanding baseline semua saham? Gunakan periode 2 Januari 2025 sampai 31 Juli 2026.")


def periods(message: str) -> list[tuple]:
    return [(p["mode"], p.get("start"), p.get("end")) for p in extract([{"role": "user", "content": message}], REF).periods]


@pytest.mark.parametrize(("message", "start", "end"), [
    (POC2, "2026-07-01", "2026-08-31"),
    (POC3, "2025-01-02", "2026-07-31"),
    ("untuk BBCA dari 1 Juli 2026 sampai 31 Agustus 2026", "2026-07-01", "2026-08-31"),
    ("RSI for BBCA from July 1 to August 31, 2026", "2026-07-01", "2026-08-31"),
    ("RSI for BBCA from 1 July to 31 August 2026", "2026-07-01", "2026-08-31"),
    ("harga BBRI 1-15 Juli 2026", "2026-07-01", "2026-07-15"),
    ("BBCA 1 Desember sampai 31 Januari 2026", "2025-12-01", "2026-01-31"),
    ("z-score BBCA sejak 3 Maret 2026", "2026-03-03", REF.isoformat()),
    ("harga close BBCA pada 5 Agustus 2026", "2026-08-05", "2026-08-05"),
    ("BBCA 1 Juli sampai 30 September 2026", "2026-07-01", REF.isoformat()),  # clamped to the reference date
])
def test_day_level_dates_are_one_period(message: str, start: str, end: str) -> None:
    assert periods(message) == [("EXPLICIT_DATES", start, end)]


def test_month_level_phrases_are_unchanged() -> None:
    assert periods("BBCA Juli sampai Agustus 2026") == [("EXPLICIT_DATES", "2026-07-01", "2026-08-31")]
    assert periods("BBCA Agustus 2026") == [("EXPLICIT_DATES", "2026-08-01", "2026-08-31")]
    assert periods("RSI 14 hari BBCA Agustus 2026") == [("EXPLICIT_DATES", "2026-08-01", "2026-08-31")]
    assert periods("RSI BBCA dalam 30 hari terakhir") == [("TRAILING", None, None)]


def test_outcome_horizons_and_one_day_moves_are_not_the_analysis_period() -> None:
    assert periods("return BBCA dalam 5 hari perdagangan berikutnya, Agustus 2026") == [
        ("EXPLICIT_DATES", "2026-08-01", "2026-08-31")]
    assert periods("saham yang turun 7% dalam sehari selama 3 bulan terakhir") == [("TRAILING", None, None)]


@pytest.mark.parametrize(("message", "universe_all"), [
    (POC2, False),                                                      # "tiap saham" = each of BBCA and BBRI
    ("RSI 14 for BBCA and TLKM, the latest value for each stock", False),
    ("hitung RSI untuk setiap saham di IDX", True),                     # no tickers: every stock
    ("RSI untuk semua saham kecuali BBCA", True),                       # collective words keep meaning all
    (POC3, True),
])
def test_distributive_words_follow_the_named_tickers(message: str, universe_all: bool) -> None:
    found = extract([{"role": "user", "content": message}], REF)
    assert bool(found.universe_all) is universe_all


def test_the_poc2_request_now_matches_a_two_ticker_spec_for_july_and_august() -> None:
    spec = zscore_spec(universe="TICKERS", tickers=["BBCA", "BBRI"],
                       period={"mode": "EXPLICIT_DATES", "start": "2026-07-01", "end": "2026-08-31",
                               "provenance": "USER_EXPLICIT"}, window=10)
    result = reviewed(spec, POC2)
    assert not result.mismatches, result.mismatches
    requirements = {r["requirement"]: r["result"] for r in result.checks}
    assert requirements["universe"] == "MATCH" and requirements["analysis_period"] == "MATCH"


def test_a_thinly_traded_ticker_gets_an_earlier_date_and_the_exclusion_option(sandbox_root) -> None:
    frame = price_frame({f"T{i:02d}": ("2026-04-01", 125) for i in range(4)})
    thin = price_frame({"THIN": ("2026-04-01", 125)}, seed=3)
    days = pd.to_datetime(thin["date"])
    # trades on about one day in seven, with a trade at the start of the bound range (like CSMI and TFCO live)
    thin = thin[(days.dt.day % 5 == 0) | (days == days.min())]
    job = Job(sandbox_root, zscore_spec(), [("prices", [{"data": pd.concat([frame, thin], ignore_index=True),
                                                         "requested_from": "2026-04-01", "requested_to": "2026-09-23"}])])
    pre = job.preflight()
    [block] = pre["blocking"]
    assert block["code"] == "INSUFFICIENT_WARMUP_HISTORY" and block["entities"] == ["THIN"]
    recommended = pre["warmup"]["prices"]["recommended_from"]
    assert date.fromisoformat(block["suggested_from"]) < date.fromisoformat(recommended)
    assert block["suggested_from"] in block["message"] and "EXCLUDE_TICKERS" in block["message"]
    assert "THIN" in block["message"]
