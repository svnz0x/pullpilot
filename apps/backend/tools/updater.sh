#!/usr/bin/env bash
# Wrapper liviano que invoca el script canonical dentro de pullpilot/resources.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
CANONICAL_SCRIPT="$SCRIPT_DIR/../pullpilot/resources/scripts/updater.sh"

if [[ ! -x "$CANONICAL_SCRIPT" ]]; then
  echo "[updater wrapper] No se encontró el script canonical en $CANONICAL_SCRIPT" >&2
  echo "Asegúrate de haber instalado las dependencias del backend o de ejecutar dentro del árbol del repo." >&2
  exit 1
fi

exec "$CANONICAL_SCRIPT" "$@"
