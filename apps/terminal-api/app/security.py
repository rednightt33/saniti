import hashlib
import hmac
import ipaddress
import secrets

# Same verifier format as edge-bff (apps/edge-bff/app/security.py) and the check in terminal.subscriber.
_DUMMY = 'scrypt$' + '0' * 32 + '$' + '0' * 64


def password_verifier(password: str) -> str:
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f'scrypt${salt.hex()}${value.hex()}'


def verify_password(password: str, verifier: str | None) -> bool:
    """Constant work whether or not the account exists (an unknown email is checked against a dummy verifier)."""
    try:
        scheme, salt, value = (verifier or _DUMMY).split('$')
        if scheme != 'scrypt' or len(password) > 1024:
            return False
        derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return verifier is not None and hmac.compare_digest(derived.hex(), value)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def same_secret(given: str | None, expected: str) -> bool:
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def client_ip(forwarded_for: str | None, peer: str | None) -> str | None:
    """Railway's edge puts the client first in X-Forwarded-For; anything that is not an IP is dropped."""
    for candidate in ((forwarded_for or '').split(',')[0].strip(), peer or ''):
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None
