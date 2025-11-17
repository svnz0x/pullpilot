"""Watch the shared schedule file and (re)start the runner when it changes."""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from threading import Event
from pathlib import Path
from typing import Any, Dict, Optional

from ..resources import get_resource_path
from ..schedule import (
    DEFAULT_CRON_EXPRESSION,
    DEFAULT_SCHEDULE_PATH,
    SchedulePersistenceError,
    ScheduleStore,
    ScheduleValidationError,
)

DEFAULT_SCHEDULE_FILE = DEFAULT_SCHEDULE_PATH
DEFAULT_CRON_FILE = Path("/tmp/pullpilot.cron")
DEFAULT_COMMAND = "/app/updater.sh"
CANONICAL_UPDATER = Path(__file__).resolve().parents[1] / "resources" / "scripts" / "updater.sh"
DEFAULT_INTERVAL = 5.0


logger = logging.getLogger("pullpilot.scheduler.watch")


def _derive_cron_path(schedule_path: Path) -> Path:
    """Return the cron file path derived from the schedule file location."""

    return schedule_path.with_name(f"{schedule_path.name}.cron")


class SchedulerWatcher:
    """Monitor the schedule file and spawn the right worker process."""

    def __init__(
        self,
        schedule_path: Path,
        cron_path: Path | None,
        updater_command: str,
        interval: float,
    ) -> None:
        self.store = ScheduleStore(schedule_path)
        self.cron_path = cron_path if cron_path is not None else _derive_cron_path(schedule_path)
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
                    logger.warning("No se pudo interpretar la programación: %s", exc)
                    schedule = None
                    signature = self.current_signature
                    load_failed = True

                if self.process and self.process.poll() is not None:
                    code = self.process.returncode
                    mode = schedule.get("mode") if isinstance(schedule, dict) else None
                    if mode == "once" and code == 0:
                        logger.info(
                            "El proceso programador finalizó con código 0; ejecución única completada"
                        )
                        try:
                            self.process.wait()
                        finally:
                            self.process = None
                        try:
                            default_schedule = self.store.save(
                                {
                                    "mode": "cron",
                                    "expression": DEFAULT_CRON_EXPRESSION,
                                }
                            )
                        except SchedulePersistenceError as exc:
                            logger.warning(
                                "No se pudo restablecer la programación predeterminada tras la ejecución única: %s",
                                exc,
                            )
                        else:
                            schedule = default_schedule.to_dict()
                            signature = json.dumps(schedule, sort_keys=True)
                    else:
                        logger.warning(
                            "El proceso programador finalizó con código %s; reiniciando", code
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
            logger.info("Interrumpido, deteniendo programador")
        finally:
            self._stop_process()

    # ------------------------------------------------------------------
    def _start_process(self, schedule: Dict[str, Any]) -> bool:
        mode = schedule.get("mode")
        if mode == "cron":
            expression = schedule.get("expression")
            if not isinstance(expression, str):
                logger.warning("Expresión cron inválida; omitiendo")
                return True
            try:
                self._write_cron_file(expression)
            except OSError as exc:
                logger.error("No se pudo preparar el archivo cron: %s", exc)
                return False
            logger.info("Iniciando supercronic con expresión '%s'", expression)
            try:
                self.process = subprocess.Popen(["supercronic", "-quiet", str(self.cron_path)])
            except (FileNotFoundError, OSError) as exc:
                logger.error("No se pudo iniciar supercronic: %s", exc)
                self.process = None
                return False
            return True
        if mode == "once":
            datetime_value = schedule.get("datetime")
            if not isinstance(datetime_value, str):
                logger.warning("Fecha/hora inválida; omitiendo")
                return True
            try:
                command_args = shlex.split(self.updater_command)
            except ValueError:
                command_args = [self.updater_command]
            logger.info("Planificando ejecución única para %s", datetime_value)
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
                logger.error("No se pudo iniciar la ejecución única: %s", exc)
                self.process = None
                return False
            return True
        logger.warning("Modo desconocido '%s'; no se inicia ningún proceso", mode)
        return True

    _ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

    def _write_cron_file(self, expression: str) -> None:
        self.cron_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            command_args = shlex.split(self.updater_command)
        except ValueError:
            command_args = [self.updater_command]
        escaped_command_parts = []
        for arg in command_args:
            if self._ASSIGNMENT_PATTERN.match(arg):
                name, value = arg.split("=", 1)
                quoted_value = shlex.quote(value)
                if quoted_value != value:
                    escaped_command_parts.append(f"{name}={quoted_value}")
                else:
                    escaped_command_parts.append(arg)
            else:
                escaped_command_parts.append(shlex.quote(arg))
        escaped_command = " ".join(escaped_command_parts)
        fd, temp_path = tempfile.mkstemp(
            dir=self.cron_path.parent,
            prefix=f".{self.cron_path.name}",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{expression} {escaped_command}\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temp_path, self.cron_path)
            except OSError as exc:
                logger.error("No se pudo reemplazar el archivo cron temporal: %s", exc)
                raise
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

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

        logger.info("Deteniendo proceso programador actual")
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
            logger.warning("El proceso no respondió; enviando señal SIGKILL")
            try:
                process.kill()
            except ProcessLookupError:
                pass
            else:
                process.wait()
def _project_root() -> Path:
    """Return the project root path used for resolving helper resources."""

    # ``watch.py`` lives under ``apps/backend/pullpilot/scheduler`` so the
    # repository root sits one level above ``apps``.
    return Path(__file__).resolve().parents[4]


def resolve_default_updater_command() -> str:
    """Determine the default updater command path.

    The scheduler prioritises the canonical helper bundled inside
    ``pullpilot/resources/scripts/updater.sh``. When unavailable we look for the
    historical wrappers in ``apps/backend/scripts`` followed by
    ``apps/backend/tools`` before falling back to the packaged default inside
    the container image or the resource bundle exposed via
    :func:`pullpilot.resources.get_resource_path`.
    """

    if CANONICAL_UPDATER.exists():
        return str(CANONICAL_UPDATER)

    project_root = _project_root()
    wrapper_paths = [
        project_root / "apps" / "backend" / "scripts" / "updater.sh",
        project_root / "apps" / "backend" / "tools" / "updater.sh",
    ]
    for wrapper in wrapper_paths:
        if wrapper.exists():
            return str(wrapper)

    packaged_wrapper = Path(DEFAULT_COMMAND)
    if packaged_wrapper.exists():
        return str(packaged_wrapper)

    try:
        bundled_wrapper = get_resource_path("scripts/updater.sh")
    except FileNotFoundError:
        bundled_wrapper = None
    else:
        if bundled_wrapper.exists():
            return str(bundled_wrapper)

    return DEFAULT_COMMAND


def build_watcher(
    schedule_path: Path = DEFAULT_SCHEDULE_FILE,
    *,
    cron_path: Path | None = None,
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
