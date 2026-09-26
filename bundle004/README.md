# Public Validation Bundle 004

This bundle tests a generic hardened GitHub Actions workflow contract against
configuration drift using only a synthetic workflow document.

## Authority

Results are **SUPPORTING_ONLY**. They do not validate private workflow contents,
private repository composition, research state, or scientific/canonical transitions.

## What it tests

- exact trigger coverage and no pull-request path suppression
- read-only workflow permissions
- stable job/check identity and runner
- no container or job-level environment injection
- full-commit-SHA action pinning
- hardened checkout options
- pinned Python runtime and parser dependency
- isolated pip bootstrap
- strict Python `-I -B --check-hash-based-pycs always`
- exact required step set and order
- rejection of extra execution steps
- rejection of `working-directory`, `shell`, `if`, and `continue-on-error` drift

The suite contains 35 adversarial negative regression classes. PyYAML is pinned to
6.0.3 in the public workflow.

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_004_PASS`
