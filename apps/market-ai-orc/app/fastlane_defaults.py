"""EXEC-FASTLANE V4 (user 2026-10-14, C and E: "kasih nama tablenya dan harus di update di agents MD karna user perlu
tweak"): the defaults the fast lane uses when the user leaves a parameter open, and the size above which a data need
is checked first. AI_FASTLANE_DECISION_RULES writes them into the fast-lane decisions note, so the model takes them
instead of weighing options. To change one, edit its "value" here, run tests/test_fastlane.py, push main (orc
redeploys itself) and record it in EXEC.md; AGENTS.md, "Fast-lane defaults".

The first values are the choices the model made most often in the logged fast-lane runs of 2026-10-13/14 (41 runs):
the 90th percentile for "large", a 21-trading-day window, five years of history."""
from __future__ import annotations

from typing import Any

FASTLANE_DEFAULTS: dict[str, dict[str, Any]] = {
    "large_threshold_percentile": {
        "value": 90, "unit": "percentile",
        "means": "a 'large' or 'high' value (a big net buy, a high volume) is at or above this percentile of the "
                 "entity's own history in the period"},
    "rolling_window_days": {
        "value": 21, "unit": "trading days",
        "means": "a rolling or 'recent' window the user does not name (about one month)"},
    "forward_horizon_days": {
        "value": 5, "unit": "trading days",
        "means": "the horizon of a forward return the user does not name"},
    "history_years": {
        "value": 5, "unit": "years",
        "means": "how far back a data need reaches when the user names no period"},
    # V4.1 (user 2026-10-14: "5 hari kerja, senin-jumat"; then "5 hari bursa terakhir" and "semua hari bursa"): a
    # relative span counts trading days back from the last available date, rolling
    "span_week_trading_days": {
        "value": 5, "unit": "trading days", "span": "1 minggu",
        "means": "'1 minggu terakhir' (a week)"},
    "span_month_trading_days": {
        "value": 21, "unit": "trading days", "span": "1 bulan",
        "means": "'1 bulan terakhir' (a month; '3 bulan' is three times this)"},
    "span_year_trading_days": {
        "value": 252, "unit": "trading days", "span": "1 tahun",
        "means": "'1 tahun terakhir' (a year)"},
    # O5 item 2 (EXEC-IMPL-1016 Fase 2, user 2026-10-15 "Sisanya OK untuk O5"; edge_2f7523a7 spent about a third of
    # its first call's reasoning on what these words mean): readings of words the user leaves open, taken as
    # assumptions; the user's words or the conversation's facts win, and the model may still ask back
    "largest_buying_measure": {
        "value": "net", "unit": "reading",
        "means": "the largest or top buying ('pembelian tertinggi', 'beli terbesar') of a broker or investor is "
                 "the net value (buy minus sell); the gross buy is shown beside it"},
    "foreign_party": {
        "value": "investor type", "unit": "reading",
        "means": "'asing' (foreign) is the foreign investor type of the transactions, not the broker's own type"},
    "event_date_meaning": {
        "value": "implementation close", "unit": "reading",
        "means": "an index rebalancing or other market event date ('tanggal efektif') is the trading close the change "
                 "is implemented at; the first trading day after it is named as the day it applies"},
    "feasibility_entity_years": {
        "value": 100, "unit": "entity-years",
        "means": "check_data_feasibility is called first only when a request's entities times its years exceed this"},
}


def value(name: str) -> Any:
    return FASTLANE_DEFAULTS[name]["value"]


def parameters_text() -> str:
    """The open-parameter defaults in one line for the note (the size limit and the history are their own rules)."""
    return "; ".join(f"{entry['means']}: {entry['value']} {entry['unit']}" for name, entry in FASTLANE_DEFAULTS.items()
                     if name in ("large_threshold_percentile", "rolling_window_days", "forward_horizon_days"))


def readings_text() -> str:
    """O5 item 2: the default readings of open words, for the note's rule 3."""
    return "; ".join(f"{entry['means']} ({entry['value']})" for entry in FASTLANE_DEFAULTS.values()
                     if entry["unit"] == "reading")


SPAN_EXAMPLE_MULTIPLE = 3  # M173 (EXEC-1018B E7): the worked multiple shown beside each span unit


def spans_text() -> str:
    """The relative spans in trading days, for the note's span rule: each unit with its worked multiple, both from the
    table (M173, user 2026-10-16 "3 bulan ini kan pakai 63 hari"; an example typed apart from its value was read as
    '3 bulan = 21'), so a changed value changes its example too."""
    parts = []
    for entry in FASTLANE_DEFAULTS.values():
        if "span" not in entry:
            continue
        count, unit = entry["span"].split(" ", 1)
        n = SPAN_EXAMPLE_MULTIPLE
        parts.append(f"{entry['span']} = {entry['value']} {entry['unit']}, N {unit} = N × {entry['value']} "
                     f"(e.g. {n} {unit} = {n * entry['value'] // int(count)})")
    return "; ".join(parts)
