#!/usr/bin/env python3
"""Wrapper conservado por compatibilidad. Usa `pullpilot-sync-defaults` en su lugar."""
from __future__ import annotations

from pullpilot.cli.sync_defaults import main

if __name__ == "__main__":  # pragma: no cover - script wrapper
    raise SystemExit(main())
