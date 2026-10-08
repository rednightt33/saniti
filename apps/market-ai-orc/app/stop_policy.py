"""EXEC-W A1 (M121 j; user decision 2026-10-08: "jeda dan tanya, bukan berhenti, plus satu aturan berhenti terpusat"):
the one table of what a check does when the model's repair is used up, so no check ends an answer without a way back.

Every kind of check the orchestrator runs on a final response (`_gate_once` kinds), and every condition that stops
work early, has exactly one outcome here:
- PAUSE: the answer goes out as a LIMITATION that keeps what was verified, marks what was not, and ends with a question
  whose choices come from the cause; execution.pause and the conversation's data record keep the pause, so the next
  message answers it (sessions, data and drafts are kept as for any answer).
- CONFIRM: the Research Plan is issued as usual and the backend lists the values the user has to confirm (M117).
- ANNOTATE: the answer goes out with the backend's line; nothing is withheld that needs a decision.
- ALTERNATIVES: a tool result names other ways to go on (another tool, asking the user, going on without it).
- PENDING_DECISION: the current behaviour stays until the user decides (M121 g, step and time budgets, FUTURE_PLAN.md).

The guarantees stay in code (EXEC-D): a figure without a source is never delivered as a fact, no data is fetched
before an approval, and spending stops at the budget. A pause changes how an answer ends, never what it may contain.
tests/test_stop_policy.py reads every check kind from the orchestrator's source and fails when one is missing here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PAUSE, CONFIRM, ANNOTATE, ALTERNATIVES, PENDING_DECISION = (
    "PAUSE", "CONFIRM", "ANNOTATE", "ALTERNATIVES", "PENDING_DECISION")
VERSION = 1

# the choices a pause offers; the user may always write something else instead
OPTIONS = {
    "RECOMPUTE": "Hitung ulang bagian yang belum terverifikasi",
    "ACCEPT_PARTIAL": "Cukup, pakai jawaban ini apa adanya",
    "REVISE_PLAN": "Ubah rencananya (sebutkan bagian yang diubah)",
    "REPLAN": "Susun ulang rencananya",
    "CONTINUE": "Lanjutkan sekarang",
}
# EXEC-X (M124): the choices whose answer needs the user's own words (what to change); a front-end lets the user write
# them instead of sending the label alone
NEEDS_INPUT = frozenset({"REVISE_PLAN"})


@dataclass(frozen=True)
class Cause:
    outcome: str
    reason: str = ""  # shown to the user when the answer pauses (plain words)
    options: tuple[str, ...] = ()


_ANSWER = ("RECOMPUTE", "ACCEPT_PARTIAL")
_PLAN = ("REVISE_PLAN", "REPLAN")

CAUSES: dict[str, Cause] = {
    # final-answer checks
    "ANALYSIS": Cause(PAUSE, "Analisis di balik jawaban ini belum lolos validasi.", _ANSWER),
    "ROUTING": Cause(PAUSE, "Pertanyaan ini butuh analisis yang tervalidasi, dan belum ada yang menopang jawaban ini.",
                     _ANSWER),
    "PROVENANCE": Cause(PAUSE, "Sebagian angka belum bisa ditelusuri ke sumbernya.", _ANSWER),
    "FINDINGS": Cause(PAUSE, "Tafsiran hasil riset belum cocok dengan putusan backend.", _ANSWER),
    "FINDINGS_2": Cause(PAUSE, "Tafsiran hasil riset belum cocok dengan putusan backend.", _ANSWER),
    "TYPED_FIGURES": Cause(ANNOTATE),
    "DEFINITION": Cause(ANNOTATE),
    "METHODOLOGY": Cause(ANNOTATE),
    "METHODOLOGY_PROVENANCE": Cause(ANNOTATE),
    "REFERENCE": Cause(ANNOTATE),  # one kind per set of failing references: REFERENCE:<hash>
    "PLAN_NOT_EXECUTED": Cause(ANNOTATE),  # the approved plan stays pending (M19)
    "RESEARCH_RUN_INCOMPLETE": Cause(ANNOTATE),
    # Research Plan checks
    "PLAN_VERSION": Cause(PAUSE, "Rencana riset belum dalam bentuk yang bisa dijalankan.", _PLAN),
    "PLAN_FINDINGS": Cause(PAUSE, "Rencana riset belum lengkap (arah, horizon, satuan, definisi sukses atau efek "
                                  "minimum).", _PLAN),
    "PLAN_CARRIED_INPUTS": Cause(PAUSE, "Rencana riset menyebut tabel yang belum dirilis di percakapan ini.", _PLAN),
    "PLAN_FEASIBILITY": Cause(PAUSE, "Ketersediaan data rencana ini belum bisa dipastikan.", _PLAN),
    "PLAN_FEASIBILITY_2": Cause(PAUSE, "Ketersediaan data rencana ini belum bisa dipastikan.", _PLAN),
    "PLAN_TEXT_PROVENANCE": Cause(PAUSE, "Sebagian angka di teks rencana belum bisa ditelusuri ke sumbernya.", _PLAN),
    "PLAN_PROVENANCE": Cause(PAUSE, "Sebagian angka di rencana belum bisa ditelusuri ke sumbernya.", _PLAN),
    "PLAN_SUCCESS_RULE": Cause(CONFIRM),
    "PLAN_MIN_EFFECT": Cause(CONFIRM),
    "PLAN_HORIZON": Cause(CONFIRM),
    "PLAN_VARIANT_COVERAGE": Cause(ANNOTATE),
    # conditions outside the checks
    "REPAIR_BUDGET": Cause(ALTERNATIVES),
    "SANDBOX_BUSY": Cause(PAUSE, "Ruang analisis sedang penuh dipakai jawaban lain.", ("CONTINUE", "ACCEPT_PARTIAL")),
    "MAX_ITERATIONS": Cause(PENDING_DECISION),
    "ANALYSIS_TIMEOUT": Cause(PENDING_DECISION),
    "TOOL_CALL_BUDGET": Cause(PENDING_DECISION),
    "CONTEXT_BUDGET": Cause(PENDING_DECISION),
}


def cause_of(kind: str) -> Cause:
    """The cause of a check kind (REFERENCE:<hash> reads as REFERENCE). An unknown kind pauses, never ends."""
    return CAUSES.get(kind.split(":", 1)[0]) or Cause(PAUSE, "Pemeriksaan belum selesai.", _ANSWER)


def pause_question(kind: str) -> str:
    """The question a paused answer ends with: the cause in plain words and its choices."""
    cause = cause_of(kind)
    choices = "; ".join(f"{index}) {OPTIONS[option]}" for index, option in enumerate(cause.options, start=1))
    return (f"Jawaban ini dijeda: {cause.reason} Pilih: {choices}. Atau tulis instruksi lain.").strip()


def pause_record(kind: str, request_id: str, kept: dict[str, Any] | None = None) -> dict[str, Any]:
    """execution.pause and the data record's pause: the cause, its choices and what the next message can build on.
    EXEC-X (M124): `question` is the exact text the answer ends with, so a front-end that shows the choices as buttons
    can leave that text out; `needs_input` marks a choice the user completes in their own words."""
    cause = cause_of(kind)
    return {"version": VERSION, "cause": kind.split(":", 1)[0], "reason": cause.reason,
            "question": pause_question(kind),
            "options": [{"id": option, "label": OPTIONS[option], "needs_input": option in NEEDS_INPUT}
                        for option in cause.options],
            "request_id": request_id, "kept": kept or {}}


def pause_note(pause: dict[str, Any]) -> str:
    """The note the next run reads: the previous answer paused and the user's message answers its question."""
    labels = "; ".join(f"{o.get('id')} ({o.get('label')})" for o in pause.get("options") or [])
    kept = pause.get("kept") or {}
    return ("The previous answer of this conversation paused (" + str(pause.get("cause")) + ": "
            + str(pause.get("reason")) + ") and asked the user to choose: " + labels + ". The user's newest message "
            "answers that question. Act on it: for RECOMPUTE or CONTINUE, redo the part that was not verified with "
            "the tools of this step (sessions, data and released tables of earlier answers are reused); for "
            "ACCEPT_PARTIAL, answer from what was verified; for a plan, present the revised plan. Anything else the "
            "user wrote decides instead." + (f" Kept from the paused answer: {kept}." if kept else ""))
