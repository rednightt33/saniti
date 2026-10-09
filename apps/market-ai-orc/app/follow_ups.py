"""EXEC-Y Fase 2: follow-up questions, insight ideas and one data test after an answer (user decisions 2026-10-09:
"untuk jalur explore harus tambahkan pertanyaan agar user bisa explore lebih lanjut"; "analysis OK"; "maksudnya bukan
idea research, tapi ide untuk pertanyaan insight lanjutan"; "explore pakai B").

One small router-model call (orchestrator.suggest_follow_ups: AI_MODEL, reasoning low, strict schema, no tools) after an
answer of a data route (ANALYSIS, EXPLORE, an INSIGHT or CONTINUE turn), never after a plan, a question, a fact, a chat,
a pause or a stopped answer. It returns:
  - FOLLOW_UP: 3-5 questions worth asking next (the /v1/ask questions of EXPLORE are candidates);
  - INSIGHT_IDEA: 2-3 questions the data already read can answer (a comparison, a breakdown, a trend, a driver), each
    naming the tables it uses; an idea naming a table this conversation did not read is dropped, so ideas are derived
    from the data at hand, new tables included, without a list in code;
  - DATA_TEST: in EXPLORE's first round with figures from data, one testable hypothesis ("Uji dengan data: ..."), the
    research plan of option B that is only built when the user clicks it.
A click sends the label as the next message; the turn router reads it like any message (judgement stays with the model,
EXEC-D). Nothing runs before the click. Any failure leaves the answer without suggestions.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import user_texts as texts

MAX_FOLLOW_UPS = 5
MAX_IDEAS = 3
MAX_LABEL = 300
ANSWER_CHARS = 6000
MAX_TABLES = 12
MAX_COLUMNS = 40
DATA_ROUTES = ("ANALYSIS", "EXPLORE")
DATA_TURNS = ("INSIGHT", "CONTINUE")
OUTPUT_TOKENS = 2000

INSTRUCTIONS = (
    "You suggest what the user could ask next, after the answer they just received. Write in the language of the "
    "question. Never give a buy, sell or hold recommendation. Never name a table, column, code or id in a question.\n"
    f"follow_ups: 3 to {MAX_FOLLOW_UPS} questions most worth asking next to explore the topic further: a point the "
    "answer could not settle, an upcoming event or decision that changes the picture, a risk it raises, a related "
    "subject. Each names its subject concretely and is not already answered. CANDIDATES (if any) are questions from a "
    "news research you may reuse or improve.\n"
    f"insight_ideas: 2 to {MAX_IDEAS} questions that dig deeper using ONLY the DATA listed (tables with their columns "
    "and dates): a comparison between subjects or periods, a breakdown by group or month, a trend, the days that stand "
    "out and what happened then. Each lists in 'tables' the exact table names it needs from DATA. Empty when DATA is "
    "empty.\n"
    "data_test: when ASK_TEST is true, one short hypothesis the data could test, in one sentence (for example 'Saham "
    "bank turun dalam 5 hari setelah BI-Rate naik'); otherwise null."
)

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["follow_ups", "insight_ideas", "data_test"],
    "properties": {
        "follow_ups": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question"],
            "properties": {"question": {"type": "string"}}}},
        "insight_ideas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["question", "tables"],
            "properties": {"question": {"type": "string"}, "tables": {"type": "array", "items": {"type": "string"}}}}},
        "data_test": {"type": ["object", "null"], "additionalProperties": False, "required": ["hypothesis"],
                      "properties": {"hypothesis": {"type": "string"}}},
    },
}


class _Question(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str


class _Idea(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str
    tables: list[str] = Field(default_factory=list)


class _Test(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hypothesis: str


class Suggestions(BaseModel):
    model_config = ConfigDict(extra="ignore")
    follow_ups: list[_Question] = Field(default_factory=list)
    insight_ideas: list[_Idea] = Field(default_factory=list)
    data_test: _Test | None = None


Kind = Literal["FOLLOW_UP", "INSIGHT_IDEA", "DATA_TEST"]


def wanted(result: Any) -> tuple[bool, bool]:
    """(suggest at all, offer a data test): only after an answer of a data route; a data test only in EXPLORE's first
    round when the answer used figures from data."""
    response, execution = result.response, result.execution
    if response is None or response.response_type not in ("ANSWER", "LIMITATION") or not response.answer.strip():
        return False, False
    if result.status in ("AWAITING_CONFIRMATION", "NEEDS_CLARIFICATION") or execution.pause or execution.stopped:
        return False, False
    block = result.mode4 or {}
    mode = execution.mode
    route = mode.route if mode is not None else None
    turn = block.get("turn_kind")
    first = block.get("round") == "FIRST"
    if turn in DATA_TURNS or (first and route in (None, "EXPLORE")) or route == "ANALYSIS" \
            or (mode is not None and mode.name == "ANALYSIS" and not block):
        return True, first and route in (None, "EXPLORE") and result.evidence_label is not None
    return False, False


def data_list(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The tables this conversation read, with their columns and dates (from the data record)."""
    record = record or {}
    columns, coverage = record.get("columns") or {}, record.get("coverage") or {}
    out = []
    for name, table in list((record.get("tables") or {}).items())[:MAX_TABLES]:
        read = list((columns.get(name) or {}).keys()) or list((table or {}).get("read") or [])
        dates = coverage.get(name) or {}
        out.append({"table": name, "columns": read[:MAX_COLUMNS],
                    "from": dates.get("actual_min_date") or dates.get("expected_min_date"),
                    "to": dates.get("actual_max_date") or dates.get("expected_max_date")})
    return out


