"""The live checker after the switch-on (F7): scripts/railway_reference_consumers.py follows a consumer whose variable is
itself referenced, so the listing and --redeploy reach every hop (edge-bff-live read backtest-worker through edge-bff,
and only edge-bff was listed). No Railway call is made here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import railway_reference_consumers as rc  # noqa: E402

GRAPH = {
    'edge-bff': {'BACKTEST_TIMEOUT_SECONDS': ('backtest-worker', 'BACKTEST_TIMEOUT_SECONDS'),
                 'TERMINAL_PROXY_KEY': ('terminal-api', 'TERMINAL_PROXY_KEY')},
    'edge-bff-live': {'BACKTEST_TIMEOUT_SECONDS': ('edge-bff', 'BACKTEST_TIMEOUT_SECONDS'),
                      'TERMINAL_PROXY_KEY': ('terminal-api', 'TERMINAL_PROXY_KEY')},
    'orc-test-runner': {'ACCOUNT_NEW_X': ('edge-bff-live', 'BACKTEST_TIMEOUT_SECONDS')},
    'backtest-worker': {},
}


def test_a_chain_is_followed_to_its_end_nearest_first():
    found = rc.transitive_consumers(GRAPH, ('backtest-worker', 'BACKTEST_TIMEOUT_SECONDS'))
    assert [(s, n) for s, n, _ in found] == [('edge-bff', 'BACKTEST_TIMEOUT_SECONDS'),
                                             ('edge-bff-live', 'BACKTEST_TIMEOUT_SECONDS'),
                                             ('orc-test-runner', 'ACCOUNT_NEW_X')]
    assert rc.chain_text(found[1][2]) == ('${{edge-bff.BACKTEST_TIMEOUT_SECONDS}} <- '
                                          '${{backtest-worker.BACKTEST_TIMEOUT_SECONDS}}')


def test_direct_consumers_alone_when_nobody_reads_them_further():
    found = rc.transitive_consumers(GRAPH, ('terminal-api', 'TERMINAL_PROXY_KEY'))
    assert [(s, n) for s, n, _ in found] == [('edge-bff', 'TERMINAL_PROXY_KEY'), ('edge-bff-live', 'TERMINAL_PROXY_KEY')]
    assert rc.transitive_consumers(GRAPH, ('nobody', 'X')) == []


def test_a_reference_loop_ends():
    loop = {'a': {'X': ('b', 'X')}, 'b': {'X': ('a', 'X')}}
    assert [(s, n) for s, n, _ in rc.transitive_consumers(loop, ('a', 'X'))] == [('b', 'X')]   # the source itself is not its consumer
