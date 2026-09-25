"""The Structured Analysis Spec: the machine-readable contract every analysis executes against.

The model proposes a spec; app/intent.py checks it against the user's own messages; an approved
spec is stored immutably (spec_id + sha256) and every run_python_analysis must reference one.
After execution, runtime/validator.py compares the actual outputs with this contract.

Every material requirement carries a provenance: USER_EXPLICIT (stated by the user), USER_CLARIFIED
(stated in a reply to a clarification question), APPROVED_DEFAULT (one of APPROVED_DEFAULTS below,
named by default_id), or AI_INFERRED (chosen by the model; reported as an unverified requirement).

Methods in METHODS have a separately implemented reference calculation (runtime/reference.py), so
their outputs can be independently recalculated. Their conventions follow, in order: TA-Lib where
TA-Lib defines the calculation, else the AI_formula_reference entry named in CONVENTIONS, else a
Saniti definition. CUSTOM calculations are allowed for any other research method (an AI-generated
formula); they must carry a formula and time-alignment rule. A CUSTOM calculation with an
`expression` (runtime/expression.py) is recalculated independently; without one it can never be
reported as CALCULATION_VERIFIED.

An optional `research` block turns a spec into a governed research experiment: the Research
Governor (app/research_policy.py) reviews it against the run's budget before a spec_id exists.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StringConstraints



def _load_expression_module():
    """runtime/expression.py is shared with the validator (which imports it as a plain module); load it by path
    so the harness does not depend on sys.path."""
    import importlib.util
    import sys
    from pathlib import Path

    name = "saniti_runtime_expression"
    if name not in sys.modules:
        location = Path(__file__).resolve().parents[1] / "runtime" / "expression.py"
        module_spec = importlib.util.spec_from_file_location(name, location)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        module_spec.loader.exec_module(module)
    return sys.modules[name]


_expression = _load_expression_module()
ExpressionError = _expression.ExpressionError
analyze_expression = _expression.analyze

SPEC_VERSION = "analysis_spec/v1"
SPEC_ID = r"^spec_[0-9a-f]{24}$"
IDENT = r"^[a-z][a-z0-9_]{0,39}$"
COLUMN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"
TABLE = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
OUTPUT_NAME = r"^[A-Za-z0-9_\-. ]{1,80}$"
TICKER = r"^[A-Z0-9]{2,6}$"

Provenance = Literal["USER_EXPLICIT", "USER_CLARIFIED", "APPROVED_DEFAULT", "AI_INFERRED"]
Ident = Annotated[str, StringConstraints(pattern=IDENT)]
Column = Annotated[str, StringConstraints(pattern=COLUMN)]

# Documented interpretations the user approved. A requirement that uses one names it in default_id
# and is reported to the user as a default, never as something the user said.
APPROVED_DEFAULTS: dict[str, dict[str, Any]] = {
    "DEFAULT_REFERENCE_DATE": {"value": "REQUEST_DATE", "meaning": "Relative periods are resolved against the request "
                               "date in the reference time zone."},
    "DEFAULT_REFERENCE_TIMEZONE": {"value": "Asia/Jakarta", "meaning": "The reference time zone is Asia/Jakarta."},
    "DEFAULT_TRAILING_CALENDAR_WINDOW": {"value": "TRAILING", "meaning": "'Last N days/weeks/months/years' is the "
                                         "calendar window (reference_date - N units, reference_date]."},
    "DEFAULT_TRADING_DAYS": {"value": "TRADING_DAYS", "meaning": "'Last N trading days' is the last N distinct "
                             "trading dates in the input at or before the reference date."},
    "DEFAULT_LATEST": {"value": "LATEST", "meaning": "'Latest' is each entity's newest observation at or before the "
                       "reference date; stale latest observations are reported."},
    "DEFAULT_MONTH_WITHOUT_YEAR": {"value": "MOST_RECENT", "meaning": "A month named without a year is its most recent "
                                   "occurrence at or before the reference date."},
    "DEFAULT_UNIVERSE_ALL_IN_SOURCE": {"value": "ALL_IN_SOURCE", "meaning": "'All IDX stocks' is every ticker present "
                                       "in the governed source table (current listings; survivorship applies)."},
    "DEFAULT_FREQUENCY_DAILY": {"value": "1D", "meaning": "Daily observations."},
    "DEFAULT_ROLLING_WINDOW_UNIT": {"value": "TRADING_OBSERVATIONS", "meaning": "An N-day rolling window is N trading "
                                    "observations of the entity, including the current one."},
    "DEFAULT_STD_DDOF": {"value": 0, "meaning": "A rolling standard deviation follows TA-Lib STDDEV: the "
                         "population standard deviation (ddof=0)."},
    "DEFAULT_ZSCORE_DDOF": {"value": 1, "meaning": "A rolling z-score uses the sample standard deviation (ddof=1), as "
                            "in AI_formula_reference CALC_053 and CALC_054 (TA-Lib has no z-score)."},
    "DEFAULT_ZSCORE_INCLUDES_CURRENT": {"value": "BY_INPUT", "meaning": "A z-score of a level series (for example a "
                                        "price) includes the current observation in its window (CALC_054); a z-score "
                                        "of a return series excludes it (CALC_053)."},
    "DEFAULT_RETURN_KIND": {"value": "SIMPLE", "meaning": "Returns are simple returns x_t / x_(t-h) - 1 (TA-Lib "
                            "ROCP)."},
    "DEFAULT_RETURN_HORIZON": {"value": 1, "meaning": "Returns are one-observation returns unless stated."},
    "DEFAULT_RETURN_AS_PERCENT": {"value": False, "meaning": "Returns are fractions, not percentages, unless stated."},
    "DEFAULT_RSI_PERIOD": {"value": 14, "meaning": "RSI uses 14 observations."},
    "DEFAULT_RSI_SMOOTHING": {"value": "WILDER", "meaning": "RSI uses Wilder smoothing seeded with the simple average "
                              "of the first N changes of the input series, and is 0 when both averages are 0 "
                              "(TA-Lib RSI convention)."},
    "DEFAULT_FORWARD_RETURN_ENTRY": {"value": "NEXT_OPEN", "meaning": "A forward return enters at the next "
                                     "observation's open and exits at the close h observations after the signal: "
                                     "close[t+h] / open[t+1] - 1 (AI_formula_reference CALC_011, tradable). The "
                                     "signal-close convention close[t+h] / close[t] - 1 (CALC_010) is used only when "
                                     "the user asks for it."},
    "DEFAULT_EVENT_OVERLAP_POLICY": {"value": "NON_OVERLAPPING", "meaning": "An event study keeps an entity's next "
                                     "event only after the previous event's outcome horizon has passed (independent "
                                     "outcome windows)."},
    "DEFAULT_EVENT_BASELINE": {"value": "ALL_ELIGIBLE", "meaning": "The baseline of an event study is every eligible "
                               "observation (defined signal and outcome) of the analysed universe in the period."},
    "DEFAULT_EVENT_MIN_EVENTS": {"value": 30, "meaning": "An event study needs at least 30 events before a historical "
                                 "pattern can be supported."},
    "DEFAULT_ZERO_DENOMINATOR": {"value": "NULL", "meaning": "A CUSTOM expression with a zero denominator has no "
                                 "value (NULL), never infinity."},
    "DEFAULT_CORRELATION_METHOD": {"value": "PEARSON", "meaning": "Correlation is Pearson correlation."},
    "DEFAULT_CORRELATION_TRANSFORM": {"value": "SIMPLE_RETURN", "meaning": "Correlation between price series is "
                                      "computed on simple returns, not on price levels."},
    "DEFAULT_CORRELATION_MIN_OVERLAP": {"value": 20, "meaning": "A correlation needs at least 20 overlapping "
                                        "observations."},
    "DEFAULT_PERIOD_RETURN_BASE": {"value": "PREVIOUS_OBSERVATION", "meaning": "A return over a period compares the "
                                   "last observation in the period with the last observation before the period "
                                   "starts (the change during the period)."},
    "DEFAULT_GROUP_MISSING_KEY": {"value": "SEPARATE_GROUP", "meaning": "Entities whose grouping value is missing (or "
                                  "listed in unknown_group_values) form their own group with a null key; they are "
                                  "reported, not dropped."},
    "DEFAULT_GROUP_MIN_OBSERVATIONS": {"value": 1, "meaning": "A group value needs at least one contributing "
                                       "non-null value."},
    "DEFAULT_GROUP_UNKNOWN_VALUES": {"value": [], "meaning": "No grouping value is treated as unknown unless listed."},
    "DEFAULT_RANK_TIE_POLICY": {"value": "INCLUDE_EXACTLY_N_STABLE", "meaning": "A top-N keeps exactly N rows; ties at "
                                "the boundary are broken by the key columns in ascending order."},
    "DEFAULT_PERIOD_STD_DDOF": {"value": 1, "meaning": "A standard deviation over the analysis period (for example the "
                                "volatility of daily returns) is the sample standard deviation (ddof=1), not "
                                "annualized."},
    "DEFAULT_PERIOD_STAT_MIN_OBSERVATIONS": {"value": 1, "meaning": "A period statistic needs at least one non-null "
                                             "observation in the period (a sample standard deviation needs two)."},
    "DEFAULT_SERIES_ALIGNMENT": {"value": "COMMON_DATES", "meaning": "Two series are compared on the dates where both "
                                 "have a defined value; nothing is forward-filled or shifted (maximum lag 0)."},
}

FAMILIES = ("RSI", "SMA", "STD", "ZSCORE", "RETURN", "FORWARD_RETURN", "CORRELATION", "EVENT_STUDY")
AGGREGATE_FUNCTIONS = ("COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MEDIAN", "MIN", "MAX")
PERIOD_FUNCTIONS = ("MEAN", "MEDIAN", "STD", "MIN", "MAX", "SUM", "COUNT")
GROUP_GRAINS = ("GROUP", "GROUP_DATE")
GROUP_METHODS = ("GROUP_AGGREGATE", "GROUP_CORRELATION")
SEGMENT_KEY = "segment"
MAX_SEGMENTS = 10


@dataclass(frozen=True)
class ParamDef:
    kind: Literal["int", "bool", "enum", "float", "list"]
    required: bool = False
    default: Any = None
    default_id: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] = ()


@dataclass(frozen=True)
class MethodDef:
    name: str
    families: tuple[str, ...]
    params: dict[str, ParamDef]
    input_columns: int
    grains: tuple[str, ...]
    formula: str
    time_alignment: str


WINDOW = ParamDef("int", required=True, minimum=2, maximum=1000)
WINDOW_UNIT = ParamDef("enum", default="TRADING_OBSERVATIONS", default_id="DEFAULT_ROLLING_WINDOW_UNIT",
                       choices=("TRADING_OBSERVATIONS",))
DDOF = ParamDef("int", default=0, default_id="DEFAULT_STD_DDOF", minimum=0, maximum=1)
ZSCORE_DDOF = ParamDef("int", default=1, default_id="DEFAULT_ZSCORE_DDOF", minimum=0, maximum=1)
RETURN_KIND = ParamDef("enum", default="SIMPLE", default_id="DEFAULT_RETURN_KIND", choices=("SIMPLE", "LOG"))
AS_PERCENT = ParamDef("bool", default=False, default_id="DEFAULT_RETURN_AS_PERCENT")
TRANSFORM = ParamDef("enum", default="SIMPLE_RETURN", default_id="DEFAULT_CORRELATION_TRANSFORM",
                     choices=("NONE", "SIMPLE_RETURN", "LOG_RETURN"))
CORR_METHOD = ParamDef("enum", default="PEARSON", default_id="DEFAULT_CORRELATION_METHOD",
                       choices=("PEARSON", "SPEARMAN"))
ENTITY_SERIES = ("ENTITY_DATE", "ENTITY")
TRAILING_ALIGNMENT = ("Value at t uses only observations at or before t of the same entity, in date order (no "
                      "look-ahead).")

METHODS: dict[str, MethodDef] = {
    "SMA": MethodDef("SMA", ("SMA",), {"window": WINDOW, "window_unit": WINDOW_UNIT}, 1, ENTITY_SERIES,
                     "mean(x[t-window+1 .. t])", TRAILING_ALIGNMENT),
    "ROLLING_STD": MethodDef("ROLLING_STD", ("STD",), {"window": WINDOW, "ddof": DDOF, "window_unit": WINDOW_UNIT}, 1,
                             ENTITY_SERIES, "std(x[t-window+1 .. t], ddof)", TRAILING_ALIGNMENT),
    "ROLLING_ZSCORE": MethodDef(
        "ROLLING_ZSCORE", ("ZSCORE", "SMA", "STD"),
        {"window": WINDOW, "ddof": ZSCORE_DDOF, "window_unit": WINDOW_UNIT,
         # default resolved per input in normalize(): True for level series, False for return series
         "include_current": ParamDef("bool", default=True, default_id="DEFAULT_ZSCORE_INCLUDES_CURRENT")},
        1, ENTITY_SERIES, "(x_t - mean(W)) / std(W, ddof); W = x[t-window+1 .. t] (include_current) or "
                          "x[t-window .. t-1]", TRAILING_ALIGNMENT),
    "RETURN": MethodDef("RETURN", ("RETURN",), {"horizon": ParamDef("int", default=1, default_id="DEFAULT_RETURN_HORIZON",
                                                                   minimum=1, maximum=1000),
                                                "kind": RETURN_KIND, "as_percent": AS_PERCENT}, 1, ENTITY_SERIES,
                        "x_t / x_(t-horizon) - 1 (SIMPLE) or ln(x_t / x_(t-horizon)) (LOG); x100 when as_percent",
                        TRAILING_ALIGNMENT),
    "FORWARD_RETURN": MethodDef("FORWARD_RETURN", ("FORWARD_RETURN",),
                                {"horizon": ParamDef("int", required=True, minimum=1, maximum=1000),
                                 "kind": RETURN_KIND, "as_percent": AS_PERCENT,
                                 "entry": ParamDef("enum", default="NEXT_OPEN", default_id="DEFAULT_FORWARD_RETURN_ENTRY",
                                                   choices=("NEXT_OPEN", "SIGNAL_CLOSE"))}, 2, ENTITY_SERIES,
                                "NEXT_OPEN: close_(t+horizon) / open_(t+1) - 1; SIGNAL_CLOSE: close_(t+horizon) / "
                                "close_t - 1 (SIMPLE) or the log of the ratio (LOG); x100 when as_percent",
                                "Value at t uses observations t+1 .. t+horizon (NEXT_OPEN) or t .. t+horizon "
                                "(SIGNAL_CLOSE) of the same entity: a look-ahead label, never a predictor at t."),
    "RSI": MethodDef("RSI", ("RSI",), {"period": ParamDef("int", default=14, default_id="DEFAULT_RSI_PERIOD", minimum=2,
                                                          maximum=500),
                                       "smoothing": ParamDef("enum", default="WILDER", default_id="DEFAULT_RSI_SMOOTHING",
                                                             choices=("WILDER",))},
                     1, ENTITY_SERIES, "100 * avg_gain / (avg_gain + avg_loss) with Wilder smoothing over period "
                                       "changes, seeded by the simple average of the first period changes of the input "
                                       "series (0 when both averages are 0)", TRAILING_ALIGNMENT),
    "ROLLING_CORRELATION": MethodDef(
        "ROLLING_CORRELATION", ("CORRELATION",),
        {"window": WINDOW, "method": CORR_METHOD, "window_unit": WINDOW_UNIT,
         "transform": ParamDef("enum", default="NONE", choices=("NONE", "SIMPLE_RETURN", "LOG_RETURN"))},
        2, ENTITY_SERIES, "corr(f(x)[t-window+1 .. t], f(y)[t-window+1 .. t]) within one entity; f = transform",
        TRAILING_ALIGNMENT),
    "CORRELATION": MethodDef(
        "CORRELATION", ("CORRELATION", "RETURN"),
        {"method": CORR_METHOD, "transform": TRANSFORM,
         "min_overlap": ParamDef("int", default=20, default_id="DEFAULT_CORRELATION_MIN_OVERLAP", minimum=3,
                                 maximum=100000)},
        1, ("ENTITY_PAIR",), "corr(f(x_a), f(x_b)) over the analysis-period dates both entities have; f = transform",
        "Both series are aligned on common dates inside the analysis period; a return on the first period date "
        "uses the previous observation."),
}
METHODS["EVENT_STUDY"] = MethodDef(
    "EVENT_STUDY", ("EVENT_STUDY",),
    {"min_events": ParamDef("int", default=30, default_id="DEFAULT_EVENT_MIN_EVENTS", minimum=1, maximum=100000),
     "overlap_policy": ParamDef("enum", default="NON_OVERLAPPING", default_id="DEFAULT_EVENT_OVERLAP_POLICY",
                                choices=("NON_OVERLAPPING", "ALL")),
     "baseline": ParamDef("enum", default="ALL_ELIGIBLE", default_id="DEFAULT_EVENT_BASELINE",
                          choices=("ALL_ELIGIBLE",))},
    0, ("SUMMARY",),
    "events: period observations where every signal predicate holds; outcome: the FORWARD_RETURN named in "
    "input_calculation; per segment: event_count, mean, median, hit_rate (outcome > 0), baseline over all eligible "
    "observations, delta_mean = mean - baseline_mean; NON_OVERLAPPING keeps an entity's next event only after the "
    "previous event's horizon",
    "Signals at t use only trailing values at or before t; the outcome starts after the signal. Events whose "
    "outcome horizon runs past the data are censored, not counted.")
# A return over the whole analysis period, per entity: the value on each period date t is x_t / x_base - 1, so the
# value at an entity's last period observation is its period return (ENTITY grain) and ENTITY_DATE outputs hold the
# cumulative path.
METHODS["PERIOD_RETURN"] = MethodDef(
    "PERIOD_RETURN", ("RETURN",),
    {"kind": RETURN_KIND, "as_percent": AS_PERCENT,
     "base": ParamDef("enum", default="PREVIOUS_OBSERVATION", default_id="DEFAULT_PERIOD_RETURN_BASE",
                      choices=("PREVIOUS_OBSERVATION", "FIRST_IN_PERIOD"))},
    1, ENTITY_SERIES, "x_t / x_base - 1 (SIMPLE) or ln(x_t / x_base) (LOG) for period dates t; x_base = last observation "
                      "before the period (PREVIOUS_OBSERVATION) or first observation in it (FIRST_IN_PERIOD); x100 when "
                      "as_percent",
    "Value at t uses the entity's observations from x_base up to t (no look-ahead).")
# Aggregation of an input column or of an earlier per-entity calculation by catalog-approved grouping keys. The
# aggregated value per entity is its value at its last observation in the period (static inputs: its only row);
# per_date aggregates each period date separately (GROUP_DATE outputs, aligned series).
METHODS["GROUP_AGGREGATE"] = MethodDef(
    "GROUP_AGGREGATE", (),
    {"function": ParamDef("enum", required=True, choices=AGGREGATE_FUNCTIONS),
     "per_date": ParamDef("bool", default=False),
     "missing_group_policy": ParamDef("enum", default="SEPARATE_GROUP", default_id="DEFAULT_GROUP_MISSING_KEY",
                                      choices=("SEPARATE_GROUP", "EXCLUDE")),
     "unknown_group_values": ParamDef("list", default=[], default_id="DEFAULT_GROUP_UNKNOWN_VALUES"),
     "min_observations": ParamDef("int", default=1, default_id="DEFAULT_GROUP_MIN_OBSERVATIONS", minimum=1,
                                  maximum=100000)},
    1, GROUP_GRAINS, "function(values of the group's entities); null values excluded; a group with fewer than "
                     "min_observations values has no value. Groups come from group_by (catalog columns) or from "
                     "segments (labelled predicates; an entity belongs to every segment whose predicates all hold)",
    "Per entity the value at its last observation in the period (or each period date when per_date).")
# A statistic of one entity's observations over the analysis period (for example the standard deviation of its daily
# returns). The value at t covers the entity's period observations up to t (expanding within the period), so the
# ENTITY value (last period observation) is the whole-period statistic. Nothing is annualized.
METHODS["PERIOD_STAT"] = MethodDef(
    "PERIOD_STAT", (),
    {"function": ParamDef("enum", required=True, choices=PERIOD_FUNCTIONS),
     "ddof": ParamDef("int", default=1, default_id="DEFAULT_PERIOD_STD_DDOF", minimum=0, maximum=1),
     "min_observations": ParamDef("int", default=1, default_id="DEFAULT_PERIOD_STAT_MIN_OBSERVATIONS", minimum=1,
                                  maximum=100000)},
    1, ENTITY_SERIES, "function(x over the entity's observations from the period start up to t); null values "
                      "excluded; STD uses ddof (not annualized); fewer than min_observations non-null values -> null",
    "Value at t uses only the entity's observations inside the period up to t (no look-ahead, no warm-up rows); the "
    "ENTITY value is the statistic over the whole period.")
# Correlation between the per-date series of groups (a per_date GROUP_AGGREGATE with one key or segments): one value
# per pair of groups.
METHODS["GROUP_CORRELATION"] = MethodDef(
    "GROUP_CORRELATION", ("CORRELATION",),
    {"method": CORR_METHOD,
     "min_overlap": ParamDef("int", default=20, default_id="DEFAULT_CORRELATION_MIN_OVERLAP", minimum=3,
                             maximum=100000),
     "alignment": ParamDef("enum", default="COMMON_DATES", default_id="DEFAULT_SERIES_ALIGNMENT",
                           choices=("COMMON_DATES",))},
    1, ("GROUP_PAIR",), "corr(s_a, s_b) for every pair of groups a < b (null-key groups excluded); s_g = the input "
                        "per-date group series; fewer than min_overlap common dates -> null",
    "Both series are aligned on the period dates where both are defined; no value is forward-filled or shifted "
    "(lag 0).")
CUSTOM = "CUSTOM"
METHOD_NAMES = tuple(METHODS) + (CUSTOM,)
# Every EVENT_STUDY summary output has these columns (key: segment).
EVENT_STUDY_COLUMNS = ("event_count", "mean", "median", "hit_rate", "baseline_count", "baseline_mean",
                       "baseline_median", "delta_mean", "censored_count", "overlapping_dropped")
LOOKAHEAD_METHODS = ("FORWARD_RETURN", "EVENT_STUDY")

# Where each method's definition comes from, in the approved order: TA-Lib, then AI_formula_reference,
# then a Saniti definition (EVENT_STUDY) or an AI-generated formula (CUSTOM).
CONVENTIONS: dict[str, dict[str, Any]] = {
    "SMA": {"source": "TA_LIB", "function": "SMA", "formula_refs": ["CALC_021"]},
    "ROLLING_STD": {"source": "TA_LIB", "function": "STDDEV", "formula_refs": []},
    "ROLLING_ZSCORE": {"source": "FORMULA_REFERENCE", "function": None, "formula_refs": ["CALC_053", "CALC_054"]},
    "RETURN": {"source": "TA_LIB", "function": "ROCP", "formula_refs": ["CALC_008", "CALC_009"]},
    "FORWARD_RETURN": {"source": "FORMULA_REFERENCE", "function": None, "formula_refs": ["CALC_010", "CALC_011"]},
    "RSI": {"source": "TA_LIB", "function": "RSI", "formula_refs": ["CALC_028"]},
    "ROLLING_CORRELATION": {"source": "TA_LIB", "function": "CORREL", "formula_refs": ["CALC_104"]},
    "CORRELATION": {"source": "TA_LIB", "function": "CORREL", "formula_refs": ["CALC_101", "CALC_102"]},
    "EVENT_STUDY": {"source": "FORMULA_REFERENCE", "function": None,
                    "formula_refs": ["CALC_176", "CALC_177", "CALC_178", "CALC_179"]},
    "PERIOD_RETURN": {"source": "SANITI", "function": None, "formula_refs": []},
    "GROUP_AGGREGATE": {"source": "SANITI", "function": None, "formula_refs": []},
    "PERIOD_STAT": {"source": "SANITI", "function": None, "formula_refs": []},
    "GROUP_CORRELATION": {"source": "SANITI", "function": None, "formula_refs": []},
}
# AI_formula_reference entries a registered method implements: a CUSTOM formula citing one must use the method.
REFERENCE_TO_METHOD = {ref: method for method, convention in CONVENTIONS.items() for ref in convention["formula_refs"]}
# Where Saniti deliberately differs from an AI_formula_reference entry (TA-Lib takes precedence).
CONVENTION_NOTES = {
    "CALC_028": "RSI follows TA-Lib: 0 (not 50) when average gain and loss are both 0.",
    "CALC_044": "Rolling volatility of returns: ROLLING_STD (TA-Lib, ddof=0) chained on RETURN; CALC_044 uses the "
                "sample standard deviation.",
}


def method_warmup(method: str, params: dict[str, Any]) -> tuple[int, int, int]:
    """(minimum warm-up observations, recommended warm-up observations, look-ahead observations)."""
    if method in ("SMA", "ROLLING_STD"):
        need = params["window"] - 1
        return need, need, 0
    if method == "ROLLING_ZSCORE":
        need = params["window"] - (1 if params["include_current"] else 0)
        return need, need, 0
    if method == "RETURN":
        return params["horizon"], params["horizon"], 0
    if method == "FORWARD_RETURN":
        return 0, 0, params["horizon"]
    if method == "EVENT_STUDY":
        return 0, 0, 0
    if method == "PERIOD_RETURN":
        need = 1 if params.get("base", "PREVIOUS_OBSERVATION") == "PREVIOUS_OBSERVATION" else 0
        return need, need, 0
    if method in ("GROUP_AGGREGATE", "GROUP_CORRELATION", "PERIOD_STAT"):
        return 0, 0, 0
    if method == "RSI":
        # Wilder smoothing depends on where the series starts; the seed effect decays by (n-1)/n per
        # observation, so about 10 x period observations make values practically start-independent.
        return params["period"], 10 * params["period"], 0
    if method == "ROLLING_CORRELATION":
        extra = 0 if params["transform"] == "NONE" else 1
        return params["window"] - 1 + extra, params["window"] - 1 + extra, 0
    if method == "CORRELATION":
        extra = 0 if params["transform"] == "NONE" else 1
        return extra, extra, 0
    warmup = max(int(params.get("warmup_observations") or 0), int(params.get("expression_warmup") or 0))
    return warmup, warmup, int(params.get("lookahead_observations") or 0)


# ---------------------------------------------------------------- request models (lenient input)

class Loose(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Universe(Loose):
    type: Literal["ALL_IN_SOURCE", "TICKERS"]
    tickers: list[Annotated[str, StringConstraints(pattern=TICKER)]] | None = Field(default=None, max_length=200)
    provenance: Provenance
    default_id: str | None = None


class Period(Loose):
    mode: Literal["EXPLICIT_DATES", "TRAILING", "TRADING_DAYS", "LATEST"]
    start: date | None = None
    end: date | None = None
    unit: Literal["DAY", "WEEK", "MONTH", "YEAR"] | None = None
    count: int | None = Field(default=None, ge=1, le=3650)
    provenance: Provenance
    default_id: str | None = None


class Frequency(Loose):
    value: Literal["1D", "1W", "1M"]
    provenance: Provenance
    default_id: str | None = None


class InputSpec(Loose):
    name: Ident
    source_table: Annotated[str, StringConstraints(pattern=TABLE)]
    entity_column: Column | None = None
    date_column: Column | None = None
    columns: list[Column] = Field(min_length=1, max_length=50)


class Param(Loose):
    name: Ident
    value: int | float | str | bool | list[str | int | float] | None
    provenance: Provenance
    default_id: str | None = None


class DataPolicies(Loose):
    zero_denominator: Literal["NULL", "ZERO"] = "NULL"
    missing: Literal["PROPAGATE"] = "PROPAGATE"


class GroupKey(Loose):
    """A grouping key: a catalog column (group_by_allowed) of an input; mapped to entities by entity column."""

    input: Ident
    column: Column


class SegmentPredicate(Loose):
    """One condition of a segment: a filterable catalog column of an input compared with catalog-typed values."""

    input: Ident
    column: Column
    operator: Literal["EQ", "NEQ", "IN", "GT", "GTE", "LT", "LTE", "IS_NULL", "IS_NOT_NULL"]
    value: str | int | float | bool | list[str | int | float] | None


class Segment(Loose):
    """A labelled group defined by predicates (all must hold), for groups one catalog column cannot express (for
    example two groups defined on different columns). Entities in no segment are not aggregated."""

    label: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.&()/-]{0,39}$")]
    predicates: list[SegmentPredicate] = Field(min_length=1, max_length=4)
    provenance: Literal["USER_EXPLICIT", "USER_CLARIFIED", "CATALOG_RESOLVED", "AI_INFERRED"] = "AI_INFERRED"
    user_text: Annotated[str, StringConstraints(max_length=200)] | None = None


class Calculation(Loose):
    id: Ident
    method: Literal["SMA", "ROLLING_STD", "ROLLING_ZSCORE", "RETURN", "FORWARD_RETURN", "RSI", "ROLLING_CORRELATION",
                    "CORRELATION", "EVENT_STUDY", "PERIOD_RETURN", "PERIOD_STAT", "GROUP_AGGREGATE",
                    "GROUP_CORRELATION", "CUSTOM"]
    dataset: Ident
    columns: list[Column] = Field(default_factory=list, max_length=4)
    input_calculation: Ident | None = None
    params: list[Param] = Field(default_factory=list, max_length=20)
    output_column: Column
    formula: Annotated[str, StringConstraints(max_length=1000)] | None = None
    time_alignment: Annotated[str, StringConstraints(max_length=300)] | None = None
    covers: list[Literal["RSI", "SMA", "STD", "ZSCORE", "RETURN", "FORWARD_RETURN", "CORRELATION",
                         "EVENT_STUDY"]] | None = None
    # EVENT_STUDY: the predicates that define an event (all must hold at t)
    signal: list["Predicate"] | None = Field(default=None, max_length=6)
    # CUSTOM: a recalculable expression (runtime/expression.py), the formula references it adapts, its meaning
    # and unit, and how undefined arithmetic is handled
    expression: Annotated[str, StringConstraints(max_length=500)] | None = None
    formula_refs: list[Annotated[str, StringConstraints(pattern=r"^CALC_[0-9]{3}$")]] | None = Field(
        default=None, max_length=5)
    meaning: Annotated[str, StringConstraints(max_length=300)] | None = None
    unit: Annotated[str, StringConstraints(max_length=40)] | None = None
    data_policies: DataPolicies | None = None
    # GROUP_AGGREGATE: the grouping keys (1-3), or labelled segments (1-10) instead
    group_by: list[GroupKey] | None = Field(default=None, max_length=3)
    segments: list[Segment] | None = Field(default=None, max_length=MAX_SEGMENTS)
    provenance: Provenance
    default_id: str | None = None


class Predicate(Loose):
    calculation: Ident
    op: Literal[">", ">=", "<", "<=", "==", "!="]
    value: float
    provenance: Provenance = "AI_INFERRED"
    default_id: str | None = None


Calculation.model_rebuild()


class Ranking(Loose):
    """Top-N of one calculation over the complete candidate population (every in-scope entity or group with a
    defined value), checked by the validator after recalculating all candidates."""

    calculation: Ident
    direction: Literal["ASC", "DESC"]
    limit: int = Field(ge=1, le=100)
    tie_policy: Literal["INCLUDE_EXACTLY_N_STABLE", "INCLUDE_TIES"] = "INCLUDE_EXACTLY_N_STABLE"
    provenance: Provenance = "AI_INFERRED"
    default_id: str | None = None


class OutputSpec(Loose):
    name: Annotated[str, StringConstraints(pattern=OUTPUT_NAME)]
    grain: Literal["ENTITY_DATE", "ENTITY", "ENTITY_PAIR", "GROUP", "GROUP_DATE", "GROUP_PAIR", "SUMMARY",
                   "UNSPECIFIED"]
    at: Literal["EACH_DATE", "PERIOD_END"] | None = None
    coverage: Literal["FULL", "SELECTION"] = "FULL"
    calculations: list[Ident] = Field(default_factory=list, max_length=12)
    selection: list[Predicate] | None = Field(default=None, max_length=6)
    entity_column: Column | None = None
    date_column: Column | None = None
    pair_columns: list[Column] | None = Field(default=None, min_length=2, max_length=2)
    # V2: the output's key columns (entity, grouping columns, date) and an optional top-N
    key_columns: list[Column] | None = Field(default=None, max_length=4)
    ranking: Ranking | None = None


class ExclusionRule(Loose):
    rule: Literal["MIN_OBSERVATIONS_IN_PERIOD", "MAX_STALENESS_DAYS", "EXCLUDE_TICKERS"]
    value: int | list[Annotated[str, StringConstraints(pattern=TICKER)]]
    provenance: Provenance
    default_id: str | None = None


EvidenceStandard = Literal["CALCULATION", "SCREEN", "DESCRIPTIVE", "HISTORICAL_PATTERN", "EXPLORATORY", "PREDICTIVE",
                           "SCENARIO"]


class Hypothesis(Loose):
    id: Annotated[str, StringConstraints(pattern=r"^H[0-9]{1,2}$")]
    statement: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class Holdout(Loose):
    """The out-of-sample part of the analysis period: observations on or after start (and up to end)."""

    start: date
    end: date | None = None


DesignType = Literal["EVENT_STUDY", "COMPARATIVE", "ASSOCIATION", "PREDICTIVE_TEMPORAL", "EXPLORATORY_SEARCH"]


class Comparator(Loose):
    """COMPARATIVE designs: GROUPS compares every pair of the listed groups (all groups when null); ALL_OTHERS compares
    each listed group with every other in-scope entity."""

    type: Literal["GROUPS", "ALL_OTHERS"]
    groups: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] | None = Field(default=None,
                                                                                              max_length=10)


class ResearchBlock(Loose):
    evidence_standard: EvidenceStandard
    objective: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    hypothesis: Hypothesis | None = None
    method_ref: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,62}$")] | None = None
    followup_of: Annotated[str, StringConstraints(pattern=SPEC_ID)] | None = None
    candidates: int | None = Field(default=None, ge=1, le=1_000_000)
    holdout: Holdout | None = None
    # the declared research design (the evidence contract the Research Governor and profile X check)
    design_type: DesignType | None = None
    primary_metric: Ident | None = None
    observation_unit: Literal["ENTITY", "ENTITY_DATE", "GROUP", "GROUP_DATE", "PAIR", "EVENT"] | None = None
    comparator: Comparator | None = None
    multiple_testing_policy: Literal["NONE", "BONFERRONI"] | None = None


class AnalysisSpec(Loose):
    question: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    universe: Universe
    analysis_period: Period
    frequency: Frequency
    inputs: list[InputSpec] = Field(min_length=1, max_length=4)
    calculations: list[Calculation] = Field(min_length=1, max_length=12)
    outputs: list[OutputSpec] = Field(min_length=1, max_length=8)
    exclusion_rules: list[ExclusionRule] = Field(default_factory=list, max_length=8)
    research: ResearchBlock | None = None


class Message(Loose):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=8000)]


class SpecRequest(Loose):
    """What market-ai-orc submits. user_messages and reference_time come from the orchestrator run, not
    from the model; the model supplies only the spec."""

    request_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]
    reference_time: datetime
    timezone: Annotated[str, StringConstraints(max_length=64)] = "Asia/Jakarta"
    user_messages: list[Message] = Field(min_length=1, max_length=12)
    spec: AnalysisSpec


# ---------------------------------------------------------------- normalization

class SpecInvalid(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def reference_date(reference_time: datetime, tz: str) -> date:
    moment = reference_time if reference_time.tzinfo else reference_time.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(ZoneInfo(tz)).date()


def resolve_period(period: dict[str, Any], ref: date) -> dict[str, Any]:
    """Calendar-resolved periods get dates now; TRADING_DAYS and LATEST are resolved from the input calendar."""
    mode = period["mode"]
    if mode == "STATIC":
        return {"mode": mode, "start": None, "end": None, "resolution": "NOT_TEMPORAL",
                "rule": "static reference data: no analysis period"}
    if mode == "EXPLICIT_DATES":
        return {"mode": mode, "start": period["start"], "end": period["end"], "resolution": "RESOLVED"}
    if mode == "TRAILING":
        count, unit = period["count"], period["unit"]
        if unit == "DAY":
            start = ref - timedelta(days=count - 1)
        elif unit == "WEEK":
            start = ref - timedelta(days=7 * count - 1)
        elif unit == "MONTH":
            start = add_months(ref, -count) + timedelta(days=1)
        else:
            start = add_months(ref, -12 * count) + timedelta(days=1)
        return {"mode": mode, "start": start.isoformat(), "end": ref.isoformat(), "resolution": "RESOLVED",
                "rule": f"(reference_date - {count} {unit.lower()}(s), reference_date]"}
    if mode == "TRADING_DAYS":
        return {"mode": mode, "start": None, "end": ref.isoformat(), "trading_days": period["count"],
                "resolution": "FROM_INPUT_CALENDAR", "rule": f"last {period['count']} trading dates <= reference_date"}
    return {"mode": mode, "start": None, "end": ref.isoformat(), "trading_days": 1, "resolution": "FROM_INPUT_CALENDAR",
            "rule": "each entity's newest observation <= reference_date"}


def calendar_days_for(observations: int) -> int:
    """Conservative calendar span holding N trading observations (weekends, ~10% holidays, buffer)."""
    return 0 if observations <= 0 else math.ceil(observations * 7 / 5 * 1.1) + 10


def _coerce(name: str, definition: ParamDef, value: Any) -> Any:
    if definition.kind == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value):
            raise ValueError(f"parameter {name} must be an integer")
        value = int(value)
    elif definition.kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"parameter {name} must be a number")
        value = float(value)
    elif definition.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"parameter {name} must be true or false")
    elif definition.kind == "list":
        if not isinstance(value, list) or len(value) > 20 or any(isinstance(v, bool) for v in value):
            raise ValueError(f"parameter {name} must be a list of at most 20 values")
        return sorted({str(v) for v in value})
    else:
        value = str(value).upper() if isinstance(value, str) else value
        if value not in definition.choices:
            raise ValueError(f"parameter {name} must be one of {list(definition.choices)}")
    if definition.minimum is not None and value < definition.minimum:
        raise ValueError(f"parameter {name} must be at least {definition.minimum:g}")
    if definition.maximum is not None and value > definition.maximum:
        raise ValueError(f"parameter {name} must be at most {definition.maximum:g}")
    return value


def _trace(item: dict[str, Any], where: str, problems: list[str]) -> None:
    default_id = item.get("default_id")
    if item.get("provenance") == "APPROVED_DEFAULT" and default_id not in APPROVED_DEFAULTS:
        problems.append(f"{where}: APPROVED_DEFAULT needs a default_id from the approved defaults "
                        f"({', '.join(sorted(APPROVED_DEFAULTS))})")
    elif default_id is not None and default_id not in APPROVED_DEFAULTS:
        problems.append(f"{where}: unknown default_id {default_id!r}")


def _looks_ahead(calc: dict[str, Any], calcs: dict[str, dict[str, Any]], depth: int = 0) -> bool:
    """True when a calculation (or anything it is built from) uses observations after t."""
    if depth > 20:
        return True
    if calc["method"] in LOOKAHEAD_METHODS:
        return True
    if calc["method"] == CUSTOM and any(p["name"] == "lookahead_observations" and (p["value"] or 0) > 0
                                        for p in calc["params"]):
        return True
    upstream = [calc["input_calculation"]] if calc.get("input_calculation") else []
    upstream += list(calc.get("expression_calcs") or [])
    return any(u in calcs and _looks_ahead(calcs[u], calcs, depth + 1) for u in upstream)


def normalize(spec: AnalysisSpec, ref: date) -> dict[str, Any]:
    """Validate semantics, fill method defaults (as APPROVED_DEFAULT), and return the canonical spec.

    Raises SpecInvalid with every problem found.
    """
    raw = spec.model_dump(mode="json")
    if any(c.get("segments") for c in raw["calculations"]):
        raise SpecInvalid(["segments need an Analysis Spec V2: their predicate values are typed against the catalog"])
    return normalize_raw(raw, ref)


def normalize_raw(raw: dict[str, Any], ref: date, problems: list[str] | None = None) -> dict[str, Any]:
    """normalize() on a JSON-shaped spec. Analysis Spec V2 (app/spec_v2.py) builds this shape from its own fields
    (analysis_period mode STATIC when there is no time scope) and reuses every calculation and output rule."""
    problems = problems if problems is not None else []
    inputs = {i["name"]: i for i in raw["inputs"]}
    if len(inputs) != len(raw["inputs"]):
        problems.append("inputs: names must be unique")
    for item in raw["inputs"]:
        item["columns"] = list(dict.fromkeys(item["columns"]))
        for key in ("entity_column", "date_column"):
            if item[key] is not None and item[key] not in item["columns"]:
                item["columns"].append(item[key])

    universe = raw["universe"]
    _trace(universe, "universe", problems)
    if universe["type"] == "TICKERS":
        tickers = sorted(set(universe["tickers"] or []))
        if not tickers:
            problems.append("universe: TICKERS needs at least one ticker")
        universe["tickers"] = tickers
    elif universe["tickers"]:
        problems.append("universe: ALL_IN_SOURCE must not list tickers")

    period = raw["analysis_period"]
    _trace(period, "analysis_period", problems)
    mode = period["mode"]
    if mode == "EXPLICIT_DATES":
        if not period["start"] or not period["end"]:
            problems.append("analysis_period: EXPLICIT_DATES needs start and end")
        elif period["start"] > period["end"]:
            problems.append("analysis_period: start is after end")
        elif date.fromisoformat(period["end"]) > ref:
            problems.append(f"analysis_period: end {period['end']} is after the reference date {ref.isoformat()}")
        period["unit"] = period["count"] = None
    elif mode == "TRAILING":
        if not period["unit"] or not period["count"]:
            problems.append("analysis_period: TRAILING needs unit and count")
        period["start"] = period["end"] = None
    elif mode == "TRADING_DAYS":
        if not period["count"]:
            problems.append("analysis_period: TRADING_DAYS needs count")
        period["start"] = period["end"] = period["unit"] = None
    else:  # LATEST, or STATIC (V2 without a time scope)
        period["start"] = period["end"] = period["unit"] = period["count"] = None
    _trace(raw["frequency"], "frequency", problems)
    static = mode == "STATIC"

    calcs: dict[str, dict[str, Any]] = {}
    outputs_of: dict[str, str] = {}
    for calc in raw["calculations"]:
        where = f"calculation {calc['id']}"
        _trace(calc, where, problems)
        if calc["id"] in calcs:
            problems.append(f"{where}: duplicate id")
        source = inputs.get(calc["dataset"])
        if source is None:
            problems.append(f"{where}: dataset {calc['dataset']!r} is not one of the inputs")
        if calc["output_column"] in outputs_of:
            problems.append(f"{where}: output_column {calc['output_column']!r} is already produced by "
                            f"{outputs_of[calc['output_column']]}")
        outputs_of[calc["output_column"]] = calc["id"]
        if calc["input_calculation"] is not None:
            upstream = calcs.get(calc["input_calculation"])
            if upstream is None:
                problems.append(f"{where}: input_calculation must name an earlier calculation")
            elif upstream["dataset"] != calc["dataset"]:
                problems.append(f"{where}: input_calculation must use the same dataset")
            elif upstream["method"] in GROUP_METHODS and calc["method"] != "GROUP_CORRELATION":
                problems.append(f"{where}: {upstream['method']} values are per group, not per entity; only "
                                f"GROUP_CORRELATION takes a group series as its input")
            if calc["columns"]:
                problems.append(f"{where}: use either columns or input_calculation, not both")
        elif source is not None:
            missing = [c for c in calc["columns"] if c not in source["columns"]]
            if missing:
                problems.append(f"{where}: columns {missing} are not listed in input {source['name']}")
        method = calc["method"]
        params = {}
        for param in calc["params"]:
            _trace(param, f"{where} parameter {param['name']}", problems)
            if param["name"] in params:
                problems.append(f"{where}: parameter {param['name']} is given twice")
            params[param["name"]] = param
        if method != "EVENT_STUDY" and calc["signal"]:
            problems.append(f"{where}: signal predicates belong to EVENT_STUDY calculations")
        calc.setdefault("group_by", None)
        calc.setdefault("segments", None)
        if method != "GROUP_AGGREGATE" and (calc["group_by"] or calc["segments"]):
            problems.append(f"{where}: group_by and segments belong to GROUP_AGGREGATE calculations")
        if method == "GROUP_AGGREGATE":
            keys = calc["group_by"] or []
            segments = calc["segments"] or []
            if keys and segments:
                problems.append(f"{where}: use either group_by or segments, not both")
            elif not keys and not segments:
                problems.append(f"{where}: GROUP_AGGREGATE needs group_by (1-3 catalog grouping columns) or segments "
                                f"(labelled predicates)")
            for key in keys:
                owner = inputs.get(key["input"])
                if owner is None:
                    problems.append(f"{where}: group_by input {key['input']!r} is not one of the inputs")
                elif key["column"] not in owner["columns"]:
                    problems.append(f"{where}: group_by column {key['column']!r} is not listed in input {owner['name']}")
            if len({(k["input"], k["column"]) for k in keys}) != len(keys):
                problems.append(f"{where}: group_by keys must be unique")
            labels = [segment["label"].strip().lower() for segment in segments]
            if len(set(labels)) != len(labels):
                problems.append(f"{where}: segment labels must be unique")
            for segment in segments:
                for predicate in segment["predicates"]:
                    owner = inputs.get(predicate["input"])
                    if owner is None:
                        problems.append(f"{where}: segment {segment['label']!r} input {predicate['input']!r} is not one "
                                        f"of the inputs")
                    elif predicate["column"] not in owner["columns"]:
                        problems.append(f"{where}: segment {segment['label']!r} column {predicate['column']!r} is not "
                                        f"listed in input {owner['name']}")
        if static and method not in ("GROUP_AGGREGATE", CUSTOM):
            problems.append(f"{where}: {method} works on dated observations; this spec has no time scope "
                            f"(TIME_SCOPE_REQUIRED)")
        if method == "PERIOD_RETURN" and mode not in ("EXPLICIT_DATES", "TRAILING"):
            problems.append(f"{where}: PERIOD_RETURN needs a calendar period (EXPLICIT_DATES or TRAILING)")
        if method == "PERIOD_STAT" and not static and mode not in ("EXPLICIT_DATES", "TRAILING", "TRADING_DAYS"):
            problems.append(f"{where}: PERIOD_STAT needs a period with a start (EXPLICIT_DATES, TRAILING or "
                            f"TRADING_DAYS), not {mode}")
        if method != CUSTOM and any(calc[k] for k in ("expression", "formula_refs", "meaning", "unit",
                                                        "data_policies")):
            problems.append(f"{where}: expression, formula_refs, meaning, unit and data_policies belong to CUSTOM "
                            f"calculations")
        if method == CUSTOM:
            if not (calc["formula"] or "").strip() or not (calc["time_alignment"] or "").strip():
                problems.append(f"{where}: CUSTOM calculations need a formula and a time_alignment rule")
            if not calc["columns"] and calc["input_calculation"] is None and not calc["expression"]:
                problems.append(f"{where}: CUSTOM calculations must name their input columns")
            implemented = sorted({REFERENCE_TO_METHOD[r] for r in calc["formula_refs"] or [] if r in REFERENCE_TO_METHOD})
            if implemented:
                problems.append(f"{where}: formula_refs {calc['formula_refs']} are implemented by the tested method(s) "
                                f"{implemented}; use that method (its convention takes precedence) instead of CUSTOM")
            if calc["expression"]:
                earlier = {cid for cid, c in calcs.items() if c["dataset"] == calc["dataset"]
                           and c["method"] not in LOOKAHEAD_METHODS + GROUP_METHODS}
                try:
                    info = analyze_expression(calc["expression"], set(calc["columns"]) | earlier)
                except ExpressionError as exc:
                    problems.append(f"{where}: expression: {exc}")
                else:
                    used_calcs = sorted(info.names & earlier)
                    calc["expression_calcs"] = used_calcs
                    calc["expression_warmup"] = info.warmup
                    calc["data_policies"] = calc["data_policies"] or {"zero_denominator": "NULL",
                                                                      "missing": "PROPAGATE"}
            for name in ("warmup_observations", "lookahead_observations"):
                if name in params:
                    try:
                        params[name]["value"] = _coerce(name, ParamDef("int", minimum=0, maximum=5000),
                                                        params[name]["value"])
                    except ValueError as exc:
                        problems.append(f"{where}: {exc}")
            calc["params"] = [params[k] for k in sorted(params)]
        else:
            definition = METHODS[method]
            expected_inputs = definition.input_columns
            given = len(calc["columns"]) + (1 if calc["input_calculation"] else 0)
            if method == "FORWARD_RETURN":
                entry_param = params.get("entry")
                entry = str(entry_param["value"]).upper() if entry_param and entry_param["value"] is not None \
                    else "NEXT_OPEN"
                expected_inputs = 2 if entry == "NEXT_OPEN" else 1
                if entry == "NEXT_OPEN" and calc["input_calculation"]:
                    problems.append(f"{where}: FORWARD_RETURN with entry NEXT_OPEN needs two input columns (the exit "
                                    f"close and the entry open), not input_calculation")
                elif entry == "NEXT_OPEN" and len(calc["columns"]) == 2:
                    opens = [c for c in calc["columns"] if "open" in c.lower()]
                    if len(opens) != 1:
                        problems.append(f"{where}: FORWARD_RETURN with entry NEXT_OPEN needs exactly one open column "
                                        f"(entry) and one close column (exit); got {calc['columns']}")
                    else:
                        calc["columns"] = [c for c in calc["columns"] if c != opens[0]] + opens  # [exit, entry]
            if method == "EVENT_STUDY":
                upstream = calcs.get(calc["input_calculation"] or "")
                if calc["columns"] or upstream is None or upstream["method"] != "FORWARD_RETURN":
                    problems.append(f"{where}: EVENT_STUDY takes no columns; input_calculation must name an earlier "
                                    f"FORWARD_RETURN calculation (the outcome)")
                if not calc["signal"]:
                    problems.append(f"{where}: EVENT_STUDY needs signal predicates (the event definition)")
                for predicate in calc["signal"] or []:
                    _trace(predicate, f"{where} signal", problems)
                    source_calc = calcs.get(predicate["calculation"])
                    if source_calc is None or source_calc["dataset"] != calc["dataset"]:
                        problems.append(f"{where}: signal calculation {predicate['calculation']!r} must be an earlier "
                                        f"calculation on the same input")
                    elif source_calc["method"] in GROUP_METHODS:
                        problems.append(f"{where}: signal calculation {predicate['calculation']!r} is per group, not "
                                        f"per entity observation")
                    elif source_calc["method"] in LOOKAHEAD_METHODS or _looks_ahead(source_calc, calcs):
                        problems.append(f"{where}: FUTURE_LABEL_IN_SIGNAL: signal {predicate['calculation']!r} uses "
                                        f"observations after t; an event may only use information available at t")
                expected_inputs = 1
            elif given != expected_inputs:
                problems.append(f"{where}: {method} takes {expected_inputs} input column(s)")
            unknown = sorted(set(params) - set(definition.params))
            if unknown:
                problems.append(f"{where}: unknown parameters {unknown} for {method}; allowed "
                                f"{sorted(definition.params)}")
            normalized = []
            dynamic: dict[str, Any] = {}
            if method == "ROLLING_ZSCORE":
                upstream = calcs.get(calc["input_calculation"] or "")
                is_return = upstream is not None and (upstream["method"] == "RETURN" or (
                    upstream["method"] == CUSTOM and "RETURN" in (upstream.get("covers") or [])))
                dynamic["include_current"] = not is_return
            for name, pdef in definition.params.items():
                if name in dynamic:
                    pdef = ParamDef(pdef.kind, pdef.required, dynamic[name], pdef.default_id, pdef.minimum,
                                    pdef.maximum, pdef.choices)
                if name in params and params[name]["value"] is None:
                    del params[name]  # null means "not chosen": the approved default applies and is marked so
                if name in params:
                    try:
                        value = _coerce(name, pdef, params[name]["value"])
                    except ValueError as exc:
                        problems.append(f"{where}: {exc}")
                        continue
                    entry = {**params[name], "value": value}
                    if entry["provenance"] == "APPROVED_DEFAULT" and (
                            entry["default_id"] != pdef.default_id or value != pdef.default):
                        problems.append(f"{where}: parameter {name} = {value!r} is not the approved default "
                                        f"({pdef.default_id}: {pdef.default!r})")
                    normalized.append(entry)
                elif pdef.required:
                    problems.append(f"{where}: parameter {name} is required for {method}")
                else:
                    normalized.append({"name": name, "value": pdef.default, "provenance": "APPROVED_DEFAULT",
                                       "default_id": pdef.default_id})
            calc["params"] = normalized
            calc["formula"] = definition.formula
            calc["time_alignment"] = definition.time_alignment
            calc["covers"] = list(definition.families)
            if method == "FORWARD_RETURN" and param_values(calc).get("entry") == "SIGNAL_CLOSE":
                calc["formula"] = ("close_(t+horizon) / close_t - 1 (SIMPLE) or the log of the ratio (LOG); x100 when "
                                   "as_percent (AI_formula_reference CALC_010, signal-close entry)")
            if raw["frequency"]["value"] not in ("1D", "STATIC") or (
                    raw["frequency"]["value"] == "STATIC" and method != "GROUP_AGGREGATE"):
                if not static:
                    problems.append(f"{where}: {method} is defined on daily observations; use CUSTOM for "
                                    f"{raw['frequency']['value']} resampled calculations")
            if method == "GROUP_AGGREGATE":
                values = param_values(calc)
                if values.get("per_date") and static:
                    problems.append(f"{where}: per_date grouping needs a time scope")
                if values.get("function") in ("SUM", "AVG", "MEDIAN") and not calc["input_calculation"] and \
                        calc["columns"] and source is not None and calc["columns"][0] == source.get("entity_column"):
                    problems.append(f"{where}: {values['function']} of the entity column is not meaningful; use "
                                    f"COUNT or COUNT_DISTINCT")
                if calc["segments"]:
                    # segments are explicit predicates: a missing attribute simply fails them
                    for name in ("missing_group_policy", "unknown_group_values"):
                        if name in params:
                            problems.append(f"{where}: {name} applies to group_by keys, not to segments")
                    calc["params"] = [p for p in calc["params"]
                                      if p["name"] not in ("missing_group_policy", "unknown_group_values")]
            if method == "PERIOD_STAT":
                function = param_values(calc).get("function")
                if function != "STD":
                    if "ddof" in params:
                        problems.append(f"{where}: ddof applies to PERIOD_STAT function STD only")
                    calc["params"] = [p for p in calc["params"] if p["name"] != "ddof"]
                calc["covers"] = ["STD"] if function == "STD" else []
            if method == "GROUP_CORRELATION":
                upstream = calcs.get(calc["input_calculation"] or "")
                if calc["columns"] or upstream is None or upstream["method"] != "GROUP_AGGREGATE" or \
                        not param_values(upstream).get("per_date"):
                    problems.append(f"{where}: GROUP_CORRELATION takes no columns; input_calculation must name an "
                                    f"earlier per_date GROUP_AGGREGATE (the aligned group series)")
                elif group_key_columns(upstream) == [] or len(group_key_columns(upstream)) > 1:
                    problems.append(f"{where}: the group series must have exactly one grouping key or use segments")
        calc["convention"] = CONVENTIONS.get(method) or {"source": "AI_GENERATED", "function": None,
                                                         "formula_refs": list(calc.get("formula_refs") or [])}
        calcs[calc["id"]] = calc

    output_names = set()
    for output in raw["outputs"]:
        where = f"output {output['name']}"
        if output["name"] in output_names:
            problems.append(f"{where}: duplicate output name")
        output_names.add(output["name"])
        for cid in output["calculations"]:
            if cid not in calcs:
                problems.append(f"{where}: unknown calculation {cid!r}")
        grain = output["grain"]
        refs = [calcs[c] for c in output["calculations"] if c in calcs]
        output.setdefault("key_columns", None)
        output.setdefault("ranking", None)
        if any(c["method"] == "EVENT_STUDY" for c in refs) and grain != "SUMMARY":
            problems.append(f"{where}: EVENT_STUDY calculations produce SUMMARY outputs")
        if any(c["method"] == "GROUP_AGGREGATE" for c in refs) and grain not in GROUP_GRAINS:
            problems.append(f"{where}: GROUP_AGGREGATE calculations produce GROUP or GROUP_DATE outputs")
        if any(c["method"] == "GROUP_CORRELATION" for c in refs) and grain != "GROUP_PAIR":
            problems.append(f"{where}: GROUP_CORRELATION calculations produce GROUP_PAIR outputs")
        if grain in GROUP_GRAINS:
            _group_output(output, refs, inputs, where, problems)
        elif grain == "GROUP_PAIR":
            _group_pair_output(output, refs, calcs, where, problems)
        ranking = output.get("ranking")
        if ranking is not None:
            _trace(ranking, f"{where} ranking", problems)
            if grain not in ("ENTITY", "GROUP"):
                problems.append(f"{where}: ranking applies to ENTITY or GROUP outputs")
            if ranking["calculation"] not in output["calculations"]:
                problems.append(f"{where}: ranking calculation {ranking['calculation']!r} must be listed in the "
                                f"output's calculations")
            if output["coverage"] != "SELECTION" or output["selection"]:
                problems.append(f"{where}: a ranked output has coverage SELECTION and no selection predicates (the "
                                f"top-N is its selection)")
        if grain == "SUMMARY":
            if len(refs) != 1 or refs[0]["method"] != "EVENT_STUDY":
                problems.append(f"{where}: a SUMMARY output lists exactly one EVENT_STUDY calculation")
            if output["coverage"] != "FULL" or output["selection"]:
                problems.append(f"{where}: SUMMARY outputs have coverage FULL and no selection")
            output["at"] = None
            output["entity_column"] = output["date_column"] = output["pair_columns"] = None
        elif grain == "ENTITY_PAIR":
            if raw["universe"]["type"] != "TICKERS" or len(raw["universe"]["tickers"] or []) < 2:
                problems.append(f"{where}: ENTITY_PAIR outputs need a TICKERS universe of at least two tickers")
            if not output["pair_columns"]:
                problems.append(f"{where}: ENTITY_PAIR outputs need pair_columns (two entity columns)")
            if any(c["method"] not in ("CORRELATION", CUSTOM) for c in refs):
                problems.append(f"{where}: only CORRELATION or CUSTOM calculations have ENTITY_PAIR grain")
            output["at"] = None
        elif grain in GROUP_GRAINS + ("GROUP_PAIR",):
            pass
        elif grain in ("ENTITY_DATE", "ENTITY"):
            if any(c["method"] == "CORRELATION" for c in refs):
                problems.append(f"{where}: CORRELATION produces ENTITY_PAIR outputs")
            output["at"] = "EACH_DATE" if grain == "ENTITY_DATE" else "PERIOD_END"
            dataset = inputs.get(refs[0]["dataset"]) if refs else None
            if dataset is not None:
                output["entity_column"] = output["entity_column"] or dataset["entity_column"]
                output["date_column"] = output["date_column"] or dataset["date_column"]
                if not dataset["entity_column"] or not dataset["date_column"]:
                    problems.append(f"{where}: input {dataset['name']} needs entity_column and date_column for "
                                    f"{grain} outputs")
            if not output["entity_column"] or (grain == "ENTITY_DATE" and not output["date_column"]):
                problems.append(f"{where}: {grain} outputs need entity_column" +
                                (" and date_column" if grain == "ENTITY_DATE" else ""))
            expected_keys = [output["entity_column"]] + ([output["date_column"]] if grain == "ENTITY_DATE" else [])
            if output["key_columns"] and output["key_columns"] != expected_keys:
                problems.append(f"{where}: key_columns {output['key_columns']} do not match the {grain} key "
                                f"{expected_keys}")
            output["key_columns"] = expected_keys
        else:
            output["at"] = None
        if output["coverage"] == "SELECTION":
            if not output["selection"] and not output.get("ranking"):
                problems.append(f"{where}: SELECTION coverage needs selection predicates or a ranking")
            for predicate in output["selection"] or []:
                _trace(predicate, f"{where} selection", problems)
                if predicate["calculation"] not in output["calculations"]:
                    problems.append(f"{where}: selection calculation {predicate['calculation']!r} must be listed in "
                                    f"the output's calculations")
        elif output["selection"]:
            problems.append(f"{where}: selection predicates need coverage SELECTION")
        if grain != "UNSPECIFIED" and not output["calculations"]:
            problems.append(f"{where}: list the calculations whose values this output contains")
    research = raw.get("research")
    if research and research.get("holdout"):
        holdout = research["holdout"]
        if holdout.get("end") and holdout["end"] < holdout["start"]:
            problems.append("research.holdout: end is before start")
    if research:
        for key in ("design_type", "primary_metric", "observation_unit", "comparator", "multiple_testing_policy"):
            research.setdefault(key, None)
        if research["primary_metric"] and research["primary_metric"] not in calcs:
            problems.append(f"research.primary_metric: {research['primary_metric']!r} is not a calculation id")
        if research["design_type"] and not research["observation_unit"] and research["primary_metric"] in calcs:
            research["observation_unit"] = observation_unit(research["design_type"], calcs[research["primary_metric"]])
    for rule in raw["exclusion_rules"]:
        _trace(rule, f"exclusion rule {rule['rule']}", problems)
        value = rule["value"]
        if rule["rule"] == "EXCLUDE_TICKERS" and not isinstance(value, list):
            problems.append("exclusion rule EXCLUDE_TICKERS needs a list of tickers")
        if rule["rule"] != "EXCLUDE_TICKERS" and not (isinstance(value, int) and value >= 1):
            problems.append(f"exclusion rule {rule['rule']} needs a positive integer")
    if problems:
        raise SpecInvalid(problems)
    return raw


def _group_output(output: dict[str, Any], refs: list[dict[str, Any]], inputs: dict[str, dict[str, Any]], where: str,
                  problems: list[str]) -> None:
    """GROUP / GROUP_DATE outputs: every listed calculation is a GROUP_AGGREGATE with the same keys; the output's
    key columns are the grouping columns (plus the date column for GROUP_DATE)."""
    grain = output["grain"]
    if not refs or any(c["method"] != "GROUP_AGGREGATE" for c in refs):
        problems.append(f"{where}: {grain} outputs list only GROUP_AGGREGATE calculations")
        return
    groupings = {grouping_identity(c) for c in refs}
    per_date = {bool(param_values(c).get("per_date")) for c in refs if c["params"]}
    if len(groupings) != 1:
        problems.append(f"{where}: every calculation of a {grain} output groups by the same keys or segments")
        return
    if per_date != {grain == "GROUP_DATE"}:
        problems.append(f"{where}: {grain} outputs need per_date {'true' if grain == 'GROUP_DATE' else 'false'} "
                        f"calculations")
    expected = group_key_columns(refs[0])
    if grain == "GROUP_DATE":
        dataset = inputs.get(refs[0]["dataset"]) or {}
        if not dataset.get("date_column"):
            problems.append(f"{where}: GROUP_DATE needs a dated input")
        else:
            expected.append(dataset["date_column"])
            output["date_column"] = dataset["date_column"]
    if output.get("key_columns") and output["key_columns"] != expected:
        problems.append(f"{where}: key_columns {output['key_columns']} do not match the grouping keys {expected}")
    output["key_columns"] = expected
    output["at"] = "EACH_DATE" if grain == "GROUP_DATE" else "PERIOD_END"
    output["entity_column"] = None
    output["pair_columns"] = None


def _group_pair_output(output: dict[str, Any], refs: list[dict[str, Any]], calcs: dict[str, dict[str, Any]],
                       where: str, problems: list[str]) -> None:
    """GROUP_PAIR outputs: GROUP_CORRELATION calculations of one group series; key columns <key>_a and <key>_b."""
    if not refs or any(c["method"] != "GROUP_CORRELATION" for c in refs):
        problems.append(f"{where}: GROUP_PAIR outputs list only GROUP_CORRELATION calculations")
        return
    series = {c["input_calculation"] for c in refs}
    if len(series) != 1:
        problems.append(f"{where}: every calculation of a GROUP_PAIR output correlates the same group series")
        return
    upstream = calcs.get(next(iter(series)) or "")
    keys = group_key_columns(upstream) if upstream else []
    if len(keys) != 1:
        return  # reported on the calculation
    expected = [f"{keys[0]}_a", f"{keys[0]}_b"]
    if output.get("key_columns") and output["key_columns"] != expected:
        problems.append(f"{where}: key_columns {output['key_columns']} do not match the pair key {expected}")
    output["key_columns"] = expected
    output["at"] = None
    output["entity_column"] = output["date_column"] = output["pair_columns"] = None


def observation_unit(design: str, metric: dict[str, Any]) -> str | None:
    """The unit one observation of the evidence is, derived from the design and its primary metric."""
    if design in ("EVENT_STUDY", "PREDICTIVE_TEMPORAL"):
        return "EVENT"
    if design == "COMPARATIVE":
        return "ENTITY"
    if design == "ASSOCIATION":
        return "GROUP_DATE" if metric["method"] == "GROUP_CORRELATION" else "ENTITY_DATE"
    return None


def group_key_columns(calc: dict[str, Any]) -> list[str]:
    """The key columns a GROUP_AGGREGATE produces (without the date of per_date series)."""
    if calc.get("segments"):
        return [SEGMENT_KEY]
    return [key["column"] for key in calc.get("group_by") or []]


def grouping_identity(calc: dict[str, Any]) -> str:
    return canonical_json({"group_by": calc.get("group_by") or [], "segments": calc.get("segments") or []})


def convention_notes(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Where a calculation's convention (TA-Lib first) differs from an AI_formula_reference entry: disclose it."""
    notes = []
    for calc in spec["calculations"]:
        refs = (calc.get("convention") or {}).get("formula_refs") or []
        if calc["method"] == "ROLLING_STD":
            refs = [*refs, "CALC_044"]
        for ref in refs:
            if ref in CONVENTION_NOTES:
                notes.append({"calculation": calc["id"], "formula_ref": ref, "note": CONVENTION_NOTES[ref]})
    return notes


