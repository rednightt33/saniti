"""EXEC-BACKTEST-REVAMP P5 (user 2026-11-15: "mekanisme hak akses disiapkan sekarang (edge-bff menentukan hak sesi,
mengirimnya ke worker, worker menolak D tanpa hak, katalog menandai D), dengan owner = admin sampai EDGE-MULTIUSER";
K8 b: the same table for the Screener).

The rights of an owner, decided here from the session's owner and the configuration only (EDGE_ADMIN_OWNERS, default
EDGE_OWNER), never from a request body: edge-bff refuses a body that carries `context` (422 UNKNOWN_FIELD) and always
sends the workers its own `context.rights` (also []), computed when the call is made (a queued job reads its owner's
rights when it is dispatched, so an owner whose right was taken away meanwhile is refused CONDITION_RESTRICTED).
"""

POINT_IN_TIME = 'flow_point_in_time'      # the point-in-time Flow indicators (Backtest pit/; the Screener's own versions)
ADMIN_RIGHTS = (POINT_IN_TIME,)


def rights_of(settings, owner):
    """The rights of an owner: every admin right for an owner listed in EDGE_ADMIN_OWNERS, none otherwise."""
    return list(ADMIN_RIGHTS) if owner in settings.admin_owners else []


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
