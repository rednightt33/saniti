"""The live checker after the switch-on (F3): Railway labelled every edge-bff log line "error" (stderr, no level), so a
real failure could not be told from a start-up line. Each JSON line of edge-bff's handlers carries Railway's `level`
(app/logs.py); a plain line stays as it is."""
import json
import logging
from pathlib import Path

from app import backtest, logs, mailer, wake
from app import main


def line(level, message):
    return logs.RailwayLevels('%(message)s').format(logging.LogRecord('edge_bff.x', level, __file__, 1, message, None, None))


def test_a_json_line_carries_railways_level_first():
    out = line(logging.INFO, json.dumps({'event': 'startup_done', 'site': 'live'}))
    assert json.loads(out) == {'level': 'info', 'event': 'startup_done', 'site': 'live'}
    assert out.startswith('{"level": "info"')
    assert json.loads(line(logging.WARNING, '{"event": "email_send_failed"}'))['level'] == 'warn'
    assert json.loads(line(logging.ERROR, '{"event": "housekeeping_failed"}'))['level'] == 'error'
    assert json.loads(line(logging.INFO, '{"event": "x", "level": "debug"}'))['level'] == 'debug'   # its own kept


def test_a_plain_or_broken_line_is_written_as_it_is():
    assert line(logging.INFO, 'Started server process') == 'Started server process'
    assert line(logging.INFO, '{not json}') == '{not json}'
    assert line(logging.INFO, '[1, 2]') == '[1, 2]'


def test_every_module_handler_uses_it():
    """The handler a module adds when none is set up (under pytest the root holds the capture handler, so it is not
    added here): each one is logs.handler(), never a plain StreamHandler."""
    for module in (main, backtest, mailer, wake):
        source = Path(module.__file__).read_text()
        assert 'logs.handler()' in source and 'logging.StreamHandler()' not in source, module.__name__
    assert isinstance(logs.handler().formatter, logs.RailwayLevels)
