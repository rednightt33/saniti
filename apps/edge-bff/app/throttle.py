"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md sections 1 and 4 "Throttle"): the sign-in throttle in
PostgreSQL (edge_bff.auth_throttle, migration 20261116_002), shared by every edge-bff instance.

- A key (the login typed at sign-in with the client address, an email address, a user id) is stored only as key_hash =
  HMAC-SHA256 with EDGE_SESSION_SECRET of its normalised form, with a domain label, the scope and the counter's own
  label in the message, so the same secret's CSRF tokens (security.py csrf_token) never collide with a throttle key and
  no text a caller types can produce the key of another counter (ERRORS R1-10: the login 'change:<user_id>' was the
  key of that user's password-change count). Two limits read one counter when they share its label (REGISTER_HOUR and
  REGISTER_DAY: one count of new registrations, read over an hour and over a day).
- Counts live in one-minute buckets; a limit sums the buckets that overlap its window (a bucket only partly inside
  counts whole, so the limit errs on the safe side by at most one minute).
- A sign-in try is decided and counted in one step before the password check (`attempt`): one transaction takes an
  advisory lock on the scope and key hash, sums the window and, under the limit, adds the try with an atomic UPSERT.
  A concurrent burst against one key, on any number of instances, therefore reaches the password check at most
  `allowed` times per window (ERRORS C1 H1; OWASP: count the attempt atomically with the decision). A successful
  sign-in clears its key's count, so only failed tries remain counted.
- Enforced now: SIGNIN_LOGIN, 10 failures per login and client address per 15 minutes (ERRORS R1-9: keyed by the login
  alone, anyone who typed a login could keep its owner out; the per-account cap of consecutive failures, accounts.py,
  bounds the guesses across addresses). Recorded, not enforced: SIGNIN_IP, until a probe proves which client address
  Railway's edge sends (CONTRACT.md section 4, "Client IP").
"""
import hashlib
import hmac
import ipaddress
import json
import math

BUCKET_SECONDS = 60
PURGE_AFTER_SECONDS = 2 * 86400


class Limit:
    """`allowed` events of one counter in `window_seconds`. `scope` is the table's scope (its CHECK lists them);
    `counter` is the counter's own label inside the key hash, one per counted thing."""

    def __init__(self, scope, counter, allowed, window_seconds, enforced=True):
        self.scope, self.counter, self.allowed, self.window_seconds, self.enforced = \
            scope, counter, allowed, window_seconds, enforced


