#!/usr/bin/env bash
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
