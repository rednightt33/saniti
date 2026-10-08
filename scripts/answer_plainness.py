"""M125 C measure (2026-10-08): how much internal vocabulary reaches the user in saved answers, and how hard they
read. The vocabulary is derived, not listed: table and column names from DATABASE_SCHEMA.md (the live catalog's
export), backend codes from the orc's schema enums, internal ids by their shapes. A new table, column or code is
counted without a change here.

    python scripts/answer_plainness.py runs.json [more.json ...]   # dumps written by the GT runner (key -> {body})
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "DATABASE_SCHEMA.md"
ORC_APP = ROOT / "apps" / "market-ai-orc" / "app"

TABLE = re.compile(r"^## ([A-Za-z][A-Za-z0-9_]+)\s*$", re.M)
COLUMN = re.compile(r"^\| `([A-Za-z][A-Za-z0-9_]+)` \|", re.M)
# a backend code: an upper-case string literal of the orc, joined by underscores or long enough not to be a ticker
CODE_IN_SOURCE = re.compile(r'"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{6,})"')
IDS = re.compile(r"\b(?:out\.o\d+|(?:exe|ana|cmp|conv|edge|draft|rp|spec|dn|bundle|sess)_[0-9a-f]{6,})\b")
SNAKE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
SENTENCE = re.compile(r"[^.!?\n]+[.!?]")
ENGLISH = re.compile(r"\b(the|was|were|is|are|of|and|which|that|this|its|from|with)\b", re.I)


def vocabulary() -> dict[str, set[str]]:
    schema = SCHEMA.read_text(encoding="utf-8")
    tables = set(TABLE.findall(schema)) - {"Tables", "Logical", "Columns"}
    # a column name is internal when it is not an everyday word: it holds an underscore or capitals inside
    columns = {c for c in COLUMN.findall(schema) if "_" in c or re.search(r"[a-z][A-Z]", c)} - tables
    codes = set()
    for path in ORC_APP.rglob("*.py"):
        codes |= set(CODE_IN_SOURCE.findall(path.read_text(encoding="utf-8")))
    return {"tables": tables, "columns": columns, "codes": codes}


def answers(paths: list[str]):
    for path in paths:
        for key, item in json.loads(Path(path).read_text(encoding="utf-8")).items():
            body = item.get("body", item) if isinstance(item, dict) else {}
            response = (body or {}).get("response") or {}
            text = "\n".join(filter(None, [response.get("answer"), response.get("clarification_question")]))
            if text:
                yield f"{Path(path).stem}:{key}", text


def measure(text: str, vocab: dict[str, set[str]]) -> dict[str, object]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9_]+", text))
    found = {kind: sorted(words & names) for kind, names in vocab.items()}
    found["ids"] = sorted(set(IDS.findall(text)))
    found["snake_case"] = sorted(set(SNAKE.findall(text)) - set(found["columns"]))
    sentences = [s for s in SENTENCE.findall(text) if len(s.split()) > 2]
    return {"internal": sum(len(v) for v in found.values()), "found": {k: v for k, v in found.items() if v},
            "words_per_sentence": round(statistics.mean(len(s.split()) for s in sentences), 1) if sentences else None,
            "english_words": len(ENGLISH.findall(text)), "chars": len(text)}


def main(paths: list[str]) -> None:
    vocab = vocabulary()
    rows = [(name, measure(text, vocab)) for name, text in answers(paths)]
    if not rows:
        raise SystemExit("no answers found")
    with_internal = [r for r in rows if r[1]["internal"]]
    wps = [r[1]["words_per_sentence"] for r in rows if r[1]["words_per_sentence"]]
    print(f"answers {len(rows)}; with internal names {len(with_internal)} ({100 * len(with_internal) // len(rows)}%); "
          f"internal names per answer {statistics.mean(r[1]['internal'] for r in rows):.2f}; "
          f"words per sentence median {statistics.median(wps):.1f}")
    totals: dict[str, dict[str, int]] = {}
    for _, m in rows:
        for kind, names in m["found"].items():
            for n in names:
                totals.setdefault(kind, {}).setdefault(n, 0)
                totals[kind][n] += 1
    for kind, counts in totals.items():
        top = sorted(counts.items(), key=lambda x: -x[1])[:8]
        print(f"  {kind}: " + ", ".join(f"{n} ×{c}" for n, c in top))


if __name__ == "__main__":
    main(sys.argv[1:])
