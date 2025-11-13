"""Minimal API surface for exposing updater configuration endpoints."""
from __future__ import annotations

import bz2
import gzip
import hmac
import json
import logging
import lzma
import os
import stat
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

try:  # pragma: no cover - optional dependency
    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.responses import (
        FileResponse,
        HTMLResponse,
        JSONResponse,
        RedirectResponse,
        Response,
    )
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - optional dependency
    FastAPI = None  # type: ignore
    Depends = None  # type: ignore
    HTTPException = None  # type: ignore
    Request = None  # type: ignore
    FileResponse = None  # type: ignore
    HTMLResponse = None  # type: ignore
    JSONResponse = None  # type: ignore
    RedirectResponse = None  # type: ignore
    Response = None  # type: ignore
    StaticFiles = None  # type: ignore

from .config import ConfigData, ConfigError, ConfigStore, PersistenceError, ValidationError
from .resources import get_resource_path
from .schedule import (
    DEFAULT_SCHEDULE_PATH,
    SchedulePersistenceError,
    ScheduleStore,
    ScheduleValidationError,
)

TOKEN_ENV = "PULLPILOT_TOKEN"
TOKEN_FILE_ENV = "PULLPILOT_TOKEN_FILE"

LOGGER = logging.getLogger("pullpilot.app")


class LogReadError(RuntimeError):
    """Raised when a log file cannot be read."""


_COMPRESSED_OPENERS = {
    ".gz": gzip.open,
    ".gzip": gzip.open,
    ".bz2": bz2.open,
    ".bzip2": bz2.open,
    ".xz": lzma.open,
    ".lzma": lzma.open,
}


def _normalize_env_value(value: Optional[str]) -> Optional[str]:
    """Normalize environment variables used for authentication."""

    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        normalized = normalized[1:-1].strip()
    if not normalized:
        return None
    return normalized


def _iter_candidate_env_paths() -> Iterable[Path]:
    """Yield possible ``.env`` locations for token discovery."""

    candidates = []
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    for root in (Path.cwd(), package_root, project_root):
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved in candidates:
            continue
        candidates.append(resolved)
        yield resolved / ".env"


def _load_token_from_env_files() -> Optional[str]:
    """Populate ``os.environ`` with the token from ``.env`` files when needed."""

    existing = os.environ.get(TOKEN_ENV)
    normalized_existing = _normalize_env_value(existing)
    if normalized_existing is not None:
        if existing != normalized_existing:
            os.environ[TOKEN_ENV] = normalized_existing
        return normalized_existing
    if existing is not None:
        os.environ.pop(TOKEN_ENV, None)

    for path in _iter_candidate_env_paths():
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export"):
                remainder = stripped[len("export"):]
                if not remainder or remainder[0].isspace():
                    stripped = remainder.lstrip()
            if "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() != TOKEN_ENV:
                continue
            normalized = _normalize_env_value(_strip_inline_comments(raw_value))
            if normalized is None:
                continue
            os.environ[TOKEN_ENV] = normalized
            return normalized
    return None


def _load_token_from_file_env() -> Optional[str]:
    """Populate ``os.environ`` with the token defined via ``PULLPILOT_TOKEN_FILE``.

    The token file must be a regular file with permissions that do not grant read
    access to group or other users. Insecure files are ignored to avoid leaking
    authentication credentials.
    """

    raw_path = os.environ.get(TOKEN_FILE_ENV)
    normalized_path = _normalize_env_value(raw_path)
    if not normalized_path:
        return None

    token_path = Path(normalized_path).expanduser()
    try:
        file_stat = token_path.lstat()
    except FileNotFoundError:
        LOGGER.warning(
            "Token file '%s' not found; falling back to environment variables and .env files.",
            token_path,
        )
        return None
    except OSError as exc:
        LOGGER.warning(
            "Failed to access token file '%s': %s; falling back to other configuration sources.",
            token_path,
            exc,
        )
        return None

    if not stat.S_ISREG(file_stat.st_mode):
        LOGGER.warning(
            "Token file '%s' is not a regular file; ignoring it and falling back to other sources.",
            token_path,
        )
        return None

    mode = stat.S_IMODE(file_stat.st_mode)
    insecure_permissions = stat.S_IRGRP | stat.S_IROTH
    if mode & insecure_permissions:
        LOGGER.warning(
            "Token file '%s' has insecure permissions; it must not be readable by group or other users.",
            token_path,
        )
        return None

    try:
        content = token_path.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning(
            "Failed to read token file '%s': %s; falling back to other configuration sources.",
            token_path,
            exc,
        )
        return None

    normalized = _normalize_env_value(content)
    if normalized is None:
        LOGGER.warning(
            "Token file '%s' is empty or contains only whitespace; ignoring it.",
            token_path,
        )
        return None

    os.environ[TOKEN_ENV] = normalized
    return normalized


