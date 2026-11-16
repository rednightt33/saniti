"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 0 and 2): the principal of a request.

The owner of every request comes from here and only from here: no route, store call, worker call or Orc call reads
settings.owner (tests/test_principal.py greps app/ for it; the allowed uses are the seed in accounts.py and the
switch-off mapping below).

- **Switch off** (EDGE_MULTIUSER false, the default): the session is read exactly as before Phase 1 (store.session,
  the configured owner only). The principal is user #1: owner_key = EDGE_OWNER, every capability ("*"), version "env".
  EDGE_ADMIN_OWNERS stays the switch-off source of the admin rights (CONTRACT.md section 2): an owner it does not list
  gets no capability, which is what rights.py and the manual routes gave before (they were the only admin checks).
- **Switch on:** the session must join an active account (accounts.py resolve, one statement), within the absolute
  lifetime and the idle timeout EDGE_SESSION_IDLE_SECONDS (default 8 h). Phase 1 grants by role: admin every capability,
  user none; the plan catalog (Phase 2) replaces ROLE_CAPABILITIES with plan_capabilities and overrides in the same
  statement.

Dependencies (`Auth`, handed to every router as `routes(app, auth)`):
- `auth.principal`: the Principal (401 UNAUTHENTICATED otherwise); sets request.state.owner and request.state.principal;
- `auth.writer`: the principal plus the CSRF check (403 CSRF_INVALID);
- `auth.need(capability, write=False)`: 403 CAPABILITY_REQUIRED without the capability;
- `auth.admin(write=False, capability='admin.access')`: need(capability) plus mfa_ok, else 403 MFA_REQUIRED.
"""
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Depends, Request

from .accounts import AccountStore
from .errors import Refusal, capability_required
from .security import csrf_token, same_ascii, token_hash

EVERYTHING = '*'
ADMIN_ACCESS = 'admin.access'
SWITCH_OFF_VERSION = 'env'
TOKEN = re.compile(r'[0-9a-f]{64}')
# Phase 1 only: the capabilities of a role while no plan catalog exists (Phase 2 reads them from the catalog)
# the routes a session that has not passed MFA may use (CONTRACT.md section 4 "Admin MFA")
MFA_OPEN = frozenset({'/api/v1/auth/session', '/api/v1/auth/sign-out', '/api/v1/auth/mfa/enroll',
                      '/api/v1/auth/mfa/verify'})
ROLE_CAPABILITIES = {'admin': frozenset({EVERYTHING}), 'user': frozenset()}


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    owner_key: str
    username: str | None
    role: str
    plan_key: str | None
    status: str
    expires_at: datetime | None
    mfa_ok: bool
    capabilities: frozenset
    limits: dict = field(default_factory=dict, hash=False, compare=False)
    version: str = SWITCH_OFF_VERSION
    token: str = field(default='', repr=False)
    # switch on: the account has a confirmed TOTP enrolment (the MFA page asks for a code, else it offers enrolment)
    mfa_enrolled: bool = False

    def can(self, capability):
        return EVERYTHING in self.capabilities or capability in self.capabilities

    def limit(self, capability, default=None):
        return self.limits.get(capability, default)

    def access(self, nxt=None):
        """The session answer's `access` object (CONTRACT.md section 4, GET /api/v1/auth/session)."""
        return {'plan': self.plan_key, 'role': self.role, 'status': self.status,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None, 'mfa_ok': self.mfa_ok,
                'capabilities': sorted(self.capabilities), 'limits': dict(self.limits), 'version': self.version,
                'owner_key': self.owner_key, 'mfa_enrolled': self.mfa_enrolled,
                'next': nxt if nxt is not None else (None if self.mfa_ok else 'mfa')}


def version_of(role, status, capabilities):
    """A short fingerprint of what the principal may do; it changes when its access changes."""
    raw = json.dumps([role, status, sorted(capabilities)], separators=(',', ':')).encode()
    return 'db-' + hashlib.sha256(raw).hexdigest()[:12]


def switch_off_principal(settings, owner, token='', seed=None):
    """The switch-off mapping: the configured owner is user #1 (role admin, every capability) while EDGE_ADMIN_OWNERS
    lists it (its default); any other owner (a queued job's owner read at dispatch) has the admin rights only when
    EDGE_ADMIN_OWNERS lists it, as rights.py decided before Phase 1."""
    admin = owner in settings.admin_owners
    first = owner == settings.owner
    seed = seed or {}
    return Principal(user_id=seed.get('user_id') if first else None, owner_key=owner,
                     username=seed.get('username') if first else None, role='admin' if admin else 'user', plan_key=None,
                     status='active', expires_at=None, mfa_ok=True,
                     capabilities=ROLE_CAPABILITIES['admin' if admin else 'user'], limits={},
                     version=SWITCH_OFF_VERSION, token=token)


def role_needs_mfa(role):
    """Switch on: an account whose role holds the admin capability passes the second factor before any other route."""
    capabilities = ROLE_CAPABILITIES.get(role, frozenset())
    return EVERYTHING in capabilities or ADMIN_ACCESS in capabilities


