"""Tests for the scheduler watcher helpers."""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest

import pullpilot.scheduler.watch as watch_module
from pullpilot.resources import get_resource_path
from pullpilot.scheduler.watch import (
    DEFAULT_COMMAND,
    DEFAULT_INTERVAL,
    DEFAULT_SCHEDULE_FILE,
    DEFAULT_SCHEDULE_PATH,
    SchedulerWatcher,
    build_watcher,
    resolve_default_updater_command,
)
from pullpilot.schedule import DEFAULT_CRON_EXPRESSION, SchedulePersistenceError


class DummyProcess:
    """Minimal stand-in for ``subprocess.Popen`` return value."""

    def __init__(self, args: List[str]) -> None:
        self.args = args

    def poll(self) -> None:  # pragma: no cover - unused in tests
        return None


class FinishedDummyProcess:
    """Dummy process that has already exited."""

    def __init__(self) -> None:
        self.wait_calls: List[float | None] = []

    def poll(self) -> int:
        return 0

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return 0

    def terminate(self) -> None:  # pragma: no cover - defensive
        raise AssertionError("terminate should not be called")

    def kill(self) -> None:  # pragma: no cover - defensive
        raise AssertionError("kill should not be called")


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


def test_write_cron_file_quotes_command_with_spaces(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "pullpilot.cron"
    updater_command = '"/path/with space/updater.sh" --flag value'
    watcher = SchedulerWatcher(schedule_path, cron_path, updater_command, 1.0)

    watcher._write_cron_file("0 * * * *")

    expected = "0 * * * * '/path/with space/updater.sh' --flag value\n"
    assert cron_path.read_text(encoding="utf-8") == expected


def test_write_cron_file_preserves_environment_assignments(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "pullpilot.cron"
    updater_command = "FOO=bar '/path/with space/updater.sh' --flag value"
    watcher = SchedulerWatcher(schedule_path, cron_path, updater_command, 1.0)

    watcher._write_cron_file("15 4 * * *")

    expected = "15 4 * * * FOO=bar '/path/with space/updater.sh' --flag value\n"
    assert cron_path.read_text(encoding="utf-8") == expected


def test_write_cron_file_quotes_assignment_values_with_spaces(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "pullpilot.cron"
    updater_command = 'FOO="two words" /path/script'
    watcher = SchedulerWatcher(schedule_path, cron_path, updater_command, 1.0)

    watcher._write_cron_file("30 6 * * *")

    expected = "30 6 * * * FOO='two words' /path/script\n"
    assert cron_path.read_text(encoding="utf-8") == expected


def test_write_cron_file_replace_failure_keeps_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")

    cron_path = tmp_path / "pullpilot.cron"
    cron_path.write_text("ORIGINAL\n", encoding="utf-8")

    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hi", 1.0)

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("boom")

    monkeypatch.setattr("pullpilot.scheduler.watch.os.replace", failing_replace)

    with caplog.at_level(logging.INFO, logger="pullpilot.scheduler.watch"):
        with pytest.raises(OSError):
            watcher._write_cron_file("* * * * *")

    assert cron_path.read_text(encoding="utf-8") == "ORIGINAL\n"
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pullpilot.scheduler.watch"
    ]
    assert any("No se pudo reemplazar el archivo cron temporal" in entry for entry in messages)


def test_watcher_default_schedule_path_matches_store_default() -> None:
    assert DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_PATH


def test_default_updater_command_prefers_canonical_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = tmp_path / "resources" / "scripts" / "updater.sh"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(watch_module, "CANONICAL_UPDATER", canonical)

    assert resolve_default_updater_command() == str(canonical)


@pytest.mark.parametrize(
    "wrapper_subpath",
    [
        Path("apps/backend/scripts/updater.sh"),
        Path("apps/backend/tools/updater.sh"),
    ],
)
def test_default_updater_command_falls_back_to_wrappers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wrapper_subpath: Path
) -> None:
    monkeypatch.setattr(
        watch_module, "CANONICAL_UPDATER", tmp_path / "does-not-exist.sh"
    )

    wrapper = tmp_path / wrapper_subpath
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr("pullpilot.scheduler.watch._project_root", lambda: tmp_path)

    assert resolve_default_updater_command() == str(wrapper)


def test_default_updater_command_falls_back_to_default_string(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        watch_module, "CANONICAL_UPDATER", tmp_path / "missing.sh"
    )
    monkeypatch.setattr("pullpilot.scheduler.watch._project_root", lambda: tmp_path)
    def missing_resource(_: str) -> Path:
        raise FileNotFoundError

    monkeypatch.setattr("pullpilot.scheduler.watch.get_resource_path", missing_resource)

    assert resolve_default_updater_command() == DEFAULT_COMMAND


def test_default_updater_command_uses_packaged_resource(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        watch_module, "CANONICAL_UPDATER", tmp_path / "missing.sh"
    )
    monkeypatch.setattr("pullpilot.scheduler.watch._project_root", lambda: tmp_path)

    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if str(self) == DEFAULT_COMMAND:
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    expected = str(get_resource_path("scripts/updater.sh"))

    assert resolve_default_updater_command() == expected


def test_scheduler_package_reexports_watcher() -> None:
    import pullpilot.scheduler as scheduler_pkg

    assert scheduler_pkg.SchedulerWatcher is SchedulerWatcher
    assert scheduler_pkg.DEFAULT_SCHEDULE_PATH == DEFAULT_SCHEDULE_PATH
    assert scheduler_pkg.DEFAULT_SCHEDULE_FILE == DEFAULT_SCHEDULE_FILE


def test_cron_write_error_is_logged_and_loop_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    schedule_path = tmp_path / "schedule.json"
    cron_path = tmp_path / "cron" / "pullpilot.cron"
    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hi", DEFAULT_INTERVAL)

    schedule_data = {"mode": "cron", "expression": "* * * * *"}

    class DummySchedule:
        def to_dict(self) -> Dict[str, Any]:
            return schedule_data

    class DummyStore:
        def load(self) -> DummySchedule:
            return DummySchedule()

    watcher.store = DummyStore()  # type: ignore[assignment]

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("pullpilot.scheduler.watch.os.replace", failing_replace)

    class SingleLoopEvent:
        def is_set(self) -> bool:
            return False

        def wait(self, interval: float) -> bool:
            return True

    with caplog.at_level(logging.INFO, logger="pullpilot.scheduler.watch"):
        watcher.run(stop_event=SingleLoopEvent())

    assert watcher.current_signature is None
    assert watcher.process is None
    module_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pullpilot.scheduler.watch"
    ]
    assert any("No se pudo preparar el archivo cron" in entry for entry in module_messages)
    assert any(
        "No se pudo reemplazar el archivo cron temporal" in entry
        for entry in module_messages
    )
    assert all("Iniciando supercronic" not in entry for entry in module_messages)


