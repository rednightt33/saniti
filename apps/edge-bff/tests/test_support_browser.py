"""Phase 4, the contact-support panel in the browser (the user, 2026-11-22: "panel sebelah kiri di live iconnya kotak
surat. Kira2 kalau di klik fungsinya sama seperti SS terlampir"; "apabila user unlogin tries to click it maka akan disuruh
login dulu"; "lampiran hanya 2A"): the rail's mailbox on a wide screen and in the phone's EDGE bar; a visitor is asked to
sign in; an account sends a message with its images, the dialog checking each file as the server does and showing the
server's own reasons, under their field or above the actions. Needs EDGE_TEST_POSTGRES_URL, Playwright with
EDGE_TEST_CHROMIUM and the built Terminal page."""
import dataclasses

import pytest

playwright = pytest.importorskip('playwright.sync_api')

from e2e_people import CHROMIUM, ROOT, Live, browser_context, db, register, shell_navigate  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 4
JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00' + bytes(200)
GIF = b'GIF89a' + bytes(100)
MAILBOX = 'nav.side-nav button[aria-label="Contact support"]'


@pytest.fixture
def site(settings, store, monkeypatch):
    on = Live(dataclasses.replace(settings, guests_enabled=True, prelaunch_enabled=False, support_per_hour=2), store,
              monkeypatch)
    on.terminal.apply_header = True
    try:
        yield on
    finally:
        on.close()


def files_in(folder):
    made = {}
    for name, raw in (('screen.png', PNG), ('photo.jpg', JPEG), ('anim.png', GIF), ('third.png', PNG), ('fourth.png', PNG),
                      ('big.png', b'\x89PNG\r\n\x1a\n' + bytes(5 * 1024 * 1024))):
        (folder / name).write_bytes(raw)
        made[name] = str(folder / name)
    return made


def write(dialog, kind, subject, body):
    dialog.get_by_label('Issue type').select_option(kind)
    dialog.get_by_label('Subject').fill(subject)
    dialog.get_by_label('Description').fill(body)


