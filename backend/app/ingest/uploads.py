"""Staging area for uploads waiting in the job queue.

An upload is written to DATA_DIR/uploads/<uuid>/<filename> so the ingest
job sees the original filename; the job copies it into the content-addressed
file store and the staging copy is removed once the job finishes.
"""

import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.ingest.parsers import SUPPORTED_EXTENSIONS


class UnsupportedUploadError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


def safe_filename(filename: str) -> str:
    # Drop any client-supplied directories (both separators, on any OS).
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        raise UnsupportedUploadError("missing filename")
    return name


def stage_upload(stream: BinaryIO, filename: str, uploads_dir: Path, *, max_bytes: int) -> Path:
    name = safe_filename(filename)
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedUploadError(f"unsupported file type for {name!r}; supported: {supported}")

    staging_dir = uploads_dir / uuid.uuid4().hex
    staging_dir.mkdir(parents=True)
    target = staging_dir / name

    written = 0
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise UploadTooLargeError(f"{name!r} exceeds {max_bytes // (1024 * 1024)} MB")
            out.write(chunk)
    return target


def discard_staged(path: Path, uploads_dir: Path) -> None:
    """Removes a staged upload's directory. Refuses anything that isn't a
    direct child of `uploads_dir`."""
    staging_dir = path.parent
    if staging_dir.parent.resolve() != uploads_dir.resolve():
        return
    shutil.rmtree(staging_dir, ignore_errors=True)
