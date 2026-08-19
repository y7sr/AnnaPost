"""Durable media import and storage owned by AnnaPost."""

from __future__ import annotations

import mimetypes
import secrets
import shutil
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.db.models.post import PostMediaSourceType
from app.services.media import MediaResolutionError


class MediaImportError(ValueError):
    """Raised when source media cannot be copied into durable storage."""


def storage_root() -> Path:
    root = settings.media_storage_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def storage_path(key: str) -> Path:
    """Resolve a stored key without allowing it to escape the media root."""
    root = storage_root()
    path = (root / key).resolve()
    if path != root and root not in path.parents:
        raise MediaResolutionError("Stored media reference escapes media storage")
    return path


def _suffix(name: str, content_type: str | None = None) -> str:
    suffix = Path(urlparse(name).path).suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    return mimetypes.guess_extension((content_type or "").split(";", 1)[0]) or ".bin"


def _new_key(name: str, content_type: str | None = None) -> str:
    return f"{secrets.token_hex(16)}{_suffix(name, content_type)}"


def _check_size(size: int) -> None:
    if size > settings.media_max_size_bytes:
        raise MediaImportError(
            f"Media exceeds the {settings.media_max_size_bytes}-byte storage limit"
        )


async def import_media(*, source_type: PostMediaSourceType, source: str) -> str:
    """Copy a local file or download a URL, returning a durable relative key."""
    if source_type is PostMediaSourceType.LOCAL_FILE:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise MediaImportError(f"Media file does not exist: {source_path}")
        size = source_path.stat().st_size
        _check_size(size)
        key = _new_key(source_path.name)
        destination = storage_path(key)
        shutil.copyfile(source_path, destination)
        return key

    if source_type is PostMediaSourceType.URL:
        key: str | None = None
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
                    follow_redirects=True,
                ) as client,
                client.stream("GET", source) as response,
            ):
                response.raise_for_status()
                content_type = response.headers.get("content-type")
                key = _new_key(source, content_type)
                destination = storage_path(key)
                size = 0
                with destination.open("wb") as output:
                    async for chunk in response.aiter_bytes(64 * 1024):
                        size += len(chunk)
                        _check_size(size)
                        output.write(chunk)
            return key
        except (httpx.HTTPError, OSError, MediaImportError) as exc:
            if key is not None:
                storage_path(key).unlink(missing_ok=True)
            if isinstance(exc, MediaImportError):
                raise
            raise MediaImportError(f"Could not import media from URL: {source}") from exc

    raise MediaImportError(f"Media source type {source_type.value!r} is not importable yet")
