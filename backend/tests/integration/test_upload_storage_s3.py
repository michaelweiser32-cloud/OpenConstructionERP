"""End-to-end durability of every upload type, local disk vs. S3 bucket.

Runs the full FastAPI app (lifespan, routers, auth) and drives each upload
consumer through its real HTTP API:

    documents · photos + thumbnails · PDF sheets (+ page thumbnails) ·
    meeting transcripts · takeoff PDFs · DWG/DXF drawings (+ entities,
    SVG thumbnail) · punch-list photos

Each scenario runs twice:

* ``local`` — STORAGE_BACKEND=local: the file must land at exactly the
  historical path on disk and nothing may be written to the bucket.
* ``s3`` — STORAGE_BACKEND=s3 against a local fake S3 (moto server on
  127.0.0.1, dummy credentials, never a real account): the file must be
  in the bucket and NOT on local disk; then a *simulated restart* (fresh
  storage-backend instance + the local upload directories wiped, as on a
  Render redeploy) must still serve the exact bytes; deleting through the
  API must remove the object; and a blob missing from the bucket must give
  a clean 404, not a 500.

All file contents are synthetic and generated in the test.
"""

from __future__ import annotations

import io
import os
import shutil
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytest.importorskip("aioboto3", reason="needs aioboto3")
moto_server = pytest.importorskip("moto.server", reason="needs moto[server]")

from app.config import get_settings  # noqa: E402
from app.core.storage import reset_storage_backend_cache  # noqa: E402
from tests.integration._auth_helpers import promote_to_admin  # noqa: E402

_DUMMY_KEY = "testing"
_REGION = "us-east-1"
MODES = ["local", "s3"]


# ── Synthetic payloads ────────────────────────────────────────────────────


def _png_bytes(width: int = 96, height: int = 64) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), (40, 120, 200))
    for x in range(width):
        img.putpixel((x, x % height), (255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _pdf_bytes(pages: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    for text in pages:
        c.setFont("Helvetica", 14)
        c.drawString(72, 760, text)
        c.drawString(72, 740, "Synthetic test drawing - not real project data")
        c.line(72, 700, 400, 500)
        c.showPage()
    c.save()
    return out.getvalue()


def _dxf_bytes() -> bytes:
    import ezdxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    doc.layers.add("WALLS")
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "WALLS"})
    msp.add_line((10, 0), (10, 5), dxfattribs={"layer": "WALLS"})
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


# ── Fake S3 + isolated local directories ──────────────────────────────────


def _admin(endpoint: str):  # noqa: ANN202 — boto3 client
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=_DUMMY_KEY,
        aws_secret_access_key=_DUMMY_KEY,
        region_name=_REGION,
    )


@pytest.fixture(scope="module")
def fake_s3() -> Iterator[tuple[str, str]]:
    saved = {k: v for k, v in os.environ.items() if k.startswith("AWS_")}
    for k in saved:
        del os.environ[k]
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    endpoint = f"http://{host}:{port}"
    bucket = f"oe-uploads-{uuid.uuid4().hex[:10]}"
    _admin(endpoint).create_bucket(Bucket=bucket)
    try:
        yield endpoint, bucket
    finally:
        server.stop()
        os.environ.pop("AWS_EC2_METADATA_DISABLED", None)
        os.environ.update(saved)


