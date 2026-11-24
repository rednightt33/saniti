# Is the published close adjusted for a corporate action? (ERRORS M559, M560)

Read-only checks on dev (pgweb role, credentials from Railway into memory only, `verification/terminal_api/pgq.py`).
Run from this folder with the publisher's Python environment and the Railway CLI on PATH.

- `basis_now.py OUT.json`: the publisher's own `broker_basis` on dev's rows now, for the stocks the Screener flags.
  `results_2026-11-24_basis_now.txt`: VKTR, AHAP and BUVA read `price` raw although pulled again on 2026-10-31.
- `jump_rule.py`: a one-session rule (the closes either side of the ex-date against the action's factor) on every
  price action since 2018. `results_2026-11-24_jump_rule.txt`: the 7 measurable actions from 2026-09-12 read adjusted;
  before it 208 adjusted and 6 with a step in the stored history (register UD40).

Plan: EXEC.md EXEC-PRICE-BREAK-BASIS (waiting for the user's approval of the revision, UD38).
