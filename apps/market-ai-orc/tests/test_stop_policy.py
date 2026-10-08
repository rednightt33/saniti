"""EXEC-W A1 (M121 j, user decision 2026-10-08: "jeda dan tanya, bukan berhenti, plus satu aturan berhenti terpusat"):
one table decides how every check ends (app/stop_policy.py). The kinds are read from the orchestrator's source, so a
new check without an outcome, or a forced ending without a question, fails here."""
from __future__ import annotations

import re
from pathlib import Path

from app import data_record as records
from app import stop_policy
from app.orchestrator import GATE_ONCE_NOTES, AgentOrchestrator, RunState
from app.schemas import AgentRunRequest
from test_provenance import answer, facts_body, fact, lookup_call, run

SOURCE = (Path(__file__).resolve().parents[1] / "app" / "orchestrator.py").read_text(encoding="utf-8")


def gate_kinds() -> set[str]:
    """Every check kind the orchestrator can raise: literal kinds and the values a `kind` variable is given."""
    kinds = set(re.findall(r'_gate_once\(\s*state,\s*"([A-Z_0-9]+)"', SOURCE))
    for call in re.finditer(r"_gate_once\(\s*state,\s*kind\b", SOURCE):
        # the values `kind` was given just before the call
        before = SOURCE[max(0, call.start() - 600):call.start()]
        assigned = re.findall(r'\bkind = (.*)', before)[-1]
        kinds |= {k.rstrip(":") for k in re.findall(r'"([A-Z_0-9]+:?)"', assigned)}
    return kinds


def forced_kinds() -> set[str]:
    """The kinds that end a response through _forced or _plan_not_feasible."""
    return set(re.findall(r'self\._(?:forced|plan_not_feasible)\(state, final, "([A-Z_0-9]+)"', SOURCE))


def test_every_check_kind_has_one_outcome() -> None:
    kinds = gate_kinds()
    assert len(kinds) >= 20, kinds  # the scan itself works
    missing = sorted(k for k in kinds if k.split(":")[0] not in stop_policy.CAUSES)
    assert missing == [], f"checks without an outcome in app/stop_policy.py: {missing}"


def test_a_forced_ending_always_pauses_with_a_question() -> None:
    kinds = forced_kinds()
    assert kinds, "the scan found no forced ending"
    dead = sorted(k for k in kinds if stop_policy.cause_of(k).outcome != stop_policy.PAUSE)
    assert dead == [], f"forced endings without a question: {dead}"
    for kind in kinds:
        cause = stop_policy.cause_of(kind)
        assert cause.reason and cause.options and all(o in stop_policy.OPTIONS for o in cause.options), kind


def test_no_limitation_is_built_outside_the_policy() -> None:
    """A LIMITATION is built only where its ending is decided by the policy (_forced, _plan_not_feasible) or by a
    budget whose way back is still the user's decision (_exhausted, M121 g pending)."""
    builders = [m.start() for m in re.finditer(r'FinalResponse\(response_type="LIMITATION"', SOURCE)]
    owners = []
    for position in builders:
        owner = re.findall(r"\n    def (\w+)\(", SOURCE[:position])[-1]
        owners.append(owner)
    assert set(owners) <= {"_forced", "_plan_not_feasible", "_exhausted"}, owners


def test_each_note_says_what_happens_to_a_kept_response() -> None:
    assert "question" in GATE_ONCE_NOTES[stop_policy.PAUSE]
    assert "confirm" in GATE_ONCE_NOTES[stop_policy.CONFIRM]
    assert "backend's note" in GATE_ONCE_NOTES[stop_policy.ANNOTATE]
    assert "dropped" not in " ".join(GATE_ONCE_NOTES.values())


def test_an_unknown_kind_pauses_instead_of_ending() -> None:
    assert stop_policy.cause_of("SOMETHING_NEW").outcome == stop_policy.PAUSE
    assert stop_policy.cause_of("REFERENCE:abc123").outcome == stop_policy.ANNOTATE


def test_a_figure_without_a_source_pauses_the_answer_and_the_next_message_reads_it() -> None:
    head = answer("Korelasi return harian BBCA dan BBRI adalah 0,42.")
    result, _ = run([lookup_call(), final_response_of(head), final_response_of(head)],
                    "Berapa korelasi return harian BBCA dan BBRI bulan ini?",
                    lookup=facts_body(fact(9125), fact(4120, entity="BBRI")))
    assert result.status == "LIMITED" and result.response.response_type == "LIMITATION"
    assert "Korelasi" in result.response.answer  # the draft is kept behind the notice, marked as not validated
    assert result.response.answer.endswith(stop_policy.pause_question("ROUTING"))
    pause = result.execution.pause
    assert pause["cause"] == "ROUTING" and [o["id"] for o in pause["options"]] == ["RECOMPUTE", "ACCEPT_PARTIAL"]
    assert result.data_record["pause"] == pause
    # the next message of the conversation reads the pause once and clears it
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    state = RunState(request_id="next", started=0.0, input_items=[{"role": "user", "content": "hitung ulang"}])
    orc.run_memory, orc.result_store = None, None
    orc._seed_findings = orc._offer_methods = orc._offer_metrics = lambda *_: None  # type: ignore[method-assign]
    AgentOrchestrator._seed_data_record(orc, state, result.data_record)
    notes = [i["content"] for i in state.input_items if "paused" in str(i.get("content"))]
    assert len(notes) == 1 and "RECOMPUTE" in notes[0] and "ROUTING" in notes[0]
    state.data_record["pause"] = state.pause  # what run() does at the end of the answering run
    assert records.normalize(state.data_record)["pause"] is None


def final_response_of(body: dict) -> dict:
    from conftest import final_response
    return final_response(body)


def test_a_record_without_a_pause_keeps_its_shape() -> None:
    assert records.empty()["pause"] is None
    assert records.is_empty(records.empty())
    assert not records.is_empty({**records.empty(), "pause": stop_policy.pause_record("PROVENANCE", "r1")})


def test_the_request_type_is_unchanged() -> None:
    # the pause rides on LIMITATION and execution.pause: no new status, no new response type for callers
    assert "PAUSED" not in AgentRunRequest.model_json_schema().__repr__()


def test_a_full_sandbox_after_the_backends_wait_pauses_the_limitation() -> None:
    """EXEC-W A5: a tool result that says PAUSE_ANSWER (directly or inside a research step's result) marks the run; its
    LIMITATION then ends with the question to continue later."""
    from app.orchestrator import _asks_pause
    from app.schemas import FinalResponse

    assert _asks_pause({"ok": True, "result": {"status": "REJECTED", "next_action": "PAUSE_ANSWER"}})
    assert _asks_pause({"result": {"group": {"opened": {"next_action": "PAUSE_ANSWER"}}}})
    assert not _asks_pause({"result": {"next_action": "USE_OPEN_SESSION"}})
    state = RunState(request_id="busy", started=0.0, input_items=[])
    limited = FinalResponse(response_type="LIMITATION", answer="Analisis belum bisa dimulai.",
                            clarification_question=None, assumptions=[], limitations=["sandbox penuh"])
    paused = AgentOrchestrator._paused(state, limited, "SANDBOX_BUSY")
    assert paused.answer.endswith(stop_policy.pause_question("SANDBOX_BUSY")) and "Lanjutkan sekarang" in paused.answer
    assert state.pause["cause"] == "SANDBOX_BUSY"
