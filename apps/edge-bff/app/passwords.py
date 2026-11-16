"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md section 4 "Registration rules"): the password and phone rules.

- A password is 8 to 256 characters (user decision; NIST SP 800-63B-4 and OWASP ask 15 without MFA, recorded in the
  contract); every character is allowed and no composition rule applies.
- A password found in Pwned Passwords is refused. The check uses the k-anonymity range API: only the first 5 hex digits
  of the SHA-1 leave EDGE (GET https://api.pwnedpasswords.com/range/<5 hex>, Add-Padding: true, 2 s timeout), and the
  suffix is compared here; padded rows (count 0) never match. When the API cannot answer, the password is accepted and
  PWNED_CHECK_UNAVAILABLE is logged (fail-open, the contract's recorded decision).
- A phone is normalised to E.164; an Indonesian 08... becomes +628...; it is not verified.
"""
import hashlib
import json
import logging
import re

import httpx

logger = logging.getLogger('edge_bff.passwords')

MIN_LENGTH, MAX_LENGTH = 8, 256
RANGE_URL = 'https://api.pwnedpasswords.com/range/'
TIMEOUT = 2.0
E164 = re.compile(r'\+[1-9][0-9]{6,14}')


def length_problem(password):
    """None when the length is allowed, else the reason (shown to the person)."""
    if not isinstance(password, str) or not MIN_LENGTH <= len(password) <= MAX_LENGTH:
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
    digest = hashlib.sha1(password.encode('utf-8', 'surrogatepass')).hexdigest().upper()
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
