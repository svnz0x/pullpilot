#!/usr/bin/env bash
# Wrapper para el script canonical de PullPilot.
# Licencia: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"

if [[ -d "$PROJECT_ROOT/src" ]]; then
  case ":${PYTHONPATH-}:" in
    *:"$PROJECT_ROOT/src":*) ;;
    *)
      if [[ -n "${PYTHONPATH-}" ]]; then
        export PYTHONPATH="$PYTHONPATH:$PROJECT_ROOT/src"
      else
        export PYTHONPATH="$PROJECT_ROOT/src"
      fi
      ;;
  esac
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "[updater wrapper] No se encontró un intérprete de Python (python3/python)." >&2
    exit 127
  fi
fi

RESOURCE_PATH="$($PYTHON_BIN - <<'PYRES'
from pullpilot.resources import get_resource_path
print(get_resource_path("scripts/updater.sh"))
PYRES
)" || {
  echo "[updater wrapper] No se pudo localizar el script canonical empaquetado." >&2
  exit 1
}

exec "$RESOURCE_PATH" "$@"
