# Clean-checkout manifest verification (read-only)

## Commands (do not invert)

```bash
# 1) Generate (writes reports then hashes; excludes manifest from inventory)
python scripts/final_evidence/executable_validation.py

# 2) Verify read-only (must FAIL on any change/missing file; nonzero exit)
python scripts/final_evidence/verify_release_manifest.py
```

Never regenerate the manifest immediately before verification merely to clear mismatches.

## This run

- Artifacts listed: **328**
- Failures: **0**
- Passed: **True**

Verification reports live under `results/final_evidence/validation/clean_checkout_verification.*`
(outside the hashed package).

`.gitattributes` enforces `eol=lf` for scientific text artifacts.
