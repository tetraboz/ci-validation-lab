#!/usr/bin/env python3
"""Generic trust/integrity guard for synthetic public validation."""
from __future__ import annotations

from pathlib import Path
import subprocess

WORKFLOW_PREFIX = b".github/workflows/"
FORBIDDEN_BASENAMES = {b"pip.py", b"sitecustomize.py", b"usercustomize.py"}


class GuardError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise GuardError(f"git failed: {completed.stderr[:300]!r}")
    return completed.stdout


def tree(repo: Path) -> dict[bytes, tuple[str, str, str]]:
    entries: dict[bytes, tuple[str, str, str]] = {}
    for record in git(repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        entries[path] = (mode, kind, oid)
    return entries


def workflow_vector(entries: dict[bytes, tuple[str, str, str]]) -> dict[bytes, tuple[str, str, str]]:
    return {p: v for p, v in entries.items() if p.startswith(WORKFLOW_PREFIX)}


def reject_bootstrap_and_bytecode(entries: dict[bytes, tuple[str, str, str]]) -> None:
    for path in entries:
        parts = path.split(b"/")
        if path.endswith((b".pyc", b".pyo")) or b"__pycache__" in parts:
            raise GuardError(f"bytecode/cache path rejected: {path!r}")
        if parts[-1] in FORBIDDEN_BASENAMES:
            raise GuardError(f"bootstrap shadow rejected: {path!r}")
        if parts and parts[0] == b"pip":
            raise GuardError(f"pip namespace shadow rejected: {path!r}")
        if len(parts) >= 2 and parts[-2:] == [b"pip", b"__main__.py"]:
            raise GuardError(f"pip package shadow rejected: {path!r}")


def verify(
    base_repo: Path,
    candidate_repo: Path,
    protected_paths: tuple[bytes, ...],
    expected_oids: dict[bytes, str],
) -> dict[str, object]:
    base = tree(base_repo)
    candidate = tree(candidate_repo)

    if set(expected_oids) != set(protected_paths):
        raise GuardError("expected oid vector does not match protected paths")

    for path in protected_paths:
        expected = ("100644", "blob", expected_oids[path])
        if base.get(path) != expected:
            raise GuardError(f"trusted base identity mismatch: {path!r}")
        if candidate.get(path) != expected:
            raise GuardError(f"protected candidate identity mismatch: {path!r}")

    if workflow_vector(candidate) != workflow_vector(base):
        raise GuardError("workflow namespace changed")

    reject_bootstrap_and_bytecode(candidate)
    return {
        "status": "GENERIC_TRUST_INTEGRITY_PASS",
        "protected_path_count": len(protected_paths),
        "candidate_execution": "NONE",
    }
