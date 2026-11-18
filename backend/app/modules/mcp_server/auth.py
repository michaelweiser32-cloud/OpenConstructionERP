"""API-key authentication for the MCP endpoint.

An MCP client authenticates with a regular OpenConstructionERP API key
(``oe_...``, created under *Settings -> API keys*).  The key is resolved to
its owning user; role and permissions are always re-read from the database,
never taken from the request.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Role, _resolve_role, permission_registry
from app.modules.users.models import APIKey, User
from app.modules.users.repository import APIKeyRepository

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "oe_"
_MAX_KEY_LENGTH = 256


@dataclass(frozen=True)
class McpPrincipal:
    """The authenticated caller of an MCP request."""

    user_id: str
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_admin: bool = False
    api_key_id: str | None = None
    api_key_prefix: str | None = None

    def can(self, permission: str) -> bool:
        """Return True if this caller may use a tool guarded by ``permission``."""
        return self.is_admin or permission in self.permissions

    @property
    def rate_limit_key(self) -> str:
        """Stable key for per-caller rate limiting."""
        return self.api_key_id or self.user_id


def extract_api_key(headers: dict[str, str]) -> str | None:
    """Pull an API key from lower-cased request headers.

    Accepts ``Authorization: Bearer <key>`` or ``X-API-Key: <key>``.
    """
    auth = headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
        if token:
            return token
    key = headers.get("x-api-key", "").strip()
    return key or None


def build_principal(user: User, api_key: APIKey | None = None) -> McpPrincipal:
    """Build a principal from DB state.

    A key with an explicit ``permissions`` list is a *scoped* key: it can only
    do what is both on its list and allowed for the user's role, and it never
    gets the admin bypass.
    """
    role_permissions = set(permission_registry.get_role_permissions(user.role))
    is_admin = _resolve_role(user.role) == Role.ADMIN

    scoped = [p for p in (api_key.permissions or []) if isinstance(p, str)] if api_key else []
    if scoped:
        permissions = set(scoped) if is_admin else role_permissions & set(scoped)
        is_admin = False
    else:
        permissions = role_permissions

    return McpPrincipal(
        user_id=str(user.id),
        role=user.role,
        permissions=frozenset(permissions),
        is_admin=is_admin,
        api_key_id=str(api_key.id) if api_key else None,
        api_key_prefix=api_key.key_prefix if api_key else None,
    )


async def authenticate_api_key(session: AsyncSession, raw_key: str | None) -> McpPrincipal | None:
    """Resolve a raw API key to a principal, or None if it is not valid.

    Rejects unknown, revoked and expired keys and keys of inactive users.
    Updates ``last_used_at`` on success (flushed, not committed).
    """
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX) or len(raw_key) > _MAX_KEY_LENGTH:
        return None

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key = await APIKeyRepository(session).get_by_hash(key_hash)
    if api_key is None:
        return None

    now = datetime.now(UTC)
    if api_key.expires_at is not None:
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:  # SQLite returns naive datetimes
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            return None

    user = await session.get(User, api_key.user_id)
    if user is None or not user.is_active:
        return None

    api_key.last_used_at = now
    await session.flush()
    return build_principal(user, api_key)
