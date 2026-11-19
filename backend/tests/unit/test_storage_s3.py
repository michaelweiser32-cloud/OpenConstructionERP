"""S3 storage backend against a local fake S3 (moto server).

No real cloud account is used: every test talks to an in-process
``moto`` S3 server on 127.0.0.1 with dummy credentials. All payloads are
synthetic bytes.

Covers:
* upload / download / overwrite / delete / prefix delete / streaming
* missing-key error path (FileNotFoundError) and missing-bucket path
  (a configuration error, NOT reported as a missing file)
* privacy: objects are private (no public ACL, no bucket policy,
  anonymous GET is refused) and the app does not hand out presigned
  URLs unless S3_PRESIGNED_DOWNLOADS is explicitly enabled
* configuration: STORAGE_BACKEND=s3 loads and builds the S3 backend,
  a missing aioboto3 fails loudly with a clear message, startup
  validation fails fast on an unreachable bucket
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("aioboto3", reason="S3 backend tests need aioboto3")
moto_server = pytest.importorskip("moto.server", reason="S3 backend tests need moto[server]")

from app.config import Settings  # noqa: E402
from app.core import storage as storage_mod  # noqa: E402
from app.core.storage import (  # noqa: E402
    S3StorageBackend,
    _s3_client_config,
    build_storage_backend,
    validate_storage_backend,
)

_DUMMY_KEY = "testing"  # moto accepts any credentials; never a real key
_REGION = "us-east-1"


# ── Fake S3 server ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fake_s3_endpoint() -> Iterator[str]:
    """Start moto's S3 server on a free localhost port for this module.

    Any ``AWS_*`` variables from the developer's shell are removed for the
    duration so a real profile / region / credential can never be used.
    """
    saved = {k: v for k, v in os.environ.items() if k.startswith("AWS_")}
    for k in saved:
        del os.environ[k]
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.stop()
        os.environ.pop("AWS_EC2_METADATA_DISABLED", None)
        os.environ.update(saved)


def _admin_client(endpoint: str):  # noqa: ANN202 — boto3 client
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=_DUMMY_KEY,
        aws_secret_access_key=_DUMMY_KEY,
        region_name=_REGION,
    )


@pytest.fixture
def bucket(fake_s3_endpoint: str) -> str:
    """A fresh, private bucket per test."""
    name = f"oe-test-{uuid.uuid4().hex[:12]}"
    _admin_client(fake_s3_endpoint).create_bucket(Bucket=name)
    return name


@pytest.fixture
def backend(fake_s3_endpoint: str, bucket: str) -> S3StorageBackend:
    return S3StorageBackend(
        endpoint=fake_s3_endpoint,
        access_key=_DUMMY_KEY,
        secret_key=_DUMMY_KEY,
        bucket=bucket,
        region=_REGION,
    )


def _s3_settings(endpoint: str, bucket: str, **extra: object) -> Settings:
    return Settings(
        _env_file=None,
        storage_backend="s3",
        s3_endpoint=endpoint,
        s3_access_key=_DUMMY_KEY,
        s3_secret_key=_DUMMY_KEY,
        s3_bucket=bucket,
        s3_region=_REGION,
        **extra,
    )


# Synthetic payloads only.
_SMALL = bytes(range(256)) * 4  # 1 KiB, every byte value
_LARGE = os.urandom(int(2.5 * 1024 * 1024))  # > 2 stream chunks of 1 MiB


# ── Upload / download / delete ────────────────────────────────────────────


class TestRoundTrip:
    async def test_put_get_roundtrip(self, backend: S3StorageBackend) -> None:
        await backend.put("bim/p1/m1/geometry.glb", _SMALL)
        assert await backend.get("bim/p1/m1/geometry.glb") == _SMALL
        assert await backend.read_bytes("bim/p1/m1/geometry.glb") == _SMALL

    async def test_exists_and_size(self, backend: S3StorageBackend) -> None:
        await backend.put("docs/a.pdf", _SMALL)
        assert await backend.exists("docs/a.pdf") is True
        assert await backend.size("docs/a.pdf") == len(_SMALL)

    async def test_overwrite_replaces_content(self, backend: S3StorageBackend) -> None:
        await backend.put("k/blob.bin", b"first-version")
        await backend.put("k/blob.bin", b"second")
        assert await backend.get("k/blob.bin") == b"second"

    async def test_stream_large_blob_in_chunks(self, backend: S3StorageBackend) -> None:
        await backend.put("bim/p1/m1/original.ifc", _LARGE)
        chunks = [c async for c in backend.open_stream("bim/p1/m1/original.ifc")]
        assert len(chunks) >= 3, "2.5 MiB must arrive in several 1 MiB chunks"
        assert max(len(c) for c in chunks) <= S3StorageBackend._STREAM_CHUNK_SIZE
        assert b"".join(chunks) == _LARGE

    async def test_delete_removes_blob(self, backend: S3StorageBackend) -> None:
        await backend.put("tmp/x.bin", _SMALL)
        await backend.delete("tmp/x.bin")
        assert await backend.exists("tmp/x.bin") is False
        with pytest.raises(FileNotFoundError):
            await backend.get("tmp/x.bin")

    async def test_delete_prefix_only_touches_prefix(self, backend: S3StorageBackend) -> None:
        for name in ("geometry.glb", "original.ifc", "nested/thumb.png"):
            await backend.put(f"bim/p1/m1/{name}", _SMALL)
        await backend.put("bim/p1/m2/geometry.glb", _SMALL)  # sibling model
        assert await backend.delete_prefix("bim/p1/m1") == 3
        assert await backend.exists("bim/p1/m1/geometry.glb") is False
        assert await backend.exists("bim/p1/m2/geometry.glb") is True


# ── Error paths ───────────────────────────────────────────────────────────


class TestErrorPaths:
    async def test_get_missing_key_raises_file_not_found(self, backend: S3StorageBackend) -> None:
        with pytest.raises(FileNotFoundError, match="missing/key.bin"):
            await backend.get("missing/key.bin")

    async def test_size_missing_key_raises_file_not_found(self, backend: S3StorageBackend) -> None:
        with pytest.raises(FileNotFoundError):
            await backend.size("missing/key.bin")

    async def test_stream_missing_key_raises_file_not_found(self, backend: S3StorageBackend) -> None:
        with pytest.raises(FileNotFoundError):
            _ = [c async for c in backend.open_stream("missing/key.bin")]

    async def test_exists_missing_key_is_false(self, backend: S3StorageBackend) -> None:
        assert await backend.exists("missing/key.bin") is False

    async def test_delete_missing_key_is_noop(self, backend: S3StorageBackend) -> None:
        await backend.delete("missing/key.bin")  # must not raise

    @pytest.mark.parametrize("bad_key", ["", "/abs/key", "a/../b", "a\\b"])
    async def test_invalid_keys_rejected_before_any_request(self, backend: S3StorageBackend, bad_key: str) -> None:
        with pytest.raises(ValueError):
            await backend.put(bad_key, b"x")

    async def test_missing_bucket_is_not_reported_as_missing_file(self, fake_s3_endpoint: str) -> None:
        wrong = S3StorageBackend(
            endpoint=fake_s3_endpoint,
            access_key=_DUMMY_KEY,
            secret_key=_DUMMY_KEY,
            bucket="bucket-that-does-not-exist",
            region=_REGION,
        )
        with pytest.raises(Exception) as excinfo:
            await wrong.get("any/key")
        assert not isinstance(excinfo.value, FileNotFoundError)
        assert "NoSuchBucket" in str(excinfo.value)

    async def test_check_ready_passes_for_existing_bucket(self, backend: S3StorageBackend) -> None:
        await backend.check_ready()

    async def test_check_ready_fails_for_missing_bucket(self, fake_s3_endpoint: str) -> None:
        wrong = S3StorageBackend(
            endpoint=fake_s3_endpoint,
            access_key=_DUMMY_KEY,
            secret_key=_DUMMY_KEY,
            bucket="bucket-that-does-not-exist",
            region=_REGION,
        )
        with pytest.raises(RuntimeError, match="bucket-that-does-not-exist"):
            await wrong.check_ready()


# ── Privacy ───────────────────────────────────────────────────────────────

_PUBLIC_GRANTEES = (
    "http://acs.amazonaws.com/groups/global/AllUsers",
    "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
)


class TestPrivacy:
    async def test_uploaded_object_has_no_public_grant(
        self, backend: S3StorageBackend, fake_s3_endpoint: str, bucket: str
    ) -> None:
        await backend.put("docs/contract.pdf", _SMALL)
        admin = _admin_client(fake_s3_endpoint)
        grants = admin.get_object_acl(Bucket=bucket, Key="docs/contract.pdf")["Grants"]
        uris = {g["Grantee"].get("URI") for g in grants}
        assert not uris.intersection(_PUBLIC_GRANTEES), grants
        assert {g["Permission"] for g in grants} == {"FULL_CONTROL"}  # owner only

    async def test_bucket_has_no_public_policy(
        self, backend: S3StorageBackend, fake_s3_endpoint: str, bucket: str
    ) -> None:
        await backend.put("docs/contract.pdf", _SMALL)
        admin = _admin_client(fake_s3_endpoint)
        from botocore.exceptions import ClientError

        with pytest.raises(ClientError, match="NoSuchBucketPolicy"):
            admin.get_bucket_policy(Bucket=bucket)
        bucket_grants = admin.get_bucket_acl(Bucket=bucket)["Grants"]
        assert not {g["Grantee"].get("URI") for g in bucket_grants}.intersection(_PUBLIC_GRANTEES)

    async def test_anonymous_http_get_is_refused(
        self, backend: S3StorageBackend, fake_s3_endpoint: str, bucket: str
    ) -> None:
        await backend.put("docs/contract.pdf", _SMALL)
        url = f"{fake_s3_endpoint}/{bucket}/docs/contract.pdf"
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(url, timeout=10)  # noqa: S310 — local fake S3
        assert excinfo.value.code == 403

    async def test_app_streams_instead_of_presigning_by_default(
        self,
        backend: S3StorageBackend,
        fake_s3_endpoint: str,
        bucket: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Default: the geometry route gets no presigned URL → it streams."""
        from app.modules.bim_hub import file_storage

        settings = _s3_settings(fake_s3_endpoint, bucket)
        assert settings.s3_presigned_downloads is False
        monkeypatch.setattr("app.config.get_settings", lambda: settings)
        monkeypatch.setattr(file_storage, "get_storage_backend", lambda: backend)

        key = await file_storage.save_geometry("p1", "m1", "glb", _SMALL)
        assert file_storage.presigned_geometry_url(key) is None
        streamed = b"".join([c async for c in file_storage.open_geometry_stream(key)])
        assert streamed == _SMALL

    async def test_presigned_urls_are_opt_in_and_short_lived(
        self,
        backend: S3StorageBackend,
        fake_s3_endpoint: str,
        bucket: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.modules.bim_hub import file_storage

        settings = _s3_settings(fake_s3_endpoint, bucket, s3_presigned_downloads=True)
        monkeypatch.setattr("app.config.get_settings", lambda: settings)
        monkeypatch.setattr(file_storage, "get_storage_backend", lambda: backend)

        key = await file_storage.save_geometry("p1", "m1", "glb", _SMALL)
        url = file_storage.presigned_geometry_url(key, expires_in=300)
        assert url is not None
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert query["X-Amz-Expires"] == ["300"]
        assert query["X-Amz-Signature"][0]
        assert _DUMMY_KEY not in query["X-Amz-Signature"][0]
        # The signed URL works without credentials …
        assert urllib.request.urlopen(url, timeout=10).read() == _SMALL  # noqa: S310
        # … and the same object without the signature does not.
        bare = url.split("?", 1)[0]
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(bare, timeout=10)  # noqa: S310
        assert excinfo.value.code == 403

    async def test_file_storage_end_to_end_delete(
        self, backend: S3StorageBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.bim_hub import file_storage

        monkeypatch.setattr(file_storage, "get_storage_backend", lambda: backend)
        await file_storage.save_geometry("p9", "m9", ".dae", _SMALL)
        await file_storage.save_original_cad("p9", "m9", "ifc", _SMALL)
        found = await file_storage.find_geometry_key("p9", "m9")
        assert found == ("bim/p9/m9/geometry.dae", ".dae")
        assert await file_storage.delete_model_blobs("p9", "m9") == 2
        assert await file_storage.find_geometry_key("p9", "m9") is None


# ── Configuration ─────────────────────────────────────────────────────────


class TestConfiguration:
    def test_env_storage_backend_s3_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("STORAGE_BACKEND", "s3")
        monkeypatch.setenv("S3_ENDPOINT", "http://127.0.0.1:9")
        monkeypatch.setenv("S3_BUCKET", "synthetic-bucket")
        monkeypatch.setenv("S3_ACCESS_KEY", _DUMMY_KEY)
        monkeypatch.setenv("S3_SECRET_KEY", _DUMMY_KEY)
        monkeypatch.setenv("S3_REGION", "auto")
        s = Settings(_env_file=None)
        assert s.storage_backend == "s3"
        assert s.s3_presigned_downloads is False
        backend = build_storage_backend(s)
        assert isinstance(backend, S3StorageBackend)
        assert backend._bucket == "synthetic-bucket"
        assert backend._endpoint == "http://127.0.0.1:9"
        assert backend._region == "auto"

    def test_unknown_storage_backend_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import ValidationError

        monkeypatch.setenv("STORAGE_BACKEND", "ftp")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_missing_aioboto3_fails_loudly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "aioboto3", None)  # simulate "not installed"
        settings = _s3_settings("http://127.0.0.1:9", "synthetic-bucket")
        with pytest.raises(ImportError, match="requires the 'aioboto3' package"):
            build_storage_backend(settings)

    async def test_startup_validation_names_missing_aioboto3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "aioboto3", None)
        settings = _s3_settings("http://127.0.0.1:9", "synthetic-bucket")
        with pytest.raises(RuntimeError, match=r"FATAL: STORAGE_BACKEND=s3 .*aioboto3"):
            await validate_storage_backend(settings)

    async def test_startup_validation_fails_on_unreachable_bucket(self, fake_s3_endpoint: str) -> None:
        settings = _s3_settings(fake_s3_endpoint, "bucket-that-does-not-exist")
        with pytest.raises(RuntimeError, match="FATAL: S3 bucket 'bucket-that-does-not-exist'"):
            await validate_storage_backend(settings)

    async def test_startup_validation_fails_on_empty_bucket_name(self) -> None:
        settings = _s3_settings("http://127.0.0.1:9", "")
        with pytest.raises(RuntimeError, match="S3_BUCKET is empty"):
            await validate_storage_backend(settings)

    async def test_startup_validation_passes_for_reachable_bucket(self, fake_s3_endpoint: str, bucket: str) -> None:
        desc = await validate_storage_backend(_s3_settings(fake_s3_endpoint, bucket))
        assert bucket in desc

    async def test_startup_validation_local_needs_no_network(self) -> None:
        desc = await validate_storage_backend(Settings(_env_file=None, storage_backend="local"))
        assert desc.startswith("local filesystem")

    def test_client_config_limits_checksums_to_required(self) -> None:
        cfg = _s3_client_config()
        assert cfg is not None
        assert cfg.request_checksum_calculation == "when_required"
        assert cfg.response_checksum_validation == "when_required"

    def test_module_exports_validation_helper(self) -> None:
        assert callable(storage_mod.validate_storage_backend)
