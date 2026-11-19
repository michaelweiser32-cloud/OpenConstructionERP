"""End-to-end: BIM upload → S3 bucket → download → delete, through the real app.

Runs the full FastAPI app (lifespan, module loader, auth, routers) with
``STORAGE_BACKEND=s3`` pointed at a local fake S3 (moto server on
127.0.0.1, dummy credentials — never a real cloud account). All data is
synthetic.

Proves that with S3 configured:
* an uploaded geometry file is written to the bucket, not the local disk
* the geometry endpoint streams the bytes through the app (200, no
  redirect to a bucket URL) and still enforces authentication
* the bucket object is not readable anonymously
* deleting the model deletes its blobs from the bucket
"""

from __future__ import annotations

import io
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

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

# Synthetic COLLADA payload — the endpoint serves whatever bytes were stored.
_GEOMETRY = (
    b'<?xml version="1.0"?>\n<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" '
    b'version="1.4.1"><asset><unit meter="1"/></asset>'
    b"<!-- synthetic test geometry " + uuid.uuid4().hex.encode() + b" --></COLLADA>\n"
)
_ELEMENTS_CSV = (
    b"element_id,element_type,name,storey,area_m2\n"
    b"W-001,Wall,Synthetic wall A,Level 1,12.5\n"
    b"W-002,Wall,Synthetic wall B,Level 1,8.0\n"
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
    bucket = f"oe-it-{uuid.uuid4().hex[:10]}"
    _admin(endpoint).create_bucket(Bucket=bucket)
    try:
        yield endpoint, bucket
    finally:
        server.stop()
        os.environ.pop("AWS_EC2_METADATA_DISABLED", None)
        os.environ.update(saved)


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
def s3_settings(fake_s3: tuple[str, str]) -> Iterator[None]:
    """Point the cached app settings at the fake bucket, restore afterwards."""
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
    email = f"s3it-{unique}@example.com"
    password = f"S3It-{unique}-Pw9"
    reg = await client.post(
        "/api/v1/users/auth/register",
        json={"email": email, "password": password, "full_name": "S3 Storage Tester"},
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
            "name": f"S3 storage test {uuid.uuid4().hex[:6]}",
            "description": "Synthetic project for the S3 storage integration test",
            "region": "DACH",
            "classification_standard": "din276",
            "currency": "EUR",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestBimStorageOnS3:
    async def test_upload_download_delete_roundtrip(
        self,
        client: AsyncClient,
        auth: dict[str, str],
        project_id: str,
        fake_s3: tuple[str, str],
    ) -> None:
        endpoint, bucket = fake_s3
        admin = _admin(endpoint)

        # 1. Upload through the real API.
        up = await client.post(
            "/api/v1/bim_hub/upload/",
            params={"project_id": project_id, "name": "Synthetic model"},
            files={
                "data_file": ("elements.csv", io.BytesIO(_ELEMENTS_CSV), "text/csv"),
                "geometry_file": ("model.dae", io.BytesIO(_GEOMETRY), "model/vnd.collada+xml"),
            },
            headers=auth,
        )
        assert up.status_code == 201, up.text
        model_id = up.json()["model_id"]
        key = f"bim/{project_id}/{model_id}/geometry.dae"

        # 2. The blob is in the bucket, byte for byte.
        obj = admin.get_object(Bucket=bucket, Key=key)
        assert obj["Body"].read() == _GEOMETRY

        # 3. …and not readable anonymously.
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"{endpoint}/{bucket}/{key}", timeout=10)  # noqa: S310
        assert excinfo.value.code == 403

        # 4. The app streams it back (no redirect to the bucket).
        token = auth["Authorization"].split(" ", 1)[1]
        geo = await client.get(
            f"/api/v1/bim_hub/models/{model_id}/geometry/",
            params={"token": token, "fmt": "dae"},
            follow_redirects=False,
        )
        assert geo.status_code == 200, geo.text[:300]
        assert "location" not in geo.headers
        assert geo.content == _GEOMETRY

        # 5. Authentication is still enforced on the download route.
        anon = await client.get(f"/api/v1/bim_hub/models/{model_id}/geometry/", follow_redirects=False)
        assert anon.status_code == 401

        # 6. Deleting the model deletes its blobs from the bucket.
        dele = await client.delete(f"/api/v1/bim_hub/{model_id}", headers=auth)
        assert dele.status_code == 204, dele.text
        listed = admin.list_objects_v2(Bucket=bucket, Prefix=f"bim/{project_id}/{model_id}/")
        assert listed.get("KeyCount", 0) == 0
