import errno
import gzip
import os
import stat
import subprocess
import sys
import uuid
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping, Optional


import pytest

from pullpilot.api import ConfigAPI
from pullpilot.app import create_app
from pullpilot.auth import (
    Authenticator,
    _load_token_from_env_files,
    _load_token_from_file_env,
)
from pullpilot.config import ConfigError, ConfigStore
from pullpilot.schedule import ScheduleStore

@pytest.fixture()
def store(tmp_path: Path) -> ConfigStore:
    from pullpilot.resources import get_resource_path

    schema = get_resource_path("config/schema.json")
    config_path = tmp_path / "updater.conf"
    return ConfigStore(config_path, schema)


@pytest.fixture()
def schedule_store(tmp_path: Path) -> ScheduleStore:
    schedule_path = tmp_path / "pullpilot.schedule"
    return ScheduleStore(schedule_path)


@pytest.fixture(autouse=True)
def fake_ui_resources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ui_root = tmp_path / "ui"
    ui_root.mkdir()
    monkeypatch.setattr("pullpilot.ui.application.get_resource_path", lambda relative: ui_root)


@pytest.fixture()
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> Mapping[str, str]:
    token = "test-token"
    monkeypatch.setenv("PULLPILOT_TOKEN", token)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions not supported on Windows")
def test_load_token_from_file_env_requires_secure_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    token_path = tmp_path / "token.txt"
    token_path.write_text("posix-token\n", encoding="utf-8")
    os.chmod(token_path, 0o644)

    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(token_path))

    with caplog.at_level("WARNING"):
        token = _load_token_from_file_env()

    assert token is None
    assert "insecure permissions" in " ".join(caplog.messages)
    assert "PULLPILOT_TOKEN" not in os.environ


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions not supported on Windows")
def test_load_token_from_file_env_accepts_secure_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "token.txt"
    token_path.write_text("secure-token\n", encoding="utf-8")
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)

    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(token_path))

    token = _load_token_from_file_env()

    assert token == "secure-token"
    assert os.environ.get("PULLPILOT_TOKEN") == "secure-token"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions not supported on Windows")
def test_load_token_from_file_env_handles_unicode_decode_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token_path = tmp_path / "token.txt"
    token_path.write_bytes(b"\xff\xfe\xfd")
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)

    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(token_path))

    with caplog.at_level("WARNING"):
        token = _load_token_from_file_env()

    assert token is None
    assert "PULLPILOT_TOKEN" not in os.environ
    assert any("Failed to read token file" in message for message in caplog.messages)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions not supported on Windows")
def test_load_token_from_file_env_expands_user_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_name = f".pullpilot-token-{uuid.uuid4().hex}"
    token_path = Path.home() / token_name
    token_path.write_text("expanded-token\n", encoding="utf-8")
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)

    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", f"~/{token_name}")

    try:
        token = _load_token_from_file_env()
        assert token == "expanded-token"
        assert os.environ.get("PULLPILOT_TOKEN") == "expanded-token"
    finally:
        try:
            token_path.unlink()
        except FileNotFoundError:
            pass


def test_load_token_from_env_files_includes_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    app_path = repo_root / "src" / "pullpilot" / "auth.py"
    app_path.parent.mkdir(parents=True)
    app_path.write_text("# fake app\n", encoding="utf-8")
    (repo_root / ".env").write_text("PULLPILOT_TOKEN=repo-token\n", encoding="utf-8")

    original_token = os.environ.get("PULLPILOT_TOKEN")
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setattr("pullpilot.auth.__file__", str(app_path))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    try:
        token = _load_token_from_env_files()

        assert token == "repo-token"
        assert os.environ.get("PULLPILOT_TOKEN") == "repo-token"
    finally:
        if original_token is None:
            os.environ.pop("PULLPILOT_TOKEN", None)
        else:
            os.environ["PULLPILOT_TOKEN"] = original_token


def test_get_returns_defaults(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK
    assert body["values"]["BASE_DIR"] == ""
    assert body["values"]["LOG_DIR"] == ""


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
    assert body.get("meta", {}).get("multiline_fields") == []


def test_get_returns_error_when_store_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: Mapping[str, str],
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)

    def fail() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "load", fail)

    status, body = api.handle_request("GET", "/config", headers=auth_headers)

    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body == {"error": "failed to load configuration", "details": "boom"}


def test_run_test_endpoint_reports_success(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('listo\\n')",
    ]
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        updater_command=command,
    )

    status, body = api.handle_request("POST", "/ui/run-test", headers=auth_headers)

    assert status == HTTPStatus.OK
    assert body["status"] == "success"
    assert body["exit_code"] == 0
    assert "listo" in body["stdout"]
    assert body["command"] == command


