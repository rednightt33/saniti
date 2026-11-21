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

The two websites (EXEC-MU-ACCOUNTS "Production environment", user decisions 2026-11-19; config.py EDGE_SITE):
- the switch-off resolution accepts only a switch-off session (user_id NULL, store.session; ERRORS R2-1), so a session
  of an account (made by the live site, with the switch on) never opens the beta, and a beta session (no account) never
  resolves on the live site (accounts.resolve joins the account);
- on the live site (EDGE_SITE=live) every principal is `live_view`: it never holds a beta-only capability (`beta_only`:
  the Monitor (AI, decision D1) and admin tabs, the admin rights of rights.py, every item at the lab stage), whatever its
  plan grants, '*' included; `auth.need` of a beta-only capability answers 404 NOT_FOUND there, as for a route the site
  does not have. The second factor is decided by the account's own grants, so user #1 still needs it on the live site.

Guests (track guest, decision 1 of 2026-11-19, the user: "1a - bukan hanya chart, nanti ada indikator dll yg juga
mungkin di show ke user. jadi design harus plug and play dan fluid"; verification/edge_multiuser/fix_round/guest.md):
- a visitor without a session (no cookie, or one that resolves to no session) on a site with guests on
  (Settings.guests: the live site unless EDGE_GUESTS=false; never with EDGE_MULTIUSER off) is the guest principal: the
  grants of the one plan marked for_guests (edge_bff.plans, migration 20261119_070), read on every request through
  read_grants as every plan's are (guest_principal), so a change of its rows changes what visitors see without code;
- it exists only for the routes that ask for it (`auth.need(capability, guests=True)`, `auth.visitor`): the Terminal's
  data relay and the catalogs the Terminal reads. Every other route keeps answering 401 UNAUTHENTICATED, so the page
  goes to sign-in;
- it never holds everything, the admin access, an admin right or a beta-only capability, whatever the plan's rows say
  (fail closed, logged guest_capability_dropped); its owner key is GUEST_OWNER for every visitor (terminal-api's one
  guest owner row), and `client` names the visitor: an HMAC of its client address (guest_client), which terminal-api
  counts its quotas by (x-terminal-client). The address is the client's X-Forwarded-For entry, the hop Railway's
  edge adds to every request it forwards (client_of); without a readable address (no header or not an IP address; the
  socket peer only on a developer machine, EDGE_ENVIRONMENT=local) there is no guest principal: 401 (fail closed);
- a guest writes without CSRF: it has no session a cross-site page could ride, and the Origin check of every write
  (main.py protections) still holds.
"""
import asyncio
import dataclasses
import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Depends, Request

from .accounts import GUEST_OWNER, OWNER_KEY, AccountStore
from .config import LIVE
from .throttle import address_key, forwarded_hop
from .errors import Refusal, capability_required, plan_expired, set_display_names
from . import releases
from .releases import KIND_OF_FAMILY, LAB, stage_of
from .rights import CAPABILITY_OF as RIGHT_CAPABILITIES
from .security import SESSION_COOKIE, cookie_name, csrf_token, same_ascii, token_hash

logger = logging.getLogger('edge_bff.principal')

EVERYTHING = '*'
ADMIN_ACCESS = 'admin.access'
SWITCH_OFF_VERSION = 'env'
TOKEN = re.compile(r'[0-9a-f]{64}')
# the routes a session that has not passed MFA may use (CONTRACT.md section 4 "Admin MFA")
MFA_OPEN = frozenset({'/api/v1/auth/session', '/api/v1/auth/sign-out', '/api/v1/auth/mfa/enroll',
                      '/api/v1/auth/mfa/verify'})
ITEM_KEYS = frozenset({'ids', 'stages', 'all'})
# EXEC-MU-ACCOUNTS "Production environment" (user 2026-11-19): the AI Monitor, the admin pages and every lab item live on
# the beta site only. A capability key is '<tab>.<name>' (the catalog's rule; an item key '<tab>.<kind>:<id>'), so the
# beta-only keys are those of these tabs, the admin rights rights.py grants (ADMIN_RIGHTS) and the lab-stage items.
BETA_ONLY_TABS = frozenset({'monitor', 'admin'})
ADMIN_RIGHT_CAPABILITIES = frozenset(RIGHT_CAPABILITIES.values())
# Track guest (module docstring): the one owner key of every visitor (never an account's, which are u_<hex>; config.py
# refuses it for EDGE_OWNER and EDGE_ADMIN_OWNERS), and the role and status a guest principal names (it has no account)
VISITOR = 'visitor'
GUEST_CLIENT_LABEL = b'edge_bff.guest_client\x00'


def beta_only(key):
    """Whether the live site never holds this capability key (module docstring): a key of a BETA_ONLY_TABS tab, an admin
    right, a key of a tab at the lab stage (releases.tab_stage; a tab the release file does not list is lab: the user,
    2026-11-20, development reaches the live site only on request, LIVE_PROMOTION.md), or an item '<family>:<id>' of a
    family with release stages (releases.KIND_OF_FAMILY) whose id is at the lab stage (an id the release file does not
    list is lab)."""
    family, sep, item = (key or '').partition(':')
    tab = family.split('.', 1)[0]
    if tab in BETA_ONLY_TABS or family in ADMIN_RIGHT_CAPABILITIES:
        return True
    if releases.TAB.fullmatch(tab) and releases.tab_stage(tab) == LAB:
        return True
    kind = KIND_OF_FAMILY.get(family) if sep else None
    return kind is not None and stage_of(kind, item) == LAB


def valid_value(kind, value):
    """A catalog value of the shape of its kind (CONTRACT.md 8a "Value shapes"; a flag may be false: an override that
    takes the plan's flag away). The database refuses any other shape at write time (capability_value_check)."""
    if kind == 'flag':
        return value is True or value is False
    if kind == 'limit':
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if kind == 'list':
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if kind == 'items':
        return isinstance(value, dict) and set(value) <= ITEM_KEYS \
            and all(isinstance(value.get(k, []), list) and all(isinstance(x, str) for x in value.get(k, []))
                    for k in ('ids', 'stages')) and set(value.get('stages', ())) <= set(releases.STAGES) \
            and isinstance(value.get('all', False), bool)
    return False


# C1 Phase 2 F1: a value that cannot be read never widens access. A flag or an item family of the wrong shape is not
# held; a limit or a list of the wrong shape is the most restrictive value (0, no entries), never "no limit". Immutable
# here and copied per read (re-check R1-24): a consumer that adds to the list it was given changes its own copy only,
# never the value of the next principal whose list cannot be read
RESTRICTIVE = {'limit': 0, 'list': ()}


def restrictive(kind):
    """A new most restrictive value of a limit or list kind (never a shared object)."""
    value = RESTRICTIVE[kind]
    return list(value) if kind == 'list' else value


def read_grants(rows, user_id=None):
    """{key: value} of the rows {key: {kind, value}} the statement resolved, each of the shape of its kind. A value of
    the wrong shape is logged (by its key only) and fails closed: a limit reads 0 and a list reads [] (RESTRICTIVE),
    anything else is not granted."""
    grants, kinds = {}, {}
    for key, row in sorted((rows or {}).items()):
        kind, value = (row or {}).get('kind'), (row or {}).get('value')
        if valid_value(kind, value):
            grants[key], kinds[key] = value, kind
            continue
        logger.warning(json.dumps({'event': 'capability_value_invalid', 'capability': key, 'user_id': user_id}))
        if kind in RESTRICTIVE:
            grants[key], kinds[key] = restrictive(kind), kind
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
    # the live site's view (live_view): no beta-only capability is held, whatever the grants say
    live: bool = False
    # track guest: a visitor without an account (guest_principal) and its visitor key, an HMAC of its client address
    guest: bool = False
    client: str = field(default='', repr=False)

    def can(self, capability):
        """'*' holds everything; a flag key is held when granted; '<family>:<id>' by the family's items value (its ids,
        its release stages, or all). Anything else is not held. On the live site a beta-only key never is."""
        if self.live and beta_only(capability):
            return False
        return EVERYTHING in self.capabilities or holds(self.grants, self.kinds, capability)

    def limit(self, capability, default=None):
        """A limit (non-negative integer) or list (strings) the plan sets; default when it sets none (no limit)."""
        return self.limits.get(capability, default)

    def capped(self, capability, hard):
        """Phase 3a (CONTRACT.md 8b "Saved-item caps"): min(the plan's limit, hard). hard is the module's constant, the
        storage guarantee no plan or override can raise; no row (the switch-off principal '*', a plan without the
        limit) gives hard. Call it after the capability check of the route: a plan without the capability has no row."""
        value = self.limit(capability, hard)
        return min(value, hard) if isinstance(value, int) and not isinstance(value, bool) else hard

    def refusal(self, capability, item=None, amount=None):
        """The refusal for a request this principal may not make: PLAN_EXPIRED when the account's ended plan would have
        allowed it (renewing that plan is the fix; ended_allows), else CAPABILITY_REQUIRED (upgrading is). `item` (a
        list member asked, e.g. a ticker) and `amount` (a number asked, e.g. a window in days) let a list or a limit be
        judged against the ended plan's own value (CONTRACT.md 8a; re-check R1-23)."""
        if self.ended_allows(capability, item, amount):
            return plan_expired(capability, self.expired_plan)
        refused = capability_required(capability)
        if self.guest:
            refused.details['visitor'] = True                    # errors.words: a visitor's sentence (C3-9)
        return refused

    def ended_allows(self, capability, item=None, amount=None):
        """Whether the account's ended plan would have allowed this request. A flag or an item family: held as can()
        holds it. A list or a limit (its kind read from the ended plan's row, else the current plan's): allowed when the
        ended plan set no such restriction (no row: every member, no limit), its list holds `item`, or `amount` is
        within its limit; without `item` or `amount` only the first case is known."""
        if not self.expired_plan:
            return False
        grants, kinds = self.expired_grants, self.expired_kinds
        kind = kinds.get(capability) or self.kinds.get(capability)
        if kind not in ('list', 'limit'):
            return holds(grants, kinds, capability)
        if grants.get(EVERYTHING) is True or capability not in kinds:
            return True
        value = grants[capability]
        if kind == 'list':
            return item is not None and item in value
        return isinstance(amount, int) and not isinstance(amount, bool) and amount <= value

    def access(self, nxt=None, ceilings=None):
        """The session answer's `access` object (CONTRACT.md section 4, GET /api/v1/auth/session). `ceilings`
        (Auth.ceilings: a limit key -> its module's HARD): a limit is reported as the routes apply it, min(plan, HARD)
        (Principal.capped; re-check R1-29), so the page's limit(key) is the number the server enforces."""
        ceilings = ceilings or {}
        limits = {k: self.capped(k, ceilings[k]) if k in ceilings and self.kinds.get(k, 'limit') == 'limit' else v
                  for k, v in self.limits.items()}
        return {'plan': self.plan_key, 'role': self.role, 'status': self.status,
                'expires_at': self.expires_at.isoformat() if self.expires_at else None, 'mfa_ok': self.mfa_ok,
                'capabilities': sorted(self.capabilities), 'limits': limits, 'version': self.version,
                'owner_key': self.owner_key, 'mfa_enrolled': self.mfa_enrolled, 'seed': self.seed,
                'expired_plan': self.expired_plan,
                'next': nxt if nxt is not None else (None if self.mfa_ok else 'mfa')}


def version_of(plan_key, status, grants, versions, expired_plan=None, expires_at=None):
    """A short fingerprint of what the principal may do (CONTRACT.md 8a): the plan key, the account status, the
    resolved grants (overrides included), the plan_capabilities versions, the ended plan, the plan's end and the
    release stages (C1/C2 Phase 2: an extension or a stage change reaches open pages). It changes when access changes,
    and is sent as X-Edge-Entitlements on every authenticated answer."""
    raw = json.dumps([plan_key, status, grants, versions, expired_plan, expires_at, releases.CURRENT.digest],
                     sort_keys=True, separators=(',', ':'), default=str).encode()
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


def live_view(p, flags=()):
    """The principal as the live site serves it (EDGE_SITE=live; module docstring): `live` set, so `can` refuses every
    beta-only key; its capabilities without them, where '*' reads as every flag capability of the catalog (`flags`,
    edge_bff.capabilities of kind flag) that is not beta-only (so the page shows the tabs the site has, never the
    Monitor); its limits without them; mfa_ok and the grants as they are (the second factor is the account's own); a
    version of its own, so an open page reads the session again when the view changes."""
    held = flags if EVERYTHING in p.capabilities else p.capabilities
    capabilities = frozenset(k for k in held if k != EVERYTHING and not beta_only(k))
    raw = json.dumps([p.version, sorted(capabilities), LIVE], separators=(',', ':')).encode()
    return dataclasses.replace(p, capabilities=capabilities, live=True,
                               limits={k: v for k, v in p.limits.items() if not beta_only(k)},
                               version='db-' + hashlib.sha256(raw).hexdigest()[:12])


def client_of(request, local=False):
    """The visitor's client key: the client's X-Forwarded-For entry over every line of the header, the one Railway's
    edge writes for the client before its own node's (throttle.forwarded_hop: measured by the probe of CONTRACT.md
    section 4, ERRORS M512; a line a client wrote never decides, 3c check C3-5), as an address key (IPv6 by its /64,
    throttle.address_key); on a
    developer machine (`local`, EDGE_ENVIRONMENT=local), with no such header, the socket peer. None otherwise: a request
    that did not pass the edge, or a header that is not an address, gets no guest principal (fail closed)."""
    hop = forwarded_hop(request)
    if hop is not None:
        return address_key(hop)
    if local and request.client:
        return address_key(request.client.host)
    return None


def guest_client(secret, address):
    """The visitor key of a client address: 32 hex of an HMAC with EDGE_SESSION_SECRET under its own label (never the
    address itself, and no other HMAC of the same secret, such as the throttle's or CSRF's, can equal it)."""
    return hmac.new(secret.encode(), GUEST_CLIENT_LABEL + address.encode(), hashlib.sha256).hexdigest()[:32]


# what a visitor never holds, whatever the guest plan's rows say (module docstring)
GUEST_NEVER = frozenset({EVERYTHING, ADMIN_ACCESS}) | ADMIN_RIGHT_CAPABILITIES


def guest_principal(row, client):
    """The guest principal from the guest plan's row ({plan_key, grants {key: {kind, value}}, versions}; accounts.py
    guest_plan) and the visitor key: the plan's grants read as every plan's are (read_grants), without GUEST_NEVER and
    the beta-only keys (dropped and logged), and `live` set so no beta-only item is held either."""
    grants, kinds = read_grants(row.get('grants'))
    for key in sorted(k for k in grants if k in GUEST_NEVER or beta_only(k)):
        logger.warning(json.dumps({'event': 'guest_capability_dropped', 'capability': key}))
        grants.pop(key)
        kinds.pop(key)
    capabilities = frozenset(k for k, kind in kinds.items() if kind == 'flag' and grants[k] is True)
    limits = {k: grants[k] for k, kind in kinds.items() if kind in ('limit', 'list')}
    return Principal(user_id=None, owner_key=GUEST_OWNER, username=None, role=VISITOR, plan_key=row.get('plan_key'),
                     status=VISITOR, expires_at=None, mfa_ok=True, capabilities=capabilities, limits=limits,
                     version=version_of(row.get('plan_key'), VISITOR, grants, row.get('versions') or {}),
                     grants=grants, kinds=kinds, live=True, guest=True, client=client)


def role_needs_mfa(capabilities):
    """Switch on: an account whose resolved capabilities hold everything or the admin access passes the second factor
    before any other route (CONTRACT.md 8a: derived from the catalog, no longer from the role)."""
    return EVERYTHING in capabilities or ADMIN_ACCESS in capabilities


def account_principal(row, token=''):
    """A switch-on principal from an account row with its resolved grants (accounts.py resolve or owner)."""
    grants, kinds = read_grants(row.get('grants'), row['user_id'])
    capabilities = frozenset(k for k, kind in kinds.items() if kind == 'flag' and grants[k] is True)
    limits = {k: grants[k] for k, kind in kinds.items() if kind in ('limit', 'list')}
    expired_plan = row.get('expired_plan')
    expired_grants, expired_kinds = read_grants(row.get('expired_grants'), row['user_id']) if expired_plan else ({}, {})
    needs_mfa = role_needs_mfa(capabilities)
    return Principal(user_id=row['user_id'], owner_key=row['owner_key'], username=row['username'], role=row['role'],
                     plan_key=row.get('plan_key'), status=row['status'], expires_at=row.get('plan_expires_at'),
                     mfa_ok=not needs_mfa or row.get('mfa_passed_at') is not None, capabilities=capabilities,
                     limits=limits,
                     version=version_of(row.get('plan_key'), row['status'], grants, row.get('versions') or {},
                                        expired_plan, row.get('plan_expires_at')),
                     token=token, mfa_enrolled=bool(row.get('mfa_enrolled')),
                     seed=not OWNER_KEY.fullmatch(row['owner_key']), grants=grants, kinds=kinds,
                     expired_plan=expired_plan, expired_grants=expired_grants, expired_kinds=expired_kinds)


class Auth:
    """The principal dependencies of one app (CONTRACT.md section 2)."""

    NAMES_SECONDS = 300           # the catalog's display names are read again at most this often (C1 Phase 3a F3)

    def __init__(self, settings, store, accounts=None):
        self.settings, self.store = settings, store
        self.accounts = accounts or AccountStore(store)
        self._names_at = None
        self.flags = frozenset()                         # the catalog's flag capabilities (refresh_names; live_view)
        self.seed = None                                 # {user_id, username} of user #1 once seeded (main.py lifespan)
        self._needs = {}
        # re-check R1-29: each module's HARD of a plan limit (ceiling), so the session answer reports what is applied
        self.ceilings = {}

        # named session and write as before Phase 1 (tests read the dependency names)
        cookie = cookie_name(SESSION_COOKIE, settings.secure_cookie)
        self.session_cookie = cookie                     # 3f: lab_admin reads the same cookie

        async def signed_in(request: Request):
            """The principal of the request's session, or None when it has none (the caller answers 401, or the
            guest routes make a guest principal); a session that still waits for the second factor is refused here."""
            token = request.cookies.get(cookie, '')
            if not token and cookie != SESSION_COOKIE and not settings.multiuser:
                # re-check R2-22: the configured owner's session from before the __Host- name, read once under the old
                # name (main.py protections sets it again under the new one); with the switch on only the new name is
                # read, so a cookie another host set under the old name is never a session
                token = request.cookies.get(SESSION_COOKIE, '')
            found = await self.resolve(token)
            if found is None:
                return None
            # the refusals below carry the principal's X-Edge-Entitlements too (main.py protections), so a page whose
            # account now needs the second factor reads its session again (re-check R2-31)
            request.state.principal = found
            # a pending admin session (the password was right, the second factor not yet): only the MFA steps, the
            # session read and sign-out; every other route answers 403 MFA_REQUIRED
            if not found.mfa_ok and request.url.path not in MFA_OPEN:
                # re-check R2-31: whether an authenticator is set up, as the sign-in answer says, so the words and the
                # shell can offer the set-up to an account raised to a plan that needs the second factor
                raise Refusal(403, 'MFA_REQUIRED', {'mfa_enrolled': found.mfa_enrolled})
            # EXEC-BACKTEST-REVAMP P5: request.state.owner stays, set from the principal (never a body's)
            request.state.owner, request.state.principal = found.owner_key, found
            return found

        async def session(request: Request):
            found = await signed_in(request)
            if found is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            return found

        def check_csrf(request, p):
            if not same_ascii(request.headers.get('x-csrf-token', ''), csrf_token(p.token, settings.session_secret)):
                # the only place that answers CSRF_INVALID (the clients re-read the session and retry once on it)
                raise Refusal(403, 'CSRF_INVALID')

        async def write(request: Request, p: Principal = Depends(session)):
            check_csrf(request, p)
            return p

        # track guest (module docstring): the session's principal, else the guest principal, else 401; a guest writes
        # without CSRF (no session to ride; the Origin check of every write holds)
        async def visitor(request: Request):
            found = await signed_in(request)
            if found is not None:
                return found
            guest = await self.guest(request)
            if guest is None:
                raise Refusal(401, 'UNAUTHENTICATED')
            request.state.owner, request.state.principal = guest.owner_key, guest
            return guest

        async def visitor_write(request: Request, p: Principal = Depends(visitor)):
            if not p.guest:
                check_csrf(request, p)
            return p

        self.principal, self.writer = session, write
        self.visitor, self.visitor_writer = visitor, visitor_write

    def seed_user(self):
        """User #1 from the configuration (accounts.py seed; blocking, a thread): owner_key EDGE_OWNER, the username
        from EDGE_LOGIN, the password identity from EDGE_PASSWORD_VERIFIER. Kept as self.seed for the switch-off
        principal's user_id and username."""
        s = self.settings
        self.seed = self.accounts.seed(s.owner, s.login, s.password_verifier, s.multiuser)
        return self.seed

    def refresh_names(self, force=True):
        """The catalog's display names into the refusals (errors.display_name); blocking, a thread. Without the catalog
        (before its migration) the refusals keep the plain phrase."""
        if not force and not self.names_due():
            return
        with self.store.connect() as c:
            rows = c.execute('SELECT capability_key, display_name, kind FROM edge_bff.capabilities').fetchall()
            plans = c.execute('SELECT plan_key, display_name FROM edge_bff.plans').fetchall()
        set_display_names({r['capability_key']: r['display_name'] for r in rows},
                          {r['plan_key']: r['display_name'] for r in plans})
        self.flags = frozenset(r['capability_key'] for r in rows if r['kind'] == 'flag')
        # marked read only after a read that worked: a failed read at the start (or later) is tried again at the next
        # request, not NAMES_SECONDS later with no flags meanwhile (3c check C3-14)
        self._names_at = time.monotonic()

    def names_due(self):
        """Whether the catalog's names and flags are to be read again: never read, or read NAMES_SECONDS ago."""
        return self._names_at is None or time.monotonic() - self._names_at >= self.NAMES_SECONDS

    async def fresh_names(self):
        """Reads the catalog's names and flags again when they are due (names_due), so a flag the catalog adds reaches
        the live site's '*' holders within NAMES_SECONDS, and a start whose read failed recovers at the next request
        (3c check C3-14). A failed read is logged and the last names stay."""
        if not self.names_due():
            return
        try:
            await asyncio.to_thread(self.refresh_names, False)
        except Exception as e:                                  # noqa: BLE001 - logged by its class only
            logger.warning(json.dumps({'event': 'capability_names_failed', 'error': type(e).__name__}))

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
        return role_needs_mfa(owner_principal(self.settings, self.accounts, owner_key).capabilities)  # the account's own

    def configured_owner(self):
        """The switch-off owner a new session is made for (main.py sign-in with EDGE_MULTIUSER off): EDGE_OWNER."""
        return self.settings.owner

    async def lab_admin(self, request):
        """3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): the principal of the admin's request, the only one lab
        code may reach, or None: a session of a principal holding admin.access that has passed the second factor (switch
        on), on the beta only. What it is then served is decided by what it holds (main.py page_app: a lab build only
        with every item, catalog.holds_every_item; a lab tab only with the tab's own <tab>.view), so lab code never
        reaches a principal the catalogs would not list it to. The live site has no lab code (every lab item and tab is
        refused there, '*' included). Never raises: a visitor, a pending or an ended session gets None."""
        if self.settings.site == LIVE:
            return None
        token = request.cookies.get(self.session_cookie, '')
        if not token and self.session_cookie != SESSION_COOKIE and not self.settings.multiuser:
            token = request.cookies.get(SESSION_COOKIE, '')       # the old cookie name, as signed_in reads it (R2-22)
        try:
            p = await self.resolve(token)
        except Exception:                                         # noqa: BLE001 - fail closed: the public build
            return None
        return p if p is not None and p.mfa_ok and p.can(ADMIN_ACCESS) else None

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
        if not row:
            return None
        await self.fresh_names()
        p = account_principal(row, token)
        # the pre-launch mode's rule (main.py sign-in) holds for every request, not only at the sign-in: a session of an
        # account that is no longer the admin or a test account (its mark removed, its plan lowered) ends with it (3c
        # check C3-7)
        if self.settings.prelaunch and not (role_needs_mfa(p.capabilities) or row.get('test_account')):
            return None
        return self.site_view(p)

    async def guest(self, request):
        """The guest principal of a request without a session (module docstring), or None: guests are off on this site
        (Settings.guests), the client address cannot be read (client_of, fail closed), or no plan is marked for guests
        (logged guest_plan_missing; a value that cannot be read never widens access)."""
        if not self.settings.guests:
            return None
        address = client_of(request, self.settings.environment == 'local')
        if address is None:
            return None
        row = await asyncio.to_thread(self.accounts.guest_plan)
        if row is None:
            logger.warning(json.dumps({'event': 'guest_plan_missing'}))
            return None
        return self.site_view(guest_principal(row, guest_client(self.settings.session_secret, address)))

    def site_view(self, p):
        """The principal as this site serves it: live_view on the live site, else as it is."""
        return live_view(p, self.flags) if self.settings.site == LIVE else p

    def owner_principal(self, owner_key):
        """The principal of an owner without a session, as it is now (the backtest loop reads its rights when it
        dispatches a queued job). Switch on: an owner with no active account has no capability. Blocking (a thread)."""
        return self.site_view(owner_principal(self.settings, self.accounts, owner_key))

    def need(self, capability, write=False, guests=False):
        """A dependency: the principal (with CSRF when write) holding the capability, else 403 CAPABILITY_REQUIRED (or
        PLAN_EXPIRED when only the account's ended plan held it). On the live site a beta-only capability (the Monitor,
        the admin routes) answers 404 NOT_FOUND before the session is read: the route is not one the site has. Track
        guest: `guests` makes the route one a visitor reaches (auth.visitor: the guest principal without a session);
        only the Terminal's data relay asks for it (tests/test_route_table.py GUEST_OPEN)."""
        key = ('need', capability, write) + (('guests',) if guests else ())
        if guests:
            base = self.visitor_writer if write else self.visitor
        else:
            base = self.writer if write else self.principal
        if key not in self._needs and self.settings.site == LIVE and beta_only(capability):

            async def absent(_: None = Depends(not_on_this_site), p: Principal = Depends(base)):
                return p                                      # never reached: not_on_this_site refuses first
            self._needs[key] = absent
        if key not in self._needs:
            async def check(p: Principal = Depends(base)):
                if not p.can(capability):
                    try:
                        await asyncio.to_thread(self.refresh_names, False)
                    except Exception:                         # noqa: BLE001 - the plain phrase stays
                        pass
                    raise p.refusal(capability)
                return p
            self._needs[key] = check
        return self._needs[key]

    def second_factor_holder(self):
        """A dependency for the second factor's own set-up (POST /api/v1/auth/mfa/enroll): the session principal, with
        CSRF, of an account whose own grants require the second factor (role_needs_mfa of the account as it is, never
        the live site's view, which leaves the admin keys out: 3c check C3-16). The set-up is part of signing in, so it
        exists on every site an account signs in on; the admin routes it protects stay beta-only. Else 403
        CAPABILITY_REQUIRED admin.access, as before."""
        key = ('second_factor_holder',)
        if key not in self._needs:
            async def check(p: Principal = Depends(self.writer)):
                if p.user_id is None or not await asyncio.to_thread(self.needs_mfa, p.owner_key):
                    raise capability_required(ADMIN_ACCESS)
                return p
            self._needs[key] = check
        return self._needs[key]

    def admin(self, write=False, capability=ADMIN_ACCESS):
        """need(capability) and need(admin.access), plus a session that proved MFA (switch on), else 403 MFA_REQUIRED
        (CONTRACT.md section 2). admin.access is what requires the second factor, so an admin route can never be
        opened by a narrower capability without it (C1 Phase 2 N2)."""
        key = ('admin', capability, write)
        if key not in self._needs:
            base = self.need(capability, write)

            async def check(p: Principal = Depends(base)):
                if not p.can(ADMIN_ACCESS):
                    raise p.refusal(ADMIN_ACCESS)
                if not p.mfa_ok:
                    raise Refusal(403, 'MFA_REQUIRED', {'mfa_enrolled': p.mfa_enrolled})
                return p
            self._needs[key] = check
        return self._needs[key]

    def ceiling(self, capability, hard):
        """A module's HARD for the plan limit `capability` (the storage guarantee Principal.capped applies), declared
        where the module registers its routes; the session answer's access.limits reports min(plan, HARD) for it. The
        lowest wins when two modules apply the same key. Returns hard."""
        was = self.ceilings.get(capability)
        self.ceilings[capability] = hard if was is None else min(was, hard)
        return hard


async def not_on_this_site():
    """The first dependency of a beta-only route on the live site (Auth.need): 404 NOT_FOUND."""
    raise Refusal(404, 'NOT_FOUND')


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
