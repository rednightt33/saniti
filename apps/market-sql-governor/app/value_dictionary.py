"""EXEC-IMPL-1016 Fase 3 (O1, user decisions 2026-10-15: "setiap WHERE = '' maka harus wajib menggunakan value dari get
dimension value, or else rejected"; "user bilang BRI, tapi kode tickernya BBRI ... How we handle this?"; matching
"Alias + persis + potongan", no pg_trgm): the stored values of every filterable text column the catalog offers, and
the names and aliases of entity codes, derived at run time from what the database already holds.

Sources, in order (none is a list typed in code):
- a single-column CHECK list (complete by construction);
- a static table's own values (its entity column and its groupable text columns, complete up to VALUE_DOMAIN_MAX);
- a dated table's entity column: the entities AI_data_coverage registered for that table, together with the codes of
  the static reference table a catalog relationship joins it to (complete: a code in neither has no rows);
- a dated table's other code column joined to a static reference key (a broker code): the reference codes, marked
  incomplete, because a traded code may be missing from a current-state profile (a warning, never a refusal).

Names come from the static tables' AI_column_catalog.entity_name column; each name gives generated aliases (its
initials when it has three words or more, and the name without its legal form), and AI_entity_alias adds curated
ones. An alias that points to several codes is ambiguous and is returned as candidates, never resolved silently.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from psycopg import sql

from .catalog_contract import CHECK_SQL, VALUE_DOMAIN_MAX, VALUE_TEXT_TYPES, Runner, check_value_lists

CACHE_SECONDS = 300.0
MAX_TERMS = 10
MAX_CANDIDATES = 8
# an entity column (tickers, broker codes, warrants included) is a code list, not a category: bounded higher
ENTITY_DOMAIN_MAX = 20_000
# aliases that are a whole name: searched in the Governor, not carried in the contract
NAME_ALIASES = frozenset({"NAME", "SHORT_NAME"})
# a legal form or share class around a company name, not part of what people call it (Indonesian and English forms)
LEGAL_FORM_RE = re.compile(r"^\s*PT\.?\s+|\s+Tbk\.?\s*$|\([^)]*\)|\bClass\s+[A-Z]\b|\bTbk\b", re.IGNORECASE)
WORD_RE = re.compile(r"[^\W\d_][\w'.]*", re.UNICODE)

# only tables this role can read: a table it cannot read has no values to offer (and must not fail the contract)
TABLES_SQL = """
SELECT table_name, entity_column, time_column FROM public."AI_table_catalog"
WHERE is_active AND ai_access_level = 'BOUNDED_READ'
  AND CASE WHEN to_regclass(format('public.%%I', table_name)) IS NULL THEN false
           ELSE has_table_privilege(to_regclass(format('public.%%I', table_name)), 'SELECT') END
"""
COLUMNS_SQL = """
SELECT table_name, column_name, data_type, group_by_allowed, filter_allowed{entity_name}
FROM public."AI_column_catalog" WHERE ai_allowed AND NOT is_sensitive
"""
PRESENT_SQL = """
SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'AI_column_catalog' AND column_name = 'entity_name') AS entity_name,
       COALESCE(has_table_privilege(to_regclass('public."AI_entity_alias"'), 'SELECT'), false) AS aliases,
       COALESCE(has_table_privilege(to_regclass('public."AI_data_coverage"'), 'SELECT'), false) AS coverage
