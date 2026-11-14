"""Optional password for the whole app (PLAN.md Phase 8, decision 0026).

Off by default: the app listens on localhost only and needs no sign-in. With
a password set, every API route (and the API docs) needs a session cookie,
except signing in, /health and /api/health. The console and portal pages are
static files that hold no data, so they load and show the sign-in screen.

- The password comes from `APP_PASSWORD` (for Docker) or from the scrypt hash
  `python -m app.cli set-password` writes to DATA_DIR/auth.json. The env var
  wins when both are set. The password itself is never stored by the app.
- A session is an HMAC-signed cookie (HttpOnly, SameSite=Strict) holding an
  expiry and a fingerprint of the password, so changing or clearing the
  password signs everyone out. The key lives in DATA_DIR/secret_key.
- Failed sign-ins are limited per client address.

Only the standard library: hashlib.scrypt, hmac, secrets.
"""

import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings

COOKIE_NAME = "rag_session"
OPEN_PATHS = {"/health", "/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
# scrypt cost: about 50 ms and 16 MB per check on a laptop (OWASP's minimum is N=2**17, r=8).
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_MAX_FAILURES = 5
_FAILURE_WINDOW = 300.0  # seconds


class AuthError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- Passwords -------------------------------------------------------------------


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise AuthError("the password can't be empty")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, _unb64(digest))


def _auth_file(settings: Settings) -> Path:
    return settings.data_dir / "auth.json"


def stored_hash(settings: Settings) -> str | None:
    try:
        return json.loads(_auth_file(settings).read_text(encoding="utf-8")).get("password_hash")
    except (OSError, ValueError):
        return None


def set_password(settings: Settings, password: str) -> None:
    """Stores the scrypt hash (the CLI's `set-password`)."""
    if len(password) < 8:
        raise AuthError("use at least 8 characters")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = _auth_file(settings)
    path.write_text(json.dumps({"password_hash": hash_password(password)}), encoding="utf-8")
    _restrict(path)


def clear_password(settings: Settings) -> bool:
    """Removes the stored hash; returns False when there was none."""
    try:
        _auth_file(settings).unlink()
        return True
    except FileNotFoundError:
        return False


def enabled(settings: Settings) -> bool:
    return bool(settings.app_password) or stored_hash(settings) is not None


def check_password(settings: Settings, password: str) -> bool:
    if settings.app_password:
        return hmac.compare_digest(password.encode(), settings.app_password.encode())
    stored = stored_hash(settings)
    return stored is not None and verify_password(password, stored)


def _fingerprint(settings: Settings) -> str:
    """Changes whenever the password does, which ends every session."""
    source = settings.app_password or stored_hash(settings) or ""
    return hashlib.sha256(source.encode()).hexdigest()[:16]


# --- Sessions --------------------------------------------------------------------


def _restrict(path: Path) -> None:
    with contextlib.suppress(OSError):  # Windows keeps its own ACLs
        os.chmod(path, 0o600)


def _secret(settings: Settings) -> bytes:
    path = settings.data_dir / "secret_key"
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        path.write_text(key.hex(), encoding="utf-8")
        _restrict(path)
        return key


def _sign(settings: Settings, body: str) -> str:
    return _b64(hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest())


def new_session(settings: Settings, *, now: float | None = None) -> str:
    now = time.time() if now is None else now
    claims = {"exp": int(now + settings.auth_session_days * 86400), "pw": _fingerprint(settings)}
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    return f"{body}.{_sign(settings, body)}"


def valid_session(settings: Settings, token: str | None, *, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(settings, body)):
        return False
    try:
        claims = json.loads(_unb64(body))
    except ValueError:
        return False
    now = time.time() if now is None else now
    return claims.get("exp", 0) > now and claims.get("pw") == _fingerprint(settings)


def session_cookie(token: str, settings: Settings, *, secure: bool) -> str:
    max_age = settings.auth_session_days * 86400
    return f"{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict" + (
        "; Secure" if secure else ""
    )


def cleared_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


def cookie_from(headers: list[tuple[bytes, bytes]]) -> str | None:
    for name, value in headers:
        if name == b"cookie":
            for part in value.decode("latin-1").split(";"):
                key, _, val = part.strip().partition("=")
                if key == COOKIE_NAME:
                    return val
    return None


# --- Failed sign-ins -------------------------------------------------------------


@dataclass
class LoginLimiter:
    """At most 5 failed sign-ins per client address in 5 minutes."""

    max_failures: int = _MAX_FAILURES
    window: float = _FAILURE_WINDOW

    def __post_init__(self):
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, client: str, now: float) -> deque[float]:
        times = self._failures.setdefault(client, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        return times

    def retry_after(self, client: str, *, now: float | None = None) -> int:
        """Seconds until this client may try again; 0 = it may now."""
        now = time.monotonic() if now is None else now
        with self._lock:
            times = self._recent(client, now)
            if len(times) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - times[0])) + 1)

    def failed(self, client: str, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._recent(client, now).append(now)

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)


# --- Middleware ------------------------------------------------------------------


def needs_session(path: str) -> bool:
    """The API and its docs. Static pages hold no data and may load."""
    if path in OPEN_PATHS:
        return False
    return (
        path == "/api" or path.startswith("/api/") or path in {"/docs", "/redoc", "/openapi.json"}
    )


class AuthMiddleware:
    """Pure ASGI (streamed SSE answers aren't buffered). Reads the settings from
    the app's runtime on every request, so setting or clearing the password
    takes effect without a restart."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not needs_session(scope["path"]):
            await self.app(scope, receive, send)
            return
        settings = scope["app"].state.runtime.settings
        if not enabled(settings) or valid_session(settings, cookie_from(scope.get("headers", []))):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "sign in first"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
