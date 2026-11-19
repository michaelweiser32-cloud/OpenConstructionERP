"""Durable storage areas for user uploads (documents, photos, takeoff, DWG …).

Most upload modules historically wrote straight to the local filesystem
(``~/.openestimator/uploads``, ``data/dwg_uploads`` …) and stored the
absolute path in the database. On hosts with an ephemeral disk (Render
free, most PaaS) those files vanish on every restart.

A :class:`FileArea` routes one of those directories through the pluggable
:mod:`app.core.storage` layer **without changing what the database stores
or how paths are validated**:

* The DB keeps the same local-style path it always stored (e.g.
  ``/data/.openestimator/photos/<project>/<file>.jpg``). Existing rows,
  the routers' ``resolve().relative_to(BASE)`` / symlink defences and
  every log line keep working unchanged.
* ``STORAGE_BACKEND=local`` → a :class:`LocalStorageBackend` rooted at the
  area's historical directory, so files land at exactly the same place on
  disk as before.
* ``STORAGE_BACKEND=s3`` → the shared S3 backend, under the key
  ``<area-name>/<path relative to the area root>`` (e.g.
  ``photos/<project>/<file>.jpg``) — next to the ``bim/…`` keys of the
  BIM hub, never colliding with them.

Paths that are *outside* the area root (legacy rows written under an older
``$HOME``, demo placeholders, …) keep their historical behaviour on the
local backend — they are read / deleted directly on disk — and are simply
"not found" on S3.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from urllib.parse import quote

from starlette.responses import FileResponse, Response, StreamingResponse

from app.core.storage import LocalStorageBackend, StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)

PathLike = str | Path


# name → area, filled as modules define their areas at import time.
_REGISTRY: dict[str, FileArea] = {}


def _s3_enabled() -> bool:
    from app.config import get_settings

    return (get_settings().storage_backend or "local").lower() == "s3"


class FileArea:
    """One upload directory, stored through the configured storage backend.

    Args:
        name: Stable S3 key prefix for this area (``uploads``, ``photos`` …).
            Never change it once data exists in a bucket.
        local_root: Callable returning the area's local directory. It is
            evaluated on every call (not at import) so ``$HOME`` /
            ``DATA_DIR`` / module-constant overrides behave exactly like the
            historical code that built these paths inline.
    """

    def __init__(self, name: str, local_root: Callable[[], Path]) -> None:
        if not name or "/" in name:
            raise ValueError(f"Invalid file area name: {name!r}")
        self.name = name
        self._local_root = local_root
        _REGISTRY[name] = self

    def __repr__(self) -> str:
        return f"FileArea({self.name!r})"

    # -- paths & keys ---------------------------------------------------

    @property
    def root(self) -> Path:
        """The area's local directory (may be relative to the CWD)."""
        return Path(self._local_root())

    def path_for(self, *parts: str) -> Path:
        """Build the local-style path that callers store in the database."""
        return self.root.joinpath(*parts)

    def relative_key(self, path: PathLike) -> str | None:
        """``path`` relative to the area root as a POSIX key, or ``None``.

        ``None`` means the path is outside this area (legacy / foreign row).
        Both sides are resolved, so ``..`` segments and symlinked parents
        cannot smuggle a path into — or out of — the area.
        """
        try:
            rel = Path(path).resolve().relative_to(self.root.resolve())
        except (ValueError, OSError):
            return None
        key = rel.as_posix()
        return key if key not in ("", ".") else None

    def contains(self, path: PathLike) -> bool:
        return self.relative_key(path) is not None

    def _target(self, path: PathLike) -> tuple[StorageBackend, str] | None:
        """Return ``(backend, key)`` for ``path`` or ``None`` if outside the area."""
        rel = self.relative_key(path)
        if rel is None:
            return None
        if _s3_enabled():
            return get_storage_backend(), f"{self.name}/{rel}"
        return LocalStorageBackend(self.root), rel

    @property
    def is_remote(self) -> bool:
        """``True`` when blobs live in a bucket rather than on local disk."""
        return _s3_enabled()

    # -- operations ------------------------------------------------------

    async def write(self, path: PathLike, content: bytes) -> None:
        """Persist ``content`` at ``path`` (creating parent dirs locally)."""
        target = self._target(path)
        if target is None:
            raise ValueError(f"{path!s} is outside file area {self.name!r} ({self.root})")
        backend, key = target
        await backend.put(key, content)

    async def read(self, path: PathLike) -> bytes:
        """Return the blob at ``path``. Raises :class:`FileNotFoundError`."""
        target = self._target(path)
        if target is None:
            if not self.is_remote:
                legacy = Path(path)
                if legacy.is_file():
                    return await asyncio.to_thread(legacy.read_bytes)
            raise FileNotFoundError(f"No file at {path!s}")
        backend, key = target
        return await backend.get(key)

    async def exists(self, path: PathLike) -> bool:
        target = self._target(path)
        if target is None:
            return (not self.is_remote) and Path(path).is_file()
        backend, key = target
        return await backend.exists(key)

    async def size(self, path: PathLike) -> int:
        target = self._target(path)
        if target is None:
            if not self.is_remote and Path(path).is_file():
                return Path(path).stat().st_size
            raise FileNotFoundError(f"No file at {path!s}")
        backend, key = target
        return await backend.size(key)

    async def delete(self, path: PathLike) -> None:
        """Delete the blob at ``path``; a missing blob is not an error."""
        target = self._target(path)
        if target is None:
            if not self.is_remote:
                legacy = Path(path)
                if legacy.is_file():
                    await asyncio.to_thread(legacy.unlink)
            return
        backend, key = target
        if isinstance(backend, LocalStorageBackend):
            # Only ever unlink a file — never sweep a directory that a
            # tampered row might point at.
            local = Path(path)
            if local.is_file():
                await asyncio.to_thread(local.unlink)
            return
        await backend.delete(key)

    def open_stream(self, path: PathLike) -> AsyncIterator[bytes]:
        target = self._target(path)
        if target is None:
            raise FileNotFoundError(f"No file at {path!s}")
        backend, key = target
        return backend.open_stream(key)

    @contextlib.asynccontextmanager
    async def local_copy(self, path: PathLike) -> AsyncIterator[Path]:
        """Yield a real filesystem path for tools that cannot read bytes.

        On the local backend this is the stored file itself (no copy). On
        S3 the blob is downloaded to a private temporary directory that is
        removed afterwards, keeping the original file name.
        """
        if not self.is_remote:
            yield Path(path)
            return
        content = await self.read(path)
        tmpdir = await asyncio.to_thread(tempfile.mkdtemp, prefix=f"oe-{self.name}-")
        try:
            local = Path(tmpdir) / Path(path).name
            await asyncio.to_thread(local.write_bytes, content)
            yield local
        finally:
            await asyncio.to_thread(shutil.rmtree, tmpdir, True)

    async def response(
        self,
        path: PathLike,
        *,
        media_type: str,
        filename: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """HTTP response serving ``path`` through the app.

        Local backend: the historical :class:`FileResponse` (range requests,
        sendfile). S3: the blob is streamed from the bucket through this
        authenticated route — the bucket is never exposed to the browser.
        Callers must have validated the path and checked :meth:`exists`.
        """
        if not self.is_remote:
            return FileResponse(
                path=str(path),
                filename=filename,
                media_type=media_type,
                headers=headers,
            )
        out_headers = dict(headers or {})
        out_headers["Content-Length"] = str(await self.size(path))
        if filename:
            out_headers["Content-Disposition"] = _attachment_header(filename)
        return StreamingResponse(
            self.open_stream(path),
            media_type=media_type,
            headers=out_headers,
        )


def _attachment_header(filename: str) -> str:
    """Same ``Content-Disposition`` value Starlette's FileResponse sends."""
    quoted = quote(filename)
    if quoted != filename:
        return f"attachment; filename*=utf-8''{quoted}"
    return f'attachment; filename="{filename}"'


def registered_areas() -> tuple[FileArea, ...]:
    """All areas defined so far (one per upload directory)."""
    return tuple(_REGISTRY.values())


def find_area(path: PathLike, areas: tuple[FileArea, ...] | None = None) -> FileArea | None:
    """Return the area that contains ``path`` (``None`` if none does).

    Used for rows that may point into another module's directory — e.g. a
    Documents-hub row cross-linked to a punch-list photo or DWG drawing.
    """
    for area in areas if areas is not None else registered_areas():
        if area.contains(path):
            return area
    return None
