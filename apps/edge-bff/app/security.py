import hashlib
import hmac
import secrets
import unicodedata


def normal_password(password: str) -> str:
    """EXEC-MU-ACCOUNTS Phase 1 fix round (ERRORS M478, C1 P1-L3; NIST SP 800-63B-4): a password is NFKC-normalised
    before hashing and before its length and breach checks, so the same password typed on another keyboard (é as one code
    point or as e + a combining accent) gives the same verifier."""
    return unicodedata.normalize('NFKC', password)


def _scrypt(text, salt):
    return hashlib.scrypt(text.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)


def password_verifier(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = _scrypt(normal_password(password), salt)
    return f'scrypt${salt.hex()}${value.hex()}'


def verify_password(password: str, verifier: str) -> bool:
    """The NFKC form first; a legacy verifier made from the text as typed (before normalisation; e.g. the configured
    EDGE_PASSWORD_VERIFIER) is still accepted. When the two forms differ both are always derived, so the number of
    derivations depends only on the text typed, never on which form (or whether any) matched."""
    try:
        scheme, salt, value = verifier.split('$')
        if scheme != 'scrypt' or len(password) > 1024:
            return False
        salt = bytes.fromhex(salt)
        normal = normal_password(password)
        ok = hmac.compare_digest(_scrypt(normal, salt).hex().encode(), value.encode())
        if normal != password:
            ok = hmac.compare_digest(_scrypt(password, salt).hex().encode(), value.encode()) or ok
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
