"""Helpers for exposing updater logs through the UI."""
from __future__ import annotations

import bz2
import gzip
import logging
import lzma
import re
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from ..config import ConfigStore

LOGGER = logging.getLogger("pullpilot.ui.logs")

MAX_UI_LOG_LINES = 400

_COMPRESSED_OPENERS = {
    ".gz": gzip.open,
    ".gzip": gzip.open,
    ".bz2": bz2.open,
    ".bzip2": bz2.open,
    ".xz": lzma.open,
    ".lzma": lzma.open,
}

_LOG_COMPRESSION_SUFFIX_PATTERN = "|".join(
    re.escape(suffix.lstrip(".")) for suffix in sorted(_COMPRESSED_OPENERS)
)

_LOG_FILE_PATTERN = re.compile(
    rf"\.log(?:[-_.]?\d+)*(?:\.(?:{_LOG_COMPRESSION_SUFFIX_PATTERN}))?\Z",
    re.IGNORECASE,
)


class LogReadError(RuntimeError):
    """Raised when a log file cannot be read."""


def gather_logs(store: ConfigStore, selected_name: Optional[str] = None) -> Dict[str, object]:
    """Return UI payload with the log directory contents."""

    data = store.load()
    log_dir_raw = data.values.get("LOG_DIR", "")
    log_dir_str = str(log_dir_raw).strip() if log_dir_raw is not None else ""
    if not log_dir_str:
        return {
            "log_dir": "",
            "files": [],
            "selected": None,
            "notice": "LOG_DIR no está configurado. Define un directorio absoluto para poder consultar los logs.",
        }

    try:
        log_dir_path = Path(log_dir_str).expanduser()
    except Exception:
        log_dir_path = Path(log_dir_str)

    if not log_dir_path.exists() or not log_dir_path.is_dir():
        return {
            "log_dir": log_dir_str,
            "files": [],
            "selected": None,
            "notice": f"El directorio de logs '{log_dir_str}' no existe o no es accesible.",
        }

    selected_payload = None
    notice_message = None
    files_payload: List[Dict[str, object]] = []

    entries = []
    for entry in log_dir_path.iterdir():
        if not entry.is_file() or not _LOG_FILE_PATTERN.search(entry.name):
            continue
        try:
            file_stat = entry.stat()
        except OSError as exc:
            LOGGER.warning("Failed to stat log '%s': %s", entry, exc, exc_info=True)
            continue
        entries.append((entry, file_stat))

    entries.sort(key=lambda item: item[1].st_mtime, reverse=True)

    if not entries:
        notice_message = "No se encontraron archivos de log en el directorio configurado."

    for entry, file_stat in entries:
        file_payload: Dict[str, object] = {
            "name": entry.name,
            "size": file_stat.st_size,
            "modified": file_stat.st_mtime,
        }
        files_payload.append(file_payload)

        should_select = False
        if selected_name:
            should_select = selected_payload is None and entry.name == selected_name
        else:
            should_select = selected_payload is None

        if not should_select:
            continue

        selected_payload = dict(file_payload)
        try:
            content = read_log_tail(entry)
        except LogReadError as exc:
            LOGGER.warning("Failed to read log '%s': %s", entry, exc, exc_info=True)
            notice_message = f"No se pudo leer el archivo de log '{entry.name}': {exc}"
            selected_payload["content"] = ""
            selected_payload["notice"] = notice_message
        else:
            selected_payload["content"] = content

    result: Dict[str, object] = {
        "log_dir": str(log_dir_path),
        "files": files_payload,
        "selected": selected_payload,
    }

    if notice_message:
        result["notice"] = notice_message

    return result


def read_log_tail(path: Path, max_lines: int = MAX_UI_LOG_LINES) -> str:
    """Return the last ``max_lines`` lines from ``path`` handling compression."""

    opener = None
    for suffix in reversed(path.suffixes):
        opener = _COMPRESSED_OPENERS.get(suffix.lower())
        if opener is not None:
            break

    try:
        if opener is not None:
            with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max_lines)
        else:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max_lines)
    except (OSError, EOFError, gzip.BadGzipFile, lzma.LZMAError) as exc:
        raise LogReadError(str(exc)) from exc

    return "".join(lines)


__all__ = ["LogReadError", "MAX_UI_LOG_LINES", "gather_logs", "read_log_tail"]
