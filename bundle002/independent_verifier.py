#!/usr/bin/env python3
"""Independent implementation for generic synthetic route-closure verification."""
from __future__ import annotations

import hashlib
from pathlib import Path


class IndependentError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    payload = path.read_bytes()
    prefix = ("blob %d\0" % len(payload)).encode("ascii")
    return hashlib.sha1(prefix + payload).hexdigest()


def _file(root: Path, raw: object) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise IndependentError("bad path")
    tokens = raw.split("/")
    if any(x in {"", ".", ".."} for x in tokens):
        raise IndependentError("bad path")
    rel = Path(*tokens)
    if rel.is_absolute() or rel.as_posix() != raw:
        raise IndependentError("bad path")
    cursor = root
    for token in rel.parts:
        cursor = cursor / token
        if cursor.is_symlink():
            raise IndependentError("symlink path")
    target = root / rel
    if not target.is_file():
        raise IndependentError("not a file")
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise IndependentError("escape") from exc
    return target


def _walk(nodes: dict[str, dict], entrypoints: list[str]) -> list[str]:
    done: set[str] = set()
    active: set[str] = set()
    output: list[str] = []
    for start in entrypoints:
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node_id, expanded = stack.pop()
            if node_id not in nodes:
                raise IndependentError("unknown node")
            if expanded:
                active.discard(node_id)
                if node_id not in done:
                    done.add(node_id)
                    output.append(node_id)
                continue
            if node_id in done:
                continue
            if node_id in active:
                raise IndependentError("cycle")
            row = nodes[node_id]
            if not isinstance(row, dict):
                raise IndependentError("bad node")
            deps = row.get("dependencies")
            if not isinstance(deps, list) or any(not isinstance(x, str) or not x for x in deps):
                raise IndependentError("bad dependencies")
            if len(deps) != len(set(deps)):
                raise IndependentError("duplicate dependency")
            active.add(node_id)
            stack.append((node_id, True))
            for dep in reversed(deps):
                stack.append((dep, False))
    return output


def verify(root: Path, spec: dict) -> dict[str, object]:
    if spec.get("schema_version") != 1 or spec.get("status") != "ACTIVE_SYNTHETIC_ROUTE":
        raise IndependentError("bad manifest identity")
    nodes = spec.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise IndependentError("bad nodes")
    entrypoints = spec.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        raise IndependentError("bad entrypoints")
    if any(not isinstance(x, str) or not x for x in entrypoints) or len(entrypoints) != len(set(entrypoints)):
        raise IndependentError("bad entrypoints")

    closure = _walk(nodes, entrypoints)
    declared = spec.get("declared_closure")
    if not isinstance(declared, list) or not declared or len(declared) != len(set(declared)):
        raise IndependentError("bad declared closure")
    if closure != declared:
        raise IndependentError("closure mismatch")

    bindings = spec.get("content_bindings")
    if not isinstance(bindings, dict):
        raise IndependentError("bad bindings")
    paths: list[str] = []
    total = 0
    for node_id in closure:
        target = _file(root, nodes[node_id].get("path"))
        rel = target.relative_to(root).as_posix()
        if rel in paths:
            raise IndependentError("duplicate path")
        paths.append(rel)
        if bindings.get(rel) != _sha(target):
            raise IndependentError("binding mismatch")
        total += target.stat().st_size
    if set(paths) != set(bindings):
        raise IndependentError("binding set mismatch")

    budget = spec.get("soft_budget_bytes")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise IndependentError("bad budget")

    return {
        "status": "INDEPENDENT_GENERIC_ROUTE_CLOSURE_PASS",
        "closure": closure,
        "path_count": len(paths),
        "total_bytes": total,
        "under_soft_budget": total <= budget,
        "budget_overage_drops_required_content": False,
    }
