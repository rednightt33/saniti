"""S4 "Pilihan AI" (PLAN_FINAL_2026-10-04.md Fase 3, user decision K6): every value the model typed into its own code
to filter, group or set a threshold is traced to its origin by the system, and what came from neither the user nor
the data is shown as the AI's choice. Nothing is blocked and the model is never required to ask.

Origin of a typed value (derived at run time; no scenario, ticker or table is named here):
- USER: it is in the user's words (this message or an earlier user turn); a number also as percent <-> fraction;
- DATA: a string the run's tool results returned (a dimension value, a ranking), or a list equal to a set a tool
  result returned whole; a number a tool result returned;
- AI_CHOICE: anything else. A list that picks some of the data's values is a choice even when each value exists.

Positions read from the syntax tree: the constant side of a comparison, the values of isin(...) or of "x in [...]",
the argument of quantile / percentile / nlargest / nsmallest / qcut / cut, and a list of strings assigned to a name
that is then used to filter (isin(name) or "x in name"). Lists of column or statistic names are not values. 0 and 1
are ignored (booleans, shifts by one, "the first"). Values computed from data are not literals and
never appear.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable

from . import user_texts as texts

CHOICE_CALLS = {"quantile", "percentile", "nanpercentile", "nanquantile", "nlargest", "nsmallest", "qcut", "cut"}
MAX_CHOICES = 30
MAX_SEEN = 50_000
LIST_MIN = 2


@dataclass(frozen=True)
class Typed:
    kind: str  # NUMBER | TEXT | LIST
    value: Any  # float, str or tuple[str, ...]
    position: str  # COMPARISON | ISIN | CALL:<name> | LIST


def _number(node: ast.AST) -> float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _number(node.operand)
        return -inner if inner is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool) \
            and math.isfinite(float(node.value)):
        return float(node.value)
    return None


def _strings(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and node.elts \
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return tuple(e.value for e in node.elts)
    return None


def _numbers(node: ast.AST) -> list[float]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [n for n in (_number(e) for e in node.elts) if n is not None]
    single = _number(node)
    return [single] if single is not None else []


def typed_values(code: str) -> list[Typed]:
    """The filter, group and threshold values typed in the code (empty when it does not parse)."""
    try:
        tree = ast.parse(code or "")
    except (SyntaxError, ValueError):
        return []
    found: list[Typed] = []
    listed: set[int] = set()

    def add_list(node: ast.AST, position: str) -> None:
        values = _strings(node)
        if values is not None:
            listed.add(id(node))
            if len(values) >= LIST_MIN:
                found.append(Typed("LIST", values, position))
            else:
                found.extend(Typed("TEXT", v, position) for v in values)
        else:
            found.extend(Typed("NUMBER", n, position) for n in _numbers(node))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    found.append(Typed("TEXT", side.value, "COMPARISON"))
                elif isinstance(side, (ast.List, ast.Tuple, ast.Set)):
                    add_list(side, "COMPARISON")  # x in ["A", "B"]
                else:
                    found.extend(Typed("NUMBER", n, "COMPARISON") for n in _numbers(side))
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else \
                node.func.id if isinstance(node.func, ast.Name) else None
            if name == "isin":
                for arg in node.args[:1]:
                    add_list(arg, "ISIN")
            elif name in CHOICE_CALLS:
                # qcut / cut / percentile take the data first; the others take the choice first
                positional = node.args[1:] if name in ("qcut", "cut", "percentile", "nanpercentile") else node.args
                keywords = [k.value for k in node.keywords if k.arg in ("q", "n", "bins", "quantiles")]
                for arg in [*positional, *keywords]:
                    add_list(arg, f"CALL:{name}")
    # a list given a name, then used to filter: bumn = ["A", "B"]; df[df.ticker.isin(bumn)]
    filtering = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "isin":
            filtering.update(a.id for a in node.args[:1] if isinstance(a, ast.Name))
        elif isinstance(node, ast.Compare):
            filtering.update(c.id for op, c in zip(node.ops, node.comparators)
                             if isinstance(op, (ast.In, ast.NotIn)) and isinstance(c, ast.Name))
    # ... also through names derived from it: present = [t for t in bumn if ...]; df.ticker.isin(present)
    sources: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            used = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            for target in node.targets:
                if isinstance(target, ast.Name):
                    sources.setdefault(target.id, set()).update(used)
    changed = True
    while changed:
        changed = False
        for name in list(filtering):
            new = sources.get(name, set()) - filtering
            if new:
                filtering |= new
                changed = True
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and id(node.value) not in listed \
                and any(isinstance(t, ast.Name) and t.id in filtering for t in node.targets):
            values = _strings(node.value)
            if values is not None and len(values) >= LIST_MIN:
                found.append(Typed("LIST", values, "LIST"))
                listed.add(id(node.value))
    return found


WORD_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.&-]*")
NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _user_numbers(text: str) -> set[float]:
    out: set[float] = set()
    for raw in NUMBER_RE.findall(text or ""):
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            continue
        out.update({value, round(value / 100, 10), round(value * 100, 10)})
    return out


def _close(value: float, pool: Iterable[float]) -> bool:
    return any(abs(value - p) <= 1e-9 * max(1.0, abs(p)) for p in pool)


def string_leaves(value: Any, out: set[str], depth: int = 0) -> None:
    """Every short string of a tool result (values a tool returned), bounded."""
    if depth > 12 or len(out) >= MAX_SEEN:
        return
    if isinstance(value, str):
        if 0 < len(value) <= 80:
            out.add(value.strip().upper())
    elif isinstance(value, dict):
        for item in value.values():
            string_leaves(item, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            string_leaves(item, out, depth + 1)


def string_sets(value: Any, out: set[frozenset[str]], depth: int = 0) -> None:
    """Every list of strings a tool result returned whole (a ranking's tickers, a dimension's values)."""
    if depth > 12 or len(out) >= MAX_SEEN:
        return
    if isinstance(value, list) and len(value) >= LIST_MIN and all(isinstance(v, str) for v in value):
        out.add(frozenset(v.strip().upper() for v in value))
    if isinstance(value, dict):
        for item in value.values():
            string_sets(item, out, depth + 1)
        return
    if isinstance(value, list):
        for item in value:
            string_sets(item, out, depth + 1)
        if value and all(isinstance(v, dict) for v in value):
            # a table's column: the values of one key across its rows
            for key in {k for row in value[:500] for k in row}:
                column = [row.get(key) for row in value[:500]]
                if len(column) >= LIST_MIN and all(isinstance(v, str) for v in column):
                    out.add(frozenset(v.strip().upper() for v in column))


def user_numbers(text: str) -> set[float]:
    """The numbers of the user's words, each also as percent <-> fraction."""
    return _user_numbers(text)


