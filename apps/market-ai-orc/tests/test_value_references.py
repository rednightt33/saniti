"""P11 value references and #15 backend-rendered findings (AI_ENABLE_VALUE_REFERENCES; user decision 2026-09-30),
with M39 (every LIMITATION after a completed run keeps the backend findings) and P10 (a zero count negates a verdict
phrase)."""
from __future__ import annotations

from typing import Any

import pytest

from app.orchestrator import AgentOrchestrator, build_system_prompt, negated_or_zero, response_contract
from app.provenance import SourceIndex, check_answer, parse_numbers
from app.schemas import AgentRunRequest, final_response_schema
from app.value_refs import UNRESOLVED, ReferenceError_, ReferenceSources, format_value, render
from conftest import ScriptedClient, final_response, make_settings
from test_multi_angle import (FINDINGS, MA, RUN_SCRIPT, Clock, RunSandbox, finding, findings_answer,
                              issued_continuation, ma_registry)

REFS = {**MA, "AI_ENABLE_VALUE_REFERENCES": "true"}


def refs_run(script: list, run_sandbox: RunSandbox | None = None):
    _, body = issued_continuation("APPROVE")
    scripted = ScriptedClient(script)
    sandbox = run_sandbox or RunSandbox()
    runner = AgentOrchestrator(make_settings(**REFS), scripted, ma_registry(sandbox), wall_clock=Clock(),
                               draft_reader=lambda draft_id: None)
    result = runner.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="Setuju.",
                                        continuation=body))
    return result, scripted


def narrative_answer(answer: str, angles: dict[str, str] | None = None) -> dict[str, Any]:
    angles = angles if angles is not None else {"a_fall": "Penurunan tajam diikuti return lebih tinggi.",
                                                "a_rank": "Data belum bisa membedakan efeknya."}
    return {"response_type": "ANSWER", "answer": answer, "clarification_question": None, "assumptions": [],
            "limitations": [], "research_plan": None,
            "research_findings": [{"angle_id": a, "interpretation": {
                "answer": text, "usefulness": "Bandingkan dengan biaya transaksi.", "follow_up": "Uji periode lain."}}
                for a, text in angles.items()]}


# ---------------------------------------------------------------- the renderer

@pytest.mark.parametrize("value,fmt,places,shown", [
    (0.9955673, "dec", 2, "1,00"), (0.9955673, None, None, "0,996"), (1234567.891, None, None, "1.234.568"),
    (-1.2034, "pp", 2, "−1,20 pp"), (0.0243, "pct", 2, "2,43%"), (24.3, "pctv", 1, "24,3%"),
    (1234567890, "rp", None, "Rp 1,23 miliar"), (56, None, None, "56"), (1.5, "x", 1, "1,5 kali"),
    (0.5, None, None, "0,50"), (-0.004, "dec", 2, "0,00")])
def test_every_format_reads_back_as_the_same_governed_figure(value, fmt, places, shown) -> None:
    assert format_value(value, fmt, places) == shown
    index = SourceIndex()
    index.add("FACT", [value])
    assert parse_numbers(shown) and check_answer(shown, index).unsupported == []


def sources() -> ReferenceSources:
    refs = ReferenceSources()
    refs.add("finding", "a_fall", {"sample": {"effective": 56},
                                   "estimates": {"primary": {"estimate": 0.9955673, "ci": [0.5, 1.4]}}},
             "DATA_COVERAGE_VERIFIED")
    refs.add("out", "out_1", {"rows": [{"ticker": "BBRI", "close": 4500.0}, {"ticker": "BMRI", "close": 6000}]},
             "DATA_COVERAGE_VERIFIED")
    refs.add("fact", "1", 12.5, "FACT")
    return refs


def test_references_resolve_paths_selectors_and_functions() -> None:
    out = render("Efek {{finding.a_fall.estimates.primary.estimate|dec:2}}, sampel {{finding.a_fall.sample.effective}}"
                 ", lebar CI {{diff(finding.a_fall.estimates.primary.ci.1, finding.a_fall.estimates.primary.ci.0)"
                 "|dec:2}}, BBRI {{out.out_1.rows[ticker=BBRI].close|rp}}, BMRI {{out.out_1.rows.1.close|int}}, "
                 "rasio {{ratio(out.out_1.rows.1.close, out.out_1.rows.0.close)|x:2}}, fakta {{fact.1}}.", sources())
    assert out.problems == [] and out.count == 7
    assert out.text == ("Efek 1,00, sampel 56, lebar CI 0,90, BBRI Rp 4.500, BMRI 6.000, rasio 1,33 kali, "
                        "fakta 12,50.")
    assert {v.label for v in out.values} == {"DATA_COVERAGE_VERIFIED", "FACT"}


