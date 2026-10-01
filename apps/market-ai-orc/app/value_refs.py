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

from .provenance import LABEL_ORDER, parse_numbers

# P13 (suite20c a03, 2026-09-30): inside a Markdown table the model escapes the format separator as "\|"
REF_RE = re.compile(r"\{\{\s*(?P<expr>[^{}|]+?)\s*(?:\\?\|\s*(?P<fmt>[a-z]+)\s*(?::\s*(?P<places>\d)\s*)?)?\}\}")
FUNC_RE = re.compile(r"^(?P<name>diff|abs|ratio|chg)\s*\((?P<args>.*)\)$", re.DOTALL)
SELECTOR_RE = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<column>[^=\[\]]+)=(?P<value>[^\]]+)\]$")
INDEX_RE = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<index>-?\d+)\]$")  # P13 (a02): rows[0], the Python way
# rows[SEMA]: a row named by its key value alone (ma-steps-20261001a, a05); read when exactly one row has that value in
# a column that identifies the rows
BARE_RE = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<value>[^=\[\]]+)\]$")
MAX_TEXT = 200
FORMATS = {"auto", "dec", "int", "pct", "pctv", "pp", "rp", "x"}
FUNCTION_ARITY = {"diff": 2, "abs": 1, "ratio": 2, "chg": 2}
MINUS = "−"
UNRESOLVED = "[nilai tidak tersedia]"


class ReferenceError_(ValueError):
    """A reference that cannot be resolved; the message names what is available instead."""


class MissingField(ReferenceError_):
    """M43 (2026-09-30, user decision): the reference names a field its object does not have, or an object where one
    value is needed (P14, a01). The answer shows the field name in brackets and keeps its response type."""

    def __init__(self, message: str, name: str) -> None:
        super().__init__(message)
        self.name = name


TABLE_FETCH_ROWS = 200  # rows per page read from the sandbox (its get_session_output maximum)
TABLE_MAX_FETCHES = 25  # pages a table may read at render time (at most 5,000 rows)


class TableRows:
    """M44 (2026-10-01): the rows of one released table by their position in the complete table (`_row`).

    Every page the run reads (complete_analysis contents at offset 0, get_session_output at its offset) adds rows and
    never replaces them, so a reference means the same row whatever was read last. A row the run has not read is
    fetched from the released output when the answer is rendered (fetch(offset, limit) -> (rows, row_count))."""

    def __init__(self, row_count: int | None = None,
                 fetch: Any | None = None) -> None:
        self.rows: dict[int, Any] = {}
        self.row_count = row_count
        self.fetch = fetch
        self.fetches = 0

    def add(self, offset: int, rows: list[Any], row_count: int | None = None) -> None:
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                row["_row"] = offset + i  # shown to the model too: the row's position in the complete table
            self.rows[offset + i] = row
        if row_count is not None:
            self.row_count = row_count

    def _read(self, offset: int) -> bool:
        if self.fetch is None or self.fetches >= TABLE_MAX_FETCHES:
            return False
        self.fetches += 1
        try:
            rows, row_count = self.fetch(offset, TABLE_FETCH_ROWS)
        except Exception:  # noqa: BLE001 - an unreadable page leaves the reference unresolved, never wrong
            return False
        self.add(offset, rows, row_count)
        return bool(rows)

    def get(self, index: int) -> Any:
        if index < 0:
            if self.row_count is None:
                return None
            index += self.row_count
        if index not in self.rows and (self.row_count is None or 0 <= index < self.row_count):
            self._read(index - index % TABLE_FETCH_ROWS)
        return self.rows.get(index)

    def all(self) -> list[Any]:
        """Every row of the table (read on demand, bounded by TABLE_MAX_FETCHES)."""
        offset = 0
        while self.row_count is None or offset < self.row_count:
            if any(i not in self.rows for i in range(offset, min(offset + TABLE_FETCH_ROWS, self.row_count or 0))) \
                    or (self.row_count is None and offset not in self.rows):
                if not self._read(offset):
                    break
            offset += TABLE_FETCH_ROWS
        return [self.rows[i] for i in sorted(self.rows)]

    def identity_column(self) -> str | None:
        """A text column whose values are unique across the rows read (broker, ticker, series code, date), derived
        from the data; None when no column identifies a row."""
        rows = [row for row in self.rows.values() if isinstance(row, dict)]
        if len(rows) < 2:
            return None
        for column in rows[0]:
            if column == "_row":
                continue
            values = [row.get(column) for row in rows]
            if all(isinstance(v, str) for v in values) and len(set(values)) == len(values):
                return column
        return None


@dataclass
class Resolved:
    value: float
    label: str


