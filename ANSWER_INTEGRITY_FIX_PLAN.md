# Answer integrity fix plan: M44, P14, P17, G13

Status (2026-10-01): **final plan approved by the user; implementation in progress (step 1: M44 + P14).** User-requested items and decisions are recorded per item.
Errors: `ERRORS_AND_SOLUTIONS.md` M44, P14, P17, G13. Each item fixes a class of failure, not the observed
instance (user rule: a fix must not name a table, column, ticker or question unless that object is the cause).

| # | Item | Class of failure | Layer | Status |
|---|---|---|---|---|
| 1 | M44 | A figure is resolved against a partial view of an output (a page), so a name and a value can come from different rows | market-ai-orc reference registry and renderer | Root cause verified 2026-10-01 |
| 2 | P14 | The renderer can show only a number or a text; any other JSON value fails and the whole answer is discarded | market-ai-orc renderer | Verified 2026-10-01 (probe below) |
| 3 | P17 | A wording gate rejects (and finally discards) a whole answer for one sentence; its negation rule looks only before the phrase | market-ai-orc answer gates, response contract | Root cause verified 2026-09-30; user design 2026-10-01 |
| 4 | G13 (part 2) | Plan feasibility compares a guessed row count (PostgreSQL planner estimate) with a counted limit (bundle rows) | market-sql-governor estimate, market-ai-orc planner | Root cause verified 2026-09-30 |

Common principle: **the backend measures or renders; it does not guess, and a problem in one part of an answer is
marked on that part instead of discarding the answer.** Number provenance stays strict: no figure without a governed
source reaches the user.

---

## 1. M44: figures resolved against the last page read

**Mechanism (verified).** `_track_references` (`app/orchestrator.py`) keeps one object per `out.<output_id>`.
`get_session_output` registers the page it returned under the same key and replaces the `complete_analysis` entry. In
run `ma-m43g13-20260930a-m01_broker_bank_crash-1-m4a` the model read the 68-row `crash_broker_ranking` at offset 13;
afterwards `rows` held only that page. The first draft's name selectors (`rows[broker=XL]`) were refused because XL
is not on the page; the repair used positions of the full table (`rows[0]` for XL), which resolved against the page
(row 0 = AZ). Six named brokers were shown with other brokers' figures; every gate passed because each figure had a
source.

**Who else is exposed.** Any released table longer than what `complete_analysis` shows at once (up to 200 rows, fewer
when the 40,000-byte tool budget cuts it): full-universe rankings (~840 tickers), sector screens, Feature tables, and
future macro/FX outputs. Not exposed: tables read whole in one view.

