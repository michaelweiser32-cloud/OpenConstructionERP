"""MCP tool registry.

Builds the set of tools exposed over MCP from the ``erp_chat`` tool
definitions plus an explicit security policy.  The policy is fail-closed:
a chat tool that has no entry in ``TOOL_POLICY`` is never exposed, so adding
a new chat tool does not silently publish it to external clients.

Other modules can contribute tools through the ``mcp.tools`` filter hook::

    from app.core.hooks import hooks
    from app.modules.mcp_server.registry import McpToolSpec

    @hooks.filter("mcp.tools", module="oe_tendering")
    async def add_tools(specs: list[McpToolSpec]) -> list[McpToolSpec]:
        return [*specs, McpToolSpec(name="list_tenders", ...)]
"""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import hooks
from app.modules.erp_chat import tools as erp_tools

logger = logging.getLogger(__name__)

MCP_TOOLS_HOOK = "mcp.tools"
CONFIRM_FIELD = "confirm"

ToolHandler = Callable[[AsyncSession, dict[str, Any], str], Awaitable[dict[str, Any]]]
"""Same signature as the erp_chat handlers: (session, arguments, user_id) -> result."""

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass(frozen=True)
class McpToolSpec:
    """One tool exposed over MCP.

    Attributes:
        name: Unique tool name.
        description: Human/LLM-readable description.
        input_schema: JSON Schema for the arguments.
        permission: RBAC permission the caller must hold. Required.
        handler: Executes the tool. Returns ``{renderer, data, summary}``.
        write: True if the tool changes data. Write tools only run with
            ``confirm=true``; otherwise ``preview`` produces a proposal.
        preview: Builds the proposal for a write tool without changing data.
            Must perform the same authorization checks as ``handler``.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    permission: str
    handler: ToolHandler
    write: bool = False
    preview: ToolHandler | None = None


# ── Handlers that differ from the chat versions ─────────────────────────────


async def list_projects_for_user(session: AsyncSession, args: dict[str, Any], user_id: str) -> dict[str, Any]:
    """List projects the caller owns (admins see all).

    The chat handler for ``get_all_projects`` lists every project in the
    database regardless of the caller, so MCP uses this scoped version.
    """
    _ = args
    from app.config import get_settings
    from app.modules.projects.service import ProjectService
    from app.modules.users.repository import UserRepository

    owner_id = erp_tools._parse_uuid(user_id, "user_id")
    user = await UserRepository(session).get_by_id(owner_id)
    is_admin = bool(user and getattr(user, "role", "") == "admin")

    svc = ProjectService(session, get_settings())
    projects, total = await svc.list_projects(owner_id, is_admin=is_admin, limit=50)
    return {
        "renderer": "projects_grid",
        "data": {
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "code": getattr(p, "project_code", ""),
                    "status": p.status,
                    "region": getattr(p, "region", ""),
                    "currency": getattr(p, "currency", "EUR"),
                    "contract_value": float(getattr(p, "contract_value", 0) or 0),
                }
                for p in projects
            ],
            "total": total,
        },
        "summary": f"{total} projects found",
    }


def _non_negative_number(raw: Any, field_name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise erp_tools.ToolAuthError(f"'{field_name}' must be a number")
    if raw < 0:
        raise erp_tools.ToolAuthError(f"'{field_name}' must not be negative")
    return float(raw)


async def preview_create_boq_item(session: AsyncSession, args: dict[str, Any], user_id: str) -> dict[str, Any]:
    """Validate a ``create_boq_item`` call and describe it without saving."""
    try:
        project_id = erp_tools._parse_uuid(args.get("project_id"), "project_id")
        await erp_tools._require_project_access(session, project_id, user_id)
        description = erp_tools._parse_str(args.get("description"), "description", required=True)
        unit = erp_tools._parse_str(args.get("unit"), "unit", required=True, max_length=20)
        quantity = _non_negative_number(args.get("quantity"), "quantity")
        unit_rate = _non_negative_number(args.get("unit_rate"), "unit_rate")
    except erp_tools.ToolAuthError as exc:
        return erp_tools._auth_error(str(exc))

    total = round(quantity * unit_rate, 2)
    return {
        "renderer": "boq_item_proposal",
        "data": {
            "project_id": str(project_id),
            "description": description,
            "unit": unit,
            "quantity": quantity,
            "unit_rate": unit_rate,
            "total": total,
        },
        "summary": (f"Would create BOQ position '{description}': {quantity} {unit} x {unit_rate} = {total:.2f}"),
    }


# ── Security policy for the erp_chat tools ──────────────────────────────────


@dataclass(frozen=True)
class _Policy:
    permission: str
    write: bool = False
    handler: ToolHandler | None = None  # override the chat handler
    preview: ToolHandler | None = None


TOOL_POLICY: dict[str, _Policy] = {
    "get_all_projects": _Policy("projects.read", handler=list_projects_for_user),
    "get_project_summary": _Policy("projects.read"),
    "compare_projects": _Policy("projects.read"),
    "get_boq_items": _Policy("boq.read"),
    "get_schedule": _Policy("schedule.read"),
    "get_validation_results": _Policy("validation.read"),
    # Despite its name the chat handler only reads the latest reports.
    "run_validation": _Policy("validation.read"),
    "get_risk_register": _Policy("risk.read"),
    "get_cost_model": _Policy("costmodel.read"),
    "search_cwicr_database": _Policy("costs.read"),
    "create_boq_item": _Policy("boq.create", write=True, preview=preview_create_boq_item),
}

# Chat tools deliberately NOT exposed over MCP, with the reason.
WITHHELD_TOOLS: dict[str, str] = dict.fromkeys(
    (
        "search_boq_positions",
        "search_documents",
        "search_tasks",
        "search_risks",
        "search_bim_elements",
        "search_anything",
    ),
    "semantic search does not enforce per-project access yet",
)


def _with_confirm(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with the optional boolean ``confirm`` field."""
    out = copy.deepcopy(schema) if schema else {"type": "object", "properties": {}}
    out.setdefault("type", "object")
    props = out.setdefault("properties", {})
    props[CONFIRM_FIELD] = {
        "type": "boolean",
        "description": (
            "Leave unset to receive a proposal without saving anything. "
            "Set to true only after the user has approved the proposal."
        ),
    }
    return out


