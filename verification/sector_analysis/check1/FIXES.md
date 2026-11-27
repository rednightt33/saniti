# Sector Analysis check 1: the fixes, one row per finding (2026-11-27)

The five checkers' journals in this folder (runs `agents_20261127-sector-data`, `-ovrs`, `-rotpm`, `-brdt`, `-mobex`;
52 findings: 6 major, 21 minor, 25 nit), each finding used as written and keyed by run + id. Fixed on the session
branch, not deployed (the beta deploy and the move of `live` are asked with context, UD68). Each fix was tested by its
author only: a re-check of these fixes runs only with the user's approval, model and effort (AGENTS.md "Findings and
fixes" rule 8). The 50 findings with a fix are rows of `verification/records/recheck_ledger.json` (status `waiting`, the
original finding as written, key = run + id) and of `RECHECK.md`; the two not built are questions to the user below.

**Commits:** `29535145` (the page: `apps/edge-bff/sector/src`, its fixture and tests), `1ccbe90d` (`SECTOR_FORMULAS.md`
prose and `CONTRACT.md` section 5; no formula code changed, so the fingerprints and the `explained-for` line stay).
`apps/terminal-publisher/sector.py` is unchanged: D-6 is stated, D-8 is carried by the page as the contract says.

**How each was reproduced** (no beta login used): on the production build served locally with the published files the
data checker downloaded (its artifacts folder, never committed) at the shell's frame widths (1440, 1280, 1152 px minus
the 56 px rail; 390 and 360 px), light and dark; and on the fixture build. **The tests that lock them:**
`apps/edge-bff/sector/tests/check1.test.ts` (vitest, one block per run, one test per finding; every test fails on the
code before `29535145`) and `apps/edge-bff/sector/tests/look/check1.mjs` (Playwright on the fixture build, whose made-up
files now carry the real data's edge cases: `npm run build:fixture && node tests/look/check1.mjs`; on the code before
`29535145` all 29 of its steps fail; after it, 29 of 29 pass, and 27 of 27 on the real published files, the two steps
that need the fixture's hooks, BD-5 and MX-7, left out).

| Key | Sev | Verdict | Root cause | Fix (`29535145` unless named) | Test that locks it | Same mechanism, also fixed |
|---|---|---|---|---|---|---|
| `agents_20261127-sector-data/D-1` | minor | fixed | Industry rows (EDGE's traded-value index) sat under the official free-float sector rows with only "weighted index" in the legend | A note whenever industries are open: sector rows = official IDX index, industry rows = EDGE's index weighted by the file's weight label, can move unlike its sector; the industry tooltip says "not an IDX index"; the method kept (D1); `SECTOR_FORMULAS.md` section 6 with the 26 Nov examples (`1ccbe90d`) | check1.test "D-1, D-4" | the industry row tooltip |
| `agents_20261127-sector-data/D-2` | minor | fixed | 1D A/U/D were recounted from the day file's `r1d` (per market session: null for a stock that did not trade the session before) instead of the series' `adv/unch/dec` | `audOf`: 1D = `M.aud1d` (Feature 08, = the Overview: 311/204/323 on 26 Nov); the window's subtitle is the card's counts and its note names the stocks the day file cannot place; 1W/1M say their denominator | check1.test "D-2 (with brdt BD-6)" | the heatmap's "Up 1D", the A/U/D window; the wrong comment of `M.aud` |
| `agents_20261127-sector-data/D-3` | minor | fixed | "Days" showed the file's `days50/200` (the stock's own Feature 04 rows) beside "Since" and a tooltip saying "sessions" | Chosen: market sessions, the meaning of "days in status" beside "Since" and of the tooltip. `M.statusSessions`: sessions from Since to the page's date; the own count only as the lower bound of "N+"; tooltip "Market sessions …"; `SECTOR_FORMULAS.md` section 7 (INPS: 19 rows, 66 sessions) | check1.test "D-3"; look "BD-11" | the row tooltip's "for N sessions" |
| `agents_20261127-sector-data/D-4` | nit | fixed | `rate` ranks the industries among all 58; nothing said so | The industry note and the RS header tip: "an industry among all N industries"; `SECTOR_FORMULAS.md` 8.2 | check1.test "D-1, D-4" | — |
| `agents_20261127-sector-data/D-5` | nit | not built: needs the user | The names come from `IDX_Stock_Universe."Company Name"` as they are | — | — | Facts: 3 of 862 names start "Pt " (AADI "Pt Adaro Andalan Indonesia Tbk", DKHH "Pt Cipta Sarana Medika Tbk.", YUPI "Pt Yupi Indo Jelly Gum Tbk"). A correction of the source table, or a display rule on every page, is the user's decision |
| `agents_20261127-sector-data/D-6` | nit | fixed (stated) | Closes are written with 2 decimals in `sector-series`/`sector-stocks` (as the Overview series); day-file returns use the raw closes; the rounding was not stated | `SECTOR_FORMULAS.md` section 7 states it (max 0.005 per price, SINI 2 Sep 2025 2,460.00 vs 2,459.9978), below the displayed rounding; no file change (`1ccbe90d`) | `scripts/tests/test_sector_formulas_doc.py` (3 passed) | — |
| `agents_20261127-sector-data/D-7` | nit | fixed | The market rows count the stocks without an IDX-IC sector ("Other"); no note | `D.other`; the "IHSG (all)" row of the heatmap and of A/U/D tells it in its tooltip; `SECTOR_FORMULAS.md` 8.5 | check1.test "D-7" | the A/U/D market row |
| `agents_20261127-sector-data/D-8` | nit | fixed (in the page) | The file holds NULL on dates without a member return; the page used the level raw, so a return with its base or end there read "—" | `D.indLevel` = `M.carryLevels` (the contract: "the level carries") for every industry figure; `sector.py` not needed | check1.test "D-8" (Alternative Energy Equipment, 6 null dates) | every industry column of the drill-down |
| `agents_20261127-sector-ovrs/OR-1` | major | fixed | The corner names and the window's Reading assumed the horizontal axis held the longer horizon | `M.hzRead` + `mmReading`: the name follows which axis is shorter (YTD by its sessions); corners, legend, window Reading, How to read; equal lengths read neutrally ("Up on 1M only") | check1.test "OR-1"; look "OR-1" | the stock quadrant (1M/5D) and the rotation map (fixed horizons) checked: no change needed |
| `agents_20261127-sector-ovrs/OR-2` | major | fixed (also closes mobex MX-2) | 13 columns needed 829 px in 818; past that a sideways scroll without any cue | Cell padding 5→4 px (fits at 1440); a scroll cue on every scroller (`ui.ts` `scrollCues`: an edge fade; a sticky column's shadow on the left) | look "OR-2 BD-4"; look "layout …" (a scroller without a cue fails) | every table, heatmap, matrix, window table, the tab bar, the Show list, Direction and speed |
| `agents_20261127-sector-ovrs/OR-3` | minor | fixed | `renderCard` marked every scroller "kept" after any redraw, so the heatmap never went to its newest week | `data-scroll-key` (the weeks shown) and "was at the end": a new set of weeks opens on the newest | look "OR-3" | every list keeps its scroll only for the same content |
| `agents_20261127-sector-ovrs/OR-4` | minor | fixed | The stock popover had no Esc | An Esc stack (`escPush`/`escTop`), run before the date menu and a window's Esc; focus returns to the tile | look "OR-4 OR-5" | the stock quadrant's popover, the Show list, the "+ Column" popover |
| `agents_20261127-sector-ovrs/OR-5` | nit | fixed | A fixed 220 px popover | Width to content (200–320 px); a value never breaks | look "OR-4 OR-5" | the stock quadrant's popover (same element) |
| `agents_20261127-sector-ovrs/OR-6` | minor | fixed (also closes brdt BD-7) | The popover printed first–last in "trading days", the card base–last in "sessions" | `checkRange` prints the card's own label (`M.spanLabel`), with a line on the base close; the weekly heatmap prints its weeks; a level chart (breadth) its first session | check1.test "OR-6"; model.test; look "RP-1 OR-6 BD-7" | every Custom: Cumulative return, stock lines, weekly heatmap, pair matrix, pair ratio, beta, breadth |
| `agents_20261127-sector-ovrs/OR-7` | nit | fixed | Card titles were cut with an ellipsis | Titles wrap | look "layout …" (no ellipsis on a title) | every card title |
| `agents_20261127-sector-ovrs/OR-8` | nit | fixed | 8 week columns of 30 px and a 78 px name column did not fit 322 px | `fitWeeks`: a narrower name and week column when needed; otherwise whole columns with the sticky column's shadow | look "OR-8 OR-12" | a Custom range of more weeks |
| `agents_20261127-sector-ovrs/OR-9` | nit | fixed | Wording | "returned −11.3%"; the rank's window named; Rank change's note plain | check1.test "OR-9"; model.test | no other "fell/rose" + signed value left |
| `agents_20261127-sector-ovrs/OR-10` | nit | fixed | Six chart colours for 11 lines | Lines past the sixth colour are dashed, their legend swatch too, and the legend says so | check1.test "OR-10" | — |
| `agents_20261127-sector-ovrs/OR-11` | nit | fixed (also closes rotpm RP-11) | A stacked window gave the card's table its whole height | A table card takes at most 48% of a stacked window and scrolls; the detail gets the rest | look "OR-11 RP-11" (2 rows before, 7 after) | every stacked table window (Beta, Rotation detail, Breadth tables, Stretched pairs) |
| `agents_20261127-sector-ovrs/OR-12` | nit | fixed | Long legends on the bottom row at 1440 | "the strongest sector … until you lock one" moved to the subtitle; a dashed swatch for the index line; the weekly legend shortened | look "OR-8 OR-12" | the market map's legend |
| `agents_20261127-sector-rotpm/RP-1` | major | fixed | `checkRange` silently clamped a start before the data; `span()` then fell back to 3M/120D under a selected Custom and printed "C" | Refused as the Overview's ("Pick dates from … to …"); a stored range is clamped with a note on the card, or the card's default with a note (`customSpan`); `plabel` never "C" | check1.test "RP-1", "RP-1, the same mechanism in Rank change"; model.test; look "RP-1 OR-6 BD-7" | all 7 Custom ranges, Rank change's compare date, a map date before the strip |
| `agents_20261127-sector-rotpm/RP-2` | minor | fixed | Row height capped by the column width (10 px rows) | Rows share the card's height (16–28 px); "in phase" heads its column; the timeline's dates only when the IHSG strip is hidden | look "RP-2" | — |
| `agents_20261127-sector-rotpm/RP-3` | minor | fixed | Rotation detail used the page's date | It follows the map date and says so; the stock quadrant (the day's returns) says "as of" the page's date | look "RP-3" | — |
| `agents_20261127-sector-rotpm/RP-4` | minor | fixed | Matrix rows at least 22 px; 36 px rows of the top 7 | Matrix rows at least 18 px; pair rows 30 px; a bottom cue on any list that scrolls | look "RP-4" | every vertical list |
| `agents_20261127-sector-rotpm/RP-5` | minor | fixed | The legend text was set after the draw (it wrapped, the chart overflowed its box); names under the dots; a 2–98% range that is the outlier itself | A legend known only after a draw keeps its last text (`footNow`/`footSet`) and a chart is drawn again when its box changes; names drawn last with a halo, labels keep clear; `M.axisRange` (quartiles ± 3 IQR) | check1.test "RP-5"; look "RP-5", "layout …" | the Momentum and rotation map legends; breadth's range label |
| `agents_20261127-sector-rotpm/RP-6` | minor | fixed | Dates without a year; the hover and the click computed the week differently | `M.dateIn` (the year when not the page's); one `target()` for hover and click, the tooltip names the date set | check1.test "RP-6" | every date of the page: Rank change, weekly heatmap, stock lines, rotation cards, pair ratio marker, Breadth, header |
| `agents_20261127-sector-rotpm/RP-7` | nit | fixed | Correlation ordered by the hidden spread period; its tooltip showed that spread; negatives unfilled | Ordered by the shown window's average correlation; the tooltip shows the correlation only; negatives in red; the legend says so | look "RP-7 RP-8" | — |
| `agents_20261127-sector-rotpm/RP-8` | nit | fixed | A bare dash | The dash carries its reason; the header tip says when | look "RP-7 RP-8" | brdt BD-11 |
| `agents_20261127-sector-rotpm/RP-9` | nit | fixed | Heading 225° was "Weakening" | Headings renamed ("Both up", "Both down"); none is a quadrant's name | check1.test "RP-9"; model.test | — |
| `agents_20261127-sector-rotpm/RP-10` | nit | fixed | A title-only span | A button with a read-out on hover, tap and focus; not locked in the example | look "RP-10" | the industry rows' tooltip (was a title) |
| `agents_20261127-sector-rotpm/RP-11` | nit | fixed with another key: ovrs/OR-11 (and its own sticky-cell part) | The same stacked window; a sticky first cell kept its own background on hover | The window split of OR-11; the sticky cell follows the row's hover | look "OR-11 RP-11" | the drill-down, heatmap table and beta sticky cells |
| `agents_20261127-sector-brdt/BD-1` | major | fixed | The chart read its box before the legend's range text arrived (and before the font), and redrew only on a width change | The range label printed before the draw; a chart box that changes size, or a chart taller than its box, is drawn again (bounded) | look "layout 1280 …" (a chart taller than its box fails) | the stock quadrant (RP-5), the Momentum and rotation map legends |
| `agents_20261127-sector-brdt/BD-2` | major | fixed (also closes BD-3, mobex MX-1) | A fixed table of % columns with an ellipsis | The stock detail sizes to its content, no ellipsis; narrower than its card it scrolls with a cue | look "layout …" (a cut cell fails) | the heatmap table, the drill-down's industry names |
| `agents_20261127-sector-brdt/BD-3` | minor | fixed with another key: brdt/BD-2 | Same | Same | look "layout 1440 …" | — |
| `agents_20261127-sector-brdt/BD-4` | minor | fixed | A minimum width of 560 px | 480 px, a 100 px name column: fits at 1152; a cue when narrower | look "OR-2 BD-4" | — |
| `agents_20261127-sector-brdt/BD-5` | minor | fixed | No sequence guard | `M.lastWins` in the date pick | check1.test "BD-5"; look "BD-5" | — |
| `agents_20261127-sector-brdt/BD-6` | minor | fixed with another key: data/D-2 | Same as D-2 | Same as D-2; 1W/1M cells and rows name who is not counted | check1.test "D-2 (with brdt BD-6)" | — |
| `agents_20261127-sector-brdt/BD-7` | minor | fixed with another key: ovrs/OR-6 (its level-chart part here) | The breadth line (a level) started its Custom range at the base session | Its Custom range shows from its first session; a preset of n sessions shows n; popover = card | check1.test "OR-6"; look "RP-1 OR-6 BD-7" | — |
| `agents_20261127-sector-brdt/BD-8` | minor | fixed | An absolute popover in a clipping card, 340 px high | Placed in the viewport down to its bottom, a cue, Esc closes it | look "BD-8" | the "+ Column" popover's Esc |
| `agents_20261127-sector-brdt/BD-9` | nit | fixed (also closes mobex MX-6) | No key handler | `M.menuStep`: arrows, Home, End | check1.test "BD-9"; look "BD-9 BD-10" | — |
| `agents_20261127-sector-brdt/BD-10` | nit | fixed | The date was not in the state | `S.date` in the address, opened on load, dropped when no longer listed | check1.test "BD-10"; look "BD-9 BD-10" | — |
| `agents_20261127-sector-brdt/BD-11` | nit | fixed | Bare dashes | Each dash carries its reason ("No EMA200 yet", "older than the 300 sessions"; "N+" explained) | look "BD-11" | Sector × horizon, drill-down, heatmap table, Δ beta, every window table's dash |
| `agents_20261127-sector-brdt/BD-12` | nit | fixed | `pct` drops the sign of a value that rounds to zero | `M.pctSigned` for distances | check1.test "BD-12" | the Breadth by sector window and its example sentence |
| `agents_20261127-sector-mobex/MX-1` | major | fixed with another key: brdt/BD-2 | Same as BD-2 | Same as BD-2 | look "layout 390/360 …" | — |
| `agents_20261127-sector-mobex/MX-2` | minor | fixed with another key: ovrs/OR-2 | Same as OR-2 | Same as OR-2 | look "layout 390/360 …" | — |
| `agents_20261127-sector-mobex/MX-3` | minor | fixed | The tab bar has no scrollbar and no cue | The scroll cue on the tab bar; the chosen tab scrolled into view | look "layout 390/360 …" | — |
| `agents_20261127-sector-mobex/MX-4` | minor | fixed in part; the rest needs the user | Small controls of the design system | On a touch screen: 44 px hit areas for the expand buttons, drill-down chevrons, the window's close button, and a 28 px hit circle for the rotation map's dots, with no visual change | none automated (CSS under `pointer: coarse`) | Left as they are, needing the user: the segmented controls (22 px high), legend toggles (24 px), sector name buttons, matrix heads and the quadrant's stock dots: the shared EDGE component sizes (the Overview's too), a design value |
| `agents_20261127-sector-mobex/MX-5` | minor | the page's part fixed; the shared tokens need the user | End labels in the series colour; white counts on `--up`/`--down`; white ink on light heat cells | End labels mix their colour with the text colour (2.67:1 → 4.5:1 or more); dark ink on the A/U/D bars (3.57/3.90 → 5.0/4.6); heat and correlation ink per theme | check1.test "MX-5 (the page's own part)"; a contrast probe of every text at 390 px | Not built: light `--text-3` #8f8f8f on white = 3.23:1 (every EDGE page's grey labels), and the tag pairs `--red`/`--red-bg` 4.39, `--green`/`--green-bg` 4.46, `--blue`/`--blue-bg` 3.81–4.08: shared design-system tokens |
| `agents_20261127-sector-mobex/MX-6` | nit | fixed with another key: brdt/BD-9 | Same as BD-9 | Same as BD-9 | check1.test "BD-9"; look "BD-9 BD-10" | — |
| `agents_20261127-sector-mobex/MX-7` | nit | fixed | The header buttons were live before any data | Off until the data is in and while only an error shows ("No data") | look "MX-7" | — |
| `agents_20261127-sector-mobex/MX-8` | nit | fixed | Mouse wording on a phone, the map named in a window without one, a fixed footer | Touch wording ("Tap …"); a window's own hint; a phone window scrolls as one under a sticky title that wraps | look "MX-8" | Direction and speed, the Breadth, Momentum and rotation legends, Cumulative return's hint |
| `agents_20261127-sector-mobex/MX-9` | nit | not built: needs the user | Δ, σ and β are Greek glyphs: the browser loads Inter's Greek subset (19 KB) on first use | — | — | Facts: about 20 labels use Δ ("Δ 4W", "Δ beta", "Δ EMA50 1W"), σ ("Band (σ)") and β; spelling them out changes the prototype's wording; keeping them costs 19 KB once, cached for every EDGE page |

