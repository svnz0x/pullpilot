from pathlib import Path

import json

import pytest

from pullpilot.schedule import (
    DEFAULT_SCHEDULE_PATH,
    ScheduleStore,
    ScheduleValidationError,
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


def test_save_rejects_invalid_cron(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": "bad"})


def test_save_rejects_every_without_interval(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    with pytest.raises(ScheduleValidationError):
        store.save({"mode": "cron", "expression": "@every"})


def test_save_normalizes_datetime(schedule_path: Path) -> None:
    store = ScheduleStore(schedule_path)
    saved = store.save({"mode": "once", "datetime": "2035-12-01T23:15:00+02:00"})
    assert saved.mode == "once"
    assert saved.datetime.endswith("+00:00")


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


def test_default_schedule_path_points_to_config_dir() -> None:
    expected = Path(__file__).resolve().parents[1] / "config" / "pullpilot.schedule"
    assert DEFAULT_SCHEDULE_PATH == expected