"""
RELATIONSHIPS_SQL = """
SELECT left_table, left_columns, right_table, right_columns FROM public."AI_catalog_relationships"
"""
COVERAGE_SQL = """
SELECT dataset_name, entity_id FROM public."AI_data_coverage"
WHERE coverage_scope = 'ENTITY' AND entity_id IS NOT NULL
"""
ALIASES_SQL = 'SELECT table_name, column_name, code, alias, alias_type FROM public."AI_entity_alias"'


def fold(text: Any) -> str:
    """Lower case with single spaces: the form values, names and aliases are matched in."""
    return " ".join(str(text or "").casefold().split())


def short_name(name: str) -> str:
    """The name people use: without its legal form and share class ("PT Bank Rakyat Indonesia (Persero) Tbk Class B"
    -> "Bank Rakyat Indonesia")."""
    previous, text = None, str(name or "")
    while previous != text:
        previous, text = text, LEGAL_FORM_RE.sub(" ", text)
    return " ".join(text.split())


def initials(short: str) -> str | None:
    """The initials of a name of three words or more ("Bank Rakyat Indonesia" -> "BRI"); shorter names give none, so a
    two-letter alias never stands for a whole name."""
    words = WORD_RE.findall(short)
    return "".join(w[0] for w in words).upper() if len(words) >= 3 else None


@dataclass
class Domain:
    values: list[str]
    source: str
    complete: bool
    kind: str  # CATEGORY or ENTITY
    names: dict[str, str] = field(default_factory=dict)  # code -> display name
    aliases: dict[str, dict[str, str]] = field(default_factory=dict)  # folded alias -> {code: alias type}

    def contract(self) -> dict[str, Any]:
        """What the catalog contract carries: values, source, completeness and, for entity codes, the short aliases
        (initials and curated ones; the sandbox names candidates from them when a value is not stored). Full names
        stay in the Governor (search-values), so the contract stays small."""
        out: dict[str, Any] = {"values": self.values, "source": self.source, "complete": self.complete,
                               "kind": self.kind}
        short = {alias: sorted(codes) for alias, codes in self.aliases.items()
                 if any(kind not in NAME_ALIASES for kind in codes.values())}
        if short:
            out["aliases"] = short
        return out


@dataclass
class Dictionary:
    domains: dict[str, dict[str, Domain]]
    built_at: float

    def domain(self, table: str, column: str) -> Domain | None:
        return (self.domains.get(table) or {}).get(column)

    def search(self, table: str, column: str, terms: list[str]) -> dict[str, Any]:
        """Each term against one column: the stored value it equals (letter case aside), the codes an alias of it
        names, and candidates whose value or name contains it. Values only, never counts."""
        domain = self.domain(table, column)
        if domain is None:
            return {"status": "REJECTED", "reason_code": "NO_VALUE_LIST", "table": table, "column": column,
                    "message": f"{table}.{column} has no stored value list (not a filterable text column of an "
                               "approved table)."}
        folded_values = {}
        for value in domain.values:
            folded_values.setdefault(fold(value), []).append(value)
        results = []
        for term in terms[:MAX_TERMS]:
            key = fold(term)
            exact = folded_values.get(key, [])
            named = domain.aliases.get(key, {})
            alias = [{"code": code, "name": domain.names.get(code), "alias_type": kind}
                     for code, kind in sorted(named.items())]
            candidates: list[dict[str, Any]] = []
            if key and not exact and len(named) != 1:
                seen = set(named)
                found_codes = [v for v in domain.values if key in fold(v)]
                found_codes += sorted({code for alias_key, codes in domain.aliases.items() if key in alias_key
                                       for code in codes})
                for code in sorted(dict.fromkeys(found_codes), key=lambda c: (not fold(c).startswith(key), len(c), c)):
                    if code not in seen:
                        seen.add(code)
                        candidates.append({"value": code, "name": domain.names.get(code)})
                candidates = candidates[:MAX_CANDIDATES]
            value = exact[0] if len(exact) == 1 else (next(iter(named)) if not exact and len(named) == 1 else None)
            results.append({"term": term, "found": value is not None, "value": value,
                            "matched_by": "VALUE" if exact else ("ALIAS" if value else None),
                            "ambiguous": len(exact) > 1 or (not exact and len(named) > 1),
                            "alias": alias, "candidates": candidates})
        return {"status": "VALUES_FOUND", "table": table, "column": column, "kind": domain.kind,
                "source": domain.source, "complete": domain.complete, "results": results,
                "note": "Stored values, names and aliases for scope predicates; never counts or facts. A term that "
                        "is not found, or is ambiguous, is not a stored value: use a candidate or ask the user."}


def build(run: Runner) -> Dictionary:
    present = (run(PRESENT_SQL, ()) or [{}])[0]
    tables = {r["table_name"]: r for r in run(TABLES_SQL, ())}
    columns: dict[str, dict[str, dict[str, Any]]] = {}
    for row in run(COLUMNS_SQL.format(entity_name=", entity_name" if present.get("entity_name") else ""), ()):
        if row["table_name"] in tables:
            columns.setdefault(row["table_name"], {})[row["column_name"]] = row
    checks = check_value_lists([(r["table_name"], r["definition"]) for r in run(CHECK_SQL, (sorted(tables),))])
    domains: dict[str, dict[str, Domain]] = {}
    static = {name for name, meta in tables.items() if not meta["time_column"]}

    def text(info: dict[str, Any]) -> bool:
        return str(info.get("data_type") or "").lower() in VALUE_TEXT_TYPES and bool(info.get("filter_allowed"))

    # static tables: their own values, and the names of their entities (a history table gives former names too)
    names: dict[tuple[str, str], dict[str, list[str]]] = {}
    for name in sorted(static):
        meta, known = tables[name], columns.get(name) or {}
        entity = meta["entity_column"]
        for column, info in known.items():
            if not text(info) or (column != entity and not info.get("group_by_allowed")):
                continue
            listed = (checks.get(name) or {}).get(column)
            if listed is not None:
                domains.setdefault(name, {})[column] = Domain(listed, "CHECK_CONSTRAINT", True, "CATEGORY")
                continue
            bound = ENTITY_DOMAIN_MAX if column == entity else VALUE_DOMAIN_MAX
            query = sql.SQL("SELECT DISTINCT {c} AS value FROM public.{t} WHERE {c} IS NOT NULL LIMIT {n}").format(
                c=sql.Identifier(column), t=sql.Identifier(name), n=sql.Literal(bound + 1))
            values = sorted(str(r["value"]) for r in run(query.as_string(None), ()))
            complete = len(values) <= bound
            domains.setdefault(name, {})[column] = Domain(values if complete else [], "STATIC_TABLE", complete,
                                                          "ENTITY" if column == entity else "CATEGORY")
        label = next((c for c, info in known.items() if info.get("entity_name")), None)
        if entity and label:
            query = sql.SQL("SELECT DISTINCT {e} AS code, {n} AS name FROM public.{t} WHERE {e} IS NOT NULL "
                            "AND {n} IS NOT NULL ORDER BY 1, 2").format(
                e=sql.Identifier(entity), n=sql.Identifier(label), t=sql.Identifier(name))
            mapping: dict[str, list[str]] = {}
            for row in run(query.as_string(None), ()):
                mapping.setdefault(str(row["code"]), []).append(str(row["name"]))
            names[(name, entity)] = mapping
    # CHECK lists of dated tables
    for name, listed_columns in checks.items():
        for column, values in listed_columns.items():
            info = (columns.get(name) or {}).get(column)
            if name not in static and info and text(info):
                domains.setdefault(name, {})[column] = Domain(values, "CHECK_CONSTRAINT", True, "CATEGORY")
    # dated code columns joined to a static reference key (one column pair); a column may join several (a current
    # profile and its history), and takes the codes and names of all of them
    references: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for rel in run(RELATIONSHIPS_SQL, ()):
        left, right = list(rel["left_columns"] or []), list(rel["right_columns"] or [])
        if len(left) != 1 or len(right) != 1:
            continue
        for (ref_table, ref_column), (table, column) in (((rel["left_table"], left[0]), (rel["right_table"], right[0])),
                                                         ((rel["right_table"], right[0]), (rel["left_table"], left[0]))):
            if ref_table in static and table in tables and table not in static \
                    and ref_column == tables[ref_table]["entity_column"] \
                    and (ref_table, ref_column) not in references.setdefault((table, column), []):
                references[(table, column)].append((ref_table, ref_column))
    for refs in references.values():
        refs.sort()
    coverage: dict[str, set[str]] = {}
    for row in run(COVERAGE_SQL, ()) if present.get("coverage") else ():
        coverage.setdefault(row["dataset_name"], set()).add(str(row["entity_id"]))
    for name in sorted(set(tables) - static):
        meta, known = tables[name], columns.get(name) or {}
        for column, info in known.items():
            if not text(info) or (name in domains and column in domains[name]):
                continue
            refs = references.get((name, column), [])
            ref_values: set[str] = set()
            for ref in refs:
                ref_domain = domains.get(ref[0], {}).get(ref[1])
                ref_values |= set(ref_domain.values) if ref_domain else set()
            if column == meta["entity_column"] and coverage.get(name):
                domains.setdefault(name, {})[column] = Domain(sorted(coverage[name] | ref_values), "COVERAGE", True,
                                                              "ENTITY")
            elif ref_values:
                domains.setdefault(name, {})[column] = Domain(sorted(ref_values), "REFERENCE_TABLE", False, "ENTITY")
    curated: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if present.get("aliases"):
        for row in run(ALIASES_SQL, ()):
            curated.setdefault((row["table_name"], row["column_name"]), []).append(row)
    # names and aliases: an entity column takes those of its own table and of every reference it joins
    for name, by_column in domains.items():
        for column, domain in by_column.items():
            if domain.kind != "ENTITY":
                continue
            sources = [(name, column)] + references.get((name, column), [])
            for source in sources:
                for code, labels in (names.get(source) or {}).items():
                    domain.names.setdefault(code, labels[0])
                    for label in labels:
                        short = short_name(label)
                        for alias, kind in ((initials(short), "ACRONYM"), (short, "SHORT_NAME"), (label, "NAME")):
                            if alias and fold(alias) != fold(code):
                                domain.aliases.setdefault(fold(alias), {}).setdefault(code, kind)
            for source in sources:
                for row in curated.get(source, []):
                    domain.aliases.setdefault(fold(row["alias"]), {})[str(row["code"])] = str(row["alias_type"])
    return Dictionary(domains, time.monotonic())


class DictionaryCache:
    """One dictionary per Governor process, rebuilt after CACHE_SECONDS (a static table changes with its data, the
    coverage after the daily job)."""

    def __init__(self, seconds: float = CACHE_SECONDS) -> None:
        self.seconds = seconds
        self._lock = threading.Lock()
        self._value: Dictionary | None = None

    def get(self, run: Runner) -> Dictionary:
        with self._lock:
            if self._value is None or time.monotonic() - self._value.built_at > self.seconds:
                self._value = build(run)
            return self._value
