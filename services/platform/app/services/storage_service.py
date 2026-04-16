"""File storage abstraction for APK uploads.

Stores files on the local filesystem under STORAGE_PATH (configurable).
In production, swap this for an S3-compatible implementation.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from app.config import settings


def _base_dir() -> Path:
    p = Path(settings.storage_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(file_bytes: bytes, app_name: str, version: str, filename: str) -> tuple[str, int, str]:
    """Save uploaded file bytes. Returns (relative_path, size_bytes, sha256_hex)."""
    dest_dir = _base_dir() / "releases" / app_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{app_name}-{version}.apk"
    dest_path = dest_dir / safe_filename

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    sha = hashlib.sha256(file_bytes).hexdigest()
    rel_path = f"releases/{app_name}/{safe_filename}"
    return rel_path, len(file_bytes), sha


def get_file_path(relative_path: str) -> Path | None:
    """Resolve a relative storage path to an absolute filesystem path."""
    full = _base_dir() / relative_path
    if full.exists() and full.is_file():
        return full
    return None


def delete_file(relative_path: str) -> bool:
    """Delete a file from storage. Returns True if deleted."""
    full = _base_dir() / relative_path
    if full.exists():
        full.unlink()
        return True
    return False
