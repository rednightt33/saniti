# web-governor-test-runner

One-off live test runner for `market-web-governor` on the Railway private network (`dev`). It exists because the
agent container cannot reach Railway SSH (port 22) and the Web Governor has no public domain.

- Railway service `web-governor-test-runner`, restart policy `NEVER`, no domain, no database or bucket credentials.
- One variable: `WEB_GOVERNOR_API_KEY`, a Railway reference to `market-web-governor`'s key. It is never printed.
- `run.py` uses only the Python standard library and calls
  `http://market-web-governor.railway.internal:8080`.
- `plan.json` selects the phase:
  - `{"phase": "pre", "prefix": "<unique request-ID prefix>"}` runs the live scenarios (auth, readiness, search,
    domain policy, exact fetch, multi-criterion WebNeed, idempotency, budgets) and prints a persistence snapshot.
  - `{"phase": "post", "web_need_id": …, "evidence_id": …, "web_need_sha256": …, "evidence_sha256": …}` re-reads
    those records after a Web Governor redeploy and compares hashes.
- Output: short `WGT {json}` lines plus the full result document as numbered `WGTDUMP i/n` gzip+base64 chunks,
  because Railway drops long log lines. Reassemble the chunks in order, base64-decode, then gunzip.

Deploy a run with `railway up apps/web-governor-test-runner --path-as-root --service web-governor-test-runner`. Use a
new request-ID prefix for every run; request IDs are idempotency keys.
