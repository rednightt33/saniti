/* Every word the answer view shows (EXEC-X, user decision 2026-10-08). Change wording here; no view code changes.
   EXEC-UI-1019B (user 2026-10-19: "semua label tetap bahasa Inggris"): every label of the interface is English; the
   user's messages and the AI's answer (with the lines the system writes inside it) keep their own language. The three
   *Message texts below are sent as the user's own message, so they stay in the user's language.
   fields: a data field's name as a label. A field missing here still shows, its name made readable.
   values: a backend code as words. A code missing here shows as written.
   verdicts: a backend verdict or status as [words, tone]; tone is positive, warning, negative or neutral.
   status: the answer's state as [words, tone]. ui: fixed texts of the answer view.
   record: the parts of the conversation's data record shown in Sources, by name; a part not named here stays in
   "Technical details" only (P4, 2026-10-08). */
window.EdgeLabels = {
  servicesWaiting: "Waiting for services to be ready.",
  fields: {
    objective:"Objective", universe:"Universe", time_scope:"Period", analysis_frequency:"Frequency", original_question:"Question",
    root_hypothesis:"Main hypothesis", hypothesis:"Hypothesis", angle_question:"Angle question", condition:"Condition",
    outcome:"Outcome measured", baseline:"Baseline", baseline_or_comparator:"Baseline", expected_direction:"Expected direction",
    outcome_horizon_periods:"Horizon", outcome_unit:"Outcome unit", success_definition:"Success definition",
    success_rule:"Success threshold", min_effect:"Minimum effect", min_effect_unit:"Minimum effect unit",
    candidate_count:"Candidates", pairwise_comparisons:"Pairwise comparisons",
    multiple_testing_policy:"Multiple-testing correction", holdout_required:"Holdout data",
    minimum_sample_value:"Minimum sample", minimum_sample_unit:"Minimum sample unit", method_id:"Method",
    method_family:"Method family", parameters:"Parameters", why_distinct:"Why it is distinct", carried_inputs:"Tables used",
    output_ref:"Table", purpose:"Purpose", assumptions:"Assumptions", limitations:"Limitations", confirmation_question:"Confirmation question",
    experiment_id:"Experiment ID", hypothesis_id:"Hypothesis ID", angle_id:"Angle ID", root_hypothesis_id:"Main hypothesis ID",
    plan_version:"Plan version", title:"Title", answer:"Answer", evidence:"Evidence", usefulness:"Usefulness", follow_up:"Next step",
    verdict:"Verdict", status:"Status", status_reason:"Status reason", validation_level:"Validation level",
    evidence_direction:"Evidence direction", effective_sample:"Effective sample", sample_unit:"Sample unit", estimate_kind:"Estimate type",
    estimate:"Estimate", ci:"Confidence interval", p_value:"p", p_adjusted:"Adjusted p", confidence_level:"Confidence level",
    estimate_unit:"Estimate unit", claim:"Claim", source:"Source", ref:"Ref", output_id:"Output ID", name:"Name", label:"Label",
    data_as_of:"Data as of", kind:"Type", quote:"Quote", note:"Note", url:"Link", ticker:"Ticker",
    tables:"Tables", columns:"Columns", outputs:"Outputs", data_needs:"Data needs", answers:"Answers", readings:"Readings", pause:"Pause",
    operator:"Operator", value:"Value", unit:"Unit", reason:"Reason", options:"Options", cause:"Cause",
    source_url:"Link", source_title:"Page title", source_date:"Source date", source_official:"Official source",
    source_quote:"Original quote", source_publisher:"Site", source_name:"Result table", source_data_as_of:"Data as of"
  },
  record: {outputs:"Result tables", tables:"Data read", findings:"Research findings"},
  values: {
    HIGHER:"Higher", LOWER:"Lower", DIFFERENT:"Different", PERCENT:"percent", DECIMAL:"decimal", BASIS_POINT:"basis points",
    OTHER:"other", EVENTS:"events", OBSERVATIONS:"observations", ENTITIES:"entities", DATES:"dates", NONE:"None",
    DATES_AUTOCORRELATION_ADJUSTED:"dates (adjusted for autocorrelation)", MEAN_DIFFERENCE:"mean difference",
    BONFERRONI:"Bonferroni", HOLM:"Holm", BENJAMINI_HOCHBERG:"Benjamini–Hochberg"
  },
  verdicts: {
    SUPPORTED:["Supported","positive"], PARTIALLY_SUPPORTED:["Partly supported","warning"], NOT_SUPPORTED:["Not supported","negative"],
    INCONCLUSIVE:["Inconclusive","neutral"], NOT_EVALUATED:["Not evaluated","neutral"],
    INSUFFICIENT_EVIDENCE:["Insufficient evidence","neutral"], INVALID:["Invalid","negative"], NOT_RUN:["Not run","neutral"],
    DIRUJUK:["Referenced","positive"], TERCEK:["Checked","positive"], TIDAK_COCOK:["Does not match","negative"]
  },
  evidence: {
    FACT:"Fact", DATABASE_AGGREGATE:"Database aggregate", CALCULATION_VERIFIED:"Calculation verified",
    SCOPE_VERIFIED:"Scope verified", DATA_COVERAGE_VERIFIED:"Data coverage verified",
    UNVERIFIED_EXPLORATORY:"Exploratory, not verified", NOT_VALIDATED:"Not validated"
  },
  status: {
    // EXEC-UI-1015D (user 2026-10-15, "selesai ganti Completed"): the answer header in English
    COMPLETED:["Completed","positive"], AWAITING_CONFIRMATION:["Awaiting approval","warning"], NEEDS_CLARIFICATION:["Needs your answer","warning"],
    LIMITED:["Limited","neutral"], PAUSED:["Paused","warning"], FAILED:["Failed","negative"]
  },
  units: {PERCENT:"%", BASIS_POINT:" bp", DECIMAL:""},
  operators: {">=":"≥", "<=":"≤", ">":">", "<":"<"},
  ui: {
    composerResize:"Resize message box", composerResizeHint:"Drag up or down to resize. Arrow keys also work.",
    yes:"Yes", no:"No", items:"items", periods:"periods", notStated:"Not stated",
    successDefault:"success = a result above zero", minEffectDefault:"the backend uses its default",
    plan:"Research plan", planPending:"Awaiting approval", experiment:"Experiment", angle:"Angle",
    designMore:"Design details", planMore:"Plan details", planAssumptions:"Plan assumptions", planLimitations:"Plan limitations",
    approve:"Approve & run", revise:"Revise", cancel:"Cancel",
    stop:"Stop", stopping:"Stopping…", stopNotYet:"Nothing to stop yet; try again in a moment.", stopped:"Stopped by you.",
    followUps:"Follow-up questions", insightIdeas:"Insight ideas", dataTest:"Further research",
    stopAndSend:"Stop & send", stoppingHint:"Stopping — waiting for the current step to finish", editResend:"Edit & resend",
    stoppedHint:"What was done so far stays in this conversation.",
    findings:"Research findings", finding:"Finding", backendMore:"Backend details",
    assumptions:"Assumptions", limitations:"Limitations", methodology:"Methodology", technical:"Technical details",
    evidencePrefix:"Evidence: ", choices:"Choices", choicesDisabled:"Choices are only for the latest answer when nothing is running",
    paused:"This answer is paused", pausedRegion:"Answer paused", pauseHint:"Or write another instruction in the message box.",
    needsInput:"Write what you want to change in the message box", claimNote:"note",
    sourcesEvidence:"Evidence", sourcesNews:"News", sourcesClaims:"Flagged claims", sourcesHurdles:"Process hurdles", sourcesRecord:"Conversation data record",
    sourcesEmpty:"No source or evidence metadata returned for this response.",
    // EXEC-ASK-BRANCH (user 2026-10-24): continue an answer in a new tab, or ask about it in a side chat
    branch:"Branch", branchTitle:"Branch · {title}", branchHint:"Continue from this answer in a new conversation (new tab)",
    branchedFrom:"Branched from “{title}”", sideFrom:"Asking about the answer to “{title}”", sideEmpty:"Ask anything about this answer. It is not repeated here; the AI reads it.",
    askAbout:"Ask about this answer", askTitle:"Ask · {title}", askHint:"Ask about this answer in a side chat",
    sideChat:"Side chat ({n})", sideClose:"Close side chat", selectionAsk:"Ask in side chat",
    // EXEC-IMPL-1016 Fase 4.1 (EDGE-CTX B): the tables this answer released, as the data behind it; the old evidence list
    // stays below, folded, as the references of its figures
    sourcesTables:"Result tables", sourcesNumbers:"Figure references", sourceContent:"Content", sourceRows:"Rows", sourceColumns:"Columns",
    // EXEC-IMPL-1016 Fase 4.3 (UI-1015B): what a running answer is doing, from Orc's steps; EXEC-M181: how long it took
    progressDone:"Steps done ({n})", progressEarlier:"{n} earlier steps",
    progressRefused:"refused, trying again", progressFailed:"failed",
    // EXEC-IMPL-1016 Fase 4.2 (EDGE-CTX A): part of an answer table attached to the next question
    attachTable:"Attach to question", attachRows:"Attach {n} rows", attachedChip:"{title} · {n} rows",
    attachRemove:"Remove attachment", attachHint:"Click rows to select them",
    // EXEC-IMPL-1017 Fase 3: the menu on selected text (right click; on a phone a floating bar) and its chip
    selectionCopy:"Copy", selectionAttach:"Attach selection as context", attachedText:"“{quote}” · {n} figures",
    attachLimit:"At most 5 attachments per question", attachComment:"Add a note about this part (optional)", attachFigures:"{n} figures", attachedPrefix:"Attachment",
    reproduced:"Recomputed from raw data: exactly equal to {figure}",
    sourceAsOf:"Data as of", askExport:"Ask AI to export data", exportMessage:"Ekspor data tabel {ref} ({name}) ke Excel",
    approveMessage:"Setujui rencana riset", cancelMessage:"Batalkan rencana riset",
    // EXEC-MODELS: the model and reasoning-level choice next to the composer
    // EXEC-UI-1015D (user 2026-10-15): the model picker in English; every EDGE message runs the fast lane (no lane choice)
    modelTitle:"Choose model and reasoning", modelHead:"AI model", modelPricesNote:"Price per 1M tokens",
    modelInput:"Input", modelOutput:"Output", modelLevel:"Reasoning", lane:"Lane", lanes:{standard:"Standard", fast:"Fast"}, answerKicker:"EDGE", modelUpdated:"Prices updated",
    modelLevels:{low:"Low", medium:"Medium", high:"High", max:"Max", off:"Off", on:"On"},
    // EXEC-CHOICES: the "Response choices" panel
    nextAction:"Your next step", choicesTitle:"Response choices", planChoicesTitle:"Plan approval",
    choiceDraft:"Fill in the message box first", choiceWrite:"Write",
    tableExpand:"Enlarge table", tableTitle:"Table", tableRows:"{n} rows", tableMoreRows:"Show {n} more rows", tableFewerRows:"Hide rows", historyJump:"Go to message", railDetails:"Show Details", railHideDetails:"Hide Details", railBookmark:"Bookmark", railShare:"Public sharing unavailable", accountSettings:"Settings",
    choiceChosen:"Chosen · reply sent", choiceChosenDraft:"Chosen · write in the message box",
    writeOther:"Write another answer", writeOtherHint:"Write your answer in the message box", exploreNote:"Includes news research",
    // EXEC-SHARE-UI (user 2026-10-19): the share button of an answer and its card
    share:"Share", sharePdf:"PDF (document)", sharePng:"PNG (image)", sharePreparing:"Preparing image…",
    shareFailed:"The image could not be made; try PDF", shareQuestion:"Question", shareDataAsOf:"Data as of {date}",
    shareRequest:"Request {id}", shareFooter:"Not investment advice", shareWord:"Word (document)",
    shareWordPreparing:"Preparing document…", shareWordFailed:"The document could not be made; try PDF",
    // EXEC-UI-1019B: the copy button says what it does; the scroll marker and table sorting in English
    copy:"Copy", copied:"Copied", markerQuestion:"Question", markerAnswer:"AI answer",
    markerLabel:"Position in the conversation; hold and drag to scroll",
    sortAscending:"sort ascending", sortDescending:"sort descending", sortRestore:"restore the original order",
    // the table download (user 2026-10-20): every row of the table as Excel, prepared by the backend
    tableDownload:"Download table (Excel)", tableDownloadPreparing:"Preparing file…",
    tableDownloadFailed:"The file could not be prepared", tableDownloadBusy:"This table's file is already being prepared",
    // EXEC-M181 (user 2026-10-20 "Otomatis 1x, lalu tawarkan"): a run whose AI provider stopped sending output
    providerStalled:"AI provider timed out",
    providerStalledHint:"The AI provider sent no output for a while, even after one retry. What was done so far stays in this conversation.",
    runawayStalled:"The AI kept thinking without answering",
    runawayStalledHint:"The AI used its whole output budget on thinking, even after one retry. What was done so far stays in this conversation.",
    retry:"Retry", changeModel:"Change model"
  },
  // EXEC-TERMINAL-API T3: the Terminal tab next to Monitor
  terminal: { nav:"Terminal", frameTitle:"Financial terminal" },
  // EDGE backtest (CONTRACT.md section 10): the Backtest tab next to Terminal
  backtest: { nav:"Backtest", frameTitle:"Backtest" }
};
