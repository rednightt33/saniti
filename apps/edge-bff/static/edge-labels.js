/* Every word the answer view shows (EXEC-X, user decision 2026-10-08). Change wording here; no view code changes.
   fields: a data field's name as a label. A field missing here still shows, its name made readable.
   values: a backend code as words. A code missing here shows as written.
   verdicts: a backend verdict or status as [words, tone]; tone is positive, warning, negative or neutral.
   status: the answer's state as [words, tone]. ui: fixed texts of the answer view.
   record: the parts of the conversation's data record shown in Sources, by name; a part not named here stays in
   "Detail teknis" only (P4, 2026-10-08). */
window.EdgeLabels = {
  fields: {
    objective:"Tujuan", universe:"Cakupan", time_scope:"Periode", analysis_frequency:"Frekuensi", original_question:"Pertanyaan",
    root_hypothesis:"Hipotesis utama", hypothesis:"Hipotesis", angle_question:"Pertanyaan sudut", condition:"Kondisi",
    outcome:"Yang diukur", baseline:"Pembanding", baseline_or_comparator:"Pembanding", expected_direction:"Arah yang diharapkan",
    outcome_horizon_periods:"Horizon", outcome_unit:"Satuan hasil", success_definition:"Definisi sukses",
    success_rule:"Ambang sukses", min_effect:"Efek minimum", min_effect_unit:"Satuan efek minimum",
    candidate_count:"Jumlah kandidat", pairwise_comparisons:"Perbandingan berpasangan",
    multiple_testing_policy:"Koreksi uji berganda", holdout_required:"Data uji terpisah (holdout)",
    minimum_sample_value:"Sampel minimum", minimum_sample_unit:"Satuan sampel minimum", method_id:"Metode",
    method_family:"Keluarga metode", parameters:"Parameter", why_distinct:"Mengapa berbeda", carried_inputs:"Tabel yang dipakai",
    output_ref:"Tabel", purpose:"Kegunaan", assumptions:"Asumsi", limitations:"Batasan", confirmation_question:"Pertanyaan konfirmasi",
    experiment_id:"ID eksperimen", hypothesis_id:"ID hipotesis", angle_id:"ID sudut", root_hypothesis_id:"ID hipotesis utama",
    plan_version:"Versi rencana", title:"Judul", answer:"Jawaban", evidence:"Bukti", usefulness:"Kegunaan", follow_up:"Langkah berikutnya",
    verdict:"Putusan", status:"Status", status_reason:"Alasan status", validation_level:"Tingkat validasi",
    evidence_direction:"Arah bukti", effective_sample:"Sampel efektif", sample_unit:"Satuan sampel", estimate_kind:"Jenis estimasi",
    estimate:"Estimasi", ci:"Selang kepercayaan", p_value:"p", p_adjusted:"p disesuaikan", confidence_level:"Tingkat keyakinan",
    estimate_unit:"Satuan estimasi", claim:"Klaim", source:"Sumber", ref:"Ref", output_id:"ID output", name:"Nama", label:"Label",
    data_as_of:"Data per", kind:"Jenis", quote:"Kutipan", note:"Catatan", url:"Tautan", ticker:"Ticker",
    tables:"Tabel", columns:"Kolom", outputs:"Output", data_needs:"Kebutuhan data", answers:"Jawaban", readings:"Bacaan", pause:"Jeda",
    operator:"Operator", value:"Nilai", unit:"Satuan", reason:"Alasan", options:"Pilihan", cause:"Penyebab",
    source_url:"Tautan", source_title:"Judul halaman", source_date:"Tanggal sumber", source_official:"Sumber resmi",
    source_quote:"Kutipan asli", source_name:"Tabel hasil", source_data_as_of:"Data per"
  },
  record: {outputs:"Tabel hasil", tables:"Data yang dibaca", findings:"Temuan riset"},
  values: {
    HIGHER:"Lebih tinggi", LOWER:"Lebih rendah", DIFFERENT:"Berbeda", PERCENT:"persen", DECIMAL:"desimal", BASIS_POINT:"basis poin",
    OTHER:"lainnya", EVENTS:"peristiwa", OBSERVATIONS:"observasi", ENTITIES:"entitas", DATES:"tanggal", NONE:"Tidak ada",
    DATES_AUTOCORRELATION_ADJUSTED:"tanggal (disesuaikan untuk autokorelasi)", MEAN_DIFFERENCE:"selisih rata-rata",
    BONFERRONI:"Bonferroni", HOLM:"Holm", BENJAMINI_HOCHBERG:"Benjamini–Hochberg"
  },
  verdicts: {
    SUPPORTED:["Didukung","positive"], PARTIALLY_SUPPORTED:["Didukung sebagian","warning"], NOT_SUPPORTED:["Tidak didukung","negative"],
    INCONCLUSIVE:["Belum konklusif","neutral"], NOT_EVALUATED:["Tidak dievaluasi","neutral"],
    INSUFFICIENT_EVIDENCE:["Bukti belum cukup","neutral"], INVALID:["Tidak valid","negative"], NOT_RUN:["Tidak dijalankan","neutral"],
    DIRUJUK:["Dirujuk","positive"], TERCEK:["Tercek","positive"], TIDAK_COCOK:["Tidak cocok","negative"]
  },
  evidence: {
    FACT:"Fakta", DATABASE_AGGREGATE:"Agregat database", CALCULATION_VERIFIED:"Perhitungan terverifikasi",
    SCOPE_VERIFIED:"Cakupan terverifikasi", DATA_COVERAGE_VERIFIED:"Cakupan data terverifikasi",
    UNVERIFIED_EXPLORATORY:"Eksploratif, belum terverifikasi", NOT_VALIDATED:"Belum tervalidasi"
  },
  status: {
    COMPLETED:["Selesai","positive"], AWAITING_CONFIRMATION:["Menunggu persetujuan","warning"], NEEDS_CLARIFICATION:["Perlu jawaban Anda","warning"],
    LIMITED:["Terbatas","neutral"], PAUSED:["Dijeda","warning"], FAILED:["Gagal","negative"]
  },
  units: {PERCENT:"%", BASIS_POINT:" bp", DECIMAL:""},
  operators: {">=":"≥", "<=":"≤", ">":">", "<":"<"},
  ui: {
    yes:"Ya", no:"Tidak", items:"item", periods:"periode", notStated:"Tidak disebut",
    successDefault:"sukses = hasil di atas nol", minEffectDefault:"backend memakai nilai bawaannya",
    plan:"Rencana riset", planPending:"Menunggu persetujuan", experiment:"Eksperimen", angle:"Sudut",
    designMore:"Detail desain", planMore:"Detail rencana", planAssumptions:"Asumsi rencana", planLimitations:"Batasan rencana",
    approve:"Setujui & jalankan", revise:"Revisi", cancel:"Batalkan",
    stop:"Stop", stopping:"Stopping…", stopNotYet:"Nothing to stop yet; try again in a moment.", stopped:"Stopped by you.",
    followUps:"Pertanyaan lanjutan", insightIdeas:"Ide insight", dataTest:"Riset lanjutan",
    stopAndSend:"Stop & send", stoppingHint:"Stopping — waiting for the current step to finish", editResend:"Edit & resend",
    stoppedHint:"What was done so far stays in this conversation.",
    findings:"Temuan riset", finding:"Temuan", backendMore:"Detail backend",
    assumptions:"Asumsi", limitations:"Batasan", methodology:"Metodologi", technical:"Detail teknis",
    evidencePrefix:"Bukti: ", choices:"Pilihan", choicesDisabled:"Pilihan hanya untuk jawaban terakhir saat tidak ada proses berjalan",
    paused:"Jawaban ini dijeda", pausedRegion:"Jawaban dijeda", pauseHint:"Atau tulis instruksi lain di kolom pesan.",
    needsInput:"Tulis bagian yang ingin diubah di kolom pesan", claimNote:"catatan",
    sourcesEvidence:"Bukti", sourcesClaims:"Klaim yang ditandai", sourcesRecord:"Catatan data percakapan",
    sourcesEmpty:"No source or evidence metadata returned for this response.",
    approveMessage:"Setujui rencana riset", cancelMessage:"Batalkan rencana riset"
  }
};
