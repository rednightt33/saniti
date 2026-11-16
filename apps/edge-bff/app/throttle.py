"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 1 and 4 "Throttle"): the sign-in throttle in
PostgreSQL (edge_bff.auth_throttle, migration 20261116_002), shared by every edge-bff instance.

- A key (the login typed at sign-in, a client address) is stored only as key_hash = HMAC-SHA256 with
  EDGE_SESSION_SECRET of its normalised form, with a domain label and the scope in the message, so the same secret's
  CSRF tokens (security.py csrf_token) never collide with a throttle key.
- Counts live in one-minute buckets; a limit sums the buckets that overlap its window (a bucket only partly inside
  counts whole, so the limit errs on the safe side by at most one minute).
- A sign-in try is decided and counted in one step before the password check (`attempt`): one transaction takes an
  advisory lock on the scope and key hash, sums the window and, under the limit, adds the try with an atomic UPSERT.
  A concurrent burst against one login, on any number of instances, therefore reaches the password check at most
  `allowed` times per window (ERRORS C1 H1; OWASP: count the attempt atomically with the decision). A successful
  sign-in clears the login's count, so only failed tries remain counted.
- Enforced now: SIGNIN_LOGIN (10 failures per login per 15 minutes). Recorded, not enforced: SIGNIN_IP, until a probe
  proves which client address Railway's edge sends (CONTRACT.md section 4, "Client IP").
"""
import hashlib
import hmac
import math

BUCKET_SECONDS = 60
PURGE_AFTER_SECONDS = 2 * 86400


class Limit:
    def __init__(self, scope, allowed, window_seconds, enforced=True):
        self.scope, self.allowed, self.window_seconds, self.enforced = scope, allowed, window_seconds, enforced


SIGNIN_LOGIN = Limit('signin_email', 10, 900)
SIGNIN_IP = Limit('signin_ip', 30, 900, enforced=False)
# EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4 "Codes", "Throttle"): 20 failed code tries per user per day (a new
# code does not reset it); 10 emails per address per day; 10 sends per client address per hour (recorded, not enforced,
# like SIGNIN_IP); 10 failed MFA tries per user per 15 minutes (scope code_user, key 'mfa:<user_id>')
CODE_USER = Limit('code_user', 20, 86400)
SEND_EMAIL = Limit('send_email', 10, 86400)
SEND_IP = Limit('send_ip', 10, 3600, enforced=False)
MFA_USER = Limit('code_user', 10, 900)

BUCKET = 'to_timestamp(floor(extract(epoch FROM now()) / %(bucket)s) * %(bucket)s)'


def normal_login(login):
    """The login as the sign-in compares it (case-folded), without surrounding spaces."""
    return login.strip().casefold()


def client_address(request):
    """The right-most X-Forwarded-For entry (the hop Railway's edge adds), else the socket peer. Unverified until the
    probe (CONTRACT.md section 4), which is why SIGNIN_IP is recorded and not enforced."""
    forwarded = request.headers.get('x-forwarded-for', '')
    last = forwarded.split(',')[-1].strip() if forwarded else ''
    return (last or (request.client.host if request.client else '') or 'unknown')[:100].lower()


class Throttle:
    def __init__(self, store, secret):
        self.store, self.secret = store, secret.encode()

    def key_hash(self, scope, key):
        return hmac.new(self.secret, b'edge_bff.auth_throttle\x00' + scope.encode() + b'\x00' + key.encode(),
                        hashlib.sha256).hexdigest()

    def attempt(self, limit, key):
        """Decide and count one try in one transaction: 0 when the try may go on (it is counted), else the seconds until
        the oldest counted bucket leaves the window (the try is refused and not counted). A limit that is not enforced
        only counts."""
        if not limit.enforced:
            self.count((limit, key))
            return 0
        hashed = self.key_hash(limit.scope, key)
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('auth_throttle:' + limit.scope + ':' + hashed,))
            wait = self._wait(c, limit, hashed)
            if not wait:
                self._add(c, limit, hashed)
        return wait

    def retry_after(self, limit, key):
        """0 while the key is under the limit (or the limit is not enforced), else the seconds until its oldest counted
        bucket leaves the window (at least 1). Reads only; a sign-in uses attempt."""
        if not limit.enforced:
            return 0
        with self.store.connect() as c:
            return self._wait(c, limit, self.key_hash(limit.scope, key))

    @staticmethod
    def _wait(c, limit, hashed):
        row = c.execute('''SELECT coalesce(sum(count), 0) AS used,
                       extract(epoch FROM min(window_start) + make_interval(secs => %(span)s) - now()) AS wait
                FROM edge_bff.auth_throttle
                WHERE scope = %(scope)s AND key_hash = %(key)s AND window_start > now() - make_interval(secs => %(span)s)''',
                        {'scope': limit.scope, 'key': hashed, 'span': limit.window_seconds + BUCKET_SECONDS}).fetchone()
        if row['used'] < limit.allowed:
            return 0
        return max(1, math.ceil(float(row['wait'] or 1)))

    def count(self, *events):
        """One more failure for each (limit, key), in one transaction; recorded whether or not the limit is enforced."""
        with self.store.connect() as c:
            for limit, key in events:
                self._add(c, limit, self.key_hash(limit.scope, key))

    @staticmethod
    def _add(c, limit, hashed):
        c.execute(f'''INSERT INTO edge_bff.auth_throttle(scope, key_hash, window_start, count)
                    VALUES (%(scope)s, %(key)s, {BUCKET}, 1)
                    ON CONFLICT (scope, key_hash, window_start) DO UPDATE SET count = edge_bff.auth_throttle.count + 1''',
                  {'scope': limit.scope, 'key': hashed, 'bucket': BUCKET_SECONDS})

    def clear(self, limit, key):
        """A successful sign-in forgets the login's failures (as the in-process limiter forgot them)."""
        with self.store.connect() as c:
            c.execute('DELETE FROM edge_bff.auth_throttle WHERE scope = %s AND key_hash = %s',
                      (limit.scope, self.key_hash(limit.scope, key)))


def purge(connection):
    """Rows older than 2 days (CONTRACT.md section 1); called from Store.cleanup_sessions, the worker loop's hourly
    cleanup, on the same connection and transaction."""
    connection.execute('DELETE FROM edge_bff.auth_throttle WHERE window_start < now() - make_interval(secs => %s)',
                       (PURGE_AFTER_SECONDS,))