def web_numbers_in_code(values: list[Typed], user_text: str, web_numbers: Iterable[float],
                        data_numbers: Iterable[float]) -> list[float]:
    """P34 (user rule 2026-10-05: every calculation is sourced from the database; web facts only describe): the
    numbers typed into code that only a web fact supplied (not the user's words, not a value the data returned)."""
    web, data, user = list(web_numbers), list(data_numbers), _user_numbers(user_text)
    out: list[float] = []
    for typed in values:
        if typed.kind != "NUMBER":
            continue
        value = float(typed.value)
        if value in (0.0, 1.0, -1.0) or value in out or not _close(value, web) or _close(value, user) \
                or _close(value, data):
            continue
        out.append(value)
    return out


def classify(values: list[Typed], user_text: str, seen_strings: set[str], seen_sets: set[frozenset[str]],
             seen_numbers: Iterable[float], web_strings: set[str] | frozenset[str] = frozenset(),
             web_sets: set[frozenset[str]] | frozenset[frozenset[str]] = frozenset()) -> list[dict[str, Any]]:
    """The AI_CHOICE values, each once: {"kind", "value", "position"}. USER and DATA values are not returned. A text
    or list only a web fact supplied (P34: web facts describe, they are not data) is returned with "origin": "WEB"."""
    words = {w.upper() for w in WORD_RE.findall(user_text or "")}
    user_numbers = _user_numbers(user_text)
    numbers = list(seen_numbers)
    out: list[dict[str, Any]] = []
    shown: set[Any] = set()
    for typed in values:
        if typed.kind == "NUMBER":
            value = float(typed.value)
            if value in (0.0, 1.0, -1.0) or _close(value, user_numbers) or _close(value, numbers):
                continue
            key: Any = ("N", value)
        elif typed.kind == "TEXT":
            text = str(typed.value).strip().upper()
            if not text or text in words or text in seen_strings or all(t in words for t in WORD_RE.findall(text)):
                continue
            key = ("T", text)
            web = text in web_strings
        else:
            items = frozenset(str(v).strip().upper() for v in typed.value)
            if items <= words or items in seen_sets:
                continue
            key = ("L", items)
            web = items in web_sets or bool(items) and items <= web_strings
        if key in shown:
            continue
        shown.add(key)
        out.append({"kind": typed.kind, "value": list(typed.value) if typed.kind == "LIST" else typed.value,
                    "position": typed.position, **({"origin": "WEB"} if typed.kind != "NUMBER" and web else {})})
        if len(out) >= MAX_CHOICES:
            break
    return out


