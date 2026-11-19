"""EXEC-MU-ACCOUNTS Phase 3c (T2; verification/edge_multiuser/access_tiers/CONTRACT.md section 8b "3c in detail"): who
the EDGE gateway acts for and what that owner's plan lets the Terminal serve.

edge-bff sends two headers beside the gateway key (only the gateway key; a service key or a session never names an
owner):

- ``x-terminal-proxy-owner``: the principal's owner key (the same rule as Orc's X-Saniti-Owner, OWNER_RE);
- ``x-terminal-capabilities``: compact ASCII JSON of at most 8 KiB, exactly the keys of EXAMPLE:
  ``{"v":1,"version":"<principal version>","admin":bool,"tickers":"*"|[..],"datasets":"*"|[..],
  "history_days":null|N,"quota":{..}}``.

Both absent: the gateway acts for its one account as before this phase (deploy step 2: terminal-api accepts the headers
before edge-bff sends them). One without the other, or a header that breaks a rule, is refused with 400 naming the
field, the rule and a right example (parse). Nothing here reads the database.

Re-check fix round (track terminal, verification/edge_multiuser/fix_round/terminal.md):
- R2-5: a `datasets` id this terminal-api does not know is not served anyway, so it is left out (Capabilities.ignored,
  logged by main.py), never a refusal of the whole call: an edge-bff that knows one dataset more (it deploys on a green
  push, terminal-api by a hand upload) keeps working. Order rule: a dataset is added on terminal-api first and removed
  on edge-bff first. An unknown field, quota name or `v` is still refused: those are contract errors.
- R1-22: `history_days` takes 0 (MIN_HISTORY_DAYS): no row dated on or before data_through is served, the value edge-bff
  sends for a plan whose history limit reads as 0 (edge-bff's principal.RESTRICTIVE), so the page files, which carry no
  history window, keep working while every dated path is refused (edge-bff refuses them first).
- R2-4: every answer to an owner call carries APPLIED_HEADER, "<v> <version>" of the header it applied (main.py's
  middleware), so edge-bff can refuse an answer of a terminal-api that ignored the headers (one from before Phase 3c).

The window of a capped owner (decision D2 = A, "exactly the last N calendar days"): with history_days N and a dataset's
manifest ``data_through`` D (its date part), the rows served are those dated strictly after D - N days, with no upper
bound (window_after). Example: N = 730, D = 2026-11-17: D - 730 days = 2024-11-17, so the first date served is
2024-11-18 and 2024-11-17 is not; 2024-11-18 .. 2026-11-17 are exactly 730 calendar days.
"""
import datetime as dt
import json
import re
from dataclasses import dataclass

OWNER_HEADER = 'x-terminal-proxy-owner'
CAPS_HEADER = 'x-terminal-capabilities'
MAX_CAPS_BYTES = 8192
# the same rule as Orc's owner header (apps/market-ai-orc/app/conversations.py OWNER_RE): edge-bff's owner keys
# (u_<24 hex>, EDGE_OWNER such as edge-private, the golden-/test- owners) all match it
OWNER_RE = re.compile(r'^[A-Za-z0-9._:@-]{1,128}$')
VERSION_RE = re.compile(r'^[A-Za-z0-9._:-]{1,64}$')          # edge-bff principal.version: 'env', 'none', 'db-<12 hex>'
TICKER_RE = re.compile(r'^[A-Z0-9]{1,12}$')
MAX_TICKERS = 5000
MAX_HISTORY_DAYS = 36600                                        # 100 years: beyond any published history
MIN_HISTORY_DAYS = 0                                            # 0: no dated row up to data_through (R1-22)
# R2-4: the acknowledgement of an applied header, on every answer to an owner call (applied())
APPLIED_HEADER = 'x-terminal-capabilities-applied'
MAX_QUOTA = 1_000_000_000
# the Terminal quota names a plan may set (terminal.quota rows of the same names); a key left out keeps its default
QUOTA_KEYS = ('files_per_hour', 'tickers_per_hour', 'tickers_per_day', 'megabytes_per_day', 'history_per_hour')
FIELDS = ('v', 'version', 'admin', 'tickers', 'datasets', 'history_days', 'quota')
EXAMPLE = ('{"v":1,"version":"db-0123456789ab","admin":false,"tickers":["BBCA"],"datasets":["price"],'
           '"history_days":730,"quota":{"files_per_hour":300}}')
ADMIN_EXAMPLE = '{"v":1,"version":"env","admin":true,"tickers":"*","datasets":"*","history_days":null,"quota":{}}'
# the datasets beside the per-ticker file datasets (main.py BUNDLE_DATASET): a ticker's intraday bars and the
# reference files (ticker list, broker list, logos, fixed income, stock lists)
EXTRA_DATASETS = ('intraday', 'reference')


