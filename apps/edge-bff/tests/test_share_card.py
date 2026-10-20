"""EXEC-SHARE-UI (user 2026-10-19: the share button in the answer's action row, "PDF dan PNG alright", the EDGE logo in
a top corner; the composer's Research Mode menu removed, "item tersebut di remove saja"): an answer is shared as a card
without EDGE's bars, composer or panels, printed alone for the PDF and drawn as a PNG in the browser."""
import copy
import re
import struct

from test_answer_view import FIXTURES, article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, sign_in, submit, saved  # noqa: F401 (fixtures)

SHARED = copy.deepcopy(FIXTURES['answer_table'])
SHARED['response'].update(assumptions=['Data sampai akhir Agustus.'], methodology='Return harian dirata-rata.')
SHARED.setdefault('data_record', {})['outputs'] = [
    {'ref': 'out.o1', 'request_id': 'earlier', 'data_as_of': '2026-10-16'},
    {'ref': 'out.o0', 'request_id': 'earlier', 'data_as_of': '2026-10-17T00:00:00+07:00'}]
FIXTURES['share_card'] = SHARED

PRINTED = """() => {
  window.print = () => {
    const stage = document.querySelector('body > .edge-share-stage');
    window.__printed = ({text: stage?.innerText || '', printing: document.body.classList.contains('edge-share-printing'),
             logo: stage?.querySelector('.edge-share-head svg.edge-share-logo circle') ? 'inline' : null,
             images: stage?.querySelectorAll('.edge-share-head img').length, title: document.title,
             headings: stage?.querySelectorAll('.edge-share-body > h1').length,
             notes: stage?.querySelectorAll('.edge-notes[data-section]').length,
             question: (q => q && [getComputedStyle(q).backgroundColor, getComputedStyle(q.querySelector('p')).color])(
               stage?.querySelector('.edge-share-question')),
             evidence: (e => e && [e.lastElementChild?.tagName.toLowerCase(), getComputedStyle(e.querySelector('.edge-badge')).color])(
               stage?.querySelector('.edge-evidence-line')),
             width: stage?.querySelector('.edge-share-card')?.getBoundingClientRect().width,
             meta: stage?.querySelector('.edge-share-meta')?.innerText || null,
             metaLogos: stage?.querySelectorAll('.edge-share-meta img').length,
             buttons: stage?.querySelectorAll('button').length, folded: stage?.querySelectorAll('.edge-row-folded').length,
             closed: stage?.querySelectorAll('details:not([open])').length});
  };
}"""
ALONE = """() => { const stage = document.querySelector('body > .edge-share-stage');
  return getComputedStyle(stage).display !== 'none' && [...document.body.children].filter(node => node !== stage)
    .every(node => getComputedStyle(node).display === 'none'); }"""


