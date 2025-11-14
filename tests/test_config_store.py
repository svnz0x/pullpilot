from http import HTTPStatus
from pathlib import Path


import pytest

from pullpilot.app import Authenticator, ConfigAPI
from pullpilot.config import ConfigStore, PersistenceError, ValidationError
from pullpilot.schedule import ScheduleStore


@pytest.fixture()
def schema_path() -> Path:
    from pullpilot.resources import get_resource_path

    return get_resource_path("config/schema.json")


def ensure_required_paths(values: dict[str, object], tmp_path: Path) -> None:
    base_dir = tmp_path / "compose-base"
    log_dir = tmp_path / "compose-logs"
    base_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    values["BASE_DIR"] = str(base_dir)
    values["LOG_DIR"] = str(log_dir)


def test_load_defaults_when_config_missing(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    assert data.values["BASE_DIR"] == ""
    assert data.values["LOG_DIR"] == ""
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
    ensure_required_paths(values, tmp_path)
    values["LOG_RETENTION_DAYS"] = 21
    values["SMTP_CMD"] = "mailx"
    values["SMTP_READ_ENVELOPE"] = False

    store.save(values)

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
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    data.values["LOG_DIR"] = str(logs_dir)
    store.save(data.values)


def test_api_returns_persistence_error_payload(
    tmp_path: Path, schema_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)
    def fail_replace(src: str, dst: str) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr("pullpilot.config.os.replace", fail_replace)

    api = ConfigAPI(
        store=store,
        schedule_store=ScheduleStore(tmp_path / "schedule.json"),
        authenticator=Authenticator(token="secret-token"),
    )
    headers = {"Authorization": "Bearer secret-token"}

    status, body = api.handle_request(
        "POST",
        "/ui/config",
        {"values": values},
        headers=headers,
    )

    assert status == HTTPStatus.BAD_REQUEST
    assert body["error"] == "write failed"
    assert body["details"]
    detail = body["details"][0]
    assert detail["path"] == str(store.config_path)
    assert detail["operation"] == "write configuration"
    assert "permission denied" in detail["message"].lower()
    assert not any(
        path.name.startswith(f".{store.config_path.name}.") and path.suffix == ".tmp"
        for path in store.config_path.parent.iterdir()
    )


def test_validation_error_collects_all_fields(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)
    values["LOG_RETENTION_DAYS"] = 0
    values["BASE_DIR"] = ""

    with pytest.raises(ValidationError) as exc:
        store.save(values)

    messages = {error["field"] for error in exc.value.errors}
    assert "BASE_DIR" in messages
    assert "LOG_RETENTION_DAYS" in messages


def test_save_does_not_truncate_config_when_write_fails(
    tmp_path: Path, schema_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "updater.conf"
    original_content = 'BASE_DIR="/srv/compose"\n'
    config_path.write_text(original_content, encoding="utf-8")

    store = ConfigStore(config_path, schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)
    base_dir = tmp_path / "compose"
    base_dir.mkdir(exist_ok=True)
    values["BASE_DIR"] = str(base_dir)

    def fail_replace(src: str, dst: str) -> None:
        raise PermissionError("disk full")

    monkeypatch.setattr("pullpilot.config.os.replace", fail_replace)

    with pytest.raises(PersistenceError) as exc:
        store.save(values)

    detail = exc.value.details[0]
    assert detail["path"] == str(config_path)
    assert detail["operation"] == "write configuration"
    assert "disk full" in detail["message"].lower()

    assert config_path.read_text(encoding="utf-8") == original_content
    entries = {path.name for path in tmp_path.iterdir()}
    assert "updater.conf" in entries


def test_exclude_projects_accepts_absolute_paths(
    tmp_path: Path, schema_path: Path
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)

    values["EXCLUDE_PROJECTS"] = " /srv/app \n\n/srv/app/legacy \n"
    result = store.save(values)

    assert result.values["EXCLUDE_PROJECTS"] == "/srv/app\n/srv/app/legacy"


def test_exclude_projects_rejects_invalid_paths(
    tmp_path: Path, schema_path: Path
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)

    values["EXCLUDE_PROJECTS"] = "relative/path\n/srv/app\n/srv/../etc"

    with pytest.raises(ValidationError) as exc:
        store.save(values)

    errors = {error["field"] for error in exc.value.errors}
    assert "EXCLUDE_PROJECTS" in errors


def test_list_constraints_accept_whitespace_separated_values(
    tmp_path: Path, schema_path: Path
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)

    values["EXCLUDE_PATTERNS"] = "vendor tmp cache"
    result = store.save(values)

    assert result.values["EXCLUDE_PATTERNS"] == "vendor tmp cache"


@pytest.mark.parametrize(
    "exclude_value",
    ["", "   ", "vendor\ncache", "vendor\rcache"],
)
def test_list_constraints_reject_invalid_values(
    tmp_path: Path, schema_path: Path, exclude_value: str
) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)

    values["EXCLUDE_PATTERNS"] = exclude_value

    with pytest.raises(ValidationError) as exc:
        store.save(values)

    assert any(error["field"] == "EXCLUDE_PATTERNS" for error in exc.value.errors)


def test_compose_bin_accepts_safe_values(tmp_path: Path, schema_path: Path) -> None:
    store = ConfigStore(tmp_path / "updater.conf", schema_path)
    data = store.load()
    values = data.values.copy()
    ensure_required_paths(values, tmp_path)

    values["COMPOSE_BIN"] = " docker compose "
    result = store.save(values)
    assert result.values["COMPOSE_BIN"] == "docker compose"

    values = result.values.copy()
    ensure_required_paths(values, tmp_path)
    values["COMPOSE_BIN"] = "docker-compose"
    result = store.save(values)
    assert result.values["COMPOSE_BIN"] == "docker-compose"

    values = result.values.copy()
    ensure_required_paths(values, tmp_path)
    values["COMPOSE_BIN"] = "/usr/bin/docker compose"
    result = store.save(values)
    assert result.values["COMPOSE_BIN"] == "/usr/bin/docker compose"

    values = result.values.copy()
    ensure_required_paths(values, tmp_path)
    values["COMPOSE_BIN"] = "/opt/bin/docker-compose"
    result = store.save(values)
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
    ensure_required_paths(values, tmp_path)
    values["COMPOSE_BIN"] = compose_value

    with pytest.raises(ValidationError) as exc:
        store.save(values)

    assert any(error["field"] == "COMPOSE_BIN" for error in exc.value.errors)


def test_validate_config_cli_reports_errors(
    tmp_path: Path, schema_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "updater.conf"
    config_path.write_text("UNKNOWN=value\n", encoding="utf-8")

    import importlib.util

    module_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_config.py"
    spec = importlib.util.spec_from_file_location("validate_config_cli", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exit_code = module.main(["--config", str(config_path), "--schema", str(schema_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "UNKNOWN" in captured.out
