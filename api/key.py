import json
import time
from http import cookies
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote, unquote

# Inlined rather than imported from a shared helper module: Vercel's Python
# runtime bundles each api/*.py file as an isolated function, and relying
# on it to also pick up a sibling module turned out to crash in production
# (FUNCTION_INVOCATION_FAILED). A few duplicated lines here beat a broken
# deploy -- see api/summarize.py for the matching copy of this logic.
COOKIE_NAME = 'gemini_key'
TOKEN_TTL_SECONDS = 16 * 60 * 60  # key stays saved for 16 hours
MAX_KEY_LEN = 512

# A second, non-secret cookie that just holds the expiry timestamp (epoch
# seconds). It is NOT HttpOnly on purpose: it carries zero information about
# the actual key, so it's safe for page JS to read directly and render a
# "time remaining" countdown without needing a round trip to the server.
EXPIRY_COOKIE_NAME = 'gemini_key_expires'


def read_token_cookie(headers) -> str:
    raw = headers.get('Cookie')
    if not raw:
        return ''
    jar = cookies.SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ''
    morsel = jar.get(COOKIE_NAME)
    if not morsel:
        return ''
    try:
        return unquote(morsel.value)
    except Exception:
        return ''


def build_cookie_header(name: str, value: str = '', clear: bool = False,
                         max_age_seconds: int = None, http_only: bool = True) -> str:
    attrs = [f'{name}={value}', 'Path=/', 'Secure', 'SameSite=Strict']
    if http_only:
        attrs.append('HttpOnly')
    if clear:
        attrs.append('Max-Age=0')
    elif max_age_seconds is not None:
        attrs.append(f'Max-Age={max_age_seconds}')
    return '; '.join(attrs)


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict, set_cookies=None):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for cookie_header in (set_cookies or []):
            self.send_header('Set-Cookie', cookie_header)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Never echoes the key back -- HttpOnly means we can't read it in JS
        # anyway, so the only useful question the client can ask is "is one set?"
        has_key = bool(read_token_cookie(self.headers))
        self._send(200, {'hasKey': has_key})

    def do_POST(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            if content_len <= 0 or content_len > 4096:
                return self._send(400, {'error': 'Invalid payload'})
            body = json.loads(self.rfile.read(content_len).decode('utf-8'))
        except Exception:
            return self._send(400, {'error': 'Malformed JSON body'})

        token = (body.get('token') or '').strip()
        if not token:
            return self._send(400, {'error': 'API key is required'})
        if len(token) > MAX_KEY_LEN:
            return self._send(400, {'error': 'That key looks too long to be valid'})

        expires_at = int(time.time()) + TOKEN_TTL_SECONDS
        self._send(200, {'ok': True, 'expiresAt': expires_at}, set_cookies=[
            build_cookie_header(COOKIE_NAME, quote(token, safe=''), max_age_seconds=TOKEN_TTL_SECONDS, http_only=True),
            build_cookie_header(EXPIRY_COOKIE_NAME, str(expires_at), max_age_seconds=TOKEN_TTL_SECONDS, http_only=False),
        ])

    def do_DELETE(self):
        self._send(200, {'ok': True}, set_cookies=[
            build_cookie_header(COOKIE_NAME, clear=True, http_only=True),
            build_cookie_header(EXPIRY_COOKIE_NAME, clear=True, http_only=False),
        ])
