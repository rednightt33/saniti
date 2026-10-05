"""check_references (10.2, plan 2026-10-05 item 10, user decision): the model renders value references before it writes
the answer. In the golden test ma-qa-20261005b an address composed from memory (finding.<id>.groups.CONDITION.median,
a field only the research summary has) was found wrong only after a 15,000-token draft, and the whole answer was
written again. This tool resolves a list of addresses against this run's references with the same code the answer
uses (value_refs.render), without a model call, and returns what each would show or why it cannot.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..value_refs import render
from .registry import ToolSpec
from .request_data import current_reference_sources

DESCRIPTION = (
    "Shows what value references render to before you write the answer: give the addresses (with or without {{ }} "
    "and a format) and get each one's displayed value, or why it does not resolve and the addresses that exist. "
    "Reads only this run's results; no data is fetched or computed.")
MAX_REFERENCES = 40


class CheckReferencesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: list[str] = Field(min_length=1, max_length=MAX_REFERENCES,
                                  description="Value references, for example 'finding.a.estimates.primary.estimate|pp:2'.")


def check(references: list[str], sources: Any) -> dict[str, Any]:
    """Each address rendered as the answer would render it."""
    if sources is None or not sources:
        return {"status": "NO_REFERENCES", "results": [],
                "note": "This run has no referable values yet: complete an analysis or read a result first."}
    results = []
    for reference in references:
        text = reference.strip()
        if not text.startswith("{{"):
            text = "{{" + text + "}}"
        rendering = render(text, sources)
        if rendering.missing:
            results.append({"reference": reference, "ok": False, "error": rendering.missing[0][2]})
        elif rendering.problems:
            results.append({"reference": reference, "ok": False, "error": rendering.problems[0]})
        else:
            entry = {"reference": reference, "ok": True, "shows": rendering.text}
            redirected = sources.redirected.pop(text[2:-2].split("|", 1)[0].strip(), None) \
                if getattr(sources, "redirected", None) else None
            if redirected:
                entry["read_from"] = redirected
            results.append(entry)
    return {"status": "OK", "results": results}


def check_references_spec() -> ToolSpec:
    def handler(arguments: CheckReferencesArguments) -> dict[str, Any]:
        return check(arguments.references, current_reference_sources.get())

    return ToolSpec(name="check_references", effect="READS", description=DESCRIPTION,
                    arguments_model=CheckReferencesArguments, handler=handler, timeout_seconds=30.0)