# the sign-in: key (normalised login, client address)
SIGNIN_LOGIN = Limit('signin_email', 'signin_login_address', 10, 900)
# the client address of every failed sign-in; also the label of the address hash a session keeps (created_ip_hash)
SIGNIN_IP = Limit('signin_ip', 'signin_address', 30, 900, enforced=False)
# EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4 "Codes", "Throttle"): 20 failed code tries per user per day (a new
# code does not reset it); 10 emails per address per day; 10 sends per client address per hour (recorded, not enforced,
# like SIGNIN_IP); 10 failed MFA tries per user per 15 minutes; 10 failed current passwords per user per 15 minutes
# (a password change)
CODE_USER = Limit('code_user', 'code_user', 20, 86400)
# ERRORS R1-8: the failed reset codes of an address, counted whether or not the address has an account, so the 429
# after 20 wrong codes tells nothing about the address
CODE_ADDRESS = Limit('code_user', 'code_address', 20, 86400)
SEND_EMAIL = Limit('send_email', 'send_email', 10, 86400)
SEND_IP = Limit('send_ip', 'send_address', 10, 3600, enforced=False)
MFA_USER = Limit('code_user', 'mfa_user', 10, 900)
PASSWORD_CHANGE = Limit('signin_email', 'password_change', 10, 900)
# The A2 fix (ERRORS M513 A2, M517; CONTRACT.md section 4 "Throttle"): no limit a stranger can fill by naming a login or
# an address may close the owner's way in or back.
# - SEND_EMAIL_CLIENT: the code emails one client address causes to one address in a day (key: the address and the
#   client), beside the address's SEND_EMAIL; one client alone cannot spend an address's day (a stranger needs three).
# - DEVICE_MAIL: the code emails a browser where the account's password was proved (security.device_of) may ask for in
#   a day (key: the address and the device); such a request is held by this limit instead of SEND_EMAIL and
#   SEND_EMAIL_CLIENT, so the owner's own browser still gets its reset code when strangers spent the address's day.
# - DEVICE_SIGNIN: the failed passwords of such a browser in a day (key: the account and the device); under it the
#   browser's tries neither count towards nor wait for the account's lock of consecutive failures (accounts.py); past it
#   the browser is treated as any other.
SEND_EMAIL_CLIENT = Limit('send_email', 'send_email_client', 4, 86400)
DEVICE_MAIL = Limit('send_email', 'device_mail', 5, 86400)
DEVICE_SIGNIN = Limit('signin_email', 'signin_device', 10, 86400)
# ERRORS M478 re-check (N4): new registrations of one address mail it at most once per hour and three times per day
# (one counter read over both windows); they also count towards SEND_EMAIL. Since the A2 fix the key is the address and
# the client address (it was the address alone, so one stranger's registrations of an address held back its owner's
# for a day): the address's own ceiling is SEND_EMAIL with SEND_EMAIL_CLIENT
REGISTER_HOUR = Limit('send_email', 'register', 1, 3600)
REGISTER_DAY = Limit('send_email', 'register', 3, 86400)
# ERRORS R1-13: every email of one pending registration (its code, a resend, a sign-in restart) counts here, key the
# registration's user id: a registration is mailed at most 3 times a day, so the 3 registrations a day N4 allows use at
# most 9 of the address's 10 emails, and the 2 of them made by others (the owner's own being the third) at most 6
REGISTRATION_MAIL = Limit('send_email', 'registration_mail', 3, 86400)

# every visitor of the guest plan together (migration 20261119_071): one counter, key GUEST_TOTAL_KEY, built per app with
# the ceiling the setting gives (main.py; Settings.guest_calls_per_hour, 0: none and nothing counted)
GUEST_TOTAL_KEY = 'every visitor'


def guest_total(allowed):
    """The Limit of every visitor's Terminal calls together in an hour."""
    return Limit('guest_total', 'guest_terminal_calls', allowed, 3600)


BUCKET = 'to_timestamp(floor(extract(epoch FROM now()) / %(bucket)s) * %(bucket)s)'


def normal_login(login):
    """The login as the sign-in compares it (case-folded), without surrounding spaces."""
    return login.strip().casefold()


# CONTRACT.md section 4, the probe of 2026-11-20 (the user's "1a"; ERRORS M512): Railway's edge drops every
# X-Forwarded-For and X-Real-IP line the client writes and sends one line of its own, "<client>, <edge node>" (the
# client's public address, then the edge node's own: 152.233.40.1 and .2 seen on app.edgefinance.id). The client is
# therefore the entry EDGE_HOPS places left of the right-most: the right-most is the edge node, the same for everyone.
# Counting from the right keeps a line a client writes from deciding even if the edge ever kept such lines (they would
# stand left of the client's hop). Run the probe again whenever something else is put in front of the site.
EDGE_HOPS = 1


def forwarded_hop(request):
    """The client's entry of the request's X-Forwarded-For, read over every line of the header (a second line is read as
    appended to the first, RFC 9110 5.3): the entry EDGE_HOPS places left of the right-most, the hop Railway's edge
    writes for the client (ERRORS M512); a line the client wrote never decides (3c check C3-5). A header with fewer
    entries (a private caller, a local test) gives its left-most. None without the header."""
    lines = request.headers.getlist('x-forwarded-for')
    hops = [h.strip() for h in ','.join(lines).split(',') if h.strip()] if lines else []
    return hops[max(0, len(hops) - 1 - EDGE_HOPS)] if hops else None


