"""Utilities for reading and writing the updater configuration file.

The configuration file follows a simple ``KEY=value`` format with optional
comments. This module loads the schema definition, merges values with the
defaults and allows rewriting the configuration while preserving comments and
quoting where possible.  Additionally it manages auxiliary files that store
multi line data such as ``COMPOSE_PROJECTS_FILE``.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = [
    "ConfigData",
    "ConfigError",
    "ConfigStore",
    "ValidationError",
]


class ConfigError(RuntimeError):
    """Base class for configuration related issues."""


class ValidationError(ConfigError):
    """Raised when user provided data does not match the schema."""

    def __init__(self, errors: List[Dict[str, Any]]):
        super().__init__("validation failed")
        self.errors = errors


@dataclass
class SchemaVariable:
    name: str
    type: str
    default: Any
    constraints: Dict[str, Any]
    description: str


@dataclass
class ConfigData:
    values: "OrderedDict[str, Any]"
    multiline: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {"values": dict(self.values), "multiline": dict(self.multiline)}


@dataclass
class CommentLine:
    text: str


@dataclass
class AssignmentLine:
    prefix: str
    key: str
    key_suffix: str
    post_equal_ws: str
    inline_comment: str
    quote: Optional[str]
    value: Any


ParsedLine = Tuple[Any, int]

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}
_MULTILINE_FIELDS = {"COMPOSE_PROJECTS_FILE"}
_SAFE_COMPOSE_TOKEN = re.compile(r"^[A-Za-z0-9._/-]+$")
_ALLOWED_COMPOSE_SHORTCUTS = {("docker", "compose"), ("docker-compose",)}


class ConfigStore:
    """High level helper that loads and stores configuration values."""

    def __init__(
        self,
        config_path: Path,
        schema_path: Path,
        *,
        allowed_multiline_dirs: Optional[Iterable[Path]] = None,
    ):
        self.config_path = Path(config_path).expanduser()
        self.schema_path = Path(schema_path).expanduser()
        self.schema: List[SchemaVariable] = self._load_schema(self.schema_path)
        self.schema_map: Dict[str, SchemaVariable] = {
            variable.name: variable for variable in self.schema
        }
        self.schema_order: List[str] = [variable.name for variable in self.schema]
        base_dirs = (
            list(allowed_multiline_dirs)
            if allowed_multiline_dirs is not None
            else [self.config_path.parent or Path(".")]
        )
        self.allowed_multiline_dirs: List[Path] = [
            Path(directory).expanduser().resolve()
            for directory in base_dirs
        ]

    # ------------------------------------------------------------------
    # Public helpers
    def load(self) -> ConfigData:
        """Return the current configuration merged with defaults."""

        defaults = OrderedDict(
            (variable.name, self._coerce_default(variable)) for variable in self.schema
        )
        document = self._read_document()
        for line in document:
            if isinstance(line, AssignmentLine) and line.key in defaults:
                defaults[line.key] = line.value
        multiline = self._load_multiline_content(defaults)
        return ConfigData(defaults, multiline)

    def save(
        self,
        values: Mapping[str, Any],
        multiline: Optional[Mapping[str, str]] = None,
    ) -> ConfigData:
        """Persist ``values`` and optional ``multiline`` payload."""

        sanitized = self._validate(values)
        multiline_payload = multiline or {}
        self._persist_multiline_files(sanitized, multiline_payload)

        document = self._read_document()
        self._update_document(document, sanitized)
        self._write_document(document)
        return self.load()

    # ------------------------------------------------------------------
    # Metadata helpers
    @property
    def multiline_fields(self) -> List[str]:
        """Return the list of variables that accept multiline payloads."""

        return sorted(_MULTILINE_FIELDS)

    def schema_overview(self) -> Dict[str, Any]:
        """Expose schema metadata useful for client applications."""

        return {
            "variables": [
                {
                    "name": variable.name,
                    "type": variable.type,
                    "default": variable.default,
                    "constraints": dict(variable.constraints),
                    "description": variable.description,
                    "multiline": variable.name in _MULTILINE_FIELDS,
                }
                for variable in self.schema
            ]
        }

    # ------------------------------------------------------------------
    # Schema helpers
    def _load_schema(self, path: Path) -> List[SchemaVariable]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        variables = raw.get("variables")
        if not isinstance(variables, list):
            raise ConfigError("invalid schema: missing 'variables'")
        parsed = []
        for entry in variables:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            var_type = entry.get("type")
            default = entry.get("default")
            constraints = entry.get("constraints", {})
            if not isinstance(name, str) or not isinstance(var_type, str):
                continue
            parsed.append(
                SchemaVariable(
                    name=name,
                    type=var_type,
                    default=default,
                    constraints=dict(constraints),
                    description=str(entry.get("description", "")),
                )
            )
        return parsed

    def _coerce_default(self, variable: SchemaVariable) -> Any:
        if variable.type == "integer":
            return int(variable.default)
        if variable.type == "boolean":
            return bool(variable.default)
        return str(variable.default) if variable.default is not None else ""

    # ------------------------------------------------------------------
    # Validation helpers
    def _validate(self, values: Mapping[str, Any]) -> "OrderedDict[str, Any]":
        errors: List[Dict[str, Any]] = []
        sanitized: "OrderedDict[str, Any]" = OrderedDict()

        for name in self.schema_order:
            if name not in values:
                errors.append({"field": name, "message": "missing value"})
                continue
            variable = self.schema_map[name]
            try:
                coerced = self._coerce_input(variable, values[name])
            except ValueError as exc:  # pragma: no cover - defensive
                errors.append({"field": name, "message": str(exc)})
                continue
            violation = self._check_constraints(variable, coerced)
            if violation is not None:
                errors.append({"field": name, "message": violation})
                continue
            sanitized[name] = coerced

        for name in values:
            if name not in self.schema_map:
                errors.append({"field": name, "message": "unknown variable"})

        if errors:
            raise ValidationError(errors)
        return sanitized

    def _coerce_input(self, variable: SchemaVariable, value: Any) -> Any:
        if variable.type == "integer":
            if isinstance(value, bool):
                raise ValueError("integer expected")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.strip():
                return int(value)
            raise ValueError("integer expected")
        if variable.type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in _BOOL_TRUE:
                    return True
                if normalized in _BOOL_FALSE:
                    return False
            raise ValueError("boolean expected")
        # string fallback
        if variable.name == "COMPOSE_BIN":
            return self._normalize_compose_bin(value)
        if value is None:
            return ""
        return str(value)

    def _check_constraints(self, variable: SchemaVariable, value: Any) -> Optional[str]:
        constraints = variable.constraints
        if variable.type == "string":
            string_value = str(value)
            if not constraints.get("allow_empty", False) and string_value == "":
                return "value cannot be empty"
            pattern = constraints.get("pattern")
            if pattern and not re.fullmatch(pattern, string_value):
                return f"value must match pattern {pattern!r}"
            min_length = constraints.get("min_length")
            if min_length is not None and len(string_value) < int(min_length):
                return f"minimum length is {min_length}"
            max_length = constraints.get("max_length")
            if max_length is not None and len(string_value) > int(max_length):
                return f"maximum length is {max_length}"
            if constraints.get("disallow_path_traversal") and string_value:
                if ".." in Path(string_value).parts:
                    return "path cannot contain '..' segments"
            allowed_values = constraints.get("allowed_values")
            if allowed_values and string_value not in allowed_values:
                return "value must be one of: " + ", ".join(map(str, allowed_values))
        elif variable.type == "integer":
            integer_value = int(value)
            minimum = constraints.get("min")
            if minimum is not None and integer_value < int(minimum):
                return f"minimum value is {minimum}"
            maximum = constraints.get("max")
            if maximum is not None and integer_value > int(maximum):
                return f"maximum value is {maximum}"
        elif variable.type == "boolean":
            allowed_values = constraints.get("allowed_values")
            if allowed_values is not None:
                normalized = "true" if value else "false"
                if normalized not in allowed_values:
                    return "value must be one of: " + ", ".join(map(str, allowed_values))
        return None

    def _normalize_compose_bin(self, value: Any) -> str:
        """Normalize the compose command to a vetted, space separated string."""

        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        try:
            tokens = shlex.split(text)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"invalid compose command: {exc}")
        if not tokens:
            return ""
        if any(not _SAFE_COMPOSE_TOKEN.fullmatch(token) for token in tokens):
            raise ValueError("compose command contains invalid characters")
        if tuple(tokens) in _ALLOWED_COMPOSE_SHORTCUTS:
            return " ".join(tokens)
        if len(tokens) == 1 and tokens[0].startswith("/"):
            binary = tokens[0]
            if binary.endswith("docker-compose"):
                return binary
        if (
            len(tokens) == 2
            and tokens[0].startswith("/")
            and tokens[0].endswith("docker")
            and tokens[1] == "compose"
        ):
            return " ".join(tokens)
        raise ValueError("unsupported compose command")

    # ------------------------------------------------------------------
    # Document helpers
    def _read_document(self) -> List[Any]:
        if not self.config_path.exists():
            return []
        text = self.config_path.read_text(encoding="utf-8")
        lines = text.split("\n")
        parsed: List[Any] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if index == len(lines) - 1 and line == "":
                break
            parsed_line, consumed = self._parse_line(lines, index)
            parsed.append(parsed_line)
            index += consumed
        return parsed

    def _parse_line(self, lines: List[str], index: int) -> ParsedLine:
        line = lines[index]
        if not line.strip():
            return CommentLine(text=line), 1
        stripped_leading = line.lstrip(" \t")
        leading = line[: len(line) - len(stripped_leading)]
        if stripped_leading.startswith("#") or "=" not in stripped_leading:
            return CommentLine(text=line), 1

        before_equal, after_equal = stripped_leading.split("=", 1)
        key = before_equal.strip()
        if not key:
            return CommentLine(text=line), 1
        key_suffix = before_equal[len(key) :]
        post_equal_ws = after_equal[: len(after_equal) - len(after_equal.lstrip(" \t"))]
        value_chunk = after_equal[len(post_equal_ws) :]

        value_text, inline_comment, consumed = self._consume_value(lines, index, value_chunk)
        quote = self._detect_quote(value_text)
        parsed_value = self._decode_value(key, value_text, quote)
        assignment = AssignmentLine(
            prefix=leading,
            key=key,
            key_suffix=key_suffix,
            post_equal_ws=post_equal_ws,
            inline_comment=inline_comment,
            quote=quote,
            value=parsed_value,
        )
        return assignment, consumed

    def _consume_value(self, lines: List[str], index: int, initial: str) -> Tuple[str, str, int]:
        value_chars: List[str] = []
        inline_comment = ""
        consumed = 1
        in_quote: Optional[str] = None
        escaped = False
        current = initial
        line_index = index
        while True:
            for pos, ch in enumerate(current):
                if escaped:
                    value_chars.append(ch)
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    value_chars.append(ch)
                    continue
                if ch in {'"', "'"}:
                    if in_quote is None:
                        in_quote = ch
                    elif in_quote == ch:
                        in_quote = None
                    value_chars.append(ch)
                    continue
                if ch == "#" and in_quote is None:
                    trailing_ws = ""
                    while value_chars and value_chars[-1] in (" ", "\t"):
                        trailing_ws = value_chars.pop() + trailing_ws
                    inline_comment = trailing_ws + current[pos:]
                    current = ""
                    break
                value_chars.append(ch)
            else:
                current = ""
            if current:
                continue
            if in_quote is None:
                break
            line_index += 1
            if line_index >= len(lines):
                break
            consumed += 1
            current = lines[line_index]
            value_chars.append("\n")
        value_text = "".join(value_chars).rstrip(" \t")
        return value_text, inline_comment, consumed

    def _detect_quote(self, value_text: str) -> Optional[str]:
        if len(value_text) >= 2 and value_text[0] == value_text[-1] and value_text[0] in {'"', "'"}:
            return value_text[0]
        return None

    def _decode_value(self, key: str, value_text: str, quote: Optional[str]) -> Any:
        variable = self.schema_map.get(key)
        raw_value = value_text
        if quote is not None:
            raw_value = raw_value[1:-1]
        if variable is None:
            return raw_value
        if variable.type == "integer":
            return int(raw_value)
        if variable.type == "boolean":
            normalized = raw_value.strip().lower()
            if normalized in _BOOL_TRUE:
                return True
            if normalized in _BOOL_FALSE:
                return False
            raise ConfigError(f"invalid boolean value for {key}")
        return raw_value

    def _update_document(self, document: List[Any], values: Mapping[str, Any]) -> None:
        seen: set[str] = set()
        for line in document:
            if isinstance(line, AssignmentLine) and line.key in values:
                line.value = values[line.key]
                seen.add(line.key)
        for key in self.schema_order:
            if key in values and key not in seen:
                variable = self.schema_map[key]
                quote = '"' if variable.type == "string" else None
                document.append(
                    AssignmentLine(
                        prefix="",
                        key=key,
                        key_suffix="",
                        post_equal_ws="",
                        inline_comment="",
                        quote=quote,
                        value=values[key],
                    )
                )

    def _write_document(self, document: Iterable[Any]) -> None:
        lines: List[str] = []
        for line in document:
            if isinstance(line, CommentLine):
                lines.append(line.text)
            elif isinstance(line, AssignmentLine):
                formatted = self._format_value(line)
                rendered = (
                    f"{line.prefix}{line.key}{line.key_suffix}="
                    f"{line.post_equal_ws}{formatted}{line.inline_comment}"
                )
                lines.append(rendered.rstrip())
        text = "\n".join(lines)
        if text and not text.endswith("\n"):
            text += "\n"
        directory = self.config_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=directory,
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.config_path)
        except Exception:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise

    def _format_value(self, line: AssignmentLine) -> str:
        variable = self.schema_map.get(line.key)
        value = line.value
        if variable is None:
            return str(value)
        if variable.type == "integer":
            return str(int(value))
        if variable.type == "boolean":
            return "true" if bool(value) else "false"
        assert variable.type == "string"
        string_value = str(value)
        quote = self._choose_quote(line.quote, string_value)
        if quote is None:
            return string_value
        escaped = string_value.replace("\\", "\\\\")
        escaped = escaped.replace(quote, f"\\{quote}")
        return f"{quote}{escaped}{quote}"

    def _choose_quote(self, current: Optional[str], value: str) -> Optional[str]:
        if current in {'"', "'"}:
            return current
        if value == "" or any(c.isspace() for c in value) or "#" in value or "\n" in value:
            return '"'
        return None

    # ------------------------------------------------------------------
    # Multiline helpers
    def _load_multiline_content(self, values: Mapping[str, Any]) -> Dict[str, str]:
        multiline: Dict[str, str] = {}
        for key in _MULTILINE_FIELDS:
            path_value = values.get(key)
            if not path_value:
                multiline[key] = ""
                continue
            file_path = Path(str(path_value)).expanduser()
            try:
                resolved = file_path.resolve()
            except FileNotFoundError:
                resolved = file_path.resolve(strict=False)
            if not self._is_path_allowed(resolved):
                multiline[key] = ""
                continue
            try:
                multiline[key] = resolved.read_text(encoding="utf-8")
            except FileNotFoundError:
                multiline[key] = ""
        return multiline

    def _persist_multiline_files(
        self, values: Mapping[str, Any], multiline: Mapping[str, str]
    ) -> None:
        pending_writes: List[Tuple[Path, str]] = []
        errors: List[Dict[str, Any]] = []
        for key in _MULTILINE_FIELDS:
            if key not in multiline:
                continue
            path_value = values.get(key, "")
            content = multiline[key]
            if not path_value:
                if content.strip():
                    raise ValidationError(
                        [{"field": key, "message": "path required for provided content"}]
                    )
                continue
            try:
                normalized = self._normalize_multiline_path(key, Path(str(path_value)))
            except ValidationError as exc:
                errors.extend(exc.errors)
                continue
            pending_writes.append((normalized, content))

        if errors:
            raise ValidationError(errors)

        for target, content in pending_writes:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _normalize_multiline_path(self, key: str, raw: Path) -> Path:
        normalized = raw.expanduser()
        if not normalized.is_absolute():
            raise ValidationError(
                [{"field": key, "message": "path must be absolute"}]
            )
        try:
            resolved = normalized.resolve()
        except FileNotFoundError:
            resolved = normalized.resolve(strict=False)
        if not self._is_path_allowed(resolved):
            allowed = ", ".join(str(directory) for directory in self.allowed_multiline_dirs)
            raise ValidationError(
                [{"field": key, "message": f"path must reside within: {allowed}"}]
            )
        return resolved

    def _is_path_allowed(self, path: Path) -> bool:
        for directory in self.allowed_multiline_dirs:
            try:
                path.relative_to(directory)
            except ValueError:
                continue
            return True
        return False


__all__ = ["ConfigStore", "ConfigError", "ValidationError", "ConfigData"]
