"""MCP protocol server and the ``/mcp`` HTTP endpoint (Streamable HTTP).

Built on the official ``mcp`` Python SDK.  The endpoint is stateless and
answers with plain JSON, so it works behind any proxy and needs no sticky
sessions.

Request flow::

    HTTP request -> McpHttpApp (module enabled? API key valid?)
                 -> SDK session manager -> handlers below
                 -> McpToolService (RBAC, confirm gate, audit)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.modules.mcp_server.auth import McpPrincipal, authenticate_api_key, extract_api_key
from app.modules.mcp_server.service import McpToolResult, McpToolService

logger = logging.getLogger(__name__)

MODULE_NAME = "oe_mcp_server"
MCP_PATH = "/mcp"
SERVER_NAME = "openconstructionerp"
PRINCIPAL_STATE_KEY = "mcp_principal"

INSTRUCTIONS = (
    "Tools for an OpenConstructionERP workspace: projects, bills of quantities (BOQ), "
    "cost database, schedule, risks and validation reports. Start with get_all_projects "
    "to find project IDs. Tools that change data return a proposal first: show it to the "
    "user and only call the tool again with confirm=true after they approve."
)

RESOURCE_SCHEME = "erp"
# uri-suffix -> (tool that serves it, human name)
_PROJECT_RESOURCES: dict[str, tuple[str, str]] = {
    "": ("get_project_summary", "Project summary"),
    "/boq": ("get_boq_items", "Project BOQ positions"),
    "/validation": ("get_validation_results", "Project validation reports"),
}

PrincipalResolver = Callable[[], McpPrincipal | None]


def _to_call_result(result: McpToolResult) -> types.CallToolResult:
    payload = result.as_dict()
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, default=str))],
        structuredContent=payload,
        isError=result.is_error,
    )


def resolve_resource(uri: str) -> tuple[str, dict[str, Any]] | None:
    """Map an ``erp://`` resource URI to ``(tool_name, arguments)``."""
    prefix = f"{RESOURCE_SCHEME}://projects"
    if uri == prefix:
        return "get_all_projects", {}
    if not uri.startswith(prefix + "/"):
        return None
    rest = uri[len(prefix) + 1 :]
    project_id, sep, tail = rest.partition("/")
    suffix = sep + tail
    if suffix not in _PROJECT_RESOURCES:
        return None
    try:
        uuid.UUID(project_id)
    except ValueError:
        return None
    return _PROJECT_RESOURCES[suffix][0], {"project_id": project_id}


