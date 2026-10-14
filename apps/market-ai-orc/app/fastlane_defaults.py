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


def spans_text() -> str:
    """The relative spans in trading days, for the note's span rule."""
    return "; ".join(f"{entry['span']} = {entry['value']} {entry['unit']}" for entry in FASTLANE_DEFAULTS.values()
                     if "span" in entry)