@dataclass
class ResolvedText:
    """P13 (suite20c, 2026-09-30): a text value (a ticker, a broker, a label) shown as written; the numbers it
    contains become provenance sources under the same label."""
    text: str
    label: str


@dataclass
class ReferenceSources:
    """namespace -> key -> (object, evidence label); P18: short aliases (o1, o2, ...) per namespace -> key."""

    objects: dict[str, dict[str, tuple[Any, str]]] = field(default_factory=dict)
    aliases: dict[str, dict[str, str]] = field(default_factory=dict)

    def add(self, namespace: str, key: str, value: Any, label: str) -> None:
        self.objects.setdefault(namespace, {})[str(key)] = (value, label)

    def alias(self, namespace: str, alias: str, key: str) -> None:
        self.aliases.setdefault(namespace, {})[alias] = key

    def __bool__(self) -> bool:
        return any(self.objects.values())

    def keys(self, namespace: str) -> list[str]:
        return sorted(self.objects.get(namespace, {}))

    def refs(self, namespace: str) -> list[str]:
        """P18: the full references a refusal lists (out.o1 rather than a bare id), aliases first."""
        aliased = self.aliases.get(namespace, {})
        named = set(aliased.values())
        shown = sorted(aliased, key=lambda a: (len(a), a)) + [k for k in self.keys(namespace) if k not in named]
        return [f"{namespace}.{k}" for k in shown]

    def _key(self, namespace: str, key: str, rest: list[str]) -> tuple[str, list[str]]:
        """P18: an alias, or the unambiguous form of a mistyped id (out.out.<hex> for out.out_<hex>)."""
        keys = self.objects.get(namespace, {})
        key = self.aliases.get(namespace, {}).get(key, key)
        if key not in keys and rest and f"{key}_{rest[0]}" in keys:
            return f"{key}_{rest[0]}", rest[1:]
        return key, rest

    def lookup(self, path: str) -> Resolved:
        value, label = self.resolve(path)
        number = _number(value)
        if number is None and isinstance(value, str):
            raise ReferenceError_(f"'{path}' is text, not a number: reference it without a format to show it as "
                                  f"written")
        if isinstance(value, dict):
            raise MissingField(f"'{path}' is an object, not one value; its fields: {', '.join(list(value)[:12])}",
                               _split(path)[-1])
        if number is None:
            raise ReferenceError_(f"'{path}' is not a number ({type(value).__name__}"
                                  + (f"; its fields: {', '.join(list(value)[:12])}" if isinstance(value, dict) else "")
                                  + ")")
        return Resolved(number, label)

    def resolve(self, path: str) -> tuple[Any, str]:
        """The raw value at path with its evidence label."""
        parts = [p for p in _split(path.strip().rstrip("\\").strip())]
        if len(parts) < 2:
            raise ReferenceError_(f"'{path}' needs a namespace and a key, for example finding.<angle_id>.<field>")
        namespace, key, rest = parts[0], parts[1], parts[2:]
        if namespace not in self.objects:
            # P18: an id written without its namespace (out_<hex>.rows[...]) when exactly one namespace has it
            owners = [n for n, keys in self.objects.items() if namespace in keys]
            if len(owners) == 1:
                namespace, key, rest = owners[0], parts[0], parts[1:]
        key, rest = self._key(namespace, key, rest)
        if namespace not in self.objects:
            raise ReferenceError_(f"'{path}': unknown namespace {namespace!r}; this run has "
                                  f"{sorted(n for n in self.objects if self.objects[n]) or 'no referable values'}")
        entry = self.objects[namespace].get(key)
        if entry is None:
            raise ReferenceError_(f"'{path}': {namespace}.{key} does not exist; available: "
                                  f"{', '.join(self.refs(namespace)[:12])}")
        value, label = entry
        # a refusal names the object as the model can write it (out.o1), never by its long id
        shown = next((a for a, k in self.aliases.get(namespace, {}).items() if k == key), key)
        return _walk(value, rest, f"{namespace}.{shown}", path), label


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


def _walk(value: Any, rest: list[str], walked: str, path: str) -> Any:
    """Follow the path segments. P15 (2026-09-30): a field name with a dot ("XL_crash_pos_days_1.0") is split by the
    path syntax, so at an object the segments are also tried joined with dots: the exact field first, then the
    shorter joined names; the first reading that resolves the whole path wins, else the exact reading's error."""
    if not rest:
        return value
    readings = [(rest[0], 1)]
    if isinstance(value, dict) and not INDEX_RE.match(rest[0]) and not SELECTOR_RE.match(rest[0]) \
            and not BARE_RE.match(rest[0]):
        readings += [(".".join(rest[:end]), end) for end in range(2, len(rest) + 1) if ".".join(rest[:end]) in value]
    first: ReferenceError_ | None = None
    for part, used in readings:
        try:
            child, child_walked = _step(value, part, walked, path)
            return _walk(child, rest[used:], child_walked, path)
        except ReferenceError_ as exc:
            first = first or exc
    assert first is not None
    raise first


