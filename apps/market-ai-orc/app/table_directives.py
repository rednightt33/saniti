"""EXEC-TABLE (user decision 2026-10-13, "render tabel dari kode ... OK"): a table instruction in the answer,
{{table out.o9; Sektor = sector; Median = median_pct|pp:2; sort -median_pct; top 10}}, is turned by this module into a
Markdown table whose cells are value references written by code, one per cell, read by the row's position in the
complete released table (rows[_row=N]). value_refs.render then fills them like any other reference, so units, formats,
provenance sources and every gate stay as they are; the model no longer composes the cells one by one (run
edge_517a29: about fifty cell references, three reference checks, one PROVENANCE repair, about three minutes).

The renderer computes nothing: a total row, a derived column or a table that joins several outputs is built and
released in the analysis (emit_table with units=) and then shown with one instruction. Behind
AI_ENABLE_TABLE_DIRECTIVES (default false: the prompt and the behaviour are those before EXEC-TABLE).
"""
from __future__ import annotations

import contextvars
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .value_refs import (FORMATS, UNRESOLVED, ReferenceError_, ReferenceSources, TableRows, _number, display_format,
                         format_value)

TABLE_RE = re.compile(r"\{\{\s*table\b(?P<body>(?:[^{}]|\{[^{}]*\})*)\}\}", re.IGNORECASE)
CELL_RE = re.compile(r"\{\s*(?P<column>[^{}|]+?)\s*(?:\|\s*(?P<fmt>[a-z]+)\s*(?::\s*(?P<places>\d))?)?\s*\}")
COLUMN_RE = re.compile(r"^(?P<column>[^{}|]+?)\s*(?:\|\s*(?P<fmt>[a-z]+)\s*(?::\s*(?P<places>\d))?)?$")
SORT_RE = re.compile(r"^sort\s+(?P<minus>-)?\s*(?P<column>.+)$", re.IGNORECASE)
TOP_RE = re.compile(r"^top\s+(?P<rows>\d+)$", re.IGNORECASE)
# Markdown table separator lines, to count the tables the model still writes cell by cell (logged, never refused)
SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$", re.MULTILINE)
# M185 (user 2026-10-20 "Ok M185 masukan exec untuk solusinya"): a table without top sends every row up to MAX_ROWS;
# EDGE shows ten and folds the rest behind a button (edge_7bdd6096: 10 of 48 rows reached EDGE, the rest unreachable)
DEFAULT_ROWS = 50
# EXEC-ROWS (user 2026-10-13, "Tp mesti ada safe guard kalau seandainya output user = 1000 rows?"; "25 baris"): a
# table in the chat shows at most this many rows whatever top asks; the line below it gives the output's size and, when
# more were asked, says the complete table can be asked for as an Excel file. EXEC-UI-1015 U4 (user 2026-10-15, "malah
# saya mau sampai 50 kalau bisa ... bisa di collapse/expand"): 50; EDGE shows ten and folds the rest
MAX_ROWS = 50
MAX_COLUMNS = 12
EMPTY_CELL = "–"  # a missing value (null, NaN) is shown as a dash, not as a reference
# a column the instruction may name: one a value reference can read (no brace, pipe, bracket or equals sign)
SAFE_COLUMN_RE = re.compile(r"^[^{}|\[\]=]+$")
FOOTER_MARK = "[[tabel-baris-{key}]]"  # letters only: no figure reaches the gates; replaced once they passed
FOOTER_MARK_RE = re.compile(r"\[\[tabel-baris-[a-z]+\]\]")
TABLE_ROWS_LINE = "_Menampilkan {shown} dari {total} baris._"
TABLE_CAPPED_LINE = ("_Menampilkan {shown} dari {total} baris; tabel di chat dibatasi {cap} baris, tabel lengkap bisa "
                     "diminta sebagai file Excel._")
# EXEC-ROWS: a Markdown table the model wrote with a title row and no data row (a stray header before a built table)
EMPTY_TABLE_RE = re.compile(r"(?m)^[ \t]*\|[^\n]*\|[ \t]*\n[ \t]*\|?[ \t]*:?-{3,}[-:| \t]*\|?[ \t]*(?:\n(?![ \t]*\|)|\Z)")

# Refusal templates (EXEC-TABLE): fixed text, details filled in; they join the REFERENCE gate's problems
NO_TABLE = "Table {ref}: no released table has this ref; the released tables are {refs}."
NO_COLUMN = "Table {ref}: column {column} does not exist; its columns are {columns}."
BAD_FORMAT = "Table {ref}: format {format} does not fit column {column} ({kind})."
NO_SORT = "Table {ref}: sort column {column} does not exist; its columns are {columns}."
UNREADABLE = ("Table instruction cannot be read ({why}); write {{{{table out.oN; Title = column|format; ...; "
              "sort -column; top N}}}}.")
