"""Build the claude.ai Design System artifact files (project/…) from this skill. Usage: python3 tools/build_artifact.py OUT_DIR"""
import json, re, sys, datetime
from pathlib import Path
SK = Path(__file__).resolve().parents[1]; OUT = Path(sys.argv[1]) / 'project'
OUT.mkdir(parents=True, exist_ok=True)
spec = (SK / 'assets/spec-v1.2.css').read_text(); canon = (SK / 'assets/edge-canonical.css').read_text()
def w(p, t): f = OUT / p; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(t)

# ---------------- tokens.json from the spec's own :root blocks ----------------
def block(src, sel_rx):
    m = re.search(sel_rx + r'\s*\{([^}]*)\}', src); return dict(re.findall(r'--([a-z0-9-]+)\s*:\s*([^;]+);?', m.group(1))) if m else {}
light = block(spec, r'@layer edge-tokens \{\s*:root')
dark = block(spec, r':root\.dark,:root\[data-theme="dark"\]')
light2 = block(spec[spec.index('5. TOKEN TAMBAHAN'):], r':root')
dark2 = block(spec[spec.index('5. TOKEN TAMBAHAN'):], r':root\.dark,:root\[data-theme="dark"\]')
canon_l = block(canon, r":root")
COLOR_RX = re.compile(r'^(#[0-9a-fA-F]{3,8}|rgba?\([0-9., ]+\))$')
USAGE = {
 'bg': 'Page background (light #fafafa, dark #0a0a0a).', 'surface': 'Cards, tables, inputs, dialogs.', 'surface-2': 'Table row hover, kbd, the track of a segmented control, chart track.',
 'hover': 'Hover of buttons and menu items.', 'sel': 'Selected neutral item: pill, tab count, open menu trigger, empty day box.', 'border': 'Every 1px line: cards, tables, inputs.', 'border-2': 'Lines on hover; the ring of the raised segment.',
 'text': 'Primary text and important numbers on bg, surface. Also the ink of the primary button and the underline of the selected tab.', 'text-2': 'Secondary text, button labels, on surface.',
 'text-3': 'Captions, table headers, axis labels, the purpose line. 3.3:1 on surface in light, 4.3:1 in dark: below 4.5:1, kept exact from the source; use for non-essential text only.',
 'green': 'Up / positive text (+1.78%), .pill.pos.', 'red': 'Down / negative text (−1.33%), .pill.neg, destructive buttons.', 'up': 'Up candles, bars, lines, sparklines, filled day boxes.', 'down': 'Down candles, bars, lines, sparklines.',
 'blue': 'Focus outline, links, a value changed from its default (.inp.custom), .pill.info.', 'amber': 'Warnings; the broker-date pill (.pill.warn).', 'violet': 'Chart accent.', 'navy': 'Chart accent; local brokers.',
 'green-bg': 'Background of .pill.pos.', 'red-bg': 'Background of .pill.neg.', 'blue-bg': 'Background of .pill.info, text selection.', 'amber-bg': 'Background of .pill.warn.',
 'c1': 'Chart series 1 (in this order).', 'c2': 'Chart series 2.', 'c3': 'Chart series 3.', 'c4': 'Chart series 4.', 'c5': 'Chart series 5.', 'c6': 'Chart series 6.',
 'up-bg': 'Volume bars and area fills, up.', 'down-bg': 'Volume bars and area fills, down.', 'violet-bg': 'Soft violet fill.', 'navy-bg': 'Soft navy fill.',
 'chart-grid': 'Horizontal gridlines of hand-made SVG charts.', 'chart-base': 'Zero / base line of SVG charts.'}
colors = []
order = list(light) + [k for k in light2 if k not in light]
for k in order:
    v = light.get(k, light2.get(k)); dv = dark.get(k, dark2.get(k))
    if not v or not COLOR_RX.match(v.strip()): continue
    val = {'light': v.strip().lower()}
    if dv and COLOR_RX.match(dv.strip()): val['dark'] = dv.strip().lower()
    u = USAGE.get(k) or (f'Colour scale step ({k}); fixed in both themes: solids, heat cells, illustrations.' if re.match(r'(gray|blue|green|red|amber|violet|navy)-\d', k) else 'Spec token.')
    colors.append({'name': k, 'value': val, 'usage': u})
