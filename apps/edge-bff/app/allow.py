"""EDGE multi-user Phase 3b (EXEC-MU-ACCOUNTS; CONTRACT.md 8b "3b in detail"): the `context` edge-bff sends the
Backtest and Screener workers, `{"rights", "allow", "limits"}`, built from the principal only (never a body: rights.py
refuse_context), when the call is made (a queued backtest reads its owner's principal at dispatch).

- `allow` holds, for each item kind the workers gate, `"*"` (every id, lab included) or the sorted ids of the release
  file (releases.entries) the principal holds in that worker's family (`p.can(family + ':' + id)`; FAMILIES: the
  indicator and Flow kinds of both workers read the Terminal's grants). `"*"` when the
  principal holds everything (`*`; the switch-off owner listed in EDGE_ADMIN_OWNERS) or the family's value is
  `{"all": true}`. An id the release file does not list is never sent (tests/test_releases.py keeps every registry id
  in the file).
- `limits` holds only keys a plan sets for the workers; none today, so `{}`.
- `digest(context)` is a short fingerprint of the three, the key of every cache whose answer depends on what the
  principal may use (the Screener's saved-item review), so one plan's answer never serves another.
- `named(error)` adds `details.display_name` (errors.display_name) to a worker's 403 CAPABILITY_REQUIRED, which edge-bff
  otherwise relays unchanged; a message that carries the internal key is worded by edge-bff instead (errors.words;
  re-check R1-34).
"""
import hashlib
import json

from . import releases
from .errors import display_name, words
from .rights import rights_of

EVERYTHING = '*'
KINDS = ('indicator', 'flow_indicator', 'candle_pattern', 'screener_metric')
# CONTRACT.md 8b "Families per worker", changed by the "3b follow-up" (user decision 2026-11-18, O3b-1: "Pokoknya gate-nya
# adalah terminal"): the Terminal's item grants decide the indicator and Flow items of the Backtest and the Screener too,
# so no tab can differ from the Terminal (the backtest.* and screener.* families of those two kinds were removed by
# migration 20261118_001). A Backtest test condition uses the Screener's metrics (screener.metric). The workers name the
# same family in a refusal's details.capability (backtest-worker src/access.ts FAMILY, screener-worker src/run.ts
# CAPABILITY_FAMILY; tests/test_allow.py reads both).
FAMILIES = {
    'backtest': {'indicator': 'terminal.indicator', 'flow_indicator': 'terminal.flow_indicator',
                 'candle_pattern': 'backtest.candle_pattern', 'screener_metric': 'screener.metric'},
    'screener': {'indicator': 'terminal.indicator', 'flow_indicator': 'terminal.flow_indicator',
                 'candle_pattern': 'screener.candle_pattern', 'screener_metric': 'screener.metric'},
}
CAPABILITY_REQUIRED = 'CAPABILITY_REQUIRED'
# the context of a call no principal made (a direct latest_preview call): no right, no item
NOTHING = {'rights': [], 'allow': {kind: [] for kind in KINDS}, 'limits': {}}


def allow_of(principal, worker):
    """{kind: "*" | sorted ids} of a principal for one worker ('backtest' or 'screener')."""
    families = FAMILIES[worker]
    everything = EVERYTHING in principal.capabilities or principal.grants.get(EVERYTHING) is True
    out = {}
    for kind in KINDS:
        family = families[kind]
        value = principal.grants.get(family) if principal.kinds.get(family) == 'items' else None
        if everything or (isinstance(value, dict) and value.get('all') is True):
            out[kind] = EVERYTHING
        else:
            out[kind] = sorted({e['id'] for e in releases.entries(kind) if principal.can(f'{family}:{e["id"]}')})
    return out


def limits_of(principal, worker):
    """The worker limits a plan sets (min(own ceiling, limits) at the worker); no plan key exists yet, so {}."""
    return {}


def context_of(principal, worker):
    """The worker's context {rights, allow, limits} of a principal."""
    return {'rights': rights_of(principal), 'allow': allow_of(principal, worker), 'limits': limits_of(principal, worker)}


def digest(context):
    """A short fingerprint of a context's rights, allow and limits (a cache key part)."""
    raw = json.dumps([context.get('rights'), context.get('allow'), context.get('limits')], sort_keys=True,
                     separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def named(error):
    """A worker error with details.display_name added when it is CAPABILITY_REQUIRED naming a capability. Its message
    stays the worker's (it names the condition and the item) unless it carries the internal key (the capability or its
    family) or is missing: then edge-bff words it (errors.words), so the person never reads an internal key
    (re-check R1-34; edge-bff owns the wording for people, CONTRACT.md section 3). Any other error as it is."""
    if not isinstance(error, dict) or error.get('code') != CAPABILITY_REQUIRED:
        return error
    details = error.get('details') if isinstance(error.get('details'), dict) else {}
    capability = details.get('capability')
    if not isinstance(capability, str) or not capability:
        return error
    details = {**details, 'display_name': display_name(capability)}
    message = error.get('message')
    if isinstance(message, str) and message and capability not in message and capability.partition(':')[0] not in message:
        return {**error, 'details': details}          # the worker's own words (they name the place), with no key
    return {**error, 'message': words(CAPABILITY_REQUIRED, 403, details), 'details': details}
