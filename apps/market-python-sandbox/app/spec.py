"""The Structured Analysis Spec: the machine-readable contract every analysis executes against.

The model proposes a spec; app/intent.py checks it against the user's own messages; an approved
spec is stored immutably (spec_id + sha256) and every run_python_analysis must reference one.
After execution, runtime/validator.py compares the actual outputs with this contract.

Every material requirement carries a provenance: USER_EXPLICIT (stated by the user), USER_CLARIFIED
(stated in a reply to a clarification question), APPROVED_DEFAULT (one of APPROVED_DEFAULTS below,
named by default_id), or AI_INFERRED (chosen by the model; reported as an unverified requirement).

Methods in METHODS have a separately implemented reference calculation (runtime/reference.py), so
their outputs can be independently recalculated. CUSTOM calculations are allowed for any other
research method; they must carry a formula and time-alignment rule, but they can never be
reported as CALCULATION_VERIFIED.
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
    "DEFAULT_STD_DDOF": {"value": 1, "meaning": "Standard deviation is the sample standard deviation (ddof=1)."},
    "DEFAULT_ZSCORE_INCLUDES_CURRENT": {"value": True, "meaning": "A rolling z-score window includes the current "
                                        "observation."},
    "DEFAULT_RETURN_KIND": {"value": "SIMPLE", "meaning": "Returns are simple returns x_t / x_(t-h) - 1."},
    "DEFAULT_RETURN_HORIZON": {"value": 1, "meaning": "Returns are one-observation returns unless stated."},
    "DEFAULT_RETURN_AS_PERCENT": {"value": False, "meaning": "Returns are fractions, not percentages, unless stated."},
    "DEFAULT_RSI_PERIOD": {"value": 14, "meaning": "RSI uses 14 observations."},
    "DEFAULT_RSI_SMOOTHING": {"value": "WILDER", "meaning": "RSI uses Wilder smoothing seeded with the simple average "
                              "of the first N changes of the input series (TA-Lib convention)."},
    "DEFAULT_CORRELATION_METHOD": {"value": "PEARSON", "meaning": "Correlation is Pearson correlation."},
    "DEFAULT_CORRELATION_TRANSFORM": {"value": "SIMPLE_RETURN", "meaning": "Correlation between price series is "
                                      "computed on simple returns, not on price levels."},
    "DEFAULT_CORRELATION_MIN_OVERLAP": {"value": 20, "meaning": "A correlation needs at least 20 overlapping "
                                        "observations."},
}

FAMILIES = ("RSI", "SMA", "STD", "ZSCORE", "RETURN", "FORWARD_RETURN", "CORRELATION")


@dataclass(frozen=True)
class ParamDef:
    kind: Literal["int", "bool", "enum", "float"]
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
DDOF = ParamDef("int", default=1, default_id="DEFAULT_STD_DDOF", minimum=0, maximum=1)
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
        {"window": WINDOW, "ddof": DDOF, "window_unit": WINDOW_UNIT,
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
                                 "kind": RETURN_KIND, "as_percent": AS_PERCENT}, 1, ENTITY_SERIES,
                                "x_(t+horizon) / x_t - 1 (SIMPLE) or ln(x_(t+horizon) / x_t) (LOG); x100 when "
                                "as_percent",
                                "Value at t uses observations t .. t+horizon of the same entity (look-ahead label; "
                                "never use as a predictor at t)."),
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
CUSTOM = "CUSTOM"
METHOD_NAMES = tuple(METHODS) + (CUSTOM,)


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
    warmup = int(params.get("warmup_observations") or 0)
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
    value: int | float | str | bool | None
    provenance: Provenance
    default_id: str | None = None


class Calculation(Loose):
    id: Ident
    method: Literal["SMA", "ROLLING_STD", "ROLLING_ZSCORE", "RETURN", "FORWARD_RETURN", "RSI", "ROLLING_CORRELATION",
                    "CORRELATION", "CUSTOM"]
    dataset: Ident
    columns: list[Column] = Field(default_factory=list, max_length=4)
    input_calculation: Ident | None = None
    params: list[Param] = Field(default_factory=list, max_length=20)
    output_column: Column
    formula: Annotated[str, StringConstraints(max_length=1000)] | None = None
    time_alignment: Annotated[str, StringConstraints(max_length=300)] | None = None
    covers: list[Literal["RSI", "SMA", "STD", "ZSCORE", "RETURN", "FORWARD_RETURN", "CORRELATION"]] | None = None
    provenance: Provenance
    default_id: str | None = None


class Predicate(Loose):
    calculation: Ident
    op: Literal[">", ">=", "<", "<=", "==", "!="]
    value: float
    provenance: Provenance = "AI_INFERRED"
    default_id: str | None = None


class OutputSpec(Loose):
    name: Annotated[str, StringConstraints(pattern=OUTPUT_NAME)]
    grain: Literal["ENTITY_DATE", "ENTITY", "ENTITY_PAIR", "UNSPECIFIED"]
    at: Literal["EACH_DATE", "PERIOD_END"] | None = None
    coverage: Literal["FULL", "SELECTION"] = "FULL"
    calculations: list[Ident] = Field(default_factory=list, max_length=12)
    selection: list[Predicate] | None = Field(default=None, max_length=6)
    entity_column: Column | None = None
    date_column: Column | None = None
    pair_columns: list[Column] | None = Field(default=None, min_length=2, max_length=2)


class ExclusionRule(Loose):
    rule: Literal["MIN_OBSERVATIONS_IN_PERIOD", "MAX_STALENESS_DAYS", "EXCLUDE_TICKERS"]
    value: int | list[Annotated[str, StringConstraints(pattern=TICKER)]]
    provenance: Provenance
    default_id: str | None = None


class AnalysisSpec(Loose):
    question: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    universe: Universe
    analysis_period: Period
    frequency: Frequency
    inputs: list[InputSpec] = Field(min_length=1, max_length=4)
    calculations: list[Calculation] = Field(min_length=1, max_length=12)
    outputs: list[OutputSpec] = Field(min_length=1, max_length=8)
    exclusion_rules: list[ExclusionRule] = Field(default_factory=list, max_length=8)


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


def normalize(spec: AnalysisSpec, ref: date) -> dict[str, Any]:
    """Validate semantics, fill method defaults (as APPROVED_DEFAULT), and return the canonical spec.

    Raises SpecInvalid with every problem found.
    """
    raw = spec.model_dump(mode="json")
    problems: list[str] = []
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
    else:
        period["start"] = period["end"] = period["unit"] = period["count"] = None
    _trace(raw["frequency"], "frequency", problems)

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
        if method == CUSTOM:
            if not (calc["formula"] or "").strip() or not (calc["time_alignment"] or "").strip():
                problems.append(f"{where}: CUSTOM calculations need a formula and a time_alignment rule")
            if not calc["columns"] and calc["input_calculation"] is None:
                problems.append(f"{where}: CUSTOM calculations must name their input columns")
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
            if given != expected_inputs:
                problems.append(f"{where}: {method} takes {expected_inputs} input column(s)")
            unknown = sorted(set(params) - set(definition.params))
            if unknown:
                problems.append(f"{where}: unknown parameters {unknown} for {method}; allowed "
                                f"{sorted(definition.params)}")
            normalized = []
            for name, pdef in definition.params.items():
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
            if raw["frequency"]["value"] != "1D":
                problems.append(f"{where}: {method} is defined on daily observations; use CUSTOM for "
                                f"{raw['frequency']['value']} resampled calculations")
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
        if grain == "ENTITY_PAIR":
            if raw["universe"]["type"] != "TICKERS" or len(raw["universe"]["tickers"] or []) < 2:
                problems.append(f"{where}: ENTITY_PAIR outputs need a TICKERS universe of at least two tickers")
            if not output["pair_columns"]:
                problems.append(f"{where}: ENTITY_PAIR outputs need pair_columns (two entity columns)")
            if any(c["method"] not in ("CORRELATION", CUSTOM) for c in refs):
                problems.append(f"{where}: only CORRELATION or CUSTOM calculations have ENTITY_PAIR grain")
            output["at"] = None
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
        else:
            output["at"] = None
        if output["coverage"] == "SELECTION":
            if not output["selection"]:
                problems.append(f"{where}: SELECTION coverage needs selection predicates")
            for predicate in output["selection"] or []:
                _trace(predicate, f"{where} selection", problems)
                if predicate["calculation"] not in output["calculations"]:
                    problems.append(f"{where}: selection calculation {predicate['calculation']!r} must be listed in "
                                    f"the output's calculations")
        elif output["selection"]:
            problems.append(f"{where}: selection predicates need coverage SELECTION")
        if grain != "UNSPECIFIED" and not output["calculations"]:
            problems.append(f"{where}: list the calculations whose values this output contains")
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


def param_values(calc: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in calc["params"]}


def required_input(spec: dict[str, Any], resolved: dict[str, Any], ref: date) -> dict[str, Any]:
    """Warm-up and look-ahead each input needs, and the date range to request from the SQL Governor."""
    per_input: dict[str, dict[str, Any]] = {}
    chains: dict[str, tuple[int, int, int]] = {}
    for calc in spec["calculations"]:
        own = method_warmup(calc["method"], param_values(calc))
        base = chains.get(calc["input_calculation"], (0, 0, 0)) if calc["input_calculation"] else (0, 0, 0)
        chains[calc["id"]] = (own[0] + base[0], own[1] + base[1], own[2] + base[2])
    for item in spec["inputs"]:
        mine = [chains[c["id"]] for c in spec["calculations"] if c["dataset"] == item["name"]]
        minimum = max((m[0] for m in mine), default=0)
        recommended = max((m[1] for m in mine), default=0)
        lookahead = max((m[2] for m in mine), default=0)
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
        if grain == "ENTITY_PAIR":
            keys = list(output["pair_columns"] or [])
        elif grain == "UNSPECIFIED":
            keys = []
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
            "independent_check": "REFERENCE_RECALCULATION" if calc["method"] in METHODS else "NONE",
        }
        definition["definition_sha256"] = sha256_json(definition)
        definitions.append(definition)
    return definitions


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