class HeaderError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class Capabilities:
    """What the owner's plan lets the Terminal serve. tickers/datasets: None = every one ("*"), else a frozenset.
    history_days: None = no limit. quota: ((name, value), ...) sorted, the plan's own Terminal limits. ignored: the
    dataset ids of the header this terminal-api does not know (left out, R2-5)."""
    version: str
    admin: bool
    tickers: frozenset | None
    datasets: frozenset | None
    history_days: int | None
    quota: tuple
    ignored: tuple = ()

    def ticker_ok(self, ticker):
        return self.admin or self.tickers is None or ticker in self.tickers

    def dataset_ok(self, dataset):
        return self.admin or self.datasets is None or dataset in self.datasets

    @property
    def capped(self):
        return not self.admin and self.history_days is not None


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def parse_owner(raw):
    value = raw.strip()
    if not OWNER_RE.fullmatch(value):
        raise HeaderError(OWNER_HEADER, f'{OWNER_HEADER} must be the EDGE owner key, 1-128 letters, digits or . _ : @ - '
                                        f'(rule {OWNER_RE.pattern}); {len(raw)} characters were sent. Fix: send the '
                                        f"principal's owner_key. Example: {OWNER_HEADER}: u_0123456789abcdef01234567.")
    return value


def parse_capabilities(raw, datasets):
    """The header's Capabilities, or HeaderError naming the field. `datasets`: every dataset id this terminal-api
    knows (main.py DATASETS, derived from its own definitions)."""
    def bad(field, rule):
        raise HeaderError(field, f'{CAPS_HEADER} field {field!r}: {rule}. Fix: build the header from the principal '
                                 f'(compact ASCII JSON, at most {MAX_CAPS_BYTES} bytes, exactly the keys '
                                 f'{", ".join(FIELDS)}). Example: {CAPS_HEADER}: {EXAMPLE}; the configured owner '
                                 f'(holding *): {ADMIN_EXAMPLE}.')
    if len(raw) > MAX_CAPS_BYTES:
        bad('header', f'{len(raw)} bytes, more than {MAX_CAPS_BYTES}')
    if not raw.isascii():
        bad('header', 'it holds a character outside ASCII')
    try:
        doc = json.loads(raw)
    except ValueError:
        bad('header', 'it is not JSON')
    if not isinstance(doc, dict):
        bad('header', 'it is not a JSON object')
    extra, missing = sorted(set(doc) - set(FIELDS)), [f for f in FIELDS if f not in doc]
    if extra:
        bad(extra[0], 'is not a field of version 1')
    if missing:
        bad(missing[0], 'is missing')
    if not _whole(doc['v']) or doc['v'] != 1:
        bad('v', f'must be 1 (the only version), not {doc["v"]!r}')
    version = doc['version']
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        bad('version', f'must be the principal version, 1-64 letters, digits or . _ : - (rule {VERSION_RE.pattern})')
    admin = doc['admin']
    if not isinstance(admin, bool):
        bad('admin', 'must be true or false')

    def ids(field, rule, limit=MAX_TICKERS):
        v = doc[field]
        if v == '*':
            return None
        if not isinstance(v, list) or len(v) > limit:
            bad(field, f'must be "*" or a list of at most {limit} ids')
        for x in v:
            if not isinstance(x, str) or not rule.fullmatch(x):
                bad(field, f'{x!r} is not an id of the rule {rule.pattern}')
        if len(set(v)) != len(v):
            bad(field, 'lists an id twice')
        return frozenset(v)
    tickers = ids('tickers', TICKER_RE)
    data = ids('datasets', re.compile(r'^[a-z][a-z_]{0,31}$'), limit=64)
    # R2-5: an id this terminal-api does not know is not served by it anyway: left out (fail closed), named in `ignored`
    ignored = tuple(sorted(data - frozenset(datasets))) if data is not None else ()
    if ignored:
        data = data & frozenset(datasets)
    days = doc['history_days']
    if days is not None and not (_whole(days) and MIN_HISTORY_DAYS <= days <= MAX_HISTORY_DAYS):
        bad('history_days', f'must be null (no limit) or a whole number of calendar days {MIN_HISTORY_DAYS}-'
                            f'{MAX_HISTORY_DAYS} (0: no row dated up to the data\'s last date)')
    q = doc['quota']
    if not isinstance(q, dict):
        bad('quota', 'must be an object of the plan\'s Terminal limits ({} when the plan sets none)')
    for name, value in q.items():
        if name not in QUOTA_KEYS:
            bad('quota', f'{name!r} is not a Terminal quota (known: {", ".join(QUOTA_KEYS)})')
        if not (_whole(value) and 1 <= value <= MAX_QUOTA):
            bad('quota', f'{name} must be a whole number 1-{MAX_QUOTA}, not {value!r}')
    if admin and (tickers is not None or data is not None or days is not None or q):
        bad('admin', 'true (the principal holds *) goes with "tickers":"*", "datasets":"*", "history_days":null and '
                     '"quota":{}; a plan with limits sends "admin":false')
    return Capabilities(version, admin, tickers, data, days, tuple(sorted(q.items())), ignored)


def applied(caps):
    """The value of APPLIED_HEADER for an applied header: '<v> <version>' (v is always 1 here)."""
    return f'1 {caps.version}'


def data_date(value):
    """The date part of a manifest data_through ('2026-10-23' or '2026-10-25T17:04:28Z'), or None."""
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def window_after(data_through, days):
    """The last date NOT served: rows dated strictly after it are in the window (module docstring). None when the
    dataset has no readable data_through (nothing can be cut)."""
    d = data_date(data_through)
    return None if d is None else d - dt.timedelta(days=days)