def test_run_logs_permission_error_and_continues(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text("{}", encoding="utf-8")
    cron_path = tmp_path / "schedule.cron"

    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hi", DEFAULT_INTERVAL)

    original_read_text = Path.read_text

    def failing_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == schedule_path:
            raise PermissionError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)

    class SingleLoopEvent:
        def is_set(self) -> bool:
            return False

        def wait(self, interval: float) -> bool:
            return True

    with caplog.at_level(logging.INFO, logger="pullpilot.scheduler.watch"):
        with caplog.at_level(logging.WARNING, logger="pullpilot.schedule"):
            watcher.run(stop_event=SingleLoopEvent())

    assert watcher.current_signature is None
    assert watcher.process is None
    module_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pullpilot.scheduler.watch"
    ]
    assert any("No se pudo interpretar la programación" in entry for entry in module_messages)
    assert any(
        record.name == "pullpilot.schedule" and "Permission denied" in record.getMessage()
        for record in caplog.records
    )


def test_once_completion_resets_schedule_via_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schedule_data = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}
    signature = json.dumps(schedule_data, sort_keys=True)

    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.1,
    )

    default_schedule = {"mode": "cron", "expression": DEFAULT_CRON_EXPRESSION}

    class DummySchedule:
        def __init__(self, data: Dict[str, Any]) -> None:
            self.data = data

        def to_dict(self) -> Dict[str, Any]:
            return self.data

    class DummyStore:
        def __init__(self) -> None:
            self.saved: List[Dict[str, Any]] = []

        def load(self) -> DummySchedule:
            return DummySchedule(schedule_data)

        def save(self, payload: Dict[str, Any]) -> DummySchedule:
            self.saved.append(payload)
            return DummySchedule(default_schedule)

    watcher.store = DummyStore()  # type: ignore[assignment]
    store = watcher.store
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

    def fake_start(self: SchedulerWatcher, schedule: Dict[str, Any]) -> bool:
        started.append(schedule)
        return True

    monkeypatch.setattr(SchedulerWatcher, "_start_process", fake_start)

    class StopLoop(RuntimeError):
        pass

    def fake_sleep(_: float) -> None:
        raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with pytest.raises(StopLoop):
        watcher.run()

    assert store.saved == [default_schedule]
    assert started == [default_schedule]
    assert watcher.current_signature == json.dumps(default_schedule, sort_keys=True)
    assert watcher.process is None
    assert process.wait_calls == 1