@pytest.fixture(scope="module")
def roots(tmp_path_factory: pytest.TempPathFactory, client: AsyncClient) -> Iterator[dict[str, Path]]:
    """Point every historical upload directory at a private temp tree.

    Applied AFTER app startup: the module loader reloads router modules on
    startup, which would reset module-level constants patched earlier.
    """
    import app.modules.documents.router as doc_router
    import app.modules.documents.service as doc_service
    import app.modules.punchlist.router as punch_router
    import app.modules.takeoff.service as takeoff_service

    base = tmp_path_factory.mktemp("upload-roots")
    home = base / "home"
    oe = home / ".openestimator"
    data = base / "data"
    punch = base / "cwd" / "uploads" / "punchlist" / "photos"
    paths = {
        "home": home,
        "uploads": oe / "uploads",
        "photos": oe / "photos",
        "thumbs": oe / "photos" / "thumbs",
        "sheets": oe / "sheets",
        "takeoff": oe / "takeoff_documents",
        "punch": punch,
        "data": data,
    }
    mp = pytest.MonkeyPatch()
    mp.setenv("HOME", str(home))
    mp.setenv("DATA_DIR", str(data))
    for mod in (doc_service, doc_router):
        mp.setattr(mod, "UPLOAD_BASE", paths["uploads"])
        mp.setattr(mod, "PHOTO_BASE", paths["photos"])
        mp.setattr(mod, "PHOTO_THUMB_BASE", paths["thumbs"])
    mp.setattr(doc_service, "SHEET_THUMB_BASE", paths["sheets"])
    mp.setattr(takeoff_service, "_TAKEOFF_DOCUMENTS_DIR", paths["takeoff"])
    mp.setattr(punch_router, "PHOTOS_DIR", punch)
    try:
        yield paths
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def s3_settings(fake_s3: tuple[str, str]) -> Iterator[None]:
    endpoint, bucket = fake_s3
    settings = get_settings()
    fields = (
        "storage_backend",
        "s3_endpoint",
        "s3_access_key",
        "s3_secret_key",
        "s3_bucket",
        "s3_region",
        "s3_presigned_downloads",
    )
    original = {f: getattr(settings, f) for f in fields}
    settings.storage_backend = "s3"
    settings.s3_endpoint = endpoint
    settings.s3_access_key = _DUMMY_KEY
    settings.s3_secret_key = _DUMMY_KEY
    settings.s3_bucket = bucket
    settings.s3_region = _REGION
    settings.s3_presigned_downloads = False
    reset_storage_backend_cache()
    try:
        yield
    finally:
        for f, v in original.items():
            setattr(settings, f, v)
        reset_storage_backend_cache()


@pytest_asyncio.fixture(scope="module")
async def client(s3_settings: None) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()

    @asynccontextmanager
    async def lifespan_ctx():  # noqa: ANN202
        async with app.router.lifespan_context(app):
            yield

    async with lifespan_ctx():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture(scope="module")
async def auth(client: AsyncClient) -> dict[str, str]:
    unique = uuid.uuid4().hex[:8]
    email = f"uploads-{unique}@example.com"
    password = f"Uploads-{unique}-Pw9"
    reg = await client.post(
        "/api/v1/users/auth/register",
        json={"email": email, "password": password, "full_name": "Upload Storage Tester"},
    )
    assert reg.status_code == 201, reg.text
    await promote_to_admin(email)
    login = await client.post("/api/v1/users/auth/login", json={"email": email, "password": password})
    token = login.json().get("access_token")
    assert token, login.text
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="module")
async def project_id(client: AsyncClient, auth: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/projects/",
        json={
            "name": f"Upload storage test {uuid.uuid4().hex[:6]}",
            "description": "Synthetic project for upload storage tests",
            "region": "DACH",
            "classification_standard": "din276",
            "currency": "EUR",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(params=MODES)
def mode(request: pytest.FixtureRequest, roots: dict[str, Path]) -> Iterator[str]:
    """Run the test once per storage backend (settings are read per call)."""
    settings = get_settings()
    previous = settings.storage_backend
    settings.storage_backend = request.param
    reset_storage_backend_cache()
    try:
        yield request.param
    finally:
        settings.storage_backend = previous
        reset_storage_backend_cache()


# ── Helpers ───────────────────────────────────────────────────────────────


class Bucket:
    def __init__(self, endpoint: str, name: str) -> None:
        self.endpoint = endpoint
        self.name = name
        self.client = _admin(endpoint)

    def keys(self, prefix: str) -> set[str]:
        resp = self.client.list_objects_v2(Bucket=self.name, Prefix=prefix)
        return {o["Key"] for o in resp.get("Contents", [])}

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.name, Key=key)["Body"].read()

    def remove(self, key: str) -> None:
        self.client.delete_object(Bucket=self.name, Key=key)

    def assert_private(self, key: str) -> None:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"{self.endpoint}/{self.name}/{key}", timeout=10)  # noqa: S310
        assert excinfo.value.code == 403


@pytest.fixture(scope="module")
def bucket(fake_s3: tuple[str, str]) -> Bucket:
    return Bucket(*fake_s3)


def _files_under(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()] if path.exists() else []


