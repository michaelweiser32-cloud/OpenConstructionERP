"""Access-control regression tests (fix/security-access-hardening).

Covers the three confirmed holes plus the project-scoping lead:

1. Project photos (file + thumbnail) require login, ``documents.read`` and
   project access; thumbnails are no longer publicly cacheable.
2. The iCalendar feed verifies the FULL API key hash (prefix-only tokens,
   revoked / expired keys and foreign projects are refused).
3. BCF / openCDE reads and writes are scoped to the caller's projects.
4. Project-scoped GET list endpoints refuse non-owners.

Users: a bootstrap admin, owner A and outsider B (both ``manager``, so
role permissions are never the reason for a refusal — only project
access is). Non-owners get **404**, the project-wide convention of
``verify_project_access`` (it does not confirm that a foreign project
UUID exists). All data is synthetic.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

# ── App + users ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()

    @asynccontextmanager
    async def lifespan_ctx():  # noqa: ANN202
        async with app.router.lifespan_context(app):
            yield

    async with lifespan_ctx():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.fixture(scope="module")
def photo_root(tmp_path_factory: pytest.TempPathFactory, client: AsyncClient) -> Iterator[Path]:
    """Keep photo files in a temp dir (patched after app start-up)."""
    import app.modules.documents.router as doc_router
    import app.modules.documents.service as doc_service

    base = tmp_path_factory.mktemp("photos-home") / ".openestimator"
    mp = pytest.MonkeyPatch()
    for mod in (doc_service, doc_router):
        mp.setattr(mod, "UPLOAD_BASE", base / "uploads")
        mp.setattr(mod, "PHOTO_BASE", base / "photos")
        mp.setattr(mod, "PHOTO_THUMB_BASE", base / "photos" / "thumbs")
    try:
        yield base
    finally:
        mp.undo()


async def _set_role(email: str, role: str) -> None:
    from app.database import async_session_factory
    from app.modules.users.models import User

    async with async_session_factory() as session:
        await session.execute(update(User).where(User.email == email.lower()).values(role=role))
        await session.commit()


async def _make_user(client: AsyncClient, tag: str, role: str) -> dict[str, str]:
    email = f"{tag}-{uuid.uuid4().hex[:8]}@example.com"
    password = f"Sec-{uuid.uuid4().hex[:10]}-Pw9"
    reg = await client.post(
        "/api/v1/users/auth/register",
        json={"email": email, "password": password, "full_name": f"Synthetic {tag}"},
    )
    assert reg.status_code == 201, reg.text
    await _set_role(email, role)
    login = await client.post("/api/v1/users/auth/login", json={"email": email, "password": password})
    token = login.json().get("access_token")
    assert token, login.text
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="module")
async def users(client: AsyncClient) -> dict[str, dict[str, str]]:
    admin = await _make_user(client, "sec-admin", "admin")
    owner = await _make_user(client, "sec-owner", "manager")
    other = await _make_user(client, "sec-other", "manager")
    return {"admin": admin, "owner": owner, "other": other}


@pytest_asyncio.fixture(scope="module")
async def project_id(client: AsyncClient, users: dict[str, dict[str, str]]) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        json={
            "name": f"Synthetic secure project {uuid.uuid4().hex[:6]}",
            "description": "synthetic",
            "region": "DACH",
            "classification_standard": "din276",
            "currency": "EUR",
        },
        headers=users["owner"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _png() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (64, 40), (200, 60, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── 1. Photos ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def photo(
    client: AsyncClient, users: dict[str, dict[str, str]], project_id: str, photo_root: Path
) -> dict[str, object]:
    content = _png()
    resp = await client.post(
        "/api/v1/documents/photos/upload/",
        params={"project_id": project_id},
        data={"category": "site"},
        files={"file": ("private-site.png", io.BytesIO(content), "image/png")},
        headers=users["owner"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["has_thumbnail"] is True
    return {"id": body["id"], "bytes": content}


class TestPhotoAccess:
    @pytest.mark.parametrize("kind", ["file", "thumb"])
    async def test_anonymous_is_rejected(self, client: AsyncClient, photo: dict[str, object], kind: str) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/{kind}/")
        assert resp.status_code == 401
        assert resp.content[:4] != b"\x89PNG"

    @pytest.mark.parametrize("kind", ["file", "thumb"])
    async def test_garbage_token_is_rejected(self, client: AsyncClient, photo: dict[str, object], kind: str) -> None:
        resp = await client.get(
            f"/api/v1/documents/photos/{photo['id']}/{kind}/",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.parametrize("kind", ["file", "thumb"])
    async def test_non_member_is_refused(
        self, client: AsyncClient, users: dict[str, dict[str, str]], photo: dict[str, object], kind: str
    ) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/{kind}/", headers=users["other"])
        assert resp.status_code == 404  # verify_project_access convention (no existence leak)
        assert resp.content[:4] != b"\x89PNG"
        assert resp.content[:3] != b"\xff\xd8\xff"

    async def test_member_gets_exact_file(
        self, client: AsyncClient, users: dict[str, dict[str, str]], photo: dict[str, object]
    ) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/file/", headers=users["owner"])
        assert resp.status_code == 200
        assert resp.content == photo["bytes"]
        assert resp.headers["content-type"] == "image/png"

    async def test_member_gets_thumbnail_privately_cacheable(
        self, client: AsyncClient, users: dict[str, dict[str, str]], photo: dict[str, object]
    ) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/thumb/", headers=users["owner"])
        assert resp.status_code == 200
        assert resp.content[:3] == b"\xff\xd8\xff"  # JPEG thumbnail
        cache = resp.headers.get("cache-control", "")
        assert "public" not in cache
        assert "private" in cache

    async def test_admin_still_has_access(
        self, client: AsyncClient, users: dict[str, dict[str, str]], photo: dict[str, object]
    ) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/file/", headers=users["admin"])
        assert resp.status_code == 200

    async def test_unknown_photo_is_404_for_member(self, client: AsyncClient, users: dict[str, dict[str, str]]) -> None:
        resp = await client.get(f"/api/v1/documents/photos/{uuid.uuid4()}/file/", headers=users["owner"])
        assert resp.status_code == 404


# ── 2. Calendar feed ──────────────────────────────────────────────────────


async def _new_api_key(client: AsyncClient, headers: dict[str, str]) -> dict[str, str]:
    resp = await client.post("/api/v1/users/me/api-keys/", json={"name": "synthetic calendar"}, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"id": body["id"], "key": body["key"]}


def _ics(project_id: str) -> str:
    return f"/api/v1/integrations/calendar/{project_id}.ics/"


class TestCalendarFeed:
    async def test_full_key_returns_calendar(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        key = await _new_api_key(client, users["owner"])
        resp = await client.get(_ics(project_id), params={"token": key["key"]})
        assert resp.status_code == 200, resp.text
        assert resp.text.startswith("BEGIN:VCALENDAR")
        assert "END:VCALENDAR" in resp.text

    @pytest.mark.parametrize(
        "mangle",
        [
            lambda k: k[:8],  # the old 8-char prefix
            lambda k: k[:12],  # the stored key_prefix
            lambda k: k[:12] + "x" * (len(k) - 12),  # right prefix, wrong remainder
            lambda k: k[:-1] + ("A" if k[-1] != "A" else "B"),  # one char off
            lambda k: k + "x",
        ],
        ids=["prefix8", "prefix12", "prefix-wrong-rest", "last-char", "extra-char"],
    )
    async def test_anything_but_the_full_key_is_rejected(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str, mangle
    ) -> None:  # noqa: ANN001
        key = await _new_api_key(client, users["owner"])
        resp = await client.get(_ics(project_id), params={"token": mangle(key["key"])})
        assert resp.status_code == 401
        assert "VCALENDAR" not in resp.text

    async def test_legacy_8_char_prefix_row_is_not_enough(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        """The exact old hole: a key row whose key_prefix is 8 chars long."""
        from app.database import async_session_factory
        from app.modules.users.models import APIKey, User

        key = await _new_api_key(client, users["owner"])  # gives us the owner's user id via DB
        async with async_session_factory() as session:
            real = await session.get(APIKey, uuid.UUID(key["id"]))
            owner = await session.get(User, real.user_id)
            legacy_secret = "oe_LEGACY_" + uuid.uuid4().hex
            session.add(
                APIKey(
                    user_id=owner.id,
                    name="synthetic legacy",
                    key_hash=hashlib.sha256(legacy_secret.encode()).hexdigest(),
                    key_prefix=legacy_secret[:8],
                    is_active=True,
                )
            )
            await session.commit()
        attack = legacy_secret[:8] + "guessed-remainder"
        resp = await client.get(_ics(project_id), params={"token": attack})
        assert resp.status_code == 401
        ok = await client.get(_ics(project_id), params={"token": legacy_secret})
        assert ok.status_code == 200

    async def test_revoked_key_is_rejected(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        key = await _new_api_key(client, users["owner"])
        revoke = await client.delete(f"/api/v1/users/me/api-keys/{key['id']}", headers=users["owner"])
        assert revoke.status_code == 204
        resp = await client.get(_ics(project_id), params={"token": key["key"]})
        assert resp.status_code == 401

    async def test_inactive_key_is_rejected(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        from app.database import async_session_factory
        from app.modules.users.models import APIKey

        key = await _new_api_key(client, users["owner"])
        async with async_session_factory() as session:
            await session.execute(update(APIKey).where(APIKey.id == uuid.UUID(key["id"])).values(is_active=False))
            await session.commit()
        resp = await client.get(_ics(project_id), params={"token": key["key"]})
        assert resp.status_code == 401

    async def test_expired_key_is_rejected(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        from app.database import async_session_factory
        from app.modules.users.models import APIKey

        key = await _new_api_key(client, users["owner"])
        async with async_session_factory() as session:
            await session.execute(
                update(APIKey)
                .where(APIKey.id == uuid.UUID(key["id"]))
                .values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
            )
            await session.commit()
        resp = await client.get(_ics(project_id), params={"token": key["key"]})
        assert resp.status_code == 401

    async def test_valid_key_of_another_user_cannot_read_the_project(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        key = await _new_api_key(client, users["other"])
        resp = await client.get(_ics(project_id), params={"token": key["key"]})
        assert resp.status_code == 404
        assert "VCALENDAR" not in resp.text

    async def test_missing_token_is_rejected(self, client: AsyncClient, project_id: str) -> None:
        resp = await client.get(_ics(project_id))
        assert resp.status_code in (401, 422)


# ── 3. BCF / openCDE ──────────────────────────────────────────────────────

BCF = "/api/v1/opencde/bcf/3.0"


@pytest_asyncio.fixture(scope="module")
async def bcf_topic(client: AsyncClient, users: dict[str, dict[str, str]], project_id: str) -> str:
    resp = await client.post(
        f"{BCF}/projects/{project_id}/topics/",
        json={"title": "Synthetic clash", "description": "synthetic"},
        headers=users["owner"],
    )
    assert resp.status_code == 201, resp.text
    guid = resp.json()["guid"]
    com = await client.post(
        f"{BCF}/projects/{project_id}/topics/{guid}/comments/",
        json={"comment": "synthetic comment"},
        headers=users["owner"],
    )
    assert com.status_code == 201, com.text
    return guid


class TestBcfScoping:
    async def test_list_projects_only_shows_own(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str
    ) -> None:
        own = await client.get(f"{BCF}/projects/", headers=users["owner"])
        assert own.status_code == 200
        assert project_id in {p["project_id"] for p in own.json()}
        foreign = await client.get(f"{BCF}/projects/", headers=users["other"])
        assert foreign.status_code == 200
        assert project_id not in {p["project_id"] for p in foreign.json()}
        admin = await client.get(f"{BCF}/projects/", headers=users["admin"])
        assert project_id in {p["project_id"] for p in admin.json()}

    async def test_owner_can_read_everything(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str, bcf_topic: str
    ) -> None:
        for path in (
            f"/projects/{project_id}",
            f"/projects/{project_id}/topics/",
            f"/projects/{project_id}/topics/{bcf_topic}",
            f"/projects/{project_id}/topics/{bcf_topic}/comments/",
            f"/projects/{project_id}/topics/{bcf_topic}/viewpoints/",
        ):
            resp = await client.get(BCF + path, headers=users["owner"])
            assert resp.status_code == 200, (path, resp.text)

    @pytest.mark.parametrize(
        "path",
        [
            "/projects/{p}",
            "/projects/{p}/topics/",
            "/projects/{p}/topics/{t}",
            "/projects/{p}/topics/{t}/comments/",
            "/projects/{p}/topics/{t}/viewpoints/",
        ],
    )
    async def test_other_user_cannot_read(
        self,
        client: AsyncClient,
        users: dict[str, dict[str, str]],
        project_id: str,
        bcf_topic: str,
        path: str,
    ) -> None:
        resp = await client.get(BCF + path.format(p=project_id, t=bcf_topic), headers=users["other"])
        assert resp.status_code == 404
        assert "Synthetic clash" not in resp.text
        assert "synthetic comment" not in resp.text

    async def test_other_user_cannot_write(
        self, client: AsyncClient, users: dict[str, dict[str, str]], project_id: str, bcf_topic: str
    ) -> None:
        topic = await client.post(
            f"{BCF}/projects/{project_id}/topics/", json={"title": "intruder"}, headers=users["other"]
        )
        assert topic.status_code == 404
        update_ = await client.put(
            f"{BCF}/projects/{project_id}/topics/{bcf_topic}", json={"title": "hijacked"}, headers=users["other"]
        )
        assert update_.status_code == 404
        comment = await client.post(
            f"{BCF}/projects/{project_id}/topics/{bcf_topic}/comments/",
            json={"comment": "intruder"},
            headers=users["other"],
        )
        assert comment.status_code == 404
        still = await client.get(f"{BCF}/projects/{project_id}/topics/{bcf_topic}", headers=users["owner"])
        assert still.json()["title"] == "Synthetic clash"

    async def test_anonymous_is_rejected(self, client: AsyncClient, project_id: str) -> None:
        assert (await client.get(f"{BCF}/projects/")).status_code == 401
        assert (await client.get(f"{BCF}/projects/{project_id}/topics/")).status_code == 401


# ── 4. Project-scoped list endpoints ──────────────────────────────────────

# (path, project_id in path?) — every GET list/summary endpoint that took a
# project_id without checking access before this branch.
SCOPED_ROUTES = [
    ("/api/v1/assemblies/", False),
    ("/api/v1/bim_hub/coverage-summary/", False),
    ("/api/v1/bim_requirements/sets/", False),
    ("/api/v1/boq/projects/{p}/activity/", True),
    ("/api/v1/cde/containers/", False),
    ("/api/v1/cde/stats/", False),
    ("/api/v1/changeorders/", False),
    ("/api/v1/changeorders/summary/", False),
    ("/api/v1/costmodel/projects/{p}/5d/budget-lines/", True),
    ("/api/v1/costmodel/projects/{p}/5d/budget/", True),
    ("/api/v1/costmodel/projects/{p}/5d/cash-flow/", True),
    ("/api/v1/costmodel/projects/{p}/5d/dashboard/", True),
    ("/api/v1/costmodel/projects/{p}/5d/evm/", True),
    ("/api/v1/costmodel/projects/{p}/5d/s-curve/", True),
    ("/api/v1/costmodel/projects/{p}/5d/snapshots/", True),
    ("/api/v1/dwg_takeoff/drawings/", False),
    ("/api/v1/enterprise_workflows/", False),
    ("/api/v1/markups/", False),
    ("/api/v1/markups/export/", False),
    ("/api/v1/markups/stamps/templates/", False),
    ("/api/v1/markups/summary/", False),
    ("/api/v1/procurement/", False),
    ("/api/v1/procurement/stats/", False),
    ("/api/v1/requirements/", False),
    ("/api/v1/requirements/stats/", False),
    ("/api/v1/risk/", False),
    ("/api/v1/risk/matrix/", False),
    ("/api/v1/risk/summary/", False),
    ("/api/v1/takeoff/cad-data/sessions/", False),
    ("/api/v1/takeoff/documents/", False),
    ("/api/v1/takeoff/measurements/", False),
    ("/api/v1/takeoff/measurements/export/", False),
    ("/api/v1/takeoff/measurements/summary/", False),
    ("/api/v1/teams/", False),
    ("/api/v1/teams/project/{p}", True),
]


class TestProjectScopedLists:
    @pytest.mark.parametrize(("path", "in_path"), SCOPED_ROUTES, ids=[r[0] for r in SCOPED_ROUTES])
    async def test_non_owner_is_refused_owner_is_not(
        self,
        client: AsyncClient,
        users: dict[str, dict[str, str]],
        project_id: str,
        path: str,
        in_path: bool,
    ) -> None:
        url = path.format(p=project_id)
        params = {} if in_path else {"project_id": project_id}
        other = await client.get(url, params=params, headers=users["other"])
        assert other.status_code == 404, (url, other.status_code, other.text[:200])
        owner = await client.get(url, params=params, headers=users["owner"])
        assert owner.status_code == 200, (url, owner.status_code, owner.text[:200])
