"""Application factory for Pullpilot's backend services."""
from __future__ import annotations

from typing import Optional

try:  # pragma: no cover - optional dependency
    from fastapi import FastAPI
except ImportError:  # pragma: no cover - optional dependency
    FastAPI = None  # type: ignore[misc, assignment]

from .api import ConfigAPI
from .config import ConfigStore
from .schedule import ScheduleStore
from .ui.application import configure_application


def create_app(
    store: Optional[ConfigStore] = None,
    schedule_store: Optional[ScheduleStore] = None,
):
    """Return a FastAPI/Flask compatible object when possible."""

    api = ConfigAPI(store=store, schedule_store=schedule_store)
    if FastAPI is None:  # pragma: no cover - exercised when FastAPI is unavailable
        return api

    app = FastAPI()
    configure_application(app, api)
    return app
