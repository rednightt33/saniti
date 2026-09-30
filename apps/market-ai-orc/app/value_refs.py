"""Value references (AI_ENABLE_VALUE_REFERENCES; ERRORS_AND_SOLUTIONS P11, user decision 2026-09-30).

The number-provenance gate read every figure back out of free text, so each new way a model writes a number needed
another parser rule (suite20b: "0,99" truncated from 0.9955, "95%", "10 miliar"), and a figure written in words was
never checked at all. With value references the model does not type a data figure: it writes a reference to the
backend value, and this module fills it in, formatted by code.

    {{finding.near_high_depth.estimates.primary.estimate|pp:2}}   a backend finding of complete_research_run
    {{out.out_2940d0.rows.3.mean_return|pct:1}}                  a released output (rows by index)
    {{out.out_2940d0.rows[ticker=BBRI].close|rp}}                 ... or the first row whose column has that value
    {{fact.1|int}}                                                a lookup_fact value
    {{diff(finding.a.estimates.primary.ci.1, finding.a.estimates.primary.ci.0)|dec:2}}

Namespaces are registered by the orchestrator from tool results the application received (never from the model),
each with its evidence label. A resolved value is added to the provenance sources under that label, so the gates run
unchanged on the rendered text; a derived value (diff, abs, ratio, chg) carries the weakest label of its inputs.

Formats (Indonesian: decimal comma, thousands dot): auto (default), dec:N, int, pct:N (a fraction shown as percent),
pctv:N (already a percent), pp:N (percentage points), rp (rupiah scaled to ribu/juta/miliar/triliun), x:N ("kali").
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .provenance import LABEL_ORDER

REF_RE = re.compile(r"\{\{\s*(?P<expr>[^{}|]+?)\s*(?:\|\s*(?P<fmt>[a-z]+)\s*(?::\s*(?P<places>\d)\s*)?)?\}\}")
FUNC_RE = re.compile(r"^(?P<name>diff|abs|ratio|chg)\s*\((?P<args>.*)\)$", re.DOTALL)
SELECTOR_RE = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<column>[^=\[\]]+)=(?P<value>[^\]]+)\]$")
FORMATS = {"auto", "dec", "int", "pct", "pctv", "pp", "rp", "x"}
FUNCTION_ARITY = {"diff": 2, "abs": 1, "ratio": 2, "chg": 2}
MINUS = "−"
UNRESOLVED = "[nilai tidak tersedia]"


class ReferenceError_(ValueError):
    """A reference that cannot be resolved; the message names what is available instead."""


@dataclass
class Resolved:
    value: float
    label: str


@dataclass
class ReferenceSources:
    """namespace -> key -> (object, evidence label)."""

    objects: dict[str, dict[str, tuple[Any, str]]] = field(default_factory=dict)

    def add(self, namespace: str, key: str, value: Any, label: str) -> None:
        self.objects.setdefault(namespace, {})[str(key)] = (value, label)

    def __bool__(self) -> bool:
        return any(self.objects.values())

    def keys(self, namespace: str) -> list[str]:
        return sorted(self.objects.get(namespace, {}))

    def lookup(self, path: str) -> Resolved:
        parts = [p for p in _split(path.strip())]
        if len(parts) < 2:
            raise ReferenceError_(f"'{path}' needs a namespace and a key, for example finding.<angle_id>.<field>")
        namespace, key, rest = parts[0], parts[1], parts[2:]
        if namespace not in self.objects:
            raise ReferenceError_(f"'{path}': unknown namespace {namespace!r}; this run has "
                                  f"{sorted(n for n in self.objects if self.objects[n]) or 'no referable values'}")
        entry = self.objects[namespace].get(key)
        if entry is None:
            raise ReferenceError_(f"'{path}': {namespace}.{key} does not exist; available: "
                                  f"{', '.join(self.keys(namespace)[:12])}")
        value, label = entry
        walked = f"{namespace}.{key}"
        for part in rest:
            value, walked = _step(value, part, walked, path)
        number = _number(value)
        if number is None:
            raise ReferenceError_(f"'{path}' is not a number ({type(value).__name__}"
                                  + (f"; its fields: {', '.join(list(value)[:12])}" if isinstance(value, dict) else "")
                                  + ")")
        return Resolved(number, label)


def _split(path: str) -> list[str]:
    """Dot-separated segments; dots inside a [column=value] selector stay in their segment."""
    parts, depth, current = [], 0, ""
    for char in path:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == "." and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def _step(value: Any, part: str, walked: str, path: str) -> tuple[Any, str]:
    selector = SELECTOR_RE.match(part)
    if selector:
        items, walked = _step(value, selector.group("key").strip(), walked, path)
        column, wanted = selector.group("column").strip(), selector.group("value").strip().strip("'\"")
        if not isinstance(items, list):
            raise ReferenceError_(f"'{path}': {walked} is not a list of rows")
        for row in items:
            if isinstance(row, dict) and str(row.get(column)) == wanted:
                return row, f"{walked}[{column}={wanted}]"
        seen = sorted({str(row.get(column)) for row in items if isinstance(row, dict)})[:12]
        raise ReferenceError_(f"'{path}': no row of {walked} has {column}={wanted}; values: {', '.join(seen)}")
    if isinstance(value, dict):
        if part not in value:
            raise ReferenceError_(f"'{path}': {walked} has no field {part!r}; its fields: "
                                  f"{', '.join(list(value)[:15])}")
        return value[part], f"{walked}.{part}"
    if isinstance(value, list):
        if not part.lstrip("-").isdigit() or not -len(value) <= int(part) < len(value):
            raise ReferenceError_(f"'{path}': {walked} is a list of {len(value)} items; use an index 0 to "
                                  f"{len(value) - 1} or a [column=value] selector")
        return value[int(part)], f"{walked}.{part}"
    raise ReferenceError_(f"'{path}': {walked} is a value, it has no field {part!r}")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def weakest(labels: list[str]) -> str:
    known = [label for label in labels if label in LABEL_ORDER]
    return max(known, key=LABEL_ORDER.index) if known else (labels[0] if labels else "CONTEXT")


def evaluate(expression: str, sources: ReferenceSources) -> Resolved:
    call = FUNC_RE.match(expression.strip())
    if not call:
        return sources.lookup(expression)
    name = call.group("name")
    args = [a.strip() for a in _split_args(call.group("args"))]
    if len(args) != FUNCTION_ARITY[name]:
        raise ReferenceError_(f"{name}() takes {FUNCTION_ARITY[name]} reference(s), got {len(args)}")
    values = [sources.lookup(a) for a in args]
    label = weakest([v.label for v in values])
    x = values[0].value
    if name == "abs":
        return Resolved(abs(x), label)
    y = values[1].value
    if name == "diff":
        return Resolved(x - y, label)
    if y == 0:
        raise ReferenceError_(f"{name}(): the second value is zero")
    return Resolved(x / y if name == "ratio" else (x - y) / y, label)


def _split_args(text: str) -> list[str]:
    args, depth, current = [], 0, ""
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        if char == "," and depth == 0:
            args.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        args.append(current)
    return args


def _grouped(value: float, places: int) -> str:
    text = f"{abs(value):,.{places}f}"  # 1,234.56
    text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return (MINUS if value < 0 and float(text.replace(".", "").replace(",", ".")) != 0 else "") + text


def format_value(value: float, fmt: str | None = None, places: int | None = None) -> str:
    """The value in Indonesian notation; every output reads back through provenance.parse_numbers."""
    fmt = fmt or "auto"
    if fmt not in FORMATS:
        raise ReferenceError_(f"unknown format {fmt!r}; use one of {', '.join(sorted(FORMATS))}")
    if fmt == "int":
        return _grouped(round(value), 0)
    if fmt == "dec":
        return _grouped(value, 2 if places is None else places)
    if fmt == "pct":
        return _grouped(value * 100, 2 if places is None else places) + "%"
    if fmt == "pctv":
        return _grouped(value, 2 if places is None else places) + "%"
    if fmt == "pp":
        return _grouped(value, 2 if places is None else places) + " pp"
    if fmt == "x":
        return _grouped(value, 2 if places is None else places) + " kali"
    if fmt == "rp":
        for factor, unit in ((1e12, "triliun"), (1e9, "miliar"), (1e6, "juta")):
            if abs(value) >= factor:
                return ("Rp " if value >= 0 else f"{MINUS}Rp ") + _grouped(abs(value) / factor,
                                                                          2 if places is None else places) + f" {unit}"
        return ("Rp " if value >= 0 else f"{MINUS}Rp ") + _grouped(abs(value), 0 if places is None else places)
    # auto
    if places is not None:
        return _grouped(value, places)
    if float(value).is_integer():
        return _grouped(value, 0)
    magnitude = abs(value)
    if magnitude >= 100:
        return _grouped(value, 0 if magnitude >= 10_000 else 1)
    if magnitude >= 1:
        return _grouped(value, 2)
    if magnitude >= 0.01:
        shown = _grouped(value, 3)  # 0.043 -> 0,043; 0.5 -> 0,50 (at least two decimals)
        return shown[:-1] if shown.endswith("0") else shown
    if magnitude == 0:
        return "0"
    mantissa, exponent = f"{value:.2e}".split("e")
    return mantissa.replace(".", ",").replace("-", MINUS) + "e" + str(int(exponent))


@dataclass
class Rendering:
    text: str
    values: list[Resolved] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    count: int = 0


def render(text: str | None, sources: ReferenceSources) -> Rendering:
    """Replace every {{reference|format}} with its formatted value. An unresolved reference is reported and shown as
    UNRESOLVED; text without references is returned unchanged."""
    if not text or "{{" not in text:
        return Rendering(text or "")
    out = Rendering("")

    def replace(match: re.Match[str]) -> str:
        out.count += 1
        places = match.group("places")
        try:
            resolved = evaluate(match.group("expr"), sources)
            shown = format_value(resolved.value, match.group("fmt"), int(places) if places is not None else None)
        except ReferenceError_ as exc:
            out.problems.append(str(exc))
            return UNRESOLVED
        out.values.append(resolved)
        return shown

    out.text = REF_RE.sub(replace, text)
    if "{{" in out.text or "}}" in out.text:
        out.problems.append("a reference is not closed or has an invalid form; write {{namespace.key.path}} or "
                            "{{namespace.key.path|format}}")
    return out
