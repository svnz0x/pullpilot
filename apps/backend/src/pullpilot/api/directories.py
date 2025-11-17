"""Helpers that prepare directories referenced by the updater."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..config import ConfigData


def ensure_required_directories(
    data: ConfigData,
) -> Optional[Tuple[int, Dict[str, object]]]:
    """Ensure updater directories exist and are accessible."""

    def _error(field: str, message: str) -> Tuple[int, Dict[str, object]]:
        return (
            HTTPStatus.BAD_REQUEST,
            {
                "error": "invalid directory",
                "details": [{"field": field, "message": message}],
            },
        )

    for field in ("BASE_DIR", "LOG_DIR"):
        raw_value = data.values.get(field, "")
        candidate = str(raw_value).strip() if raw_value is not None else ""
        if not candidate:
            continue
        try:
            target_path = Path(candidate).expanduser()
        except Exception as exc:  # pragma: no cover - defensive
            return _error(field, f"No se pudo resolver la ruta '{candidate}': {exc}")

        try:
            target_path.resolve()
        except PermissionError as exc:
            return _error(
                field,
                (
                    f"No se pudo acceder al directorio '{candidate}' para validar permisos: {exc}."
                ),
            )
        except OSError:
            pass

        try:
            target_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            return _error(
                field,
                f"No se pudo crear el directorio '{candidate}' automáticamente: {exc}.",
            )
        except OSError as exc:
            return _error(
                field,
                f"No se pudo preparar el directorio '{candidate}' automáticamente: {exc}.",
            )

        if not target_path.is_dir():  # pragma: no cover - defensive
            return _error(
                field,
                f"La ruta '{candidate}' no es un directorio accesible tras crearlo automáticamente.",
            )

    return None


__all__ = ["ensure_required_directories"]
