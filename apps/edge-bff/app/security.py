import hashlib
import hmac
import re
import secrets
import time
import unicodedata

# ERRORS R2-29 (OWASP Password Storage Cheat Sheet: scrypt N=2^17, r=8, p=1, or an equivalent; at 16 MiB the equivalent
# is N=2^14, r=8, p=5): the cost (N, r, p) of every new verifier. A verifier names its cost
# ('scrypt$n=16384,r=8,p=5$<salt>$<hash>'); one without (the form before R2-29, 'scrypt$<salt>$<hash>') has LEGACY's and
# is still accepted, then replaced at the account's next sign-in (accounts.py create_session `rehash`). Only the costs
# in COSTS are read, so a verifier cannot ask for an unbounded derivation.
COST = (16384, 8, 5)
LEGACY = (16384, 8, 1)
COSTS = frozenset({COST, LEGACY})
VERIFIER = re.compile(r'scrypt\$(?:n=([0-9]{1,7}),r=([0-9]{1,2}),p=([0-9]{1,2})\$)?([0-9a-f]{32})\$([0-9a-f]{64})')

# re-check R2-22: the session and registration cookies. On a Secure (https) origin their names carry the __Host- prefix:
# the browser then keeps them only when Secure, Path=/ and without Domain, so no other host of the domain (a sibling
# site under the live domain, a dangling name) can set or overwrite them ("cookie tossing"). A local http origin keeps
# the plain names (a __Host- cookie needs Secure).
SESSION_COOKIE = 'edge_session'
REGISTRATION_COOKIE = 'edge_registration'
REGISTRATION_PATH = '/api/v1/auth/'             # the registration cookie's path where no prefix applies
# The A2 fix (ERRORS M513 A2, M517; CONTRACT.md section 4 "Throttle"): the account's own browser and a password reset's
# browser, on the same path as the registration cookie (registration_path)
DEVICE_COOKIE = 'edge_device'
RESET_COOKIE = 'edge_reset'


def cookie_name(name, secure):
    """The cookie's name on this origin: '__Host-' + name when Secure, else name."""
    return '__Host-' + name if secure else name


def registration_path(secure):
    """A __Host- cookie must have Path=/; without the prefix the registration cookie stays on the auth routes."""
    return '/' if secure else REGISTRATION_PATH


def normal_password(password: str) -> str:
    """EXEC-MU-ACCOUNTS Phase 1 fix round (ERRORS M478, C1 P1-L3; NIST SP 800-63B-4): a password is NFKC-normalised
    before hashing and before its length and breach checks, so the same password typed on another keyboard (é as one code
    point or as e + a combining accent) gives the same verifier."""
    return unicodedata.normalize('NFKC', password)


