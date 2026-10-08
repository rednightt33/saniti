"""M125 C measure (2026-10-08): how much internal vocabulary reaches the user in saved answers, and how hard they
read. The vocabulary is derived, not listed: table and column names from DATABASE_SCHEMA.md (the live catalog's
export), backend codes from the orc's schema enums, internal ids by their shapes. A new table, column or code is
counted without a change here.

    python scripts/answer_plainness.py runs.json [more.json ...]   # dumps written by the GT runner (key -> {body})

P5 (2026-10-08): every text the reader sees is measured, not only the answer: the clarification question, assumptions,
limitations, methodology, the research findings' readings and the evidence labels of the Sources panel. The English
share is the share of words that are common English function words (the reader writes Indonesian).
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


READER_FIELDS = ("answer", "clarification_question", "assumptions", "limitations", "methodology")
FINDING_PARTS = ("answer", "evidence", "usefulness", "follow_up")


def reader_texts(body: dict) -> dict[str, str]:
    """Every text of one response that the reader sees, by where it is shown."""
    response = body.get("response") or {}
    texts = {}
    for name in READER_FIELDS:
        value = response.get(name)
        value = "\n".join(x for x in value if isinstance(x, str)) if isinstance(value, list) else value
        if isinstance(value, str) and value.strip():
            texts[name] = value
    findings = [str((f.get("interpretation") or {}).get(part) or "") for f in response.get("research_findings") or []
                if isinstance(f, dict) for part in FINDING_PARTS]
    if any(findings):
        texts["findings"] = "\n".join(x for x in findings if x)
    labels = [str(e.get("label") or "") for e in body.get("evidence") or [] if isinstance(e, dict)]
    if any(labels):
        texts["evidence_labels"] = "\n".join(x for x in labels if x)
    return texts


def answers(paths: list[str]):
    for path in paths:
        for key, item in json.loads(Path(path).read_text(encoding="utf-8")).items():
            body = item.get("body", item) if isinstance(item, dict) else {}
            texts = reader_texts(body or {})
            if texts:
                yield f"{Path(path).stem}:{key}", texts


def measure(text: str, vocab: dict[str, set[str]]) -> dict[str, object]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9_]+", text))
    found = {kind: sorted(words & names) for kind, names in vocab.items()}
    found["ids"] = sorted(set(IDS.findall(text)))
    found["snake_case"] = sorted(set(SNAKE.findall(text)) - set(found["columns"]))
    sentences = [s for s in SENTENCE.findall(text) if len(s.split()) > 2]
    total = len(re.findall(r"\w+", text)) or 1
    return {"internal": sum(len(v) for v in found.values()), "found": {k: v for k, v in found.items() if v},
            "words_per_sentence": round(statistics.mean(len(s.split()) for s in sentences), 1) if sentences else None,
            "english_words": len(ENGLISH.findall(text)), "english_share": len(ENGLISH.findall(text)) / total,
            "chars": len(text)}


def main(paths: list[str]) -> None:
    vocab = vocabulary()
    measured = [(name, {field: measure(text, vocab) for field, text in texts.items()}) for name, texts in answers(paths)]
    if not measured:
        raise SystemExit("no answers found")
    rows = [(name, measure("\n".join(texts.values()), vocab)) for name, texts in answers(paths)]
    by_field: dict[str, list[dict]] = {}
    for _, fields in measured:
        for field, m in fields.items():
            by_field.setdefault(field, []).append(m)
    for field, ms in by_field.items():
        print(f"  [{field}] {len(ms)} texts; with internal names {sum(1 for m in ms if m['internal'])}; "
              f"English share {100 * statistics.mean(m['english_share'] for m in ms):.1f}%")
    with_internal = [r for r in rows if r[1]["internal"]]
    wps = [r[1]["words_per_sentence"] for r in rows if r[1]["words_per_sentence"]]
    print(f"answers {len(rows)}; with internal names {len(with_internal)} ({100 * len(with_internal) // len(rows)}%); "
          f"internal names per answer {statistics.mean(r[1]['internal'] for r in rows):.2f}; "
          f"words per sentence median {statistics.median(wps):.1f}; "
          f"English share {100 * statistics.mean(r[1]['english_share'] for r in rows):.1f}%")
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
