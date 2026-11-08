"""Minimal JSON Schema subset validator (DECISIONS D02).

Supported keywords: type, const, enum, pattern, minLength, minItems, items,
required, properties, additionalProperties(false), $ref to #/definitions/*.
"""
from __future__ import annotations

import re
from typing import Any

_TYPE_NAMES = {
    dict: "object", list: "array", str: "string", bool: "boolean", int: "integer", float: "number", type(None): "null",
}


def _type_name(value: Any) -> str:
    return _TYPE_NAMES.get(type(value), type(value).__name__)


def _is_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise ValueError(f"unsupported schema type {expected!r}")


def validate(instance: Any, schema: dict) -> list[str]:
    errors: list[str] = []
    _validate(instance, schema, schema, "$", errors)
    return errors


def _resolve(ref: str, root: dict) -> dict:
    prefix = "#/definitions/"
    if not ref.startswith(prefix):
        raise ValueError(f"unsupported $ref {ref!r}")
    return root["definitions"][ref[len(prefix):]]


def _validate(value: Any, schema: dict, root: dict, path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        schema = _resolve(schema["$ref"], root)
    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_is_type(value, t) for t in options):
            errors.append(f"{path}: expected {'/'.join(options)}, got {_type_name(value)}")
            return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            errors.append(f"{path}: must not be empty")
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            errors.append(f"{path}: {value!r} does not match {pattern}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                _validate(item, item_schema, root, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                _validate(value[key], sub, root, f"{path}.{key}", errors)
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unknown field '{key}'")
