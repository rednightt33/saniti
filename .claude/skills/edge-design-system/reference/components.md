# Components (canonical)

Every snippet is shown live in `../assets/showcase.html`. Classes come from `spec-v1.2.css` (spec) or
`edge-canonical.css` (canonical). Icons: `<svg class="ic ic-sm"><use href="#i-NAME"/></svg>` (sprite `icons.svg`).
Where EDGE's pages already implement a component, the source is named so you can read a working example.

## Page header — title, purpose, data dates, actions
```html
<header class="head">
  <div><h1>Watchlist</h1><p>One card per stock: price, 30-session line and the first 4 indicators.</p></div>
  <div class="actions">
    <span class="pill pos"><span class="dot"></span>Prices to Mon 17 Nov</span>
    <span class="pill warn"><span class="dot"></span>Broker data to Mon 9 Nov</span>
    <button class="btn" type="button"><svg class="ic ic-sm"><use href="#i-cols"/></svg>Indicators</button>
    <button class="btn primary" type="button" aria-keyshortcuts="Alt+A" title="Add stocks (Alt+A)"><svg class="ic ic-sm"><use href="#i-plus"/></svg>Add ticker<kbd>Alt+A</kbd></button>
  </div>
</header>
```
h1 22 px/600 (spec), purpose line `--text-3`. Pills say the date of the data shown (decision 5). Example: Overview, Watchlist.

## Card and card header
```html
<div class="card">
  <div class="card-h">
    <div class="ttl"><h3>Sector Performance</h3><span class="ttl-s">Cumulative return vs IHSG</span></div>
    <span class="pctl"><span class="plab">Period</span>
      <div class="seg sm" role="group" aria-label="Sector Performance period">
        <button type="button">20D</button><button type="button" class="on" aria-pressed="true">60D</button><button type="button">YTD</button>
      </div></span>
  </div>
  <div class="card-b">…</div>
</div>
```
Card: 1 px `--border`, radius 12, no shadow. Title 14 px/600; subtitle 12 px `--text-3`. A one-line header without a
subtitle: `<h3>…</h3><span class="grow"></span>…controls`. A grey hint at the right: `<span class="hint">`.
Example: `apps/edge-bff/overview/index.html` (Sector Performance, Foreign Flow).

## KPI tile (+ sparkline)
```html
<div class="kpis">
  <div class="card ktile" tabindex="0">
    <div class="lb"><span>Turnover (1D)</span><span class="pill warn">9 Nov</span></div>
    <div class="ksub">Value traded · Regular</div>
    <div><div class="v">Rp 5.95T</div><div class="s"><b>0.61×</b> 20D average</div></div>
    <!-- EdgeDS.spark(values) → <svg class="sp" width="64" height="26">…</svg> -->
  </div>
</div>
```
Value 18 px/600, change line 12 px, sparkline bottom right (up/down by first vs last; a neutral series uses
`--text-3`). Breadth adds `<div class="adbar"><i style="flex:564;background:var(--up)"></i>…</div>`. A small label–value
box inside a card is the spec `.kpi` (`<div class="kpi"><span>Net 5D</span><b>+38.4B</b></div>`).
Example: Overview KPI strip (`overview/src/app.ts`).

## Segmented control (2–5 choices, periods)
```html
<div class="seg" role="group" aria-label="View"><button type="button">Table</button><button type="button" class="on" aria-pressed="true">Cards</button></div>
```
`.seg.sm` (22 px) inside card headers. The selected button is raised white on the grey track (decision 3). On a touch
screen each button takes 44 px of height to a tap (decision 14), its width stopping at its neighbours.

## Tabs (switching views or lists)
```html
<div class="tabs" role="tablist" aria-label="Watchlists">
  <button role="tab" aria-selected="true">Core<span class="cnt">10</span></button>
  <button role="tab" aria-selected="false">Banks<span class="cnt">2</span></button>
</div>
```
Underline tabs, 40 px, ink bar 2 px (decision 4); scroll sideways on a phone. Example: Watchlist list tabs.

## Filter toggle, switch
```html
<button class="tog on" aria-pressed="true" type="button"><svg class="ic ic-sm"><use href="#i-radar"/></svg>Radar</button>
<button class="switch on" role="switch" aria-checked="true" aria-label="Near misses" type="button"></button>
```
A toggle that filters what is shown answers with a toast ("Filtered: only stocks in Radar (9 Nov) · 2 of 3").

## Buttons
| use | markup |
|---|---|
| main action of the page | `<button class="btn primary">Open Terminal</button>` |
| runs something, ready to run | `<button class="btn primary ready">Screen now<kbd>Alt+S</kbd></button>` |
| secondary | `<button class="btn">Save screen</button>` |
| quiet | `<button class="btn ghost">Reset</button>` |
| destructive | `<button class="btn danger">Delete list</button>` (confirmed by a dialog that names the thing) |
| small | add `sm` (28 px) |
| icon only | `<button class="iconbtn" aria-label="More"><svg class="ic"><use href="#i-more"/></svg></button>` (`iconbtn sm` 26 px) |
| opens a menu | `aria-haspopup="menu" aria-expanded="false"`; while open it gets the `--sel` look automatically |
The spec's button catalog (`.btn.solid/.soft/.outline` × `tone-*`) exists for special cases; prefer the table above.

