#!/usr/bin/env python3
"""Aggregate public-suite meta-validation regressions for Bundle 006."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile


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
    raise SystemExit("BUNDLE_006_FAIL: strict isolated no-bytecode Python required")

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((BUNDLE_ROOT / "contract.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((BUNDLE_ROOT / "suite_registry.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("bundle006_meta", BUNDLE_ROOT / "meta_validate.py")
if spec is None or spec.loader is None:
    raise RuntimeError("missing meta_validate.py")
meta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meta)


def expect_fail(label: str, root: Path, registry: dict) -> None:
    try:
        meta.validate_suite(root, registry)
    except meta.MetaValidationError:
        return
    raise AssertionError(f"false PASS: {label}")


def mutate_file(root: Path, rel: str, old: str, new: str) -> None:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    changed = text.replace(old, new, 1)
    if changed == text:
        raise AssertionError(f"mutation anchor missing: {rel}: {old!r}")
    p.write_text(changed, encoding="utf-8")


def copied_suite() -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    dst = Path(tmp.name)
    for bundle in REGISTRY["bundles"]:
        for rel in bundle["artifacts"]:
            source = ROOT / rel
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return tmp


def main() -> int:
    positive = meta.validate_suite(ROOT, REGISTRY)
    if positive["audited_bundle_count"] != 5 or positive["audited_artifact_count"] != 26:
        raise AssertionError("positive aggregate counts mismatch")

    labels: list[str] = []

    def registry_case(label: str, mutator) -> None:
        reg = copy.deepcopy(REGISTRY)
        mutator(reg)
        expect_fail(label, ROOT, reg)
        labels.append(label)

    registry_case("suite_id_drift", lambda r: r.__setitem__("id", "OTHER_SUITE"))
    registry_case("suite_authority_drift", lambda r: r.__setitem__("authority", "AUTHORITATIVE"))
    registry_case("bundle_removed", lambda r: (r["bundles"].pop(), r["bundle_order"].pop()))
    registry_case("bundle_added", lambda r: (r["bundles"].append(copy.deepcopy(r["bundles"][-1])), r["bundles"][-1].__setitem__("id", "PUBLIC_VALIDATION_BUNDLE_006"), r["bundle_order"].append("PUBLIC_VALIDATION_BUNDLE_006")))
    registry_case("bundle_order_drift", lambda r: r["bundle_order"].__setitem__(slice(0, 2), list(reversed(r["bundle_order"][:2]))))
    registry_case("duplicate_bundle_id", lambda r: r["bundles"][1].__setitem__("id", r["bundles"][0]["id"]))
    registry_case("bundle_status_drift", lambda r: r["bundles"][0].__setitem__("status", "PENDING"))
    registry_case("bundle_authority_drift", lambda r: r["bundles"][0].__setitem__("authority", "AUTHORITATIVE"))
    registry_case("duplicate_artifact_target", lambda r: r["bundles"][1]["artifacts"].__setitem__("README.md", r["bundles"][0]["artifacts"]["README.md"]))
    registry_case("artifact_missing", lambda r: r["bundles"][0]["artifacts"].__setitem__("missing.txt", "0" * 40))
    registry_case("artifact_sha_drift", lambda r: r["bundles"][0]["artifacts"].__setitem__("bundle001/contract.json", "0" * 40))
    registry_case("artifact_path_escape", lambda r: r["bundles"][0]["artifacts"].__setitem__("../escape.txt", "0" * 40))
    registry_case("contract_id_mismatch", lambda r: r["bundles"][0].__setitem__("id", "PUBLIC_VALIDATION_BUNDLE_009"))
    registry_case("contract_authority_mismatch", lambda r: r["bundles"][0].__setitem__("authority", "OTHER"))

    with copied_suite() as tmp:
        root = Path(tmp)
        victim = root / "bundle001/contract.json"
        victim.unlink()
        victim.symlink_to(root / "bundle002/contract.json")
        expect_fail("artifact_symlink_substitution", root, REGISTRY)
        labels.append("artifact_symlink_substitution")

    workflow_cases = [
        ("workflow_permissions_escalation", "permissions:\n  contents: read", "permissions:\n  contents: write"),
        ("workflow_extra_permission", "permissions:\n  contents: read", "permissions:\n  contents: read\n  actions: read"),
        ("workflow_pull_request_added", "on:\n  push:", "on:\n  pull_request:\n  push:"),
        ("workflow_dispatch_removed", "  workflow_dispatch:\n", ""),
        ("workflow_push_branch_drift", "      - main\n    paths:", "      - release\n    paths:"),
        ("workflow_push_path_drift", '      - "bundle001/**"', '      - "other/**"'),
        ("workflow_runner_drift", "runs-on: ubuntu-latest", "runs-on: self-hosted"),
        ("workflow_job_if_added", "    runs-on: ubuntu-latest", "    if: false\n    runs-on: ubuntu-latest"),
        ("workflow_job_env_added", "    runs-on: ubuntu-latest", "    env:\n      X: y\n    runs-on: ubuntu-latest"),
        ("workflow_action_mutable_tag", "actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "actions/checkout@v4"),
        ("workflow_local_action_substitution", "actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "./.github/actions/checkout"),
        ("workflow_checkout_credentials_enabled", "persist-credentials: false", "persist-credentials: true"),
        ("workflow_step_if_added", "      - name: Run Bundle 001\n        run:", "      - name: Run Bundle 001\n        if: false\n        run:"),
        ("workflow_continue_on_error_added", "      - name: Run Bundle 001\n        run:", "      - name: Run Bundle 001\n        continue-on-error: true\n        run:"),
        ("workflow_shell_override", "      - name: Run Bundle 001\n        run:", "      - name: Run Bundle 001\n        shell: bash {0} || true\n        run:"),
        ("workflow_working_directory_override", "      - name: Run Bundle 001\n        run:", "      - name: Run Bundle 001\n        working-directory: other\n        run:"),
        ("workflow_test_command_drift", "bundle001/test_bundle.py", "bundle001/other.py"),
    ]
    for label, old, new in workflow_cases:
        with copied_suite() as tmp:
            root = Path(tmp)
            mutate_file(root, ".github/workflows/bundle001-trust-integrity.yml", old, new)
            reg = copy.deepcopy(REGISTRY)
            actual = meta.git_blob_sha1(root / ".github/workflows/bundle001-trust-integrity.yml")
            reg["bundles"][0]["artifacts"][".github/workflows/bundle001-trust-integrity.yml"] = actual
            expect_fail(label, root, reg)
            labels.append(label)

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        **positive,
        "regression_count": len(labels),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
