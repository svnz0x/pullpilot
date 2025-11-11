#!/usr/bin/env python3
"""Sincroniza los defaults empaquetados de configuración hacia un directorio editable."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pullpilot.resources import get_resource_path

LEGACY_DEFAULT_TARGET = REPO_ROOT / "Legacy - config"


def _copy_entry(source: Path, destination: Path, overwrite: bool) -> None:
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_entry(child, destination / child.name, overwrite)
        return

    if destination.exists() and not overwrite:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def sync_defaults(target: Path, overwrite: bool) -> None:
    source = get_resource_path("config")
    if not source.exists():
        raise FileNotFoundError("No se encontraron los defaults empaquetados")

    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        _copy_entry(entry, target / entry.name, overwrite)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copia los defaults empaquetados a un directorio editable",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=LEGACY_DEFAULT_TARGET,
        help=(
            "Directorio donde colocar los defaults. "
            "Por defecto se usa 'Legacy - config' en la raíz del repo."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reemplaza archivos existentes en el destino",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sync_defaults(args.target.expanduser().resolve(), args.overwrite)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
