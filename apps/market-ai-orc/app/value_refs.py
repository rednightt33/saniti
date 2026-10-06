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
pctv:N (already a percent), pp:N (percentage points), rp (rupiah scaled to ribu/juta/miliar/triliun), x:N ("kali"),
p (a p-value: "p < 0,001", "p = 0,003", "p = 0,35").

P23 (2026-10-02): a value whose unit the backend knows (FRACTION, PERCENT or P_VALUE, declared by the object that holds
it: a finding's "units", a table's declared column units) is shown by that unit, not by the format's assumption: pct,
pctv and pp scale a FRACTION by 100 and leave a PERCENT as it is, and a P_VALUE is shown with p. A percent-type word
the model typed right after such a reference ("{{x|dec:2}} pp") is read as the display it asked for.
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
FORMATS = {"auto", "dec", "int", "p", "pct", "pctv", "pp", "rp", "x"}
UNITS = ("FRACTION", "PERCENT", "P_VALUE")
P_FLOOR = 0.001  # P24: a smaller p-value is shown as "p < 0,001"
FUNCTION_ARITY = {"diff": 2, "abs": 1, "ratio": 2, "chg": 2}
MINUS = "−"
MENU_TABLE_ROWS = 30  # 1b: rows of a table (or items of a list of objects) listed one by one
MENU_OBJECT_LIMIT = 200  # address menu lines for one object
UNRESOLVED = "[nilai tidak tersedia]"
# Item 12 (plan 2026-10-05): labels of values from outside the database, and how a rendered value names them; such a
# value is a context source for the provenance gate (not in LABEL_ORDER), so it never lowers an answer's data label
OUTSIDE_LABELS = {"WEB_FACT": "fakta web"}
OUTSIDE_NAMESPACES = {"WEB_FACT": "web"}  # the namespace an item of a citable envelope is registered under
OUTSIDE_FIELDS = frozenset({"value", "value_as_written", "members"})  # the fields of an outside item that are its value
NEXT_IS_WORD_RE = re.compile(r"\s*[\w$€£¥%]")


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
    unit: str | None = None  # P23: FRACTION, PERCENT, P_VALUE or unknown


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
    # P23: (namespace, key) -> {field or column (or a dotted path of them): unit} declared beside the object
    units: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    # 10.4 (plan 2026-10-05 item 10): (namespace, key) -> (namespace, key, path prefix) read when a field is missing
    fallbacks: dict[tuple[str, str], tuple[str, str, tuple[str, ...]]] = field(default_factory=dict)
    # 10.4: reference -> the reference it was read from (logged as ai_reference_redirected)
    redirected: dict[str, str] = field(default_factory=dict)
    # Item 12: (namespace, key) -> where an outside value comes from (a web fact's domain), named where it is shown
    origins: dict[tuple[str, str], str] = field(default_factory=dict)

    def add(self, namespace: str, key: str, value: Any, label: str, units: dict[str, Any] | None = None,
            origin: str | None = None) -> None:
        self.objects.setdefault(namespace, {})[str(key)] = (value, label)
        if origin:
            self.origins[(namespace, str(key))] = origin
        declared = {str(k): v for k, v in (units or {}).items() if v in UNITS}
        if declared:  # a later registration without units keeps the ones learned before (the same output)
            self.units[(namespace, str(key))] = declared

    def alias(self, namespace: str, alias: str, key: str) -> None:
        self.aliases.setdefault(namespace, {})[alias] = key

    def fallback(self, namespace: str, key: str, target_namespace: str, target_key: str,
                 prefix: tuple[str, ...] = ()) -> None:
        """10.4: a field the object (namespace, key) lacks is read from the same path under prefix of another object
        of this run (a hypothesis finding from its released research_summary). One fallback per object."""
        self.fallbacks[(namespace, str(key))] = (target_namespace, str(target_key), tuple(prefix))

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
        unit = self.unit(self.redirected.get(path, path))
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
        return Resolved(number, label, unit)

    def _locate(self, path: str) -> tuple[str, str, list[str]]:
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
        return namespace, key, rest

    def outside(self, path: str, label: str) -> str | None:
        """Item 12: how a value from outside the database is named where it is shown ("fakta web, bps.go.id"), for
        an outside label and a path that ends at the item's value; None otherwise. A function of outside values is
        named without its domain."""
        name = OUTSIDE_LABELS.get(label)
        if name is None:
            return None
        if FUNC_RE.match(path.strip()):
            return name
        try:
            namespace, key, rest = self._locate(path)
        except ReferenceError_:
            return None
        if not rest or _names([rest[-1]])[:1] != [rest[-1]] or rest[-1] not in OUTSIDE_FIELDS:
            return None
        origin = self.origins.get((namespace, key))
        return f"{name}, {origin}" if origin else name

    def unit(self, path: str) -> str | None:
        """P23: the unit of the value at path, from the units declared beside its object or by an object on the way
        to it (the innermost declaration wins); a declaration names a field by its name or by a dotted path that
        ends at it, and a row selector or an index is not part of the name. None when no declaration covers it."""
        try:
            namespace, key, rest = self._locate(path)
        except ReferenceError_:
            return None
        entry = self.objects.get(namespace, {}).get(key)
        if entry is None:
            return None
        declared: list[tuple[dict[str, Any], list[str]]] = []
        if (namespace, key) in self.units:
            declared.append((self.units[(namespace, key)], _names(rest)))
        current: Any = entry[0]
        for i, part in enumerate(rest):
            if isinstance(current, dict) and isinstance(current.get("units"), dict):
                declared.append((current["units"], _names(rest[i:])))
            name = _names([part])
            if not (isinstance(current, dict) and name and name[0] in current) or name[0] != part:
                break
            current = current[name[0]]
        for units, names in reversed(declared):
            for start in range(len(names)):
                unit = units.get(".".join(names[start:]))
                if unit in UNITS:
                    return unit
        return None

    def resolve(self, path: str) -> tuple[Any, str]:
        """The raw value at path with its evidence label."""
        namespace, key, rest = self._locate(path)
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
        try:
            return _walk(value, rest, f"{namespace}.{shown}", path), label
        except MissingField:
            target = self.fallbacks.get((namespace, key))
            entry = self.objects.get(target[0], {}).get(target[1]) if target else None
            if target is None or entry is None:
                raise
            target_shown = next((a for a, k in self.aliases.get(target[0], {}).items() if k == target[1]), target[1])
            walked = ".".join([target[0], target_shown, *target[2]])
            try:
                found = _walk(entry[0], [*target[2], *rest], walked, path)
            except ReferenceError_:
                pass
            else:
                self.redirected[path] = ".".join([walked, *rest])
                return found, entry[1]
            raise

    def leaves(self, ref: str, limit: int = MENU_OBJECT_LIMIT) -> list[tuple[str, float]]:
        """The (address, value) of each numeric value of the object at ref, as the menu lists them (EXEC-R R3)."""
        try:
            value, _ = self.resolve(ref)
        except ReferenceError_:
            return []
        paths: list[tuple[str, float]] = []
        _menu_leaves(value, ref, paths, limit, 0)
        return paths

    def menu(self, ref: str, limit: int = MENU_OBJECT_LIMIT) -> list[str]:
        """10.1 and 1b (user decision 2026-10-05: "every result with figures lists the full address next to each figure,
        e.g. median: −2,40 → {{out.o2.content.groups.CONDITION.median}}"): one line per numeric value of the object at
        ref, "<name>: <value as shown> [unit] → {{<address>}}", for the model to copy instead of composing an address.
        A table lists every row it has read up to MENU_TABLE_ROWS, by its identifying column when it has one, after a
        pattern line naming the row selector and the numeric columns; a longer table states how many rows the pattern
        covers. Bounded to limit lines; payloads, hashes and versions are left out."""
        try:
            value, _ = self.resolve(ref)
        except ReferenceError_:
            return []
        paths: list[tuple[str, float]] = []
        patterns: list[str] = []
        _menu_leaves(value, ref, paths, limit, 0, patterns)
        out = list(patterns)
        for address, number in paths:
            if len(out) >= limit:
                break
            unit = self.unit(address)
            out.append(f"{_menu_name(address)}: {format_value(number)}" + (f" [{unit}]" if unit else "")
                       + f" → {{{{{address}}}}}")
        return out


