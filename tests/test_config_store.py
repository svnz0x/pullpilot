import logging
import os
from http import HTTPStatus
from pathlib import Path


import pytest

from pullpilot.app import Authenticator, ConfigAPI
from pullpilot.config import ConfigStore, ValidationError
from pullpilot.schedule import ScheduleStore


@pytest.fixture()
def schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "schema.json"


def test_load_defaults_when_config_missing(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    assert data.values["BASE_DIR"] == "/srv/compose"
    assert data.values["LOG_RETENTION_DAYS"] == 14
    assert data.values["SMTP_READ_ENVELOPE"] is True


def test_roundtrip_preserves_comments_and_quotes(tmp_path: Path, schema_path: Path) -> None:
    config_text = (
        "# sample configuration\n"
        "SMTP_CMD=\"msmtp\"           # command\n"
        "LOG_RETENTION_DAYS=14\n"
        "SMTP_READ_ENVELOPE=true    # inline\n"
    )
    config_path = tmp_path / "updater.conf"
    config_path.write_text(config_text, encoding="utf-8")
    store = ConfigStore(config_path, schema_path)

    data = store.load()
    values = data.values.copy()
    values["LOG_RETENTION_DAYS"] = 21
    values["SMTP_CMD"] = "mailx"
    values["SMTP_READ_ENVELOPE"] = False

    store.save(values, data.multiline)

    rendered = config_path.read_text(encoding="utf-8")
    assert "SMTP_CMD=\"mailx\"           # command" in rendered
    assert "LOG_RETENTION_DAYS=21" in rendered
    assert "SMTP_READ_ENVELOPE=false    # inline" in rendered
    assert rendered.splitlines()[0] == "# sample configuration"


def test_load_handles_crlf_line_endings(tmp_path: Path, schema_path: Path) -> None:
    config_text = (
        "# windows style configuration\r\n"
        "SMTP_CMD=\"msmtp\"\r\n"
        "BASE_DIR=\"/srv/compose\"\r\n"
        "SMTP_READ_ENVELOPE=false\r\n"
    )
    config_path = tmp_path / "updater.conf"
    config_path.write_text(config_text, encoding="utf-8")

    store = ConfigStore(config_path, schema_path)
    data = store.load()

    assert data.values["SMTP_CMD"] == "msmtp"
    assert "\r" not in data.values["SMTP_CMD"]
    assert data.values["BASE_DIR"] == "/srv/compose"
    assert "\r" not in data.values["BASE_DIR"]
    assert data.values["SMTP_READ_ENVELOPE"] is False

    # ensure saving does not raise validation errors after normalization
    store.save(data.values, data.multiline)


def test_multiline_file_roundtrip(tmp_path: Path, schema_path: Path) -> None:
    projects_path = tmp_path / "projects.txt"
    projects_path.write_text("/srv/app\n/srv/api\n", encoding="utf-8")
    config_path = tmp_path / "updater.conf"
    config_path.write_text(
        f"COMPOSE_PROJECTS_FILE=\"{projects_path}\"\n",
        encoding="utf-8",
    )

    store = ConfigStore(config_path, schema_path)
    data = store.load()
    assert data.multiline["COMPOSE_PROJECTS_FILE"] == "/srv/app\n/srv/api\n"

    values = data.values.copy()
    values["COMPOSE_PROJECTS_FILE"] = str(projects_path)
    multiline = data.multiline.copy()
    multiline["COMPOSE_PROJECTS_FILE"] = "/srv/ui\n"

    store.save(values, multiline)
    assert projects_path.read_text(encoding="utf-8") == "/srv/ui\n"


def test_multiline_load_handles_permission_error(
    tmp_path: Path,
    schema_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    projects_path = tmp_path / "projects.txt"
    projects_path.write_text("/srv/app\n", encoding="utf-8")
    os.chmod(projects_path, 0)

    config_path = tmp_path / "updater.conf"
    config_path.write_text(
        f'COMPOSE_PROJECTS_FILE="{projects_path}"\n',
        encoding="utf-8",
    )

    store = ConfigStore(config_path, schema_path)

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == projects_path:
            raise PermissionError("permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    caplog.set_level(logging.WARNING, logger="pullpilot.config")

    try:
        data = store.load()

        assert data.multiline["COMPOSE_PROJECTS_FILE"] == ""
        assert any(
            "No se pudo leer el contenido multilinea" in record.getMessage()
            for record in caplog.records
        )
    finally:
        os.chmod(projects_path, 0o600)


def test_api_returns_bad_request_when_multiline_path_inaccessible(
    tmp_path: Path,
    schema_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    target_path = tmp_path / "restricted" / "projects.txt"
    values["COMPOSE_PROJECTS_FILE"] = str(target_path)
    multiline = data.multiline.copy()
    multiline["COMPOSE_PROJECTS_FILE"] = "/srv/app\n"

    original_resolve = Path.resolve

    def guarded_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self == target_path:
            raise PermissionError("permission denied")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)

    api = ConfigAPI(
        store=store,
        schedule_store=ScheduleStore(tmp_path / "schedule.json"),
        authenticator=Authenticator(token="secret-token"),
    )
    headers = {"Authorization": "Bearer secret-token"}

    status, body = api.handle_request(
        "POST",
        "/ui/config",
        {"values": values, "multiline": multiline},
        headers=headers,
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert {
        "field": "COMPOSE_PROJECTS_FILE",
        "message": "path is not accessible",
    } in body.get("details", [])


def test_validation_error_collects_all_fields(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    values["LOG_RETENTION_DAYS"] = 0
    values.pop("BASE_DIR")

    with pytest.raises(ValidationError) as exc:
        store.save(values, data.multiline)

    messages = {error["field"] for error in exc.value.errors}
    assert "BASE_DIR" in messages
    assert "LOG_RETENTION_DAYS" in messages


def test_save_does_not_touch_config_when_multiline_fails(
    tmp_path: Path, schema_path: Path
) -> None:
    config_path = tmp_path / "updater.conf"
    original_content = 'BASE_DIR="/srv/compose"\n'
    config_path.write_text(original_content, encoding="utf-8")

    store = ConfigStore(config_path, schema_path)
    data = store.load()
    values = data.values.copy()
    multiline = data.multiline.copy()
    multiline["COMPOSE_PROJECTS_FILE"] = "/srv/app\n"

    with pytest.raises(ValidationError):
        store.save(values, multiline)

    assert config_path.read_text(encoding="utf-8") == original_content


def test_save_does_not_truncate_config_when_write_fails(
    tmp_path: Path, schema_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "updater.conf"
    original_content = 'BASE_DIR="/srv/compose"\n'
    config_path.write_text(original_content, encoding="utf-8")

    store = ConfigStore(config_path, schema_path)
    data = store.load()
    values = data.values.copy()
    values["BASE_DIR"] = "/srv/other"

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("pullpilot.config.os.replace", fail_replace)

    with pytest.raises(OSError):
        store.save(values, data.multiline)

    assert config_path.read_text(encoding="utf-8") == original_content
    assert {path.name for path in tmp_path.iterdir()} == {"updater.conf"}


def test_multiline_save_does_not_truncate_file_when_write_fails(
    tmp_path: Path, schema_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "updater.conf"
    projects_path = tmp_path / "projects.txt"
    original_projects = "/srv/app\n"
    projects_path.write_text(original_projects, encoding="utf-8")
    config_path.write_text(
        f'COMPOSE_PROJECTS_FILE="{projects_path}"\n', encoding="utf-8"
    )

    store = ConfigStore(config_path, schema_path)
    data = store.load()
    values = data.values.copy()
    multiline = data.multiline.copy()
    multiline["COMPOSE_PROJECTS_FILE"] = "/srv/other\n"

    original_replace = os.replace

    def fail_replace(src: str, dst: str) -> None:
        if Path(dst) == projects_path:
            raise OSError("disk full")
        original_replace(src, dst)

    monkeypatch.setattr("pullpilot.config.os.replace", fail_replace)

    with pytest.raises(OSError):
        store.save(values, multiline)

    assert config_path.read_text(encoding="utf-8") == (
        f'COMPOSE_PROJECTS_FILE="{projects_path}"\n'
    )
    assert projects_path.read_text(encoding="utf-8") == original_projects
    assert {path.name for path in tmp_path.iterdir()} == {"updater.conf", "projects.txt"}


def test_multiline_path_must_reside_in_allowed_directory(
    tmp_path: Path, schema_path: Path
) -> None:
    config_path = tmp_path / "updater.conf"
    config_path.write_text('COMPOSE_PROJECTS_FILE=""\n', encoding="utf-8")
    store = ConfigStore(config_path, schema_path)

    data = store.load()
    values = data.values.copy()
    values["COMPOSE_PROJECTS_FILE"] = str(tmp_path.parent / "escape.txt")
    multiline = {"COMPOSE_PROJECTS_FILE": "/srv/app\n"}

    with pytest.raises(ValidationError) as exc:
        store.save(values, multiline)

    assert any(error["field"] == "COMPOSE_PROJECTS_FILE" for error in exc.value.errors)
    assert not (tmp_path.parent / "escape.txt").exists()


def test_multiline_path_rejects_parent_segments(
    tmp_path: Path, schema_path: Path
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    multiline = data.multiline.copy()

    values["COMPOSE_PROJECTS_FILE"] = "/tmp/../etc/passwd"
    multiline["COMPOSE_PROJECTS_FILE"] = "/srv/app\n"

    with pytest.raises(ValidationError) as exc:
        store.save(values, multiline)

    assert any(error["field"] == "COMPOSE_PROJECTS_FILE" for error in exc.value.errors)


def test_compose_bin_accepts_safe_values(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()

    values["COMPOSE_BIN"] = " docker compose "
    result = store.save(values, data.multiline)
    assert result.values["COMPOSE_BIN"] == "docker compose"

    values = result.values.copy()
    values["COMPOSE_BIN"] = "docker-compose"
    result = store.save(values, data.multiline)
    assert result.values["COMPOSE_BIN"] == "docker-compose"

    values = result.values.copy()
    values["COMPOSE_BIN"] = "/usr/bin/docker compose"
    result = store.save(values, data.multiline)
    assert result.values["COMPOSE_BIN"] == "/usr/bin/docker compose"

    values = result.values.copy()
    values["COMPOSE_BIN"] = "/opt/bin/docker-compose"
    result = store.save(values, data.multiline)
    assert result.values["COMPOSE_BIN"] == "/opt/bin/docker-compose"


@pytest.mark.parametrize(
    "compose_value",
    [
        "docker; compose",
        "docker -c 'rm -rf /'",
        'docker "compose',
        "docker compose --ansi never",
        "/tmp/docker",
        "/tmp/docker-compose --version",
    ],
)
def test_compose_bin_rejects_dangerous_values(
    tmp_path: Path, schema_path: Path, compose_value: str
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    values["COMPOSE_BIN"] = compose_value

    with pytest.raises(ValidationError) as exc:
        store.save(values, data.multiline)

    assert any(error["field"] == "COMPOSE_BIN" for error in exc.value.errors)