def account_principal(row, token=''):
    """A switch-on principal from an account row (accounts.py resolve or owner)."""
    capabilities = ROLE_CAPABILITIES.get(row['role'], frozenset())
    needs_mfa = role_needs_mfa(row['role'])
    return Principal(user_id=row['user_id'], owner_key=row['owner_key'], username=row['username'], role=row['role'],
                     plan_key=None, status=row['status'], expires_at=None,
                     mfa_ok=not needs_mfa or row.get('mfa_passed_at') is not None, capabilities=capabilities,
                     limits={}, version=version_of(row['role'], row['status'], capabilities), token=token,
                     mfa_enrolled=bool(row.get('mfa_enrolled')))


class Auth:
    """The principal dependencies of one app (CONTRACT.md section 2)."""

    def __init__(self, settings, store, accounts=None):
        self.settings, self.store = settings, store
        self.accounts = accounts or AccountStore(store)
        self.seed = None                                 # {user_id, username} of user #1 once seeded (main.py lifespan)
        self._needs = {}

        # named session and write as before Phase 1 (tests read the dependency names)
        async def session(request: Request):
            found = await self.resolve(request.cookies.get('edge_session', ''))
            if found is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            # a pending admin session (the password was right, the second factor not yet): only the MFA steps, the
            # session read and sign-out; every other route answers 403 MFA_REQUIRED
            if not found.mfa_ok and request.url.path not in MFA_OPEN:
                raise Refusal(403, 'MFA_REQUIRED')
            # EXEC-BACKTEST-REVAMP P5: request.state.owner stays, set from the principal (never a body's)
            request.state.owner, request.state.principal = found.owner_key, found
            return found

        async def write(request: Request, p: Principal = Depends(session)):
            if not same_ascii(request.headers.get('x-csrf-token', ''), csrf_token(p.token, settings.session_secret)):
                # the only place that answers CSRF_INVALID (the clients re-read the session and retry once on it)
                raise Refusal(403, 'CSRF_INVALID')
            return p

        self.principal, self.writer = session, write

    def seed_user(self):
        """User #1 from the configuration (accounts.py seed; blocking, a thread): owner_key EDGE_OWNER, the username
        from EDGE_LOGIN, the password identity from EDGE_PASSWORD_VERIFIER. Kept as self.seed for the switch-off
        principal's user_id and username."""
        s = self.settings
        self.seed = self.accounts.seed(s.owner, s.login, s.password_verifier, s.multiuser)
        return self.seed

    def configured_owner(self):
        """The switch-off owner a new session is made for (main.py sign-in with EDGE_MULTIUSER off): EDGE_OWNER."""
        return self.settings.owner

    async def resolve(self, token):
        """The Principal of a session token, or None (no, revoked, expired or idle session; a disabled account)."""
        if not TOKEN.fullmatch(token or ''):
            return None
        hashed = token_hash(token)
        if not self.settings.multiuser:
            found = await asyncio.to_thread(self.store.session, hashed)
            if not found or found['owner_key'] != self.settings.owner:
                return None
            return switch_off_principal(self.settings, self.settings.owner, token, self.seed)
        row = await asyncio.to_thread(self.accounts.resolve, hashed, self.settings.session_idle_seconds)
        return account_principal(row, token) if row else None

    def owner_principal(self, owner_key):
        """The principal of an owner without a session, as it is now (the backtest loop reads its rights when it
        dispatches a queued job). Switch on: an owner with no active account has no capability. Blocking (a thread)."""
        return owner_principal(self.settings, self.accounts, owner_key)

    def need(self, capability, write=False):
        """A dependency: the principal (with CSRF when write) holding the capability, else 403 CAPABILITY_REQUIRED."""
        key = ('need', capability, write)
        if key not in self._needs:
            base = self.writer if write else self.principal

            async def check(p: Principal = Depends(base)):
                if not p.can(capability):
                    raise capability_required(capability)
                return p
            self._needs[key] = check
        return self._needs[key]

    def admin(self, write=False, capability=ADMIN_ACCESS):
        """need(capability) plus a session that proved MFA (switch on, an admin), else 403 MFA_REQUIRED."""
        key = ('admin', capability, write)
        if key not in self._needs:
            base = self.need(capability, write)

            async def check(p: Principal = Depends(base)):
                if not p.mfa_ok:
                    raise Refusal(403, 'MFA_REQUIRED')
                return p
            self._needs[key] = check
        return self._needs[key]


def owner_principal(settings, accounts, owner_key):
    """The principal of an owner without a session (see Auth.owner_principal); accounts may be None with the switch
    off."""
    if not getattr(settings, 'multiuser', False):
        return switch_off_principal(settings, owner_key)
    row = accounts.owner(owner_key) if accounts is not None else None
    if row is None:
        return Principal(user_id=None, owner_key=owner_key, username=None, role='user', plan_key=None, status='unknown',
                         expires_at=None, mfa_ok=False, capabilities=frozenset(), version='none')
    return account_principal(row)