colors.append({'name': 'chart-grid', 'value': {'light': '#f0f0f0', 'dark': '#1f1f1f'}, 'usage': USAGE['chart-grid']})
colors.append({'name': 'chart-base', 'value': {'light': '#c4c4c4', 'dark': '#4a4a4a'}, 'usage': USAGE['chart-base']})
px = lambda d, rx: [(k, v.strip()) for k, v in d.items() if re.match(rx, k)]
spacing = [{'name': k, 'value': v, 'usage': u} for (k, v), u in zip(px(light, r's-\d+$'), ['Hairline gaps.', 'Icon–label gap.', 'Small gaps.', 'Control gaps, kpi padding.', 'Input padding.', 'Card-to-control gaps.', 'Card header top.', 'Card padding, grid gaps.', 'Page padding (top).', 'Page padding (sides).', 'Large section gaps.'])]
RU = {'r-xs': 'kbd, small inputs.', 'r-sm': 'Menu items, buttons inside a segmented control.', 'r-md': 'Buttons, inputs, segmented control, search, small KPI box.', 'r-lg': 'Popovers, windows.', 'r-xl': 'Cards and panels.', 'r-2xl': 'Dialogs.', 'r-pill': 'Pills, toggles, toasts.'}
radius = [{'name': k, 'value': v, 'usage': RU.get(k, '')} for k, v in px(light, r'r-')]
HU = {'h-xs': 'Small segmented control (.seg.sm).', 'h-sm': 'Small button (.btn.sm).', 'h-md': 'Button, input, select.', 'h-th': 'Table header row.', 'h-row': 'Table row: 36px is the standard (canonical; the spec file says 44).', 'h-top': 'Top bar.'}
heights = [{'name': k, 'value': ('36px' if k == 'h-row' else v), 'usage': HU.get(k, '')} for k, v in px(light, r'h-')]
shadow = [{'name': 'shadow', 'value': {'light': light['shadow'].strip(), 'dark': dark['shadow'].strip()}, 'usage': 'Hover of buttons and cards.'},
          {'name': 'shadow-lg', 'value': {'light': light['shadow-lg'].strip(), 'dark': dark['shadow-lg'].strip()}, 'usage': 'Popovers, dialogs, windows, tooltips.'},
          {'name': 'shadow-sm', 'value': {'light': '0 1px 2px rgba(0,0,0,.06),0 2px 8px -2px rgba(0,0,0,.10)', 'dark': '0 1px 2px rgba(0,0,0,.45),0 2px 8px -2px rgba(0,0,0,.55)'}, 'usage': 'An open menu trigger.'},
          {'name': 'raise', 'value': '0 1px 2px rgba(0,0,0,.08),0 0 0 1px #dcdcdc', 'usage': 'The selected button of a segmented control (canonical decision 3). In CSS it uses var(--border-2) for the ring.'}]
