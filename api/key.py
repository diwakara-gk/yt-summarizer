import json
from http.server import BaseHTTPRequestHandler

from _cookie_utils import build_set_cookie_header, read_token_cookie

MAX_KEY_LEN = 512


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
