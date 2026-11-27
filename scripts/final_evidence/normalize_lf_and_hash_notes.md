# P5 — Canonical LF and clean-checkout verification

## Policy

`.gitattributes` sets `text=auto eol=lf` for scientific text artifacts.

## Commands (do not invert)

```bash
# Generate (writes reports, then hashes; excludes self + clean_checkout_verification*)
python scripts/final_evidence/executable_validation.py

# Verify read-only from the SAME committed tree (Linux fresh checkout preferred)
python scripts/final_evidence/verify_release_manifest.py
```

Never regenerate the manifest immediately before verification merely to clear mismatches.

Verification reports live under `manifests/clean_checkout_verification.*` and are excluded from the hashed inventory.

CI job: `release-manifest-verify` in `.github/workflows/tests.yml`.
