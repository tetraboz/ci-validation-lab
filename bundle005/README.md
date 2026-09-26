# Public Validation Bundle 005

This bundle provides a generic synthetic harness for exact representation-equivalence
checks. It deliberately does **not** contain private semantic rules, private
certificates, private representation axioms, or real component content.

## Authority

Results are **SUPPORTING_ONLY**. Passing synthetic exactness checks does not establish
semantic equivalence for any private component and cannot authorize compression,
replacement, or canonical/scientific state transitions.

## What it tests

- type-exact recursive structural equality
- mapping equality independent of mapping key order
- ordered-list identity
- explicitly declared ordered-subsequence selection
- explicitly declared mapping exclusions
- binding source/target paths to registered synthetic family versions
- exact semantic-subject path identity
- mandatory machine-check evidence marker
- unresolved structural differences remain UNRESOLVED
- uncertified or uncovered members remain in an explicit delta
- whole-equivalence claims fail while unresolved content exists

The suite contains 28 adversarial negative regression classes.

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_005_PASS`
