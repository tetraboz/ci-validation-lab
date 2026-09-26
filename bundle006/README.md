# Public Validation Bundle 006

This bundle is the aggregate drift auditor for public validation Bundles 001-005.

It pins every already-published artifact from those bundles and independently checks
their public contract identity, SUPPORTING_ONLY authority, adoption label, workflow
permissions, trigger shape, action pinning, checkout hardening, and strict test command.

## Boundary

This public meta-validator verifies the adopted **public snapshot**. It cannot inspect
the private source repository and therefore does not replace the private
source-to-public publication evidence. Its own result is SUPPORTING_ONLY.

## Coverage

- 5 adopted public bundles
- 26 pinned public artifacts
- exact Git blob SHA checks
- contract ID and authority checks
- public workflow hardening checks
- 32 adversarial meta-validation regressions

Expected terminal status:

`PUBLIC_VALIDATION_BUNDLE_006_PASS`
