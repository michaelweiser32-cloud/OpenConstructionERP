"""MCP tool execution: RBAC, confirm-gating, rate limiting and audit.

Transport-independent.  The MCP server (``server.py``) and the tests call
``McpToolService`` directly; nothing in here knows about HTTP.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit_log
from app.core.rate_limiter import RateLimiter
from app.modules.mcp_server.auth import McpPrincipal
from app.modules.mcp_server.registry import CONFIRM_FIELD, McpToolSpec, get_tool_specs

logger = logging.getLogger(__name__)

AUDIT_ACTION = "mcp_tool_call"
AUDIT_ENTITY = "mcp_tool"

STATUS_OK = "ok"
STATUS_PROPOSAL = "proposal"
STATUS_DENIED = "denied"
STATUS_UNKNOWN = "unknown_tool"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_ERROR = "error"

# Tool calls per API key per minute.
mcp_call_limiter = RateLimiter(max_requests=120, window_seconds=60)

_MAX_AUDIT_STRING = 200
_MAX_AUDIT_ITEMS = 20


@dataclass(frozen=True)
class McpToolResult:
    """Outcome of one tool call."""

    status: str
    summary: str
    data: dict[str, Any]

    @property
    def is_error(self) -> bool:
        return self.status not in (STATUS_OK, STATUS_PROPOSAL)

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "summary": self.summary, "data": self.data}


def _audit_value(value: Any) -> Any:
    """Shrink an argument value to something safe and small to store."""
    if isinstance(value, str):
        return value if len(value) <= _MAX_AUDIT_STRING else value[:_MAX_AUDIT_STRING] + "..."
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_audit_value(v) for v in list(value)[:_MAX_AUDIT_ITEMS]]
    return f"<{type(value).__name__}>"


def _audit_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {str(k)[:64]: _audit_value(v) for k, v in list(arguments.items())[:_MAX_AUDIT_ITEMS]}


def _entity_id(arguments: dict[str, Any]) -> str | None:
    project_id = arguments.get("project_id")
    if isinstance(project_id, str) and 0 < len(project_id) <= 36:
        return project_id
    return None


class McpToolService:
    """Runs MCP tool calls for an authenticated principal."""

    def __init__(
        self,
        session_factory: Callable[[], Any] | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        if session_factory is None:
            from app.database import async_session_factory

            session_factory = async_session_factory
        self._session_factory = session_factory
        self._limiter = limiter or mcp_call_limiter

    async def list_tools(self, principal: McpPrincipal) -> list[McpToolSpec]:
        """Tools the principal is allowed to call."""
        specs = await get_tool_specs()
        return [spec for spec in specs.values() if principal.can(spec.permission)]

    async def call_tool(
        self,
        principal: McpPrincipal,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        via: str = "tool",
    ) -> McpToolResult:
        """Execute one tool call and audit it.

        Order of checks: rate limit -> tool exists -> RBAC -> confirm gate.
        Every outcome, including refusals, is written to the audit log (rate
        limited calls are only logged).  For a confirmed write the audit entry
        is committed in the same transaction as the change, so a write can
        never go unaudited.
        """
        started = time.monotonic()
        args = dict(arguments or {})
        confirmed = args.pop(CONFIRM_FIELD, None) is True

        async with self._session_factory() as session:
            result = await self._run(session, principal, name, args, confirmed)
            if result.status == STATUS_RATE_LIMITED:
                # Not stored: a flood of refused calls must not flood the audit table.
                logger.warning(
                    "MCP: rate limit hit for user=%s key=%s tool=%s",
                    principal.user_id,
                    principal.api_key_prefix,
                    name[:64],
                )
                return result
            try:
                await audit_log(
                    session,
                    action=AUDIT_ACTION,
                    entity_type=AUDIT_ENTITY,
                    entity_id=_entity_id(args),
                    user_id=principal.user_id,
                    details={
                        "tool": name[:64],
                        "status": result.status,
                        "confirmed": confirmed,
                        "via": via,
                        "arguments": _audit_arguments(args),
                        "api_key_prefix": principal.api_key_prefix,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    },
                )
                await session.commit()
            except Exception:
                logger.exception("MCP: audit write failed for tool '%s'; call rolled back", name)
                await session.rollback()
                return McpToolResult(
                    STATUS_ERROR,
                    "The call could not be recorded in the audit log, so it was not applied.",
                    {},
                )
        return result

    async def _run(
        self,
        session: AsyncSession,
        principal: McpPrincipal,
        name: str,
        args: dict[str, Any],
        confirmed: bool,
    ) -> McpToolResult:
        allowed, _remaining = self._limiter.is_allowed(principal.rate_limit_key)
        if not allowed:
            return McpToolResult(STATUS_RATE_LIMITED, "Rate limit exceeded. Try again in a minute.", {})

        spec = (await get_tool_specs()).get(name)
        if spec is None:
            return McpToolResult(STATUS_UNKNOWN, f"Unknown tool: {name[:64]}", {})

        if not principal.can(spec.permission):
            return McpToolResult(
                STATUS_DENIED,
                f"Permission denied: '{spec.name}' requires '{spec.permission}'.",
                {"required_permission": spec.permission},
            )

        proposal = spec.write and not confirmed
        runner = spec.preview if proposal else spec.handler
        if proposal and runner is None:
            return McpToolResult(
                STATUS_PROPOSAL,
                f"Proposal only, nothing was saved. Call '{spec.name}' again with confirm=true to apply.",
                {"proposed": dict(args), "confirm_with": {**args, CONFIRM_FIELD: True}},
            )

        try:
            raw = await runner(session, args, principal.user_id)  # type: ignore[misc]
        except Exception as exc:
            logger.exception("MCP: tool '%s' raised", spec.name)
            await session.rollback()
            return McpToolResult(STATUS_ERROR, f"Tool failed: {type(exc).__name__}", {})

        if not isinstance(raw, dict):
            await session.rollback()
            return McpToolResult(STATUS_ERROR, "Tool returned an unexpected result.", {})

        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        summary = str(raw.get("summary", ""))
        if raw.get("renderer") == "error":
            # Handlers swallow their own exceptions; make sure nothing half-done is kept.
            await session.rollback()
            return McpToolResult(STATUS_ERROR, summary or "Tool failed.", data)

        if proposal:
            await session.rollback()  # a preview must never persist anything
            return McpToolResult(
                STATUS_PROPOSAL,
                f"Proposal only, nothing was saved. {summary} "
                f"Show this to the user and call '{spec.name}' again with confirm=true to apply.",
                {"proposed": data, "confirm_with": {**args, CONFIRM_FIELD: True}},
            )
        return McpToolResult(STATUS_OK, summary, data)
