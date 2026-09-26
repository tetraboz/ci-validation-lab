# Public Validation Bundle 003

This bundle tests generic parser, schema, selector, and Python syntax invariants using
only synthetic documents.

## Authority

Results are **SUPPORTING_ONLY**. They do not establish semantic equivalence, validate
private governance content, or authorize scientific/canonical state transitions.

## What it tests

- duplicate YAML keys fail closed, including nested mappings
- duplicate JSON keys fail closed
- malformed YAML and JSON fail closed
- required and unknown-field schema rules
- exact scalar types, including rejection of bool where integer is required
- enum and non-empty constraints
- homogeneous list item types
- exact dotted-selector resolution
- Python source compilation
- strict isolated/no-bytecode execution

The suite contains 18 adversarial negative regression classes. PyYAML is pinned to
6.0.3 in the public workflow.

Run:

`python -I -B --check-hash-based-pycs always bundle003/test_bundle.py`

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_003_PASS`