fs = lambda k: light[k].strip()
type_ = {'fonts': [], 'families': {'sans': 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif'},
  'groups': [{'name': 'Headings', 'family': 'sans', 'styles': [
     {'name': 'h1', 'fontSize': fs('fs-3xl'), 'lineHeight': 1.25, 'fontWeight': 600, 'letterSpacing': '-0.01em', 'sample': 'Market Overview', 'usage': 'Page title, once per page.'},
     {'name': 'h2', 'fontSize': fs('fs-xl'), 'lineHeight': 1.3, 'fontWeight': 600, 'sample': 'Delete “Banks”?', 'usage': 'Dialog title.'},
     {'name': 'h3', 'fontSize': fs('fs-lg'), 'lineHeight': 1.35, 'fontWeight': 600, 'sample': 'Sector Performance', 'usage': 'Card title.'},
     {'name': 'kpi', 'fontSize': fs('fs-2xl'), 'lineHeight': '22px', 'fontWeight': 600, 'sample': 'Rp 5.95T', 'usage': 'KPI tile value.'}]},
   {'name': 'Text', 'family': 'sans', 'styles': [
     {'name': 'body', 'fontSize': fs('fs-base'), 'lineHeight': 1.5, 'fontWeight': 400, 'sample': 'What is happening in the market today, before you pick a stock.', 'usage': 'Default text; buttons and inputs.'},
     {'name': 'table', 'fontSize': fs('fs-md'), 'lineHeight': 1.5, 'fontWeight': 400, 'sample': 'BBCA  9,875  +0.51%', 'usage': 'Tables, segmented controls, menus; tabular digits.'},
     {'name': 'small', 'fontSize': fs('fs-12'), 'lineHeight': '16px', 'fontWeight': 400, 'sample': 'Cumulative return vs IHSG', 'usage': 'Card subtitles, KPI change line, small buttons.'},
     {'name': 'note', 'fontSize': fs('fs-sm'), 'lineHeight': 1.35, 'fontWeight': 400, 'sample': 'Broker data to Mon 9 Nov', 'usage': 'Notes, field labels.'},
     {'name': 'pill', 'fontSize': fs('fs-xs'), 'lineHeight': '20px', 'fontWeight': 600, 'sample': '+2.26%', 'usage': 'Pills, KPI labels.'},
     {'name': 'caps', 'fontSize': fs('fs-2xs'), 'lineHeight': 1.35, 'fontWeight': 600, 'letterSpacing': '0.05em', 'sample': 'NET BUY', 'usage': 'Uppercase eyebrows and menu titles, axis labels (10.5px, not uppercase).'}]}]}
tokens = {'name': 'EDGE Design System', 'version': 1,
  'color': {'themes': [{'id': 'light', 'name': 'Light'}, {'id': 'dark', 'name': 'Dark'}], 'tokens': colors},
  'type': type_, 'spacing': {'tokens': spacing}, 'radius': {'tokens': radius}, 'shadow': {'tokens': shadow},
  'height': {'note': 'Control heights.', 'tokens': heights},
  'meta': {'source': 'github', 'repo': 'rednightt33/saniti', 'paths': {'tokens': ['.claude/skills/edge-design-system/assets/spec-v1.2.css', '.claude/skills/edge-design-system/assets/edge-canonical.css']}, 'synced': datetime.date.today().isoformat()}}
w('tokens.json', json.dumps(tokens, indent=1, ensure_ascii=False))

# ---------------- bundle: the spec + canonical CSS; edge-ds.js as window.EDGE ----------------
w('components/bundle.css', '/* EDGE: spec v1.2 (verbatim) then the canonical layer of 2026-11-18. tokens.css (generated from tokens.json) is loaded before and wins for token values. */\n' + spec + '\n' + canon)
js = (SK / 'assets/edge-ds.js').read_text()
assert '</script' not in js and '<!--' not in js
w('components/bundle.js', js + '\nwindow.EDGE = window.EdgeDS;\n')

# ---------------- README ----------------
skill = (SK / 'SKILL.md').read_text()
rules = skill[skill.index('## The rules'):skill.index('## How to use it')]
readme = '''EDGE / Market Lab is a research workstation for Indonesian (IDX) equities: market overview, watchlist, AI research,
a TradingView-like terminal, backtest, screener and radar. Its look is quiet and dense: white surfaces, 1px grey lines,
ink for the main action, green up and red down, Inter at 13px. Numbers carry the date of their data.

Load order on a page: Inter (Google Fonts, 400–700) → `tokens.css` → `components/bundle.css` (spec v1.2, then the
canonical layer) → the page's own CSS. Charts and number formats: `window.EDGE` (`components/bundle.js`): `pct`, `rp`,
`amount`, `price`, `dateLabel`, `spark`, `trend`, `lines`, `hbars`, `kofn`, `heat`, `changeColor`.

''' + rules.replace('## The rules (canonical, 2026-11-18)', '## Rules (canonical, 2026-11-18)') + '''
## Content

- English UI labels, sentence case, plain verbs: "Add ticker", "Save screen", "Open Terminal". No emoji.
- A refusal or empty state says what happened and the next step as a button ("Loosen a threshold, switch the match to Any, or show near misses").
- Dates: "Mon 17 Nov"; periods: 1D, 5D, 1M, 3M, YTD, 1Y, Custom; amounts: "Rp 5.95T", "+414B"; changes: "+1.78%", "−1.33%" (U+2212).
- Codes are upper case (BBCA, IHSG, LQ45); company names as listed ("PT Bank Central Asia Tbk").

## Iconography

16×16 stroke icons, stroke 1.6, round caps, `currentColor`, from one sprite (`<svg class="ic"><use href="#i-NAME"/></svg>`;
the sprite is in the repository at `.claude/skills/edge-design-system/assets/icons.svg`, previewed under Icons). Names:
overview, radar, watch, terminal, backtest, research, post, saved, search, chev, chevr, plus, x, grip, cal, filter, more,
info, cols, check, sort, share, expand, bulb, spark, arrow. No icon font, no emoji.

## Source

The repository `rednightt33/saniti`, folder `.claude/skills/edge-design-system/` (the source of this system; edit there
first, then update this artifact), built from EDGE's pages (`apps/edge-bff`) and the user's design proposals.
'''
w('README.md', readme)

# ---------------- components ----------------
SPRITE = (SK / 'assets/icons.svg').read_text().split('\n', 1)[1].strip()
C = {}
def comp(name, group, height, summary, guide, body, script=''):
    C[name] = (group, height, summary, guide, body, script)
comp('Button', 'Actions', 150, 'Buttons: ink primary, green when ready to run, secondary, ghost, danger, small and icon-only.',
 '''- **Primary** (`.btn.primary`): the page's main action, once per area. **Ready** (`.btn.primary.ready`): a button that runs something (Screen now) when it can run.
- **Secondary** `.btn`, **quiet** `.btn.ghost`, **destructive** `.btn.danger` (always confirmed by a dialog naming the thing), **small** `.sm` (28px), **icon only** `.iconbtn` with `aria-label`.
- Shortcuts: `<kbd>Alt+A</kbd>` inside the button and `aria-keyshortcuts`; hidden on phones.
- A trigger with `aria-haspopup` + `aria-expanded="true"` shows the open state by itself.
- Provide: the label (verb first), an icon only when it helps scanning.''',
 '''<div class="row" style="flex-wrap:wrap;padding:16px"><button class="btn primary">Open Terminal</button><button class="btn primary ready">Screen now<kbd>Alt+S</kbd></button><button class="btn">Save screen</button><button class="btn ghost">Reset</button><button class="btn danger">Delete list</button><button class="btn sm">Small</button><button class="iconbtn" aria-label="More"><svg class="ic"><use href="#i-more"/></svg></button><button class="btn" aria-haspopup="menu" aria-expanded="true">Open menu<svg class="ic ic-sm"><use href="#i-chev"/></svg></button></div>''')
comp('SegmentedControl', 'Controls', 110, 'Segmented control for 2–5 choices such as periods; the selected button is raised white on a grey track.',
 '''- Use for periods (1D 5D 1M Custom) and views (Table / Cards). `.seg.sm` inside a card header, after a "Period" label (`.plab`).
- Selected: `.on` + `aria-pressed="true"` (decision 2, 3). More than 5 choices: a select or a menu.''',
 '''<div class="row" style="padding:16px;gap:16px;flex-wrap:wrap"><div class="seg" role="group" aria-label="View"><button>Table</button><button class="on" aria-pressed="true">Cards</button></div><span class="row"><span class="muted" style="font-size:12px">Period</span><div class="seg sm" role="group" aria-label="Period"><button>1D</button><button class="on" aria-pressed="true">5D</button><button>1M</button><button>Custom</button></div></span></div>''')
comp('Tabs', 'Controls', 100, 'Underline tabs that switch views or lists, with an optional count.',
 '''- 40px, a 2px ink bar under the selected tab (`aria-selected="true"`), optional `.cnt` that turns ink when selected.
- Scrolls sideways on a phone; never wraps. Not for 2–5 small options (use SegmentedControl).''',
 '''<div style="padding:8px 16px"><div class="tabs" role="tablist"><button role="tab" aria-selected="true">Core<span class="cnt">10</span></button><button role="tab" aria-selected="false">Banks<span class="cnt">2</span></button><button role="tab" aria-selected="false">Commodities<span class="cnt">4</span></button></div></div>''')
comp('Pill', 'Data display', 120, 'Pills and badges for status, change and data dates.',
 '''- `.pill` neutral, `.pos` up, `.neg` down, `.warn` warning / broker date, `.info` corporate action. With `.dot` for the data-date pills in the page header: prices `.pos`, broker data `.warn`.
- Radar hit: ink pill (`background:var(--text);color:var(--surface)`) with the radar icon.''',
 '''<div class="row" style="flex-wrap:wrap;padding:16px"><span class="pill pos"><span class="dot"></span>Prices to Mon 17 Nov</span><span class="pill warn"><span class="dot"></span>Broker data to Mon 9 Nov</span><span class="pill">Neutral</span><span class="pill pos">+2.26%</span><span class="pill neg">−1.33%</span><span class="pill info"><svg class="ic ic-sm"><use href="#i-cal"/></svg>RUPS 17 Nov</span><span class="pill" style="background:var(--text);color:var(--surface)"><svg class="ic ic-sm"><use href="#i-radar"/></svg>Radar S6</span></div>''')
comp('Toggle', 'Controls', 90, 'Filter toggles (pill buttons) and the on/off switch.',
 '''- `.tog` + `aria-pressed`: a filter of what is shown; answer with a toast saying what is filtered and how many remain.
- `.switch` + `role="switch"` + `aria-checked`: a setting that applies at once.''',
 '''<div class="row" style="padding:16px"><button class="tog on" aria-pressed="true"><svg class="ic ic-sm"><use href="#i-radar"/></svg>Radar</button><button class="tog" aria-pressed="false">Corporate action</button><button class="switch on" role="switch" aria-checked="true" aria-label="Near misses"></button><span class="muted">Near misses</span></div>''')
comp('Field', 'Controls', 120, 'Labelled inputs; grey border on focus; blue text for a value changed from its default.',
 '''- `<label class="field"><span>Label</span><input class="inp"></label>`; errors under the field in red, naming the fix.
- `.inp.custom` marks a parameter changed from its default. Focus: grey 1px border, no ring (decision 8).''',
 '''<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:16px"><label class="field"><span>List name</span><input class="inp" value="Core"></label><label class="field"><span>Search</span><input class="inp" placeholder="Search code or name, e.g. AD"></label><label class="field"><span>RSI below</span><input class="inp custom" value="25"></label></div>''')
comp('Card', 'Layout', 200, 'Card with header: title over a grey subtitle, Period label and segmented control on the right.',
 '''- `.card` (radius 12, 1px border, no shadow) › `.card-h` › `.ttl` (`h3` + `.ttl-s`) and `.pctl` (`.plab` + `.seg.sm`); body `.card-b`.
- One idea per card; its data date in the subtitle or a note.''',
 '''<div style="padding:16px"><div class="card"><div class="card-h"><div class="ttl"><h3>Sector Performance</h3><span class="ttl-s">Cumulative return vs IHSG</span></div><span class="pctl"><span class="plab">Period</span><div class="seg sm" role="group" aria-label="Period"><button>20D</button><button class="on" aria-pressed="true">60D</button><button>YTD</button><button>1Y</button></div></span></div><div class="card-b"><p class="note">Card body.</p></div></div></div>''')
comp('KpiTile', 'Data display', 150, 'KPI tile: label with timeframe, purpose line, 18px value, change line and a 64×26 sparkline.',
 '''- `.kpis` grid › `.card.ktile` (`.lb`, `.ksub`, `.v`, `.s`, `EDGE.spark(values)`); a broker-data tile carries the amber date pill; breadth adds `.adbar`.
- 4–6 tiles in one row at the top of a page. Provide: label, timeframe, value, change, the last ~30 values.''',
 '''<div class="kpis" id="k" style="padding:16px"></div>''',
 '''var r=1;function wk(n,d){var v=100,a=[];for(var i=0;i<n;i++){a.push(v);r=(r*16807)%2147483647;v*=1+d/100/n+((r/2147483647)-.5)*.02}return a}
document.getElementById('k').innerHTML='<div class="card ktile" tabindex="0"><div class="lb"><span>IHSG (1D)</span></div><div class="ksub">Composite · vs prior close</div><div><div class="v">4,649.64</div><div class="s"><b class="up">+81.36 · +1.78%</b></div></div>'+EDGE.spark(wk(30,4))+'</div><div class="card ktile" tabindex="0"><div class="lb"><span>Turnover (1D)</span><span class="pill warn">9 Nov</span></div><div class="ksub">Value traded · Regular</div><div><div class="v">Rp 5.95T</div><div class="s"><b>0.61×</b> 20D average</div></div>'+EDGE.spark(wk(30,2),{color:'var(--text-3)'})+'</div><div class="card ktile" tabindex="0"><div class="lb"><span>Breadth (1D)</span></div><div class="ksub">Advancers / decliners</div><div><div class="v">564 / 143</div><div class="adbar"><i style="flex:564;background:var(--up)"></i><i style="flex:129;background:var(--gray-300)"></i><i style="flex:143;background:var(--down)"></i></div><div class="s">A/D 3.94×</div></div></div>';''')
comp('Table', 'Data display', 230, 'Dense data table: 36px rows, sticky header, right-aligned numbers, selected row.',
 '''- `.tbl-wrap` › `table.tbl`; `.sym` + `.sub` for stock and name; `.l` for left columns; `tr.on` selected; `th.sort` sortable; `td.miss` hatched.
- Rows 36px (decision 6); numbers in `EDGE.price`, `pct`, `rp`. Wide tables scroll inside their card.''',
 '''<div style="padding:16px"><div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Stock</th><th>Last</th><th>1D</th><th>Foreign 5D</th><th class="l">Signal</th></tr></thead><tbody><tr><td><span class="sym">ALFQ</span></td><td>2,480</td><td class="up">+0.12%</td><td class="down">−Rp 99.6B</td><td class="l"><span class="muted">—</span></td></tr><tr class="on"><td><span class="sym">BETQ</span></td><td>9,150</td><td class="down">−0.20%</td><td class="up">+Rp 1.97T</td><td class="l"><span class="pill pos">Accumulation</span></td></tr><tr><td><span class="sym">CAKQ</span></td><td>3,330</td><td class="up">+3.80%</td><td class="up">+Rp 24.5B</td><td class="l"><span class="muted">—</span></td></tr></tbody></table></div></div></div>''')
comp('Menu', 'Overlays', 170, 'Menu (popover) of actions under its trigger.',
 '''- `.pop` › `.menu-title` and `.menu-item` buttons; Escape and outside click close; arrow keys move.''',
 '''<div style="padding:16px"><div class="pop" role="menu" style="position:static;width:240px"><div class="menu-title">List</div><button class="menu-item" role="menuitem">Rename</button><button class="menu-item" role="menuitem">Indicators…</button><button class="menu-item" role="menuitem" style="color:var(--red)">Delete list</button></div></div>''')
comp('Dialog', 'Overlays', 220, 'Dialog on a dimmed backdrop: head, body, footer with the action.',
 '''- `.backdrop` › `.dialog` (`.dialog-head`, `.dialog-body`, `.dialog-foot`); focus trapped, Escape closes; destructive action named ("Delete list").''',
 '''<div style="display:grid;place-items:center;padding:24px;background:rgba(0,0,0,.32)"><div class="dialog" role="dialog" aria-label="Delete list"><div class="dialog-head"><strong>Delete “Banks”?</strong><span class="note">2 stocks. You can undo for 8 seconds.</span></div><div class="dialog-foot"><button class="btn">Cancel</button><button class="btn danger">Delete list</button></div></div></div>''')
comp('Toast', 'Overlays', 80, 'Toast: an ink pill at the bottom centre confirming what happened, with Undo where it applies.',
 '- `.toast` with `role="status"`; 6–8 seconds; the same verb as the action ("Deleted", "Filtered").',
 '''<div style="padding:20px;display:flex;justify-content:center"><span class="toast" role="status" style="position:static;transform:none">Filtered: only stocks in Radar (9 Nov) · 2 of 3</span></div>''')
comp('Tooltip', 'Overlays', 140, 'Two tooltips: an ink hint for tiles and badges, a surface card for chart read-outs.',
 '- `.ttip` hint; `.ctip` chart card: date first, then one row per series (swatch, name, value coloured up/down).',
 '''<div class="row" style="padding:16px;gap:24px;align-items:flex-start"><span class="ttip" style="position:static"><span class="t">Turnover (1D)</span><span class="r"><span>Value traded</span><b>Rp 5.95T</b></span><span class="r"><span>vs 20D average</span><b>0.61×</b></span></span><span class="ctip" style="position:static"><span class="d">Fri 13 Nov · day 12 of 20</span><span class="r"><i style="background:var(--c1)"></i><span>Financials</span><b class="up">+1.2%</b></span><span class="r"><i style="background:var(--text)"></i><span>IHSG</span><b class="down">−0.4%</b></span></span></div>''')
comp('EmptyState', 'Feedback', 150, 'Empty state: what happened, why, and the next step as a button.',
 '- `.empty` › `strong` + a sentence + buttons. When data cannot be read, keep the page usable with "—" and a notice with "Try again".',
 '''<div style="padding:16px"><div class="card"><div class="empty"><strong>No stock meets at least 1 of 2 conditions</strong>Loosen a threshold, switch the match to Any, or show near misses.<div class="row" style="justify-content:center;margin-top:12px"><button class="btn sm">Show near misses (0)</button><button class="btn sm">Match at least 1</button></div></div></div></div>''')
comp('LineChart', 'Charts', 260, 'Hand-made SVG line chart for a few series with grid, zero line, date labels and a legend.',
 '''- `EDGE.lines(series, dates, {zero:true})`: series `{name, color, values, dash?, w?}`; colours `--c1…--c6` in order, the benchmark `--text` dashed.
- Grid `--chart-grid`, zero `--chart-base`, labels 10.5px `--text-3`; hover read-out `.ctip`.''',
 '''<div style="padding:16px" id="c"></div>''',
 '''var r=3;function wk(n,d){var v=100,a=[];for(var i=0;i<n;i++){a.push(v);r=(r*16807)%2147483647;v*=1+d/100/n+((r/2147483647)-.5)*.03}return a.map(function(x){return (x/a[0]-1)*100})}
var ds=[];for(var i=0;i<60;i++){ds.push(new Date(Date.UTC(2026,7,20+Math.round(i*1.45))).toISOString().slice(0,10))}
document.getElementById('c').innerHTML=EDGE.lines([{name:'Financials',color:'var(--c1)',values:wk(60,-8)},{name:'Energy',color:'var(--c2)',values:wk(60,-22)},{name:'Industrials',color:'var(--c3)',values:wk(60,-14)},{name:'IHSG',color:'var(--text)',dash:true,w:1.4,values:wk(60,-12)}],ds,{zero:true,w:900,h:220,left:48});''')
comp('Sparkline', 'Charts', 90, 'Sparklines: 64×26 for KPI tiles and a fluid 40px trend line for cards; up or down by first vs last value.',
 '- `EDGE.spark(values)`, `EDGE.trend(values, 40)`; a neutral series passes `{color:"var(--text-3)"}`.',
 '''<div class="row" style="padding:16px;gap:24px" id="s"></div>''',
 '''var a=[],b=[],v=100,w=100;for(var i=0;i<30;i++){v*=1+Math.sin(i/3)*.01+.003;w*=1-Math.cos(i/4)*.01-.003;a.push(v);b.push(w)}
document.getElementById('s').innerHTML=EDGE.spark(a)+EDGE.spark(b)+'<div style="width:300px">'+EDGE.trend(a,40)+'</div>';''')
comp('Treemap', 'Charts', 130, 'Change colours for treemap tiles and heat cells: seven steps, white text on the two darkest.',
 '- `EDGE.changeColor(change, signed)` returns [background, text]; tile label = code + change.',
 '''<div id="t" style="padding:16px;display:grid;grid-template-columns:repeat(7,1fr);gap:2px"></div>''',
 '''document.getElementById('t').innerHTML=[3.4,1.8,.7,0,-.8,-2.1,-4.2].map(function(c){var k=EDGE.changeColor(c);return '<div style="padding:8px;font-size:11px;background:'+k[0]+';color:'+k[1]+'"><b style="display:block;font-size:12px">ALFQ</b>'+EDGE.pct(c)+'</div>'}).join('');''')
comp('Bars', 'Charts', 170, 'Horizontal value bars for rankings and foreign net buy/sell.',
 '- `EDGE.hbars(rows)` with rows `{label, value, text}`; up green, down red; values with `EDGE.amount`.',
 '''<div style="padding:16px;display:grid;grid-template-columns:1fr 1fr;gap:16px"><div id="b1"></div><div id="b2"></div></div>''',
 '''document.getElementById('b1').innerHTML=EDGE.hbars([['ALFQ',414e9],['OKZX',268e9],['FUHX',31e9]].map(function(r){return {label:r[0],value:r[1],text:EDGE.amount(r[1])}}));
document.getElementById('b2').innerHTML=EDGE.hbars([['HOMX',-330e9],['PYJX',-179e9],['XXBX',-90e9]].map(function(r){return {label:r[0],value:r[1],text:EDGE.amount(r[1])}}));''')
comp('DayCounts', 'Charts', 260, 'Day-count boxes ("k of N days", streaks) and a one-row heat strip for compact panes.',
 '- `EDGE.kofn(values, N)`: one column per session, filled `--up`, empty `--sel`; `EDGE.heat(signed)`: colour = direction, opacity = size. Percent stays in the legend.',
 '''<div style="padding:16px;display:grid;gap:12px"><div id="k1"></div><div id="k2"></div></div>''',
 '''document.getElementById('k1').innerHTML=EDGE.kofn([11,12,12,13,12,11,11,10,11,12,13,14,14,15,14,13,12,12,13,14],20);
document.getElementById('k2').innerHTML=EDGE.heat([1,2,3,-1,1,-1,-2,-3,-4,1,2,3,4,5,-1,1,2,-1,-2,1]);''')
comp('Window', 'Layout', 260, 'Floating window (Terminal ⤢ windows): head with context, pin and close; controls row; body.',
 '- `.win` › `.win-h` (`strong`, `small` context, `.acts`), `.win-b` › `.win-ctl` (period, Top N, board) then the content; 880×520 or 720×560.',
 '''<div style="padding:16px"><div class="win"><div class="win-h"><strong>Foreign × Domestic</strong><small>ALFQ · Regular · Top 3 · to Mon 9 Nov</small><span class="acts"><button class="iconbtn sm" aria-label="Pin"><svg class="ic ic-sm"><use href="#i-saved"/></svg></button><button class="iconbtn sm" aria-label="Close"><svg class="ic ic-sm"><use href="#i-x"/></svg></button></span></div><div class="win-b"><div class="win-ctl"><div class="seg sm" role="group" aria-label="Period"><button>1D</button><button class="on" aria-pressed="true">5D</button><button>20D</button></div></div><table class="tbl compact"><thead><tr><th>Party</th><th>Buy %</th><th>Sell %</th><th>Net pt</th></tr></thead><tbody><tr><td><span class="sym">Foreign</span></td><td>34.2</td><td>41.8</td><td class="down">−7.6</td></tr><tr class="on"><td><span class="sym">Domestic</span></td><td>65.8</td><td>58.2</td><td class="up">+7.6</td></tr></tbody></table></div></div></div>''')
comp('SignalMatrix', 'Data display', 200, 'Signal matrix: one row per stock, Strong / Neutral / Weak cells per signal family.',
 '- `.mx` grid (`--mx-cols`), `.h` headers, `.c.s` / `.c.n` / `.c.w` cells with the word, not colour alone.',
 '''<div style="padding:16px"><div class="mx" id="m"></div></div>''',
 '''var M=['Technical','Momentum','Foreign','Bandar','Fundamental'],L=['s','n','w'];document.getElementById('m').innerHTML='<div></div>'+M.map(function(x){return '<div class="h">'+x+'</div>'}).join('')+['ALFQ','BETQ','CAKQ','DELQ'].map(function(t,r){return '<div class="sym">'+t+'</div>'+M.map(function(_,c){var k=L[(r*2+c)%3];return '<div class="c '+k+'">'+(k=='s'?'Strong':k=='w'?'Weak':'Neutral')+'</div>'}).join('')}).join('');''')
comp('Timeline', 'Data display', 200, 'Event timeline: a dot on a rule, the event, a grey line with source and time.',
 '- `.tl` › `.e` (`.pos` / `.neg` / `.info` for the dot) › text + `small`.',
 '''<div style="padding:16px"><div class="tl"><div class="e pos">ALFQ crossed its 52-week high<small>Alert · 15:42</small></div><div class="e info">INTQ entered the Radar<small>Signal · 09:05 · Big Accumulation</small></div><div class="e neg">GALQ fell below 2,800<small>Alert · 14:12</small></div><div class="e">BETQ cum date, dividend<small>Corporate action · 20 Nov</small></div></div></div>''')
comp('Icons', 'Foundations', 170, 'The 16px stroke icon sprite.',
 '- `<svg class="ic"><use href="#i-NAME"/></svg>` (`.ic-sm` 14px); paste the sprite once per page. A new icon is a new `<symbol>` in the same style (16×16, stroke 1.6, round).',
 '''<div id="ic" style="padding:16px;display:grid;grid-template-columns:repeat(9,1fr);gap:12px;font-size:10.5px;color:var(--text-3)"></div>''',
 '''document.getElementById('ic').innerHTML=['overview','radar','watch','terminal','backtest','research','post','saved','search','chev','chevr','plus','x','grip','cal','filter','more','info','cols','check','sort','share','expand','bulb','spark','arrow'].map(function(n){return '<div style="display:grid;justify-items:center;gap:6px;color:var(--text-2)"><svg class="ic"><use href="#i-'+n+'"/></svg><span style="color:var(--text-3)">'+n+'</span></div>'}).join('');''')
for name, (group, height, summary, guide, body, script) in C.items():
    pv = f'<!-- @dsCard group="{group}" height={height} -->\n' + SPRITE + '\n' + body + ('\n<script>\n' + script + '\n</script>' if script else '') + '\n'
    assert '</script' not in script
    w(f'components/{name}/preview.html', pv)
    w(f'components/{name}/README.md', f'# {name}\n\n{summary}\n\n{guide}\n')
# index.d.ts as documentation of the helpers
w('components/index.d.ts', '''/** window.EDGE: number formats and hand-made SVG charts (en-US, U+2212 minus). */
export declare function pct(v: number | null, digits?: number): string;   // "+1.78%"
export declare function rp(v: number | null, signed?: boolean): string;    // "Rp 8.15T"
export declare function amount(v: number | null): string;                 // "+414B"
export declare function price(v: number | null): string;                  // "7,925"
export declare function dateLabel(iso: string, withYear?: boolean): string; // "Mon 17 Nov"
export declare function changeColor(change: number, signed?: boolean): [string, string];
export declare function spark(values: (number | null)[], opt?: { w?: number; h?: number; color?: string }): string;
export declare function trend(values: (number | null)[], h?: number): string;
export declare function lines(series: { name: string; color: string; values: (number | null)[]; dash?: boolean; w?: number }[], dates: string[], opt?: { w?: number; h?: number; zero?: boolean; fy?: (v: number) => string; label?: string }): string;
export declare function hbars(rows: { label: string; value: number; text?: string }[], opt?: { color?: string; neutral?: boolean }): string;
export declare function kofn(values: number[], N: number): string;
export declare function heat(values: number[]): string;
''')
# ---------------- cover (written last) ----------------
w('components/Cover/preview.html', '''<!-- @dsCard height=288 -->
<style>
.cv{position:relative;width:960px;height:288px;background:var(--bg);overflow:hidden;font-family:var(--font-sans)}
.cv svg{position:absolute;left:0;top:0}
.cv .k-ink{fill:var(--text)}.cv .k-up{fill:var(--up)}.cv .k-down{fill:var(--down)}.cv .k-blue{fill:var(--blue)}.cv .k-empty{fill:var(--sel)}
.line{stroke:var(--border);stroke-width:1}
.cv .nm{position:absolute;left:40px;bottom:92px;max-width:440px;font-size:96px;line-height:.92;font-weight:600;letter-spacing:-.02em;color:var(--text)}
.cv .tg{position:absolute;left:40px;bottom:32px;max-width:440px;font-size:14px;color:var(--text-3)}
</style>
<div class="cv">
<svg width="960" height="288" viewBox="0 0 960 288" aria-hidden="true">
<!-- blocks: --text 224×168 (r-xl 12), --up 136×120, --down 136×72, --blue 64×64 (r-md 8); sizes are multiples of s-8 (16)
     arrangement: a dense modular grid right of x=480, bleeding off the top, like EDGE's KPI strip and cards
     pattern: day-count boxes (k of N days) — the system's own chart for counted days; "precise, technical, dense UI" -> tiles at one spacing step
     steps and radii: boxes 12px pitch 16 (s-8), r-xs 4 on boxes, r-xl 12 on cards -->
<rect class="k-ink" x="512" y="-12" width="224" height="168" rx="12"/>
<rect class="k-up" x="752" y="-12" width="136" height="120" rx="12"/>
<rect class="k-down" x="752" y="124" width="136" height="72" rx="12"/>
<rect class="k-blue" x="904" y="44" width="64" height="64" rx="8"/>
<g>''' + ''.join(f'<rect class="{"k-up" if j < k else "k-empty"}" x="{512 + i * 16}" y="{272 - (j + 1) * 16}" width="12" height="12" rx="4"/>' for i, k in enumerate([2, 3, 3, 4, 3, 2, 3, 4, 5, 4, 3, 4, 5, 6, 5, 4, 5, 6, 6, 5, 4, 5, 6, 7, 6, 5, 6, 7]) for j in range(5) if i * 16 + 512 < 952 and (j < k or j < 5)) + '''</g>
</svg>
<div class="nm">EDGE</div>
<div class="tg">Quiet, dense research screens for IDX equities: one ink action, green up, red down, every number dated.</div>
</div>
''')
idx = {'v': 3, 'layout': 'files', 'createdOnFiles': {'v': 1, 'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')},
       'title': 'EDGE Design System', 'namespace': 'EDGE', 'libraries': [], 'sections': {}, 'groups': [], 'assetGroups': {}, 'blobs': {}, 'docs': {'sections': []},
       'lastChange': {'by': 'Claude', 'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'via': 'Claude Code · rednightt33/saniti', 'note': 'First build from .claude/skills/edge-design-system (spec v1.2 + canonical layer, user decisions 2026-11-18).'}}
w('design-system.json', json.dumps(idx, indent=1))
print('colors', len(colors), 'components', len(C), 'files', sum(1 for _ in OUT.rglob('*') if _.is_file()))
