"""Application orchestrator that mirrors the legacy Docker entrypoint."""
from __future__ import annotations

import argparse
import logging
import shutil
import signal
import sys
from pathlib import Path
from threading import Event, Thread
from typing import Iterable, Optional

import uvicorn

from .app import create_app
from .config import ConfigStore
from .resources import get_resource_path
from .schedule import ScheduleStore
from .scheduler.watch import build_watcher

LOGGER = logging.getLogger("pullpilot.runner")

DEFAULT_CONFIG_TARGET = Path("/app/config")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta la API y el scheduler de Pullpilot")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="Dirección donde exponer la API (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Puerto donde exponer la API (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        help="Nivel de log para Uvicorn (default: %(default)s)",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Inicia solo la API, deshabilitando el scheduler interno",
    )
    return parser.parse_args(argv)


def _resolve_config_dir() -> Path:
    project_config = Path(__file__).resolve().parents[2] / "config"
    if project_config.exists():
        return project_config
    return DEFAULT_CONFIG_TARGET


def _discover_default_config_dir() -> Optional[Path]:
    project_root = Path(__file__).resolve().parents[2]
    for name in ("config.defaults", "config"):
        candidate = project_root / name
        if candidate.exists():
            return candidate
    try:
        resource_path = get_resource_path("config")
    except FileNotFoundError:
        return None
    return resource_path if resource_path.exists() else None


def _copy_missing_config(config_dir: Path, default_dir: Optional[Path]) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    if not default_dir or not default_dir.exists():
        LOGGER.debug("No default config directory found; skipping bootstrap")
        return
    def _copy_entry(source: Path, destination: Path) -> None:
        if source.is_dir():
            if not destination.exists():
                destination.mkdir(parents=True, exist_ok=True)
                LOGGER.info(
                    "Copiado recurso de configuración por defecto: %s", destination
                )
            try:
                children = list(source.iterdir())
            except OSError as exc:
                LOGGER.warning(
                    "No se pudo listar el directorio de configuración por defecto %s", source,
                    exc_info=exc,
                )
                return
            for child in children:
                _copy_entry(child, destination / child.name)
            return

        if destination.exists():
            return

        try:
            shutil.copy2(source, destination)
        except OSError as exc:
            LOGGER.warning(
                "No se pudo copiar el recurso de configuración por defecto %s", source,
                exc_info=exc,
            )
            return
        LOGGER.info("Copiado recurso de configuración por defecto: %s", destination)

    for entry in default_dir.iterdir():
        _copy_entry(entry, config_dir / entry.name)


def _configure_logging(level: str) -> None:
    # Defer to Uvicorn for structured logging but ensure the root handler exists.
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    _configure_logging(args.log_level)

    config_dir = _resolve_config_dir()
    default_dir = _discover_default_config_dir()
    _copy_missing_config(config_dir, default_dir)

    schedule_path = config_dir / "pullpilot.schedule"
    config_path = config_dir / "updater.conf"
    schema_path = get_resource_path("config/schema.json")

    store = ConfigStore(config_path, schema_path)
    schedule_store = ScheduleStore(schedule_path)
    app = create_app(store=store, schedule_store=schedule_store)

    uvicorn_config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        factory=False,
    )
    server = uvicorn.Server(uvicorn_config)
    server.install_signal_handlers = lambda: None

    scheduler_stop = Event()
    scheduler_thread: Thread | None = None
    should_run_scheduler = not args.no_scheduler

    if should_run_scheduler:
        watcher = build_watcher(schedule_path=schedule_path)

        def _run_scheduler() -> None:
            try:
                watcher.run(scheduler_stop)
            except Exception:  # pragma: no cover - defensive guard
                LOGGER.exception("El scheduler terminó con una excepción no controlada")
                scheduler_stop.set()

        scheduler_thread = Thread(target=_run_scheduler, name="scheduler-watcher", daemon=True)
        scheduler_thread.start()
        LOGGER.info("Scheduler iniciado")
    else:
        LOGGER.info("Scheduler deshabilitado por configuración")

    shutdown_triggered = Event()

    def _initiate_shutdown(signum: int | None = None) -> None:
        if shutdown_triggered.is_set():
            return
        shutdown_triggered.set()
        if signum is not None:
            try:
                signal_name = signal.Signals(signum).name
            except ValueError:
                signal_name = str(signum)
            LOGGER.info("Recibida señal %s, iniciando apagado", signal_name)
        scheduler_stop.set()
        server.should_exit = True

    signal.signal(signal.SIGTERM, lambda signum, frame: _initiate_shutdown(signum))
    signal.signal(signal.SIGINT, lambda signum, frame: _initiate_shutdown(signum))

    try:
        server.run()
    except KeyboardInterrupt:  # pragma: no cover - handled by signals but kept for robustness
        _initiate_shutdown()
    finally:
        _initiate_shutdown()
        if scheduler_thread:
            scheduler_thread.join(timeout=5)
            if scheduler_thread.is_alive():
                LOGGER.warning("El scheduler no se detuvo correctamente antes de agotar el tiempo de espera")
        LOGGER.info("Apagado completo")

    if not server.should_exit and not shutdown_triggered.is_set():
        # Server stopped unexpectedly; propagate non-zero exit for callers.
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - CLI execution path
    main()
