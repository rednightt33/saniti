"""Every line the backend writes for the user (M125, user decision 2026-10-08: "bahasa sangat baku ... too much technical
terms exposed"). Plain, everyday Indonesian; no table or column names, no internal ids (analysis, session, experiment,
output) and no backend codes. A code reaches the user only through words(): its plain words, or, for a code not listed
yet, the code made readable. Instructions to the model stay in English in the orchestrator; they are not here.

tests/test_user_texts.py reads every text here (and the lines the orchestrator builds from them) and fails on an
internal name, a code or an English sentence.

EXEC-UI-1019B (user 2026-10-19: "semua label tetap bahasa Inggris"; "langkah progres orc ke bahasa Inggris: Ya"): the
texts EDGE shows outside the answer (the run's progress steps, its hurdles and why a run failed) are English and are
named in INTERFACE_TEXTS; every line inside the answer stays Indonesian.
"""
from __future__ import annotations

import re

# ---- codes as words ----
WORDS = {
    # verdicts and statuses of a research finding
    "SUPPORTED": "didukung data", "PARTIALLY_SUPPORTED": "didukung sebagian", "NOT_SUPPORTED": "tidak didukung data",
    "INCONCLUSIVE": "belum bisa disimpulkan", "NOT_EVALUATED": "tidak dievaluasi",
    "INSUFFICIENT_EVIDENCE": "bukti belum cukup", "INVALID": "tidak valid", "NOT_RUN": "tidak dijalankan",
    "INSUFFICIENT_SAMPLE": "sampel terlalu sedikit", "UNDERPOWERED": "sampel terlalu kecil untuk menyimpulkan",
    # why a finding has its status
    "EFFECT_CI_EXCLUDES_ZERO": "rentang keyakinannya tidak memuat nol",
    "MULTIPLE_TESTING_NOT_PASSED": "tidak lolos koreksi untuk banyak perbandingan",
    "EFFECT_OPPOSITE_TO_EXPECTED": "arah efeknya berlawanan dengan dugaan",
    "MINIMUM_SAMPLE_NOT_MET": "sampel minimum tidak terpenuhi", "INSUFFICIENT_INPUT_DATA": "data masukan tidak cukup",
    "INSUFFICIENT_HISTORY": "riwayat data tidak cukup", "MEAN_DIFFERENCE": "selisih rata-rata",
    "DATES_AUTOCORRELATION_ADJUSTED": "tanggal (disesuaikan untuk autokorelasi)",
    # how far the backend checked a calculation
    "CALCULATION_VERIFIED": "dihitung ulang dan cocok", "STATISTICS_VERIFIED": "statistiknya dihitung ulang dan cocok",
    "FORMULA_AND_STATISTICS_VERIFIED": "rumus dan statistiknya dihitung ulang dan cocok",
    "EXECUTION_ONLY": "hanya dijalankan, tidak dihitung ulang", "NOT_PERFORMED": "tidak dihitung ulang",
    "UNVERIFIED": "belum bisa dicek", "FAILED": "gagal", "INCOMPLETE": "belum lengkap", "PASSED": "lolos",
    # the direction of the evidence against the hypothesis
    "EXPECTED": "searah dugaan", "OPPOSITE": "berlawanan dengan dugaan", "NONE": "tidak ada arah yang jelas",
    # statistics a question can ask for
    "RSI": "RSI", "SMA": "rata-rata bergerak", "STD": "simpangan baku", "ZSCORE": "skor-z", "RETURN": "return",
    "FORWARD_RETURN": "return ke depan", "CORRELATION": "korelasi", "EVENT_STUDY": "studi peristiwa",
    "AVERAGE": "rata-rata",
    # horizon units
    "DAY": "hari", "WEEK": "minggu", "MONTH": "bulan",
    # where a cited figure comes from
    "FACT": "data pasar", "WEB": "sumber web",
    # the outcome of a web lookup (research_web, find_web_fact)
    "OK": "ditemukan", "PARTIAL": "sebagian", "NOT_FOUND": "tidak ditemukan",
    "BUDGET_EXHAUSTED": "batas biaya habis", "CONFIRMED": "terkonfirmasi", "CONFLICTING": "sumbernya berbeda",
    # EXEC-FRICTION (M142): why a step or a draft was refused (execution.hurdles)
    "RELATIONSHIP_KEY_MISMATCH": "kunci penggabungan tabel tidak sesuai",
    "INVALID_REQUEST_ID": "nama permintaan data tidak sesuai aturan",
    "AGGREGATE_COLUMNS_MISMATCH": "kolom ringkasan tidak sesuai aturan", "AGGREGATE_INVALID": "ringkasan tidak sesuai aturan",
    "REVISION_REQUIRED": "permintaan perlu diperbaiki", "INVALID_ARGUMENTS": "isian langkah tidak sesuai format",
    "SCRIPT_ERROR": "kode berhenti karena galat", "TIMEOUT": "waktu habis", "TOOL_TIMEOUT": "waktu habis",
    "SESSION_CAPACITY_EXCEEDED": "kapasitas ruang analisis penuh", "NOT_FEASIBLE": "tidak bisa dijalankan",
    "TYPED_FIGURES": "angka ditulis tanpa rujukan", "PROVENANCE": "ada angka tanpa sumber",
    "DEFINITION": "definisi tidak cocok dengan hasil sebelumnya", "REFERENCE": "rujukan angka tidak dikenali",
    "ROUTING": "jawaban perlu hasil analisis", "FINAL_REASK": "bentuk jawaban perlu diulang", "TOOL_MARKUP": "panggilan alat tertulis sebagai teks", "FINAL_REJECTED": "bentuk jawaban tidak sesuai",
}

