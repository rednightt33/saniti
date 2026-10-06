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

EDIT_KEYS = frozenset({"edits", "fields", "set", "keep"})
MAX_EDITS = 40

EDIT_REPAIR_INSTRUCTION = (
    "You may fix the refused draft above with an edit instead of writing it again: answer with only "
    '{"edits": [{"find": "<exact text from one string value of the draft>", "replace": "<new text>"}], '
    '"set": {"<field path>": <new value>}, "fields": {"<top-level field>": <new value>}} (any key may be left out). '
    "Each find must occur exactly once across the draft's string values, as the decoded text (not JSON-escaped); a "
    'find that repeats is replaced everywhere with "all": true. set replaces one value at a field path of the draft, '
    "nested fields included (research_plan.angles[0].min_effect, research_plan.experiments[1].success_rule); every "
    "step before the last must exist in the draft. fields replaces whole top-level fields of the response (for example response_type, assumptions "
    'or limitations). To keep the draft as it is, answer {"keep": true}. The backend applies the edit and checks the '
    "whole answer again. For a large change send the complete final response instead.")
# 10.3 (plan 2026-10-05 item 10): a repeated wrong reference or typed figure ("IK 95%" eight times in h_add turn 3)
# forced a full rewrite because a find had to occur once; "all" or "count" now replaces each. EXEC-R R4c (2026-10-06):
# "all" covers any text, not only a whole value reference (an "all" on plain text was refused and rewritten in full)


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
    match exactly once (or as counted), a set path does not exist, or a field is not a top-level field of the
    response. {"keep": true} returns the draft unchanged (EXEC-R R2)."""
    draft = json.loads(json.dumps(base))  # a copy that is plain JSON
    if edit.get("keep") is True and set(edit) == {"keep"}:
        return json.dumps(draft, ensure_ascii=False), {"edits": 0, "fields": 0, "kept": 1}  # EXEC-R R2
    edits = edit.get("edits") or []
    replaced = edit.get("fields") or {}
    paths = edit.get("set") or {}
    if not isinstance(edits, list) or not isinstance(replaced, dict) or not isinstance(paths, dict) \
            or len(edits) + len(paths) > MAX_EDITS:
        raise EditNotApplied(f"edits must be a list and set and fields objects, at most {MAX_EDITS} changes")
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
        elif everywhere:  # EXEC-R R4c: every occurrence, of a value reference or of other text
            if found < 1:
                raise EditNotApplied(f"edit {number}: find occurs 0 times in the draft's string values")
        elif found != 1:
            raise EditNotApplied(f"edit {number}: find occurs {found} times in the draft's string values, not once")
        draft = _replace(draft, item["find"], item["replace"])
    for path, value in paths.items():  # EXEC-R R1: a nested field of the draft, by its path
        _set_path(draft, str(path), value, fields)
    draft.update(replaced)
    return json.dumps(draft, ensure_ascii=False), {"edits": len(edits), "fields": len(replaced), "set": len(paths)}


PATH_STEP = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)")


def _set_path(draft: dict[str, Any], path: str, value: Any, fields: frozenset[str] | set[str]) -> None:
    """EXEC-R R1: replace the value at a dotted path with list indexes (research_plan.angles[0].min_effect). Every
    step before the last must exist in the draft; the last may be a field the draft left out (an optional field), which
    the full schema check that follows accepts only when the response format has it. A top-level field must be one of
    the response's fields."""
    current: Any = draft
    steps: list[Any] = []
    for part in path.split("."):
        match = PATH_STEP.fullmatch(part.strip())
        if match is None:
            raise EditNotApplied(f"set path {path!r}: {part!r} is not a field name with optional [index]")
        steps.append(match.group(1))
        steps.extend(int(i) for i in re.findall(r"\[(\d+)\]", match.group(2)))
    for step in steps[:-1]:
        current = _step(current, step, path)
    last = steps[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or not 0 <= last < len(current):
            raise EditNotApplied(f"set path {path!r}: index {last} does not exist in the draft")
    elif not isinstance(current, dict) or (current is draft and last not in fields):
        raise EditNotApplied(f"set path {path!r}: field {last!r} is not a field of the response")
    current[last] = value


def _step(current: Any, step: Any, path: str) -> Any:
    if isinstance(step, int):
        if isinstance(current, list) and 0 <= step < len(current):
            return current[step]
        raise EditNotApplied(f"set path {path!r}: index {step} does not exist in the draft")
    if isinstance(current, dict) and step in current:
        return current[step]
    raise EditNotApplied(f"set path {path!r}: field {step!r} does not exist in the draft")


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
