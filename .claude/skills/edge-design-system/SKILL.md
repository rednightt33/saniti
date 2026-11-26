---
name: edge-design-system
description: The EDGE / Market Lab design system (tokens, components, charts, page patterns, how to add a page). Use it whenever you build or change a page, panel, card, chart, dialog or HTML mockup of EDGE (apps/edge-bff), or answer how something in EDGE should look, so a new page matches the existing ones instead of starting from scratch.
---

# EDGE design system

User decisions 2026-11-18 (`EXEC.md`, EXEC-DESIGN-SYSTEM): spec **v1.2** is the base; where EDGE's pages differ, the
**canonical layer** below names the one version a new page uses; patterns from the user's design proposals are taken
**adapted to the tokens**. A copy of this system lives as a Design System artifact on claude.ai (link in `README.md`);
this folder is the source, the artifact follows it.

## Files

| file | what |
|---|---|
| `assets/spec-v1.2.css` | EDGE Design Spec v1.2, verbatim (tokens, base, components, colour scales, button catalog) |
| `assets/edge-canonical.css` | the canonical layer: the 11 decisions + the components a new page reuses |
| `assets/icons.svg` | the 16 px icon sprite (`<svg class="ic"><use href="#i-NAME"/></svg>`) |
| `assets/edge-ds.js` | number formats and hand-made SVG charts (`window.EdgeDS`), the reference implementation |
| `assets/showcase.html` | every component on made-up data; open it, it is the visual check (`?theme=dark`) |
| `reference/components.md` | the exact markup of each component, when to use it, its classes |
| `reference/charts.md` | how charts are drawn: SVG rules, lightweight-charts setup, tooltips, number formats |
| `reference/patterns.md` | page layouts and the patterns from the design proposals (widgets, windows, side panels, day counts) |
| `reference/new-page.md` | how to add a page to EDGE end to end (sub-app, shell, BFF route, tests, docs) |
| `README.md` | where everything came from, how to update this system and the claude.ai copy |

## The rules (canonical, 2026-11-18)

1. **Tokens:** load Inter, then `spec-v1.2.css`, then `edge-canonical.css`, then the page's own CSS (unlayered, so it
   wins without `!important`). Use `var(--token)`; never a literal colour or a px value the spec has a token for.
2. **Selected state:** class `.on`, plus `aria-pressed` (toggles, segments) or `aria-selected` (tabs, rows).
3. **Segmented control** (`.seg`, periods, 2–5 choices): the selected button is raised white on a grey track. (The
   Radar's ink fill stays a Radar exception.)
4. **Tabs** (`.tabs`, switching views): underline tabs, 40 px, a 2 px ink bar under the selected one, optional `.cnt`.
5. **Data-date pills** in the page header: prices `.pill.pos` with `.dot` ("Prices to Mon 17 Nov"), broker data
   `.pill.warn` ("Broker data to Mon 9 Nov"). Every figure says the date of its data.
6. **Tables:** `.tbl` with 36 px rows (`--h-row` is 36 px in the canonical layer), sticky 36 px header, numbers right
   aligned with tabular digits, selected row `tr.on`.
7. **Numbers:** en-US digits, U+2212 minus (`−`), percent `+1.78%`, rupiah `Rp 8.15T` / `Rp 116.6B` / `Rp 4.2M`, prices
   with thousands commas (`edge-ds.js`: `pct`, `rp`, `amount`, `price`). Up = `.up` (green), down = `.down` (red).
   (The Backtest's Indonesian format is an existing exception; do not copy it.)
8. **Inputs:** focus is the Terminal's selected state: the border line goes and the soft shadow `--shadow` takes its place,
   no ring (changed by the user 2026-11-26, VISUAL-STATES: "Acuan selected state untuk tweak customize indicator adalah seperti
   terminal"; it was a grey 1 px border). A select is as wide as its longest choice where the row has room, and a choice
   that still does not fit ends in "…".
9. **Icons:** the sprite in `assets/icons.svg`, 16 px, stroke 1.6, `currentColor`. A new icon is a new `<symbol>` in
   the same style.
10. **Primary button:** ink (`.btn.primary`); a button that runs something may turn green when it can run
    (`.btn.primary.ready`). Shortcuts show as `<kbd>` inside the button (hidden on phones) with `aria-keyshortcuts`.
11. **Terminal** (`apps/edge-bff/terminal`) has its own older look and the user's rule "Terminal jangan disentuh": it is
    not a model for new pages and is not restyled, except its states: since 2026-11-26 its selected (focus) state and
    its Add-button hover are the model the Backtest and the Screener follow (VISUAL-STATES).

Also, from the pages and the spec (not up for choice):
- Language of the UI: **English** labels (wording in `static/edge-labels.js` for the shell). Plain words; a refusal or
  an empty state says what happened and what to do.
- Light and dark: every page follows the shell's theme key `edge-auth-monitor-theme` (`html.dark` /
  `[data-theme="dark"]`); check both.
- Widths: 1440, 1152, 390 and 360 px with no sideways scroll; touch targets ≥ 32 px; the page scrolls, the shell does not.
- Charts: up/down colour from the first vs last point; series colours `--c1`…`--c6` in that order; ticks in steps of
  1/2/2.5/5/10; hover = a 1 px `--text-3` line + a `.ctip` card; tile/badge hints = `.ttip`.

## How to use it

- **A new EDGE page:** follow `reference/new-page.md`; build the page from `reference/patterns.md` (page skeleton,
  header, KPI strip, cards) and `reference/components.md`; check it against `assets/showcase.html` at the four widths and
  in dark mode.
- **An HTML mockup for the user:** link or inline `spec-v1.2.css` + `edge-canonical.css` + `icons.svg`, use the
  components as written, made-up data unless the user asks for real data (real market data never goes into Git).
- **A value the system does not have:** add it as a token here first (and in the showcase), with the user's approval
  when it changes how pages look, rather than writing a literal in one page.
