"""User 2026-10-21 (iPhone screenshot): a completed answer's head says "EDGE" only (any other status stays named,
e.g. "EDGE · Limited"), and the phone's model picker shows the model's name and reasoning level beside its logo, as the
desktop does, without pushing the send button off the box."""
from test_answer_view import article, fixture_server  # noqa: F401 (fixture)
from test_composer_layout import device_page  # noqa: F401 (fixture)
from test_visual import capture, saved, sign_in, submit


def test_a_completed_answer_says_edge_only_and_the_picker_names_model_and_level(fixture_server, device_page):
    origin, _ = fixture_server
    page, touch, name = device_page
    sign_in(page, origin)
    submit(page, 'fx:answer_table')
    saved(page)
    kicker = article(page).locator('.result-kicker')
    assert kicker.text_content() == 'EDGE' and kicker.locator('.edge-badge').count() == 0
    trigger = page.locator('.composer .edge-model-trigger:not([disabled])')
    trigger.wait_for()
    shown = trigger.evaluate("""t => { const box = n => n.getBoundingClientRect(), vis = n => !!n && getComputedStyle(n).display !== 'none' && box(n).width > 0;
      const name = t.querySelector('.edge-model-name'), level = t.querySelector('.edge-model-level'),
            send = document.querySelector('.composer [aria-label="Send"], .composer button[type=submit]') || [...document.querySelectorAll('.composer button')].pop(),
            composer = document.querySelector('.composer');
      return {name: vis(name) && name.textContent, level: vis(level) && level.textContent, logo: vis(t.querySelector('.edge-model-logo')),
              sendInside: box(send).right <= box(composer).right + 0.5, overlap: box(t).right > box(send).left,
              overflow: document.documentElement.scrollWidth - innerWidth}; }""")
    assert shown['logo'] and shown['name'] and shown['level'] == 'High', (name, shown)
    assert shown['sendInside'] and not shown['overlap'] and shown['overflow'] <= 0, (name, shown)
    capture(page, f'ui-1021-{name}')


def test_another_status_stays_named(fixture_server, device_page):
    origin, orc = fixture_server
    page, _, _ = device_page
    sign_in(page, origin)
    original = orc.run

    def limited(owner, request_id, payload):
        result = original(owner, request_id, payload)
        result['status'] = 'LIMITED'
        return result
    orc.run = limited
    try:
        submit(page, 'fx:answer_table')
        saved(page)
    finally:
        orc.run = original
    kicker = page.locator('article.result').last.locator('.result-kicker')
    # MONITOR-REVAMP (AI_revamp.html .kick): "EDGE", then the status as a pill
    assert kicker.text_content() == 'EDGELimited' and kicker.locator('.edge-badge').text_content() == 'Limited'
