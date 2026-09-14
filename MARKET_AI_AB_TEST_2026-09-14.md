# Market AI compaction A/B test — 2026-09-14

## Decision

Keep `AI_CONTEXT_COMPACTION_MODE=DISABLED` as the current Railway `dev`
setting. `PRESERVE_DECISIVE` remains implemented and configurable, but the test
did not demonstrate that it preserves every explicitly requested observation.
This decision disables only cross-iteration compaction; mandatory per-tool
row, byte, and token shaping remains active.

## Controlled setup

- Provider/model: OpenRouter / `deepseek/deepseek-v4.1-flash`.
- Code under test: commit `88a5514` for both modes.
- Railway service: `market-ai-backend` in environment `dev`.
- Questions: the exact same fixed suite in `scripts/stress_market_ai_ab.py`:
  five screening questions (`S1`–`S5`) and five other analyst questions
  (`F1`–`F5`).
- Hard cumulative input ceiling: 150,000 tokens per `Analysis_Request`.
- Mode A: `AI_CONTEXT_COMPACTION_MODE=DISABLED`.
- Mode B: `AI_CONTEXT_COMPACTION_MODE=PRESERVE_DECISIVE`.
- Mode B deployment: `63f2e3b9-d8ef-423b-aced-6e6a8f24bf62` (`SUCCESS`).
- Final restored Mode A deployment: `e962dc56-8c02-4f22-a943-e4a2a1d1c332`
  (`SUCCESS`).

Preliminary batches that ran before the final JSON/date/serialization fixes are
not comparable and are excluded from the figures below. Their failures remain
available in the audit tables and local result files as recovery evidence.

## Aggregate results

| Metric | Mode A: disabled | Mode B: preserve decisive | Difference |
| --- | ---: | ---: | ---: |
| Terminal success | 7/10 | 8/10 | +1 request |
| Cumulative input tokens | 902,667 | 857,164 | -45,503 (-5.0%) |
| Cumulative output tokens | 66,073 | 65,085 | -988 (-1.5%) |
| Total latency | 996.363 s | 573.907 s | -422.456 s (-42.4%) |
| Tool calls | 112 | 110 | -2 |
| Model iterations/calls | 92 | 88 | -4 |
| Successful answers with durable evidence | 7/7 | 8/8 | all |
| Data/QC calls after evidence gate | 0 | 0 | equal |
| Requests actually compacted | 0 | 2 | S5 and F4 only |

The higher terminal-success count in Mode B must not be attributed entirely to
compaction. `S2` succeeded in Mode B but had `context_compaction_count=0`; its
Mode A failure was malformed/truncated final JSON after the bounded repair
attempts. This is provider-output variance, not evidence that compaction fixed
the request.

## Per-question terminal result

| Question | Mode A | Mode B | Compacted in B | Material observation |
| --- | --- | --- | ---: | --- |
| S1 | SUCCESS | SUCCESS | 0 | B supplied the complete requested table; A summarized it. |
| S2 | FAILED | SUCCESS | 0 | A final JSON remained truncated; B completed without compaction. |
| S3 | SUCCESS | SUCCESS | 0 | Both supplied the requested multi-period ranking. |
| S4 | SUCCESS | SUCCESS | 0 | A supplied every requested numeric column; B omitted the per-ticker values. |
| S5 | FAILED | FAILED | 1 | A exhausted phase output budget; B compacted once, then exceeded 150k cumulative input. |
| F1 | SUCCESS | SUCCESS | 0 | Both correctly explained the catalog definition and caveats. |
| F2 | SUCCESS | SUCCESS | 0 | B contained an internal contradiction about which banks had positive 20-day return. |
| F3 | SUCCESS | SUCCESS | 0 | Both found the longest/latest BBCA negative-return streaks with scoped context. |
| F4 | SUCCESS | SUCCESS | 1 | A supplied all five brokers and requested metrics; compacted B omitted net values, types/classes, and z-scores. |
| F5 | FAILED | FAILED | 0 | Both exhausted the phase output budget before evidence/final answer. |

## Answer-quality review

A strict manual rubric was applied after terminal status:

1. every explicitly requested output field is present;
2. the narrative is internally numerically consistent;
3. material conclusions are supported by persisted evidence;
4. requested caveats and non-predictive boundaries are retained.

Under that rubric, Mode A produced six complete answers, one partial answer, and
three failures. Mode B produced five complete answers, three partial answers,
and two failures. The two requests that actually exercised compaction provide no
quality win: S5 failed in both modes, while F4 regressed from complete to partial.
Therefore the observed latency and aggregate-token improvements are not yet a
sufficient reason to enable cross-iteration compaction by default.

## Evidence and stopping-policy audit

- Every successful request in both modes persisted evidence and cited only
  evidence IDs that exist for that request.
- There were zero successful data or QC tool calls after the `record_evidence`
  gate in either mode.
- Exactly one successful `complete_analysis` call exists for every successful
  request.
- All 180 provider calls across both batches have a durable
  `Analysis_Model_Call` row, a bounded provider-returned `reasoning_details`
  payload, a concise `decision_summary`, token usage, and a 30-day expiry.
- Provider-returned reasoning is retained for audit; the backend does not
  reconstruct missing hidden reasoning or expose it as the analyst answer.

## Remaining gaps

- Final-answer formatting still needs a stronger bounded recovery path: S2 Mode
  A returned truncated JSON despite two retries.
- Evidence is durable once recorded, but S5/F5 exhausted a budget before calling
  `record_evidence`; intermediate query hashes remain in `Analysis_Step_Log` but
  there is no completed evidence package or user answer.
- Output-budget handling should reserve enough room for one concise evidence
  package and final answer even when earlier calls are verbose.
- `PRESERVE_DECISIVE` should not be reconsidered as the default until a regression
  test proves that all user-requested rows/columns survive compaction.
- Deferred priority 7 was intentionally not implemented or activated.

## Verification

- Backend unit tests: 58/58 PASS.
- Live backend/catalog verification: PASS.
- Deterministic Golden Test run `801f4f11-5d8a-4774-9fa6-58bf60f68f47`:
  16/16 PASS.
- Final Railway mode: `DISABLED`, cumulative input ceiling 150,000.
