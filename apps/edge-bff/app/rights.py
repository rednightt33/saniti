"""EXEC-BACKTEST-REVAMP P5 (user 2026-11-15: "mekanisme hak akses disiapkan sekarang (edge-bff menentukan hak sesi,
mengirimnya ke worker, worker menolak D tanpa hak, katalog menandai D), dengan owner = admin sampai EDGE-MULTIUSER";
K8 b: the same table for the Screener).

The rights of an owner, decided here from the session's owner and the configuration only (EDGE_ADMIN_OWNERS, default
EDGE_OWNER), never from a request body: edge-bff refuses a body that carries `context` (422 UNKNOWN_FIELD) and always
sends the workers its own `context.rights` (also []), computed when the call is made (a queued job reads its owner's
rights when it is dispatched, so an owner whose right was taken away meanwhile is refused CONDITION_RESTRICTED).

EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 2): the rights come from the principal's capabilities (app/principal.py):
the right flow_point_in_time is the capability backtest.flow_point_in_time. With EDGE_MULTIUSER off the principal holds
every capability exactly when EDGE_ADMIN_OWNERS lists its owner, so the rights are the ones decided here before.
"""

POINT_IN_TIME = 'flow_point_in_time'      # the point-in-time Flow indicators (Backtest pit/; the Screener's own versions)
ADMIN_RIGHTS = (POINT_IN_TIME,)
# the wire right (context.rights, read by the workers) -> the capability the principal must hold for it
CAPABILITY_OF = {POINT_IN_TIME: 'backtest.flow_point_in_time'}


def rights_of(principal):
    """The wire rights of a principal: each right whose capability it holds (none for a principal without them)."""
    return [right for right in ADMIN_RIGHTS if principal.can(CAPABILITY_OF[right])]


def refuse_context(body):
    """A body from the page never carries the context (the rights): it is edge-bff's to set."""
    from .backtest import BacktestError    # one error shape with the Backtest routes
    if isinstance(body, dict) and 'context' in body:
        raise BacktestError(422, {'code': 'UNKNOWN_FIELD', 'field': 'context',
                                  'message': 'context is set by EDGE; remove it from the request.'})


def catalog_for(catalog, rights):
    """The worker's catalog as a session sees it: an entry marked access 'admin' only with its right."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get('flow_indicators'), list):
        return catalog
    keep = [x for x in catalog['flow_indicators'] if not (isinstance(x, dict) and x.get('access') == 'admin' and POINT_IN_TIME not in rights)]
    return {**catalog, 'flow_indicators': keep}
