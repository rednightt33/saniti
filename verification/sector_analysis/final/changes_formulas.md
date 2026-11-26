# Sector Analysis prototype: first version → final version

Compared files:
- first version: `sector/logic.js` (1,621 lines), the markup and CSS inside `sector/app_overview.txt`;
- final version: `sector/v2/logic.js` (1,729 lines), `v2/markup.html`, `v2/css.css` / `v2/app_overview.txt`.

`window.SX` is byte-identical in both. Line numbers: `v1 L…` = first version, `L…` alone = final version.

## 1. Verdict

| Area | Changed? |
|---|---|
| Data read (SX fields) | **No.** The same fields are read, with the same reference counts. |
| Data needed beyond SX | **No new need.** |
| Any computed value, formula, window or threshold | **No.** `ret`, `rr`, `rankAt`, `rrg`/`RRGS`, `members`, `ovxRet`/`ovxPath`/`ovxResolve`, `rotRows`, `rotCmp`, the `pq*` helpers, `zOf`, `brSeries`, `brDum`, the `rsD` ratings and tags, and every `fwd*` computation are unchanged. |
| Periods, options, defaults | **No.** Every `SEG` keeps its options and default; every table keeps its default order. |
| GAP list | **Unchanged in data** (G1-G14 all open). Three fake-data disclaimers disappeared from the windows (W4). |
| Sorting | **Changed:** one shared multi-column sort everywhere; four tables became sortable or multi-level for the first time (section 3). |
| Selection and interaction | **Changed:** one-click Rotation pick, ticker pick in `rotC`, chart markers from detail rows, legend hide/show, row clicks in windows (section 4). |
| Wording | **Changed:** most subtitles, the window footers (`FW_READ`), and the market-map subtitle in the markup (section 5). One new wording/formula mismatch (I8) and three misleading footers (W1, W2, W4). |
| Windows | **Changed:** auto-size, backdrop close, the pin button hidden, hover date tags (section 4). |

## 2. Inputs, formulas, periods, thresholds: re-checked one by one

- **SX fields read** (counted in both files):
  - `DY.date`, `DY.stocks`, `MT.market`, `MT.stocks`, `MT.broker_through`;
  - `S.sector`, `S.index`, `S.above_ema50`, `S.above_ema200`, `S.dates`;
  - `st.{i, r1d, r5d, r1m, size, above_ema50, above_ema200, fnet_5d}`;
  - `SX.ind`.

  Same set, same counts. Still unused: `series.breadth_n`, `series.flow`, `meta.dates`, `day.market`, `day.index`,
  `day.volatility`, `day.breadth`, `day.intraday`, `day.stocks.close` and `fnet_1d/1m/3m`.
- **Options and defaults, unchanged:**

  | Card | Options (default first or marked) |
  |---|---|
  | rcCard | 1M/3M/YTD/Custom (3M) |
  | mmCard | x = 3M, y = 1M |
  | hxCard | 1D…1Y, default sort 1M |
  | rsA | 3/5/10 (5); vs IHSG / Absolute |
  | rsB | 5/10/21/Custom (5) |
  | rsW | 4W/8W/Custom (8W) |
  | rsL | 1M/3M/YTD/Custom (3M) |
  | rotA | tail 4/8/12 W (4) |
  | rotD | 1/2/4 W (1) |
  | rotB | previous 5/10/21 (5) |
  | rotC | IHSG / sector index |
  | pmM | 5/21/63/Custom (21); corr 20/60/120 (60) |
  | pmR | 3M/6M/1Y/Custom (6M), MA 20/50 (50) |
  | pmT | 20/60/120/250/Custom (120); IHSG/LQ45 |
  | pmS | 3D/1W/1M (1M); Both/ahead/behind; top 7/all |
  | brH | 3M/6M/1Y/Custom (6M), EMA50/200 |
  | brN | 1D/1W/1M |
  | brA | % > EMA50 / % > IHSG 5D / % > 0 |
  | brT | % / count |
  | brD | All / Above / Below |
