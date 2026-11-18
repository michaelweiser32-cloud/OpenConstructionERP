"""Tests for the MCP server module.

Covers API-key authentication, the fail-closed tool registry, RBAC,
confirm-gating of write tools, audit logging, and the MCP protocol surface
(in-memory client and the HTTP endpoint).

All data is synthetic.  The erp_chat handlers are replaced with recording
fakes so the tests need only three tables (users, API keys, audit log).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.routing import Route

from app.core.audit import AuditEntry
from app.core.hooks import hooks
from app.core.permissions import Role, permission_registry
from app.core.rate_limiter import RateLimiter
from app.database import Base
from app.modules.erp_chat import tools as erp_tools
from app.modules.mcp_server import registry
from app.modules.mcp_server import service as service_module
from app.modules.mcp_server.auth import (
    McpPrincipal,
    authenticate_api_key,
    build_principal,
    extract_api_key,
)
from app.modules.mcp_server.registry import McpToolSpec, get_tool_specs
from app.modules.mcp_server.server import McpHttpApp, build_mcp_server, resolve_resource
from app.modules.mcp_server.service import AUDIT_ACTION, McpToolService
from app.modules.users.models import APIKey, User
from app.modules.users.service import generate_api_key

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
BOQ_ARGS = {
    "project_id": PROJECT_ID,
    "description": "Synthetic test wall",
    "unit": "m2",
    "quantity": 10,
    "unit_rate": 25.5,
}

_PERMISSIONS = {
    "projects": {"projects.read": Role.VIEWER},
    "boq": {"boq.read": Role.VIEWER, "boq.create": Role.EDITOR},
    "schedule": {"schedule.read": Role.VIEWER},
    "validation": {"validation.read": Role.VIEWER},
    "risk": {"risk.read": Role.VIEWER},
    "costmodel": {"costmodel.read": Role.VIEWER},
    "costs": {"costs.read": Role.VIEWER},
}


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _permissions():
    for module, perms in _PERMISSIONS.items():
        permission_registry.register_module_permissions(module, perms)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[User.__table__, APIKey.__table__, AuditEntry.__table__],
            )
        )
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _make_user(
    factory: Any,
    role: str,
    *,
    active: bool = True,
    key_active: bool = True,
    expires_at: datetime | None = None,
    key_permissions: list[str] | None = None,
) -> tuple[User, str]:
    """Create a synthetic user with one API key. Returns (user, raw_key)."""
    full_key, key_hash, key_prefix = generate_api_key()
    async with factory() as session:
        user = User(
            email=f"{role}-{uuid.uuid4().hex[:8]}@example.test",
            hashed_password="not-a-real-hash",
            full_name=f"Synthetic {role}",
            role=role,
            is_active=active,
        )
        session.add(user)
        await session.flush()
        session.add(
            APIKey(
                user_id=user.id,
                name="test key",
                key_hash=key_hash,
                key_prefix=key_prefix,
                is_active=key_active,
                expires_at=expires_at,
                permissions=key_permissions or [],
            )
        )
        await session.commit()
        return user, full_key


class Recorder:
    """Stand-in for the erp_chat handlers; records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def handler(self, name: str, result: dict[str, Any] | None = None, raises: bool = False):
        async def _handler(session: AsyncSession, args: dict[str, Any], user_id: str):
            self.calls.append((name, dict(args), user_id))
            if raises:
                raise RuntimeError("secret internal detail")
            return result or {"renderer": "ok", "data": {"tool": name}, "summary": f"{name} ok"}

        return _handler

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def recorder(monkeypatch) -> Recorder:
    rec = Recorder()
    fake_map = {name: rec.handler(name) for name in erp_tools.TOOL_HANDLER_MAP}
    monkeypatch.setattr(erp_tools, "TOOL_HANDLER_MAP", fake_map)
    monkeypatch.setitem(
        registry.TOOL_POLICY,
        "get_all_projects",
        registry._Policy("projects.read", handler=rec.handler("get_all_projects")),
    )

    async def _allow(session, project_id, user_id):
        return None

    monkeypatch.setattr(erp_tools, "_require_project_access", _allow)
    return rec


