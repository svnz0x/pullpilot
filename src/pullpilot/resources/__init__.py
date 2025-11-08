"""Helper utilities to access bundled configuration and script resources."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import shutil
import tempfile

__all__ = ["get_resource_path", "resource_exists"]

_CACHE_DIR = Path(tempfile.gettempdir()) / "pullpilot" / "resources"


def _copy_file(source: resources.abc.Traversable, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with resources.as_file(source) as resolved:
        shutil.copy2(resolved, destination)


def _copy_directory(source: resources.abc.Traversable, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_directory(entry, target)
        else:
            _copy_file(entry, target)


def _ensure_cached(relative: str) -> Path:
    origin = resources.files(__name__).joinpath(relative)
    target = _CACHE_DIR / relative
    if origin.is_dir():
        _copy_directory(origin, target)
        return target
    _copy_file(origin, target)
    return target


def get_resource_path(relative: str) -> Path:
    """Return a filesystem path for a bundled resource.

    The returned path points to a cached copy extracted under the system
    temporary directory so it can be consumed by APIs that expect regular
    ``Path`` objects (e.g. to be passed to subprocesses).
    """

    return _ensure_cached(relative)


def resource_exists(relative: str) -> bool:
    """Return ``True`` when the given resource exists in the package."""

    try:
        origin = resources.files(__name__).joinpath(relative)
    except FileNotFoundError:
        return False

    try:
        return origin.is_file() or origin.is_dir()
    except FileNotFoundError:
        return False
