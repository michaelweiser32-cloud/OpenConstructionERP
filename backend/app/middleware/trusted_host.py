"""Host-header allowlist middleware.

A small variant of Starlette's ``TrustedHostMiddleware`` that always lets
``/api/health`` through: platform health checkers (Render, Docker
HEALTHCHECK, Kubernetes probes) hit the container by internal IP or
``localhost``, and a strict allowlist would otherwise mark a healthy
service as down.

Entries may be exact host names (``erp.example.com``) or a leading
wildcard (``*.onrender.com``). Ports are ignored.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_EXEMPT_PATHS = ("/api/health",)


def host_is_allowed(host: str, allowed_hosts: Sequence[str]) -> bool:
    """Return True when ``host`` (without port) matches the allowlist."""
    host = host.split(":", 1)[0].strip().lower().rstrip(".")
    if not host:
        return False
    for pattern in allowed_hosts:
        pattern = pattern.strip().lower()
        if pattern == "*":
            return True
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".onrender.com"
            if host.endswith(suffix) and len(host) > len(suffix):
                return True
        elif host == pattern:
            return True
    return False


class TrustedHostMiddleware:
    """Reject HTTP requests whose ``Host`` header is not allowlisted."""

    def __init__(self, app: ASGIApp, allowed_hosts: Sequence[str]) -> None:
        self.app = app
        self.allowed_hosts = list(allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        if path.rstrip("/") in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        headers: Any = Headers(scope=scope)
        if host_is_allowed(headers.get("host", ""), self.allowed_hosts):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse("Invalid host header", status_code=400)
        await response(scope, receive, send)