@pytest.fixture
def clean_hooks():
    saved = list(hooks._filters.get(registry.MCP_TOOLS_HOOK, []))
    hooks._filters[registry.MCP_TOOLS_HOOK] = []
    yield
    hooks._filters[registry.MCP_TOOLS_HOOK] = saved


async def _principal(factory: Any, role: str, **kwargs: Any) -> McpPrincipal:
    _user, key = await _make_user(factory, role, **kwargs)
    async with factory() as session:
        principal = await authenticate_api_key(session, key)
        await session.commit()
    assert principal is not None
    return principal


def _service(factory: Any, limit: int = 1000) -> McpToolService:
    return McpToolService(session_factory=factory, limiter=RateLimiter(limit, 60))


async def _audit_rows(factory: Any) -> list[AuditEntry]:
    async with factory() as session:
        rows = await session.execute(select(AuditEntry).order_by(AuditEntry.created_at))
        return list(rows.scalars())


# ── Authentication ──────────────────────────────────────────────────────────


class TestAuth:
    def test_extract_api_key(self):
        assert extract_api_key({"authorization": "Bearer oe_abc"}) == "oe_abc"
        assert extract_api_key({"authorization": "bearer oe_abc"}) == "oe_abc"
        assert extract_api_key({"x-api-key": "oe_xyz"}) == "oe_xyz"
        assert extract_api_key({"authorization": "Basic abc"}) is None
        assert extract_api_key({}) is None

    async def test_valid_key_resolves_user_and_role(self, session_factory):
        user, key = await _make_user(session_factory, "editor")
        async with session_factory() as session:
            principal = await authenticate_api_key(session, key)
            await session.commit()
        assert principal is not None
        assert principal.user_id == str(user.id)
        assert principal.role == "editor"
        assert principal.can("boq.create")
        assert not principal.is_admin
        async with session_factory() as session:
            stored = (await session.execute(select(APIKey))).scalar_one()
            assert stored.last_used_at is not None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"key_active": False},
            {"active": False},
            {"expires_at": datetime.now(UTC) - timedelta(days=1)},
        ],
        ids=["revoked-key", "inactive-user", "expired-key"],
    )
    async def test_rejected_keys(self, session_factory, kwargs):
        _user, key = await _make_user(session_factory, "editor", **kwargs)
        async with session_factory() as session:
            assert await authenticate_api_key(session, key) is None

    @pytest.mark.parametrize("raw", [None, "", "oe_does-not-exist", "sk-wrong-prefix", "oe_" + "x" * 400])
    async def test_unknown_or_malformed_keys(self, session_factory, raw):
        await _make_user(session_factory, "admin")
        async with session_factory() as session:
            assert await authenticate_api_key(session, raw) is None

    async def test_unexpired_key_is_accepted(self, session_factory):
        _user, key = await _make_user(session_factory, "viewer", expires_at=datetime.now(UTC) + timedelta(days=1))
        async with session_factory() as session:
            assert await authenticate_api_key(session, key) is not None

    async def test_viewer_cannot_write(self, session_factory):
        principal = await _principal(session_factory, "viewer")
        assert principal.can("boq.read")
        assert not principal.can("boq.create")

    async def test_scoped_key_narrows_role_and_drops_admin_bypass(self, session_factory):
        editor = await _principal(session_factory, "editor", key_permissions=["boq.read", "users.delete"])
        assert editor.permissions == frozenset({"boq.read"})  # users.delete is not an editor right

        admin = await _principal(session_factory, "admin", key_permissions=["boq.read"])
        assert not admin.is_admin
        assert admin.can("boq.read")
        assert not admin.can("boq.create")

    def test_role_is_taken_from_the_user_record(self):
        user = User(id=uuid.uuid4(), email="a@example.test", hashed_password="x", role="admin")
        assert build_principal(user).is_admin


# ── Registry ────────────────────────────────────────────────────────────────


