"""Tests for the scheduler watcher helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from pullpilot.scheduler import (
    DEFAULT_SCHEDULE_FILE,
    DEFAULT_SCHEDULE_PATH,
    SchedulerWatcher,
    resolve_default_updater_command,
)


class DummyProcess:
    """Minimal stand-in for ``subprocess.Popen`` return value."""

    def __init__(self, args: List[str]) -> None:
        self.args = args

    def poll(self) -> None:  # pragma: no cover - unused in tests
        return None


def test_run_once_uses_split_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: Dict[str, Any] = {}

    def fake_popen(args: List[str], *popen_args: Any, **popen_kwargs: Any) -> DummyProcess:
        calls["args"] = args
        return DummyProcess(args)

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    schedule_path = tmp_path / "schedule.json"
    cron_path = tmp_path / "schedule.cron"
    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hello world", 1.0)

    watcher._start_process({"mode": "once", "datetime": "2023-09-01T10:00:00Z"})

    expected = [
        sys.executable,
        "-m",
        "pullpilot.scheduler.run_once",
        "--at",
        "2023-09-01T10:00:00Z",
        "--",
        "echo",
        "hello",
        "world",
    ]

    assert calls["args"] == expected


def test_write_cron_file_creates_missing_parent(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "nested" / "cron" / "pullpilot.cron"
    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hello", 1.0)

    watcher._write_cron_file("* * * * *")

    assert cron_path.parent.is_dir()
    assert cron_path.read_text(encoding="utf-8") == "* * * * * echo hello\n"


def test_watcher_default_schedule_path_matches_store_default() -> None:
    assert DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_PATH


def test_default_updater_command_prefers_local_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_scripts = tmp_path / "scripts"
    local_scripts.mkdir()
    local_script = local_scripts / "updater.sh"
    local_script.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr("pullpilot.scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == str(local_script)


def test_default_updater_command_falls_back_to_packaged_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pullpilot.resources import get_resource_path

    monkeypatch.setattr("pullpilot.scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == str(
        get_resource_path("scripts/updater.sh")
    )


def test_scheduler_package_reexports_watcher() -> None:
    import pullpilot.scheduler as scheduler_pkg

    assert scheduler_pkg.SchedulerWatcher is SchedulerWatcher
    assert scheduler_pkg.DEFAULT_SCHEDULE_PATH == DEFAULT_SCHEDULE_PATH
    assert scheduler_pkg.DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_FILE


def test_once_completion_keeps_signature(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schedule_data = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}
    signature = json.dumps(schedule_data, sort_keys=True)

    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.1,
    )

    class DummySchedule:
        def to_dict(self) -> Dict[str, Any]:
            return schedule_data

    class DummyStore:
        def load(self) -> DummySchedule:
            return DummySchedule()

    watcher.store = DummyStore()  # type: ignore[assignment]
    watcher.current_signature = signature

    class FinishedProcess:
        def __init__(self) -> None:
            self.returncode = 0
            self.wait_calls = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            return self.returncode

    process = FinishedProcess()
    watcher.process = process  # type: ignore[assignment]

    started: List[Dict[str, Any]] = []

    def fake_start(self: SchedulerWatcher, schedule: Dict[str, Any]) -> None:
        started.append(schedule)

    monkeypatch.setattr(SchedulerWatcher, "_start_process", fake_start)

    class StopLoop(RuntimeError):
        pass

    def fake_sleep(_: float) -> None:
        raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with pytest.raises(StopLoop):
        watcher.run()

    assert started == []
    assert watcher.current_signature == signature
    assert watcher.process is None
    assert process.wait_calls == 1
