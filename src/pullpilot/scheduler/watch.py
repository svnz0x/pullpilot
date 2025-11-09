"""Watch the shared schedule file and (re)start the runner when it changes."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from threading import Event
from pathlib import Path
from typing import Any, Dict, Optional

from ..resources import get_resource_path
from ..schedule import DEFAULT_SCHEDULE_PATH, ScheduleStore, ScheduleValidationError

DEFAULT_SCHEDULE_FILE = DEFAULT_SCHEDULE_PATH
DEFAULT_CRON_FILE = Path("/tmp/pullpilot.cron")
DEFAULT_COMMAND = "/app/updater.sh"
DEFAULT_INTERVAL = 5.0


class SchedulerWatcher:
    """Monitor the schedule file and spawn the right worker process."""

    def __init__(
        self,
        schedule_path: Path,
        cron_path: Path,
        updater_command: str,
        interval: float,
    ) -> None:
        self.store = ScheduleStore(schedule_path)
        self.cron_path = cron_path
        self.updater_command = updater_command
        self.interval = interval
        self.current_signature: Optional[str] = None
        self.process: Optional[subprocess.Popen[bytes]] = None

    # ------------------------------------------------------------------
    def run(self, stop_event: Event | None = None) -> None:
        try:
            while not (stop_event and stop_event.is_set()):
                load_failed = False
                try:
                    schedule = self.store.load().to_dict()
                    signature = json.dumps(schedule, sort_keys=True)
                except (ScheduleValidationError, json.JSONDecodeError) as exc:
                    _log(f"No se pudo interpretar la programación: {exc}")
                    schedule = None
                    signature = self.current_signature
                    load_failed = True

                if self.process and self.process.poll() is not None:
                    code = self.process.returncode
                    mode = schedule.get("mode") if isinstance(schedule, dict) else None
                    if mode == "once" and code == 0:
                        _log(
                            "El proceso programador finalizó con código 0; ejecución única completada"
                        )
                        try:
                            self.process.wait()
                        finally:
                            self.process = None
                    else:
                        _log(
                            f"El proceso programador finalizó con código {code}; reiniciando"
                        )
                        self._stop_process()
                        self.current_signature = None

                if signature != self.current_signature:
                    self._stop_process()
                    if schedule:
                        started = self._start_process(schedule)
                        if started:
                            self.current_signature = signature
                        else:
                            self.current_signature = None
                    else:
                        if not load_failed:
                            self.current_signature = None
                if stop_event:
                    if stop_event.wait(self.interval):
                        break
                else:
                    time.sleep(self.interval)
        except KeyboardInterrupt:  # pragma: no cover - manual interruption
            _log("Interrumpido, deteniendo programador")
        finally:
            self._stop_process()

    # ------------------------------------------------------------------
    def _start_process(self, schedule: Dict[str, Any]) -> bool:
        mode = schedule.get("mode")
        if mode == "cron":
            expression = schedule.get("expression")
            if not isinstance(expression, str):
                _log("Expresión cron inválida; omitiendo")
                return True
            try:
                self._write_cron_file(expression)
            except OSError as exc:
                _log(f"No se pudo preparar el archivo cron: {exc}")
                return False
            _log(f"Iniciando supercronic con expresión '{expression}'")
            try:
                self.process = subprocess.Popen(["supercronic", "-quiet", str(self.cron_path)])
            except (FileNotFoundError, OSError) as exc:
                _log(f"No se pudo iniciar supercronic: {exc}")
                self.process = None
                return False
            return True
        if mode == "once":
            datetime_value = schedule.get("datetime")
            if not isinstance(datetime_value, str):
                _log("Fecha/hora inválida; omitiendo")
                return True
            try:
                command_args = shlex.split(self.updater_command)
            except ValueError:
                command_args = [self.updater_command]
            _log(f"Planificando ejecución única para {datetime_value}")
            try:
                self.process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "pullpilot.scheduler.run_once",
                        "--at",
                        datetime_value,
                        "--",
                        *command_args,
                    ]
                )
            except (FileNotFoundError, OSError) as exc:
                _log(f"No se pudo iniciar la ejecución única: {exc}")
                self.process = None
                return False
            return True
        _log(f"Modo desconocido '{mode}'; no se inicia ningún proceso")
        return True

    def _write_cron_file(self, expression: str) -> None:
        self.cron_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            command_args = shlex.split(self.updater_command)
        except ValueError:
            command_args = [self.updater_command]
        escaped_command = " ".join(shlex.quote(arg) for arg in command_args)
        self.cron_path.write_text(
            f"{expression} {escaped_command}\n", encoding="utf-8"
        )

    def _stop_process(self) -> None:
        process = self.process
        if not process:
            return
        self.process = None

        poll_result = process.poll()
        if poll_result is not None:
            try:
                process.wait()
            except Exception:  # pragma: no cover - defensive
                pass
            return

        _log("Deteniendo proceso programador actual")
        try:
            process.terminate()
        except ProcessLookupError:
            try:
                process.wait()
            except Exception:  # pragma: no cover - defensive
                pass
            return

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _log("El proceso no respondió; enviando señal SIGKILL")
            try:
                process.kill()
            except ProcessLookupError:
                pass
            else:
                process.wait()


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _project_root() -> Path:
    """Return the project root path used for resolving helper resources."""

    return Path(__file__).resolve().parents[3]


def resolve_default_updater_command() -> str:
    """Determine the default updater command path.

    When running from a checked-out source tree, prefer the updater script
    located under ``scripts/updater.sh``. When the project is packaged into the
    production image the script is shipped at ``/app/updater.sh``; fall back to
    that location when the local script is missing.
    """

    scripts_path = _project_root() / "scripts" / "updater.sh"
    if scripts_path.exists():
        return str(scripts_path)
    packaged = get_resource_path("scripts/updater.sh")
    if packaged.exists():
        return str(packaged)
    return DEFAULT_COMMAND


def build_watcher(
    schedule_path: Path = DEFAULT_SCHEDULE_FILE,
    *,
    cron_path: Path = DEFAULT_CRON_FILE,
    updater_command: str | None = None,
    interval: float = DEFAULT_INTERVAL,
) -> SchedulerWatcher:
    """Create a scheduler watcher using the default runtime configuration.

    The helper intentionally avoids environment variables so callers have to
    provide any overrides explicitly. When the optional arguments are omitted it
    will rely on the constants exposed by this module, mirroring the behaviour
    of the previous helper but with deterministic inputs.
    """

    command = updater_command or resolve_default_updater_command()
    return SchedulerWatcher(schedule_path, cron_path, command, interval)


def main() -> None:
    watcher = build_watcher()
    watcher.run()


if __name__ == "__main__":
    main()
