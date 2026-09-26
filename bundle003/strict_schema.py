#!/usr/bin/env python3
"""Generic strict parsing and small schema helpers for synthetic public validation."""
from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

import yaml


class SchemaError(RuntimeError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise SchemaError(f"unhashable YAML mapping key: {key!r}") from exc
        if duplicate:
            raise SchemaError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_yaml_text(text: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except SchemaError:
        raise
    except yaml.YAMLError as exc:
        raise SchemaError(f"malformed YAML: {exc}") from exc


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SchemaError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def load_json_text(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_json_pairs)
    except SchemaError:
        raise
    except json.JSONDecodeError as exc:
        raise SchemaError(f"malformed JSON: {exc}") from exc


_TYPE_TABLE = {
    "mapping": dict,
    "list": list,
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": (int, float),
}


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "number":
        return type(value) in (int, float)
    target = _TYPE_TABLE.get(expected)
    if target is None:
        raise SchemaError(f"unknown schema type: {expected}")
    return type(value) is target


def _validate_rule(field: str, value: Any, rule: Mapping[str, Any]) -> None:
    expected = rule.get("type")
    if not isinstance(expected, str):
        raise SchemaError(f"schema rule missing type: {field}")
    if not _type_matches(value, expected):
        raise SchemaError(
            f"type mismatch for {field}: expected={expected} actual={type(value).__name__}"
        )
    if rule.get("nonempty") is True:
        if expected == "string" and value == "":
            raise SchemaError(f"empty string forbidden: {field}")
        if expected in {"list", "mapping"} and not value:
            raise SchemaError(f"empty collection forbidden: {field}")
    if "enum" in rule:
        enum = rule["enum"]
        if not isinstance(enum, list) or value not in enum:
            raise SchemaError(f"enum mismatch: {field}")
    if expected == "list" and "items_type" in rule:
        item_type = rule["items_type"]
        if not isinstance(item_type, str):
            raise SchemaError(f"invalid items_type rule: {field}")
        for index, item in enumerate(value):
            if not _type_matches(item, item_type):
                raise SchemaError(
                    f"list item type mismatch: {field}[{index}] expected={item_type}"
                )


def validate_record(doc: Any, schema: Mapping[str, Any]) -> dict[str, Any]:
    if type(doc) is not dict:
        raise SchemaError("document must be a mapping")
    if any(type(key) is not str for key in doc):
        raise SchemaError("document keys must be strings")

    required = schema.get("required", {})
    optional = schema.get("optional", {})
    if type(required) is not dict or type(optional) is not dict:
        raise SchemaError("schema required/optional sections must be mappings")

    for field, rule in required.items():
        if field not in doc:
            raise SchemaError(f"missing required field: {field}")
        if not isinstance(rule, Mapping):
            raise SchemaError(f"invalid schema rule: {field}")
        _validate_rule(field, doc[field], rule)

    for field, rule in optional.items():
        if field in doc:
            if not isinstance(rule, Mapping):
                raise SchemaError(f"invalid schema rule: {field}")
            _validate_rule(field, doc[field], rule)

    if schema.get("reject_unknown") is True:
        allowed = set(required) | set(optional)
        unknown = sorted(set(doc) - allowed)
        if unknown:
            raise SchemaError(f"unknown fields: {unknown}")

    return dict(doc)


def resolve_selector(doc: Any, selector: str) -> Any:
    if not isinstance(selector, str) or not selector:
        raise SchemaError("selector must be a non-empty string")
    current = doc
    for part in selector.split("."):
        if not part or not isinstance(current, Mapping) or part not in current:
            raise SchemaError(f"unresolved selector: {selector}")
        current = current[part]
    return current


def compile_python_text(source: str) -> None:
    if not isinstance(source, str):
        raise SchemaError("Python source must be text")
    try:
        compile(source, "<synthetic>", "exec")
    except (SyntaxError, ValueError) as exc:
        raise SchemaError(f"Python source does not compile: {exc}") from exc