def test_once_completion_resets_schedule_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schedule_path = tmp_path / "pullpilot.schedule"
    cron_path = tmp_path / "pullpilot.cron"
    schedule_data = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}
    schedule_path.write_text(json.dumps(schedule_data), encoding="utf-8")

    watcher = SchedulerWatcher(schedule_path, cron_path, "echo hi", 0.01)
    once_signature = json.dumps(schedule_data, sort_keys=True)
    watcher.current_signature = once_signature

    class FinishedProcess:
        def __init__(self) -> None:
            self.returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    watcher.process = FinishedProcess()  # type: ignore[assignment]

    started: List[Dict[str, Any]] = []

    def fake_start(self: SchedulerWatcher, schedule: Dict[str, Any]) -> bool:
        started.append(schedule)
        return True

    monkeypatch.setattr(SchedulerWatcher, "_start_process", fake_start)

    class StopLoop(RuntimeError):
        pass

    sleep_calls = 0

    def fake_sleep(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with pytest.raises(StopLoop):
        watcher.run()

    saved_schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    assert saved_schedule == {"mode": "cron", "expression": DEFAULT_CRON_EXPRESSION}
    assert started == [{"mode": "cron", "expression": DEFAULT_CRON_EXPRESSION}]
    assert watcher.current_signature == json.dumps(
        {"mode": "cron", "expression": DEFAULT_CRON_EXPRESSION}, sort_keys=True
    )


def test_once_completion_reset_failure_logs_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    schedule_data = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}
    signature = json.dumps(schedule_data, sort_keys=True)

    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.1,
    )
    failing_path = watcher.store.schedule_path

    class DummySchedule:
        def to_dict(self) -> Dict[str, Any]:
            return schedule_data

    class DummyStore:
        def __init__(self, path: Path) -> None:
            self.path = path

        def load(self) -> DummySchedule:
            return DummySchedule()

        def save(self, payload: Dict[str, Any]) -> DummySchedule:
            raise SchedulePersistenceError(
                path=self.path,
                operation="write",
                error=OSError("disk full"),
            )

    watcher.store = DummyStore(failing_path)  # type: ignore[assignment]
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

    def fake_start(self: SchedulerWatcher, schedule: Dict[str, Any]) -> bool:
        started.append(schedule)
        return True

    monkeypatch.setattr(SchedulerWatcher, "_start_process", fake_start)

    class StopLoop(RuntimeError):
        pass

    def fake_sleep(_: float) -> None:
        raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with caplog.at_level(logging.WARNING, logger="pullpilot.scheduler.watch"):
        with pytest.raises(StopLoop):
            watcher.run()

    module_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pullpilot.scheduler.watch"
    ]
    assert any("No se pudo restablecer la programación predeterminada" in entry for entry in module_messages)
    assert started == []
    assert watcher.current_signature == signature
    assert watcher.process is None
    assert process.wait_calls == 1


def test_run_handles_missing_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    schedule_data = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}

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

    def fake_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("missing binary")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    class StopLoop(RuntimeError):
        pass

    def fake_sleep(_: float) -> None:
        raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with caplog.at_level(logging.INFO, logger="pullpilot.scheduler.watch"):
        with pytest.raises(StopLoop):
            watcher.run()

    module_messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "pullpilot.scheduler.watch"
    ]
    assert any("No se pudo iniciar la ejecución única" in entry for entry in module_messages)
    assert watcher.process is None
    assert watcher.current_signature is None


