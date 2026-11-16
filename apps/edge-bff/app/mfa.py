"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 1 and 4 "Admin MFA"): the admin TOTP.

- The secret of an account is HMAC-SHA256(EDGE_MFA_KEY, user_id as 8 bytes big-endian || nonce)[:20]; only the random
  16-byte nonce is stored (edge_bff.mfa_totp), so a database leak alone yields no secret.
- RFC 6238 with SHA-1, 30 s steps, 6 digits; a code of the current step or one step either side is accepted, and only a
  step after the last one used (last_step), so a code is never accepted twice.
- Ten recovery codes (10 characters of base32, shown as xxxxx-xxxxx) are shown once at enrolment and stored as
  HMAC-SHA256(EDGE_MFA_KEY, 'recovery' || user_id || code); each works once.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS, DIGITS, WINDOW = 30, 6, 1
RECOVERY_CODES = 10
ISSUER = 'EDGE'
ALPHABET = 'abcdefghijklmnopqrstuvwxyz234567'


def secret_of(key, user_id, nonce):
    return hmac.new(key.encode(), int(user_id).to_bytes(8, 'big') + bytes(nonce), hashlib.sha256).digest()[:20]


def code_at(secret, step):
    digest = hmac.new(secret, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def step_now(clock=time.time):
    return int(clock()) // STEP_SECONDS


def matching_step(secret, code, now_step):
    """The step (now-1 .. now+1) whose code equals the given one, compared in constant time; None when none does."""
    code = (code or '').strip().replace(' ', '')
    found = None
    for step in range(now_step - WINDOW, now_step + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, step).encode(), code.encode()) and found is None:
            found = step
    return found


def otpauth_uri(secret, account):
    label = quote(f'{ISSUER}:{account}')
    query = urlencode({'secret': base64.b32encode(secret).decode().rstrip('='), 'issuer': ISSUER, 'algorithm': 'SHA1',
                       'digits': DIGITS, 'period': STEP_SECONDS})
    return f'otpauth://totp/{label}?{query}'


def new_recovery_code():
    raw = ''.join(secrets.choice(ALPHABET) for _ in range(10))
    return f'{raw[:5]}-{raw[5:]}'


def recovery_hash(key, user_id, code):
    normal = (code or '').strip().lower().replace('-', '').replace(' ', '')
    return hmac.new(key.encode(), b'recovery\x00' + str(user_id).encode() + b'\x00' + normal.encode(),
                    hashlib.sha256).hexdigest()