def test_run_test_endpoint_injects_config_path_into_env(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    captured_env: Optional[Mapping[str, str]] = None

    def fake_runner(command, **kwargs):
        nonlocal captured_env
        captured_env = kwargs.get("env")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    command = ["/bin/echo", "hola"]
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        updater_command=command,
        process_runner=fake_runner,
    )

    status, body = api.handle_request("POST", "/ui/run-test", headers=auth_headers)

    assert status == HTTPStatus.OK
    assert body["status"] == "success"
    assert captured_env is not None
    assert captured_env.get("CONF_FILE") == str(store.config_path)


def test_run_test_endpoint_reports_non_zero_exit(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('fallo\\n'); sys.exit(5)",
    ]
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        updater_command=command,
    )

    status, body = api.handle_request("POST", "/ui/run-test", headers=auth_headers)

    assert status == HTTPStatus.OK
    assert body["status"] == "error"
    assert body["exit_code"] == 5
    assert "fallo" in body["stderr"]


def test_run_test_endpoint_handles_missing_command(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        updater_command=["/path/that/does/not/exist"],
    )

    status, body = api.handle_request("POST", "/ui/run-test", headers=auth_headers)

    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body["error"] == "execution failed"
    details = body.get("details", [])
    assert any("No se pudo iniciar el comando" in detail.get("message", "") for detail in details)


