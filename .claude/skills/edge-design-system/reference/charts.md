# Charts

Two technologies, chosen by the job:

| job | use | example in EDGE |
|---|---|---|
| price candles, long time series with zoom/pan, panes | **lightweight-charts 5.2.1** (npm, bundled) | Terminal `app/chart.ts:8 initChart`, Backtest `signals.ts:146`, Screener `preview.ts:221` |
| small and static charts: sparklines, lines of a few series, bars, treemap, heat cells, day boxes | **hand-made SVG** (or HTML bars) | Overview `app.ts:379 lineChart`, `:146 spark`, `model.ts:156 squarify`; Watchlist `model.ts:161 spark` |

Reference implementations of the SVG ones: `../assets/edge-ds.js` (`spark`, `trend`, `lines`, `ticks`, `hbars`,
`kofn`, `heat`, `changeColor`). A full per-chart inventory of the current pages (sizes, paddings, colours, formats) is
in the EDGE Reference Pack (`charts.md` there; not in Git because it ships market data).

## Rules for every chart
- **Colour:** direction = `--up` / `--down` (sparklines: last vs first point). Several series = `--c1`…`--c6` in order;
  the benchmark (IHSG) is `--text`, 1.4 px, dashed `4 3`. Neutral series `--text-3`. Fills at `--up-bg`/`--down-bg`.
- **Lines:** 1.6 px (sparkline 1.5), round joins; a null value lifts the pen (no line through gaps).
- **Grid:** horizontal only, `--chart-grid`; zero/base line `--chart-base`. No vertical grid in SVG charts.
- **Ticks:** "nice" steps 1/2/2.5/5/10 × 10ⁿ, 3–6 of them (`EdgeDS.ticks`); the value range padded 6%.
- **Axis labels:** `.ax` 10.5 px `--text-3`, tabular digits; y labels on the left, right-aligned 6 px from the plot;
  x labels 2, 3 or 4 dates by plot width (<170, <260, else), the first carries the year when the range crosses years.
- **Formats:** `EdgeDS.pct` (`+1.2%`), `rp` (`Rp 8.15T`), `amount` (`+414B` in bar rows), `price` (`7,925`),
  `dateLabel` (`Mon 17 Nov`). en-US, U+2212 minus.
- **Hover:** a 1 px `--text-3` vertical line (`.xh`), dots r 4 with a 2 px `--surface` ring, and a `.ctip` card
  (date first, then series sorted by value). On touch: tap shows, tap elsewhere hides.
- **Size:** fill the card width (`width:100%` + `viewBox`), fixed height (lines 200 px, sparklines 26 px, card trend
  40 px). Charts never cause sideways scroll; very wide tables/charts scroll inside their card.
- **Every chart says its data date and window** in the card header or a note under it.

## lightweight-charts setup (new pages: theme tokens, as Backtest/Screener)
```ts
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const chart = createChart(el, {
  autoSize: true,
  layout: { background: { type: ColorType.Solid, color: css('--surface') }, textColor: css('--text-3'),
            fontFamily: 'Inter,"Segoe UI",sans-serif', fontSize: 11, attributionLogo: false },
  grid: { vertLines: { visible: false }, horzLines: { visible: false } },
  rightPriceScale: { borderColor: css('--border') }, timeScale: { borderColor: css('--border'), rightOffset: 3 },
  crosshair: { mode: CrosshairMode.Normal },
  localization: { locale: 'en-US' },
});
chart.addSeries(CandlestickSeries, { upColor: css('--up'), downColor: css('--down'), borderVisible: false,
  wickUpColor: css('--up'), wickDownColor: css('--down'), priceLineVisible: false });
```
Re-read the tokens and `applyOptions` when the theme changes. Volume: a Histogram on its own scale with
`scaleMargins:{top:.82,bottom:0}`, colours `--up-bg`/`--down-bg`. The Terminal's hard-coded white theme is its own
exception (rule 11).

## Patterns
- **Sparkline in a KPI tile:** 64×26, last 30 values (`EdgeDS.spark`).
- **Trend line on a card:** fluid width × 40 px, `vector-effect:non-scaling-stroke` (`EdgeDS.trend`).
- **Multi-line comparison:** `EdgeDS.lines` + legend row (`.legend`: 8 px swatch, name, last value coloured).
- **Ranking / foreign net bars:** HTML bars (`EdgeDS.hbars`): 44 px label, track `--surface-2` 8 px, value right.
- **Treemap / heat cells:** `EdgeDS.changeColor(change, signed)` seven steps; white text on the two darkest.
- **Day counts ("k of N days", streaks):** boxes 9 px, gap 2, filled `--up` (or `--down`), empty `--sel`
  (`EdgeDS.kofn`); a one-row heat strip for a compact pane (`EdgeDS.heat`). From the user's Flow day-count proposal
  (FL12/FL26/FL29/FL35).
