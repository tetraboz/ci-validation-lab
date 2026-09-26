#!/usr/bin/env python3
"""Synthetic adversarial regression suite for public validation Bundle 001."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

def strict_hash_mode_requested() -> bool:
    argv = getattr(sys, "orig_argv", [])
    for i, arg in enumerate(argv):
        if (
            arg == "--check-hash-based-pycs"
            and i + 1 < len(argv)
            and argv[i + 1] == "always"
        ):
            return True
        if arg == "--check-hash-based-pycs=always":
            return True
    return False


if __name__ == "__main__" and (
    not sys.flags.isolated
    or not sys.flags.dont_write_bytecode
    or not strict_hash_mode_requested()
):
    raise SystemExit("BUNDLE_001_FAIL: strict isolated Python required")

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("public_guard", ROOT / "trust_integrity_guard.py")
if spec is None or spec.loader is None:
    raise RuntimeError("missing guard")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def write(repo: Path, rel: str, data: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def commit(repo: Path) -> str:
    git(repo, "add", "-A")
    git(
        repo,
        "-c", "user.name=Public validation fixture",
        "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "fixture",
    )
    return git(repo, "rev-parse", "HEAD")


def reset(repo: Path, head: str) -> None:
    git(repo, "reset", "--hard", head)
    git(repo, "clean", "-fdq")


def blob_oid(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def protected_paths() -> tuple[bytes, ...]:
    return tuple(
        f"synthetic/protected/{i:03d}.txt".encode("ascii")
        for i in range(int(CONTRACT["synthetic_protected_path_count"]))
    )


def build_base(root: Path):
    repo = root / "base"
    repo.mkdir()
    paths = protected_paths()
    expected: dict[bytes, str] = {}

    for i, raw in enumerate(paths):
        content = f"fixture-{i:03d}\n"
        write(repo, raw.decode("ascii"), content)
        expected[raw] = blob_oid(content.encode("utf-8"))

    write(
        repo,
        ".github/workflows/synthetic.yml",
        "name: synthetic\non: workflow_dispatch\npermissions:\n  contents: read\n",
    )
    git(repo, "init", "-q")
    head = commit(repo)

    probe = CONTRACT["fixed_identity_probe"]
    if expected[probe["path"].encode("ascii")] != probe["git_blob_sha1"]:
        raise AssertionError("fixed Git blob identity mismatch")

    return repo, head, paths, expected


def clone(root: Path, base: Path):
    candidate = root / "candidate"
    git(root, "clone", "-q", str(base), str(candidate))
    return candidate, git(candidate, "rev-parse", "HEAD")


def expect_fail(base, candidate, paths, expected, label: str) -> None:
    try:
        guard.verify(base, candidate, paths, expected)
    except guard.GuardError:
        return
    raise AssertionError(f"false PASS: {label}")


def main() -> int:
    labels: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base, _, paths, expected = build_base(root)
        candidate, clean = clone(root, base)

        guard.verify(base, candidate, paths, expected)

        sentinel = root / "candidate-executed.txt"
        write(candidate, "unprotected_candidate.py", f"open({str(sentinel)!r}, 'w').write('x')\n")
        commit(candidate)
        guard.verify(base, candidate, paths, expected)
        if sentinel.exists():
            raise AssertionError("candidate source executed")
        reset(candidate, clean)

        p0 = paths[0].decode("ascii")

        def mutate(label: str, fn) -> None:
            fn()
            commit(candidate)
            expect_fail(base, candidate, paths, expected, label)
            labels.append(label)
            reset(candidate, clean)

        mutate("protected_content_mutation", lambda: write(candidate, p0, "changed\n"))
        mutate("protected_same_size_mutation", lambda: write(candidate, p0, "fixture-999\n"))
        mutate("protected_deletion", lambda: (candidate / p0).unlink())

        def make_symlink():
            path = candidate / p0
            path.unlink()
            path.symlink_to("../protected/001.txt")
        mutate("protected_symlink_substitution", make_symlink)

        mutate("workflow_addition", lambda: write(candidate, ".github/workflows/extra.yml", "name: extra\n"))
        mutate("workflow_mutation", lambda: write(candidate, ".github/workflows/synthetic.yml", "name: changed\n"))
        mutate("workflow_deletion", lambda: (candidate / ".github/workflows/synthetic.yml").unlink())
        mutate("unchecked_bytecode_addition", lambda: write(candidate, "module.pyc", "x\n"))
        mutate("optimized_bytecode_addition", lambda: write(candidate, "module.pyo", "x\n"))
        mutate("pycache_addition", lambda: write(candidate, "pkg/__pycache__/module.cpython-312.pyc", "x\n"))
        mutate("pip_shadow_module", lambda: write(candidate, "pip.py", "raise SystemExit\n"))
        mutate("pip_package_shadow", lambda: write(candidate, "pip/__main__.py", "raise SystemExit\n"))
        mutate("pip_namespace_shadow", lambda: write(candidate, "pip/arbitrary.py", "raise SystemExit\n"))
        mutate("sitecustomize_shadow", lambda: write(candidate, "sitecustomize.py", "raise SystemExit\n"))
        mutate("usercustomize_shadow", lambda: write(candidate, "usercustomize.py", "raise SystemExit\n"))

        def mode_change():
            (candidate / p0).chmod(0o755)
        mutate("protected_mode_change", mode_change)

        def type_change():
            path = candidate / p0
            path.unlink()
            path.mkdir()
            write(candidate, f"{p0}/nested.txt", "x\n")
        mutate("protected_path_type_change", type_change)

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        "status": "PUBLIC_VALIDATION_BUNDLE_001_PASS",
        "authority": CONTRACT["authority"],
        "synthetic_protected_path_count": CONTRACT["synthetic_protected_path_count"],
        "regression_count": len(labels),
        "candidate_execution": "NONE",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
