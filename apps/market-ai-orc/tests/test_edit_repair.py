"""M45 (plan step 6, AI_ENABLE_EDIT_REPAIR): a refused final draft repaired by an edit instead of a full rewrite.

Live (ma-integrity-20261001a, m4a): six final attempts took 510 s of a 1,335 s run, each a full rewrite of an
18,952-character report. With the flag, a refusal of a draft that is a JSON object offers an edit object; the backend
applies it and every check runs again. Prose, cut-off drafts and edits that do not match exactly once get the full
rewrite as before.
"""
from __future__ import annotations

import json
import logging

import pytest

from app import edit_repair
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest, FinalResponse
from app.tools import build_default_registry
from conftest import ScriptedClient, final_response, make_settings
from test_analysis_tools import AnyRunBundles, REFERENCE, mock_sandbox
from test_orchestrator import ListHandler
from test_provenance import answer, fact, facts_body, governor, lookup_call, preview_tool, rejection_text

LONG = "Ringkasan panjang analisis harga. " * 40


def run(script: list, message: str = "Berapa close BBCA kemarin?", *, flag: bool = True, lookup=None):
    registry = build_default_registry(None, bundles=AnyRunBundles(), request_data_enabled=True,
                                      governor_client=governor(lookup or facts_body(fact(9125))),
                                      sandbox_client=mock_sandbox({}), sandbox_timeout_seconds=5)
    registry.register(preview_tool())
    scripted = ScriptedClient(script)
    settings = make_settings(**({"AI_ENABLE_EDIT_REPAIR": "true"} if flag else {}))
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        result = AgentOrchestrator(settings, scripted, registry, wall_clock=lambda: REFERENCE).run(
            AgentRunRequest(request_id="edit", message=message))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    scripted.events = [json.loads(m) for m in handler.messages]
    return result, scripted


def edit(*pairs: tuple[str, str], **fields) -> dict:
    body = {"edits": [{"find": f, "replace": r} for f, r in pairs]}
    if fields:
        body["fields"] = fields
    return final_response(body)


def test_a_gate_refusal_is_repaired_by_an_edit_and_checked_again() -> None:
    draft = answer(LONG + "Close BBCA 9.140.")
    result, scripted = run([lookup_call(), final_response(draft), edit(("9.140", "9.125"))])
    assert "9.140" in rejection_text(scripted)  # the second call was the refusal
    assert result.status == "COMPLETED" and result.response.answer == LONG + "Close BBCA 9.125."
    assert result.evidence_label == "FACT"
    events = [e for e in scripted.events if e.get("event") == "ai_final_edit_applied"]
    assert events and events[0]["edits"] == 1 and events[0]["edit_chars"] < events[0]["draft_chars"]


def test_the_edited_answer_passes_every_check_again() -> None:
    result, scripted = run([lookup_call(), final_response(answer(LONG + "Close BBCA 9.140.")),
                            edit(("9.140", "9.999"))])
    # the edit still states an unsupported number: the provenance gate refuses it like a full response
    assert result.response.response_type == "LIMITATION"
    assert result.execution.number_provenance.unsupported == ["9.999"]


def test_an_edit_that_matches_twice_falls_back_to_the_full_rewrite() -> None:
    twice = answer("Close BBCA 9.140, sekali lagi 9.140.")
    result, scripted = run([lookup_call(), final_response(twice), edit(("9.140", "9.125")),
                            final_response(answer("Close BBCA 9.125."))])
    fallback = [i["content"] for i in scripted.payloads[3]["input"] if i.get("role") == "user"][-1]
    assert "could not be applied" in fallback and "occurs 2 times" in fallback
    assert edit_repair.EDIT_REPAIR_INSTRUCTION not in fallback  # the full response, not another edit
    assert result.status == "COMPLETED" and result.response.answer == "Close BBCA 9.125."


def test_fields_repair_a_form_refusal() -> None:
    empty = answer("Data harga belum tersedia untuk tanggal itu.", kind="LIMITATION", limitations=[])
    result, scripted = run([lookup_call(), final_response(empty),
                            final_response({"fields": {"limitations": ["Data 2026-08-31 belum dimuat."]}})])
    reask = [i["content"] for i in scripted.payloads[2]["input"] if i.get("role") == "user"][-1]
    assert "limitations" in reask and edit_repair.EDIT_REPAIR_INSTRUCTION in reask
    assert scripted.payloads[2].get("tools")  # free-form: an edit object cannot pass the strict schema
    assert result.response.response_type == "LIMITATION"
    assert result.response.limitations == ["Data 2026-08-31 belum dimuat."]


def test_prose_is_rewritten_in_full_and_the_flag_off_keeps_todays_refusal() -> None:
    _, scripted = run([lookup_call(), final_response("Close BBCA kemarin 9.125."),
                       final_response(answer("Close BBCA 9.125."))])
    assert edit_repair.EDIT_REPAIR_INSTRUCTION not in rejection_text(scripted)
    _, scripted = run([lookup_call(), final_response(answer("Close BBCA 9.140.")),
                       final_response(answer("Close BBCA 9.125."))], flag=False)
    assert edit_repair.EDIT_REPAIR_INSTRUCTION not in rejection_text(scripted)


def test_apply_works_on_decoded_string_values_and_only_on_response_fields() -> None:
    fields = set(FinalResponse.model_fields)
    base = {"response_type": "ANSWER", "answer": 'Kata "kutip"\nbaris dua', "assumptions": ["a 1", "b 2"],
            "limitations": [], "clarification_question": None}
    merged, counts = edit_repair.apply(base, {"edits": [{"find": '"kutip"\nbaris', "replace": "kutip baris"},
                                                        {"find": "b 2", "replace": "b 3"}]}, fields)
    assert json.loads(merged)["answer"] == "Kata kutip baris dua" and json.loads(merged)["assumptions"][1] == "b 3"
    assert counts == {"edits": 2, "fields": 0} and base["assumptions"][1] == "b 2"  # the base is not changed
    with pytest.raises(edit_repair.EditNotApplied, match="limitations_note"):
        edit_repair.apply(base, {"fields": {"limitations_note": "x"}}, fields)
    with pytest.raises(edit_repair.EditNotApplied, match="occurs 0 times"):
        edit_repair.apply(base, {"edits": [{"find": "tidak ada", "replace": "x"}]}, fields)
    assert edit_repair.draft_object("```json\n" + json.dumps(base) + "\n```") == base
    assert edit_repair.draft_object('{"edits": []}') is None and edit_repair.draft_object("prosa") is None