def param_values(calc: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in calc["params"]}


def required_input(spec: dict[str, Any], resolved: dict[str, Any], ref: date) -> dict[str, Any]:
    """Warm-up and look-ahead each input needs, and the date range to request from the SQL Governor."""
    per_input: dict[str, dict[str, Any]] = {}
    chains: dict[str, tuple[int, int, int]] = {}
    for calc in spec["calculations"]:
        params = param_values(calc)
        if calc["method"] == CUSTOM:
            params["expression_warmup"] = calc.get("expression_warmup") or 0
        own = method_warmup(calc["method"], params)
        upstream = [calc["input_calculation"]] if calc["input_calculation"] else []
        upstream += list(calc.get("expression_calcs") or [])
        upstream += [p["calculation"] for p in calc.get("signal") or []]
        bases = [chains.get(u, (0, 0, 0)) for u in upstream] or [(0, 0, 0)]
        base = tuple(max(b[i] for b in bases) for i in range(3))
        chains[calc["id"]] = (own[0] + base[0], own[1] + base[1], own[2] + base[2])
    for item in spec["inputs"]:
        mine = [chains[c["id"]] for c in spec["calculations"] if c["dataset"] == item["name"]]
        minimum = max((m[0] for m in mine), default=0)
        recommended = max((m[1] for m in mine), default=0)
        lookahead = max((m[2] for m in mine), default=0)
        if resolved["mode"] == "STATIC" or item.get("is_static"):
            # no time column: nothing to warm up and no date range to request
            per_input[item["name"]] = {
                "source_table": item["source_table"], "required_columns": item["columns"],
                "minimum_warmup_observations": 0, "recommended_warmup_observations": 0, "lookahead_observations": 0,
                "recommended_request_date_range": None}
            continue
        end = date.fromisoformat(resolved["end"])
        if resolved.get("start"):
            start = date.fromisoformat(resolved["start"])
            request_from = start - timedelta(days=calendar_days_for(recommended))
        else:
            span = recommended + int(resolved.get("trading_days") or 1)
            request_from = end - timedelta(days=calendar_days_for(span) + (14 if resolved["mode"] == "LATEST" else 0))
        request_to = min(ref, end + timedelta(days=calendar_days_for(lookahead)))
        per_input[item["name"]] = {
            "source_table": item["source_table"], "required_columns": item["columns"],
            "minimum_warmup_observations": minimum, "recommended_warmup_observations": recommended,
            "lookahead_observations": lookahead,
            "recommended_request_date_range": {"from": request_from.isoformat(), "to": request_to.isoformat()},
        }
    return per_input


