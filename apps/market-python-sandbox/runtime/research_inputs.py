"""Declarative research inputs (Multi-Angle Research, validation level FORMULA_AND_STATISTICS_VERIFIED).

An angle's input can be declared instead of built by model code: one approved data request of the angle's contract, an
optional range of it, and each role of the angle's engine as

    "<expression>"              the restricted grammar of runtime/expression.py over the request's contract columns
                                (and the numeric roles evaluated before it: signal, leader, follower, state), past-only;
    {"column": "<column>"}      a contract column as it is (a group label);
    {"forward_return": "<column>"}
                                the backend's forward return over the angle's approved horizon: value h observations
                                later of the same entity / value now - 1 (percent when the angle's unit is PERCENT);
                                undefined (censored) when those observations are not in the delivered data.
    {"forward_return": "<column>", "request": "<another request of the angle's contract>"}
                                the same forward return computed on that request's own rows (per entity, its own
                                calendar), then matched to this request's rows by entity and date. Found live (suite20,
                                2026-09-29, S15): a condition in the broker table and the price in the price table could
                                not be declared together, and the frame the model built used the price level as outcome.

The session wrapper and the harness build the input with this same module from the same governed rows and approved
values, so the harness reproduces the input without trusting anything the model's process computed. Expressions and
lags see the whole delivered request (its history buffer included); only rows inside the declared range(s) are
analysed, and forward returns may use the future buffer.
"""
from __future__ import annotations

import sys
from typing import Any


def _expression_module():
    """runtime/expression.py: imported by name in a session (the runtime directory is on sys.path); the harness loads it
    under a private name first (app/research_validation.py)."""
    module = sys.modules.get("saniti_runtime_expression")
    if module is None:
        import expression as module
    return module

ROLES: dict[str, tuple[str, ...]] = {
    "conditional_distribution": ("condition", "outcome"),
    "threshold_sensitivity": ("signal", "outcome"),
    "streak_persistence": ("state",),
    "regime_comparison": ("group", "outcome"),
    "cohort_comparison": ("group", "outcome"),
    "quantile_ranking": ("signal", "outcome"),
    "lead_lag": ("leader", "follower"),
    "correlation_dependency": ("leader", "follower"),
}
OPTIONAL: dict[str, tuple[str, ...]] = {"correlation_dependency": ("condition",)}
ORDER = ("signal", "leader", "follower", "state", "condition", "group", "outcome")
BOOLEAN = {"condition", "state"}
LABEL = {"group"}
MAX_DECLARATION_CHARS = 4000


class InputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def roles_for(method_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if method_id not in ROLES:
        raise InputError("METHOD_UNKNOWN", f"{method_id!r} is not a registered method.")
    return ROLES[method_id], OPTIONAL.get(method_id, ())


def normalize(method_id: str, declaration: Any) -> dict[str, Any]:
    """The declaration in canonical form, or InputError. Shape: {"request": str, "range_id": str | None,
    "roles": {role: "<expression>" | {"column": c} | {"forward_return": c[, "request": r]}}}."""
    import json

    required, optional = roles_for(method_id)
    if not isinstance(declaration, dict) or set(declaration) - {"request", "range_id", "roles"}:
        raise InputError("DECLARATION_INVALID", "A declaration has request, range_id and roles only.")
    if len(json.dumps(declaration, default=str)) > MAX_DECLARATION_CHARS:
        raise InputError("DECLARATION_INVALID", f"A declaration has at most {MAX_DECLARATION_CHARS} characters.")
    request, range_id, roles = declaration.get("request"), declaration.get("range_id"), declaration.get("roles")
    if not isinstance(request, str) or not request:
        raise InputError("DECLARATION_INVALID", "request names one data request of the angle's contract.")
    if range_id is not None and not isinstance(range_id, str):
        raise InputError("DECLARATION_INVALID", "range_id is a range id of that request, or null for all of them.")
    if not isinstance(roles, dict):
        raise InputError("DECLARATION_INVALID", "roles maps each input role to its declaration.")
    unknown = sorted(set(roles) - set(required) - set(optional))
    missing = sorted(r for r in required if roles.get(r) is None)
    if unknown or missing:
        raise InputError("DECLARATION_INVALID", f"{method_id} takes the roles {list(required)}"
                         + (f" (optional {list(optional)})" if optional else "")
                         + (f"; unknown {unknown}" if unknown else "") + (f"; missing {missing}" if missing else ""))
    clean: dict[str, Any] = {}
    for role, value in roles.items():
        if value is None:
            continue
        if isinstance(value, str):
            clean[role] = value.strip()
        elif isinstance(value, dict) and set(value) in ({"column"}, {"forward_return"}, {"forward_return", "request"}) \
                and all(isinstance(v, str) and v for v in value.values()):
            kind = "column" if "column" in value else "forward_return"
            if kind == "forward_return" and role not in ("outcome", "follower"):
                raise InputError("DECLARATION_INVALID", "forward_return declares an outcome or a follower only.")
            if kind == "column" and role not in LABEL:
                raise InputError("DECLARATION_INVALID", "{'column': ...} declares a group label; use an expression "
                                                        "for a number.")
            clean[role] = {kind: value[kind]}
            if value.get("request") and value["request"] != request:
                clean[role]["request"] = value["request"]
        else:
            raise InputError("DECLARATION_INVALID", f"{role}: an expression string, {{'column': name}} or "
                                                    "{'forward_return': name} (optionally with 'request': another "
                                                    "request of the contract).")
    return {"request": request, "range_id": range_id, "roles": {r: clean[r] for r in sorted(clean)}}


def related_requests(declaration: dict[str, Any]) -> list[str]:
    """The other contract requests a normalized declaration reads (a forward return computed on another request)."""
    main = declaration.get("request")
    return sorted({spec["request"] for spec in (declaration.get("roles") or {}).values()
                   if isinstance(spec, dict) and spec.get("request") and spec["request"] != main})


def _forward_from(role: str, source: str, column: str, other: dict[str, Any], horizon: int, work) -> Any:
    """The forward return of `column` computed on another request's rows (per entity, on that request's calendar),
    matched to the rows of `work` by entity and date; NaN where the other request has no value or no later value."""
    import numpy as np
    import pandas as pd

    rows = other["rows"]
    entity_column, time_column = other.get("entity_column"), other["time_column"]
    if column not in (other.get("columns") or []) or column not in rows.columns:
        raise InputError("COLUMN_OUTSIDE_CONTRACT", f"{role}: {column!r} is not a contract column of {source}.")
    dates = pd.to_datetime(rows[time_column], errors="coerce").dt.normalize()
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    frame = pd.DataFrame({"__date": dates, "__entity": rows[entity_column].astype(str) if entity_column else "_all",
                          "__value": pd.to_numeric(rows[column], errors="coerce").astype("float64")})
    frame = frame[frame["__date"].notna()].sort_values(["__entity", "__date"], kind="mergesort")
    if frame.duplicated(["__entity", "__date"]).any():
        raise InputError("DUPLICATE_ENTITY_DATE", f"{role}: {source} has more than one row per entity and date, so a "
                                                  "forward return is ambiguous; narrow that request's scope.")
    now = frame["__value"].to_numpy(dtype="float64")
    later = frame.groupby("__entity", sort=False)["__value"].shift(-max(1, int(horizon))).to_numpy(dtype="float64")
    with np.errstate(all="ignore"):
        ratio = np.where((now > 0) & np.isfinite(now) & np.isfinite(later), later / now - 1.0, np.nan)
    lookup = pd.Series(ratio, index=pd.MultiIndex.from_arrays([frame["__entity"], frame["__date"]]))
    keys = pd.MultiIndex.from_arrays([work["__entity"], work["__date"]])
    return lookup.reindex(keys).to_numpy(dtype="float64")


def outcome_problem(method_id: str, frame, unit: str) -> str | None:
    """A reason when an angle's outcome (or follower) cannot be the approved return: its median absolute value is
    implausible for the approved unit (above 100 for PERCENT, above 1 for DECIMAL). Found live (suite20, S15): three
    angles were SUPPORTED on the closing price level (median about 1,400) recorded as a PERCENT outcome."""
    import numpy as np
    import pandas as pd

    if unit not in ("PERCENT", "DECIMAL"):
        return None
    limit = 100.0 if unit == "PERCENT" else 1.0
    for role in ("outcome", "follower"):
        if role not in ROLES.get(method_id, ()) or role not in getattr(frame, "columns", []):
            continue
        values = pd.to_numeric(frame[role], errors="coerce").to_numpy(dtype="float64")
        values = values[np.isfinite(values)]
        if len(values) and float(np.median(np.abs(values))) > limit:
            return (f"{role}: its median absolute value is {float(np.median(np.abs(values))):.6g}, not a return in "
                    f"{unit} (a price or a level, not the approved forward return). Declare it as "
                    "{'forward_return': '<price column>'} (with 'request' when the price is in another request).")
    return None


def build(method_id: str, declaration: dict[str, Any], rows, *, entity_column: str | None, time_column: str,
          columns: list[str], windows: list[tuple[str, str]], horizon: int, unit: str,
          related: dict[str, dict[str, Any]] | None = None) -> tuple[Any, dict[str, Any]]:
    """(canonical frame for research_engines, info). rows: every delivered row of the request (buffers included);
    columns: the contract columns the declaration may use; windows: the (start, end) dates analysed; related: the
    other contract requests a forward return reads, {request id: {rows, entity_column, time_column, columns}}."""
    import numpy as np
    import pandas as pd

    declaration = normalize(method_id, declaration)
    roles = declaration["roles"]
    missing = [c for c in [time_column, *( [entity_column] if entity_column else [])] if c not in rows.columns]
    if missing:
        raise InputError("INPUT_COLUMNS_MISSING", f"The request rows lack {missing}.")
    work = rows.copy()
    work["__date"] = pd.to_datetime(work[time_column], errors="coerce").dt.normalize()
    if getattr(work["__date"].dt, "tz", None) is not None:
        work["__date"] = work["__date"].dt.tz_localize(None)
    work["__entity"] = work[entity_column].astype(str) if entity_column else "_all"
    work = work[work["__date"].notna()].sort_values(["__entity", "__date"], kind="mergesort").reset_index(drop=True)
    positions = work.groupby("__entity", sort=True).indices
    groups = [np.asarray(index, dtype=int) for index in positions.values()]
    allowed = set(columns)
    numeric: dict[str, Any] = {}
    for column in columns:
        if column in work.columns and column not in (entity_column, time_column):
            values = pd.to_numeric(work[column], errors="coerce") if not pd.api.types.is_bool_dtype(work[column]) \
                else work[column].astype("float64")
            numeric[column] = values.to_numpy(dtype="float64")
    out: dict[str, Any] = {}
    info: dict[str, Any] = {"expressions": {}, "forward_horizon": None, "censored_outcome_rows": 0}
    _expression = _expression_module()
    for role in ORDER:
        spec = roles.get(role)
        if spec is None:
            continue
        if isinstance(spec, str):
            names = allowed | {r for r in ("signal", "leader", "follower", "state") if r in out and r not in LABEL}
            try:
                analysed = _expression.analyze(spec, names)
            except _expression.ExpressionError as exc:
                raise InputError("EXPRESSION_INVALID", f"{role}: {exc}") from None
            values = {**numeric, **{r: out[r] for r in ("signal", "leader", "follower", "state") if r in out}}
            missing_columns = sorted(n for n in analysed.names if n not in values)
            if missing_columns:
                raise InputError("COLUMN_OUTSIDE_CONTRACT", f"{role}: {missing_columns} are not delivered columns of "
                                                            "this request.")
            out[role] = _expression.evaluate(spec, {n: values[n] for n in analysed.names} or
                                             {"__n": np.zeros(len(work))}, groups)
            info["expressions"][role] = {"expression": spec, "warmup_observations": analysed.warmup}
        elif "column" in spec:
            column = spec["column"]
            if column not in allowed or column not in work.columns:
                raise InputError("COLUMN_OUTSIDE_CONTRACT", f"{role}: {column!r} is not a contract column of this "
                                                            "request.")
            out[role] = work[column].map(lambda v: None if v is None or (isinstance(v, float) and v != v)
                                         else str(v)).to_numpy(dtype=object)
        else:
            column = spec["forward_return"]
            h = max(1, int(horizon))
            source = spec.get("request")
            if source:
                other = (related or {}).get(source)
                if other is None:
                    raise InputError("REQUEST_OUTSIDE_CONTRACT", f"{role}: {source!r} is not a data request of this "
                                                                 "angle's contract.")
                if bool(other.get("entity_column")) != bool(entity_column):
                    raise InputError("ENTITY_MISMATCH", f"{role}: {source} and {declaration['request']} must both "
                                                        "have an entity column, or neither.")
                forward = _forward_from(role, source, column, other, h, work)
            else:
                if column not in numeric or column not in allowed:
                    raise InputError("COLUMN_OUTSIDE_CONTRACT", f"{role}: {column!r} is not a numeric contract column "
                                                                "of this request (another request's price column: add "
                                                                "'request': '<its data_request_id>').")
                value = numeric[column]
                forward = np.full(len(work), np.nan)
                for index in groups:
                    series = value[index]
                    if len(series) > h:
                        with np.errstate(all="ignore"):
                            now, later = series[:-h], series[h:]
                            ratio = np.where((now > 0) & np.isfinite(now) & np.isfinite(later), later / now - 1.0,
                                             np.nan)
                        forward[index[:-h]] = ratio
            out[role] = forward * (100.0 if unit == "PERCENT" else 1.0)
            info["forward_horizon"] = h
    frame = pd.DataFrame({"date": work["__date"], "entity": work["__entity"]})
    for role, values in out.items():
        if role in BOOLEAN:
            frame[role] = pd.Series([None if not np.isfinite(v) else bool(v != 0) for v in values], dtype="object")
        elif role in LABEL and values.dtype == object:
            frame[role] = values
        else:
            frame[role] = values
    inside = np.zeros(len(frame), dtype=bool)
    for start, end in windows:
        inside |= ((frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))).to_numpy()
    frame = frame[inside].reset_index(drop=True)
    if "outcome" in roles and isinstance(roles["outcome"], dict) and "forward_return" in roles["outcome"]:
        info["censored_outcome_rows"] = int(frame["outcome"].isna().sum())
    if "follower" in roles and isinstance(roles["follower"], dict) and "forward_return" in roles["follower"]:
        info["censored_outcome_rows"] = int(frame["follower"].isna().sum())
    info["rows"] = int(len(frame))
    info["declaration"] = declaration
    info["outcome_source"] = outcome_source(declaration)
    return frame, info


def outcome_source(declaration: dict[str, Any] | None) -> str:
    """How the outcome (or follower) of a recorded input was obtained: FORWARD_RETURN (computed by the backend),
    EXPRESSION (a declared expression) or FRAME (built by the model's code)."""
    if not declaration:
        return "FRAME"
    roles = declaration.get("roles") or {}
    spec = roles.get("outcome", roles.get("follower"))
    return "FORWARD_RETURN" if isinstance(spec, dict) and "forward_return" in spec else "EXPRESSION"
