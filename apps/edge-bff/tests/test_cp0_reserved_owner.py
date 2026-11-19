"""Checker C-P0 (EXEC-MU-ACCOUNTS Phase 0, CONTRACT.md sections 1 and 7; ERRORS M475): EDGE_OWNER may be an owner key
Orc reserves for tests.

market-ai-orc lets MARKET_AI_ORC_TEST_KEY (orc-test-runner) name exactly the owners golden-*, test-* and someone-else
(conversations.py TEST_OWNER_RE); the boundary holds only while no EDGE account has such a key. A server-made key is
'u_' + hex (accounts.py new_owner_key) and the users trigger refuses the reserved keys
(20261116_003 users_owner_key_rules). EDGE_OWNER, the one key that is configured, is checked only against Orc's general
shape (config.py validate: [A-Za-z0-9._:@-]{1,128}). With the switch off a refused seed is only logged
(main.py lifespan: account_seed_failed) and the switch-off principal still runs as EDGE_OWNER (principal.py resolve),
so EDGE_OWNER=golden-x would make user #1's conversations, runs, progress, exports and manual steps readable with the
test key. 'default' is Orc's old shared owner (M475).
"""
import dataclasses

import pytest

from app.accounts import reserved_owner


@pytest.mark.parametrize('owner', ['golden-suite', 'test-x', 'someone-else', 'default'])
def test_edge_owner_is_never_a_reserved_owner_key(settings, owner):
    assert reserved_owner(owner) or owner == 'default'
    with pytest.raises(ValueError):
        dataclasses.replace(settings, owner=owner, admin_owners=(owner,)).validate()


# ---- fix round (verification/edge_multiuser/fix_round/auth.md, R1-3) ---------------------------------------------------
# The refuters' correction: the check must not refuse edge-private (the live EDGE_OWNER and the seed's own key, which
# accounts.reserved_owner also reserves), so it is keyed on Orc's test-owner rule and 'default' only.

@pytest.mark.parametrize('owner', ['edge-private', 'local-test-owner', 'owner-1', 'golden', 'testing-x'])
def test_an_owner_key_orc_does_not_reserve_still_validates(settings, owner):
    dataclasses.replace(settings, owner=owner, admin_owners=(owner,)).validate()


def test_an_admin_owner_orc_reserves_is_refused_too(settings):
    with pytest.raises(ValueError, match='EDGE_ADMIN_OWNERS'):
        dataclasses.replace(settings, admin_owners=(settings.owner, 'golden-suite')).validate()


def test_edge_bff_reads_the_same_test_owner_rule_as_market_ai_orc():
    """One rule in two services (market-ai-orc app/conversations.py TEST_OWNER_RE, edge-bff accounts.ORC_TEST_OWNER):
    the pattern texts stay the same, so the boundary cannot move in one service only."""
    import re
    from pathlib import Path
    from app.accounts import ORC_TEST_OWNER
    source = (Path(__file__).resolve().parents[2] / 'market-ai-orc/app/conversations.py').read_text()
    orc = re.search(r'TEST_OWNER_RE = re\.compile\(r"\^\((.+)\)\$"\)', source).group(1)
    assert orc == ORC_TEST_OWNER.pattern
