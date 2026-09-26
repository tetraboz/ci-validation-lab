#!/usr/bin/env python3
"""Aggregate public-suite drift validator for already-public synthetic bundles."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

import yaml


class MetaValidationError(RuntimeError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _yaml_mapping(loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    out: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in out
        except TypeError as exc:
            raise MetaValidationError(f"unhashable YAML key: {key!r}") from exc
        if duplicate:
            raise MetaValidationError(f"duplicate YAML key: {key!r}")
        out[key] = loader.construct_object(value_node, deep=deep)
    return out


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MetaValidationError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_json_pairs)
    except MetaValidationError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise MetaValidationError(f"cannot load JSON {path}: {exc}") from exc


def load_yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except MetaValidationError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise MetaValidationError(f"cannot load YAML {path}: {exc}") from exc


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()


def exact_regular_file(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise MetaValidationError(f"invalid artifact path: {raw!r}")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise MetaValidationError(f"noncanonical artifact path: {raw}")
    rel = Path(*parts)
    if rel.is_absolute() or rel.as_posix() != raw:
        raise MetaValidationError(f"noncanonical artifact path: {raw}")
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise MetaValidationError(f"symlink artifact path component: {raw}")
    if not cur.exists():
        raise MetaValidationError(f"missing artifact: {raw}")
    st = os.lstat(cur)
    if not stat.S_ISREG(st.st_mode):
        raise MetaValidationError(f"artifact is not regular file: {raw}")
    try:
        cur.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise MetaValidationError(f"artifact escapes suite root: {raw}") from exc
    return cur


def _trigger_map(doc: dict[Any, Any]) -> dict[Any, Any]:
    candidates = [key for key in ("on", True) if key in doc]
    if len(candidates) != 1:
        raise MetaValidationError("workflow must have exactly one trigger key")
    value = doc[candidates[0]]
    if type(value) is not dict:
        raise MetaValidationError("workflow trigger map malformed")
    return value


FULL_ACTION_SHA = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"


def validate_workflow(path: Path, bundle: dict[str, Any]) -> None:
    doc = load_yaml(path)
    if type(doc) is not dict:
        raise MetaValidationError("workflow must be mapping")
    if doc.get("permissions") != {"contents": "read"}:
        raise MetaValidationError("workflow permissions are not contents:read")

    triggers = _trigger_map(doc)
    if set(triggers) != {"push", "workflow_dispatch"}:
        raise MetaValidationError("workflow trigger set drift")
    if triggers.get("workflow_dispatch") is not None:
        raise MetaValidationError("workflow_dispatch must be empty")
    push = triggers.get("push")
    if type(push) is not dict:
        raise MetaValidationError("push trigger malformed")
    if push.get("branches") != ["main"]:
        raise MetaValidationError("push branch drift")
    if push.get("paths") != bundle["workflow_push_paths"]:
        raise MetaValidationError("push path drift")

    jobs = doc.get("jobs")
    if type(jobs) is not dict or len(jobs) != 1:
        raise MetaValidationError("workflow must contain exactly one job")
    job = next(iter(jobs.values()))
    if type(job) is not dict or job.get("runs-on") != "ubuntu-latest":
        raise MetaValidationError("runner drift")
    for forbidden in ("if", "env", "container", "continue-on-error", "permissions", "defaults"):
        if forbidden in job:
            raise MetaValidationError(f"forbidden job key: {forbidden}")

    steps = job.get("steps")
    if type(steps) is not list or not steps:
        raise MetaValidationError("workflow steps malformed")
    test_commands: list[str] = []
    checkout_seen = False
    for step in steps:
        if type(step) is not dict:
            raise MetaValidationError("workflow step malformed")
        for forbidden in ("if", "continue-on-error", "shell", "working-directory"):
            if forbidden in step:
                raise MetaValidationError(f"forbidden step key: {forbidden}")
        if "uses" in step:
            uses = step["uses"]
            if not isinstance(uses, str) or not FULL_ACTION_SHA.fullmatch(uses):
                raise MetaValidationError(f"action is not full-SHA pinned: {uses!r}")
            if uses == CHECKOUT:
                checkout_seen = True
                if step.get("with") != {
                    "persist-credentials": False,
                    "submodules": False,
                    "lfs": False,
                }:
                    raise MetaValidationError("checkout hardening drift")
            elif uses == SETUP_PYTHON:
                if step.get("with") != {"python-version": "3.12"}:
                    raise MetaValidationError("setup-python contract drift")
        if "run" in step:
            run = step["run"]
            if not isinstance(run, str):
                raise MetaValidationError("run command must be string")
            if "test_bundle.py" in run:
                test_commands.append(run)

    if not checkout_seen:
        raise MetaValidationError("pinned checkout action missing")
    if test_commands != [bundle["test_command"]]:
        raise MetaValidationError("bundle test command drift")


def validate_suite(root: Path, registry: dict[str, Any]) -> dict[str, object]:
    if registry.get("id") != "PUBLIC_VALIDATION_SUITE":
        raise MetaValidationError("suite id drift")
    if registry.get("version") != 1:
        raise MetaValidationError("suite version drift")
    if registry.get("authority") != "SUPPORTING_ONLY":
        raise MetaValidationError("suite authority drift")

    bundles = registry.get("bundles")
    order = registry.get("bundle_order")
    if type(bundles) is not list or type(order) is not list:
        raise MetaValidationError("suite bundles/order malformed")
    ids = [b.get("id") if isinstance(b, dict) else None for b in bundles]
    if len(ids) != len(set(ids)):
        raise MetaValidationError("duplicate bundle id")
    if ids != order:
        raise MetaValidationError("bundle order or membership drift")
    if ids != [f"PUBLIC_VALIDATION_BUNDLE_{i:03d}" for i in range(1, 6)]:
        raise MetaValidationError("audited bundle membership drift")

    global_targets: set[str] = set()
    artifact_count = 0
    for bundle in bundles:
        if type(bundle) is not dict:
            raise MetaValidationError("bundle record malformed")
        if bundle.get("status") != "ADOPTED_PUBLIC_SUPPORTING":
            raise MetaValidationError("bundle adoption state drift")
        if bundle.get("authority") != "SUPPORTING_ONLY":
            raise MetaValidationError("bundle authority drift")
        artifacts = bundle.get("artifacts")
        if type(artifacts) is not dict or not artifacts:
            raise MetaValidationError("bundle artifact table malformed")

        for target, expected_sha in artifacts.items():
            if target in global_targets:
                raise MetaValidationError(f"duplicate artifact target: {target}")
            global_targets.add(target)
            if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
                raise MetaValidationError(f"invalid artifact SHA: {target}")
            actual = git_blob_sha1(exact_regular_file(root, target))
            if actual != expected_sha:
                raise MetaValidationError(f"artifact SHA drift: {target}")
            artifact_count += 1

        contract_path = exact_regular_file(root, bundle.get("contract"))
        contract = load_json(contract_path)
        if type(contract) is not dict or contract.get("id") != bundle["id"]:
            raise MetaValidationError("contract id mismatch")
        if contract.get("authority") != bundle["authority"]:
            raise MetaValidationError("contract authority mismatch")

        workflow_path = exact_regular_file(root, bundle.get("workflow"))
        validate_workflow(workflow_path, bundle)

    return {
        "status": "PUBLIC_VALIDATION_BUNDLE_006_PASS",
        "authority": "SUPPORTING_ONLY",
        "audited_bundle_count": len(bundles),
        "audited_artifact_count": artifact_count,
        "adoption_states": "ALL_ADOPTED_PUBLIC_SUPPORTING",
        "artifact_sha_pins": "PASS",
        "contract_authority": "PASS",
        "workflow_hardening": "PASS",
    }
