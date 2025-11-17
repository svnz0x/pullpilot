"""Minimal API surface for exposing updater configuration endpoints."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from http import HTTPStatus
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple, Union

from ..auth import Authenticator, TOKEN_ENV
from ..config import ConfigData, ConfigError, ConfigStore, PersistenceError, ValidationError
from ..resources import get_resource_path
from ..schedule import (
    DEFAULT_SCHEDULE_PATH,
    SchedulePersistenceError,
    ScheduleStore,
    ScheduleValidationError,
)
from ..scheduler.watch import resolve_default_updater_command
from ..ui.logs import LogReadError, gather_logs
from .directories import ensure_required_directories

LOGGER = logging.getLogger("pullpilot.api.config")

DEFAULT_CONFIG_PATH = get_resource_path("config/updater.conf")
DEFAULT_SCHEMA_PATH = get_resource_path("config/schema.json")


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
LogGatherer = Callable[[Optional[str]], Dict[str, Any]]
EnsureDirectoriesFn = Callable[[ConfigData], Optional[Tuple[int, Dict[str, Any]]]]


class ConfigAPI:
    """Lightweight request handler used both for tests and WSGI bridges."""

    def __init__(
        self,
        store: Optional[ConfigStore] = None,
        schedule_store: Optional[ScheduleStore] = None,
        authenticator: Optional[Authenticator] = None,
        *,
        updater_command: Optional[Union[str, Sequence[str]]] = None,
        process_runner: Optional[ProcessRunner] = None,
        log_gatherer: Optional[LogGatherer] = None,
        ensure_directories: Optional[EnsureDirectoriesFn] = None,
    ):
        self.store = store or ConfigStore(DEFAULT_CONFIG_PATH, DEFAULT_SCHEMA_PATH)
        self.schedule_store = schedule_store or ScheduleStore(DEFAULT_SCHEDULE_PATH)
        if authenticator is not None:
            self.authenticator = authenticator
        else:
            self.authenticator = Authenticator.from_env()
        self._updater_command = updater_command
        self._process_runner = process_runner or subprocess.run
        self._ensure_required_directories = ensure_directories or ensure_required_directories
        self._log_gatherer = log_gatherer or (lambda selected: gather_logs(self.store, selected))

    # ------------------------------------------------------------------
    # Request helpers
    def handle_request(
        self,
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        method = method.upper()
        ui_public_paths = {
            "/",
            "/ui",
            "/ui/",
            "/ui/styles.css",
            "/ui/app.js",
            "/ui/manifest.json",
        }
        ui_public_prefixes = ("/ui/assets",)
        ui_auth_only_paths = {"/ui/auth-check"}
        is_ui_request = path == "/" or path.startswith("/ui")
        is_public_asset_request = any(path.startswith(prefix) for prefix in ui_public_prefixes)
        requires_auth = (
            path in ui_auth_only_paths
            or (
                not is_public_asset_request
                and path not in ui_public_paths
                and (path.startswith("/ui") or path in {"/config", "/schedule"})
            )
        )
        if requires_auth:
            if not self.authenticator or not self.authenticator.configured:
                return (
                    HTTPStatus.UNAUTHORIZED,
                    {
                        "error": "missing credentials",
                        "details": (
                            "Set the "
                            f"{TOKEN_ENV} environment variable and send an Authorization header."
                        ),
                    },
                )
            if not self.authenticator.authorize(headers):
                return HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"}

        if is_ui_request:
            return self._handle_ui_request(method, path, payload)
        if path not in {"/config", "/schedule"}:
            return HTTPStatus.NOT_FOUND, {"error": "not found"}

        if path == "/config":
            if method == "GET":
                try:
                    data = self.store.load()
                except Exception as exc:
                    return HTTPStatus.INTERNAL_SERVER_ERROR, {
                        "error": "failed to load configuration",
                        "details": str(exc),
                    }
                return HTTPStatus.OK, self._serialize(data)
            if method == "PUT":
                return self._handle_put(payload)
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}

        if method == "GET":
            try:
                data = self.schedule_store.load()
            except (ScheduleValidationError, json.JSONDecodeError) as exc:
                return HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "error": "failed to load schedule",
                    "details": str(exc),
                }
            return HTTPStatus.OK, data.to_dict()
        if method == "PUT":
            return self._handle_schedule_put(payload)
        return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}

    # ------------------------------------------------------------------
    # UI helpers
    def _handle_ui_request(
        self,
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        if path == "/ui/config":
            if method == "GET":
                try:
                    data = self.store.load()
                except Exception as exc:
                    return HTTPStatus.INTERNAL_SERVER_ERROR, {
                        "error": "failed to load configuration",
                        "details": str(exc),
                    }
                return HTTPStatus.OK, self._serialize(data)
            if method in {"POST", "PUT"}:
                return self._handle_put(payload)
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}

        if path == "/ui/auth-check":
            if method == "GET":
                return HTTPStatus.NO_CONTENT, {}
            return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}

        if path == "/ui/logs":
            if method not in {"GET", "POST"}:
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}
            if payload is not None and not isinstance(payload, Mapping):
                return HTTPStatus.BAD_REQUEST, {"error": "payload must be an object"}
            selected_name = None
            if payload is not None:
                candidate = payload.get("name")
                if candidate is not None and not isinstance(candidate, str):
                    return HTTPStatus.BAD_REQUEST, {"error": "'name' must be a string"}
                selected_name = candidate
            try:
                logs_payload = self._log_gatherer(selected_name)
            except ConfigError as exc:
                LOGGER.warning("Configuration error while gathering logs", exc_info=True)
                return HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "error": "failed to load logs",
                    "details": str(exc),
                }
            except LogReadError as exc:
                LOGGER.warning("Log read error while gathering logs", exc_info=True)
                return HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "error": "failed to load logs",
                    "details": str(exc),
                }
            except Exception as exc:
                LOGGER.warning("Unexpected error while gathering logs", exc_info=True)
                return HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "error": "failed to load logs",
                    "details": str(exc),
                }
            return HTTPStatus.OK, logs_payload

        if path in {"/", "/ui", "/ui/"}:
            return HTTPStatus.OK, {"message": "ui"}

        if path == "/ui/run-test":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"}
            return self._handle_run_test()

        return HTTPStatus.NOT_FOUND, {"error": "not found"}

    def _handle_put(self, payload: Optional[Mapping[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        if payload is None:
            return HTTPStatus.BAD_REQUEST, {"error": "missing payload"}
        values = payload.get("values")
        if not isinstance(values, Mapping):
            return HTTPStatus.BAD_REQUEST, {"error": "'values' must be an object"}
        multiline = payload.get("multiline")
        sanitized_multiline: Dict[str, str] = {}
        if multiline is not None:
            if not isinstance(multiline, Mapping):
                return HTTPStatus.BAD_REQUEST, {"error": "'multiline' must be an object"}

            errors = []
            for key, value in multiline.items():
                if isinstance(value, str):
                    sanitized_multiline[str(key)] = value
                    continue
                errors.append(
                    {
                        "field": str(key),
                        "message": "multiline values must be strings",
                    }
                )

            if errors:
                return HTTPStatus.BAD_REQUEST, {
                    "error": "validation failed",
                    "details": errors,
                }
        else:
            sanitized_multiline = {}

        try:
            sanitized_values = self.store._validate(values)
        except ValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "validation failed", "details": exc.errors}

        directory_error = self._ensure_required_directories(
            ConfigData(sanitized_values, sanitized_multiline)
        )
        if directory_error is not None:
            return directory_error

        try:
            data = self.store.save(values, sanitized_multiline if multiline is not None else None)
        except ValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "validation failed", "details": exc.errors}
        except PersistenceError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "write failed", "details": exc.details}
        return HTTPStatus.OK, self._serialize(data)

    def _handle_schedule_put(self, payload: Optional[Mapping[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        if payload is None:
            return HTTPStatus.BAD_REQUEST, {"error": "missing payload"}
        if not isinstance(payload, Mapping):
            return HTTPStatus.BAD_REQUEST, {"error": "payload must be an object"}
        try:
            data = self.schedule_store.save(payload)
        except ScheduleValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": "validation failed",
                "details": [exc.as_payload()],
            }
        except SchedulePersistenceError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "write failed", "details": exc.details}
        except OSError as exc:
            message = exc.strerror or str(exc)
            detail = {
                "path": str(self.schedule_store.schedule_path),
                "operation": "write",
                "message": message,
            }
            errno = getattr(exc, "errno", None)
            if errno is not None:
                detail["errno"] = errno
            return HTTPStatus.BAD_REQUEST, {"error": "write failed", "details": [detail]}
        return HTTPStatus.OK, data.to_dict()

    # ------------------------------------------------------------------
    def _serialize(self, data: ConfigData) -> Dict[str, Any]:
        payload = data.to_dict()
        payload["schema"] = self.store.schema_overview()
        payload["meta"] = {"multiline_fields": self.store.multiline_fields}
        return payload

    def _resolve_updater_command(self) -> list[str]:
        command = self._updater_command
        if command is None:
            resolved = resolve_default_updater_command()
            command_parts: Sequence[Union[str, os.PathLike[str]]] = [resolved]
        elif isinstance(command, str):
            command_parts = [command]
        else:
            command_parts = command

        normalized = []
        for part in command_parts:
            if part is None:
                continue
            if isinstance(part, os.PathLike):
                normalized.append(os.fspath(part))
            else:
                normalized.append(str(part))

        if not normalized:
            raise ValueError("updater command is empty")
        return normalized

    def _handle_run_test(self) -> Tuple[int, Dict[str, Any]]:
        try:
            command = self._resolve_updater_command()
        except Exception as exc:
            LOGGER.error("Failed to resolve updater command: %s", exc)
            return (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "execution failed",
                    "details": [
                        {
                            "message": f"No se pudo preparar el comando de prueba: {exc}.",
                        }
                    ],
                },
            )

        env = dict(os.environ)
        env.setdefault("CONF_FILE", str(self.store.config_path))

        runner = self._process_runner
        try:
            completed = runner(  # type: ignore[call-arg]
                command,
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            detail: Dict[str, Any] = {
                "message": f"No se pudo iniciar el comando de prueba: {exc}.",
                "command": command,
            }
            errno = getattr(exc, "errno", None)
            if errno is not None:
                detail["errno"] = errno
            return (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "execution failed", "details": [detail]},
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Unexpected error while executing updater command")
            return (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "execution failed",
                    "details": [
                        {
                            "message": f"Error inesperado al ejecutar el comando de prueba: {exc}.",
                            "command": command,
                        }
                    ],
                },
            )

        payload: Dict[str, Any] = {
            "status": "success" if completed.returncode == 0 else "error",
            "exit_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "command": command,
        }
        if completed.returncode == 0:
            payload["message"] = "El comando de prueba finalizó correctamente."
        else:
            payload["message"] = "El comando de prueba finalizó con errores."
        return HTTPStatus.OK, payload


__all__ = ["ConfigAPI"]
