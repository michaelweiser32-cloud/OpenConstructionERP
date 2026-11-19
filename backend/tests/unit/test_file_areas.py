"""Unit tests for app.core.file_areas (upload storage routing).

Local cases use a temp directory; S3 cases use a local fake S3 (moto
server, dummy credentials). All data is synthetic.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.core.file_areas import FileArea, find_area
from app.core.storage import reset_storage_backend_cache

_DUMMY_KEY = "testing"


@pytest.fixture
def local_mode() -> Iterator[None]:
    settings = get_settings()
    previous = settings.storage_backend
    settings.storage_backend = "local"
    reset_storage_backend_cache()
    try:
        yield
    finally:
        settings.storage_backend = previous
        reset_storage_backend_cache()


@pytest.fixture(scope="module")
def fake_s3() -> Iterator[str]:
    pytest.importorskip("aioboto3")
    moto_server = pytest.importorskip("moto.server")
    saved = {k: v for k, v in os.environ.items() if k.startswith("AWS_")}
    for k in saved:
        del os.environ[k]
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.stop()
        os.environ.update(saved)


@pytest.fixture
def s3_mode(fake_s3: str) -> Iterator[str]:
    import boto3

    bucket = f"oe-fa-{uuid.uuid4().hex[:10]}"
    boto3.client(
        "s3",
        endpoint_url=fake_s3,
        aws_access_key_id=_DUMMY_KEY,
        aws_secret_access_key=_DUMMY_KEY,
        region_name="us-east-1",
    ).create_bucket(Bucket=bucket)
    settings = get_settings()
    fields = ("storage_backend", "s3_endpoint", "s3_access_key", "s3_secret_key", "s3_bucket", "s3_region")
    original = {f: getattr(settings, f) for f in fields}
    settings.storage_backend = "s3"
    settings.s3_endpoint = fake_s3
    settings.s3_access_key = _DUMMY_KEY
    settings.s3_secret_key = _DUMMY_KEY
    settings.s3_bucket = bucket
    settings.s3_region = "us-east-1"
    reset_storage_backend_cache()
    try:
        yield bucket
    finally:
        for f, v in original.items():
            setattr(settings, f, v)
        reset_storage_backend_cache()


def _area(tmp_path: Path, name: str = "unit_area") -> FileArea:
    root = tmp_path / name
    return FileArea(name, lambda: root)


class TestKeys:
    def test_relative_key_inside_root(self, tmp_path: Path) -> None:
        area = _area(tmp_path)
        assert area.relative_key(area.path_for("p1", "a.pdf")) == "p1/a.pdf"

    def test_paths_outside_root_have_no_key(self, tmp_path: Path) -> None:
        area = _area(tmp_path)
        assert area.relative_key(tmp_path / "elsewhere" / "a.pdf") is None
        assert area.relative_key(area.path_for("..", "escape.pdf")) is None
        assert area.relative_key(area.root) is None  # the root itself is not a file

    def test_root_is_evaluated_per_call(self, tmp_path: Path) -> None:
        holder = {"root": tmp_path / "one"}
        area = FileArea("unit_dynamic", lambda: holder["root"])
        assert area.contains(tmp_path / "one" / "x")
        holder["root"] = tmp_path / "two"
        assert not area.contains(tmp_path / "one" / "x")
        assert area.contains(tmp_path / "two" / "x")

    def test_find_area_picks_the_containing_area(self, tmp_path: Path) -> None:
        a, b = _area(tmp_path, "unit_a"), _area(tmp_path, "unit_b")
        assert find_area(b.path_for("k"), (a, b)) is b
        assert find_area(tmp_path / "nowhere", (a, b)) is None

    @pytest.mark.parametrize("bad", ["", "a/b"])
    def test_invalid_names_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            FileArea(bad, lambda: Path("."))


class TestLocalBackend:
    async def test_write_read_delete_on_disk(self, tmp_path: Path, local_mode: None) -> None:
        area = _area(tmp_path)
        path = area.path_for("proj", "notes.txt")
        await area.write(path, b"synthetic")
        assert path.read_bytes() == b"synthetic"  # exactly the historical location
        assert await area.exists(path)
        assert await area.size(path) == 9
        assert await area.read(path) == b"synthetic"
        await area.delete(path)
        assert not path.exists()
        await area.delete(path)  # idempotent
        with pytest.raises(FileNotFoundError):
            await area.read(path)

    async def test_write_outside_root_is_refused(self, tmp_path: Path, local_mode: None) -> None:
        with pytest.raises(ValueError):
            await _area(tmp_path).write(tmp_path / "outside.txt", b"x")

    async def test_legacy_paths_outside_root_still_work_locally(self, tmp_path: Path, local_mode: None) -> None:
        legacy = tmp_path / "old-home" / "file.bin"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy")
        area = _area(tmp_path)
        assert await area.exists(legacy)
        assert await area.read(legacy) == b"legacy"
        await area.delete(legacy)
        assert not legacy.exists()

    async def test_delete_never_removes_directories(self, tmp_path: Path, local_mode: None) -> None:
        area = _area(tmp_path)
        folder = area.path_for("proj")
        (folder / "keep.txt").parent.mkdir(parents=True)
        (folder / "keep.txt").write_bytes(b"k")
        await area.delete(folder)
        assert (folder / "keep.txt").exists()

    async def test_local_copy_is_the_file_itself(self, tmp_path: Path, local_mode: None) -> None:
        area = _area(tmp_path)
        path = area.path_for("a.dxf")
        await area.write(path, b"0\nEOF\n")
        async with area.local_copy(path) as local:
            assert local == path

    async def test_response_is_a_file_response(self, tmp_path: Path, local_mode: None) -> None:
        from starlette.responses import FileResponse

        area = _area(tmp_path)
        path = area.path_for("a.pdf")
        await area.write(path, b"%PDF-1.4")
        resp = await area.response(path, media_type="application/pdf", filename="a.pdf")
        assert isinstance(resp, FileResponse)


class TestS3Backend:
    async def test_roundtrip_uses_prefixed_key_and_no_disk(self, tmp_path: Path, s3_mode: str) -> None:
        import boto3

        area = _area(tmp_path, "unit_s3")
        path = area.path_for("proj", "plan.pdf")
        await area.write(path, b"synthetic-pdf")
        assert not path.exists()
        s3 = boto3.client(
            "s3",
            endpoint_url=get_settings().s3_endpoint,
            aws_access_key_id=_DUMMY_KEY,
            aws_secret_access_key=_DUMMY_KEY,
            region_name="us-east-1",
        )
        assert s3.get_object(Bucket=s3_mode, Key="unit_s3/proj/plan.pdf")["Body"].read() == b"synthetic-pdf"

        reset_storage_backend_cache()  # simulated restart: fresh backend instance
        assert await area.read(path) == b"synthetic-pdf"
        assert await area.size(path) == 13
        await area.delete(path)
        assert not await area.exists(path)
        with pytest.raises(FileNotFoundError):
            await area.read(path)

    async def test_legacy_paths_are_not_found_on_s3(self, tmp_path: Path, s3_mode: str) -> None:
        legacy = tmp_path / "old-home" / "file.bin"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy")
        area = _area(tmp_path, "unit_s3")
        assert not await area.exists(legacy)
        with pytest.raises(FileNotFoundError):
            await area.read(legacy)
        await area.delete(legacy)  # no-op, and never touches local disk on S3
        assert legacy.exists()

    async def test_local_copy_is_a_temp_file_removed_afterwards(self, tmp_path: Path, s3_mode: str) -> None:
        area = _area(tmp_path, "unit_s3")
        path = area.path_for("drawing.dxf")
        await area.write(path, b"0\nEOF\n")
        async with area.local_copy(path) as local:
            assert local != path
            assert local.name == "drawing.dxf"
            assert local.read_bytes() == b"0\nEOF\n"
        assert not local.exists()

    async def test_response_streams_with_length_and_disposition(self, tmp_path: Path, s3_mode: str) -> None:
        from starlette.responses import StreamingResponse

        area = _area(tmp_path, "unit_s3")
        path = area.path_for("Plan Ü.pdf")
        await area.write(path, b"%PDF-1.4 synthetic")
        resp = await area.response(path, media_type="application/pdf", filename="Plan Ü.pdf")
        assert isinstance(resp, StreamingResponse)
        assert resp.headers["content-length"] == "18"
        assert resp.headers["content-disposition"] == "attachment; filename*=utf-8''Plan%20%C3%9C.pdf"
        body = b"".join([chunk async for chunk in resp.body_iterator])
        assert body == b"%PDF-1.4 synthetic"