def test_run_keeps_process_alive_when_schedule_load_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    initial_schedule = {"mode": "once", "datetime": "2023-09-01T10:00:00Z"}
    initial_signature = json.dumps(initial_schedule, sort_keys=True)
    new_schedule = {"mode": "once", "datetime": "2023-09-01T12:00:00Z"}
    new_signature = json.dumps(new_schedule, sort_keys=True)

    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.01,
    )
    watcher.current_signature = initial_signature

    class ActiveProcess:
        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> None:
            pass

        def kill(self) -> None:  # pragma: no cover - defensive
            self.terminated = True

    running_process = ActiveProcess()
    watcher.process = running_process  # type: ignore[assignment]

    class DummySchedule:
        def __init__(self, data: Dict[str, Any]) -> None:
            self.data = data

        def to_dict(self) -> Dict[str, Any]:
            return self.data

    class FlakyStore:
        def __init__(self) -> None:
            self.calls = 0

        def load(self) -> DummySchedule:
            self.calls += 1
            if self.calls == 1:
                raise json.JSONDecodeError("boom", "{}", 0)
            return DummySchedule(new_schedule)

    store = FlakyStore()
    watcher.store = store  # type: ignore[assignment]

    stop_store_calls: List[int] = []
    original_stop = SchedulerWatcher._stop_process

    def tracking_stop(self: SchedulerWatcher) -> None:
        stop_store_calls.append(store.calls)
        original_stop(self)

    monkeypatch.setattr(SchedulerWatcher, "_stop_process", tracking_stop)

    started: List[Dict[str, Any]] = []
    started_processes: List[ActiveProcess] = []

    def fake_start(self: SchedulerWatcher, schedule: Dict[str, Any]) -> bool:
        started.append(schedule)
        new_process = ActiveProcess()
        started_processes.append(new_process)
        self.process = new_process  # type: ignore[assignment]
        return True

    monkeypatch.setattr(SchedulerWatcher, "_start_process", fake_start)

    class StopLoop(RuntimeError):
        pass

    observed_processes: List[ActiveProcess | None] = []

    def fake_sleep(_: float) -> None:
        observed_processes.append(watcher.process)  # type: ignore[arg-type]
        if len(observed_processes) >= 2:
            raise StopLoop()

    monkeypatch.setattr("pullpilot.scheduler.watch.time.sleep", fake_sleep)

    with pytest.raises(StopLoop):
        watcher.run()

    # After the first failed load, the running process remains active and _stop_process wasn't
    # triggered until the schedule recovered (store.calls == 2). The final call corresponds to the
    # teardown in the ``finally`` block when the loop exits.
    assert observed_processes[0] is running_process
    assert stop_store_calls == [2, 2]

    # Once a valid schedule is available the watcher restarts the process with the new signature.
    assert started == [new_schedule]
    assert started_processes
    assert watcher.current_signature == new_signature
    assert stop_store_calls[0] == 2
    assert started_processes[0] is not running_process

def test_run_respects_stop_event(tmp_path: Path) -> None:
    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.01,
    )

    stop_event = threading.Event()

    thread = threading.Thread(target=watcher.run, args=(stop_event,), daemon=True)
    thread.start()
    stop_event.set()
    thread.join(timeout=1)

    assert not thread.is_alive()


def test_build_watcher_uses_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    expected_command = "dummy-command"

    monkeypatch.setattr(
        "pullpilot.scheduler.watch.resolve_default_updater_command",
        lambda: expected_command,
    )

    watcher = build_watcher(schedule_path=schedule_path)

    assert watcher.store.schedule_path == schedule_path
    assert watcher.cron_path == schedule_path.with_name(f"{schedule_path.name}.cron")
    assert watcher.updater_command == expected_command
    assert watcher.interval == DEFAULT_INTERVAL


def test_scheduler_watcher_derives_cron_path(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    watcher = SchedulerWatcher(schedule_path, None, "echo hi", DEFAULT_INTERVAL)

    assert watcher.cron_path == schedule_path.with_name(f"{schedule_path.name}.cron")


def test_stop_process_handles_finished_process(tmp_path: Path) -> None:
    watcher = SchedulerWatcher(
        tmp_path / "schedule.json",
        tmp_path / "schedule.cron",
        "echo hi",
        0.1,
    )

    finished = FinishedDummyProcess()
    watcher.process = finished  # type: ignore[assignment]

    watcher._stop_process()

    assert watcher.process is None
    assert finished.wait_calls == [None]
