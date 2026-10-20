"""EXEC-UI-1019B and EXEC-M181 in EDGE (user 2026-10-19/20): the table download icon ("tambah ICON download ... excel",
"Preparing file…" then the file), the run whose AI provider timed out ("user perlu tahu bahwa penyedia timeout dan
diberikan opsi untuk retry panggilan": Retry with the same model and level, or Change model), how long the running
step has taken, the copy button's label and the new logo. Served through the real BFF and queue; no AI call."""
import threading

from app.client import OrcError
from test_answer_view import article, fixture_server  # noqa: F401 (fixture)
from test_visual import browser_page, capture, saved, sign_in, submit  # noqa: F401 (fixtures)

OUTPUT = 'out_' + 'a' * 24
EXPORT = 'exp_' + 'b' * 24
TITLES = ['Ukuran', 'Setelah sinyal', 'Baseline', 'Selisih (95% CI)', 'p']
COLUMNS = ['measure', 'signal', 'base', 'measure', 'p']  # two shown columns can read the same output column


def with_kept_table(orc):
    """Answers with the answer_table fixture whose table Orc built from a kept output (answer_tables)."""
    original = orc.run

    def built(owner, id, payload):
        result = original(owner, id, {**payload, 'message': 'fx:answer_table'})
        result['answer_tables'] = [{'ref': 'out.o2', 'output_id': OUTPUT, 'rows': [0, 1], 'titles': TITLES,
                                    'columns': COLUMNS}]
        orc.saved[id]['response'] = result
        return result
    return original, built


