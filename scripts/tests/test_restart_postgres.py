"""EXEC-PG-RESTART-CRON (user go 2026-11-03: "Go langkah 1–9, tafsiran toggle benar, setuju"): the decisions of
scripts/restart_postgres.py --cron. No Railway, database or Telegram call is made here: every outside call is replaced."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import restart_postgres as rp  # noqa: E402

TIMES = rp.run_times('09:45,20:45')


def utc(h, m):
    return datetime(2026, 11, 4, h, m, tzinfo=timezone.utc)


def test_cron_is_the_product_of_the_listed_times():
    assert rp.cron_for(TIMES) == '45 2,13 * * *'
    assert rp.cron_for(rp.run_times('09:30,20:45')) == '30,45 2,13 * * *'


@pytest.mark.parametrize('now, manual, kind', [
    (utc(2, 46), False, 'scheduled'),          # 09:46 WIB
    (utc(13, 50), False, 'scheduled'),         # 20:50 WIB
    (utc(13, 50), True, 'manual-telegram'),    # the button wins
    (utc(5, 10), False, 'manual-railway'),     # dashboard Run Now
])
def test_run_kind(now, manual, kind):
    assert rp.run_kind(TIMES, now, manual) == kind


def test_a_tick_that_is_not_a_listed_time_does_nothing():
    times = rp.run_times('09:30,20:45')        # cron 30,45 2,13: 09:45 and 20:30 WIB are extra ticks
    assert rp.run_kind(times, utc(13, 31), False) == 'tick'
    assert rp.run_kind(times, utc(2, 31), False) == 'scheduled'


def test_own_cron_is_left_out_of_the_cron_guard():
    crons = {'postgres-memory-cron': '45 2,13 * * *', 'terminal-publisher': '0,30 0,1,12 * * *'}
    assert rp.crons_due(crons, utc(13, 45), 45, skip='postgres-memory-cron') == []
    assert rp.crons_due(crons, utc(13, 10), 45, skip='postgres-memory-cron')     # 12:30 publisher within 45 min
    assert rp.in_b6(utc(13, 10)) and not rp.in_b6(utc(13, 45))


@pytest.fixture
def cron(monkeypatch):
    """A cron run with every outside call replaced; returns the notifications and whether a restart happened."""
    state = {'sent': [], 'restarted': False, 'checks': [], 'kind': 'scheduled', 'auto': True}

    def fake_checks(args):
        out = state['checks'].pop(0) if len(state['checks']) > 1 else state['checks'][0]
        return dict(out, refusals=[f'r:{c}' for c in out['reasons']]), {'Postgres': 'pg'}

    monkeypatch.setattr(rp, 'checks', fake_checks)
    monkeypatch.setattr(rp, 'run_kind', lambda times, now, manual: state['kind'])
    monkeypatch.setattr(rp, 'telegram_manual', lambda: False)
    monkeypatch.setattr(rp, 'auto_on', lambda: state['auto'])
    monkeypatch.setattr(rp, 'notify', lambda kind, run_id, event, details: state['sent'].append((event, details)))
    monkeypatch.setattr(rp, 'memory_gb', lambda services, since_minutes=30: {'ts': 9e12, 'value': 0.1})
    monkeypatch.setattr(rp.time, 'sleep', lambda s: None)

    def fake_restart(services):
        state['restarted'] = True
        return {'deployment': 'd', 'start_before': 'a', 'start_after': 'b', 'seconds': 14, 'edge_bff_ready': 200}
    monkeypatch.setattr(rp, 'restart', fake_restart)
    monkeypatch.setenv('PG_RESTART_MODE', 'apply')
    monkeypatch.setenv('PG_RESTART_TIMES_WIB', '09:45,20:45')
    return state


def guards(memory=3.9, reasons=()):
    return {'postgres_memory_gb': memory, 'reasons': list(reasons)}


def events(state):
    return [e for e, _ in state['sent']]


def test_scheduled_with_cache_restarts_and_reports(cron):
    cron['checks'] = [guards()]
    assert rp.cron_main() == 0
    assert cron['restarted'] and events(cron) == ['started', 'success']
    assert cron['sent'][1][1]['seconds'] == 14 and cron['sent'][1][1]['memory_after_gb'] == 0.1


def test_scheduled_with_low_memory_or_auto_off_is_quiet(cron):
    cron['checks'] = [guards(memory=0.3, reasons=['memory_low'])]
    assert rp.cron_main() == 0 and not cron['restarted'] and events(cron) == []
    cron['checks'], cron['auto'] = [guards()], False
    assert rp.cron_main() == 0 and not cron['restarted'] and events(cron) == []


def test_manual_ignores_memory_and_auto_but_not_the_guards(cron):
    cron['kind'], cron['auto'] = 'manual-telegram', False
    cron['checks'] = [guards(memory=0.2, reasons=['memory_low'])]
    assert rp.cron_main() == 0
    assert cron['restarted'] and events(cron) == ['manual', 'started', 'success']
    cron['restarted'], cron['sent'] = False, []
    cron['checks'] = [guards(reasons=['cron_due'])]
    assert rp.cron_main() == 0
    assert not cron['restarted'] and events(cron) == ['manual', 'refused']
    assert cron['sent'][1][1]['reasons'] == ['cron_due']


def test_a_user_run_is_waited_for_then_the_restart_goes(cron):
    cron['checks'] = [guards(reasons=['user_runs']), guards(reasons=['user_runs']), guards()]
    assert rp.cron_main() == 0
    assert cron['restarted'] and events(cron) == ['started', 'success']
    assert cron['sent'][0][1]['waited_minutes'] == 10


def test_a_user_run_past_the_wait_refuses(cron, monkeypatch):
    monkeypatch.setenv('PG_RESTART_WAIT_MINUTES', '10')
    cron['checks'] = [guards(reasons=['user_runs'])]
    assert rp.cron_main() == 0
    assert not cron['restarted'] and events(cron) == ['refused']


def test_check_mode_never_restarts_and_says_what_it_would_do(cron, monkeypatch):
    monkeypatch.setenv('PG_RESTART_MODE', 'check')
    cron['checks'] = [guards()]
    assert rp.cron_main() == 0
    assert not cron['restarted'] and events(cron) == ['check'] and cron['sent'][0][1]['would_restart'] is True
    cron['sent'], cron['checks'] = [], [guards(memory=0.2, reasons=['memory_low'])]
    rp.cron_main()
    assert cron['sent'][0][1]['would_restart'] is False and cron['sent'][0][1]['reasons'] == ['memory_low']


def test_a_failed_restart_is_reported_and_exits_1(cron, monkeypatch):
    cron['checks'] = [guards()]
    monkeypatch.setattr(rp, 'restart', lambda services: (_ for _ in ()).throw(SystemExit('not back')))
    assert rp.cron_main() == 1
    assert events(cron) == ['started', 'failed'] and cron['sent'][1][1]['reasons'] == ['postgres_not_back']


def test_a_tick_does_nothing(cron):
    cron['kind'], cron['checks'] = 'tick', [guards()]
    assert rp.cron_main() == 0 and not cron['restarted'] and events(cron) == []


def test_every_report_passes_the_monitor_shape(cron, monkeypatch):
    """What the cron sends is what telegram-monitor accepts (the two files must agree)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/telegram-monitor'))
    tm = pytest.importorskip('telegram_monitor')
    cron['kind'] = 'manual-telegram'
    cron['checks'] = [guards(reasons=['user_runs']), guards()]
    rp.cron_main()
    monkeypatch.setenv('PG_RESTART_MODE', 'check')
    rp.cron_main()
    assert events(cron) == ['manual', 'started', 'success', 'manual', 'check']
    for event, details in cron['sent']:
        full = dict(details, kind='manual-telegram', event=event)
        tm.build_postgres_restart_message(tm.parse_postgres_restart(f'pg-restart-manual-telegram-20261104T0300-{event}',
                                                                    full))