FIX_ONLY = " Fix this table instruction only."

# set by the orchestrator for each run with the flag on, read by check_references (a preview of the table)
current_table_directives: contextvars.ContextVar[bool] = contextvars.ContextVar("current_table_directives",
                                                                                default=False)


class DirectiveError(ValueError):
    """A table instruction that cannot be turned into a table; the message is one of the templates above."""


@dataclass
class Column:
    title: str
    cells: list[tuple[str, str | None, int | None]]  # (column, format, places) in the order they appear
    pattern: str | None = None  # a joined cell: "{n|int} ({share|pct:1})"; None for one column


@dataclass
class Directive:
    ref: str
    columns: list[Column]
    sort: str | None = None
    descending: bool = False
    top: int = DEFAULT_ROWS
    asked: int = DEFAULT_ROWS  # EXEC-ROWS: the rows top asked for before MAX_ROWS


@dataclass
class Expansion:
    text: str
    problems: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # the instructions that could not be shown
    tables: list[dict[str, Any]] = field(default_factory=list)  # logged: ref, rows shown, row count, columns
    refs: list[str] = field(default_factory=list)  # the tables shown (cited as evidence, not every cell)
    footers: dict[str, str] = field(default_factory=dict)  # mark -> line, put in once the gates passed
    layouts: list[dict[str, Any]] = field(default_factory=list)  # EXEC-IMPL-1016 4.2: the shown tables' shape for EDGE
    count: int = 0  # instructions read
    unwrapped: int = 0  # (a)+(b): instructions taken out of a Markdown table the model wrapped around them


# (a)+(b) (user 2026-10-20 "A ok masukan exec"; edge_b6559a4f: Qwen typed a Markdown title row and put the instruction
# in a cell, "| {{table ...}} |", so the built table came out between stray pipes, and typed its own "Menampilkan 10
# dari 29 baris" beside the system's): the instruction stands on its own line and the rows line is the system's
WRAPPED_RE = re.compile(r"(?m)^[ \t]*\|[ \t]*(?P<directive>\{\{\s*table\b(?:[^{}]|\{[^{}]*\})*\}\})[ \t]*(?:\|[ \t]*)*$")
TYPED_ROWS_LINE_RE = re.compile(r"(?mi)^[ \t]*[_*]*\(?(?:menampilkan|showing)\s+\d[\d.,]*\s+(?:dari|of)\s+\d[\d.,]*\s+"
                                r"(?:baris|rows)\b[^\n]*$\n?")


def unwrap(text: str) -> tuple[str, int]:
    """The instructions the model put inside a Markdown table cell, back on their own line, and the rows lines it
    typed itself removed (the system writes its own under a cut table); returns the text and how many changed. The
    title row the model typed above is then an empty table, which drop_empty_tables removes."""
    text, wrapped = WRAPPED_RE.subn(lambda m: m.group("directive"), text)
    text, typed = TYPED_ROWS_LINE_RE.subn("", text)
    return text, wrapped + typed


def typed_tables(text: str | None) -> int:
    """The Markdown tables the text writes itself (the model's cell-by-cell tables), counted by separator line."""
    return len(SEPARATOR_RE.findall(text or ""))


def parse(body: str) -> Directive:
    parts = [p.strip() for p in body.split(";")]
    if not parts or not parts[0]:
        raise DirectiveError(UNREADABLE.format(why="it names no table"))
    ref, columns, sort, descending, top = parts[0], [], None, False, DEFAULT_ROWS
    if " " in ref or "=" in ref:
        raise DirectiveError(UNREADABLE.format(why=f"'{ref}' is not a table ref; separate the parts with ;"))
    for part in parts[1:]:
        if not part:
            continue
        if "=" not in part:
            sort_match, top_match = SORT_RE.match(part), TOP_RE.match(part)
            if sort_match:
                sort, descending = sort_match.group("column").strip(), bool(sort_match.group("minus"))
            elif top_match:
                top = int(top_match.group("rows"))
                if top < 1:
                    raise DirectiveError(UNREADABLE.format(why="top must be at least one row"))
            else:
                raise DirectiveError(UNREADABLE.format(why=f"'{part}' is neither Title = column, sort nor top"))
            continue
        title, cell = (x.strip() for x in part.split("=", 1))
        if not title or not cell:
            raise DirectiveError(UNREADABLE.format(why=f"'{part}' needs a title and a column"))
        if "{" in cell:
            cells = [(m.group("column").strip(), m.group("fmt"),
                      int(m.group("places")) if m.group("places") else None) for m in CELL_RE.finditer(cell)]
            if not cells or "{" in CELL_RE.sub("", cell) or "}" in CELL_RE.sub("", cell):
                raise DirectiveError(UNREADABLE.format(why=f"'{cell}' joins columns as {{column|format}}"))
            columns.append(Column(title, cells, pattern=cell))
            continue
        match = COLUMN_RE.match(cell)
        if not match:
            raise DirectiveError(UNREADABLE.format(why=f"'{cell}' is not column or column|format"))
        columns.append(Column(title, [(match.group("column").strip(), match.group("fmt"),
                                       int(match.group("places")) if match.group("places") else None)]))
    if not columns:
        raise DirectiveError(UNREADABLE.format(why="it shows no column"))
    if len(columns) > MAX_COLUMNS:
        raise DirectiveError(UNREADABLE.format(why=f"at most {MAX_COLUMNS} columns"))
    return Directive(ref, columns, sort, descending, min(top, MAX_ROWS), top)


