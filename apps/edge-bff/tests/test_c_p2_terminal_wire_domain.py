"""EXEC-MU-ACCOUNTS ultracode re-check of Phase 2 (checker C-P2, 2026-11-18): the Phase 2 value model against the
Phase 3c wire (CONTRACT.md 8a "Value shapes", 8b "3c in detail").

Phase 2 accepts any non-negative integer for a limit and any array of strings for a list (capability_value_check,
principal.valid_value), and reads a value it cannot read as the most restrictive one, a limit 0 and a list []
(principal.RESTRICTIVE; ERRORS M480 C1 F1). terminal-api's x-terminal-capabilities takes history_days only as null or
1..36600 and tickers only as ^[A-Z0-9]{1,12}$ (apps/terminal-api/app/entitlements.py parse_capabilities), and answers
any other header 400 invalid_owner_headers. edge-bff builds the header from the principal for every Terminal call
(app/terminal_access.py capabilities_header, main.py forward_terminal, pages.py PageFiles), so one such value fails
every Terminal and page-file call of the account with terminal-api's internal 400, never a named CAPABILITY_REQUIRED.

The rule this file holds: for every value Phase 2 accepts or produces for the Terminal capabilities, edge-bff either
refuses before terminal-api in the contract's shape (403 CAPABILITY_REQUIRED, 429 LIMIT_REACHED) or sends a header
terminal-api accepts. It skips until Phase 3c's app/terminal_access.py and terminal-api's entitlements.py exist.
"""
import importlib.util
from pathlib import Path

import pytest

from app.errors import Refusal
from app.principal import account_principal, valid_value

terminal_access = pytest.importorskip('app.terminal_access')
ROOT = Path(__file__).resolve().parents[3]
ENTITLEMENTS = ROOT / 'apps/terminal-api/app/entitlements.py'
if not ENTITLEMENTS.exists():
    pytest.skip('terminal-api entitlements.py (Phase 3c) is not in this tree', allow_module_level=True)
_spec = importlib.util.spec_from_file_location('terminal_api_entitlements', ENTITLEMENTS)
entitlements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entitlements)
KNOWN = terminal_access.DATASET_IDS

BASE = {'terminal.view': {'kind': 'flag', 'value': True},
        'terminal.dataset': {'kind': 'items', 'value': {'ids': ['price']}}}
CASES = {
    # values the trigger accepts and Phase 2's own tests call "the right shape" (test_phase2_fix_round.py)
    'history_days 0': {'terminal.history_days': {'kind': 'limit', 'value': 0}},
    'history_days 40000': {'terminal.history_days': {'kind': 'limit', 'value': 40000}},
    'tickers lower case': {'terminal.tickers': {'kind': 'list', 'value': ['bbca']}},
    'tickers with a space': {'terminal.tickers': {'kind': 'list', 'value': [' BBCA']}},
    'tickers empty name': {'terminal.tickers': {'kind': 'list', 'value': ['BBCA', '']}},
    # a value that cannot be read: Phase 2 reads it as 0 (RESTRICTIVE), the most restrictive value
    'history_days malformed': {'terminal.history_days': {'kind': 'limit', 'value': '730'}},
}


def principal(extra):
    row = {'user_id': 9, 'owner_key': 'u_' + 'a' * 24, 'username': 'free1', 'role': 'user', 'status': 'active',
           'plan_key': 'free', 'grants': {**BASE, **extra}, 'versions': {}, 'mfa_passed_at': None}
    return account_principal(row)


@pytest.mark.parametrize('name', sorted(CASES))
def test_a_value_phase_2_accepts_never_breaks_the_terminal_header(name):
    extra = CASES[name]
    key, = extra
    if name != 'history_days malformed':
        assert valid_value(extra[key]['kind'], extra[key]['value'])          # Phase 2 takes it as it is
    p = principal(extra)
    try:
        header = terminal_access.capabilities_header(p)
    except Refusal as refused:                       # refused before terminal-api, in the contract's shape: passes
        assert (refused.status, refused.code) in ((403, 'CAPABILITY_REQUIRED'), (429, 'LIMIT_REACHED')), refused.code
        return
    try:
        caps = entitlements.parse_capabilities(header, KNOWN)
    except entitlements.HeaderError as e:
        pytest.fail(f'{name}: edge-bff sends {header} and terminal-api refuses it 400 invalid_owner_headers '
                    f'(field {e.field}): every Terminal call of this account fails')
    # what terminal-api then serves is never wider than the principal's own value
    value = p.limit(key)
    if key == 'terminal.tickers':
        assert caps.tickers is not None and caps.tickers <= {v.strip().upper() for v in value}
    else:
        assert caps.history_days is not None and caps.history_days <= value