MENU_SKIP = frozenset({"units", "hashes", "versions", "method_payload", "lineage", "definition", "warnings",
                       "limitations", "released_output_ids", "addresses", "_row", "query_hash", "query_id"})
MENU_DEPTH = 7
MENU_ADDRESS_RE = re.compile(r"\{\{([^{}]+)\}\}")


def menu_address(line: str) -> str | None:
    """The address a menu line writes (None for a pattern or note line)."""
    match = MENU_ADDRESS_RE.search(line)
    return match.group(1) if match and "<" not in match.group(1) else None


def _menu_name(address: str) -> str:
    """The short name of a menu line: the field, after the row it belongs to (BBCA mean_return, CONDITION median)."""
    parts = _split(address)
    field_name = parts[-1]
    row = re.search(r"\[[^=\]]+=([^\]]+)\]", address)
    if row and not field_name.startswith(row.group(0)):
        return f"{row.group(1)} {field_name.split('[', 1)[0]}"
    if len(parts) >= 4 and parts[-2].isdigit():
        return f"row {parts[-2]} {field_name}"
    if len(parts) >= 4 and parts[-2] not in ("content", "rows"):
        return f"{parts[-2].split('[', 1)[0]} {field_name}"
    return field_name


def _identity(rows: list[dict]) -> str | None:
    """A text column whose values are unique across the rows (ticker, broker, date), else None."""
    if len(rows) < 2:
        return None
    for column in rows[0]:
        values = [r.get(column) for r in rows]
        if column != "_row" and all(isinstance(v, str) for v in values) and len(set(values)) == len(values):
            return column
    return None