def test_put_updates_config_and_exclusions(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)
    values["LOG_RETENTION_DAYS"] = 30
    values["SMTP_READ_ENVELOPE"] = False
    values["EXCLUDE_PROJECTS"] = " /tmp/alpha \n/tmp/beta\n"

    status, response = api.handle_request(
        "PUT", "/config", {"values": values}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert response["values"]["LOG_RETENTION_DAYS"] == 30
    assert response["values"]["EXCLUDE_PROJECTS"] == "/tmp/alpha\n/tmp/beta"
    text = store.config_path.read_text(encoding="utf-8")
    assert "SMTP_READ_ENVELOPE=false" in text
    assert "LOG_RETENTION_DAYS=30" in text
    assert 'EXCLUDE_PROJECTS="/tmp/alpha' in text
    assert '\n/tmp/beta"' in text


def test_put_returns_validation_errors(
    auth_headers: Mapping[str, str], store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    defaults = store.load()
    values = defaults.values.copy()
    values["BASE_DIR"] = ""
    values["LOG_DIR"] = ""
    values["LOG_RETENTION_DAYS"] = 0
    status, body = api.handle_request(
        "PUT",
        "/config",
        {"values": values},
        headers=auth_headers,
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert any(error["field"] == "BASE_DIR" for error in body["details"])
    assert any(error["field"] == "LOG_DIR" for error in body["details"])


def test_put_rejects_invalid_exclude_projects(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)
    values["EXCLUDE_PROJECTS"] = "relative\n/srv/app\n"

    status, response = api.handle_request(
        "PUT", "/config", {"values": values}, headers=auth_headers
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert any(error["field"] == "EXCLUDE_PROJECTS" for error in response["details"])


def test_put_creates_required_directories(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path / "compose" / "projects"
    log_dir = tmp_path / "logs"
    assert not base_dir.exists()
    assert not log_dir.exists()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)

    status, response = api.handle_request(
        "PUT",
        "/config",
        {"values": values},
        headers=auth_headers,
    )

    assert status == HTTPStatus.OK
    assert response["values"]["BASE_DIR"] == str(base_dir)
    assert response["values"]["LOG_DIR"] == str(log_dir)
    assert base_dir.is_dir()
    assert log_dir.is_dir()


def test_put_allows_directories_outside_persistent_root(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path.parent / "escape-base"
    log_dir = tmp_path.parent / "escape-logs"
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)

    status, response = api.handle_request(
        "PUT",
        "/config",
        {"values": values},
        headers=auth_headers,
    )

    assert status == HTTPStatus.OK
    assert response["values"]["BASE_DIR"] == str(base_dir)
    assert response["values"]["LOG_DIR"] == str(log_dir)
    assert base_dir.is_dir()
    assert log_dir.is_dir()


def test_put_invalid_directory_does_not_modify_config(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path / "compose"
    log_dir = tmp_path / "logs"
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)

    status, response = api.handle_request(
        "PUT", "/config", {"values": values}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    baseline = store.config_path.read_text(encoding="utf-8")

    invalid_values = dict(values)
    invalid_base_file = tmp_path / "compose-file"
    invalid_log_file = tmp_path / "logs-file"
    invalid_base_file.write_text("not-a-directory", encoding="utf-8")
    invalid_log_file.write_text("not-a-directory", encoding="utf-8")
    invalid_values["BASE_DIR"] = str(invalid_base_file)
    invalid_values["LOG_DIR"] = str(invalid_log_file)

    status, error = api.handle_request(
        "PUT", "/config", {"values": invalid_values}, headers=auth_headers
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"] == "invalid directory"
    assert error.get("details")
    assert invalid_base_file.exists()
    assert invalid_log_file.exists()
    assert store.config_path.read_text(encoding="utf-8") == baseline


def test_requests_rejected_without_credentials(
    monkeypatch, store: ConfigStore, schedule_store: ScheduleStore
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        authenticator=Authenticator(token=None),
    )

    status, body = api.handle_request("GET", "/config")
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["error"] == "missing credentials"
    assert (
        body["details"]
        == "Set the PULLPILOT_TOKEN environment variable and send an Authorization header."
    )

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


@pytest.mark.parametrize(
    "line, expected",
    [
        ("export PULLPILOT_TOKEN=super-secret", "super-secret"),
        ("PULLPILOT_TOKEN=another-secret   # comment", "another-secret"),
        ("export   PULLPILOT_TOKEN=\"quoted # value\"   # trailing comment", "quoted # value"),
        (r"PULLPILOT_TOKEN=hash\#value", r"hash\#value"),
        (
            "export PULLPILOT_TOKEN=\"quoted with \\\"inner\\\" quote and \\# hash\"   # comment",
            "quoted with \\\"inner\\\" quote and \\# hash",
        ),
    ],
)
def test_env_loader_supports_real_world_syntax(
    line: str, expected: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text(f"{line}\n", encoding="utf-8")

    _load_token_from_env_files()

    assert os.environ["PULLPILOT_TOKEN"] == expected
    monkeypatch.setenv("PULLPILOT_TOKEN", expected)


def test_create_app_without_token_raises(
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="PULLPILOT_TOKEN"):
        create_app(store=store, schedule_store=schedule_store)


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
    monkeypatch.setenv("PULLPILOT_TOKEN", raw_token)

    authenticator = Authenticator.from_env()

    assert authenticator.token == "secreto"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions not supported on Windows")
def test_authenticator_loads_token_from_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_path = tmp_path / "token.txt"
    token_path.write_text("  token-desde-fichero  \n", encoding="utf-8")
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)

    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(token_path))

    authenticator = Authenticator.from_env()

    assert authenticator.token == "token-desde-fichero"


def test_authenticator_missing_token_file_falls_back_to_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PULLPILOT_TOKEN", raising=False)
    monkeypatch.setenv("PULLPILOT_TOKEN_FILE", str(tmp_path / "no-existe.txt"))

    with pytest.raises(RuntimeError, match="PULLPILOT_TOKEN"):
        Authenticator.from_env()


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
    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        authenticator=Authenticator(token=None),
    )

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


def test_schedule_put_returns_persistence_errors(
    auth_headers: Mapping[str, str],
    schedule_store: ScheduleStore,
    store: ConfigStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = create_app(store=store, schedule_store=schedule_store)

    permission_error = PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    def fail(_: Mapping[str, Any]) -> None:
        raise permission_error

    monkeypatch.setattr(schedule_store, "save", fail)

    status, body = api.handle_request(
        "PUT",
        "/schedule",
        {"mode": "cron", "expression": "30 1 * * *"},
        headers=auth_headers,
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert body["error"] == "write failed"
    assert body["details"]
    detail = body["details"][0]
    assert detail["path"] == str(schedule_store.schedule_path)
    assert detail["operation"] == "write"
    assert detail["message"] == os.strerror(errno.EACCES)
    assert detail["errno"] == errno.EACCES


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


def test_fastapi_get_returns_error_body_when_store_load_fails(
    monkeypatch: pytest.MonkeyPatch,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    def fail() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "load", fail)
    monkeypatch.setenv("PULLPILOT_TOKEN", "fast-failure")

    app = create_app(store=store, schedule_store=schedule_store)
    client = TestClient(app)

    headers = {"Authorization": "Bearer fast-failure"}
    response = client.get("/config", headers=headers)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json() == {"error": "failed to load configuration", "details": "boom"}


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

    api = ConfigAPI(
        store=store,
        schedule_store=schedule_store,
        authenticator=Authenticator(token=None),
    )

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
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)
    values["LOG_RETENTION_DAYS"] = 7
    values["EXCLUDE_PROJECTS"] = "/data/app\n/data/legacy\n"

    status, updated = api.handle_request(
        "POST", "/ui/config", {"values": values}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert updated["values"]["LOG_RETENTION_DAYS"] == 7
    assert updated["values"]["EXCLUDE_PROJECTS"] == "/data/app\n/data/legacy"


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
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(tmp_path)
    status, _ = api.handle_request("POST", "/ui/config", {"values": values}, headers=auth_headers)
    assert status == HTTPStatus.OK

    rotated_log = tmp_path / "uno.log.1"
    rotated_log.write_text("linea antigua\n", encoding="utf-8")
    compressed_log = tmp_path / "uno.log.1.gz"
    with gzip.open(compressed_log, "wt", encoding="utf-8") as handle:
        handle.write("linea comprimida\n")
    dated_log = tmp_path / "errores.log.20240101.gz"
    with gzip.open(dated_log, "wt", encoding="utf-8") as handle:
        handle.write("error 1\n")
    dashed_log = tmp_path / "tres.log-20240101"
    dashed_log.write_text("linea con fecha\n", encoding="utf-8")
    dashed_compressed = tmp_path / "cuatro.log-20240101.gz"
    with gzip.open(dashed_compressed, "wt", encoding="utf-8") as handle:
        handle.write("linea comprimida reciente\n")
    second_log = tmp_path / "dos.log"
    second_log.write_text("hola\n", encoding="utf-8")
    ignored = tmp_path / "notes.txt"
    ignored.write_text("no es un log\n", encoding="utf-8")
    first_log = tmp_path / "uno.log"
    first_log.write_text("linea 1\nlinea 2\n", encoding="utf-8")

    status, logs = api.handle_request("GET", "/ui/logs", headers=auth_headers)
    assert status == HTTPStatus.OK
    expected_names = {
        "uno.log",
        "uno.log.1",
        "uno.log.1.gz",
        "dos.log",
        "errores.log.20240101.gz",
        "tres.log-20240101",
        "cuatro.log-20240101.gz",
    }
    assert {entry["name"] for entry in logs["files"]} == expected_names
    assert logs["selected"] is None or logs["selected"]["name"] in expected_names

    status, selected = api.handle_request(
        "GET", "/ui/logs", {"name": "uno.log"}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert selected["selected"]["name"] == "uno.log"
    assert "linea 1" in selected["selected"]["content"]

    status, dashed_selected = api.handle_request(
        "GET", "/ui/logs", {"name": "tres.log-20240101"}, headers=auth_headers
    )
    assert status == HTTPStatus.OK
    assert dashed_selected["selected"]["name"] == "tres.log-20240101"
    assert "linea con fecha" in dashed_selected["selected"]["content"]

    status, dashed_compressed_selected = api.handle_request(
        "GET",
        "/ui/logs",
        {"name": "cuatro.log-20240101.gz"},
        headers=auth_headers,
    )
    assert status == HTTPStatus.OK
    assert (
        dashed_compressed_selected["selected"]["name"] == "cuatro.log-20240101.gz"
    )
    assert "linea comprimida reciente" in dashed_compressed_selected["selected"]["content"]

    status, error = api.handle_request("POST", "/ui/logs", {"name": 123}, headers=auth_headers)
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"] == "'name' must be a string"


def test_ui_logs_reads_compressed_content(
    auth_headers: Mapping[str, str],
    tmp_path: Path,
    store: ConfigStore,
    schedule_store: ScheduleStore,
) -> None:
    api = ConfigAPI(store=store, schedule_store=schedule_store)
    status, body = api.handle_request("GET", "/ui/config", headers=auth_headers)
    assert status == HTTPStatus.OK

    values = dict(body["values"])
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(tmp_path)
    status, _ = api.handle_request("POST", "/ui/config", {"values": values}, headers=auth_headers)
    assert status == HTTPStatus.OK

    compressed_log = tmp_path / "service.log.gz"
    with gzip.open(compressed_log, "wt", encoding="utf-8") as handle:
        handle.write("línea A\n")
        handle.write("línea B\n")

    status, logs = api.handle_request(
        "POST",
        "/ui/logs",
        {"name": compressed_log.name},
        headers=auth_headers,
    )
    assert status == HTTPStatus.OK
    assert logs["selected"] is not None
    assert logs["selected"]["name"] == compressed_log.name
    assert logs["selected"].get("notice") is None
    assert logs.get("notice") is None
    assert logs["selected"]["content"] == "línea A\nlínea B\n"
