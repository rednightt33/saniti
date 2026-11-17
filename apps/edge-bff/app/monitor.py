"""EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b, decisions D1 and D5): the Monitor (AI) model rules.

The Monitor is admin only for now (D1): the paid plan holds monitor.example, not monitor.view, monitor.chat or
monitor.model. The routes (main.py) need monitor.view to read and monitor.chat to write; on top of that a run's model
must be one the principal holds:

- the model a run uses is the request's, else Orc's server default (`server_default.model` of GET /v1/models, the
  model Orc runs when a message names none);
- it is refused unless `p.can('monitor.model:<model>')`;
- the manual troubleshooting model (EXEC-MANUAL) is refused without `admin.manual` (only '*' holds it);
- the worker checks the same again when it dispatches a queued run (worker.py), so a plan lowered meanwhile is refused
  before any Orc call.

Rules (AGENTS.md "Gates and evidence"): (a) the page reads the models it may choose from GET /api/v1/models, which lists
only those (`visible`); (b) to pass, choose a listed model or upgrade the plan; (c) right: an admin sends
deepseek/deepseek-v4.1-flash; wrong: an account without monitor.model sends it; (d) the refusal is 403
CAPABILITY_REQUIRED naming the capability (`monitor.model:<id>` or `admin.manual`).

Models and providers do not change here (AGENTS.md "Model and provider"): this module only reads Orc's list.
"""
import asyncio
import time

from .client import OrcError

MODELS_CACHE_SECONDS = 600  # Orc reads OpenRouter's prices every hour; the page sees them within ten minutes
MANUAL_MODEL = 'saniti/claude-manual'   # market-ai-orc app/model_choices.py MANUAL_OPTION
MANUAL_CAPABILITY = 'admin.manual'
MODEL_FAMILY = 'monitor.model'


class ModelCatalog:
    """Orc's model list, shared by every principal (the list is the same for all; each answer is filtered after it)."""

    def __init__(self, orc, clock=time.monotonic):
        self.orc, self.clock = orc, clock
        self.at, self.data = None, None

    async def read(self, owner):
        """The cached list, read again from Orc after MODELS_CACHE_SECONDS; when Orc cannot answer the last list is
        kept (none yet: OrcError MODELS_UNAVAILABLE)."""
        now = self.clock()
        if self.data is None or now - self.at >= MODELS_CACHE_SECONDS:
            try:
                data = await asyncio.to_thread(self.orc.models, owner)
            except OrcError:
                data = None
            if data:
                self.at, self.data = now, data
            elif self.data is None:
                raise OrcError('MODELS_UNAVAILABLE', 503)
        return self.data


def holds_everything(p):
    return '*' in p.capabilities


def model_allowed(p, model):
    """Whether the principal may run this model (the manual one also needs admin.manual)."""
    if model == MANUAL_MODEL and not p.can(MANUAL_CAPABILITY):
        return False
    return p.can(f'{MODEL_FAMILY}:{model}')


def model_refusal(p, model):
    """The refusal for a model the principal may not run, else None."""
    if model == MANUAL_MODEL and not p.can(MANUAL_CAPABILITY):
        return p.refusal(MANUAL_CAPABILITY)
    if not p.can(f'{MODEL_FAMILY}:{model}'):
        return p.refusal(f'{MODEL_FAMILY}:{model}')
    return None


async def run_model(p, model, catalog):
    """The model a run of this principal uses: the request's, else the server default. A principal holding every
    capability needs no resolution (every model is allowed; no Orc read is added to its submit)."""
    if model or holds_everything(p):
        return model
    data = await catalog.read(p.owner_key)
    found = ((data or {}).get('server_default') or {}).get('model')
    if not isinstance(found, str) or not found:
        raise OrcError('MODELS_UNAVAILABLE', 503)
    return found


async def run_refusal(p, model, catalog):
    """None when the principal may run this (resolved) model, else its refusal."""
    resolved = await run_model(p, model, catalog)
    return None if resolved is None else model_refusal(p, resolved)


def visible(p, data):
    """Orc's model list as this principal may use it: only the models it holds, and each default only when held. A
    principal holding every capability gets the list unchanged."""
    if holds_everything(p) or not isinstance(data, dict):
        return data
    out = dict(data)
    if isinstance(data.get('models'), list):
        out['models'] = [m for m in data['models']
                         if isinstance(m, dict) and isinstance(m.get('model'), str) and model_allowed(p, m['model'])]
    for key in ('edge_default', 'server_default'):
        value = data.get(key)
        if isinstance(value, dict) and not (isinstance(value.get('model'), str) and model_allowed(p, value['model'])):
            out[key] = None
    return out
