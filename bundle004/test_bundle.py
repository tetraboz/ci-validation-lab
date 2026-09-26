#!/usr/bin/env python3
"""Synthetic CI workflow-contract drift regressions for Bundle 004."""
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
    raise SystemExit("BUNDLE_004_FAIL: strict isolated no-bytecode Python required")

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("bundle004_contract", ROOT / "workflow_contract.py")
if spec is None or spec.loader is None:
    raise RuntimeError("missing workflow_contract.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

BASE = """name: Synthetic Hardened Validation

on:
  pull_request:
    branches:
      - main
    types: [opened, synchronize, reopened, ready_for_review, edited]
  push:
    branches:
      - main
    paths:
      - "synthetic/**"
      - ".github/workflows/synthetic-validation.yml"

permissions:
  contents: read

jobs:
  synthetic-validation:
    name: synthetic-validation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
        with:
          fetch-depth: 0
          persist-credentials: false
          submodules: false
          lfs: false
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
        with:
          python-version: "3.12"
      - name: Install pinned validator dependency
        run: python -I -m pip --isolated install --disable-pip-version-check "PyYAML==6.0.3"
      - name: Validate synthetic contract
        run: python -I -B --check-hash-based-pycs always synthetic/validator.py
      - name: Run synthetic regressions
        run: python -I -B --check-hash-based-pycs always synthetic/regressions.py
"""


def mutate(old: str, new: str) -> str:
    changed = BASE.replace(old, new, 1)
    if changed == BASE:
        raise AssertionError(f"mutation anchor missing: {old!r}")
    return changed


def expect_fail(label: str, text: str) -> None:
    try:
        validator.validate_workflow_text(text)
    except validator.WorkflowContractError:
        return
    raise AssertionError(f"false PASS: {label}")


def main() -> int:
    positive = validator.validate_workflow_text(BASE)
    if positive["status"] != "GENERIC_WORKFLOW_CONTRACT_PASS":
        raise AssertionError("positive control failed")

    cases = {
        "top_level_extra_key": BASE + "\ntimeout-minutes: 10\n",
        "permissions_write_escalation": mutate("contents: read", "contents: write"),
        "pull_request_path_filter_added": mutate(
            "    types: [opened, synchronize, reopened, ready_for_review, edited]\n",
            "    types: [opened, synchronize, reopened, ready_for_review, edited]\n    paths:\n      - \"synthetic/**\"\n",
        ),
        "pull_request_event_suppression": mutate(
            "types: [opened, synchronize, reopened, ready_for_review, edited]",
            "types: [opened, synchronize, reopened, ready_for_review]",
        ),
        "pull_request_branch_drift": mutate(
            "  pull_request:\n    branches:\n      - main",
            "  pull_request:\n    branches:\n      - other",
        ),
        "push_branch_drift": mutate(
            "  push:\n    branches:\n      - main",
            "  push:\n    branches:\n      - release",
        ),
        "push_path_removed": mutate(
            '      - ".github/workflows/synthetic-validation.yml"\n',
            "",
        ),
        "extra_trigger_added": mutate(
            "  push:\n",
            "  workflow_dispatch:\n  push:\n",
        ),
        "job_id_drift": mutate(
            "  synthetic-validation:\n    name: synthetic-validation",
            "  validate:\n    name: synthetic-validation",
        ),
        "check_name_drift": mutate(
            "    name: synthetic-validation",
            "    name: spoofed-validation",
        ),
        "runner_drift": mutate("runs-on: ubuntu-latest", "runs-on: self-hosted"),
        "container_added": mutate(
            "    runs-on: ubuntu-latest",
            "    container: attacker/image:latest\n    runs-on: ubuntu-latest",
        ),
        "job_environment_added": mutate(
            "    runs-on: ubuntu-latest",
            "    env:\n      PATH: attacker\n    runs-on: ubuntu-latest",
        ),
        "checkout_mutable_tag": mutate(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "actions/checkout@v4",
        ),
        "checkout_local_action_substitution": mutate(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            "./.github/actions/checkout",
        ),
        "checkout_persist_credentials_enabled": mutate(
            "persist-credentials: false",
            "persist-credentials: true",
        ),
        "checkout_fetch_depth_drift": mutate("fetch-depth: 0", "fetch-depth: 1"),
        "checkout_submodules_enabled": mutate("submodules: false", "submodules: true"),
        "checkout_lfs_enabled": mutate("lfs: false", "lfs: true"),
        "setup_python_mutable_tag": mutate(
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/setup-python@v5",
        ),
        "setup_python_version_drift": mutate('python-version: "3.12"', 'python-version: "3.13"'),
        "install_python_isolation_removed": mutate(
            'python -I -m pip --isolated install --disable-pip-version-check "PyYAML==6.0.3"',
            'python -m pip --isolated install --disable-pip-version-check "PyYAML==6.0.3"',
        ),
        "install_pip_isolated_removed": mutate(
            'python -I -m pip --isolated install --disable-pip-version-check "PyYAML==6.0.3"',
            'python -I -m pip install --disable-pip-version-check "PyYAML==6.0.3"',
        ),
        "install_dependency_unpinned": mutate('"PyYAML==6.0.3"', '"PyYAML"'),
        "validator_isolation_removed": mutate(
            "python -I -B --check-hash-based-pycs always synthetic/validator.py",
            "python -B --check-hash-based-pycs always synthetic/validator.py",
        ),
        "validator_no_bytecode_removed": mutate(
            "python -I -B --check-hash-based-pycs always synthetic/validator.py",
            "python -I --check-hash-based-pycs always synthetic/validator.py",
        ),
        "validator_hash_check_removed": mutate(
            "python -I -B --check-hash-based-pycs always synthetic/validator.py",
            "python -I -B synthetic/validator.py",
        ),
        "required_step_removed": mutate(
            "      - name: Run synthetic regressions\n        run: python -I -B --check-hash-based-pycs always synthetic/regressions.py\n",
            "",
        ),
        "extra_execution_step": mutate(
            "      - name: Validate synthetic contract\n",
            "      - name: Unreviewed step\n        run: echo unreviewed\n      - name: Validate synthetic contract\n",
        ),
        "working_directory_override": mutate(
            "      - name: Validate synthetic contract\n        run:",
            "      - name: Validate synthetic contract\n        working-directory: attacker\n        run:",
        ),
        "shell_override": mutate(
            "      - name: Validate synthetic contract\n        run:",
            "      - name: Validate synthetic contract\n        shell: bash {0} || true\n        run:",
        ),
        "conditional_step_suppression": mutate(
            "      - name: Validate synthetic contract\n        run:",
            "      - name: Validate synthetic contract\n        if: false\n        run:",
        ),
        "continue_on_error_enabled": mutate(
            "      - name: Validate synthetic contract\n        run:",
            "      - name: Validate synthetic contract\n        continue-on-error: true\n        run:",
        ),
        "conditional_job_suppression": mutate(
            "  synthetic-validation:\n    name:",
            "  synthetic-validation:\n    if: false\n    name:",
        ),
        "validator_command_replaced": mutate(
            "python -I -B --check-hash-based-pycs always synthetic/validator.py",
            "python -I -B --check-hash-based-pycs always synthetic/other.py",
        ),
    }

    labels: list[str] = []
    for label, text in cases.items():
        expect_fail(label, text)
        labels.append(label)

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        "status": "PUBLIC_VALIDATION_BUNDLE_004_PASS",
        "authority": CONTRACT["authority"],
        "regression_count": len(labels),
        "permissions": positive["permissions"],
        "required_pr_event_count": positive["required_pr_event_count"],
        "action_pins": positive["action_pins"],
        "isolated_dependency_bootstrap": positive["isolated_dependency_bootstrap"],
        "strict_python_execution": positive["strict_python_execution"],
        "exact_step_order": positive["exact_step_order"]
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