# ---- the hurdles of a run (EXEC-FRICTION, M142): what the backend refused, in the order it happened ----
HURDLE_STEPS = {
    "submit_data_need_spec": "Data request", "check_data_feasibility": "Data feasibility check",
    "check_research_feasibility": "Research feasibility check", "prepare_data_bundle": "Data preparation",
    "open_analysis_session": "Opening the analysis session", "run_python": "Analysis code",
    "complete_analysis": "Closing the analysis", "research_web": "Web search", "query_metric": "Metric lookup",
    "lookup_reference": "Reference data lookup", "export_result": "Table export",
}
HURDLE_TOOL_STEP = "A work step"
# EXEC-IMPL-1016 Fase 4.3 (UI-1015B): the steps EDGE shows while a run works (app/progress.py); a tool without its own
# label above is named by what it does (its ToolSpec effect)
PROGRESS_ROUTING = "Understanding the question"
PROGRESS_THINKING = "Planning the next step"
PROGRESS_SERVICES_WAIT = "Waiting for services to be ready."
# EXEC-M181 and the branch behaviours (user 2026-10-19/20): a call asked again is shown, never silent
PROGRESS_PROVIDER_RETRY = "AI provider did not respond, trying once more"
PROGRESS_RUNAWAY_RETRY = "AI used its whole budget on thinking, asking it to answer more briefly"
REASONING_RUNAWAY_MESSAGE = ("The AI used its whole output budget on thinking twice without answering. Try again, "
                             "choose a lower thinking level, or choose another model.")
PROGRESS_SANDBOX_SESSION = "Initiating sandbox session."
PROGRESS_EFFECTS = {"READS": "Reading the catalog and results", "OWN_ARTIFACT": "Saving results",
                    "FETCHES_DATA": "Fetching data", "FETCHES_WEB": "Web search",
                    "COMPUTES": "Running the analysis"}
HURDLE_REFUSED = "{step} refused{why}"
HURDLE_FAILED = "{step} failed{why}"
HURDLE_GATE = "The answer check sent the draft back{why}"
# H (user 2026-10-20, go): a gate that did not send the draft back says what it did instead, without "not resolved"
# (advice mode labels and sends; orchestrator GATE_OUTCOMES)
HURDLE_GATE_DONE = {
    "ANNOTATED": "The answer check labelled a part of the answer{why}; the answer was sent with the label.",
    "FORCED_LIMITATION": "The answer check could not pass the draft{why}; it was sent marked as not validated.",
    "CONFIRMED": "The answer check listed values{why} for you to confirm before anything runs.",
}
HURDLE_FORMAT = "The answer's format was asked for again{why}"
# why a step or a draft was refused, in the interface's words (EDGE shows the hurdles outside the answer)
HURDLE_WORDS = {
    "RELATIONSHIP_KEY_MISMATCH": "the keys joining the tables do not match",
    "INVALID_REQUEST_ID": "the data request's name breaks the naming rule",
    "AGGREGATE_COLUMNS_MISMATCH": "the summary columns break the rules", "AGGREGATE_INVALID": "the summary breaks the rules",
    "REVISION_REQUIRED": "the request needs a fix", "INVALID_ARGUMENTS": "the step's inputs had the wrong format",
    "SCRIPT_ERROR": "the code stopped with an error", "TIMEOUT": "time ran out", "TOOL_TIMEOUT": "time ran out",
    "SESSION_CAPACITY_EXCEEDED": "the analysis space was full", "NOT_FEASIBLE": "it cannot be run",
    "TYPED_FIGURES": "figures typed without a reference", "PROVENANCE": "figures without a source",
    "DEFINITION": "said to match an earlier result whose definition differs", "REFERENCE": "a figure's reference was "
    "not recognised", "UNITS": "a figure's unit was missing", "UNRECORDED_TEST": "a statistic no recorded test made",
    "REPRODUCTION": "a reproduction did not hold", "ROUTING": "the answer needed an analysis result",
    "FINAL_REASK": "the answer had to be sent again in the right format",
    "TOOL_MARKUP": "a tool call was written as text", "FINAL_REJECTED": "the answer's format did not fit",
    "BUNDLE_EXPIRED": "the prepared data had expired", "OUTPUT_EXPIRED": "the result had expired",
    "FAILED": "failed", "INCOMPLETE": "incomplete",
}
# the texts EDGE shows outside the answer: English (tests/test_user_texts.py)
INTERFACE_TEXTS = frozenset({
    "PROGRESS_ROUTING", "PROGRESS_THINKING", "PROGRESS_SERVICES_WAIT", "PROGRESS_SANDBOX_SESSION", "PROGRESS_EFFECTS",
    "PROGRESS_PROVIDER_RETRY", "PROGRESS_RUNAWAY_RETRY", "REASONING_RUNAWAY_MESSAGE", "HURDLE_STEPS",
    "HURDLE_TOOL_STEP", "HURDLE_REFUSED", "HURDLE_FAILED", "HURDLE_GATE", "HURDLE_GATE_DONE", "HURDLE_FORMAT", "HURDLE_WORDS",
    "HURDLE_OVERCOME", "HURDLE_OPEN"})
