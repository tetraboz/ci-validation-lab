#!/usr/bin/env python3
"""Synthetic regressions for public validation Bundle 003."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def strict_hash_mode_requested() -> bool:
    argv = getattr(sys, "orig_argv", [])
    for i, arg in enumerate(argv):
        if arg == "--check-hash-based-pycs" and i + 1 < len(argv) and argv[i + 1] == "always":
            return True
        if arg == "--check-hash-based-pycs=always":
            return True
    return False


if __name__ == "__main__" and (
    not sys.flags.isolated
    or not sys.flags.dont_write_bytecode
    or not strict_hash_mode_requested()
):
    raise SystemExit("BUNDLE_003_FAIL: strict isolated no-bytecode Python required")

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("bundle003_schema", ROOT / "strict_schema.py")
if spec is None or spec.loader is None:
    raise RuntimeError("missing strict_schema.py")
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)

SYNTHETIC_SCHEMA = {
    "required": {
        "schema_version": {"type": "integer", "enum": [1]},
        "status": {"type": "string", "enum": ["ACTIVE"]},
        "name": {"type": "string", "nonempty": True},
        "enabled": {"type": "boolean"},
        "tags": {"type": "list", "items_type": "string"},
        "nested": {"type": "mapping"},
    },
    "optional": {
        "note": {"type": "string"},
    },
    "reject_unknown": True,
}

VALID_YAML = """schema_version: 1
status: ACTIVE
name: alpha
enabled: true
tags:
  - one
  - two
nested:
  value: 3
"""

VALID_JSON = """{
  "schema_version": 1,
  "status": "ACTIVE",
  "name": "alpha",
  "enabled": true,
  "tags": ["one", "two"],
  "nested": {"value": 3}
}"""


def expect_schema_fail(label: str, fn) -> None:
    try:
        fn()
    except schema.SchemaError:
        return
    raise AssertionError(f"false PASS: {label}")


def main() -> int:
    labels: list[str] = []

    yaml_doc = schema.load_yaml_text(VALID_YAML)
    json_doc = schema.load_json_text(VALID_JSON)
    schema.validate_record(yaml_doc, SYNTHETIC_SCHEMA)
    schema.validate_record(json_doc, SYNTHETIC_SCHEMA)
    if schema.resolve_selector(yaml_doc, "nested.value") != 3:
        raise AssertionError("positive selector mismatch")
    schema.compile_python_text("def f(x):\n    return x + 1\n")

    def negative(label: str, fn) -> None:
        expect_schema_fail(label, fn)
        labels.append(label)

    negative(
        "yaml_duplicate_top_level",
        lambda: schema.load_yaml_text("schema_version: 1\nschema_version: 2\n"),
    )
    negative(
        "yaml_duplicate_nested",
        lambda: schema.load_yaml_text("outer:\n  x: 1\n  x: 2\n"),
    )
    negative(
        "yaml_malformed",
        lambda: schema.load_yaml_text("outer: [1, 2\n"),
    )
    negative(
        "json_duplicate_top_level",
        lambda: schema.load_json_text('{"x":1,"x":2}'),
    )
    negative(
        "json_duplicate_nested",
        lambda: schema.load_json_text('{"outer":{"x":1,"x":2}}'),
    )
    negative(
        "json_malformed",
        lambda: schema.load_json_text('{"x":1'),
    )
    negative(
        "document_not_mapping",
        lambda: schema.validate_record(schema.load_yaml_text("- one\n- two\n"), SYNTHETIC_SCHEMA),
    )

    missing = dict(yaml_doc)
    missing.pop("name")
    negative(
        "missing_required_field",
        lambda: schema.validate_record(missing, SYNTHETIC_SCHEMA),
    )

    unknown = dict(yaml_doc)
    unknown["extra"] = 1
    negative(
        "unknown_field",
        lambda: schema.validate_record(unknown, SYNTHETIC_SCHEMA),
    )

    version_string = dict(yaml_doc)
    version_string["schema_version"] = "1"
    negative(
        "schema_version_string_not_integer",
        lambda: schema.validate_record(version_string, SYNTHETIC_SCHEMA),
    )

    version_bool = dict(yaml_doc)
    version_bool["schema_version"] = True
    negative(
        "schema_version_bool_not_integer",
        lambda: schema.validate_record(version_bool, SYNTHETIC_SCHEMA),
    )

    enum_bad = dict(yaml_doc)
    enum_bad["status"] = "PAUSED"
    negative(
        "enum_mismatch",
        lambda: schema.validate_record(enum_bad, SYNTHETIC_SCHEMA),
    )

    empty_name = dict(yaml_doc)
    empty_name["name"] = ""
    negative(
        "empty_nonempty_string",
        lambda: schema.validate_record(empty_name, SYNTHETIC_SCHEMA),
    )

    bad_items = dict(yaml_doc)
    bad_items["tags"] = ["one", 2]
    negative(
        "list_item_type_mismatch",
        lambda: schema.validate_record(bad_items, SYNTHETIC_SCHEMA),
    )

    negative(
        "selector_missing_leaf",
        lambda: schema.resolve_selector(yaml_doc, "nested.missing"),
    )
    negative(
        "selector_non_mapping_intermediate",
        lambda: schema.resolve_selector(yaml_doc, "name.value"),
    )
    negative(
        "python_syntax_error",
        lambda: schema.compile_python_text("def broken(:\n    pass\n"),
    )
    negative(
        "python_null_byte_rejected",
        lambda: schema.compile_python_text("x = 1\x00\n"),
    )

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        "status": "PUBLIC_VALIDATION_BUNDLE_003_PASS",
        "authority": CONTRACT["authority"],
        "regression_count": len(labels),
        "yaml_duplicate_keys": "FAIL_CLOSED",
        "json_duplicate_keys": "FAIL_CLOSED",
        "exact_type_schema": "PASS",
        "selector_resolution": "PASS",
        "python_compile_check": "PASS"
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
