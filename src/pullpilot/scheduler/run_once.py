"""Helper that waits until the desired datetime and runs the updater once."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from pullpilot.schedule import normalize_datetime_utc


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a command once at the desired datetime")
    parser.add_argument("--at", dest="when", required=True, help="ISO 8601 datetime (UTC or with offset)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    parsed = parser.parse_args(argv)
    if parsed.command and parsed.command[0] == "--":
        parsed.command = parsed.command[1:]
    return parsed


def parse_datetime(value: str) -> datetime:
    return normalize_datetime_utc(value)


def run_once(argv: List[str] | None = None) -> int:
    """Entrypoint compatible helper for executing the updater once."""

    return main(argv)


def _split_env_and_command(command: List[str]) -> Tuple[Dict[str, str], List[str]]:
    env_overrides: Dict[str, str] = {}
    remaining: List[str] = []

    iterator = iter(command)
    for token in iterator:
        if "=" not in token or token.startswith("="):
            remaining.append(token)
            break
        name, value = token.split("=", 1)
        if not name:
            remaining.append(token)
            break
        env_overrides[name] = value
    else:
        return env_overrides, remaining

    remaining.extend(iterator)
    return env_overrides, remaining


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    env_overrides, command = _split_env_and_command(args.command)
    if not command:
        print("No command provided to run once", file=sys.stderr)
        return 2

    try:
        target = parse_datetime(args.when)
    except ValueError as exc:
        print(f"Invalid datetime value for --at: {exc}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    seconds = (target - now).total_seconds()
    while seconds > 0:
        sleep_time = min(seconds, 60)
        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            return 130
        now = datetime.now(timezone.utc)
        seconds = (target - now).total_seconds()

    merged_env = os.environ.copy()
    merged_env.update(env_overrides)

    try:
        result = subprocess.run(command, check=True, env=merged_env)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return result.returncode if isinstance(result.returncode, int) else 0


if __name__ == "__main__":
    sys.exit(main())
