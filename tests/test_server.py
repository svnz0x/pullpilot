import logging
import os
from http import HTTPStatus
from pathlib import Path
from typing import Mapping


import pytest

from pullpilot.config import ConfigError, ConfigStore
from pullpilot.schedule import ScheduleStore
from pullpilot.app import Authenticator, ConfigAPI, create_app

@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    schema = Path(__file__).resolve().parents[1] / "config" / "schema.json"
    config_path = tmp_path / "updater.conf"
    return ConfigStore(config_path, schema)


@pytest.fixture()
def schedule_store(tmp_path: Path) -> ScheduleStore:
    schedule_path = tmp_path / "pullpilot.schedule"
    return ScheduleStore(schedule_path)


@pytest.fixture()
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> Mapping[str, str]:
    token = "test-token"
    monkeypatch.setenv("PULLPILOT_TOKEN", token)
    return {"Authorization": f"Bearer {token}"}


def test_get_returns_defaults(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK
    assert body["values"]["BASE_DIR"] == "/srv/compose"


def test_get_includes_schema_metadata(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK
    schema = body.get("schema", {})
    variables = {entry["name"]: entry for entry in schema.get("variables", [])}
    assert "PRUNE_VOLUMES" in variables
    assert variables["PRUNE_VOLUMES"]["description"]
    assert body.get("meta", {}).get("multiline_fields") == ["COMPOSE_PROJECTS_FILE"]


def test_put_updates_config_and_multiline(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    projects_path = tmp_path / "projects.txt"
    values["BASE_DIR"] = str(tmp_path / "compose")
    values["LOG_RETENTION_DAYS"] = 30
    values["SMTP_READ_ENVELOPE"] = False
    values["COMPOSE_PROJECTS_FILE"] = str(projects_path)
    multiline = {"COMPOSE_PROJECTS_FILE": "/tmp/alpha\n/tmp/beta\n"}

    status, response = api.handle_request(
        "PUT", "/config", {"values": values, "multiline": multiline}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert response["values"]["LOG_RETENTION_DAYS"] == 30
    assert Path(values["COMPOSE_PROJECTS_FILE"]).read_text(encoding="utf-8") == multiline[
        "COMPOSE_PROJECTS_FILE"
    ]
    text = store.config_path.read_text(encoding="utf-8")
    assert "SMTP_READ_ENVELOPE=false" in text
    assert "LOG_RETENTION_DAYS=30" in text


def test_put_returns_validation_errors(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT",
        "/config",
        {"values": {"BASE_DIR": "", "LOG_RETENTION_DAYS": 0}},
        headers=auth_headers,
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert any(error["field"] == "BASE_DIR" for error in body["details"])


def test_put_rejects_multiline_paths_outside_allowed_directory(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    values["COMPOSE_PROJECTS_FILE"] = str(tmp_path.parent / "escape.txt")
    multiline = {"COMPOSE_PROJECTS_FILE": "/tmp/app\n"}

    status, response = api.handle_request(
        "PUT", "/config", {"values": values, "multiline": multiline}, headers=auth_headers
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert any(error["field"] == "COMPOSE_PROJECTS_FILE" for error in response["details"])


def test_requests_rejected_without_credentials(monkeypatch, store: ConfigStore, schedule_store: ScheduleStore) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.delenv("PULLPILOT_TOKEN_FILE", raising=False)
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "missing credentials"
    details = body.get("details", "")
    assert "PULLPILOT_TOKEN_FILE" in details
    assert "PULLPILOT_TOKEN" in details
    assert "precedence" in details

    status, body = api.handle_request("PUT", "/config", {"values": {}})
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "missing credentials"


def test_token_auth_blocks_unauthenticated_access(
    monkeypatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "super-secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    status, body = api.handle_request("GET", "/config", headers={"Authorization": "Bearer super-secret"})
    assert status == HTTPStatus.OK


def test_token_auth_rejects_invalid_token(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "another-secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request(
        "GET", "/config", headers={"Authorization": "Bearer wrong-secret"}
    )
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"


def test_authenticator_loads_token_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("  file-token \n", encoding="utf-8")
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("PULLPILOT_TOKEN", "env-token")

    authenticator = Authenticator.from_env()

    assert authenticator.token == "file-token"


def test_authenticator_logs_error_when_token_file_missing(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_file = tmp_path / "no-token.txt"
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(missing_file))
    monkeypatch.setenv("PULLPILOT_TOKEN", "fallback-token")
    caplog.set_level(logging.ERROR, logger="pullpilot.app")

    authenticator = Authenticator.from_env()

    assert authenticator.token == "fallback-token"
    expanded_path = Path(os.path.expandvars(str(missing_file))).expanduser()
    assert any(
        "Failed to read token file" in record.getMessage() and str(expanded_path) in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("token_file", ["~/token.txt", "$HOME/token.txt"])
def test_authenticator_expands_token_file_path(
    token_file: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolved_home = tmp_path / "home"
    resolved_home.mkdir()
    token_path = resolved_home / "token.txt"
    token_path.write_text("  expanded-token  \n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(resolved_home))
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", token_file)
    monkeypatch.setenv("PULLPILOT_TOKEN", "fallback-token")

    authenticator = Authenticator.from_env()

    assert authenticator.token == "expanded-token"


def test_token_auth_allows_token_scheme(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "token-scheme")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request(
        "GET", "/config", headers={"Authorization": "Token token-scheme"}
    )
    assert status == HTTPStatus.OK


@pytest.mark.parametrize(
    "header_value",
    [
        "Bearer super-secret  ",
        "  Bearer    super-secret",
        "Bearer super-secret\n",
        "Bearer\t super-secret\n\n",
    ],
)
def test_token_auth_allows_headers_with_ows(
    header_value: str,
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "super-secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config", headers={"Authorization": header_value})
    assert status == HTTPStatus.OK


def test_ui_endpoints_require_auth_when_token_set(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "secret")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/ui/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    status, body = api.handle_request("GET", "/ui/logs")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    headers = {"Authorization": "Bearer secret"}
    status, body = api.handle_request("GET", "/ui/config", headers=headers)
    assert status == HTTPStatus.OK

    status, body = api.handle_request("GET", "/ui/logs", headers=headers)
    assert status == HTTPStatus.OK


@pytest.mark.parametrize("raw_token", ['"secreto"', "'secreto'"])
def test_authenticator_ignores_wrapping_quotes_in_token(
    raw_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN_FILE", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN", raw_token)

    authenticator = Authenticator.from_env()

    assert authenticator.token == "secreto"


def test_authenticator_reads_token_file_with_wrapped_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    token_dir = home_dir / "tokens"
    token_dir.mkdir()
    token_path = token_dir / "token.txt"
    token_path.write_text("wrapped-token\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", "  '~/tokens/token.txt'  ")
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)

    authenticator = Authenticator.from_env()

    assert authenticator.token == "wrapped-token"


def test_authenticator_skips_empty_token_file_after_normalization(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", '  ""  ')
    monkeypatch.setenv("PULLPILOT_TOKEN", "fallback-token")

    authenticator = Authenticator.from_env()

    assert authenticator.token == "fallback-token"


def test_ui_logs_returns_internal_error_when_store_fails(
    auth_headers: Mapping[str, str],
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    def failing_load() -> None:
        raise ConfigError("boom")

    monkeypatch.setattr(api.store, "load", failing_load)

    status, body = api.handle_request("GET", "/ui/logs", headers=auth_headers)
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"error": "failed to load logs", "details": "boom"}


def test_ui_auth_check_allows_token_validation_when_config_fails(
    auth_headers: Mapping[str, str],
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    calls = {"count": 0}

    def failing_load() -> None:
        calls["count"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(api.store, "load", failing_load)

    status, body = api.handle_request("GET", "/ui/auth-check", headers=auth_headers)
    assert status in {HTTPStatus.NO_CONTENT, HTTPStatus.OK}
    assert body == {}
    assert calls["count"] == 0

    status, body = api.handle_request("GET", "/ui/config", headers=auth_headers)
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert calls["count"] == 1
    assert body["error"] == "failed to load configuration"
    assert "boom" in body.get("details", "")


def test_ui_root_allows_anonymous_access(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/")
    assert status == HTTPStatus.OK
    assert body == {"message": "ui"}

    status, body = api.handle_request("GET", "/ui")
    assert status == HTTPStatus.OK
    assert body == {"message": "ui"}

    status, body = api.handle_request("GET", "/ui/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "missing credentials"


def test_token_env_whitespace_trimmed(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.setenv("PULLPILOT_TOKEN", "  my-token \n")
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "unauthorized"

    headers = {"Authorization": "Bearer my-token"}
    status, body = api.handle_request("GET", "/config", headers=headers)
    assert status == HTTPStatus.OK


def test_schedule_get_returns_defaults(
    auth_headers: Mapping[str, str], schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/schedule", headers=auth_headers)
    assert status == HTTPStatus.OK
    assert body["mode"] == "cron"
    assert body["expression"] == "0 4 * * *"


def test_schedule_put_accepts_valid_cron(
    auth_headers: Mapping[str, str], schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT", "/schedule", {"mode": "cron", "expression": "15 2 * * 1"}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert body["expression"] == "15 2 * * 1"
    saved = schedule_store.load()
    assert saved.expression == "15 2 * * 1"


def test_schedule_put_rejects_invalid_expression(
    auth_headers: Mapping[str, str], schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT", "/schedule", {"mode": "cron", "expression": "bad"}, headers=auth_headers
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert body["error"] == "validation failed"
    assert body["details"][0]["field"] == "expression"


def test_schedule_put_accepts_datetime(
    auth_headers: Mapping[str, str], schedule_store: ScheduleStore, store: ConfigStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request(
        "PUT",
        "/schedule",
        {"mode": "once", "datetime": "2030-05-10T12:30:00+02:00"},
        headers=auth_headers,
    )
    assert status == HTTPStatus.OK
    assert body["mode"] == "once"
    assert body["datetime"].endswith("+00:00")


def test_fastapi_get_propagates_error(
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    original_handle_request = ConfigAPI.handle_request

    def fake_handle_request(
        self: ConfigAPI,
        method: str,
        path: str,
        payload=None,
        headers=None,
    ):
        if method == "GET" and path == "/config":
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "boom"}
        return original_handle_request(self, method, path, payload, headers)

    monkeypatch.setattr(ConfigAPI, "handle_request", fake_handle_request)

    monkeypatch.setenv("PULLPILOT_TOKEN", "fast-error")
    app = create_app(store=store, schedule_store=schedule_store)
    client = TestClient(app)

    headers = {"Authorization": "Bearer fast-error"}
    response = client.get("/config", headers=headers)
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


def test_fastapi_ui_routes_require_auth(
    monkeypatch: pytest.MonkeyPatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PULLPILOT_TOKEN", "fast-secret")

    app = create_app(store=store, schedule_store=schedule_store)
    client = TestClient(app)

    response = client.get("/ui/config")
    assert response.status_code == HTTPStatus.UNAUTHORIZED

    response = client.get("/ui/logs")
    assert response.status_code == HTTPStatus.UNAUTHORIZED

    headers = {"Authorization": "Bearer fast-secret"}
    assert client.get("/ui/config", headers=headers).status_code == HTTPStatus.OK
    assert client.get("/ui/logs", headers=headers).status_code == HTTPStatus.OK


def test_ui_config_rejected_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)

    api = ConfigAPI(store=store, schedule_store=schedule_store)

    status, body = api.handle_request("GET", "/ui/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "missing credentials"


def test_ui_config_put_updates_values(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/ui/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    values["LOG_RETENTION_DAYS"] = 7
    projects_file = tmp_path / "projects.txt"
    values["COMPOSE_PROJECTS_FILE"] = str(projects_file)
    multiline = {"COMPOSE_PROJECTS_FILE": "/data/app\n"}

    status, updated = api.handle_request(
        "POST", "/ui/config", {"values": values, "multiline": multiline}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert updated["values"]["LOG_RETENTION_DAYS"] == 7
    assert projects_file.read_text(encoding="utf-8") == multiline["COMPOSE_PROJECTS_FILE"]


def test_ui_logs_listing_and_selection(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/ui/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    values["LOG_DIR"] = str(tmp_path)
    status, _ = api.handle_request("POST", "/ui/config", {"values": values}, headers=auth_headers)
    assert status == HTTPStatus.OK

    first_log = tmp_path / "uno.log"
    first_log.write_text("linea 1\nlinea 2\n", encoding="utf-8")
    second_log = tmp_path / "dos.log"
    second_log.write_text("hola\n", encoding="utf-8")

    status, logs = api.handle_request("GET", "/ui/logs", headers=auth_headers)
    assert status == HTTPStatus.OK
    assert {entry["name"] for entry in logs["files"]} == {"uno.log", "dos.log"}
    assert logs["selected"] is None or logs["selected"]["name"] in {"uno.log", "dos.log"}

    status, selected = api.handle_request(
        "GET", "/ui/logs", {"name": "uno.log"}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert selected["selected"]["name"] == "uno.log"
    assert "linea 1" in selected["selected"]["content"]

    status, error = api.handle_request("POST", "/ui/logs", {"name": 123}, headers=auth_headers)
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"] == "'name' must be a string"
