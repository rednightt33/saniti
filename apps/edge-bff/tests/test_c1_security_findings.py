"""C1 adversarial security check of EXEC-MU-ACCOUNTS Phase 0: failing tests for the findings (no fix here).

Each test names the contract rule it holds the code to (verification/edge_multiuser/access_tiers/CONTRACT.md).
"""
import asyncio

import httpx

from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}


async def _burst(app, n, login='owner', password='wrong'):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
        async def one():
            r = await client.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': login, 'password': password})
            return r.status_code
        return await asyncio.gather(*[one() for _ in range(n)])


def test_c1_concurrent_burst_cannot_exceed_the_sign_in_limit(settings, store):
    """CONTRACT.md section 4 "Throttle": 10 failures per login per 15 min. The check (throttle.retry_after) runs before
    the password check and the count after it (main.py sign_in), so the tries of a concurrent burst all pass the check
    before any is counted: 40 parallel guesses against one login are all evaluated. OWASP Authentication cheat sheet:
    the attempt must be counted atomically with the decision. At most 10 guesses may reach the password check."""
    app = create_app(settings, store, FakeOrc())
    codes = asyncio.run(_burst(app, 40))
    guessed = sum(1 for c in codes if c == 401)
    assert guessed <= 10, f'{guessed} of 40 concurrent guesses reached the password check (limit 10): {codes}'
