#!/usr/bin/env python3
"""Valida updater.conf frente al esquema descriptivo."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
  sys.path.insert(0, str(SRC_DIR))

from pullpilot.resources import get_resource_path


@dataclass
class VariableDefinition:
  name: str
  type: str
  default: Any
  description: str
  constraints: Dict[str, Any]


class SchemaError(RuntimeError):
  pass


def load_schema(schema_path: Path) -> Dict[str, VariableDefinition]:
  with schema_path.open(encoding="utf-8") as fh:
    data = json.load(fh)

  variables = data.get("variables")
  if not isinstance(variables, list):
    raise SchemaError("El esquema debe incluir una lista 'variables'.")

  definitions: Dict[str, VariableDefinition] = {}
  for entry in variables:
    if not isinstance(entry, dict):
      raise SchemaError("Cada variable del esquema debe ser un objeto JSON.")
    try:
      name = entry["name"]
      var_type = entry["type"]
      default = entry.get("default")
      description = entry.get("description", "")
      constraints = entry.get("constraints", {})
    except KeyError as exc:  # pragma: no cover - validación defensiva
      raise SchemaError(f"Faltan campos obligatorios en el esquema: {exc}") from exc

    if name in definitions:
      raise SchemaError(f"Variable duplicada en el esquema: {name}")
    definitions[name] = VariableDefinition(name, var_type, default, description, constraints)

  return definitions


def strip_inline_comment(line: str) -> str:
  in_single = False
  in_double = False
  escaped = False
  for idx, char in enumerate(line):
    if escaped:
      escaped = False
      continue
    if char == "\\":
      escaped = True
      continue
    if char == "'" and not in_double:
      in_single = not in_single
      continue
    if char == '"' and not in_single:
      in_double = not in_double
      continue
    if char == "#" and not in_single and not in_double:
      return line[:idx].rstrip()
  return line


def parse_conf(conf_path: Path) -> Dict[str, Tuple[str, int]]:
  assignments: Dict[str, Tuple[str, int]] = {}
  with conf_path.open(encoding="utf-8") as fh:
    for lineno, raw_line in enumerate(fh, start=1):
      line = raw_line.strip()
      if not line or line.startswith("#"):
        continue
      line = strip_inline_comment(raw_line).strip()
      if not line:
        continue
      match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
      if not match:
        raise ValueError(f"Línea {lineno}: formato no reconocido: {raw_line.rstrip()}" )
      key = match.group(1)
      value = match.group(2).strip()
      assignments[key] = (value, lineno)
  return assignments


def _unquote(value: str) -> str:
  if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
    quote = value[0]
    inner = value[1:-1]
    if quote == '"':
      inner = inner.replace("\\\"", '"').replace("\\\\", "\\")
    return inner
  return value


def _split_list(value: str, separator: str) -> List[str]:
  if not value:
    return []
  if separator == "whitespace":
    return value.split()
  if separator == "comma":
    return [item.strip() for item in value.split(",") if item.strip()]
  raise SchemaError(f"Separador de lista desconocido: {separator}")


def convert_value(name: str, raw_value: str, definition: VariableDefinition, lineno: int) -> Tuple[Any, List[str]]:
  errors: List[str] = []
  constraints = definition.constraints
  processed = _unquote(raw_value)

  if constraints.get("is_list"):
    separator = constraints.get("list_separator", "whitespace")
    items = _split_list(processed, separator)
    converted_items: List[Any] = []
    for item in items:
      converted, item_errors = _convert_scalar(name, item, definition.type, lineno)
      errors.extend(item_errors)
      if item_errors:
        continue
      converted_items.append(converted)
    value: Any = converted_items
  else:
    value, scalar_errors = _convert_scalar(name, processed, definition.type, lineno)
    errors.extend(scalar_errors)

  if not errors:
    errors.extend(validate_constraints(name, value, definition, lineno))
  return value, errors


def _convert_scalar(name: str, value: str, var_type: str, lineno: int) -> Tuple[Any, List[str]]:
  if var_type == "string":
    return value, []
  if var_type == "integer":
    try:
      return int(value), []
    except ValueError:
      return None, [f"{name} (línea {lineno}) debe ser un entero válido"]
  if var_type == "boolean":
    lowered = value.lower()
    true_values = {"true", "1", "yes", "on"}
    false_values = {"false", "0", "no", "off"}
    if lowered in true_values:
      return True, []
    if lowered in false_values:
      return False, []
    return None, [f"{name} (línea {lineno}) debe ser booleano (true/false)"]
  raise SchemaError(f"Tipo no soportado en el esquema: {var_type}")


def validate_constraints(name: str, value: Any, definition: VariableDefinition, lineno: int) -> List[str]:
  constraints = definition.constraints
  errors: List[str] = []

  if constraints.get("is_list"):
    sequence = value if isinstance(value, list) else []
    min_length = constraints.get("min_length")
    if isinstance(min_length, int) and len(sequence) < min_length:
      errors.append(f"{name} (línea {lineno}) debe contener al menos {min_length} elementos")
    max_length = constraints.get("max_length")
    if isinstance(max_length, int) and len(sequence) > max_length:
      errors.append(f"{name} (línea {lineno}) no puede superar {max_length} elementos")
    allowed_values = constraints.get("allowed_values")
    if allowed_values:
      invalid = [item for item in sequence if item not in allowed_values]
      if invalid:
        errors.append(
          f"{name} (línea {lineno}) contiene valores no permitidos: {', '.join(invalid)}"
        )
    return errors

  if definition.type == "string":
    if not constraints.get("allow_empty", False) and value == "":
      errors.append(f"{name} (línea {lineno}) no puede ser vacío")
    min_length = constraints.get("min_length")
    if isinstance(min_length, int) and len(value) < min_length:
      errors.append(f"{name} (línea {lineno}) debe tener al menos {min_length} caracteres")
    max_length = constraints.get("max_length")
    if isinstance(max_length, int) and len(value) > max_length:
      errors.append(f"{name} (línea {lineno}) debe tener como máximo {max_length} caracteres")
    pattern = constraints.get("pattern")
    if pattern and not re.fullmatch(pattern, value):
      errors.append(f"{name} (línea {lineno}) no cumple el patrón requerido ({pattern})")
    allowed_values = constraints.get("allowed_values")
    if allowed_values and value not in allowed_values:
      errors.append(f"{name} (línea {lineno}) debe ser uno de: {', '.join(allowed_values)}")
  elif definition.type == "integer":
    minimum = constraints.get("min")
    if minimum is not None and value < minimum:
      errors.append(f"{name} (línea {lineno}) debe ser >= {minimum}")
    maximum = constraints.get("max")
    if maximum is not None and value > maximum:
      errors.append(f"{name} (línea {lineno}) debe ser <= {maximum}")
    allowed_values = constraints.get("allowed_values")
    if allowed_values and value not in allowed_values:
      errors.append(f"{name} (línea {lineno}) debe ser uno de: {', '.join(map(str, allowed_values))}")
  elif definition.type == "boolean":
    # allowed_values para booleano permitiría restringir a true/false concretos si se quisiese.
    pass

  return errors


def validate_config(
  definitions: Dict[str, VariableDefinition],
  assignments: Dict[str, Tuple[str, int]],
  schema_path: Path,
) -> int:
  errors: List[str] = []

  schema_names = set(definitions.keys())
  for key in assignments:
    if key not in schema_names:
      value, lineno = assignments[key]
      errors.append(f"{key} (línea {lineno}) no está definido en {schema_path}")

  for name, definition in definitions.items():
    raw = assignments.get(name)
    if raw is None:
      continue
    raw_value, lineno = raw
    _, local_errors = convert_value(name, raw_value, definition, lineno)
    errors.extend(local_errors)

  if errors:
    for err in errors:
      print(f"ERROR: {err}")
    return 1

  print(f"Configuración válida según {schema_path}")
  return 0


def main(argv: Iterable[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description="Valida updater.conf frente al esquema JSON")
  parser.add_argument(
    "--config",
    default=None,
    help=(
      "Ruta del archivo de configuración a validar. "
      "Por defecto se usa el `updater.conf` empaquetado."
    ),
  )
  parser.add_argument(
    "--schema",
    default=None,
    help=(
      "Ruta del esquema JSON. "
      "Por defecto se usa el esquema empaquetado."
    ),
  )
  args = parser.parse_args(list(argv) if argv is not None else None)

  if args.schema is None:
    schema_path = get_resource_path("config/schema.json")
  else:
    schema_path = Path(args.schema).expanduser().resolve()

  if args.config is None:
    config_path = get_resource_path("config/updater.conf")
  else:
    config_path = Path(args.config).expanduser().resolve()

  definitions = load_schema(schema_path)
  assignments = parse_conf(config_path)
  return validate_config(definitions, assignments, schema_path)


if __name__ == "__main__":
  sys.exit(main())