# a bare status says nothing the sentence does not already say: no reason is shown (Run A 2026-10-12: "(rejected)")
HURDLE_BARE_STATUSES = frozenset({"REJECTED", "ERROR", "FAILED", "INCOMPLETE"})
HURDLE_OVERCOME = ", then fixed."
HURDLE_OPEN = ", not resolved."


def hurdle_text(stage: str, name: str | None, code: str | None, outcome: str | None, overcome: bool) -> str:
    """One hurdle in plain words: which step, why, and whether it was overcome."""
    def reason(text: str) -> str:
        return f" ({text})" if text else ""

    parts = [part.strip() for part in str(code or name or "").split(",") if part.strip()]
    why = reason(", ".join(hurdle_words(part) for part in parts if part.upper() not in HURDLE_BARE_STATUSES)
                 or ("" if parts else hurdle_words(outcome)))
    if stage == "GATE" and outcome in HURDLE_GATE_DONE:
        return HURDLE_GATE_DONE[outcome].format(why=reason(hurdle_words(name)) if not code else why)
    if stage == "GATE":
        line = HURDLE_GATE.format(why=reason(hurdle_words(name)) if not code else why)
    elif stage == "FORMAT":
        line = HURDLE_FORMAT.format(why=reason(hurdle_words(name)))
    else:
        step = HURDLE_STEPS.get(str(name or ""), HURDLE_TOOL_STEP)
        line = (HURDLE_FAILED if outcome == "FAILED" else HURDLE_REFUSED).format(step=step, why=why)
    return line + (HURDLE_OVERCOME if overcome else HURDLE_OPEN)


def hurdle_words(code: object) -> str:
    """A hurdle's code in the interface's words; a code not listed yet is made readable instead of shown raw."""
    text = str(code or "").strip()
    return HURDLE_WORDS.get(text.upper(), text.replace("_", " ").lower())


def words(code: object) -> str:
    """A backend code in plain words; a code not listed yet is made readable instead of shown raw."""
    text = str(code or "").strip()
    return WORDS.get(text.upper(), text.replace("_", " ").lower())


def words_list(codes: object) -> str:
    return ", ".join(words(code) for code in (codes or []))


# ---- what a cited figure is (the Sources list) ----
# parts of a value address that only give structure; they are left out unless they end the address
STRUCTURE = frozenset({"groups", "estimates", "primary", "rows", "values", "summary", "stats"})
PARTS = {"CONDITION": "kelompok sinyal", "BASELINE": "kelompok pembanding", "dates": "jumlah tanggal",
         "rows": "jumlah baris", "estimate": "perkiraan", "ci": "rentang keyakinan", "p_value": "p",
         "p_adjusted": "p setelah koreksi", "mean": "rata-rata", "median": "median", "count": "jumlah",
         "condition_mean": "rata-rata kelompok sinyal", "baseline_mean": "rata-rata kelompok pembanding",
         "hit_rate": "seberapa sering naik", "effective": "sampel efektif", "value": "nilai"}
FIGURE_FROM = "Dari {source}: {what}"
FIGURE_VALUE = "nilai"
# M125 P2: every namespace a value reference can read, named for the reader (tests/test_user_texts.py checks that each
# namespace the orchestrator registers has a name here)
SOURCE_NAMES = {"out": "hasil analisis", "analysis": "hasil analisis", "finding": "hasil riset", "fact": "data pasar",
                "metric": "data pasar", "reference": "tabel referensi", "web": "fakta web",
                "data": "data yang disiapkan"}
WEB_EVIDENCE = "Fakta web · {domain}"
SELECTED_RE = re.compile(r"^(?P<name>[^\[\]]+)\[(?:[^=\[\]]+=)?(?P<value>[^\[\]]+)\]$")  # rows[Ticker=BRIS], rows[BRIS]


def value_label(expression: str, output_names: dict[str, str] | None = None) -> str:
    """A value address ("finding.x.groups.CONDITION.dates", "out.o3.rows.2.mean_return") in words: where it comes
    from and what it is. Derived from the address itself, so a new field reads as its name made readable."""
    parts = [p for p in str(expression).split(".") if p]
    if not parts:
        return ""
    namespace, rest = parts[0], parts[2:] if len(parts) > 2 else parts[1:]
    source = (output_names or {}).get(".".join(parts[:2])) if namespace == "out" else None
    source = source or SOURCE_NAMES.get(namespace) or words(namespace)
    entities, names = [], []
    for part in rest:  # a row picked by its key ("rows[Ticker=BRIS]") is named by that key: "(BRIS)"
        selected = SELECTED_RE.match(part)
        if selected:
            part = selected.group("name")
            if not selected.group("value").lstrip("-").isdigit():
                entities.append(selected.group("value").strip())
        names.append(part)
    meaning = [p for i, p in enumerate(names) if not p.isdigit() and not (p in STRUCTURE and i < len(names) - 1)]
    what = ", ".join(PARTS.get(p) or _angle(p) or words(p) for p in reversed(meaning)) or FIGURE_VALUE
    return FIGURE_FROM.format(source=source, what=what) + (f" ({', '.join(entities)})" if entities else "")


