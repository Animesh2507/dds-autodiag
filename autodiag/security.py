"""HTTP hardening for the dashboard.

The dashboard runs local ROS 2 / Docker CLI probes, so a malicious web page in the
operator's browser must not be able to drive it:

* Host header allow-list blocks DNS-rebinding attacks against a loopback server.
* Origin check on state-changing requests blocks cross-site POSTs.
* Optional shared token (AUTODIAG_UI_TOKEN) is required when the server is reachable
  from other machines.
* Strict security headers; the UI ships no inline script so CSP can forbid it.
"""
from __future__ import annotations
import hmac
from urllib.parse import urlsplit
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from .config import LOOPBACK_HOSTS, settings

COOKIE = 'autodiag_token'
# The collector endpoint has its own token; health probes must work for supervisors.
PUBLIC_PATHS = ('/api/agent/snapshot', '/api/healthz', '/login', '/static/')
SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
# The previous dashboard is a single file with inline script and handlers.
LEGACY_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
              "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
# FastAPI's Swagger UI loads its assets from a CDN and uses inline script.
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'")


def _hostname(value: str) -> str:
    try:
        return (urlsplit('//' + value).hostname or '').lower()
    except ValueError:
        return ''


def host_allowed(host_header: str) -> bool:
    host = _hostname(host_header)
    if not host:
        return False
    allowed = settings().allowed_hosts
    return host in LOOPBACK_HOSTS or host == 'testserver' or '*' in allowed or host in allowed


def token_valid(request: Request) -> bool:
    expected = settings().ui_token
    if not expected:
        return True
    supplied = request.headers.get('authorization', '')
    supplied = supplied[7:] if supplied.lower().startswith('bearer ') else request.cookies.get(COOKIE, '')
    return bool(supplied) and hmac.compare_digest(expected.encode(), supplied.encode())


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({'detail': detail}, status_code=status)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not host_allowed(request.headers.get('host', '')):
            return _error(400, 'Host header not allowed. Add it to AUTODIAG_ALLOWED_HOSTS if intended.')
        if request.method not in SAFE_METHODS:
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc.lower() != request.headers.get('host', '').lower():
                return _error(403, 'Cross-origin request rejected.')
        path = request.url.path
        if not path.startswith(PUBLIC_PATHS) and not token_valid(request):
            if path.startswith('/api/'):
                return _error(401, 'Dashboard token required. Open /login or send "Authorization: Bearer <token>".')
            return Response(status_code=303, headers={'Location': '/login'})
        response = await call_next(request)
        if path.startswith('/api/docs') or path == '/openapi.json':
            csp = DOCS_CSP
        elif path == '/legacy':
            csp = LEGACY_CSP
        else:
            csp = CSP
        response.headers.setdefault('Content-Security-Policy', csp)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault('Cache-Control', 'no-store')
        return response
