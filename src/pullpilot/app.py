"""Minimal API surface for exposing updater configuration endpoints."""
from __future__ import annotations

import hmac
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .config import ConfigData, ConfigError, ConfigStore, ValidationError
from .resources import get_resource_path
from .schedule import DEFAULT_SCHEDULE_PATH, ScheduleStore, ScheduleValidationError

TOKEN_ENV = "PULLPILOT_TOKEN"

LOGGER = logging.getLogger("pullpilot.app")


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


def _load_token_from_env_files() -> None:
    """Populate ``os.environ`` with the token from ``.env`` files when needed."""

    existing = os.environ.get(TOKEN_ENV)
    normalized_existing = _normalize_env_value(existing)
    if normalized_existing is not None:
        if existing != normalized_existing:
            os.environ[TOKEN_ENV] = normalized_existing
        return
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
            return


def _strip_inline_comments(value: str) -> str:
    """Remove inline comments from ``.env`` style assignments."""

    result = []
    quote_char: Optional[str] = None
    for char in value:
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

        _load_token_from_env_files()
        token = _normalize_env_value(os.getenv(TOKEN_ENV))
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
        ui_public_paths = {"/", "/ui"}
        ui_auth_only_paths = {"/ui/auth-check"}
        is_ui_request = path == "/" or path.startswith("/ui")
        requires_auth = (
            path in ui_auth_only_paths
            or (
                path not in ui_public_paths
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

        if path in {"/", "/ui"}:
            return HTTPStatus.OK, {"message": "ui"}

        return HTTPStatus.NOT_FOUND, {"error": "not found"}

    def _gather_logs(self, selected_name: Optional[str] = None) -> Dict[str, Any]:
        data = self.store.load()
        log_dir_raw = data.values.get("LOG_DIR", "")
        log_dir_str = str(log_dir_raw) if log_dir_raw is not None else ""
        try:
            log_dir = Path(log_dir_str).expanduser()
        except Exception:
            log_dir = Path(log_dir_str)

        files_payload = []
        selected_payload: Optional[Dict[str, Any]] = None
        entries: list[Tuple[Path, os.stat_result]] = []
        try:
            if log_dir.exists():
                for entry in log_dir.iterdir():
                    if not entry.is_file() or entry.suffix != ".log":
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
                content = self._read_log_tail(entry)
                selected_payload = dict(file_payload)
                selected_payload["content"] = content

        return {
            "log_dir": str(log_dir),
            "files": files_payload,
            "selected": selected_payload,
        }

    def _read_log_tail(self, path: Path, max_lines: int = MAX_UI_LOG_LINES) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max_lines)
        except OSError:
            return ""
        return "".join(lines)

    def _handle_put(self, payload: Optional[Mapping[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        if payload is None:
            return HTTPStatus.BAD_REQUEST, {"error": "missing payload"}
        values = payload.get("values")
        if not isinstance(values, Mapping):
            return HTTPStatus.BAD_REQUEST, {"error": "'values' must be an object"}
        multiline = payload.get("multiline")
        if multiline is not None and not isinstance(multiline, Mapping):
            return HTTPStatus.BAD_REQUEST, {"error": "'multiline' must be an object"}
        try:
            data = self.store.save(values, multiline)
        except ValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": "validation failed", "details": exc.errors}
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
        return HTTPStatus.OK, data.to_dict()

    # ------------------------------------------------------------------
    def _serialize(self, data: ConfigData) -> Dict[str, Any]:
        payload = data.to_dict()
        payload["schema"] = self.store.schema_overview()
        payload["meta"] = {"multiline_fields": self.store.multiline_fields}
        return payload


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
    try:  # pragma: no cover - exercised when FastAPI is available
        from fastapi import Depends, FastAPI, HTTPException, Request
        from fastapi.responses import HTMLResponse, JSONResponse, Response

        app = FastAPI()
        ui_index_content = get_resource_path("ui/index.html").read_text(encoding="utf-8")

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

        @app.get("/", response_class=HTMLResponse)
        @app.get("/ui", response_class=HTMLResponse)
        def get_ui_page() -> HTMLResponse:
            return HTMLResponse(ui_index_content)

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
    except ImportError:
        return api
