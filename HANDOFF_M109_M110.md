# Handoff: M109 and M110 (troubleshooting context for a new AI session)

Written 2026-10-07 at the end of EXEC-D. Read `AGENTS.md` first (it overrides everything here), then
`ERRORS_AND_SOLUTIONS.md` rows M102–M110, `EXEC.md` EXEC-D and `GT_QA_2026-10-06.md` §10.

## Status and what the user asked

- Both defects are **OPEN**. The user has not chosen a fix yet.
- The user asked for this file so another session can troubleshoot: context, git references, an external benchmark
  first, then a proposed solution with risks and mitigation.
- **Do not change code, Railway or the database before the user approves a plan** (user preference: confirm before any
  change; record the approval with date and words in `EXEC.md`, R34).
- **External benchmark: not run yet.** The search calls were declined in the session that wrote this file (low weekly
  budget). Run it first (see "Benchmark to run first") and confirm or correct the proposals below with it.
- A third open decision from the same report is not part of this file: accept "time after refusals" at 7.5% or plan more
  work (target ≤ 5%; `EXEC.md` Verifikasi bersama).

## Git references (repository `rednightt33/saniti`)

| Ref | What |
|---|---|
| `main` = branch `claude/upbeat-dijkstra-iybq2f` = `5cdd985` | State when this file was written (no uncommitted work) |
| `c07f9b0` | EXEC-D code (P-a … P-h). Deployed as orc `63e29b62` (dev) |
| `2a0ce1a` | EXEC-D deploy record + suite `apps/orc-test-runner/suites/qa_20261007c.json` |
| `5cdd985` | Re-test `ma-qa-20261007c` records, M109/M110 entries |
| `3667c24` / orc `3d217256` | M101–M103 fixes (EXEC-P5 envelope, M102 open rule). Way back for EXEC-D |

Railway dev (IDs only, no secrets; full list in `PROJECT_CONTEXT.md`):
- project `8aef1702-030b-49cb-9df7-5ac2e0a42691`, environment `4d3e5af2-302b-4a2e-84e2-7d7476d6ff49`;
- `market-ai-orc` `41dc17ee-3bac-41ef-90ec-8b9356815c71`, live deployment `63e29b62`;
- `orc-test-runner` `09358b92-09d4-4da2-b547-bf8f621e226c` (golden tests: copy a suite to
  `apps/orc-test-runner/suite.json`, then `railway up apps/orc-test-runner --path-as-root --service … --environment …
  --detach`).
- A push to `main` that touches `apps/market-ai-orc/` redeploys orc. Docs-only pushes are SKIPPED.

Dev switches relevant here: `AI_ENABLE_ASK_BACK=true`, `AI_ENABLE_CONVERSATION_ROUTER=true`,
`AI_ENABLE_FIRST_TURN_ROUTER=true`, `AI_ENABLE_MERGED_STEPS=true`, `AI_ENABLE_TOOL_ENVELOPE=true`,
`AI_ENABLE_RUN_MEMORY=true`, `AI_MODE_SWITCH=4`, `AI_MODEL_SWITCH=1`. Never change model, provider or mode switches
without the user's approval (`AGENTS.md`, Model and provider).

## Governing principle (user decision, `AGENTS.md` Judgement principle)

- Judgement (intent, route, when to ask back, the question and its labels) belongs to the model.
- Code keeps the guarantees, among them: **each quick choice runs its route**; **a fixed question only when the model
  fails**; **at most two questions in a row**; tools locked per step.
- For every rule ask:
  1. Does it protect data, cost or figures? Then it stays.
  2. Does it guess intent or force an answer? Then it moves to the model.
  3. Is there a way out by asking back?
  4. Which test locks the rule?

---

## M109: the router's ask-back question is replaced by the fixed question

### Symptom (live, `ma-qa-20261007c` q7 turn 3, request `ma-qa-20261007c-q7_export_trade_war-3`, orc `63e29b62`)

- **What happened before:** turn 2 had already approved and run the research plan. The user then wrote "setuju,
  jalankan rencananya" (nothing was pending any more).
- **What the router returned (correct judgement):**
  ```json
  {"understood_intent": "Pengguna menyetujui dan ingin menjalankan sebuah rencana riset, tetapi rencana yang dimaksud tidak jelas karena tidak ada saran yang sedang menunggu.",
   "question": "Rencana riset mana yang harus dijalankan? Tidak ada saran yang sedang menunggu persetujuan, jadi saya perlu tahu angle mana yang Anda maksud.",
   "options": [{"label": "momentum_rank", "route": "CONTINUE"}, {"label": "dip_rebound", "route": "CONTINUE"},
               {"label": "momentum_size", "route": "CONTINUE"}, {"label": "industry_gap", "route": "CONTINUE"}],
   "referent": "UNCLEAR"}
  ```
