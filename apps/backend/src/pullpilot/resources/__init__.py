"""Helper utilities to access bundled configuration and script resources."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from typing import Dict, Tuple

import logging
import shutil
import tempfile


_LOGGER = logging.getLogger(__name__)

__all__ = ["get_resource_path", "resource_exists"]

_CACHE_DIR = Path(tempfile.gettempdir()) / "pullpilot" / "resources"


def _copy_file(source: resources.abc.Traversable, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with resources.as_file(source) as resolved:
        shutil.copy2(resolved, destination)


def _copy_directory(source: resources.abc.Traversable, destination: Path) -> None:
    if destination.exists():
        if destination.is_file() or destination.is_symlink():
            destination.unlink()
        else:
            shutil.rmtree(destination)
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
        with resources.as_file(origin) as resolved:
            if _is_directory_cache_valid(resolved, target):
                _log_cache_state(relative, target)
                return target
        _copy_directory(origin, target)
        _log_cache_state(relative, target)
        return target
    with resources.as_file(origin) as resolved:
        if _is_file_cache_valid(resolved, target):
            _log_cache_state(relative, target)
            return target
    _copy_file(origin, target)
    _log_cache_state(relative, target)
    return target


def _is_file_cache_valid(source: Path, destination: Path) -> bool:
    if not destination.exists() or not destination.is_file():
        return False
    try:
        source_stat = source.stat()
        dest_stat = destination.stat()
    except OSError:
        return False
    return (
        dest_stat.st_mtime_ns == source_stat.st_mtime_ns
        and dest_stat.st_size == source_stat.st_size
    )


def _is_directory_cache_valid(source: Path, destination: Path) -> bool:
    if not destination.exists() or not destination.is_dir():
        return False
    try:
        source_snapshot = _snapshot_directory(source)
        destination_snapshot = _snapshot_directory(destination)
    except OSError:
        return False
    return source_snapshot == destination_snapshot


def _snapshot_directory(base: Path) -> Tuple[Dict[str, Tuple[int, int]], Tuple[str, ...]]:
    files: Dict[str, Tuple[int, int]] = {}
    directories = set()
    for path in base.rglob("*"):
        relative = path.relative_to(base).as_posix()
        if path.is_file():
            stats = path.stat()
            files[relative] = (stats.st_size, stats.st_mtime_ns)
        elif path.is_dir():
            directories.add(relative)
    return files, tuple(sorted(directories))


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