def address_key(text):
    """An IP address as the key of one client: IPv4 as it is; IPv6 as its /64 prefix (one subscriber line usually
    holds a whole /64, so a client cannot take a new key per address in it; C3-5); an IPv4-mapped IPv6 address as its
    IPv4. None for anything that is not an address (fail closed)."""
    try:
        address = ipaddress.ip_address((text or '').strip())
    except ValueError:
        return None
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f'{address}/64', strict=False))
    return str(address)


def client_address(request):
    """The client's key for the sign-in and reset counters: the client's X-Forwarded-For hop over every line
    (forwarded_hop: the entry before the edge node's, as the probe of CONTRACT.md section 4 measured), else the socket
    peer, as an address_key; 'unknown' when neither is an address. SIGNIN_IP stays recorded and not enforced until
    the user decides it (ERRORS M512)."""
    hop = forwarded_hop(request)
    raw = hop if hop is not None else (request.client.host if request.client else '')
    # an address is keyed by address_key (IPv6 by its /64); anything else (a test client's peer name) as it is
    return address_key(raw) or (raw or '').strip().lower()[:100] or 'unknown'


class Throttle:
    def __init__(self, store, secret):
        self.store, self.secret = store, secret.encode()

    def key_hash(self, limit, key):
        """The stored hash of `key` for `limit`'s counter. A key of several parts (a tuple: the login and the client
        address) is written as a JSON list, so no part can run into the next."""
        text = json.dumps(list(key)) if isinstance(key, tuple) else key
        return hmac.new(self.secret, b'edge_bff.auth_throttle\x00' + limit.scope.encode() + b'\x00'
                        + limit.counter.encode() + b'\x00' + text.encode('utf-8', 'surrogatepass'),
                        hashlib.sha256).hexdigest()

    def attempt(self, limit, key):
        """Decide and count one try in one transaction: 0 when the try may go on (it is counted), else the seconds until
        the oldest counted bucket leaves the window (the try is refused and not counted). A limit that is not enforced
        only counts."""
        if not limit.enforced:
            self.count((limit, key))
            return 0
        hashed = self.key_hash(limit, key)
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
            return self._wait(c, limit, self.key_hash(limit, key))

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
                self._add(c, limit, self.key_hash(limit, key))

    @staticmethod
    def _add(c, limit, hashed):
        c.execute(f'''INSERT INTO edge_bff.auth_throttle(scope, key_hash, window_start, count)
                    VALUES (%(scope)s, %(key)s, {BUCKET}, 1)
                    ON CONFLICT (scope, key_hash, window_start) DO UPDATE SET count = edge_bff.auth_throttle.count + 1''',
                  {'scope': limit.scope, 'key': hashed, 'bucket': BUCKET_SECONDS})

    def clear(self, limit, *keys):
        """A successful sign-in forgets its key's failures (as the in-process limiter forgot them); a password reset
        proved by the email code forgets the account's logins from the resetting client (ERRORS R1-9)."""
        with self.store.connect() as c:
            for key in keys:
                c.execute('DELETE FROM edge_bff.auth_throttle WHERE scope = %s AND key_hash = %s',
                          (limit.scope, self.key_hash(limit, key)))


def purge(connection, limit=None):
    """Rows older than 2 days (CONTRACT.md section 1), at most limit of them (None: every one); the rows deleted. Called
    from Store.purge, the hourly housekeeping (worker.Housekeeping), on its connection and transaction."""
    return connection.execute('''DELETE FROM edge_bff.auth_throttle WHERE (scope, key_hash, window_start) IN (
            SELECT scope, key_hash, window_start FROM edge_bff.auth_throttle
            WHERE window_start < now() - make_interval(secs => %s) LIMIT %s)''', (PURGE_AFTER_SECONDS, limit)).rowcount
