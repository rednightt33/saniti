"""Every line the backend writes for the user (M125, user decision 2026-10-08: "bahasa sangat baku ... too much technical
terms exposed"). Plain, everyday Indonesian; no table or column names, no internal ids (analysis, session, experiment,
output) and no backend codes. A code reaches the user only through words(): its plain words, or, for a code not listed
yet, the code made readable. Instructions to the model stay in English in the orchestrator; they are not here.

tests/test_user_texts.py reads every text here (and the lines the orchestrator builds from them) and fails on an
internal name, a code or an English sentence.
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
}


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
                "metric": "data pasar", "reference": "tabel referensi", "web": "fakta web"}
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
}


def _empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def export_definition(definition: dict | None) -> dict:
    """An output's definition with the reader's field names; a field not named here is made readable."""
    out = {}
    for key, value in (definition or {}).items():
        if _empty(value):
            continue
        if key == "period" and isinstance(value, dict):
            value = EXPORT_PERIOD.format(start=value.get("start") or "-", end=value.get("end") or "-")
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