class TestRegistry:
    async def test_exposes_policy_tools_only(self, clean_hooks):
        specs = await get_tool_specs()
        assert set(specs) == set(registry.TOOL_POLICY)
        assert "create_boq_item" in specs
        for withheld in registry.WITHHELD_TOOLS:
            assert withheld not in specs

    async def test_every_tool_has_permission_and_handler(self, clean_hooks):
        for spec in (await get_tool_specs()).values():
            assert spec.permission
            assert callable(spec.handler)

    async def test_only_create_boq_item_writes_and_it_takes_confirm(self, clean_hooks):
        specs = await get_tool_specs()
        assert [s.name for s in specs.values() if s.write] == ["create_boq_item"]
        props = specs["create_boq_item"].input_schema["properties"]
        assert props["confirm"]["type"] == "boolean"
        assert "confirm" not in specs["create_boq_item"].input_schema.get("required", [])
        assert "confirm" not in specs["get_boq_items"].input_schema["properties"]

    async def test_new_chat_tool_without_policy_is_not_exposed(self, clean_hooks, monkeypatch):
        extra = {"name": "delete_everything", "description": "x", "input_schema": {"type": "object"}}
        monkeypatch.setattr(erp_tools, "TOOL_DEFINITIONS", [*erp_tools.TOOL_DEFINITIONS, extra])
        assert "delete_everything" not in await get_tool_specs()

    async def test_does_not_mutate_chat_tool_schemas(self, clean_hooks):
        await get_tool_specs()
        chat_def = next(d for d in erp_tools.TOOL_DEFINITIONS if d["name"] == "create_boq_item")
        assert "confirm" not in chat_def["input_schema"]["properties"]

    async def test_hook_can_add_tools(self, clean_hooks):
        async def handler(session, args, user_id):
            return {"renderer": "ok", "data": {}, "summary": "ok"}

        async def add(specs):
            return [
                *specs,
                McpToolSpec("list_tenders", "List tenders", {"type": "object"}, "projects.read", handler),
                McpToolSpec("award_tender", "Award", {"type": "object"}, "boq.create", handler, write=True),
            ]

        hooks.add_filter(registry.MCP_TOOLS_HOOK, add)
        specs = await get_tool_specs()
        assert "list_tenders" in specs
        # write tools from plugins get the confirm field automatically
        assert "confirm" in specs["award_tender"].input_schema["properties"]

    async def test_hook_cannot_weaken_or_break_the_registry(self, clean_hooks):
        async def handler(session, args, user_id):
            return {}

        async def tamper(specs):
            return [
                McpToolSpec("create_boq_item", "hijacked", {"type": "object"}, "projects.read", handler),
                McpToolSpec("no_permission", "x", {"type": "object"}, "", handler),
                McpToolSpec("bad name!", "x", {"type": "object"}, "projects.read", handler),
                "not a spec",
            ]

        hooks.add_filter(registry.MCP_TOOLS_HOOK, tamper)
        specs = await get_tool_specs()
        assert specs["create_boq_item"].write is True
        assert specs["create_boq_item"].permission == "boq.create"
        assert "no_permission" not in specs
        assert "bad name!" not in specs
        assert set(registry.TOOL_POLICY) <= set(specs)

    async def test_failing_hook_falls_back_to_core_tools(self, clean_hooks):
        async def boom(specs):
            raise RuntimeError("plugin bug")

        hooks.add_filter(registry.MCP_TOOLS_HOOK, boom)
        assert set(await get_tool_specs()) == set(registry.TOOL_POLICY)


class TestBoqPreview:
    async def test_preview_describes_without_saving(self, recorder):
        result = await registry.preview_create_boq_item(None, dict(BOQ_ARGS), "user")  # type: ignore[arg-type]
        assert result["renderer"] == "boq_item_proposal"
        assert result["data"]["total"] == 255.0
        assert recorder.calls == []

    @pytest.mark.parametrize(
        "patch",
        [
            {"project_id": "not-a-uuid"},
            {"description": ""},
            {"quantity": -1},
            {"unit_rate": "12"},
            {"quantity": True},
        ],
    )
    async def test_preview_rejects_bad_input(self, recorder, patch):
        result = await registry.preview_create_boq_item(None, {**BOQ_ARGS, **patch}, "user")  # type: ignore[arg-type]
        assert result["renderer"] == "error"

    async def test_preview_enforces_project_access(self, monkeypatch):
        async def deny(session, project_id, user_id):
            raise erp_tools.ToolAuthError("Access denied")

        monkeypatch.setattr(erp_tools, "_require_project_access", deny)
        result = await registry.preview_create_boq_item(None, dict(BOQ_ARGS), "user")  # type: ignore[arg-type]
        assert result["renderer"] == "error"
        assert "Access denied" in result["summary"]


