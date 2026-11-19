"""EXEC-MU-ACCOUNTS Phase 3c (CONTRACT.md 8b "3c in detail"): what edge-bff tells terminal-api about the principal of a
request, and what it refuses before asking terminal-api at all.

Every terminal-api call edge-bff makes for a principal (main.py forward_terminal, pages.py PageFiles) takes its headers
from `headers(settings, p)` and from nowhere else (tests/test_terminal_access.py greps app/ for the proxy key):

  x-terminal-proxy-key     the gateway key (TERMINAL_PROXY_KEY), as before
  x-terminal-proxy-owner   the principal's owner_key
  x-terminal-capabilities  compact ASCII JSON, at most 8 KiB, built from the principal only (`capabilities(p)`):
                           {"v":1,"version":..,"admin":bool,"tickers":"*"|[..],"datasets":"*"|[..],
                            "history_days":null|N,"quota":{..}}

- `admin` is '*' in the principal's capabilities; an admin's tickers and datasets are "*" and its history_days null.
- `tickers` is the list `terminal.tickers` (no row: "*"); `datasets` the ids of DATASET_IDS that
  p.can('terminal.dataset:<id>') grants, in DATASET_IDS order; `history_days` the plan's `terminal.history_days` (no
  row: null); `quota` the Terminal quota limits the plan sets (QUOTA, terminal-api's own names, each read from
  `terminal.<name>`; a limit the plan leaves out is left out, so terminal-api keeps its default for it; terminal-api takes
  1 to 10^9, so a larger one is sent as 10^9 and 0 is refused here 403 CAPABILITY_REQUIRED, R1-22).
- terminal-api's own 403 capability_required is answered in EDGE's CAPABILITY_REQUIRED shape (answered_capability).
- With EDGE_MULTIUSER off the configured owner holds '*': its header is admin with everything and terminal-api answers
  exactly as before.

Re-check fix round (track terminal; verification/edge_multiuser/fix_round/terminal.md):
- R1-22: every value the plan catalog can hold maps onto the header terminal-api takes (capabilities): `history_days`
  above MAX_HISTORY_DAYS is sent as that bound (narrower, never wider); 0, the value of a limit that cannot be read
  (principal.RESTRICTIVE), is sent as 0, the empty window terminal-api takes, and `check` refuses every dated path first
  with 403 CAPABILITY_REQUIRED terminal.history_days, so the page files (no history window) keep working; a ticker
  outside terminal-api's rule (TICKER) is left out and logged, never sent; a quota of 0 is 403 CAPABILITY_REQUIRED
  naming the limit (waiting would not help, so it is not a 429).
- ERRORS M260 (the user's go 2026-11-19, "a"): a 2xx JSON answer reaches the page only through client.public_data, in
  `relayed` (no private key, no *.railway.internal address), as every Orc and worker relay does; tests/
  test_decisions_small.py walks every route that calls terminal-api with a planted answer.
- R1-1, R1-26: `relayed` is the one rule for every terminal-api answer edge-bff relays (main.py forward_terminal and
  relay_cut, pages.py PageFiles), so each refusal reaches the page in the contract's shape (CONTRACT.md section 3): a
  401, or a 403 other than capability_required, is about terminal-api's own account, key or host rule, never the EDGE
  session, so it is 503 TERMINAL_UNAVAILABLE with the upstream code logged; a 429 is 429 LIMIT_REACHED with
  details.limit terminal.<quota>, details.allowed, retry_after_s and Retry-After, from the fields terminal-api adds (its
  quota name, its limit and the seconds until its window frees; QUOTA_RETRY_SECONDS when an older terminal-api names
  none); a 400 about the request is 400 INVALID_INPUT and a 404 404 NOT_FOUND, each with terminal-api's code as
  details.reason; a 400 about edge-bff's own headers and every 5xx are 503 TERMINAL_UNAVAILABLE, logged. terminal-api's
  prose never reaches the page (its messages name internal routes).
- R2-4: an answer for a principal without '*' is relayed only when terminal-api acknowledges the header it applied
  (APPLIED_HEADER "1 <version>"); without it (a terminal-api from before Phase 3c, which ignores the owner headers and
  would serve the plan in full) the answer is 503 TERMINAL_UNAVAILABLE, logged. The switch-off principal holds '*', so
  nothing changes while the switch is off.
- R2-32: the reference files are no longer refused: terminal-api answers a plan without the dataset `reference` with
  its own copy (apps/terminal-api/app/refcut.py: the rows of its tickers), relayed byte for byte from
  reference/<name>/cut like a cut.

A request from the page that carries one of RESERVED is refused 400 HEADER_NOT_ALLOWED naming the header (`guard`),
before any terminal-api call: the page never sets them, edge-bff never copies a request header to terminal-api, so a
header that claims an owner or capabilities is never relayed and never trusted.

Refuse first (`check`, CONTRACT.md 8b "edge-bff refuses first"): for a principal without '*', a ticker outside `tickers`,
a dataset outside `datasets` (an intraday timeframe is the dataset `intraday`), a /bundle whose every dataset is locked,
/history with `history_days` set, and every dated path (/files, /bundle, /cut) with `history_days` 0 answer 403
CAPABILITY_REQUIRED (with its display_name) before terminal-api is asked. A reference file is forwarded: terminal-api
answers a plan without the dataset `reference` with its own copy (R2-32). A /bundle with some allowed datasets is
forwarded: terminal-api answers the locked ones `{locked: true, capability}`. The checked JSON body is what is
forwarded (re-serialised), so terminal-api reads exactly what was checked.

The dataset ids come from one place (DATASETS = terminal-api's BUNDLE_DATASET, FILES_DATASETS its FilesRequest dataset,
BUNDLE_DEFAULT its BundleRequest default); tests/test_terminal_access.py reads apps/terminal-api/app/main.py and fails
when they differ, so a dataset terminal-api adds is locked for a plan until it is named here (never open by default).
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import Depends, Request

from .client import public_data
from .errors import Refusal, capability_required

logger = logging.getLogger('edge_bff.terminal_access')

# terminal-api's dataset names (app/main.py BUNDLE_DATASET, FilesRequest.dataset, BundleRequest.datasets default)
DATASETS = ('price', 'broker', 'events', 'yield')
FILES_DATASETS = ('price', 'broker', 'events')
BUNDLE_DEFAULT = ('price', 'broker', 'events')
INTRADAY, REFERENCE = 'intraday', 'reference'
# terminal-api's bounds of the header (apps/terminal-api/app/entitlements.py MAX_HISTORY_DAYS, TICKER_RE; tests compare)
MAX_HISTORY_DAYS = 36600
TICKER = re.compile(r'[A-Z0-9]{1,12}')
# R2-4: terminal-api's acknowledgement of the header it applied (entitlements.py APPLIED_HEADER, applied())
APPLIED_HEADER = 'x-terminal-capabilities-applied'
# R1-1: terminal-api refusals about the owner headers edge-bff built itself: edge-bff's fault, never the page's
OWN_HEADER_CODES = ('invalid_owner_headers', 'owner_not_allowed')
REASON = re.compile(r'[a-z][a-z0-9_]{0,63}')
DATASET_IDS = DATASETS + (INTRADAY, REFERENCE)
# GET /history/<name> reads the dataset of the same name
HISTORY_DATASETS = ('price', 'broker')
# the datasets terminal-api cuts to the last N days (GET /cut/<TICKER>/<dataset>; CONTRACT.md 8b D2 = A; terminal-api's
# cut route takes the dated datasets of /bundle, not intraday)
CUT_DATASETS = DATASETS
# terminal-api's quota names (app/quota.py check); the plan's limit of each is the capability terminal.<name>. terminal-api
# takes each as an integer from 1 to QUOTA_MAX (history_per_hour too, which no plan sets: its default stays)
QUOTA = ('tickers_per_hour', 'tickers_per_day', 'files_per_hour', 'megabytes_per_day')
QUOTA_MAX = 10 ** 9
QUOTA_RETRY_SECONDS = 3600
# terminal-api's owner key rule (x-terminal-proxy-owner); every EDGE owner key fits it
OWNER_KEY = re.compile(r'[A-Za-z0-9._:@-]{1,128}')

EVERYTHING = '*'
TICKERS, HISTORY_DAYS, DATASET = 'terminal.tickers', 'terminal.history_days', 'terminal.dataset'
OWNER_HEADER, CAPABILITIES_HEADER, KEY_HEADER = 'x-terminal-proxy-owner', 'x-terminal-capabilities', 'x-terminal-proxy-key'
RESERVED = (KEY_HEADER, OWNER_HEADER, CAPABILITIES_HEADER)
MAX_HEADER_BYTES = 8192


def admin(p):
    return EVERYTHING in p.capabilities


def _limit(p, key):
    value = p.limit(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _tickers(p):
    """(the plan's tickers terminal-api's rule takes, sorted; the ones it does not, left out) or (None, ()) for no row
    (every ticker). A list of strings (principal.read_grants); any other shape reads as no ticker (fail closed)."""
    tickers = p.limit(TICKERS)
    if tickers is None:
        return None, ()
    names = set(t for t in tickers if isinstance(t, str)) if isinstance(tickers, list) else set()
    return sorted(t for t in names if TICKER.fullmatch(t)), tuple(sorted(t for t in names if not TICKER.fullmatch(t)))


def capabilities(p):
    """The x-terminal-capabilities object of a principal (module docstring); nothing else goes into it. Every value
    the catalog can hold maps onto what terminal-api takes, never wider than the plan (R1-22)."""
    if admin(p):
        return {'v': 1, 'version': p.version, 'admin': True, 'tickers': EVERYTHING, 'datasets': EVERYTHING,
                'history_days': None, 'quota': {}}
    tickers, _ = _tickers(p)
    # above terminal-api's bound a limit is the bound (never wider than the plan); 0 is refused in capabilities_header
    quota = {name: min(value, QUOTA_MAX) for name in QUOTA if (value := _limit(p, f'terminal.{name}')) is not None}
    days = _limit(p, HISTORY_DAYS)
    return {'v': 1, 'version': p.version, 'admin': False, 'tickers': EVERYTHING if tickers is None else tickers,
            'datasets': [d for d in DATASET_IDS if p.can(f'{DATASET}:{d}')],
            'history_days': None if days is None else min(days, MAX_HISTORY_DAYS), 'quota': quota}


def capabilities_header(p):
    """The header's value: compact ASCII JSON of capabilities(p), at most MAX_HEADER_BYTES. A longer one (a ticker list
    of more than about 900 names) is refused with 503 TERMINAL_UNAVAILABLE and logged, never cut short or dropped. A
    quota of 0 (terminal-api takes 1 to 10^9; leaving it out would give terminal-api's default, a wider one) answers 403
    CAPABILITY_REQUIRED naming the limit, before terminal-api is asked: the plan allows none of it, so waiting would not
    help (R1-22). A ticker of the plan outside terminal-api's rule is left out (capabilities) and logged here."""
    caps = capabilities(p)
    for name, value in caps['quota'].items():
        if value < 1:
            raise capability_required(f'terminal.{name}')
    if not admin(p) and (dropped := _tickers(p)[1]):
        logger.warning(json.dumps({'event': 'terminal_tickers_dropped', 'owner_key': p.owner_key,
                                   'count': len(dropped), 'rule': TICKER.pattern}))
    text = json.dumps(caps, separators=(',', ':'), ensure_ascii=True, sort_keys=False)
    if len(text) > MAX_HEADER_BYTES:
        logger.warning(json.dumps({'event': 'terminal_capabilities_too_large', 'owner_key': p.owner_key,
                                   'bytes': len(text)}))
        raise Refusal(503, 'TERMINAL_UNAVAILABLE')
    return text


def headers(settings, p):
    """The headers of every terminal-api call made for the principal p (the only place they are built): both terminal
    headers always beside the gateway key (terminal-api refuses one without the other)."""
    if not OWNER_KEY.fullmatch(p.owner_key or ''):
        logger.warning(json.dumps({'event': 'terminal_owner_key_invalid'}))
        raise Refusal(503, 'TERMINAL_UNAVAILABLE')
    return {'content-type': 'application/json', KEY_HEADER: settings.terminal_proxy_key,
            OWNER_HEADER: p.owner_key, CAPABILITIES_HEADER: capabilities_header(p)}


_guards = {}


def guard(base):
    """A dependency: the principal of `base` (an auth.need(...) dependency), after refusing a request that carries a
    header edge-bff sets itself (RESERVED). Every route that calls terminal-api depends on it (the route walk of
    tests/test_terminal_access.py finds it in the dependant tree)."""
    if base not in _guards:
        async def terminal_guard(request: Request, p=Depends(base)):
            refuse_reserved(request)
            return p
        terminal_guard.terminal_guard = True
        _guards[base] = terminal_guard
    return _guards[base]


def refuse_reserved(request):
    for name in RESERVED:
        if name in request.headers:
            raise Refusal(400, 'HEADER_NOT_ALLOWED', {'header': name})


def invalid(*fields):
    return Refusal(422, 'INVALID_INPUT', {'fields': list(fields)})


def _ticker(caps, ticker):
    if caps['tickers'] != EVERYTHING and ticker not in caps['tickers']:
        raise capability_required(TICKERS)


def _dataset(caps, dataset):
    if dataset not in caps['datasets']:
        raise capability_required(f'{DATASET}:{dataset}')


def _body(body):
    try:
        data = json.loads(body or b'')
    except (ValueError, UnicodeDecodeError):
        raise invalid('body') from None
    if not isinstance(data, dict):
        raise invalid('body')
    if not isinstance(data.get('ticker'), str):
        raise invalid('ticker')
    return data


def check(p, method, path, query, body):
    """Refuse before terminal-api (module docstring). path is the route regex's match (main.py TERMINAL_ROUTES), query
    the request's query parameters, body the POST bytes. Returns the body to forward: the request's own bytes for an
    admin (unchanged, as before 3c), else the checked JSON re-serialised."""
    if admin(p):
        return body
    caps = capabilities(p)
    head, _, rest = path.partition('/')
    if caps['history_days'] == 0 and head in ('files', 'bundle', 'cut', 'history'):
        # R1-22: a window of 0 days holds no dated row (every /files, /bundle and /cut dataset is dated)
        raise capability_required(HISTORY_DAYS)
    if method == 'GET':
        if head in ('manifest', 'logo'):
            _ticker(caps, rest)
        elif head == 'reference':
            pass                                    # R2-32: terminal-api answers the plan's own copy (refcut.py)
        elif head == 'history':
            _dataset(caps, rest)
            tickers = query.getlist('ticker')
            if len(tickers) != 1:
                raise invalid('ticker')
            _ticker(caps, tickers[0])
            # history serves only the dates before the published files (terminal-api history_range): with the last N
            # days set they are outside the window (decision D2 = A)
            if caps['history_days'] is not None:
                raise capability_required(HISTORY_DAYS)
        elif head == 'cut':
            ticker, _, dataset = rest.partition('/')
            _ticker(caps, ticker)
            _dataset(caps, dataset)
        else:                                       # a forwarded GET route this function does not know
            raise capability_required(DATASET)
        return body
    data = _body(body)
    _ticker(caps, data['ticker'])
    if head == 'files':
        dataset = data.get('dataset')
        if not isinstance(dataset, str):
            raise invalid('dataset')
        _dataset(caps, dataset)
    elif head == 'bundle':
        asked = data.get('datasets', list(BUNDLE_DEFAULT))
        if not isinstance(asked, list) or not asked or not all(isinstance(d, str) for d in asked):
            raise invalid('datasets')
        asked = list(dict.fromkeys(asked)) + ([INTRADAY] if data.get('timeframe') else [])
        locked = [d for d in asked if d not in caps['datasets']]
        if len(locked) == len(asked):
            raise capability_required(f'{DATASET}:{locked[0]}')
    else:
        raise capability_required(DATASET)
    return json.dumps(data, separators=(',', ':'), ensure_ascii=True).encode()


def answered_capability(status, data):
    """The capability of terminal-api's own refusal (403 {"error": "capability_required", "capability": ..}), relayed by
    edge-bff in its CAPABILITY_REQUIRED shape with the display_name; None for any other answer."""
    if status == 403 and isinstance(data, dict) and data.get('error') == 'capability_required' \
            and isinstance(data.get('capability'), str) and 0 < len(data['capability']) <= 128:
        return data['capability']
    return None


def acknowledged(p, headers):
    """R2-4: whether terminal-api applied the header edge-bff sent for p (APPLIED_HEADER "1 <version>"); always true
    for a principal holding '*' (its header asks for nothing to be held back)."""
    return admin(p) or (headers.get(APPLIED_HEADER) or '') == f'1 {p.version}'


def _wait(data, headers):
    """The seconds a 429 of terminal-api names (its retry_after_s, else its Retry-After), else QUOTA_RETRY_SECONDS;
    1 to one day."""
    for value in (data.get('retry_after_s'), headers.get('retry-after')):
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= seconds <= 86400:
            return seconds
    return QUOTA_RETRY_SECONDS


def relayed(p, status, data, headers, where):
    """The one rule for a terminal-api answer edge-bff relays (module docstring, R1-1, R1-26, R2-4, M260): a pair
    (refusal, data). (None, public data) when the answer may go to the page (a 2xx terminal-api acknowledged): its JSON
    through client.public_data, the house filter of every upstream relay (ERRORS M260, the user's go 2026-11-19 "a"):
    no private key (PRIVATE_KEYS: reasoning, token, api_key, ...) and no *.railway.internal address reaches the page,
    whatever terminal-api answers (None stays None: a cut's bytes or a logo are relayed as they are, never parsed).
    (Refusal, None) otherwise, in the contract's shape. `data`: the answer's JSON (None when it has none); `where`: the
    route, for the log only."""
    if not acknowledged(p, headers):
        logger.warning(json.dumps({'event': 'terminal_capabilities_not_applied', 'status': status, 'where': where[:80],
                                   'fix': 'terminal-api is older than Phase 3c: deploy terminal-api first'}))
        return Refusal(503, 'TERMINAL_UNAVAILABLE'), None
    if 200 <= status < 300:
        return None, public_data(data)
    return refused_answer(status, data, headers, where), None


def refused_answer(status, data, headers, where):
    """A non-2xx terminal-api answer as the Refusal the page gets (relayed)."""
    data = data if isinstance(data, dict) else {}
    code = data.get('error') if isinstance(data.get('error'), str) else None
    reason = {'reason': code} if code and REASON.fullmatch(code) else {}
    if (capability := answered_capability(status, data)) is not None:
        return capability_required(capability)
    if status == 429:
        wait = _wait(data, headers)
        name = data.get('quota') if isinstance(data.get('quota'), str) and REASON.fullmatch(data['quota']) else None
        details = {'limit': f'terminal.{name}' if name else 'terminal.quota', 'retry_after_s': wait}
        if isinstance(data.get('limit'), int) and not isinstance(data['limit'], bool):
            details['allowed'] = data['limit']
        return Refusal(429, 'LIMIT_REACHED', details, headers={'Retry-After': str(wait)})
    if status == 404:
        return Refusal(404, 'NOT_FOUND', reason)
    if status == 400 and code not in OWN_HEADER_CODES:
        fields = [f['field'] for f in data.get('fields') or ()
                  if isinstance(f, dict) and isinstance(f.get('field'), str)]
        return Refusal(400, 'INVALID_INPUT', {**reason, **({'fields': fields[:20]} if fields else {})})
    # a 401 or 403 (terminal-api's own account, key or host rule), a 400 about edge-bff's own headers, a 5xx: nothing
    # the page or the person can fix, so never their sign-in or plan (CONTRACT.md section 3)
    logger.warning(json.dumps({'event': 'terminal_refused', 'status': status, 'code': code, 'where': where[:80]}))
    return Refusal(503, 'TERMINAL_UNAVAILABLE')