def simulate_restart(mode: str, roots: dict[str, Path]) -> None:
    """New storage backend instance; on S3 also wipe the local disk."""
    reset_storage_backend_cache()
    if mode == "s3":
        for key in ("uploads", "photos", "sheets", "takeoff", "punch", "data"):
            shutil.rmtree(roots[key], ignore_errors=True)


def _single_new(keys_after: set[str], keys_before: set[str]) -> str:
    new = keys_after - keys_before
    assert len(new) == 1, f"expected exactly one new object, got {sorted(new)}"
    return new.pop()


# ── Tests ─────────────────────────────────────────────────────────────────


class TestDocuments:
    async def test_document_upload_restart_download_delete(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        content = f"Synthetic site notes {uuid.uuid4().hex}\n".encode() * 50
        prefix = f"uploads/{project_id}/"
        before = bucket.keys(prefix)

        up = await client.post(
            "/api/v1/documents/upload/",
            params={"project_id": project_id, "category": "other"},
            files={"file": ("site-notes.txt", io.BytesIO(content), "text/plain")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        doc_id = up.json()["id"]
        local_files = [p for p in _files_under(roots["uploads"] / project_id) if p.name.endswith("site-notes.txt")]

        if mode == "local":
            assert len(local_files) == 1
            assert local_files[0].read_bytes() == content
            assert bucket.keys(prefix) == before
        else:
            key = _single_new(bucket.keys(prefix), before)
            assert bucket.get(key) == content
            assert local_files == []
            bucket.assert_private(key)

        simulate_restart(mode, roots)

        dl = await client.get(f"/api/v1/documents/{doc_id}/download/", headers=auth)
        assert dl.status_code == 200, dl.text
        assert dl.content == content
        assert 'filename="site-notes.txt"' in dl.headers.get("content-disposition", "")

        dele = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            assert bucket.keys(prefix) == before
        else:
            assert not local_files[0].exists()

    async def test_missing_document_blob_is_a_clean_404(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        bucket: Bucket,
        roots: dict[str, Path],
    ) -> None:
        prefix = f"uploads/{project_id}/"
        before = bucket.keys(prefix)
        up = await client.post(
            "/api/v1/documents/upload/",
            params={"project_id": project_id},
            files={"file": ("lost.txt", io.BytesIO(b"synthetic"), "text/plain")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        if mode == "s3":
            bucket.remove(_single_new(bucket.keys(prefix), before))
        else:
            for p in _files_under(roots["uploads"] / project_id):
                if p.name.endswith("lost.txt"):
                    p.unlink()
        dl = await client.get(f"/api/v1/documents/{up.json()['id']}/download/", headers=auth)
        assert dl.status_code == 404


class TestPhotos:
    async def test_photo_and_thumbnail_survive_restart(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        png = _png_bytes()
        photo_prefix = f"photos/{project_id}/"
        thumb_prefix = f"photos/thumbs/{project_id}/"
        before_photo, before_thumb = bucket.keys(photo_prefix), bucket.keys(thumb_prefix)

        up = await client.post(
            "/api/v1/documents/photos/upload/",
            params={"project_id": project_id},
            data={"category": "site", "caption": "synthetic"},
            files={"file": ("facade.png", io.BytesIO(png), "image/png")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        photo = up.json()
        assert photo["has_thumbnail"] is True

        local_photo = [p for p in _files_under(roots["photos"] / project_id) if p.name.endswith("facade.png")]
        if mode == "local":
            assert len(local_photo) == 1
            assert local_photo[0].read_bytes() == png
            assert len(_files_under(roots["thumbs"] / project_id)) >= 1
            assert bucket.keys(photo_prefix) == before_photo
        else:
            photo_key = _single_new(bucket.keys(photo_prefix), before_photo)
            thumb_key = _single_new(bucket.keys(thumb_prefix), before_thumb)
            assert bucket.get(photo_key) == png
            assert bucket.get(thumb_key)[:3] == b"\xff\xd8\xff"  # JPEG thumbnail
            assert _files_under(roots["photos"]) == []
            bucket.assert_private(photo_key)

        simulate_restart(mode, roots)

        full = await client.get(f"/api/v1/documents/photos/{photo['id']}/file/", headers=auth)
        assert full.status_code == 200, full.text
        assert full.content == png
        assert full.headers["content-type"] == "image/png"
        thumb = await client.get(f"/api/v1/documents/photos/{photo['id']}/thumb/", headers=auth)
        assert thumb.status_code == 200
        assert thumb.headers["content-type"] == "image/jpeg"
        assert thumb.content[:3] == b"\xff\xd8\xff"
        assert thumb.headers["cache-control"] == "private, max-age=86400"

        dele = await client.delete(f"/api/v1/documents/photos/{photo['id']}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            assert bucket.keys(photo_prefix) == before_photo
            assert bucket.keys(thumb_prefix) == before_thumb
        else:
            assert not local_photo[0].exists()

    async def test_missing_photo_blob_is_a_clean_404(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        bucket: Bucket,
        roots: dict[str, Path],
    ) -> None:
        up = await client.post(
            "/api/v1/documents/photos/upload/",
            params={"project_id": project_id},
            files={"file": ("gone.png", io.BytesIO(_png_bytes(20, 20)), "image/png")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        photo = up.json()
        # Remove the original and every thumbnail behind the app's back.
        if mode == "s3":
            for key in bucket.keys(f"photos/{project_id}/") | bucket.keys(f"photos/thumbs/{project_id}/"):
                if key.endswith("gone.png") or key.endswith("_thumb.jpg"):
                    bucket.remove(key)
        else:
            for p in _files_under(roots["photos"] / project_id) + _files_under(roots["thumbs"] / project_id):
                if p.name.endswith("gone.png") or p.name.endswith("_thumb.jpg"):
                    p.unlink()
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/file/", headers=auth)
        assert resp.status_code == 404
        resp = await client.get(f"/api/v1/documents/photos/{photo['id']}/thumb/", headers=auth)
        assert resp.status_code == 404


class TestSheets:
    async def test_split_pdf_pages_and_thumbnails_survive_restart(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        pdf = _pdf_bytes(["A-101 Ground floor plan", "S-201 Foundation plan"])
        before_pdf = bucket.keys(f"uploads/{project_id}/")
        before_thumbs = bucket.keys(f"sheets/{project_id}/")

        resp = await client.post(
            "/api/v1/documents/sheets/split-pdf/",
            params={"project_id": project_id},
            files={"file": ("plans.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=auth,
        )
        assert resp.status_code == 201, resp.text
        sheets = resp.json()
        assert len(sheets) == 2
        document_id = sheets[0]["document_id"]
        thumbs = [s["thumbnail_path"] for s in sheets]
        assert all(thumbs), "every page should get a thumbnail"

        if mode == "local":
            assert all(Path(t).is_file() for t in thumbs)
            assert bucket.keys(f"sheets/{project_id}/") == before_thumbs
        else:
            new_thumbs = bucket.keys(f"sheets/{project_id}/") - before_thumbs
            assert len(new_thumbs) == 2
            assert all(bucket.get(k)[:8] == b"\x89PNG\r\n\x1a\n" for k in new_thumbs)
            assert bucket.get(_single_new(bucket.keys(f"uploads/{project_id}/"), before_pdf)) == pdf
            assert not any(Path(t).exists() for t in thumbs)

        simulate_restart(mode, roots)

        dl = await client.get(f"/api/v1/documents/{document_id}/download/", headers=auth)
        assert dl.status_code == 200, dl.text
        assert dl.content == pdf

        dele = await client.delete(f"/api/v1/documents/{document_id}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            assert bucket.keys(f"uploads/{project_id}/") == before_pdf


class TestMeetingTranscripts:
    async def test_transcript_survives_restart(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        transcript = (
            "Meeting: Synthetic coordination meeting\n"
            "Attendees: Alice Example, Bob Example\n"
            "Action item: Bob to update the synthetic schedule\n"
            f"Ref {uuid.uuid4().hex}\n"
        ).encode()
        prefix = f"uploads/{project_id}/"
        before = bucket.keys(prefix)

        resp = await client.post(
            "/api/v1/meetings/import-summary/",
            params={"project_id": project_id},
            files={"file": ("standup.txt", io.BytesIO(transcript), "text/plain")},
            headers=auth,
        )
        assert resp.status_code in (200, 201), resp.text

        docs = await client.get("/api/v1/documents/", params={"project_id": project_id}, headers=auth)
        assert docs.status_code == 200
        matches = [d for d in docs.json() if d["name"] == "standup.txt"]
        assert matches, "transcript should be cross-linked into the Documents hub"
        doc_id = matches[-1]["id"]

        if mode == "s3":
            key = _single_new(bucket.keys(prefix), before)
            assert bucket.get(key) == transcript
            assert not [p for p in _files_under(roots["uploads"]) if p.name.endswith("standup.txt")]
        else:
            assert [p for p in _files_under(roots["uploads"] / project_id) if p.name.endswith("standup.txt")]
            assert bucket.keys(prefix) == before

        simulate_restart(mode, roots)

        dl = await client.get(f"/api/v1/documents/{doc_id}/download/", headers=auth)
        assert dl.status_code == 200, dl.text
        assert dl.content == transcript

        dele = await client.delete(f"/api/v1/documents/{doc_id}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            assert bucket.keys(prefix) == before


class TestTakeoffPdfs:
    async def test_takeoff_pdf_upload_restart_download_delete(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        pdf = _pdf_bytes(["Takeoff sheet 1 - synthetic"])
        before = bucket.keys("takeoff_documents/")

        up = await client.post(
            "/api/v1/takeoff/documents/upload/",
            params={"project_id": project_id},
            files={"file": ("takeoff.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        doc_id = up.json()["id"]
        local_pdf = roots["takeoff"] / f"{doc_id}.pdf"

        if mode == "local":
            assert local_pdf.read_bytes() == pdf
            assert bucket.keys("takeoff_documents/") == before
        else:
            key = _single_new(bucket.keys("takeoff_documents/"), before)
            assert key == f"takeoff_documents/{doc_id}.pdf"
            assert bucket.get(key) == pdf
            assert not local_pdf.exists()
            bucket.assert_private(key)

        simulate_restart(mode, roots)

        dl = await client.get(f"/api/v1/takeoff/documents/{doc_id}/download/", headers=auth)
        assert dl.status_code == 200, dl.text
        assert dl.content == pdf
        assert dl.headers["content-type"] == "application/pdf"

        dele = await client.delete(f"/api/v1/takeoff/documents/{doc_id}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            assert bucket.keys("takeoff_documents/") == before
        else:
            assert not local_pdf.exists()
        gone = await client.get(f"/api/v1/takeoff/documents/{doc_id}/download/", headers=auth)
        assert gone.status_code == 404

    async def test_missing_takeoff_blob_is_a_clean_404(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        up = await client.post(
            "/api/v1/takeoff/documents/upload/",
            params={"project_id": project_id},
            files={"file": ("t2.pdf", io.BytesIO(_pdf_bytes(["x"])), "application/pdf")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        doc_id = up.json()["id"]
        if mode == "s3":
            bucket.remove(f"takeoff_documents/{doc_id}.pdf")
        else:
            (roots["takeoff"] / f"{doc_id}.pdf").unlink()
        dl = await client.get(f"/api/v1/takeoff/documents/{doc_id}/download/", headers=auth)
        assert dl.status_code == 404


class TestDwgDrawings:
    async def test_dxf_drawing_entities_thumbnail_survive_restart(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        pytest.importorskip("ezdxf")
        dxf = _dxf_bytes()
        up = await client.post(
            "/api/v1/dwg_takeoff/drawings/upload/",
            params={"project_id": project_id, "name": "Synthetic plan"},
            files={"file": ("plan.dxf", io.BytesIO(dxf), "application/dxf")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        drawing = up.json()
        drawing_id = drawing["id"]
        assert drawing["status"] == "ready", drawing

        expected = {
            "dwg_entities/": f"dwg_entities/{drawing_id}/entities.json",
            "dwg_thumbnails/": f"dwg_thumbnails/{drawing_id}/thumbnail.svg",
        }
        if mode == "s3":
            uploads = {k for k in bucket.keys("dwg_uploads/") if k.endswith(".dxf")}
            assert any(bucket.get(k) == dxf for k in uploads)
            for prefix, key in expected.items():
                assert key in bucket.keys(prefix)
            assert _files_under(roots["data"]) == []
        else:
            assert (roots["data"] / "dwg_entities" / drawing_id / "entities.json").is_file()
            assert (roots["data"] / "dwg_thumbnails" / drawing_id / "thumbnail.svg").is_file()
            assert any(p.read_bytes() == dxf for p in _files_under(roots["data"] / "dwg_uploads"))
            for prefix, key in expected.items():
                assert key not in bucket.keys(prefix)

        simulate_restart(mode, roots)

        ents = await client.get(f"/api/v1/dwg_takeoff/drawings/{drawing_id}/entities/", headers=auth)
        assert ents.status_code == 200, ents.text
        assert len(ents.json()) >= 3
        thumb = await client.get(f"/api/v1/dwg_takeoff/drawings/{drawing_id}/thumbnail/", headers=auth)
        assert thumb.status_code == 200, thumb.text
        assert "<svg" in thumb.text

        dele = await client.delete(f"/api/v1/dwg_takeoff/drawings/{drawing_id}", headers=auth)
        assert dele.status_code == 204
        if mode == "s3":
            for prefix, key in expected.items():
                assert key not in bucket.keys(prefix)
            assert not any(bucket.get(k) == dxf for k in bucket.keys("dwg_uploads/"))
        else:
            assert not (roots["data"] / "dwg_entities" / drawing_id / "entities.json").exists()

    async def test_missing_dwg_entities_blob_degrades_cleanly(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        pytest.importorskip("ezdxf")
        up = await client.post(
            "/api/v1/dwg_takeoff/drawings/upload/",
            params={"project_id": project_id},
            files={"file": ("p2.dxf", io.BytesIO(_dxf_bytes()), "application/dxf")},
            headers=auth,
        )
        assert up.status_code == 201, up.text
        drawing_id = up.json()["id"]
        if mode == "s3":
            bucket.remove(f"dwg_entities/{drawing_id}/entities.json")
            bucket.remove(f"dwg_thumbnails/{drawing_id}/thumbnail.svg")
        else:
            (roots["data"] / "dwg_entities" / drawing_id / "entities.json").unlink()
            (roots["data"] / "dwg_thumbnails" / drawing_id / "thumbnail.svg").unlink()
        ents = await client.get(f"/api/v1/dwg_takeoff/drawings/{drawing_id}/entities/", headers=auth)
        assert ents.status_code == 200
        assert ents.json() == []  # historical "missing → empty"
        thumb = await client.get(f"/api/v1/dwg_takeoff/drawings/{drawing_id}/thumbnail/", headers=auth)
        assert thumb.status_code == 404


class TestPunchListPhotos:
    async def test_punch_photo_upload_restart_remove(
        self,
        mode: str,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        roots: dict[str, Path],
        bucket: Bucket,
    ) -> None:
        item = await client.post(
            "/api/v1/punchlist/items/",
            json={"project_id": project_id, "title": "Synthetic snag", "description": "test"},
            headers=auth,
        )
        assert item.status_code == 201, item.text
        item_id = item.json()["id"]
        png = _png_bytes(32, 32)

        up = await client.post(
            f"/api/v1/punchlist/items/{item_id}/photos/",
            files={"file": ("snag.png", io.BytesIO(png), "image/png")},
            headers=auth,
        )
        assert up.status_code == 200, up.text
        ref = up.json()["photos"][-1]
        assert ref.startswith("punchlist/photos/")
        filename = ref.rsplit("/", 1)[-1]
        key = f"punchlist_photos/{filename}"

        if mode == "s3":
            assert bucket.get(key) == png
            assert not (roots["punch"] / filename).exists()
            bucket.assert_private(key)
        else:
            assert (roots["punch"] / filename).read_bytes() == png
            assert key not in bucket.keys("punchlist_photos/")

        simulate_restart(mode, roots)

        # No HTTP download route exists for punch photos (unchanged); prove
        # durability through a fresh storage instance instead.
        from app.modules.punchlist.router import PUNCH_PHOTOS_AREA

        assert await PUNCH_PHOTOS_AREA.read(roots["punch"] / filename) == png

        rm = await client.delete(f"/api/v1/punchlist/items/{item_id}/photos/0", headers=auth)
        assert rm.status_code == 204
        if mode == "s3":
            assert key not in bucket.keys("punchlist_photos/")
        else:
            assert not (roots["punch"] / filename).exists()
        with pytest.raises(FileNotFoundError):
            await PUNCH_PHOTOS_AREA.read(roots["punch"] / filename)

        # Out-of-range index is still rejected and deletes nothing.
        bad = await client.delete(f"/api/v1/punchlist/items/{item_id}/photos/5", headers=auth)
        assert bad.status_code == 400
