"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md section 4 "Registration rules"): the password and phone rules.

- A password is 8 to 256 characters (user decision; NIST SP 800-63B-4 and OWASP ask 15 without MFA, recorded in the
  contract); every character is allowed and no composition rule applies.
- A password found in Pwned Passwords is refused. The check uses the k-anonymity range API: only the first 5 hex digits
  of the SHA-1 leave EDGE (GET https://api.pwnedpasswords.com/range/<5 hex>, Add-Padding: true, 2 s timeout), and the
  suffix is compared here; padded rows (count 0) never match. When the API cannot answer, the password is accepted and
  PWNED_CHECK_UNAVAILABLE is logged (fail-open, the contract's recorded decision).
- A phone is normalised to E.164; an Indonesian 08... becomes +628...; it is not verified.
- Where password work runs (ERRORS R2-37): every password derivation and Pwned Passwords call of a request (sign-in,
  registration, reset, change) runs on PasswordWork's own small thread pool, never on the event loop's default executor
  that every database call uses, so a burst of sign-ins with made-up logins cannot hold the signed-in users' requests.
  At most PasswordWork.LIMIT requests do password work at once (running or waiting for a thread); one more is answered
  503 SERVICE_UNAVAILABLE with Retry-After at once, so under a flood only password requests wait.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import json
import logging
import re

import httpx

from .errors import Refusal
from .security import normal_password

logger = logging.getLogger('edge_bff.passwords')


class PasswordWork:
    """The pool of password work (the module docstring). WORKERS threads (each derivation holds 16 MiB while it runs);
    LIMIT requests admitted at once; a request over it is refused 503 with Retry-After RETRY_SECONDS."""
    WORKERS, LIMIT, RETRY_SECONDS = 4, 16, 5

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=self.WORKERS, thread_name_prefix='edge-password')
        self.admitted = 0                       # read and changed on the event loop only

    @asynccontextmanager
    async def admitted_request(self):
        """One request's password work; 503 SERVICE_UNAVAILABLE when LIMIT requests already do password work."""
        if self.admitted >= self.LIMIT:
            logger.warning(json.dumps({'event': 'password_work_full', 'admitted': self.admitted}))
            raise Refusal(503, 'SERVICE_UNAVAILABLE', {'retry_after_s': self.RETRY_SECONDS},
                          {'Retry-After': str(self.RETRY_SECONDS)})
        self.admitted += 1
        try:
            yield self
        finally:
            self.admitted -= 1

    async def run(self, fn, *args):
        """fn(*args) on the pool's threads (a derivation, a Pwned Passwords call)."""
        return await asyncio.get_running_loop().run_in_executor(self.executor, fn, *args)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


MIN_LENGTH, MAX_LENGTH = 8, 256
RANGE_URL = 'https://api.pwnedpasswords.com/range/'
TIMEOUT = 2.0
E164 = re.compile(r'\+[1-9][0-9]{6,14}')


def length_problem(password):
    """None when the length is allowed, else the reason (shown to the person)."""
    if not isinstance(password, str) or not MIN_LENGTH <= len(normal_password(password)) <= MAX_LENGTH:
        return f'A password is {MIN_LENGTH} to {MAX_LENGTH} characters; any characters are allowed.'
    return None


def fetch_range(prefix):
    """The range API's answer for a 5-hex prefix (text), or None when it cannot answer in time."""
    try:
        answer = httpx.get(RANGE_URL + prefix, headers={'Add-Padding': 'true', 'User-Agent': 'edge-bff-password-check'},
                           timeout=TIMEOUT)
    except httpx.HTTPError:
        return None
    return answer.text if answer.status_code == 200 else None


def pwned(password, fetch=None):
    """True when Pwned Passwords holds the password; False when not, or when the API cannot answer (logged)."""
    digest = hashlib.sha1(normal_password(password).encode('utf-8', 'surrogatepass')).hexdigest().upper()
    text = (fetch or fetch_range)(digest[:5])
    if text is None:
        logger.warning(json.dumps({'event': 'PWNED_CHECK_UNAVAILABLE'}))
        return False
    for line in text.splitlines():
        suffix, _, count = line.strip().partition(':')
        if suffix.upper() == digest[5:] and count.strip().isdigit() and int(count) > 0:
            return True
    return False


def normal_phone(raw):
    """The phone in E.164, or None when it cannot be one. Spaces, dashes, dots and brackets are dropped; 08... and
    8... (Indonesian national numbers) become +628...; 62... becomes +62...; 00 becomes +."""
    if not isinstance(raw, str):
        return None
    digits = re.sub(r'[\s().-]', '', raw)
    if digits.startswith('00'):
        digits = '+' + digits[2:]
    elif digits.startswith('0'):
        digits = '+62' + digits[1:]
    elif digits.startswith('62') or digits.startswith('8'):
        digits = '+' + digits if digits.startswith('62') else '+62' + digits
    return digits if E164.fullmatch(digits) else None