def _step(value: Any, part: str, walked: str, path: str) -> tuple[Any, str]:
    index = INDEX_RE.match(part)
    if index:
        items, walked = _step(value, index.group("key").strip(), walked, path)
        return _step(items, index.group("index"), walked, path)
    selector = SELECTOR_RE.match(part)
    if selector:
        items, walked = _step(value, selector.group("key").strip(), walked, path)
        column, wanted = selector.group("column").strip(), selector.group("value").strip().strip("'\"")
        if isinstance(items, TableRows):
            items = items.all()  # M44: the selector searches the complete table, not the last page read
        if not isinstance(items, list):
            raise ReferenceError_(f"'{path}': {walked} is not a list of rows")
        for row in items:
            if isinstance(row, dict) and str(row.get(column)) == wanted:
                return row, f"{walked}[{column}={wanted}]"
        seen = sorted({str(row.get(column)) for row in items if isinstance(row, dict)})[:12]
        raise ReferenceError_(f"'{path}': no row of {walked} has {column}={wanted}; values: {', '.join(seen)}")
    bare = BARE_RE.match(part)
    if bare and not INDEX_RE.match(part):
        items, walked = _step(value, bare.group("key").strip(), walked, path)
        wanted = bare.group("value").strip().strip("'\"")
        rows = [r for r in (items.all() if isinstance(items, TableRows) else items if isinstance(items, list) else [])
                if isinstance(r, dict)]
        keys = [c for c in (rows[0] if rows else {}) if c != "_row" and all(isinstance(r.get(c), str) for r in rows)
                and len({r.get(c) for r in rows}) == len(rows)]
        matches = [(c, r) for c in keys for r in rows if r.get(c) == wanted]
        if len(matches) == 1:
            column, row = matches[0]
            return row, f"{walked}[{column}={wanted}]"
        example = f"{walked}[{keys[0]}={wanted}]" if keys else f"{walked}[<column>={wanted}]"
        raise ReferenceError_(f"'{path}': write a row selector with its column, for example {example}"
                              + (f" (identifying columns: {', '.join(keys)})" if keys else ""))
    if isinstance(value, dict):
        if part not in value:
            raise MissingField(f"'{path}': {walked} has no field {part!r}; its fields: "
                               f"{', '.join(list(value)[:15])}", part)
        return value[part], f"{walked}.{part}"
    if isinstance(value, TableRows):
        if not part.lstrip("-").isdigit():
            raise ReferenceError_(f"'{path}': {walked} is a table; use a row selector [column=value]")
        key = value.identity_column()
        if key is not None:
            # M44: a row position next to a name can take another entity's row; a keyed table is read by its key
            row = value.get(int(part))
            hint = f"{walked}[{key}={row.get(key)}]" if isinstance(row, dict) else f"{walked}[{key}=<value>]"
            raise ReferenceError_(f"'{path}': {walked} is identified by {key!r}; reference its rows by that column, "
                                  f"for example {hint}, not by position")
        row = value.get(int(part))
        if row is None:
            raise ReferenceError_(f"'{path}': {walked} has no row {part} (rows: {value.row_count})")
        return row, f"{walked}.{part}"
    if isinstance(value, list):
        if not part.lstrip("-").isdigit() or not -len(value) <= int(part) < len(value):
            raise ReferenceError_(f"'{path}': {walked} is a list of {len(value)} items; use an index 0 to "
                                  f"{len(value) - 1} or a [column=value] selector")
        return value[int(part)], f"{walked}.{part}"
    # a field below a value: most often a dotted field name the object does not have ("XL_days_1.5")
    raise MissingField(f"'{path}': {walked} is a value, it has no field {part!r}",
                       f"{walked.rsplit('.', 1)[-1]}.{part}")


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
    values: list[Resolved] = field(default_factory=list)  # numbers shown, and the numbers inside a shown text
    problems: list[str] = field(default_factory=list)
    count: int = 0
    # M43: references to a field that does not exist (or to an object), shown as [field]: (expression, field, message)
    missing: list[tuple[str, str, str]] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # the expressions of the other unresolved references


def _text(value: str) -> str:
    one_line = " ".join(value.split())
    return one_line if len(one_line) <= MAX_TEXT else one_line[:MAX_TEXT - 1] + "…"


