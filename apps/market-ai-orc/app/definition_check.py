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


def problems(text: str, produced: list[dict[str, Any]], opened: list[dict[str, Any]]) -> list[str]:
    """Why a consistency claim in text is not supported, or [] (no claim, or every result produced in the run has
    the definition of an earlier result it opened). produced/opened: [{"name", "definition"}]."""
    if not claims_consistency(text):
        return []
    if not opened:
        return ["the answer says its result follows an earlier result, but this run opened no earlier result "
                "(load_output), so the backend cannot see that the definitions are the same"]
    earlier = {_key(o["definition"]): o for o in opened if isinstance(o.get("definition"), dict)}
    if not earlier:
        return ["the earlier result(s) opened in this run carry no definition, so the claim cannot be checked: "
                + ", ".join(str(o.get("name")) for o in opened)]
    found = []
    for output in produced:
        definition = output.get("definition")
        if not isinstance(definition, dict):
            continue
        if _key(definition) not in earlier:
            found.append(f"{output.get('name')} uses {describe(definition)}, the earlier result(s) "
                         + "; ".join(f"{o.get('name')} {describe(o.get('definition'))}" for o in opened))
    return found