def _derive(text, salt, cost):
    n, r, p = cost
    return hashlib.scrypt(text.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


def _scrypt(text, salt):
    """One derivation at the current cost: the work every password check pays (tests hold it to fill the pool)."""
    return _derive(text, salt, COST)


def password_verifier(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = _scrypt(normal_password(password), salt)
    n, r, p = COST
    return f'scrypt$n={n},r={r},p={p}${salt.hex()}${value.hex()}'


def verifier_parts(verifier):
    """(cost, salt bytes, hash hex) of a verifier of a cost in COSTS, else None."""
    found = VERIFIER.fullmatch(verifier) if isinstance(verifier, str) else None
    if found is None:
        return None
    cost = tuple(int(x) for x in found.group(1, 2, 3)) if found.group(1) else LEGACY
    return (cost, bytes.fromhex(found.group(4)), found.group(5)) if cost in COSTS else None


def is_verifier(verifier) -> bool:
    """The shape of a verifier this module makes or reads (EDGE_PASSWORD_VERIFIER, config.py)."""
    return verifier_parts(verifier) is not None


def needs_rehash(verifier) -> bool:
    """True when a readable verifier is not at the current cost (it is replaced at the next sign-in)."""
    parts = verifier_parts(verifier)
    return parts is not None and parts[0] != COST


def _matches(text, salt, value, cost):
    """One form checked at the verifier's cost and padded to the current cost (scrypt's work grows with p, so p=1 plus
    p=4 is the work of p=5): a check costs the same whatever the verifier's age, so the time tells nothing about it
    (ERRORS M478 N1: the time of a sign-in tells nothing about the account)."""
    if cost == COST:
        derived = _scrypt(text, salt)
    else:
        derived = _derive(text, salt, cost)
        if cost[:2] == COST[:2] and cost[2] < COST[2]:
            _derive(text, salt, (COST[0], COST[1], COST[2] - cost[2]))
    return hmac.compare_digest(derived.hex().encode(), value.encode())


def verify_password(password: str, verifier: str) -> bool:
    """The NFKC form first; a legacy verifier made from the text as typed (before normalisation; e.g. the configured
    EDGE_PASSWORD_VERIFIER) is still accepted. When the two forms differ both are always derived, so the number of
    derivations depends only on the text typed, never on which form (or whether any) matched."""
    try:
        parts = verifier_parts(verifier)
        if parts is None or len(password) > 1024:
            return False
        cost, salt, value = parts
        normal = normal_password(password)
        ok = _matches(normal, salt, value, cost)
        if normal != password:
            ok = _matches(password, salt, value, cost) or ok
        return ok
    except (ValueError, TypeError, UnicodeEncodeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---- the account's own browsers (the A2 fix, ERRORS M513 A2 and M517) ------------------------------------------------
# NIST SP 800-63B 5.2.2 and OWASP's "device cookies": a limit a stranger can reach by naming a login or an address must
# not lock out the account's owner. A browser where the account's password was proved gets a device token, signed with
# EDGE_SESSION_SECRET over the account's id, the time and the account's current verifier, so it stops being valid when
# the password changes (a change, a reset, a rehash) and after DEVICE_SECONDS. It proves only that this browser once
# signed the account in with its current password: it lets that browser past the limits strangers can fill (the
# account's lock of consecutive failed passwords, the address's daily code emails), under limits of its own
# (throttle.DEVICE_SIGNIN, DEVICE_MAIL); it never signs anyone in. Nothing is stored: the token is checked against the
# account's row at the moment it is used.
DEVICE_SECONDS = 180 * 86400
DEVICE_TOKEN = re.compile(r'([1-9][0-9]{0,18})\.([0-9]{10})\.([0-9a-f]{32})\.([0-9a-f]{64})')
DEVICE_LABEL = b'edge_bff.device_token\x00'


def _device_mac(secret: str, user_id: int, issued: int, nonce: str, verifier: str) -> str:
    return hmac.new(secret.encode(), DEVICE_LABEL + f'{user_id}.{issued}.{nonce}'.encode() + b'\x00'
                    + hashlib.sha256((verifier or '').encode()).digest(), hashlib.sha256).hexdigest()


def device_token(secret: str, user_id: int, verifier: str, now=None) -> str:
    """A new device token of the account (a fresh nonce each time), bound to its current verifier."""
    issued = int(time.time() if now is None else now)
    nonce = secrets.token_hex(16)
    return f'{user_id}.{issued}.{nonce}.{_device_mac(secret, user_id, issued, nonce, verifier)}'


def device_user(token) -> int | None:
    """The account id a device token names, unchecked (device_of checks it against that account's row); None when the
    text is not a device token."""
    m = DEVICE_TOKEN.fullmatch(token or '') if isinstance(token, str) else None
    return int(m.group(1)) if m else None


def device_of(secret: str, token, user_id: int, verifier: str, now=None) -> str | None:
    """The device's nonce when `token` is a device token of this account, signed over its current verifier and not older
    than DEVICE_SECONDS (nor more than 5 minutes ahead of this clock); else None."""
    m = DEVICE_TOKEN.fullmatch(token or '') if isinstance(token, str) else None
    if m is None or user_id is None or int(m.group(1)) != int(user_id) or not verifier:
        return None
    issued, at = int(m.group(2)), time.time() if now is None else now
    if not at - DEVICE_SECONDS <= issued <= at + 300:
        return None
    if not hmac.compare_digest(m.group(4), _device_mac(secret, int(user_id), issued, m.group(3), verifier)):
        return None
    return m.group(3)


def csrf_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def same_ascii(given, expected):
    """A header value equals the expected ASCII text, compared as bytes in constant time; a non-ASCII value is simply
    unequal (ERRORS M478, C1 P1-L4: compare_digest raises on non-ASCII str)."""
    return isinstance(given, str) and given.isascii() and hmac.compare_digest(given.encode(), expected.encode())
