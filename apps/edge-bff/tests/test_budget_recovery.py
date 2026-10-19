"""Real BFF auth/queue/SSE plus browser interactions. The upstream is a fixture, never paid inference."""
import copy

import pytest

from test_answer_view import FIXTURES, FixtureOrc, fixture_server  # noqa: F401
from test_composer_layout import device_page  # noqa: F401
from test_visual import capture, sign_in, submit


def test_presentation_retry_preserves_model_and_level_through_the_queue(fixture_server, device_page, monkeypatch):
    origin, orc = fixture_server
    page, touch, name = device_page
    failed = {"status":"FAILED", "response":None,
              "error":{"code":"PROVIDER_TIMEOUT", "user_message":"Penulisan jawaban belum selesai."},
              "execution":{"model":"deepseek/deepseek-v4.1-flash", "reasoning_level":"max",
                 "token_budget":{"total_output_tokens":96000,"reasoning_max_tokens":None},
                 "presentation_recovery":{"available":True,"choices":[{
                    "presentation_retry_of":"original", "presentation_retry_step":"original-m4a",
                    "model":"deepseek/deepseek-v4.1-flash", "model_label":"DeepSeek V4.1 Flash", "reasoning_level":"max"}]}}}
    monkeypatch.setitem(FIXTURES, 'budget-failed', failed)
    original_run = FixtureOrc.run
    def run(self, owner, request_id, payload):
        result = original_run(self, owner, request_id, payload)
        if payload.get('presentation_retry_of'):
            result['execution'].update(token_budget={'total_output_tokens':96000,'reasoning_max_tokens':None},
                model_calls=[{'requested_model':payload['model'],'served_model':payload['model'],
                              'reasoning_level':payload['reasoning_level'],'sent_reasoning':{'effort':'max'},
                              'max_output_tokens':96000,'phase':'presentation'}])
        return result
    monkeypatch.setattr(FixtureOrc, 'run', run)
    sign_in(page, origin)
    submit(page, 'fx:budget-failed')
    retry = page.get_by_role('button', name='Retry presentation · DeepSeek V4.1 Flash · Max', exact=True)
    retry.wait_for()
    assert page.get_by_text('Penulisan jawaban belum selesai.', exact=True).is_visible()
    assert page.get_by_text('Retry writing from these saved results only.', exact=False).is_visible()
    page.get_by_role('button', name='Retry', exact=True).click()  # full retry fills the composer without dispatch
    assert page.evaluate("JSON.parse(localStorage.getItem('edge-model-choice')).reasoning_level") == 'max'
    assert len(orc.calls) == 1
    capture(page, 'budget-' + name + '-retry-available')
    if touch:
        retry.tap()
    else:
        retry.click()
    page.locator('article.result').wait_for()
    assert len(orc.calls) == 2
    payload = orc.calls[-1][2]
    assert payload['presentation_retry_of'] == 'original' and payload['presentation_retry_step'] == 'original-m4a'
    assert payload['model'] == 'deepseek/deepseek-v4.1-flash' and payload['reasoning_level'] == 'max'
    assert payload['conversation_id'] == next(iter(orc.saved.values()))['conversation_id']
    assert '96,000 tokens per call' in page.locator('article.result').inner_text()
    assert 'A 48k/48k split is not guaranteed' in page.locator('article.result').inner_text()
    page.get_by_text('AI call settings', exact=True).click()
    assert page.get_by_text('96.000', exact=True).count() >= 1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(page, 'budget-' + name + '-sent-settings')
    page.reload()
    page.get_by_placeholder('Ask a research question…').wait_for()
    if page.viewport_size['width'] <= 1050:
        page.get_by_role('button', name='Open history', exact=True).click()
    page.locator('.conversation-list .conversation').first.click()
    page.locator('article.result').wait_for()
    assert len(orc.calls) == 2  # reload/history did not dispatch or recalculate
