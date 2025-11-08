"""Utilities for persisting and validating scheduler configuration."""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional

DEFAULT_SCHEDULE_PATH = Path(__file__).resolve().parents[2] / "config" / "pullpilot.schedule"
DEFAULT_CRON_EXPRESSION = "0 4 * * *"


@dataclass
class ScheduleData:
    """Normalized representation of the scheduler configuration."""

    mode: str
    expression: Optional[str] = None
    datetime: Optional[str] = None

    def to_dict(self) -> MutableMapping[str, Optional[str]]:
        payload: MutableMapping[str, Optional[str]] = {"mode": self.mode}
        if self.mode == "cron":
            payload["expression"] = self.expression
        elif self.mode == "once":
            payload["datetime"] = self.datetime
        return payload


class ScheduleValidationError(Exception):
    """Raised when an invalid schedule payload is received."""

    def __init__(self, message: str, field: str = "schedule") -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def as_payload(self) -> Mapping[str, str]:
        return {"field": self.field, "message": self.message}


class ScheduleStore:
    """Persist the scheduler configuration in a shared JSON file."""

    def __init__(self, schedule_path: Optional[Path] = None) -> None:
        self.schedule_path = Path(schedule_path or DEFAULT_SCHEDULE_PATH)

    # ------------------------------------------------------------------
    def load(self) -> ScheduleData:
        if not self.schedule_path.exists():
            return ScheduleData(mode="cron", expression=DEFAULT_CRON_EXPRESSION)
        try:
            raw = self.schedule_path.read_text(encoding="utf-8") or "{}"
        except FileNotFoundError:
            return ScheduleData(mode="cron", expression=DEFAULT_CRON_EXPRESSION)
        payload = json.loads(raw)
        return self._validate(payload)

    def save(self, payload: Mapping[str, Any]) -> ScheduleData:
        data = self._validate(payload)
        self.schedule_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            dir=self.schedule_path.parent,
            prefix=f".{self.schedule_path.name}",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.schedule_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        return data

    # ------------------------------------------------------------------
    def _validate(self, payload: Mapping[str, Any]) -> ScheduleData:
        if not isinstance(payload, Mapping):
            raise ScheduleValidationError("El contenido de programación debe ser un objeto.")

        mode = payload.get("mode")
        if mode not in {"cron", "once"}:
            raise ScheduleValidationError("Selecciona un modo válido.", field="mode")

        if mode == "cron":
            expression = payload.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                raise ScheduleValidationError("Indica una expresión cron.", field="expression")
            expression = expression.strip()
            if not _is_valid_cron(expression):
                raise ScheduleValidationError("La expresión cron no es válida.", field="expression")
            return ScheduleData(mode=mode, expression=expression)

        datetime_value = payload.get("datetime")
        if not isinstance(datetime_value, str) or not datetime_value.strip():
            raise ScheduleValidationError("Indica una fecha y hora válidas.", field="datetime")
        normalized = _normalize_datetime(datetime_value)
        return ScheduleData(mode=mode, datetime=normalized)


CRON_FIELD_PATTERN = re.compile(r"^[\w*/,.-]+$")
CRON_MACROS = {
    "@yearly",
    "@annually",
    "@monthly",
    "@weekly",
    "@daily",
    "@midnight",
    "@hourly",
    "@reboot",
}


def _is_valid_cron(expression: str) -> bool:
    lowered = expression.lower()
    if lowered.startswith("@every"):
        parts = lowered.split(maxsplit=1)
        if len(parts) < 2:
            return False
        return bool(parts[1].strip())
    if lowered in CRON_MACROS:
        return True
    parts = [part for part in expression.split() if part]
    if len(parts) != 5:
        return False
    return all(CRON_FIELD_PATTERN.match(part) for part in parts)


def _normalize_datetime(value: str) -> str:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:  # pragma: no cover - sanity guard for unexpected formats
        raise ScheduleValidationError("Formato de fecha/hora inválido.", field="datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
