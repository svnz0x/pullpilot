"""Helper that waits until the desired datetime and runs the updater once."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import List


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a command once at the desired datetime")
    parser.add_argument("--at", dest="when", required=True, help="ISO 8601 datetime (UTC or with offset)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    return parser.parse_args(argv)


def parse_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if not args.command:
        print("No command provided to run once", file=sys.stderr)
        return 2

    target = parse_datetime(args.when)
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

    try:
        result = subprocess.run(args.command, check=True)
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return result.returncode if isinstance(result.returncode, int) else 0


if __name__ == "__main__":
    sys.exit(main())