def _angle(part: str) -> str | None:
    """A multi-angle finding's angle id ("angle_a", "angle_quant") is the angle the reader sees as "sudut a"."""
    return f"sudut {part[len('angle_'):].replace('_', ' ')}" if part.startswith("angle_") and len(part) > 6 else None


# ---- notices that open a response the backend had to hold back ----
PLAN_FINDINGS_NOTICE = "Rencana riset di bawah belum lengkap, jadi belum bisa disetujui. "
FINDINGS_NOTICE = "Tafsiran hasil riset di bawah tidak cocok dengan putusan sistem; anggap angkanya belum pasti. "
ANGLE_FINDINGS_NOTICE = ("Tafsiran hasil riset beberapa sudut di bawah tidak cocok dengan temuan sistem; anggap "
                         "angkanya belum pasti. ")
GATE_NOTICE = "Analisis di balik jawaban ini belum lolos pemeriksaan; angka di bawah belum bisa dipegang. "
ROUTING_NOTICE = ("Pertanyaan ini perlu analisis yang sudah diperiksa ({families}), dan belum ada yang mendukung "
                  "jawaban ini; angka di bawah belum bisa dipegang. ")
PROVENANCE_NOTICE = "Sebagian angka di bawah belum bisa ditelusuri ke sumbernya: {numbers}. "
DATANEED_GATE_NOTICE = "Analisis data di balik jawaban ini belum selesai; angka di bawah belum bisa dipegang. "
DATANEED_ROUTING_NOTICE = ("Pertanyaan ini perlu analisis yang selesai ({families}), dan belum ada yang mendukung "
                           "jawaban ini; angka di bawah belum bisa dipegang. ")
DATANEED_PROVENANCE_NOTICE = "Sebagian angka di bawah belum bisa ditelusuri ke hasil analisis atau sumber lain: {numbers}. "
PLAN_NOT_FEASIBLE_NOTICE = ("Rencana riset belum dibuat: belum bisa dipastikan datanya tersedia dan cukup diproses "
                            "dalam sekali jalan. ")
PLAN_VERSION_NOTICE = "Rencana riset di bawah belum dalam bentuk yang bisa dijalankan, jadi belum bisa disetujui. "
PLAN_PROVENANCE_NOTICE = "Sebagian angka di bawah belum bisa ditelusuri ke rencana riset atau sumber lain: {numbers}. "

# ---- limitation lines ----
METHODOLOGY_MISSING_LINE = "Jawaban ini tidak menyertakan catatan cara menghitung."
# M160: the model provider is down (credit or key limit used up, account refused, provider unavailable); nothing ran
SERVICE_UNAVAILABLE_LINE = ("Layanan AI sedang tidak tersedia (kuota habis atau penyedia model sedang gangguan), "
                            "jadi pesan ini belum dijawab. Coba kirim ulang beberapa saat lagi.")
METHODOLOGY_WITHHELD_LINE = "Catatan cara menghitung tidak ditampilkan karena menyebut angka tanpa sumber: {numbers}."
PLAN_NOT_EXECUTED_LINE = ("Rencana riset yang Anda setujui belum dijalankan di pesan ini, jadi masih menunggu; setujui "
                          "lagi untuk menjalankannya.")
ANALYSIS_PATH_LINE = ("Jawaban ini hanya statistik historis: tanpa uji signifikansi dan tanpa koreksi untuk banyak "
                      "perbandingan; bukan kesimpulan, sebab, prediksi, atau sinyal trading.")
DERIVED_FREQUENCY_LINE = ("Angka mingguan atau bulanan diturunkan dari data harian (minggu ditutup hari Jumat, bulan di "
                          "akhir bulan); periode yang masih berjalan atau datanya belum penuh ditandai belum lengkap.")
PIT_FALLBACK_LINE = ("Data seperti yang diketahui pada tiap tanggal tidak tersedia, jadi hasil ini memakai data "
                     "referensi terkini (pengelompokan hari ini dipakai untuk tanggal-tanggal lama).")
WARNING_LINES = {
    "HISTORICAL_REFERENCE_USES_CURRENT_STATE": "Pengelompokan memakai data terkini, bukan pengelompokan yang berlaku di "
                                               "tiap tanggal lama.",
    "HISTORY_BUFFER_SHORTFALL": "Sebagian saham punya data sebelum periode lebih sedikit dari yang dibutuhkan.",
    "FUTURE_BUFFER_SHORTFALL": "Sebagian saham punya data sesudah periode lebih sedikit dari yang diminta (datanya "
                               "mungkin berhenti di tanggal acuan).",
    "FREQUENCY_GAPS": "Sebagian saham tidak punya data di beberapa hari bursa dalam periode.",
    "EMPTY_RANGE": "Satu periode yang diminta tidak punya data.",
    "PARTIAL_RANGE_COVERAGE": "Satu periode yang diminta hanya sebagian tercakup data.",
    "EMPTY_ENTITY": "Satu saham yang disebut tidak punya data.",
    "NULL_VALUES": "Sebagian nilai kosong.",
    "DUPLICATE_KEYS": "Sebagian baris data tercatat ganda.",
    "CURRENT_STATE_COLUMN": "Sebagian kolom berisi nilai hari ini di semua tanggal (misalnya sektor atau jenis broker "
                            "saat ini), bukan nilai pada tiap tanggal.",
}
CORPORATE_ACTIONS_LINE = ("Harga sudah disesuaikan untuk stock split, tetapi tidak untuk dividen; return yang melewati "
                          "aksi korporasi bisa terdistorsi.")
