"""A deliberately small JSON-Schema validator for the vendored Codex hook schemas.

Only the keywords those generated schemas use are supported (type, properties, required,
additionalProperties, enum, const, $ref into definitions, allOf/anyOf/oneOf, default,
format, title/description). Anything else fails loudly, so a future schema feature cannot
be silently ignored. No third-party validator is needed for the dev environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMAS = Path(__file__).parent / "fixtures" / "codex_schemas"

_ANNOTATIONS = {"$schema", "title", "description", "default", "format", "definitions"}
_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def load(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def errors(
    instance: Any, schema: dict[str, Any], root: dict[str, Any] | None = None, at: str = "$"
) -> list[str]:
    if schema is True:  # boolean schemas: `tool_input: true` accepts any JSON value
        return []
    if schema is False:
        return [f"{at}: no value is allowed here"]
    root = root if root is not None else schema
    found: list[str] = []
    for keyword in schema:
        if keyword not in _ANNOTATIONS | {
            "type", "properties", "required", "additionalProperties", "enum", "const",
            "$ref", "allOf", "anyOf", "oneOf", "items", "minimum", "maximum",
        }:
            raise ValueError(f"unsupported schema keyword {keyword!r} at {at}")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            raise ValueError(f"unsupported $ref {ref}")
        found += errors(instance, root["definitions"][ref.split("/")[-1]], root, at)
    for sub in schema.get("allOf", []):
        found += errors(instance, sub, root, at)
    if "anyOf" in schema and not any(not errors(instance, s, root, at) for s in schema["anyOf"]):
        found.append(f"{at}: matches none of anyOf")
    if "oneOf" in schema and sum(not errors(instance, s, root, at) for s in schema["oneOf"]) != 1:
        found.append(f"{at}: must match exactly one of oneOf")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, t) for t in types):
            found.append(f"{at}: expected {types}, got {type(instance).__name__}")
            return found
    if "enum" in schema and instance not in schema["enum"]:
        found.append(f"{at}: {instance!r} not in {schema['enum']}")
    if "const" in schema and instance != schema["const"]:
        found.append(f"{at}: {instance!r} != {schema['const']!r}")
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                found.append(f"{at}: missing required {name!r}")
        for name, value in instance.items():
            if name in props:
                found += errors(value, props[name], root, f"{at}.{name}")
            elif schema.get("additionalProperties") is False:
                found.append(f"{at}: unexpected field {name!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                found += errors(value, schema["additionalProperties"], root, f"{at}.{name}")
    if isinstance(instance, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(instance):
            found += errors(item, schema["items"], root, f"{at}[{i}]")
    return found


def validate(instance: Any, name: str) -> list[str]:
    return errors(instance, load(name))
