"""Minimal API surface for exposing updater configuration endpoints."""
from __future__ import annotations

import base64
import json
import os
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .config import ConfigData, ConfigStore, ValidationError
from .resources import get_resource_path
from .schedule import DEFAULT_SCHEDULE_PATH, ScheduleStore, ScheduleValidationError

TOKEN_ENV = "PULLPILOT_TOKEN"
TOKEN_FILE_ENV = "PULLPILOT_TOKEN_FILE"
LEGACY_TOKEN_ENV = "PULLPILOT_UI_TOKEN"
LEGACY_TOKEN_FILE_ENV = "PULLPILOT_UI_TOKEN_FILE"
USERNAME_ENV = "PULLPILOT_USERNAME"
PASSWORD_ENV = "PULLPILOT_PASSWORD"
CREDENTIALS_ENV = "PULLPILOT_CREDENTIALS_FILE"
LEGACY_USERNAME_ENV = "PULLPILOT_UI_USERNAME"
LEGACY_PASSWORD_ENV = "PULLPILOT_UI_PASSWORD"
LEGACY_CREDENTIALS_ENV = "PULLPILOT_UI_CREDENTIALS_FILE"
ALLOW_ANONYMOUS_ENV = "PULLPILOT_ALLOW_ANONYMOUS"


class Authenticator:
    """Simple helper that validates Authorization headers when configured."""

    def __init__(self, *, token: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None) -> None:
        self.token = token
        self.username = username
        self.password = password

    @classmethod
    def from_env(cls) -> Optional["Authenticator"]:
        """Create an authenticator from environment variables, if enabled.

        The handler supports either bearer-token authentication or HTTP basic
        auth credentials. Tokens can be passed directly via ``PULLPILOT_TOKEN``
        (or legacy ``PULLPILOT_UI_TOKEN``) or read from ``PULLPILOT_TOKEN_FILE``.
        Basic auth credentials are read from ``PULLPILOT_USERNAME`` and
        ``PULLPILOT_PASSWORD`` or from ``PULLPILOT_CREDENTIALS_FILE`` in
        ``username:password`` format.
        """

        allow_anonymous_raw = os.getenv(ALLOW_ANONYMOUS_ENV, "")
        allow_anonymous = allow_anonymous_raw.strip().lower() in {"1", "true", "yes", "on"}

        token = _read_secret(TOKEN_ENV, TOKEN_FILE_ENV, LEGACY_TOKEN_ENV, LEGACY_TOKEN_FILE_ENV)
        if token:
            return cls(token=token)

        username, password = _read_credentials()
        if username and password:
            return cls(username=username, password=password)

        if allow_anonymous:
            return None

        return cls()

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
        if self.username and self.password:
            return _match_basic_credentials(self.username, self.password, auth_header)
        return False


def _getenv(name: str, legacy: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    if name in os.environ:
        return os.environ[name], name
    if legacy is not None and legacy in os.environ:
        return os.environ[legacy], legacy
    return None, None


def _read_secret(value_var: str, file_var: str, legacy_value_var: Optional[str] = None, legacy_file_var: Optional[str] = None) -> Optional[str]:
    """Read a secret either directly from an env-var or from a file path."""

    direct, _ = _getenv(value_var, legacy_value_var)
    if direct:
        return direct.strip()
    path_value, path_source = _getenv(file_var, legacy_file_var)
    if not path_value:
        return None
    secret_path = Path(path_value)
    if not secret_path.exists():
        variable = path_source or file_var
        raise FileNotFoundError(f"Secret file referenced by {variable} not found: {secret_path}")
    return secret_path.read_text(encoding="utf-8").strip()


def _read_credentials() -> Tuple[Optional[str], Optional[str]]:
    username, _ = _getenv(USERNAME_ENV, LEGACY_USERNAME_ENV)
    password, _ = _getenv(PASSWORD_ENV, LEGACY_PASSWORD_ENV)
    creds_file, creds_source = _getenv(CREDENTIALS_ENV, LEGACY_CREDENTIALS_ENV)
    if creds_file:
        path = Path(creds_file)
        if not path.exists():
            variable = creds_source or CREDENTIALS_ENV
            raise FileNotFoundError(
                f"Credentials file referenced by {variable} not found: {path}"
            )
        content = path.read_text(encoding="utf-8").strip()
        if ":" in content:
            file_username, file_password = content.split(":", 1)
            username = file_username.strip()
            password = file_password.strip()
    if username and password:
        return username, password
    return None, None


def _match_token(expected: str, header: str) -> bool:
    scheme, _, value = header.partition(" ")
    if not value:
        return False
    if scheme.lower() in {"bearer", "token"}:
        return value == expected
    return False


def _match_basic_credentials(username: str, password: str, header: str) -> bool:
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        return False
    try:
        decoded = base64.b64decode(value).decode("utf-8")
    except Exception:  # pragma: no cover - defensive guard for malformed input
        return False
    received_user, _, received_pass = decoded.partition(":")
    return received_user == username and received_pass == password


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
        requires_auth = path.startswith("/ui") or path in {"/config", "/schedule"}
        if self.authenticator and requires_auth and not self.authenticator.authorize(headers):
            return HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"}

        if path.startswith("/ui"):
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
                return HTTPStatus.OK, self._serialize(self.store.load())
            if method in {"POST", "PUT"}:
                return self._handle_put(payload)
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
            return HTTPStatus.OK, self._gather_logs(selected_name)

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
        from fastapi.responses import HTMLResponse, JSONResponse

        app = FastAPI()
        ui_index_content = get_resource_path("ui/index.html").read_text(encoding="utf-8")

        async def _require_auth(request: Request) -> None:
            if not api.authenticator:
                return
            if api.authenticator.authorize(request.headers):
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

        @app.post("/ui/config", dependencies=[Depends(_require_auth)])
        def post_ui_config(payload: Dict[str, Any], request: Request):
            status, body = api.handle_request(
                "POST", "/ui/config", payload, request.headers
            )
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body, status_code=status)

        @app.get("/ui/logs", dependencies=[Depends(_require_auth)])
        def get_ui_logs(request: Request, name: Optional[str] = None):
            payload = {"name": name} if name is not None else None
            status, body = api.handle_request(
                "GET", "/ui/logs", payload, request.headers
            )
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body, status_code=status)

        @app.post("/ui/logs", dependencies=[Depends(_require_auth)])
        def post_ui_logs(payload: Dict[str, Any], request: Request):
            status, body = api.handle_request(
                "POST", "/ui/logs", payload, request.headers
            )
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body, status_code=status)

        @app.get("/config")
        def get_config(request: Request, _: None = Depends(_require_auth)):
            status, body = api.handle_request("GET", "/config", headers=request.headers)
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body, status_code=status)

        @app.put("/config")
        def put_config(payload: Dict[str, Any], request: Request, _: None = Depends(_require_auth)):
            status, body = api.handle_request("PUT", "/config", payload, request.headers)
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body)

        @app.get("/schedule")
        def get_schedule(request: Request, _: None = Depends(_require_auth)):
            status, body = api.handle_request("GET", "/schedule", headers=request.headers)
            if status != HTTPStatus.OK:
                raise HTTPException(status_code=status, detail=body)
            return JSONResponse(body, status_code=status)

        @app.put("/schedule")
        def put_schedule(payload: Dict[str, Any], request: Request, _: None = Depends(_require_auth)):
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
