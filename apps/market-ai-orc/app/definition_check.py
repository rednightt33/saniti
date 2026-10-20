"""H1 (M63, golden test 2026-10-02): an answer may say its result is consistent with an earlier one ("agar konsisten
dengan jawaban sebelumnya") only when the backend can see that both rest on the same definition. Turn 3 of the golden
test claimed consistency after filtering a board the earlier ranking had not filtered.

The definitions compared are the ones the sandbox stores with each released table (runtime emit_table definition: filters
in the DataNeed scope grammar, period, entities, thresholds) and the ones of the earlier tables the run loaded
(final_status.carried_inputs). Free-text notes are not compared."""
from __future__ import annotations

import json
import re
from typing import Any

# A sentence that claims the result follows the earlier result's definition (Indonesian and English)
CLAIM = re.compile(
    r"(konsisten\s+dengan\s+(jawaban|analisis|hasil|tabel|definisi|perhitungan)\s+(sebelumnya|tadi|awal|pertama)"
    r"|sama\s+(dengan|seperti)\s+(definisi|analisis|jawaban|hasil|perhitungan)\s+(sebelumnya|tadi|awal|pertama)"
    r"|definisi\s+yang\s+sama|cakupan\s+yang\s+sama"
    r"|consistent\s+with\s+(the\s+)?(previous|earlier|prior)|same\s+definition)",
    re.IGNORECASE)
COMPARED = ("filters", "period", "entities", "thresholds")


def claims_consistency(text: str) -> bool:
    return bool(CLAIM.search(text or ""))


def _key(definition: dict[str, Any]) -> str:
    filters = sorted(json.dumps(f, sort_keys=True, default=str) for f in definition.get("filters") or [])
    rest = {k: definition.get(k) for k in COMPARED if k != "filters" and definition.get(k) not in (None, {}, [])}
    return json.dumps({"filters": filters, **rest}, sort_keys=True, default=str)


def describe(definition: Any) -> str:
    if not isinstance(definition, dict):
        return "not stated"
    return json.dumps({k: definition.get(k) for k in COMPARED if definition.get(k) not in (None, {}, [])},
                      ensure_ascii=False, sort_keys=True, default=str) or "{}"


def claim_sentence(text: str) -> str | None:
    """M192 (3): the sentence of text that makes the claim, so a refusal can quote it."""
    match = CLAIM.search(text or "")
    if match is None:
        return None
    start = max((text.rfind(mark, 0, match.start()) for mark in (". ", "! ", "? ", "\n")), default=-1)
    ends = [i for i in (text.find(mark, match.end()) for mark in (". ", "! ", "? ", "\n")) if i >= 0]
    return " ".join(text[start + 1:(min(ends) + 1) if ends else len(text)].split())[:300]


def _entities(definition: dict[str, Any]) -> set[str]:
    return {str(e) for e in definition.get("entities") or [] if isinstance(e, (str, int))} \
        if isinstance(definition.get("entities"), list) else set()


def differences(definition: dict[str, Any], earlier: dict[str, Any], scope_added: bool = False) -> list[str]:
    """M192 (3): the compared fields whose values differ. (2): with scope_added (the user asked to add stocks, a SCOPE
    ADD fact) a list of stocks that keeps every earlier stock is not a difference."""
    found = []
    for field in COMPARED:
        mine, theirs = _key({field: definition.get(field)}), _key({field: earlier.get(field)})
        if mine == theirs:
            continue
        if field == "entities" and scope_added and _entities(earlier) and _entities(earlier) <= _entities(definition):
            continue
        found.append(field)
    return found


def findings(text: str, produced: list[dict[str, Any]], opened: list[dict[str, Any]],
             scope_added: bool = False) -> list[dict[str, Any]]:
    """Why a consistency claim in text is not supported, or [] (no claim, or every result produced in the run has
    the definition of an earlier result it opened). produced/opened: [{"name", "definition"}]. M151 (EXEC-FASTLANE G3,
    run edge_80e733ba): a run that produced no new result (it only read or exported earlier ones) has nothing whose
    definition could differ, so its claim is not checked. Each finding: kind (NOT_OPENED, NO_DEFINITION, DIFFERENT),
    the English problem for the model, and for DIFFERENT the produced and earlier definitions and the fields."""
    if not claims_consistency(text) or not produced:
        return []
    if not opened:
        return [{"kind": "NOT_OPENED", "problem": "the answer says its result follows an earlier result, but this run "
                 "opened no earlier result (load_output), so the backend cannot see that the definitions are the same"}]
    earlier = [o for o in opened if isinstance(o.get("definition"), dict)]
    if not earlier:
        return [{"kind": "NO_DEFINITION", "problem": "the earlier result(s) opened in this run carry no definition, so "
                 "the claim cannot be checked: " + ", ".join(str(o.get("name")) for o in opened)}]
    found = []
    for output in produced:
        definition = output.get("definition")
        if not isinstance(definition, dict):
            continue
        apart = [(o, differences(definition, o["definition"], scope_added)) for o in earlier]
        if any(not fields for _, fields in apart):
            continue
        closest, fields = min(apart, key=lambda pair: len(pair[1]))
        found.append({"kind": "DIFFERENT", "fields": fields, "mine": definition, "earlier": closest["definition"],
                      "problem": f"{output.get('name')} uses {describe(definition)}, the earlier result(s) "
                      + "; ".join(f"{o.get('name')} {describe(o.get('definition'))}" for o in opened)
                      + f" (different: {', '.join(fields)})"})
    return found


def problems(text: str, produced: list[dict[str, Any]], opened: list[dict[str, Any]],
             scope_added: bool = False) -> list[str]:
    return [f["problem"] for f in findings(text, produced, opened, scope_added)]
