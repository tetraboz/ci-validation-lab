#!/usr/bin/env python3
"""Generic deterministic dependency-closure resolver for synthetic fixtures."""
from __future__ import annotations

import hashlib
from pathlib import Path


class ClosureError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def exact_file(root: Path, raw: object, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ClosureError(f"invalid path for {label}: {raw!r}")
    if "\\" in raw:
        raise ClosureError(f"non-canonical path for {label}: {raw}")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ClosureError(f"non-canonical or escaping path for {label}: {raw}")
    rel = Path(*parts)
    if rel.is_absolute() or rel.as_posix() != raw:
        raise ClosureError(f"non-canonical exact path for {label}: {raw}")
    candidate = root / rel
    component = root
    for part in rel.parts:
        component = component / part
        if component.is_symlink():
            raise ClosureError(f"symlink path component forbidden for {label}: {raw}")
    if not candidate.is_file():
        raise ClosureError(f"unresolved regular file for {label}: {raw}")
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ClosureError(f"path escapes root for {label}: {raw}") from exc
    return candidate


def _validated_nodes(spec: dict) -> dict[str, dict]:
    nodes = spec.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ClosureError("nodes must be a non-empty mapping")
    for node_id, row in nodes.items():
        if not isinstance(node_id, str) or not node_id or not isinstance(row, dict):
            raise ClosureError("malformed node table")
        deps = row.get("dependencies")
        if not isinstance(deps, list) or any(not isinstance(x, str) or not x for x in deps):
            raise ClosureError(f"malformed dependencies for {node_id}")
        if len(deps) != len(set(deps)):
            raise ClosureError(f"duplicate dependency for {node_id}")
    return nodes


def _dependency_first_closure(nodes: dict[str, dict], entrypoints: list[str]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []

    def visit(node_id: str) -> None:
        if node_id not in nodes:
            raise ClosureError(f"unknown dependency or entrypoint: {node_id}")
        if node_id in visiting:
            raise ClosureError(f"dependency cycle: {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in nodes[node_id]["dependencies"]:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)
        order.append(node_id)

    for entrypoint in entrypoints:
        visit(entrypoint)
    return order


def resolve(root: Path, spec: dict) -> dict[str, object]:
    if spec.get("schema_version") != 1:
        raise ClosureError("schema version mismatch")
    if spec.get("status") != "ACTIVE_SYNTHETIC_ROUTE":
        raise ClosureError("route status mismatch")

    nodes = _validated_nodes(spec)
    entrypoints = spec.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        raise ClosureError("entrypoints must be non-empty")
    if any(not isinstance(x, str) or not x for x in entrypoints):
        raise ClosureError("malformed entrypoint")
    if len(entrypoints) != len(set(entrypoints)):
        raise ClosureError("duplicate entrypoint")

    computed = _dependency_first_closure(nodes, entrypoints)
    declared = spec.get("declared_closure")
    if not isinstance(declared, list) or not declared:
        raise ClosureError("declared closure must be non-empty")
    if len(declared) != len(set(declared)):
        raise ClosureError("duplicate declared closure member")
    if declared != computed:
        raise ClosureError(f"declared closure mismatch: expected={computed!r} actual={declared!r}")

    bindings = spec.get("content_bindings")
    if not isinstance(bindings, dict):
        raise ClosureError("content bindings must be a mapping")

    read_set: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    total_bytes = 0
    required_paths: list[str] = []
    for node_id in computed:
        raw = nodes[node_id].get("path")
        path = exact_file(root, raw, f"nodes.{node_id}.path")
        rel = path.relative_to(root).as_posix()
        if rel in seen_paths:
            raise ClosureError(f"duplicate node path: {rel}")
        seen_paths.add(rel)
        required_paths.append(rel)
        expected = bindings.get(rel)
        if not isinstance(expected, str) or len(expected) != 40:
            raise ClosureError(f"missing or invalid content binding: {rel}")
        actual = git_blob_sha(path)
        if actual != expected:
            raise ClosureError(f"content identity mismatch: {rel}")
        size = path.stat().st_size
        total_bytes += size
        read_set.append({"node": node_id, "path": rel, "bytes": size, "git_blob_sha": actual})

    if set(bindings) != set(required_paths):
        extra = sorted(set(bindings) - set(required_paths))
        missing = sorted(set(required_paths) - set(bindings))
        raise ClosureError(f"binding/closure mismatch missing={missing!r} extra={extra!r}")

    budget = spec.get("soft_budget_bytes")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise ClosureError("invalid soft budget")

    return {
        "status": "GENERIC_ROUTE_CLOSURE_RESOLVED",
        "entrypoints": list(entrypoints),
        "closure": computed,
        "read_set": read_set,
        "path_count": len(read_set),
        "total_bytes": total_bytes,
        "soft_budget_bytes": budget,
        "under_soft_budget": total_bytes <= budget,
        "budget_overage_drops_required_content": False,
    }
