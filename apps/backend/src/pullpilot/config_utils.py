"""Shared helpers for manipulating configuration resources."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import shutil


Operation = str
ErrorHandler = Callable[[Operation, Path, OSError], bool]
PathCallback = Callable[[Path], None]


def copy_config_tree(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    on_directory_created: Optional[PathCallback] = None,
    on_file_copied: Optional[PathCallback] = None,
    error_handler: Optional[ErrorHandler] = None,
) -> None:
    """Recursively copy ``source`` into ``destination``.

    ``overwrite`` controls whether existing files in ``destination`` are
    replaced.  ``on_directory_created`` and ``on_file_copied`` are invoked when
    a directory is materialised or a file is copied respectively.  When an
    ``OSError`` occurs during the operation the ``error_handler`` is invoked
    with the operation name, the path being processed and the exception.  If
    the handler returns ``True`` the error is suppressed, otherwise it is
    re-raised.
    """

    source = Path(source)
    destination = Path(destination)

    if source.is_dir():
        created = False
        if not destination.exists():
            destination.mkdir(parents=True, exist_ok=True)
            created = True
        if created and on_directory_created:
            on_directory_created(destination)

        try:
            children = list(source.iterdir())
        except OSError as exc:  # pragma: no cover - delegated behaviour
            if error_handler and error_handler("listdir", source, exc):
                return
            raise

        for child in children:
            copy_config_tree(
                child,
                destination / child.name,
                overwrite=overwrite,
                on_directory_created=on_directory_created,
                on_file_copied=on_file_copied,
                error_handler=error_handler,
            )
        return

    if destination.exists() and not overwrite:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(source, destination)
    except OSError as exc:
        if error_handler and error_handler("copy", source, exc):
            return
        raise

    if on_file_copied:
        on_file_copied(destination)


__all__ = ["copy_config_tree"]

