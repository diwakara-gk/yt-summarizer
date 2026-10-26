"""Shared cookie helpers for the Gemini API key cookie store.

This file intentionally has NO `handler`/`app` export. Vercel's Python
runtime only turns files in api/ into routes when they expose one of
those; a plain helper module like this just gets imported, same as any
other local module, and keeps the cookie logic in one place (DRY)
instead of copy-pasted into every function that needs it.
"""
from http import cookies
from urllib.parse import quote, unquote

COOKIE_NAME = 'gemini_key'
TOKEN_TTL_SECONDS = 16 * 60 * 60  # key stays saved for 16 hours


def read_token_cookie(headers) -> str:
    """Pull the Gemini key out of the request's Cookie header, if present."""
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
    """Build a Set-Cookie value that is HttpOnly + Secure + SameSite=Strict.

    Because it's HttpOnly, neither page JS nor a content-script-based
    browser extension can ever read it via document.cookie -- only the
    server sees the value. `max_age_seconds` controls how long it survives
    (defaults to TOKEN_TTL_SECONDS); pass `clear=True` to delete it now.
    """
    value = quote(token, safe='') if token else ''
    attrs = [f'{COOKIE_NAME}={value}', 'Path=/', 'HttpOnly', 'Secure', 'SameSite=Strict']
    if clear:
        attrs.append('Max-Age=0')
    elif max_age_seconds is not None:
        attrs.append(f'Max-Age={max_age_seconds}')
    return '; '.join(attrs)
