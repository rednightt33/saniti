# Sector Analysis prototype: audit (2026-11-26)

The user's prototype `sector-analysis (1).html` (2026-11-26, an EDGE Reference Pack page: the Overview app with a new
"Sector Analysis" page and its data `window.SX` built in) was audited before any build (PLAN.md SECTOR-ANALYSIS).
The prototype itself stays outside Git (it carries market data, as the Reference Pack does).

- `click_inventory.md`: every card, control and option clicked at 1440 px (and each tab at 390 px), what each does, and
  21 defects with their evidence (screenshots kept in the session's scratchpad only).
- `formulas.md`: every card's inputs, lookback and formula (with the prototype's `logic.js` line numbers), the GAP list
  (synthetic or missing data) and the derived measures a server-side precompute would produce.

## Final version (2026-11-26, the user: "Terlampir")

`final/` audits the user's final prototype the same way (`final/click_inventory.md`, `final/formulas.md`) and lists what
changed against the first (`final/changes_click.md`, `final/changes_formulas.md`). The data `window.SX` is
byte-identical and no formula, input, period or default changed; the changes are sorting (one shared multi-column sort),
selection and hover, floating windows (sized to content, "How to read" footers), wording and axes. Of the first version's
21 defects 4 are fixed, 4 partly, 13 remain (the phone layout among them); 8 are new. Every GAP (G1-G14) is still open:
the illustrative values are now shown without their "illustrative" note where a "How to read" footer replaced it.