def _menu_leaves(value: Any, path: str, out: list[tuple[str, float]], limit: int, depth: int,
                 patterns: list[str] | None = None) -> None:
    if len(out) >= limit or depth > MENU_DEPTH:
        return
    total = None
    if isinstance(value, TableRows):
        total = value.row_count
        value = [value.rows[i] for i in sorted(value.rows)]
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in MENU_SKIP:
                continue
            _menu_leaves(child, f"{path}.{key}", out, limit, depth + 1, patterns)
        return
    if isinstance(value, list):
        if value and all(_number(v) is not None and not isinstance(v, str) for v in value) and len(value) <= 4:
            for i, item in enumerate(value):
                if len(out) < limit:
                    out.append((f"{path}.{i}", float(item)))
            return
        if value and all(isinstance(v, dict) for v in value):
            rows = [v for v in value if isinstance(v, dict)]
            column = _identity(rows)
            shown = rows[:MENU_TABLE_ROWS]
            total = total if total is not None else len(rows)
            if patterns is not None:
                numeric = [k for k, v in rows[0].items()
                           if k not in MENU_SKIP and not isinstance(v, (str, bool)) and _number(v) is not None]
                selector = f"[{column}=<{column}>]" if column else ".<baris>"
                note = f" ({len(shown)} of {total} rows listed below; the others use the same pattern)" \
                    if total > len(shown) else ""
                if numeric:
                    patterns.append(f"pattern: {{{{{path}{selector}.<column>}}}}, numeric columns: "
                                    f"{', '.join(numeric[:20])}{note}")
                if column and total > len(shown):
                    names = [str(r.get(column)) for r in rows[len(shown):len(shown) + 50]]
                    if names:
                        patterns.append(f"other {column} values: {', '.join(names)}"
                                        + (" …" if total > len(shown) + len(names) else ""))
            for i, row in enumerate(shown):
                step = f"[{column}={row[column]}]" if column else f".{i}"
                _menu_leaves(row, f"{path}{step}", out, limit, depth + 1, patterns)
        return
    if not isinstance(value, (str, bool)) and _number(value) is not None:
        out.append((path, float(value)))


