"""Watch the shared schedule file and (re)start the runner when it changes."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from typing import TYPE_CHECKING

from scheduler import load_schedule_module

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from pullpilot.schedule import ScheduleStore as _ScheduleStore
    from pullpilot.schedule import ScheduleValidationError as _ScheduleValidationError

_schedule_module = load_schedule_module()
DEFAULT_SCHEDULE_PATH = _schedule_module.DEFAULT_SCHEDULE_PATH
ScheduleStore = _schedule_module.ScheduleStore
ScheduleValidationError = _schedule_module.ScheduleValidationError

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
    def run(self) -> None:
        try:
            while True:
                try:
                    schedule = self.store.load().to_dict()
                    signature = json.dumps(schedule, sort_keys=True)
                except (ScheduleValidationError, json.JSONDecodeError) as exc:
                    _log(f"No se pudo interpretar la programación: {exc}")
                    schedule = None
                    signature = None

                if self.process and self.process.poll() is not None:
                    code = self.process.returncode
                    _log(f"El proceso programador finalizó con código {code}; reiniciando")
                    self._stop_process()
                    self.current_signature = None

                if signature != self.current_signature:
                    self._stop_process()
                    if schedule:
                        self._start_process(schedule)
                        self.current_signature = signature
                    else:
                        self.current_signature = None
                time.sleep(self.interval)
        except KeyboardInterrupt:  # pragma: no cover - manual interruption
            _log("Interrumpido, deteniendo programador")
        finally:
            self._stop_process()

    # ------------------------------------------------------------------
    def _start_process(self, schedule: Dict[str, Any]) -> None:
        mode = schedule.get("mode")
        if mode == "cron":
            expression = schedule.get("expression")
            if not isinstance(expression, str):
                _log("Expresión cron inválida; omitiendo")
                return
            self._write_cron_file(expression)
            _log(f"Iniciando supercronic con expresión '{expression}'")
            self.process = subprocess.Popen(["supercronic", "-quiet", str(self.cron_path)])
            return
        if mode == "once":
            datetime_value = schedule.get("datetime")
            if not isinstance(datetime_value, str):
                _log("Fecha/hora inválida; omitiendo")
                return
            try:
                command_args = shlex.split(self.updater_command)
            except ValueError:
                command_args = [self.updater_command]
            _log(f"Planificando ejecución única para {datetime_value}")
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "scheduler.run_once",
                    "--at",
                    datetime_value,
                    "--",
                    *command_args,
                ]
            )
            return
        _log(f"Modo desconocido '{mode}'; no se inicia ningún proceso")

    def _write_cron_file(self, expression: str) -> None:
        self.cron_path.write_text(f"{expression} {self.updater_command}\n", encoding="utf-8")

    def _stop_process(self) -> None:
        if not self.process:
            return
        _log("Deteniendo proceso programador actual")
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _log("El proceso no respondió; enviando señal SIGKILL")
            self.process.kill()
        finally:
            self.process = None


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _project_root() -> Path:
    """Return the project root path used for resolving helper resources."""

    return Path(__file__).resolve().parents[1]


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
    return DEFAULT_COMMAND


def main() -> None:
    schedule_file_env = os.environ.get("PULLPILOT_SCHEDULE_FILE")
    schedule_file = (
        Path(schedule_file_env) if schedule_file_env else DEFAULT_SCHEDULE_FILE
    )
    cron_file = Path(os.environ.get("PULLPILOT_CRON_FILE", DEFAULT_CRON_FILE))
    default_updater_command = resolve_default_updater_command()
    updater_command = os.environ.get(
        "PULLPILOT_UPDATER_COMMAND", default_updater_command
    )
    interval = float(os.environ.get("PULLPILOT_SCHEDULE_POLL_INTERVAL", DEFAULT_INTERVAL))

    watcher = SchedulerWatcher(schedule_file, cron_file, updater_command, interval)
    watcher.run()


if __name__ == "__main__":
    main()
