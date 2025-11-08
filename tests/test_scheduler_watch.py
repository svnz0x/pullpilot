"""Tests for the scheduler watcher helpers."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from pullpilot.schedule import DEFAULT_SCHEDULE_PATH
from scheduler.watch import (
    DEFAULT_SCHEDULE_FILE,
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
        "scheduler.run_once",
        "--at",
        "2023-09-01T10:00:00Z",
        "--",
        "echo",
        "hello",
        "world",
    ]

    assert calls["args"] == expected


def test_watcher_default_schedule_path_matches_store_default() -> None:
    assert DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_PATH


def test_default_updater_command_prefers_local_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_scripts = tmp_path / "scripts"
    local_scripts.mkdir()
    local_script = local_scripts / "updater.sh"
    local_script.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr("scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == str(local_script)


def test_default_updater_command_falls_back_to_container_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == "/app/updater.sh"


def test_watch_module_imports_without_src_path(monkeypatch: pytest.MonkeyPatch) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    resolved_src = src_dir.resolve()

    sanitized_path: List[str] = []
    for entry in sys.path:
        try:
            entry_path = Path(entry or ".").resolve()
        except (OSError, RuntimeError):
            entry_path = Path(entry)
        if entry_path != resolved_src:
            sanitized_path.append(entry)

    assert all(Path(p or ".").resolve() != resolved_src for p in sanitized_path)
    monkeypatch.setattr(sys, "path", sanitized_path)

    for module_name in ["scheduler.watch", "pullpilot.schedule", "pullpilot"]:
        sys.modules.pop(module_name, None)

    module = importlib.import_module("scheduler.watch")

    assert module.DEFAULT_SCHEDULE_PATH is not None
    assert str(resolved_src) in sys.path


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

    monkeypatch.setattr("scheduler.watch.time.sleep", fake_sleep)

    with pytest.raises(StopLoop):
        watcher.run()

    assert started == []
    assert watcher.current_signature == signature
    assert watcher.process is None
    assert process.wait_calls == 1