# ── Service: RBAC, confirm gate, audit ──────────────────────────────────────


class TestService:
    async def test_tool_list_is_filtered_by_role(self, session_factory, recorder, clean_hooks):
        svc = _service(session_factory)
        viewer = {s.name for s in await svc.list_tools(await _principal(session_factory, "viewer"))}
        editor = {s.name for s in await svc.list_tools(await _principal(session_factory, "editor"))}
        assert "create_boq_item" not in viewer
        assert "get_boq_items" in viewer
        assert "create_boq_item" in editor

    async def test_read_tool_runs_as_the_key_owner_and_is_audited(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        result = await _service(session_factory).call_tool(principal, "get_boq_items", {"project_id": PROJECT_ID})
        assert result.status == "ok"
        assert recorder.calls == [("get_boq_items", {"project_id": PROJECT_ID}, principal.user_id)]

        rows = await _audit_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].action == AUDIT_ACTION
        assert str(rows[0].user_id) == principal.user_id
        assert rows[0].entity_id == PROJECT_ID
        assert rows[0].details["tool"] == "get_boq_items"
        assert rows[0].details["status"] == "ok"
        assert rows[0].details["api_key_prefix"] == principal.api_key_prefix

    async def test_viewer_is_denied_write_tool(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        result = await _service(session_factory).call_tool(principal, "create_boq_item", {**BOQ_ARGS, "confirm": True})
        assert result.status == "denied"
        assert result.is_error
        assert recorder.calls == []
        rows = await _audit_rows(session_factory)
        assert rows[0].details["status"] == "denied"

    @pytest.mark.parametrize("confirm", [None, False, "true", 1, "yes"])
    async def test_write_without_real_confirm_only_proposes(self, session_factory, recorder, clean_hooks, confirm):
        principal = await _principal(session_factory, "editor")
        args = dict(BOQ_ARGS) if confirm is None else {**BOQ_ARGS, "confirm": confirm}
        result = await _service(session_factory).call_tool(principal, "create_boq_item", args)

        assert result.status == "proposal"
        assert not result.is_error
        assert recorder.calls == []  # the real handler never ran
        assert result.data["proposed"]["total"] == 255.0
        assert result.data["confirm_with"]["confirm"] is True
        rows = await _audit_rows(session_factory)
        assert rows[0].details["status"] == "proposal"
        assert rows[0].details["confirmed"] is False

    async def test_confirmed_write_executes_once(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "editor")
        result = await _service(session_factory).call_tool(principal, "create_boq_item", {**BOQ_ARGS, "confirm": True})
        assert result.status == "ok"
        assert recorder.calls == [("create_boq_item", BOQ_ARGS, principal.user_id)]  # confirm stripped
        rows = await _audit_rows(session_factory)
        assert rows[0].details["status"] == "ok"
        assert rows[0].details["confirmed"] is True

    async def test_unknown_and_withheld_tools_are_refused(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "admin")
        svc = _service(session_factory)
        assert (await svc.call_tool(principal, "nope", {})).status == "unknown_tool"
        assert (await svc.call_tool(principal, "search_anything", {"query": "x"})).status == "unknown_tool"
        assert recorder.calls == []
        assert [r.details["status"] for r in await _audit_rows(session_factory)] == ["unknown_tool"] * 2

    async def test_handler_error_result_is_reported(self, session_factory, recorder, clean_hooks, monkeypatch):
        failing = recorder.handler("get_schedule", {"renderer": "error", "data": {"error": "x"}, "summary": "Error: x"})
        monkeypatch.setitem(erp_tools.TOOL_HANDLER_MAP, "get_schedule", failing)
        principal = await _principal(session_factory, "viewer")
        result = await _service(session_factory).call_tool(principal, "get_schedule", {"project_id": PROJECT_ID})
        assert result.status == "error"
        assert (await _audit_rows(session_factory))[0].details["status"] == "error"

    async def test_handler_exception_does_not_leak_details(self, session_factory, recorder, clean_hooks, monkeypatch):
        monkeypatch.setitem(erp_tools.TOOL_HANDLER_MAP, "get_schedule", recorder.handler("get_schedule", raises=True))
        principal = await _principal(session_factory, "viewer")
        result = await _service(session_factory).call_tool(principal, "get_schedule", {"project_id": PROJECT_ID})
        assert result.status == "error"
        assert "secret internal detail" not in result.summary
        assert len(await _audit_rows(session_factory)) == 1

    async def test_rate_limit(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        svc = _service(session_factory, limit=2)
        statuses = [(await svc.call_tool(principal, "get_all_projects", {})).status for _ in range(3)]
        assert statuses == ["ok", "ok", "rate_limited"]
        assert len(recorder.calls) == 2

    async def test_write_is_rolled_back_when_audit_fails(self, session_factory, recorder, clean_hooks, monkeypatch):
        marker_email = "written-by-tool@example.test"

        async def writing_handler(session, args, user_id):
            session.add(User(email=marker_email, hashed_password="x", role="viewer"))
            await session.flush()
            return {"renderer": "ok", "data": {}, "summary": "created"}

        async def broken_audit(*args, **kwargs):
            raise RuntimeError("audit table unavailable")

        monkeypatch.setitem(erp_tools.TOOL_HANDLER_MAP, "create_boq_item", writing_handler)
        monkeypatch.setattr(service_module, "audit_log", broken_audit)

        principal = await _principal(session_factory, "editor")
        result = await _service(session_factory).call_tool(principal, "create_boq_item", {**BOQ_ARGS, "confirm": True})
        assert result.status == "error"
        async with session_factory() as session:
            found = await session.execute(select(User).where(User.email == marker_email))
            assert found.scalar_one_or_none() is None

    async def test_confirmed_write_and_audit_commit_together(self, session_factory, recorder, clean_hooks, monkeypatch):
        marker_email = "kept-by-tool@example.test"

        async def writing_handler(session, args, user_id):
            session.add(User(email=marker_email, hashed_password="x", role="viewer"))
            await session.flush()
            return {"renderer": "ok", "data": {}, "summary": "created"}

        monkeypatch.setitem(erp_tools.TOOL_HANDLER_MAP, "create_boq_item", writing_handler)
        principal = await _principal(session_factory, "editor")
        await _service(session_factory).call_tool(principal, "create_boq_item", {**BOQ_ARGS, "confirm": True})
        async with session_factory() as session:
            found = await session.execute(select(User).where(User.email == marker_email))
            assert found.scalar_one_or_none() is not None
        assert len(await _audit_rows(session_factory)) == 1

    async def test_audit_truncates_large_arguments(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        await _service(session_factory).call_tool(
            principal, "search_cwicr_database", {"query": "q" * 5000, "nested": {"a": 1}}
        )
        details = (await _audit_rows(session_factory))[0].details
        assert len(details["arguments"]["query"]) < 300
        assert details["arguments"]["nested"] == "<dict>"


# ── MCP protocol (in-memory client) ─────────────────────────────────────────


class TestProtocol:
    async def test_list_and_call_tools(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        server = build_mcp_server(_service(session_factory), lambda: principal)
        async with create_connected_server_and_client_session(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert "get_boq_items" in tools
            assert "create_boq_item" not in tools  # viewer
            assert tools["get_boq_items"].annotations.readOnlyHint is True

            result = await client.call_tool("get_boq_items", {"project_id": PROJECT_ID})
            assert result.isError is False
            assert result.structuredContent["status"] == "ok"
            assert json.loads(result.content[0].text)["summary"] == "get_boq_items ok"

    async def test_write_flow_propose_then_confirm(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "editor")
        server = build_mcp_server(_service(session_factory), lambda: principal)
        async with create_connected_server_and_client_session(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert tools["create_boq_item"].annotations.readOnlyHint is False

            proposal = await client.call_tool("create_boq_item", dict(BOQ_ARGS))
            assert proposal.structuredContent["status"] == "proposal"
            assert recorder.calls == []

            done = await client.call_tool("create_boq_item", {**BOQ_ARGS, "confirm": True})
            assert done.structuredContent["status"] == "ok"
            assert recorder.names() == ["create_boq_item"]

    async def test_schema_validation_rejects_bad_arguments(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "editor")
        server = build_mcp_server(_service(session_factory), lambda: principal)
        async with create_connected_server_and_client_session(server) as client:
            await client.list_tools()
            missing = await client.call_tool("create_boq_item", {"project_id": PROJECT_ID})
            assert missing.isError is True
            stringly = await client.call_tool("create_boq_item", {**BOQ_ARGS, "confirm": "true"})
            assert stringly.isError is True
            assert recorder.calls == []

    async def test_denied_call_is_an_error_result(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        server = build_mcp_server(_service(session_factory), lambda: principal)
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("create_boq_item", {**BOQ_ARGS, "confirm": True})
            assert result.isError is True
            assert recorder.calls == []

    async def test_resources(self, session_factory, recorder, clean_hooks):
        principal = await _principal(session_factory, "viewer")
        server = build_mcp_server(_service(session_factory), lambda: principal)
        async with create_connected_server_and_client_session(server) as client:
            resources = (await client.list_resources()).resources
            assert [str(r.uri) for r in resources] == ["erp://projects"]
            templates = (await client.list_resource_templates()).resourceTemplates
            assert "erp://projects/{project_id}/boq" in [t.uriTemplate for t in templates]

            contents = await client.read_resource(AnyUrl(f"erp://projects/{PROJECT_ID}/boq"))
            assert json.loads(contents.contents[0].text)["status"] == "ok"
            assert recorder.calls == [("get_boq_items", {"project_id": PROJECT_ID}, principal.user_id)]
            assert (await _audit_rows(session_factory))[0].details["via"] == "resource"

            with pytest.raises(Exception):  # noqa: B017, PT011 - SDK error type is not part of our contract
                await client.read_resource(AnyUrl("erp://secrets"))

    async def test_no_principal_means_no_access(self, session_factory, recorder, clean_hooks):
        server = build_mcp_server(_service(session_factory), lambda: None)
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool("get_all_projects", {})
            assert result.isError is True
            assert recorder.calls == []

    def test_resolve_resource(self):
        assert resolve_resource("erp://projects") == ("get_all_projects", {})
        assert resolve_resource(f"erp://projects/{PROJECT_ID}") == (
            "get_project_summary",
            {"project_id": PROJECT_ID},
        )
        assert resolve_resource(f"erp://projects/{PROJECT_ID}/validation") == (
            "get_validation_results",
            {"project_id": PROJECT_ID},
        )
        assert resolve_resource("erp://projects/not-a-uuid/boq") is None
        assert resolve_resource(f"erp://projects/{PROJECT_ID}/secrets") is None
        assert resolve_resource("file:///etc/passwd") is None


# ── HTTP endpoint ───────────────────────────────────────────────────────────


def _rpc(method: str, params: dict[str, Any] | None = None, rpc_id: int = 1) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest_asyncio.fixture
async def http(session_factory, recorder, clean_hooks):
    state = {"enabled": True}
    mcp_app = McpHttpApp(
        service=_service(session_factory),
        session_factory=session_factory,
        enabled_check=lambda: state["enabled"],
    )
    app = Starlette(routes=[Route("/mcp", endpoint=mcp_app)])
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, state
    await mcp_app.stop()


class TestHttpEndpoint:
    async def test_requires_api_key(self, http, session_factory):
        client, _ = http
        resp = await client.post("/mcp", json=_rpc("tools/list"), headers=_HEADERS)
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"].startswith("Bearer")

        resp = await client.post(
            "/mcp", json=_rpc("tools/list"), headers={**_HEADERS, "Authorization": "Bearer oe_wrong"}
        )
        assert resp.status_code == 401

    async def test_revoked_key_is_rejected(self, http, session_factory):
        client, _ = http
        _user, key = await _make_user(session_factory, "admin", key_active=False)
        resp = await client.post(
            "/mcp", json=_rpc("tools/list"), headers={**_HEADERS, "Authorization": f"Bearer {key}"}
        )
        assert resp.status_code == 401

    async def test_disabled_module_returns_404(self, http, session_factory):
        client, state = http
        _user, key = await _make_user(session_factory, "admin")
        state["enabled"] = False
        resp = await client.post(
            "/mcp", json=_rpc("tools/list"), headers={**_HEADERS, "Authorization": f"Bearer {key}"}
        )
        assert resp.status_code == 404

    async def test_full_round_trip_over_http(self, http, session_factory, recorder):
        client, _ = http
        user, key = await _make_user(session_factory, "editor")
        headers = {**_HEADERS, "Authorization": f"Bearer {key}"}

        init = await client.post(
            "/mcp",
            json=_rpc(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            ),
            headers=headers,
        )
        assert init.status_code == 200
        assert init.json()["result"]["serverInfo"]["name"] == "openconstructionerp"

        listed = await client.post("/mcp", json=_rpc("tools/list", rpc_id=2), headers=headers)
        assert listed.status_code == 200
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert {"get_all_projects", "create_boq_item"} <= names
        assert not names & set(registry.WITHHELD_TOOLS)

        proposed = await client.post(
            "/mcp",
            json=_rpc("tools/call", {"name": "create_boq_item", "arguments": BOQ_ARGS}, rpc_id=3),
            headers=headers,
        )
        assert proposed.json()["result"]["structuredContent"]["status"] == "proposal"
        assert recorder.calls == []

        done = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "create_boq_item", "arguments": {**BOQ_ARGS, "confirm": True}},
                rpc_id=4,
            ),
            headers={"Accept": _HEADERS["Accept"], "X-API-Key": key},
        )
        assert done.json()["result"]["structuredContent"]["status"] == "ok"
        assert recorder.calls == [("create_boq_item", BOQ_ARGS, str(user.id))]

        statuses = [r.details["status"] for r in await _audit_rows(session_factory)]
        assert statuses == ["proposal", "ok"]

    async def test_each_request_uses_its_own_key(self, http, session_factory, recorder):
        """Two callers on the same endpoint never see each other's identity."""
        client, _ = http
        viewer, viewer_key = await _make_user(session_factory, "viewer")
        editor, editor_key = await _make_user(session_factory, "editor")

        async def tool_names(key: str) -> set[str]:
            resp = await client.post(
                "/mcp", json=_rpc("tools/list"), headers={**_HEADERS, "Authorization": f"Bearer {key}"}
            )
            return {t["name"] for t in resp.json()["result"]["tools"]}

        assert "create_boq_item" in await tool_names(editor_key)
        assert "create_boq_item" not in await tool_names(viewer_key)

        await client.post(
            "/mcp",
            json=_rpc("tools/call", {"name": "get_all_projects", "arguments": {}}),
            headers={**_HEADERS, "Authorization": f"Bearer {viewer_key}"},
        )
        assert recorder.calls[-1][2] == str(viewer.id)


# ── Regression: chat handlers the MCP server exposes ────────────────────────


class TestValidationHandlers:
    """``ValidationReportRepository.list_for_project`` returns a plain list."""

    @pytest.fixture
    def fake_reports(self, monkeypatch):
        from types import SimpleNamespace

        from app.modules.validation import repository as validation_repository

        state: dict[str, Any] = {"reports": []}

        class FakeRepo:
            def __init__(self, session):
                pass

            async def list_for_project(self, project_id, *, target_type=None, limit=50):
                return list(state["reports"])[:limit]

        async def _allow(session, project_id, user_id):
            return None

        monkeypatch.setattr(validation_repository, "ValidationReportRepository", FakeRepo)
        monkeypatch.setattr(erp_tools, "_require_project_access", _allow)
        state["make"] = lambda status: SimpleNamespace(
            id=uuid.uuid4(),
            target_type="boq",
            target_id=uuid.uuid4(),
            rule_set="boq_quality",
            status=status,
            score=0.9,
            total_rules=3,
            passed_count=2,
            warning_count=1,
            error_count=0,
            created_at=datetime.now(UTC),
            results=[],
        )
        return state

    @pytest.mark.parametrize("handler_name", ["get_validation_results", "run_validation"])
    async def test_no_reports(self, fake_reports, handler_name):
        handler = erp_tools.TOOL_HANDLER_MAP[handler_name]
        result = await handler(None, {"project_id": PROJECT_ID}, "user")
        assert result["renderer"] != "error"

    @pytest.mark.parametrize("handler_name", ["get_validation_results", "run_validation"])
    async def test_with_reports(self, fake_reports, handler_name):
        fake_reports["reports"] = [fake_reports["make"]("passed"), fake_reports["make"]("warnings")]
        handler = erp_tools.TOOL_HANDLER_MAP[handler_name]
        result = await handler(None, {"project_id": PROJECT_ID}, "user")
        assert result["renderer"] != "error"
        assert result["data"]["total"] == 2