- **Thresholds, unchanged:**
  - rank change ±3 places (rsB);
  - momentum tag ±0.5 pp (rsD);
  - RRG 100/100 (rotA);
  - band ±2σ (pmR);
  - |z| ≥ 2 and corr ≥ 0.7 (dead pmB);
  - breadth zones 70 % / 30 % (brH);
  - 50 % colour centre;
  - concentration 60 % (dead brC);
  - thrust 30 → 60 % in 10 sessions (dead brB);
  - `brT` tags (computed, still not shown).
- **Fakes, unchanged:**
  - `rsL` stock paths (L316-320);
  - `rsD` industry 3M/YTD/Δ4W/RRG (L289), industry rows still never displayed (`open` empty, L290);
  - `brSeries` (L751-762);
  - `brDum` (L771-779);
  - `fwdPMT` β/corr (L1549);
  - `fwdBRN` close/volume (L1588-1589);
  - `brM` "> EMA20" = `r1m > 0`.
- **Correction to the first `formulas.md`:** `rsC` (Acceleration and streak) is **hidden** by the stylesheet rule
  `#rsC{display:none}` in **both** versions. The first document listed it as drawn.

## 3. Sorting (shared multi-column sort, L563-576)

New helpers `msTh`, `msCmp`, `msSort`, `msNote`, `msClick`, `msWire`, `msKeep`:
- A click adds the column as the next level, up to 3 levels; the oldest drops.
- A second click reverses that level; a third click removes it.
- With no level chosen, the table shows its default order with a faint arrow on the default column.
- **Nulls always sort last.** In v1, `?? -1e9` put them last when descending and first when ascending.
- A "Sorted by … · Clear sort" note appears at 2 or more levels. It replaces "Sorted by … · Reset" in the subtitle.

| Table | First version | Final version | Default (unchanged) |
|---|---|---|---|
| hxCard heatmap | one column (`OVX.hk`, `OVX.hd`) | up to 3 levels (`OVX.hs`, **saved in `localStorage`**) | 1M descending |
| rsW weekly grid | not sortable (fixed by `rr(s,20)`) | sector name and **every week column** sortable (`TT.rsWS`) | `rr(s,20)` descending |
| rsD drill-down | one column (`TT.rsDk`, `TT.rsDd`) | up to 3 levels (`TT.rsSK`) | RS rating descending |
| rotB detail | 3 levels (own code) | shared sort (`TT.rotSort`) | `dm` descending |
| pmM matrix rows | one column sector (`TT.pqSC`) | up to 3 column sectors (`TT.pqSK`); the column's own sector last | spread-period return descending |
| pmT, pmS, brM | 3 levels, default pre-set as a level | shared sort; the default shown, not a level | β, |spread|, > EMA50 descending |
| brT heatmap table | one column (`TT.btK`, `TT.btD`); window extra columns not sortable | up to 3 levels (`TT.btSK`); **window Δ columns sortable** | > EMA50 descending |
| brD stock detail | one column (`TT.bdK`, `TT.bdD`) | up to 3 levels (`TT.bdSK`) | distance from the chosen EMA, descending |
| Every window detail table (`fwDetail`) | one column (`w.ds`) | up to 3 levels (`w.dsk`) | the table's `sort` |

## 4. Selection, interaction and windows