def test_a_visitor_is_asked_to_sign_in_and_an_account_sends_its_message_with_images(site, tmp_path):
    if not (ROOT / 'static' / 'terminal-app' / 'index.html').is_file():
        pytest.skip('the Terminal page is not built (cd apps/edge-bff/terminal && npm run build)')
    files = files_in(tmp_path)
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True, args=site.terminal.browser_args())
        try:
            # a visitor: the mailbox is in the rail, and its click asks to sign in (never the dialog)
            visitor = browser_context(browser).new_page()
            visitor.goto(site.origin + '/terminal')
            visitor.locator(MAILBOX).click()
            box = visitor.get_by_role('dialog')
            box.get_by_text('Sign in to contact support').wait_for()
            assert 'Contact support is for EDGE accounts' in box.inner_text() and not visitor.locator('.support-dialog').count()
            box.get_by_role('button', name='Sign in').click()
            visitor.wait_for_function("() => location.pathname === '/login'")

            page = browser_context(browser, timezone_id='Asia/Jakarta', locale='en-US').new_page()
            register(page, site, 'ana_support', 'ana@example.com')
            shell_navigate(page, '/terminal')
            page.locator('.terminal-page iframe.terminal-frame').wait_for()
            page.locator(MAILBOX).click()
            dialog = page.locator('.support-dialog')
            dialog.wait_for()
            assert dialog.get_by_label('Issue type').evaluate('n => document.activeElement === n')
            assert 'Relevant technical details will be included automatically' in dialog.inner_text()
            assert 'Up to 3 images: PNG, JPG or WebP, 5 MB each.' in dialog.inner_text()
            dialog.get_by_role('button', name='Submit issue').click()                # empty: each field says what to write
            assert dialog.locator('#support-subject-note').inner_text() == 'Write a short title.'
            assert dialog.locator('#support-body-note').inner_text() == 'Describe the issue.'
            assert dialog.get_by_label('Subject').evaluate('n => document.activeElement === n')
            write(dialog, 'data', 'BBCA price looks wrong', 'On 20 Nov the close shows 0.\nIt should be 9,000.')
            assert dialog.locator('#support-subject-note').inner_text() == 'A short title, for example: The chart does not load.'
            # each file as the server checks it: its own first bytes, its size, at most three
            picker = page.locator('#support-images')
            picker.set_input_files([files['anim.png']])
            dialog.get_by_text('anim.png is not a PNG, JPG or WebP image.').wait_for()
            picker.set_input_files([files['big.png']])
            dialog.get_by_text('big.png is larger than 5 MB; make it smaller or crop it.').wait_for()
            picker.set_input_files([files['screen.png'], files['photo.jpg'], files['third.png'], files['fourth.png']])
            dialog.get_by_text('Attach at most 3 images.').wait_for()
            names = dialog.locator('.support-files li > span')
            assert names.all_inner_texts() == ['screen.png', 'photo.jpg', 'third.png']
            # the layout holds (a class the shell already styled once broke it unseen by the checks above): the attach
            # button and every row inside the dialog, a name shown in full, not cut to its first letter
            frame = dialog.bounding_box()
            for part in [dialog.get_by_role('button', name='Attach screenshot or file'), *[names.nth(i) for i in range(3)]]:
                box = part.bounding_box()
                assert frame['x'] <= box['x'] and box['x'] + box['width'] <= frame['x'] + frame['width'], box
            assert all(n.evaluate('e => e.scrollWidth <= e.clientWidth') for n in [names.nth(i) for i in range(3)])
            assert dialog.get_by_role('button', name='Attach screenshot or file').is_disabled()
            dialog.get_by_role('button', name='Remove third.png').click()
            assert names.all_inner_texts() == ['screen.png', 'photo.jpg']
            dialog.get_by_role('button', name='Submit issue').click()
            done = dialog.locator('.support-success')
            done.wait_for()
            ticket = db(site.store, 'SELECT ticket_id FROM edge_bff.support_tickets')[0]['ticket_id']
            assert done.locator('dd').all_inner_texts() == [f'#{ticket}', 'Data looks wrong', 'BBCA price looks wrong']
            assert done.get_by_text("Your message was sent. The reply comes to your account's email.").is_visible()
            page.wait_for_function('() => document.activeElement?.closest(".support-success") !== null', timeout=5000)
            done.get_by_role('button', name='Close').click()
            assert not page.locator('.support-dialog').count()
            # the focus goes back to the mailbox on the dialog's next frame (DialogShell's returnFocusRef)
            page.wait_for_function('() => document.activeElement?.getAttribute("aria-label") === "Contact support"', timeout=5000)
            row = db(site.store, 'SELECT ticket_id, kind, subject, body, images, details FROM edge_bff.support_tickets')[0]
            assert (row['kind'], row['subject'], row['body'], row['images']) == (
                'data', 'BBCA price looks wrong', 'On 20 Nov the close shows 0.\nIt should be 9,000.', 2)
            d = row['details']
            assert (d['page'], d['frame'], d['viewport'], d['timezone'], d['language'], d['plan']) == (
                '/terminal', '/terminal-app/', '1440x900', 'Asia/Jakarta', 'en-US', 'free'), d
            assert [(r['filename'], r['content_type'], r['bytes']) for r in db(
                site.store, 'SELECT filename, content_type, bytes FROM edge_bff.support_attachments ORDER BY position')] == [
                ('screen.png', 'image/png', len(PNG)), ('photo.jpg', 'image/jpeg', len(JPEG))]
            # the server's reason under its field (a hidden character), then the account's hourly limit above the actions
            page.locator(MAILBOX).click()
            dialog.wait_for()
            write(dialog, 'question', 'Hidden\u202echaracter', 'A question.')
            dialog.get_by_role('button', name='Submit issue').click()
            dialog.get_by_text('Remove the hidden or control character').wait_for()
            assert dialog.locator('#support-subject-note').get_attribute('role') == 'alert'
            dialog.get_by_label('Subject').fill('A question')
            assert dialog.locator('#support-subject-note').inner_text() == 'A short title, for example: The chart does not load.'
            dialog.get_by_role('button', name='Submit issue').click()
            dialog.locator('.support-success').wait_for()
            dialog.locator('.support-success').get_by_role('button', name='Close').click()
            page.locator(MAILBOX).click()
            write(dialog, 'bug', 'A third one', 'Over the limit.')
            dialog.get_by_role('button', name='Submit issue').click()
            alert = dialog.locator('.support-error[role="alert"]')
            alert.wait_for()
            assert alert.inner_text().startswith('You can send 2 support messages per hour. Wait '), alert.inner_text()
            assert dialog.get_by_label('Subject').input_value() == 'A third one'                # nothing typed is lost
            dialog.get_by_role('button', name='Cancel').click()
            assert not page.locator('.support-dialog').count()
            assert db(site.store, 'SELECT count(*) AS n FROM edge_bff.support_tickets')[0]['n'] == 2

            # a phone (390 and 360 px): the EDGE bar's mailbox opens the same dialog, inside the screen
            for width in (390, 360):
                phone = browser.new_context(viewport={'width': width, 'height': 800}, ignore_https_errors=True,
                                            storage_state=page.context.storage_state())      # the same account
                phone.route('https://fonts.*/*', lambda route: route.abort())
                mobile = phone.new_page()
                mobile.goto(site.origin + '/terminal')
                mobile.locator('.topbar button[aria-label="Contact support"]').click()
                mobile.locator('.support-dialog').wait_for()
                assert mobile.evaluate('() => document.documentElement.scrollWidth <= innerWidth'), width
                box = mobile.locator('.support-dialog').bounding_box()
                assert box['x'] >= 0 and box['x'] + box['width'] <= width, (width, box)
                actions = mobile.locator('.support-foot').bounding_box()
                assert actions['x'] + actions['width'] <= width, (width, actions)
                phone.close()
        finally:
            browser.close()
