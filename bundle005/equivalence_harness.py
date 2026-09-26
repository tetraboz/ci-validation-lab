#!/usr/bin/env python3
"""Generic exact-representation equivalence harness for synthetic fixtures only."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any


class EquivalenceError(RuntimeError):
    pass


def type_exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        if len(left) != len(right):
            return False
        unmatched = list(right.items())
        for left_key, left_value in left.items():
            match_index = None
            for index, (right_key, right_value) in enumerate(unmatched):
                if type_exact_equal(left_key, right_key):
                    if not type_exact_equal(left_value, right_value):
                        return False
                    match_index = index
                    break
            if match_index is None:
                return False
            unmatched.pop(match_index)
        return not unmatched
    if isinstance(left, list):
        return len(left) == len(right) and all(
            type_exact_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def resolve_selector(doc: Any, selector: str) -> Any:
    if not isinstance(selector, str) or not selector:
        raise EquivalenceError("selector must be a non-empty string")
    cur = doc
    for part in selector.split("."):
        if not part or not isinstance(cur, Mapping) or part not in cur:
            raise EquivalenceError(f"unresolved selector: {selector}")
        cur = cur[part]
    return cur


def select_value(doc: Any, expression: str) -> Any:
    if not isinstance(expression, str) or not expression:
        raise EquivalenceError("empty path expression")
    if "[" in expression:
        if not expression.endswith("]") or expression.count("[") != 1:
            raise EquivalenceError(f"unsupported path expression: {expression}")
        base, modifier = expression[:-1].split("[", 1)
    else:
        base, modifier = expression, None

    value = resolve_selector(doc, base)
    if modifier is None:
        return value

    if modifier.startswith("item="):
        item = modifier[len("item="):]
        if not isinstance(value, list) or item not in value:
            raise EquivalenceError(f"selected item not found: {expression}")
        return item

    if modifier.startswith("items="):
        items = modifier[len("items="):].split(",")
        if not isinstance(value, list):
            raise EquivalenceError("ordered-subsequence source is not a list")
        positions: list[int] = []
        for item in items:
            if item not in value:
                raise EquivalenceError(f"ordered-subsequence item not found: {item}")
            positions.append(value.index(item))
        if positions != sorted(positions):
            raise EquivalenceError("declared ordered subsequence is reordered")
        return items

    if modifier.startswith("excluding="):
        if not isinstance(value, Mapping):
            raise EquivalenceError("exclusion source is not a mapping")
        result = copy.deepcopy(dict(value))
        exclusions = modifier[len("excluding="):].split(",")
        for exclusion in exclusions:
            parts = exclusion.split(".")
            cur: Any = result
            for part in parts[:-1]:
                if not isinstance(cur, Mapping) or part not in cur:
                    raise EquivalenceError(f"exclusion path not found: {exclusion}")
                cur = cur[part]
            leaf = parts[-1]
            if not isinstance(cur, dict) or leaf not in cur:
                raise EquivalenceError(f"exclusion leaf not found: {exclusion}")
            del cur[leaf]
        return result

    raise EquivalenceError(f"unsupported selector modifier: {modifier}")


def _registered_file(registry: Mapping[str, Any], key: str) -> str:
    components = registry.get("components")
    resolution = registry.get("resolution")
    if not isinstance(components, Mapping) or not isinstance(resolution, Mapping):
        raise EquivalenceError("synthetic registry malformed")
    meta = components.get(key)
    if not isinstance(meta, Mapping):
        raise EquivalenceError(f"component registration missing: {key}")
    root = resolution.get("root")
    rel = meta.get("path")
    if not isinstance(root, str) or not root or not isinstance(rel, str) or not rel:
        raise EquivalenceError(f"component path missing: {key}")
    return (PurePosixPath(root) / PurePosixPath(rel)).as_posix()


def _subject_signature(expression: str, wrapper: str) -> tuple[str, ...]:
    base = expression.split("[", 1)[0]
    if not base:
        raise EquivalenceError("empty subject path")
    parts = base.split(".")
    if parts and parts[0] == wrapper:
        parts = parts[1:]
    return tuple(parts)


def require_subject_binding(cert: Mapping[str, Any], registry: Mapping[str, Any]) -> None:
    source = cert.get("source")
    target = cert.get("target")
    valid_under = cert.get("valid_under")
    if not all(isinstance(x, Mapping) for x in (source, target, valid_under)):
        raise EquivalenceError("certificate missing source/target/valid_under mapping")

    family = valid_under.get("component_family")
    source_version = valid_under.get("source_version")
    target_version = valid_under.get("target_version")
    if not isinstance(family, str) or not family:
        raise EquivalenceError("component family missing")
    if type(source_version) is not int:
        raise EquivalenceError("source version missing or not exact integer")
    if type(target_version) is not int:
        raise EquivalenceError("target version missing or not exact integer")

    source_key = f"{family}@{source_version}"
    target_key = f"{family}@{target_version}"
    if source.get("file") != _registered_file(registry, source_key):
        raise EquivalenceError("source file is not registered source component")
    if target.get("file") != _registered_file(registry, target_key):
        raise EquivalenceError("target file is not registered target component")

    source_path = source.get("path")
    target_path = target.get("path")
    if not isinstance(source_path, str) or not isinstance(target_path, str):
        raise EquivalenceError("certificate path identity incomplete")
    if _subject_signature(source_path, "source_payload") != _subject_signature(
        target_path, "target_delta"
    ):
        raise EquivalenceError("semantic subject/path mismatch")


def certify_exact(
    source_doc: Any,
    target_doc: Any,
    cert: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, object]:
    require_subject_binding(cert, registry)
    evidence = cert.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("machine_check") is not True:
        raise EquivalenceError("exact certificate requires machine_check=true")

    source = cert["source"]
    target = cert["target"]
    source_value = select_value(source_doc, source["path"])
    target_value = select_value(target_doc, target["path"])
    if not type_exact_equal(source_value, target_value):
        return {
            "state": "UNRESOLVED",
            "reason": "TYPE_EXACT_STRUCTURAL_MISMATCH",
        }
    return {
        "state": "CERTIFIED_EXACT",
        "reason": "TYPE_EXACT_STRUCTURAL_IDENTITY",
    }


def validate_explicit_delta(
    *,
    source_members: list[str],
    certified_exact: list[str],
    unresolved: list[str],
    uncovered: list[str],
    explicit_delta: list[str],
    whole_equivalence_claimed: bool,
) -> dict[str, object]:
    vectors = {
        "source_members": source_members,
        "certified_exact": certified_exact,
        "unresolved": unresolved,
        "uncovered": uncovered,
        "explicit_delta": explicit_delta,
    }
    for name, values in vectors.items():
        if type(values) is not list or any(type(x) is not str or not x for x in values):
            raise EquivalenceError(f"invalid {name}")
        if len(values) != len(set(values)):
            raise EquivalenceError(f"duplicate member in {name}")

    source = set(source_members)
    certified = set(certified_exact)
    unresolved_set = set(unresolved)
    uncovered_set = set(uncovered)
    delta = set(explicit_delta)

    if certified - source or unresolved_set - source or uncovered_set - source:
        raise EquivalenceError("classification references unknown source member")
    if certified & unresolved_set or certified & uncovered_set:
        raise EquivalenceError("certified member cannot also be unresolved/uncovered")

    must_retain = unresolved_set | uncovered_set
    if not must_retain <= delta:
        raise EquivalenceError("uncertified source member omitted from explicit delta")
    if delta - source:
        raise EquivalenceError("explicit delta contains unknown source member")
    if certified & delta:
        raise EquivalenceError("certified exact member unnecessarily remains in delta")
    if whole_equivalence_claimed and must_retain:
        raise EquivalenceError("whole equivalence cannot be claimed with unresolved content")

    accounted = certified | delta
    if accounted != source:
        raise EquivalenceError("source coverage is incomplete")

    return {
        "status": "GENERIC_EXPLICIT_DELTA_COVERAGE_PASS",
        "certified_count": len(certified),
        "explicit_delta_count": len(delta),
        "unresolved_count": len(unresolved_set),
        "uncovered_count": len(uncovered_set),
        "whole_equivalence_allowed": not must_retain,
    }
