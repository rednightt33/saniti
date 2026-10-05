"""Trade simulation (P32 layer 3, plan 2026-10-05): the backtest a strategy question asks for, on the governed prices,
with the conventions written down and the statistics over the approved period only.

Shared by saniti.backtest (in the session) and app/backtest_validation.py (the backend's recomputation at
complete_analysis), so the released tables can be checked against the bundle files. The model supplies only the
signal dates (and exit-signal dates); prices always come from the bundle.

Conventions (as TradingView's strategy tester, QuantConnect and Backtrader; reported with every result):
- long only, one position per entity at a time; a signal while a position is open is skipped (IN_POSITION);
- an entry signal on bar t enters at the open of bar t+1; an exit signal on bar t exits at the open of bar t+1;
- stop and target are checked on every bar from the entry bar: a bar that opens beyond a level fills at its open (a
  gap), otherwise at the level; when the stop and the target are both inside one bar, the stop is taken first;
- max_hold closes the position at the close of its max_hold-th bar;
- only bars inside an approved range trade: buffer bars (warm-up history, forward outcomes) feed indicators only; a
  position still open at the end of a range closes at that range's last close (OPEN_AT_END);
- a trade's return is exit * (1 - fee) / (entry * (1 + fee)) - 1 (fee per side, a fraction).
"""
from __future__ import annotations

import math
from typing import Any

VERSION = 1
CONVENTIONS = ("long only, one position per entity; entry and exit signals fill at the next bar's open; stop and "
               "target from the entry bar, a gap fills at the open, stop first when both are inside one bar; "
               "max_hold closes at the close of its last bar; only bars inside the approved ranges trade, a position "
               "open at a range's end closes at its last close (OPEN_AT_END); return = exit*(1-fee)/(entry*(1+fee))-1")
TRADE_COLUMNS = ("entity", "range_id", "signal_date", "entry_date", "entry_price", "exit_date", "exit_price",
                 "exit_reason", "bars_held", "return")
SUMMARY_COLUMNS = ("entity", "signals", "signals_skipped", "trades", "wins", "win_rate", "mean_return",
                   "median_return", "average_win", "average_loss", "realized_reward_risk", "profit_factor",
                   "cumulative_return", "max_drawdown", "bars_in_period", "bars_buffer", "first_date", "last_date")
COUNT_COLUMNS = ("signals", "signals_skipped", "trades", "wins", "bars_in_period", "bars_buffer")
RETURN_COLUMNS = ("return",)
SUMMARY_RETURN_COLUMNS = ("mean_return", "median_return", "average_win", "average_loss", "cumulative_return",
                          "max_drawdown")
EXIT_REASONS = ("STOP", "TARGET", "EXIT_SIGNAL", "MAX_HOLD", "OPEN_AT_END")
VALUE_UNITS = {"PERCENT": "PERCENT", "DECIMAL": "FRACTION"}
ALL = "ALL"


class BacktestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parameters(stop: float | None, target: float | None, max_hold: int | None, fee: float | None,
               unit: str | None) -> dict[str, Any]:
    """The checked parameters: stop and target are fractions of the entry price (0.05 = 5%)."""
    for name, value in (("stop", stop), ("target", target)):
        if value is not None and not (isinstance(value, (int, float)) and 0 < float(value) < 1):
            raise BacktestError("PARAMETER_INVALID", f"{name} is a fraction of the entry price between 0 and 1 "
                                                     f"(0.05 for 5%), got {value!r}.")
    if max_hold is not None and not (isinstance(max_hold, int) and max_hold >= 1):
        raise BacktestError("PARAMETER_INVALID", f"max_hold is a whole number of bars (>= 1), got {max_hold!r}.")
    if fee is not None and not (isinstance(fee, (int, float)) and 0 <= float(fee) < 0.1):
        raise BacktestError("PARAMETER_INVALID", f"fee is a fraction per side (0.0015 for 0.15%), got {fee!r}.")
    unit = unit or "PERCENT"
    if unit not in VALUE_UNITS:
        raise BacktestError("PARAMETER_INVALID", "unit is PERCENT or DECIMAL.")
    return {"stop": None if stop is None else float(stop), "target": None if target is None else float(target),
            "max_hold": max_hold, "fee": float(fee or 0.0), "unit": unit}