def core_tool_specs() -> list[McpToolSpec]:
    """Build specs for the erp_chat tools that have a policy entry."""
    specs: list[McpToolSpec] = []
    for definition in erp_tools.TOOL_DEFINITIONS:
        name = definition.get("name", "")
        policy = TOOL_POLICY.get(name)
        if policy is None:
            if name not in WITHHELD_TOOLS:
                logger.info("MCP: chat tool '%s' has no MCP policy and is not exposed", name)
            continue
        handler = policy.handler or erp_tools.TOOL_HANDLER_MAP.get(name)
        if handler is None:
            logger.warning("MCP: chat tool '%s' has no handler and is not exposed", name)
            continue
        description = definition.get("description", "")
        schema = definition.get("input_schema") or {"type": "object", "properties": {}}
        if policy.write:
            schema = _with_confirm(schema)
            description += " Changes data: without confirm=true this only returns a proposal for the user to review."
        specs.append(
            McpToolSpec(
                name=name,
                description=description,
                input_schema=schema,
                permission=policy.permission,
                handler=handler,
                write=policy.write,
                preview=policy.preview,
            )
        )
    return specs


def _is_valid(spec: Any) -> bool:
    return (
        isinstance(spec, McpToolSpec)
        and bool(_NAME_RE.match(spec.name or ""))
        and isinstance(spec.permission, str)
        and bool(spec.permission.strip())
        and callable(spec.handler)
        and isinstance(spec.input_schema, dict)
    )


async def get_tool_specs() -> dict[str, McpToolSpec]:
    """Return all MCP tools: core tools plus those added via the ``mcp.tools`` hook.

    Invalid contributions (no permission, no handler, bad name) are dropped,
    a failing hook falls back to the core tools, and a hook cannot replace a
    core tool, so a plugin can never break or weaken the endpoint.
    """
    core = core_tool_specs()
    try:
        contributed = await hooks.apply_filters(MCP_TOOLS_HOOK, list(core))
    except Exception:
        logger.exception("MCP: '%s' hook failed; serving core tools only", MCP_TOOLS_HOOK)
        contributed = core
    if not isinstance(contributed, list):
        logger.warning("MCP: '%s' hook returned %s, expected list", MCP_TOOLS_HOOK, type(contributed))
        contributed = core

    specs: dict[str, McpToolSpec] = {}
    for spec in contributed:
        if not _is_valid(spec):
            logger.warning("MCP: dropping invalid tool spec %r", getattr(spec, "name", spec))
            continue
        if spec.write and CONFIRM_FIELD not in spec.input_schema.get("properties", {}):
            spec = McpToolSpec(
                name=spec.name,
                description=spec.description,
                input_schema=_with_confirm(spec.input_schema),
                permission=spec.permission,
                handler=spec.handler,
                write=True,
                preview=spec.preview,
            )
        specs[spec.name] = spec
    # Core tools always win: a hook may add tools but not replace a core policy.
    for spec in core:
        specs[spec.name] = spec
    return specs
