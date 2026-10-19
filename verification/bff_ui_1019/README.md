# BFF composer and Details — 2026-10-19

User approval, verbatim: “Okay, please proceed, Ensure sebelum done kamu test visually dan interactionally baik dimobile dan desktop.”

Requested scope: align AI answers with the message box; resize the box by dragging its border on desktop and mobile;
Enter must preserve the Details panel state; keep Pinned responses / Response History headers visible while their lists
scroll; newest history first, pinned order unchanged. Frontend source only, through Git main.

## Implementation

- `static/index.html`: shared responsive reading width and actual scrollbar measurement; neutralise legacy positional
  offsets; a top-border grip with mouse/touch pointer capture and Arrow Up/Down support. Drag up grows, down shrinks.
  Manual height survives typing during the page session. The viewport caps it, preserving conversation/toolbar room.
- Submit preserves the panel's current state. Desktop Enter sends, Shift+Enter inserts a newline; touch keyboards retain
  multiline Enter. Explicit Details controls remain available.
- Each section header is sticky in its own scroll area, with an opaque mask over the scroll padding; collapse, resize, unpin and jump remain interactive. History
  reverses a copy of the chronological view list, so pins and backend turn order stay unchanged. New entries are revealed
  below the fixed header.
- New wording belongs to `static/edge-labels.js`. Preview was built, edited and imported with `preview/edge_preview.py`.

No Orc/model/router, API, database, Railway variables, service source configuration or scheduler change.

## Verification

`tests/test_composer_layout.py`: **8 passed** through real HTTP BFF, authentication, queue, SSE and a disposable local
PostgreSQL database, with a deterministic upstream fixture (no paid model call). Viewports: 1920×1080, 1280×800,
390×844 and 360×740. Mobile contexts have `is_mobile` and `has_touch`; CDP dispatches actual touch start/move/end,
desktop uses mouse drag. Keyboard resize is checked too.

Assertions cover response/composer left and right edges; a reserved classic desktop scrollbar; growth, shrink and typing
after manual resize; light/dark screenshots; short/rotated viewports; multiline editing; closed panel staying closed after
Enter/Submit; open desktop panel staying open; independent sticky headers; collapse/reopen; LIFO history and unchanged
pin order after an actual server reload; latest history summary below its header. No page JavaScript errors.

Screenshots were inspected visually for desktop and mobile, including resized input, both scrolled headers, light theme
and a short viewport. Mobile verification uses Chromium touch emulation, not a physical iOS/Android device.
Artifacts: `/workspace/edge-ui-layout-2026-10-19/` in the execution workspace. Compact reproducible results and artifact
hashes are in `results.json`. All **127 distinct BFF checks** have passing results across these groups: 113 existing checks passed in the initial
regression run; that run also exposed two failures (the old oldest-first selector and suppressed compatibility click after a touch drag
on the section toggle). The final affected run passes all 12 selected checks: the eight new cases plus both corrected
regressions, the strengthened oldest-response scroll test and desktop split/collapse. The remaining four preview breakpoint checks pass via an
intercepted HTTP document, avoiding this environment's browser restriction on `file://` without changing browser policy.
Section toggles use `touch-action:manipulation`, handle an unmoved touch release directly, cancel the native touch-end click before layout changes and suppress any
later compatibility click for 750 ms; mouse and keyboard retain native click handling. Event tracing verified that the
failing browser case emitted pointer/touch down/up but no click. Touch assertions wait for actual expanded/collapsed state. Immediate Enter/Space and real mouse activation after touch are also checked, preventing duplicate toggles. No final
failures remain. Dependency deprecation warnings are unrelated. `git diff --check` and preview build/import round trip pass.

The pre-change regression failed with a -4 px offset on both edges on the compact desktop. Final measurements show zero
offset before/after resize across all four target sizes (see `results.json`).

## Deployment

Inspected before changes: lucid-patience / dev, edge-bff `c3656044-2817-44a7-9b55-54910bab416f`, GitHub
`rednightt33/saniti`, branch `main`, root `/apps/edge-bff`, watch `/apps/edge-bff/**`, one replica, `/ready` healthcheck.
Active baseline `22c9671d-c117-4db6-9b6e-cd9e5a53f7d9` SUCCESS; no staged BFF changes. Delivery uses Git push and
Railway's existing source connection. Deployment **98142fe9-9b86-4276-b417-c5660bd809da** reached **SUCCESS** at 2026-10-19 05:09:22 UTC
(12:09:22 WIB). Railway metadata confirms source `7c6bf18462eb84053ac0358cf46dbf887b076cfd`, branch `main`.
One replica running, zero crashed replicas, no BFF warnings/criticals or recent failures. Runtime logs show application
startup complete and Uvicorn serving port 8080. Uvicorn INFO lines are labelled error by the log transport because they
use stderr; no application exception is present. Orc remains on `4138d8bd-70e9-451d-9e77-faf91f6966c2`; sandbox
remains on `84fa7fa3-6bda-46af-8162-7d13d42fde7b`, both SUCCESS. The disposable local PostgreSQL container was stopped
and removed after testing. Approval is archived here; the completed item was removed from `EXEC.md`.

 Direct public asset/health readback from this execution environment is blocked
by the outbound proxy (HTTP CONNECT 403); verification will use Railway's exact Git source metadata, healthchecked
SUCCESS status, replica state and runtime logs. The visual/interaction tests above run against the real local BFF.
No live inference or live conversation/data mutation is used.