def summary_units(unit: str) -> dict[str, str]:
    return {**{c: VALUE_UNITS[unit] for c in SUMMARY_RETURN_COLUMNS}, "win_rate": "FRACTION"}


def trades_units(unit: str) -> dict[str, str]:
    return {"return": VALUE_UNITS[unit]}


def _day(value: Any) -> str:
    import pandas as pd

    return pd.Timestamp(value).date().isoformat()


def simulate(prices, *, entity_column: str | None, time_column: str, columns: dict[str, str],
             ranges: list[dict[str, Any]], signals: set[tuple[str, str]], exits: set[tuple[str, str]],
             params: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(trades, summary rows) from a price frame and the (entity, date) pairs of the entry and exit signals."""
    import pandas as pd

    frame = prices.copy()
    frame["_date"] = pd.to_datetime(frame[time_column]).dt.normalize()
    frame["_entity"] = frame[entity_column].astype(str) if entity_column else ALL
    for role in ("open", "high", "low", "close"):
        if columns.get(role) not in frame.columns:
            raise BacktestError("PRICE_COLUMN_MISSING", f"The {role} price column {columns.get(role)!r} is not in "
                                                        "the request; pass prices={'open': ..., 'high': ..., "
                                                        "'low': ..., 'close': ...}.")
    frame = frame.sort_values(["_entity", "_date"]).drop_duplicates(["_entity", "_date"], keep="last")
    fee, unit = params["fee"], params["unit"]
    scale = 100.0 if unit == "PERCENT" else 1.0
    trades: list[dict[str, Any]] = []
    stats: dict[str, dict[str, Any]] = {}
    windows = [(w["range_id"], pd.Timestamp(w["start"]), pd.Timestamp(w["end"])) for w in ranges]
    for entity, rows in frame.groupby("_entity", sort=True):
        inside_any = pd.Series(False, index=rows.index)
        for _, start, end in windows:
            inside_any |= (rows["_date"] >= start) & (rows["_date"] <= end)
        entry = stats.setdefault(entity, {"signals": 0, "signals_skipped": 0, "bars_in_period": int(inside_any.sum()),
                                          "bars_buffer": int((~inside_any).sum()), "first_date": None,
                                          "last_date": None})
        if inside_any.any():
            entry["first_date"] = _day(rows.loc[inside_any, "_date"].min())
            entry["last_date"] = _day(rows.loc[inside_any, "_date"].max())
        for range_id, start, end in windows:
            bars = rows[(rows["_date"] >= start) & (rows["_date"] <= end)]
            dates = [_day(d) for d in bars["_date"]]
            o, h, lo, c = (bars[columns[k]].astype(float).tolist() for k in ("open", "high", "low", "close"))
            n = len(dates)
            position: dict[str, Any] | None = None
            pending_entry: str | None = None
            pending_exit = False

            def close(k: int, price: float, reason: str) -> None:
                assert position is not None
                ret = price * (1 - fee) / (position["entry_price"] * (1 + fee)) - 1
                trades.append({"entity": entity, "range_id": range_id, "signal_date": position["signal_date"],
                               "entry_date": position["entry_date"], "entry_price": position["entry_price"],
                               "exit_date": dates[k], "exit_price": float(price), "exit_reason": reason,
                               "bars_held": k - position["k"] + 1, "return": ret * scale})

            for k in range(n):
                if position is not None and pending_exit:
                    close(k, o[k], "EXIT_SIGNAL")
                    position, pending_exit = None, False
                if position is None and pending_entry is not None:
                    position = {"k": k, "entry_date": dates[k], "entry_price": float(o[k]),
                                "signal_date": pending_entry}
                    pending_entry = None
                if position is not None:
                    stop = position["entry_price"] * (1 - params["stop"]) if params["stop"] is not None else None
                    target = position["entry_price"] * (1 + params["target"]) if params["target"] is not None \
                        else None
                    hit = None
                    if stop is not None and o[k] <= stop:
                        hit = (o[k], "STOP")
                    elif target is not None and o[k] >= target:
                        hit = (o[k], "TARGET")
                    elif stop is not None and lo[k] <= stop:
                        hit = (stop, "STOP")
                    elif target is not None and h[k] >= target:
                        hit = (target, "TARGET")
                    if hit is not None:
                        close(k, hit[0], hit[1])
                        position = None
                    elif params["max_hold"] is not None and k - position["k"] + 1 >= params["max_hold"]:
                        close(k, c[k], "MAX_HOLD")
                        position = None
                    elif (entity, dates[k]) in exits and k + 1 < n:
                        pending_exit = True
                if (entity, dates[k]) in signals:
                    entry["signals"] += 1
                    if position is not None or pending_entry is not None or k + 1 >= n:
                        entry["signals_skipped"] += 1
                    else:
                        pending_entry = dates[k]
            if position is not None:
                close(n - 1, c[n - 1], "OPEN_AT_END")
    summary = [_summary(entity, [t for t in trades if t["entity"] == entity], stats[entity], scale)
               for entity in sorted(stats)]
    if len(summary) > 1:
        total = {k: sum(s[k] for s in stats.values()) for k in ("signals", "signals_skipped", "bars_in_period",
                                                                 "bars_buffer")}
        firsts = [s["first_date"] for s in stats.values() if s["first_date"]]
        lasts = [s["last_date"] for s in stats.values() if s["last_date"]]
        total.update(first_date=min(firsts) if firsts else None, last_date=max(lasts) if lasts else None)
        row = _summary(ALL, trades, total, scale)
        row["cumulative_return"] = row["max_drawdown"] = None  # compounding across entities has no single order
        summary.append(row)
    return trades, summary


def _summary(entity: str, trades: list[dict[str, Any]], stats: dict[str, Any], scale: float) -> dict[str, Any]:
    import statistics

    returns = [t["return"] / scale for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for t in sorted(trades, key=lambda t: (t["exit_date"], t["entry_date"])):
        equity *= 1 + t["return"] / scale
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)

    def pct(value: float | None) -> float | None:
        return None if value is None else value * scale

    return {"entity": entity, "signals": stats["signals"], "signals_skipped": stats["signals_skipped"],
            "trades": len(trades), "wins": len(wins), "win_rate": len(wins) / len(trades) if trades else None,
            "mean_return": pct(statistics.fmean(returns)) if returns else None,
            "median_return": pct(statistics.median(returns)) if returns else None,
            "average_win": pct(statistics.fmean(wins)) if wins else None,
            "average_loss": pct(statistics.fmean(losses)) if losses else None,
            "realized_reward_risk": statistics.fmean(wins) / abs(statistics.fmean(losses)) if wins and losses
            else None,
            "profit_factor": sum(wins) / abs(sum(losses)) if wins and losses else None,
            "cumulative_return": pct(equity - 1) if trades else None, "max_drawdown": pct(drawdown) if trades
            else None, "bars_in_period": stats["bars_in_period"], "bars_buffer": stats["bars_buffer"],
            "first_date": stats["first_date"], "last_date": stats["last_date"]}


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def compare(released: list[dict[str, Any]], recomputed: list[dict[str, Any]], key: str, columns: tuple[str, ...],
            rtol: float = 1e-9, atol: float = 1e-12) -> list[dict[str, Any]]:
    """The cells of a released table that differ from the recomputed rows (same row order; numbers within rtol)."""
    mismatches = []
    if len(released) != len(recomputed):
        mismatches.append({"row": None, "column": "rows", "expected": len(recomputed), "actual": len(released)})
    for i, (got, want) in enumerate(zip(released, recomputed)):
        for column in columns:
            a, b = got.get(column), want.get(column)
            if _missing(a) or _missing(b):
                same = _missing(a) and _missing(b)
            elif isinstance(b, (int, float)) and not isinstance(b, bool):
                same = math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=atol)
            elif column.endswith("date"):
                same = str(a)[:10] == str(b)[:10]
            else:
                same = a == b
            if not same:
                mismatches.append({"row": i, key: want.get(key), "column": column, "expected": b, "actual": a})
    return mismatches