def test_a_kept_table_downloads_every_row_as_excel_after_preparing_the_file(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = with_kept_table(orc)
    orc.run = built
    gate, asked = threading.Event(), []

    def export_table(owner, conversation_id, output_id, columns, titles):
        asked.append((owner, conversation_id, output_id, columns, titles))
        gate.wait(10)
        return {'export_id': EXPORT, 'file_name': 'ret_sektor.xlsx', 'size_bytes': 4, 'format': 'XLSX'}
    orc.export_table = export_table
    page.route(f'**/api/v1/exports/{EXPORT}', lambda route: route.fulfill(status=200, body=b'PK\x03\x04', headers={
        'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'content-disposition': 'attachment; filename="ret_sektor.xlsx"'}))
    try:
        submit(page, 'uji sinyal volume')
        saved(page)
        frame = article(page).locator('.edge-md-table-frame')
        button = frame.get_by_role('button', name='Download table (Excel)', exact=True)
        assert button.is_visible() and frame.get_by_role('button', name='Enlarge table', exact=True).is_visible()
        button.click()
        note = frame.locator('.edge-table-file-note')
        note.wait_for()
        assert note.inner_text() == 'Preparing file…' and button.is_disabled()
        capture(page, 'ui-1019b-table-download-preparing')
        with page.expect_download(timeout=10000) as info:
            gate.set()
        assert info.value.suggested_filename == 'ret_sektor.xlsx'
        page.wait_for_function("() => !document.querySelector('.edge-table-file-note')")
        owner, conversation, output, columns, titles = asked[0]
        assert conversation.startswith('conv_') and output == OUTPUT
        # the shown columns with their titles, each output column once
        assert columns == ['measure', 'signal', 'base', 'p'] and titles == ['Ukuran', 'Setelah sinyal', 'Baseline', 'p']
        assert not button.is_disabled()
    finally:
        gate.set()
        orc.run = original


def test_a_table_being_prepared_says_so_and_a_typed_table_has_no_download(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original, built = with_kept_table(orc)
    orc.run = built

    def busy(owner, conversation_id, output_id, columns, titles):
        raise OrcError('EXPORT_IN_PROGRESS', 409)
    orc.export_table = busy
    try:
        submit(page, 'uji sinyal volume')
        saved(page)
        frame = article(page).locator('.edge-md-table-frame')
        frame.get_by_role('button', name='Download table (Excel)', exact=True).click()
        frame.locator('.edge-table-file-note', has_text="This table's file is already being prepared").wait_for()
    finally:
        orc.run = original
    submit(page, 'fx:answer_table')  # the same table without answer_tables: the model typed it, nothing is kept
    saved(page, 2)
    assert article(page).locator('.edge-md-table-frame').count() >= 1
    assert article(page).locator('.edge-table-download').count() == 0


def test_the_ai_answer_has_a_labelled_copy_button_and_the_new_logo_is_served(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    assert article(page).locator('.clipboard-action.with-label').inner_text().strip() == 'Copy'
    for path in ('/edge-logo.svg', '/favicon.svg'):
        reply = page.request.get(origin + path)
        assert reply.status == 200 and reply.headers['content-type'].startswith('image/svg+xml'), path
        assert b'<svg' in reply.body()


def stalled_run(orc, original, code):
    def failing(owner, id, payload):
        result = original(owner, id, payload)
        # the run's model and level as Orc recorded them (not the composer's choice)
        result.update(status='FAILED', response=None,
                      error={'code': code, 'message': 'the AI provider sent no output for 30 s'})
        result['execution'].update(model='z-ai/glm-5.3-flash', reasoning_level='low')
        orc.saved[id].update(response=result, run_status='FAILED')
        return result
    return failing


def test_a_provider_timeout_offers_retry_with_the_same_model_and_level(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    orc.run = stalled_run(orc, original, 'PROVIDER_STALLED')
    try:
        submit(page, 'net beli asing BBRI')
        state = page.locator('.edge-provider-stalled')
        state.wait_for(timeout=15000)
        assert 'AI provider timed out' in state.inner_text() and 'even after one retry' in state.inner_text()
        capture(page, 'm181-provider-stalled')
    finally:
        orc.run = original
    calls = len(orc.calls)
    state.get_by_role('button', name='Retry', exact=True).click()
    for _ in range(200):
        if len(orc.calls) > calls:
            break
        page.wait_for_timeout(50)
    sent = orc.calls[-1][2]
    assert sent['message'] == 'net beli asing BBRI'
    assert sent['model'] == 'z-ai/glm-5.3-flash' and sent['reasoning_level'] == 'low'
    saved(page)


def test_change_model_puts_the_question_back_and_opens_the_model_menu(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    orc.run = stalled_run(orc, original, 'REASONING_RUNAWAY')
    try:
        submit(page, 'net beli asing BBRI')
        state = page.locator('.edge-provider-stalled')
        state.wait_for(timeout=15000)
        assert 'The AI kept thinking without answering' in state.inner_text()
        state.get_by_role('button', name='Change model', exact=True).click()
        page.locator('.edge-model-menu').wait_for()
        assert page.locator('textarea').input_value() == 'net beli asing BBRI'
    finally:
        orc.run = original


def test_the_running_step_shows_how_long_it_has_taken(fixture_server, browser_page):
    origin, orc = fixture_server
    page = browser_page
    sign_in(page, origin)
    original = orc.run
    release = threading.Event()

    def slow(owner, id, payload):
        orc.PROGRESS = {id: {'status': 'RUNNING', 'elapsed_ms': 130000, 'earlier_steps': 0, 'steps': [
            {'label': 'Understanding the question', 'state': 'done', 'started_ms': 0, 'duration_ms': 4000},
            {'label': 'Thinking', 'state': 'running', 'started_ms': 4000, 'duration_ms': 126000}]}}
        release.wait(timeout=20)
        return original(owner, id, {**payload, 'message': 'fx:answer_table'})
    orc.run = slow
    try:
        submit(page, 'net beli asing BBRI')
        step = page.locator('.edge-run-progress-step')
        step.wait_for(timeout=10000)
        clock = step.locator('.edge-run-step-clock')
        page.wait_for_function("() => Number(document.querySelector('.edge-run-step-clock')?.dataset.seconds) >= 126")
        assert ' '.join(step.inner_text().split()).startswith('Thinking · 2m'), step.inner_text()
        assert clock.inner_text().strip().startswith('· 2m')
    finally:
        release.set()
        orc.run = original
    saved(page)


def test_the_bff_passes_a_table_download_to_orc_for_the_owners_conversation(settings, store):
    """The route checks the conversation is this owner's and the table id's shape, sends only the columns and titles,
    and keeps Orc's refusal code (never its text)."""
    import httpx
    import psycopg
    from fastapi.testclient import TestClient

    from app.client import OrcClient
    from app.main import create_app
    from conftest import FakeOrc
    from test_edge import login

    conversation = 'conv_' + 'c' * 32
    with psycopg.connect(settings.database_url) as c:
        c.execute('INSERT INTO edge_bff.conversation_ui(owner_key,conversation_id,title) VALUES (%s,%s,%s)',
                  (settings.owner, conversation, 'uji'))
    seen = []

    def orc_side(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers['x-saniti-owner'], request.content))
        if b'"busy"' in request.content:
            return httpx.Response(409, json={'detail': {'code': 'EXPORT_IN_PROGRESS', 'message': 'internal words'}})
        return httpx.Response(200, json={'export_id': EXPORT, 'file_name': 'ret.xlsx', 'size_bytes': 9,
                                         'format': 'XLSX', 'download': '/v1/exports/x/download', 'inputs': []})

    class Orc(FakeOrc):
        client = OrcClient(settings, httpx.Client(base_url='http://orc.test', transport=httpx.MockTransport(orc_side)))

        def export_table(self, *args):
            return self.client.export_table(*args)

    url = f'/api/v1/conversations/{conversation}/outputs/{OUTPUT}/export'
    with TestClient(create_app(settings, store, Orc())) as c:
        assert c.post(url, json={'columns': ['a']}).status_code in (401, 403)  # signed in, with the CSRF token
        h = login(c)
        reply = c.post(url, headers=h, json={'columns': ['sector', 'n'], 'titles': ['Sektor', 'Jumlah']})
        assert reply.status_code == 200
        assert reply.json() == {'export_id': EXPORT, 'file_name': 'ret.xlsx', 'size_bytes': 9, 'format': 'XLSX'}
        path, owner, body = seen[-1]
        assert path == f'/v1/conversations/{conversation}/outputs/{OUTPUT}/export' and owner == settings.owner
        assert body == b'{"columns":["sector","n"],"titles":["Sektor","Jumlah"]}'
        busy = c.post(url, headers=h, json={'columns': ['busy'], 'titles': ['x']})
        assert busy.status_code == 409 and busy.json()['error']['code'] == 'EXPORT_IN_PROGRESS'
        assert 'internal words' not in busy.text
        calls = len(seen)
        assert c.post(f'/api/v1/conversations/{conversation}/outputs/out_x/export', headers=h,
                      json={}).status_code == 404
        assert c.post(f'/api/v1/conversations/conv_{"d" * 32}/outputs/{OUTPUT}/export', headers=h,
                      json={}).status_code == 404  # another conversation (not this owner's)
        assert c.post(url, headers=h, json={'columns': ['a'], 'extra': 1}).status_code == 422
        assert len(seen) == calls  # none of these reached Orc