def test_the_composer_has_no_research_mode_menu(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    assert not page.locator('.mode-anchor').count()
    assert not page.get_by_role('button', name='Standard', exact=True).count()


def test_share_offers_pdf_and_png_and_the_pdf_prints_the_card_alone(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:share_card')
    saved(page)
    page.evaluate(PRINTED)
    page.get_by_role('button', name='Share', exact=True).click()
    menu = page.get_by_role('menu', name='Share')
    assert menu.get_by_role('menuitem').all_inner_texts() == ['PDF (document)', 'PNG (image)', 'Word (document)']
    menu.get_by_role('menuitem', name='PDF (document)').click()
    card = page.wait_for_function('() => window.__printed').json_value()
    page.emulate_media(media='print')  # while the print dialog is open only the card is printed
    assert page.evaluate(ALONE)
    page.emulate_media(media='screen')
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    # EXEC-UI-1019B: the new EDGE logo and the date in the head, a 760 px card, the answer's metadata row without its cost
    assert card['printing'] and card['logo'] == 'inline' and card['images'] == 0 and round(card['width']) == 760
    # EXEC share card 2026-10-20: B black question box, C no title, D evidence in black with the check on the right
    assert card['question'] == ['rgb(3, 2, 19)', 'rgb(255, 255, 255)'] and card['headings'] == 0, card
    if card['evidence']:
        assert card['evidence'] == ['svg', 'rgb(3, 2, 19)'], card['evidence']
    assert re.match(r'\d{1,2} [A-Z][a-z]+ \d{4}', card['text']) and 'Question\n\nfx:share_card' in card['text']
    assert card['meta'] and card['meta'].startswith('Request ') and 'cost' not in card['meta'] and '$' not in card['meta']
    assert 'Data as of 17 October 2026' in card['text']  # the latest date of the tables
    assert 'Request ' in card['text'] and 'Not investment advice' in card['text'] and 'Made by EDGE AI' not in card['text']
    # E: Assumptions and Limitations show their title and count only; the methodology stays written out
    assert 'Assumptions (1)' in card['text'] and 'Data sampai akhir Agustus.' not in card['text']
    assert 'Return harian dirata-rata.' in card['text']
    for chrome in ('Pin', 'Submit', 'Share', 'Reported cost', 'Copy'):
        assert chrome not in card['text'], chrome
    assert card['buttons'] == 0 and card['folded'] == 0 and card['closed'] == card['notes'] >= 1
    assert card['title'].startswith('EDGE ')
    # this request's own tables come first; without any, every table of the record counts
    info = page.evaluate("""() => [EdgeView.shareInfo({request_id: 'r1', data_record: {outputs: [
        {request_id: 'r1', data_as_of: '2026-10-15'}, {request_id: 'r0', data_as_of: '2026-10-17'}]}}),
      EdgeView.shareInfo({request_id: 'r2', data_record: {outputs: [{request_id: 'r0', data_as_of: '2026-10-17'}]}}),
      EdgeView.shareInfo({request_id: 'r3'})]""")
    assert [i['dataAsOf'] for i in info] == ['2026-10-15', '2026-10-17', None]
    page.wait_for_function("() => !document.querySelector('.edge-share-stage') && "
                           "!document.body.classList.contains('edge-share-printing')")
    assert not page.title().startswith('EDGE ') or page.title() != card['title']


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    return struct.unpack('>II', data[16:24])


def test_png_draws_the_card_at_3x_and_downloads_it_without_web_share(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:share_card')
    saved(page)
    page.get_by_role('button', name='Share', exact=True).click()
    with page.expect_download(timeout=20000) as info:
        page.get_by_role('menuitem', name='PNG (image)').click()
    download = info.value
    assert download.suggested_filename.startswith('EDGE ') and download.suggested_filename.endswith('.png')
    data = open(download.path(), 'rb').read()
    width, height = png_size(data)
    assert width == 2280 and height > 600  # 760 CSS px at 3x (2026-10-20: sharper, the same layout)
    assert not page.locator('.edge-share-stage').count()  # the off-screen card is removed again
    assert page.evaluate("() => typeof window.htmlToImage === 'object'")  # loaded on first use, from this origin


def test_word_downloads_a_real_docx_with_every_section(fixture_server, browser_page):
    """2026-10-20 ("Tambahkan opsi untuk save as WORD", ".docx asli"): a ZIP of WordprocessingML that Word opens: the
    logo as PNG, the question, the answer with its table and the assumptions written out."""
    import io
    import zipfile
    from xml.dom import minidom
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:share_card')
    saved(page)
    page.get_by_role('button', name='Share', exact=True).click()
    with page.expect_download(timeout=20000) as info:
        page.get_by_role('menuitem', name='Word (document)').click()
    download = info.value
    assert download.suggested_filename.startswith('EDGE ') and download.suggested_filename.endswith('.docx')
    archive = zipfile.ZipFile(io.BytesIO(open(download.path(), 'rb').read()))
    assert archive.testzip() is None
    names = set(archive.namelist())
    assert {'[Content_Types].xml', '_rels/.rels', 'word/document.xml', 'word/styles.xml',
            'word/_rels/document.xml.rels', 'word/media/edge-logo.png'} <= names
    assert archive.read('word/media/edge-logo.png')[:8] == b'\x89PNG\r\n\x1a\n'
    for name in names - {'word/media/edge-logo.png'}:
        minidom.parseString(archive.read(name))  # every part is well-formed XML
    document = archive.read('word/document.xml').decode()
    text = ' '.join(node.data for node in minidom.parseString(document).getElementsByTagName('w:t')
                    for node in node.childNodes)
    assert 'fx:share_card' in text and 'Data sampai akhir Agustus.' in text and 'Return harian dirata-rata.' in text
    assert '<w:tbl>' in document and 'Not investment advice' in text and 'Request ' in text
    grid = minidom.parseString(document).getElementsByTagName('w:tblGrid')[0]
    first_row = minidom.parseString(document).getElementsByTagName('w:tr')[0]
    assert len(grid.getElementsByTagName('w:gridCol')) == len(first_row.getElementsByTagName('w:tc')) > 1
    assert all(n.nodeType == n.ELEMENT_NODE for n in grid.childNodes)  # no stray text in the grid
    assert page.evaluate("() => typeof window.EdgeDocx === 'object'")  # loaded on first use, from this origin