| Where | Change | Lines |
|---|---|---|
| Rotation (RRG dots, timeline names and rows, `fwdROTA` and `fwdROTB` rows) | `rotPick`: one click = that sector only. It replaces a multi-pick from Rotation detail; a second click on the only selected sector clears it. v1 toggled the page lock (`lockT`) | L183, L419, L460-461, L1505, L1511 |
| rotC | **click a dot to select the ticker** (`TT.rqT`; v1: only from the window list). The selected dot gets a halo and its own label | L539-549 |
| rcCard | legend **IHSG button** hides or shows the IHSG line (`OVX.ihOff`, not saved); a hovered or pinned line keeps its colour | L997-999, L1061-1062 |
| brH | legend items are buttons: **hide or show** any line, the IHSG price included (`TT.bhHid`) | L812, L815, L819, L851-854 |
| brH ← `fwdBRH` | a row click marks the date on the chart (`TT.bhMk`) | L854, L1567 |
| pmR ← `fwdPMR` | a row click marks the date on the chart with its ratio (`TT.prMk`) | L635-636, L1543 |
| mkCard ← `fwdMK` | a row click highlights one industry on the map (`OVX.mkSub`, cleared when the sector changes) | L1207-1208, L1461 |
| `fwdRC`, `fwdMM`, `fwdHX` | a row click pins the sector | L1434, L1443, L1452 |
| `fwdPMM`, `fwdPMS` | a row click opens the pair (`pa`, `pb` fields added) | L1530-1533, L1557-1560 |
| `fwdBRT` | a row click selects the sector for the Breadth tab | L1574 |
| Highlights | rsW pinned cells; pmM pinned row; brT `has`; scatter halo; RRG pinned halo (r 9). The timeline's pinned-row outline and the dark ring on unlabelled dots (RRG, scatter, rotC) were removed | various |
| Line charts | the hovered date shown in a tag on the x-axis (`xTag`): Cumulative Return, rsL, the IHSG strip, pmR, brH | L1642-1648 |
| Windows | auto-sized to their content (`fwFit`); a backdrop click closes the top window (`fwBackdrop`); **the pin button is hidden** (`.fw-pin{display:none!important}`), so every window closes on a tab switch; rotB and rotC legends hidden inside windows | L1649-1663, L1708-1711, CSS |
| Page code | `$` / `$$` skip elements inside a floating window while no window is running (L6-8): a fix so page code never edits a window's copy of a card | L6-8 |
| Subtitles | a cut-off subtitle shows in full on hover | L1326 |

## 5. Wording

### 5.1 Card subtitles and legends

| Card | First version | Final version |
|---|---|---|
| rsA | "Sector return − IHSG return, last n sessions" / "Sector index return, last n sessions · dashed line = IHSG" | "… over the last n sessions (pp)" / "Sector index return over the last n sessions · dashed line = IHSG" |
| rsW | "Sector return − IHSG return per week (pp)" | "Sector − IHSG return per 5-day week (pp)" |
| rsD | "Click a sector to see its stocks · click a column to sort" | "Return, return vs IHSG and RS rating (1–99 rank of 1M vs IHSG) per sector and subsector". Industry rows are still not shown (W3) |
| rsL | "Top 10 by trading value, cumulative" | "Return since <start date> · top 10 traded" |
| rotA | "vs IHSG · <date> (latest) · tail nW"; timeline "Quadrant each week …"; y-axis "RS-Momentum ↑"; footer "n labels hidden (dark ring) · hover a dot for values" | "RS-Ratio × RS-Mom vs IHSG · <date> · tail nW"; "RRG quadrant of each sector per week …"; rotated "RS-Momentum →"; "Click a dot to pin the sector · hover a dot for names not shown" |
| rotB | "Sorted by … · Reset" or "Click headers to sort · each click adds a level" | "Quadrant now vs <P> ago · speed = RRG distance moved in <P> sessions": **wrong for P = 10/21**, speed is still 5 sessions (I8) |
| rotC | "1M × 5D vs <bench> · N stocks"; "n labels hidden (ring)" | "Dot = stock · across = 1M − <bench>, up = 5D − <bench> (pp) · size = value"; "point at a dot for names not shown" |
| mmCard footer | "n labels hidden (dark ring); point at a dot for its name." | "Point at a dot for names not shown." |
| mkCard (markup) | "Grouped by subsector" | "Tile size = 20D avg trading value · colour = 5D return − IHSG · grouped by subsector" |
| pmM legend | "click a column name to sort rows by it" | "click column names to sort rows (each adds a level)" |
| pmR | "Pair Ratio · line up = A ahead of B" | "A ÷ B, start = 100 · line up = A ahead" |
| pmT | "Sorted by …" or "Click headers to sort …" | "β = sector move per 1% <BM> move, from <W> daily returns · Corr = how closely they move" |
| pmS | "Sorted by …" or "Widest spread between two sectors" | "Pairs ranked by return gap, first − second sector over <H> (pp)". The visible text now matches the code; the code comment (L671) still says "|z|" (I6) |
| brH | "% of <x> stocks above <EMA>" | "% of <x> stocks closing above their <EMA> · IHSG price on the right" |
| brT | "Green above 50%, red below · click a header to sort" | "% of stocks up 1D/1W/1M, above EMA50/200 · green ≥ 50%" |
| brD | "<who> · x of N above <EMA>" | "Close vs EMAs · <who>: x of N above <EMA>" |
| brM (not drawn) | "Sorted by …" | fixed text |

