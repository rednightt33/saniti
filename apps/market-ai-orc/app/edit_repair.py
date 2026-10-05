"""M45 (plan step 6, AI_ENABLE_EDIT_REPAIR): a refused final draft repaired by an edit instead of a full rewrite.

Live (ma-integrity-20261001a, m4a): six final attempts took 510 s of a 1,335 s run, each a complete rewrite of an
18,952-character report for a fix of a few words. When a refused draft is a JSON object, the refusal now offers an edit:
the model may answer with only {"edits": [{"find", "replace"}], "fields": {...}}. The backend applies it to the draft
and the whole answer goes through every check again. Anything that cannot be applied exactly falls back to the full
rewrite, so an edit never weakens a check: it only changes what the model has to write.
"""
from __future__ import annotations

import json
import re
from typing import Any

EDIT_KEYS = frozenset({"edits", "fields"})
MAX_EDITS = 40

EDIT_REPAIR_INSTRUCTION = (
    "You may fix the refused draft above with an edit instead of writing it again: answer with only "
    '{"edits": [{"find": "<exact text from one string value of the draft>", "replace": "<new text>"}], '
    '"fields": {"<top-level field>": <new value>}} (either key may be left out). Each find must occur exactly once '
    "across the draft's string values, as the decoded text (not JSON-escaped); a find that repeats is replaced "
    'everywhere with "all": true when it is a whole value reference {{...}}, or with "count": <its number of '
    "occurrences> for other text. fields replaces whole top-level fields of the response (for example response_type, "
    "assumptions or limitations). The backend applies the edit and checks the whole answer again. For a large change "
    "send the complete final response instead.")
# 10.3 (plan 2026-10-05 item 10): a repeated wrong reference or typed figure ("IK 95%" eight times in h_add turn 3)
# forced a full rewrite because a find had to occur once; "all" (a whole reference) or "count" now replaces each
REFERENCE_FIND = re.compile(r"\{\{[^{}]+\}\}")


class EditNotApplied(ValueError):
    """The reply was an edit object that cannot be applied exactly; the model must send the full response."""


def draft_object(raw: str, edits: bool = False) -> dict[str, Any] | None:
    """The refused draft as a JSON object (a ```json wrapper allowed), or None for prose or a cut-off draft; with
    edits=True also an edit object (the reply to an offered edit)."""
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if len(lines) < 3 or lines[-1].strip() != "```":
            return None
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(candidate, strict=False)
    except ValueError:
        return None
    return data if isinstance(data, dict) and (edits or not is_edit(data)) else None


def is_edit(data: Any) -> bool:
    return isinstance(data, dict) and bool(data) and set(data) <= EDIT_KEYS


def apply(base: dict[str, Any], edit: dict[str, Any], fields: frozenset[str] | set[str]) -> tuple[str, dict[str, int]]:
    """The draft with the edit applied, as JSON text, and what changed. Raises EditNotApplied when an edit does not
    match exactly once or a field is not a top-level field of the response."""
    draft = json.loads(json.dumps(base))  # a copy that is plain JSON
    edits = edit.get("edits") or []
    replaced = edit.get("fields") or {}
    if not isinstance(edits, list) or not isinstance(replaced, dict) or len(edits) > MAX_EDITS:
        raise EditNotApplied(f"edits must be a list of at most {MAX_EDITS} items and fields an object")
    unknown = sorted(set(replaced) - set(fields))
    if unknown:
        raise EditNotApplied(f"fields names keys the response does not have: {', '.join(unknown)}")
    for number, item in enumerate(edits, 1):
        if not isinstance(item, dict) or not isinstance(item.get("find"), str) or not item["find"] \
                or not isinstance(item.get("replace"), str):
            raise EditNotApplied(f"edit {number} needs a non-empty find and a replace, both text")
        found = _count(draft, item["find"])
        expected, everywhere = item.get("count"), item.get("all") is True
        if expected is not None:
            if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1 or found != expected:
                raise EditNotApplied(f"edit {number}: find occurs {found} times in the draft's string values, not "
                                     f"{expected}")
        elif everywhere:
            if not REFERENCE_FIND.fullmatch(item["find"].strip()):
                raise EditNotApplied(f"edit {number}: all replaces every occurrence of a whole value reference "
                                     "{{...}} only; for other text give count, the number of occurrences")
            if found < 1:
                raise EditNotApplied(f"edit {number}: find occurs 0 times in the draft's string values")
        elif found != 1:
            raise EditNotApplied(f"edit {number}: find occurs {found} times in the draft's string values, not once")
        draft = _replace(draft, item["find"], item["replace"])
    draft.update(replaced)
    return json.dumps(draft, ensure_ascii=False), {"edits": len(edits), "fields": len(replaced)}


def _count(value: Any, text: str) -> int:
    if isinstance(value, str):
        return value.count(text)
    if isinstance(value, dict):
        return sum(_count(v, text) for v in value.values())
    if isinstance(value, list):
        return sum(_count(v, text) for v in value)
    return 0


def _replace(value: Any, text: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(text, new)
    if isinstance(value, dict):
        return {k: _replace(v, text, new) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace(v, text, new) for v in value]
    return value
