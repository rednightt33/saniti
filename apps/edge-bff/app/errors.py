"""EDGE multi-user Phase 0 (EXEC-MU-ACCOUNTS; CONTRACT.md section 3, ERRORS M471): one error shape for edge-bff's own
refusals, FastAPI's included: {"error": {"code", "message", "details"}}. The front-end decides by the code, never by
the status alone: UNAUTHENTICATED (401) goes to sign-in, CSRF_INVALID (403) re-reads the session once and retries once,
CAPABILITY_REQUIRED (403) keeps the session and shows that the feature is not open to this account.

Messages are plain Indonesian for the person using EDGE, without internal names (AGENTS.md "Gates and evidence" (d):
each names what is wrong and how to go on).
"""
from fastapi.responses import JSONResponse

MESSAGES = {
    'UNAUTHENTICATED': 'Sesi Anda sudah berakhir atau belum masuk. Silakan masuk lagi.',
    'CSRF_INVALID': 'Permintaan ini tidak bisa diverifikasi. Muat ulang halaman, lalu coba lagi.',
    'CAPABILITY_REQUIRED': 'Fitur ini tidak tersedia untuk akun Anda.',
    'SIGN_IN_RATE_LIMIT': 'Terlalu banyak percobaan masuk yang gagal. Tunggu sebentar, lalu coba lagi.',
    'INVALID_INPUT': 'Isi permintaan tidak sesuai. Periksa isian Anda, lalu coba lagi.',
    'NOT_FOUND': 'Halaman atau data yang diminta tidak ditemukan.',
    'METHOD_NOT_ALLOWED': 'Cara permintaan ini tidak didukung.',
    'REQUEST_REFUSED': 'Permintaan ini tidak dapat diproses.',
}

# FastAPI's and Starlette's own refusals by status (a route raises HTTPException with one of these codes as its detail)
STATUS_CODES = {400: 'INVALID_INPUT', 401: 'UNAUTHENTICATED', 403: 'CSRF_INVALID', 404: 'NOT_FOUND',
                405: 'METHOD_NOT_ALLOWED', 422: 'INVALID_INPUT'}

# The capabilities a Phase 0 route may require, with the name the person sees (CONTRACT.md section 3 details)
CAPABILITY_NAMES = {'admin.manual': 'Agen manual (pemecahan masalah)'}


class Refusal(Exception):
    """A refusal in the contract's shape, raised from a dependency or a handler."""

    def __init__(self, status, code, details=None, headers=None):
        self.status, self.code, self.details, self.headers = status, code, details or {}, headers
        super().__init__(code)


def refusal(status, code, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={'error': {
        'code': code, 'message': MESSAGES.get(code, MESSAGES['REQUEST_REFUSED']), 'details': details or {}}})


def capability_required(capability):
    return Refusal(403, 'CAPABILITY_REQUIRED', {'capability': capability,
                                                'display_name': CAPABILITY_NAMES.get(capability, capability)})


def http_refusal(exc):
    """A FastAPI/Starlette HTTPException: its detail when it is one of our codes, else the code of its status."""
    code = exc.detail if isinstance(exc.detail, str) and exc.detail in MESSAGES else \
        STATUS_CODES.get(exc.status_code, 'REQUEST_REFUSED')
    return refusal(exc.status_code, code, headers=getattr(exc, 'headers', None))


def validation_refusal(exc):
    """A body, query or path value FastAPI could not accept: 422 INVALID_INPUT naming the fields (their API names, as
    the page sends them), never the values."""
    fields = []
    for item in exc.errors():
        loc = [str(p) for p in item.get('loc', ()) if p not in ('body', 'query', 'path', 'header', 'cookie')]
        name = '.'.join(loc)
        if name and name not in fields:
            fields.append(name)
    return refusal(422, 'INVALID_INPUT', {'fields': fields[:20]} if fields else {})