def _names(parts: list[str]) -> list[str]:
    """The field names of path segments: rows[ticker=BBRI] and rows[0] are rows; an index (ci.0) is no name."""
    names = []
    for part in parts:
        name = part.split("[", 1)[0].strip()
        if name and not name.lstrip("-").isdigit():
            names.append(name)
    return names


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
    # P23: a difference keeps the unit its inputs share (a difference of p-values has none); a ratio has no unit and
    # a relative change is a fraction
    units = {v.unit for v in values}
    shared = units.pop() if len(units) == 1 and values[0].unit != "P_VALUE" else None
    x = values[0].value
    if name == "abs":
        return Resolved(abs(x), label, values[0].unit)
    y = values[1].value
    if name == "diff":
        return Resolved(x - y, label, shared)
    if y == 0:
        raise ReferenceError_(f"{name}(): the second value is zero")
    return Resolved(x / y, label) if name == "ratio" else Resolved((x - y) / y, label, "FRACTION")


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


PERCENT_FORMATS = ("pct", "pctv", "pp")


def display_format(fmt: str | None, unit: str | None) -> str:
    """P23/P24: the format a value is shown with once its unit is known. A p-value is shown with p (a percent format
    on it is refused); a known FRACTION or PERCENT decides the scaling of pct, pctv and pp (see format_value)."""
    fmt = fmt or "auto"
    if unit == "P_VALUE":
        if fmt in PERCENT_FORMATS + ("x", "rp"):
            raise ReferenceError_(f"a p-value cannot be shown with |{fmt}; write it with |p")
        return "p"
    return fmt


def scale_changed(fmt: str | None, unit: str | None) -> bool:
    """True when the data's unit overrides the scaling the format assumes (pct on a PERCENT, pctv or pp on a
    FRACTION): the value is shown right, and the change is logged."""
    return (fmt == "pct" and unit == "PERCENT") or (fmt in ("pctv", "pp") and unit == "FRACTION")


def format_value(value: float, fmt: str | None = None, places: int | None = None, unit: str | None = None) -> str:
    """The value in Indonesian notation; every output reads back through provenance.parse_numbers. With a known unit
    (P23) the percent formats scale by it: FRACTION x 100, PERCENT as it is."""
    fmt = fmt or "auto"
    if fmt not in FORMATS:
        raise ReferenceError_(f"unknown format {fmt!r}; use one of {', '.join(sorted(FORMATS))}")
    if fmt in PERCENT_FORMATS and unit in ("FRACTION", "PERCENT"):
        shown = value * 100 if unit == "FRACTION" else value
        return _grouped(shown, 2 if places is None else places) + (" pp" if fmt == "pp" else "%")
    if fmt == "p":
        if not 0 <= value <= 1:
            return _grouped(value, 3 if places is None else places)
        if value < P_FLOOR:
            return "p < " + _grouped(P_FLOOR, 3)
        return "p = " + _grouped(value, 3 if value < 0.01 else 2 if places is None else places)
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
    # P22: units the model typed next to a reference whose format already shows them ("{{x|pp}} pp" -> "1,00 pp")
    dropped_units: list[str] = field(default_factory=list)
    # P23: references shown by their data's unit rather than as written: {reference, format, shown_as, unit}
    corrected_units: list[dict[str, Any]] = field(default_factory=list)
    unknown_units: list[str] = field(default_factory=list)  # percent formats on a value of undeclared unit
    # Item 12: the outside sources shown, (expression, "fakta web, <domain>"); a source is named after the first value
    # of it in each text when no word follows that value (otherwise the sentence keeps its flow and the system's
    # line of web facts names it)
    outside: list[tuple[str, str]] = field(default_factory=list)
    named: set[str] = field(default_factory=set)
    pending: str | None = None


def _text(value: str) -> str:
    one_line = " ".join(value.split())
    return one_line if len(one_line) <= MAX_TEXT else one_line[:MAX_TEXT - 1] + "…"


def _text_numbers(text: str) -> list[float]:
    return [value for shown in parse_numbers(text) for value, _ in shown.candidates]


LIST_ITEMS = 8  # items of a list shown before "(+N lainnya)"