def test_a_unit_typed_next_to_a_reference_that_shows_it_is_dropped_once() -> None:
    # P22 (ma-reason-20261001b m01): "{{finding....estimate|pp:2}} pp" read "-0,10 pp pp"
    out = render("Selisih {{finding.a_fall.estimates.primary.estimate|pp:2}} pp; porsi {{fact.1|pctv:1}} %, "
                 "rasio {{ratio(out.out_1.rows.1.close, out.out_1.rows.0.close)|x:2}} kali lipat, "
                 "nilai Rp {{out.out_1.rows.0.close|rp}} dan {{out.out_1.rows.1.close|rp}} rupiah.", sources())
    assert out.text == ("Selisih 1,00 pp; porsi 12,5%, rasio 1,33 kali lipat, nilai Rp 4.500 dan Rp 6.000 rupiah.")
    assert out.dropped_units == ["pp", "%", "kali", "Rp"]
    # a different word or a longer one is kept: "ppm" is not "pp", "kalinya" is not "kali"
    kept = render("{{finding.a_fall.estimates.primary.estimate|pp:2}} ppm, {{fact.1|x:1}} kalinya", sources())
    assert kept.text == "1,00 pp ppm, 12,5 kali kalinya" and kept.dropped_units == []
    big = ReferenceSources()
    big.add("out", "out_9", {"rows": [{"v": 6.94e10}, {"v": -2.5e10}]}, "DATA_COVERAGE_VERIFIED")
    shown = render("{{out.out_9.rows.0.v|rp}} miliar dan Rp {{out.out_9.rows.1.v|rp}}", big)
    assert shown.text == "Rp 69,40 miliar dan \u2212Rp 25,00 miliar" and shown.dropped_units == ["miliar", "Rp"]


def test_an_unknown_reference_names_what_exists() -> None:
    out = render("{{finding.a_rank.sample.effective}} {{finding.a_fall.samples}} {{fact.1|money}} {{out.out_1.rows"
                 "[ticker=XXXX].close}} {{finding.a_fall.estimates}}", sources())
    # M43 (user decision 2026-09-30): a missing field and an object show their name; the rest stay unresolved
    assert out.text.count(UNRESOLVED) == 3 and "[samples]" in out.text and "[estimates]" in out.text
    joined = " ".join(out.problems)
    assert "available: finding.a_fall" in joined  # P18: refusals list full references
    assert "unknown format 'money'" in joined and "values: BBRI, BMRI" in joined
    assert [(expression, name) for expression, name, _ in out.missing] == [
        ("finding.a_fall.samples", "samples"), ("finding.a_fall.estimates", "estimates")]
    assert "its fields: sample, estimates" in out.missing[0][2] and "is an object" in out.missing[1][2]
    assert sorted(out.failed) == ["fact.1", "finding.a_rank.sample.effective", "out.out_1.rows[ticker=XXXX].close"]


def test_a_field_name_with_a_dot_resolves_and_an_exact_field_wins() -> None:  # P15
    refs = ReferenceSources()
    refs.add("out", "o1", {"content": {"XL_days_1.0": 51, "XL_days_1": 7, "a": {"b": 2}, "a.b": 3}}, "FACT")
    out = render("{{out.o1.content.XL_days_1.0}} {{out.o1.content.XL_days_1}} {{out.o1.content.a.b}}", refs)
    assert out.text == "51 7 2" and not out.problems and not out.missing
    assert render("{{out.o1.content.XL_days_1.5}}", refs).text == "[XL_days_1.5]"


# ---------------------------------------------------------------- the prompt, contract and schema

