"""WebUI sign-in: a single shared password, set on first visit.

The password hash and the active session tokens live in one JSON file so a
sign-in survives both closing the browser (persistent cookie) and restarting
the WebUI server (server-side token list on disk).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Final

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from codex_image.atomic_files import atomic_write_text

SESSION_COOKIE_NAME: Final = "conjure_session"
# Browsers cap cookie lifetimes at 400 days; the cookie is refreshed on every
# page load, so an active user effectively never gets signed out.
SESSION_COOKIE_MAX_AGE_SECONDS: Final = 400 * 24 * 60 * 60
LOGIN_REQUIRED_HEADER: Final = "X-Conjure-Login"
MAX_SESSIONS: Final = 200
MAX_PASSWORD_CHARS: Final = 1024
PBKDF2_ITERATIONS: Final = 310_000
FAILED_ATTEMPT_WINDOW_SECONDS: Final = 5 * 60
MAX_FAILED_ATTEMPTS: Final = 10

PUBLIC_PATHS: Final = frozenset(
    {
        "/login",
        "/api/login/status",
        "/api/login/setup",
        "/api/login",
        "/api/logout",
        "/manifest.webmanifest",
        "/service-worker.js",
    }
)
PUBLIC_PREFIXES: Final = ("/static/",)
LOGIN_PAGE_PATHS: Final = frozenset({"/", "/history"})


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cache_mtime: float | None = None

    def _read(self) -> dict[str, Any]:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self._cache, self._cache_mtime = {}, None
            return {}
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        self._cache, self._cache_mtime = payload, mtime
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        atomic_write_text(self.path, json.dumps(payload, indent=2), mode=0o600)
        self._cache = payload
        try:
            self._cache_mtime = self.path.stat().st_mtime
        except OSError:
            self._cache_mtime = None

    def is_configured(self) -> bool:
        with self._lock:
            payload = self._read()
            return bool(payload.get("password_hash")) and bool(payload.get("password_salt"))

    def set_initial_password(self, password: str) -> str | None:
        """Store the first password and return a new session token.

        Returns None when a password already exists, so a second visitor
        cannot replace it.
        """
        with self._lock:
            payload = self._read()
            if payload.get("password_hash"):
                return None
            salt = secrets.token_bytes(16)
            token = secrets.token_urlsafe(32)
            self._write(
                {
                    "version": 1,
                    "password_salt": salt.hex(),
                    "password_hash": _hash_password(password, salt),
                    "password_iterations": PBKDF2_ITERATIONS,
                    "sessions": [{"token_sha256": _token_digest(token), "created_at": int(time.time())}],
                }
            )
            return token

    def verify_password(self, password: str) -> bool:
        with self._lock:
            payload = dict(self._read())
        stored = str(payload.get("password_hash") or "")
        salt_hex = str(payload.get("password_salt") or "")
        if not stored or not salt_hex:
            return False
        try:
            salt = bytes.fromhex(salt_hex)
        except ValueError:
            return False
        iterations = int(payload.get("password_iterations") or PBKDF2_ITERATIONS)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()
        return hmac.compare_digest(candidate, stored)

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            payload = dict(self._read())
            sessions = [item for item in payload.get("sessions") or [] if isinstance(item, dict)]
            sessions.append({"token_sha256": _token_digest(token), "created_at": int(time.time())})
            payload["sessions"] = sessions[-MAX_SESSIONS:]
            self._write(payload)
        return token

    def session_is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        digest = _token_digest(token)
        with self._lock:
            sessions = self._read().get("sessions") or []
        return any(
            isinstance(item, dict) and hmac.compare_digest(str(item.get("token_sha256") or ""), digest)
            for item in sessions
        )

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        digest = _token_digest(token)
        with self._lock:
            payload = dict(self._read())
            sessions = [item for item in payload.get("sessions") or [] if isinstance(item, dict)]
            remaining = [item for item in sessions if item.get("token_sha256") != digest]
            if len(remaining) != len(sessions):
                payload["sessions"] = remaining
                self._write(payload)


class FailedLoginLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        return [stamp for stamp in self._failures.get(key, []) if now - stamp < FAILED_ATTEMPT_WINDOW_SECONDS]

    def blocked(self, key: str) -> bool:
        with self._lock:
            recent = self._recent(key, time.monotonic())
            self._failures[key] = recent
            return len(recent) >= MAX_FAILED_ATTEMPTS

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            recent = self._recent(key, now)
            recent.append(now)
            self._failures[key] = recent

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def _client_key(scope: Scope) -> str:
    client = scope.get("client")
    return str(client[0]) if client else ""


def _client_is_local(scope: Scope) -> bool:
    from .security import _client_is_loopback

    return _client_is_loopback(scope)


def _session_cookie_kwargs(request: Request) -> dict[str, Any]:
    return {
        "key": SESSION_COOKIE_NAME,
        "max_age": SESSION_COOKIE_MAX_AGE_SECONDS,
        "expires": SESSION_COOKIE_MAX_AGE_SECONDS,
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": request.url.scheme == "https",
    }


def _wants_html(scope: Scope) -> bool:
    if str(scope.get("method") or "").upper() not in {"GET", "HEAD"}:
        return False
    path = str(scope.get("path") or "")
    if path in LOGIN_PAGE_PATHS:
        return True
    accept = Headers(scope=scope).get("accept", "")
    return not path.startswith("/api/") and "text/html" in accept


class LoginGateMiddleware:
    def __init__(self, app: ASGIApp, *, store: LoginStore, login_page: Path) -> None:
        self.app = app
        self.store = store
        self.login_page = Path(login_page)

    def _login_page_response(self) -> Response:
        headers = {"Cache-Control": "no-store", LOGIN_REQUIRED_HEADER: "required"}
        if self.login_page.exists():
            return FileResponse(self.login_page, media_type="text/html", headers=headers)
        return HTMLResponse("<!doctype html><title>Sign in</title>", headers=headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return
        cookies = Request(scope).cookies if scope["type"] == "http" else _websocket_cookies(scope)
        token = cookies.get(SESSION_COOKIE_NAME)
        if self.store.session_is_valid(token):
            if scope["type"] == "http" and _wants_html(scope) and path in LOGIN_PAGE_PATHS:
                await self.app(scope, receive, _refresh_cookie_sender(scope, send, token or ""))
                return
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if _wants_html(scope):
            response = self._login_page_response()
        else:
            response = JSONResponse(
                {"detail": "login_required"},
                status_code=401,
                headers={"Cache-Control": "no-store", LOGIN_REQUIRED_HEADER: "required"},
            )
        await response(scope, receive, send)


def _websocket_cookies(scope: Scope) -> dict[str, str]:
    from http.cookies import SimpleCookie

    raw = Headers(scope=scope).get("cookie", "")
    parsed = SimpleCookie()
    try:
        parsed.load(raw)
    except Exception:
        return {}
    return {key: morsel.value for key, morsel in parsed.items()}


def _refresh_cookie_sender(scope: Scope, send: Send, token: str) -> Send:
    """Re-issue the session cookie on page loads so its 400-day clock slides."""
    request = Request(scope)

    async def sender(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            carrier = Response()
            carrier.set_cookie(value=token, **_session_cookie_kwargs(request))
            headers = list(message.get("headers") or [])
            headers.extend(
                (name, value) for name, value in carrier.raw_headers if name.lower() == b"set-cookie"
            )
            message = {**message, "headers": headers}
        await send(message)

    return sender


def register_login_routes(app: Any, store: LoginStore, login_page: Path) -> None:
    from fastapi import Body

    limiter = FailedLoginLimiter()

    def status_payload(request: Request) -> dict[str, Any]:
        configured = store.is_configured()
        return {
            "configured": configured,
            "authenticated": configured and store.session_is_valid(request.cookies.get(SESSION_COOKIE_NAME)),
            "setup_allowed": not configured and _client_is_local(request.scope),
        }

    def signed_in(request: Request, token: str) -> JSONResponse:
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.set_cookie(value=token, **_session_cookie_kwargs(request))
        return response

    def read_password(payload: Any) -> str:
        password = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(password, str) or not password:
            raise _bad_request("password_required")
        if len(password) > MAX_PASSWORD_CHARS:
            raise _bad_request("password_too_long")
        return password

    @app.get("/login", response_model=None)
    def login_page_route(request: Request) -> Response:
        if store.is_configured() and store.session_is_valid(request.cookies.get(SESSION_COOKIE_NAME)):
            return Response(status_code=303, headers={"Location": "/"})
        if login_page.exists():
            return FileResponse(login_page, media_type="text/html", headers={"Cache-Control": "no-store"})
        return HTMLResponse("<!doctype html><title>Sign in</title>", headers={"Cache-Control": "no-store"})

    @app.get("/api/login/status")
    def login_status(request: Request) -> JSONResponse:
        return JSONResponse(status_payload(request), headers={"Cache-Control": "no-store"})

    @app.post("/api/login/setup", response_model=None)
    def login_setup(request: Request, payload: Any = Body(...)) -> Response:
        if store.is_configured():
            return JSONResponse({"detail": "already_configured"}, status_code=409)
        if not _client_is_local(request.scope):
            # The first visitor sets the password, so only this device may do it.
            return JSONResponse({"detail": "setup_local_only"}, status_code=403)
        password = read_password(payload)
        token = store.set_initial_password(password)
        if token is None:
            return JSONResponse({"detail": "already_configured"}, status_code=409)
        return signed_in(request, token)

    @app.post("/api/login", response_model=None)
    def login(request: Request, payload: Any = Body(...)) -> Response:
        if not store.is_configured():
            return JSONResponse({"detail": "setup_required"}, status_code=409)
        key = _client_key(request.scope)
        if limiter.blocked(key):
            return JSONResponse({"detail": "too_many_attempts"}, status_code=429)
        password = read_password(payload)
        if not store.verify_password(password):
            limiter.record_failure(key)
            return JSONResponse({"detail": "wrong_password"}, status_code=401)
        limiter.reset(key)
        return signed_in(request, store.create_session())

    @app.post("/api/logout", response_model=None)
    def logout(request: Request) -> Response:
        store.revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return response


def _bad_request(code: str) -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=400, detail=code)
