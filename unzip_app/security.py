"""Security middleware and utilities for ZIP Extractor."""

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from threading import Lock
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import (
    AUTH_ENABLED,
    AUTH_PASSWORD,
    AUTH_USERNAME,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    SECRET_KEY,
)

__all__ = [
    "SecurityHeadersMiddleware",
    "RateLimitMiddleware",
    "BasicAuthMiddleware",
    "generate_csrf_token",
    "validate_csrf_token",
    "csrf_input",
]


# =============================================================================
# CSRF Protection
# =============================================================================

def generate_csrf_token() -> str:
    """Generate a CSRF token with timestamp for validation."""
    timestamp = str(int(time.time()))
    random_part = secrets.token_hex(16)
    message = f"{timestamp}:{random_part}"
    signature = hmac.new(
        SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{message}:{signature}"


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Validate a CSRF token. Returns True if valid."""
    if not token:
        return False
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        timestamp_str, random_part, signature = parts
        timestamp = int(timestamp_str)

        # Check if token is expired
        if time.time() - timestamp > max_age:
            return False

        # Verify signature
        message = f"{timestamp_str}:{random_part}"
        expected_signature = hmac.new(
            SECRET_KEY.encode(), message.encode(), hashlib.sha256
        ).hexdigest()[:16]

        return hmac.compare_digest(signature, expected_signature)
    except (ValueError, TypeError):
        return False


def csrf_input() -> str:
    """Generate a hidden input field with CSRF token for forms."""
    token = generate_csrf_token()
    return f'<input type="hidden" name="csrf_token" value="{token}">'


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, client_id: str) -> tuple[bool, int]:
        """
        Check if request is allowed for client.
        Returns (allowed, retry_after_seconds).
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            # Clean old requests
            self._requests[client_id] = [
                ts for ts in self._requests[client_id] if ts > window_start
            ]

            if len(self._requests[client_id]) >= self.max_requests:
                # Calculate retry-after
                oldest = min(self._requests[client_id])
                retry_after = int(oldest + self.window_seconds - now) + 1
                return False, max(1, retry_after)

            self._requests[client_id].append(now)
            return True, 0

    def cleanup(self) -> None:
        """Remove stale entries to prevent memory growth."""
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            empty_keys = [
                key for key, timestamps in self._requests.items()
                if not timestamps or max(timestamps) < window_start
            ]
            for key in empty_keys:
                del self._requests[key]


# Global rate limiter instance
_rate_limiter = RateLimiter(RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)
_last_cleanup = 0.0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces rate limiting per client IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        global _last_cleanup

        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Periodic cleanup every 5 minutes
        now = time.time()
        if now - _last_cleanup > 300:
            _rate_limiter.cleanup()
            _last_cleanup = now

        # Get client identifier (IP or forwarded IP)
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        allowed, retry_after = _rate_limiter.is_allowed(client_ip)

        if not allowed:
            return Response(
                content="Rate limit exceeded. Please try again later.",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS),
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)
        return response


# =============================================================================
# HTTP Basic Authentication
# =============================================================================

class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces HTTP Basic Authentication."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not AUTH_ENABLED:
            return await call_next(request)

        # Allow favicon without auth
        if request.url.path == "/favicon.ico":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Basic "):
            return self._unauthorized_response()

        try:
            encoded_credentials = auth_header[6:]  # Remove "Basic "
            decoded = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded.split(":", 1)

            if not self._verify_credentials(username, password):
                return self._unauthorized_response()

        except (ValueError, UnicodeDecodeError):
            return self._unauthorized_response()

        return await call_next(request)

    def _verify_credentials(self, username: str, password: str) -> bool:
        """Verify username and password using constant-time comparison."""
        username_valid = hmac.compare_digest(username, AUTH_USERNAME)
        password_valid = hmac.compare_digest(password, AUTH_PASSWORD)
        return username_valid and password_valid

    def _unauthorized_response(self) -> Response:
        """Return 401 response with WWW-Authenticate header."""
        return Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="ZIP Extractor"'},
        )


# =============================================================================
# Security Headers
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS filter in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy - don't leak URLs
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy - restrict resource loading
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # HTMX needs inline
            "style-src 'self' 'unsafe-inline'; "   # Inline styles
            "img-src 'self' data:; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )

        # Permissions policy - disable unnecessary features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        return response