- **What the user saw:** the fixed question "Maaf, maksud pesan ini belum terbaca dengan pasti. Mau saya kerjakan yang
  mana?" with `[{"label": "Jelaskan hasil tadi", "route": "CLARIFY"}, {"label": "Analisis lanjutan", "route":
  "CONTINUE"}]`.

### Verified root cause (code at `5cdd985`)

- `apps/market-ai-orc/app/conversation_router.py:500` `usable_options` keeps each route once. The four CONTINUE
  choices collapse into one.
- `apps/market-ai-orc/app/mode4.py:264` `ask_back_response`:
  - line 272: `question = usage.get("question") if len(options) >= 2 else None`;
  - line 274: with fewer than 2 choices the fixed choices replace them;
  - `conversation_router.question_text` (line 518) then uses `FALLBACK_QUESTION` (line 175), because the question is
    None.
- **Why routes are kept unique:** a quick choice carries only its route. The client sends back `chosen_option` (a route
  name; `app/schemas.py` around line 80 for the request, around line 713 for the response `options`). `mode4.py:411-416`
  then runs that route without a router call. Two choices with the same route would run the same thing, and the label
  (here, which angle) would be lost.
- **Principle check:** the fixed question is a guarantee only for "the model failed". Here the router did not fail; the
  code overrode a correct judgement (criterion 2), which the principle treats as a defect.

### Proposal (recommended)

1. Keep the router's question whenever the router asked back and did not fail. The fixed question stays only for
   `failed=True` (router call failed twice).
2. Choices:
   - 2 or more usable choices: as today;
   - 1 usable choice: show it plus the free-text hint;
   - 0 usable choices: no choices, only `ANSWER_HINT` (free text).
   - Do **not** pad with the fixed choices under a router question that asks something else.
3. Optional, second step, needs the user's decision because it changes the API: let a choice carry its label back
   (for example `chosen_option` + `chosen_label`, or the client sends the label as the message), so same-route choices
   can survive with their meaning ("CONTINUE: dip_rebound").

### Risks and mitigation

| Risk | Mitigation |
|---|---|
| A router question with a single choice or none confuses the user | `ANSWER_HINT` ("Balas dengan nomor pilihan, atau tulis maksud Anda.") always ends it; a free-text reply is routed again by the router |
| The two-questions limit is bypassed | Unchanged: the ask-back line still ends with `ANSWER_HINT`, so `conversation_router.questions_in_a_row` and `mode4.MAX_ASK_BACKS` still count it |
| A client that only renders choices loses the question | The question is in `response.answer` and `clarification_question`, as today |
| The documented ask-back action ("three or four quick choices") drifts | Update `ASK_BACK_ACTION` / `ASK_BACK_TURN_RULE` text if behaviour text changes, regenerate `AI_ROUTER.md` (`scripts/generate_ai_router_doc.py`), run `scripts/benchmark_turn_router.py --ask-back` before deploy (`AGENTS.md`, AI router) |

### Tests

- Find the existing ask-back tests with `grep -rn "ask_back_response\|FALLBACK_QUESTION" apps/market-ai-orc/tests`
  (`test_mode4*.py`, `test_first_message_router.py`).
- **Add** an offline replay of the router output above: four same-route choices → the router's question is kept.
- **Keep** the test "failed router call → fixed question". Cost: none, no model call.

---

## M110: the model opens every prepared session before running any code

### Symptom (live, `ma-qa-20261007c` variant_bbca turn 2, request `ma-qa-20261007c-variant_bbca-2`)

Timeline from the orc log (`ai_model_call.tools_requested`, `mechanical_steps_merged`, `analysis_sessions_superseded`):

```
call 1  submit_data_need_spec ×4 (parallel; refused for a malformed data_request_id, the model resubmitted one by one)
call 2  submit  -> merged: prepare_data_bundle READY, open_analysis_session ACTIVE   (first need: backend opens, M102 OK)
call 3  submit  -> merged: prepare_data_bundle READY                                (later needs: prepared only, M102 OK)
call 4  submit  -> merged: prepare READY
call 5  submit  -> merged: prepare READY
call 6  open_analysis_session -> analysis_sessions_superseded (session 1 closed, never used)
call 7  open_analysis_session -> superseded (session 2 closed, never used)
call 8  open_analysis_session -> superseded (session 3 closed, never used)
call 9  run_python
call 10 open_analysis_session -> superseded (session 4 closed)
call 11 run_python(complete) -> merged complete_analysis
call 12-17 open -> run_python(complete) ×3, each merged complete_analysis
call 18-20 check_references; 21 TYPED_FIGURES gate; 22 final
```

Result: 22 calls, 294 s, correct answer with the Holm correction. Compare 07a: 34 calls, 815 s. About 4 calls and
4 sessions were wasted.

### Verified root cause

- One open session per run (S08), enforced in `apps/market-ai-orc/app/orchestrator.py:2922` `_one_open_session`:
  - an open with another open, unused session closes the earlier one (`analysis_sessions_superseded`, line 2949);
  - the same function also has an `ANALYSIS_SESSION_ALREADY_OPEN` refusal path (line 2934). **Read it first** to see
    when each path applies.
- The model's plan "prepare all, open all, then run" conflicts with that rule. The tool result names the closed
  session, but no next step that the model follows.
- Related code:
  - `_pending_sessions` (line 2916), the M102 rule (no automatic open while a session is pending);
  - `_merged_steps` (line 3808), EXEC-P5;
  - `MERGED_STEPS_NOTE` (line 1412);
  - `app/tools/envelope.py:47`: `ANALYSIS_SESSION_ALREADY_OPEN` → `USE_OPEN_SESSION`.

### Options

| Option | What | Fit with the principle |
|---|---|---|
| **B (recommended first)** | While a session is open and has no execution, refuse a new `open_analysis_session` with `ANALYSIS_SESSION_ALREADY_OPEN` instead of closing the earlier one. The message names the open session and the order: open → run_python(complete=true) → next | Guarantee (capacity/cost) with a clear way out; small change; uses an existing code and envelope action |
| A | After `complete_analysis` (merged or called), the backend opens the session of the next prepared bundle in the same call (EXEC-P5 style) | Saves the most calls, but the backend guesses which bundle comes next: a judgement taken from the model |
| C | Only a sentence in `MERGED_STEPS_NOTE` / the open tool's description: "one session at a time" | No guarantee; the model already ignored the tool result |

### Risks and mitigation (option B)

| Risk | Mitigation |
|---|---|
| The model retries the open in a loop | The repair budget (`_repair_budget`, `REPEATED_TOOL_CALL`) already caps repeats; the refusal names the session to use |
| A run that really wants to drop an unused session can no longer do it | Allow the replacement once the open session has an execution, or when the model passes the same bundle again; keep S08's run-end close |
| Changes the S08/M102 tests | Update `tests/test_merged_steps.py` and the S08 session tests (`grep -rn "analysis_sessions_superseded\|ALREADY_OPEN" apps/market-ai-orc/tests`) |
| Tool behaviour change | Check whether `AI_TOOLS.md` describes the open rule; if so, regenerate it (`scripts/generate_ai_tools_doc.py`) and update `Tool_Catalog` by a new migration only if the tool contract text changes |

### Tests and live check

- **Unit:** four needs prepared, then the model opens a second session while the first is unused → refused with
  `ANALYSIS_SESSION_ALREADY_OPEN` and no session closed.
- **Live:** re-run `variant_bbca` (2 turns, about USD 0.15) from `apps/orc-test-runner/suites/qa_20261007c.json`.
- **Pass:** `analysis_sessions_superseded` = 0, model calls < 22, same answer quality.

---

## Benchmark to run first (external, online)

Use `WebSearch` in standard mode. Cross-check what you find against the proposals above and cite the URLs.

1. **Clarifying questions with quick replies (M109).**
   - Do major assistants keep the model's question when its suggested replies collapse or are invalid?
   - How do they carry a parameter with a choice: payload vs label?
   - Example searches:
     - "suggested replies payload postback clarification chatbot";
     - "Dialogflow / Rasa buttons payload intent entity";
     - "LLM ask clarifying question options UX".
2. **Tool design for agents (M110).**
   - Anthropic "Writing effective tools for agents" (actionable error messages, return the next step).
   - OpenAI function-calling best practices.
   - Patterns for single-slot resources: queue vs refuse vs auto-advance, for example "Jupyter kernel one active
     session", "agent tool error message next action".
3. **Record the findings** in `ERRORS_AND_SOLUTIONS.md` M109/M110 (Solution column, with sources) before proposing an
   `EXEC.md` section.

## How to verify locally

- **orc tests:** create a venv in `apps/market-ai-orc` (dependencies in its README / requirements), then
  `python -m pytest -q -p no:cacheprovider`. Baseline at `5cdd985`: 1293 passed, 223 skipped.
- **Drift tests:**
  - `tests/test_ai_router_doc.py` (regenerate `AI_ROUTER.md` with `scripts/generate_ai_router_doc.py` after router
    text changes);
  - `tests/test_ai_tools_doc.py`;
  - `tests/test_ai_models_doc.py`.
- **Router benchmarks need `OPENROUTER_API_KEY`:** `scripts/benchmark_turn_router.py --ask-back`, and
  `scripts/benchmark_plan_reply.py --ask-back` (EXEC-D baseline 36/36). Read the key in-process; never print it.
- **Credit rule:** stop and report if the OpenRouter key's remaining limit is below USD 0.30 before a paid test (it was
  USD 1.529 after `ma-qa-20261007c`).
- **Before deploy:**
  - `git diff --check`;
  - commit on the working branch, fast-forward `main`, push;
  - wait for the exact orc deployment to reach `SUCCESS`;
  - read its start log;
  - record in `RAILWAY_CHANGELOG.md`, `ERRORS_AND_SOLUTIONS.md`, `EXEC.md` (`AGENTS.md`, Mandatory workflow).
