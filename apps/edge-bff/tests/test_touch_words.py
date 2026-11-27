"""The hints of the EDGE pages say tap on a touch screen (EXEC-SECTOR-ANALYSIS check 2 MX2-8 on the Sector page; the
Watchlist, the Screener and the Backtest by the user's 2026-11-27 "ud 81 oke dgn rekomendasi"; ERRORS M576).

A text a person reads (a string, a template or markup in a page's source, not a comment) that names a mouse action
(click, double-click, hover) is written through `tap(mouse, touch)` of `shared/touch-words.ts`, so a phone or a
tablet reads its touch words. A new page is covered when it is added to PAGES; the Terminal keeps its own words
("Terminal jangan disentuh"). The rendered check of the same rule on the Sector page: `sector/tests/look/check2.mjs`
MX2-8. This test fails on the 16 texts the three pages had before (1 Watchlist, 10 Screener, 5 Backtest)."""
import re
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
PAGES = ('sector', 'watchlist', 'screener', 'backtest')
# a mouse word inside a string, a template or markup: after a quote, a backtick, a '>' or a ' · ', before the next one
WORD = re.compile(r"""(['"`>]|· )[^'"`<\n]*(?<![.\w$])([Cc]lick|[Dd]ouble-click|Hover|[Hh]over(?:ing)? (?:over|on|to|a|the))\b""")
# code that names the event, not a text: listeners, event types, CSS hover states, the helper itself
CODE = re.compile(r"addEventListener|onclick|\.click\(|'click'|\"click\"|'dblclick'|e\.type|tap\(|mouse|:hover|--hover")


def visible_mouse_words(text):
    out, block = [], False
    for n, line in enumerate(text.split('\n'), 1):
        s = line.strip()
        if block:
            block = '*/' not in s
            continue
        if s.startswith('/*') and '*/' not in s:
            block = True
            continue
        if s.startswith(('//', '*', '/*')):
            continue
        code = re.sub(r'//.*$|/\*.*?\*/', '', line)          # a trailing comment is not text
        if WORD.search(code) and not CODE.search(code):
            out.append((n, s[:120]))
    return out


def test_the_pages_say_tap_on_a_touch_screen():
    bad = []
    for page in PAGES:
        for f in sorted((EDGE / page / 'src').rglob('*.ts')):
            bad += [f'{f.relative_to(EDGE)}:{n}: {s}' for n, s in visible_mouse_words(f.read_text(encoding='utf-8'))]
    assert not bad, 'a mouse word a person reads, not written through tap() of shared/touch-words.ts:\n' + '\n'.join(bad)


def test_the_check_finds_a_bare_mouse_word():
    assert visible_mouse_words("x.title = 'Click to edit';")
    assert visible_mouse_words("const t = `<b>Click a row</b>`;")
    assert not visible_mouse_words("x.title = `${tap('Click', 'Tap')} to edit`;")
    assert not visible_mouse_words("el.addEventListener('click', go);  // a click opens it")
    assert not visible_mouse_words("   a click on a compact row opens it (comment)")