## Pills and badges
```html
<span class="pill">Neutral</span> <span class="pill pos">+2.26%</span> <span class="pill neg">−1.33%</span>
<span class="pill warn">9 Nov</span> <span class="pill info"><svg class="ic ic-sm"><use href="#i-cal"/></svg>RUPS 17 Nov</span>
<span class="pill" style="background:var(--text);color:var(--surface)"><svg class="ic ic-sm"><use href="#i-radar"/></svg>Radar S6</span>
```
Corporate action = `.pill.info` with the calendar icon; Radar hit = ink pill (user 2026-11-16). 20 px high, 11 px/600.
A tag's text on its tint is the tag ink, 4.5:1 (decision 12): `.pill.pos/.neg/.warn/.info` take it; a page's own tag
writes `background:var(--green-bg);color:var(--green-tag)` (never `color:var(--green)` on the tint).

## Fields
```html
<label class="field"><span>List name</span><input class="inp" value="Core"></label>
<input class="inp custom" value="25">   <!-- a parameter changed from its default: blue text -->
```
Focus: the border line goes and the soft shadow `--shadow` shows, no ring: the Terminal's selected state (decision 8, changed 2026-11-26), by mouse and by Tab, a select opened with the mouse included (decision 13). Errors under the field: `<small class="ferr">` in `--red`, naming the fix.

## Focus ring (every control that is not a field)
```css
.my-row:focus-visible{outline:2px solid var(--focus-ring);outline-offset:-2px}   /* or box-shadow:inset 0 0 0 2px var(--focus-ring) */
```
Keyboard only, neutral grey (decision 13): `--focus-ring` is `--text-3`, transparent while the last input was a mouse, a
pen or a finger (`data-modality="pointer"` on `<html>`, written by `apps/edge-bff/shared/focus-modality.ts`, which every
page entry imports). Never `var(--blue)` in a focus rule. Wrong: `.row:focus-visible{outline:2px solid var(--blue)}` (a blue
ring after every click that gives the row the focus back).

## Touch hit area (a page's own small control)
```html
<button class="chip hit" type="button">Banks</button>   <!-- 44 × 44 px to a tap on a touch screen, nothing drawn -->
<div class="chips" style="--hit-y:4px">…</div>          <!-- a row 8 px apart: each area stops halfway -->
```
Decision 14: `.hit` (and the shared small controls) get an invisible `::after` box under `pointer: coarse`; it never
moves the layout. A control whose `::after` draws something takes the area on a wrapper instead.

## Table
```html
<div class="card"><div class="tbl-wrap"><table class="tbl">
  <thead><tr><th>Stock</th><th>Last</th><th>1D</th><th class="l">Signal</th></tr></thead>
  <tbody><tr class="on"><td><span class="sym">BETQ</span><span class="sub">PT Bank Beta Sejahtera Tbk</span></td><td>9,150</td><td class="down">−0.20%</td><td class="l"><span class="pill pos">Accumulation</span></td></tr></tbody>
</table></div></div>
```
36 px rows (decision 6), right-aligned numbers, `.l` for a left column, sortable header `th.sort`, missing value
`td.miss` (hatched) or `—`. Selected row `tr.on`. Pagination row: "Showing 1–25 of 297", rows-per-page select, pager.

## Menu (popover)
```html
<div class="pop" role="menu"><div class="menu-title">List</div>
  <button class="menu-item" role="menuitem">Rename</button>
  <button class="menu-item" role="menuitem" style="color:var(--red)">Delete list</button></div>
```
Positioned under its trigger; Escape and a click outside close it; arrow keys move between items.

## Dialog
```html
<div class="backdrop"><div class="dialog" role="dialog" aria-modal="true" aria-label="Delete list">
  <div class="dialog-head"><strong>Delete “Banks”?</strong><span class="note">2 stocks. You can undo for 8 seconds.</span></div>
  <div class="dialog-body">…</div>
  <div class="dialog-foot"><button class="btn">Cancel</button><button class="btn danger">Delete list</button></div>
</div></div>
```
Focus stays inside (Tab cycles), Escape closes, the first field gets focus on desktop only (no keyboard pop-up on phones).

## Toast
`<div class="toast" role="status">Deleted “Banks” <button class="btn sm ghost" style="color:inherit">Undo</button></div>` — ink pill, bottom centre, 6–8 s.

## Tooltips
- **Hint** on a tile, badge or icon: `.ttip` (ink box, white text, rows `<span class="r"><span>label</span><b>value</b></span>`).
- **Chart read-out**: `.ctip` (surface card): first line the date `<span class="d">Fri 13 Nov · day 12 of 20</span>`,
  then one row per series sorted by value: swatch, name, value coloured up/down.

## Empty and failure states
```html
<div class="empty"><strong>No stock meets at least 1 of 2 conditions</strong>Loosen a threshold, switch the match to Any, or show near misses.
  <div class="row" style="justify-content:center;margin-top:12px"><button class="btn sm">Show near misses (0)</button></div></div>
```
Always: what happened, why, the next step as a button. When the data file cannot be read, keep the page usable with
"—" values and a notice with "Try again" (Watchlist M466 a).

## Loading
Under ~1 s show nothing; longer, keep the layout and put "—"/skeleton text in place of values; never a full-page spinner.

## Icon rail and page frame
The shell (`static/index.html`) draws the left rail; a page never draws its own navigation. Pages live in the shell's
iframe (`.terminal-frame`) and fill it: `html,body{height:100%;overflow:hidden}`, the page's `.page` scrolls
(`padding:var(--s-9) var(--s-10)`). See `new-page.md`.