def _table(sources: ReferenceSources, ref: str) -> tuple[list[dict[str, Any]], int, bool]:
    """The rows of the released table ref names, its row count, and whether rows are read by _row (a TableRows)."""
    try:
        namespace, key, rest = sources._locate(ref)
    except ReferenceError_:
        namespace, key, rest = "", "", []
    entry = sources.objects.get(namespace, {}).get(key) if not rest else None
    holder = entry[0] if entry else None
    rows = holder.get("rows") if isinstance(holder, dict) else None
    if isinstance(rows, TableRows):
        read = [r for r in rows.all() if isinstance(r, dict)]
        return read, max(rows.row_count or 0, len(read)), True
    if isinstance(rows, list) and all(isinstance(r, dict) for r in rows):
        return rows, len(rows), False
    tables = [r for r in sources.refs("out")][:12]
    raise DirectiveError(NO_TABLE.format(ref=ref, refs=", ".join(tables) or "none yet (release one first)"))


def _kind(rows: list[dict[str, Any]], column: str) -> str:
    """TEXT when a non-empty value of the column is not a number, else NUMBER."""
    for row in rows:
        value = row.get(column)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, str) and _number(value) is None:
            return "TEXT"
    return "NUMBER"


def _sort_key(value: Any) -> tuple[int, Any]:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return (2, 0)
    number = _number(value) if not isinstance(value, bool) else None
    if number is not None:
        return (0, number)
    return (1, str(value).lower())


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, float) and not math.isfinite(value))


def build(directive: Directive, sources: ReferenceSources, layout: dict[str, Any] | None = None
          ) -> tuple[str, int, int]:
    """The Markdown table with one generated reference per cell; (table, rows shown, rows in the output). layout, when
    given, receives the table's shape for EDGE (EXEC-IMPL-1016 Fase 4.2): each shown column's title and the output
    column of its first cell, and each shown row's position in the complete released table."""
    rows, row_count, positional = _table(sources, directive.ref)
    present = list(dict.fromkeys(c for row in rows[:50] for c in row if c != "_row"))
    listed = ", ".join(present[:30]) or "none"
    for column in directive.columns:
        for name, fmt, _ in column.cells:
            if name not in present:
                raise DirectiveError(NO_COLUMN.format(ref=directive.ref, column=name, columns=listed))
            if not SAFE_COLUMN_RE.match(name):
                raise DirectiveError(BAD_FORMAT.format(ref=directive.ref, format=fmt or "-", column=name,
                                                       kind="its name cannot be referenced; rename it in the "
                                                            "analysis"))
            if fmt is None:
                continue
            if fmt not in FORMATS:
                raise DirectiveError(BAD_FORMAT.format(ref=directive.ref, format=fmt, column=name,
                                                       kind="unknown format; use one of "
                                                            + ", ".join(sorted(FORMATS))))
            if _kind(rows, name) == "TEXT":
                raise DirectiveError(BAD_FORMAT.format(ref=directive.ref, format=fmt, column=name,
                                                       kind="a text column; write it without a format"))
            try:
                display_format(fmt, sources.unit(f"{directive.ref}.rows[_row=0].{name}"))
            except ReferenceError_ as exc:
                raise DirectiveError(BAD_FORMAT.format(ref=directive.ref, format=fmt, column=name,
                                                       kind=str(exc))) from exc
    positions = {id(row): i for i, row in enumerate(rows)}  # a list's rows are read by their index
    if directive.sort is not None:
        if directive.sort not in present:
            raise DirectiveError(NO_SORT.format(ref=directive.ref, column=directive.sort, columns=listed))
        ordered = sorted(rows, key=lambda r: _sort_key(r.get(directive.sort)))
        if directive.descending:  # the empty values stay last either way
            filled = [r for r in ordered if _sort_key(r.get(directive.sort))[0] < 2]
            ordered = list(reversed(filled)) + [r for r in ordered if _sort_key(r.get(directive.sort))[0] == 2]
        rows = ordered
    shown = rows[:directive.top]

    def cell(row: dict[str, Any], index: int, name: str, fmt: str | None, places: int | None) -> str:
        value = row.get(name)
        if _empty(value):
            return EMPTY_CELL
        if isinstance(value, str) and ("|" in value or "\n" in value) and _number(value) is None:
            # a text that would break the Markdown row is written as it is, its separators made plain
            return " ".join(value.replace("|", "/").split())
        address = f"rows[_row={row['_row']}]" if positional and "_row" in row else f"rows.{index}"
        written = f"{fmt}:{places}" if fmt and places is not None else fmt
        return "{{" + f"{directive.ref}.{address}.{name}" + (f"\\|{written}" if written else "") + "}}"

    lines = ["| " + " | ".join(c.title.replace("|", "/") for c in directive.columns) + " |",
             "|" + "---|" * len(directive.columns)]
    for row in shown:
        position = positions[id(row)]
        cells = []
        for column in directive.columns:
            if column.pattern is None:
                cells.append(cell(row, position, *column.cells[0]))
                continue
            parts = iter(column.cells)
            cells.append(CELL_RE.sub(lambda _m: cell(row, position, *next(parts)), column.pattern))
        lines.append("| " + " | ".join(cells) + " |")
    if layout is not None:
        layout.update(titles=[c.title.replace("|", "/") for c in directive.columns],
                      columns=[c.cells[0][0] for c in directive.columns],
                      rows=[row.get("_row", positions[id(row)]) if positional else positions[id(row)]
                            for row in shown])
    return "\n".join(lines), len(shown), row_count