HISTORICAL_PATTERN_LINE = "Hasil riset hanya menggambarkan pola masa lalu; bukan bukti sebab-akibat atau prediksi."

# analyses of the older Python path (one line per analysis; its id stays in the log, not in the answer)
ANALYSIS_NOT_FINISHED_LINE = "Satu analisis belum selesai, jadi belum ada hasil hitungan darinya."
ANALYSIS_FAILED_LINE = "Satu analisis gagal dijalankan, jadi tidak ada hasil hitungan yang sudah diperiksa darinya."
ANALYSIS_NOT_VALIDATED_LINE = ("Satu analisis selesai dijalankan, tetapi pemeriksaannya {status}; hasilnya belum bisa "
                               "dipegang untuk pertanyaan ini.")
ANALYSIS_UNVERIFIED_LINE = "Cakupan dan nilai satu analisis belum bisa dicek terpisah."
ANALYSIS_NOT_RECOMPUTED_LINE = "Perhitungan satu analisis tidak dihitung ulang secara terpisah oleh sistem."
ANALYSIS_ASSUMED_LINE = "Satu analisis memakai syarat yang tidak Anda sebut: {items}."
ANALYSIS_EVIDENCE_LINE = "Kekuatan bukti satu analisis: {decision} ({level})."

# analyses of the data-need path
SESSION_NOT_COMPLETED_LINE = "Satu sesi analisis tidak diselesaikan, jadi hasilnya tidak dirilis."
SESSION_INCOMPLETE_LINE = "Satu sesi analisis belum lengkap (data atau perhitungannya belum tuntas), jadi hasilnya tidak dirilis."
COVERAGE_RECOMPUTED_LINE = ("Kelengkapan data sudah dicek. Tabel studi peristiwa dihitung ulang secara terpisah oleh "
                            "sistem dan hasilnya cocok; perhitungan lainnya tidak dihitung ulang.")
COVERAGE_ONLY_LINE = "Kelengkapan data sudah dicek; perhitungannya sendiri tidak dihitung ulang secara terpisah oleh sistem."
EVENT_STUDY_INVALID_LINE = "Sebagian tabel studi peristiwa tidak bisa dihitung ulang oleh sistem, jadi belum terverifikasi terpisah."
EARLIER_FIGURES_LINE = "Angka dari {name} dihitung di pesan sebelumnya dan tidak dihitung ulang di pesan ini."
EARLIER_COVERAGE_LINE = ("Kelengkapan datanya dicek saat angka itu dihitung; perhitungannya tidak dihitung ulang "
                         "secara terpisah oleh sistem.")
EARLIER_RESULT = "hasil sebelumnya"
IN_SAMPLE_LINE = ("Sebagian temuan diuji pada data yang sudah dibaca di langkah sebelumnya dalam percakapan ini "
                  "({detail}). Pola yang ditemukan dan diuji di periode yang sama cenderung terlihat lebih kuat dari "
                  "sebenarnya; anggap temuan ini awal dan cek ulang di periode atau saham lain.")
IN_SAMPLE_PERIOD = "periode uji {start} s/d {end} bertumpuk dengan {seen_start} s/d {seen_end}"
IN_SAMPLE_CARRIED = "hasil sebelumnya dipakai sebagai data uji"


def in_sample_detail(in_sample: dict, limit: int = 3) -> str:
    """The overlaps behind flagged findings in words: periods, never table names or ids (in_sample.details keeps
    those for the log and the data record)."""
    seen: list[str] = []
    for entries in (in_sample or {}).values():
        for entry in entries:
            text = IN_SAMPLE_CARRIED if entry.get("carried_output") else IN_SAMPLE_PERIOD.format(
                start=entry["research_range"][0], end=entry["research_range"][1],
                seen_start=entry["analysis_range"][0], seen_end=entry["analysis_range"][1])
            if text not in seen:
                seen.append(text)
    return "; ".join(seen[:limit])
RESEARCH_RUN_NOT_COMPLETED_LINE = "Riset beberapa sudut tidak diselesaikan, jadi temuannya tidak dirilis."
RESEARCH_RUN_LINE = ("Riset beberapa sudut: {planned} sudut direncanakan, {validated} punya temuan yang sudah "
                     "diperiksa, {invalid} tidak valid, {not_run} tidak dijalankan.")
RESEARCH_NOT_RECOMPUTED_LINE = "Statistik temuan yang dipakai tidak dihitung ulang secara terpisah oleh sistem."
NEEDS_ANALYSIS_LINE = "Pertanyaan ini perlu analisis yang selesai ({families}); belum ada yang mendukung jawaban ini."
NO_SOURCE_LINE = "Angka tanpa sumber yang jelas: {numbers}."

# ---- the backend's evidence sentence of one research angle ----
ANGLE_EVIDENCE = {
    "status": "Hasil: {status}",
    "reason": " ({reason})",
    "validation": "pemeriksaan: {level}",
    "sample": "sampel efektif {value}{unit}",
    "estimate": "perkiraan utama{kind} {value}",
    "ci": " (rentang keyakinan{level} {low} s/d {high})",
    "p": "{value}",
    "p_adjusted": " (setelah koreksi: {value})",
    "direction": "arah: {direction}",
}