def _display(raw: Any, label: str, fmt: str | None, places: int | None, path: str, out: "Rendering",
             unit: str | None = None) -> str | None:
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
            text = _display(item, label, fmt, places, path, out, unit)
            if text is None:
                number = Resolved(float(_number(item)), label, unit)
                out.values.append(number)
                text = _Number(number, fmt, places, path).show(out)
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

    def replace(match: re.Match[str]) -> tuple[str, "_Number | None"]:
        out.count += 1
        places = int(match.group("places")) if match.group("places") is not None else None
        fmt = match.group("fmt")
        expression = match.group("expr").strip().rstrip("\\").strip()
        out.pending = None
        try:
            if not FUNC_RE.match(expression):
                raw, label = sources.resolve(expression)
                shown = _display(raw, label, fmt, places, expression, out,
                                 sources.unit(sources.redirected.get(expression, expression)))
                if shown is not None:
                    _note_outside(out, sources, expression, label)
                    return shown, None
            resolved = evaluate(expression, sources)
            _note_outside(out, sources, expression, resolved.label)
            number = _Number(resolved, fmt, places, expression)
            shown = number.show(out)
        except MissingField as exc:
            out.missing.append((expression, exc.name, str(exc)))
            return f"[{exc.name}]", None
        except ReferenceError_ as exc:
            out.problems.append(str(exc))
            out.failed.append(expression)
            return UNRESOLVED, None
        out.values.append(resolved)
        return shown, number

    out.text = _without_repeated_units(text, replace, out)
    if "{{" in out.text or "}}" in out.text:
        out.failed.append("{{")
        out.problems.append(_invalid_form(out.text))
    return out


def _note_outside(out: Rendering, sources: ReferenceSources, expression: str, label: str) -> None:
    """Item 12: an outside value is recorded with its source name, to be written after it (_without_repeated_units)."""
    name = sources.outside(expression, label)
    if name is None:
        return
    out.outside.append((expression, name))
    out.pending = name


@dataclass
class _Number:
    """A number a reference shows, kept so a unit word typed after it can decide its display (P23)."""
    resolved: Resolved
    fmt: str | None
    places: int | None
    expression: str

    def show(self, out: Rendering, fmt: str | None = None) -> str:
        asked = fmt or self.fmt
        unit = self.resolved.unit
        used = display_format(asked, unit)
        if scale_changed(asked, unit) or (fmt and fmt != self.fmt):
            out.corrected_units.append({"reference": self.expression, "format": self.fmt or "auto",
                                        "shown_as": used, "unit": unit})
        elif used in PERCENT_FORMATS and unit is None:
            out.unknown_units.append(self.expression)  # measured: a percent figure whose unit nobody declared
        if used == "p" and self.resolved.value < P_FLOOR and self.resolved.value >= 0:
            out.values.append(Resolved(P_FLOOR, self.resolved.label))  # P24: the bound shown is a source too
        return format_value(self.resolved.value, used, self.places, unit)


# P22: the unit a format adds is read from the shown value itself (its non-numeric tail and head), so every format that
# shows a unit (pct, pctv, pp, x, rp and any later one) is covered without a per-format list
UNIT_TAIL_RE = re.compile(r"[0-9)](\s*[^\s0-9.,()\u2212-][^0-9]*)$")
UNIT_HEAD_RE = re.compile(r"^\u2212?([^\s0-9.,\u2212-]+\s*)")
# P22 (golden test 2026-10-02): the words that name one unit; a word of the unit's family typed next to a reference
# repeats the unit ("−0,10 pp poin persentase"); a unit outside every family is matched as itself
PERCENT_WORDS = ("%", "persen", "percent", "per cent")
POINT_WORDS = ("pp", "p.p.", "poin persentase", "poin persen", "persentase poin", "percentage points",
               "percentage point", "percent points")
UNIT_FAMILIES = (PERCENT_WORDS, POINT_WORDS, ("kali", "times", "×"), ("Rp", "IDR", "rupiah"), ("triliun",),
                 ("miliar", "milyar"), ("juta",), ("ribu",))
EMPHASIS = r"[*_]{1,3}"  # Markdown emphasis between a reference and the word typed next to it ("**1,58 kali** kali")
P_TYPED_RE = re.compile(r"(?:^|(?<=[\s(*_]))p(?:-value| value)?\s*[=:<≤]?\s*(?P<emph>" + EMPHASIS + r")?$",
                        re.IGNORECASE)