def _text_numbers(text: str) -> list[float]:
    return [value for shown in parse_numbers(text) for value, _ in shown.candidates]


LIST_ITEMS = 8  # items of a list shown before "(+N lainnya)"


def _display(raw: Any, label: str, fmt: str | None, places: int | None, path: str, out: "Rendering") -> str | None:
    """P14 (2026-10-01): how a non-numeric value is shown, or None for a number (formatted by the caller). Every value
    the AI can reference has a display; only an object or a table (no single rendering) becomes a [field] marker."""
    if isinstance(raw, bool):
        return "ya" if raw else "tidak"
    if raw is None:
        return "null"  # user decision 2026-10-01
    if isinstance(raw, float) and not math.isfinite(raw):
        return "undefined"  # NaN, inf (user decision 2026-10-01)
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and _number(raw) is not None):
        return None
    if isinstance(raw, str):
        shown = _text(raw)  # a number format on a text is not applicable: the text is shown as written
        out.values.extend(Resolved(v, label) for v in _text_numbers(shown))
        return shown
    if isinstance(raw, list):
        if not raw:
            return "tidak ada"
        if any(isinstance(item, (dict, list, TableRows)) for item in raw):
            raise MissingField(f"'{path}' is a list of objects; reference one item by its index or a selector",
                               _split(path)[-1])
        shown = []
        for item in raw[:LIST_ITEMS]:
            text = _display(item, label, fmt, places, path, out)
            if text is None:
                number = float(_number(item))
                out.values.append(Resolved(number, label))
                text = format_value(number, fmt, places)
            shown.append(text)
        more = f" (+{len(raw) - LIST_ITEMS} lainnya)" if len(raw) > LIST_ITEMS else ""
        return "; ".join(shown) + more
    if isinstance(raw, (dict, TableRows)):
        names = ", ".join(list(raw)[:12]) if isinstance(raw, dict) else "rows by [column=value]"
        raise MissingField(f"'{path}' is an object, not one value; its fields: {names}", _split(path)[-1])
    raise ReferenceError_(f"'{path}' has no display ({type(raw).__name__})")


def render(text: str | None, sources: ReferenceSources) -> Rendering:
    """Replace every {{reference|format}} with its formatted value. An unresolved reference is reported and shown as
    UNRESOLVED; text without references is returned unchanged."""
    if not text or "{{" not in text:
        return Rendering(text or "")
    out = Rendering("")

    def replace(match: re.Match[str]) -> str:
        out.count += 1
        places = match.group("places")
        expression = match.group("expr").strip().rstrip("\\").strip()
        try:
            if not FUNC_RE.match(expression):
                raw, label = sources.resolve(expression)
                shown = _display(raw, label, match.group("fmt"), int(places) if places is not None else None,
                                 expression, out)
                if shown is not None:
                    return shown
            resolved = evaluate(expression, sources)
            shown = format_value(resolved.value, match.group("fmt"), int(places) if places is not None else None)
        except MissingField as exc:
            out.missing.append((expression, exc.name, str(exc)))
            return f"[{exc.name}]"
        except ReferenceError_ as exc:
            out.problems.append(str(exc))
            out.failed.append(expression)
            return UNRESOLVED
        out.values.append(resolved)
        return shown

    out.text = REF_RE.sub(replace, text)
    if "{{" in out.text or "}}" in out.text:
        out.failed.append("{{")
        out.problems.append(_invalid_form(out.text))
    return out


LEFTOVER_RE = re.compile(r"\{\{([^{}]{0,300}?)\}\}")


def _invalid_form(text: str) -> str:
    """P7 (2026-10-01, e02): `{{finding....|dec:2e-0}}` was refused only as "not closed or has an invalid form", so the
    model could not see which reference or what was wrong. Each leftover reference is named with its fault."""
    named = []
    for match in LEFTOVER_RE.finditer(text):
        body = match.group(1)
        expression, _, fmt = body.partition("|")
        if fmt:
            name, _, places = fmt.strip().partition(":")
            if name.strip() not in FORMATS:
                fault = f"unknown format {name.strip()!r}"
            else:
                fault = f"places {places.strip()!r} must be one digit 0-9"
        else:
            fault = "not a namespace.key.path"
        named.append(f"'{{{{{body.strip()[:120]}}}}}': {fault}")
        if len(named) == 3:
            break
    where = "; ".join(named) if named else "a '{{' without its closing '}}' (or the reverse)"
    return (f"a reference has an invalid form: {where}. Write {{{{namespace.key.path}}}} or "
            f"{{{{namespace.key.path|format}}}} or {{{{...|format:N}}}} with a format among "
            f"{', '.join(sorted(FORMATS))} and N one digit of decimal places")
