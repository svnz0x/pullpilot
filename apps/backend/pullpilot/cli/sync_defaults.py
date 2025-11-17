"""CLI que sincroniza los defaults de configuración hacia un directorio editable."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional

from pullpilot.config_utils import copy_config_tree
from pullpilot.resources import get_resource_path

DEFAULT_CONFIG_TARGET = Path("config") / "defaults"


class SyncDefaultsError(Exception):
    """Señala que no se encontraron los defaults empaquetados."""


def discover_defaults_dir() -> Path:
    source = get_resource_path("config")
    if not source.exists():
        raise SyncDefaultsError("No se encontraron los defaults empaquetados")
    return source


def sync_defaults(target: Path, overwrite: bool) -> None:
    source = discover_defaults_dir()
    target = target.expanduser()
    target.mkdir(parents=True, exist_ok=True)

    for entry in source.iterdir():
        copy_config_tree(entry, target / entry.name, overwrite=overwrite)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copia los defaults empaquetados a un directorio editable",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_CONFIG_TARGET,
        help=(
            "Directorio donde colocar los defaults. "
            "Por defecto se usa ./config/defaults relativo al directorio actual."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reemplaza archivos existentes en el destino",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    target = args.target if args.target is not None else DEFAULT_CONFIG_TARGET
    try:
        sync_defaults(target, args.overwrite)
    except SyncDefaultsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution path
    raise SystemExit(main())