def output_contract(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """What each declared output must contain, as the validator will read it."""
    calcs = {c["id"]: c for c in spec["calculations"]}
    contract = []
    for output in spec["outputs"]:
        grain = output["grain"]
        if grain == "SUMMARY":
            holdout = (spec.get("research") or {}).get("holdout")
            contract.append({"name": output["name"], "grain": grain, "key_columns": ["segment"],
                             "value_columns": list(EVENT_STUDY_COLUMNS), "coverage": "FULL", "emit": "emit_table",
                             "rows": ["ALL"] + (["IN_SAMPLE", "OUT_OF_SAMPLE"] if holdout else [])})
            continue
        if grain == "ENTITY_PAIR":
            keys = list(output["pair_columns"] or [])
        elif grain == "UNSPECIFIED":
            keys = []
        elif grain in GROUP_GRAINS + ("GROUP_PAIR",):
            keys = list(output.get("key_columns") or [])
        else:
            keys = [output["entity_column"]] + ([output["date_column"]] if grain == "ENTITY_DATE" else [])
        item = {"name": output["name"], "grain": grain, "key_columns": keys,
                "value_columns": [calcs[c]["output_column"] for c in output["calculations"] if c in calcs],
                "coverage": output["coverage"], "emit": "emit_table"}
        if grain == "ENTITY":
            item["optional_columns"] = [output["date_column"]] if output.get("date_column") else []
            item["at"] = output.get("at")
        if output.get("selection"):
            item["selection"] = output["selection"]
        if output.get("ranking"):
            item["ranking"] = output["ranking"]
        grouped = [calcs[c] for c in output["calculations"] if c in calcs and calcs[c].get("segments")]
        if grouped:
            item["segments"] = [{"label": s["label"], "predicates": s["predicates"]} for s in grouped[0]["segments"]]
            item["segment_rule"] = ("An entity belongs to every segment whose predicates all hold; entities in no "
                                    "segment are not aggregated. The key column 'segment' holds the label.")
        if grain == "GROUP_PAIR":
            item["pair_rule"] = ("One row per pair of groups with a non-null key, the smaller key in the _a column; "
                                 "series aligned on dates where both are defined.")
        contract.append(item)
    return contract


def derived_feature_definitions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Every calculation output is a derived feature of this analysis (never a database feature)."""
    grains: dict[str, list[str]] = {}
    for output in spec["outputs"]:
        for cid in output["calculations"]:
            grains.setdefault(cid, []).append(output["grain"])
    inputs = {i["name"]: i for i in spec["inputs"]}
    definitions = []
    for calc in spec["calculations"]:
        definition = {
            "name": calc["output_column"], "calculation_id": calc["id"], "method": calc["method"],
            "formula": calc["formula"], "parameters": param_values(calc),
            "source": {"logical_dataset": calc["dataset"], "source_table": inputs[calc["dataset"]]["source_table"],
                       "input_columns": calc["columns"], "input_calculation": calc["input_calculation"]},
            "output_grain": sorted(set(grains.get(calc["id"], []))) or ["NOT_EMITTED"],
            "time_alignment": calc["time_alignment"], "origin": "DERIVED_IN_ANALYSIS",
            "status": "EXPLORATORY_UNVALIDATED",
            "independent_check": "REFERENCE_RECALCULATION" if calc["method"] in METHODS else
            "EXPRESSION_RECALCULATION" if calc.get("expression") else "NONE",
            "convention": calc.get("convention"),
            "formula_status": "TESTED_IMPLEMENTATION" if calc["method"] in METHODS else "CUSTOM_FORMULA",
        }
        if calc["method"] == CUSTOM:
            definition.update({k: calc.get(k) for k in ("expression", "formula_refs", "meaning", "unit",
                                                         "data_policies") if calc.get(k)})
        definition["definition_sha256"] = sha256_json(definition)
        definitions.append(definition)
    return definitions


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