def describe_web(facts: list[dict[str, Any]]) -> str | None:
    """S4b: the web facts the run used, each with its status and domains (written by the system, user_texts)."""
    parts = []
    for fact in facts[:10]:
        versions = fact.get("versions") or []
        if fact.get("status") == "CONFLICTING":
            shown = " vs ".join(f"{v.get('value')} ({', '.join(v.get('domains') or [])})" for v in versions[:3])
        else:
            domains = ", ".join((versions[0].get("domains") or []) if versions else [])
            shown = f"{fact.get('value') or texts.words('NOT_FOUND')}" + (f" ({domains})" if domains else "")
        parts.append(texts.WEB_FACT_ITEM.format(subject=fact.get("subject"), attribute=fact.get("attribute"),
                                                shown=shown, status=texts.words(fact.get("status"))))
    if not parts:
        return None
    return texts.WEB_FACTS_LINE.format(facts="; ".join(parts))


def describe_web_research(lookups: list[dict[str, Any]]) -> str | None:
    """Item 12: the web lookups of research_web the run made: how many, how each ended, the sites (system-written,
    user_texts; the model's search text is not shown, P3 2026-10-08); the values are named where they are shown."""
    return texts.web_lookups_line(lookups[:10])


def describe_web_used(choices: list[dict[str, Any]]) -> str | None:
    """P34: the web-fact values the code used to filter (system-written), or None."""
    parts = [("daftar " + ", ".join(str(v) for v in c["value"][:20]) + (" …" if len(c["value"]) > 20 else ""))
             if c["kind"] == "LIST" else f"nilai '{c['value']}'" for c in choices if c.get("origin") == "WEB"]
    if not parts:
        return None
    return ("Fakta web dipakai di kode (penyaring dari web, bukan dari data pasar; perhitungannya tetap dari "
            "database): " + "; ".join(parts) + ".")


def describe(choices: list[dict[str, Any]]) -> str | None:
    """The system-written line shown in the answer, or None (web-fact values have their own line)."""
    choices = [c for c in choices if c.get("origin") != "WEB"]
    if not choices:
        return None
    parts = []
    for choice in choices:
        value = choice["value"]
        if choice["kind"] == "LIST":
            parts.append("daftar " + ", ".join(str(v) for v in value[:20]) + (" …" if len(value) > 20 else ""))
        elif choice["kind"] == "NUMBER":
            shown = f"{value:g}"
            name = choice["position"].split(":", 1)[-1]
            parts.append(f"{name} {shown}" if choice["position"].startswith("CALL:") else f"ambang {shown}")
        else:
            parts.append(f"nilai '{value}'")
    return ("Pilihan AI (nilai yang diketik AI di kodenya, bukan dari pesan Anda dan bukan hasil dari data): "
            + "; ".join(parts) + ".")
