from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "updater.sh"


@pytest.fixture()
def fake_docker(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail

            if [[ "$#" -eq 0 ]]; then
              exit 0
            fi

            subcommand="$1"
            shift

            if [[ "$subcommand" == compose ]]; then
              if [[ "$#" -gt 0 && "$1" == -f ]]; then
                shift 2
              fi
              if [[ "$#" -gt 0 && "$1" == version ]]; then
                shift
                if [[ "$#" -gt 0 && "$1" == --short ]]; then
                  echo "v2.20.0"
                else
                  echo "Docker Compose version v2.20.0"
                fi
                exit 0
              fi
              if [[ "$#" -gt 0 && "$1" == config ]]; then
                shift
                if [[ "$#" -gt 0 && "$1" == --services ]]; then
                  echo "web"
                fi
                exit 0
              fi
              if [[ "$#" -gt 0 && "$1" == ps ]]; then
                # Consume flags like -q and optional service name
                while [[ "$#" -gt 0 ]]; do
                  case "$1" in
                    -f)
                      shift 2
                      ;;
                    -q)
                      shift
                      ;;
                    *)
                      break
                      ;;
                  esac
                done
                echo "container123"
                exit 0
              fi
              if [[ "$#" -gt 0 && "$1" == up && "$2" == --help ]]; then
                cat <<'HELP'
Usage: docker compose up
  --wait
  --quiet-pull
HELP
                exit 0
              fi
              exit 0
            fi

            if [[ "$subcommand" == inspect ]]; then
              if [[ "$1" == --format ]]; then
                format="$2"
                if [[ "$format" == *Image* ]]; then
                  echo "image:latest"
                elif [[ "$format" == *Health* ]]; then
                  echo "healthy"
                else
                  echo "running"
                fi
                exit 0
              fi
            fi

            exit 0
            """
        ),
        encoding="utf-8",
    )
    docker_path.chmod(docker_path.stat().st_mode | stat.S_IEXEC)
    return docker_path


def run_updater(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def base_environment(tmp_path: Path, docker_path: Path) -> dict[str, str]:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    compose_file = project_dir / "compose.yaml"
    compose_file.write_text("version: '3'\nservices:\n  web:\n    image: alpine\n", encoding="utf-8")

    projects_list = tmp_path / "projects.txt"
    projects_list.write_text(f"{project_dir}\n", encoding="utf-8")

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    lock_file = tmp_path / "lock"
    conf_path = tmp_path / "updater.conf"
    conf_path.write_text(
        textwrap.dedent(
            f"""
            BASE_DIR="{tmp_path}"
            LOG_DIR="{log_dir}"
            LOCK_FILE="{lock_file}"
            LOG_RETENTION_DAYS=7
            EMAIL_TO=""
            EMAIL_FROM="tester@example.com"
            SUBJECT_PREFIX="[docker-updater]"
            SMTP_CMD="msmtp"
            SMTP_ACCOUNT="default"
            SMTP_READ_ENVELOPE=true
            DOCKER_TIMEOUT=120
            QUIET_PULL=true
            PULL_POLICY="always"
            PARALLEL_PULL=0
            EXCLUDE_PATTERNS=""
            COMPOSE_PROJECTS_FILE="{projects_list}"
            ATTACH_LOGS_ON="changes"
            PRUNE_ENABLED=false
            PRUNE_VOLUMES=false
            PRUNE_FILTER_UNTIL=""
            DRY_RUN=true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{docker_path.parent}:{env.get('PATH', '')}",
            "CONF_FILE": str(conf_path),
            "NO_COLOR": "1",
        }
    )
    return env


def test_script_allows_empty_base_directory(tmp_path: Path, fake_docker: Path) -> None:
    base_dir = tmp_path / "compose"
    base_dir.mkdir()

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    lock_file = tmp_path / "lock"
    conf_path = tmp_path / "updater-empty.conf"
    conf_path.write_text(
        textwrap.dedent(
            f"""
            BASE_DIR="{base_dir}"
            LOG_DIR="{log_dir}"
            LOCK_FILE="{lock_file}"
            LOG_RETENTION_DAYS=7
            EMAIL_TO=""
            EMAIL_FROM="tester@example.com"
            SUBJECT_PREFIX="[docker-updater]"
            SMTP_CMD="msmtp"
            SMTP_ACCOUNT="default"
            SMTP_READ_ENVELOPE=true
            DOCKER_TIMEOUT=120
            QUIET_PULL=true
            PULL_POLICY="always"
            PARALLEL_PULL=0
            EXCLUDE_PATTERNS=""
            COMPOSE_PROJECTS_FILE=""
            ATTACH_LOGS_ON="changes"
            PRUNE_ENABLED=false
            PRUNE_VOLUMES=false
            PRUNE_FILTER_UNTIL=""
            DRY_RUN=true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_docker.parent}:{env.get('PATH', '')}",
            "CONF_FILE": str(conf_path),
            "NO_COLOR": "1",
        }
    )

    result = run_updater(env)

    assert result.returncode == 0
    assert "No se encontraron proyectos bajo" in result.stdout


def test_script_accepts_absolute_compose_path(tmp_path: Path, fake_docker: Path) -> None:
    env = base_environment(tmp_path, fake_docker)
    compose_value = f"{fake_docker} compose"
    env["COMPOSE_BIN"] = compose_value

    result = run_updater(env)

    assert result.returncode == 0, result.stdout


def test_script_rejects_injected_compose_value(tmp_path: Path, fake_docker: Path) -> None:
    env = base_environment(tmp_path, fake_docker)
    env["COMPOSE_BIN"] = "docker compose; rm -rf /"

    result = run_updater(env)

    assert result.returncode != 0
    assert "COMPOSE_BIN inválido" in result.stdout


def test_script_requires_executable_path(tmp_path: Path, fake_docker: Path) -> None:
    env = base_environment(tmp_path, fake_docker)
    missing_path = tmp_path / "missing" / "docker"
    env["COMPOSE_BIN"] = f"{missing_path} compose"

    result = run_updater(env)

    assert result.returncode != 0
    assert "no existe o no es ejecutable" in result.stdout


def test_script_fails_when_base_dir_missing(tmp_path: Path, fake_docker: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    conf_path = tmp_path / "updater-missing-base.conf"
    conf_path.write_text(
        textwrap.dedent(
            f"""
            BASE_DIR=""
            LOG_DIR="{log_dir}"
            LOCK_FILE="{tmp_path / "lock"}"
            DRY_RUN=true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_docker.parent}:{env.get('PATH', '')}",
            "CONF_FILE": str(conf_path),
            "NO_COLOR": "1",
        }
    )

    result = run_updater(env)

    assert result.returncode != 0
    assert "BASE_DIR no puede estar vacío" in result.stdout


def test_script_fails_when_log_dir_missing(tmp_path: Path, fake_docker: Path) -> None:
    base_dir = tmp_path / "compose"
    base_dir.mkdir()
    missing_log = tmp_path / "logs"
    conf_path = tmp_path / "updater-missing-log.conf"
    conf_path.write_text(
        textwrap.dedent(
            f"""
            BASE_DIR="{base_dir}"
            LOG_DIR="{missing_log}"
            LOCK_FILE="{tmp_path / "lock"}"
            DRY_RUN=true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_docker.parent}:{env.get('PATH', '')}",
            "CONF_FILE": str(conf_path),
            "NO_COLOR": "1",
        }
    )

    result = run_updater(env)

    assert result.returncode != 0
    assert f"LOG_DIR apunta a un directorio inexistente: {missing_log}" in result.stdout
