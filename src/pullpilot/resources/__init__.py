"""Helper utilities to access bundled configuration and script resources."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import logging
import shutil
import tempfile


_LOGGER = logging.getLogger(__name__)

__all__ = ["get_resource_path", "resource_exists"]

_CACHE_DIR = Path(tempfile.gettempdir()) / "pullpilot" / "resources"


def _copy_file(
    source: resources.abc.Traversable,
    destination: Path,
    *,
    refresh: bool = False,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not refresh:
        return

    if refresh and destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    with resources.as_file(source) as resolved:
        shutil.copy2(resolved, destination)


def _copy_directory(
    source: resources.abc.Traversable,
    destination: Path,
    *,
    refresh: bool = False,
) -> None:
    if destination.exists():
        if destination.is_file() or destination.is_symlink():
            if refresh:
                destination.unlink()
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.unlink()
                destination.mkdir(parents=True, exist_ok=True)
        elif refresh:
            for entry in list(destination.iterdir()):
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
    else:
        destination.mkdir(parents=True, exist_ok=True)

    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _copy_directory(entry, target, refresh=refresh)
        else:
            _copy_file(entry, target, refresh=refresh)


def _ensure_cached(relative: str, *, refresh: bool = False) -> Path:
    origin = resources.files(__name__).joinpath(relative)
    target = _CACHE_DIR / relative
    if origin.is_dir():
        _copy_directory(origin, target, refresh=refresh)
        _log_cache_state(relative, target)
        return target
    _copy_file(origin, target, refresh=refresh)
    _log_cache_state(relative, target)
    return target


def _log_cache_state(relative: str, target: Path) -> None:
    try:
        if target.is_file():
            stats = target.stat()
            _LOGGER.debug(
                "Cached resource '%s' -> %s (size=%d bytes, mtime_ns=%d)",
                relative,
                target,
                stats.st_size,
                stats.st_mtime_ns,
            )
            return

        files = list(target.rglob("*"))
        file_count = sum(1 for path in files if path.is_file())
        total_size = 0
        for path in files:
            if path.is_file():
                total_size += path.stat().st_size
        stats = target.stat()
        _LOGGER.debug(
            "Cached resource directory '%s' -> %s (files=%d, size=%d bytes, mtime_ns=%d)",
            relative,
            target,
            file_count,
            total_size,
            stats.st_mtime_ns,
        )
    except OSError:
        _LOGGER.debug("Cached resource '%s' -> %s", relative, target)


def get_resource_path(relative: str, *, refresh: bool = False) -> Path:
    """Return a filesystem path for a bundled resource.

    The returned path points to a cached copy extracted under the system
    temporary directory so it can be consumed by APIs that expect regular
    ``Path`` objects (e.g. to be passed to subprocesses).
    """

    return _ensure_cached(relative, refresh=refresh)


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
