#!/usr/bin/env python3
"""Adversarial synthetic regressions for public validation Bundle 002."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

if __name__ == "__main__" and (not sys.flags.isolated or not sys.flags.dont_write_bytecode):
    raise SystemExit("BUNDLE_002_FAIL: python -I -B required")

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing module: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load_module("bundle002_resolver", "route_closure.py")
independent = load_module("bundle002_independent", "independent_verifier.py")


def blob_oid(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(root: Path) -> dict:
    for node in "abcdefg":
        write(root, f"synthetic/nodes/{node}.txt", f"node-{node}\n")

    nodes = {
        "A": {"path": "synthetic/nodes/a.txt", "dependencies": ["B", "C"]},
        "B": {"path": "synthetic/nodes/b.txt", "dependencies": ["D", "E"]},
        "C": {"path": "synthetic/nodes/c.txt", "dependencies": ["F"]},
        "D": {"path": "synthetic/nodes/d.txt", "dependencies": []},
        "E": {"path": "synthetic/nodes/e.txt", "dependencies": ["G"]},
        "F": {"path": "synthetic/nodes/f.txt", "dependencies": []},
        "G": {"path": "synthetic/nodes/g.txt", "dependencies": []},
    }
    closure = ["D", "G", "E", "B", "F", "C", "A"]
    bindings = {
        row["path"]: blob_oid((root / row["path"]).read_bytes())
        for row in nodes.values()
    }
    probe = CONTRACT["fixed_identity_probe"]
    if bindings[probe["path"]] != probe["git_blob_sha1"]:
        raise AssertionError("fixed identity probe mismatch")
    return {
        "schema_version": 1,
        "status": "ACTIVE_SYNTHETIC_ROUTE",
        "entrypoints": ["A"],
        "nodes": nodes,
        "declared_closure": closure,
        "content_bindings": bindings,
        "soft_budget_bytes": 64,
    }


def both_pass(root: Path, spec: dict) -> tuple[dict, dict]:
    return resolver.resolve(root, spec), independent.verify(root, spec)


def both_fail(root: Path, spec: dict, label: str) -> None:
    for name, fn in [("resolver", resolver.resolve), ("independent", independent.verify)]:
        try:
            fn(root, spec)
        except Exception as exc:
            if exc.__class__.__name__ not in {"ClosureError", "IndependentError"}:
                raise
        else:
            raise AssertionError(f"false PASS: {label} via {name}")


def assert_independence() -> None:
    source = (ROOT / "independent_verifier.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "route_closure" for alias in node.names):
                raise AssertionError("independent verifier imports resolver")
        if isinstance(node, ast.ImportFrom) and node.module == "route_closure":
            raise AssertionError("independent verifier imports resolver")


def main() -> int:
    labels: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = fixture(root)
        primary, audit = both_pass(root, base)
        expected = ["D", "G", "E", "B", "F", "C", "A"]
        if primary["closure"] != expected or audit["closure"] != expected:
            raise AssertionError("deterministic closure mismatch")
        if primary["path_count"] != 7 or audit["path_count"] != 7:
            raise AssertionError("synthetic node count mismatch")
        assert_independence()

        over = copy.deepcopy(base)
        over["soft_budget_bytes"] = 10
        p_over, i_over = both_pass(root, over)
        for result in (p_over, i_over):
            if result["under_soft_budget"] is not False:
                raise AssertionError("budget overage not detected")
            if result["closure"] != expected or result["path_count"] != 7:
                raise AssertionError("soft budget dropped required closure")
            if result["budget_overage_drops_required_content"] is not False:
                raise AssertionError("budget overage authorized dropping content")

        def negative(label: str, mutator) -> None:
            spec = copy.deepcopy(base)
            cleanup = mutator(spec)
            try:
                both_fail(root, spec, label)
                labels.append(label)
            finally:
                if callable(cleanup):
                    cleanup()

        negative("wrong_schema_version", lambda s: s.__setitem__("schema_version", 2))
        negative("wrong_status", lambda s: s.__setitem__("status", "INACTIVE"))
        negative("empty_entrypoints", lambda s: s.__setitem__("entrypoints", []))
        negative("duplicate_entrypoint", lambda s: s.__setitem__("entrypoints", ["A", "A"]))
        negative("unknown_entrypoint", lambda s: s.__setitem__("entrypoints", ["UNKNOWN"]))
        negative("unknown_dependency", lambda s: s["nodes"]["B"].__setitem__("dependencies", ["D", "UNKNOWN"]))
        negative("dependency_cycle", lambda s: s["nodes"]["G"].__setitem__("dependencies", ["A"]))
        negative("duplicate_dependency", lambda s: s["nodes"]["B"].__setitem__("dependencies", ["D", "D"]))
        negative("missing_declared_closure_member", lambda s: s.__setitem__("declared_closure", s["declared_closure"][:-1]))
        negative("extra_declared_closure_member", lambda s: s.__setitem__("declared_closure", s["declared_closure"] + ["X"]))
        negative("declared_closure_order_drift", lambda s: s.__setitem__("declared_closure", ["G", "D", "E", "B", "F", "C", "A"]))
        negative("duplicate_declared_closure_member", lambda s: s.__setitem__("declared_closure", s["declared_closure"] + ["A"]))
        negative("missing_content_binding", lambda s: s["content_bindings"].pop("synthetic/nodes/g.txt"))
        negative("extra_content_binding", lambda s: s["content_bindings"].__setitem__("synthetic/extra.txt", "0" * 40))

        original_a = (root / "synthetic/nodes/a.txt").read_text(encoding="utf-8")
        def same_size_mutation(_s):
            (root / "synthetic/nodes/a.txt").write_text("node-z\n", encoding="utf-8")
            return lambda: (root / "synthetic/nodes/a.txt").write_text(original_a, encoding="utf-8")
        negative("same_size_content_mutation", same_size_mutation)

        negative("noncanonical_path_dot", lambda s: s["nodes"]["A"].__setitem__("path", "synthetic/./nodes/a.txt"))
        negative("parent_escape_path", lambda s: s["nodes"]["A"].__setitem__("path", "../outside.txt"))
        negative("absolute_path", lambda s: s["nodes"]["A"].__setitem__("path", "/tmp/a.txt"))

        def symlink_mutation(s):
            link = root / "synthetic/link"
            link.symlink_to("nodes")
            s["nodes"]["A"]["path"] = "synthetic/link/a.txt"
            s["content_bindings"]["synthetic/link/a.txt"] = s["content_bindings"].pop("synthetic/nodes/a.txt")
            return link.unlink
        negative("symlink_path_component", symlink_mutation)

        def duplicate_path(s):
            old = s["nodes"]["C"]["path"]
            s["nodes"]["C"]["path"] = s["nodes"]["B"]["path"]
            s["content_bindings"].pop(old)
        negative("duplicate_node_path", duplicate_path)
        negative("invalid_soft_budget_zero", lambda s: s.__setitem__("soft_budget_bytes", 0))

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        "status": "PUBLIC_VALIDATION_BUNDLE_002_PASS",
        "authority": CONTRACT["authority"],
        "synthetic_node_count": CONTRACT["synthetic_node_count"],
        "regression_count": len(labels),
        "independent_verifier": "PASS",
        "soft_budget_overage_no_drop": "PASS"
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
