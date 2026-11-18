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
