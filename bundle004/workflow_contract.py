#!/usr/bin/env python3
"""Strict generic GitHub Actions workflow contract validator."""
from __future__ import annotations

from typing import Any
import yaml


class WorkflowContractError(RuntimeError):
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
            raise WorkflowContractError(f"unhashable workflow key: {key!r}") from exc
        if duplicate:
            raise WorkflowContractError(f"duplicate workflow key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)

CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"
PR_TYPES = ["opened", "synchronize", "reopened", "ready_for_review", "edited"]
PUSH_PATHS = ["synthetic/**", ".github/workflows/synthetic-validation.yml"]
INSTALL = 'python -I -m pip --isolated install --disable-pip-version-check "PyYAML==6.0.3"'
STRICT_PREFIX = "python -I -B --check-hash-based-pycs always "

EXPECTED_STEPS = [
    {
        "uses": CHECKOUT,
        "with": {
            "fetch-depth": 0,
            "persist-credentials": False,
            "submodules": False,
            "lfs": False,
        },
    },
    {
        "uses": SETUP_PYTHON,
        "with": {"python-version": "3.12"},
    },
    {
        "name": "Install pinned validator dependency",
        "run": INSTALL,
    },
    {
        "name": "Validate synthetic contract",
        "run": STRICT_PREFIX + "synthetic/validator.py",
    },
    {
        "name": "Run synthetic regressions",
        "run": STRICT_PREFIX + "synthetic/regressions.py",
    },
]

EXPECTED_JOB = {
    "name": "synthetic-validation",
    "runs-on": "ubuntu-latest",
    "steps": EXPECTED_STEPS,
}


def load_workflow_text(text: str) -> dict[Any, Any]:
    try:
        doc = yaml.load(text, Loader=UniqueKeyLoader)
    except WorkflowContractError:
        raise
    except yaml.YAMLError as exc:
        raise WorkflowContractError(f"malformed workflow YAML: {exc}") from exc
    if type(doc) is not dict:
        raise WorkflowContractError("workflow document must be a mapping")
    return doc


def _trigger_key(doc: dict[Any, Any]) -> Any:
    keys = [key for key in ("on", True) if key in doc]
    if len(keys) != 1:
        raise WorkflowContractError("workflow must contain exactly one on trigger key")
    return keys[0]


def validate_workflow_text(text: str) -> dict[str, object]:
    doc = load_workflow_text(text)
    trigger_key = _trigger_key(doc)
    if set(doc) != {"name", "permissions", "jobs", trigger_key}:
        raise WorkflowContractError("top-level workflow structure changed")
    if doc.get("name") != "Synthetic Hardened Validation":
        raise WorkflowContractError("workflow name changed")
    if doc.get("permissions") != {"contents": "read"}:
        raise WorkflowContractError("workflow permissions changed")

    triggers = doc[trigger_key]
    if type(triggers) is not dict or set(triggers) != {"pull_request", "push"}:
        raise WorkflowContractError("workflow trigger set changed")
    if triggers.get("pull_request") != {
        "branches": ["main"],
        "types": PR_TYPES,
    }:
        raise WorkflowContractError("pull_request coverage changed")
    if triggers.get("push") != {
        "branches": ["main"],
        "paths": PUSH_PATHS,
    }:
        raise WorkflowContractError("push coverage changed")

    jobs = doc.get("jobs")
    if type(jobs) is not dict or set(jobs) != {"synthetic-validation"}:
        raise WorkflowContractError("job identity changed")
    if jobs["synthetic-validation"] != EXPECTED_JOB:
        raise WorkflowContractError("hardened execution contract changed")

    return {
        "status": "GENERIC_WORKFLOW_CONTRACT_PASS",
        "permissions": "CONTENTS_READ_ONLY",
        "pull_request_unfiltered_by_path": True,
        "required_pr_event_count": len(PR_TYPES),
        "push_path_count": len(PUSH_PATHS),
        "job_id": "synthetic-validation",
        "runner": "ubuntu-latest",
        "action_pins": "FULL_COMMIT_SHA",
        "isolated_dependency_bootstrap": True,
        "strict_python_execution": True,
        "exact_step_order": True,
    }