def _load_token_from_configured_sources() -> Optional[str]:
    """Ensure the authentication token is loaded from env vars, files or `.env`."""

    token = _normalize_env_value(os.environ.get(TOKEN_ENV))
    if token is not None:
        if os.environ[TOKEN_ENV] != token:
            os.environ[TOKEN_ENV] = token
        return token

    os.environ.pop(TOKEN_ENV, None)

    token = _load_token_from_file_env()
    if token is not None:
        return token

    token = _load_token_from_env_files()
    if token is not None:
        return token

    return _normalize_env_value(os.environ.get(TOKEN_ENV))


def _strip_inline_comments(value: str) -> str:
    """Remove inline comments from ``.env`` style assignments."""

    result = []
    quote_char: Optional[str] = None
    escape = False
    for char in value:
        if escape:
            result.append(char)
            escape = False
            continue
        if char == "\\":
            result.append(char)
            escape = True
            continue
        if quote_char:
            if char == quote_char:
                quote_char = None
            result.append(char)
            continue
        if char in {'"', "'"}:
            quote_char = char
            result.append(char)
            continue
        if char == "#":
            break
        result.append(char)
    return "".join(result)


class Authenticator:
    """Simple helper that validates Authorization headers when configured."""

    def __init__(self, *, token: Optional[str] = None) -> None:
        self.token = token

    @classmethod
    def from_env(cls) -> "Authenticator":
        """Create an authenticator from environment variables.

        The handler supports bearer-token authentication using the
        ``PULLPILOT_TOKEN`` environment variable.
        """

        token = _load_token_from_configured_sources()
        if token is None:
            raise RuntimeError(
                "Missing authentication token. Configure the PULLPILOT_TOKEN environment variable."
            )
        return cls(token=token)

    @property
    def configured(self) -> bool:
        """Return ``True`` when a token is available for authorization."""

        return self.token is not None

    def authorize(self, headers: Optional[Mapping[str, str]]) -> bool:
        if not headers:
            return False
        auth_header = None
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth_header = value
                break
        if not auth_header:
            return False
        if self.token:
            return _match_token(self.token, auth_header)
        return False


def _match_token(expected: str, header: str) -> bool:
    normalized = header.strip()
    if not normalized:
        return False
    parts = normalized.split(None, 1)
    if len(parts) != 2:
        return False
    scheme, value = parts
    if not value:
        return False
    if scheme.lower() in {"bearer", "token"}:
        return hmac.compare_digest(value, expected)
    return False


DEFAULT_CONFIG_PATH = get_resource_path("config/updater.conf")
DEFAULT_SCHEMA_PATH = get_resource_path("config/schema.json")
MAX_UI_LOG_LINES = 400