# ERRORS M433: the Railway credential is the first one Railway accepts; none working is one NOT_RUN line, never a
# traceback after a job's success line.
class _Answer:
    def __init__(self, body):
        self.body = body

    def read(self):
        return rp.json.dumps(self.body).encode()


@pytest.fixture
def railway(monkeypatch):
    """Railway replaced: `accept` names the credential values it accepts; `seen` the (header, value) pairs sent."""
    state = {'accept': set(), 'seen': [], 'errors': None}
    for name, _ in rp.CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(rp._auth, 'name', None)

    def urlopen(req, timeout):
        sent = {k.lower(): v for k, v in req.header_items()}
        value = sent.get('project-access-token') or sent.get('authorization')
        state['seen'].append(value)
        if value not in state['accept']:
            raise rp.urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, None)
        if state['errors']:
            return _Answer({'data': None, 'errors': [{'message': state['errors']}]})
        return _Answer({'data': {'ok': True}})
    monkeypatch.setattr(rp.urllib.request, 'urlopen', urlopen)
    return state


def test_a_refused_project_token_falls_back_to_the_session_credential(railway, monkeypatch):
    monkeypatch.setenv('RAILWAY_TOKEN', 'stale-project-token')
    monkeypatch.setenv('RAILWAY_API_TOKEN', 'session-token')
    railway['accept'] = {'Bearer session-token'}
    assert rp.gql('query{ok}', {}) == {'ok': True}
    assert railway['seen'] == ['stale-project-token', 'Bearer session-token']
    assert rp._auth['name'] == 'RAILWAY_API_TOKEN'
    railway['seen'].clear()
    rp.gql('query{ok}', {})                                   # the one that worked is tried first afterwards
    assert railway['seen'] == ['Bearer session-token']


def test_the_cron_token_comes_first_and_is_sent_as_a_project_token(railway, monkeypatch):
    monkeypatch.setenv('RAILWAY_RESTART_TOKEN', 'cron-token')
    monkeypatch.setenv('RAILWAY_API_TOKEN', 'session-token')
    railway['accept'] = {'cron-token', 'Bearer session-token'}
    rp.gql('query{ok}', {})
    assert railway['seen'] == ['cron-token'] and rp._auth['name'] == 'RAILWAY_RESTART_TOKEN'


def test_an_error_that_is_not_about_the_credential_is_not_retried(railway, monkeypatch):
    monkeypatch.setenv('RAILWAY_TOKEN', 'project-token')
    monkeypatch.setenv('RAILWAY_API_TOKEN', 'session-token')
    railway['accept'] = {'project-token', 'Bearer session-token'}
    railway['errors'] = 'Deployment not found'
    with pytest.raises(SystemExit, match='Railway refused: Deployment not found'):
        rp.gql('query{ok}', {})
    assert railway['seen'] == ['project-token']


def test_no_working_credential_is_one_not_run_line(railway, monkeypatch, capsys):
    monkeypatch.setenv('RAILWAY_TOKEN', 'stale-project-token')
    monkeypatch.setattr(rp.sys, 'argv', ['restart_postgres.py', '--apply'])
    assert rp.main() == 4
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith('POSTGRES_RESTART NOT_RUN: ')
    assert 'RAILWAY_TOKEN' in lines[0] and 'stale-project-token' not in lines[0]   # names only, never a value