def test_the_references_rules_and_the_narrative_schema_only_with_the_flag() -> None:
    on = build_system_prompt(False, True, True, final_contract=True, plan_feasibility=True, multi_angle=True,
                             value_references=True)
    off = build_system_prompt(False, True, True, final_contract=True, plan_feasibility=True, multi_angle=True)
    assert "VALUE REFERENCES" in on and "{{finding.<angle_id>.<path>}}" in on and "VALUE REFERENCES" not in off
    assert "interpretation in three parts" in on and "interpretation in four parts" in off
    assert "value references {{...}}" in response_contract(True, False, False, True, True)
    items = final_response_schema(True, False, False, True, True)["properties"]["research_findings"]["anyOf"][0]
    assert set(items["items"]["properties"]) == {"angle_id", "interpretation"}
    assert set(items["items"]["properties"]["interpretation"]["properties"]) == {"answer", "usefulness", "follow_up"}
    legacy = final_response_schema(True, False, False, True)["properties"]["research_findings"]["anyOf"][0]
    assert set(legacy["items"]["properties"]) == {"angle_id", "status", "interpretation"}


# ---------------------------------------------------------------- end to end (multi-angle, flag on)

def test_the_answer_is_rendered_and_every_angle_carries_the_backend_block() -> None:
    answer = ("Sudut a_fall mendukung hipotesis: selisih return {{finding.a_fall.estimates.primary.estimate|pp:2}} "
              "(sampel efektif {{finding.a_fall.sample.effective}} tanggal); a_rank belum cukup bukti.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(narrative_answer(answer))])
    assert result.response.response_type == "ANSWER", result.response
    assert "1,25 pp" in result.response.answer and "120 tanggal" in result.response.answer
    assert "{{" not in result.response.answer
    # the complete_research_run result showed the model each finding's ref
    assert '"ref": "finding.a_fall"' in str(scripted.payloads[3]["input"]) \
        or '"ref":"finding.a_fall"' in str(scripted.payloads[3]["input"])
    findings = result.response.research_findings
    assert [(f.angle_id, f.status) for f in findings] == [
        ("a_fall", "SUPPORTED"), ("a_rank", "INSUFFICIENT_EVIDENCE"), ("a_lag", "NOT_RUN")]
    fall, rank, lag = findings
    assert fall.backend.effective_sample == 120 and fall.backend.estimate == 1.25 and fall.backend.ci == [0.4, 2.1]
    assert "sampel efektif 120" in fall.interpretation.evidence and "Status backend SUPPORTED" in \
        fall.interpretation.evidence
    assert rank.interpretation.answer == "Data belum bisa membedakan efeknya."
    assert lag.interpretation.answer == "Tidak diinterpretasikan oleh model."  # not interpreted, still reported
    dumped = result.model_dump(mode="json")["response"]["research_findings"][0]
    assert dumped["backend"]["status"] == "SUPPORTED"
    assert result.execution.validation_gate in ("PASSED", "ANNOTATED")


def test_a_missing_field_is_refused_once_then_shown_by_name_in_an_answer() -> None:  # M43
    bad = narrative_answer("Selisih {{finding.a_fall.estimates.primary.estimate|pp:2}}, ambang {{finding.a_fall."
                           "min_filter}} hari.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(bad), final_response(bad)])
    assert "value references that do not resolve" in str(scripted.payloads[4]["input"][-1])
    assert "estimates" in str(scripted.payloads[4]["input"][-1])  # names the fields that exist
    assert result.response.response_type == "ANSWER" and result.execution.validation_gate == "ANNOTATED"
    assert "1,25 pp" in result.response.answer and "ambang [min_filter] hari" in result.response.answer
    assert UNRESOLVED not in result.response.answer and "tidak ada di hasil" not in result.response.answer
    assert any("min_filter" in line and "field-nya tidak ada" in line for line in result.response.limitations)
    assert [f.status for f in result.response.research_findings] == ["SUPPORTED", "INSUFFICIENT_EVIDENCE", "NOT_RUN"]


def test_a_repaired_missing_field_leaves_a_clean_answer() -> None:
    bad = narrative_answer("Selisih {{finding.a_fall.estimate}}.")
    fixed = narrative_answer("Selisih {{finding.a_fall.estimates.primary.estimate|pp:2}}.")
    result, _ = refs_run([*RUN_SCRIPT, final_response(bad), final_response(fixed)])
    assert result.response.response_type == "ANSWER" and "1,25 pp" in result.response.answer
    assert not any("field-nya tidak ada" in line for line in result.response.limitations)


def test_an_annotated_draft_refused_by_another_gate_does_not_mark_the_clean_answer() -> None:
    bad = narrative_answer("Selisih {{finding.a_fall.min_filter}} hari.")
    typed = narrative_answer("Selisih {{finding.a_fall.min_filter}} hari dan 9,9 pp.")  # refused by PROVENANCE
    fixed = narrative_answer("Selisih {{finding.a_fall.estimates.primary.estimate|pp:2}}.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(bad), final_response(typed), final_response(fixed)])
    assert "9,9" in str(scripted.payloads[5]["input"][-1])  # the annotated draft was refused by PROVENANCE
    clean, _ = refs_run([*RUN_SCRIPT, final_response(fixed)])
    assert result.response.response_type == "ANSWER"
    assert result.execution.validation_gate == clean.execution.validation_gate
    assert result.response.limitations == clean.response.limitations  # no missing-field line from the refused draft


def test_another_unresolved_reference_is_refused_once_then_marked() -> None:
    # P14 (user decision 2026-10-01): after its repair the reference is marked, the answer keeps its type
    bad = narrative_answer("Selisih {{finding.a_nope.estimate}}.")  # an unknown angle, not a missing field
    result, _ = refs_run([*RUN_SCRIPT, final_response(bad), final_response(bad)])
    assert result.response.response_type == "ANSWER" and result.execution.validation_gate == "ANNOTATED"
    assert UNRESOLVED in result.response.answer
    assert any("[nilai tidak tersedia]" in line for line in result.response.limitations)
    assert [f.status for f in result.response.research_findings] == ["SUPPORTED", "INSUFFICIENT_EVIDENCE", "NOT_RUN"]


def test_each_distinct_reference_error_gets_one_repair_up_to_two() -> None:  # P16
    first = narrative_answer("Selisih {{finding.a_nope.estimate}}.")
    second = narrative_answer("Selisih {{finding.a_other.estimate}}.")
    third = narrative_answer("Selisih {{finding.a_third.estimate}}.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(first), final_response(second), final_response(third)])
    assert "a_nope" in str(scripted.payloads[4]["input"][-1]) and "a_other" in str(scripted.payloads[5]["input"][-1])
    assert len(scripted.payloads) == 6  # the third distinct error finds the budget spent: no third repair
    assert result.response.response_type == "ANSWER" and UNRESOLVED in result.response.answer  # marked (P14)
    same = narrative_answer("Selisih {{finding.a_nope.estimate}}.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(first), final_response(same)])
    assert len(scripted.payloads) == 5 and result.response.response_type == "ANSWER"  # the same error: one repair


def test_a_typed_truncated_figure_is_refused_and_a_reference_repairs_it() -> None:
    typed = narrative_answer("Selisih return 1,24 pp pada a_fall.")  # 1.25 cut to 1,24 instead of rounded
    fixed = narrative_answer("Selisih return {{finding.a_fall.estimates.primary.estimate|pp:2}} pada a_fall.")
    result, scripted = refs_run([*RUN_SCRIPT, final_response(typed), final_response(fixed)])
    assert "1,24" in str(scripted.payloads[4]["input"][-1])
    assert result.response.response_type == "ANSWER" and "1,25 pp" in result.response.answer


def test_m39_a_provenance_limitation_keeps_the_backend_findings() -> None:
    typed = narrative_answer("Selisih return 9,9 pp.")
    result, _ = refs_run([*RUN_SCRIPT, final_response(typed), final_response(typed)])
    assert result.response.response_type == "LIMITATION" and result.execution.validation_gate == "FORCED_LIMITATION"
    assert [f.status for f in result.response.research_findings] == ["SUPPORTED", "INSUFFICIENT_EVIDENCE", "NOT_RUN"]
    assert result.response.research_findings[0].backend is not None


def test_m39_without_references_a_forced_limitation_keeps_the_backend_findings() -> None:
    from test_multi_angle import approved_run

    typed = findings_answer(text="Sudut a_fall: return 9,9 persen lebih tinggi (sampel efektif 120).")
    result, _, _, _ = approved_run([*RUN_SCRIPT, final_response(typed), final_response(typed)])
    assert result.response.response_type == "LIMITATION"
    assert [f.status for f in result.response.research_findings] == ["SUPPORTED", "NOT_RUN", "INSUFFICIENT_EVIDENCE"]


# ---------------------------------------------------------------- P10

def test_p10_a_zero_count_negates_a_verdict_phrase() -> None:
    sentence = ("Peta sintesis tidak mengizinkan kesimpulan bahwa sudut-sudut saling menguatkan karena hanya ada "
                "0 keluarga metode didukung, jadi hasilnya dibaca per sudut.")
    assert negated_or_zero(sentence, sentence.index("didukung"))
    for text in ("Nol sudut didukung oleh data.", "None of the angles is supported by the data."):
        assert negated_or_zero(text, text.lower().index("didukung" if "didukung" in text else "supported"))
    claim = "Semua 3 dari 3 sudut didukung oleh data."
    assert not negated_or_zero(claim, claim.index("didukung"))
    decimal = "Return 0,5% lebih tinggi dan hipotesis didukung."
    assert not negated_or_zero(decimal, decimal.index("didukung"))


def unsupported() -> RunSandbox:
    """No angle is SUPPORTED (as in suite20b r08)."""
    return RunSandbox(findings=[finding("a_fall", "INSUFFICIENT_EVIDENCE", "STATISTICS_VERIFIED"),
                                *[f for f in FINDINGS if f["angle_id"] != "a_fall"]])


def test_p10_the_r08_sentence_passes_the_findings_gate_and_a_real_claim_does_not() -> None:
    rank_only = {"a_rank": "Data belum bisa membedakan efeknya."}
    r08 = narrative_answer("Tidak ada sudut yang SUPPORTED; hanya 0 keluarga metode didukung, jadi tidak ada "
                           "kesimpulan gabungan.", rank_only)
    result, _ = refs_run([*RUN_SCRIPT, final_response(r08)], unsupported())
    assert result.response.response_type == "ANSWER", result.response.limitations
    claim = narrative_answer("Hipotesis terbukti dan didukung data.", rank_only)
    result, scripted = refs_run([*RUN_SCRIPT, final_response(claim), final_response(r08)], unsupported())
    assert "states a supported verdict" in str(scripted.payloads[4]["input"][-1])
    assert result.response.response_type == "ANSWER"


# ---------------------------------------------------------------- sources of the DataNeed analysis flow

def tracker(row_reader=None) -> AgentOrchestrator:
    """An orchestrator with only what _track_references needs (the reader of released rows, M44)."""
    orc = AgentOrchestrator.__new__(AgentOrchestrator)
    orc.row_reader = row_reader
    return orc


def test_released_outputs_and_facts_become_referable_and_show_their_ref() -> None:
    from app.orchestrator import RunState
    from app.tools import ToolOutcome

    state = RunState(request_id="r", started=0.0, input_items=[])
    orc = tracker()
    completion = {"result": {"status": "COMPLETED", "released_contents": [
        {"output_id": "out_1", "name": "top5", "type": "TABLE", "rows": [{"ticker": "BBRI", "ret": 0.0412}]}]}}
    orc._track_references(state, "complete_analysis",
                                        ToolOutcome(call_id="c", name="complete_analysis", ok=True, output=completion))
    facts = {"result": {"decision": "FACTS_READY", "facts": [{"kind": "AGGREGATE", "value": 1234.5},
                                                             {"kind": "VALUE", "value": 7}]}}
    orc._track_references(state, "lookup_fact",
                                        ToolOutcome(call_id="d", name="lookup_fact", ok=True, output=facts))
    assert completion["result"]["released_contents"][0]["ref"] == "out.o1"  # P18: a short alias
    assert [f["ref"] for f in facts["result"]["facts"]] == ["fact.1", "fact.2"]
    out = render("BBRI {{out.o1.rows[ticker=BBRI].ret|pct:2}}, rata-rata {{fact.1|dec:1}}, n {{fact.2}}",
                 state.ref_sources)
    assert out.text == "BBRI 4,12%, rata-rata 1.234,5, n 7" and out.problems == []
    assert [v.label for v in out.values] == ["DATA_COVERAGE_VERIFIED", "DATABASE_AGGREGATE", "FACT"]


def test_short_aliases_and_the_unambiguous_mistyped_forms_resolve() -> None:
    """P18 (2026-10-01, m4a): output ids are out_ + 24 hex characters inside the out. namespace; the model wrote
    out.out.<hex> and out_<hex> without the namespace, and the refusal listed bare ids it then copied."""
    hex_id = "out_946408ad8bc7ee2da4597136"
    table = [{"broker": "XL", "net": 1.5}, {"broker": "SQ", "net": 2.5}]
    refs = ReferenceSources()
    refs.add("out", hex_id, {"rows": table}, "DATA_COVERAGE_VERIFIED")
    refs.alias("out", "o1", hex_id)
    for form in ("out.o1", f"out.{hex_id}", f"out.out.{hex_id[4:]}", hex_id):
        assert refs.resolve(f"{form}.rows[broker=XL].net")[0] == 1.5, form
    with pytest.raises(ReferenceError_) as missing:
        refs.resolve("out.o2.rows[broker=XL].net")
    assert "available: out.o1" in str(missing.value) and hex_id not in str(missing.value)
    other = ReferenceSources()  # the same id in two namespaces is ambiguous without one
    other.add("out", hex_id, {"rows": table}, "DATA_COVERAGE_VERIFIED")
    other.add("analysis", hex_id, {"rows": table}, "DATA_COVERAGE_VERIFIED")
    with pytest.raises(ReferenceError_):
        other.resolve(f"{hex_id}.rows[broker=XL].net")
    refs.add("finding", "a_rank", {"sample": {"effective": 40}}, "FORMULA_AND_STATISTICS_VERIFIED")
    assert refs.resolve("finding.a_rank.sample.effective")[0] == 40  # other namespaces are unaffected


def test_a_row_named_by_its_key_alone_resolves_and_refusals_use_the_alias() -> None:
    """ma-steps-20261001a, a05: out.o1.rows[SEMA].base_value was refused as "out.out_3f37… has no field 'rows[SEMA]'"
    (no hint, and the long id the alias exists to avoid)."""
    sources = ReferenceSources()
    rows = [{"ticker": "SEMA", "sector": "Tech", "base_value": 10.5}, {"ticker": "BBCA", "sector": "Banks",
                                                                       "base_value": 9.0}]
    sources.add("out", "out_" + "3" * 24, {"name": "rank", "rows": rows}, "DATA_COVERAGE_VERIFIED")
    sources.alias("out", "o1", "out_" + "3" * 24)
    assert sources.lookup("out.o1.rows[SEMA].base_value").value == 10.5
    assert sources.lookup("out.o1.rows[ticker=BBCA].base_value").value == 9.0
    with pytest.raises(ReferenceError_) as missing:
        sources.lookup("out.o1.rows[XXXX].base_value")
    assert "out.o1.rows[ticker=XXXX]" in str(missing.value) and "out_3" not in str(missing.value)
    with pytest.raises(ReferenceError_) as field_error:
        sources.lookup("out.o1.total")
    assert "out.o1 has no field 'total'" in str(field_error.value)
    same = [{"sector": "Banks", "v": 1.0}, {"sector": "Banks", "v": 2.0}]  # no column identifies these rows
    sources.add("out", "out_" + "4" * 24, {"rows": same}, "DATA_COVERAGE_VERIFIED")
    with pytest.raises(ReferenceError_, match=r"\[<column>=Banks\]"):
        sources.lookup("out.out_" + "4" * 24 + ".rows[Banks].v")


def test_an_invalid_reference_form_is_named_with_its_fault() -> None:
    """P7 (ma-steps-20261001a, e02): `|dec:2e-0` was refused as "not closed or has an invalid form" only."""
    sources = ReferenceSources()
    sources.add("finding", "a", {"p": 0.0003}, "DATA_COVERAGE_VERIFIED")
    out = render("p {{finding.a.p|dec:2e-0}} dan {{finding.a.p|sci}} serta {{finding.a.p|dec:3}}", sources)
    problem = out.problems[-1]
    assert "'{{finding.a.p|dec:2e-0}}': places '2e-0' must be one digit 0-9" in problem
    assert any("unknown format 'sci'" in p for p in out.problems)  # a well-formed reference with an unknown format
    unclosed = render("p {{finding.a.p", sources)
    assert "without its closing" in unclosed.problems[-1]
