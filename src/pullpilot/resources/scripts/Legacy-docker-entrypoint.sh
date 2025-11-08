#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${PULLPILOT_CONFIG_DIR:-/app/config}"
DEFAULT_CONFIG_DIR="${PULLPILOT_DEFAULT_CONFIG_DIR:-/app/config.defaults}"

# Ensure the target config directory exists (it may be an empty volume on first run)
mkdir -p "$CONFIG_DIR"

# Copy default configuration files when they do not exist in the mounted volume.
if [ -d "$DEFAULT_CONFIG_DIR" ]; then
  for default_file in "$DEFAULT_CONFIG_DIR"/*; do
    [ -e "$default_file" ] || continue
    filename="$(basename "$default_file")"
    target="$CONFIG_DIR/$filename"
    if [ ! -e "$target" ]; then
      if [ -d "$default_file" ]; then
        cp -r "$default_file" "$target"
      else
        cp "$default_file" "$target"
      fi
    fi
  done
fi

exec "$@"
