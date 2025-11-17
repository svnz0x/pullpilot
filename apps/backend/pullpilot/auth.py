"""Authentication helpers for Pullpilot services."""
from __future__ import annotations

import hmac
import logging
import os
import stat
from pathlib import Path
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger("pullpilot.auth")

TOKEN_ENV = "PULLPILOT_TOKEN"
TOKEN_FILE_ENV = "PULLPILOT_TOKEN_FILE"


def _normalize_env_value(value: Optional[str]) -> Optional[str]:
    """Normalize environment variables used for authentication."""

    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        normalized = normalized[1:-1].strip()
    if not normalized:
        return None
    return normalized


def _strip_inline_comments(value: str) -> str:
    """Remove inline comments from ``.env`` style assignments."""

    result = []
    quote_char: Optional[str] = None
    escape = False
    for char in value:
        if escape:
            result.append(char)
            escape = False
            continue
        if char == "\\":
            result.append(char)
            escape = True
            continue
        if quote_char:
            if char == quote_char:
                quote_char = None
            result.append(char)
            continue
        if char in {'"', "'"}:
            quote_char = char
            result.append(char)
            continue
        if char == "#" and (not result or result[-1].isspace()):
            break
        result.append(char)
    return "".join(result)


def _iter_candidate_env_paths() -> Iterable[Path]:
    """Yield possible ``.env`` locations for token discovery."""

    candidates = []
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parent
    repo_root = project_root.parent
    workspace_root = repo_root.parent
    for root in (Path.cwd(), package_root, project_root, repo_root, workspace_root):
        try:
            resolved = root.resolve()
        except OSError:
            resolved = root
        if resolved in candidates:
            continue
        candidates.append(resolved)
        yield resolved / ".env"


def _load_token_from_env_files() -> Optional[str]:
    """Populate ``os.environ`` with the token from ``.env`` files when needed."""

    existing = os.environ.get(TOKEN_ENV)
    normalized_existing = _normalize_env_value(existing)
    if normalized_existing is not None:
        if existing != normalized_existing:
            os.environ[TOKEN_ENV] = normalized_existing
        return normalized_existing
    if existing is not None:
        os.environ.pop(TOKEN_ENV, None)

    for path in _iter_candidate_env_paths():
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export"):
                remainder = stripped[len("export"):]
                if not remainder or remainder[0].isspace():
                    stripped = remainder.lstrip()
            if "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() != TOKEN_ENV:
                continue
            normalized = _normalize_env_value(_strip_inline_comments(raw_value))
            if normalized is None:
                continue
            os.environ[TOKEN_ENV] = normalized
            return normalized
    return None


def _load_token_from_file_env() -> Optional[str]:
    """Populate ``os.environ`` with the token defined via ``PULLPILOT_TOKEN_FILE``."""

    raw_path = os.environ.get(TOKEN_FILE_ENV)
    normalized_path = _normalize_env_value(raw_path)
    if not normalized_path:
        return None

    token_path = Path(normalized_path).expanduser()
    try:
        file_stat = token_path.lstat()
    except FileNotFoundError:
        LOGGER.warning(
            "Token file '%s' not found; falling back to environment variables and .env files.",
            token_path,
        )
        return None
    except OSError as exc:
        LOGGER.warning(
            "Failed to access token file '%s': %s; falling back to other configuration sources.",
            token_path,
            exc,
        )
        return None

    if not stat.S_ISREG(file_stat.st_mode):
        LOGGER.warning(
            "Token file '%s' is not a regular file; ignoring it and falling back to other sources.",
            token_path,
        )
        return None

    mode = stat.S_IMODE(file_stat.st_mode)
    insecure_permissions = (
        stat.S_IWGRP | stat.S_IXGRP | stat.S_IWOTH | stat.S_IXOTH
    )
    if mode & insecure_permissions:
        LOGGER.warning(
            "Token file '%s' has insecure permissions; it must not be writable or executable by group/other users.",
            token_path,
        )
        return None

    try:
        content = token_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        LOGGER.warning(
            "Failed to read token file '%s': %s; falling back to other configuration sources.",
            token_path,
            exc,
        )
        return None

    normalized = _normalize_env_value(content)
    if normalized is None:
        LOGGER.warning(
            "Token file '%s' is empty or contains only whitespace; ignoring it.",
            token_path,
        )
        return None

    os.environ[TOKEN_ENV] = normalized
    return normalized


def _load_token_from_configured_sources() -> Optional[str]:
    """Ensure the authentication token is loaded from env vars, files or `.env`."""

    token = _normalize_env_value(os.environ.get(TOKEN_ENV))
    if token is not None:
        if os.environ[TOKEN_ENV] != token:
            os.environ[TOKEN_ENV] = token
        return token

    os.environ.pop(TOKEN_ENV, None)

    token = _load_token_from_file_env()
    if token is not None:
        return token

    token = _load_token_from_env_files()
    if token is not None:
        return token

    return _normalize_env_value(os.environ.get(TOKEN_ENV))


class Authenticator:
    """Simple helper that validates Authorization headers when configured."""

    def __init__(self, *, token: Optional[str] = None) -> None:
        self.token = token

    @classmethod
    def from_env(cls) -> "Authenticator":
        """Create an authenticator from environment variables."""

        token = _load_token_from_configured_sources()
        if token is None:
            raise RuntimeError(
                "Missing authentication token. Configure the PULLPILOT_TOKEN environment variable."
            )
        return cls(token=token)

    @property
    def configured(self) -> bool:
        """Return ``True`` when a token is available for authorization."""

        return self.token is not None

    def authorize(self, headers: Optional[Mapping[str, str]]) -> bool:
        if not headers:
            return False
        auth_header = None
        for key, value in headers.items():
            if key.lower() == "authorization":
                auth_header = value
                break
        if not auth_header:
            return False
        if self.token:
            return _match_token(self.token, auth_header)
        return False


def _match_token(expected: str, header: str) -> bool:
    normalized = header.strip()
    if not normalized:
        return False
    parts = normalized.split(None, 1)
    if len(parts) != 2:
        return False
    scheme, value = parts
    if not value:
        return False
    if scheme.lower() in {"bearer", "token"}:
        return hmac.compare_digest(value, expected)
    return False


__all__ = [
    "Authenticator",
    "TOKEN_ENV",
    "TOKEN_FILE_ENV",
    "_load_token_from_env_files",
    "_load_token_from_file_env",
]