# ---- Research Plan values the user confirms (M117) ----
PLAN_ITEM = {"experiments": "eksperimen", "angles": "sudut"}


def plan_item(kind: str, index: int) -> str:
    """How a confirmation line names an experiment or an angle: by its place in the plan, as the plan card shows it."""
    return f"{PLAN_ITEM.get(kind, kind)} {index + 1}"


def horizon_text(horizons: object) -> str:
    """Stated horizons in words ("10 hari"), for the user; the model's instruction keeps its own form."""
    return ", ".join(f"{n} {words(u)}" for n, u in sorted(horizons or []))


# the internal names a user-facing text must not show (tests/test_user_texts.py)
INTERNAL_NAME = re.compile(r"\b[a-z]+_[a-z0-9_]+\b|\b[A-Z]{2,}_[A-Z0-9_]+\b|\b[a-z]+[A-Z][A-Za-z]+\b")


# ---- the web lookups of a run (system-written; P3, 2026-10-08) ----
# The need is the model's search text, often English for wider results: it is not shown; the reader sees how many
# topics were looked up, how each ended, and the sites the answer could draw on.
WEB_LOOKUPS_LINE = "Dicari di web (bukan dari data pasar): {count} topik, {outcomes}; sumber: {domains}."
WEB_FACTS_LINE = "Fakta web (dicari sistem, bukan dari data pasar): {facts}."
WEB_FACT_ITEM = "{subject} — {attribute}: {shown} ({status})"
EVIDENCE_REFERENCED_LINE = ("Angka hasil analisis di jawaban ini dibaca langsung dari tabel hasilnya, tanpa dihitung "
                            "ulang secara terpisah.")


def web_lookups_line(lookups: list[dict]) -> str | None:
    if not lookups:
        return None
    counts: dict[str, int] = {}
    for lookup in lookups:
        counts[words(lookup.get("status"))] = counts.get(words(lookup.get("status")), 0) + 1
    domains = sorted({d for lookup in lookups for d in lookup.get("domains") or []})
    return WEB_LOOKUPS_LINE.format(count=len(lookups), outcomes=", ".join(f"{n} {w}" for w, n in counts.items()),
                                   domains=", ".join(domains[:12]) + (" …" if len(domains) > 12 else "") or "-")


# ---- an exported file is read by people (M128b, 2026-10-09) ----
EXPORT_DEFINITION = {"period": "Periode", "entities": "Saham", "filters": "Saringan", "thresholds": "Ambang",
                     "notes": "Catatan"}
EXPORT_LINEAGE = {"name": "Nama tabel", "source_tables": "Tabel sumber", "data_as_of": "Data per",
                  "reference_date": "Tanggal acuan"}
EXPORT_AUDIT = "Kode audit (untuk tim teknis)"  # the ids the audit trail joins on, kept in one line
EXPORT_PERIOD = "{start} s.d. {end}"
# EXEC-Y Fase 3 E2: a column meaning the catalog has only in English (no Indonesian text yet)
EXPORT_ENGLISH_MEANING = "{text} (teks Inggris; terjemahan belum ada)"
# EXEC-Y Fase 3 E1(1) and E1(3): the 'definisi' rows the sandbox writes from the file and the source counts
EXPORT_READING = {
    "row_rule_label": "Aturan baris",
    "row_rule_one": "Satu baris untuk setiap {key}.",
    "row_rule_many": "Satu baris untuk setiap kombinasi {keys}.",
    "and": " dan ",
    "row_rule_none": "Tidak ada kolom teks atau tanggal yang unik per baris.",
    "completeness_label": "Kelengkapan",
    "period": "Dicek terhadap tabel sumber untuk {start} s.d. {end} ({calendar} hari bursa).",
    "group": "{group}: file memuat {file} tanggal; sumber punya data pada {source} hari.",
    "all_rows": "Semua baris",
    "unchecked": "Tidak dapat dicek otomatis terhadap tabel sumber.",
    "activity_only": "Tabel sumber hanya mencatat hari yang ada aktivitasnya; hari tanpa baris berarti tidak ada "
                     "aktivitas, bukan data yang hilang.",
    # E1 (EXEC-1018B): the rows a result was computed from, in their own sheets
    "inputs_field": "Lembar input",
    "inputs": "Baris data yang dipakai untuk menghitung tabel ini, termasuk baris sebelum periodenya (misalnya harga "
              "dasar atau baris pemanasan), ada di lembar {sheets}.",
}


def _empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


# a filter of an output's definition ({column, operator, value}) as one line (live check 2026-10-09 showed
# "Saringan[0].column market_board" row by row)
FILTER_OPERATORS = {"EQ": "=", "NE": "≠", "NEQ": "≠", "GT": ">", "GE": "≥", "GTE": "≥", "LT": "<", "LE": "≤",
                    "LTE": "≤", "IN": "salah satu dari", "NOT_IN": "bukan salah satu dari", "BETWEEN": "antara",
                    "IS_NULL": "kosong", "IS_NOT_NULL": "terisi"}


