import hashlib
import hmac
import re
import secrets
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


def csrf_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def same_ascii(given, expected):
    """A header value equals the expected ASCII text, compared as bytes in constant time; a non-ASCII value is simply
    unequal (ERRORS M478, C1 P1-L4: compare_digest raises on non-ASCII str)."""
    return isinstance(given, str) and given.isascii() and hmac.compare_digest(given.encode(), expected.encode())
