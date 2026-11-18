"""MCP server status API.

Mounted by the module loader at ``/api/v1/mcp_server``.  The MCP protocol
endpoint itself lives at ``/mcp`` (see ``server.py``); this router only tells
a signed-in user what that endpoint offers them.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.permissions import Role, _resolve_role
from app.dependencies import get_current_user_payload
from app.modules.mcp_server.auth import McpPrincipal
from app.modules.mcp_server.registry import WITHHELD_TOOLS
from app.modules.mcp_server.server import MCP_PATH
from app.modules.mcp_server.service import McpToolService

router = APIRouter()


class McpToolInfo(BaseModel):
    """A tool the current user can call over MCP."""

    name: str
    description: str
    permission: str
    write: bool


class McpInfoResponse(BaseModel):
    """What the MCP endpoint offers the current user."""

    endpoint: str
    transport: str
    auth: str
    tools: list[McpToolInfo]
    withheld_tools: dict[str, str]


@router.get("/info/", response_model=McpInfoResponse)
async def get_mcp_info(
    payload: Annotated[dict[str, Any], Depends(get_current_user_payload)],
) -> McpInfoResponse:
    """Describe the MCP endpoint and the tools available to the current user."""
    role = str(payload.get("role", ""))
    principal = McpPrincipal(
        user_id=str(payload.get("sub", "")),
        role=role,
        permissions=frozenset(payload.get("permissions", [])),
        is_admin=_resolve_role(role) == Role.ADMIN,
    )
    specs = await McpToolService().list_tools(principal)
    return McpInfoResponse(
        endpoint=MCP_PATH,
        transport="streamable-http",
        auth="Authorization: Bearer <API key>",
        tools=[
            McpToolInfo(name=s.name, description=s.description, permission=s.permission, write=s.write) for s in specs
        ],
        withheld_tools=WITHHELD_TOOLS,
    )
