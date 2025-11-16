from pathlib import Path

import json

import pytest

from pullpilot.schedule import (
    DEFAULT_SCHEDULE_PATH,
    ScheduleStore,
    ScheduleValidationError,
    normalize_datetime_utc,
)


@pytest.fixture()
def schedule_path(tmp_path: Path) -> Path:
    return tmp_path / "schedule.json"


def test_load_returns_default_when_missing(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    data = store.load()
    assert data.mode == "cron"
    assert data.expression == "0 4 * * *"


def test_save_and_reload_cron(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    saved = store.save({"mode": "cron", "expression": "15 6 * * 2"})
    assert saved.expression == "15 6 * * 2"
    raw = json.loads(schedule_path.read_text(encoding="utf-8"))
    assert raw["expression"] == "15 6 * * 2"
    reloaded = store.load()
    assert reloaded.expression == "15 6 * * 2"


def test_save_accepts_macros(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    saved = store.save({"mode": "cron", "expression": "@hourly"})
    assert saved.expression == "@hourly"


@pytest.mark.parametrize("expression", ["@every 5m", "@every 1h30m"])
def test_save_accepts_every_durations(schedule_path: Path, expression: str) -> None:
    store = ScheduleStore(schedule_path)
    saved = store.save({"mode": "cron", "expression": expression})
    assert saved.expression == expression


def test_save_rejects_invalid_cron(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": "bad"})


def test_save_rejects_datetime_when_cron(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError) as excinfo:
        store.save({"mode": "cron", "expression": "5 4 * * *", "datetime": "2030-01-01T00:00:00Z"})
    assert excinfo.value.field == "datetime"


def test_save_rejects_every_without_interval(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": "@every"})


@pytest.mark.parametrize("expression", ["@every potato", "@every 5m 10s"])
def test_save_rejects_invalid_every_durations(
    schedule_path: Path, expression: str
) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": expression})


@pytest.mark.parametrize("expression", ["@every -5m", "@every 0s", "@every 0h"]) 
def test_save_rejects_non_positive_every_durations(
    schedule_path: Path, expression: str
) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": expression})


def test_save_preserves_existing_file_on_write_failure(
    schedule_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_payload = {"mode": "cron", "expression": "0 0 * * *"}
    schedule_path.write_text(json.dumps(original_payload), encoding="utf-8")
    store = ScheduleStore(schedule_path)

    def explode(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr("pullpilot.schedule.json.dump", explode)

    with pytest.raises(RuntimeError):
        store.save({"mode": "cron", "expression": "10 5 * * 1"})

    assert schedule_path.exists()
    assert json.loads(schedule_path.read_text(encoding="utf-8")) == original_payload


def test_save_normalizes_datetime(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    raw_value = "2035-12-01T23:15:00+02:00"
    saved = store.save({"mode": "once", "datetime": raw_value})
    assert saved.mode == "once"
    expected = normalize_datetime_utc(raw_value).isoformat()
    assert saved.datetime == expected


def test_save_rejects_expression_when_once(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError) as excinfo:
        store.save({"mode": "once", "datetime": "2035-12-01T23:15:00+02:00", "expression": "@daily"})
    assert excinfo.value.field == "expression"


def test_default_path_uses_config_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "config" / "pullpilot.schedule"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"mode": "cron", "expression": "5 1 * * *"}), encoding="utf-8")
    monkeypatch.setattr("pullpilot.schedule.DEFAULT_SCHEDULE_PATH", target)

    store = ScheduleStore()
    loaded = store.load()
    assert loaded.expression == "5 1 * * *"

    saved = store.save({"mode": "cron", "expression": "45 3 * * 3"})
    assert saved.expression == "45 3 * * 3"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["expression"] == "45 3 * * 3"


def test_load_logs_and_raises_when_permission_denied(
    schedule_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    schedule_path.write_text("{}", encoding="utf-8")
    store = ScheduleStore(schedule_path)

    original_read_text = Path.read_text

    def failing_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == schedule_path:
            raise PermissionError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)

    with caplog.at_level("WARNING", logger="pullpilot.schedule"):
        with pytest.raises(ScheduleValidationError) as excinfo:
            store.load()

    assert "revisa los permisos" in str(excinfo.value)
    assert any("Permission denied" in record.getMessage() for record in caplog.records)


def test_default_schedule_path_points_to_packaged_file() -> None:
    from pullpilot.resources import get_resource_path

    expected = get_resource_path("config/pullpilot.schedule")
    assert DEFAULT_SCHEDULE_PATH == expected
