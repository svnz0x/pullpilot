#!/usr/bin/env python3
"""Synchronize the canonical updater.sh script with all required locations."""
from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "tools" / "updater.sh"
PACKAGE_DEST = ROOT / "pullpilot" / "resources" / "scripts" / "updater.sh"
WRAPPER_DEST = ROOT / "scripts" / "updater.sh"

STUB_TEMPLATE = """#!/usr/bin/env bash
# Este archivo se genera automáticamente. No lo edites a mano.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

find_root() {
  local candidate="$SCRIPT_DIR"
  while [[ "$candidate" != "/" ]]; do
    if [[ -f "$candidate/tools/updater.sh" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
    candidate="$(dirname "$candidate")"
  done
  return 1
}

PROJECT_ROOT="$(find_root)" || {
  echo "[updater wrapper] No se encontró tools/updater.sh" >&2
  exit 1
}

exec "$PROJECT_ROOT/tools/updater.sh" "$@"
"""


class SyncError(Exception):
    """Raised when synchronization cannot be completed."""


def ensure_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_file(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    path.write_bytes(data)
    return True


def copy_canonical(destination: Path) -> bool:
    if not CANONICAL.is_file():
        raise SyncError(f"No se encontró la fuente canonical: {CANONICAL}")
    return write_file(destination, CANONICAL.read_bytes())


def write_stub(destination: Path) -> bool:
    return write_file(destination, STUB_TEMPLATE.encode("utf-8"))


def sync(check: bool = False) -> int:
    changed = 0
    if not CANONICAL.is_file():
        raise SyncError(f"No se encontró la fuente canonical: {CANONICAL}")
    if not check:
        ensure_executable(CANONICAL)
    for target, writer in (
        (PACKAGE_DEST, copy_canonical),
        (WRAPPER_DEST, write_stub),
    ):
        did_change = writer(target)
        if did_change:
            if check:
                return 1
            ensure_executable(target)
            changed += 1
        elif not check:
            ensure_executable(target)
    if check:
        return 0
    return changed


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo verifica si habría cambios pendientes",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = sync(check=args.check)
    except SyncError as exc:  # pragma: no cover - errores excepcionales
        print(exc, file=sys.stderr)
        return 1
    if args.check and result:
        print("Hay archivos desactualizados; ejecuta sync_updater.py", file=sys.stderr)
        return 1
    if not args.check:
        print("Archivos sincronizados" if result else "No hubo cambios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
