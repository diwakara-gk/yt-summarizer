import json
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


def build_set_cookie_header(token: str = '', clear: bool = False, max_age_seconds: int = TOKEN_TTL_SECONDS) -> str:
    value = quote(token, safe='') if token else ''
    attrs = [f'{COOKIE_NAME}={value}', 'Path=/', 'HttpOnly', 'Secure', 'SameSite=Strict']
    if clear:
        attrs.append('Max-Age=0')
    elif max_age_seconds is not None:
        attrs.append(f'Max-Age={max_age_seconds}')
    return '; '.join(attrs)


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict, set_cookie: str = None):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if set_cookie:
            self.send_header('Set-Cookie', set_cookie)
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

        self._send(200, {'ok': True}, set_cookie=build_set_cookie_header(token))

    def do_DELETE(self):
        self._send(200, {'ok': True}, set_cookie=build_set_cookie_header(clear=True))
