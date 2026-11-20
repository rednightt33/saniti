"""The live checker after the switch-on (F3): Railway labelled every edge-bff log line "error" (they go to stderr and
carry no level), so a real failure (email_send_failed, housekeeping_failed) could not be told from a start-up line.
Railway reads a JSON line's `level`; every edge_bff event is a JSON object (json.dumps of a dict), so the one formatter
of edge-bff's handlers writes it with Railway's `level` first: debug, info, warn, error. Other lines stay as they are.
The streams are unchanged (stderr), so nothing that reads a process's stdout gets log lines."""
import json
import logging

LEVELS = {logging.DEBUG: 'debug', logging.INFO: 'info', logging.WARNING: 'warn', logging.ERROR: 'error',
          logging.CRITICAL: 'error'}


def level_of(record):
    return LEVELS.get(record.levelno, 'error' if record.levelno > logging.ERROR else 'info')


class RailwayLevels(logging.Formatter):
    """The message as it is; a JSON object message with `level` added first (never one it already has)."""

    def format(self, record):
        message = super().format(record)
        if message.startswith('{') and message.endswith('}'):
            try:
                body = json.loads(message)
            except ValueError:
                return message
            if isinstance(body, dict) and 'level' not in body:
                return json.dumps({'level': level_of(record), **body})
        return message


def handler():
    """A stderr handler with RailwayLevels, for a module logger that has none (main.py, backtest.py, mailer.py, wake.py)."""
    out = logging.StreamHandler()
    out.setFormatter(RailwayLevels('%(message)s'))
    return out
