"""The EDGE round of 2026-11-27 (EXEC.md EXEC-DESIGN-SYSTEM, decisions 12-14 of the design system's canonical layer): the
focus ring (UD75 "1a", scope "1A"), the contrast of the grey and the tags (UD73 "4A") and the touch hit areas (UD72
"3A"), on every EDGE page but the Terminal (the user's "Terminal jangan disentuh"; it keeps its own look).

- Every page entry (the production entry and every test build's) runs shared/focus-modality.ts, and the shell's
  static/edge-boot.js writes the same attribute from the same events: the kind of the last input on <html>.
- Every page's style sheets define --focus-ring, transparent under data-modality="pointer", and no focus rule paints a
  ring in blue: the old blue (#0070f3, var(--blue), #2563eb, the details tabs' #557499/#9dbbe1) is gone from every
  :focus, :focus-visible and :focus-within rule's outline and box-shadow.
- --text-3 is #6b6b6b light and #8a8a8a dark wherever a page defines it, and the tag ink tokens are defined.
- The pages that hold spec v1.2 inside their own CSS carry the canonical layer's touch block as the system writes it.
The browser check of the same rules: verification/edge_states/round2_focus_contrast.mjs."""
import re
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
SYSTEM = EDGE.parents[1] / '.claude/skills/edge-design-system/assets'
EXEMPT = {'terminal': 'the user\'s standing rule "Terminal jangan disentuh": the Terminal keeps its own look and states'}
PAGES = sorted(p.parent.name for p in EDGE.glob('*/vite.config.ts') if p.parent.name not in EXEMPT)
# the style sheets each page's entry imports (its own, the design system's copies it @imports)
SHEETS = {page: sorted((EDGE / page / 'src/styles').glob('*.css')) for page in PAGES}
EMBEDDING = ['overview/src/styles/overview.css', 'watchlist/src/styles/watchlist.css', 'radar/src/styles/radar.css',
             'screener/src/styles/screener.css', 'backtest/src/styles/design.css']
BLUE = re.compile(r'var\(--blue[,)]|#0070f3|#2563eb|#557499|#9dbbe1|var\(--accent,#2563eb\)', re.I)
RULE = re.compile(r'([^{}]+)\{([^{}]*)\}')


def entries(page):
    return [p for p in (EDGE / page / 'src/main.ts', EDGE / page / 'tests/fixture/main.ts', EDGE / page / 'tests/smoke/main.ts') if p.is_file()]


def blue_focus_rules(css):
    """(selector, body) of every rule whose selector names a focus state and whose outline or box-shadow is blue"""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []
    for sel, body in RULE.findall(css):
        if not re.search(r':focus|\.is-focus', sel):
            continue
        for decl in body.split(';'):
            if re.match(r'\s*(outline|outline-color|box-shadow)\s*:', decl) and BLUE.search(decl):
                out.append((sel.strip()[-120:], decl.strip()))
    return out


def test_the_pages_are_found():
    assert set(PAGES) >= {'overview', 'watchlist', 'radar', 'sector', 'screener', 'backtest', 'admin'}, PAGES


def test_every_page_entry_writes_the_kind_of_the_last_input():
    for page in PAGES:
        found = entries(page)
        assert found, page
        for p in found:
            assert re.search(r"^import '(\.\./)+shared/focus-modality\.ts';", p.read_text(), re.M), f'{p.relative_to(EDGE)} does not import shared/focus-modality.ts'


def test_the_shell_writes_the_same_attribute_from_the_same_events():
    shared = (EDGE / 'shared/focus-modality.ts').read_text()
    boot = (EDGE / 'static/edge-boot.js').read_text()
    assert "MODALITY = 'modality'" in shared and 'root.dataset.modality' in boot
    for text in (shared, boot):
        assert re.search(r"""addEventListener\(['"]pointerdown['"].*?, true\)""", text), text[:80]
        assert re.search(r"""addEventListener\(['"]keydown['"].*?, true\)""", text), text[:80]
        assert re.search(r'ctrlKey.*altKey.*metaKey', text, re.S)


