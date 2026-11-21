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
  // EXEC-MU-ACCOUNTS Phase 0 (M471): a session refusal that keeps the session, by its code, when the server sends no
  // message of its own (the server's message is shown first)
  access: {
    CAPABILITY_REQUIRED:"This feature is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.",
    PLAN_EXPIRED:"Your EDGE plan has ended. Renew it to use this again; you are still signed in.",
    MFA_REQUIRED:"This needs your sign-in code. Enter the code from your authenticator app, then try again.",
    LIMIT_REACHED:"You have reached your plan's limit. Try again later, or upgrade the plan.",
    SIGN_IN_RATE_LIMIT:"Too many sign-in attempts from here. Wait a few minutes, then try again.",
    // Phase 2 (contract 8a, locked wording, EXEC-UI-1019B): a locked item, an item not released yet, the upgrade prompt,
    // a plan that has ended, and a capability refusal shown as a toast. No page shows them before Phase 3.
    paidPlan:"Available on a paid plan",
    comingSoon:"Coming soon",
    contactUpgrade:"Contact us to upgrade",
    planEnded:"Your plan has ended",
    refusedToast:"This is not part of your plan."
  },
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
    // MONITOR-REVAMP (user 2026-10-29, AI_revamp.html): the suggestions as one list, each with its kind; the note of a choice
    // sent at once; the short label of the side-chat button under an answer
    suggestedNext:"Suggested next questions", followUpKind:"Follow-up", insightIdeaKind:"Insight idea", dataTestKind:"Further research",
    choiceSends:"Sends right away", reviseHint:"Write what to change", askAboutShort:"Ask about this",
    send:"Send", sendHint:"\u21B5 to send", runningHint:"Running\u2026 press to stop",
    running:"Running", runNote:"You can keep typing; \u201cStop & send\u201d sends your next message right away.",
    shareTitle:"Share this answer", branchedNote:" \u2014 continues from that answer without recomputing.",
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
    tableExpand:"Enlarge table", tableTitle:"Table", tableRows:"{n} rows", tableMoreRows:"Show {n} more rows", tableFewerRows:"Hide rows", historyJump:"Go to message", railDetails:"Show Details", railHideDetails:"Hide Details", railBookmark:"Bookmark", railShare:"Share latest answer", accountSettings:"Settings",
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
  backtest: { nav:"Backtest", frameTitle:"Backtest" },
  // EXEC-SCREENER (report FRONTEND INTEGRATION 9.7): the Screener tab next to Backtest
  screener: { nav:"Screener", frameTitle:"Stock screener" },
  // EXEC-RADAR R7 (user 2026-11-14: "A1 S8 ikut, dan halaman tetap bernama Radar"): the Radar tab after Screener
  radar: { nav:"Radar", frameTitle:"Radar" },
  // EXEC-OVERVIEW O4 (decision 7, 2026-11-15): the Overview tab, first in the rail
  overview: { nav:"Overview", frameTitle:"Market overview" },
  // EXEC-WATCHLIST L5 (user go 2026-11-16): the Watchlist tab, after Overview in the rail
  watchlist: { nav:"Watchlist", frameTitle:"Watchlist" },
  // EXEC-OVERVIEW QA (user 2026-11-15: "1B"): on a phone (the left menu is hidden at 720 px or less) a menu button in the
  // EDGE bar lists the same pages
  shell: { pagesMenu:"Pages", openPages:"Open the pages menu", closePages:"Close the pages menu" },
  // EXEC-TERMINAL-IND-EDIT (user 2026-11-05: "apapun tabnya selalu tulisannya Edge, Sign In, and Monitor. Boleh diganti
  // misalkan Edge, - terminal, backtest, screener"): the browser tab's title on each page
  pages: { loading:"EDGE", signIn:"EDGE — Sign In", monitor:"EDGE — Monitor", terminal:"EDGE — Terminal",
    backtest:"EDGE — Backtest", screener:"EDGE — Screener", radar:"EDGE — Radar",
    overview:"EDGE — Overview", watchlist:"EDGE — Watchlist",
    register:"EDGE — Create Account", verify:"EDGE — Enter Code", forgot:"EDGE — Forgot Password",
    reset:"EDGE — New Password", mfa:"EDGE — Authenticator" },
  // track guest (decision 1 of 2026-11-19, the user: "ketika dia klik ticker selain bbca maka akan keluar pop up box to
  // login (jika belum login) dan jika sudah login maka akan keluar pop up box (to upgrade plan)"): the box the Terminal
  // opens for a ticker, an indicator or a feature the principal does not hold ({name}: the item). Without an account:
  // sign in or create one; with one: the upgrade box, "segera hadir" (access.comingSoon) and the contact of
  // EDGE_UPGRADE_CONTACT, or, while it is not set, that it comes soon. `mark`: the lock beside a locked row
  locked: {
    mark:"Locked",
    guestTitle:"Sign in to open {name}",
    guestLead:"Without an account EDGE shows part of the Terminal. Sign in to see more, or create an account.",
    guestLeadClosed:"Without an account EDGE shows part of the Terminal. Sign in to see more; registration opens soon.",
    signIn:"Sign in", register:"Create account",
    upgradeTitle:"{name} is not in your plan",
    upgradeLead:"Your EDGE plan does not include this yet. Upgrading is coming soon.",
    contact:"Contact us to upgrade:", contactSoon:"How to contact us about upgrading will be shown here soon.",
    close:"Close",
    features:{ "terminal.layouts":"Saved chart layouts", "terminal.presets":"Indicator presets",
      // 3e: the Terminal's locked data (its lockedPage)
      "terminal.dataset:broker":"Broker data", "terminal.dataset:events":"Corporate actions",
      "terminal.dataset:intraday":"Intraday charts" },
    // 3e: a tab the principal cannot open (LockedTabPage)
    tabGuestLead:"{name} needs an EDGE account. Sign in to open it, or create an account.",
    tabGuestLeadClosed:"{name} needs an EDGE account. Sign in to open it; registration opens soon.",
    tabUpgradeLead:"Your EDGE plan does not include {name} yet. Upgrading is coming soon.",
    // an account whose plan ended (access.expired_plan): renewing opens the tab again
    tabEndedTitle:"Your plan has ended", tabEndedLead:"Your {plan} plan has ended, so {name} is closed for now. Renew the plan to open it again; your data is kept.",
    contactRenew:"Contact us to renew:",
    openTerminal:"Open the Terminal"
  },
  // EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (ERRORS M527; static/edge-app.js
  // ExampleTabPage): a tab the principal cannot open shows its example, a view of one day ({name}: the tab, {date}: the
  // day of its data); a click on it opens the lock box with these leads (sign in for a visitor, the paywall for an account)
  example: {
    badge:"Example", loading:"Opening the {name} example…", frameTitle:"{name} example",
    banner:"{name} with the data of {date}, as a view of that day.", bannerNoDate:"{name}, as a view of one day.",
    guest:"Sign in to use {name} itself.", guestClosed:"Sign in to use {name} itself; registration opens soon.",
    account:"Your plan does not include {name} itself yet; upgrading is coming soon.",
    dialogGuestLead:"This is an example of {name}: a view of one day. Sign in to use {name} itself, or create an account.",
    dialogGuestLeadClosed:"This is an example of {name}: a view of one day. Sign in to use {name} itself; registration opens soon.",
    dialogUpgradeLead:"This is an example of {name}: a view of one day. Your EDGE plan does not include {name} itself yet. Upgrading is coming soon."
  },
  // EXEC-MU-ACCOUNTS Phase 1 (contract section 4; user: English labels): the account pages. A refusal shows the
  // server's own message (error.message); `errors` is the fallback by code when the server sends none.
  auth: {
    login: { title:"Welcome to Edge", lead:"Sign in to your private workspace.", login:"Login", loginHint:"Username or email",
      password:"Password", submit:"Sign In", busy:"Signing in…", create:"Create account", noAccount:"No account yet?",
      forgot:"Forgot password?", resetDone:"Your password was changed. Sign in with the new password.",
      justRegistered:"If you have just registered, check your email for a code and enter it on the", verifyLink:"Verify page",
      // track guest: where visitors open the Terminal without an account (shown when the site has guests)
      guest:"Open the Terminal without an account", signInTop:"Sign in" },
    // track guest (the pre-launch mode, the user 2026-11-19: "Terbuka, tapi belum bisa mendaftar"): the register page
    // while registration is closed
    closed: { title:"Registration opens soon", lead:"EDGE is not taking new accounts yet. You can open the Terminal without an account.",
      terminal:"Open the Terminal", back:"Back to sign in" },
    register: { title:"Create your account", lead:"Use your email to create an EDGE account.", username:"Username",
      usernameHint:"3 to 30 lowercase letters, digits or _", firstName:"First name", lastName:"Last name", email:"Email",
      phone:"Phone", phoneHint:"For example 0812 3456 7890 or +62 812 3456 7890", password:"Password",
      passwordHint:"At least 8 characters", repeat:"Repeat password", submit:"Create account", busy:"Creating…",
      haveAccount:"Already have an account?", signIn:"Sign in" },
    verify: { title:"Check your email", sent:"We sent a code to your email.", sameBrowser:"Enter the code in the same browser where you registered.", sentTo:"We sent a code to", code:"Code",
      codeHint:"6 digits", email:"Email", submit:"Verify", busy:"Verifying…", expiresIn:"The code expires in",
      expired:"The code has expired. Send a new one.", resend:"Send a new code", resendIn:"You can send a new code in",
      resent:"A new code is on its way.", back:"Back to sign in", username:"New username",
      usernameTaken:"That username was taken while you were away. Choose another one and verify again." },
    forgot: { title:"Forgot your password?", lead:"Enter the email of your account. We will send you a code.",
      email:"Email", submit:"Send code", busy:"Sending…", back:"Back to sign in" },
    // the A2 fix (ERRORS M517): a reset code works only in the browser that asked for it, and each place gets a few codes
    // a day for an address (one sentence for every address, so it tells nothing about one)
    reset: { title:"Set a new password", sentTo:"We sent a code to", code:"Code", password:"New password",
      passwordHint:"At least 8 characters", repeat:"Repeat new password", submit:"Change password", busy:"Changing…",
      back:"Back to sign in", sameBrowser:"Enter the code in this browser, where you asked for it.",
      noMail:"No email after a few minutes? Today's codes from this place may be used up: try again tomorrow, or ask in a browser where you have signed in to EDGE before." },
    mfa: { title:"Authenticator code", lead:"Enter the 6-digit code from your authenticator app.", code:"Code",
      codeHint:"6 digits", useRecovery:"Use a recovery code instead", useCode:"Use the authenticator code",
      recovery:"Recovery code", submit:"Continue", busy:"Checking…", setup:"Set up an authenticator app",
      enrolTitle:"Set up your authenticator", enrolLead:"Scan this QR code with your authenticator app, then enter the 6-digit code it shows.",
      secret:"Or enter this key by hand", codesTitle:"Recovery codes",
      codesLead:"Each code signs you in once if you lose your phone. They are shown only now: save them somewhere safe.",
      saved:"I have saved my recovery codes", lockedCode:"Too many wrong authenticator codes. Enter one of your recovery codes instead.",
      lockedAll:"Ask an admin to unlock your account.",
      lockedRecovery:"Too many wrong recovery codes, so recovery codes are locked for now. Sign in with the code from your authenticator app.",
      unlockAt:"It unlocks on", busySetup:"Preparing…", qrFailed:"The QR code could not be drawn here: enter the key by hand." },
    check: { short:"The password needs at least 8 characters.", long:"The password can have at most 256 characters.",
      mismatch:"The two passwords are not the same.", code:"Enter the 6 digits of the code." },
    // re-check R2-20: the account menu's page for the Phase 1 password change and sign-out on every device (the
    // sessions table is shared by the beta and the live website, so "every device" covers both)
    // the footer's links, shown only once their texts exist (EXEC option A, 2026-11-20)
    legal: { privacy:"Privacy", terms:"Terms" },
    account: { menu:"Password and sign-in", title:"Password and sign-in",
      lead:"Change your password, or sign out of EDGE on every device.",
      current:"Current password", password:"New password", passwordHint:"At least 8 characters.", repeat:"Repeat new password",
      submit:"Change password", busy:"Changing…",
      changed:"Your password was changed. EDGE signed out your other devices; this one stays signed in.",
      allTitle:"Sign out everywhere",
      allLead:"Ends every EDGE session of this account, on every device and on both EDGE websites, this one included.",
      all:"Sign out everywhere", allBusy:"Signing out…",
      mfaTitle:"Authenticator app",
      mfaLead:"A new phone or a new app: set up a new authenticator. Your current one stops working once the new one is confirmed.",
      mfaNew:"Set up a new authenticator" },
    errors: { INVALID_CREDENTIALS:"The login or the password is not right.", CODE_INVALID_OR_EXPIRED:"That code is not valid or has expired. Send a new one.",
      USERNAME_TAKEN:"That username is taken. Choose another one.",
      USER_CHANGED:"Another EDGE account signed in on this browser. Reload the page to continue as that account.",
      SIGN_IN_RATE_LIMIT:"Too many attempts. Wait a few minutes, then try again.", LIMIT_REACHED:"Too many attempts today. Try again tomorrow.",
      INVALID_INPUT:"Check the fields and try again.", MFA_INVALID:"That code is not right. Try the newest code.",
      REGISTRATION_CLOSED:"Registration opens soon. You can still open the Terminal without an account.",
      SIGN_IN_CLOSED:"EDGE opens to accounts soon. Until then only test accounts can sign in.",
      fallback:"That did not work. Try again in a minute." }
  }
};