### 5.2 Window footers (`FW_READ`, L1328-1368)

- **Mechanism:** 20 windows now show "How to read · <text> Example · <a sentence from the first non-IHSG row>". It
  **replaces** the old `D.note` (L1618-1623).
- Some notes were edited in v2 ("Click a row to select …", added to `fwdMM`, `fwdHX`, `fwdMK`, `fwdPMM`, `fwdPMR`,
  `fwdPMS`, `fwdBRH`). Those windows all have a `FW_READ` entry, so the edited notes are never shown.
- Readings to fix before release:
  - **W1 `rsB`:** "Rank 1 = highest 5D return vs IHSG … Places gained = last week's rank − this week's rank". Both
    are hard-coded, while the card offers n = 3/5/10 and compare 5/10/21/Custom. The example quotes columns `p3` → `p4`:
    - k = 10: E−5 → E, while the places are counted from E−10;
    - k = 21: E−10 → E−5, while the places count from E−21.
  - **W2 `rsA`:** the example always uses the 5D column; "rank #k" is the rank on the chosen window.
  - **W4, fake data no longer flagged:**
    - `rsL`: "the chart paths are illustrative" is gone;
    - `brA`: "(illustrative)" is gone, and the footer explains the fake distance as real;
    - `pmT`: "Stock β and correlation are illustrative" is gone; the footer explains the fake stock β as real ("when
      the benchmark moves 1%, X tends to move about 1.12%").
    - Only `brN` still says "Close and volume are illustrative".
  - **`brT`:** the example quotes Δ 1W, which is the fake `brSeries` value for a sector row (G4).

## 6. GAP and inconsistency status (v1 → v2)

| Id | First version | Final version |
|---|---|---|
| G1 rsL stock paths | fake, labelled in the window | **fake, label gone** |
| G2 rsD industry history | fake; rows not shown | unchanged; subtitle now claims "and subsector" (W3) |
| G3a `ind` not published | open | open |
| G3b weights = traded value | open | open (no market cap in the database, `formulas_v2.md` §11) |
| G4 sector breadth history | fake | unchanged; the brT example now quotes it |
| G5 EMA20 | illustrative | unchanged (Feature 04 has no `ema_20`) |
| G6 brD distances, days | fake | unchanged |
| G7 fwdBRA distance | fake, labelled | **fake, label gone** |
| G8 fwdBRN close, volume | fake, labelled | fake, still labelled |
| G9 fwdPMT β/corr | fake, labelled | **fake, label gone, explained as real** |
| G10 date button | latest only | unchanged |
| G11 Screener | no destination | unchanged |
| G12 CSV | no handler (hidden button) | unchanged |
| G13, G14 (dead cards) | open | unchanged |
| I1 20 vs 21 sessions | open | unchanged |
| I2 1Y = 250 vs 252 | open | unchanged |
| I3 Custom base and cap | open | unchanged |
| I4 breadth denominators and nulls | open | unchanged |
| I5 legacy YTD → 60D | open | unchanged |
| I6 pmS "z" | comment wrong | the visible subtitle is right now; only the comment is wrong |
| I7 broker date lag | open | unchanged (no broker round since 2026-11-09) |
| **I8** | — | **new:** rotB subtitle "speed … in P sessions" vs the 5-session speed |
| **W1-W4** | — | **new:** `FW_READ` wording (above) |

## 7. Data needs

No new data need. The data-source mapping for the build (every need → table or function) is in `formulas_v2.md`
section 11. Only two needs fall outside the sources already used: an **EMA20** (Feature 04 has only `sma_20`), and
**market-cap weights** (no market cap or shares outstanding in the database) if they are wanted.
