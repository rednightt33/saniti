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
  1 to 10^9, so a larger one is sent as 10^9 and 0 is refused here 429 LIMIT_REACHED).
- terminal-api's own 403 capability_required is answered in EDGE's CAPABILITY_REQUIRED shape (answered_capability).
- With EDGE_MULTIUSER off the configured owner holds '*': its header is admin with everything and terminal-api answers
  exactly as before.

A request from the page that carries one of RESERVED is refused 400 HEADER_NOT_ALLOWED naming the header (`guard`),
before any terminal-api call: the page never sets them, edge-bff never copies a request header to terminal-api, so a
header that claims an owner or capabilities is never relayed and never trusted.

Refuse first (`check`, CONTRACT.md 8b "edge-bff refuses first"): for a principal without '*', a ticker outside `tickers`,
a dataset outside `datasets` (a reference file is the dataset `reference`, an intraday timeframe `intraday`), a /bundle
whose every dataset is locked, and /history with `history_days` set answer 403 CAPABILITY_REQUIRED (with its
display_name) before terminal-api is asked. A /bundle with some allowed datasets is forwarded: terminal-api answers the
locked ones `{locked: true, capability}`. The checked JSON body is what is forwarded (re-serialised), so terminal-api
reads exactly what was checked.

The dataset ids come from one place (DATASETS = terminal-api's BUNDLE_DATASET, FILES_DATASETS its FilesRequest dataset,
BUNDLE_DEFAULT its BundleRequest default); tests/test_terminal_access.py reads apps/terminal-api/app/main.py and fails
when they differ, so a dataset terminal-api adds is locked for a plan until it is named here (never open by default).
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import Depends, Request

from .errors import Refusal, capability_required

logger = logging.getLogger('edge_bff.terminal_access')

# terminal-api's dataset names (app/main.py BUNDLE_DATASET, FilesRequest.dataset, BundleRequest.datasets default)
DATASETS = ('price', 'broker', 'events', 'yield')
FILES_DATASETS = ('price', 'broker', 'events')
BUNDLE_DEFAULT = ('price', 'broker', 'events')
INTRADAY, REFERENCE = 'intraday', 'reference'
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


def capabilities(p):
    """The x-terminal-capabilities object of a principal (module docstring); nothing else goes into it."""
    if admin(p):
        return {'v': 1, 'version': p.version, 'admin': True, 'tickers': EVERYTHING, 'datasets': EVERYTHING,
                'history_days': None, 'quota': {}}
    tickers = p.limit(TICKERS)
    if tickers is not None:
        # a list of strings (principal.read_grants); any other shape reads as no ticker (fail closed)
        tickers = sorted(set(t for t in tickers if isinstance(t, str))) if isinstance(tickers, list) else []
    # above terminal-api's bound a limit is the bound (never wider than the plan); 0 is refused in capabilities_header
    quota = {name: min(value, QUOTA_MAX) for name in QUOTA if (value := _limit(p, f'terminal.{name}')) is not None}
    return {'v': 1, 'version': p.version, 'admin': False, 'tickers': EVERYTHING if tickers is None else tickers,
            'datasets': [d for d in DATASET_IDS if p.can(f'{DATASET}:{d}')], 'history_days': _limit(p, HISTORY_DAYS),
            'quota': quota}


def capabilities_header(p):
    """The header's value: compact ASCII JSON of capabilities(p), at most MAX_HEADER_BYTES. A longer one (a ticker list
    of more than about 900 names) is refused with 503 TERMINAL_UNAVAILABLE and logged, never cut short or dropped. A
    quota of 0 (terminal-api takes 1 to 10^9; leaving it out would give terminal-api's default, a wider one) answers 429
    LIMIT_REACHED naming the limit, before terminal-api is asked."""
    for name, value in capabilities(p)['quota'].items():
        if value < 1:
            raise Refusal(429, 'LIMIT_REACHED', {'limit': f'terminal.{name}', 'allowed': 0,
                                                 'retry_after_s': QUOTA_RETRY_SECONDS},
                          headers={'Retry-After': str(QUOTA_RETRY_SECONDS)})
    text = json.dumps(capabilities(p), separators=(',', ':'), ensure_ascii=True, sort_keys=False)
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
    if method == 'GET':
        if head in ('manifest', 'logo'):
            _ticker(caps, rest)
        elif head == 'reference':
            _dataset(caps, REFERENCE)
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