def _mark(n: int) -> str:
    key = ""
    n += 1
    while n:
        n, rest = divmod(n - 1, 26)
        key = chr(ord("a") + rest) + key
    return FOOTER_MARK.format(key=key)


def expand(text: str | None, sources: ReferenceSources, marks: bool = True) -> Expansion:
    """Every table instruction of text turned into its table. With marks the line under a cut table is a mark
    (FOOTER_MARK) replaced by put_footers once the gates passed; without (check_references) it is the line itself. An
    instruction that cannot be shown becomes UNRESOLVED and its problem is reported (the REFERENCE gate's repair)."""
    out = Expansion(text or "")
    if not text or not TABLE_RE.search(text):
        return out
    text, out.unwrapped = unwrap(text)

    def replace(match: re.Match[str]) -> str:
        out.count += 1
        try:
            directive = parse(match.group("body"))
            layout: dict[str, Any] = {}
            table, shown, total = build(directive, sources, layout)
        except DirectiveError as exc:
            out.problems.append(str(exc) + FIX_ONLY)
            out.failed.append(match.group(0)[:200])
            return UNRESOLVED
        out.refs.append(directive.ref)
        out.tables.append({"ref": directive.ref, "rows": shown, "row_count": total,
                           "columns": len(directive.columns)})
        out.layouts.append({"ref": directive.ref, **layout})
        footer = ""
        if total > shown:
            template = TABLE_CAPPED_LINE if directive.asked > MAX_ROWS else TABLE_ROWS_LINE
            line = template.format(shown=format_value(shown, "int"), total=format_value(total, "int"),
                                   cap=format_value(MAX_ROWS, "int"))
            if marks:
                mark = _mark(len(out.footers))
                out.footers[mark] = line
                footer = "\n\n" + mark
            else:
                footer = "\n\n" + line
        return "\n\n" + table + footer + "\n\n"

    expanded = TABLE_RE.sub(replace, text)
    out.text = re.sub(r"\n{3,}", "\n\n", expanded).strip("\n") if out.tables or out.failed else expanded
    return out


def drop_empty_tables(text: str | None) -> tuple[str | None, int]:
    """EXEC-ROWS: Markdown tables with a title row and no data row removed (a model wrote one above a built table: the
    reader saw the titles twice); returns the text and how many were removed."""
    if not text or "|" not in text:
        return text, 0
    cleaned, count = EMPTY_TABLE_RE.subn("", text)
    return (re.sub(r"\n{3,}", "\n\n", cleaned) if count else text), count


def put_footers(text: str | None, footers: dict[str, str]) -> str | None:
    """The line under each cut table, once the gates passed; a mark without its line is removed."""
    if not text or "[[tabel-baris-" not in text:
        return text
    return FOOTER_MARK_RE.sub(lambda m: footers.get(m.group(0), ""), text)
