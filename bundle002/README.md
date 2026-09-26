# Public Validation Bundle 002

This bundle tests generic deterministic route/dependency closure behavior using only
synthetic files and a synthetic dependency graph.

## Authority

Results are **SUPPORTING_ONLY**. They do not authorize private project composition,
research-state changes, scientific transitions, or final integration acceptance.

## What it tests

- deterministic dependency-first closure
- unknown dependency and cycle fail-closed behavior
- exact declared-closure equality and order
- exact canonical relative paths
- symlink-path rejection
- exact Git blob content bindings
- duplicate path and binding rejection
- soft budget overage without dropping required closure members
- agreement with a separately implemented independent verifier

The synthetic graph has 7 nodes and 21 adversarial negative regression classes.

## Prohibited inputs

Do not copy or fetch private repository state, real project identifiers, research
state, market data, private blob pins, private acceptance thresholds, or unpublished
governance semantics.

Run:

`python3 -I -B --check-hash-based-pycs always bundle002/test_bundle.py`

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_002_PASS`