def filter_text(item: object) -> str:
    """One filter in words: the column made readable, the operator as a sign or words, the value(s)."""
    if not isinstance(item, dict):
        return str(item)
    value = item.get("values", item.get("value"))
    shown = ", ".join(map(str, value)) if isinstance(value, list) else ("" if value is None else str(value))
    operator = str(item.get("operator") or item.get("op") or "")
    return " ".join(part for part in (words(item.get("column")),
                                      FILTER_OPERATORS.get(operator.upper(), words(operator)), shown) if part)


def export_definition(definition: dict | None) -> dict:
    """An output's definition with the reader's field names; a field not named here is made readable."""
    out = {}
    for key, value in (definition or {}).items():
        if _empty(value):
            continue
        if key == "period" and isinstance(value, dict):
            value = EXPORT_PERIOD.format(start=value.get("start") or "-", end=value.get("end") or "-")
        if key == "filters" and isinstance(value, list):
            value = "; ".join(filter_text(item) for item in value)
        out[EXPORT_DEFINITION.get(key) or words(key).capitalize()] = value
    return out


def export_lineage(lineage: dict | None) -> dict:
    """Where the file's rows came from, in words; the audit ids in one line for the technical team."""
    out, audit = {}, []
    for key, value in (lineage or {}).items():
        if _empty(value):
            continue
        if key in EXPORT_LINEAGE:
            out[EXPORT_LINEAGE[key]] = ", ".join(map(str, value)) if isinstance(value, list) else value
        else:
            audit.append(f"{key}={value}")
    if audit:
        out[EXPORT_AUDIT] = "; ".join(audit)
    return out


def export_columns(names: list, labels: dict | None, meanings: dict | None) -> list[dict]:
    """The column sheet: the title the reader sees (the model's, else the name made readable), the name in the data,
    the meaning and unit the catalog gives a column of the source tables (none for a column the analysis made)."""
    rows = []
    for name in names:
        found = (meanings or {}).get(name) or {}
        rows.append({"label": (labels or {}).get(name) or words(name).capitalize(), "name": name,
                     "meaning": (found.get("meaning") or "")[:300] or None, "unit": found.get("unit")})
    return rows


# ---- the stop button (EXEC-Y Fase 1, S2): what a stopped answer had already done ----
STOPPED_DONE = "Sebelum dihentikan: {tables} data sudah dibaca dan {outputs} tabel hasil sudah selesai. Catatan itu ikut ke pesan berikutnya di percakapan ini."
STOPPED_NOTHING_DONE = "Sebelum dihentikan belum ada data yang selesai dibaca."


def stopped_done_line(tables: int, outputs: int) -> str:
    return STOPPED_DONE.format(tables=tables, outputs=outputs) if tables or outputs else STOPPED_NOTHING_DONE


# ---- EXPLORE and follow-ups (EXEC-Y Fase 2) ----
NEWS_TITLE = "Riwayat dan konteks berita"
NEWS_NOTE = "Diringkas dari {count} berita; sumbernya ada di tab Sources."
FORWARD_TITLE = "Peristiwa ke depan"
NEWS_DATE_UNKNOWN = "Tanggal belum diumumkan"
DATA_TEST_LABEL = "Uji dengan data: {hypothesis}"


# EXEC-FASTLANE B3: the system's statistical evidence line under a fast-lane answer (the model writes none of it)
EXPLORE_EVIDENCE_LINE = ("Bukti statistik (eksploratif, dihitung sistem, tanpa Research Governor): {count} uji dicoba, "
                         "{held} bertahan sesudah koreksi uji ganda (Benjamini-Hochberg, alfa 5%).")
EXPLORE_NONE_HELD = (" Belum ada pola yang cukup kuat untuk disebut temuan; baca angka sebagai gambaran data historis, "
                     "bukan sebab-akibat atau sinyal transaksi.")
EXPLORE_HELD_NOTE = " Pola yang bertahan tetap pola historis, bukan sebab-akibat atau sinyal transaksi."
EXPLORE_UNSTABLE = " {unstable} uji arahnya tidak konsisten di dua paruh periode."
EXPLORE_SMALL = " {small} uji sampel efektifnya kecil atau kurang kuat untuk efek sekecil itu."


# EXEC-IMPL-1017 Fase 3: a recomputation of an attached figure that did not come out the same
NOT_REPRODUCED_LINE = ("Hitungan ulang angka yang dilampirkan belum sama persis dengan angka aslinya; selisihnya "
                       "dijelaskan di jawaban.")
# EXEC-IMPL-1017 (M171): an insight answer still shows a statistic no recorded test produced
UNRECORDED_TEST_LINE = ("Sebagian angka uji di jawaban ini tidak dihitung oleh pencatat uji sistem, sehingga tidak ikut "
                        "dikoreksi bersama uji lainnya; baca angka itu sebagai gambaran saja.")


def explore_evidence_line(count: int, held: int, unstable: int, small: int) -> str:
    line = EXPLORE_EVIDENCE_LINE.format(count=count, held=held)
    line += EXPLORE_HELD_NOTE if held else EXPLORE_NONE_HELD
    if unstable:
        line += EXPLORE_UNSTABLE.format(unstable=unstable)
    if small:
        line += EXPLORE_SMALL.format(small=small)
    return line


