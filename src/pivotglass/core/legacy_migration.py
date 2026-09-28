"""Explicit, non-destructive migration of pre-Pivotglass local data."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

LEGACY_EXTENSION_PREFIX = "x_ap_"
EXTENSION_PREFIX = "x_pivotglass_"


def normalize_extensions(value: Any) -> Any:
    """Project legacy extension keys into the current namespace without mutation.

    A current key wins if both names exist. The stored original remains untouched.
    """
    if isinstance(value, list):
        return [normalize_extensions(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {
        key: normalize_extensions(item)
        for key, item in value.items()
        if not key.startswith(LEGACY_EXTENSION_PREFIX)
    }
    for key, item in value.items():
        if key.startswith(LEGACY_EXTENSION_PREFIX):
            new_key = EXTENSION_PREFIX + key.removeprefix(LEGACY_EXTENSION_PREFIX)
            result.setdefault(new_key, normalize_extensions(item))
    return result


def migrate_home(source: Path, destination: Path) -> Path:
    """Copy a stopped installation's home atomically; preserve the source.

    Refuses merges and symbolic links. Copies file metadata, including secret file
    modes, into a private staging directory before publishing the destination.
    """
    source = source.expanduser().absolute()
    destination = destination.expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError("The source must be a real directory, not a symbolic link.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("The destination already exists; migration never merges or overwrites it.")
    if source.resolve() in destination.resolve().parents:
        raise ValueError("The destination must be outside the source directory.")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("The source contains symbolic links; review and copy them explicitly first.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pivotglass-migration-", dir=destination.parent))
    try:
        shutil.copytree(source, staging / "home", copy_function=shutil.copy2)
        copied = staging / "home"
        copied.chmod(0o700)
        if destination.exists() or destination.is_symlink():
            raise ValueError("The destination appeared during migration; it was left untouched.")
        copied.rename(destination)
    finally:
        shutil.rmtree(staging)
    return destination
