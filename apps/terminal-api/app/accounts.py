"""Who is calling, and the in-process account cache of the read-only routes (EXEC-MU-RUNTIME T1, T3; user 2026-10-28,
option A).

A caller is identified from its request without the database: the EDGE gateway key, a service key (one per service
account, config.py TERMINAL_SERVICE_KEY_<NAME>) or a subscriber's session cookie. Its account row is then read:

- by a grant (/bundle, /files, /xsection, /reference, /history) inside the grant's own transaction, after the
  account's advisory lock (main.py admit), so a grant always sees the account as it is after any wait for the lock;
- by /manifest, /state and /logo, which grant nothing, from this cache: the row of the last check of this process, at
  most TTL_SECONDS old. A deactivated account can read manifests, the publication state and logos for up to that long;
  it can never be granted a file (spec: verification/edge_multiuser/runtime/terminal.md T3).

The cache never decides a grant: a grant only takes the cached subscriber id as the key of the lock it then reads the
account under, and refuses when the row it reads is not that id's.
"""
import threading
import time
from dataclasses import dataclass

TTL_SECONDS = 60
MAX_ENTRIES = 4096          # sessions are per sign-in; beyond this the cache starts again (a read costs one lookup)


@dataclass(frozen=True)
class Caller:
    """kind: 'gateway' (TERMINAL_PROXY_KEY, its account TERMINAL_PROXY_SUBSCRIBER), 'service' (a service key; `name`
    the service, its account `email`) or 'session' (a sign-in cookie; `token_hash`).

    EXEC-MU-ACCOUNTS Phase 3c (T2): a gateway call that names an EDGE owner (x-terminal-proxy-owner with
    x-terminal-capabilities, entitlements.py) carries `owner` and `caps`; its credential is ('gateway', owner), so the
    account cache, the usage and the audit rows are the owner's own row (terminal.subscriber.edge_owner_key). A gateway
    call without the headers keeps ('gateway', TERMINAL_PROXY_SUBSCRIBER), as before.

    Track guest (decision 1 of 2026-11-19): a gateway call for a visitor of EDGE's guest plan also carries `client`
    (x-terminal-client, the visitor's opaque key): the account row and the cache stay the owner's, the quota usage, its
    lock and the audit rows are the visitor's (main.py meter)."""
    kind: str
    name: str | None = None
    email: str | None = None
    token_hash: str | None = None
    owner: str | None = None
    caps: object = None                                   # entitlements.Capabilities with `owner`
    client: str | None = None                             # the visitor key beside `owner` (guests only)

    @property
    def credential(self):
        if self.kind == 'gateway' and self.owner is not None:
            return ('gateway', self.owner)
        return (self.kind, self.name or self.email or self.token_hash)

    @property
    def proxied(self):
        return self.kind in ('gateway', 'service')


class AccountCache:
    def __init__(self, ttl=TTL_SECONDS, max_entries=MAX_ENTRIES):
        self.ttl, self.max_entries = ttl, max_entries
        self._rows = {}
        self._lock = threading.Lock()

    def get(self, caller):
        """The account row of the last check, if it is at most ttl seconds old."""
        with self._lock:
            hit = self._rows.get(caller.credential)
        if hit and time.monotonic() - hit[1] <= self.ttl:
            return hit[0]
        return None

    def sid(self, caller):
        row = self.get(caller)
        return row['subscriber_id'] if row else None

    def put(self, caller, row):
        with self._lock:
            if len(self._rows) >= self.max_entries and caller.credential not in self._rows:
                self._rows.clear()
            self._rows[caller.credential] = (row, time.monotonic())

    def drop(self, caller):
        with self._lock:
            self._rows.pop(caller.credential, None)

    def clear(self):
        with self._lock:
            self._rows.clear()
