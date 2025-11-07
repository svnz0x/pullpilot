from pathlib import Path


import pytest

from pullpilot.config import ConfigStore, ValidationError


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
