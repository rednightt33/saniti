"""EDGE multi-user Phase 1 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 0 and 2): the principal of a request.

The owner of every request comes from here and only from here: no route, store call, worker call or Orc call reads
settings.owner (tests/test_principal.py greps app/ for it; the allowed uses are the seed in accounts.py and the
switch-off mapping below).

- **Switch off** (EDGE_MULTIUSER false, the default): the session is read exactly as before Phase 1 (store.session,
  the configured owner only). The principal is user #1: owner_key = EDGE_OWNER, every capability ("*"), version "env".
  EDGE_ADMIN_OWNERS stays the switch-off source of the admin rights (CONTRACT.md section 2): an owner it does not list
  gets no capability, which is what rights.py and the manual routes gave before (they were the only admin checks).
- **Switch on:** the session must join an active account (accounts.py resolve, one statement), within the absolute
  lifetime and the idle timeout EDGE_SESSION_IDLE_SECONDS (default 8 h). Phase 2 (CONTRACT.md 8a): the same statement
  resolves the plan catalog: the active, unexpired subscription's plan, else the default plan; its plan_capabilities;
  the account's unexpired overrides replacing the plan's value of their key. No plan or role grants anything in code:
  the role only names the account's kind, the catalog decides what it may do (a catalog change applies on the next
  request, no restart).

What a principal holds (`grants`, key -> value, each checked against its capability kind on read):
- `capabilities`: the flag keys whose value is true ('*' = every capability, every item at any release stage);
- `limits`: the limits (non-negative integers) and lists (arrays of strings), read with `p.limit(key)`;
- item families (`items` values {ids, stages, all}): `p.can('<family>:<id>')` holds the item when its id is listed,
  its release stage (releases.py stage_of) is listed, or all is true. Unknown keys are not held.

Dependencies (`Auth`, handed to every router as `routes(app, auth)`):
- `auth.principal`: the Principal (401 UNAUTHENTICATED otherwise); sets request.state.owner and request.state.principal;
- `auth.writer`: the principal plus the CSRF check (403 CSRF_INVALID);
- `auth.need(capability, write=False)`: 403 CAPABILITY_REQUIRED without the capability, or 403 PLAN_EXPIRED when only
  the account's ended plan held it (access.expired_plan names that plan; the fix is to renew it);
- `auth.admin(write=False, capability='admin.access')`: need(capability) plus mfa_ok, else 403 MFA_REQUIRED.
"""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Depends, Request

from .accounts import OWNER_KEY, AccountStore
from .errors import Refusal, capability_required, plan_expired
from .releases import KIND_OF_FAMILY, stage_of
from .security import csrf_token, same_ascii, token_hash

logger = logging.getLogger('edge_bff.principal')

EVERYTHING = '*'
ADMIN_ACCESS = 'admin.access'
SWITCH_OFF_VERSION = 'env'
TOKEN = re.compile(r'[0-9a-f]{64}')
# the routes a session that has not passed MFA may use (CONTRACT.md section 4 "Admin MFA")
MFA_OPEN = frozenset({'/api/v1/auth/session', '/api/v1/auth/sign-out', '/api/v1/auth/mfa/enroll',
                      '/api/v1/auth/mfa/verify'})
ITEM_KEYS = frozenset({'ids', 'stages', 'all'})


def valid_value(kind, value):
    """A catalog value of the shape of its kind (CONTRACT.md 8a "Value shapes")."""
    if kind == 'flag':
        return value is True
    if kind == 'limit':
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if kind == 'list':
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if kind == 'items':
        return isinstance(value, dict) and set(value) <= ITEM_KEYS \
            and all(isinstance(value.get(k, []), list) and all(isinstance(x, str) for x in value.get(k, []))
                    for k in ('ids', 'stages')) and isinstance(value.get('all', False), bool)
    return False


def read_grants(rows, user_id=None):
    """{key: value} of the rows {key: {kind, value}} the statement resolved, each of the shape of its kind; a value of
    the wrong shape is not granted and is logged (by its key only)."""
    grants, kinds = {}, {}
    for key, row in sorted((rows or {}).items()):
        kind, value = (row or {}).get('kind'), (row or {}).get('value')
        if valid_value(kind, value):
            grants[key], kinds[key] = value, kind
        else:
            logger.warning(json.dumps({'event': 'capability_value_invalid', 'capability': key, 'user_id': user_id}))
    return grants, kinds