def test_every_page_defines_the_ring_and_clears_it_after_a_pointer():
    for page in PAGES + ['static']:
        css = (EDGE / 'static/index.html').read_text() if page == 'static' else '\n'.join(p.read_text() for p in SHEETS[page])
        assert re.search(r'--focus-ring:\s*var\(--text-3\)', css), page
        assert re.search(r'\[data-modality="pointer"\][^{]*\{--focus-ring:transparent\}', css), page


def test_no_focus_rule_draws_a_blue_ring():
    for page in PAGES:
        for p in SHEETS[page]:
            if p.name == 'spec-v1.2.css':
                # the user's spec, held verbatim (its blue :focus-visible and .btn.is-focus): the canonical layer, a later
                # layer the same pages load after it, replaces both rules (asserted below)
                assert (p.parent / 'edge-canonical.css').is_file(), p
                continue
            assert not blue_focus_rules(p.read_text()), (str(p.relative_to(EDGE)), blue_focus_rules(p.read_text()))
    assert not blue_focus_rules((EDGE / 'static/index.html').read_text())
    canonical = (SYSTEM / 'edge-canonical.css').read_text()
    assert not blue_focus_rules(canonical)
    assert ':focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px}' in canonical
    assert '.btn.is-focus{outline:2px solid var(--text-3);outline-offset:2px}' in canonical
    assert '@layer edge-canonical {' in canonical


def test_the_self_test_sees_a_blue_ring():
    assert blue_focus_rules('.x:focus-visible{outline:2px solid var(--blue);outline-offset:2px}')
    assert blue_focus_rules('.x:focus-visible{box-shadow:inset 0 0 0 2px var(--blue)}')
    assert blue_focus_rules('.a,.x:focus-visible{outline:2px solid var(--blue,#0070f3)}')
    assert not blue_focus_rules('.x:focus-visible{outline:2px solid var(--focus-ring)}')
    assert not blue_focus_rules('.x:hover{border-color:var(--blue)}')
    assert not blue_focus_rules('.x:focus-visible{outline:2px solid var(--blue-tag)}')


def test_fields_never_take_the_ring():
    field = ':is(input:not([type=checkbox],[type=radio],[type=range],[type=color],[type=file],[type=button],[type=submit],[type=reset],[type=image]),select,textarea):focus-visible{outline:none}'
    assert field in (SYSTEM / 'edge-canonical.css').read_text()
    for rel in EMBEDDING:
        assert field in (EDGE / rel).read_text(), rel


def test_the_grey_reads_four_and_a_half_to_one_everywhere():
    def values(css):
        return set(re.findall(r'--text-3:\s*(#[0-9a-f]{6})', css, re.I))
    canonical = (SYSTEM / 'edge-canonical.css').read_text()
    assert values(canonical) == {'#6b6b6b', '#8a8a8a'}
    for rel in EMBEDDING + ['backtest/src/styles/backtest.css']:
        assert values((EDGE / rel).read_text()) <= {'#6b6b6b', '#8a8a8a'}, rel
    assert values((EDGE / 'static/index.html').read_text()) == {'#6b6b6b', '#8a8a8a'}
    for rel in EMBEDDING + [str(SYSTEM / 'edge-canonical.css')]:
        css = Path(rel).read_text() if rel.startswith('/') else (EDGE / rel).read_text()
        assert re.search(r'--green-tag:#087855;\s*--red-tag:#c92535;\s*--blue-tag:#0064d8;\s*--amber-tag:#ad5009', css), rel


def test_the_pages_that_hold_spec_v12_carry_the_touch_block_as_the_system_writes_it():
    canonical = (SYSTEM / 'edge-canonical.css').read_text()
    block = re.search(r'@media \(pointer:coarse\)\{\n.*?\n\}\n', canonical, re.S).group(0)
    assert '.seg button' in block and '.switch::before' in block and '--hit-x' in block
    for rel in EMBEDDING:
        text = (EDGE / rel).read_text()
        assert '@layer edge-canonical {\n' + block + '}' in text, rel
    for page in ('admin', 'sector'):
        assert (EDGE / page / 'src/styles/edge-canonical.css').read_text() == canonical, page
