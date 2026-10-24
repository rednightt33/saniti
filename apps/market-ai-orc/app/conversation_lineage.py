"""EXEC-ASK-BRANCH (user 2026-10-24): what a conversation may read of the conversations it continues.

A conversation made by EDGE "Branch" or by the side chat "Ask about this answer" continues another one from one of its
answers. "AI_conversation".lineage (migration 20261024_001) lists those conversations, oldest first, each with the
last turn continued (through_turn) and that turn's completed_at (cut_at). Nothing is copied: a read of the
conversation's stored results (outputs, executions, evidence, exports, run memories, turns) takes its own rows and the
rows of each conversation in its lineage created up to that entry's cut_at, so a result made there after the branch
point stays out. Writes always go to the conversation itself.

A lineage is written once, when the conversation is made, so it is kept in memory after the first read.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

LINEAGE_MAX = 20  # the migration's check: a branch of a branch ... at most 20 deep
_CACHE_MAX = 4096
_cache: dict[str, tuple["Ancestor", ...]] = {}


@dataclass(frozen=True)
class Ancestor:
    conversation_id: str
    through_turn: int
    cut_at: datetime

    def to_json(self) -> dict[str, Any]:
        return {"conversation_id": self.conversation_id, "through_turn": self.through_turn,
                "cut_at": self.cut_at.isoformat()}


def parse(value: Any) -> tuple[Ancestor, ...]:
    """The stored lineage (a JSON array) as ancestors; an empty or unreadable value is no lineage."""
    if not isinstance(value, list):
        return ()
    found = []
    for entry in value:
        if isinstance(entry, dict) and entry.get("conversation_id") and entry.get("cut_at") is not None:
            cut = entry["cut_at"]
            found.append(Ancestor(str(entry["conversation_id"]), int(entry.get("through_turn") or 0),
                                  cut if isinstance(cut, datetime) else datetime.fromisoformat(str(cut))))
    return tuple(found)


def lineage_of(connection: psycopg.Connection, conversation_id: str) -> tuple[Ancestor, ...]:
    """The conversation's lineage, read once and then kept (it never changes); () for an unknown conversation."""
    if conversation_id in _cache:
        return _cache[conversation_id]
    row = connection.execute('SELECT lineage FROM public."AI_conversation" WHERE conversation_id = %s',
                             (conversation_id,)).fetchone()
    if row is None:
        return ()
    lineage = parse(row["lineage"] if isinstance(row, dict) else row[0])
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[conversation_id] = lineage
    return lineage


def visible(conversation_id: str, lineage: tuple[Ancestor, ...], alias: str = "") -> tuple[str, list[Any]]:
    """The WHERE part (and its parameters) for the rows a conversation reads: its own, and those of each conversation
    in its lineage created up to that entry's cut_at."""
    column = f"{alias}." if alias else ""
    clauses, params = [f"{column}conversation_id = %s"], [conversation_id]
    for ancestor in lineage:
        clauses.append(f"({column}conversation_id = %s AND {column}created_at <= %s)")
        params += [ancestor.conversation_id, ancestor.cut_at]
    return "(" + " OR ".join(clauses) + ")", params


def scope(connection: psycopg.Connection, conversation_id: str, alias: str = "") -> tuple[str, list[Any]]:
    return visible(conversation_id, lineage_of(connection, conversation_id), alias)