def _family(unit: str) -> tuple[str, ...]:
    return next((f for f in UNIT_FAMILIES if unit.lower() in (w.lower() for w in f)), (unit,))


def _words(family: tuple[str, ...]) -> str:
    return "|".join(re.escape(w) for w in sorted(family, key=len, reverse=True))


def _typed_after(after: str, family: tuple[str, ...]) -> re.Match[str] | None:
    return re.match(r"(?P<emph>" + EMPHASIS + r")?\s*(?:" + _words(family) + r")(?![\w%])", after, re.IGNORECASE)


def _typed_before(before: str, family: tuple[str, ...]) -> re.Match[str] | None:
    return re.search(r"(?:^|(?<=[\s(*_]))(?:" + _words(family) + r")\s*(?P<emph>" + EMPHASIS + r")?$", before,
                     re.IGNORECASE)


def _without_repeated_units(text: str, replace, out: Rendering) -> str:
    """Fill every reference and drop a copy of its unit typed right next to it: "{{x|pp:2}} pp" shows "1,00 pp", not
    "1,00 pp pp", "Rp {{y|rp}}" shows "Rp 5 miliar", and "p = {{z|p}}" shows "p = 0,03". A copy is any word of the
    unit's family ("poin persentase" for pp, "persen" for %, "rupiah" for Rp), also behind Markdown emphasis; each
    drop is recorded in out.dropped_units. P23: a percent-type word typed after a number whose unit is known decides
    how it is shown ("{{rate|dec:2}} pp" shows the fraction as percentage points)."""
    parts: list[str] = []
    position = 0
    for match in REF_RE.finditer(text):
        if match.start() < position:
            continue
        before = text[position:match.start()]
        shown, number = replace(match)
        position = match.end()
        follows_reference = bool(REF_RE.match(text, position))
        if number is not None and number.resolved.unit in ("FRACTION", "PERCENT") and not follows_reference \
                and display_format(number.fmt, number.resolved.unit) in ("auto", "dec", "int") + PERCENT_FORMATS:
            for family, fmt in ((POINT_WORDS, "pp"), (PERCENT_WORDS, "pct")):
                typed = _typed_after(text[position:], family)
                if typed:
                    current = "pp" if (number.fmt or "") == "pp" else "pct" if number.fmt in ("pct", "pctv") else None
                    if current != fmt:
                        shown = number.show(out, fmt)
                    break
        if number is not None and shown.startswith("p "):
            typed_p = P_TYPED_RE.search(before)
            if typed_p:
                before = before[:typed_p.start()] + (typed_p.group("emph") or "")
                out.dropped_units.append("p")
        head = UNIT_HEAD_RE.match(shown)
        head_family: tuple[str, ...] = ()
        if head and head.group(1).strip() and not shown.startswith("p "):
            head_family = _family(head.group(1).strip())
            repeat = _typed_before(before, head_family)
            if repeat:
                out.dropped_units.append(before[repeat.start():repeat.end()].strip(" *_"))
                before = before[:repeat.start()] + (repeat.group("emph") or "")
        parts.append(before + shown)
        tail = UNIT_TAIL_RE.search(shown)
        for family in ([_family(tail.group(1).strip())] if tail and tail.group(1).strip() else []) \
                + ([head_family] if head_family else []):
            repeat = _typed_after(text[position:], family)
            if repeat and not follows_reference:
                out.dropped_units.append(text[position:position + repeat.end()].strip(" *_"))
                emphasis = repeat.group("emph") or ""
                position += repeat.end()
                parts.append(emphasis)  # the emphasis closes after the shown unit
                break
        if out.pending is not None:
            name, out.pending = out.pending, None
            if name not in out.named and not NEXT_IS_WORD_RE.match(text, position):
                out.named.add(name)
                parts.append(f" ({name})")
                out.values.extend(Resolved(v, "CONTEXT") for v in _text_numbers(name))
    parts.append(text[position:])
    return "".join(parts)


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
