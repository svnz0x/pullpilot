#!/usr/bin/env python3
"""Valida updater.conf frente al esquema descriptivo."""
from __future__ import annotations

import argparse
import errno
import sys
from pathlib import Path
from typing import Iterable, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pullpilot.config import ConfigError, ValidationError, validate_conf
from pullpilot.resources import get_resource_path


def _resolve_path(value: Optional[str], default: Path) -> Path:
    if value is None:
        return default
    path = Path(value).expanduser()
    if not path.exists():
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(path))
    return path.resolve()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida updater.conf frente al esquema JSON")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Ruta del archivo de configuración a validar. "
            "Por defecto se usa el `updater.conf` empaquetado."
        ),
    )
    parser.add_argument(
        "--schema",
        default=None,
        help=(
            "Ruta del esquema JSON. "
            "Por defecto se usa el esquema empaquetado."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        schema_path = _resolve_path(args.schema, get_resource_path("config/schema.json"))
        config_path = _resolve_path(args.config, get_resource_path("config/updater.conf"))
        validate_conf(config_path, schema_path)
    except ValidationError as exc:
        for error in exc.errors:
            field = error.get("field", "<unknown>")
            message = error.get("message", "validation error")
            print(f"ERROR: {field}: {message}")
        return 1
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 1
    except OSError as exc:
        if isinstance(exc, FileNotFoundError) and exc.filename:
            print(f"ERROR: Ruta no encontrada: {exc.filename}")
        else:
            print(f"ERROR: {exc}")
        return 1

    print(f"Configuración válida según {schema_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