def build_mcp_server(
    service: McpToolService | None = None,
    principal_resolver: PrincipalResolver | None = None,
) -> Server:
    """Create the MCP server.

    Args:
        service: Tool service (defaults to one bound to the app database).
        principal_resolver: Returns the caller when there is no HTTP request
            (in-memory transports, tests). Over HTTP the caller always comes
            from the authenticated request.
    """
    from app.config import get_settings

    tool_service = service or McpToolService()
    server: Server = Server(
        SERVER_NAME,
        version=getattr(get_settings(), "app_version", None),
        instructions=INSTRUCTIONS,
    )

    def current_principal() -> McpPrincipal:
        principal: McpPrincipal | None = None
        request = getattr(server.request_context, "request", None)
        if request is not None:
            principal = getattr(request.state, PRINCIPAL_STATE_KEY, None)
        elif principal_resolver is not None:
            principal = principal_resolver()
        if principal is None:
            raise PermissionError("Not authenticated")
        return principal

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        specs = await tool_service.list_tools(current_principal())
        return [
            types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
                annotations=types.ToolAnnotations(
                    readOnlyHint=not spec.write,
                    destructiveHint=False,
                    openWorldHint=False,
                ),
            )
            for spec in specs
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        result = await tool_service.call_tool(current_principal(), name, arguments)
        return _to_call_result(result)

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        allowed = {spec.name for spec in await tool_service.list_tools(current_principal())}
        if "get_all_projects" not in allowed:
            return []
        return [
            types.Resource(
                uri=AnyUrl(f"{RESOURCE_SCHEME}://projects"),
                name="Projects",
                description="Projects visible to the authenticated user.",
                mimeType="application/json",
            )
        ]

    @server.list_resource_templates()
    async def list_resource_templates() -> list[types.ResourceTemplate]:
        allowed = {spec.name for spec in await tool_service.list_tools(current_principal())}
        return [
            types.ResourceTemplate(
                uriTemplate=f"{RESOURCE_SCHEME}://projects/{{project_id}}{suffix}",
                name=label,
                mimeType="application/json",
            )
            for suffix, (tool, label) in _PROJECT_RESOURCES.items()
            if tool in allowed
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        target = resolve_resource(str(uri))
        if target is None:
            raise ValueError(f"Unknown resource: {uri}")
        tool, arguments = target
        result = await tool_service.call_tool(current_principal(), tool, arguments, via="resource")
        if result.is_error:
            raise ValueError(result.summary)
        return [
            ReadResourceContents(
                content=json.dumps(result.as_dict(), default=str),
                mime_type="application/json",
            )
        ]

    return server


def _module_enabled() -> bool:
    from app.core.module_loader import module_loader

    return module_loader.is_enabled(MODULE_NAME)


class McpHttpApp:
    """ASGI app for ``/mcp``: gatekeeping in front of the SDK transport.

    The SDK session manager needs a long-lived task group.  The host app uses
    startup events rather than a lifespan context, so the manager runs in its
    own background task, started on first use and stopped on shutdown.
    """

    def __init__(
        self,
        service: McpToolService | None = None,
        session_factory: Callable[[], Any] | None = None,
        enabled_check: Callable[[], bool] = _module_enabled,
    ) -> None:
        self._service = service
        self._session_factory = session_factory
        self._enabled_check = enabled_check
        self._manager: StreamableHTTPSessionManager | None = None
        self._runner: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._start_lock = asyncio.Lock()

    async def _ensure_started(self) -> StreamableHTTPSessionManager:
        async with self._start_lock:
            if self._manager is not None and self._runner is not None and not self._runner.done():
                return self._manager

            manager = StreamableHTTPSessionManager(
                app=build_mcp_server(self._service),
                stateless=True,
                json_response=True,
            )
            ready = asyncio.Event()
            stop = asyncio.Event()

            async def run() -> None:
                async with manager.run():
                    ready.set()
                    await stop.wait()

            runner = asyncio.create_task(run(), name="mcp-session-manager")
            waiter = asyncio.create_task(ready.wait())
            await asyncio.wait({runner, waiter}, return_when=asyncio.FIRST_COMPLETED)
            waiter.cancel()
            if runner.done():
                runner.result()  # surface the startup error
                raise RuntimeError("MCP session manager stopped during startup")
            self._manager, self._runner, self._stop = manager, runner, stop
            return manager

    async def stop(self) -> None:
        """Stop the background session manager (safe to call repeatedly)."""
        runner, stop = self._runner, self._stop
        self._manager = self._runner = self._stop = None
        if runner is None or stop is None:
            return
        stop.set()
        try:
            await asyncio.wait_for(runner, timeout=5)
        except (TimeoutError, asyncio.CancelledError, RuntimeError):
            runner.cancel()

    async def _authenticate(self, request: Request) -> McpPrincipal | None:
        raw_key = extract_api_key({k.lower(): v for k, v in request.headers.items()})
        if raw_key is None:
            return None
        factory = self._session_factory
        if factory is None:
            from app.database import async_session_factory

            factory = async_session_factory
        async with factory() as session:
            principal = await authenticate_api_key(session, raw_key)
            if principal is not None:
                await session.commit()  # persist last_used_at
            return principal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        request = Request(scope, receive)

        if not self._enabled_check():
            await JSONResponse({"detail": "Not found"}, status_code=404)(scope, receive, send)
            return

        try:
            principal = await self._authenticate(request)
        except Exception:
            logger.exception("MCP: authentication backend failed")
            await JSONResponse({"detail": "Authentication service temporarily unavailable"}, status_code=503)(
                scope, receive, send
            )
            return
        if principal is None:
            await JSONResponse(
                {"detail": "A valid API key is required (Authorization: Bearer oe_...)."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="mcp"'},
            )(scope, receive, send)
            return

        scope.setdefault("state", {})[PRINCIPAL_STATE_KEY] = principal
        manager = await self._ensure_started()
        await manager.handle_request(scope, receive, send)


def mount_mcp(app: Any) -> McpHttpApp:
    """Attach the MCP endpoint to the FastAPI app at ``/mcp`` (idempotent)."""
    existing = getattr(app.state, "mcp_http_app", None)
    if existing is not None:
        return existing
    mcp_app = McpHttpApp()
    # Exact routes rather than a Mount: a Mount would answer POST /mcp with a
    # redirect to /mcp/, which many MCP clients do not follow.
    for path in (MCP_PATH, MCP_PATH + "/"):
        app.router.routes.insert(0, Route(path, endpoint=mcp_app, include_in_schema=False))
    app.state.mcp_http_app = mcp_app
    logger.info("MCP endpoint mounted at %s", MCP_PATH)
    return mcp_app


async def unmount_mcp(app: Any) -> None:
    """Stop the MCP background task on application shutdown."""
    mcp_app = getattr(app.state, "mcp_http_app", None)
    if mcp_app is not None:
        await mcp_app.stop()
