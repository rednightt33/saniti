# backtest-worker (EDGE backtest, in progress)

Private worker for the EDGE backtest page. User decision K1 = C (2026-10-26): the worker runs on Node and imports the
Terminal's calculation module (`apps/edge-bff/terminal/src/calc/indicators.ts`), so the chart, the page's preview and
the backtest share one formula per indicator. Inspection and open decisions:
`/mnt/project-files/backtest/inspeksi-lengkap-backtest-2026-10-26.md` (project files).

Done (no business decision needed):

- `registry/backtest-registry.json`: the 53 indicators with their function, inputs, accepted parameters (only the ones
  the module reads, with its executable defaults and the workbook limits), outputs and `available_for_backtest`; no
  visual settings. Built by `scripts/build-registry.mjs` from `indRegistry.json` + `DEFAULTS`; `npm run registry`
  rewrites it, a test fails when it is stale.
- `src/registry.ts`: parameter validation (refuses unknown parameters, wrong types, out-of-range values, fractional
  integers, unlisted options; never rounds or clamps) and `REGISTRY_VERSION` (hash of the registry and the module).
- `src/conditions.ts`: indicator conditions (price/volume or an output against an output or a value; `gt`, `lt`,
  `crosses_above`, `crosses_below`), the page's price-action and pattern conditions on verified indicator outputs,
  ALL / ANY / AT LEAST N within 1–20 bars, exit signals ANY / ALL, switch-on events and true-bar counts.

Not yet (waiting for decisions E1–E5, K3–K8, U1): storage reader, execution engine, statistics, robustness, HTTP
service, Dockerfile, edge-bff integration. Flow and broker conditions stay disabled until their storage data is verified.

Differences from the page, on purpose: thresholds are fractions (`dip` value -0.03, not -3); a missing low is never a
swing low in the bullish divergence (the page treats NaN as a low).

Tests: `npm test` (Node ≥ 22.6 with type stripping, no dependencies). The condition tests run on the Terminal parity fixtures (real
stored bars of 8 tickers) against the page's own condition code (`tests/oracle.mjs`); signals must be equal bar by bar.
