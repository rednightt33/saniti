"""EXEC-SHARE-UI (user 2026-10-19: the share button in the answer's action row, "PDF dan PNG alright", the EDGE logo in
a top corner; the composer's Research Mode menu removed, "item tersebut di remove saja"): an answer is shared as a card
without EDGE's bars, composer or panels, printed alone for the PDF and drawn as a PNG in the browser."""
import copy
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
             logo: stage?.querySelector('.edge-share-head img')?.getAttribute('src'), title: document.title,
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
    page.get_by_role('button', name='Bagikan', exact=True).click()
    menu = page.get_by_role('menu', name='Bagikan')
    assert menu.get_by_role('menuitem').all_inner_texts() == ['PDF (dokumen)', 'PNG (gambar)']
    menu.get_by_role('menuitem', name='PDF (dokumen)').click()
    card = page.wait_for_function('() => window.__printed').json_value()
    page.emulate_media(media='print')  # while the print dialog is open only the card is printed
    assert page.evaluate(ALONE)
    page.emulate_media(media='screen')
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    assert card['printing'] and card['logo'] == '/favicon.svg'
    assert card['text'].startswith('EDGE') and 'Pertanyaan\n\nfx:share_card' in card['text']
    assert 'Data sampai 17 Oktober 2026' in card['text']  # the latest date of the tables
    assert 'Permintaan ' in card['text'] and 'Dibuat oleh EDGE AI; bukan saran investasi' in card['text']
    assert 'Asumsi' in card['text'] and 'Data sampai akhir Agustus.' in card['text'] and 'Return harian dirata-rata.' in card['text']
    for chrome in ('Pin', 'Submit', 'Bagikan', 'Request '):
        assert chrome not in card['text'], chrome
    assert card['buttons'] == 0 and card['folded'] == 0 and card['closed'] == 0
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


def test_png_draws_the_card_at_2x_and_downloads_it_without_web_share(fixture_server, browser_page):
    origin, _ = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:share_card')
    saved(page)
    page.get_by_role('button', name='Bagikan', exact=True).click()
    with page.expect_download(timeout=20000) as info:
        page.get_by_role('menuitem', name='PNG (gambar)').click()
    download = info.value
    assert download.suggested_filename.startswith('EDGE ') and download.suggested_filename.endswith('.png')
    data = open(download.path(), 'rb').read()
    width, height = png_size(data)
    assert width == 1080 and height > 400 and len(data) > 20000
    assert not page.locator('.edge-share-stage').count()  # the off-screen card is removed again
    assert page.evaluate("() => typeof window.htmlToImage === 'object'")  # loaded on first use, from this origin
