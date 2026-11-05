"""Content-addressed storage for original uploaded files (CLAUDE.md invariant 2)."""

import hashlib
import shutil
from pathlib import Path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def store_file(path: Path, files_dir: Path) -> tuple[str, Path]:
    """Copy `path` into `files_dir` under its content hash, unless already present.

    Returns (sha256, stored_path).
    """
    sha256 = hash_file(path)
    stored_path = files_path_for(files_dir, sha256, path.suffix.lower())
    if not stored_path.exists():
        files_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, stored_path)
    return sha256, stored_path


def files_path_for(files_dir: Path, sha256: str, ext: str) -> Path:
    """Reconstructs a content-addressed path without needing the original file."""
    return files_dir / f"{sha256}{ext}"