def content(question: str, answer: str, record: dict[str, Any] | None, candidates: list[str], ask_test: bool,
            today: str) -> str:
    return json.dumps({"TODAY": today, "QUESTION": question[:2000], "ANSWER": answer[:ANSWER_CHARS],
                       "DATA": data_list(record), "CANDIDATES": candidates[:MAX_FOLLOW_UPS], "ASK_TEST": ask_test},
                      ensure_ascii=False)


def _clean(text: str, names: list[str]) -> str | None:
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_LABEL]
    if not text or any(name and name.casefold() in text.casefold() for name in names):
        return None  # a table name in a reader's question: the reader rules forbid it
    return text


def items(parsed: Suggestions, record: dict[str, Any] | None, ask_test: bool) -> list[dict[str, str]]:
    """The suggestions the backend keeps, in display order, deduplicated."""
    read = {t["table"] for t in data_list(record)}
    names = sorted(read)
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(kind: str, text: str | None) -> None:
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append({"kind": kind, "label": text})

    for q in parsed.follow_ups[:MAX_FOLLOW_UPS]:
        add("FOLLOW_UP", _clean(q.question, names))
    for idea in parsed.insight_ideas[:MAX_IDEAS]:
        if idea.tables and set(idea.tables) <= read:  # only what the data at hand can answer
            add("INSIGHT_IDEA", _clean(idea.question, names))
    if ask_test and parsed.data_test is not None:
        hypothesis = _clean(parsed.data_test.hypothesis, names)
        add("DATA_TEST", texts.DATA_TEST_LABEL.format(hypothesis=hypothesis.rstrip(".")) if hypothesis else None)
    return out


def attach(orchestrator: Any, question: str, result: Any) -> Any:
    """The result with its follow-up suggestions (follow_ups) and the call's cost in its totals; unchanged when none
    are wanted or the call fails."""
    want, ask_test = wanted(result)
    suggest = getattr(orchestrator, "suggest_follow_ups", None)
    if not want or suggest is None:
        return result
    candidates = list(((result.mode4 or {}).get("news") or {}).get("follow_ups") or [])
    try:
        parsed, record = suggest(result.request_id, content(question, result.response.answer, result.data_record,
                                                            candidates, ask_test, str(orchestrator._today())))
    except Exception:  # noqa: BLE001 - the answer never depends on its suggestions
        return result
    kept = items(parsed, result.data_record, ask_test) if parsed is not None else []
    execution = result.execution
    if record.get("cost") is not None:
        execution = execution.model_copy(update={"cost": round((execution.cost or 0) + record["cost"], 6)})
    return result.model_copy(update={"follow_ups": kept or None, "execution": execution})
