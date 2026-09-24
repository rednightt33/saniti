"""Restricted arithmetic expressions for CUSTOM calculations.

A CUSTOM calculation may carry an `expression`. The harness parses it when the spec is reviewed
(`analyze`), and the validator evaluates it independently of the analysis code (`evaluate`), so a
niche formula can be recalculated like a registered method.

Grammar (Python expression syntax, nothing else):
    numbers; names (the calculation's input columns, or ids of earlier calculations);
    + - * / **, unary -, comparisons (< <= > >= == !=), & | ~ (and, or, not);
    abs(x) log(x) exp(x) sqrt(x) sign(x) min(a, b) max(a, b) where(condition, a, b);
    lag(x, k)          value k observations earlier for the same entity (k >= 1, past only);
    rolling_sum(x, n)  trailing sum of n observations of the same entity, including the current one;
    rolling_mean(x, n) trailing mean of n observations, including the current one.

Every value at t depends only on observations at or before t of the same entity, so an expression
can never look ahead. Undefined inputs propagate; a zero denominator follows the declared policy
(NULL by default); log, sqrt and powers outside their domain are undefined.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

MAX_LENGTH = 500
MAX_NODES = 200
MAX_DEPTH = 20
MAX_LAG = 1000
ELEMENTWISE = {"abs": 1, "log": 1, "exp": 1, "sqrt": 1, "sign": 1, "min": 2, "max": 2, "where": 3}
WINDOWED = {"lag", "rolling_sum", "rolling_mean"}
BINARY = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "**", ast.BitAnd: "&", ast.BitOr: "|"}
COMPARE = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}


class ExpressionError(ValueError):
    pass


@dataclass
class Info:
    names: set[str] = field(default_factory=set)
    warmup: int = 0  # observations of history the expression needs before its first defined value


def _parse(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ExpressionError("expression is empty")
    if len(expression) > MAX_LENGTH:
        raise ExpressionError(f"expression exceeds {MAX_LENGTH} characters")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"expression is not valid syntax ({exc.msg})") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ExpressionError(f"expression has more than {MAX_NODES} elements")
    return tree


def _window_argument(node: ast.expr, name: str) -> int:
    if not (isinstance(node, ast.Constant) and type(node.value) is int):
        raise ExpressionError(f"the second argument of {name} must be an integer literal")
    value = node.value
    if not 1 <= value <= MAX_LAG:
        raise ExpressionError(f"the second argument of {name} must be between 1 and {MAX_LAG}")
    return value


def analyze(expression: str, allowed: set[str]) -> Info:
    """Validate an expression against the names it may use; return its names and warm-up need."""
    tree = _parse(expression)
    info = Info()

    def visit(node: ast.AST, depth: int) -> int:
        if depth > MAX_DEPTH:
            raise ExpressionError(f"expression nests deeper than {MAX_DEPTH} levels")
        if isinstance(node, ast.Expression):
            return visit(node.body, depth + 1)
        if isinstance(node, ast.Constant):
            if type(node.value) not in (int, float):
                raise ExpressionError("only numeric constants are allowed")
            return 0
        if isinstance(node, ast.Name):
            if node.id not in allowed:
                raise ExpressionError(f"unknown name {node.id!r}; use the calculation's input columns or earlier "
                                      f"calculation ids ({', '.join(sorted(allowed)) or 'none'})")
            info.names.add(node.id)
            return 0
        if isinstance(node, ast.BinOp):
            if type(node.op) not in BINARY:
                raise ExpressionError(f"operator {type(node.op).__name__} is not allowed")
            return max(visit(node.left, depth + 1), visit(node.right, depth + 1))
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert)):
                raise ExpressionError(f"operator {type(node.op).__name__} is not allowed")
            return visit(node.operand, depth + 1)
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or type(node.ops[0]) not in COMPARE:
                raise ExpressionError("use one comparison at a time (combine with & and |)")
            return max(visit(node.left, depth + 1), visit(node.comparators[0], depth + 1))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise ExpressionError("only allowlisted functions with positional arguments may be called")
            name = node.func.id
            if name in WINDOWED:
                if len(node.args) != 2:
                    raise ExpressionError(f"{name} takes (x, n)")
                size = _window_argument(node.args[1], name)
                inner = visit(node.args[0], depth + 1)
                return inner + (size if name == "lag" else size - 1)
            if name in ELEMENTWISE:
                if len(node.args) != ELEMENTWISE[name]:
                    raise ExpressionError(f"{name} takes {ELEMENTWISE[name]} argument(s)")
                return max(visit(arg, depth + 1) for arg in node.args)
            raise ExpressionError(f"function {name!r} is not allowed ({', '.join(sorted(ELEMENTWISE) + sorted(WINDOWED))})")
        raise ExpressionError(f"{type(node).__name__} is not allowed in an expression")

    info.warmup = visit(tree, 0)
    return info


# ---------------------------------------------------------------- units

ANY_UNIT = "*"


def unit_conflicts(expression: str, units: dict[str, str | None]) -> list[str]:
    """Additions, subtractions, comparisons, min/max and where-branches between values of different known units
    (for example IDR + lots). Unknown units (None) are never reported."""
    tree = _parse(expression)
    conflicts: list[str] = []

    def combine(a: str | None, b: str | None, where: str) -> str | None:
        known = [u for u in (a, b) if u not in (None, ANY_UNIT)]
        if len(known) == 2 and known[0].strip().lower() != known[1].strip().lower():
            conflicts.append(f"{where}: {known[0]} vs {known[1]}")
        if known:
            return known[0]
        return ANY_UNIT if a == b == ANY_UNIT else None

    def visit(node: ast.AST) -> str | None:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return ANY_UNIT
        if isinstance(node, ast.Name):
            return units.get(node.id)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                return combine(left, right, ast.unparse(node))
            if isinstance(node.op, ast.Mult):
                return left if right == ANY_UNIT else right if left == ANY_UNIT else None
            if isinstance(node.op, ast.Div):
                if left not in (None, ANY_UNIT) and right not in (None, ANY_UNIT) and \
                        left.strip().lower() == right.strip().lower():
                    return "ratio"
                return left if right == ANY_UNIT else None
            return None
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            return None if isinstance(node.op, ast.Invert) else value
        if isinstance(node, ast.Compare):
            combine(visit(node.left), visit(node.comparators[0]), ast.unparse(node))
            return None
        if isinstance(node, ast.Call):
            name = node.func.id
            if name in WINDOWED:
                return visit(node.args[0])
            args = [visit(arg) for arg in node.args]
            if name in ("abs", "sign"):
                return args[0] if name == "abs" else None
            if name in ("min", "max"):
                return combine(args[0], args[1], ast.unparse(node))
            if name == "where":
                return combine(args[1], args[2], ast.unparse(node))
            return None
        return None

    visit(tree)
    return conflicts


# ---------------------------------------------------------------- evaluation (validator side)

def evaluate(expression: str, columns: dict[str, Any], groups: list[Any], zero_denominator: str = "NULL") -> Any:
    """Evaluate over rows sorted by entity and date.

    columns: name -> float array over all rows; groups: index arrays of each entity's rows in date order.
    """
    import numpy as np

    tree = _parse(expression)
    n = len(next(iter(columns.values()))) if columns else (int(max((g.max() for g in groups if len(g)), default=-1)) + 1)

    def per_group(x: Any, fn) -> Any:
        out = np.full(n, np.nan)
        for index in groups:
            if len(index):
                out[index] = fn(x[index])
        return out

    def lag(x: Any, k: int) -> Any:
        def shift(values: Any) -> Any:
            out = np.full(len(values), np.nan)
            if len(values) > k:
                out[k:] = values[:-k]
            return out
        return per_group(x, shift)

    def rolling(x: Any, size: int, mean: bool) -> Any:
        from numpy.lib.stride_tricks import sliding_window_view

        def window(values: Any) -> Any:
            out = np.full(len(values), np.nan)
            if len(values) >= size:
                sums = sliding_window_view(values, size).sum(axis=1)  # NaN inside a window propagates
                out[size - 1:] = sums / size if mean else sums
            return out
        return per_group(x, window)

    def truth(x: Any) -> Any:
        return np.where(np.isnan(x), np.nan, (x != 0).astype(float))

    def clean(x: Any) -> Any:
        x = np.asarray(x, dtype=float)
        if x.ndim == 0:
            x = np.full(n, float(x))
        x = x.copy()
        x[~np.isfinite(x)] = np.nan
        return x

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return np.full(n, float(node.value))
        if isinstance(node, ast.Name):
            return np.asarray(columns[node.id], dtype=float)
        with np.errstate(all="ignore"):
            if isinstance(node, ast.BinOp):
                left, right = visit(node.left), visit(node.right)
                op = type(node.op)
                if op is ast.Add:
                    return clean(left + right)
                if op is ast.Sub:
                    return clean(left - right)
                if op is ast.Mult:
                    return clean(left * right)
                if op is ast.Div:
                    zero = right == 0
                    out = clean(np.divide(left, np.where(zero, np.nan, right)))
                    if zero_denominator == "ZERO":
                        out = np.where(zero & ~np.isnan(left), 0.0, out)
                    return out
                if op is ast.Pow:
                    return clean(np.power(left, right))
                both = np.isnan(left) | np.isnan(right)
                value = (left != 0) & (right != 0) if op is ast.BitAnd else (left != 0) | (right != 0)
                return np.where(both, np.nan, value.astype(float))
            if isinstance(node, ast.UnaryOp):
                value = visit(node.operand)
                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.UAdd):
                    return value
                return np.where(np.isnan(value), np.nan, (value == 0).astype(float))
            if isinstance(node, ast.Compare):
                left, right = visit(node.left), visit(node.comparators[0])
                op = type(node.ops[0])
                value = {ast.Lt: left < right, ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right,
                         ast.Eq: left == right, ast.NotEq: left != right}[op]
                return np.where(np.isnan(left) | np.isnan(right), np.nan, value.astype(float))
            if isinstance(node, ast.Call):
                name = node.func.id
                if name in WINDOWED:
                    size = node.args[1].value
                    inner = visit(node.args[0])
                    return lag(inner, size) if name == "lag" else rolling(inner, size, name == "rolling_mean")
                args = [visit(arg) for arg in node.args]
                if name == "abs":
                    return np.abs(args[0])
                if name == "log":
                    return clean(np.where(args[0] > 0, np.log(np.where(args[0] > 0, args[0], 1.0)), np.nan))
                if name == "exp":
                    return clean(np.exp(args[0]))
                if name == "sqrt":
                    return clean(np.where(args[0] >= 0, np.sqrt(np.where(args[0] >= 0, args[0], 0.0)), np.nan))
                if name == "sign":
                    return np.sign(args[0])
                if name in ("min", "max"):
                    pick = np.minimum if name == "min" else np.maximum
                    return pick(args[0], args[1])  # NaN propagates
                condition = truth(args[0])
                return np.where(np.isnan(condition), np.nan, np.where(condition == 1.0, args[1], args[2]))
        raise ExpressionError(f"{type(node).__name__} is not allowed in an expression")

    return clean(visit(tree))