def holds(grants, kinds, key):
    """Whether resolved grants hold a key (Principal.can; also the ended plan's grants for PLAN_EXPIRED)."""
    if grants.get(EVERYTHING) is True:
        return True
    if kinds.get(key) == 'flag':
        return grants[key] is True
    family, sep, item = key.partition(':')
    if not sep or not item or kinds.get(family) != 'items':
        return False
    value = grants[family]
    if value.get('all') is True or item in value.get('ids', ()):
        return True
    kind = KIND_OF_FAMILY.get(family)
    return kind is not None and stage_of(kind, item) in value.get('stages', ())


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
    # user #1, the account EDGE had before accounts (owner key EDGE_OWNER; the seed row, the one key not of the 'u_'
    # form, users_one_seed): browser state left before the last-login mark existed can only be its (C3 Phase 1 B1)
    seed: bool = False
    # Phase 2 (CONTRACT.md 8a): every resolved grant (key -> value) and its capability kind; the plan that ended
    # (access.expired_plan, None when none) with its own grants, which decide PLAN_EXPIRED
    grants: dict = field(default_factory=dict, hash=False, compare=False)
    kinds: dict = field(default_factory=dict, hash=False, compare=False, repr=False)
    expired_plan: str | None = None
    expired_grants: dict = field(default_factory=dict, hash=False, compare=False, repr=False)
    expired_kinds: dict = field(default_factory=dict, hash=False, compare=False, repr=False)

    def can(self, capability):
        """'*' holds everything; a flag key is held when granted; '<family>:<id>' by the family's items value (its ids,
        its release stages, or all). Anything else is not held."""
        return EVERYTHING in self.capabilities or holds(self.grants, self.kinds, capability)

    def limit(self, capability, default=None):
        """A limit (non-negative integer) or list (strings) the plan sets; default when it sets none (no limit)."""
        return self.limits.get(capability, default)

    def refusal(self, capability):
        """The refusal for a capability this principal does not hold: PLAN_EXPIRED when only its ended plan held it
        (renewing that plan is the fix), else CAPABILITY_REQUIRED (upgrading is)."""
        if self.expired_plan and holds(self.expired_grants, self.expired_kinds, capability):
            return plan_expired(capability, self.expired_plan)
        return capability_required(capability)

    def access(self, nxt=None):
        """The session answer's `access` object (CONTRACT.md section 4, GET /api/v1/auth/session)."""
        return {'plan': self.plan_key, 'role': self.role, 'status': self.status,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None, 'mfa_ok': self.mfa_ok,
                'capabilities': sorted(self.capabilities), 'limits': dict(self.limits), 'version': self.version,
                'owner_key': self.owner_key, 'mfa_enrolled': self.mfa_enrolled, 'seed': self.seed,
                'expired_plan': self.expired_plan,
                'next': nxt if nxt is not None else (None if self.mfa_ok else 'mfa')}


def version_of(plan_key, status, grants, versions, expired_plan=None):
    """A short fingerprint of what the principal may do (CONTRACT.md 8a): the plan key, the account status, the
    resolved grants (overrides included), the plan_capabilities versions and the ended plan. It changes when access
    changes, and is sent as X-Edge-Entitlements on every authenticated answer."""
    raw = json.dumps([plan_key, status, grants, versions, expired_plan], sort_keys=True, separators=(',', ':'),
                     default=str).encode()
    return 'db-' + hashlib.sha256(raw).hexdigest()[:12]


def switch_off_principal(settings, owner, token='', seed=None):
    """The switch-off mapping: the configured owner is user #1 (role admin, every capability) while EDGE_ADMIN_OWNERS
    lists it (its default); any other owner (a queued job's owner read at dispatch) has the admin rights only when
    EDGE_ADMIN_OWNERS lists it, as rights.py decided before Phase 1."""
    admin = owner in settings.admin_owners
    first = owner == settings.owner
    seed = seed or {}
    # the environment's mapping, not a plan: EDGE_ADMIN_OWNERS lists the owners that hold everything
    return Principal(user_id=seed.get('user_id') if first else None, owner_key=owner,
                     username=seed.get('username') if first else None, role='admin' if admin else 'user', plan_key=None,
                     status='active', expires_at=None, mfa_ok=True,
                     capabilities=frozenset({EVERYTHING}) if admin else frozenset(), limits={},
                     version=SWITCH_OFF_VERSION, token=token, seed=first)


def role_needs_mfa(capabilities):
    """Switch on: an account whose resolved capabilities hold everything or the admin access passes the second factor
    before any other route (CONTRACT.md 8a: derived from the catalog, no longer from the role)."""
    return EVERYTHING in capabilities or ADMIN_ACCESS in capabilities


def account_principal(row, token=''):
    """A switch-on principal from an account row with its resolved grants (accounts.py resolve or owner)."""
    grants, kinds = read_grants(row.get('grants'), row['user_id'])
    capabilities = frozenset(k for k, kind in kinds.items() if kind == 'flag')
    limits = {k: grants[k] for k, kind in kinds.items() if kind in ('limit', 'list')}
    expired_plan = row.get('expired_plan')
    expired_grants, expired_kinds = read_grants(row.get('expired_grants'), row['user_id']) if expired_plan else ({}, {})
    needs_mfa = role_needs_mfa(capabilities)
    return Principal(user_id=row['user_id'], owner_key=row['owner_key'], username=row['username'], role=row['role'],
                     plan_key=row.get('plan_key'), status=row['status'], expires_at=row.get('plan_expires_at'),
                     mfa_ok=not needs_mfa or row.get('mfa_passed_at') is not None, capabilities=capabilities,
                     limits=limits,
                     version=version_of(row.get('plan_key'), row['status'], grants, row.get('versions') or {},
                                        expired_plan),
                     token=token, mfa_enrolled=bool(row.get('mfa_enrolled')),
                     seed=not OWNER_KEY.fullmatch(row['owner_key']), grants=grants, kinds=kinds,
                     expired_plan=expired_plan, expired_grants=expired_grants, expired_kinds=expired_kinds)


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

    def seed_plan(self):
        """Phase 2 (CONTRACT.md 8a "User #1"): the seed user's subscription to the plan that holds every capability
        (accounts.py seed_subscription; blocking, a thread, after seed_user). None without a seed or a single such
        plan."""
        if not self.seed:
            return None
        return self.accounts.seed_subscription(self.seed['user_id'])

    def needs_mfa(self, owner_key):
        """Switch on: whether the account's resolved capabilities require the second factor (the sign-in makes a
        pending session for it). Blocking (a thread)."""
        return role_needs_mfa(self.owner_principal(owner_key).capabilities)

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
        """A dependency: the principal (with CSRF when write) holding the capability, else 403 CAPABILITY_REQUIRED (or
        PLAN_EXPIRED when only the account's ended plan held it)."""
        key = ('need', capability, write)
        if key not in self._needs:
            base = self.writer if write else self.principal

            async def check(p: Principal = Depends(base)):
                if not p.can(capability):
                    raise p.refusal(capability)
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
