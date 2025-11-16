"""CLI que valida updater.conf frente al esquema empaquetado."""
from __future__ import annotations

import argparse
import errno
import sys
from pathlib import Path
from typing import Iterable, Optional

from pullpilot.config import ConfigError, ValidationError, validate_conf
from pullpilot.resources import get_resource_path

DEFAULT_CONFIG_PATH = Path("config") / "updater.conf"
DEFAULT_SCHEMA_PATH = Path("config") / "schema.json"


def _resolve_path(value: Optional[str], default: Path) -> Path:
    if value is None:
        return default.expanduser().resolve()
    path = Path(value).expanduser()
    if not path.exists():
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(path))
    return path.resolve()


def _resolve_resource_path(relative: str) -> Path:
    path = get_resource_path(relative)
    if not path.exists():
        raise FileNotFoundError(errno.ENOENT, "No such file or directory", relative)
    return path


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida updater.conf frente al esquema JSON")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Ruta del archivo de configuración a validar. "
            "Por defecto se usa ./config/updater.conf si existe o el recurso empaquetado."
        ),
    )
    parser.add_argument(
        "--schema",
        default=None,
        help=(
            "Ruta del esquema JSON. "
            "Por defecto se usa ./config/schema.json si existe o el recurso empaquetado."
        ),
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _discover_default(path: Path, fallback_resource: str) -> Path:
    candidate = path.expanduser()
    if candidate.exists():
        return candidate.resolve()
    return _resolve_resource_path(fallback_resource)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    try:
        schema_path = _resolve_path(args.schema, _discover_default(DEFAULT_SCHEMA_PATH, "config/schema.json"))
        config_path = _resolve_path(args.config, _discover_default(DEFAULT_CONFIG_PATH, "config/updater.conf"))
        validate_conf(config_path, schema_path)
    except ValidationError as exc:
        for error in exc.errors:
            field = error.get("field", "<unknown>")
            message = error.get("message", "validation error")
            print(f"ERROR: {field}: {message}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        if isinstance(exc, FileNotFoundError) and exc.filename:
            print(f"ERROR: Ruta no encontrada: {exc.filename}", file=sys.stderr)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Configuración válida según", schema_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI execution path
    raise SystemExit(main())
