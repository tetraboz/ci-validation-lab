#!/usr/bin/env python3
"""Synthetic exact-equivalence and explicit-delta regressions for Bundle 005."""
from __future__ import annotations

import copy
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
    raise SystemExit("BUNDLE_005_FAIL: strict isolated no-bytecode Python required")

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("bundle005_harness", ROOT / "equivalence_harness.py")
if spec is None or spec.loader is None:
    raise RuntimeError("missing equivalence_harness.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

REGISTRY = {
    "resolution": {"root": "synthetic/components"},
    "components": {
        "SYNTHETIC_PROFILE@1": {"path": "profile_v1.yaml"},
        "SYNTHETIC_PROFILE@2": {"path": "profile_v2.yaml"},
    },
}

SOURCE = {
    "source_payload": {
        "rules": {
            "mode": "strict",
            "threshold": 2,
            "enabled": True,
            "ordered": ["alpha", "beta", "gamma", "delta"],
            "nested": {"keep": "yes", "remove": "legacy"},
        }
    }
}

TARGET = {
    "target_delta": {
        "rules": {
            "mode": "strict",
            "threshold": 2,
            "enabled": True,
            "ordered": ["alpha", "beta", "gamma", "delta"],
            "nested": {"keep": "yes", "remove": "legacy"},
        }
    }
}

CERT = {
    "source": {
        "file": "synthetic/components/profile_v1.yaml",
        "path": "source_payload.rules",
    },
    "target": {
        "file": "synthetic/components/profile_v2.yaml",
        "path": "target_delta.rules",
    },
    "valid_under": {
        "component_family": "SYNTHETIC_PROFILE",
        "source_version": 1,
        "target_version": 2,
    },
    "evidence": {"machine_check": True},
}


def expect_error(label: str, fn) -> None:
    try:
        fn()
    except h.EquivalenceError:
        return
    raise AssertionError(f"false PASS: {label}")


def expect_unresolved(label: str, source, target, cert=CERT) -> None:
    result = h.certify_exact(source, target, cert, REGISTRY)
    if result.get("state") != "UNRESOLVED":
        raise AssertionError(f"false exact certification: {label}: {result!r}")


def main() -> int:
    labels: list[str] = []

    positive = h.certify_exact(SOURCE, TARGET, CERT, REGISTRY)
    if positive["state"] != "CERTIFIED_EXACT":
        raise AssertionError("positive exact structural identity did not certify")

    reordered_mapping_target = copy.deepcopy(TARGET)
    rules = reordered_mapping_target["target_delta"]["rules"]
    reordered_mapping_target["target_delta"]["rules"] = {
        "nested": rules["nested"],
        "ordered": rules["ordered"],
        "enabled": rules["enabled"],
        "threshold": rules["threshold"],
        "mode": rules["mode"],
    }
    if h.certify_exact(SOURCE, reordered_mapping_target, CERT, REGISTRY)["state"] != "CERTIFIED_EXACT":
        raise AssertionError("mapping key order incorrectly treated as semantic")

    source_sub = {"source_payload": {"rules": SOURCE["source_payload"]["rules"]["ordered"]}}
    target_sub = {"target_delta": {"rules": ["alpha", "gamma"]}}
    sub_cert = copy.deepcopy(CERT)
    sub_cert["source"]["path"] = "source_payload.rules[items=alpha,gamma]"
    sub_cert["target"]["path"] = "target_delta.rules"
    if h.certify_exact(source_sub, target_sub, sub_cert, REGISTRY)["state"] != "CERTIFIED_EXACT":
        raise AssertionError("declared ordered subsequence positive control failed")

    source_exc = copy.deepcopy(SOURCE)
    target_exc = {"target_delta": {"rules": {
        "mode": "strict",
        "threshold": 2,
        "enabled": True,
        "ordered": ["alpha", "beta", "gamma", "delta"],
        "nested": {"keep": "yes"},
    }}}
    exc_cert = copy.deepcopy(CERT)
    exc_cert["source"]["path"] = "source_payload.rules[excluding=nested.remove]"
    if h.certify_exact(source_exc, target_exc, exc_cert, REGISTRY)["state"] != "CERTIFIED_EXACT":
        raise AssertionError("declared exclusion positive control failed")

    coverage = h.validate_explicit_delta(
        source_members=["a", "b", "c", "d"],
        certified_exact=["a", "b"],
        unresolved=["c"],
        uncovered=["d"],
        explicit_delta=["c", "d"],
        whole_equivalence_claimed=False,
    )
    if coverage["status"] != "GENERIC_EXPLICIT_DELTA_COVERAGE_PASS":
        raise AssertionError("positive explicit-delta coverage failed")

    def unresolved(label: str, mutator) -> None:
        s = copy.deepcopy(SOURCE)
        t = copy.deepcopy(TARGET)
        mutator(s, t)
        expect_unresolved(label, s, t)
        labels.append(label)

    unresolved("scalar_value_mismatch", lambda s, t: t["target_delta"]["rules"].__setitem__("mode", "relaxed"))
    unresolved("integer_boolean_type_mismatch", lambda s, t: t["target_delta"]["rules"].__setitem__("threshold", True))
    unresolved("integer_float_type_mismatch", lambda s, t: t["target_delta"]["rules"].__setitem__("threshold", 2.0))
    unresolved("ordered_list_reordering", lambda s, t: t["target_delta"]["rules"].__setitem__("ordered", ["beta", "alpha", "gamma", "delta"]))
    unresolved("ordered_list_member_removed", lambda s, t: t["target_delta"]["rules"].__setitem__("ordered", ["alpha", "beta", "gamma"]))
    unresolved("mapping_member_removed", lambda s, t: t["target_delta"]["rules"].pop("enabled"))
    unresolved("mapping_member_added", lambda s, t: t["target_delta"]["rules"].__setitem__("extra", "x"))

    def key_type_drift(s, t):
        t["target_delta"]["rules"]["nested"] = {1: "yes", "remove": "legacy"}
        s["source_payload"]["rules"]["nested"] = {"1": "yes", "remove": "legacy"}
    unresolved("mapping_key_type_mismatch", key_type_drift)

    def error_case(label: str, fn) -> None:
        expect_error(label, fn)
        labels.append(label)

    bad = copy.deepcopy(CERT)
    bad["source"]["path"] = "source_payload.missing"
    error_case("source_selector_unresolved", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["target"]["path"] = "target_delta.missing"
    error_case("target_selector_unresolved", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    error_case(
        "item_selector_missing",
        lambda: h.select_value({"x": ["a", "b"]}, "x[item=z]"),
    )
    error_case(
        "ordered_subsequence_member_missing",
        lambda: h.select_value({"x": ["a", "b"]}, "x[items=a,z]"),
    )
    error_case(
        "ordered_subsequence_reordered",
        lambda: h.select_value({"x": ["a", "b", "c"]}, "x[items=c,a]"),
    )
    error_case(
        "exclusion_source_not_mapping",
        lambda: h.select_value({"x": ["a"]}, "x[excluding=a]"),
    )
    error_case(
        "exclusion_path_missing",
        lambda: h.select_value({"x": {"a": 1}}, "x[excluding=missing]"),
    )

    bad = copy.deepcopy(CERT)
    bad["source"]["file"] = "synthetic/components/wrong.yaml"
    error_case("certificate_source_file_mismatch", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["target"]["file"] = "synthetic/components/wrong.yaml"
    error_case("certificate_target_file_mismatch", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["valid_under"].pop("component_family")
    error_case("certificate_family_missing", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["valid_under"].pop("source_version")
    error_case("certificate_source_version_missing", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["valid_under"].pop("target_version")
    error_case("certificate_target_version_missing", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["target"]["path"] = "target_delta.other"
    error_case("certificate_subject_path_mismatch", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    bad = copy.deepcopy(CERT)
    bad["evidence"] = {}
    error_case("certificate_machine_check_missing", lambda: h.certify_exact(SOURCE, TARGET, bad, REGISTRY))

    base_cov = {
        "source_members": ["a", "b", "c", "d"],
        "certified_exact": ["a", "b"],
        "unresolved": ["c"],
        "uncovered": ["d"],
        "explicit_delta": ["c", "d"],
        "whole_equivalence_claimed": False,
    }

    def coverage_error(label: str, mutate) -> None:
        args = copy.deepcopy(base_cov)
        mutate(args)
        error_case(label, lambda: h.validate_explicit_delta(**args))

    coverage_error("coverage_uncovered_not_retained", lambda a: a.__setitem__("explicit_delta", ["c"]))
    coverage_error("coverage_unresolved_not_retained", lambda a: a.__setitem__("explicit_delta", ["d"]))
    coverage_error("coverage_unknown_delta_member", lambda a: a.__setitem__("explicit_delta", ["c", "d", "x"]))
    coverage_error("coverage_duplicate_delta_member", lambda a: a.__setitem__("explicit_delta", ["c", "d", "d"]))
    coverage_error("coverage_certified_member_left_in_delta", lambda a: a.__setitem__("explicit_delta", ["a", "c", "d"]))
    coverage_error("whole_equivalence_claim_with_unresolved_member", lambda a: a.__setitem__("whole_equivalence_claimed", True))

    required = set(CONTRACT["regression_classes"])
    if set(labels) != required:
        raise AssertionError(
            f"regression mismatch missing={sorted(required-set(labels))} extra={sorted(set(labels)-required)}"
        )

    print(json.dumps({
        "status": "PUBLIC_VALIDATION_BUNDLE_005_PASS",
        "authority": CONTRACT["authority"],
        "regression_count": len(labels),
        "exact_structural_identity": "PASS",
        "ordered_subsequence": "PASS",
        "declared_exclusion": "PASS",
        "subject_binding": "PASS",
        "explicit_delta_preservation": "PASS",
        "unresolved_never_promotes": "PASS"
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
