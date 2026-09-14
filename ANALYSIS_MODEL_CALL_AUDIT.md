# Analysis model-call audit

`public."Analysis_Model_Call"` records one row for every provider response made
inside an `Analysis_Request` processing attempt. It answers which model was called, which analytical
stage and tool families were visible, how many tokens that individual call used,
and what provider-returned reasoning material was available for audit.

This table complements rather than replaces the other analysis tables:

- `Analysis_Request` is the full request lifecycle and cumulative usage.
- `Analysis_Model_Call` is one provider-call iteration and its temporary reasoning audit.
- `Analysis_Step_Log` is one tool, query, compaction, or orchestration step.
- `Analysis_Evidence` is compact reproducible evidence supporting final claims.

## Stored and deliberately not stored

The backend keeps provider requests at `store=false`. It stores only reasoning
blocks that the provider actually returns; it does not reconstruct hidden
chain-of-thought and does not copy prompts, credentials, query result payloads,
or complete conversation context into this table. The retry-safe identity is
`(request_id, attempt_number, iteration_number)`. `decision_summary_source`
distinguishes an actual provider reasoning summary from a deterministic action
summary such as the names of requested tools.

`input_tokens`, `output_tokens`, and `reasoning_tokens` are per call.
`active_context_tokens` is the backend estimate of instructions, active input,
and exposed tool schemas. Cumulative request totals remain in `Analysis_Request`.

Provider-returned reasoning is bounded by `AI_REASONING_MAX_BYTES_PER_CALL` and
retained until `reasoning_expires_at`. The in-service worker periodically clears
expired `reasoning_details`, marks the row `PURGED`, and sets
`reasoning_purged_at`; the row, per-call usage, and concise decision summary remain.
Current configuration defaults are:

```text
AI_STORE_REASONING_DETAILS=true
AI_REASONING_RETENTION_DAYS=30
AI_REASONING_MAX_BYTES_PER_CALL=65536
AI_REASONING_CLEANUP_INTERVAL_SECONDS=3600
```

The cleanup is idempotent and never deletes an `Analysis_Request`, evidence row,
or model-call audit row. If a provider supplies no reasoning, the format is
`NONE`; absence must not be interpreted as proof that the model performed no
internal reasoning.

## QC and context relationship

Quality checks are conditional across all tools. A scoped check runs only when
coverage, NULL/gap, freshness, cross-feature consistency, anomaly validation, or
a material conclusion requires it. `WARNING` and source-valid anomalies continue
analysis; only an impossible/invalid `FAIL` blocks the affected conclusion.

At 75% of the configured cumulative input budget, the orchestrator compacts
superseded metadata and tool results even when the active context is still below
32k. The hard 64k active-context and 100k cumulative-input ceilings remain
independent. Per-call rows in this table make that distinction directly auditable.
