# Public Validation Bundle 001

This bundle contains only generic, synthetic CI trust/integrity regressions.

## Authority

Results are **SUPPORTING_ONLY**. A PASS here does not authorize scientific-state
transitions, canonical private-state updates, or final private integration acceptance.

## What it tests

- 55 deterministic synthetic protected paths
- exact Git blob identity rather than file size or filename alone
- protected-file mutation, deletion, mode and path-type substitution
- workflow namespace mutation
- Python bootstrap-shadow paths
- bytecode / __pycache__ injection
- candidate-as-data behavior: candidate source is not executed by the guard

## Prohibited inputs

Do not copy or fetch:

- a private repository checkout
- private research state
- real or restricted market data
- secrets
- unpublished prompt-governance content
- private acceptance thresholds

## Public repository layout

Copy these files to `tetraboz/ci-validation-lab`:

- `contract.json` -> `bundle001/contract.json`
- `trust_integrity_guard.py` -> `bundle001/trust_integrity_guard.py`
- `test_bundle.py` -> `bundle001/test_bundle.py`
- `bundle001-trust-integrity.yml` -> `.github/workflows/bundle001-trust-integrity.yml`

Run:

`python3 -I -B --check-hash-based-pycs always bundle001/test_bundle.py`

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_001_PASS`

Private authoritative validation remains separate.