class ConfigAPI:
    """Lightweight request handler used both for tests and WSGI bridges."""

    def __init__(
        self,
        store: Optional[ConfigStore] = None,
        schedule_store: Optional[ScheduleStore] = None,
        authenticator: Optional[Authenticator] = None,
    ):
        self.store = store or ConfigStore(DEFAULT_CONFIG_PATH, DEFAULT_SCHEMA_PATH)
        self.schedule_store = schedule_store or ScheduleStore(DEFAULT_SCHEDULE_PATH)
        if authenticator is not None:
            self.authenticator = authenticator
        else:
            self.authenticator = Authenticator.from_env()

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
                return HTTPStatus.OK, self._serialize(self.store.load())
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
                logs_payload = self._gather_logs(selected_name)
            except ConfigError as exc:
                LOGGER.warning("Configuration error while gathering logs", exc_info=True)
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

        return HTTPStatus.NOT_FOUND, {"error": "not found"}

    def _gather_logs(self, selected_name: Optional[str] = None) -> Dict[str, Any]:
        data = self.store.load()
        log_dir_raw = data.values.get("LOG_DIR", "")
        log_dir_str = str(log_dir_raw).strip() if log_dir_raw is not None else ""
        if not log_dir_str:
            return {
                "log_dir": "",
                "files": [],
                "selected": None,
                "notice": "LOG_DIR no está configurado. Define un directorio absoluto para poder consultar los logs.",
            }

        try:
            log_dir_path = Path(log_dir_str).expanduser()
        except Exception:
            log_dir_path = Path(log_dir_str)

        if not log_dir_path.exists() or not log_dir_path.is_dir():
            return {
                "log_dir": log_dir_str,
                "files": [],
                "selected": None,
                "notice": f"El directorio de logs '{log_dir_str}' no existe o no es accesible.",
            }

        files_payload: list[Dict[str, Any]] = []
        selected_payload: Optional[Dict[str, Any]] = None
        notice_message: Optional[str] = None
        entries: list[Tuple[Path, os.stat_result]] = []
        try:
            for entry in log_dir_path.iterdir():
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                suffixes = entry.suffixes
                if not suffixes or suffixes[0].lower() != ".log":
                    continue
                try:
                    stat_result = entry.stat()
                except OSError:
                    continue
                entries.append((entry, stat_result))
        except OSError:
            entries = []

        entries.sort(key=lambda item: item[1].st_mtime, reverse=True)
        available_names = {entry.name for entry, _ in entries}
        target_name = (
            selected_name
            if selected_name and selected_name in available_names
            else (entries[0][0].name if entries else None)
        )

        for entry, stat_result in entries:
            file_payload = {
                "name": entry.name,
                "size": stat_result.st_size,
                "modified": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat(),
            }
            files_payload.append(file_payload)
            if target_name and entry.name == target_name and selected_payload is None:
                try:
                    content = self._read_log_tail(entry)
                except LogReadError as exc:
                    LOGGER.warning("Failed to read log '%s': %s", entry, exc, exc_info=True)
                    notice_message = (
                        f"No se pudo leer el archivo de log '{entry.name}': {exc}"
                    )
                    selected_payload = dict(file_payload)
                    selected_payload["content"] = ""
                    selected_payload["notice"] = notice_message
                else:
                    selected_payload = dict(file_payload)
                    selected_payload["content"] = content

        result = {
            "log_dir": str(log_dir_path),
            "files": files_payload,
            "selected": selected_payload,
        }

        if notice_message:
            result["notice"] = notice_message

        return result

    def _read_log_tail(self, path: Path, max_lines: int = MAX_UI_LOG_LINES) -> str:
        opener = None
        for suffix in reversed(path.suffixes):
            opener = _COMPRESSED_OPENERS.get(suffix.lower())
            if opener is not None:
                break

        try:
            if opener is not None:
                with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                    lines = deque(handle, maxlen=max_lines)
            else:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    lines = deque(handle, maxlen=max_lines)
        except (OSError, EOFError, gzip.BadGzipFile, lzma.LZMAError) as exc:
            raise LogReadError(str(exc)) from exc

        return "".join(lines)

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

    def _ensure_required_directories(
        self, data: ConfigData
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        """Ensure updater directories exist inside the persistent volume.

        ``scripts/updater.sh`` expects the configuration provided via the UI to
        point to ready-to-use directories.  This helper is invoked right after
        persisting the configuration to guarantee that both ``BASE_DIR`` and
        ``LOG_DIR`` exist.  The persistent storage root is derived from
        ``self.store.config_path.parent``; whenever a configured path resolves
        outside that tree the request is rejected so operators know they must
        mount it inside the volume beforehand.
        """

        try:
            persistent_root = self.store.config_path.parent.resolve()
        except OSError:
            persistent_root = self.store.config_path.parent

        def _error(field: str, message: str) -> Tuple[int, Dict[str, Any]]:
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
                resolved_target = target_path.resolve()
            except PermissionError as exc:
                return _error(
                    field,
                    (
                        f"No se pudo acceder al directorio '{candidate}' para validar permisos: {exc}."
                    ),
                )
            except OSError:
                resolved_target = target_path

            try:
                resolved_target.relative_to(persistent_root)
            except ValueError:
                return _error(
                    field,
                    (
                        f"La ruta debe vivir dentro del volumen persistente '{persistent_root}'. "
                        "Monta el directorio en esa ubicación antes de guardar la configuración."
                    ),
                )

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


def create_app(
    store: Optional[ConfigStore] = None,
    schedule_store: Optional[ScheduleStore] = None,
):
    """Return a FastAPI/Flask compatible object when possible.

    When the optional frameworks are unavailable a plain :class:`ConfigAPI`
    instance is returned so tests can interact with the request handlers
    directly.
    """

    api = ConfigAPI(store=store, schedule_store=schedule_store)
    if FastAPI is None:  # pragma: no cover - exercised when FastAPI is unavailable
        return api

    app = FastAPI()

    ui_root_dir = get_resource_path("ui")
    ui_dist_dir = ui_root_dir / "dist"
    dist_index_path = ui_dist_dir / "index.html"
    has_built_assets = dist_index_path.exists()

    project_root = Path(__file__).resolve().parent.parent.parent
    ui_source_root = project_root / "ui"
    ui_source_index_path = ui_source_root / "index.html"
    ui_source_src_dir = ui_source_root / "src"
    ui_source_styles_path = ui_source_src_dir / "styles.css"
    ui_source_script_path = ui_source_src_dir / "app.js"

    use_source_assets = not has_built_assets and ui_source_index_path.exists()

    if has_built_assets:
        ui_index_path = dist_index_path
        ui_assets_dir = ui_dist_dir / "assets"
        ui_manifest_path = ui_dist_dir / "manifest.json"
    elif use_source_assets:
        ui_index_path = ui_source_index_path
        ui_assets_dir = None
        ui_manifest_path = None
    else:
        raise RuntimeError(
            "UI assets are missing; run 'npm run build' or install the source tree"
        )

    ui_index_content = ui_index_path.read_text(encoding="utf-8")
    ui_styles_path = ui_source_styles_path if ui_source_styles_path.exists() else None
    ui_script_path = ui_source_script_path if ui_source_script_path.exists() else None

    if ui_assets_dir and ui_assets_dir.exists():
        app.mount("/ui/assets", StaticFiles(directory=ui_assets_dir), name="ui-assets")

    if not has_built_assets and ui_source_src_dir.exists():
        app.mount("/ui/src", StaticFiles(directory=ui_source_src_dir), name="ui-src")

    if ui_manifest_path and ui_manifest_path.exists():
        @app.get("/ui/manifest.json")
        def get_ui_manifest() -> FileResponse:
            return FileResponse(ui_manifest_path, media_type="application/json")

    @app.get("/", include_in_schema=False)
    def redirect_root_to_ui() -> RedirectResponse:
        return RedirectResponse("/ui/", status_code=HTTPStatus.TEMPORARY_REDIRECT)

    @app.get("/ui", include_in_schema=False)
    def redirect_ui() -> RedirectResponse:
        return RedirectResponse("/ui/", status_code=HTTPStatus.TEMPORARY_REDIRECT)

    if ui_styles_path:
        @app.get("/ui/styles.css")
        def get_ui_styles() -> FileResponse:
            return FileResponse(ui_styles_path, media_type="text/css")

    if ui_script_path:
        @app.get("/ui/app.js")
        def get_ui_script() -> FileResponse:
            return FileResponse(ui_script_path, media_type="application/javascript")

    @app.get("/ui/", response_class=HTMLResponse)
    def get_ui_page() -> HTMLResponse:
        return HTMLResponse(ui_index_content)

    async def _require_auth(request: Request) -> None:
        authenticator = api.authenticator
        if not authenticator or not authenticator.configured:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail={
                    "error": "missing credentials",
                    "details": f"Set the {TOKEN_ENV} environment variable and send an Authorization header.",
                },
            )
        if authenticator.authorize(request.headers):
            return
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail={"error": "unauthorized"})

    @app.get("/ui/config", dependencies=[Depends(_require_auth)])
    def get_ui_config(request: Request):
        status, body = api.handle_request("GET", "/ui/config", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/ui/auth-check", dependencies=[Depends(_require_auth)])
    def get_ui_auth_check(request: Request):
        status, body = api.handle_request("GET", "/ui/auth-check", headers=request.headers)
        if status == HTTPStatus.NO_CONTENT:
            return Response(status_code=status)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.post("/ui/config", dependencies=[Depends(_require_auth)])
    async def post_ui_config(request: Request):
        payload = await request.json()
        status, body = api.handle_request(
            "POST", "/ui/config", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/ui/logs", dependencies=[Depends(_require_auth)])
    def get_ui_logs(request: Request):
        name = request.query_params.get("name")
        payload = {"name": name} if name is not None else None
        status, body = api.handle_request(
            "GET", "/ui/logs", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.post("/ui/logs", dependencies=[Depends(_require_auth)])
    async def post_ui_logs(request: Request):
        payload = await request.json()
        status, body = api.handle_request(
            "POST", "/ui/logs", payload, request.headers
        )
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.get("/config", dependencies=[Depends(_require_auth)])
    def get_config(request: Request):
        status, body = api.handle_request("GET", "/config", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.put("/config", dependencies=[Depends(_require_auth)])
    async def put_config(request: Request):
        payload = await request.json()
        status, body = api.handle_request("PUT", "/config", payload, request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body)

    @app.get("/schedule", dependencies=[Depends(_require_auth)])
    def get_schedule(request: Request):
        status, body = api.handle_request("GET", "/schedule", headers=request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body, status_code=status)

    @app.put("/schedule", dependencies=[Depends(_require_auth)])
    async def put_schedule(request: Request):
        payload = await request.json()
        status, body = api.handle_request("PUT", "/schedule", payload, request.headers)
        if status != HTTPStatus.OK:
            raise HTTPException(status_code=status, detail=body)
        return JSONResponse(body)

    def handle_request(
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ):
        return api.handle_request(method, path, payload, headers)

    setattr(app, "handle_request", handle_request)
    return app