**Fix.**
1. *Complete-table resolution* (`app/orchestrator.py` `_track_references`, `app/value_refs.py`): the registry keeps
   rows by absolute index per output (`offset + i`); a page adds rows and never replaces the entry. At render time a
   reference to a row the run has not fetched is resolved by the backend from the released output
   (`GET /v1/sessions/{id}/outputs/{output_id}`, paged, bounded by the output's `row_count`), so a reference always
   means the row of the complete table.
2. *No positional rows in keyed tables* (`app/value_refs.py`): when a table has a text column whose values are unique
   (broker, ticker, series code: derived from the rows, not from a list of names), a reference by position
   (`rows[3]`, `rows.3`) is refused with the selector to use (`rows[broker=XL]`). Positions stay allowed for tables
   without such a column.
3. *Absolute row number* (user suggestion 2026-10-01): every released table row carries its position in the complete
   table as `_row` (added by the backend when it registers or fetches rows, never by the model), so pages show true
   positions and a position reference in a table without an identity column resolves to the same row the model read.
   It complements items 1 and 2; it does not replace item 2, because a row number cannot stop the model from writing
   a name next to another entity's row.
4. Prompt (support only): one sentence that rows of a table are referenced by a selector on their identity column.
   Item 2 enforces it.

**Verification.** Unit: a page read at offset 13 then `rows[broker=XL]` resolves to XL's row of the full table; a
positional reference in a keyed table is refused; a table without a unique text column still accepts positions. Live:
the broker question again, and a full-universe return ranking (a second case, different table).

**Scan of past runs (reader key on the runner, see Outstanding).** List audited runs whose final answer used a
positional row reference after a `get_session_output` call on the same output, to know whether other answers were
affected.

---

## 2. P14: values the renderer cannot show

**Probe (2026-10-01, `app/value_refs.render`).** Shown: numbers, numeric text, text without a format, a date as text.
Marked `[field]`: objects, missing fields. **Failed** (and, after the repair budget, the whole answer forced to
LIMITATION): `true`/`false`, `null`, `NaN`, any list (numbers, texts, rows, empty), and a text with a number format
(for example a date with `|dec:1`). So lists are one case of a general gap: the renderer defines numbers and text only.

**Fix (`app/value_refs.py`): a display rule for every JSON value.**

| Value | Shown as |
|---|---|
| number | as now (format applies) |
| text | as written (a number format on non-numeric text is ignored, with a note) |
| `true` / `false` | `ya` / `tidak` |
| `null` | `null` (user decision 2026-10-01) |
| `NaN`, `inf` | `undefined` (user decision 2026-10-01) |
| list of numbers or texts | joined with `; `, at most 8 items then `(+N lainnya)`; numbers formatted with the reference's format |
| empty list | `tidak ada` |
| list of objects, object | `[field]` marker, as for objects today |

Every number shown, inside a list or a text, joins the provenance sources under the reference's label, so the
provenance gate is unchanged. A reference that still cannot be resolved (unknown output, malformed) is shown as a
marker with one limitation line; it no longer discards the answer (same decision as M43 for missing fields).

**Verification.** Unit: each row of the table above, plus a CI pair `finding.<a>.backend.ci`, quality warnings
`finding.<a>.warnings`, and a malformed reference after its repair. Live: a research question whose answer quotes
warnings and intervals.

---

## 3. P17: mark doubtful claims instead of rejecting the answer (user design 2026-10-01)

**Mechanism (verified).** `_claim_problem` (`app/orchestrator.py`) looks for a negation only in the 40 characters
before a causal or predictive phrase, so "klaim bahwa … menyebabkan … tidak terbukti" counted as a claim; the CLAIM
gate allows one repair per run and then replaces the whole answer with a LIMITATION.

**User design.** The editor keeps detecting; it never rejects. The answer reaches the user, and each sentence the
editor flagged is marked so the front end can show a hover note ("klaim ini tidak didukung oleh analisis").
Example: in "BBCA terbukti naik", the phrase "terbukti naik" is flagged and marked.

**Fix.**
1. *Detection*: one negation rule shared by every wording check (CLAIM, findings verdict, agreement): a negation in
   the same clause, before **or after** the phrase (the P09/P10 clause rule extended), plus the zero-count rule. A
   sentence that denies a claim is not flagged.
2. *Marking instead of rejection* (CLAIM gate in DataNeed answers): no repair turn, no forced LIMITATION. The response
   gains `response.annotations`: one entry per flagged span `{kind: CAUSAL|PREDICTIVE|VERIFIED_CALCULATION,
   quote, start, end, sentence, note}` (offsets in the final `answer`), `validation_gate` `ANNOTATED`, and one
   limitation line ("Beberapa kalimat ditandai: klaim sebab-akibat/prediksi tidak didukung oleh analisis
   historis."). Additive field: clients that ignore it still get the answer and the limitation line.
3. *Italics* (user decision 2026-10-01, "miring dulu saja for now"): the flagged span is also wrapped in italics in
   `answer`, so it is visible without hover; `annotations` carries the offsets after the italics are inserted.
4. Not extended to the findings verdict-wording and agreement checks (user decision 2026-10-01): they keep their
   current repair-then-LIMITATION behaviour; only their shared negation rule (item 1) changes.

**What stays strict.** Number provenance, value references, the findings status (from the backend) and the research
plan gates are unchanged: a figure without a source is still never shown.

**Risk.** A flagged causal sentence is visible to the user (marked, not removed). Mitigation: the hover note, the
limitation line, `validation_gate` ANNOTATED, and the audit keeps every flag (`final.annotated` event).

**Verification.** Unit: e02's sentence is not flagged; "BBCA terbukti naik" and "net beli asing menyebabkan kenaikan"
are flagged and annotated, the answer kept; "causes … is not supported" is not flagged. Live: e02 rerun.

---

## 4. G13 (part 2): count rows instead of estimating them

**Mechanism (verified).** `check_research_feasibility` and the preflight sum the Governor's `result_rows`, the
planner's `Plan Rows` from `EXPLAIN` (`market-sql-governor` `governor.py` `_explain`); the sandbox refuses a bundle on
counted rows (2,000,000). In e02 (suite20d) one part was estimated at 108,091 and returned 319,801 (about 3x), so a
plan passed and failed after the user's approval.

**Fix (Governor counts, it does not guess).**
1. For `estimate_only` parts (feasibility and preflight), when the planner estimate could change a decision (at least
   `SQL_ESTIMATE_COUNT_MIN_ROWS`, default 10% of the bundle limit), the Governor runs `SELECT count(*)` over the same
   compiled SQL (scope, semi-join restrictions, ranges) under `SET LOCAL statement_timeout =
   SQL_ESTIMATE_COUNT_TIMEOUT_MS` (default 7,000 ms, user decision 2026-10-01). The answer carries `counted_rows` and `row_basis` `COUNTED`; on a timeout
   `row_basis` is `PLANNER` with warning `ROW_ESTIMATE_UNCERTAIN`.
2. market-ai-orc (`research_planner.py`, `data_planner.py`) uses `counted_rows` when present. An oversized plan is
   then split into bundle groups by the existing logic, or returned `REVISION_REQUIRED` with rows per request,
   **before** the user sees it.
3. Behind `SQL_ESTIMATE_COUNT_ENABLED` (default off); turned on in dev with the user's approval.

**Risks compared with today.**

| | Today (estimate) | Counting |
|---|---|---|
| Accuracy | can be off several times (3x seen) | exact for the moment of the check |
| Planning time | ~50–100 ms per part | the count reads the same rows: from well under a second (indexed, small scope) to seconds per large part; bounded by the timeout and only where it matters |
| Database load | almost none | one extra scan per counted part on the shared PostgreSQL (crons and price loads share it) |
| Failure mode | plan approved, then BUNDLE_TOO_LARGE after approval; extraction wasted (1.9 million rows discarded in b01) | plan revised or split before approval; on a timeout, no worse than today (flagged) |
| Not covered | — | bundle bytes (256 MB) still measured only at build; data loaded between check and run (small) |

Also not chosen: per-entity row counts from `AI_data_coverage` (cheap, but exact only for entity and date filters and
refreshed once a day, C06).

**Verification.** Governor unit tests (count used when present; timeout falls back with the warning); planner tests
(e02 shape split or revised before a plan); live: e02 and a broad cross-section with `broad_scope`.

---

## Order

M44 and P14 (one module family, value references) → P17 (gates and response contract) → G13 (Governor, then
market-ai-orc). Each: tests, push `main`, deploy one service at a time to `SUCCESS`, live check, records in
`RAILWAY_CHANGELOG.md` and `ERRORS_AND_SOLUTIONS.md`; Tool_Catalog version for a changed tool output
(`check_research_feasibility` gains `row_basis`).

## Decisions

- 2026-10-01 (user): P17 flagged spans in italics as well as `annotations`; marking not extended to the findings
  wording checks; G13 count timeout 7,000 ms; M44 adds an absolute row number column (`_row`) next to items 1 and 2.
- Open: turn on `SQL_ESTIMATE_COUNT_ENABLED` in dev after deploy; scan of past runs for M44 (reader key ready).