# Mode Jawab v2: the line under a fast-lane answer-mode analysis whose tests (if any) the model computed with its code
FASTLANE_ANSWER_LINE = ("Uji statistik (bila ada) dihitung AI dengan kode dan tidak diperiksa ulang sistem; ini pola "
                        "historis, bukan sebab-akibat, prediksi, atau sinyal transaksi.")

# EXEC-FASTLANE F2 (AI_FASTLANE_CONVENTION_NUMBERS): the numbers of a fast-lane answer that passed without a table
# source, written by the system as an assumption
CONVENTION_NUMBER_KINDS = {"CONFIDENCE_LEVEL": "tingkat kepercayaan standar", "DERIVED": "hitungan dari hasil",
                           "CODE_PARAMETER": "parameter yang ditulis di kode analisis"}


def convention_numbers_line(accepted: list[tuple[str, str]]) -> str:
    items = "; ".join(f"{number} ({CONVENTION_NUMBER_KINDS.get(kind, kind)})" for number, kind in accepted[:10])
    return f"Angka berikut tidak berasal dari tabel hasil: {items}."


# E9(b) and E9(c) (EXEC-1018B Fase 4, user 2026-10-16 "4. Otomatis"): the turn moved to an analysis step, and an
# offer the user accepted
HANDOFF_LINE = "Permintaan ini butuh hitungan baru ({reason}), jadi langsung dikerjakan sebagai analisis lanjutan."
OFFER_RUN_LINE = "Menjalankan tawaran sebelumnya: {label}."


# M192 (4) (user 2026-10-19 "Ok untuk M192 masukan exec"): the note under an answer whose "same as before" claim the
# backend could not confirm, in plain words without JSON (it showed `bank_returns_4 uses {"entities": ...}`)
DEFINITION_NOTE = "Catatan sistem: jawaban menyebut hasil ini sama dengan hasil sebelumnya, {why}."
DEFINITION_NOT_OPENED = ("tetapi hasil sebelumnya tidak dibuka dalam analisis ini, jadi kesamaannya belum bisa "
                         "diperiksa")
DEFINITION_NO_RECORD = "tetapi hasil sebelumnya tidak menyimpan cara hitungnya, jadi kesamaannya belum bisa diperiksa"
DEFINITION_DIFFERENT = "padahal {fields} berbeda: hasil ini {mine}; hasil sebelumnya {earlier}"
DEFINITION_FIELDS = {"filters": "filter", "period": "periode", "entities": "daftar saham", "thresholds": "ambang"}
DEFINITION_NONE = {"filters": "tanpa filter", "period": "tanpa periode tertulis", "entities": "tanpa daftar saham",
                   "thresholds": "tanpa ambang"}
MAX_NAMED_STOCKS = 6


def _definition_part(field: str, value: object) -> str:
    if _empty(value):
        return DEFINITION_NONE[field]
    if field == "filters" and isinstance(value, list):
        return "filter " + "; ".join(filter_text(item) for item in value)
    if field == "period" and isinstance(value, dict):
        return "periode " + EXPORT_PERIOD.format(start=value.get("start") or value.get("from") or "-",
                                                 end=value.get("end") or value.get("to") or "-")
    if field == "entities" and isinstance(value, list):
        shown = ", ".join(map(str, value[:MAX_NAMED_STOCKS])) + (", …" if len(value) > MAX_NAMED_STOCKS else "")
        return f"{len(value)} saham ({shown})"
    if isinstance(value, dict):
        return f"{DEFINITION_FIELDS[field]} " + "; ".join(f"{words(k)} {v}" for k, v in value.items())
    return f"{DEFINITION_FIELDS[field]} {value}"


def definition_note(finding: dict) -> str:
    """One finding of definition_check.findings as the plain note under the answer."""
    if finding.get("kind") == "NOT_OPENED":
        return DEFINITION_NOTE.format(why=DEFINITION_NOT_OPENED)
    if finding.get("kind") != "DIFFERENT":
        return DEFINITION_NOTE.format(why=DEFINITION_NO_RECORD)
    fields = [f for f in finding.get("fields") or [] if f in DEFINITION_FIELDS]
    mine, earlier = finding.get("mine") or {}, finding.get("earlier") or {}
    return DEFINITION_NOTE.format(why=DEFINITION_DIFFERENT.format(
        fields=" dan ".join(DEFINITION_FIELDS[f] for f in fields),
        mine=", ".join(_definition_part(f, mine.get(f)) for f in fields),
        earlier=", ".join(_definition_part(f, earlier.get(f)) for f in fields)))


# the statistics decision (user 2026-10-20, AI_FASTLANE_GOAL_ANSWERS): an insight answer may show a test the AI
# computed with its own code; the reader is told it was not checked again
OWN_TEST_LINE = ("Sebagian uji statistik di jawaban ini dihitung AI dengan kodenya sendiri dan tidak diperiksa ulang "
                 "sistem; minta verifikasi bila perlu kepastian lebih.")


# the table download (user 2026-10-20 "Ok, opsi A"): an input sheet whose data the sandbox no longer kept was extracted
# again with the same approved data need; the file's definition sheet says so (the file follows the answer's language)
INPUTS_REBUILT_FIELD = "Data input"
INPUTS_REBUILT = "ditarik ulang dari sumber pada {date} dengan permintaan data yang sama (data asli sudah tidak disimpan)"