## Counts

| Verdict | Keys |
|---|---|
| fixed | 41 (D-6 by a stated rounding, D-8 in the page) |
| fixed with another key | 7 (brdt BD-6 with data D-2; brdt BD-7 with ovrs OR-6; mobex MX-2 with ovrs OR-2; rotpm RP-11 with ovrs OR-11; brdt BD-3 and mobex MX-1 with brdt BD-2; mobex MX-6 with brdt BD-9) |
| fixed in part, the rest needs the user | 2 (MX-4, MX-5) |
| cannot reproduce | 0 |
| not built: needs the user | 2 (D-5, MX-9) |

Of the 6 majors all 6 are fixed (OR-1, OR-2, RP-1, BD-1, BD-2; MX-1 with BD-2). Total 52.

## Questions to the user (for the register, rule 6)

1. **D-5, company names "Pt …"** (3 of 862 names, the source table `IDX_Stock_Universe`): correct the source rows, add a
   display rule on every page, or leave them.
2. **MX-4, touch targets**: the design system's small controls (segmented 22 px, toggles 24 px, name buttons 20 px) are
   the same on the Overview; make every EDGE page's controls 32-44 px on touch (a design-system change), or keep them.
3. **MX-5, contrast**: light `--text-3` (3.23:1 on white) and the tag colour pairs (3.81-4.46:1) are shared tokens; a
   darker grey or tag text changes every EDGE page.
4. **MX-9, Greek glyphs**: spell out Δ/σ/β (a wording change of the user's prototype) or keep them (19 KB once).
